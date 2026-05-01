"""
EMS AI Dynamics service.
Replaces the hardcoded EMS_AI_DYNAMICS dict with live data per company:

- recent_highlights : top 3 headlines from the news service disk cache
- guidance_outlook  : derived from analyze_company_trends (ChromaDB)
- ai_revenue_mix_pct
  ai_revenue_growth_pct : Brave search + LLM extraction from earnings announcements
- investment_focus  : static config (strategic themes, changes infrequently)

All results cached 24 h in a dedicated SimpleCache instance.
Falls back to hardcoded values when Brave is unavailable.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from backend.core.cache import SimpleCache
from backend.core.config import ANALYST_VIEW_BRAVE_ENABLED, BRAVE_API_KEY
from backend.core.llm_client import llm_structured
from backend.rag.web_search import search_web_with_diagnostics

logger = logging.getLogger(__name__)

# 24-hour TTL — earnings metrics update quarterly
_cache: SimpleCache = SimpleCache(default_ttl=86400)

# (company display name → SEC ticker)
EMS_COMPANIES: dict[str, str] = {
    "Flex":      "FLEX",
    "Jabil":     "JBL",
    "Celestica": "CLS",
    "Benchmark": "BHE",
    "Sanmina":   "SANM",
    "Plexus":    "PLXS",
}

# Strategic investment themes — stable, appropriate to keep static
INVESTMENT_FOCUS: dict[str, list[str]] = {
    "Flex":      ["Liquid cooling", "Power modules", "AI server assembly"],
    "Jabil":     ["Cloud infrastructure", "Thermal management", "Advanced packaging"],
    "Celestica": ["HPC/AI servers", "Networking equipment", "Storage solutions"],
    "Benchmark": ["Precision manufacturing", "High-reliability components"],
    "Sanmina":   ["Optical components", "Industrial automation"],
    "Plexus":    ["Product realization", "Complex program ramps", "High-reliability systems"],
}

# Hardcoded fallback — used when Brave is unavailable
_FALLBACK: dict[str, dict] = {
    "Flex":      {"ai_revenue_mix_pct": 28, "ai_revenue_growth_pct": 45, "guidance_summary": "expecting AI/DC to reach 35% of revenue"},
    "Jabil":     {"ai_revenue_mix_pct": 32, "ai_revenue_growth_pct": 52, "guidance_summary": "cloud and AI driving double-digit growth"},
    "Celestica": {"ai_revenue_mix_pct": 42, "ai_revenue_growth_pct": 68, "guidance_summary": "AI/HPS now largest segment"},
    "Benchmark": {"ai_revenue_mix_pct": 15, "ai_revenue_growth_pct": 25, "guidance_summary": "prioritising margin over AI growth"},
    "Sanmina":   {"ai_revenue_mix_pct": 18, "ai_revenue_growth_pct": 30, "guidance_summary": "balanced portfolio approach"},
    "Plexus":    {"ai_revenue_mix_pct": 16, "ai_revenue_growth_pct": 34, "guidance_summary": "selective AI-adjacent participation"},
}

AI_METRICS_QUERIES: dict[str, str] = {
    "Flex":      'Flex Ltd FLEX "AI revenue" OR "data center revenue" mix percentage growth 2025 earnings results',
    "Jabil":     'Jabil JBL "cloud segment" OR "AI revenue" mix percentage growth 2025 earnings results',
    "Celestica": 'Celestica CLS "HPS segment" OR "AI revenue" mix percentage growth 2025 earnings results',
    "Benchmark": 'Benchmark Electronics BHE "AI revenue" OR "advanced computing" percentage growth 2025 earnings',
    "Sanmina":   'Sanmina SANM "AI revenue" OR "communications" mix percentage growth 2025 earnings results',
    "Plexus":    'Plexus PLXS "AI revenue" OR "communications" mix percentage growth 2025 earnings results',
}


class _LLMSchema(BaseModel):
    ai_revenue_mix_pct: Optional[float] = None
    ai_revenue_growth_pct: Optional[float] = None
    guidance_summary: str = ""


async def _fetch_ai_metrics(company: str) -> _LLMSchema:
    """Brave search + LLM extraction for one EMS company's AI revenue metrics."""
    cache_key = f"ems_ai_metrics:{company}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return _LLMSchema(**cached)

    if not ANALYST_VIEW_BRAVE_ENABLED or not BRAVE_API_KEY:
        fb = _FALLBACK.get(company, {})
        return _LLMSchema(**fb)

    query = AI_METRICS_QUERIES.get(company, f"{company} AI revenue mix growth 2025 earnings")
    results, _ = await search_web_with_diagnostics(query, count=8, freshness="py")
    items = [r for r in results if (r.get("url") or "").strip()]

    if not items:
        fb = _FALLBACK.get(company, {})
        return _LLMSchema(**fb)

    context = "\n\n".join(
        f"[{i}] {r['title']}\n{r.get('description', '').strip()}"
        for i, r in enumerate(items[:8], 1)
    )

    extracted: _LLMSchema | None = await asyncio.to_thread(
        llm_structured,
        messages=[{
            "role": "user",
            "content": f"Extract AI/data-centre revenue metrics for {company} from these snippets:\n\n{context}",
        }],
        system=(
            f"Extract AI and data-centre revenue metrics for {company} from earnings snippets. "
            f"Return JSON with:\n"
            f"- ai_revenue_mix_pct: AI/data-centre revenue as % of total revenue (float). "
            f"null if not mentioned.\n"
            f"- ai_revenue_growth_pct: YoY growth of AI/data-centre revenue (float). "
            f"null if not mentioned.\n"
            f"- guidance_summary: one sentence (≤20 words) summarising management's outlook "
            f"on AI/DC growth. Empty string if nothing relevant found."
        ),
        model_key="fast",
        schema=_LLMSchema,
    )

    result = extracted if extracted else _LLMSchema(**_FALLBACK.get(company, {}))

    # Fill any null fields from fallback so the response is always populated
    fb = _FALLBACK.get(company, {})
    if result.ai_revenue_mix_pct is None:
        result.ai_revenue_mix_pct = fb.get("ai_revenue_mix_pct")
    if result.ai_revenue_growth_pct is None:
        result.ai_revenue_growth_pct = fb.get("ai_revenue_growth_pct")
    if not result.guidance_summary:
        result.guidance_summary = fb.get("guidance_summary", "")

    _cache.set(cache_key, result.model_dump())
    return result


