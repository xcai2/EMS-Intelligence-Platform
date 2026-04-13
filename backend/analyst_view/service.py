"""
Analyst view intelligence service.

Company intel: per-company Brave search + LLM extraction of consensus rating,
price target, recent analyst actions, and key view.

Analyst summaries: per-analyst Brave search to find what each sell-side analyst
said recently; all snippets batched into a single LLM call that returns a
1-sentence "recent commentary" per analyst.

All results cached 30 min in analytics_cache.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from backend.core.cache import analytics_cache
from backend.core.config import BRAVE_API_KEY
from backend.core.llm_client import llm_structured
from backend.rag.web_search import search_web_with_diagnostics

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class CompanyIntelResult(BaseModel):
    ticker: str
    company: str
    kind: str                      # "EMS" | "Hyperscaler"
    consensus: str                 # Bullish | Neutral | Bearish | Mixed | Unknown
    price_target: str              # e.g. "$35" | "$30–$40" | "—"
    recent_actions: list[str]      # up to 5 concise analyst-action strings
    key_view: str                  # 2-sentence analyst consensus summary
    sources: list[dict]            # [{title, url}, ...]
    updated_at: str                # ISO-8601
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Company roster
# ---------------------------------------------------------------------------

TRACKED_COMPANIES: list[tuple[str, str, str]] = [
    # (ticker, display_name, kind)
    ("FLEX",  "Flex Ltd",              "EMS"),
    ("JBL",   "Jabil",                 "EMS"),
    ("CLS",   "Celestica",             "EMS"),
    ("BHE",   "Benchmark Electronics", "EMS"),
    ("SANM",  "Sanmina",               "EMS"),
    ("PLXS",  "Plexus",                "EMS"),
    ("AMZN",  "Amazon",                "Hyperscaler"),
    ("MSFT",  "Microsoft",             "Hyperscaler"),
    ("GOOGL", "Alphabet",              "Hyperscaler"),
    ("META",  "Meta",                  "Hyperscaler"),
    ("AAPL",  "Apple",                 "Hyperscaler"),
    ("ORCL",  "Oracle",                "Hyperscaler"),
]

_CACHE_PREFIX = "analyst_view:intel:"


def _cache_key(ticker: str) -> str:
    return f"{_CACHE_PREFIX}{ticker}"


# ---------------------------------------------------------------------------
# Per-company fetch + LLM extraction
# ---------------------------------------------------------------------------

async def _fetch_and_extract(ticker: str, company: str, kind: str) -> CompanyIntelResult:
    """Run a single Brave search + LLM extraction for one company.

    One broad query per company keeps total Brave usage to 12 calls per full
    refresh cycle (vs 24 with two queries), staying within the free-tier
    rate limit when combined with the semaphore in web_search.py.
    """
    query = f"{ticker} {company} analyst rating price target upgrade downgrade"

    results, err = await search_web_with_diagnostics(query, count=8, freshness="py")
    items: list[dict] = [r for r in results if (r.get("url") or "").strip()]

    if not items:
        return CompanyIntelResult(
            ticker=ticker, company=company, kind=kind,
            consensus="Unknown", price_target="—",
            recent_actions=[], key_view="No search results available.",
            sources=[], updated_at=datetime.now(timezone.utc).isoformat(),
            error="No Brave search results returned",
        )

    # Build LLM context from top 8 snippets
    context = "\n\n".join(
        f"[{i}] {r['title']}\n{r.get('description', '').strip()}"
        for i, r in enumerate(items[:8], 1)
    )

    class _Schema(BaseModel):
        consensus: str
        price_target: str
        recent_actions: list[str]
        key_view: str

    extracted: _Schema | None = await asyncio.to_thread(
        llm_structured,
        messages=[{
            "role": "user",
            "content": (
                f"Analyze these web search snippets about Wall Street analyst coverage "
                f"of {company} ({ticker}):\n\n{context}"
            ),
        }],
        system=(
            "You extract structured analyst intelligence from web search snippets. "
            "Return JSON with exactly these fields:\n"
            "- consensus: one of Bullish, Neutral, Bearish, Mixed, Unknown\n"
            "- price_target: consensus PT or range (e.g. '$35' or '$30–$40') "
            "if clearly mentioned in the snippets, else '—'\n"
            "- recent_actions: list of up to 5 recent analyst moves as short strings "
            "(e.g. 'Goldman Sachs raised PT to $40 (Buy)'). "
            "Empty list if none clearly found.\n"
            "- key_view: exactly 2 sentences summarising the current Wall Street "
            "consensus view on this stock based on the snippets."
        ),
        model_key="fast",
        schema=_Schema,
    )

    sources = [{"title": r["title"], "url": r["url"]} for r in items[:3]]

    if extracted:
        return CompanyIntelResult(
            ticker=ticker, company=company, kind=kind,
            consensus=extracted.consensus,
            price_target=extracted.price_target,
            recent_actions=extracted.recent_actions,
            key_view=extracted.key_view,
            sources=sources,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    # LLM failed — fall back to raw snippets so the card still has content
    fallback_actions = [
        (r.get("description") or r.get("title") or "")[:120]
        for r in items[:3]
    ]
    return CompanyIntelResult(
        ticker=ticker, company=company, kind=kind,
        consensus="Unknown", price_target="—",
        recent_actions=[a for a in fallback_actions if a],
        key_view="LLM extraction unavailable — see source links for analyst commentary.",
        sources=sources,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_all_company_intel() -> dict:
    """
    Return analyst intel for all tracked companies.

    Hits the per-ticker cache (30 min in analytics_cache) first;
    only fires new searches for stale / missing entries.
    """
    if not BRAVE_API_KEY:
        return {
            "companies": [],
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "warning": "Brave API key not configured (BRAVE_API_KEY). Company intel unavailable.",
        }

    cached_results: list[dict] = []
    to_fetch: list[tuple[str, str, str]] = []

    for ticker, company, kind in TRACKED_COMPANIES:
        hit = analytics_cache.get(_cache_key(ticker))
        if hit is not None:
            cached_results.append(hit)
        else:
            to_fetch.append((ticker, company, kind))

    if to_fetch:
        # Process companies one at a time so Brave searches queue through the
        # rate-limiter in web_search.py without bursting.
        for ticker, company, kind in to_fetch:
            try:
                result = await _fetch_and_extract(ticker, company, kind)
            except Exception as exc:
                result = CompanyIntelResult(
                    ticker=ticker, company=company, kind=kind,
                    consensus="Unknown", price_target="—",
                    recent_actions=[], key_view="Error fetching data.",
                    sources=[], updated_at=datetime.now(timezone.utc).isoformat(),
                    error=str(exc),
                )
            r_dict = result.model_dump()
            analytics_cache.set(_cache_key(ticker), r_dict)
            cached_results.append(r_dict)

    # Restore original order
    order = {ticker: i for i, (ticker, _, _) in enumerate(TRACKED_COMPANIES)}
    cached_results.sort(key=lambda x: order.get(x.get("ticker", ""), 99))

    return {
        "companies": cached_results,
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "warning": None,
    }


async def invalidate_company_cache(ticker: str | None = None) -> None:
    """Delete one ticker's cache entry (or all, if ticker is None)."""
    if ticker:
        analytics_cache.delete(_cache_key(ticker))
    else:
        for t, _, _ in TRACKED_COMPANIES:
            analytics_cache.delete(_cache_key(t))


