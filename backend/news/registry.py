"""Company registry: the only module that reads/writes the news configuration database.

Other modules obtain company data by calling functions here —
they never import db.get_connection() directly.

Phase 1 fixed intents per company: official_name, industry_news, stock_news, supporting_query.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from backend.news.db import get_connection
from backend.news.models import Company, QueryTemplate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_BUILTIN_TICKER_ORDER = {
    "FLEX": 0,
    "JBL": 1,
    "CLS": 2,
    "BHE": 3,
    "SANM": 4,
    "PLXS": 5,
}


def _row_to_company(row) -> Company:
    return Company(
        ticker=row["ticker"],
        full_name=row["full_name"],
        aliases=row["aliases"] or "",
        industry=row["industry"] or "",
        official_domain=row["official_domain"] or "",
        official_website=row["official_website"] or "",
        rss_feeds=row["rss_feeds"] or "",
        template_tier=row["template_tier"] or "standard",
        created_at=row["created_at"] or "",
    )


def _row_to_query_template(row) -> QueryTemplate:
    return QueryTemplate(
        id=row["id"],
        ticker=row["ticker"],
        intent=row["intent"],
        query_template=row["query_template"],
        freshness=row["freshness"],
        count=int(row["count"] or 40),
        updated_at=row["updated_at"] or "",
    )


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def list_companies() -> list[Company]:
    """Return all registered companies in UI order.

    Rules:
    - built-in six companies keep a fixed order
    - user-added companies append after built-ins
    - appended companies sort by created_at, then ticker
    """
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM companies").fetchall()
    companies = [_row_to_company(r) for r in rows]
    companies.sort(
        key=lambda c: (
            0 if c.ticker in _BUILTIN_TICKER_ORDER else 1,
            _BUILTIN_TICKER_ORDER.get(c.ticker, 999),
            c.created_at or "",
            c.ticker,
        )
    )
    return companies


def get_company(ticker: str) -> Optional[Company]:
    """Return a single company by ticker, or None if not registered."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE ticker = ?", (ticker.upper(),)
        ).fetchone()
    return _row_to_company(row) if row else None


def get_company_queries(ticker: str) -> list[QueryTemplate]:
    """Return all query templates for a company, ordered by intent."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM company_queries WHERE ticker = ? ORDER BY intent",
            (ticker.upper(),),
        ).fetchall()
    return [_row_to_query_template(r) for r in rows]


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def save_company(company: Company, queries: list[QueryTemplate]) -> None:
    """Insert a new company and its query templates (atomic).

    Raises ValueError if the ticker already exists — use update_company_queries
    to modify templates for an existing company.
    """
    now = _now_iso()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT ticker FROM companies WHERE ticker = ?",
            (company.ticker.upper(),),
        ).fetchone()
        if existing:
            raise ValueError(
                f"Company {company.ticker.upper()} already exists. "
                "Use PUT /api/news/companies/{ticker}/queries to update templates."
            )
        conn.execute(
            """
            INSERT INTO companies
                (ticker, full_name, aliases, industry, official_domain, official_website, rss_feeds, template_tier, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company.ticker.upper(),
                company.full_name,
                company.aliases,
                company.industry,
                company.official_domain,
                company.official_website,
                company.rss_feeds,
                company.template_tier,
                company.created_at or now,
            ),
        )
        for q in queries:
            conn.execute(
                """
                INSERT INTO company_queries
                    (ticker, intent, query_template, freshness, count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    company.ticker.upper(),
                    q.intent,
                    q.query_template,
                    q.freshness,
                    q.count or 50,
                    now,
                ),
            )
        conn.commit()


def update_company_queries(ticker: str, queries: list[QueryTemplate]) -> None:
    """Replace all query templates for an existing company (Phase 1: all 4 at once)."""
    now = _now_iso()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM company_queries WHERE ticker = ?", (ticker.upper(),)
        )
        for q in queries:
            conn.execute(
                """
                INSERT INTO company_queries
                    (ticker, intent, query_template, freshness, count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker.upper(),
                    q.intent,
                    q.query_template,
                    q.freshness,
                    q.count or 50,
                    now,
                ),
            )
        conn.commit()


