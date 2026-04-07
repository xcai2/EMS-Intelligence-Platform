"""Low-level source fetchers for News pipelines."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional
from urllib.parse import parse_qs, parse_qsl, quote_plus, unquote, urlencode, urljoin, urlparse

import httpx

from backend.news.news_filters import dedupe_items
from backend.news.query_helpers import build_company_site_query, get_company_aliases
from backend.news.sources import OFFICIAL_COMPANY_SOURCES, OFFICIAL_NEWS_KEYWORDS
from backend.news.source_parsing import (
    clean_html,
    extract_first_external_url_from_html,
    extract_first_image_url,
    extract_source,
    extract_source_from_google_description,
    extract_source_from_google_title,
    is_google_news_domain,
    is_likely_article_url,
    title_from_url,
)

if TYPE_CHECKING:
    from backend.news.service import NewsFeed


logger = logging.getLogger(__name__)
DEFAULT_HTTP_TIMEOUT = 12.0
GOOGLE_RSS_MAX_RETRIES = 2
SITEMAP_MAX_DEPTH = 1
SEED_PAGE_TIMEOUT = 10.0
REDIRECT_RESOLVE_TIMEOUT = 8.0
DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
}
RSS_HTTP_HEADERS = {
    **DEFAULT_HTTP_HEADERS,
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
HTML_HTTP_HEADERS = {
    **DEFAULT_HTTP_HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
GOOGLE_NEWS_AGGREGATOR = "Google News"
DIAGNOSTIC_STATUS_OK = "ok"
DIAGNOSTIC_STATUS_EMPTY = "empty"
DIAGNOSTIC_STATUS_REQUEST_ERROR = "request_error"
DIAGNOSTIC_STATUS_PARSE_ERROR = "parse_error"
DIAGNOSTIC_STATUS_PROCESSING_ERROR = "processing_error"
DIAGNOSTIC_STATUS_NOT_ATTEMPTED = "not_attempted"
DIAGNOSTIC_STATUS_NOT_APPLICABLE = "not_applicable"
DIAGNOSTIC_STATUS_MISSING_SOURCE_CONFIG = "missing_source_config"
DIAGNOSTIC_STATUS_ERROR = "error"
OFFICIAL_CANDIDATE_TIER_ORDER = (
    "rss_candidates",
    "site_query_candidates",
    "sitemap_candidates",
    "html_scan_candidates",
    "seed_candidates",
)
OFFICIAL_STRONG_CANDIDATE_TIERS = (
    "rss_candidates",
    "site_query_candidates",
    "sitemap_candidates",
)
OFFICIAL_WEAK_CANDIDATE_TIERS = (
    "html_scan_candidates",
    "seed_candidates",
)
OFFICIAL_TRACKING_QUERY_PARAM_PREFIXES = ("utm_",)
OFFICIAL_TRACKING_QUERY_PARAMS = {
    "cmpid",
    "fbclid",
    "gclid",
    "guccounter",
    "guce_referrer",
    "guce_referrer_sig",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "ncid",
    "ocid",
    "ref",
    "ref_src",
    "refsrc",
    "wt_mc_id",
    "xtor",
}


def _build_async_client(
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    headers: Optional[dict[str, str]] = None,
) -> httpx.AsyncClient:
    """Create the standard async HTTP client used by news source fetchers."""
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers or DEFAULT_HTTP_HEADERS,
    )


async def _fetch_text_response(
    url: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    headers: Optional[dict[str, str]] = None,
) -> tuple[str | None, int]:
    """Fetch a text response and return its body only on HTTP 200."""
    try:
        async with _build_async_client(timeout=timeout, headers=headers) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return None, response.status_code
            return response.text, response.status_code
    except Exception:
        return None, 0


async def _fetch_text_response_with_error(
    url: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    headers: Optional[dict[str, str]] = None,
) -> tuple[str | None, int, str | None]:
    """Fetch a text response and preserve a compact request error string when one occurs."""
    try:
        async with _build_async_client(timeout=timeout, headers=headers) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return None, response.status_code, None
            return response.text, response.status_code, None
    except Exception as exc:
        return None, 0, f"request_error: {exc}"


async def _fetch_xml_response_with_error(
    url: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    headers: Optional[dict[str, str]] = None,
) -> tuple[str | None, int, str | None]:
    """Fetch an XML response while preserving HTTP status and request error text."""
    return await _fetch_text_response_with_error(
        url,
        timeout=timeout,
        headers=headers or RSS_HTTP_HEADERS,
    )


async def _fetch_text_response_with_final_url(
    url: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    headers: Optional[dict[str, str]] = None,
) -> tuple[str | None, int, str | None]:
    """Fetch a text response plus the final resolved URL after redirects."""
    try:
        async with _build_async_client(timeout=timeout, headers=headers) as client:
            response = await client.get(url)
            final_url = str(response.url)
            if response.status_code != 200:
                return None, response.status_code, final_url
            return response.text, response.status_code, final_url
    except Exception:
        return None, 0, None


def _http_status_label(status_code: int) -> str:
    """Normalize HTTP outcomes into a compact diagnostics label."""
    if status_code == 200:
        return DIAGNOSTIC_STATUS_OK
    if status_code == 0:
        return DIAGNOSTIC_STATUS_REQUEST_ERROR
    return f"http_{status_code}"


def _company_source_label(company_name: str) -> str:
    """Build the short company label used in official-source item titles and sources."""
    parts = company_name.split()
    return parts[0] if parts else "Company"


def _build_fetcher_item(
    title: str,
    url: str,
    description: str,
    source: str,
    *,
    image_url: str = "",
    original_source: str | None = None,
    aggregator: str | None = None,
    published: str = "",
    relevance_score: float | None = None,
) -> dict[str, Any]:
    """Build the shared low-level item shape used across fetchers."""
    item: dict[str, Any] = {
        "title": title,
        "url": url,
        "description": description,
        "image_url": image_url or "",
        "source": source,
        "original_source": original_source if original_source is not None else source,
        "aggregator": aggregator,
        "published": published or "",
    }
    if relevance_score is not None:
        item["relevance_score"] = relevance_score
    return item


def _build_official_item(
    title: str,
    url: str,
    description: str,
    source: str,
    *,
    image_url: str = "",
    original_source: str | None = None,
    aggregator: str | None = None,
    published: str = "",
    relevance_score: float | None = None,
) -> dict[str, Any]:
    """Build an official-source item on top of the shared fetcher schema."""
    return _build_fetcher_item(
        title,
        url,
        description,
        source,
        image_url=image_url,
        original_source=original_source,
        aggregator=aggregator,
        published=published,
        relevance_score=relevance_score,
    )


def _build_source_diagnostics(
    status: str,
    *,
    status_code: int | None,
    error: str | None,
    items_found: int,
    **extra: Any,
) -> dict[str, Any]:
    """Build a compact diagnostics record shared by low-level source fetchers."""
    diagnostics: dict[str, Any] = {
        "status": status,
        "status_code": status_code,
        "error": error,
        "items_found": items_found,
    }
    diagnostics.update(extra)
    return diagnostics


def _status_from_items_found(items_found: int) -> str:
    """Return the shared success/empty status for fetchers that completed normally."""
    return DIAGNOSTIC_STATUS_OK if items_found else DIAGNOSTIC_STATUS_EMPTY


def _resolve_google_rss_source_fields(
    *,
    title_source: str | None,
    raw_description: str,
    original_url: str,
) -> tuple[str, str, str]:
    """Resolve Google RSS source fields with one consistent meaning across fetchers.

    `source` is the display-friendly underlying publisher when recoverable.
    `original_source` keeps that best available publisher label before any UI fallback.
    `aggregator` is reserved for the transport layer and remains `Google News`.
    """
    desc_source = extract_source_from_google_description(raw_description)
    source_from_url = extract_source(original_url)
    publisher_source = title_source or desc_source
    if not publisher_source and source_from_url != "Unknown":
        publisher_source = source_from_url

    display_source = publisher_source or GOOGLE_NEWS_AGGREGATOR
    original_source = publisher_source or display_source
    return display_source, original_source, GOOGLE_NEWS_AGGREGATOR


def _build_official_candidate_buckets() -> dict[str, list[dict]]:
    """Create the ordered candidate buckets used by official company source collection."""
    return {tier_name: [] for tier_name in OFFICIAL_CANDIDATE_TIER_ORDER}


def _sum_candidate_tier_counts(counts: dict[str, int], tier_names: tuple[str, ...]) -> int:
    """Sum selected official candidate tier counts into a compact diagnostics number."""
    return sum(int(counts.get(tier_name, 0) or 0) for tier_name in tier_names)


def _should_drop_official_tracking_param(param_name: str) -> bool:
    """Drop only clearly tracking-oriented query params during official-source dedupe."""
    normalized_name = (param_name or "").strip().lower()
    if not normalized_name:
        return False
    if any(normalized_name.startswith(prefix) for prefix in OFFICIAL_TRACKING_QUERY_PARAM_PREFIXES):
        return True
    return normalized_name in OFFICIAL_TRACKING_QUERY_PARAMS


def _normalize_official_candidate_url(url: str) -> str:
    """Normalize a candidate URL enough for conservative official-source dedupe."""
    raw_url = (url or "").strip()
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/")
    if parsed.path and not path:
        path = "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _should_drop_official_tracking_param(key)
    ]
    normalized_query = urlencode(sorted(query_pairs))
    return f"{scheme}://{netloc}{path}" + (f"?{normalized_query}" if normalized_query else "")


def _merge_official_candidate_buckets(
    candidate_buckets: dict[str, list[dict]],
    limit: int,
) -> tuple[list[dict], dict[str, int], dict[str, int]]:
    """Merge official-source candidates by quality tier while keeping stronger matches first."""
    merged: list[dict] = []
    seen_urls: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    deduped_buckets = {
        tier_name: dedupe_items(candidate_buckets.get(tier_name, []))
        for tier_name in OFFICIAL_CANDIDATE_TIER_ORDER
    }
    raw_counts = {
        tier_name: len(deduped_buckets[tier_name])
        for tier_name in OFFICIAL_CANDIDATE_TIER_ORDER
    }
    kept_counts = {
        tier_name: 0
        for tier_name in OFFICIAL_CANDIDATE_TIER_ORDER
    }

    if limit <= 0:
        return [], raw_counts, kept_counts

    for tier_name in OFFICIAL_CANDIDATE_TIER_ORDER:
        tier_items = deduped_buckets[tier_name]
        for item in tier_items:
            normalized_url = _normalize_official_candidate_url(item.get("url", ""))
            normalized_title = (item.get("title", "") or "").strip().lower()
            pair_key = (normalized_url, normalized_title)

            if normalized_url and normalized_url in seen_urls:
                continue
            if pair_key in seen_pairs:
                continue

            if normalized_url:
                seen_urls.add(normalized_url)
            seen_pairs.add(pair_key)
            merged.append(item)
            kept_counts[tier_name] += 1

            if len(merged) >= limit:
                return merged, raw_counts, kept_counts

    return merged, raw_counts, kept_counts


def _extract_anchor_links(html: str) -> list[tuple[str, str]]:
    """Extract anchor href/text pairs with lightweight whitespace cleanup."""
    links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL)
    return [(href.strip(), inner_html.strip()) for href, inner_html in links if href.strip()]


def _build_google_news_rss_urls(query: str) -> list[str]:
    """Build the Google News RSS URL fallbacks used for a query."""
    encoded_query = quote_plus(query)
    return [
        f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en",
        f"https://news.google.com/rss/search?q={encoded_query}&hl=en&gl=US&ceid=US:en",
        f"https://news.google.com/rss/search?q={encoded_query}",
    ]


def _google_news_rss_status_from_error(error: str | None) -> str:
    """Collapse Google RSS fetch outcomes into a compact diagnostics status."""
    if not error:
        return DIAGNOSTIC_STATUS_OK
    error_lower = error.lower()
    if "returned empty feed" in error_lower:
        return DIAGNOSTIC_STATUS_EMPTY
    if "request error" in error_lower or "request_error" in error_lower:
        return DIAGNOSTIC_STATUS_REQUEST_ERROR
    if "parse error" in error_lower or "parse_error" in error_lower:
        return DIAGNOSTIC_STATUS_PARSE_ERROR
    if "http " in error_lower:
        return "http_error"
    if "google news rss error" in error_lower:
        return DIAGNOSTIC_STATUS_PROCESSING_ERROR
    return DIAGNOSTIC_STATUS_ERROR


def _finalize_google_news_rss_failure_status(error: str | None, status_code: int | None) -> str:
    """Align Google RSS failure status naming with the broader fetcher diagnostics vocabulary."""
    collapsed_status = _google_news_rss_status_from_error(error)
    if collapsed_status == "http_error" and status_code not in {None, 0, 200}:
        return _http_status_label(status_code)
    if collapsed_status == "http_error":
        return DIAGNOSTIC_STATUS_ERROR
    return collapsed_status


async def _parse_google_news_rss_items(
    feed: "NewsFeed",
    xml_text: str,
    limit: int,
) -> list[dict]:
    """Parse a Google News RSS payload into normalized item records."""
    root = ET.fromstring(xml_text)
    items = []

    for item in root.findall(".//item"):
        raw_title = (item.findtext("title", "") or "").strip()
        title, title_source = extract_source_from_google_title(raw_title)
        link = (item.findtext("link", "") or "").strip()
        raw_description = item.findtext("description", "") or ""
        description = clean_html(raw_description)
        original_url = extract_first_external_url_from_html(raw_description) or link
        if is_google_news_domain(original_url):
            original_url = await resolve_google_news_redirect_url(feed, original_url)
        source, original_source, aggregator = _resolve_google_rss_source_fields(
            title_source=title_source,
            raw_description=raw_description,
            original_url=original_url,
        )
        image_url = extract_first_image_url(raw_description)
        if not title or not original_url:
            continue
        items.append(
            _build_fetcher_item(
                title,
                original_url,
                description[:260],
                source,
                image_url=image_url,
                original_source=original_source,
                aggregator=aggregator,
                published=item.findtext("pubDate", "") or "",
            )
        )
        if len(items) >= limit:
            break

    return items


async def _fetch_google_news_rss_xml(
    query: str,
    *,
    accept_xml: Callable[[str], Awaitable[int]] | None = None,
) -> tuple[str | None, str | None]:
    """Fetch Google News RSS XML with URL fallbacks, retries, and compact error tracking."""
    xml_text, diagnostics = await _fetch_google_news_rss_xml_with_full_diagnostics(query, accept_xml=accept_xml)
    return xml_text, diagnostics.get("error")


async def _fetch_google_news_rss_xml_with_full_diagnostics(
    query: str,
    *,
    accept_xml: Callable[[str], Awaitable[int]] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Fetch Google News RSS XML with URL fallbacks, retries, and detailed diagnostics."""
    rss_urls = _build_google_news_rss_urls(query)
    rss_urls_tried: list[str] = []
    attempts = 0
    last_error: str | None = None
    last_status_code: int | None = None
    accepted_items_found = 0

    for rss_url in rss_urls:
        rss_urls_tried.append(rss_url)
        for _ in range(GOOGLE_RSS_MAX_RETRIES):
            attempts += 1
            xml_text, status_code, request_error = await _fetch_xml_response_with_error(rss_url)
            last_status_code = status_code
            if request_error:
                last_error = f"Google News RSS {request_error}"
                continue
            if status_code != 200 or not xml_text:
                last_error = f"Google News RSS HTTP {status_code}"
                continue
            try:
                if accept_xml is None:
                    diagnostics = _build_source_diagnostics(
                        DIAGNOSTIC_STATUS_OK,
                        status_code=status_code,
                        error=None,
                        items_found=0,
                        query=query,
                        rss_urls_tried=rss_urls_tried,
                        attempts=attempts,
                    )
                    return xml_text, diagnostics
                accepted_items_found = await accept_xml(xml_text)
                if accepted_items_found:
                    diagnostics = _build_source_diagnostics(
                        DIAGNOSTIC_STATUS_OK,
                        status_code=status_code,
                        error=None,
                        items_found=accepted_items_found,
                        query=query,
                        rss_urls_tried=rss_urls_tried,
                        attempts=attempts,
                    )
                    return xml_text, diagnostics
                last_error = "Google News RSS returned empty feed"
            except ET.ParseError as e:
                last_error = f"Google News RSS parse error: {e}"
            except Exception as e:
                last_error = f"Google News RSS error: {e}"

    diagnostics = _build_source_diagnostics(
        _finalize_google_news_rss_failure_status(last_error or "Google News RSS unknown error", last_status_code),
        status_code=last_status_code,
        error=last_error or "Google News RSS unknown error",
        items_found=accepted_items_found,
        query=query,
        rss_urls_tried=rss_urls_tried,
        attempts=attempts,
    )
    return None, diagnostics