# ---------------------------------------------------------------------------
# Analyst summaries
# ---------------------------------------------------------------------------

class AnalystSummaryResult(BaseModel):
    name: str
    institution: str
    summary: str        # 1-sentence recent commentary; "—" if nothing found
    source_url: str     # best source URL, or ""


_ANALYST_SUMMARIES_CACHE_KEY = "analyst_view:analyst_summaries_v2"

# (name, institution, key_stocks_to_search)
# key_stocks gives the Brave query the best chance of surfacing real
# research notes — we search institution + stocks, not by analyst name,
# because analyst names rarely appear in indexed financial web content.
ANALYST_ROSTER_META: list[tuple[str, str, str]] = [
    ("Thanos Moschopoulos", "BMO Capital Markets",    "Celestica Jabil EMS"),
    ("Matthew Sheerin",     "Stifel",                 "Flex Sanmina Plexus EMS"),
    ("Samik Chatterjee",    "JPMorgan",               "EMS electronics manufacturing Sanmina"),
    ("James Ricchiuti",     "Needham",                "Benchmark Plexus EMS manufacturing"),
    ("Maxim Matushansky",   "RBC Capital Markets",    "Celestica EMS industrials"),
    ("Daniel Chan",         "TD Securities",          "Celestica EMS tech"),
    ("Robert Young",        "Canaccord Genuity",      "EMS supply chain tech"),
    ("Mark Delaney",        "Goldman Sachs",          "Flex Jabil EMS hardware"),
    ("Timothy Long",        "Barclays",               "Flex Celestica EMS"),
    ("George Wang",         "Barclays",               "Flex EMS sector"),
    ("Ruplu Bhattacharya",  "Bank of America",        "Flex Jabil supply chain"),
    ("Jacob Moore",         "KeyBanc",                "Flex EMS industrials"),
    ("Steven Barger",       "KeyBanc",                "Flex industrials EMS"),
    ("Steven Fox",          "Fox Advisors",           "Flex EMS sector"),
    ("Ruben Roy",           "Stifel",                 "Flex Celestica EMS"),
    ("Todd Coupland",       "CIBC",                   "Celestica Canadian tech EMS"),
    ("Paul Treiber",        "RBC Capital Markets",    "Celestica tech"),
    ("Atif Malik",          "Citigroup",              "Celestica semiconductors EMS"),
    ("David Vogt",          "UBS",                    "Celestica tech hardware"),
]


