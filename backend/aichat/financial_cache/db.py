"""SQLite database for the AI Chat financial cache.

Independent of news_config.db. Schema is idempotent — tables are
only created if missing, never dropped.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.core.config import DATA_DIR

DB_PATH = Path(DATA_DIR) / "aichat_financials.db"


def get_connection() -> sqlite3.Connection:
    """Return a WAL-mode connection to aichat_financials.db."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they do not yet exist. Safe on every startup."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS financial_snapshots (
                ticker        TEXT NOT NULL,
                statement     TEXT NOT NULL,   -- 'income' | 'balance' | 'cashflow' | 'info'
                period_type   TEXT NOT NULL,   -- 'quarterly' | 'annual'
                period_end    TEXT NOT NULL,   -- 'YYYY-MM-DD'
                payload       TEXT NOT NULL,   -- JSON of yfinance fields
                fetched_at    TEXT NOT NULL,
                PRIMARY KEY (ticker, statement, period_type, period_end)
            );

            CREATE INDEX IF NOT EXISTS idx_fs_ticker_period
                ON financial_snapshots(ticker, period_type, period_end DESC);

            CREATE TABLE IF NOT EXISTS fetch_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker       TEXT NOT NULL,
                fetched_at   TEXT NOT NULL,
                status       TEXT NOT NULL,    -- 'ok' | 'partial' | 'error'
                error        TEXT,
                rows_written INTEGER NOT NULL DEFAULT 0
            );
        """)
        conn.commit()