class NewsSourceFetcherGateway:
    """Named gateway exposing low-level news source fetchers off a NewsFeed instance."""

    def __init__(self, feed: "NewsFeed"):
        self._feed = feed

    async def google_news_rss_with_diagnostics(self, query: str, limit: int = 8) -> tuple[list[dict], str | None]:
        return await fetch_google_news_rss_with_diagnostics(self._feed, query, limit)

    async def google_news_rss_with_full_diagnostics(
        self,
        query: str,
        limit: int = 8,
    ) -> tuple[list[dict], dict[str, Any]]:
        return await fetch_google_news_rss_with_full_diagnostics(self._feed, query, limit)

    async def google_news_rss(self, query: str, limit: int = 8) -> list[dict]:
        return await fetch_google_news_rss(self._feed, query, limit)

    async def official_company_news(self, ticker: str, company_name: str, limit: int = 8) -> list[dict]:
        return await fetch_official_company_news(self._feed, ticker, company_name, limit)

    async def official_company_news_with_diagnostics(
        self,
        ticker: str,
        company_name: str,
        limit: int = 8,
    ) -> tuple[list[dict], dict[str, Any]]:
        return await fetch_official_company_news_with_diagnostics(self._feed, ticker, company_name, limit)

    async def flex_newsroom_from_sitemap(self, limit: int = 10) -> list[dict]:
        return await fetch_flex_newsroom_from_sitemap(limit)

    async def flex_newsroom_from_sitemap_with_diagnostics(self, limit: int = 10) -> tuple[list[dict], dict[str, Any]]:
        return await fetch_flex_newsroom_from_sitemap_with_diagnostics(limit)

    async def extract_news_urls_from_sitemap(self, sitemap_url: str, domain_hint: str = "", depth: int = 0) -> list[str]:
        return await extract_news_urls_from_sitemap(sitemap_url, domain_hint=domain_hint, depth=depth)

    async def company_rss(self, source_name: str, rss_url: str, limit: int = 8) -> list[dict]:
        return await fetch_company_rss(source_name, rss_url, limit)

    async def public_news_links(self, board_url: str, ticker: str, company_name: str, limit: int = 10) -> list[dict]:
        return await fetch_public_news_links(board_url, ticker, company_name, limit)

    async def public_news_links_with_diagnostics(
        self,
        board_url: str,
        ticker: str,
        company_name: str,
        limit: int = 10,
    ) -> tuple[list[dict], dict[str, Any]]:
        return await fetch_public_news_links_with_diagnostics(board_url, ticker, company_name, limit)

    async def scan_company_news_links(self, page_url: str, company_name: str, limit: int = 8) -> list[dict]:
        return await scan_company_news_links(page_url, company_name, limit)

    async def scan_company_news_links_with_diagnostics(
        self,
        page_url: str,
        company_name: str,
        limit: int = 8,
    ) -> tuple[list[dict], dict[str, Any]]:
        return await scan_company_news_links_with_diagnostics(page_url, company_name, limit)

    async def seed_page_item(self, page_url: str, company_name: str) -> Optional[dict]:
        return await build_seed_page_item(page_url, company_name)

    async def seed_page_item_with_diagnostics(
        self,
        page_url: str,
        company_name: str,
    ) -> tuple[Optional[dict], dict[str, Any]]:
        return await build_seed_page_item_with_diagnostics(page_url, company_name)

    async def resolve_google_news_redirect_url(self, url: str) -> str:
        return await resolve_google_news_redirect_url(self._feed, url)