def delete_company(ticker: str) -> bool:
    """Remove a company and all its query templates. Returns True if found."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM company_queries WHERE ticker = ?", (ticker.upper(),)
        )
        result = conn.execute(
            "DELETE FROM companies WHERE ticker = ?", (ticker.upper(),)
        )
        conn.commit()
        return (result.rowcount or 0) > 0


def is_builtin_company(ticker: str) -> bool:
    return ticker.upper() in _BUILTIN_TICKER_ORDER


# ---------------------------------------------------------------------------
# Initial data seeding (Phase 1 — 4 fixed intents per company)
# ---------------------------------------------------------------------------

# Company metadata
_COMPANY_META: dict[str, dict] = {
    "FLEX": {
        "full_name": "Flex Ltd",
        "aliases": "Flextronics,FLEX",
        "industry": "EMS",
        "official_domain": "flex.com",
        "official_website": "https://flex.com/newsroom",
        "template_tier": "enhanced",
    },
    "JBL": {
        "full_name": "Jabil Inc",
        "aliases": "Jabil Inc,NYSE:JBL",
        "industry": "EMS",
        "official_domain": "jabil.com",
        "official_website": "https://www.jabil.com/",
        "template_tier": "standard",
    },
    "CLS": {
        "full_name": "Celestica Inc",
        "aliases": "Celestica Inc,NYSE:CLS,TSX:CLS",
        "industry": "EMS",
        "official_domain": "celestica.com",
        "official_website": "https://www.celestica.com/",
        "template_tier": "standard",
    },
    "BHE": {
        "full_name": "Benchmark Electronics",
        "aliases": "Benchmark Electronics Inc,NYSE:BHE",
        "industry": "EMS",
        "official_domain": "bench.com",
        "official_website": "https://www.bench.com/",
        "template_tier": "standard",
    },
    "SANM": {
        "full_name": "Sanmina Corporation",
        "aliases": "Sanmina Corporation,NASDAQ:SANM",
        "industry": "EMS",
        "official_domain": "sanmina.com",
        "official_website": "https://www.sanmina.com/",
        "template_tier": "standard",
    },
    "PLXS": {
        "full_name": "Plexus Corp",
        "aliases": "Plexus Corp,NASDAQ:PLXS",
        "industry": "EMS",
        "official_domain": "plexus.com",
        "official_website": "https://www.plexus.com/news/",
        "template_tier": "standard",
    },
}

# Phase 1 query templates: (intent, query_template, freshness, count)
_COMPANY_TEMPLATES: dict[str, list[tuple]] = {
    "FLEX": [
        ("official_name",    '"Flex Ltd." news',                     None, 40),
        ("industry_news",    "Flex manufacturing supply chain news", None, 40),
        ("stock_news",       "FLEX earnings results quarterly",      None, 40),
        ("supporting_query", "Flextronics news",                    None, 40),
    ],
    "JBL": [
        ("official_name",    '"Jabil Inc." news',                    None, 40),
        ("industry_news",    "Jabil manufacturing electronics news", None, 40),
        ("stock_news",       "JBL earnings results quarterly",       None, 40),
        ("supporting_query", "Jabil supply chain EMS news",         None, 40),
    ],
    "CLS": [
        ("official_name",    '"Celestica Inc." news',                     None, 40),
        ("industry_news",    "Celestica manufacturing EMS news",          None, 40),
        ("stock_news",       "CLS earnings results quarterly",            None, 40),
        ("supporting_query", "Celestica data center infrastructure news", None, 40),
    ],
    "BHE": [
        ("official_name",    '"Benchmark Electronics" news',              None, 40),
        ("industry_news",    "Benchmark Electronics manufacturing news",  None, 40),
        ("stock_news",       "BHE earnings results quarterly",            None, 40),
        ("supporting_query", "Benchmark Electronics supply chain news",  None, 40),
    ],
    "SANM": [
        ("official_name",    '"Sanmina Corporation" news',               None, 40),
        ("industry_news",    "Sanmina manufacturing electronics news",   None, 40),
        ("stock_news",       "SANM earnings results quarterly",          None, 40),
        ("supporting_query", "Sanmina EMS supply chain news",           None, 40),
    ],
    "PLXS": [
        ("official_name",    '"Plexus Corp." news',                  None, 40),
        ("industry_news",    "Plexus manufacturing engineering news", None, 40),
        ("stock_news",       "PLXS earnings results quarterly",      None, 40),
        ("supporting_query", "Plexus EMS supply chain news",        None, 40),
    ],
}


def upgrade_templates_count_to_50() -> int:
    """One-time idempotent migration: update existing company_queries count from 40 to 50.

    Phase 3 requirement (§5.10): all formal query templates should use count=50
    (Brave News API maximum).  Safe to call at every startup — only touches rows
    that still have the old default of 40.
    """
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE company_queries SET count = 50 WHERE count = 40"
        )
        conn.commit()
        updated = result.rowcount or 0
    if updated:
        logger.info("Upgraded %d company_queries rows: count 40 → 50", updated)
    return updated


def seed_initial_companies() -> None:
    """Populate the database with the six initial EMS companies.

    Idempotent: skips tickers that already exist (INSERT OR IGNORE semantics).
    This runs at startup; it must not raise if data already exists.
    """
    now = _now_iso()
    for ticker, meta in _COMPANY_META.items():
        if get_company(ticker) is not None:
            continue  # already seeded — skip entirely

        company = Company(
            ticker=ticker,
            full_name=meta["full_name"],
            aliases=meta["aliases"],
            industry=meta["industry"],
            official_domain=meta["official_domain"],
            official_website=meta.get("official_website", ""),
            template_tier=meta["template_tier"],
            rss_feeds="",  # sources.py is the Phase 1 runtime source; this field is a mirror only
            created_at=now,
        )
        queries = [
            QueryTemplate(ticker=ticker, intent=intent, query_template=tmpl, freshness=freshness, count=count)
            for intent, tmpl, freshness, count in _COMPANY_TEMPLATES.get(ticker, [])
        ]

        try:
            save_company(company, queries)
            logger.info("Seeded company: %s (%s)", ticker, meta["full_name"])
        except Exception as exc:
            logger.warning("Failed to seed company %s: %s", ticker, exc)


def backfill_builtin_company_websites() -> int:
    """Idempotently backfill the fixed official_website for the six built-in companies.

    This preserves the prefilled website behavior for the original six companies
    even if older DB rows were created before the official_website column existed.
    User-added companies are not touched.
    """
    updated = 0
    with get_connection() as conn:
        for ticker, meta in _COMPANY_META.items():
            website = meta.get("official_website", "")
            if not website:
                continue
            result = conn.execute(
                """
                UPDATE companies
                SET official_website = ?
                WHERE ticker = ?
                  AND (official_website IS NULL OR official_website = '')
                """,
                (website, ticker),
            )
            updated += result.rowcount or 0
        conn.commit()
    if updated:
        logger.info("Backfilled official_website for %d built-in companies", updated)
    return updated
