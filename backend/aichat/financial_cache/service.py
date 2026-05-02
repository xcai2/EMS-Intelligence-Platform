"""Public facade for the AI Chat financial cache.

The pipeline and any internal admin endpoint should import only from this
module — never touch fetcher / repository directly.
"""

from __future__ import annotations

import re
import time
from typing import Optional

from backend.aichat.financial_cache import repository
from backend.aichat.financial_cache.companies import (
    COMPANIES,
    all_tickers,
    fiscal_label,
    get_company,
)
from backend.aichat.financial_cache.db import init_db
from backend.aichat.financial_cache.fetcher import fetch_ticker
from backend.aichat.financial_cache.intent import detect_financial_intent

# Seconds to sleep between yfinance calls in refresh_all to be polite.
_REFRESH_DELAY_SECONDS = 1.0


# ---------------------------------------------------------------------------
# Refresh (manual trigger only — per design §7)
# ---------------------------------------------------------------------------

def refresh_one(ticker: str) -> dict:
    """Fetch a single ticker and overwrite its snapshots in cache.

    Pre-deletes existing rows for the ticker so period_ends from a previous
    data source (e.g. stale yfinance rows from before EDGAR was wired in)
    don't linger alongside the freshly-fetched ones.
    """
    ticker = ticker.upper()
    if ticker not in COMPANIES:
        return {"ticker": ticker, "status": "error",
                "error": f"unknown ticker (not in COMPANIES)", "rows_written": 0}

    init_db()
    snapshots, error = fetch_ticker(ticker)
    if snapshots:
        # Only purge if the new fetch produced data — otherwise keep old
        # data so we don't end up with an empty cache on a transient failure.
        repository.delete_snapshots(ticker)
    rows_written = repository.write_snapshots(snapshots)
    status = "ok" if rows_written and not error else ("partial" if rows_written else "error")
    repository.log_fetch(ticker, status, error, rows_written)
    return {"ticker": ticker, "status": status, "rows_written": rows_written, "error": error}


def refresh_all() -> dict:
    """Fetch every tracked ticker. Serial with a small delay to avoid throttling."""
    init_db()
    results = []
    for ticker in all_tickers():
        results.append(refresh_one(ticker))
        time.sleep(_REFRESH_DELAY_SECONDS)
    summary = {
        "total":     len(results),
        "ok":        sum(1 for r in results if r["status"] == "ok"),
        "partial":   sum(1 for r in results if r["status"] == "partial"),
        "error":     sum(1 for r in results if r["status"] == "error"),
        "results":   results,
    }
    return summary


# ---------------------------------------------------------------------------
# Query (read-only — pipeline calls this)
# ---------------------------------------------------------------------------

def query_snapshot(ticker: str, statement: str, period_type: str = "quarterly",
                   period_end: Optional[str] = None) -> Optional[dict]:
    """Return a single snapshot or None if not in cache."""
    return repository.get_snapshot(ticker.upper(), statement, period_type, period_end)


def query_metric(ticker: str, metric: str, period_type: str = "quarterly",
                 limit: int = 8) -> list[dict]:
    """Return a time series of one metric across the most recent snapshots.

    Searches all three financial statements (income/balance/cashflow) and
    returns the metric where it's found. Each result is
    `{period_end, value, statement, fetched_at}`.
    """
    ticker = ticker.upper()
    series: list[dict] = []
    for statement in ("income", "balance", "cashflow"):
        snaps = repository.list_snapshots(ticker, statement, period_type, limit=limit)
        for snap in snaps:
            if metric in snap["payload"]:
                series.append({
                    "period_end": snap["period_end"],
                    "value":      snap["payload"][metric],
                    "statement":  statement,
                    "fetched_at": snap["fetched_at"],
                })
        if series:
            break  # don't mix statements; first hit wins
    series.sort(key=lambda r: r["period_end"], reverse=True)
    return series[:limit]


def cache_summary() -> dict:
    """Per-ticker row counts + last fetch time. For the admin endpoint."""
    return {
        "tickers_tracked": all_tickers(),
        "by_ticker": repository.cache_summary(),
    }


# ---------------------------------------------------------------------------
# High-level entry point — both /chat and /chat/stream short-circuit through here
# ---------------------------------------------------------------------------

