"""Normalization, source-mapping, and shared ordering helpers for News."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

SOURCE_DOMAIN_LABELS = {
    "reuters.com": "Reuters",
    "bloomberg.com": "Bloomberg",
    "wsj.com": "Wall Street Journal",
    "ft.com": "Financial Times",
    "cnbc.com": "CNBC",
    "yahoo.com": "Yahoo Finance",
    "seekingalpha.com": "Seeking Alpha",
    "fool.com": "Motley Fool",
    "marketwatch.com": "MarketWatch",
    "barrons.com": "Barron's",
    "businesswire.com": "Business Wire",
    "prnewswire.com": "PR Newswire",
    "globenewswire.com": "GlobeNewswire",
}


def parse_published_dt(published: str) -> Optional[datetime]:
    """Parse common news timestamp formats into UTC datetimes."""
    value = (published or "").strip()
    if not value:
        return None

    iso_candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(value)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def sort_items_by_recency_and_relevance(items: list[dict]) -> list[dict]:
    """Sort feed items by timestamp first, then by lightweight relevance score."""

    def sort_key(item: dict) -> tuple[int, float, float]:
        published_dt = parse_published_dt(item.get("published", ""))
        has_date = 1 if published_dt else 0
        published_epoch = published_dt.timestamp() if published_dt else 0.0
        relevance = float(item.get("relevance_score", 0.0) or 0.0)
        return (has_date, published_epoch, relevance)

    return sorted(items, key=sort_key, reverse=True)
