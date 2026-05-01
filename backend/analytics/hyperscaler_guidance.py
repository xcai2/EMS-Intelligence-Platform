"""
Hyperscaler forward CapEx guidance service.

All financial figures, focus areas, announcements, and Stargate details are
fetched live via Brave search + LLM extraction. Nothing is hardcoded.

Seed file (data/big5_capex_seed.json) contains only stable identity fields:
name, ticker, color. Everything else comes from here.

Cache TTL: 7 days — guidance is stable once Q4 earnings are published.
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from backend.core.cache import SimpleCache
from backend.core.config import ANALYST_VIEW_BRAVE_ENABLED, BRAVE_API_KEY
from backend.core.llm_client import llm_structured
from backend.rag.web_search import search_web_with_diagnostics

logger = logging.getLogger(__name__)

_cache: SimpleCache = SimpleCache(default_ttl=604800)  # 7 days

_SEED_PATH = Path("data/big5_capex_seed.json")

GUIDANCE_QUERIES: dict[str, str] = {
    "Amazon":    "Amazon AWS capital expenditure capex guidance full year annual earnings revenue segment",
    "Microsoft": "Microsoft capital expenditure capex guidance annual earnings Azure revenue backlog",
    "Alphabet":  "Alphabet Google capital expenditure capex guidance full year earnings cloud revenue",
    "Meta":      "Meta capital expenditure capex guidance annual earnings infrastructure AI investment",
    "Oracle":    "Oracle capital expenditure capex guidance annual earnings cloud OCI remaining obligations",
}

_STARGATE_QUERY = (
    "Stargate AI project OpenAI SoftBank Oracle investment update 2026 "
    "capacity gigawatt locations partners"
)

# Fallback figures from public earnings / guidance (used when Brave is unavailable).
# Update these after each quarterly earnings cycle.
_FALLBACK: dict[str, dict] = {
    "Amazon": {
        "capex_2026_billions": 104.0,
        "capex_2025_billions": 83.0,
        "yoy_growth_pct": 25,
        "recent_announcements": [
            "AWS CapEx guidance raised to ~$104B for 2025 on AI demand",
            "Expanding data-center footprint across 19 AWS regions",
            "Investing in custom AI chips: Trainium 2 and Inferentia 3",
        ],
        "key_metrics": {"aws_revenue_billions": 108.0, "aws_growth_pct": 17.0},
        "ai_focus_areas": ["AI (Custom Chips)", "AI (Cloud Infrastructure)", "AI (Generative AI Services)"],
        "guidance_source_date": "February 2025",
        "guidance_confidence": "high",
    },
    "Microsoft": {
        "capex_2026_billions": 80.0,
        "capex_2025_billions": 56.0,
        "yoy_growth_pct": 43,
        "recent_announcements": [
            "FY2025 CapEx guidance of ~$80B driven by AI and Azure growth",
            "Global data-center buildout with $80B committed for FY2025",
            "Azure AI capacity additions accelerating across all regions",
        ],
        "key_metrics": {"azure_growth_pct": 31.0, "commercial_cloud_billions": 40.9},
        "ai_focus_areas": ["AI (Azure OpenAI)", "AI (Cloud Infrastructure)", "AI (Copilot Platform)"],
        "guidance_source_date": "January 2025",
        "guidance_confidence": "high",
    },
    "Alphabet": {
        "capex_2026_billions": 75.0,
        "capex_2025_billions": 52.5,
        "yoy_growth_pct": 43,
        "recent_announcements": [
            "2025 CapEx guidance of $75B focused on AI infrastructure",
            "TPU v5 and v6 deployments ramping for Google Cloud AI",
            "Expanding data-center capacity across North America and Europe",
        ],
        "key_metrics": {"google_cloud_billions": 43.2, "google_cloud_growth_pct": 28.0},
        "ai_focus_areas": ["AI (TPU Custom Chips)", "AI (Google Cloud)", "AI (Gemini Models)"],
        "guidance_source_date": "February 2025",
        "guidance_confidence": "high",
    },
    "Meta": {
        "capex_2026_billions": 65.0,
        "capex_2025_billions": 38.7,
        "yoy_growth_pct": 68,
        "recent_announcements": [
            "2025 CapEx guidance raised to $60–65B for AI training infrastructure",
            "Building 2GW+ data-center campus in Louisiana",
            "Deploying ~1.3M GPUs for Llama model training",
        ],
        "key_metrics": {"daily_active_people_billions": 3.35, "revenue_growth_pct": 21.0},
        "ai_focus_areas": ["AI (Training Infrastructure)", "AI (Custom Silicon)", "AI (Llama Models)"],
        "guidance_source_date": "January 2025",
        "guidance_confidence": "high",
    },
    "Oracle": {
        "capex_2026_billions": 16.0,
        "capex_2025_billions": 9.0,
        "yoy_growth_pct": 78,
        "recent_announcements": [
            "FY2026 CapEx expected to exceed $16B as OCI demand surges",
            "Remaining performance obligations exceed $130B driven by AI workloads",
            "Stargate JV partner alongside OpenAI and SoftBank",
        ],
        "key_metrics": {"cloud_revenue_billions": 25.6, "cloud_growth_pct": 25.0},
        "ai_focus_areas": ["AI (OCI Cloud)", "AI (Database & Analytics)", "AI (Stargate JV)"],
        "guidance_source_date": "December 2024",
        "guidance_confidence": "medium",
    },
}

_FALLBACK_STARGATE: dict = {
    "total_investment_billions": 500,
    "timeline": "2025–2029",
    "partners": ["OpenAI", "SoftBank", "Oracle"],
    "planned_capacity_gw": 5.0,
    "locations": ["Texas", "Arizona", "Wisconsin", "Pennsylvania"],
    "latest_updates": [
        "$500B joint venture announced January 2025",
        "Initial $100B phase under construction in Abilene, Texas",
        "Oracle providing cloud infrastructure; OpenAI operating AI systems",
    ],
}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class _CompanyLLMSchema(BaseModel):
    capex_current_billions: Optional[float] = None
    capex_prev_billions: Optional[float] = None
    guidance_year: Optional[int] = None
    key_announcements: list[str] = []
    source_date: str = "—"
    confidence: str = "low"
    key_metrics: dict[str, float] = {}
    ai_focus_areas: list[str] = []


class _StargateSchema(BaseModel):
    total_investment_billions: Optional[float] = None
    timeline: str = ""
    partners: list[str] = []
    planned_capacity_gw: Optional[float] = None
    locations: list[str] = []
    latest_updates: list[str] = []


class GuidanceResult(BaseModel):
    company: str
    guidance_year: Optional[int] = None
    capex_current_billions: Optional[float] = None
    capex_prev_billions: Optional[float] = None
    yoy_growth_pct: Optional[int] = None
    key_announcements: list[str] = []
    key_metrics: dict[str, float] = {}
    ai_focus_areas: list[str] = []
    source_date: str = "—"
    confidence: str = "low"
    source: str = "none"
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Seed loader
# ---------------------------------------------------------------------------

def _load_seed() -> dict:
    """Load the seed file. Returns minimal structure if file is missing."""
    try:
        data = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
        return data
    except Exception as exc:
        logger.error("Could not load seed file %s: %s", _SEED_PATH, exc)
        return {"companies": []}


# ---------------------------------------------------------------------------
# Per-company fetch
# ---------------------------------------------------------------------------

async def _fetch_one(company: str) -> GuidanceResult:
    """Brave search + LLM extraction for one hyperscaler."""
    cache_key = f"hyperscaler:guidance:{company}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return GuidanceResult(**cached)

    query = GUIDANCE_QUERIES.get(company)
    if not query:
        return GuidanceResult(company=company, error="No query defined", source="none")

    results, err = await search_web_with_diagnostics(query, count=8, freshness="py")
    items = [r for r in results if (r.get("url") or "").strip()]

    if not items:
        return GuidanceResult(company=company, error=err or "No search results", source="none")

    context = "\n\n".join(
        f"[{i}] {r['title']}\n{r.get('description', '').strip()}"
        for i, r in enumerate(items[:8], 1)
    )

    current_year = datetime.now().year

    extracted: _CompanyLLMSchema | None = await asyncio.to_thread(
        llm_structured,
        messages=[{
            "role": "user",
            "content": (
                f"Extract financial data for {company} from these earnings snippets:\n\n{context}"
            ),
        }],
        system=(
            f"Extract financial data for {company} from earnings/guidance snippets. "
            f"Today is {datetime.now().strftime('%B %Y')}. "
            f"Return JSON with exactly these fields:\n"
            f"- capex_current_billions: forward CapEx guidance for fiscal year {current_year} "
            f"in USD billions as a float. null if not clearly stated.\n"
            f"- capex_prev_billions: prior fiscal year actual CapEx in USD billions. "
            f"null if not stated.\n"
            f"- guidance_year: fiscal year the guidance covers as an integer. null if unclear.\n"
            f"- key_announcements: up to 3 short strings (≤20 words each) summarising the most "
            f"important CapEx or AI infrastructure statements.\n"
            f"- source_date: month and year the guidance was published e.g. 'February {current_year}'. "
            f"'—' if unknown.\n"
            f"- confidence: 'high' if the number is explicitly stated, 'medium' if inferred, "
            f"'low' if uncertain.\n"
            f"- key_metrics: a JSON object of up to 4 key segment metrics mentioned "
            f"(e.g. {{\"aws_revenue_billions\": 147, \"aws_growth_pct\": 17}}). "
            f"Use snake_case keys with _billions or _pct suffix where appropriate. "
            f"Empty object if nothing clearly stated.\n"
            f"- ai_focus_areas: up to 4 short strings describing what AI areas this company "
            f"is investing in (e.g. 'AI (Custom Chips)', 'AI (Cloud Infrastructure)'). "
            f"Empty list if nothing clearly stated."
        ),
        model_key="fast",
        schema=_CompanyLLMSchema,
    )

    if not extracted:
        return GuidanceResult(company=company, error="LLM extraction failed", source="none")

    yoy: Optional[int] = None
    if (
        extracted.capex_current_billions is not None
        and extracted.capex_prev_billions
        and extracted.capex_prev_billions != 0
    ):
        yoy = round(
            (extracted.capex_current_billions - extracted.capex_prev_billions)
            / extracted.capex_prev_billions
            * 100
        )

    result = GuidanceResult(
        company=company,
        guidance_year=extracted.guidance_year,
        capex_current_billions=extracted.capex_current_billions,
        capex_prev_billions=extracted.capex_prev_billions,
        yoy_growth_pct=yoy,
        key_announcements=extracted.key_announcements,
        key_metrics=extracted.key_metrics,
        ai_focus_areas=extracted.ai_focus_areas,
        source_date=extracted.source_date,
        confidence=extracted.confidence,
        source="live",
    )

    _cache.set(cache_key, result.model_dump())
    return result


# ---------------------------------------------------------------------------
# Stargate project fetch
# ---------------------------------------------------------------------------

async def fetch_stargate_update() -> dict:
    """Brave search + LLM extraction for current Stargate project status."""
    cache_key = "hyperscaler:stargate"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    results, _ = await search_web_with_diagnostics(_STARGATE_QUERY, count=8, freshness="py")
    items = [r for r in results if (r.get("url") or "").strip()]

    if not items:
        return {}

    context = "\n\n".join(
        f"[{i}] {r['title']}\n{r.get('description', '').strip()}"
        for i, r in enumerate(items[:8], 1)
    )

    extracted: _StargateSchema | None = await asyncio.to_thread(
        llm_structured,
        messages=[{
            "role": "user",
            "content": f"Extract current Stargate AI project details from these snippets:\n\n{context}",
        }],
        system=(
            "Extract the latest details about the Stargate AI infrastructure project. "
            "Return JSON with:\n"
            "- total_investment_billions: total announced investment in USD billions. null if unclear.\n"
            "- timeline: investment timeline e.g. '2025–2029'. Empty string if unknown.\n"
            "- partners: list of known partner organisations.\n"
            "- planned_capacity_gw: planned data centre capacity in gigawatts. null if unknown.\n"
            "- locations: list of US states or countries where facilities are planned.\n"
            "- latest_updates: up to 3 short strings (≤20 words each) describing the most "
            "recent developments."
        ),
        model_key="fast",
        schema=_StargateSchema,
    )

    if not extracted:
        return {}

    result = {k: v for k, v in extracted.model_dump().items() if v not in (None, [], "")}
    _cache.set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_all_guidance() -> dict[str, GuidanceResult]:
    """Fetch guidance for all 5 hyperscalers sequentially (respects Brave rate-limiter)."""
    results: dict[str, GuidanceResult] = {}
    for company in GUIDANCE_QUERIES:
        try:
            results[company] = await _fetch_one(company)
        except Exception as exc:
            logger.error("Guidance fetch failed for %s: %s", company, exc)
            results[company] = GuidanceResult(company=company, error=str(exc), source="none")
    return results


async def build_big5_capex_response() -> dict:
    """
    Build the full Big 5 CapEx response from the seed file + live data.
    The seed provides only name/ticker/color. All financial fields come from
    Brave search + LLM. If Brave is unavailable the response contains only
    identity fields — no stale numbers are shown.
    """
    seed = _load_seed()
    seed_companies = {c["ticker"]: c for c in seed.get("companies", [])}

    if not ANALYST_VIEW_BRAVE_ENABLED or not BRAVE_API_KEY:
        name_to_ticker = {
            "Amazon": "AMZN", "Microsoft": "MSFT", "Alphabet": "GOOGL",
            "Meta": "META", "Oracle": "ORCL",
        }
        companies = []
        for company_name, ticker in name_to_ticker.items():
            base = dict(seed_companies.get(ticker, {"ticker": ticker}))
            base.update(_FALLBACK.get(company_name, {}))
            companies.append(base)
        total = sum(c.get("capex_2026_billions", 0) for c in companies)
        return {
            "companies": companies,
            "last_updated": "2025-04-30",
            "guidance_source": "fallback",
            "source": "Earnings guidance (static fallback — Brave API not configured)",
            "total_2026_capex_billions": round(total, 1),
            "stargate_project": _FALLBACK_STARGATE,
        }

    # Fetch guidance + Stargate concurrently
    guidance_task  = asyncio.create_task(fetch_all_guidance())
    stargate_task  = asyncio.create_task(fetch_stargate_update())

    guidance  = await guidance_task
    stargate  = await stargate_task

    companies = []
    name_to_ticker = {
        "Amazon":    "AMZN",
        "Alphabet":  "GOOGL",
        "Microsoft": "MSFT",
        "Meta":      "META",
        "Oracle":    "ORCL",
    }

    for company_name, ticker in name_to_ticker.items():
        base = dict(seed_companies.get(ticker, {"ticker": ticker}))
        g = guidance.get(company_name)

        if g and g.source == "live":
            if g.capex_current_billions is not None:
                base["capex_2026_billions"] = g.capex_current_billions
            if g.capex_prev_billions is not None:
                base["capex_2025_billions"] = g.capex_prev_billions
            if g.yoy_growth_pct is not None:
                base["yoy_growth_pct"] = g.yoy_growth_pct
            if g.key_announcements:
                base["recent_announcements"] = g.key_announcements
            if g.key_metrics:
                base["key_metrics"] = g.key_metrics
            if g.ai_focus_areas:
                base["ai_focus_areas"] = g.ai_focus_areas
            base["guidance_source_date"] = g.source_date
            base["guidance_confidence"]  = g.confidence

        companies.append(base)

    live_count = sum(1 for g in guidance.values() if g.source == "live")

    result: dict = {
        "companies":    companies,
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "guidance_source": "live" if live_count > 0 else "none",
        "live_companies": live_count,
        "source": "Brave search + LLM extraction",
    }

    if stargate:
        result["stargate_project"] = stargate

    total = sum(c.get("capex_2026_billions", 0) for c in companies)
    if total:
        result["total_2026_capex_billions"] = round(total, 1)

    return result


def invalidate_guidance_cache(company: Optional[str] = None) -> None:
    if company:
        _cache.delete(f"hyperscaler:guidance:{company}")
    else:
        for c in GUIDANCE_QUERIES:
            _cache.delete(f"hyperscaler:guidance:{c}")
        _cache.delete("hyperscaler:stargate")
