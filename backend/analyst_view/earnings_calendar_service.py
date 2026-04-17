"""
EMS Earnings Calendar Service.

Computes upcoming and recent earnings dates for each tracked EMS company
using:
  1. Fiscal-year structure per company (quarter boundaries, typical lag).
  2. Day-of-week conventions (e.g. Sanmina always reports on Monday).
  3. US-holiday avoidance.
  4. Confidence scoring (confirmed / preliminary / estimated).
  5. **Brave web search + LLM extraction** to fetch real confirmed dates
     (triggered manually via POST /api/calendar/sync).

Confirmed dates are persisted in SQLite (`confirmed_earnings` table) so
they survive restarts and only update when the user clicks Refresh.
"""
from __future__ import annotations

import calendar as _cal
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from backend.analyst_view.db import get_all_confirmed_earnings, upsert_confirmed_earning

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Company fiscal-year definitions
# ---------------------------------------------------------------------------

_COMPANIES: list[dict] = [
    {
        "company": "Flex Ltd",
        "ticker": "FLEX",
        "exchange": "NASDAQ",
        "fy_start_month": 4,       # Apr 1 – Mar 31
        "quarters": [
            ("Q1", 6, 30),
            ("Q2", 9, 30),
            ("Q3", 12, 31),
            ("Q4", 3, 31),
        ],
        "lag_days": 36,
        "release_dow": 2,          # Wednesday
        "call_time": "08:30 ET",
        "release_timing": "before_open",
        "ir_url": "https://investors.flex.com/news/default.aspx",
    },
    {
        "company": "Celestica Inc",
        "ticker": "CLS",
        "exchange": "NYSE",
        "fy_start_month": 1,
        "quarters": [
            ("Q1", 3, 31),
            ("Q2", 6, 30),
            ("Q3", 9, 30),
            ("Q4", 12, 31),
        ],
        "lag_days": 27,
        "release_dow": 0,
        "call_time": "08:00 ET",
        "release_timing": "after_close",
        "ir_url": "https://corporate.celestica.com/news-releases",
    },
    {
        "company": "Jabil Inc",
        "ticker": "JBL",
        "exchange": "NYSE",
        "fy_start_month": 9,
        "quarters": [
            ("Q1", 11, 30),
            ("Q2", 2, 28),
            ("Q3", 5, 31),
            ("Q4", 8, 31),
        ],
        "lag_days": 18,
        "release_dow": 2,
        "call_time": "08:30 ET",
        "release_timing": "before_open",
        "ir_url": "https://investors.jabil.com/news/default.aspx",
    },
    {
        "company": "Sanmina Corporation",
        "ticker": "SANM",
        "exchange": "NASDAQ",
        "fy_start_month": 10,
        "quarters": [
            ("Q1", 12, 31),
            ("Q2", 3, 31),
            ("Q3", 6, 30),
            ("Q4", 9, 30),
        ],
        "lag_days": 27,
        "release_dow": 0,
        "call_time": "17:00 ET",
        "release_timing": "after_close",
        "ir_url": "https://ir.sanmina.com/overview/default.aspx",
    },
    {
        "company": "Benchmark Electronics",
        "ticker": "BHE",
        "exchange": "NYSE",
        "fy_start_month": 1,
        "quarters": [
            ("Q1", 3, 31),
            ("Q2", 6, 30),
            ("Q3", 9, 30),
            ("Q4", 12, 31),
        ],
        "lag_days": 29,
        "release_dow": 2,
        "call_time": "17:00 ET",
        "release_timing": "after_close",
        "ir_url": "https://ir.bench.com/news/default.aspx",
    },
    {
        "company": "Plexus Corp",
        "ticker": "PLXS",
        "exchange": "NASDAQ",
        "fy_start_month": 10,
        "quarters": [
            ("Q1", 12, 31),
            ("Q2", 3, 31),
            ("Q3", 6, 30),
            ("Q4", 9, 30),
        ],
        "lag_days": 29,
        "release_dow": 2,
        "call_time": "08:30 ET",
        "release_timing": "after_close",
        "ir_url": "https://investor.plexus.com/overview/default.aspx",
    },
]