async def fetch_google_news_rss_with_diagnostics(
    feed: "NewsFeed",
    query: str,
    limit: int = 8,
) -> tuple[list[dict], str | None]:
    """Fetch Google News RSS results and preserve a lightweight error string."""
    items, diagnostics = await fetch_google_news_rss_with_full_diagnostics(feed, query, limit)
    return items, diagnostics.get("error")


async def fetch_google_news_rss_with_full_diagnostics(
    feed: "NewsFeed",
    query: str,
    limit: int = 8,
) -> tuple[list[dict], dict[str, Any]]:
    """Fetch Google News RSS results and preserve a richer diagnostics record."""
    parsed_items: list[dict] = []

    async def _accept_xml(xml_text: str) -> int:
        nonlocal parsed_items
        parsed_items = await _parse_google_news_rss_items(feed, xml_text, limit)
        return len(parsed_items)

    _xml_text, diagnostics = await _fetch_google_news_rss_xml_with_full_diagnostics(query, accept_xml=_accept_xml)
    diagnostics["items_found"] = len(parsed_items)
    return parsed_items, diagnostics


async def fetch_google_news_rss(
    feed: "NewsFeed",
    query: str,
    limit: int = 8,
) -> list[dict]:
    """Fetch Google News RSS results and log failures at the caller facade."""
    items, error = await fetch_google_news_rss_with_diagnostics(feed, query, limit)
    if error:
        logger.warning("Google RSS fetch failed for query '%s': %s", query, error)
    return items


