"""LLM-powered summary generation for Top News items (Phase 3 Part 2).

Two summary types:
    1. Per-article summary   — 1 sentence explaining why this article matters
    2. Weekly group summary  — 2-3 sentences summarising the main themes across Top News

Phase 3 upgrades (§六):
    - summary_version: v2 for all newly generated summaries (old cache = v1)
    - summary_status: ready | failed | fallback_used
    - Weekly summary input uses three-tier fallback: article summary > description > title
    - Weekly summary response includes completeness metadata:
        source_item_count, summary_ready_count, fallback_count

Cache tables: article_summary_cache, weekly_summary_cache (SQLite, news_config.db)
LLM calls run via llm_complete(model_key="fast") — non-blocking on failure.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from backend.news.db import get_connection

logger = logging.getLogger(__name__)

SUMMARY_VERSION = "v2"

_ARTICLE_SYSTEM = """You are a financial news analyst writing one-sentence summaries for an EMS (Electronics Manufacturing Services) industry intelligence dashboard.

Rules:
- Write exactly 1 sentence, 40-60 English words.
- Do NOT simply restate the headline. The headline already says what happened.
- Your sentence must add context: the financial impact, demand signal, customer or industry backdrop, or why this item belongs in Top News.
- Prioritise: earnings/revenue impact, capacity or demand signals, customer relationships, supply chain implications, or macro factors that affect EMS manufacturers.
- Write in plain declarative English. No bullet points, no markdown, no quotation marks around the whole sentence.
- If the article relates to data center build-out, AI infrastructure, power, cooling, or networking — mention the EMS supply-chain angle specifically."""

_WEEKLY_SYSTEM = """You are a financial news analyst writing a brief weekly overview for an EMS (Electronics Manufacturing Services) industry intelligence dashboard.

Rules:
- Write 2-3 sentences total.
- Synthesise the main themes running across this week's Top News as a group — earnings, capacity signals, demand trends, supply chain shifts, or macro factors.
- Mention the most prominent companies or topics by name where relevant.
- Do NOT list every headline. Find the common thread and articulate it.
- Write in plain declarative English. No bullet points, no markdown."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _article_key(item: dict) -> str:
    return (item.get("canonical_url") or item.get("url") or "").strip()


def _weekly_cache_key(top_news_items: list[dict]) -> str:
    keys = sorted(_article_key(item) for item in top_news_items if _article_key(item))
    digest = hashlib.sha256("\n".join(keys).encode()).hexdigest()[:16]
    return f"weekly_{digest}"


# ---------------------------------------------------------------------------
# SQLite cache helpers
# ---------------------------------------------------------------------------

def _get_cached_article_summary(article_key: str) -> Optional[dict]:
    """Return cached summary record or None. Dict has summary, version, status, source."""
    if not article_key:
        return None
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT summary, summary_version, summary_status, summary_source FROM article_summary_cache WHERE article_key = ?",
                (article_key,),
            ).fetchone()
            if row:
                return {
                    "summary": row["summary"],
                    "summary_version": row["summary_version"] or "v1",
                    "summary_status": row["summary_status"] or "ready",
                    "summary_source": row["summary_source"] or "llm_from_metadata",
                }
            return None
    except Exception as exc:
        logger.debug("Cache read error for %s: %s", article_key[:60], exc)
        return None


