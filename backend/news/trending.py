"""Trending topic clustering for Phase 3 Part 3.

Phase 3 upgrades over Phase 2:
  - Dynamic cluster discovery via lightweight title/keyword overlap (no fixed-theme cards)
  - Supporting article counts across three time windows: 7d / 30d / 60d
  - Stable trend_cluster_key = "{window_label}:{normalized_slug}" (§7.5.1)
  - LLM generates trend_title and trend_summary for each cluster (§7.7)
  - trend_summary_cache prevents repeated LLM calls for the same cluster
  - Returns 1–6 real clusters sorted by strength; does not pad with fake cards (§7.8)

Phase 2 baseline preserved:
  - sec_filing_rss is excluded from input before this layer
  - Phase 2 age filter (Brave ≤5 months, RSS ≤6 months) governs what enters the snapshot;
    7d/30d/60d are analysis windows on top of that, not new global age filters (§7.3)
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.news.db import get_connection
from backend.news.normalizer import parse_published_dt

logger = logging.getLogger(__name__)

MAX_TRENDING_CLUSTERS = 6
MAX_REPRESENTATIVE_ITEMS = 3
_MIN_CLUSTER_ITEMS = 2
_MIN_SHARED_TOKENS = 2
_CLUSTER_SIMILARITY_THRESHOLD = 0.25
_CLUSTER_MERGE_THRESHOLD = 0.4

# ---------------------------------------------------------------------------
# Slug normalisation (§7.5.1)
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "remains", "remain", "continue", "continues", "continued", "strong", "rising",
    "growing", "amid", "with", "as", "its", "their", "this", "that", "from",
    "by", "more", "new", "report", "reports", "says", "said",
})

_CANONICAL_PHRASES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bdata[\s\-]?centers?\b", re.I), "data-center"),
    (re.compile(r"\bai[\s\-]infra(?:structure)?\b", re.I), "ai-infrastructure"),
    (re.compile(r"\bartificial[\s\-]intelligence\b", re.I), "ai-infrastructure"),
    (re.compile(r"\bpower[\s\-]supply\b", re.I), "power-supply"),
    (re.compile(r"\bliquid[\s\-]cooling\b", re.I), "liquid-cooling"),
    (re.compile(r"\bthermal[\s\-]management\b", re.I), "thermal-management"),
    (re.compile(r"\bsupply[\s\-]chain\b", re.I), "supply-chain"),
]

_TOPIC_STOPWORDS: frozenset[str] = frozenset({
    "flex", "jabil", "celestica", "benchmark", "plexus", "sanmina",
    "ltd", "corp", "inc", "corporation", "company", "group", "holdings",
    "nasdaq", "nyse", "tsx", "stock", "news", "ems", "electronics", "manufacturing",
})


def _normalize_slug(text: str) -> str:
    """Convert a trend phrase to a stable kebab-case slug (§7.5.1)."""
    s = text.lower()
    # Apply canonical phrase replacements first
    for pattern, replacement in _CANONICAL_PHRASES:
        s = pattern.sub(replacement, s)
    # Strip punctuation except hyphens
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
    # Tokenise
    tokens = s.split()
    # Remove stopwords, keep max 4 core terms
    tokens = [t for t in tokens if t not in _STOPWORDS and t]
    tokens = tokens[:4]
    return "-".join(tokens) if tokens else "unknown"


def _trend_cluster_key(window_label: str, phrase: str) -> str:
    """Build a stable trend_cluster_key (§7.5)."""
    slug = _normalize_slug(phrase)
    return f"{window_label}:{slug}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _item_age_days(item: dict) -> Optional[float]:
    dt = parse_published_dt(item.get("published", ""))
    if dt is None:
        return None
    return (_now_utc() - dt).total_seconds() / 86400


def _count_in_window(items: list[dict], days: int) -> int:
    count = 0
    for item in items:
        age = _item_age_days(item)
        if age is None or age <= days:
            count += 1
    return count


def _extract_company(item: dict) -> Optional[str]:
    return item.get("company") or None


def _normalize_cluster_tokens(text: str) -> list[str]:
    s = text.lower()
    for pattern, replacement in _CANONICAL_PHRASES:
        s = pattern.sub(replacement, s)
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
    tokens = []
    for token in s.split():
        if (
            not token
            or token in _STOPWORDS
            or token in _TOPIC_STOPWORDS
            or len(token) <= 2
        ):
            continue
        tokens.append(token)
    return tokens


def _extract_phrase_hits(text: str) -> list[str]:
    lowered = text.lower()
    hits: list[str] = []
    for pattern, replacement in _CANONICAL_PHRASES:
        if pattern.search(lowered):
            hits.append(replacement)
    return hits


def _item_cluster_features(item: dict) -> dict:
    title = item.get("title") or ""
    description = item.get("description") or ""
    text = " ".join([title, description])
    tokens = _normalize_cluster_tokens(text)
    phrases = _extract_phrase_hits(text)
    return {
        "tokens": tokens,
        "token_set": set(tokens),
        "phrases": phrases,
    }


def _token_overlap(a: set[str], b: set[str]) -> tuple[float, int]:
    if not a or not b:
        return 0.0, 0
    intersection = len(a & b)
    union = len(a | b)
    return (intersection / union if union else 0.0), intersection


def _cluster_label(cluster: dict) -> str:
    phrase_counts: Counter[str] = cluster["phrase_counts"]
    if phrase_counts:
        top_phrases = [phrase for phrase, _ in phrase_counts.most_common(2)]
        return " ".join(top_phrases)

    token_counts: Counter[str] = cluster["token_counts"]
    if token_counts:
        label_tokens = [token for token, _ in token_counts.most_common(4)]
        return " ".join(label_tokens)

    first_title = cluster["items"][0].get("title") or "trend"
    return first_title


def _merge_similar_clusters(raw_clusters: list[dict]) -> list[dict]:
    """Merge near-duplicate clusters before LLM enrichment.

    This prevents two cards with almost identical labels/summaries from being
    shown side by side when the greedy first pass split one broad theme into
    two neighbouring clusters.
    """
    if not raw_clusters:
        return raw_clusters

    merged: list[dict] = []
    for cluster in raw_clusters:
        merged_into_existing = False
        slug = _normalize_slug(cluster["theme_label"])
        phrases = set(cluster.get("keywords") or [])
        token_set = set(cluster.get("token_set") or [])

        for existing in merged:
            existing_slug = _normalize_slug(existing["theme_label"])
            similarity, shared = _token_overlap(token_set, set(existing.get("token_set") or []))
            phrase_overlap = phrases and set(existing.get("keywords") or []) and bool(
                phrases & set(existing.get("keywords") or [])
            )

            if (
                slug == existing_slug
                or similarity >= _CLUSTER_MERGE_THRESHOLD
                or (phrase_overlap and shared >= 1)
            ):
                # Merge current cluster into existing cluster.
                existing["unique_items"].extend(cluster["unique_items"])
                existing["companies"] = sorted(set(existing["companies"]) | set(cluster["companies"]))
                existing["supporting_count_7d"] += cluster["supporting_count_7d"]
                existing["supporting_count_30d"] += cluster["supporting_count_30d"]
                existing["supporting_count_60d"] += cluster["supporting_count_60d"]
                existing["token_set"].update(token_set)

                # Re-deduplicate merged unique items by canonical URL.
                seen_urls: set[str] = set()
                deduped_items: list[dict] = []
                for item in sorted(
                    existing["unique_items"],
                    key=lambda i: parse_published_dt(i.get("published", "")).timestamp()
                    if parse_published_dt(i.get("published", ""))
                    else 0.0,
                    reverse=True,
                ):
                    key = item.get("canonical_url") or item.get("url") or ""
                    if key and key in seen_urls:
                        continue
                    if key:
                        seen_urls.add(key)
                    deduped_items.append(item)
                existing["unique_items"] = deduped_items
                existing["representative_items"] = deduped_items[:MAX_REPRESENTATIVE_ITEMS]

                merged_keywords = list(dict.fromkeys((existing.get("keywords") or []) + (cluster.get("keywords") or [])))
                existing["keywords"] = merged_keywords[:4]
                merged_into_existing = True
                break

        if not merged_into_existing:
            merged.append(cluster)

    return merged


# ---------------------------------------------------------------------------
# trend_summary_cache helpers
# ---------------------------------------------------------------------------

def _get_cached_trend(cluster_key: str) -> Optional[dict]:
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT trend_title, trend_summary FROM trend_summary_cache WHERE cluster_key = ?",
                (cluster_key,),
            ).fetchone()
            if row:
                return {"trend_title": row["trend_title"], "trend_summary": row["trend_summary"]}
            return None
    except Exception as exc:
        logger.debug("Trend cache read error for %s: %s", cluster_key, exc)
        return None


def _set_cached_trend(cluster_key: str, trend_title: str, trend_summary: str) -> None:
    if not trend_title:
        return
    try:
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO trend_summary_cache (cluster_key, trend_title, trend_summary, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(cluster_key) DO UPDATE SET
                       trend_title = excluded.trend_title,
                       trend_summary = excluded.trend_summary,
                       updated_at = excluded.updated_at""",
                (cluster_key, trend_title, trend_summary, now),
            )
    except Exception as exc:
        logger.warning("Trend cache write error for %s: %s", cluster_key, exc)


