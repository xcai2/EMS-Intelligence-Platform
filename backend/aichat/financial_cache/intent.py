"""Intent detection for numeric financial queries.

A query is treated as a financial-cache query iff:
  - At least one tracked company is mentioned (ticker / name / alias), AND
  - At least one mapped metric keyword is present, AND
  - It is not asking for a CapEx breakdown / segment / customer split
    (those have to fall back to RAG — see design §6).

Output is a `FinancialIntent` dict consumed by pipeline.py.

Vocabulary is English-first. A small set of common Chinese aliases is kept
so previously tested Chinese queries (e.g. "Flex 最近一季营收") still match.
To add a new alias, append it to the relevant metric's `aliases` list.
"""

from __future__ import annotations

import re
from typing import Optional, TypedDict

from backend.aichat.financial_cache.companies import COMPANIES, resolve_ticker


class FinancialIntent(TypedDict):
    ticker:        str
    metric_field:  str           # exact yfinance field name
    metric_label:  str           # human label (e.g. "Revenue")
    statement:     str           # 'income' | 'balance' | 'cashflow' | 'info'
    period_type:   str           # 'quarterly' | 'annual'
    limit:         int           # number of periods to return
    period_end:    Optional[str] # exact period if user named one (else None)


# ===========================================================================
#                       FINANCIAL METRIC VOCABULARY
# ===========================================================================
# Each metric lists EVERY English alias users might use — full name,
# abbreviation, and common synonyms. A short set of canonical Chinese
# aliases is kept per metric for backward compatibility.
#
# Aliases match as case-insensitive substrings. After flattening, all
# aliases are sorted by length descending so longer/more-specific phrases
# win over shorter ones (e.g. "free cash flow" wins over "cash flow").
# ===========================================================================
METRICS: list[dict] = [
    # ------------------------------------------------------------ INCOME ---
    {
        "field": "Total Revenue", "statement": "income", "label": "Total Revenue",
        "aliases": [
            "total revenue", "net revenue", "net sales", "operating revenue",
            "revenue", "sales", "turnover", "top line", "topline",
            "营收", "收入",
        ],
    },
    {
        "field": "Cost Of Revenue", "statement": "income", "label": "Cost of Revenue",
        "aliases": [
            "cost of revenue", "cost of goods sold", "cost of sales", "cogs",
            "成本",
        ],
    },
    {
        "field": "Gross Profit", "statement": "income", "label": "Gross Profit",
        "aliases": [
            "gross profit", "gross income", "gross margin",
            "毛利",
        ],
    },
    {
        "field": "Operating Income", "statement": "income", "label": "Operating Income",
        "aliases": [
            "operating income", "operating profit", "income from operations",
            "营业利润",
        ],
    },
    {
        "field": "Operating Expense", "statement": "income", "label": "Operating Expense",
        "aliases": [
            "operating expense", "operating expenses", "opex",
        ],
    },
    {
        "field": "Selling General And Administration", "statement": "income",
        "label": "SG&A",
        "aliases": [
            "selling general and administration", "selling general administrative",
            "sg&a", "sga", "selling and administrative",
        ],
    },
    {
        "field": "EBITDA", "statement": "income", "label": "EBITDA",
        "aliases": [
            "ebitda",
            "earnings before interest taxes depreciation and amortization",
        ],
    },
    {
        "field": "EBIT", "statement": "income", "label": "EBIT",
        "aliases": [
            "ebit", "earnings before interest and tax",
        ],
    },
    {
        "field": "Pretax Income", "statement": "income", "label": "Pretax Income",
        "aliases": [
            "pretax income", "pre-tax income", "pre tax income", "income before tax",
            "ebt", "earnings before tax",
        ],
    },
    {
        "field": "Tax Provision", "statement": "income", "label": "Income Tax",
        "aliases": [
            "tax provision", "income tax", "income taxes", "tax expense",
        ],
    },
    {
        "field": "Interest Expense", "statement": "income", "label": "Interest Expense",
        "aliases": [
            "interest expense",
        ],
    },
    {
        "field": "Interest Income", "statement": "income", "label": "Interest Income",
        "aliases": [
            "interest income",
        ],
    },
    {
        "field": "Net Income", "statement": "income", "label": "Net Income",
        "aliases": [
            "net income", "net profit", "net earnings",
            "bottom line", "bottomline",
            "净利润",
        ],
    },
    # NOTE: Specific EPS variants must come before any standalone "EPS" alias.
    {
        "field": "Diluted EPS", "statement": "income", "label": "Diluted EPS",
        "aliases": [
            "diluted earnings per share", "diluted eps",
        ],
    },
    {
        "field": "Basic EPS", "statement": "income", "label": "Basic EPS",
        "aliases": [
            "basic earnings per share", "basic eps",
        ],
    },
    {
        "field": "Diluted EPS", "statement": "income", "label": "Diluted EPS",
        "aliases": [
            "earnings per share", "eps",
            "每股收益",
        ],
    },

    # ----------------------------------------------------------- CASHFLOW --
    {
        "field": "Free Cash Flow", "statement": "cashflow", "label": "Free Cash Flow",
        "aliases": [
            "free cash flow", "fcf",
            "自由现金流",
        ],
    },
    {
        "field": "Operating Cash Flow", "statement": "cashflow",
        "label": "Operating Cash Flow",
        "aliases": [
            "operating cash flow", "cash from operations", "cash flow from operations",
            "ocf", "cfo",
            "经营现金流",
        ],
    },
    {
        "field": "Investing Cash Flow", "statement": "cashflow",
        "label": "Investing Cash Flow",
        "aliases": [
            "investing cash flow", "cash flow from investing", "cfi",
        ],
    },
    {
        "field": "Financing Cash Flow", "statement": "cashflow",
        "label": "Financing Cash Flow",
        "aliases": [
            "financing cash flow", "cash flow from financing", "cff",
        ],
    },
    # Catch-all "cash flow" — must be AFTER all longer cash-flow phrases.
    {
        "field": "Operating Cash Flow", "statement": "cashflow",
        "label": "Operating Cash Flow",
        "aliases": [
            "cash flow",
            "现金流",
        ],
    },
    {
        "field": "Capital Expenditure", "statement": "cashflow",
        "label": "Capital Expenditure",
        "aliases": [
            "capital expenditures", "capital expenditure",
            "capital spending", "capital spend", "capital investment",
            "capex",
            "资本支出",
        ],
    },
    {
        "field": "Depreciation And Amortization", "statement": "cashflow",
        "label": "Depreciation & Amortization",
        "aliases": [
            "depreciation and amortization", "depreciation & amortization", "d&a",
        ],
    },
    {
        "field": "Depreciation", "statement": "cashflow", "label": "Depreciation",
        "aliases": [
            "depreciation",
        ],
    },
    {
        "field": "Amortization", "statement": "cashflow", "label": "Amortization",
        "aliases": [
            "amortization",
        ],
    },
    {
        "field": "Repurchase Of Capital Stock", "statement": "cashflow",
        "label": "Share Repurchases",
        "aliases": [
            "share repurchase", "stock repurchase", "stock buyback",
            "share buyback", "buybacks", "buyback",
        ],
    },
    {
        "field": "Issuance Of Debt", "statement": "cashflow", "label": "Debt Issuance",
        "aliases": [
            "debt issuance", "issuance of debt",
        ],
    },
    {
        "field": "Repayment Of Debt", "statement": "cashflow", "label": "Debt Repayment",
        "aliases": [
            "debt repayment", "repayment of debt",
        ],
    },
    {
        "field": "End Cash Position", "statement": "cashflow", "label": "Ending Cash Position",
        "aliases": [
            "end cash position", "ending cash position", "ending cash balance",
        ],
    },

    # ----------------------------------------------------------- BALANCE ---
    {
        "field": "Total Assets", "statement": "balance", "label": "Total Assets",
        "aliases": [
            "total assets",
            "总资产",
        ],
    },
    {
        "field": "Total Liabilities Net Minority Interest", "statement": "balance",
        "label": "Total Liabilities",
        "aliases": [
            "total liabilities",
        ],
    },
    {
        "field": "Net Debt", "statement": "balance", "label": "Net Debt",
        "aliases": [
            "net debt",
            "净债务",
        ],
    },
    {
        "field": "Total Debt", "statement": "balance", "label": "Total Debt",
        "aliases": [
            "total debt",
            "总债务",
        ],
    },
    {
        "field": "Long Term Debt", "statement": "balance", "label": "Long Term Debt",
        "aliases": [
            "long term debt", "long-term debt", "ltd",
        ],
    },
    {
        "field": "Current Debt", "statement": "balance", "label": "Current Debt",
        "aliases": [
            "current debt", "short term debt", "short-term debt", "std",
        ],
    },
    {
        "field": "Stockholders Equity", "statement": "balance",
        "label": "Stockholders Equity",
        "aliases": [
            "stockholders equity", "stockholders' equity", "shareholders equity",
            "shareholders' equity", "book value", "equity",
            "股东权益",
        ],
    },
    {
        "field": "Working Capital", "statement": "balance", "label": "Working Capital",
        "aliases": [
            "working capital", "nwc", "net working capital",
            "营运资本",
        ],
    },
    {
        "field": "Inventory", "statement": "balance", "label": "Inventory",
        "aliases": [
            "inventories", "inventory", "stock on hand",
            "存货",
        ],
    },
    {
        "field": "Receivables", "statement": "balance", "label": "Receivables",
        "aliases": [
            "accounts receivable", "trade receivables", "receivables", "ar",
            "应收账款",
        ],
    },
    {
        "field": "Accounts Payable", "statement": "balance", "label": "Accounts Payable",
        "aliases": [
            "accounts payable", "trade payables", "payables", "ap",
        ],
    },
    {
        "field": "Goodwill", "statement": "balance", "label": "Goodwill",
        "aliases": [
            "goodwill",
        ],
    },
    {
        "field": "Net PPE", "statement": "balance",
        "label": "Property, Plant & Equipment (Net)",
        "aliases": [
            "property plant and equipment", "property, plant and equipment",
            "property plant equipment", "ppe", "pp&e", "fixed assets",
        ],
    },
    {
        "field": "Retained Earnings", "statement": "balance", "label": "Retained Earnings",
        "aliases": [
            "retained earnings",
        ],
    },
    {
        "field": "Tangible Book Value", "statement": "balance",
        "label": "Tangible Book Value",
        "aliases": [
            "tangible book value", "tbv",
        ],
    },
    {
        "field": "Treasury Stock", "statement": "balance", "label": "Treasury Stock",
        "aliases": [
            "treasury stock", "treasury shares",
        ],
    },

    # ----------------------------------------------------------- INFO -----
    {
        "field": "marketCap", "statement": "info", "label": "Market Cap",
        "aliases": [
            "market capitalization", "market capitalisation", "market cap",
            "mcap",
            "市值",
        ],
    },
    {
        "field": "forwardPE", "statement": "info", "label": "P/E (Forward)",
        "aliases": [
            "forward pe ratio", "forward p/e ratio", "forward pe", "forward p/e",
            "fwd p/e", "fwd pe",
        ],
    },
    {
        "field": "trailingPE", "statement": "info", "label": "P/E (Trailing)",
        "aliases": [
            "trailing pe ratio", "trailing p/e ratio",
            "trailing pe", "trailing p/e", "ttm pe", "ttm p/e",
            "p/e ratio", "pe ratio",
            "p/e", "p e ratio", "pe",
            "市盈率",
        ],
    },
    {
        "field": "trailingEps", "statement": "info", "label": "EPS (TTM)",
        "aliases": [
            "trailing eps", "ttm eps",
        ],
    },
    {
        "field": "forwardEps", "statement": "info", "label": "EPS (Forward)",
        "aliases": [
            "forward eps", "fwd eps",
        ],
    },
    {
        "field": "sharesOutstanding", "statement": "info", "label": "Shares Outstanding",
        "aliases": [
            "shares outstanding", "share count", "outstanding shares",
            "流通股",
        ],
    },
    {
        "field": "dividendYield", "statement": "info", "label": "Dividend Yield",
        "aliases": [
            "dividend yield",
        ],
    },
    {
        "field": "fiftyTwoWeekHigh", "statement": "info", "label": "52-Week High",
        "aliases": [
            "52 week high", "52-week high", "fifty two week high",
        ],
    },
    {
        "field": "fiftyTwoWeekLow", "statement": "info", "label": "52-Week Low",
        "aliases": [
            "52 week low", "52-week low", "fifty two week low",
        ],
    },
]


