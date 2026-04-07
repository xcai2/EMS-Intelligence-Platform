"""News API routes for the News domain module."""

from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.config import COMPANIES
from backend.news.filtering import CATEGORIES
from backend.news.service import NewsFeed

router = APIRouter()
VALID_COMPANY_CATEGORIES = tuple(CATEGORIES.keys())
VALID_COMPANY_CATEGORY_PATTERN = "^(" + "|".join(VALID_COMPANY_CATEGORIES) + ")$"


@lru_cache(maxsize=1)
def get_news_feed() -> NewsFeed:
    """Lazily create the NewsFeed singleton used by API routes."""
    return NewsFeed()


@router.get("/news/company/{ticker}")
async def get_company_news(
    ticker: str,
    category: Optional[str] = Query(
        default=None,
        pattern=VALID_COMPANY_CATEGORY_PATTERN,
        description=f"Optional post-fetch category filter. One of: {', '.join(VALID_COMPANY_CATEGORIES)}",
    ),
    count: int = Query(default=10, ge=1, le=100),
    force_refresh: bool = False,
    news_feed: NewsFeed = Depends(get_news_feed),
):
    """Get broad company-linked news, with optional post-fetch category filtering."""
    ticker_upper = ticker.upper()
    if ticker_upper not in COMPANIES:
        raise HTTPException(status_code=404, detail=f"Company {ticker} not found")

    return await news_feed.get_company_news(ticker_upper, category, count, force_refresh=force_refresh)


@router.get("/news/industry")
async def get_industry_news(
    count: int = Query(default=15, ge=1, le=100),
    force_refresh: bool = False,
    news_feed: NewsFeed = Depends(get_news_feed),
):
    """Get industry-wide EMS news."""
    return await news_feed.get_industry_news(count, force_refresh=force_refresh)


@router.get("/news/comparative")
async def get_comparative_news(
    force_refresh: bool = False,
    news_feed: NewsFeed = Depends(get_news_feed),
):
    """Get news comparing multiple companies."""
    return await news_feed.get_competitor_comparison_news(force_refresh=force_refresh)


@router.get("/news/all")
async def get_all_news(
    count_per_company: int = Query(default=100, ge=0, le=100, description="Per-company item cap. Use 0 to return all cached items."),
    force_refresh: bool = False,
    news_feed: NewsFeed = Depends(get_news_feed),
):
    """Get news for all tracked companies."""
    return await news_feed.get_all_companies_news(count_per_company, force_refresh=force_refresh)