# ---------------------------------------------------------------------------
# LLM generation for cluster title + summary (§7.7)
# ---------------------------------------------------------------------------

_TREND_SYSTEM = """You are a financial analyst writing concise trend summaries for an EMS (Electronics Manufacturing Services) industry intelligence dashboard.

Given a cluster label and a list of representative article headlines, write:
1. trend_title: A single sharp phrase (8–12 words) capturing the core trend. No fluff, no "remains strong" — state the direction.
2. trend_summary: 1–2 sentences synthesising what is driving this cluster across multiple companies and time. Mention specific companies or demand signals where relevant.

Return ONLY valid JSON with keys "trend_title" and "trend_summary". No markdown, no extra keys."""


def _generate_trend_llm(cluster_label: str, representative_titles: list[str]) -> dict:
    """Call LLM to generate trend_title and trend_summary for a cluster."""
    from backend.core.llm_client import llm_complete

    titles_text = "\n".join(f"- {t}" for t in representative_titles[:5])
    user_content = f"Cluster theme: {cluster_label}\n\nRepresentative headlines:\n{titles_text}"

    try:
        raw = llm_complete(
            messages=[{"role": "user", "content": user_content}],
            system=_TREND_SYSTEM,
            model_key="fast",
            max_tokens=150,
        )
        raw = (raw or "").strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        import json
        parsed = json.loads(raw)
        return {
            "trend_title": str(parsed.get("trend_title") or cluster_label),
            "trend_summary": str(parsed.get("trend_summary") or ""),
        }
    except Exception as exc:
        logger.warning("LLM trend generation failed for '%s': %s", cluster_label, exc)
        return {"trend_title": cluster_label, "trend_summary": ""}


