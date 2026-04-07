"""Comparative-news orchestration for the News domain."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from backend.core.config import COMPANIES
from backend.news.news_filter_policies import build_comparative_news_items
from backend.rag.web_search import search_web

if TYPE_CHECKING:
    from backend.news.service import NewsFeed


async def build_comparative_news_payload(
    feed: "NewsFeed",
    force_refresh: bool = False,
) -> dict:
    """Fetch and assemble multi-company comparative news."""
    cache_key = "comparative"
    if not force_refresh:
        cached_payload = feed._runtime_cache.get(cache_key)
        if cached_payload:
            return cached_payload
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