def format_series_context(intent: dict, series: list[dict]) -> str:
    """Render a financial cache hit as Markdown context for the LLM.

    Each row carries an FY/Q label so the LLM can match queries phrased in
    fiscal terms (e.g. JBL FY2025 Q2 = period ending 2025-02-28).
    """
    ticker = intent["ticker"]
    label = intent["metric_label"]
    if not series:
        return (
            f"## Financial data ({ticker} · {label})\n"
            f"Source: yfinance cache (no data in cache)."
        )

    is_snapshot = intent["statement"] == "info"
    period_type = intent.get("period_type", "quarterly")
    lines = [
        f"## Financial data ({ticker} · {label})",
        "Source: yfinance cache. Each row below is an authoritative fact.",
        "",
    ]
    for row in series:
        v = row.get("value")
        v_fmt = f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
        period_end = row.get("period_end", "")
        fy_lbl = fiscal_label(ticker, period_end) if not is_snapshot else None
        if fy_lbl and period_type == "annual":
            fy_lbl = fy_lbl.split(" ")[0]
        if is_snapshot:
            lines.append(f"- {ticker} {label} as of {period_end}: {v_fmt} (USD).")
        elif fy_lbl:
            lines.append(
                f"- {ticker} {label} for {fy_lbl} (period ending {period_end}): "
                f"{v_fmt} (USD)."
            )
        else:
            lines.append(
                f"- {ticker} {label} for the period ending {period_end}: "
                f"{v_fmt} (USD)."
            )

    if is_snapshot:
        lines += ["", "| As Of | Value (USD) |", "|---|---|"]
        for row in series:
            v = row.get("value")
            v_fmt = f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
            lines.append(f"| {row['period_end']} | {v_fmt} |")
    else:
        lines += ["", "| Fiscal Period | Period End | Value (USD) |", "|---|---|---|"]
        for row in series:
            v = row.get("value")
            v_fmt = f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
            period_end = row.get("period_end", "")
            fy_lbl = fiscal_label(ticker, period_end) or "—"
            if period_type == "annual" and fy_lbl != "—":
                fy_lbl = fy_lbl.split(" ")[0]
            lines.append(f"| {fy_lbl} | {period_end} | {v_fmt} |")
    return "\n".join(lines)


_RE_FY_TOKEN = re.compile(r"\bfy\s*(\d{4})\b", re.IGNORECASE)
_RE_Q_TOKEN  = re.compile(r"\bq([1-4])\b",     re.IGNORECASE)

# Table-intent keyword patterns — same as routes.py is_table_query, kept local
# so we don't import routes from service (which would be a circular dep).
_TABLE_PATTERNS = re.compile(
    # Match any standalone mention of "table" (covers "provide table",
    # "provide a table", "give me a table", "in a table", etc.) plus a
    # few keyword phrases that imply tabular output without using the word.
    r"\btable\b|\b(not\s+paragraph|year.over.year\s+change|tabular\s+form)\b",
    re.IGNORECASE | re.DOTALL,
)


def _is_table_query(query: str) -> bool:
    """Mirror of routes.is_table_query — kept here to avoid a circular import."""
    return bool(_TABLE_PATTERNS.search(query))


def _strip_frontend_template(query: str) -> str:
    """Remove the multi-section response template the chat frontend prepends.

    The frontend's `STRUCTURED_RESPONSE_INSTRUCTION` ("Structure every response
    with exactly three sections… IMPLICATION FOR FLEX …") leaks the literal
    word "FLEX" into every query, which would otherwise cause `resolve_ticker`
    to mis-identify the target company. We drop the template here so intent
    detection sees only the user's actual question.
    """
    if not query:
        return query
    stripped = query.lstrip()
    if not stripped.lower().startswith("structure every response"):
        return query
    parts = stripped.split("\n\n", 1)
    if len(parts) == 2:
        return parts[1].strip()
    return query

# yfinance reports these as negative cash outflows; conventionally shown as
# positive magnitudes in tables, matching how analysts cite them in reports.
_FLIP_SIGN_FIELDS = {
    "Capital Expenditure",
    "Repurchase Of Capital Stock",
    "Repayment Of Debt",
}


