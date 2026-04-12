"""Feed-specific filtering policies for company, industry, and comparative news."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote_plus, urlparse

from backend.news.content_signals import is_ai_related, mentions_tracked_company
from backend.news.filtering import EXCLUDED_NOISE_TERMS
from backend.news.news_filters import dedupe_items, normalize_result
from backend.news.normalizer import sort_items_by_recency_and_relevance
from backend.news.query_helpers import get_company_aliases
from backend.news.sources import OFFICIAL_COMPANY_SOURCES

if TYPE_CHECKING:
    from backend.news.service import NewsFeed

_SECOND_PASS_EXCLUDED_DOMAINS = {
    "medium.com",
    "ventureoutsource.com",
    "dataequipmentmanufacturers.com",
    "asteelflash.com",
    "owler.com",
    "chartmill.com",
    "simplywall.st",
    "stockstory.org",
    "stockstory.com",
    "samsung.com",
    "public.com",
}

_SECOND_PASS_NON_NEWS_SIGNALS = [
    "competitors and alternatives",
    "top competitors",
    "alternatives",
    "competitors",
    "owler",
    "chartmill",
    "simplywall",
    "stockstory",
    "how to compare",
    "comparison of",
    "market report",
    "industry report",
    "swot analysis",
    "porter's five force",
    "capabilities/artificial-intelligence-for-supply-chain",
    "report of proposed sale of securities",
    "statement of changes in beneficial ownership",
    "amended statement of ownership",
    "current report filing",
    "sec-filings",
    "filingid=",
]

_SECOND_PASS_EXCLUDED_SOURCE_TERMS = [
    "chartmill",
    "simplywall",
    "stockstory",
    "owler",
    "samsung",
    "public news",
]

_FLEX_CONTEXT_TERMS = [
    "ems",
    "electronics manufacturing",
    "contract manufacturing",
    "manufacturing",
    "supply chain",
    "ai",
    "data center",
    "hyperscaler",
    "server",
    "cloud infrastructure",
    "factory",
    "operations",
    "capex",
    "investor relations",
    "earnings",
]

_CLS_CONTEXT_TERMS = [
    "celestica",
    "celestica inc",
    "nyse:cls",
    "tsx:cls",
    "electronics manufacturing",
    "contract manufacturing",
    "supply chain",
    "data center",
    "cloud infrastructure",
    "investor relations",
    "earnings",
    "revenue",
    "guidance",
]

_BHE_CONTEXT_TERMS = [
    "benchmark electronics",
    "nyse:bhe",
    "bhe",
    "bench.com",
    "electronics manufacturing",
    "contract manufacturing",
    "manufacturing services",
    "ems",
    "supply chain",
    "data center",
    "semiconductor",
    "investor relations",
    "earnings",
    "revenue",
    "guidance",
]


def _domain_from_url(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().replace("www.", "")
    except Exception:
        return ""


def _is_second_pass_noise_item(item: dict, allow_domains: set[str] | None = None) -> bool:
    """Apply cache-driven noise controls after normalization and before ranking."""
    domain = _domain_from_url(item.get("url", ""))
    allowed = allow_domains or set()
    if domain and any(domain.endswith(excluded) for excluded in _SECOND_PASS_EXCLUDED_DOMAINS):
        if not any(domain.endswith(allowed_domain) for allowed_domain in allowed):
            return True
    source_lower = (item.get("source") or "").lower()
    if any(term in source_lower for term in _SECOND_PASS_EXCLUDED_SOURCE_TERMS):
        return True
    content = f"{item.get('title', '')} {item.get('description', '')} {item.get('url', '')}".lower()
    return any(signal in content for signal in _SECOND_PASS_NON_NEWS_SIGNALS)


def _has_flex_industry_context(item: dict) -> bool:
    """Require non-official FLEX mentions to carry EMS/manufacturing context."""
    content = f"{item.get('title', '')} {item.get('description', '')} {item.get('url', '')}".lower()
    return any(term in content for term in _FLEX_CONTEXT_TERMS)


def _has_cls_company_context(item: dict) -> bool:
    """Require non-official CLS mentions to carry Celestica/issuer context."""
    content = f"{item.get('title', '')} {item.get('description', '')} {item.get('url', '')}".lower()
    return any(term in content for term in _CLS_CONTEXT_TERMS)


def _has_bhe_company_context(item: dict) -> bool:
    """Require non-official BHE mentions to carry Benchmark Electronics context."""
    content = f"{item.get('title', '')} {item.get('description', '')} {item.get('url', '')}".lower()
    return any(term in content for term in _BHE_CONTEXT_TERMS)


def _ensure_published(item: dict, feed: "NewsFeed") -> dict:
    """Backfill missing published values so UI and sorting have stable timestamps."""
    published = (item.get("published") or "").strip()
    if published:
        return item
    enriched = dict(item)
    enriched["published"] = feed._now_utc_iso()
    return enriched


def build_company_news_response(raw_payload: dict, category: Optional[str], count: int, categories_map: dict[str, list[str]]) -> dict:
    """Apply post-fetch category filtering to a cached raw company payload."""
    items = raw_payload.get("news", [])
    if category and category in categories_map:
        items = [item for item in items if category in item.get("categories", [])]
    visible_items = items[:count] if count > 0 else items

    return {
        "ticker": raw_payload.get("ticker"),
        "company_name": raw_payload.get("company_name"),
        "category_filter": category,
        "news": visible_items,
        "total_found": len(items),
        "timestamp": raw_payload.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "diagnostics": raw_payload.get("diagnostics", {}),
    }


def _alias_in_title_strict(alias_lower: str, title: str) -> bool:
    """Single-word alias match for strict-mode companies.

    Requires the alias to appear in 'subject position': at the very start of the
    title, or immediately after a common separator (': ', ', ', ' — ', ' - ').
    This prevents brand-modifier patterns like 'Omega Flex' or 'Galaxy Book Flex'
    from triggering a match on the single word 'flex'.
    Multi-word aliases are handled by the caller with plain substring matching.
    """
    pattern = r'(?:^|(?<=:\s)|(?<=,\s)|(?<= — )|(?<= - ))' + re.escape(alias_lower) + r'(?=\s|,|:|$)'
    return bool(re.search(pattern, title))


def is_company_related_item(feed: "NewsFeed", item: dict, ticker: str, company_name: str) -> bool:
    """Keep company items only when they clearly belong to the selected issuer.

    Decision order
    --------------
    1. Per-company noise rejection  — config: excluded_noise_terms
       Any noise pattern in title+description → reject immediately.
    2. Official domain match        — config: domain
       Item URL matches the company's domain → accept (official source is always relevant).
    3. Alias in title               — aliases from get_company_aliases()
       Any alias (single- or multi-word) in the title → accept.
    4. Multi-word alias in description
       Unambiguous even for companies with short names (e.g. "Flex Ltd" in desc → accept).
    5. Source field match
       item.source contains the company's short name → accept.
    6. Single-word alias in description (non-strict companies only)
       Gated by config: strict_title_match=True disables this step for companies
       whose short name is a common English word (Flex, Benchmark).
    """
    title = (item.get("title") or "").lower()
    description = (item.get("description") or "").lower()
    content = f"{title} {description}"
    url = (item.get("url") or "")
    source_text = (item.get("source") or "").lower()

    source_cfg = OFFICIAL_COMPANY_SOURCES.get(ticker, {})
    aliases = get_company_aliases(ticker, company_name)

    # --- Step 1: per-company noise rejection ---
    # 1a. Domain-level exclusion: reject before touching content.
    for excl_domain in (source_cfg.get("excluded_domains") or []):
        try:
            item_domain = (urlparse(url).netloc or "").lower().replace("www.", "")
            if item_domain.endswith(excl_domain.lower()):
                return False
        except Exception:
            pass
    # 1b. Content-pattern exclusion: reject if any noise term appears in title+description.
    for noise in (source_cfg.get("excluded_noise_terms") or []):
        if noise.lower() in content:
            return False

    # --- Step 2: official domain match ---
    domain = (source_cfg.get("domain") or "").lower()
    item_domain = ""
    if domain:
        try:
            item_domain = (urlparse(url).netloc or "").lower().replace("www.", "")
            if item_domain.endswith(domain):
                return True
        except Exception:
            pass

    # FLEX hard gate: for non-official domains, require EMS/manufacturing context.
    # This rejects ticker-only compare/valuation/product pages that mention "FLEX"
    # without being about Flex Ltd operations.
    if ticker == "FLEX" and not _has_flex_industry_context(item):
        return False
    if ticker == "CLS" and not _has_cls_company_context(item):
        return False
    if ticker == "BHE" and not _has_bhe_company_context(item):
        return False

    # --- Step 3: alias in title ---
    # For strict-mode companies (common English words like "flex", "benchmark"),
    # single-word aliases must appear in subject position to avoid matching brand
    # modifiers like "Omega Flex" or "Galaxy Book Flex".
    # Multi-word aliases (e.g. "Flex Ltd", "Flextronics") use plain substring match.
    strict = source_cfg.get("strict_title_match", False)
    for alias in aliases:
        alias_lower = alias.lower()
        if " " in alias_lower:
            if alias_lower in title:
                return True
        elif strict:
            if _alias_in_title_strict(alias_lower, title):
                return True
        else:
            if alias_lower in title:
                return True

    # --- Step 4: multi-word alias in description ---
    multi_word_aliases = [a.lower() for a in aliases if " " in a]
    if any(alias in description for alias in multi_word_aliases):
        return True

    # --- Step 5: source field match ---
    short_name = company_name.split()[0].lower()
    if short_name in source_text:
        return True

    # --- Step 6: single-word alias in description (non-strict only) ---
    if not source_cfg.get("strict_title_match", False):
        if any(alias.lower() in description for alias in aliases):
            return True

    return False


def filter_company_news_items(feed: "NewsFeed", items: list[dict], ticker: str, company_name: str) -> list[dict]:
    """Dedupe, validate company affinity, and rank broad company candidates."""
    source_cfg = OFFICIAL_COMPANY_SOURCES.get(ticker, {})
    official_domain = (source_cfg.get("domain") or "").lower().strip()
    allow_domains = {official_domain} if official_domain else set()
    filtered_items = []
    for item in dedupe_items(items):
        if _is_second_pass_noise_item(item, allow_domains):
            continue
        if is_company_related_item(feed, item, ticker, company_name):
            filtered_items.append(_ensure_published(item, feed))
    return sort_items_by_recency_and_relevance(filtered_items)


def filter_industry_news_items(feed: "NewsFeed", items: list[dict]) -> list[dict]:
    """Keep only items that reflect the tracked theme or tracked companies."""
    unique_results = []
    for item in dedupe_items(items):
        if _is_second_pass_noise_item(item):
            continue
        content = f"{item['title']} {item.get('description', '')}"
        content_lower = content.lower()
        # Global noise exclusion before thematic keep — catches EMS acronym
        # ambiguity (FortiClient EMS, emergency medical, etc.) and other
        # cross-company noise defined in filtering.py.
        if any(noise in content_lower for noise in EXCLUDED_NOISE_TERMS):
            continue
        if is_ai_related(content) or mentions_tracked_company(content):
            unique_results.append(_ensure_published(item, feed))
    return unique_results


# Patterns in title/description that signal a static analysis page rather than a news article.
# Checked case-insensitively against title + description before the company-mention gate.
_COMPARATIVE_NON_NEWS_SIGNALS = [
    "competitive landscape",
    "competitive analysis",
    "market report",
    "industry report",
    "porter's five force",
    "portersfiveforce",
    "bcg matrix",
    " vs. ",
    " vs ",
    "comparison of",
    "compared to",
    "swot analysis",
    "how to compare",
    "competitors",
    "alternatives",
    "top competitors",
    "owler",
]


def build_comparative_news_items(feed: "NewsFeed", raw_results: list[dict], company_names: list[str]) -> list[dict]:
    """Keep multi-company stories that can support competitive comparison views."""
    comparative_news = []
    for result in raw_results:
        normalized = normalize_result(feed, result)
        if not normalized:
            continue
        title = normalized.get("title", "")
        description = normalized.get("description", "")
        url = normalized.get("url", "")
        content = f"{title} {description}".lower()

        # Reject static analysis/comparison pages before the company-mention gate.
        if any(signal in content for signal in _COMPARATIVE_NON_NEWS_SIGNALS):
            continue

        mentioned = [name for name in company_names if name.lower() in content]
        if len(mentioned) >= 2:
            comparative_news.append(
                {
                    "title": title,
                    "url": url,
                    "backup_url": normalized.get("backup_url") or f"https://www.google.com/search?q={quote_plus(title)}",
                    "description": description,
                    "source": normalized.get("source"),
                    "original_source": normalized.get("original_source"),
                    "aggregator": normalized.get("aggregator"),
                    "published": normalized.get("published") or "",
                    "companies_mentioned": mentioned,
                }
            )
    return dedupe_items(comparative_news)
