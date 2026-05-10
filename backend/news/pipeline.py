"""News pipeline: normalize → exact dedup → cross-source merge → age-filter → categorize → sort.

Phase 2 pipeline:
  1. Normalize          — standard fields; drop items missing title/url; compute canonical_url
  2. Exact dedup        — collapse same canonical_url; merge matched_intents
  3. Age filter         — drop Brave items older than 5 months, RSS items older than 6 months
  4. Categorize         — assign display-layer category tags via keyword matching (filtering.py)
  5. Sort               — descending by published date; undated items go last

Phase 3 addition:
  2b. Cross-source merge — after exact dedup, fold reprints of the same press release into
      one primary record; assign canonical_event_key, merged_sources, merged_urls.
      Insertion point: normalize → exact dedup → cross-source merge → age filter → sort.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from backend.news.filtering import classify_article
from backend.news.models import NewsItem, compute_canonical_url
from backend.news.normalizer import SOURCE_DOMAIN_LABELS, extract_title_date_dt, parse_published_dt

logger = logging.getLogger(__name__)

# 5 months ≈ 150 days (Phase 1 time window enforced via post-processing)
NEWS_MAX_AGE_DAYS = 150
RSS_MAX_AGE_DAYS = 180

# Domains that are navigation/social pages, not news articles — drop from Brave results.
_JUNK_DOMAINS: frozenset[str] = frozenset({
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "reddit.com",
    "youtube.com",
    "sec.gov",           # Raw EDGAR filings — use sec_filing_rss instead
})

# Exact title patterns that indicate a homepage/navigation result, not an article.
_JUNK_TITLE_SUBSTRINGS: tuple[str, ...] = (
    "| home",
    "| linkedin",
    "| twitter",
    "| facebook",
    "sec.gov | home",
    "investor relations",   # IR navigation pages, e.g. "SEC Filings - Financials - Investor Relations | ..."
)


# ---------------------------------------------------------------------------
# Step 1: Normalize
# ---------------------------------------------------------------------------

def _is_junk_item(title: str, url: str, source_type: str) -> bool:
    """Return True if this item is a navigation page / social profile, not a news article.

    Only applied to Brave results — RSS items are trusted as-is.
    """
    if source_type != "brave":
        return False
    try:
        domain = urlparse(url).netloc.replace("www.", "").lower()
    except Exception:
        return False
    if domain in _JUNK_DOMAINS:
        return True
    title_lower = title.lower()
    return any(pat in title_lower for pat in _JUNK_TITLE_SUBSTRINGS)


def normalize_items(raw_items: list[dict]) -> list[NewsItem]:
    """Ensure every item has the standard set of fields.

    Items missing title or URL are silently dropped.
    Brave items identified as navigation/social pages are also dropped.
    All other fields receive safe defaults.
    """
    normalized: list[NewsItem] = []
    for raw in raw_items:
        title = (raw.get("title") or "").strip()
        url = (raw.get("url") or "").strip()
        if not title or not url:
            continue

        published_raw = (
            raw.get("published")
            or raw.get("published_at")
            or raw.get("date")
            or ""
        ).strip()

        # Standardize to ISO 8601 UTC. If structured fields are missing, allow a
        # simple explicit title-date fallback before leaving published empty.
        published_dt = parse_published_dt(published_raw)
        if published_dt is None:
            published_dt = extract_title_date_dt(title)
        published_iso = published_dt.isoformat() if published_dt else ""

        source = (raw.get("source") or raw.get("original_source") or "").strip()
        source_type = raw.get("source_type") or "brave"
        # Brave results carry no source field — derive display name from URL domain.
        if not source and source_type == "brave":
            try:
                domain = urlparse(url).netloc.replace("www.", "")
                source = SOURCE_DOMAIN_LABELS.get(domain, domain)
            except Exception:
                pass

        if _is_junk_item(title, url, source_type):
            continue

        canonical = compute_canonical_url(url)
        intent_val = raw.get("intent")
        matched = [intent_val] if intent_val else []

        normalized.append(
            NewsItem(
                title=title,
                url=url,
                source=source,
                source_type=source_type,
                published=published_iso,
                image_url=(raw.get("image_url") or "").strip(),
                description=(raw.get("description") or "").strip()[:500],
                intent=intent_val,
                categories=[],
                content=raw.get("content"),
                canonical_url=canonical,
                matched_intents=matched,
                match_count=len(matched),
            )
        )
    return normalized


# ---------------------------------------------------------------------------
# Intent priority for choosing the primary intent on a merged record
# ---------------------------------------------------------------------------

_INTENT_PRIORITY: dict[str, int] = {
    "official_name": 4,
    "stock_news": 3,
    "industry_news": 2,
    "supporting_query": 1,
}


def _primary_intent(intents: list[str]) -> str | None:
    """Return the highest-priority intent from a merged intent list."""
    if not intents:
        return None
    return max(intents, key=lambda i: _INTENT_PRIORITY.get(i, 0))


def _quality_score(item: NewsItem) -> tuple[int, int, int, int]:
    return (
        1 if item.published else 0,
        len(item.description or ""),
        1 if item.source else 0,
        1 if item.image_url else 0,
    )


# Source-type priority: prefer company_news_rss over brave when same URL hit by both
_SOURCE_TYPE_PRIORITY: dict[str, int] = {
    "company_news_rss": 2,
    "brave": 1,
    "market_commentary_rss": 1,
}


def _source_priority(source_type: str) -> int:
    return _SOURCE_TYPE_PRIORITY.get(source_type, 0)


# ---------------------------------------------------------------------------
# Phase 2 — URL-level exact dedup with intent merging
# ---------------------------------------------------------------------------

def deduplicate_exact_items(items: list[NewsItem]) -> list[NewsItem]:
    """Collapse strict URL duplicates, merging matched_intents from all hits.

    Conservative: only collapses items with the same canonical_url + source_type.
    Does NOT merge same-event coverage from different domains.
    sec_filing_rss items are excluded from cross-source comparison by design
    (they are separated before this step in the service layer).

    For each group of duplicates:
    - The record with the highest source-type priority is chosen as main record;
      ties are broken by quality score (published date, description length, source, image).
    - All intents from every duplicate are merged into matched_intents.
    - intent (primary display label) is derived from matched_intents using priority order.
    - match_count is set to len(matched_intents).
    """
    kept_by_key: dict[str, NewsItem] = {}
    all_intents_by_key: dict[str, list[str]] = {}
    order: list[str] = []

    for item in items:
        # Key is canonical_url only — cross-source dedup (e.g. brave vs company_news_rss
        # for the same article) is intentional; source_type decides which record to keep.
        key = item.canonical_url or compute_canonical_url(item.url)
        existing = kept_by_key.get(key)

        # Collect all intents seen for this key
        if key not in all_intents_by_key:
            all_intents_by_key[key] = []
        for i in item.matched_intents:
            if i and i not in all_intents_by_key[key]:
                all_intents_by_key[key].append(i)

        if existing is None:
            kept_by_key[key] = item
            order.append(key)
            continue

        # Choose the better main record
        if _source_priority(item.source_type) > _source_priority(existing.source_type):
            kept_by_key[key] = item
        elif _source_priority(item.source_type) == _source_priority(existing.source_type):
            if _quality_score(item) > _quality_score(existing):
                kept_by_key[key] = item

    # Write merged intents back onto each surviving record
    result: list[NewsItem] = []
    for key in order:
        item = kept_by_key[key]
        merged = all_intents_by_key.get(key) or item.matched_intents
        item.matched_intents = merged
        item.match_count = len(merged)
        item.intent = _primary_intent(merged)
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

# Press-release origin domains — items from these are treated as primary sources (§8.3.1)
_PR_ORIGIN_DOMAINS: frozenset[str] = frozenset({
    "prnewswire.com",
    "businesswire.com",
    "globenewswire.com",
    "accessnewswire.com",
    "einpresswire.com",
    "newswire.com",
})

# URL path patterns that indicate an original press release (§8.3.1)
_PR_PATH_PATTERNS: tuple[str, ...] = (
    "/news-releases/",
    "/press-release/",
    "/press-releases/",
    "/newsroom/",
    "/news/press-",
)

# Event label mapping: title keywords → event fragment (§8.2)
_EVENT_LABELS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bearnings[\s\-]call\b", re.I), "earnings-call"),
    (re.compile(r"\bearnings[\s\-]release\b", re.I), "earnings-release"),
    (re.compile(r"\bquarterly[\s\-]results?\b", re.I), "quarterly-results"),
    (re.compile(r"\binvestor[\s\-]day\b", re.I), "investor-day"),
    (re.compile(r"\bannual[\s\-]meeting\b", re.I), "annual-meeting"),
    (re.compile(r"\bpress[\s\-]release\b", re.I), "press-release"),
    (re.compile(r"\bofficial[\s\-]announcement\b", re.I), "official-announcement"),
    (re.compile(r"\bfiscal[\s\-]year\b", re.I), "fiscal-year"),
]

# Quarter patterns for stable date fragments (§8.2.1)
_QUARTER_PATTERN = re.compile(r"\b(q[1-4])\b", re.I)
_FISCAL_YEAR_PATTERN = re.compile(r"\bfiscal\s*(20\d{2})\b", re.I)
_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")

# Stopwords for title slug normalisation
_TITLE_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for",
    "is", "are", "was", "its", "with", "by", "as", "new", "announces",
    "announce", "reports", "report", "says", "said", "from", "that", "this",
})


def _source_origin_priority(item: NewsItem) -> int:
    """Score how likely this item is the original publication (not a reprint).

    Higher = more authoritative.
      3 — company_news_rss (official IR feed)
      2 — known press-release wire domain
      1 — press-release URL path pattern
      0 — everything else (aggregators, news sites)
    """
    if item.source_type == "company_news_rss":
        return 3
    try:
        parsed = urlparse(item.url)
        domain = parsed.netloc.lower().lstrip("www.")
        if domain in _PR_ORIGIN_DOMAINS:
            return 2
        path = parsed.path.lower()
        if any(pat in path for pat in _PR_PATH_PATTERNS):
            return 1
    except Exception:
        pass
    return 0


def _normalize_title_tokens(title: str) -> list[str]:
    """Return a sorted, deduplicated list of significant lowercase tokens."""
    s = re.sub(r"[^a-z0-9\s]", " ", title.lower())
    tokens = [t for t in s.split() if t not in _TITLE_STOPWORDS and len(t) > 1]
    return sorted(set(tokens))


def _title_overlap_score(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Jaccard similarity on significant title tokens."""
    if not tokens_a or not tokens_b:
        return 0.0
    set_a, set_b = set(tokens_a), set(tokens_b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def _build_canonical_event_key(item: NewsItem) -> str:
    """Build a stable canonical_event_key for an item (§8.2 / §8.2.1).

    Format: {ticker_or_generic}:{event_slug}[:{date_fragment}]

    Rules:
    - Prefer business event fragments (q1/q4, fiscal-2026, investor-day) over
      exact publication dates.
    - Add a coarse date fragment only when no strong event label is found.
    - Never use day-precision dates (reprints may arrive a day later).
    """
    title = item.title or ""
    company = (item.source or "").split()[0].lower()  # rough company anchor

    # Extract event label
    event_label = ""
    for pattern, label in _EVENT_LABELS:
        if pattern.search(title):
            event_label = label
            break

    # Extract quarter / fiscal year fragments
    quarter_match = _QUARTER_PATTERN.search(title)
    fiscal_match = _FISCAL_YEAR_PATTERN.search(title)
    year_match = _YEAR_PATTERN.search(title)

    quarter_frag = quarter_match.group(1).lower() if quarter_match else ""
    fiscal_frag = f"fiscal-{fiscal_match.group(1)}" if fiscal_match else ""
    year_frag = year_match.group(1) if year_match else ""

    # Build slug from normalised title tokens (max 4 significant words)
    tokens = _normalize_title_tokens(title)
    slug_words = [t for t in tokens if t not in {"fiscal", "quarter", "annual"}][:4]
    title_slug = "-".join(slug_words) if slug_words else "news"

    # Compose date fragment: prefer quarter+fiscal > fiscal > year > nothing
    if quarter_frag and fiscal_frag:
        date_frag = f"{quarter_frag}-{fiscal_frag}"
    elif fiscal_frag:
        date_frag = fiscal_frag
    elif event_label and year_frag:
        # Strong event label — add year only to distinguish editions across years
        date_frag = year_frag
    elif year_frag and not event_label:
        date_frag = year_frag
    else:
        date_frag = ""

    parts = [p for p in [title_slug, event_label, date_frag] if p]
    key_body = "-".join(parts)[:80]  # cap length
    return f"{company}:{key_body}" if company else key_body


# Cross-source merge similarity threshold (§7.4 / §8.3)
_MERGE_TITLE_THRESHOLD = 0.55  # Jaccard on significant tokens


def merge_cross_source_items(items: list[NewsItem]) -> list[NewsItem]:
    """Fold reprints of the same press release into one primary record.

    Strategy (§8.3 / §8.3.1):
    - Compare pairs of items by title token overlap (Jaccard ≥ threshold).
    - Only merge items within a ±3-day published window to avoid false positives.
    - Winner = highest _source_origin_priority(); ties broken by description length.
    - Winner inherits: merged_sources, merged_urls, canonical_event_key.
    - Losers are dropped.

    Runs after exact dedup — so all inputs already have unique canonical_url.
    """
    if not items:
        return items

    n = len(items)
    token_cache: list[list[str]] = [_normalize_title_tokens(item.title) for item in items]
    merged_into: list[int] = list(range(n))  # union-find (flat)

    def _find(i: int) -> int:
        while merged_into[i] != i:
            merged_into[i] = merged_into[merged_into[i]]
            i = merged_into[i]
        return i

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra == rb:
            return
        # Keep the higher-priority item as the group root
        pa = _source_origin_priority(items[ra])
        pb = _source_origin_priority(items[rb])
        if pb > pa or (pb == pa and len(items[rb].description) > len(items[ra].description)):
            merged_into[ra] = rb
        else:
            merged_into[rb] = ra

    from backend.news.normalizer import parse_published_dt

    for i in range(n):
        for j in range(i + 1, n):
            if _find(i) == _find(j):
                continue
            score = _title_overlap_score(token_cache[i], token_cache[j])
            if score < _MERGE_TITLE_THRESHOLD:
                continue
            # Published date proximity guard (±3 days)
            dt_i = parse_published_dt(items[i].published)
            dt_j = parse_published_dt(items[j].published)
            if dt_i and dt_j:
                delta = abs((dt_i - dt_j).total_seconds())
                if delta > 3 * 86400:
                    continue
            _union(i, j)

    # Group by root
    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = _find(i)
        groups.setdefault(root, []).append(i)

    # Build result in order of first appearance (min member index per group)
    ordered_roots = sorted(groups.keys(), key=lambda root: min(groups[root]))
    result: list[NewsItem] = []
    for root in ordered_roots:
        members = groups[root]
        primary = items[root]
        all_sources = list({items[m].source_type for m in members})
        all_urls = list({items[m].url for m in members if items[m].url})
        primary.merged_sources = all_sources
        primary.merged_urls = all_urls
        primary.primary_source_type = primary.source_type
        primary.canonical_event_key = _build_canonical_event_key(primary)
        result.append(primary)

    return result


# ---------------------------------------------------------------------------
# Step 2: Age filter
# ---------------------------------------------------------------------------

_RSS_SOURCE_TYPES: frozenset[str] = frozenset({
    "company_news_rss",
    "sec_filing_rss",
    "market_commentary_rss",
})


def filter_by_age(
    items: list[NewsItem],
    max_age_days: int = NEWS_MAX_AGE_DAYS,
    rss_max_age_days: int = RSS_MAX_AGE_DAYS,
) -> list[NewsItem]:
    """Drop Brave items older than max_age_days and RSS items older than rss_max_age_days.

    Phase 1 rule:
    - Brave: keep roughly the most recent 5 months
    - RSS: keep roughly the most recent 6 months / 2 quarters
    - Undated items of any source are kept
    """
    brave_cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    rss_cutoff = datetime.now(timezone.utc) - timedelta(days=rss_max_age_days)
    kept: list[NewsItem] = []
    for item in items:
        published = item.published
        if not published:
            kept.append(item)
            continue
        dt = parse_published_dt(published)
        if dt is None:
            kept.append(item)
            continue
        if item.source_type in _RSS_SOURCE_TYPES:
            if dt >= rss_cutoff:
                kept.append(item)
            continue
        if dt >= brave_cutoff:
            kept.append(item)
    return kept


# ---------------------------------------------------------------------------
# Step 3: Categorize
# ---------------------------------------------------------------------------

def categorize_items(items: list[NewsItem]) -> list[NewsItem]:
    """Assign display-layer category tags to each item via keyword matching.

    Uses filtering.classify_article(); categories are written into item.categories.
    No items are removed — categories affect display only.
    """
    for item in items:
        item.categories = classify_article(
            title=item.title,
            description=item.description,
            intent=item.intent,
            url=item.url,
            source=item.source,
        )
    return items


# ---------------------------------------------------------------------------
# Step 4: Sort
# ---------------------------------------------------------------------------

def sort_by_recency(items: list[NewsItem]) -> list[NewsItem]:
    """Sort descending by publish date; undated items go to the bottom."""

    def sort_key(item: NewsItem) -> tuple[int, float]:
        dt = parse_published_dt(item.published)
        has_date = 1 if dt else 0
        epoch = dt.timestamp() if dt else 0.0
        return (has_date, epoch)

    return sorted(items, key=sort_key, reverse=True)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def run_with_diagnostics(
    raw_items: list[dict],
    max_age_days: int = NEWS_MAX_AGE_DAYS,
) -> tuple[list[NewsItem], dict]:
    """Execute all pipeline steps and return processed NewsItem objects plus counts.

    Steps: normalize → exact dedup → age filter → categorize → sort
    Returns list[NewsItem] — callers (e.g. service.py) convert to dicts at the
    cache write boundary via item.to_dict().
    """
    items = normalize_items(raw_items)
    after_normalize = len(items)
    items = deduplicate_exact_items(items)
    after_exact_dedup = len(items)
    items = merge_cross_source_items(items)
    after_cross_merge = len(items)
    items = filter_by_age(items, max_age_days=max_age_days)
    after_age_filter = len(items)
    items = categorize_items(items)
    items = sort_by_recency(items)
    diagnostics = {
        "raw_items": len(raw_items),
        "after_normalize": after_normalize,
        "after_exact_dedup": after_exact_dedup,
        "after_cross_merge": after_cross_merge,
        "after_age_filter": after_age_filter,
        "final_items": len(items),
        "dropped_in_normalize": len(raw_items) - after_normalize,
        "dropped_in_exact_dedup": after_normalize - after_exact_dedup,
        "dropped_in_cross_merge": after_exact_dedup - after_cross_merge,
        "dropped_in_age_filter": after_cross_merge - after_age_filter,
    }
    return items, diagnostics


def run(raw_items: list[dict], max_age_days: int = NEWS_MAX_AGE_DAYS) -> list[NewsItem]:
    """Execute all pipeline steps and return processed NewsItem objects.

    Steps: normalize → exact dedup → age filter → categorize → sort
    Returns list[NewsItem] — callers convert to dicts at the serialization boundary.
    """
    result, _diagnostics = run_with_diagnostics(raw_items, max_age_days=max_age_days)
    return result