def _set_cached_article_summary(article_key: str, summary: str, status: str = "ready") -> None:
    if not article_key or not summary:
        return
    try:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO article_summary_cache
                       (article_key, summary, summary_version, summary_status, summary_source, updated_at)
                   VALUES (?, ?, ?, ?, 'llm_from_metadata', ?)
                   ON CONFLICT(article_key) DO UPDATE SET
                       summary = excluded.summary,
                       summary_version = excluded.summary_version,
                       summary_status = excluded.summary_status,
                       summary_source = excluded.summary_source,
                       updated_at = excluded.updated_at""",
                (article_key, summary, SUMMARY_VERSION, status, _now_iso()),
            )
    except Exception as exc:
        logger.warning("Cache write error for %s: %s", article_key[:60], exc)


def _get_cached_weekly_summary(cache_key: str) -> Optional[dict]:
    """Return cached weekly summary record or None."""
    try:
        with get_connection() as conn:
            row = conn.execute(
                """SELECT summary, summary_version, summary_status,
                          source_item_count, summary_ready_count, fallback_count
                   FROM weekly_summary_cache WHERE cache_key = ?""",
                (cache_key,),
            ).fetchone()
            if row:
                return {
                    "weekly_summary": row["summary"],
                    "summary_version": row["summary_version"] or "v1",
                    "summary_status": row["summary_status"] or "ready",
                    "summary_source": "llm_with_article_summaries",
                    "source_item_count": row["source_item_count"] or 0,
                    "summary_ready_count": row["summary_ready_count"] or 0,
                    "fallback_count": row["fallback_count"] or 0,
                }
            return None
    except Exception as exc:
        logger.debug("Weekly cache read error: %s", exc)
        return None


def _set_cached_weekly_summary(
    cache_key: str,
    summary: str,
    status: str,
    source_item_count: int,
    summary_ready_count: int,
    fallback_count: int,
) -> None:
    if not summary:
        return
    try:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO weekly_summary_cache
                       (cache_key, summary, summary_version, summary_status,
                        source_item_count, summary_ready_count, fallback_count, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(cache_key) DO UPDATE SET
                       summary = excluded.summary,
                       summary_version = excluded.summary_version,
                       summary_status = excluded.summary_status,
                       source_item_count = excluded.source_item_count,
                       summary_ready_count = excluded.summary_ready_count,
                       fallback_count = excluded.fallback_count,
                       updated_at = excluded.updated_at""",
                (cache_key, summary, SUMMARY_VERSION, status,
                 source_item_count, summary_ready_count, fallback_count, _now_iso()),
            )
    except Exception as exc:
        logger.warning("Weekly cache write error: %s", exc)


# ---------------------------------------------------------------------------
# LLM generation
# ---------------------------------------------------------------------------

def _generate_article_summary(item: dict) -> str:
    """Call LLM to generate a one-sentence summary for a single news item."""
    from backend.core.llm_client import llm_complete

    title = (item.get("title") or "").strip()
    description = (item.get("description") or "").strip()
    source = (item.get("source") or "").strip()
    published = (item.get("published") or "").strip()
    company = (item.get("company") or "").strip()

    if not title:
        return ""

    parts = [f"Headline: {title}"]
    if description:
        parts.append(f"Description: {description[:400]}")
    if source:
        parts.append(f"Source: {source}")
    if published:
        parts.append(f"Published: {published}")
    if company:
        parts.append(f"Company: {company}")

    user_content = "\n".join(parts)

    try:
        result = llm_complete(
            messages=[{"role": "user", "content": user_content}],
            system=_ARTICLE_SYSTEM,
            model_key="fast",
            max_tokens=120,
        )
        return (result or "").strip()
    except Exception as exc:
        logger.warning("LLM article summary failed for '%s': %s", title[:50], exc)
        return ""