def _extract_fiscal_filter(query: str) -> tuple[set[str], set[str]]:
    """Find FY year / quarter references in the query.

    Returns (specific_periods, year_only):
      - `specific_periods`: {"FY2025 Q2", "FY2025 Q3"} when user named both
        a year and at least one quarter. Reuses the rich
        `_extract_explicit_periods` utility from rag.retriever, which
        understands ranges ("FY2025 Q1 to Q3"), lists ("Q1, Q2, Q3"),
        cross-year ("FY24 Q3 and FY25 Q1"), and short-form ("FY24 Q3").
      - `year_only`: {"FY2025"} when user named the year but no quarter
        (typical for annual queries).
    Empty sets mean "no specific period named — return everything".
    """
    # Defer the import: rag.retriever pulls in heavy embedding deps that we
    # don't want to load at module import time.
    try:
        from backend.rag.retriever import _extract_explicit_periods
        explicit = _extract_explicit_periods(query)
    except Exception:
        explicit = []

    specific: set[str] = set()
    for year, q in explicit:
        if year and q:
            specific.add(f"FY{year} {q}")
    if specific:
        return specific, set()

    # Fall through to FY-only detection (annual queries with no quarter).
    years = set(_RE_FY_TOKEN.findall(query))
    if not years:
        return set(), set()
    quarters = set(_RE_Q_TOKEN.findall(query))
    if quarters:
        # Quarters are mentioned but `_extract_explicit_periods` couldn't
        # bind them to a year — fall back to a Cartesian product so we
        # don't silently lose the user's intent.
        return {f"FY{y} Q{q}" for y in years for q in quarters}, set()
    return set(), {f"FY{y}" for y in years}


def _format_value(v, flip_sign: bool = False) -> str:
    """Render a numeric value compactly with M / B suffix."""
    if v is None:
        return "—"
    if not isinstance(v, (int, float)):
        return str(v)
    if flip_sign:
        v = -v
    abs_v = abs(v)
    if abs_v >= 1e9:
        return f"{v/1e9:,.2f}B"
    if abs_v >= 1e6:
        return f"{v/1e6:,.0f}M"
    if abs_v >= 1e3:
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def _build_table_payload(intent: dict, series: list[dict]) -> dict:
    """Structured table payload matching `generate_table_response` shape.

    Frontend renders this with its dedicated table component (see
    `page.tsx` Message.table_payload). Same value formatting as the markdown
    response so users see consistent numbers in either UI surface.
    """
    ticker      = intent["ticker"]
    label       = intent["metric_label"]
    field       = intent["metric_field"]
    period_type = intent.get("period_type", "quarterly")
    is_snapshot = intent["statement"] == "info"
    flip_sign   = field in _FLIP_SIGN_FIELDS

    if is_snapshot:
        title = f"{ticker} {label}"
        columns = ["As Of", label]
        rows = [
            [series[0]["period_end"], _format_value(series[0]["value"], flip_sign)]
        ]
    elif period_type == "annual":
        title = f"{ticker} {label} (Annual)"
        columns = ["Fiscal Year", "Period End", label]
        rows = []
        for r in series:
            fy_lbl = fiscal_label(ticker, r["period_end"]) or "—"
            fy_year = fy_lbl.split(" ")[0] if fy_lbl != "—" else "—"
            rows.append([fy_year, r["period_end"], _format_value(r["value"], flip_sign)])
    else:
        title = f"{ticker} {label} (Quarterly)"
        columns = ["Fiscal Period", "Period End", label]
        rows = []
        for r in series:
            fy_lbl = fiscal_label(ticker, r["period_end"]) or "—"
            rows.append([fy_lbl, r["period_end"], _format_value(r["value"], flip_sign)])

    return {"title": title, "columns": columns, "rows": rows}


