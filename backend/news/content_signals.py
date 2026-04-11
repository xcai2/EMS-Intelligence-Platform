"""Content-level topic and company mention signals for News filtering."""

from __future__ import annotations

import re

from backend.news.filtering import AI_TERMS
from backend.news.query_helpers import company_short_names

# AI terms that are unambiguous on their own — a single hit is sufficient.
# Terms NOT in this set ("ai", "cloud", "chip", "cooling") are weak and require
# at least two independent AI term hits before we accept the item as AI-related.
_AI_STRONG_TERMS = frozenset({
    "artificial intelligence",
    "data center",
    "nvidia",
    "hyperscaler",
    "llm",
    "semiconductor",
    "liquid cooling",
    "immersion cooling",
    "thermal management",
    "generative",
})


def mentions_tracked_company(content: str) -> bool:
    """Detect whether a piece of text mentions any tracked company short name.

    Uses whole-word (\\b) matching so common-English company names like 'Flex'
    or 'Benchmark' don't false-positive on unrelated words that contain them
    as substrings (e.g. 'flexible', 'benchmarking').
    """
    content_lower = content.lower()
    for short in company_short_names().values():
        pattern = r'\b' + re.escape(short.lower()) + r'\b'
        if re.search(pattern, content_lower):
            return True
    return False


def is_ai_related(content: str) -> bool:
    """Detect whether a piece of text reflects the tracked AI/data-center theme.

    A single strong AI term is sufficient to accept.
    Weak single-word terms ('ai', 'cloud', 'chip', 'cooling') require at least
    two independent hits to reduce false positives from generic tech articles.
    """
    content_lower = content.lower()
    hits = [term for term in AI_TERMS if term in content_lower]
    if not hits:
        return False
    if any(h in _AI_STRONG_TERMS for h in hits):
        return True
    return len(hits) >= 2