def _build_vocab() -> list[tuple[str, str, str, str]]:
    """Flatten METRICS → list of (alias, field, statement, label).

    Sorted by alias length descending so the most specific match wins.
    """
    rows: list[tuple[str, str, str, str]] = []
    for m in METRICS:
        for alias in m["aliases"]:
            rows.append((alias.lower(), m["field"], m["statement"], m["label"]))
    rows.sort(key=lambda r: len(r[0]), reverse=True)
    return rows


_METRIC_VOCAB: list[tuple[str, str, str, str]] = _build_vocab()


# Words that, combined with capex, indicate a non-numeric question (RAG).
_BREAKDOWN_TRIGGERS = [
    "breakdown", "by category", "by region", "by segment", "by area", "by project",
    "where", "用途", "拆分", "分类", "构成", "哪些", "花在", "分布", "明细", "细分",
]


def _has_breakdown_intent(lowered: str) -> bool:
    """True if the query asks for *how* CapEx is split, not the number itself."""
    capex_present = any(kw in lowered for kw in
                        ("capex", "capital expenditure", "资本支出"))
    if not capex_present:
        return False
    return any(trig in lowered for trig in _BREAKDOWN_TRIGGERS)


# Period parsing
_RE_Q_THEN_YEAR = re.compile(r"\bq([1-4])\s*(?:fy)?\s*(\d{4})\b", re.IGNORECASE)
_RE_FY_THEN_Q  = re.compile(r"\bfy\s*(\d{4})\s*q([1-4])\b",        re.IGNORECASE)
_RE_FY_YEAR    = re.compile(r"\bfy\s*(\d{4})\b",                   re.IGNORECASE)
_RE_PAST_N     = re.compile(
    r"\b(?:past|last)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"\s+(?:fiscal\s+)?(quarter|year)s?\b",
    re.IGNORECASE,
)
_RE_PAST_N_ZH  = re.compile(r"(?:过去|最近)\s*(\d+|[一二三四五六七八九十])\s*(季|年)")
# Counts standalone quarter mentions ("Q2", "Q3", etc.) — used to bump limit
# for multi-quarter requests like "FY2025 Q2 and Q3".
_RE_Q_TOKEN    = re.compile(r"\bq[1-4]\b", re.IGNORECASE)

