"""Authoritative static RSS feed configuration (Phase 1 runtime source).

Phase 1 rule: fetcher.py reads RSS feeds exclusively from RSS_FEEDS below.
The companies.rss_feeds database column is a mirror/preview field only
and is NOT used as a runtime source in Phase 1.

RSS feed `kind` values:
  news              — company IR press release feed
  sec_filing        — SEC Filing RSS from IR site
  market_commentary — third-party commentary RSS (e.g. Seeking Alpha)

To add a new company:
  1. Add an entry here under its ticker.
  2. Register the company via POST /api/news/companies (or seed in registry.py).
  3. No code change is needed in fetcher.py — it reads this dict at runtime.
"""

from __future__ import annotations

# Per-company RSS feed list.
# Each entry: {"kind": str, "url": str, "source_name": str}
RSS_FEEDS: dict[str, list[dict]] = {
    "FLEX": [
        {
            "kind": "news",
            "url": "https://investors.flex.com/rss/pressrelease.aspx",
            "source_name": "Flex IR",
        },
        {
            "kind": "sec_filing",
            "url": "https://investors.flex.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000866374",
            "source_name": "Flex SEC",
        },
    ],
    "JBL": [
        {
            "kind": "news",
            "url": "https://investors.jabil.com/rss/pressrelease.aspx",
            "source_name": "Jabil IR",
        },
        {
            "kind": "sec_filing",
            "url": "https://investors.jabil.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000898293",
            "source_name": "Jabil SEC",
        },
    ],
    "BHE": [
        {
            "kind": "news",
            "url": "https://ir.bench.com/rss/pressrelease.aspx",
            "source_name": "Benchmark IR",
        },
        {
            "kind": "sec_filing",
            "url": "https://ir.bench.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000863436",
            "source_name": "Benchmark SEC",
        },
        {
            "kind": "market_commentary",
            "url": "https://seekingalpha.com/symbol/BHE.xml",
            "source_name": "Seeking Alpha BHE",
        },
    ],
    "SANM": [
        {
            "kind": "news",
            "url": "https://ir.sanmina.com/rss/pressrelease.aspx",
            "source_name": "Sanmina IR",
        },
        {
            "kind": "sec_filing",
            "url": "https://ir.sanmina.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000897723",
            "source_name": "Sanmina SEC",
        },
    ],
    "CLS": [
        {
            "kind": "news",
            "url": "https://www.globenewswire.com/rssfeed/organization/vlXa3ip4O0JMbJucCiUeUg==",
            "source_name": "Celestica GlobeNewswire",
        },
        {
            "kind": "sec_filing",
            "url": "https://data.sec.gov/rss?cik=0001030894&type=3,4,5&exclude=true&count=40",
            "source_name": "Celestica SEC",
        },
    ],
    "PLXS": [
        {
            "kind": "news",
            "url": "https://www.plexus.com/feed/",
            "source_name": "Plexus News",
        },
        {
            "kind": "sec_filing",
            "url": "https://data.sec.gov/rss?cik=0000785786&count=40",
            "source_name": "Plexus SEC",
        },
    ],
}
