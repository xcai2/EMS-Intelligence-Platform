"""Data structures for the News module (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse, urlunparse


def compute_canonical_url(url: str) -> str:
    """Compute a stable canonical URL for dedup and summary cache keying.

    Conservative normalisation: lowercase scheme + host, strip trailing slash
    from path, drop fragment, and normalise a leading ``www.`` host prefix.
    Query string and params are preserved so that distinct paginated or
    parameterised URLs are not collapsed.
    """
    raw = (url or "").strip()
    if not raw:
        return raw
    try:
        parsed = urlparse(raw)
        path = parsed.path.rstrip("/") or "/"
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return urlunparse((
            parsed.scheme.lower(),
            host,
            path,
            parsed.params,
            parsed.query,
            "",  # drop fragment
        ))
    except Exception:
        return raw


@dataclass
class Company:
    """A registered company in the news configuration database."""

    ticker: str
    full_name: str
    aliases: str = ""          # comma-separated aliases, e.g. "Flextronics,FLEX"
    industry: str = ""         # e.g. "EMS", "Hyperscaler"
    official_domain: str = ""  # official website domain
    official_website: str = "" # full official website URL
    rss_feeds: str = ""        # JSON array: [{"kind": "news", "url": "...", "source_name": "..."}]
                               # reserved mirror field; Phase 1 runtime uses sources.py, not this
    template_tier: str = "standard"  # "enhanced" or "standard"
    created_at: str = ""


@dataclass
class QueryTemplate:
    """A single Brave query template for a company intent.

    Phase 1 fixed intents: official_name, industry_news, stock_news, supporting_query.
    Phase 2 adds query_tier to distinguish base templates from enhanced supplements.
    query_template stores only the positive search terms; the global exclusion suffix
    (-site:sec.gov, -site:www.sec.gov) is appended by query_engine.py at runtime.
    """

    ticker: str
    intent: str           # "official_name" | "industry_news" | "stock_news" | "supporting_query"
    query_template: str   # base query — no year, no exclusion suffixes
    freshness: Optional[str] = None  # Brave freshness param
    count: int = 50       # results to request per Brave call
    query_tier: str = "base"  # "base" (Phase 1 fixed 4) | "enhanced" (Phase 2 supplements)
    id: Optional[int] = None
    updated_at: str = ""


@dataclass
class NewsItem:
    """A single normalized news article output by pipeline.py.

    source_type fixed values: brave | company_news_rss | sec_filing_rss | market_commentary_rss

    Phase 2 additions:
    - canonical_url: stable URL used for exact dedup keying and summary cache keying.
      Computed once during normalisation via compute_canonical_url(); all downstream
      consumers (dedup, summary cache) must use this field — never recompute independently.
    - matched_intents: all query intents that returned this article; populated by
      deduplicate_exact_items() when multiple queries hit the same canonical URL.
    - match_count: len(matched_intents), convenience field for ranking signals.
    """

    title: str
    url: str
    source: str
    source_type: str
    published: str = ""
    image_url: str = ""
    description: str = ""
    intent: Optional[str] = None          # primary intent (display label)
    categories: list = field(default_factory=list)  # compatibility field; theme filtering in frontend
    content: Optional[str] = None         # full article text; None until Phase 2 enrichment
    canonical_url: str = ""               # Phase 2: stable dedup/cache key
    matched_intents: List[str] = field(default_factory=list)  # Phase 2: all intents that hit this URL
    match_count: int = 0                  # Phase 2: len(matched_intents)
    canonical_event_key: str = ""         # stable event key across reprint sites
    merged_sources: List[str] = field(default_factory=list)   # source_types merged into this record
    merged_urls: List[str] = field(default_factory=list)      # all URLs that mapped to this event
    primary_source_type: str = ""         # winning source_type after merge priority

    @classmethod
    def from_dict(cls, data: dict) -> "NewsItem":
        url = data.get("url", "")
        matched_intents = list(data.get("matched_intents") or [])
        intent = data.get("intent")
        if not matched_intents and intent:
            matched_intents = [intent]
        return cls(
            title=data.get("title", ""),
            url=url,
            source=data.get("source", ""),
            source_type=data.get("source_type", ""),
            published=data.get("published", ""),
            image_url=data.get("image_url", ""),
            description=data.get("description", ""),
            intent=intent,
            categories=list(data.get("categories") or []),
            content=data.get("content"),
            canonical_url=data.get("canonical_url") or compute_canonical_url(url),
            matched_intents=matched_intents,
            match_count=int(data.get("match_count") or len(matched_intents)),
            canonical_event_key=data.get("canonical_event_key", ""),
            merged_sources=list(data.get("merged_sources") or []),
            merged_urls=list(data.get("merged_urls") or []),
            primary_source_type=data.get("primary_source_type", ""),
        )

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "source_type": self.source_type,
            "published": self.published,
            "image_url": self.image_url,
            "description": self.description,
            "intent": self.intent,
            "categories": self.categories,
            "content": self.content,
            "canonical_url": self.canonical_url,
            "matched_intents": self.matched_intents,
            "match_count": self.match_count,
            "canonical_event_key": self.canonical_event_key,
            "merged_sources": self.merged_sources,
            "merged_urls": self.merged_urls,
            "primary_source_type": self.primary_source_type,
        }
