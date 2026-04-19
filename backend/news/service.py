"""News service: cache orchestration for Phase 2 company news pipeline.

Flow for force_refresh=True:
    query_engine → fetcher → pipeline (normalize→dedup→age filter→sort) → write cache → return

Flow for force_refresh=False (default):
    read per-company disk cache → return (or return refresh_required if absent/stale)

Per-company cache files: data/news_cache/company_{ticker}.json
  (e.g. data/news_cache/company_FLEX.json)

Phase 2 response format:
    {
      "items":            [...],   # news items only (sec_filing_rss excluded)
      "top_news":         [...],   # first 7 from items (Phase 2 ranking in ranking.py, TBD)
      "sec_items":        [...],   # sec_filing_rss items, separated from main news flow
      "refresh_required": bool
    }

GET /api/news/all does NOT support force_refresh=True — returns HTTP 400.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import asyncio

from backend.news import fetcher, pipeline, query_engine, ranking, summarizer, trending
from backend.news.models import NewsItem, compute_canonical_url
from backend.news.normalizer import parse_published_dt
from backend.news.registry import get_company, list_companies

logger = logging.getLogger(__name__)

NEWS_CACHE_DIR = Path("data/news_cache")
CACHE_TTL_SECONDS = 48 * 3600  # 48 hours
TOP_NEWS_COUNT = 7


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _company_cache_path(ticker: str) -> Path:
    return NEWS_CACHE_DIR / f"company_{ticker.upper()}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_cache_fresh(payload: Optional[dict]) -> bool:
    if not payload:
        return False
    cached_at = parse_published_dt(payload.get("timestamp", ""))
    if not cached_at:
        return False
    age = (datetime.now(timezone.utc) - cached_at).total_seconds()
    return 0 <= age <= CACHE_TTL_SECONDS


def _write_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read_cache(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def delete_company_artifacts(ticker: str) -> dict:
    """Remove cache and summary artifacts for a company.

    Returns a small diagnostics payload describing what was removed.
    """
    ticker_upper = ticker.upper()
    cache_path = _company_cache_path(ticker_upper)
    payload = _read_cache(cache_path) or {}
    items = payload.get("items") or []
    all_items = list(items)
    article_keys = {
        (item.get("canonical_url") or item.get("url") or "").strip()
        for item in all_items
        if isinstance(item, dict)
    }
    article_keys.discard("")

    weekly_key = None
    try:
        company = get_company(ticker_upper)
        news_items, _sec_items = _split_sec_items([
            item for item in all_items if isinstance(item, dict)
        ])
        top_news = ranking.build_top_news(news_items, company=company) if company else []
        if top_news:
            weekly_key = summarizer._weekly_cache_key(top_news)  # type: ignore[attr-defined]
    except Exception:
        weekly_key = None

    removed_cache_file = False
    if cache_path.exists():
        cache_path.unlink()
        removed_cache_file = True

    article_deleted = 0
    weekly_deleted = 0
    if article_keys or weekly_key:
        from backend.news.db import get_connection

        with get_connection() as conn:
            for key in article_keys:
                result = conn.execute(
                    "DELETE FROM article_summary_cache WHERE article_key = ?",
                    (key,),
                )
                article_deleted += result.rowcount or 0
            if weekly_key:
                result = conn.execute(
                    "DELETE FROM weekly_summary_cache WHERE cache_key = ?",
                    (weekly_key,),
                )
                weekly_deleted += result.rowcount or 0
            conn.commit()

    return {
        "removed_cache_file": removed_cache_file,
        "article_summary_deleted": article_deleted,
        "weekly_summary_deleted": weekly_deleted,
        "trend_cache_deleted": 0,
    }


# SEC source type identifier
_SEC_SOURCE_TYPE = "sec_filing_rss"


# _pick_top_news removed — ranking.build_top_news() is used directly in _build_top_news_with_summaries()


# ---------------------------------------------------------------------------
# SEC separation helper
# ---------------------------------------------------------------------------

def _split_sec_items(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split a flat item list into (news_items, sec_items).

    news_items: everything except sec_filing_rss
    sec_items:  only sec_filing_rss entries
    """
    news: list[dict] = []
    sec: list[dict] = []
    for item in items:
        if item.get("source_type") == _SEC_SOURCE_TYPE:
            sec.append(item)
        else:
            news.append(item)
    return news, sec


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------

