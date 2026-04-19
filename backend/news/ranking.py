"""Top News ranking for Phase 2.

Responsibility: given a clean, deduplicated list of news items (sec_filing_rss
already removed), produce a scored candidate pool and return the top N items.

Scoring formula:
    top_score = freshness_score + source_quality_score + intent_weight + source_count_bonus

Ranges (approximate, all non-negative):
    freshness_score:       0.0 – 1.0   (1.0 = published within last 6 hours)
    source_quality_score:  0.0 – 1.0   (1.0 = tier-1 outlet)
    intent_weight:         0.0 – 1.0   (official_name = 1.0)
    source_count_bonus:    0.0 – 0.6   (0.2 per extra match beyond 1, capped at 3)
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from backend.news.models import Company
from backend.news.normalizer import parse_published_dt

logger = logging.getLogger(__name__)

TOP_NEWS_COUNT = 7
_COMPANY_TOP_NEWS_WINDOW_DAYS = 7

# ---------------------------------------------------------------------------
# Source quality tiers
# ---------------------------------------------------------------------------

_TIER_1_DOMAINS: frozenset[str] = frozenset({
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "apnews.com",
    "cnbc.com",
    "barrons.com",
    "economist.com",
})

_TIER_2_DOMAINS: frozenset[str] = frozenset({
    "seekingalpha.com",
    "marketwatch.com",
    "fool.com",
    "thestreet.com",
    "businesswire.com",
    "prnewswire.com",
    "globenewswire.com",
    "accesswire.com",
    "businessinsider.com",
    "techcrunch.com",
    "theverge.com",
    "arstechnica.com",
    "electronicdesign.com",
    "edn.com",
    "eetimes.com",
})

_INTENT_WEIGHTS: dict[str, float] = {
    "official_name": 1.0,
    "stock_news": 0.75,
    "industry_news": 0.5,
    "supporting_query": 0.25,
}

# Max number of articles from the same root domain in the candidate pool
_MAX_PER_DOMAIN = 3

_LEGAL_SUFFIXES: tuple[str, ...] = (
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "company",
    "co",
    "limited",
    "ltd",
    "plc",
    "holdings",
)


def _root_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().replace("www.", "")
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return ""


def _normalize_text(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip() + " "


def _company_terms(company: Company) -> list[str]:
    candidates: list[str] = []
    full_name = (company.full_name or "").strip()
    if full_name:
        candidates.append(full_name)
        parts = [p for p in re.split(r"[^A-Za-z0-9]+", full_name) if p]
        if parts:
            trimmed = parts[:]
            while trimmed and trimmed[-1].lower() in _LEGAL_SUFFIXES:
                trimmed.pop()
            if trimmed:
                candidates.append(" ".join(trimmed))
                if len(trimmed) == 1:
                    candidates.append(trimmed[0])
    aliases = [a.strip() for a in (company.aliases or "").split(",") if a.strip()]
    candidates.extend(aliases)
    candidates.append(company.ticker)

    seen: set[str] = set()
    result: list[str] = []
    for value in candidates:
        normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _is_company_relevant(item: dict, company: Company) -> bool:
    if item.get("source_type") == "company_news_rss":
        return True
    official_domain = (company.official_domain or "").lower().strip()
    item_domain = _root_domain(item.get("url", ""))
    if official_domain and item_domain.endswith(official_domain):
        return True

    haystack = _normalize_text(" ".join([
        item.get("title", ""),
        item.get("description", ""),
        item.get("source", ""),
    ]))
    terms = _company_terms(company)
    return any(f" {term} " in haystack for term in terms)


def _freshness_score(published: str) -> float:
    """Return a freshness score in [0, 1].

    1.0  = published within the last 6 hours
    0.75 = within 24 hours
    0.5  = within 3 days
    0.25 = within 7 days
    0.1  = within 30 days
    0.0  = older than 30 days or undated
    """
    dt = parse_published_dt(published)
    if dt is None:
        return 0.0
    age = datetime.now(timezone.utc) - dt
    if age <= timedelta(hours=6):
        return 1.0
    if age <= timedelta(hours=24):
        return 0.75
    if age <= timedelta(days=3):
        return 0.5
    if age <= timedelta(days=7):
        return 0.25
    if age <= timedelta(days=30):
        return 0.1
    return 0.0


def _source_quality_score(url: str) -> float:
    domain = _root_domain(url)
    if domain in _TIER_1_DOMAINS:
        return 1.0
    if domain in _TIER_2_DOMAINS:
        return 0.5
    return 0.2


def _intent_weight(intent: str | None, matched_intents: list) -> float:
    if matched_intents:
        return max(_INTENT_WEIGHTS.get(i, 0.0) for i in matched_intents)
    return _INTENT_WEIGHTS.get(intent or "", 0.0)


def _source_count_bonus(match_count: int) -> float:
    extra = max(0, match_count - 1)
    return min(extra * 0.2, 0.6)


def score_item(item: dict) -> float:
    return (
        _freshness_score(item.get("published", ""))
        + _source_quality_score(item.get("url", ""))
        + _intent_weight(item.get("intent"), item.get("matched_intents") or [])
        + _source_count_bonus(item.get("match_count") or 0)
    )


# ---------------------------------------------------------------------------
# Candidate pool
# ---------------------------------------------------------------------------

def _is_valid_candidate(item: dict) -> bool:
    """Return True if this item is eligible for the Top News candidate pool."""
    # Must have a published date
    if not item.get("published"):
        return False
    # Must not be a SEC filing (already separated upstream, but defensive check)
    if item.get("source_type") == "sec_filing_rss":
        return False
    # Must have a non-empty title
    if not (item.get("title") or "").strip():
        return False
    return True


def _within_recent_days(published: str, days: int) -> bool:
    dt = parse_published_dt(published)
    if dt is None:
        return False
    return (datetime.now(timezone.utc) - dt) <= timedelta(days=days)


def build_top_news(items: list[dict], n: int = TOP_NEWS_COUNT, company: Company | None = None) -> list[dict]:
    """Select and rank the top N news items from a deduplicated, SEC-free list.

    Steps:
    1. Filter to valid candidates (has date, not SEC, has title).
    2. If company context is provided, keep only items relevant to that company.
    3. For single-company views, further restrict Top News to the last 7 days.
       If that yields fewer than N items, do NOT backfill older news.
    4. Limit per-domain representation to _MAX_PER_DOMAIN articles.
    5. Score each candidate.
    6. Return top N by score.
    """
    candidates = [item for item in items if _is_valid_candidate(item)]
    if company is not None:
        candidates = [item for item in candidates if _is_company_relevant(item, company)]
        candidates = [
            item for item in candidates
            if _within_recent_days(item.get("published", ""), _COMPANY_TOP_NEWS_WINDOW_DAYS)
        ]

    # Per-domain cap
    domain_count: dict[str, int] = {}
    capped: list[dict] = []
    for item in candidates:
        d = _root_domain(item.get("url", ""))
        if domain_count.get(d, 0) < _MAX_PER_DOMAIN:
            capped.append(item)
            domain_count[d] = domain_count.get(d, 0) + 1

    scored = sorted(capped, key=score_item, reverse=True)
    return scored[:n]
