"""News API routes (Phase 3 Part 1).

Endpoints:
    GET  /api/news/company/{ticker}          — single-company news (cache or force_refresh)
    GET  /api/news/all                       — aggregate view across all company caches

    GET  /api/news/companies                 — list all registered companies
    GET  /api/news/companies/suggest         — autocomplete candidates for a query string
    POST /api/news/companies/resolve         — standardize a selected candidate (LLM)
    POST /api/news/companies/preview         — generate 4 template drafts (no DB write)
    POST /api/news/companies                 — save new company + templates to DB
    PUT  /api/news/companies/{ticker}/queries — replace all 4 query templates
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.news.db import init_db
from backend.news.models import Company, QueryTemplate
from backend.news.onboarding import (
    build_query_templates_from_preview,
    generate_template_preview,
)
from backend.news.registry import (
    backfill_builtin_company_websites,
    get_company,
    is_builtin_company,
    list_companies,
    delete_company,
    save_company,
    seed_initial_companies,
    update_company_queries,
    upgrade_templates_count_to_50,
)
from backend.news import service
from backend.news.company_resolver import suggest as resolver_suggest, resolve as resolver_resolve

# Idempotent startup: create tables, seed built-ins, then run one-time migrations.
init_db()
seed_initial_companies()
upgrade_templates_count_to_50()
backfill_builtin_company_websites()

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter()

# Phase 1 fixed intent values (§6.2)
_VALID_INTENTS = frozenset({"official_name", "industry_news", "stock_news", "supporting_query"})


def _require_company(ticker: str) -> None:
    """Raise HTTP 404 if ticker is not registered."""
    if not get_company(ticker.upper()):
        raise HTTPException(status_code=404, detail=f"Company {ticker} not found")


def _validate_query_templates(queries: List[_QueryTemplateIn]) -> None:
    """Enforce Phase 1 constraint: exactly 4 templates with the fixed intent set (§6.2, §12.3)."""
    if len(queries) != 4:
        raise HTTPException(
            status_code=422,
            detail=f"Exactly 4 query templates are required (got {len(queries)}). "
                   f"Required intents: {sorted(_VALID_INTENTS)}",
        )
    provided = {q.intent for q in queries}
    if provided != _VALID_INTENTS:
        missing = sorted(_VALID_INTENTS - provided)
        extra = sorted(provided - _VALID_INTENTS)
        detail = "Query intents must be exactly: official_name, industry_news, stock_news, supporting_query."
        if missing:
            detail += f" Missing: {missing}."
        if extra:
            detail += f" Not allowed: {extra}."
        raise HTTPException(status_code=422, detail=detail)


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@router.get("/news/company/{ticker}")
async def get_company_news(
    ticker: str,
    force_refresh: bool = Query(default=False),
):
    """Get news for a single company.

    Default (force_refresh=false): reads from disk cache.
    - Cache hit (fresh): returns items + top_news, refresh_required=false.
    - Cache miss or stale: returns empty lists, refresh_required=true.

    force_refresh=true: triggers live Brave + RSS fetch, runs pipeline, writes cache.
    """
    ticker_upper = ticker.upper()
    _require_company(ticker_upper)

    return await service.get_company_news(ticker_upper, force_refresh=force_refresh)


@router.get("/news/all")
async def get_all_news(
    force_refresh: bool = Query(default=False),
):
    """Get aggregated news from all registered companies' caches.

    force_refresh=true is NOT supported for this endpoint (Phase 1 §12.2).
    Use GET /api/news/company/{ticker}?force_refresh=true per company instead.
    """
    if force_refresh:
        raise HTTPException(
            status_code=400,
            detail={"error": "force_refresh_not_supported_for_all"},
        )
    return await service.get_all_companies_news()


# ---------------------------------------------------------------------------
# Company list + resolver endpoints (Phase 3 Part 1)
# ---------------------------------------------------------------------------

@router.get("/news/companies")
async def get_companies():
    """Return all registered companies with their metadata."""
    companies = list_companies()
    return {
        "companies": [
            {
                "ticker": c.ticker,
                "full_name": c.full_name,
                "display_name": c.full_name.split()[0],
                "aliases": c.aliases,
                "official_domain": c.official_domain,
                "official_website": c.official_website or (f"https://www.{c.official_domain}" if c.official_domain else ""),
                "industry": c.industry,
                "template_tier": c.template_tier,
                "is_builtin": is_builtin_company(c.ticker),
                "is_deletable": not is_builtin_company(c.ticker),
            }
            for c in companies
        ],
        "total": len(companies),
    }


@router.get("/news/companies/suggest")
async def suggest_companies(q: str = Query(..., min_length=2)):
    """Return autocomplete candidates for a company name/ticker/alias query.

    Strategy (§5.3.4): local registry first, LLM fallback only if local < 3.
    """
    candidates = await resolver_suggest(q)
    return {"candidates": candidates, "query": q}


class _ResolveRequest(BaseModel):
    company_name: str
    ticker: str
    official_website: str = ""


@router.post("/news/companies/resolve")
async def resolve_company(body: _ResolveRequest):
    """Standardize a selected candidate into a full company object with confidence.

    Returns confidence score and reason so the frontend can decide whether to
    auto-proceed (≥0.85), require manual confirmation (0.60–0.85), or reject (<0.60).
    """
    resolved = await resolver_resolve(
        company_name=body.company_name,
        ticker=body.ticker,
        official_website=body.official_website,
    )
    return resolved


# ---------------------------------------------------------------------------
# Company management endpoints
# ---------------------------------------------------------------------------

class _PreviewRequest(BaseModel):
    ticker: str
    full_name: str
    industry: str = ""
    aliases: str = ""
    template_tier: str = "standard"


@router.post("/news/companies/preview")
async def preview_company_templates(body: _PreviewRequest):
    """Generate 4 fixed query template drafts for a new company.

    Does NOT write to the database. Returns template previews for operator review.
    Phase 1: uses fixed rules only, no LLM.
    """
    preview = generate_template_preview(
        full_name=body.full_name,
        ticker=body.ticker.upper(),
        industry=body.industry,
        aliases=body.aliases,
    )
    return {
        "ticker": body.ticker.upper(),
        "full_name": body.full_name,
        "template_tier": body.template_tier,
        "templates": preview,
    }


class _QueryTemplateIn(BaseModel):
    intent: str
    query_template: str
    freshness: Optional[str] = None
    count: int = 50


class _CompanyIn(BaseModel):
    ticker: str
    full_name: str
    industry: str = ""
    aliases: str = ""
    official_domain: str = ""
    official_website: str = ""
    template_tier: str = "standard"


class _SaveCompanyRequest(BaseModel):
    company: _CompanyIn
    queries: List[_QueryTemplateIn]


@router.post("/news/companies")
async def save_new_company(body: _SaveCompanyRequest):
    """Save a new company and its query templates to the database.

    Step 2 of the onboarding flow. Accepts the (optionally edited) templates
    returned from POST /api/news/companies/preview.

    Returns HTTP 409 if the ticker already exists — use PUT /queries to update.
    """
    ticker = body.company.ticker.upper()
    if get_company(ticker):
        raise HTTPException(status_code=409, detail=f"Company {ticker} already exists")

    _validate_query_templates(body.queries)

    company = Company(
        ticker=ticker,
        full_name=body.company.full_name,
        aliases=body.company.aliases,
        industry=body.company.industry,
        official_domain=body.company.official_domain,
        official_website=body.company.official_website,
        template_tier=body.company.template_tier,
    )
    queries = build_query_templates_from_preview(
        ticker,
        [q.model_dump() for q in body.queries],
    )

    try:
        save_company(company, queries)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save company: {exc}")

    init_fetch = {"status": "skipped"}
    try:
        init_payload = await service.get_company_news(ticker, force_refresh=True)
        init_fetch = {
            "status": "ok",
            "item_count": len(init_payload.get("items") or []),
            "sec_count": len(init_payload.get("sec_items") or []),
        }
    except Exception as exc:
        init_fetch = {"status": "failed", "detail": str(exc)}

    return {
        "ticker": ticker,
        "full_name": body.company.full_name,
        "template_count": len(queries),
        "initial_fetch": init_fetch,
        "message": f"Company {ticker} registered successfully.",
    }


@router.put("/news/companies/{ticker}/queries")
async def update_queries(ticker: str, queries: List[_QueryTemplateIn]):
    """Replace all query templates for an existing company.

    Phase 1: replaces the entire set of 4 templates atomically.
    """
    ticker_upper = ticker.upper()
    _require_company(ticker_upper)
    _validate_query_templates(queries)

    new_templates = build_query_templates_from_preview(
        ticker_upper,
        [q.model_dump() for q in queries],
    )
    try:
        update_company_queries(ticker_upper, new_templates)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update queries: {exc}")

    return {
        "ticker": ticker_upper,
        "template_count": len(new_templates),
        "message": "Query templates updated.",
    }


@router.delete("/news/companies/{ticker}")
async def remove_company(ticker: str):
    """Delete a user-added company and its related artifacts."""
    ticker_upper = ticker.upper()
    _require_company(ticker_upper)
    if is_builtin_company(ticker_upper):
        raise HTTPException(status_code=400, detail=f"Built-in company {ticker_upper} cannot be deleted")

    artifacts = service.delete_company_artifacts(ticker_upper)
    deleted = delete_company(ticker_upper)
    if not deleted:
        raise HTTPException(status_code=500, detail=f"Failed to delete company {ticker_upper}")

    return {
        "ticker": ticker_upper,
        "deleted": True,
        "artifacts": artifacts,
    }
