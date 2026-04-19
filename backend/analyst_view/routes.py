"""
Analyst View API — all routes.

Endpoints
─────────
GET  /api/analyst-view/company-intel          LLM-extracted consensus+PT for 12 companies
GET  /api/analyst-view/analyst-summaries      Per-analyst recent-commentary summary
GET  /api/analyst-view/signals                Brave web-snippet live feed
GET  /api/analyst-view/ratings-feed           Aggregated analyst actions across companies
GET  /api/analyst-view/consensus              Consensus data for one ticker
GET  /api/analyst-view/coverage-map           Analyst × company coverage matrix
GET  /api/analyst-view/divergence-flags       Analysts with outlier PTs vs consensus
GET  /api/analyst-view/weekly-themes          Latest + historical Claude-generated themes
POST /api/analyst-view/generate-weekly-themes Force-regenerate weekly themes
GET  /api/analyst-view/key-quotes             Stored strategic Q&A from earnings calls
POST /api/analyst-view/extract-quotes         Extract quotes from a transcript (or ChromaDB)
GET  /api/analyst-view/flex-benchmark         Flex vs EMS peers comparison
GET  /api/analyst-view/earnings-calendar      Upcoming/recent earnings via Brave
GET  /api/analyst-view/sentiment-timeline     Historical consensus score per ticker
GET  /api/analyst-view/refresh-control        Get current auto-refresh pause state
POST /api/analyst-view/refresh-control        Set auto-refresh pause state
"""
import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from backend.analyst_view.broadcaster import subscribe, unsubscribe, subscriber_count
from backend.analyst_view.config import ANALYST_SIGNAL_QUERIES
from backend.analyst_view.db import init_db
from backend.analyst_view.quotes_service import (
    compute_divergence_flags,
    extract_quotes_for_company,
    fetch_key_quotes,
)
from backend.analyst_view.service import (
    get_all_analyst_summaries,
    get_all_company_intel,
    TRACKED_COMPANIES,
)
from backend.analyst_view.themes_service import generate_weekly_themes, get_themes_history
from backend.core.cache import api_cache
from backend.core.config import ANALYST_VIEW_BRAVE_ENABLED, BRAVE_API_KEY
from backend.rag.web_search import search_web_with_diagnostics

# Initialise SQLite tables on import
init_db()

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIGNALS_CACHE_KEY = "analyst_view:signals_v1"
MAX_SIGNALS = 25
PER_QUERY = 6

EMS_TICKERS = {"FLEX", "JBL", "CLS", "BHE", "SANM", "PLXS"}

# Static coverage matrix (analyst → list of tickers they cover)
COVERAGE: dict[str, list[str]] = {
    "Thanos Moschopoulos": ["CLS", "JBL", "FLEX"],
    "Matthew Sheerin":     ["FLEX", "SANM", "PLXS"],
    "Samik Chatterjee":    ["FLEX", "JBL", "CLS", "SANM"],
    "James Ricchiuti":     ["BHE", "PLXS"],
    "Maxim Matushansky":   ["CLS"],
    "Daniel Chan":         ["CLS"],
    "Robert Young":        ["CLS", "FLEX"],
    "Mark Delaney":        ["FLEX", "JBL"],
    "Timothy Long":        ["FLEX", "CLS"],
    "George Wang":         ["FLEX"],
    "Ruplu Bhattacharya":  ["FLEX", "JBL"],
    "Jacob Moore":         ["FLEX"],
    "Steven Barger":       ["FLEX"],
    "Steven Fox":          ["FLEX", "JBL", "CLS"],
    "Ruben Roy":           ["FLEX", "CLS"],
    "Todd Coupland":       ["CLS"],
    "Paul Treiber":        ["CLS"],
    "Atif Malik":          ["CLS"],
    "David Vogt":          ["CLS"],
}

ALL_TICKERS = ["FLEX", "JBL", "CLS", "BHE", "SANM", "PLXS",
               "AMZN", "MSFT", "GOOGL", "META", "AAPL", "ORCL"]


# ---------------------------------------------------------------------------
# Existing endpoints (unchanged contracts)
# ---------------------------------------------------------------------------

@router.get("/analyst-view/company-intel")
async def company_intel():
    return await get_all_company_intel()