def _generate_weekly_summary(input_lines: list[str]) -> str:
    """Call LLM to generate a 2-3 sentence overview from pre-built input lines."""
    from backend.core.llm_client import llm_complete

    if not input_lines:
        return ""

    user_content = "Top News this week:\n" + "\n".join(input_lines)

    try:
        result = llm_complete(
            messages=[{"role": "user", "content": user_content}],
            system=_WEEKLY_SYSTEM,
            model_key="fast",
            max_tokens=200,
        )
        return (result or "").strip()
    except Exception as exc:
        logger.warning("LLM weekly summary failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_top_news_with_summaries(
    top_news_items: list[dict],
    force: bool = False,
) -> tuple[list[dict], dict]:
    """Add per-article summaries and generate weekly group summary.

    Phase 3 Part 2 changes:
    - Each enriched item carries summary_version and summary_status.
    - Weekly summary input uses three-tier fallback: article summary > description > title.
    - Returns a full weekly_summary_meta dict instead of a plain string.

    Args:
        top_news_items: List of top news item dicts (already ranked).
        force:          If True, bypass cache and regenerate all summaries.

    Returns:
        (enriched_items, weekly_summary_meta)
        enriched_items: Same list with summary / summary_version / summary_status added.
        weekly_summary_meta: {
            weekly_summary, summary_version, summary_status, summary_source,
            source_item_count, summary_ready_count, fallback_count
        }
    """
    enriched: list[dict] = []
    summary_ready_count = 0
    fallback_count = 0

    for item in top_news_items:
        key = _article_key(item)
        cached = None if force else _get_cached_article_summary(key)

        if cached is not None:
            summary = cached["summary"]
            s_version = cached["summary_version"]
            s_status = cached["summary_status"]
            s_source = cached.get("summary_source") or "llm_from_metadata"
        else:
            summary = _generate_article_summary(item)
            s_status = "ready" if summary else "failed"
            s_version = SUMMARY_VERSION
            s_source = "llm_from_metadata"
            if summary:
                _set_cached_article_summary(key, summary, status=s_status)

        if summary:
            summary_ready_count += 1

        enriched.append({
            **item,
            "summary": summary,
            "summary_version": s_version,
            "summary_status": s_status,
            "summary_source": s_source,
        })

    # --- Build weekly summary input with three-tier fallback (§6.3.1) ---
    source_item_count = len(enriched)
    weekly_input_lines: list[str] = []
    weekly_fallback_count = 0

    for i, item in enumerate(enriched, 1):
        title = (item.get("title") or "").strip()
        description = (item.get("description") or "").strip()
        article_summary = (item.get("summary") or "").strip()
        source = (item.get("source") or "").strip()
        company = (item.get("company") or "").strip()

        if article_summary:
            primary_text = article_summary
            used_fallback = False
        elif description:
            primary_text = description[:200]
            used_fallback = True
        elif title:
            primary_text = title
            used_fallback = True
        else:
            continue  # skip items with no usable text

        if used_fallback:
            weekly_fallback_count += 1

        meta = " | ".join(filter(None, [source, company]))
        line = f"{i}. {primary_text}" + (f" ({meta})" if meta else "")
        weekly_input_lines.append(line)

    # Determine weekly summary status (§6.3.2)
    if summary_ready_count < 4:
        weekly_status = "failed"
    elif weekly_fallback_count > 0:
        weekly_status = "fallback_used"
    else:
        weekly_status = "ready"

    # Retrieve or generate weekly summary
    weekly_key = _weekly_cache_key(top_news_items)
    cached_weekly = None if force else _get_cached_weekly_summary(weekly_key)

    if cached_weekly is not None:
        weekly_meta = cached_weekly
    elif weekly_status == "failed" or not weekly_input_lines:
        weekly_meta = {
            "weekly_summary": "",
            "summary_version": SUMMARY_VERSION,
            "summary_status": "failed",
            "summary_source": "llm_with_article_summaries",
            "source_item_count": source_item_count,
            "summary_ready_count": summary_ready_count,
            "fallback_count": weekly_fallback_count,
        }
    else:
        weekly_text = _generate_weekly_summary(weekly_input_lines)
        actual_status = weekly_status if weekly_text else "failed"
        _set_cached_weekly_summary(
            weekly_key,
            weekly_text,
            status=actual_status,
            source_item_count=source_item_count,
            summary_ready_count=summary_ready_count,
            fallback_count=weekly_fallback_count,
        )
        weekly_meta = {
            "weekly_summary": weekly_text,
            "summary_version": SUMMARY_VERSION,
            "summary_status": actual_status,
            "summary_source": "llm_with_article_summaries",
            "source_item_count": source_item_count,
            "summary_ready_count": summary_ready_count,
            "fallback_count": weekly_fallback_count,
        }

    return enriched, weekly_meta
