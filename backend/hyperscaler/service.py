import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from backend.hyperscaler import cache as cache_mod
from backend.hyperscaler.models import (
    Big5CapexResponse,
    Big5CapexSummaryResponse,
    HyperscalerCompany,
    StargateProject,
)
from backend.hyperscaler.questions import BIG5_CAPEX_QUESTION

logger = logging.getLogger(__name__)

COMPANY_CONFIG = [
    {"ticker": "AMZN",  "name": "Amazon",    "color": "#FF9900"},
    {"ticker": "MSFT",  "name": "Microsoft", "color": "#00A4EF"},
    {"ticker": "GOOGL", "name": "Alphabet",  "color": "#4285F4"},
    {"ticker": "META",  "name": "Meta",      "color": "#0866FF"},
    {"ticker": "ORCL",  "name": "Oracle",    "color": "#F80000"},
]

CAPEX_2026_HIGHLIGHT_COLOR = "#F59E0B"

_TICKER_MAP = {c["ticker"]: c for c in COMPANY_CONFIG}

_TICKER_ALIASES = {
    "GOOG": "GOOGL",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "MICROSOFT": "MSFT",
    "FACEBOOK": "META",
    "ORACLE": "ORCL",
}


def _extract_json(text: str) -> str:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        candidate = match.group(1).strip()
    else:
        start = text.find("{")
        candidate = text[start:] if start != -1 else text

    # Strip "sources" array before parsing — it can be large and cause truncation
    candidate = re.sub(r',\s*"sources"\s*:\s*\[[\s\S]*?\]', '', candidate)
    return candidate


def build_response_from_cache() -> Big5CapexResponse:
    raw = cache_mod.read_view_model()
    if raw is None:
        return Big5CapexResponse(source_status="missing_cache")
    return _normalize(raw)


def _get_yfinance_2025_capex() -> dict[str, Optional[float]]:
    """Fetch 2025 actual CapEx from yfinance for all hyperscalers."""
    try:
        from backend.hyperscaler.financials import fetch_hyperscaler_financials, HYPERSCALER_TICKERS
        result = {}
        for company_name, ticker in HYPERSCALER_TICKERS.items():
            data = fetch_hyperscaler_financials(company_name)
            capex = None
            if not data.error and data.fiscal_years:
                fy2025 = data.fiscal_years.get("2025")
                if fy2025:
                    capex = fy2025.capex
            result[ticker] = capex
        return result
    except Exception as exc:
        logger.warning("Failed to fetch yfinance 2025 CapEx: %s", exc)
        return {}


def _parse_capex(value) -> Optional[float]:
    """Parse CapEx value: float passthrough, range string → midpoint, text → extracted number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        range_match = re.search(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)", value)
        if range_match:
            lo, hi = float(range_match.group(1)), float(range_match.group(2))
            return round((lo + hi) / 2, 1)
        num_match = re.search(r"(\d+(?:\.\d+)?)", value)
        if num_match:
            return float(num_match.group(1))
    return None


def _parse_yoy(value) -> Optional[float]:
    """Parse YoY growth: float passthrough, extract first number from string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        num_match = re.search(r"(\d+(?:\.\d+)?)", value)
        if num_match:
            return float(num_match.group(1))
    return None


