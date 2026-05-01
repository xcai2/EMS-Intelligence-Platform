"""EDGAR + yfinance fetcher for the AI Chat financial cache.

Data source strategy:
  - Financial statements (income / balance / cashflow):
      Primary:  SEC EDGAR companyfacts API  → full history, all quarters
      Fallback: yfinance                    → if EDGAR fetch fails for a ticker
  - Market / info data (marketCap, P/E, etc.):
      Always:   yfinance Ticker.info        → EDGAR has no market data

The output format is IDENTICAL to the old yfinance-only fetcher.py.
repository.py, db.py, service.py, and intent.py need ZERO changes.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime
from typing import Any, Optional

import requests
import yfinance as yf


# ---------------------------------------------------------------------------
# 1.  Company → CIK mapping
#     CIK is the unique ID SEC uses for every registrant.
#     Pad to 10 digits with leading zeros (SEC convention).
# ---------------------------------------------------------------------------
_TICKER_TO_CIK: dict[str, str] = {
    "FLEX":  "0000866374",
    "JBL":   "0000898293",
    "CLS":   "0001030894",
    "BHE":   "0000863436",
    "SANM":  "0000897723",
    "PLXS":  "0000785786",
    # Hyperscalers — EDGAR has them too
    "AMZN":  "0001018724",
    "GOOGL": "0001652044",
    "MSFT":  "0000789019",
    "META":  "0001326801",
    "ORCL":  "0001341439",
}

# ---------------------------------------------------------------------------
# 2.  EDGAR XBRL concept → yfinance field name
#
#     Each entry is a list because companies sometimes file under slightly
#     different concept names across years.  We try them IN ORDER and use
#     the first one that has data for the requested ticker.
#
#     The VALUE stored in SQLite is keyed by the yfinance field name on the
#     RIGHT so that service.py / intent.py never need to change.
# ---------------------------------------------------------------------------
_EDGAR_INCOME_MAP: list[tuple[list[str], str]] = [
    # (EDGAR concept candidates,                      yfinance field name)
    (["Revenues",
      "RevenueFromContractWithCustomerExcludingAssessedTax",
      "SalesRevenueNet"],                             "Total Revenue"),

    (["CostOfRevenue",
      "CostOfGoodsSold",
      "CostOfGoodsAndServicesSold"],                  "Cost Of Revenue"),

    (["GrossProfit"],                                 "Gross Profit"),

    (["OperatingIncomeLoss"],                         "Operating Income"),

    (["OperatingExpenses"],                           "Operating Expense"),

    (["SellingGeneralAndAdministrativeExpense"],      "Selling General And Administration"),

    (["EarningsPerShareDiluted"],                     "Diluted EPS"),
    (["EarningsPerShareBasic"],                       "Basic EPS"),

    (["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
                                                      "Pretax Income"),

    (["IncomeTaxExpenseBenefit"],                     "Tax Provision"),

    (["NetIncomeLoss",
      "ProfitLoss"],                                  "Net Income"),

    (["InterestExpense",
      "InterestAndDebtExpense"],                      "Interest Expense"),

    (["InterestIncomeOperating",
      "InvestmentIncomeInterest"],                    "Interest Income"),

    # EBITDA is not filed directly; we skip it (yfinance calculates it)
    # EBIT is also not a standard XBRL concept
]

_EDGAR_CASHFLOW_MAP: list[tuple[list[str], str]] = [
    (["NetCashProvidedByUsedInOperatingActivities"],  "Operating Cash Flow"),

    (["PaymentsToAcquirePropertyPlantAndEquipment",
      "PaymentsToAcquireProductiveAssets",
      "PaymentsForCapitalImprovements"],              "Capital Expenditure"),

    (["DepreciationDepletionAndAmortization",
      "DepreciationAndAmortization"],                 "Depreciation And Amortization"),

    (["Depreciation"],                                "Depreciation"),

    (["AmortizationOfIntangibleAssets"],              "Amortization"),

    (["NetCashProvidedByUsedInInvestingActivities"],  "Investing Cash Flow"),

    (["NetCashProvidedByUsedInFinancingActivities"],  "Financing Cash Flow"),

    (["PaymentsForRepurchaseOfCommonStock",
      "PaymentsForRepurchaseOfEquity"],               "Repurchase Of Capital Stock"),

    (["ProceedsFromIssuanceOfDebt",
      "ProceedsFromIssuanceOfLongTermDebt"],          "Issuance Of Debt"),

    (["RepaymentsOfDebt",
      "RepaymentsOfLongTermDebt"],                    "Repayment Of Debt"),

    (["CashAndCashEquivalentsAtCarryingValue",
      "CashCashEquivalentsAndShortTermInvestments"],  "End Cash Position"),
]

_EDGAR_BALANCE_MAP: list[tuple[list[str], str]] = [
    (["Assets"],                                      "Total Assets"),

    (["Liabilities"],                                 "Total Liabilities Net Minority Interest"),

    (["LongTermDebtAndCapitalLeaseObligations",
      "LongTermDebt"],                                "Long Term Debt"),

    (["ShortTermBorrowings",
      "DebtCurrent"],                                 "Current Debt"),

    (["LongTermDebtCurrent",
      "LongTermDebtNoncurrent"],                      "Total Debt"),

    (["StockholdersEquity",
      "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
                                                      "Stockholders Equity"),

    (["InventoryNet"],                                "Inventory"),

    (["AccountsReceivableNetCurrent",
      "ReceivablesNetCurrent"],                       "Receivables"),

    (["AccountsPayableCurrent",
      "AccountsPayable"],                             "Accounts Payable"),

    (["Goodwill"],                                    "Goodwill"),

    (["PropertyPlantAndEquipmentNet"],                "Net PPE"),

    (["RetainedEarningsAccumulatedDeficit"],          "Retained Earnings"),

    (["TreasuryStockValue"],                          "Treasury Stock"),
]

# Statement label → map to use
_STATEMENT_MAPS = {
    "income":   _EDGAR_INCOME_MAP,
    "cashflow": _EDGAR_CASHFLOW_MAP,
    "balance":  _EDGAR_BALANCE_MAP,
}

# ---------------------------------------------------------------------------
# 3.  yfinance info fields (unchanged from original fetcher.py)
# ---------------------------------------------------------------------------
_INFO_FIELDS = (
    "marketCap", "trailingPE", "forwardPE", "sharesOutstanding",
    "trailingEps", "forwardEps", "dividendYield", "currency",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
)

# EDGAR rate-limit: SEC asks for max 10 req/sec; we stay well under.
_EDGAR_REQUEST_DELAY = 0.15   # seconds between concept fetches


# ---------------------------------------------------------------------------
# 4.  Helper utilities
# ---------------------------------------------------------------------------

def _clean(value: Any) -> Any:
    """Make a value JSON-serializable. NaN / Inf → None."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _edgar_headers() -> dict[str, str]:
    """SEC requires a descriptive User-Agent on every request."""
    return {"User-Agent": "PracticumProject2026 research@example.com"}