def _outlook_label(overall_outlook: str, guidance_summary: str) -> str:
    """Build a human-readable guidance_outlook string."""
    label_map = {
        "positive": "Positive",
        "cautious": "Cautious",
        "neutral":  "Stable",
    }
    label = label_map.get(overall_outlook, "Stable")
    if guidance_summary:
        return f"{label} — {guidance_summary}"
    return label


async def _highlights_for(ticker: str) -> list[str]:
    """Return top 3 news headlines from the company's disk cache (no live fetch)."""
    try:
        from backend.news import service as news_service
        payload = await news_service.get_company_news(ticker, force_refresh=False)
        top = payload.get("top_news") or payload.get("items") or []
        return [item["title"] for item in top[:3] if item.get("title")]
    except Exception as exc:
        logger.warning("Could not load news highlights for %s: %s", ticker, exc)
        return []


async def get_company_dynamics(company: str) -> dict:
    """Build the AI dynamics record for a single EMS company."""
    cache_key = f"ems_ai_dynamics:{company}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    ticker = EMS_COMPANIES.get(company, company.upper())

    # Run news fetch and Brave metrics fetch concurrently
    highlights_task = asyncio.create_task(_highlights_for(ticker))
    metrics_task    = asyncio.create_task(_fetch_ai_metrics(company))

    # ChromaDB trends is synchronous — run in thread
    try:
        from backend.analytics.trends import analyze_company_trends
        trends = await asyncio.to_thread(analyze_company_trends, company)
        overall_outlook = trends.get("overall_outlook", "neutral")
    except Exception as exc:
        logger.warning("Trends analysis failed for %s: %s", company, exc)
        overall_outlook = "neutral"

    highlights = await highlights_task
    metrics    = await metrics_task

    if not highlights:
        fb = _FALLBACK.get(company, {})
        highlights = fb.get("recent_highlights", ["No recent news available"])

    result = {
        "company":                company,
        "ticker":                 ticker,
        "ai_revenue_growth_pct":  round(metrics.ai_revenue_growth_pct or 0, 1),
        "ai_revenue_mix_pct":     round(metrics.ai_revenue_mix_pct or 0, 1),
        "recent_highlights":      highlights,
        "investment_focus":       INVESTMENT_FOCUS.get(company, []),
        "guidance_outlook":       _outlook_label(overall_outlook, metrics.guidance_summary),
    }

    _cache.set(cache_key, result)
    return result


async def get_all_dynamics() -> dict:
    """Build AI dynamics for all 6 EMS companies (concurrent per-company fetches)."""
    cache_key = "ems_ai_dynamics:all"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    tasks = [get_company_dynamics(company) for company in EMS_COMPANIES]
    companies = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for company, res in zip(EMS_COMPANIES.keys(), companies):
        if isinstance(res, Exception):
            logger.error("get_company_dynamics failed for %s: %s", company, res)
            fb = _FALLBACK.get(company, {})
            results.append({
                "company": company,
                "ticker":  EMS_COMPANIES[company],
                **fb,
                "recent_highlights": ["Data temporarily unavailable"],
                "investment_focus":  INVESTMENT_FOCUS.get(company, []),
                "guidance_outlook":  fb.get("guidance_summary", "—"),
            })
        else:
            results.append(res)

    payload = {
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "companies":    results,
    }
    _cache.set(cache_key, payload)
    return payload


def invalidate_cache(company: Optional[str] = None) -> None:
    if company:
        _cache.delete(f"ems_ai_dynamics:{company}")
        _cache.delete(f"ems_ai_metrics:{company}")
    else:
        for c in EMS_COMPANIES:
            _cache.delete(f"ems_ai_dynamics:{c}")
            _cache.delete(f"ems_ai_metrics:{c}")
        _cache.delete("ems_ai_dynamics:all")