# ---------------------------------------------------------------------------
# Cluster scoring & ranking (§7.8)
# ---------------------------------------------------------------------------

def _cluster_strength(c: dict) -> tuple:
    """Sort key: prefer clusters with more 7d articles, then 30d, then company coverage."""
    return (
        c["supporting_count_7d"],
        c["supporting_count_30d"],
        c["supporting_count_60d"],
        len(c["companies"]),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_trending(
    news_items: list[dict],
    max_clusters: int = MAX_TRENDING_CLUSTERS,
    force: bool = False,
) -> list[dict]:
    """Discover and return up to max_clusters trending topic clusters.

    Phase 3 strategy (§7.4):
      1. Build lightweight token features from title + description
      2. Greedily cluster items by token overlap / phrase overlap
      3. Drop weak clusters (§7.8 — no padding)
      4. Score each cluster across 7d / 30d / 60d windows
      5. Generate stable trend_cluster_key (§7.5)
      6. Fetch or generate LLM trend_title + trend_summary (§7.7), cache result

    Returns 1–max_clusters real clusters, never padded with empty cards.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    if not news_items:
        return []

    def _sort_key(i: dict) -> float:
        dt = parse_published_dt(i.get("published", ""))
        return dt.timestamp() if dt else 0.0

    sorted_news = sorted(news_items, key=_sort_key, reverse=True)
    clusters: list[dict] = []

    for item in sorted_news:
        features = _item_cluster_features(item)
        token_set = features["token_set"]
        phrases = features["phrases"]
        if not token_set and not phrases:
            continue

        best_cluster = None
        best_score = 0.0
        best_shared = 0
        for cluster in clusters:
            similarity, shared = _token_overlap(token_set, cluster["token_set"])
            phrase_overlap = 1.0 if phrases and any(p in cluster["phrase_counts"] for p in phrases) else 0.0
            score = max(similarity, phrase_overlap)
            if score > best_score or (score == best_score and shared > best_shared):
                best_cluster = cluster
                best_score = score
                best_shared = shared

        if best_cluster and (
            best_score >= _CLUSTER_SIMILARITY_THRESHOLD or
            best_shared >= _MIN_SHARED_TOKENS
        ):
            best_cluster["items"].append(item)
            best_cluster["token_counts"].update(features["tokens"])
            best_cluster["phrase_counts"].update(phrases)
            best_cluster["token_set"].update(token_set)
        else:
            clusters.append({
                "items": [item],
                "token_counts": Counter(features["tokens"]),
                "phrase_counts": Counter(phrases),
                "token_set": set(token_set),
            })

    raw_clusters: list[dict] = []
    for idx, cluster in enumerate(clusters):
        seen_urls: set[str] = set()
        unique: list[dict] = []
        for item in cluster["items"]:
            key = item.get("canonical_url") or item.get("url") or ""
            if key and key not in seen_urls:
                seen_urls.add(key)
                unique.append(item)
            elif not key:
                unique.append(item)

        if len(unique) < _MIN_CLUSTER_ITEMS:
            continue

        count_7d = _count_in_window(unique, 7)
        count_30d = _count_in_window(unique, 30)
        count_60d = _count_in_window(unique, 60)

        if count_30d == 0 and count_60d == 0:
            continue

        sorted_items = sorted(unique, key=_sort_key, reverse=True)
        representative = sorted_items[:MAX_REPRESENTATIVE_ITEMS]
        companies = sorted({
            c for item in unique
            if (c := _extract_company(item)) is not None
        })

        label = _cluster_label(cluster)
        cluster_key = _trend_cluster_key("30d", label)
        keywords = []
        if cluster["phrase_counts"]:
            keywords.extend([phrase for phrase, _ in cluster["phrase_counts"].most_common(3)])
        for token, _ in cluster["token_counts"].most_common(5):
            if token not in keywords:
                keywords.append(token)
        keywords = keywords[:4]

        raw_clusters.append({
            "id": f"cluster_{idx + 1}",
            "cluster_key": cluster_key,
            "theme_label": label,
            "keywords": keywords,
            "token_set": set(cluster["token_set"]),
            "unique_items": unique,
            "supporting_count_7d": count_7d,
            "supporting_count_30d": count_30d,
            "supporting_count_60d": count_60d,
            "companies": companies,
            "representative_items": representative,
            "updated_at": now_iso,
        })

    raw_clusters = _merge_similar_clusters(raw_clusters)

    # Sort by strength, keep top N (§7.8)
    raw_clusters.sort(key=_cluster_strength, reverse=True)
    top_clusters = raw_clusters[:max_clusters]

    # LLM enrichment with cache (§7.7)
    result: list[dict] = []
    for cluster in top_clusters:
        cluster_key = cluster["cluster_key"]
        cached = None if force else _get_cached_trend(cluster_key)

        if cached:
            trend_title = cached["trend_title"]
            trend_summary = cached["trend_summary"]
        else:
            titles = [
                (item.get("title") or "")
                for item in cluster["representative_items"]
                if item.get("title")
            ]
            generated = _generate_trend_llm(cluster["theme_label"], titles)
            trend_title = generated["trend_title"]
            trend_summary = generated["trend_summary"]
            if trend_title:
                _set_cached_trend(cluster_key, trend_title, trend_summary)

        result.append({
            "id": cluster["id"],
            "trend_cluster_key": cluster_key,
            "trend_title": trend_title,
            "trend_summary": trend_summary,
            "keywords": cluster["keywords"],
            "window_label": "30d",
            "supporting_count_7d": cluster["supporting_count_7d"],
            "supporting_count_30d": cluster["supporting_count_30d"],
            "supporting_count_60d": cluster["supporting_count_60d"],
            "cluster_size": cluster["supporting_count_30d"],  # primary display count
            "companies": cluster["companies"],
            "representative_items": cluster["representative_items"],
            "updated_at": cluster["updated_at"],
        })

    return result


async def build_trending_async(
    news_items: list[dict],
    max_clusters: int = MAX_TRENDING_CLUSTERS,
    force: bool = False,
) -> list[dict]:
    """Async wrapper — runs LLM-heavy build_trending in a thread."""
    return await asyncio.to_thread(build_trending, news_items, max_clusters, force)
