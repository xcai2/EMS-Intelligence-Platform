"""Low-level source fetchers for News pipelines.

Responsibilities:
  - Company / IR RSS: fetch + parse per-company RSS feeds
  - Image URL extraction helper from RSS descriptions

The active source set is now:
  1. Company RSS feeds
  2. Brave Search API
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any, Optional

import httpx

from backend.news.source_parsing import clean_html, extract_first_image_url

logger = logging.getLogger(__name__)

DEFAULT_HTTP_TIMEOUT = 12.0
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

DIAGNOSTIC_STATUS_OK = "ok"
DIAGNOSTIC_STATUS_EMPTY = "empty"
DIAGNOSTIC_STATUS_REQUEST_ERROR = "request_error"
DIAGNOSTIC_STATUS_PARSE_ERROR = "parse_error"
DIAGNOSTIC_STATUS_PROCESSING_ERROR = "processing_error"


def _build_async_client(
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    headers: Optional[dict[str, str]] = None,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers or DEFAULT_HTTP_HEADERS,
    )


async def _fetch_text_response_with_error(
    url: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    headers: Optional[dict[str, str]] = None,
) -> tuple[str | None, int, str | None]:
    try:
        async with _build_async_client(timeout=timeout, headers=headers) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return None, response.status_code, None
            return response.text, response.status_code, None
    except Exception as exc:
        return None, 0, f"request_error: {exc}"


def _http_status_label(status_code: int) -> str:
    if status_code == 200:
        return DIAGNOSTIC_STATUS_OK
    if status_code == 0:
        return DIAGNOSTIC_STATUS_REQUEST_ERROR
    return f"http_{status_code}"


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
) -> dict[str, Any]:
    return {
        "title": title,
        "url": url,
        "description": description,
        "image_url": image_url or "",
        "source": source,
        "original_source": original_source if original_source is not None else source,
        "aggregator": aggregator,
        "published": published or "",
    }


def _build_source_diagnostics(
    status: str,
    *,
    status_code: int | None,
    error: str | None,
    items_found: int,
    **extra: Any,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "status": status,
        "status_code": status_code,
        "error": error,
        "items_found": items_found,
    }
    diagnostics.update(extra)
    return diagnostics


def _status_from_items_found(items_found: int) -> str:
    return DIAGNOSTIC_STATUS_OK if items_found else DIAGNOSTIC_STATUS_EMPTY


async def fetch_company_rss_with_diagnostics(
    source_name: str,
    rss_url: str,
    limit: int = 8,
) -> tuple[list[dict], dict[str, Any]]:
    """Fetch a company's RSS feed with lightweight source diagnostics."""
    xml_text, status_code, request_error = await _fetch_text_response_with_error(
        rss_url, headers=RSS_HTTP_HEADERS
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


async def fetch_company_rss(
    source_name: str,
    rss_url: str,
    limit: int = 8,
) -> list[dict]:
    """Fetch a company's RSS feed and return item records."""
    items, diagnostics = await fetch_company_rss_with_diagnostics(source_name, rss_url, limit)
    if diagnostics.get("error"):
        logger.warning("Company RSS fetch failed for %s (%s): %s", source_name, rss_url, diagnostics["error"])
    return items