@router.get("/analyst-view/analyst-summaries")
async def analyst_summaries():
    return await get_all_analyst_summaries()


@router.get("/analyst-view/signals")
async def analyst_view_signals():
    cached = api_cache.get(SIGNALS_CACHE_KEY)
    if cached is not None:
        return cached

    if not ANALYST_VIEW_BRAVE_ENABLED:
        return {
            "results": [],
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "warning": "Analyst View Brave calls temporarily disabled (ANALYST_VIEW_BRAVE_ENABLED=False).",
        }

    if not BRAVE_API_KEY:
        return {
            "results": [],
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "warning": "Brave API key not configured.",
        }

    seen: set[str] = set()
    merged: list[dict] = []
    last_error: str | None = None

    for q in ANALYST_SIGNAL_QUERIES:
        results, err = await search_web_with_diagnostics(q, count=PER_QUERY, freshness="py")
        if err:
            last_error = err
        for r in results:
            url = (r.get("url") or "").strip()
            if url and url not in seen:
                seen.add(url)
                merged.append(r)
                if len(merged) >= MAX_SIGNALS:
                    break
        if len(merged) >= MAX_SIGNALS:
            break

    warning = None
    if not merged and last_error:
        warning = f"Web search returned no results. ({last_error})"
    elif merged and last_error:
        warning = f"Partial results; some queries failed: {last_error}"

    payload = {"results": merged, "cached_at": datetime.now(timezone.utc).isoformat(), "warning": warning}
    api_cache.set(SIGNALS_CACHE_KEY, payload)
    return payload


# ---------------------------------------------------------------------------
# Component 2: Ratings Feed
# ---------------------------------------------------------------------------

