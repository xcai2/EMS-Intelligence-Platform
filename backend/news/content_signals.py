"""Content-level topic and company mention signals for News filtering."""

from __future__ import annotations

from backend.news.filtering import AI_TERMS
from backend.news.query_helpers import company_short_names


def mentions_tracked_company(content: str) -> bool:
    """Detect whether a piece of text mentions any tracked company short name."""
    content_lower = content.lower()
    for short in company_short_names().values():
        if short.lower() in content_lower:
            return True
    return False


def is_ai_related(content: str) -> bool:
    """Detect whether a piece of text reflects the tracked AI/data-center theme."""
    content_lower = content.lower()
    return any(term in content_lower for term in AI_TERMS)