async def fetch_official_company_news(
    feed: "NewsFeed",
    ticker: str,
    company_name: str,
    limit: int = 8,
) -> list[dict]:
    """Compatibility wrapper returning only items."""
    items, _diagnostics = await fetch_official_company_news_with_diagnostics(feed, ticker, company_name, limit)
    return items


async def _collect_official_company_source_results(
    feed: "NewsFeed",
    ticker: str,
    company_name: str,
    source: dict[str, Any],
    limit: int,
) -> tuple[dict[str, list[dict]], dict[str, Any]]:
    """Collect raw official-source candidates by quality tier before final merge and truncation."""
    candidate_buckets = _build_official_candidate_buckets()
    diagnostics: dict[str, Any] = {
        "status": DIAGNOSTIC_STATUS_OK,
        "status_code": None,
        "error": None,
        "ticker": ticker,
        "company_name": company_name,
        "sitemap_result_count": 0,
        "sitemap": {
            "status": DIAGNOSTIC_STATUS_NOT_APPLICABLE,
            "status_code": None,
            "error": None,
            "sitemap_candidates": [],
            "matched_sitemap_url": None,
            "urls_found": 0,
            "items_found": 0,
        },
        "rss_sources": [],
        "site_query_used": False,
        "site_query": None,
        "site_query_diagnostics": _build_source_diagnostics(
            DIAGNOSTIC_STATUS_NOT_ATTEMPTED,
            status_code=None,
            error=None,
            items_found=0,
            query=None,
        ),
        "site_query_result_count": 0,
        "html_scan_disabled": bool(source.get("disable_html_scan")),
        "html_scans": [],
        "seed_page": {
            "page_url": source.get("news_url"),
            "status": DIAGNOSTIC_STATUS_NOT_ATTEMPTED,
            "status_code": None,
            "title_found": False,
            "item_built": False,
            "error": None,
        },
        "seed_page_added": False,
        "candidate_tier_order": list(OFFICIAL_CANDIDATE_TIER_ORDER),
        "candidate_tier_counts": {tier_name: 0 for tier_name in OFFICIAL_CANDIDATE_TIER_ORDER},
        "candidate_tier_kept_counts": {tier_name: 0 for tier_name in OFFICIAL_CANDIDATE_TIER_ORDER},
        "candidate_tier_suppressed_counts": {tier_name: 0 for tier_name in OFFICIAL_CANDIDATE_TIER_ORDER},
        "strong_candidate_total_count": 0,
        "strong_candidate_kept_count": 0,
        "strong_candidate_suppressed_count": 0,
        "weak_candidate_total_count": 0,
        "weak_candidate_kept_count": 0,
        "weak_candidate_suppressed_count": 0,
        "items_found": 0,
    }

    if ticker == "FLEX":
        sitemap_results, sitemap_diagnostics = await fetch_flex_newsroom_from_sitemap_with_diagnostics(limit=limit)
        diagnostics["sitemap_result_count"] = len(sitemap_results)
        diagnostics["sitemap"] = sitemap_diagnostics
        candidate_buckets["sitemap_candidates"].extend(sitemap_results)

    rss_url = source.get("rss_url")
    if isinstance(rss_url, list):
        for single_rss_url in rss_url:
            if single_rss_url:
                rss_items, rss_diagnostics = await fetch_company_rss_with_diagnostics(
                    source["name"],
                    single_rss_url,
                    limit=limit,
                )
                diagnostics["rss_sources"].append(rss_diagnostics)
                candidate_buckets["rss_candidates"].extend(rss_items)
    elif rss_url:
        rss_items, rss_diagnostics = await fetch_company_rss_with_diagnostics(
            source["name"],
            rss_url,
            limit=limit,
        )
        diagnostics["rss_sources"].append(rss_diagnostics)
        candidate_buckets["rss_candidates"].extend(rss_items)

    domain = source.get("domain")
    if domain:
        site_query = build_company_site_query(ticker, company_name, domain)
        if site_query:
            site_query_items, site_query_diagnostics = await fetch_google_news_rss_with_full_diagnostics(
                feed,
                site_query,
                limit=limit,
            )
            diagnostics["site_query_used"] = True
            diagnostics["site_query"] = site_query
            diagnostics["site_query_diagnostics"] = site_query_diagnostics
            diagnostics["site_query_result_count"] = int(site_query_diagnostics.get("items_found", len(site_query_items)) or 0)
            candidate_buckets["site_query_candidates"].extend(site_query_items)

    disable_html_scan = bool(source.get("disable_html_scan"))
    if not disable_html_scan:
        urls_to_scan = [source.get("news_url"), source.get("base_url")]
        for scan_url in urls_to_scan:
            if not scan_url:
                continue
            scan_items, scan_diagnostics = await scan_company_news_links_with_diagnostics(
                scan_url,
                company_name,
                limit=limit,
            )
            diagnostics["html_scans"].append(scan_diagnostics)
            candidate_buckets["html_scan_candidates"].extend(scan_items)

        if source.get("news_url"):
            seed_item, seed_diagnostics = await build_seed_page_item_with_diagnostics(
                source["news_url"],
                company_name,
            )
            diagnostics["seed_page"] = seed_diagnostics
            if seed_item:
                diagnostics["seed_page_added"] = True
                candidate_buckets["seed_candidates"].append(seed_item)

    diagnostics["candidate_tier_counts"] = {
        tier_name: len(dedupe_items(candidate_buckets[tier_name]))
        for tier_name in OFFICIAL_CANDIDATE_TIER_ORDER
    }
    return candidate_buckets, diagnostics


