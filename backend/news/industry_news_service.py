"""Industry-news orchestration for the News domain."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from backend.core.config import TRACKED_COMPANY_NAMES
from backend.news.news_filters import normalize_result
from backend.news.news_filter_policies import filter_industry_news_items
from backend.news.normalizer import filter_items_by_max_age
from backend.news.sources import FALLBACK_INDUSTRY_NEWS
from backend.rag.web_search import search_web

if TYPE_CHECKING:
    from backend.news.service import NewsFeed


async def build_industry_news_payload(
    feed: "NewsFeed",
    count: int = 15,
    force_refresh: bool = False,
) -> dict:
    """Fetch and assemble industry-theme news."""
    cache_key = f"industry:{count}"
    if not force_refresh:
        cached_payload = feed._runtime_cache.get(cache_key)
        if cached_payload:
            # Re-apply current filter rules so changes to EXCLUDED_NOISE_TERMS,
            # is_ai_related(), or mentions_tracked_company() take effect on restart.
            refiltered = filter_industry_news_items(
                feed,
                filter_items_by_max_age(cached_payload.get("news", [])),
            )
            refiltered_payload = {
                **cached_payload,
                "news": refiltered[:count],
                "total_found": len(refiltered),
            }
            feed._runtime_cache[cache_key] = refiltered_payload
            feed._persist_runtime_cache()
            return refiltered_payload
        return {
            "news": [],
            "total_found": 0,
            "timestamp": feed._now_utc_iso(),
            "diagnostics": {
                "cache_status": "miss",
                "cache_only": True,
                "refresh_required": True,
            },
        }

    tracked_company_query = " ".join(TRACKED_COMPANY_NAMES) + " AI news"
    queries = [
        "EMS AI infrastructure supply chain news",
        "electronics manufacturing data center demand",
        tracked_company_query,
        "NVIDIA hyperscaler manufacturing partners news",
        "liquid cooling data center manufacturing news",
        "immersion cooling AI server supply chain news",
    ]

    merged_items: list[dict] = []
    for query in queries:
        for result in await search_web(query, count=5):
            result.setdefault("aggregator", "Brave Search")
            normalized = normalize_result(feed, result)
            if normalized:
                merged_items.append(normalized)

        for result in await feed.fetchers.google_news_rss(query, limit=5):
            normalized = normalize_result(feed, result)
            if normalized:
                merged_items.append(normalized)

    if not merged_items:
        merged_items = [normalize_result(feed, item) for item in FALLBACK_INDUSTRY_NEWS]
        merged_items = [item for item in merged_items if item]

    unique_results = filter_industry_news_items(feed, filter_items_by_max_age(merged_items))

    result = {
        "news": unique_results[:count],
        "total_found": len(unique_results),
        "timestamp": feed._now_utc_iso(),
    }
    feed._runtime_cache[cache_key] = result
    feed._persist_runtime_cache()
    return result
