"""Data fetcher: executes Brave News Search + company RSS queries (Phase 1).

This layer only fetches raw results — it does no filtering or normalization.
pipeline.py handles all post-fetch processing.

Phase 1 scope: only fetch_company_news() is used.
industry/comparative fetching is not part of Phase 1.

Brave News Search API
---------------------
Endpoint: GET https://api.search.brave.com/res/v1/news/search
  - Dedicated news endpoint (NOT the web search endpoint /res/v1/web/search)
  - Returns news articles with `page_age` (ISO 8601 timestamp) and `age` (relative fallback)
  - Response: data["results"] — flat array, NOT data["web"]["results"]
  - count max: 50 per request

Rate limiting: a shared asyncio.Semaphore(1) imported from rag/web_search.py
enforces ~1 req/sec across ALL Brave callers in the app.  Do NOT bypass this.

Return contract
---------------
fetch_company_news() returns (raw_items, diagnostics).

  raw_items     — flat list of raw item dicts tagged with source_type and intent
  diagnostics   — per-source summary for Brave and RSS, including attempted count,
                  items found, failures, and per-attempt details
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from backend.core.config import BRAVE_API_KEY
from backend.news.source_fetchers import fetch_company_rss_with_diagnostics
from backend.rag.web_search import get_brave_semaphore as _get_semaphore

# ---------------------------------------------------------------------------
# Brave News API — kept here so the News module owns its own Brave calls.
# rag/web_search.py is for RAG/chat use; news fetching uses the news endpoint.
#
# IMPORTANT: _get_semaphore() is imported from rag/web_search.py so that ALL
# Brave calls across the app share one semaphore.  Brave rate-limits by API
# key (not by endpoint), so having two independent semaphores caused combined
# > 1 req/sec and triggered HTTP 429 "usage limited".
# ---------------------------------------------------------------------------
_BRAVE_NEWS_URL = "https://api.search.brave.com/res/v1/news/search"


def _extract_brave_error(exc: httpx.HTTPStatusError) -> str:
    status = exc.response.status_code
    try:
        payload = exc.response.json()
        err = payload.get("error") or {}
        detail = (err.get("detail") or "").strip()
        code = (err.get("code") or "").strip()
        if detail:
            return f"Brave API HTTP {status}: {detail}" + (f" ({code})" if code else "")
    except Exception:
        pass
    text = exc.response.text.strip()
    return f"Brave API HTTP {status}: {text[:200]}" if text else f"Brave API HTTP {status}"


async def _fetch_brave_news(
    query: str,
    count: int = 50,
    freshness: Optional[str] = None,
) -> tuple[list[dict], Optional[str]]:
    """Call Brave News Search API and return (results, error).

    Uses /res/v1/news/search (NOT web search).
    Each result dict has: title, url, description, published, source, image_url.
    published comes from page_age (ISO 8601) when available, else age (relative).
    source comes from profile.name (publisher display name) when available,
    else meta_url.netloc (domain).
    image_url comes from thumbnail.src, empty string if absent.
    """
    if not BRAVE_API_KEY:
        return [], "BRAVE_API_KEY not set"

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params: dict = {
        "q": query,
        "count": min(count, 50),   # Brave News API max is 50
        "safesearch": "moderate",
    }
    if freshness:
        params["freshness"] = freshness

    async with _get_semaphore():
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    _BRAVE_NEWS_URL,
                    headers=headers,
                    params=params,
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("results", [])[:count]:
                # page_age is ISO 8601 (e.g. "2026-04-15T10:30:00"); prefer it over
                # the human-readable age string ("2 hours ago").
                published = item.get("page_age") or item.get("age") or ""
                # profile.name gives the publisher display name (e.g. "Reuters");
                # fall back to meta_url.netloc (domain) if profile is absent.
                source = (
                    (item.get("profile") or {}).get("name", "")
                    or (item.get("meta_url") or {}).get("netloc", "")
                )
                image_url = (item.get("thumbnail") or {}).get("src", "")
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "published": published,
                    "source": source,
                    "image_url": image_url,
                })
            return results, None

        except httpx.HTTPStatusError as exc:
            return [], _extract_brave_error(exc)
        except httpx.RequestError as exc:
            return [], f"Network error: {exc}"
        except Exception as exc:
            return [], f"Brave news fetch error: {exc}"
        finally:
            # Hold semaphore for 1.1 s to stay within ~1 req/sec free-tier limit.
            await asyncio.sleep(1.1)

logger = logging.getLogger(__name__)


def _new_source_summary() -> dict:
    return {
        "attempted": 0,
        "ok": 0,
        "empty": 0,
        "failed": 0,
        "items_found": 0,
        "details": [],
    }


async def fetch_company_news(
    ticker: str,
    query_params: list[dict],
    rss_feeds: list[dict],
) -> tuple[list[dict], dict]:
    """Execute all queries and RSS fetches for a single company.

    Args:
        ticker:       Company ticker (used only for logging).
        query_params: List of query parameter dicts produced by query_engine.py.
                      Each dict has keys: q, count, freshness, intent.
        rss_feeds:    List of RSS feed configs from query_engine.get_rss_feeds().
                      Each dict has keys: kind, url, source_name.

    Returns:
        (raw_items, diagnostics)
        raw_items    — flat list of raw item dicts tagged with source_type and intent.
        diagnostics  — source-level fetch diagnostics for Brave and RSS.
    """
    raw_items: list[dict] = []
    diagnostics = {
        "brave": _new_source_summary(),
        "rss": _new_source_summary(),
    }

    # ── Brave Search (one call per query template) ────────────────────────────
    for params in query_params:
        query: str = params["q"]
        count: int = params.get("count", 50)
        freshness: Optional[str] = params.get("freshness")
        intent: Optional[str] = params.get("intent")
        brave_summary = diagnostics["brave"]
        brave_summary["attempted"] += 1

        try:
            brave_results, _error = await _fetch_brave_news(
                query, count=count, freshness=freshness
            )
            for item in brave_results:
                item["source_type"] = "brave"
                item["intent"] = intent
            raw_items.extend(brave_results)
            items_found = len(brave_results)
            brave_summary["items_found"] += items_found
            if _error:
                brave_summary["failed"] += 1
                brave_summary["details"].append(
                    {
                        "intent": intent,
                        "query": query,
                        "status": "error",
                        "items_found": items_found,
                        "error": _error,
                    }
                )
                logger.warning("Brave error for '%s': %s", query, _error)
            elif items_found:
                brave_summary["ok"] += 1
                brave_summary["details"].append(
                    {
                        "intent": intent,
                        "query": query,
                        "status": "ok",
                        "items_found": items_found,
                        "error": None,
                    }
                )
            else:
                brave_summary["empty"] += 1
                brave_summary["details"].append(
                    {
                        "intent": intent,
                        "query": query,
                        "status": "empty",
                        "items_found": 0,
                        "error": None,
                    }
                )
        except Exception as exc:
            brave_summary["failed"] += 1
            brave_summary["details"].append(
                {
                    "intent": intent,
                    "query": query,
                    "status": "error",
                    "items_found": 0,
                    "error": str(exc),
                }
            )
            logger.warning("Brave search failed for query '%s': %s", query, exc)

    # ── Company RSS feeds ─────────────────────────────────────────────────────
    for feed in rss_feeds:
        kind: str = feed.get("kind", "news")
        url: str = feed.get("url", "")
        source_name: str = feed.get("source_name", ticker)
        if not url:
            continue
        rss_summary = diagnostics["rss"]
        rss_summary["attempted"] += 1

        if kind == "sec_filing":
            source_type = "sec_filing_rss"
        elif kind == "market_commentary":
            source_type = "market_commentary_rss"
        else:
            source_type = "company_news_rss"

        try:
            feed_items, feed_diagnostics = await fetch_company_rss_with_diagnostics(
                source_name, url, limit=100
            )
            for item in feed_items:
                item["source_type"] = source_type
                item.setdefault("intent", None)
            raw_items.extend(feed_items)
            items_found = len(feed_items)
            status = feed_diagnostics.get("status") or ("ok" if items_found else "empty")
            rss_summary["items_found"] += items_found
            if status == "ok":
                rss_summary["ok"] += 1
            elif status == "empty":
                rss_summary["empty"] += 1
            else:
                rss_summary["failed"] += 1
            rss_summary["details"].append(
                {
                    "kind": kind,
                    "source_name": source_name,
                    "url": url,
                    "source_type": source_type,
                    "status": status,
                    "status_code": feed_diagnostics.get("status_code"),
                    "items_found": items_found,
                    "error": feed_diagnostics.get("error"),
                }
            )
        except Exception as exc:
            rss_summary["failed"] += 1
            rss_summary["details"].append(
                {
                    "kind": kind,
                    "source_name": source_name,
                    "url": url,
                    "source_type": source_type,
                    "status": "error",
                    "status_code": None,
                    "items_found": 0,
                    "error": str(exc),
                }
            )
            logger.warning(
                "RSS fetch failed for %s (%s): %s", ticker, url, exc
            )

    return raw_items, diagnostics
