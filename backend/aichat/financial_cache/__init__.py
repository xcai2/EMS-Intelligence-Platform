"""Financial data cache for AI Chat.

Self-contained yfinance-backed SQLite cache covering 11 companies
(6 EMS competitors + 5 hyperscalers). Used exclusively by the AI Chat
pipeline to answer numeric financial questions without hitting RAG/web.

This package never modifies news/, analytics/, or existing API routes.
"""

from backend.aichat.financial_cache.companies import COMPANIES, get_company, all_tickers
from backend.aichat.financial_cache.service import (
    refresh_all,
    refresh_one,
    query_metric,
    query_snapshot,
)

__all__ = [
    "COMPANIES",
    "get_company",
    "all_tickers",
    "refresh_all",
    "refresh_one",
    "query_metric",
    "query_snapshot",
]
