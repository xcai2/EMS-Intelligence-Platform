"""SQLite database initialization and connection for the news module.

This is the only file that directly interacts with news_config.db.
All other modules access the database through registry.py.

Schema is idempotent — tables are only created if they do not exist.
Tables are NEVER dropped or recreated on startup.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.core.config import DATA_DIR

DB_PATH = Path(DATA_DIR) / "news" / "news_config.db"


def get_connection() -> sqlite3.Connection:
    """Return a WAL-mode connection to news_config.db."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they do not yet exist.

    Safe to call at every application startup — never drops or recreates tables.
    """
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS companies (
                ticker          TEXT PRIMARY KEY,
                full_name       TEXT NOT NULL,
                aliases         TEXT NOT NULL DEFAULT '',
                industry        TEXT NOT NULL DEFAULT '',
                official_domain TEXT NOT NULL DEFAULT '',
                official_website TEXT NOT NULL DEFAULT '',
                rss_feeds       TEXT NOT NULL DEFAULT '',
                template_tier   TEXT NOT NULL DEFAULT 'standard',
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS company_queries (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker          TEXT NOT NULL,
                intent          TEXT NOT NULL,
                query_template  TEXT NOT NULL,
                freshness       TEXT,
                count           INTEGER NOT NULL DEFAULT 50,
                updated_at      TEXT NOT NULL,
                FOREIGN KEY (ticker) REFERENCES companies(ticker)
            );

            CREATE TABLE IF NOT EXISTS article_summary_cache (
                article_key     TEXT PRIMARY KEY,
                summary         TEXT NOT NULL,
                summary_source  TEXT NOT NULL DEFAULT 'llm_from_metadata',
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weekly_summary_cache (
                cache_key       TEXT PRIMARY KEY,
                summary         TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trend_summary_cache (
                cluster_key     TEXT PRIMARY KEY,
                trend_title     TEXT NOT NULL,
                trend_summary   TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
        """)
        # Idempotent column additions — safe to run on every startup.
        companies_cols = {row["name"] for row in conn.execute("PRAGMA table_info(companies)").fetchall()}
        if "official_website" not in companies_cols:
            conn.execute(
                "ALTER TABLE companies ADD COLUMN official_website TEXT NOT NULL DEFAULT ''"
            )

        article_cols = {row["name"] for row in conn.execute("PRAGMA table_info(article_summary_cache)").fetchall()}
        if "summary_version" not in article_cols:
            conn.execute("ALTER TABLE article_summary_cache ADD COLUMN summary_version TEXT NOT NULL DEFAULT 'v1'")
        if "summary_status" not in article_cols:
            conn.execute("ALTER TABLE article_summary_cache ADD COLUMN summary_status TEXT NOT NULL DEFAULT 'ready'")

        weekly_cols = {row["name"] for row in conn.execute("PRAGMA table_info(weekly_summary_cache)").fetchall()}
        if "summary_version" not in weekly_cols:
            conn.execute("ALTER TABLE weekly_summary_cache ADD COLUMN summary_version TEXT NOT NULL DEFAULT 'v1'")
        if "summary_status" not in weekly_cols:
            conn.execute("ALTER TABLE weekly_summary_cache ADD COLUMN summary_status TEXT NOT NULL DEFAULT 'ready'")
        if "source_item_count" not in weekly_cols:
            conn.execute("ALTER TABLE weekly_summary_cache ADD COLUMN source_item_count INTEGER NOT NULL DEFAULT 0")
        if "summary_ready_count" not in weekly_cols:
            conn.execute("ALTER TABLE weekly_summary_cache ADD COLUMN summary_ready_count INTEGER NOT NULL DEFAULT 0")
        if "fallback_count" not in weekly_cols:
            conn.execute("ALTER TABLE weekly_summary_cache ADD COLUMN fallback_count INTEGER NOT NULL DEFAULT 0")

        conn.commit()