def _build_table_response(intent: dict, series: list[dict]) -> str:
    """Markdown table layout — used only when the user explicitly asked for a
    table ("give me a table", "in a table", etc.). Sits next to the
    structured `table_payload` for the dedicated table component.
    """
    ticker      = intent["ticker"]
    label       = intent["metric_label"]
    field       = intent["metric_field"]
    period_type = intent.get("period_type", "quarterly")
    is_snapshot = intent["statement"] == "info"
    flip_sign   = field in _FLIP_SIGN_FIELDS

    sign_note = " (shown as positive cash outflow magnitude)" if flip_sign else ""
    lines = [f"**{ticker} — {label}**{sign_note}", ""]

    if is_snapshot:
        row = series[0]
        lines += [
            "| As Of | " + label + " |",
            "|---|---|",
            f"| {row['period_end']} | {_format_value(row['value'], flip_sign)} |",
        ]
    elif period_type == "annual":
        lines += [
            f"| Fiscal Year | Period End | {label} |",
            "|---|---|---|",
        ]
        for row in series:
            fy_lbl = fiscal_label(ticker, row["period_end"]) or "—"
            fy_year = fy_lbl.split(" ")[0] if fy_lbl != "—" else "—"
            lines.append(
                f"| {fy_year} | {row['period_end']} | "
                f"{_format_value(row['value'], flip_sign)} |"
            )
    else:
        lines += [
            f"| Fiscal Period | Period End | {label} |",
            "|---|---|---|",
        ]
        for row in series:
            fy_lbl = fiscal_label(ticker, row["period_end"]) or "—"
            lines.append(
                f"| {fy_lbl} | {row['period_end']} | "
                f"{_format_value(row['value'], flip_sign)} |"
            )

    fetched = series[0]["fetched_at"][:10] if series and series[0].get("fetched_at") else "—"
    lines += ["", f"_Source: yfinance cache (fetched {fetched})._"]
    return "\n".join(lines)


def _build_default_response(intent: dict, series: list[dict]) -> str:
    """Default non-table layout — sentence for one value, bullet list for many.

    Used when the user did not ask for a table, matching the original chat
    flow's expectation of natural-language answers rather than tabular ones.
    """
    ticker      = intent["ticker"]
    label       = intent["metric_label"]
    field       = intent["metric_field"]
    period_type = intent.get("period_type", "quarterly")
    is_snapshot = intent["statement"] == "info"
    flip_sign   = field in _FLIP_SIGN_FIELDS

    def _label_for(row: dict) -> str:
        fy_lbl = fiscal_label(ticker, row["period_end"]) or row["period_end"]
        if period_type == "annual" and fy_lbl != "—" and " Q" in fy_lbl:
            fy_lbl = fy_lbl.split(" ")[0]
        return fy_lbl

    sign_note = " (cash outflow, shown as positive magnitude)" if flip_sign else ""
    lines = [f"**{ticker} — {label}**{sign_note}", ""]

    if is_snapshot:
        row = series[0]
        lines.append(
            f"As of {row['period_end']}: "
            f"{_format_value(row['value'], flip_sign)}"
        )
    elif len(series) == 1:
        row = series[0]
        lines.append(
            f"{_label_for(row)} (period ending {row['period_end']}): "
            f"{_format_value(row['value'], flip_sign)}"
        )
    else:
        for row in series:
            lines.append(
                f"- {_label_for(row)} (period ending {row['period_end']}): "
                f"{_format_value(row['value'], flip_sign)}"
            )

    fetched = series[0]["fetched_at"][:10] if series and series[0].get("fetched_at") else "—"
    lines += ["", f"_Source: yfinance cache (fetched {fetched})._"]
    return "\n".join(lines)