# US market holidays (fixed + floating for 2026)
_US_HOLIDAYS_2026 = {
    date(2026, 1, 1),   # New Year
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Presidents Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 7, 3),   # Independence Day (observed)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _period_end_date(month: int, day: int, ref_year: int) -> date:
    max_day = _cal.monthrange(ref_year, month)[1]
    return date(ref_year, month, min(day, max_day))


def _next_weekday(d: date, target_dow: int) -> date:
    diff = (target_dow - d.weekday()) % 7
    if diff == 0:
        diff = 7
    return d + timedelta(days=diff)


def _snap_to_weekday(d: date, target_dow: int | None) -> date:
    if target_dow is None:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d
    candidate = d - timedelta(days=3)
    candidate = _next_weekday(candidate, target_dow)
    if candidate < d - timedelta(days=3):
        candidate += timedelta(days=7)
    return candidate


def _avoid_holidays(d: date) -> date:
    for _ in range(10):
        if d.weekday() >= 5 or d in _US_HOLIDAYS_2026:
            d += timedelta(days=1)
        else:
            break
    return d


ConfidenceLevel = Literal["confirmed", "preliminary", "estimated"]
DataStatus = Literal["confirmed", "estimated", "preliminary"]


def _estimate_release_date(
    period_end: date,
    lag_days: int,
    release_dow: int | None,
) -> date:
    raw = period_end + timedelta(days=lag_days)
    snapped = _snap_to_weekday(raw, release_dow)
    return _avoid_holidays(snapped)


# ---------------------------------------------------------------------------
# Core calendar builder
# ---------------------------------------------------------------------------

def _fiscal_year_for_quarter(fy_start_month: int, period_end: date) -> int:
    if fy_start_month == 1:
        return period_end.year
    if period_end.month >= fy_start_month:
        return period_end.year + 1
    return period_end.year


def build_company_events(
    company_def: dict,
    confirmed_map: dict[tuple[str, str, int], dict],
    horizon_start: date | None = None,
    horizon_end: date | None = None,
) -> list[dict]:
    if horizon_start is None:
        horizon_start = date.today() - timedelta(days=90)
    if horizon_end is None:
        horizon_end = date.today() + timedelta(days=270)

    events: list[dict] = []

    for year in range(horizon_start.year, horizon_end.year + 1):
        for q_label, end_month, end_day in company_def["quarters"]:
            period_end = _period_end_date(end_month, end_day, year)

            release = _estimate_release_date(
                period_end,
                company_def["lag_days"],
                company_def.get("release_dow"),
            )

            fy = _fiscal_year_for_quarter(company_def["fy_start_month"], period_end)
            ticker = company_def["ticker"]

            # Check for confirmed date from SQLite
            override = confirmed_map.get((ticker, q_label, fy))

            if override:
                release = date.fromisoformat(override["release_date"])
                call_date = date.fromisoformat(override["call_date"]) if override.get("call_date") else release
                call_time = override.get("call_time") or company_def["call_time"]
                data_status = "confirmed"
                confidence: ConfidenceLevel = "high"
                source = "ir_announcement"
                ir_url = company_def["ir_url"]
            else:
                call_date = release
                if ticker in ("CLS", "PLXS"):
                    call_date = release + timedelta(days=1)
                    call_date = _avoid_holidays(call_date)
                call_time = company_def["call_time"]
                data_status = "estimated"
                confidence = _confidence_for_date(release)
                source = "historical_pattern"
                ir_url = company_def["ir_url"]

            if release < horizon_start or release > horizon_end:
                continue

            cal_q = (period_end.month - 1) // 3 + 1

            events.append({
                "company": company_def["company"],
                "ticker": ticker,
                "exchange": company_def["exchange"],
                "quarter": f"{q_label} FY{fy}",
                "period_end_date": period_end.isoformat(),
                "release_date": release.isoformat(),
                "release_timing": company_def["release_timing"],
                "call_date": call_date.isoformat(),
                "call_time": call_time,
                "fiscal_year": fy,
                "calendar_quarter": f"Q{cal_q} {period_end.year}",
                "ir_url": ir_url,
                "webcast_url": None,
                "data_status": data_status,
                "confidence": confidence,
                "source": source,
                "last_verified": date.today().isoformat(),
            })

    events.sort(key=lambda e: e["release_date"])
    return events