def _normalize(raw: dict, yfinance_2025: Optional[dict] = None) -> Big5CapexResponse:
    if yfinance_2025 is None:
        yfinance_2025 = _get_yfinance_2025_capex()

    companies = []
    for item in raw.get("companies", []):
        ticker = item.get("ticker", "").upper()
        ticker = _TICKER_ALIASES.get(ticker, ticker)
        config = _TICKER_MAP.get(ticker, {})

        # 2025: always use yfinance — it is the authoritative source for historical actuals
        capex_2025 = yfinance_2025.get(ticker)

        # 2026: use Gemini, but discard if it looks like a 2025 figure (≤ yfinance 2025 actual)
        capex_2026_raw = _parse_capex(item.get("capex_2026_billions"))
        if capex_2026_raw is not None and capex_2025 is not None and capex_2026_raw <= capex_2025:
            logger.warning("Discarding Gemini 2026 CapEx for %s ($%sB) — not greater than yfinance 2025 ($%sB)", ticker, capex_2026_raw, capex_2025)
            capex_2026 = None
        else:
            capex_2026 = capex_2026_raw

        # Recalculate YoY from authoritative sources only
        if capex_2026 is not None and capex_2025 is not None and capex_2025 > 0:
            yoy = round((capex_2026 - capex_2025) / capex_2025 * 100, 1)
        else:
            yoy = None

        companies.append(HyperscalerCompany(
            name=item.get("name") or config.get("name", ticker),
            ticker=ticker,
            color=config.get("color", "#64748B"),
            capex_2026_billions=capex_2026,
            capex_2025_billions=capex_2025,
            yoy_growth_pct=yoy,
            ai_focus_areas=item.get("ai_focus_areas") or [],
            key_metrics=item.get("key_metrics") or {},
            recent_announcements=item.get("recent_announcements") or [],
        ))

    sg = raw.get("stargate_project") or {}
    stargate = StargateProject(
        total_investment_billions=sg.get("total_investment_billions"),
        timeline=sg.get("timeline") or "",
        partners=sg.get("partners") or [],
        planned_capacity_gw=sg.get("planned_capacity_gw"),
        locations=sg.get("locations") or [],
    )

    valid_capex = [c.capex_2026_billions for c in companies if c.capex_2026_billions is not None]
    total = round(sum(valid_capex), 1) if valid_capex else None

    return Big5CapexResponse(
        companies=companies,
        last_updated=raw.get("last_updated", ""),
        source=raw.get("source", "Gemini API"),
        source_status=raw.get("source_status", "gemini_cached"),
        total_2026_capex_billions=total,
        stargate_project=stargate,
    )


async def refresh_from_gemini() -> Big5CapexResponse:
    from backend.hyperscaler.gemini_client import ask_gemini_with_search

    raw_text = await ask_gemini_with_search(BIG5_CAPEX_QUESTION)

    try:
        parsed = json.loads(_extract_json(raw_text))
        parsed.pop("sources", None)
    except Exception as exc:
        logger.error("Failed to parse Gemini response as JSON: %s", exc)
        logger.debug("Gemini raw response: %s", raw_text[:500])
        raise ValueError(f"Gemini returned non-JSON response: {exc}") from exc

    cache_mod.write_raw({"raw_text": raw_text, "parsed": parsed, "fetched_at": datetime.now(timezone.utc).isoformat()})

    # Read old cache BEFORE overwriting — preserve 2025 actuals and previous 2026 if Gemini returns null
    prev = cache_mod.read_view_model()
    preserved_2025: dict[str, Optional[float]] = {}
    preserved_2026: dict[str, Optional[float]] = {}
    if prev:
        for c in prev.get("companies", []):
            t = c.get("ticker")
            v25 = c.get("capex_2025_billions")
            v26 = c.get("capex_2026_billions")
            if t and v25 is not None:
                preserved_2025[t] = v25
            if t and v26 is not None:
                preserved_2026[t] = v26

    # Backfill null 2026 values from previous cache
    for company in parsed.get("companies", []):
        t = company.get("ticker", "").upper()
        t = _TICKER_ALIASES.get(t, t)
        if company.get("capex_2026_billions") is None and t in preserved_2026:
            company["capex_2026_billions"] = preserved_2026[t]
            logger.info("Backfilled 2026 CapEx for %s from previous cache: $%sB", t, preserved_2026[t])

    now = datetime.now()
    payload = {
        "last_updated": now.strftime("%Y-%m-%d"),
        "source": "Gemini API",
        "source_status": "gemini_cached",
        "companies": parsed.get("companies", []),
        "stargate_project": parsed.get("stargate_project", {}),
    }
    cache_mod.write_view_model(payload)

    return _normalize(payload, yfinance_2025=preserved_2025 or _get_yfinance_2025_capex())


def build_summary(response: Big5CapexResponse) -> Big5CapexSummaryResponse:
    valid_growth = [c.yoy_growth_pct for c in response.companies if c.yoy_growth_pct is not None]
    avg_growth = round(sum(valid_growth) / len(valid_growth), 1) if valid_growth else None

    return Big5CapexSummaryResponse(
        total_2026_capex_billions=response.total_2026_capex_billions,
        avg_yoy_growth_pct=avg_growth,
        company_count=len(response.companies),
        source_status=response.source_status,
    )
