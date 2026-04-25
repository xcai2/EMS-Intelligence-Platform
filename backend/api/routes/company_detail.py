"""
API routes for detailed company information.
Provides comprehensive data for company deep-dive pages.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional

from backend.core.config import COMPANIES, COMPANY_NAME_TO_TICKER
from backend.core.database import get_collection_stats
from backend.rag.retriever import search_documents, get_company_documents
from backend.analytics.sentiment import analyze_company_sentiment
from backend.analytics.trends import analyze_company_trends
from backend.analytics.classifier import classify_company_investments
from backend.analytics.geographic import get_company_facilities, get_regional_distribution
from backend.analytics.anomaly import detect_capex_anomalies, detect_ai_investment_changes
from backend.analytics.table_extractor import extract_company_financials, extract_capex_breakdown
from backend.analytics.financial_service import get_company_financials

router = APIRouter()

DEFAULT_COMPANY_COLORS = {
    "FLEX": "#3B82F6",
    "JBL": "#10B981",
    "CLS": "#6366F1",
    "BHE": "#F59E0B",
    "SANM": "#EF4444",
    "PLXS": "#14B8A6",
}


def get_company_info(company_name: str) -> dict:
    """Get company configuration info."""
    # Handle both ticker and name
    ticker = COMPANY_NAME_TO_TICKER.get(company_name.title())
    if not ticker:
        ticker = company_name.upper()
    
    company_config = COMPANIES.get(ticker)
    if not company_config:
        return None
    
    return {
        "ticker": ticker,
        "name": company_config["name"],
        "cik": company_config["cik"],
        "fiscal_year_end": company_config.get("fiscal_year_end", "Unknown"),
        "headquarters": company_config.get("headquarters", "Unknown"),
        "industry": company_config.get("industry", company_config.get("sector", "Unknown")),
        "color": company_config.get("color", DEFAULT_COMPANY_COLORS.get(ticker, "#64748B")),
    }


@router.get("/company/{company}/overview")
async def get_company_overview(company: str):
    """
    Get comprehensive overview for a company.
    Combines all key metrics into a single response.
    """
    try:
        # Normalize company name
        company_title = company.title()
        
        # Get company info
        info = get_company_info(company)
        if not info:
            raise HTTPException(status_code=404, detail=f"Company {company} not found")
        
        # Get document stats
        stats = get_collection_stats()
        doc_count = stats["companies"].get(company_title, 0)
        
        # Get all analytics in parallel conceptually (we're in async context)
        sentiment = analyze_company_sentiment(company_title)
        trends = analyze_company_trends(company_title)
        classification = classify_company_investments(company_title)
        facilities = get_company_facilities(company_title)
        
        return {
            "company": company_title,
            "info": info,
            "documents": doc_count,
            "sentiment": {
                "score": sentiment.get("sentiment_score", 0),
                "positive_count": sentiment.get("positive_count", 0),
                "negative_count": sentiment.get("negative_count", 0),
                "ai_mentions": sentiment.get("ai_mentions", 0),
                "method": sentiment.get("method", "finbert"),
            },
            "trends": {
                "outlook": trends.get("overall_outlook", "neutral"),
                "capex_trend": trends.get("capex_trend", {}),
                "ai_focus_trend": trends.get("ai_focus_trend", {}),
                "sentiment_trend": trends.get("sentiment_trend", {}),
            },
            "investment": {
                "ai_focus_percentage": classification.get("overall_ai_focus_percentage", 0),
                "investment_focus": classification.get("investment_focus", "Balanced"),
            },
            "facilities": {
                "total": facilities.get("total_facilities", 0),
                "headquarters": facilities.get("headquarters", {}),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/{company}/filings")
async def get_company_filings(company: str, filing_type: Optional[str] = None, limit: int = 20):
    """
    Get recent filings for a company.
    """
    try:
        company_title = company.title()
        
        docs = get_company_documents(company_title, limit=limit * 5)  # Get more to filter
        
        # Group by source
        filings = {}
        for doc in docs:
            source = doc.get("metadata", {}).get("source", "Unknown")
            filing_t = doc.get("metadata", {}).get("filing_type", "Unknown")
            fiscal_year = doc.get("metadata", {}).get("fiscal_year", "Unknown")
            
            if filing_type and filing_t != filing_type:
                continue
            
            if source not in filings:
                filings[source] = {
                    "source": source,
                    "filing_type": filing_t,
                    "fiscal_year": fiscal_year,
                    "chunk_count": 0,
                    "preview": doc["content"][:300] + "...",
                }
            filings[source]["chunk_count"] += 1
        
        # Sort by fiscal year descending
        sorted_filings = sorted(
            filings.values(),
            key=lambda x: x["fiscal_year"],
            reverse=True
        )[:limit]
        
        return {
            "company": company_title,
            "filings": sorted_filings,
            "total": len(sorted_filings),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/{company}/financials")
async def get_company_financial_data(company: str):
    """
    Get financial data for a company.
    Primary source: yfinance. Fallback: vector DB extraction.
    """
    try:
        company_title = company.title()
        data = get_company_financials(company_title)
        return {"company": company_title, **data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/{company}/ai-analysis")
async def get_company_ai_analysis(company: str):
    """
    Get AI/Data Center investment analysis for a company.
    """
    try:
        company_title = company.title()
        
        classification = classify_company_investments(company_title, n_docs=100)
        ai_changes = detect_ai_investment_changes(company_title)
        
        # Search for AI-specific content
        ai_docs = search_documents(
            query=f"{company_title} AI artificial intelligence data center GPU machine learning hyperscale",
            company_filter=company_title,
            n_results=20,
        )
        
        ai_mentions = []
        for doc in ai_docs[:10]:
            ai_mentions.append({
                "source": doc.get("source", "Unknown"),
                "fiscal_year": doc.get("fiscal_year", "Unknown"),
                "preview": doc["content"][:200] + "...",
            })
        
        return {
            "company": company_title,
            "ai_focus_percentage": classification.get("overall_ai_focus_percentage", 0),
            "investment_focus": classification.get("investment_focus", "Balanced"),
            "investment_breakdown": classification.get("investment_breakdown", {}),
            "ai_trend": ai_changes.get("trend", "stable"),
            "ai_focus_by_year": ai_changes.get("ai_focus_by_year", {}),
            "sample_ai_mentions": ai_mentions,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/{company}/capex")
async def get_company_capex_analysis(company: str):
    """
    Get CapEx analysis for a company.
    """
    try:
        company_title = company.title()
        
        anomalies = detect_capex_anomalies(company_title)
        capex_breakdown = extract_capex_breakdown(company_title)
        
        # Search for CapEx content
        capex_docs = search_documents(
            query=f"{company_title} capital expenditure CapEx investment property plant equipment",
            company_filter=company_title,
            n_results=20,
        )
        
        capex_mentions = []
        for doc in capex_docs[:10]:
            capex_mentions.append({
                "source": doc.get("source", "Unknown"),
                "fiscal_year": doc.get("fiscal_year", "Unknown"),
                "preview": doc["content"][:200] + "...",
            })
        
        return {
            "company": company_title,
            "anomalies": anomalies.get("anomalies", []),
            "has_anomalies": anomalies.get("has_anomalies", False),
            "period_data": anomalies.get("period_data", {}),
            "breakdown": capex_breakdown.get("breakdown", {}),
            "primary_focus": capex_breakdown.get("primary_focus"),
            "sample_mentions": capex_mentions,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/{company}/geographic")
async def get_company_geographic_data(company: str):
    """
    Get geographic/facility data for a company.
    """
    try:
        company_title = company.title()
        
        facilities = get_company_facilities(company_title)
        distribution = get_regional_distribution(company_title)
        
        if "error" in facilities:
            raise HTTPException(status_code=404, detail=facilities["error"])
        
        return {
            "company": company_title,
            "headquarters": facilities.get("headquarters", {}),
            "facilities": facilities.get("facilities", []),
            "total_facilities": facilities.get("total_facilities", 0),
            "regional_distribution": distribution.get("distribution", {}),
            "regional_percentages": distribution.get("percentages", {}),
            "primary_region": distribution.get("primary_region"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/{company}/news")
async def get_company_news(company: str, limit: int = 10):
    """
    Get recent news/press releases for a company.
    """
    try:
        company_title = company.title()
        
        # Search for press releases and news
        docs = search_documents(
            query=f"{company_title} announces reported quarterly results",
            company_filter=company_title,
            n_results=limit * 2,
        )
        
        # Filter for press releases
        news_items = []
        for doc in docs:
            filing_type = doc.get("filing_type", "")
            if "Press Release" in filing_type or "8-K" in filing_type:
                news_items.append({
                    "source": doc.get("source", "Unknown"),
                    "filing_type": filing_type,
                    "fiscal_year": doc.get("fiscal_year", "Unknown"),
                    "preview": doc["content"][:300] + "...",
                })
        
        return {
            "company": company_title,
            "news": news_items[:limit],
            "count": len(news_items[:limit]),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
