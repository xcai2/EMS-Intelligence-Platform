"""
API routes for sentiment analysis.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
from pydantic import BaseModel

from backend.core.config import TRACKED_COMPANY_NAMES
from backend.analytics.sentiment import (
    analyze_company_sentiment,
    compare_company_sentiments,
    detect_sentiment_changes,
    analyze_sentiment_llm,
)
from backend.rag.retriever import search_documents

router = APIRouter()


class TextSentimentRequest(BaseModel):
    """Request body for text sentiment analysis."""
    text: str
    use_llm: bool = False
    context: str = ""


@router.get("/sentiment/company/{company}")
async def get_company_sentiment(
    company: str,
    n_chunks: int = 20,
):
    """
    Get sentiment analysis for a specific company.
    
    Args:
        company: Company name (Flex, Jabil, etc.)
        n_chunks: Number of document chunks to analyze
    """
    result = analyze_company_sentiment(company, n_chunks)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


@router.get("/sentiment/compare")
async def compare_sentiments(
    companies: Optional[str] = None,
):
    """
    Compare sentiment across companies.
    
    Args:
        companies: Comma-separated list of companies (default: all)
    """
    if companies:
        company_list = [c.strip() for c in companies.split(",")]
    else:
        company_list = None
    
    results = compare_company_sentiments(company_list)
    
    return {
        "companies": results,
        "comparison": results,
        "most_positive": results[0].get("company") if results else None,
        "most_negative": results[-1].get("company") if results else None,
    }


@router.get("/sentiment/trend/{company}")
async def get_sentiment_trend(company: str):
    """
    Get sentiment trend analysis for a company.
    Shows changes between recent and older documents.
    """
    result = detect_sentiment_changes(company)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


@router.post("/sentiment/analyze-text")
async def analyze_text_sentiment(request: TextSentimentRequest):
    """
    Analyze sentiment of provided text.
    Optionally uses LLM for deeper analysis.
    """
    from backend.analytics.sentiment import analyze_lexicon_sentiment
    
    # Always do lexicon analysis
    lexicon_result = analyze_lexicon_sentiment(request.text)
    
    result = {
        "lexicon_analysis": lexicon_result,
    }
    
    # Optionally add LLM analysis
    if request.use_llm:
        llm_result = await analyze_sentiment_llm(request.text, request.context)
        result["llm_analysis"] = llm_result
    
    return result


@router.get("/sentiment/ai-focus")
async def get_ai_focus_by_company():
    """
    Get AI focus intensity for each company based on mentions.
    """
    companies = list(TRACKED_COMPANY_NAMES)
    
    results = []
    for company in companies:
        # Search for AI-related content
        ai_docs = search_documents(
            query="AI artificial intelligence machine learning GPU neural network data center",
            company_filter=company,
            n_results=50,
        )
        
        # Count actual AI mentions
        ai_keywords = ["ai", "artificial intelligence", "machine learning", "gpu", "neural", 
                       "deep learning", "data center", "hyperscale", "inference"]
        
        mention_count = 0
        for doc in ai_docs:
            content_lower = doc["content"].lower()
            for keyword in ai_keywords:
                mention_count += content_lower.count(keyword)
        
        results.append({
            "company": company,
            "ai_documents": len(ai_docs),
            "ai_mentions": mention_count,
            "focus_level": "high" if mention_count > 50 else "medium" if mention_count > 20 else "low",
        })
    
    # Sort by mentions
    results.sort(key=lambda x: x["ai_mentions"], reverse=True)
    
    return {"companies": results}


@router.get("/sentiment/dashboard")
async def get_sentiment_dashboard():
    """
    Get a complete sentiment dashboard for all companies.
    """
    companies = list(TRACKED_COMPANY_NAMES)
    
    dashboard = {
        "companies": [],
        "summary": {
            "most_positive": None,
            "most_negative": None,
            "most_ai_focused": None,
            "average_sentiment": 0,
        }
    }
    
    total_sentiment = 0
    max_sentiment = -2
    min_sentiment = 2
    max_ai = 0
    
    for company in companies:
        sentiment = analyze_company_sentiment(company)
        trend = detect_sentiment_changes(company)
        
        company_data = {
            "company": company,
            "sentiment_score": sentiment.get("sentiment_score", 0),
            "positive_words": sentiment.get("positive_per_1k", 0),
            "negative_words": sentiment.get("negative_per_1k", 0),
            "ai_mentions": sentiment.get("ai_mentions", 0),
            "trend": trend.get("trend", "unknown"),
            "sentiment_change": trend.get("sentiment_change", 0),
        }
        
        dashboard["companies"].append(company_data)
        
        # Track extremes
        score = company_data["sentiment_score"]
        total_sentiment += score
        
        if score > max_sentiment:
            max_sentiment = score
            dashboard["summary"]["most_positive"] = company
        
        if score < min_sentiment:
            min_sentiment = score
            dashboard["summary"]["most_negative"] = company
        
        if company_data["ai_mentions"] > max_ai:
            max_ai = company_data["ai_mentions"]
            dashboard["summary"]["most_ai_focused"] = company
    
    dashboard["summary"]["average_sentiment"] = round(total_sentiment / len(companies), 3)
    
    return dashboard