def _build_named_period_miss_result(
    intent: dict,
    cleaned_query: str,
    wanted_labels: list[str],
    available_series: list[dict],
    original_query: str,
) -> dict:
    """When the user explicitly named FY/Q periods and none are in cache,
    return a clear message + the periods that ARE available, instead of
    silently falling through to RAG (which produces misleading historical
    framing for these queries).
    """
    ticker = intent["ticker"]
    label  = intent["metric_label"]
    field  = intent["metric_field"]
    flip   = field in _FLIP_SIGN_FIELDS

    if available_series:
        first = fiscal_label(ticker, available_series[-1]["period_end"]) or available_series[-1]["period_end"]
        last  = fiscal_label(ticker, available_series[0]["period_end"]) or available_series[0]["period_end"]
        coverage_note = f"Available in cache for {ticker}: **{first} → {last}**."
    else:
        coverage_note = "No data for this metric is in the cache."

    wanted_str = ", ".join(wanted_labels)
    sign_note = " (cash outflow, shown as positive magnitude)" if flip else ""

    lines = [
        f"**{ticker} — {label}**{sign_note}",
        "",
        f"Requested period(s) **{wanted_str}** are not available in the yfinance cache "
        f"(yfinance only keeps roughly the most recent 5–7 quarters of complete data; "
        f"older quarters age out, sometimes leaving rows with missing values).",
        "",
        coverage_note,
    ]
    if available_series:
        lines.append("")
        lines.append("Most recent values currently in cache:")
        for row in available_series[:6]:
            fy_lbl = fiscal_label(ticker, row["period_end"]) or row["period_end"]
            lines.append(
                f"- {fy_lbl} (period ending {row['period_end']}): "
                f"{_format_value(row['value'], flip)}"
            )

    fetched = (
        available_series[0]["fetched_at"][:10]
        if available_series and available_series[0].get("fetched_at") else "—"
    )
    lines += ["", f"_Source: yfinance cache (fetched {fetched})._"]
    response = "\n".join(lines)

    return {
        "response": response,
        "sources": [{
            "company":     ticker,
            "source":      "yfinance",
            "filing_type": "financial_cache",
            "fiscal_year": None,
            "similarity":  1.0,
        }],
        "mode":          "financial_cache",
        "data": {
            "ticker":         ticker,
            "metric":         label,
            "period_type":    intent["period_type"],
            "requested":      wanted_labels,
            "available":      [
                {"period_end": s["period_end"], "value": s["value"]}
                for s in available_series
            ],
            "miss_reason":    "named_period_not_in_cache",
        },
        "fetched_at":        available_series[0]["fetched_at"] if available_series else None,
        "reranking_enabled": False,
    }


def _answer_multi_ticker(query: str, intents: list[dict], original_query: str) -> Optional[dict]:
    """Handle queries that mention multiple companies."""
    from backend.aichat.financial_cache.intent import detect_all_financial_intents
    specific_periods, year_only = _extract_fiscal_filter(query)
    fetch_limit = 20 if (specific_periods or year_only) else intents[0]["limit"]
    wants_table = _is_table_query(original_query)

    all_series: dict[str, list] = {}
    for intent in intents:
        ticker = intent["ticker"]
        series = query_metric(
            ticker,
            intent["metric_field"],
            period_type=intent["period_type"],
            limit=fetch_limit,
        )
        series = [s for s in series if s.get("value") is not None]
        if specific_periods or year_only:
            filtered = []
            for s in series:
                lbl = fiscal_label(ticker, s["period_end"]) or ""
                fy_year = lbl.split(" ")[0] if lbl else ""
                if lbl in specific_periods:
                    filtered.append(s)
                elif fy_year in year_only:
                    filtered.append(s)
                elif intent["period_type"] == "annual" and any(
                    fy in year_only for fy in [fy_year, f"FY{s['period_end'][:4]}"]
                ):
                    filtered.append(s)
            series = filtered
        if series:
            all_series[ticker] = series

    if not all_series:
        return None

    # Build combined response
    intent = intents[0]
    label = intent["metric_label"]
    flip_sign = label in _FLIP_SIGN_FIELDS

    lines: list[str] = []
    for ticker, series in all_series.items():
        for s in series:
            fy_lbl = fiscal_label(ticker, s["period_end"]) or s["period_end"]
            if intent["period_type"] == "annual" and " Q" in fy_lbl:
                fy_lbl = fy_lbl.split(" ")[0]  # strip Q label for annual data
            v_fmt = _format_value(s["value"], flip_sign=flip_sign)
            lines.append(f"- {ticker} {fy_lbl} (period ending {s['period_end']}): {v_fmt}")

    response = f"**{label}**\n\n" + "\n".join(lines)

    fetched_ats = [s["fetched_at"] for series in all_series.values() for s in series]
    fetched_at = max(fetched_ats) if fetched_ats else ""

    result: dict = {
        "response":          response,
        "sources":           [],
        "mode":              "financial_cache",
        "data":              {"tickers": list(all_series.keys()), "metric": label},
        "fetched_at":        fetched_at,
        "reranking_enabled": False,
    }

    if wants_table:
        columns = ["Company", "Period", f"{label} (USD Millions)"]
        rows = []
        for ticker, series in all_series.items():
            for s in series:
                fy_lbl = fiscal_label(ticker, s["period_end"]) or s["period_end"]
                if intent["period_type"] == "annual" and " Q" in fy_lbl:
                    fy_lbl = fy_lbl.split(" ")[0]
                v_fmt = _format_value(s["value"], flip_sign=flip_sign)
                rows.append([ticker, fy_lbl, v_fmt])
        result["table_payload"] = {
            "title": f"{label} Comparison (USD Millions)",
            "columns": columns,
            "rows": rows,
        }
        result["narrative_text"] = f"{label} comparison across {len(all_series)} companies."

    return result


