"""Read/write layer for financial_snapshots and fetch_log.

All SQL stays here; service.py and fetcher.py never touch the DB directly.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from backend.aichat.financial_cache.db import get_connection


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def write_snapshots(rows: list[dict]) -> int:
    """Upsert snapshot rows. Returns number of rows written."""
    if not rows:
        return 0
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO financial_snapshots
                (ticker, statement, period_type, period_end, payload, fetched_at)
            VALUES (:ticker, :statement, :period_type, :period_end, :payload, :fetched_at)
            ON CONFLICT(ticker, statement, period_type, period_end) DO UPDATE SET
                payload = excluded.payload,
                fetched_at = excluded.fetched_at
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def delete_snapshots(ticker: str) -> int:
    """Delete all snapshot rows for a ticker. Returns rows deleted.

    Used by refresh_one before re-fetching so stale rows from earlier data
    sources (e.g. yfinance period_ends that EDGAR doesn't reproduce) don't
    linger in the cache.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM financial_snapshots WHERE ticker=?",
            (ticker.upper(),),
        )
        conn.commit()
        return cur.rowcount


def log_fetch(ticker: str, status: str, error: Optional[str], rows_written: int) -> None:
    """Append a fetch_log row."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO fetch_log (ticker, fetched_at, status, error, rows_written)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ticker, datetime.utcnow().isoformat(timespec="seconds"), status, error, rows_written),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_snapshot(ticker: str, statement: str, period_type: str,
                 period_end: Optional[str] = None) -> Optional[dict]:
    """Return a single snapshot row (most recent if period_end omitted), or None."""
    with get_connection() as conn:
        if period_end:
            row = conn.execute(
                """SELECT * FROM financial_snapshots
                   WHERE ticker=? AND statement=? AND period_type=? AND period_end=?""",
                (ticker.upper(), statement, period_type, period_end),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT * FROM financial_snapshots
                   WHERE ticker=? AND statement=? AND period_type=?
                   ORDER BY period_end DESC LIMIT 1""",
                (ticker.upper(), statement, period_type),
            ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["payload"] = json.loads(out["payload"])
    return out


def list_snapshots(ticker: str, statement: str, period_type: str,
                   limit: int = 8) -> list[dict]:
    """Return up to `limit` most recent snapshots, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM financial_snapshots
               WHERE ticker=? AND statement=? AND period_type=?
               ORDER BY period_end DESC LIMIT ?""",
            (ticker.upper(), statement, period_type, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d["payload"])
        out.append(d)
    return out


def cache_summary() -> dict:
    """High-level overview: per-ticker row counts and last fetched_at."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT ticker,
                      COUNT(*)          AS rows,
                      MAX(fetched_at)   AS last_fetched
               FROM financial_snapshots
               GROUP BY ticker
               ORDER BY ticker"""
        ).fetchall()
    return {r["ticker"]: {"rows": r["rows"], "last_fetched": r["last_fetched"]} for r in rows}
