"""
API routes for advanced data sources.
Patents, job postings, enhanced news aggregation, and OCP data.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional

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
from backend.news.aggregator import (
    get_company_news,
    get_industry_news,
    get_all_companies_news,
    get_trending_topics,
    get_news_categories,
    get_rss_feeds,
)
from backend.ingestion.ocp_scraper import (
    get_company_ocp_data,
    compare_ocp_involvement,
    get_ocp_categories,
    get_ocp_member_info,
)

router = APIRouter()


# ============== Patent Routes ==============

@router.get("/patents/compare/all")
async def compare_patents():
    """
    Compare patent activity across all tracked companies.
    """
    try:
        return await compare_all_patents()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patents/categories")
async def list_patent_categories():
    """
    Get available patent categories for filtering.
    """
    return get_patent_categories()


@router.get("/patents/{company}")
async def get_company_patents(company: str, category: Optional[str] = None):
    """
    Get patent filings for a company.
    Optionally filter by category (ai_ml, automation, manufacturing, etc.)
    """
    try:
        patents = await search_company_patents(company.title(), category)
        innovation = get_innovation_score(patents)
        return {
            **patents,
            "innovation_score": innovation,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Job Routes ==============

@router.get("/jobs/compare/all")
async def compare_hiring():
    """
    Compare hiring trends across all tracked companies.
    """
    try:
        return await compare_all_hiring()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/categories")
async def list_job_categories():
    """
    Get available job categories for filtering.
    """
    return get_job_categories()


@router.get("/jobs/{company}")
async def get_company_job_postings(company: str, category: Optional[str] = None):
    """
    Get job postings for a company.
    Optionally filter by category (ai_ml, software, hardware, etc.)
    """
    try:
        jobs = await search_company_jobs(company.title(), category)
        hiring_score = get_hiring_score(jobs)
        return {
            **jobs,
            "hiring_score": hiring_score,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Enhanced News Routes ==============

@router.get("/news-aggregator/company/{company}")
async def get_aggregated_company_news(company: str, count: int = 10):
    """
    Get aggregated news for a specific company.
    """
    try:
        return await get_company_news(company.title(), count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news-aggregator/industry")
async def get_aggregated_industry_news(count: int = 20):
    """
    Get industry news from RSS feeds and web search.
    """
    try:
        return await get_industry_news(count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news-aggregator/all-companies")
async def get_aggregated_all_companies_news(count_per_company: int = 5):
    """
    Get news for all tracked companies.
    """
    try:
        return await get_all_companies_news(count_per_company)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news-aggregator/trending")
async def get_trending():
    """
    Get trending topics in industry news.
    """
    try:
        return await get_trending_topics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news-aggregator/categories")
async def list_news_categories():
    """
    Get available news categories.
    """
    return get_news_categories()


@router.get("/news-aggregator/feeds")
async def list_rss_feeds():
    """
    Get configured RSS feeds.
    """
    return get_rss_feeds()


# ============== Combined Intelligence ==============

@router.get("/intelligence/{company}")
async def get_company_intelligence(company: str):
    """
    Get comprehensive intelligence for a company.
    Combines patents, jobs, and news data.
    """
    try:
        company_title = company.title()
        
        # Gather all data
        patents = await search_company_patents(company_title)
        jobs = await search_company_jobs(company_title)
        news = await get_company_news(company_title, count=5)
        
        # Calculate scores
        innovation = get_innovation_score(patents)
        hiring = get_hiring_score(jobs)
        
        # Combined intelligence score
        combined_score = (
            innovation.get('innovation_score', 0) * 0.4 +
            hiring.get('hiring_score', 0) * 0.3 +
            (50 if news.get('total', 0) > 5 else 25) * 0.3
        )
        
        return {
            "company": company_title,
            "combined_intelligence_score": round(combined_score, 1),
            "patents": {
                "total": patents.get('total_patents', 0),
                "innovation_score": innovation.get('innovation_score', 0),
                "focus_areas": innovation.get('focus_areas', []),
                "ai_focus": innovation.get('ai_focus', False),
            },
            "hiring": {
                "total_openings": jobs.get('total_jobs', 0),
                "hiring_score": hiring.get('hiring_score', 0),
                "ai_focus": hiring.get('ai_focus_pct', 0),
                "strategic_focus": hiring.get('strategic_focus', []),
            },
            "news": {
                "recent_articles": news.get('total', 0),
                "top_articles": news.get('articles', [])[:3],
            },
            "insights": _generate_insights(innovation, hiring, news),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intelligence/compare/all")
async def compare_all_intelligence():
    """
    Compare comprehensive intelligence across all companies.
    """
    try:
        patents_comparison = await compare_all_patents()
        hiring_comparison = await compare_all_hiring()
        
        companies_intel = {}
        
        for company in patents_comparison.get('companies', {}).keys():
            patent_data = patents_comparison['companies'].get(company, {})
            hiring_data = hiring_comparison['companies'].get(company, {})
            
            # Simple combined score
            patent_score = min(patent_data.get('total', 0) * 5, 50)
            hiring_score = min(hiring_data.get('total_jobs', 0) * 3, 30)
            ai_bonus = 20 if (patent_data.get('by_category', {}).get('ai_ml', 0) > 0 or 
                             hiring_data.get('is_hiring_ai', False)) else 0
            
            companies_intel[company] = {
                "patent_activity": patent_data.get('total', 0),
                "hiring_activity": hiring_data.get('total_jobs', 0),
                "ai_focus": hiring_data.get('ai_focus', 0),
                "combined_score": patent_score + hiring_score + ai_bonus,
            }
        
        # Rank companies
        ranked = sorted(
            companies_intel.items(),
            key=lambda x: x[1].get('combined_score', 0),
            reverse=True
        )
        
        return {
            "companies": companies_intel,
            "rankings": [{"rank": i+1, "company": c[0], "score": c[1]['combined_score']} 
                        for i, c in enumerate(ranked)],
            "leader": ranked[0][0] if ranked else None,
            "patents_leader": patents_comparison.get('leader'),
            "hiring_leader": hiring_comparison.get('most_active_hiring'),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _generate_insights(innovation: dict, hiring: dict, news: dict) -> list:
    """Generate strategic insights from combined data."""
    insights = []
    
    if innovation.get('ai_focus'):
        insights.append("Active in AI/ML patent filings, indicating R&D investment in emerging technologies")
    
    if hiring.get('ai_focus_pct', 0) > 15:
        insights.append(f"Strong AI hiring focus ({hiring.get('ai_focus_pct', 0):.0f}% of openings) suggests strategic AI buildout")
    
    if hiring.get('is_aggressively_hiring'):
        insights.append("Aggressive hiring activity indicates expansion or new initiatives")
    
    if innovation.get('focus_areas'):
        areas = ', '.join(innovation['focus_areas'][:2])
        insights.append(f"Key innovation areas: {areas}")
    
    if news.get('total', 0) > 8:
        insights.append("High news volume indicates significant market activity or announcements")
    
    if not insights:
        insights.append("Limited public intelligence data available; recommend deeper analysis")
    
    return insights[:5]


# ============================================================================
# Open Compute Project (OCP) Routes
# ============================================================================

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
        company_title = company.title()
        return await get_company_ocp_data(company_title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