async def fetch_official_company_news_with_diagnostics(
    feed: "NewsFeed",
    ticker: str,
    company_name: str,
    limit: int = 8,
) -> tuple[list[dict], dict[str, Any]]:
    """Collect official company updates from RSS, site-scoped Google RSS, and lightweight HTML scans."""
    source = OFFICIAL_COMPANY_SOURCES.get(ticker)
    if not source:
        return [], _build_source_diagnostics(
            DIAGNOSTIC_STATUS_MISSING_SOURCE_CONFIG,
            status_code=None,
            error=None,
            items_found=0,
            ticker=ticker,
            company_name=company_name,
        )

    candidate_buckets, diagnostics = await _collect_official_company_source_results(
        feed,
        ticker,
        company_name,
        source,
        limit,
    )

    merged_items, raw_counts, kept_counts = _merge_official_candidate_buckets(candidate_buckets, limit)
    diagnostics["candidate_tier_counts"] = raw_counts
    diagnostics["candidate_tier_kept_counts"] = kept_counts
    diagnostics["candidate_tier_suppressed_counts"] = {
        tier_name: max(raw_counts[tier_name] - kept_counts[tier_name], 0)
        for tier_name in OFFICIAL_CANDIDATE_TIER_ORDER
    }
    diagnostics["strong_candidate_total_count"] = _sum_candidate_tier_counts(raw_counts, OFFICIAL_STRONG_CANDIDATE_TIERS)
    diagnostics["strong_candidate_kept_count"] = _sum_candidate_tier_counts(kept_counts, OFFICIAL_STRONG_CANDIDATE_TIERS)
    diagnostics["strong_candidate_suppressed_count"] = _sum_candidate_tier_counts(
        diagnostics["candidate_tier_suppressed_counts"],
        OFFICIAL_STRONG_CANDIDATE_TIERS,
    )
    diagnostics["weak_candidate_total_count"] = _sum_candidate_tier_counts(raw_counts, OFFICIAL_WEAK_CANDIDATE_TIERS)
    diagnostics["weak_candidate_kept_count"] = _sum_candidate_tier_counts(kept_counts, OFFICIAL_WEAK_CANDIDATE_TIERS)
    diagnostics["weak_candidate_suppressed_count"] = _sum_candidate_tier_counts(
        diagnostics["candidate_tier_suppressed_counts"],
        OFFICIAL_WEAK_CANDIDATE_TIERS,
    )
    diagnostics["items_found"] = len(merged_items)
    if not merged_items:
        diagnostics["status"] = DIAGNOSTIC_STATUS_EMPTY
    return merged_items, diagnostics