def _confidence_for_date(release: date) -> ConfidenceLevel:
    days_away = (release - date.today()).days
    if days_away <= 14:
        return "high"
    if days_away <= 56:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Public API — read (no external calls)
# ---------------------------------------------------------------------------

def get_full_earnings_calendar(
    horizon_months: int = 9,
) -> dict:
    """
    Build the full earnings calendar for all EMS companies.
    Reads confirmed dates from SQLite (no external API calls).
    """
    today = date.today()
    horizon_start = today - timedelta(days=90)
    horizon_end = today + timedelta(days=horizon_months * 30)

    # Load confirmed dates from SQLite
    confirmed_map = get_all_confirmed_earnings()

    all_events: list[dict] = []
    for company_def in _COMPANIES:
        events = build_company_events(company_def, confirmed_map, horizon_start, horizon_end)
        all_events.extend(events)

    all_events.sort(key=lambda e: e["release_date"])

    today_str = today.isoformat()
    upcoming = [e for e in all_events if e["release_date"] >= today_str]
    recent = [e for e in all_events if e["release_date"] < today_str]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon": f"{horizon_start.isoformat()} to {horizon_end.isoformat()}",
        "total_events": len(all_events),
        "upcoming": upcoming,
        "recent": list(reversed(recent)),
        "companies": [c["ticker"] for c in _COMPANIES],
    }


# ---------------------------------------------------------------------------
# Sync — Brave search + LLM extraction (costs money, manual only)
# ---------------------------------------------------------------------------

def _next_upcoming_quarters() -> list[dict]:
    """
    For each company, find the NEAREST upcoming quarter (by estimated release date).
    Returns list of {company, ticker, quarter_label, fiscal_year, estimated_date}.
    """
    today = date.today()
    result = []
    for cdef in _COMPANIES:
        # Collect all future events for this company
        candidates = []
        for year in range(today.year, today.year + 2):
            for q_label, end_month, end_day in cdef["quarters"]:
                period_end = _period_end_date(end_month, end_day, year)
                est_release = _estimate_release_date(
                    period_end, cdef["lag_days"], cdef.get("release_dow"),
                )
                if est_release < today - timedelta(days=7):
                    continue
                fy = _fiscal_year_for_quarter(cdef["fy_start_month"], period_end)
                candidates.append({
                    "company": cdef["company"],
                    "ticker": cdef["ticker"],
                    "quarter_label": q_label,
                    "fiscal_year": fy,
                    "estimated_date": est_release.isoformat(),
                    "call_time": cdef["call_time"],
                })
        # Sort by estimated date, take the nearest one
        candidates.sort(key=lambda c: c["estimated_date"])
        if candidates:
            result.append(candidates[0])
    return result


_LLM_SYSTEM = """You are an earnings-date extraction bot.
Given search result snippets about a company's upcoming earnings, extract the EARNINGS CONFERENCE CALL date.

IMPORTANT RULES:
- Extract the CONFERENCE CALL date, NOT the results release date.
  For example if results are released April 27 after close and the conference call is April 28 at 8am, return April 28.
- The date MUST match the specific quarter requested (e.g. Q4 FY2026, Q1 FY2026). Do NOT return dates for a different quarter.
- If multiple quarters are mentioned, only extract the one matching the requested quarter.
- If you cannot find a date for the EXACT quarter requested, respond with null.

Respond ONLY with valid JSON, no markdown:
{"date": "YYYY-MM-DD", "call_time": "HH:MM ET", "source_url": "https://..."}

If you cannot determine the date for the requested quarter, respond: {"date": null, "call_time": null, "source_url": null}
"""