async def get_all_analyst_summaries() -> dict:
    """
    For each analyst, search Brave by *institution + covered stocks* (not by
    analyst name — names are rarely indexed).  Deduplicate searches for analysts
    who share a firm, then batch all snippets into ONE LLM call.
    Cached 30 min.
    """
    cached = analytics_cache.get(_ANALYST_SUMMARIES_CACHE_KEY)
    if cached is not None:
        return cached

    if not BRAVE_API_KEY:
        return {
            "analysts": [],
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "warning": "Brave API key not configured.",
        }

    # Build deduplicated search plan: one query per unique (institution, stocks) pair
    # so two Barclays or two Stifel analysts share one search result set.
    seen_queries: dict[str, list[dict]] = {}   # query_key → snippets
    query_for: dict[str, str] = {}             # analyst_name → query_key

    for name, institution, stocks in ANALYST_ROSTER_META:
        key = f"{institution}|{stocks}"
        query_for[name] = key
        if key not in seen_queries:
            seen_queries[key] = []  # placeholder; filled below

    # Run deduplicated searches sequentially (rate-limited via semaphore)
    for key in seen_queries:
        institution, stocks = key.split("|", 1)
        query = f"{institution} {stocks} analyst rating note"
        results, _ = await search_web_with_diagnostics(query, count=4)
        seen_queries[key] = results

    # Build per-analyst snippet sets (shared results for same-firm analysts)
    analyst_snippets: list[tuple[str, str, list[dict]]] = [
        (name, institution, seen_queries[query_for[name]])
        for name, institution, _ in ANALYST_ROSTER_META
    ]

    # One LLM call — pass all snippets grouped by analyst
    sections: list[str] = []
    for name, institution, snippets in analyst_snippets:
        lines = "\n".join(
            f"  - {r['title']}: {r.get('description', '')[:200]}"
            for r in snippets
        ) or "  (no results)"
        sections.append(f"Analyst: {name} ({institution})\n{lines}")

    context = "\n\n".join(sections)

    class _SummaryItem(BaseModel):
        name: str
        summary: str

    class _SummariesSchema(BaseModel):
        summaries: list[_SummaryItem]

    extracted: _SummariesSchema | None = await asyncio.to_thread(
        llm_structured,
        messages=[{
            "role": "user",
            "content": (
                "These are recent web search snippets for research firms covering EMS stocks. "
                "Each analyst below is from that firm. Based on the snippets, write a "
                "1-sentence summary of the most notable recent call, price target, or "
                "rating action attributable to each named analyst. "
                "Use '—' only if absolutely nothing can be attributed.\n\n" + context
            ),
        }],
        system=(
            "You attribute recent analyst commentary from institutional research snippets. "
            "Return JSON with a 'summaries' list. Each item:\n"
            "- name: analyst full name exactly as given\n"
            "- summary: one sentence (≤30 words) on their most recent notable call or "
            "view on the stocks they cover. Infer from the firm's activity when the "
            "analyst's name is not explicitly mentioned. Use '—' only as a last resort."
        ),
        model_key="fast",
        schema=_SummariesSchema,
    )

    summary_map: dict[str, str] = {}
    if extracted:
        for item in extracted.summaries:
            summary_map[item.name] = item.summary

    # Best source URL: first snippet for the analyst's institution query
    source_map: dict[str, str] = {
        name: (snippets[0]["url"] if snippets else "")
        for name, _, snippets in analyst_snippets
    }

    analysts_out: list[dict] = [
        AnalystSummaryResult(
            name=name,
            institution=institution,
            summary=summary_map.get(name, "—"),
            source_url=source_map.get(name, ""),
        ).model_dump()
        for name, institution, _ in ANALYST_ROSTER_META
    ]

    payload = {
        "analysts": analysts_out,
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "warning": None,
    }
    analytics_cache.set(_ANALYST_SUMMARIES_CACHE_KEY, payload)
    return payload