def _empty_weekly_meta() -> dict:
    return {
        "weekly_summary": "",
        "summary_version": "v2",
        "summary_status": "failed",
        "summary_source": "llm_with_article_summaries",
        "source_item_count": 0,
        "summary_ready_count": 0,
        "fallback_count": 0,
    }


def _build_response(
    items: list[dict],
    top_news: Optional[list[dict]] = None,
    weekly_summary_meta: Optional[dict] = None,
    trending_clusters: Optional[list[dict]] = None,
    sec_items: Optional[list[dict]] = None,
    refresh_required: bool = False,
    diagnostics: Optional[dict] = None,
) -> dict:
    """Build the Phase 3 standard response envelope.

    weekly_summary_meta is the full dict from summarizer (Phase 3 Part 2).
    For backwards compatibility the top-level weekly_summary string is still
    included alongside the richer weekly_summary_meta object.
    """
    meta = weekly_summary_meta if weekly_summary_meta is not None else _empty_weekly_meta()
    resp: dict = {
        "items": items,
        "top_news": top_news if top_news is not None else ranking.build_top_news(items),
        "weekly_summary": meta.get("weekly_summary", ""),
        "weekly_summary_meta": meta,
        "trending": trending_clusters if trending_clusters is not None else [],
        "sec_items": sec_items if sec_items is not None else [],
        "refresh_required": refresh_required,
    }
    if diagnostics:
        resp["diagnostics"] = diagnostics
    return resp


def _empty_response(
    refresh_required: bool = True,
    diagnostics: Optional[dict] = None,
) -> dict:
    return _build_response([], top_news=[], weekly_summary_meta=None, trending_clusters=[], sec_items=[], refresh_required=refresh_required, diagnostics=diagnostics)


async def _build_top_news_with_summaries(
    news_items: list[dict],
    company=None,
    force_summarize: bool = False,
) -> tuple[list[dict], dict]:
    """Pick top news via ranking, then enrich with LLM summaries (async wrapper).

    LLM calls are synchronous; we run them in a thread to avoid blocking the
    event loop.

    Returns (enriched_top_news, weekly_summary_meta).
    """
    top = ranking.build_top_news(news_items, company=company)
    if not top:
        return [], _empty_weekly_meta()
    enriched, weekly_meta = await asyncio.to_thread(
        summarizer.enrich_top_news_with_summaries, top, force_summarize
    )
    return enriched, weekly_meta


def _serialize_news_items(items: list[NewsItem]) -> list[dict]:
    return [item.to_dict() for item in items]


def _repair_cached_items(items: list[dict]) -> tuple[list[dict], bool]:
    """Self-heal cached items after canonical-url or exact-dedup rule changes.

    This keeps old cache files usable after Part 1 dedup fixes without requiring
    a manual force refresh.
    """
    hydrated = [
        NewsItem.from_dict(item)
        for item in items
        if isinstance(item, dict)
    ]
    for item in hydrated:
        item.canonical_url = compute_canonical_url(item.url)
        if not item.matched_intents and item.intent:
            item.matched_intents = [item.intent]
            item.match_count = 1
    repaired = pipeline.sort_by_recency(pipeline.deduplicate_exact_items(hydrated))
    serialized = _serialize_news_items(repaired)
    return serialized, serialized != items