async def sync_confirmed_dates_from_web() -> dict:
    """
    For each company's next upcoming quarter(s):
      1. Search Brave for the earnings date announcement.
      2. Use LLM (fast model) to extract the confirmed date from snippets.
      3. Store in SQLite.

    Returns summary of what was found/updated.
    """
    from backend.core.llm_client import llm_complete
    from backend.rag.web_search import search_web_with_diagnostics

    quarters = _next_upcoming_quarters()
    updated = []
    errors = []

    for q in quarters:
        # Search with company name for better results
        fy_label = f"fiscal {q['fiscal_year']}" if q['fiscal_year'] >= 2026 else f"FY{q['fiscal_year']}"
        query = f"{q['company']} {q['ticker']} {q['quarter_label']} {fy_label} earnings call date conference {q['fiscal_year']}"
        try:
            results, err = await search_web_with_diagnostics(query, count=5, freshness="pm")
            if not results:
                # Retry without freshness filter
                results, err = await search_web_with_diagnostics(query, count=5)

            if not results:
                errors.append(f"{q['ticker']} {q['quarter_label']}: no search results")
                continue

            # Build snippet text for LLM
            snippets = []
            for r in results[:5]:
                title = r.get("title", "")
                desc = r.get("description", "")
                url = r.get("url", "")
                snippets.append(f"Title: {title}\nSnippet: {desc}\nURL: {url}")
            snippet_text = "\n\n".join(snippets)

            user_msg = (
                f"Company: {q['company']} ({q['ticker']})\n"
                f"I need the CONFERENCE CALL date for EXACTLY this quarter: {q['quarter_label']} FY{q['fiscal_year']}\n"
                f"The expected date is around {q['estimated_date']} (±2 weeks). "
                f"Only return a date that is close to this range and matches the correct quarter.\n"
                f"Do NOT return a date for any other quarter. If the search results only mention other quarters, return null.\n\n"
                f"Search results:\n{snippet_text}"
            )

            llm_response = llm_complete(
                messages=[{"role": "user", "content": user_msg}],
                system=_LLM_SYSTEM,
                model_key="fast",
                max_tokens=200,
            )

            # Parse LLM JSON response
            parsed = _parse_llm_response(llm_response)
            if not parsed or not parsed.get("date"):
                errors.append(f"{q['ticker']} {q['quarter_label']}: LLM could not extract date")
                continue

            # Validate date format
            try:
                confirmed_date = date.fromisoformat(parsed["date"])
            except ValueError:
                errors.append(f"{q['ticker']} {q['quarter_label']}: invalid date '{parsed['date']}'")
                continue

            # Sanity check: confirmed date should be within 30 days of estimate
            est = date.fromisoformat(q["estimated_date"])
            if abs((confirmed_date - est).days) > 30:
                errors.append(
                    f"{q['ticker']} {q['quarter_label']}: extracted {confirmed_date} too far from estimate {est}, skipping"
                )
                continue

            call_time = parsed.get("call_time") or q["call_time"]
            source_url = parsed.get("source_url") or ""

            upsert_confirmed_earning(
                ticker=q["ticker"],
                quarter=q["quarter_label"],
                fiscal_year=q["fiscal_year"],
                release_date=confirmed_date.isoformat(),
                call_date=confirmed_date.isoformat(),
                call_time=call_time,
                source_url=source_url,
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )

            updated.append({
                "ticker": q["ticker"],
                "quarter": f"{q['quarter_label']} FY{q['fiscal_year']}",
                "confirmed_date": confirmed_date.isoformat(),
                "call_time": call_time,
                "source_url": source_url,
            })

            log.info("Confirmed %s %s FY%s → %s", q["ticker"], q["quarter_label"], q["fiscal_year"], confirmed_date)

        except Exception as exc:
            errors.append(f"{q['ticker']} {q['quarter_label']}: {exc}")
            log.exception("Failed to sync %s %s", q["ticker"], q["quarter_label"])

    return {
        "synced": True,
        "updated": updated,
        "updated_count": len(updated),
        "errors": errors,
        "searched_quarters": len(quarters),
    }


def _parse_llm_response(text: str) -> dict | None:
    """Extract JSON dict from LLM response, tolerant of markdown fences."""
    if not text:
        return None
    # Strip markdown code fences
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        m = re.search(r"\{[^}]+\}", text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return None
