"""
Hyperscaler financial data service.
Fetches income statement and cash flow statement from yfinance
for the 5 tracked hyperscaler companies (AMZN, MSFT, GOOGL, META, ORCL).

Completely isolated from the EMS financial data flow in financial_service.py.
"""
import logging
from datetime import datetime
from typing import Optional

from backend.core.cache import SimpleCache
from backend.hyperscaler.models import HyperscalerCompanyFinancials, HyperscalerFinancialsResponse

logger = logging.getLogger(__name__)

HYPERSCALER_TICKERS: dict[str, str] = {
    "Amazon":    "AMZN",
    "Microsoft": "MSFT",
    "Alphabet":  "GOOGL",
    "Meta":      "META",
    "Oracle":    "ORCL",
}

TICKER_TO_NAME: dict[str, str] = {v: k for k, v in HYPERSCALER_TICKERS.items()}

COMPANY_COLORS: dict[str, str] = {
    "Amazon":    "#FF9900",
    "Microsoft": "#00A4EF",
    "Alphabet":  "#4285F4",
    "Meta":      "#1877F2",
    "Oracle":    "#F80000",
}

_CAPEX_KEYS = ("Capital Expenditure", "Capital Expenditures", "Purchase Of Property Plant And Equipment")

_cache: SimpleCache = SimpleCache(default_ttl=86400)

_INCOME_MAP = {
    "Total Revenue":    "revenue",
    "Operating Income": "operating_income",
    "Net Income":       "net_income",
}


def _to_billions(val) -> Optional[float]:
    try:
        return round(float(val) / 1e9, 2)
    except (TypeError, ValueError):
        return None


def fetch_hyperscaler_financials(company: str) -> HyperscalerCompanyFinancials:
    cache_key = f"hyperscaler:financials:{company}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return HyperscalerCompanyFinancials(**cached)

    ticker_symbol = HYPERSCALER_TICKERS.get(company)
    if not ticker_symbol:
        return HyperscalerCompanyFinancials(company=company, ticker="", color="", error=f"Unknown hyperscaler: {company}")

    try:
        import yfinance as yf
    except ImportError:
        return HyperscalerCompanyFinancials(company=company, ticker=ticker_symbol, color="", error="yfinance not installed")

    try:
        ticker = yf.Ticker(ticker_symbol)
        income   = ticker.income_stmt
        cashflow = ticker.cashflow
    except Exception as exc:
        logger.error("yfinance fetch failed for %s (%s): %s", company, ticker_symbol, exc)
        return HyperscalerCompanyFinancials(company=company, ticker=ticker_symbol, color="", error=str(exc))

    fiscal_years: dict[str, dict] = {}

    if income is not None and not income.empty:
        for col in income.columns:
            year = str(col.year) if hasattr(col, "year") else str(col)[:4]
            entry = fiscal_years.setdefault(year, {})
            for yf_key, our_key in _INCOME_MAP.items():
                if yf_key in income.index:
                    val = _to_billions(income.loc[yf_key, col])
                    if val is not None:
                        entry[our_key] = val
            rev = entry.get("revenue")
            op  = entry.get("operating_income")
            if rev and op and rev != 0:
                entry["operating_margin"] = round((op / rev) * 100, 2)

    if cashflow is not None and not cashflow.empty:
        for col in cashflow.columns:
            year = str(col.year) if hasattr(col, "year") else str(col)[:4]
            entry = fiscal_years.setdefault(year, {})
            for key in _CAPEX_KEYS:
                if key in cashflow.index:
                    val = _to_billions(cashflow.loc[key, col])
                    if val is not None:
                        entry["capex"] = abs(val)
                    break

    current_year = datetime.now().year
    keep = {str(y) for y in range(current_year - 4, current_year + 1)}
    filtered = {yr: data for yr, data in fiscal_years.items() if yr in keep}

    result_dict = {
        "company":      company,
        "ticker":       ticker_symbol,
        "color":        COMPANY_COLORS.get(company, "#64748B"),
        "fiscal_years": dict(sorted(filtered.items())),
        "source":       "yfinance",
        "fetched_at":   datetime.now().isoformat(),
    }

    _cache.set(cache_key, result_dict)
    return HyperscalerCompanyFinancials(**result_dict)


def fetch_all_hyperscaler_financials() -> dict:
    companies = []
    errors    = []

    for company in HYPERSCALER_TICKERS:
        try:
            result = fetch_hyperscaler_financials(company)
            if result.error:
                errors.append({"company": company, "error": result.error})
            else:
                companies.append(result.model_dump())
        except Exception as exc:
            logger.error("Failed to fetch financials for %s: %s", company, exc)
            errors.append({"company": company, "error": str(exc)})

    return {
        "companies":   companies,
        "fetched_at":  datetime.now().isoformat(),
        "source":      "yfinance",
        "errors":      errors or None,
    }


def invalidate_financials_cache(company: Optional[str] = None) -> None:
    if company:
        _cache.delete(f"hyperscaler:financials:{company}")
    else:
        for c in HYPERSCALER_TICKERS:
            _cache.delete(f"hyperscaler:financials:{c}")