def answer_financial_query(query: str) -> Optional[dict]:
    """Try to answer a query from the cache. Return None if not applicable.

    Used by both pipeline.process_query and the /chat[/stream] route handlers
    to short-circuit numeric financial questions before any RAG / web search
    runs. Builds a deterministic Markdown response — no LLM round-trip — so
    the answer is unaffected by whatever response template the frontend
    prepends to the user's text.
    """
    original_query = query
    query = _strip_frontend_template(query)
    from backend.aichat.financial_cache.intent import detect_all_financial_intents
    intents = detect_all_financial_intents(query)
    if not intents:
        return None
    if len(intents) == 1:
        intent = intents[0]
    else:
        return _answer_multi_ticker(query, intents, original_query)

    if intent["statement"] == "info":
        snap = query_snapshot(intent["ticker"], "info", "snapshot")
        if not snap or intent["metric_field"] not in (snap.get("payload") or {}):
            return None
        value = snap["payload"][intent["metric_field"]]
        if value is None:
            return None
        series = [{
            "period_end": snap["period_end"],
            "value":      value,
            "statement":  "info",
            "fetched_at": snap["fetched_at"],
        }]
    else:
        # When the user named specific historical periods (FY2025 Q1, etc.),
        # widen the fetch window so we have enough history (~5 years) to
        # cover whatever they pointed at — EDGAR returns full history, but
        # the default `intent["limit"]` is small.
        specific_periods, year_only = _extract_fiscal_filter(query)
        fetch_limit = 20 if (specific_periods or year_only) else intent["limit"]
        series = query_metric(
            intent["ticker"],
            intent["metric_field"],
            period_type=intent["period_type"],
            limit=fetch_limit,
        )
        # Filter out None values; if everything is None, treat as miss.
        series = [s for s in series if s.get("value") is not None]
        if not series:
            return None

        # If the user named specific FY/Q periods, narrow the table to just those.
        named_periods = bool(specific_periods or year_only)
        if named_periods:
            filtered = []
            for s in series:
                lbl = fiscal_label(intent["ticker"], s["period_end"]) or ""
                if lbl in specific_periods:
                    filtered.append(s)
                elif lbl and lbl.split(" ")[0] in year_only:
                    filtered.append(s)
            # If NONE of the named periods are in cache, don't fall through —
            # the original RAG flow tends to hallucinate "Over the last 0
            # quarters..." style messages on these queries. Show the user a
            # clear message naming the missing periods and listing what IS
            # available, so they can re-ask within the cache window.
            if not filtered:
                wanted_lbls = sorted(specific_periods | year_only)
                return _build_named_period_miss_result(
                    intent, query, wanted_lbls, series, original_query
                )
            series = filtered

    wants_table = _is_table_query(original_query)
    if wants_table:
        response = _build_table_response(intent, series)
    else:
        response = _build_default_response(intent, series)

    result = {
        "response": response,
        "sources": [{
            "company":     intent["ticker"],
            "source":      "yfinance",
            "filing_type": "financial_cache",
            "fiscal_year": series[0]["period_end"][:4] if series else None,
            "similarity":  1.0,
        }],
        "mode":          "financial_cache",
        "data": {
            "ticker":      intent["ticker"],
            "metric":      intent["metric_label"],
            "period_type": intent["period_type"],
            "series":      series,
        },
        "fetched_at":        series[0]["fetched_at"] if series else None,
        "reranking_enabled": False,
    }

    # Only produce the structured table payload when the user asked for a
    # table — the dedicated frontend component renders it specially.
    if wants_table:
        result["table_payload"]  = _build_table_payload(intent, series)
        result["narrative_text"] = (
            f"{intent['ticker']} {intent['metric_label']} "
            f"({intent['period_type']}) from yfinance cache."
        )

    return result