_ZH_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_EN_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
           "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

# When the query references specific FY/quarter periods, return a wider window
# so the LLM can pick the right rows instead of seeing only the latest one.
_FY_DEFAULT_QUARTERLY_LIMIT = 8   # 8 quarters ≈ 2 years — covers what yfinance has.
_FY_DEFAULT_ANNUAL_LIMIT    = 5


def _parse_period(query: str) -> tuple[str, int, Optional[str]]:
    """Return (period_type, limit, exact_period_end_or_None).

    Defaults to ('quarterly', 1, None) — most recent single quarter.
    """
    lowered = query.lower()

    # "past 4 quarters" / "last 5 years"
    m = _RE_PAST_N.search(lowered)
    if m:
        raw = m.group(1)
        n = int(raw) if raw.isdigit() else _EN_NUM.get(raw.lower(), 1)
        unit = m.group(2)
        return ("annual" if unit == "year" else "quarterly", min(n, 12), None)

    # "过去四季度" / "最近 4 年"
    m = _RE_PAST_N_ZH.search(query)
    if m:
        raw = m.group(1)
        n = int(raw) if raw.isdigit() else _ZH_NUM.get(raw, 1)
        unit = m.group(2)
        return ("annual" if unit == "年" else "quarterly", min(n, 12), None)

    # FY references — either order works ("Q2 FY2025", "FY2025 Q2", "FY2025").
    has_fy_quarter = bool(_RE_Q_THEN_YEAR.search(lowered) or _RE_FY_THEN_Q.search(lowered))
    has_fy_year    = bool(_RE_FY_YEAR.search(lowered))

    if has_fy_quarter or has_fy_year:
        # Count Q-tokens — multiple quarters (e.g. "Q2 and Q3") needs a wider window.
        # Always return _FY_DEFAULT_QUARTERLY_LIMIT to give the LLM enough context
        # to identify exactly which fiscal periods the user named.
        if has_fy_quarter:
            return ("quarterly", _FY_DEFAULT_QUARTERLY_LIMIT, None)
        # FY mentioned without specific Q → annual.
        return ("annual", _FY_DEFAULT_ANNUAL_LIMIT, None)

    # Generic "annual" / "fiscal year" mention without a specific year
    if any(kw in lowered for kw in ("annual", "fiscal year", "年报", "全年", "年度")):
        return ("annual", 1, None)

    # Standalone "Q2" without year — give a wider window too.
    if _RE_Q_TOKEN.search(lowered):
        return ("quarterly", _FY_DEFAULT_QUARTERLY_LIMIT, None)

    return ("quarterly", 1, None)


