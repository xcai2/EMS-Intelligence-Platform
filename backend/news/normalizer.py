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
    "%d %B %Y",
    "%d %b %Y",
    "%Y-%m-%d",
)

_TITLE_DATE_PATTERNS = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(
        r"\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|"
        r"Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+\d{4}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|"
        r"Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2}\s+\d{4}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d{1,2}\s+(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|"
        r"Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{4}\b",
        re.IGNORECASE,
    ),
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


def extract_title_date_dt(title: str) -> Optional[datetime]:
    """Extract a simple explicit date from the title when structured fields are missing.

    This is a Phase 1 fallback only. It intentionally supports a small set of
    obvious date forms and does not attempt fuzzy or semantic date inference.
    """
    value = (title or "").strip()
    if not value:
        return None

    for pattern in _TITLE_DATE_PATTERNS:
        match = pattern.search(value)
        if not match:
            continue
        parsed = parse_published_dt(match.group(0))
        if parsed is not None:
            return parsed
    return None

