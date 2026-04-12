"""Normalization, source-mapping, and shared ordering helpers for News."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
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

NEWS_MAX_AGE_DAYS = 90

_RELATIVE_TIME_PATTERN = re.compile(
    r"^\s*(?:(?P<an>a|an)|(?P<count>\d+))\s+"
    r"(?P<unit>minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago\s*$",
    re.IGNORECASE,
)

_TEXT_DATE_FORMATS = (
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
    "%b %d %Y",
    "%Y-%m-%d",
)


def _parse_relative_published_dt(value: str) -> Optional[datetime]:
    """Parse relative timestamps like '17 hours ago' into UTC datetimes."""
    lowered = value.strip().lower()
    if not lowered:
        return None
    if lowered in {"today", "just now"}:
        return datetime.now(timezone.utc)
    if lowered == "yesterday":
        return datetime.now(timezone.utc) - timedelta(days=1)

    match = _RELATIVE_TIME_PATTERN.match(lowered)
    if not match:
        return None

    count_raw = match.group("count") or match.group("an") or "1"
    count = 1 if count_raw in {"a", "an"} else int(count_raw)
    unit = match.group("unit").lower()

    if unit.startswith("minute"):
        delta = timedelta(minutes=count)
    elif unit.startswith("hour"):
        delta = timedelta(hours=count)
    elif unit.startswith("day"):
        delta = timedelta(days=count)
    elif unit.startswith("week"):
        delta = timedelta(weeks=count)
    elif unit.startswith("month"):
        delta = timedelta(days=30 * count)
    elif unit.startswith("year"):
        delta = timedelta(days=365 * count)
    else:
        return None

    return datetime.now(timezone.utc) - delta


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

    relative_parsed = _parse_relative_published_dt(value)
    if relative_parsed is not None:
        return relative_parsed

    for date_format in _TEXT_DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, date_format)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        parsed = parsedate_to_datetime(value)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def filter_items_by_max_age(items: list[dict], max_age_days: int = NEWS_MAX_AGE_DAYS) -> list[dict]:
    """Drop items older than the configured window while keeping undated items."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    filtered: list[dict] = []
    for item in items:
        published = (item.get("published") or "").strip()
        if not published:
            filtered.append(item)
            continue
        published_dt = parse_published_dt(published)
        if published_dt is None or published_dt >= cutoff:
            filtered.append(item)
    return filtered


def sort_items_by_recency_and_relevance(items: list[dict]) -> list[dict]:
    """Sort feed items by timestamp first, then by lightweight relevance score."""

    def sort_key(item: dict) -> tuple[int, float, float]:
        published_dt = parse_published_dt(item.get("published", ""))
        has_date = 1 if published_dt else 0
        published_epoch = published_dt.timestamp() if published_dt else 0.0
        relevance = float(item.get("relevance_score", 0.0) or 0.0)
        return (has_date, published_epoch, relevance)

    return sorted(items, key=sort_key, reverse=True)