def _match_metric(query: str) -> Optional[tuple[str, str, str]]:
    """Return (yfinance_field, statement, label) or None."""
    lowered = query.lower()
    for keyword, field, statement, label in _METRIC_VOCAB:
        if keyword in lowered:
            return field, statement, label
    return None


def detect_financial_intent(query: str) -> Optional[FinancialIntent]:
    """Classify a user query. Return intent dict or None to fall through to RAG."""
    if not query or not query.strip():
        return None

    lowered = query.lower()

    if _has_breakdown_intent(lowered):
        return None

    ticker = resolve_ticker(query)
    if ticker is None or ticker not in COMPANIES:
        return None

    metric = _match_metric(query)
    if metric is None:
        return None
    field, statement, label = metric

    period_type, limit, period_end = _parse_period(query)

    if statement == "info":
        period_type = "snapshot"
        limit = 1

    return FinancialIntent(
        ticker=ticker,
        metric_field=field,
        metric_label=label,
        statement=statement,
        period_type=period_type,
        limit=limit,
        period_end=period_end,
    )


def detect_all_financial_intents(query: str) -> list[dict]:
    """Detect financial intents for ALL companies mentioned in the query.
    Returns a list of intent dicts, one per company found.
    Returns empty list if no valid intent detected.
    """
    from backend.aichat.financial_cache.companies import resolve_all_tickers
    lowered = query.lower()
    if _has_breakdown_intent(lowered):
        return []
    tickers = resolve_all_tickers(query)
    if not tickers:
        return []
    metric = _match_metric(query)
    if metric is None:
        return []
    field, statement, label = metric
    period_type, limit, period_end = _parse_period(query)
    if statement == "info":
        period_type = "snapshot"
        limit = 1
    return [
        {
            "ticker":       t,
            "metric_field": field,
            "metric_label": label,
            "statement":    statement,
            "period_type":  period_type,
            "limit":        limit,
            "period_end":   period_end,
        }
        for t in tickers
    ]