def _build_reason(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


_EMPTY_PIPELINE_DIAG: dict = {
    "raw_items": 0,
    "after_normalize": 0,
    "after_exact_dedup": 0,
    "after_age_filter": 0,
    "final_items": 0,
    "dropped_in_normalize": 0,
    "dropped_in_exact_dedup": 0,
    "dropped_in_age_filter": 0,
}


def _build_force_refresh_diagnostics(
    *,
    status: str,
    fetch: Optional[dict] = None,
    pipeline_diag: Optional[dict] = None,
    message: Optional[str] = None,
) -> dict:
    brave = (fetch or {}).get("brave") or {}
    rss = (fetch or {}).get("rss") or {}
    pipeline_info = pipeline_diag or _EMPTY_PIPELINE_DIAG

    reasons: list[dict[str, str]] = []

    brave_attempted = int(brave.get("attempted") or 0)
    brave_failed = int(brave.get("failed") or 0)
    brave_items_found = int(brave.get("items_found") or 0)
    if brave_failed:
        reasons.append(
            _build_reason(
                "brave_fetch_failed",
                f"{brave_failed}/{brave_attempted} Brave queries failed",
            )
        )
    elif brave_attempted and brave_items_found == 0:
        reasons.append(
            _build_reason("brave_empty", "Brave returned 0 items")
        )

    rss_attempted = int(rss.get("attempted") or 0)
    rss_failed = int(rss.get("failed") or 0)
    rss_items_found = int(rss.get("items_found") or 0)
    if rss_failed:
        reasons.append(
            _build_reason(
                "rss_fetch_failed",
                f"{rss_failed}/{rss_attempted} RSS feeds failed",
            )
        )
    elif rss_attempted and rss_items_found == 0:
        reasons.append(
            _build_reason("rss_empty", "RSS returned 0 items")
        )

    raw_items = int(pipeline_info.get("raw_items") or 0)
    final_items = int(pipeline_info.get("final_items") or 0)
    if raw_items > 0 and final_items == 0:
        reasons.append(
            _build_reason(
                "pipeline_filtered_all",
                f"Pipeline filtered all {raw_items} fetched items",
            )
        )

    diagnostics: dict[str, Any] = {
        "status": status,
        "reasons": reasons,
        "sources": {
            "brave": brave,
            "rss": rss,
        },
        "pipeline": pipeline_info,
    }
    if message:
        diagnostics["message"] = message
    return diagnostics


# ---------------------------------------------------------------------------
# Company news
# ---------------------------------------------------------------------------

async def get_company_news(
    ticker: str,
    force_refresh: bool = False,
) -> dict:
    """Return cached or freshly fetched news for a single company.

    force_refresh=False (default): read disk cache.
      - Cache hit (fresh): return cached items.
      - Cache miss or stale: return empty list with refresh_required=True.
    force_refresh=True: fetch live, run pipeline, write cache.
      - 0 items after pipeline: do NOT write cache; return diagnostics.
    """
    cache_path = _company_cache_path(ticker)
    company = get_company(ticker)

    if not force_refresh:
        payload = _read_cache(cache_path)
        if payload and _is_cache_fresh(payload):
            all_items = payload.get("items") or []
            repaired_items, changed = _repair_cached_items(all_items)
            if changed:
                payload["items"] = repaired_items
                _write_cache(cache_path, payload)
                logger.info("Repaired cached items for %s after dedup/canonical-url update", ticker)
                all_items = repaired_items
            news_items, sec_items = _split_sec_items(all_items)
            top_news, weekly_summary = await _build_top_news_with_summaries(news_items, company=company)
            return _build_response(
                news_items,
                top_news=top_news,
                weekly_summary_meta=weekly_summary,
                trending_clusters=[],  # trending only in aggregate view
                sec_items=sec_items,
                refresh_required=False,
            )
        return _empty_response(refresh_required=True)

    # ── Force refresh path ────────────────────────────────────────────────────
    if company is None:
        logger.warning("Ticker %s not found in registry", ticker)
        return _empty_response(
            refresh_required=False,
            diagnostics={"status": "fetch_failed", "message": f"Ticker {ticker} not registered"},
        )

    params = query_engine.build_query_params(ticker)
    rss_feeds = query_engine.get_rss_feeds(ticker)

    raw_items: list[dict] = []
    fetch_diagnostics: dict = {}
    try:
        raw_items, fetch_diagnostics = await fetcher.fetch_company_news(
            ticker, params, rss_feeds
        )
    except Exception as exc:
        # Unexpected error in fetcher itself (not just a per-source failure)
        logger.error("Fetch failed for %s: %s", ticker, exc)
        return _empty_response(
            refresh_required=False,
            diagnostics={"status": "fetch_failed", "message": str(exc)},
        )

    brave_failed = int(fetch_diagnostics.get("brave", {}).get("failed") or 0)
    rss_failed = int(fetch_diagnostics.get("rss", {}).get("failed") or 0)
    any_failed = bool(brave_failed or rss_failed)

    # All source attempts failed and nothing came back
    if any_failed and not raw_items:
        logger.warning("All fetch attempts failed for %s", ticker)
        return _empty_response(
            refresh_required=False,
            diagnostics=_build_force_refresh_diagnostics(
                status="fetch_failed",
                fetch=fetch_diagnostics,
                pipeline_diag=_EMPTY_PIPELINE_DIAG,
                message="All Brave/RSS sources failed",
            ),
        )

    items, pipeline_diagnostics = pipeline.run_with_diagnostics(raw_items)

    if not items:
        logger.warning("Force refresh returned 0 items after pipeline for %s", ticker)
        return _empty_response(
            refresh_required=False,
            diagnostics=_build_force_refresh_diagnostics(
                status="no_news",
                fetch=fetch_diagnostics,
                pipeline_diag=pipeline_diagnostics,
                message="Fetched items did not produce any final news",
            ),
        )

    serialized_items = _serialize_news_items(items)

    # Cache stores all items (news + sec) together; separation happens at read time
    payload = {
        "ticker": ticker.upper(),
        "items": serialized_items,
        "timestamp": _now_iso(),
    }
    _write_cache(cache_path, payload)
    logger.info("Cached %d items for %s", len(items), ticker)

    news_items, sec_items = _split_sec_items(serialized_items)
    top_news, weekly_summary = await _build_top_news_with_summaries(
        news_items, company=company, force_summarize=True
    )

    return _build_response(
        news_items,
        top_news=top_news,
        weekly_summary_meta=weekly_summary,
        trending_clusters=[],  # trending only in aggregate view
        sec_items=sec_items,
        refresh_required=False,
        diagnostics=_build_force_refresh_diagnostics(
            status="ok",
            fetch=fetch_diagnostics,
            pipeline_diag=pipeline_diagnostics,
        ),
    )


# ---------------------------------------------------------------------------
# All companies (aggregate view — no force_refresh support in Phase 1)
# ---------------------------------------------------------------------------

async def get_all_companies_news() -> dict:
    """Return aggregated news from all registered companies' disk caches.

    Rules (Phase 1 §12.2):
    - Only reads from per-company caches; never triggers a live fetch.
    - Partial results are allowed: returns what's available.
    - If no company has a cache, returns empty list with refresh_required=True.
    - Items from all companies are merged and sorted by recency.
    """
    companies = list_companies()
    all_items: list[dict] = []
    missing: list[str] = []

    for company in companies:
        ticker = company.ticker
        payload = _read_cache(_company_cache_path(ticker))
        if payload and _is_cache_fresh(payload):
            company_items = payload.get("items") or []
            all_items.extend(company_items)
        else:
            missing.append(ticker)

    if missing:
        logger.debug("Missing or stale caches for: %s", ", ".join(missing))

    if not all_items and missing:
        # No caches at all
        return _empty_response(
            refresh_required=True,
            diagnostics={
                "status": "no_news",
                "missing_companies": missing,
            },
        )

    # Sort merged list by recency
    def sort_key(item: dict) -> tuple[int, float]:
        dt = parse_published_dt(item.get("published", ""))
        return (1 if dt else 0, dt.timestamp() if dt else 0.0)

    all_items.sort(key=sort_key, reverse=True)

    news_items, sec_items = _split_sec_items(all_items)
    top_news, weekly_summary = await _build_top_news_with_summaries(news_items)
    trending_clusters = await trending.build_trending_async(news_items)

    resp = _build_response(
        news_items,
        top_news=top_news,
        weekly_summary_meta=weekly_summary,
        trending_clusters=trending_clusters,
        sec_items=sec_items,
        refresh_required=False,
    )
    if missing:
        resp["diagnostics"] = {"missing_companies": missing}
    return resp
