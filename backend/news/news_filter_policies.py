"""Feed-specific filtering policies for company, industry, and comparative news."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote_plus, urlparse

from backend.news.content_signals import is_ai_related, mentions_tracked_company
from backend.news.news_filters import dedupe_items, normalize_result
from backend.news.normalizer import sort_items_by_recency_and_relevance
from backend.news.query_helpers import get_company_aliases
from backend.news.sources import OFFICIAL_COMPANY_SOURCES

if TYPE_CHECKING:
    from backend.news.service import NewsFeed


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


def is_company_related_item(feed: "NewsFeed", item: dict, ticker: str, company_name: str) -> bool:
    """Keep company items only when they clearly belong to the selected issuer."""
    content = f"{item.get('title', '')} {item.get('description', '')}".lower()
    aliases = get_company_aliases(ticker, company_name)
    if any(alias.lower() in content for alias in aliases):
        return True

    source = OFFICIAL_COMPANY_SOURCES.get(ticker, {})
    domain = (source.get("domain") or "").lower()
    if not domain:
        return False
    try:
        item_domain = (urlparse(item.get("url", "")).netloc or "").lower().replace("www.", "")
        if item_domain.endswith(domain):
            return True
    except Exception:
        pass

    source_text = (item.get("source") or "").lower()
    return company_name.split()[0].lower() in source_text


def filter_company_news_items(feed: "NewsFeed", items: list[dict], ticker: str, company_name: str) -> list[dict]:
    """Dedupe, validate company affinity, and rank broad company candidates."""
    filtered_items = []
    for item in dedupe_items(items):
        if is_company_related_item(feed, item, ticker, company_name):
            filtered_items.append(item)
    return sort_items_by_recency_and_relevance(filtered_items)


def filter_industry_news_items(feed: "NewsFeed", items: list[dict]) -> list[dict]:
    """Keep only items that reflect the tracked theme or tracked companies."""
    unique_results = []
    for item in dedupe_items(items):
        content = f"{item['title']} {item.get('description', '')}"
        if is_ai_related(content) or mentions_tracked_company(content):
            unique_results.append(item)
    return unique_results


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
                    "companies_mentioned": mentioned,
                }
            )
    return dedupe_items(comparative_news)
