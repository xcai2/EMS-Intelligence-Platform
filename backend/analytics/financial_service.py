"""
Financial data service with yfinance primary source and ChromaDB vector DB fallback.
Returns: Total Revenue, Operating Income, Net Income, EPS, Operating Margin for 2022-2026.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

COMPANY_NAME_TO_TICKER = {
    "Flex": "FLEX",
    "Jabil": "JBL",
    "Celestica": "CLS",
    "Benchmark": "BHE",
    "Sanmina": "SANM",
    "Plexus": "PLXS",
}

YEAR_RANGE = {"2022", "2023", "2024", "2025", "2026"}

INCOME_MAP = {
    "Total Revenue": "revenue",
    "Operating Income": "operating_income",
    "Net Income": "net_income",
    "Diluted EPS": "eps",
}


def _format_millions(val) -> Optional[float]:
    try:
        f = float(val)
        return round(f / 1e6, 2)
    except (TypeError, ValueError):
        return None


def _format_eps(val) -> Optional[float]:
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None


def fetch_yfinance_financials(company: str) -> dict:
    """Fetch financials from yfinance, filtered to 2022-2026."""
    import yfinance as yf

    ticker_symbol = COMPANY_NAME_TO_TICKER.get(company)
    if not ticker_symbol:
        return {}

    ticker = yf.Ticker(ticker_symbol)
    income = ticker.income_stmt

    if income is None or income.empty:
        return {}

    years = {}

    for col in income.columns:
        year_label = str(col.year) if hasattr(col, "year") else str(col)[:4]
        if year_label not in YEAR_RANGE:
            continue

        entry = {"source": "yfinance"}

        for yf_key, our_key in INCOME_MAP.items():
            if yf_key not in income.index:
                continue
            raw = income.loc[yf_key, col]
            val = _format_eps(raw) if our_key == "eps" else _format_millions(raw)
            if val is not None:
                entry[our_key] = val

        # Compute operating margin
        rev = entry.get("revenue")
        op = entry.get("operating_income")
        if rev and op and rev != 0:
            entry["operating_margin"] = round((op / rev) * 100, 2)

        if len(entry) > 1:
            years[year_label] = entry

    return {"fiscal_years": years, "source": "yfinance", "ticker": ticker_symbol}


_CAPEX_KEYS = (
    "Capital Expenditure",
    "Capital Expenditures",
    "Purchase Of Property Plant And Equipment",
)


def fetch_yfinance_capex(company: str) -> dict:
    """Return {year_str: capex_millions} for 2022-2026 from yfinance cash flow statement."""
    import yfinance as yf

    ticker_symbol = COMPANY_NAME_TO_TICKER.get(company)
    if not ticker_symbol:
        return {}
    try:
        cashflow = yf.Ticker(ticker_symbol).cashflow
    except Exception:
        return {}
    if cashflow is None or cashflow.empty:
        return {}

    result = {}
    for col in cashflow.columns:
        year_label = str(col.year) if hasattr(col, "year") else str(col)[:4]
        if year_label not in YEAR_RANGE:
            continue
        for key in _CAPEX_KEYS:
            if key in cashflow.index:
                val = _format_millions(cashflow.loc[key, col])
                if val is not None:
                    result[year_label] = abs(val)
                break
    return result


def get_company_financials(company: str) -> dict:
    """Primary: yfinance. Fallback: ChromaDB vector DB extraction."""
    try:
        result = fetch_yfinance_financials(company)
        if result and result.get("fiscal_years"):
            logger.info("Financials for %s loaded from yfinance", company)
            return result
    except Exception as e:
        logger.warning("yfinance failed for %s: %s — falling back to vector DB", company, e)

    try:
        from backend.analytics.table_extractor import extract_company_financials
        financials = extract_company_financials(company)
        # Filter fallback data to 2022-2026 as well
        filtered = {
            yr: data
            for yr, data in financials.get("fiscal_years", {}).items()
            if yr in YEAR_RANGE
        }
        logger.info("Financials for %s loaded from vector DB fallback", company)
        return {"fiscal_years": filtered, "source": "vector_db"}
    except Exception as e:
        logger.error("Vector DB fallback also failed for %s: %s", company, e)
        return {"fiscal_years": {}, "source": "error", "error": str(e)}
