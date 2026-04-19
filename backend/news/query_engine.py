"""Query engine: reads templates from the registry and builds Brave query params.

This layer only constructs query parameter packages — it makes no network requests.
The actual requests are issued by fetcher.py.

Phase 1 rules:
- No year is appended to queries.
- Global exclusion suffixes for sec.gov are appended to every Brave query.
- RSS feed configuration is read from sources.py (not the database).
"""

from __future__ import annotations

import logging

from backend.news.registry import get_company_queries
from backend.news.sources import RSS_FEEDS

logger = logging.getLogger(__name__)

# Global exclusion suffixes appended to every Brave query (Phase 1 only item).
# Brave can still occasionally leak SEC pages despite a single -site:sec.gov
# clause, so we apply both host forms as a low-risk defensive exclusion.
_GLOBAL_EXCLUSIONS: tuple[str, ...] = (
    "-site:sec.gov",
    "-site:www.sec.gov",
)


def build_query_params(ticker: str) -> list[dict]:
    """Return a list of ready-to-execute Brave query parameter dicts for a company.

    Each dict contains:
        q         — query string with global exclusion suffix appended
        count     — number of results to request from Brave
        freshness — Brave freshness param (None in Phase 1)
        intent    — the template intent label

    Returns an empty list if no templates are found for the ticker.
    """
    templates = get_company_queries(ticker.upper())
    if not templates:
        logger.warning("No query templates found for ticker %s", ticker.upper())
        return []

    params: list[dict] = []
    for t in templates:
        # Append global exclusion suffixes; do NOT append year (Phase 1 rule)
        exclusion_suffix = " ".join(_GLOBAL_EXCLUSIONS)
        q = f"{t.query_template} {exclusion_suffix}"
        params.append(
            {
                "q": q,
                "count": t.count or 40,
                "freshness": t.freshness,  # None in Phase 1
                "intent": t.intent,
            }
        )
    return params


def get_rss_feeds(ticker: str) -> list[dict]:
    """Return the RSS feed list for a company from the static sources.py config.

    Phase 1 rule: only sources.py is used; the database rss_feeds field is ignored.

    Each entry: {"kind": str, "url": str, "source_name": str}
    Returns an empty list if no feeds are configured.
    """
    return RSS_FEEDS.get(ticker.upper(), [])