async def fetch_flex_newsroom_from_sitemap(limit: int = 10) -> list[dict]:
    """Compatibility wrapper returning only items."""
    items, _diagnostics = await fetch_flex_newsroom_from_sitemap_with_diagnostics(limit)
    return items


async def fetch_flex_newsroom_from_sitemap_with_diagnostics(
    limit: int = 10,
) -> tuple[list[dict], dict[str, Any]]:
    """Fetch official Flex newsroom URLs directly from the public sitemap."""
    sitemap_candidates = [
        "https://flex.com/sitemap.xml",
        "https://flex.com/sitemap_index.xml",
    ]
    diagnostics: dict[str, Any] = {
        "status": DIAGNOSTIC_STATUS_OK,
        "status_code": None,
        "error": None,
        "sitemap_candidates": sitemap_candidates,
        "matched_sitemap_url": None,
        "urls_found": 0,
        "items_found": 0,
    }
    urls: list[str] = []

    for sitemap_url in sitemap_candidates:
        sitemap_urls = await extract_news_urls_from_sitemap(sitemap_url, domain_hint="flex.com")
        if sitemap_urls:
            diagnostics["matched_sitemap_url"] = sitemap_url
            urls.extend(sitemap_urls)
            break

    if not urls:
        diagnostics["status"] = DIAGNOSTIC_STATUS_EMPTY
        return [], diagnostics

    items = []
    for url in urls:
        title = title_from_url(url)
        if not title:
            continue
        items.append(_build_official_item(title, url, "Official update from Flex newsroom", "Flex Newsroom"))
        if len(items) >= limit:
            break

    diagnostics["urls_found"] = len(urls)
    diagnostics["items_found"] = len(items)
    if not items:
        diagnostics["status"] = DIAGNOSTIC_STATUS_EMPTY
    return items, diagnostics