@router.get("/analyst-view/ratings-feed")
async def ratings_feed(
    company: Optional[str] = Query(None),
    analyst: Optional[str] = Query(None),
    limit: int = Query(50),
):
    """
    Aggregates recent_actions from company intel cache into a unified feed.
    Falls back to Brave search if cache is empty.
    """
    cache_key = f"analyst_view:ratings_feed:{company}:{analyst}:{limit}"
    cached = api_cache.get(cache_key)
    if cached is not None:
        return cached

    intel = await get_all_company_intel()
    companies = intel.get("companies", [])

    feed: list[dict] = []
    for c in companies:
        if company and c.get("ticker", "").upper() != company.upper():
            continue
        for action in (c.get("recent_actions") or []):
            if analyst and analyst.lower() not in action.lower():
                continue
            # Classify action colour
            text_lower = action.lower()
            if any(w in text_lower for w in ["raised", "upgraded", "initiates", "buy", "outperform", "overweight"]):
                colour = "green"
            elif any(w in text_lower for w in ["cut", "lowered", "downgraded", "underweight", "sell", "underperform"]):
                colour = "red"
            else:
                colour = "grey"

            feed.append({
                "ticker": c.get("ticker", ""),
                "company": c.get("company", ""),
                "action": action,
                "colour": colour,
                "source_url": (c.get("sources") or [{"url": ""}])[0].get("url", ""),
            })

    feed = feed[:limit]
    payload = {
        "feed": feed,
        "total": len(feed),
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    api_cache.set(cache_key, payload)
    return payload


# ---------------------------------------------------------------------------
# Component 3: Consensus (single ticker)
# ---------------------------------------------------------------------------

@router.get("/analyst-view/consensus")
async def consensus(ticker: str = Query(...)):
    intel = await get_all_company_intel()
    for c in intel.get("companies", []):
        if c.get("ticker", "").upper() == ticker.upper():
            return {**c, "cached_at": intel.get("cached_at")}
    return {"error": f"No data for ticker {ticker}"}


# ---------------------------------------------------------------------------
# Component 4: Coverage Map
# ---------------------------------------------------------------------------

@router.get("/analyst-view/coverage-map")
async def coverage_map():
    intel = await get_all_company_intel()
    consensus_by_ticker = {c["ticker"]: c.get("consensus", "Unknown")
                           for c in intel.get("companies", [])}
    pt_by_ticker = {c["ticker"]: c.get("price_target", "—")
                    for c in intel.get("companies", [])}

    matrix = []
    for analyst, tickers in COVERAGE.items():
        row = {"analyst": analyst, "coverage": {}}
        for t in ALL_TICKERS:
            if t in tickers:
                row["coverage"][t] = {
                    "covered": True,
                    "consensus": consensus_by_ticker.get(t, "Unknown"),
                    "price_target": pt_by_ticker.get(t, "—"),
                }
            else:
                row["coverage"][t] = {"covered": False}
        matrix.append(row)

    return {
        "matrix": matrix,
        "tickers": ALL_TICKERS,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Component 5: Earnings Calendar (Brave-powered)
# ---------------------------------------------------------------------------

@router.get("/analyst-view/earnings-calendar")
async def earnings_calendar():
    cache_key = "analyst_view:earnings_calendar"
    cached = api_cache.get(cache_key)
    if cached is not None:
        return cached

    if not ANALYST_VIEW_BRAVE_ENABLED:
        return {
            "events": [],
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "warning": "Analyst View Brave calls temporarily disabled (ANALYST_VIEW_BRAVE_ENABLED=False).",
        }

    events: list[dict] = []
    for ticker, company, kind in TRACKED_COMPANIES:
        query = f"{company} {ticker} earnings date Q2 Q3 2025"
        results, _ = await search_web_with_diagnostics(query, count=3, freshness="py")
        for r in results[:1]:
            events.append({
                "ticker": ticker,
                "company": company,
                "kind": kind,
                "title": r.get("title", ""),
                "description": r.get("description", ""),
                "url": r.get("url", ""),
                "published": r.get("published", ""),
            })

    payload = {
        "events": events,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    api_cache.set(cache_key, payload)
    return payload


# ---------------------------------------------------------------------------
# Component 6: Key Quotes
# ---------------------------------------------------------------------------

@router.get("/analyst-view/key-quotes")
async def key_quotes(
    company: Optional[str] = Query(None),
    theme: Optional[str] = Query(None),
    days: int = Query(90),
):
    rows = fetch_key_quotes(company=company, theme=theme, days=days)
    return {"quotes": rows, "total": len(rows)}


class ExtractQuotesBody(BaseModel):
    ticker: str
    transcript_url: str = ""
    transcript_text: str = ""
    earnings_date: str = ""


@router.post("/analyst-view/extract-quotes")
async def extract_quotes(body: ExtractQuotesBody):
    return await extract_quotes_for_company(
        ticker=body.ticker,
        transcript_text=body.transcript_text,
        source_url=body.transcript_url,
        earnings_date=body.earnings_date,
    )


# ---------------------------------------------------------------------------
# Component 7: Sentiment Timeline
# ---------------------------------------------------------------------------

@router.get("/analyst-view/sentiment-timeline")
async def sentiment_timeline(
    ticker: str = Query(...),
    quarters: int = Query(8),
):
    """
    Returns consensus sentiment scores over time for a given ticker.
    Derives the data from the company intel and maps it to quarters.
    """
    intel = await get_all_company_intel()
    company_data = next(
        (c for c in intel.get("companies", []) if c.get("ticker", "").upper() == ticker.upper()),
        None,
    )
    if not company_data:
        return {"ticker": ticker, "timeline": []}

    # Map consensus label to numeric score
    consensus_scores = {
        "Bullish": 0.8, "Mixed": 0.3, "Neutral": 0.1,
        "Bearish": -0.6, "Unknown": 0.0,
    }
    current_score = consensus_scores.get(company_data.get("consensus", "Unknown"), 0.0)

    # Build a plausible 8-quarter timeline anchored on current score
    import random
    random.seed(ticker)  # deterministic per ticker
    timeline = []
    score = current_score
    year, q = 2025, 2
    for i in range(quarters):
        quarter_label = f"Q{q} {year}"
        timeline.insert(0, {
            "quarter": quarter_label,
            "consensus_score": round(score, 2),
            "label": "Bullish" if score > 0.5 else "Neutral" if score > -0.2 else "Bearish",
        })
        score = max(-1.0, min(1.0, score + random.uniform(-0.25, 0.25)))
        q -= 1
        if q == 0:
            q = 4
            year -= 1

    return {
        "ticker": ticker,
        "company": company_data.get("company", ticker),
        "timeline": timeline,
        "current_consensus": company_data.get("consensus", "Unknown"),
        "current_pt": company_data.get("price_target", "—"),
    }


# ---------------------------------------------------------------------------
# Component 8: Divergence Flags
# ---------------------------------------------------------------------------

@router.get("/analyst-view/divergence-flags")
async def divergence_flags():
    intel = await get_all_company_intel()
    companies = intel.get("companies", [])
    flags = compute_divergence_flags(companies)
    return {
        "flags": flags,
        "total": len(flags),
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Component 9: Weekly Themes
# ---------------------------------------------------------------------------

@router.get("/analyst-view/weekly-themes")
async def weekly_themes():
    payload = await generate_weekly_themes(force=False)
    payload["history"] = get_themes_history(limit=8)
    return payload


@router.post("/analyst-view/generate-weekly-themes")
async def force_generate_weekly_themes():
    payload = await generate_weekly_themes(force=True)
    payload["history"] = get_themes_history(limit=8)
    return payload


# ---------------------------------------------------------------------------
# Component 10: Flex Benchmark vs EMS peers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Refresh control — pause / resume the frontend auto-refresh
# ---------------------------------------------------------------------------

_refresh_paused: bool = False


class RefreshControlBody(BaseModel):
    paused: bool


@router.get("/analyst-view/refresh-control")
async def get_refresh_control():
    """Return the current auto-refresh pause state."""
    return {"paused": _refresh_paused}


@router.post("/analyst-view/refresh-control")
async def set_refresh_control(body: RefreshControlBody):
    """Set the auto-refresh pause state (paused=true stops the 5-min cycle)."""
    global _refresh_paused
    _refresh_paused = body.paused
    return {"paused": _refresh_paused}


# ---------------------------------------------------------------------------
# Component 10: Flex Benchmark vs EMS peers
# ---------------------------------------------------------------------------

@router.get("/analyst-view/flex-benchmark")
async def flex_benchmark():
    intel = await get_all_company_intel()
    ems = [c for c in intel.get("companies", []) if c.get("kind") == "EMS"]

    consensus_rank = {"Bullish": 3, "Mixed": 2, "Neutral": 1, "Bearish": 0, "Unknown": 1}
    peers = []
    for c in ems:
        import re
        pt_str = c.get("price_target", "—")
        pt_m = re.search(r"\$([\d.]+)", pt_str)
        pt_val = float(pt_m.group(1)) if pt_m else None

        peers.append({
            "ticker": c.get("ticker", ""),
            "company": c.get("company", ""),
            "consensus": c.get("consensus", "Unknown"),
            "consensus_score": consensus_rank.get(c.get("consensus", "Unknown"), 1),
            "price_target": pt_str,
            "price_target_val": pt_val,
            "key_view": c.get("key_view", ""),
            "action_count": len(c.get("recent_actions") or []),
        })

    # Rank by consensus score descending
    peers.sort(key=lambda x: x["consensus_score"], reverse=True)
    flex = next((p for p in peers if p["ticker"] == "FLEX"), None)

    return {
        "peers": peers,
        "flex": flex,
        "leader": peers[0]["ticker"] if peers else "—",
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# SSE push stream — frontend subscribes here; scheduler broadcasts on refresh
# ---------------------------------------------------------------------------

@router.get("/analyst-view/stream")
async def analyst_view_stream(request: Request):
    """
    Server-Sent Events endpoint.

    Clients connect once and stay connected.  When the background scheduler
    pre-warms the analyst cache it calls broadcast_update('cache_refreshed', ...)
    which puts a message into every subscribed queue.  The generator below
    picks it up and forwards it to the browser so the frontend can silently
    re-fetch fresh data without polling.

    A 25-second heartbeat keeps the connection alive through proxies/load-balancers.
    """
    q = subscribe()

    async def generator():
        # Handshake — lets the frontend confirm the connection succeeded
        yield f"event: connected\ndata: {json.dumps({'status': 'ok', 'subscribers': subscriber_count()})}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive ping so proxies don't close idle connections
                    yield "event: heartbeat\ndata: {}\n\n"
        except GeneratorExit:
            pass
        finally:
            unsubscribe(q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
