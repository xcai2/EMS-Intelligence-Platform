"""Shared normalization and common filtering helpers for the News domain."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote_plus, urlparse

from backend.news.filtering import AI_TERMS, BLOCKED_OR_PAYWALL_DOMAINS, CAPEX_TERMS, CATEGORIES, EXCLUDED_NOISE_TERMS
from backend.news.source_parsing import (
    extract_source,
    extract_source_from_google_description,
    extract_source_from_title_suffix,
    normalize_source_candidate,
)

if TYPE_CHECKING:
    from backend.news.service import NewsFeed


def categorize_content(content: str, categories_map: dict[str, list[str]]) -> list[str]:
    """Assign lightweight content tags used for downstream filtering."""
    content_lower = content.lower()
    categories = []

    for category, keywords in categories_map.items():
        if any(kw.lower() in content_lower for kw in keywords):
            categories.append(category)

    if not categories:
        if any(term in content_lower for term in ["q1", "q2", "q3", "q4", "quarter", "fiscal", "fy2", "fy2025", "fy2024", "eps", "beat", "miss"]):
            categories.append("earnings")
        if any(term in content_lower for term in ["nvidia", "hyperscale", "cloud", "generative", "llm", "chip", "semiconductor"]):
            categories.append("ai")
        if any(term in content_lower for term in ["liquid cooling", "immersion cooling", "thermal management", "heat exchanger", "cold plate"]):
            categories.append("cooling")
        if any(term in content_lower for term in ["million", "billion", "invest", "expand", "new facility", "build"]):
            categories.append("capex")
        if any(term in content_lower for term in ["acquire", "deal", "agreement", "partner", "announce"]):
            categories.append("strategy")

    return categories if categories else ["general"]


def calculate_relevance(result: dict, company_name: str) -> float:
    """Calculate a lightweight relevance score for ranking within a feed."""
    score = 0.0
    content = (result["title"] + " " + result.get("description", "")).lower()
    company_lower = company_name.lower()

    if company_lower in content:
        score += 0.5

    current_year = datetime.now().year
    if any(term in content for term in ["today", "announces", "reports", str(current_year), str(current_year - 1)]):
        score += 0.2

    if any(term in content for term in ["earnings", "revenue", "investment", "strategy"]):
        score += 0.3

    if any(term in content for term in [*AI_TERMS, *CAPEX_TERMS]):
        score += 0.2

    return min(score, 1.0)


def is_likely_accessible(url: str) -> bool:
    """Drop clearly broken or blocked links before they reach the UI."""
    try:
        domain = (urlparse(url).netloc or "").lower().replace("www.", "")
        if not domain:
            return False
        return all(not domain.endswith(blocked) for blocked in BLOCKED_OR_PAYWALL_DOMAINS)
    except Exception:
        return False


def normalize_result(feed: "NewsFeed", result: dict, company_name: str = "") -> Optional[dict]:
    """Normalize different search/feed payloads into a unified news record."""
    title = (result.get("title") or "").strip()
    url = (result.get("url") or "").strip()
    if not title or not url:
        return None

    noise_content = f"{title} {result.get('description', '')} {url} {result.get('source', '')}".lower()
    if any(term in noise_content for term in EXCLUDED_NOISE_TERMS):
        return None
    if not is_likely_accessible(url):
        return None

    description = (result.get("description") or "").strip()
    categories = categorize_content(f"{title} {description}", CATEGORIES)
    backup_url = f"https://www.google.com/search?q={quote_plus(title)}"
    raw_source = (result.get("source") or "").strip()
    original_source = (result.get("original_source") or "").strip()
    normalized_raw_source = normalize_source_candidate(raw_source)
    normalized_original_source = normalize_source_candidate(original_source)
    source_from_url = extract_source(url)
    title_source = extract_source_from_title_suffix(title)[1]
    desc_source = extract_source_from_google_description(result.get("description", "") or "")
    if normalized_original_source and normalized_original_source.lower() not in {"google news", "brave search"}:
        resolved_source = normalized_original_source
    elif normalized_raw_source and normalized_raw_source.lower() not in {"google news", "brave search"}:
        resolved_source = normalized_raw_source
    elif title_source:
        resolved_source = title_source
    elif desc_source:
        resolved_source = desc_source
    elif source_from_url and source_from_url != "Unknown":
        resolved_source = source_from_url
    else:
        resolved_source = normalized_raw_source or "Unknown"

    return {
        "title": title,
        "url": url,
        "backup_url": backup_url,
        "description": description,
        "image_url": (result.get("image_url") or "").strip(),
        "source": resolved_source,
        "original_source": resolved_source,
        "aggregator": result.get("aggregator") or None,
        "published": (
            result.get("published")
            or result.get("published_at")
            or result.get("date")
            or ""
        ),
        "categories": categories,
        "relevance_score": calculate_relevance(
            {"title": title, "description": description},
            company_name,
        ),
    }


def dedupe_items(items: list[dict]) -> list[dict]:
    """Dedupe exact URL/title pairs while preserving input order."""
    seen = set()
    deduped = []
    for item in items:
        key = (item.get("url", "").strip().lower(), item.get("title", "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