async def extract_news_urls_from_sitemap(
    sitemap_url: str,
    domain_hint: str = "",
    depth: int = 0,
) -> list[str]:
    """Walk a small sitemap tree and keep likely newsroom/content URLs."""
    if depth > SITEMAP_MAX_DEPTH:
        return []
    try:
        xml_text, status_code = await _fetch_text_response(sitemap_url)
        if status_code != 200 or not xml_text:
            return []
        root = ET.fromstring(xml_text)
    except Exception:
        return []

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [loc.text.strip() for loc in root.findall(".//sm:loc", ns) if loc.text]
    if not locs:
        locs = [loc.text.strip() for loc in root.findall(".//loc") if loc.text]

    news_urls = []
    for loc in locs:
        loc_lower = loc.lower()
        if domain_hint and domain_hint not in loc_lower:
            continue

        if loc_lower.endswith(".xml") and "sitemap" in loc_lower:
            news_urls.extend(
                await extract_news_urls_from_sitemap(
                    loc,
                    domain_hint=domain_hint,
                    depth=depth + 1,
                )
            )
            continue

        if "/newsroom" in loc_lower or "/news/" in loc_lower or "/press" in loc_lower:
            news_urls.append(loc)

    deduped = dedupe_items([{"url": url, "title": url} for url in news_urls])
    return [item["url"] for item in deduped if item.get("url")]


async def fetch_company_rss(
    source_name: str,
    rss_url: str,
    limit: int = 8,
) -> list[dict]:
    """Fetch a company's official RSS feed and map items into the shared record shape."""
    items, _diagnostics = await fetch_company_rss_with_diagnostics(source_name, rss_url, limit)
    return items


async def fetch_company_rss_with_diagnostics(
    source_name: str,
    rss_url: str,
    limit: int = 8,
) -> tuple[list[dict], dict[str, Any]]:
    """Fetch a company's official RSS feed and return lightweight source diagnostics."""
    xml_text, status_code, request_error = await _fetch_text_response_with_error(
        rss_url,
        headers=RSS_HTTP_HEADERS,
    )
    if request_error:
        return [], _build_source_diagnostics(
            DIAGNOSTIC_STATUS_REQUEST_ERROR,
            status_code=0,
            error=request_error,
            items_found=0,
            parse_ok=False,
            rss_url=rss_url,
            source_name=source_name,
        )

    if status_code != 200 or not xml_text:
        return [], _build_source_diagnostics(
            _http_status_label(status_code),
            status_code=status_code,
            error=None,
            items_found=0,
            parse_ok=False,
            rss_url=rss_url,
            source_name=source_name,
        )

    try:
        root = ET.fromstring(xml_text)
        items = []
        for item in root.findall(".//item"):
            title = (item.findtext("title", "") or "").strip()
            link = (item.findtext("link", "") or "").strip()
            raw_description = item.findtext("description", "") or ""
            description = clean_html(raw_description)
            image_url = extract_first_image_url(raw_description)
            if not title or not link:
                continue
            items.append(
                _build_fetcher_item(
                    title,
                    link,
                    description[:260],
                    source_name,
                    image_url=image_url,
                    published=item.findtext("pubDate", "") or "",
                )
            )
            if len(items) >= limit:
                break
        return items, _build_source_diagnostics(
            _status_from_items_found(len(items)),
            status_code=status_code,
            error=None,
            items_found=len(items),
            parse_ok=True,
            rss_url=rss_url,
            source_name=source_name,
        )
    except ET.ParseError as exc:
        return [], _build_source_diagnostics(
            DIAGNOSTIC_STATUS_PARSE_ERROR,
            status_code=status_code,
            error=f"parse_error: {exc}",
            items_found=0,
            parse_ok=False,
            rss_url=rss_url,
            source_name=source_name,
        )
    except Exception as exc:
        return [], _build_source_diagnostics(
            DIAGNOSTIC_STATUS_PROCESSING_ERROR,
            status_code=status_code,
            error=f"processing_error: {exc}",
            items_found=0,
            parse_ok=False,
            rss_url=rss_url,
            source_name=source_name,
        )


async def fetch_public_news_links(
    board_url: str,
    ticker: str,
    company_name: str,
    limit: int = 10,
) -> list[dict]:
    """Compatibility wrapper returning only items."""
    items, _diagnostics = await fetch_public_news_links_with_diagnostics(board_url, ticker, company_name, limit)
    return items


async def fetch_public_news_links_with_diagnostics(
    board_url: str,
    ticker: str,
    company_name: str,
    limit: int = 10,
) -> tuple[list[dict], dict[str, Any]]:
    """Extract outbound article links from a Public.com company news board."""
    html, status_code = await _fetch_text_response(board_url, headers=HTML_HTTP_HEADERS)
    if status_code != 200 or not html:
        return [], _build_source_diagnostics(
            _http_status_label(status_code),
            status_code=status_code,
            error=DIAGNOSTIC_STATUS_REQUEST_ERROR if status_code == 0 else None,
            items_found=0,
            board_url=board_url,
            ticker=ticker,
        )

    aliases = [alias.lower() for alias in get_company_aliases(ticker, company_name)]
    links = _extract_anchor_links(html)
    results: list[dict] = []

    for href, inner_html in links:
        url = href
        if not url.startswith("http"):
            continue

        domain = (urlparse(url).netloc or "").lower().replace("www.", "")
        if domain.endswith("public.com"):
            continue

        title = clean_html(inner_html)
        if len(title) < 20 or len(title) > 220:
            continue

        title_lower = title.lower()
        if not any(alias in title_lower for alias in aliases):
            continue

        results.append(
            _build_fetcher_item(
                title,
                url,
                f"Curated from Public.com {ticker} news board",
                "Public News",
            )
        )
        if len(results) >= limit:
            break

    deduped_items = dedupe_items(results)[:limit]
    return deduped_items, _build_source_diagnostics(
        _status_from_items_found(len(deduped_items)),
        status_code=status_code,
        error=None,
        items_found=len(deduped_items),
        board_url=board_url,
        ticker=ticker,
        raw_link_count=len(links),
    )


