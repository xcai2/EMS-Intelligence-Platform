"""
SQLite persistence for analyst view features that need history:
  - weekly_themes   : Claude-generated weekly strategic theme digests
  - key_quotes      : LLM-extracted earnings-call Q&A with strategic framing
  - sentiment_snaps : quarterly consensus snapshots for the timeline chart
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.core.config import DATA_DIR

DB_PATH = Path(DATA_DIR) / "analyst_intel.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS weekly_themes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start    TEXT NOT NULL,
                themes_json   TEXT NOT NULL,
                generated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS key_quotes (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                company              TEXT NOT NULL,
                ticker               TEXT NOT NULL,
                analyst_name         TEXT,
                question             TEXT NOT NULL,
                management_response  TEXT NOT NULL,
                theme                TEXT NOT NULL,
                strategic_implication TEXT NOT NULL,
                earnings_date        TEXT,
                source_url           TEXT,
                created_at           TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS confirmed_earnings (
                ticker        TEXT NOT NULL,
                quarter       TEXT NOT NULL,
                fiscal_year   INTEGER NOT NULL,
                release_date  TEXT NOT NULL,
                call_date     TEXT,
                call_time     TEXT,
                source_url    TEXT,
                fetched_at    TEXT NOT NULL,
                PRIMARY KEY (ticker, quarter, fiscal_year)
            );

            CREATE TABLE IF NOT EXISTS sentiment_snaps (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker           TEXT NOT NULL,
                quarter          TEXT NOT NULL,
                consensus_score  REAL,
                avg_pt           REAL,
                analyst_count    INTEGER,
                recorded_at      TEXT NOT NULL,
                UNIQUE(ticker, quarter)
            );
        """)


# ---------------------------------------------------------------------------
# Weekly themes helpers
# ---------------------------------------------------------------------------

def save_weekly_themes(week_start: str, themes_json: str, generated_at: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO weekly_themes (week_start, themes_json, generated_at) VALUES (?,?,?)",
            (week_start, themes_json, generated_at),
        )
        return cur.lastrowid or 0


def get_latest_weekly_themes() -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM weekly_themes ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()


def get_all_weekly_themes(limit: int = 12) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM weekly_themes ORDER BY generated_at DESC LIMIT ?", (limit,)
        ).fetchall()


# ---------------------------------------------------------------------------
# Key quotes helpers
# ---------------------------------------------------------------------------

def save_key_quotes(quotes: list[dict]) -> None:
    with _connect() as conn:
        conn.executemany(
            """INSERT INTO key_quotes
               (company, ticker, analyst_name, question, management_response,
                theme, strategic_implication, earnings_date, source_url, created_at)
               VALUES (:company,:ticker,:analyst_name,:question,:management_response,
                       :theme,:strategic_implication,:earnings_date,:source_url,:created_at)""",
            quotes,
        )


def get_key_quotes(
    company: str | None = None,
    theme: str | None = None,
    days: int = 90,
    limit: int = 50,
) -> list[sqlite3.Row]:
    clauses: list[str] = [
        "created_at >= datetime('now', ? || ' days')"
    ]
    params: list = [f"-{days}"]
    if company:
        clauses.append("company = ?")
        params.append(company)
    if theme:
        clauses.append("theme = ?")
        params.append(theme)
    where = " AND ".join(clauses)
    params.append(limit)
    with _connect() as conn:
        return conn.execute(
            f"SELECT * FROM key_quotes WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()


# ---------------------------------------------------------------------------
# Confirmed earnings helpers
# ---------------------------------------------------------------------------

def upsert_confirmed_earning(
    ticker: str, quarter: str, fiscal_year: int,
    release_date: str, call_date: str | None, call_time: str | None,
    source_url: str | None, fetched_at: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO confirmed_earnings
               (ticker, quarter, fiscal_year, release_date, call_date, call_time, source_url, fetched_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(ticker, quarter, fiscal_year) DO UPDATE SET
                 release_date=excluded.release_date,
                 call_date=excluded.call_date,
                 call_time=excluded.call_time,
                 source_url=excluded.source_url,
                 fetched_at=excluded.fetched_at""",
            (ticker, quarter, fiscal_year, release_date, call_date, call_time, source_url, fetched_at),
        )


def get_all_confirmed_earnings() -> dict[tuple[str, str, int], dict]:
    """Return {(ticker, quarter, fy): {release_date, call_date, ...}} for all rows."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM confirmed_earnings").fetchall()
    result = {}
    for r in rows:
        key = (r["ticker"], r["quarter"], r["fiscal_year"])
        result[key] = {
            "release_date": r["release_date"],
            "call_date": r["call_date"],
            "call_time": r["call_time"],
            "source_url": r["source_url"],
            "fetched_at": r["fetched_at"],
        }
    return result


# ---------------------------------------------------------------------------
# Sentiment snapshot helpers
# ---------------------------------------------------------------------------

def upsert_sentiment_snap(ticker: str, quarter: str, score: float,
                           avg_pt: float, count: int, recorded_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO sentiment_snaps (ticker,quarter,consensus_score,avg_pt,analyst_count,recorded_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(ticker,quarter) DO UPDATE SET
                 consensus_score=excluded.consensus_score,
                 avg_pt=excluded.avg_pt,
                 analyst_count=excluded.analyst_count,
                 recorded_at=excluded.recorded_at""",
            (ticker, quarter, score, avg_pt, count, recorded_at),
        )


def get_sentiment_timeline(ticker: str, quarters: int = 8) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            """SELECT * FROM sentiment_snaps WHERE ticker=?
               ORDER BY quarter DESC LIMIT ?""",
            (ticker, quarters),
        ).fetchall()
