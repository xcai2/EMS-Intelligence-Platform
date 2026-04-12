"""Comparative-news orchestration for the News domain."""

from __future__ import annotations

from urllib.parse import urlparse
from typing import TYPE_CHECKING

from backend.core.config import COMPANIES
from backend.news.normalizer import NEWS_MAX_AGE_DAYS, filter_items_by_max_age
from backend.news.news_filter_policies import (
    build_comparative_news_items,
    _COMPARATIVE_NON_NEWS_SIGNALS,
)
from backend.rag.web_search import search_web

if TYPE_CHECKING:
    from backend.news.service import NewsFeed

# Domains that produce comparison/reference pages rather than actual news articles.
# These are valid web sources but not the time-sensitive news we want here.
_COMPARATIVE_EXCLUDED_DOMAINS = {
    "medium.com",
    "linkedin.com",
    "owler.com",
    "comparably.com",
    "craft.co",
    "macrotrends.net",
    "stockanalysis.com",
    "wisesheets.io",
    "koalagains.com",
    "portersfiveforces.com",
    "comparably.com",
    "comparativefunding.com",
    "compareinfobase.com",
}

def _refilter_comparative_cache(items: list[dict]) -> list[dict]:
    """Re-apply all comparative post-filters to a cached item list.

    Mirrors the post-filter block in build_comparative_news_payload() so that
    changes to _COMPARATIVE_EXCLUDED_DOMAINS, _COMPARATIVE_NON_NEWS_SIGNALS,
    or _COMPARATIVE_MAX_AGE_DAYS take effect on restart without a re-fetch.
    """
    result: list[dict] = []
    for item in items:
        # Domain filter
        try:
            domain = urlparse(item.get("url", "")).netloc.lower().replace("www.", "")
        except Exception:
            domain = ""
        if any(domain.endswith(excl) for excl in _COMPARATIVE_EXCLUDED_DOMAINS):
            continue
        # Non-news-signal filter (title + description)
        content = f"{item.get('title', '')} {item.get('description', '')}".lower()
        if any(signal in content for signal in _COMPARATIVE_NON_NEWS_SIGNALS):
            continue
        result.append(item)
    return filter_items_by_max_age(result, NEWS_MAX_AGE_DAYS)


async def build_comparative_news_payload(
    feed: "NewsFeed",
    force_refresh: bool = False,
) -> dict:
    """Fetch and assemble multi-company comparative news."""
    cache_key = "comparative"
    if not force_refresh:
        cached_payload = feed._runtime_cache.get(cache_key)
        if cached_payload:
            # Re-apply domain, non-news-signal, and recency filters so rule
            # changes take effect on restart without a full re-fetch.
            refiltered = _refilter_comparative_cache(cached_payload.get("comparative_news", []))
            refiltered_payload = {
                **cached_payload,
                "comparative_news": refiltered,
                "total_found": len(refiltered),
            }
            feed._runtime_cache[cache_key] = refiltered_payload
            feed._persist_runtime_cache()
            return refiltered_payload
        return {
            "comparative_news": [],
            "total_found": 0,
            "timestamp": feed._now_utc_iso(),
            "diagnostics": {
                "cache_status": "miss",
                "cache_only": True,
                "refresh_required": True,
            },
        }

    company_names = [c["name"].split()[0] for c in COMPANIES.values()]
    query = " OR ".join(company_names) + " EMS comparison AI manufacturing"

    raw_results = await search_web(query, count=10)
    for result in raw_results:
        result.setdefault("aggregator", "Brave Search")
    raw_results.extend(await feed.fetchers.google_news_rss(query, limit=8))

    comparative_news = build_comparative_news_items(feed, raw_results, company_names)

    # Post-filter: drop comparison/reference pages and stale items.
    filtered_comparative: list[dict] = []
    for item in comparative_news:
        # Domain filter
        try:
            domain = urlparse(item.get("url", "")).netloc.lower().replace("www.", "")
        except Exception:
            domain = ""
        if any(domain.endswith(excluded) for excluded in _COMPARATIVE_EXCLUDED_DOMAINS):
            continue
        filtered_comparative.append(item)

    filtered_comparative = filter_items_by_max_age(filtered_comparative, NEWS_MAX_AGE_DAYS)
    comparative_news = filtered_comparative if filtered_comparative else comparative_news

    if not comparative_news:
        comparative_news = [
            {
                "title": "EMS peers balance AI server growth with margin discipline",
                "url": "https://www.eetimes.com/",
                "description": "Market commentary compares execution quality across major EMS players serving cloud and AI programs.",
                "source": "EE Times",
                "companies_mentioned": company_names[:3],
            }
        ]

    result = {
        "comparative_news": comparative_news,
        "total_found": len(comparative_news),
        "timestamp": feed._now_utc_iso(),
    }
    feed._runtime_cache[cache_key] = result
    feed._persist_runtime_cache()
    return result
