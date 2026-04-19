"""
API routes for supplemental data sources used outside the core News domain.
Patents, job postings, OCP data, and combined intelligence views live here.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional

from backend.core.config import COMPANY_NAME_TO_TICKER
from backend.ingestion.patent_scraper import (
    search_company_patents,
    compare_all_patents,
    get_innovation_score,
    get_patent_categories,
)
from backend.ingestion.job_scraper import (
    search_company_jobs,
    compare_all_hiring,
    get_hiring_score,
    get_job_categories,
)
from backend.ingestion.ocp_scraper import (
    get_company_ocp_data,
    compare_ocp_involvement,
    get_ocp_categories,
    get_ocp_member_info,
)
from backend.news import service as news_service

router = APIRouter()


def _normalize_company_title(company: str) -> str:
    return company.title()


async def _get_company_news_snapshot(company_title: str) -> dict:
    """Read the current cached company-news snapshot."""
    ticker = COMPANY_NAME_TO_TICKER.get(company_title, company_title.upper())
    payload = await news_service.get_company_news(ticker, force_refresh=False)
    items = payload.get("items", [])
    return {
        "recent_articles": len(items),
        "top_articles": items[:3],
    }


@router.get("/patents/compare/all")
async def compare_patents():
    """Compare patent activity across all tracked companies."""
    try:
        return await compare_all_patents()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patents/categories")
async def list_patent_categories():
    """Get available patent categories for filtering."""
    return get_patent_categories()


@router.get("/patents/{company}")
async def get_company_patents(company: str, category: Optional[str] = None):
    """Get patent filings for a company."""
    try:
        patents = await search_company_patents(_normalize_company_title(company), category)
        innovation = get_innovation_score(patents)
        return {
            **patents,
            "innovation_score": innovation,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/compare/all")
async def compare_hiring():
    """Compare hiring trends across all tracked companies."""
    try:
        return await compare_all_hiring()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/categories")
async def list_job_categories():
    """Get available job categories for filtering."""
    return get_job_categories()


@router.get("/jobs/{company}")
async def get_company_job_postings(company: str, category: Optional[str] = None):
    """Get job postings for a company."""
    try:
        jobs = await search_company_jobs(_normalize_company_title(company), category)
        hiring_score = get_hiring_score(jobs)
        return {
            **jobs,
            "hiring_score": hiring_score,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intelligence/{company}")
async def get_company_intelligence(company: str):
    """Get a combined company snapshot across patents, jobs, and cached news."""
    try:
        company_title = _normalize_company_title(company)
        patents = await search_company_patents(company_title)
        jobs = await search_company_jobs(company_title)
        news = await _get_company_news_snapshot(company_title)

        innovation = get_innovation_score(patents)
        hiring = get_hiring_score(jobs)

        combined_score = (
            innovation.get("innovation_score", 0) * 0.4
            + hiring.get("hiring_score", 0) * 0.3
            + (50 if news.get("recent_articles", 0) > 5 else 25) * 0.3
        )

        return {
            "company": company_title,
            "combined_intelligence_score": round(combined_score, 1),
            "patents": {
                "total": patents.get("total_patents", 0),
                "innovation_score": innovation.get("innovation_score", 0),
                "focus_areas": innovation.get("focus_areas", []),
                "ai_focus": innovation.get("ai_focus", False),
            },
            "hiring": {
                "total_openings": jobs.get("total_jobs", 0),
                "hiring_score": hiring.get("hiring_score", 0),
                "ai_focus": hiring.get("ai_focus_pct", 0),
                "strategic_focus": hiring.get("strategic_focus", []),
            },
            "news": news,
            "insights": _generate_insights(innovation, hiring, news),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intelligence/compare/all")
async def compare_all_intelligence():
    """Compare comprehensive intelligence across all companies."""
    try:
        patents_comparison = await compare_all_patents()
        hiring_comparison = await compare_all_hiring()

        companies_intel = {}

        for company in patents_comparison.get("companies", {}).keys():
            patent_data = patents_comparison["companies"].get(company, {})
            hiring_data = hiring_comparison.get("companies", {}).get(company, {})

            patent_score = min(patent_data.get("total", 0) * 5, 50)
            hiring_score = min(hiring_data.get("total_jobs", 0) * 3, 30)
            ai_bonus = 20 if (
                patent_data.get("by_category", {}).get("ai_ml", 0) > 0
                or hiring_data.get("is_hiring_ai", False)
            ) else 0

            companies_intel[company] = {
                "patent_activity": patent_data.get("total", 0),
                "hiring_activity": hiring_data.get("total_jobs", 0),
                "ai_focus": hiring_data.get("ai_focus", 0),
                "combined_score": patent_score + hiring_score + ai_bonus,
            }

        ranked = sorted(
            companies_intel.items(),
            key=lambda item: item[1].get("combined_score", 0),
            reverse=True,
        )

        return {
            "companies": companies_intel,
            "rankings": [
                {"rank": index + 1, "company": company, "score": data["combined_score"]}
                for index, (company, data) in enumerate(ranked)
            ],
            "leader": ranked[0][0] if ranked else None,
            "patents_leader": patents_comparison.get("leader"),
            "hiring_leader": hiring_comparison.get("most_active_hiring"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _generate_insights(innovation: dict, hiring: dict, news: dict) -> list[str]:
    """Generate a few high-level insights from combined data."""
    insights: list[str] = []

    if innovation.get("ai_focus"):
        insights.append("Active in AI/ML patent filings, indicating R&D investment in emerging technologies")

    if hiring.get("ai_focus_pct", 0) > 15:
        insights.append(
            f"Strong AI hiring focus ({hiring.get('ai_focus_pct', 0):.0f}% of openings) suggests strategic AI buildout"
        )

    if hiring.get("is_aggressively_hiring"):
        insights.append("Aggressive hiring activity indicates expansion or new initiatives")

    if innovation.get("focus_areas"):
        areas = ", ".join(innovation["focus_areas"][:2])
        insights.append(f"Key innovation areas: {areas}")

    if news.get("recent_articles", 0) > 8:
        insights.append("High news volume indicates significant market activity or announcements")

    if not insights:
        insights.append("Limited public intelligence data available; recommend deeper analysis")

    return insights[:5]


@router.get("/ocp/compare/all")
async def compare_ocp():
    """Compare OCP involvement across all companies."""
    try:
        return await compare_ocp_involvement()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ocp/categories")
async def list_ocp_categories():
    """Get OCP project categories."""
    return get_ocp_categories()


@router.get("/ocp/members")
async def list_ocp_members():
    """Get known OCP member information for tracked companies."""
    return get_ocp_member_info()


@router.get("/ocp/{company}")
async def get_company_ocp(company: str):
    """Get OCP involvement details for a specific company."""
    try:
        return await get_company_ocp_data(_normalize_company_title(company))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