# ---------------------------------------------------------------------------
# 5.  EDGAR data fetcher
# ---------------------------------------------------------------------------

def _fetch_company_facts(cik: str) -> Optional[dict]:
    """Download the full companyfacts JSON for one CIK.

    Returns the parsed dict, or None on any error.
    SEC endpoint: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        resp = requests.get(url, headers=_edgar_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _extract_concept_series(
    gaap_facts: dict,
    concepts: list[str],
    period_type: str,
) -> list[tuple[str, float]]:
    """Try each XBRL concept in order; merge results across all concepts.
    Later concepts fill in gaps left by earlier ones.
    """
    merged_map: dict[str, float] = {}

    for concept in concepts:
        entry = gaap_facts.get(concept)
        if not entry:
            continue
        units = entry.get("units", {})
        raw_rows = units.get("USD") or units.get("USD/shares") or []
        if not raw_rows:
            continue

        results: list[tuple] = []

        for row in raw_rows:
            end_date   = row.get("end", "")
            start_date = row.get("start", "")
            val        = row.get("val")
            form       = row.get("form", "")

            if val is None or form not in ("10-Q", "10-K"):
                continue

            is_instant = not start_date

            if is_instant:
                results.append((end_date, float(val), 0, "", "single"))
            else:
                try:
                    from datetime import date
                    d_start = date.fromisoformat(start_date)
                    d_end   = date.fromisoformat(end_date)
                    days    = (d_end - d_start).days
                except ValueError:
                    continue

                if period_type == "annual" and 340 <= days <= 380:
                    # Only the actual annual report (10-K) carries the true
                    # fiscal-year value. 10-Qs sometimes file 365-day TTM
                    # rolling values that would otherwise pass this filter
                    # (e.g. AMZN reports TTM CapEx every quarter), polluting
                    # annual results with non-FY numbers.
                    if form != "10-K":
                        continue
                    results.append((end_date, float(val), days, start_date, "annual"))
                elif period_type == "quarterly":
                    if 60 <= days <= 105:
                        results.append((end_date, float(val), days, start_date, "single"))
                    elif 106 <= days <= 380:
                        results.append((end_date, float(val), days, start_date, "cumulative"))

        if not results:
            continue

        # Process results into a period_map for this concept
        concept_map: dict[str, float] = {}

        if period_type == "quarterly":
            def _qk(d: str) -> str:
                y, m, _ = d.split("-")
                return f"{y}-Q{(int(m)-1)//3+1}"

            from collections import defaultdict
            # Group ALL duration entries (90-day singles AND multi-quarter
            # cumulatives) by their fiscal-year start_date. Within each
            # group, sort by days ascending and difference adjacent values
            # to produce single-quarter deltas — Q1 = val(90) - 0,
            # Q2 = val(181) - val(90), etc. This handles the common XBRL
            # pattern where companies file YTD-style cumulatives whose
            # start_date is the fiscal year beginning.
            entries_by_start: dict[str, list] = defaultdict(list)
            for item in results:
                end, v, days, start, kind = item
                # Skip instant rows (kind="single" with no start_date) — those
                # come from the balance-sheet path, not duration data.
                if kind in ("single", "cumulative") and start:
                    entries_by_start[start].append((days, end, v))

            # Per-quarter dedup map: qk -> (latest_end_date, value)
            best_per_qk: dict[str, tuple[str, float]] = {}

            for start, entries in entries_by_start.items():
                entries.sort(key=lambda x: x[0])
                prev_days = 0
                prev_val = 0.0
                for days, end, v in entries:
                    if days - prev_days >= 30:
                        single_val = v - prev_val
                        qk = _qk(end)
                        # Prefer the latest end_date when same qk appears
                        # in multiple groups (e.g. cumulative vs single-Q
                        # filings landing on the same fiscal Q).
                        if qk not in best_per_qk or end > best_per_qk[qk][0]:
                            best_per_qk[qk] = (end, single_val)
                    prev_days = days
                    prev_val = v

            concept_map = {end: v for end, v in best_per_qk.values()}

        else:
            # Annual: deduplicate by end date
            for item in results:
                end, v = item[0], item[1]
                concept_map[end] = v

        # Merge into global map: only fill gaps (don't overwrite existing)
        for end, v in concept_map.items():
            if end not in merged_map:
                merged_map[end] = v

    if not merged_map:
        return []
    return sorted(merged_map.items(), reverse=True)


def _edgar_to_snapshots(
    cik: str,
    ticker: str,
    facts: dict,
    fetched_at: str,
) -> list[dict]:
    """Convert EDGAR companyfacts → list of snapshot dicts (same format as
    the old yfinance _frame_to_snapshots output).

    For each (statement, period_type) combination we collect all mapped
    metrics, group them by period_end, and emit one snapshot row per period.
    This matches the SQLite schema perfectly:
        PRIMARY KEY (ticker, statement, period_type, period_end)
    """
    gaap = facts.get("facts", {}).get("us-gaap", {})
    if not gaap:
        return []

    snapshots: list[dict] = []

    for statement, concept_map in _STATEMENT_MAPS.items():
        for period_type in ("quarterly", "annual"):
            # Collect all metrics for this statement+period_type
            # period_payloads: {period_end: {yfinance_field: value}}
            period_payloads: dict[str, dict[str, Any]] = {}

            for concepts, yf_field in concept_map:
                series = _extract_concept_series(gaap, concepts, period_type)
                time.sleep(_EDGAR_REQUEST_DELAY)   # be polite to SEC servers
                # CapEx must always be stored as negative (cash outflow).
                # EDGAR sometimes files it as positive, sometimes negative.
                # service.py's _FLIP_SIGN_FIELDS will then flip it to
                # positive for display, giving a consistent result.
                _FORCE_NEGATIVE_FIELDS = {"Capital Expenditure"}
                for period_end, value in series:
                    if period_end not in period_payloads:
                        period_payloads[period_end] = {}
                    if yf_field in _FORCE_NEGATIVE_FIELDS and value > 0:
                        value = -value
                    period_payloads[period_end][yf_field] = value

            # Emit one snapshot row per period_end
            for period_end, payload in period_payloads.items():
                if not payload:
                    continue
                snapshots.append({
                    "ticker":      ticker,
                    "statement":   statement,
                    "period_type": period_type,
                    "period_end":  period_end,
                    "payload":     json.dumps(payload, ensure_ascii=False),
                    "fetched_at":  fetched_at,
                })

    # Derive Free Cash Flow = Operating Cash Flow - Capital Expenditure
    # (EDGAR has no direct FCF concept)
    snapshots = _add_free_cash_flow(snapshots, ticker, fetched_at)

    return snapshots


def _add_free_cash_flow(
    snapshots: list[dict],
    ticker: str,
    fetched_at: str,
) -> list[dict]:
    """Post-process: compute Free Cash Flow and inject it into cashflow rows.

    FCF = Operating Cash Flow + Capital Expenditure
    (CapEx is stored as a negative number in EDGAR, so we ADD it.)
    If either value is missing for a period, we skip that period.
    """
    # Index existing cashflow snapshots by (period_type, period_end)
    cf_index: dict[tuple[str, str], dict] = {}
    for snap in snapshots:
        if snap["statement"] == "cashflow":
            key = (snap["period_type"], snap["period_end"])
            cf_index[key] = snap

    for key, snap in cf_index.items():
        try:
            payload = json.loads(snap["payload"])
        except (json.JSONDecodeError, TypeError):
            continue
        ocf   = payload.get("Operating Cash Flow")
        capex = payload.get("Capital Expenditure")
        if ocf is not None and capex is not None:
            # CapEx from EDGAR is negative (cash outflow); FCF = OCF + CapEx
            payload["Free Cash Flow"] = ocf + capex
            snap["payload"] = json.dumps(payload, ensure_ascii=False)

    return snapshots


# ---------------------------------------------------------------------------
# 6.  yfinance info fetch (unchanged purpose from original fetcher.py)
# ---------------------------------------------------------------------------

def _fetch_yfinance_info(ticker: str, fetched_at: str) -> Optional[dict]:
    """Fetch market/info snapshot from yfinance. Returns a snapshot row or None."""
    try:
        t    = yf.Ticker(ticker)
        info = t.info or {}
        info_payload = {k: _clean(info.get(k)) for k in _INFO_FIELDS}
        return {
            "ticker":      ticker,
            "statement":   "info",
            "period_type": "snapshot",
            "period_end":  fetched_at[:10],
            "payload":     json.dumps(info_payload, ensure_ascii=False),
            "fetched_at":  fetched_at,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 7.  yfinance FULL fallback (used when EDGAR fetch fails entirely)
#     Identical logic to the original fetcher.py fetch_ticker.
# ---------------------------------------------------------------------------

def _fetch_yfinance_statements(ticker: str, fetched_at: str) -> list[dict]:
    """Pull income / balance / cashflow from yfinance as a fallback.

    Used only when EDGAR returns no data for a ticker.
    Output format is the same as _edgar_to_snapshots.
    """
    try:
        t = yf.Ticker(ticker)
    except Exception:
        return []

    statement_map = [
        ("income",   "quarterly", "quarterly_financials"),
        ("income",   "annual",    "financials"),
        ("balance",  "quarterly", "quarterly_balance_sheet"),
        ("balance",  "annual",    "balance_sheet"),
        ("cashflow", "quarterly", "quarterly_cashflow"),
        ("cashflow", "annual",    "cashflow"),
    ]
    snapshots: list[dict] = []
    for statement, period_type, attr in statement_map:
        try:
            frame = getattr(t, attr)
            if frame is None or frame.empty:
                continue
            for col in frame.columns:
                try:
                    period_end = col.strftime("%Y-%m-%d")
                except AttributeError:
                    period_end = str(col)[:10]
                payload = {
                    str(idx): _clean(frame.at[idx, col])
                    for idx in frame.index
                }
                snapshots.append({
                    "ticker":      ticker,
                    "statement":   statement,
                    "period_type": period_type,
                    "period_end":  period_end,
                    "payload":     json.dumps(payload, ensure_ascii=False),
                    "fetched_at":  fetched_at,
                })
        except Exception:
            continue
    return snapshots


# ---------------------------------------------------------------------------
# 8.  Public entry point  (same signature as original fetch_ticker)
# ---------------------------------------------------------------------------

def fetch_ticker(ticker: str) -> tuple[list[dict], str | None]:
    """Fetch all financial data for one ticker.

    Strategy:
      1. Look up CIK for the ticker.
      2. Fetch full companyfacts JSON from SEC EDGAR.
      3. Convert EDGAR data → snapshot rows (full history).
      4. Fetch yfinance info snapshot (market data).
      5. If EDGAR failed entirely, fall back to yfinance statements.

    Returns (snapshots, error_string_or_None).
    Matches the exact signature of the original fetch_ticker so that
    service.py / refresh_one / refresh_all need no changes.
    """
    fetched_at = datetime.utcnow().isoformat(timespec="seconds")
    ticker     = ticker.upper()
    errors: list[str] = []
    snapshots: list[dict] = []

    # --- Step 1: EDGAR financial statements ---
    cik = _TICKER_TO_CIK.get(ticker)
    edgar_ok = False

    if cik:
        facts = _fetch_company_facts(cik)
        if facts:
            edgar_snaps = _edgar_to_snapshots(cik, ticker, facts, fetched_at)
            if edgar_snaps:
                snapshots.extend(edgar_snaps)
                edgar_ok = True
            else:
                errors.append("EDGAR: companyfacts returned no usable rows")
        else:
            errors.append("EDGAR: failed to download companyfacts JSON")
    else:
        errors.append(f"EDGAR: no CIK mapping for {ticker}")

    # --- Step 2: yfinance info (always, EDGAR has no market data) ---
    info_snap = _fetch_yfinance_info(ticker, fetched_at)
    if info_snap:
        snapshots.append(info_snap)
    else:
        errors.append("yfinance info: fetch failed")

    # --- Step 3: yfinance fallback if EDGAR gave nothing ---
    if not edgar_ok:
        yf_snaps = _fetch_yfinance_statements(ticker, fetched_at)
        if yf_snaps:
            snapshots.extend(yf_snaps)
            errors.append("EDGAR unavailable — used yfinance statements as fallback")
        else:
            errors.append("yfinance fallback: also failed")

    error_str = "; ".join(errors) if errors else None
    return snapshots, error_str
