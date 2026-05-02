"""
Current-year CapEx guidance fetcher for EMS companies.
Uses Gemini + Google Search grounding (same pattern as hyperscaler/service.py).
Results are cached to disk; cache is only cleared via the DELETE endpoint.
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_DIR = Path("data/company_capex")

EMS_TICKER_MAP = {
    "Flex":      "FLEX",
    "Jabil":     "JBL",
    "Celestica": "CLS",
    "Benchmark": "BHE",
    "Sanmina":   "SANM",
    "Plexus":    "PLXS",
}

EMS_FISCAL_YEAR_END = {
    "Flex":      "March",
    "Jabil":     "August",
    "Celestica": "December",
    "Benchmark": "December",
    "Sanmina":   "September",
    "Plexus":    "September",
}


def _cache_path(company: str) -> Path:
    ticker = EMS_TICKER_MAP.get(company, company.upper())
    return _CACHE_DIR / f"{ticker}_capex_guidance.json"


def read_guidance_cache(company: str) -> Optional[dict]:
    path = _cache_path(company)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.error("Failed to read capex guidance cache for %s: %s", company, exc)
        return None


def write_guidance_cache(company: str, data: dict) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(company)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        logger.error("Failed to write capex guidance cache for %s: %s", company, exc)


def clear_guidance_cache(company: str) -> None:
    try:
        _cache_path(company).unlink(missing_ok=True)
    except Exception as exc:
        logger.error("Failed to clear capex guidance cache for %s: %s", company, exc)


def _build_prompt(company: str) -> str:
    ticker = EMS_TICKER_MAP.get(company, company.upper())
    fy_end = EMS_FISCAL_YEAR_END.get(company, "December")
    current_year = datetime.now().year
    return f"""Search for the most recent fiscal year capital expenditure (CapEx) data for {company} ({ticker}), an electronics manufacturing services (EMS) company. Their fiscal year ends in {fy_end}.

Find either:
1. The full-year actual CapEx for the fiscal year ending in {fy_end} {current_year} (if already reported), OR
2. The full-year CapEx guidance or outlook for fiscal year {current_year} (if the year is not yet complete).

Use reliable sources only:
- Form 8-K earnings release
- Latest 10-Q or 10-K filing
- Earnings call transcript
- Investor presentation or annual meeting

Return JSON only. No markdown. No explanation.
{{
  "company": "{company}",
  "ticker": "{ticker}",
  "fiscal_year": "FY{current_year}",
  "capex_millions": null,
  "value_type": "actual | guidance | range_midpoint | ytd_annualized | missing",
  "range_low_millions": null,
  "range_high_millions": null,
  "source_title": "",
  "source_date": "",
  "quote": "",
  "confidence": 0
}}

Rules:
- Return capex_millions in USD millions (not billions).
- If management gives a range, return the midpoint in capex_millions and fill range_low_millions / range_high_millions.
- If only year-to-date CapEx is available, mark value_type as "ytd_annualized" and set confidence below 60.
- If no reliable CapEx figure is found, set value_type to "missing" and capex_millions to null.
- Do not estimate or fabricate. Do not include a sources field.
"""


def _extract_json(text: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    candidate = match.group(1).strip() if match else text[text.find("{"):]
    candidate = re.sub(r',\s*"sources"\s*:\s*\[[\s\S]*?\]', "", candidate)
    return json.loads(candidate)


async def fetch_capex_guidance(company: str) -> dict:
    """Call Gemini with Google Search grounding to get current-year CapEx guidance."""
    from backend.hyperscaler.gemini_client import ask_gemini_with_search

    prompt = _build_prompt(company)
    raw_text = await ask_gemini_with_search(prompt)
    logger.info("Gemini raw response for %s capex guidance: %.200s", company, raw_text)

    try:
        parsed = _extract_json(raw_text)
    except Exception as exc:
        logger.error("Failed to parse Gemini JSON for %s: %s\nRaw: %s", company, exc, raw_text[:500])
        return {"company": company, "value_type": "missing", "capex_millions": None, "error": str(exc)}

    # Normalise: ensure capex_millions is a float or None
    try:
        val = parsed.get("capex_millions")
        parsed["capex_millions"] = round(float(val), 2) if val is not None else None
    except (TypeError, ValueError):
        parsed["capex_millions"] = None

    parsed["fetched_at"] = datetime.now().isoformat()
    write_guidance_cache(company, parsed)
    return parsed