async def scan_company_news_links(
    page_url: str,
    company_name: str,
    limit: int = 8,
) -> list[dict]:
    """Compatibility wrapper returning only items."""
    items, _diagnostics = await scan_company_news_links_with_diagnostics(page_url, company_name, limit)
    return items


async def scan_company_news_links_with_diagnostics(
    page_url: str,
    company_name: str,
    limit: int = 8,
) -> tuple[list[dict], dict[str, Any]]:
    """Scan a company page for likely newsroom/article links without fetching article bodies."""
    company_label = _company_source_label(company_name)
    html, status_code = await _fetch_text_response(page_url, headers=HTML_HTTP_HEADERS)
    if status_code != 200 or not html:
        return [], _build_source_diagnostics(
            _http_status_label(status_code),
            status_code=status_code,
            error=DIAGNOSTIC_STATUS_REQUEST_ERROR if status_code == 0 else None,
            items_found=0,
            page_url=page_url,
            company_name=company_name,
        )

    links = _extract_anchor_links(html)
    candidates = []

    for href, inner_html in links:
        title = clean_html(inner_html)
        if len(title) < 18 or len(title) > 220:
            continue
        full_url = urljoin(page_url, href)
        if not full_url.startswith("http"):
            continue
        combined = f"{title} {full_url}".lower()
        if not any(keyword in combined for keyword in OFFICIAL_NEWS_KEYWORDS):
            continue

        article_hint = any(token in full_url.lower() for token in ["/news", "/press", "/article", "/insight", "/media"])
        company_hint = company_label.lower() in title.lower()
        official_hint = any(
            token in combined
            for token in ("newsroom", "press", "news", "media", "investor", "relations", "events")
        )
        score = (
            (2 if article_hint else 0)
            + (2 if company_hint else 0)
            + (1 if official_hint else 0)
        )

        candidate = _build_official_item(
            title,
            full_url,
            f"Official update from {company_name}",
            f"{company_label} Official",
        )
        candidate["_score"] = score
        candidates.append(candidate)

    candidates.sort(key=lambda item: item.get("_score", 0), reverse=True)
    cleaned = []
    for item in candidates[: limit * 2]:
        cleaned.append({key: value for key, value in item.items() if key != "_score"})

    deduped_items = dedupe_items(cleaned)[:limit]
    return deduped_items, _build_source_diagnostics(
        _status_from_items_found(len(deduped_items)),
        status_code=status_code,
        error=None,
        items_found=len(deduped_items),
        page_url=page_url,
        company_name=company_name,
        raw_link_count=len(links),
        candidate_count=len(candidates),
    )


async def build_seed_page_item(
    page_url: str,
    company_name: str,
) -> Optional[dict]:
    """Create one fallback item from the configured official page itself."""
    item, _diagnostics = await build_seed_page_item_with_diagnostics(page_url, company_name)
    return item


async def build_seed_page_item_with_diagnostics(
    page_url: str,
    company_name: str,
) -> tuple[Optional[dict], dict[str, Any]]:
    """Create one fallback item from the configured official page itself with diagnostics."""
    company_label = _company_source_label(company_name)
    html, status_code = await _fetch_text_response(page_url, timeout=SEED_PAGE_TIMEOUT, headers=HTML_HTTP_HEADERS)
    if status_code != 200 or not html:
        diagnostics = _build_source_diagnostics(
            _http_status_label(status_code),
            status_code=status_code,
            error=DIAGNOSTIC_STATUS_REQUEST_ERROR if status_code == 0 else None,
            items_found=0,
            page_url=page_url,
            title_found=False,
            item_built=False,
        )
        return None, diagnostics

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    page_title = clean_html(title_match.group(1)) if title_match else ""
    title_found = bool(page_title)
    if not page_title:
        page_title = f"{company_label} Official News"

    item = _build_official_item(
        page_title,
        page_url,
        f"Official updates from {company_name}",
        f"{company_label} Official",
        original_source=f"{company_label} Official",
        relevance_score=1.0,
    )
    diagnostics = _build_source_diagnostics(
        DIAGNOSTIC_STATUS_OK,
        status_code=status_code,
        error=None,
        items_found=1,
        page_url=page_url,
        title_found=title_found,
        item_built=True,
    )
    return item, diagnostics


async def resolve_google_news_redirect_url(feed: "NewsFeed", url: str) -> str:
    """Resolve a Google News redirect URL into the likely original article URL."""
    if not url:
        return url
    cached = feed._google_redirect_cache.get(url)
    if cached:
        return cached
    resolved = url
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        for key in ("url", "u"):
            candidate = (qs.get(key) or [None])[0]
            if not candidate:
                continue
            candidate = unquote(candidate).strip()
            if is_likely_article_url(candidate):
                resolved = candidate
                feed._google_redirect_cache[url] = resolved
                return resolved
    except Exception:
        pass

    try:
        html, _status_code, final_url = await _fetch_text_response_with_final_url(
            url,
            timeout=REDIRECT_RESOLVE_TIMEOUT,
            headers=HTML_HTTP_HEADERS,
        )
        if final_url and is_likely_article_url(final_url):
            resolved = final_url
        elif html:
            html_external = extract_first_external_url_from_html(html)
            if is_likely_article_url(html_external):
                resolved = html_external
    except Exception:
        pass

    feed._google_redirect_cache[url] = resolved
    return resolved
