"""
Weekly strategic themes service (Component 9).

Gathers the most recent company intel and analyst summaries from cache,
then calls Claude with the provided executive-synthesis prompt to produce
5 strategic themes. Results are persisted in SQLite so executives can
view history across weeks.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from pydantic import BaseModel

from backend.analyst_view.db import (
    get_all_weekly_themes,
    get_latest_weekly_themes,
    save_weekly_themes,
)
from backend.core.cache import analytics_cache
from backend.core.llm_client import llm_structured

_THEMES_CACHE_KEY = "analyst_view:weekly_themes_live"


class ThemeItem(BaseModel):
    title: str
    supporting_analysts: list[str]
    supporting_companies: list[str]
    explanation: str
    flex_implication: str
    severity: str          # High | Medium | Low


class ThemesResponse(BaseModel):
    themes: list[ThemeItem]


def _build_context(intel_payload: dict, summaries_payload: dict, signals_payload: dict) -> str:
    """Flatten cached data into a text block for Claude."""
    lines: list[str] = []

    # Company intel: consensus + recent actions
    for c in (intel_payload.get("companies") or []):
        ticker = c.get("ticker", "")
        consensus = c.get("consensus", "")
        pt = c.get("price_target", "—")
        actions = c.get("recent_actions") or []
        lines.append(f"{ticker} ({c.get('company','')}): consensus={consensus}, PT={pt}")
        for a in actions[:3]:
            lines.append(f"  • {a}")

    lines.append("")

    # Analyst summaries
    for a in (summaries_payload.get("analysts") or []):
        name = a.get("name", "")
        summary = a.get("summary", "—")
        if summary and summary != "—":
            lines.append(f"[{name}]: {summary}")

    lines.append("")

    # Live feed signals
    for s in (signals_payload.get("results") or [])[:10]:
        title = s.get("title", "")
        desc = s.get("description", "")
        lines.append(f"Signal: {title} — {desc[:120]}")

    return "\n".join(lines)


async def generate_weekly_themes(force: bool = False) -> dict:
    """
    Generate (or return cached) weekly themes.

    If force=False, returns the cached result if it was generated this week.
    If force=True or no entry exists, calls Claude and saves to SQLite.
    """
    # Check in-memory cache first (avoids SQLite on every page load)
    if not force:
        live = analytics_cache.get(_THEMES_CACHE_KEY)
        if live is not None:
            return live

    # Check SQLite for a result generated this week
    if not force:
        row = get_latest_weekly_themes()
        if row:
            generated_at = row["generated_at"]
            # Use it if generated within the last 7 days
            try:
                gen_dt = datetime.fromisoformat(generated_at)
                age_hours = (datetime.now(timezone.utc) - gen_dt).total_seconds() / 3600
                if age_hours < 168:  # 7 days
                    payload = {
                        "themes": json.loads(row["themes_json"]),
                        "generated_at": generated_at,
                        "week_start": row["week_start"],
                        "source": "cache",
                    }
                    analytics_cache.set(_THEMES_CACHE_KEY, payload)
                    return payload
            except Exception:
                pass

    # Gather fresh context from existing caches
    intel_payload = analytics_cache.get("analyst_view:intel:FLEX") or {}
    # Build a combined intel dict by collecting all company caches
    all_intel: list[dict] = []
    for ticker in ["FLEX","JBL","CLS","BHE","SANM","PLXS","AMZN","MSFT","GOOGL","META","AAPL","ORCL"]:
        item = analytics_cache.get(f"analyst_view:intel:{ticker}")
        if item:
            all_intel.append(item)
    intel_combined = {"companies": all_intel}

    summaries_payload = analytics_cache.get("analyst_view:analyst_summaries_v2") or {}
    signals_payload = analytics_cache.get("analyst_view:signals_v1") or {}

    context = _build_context(intel_combined, summaries_payload, signals_payload)

    now = datetime.now(timezone.utc)
    week_start = now.strftime("%Y-%m-%d")

    extracted: ThemesResponse | None = await asyncio.to_thread(
        llm_structured,
        messages=[{
            "role": "user",
            "content": (
                "You are a strategic intelligence analyst for Flex, a global contract manufacturer. "
                "Analyze the following analyst actions, rating changes, and earnings call quotes from "
                "recent weeks across these companies: Flex, Jabil, Celestica, Benchmark Electronics, "
                "Sanmina, Plexus, Amazon, Microsoft, Google, Meta, Apple, Oracle.\n\n"
                f"{context}\n\n"
                "Identify the top 5 strategic themes that Wall Street analysts are currently most "
                "focused on. For each theme: 1) Give it a clear title (max 8 words), 2) List which "
                "analysts and companies support this theme, 3) Explain the theme in 2-3 sentences, "
                "4) State the strategic implication for Flex in one sentence, 5) Rate severity as "
                "High/Medium/Low based on how much it could affect Flex's competitive position."
            ),
        }],
        system=(
            "You are an executive strategic intelligence analyst. "
            "Return JSON with a 'themes' list. Each item must have:\n"
            "- title: string (max 8 words)\n"
            "- supporting_analysts: list of analyst names mentioned\n"
            "- supporting_companies: list of company tickers\n"
            "- explanation: 2-3 sentence theme explanation\n"
            "- flex_implication: one sentence strategic implication for Flex\n"
            "- severity: one of High, Medium, Low"
        ),
        model_key="main",
        schema=ThemesResponse,
        max_tokens=3000,
    )

    if not extracted:
        return {
            "themes": [],
            "generated_at": now.isoformat(),
            "week_start": week_start,
            "source": "error",
            "warning": "LLM extraction failed — try again.",
        }

    themes_list = [t.model_dump() for t in extracted.themes]
    generated_at = now.isoformat()

    save_weekly_themes(week_start, json.dumps(themes_list), generated_at)

    payload = {
        "themes": themes_list,
        "generated_at": generated_at,
        "week_start": week_start,
        "source": "generated",
    }
    analytics_cache.set(_THEMES_CACHE_KEY, payload)
    return payload


def get_themes_history(limit: int = 8) -> list[dict]:
    rows = get_all_weekly_themes(limit)
    result = []
    for row in rows:
        try:
            result.append({
                "id": row["id"],
                "week_start": row["week_start"],
                "themes": json.loads(row["themes_json"]),
                "generated_at": row["generated_at"],
            })
        except Exception:
            pass
    return result
