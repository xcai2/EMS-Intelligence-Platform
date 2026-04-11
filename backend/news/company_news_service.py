"""Company-news orchestration for the News domain."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from backend.core.config import COMPANIES
from backend.news.filtering import CATEGORIES
from backend.news.news_filters import dedupe_items, normalize_result
from backend.news.news_filter_policies import build_company_news_response, filter_company_news_items
from backend.news.normalizer import filter_items_by_max_age, sort_items_by_recency_and_relevance
from backend.news.query_helpers import build_company_alias_query
from backend.news.sources import FALLBACK_COMPANY_NEWS, OFFICIAL_COMPANY_SOURCES
from backend.rag.web_search import search_web_with_diagnostics

if TYPE_CHECKING:
    from backend.news.service import NewsFeed


COMPANY_FALLBACK_MIN_THRESHOLD = 3
CATEGORY_ALIAS_QUERY_LIMIT = 3
CATEGORY_RAW_TARGET_MULTIPLIER = 2
CATEGORY_RAW_TARGET_PADDING = 20
CATEGORY_RAW_TARGET_MIN = 40
CATEGORY_RAW_TARGET_MAX = 120
CANDIDATE_MERGE_CAP_MULTIPLIER = 3
CANDIDATE_MERGE_CAP_MIN = 90
CANDIDATE_MERGE_CAP_MAX = 300
MIN_COMPANY_CANDIDATE_LIMIT = 20
MAX_COMPANY_CANDIDATE_LIMIT = 50
OFFICIAL_SOURCE_MIN_RESULTS = 8
PUBLIC_BOARD_MIN_RESULTS = 10
SEARCH_QUERY_MIN_RESULTS = 10
GOOGLE_RSS_MIN_RESULTS = 12
ALL_COMPANIES_AGGREGATE_CACHE_PREFIX = "all:"
UNBOUNDED_COMPANY_RESPONSE_FETCH_TARGET = 100
COMPANY_SOURCE_BUCKET_ORDER = (
    "official",
    "public_board",
    "brave",
    "google_rss",
)
COMPANY_FINAL_SOURCE_ORDER = (
    *COMPANY_SOURCE_BUCKET_ORDER,
    "fallback",
)
COMPANY_QUERY_PATTERNS = (
    # Broad company-news discovery for general external coverage.
    ("broad_news", "news"),
    # Corporate release / IR style coverage that often carries the cleanest company signal.
    ("official_releases", '("press release" OR announcement OR earnings OR "investor relations")'),
    # Newsroom-style surfaces that catch media-center and press-page mentions.
    ("newsroom_channels", '(newsroom OR press OR "media center" OR "news release")'),
)


def build_company_news_queries(feed: "NewsFeed", ticker: str, company_name: str) -> list[str]:
    """Build the broad company-search query set used across external search sources."""
    alias_or = build_company_alias_query(
        ticker,
        company_name,
        limit=CATEGORY_ALIAS_QUERY_LIMIT,
    )
    cleaned_alias_or = " ".join((alias_or or "").split()).strip()
    if not cleaned_alias_or:
        return []
    return [f"({cleaned_alias_or}) {query_suffix}" for _intent, query_suffix in COMPANY_QUERY_PATTERNS]


def _prepare_company_queries(feed: "NewsFeed", ticker: str, company_name: str) -> list[str]:
    """Drop empty or duplicate search queries before fan-out."""
    prepared: list[str] = []
    seen = set()
    for query in build_company_news_queries(feed, ticker, company_name):
        cleaned = " ".join((query or "").split()).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        prepared.append(cleaned)
    return prepared


async def _gather_query_results(
    query_tasks: list[tuple[str, Awaitable[tuple[list[dict], str | None]]]],
) -> tuple[list[tuple[str, list[dict]]], dict[str, str], dict[str, dict[str, Any]]]:
    """Run query fan-out without letting one task abort the whole batch."""
    responses = await asyncio.gather(
        *(task for _, task in query_tasks),
        return_exceptions=True,
    )

    query_batches: list[tuple[str, list[dict]]] = []
    query_errors: dict[str, str] = {}
    query_diagnostics: dict[str, dict[str, Any]] = {}

    for (query, _task), response in zip(query_tasks, responses):
        query_diagnostics[query] = {
            "query": query,
            "response_ok": False,
            "raw_results": 0,
            "normalized_results": 0,
            "error": None,
        }
        if isinstance(response, Exception):
            error_message = f"{type(response).__name__}: {response}"
            query_errors[query] = error_message
            query_diagnostics[query]["error"] = error_message
            continue

        if not isinstance(response, tuple):
            error_message = f"Unexpected response type: expected tuple, got {type(response).__name__}"
            query_errors[query] = error_message
            query_diagnostics[query]["error"] = error_message
            continue
        if len(response) != 2:
            error_message = f"Unexpected response shape: expected 2 items, got {len(response)}"
            query_errors[query] = error_message
            query_diagnostics[query]["error"] = error_message
            continue
        if not isinstance(response[0], list):
            error_message = f"Unexpected response payload: first item should be list, got {type(response[0]).__name__}"
            query_errors[query] = error_message
            query_diagnostics[query]["error"] = error_message
            continue
        if any(not isinstance(item, dict) for item in response[0]):
            bad_item = next(item for item in response[0] if not isinstance(item, dict))
            error_message = (
                "Unexpected response payload: results list should contain dict items, "
                f"got {type(bad_item).__name__}"
            )
            query_errors[query] = error_message
            query_diagnostics[query]["error"] = error_message
            continue

        results, error = response
        query_diagnostics[query]["response_ok"] = True
        query_diagnostics[query]["raw_results"] = len(results)
        query_batches.append((query, results))
        if error is None:
            normalized_error = None
        elif isinstance(error, str):
            normalized_error = error or None
        else:
            normalized_error = f"{type(error).__name__}: {error}"
        if normalized_error is not None:
            query_errors[query] = normalized_error
            query_diagnostics[query]["error"] = normalized_error

    return query_batches, query_errors, query_diagnostics


def _compute_raw_target_count(count: int, category: Optional[str]) -> int:
    """Smooth raw-candidate expansion for category-filtered reads."""
    if not category:
        return count
    return min(
        max(
            count * CATEGORY_RAW_TARGET_MULTIPLIER,
            count + CATEGORY_RAW_TARGET_PADDING,
            CATEGORY_RAW_TARGET_MIN,
        ),
        CATEGORY_RAW_TARGET_MAX,
    )


def _compute_candidate_merge_cap(raw_target_count: int) -> int:
    """Cap merged normalized candidates so multi-source fan-out stays bounded."""
    return min(
        max(
            raw_target_count * CANDIDATE_MERGE_CAP_MULTIPLIER,
            CANDIDATE_MERGE_CAP_MIN,
        ),
        CANDIDATE_MERGE_CAP_MAX,
    )


def _get_company_candidate_limit(requested_count: int) -> int:
    """Keep broad company fetches large enough for local filtering without exploding fan-out."""
    return min(max(requested_count, MIN_COMPANY_CANDIDATE_LIMIT), MAX_COMPANY_CANDIDATE_LIMIT)


def _minimum_company_news_threshold(count: int) -> int:
    """Fallback when the kept company-news set is too thin to be useful."""
    return max(1, min(COMPANY_FALLBACK_MIN_THRESHOLD, count))


def _item_identity_key(item: dict) -> tuple[str, str]:
    """Build the stable URL/title identity used for service-level source tracing."""
    return (
        (item.get("url") or "").strip().lower(),
        (item.get("title") or "").strip().lower(),
    )


def _empty_source_count_map(source_order: tuple[str, ...]) -> dict[str, int]:
    """Create a zeroed source-count mapping for diagnostics bookkeeping."""
    return {source_name: 0 for source_name in source_order}


def _normalize_results_batch(feed: "NewsFeed", raw_results: list[dict], company_name: str) -> list[dict]:
    """Normalize a raw batch into a source-local bucket before global merge."""
    normalized_items: list[dict] = []
    for result in raw_results:
        normalized = normalize_result(feed, result, company_name)
        if normalized:
            normalized_items.append(normalized)
    return normalized_items


def _merge_source_buckets_first_win_with_trace(
    source_buckets: dict[str, list[dict]],
    source_order: tuple[str, ...],
) -> tuple[list[dict], dict[str, int], dict[tuple[str, str], str]]:
    """Merge source buckets by exact identity with source-order first-win semantics."""
    merged_items: list[dict] = []
    kept_counts = _empty_source_count_map(source_order)
    winning_source_by_key: dict[tuple[str, str], str] = {}
    seen_keys: set[tuple[str, str]] = set()

    for source_name in source_order:
        for item in source_buckets.get(source_name, []):
            identity_key = _item_identity_key(item)
            if identity_key in seen_keys:
                continue
            seen_keys.add(identity_key)
            winning_source_by_key[identity_key] = source_name
            kept_counts[source_name] += 1
            merged_items.append(item)

    return merged_items, kept_counts, winning_source_by_key


def _count_items_by_source(
    items: list[dict],
    winning_source_by_key: dict[tuple[str, str], str],
    source_order: tuple[str, ...],
) -> dict[str, int]:
    """Count items by the source bucket that won them during merge."""
    counts = _empty_source_count_map(source_order)
    for item in items:
        source_name = winning_source_by_key.get(_item_identity_key(item))
        if source_name in counts:
            counts[source_name] += 1
    return counts


def _build_source_flow_diagnostics(
    *,
    raw_counts: dict[str, int],
    normalized_source_buckets: dict[str, list[dict]],
    merged_source_counts: dict[str, int],
    capped_source_counts: dict[str, int],
    pre_fallback_kept_source_counts: dict[str, int],
    final_kept_source_counts: dict[str, int],
) -> dict[str, dict[str, int]]:
    """Summarize per-source candidate loss from raw fetch to final kept items."""
    source_flow: dict[str, dict[str, int]] = {}
    for source_name in COMPANY_SOURCE_BUCKET_ORDER:
        raw_count = int(raw_counts.get(source_name, 0) or 0)
        normalized_count = len(normalized_source_buckets.get(source_name, []))
        merged_candidate_count = int(merged_source_counts.get(source_name, 0) or 0)
        capped_candidate_count = int(capped_source_counts.get(source_name, 0) or 0)
        pre_fallback_kept_count = int(pre_fallback_kept_source_counts.get(source_name, 0) or 0)
        final_kept_count = int(final_kept_source_counts.get(source_name, 0) or 0)

        source_flow[source_name] = {
            "raw_count": raw_count,
            "normalized_count": normalized_count,
            "dropped_during_normalize": max(raw_count - normalized_count, 0),
            "merged_candidate_count": merged_candidate_count,
            "dropped_during_merge": max(normalized_count - merged_candidate_count, 0),
            "capped_candidate_count": capped_candidate_count,
            "dropped_during_cap": max(merged_candidate_count - capped_candidate_count, 0),
            "pre_fallback_kept_count": pre_fallback_kept_count,
            "dropped_during_filter": max(capped_candidate_count - pre_fallback_kept_count, 0),
            "final_kept_count": final_kept_count,
            "added_after_fallback": max(final_kept_count - pre_fallback_kept_count, 0),
        }
    return source_flow


def _build_fallback_flow_diagnostics(
    *,
    fallback_used: bool,
    fallback_raw_count: int,
    fallback_normalized_items: list[dict],
    fallback_final_candidate_count: int,
    fallback_final_kept_count: int,
) -> dict[str, int | bool]:
    """Summarize how much the fallback source actually contributed after the main pipeline."""
    normalized_count = len(fallback_normalized_items)
    return {
        "used": fallback_used,
        "raw_count": fallback_raw_count,
        "normalized_count": normalized_count,
        "dropped_during_normalize": max(fallback_raw_count - normalized_count, 0),
        "final_candidate_count": fallback_final_candidate_count,
        "dropped_against_existing_candidates": max(normalized_count - fallback_final_candidate_count, 0),
        "final_kept_count": fallback_final_kept_count,
        "dropped_during_filter": max(fallback_final_candidate_count - fallback_final_kept_count, 0),
    }


async def _collect_query_source_results(
    feed: "NewsFeed",
    company_queries: list[str],
    company_name: str,
    *,
    queries_empty: bool,
    task_factory: Callable[[str], Awaitable[tuple[list[dict], str | None]]],
    aggregator: str | None = None,
) -> tuple[list[dict], list[dict], dict[str, str], dict[str, dict[str, Any]], int]:
    """Run a query source fan-out and keep normalized results source-local until merge time."""
    if queries_empty:
        return [], [], {}, {}, 0

    query_tasks = [(query, task_factory(query)) for query in company_queries]
    query_batches, query_errors, query_diagnostics = await _gather_query_results(query_tasks)

    source_results: list[dict] = []
    normalized_source_items: list[dict] = []
    for query, result_batch in query_batches:
        if aggregator:
            for result in result_batch:
                result.setdefault("aggregator", aggregator)
        source_results.extend(result_batch)
        normalized_batch = _normalize_results_batch(feed, result_batch, company_name)
        normalized_source_items.extend(normalized_batch)
        query_diagnostics[query]["normalized_results"] = len(normalized_batch)

    normalized_count = sum(
        entry["normalized_results"] for entry in query_diagnostics.values()
    )
    return source_results, normalized_source_items, query_errors, query_diagnostics, normalized_count


async def build_company_news_payload(
    feed: "NewsFeed",
    ticker: str,
    category: Optional[str] = None,
    count: int = 10,
    force_refresh: bool = False,
) -> dict:
    """Fetch and assemble the broad company-linked news payload."""
    company = COMPANIES.get(ticker, {})
    company_name = company.get("name", ticker)
    planning_count = count if count > 0 else UNBOUNDED_COMPANY_RESPONSE_FETCH_TARGET
    raw_target_count = _compute_raw_target_count(planning_count, category)
    raw_cache_key = f"company:{ticker}:raw"
    cached_raw = feed._runtime_cache.get(raw_cache_key)
    if not force_refresh:
        if cached_raw:
            # Re-apply current filter rules to the cached item list so that any
            # changes to excluded_noise_terms, strict_title_match, or the
            # is_company_related_item() logic take effect immediately on restart,
            # without requiring a full force_refresh re-fetch.
            refiltered = filter_company_news_items(
                feed,
                filter_items_by_max_age(cached_raw.get("news", [])),
                ticker,
                company_name,
            )
            refiltered_raw = {
                **cached_raw,
                "news": refiltered,
                "final_kept_count": len(refiltered),
            }
            # Update in-memory cache so subsequent reads in this session are free.
            feed._runtime_cache[raw_cache_key] = refiltered_raw
            feed._persist_runtime_cache()
            return build_company_news_response(refiltered_raw, category, count, CATEGORIES)
        return build_company_news_response(
            {
                "ticker": ticker,
                "company_name": company_name,
                "collection_target_count": raw_target_count,
                "fetched_count": 0,
                "final_kept_count": 0,
                "news": [],
                "timestamp": feed._now_utc_iso(),
                "diagnostics": {
                    "cache_status": "miss",
                    "cache_only": True,
                    "refresh_required": True,
                },
            },
            category,
            count,
            CATEGORIES,
        )

    company_queries = _prepare_company_queries(feed, ticker, company_name)
    candidate_limit = _get_company_candidate_limit(raw_target_count)
    merge_cap = _compute_candidate_merge_cap(raw_target_count)
    company_queries_empty = not company_queries
    query_skip_reason = (
        "No prepared company queries were available after alias expansion and cleanup."
        if company_queries_empty
        else None
    )

    normalized_source_buckets: dict[str, list[dict]] = {
        source_name: []
        for source_name in COMPANY_FINAL_SOURCE_ORDER
    }
    normalized_counts = {
        "official": 0,
        "public_board": 0,
        "brave": 0,
        "google_rss": 0,
        "fallback": 0,
    }

    official_results, official_source_diagnostics = await feed.fetchers.official_company_news_with_diagnostics(
        ticker,
        company_name,
        limit=max(candidate_limit, OFFICIAL_SOURCE_MIN_RESULTS),
    )
    normalized_source_buckets["official"] = _normalize_results_batch(feed, official_results, company_name)
    normalized_counts["official"] = len(normalized_source_buckets["official"])

    source_cfg_raw = OFFICIAL_COMPANY_SOURCES.get(ticker)
    source_cfg = source_cfg_raw if isinstance(source_cfg_raw, dict) else {}
    public_news_url = source_cfg.get("public_news_url")
    public_results: list[dict] = []
    public_source_diagnostics: dict[str, object] = {
        "status": "not_configured",
        "ticker": ticker,
        "items_found": 0,
    }
    if public_news_url:
        public_results, public_source_diagnostics = await feed.fetchers.public_news_links_with_diagnostics(
            public_news_url,
            ticker,
            company_name,
            limit=max(candidate_limit, PUBLIC_BOARD_MIN_RESULTS),
        )
        normalized_source_buckets["public_board"] = _normalize_results_batch(feed, public_results, company_name)
        normalized_counts["public_board"] = len(normalized_source_buckets["public_board"])

    search_results, brave_normalized_results, brave_errors, brave_query_diagnostics, normalized_counts["brave"] = await _collect_query_source_results(
        feed,
        company_queries,
        company_name,
        queries_empty=company_queries_empty,
        task_factory=lambda query: search_web_with_diagnostics(
            query,
            count=max(candidate_limit, SEARCH_QUERY_MIN_RESULTS),
        ),
        aggregator="Brave Search",
    )
    normalized_source_buckets["brave"] = brave_normalized_results

    rss_results, google_rss_normalized_results, rss_errors, rss_query_diagnostics, normalized_counts["google_rss"] = await _collect_query_source_results(
        feed,
        company_queries,
        company_name,
        queries_empty=company_queries_empty,
        task_factory=lambda query: feed.fetchers.google_news_rss_with_diagnostics(
            query,
            limit=max(candidate_limit, GOOGLE_RSS_MIN_RESULTS),
        ),
    )
    normalized_source_buckets["google_rss"] = google_rss_normalized_results

    merged_candidates, merged_source_counts, winning_source_by_key = _merge_source_buckets_first_win_with_trace(
        normalized_source_buckets,
        COMPANY_SOURCE_BUCKET_ORDER,
    )
    merged_candidate_count = len(merged_candidates)
    capped_candidates = merged_candidates
    if merged_candidate_count > merge_cap:
        capped_candidates = sort_items_by_recency_and_relevance(capped_candidates)[:merge_cap]
    capped_candidate_count = len(capped_candidates)
    capped_source_counts = _count_items_by_source(
        capped_candidates,
        winning_source_by_key,
        COMPANY_SOURCE_BUCKET_ORDER,
    )

    recent_candidates = filter_items_by_max_age(capped_candidates)
    filtered_items = filter_company_news_items(feed, recent_candidates, ticker, company_name)
    pre_fallback_kept_count = len(filtered_items)
    pre_fallback_kept_source_counts = _count_items_by_source(
        filtered_items,
        winning_source_by_key,
        COMPANY_SOURCE_BUCKET_ORDER,
    )
    pre_fallback_source_counts = {
        **pre_fallback_kept_source_counts,
        "fallback": 0,
    }
    fallback_threshold = _minimum_company_news_threshold(planning_count)
    fallback_used = False
    fallback_raw_results = FALLBACK_COMPANY_NEWS.get(ticker, [])
    fallback_normalized_items: list[dict] = []
    fallback_final_candidate_count = 0
    fallback_final_kept_count = 0
    post_fallback_kept = 0
    if pre_fallback_kept_count < fallback_threshold:
        fallback_used = True
        fallback_normalized_items = _normalize_results_batch(
            feed,
            fallback_raw_results,
            company_name,
        )
        normalized_source_buckets["fallback"] = fallback_normalized_items
        normalized_counts["fallback"] = len(fallback_normalized_items)
        capped_bucket_items: dict[str, list[dict]] = {source_name: [] for source_name in COMPANY_SOURCE_BUCKET_ORDER}
        for item in capped_candidates:
            source_name = winning_source_by_key.get(_item_identity_key(item))
            if source_name in capped_bucket_items:
                capped_bucket_items[source_name].append(item)
        final_candidate_buckets: dict[str, list[dict]] = {
            **capped_bucket_items,
            "fallback": fallback_normalized_items,
        }
        final_candidate_pool, _final_candidate_counts, final_winning_source_by_key = _merge_source_buckets_first_win_with_trace(
            final_candidate_buckets,
            COMPANY_FINAL_SOURCE_ORDER,
        )
        fallback_final_candidate_count = _final_candidate_counts["fallback"]
        filtered_items = filter_company_news_items(
            feed,
            filter_items_by_max_age(final_candidate_pool),
            ticker,
            company_name,
        )
        final_kept_source_counts = _count_items_by_source(
            filtered_items,
            final_winning_source_by_key,
            COMPANY_FINAL_SOURCE_ORDER,
        )
        fallback_final_kept_count = final_kept_source_counts["fallback"]
        post_fallback_kept = len(filtered_items)
    else:
        final_kept_source_counts = {
            **pre_fallback_kept_source_counts,
            "fallback": 0,
        }

    normalized_total = sum(
        len(normalized_source_buckets[source_name])
        for source_name in COMPANY_SOURCE_BUCKET_ORDER
    )
    source_counts = {
        "official": len(official_results),
        "public_board": len(public_results),
        "brave": len(search_results),
        "google_rss": len(rss_results),
        "fallback": len(fallback_raw_results) if fallback_used else 0,
    }
    source_flow = _build_source_flow_diagnostics(
        raw_counts=source_counts,
        normalized_source_buckets=normalized_source_buckets,
        merged_source_counts=merged_source_counts,
        capped_source_counts=capped_source_counts,
        pre_fallback_kept_source_counts=pre_fallback_kept_source_counts,
        final_kept_source_counts=final_kept_source_counts,
    )
    fallback_flow = _build_fallback_flow_diagnostics(
        fallback_used=fallback_used,
        fallback_raw_count=source_counts["fallback"],
        fallback_normalized_items=fallback_normalized_items,
        fallback_final_candidate_count=fallback_final_candidate_count,
        fallback_final_kept_count=fallback_final_kept_count,
    )

    raw_result = {
        "ticker": ticker,
        "company_name": company_name,
        "collection_target_count": raw_target_count,
        "fetched_count": merged_candidate_count,
        "final_kept_count": len(filtered_items),
        "news": filtered_items,
        "timestamp": feed._now_utc_iso(),
        "diagnostics": {
            "source_counts": source_counts,
            "sources": {
                "official": official_source_diagnostics,
                "public_board": public_source_diagnostics,
            },
            "normalized_counts": normalized_counts,
            "source_flow": source_flow,
            "fallback_flow": fallback_flow,
            "pre_fallback_source_counts": pre_fallback_source_counts,
            "post_fallback_source_counts": final_kept_source_counts,
            "final_source_counts": final_kept_source_counts,
            "pipeline_counts": {
                "normalized_total": normalized_total,
                "merged_candidates": merged_candidate_count,
                "deduped_candidates": merged_candidate_count,
                "capped_candidates": capped_candidate_count,
                "pre_fallback_kept": pre_fallback_kept_count,
                "fallback_candidates_normalized": len(fallback_normalized_items),
                "post_fallback_kept": post_fallback_kept,
                "final_kept": len(filtered_items),
                "merge_strategy": "source_order_first_win_exact_identity",
            },
            "limits": {
                "candidate_limit_per_query": candidate_limit,
                "merge_cap": merge_cap,
                "fallback_threshold": fallback_threshold,
            },
            "query_plan": {
                "company_query_count": len(company_queries),
                "company_queries_empty": company_queries_empty,
                "company_queries": company_queries,
                "brave_skipped_reason": query_skip_reason if company_queries_empty else None,
                "google_rss_skipped_reason": query_skip_reason if company_queries_empty else None,
            },
            "fallback_used": fallback_used,
            "queries": {
                "brave": list(brave_query_diagnostics.values()),
                "google_rss": list(rss_query_diagnostics.values()),
            },
            "errors": {
                "brave": brave_errors or None,
                "google_rss": rss_errors or None,
            },
        },
    }
    feed._runtime_cache[raw_cache_key] = raw_result
    feed._invalidate_aggregate_cache(ALL_COMPANIES_AGGREGATE_CACHE_PREFIX)
    feed._persist_runtime_cache()
    return build_company_news_response(raw_result, category, count, CATEGORIES)
