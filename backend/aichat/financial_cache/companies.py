"""Company master data for the AI Chat financial cache.

Hardcoded by design: keeps this module independent of news_config.db.
Two groups share the same schema and fetch flow — `group` is informational only.

`fy_end_month` is the calendar month in which each company's fiscal year ends
(e.g. JBL=8 means FY2025 Q2 = period ending 2025-02-28). Used to label cache
rows with FY/Q notation when feeding LLM context.
"""

from typing import Optional

COMPANIES: dict[str, dict] = {
    # ---- EMS targets ---------------------------------------------------
    "FLEX":  {"name": "Flex Ltd",                "group": "ems",          "fy_end_month": 3,
              "aliases": ["Flex", "Flextronics"]},
    "JBL":   {"name": "Jabil Inc",               "group": "ems",          "fy_end_month": 8,
              "aliases": ["Jabil"]},
    "CLS":   {"name": "Celestica Inc",           "group": "ems",          "fy_end_month": 12,
              "aliases": ["Celestica"]},
    "BHE":   {"name": "Benchmark Electronics",   "group": "ems",          "fy_end_month": 12,
              "aliases": ["Benchmark"]},
    "SANM":  {"name": "Sanmina Corporation",     "group": "ems",          "fy_end_month": 9,
              "aliases": ["Sanmina"]},
    "PLXS":  {"name": "Plexus Corp",             "group": "ems",          "fy_end_month": 9,
              "aliases": ["Plexus"]},

    # ---- Hyperscalers / large customers --------------------------------
    "AMZN":  {"name": "Amazon.com, Inc.",        "group": "hyperscaler",  "fy_end_month": 12,
              "aliases": ["Amazon", "AWS", "亚马逊"]},
    "GOOGL": {"name": "Alphabet Inc.",           "group": "hyperscaler",  "fy_end_month": 12,
              "aliases": ["Google", "GOOG", "Alphabet", "谷歌"]},
    "MSFT":  {"name": "Microsoft Corporation",   "group": "hyperscaler",  "fy_end_month": 6,
              "aliases": ["Microsoft", "微软"]},
    "META":  {"name": "Meta Platforms, Inc.",    "group": "hyperscaler",  "fy_end_month": 12,
              "aliases": ["Meta", "Facebook"]},
    "ORCL":  {"name": "Oracle Corporation",      "group": "hyperscaler",  "fy_end_month": 5,
              "aliases": ["Oracle", "甲骨文"]},
}


def fiscal_label(ticker: str, period_end: str) -> Optional[str]:
    """Convert a calendar period_end ('YYYY-MM-DD') to 'FY{year} Q{1-4}'.

    Returns None if ticker is unknown or the date can't be parsed.
    """
    info = COMPANIES.get(ticker.upper())
    if not info or "fy_end_month" not in info:
        return None
    try:
        y, m, d = period_end.split("-")
        y, m, d = int(y), int(m), int(d)
    except (ValueError, AttributeError):
        return None
    fy_end = info["fy_end_month"]
    if m > fy_end:
        # 52/53-week calendars let period_end drift into the first days of the
        # month after FY-end (e.g. SANM FY2021 ends 2021-10-02, not 2021-09-30).
        # Absorb up to 7 days of drift so the label stays in the correct FY.
        if m == fy_end + 1 and d <= 7:
            fy = y
            q = 4
        else:
            fy = y + 1
            q = (m - fy_end - 1) // 3 + 1
    else:
        fy = y
        q = (m + 12 - fy_end - 1) // 3 + 1
    if q < 1 or q > 4:
        return None
    return f"FY{fy} Q{q}"


def get_company(ticker: str) -> Optional[dict]:
    """Return the company record by ticker (case-insensitive). None if unknown."""
    return COMPANIES.get(ticker.upper())


def all_tickers() -> list[str]:
    """All tickers tracked by the cache."""
    return list(COMPANIES.keys())


def resolve_ticker(text: str) -> Optional[str]:
    """Resolve a free-form mention to a ticker via name or alias match.

    Match is case-insensitive on whole words. Returns None on no match.
    """
    if not text:
        return None
    lowered = text.lower()
    for ticker, info in COMPANIES.items():
        if ticker.lower() in lowered.split():
            return ticker
        for alias in [info["name"], *info["aliases"]]:
            if alias.lower() in lowered:
                return ticker
    return None


def resolve_all_tickers(text: str) -> list[str]:
    """Resolve all company mentions in a text to a list of tickers.
    Returns a list of matched tickers in order of appearance.
    """
    if not text:
        return []
    lowered = text.lower()
    found: list[str] = []
    for ticker, info in COMPANIES.items():
        if ticker.lower() in lowered.split():
            found.append(ticker)
            continue
        for alias in [info["name"], *info["aliases"]]:
            if alias.lower() in lowered:
                found.append(ticker)
                break
    return found
