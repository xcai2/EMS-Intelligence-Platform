"""News API routes for the News domain module."""

from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.core.config import COMPANIES
from backend.news.service import NewsFeed

router = APIRouter()
_news_feed = NewsFeed()


@router.get("/news/company/{ticker}")
async def get_company_news(ticker: str, category: Optional[str] = None, count: int = 10, force_refresh: bool = False):
    """Get news for a specific company."""
    ticker_upper = ticker.upper()
    if ticker_upper not in COMPANIES:
        raise HTTPException(status_code=404, detail=f"Company {ticker} not found")

    return await _news_feed.get_company_news(ticker_upper, category, count, force_refresh=force_refresh)


@router.get("/news/industry")
async def get_industry_news(count: int = 15, force_refresh: bool = False):
    """Get industry-wide EMS news."""
    return await _news_feed.get_industry_news(count, force_refresh=force_refresh)


@router.get("/news/comparative")
async def get_comparative_news(force_refresh: bool = False):
    """Get news comparing multiple companies."""
    return await _news_feed.get_competitor_comparison_news(force_refresh=force_refresh)


@router.get("/news/all")
async def get_all_news(count_per_company: int = 3, force_refresh: bool = False):
    """Get news for all tracked companies."""
    return await _news_feed.get_all_companies_news(count_per_company, force_refresh=force_refresh)


# Convenience functions
async def get_company_news_service(ticker: str, category: Optional[str] = None) -> dict:
    """Get news for a company."""
    return await _news_feed.get_company_news(ticker, category)


async def get_latest_industry_news() -> dict:
    """Get latest industry news."""
    return await _news_feed.get_industry_news()
