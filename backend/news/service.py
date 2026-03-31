"""
News feed integration for competitive intelligence.
Aggregates news from multiple sources for tracked companies.
"""
import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urlparse, urljoin, parse_qs, unquote

import httpx

from backend.core.config import COMPANIES, OPENAI_API_KEY, LLM_MODEL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from backend.core.llm_client import llm_complete
from backend.news.filtering import AI_TERMS, BLOCKED_OR_PAYWALL_DOMAINS, EXCLUDED_NOISE_TERMS
from backend.news.normalizer import SOURCE_DOMAIN_LABELS
from backend.news.sources import (
    FALLBACK_COMPANY_NEWS,
    FALLBACK_INDUSTRY_NEWS,
    OFFICIAL_COMPANY_SOURCES,
    OFFICIAL_NEWS_KEYWORDS,
)
from backend.rag.web_search import search_web, search_web_with_diagnostics

logger = logging.getLogger(__name__)
CACHE_FILE = Path("data/news_runtime_cache.json")


class NewsFeed:
    """
    Aggregates and manages company news from multiple sources.
    """
    
    # News categories for filtering (all lowercase for case-insensitive matching)
    CATEGORIES = {
        "earnings": ["earnings", "quarterly", "revenue", "profit", "results", "guidance", "eps", "beat", "miss", "forecast", "outlook", "fiscal"],
        "ai": ["artificial intelligence", "ai", "machine learning", "data center", "nvidia", "hyperscale", "cloud computing", "generative", "llm", "semiconductor", "chip"],
        "capex": ["capital expenditure", "capex", "investment", "expansion", "factory", "facility", "million", "billion", "spending", "infrastructure"],
        "strategy": ["acquisition", "merger", "partnership", "restructuring", "strategy", "deal", "agreement", "acquire", "divest"],
        "operations": ["manufacturing", "supply chain", "production", "capacity", "logistics", "assembly", "plant"],
        "cooling": ["liquid cooling", "immersion cooling", "thermal", "thermal management", "cooling", "heat exchanger", "cold plate"],
    }
    
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 3600  # 1 hour cache
        # Runtime cache: persists until backend process restarts.
        self._runtime_cache: dict[str, dict] = {}
        self._google_redirect_cache: dict[str, str] = {}
        self._load_runtime_cache()

    def _load_runtime_cache(self) -> None:
        try:
            if not CACHE_FILE.exists():
                return
            loaded = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._runtime_cache = loaded
                logger.info("Loaded news runtime cache with %d keys", len(self._runtime_cache))
        except Exception as e:
            logger.warning("Failed to load news runtime cache: %s", e)

    def _persist_runtime_cache(self) -> None:
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp_file = CACHE_FILE.with_suffix(".tmp")
            temp_file.write_text(json.dumps(self._runtime_cache, ensure_ascii=False), encoding="utf-8")
            temp_file.replace(CACHE_FILE)
        except Exception as e:
            logger.warning("Failed to persist news runtime cache: %s", e)

    async def _fetch_google_news_rss_with_diagnostics(self, query: str, limit: int = 8) -> tuple[list[dict], str | None]:
        """Fetch Google News RSS results and return diagnostics."""
        rss_urls = [
            f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en",
            f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en&gl=US&ceid=US:en",
            f"https://news.google.com/rss/search?q={quote_plus(query)}",
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        last_error: str | None = None

        for rss_url in rss_urls:
            for _ in range(2):
                try:
                    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers) as client:
                        response = await client.get(rss_url)
                        if response.status_code != 200:
                            last_error = f"Google News RSS HTTP {response.status_code}"
                            continue

                    root = ET.fromstring(response.text)
                    items = []
                    for item in root.findall(".//item"):
                        raw_title = (item.findtext("title", "") or "").strip()
                        title, title_source = self._extract_source_from_google_title(raw_title)
                        link = (item.findtext("link", "") or "").strip()
                        raw_description = item.findtext("description", "") or ""
                        description = self._clean_html(raw_description)
                        desc_source = self._extract_source_from_google_description(raw_description)
                        original_url = self._extract_first_external_url_from_html(raw_description) or link
                        if self._is_google_news_domain(original_url):
                            original_url = await self._resolve_google_news_redirect_url(original_url)
                        source_from_url = self._extract_source(original_url)
                        source = title_source or desc_source
                        if not source and source_from_url != "Unknown":
                            source = source_from_url
                        if not source:
                            source = "Google News"
                        image_url = self._extract_first_image_url(raw_description)
                        if not title or not original_url:
                            continue
                        items.append(
                            {
                                "title": title,
                                "url": original_url,
                                "description": description[:260],
                                "image_url": image_url,
                                "source": source,
                                "original_source": source,
                                "aggregator": "Google News",
                                "published": item.findtext("pubDate", "") or "",
                            }
                        )
                        if len(items) >= limit:
                            break
                    if items:
                        return items, None
                    last_error = "Google News RSS returned empty feed"
                except httpx.RequestError as e:
                    last_error = f"Google News RSS request error: {e}"
                except ET.ParseError as e:
                    last_error = f"Google News RSS parse error: {e}"
                except Exception as e:
                    last_error = f"Google News RSS error: {e}"

        return [], last_error or "Google News RSS unknown error"

    async def _fetch_google_news_rss(self, query: str, limit: int = 8) -> list[dict]:
        """Fetch Google News RSS results (free, no API key)."""
        items, error = await self._fetch_google_news_rss_with_diagnostics(query, limit)
        if error:
            logger.warning("Google RSS fetch failed for query '%s': %s", query, error)
        return items

    async def _fetch_official_company_news(self, ticker: str, company_name: str, limit: int = 8) -> list[dict]:
        """
        Lightweight scraper for official company websites.
        Uses RSS if configured, otherwise scans page links for likely news items.
        """
        source = OFFICIAL_COMPANY_SOURCES.get(ticker)
        if not source:
            return []

        collected: list[dict] = []

        # 0) Flex newsroom direct from sitemap (official source, no search dependency)
        if ticker == "FLEX":
            collected.extend(await self._fetch_flex_newsroom_from_sitemap(limit=limit))

        # 1) RSS (if available)
        rss_url = source.get("rss_url")
        if isinstance(rss_url, list):
            for single_rss_url in rss_url:
                if single_rss_url:
                    collected.extend(await self._fetch_company_rss(source["name"], single_rss_url, limit=limit))
        elif rss_url:
            collected.extend(await self._fetch_company_rss(source["name"], rss_url, limit=limit))

        # 1.5) Site-scoped Google News RSS (most reliable lightweight source)
        domain = source.get("domain")
        if domain:
            site_query = (
                f'site:{domain} ("news" OR "press release" OR "earnings" OR "AI" OR "data center") {company_name}'
            )
            collected.extend(await self._fetch_google_news_rss(site_query, limit=limit))

        disable_html_scan = bool(source.get("disable_html_scan"))
        if not disable_html_scan:
            # 2) HTML link scan (very lightweight fallback)
            urls_to_scan = [source.get("news_url"), source.get("base_url")]
            for scan_url in urls_to_scan:
                if not scan_url:
                    continue
                collected.extend(await self._scan_company_news_links(scan_url, company_name, limit=limit))

            # 3) Always keep one official clickable entry if link extraction is empty
            if source.get("news_url"):
                seed_item = await self._build_seed_page_item(source["news_url"], company_name)
                if seed_item:
                    # Keep one explicit official entry in the pool every time.
                    collected.append(seed_item)

        return self._dedupe_items(collected)[:limit]

    async def _fetch_flex_newsroom_from_sitemap(self, limit: int = 10) -> list[dict]:
        """
        Fetch Flex newsroom links from flex.com sitemaps.
        This is lightweight and does not depend on search engines.
        """
        sitemap_candidates = [
            "https://flex.com/sitemap.xml",
            "https://flex.com/sitemap_index.xml",
        ]
        urls: list[str] = []

        for sitemap_url in sitemap_candidates:
            urls.extend(await self._extract_news_urls_from_sitemap(sitemap_url, domain_hint="flex.com"))
            if urls:
                break

        if not urls:
            return []

        items = []
        for url in urls:
            title = self._title_from_url(url)
            if not title:
                continue
            items.append(
                {
                    "title": title,
                    "url": url,
                    "description": "Official update from Flex newsroom",
                    "source": "Flex Newsroom",
                }
            )
            if len(items) >= limit:
                break

        return items

    async def _extract_news_urls_from_sitemap(self, sitemap_url: str, domain_hint: str = "", depth: int = 0) -> list[str]:
        if depth > 1:
            return []
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                response = await client.get(sitemap_url)
                if response.status_code != 200:
                    return []
            xml_text = response.text
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

            # Nested sitemap indexes
            if loc_lower.endswith(".xml") and "sitemap" in loc_lower:
                news_urls.extend(await self._extract_news_urls_from_sitemap(loc, domain_hint=domain_hint, depth=depth + 1))
                continue

            # Newsroom/content pages
            if "/newsroom" in loc_lower or "/news/" in loc_lower or "/press" in loc_lower:
                news_urls.append(loc)

        deduped = self._dedupe_items([{"url": u, "title": u} for u in news_urls])
        return [item["url"] for item in deduped if item.get("url")]

    def _title_from_url(self, url: str) -> str:
        try:
            path = urlparse(url).path.strip("/")
            if not path:
                return ""
            slug = path.split("/")[-1]
            slug = re.sub(r"[-_]+", " ", slug).strip()
            slug = re.sub(r"\s+", " ", slug)
            if len(slug) < 5:
                return ""
            return slug.title()
        except Exception:
            return ""

    async def _fetch_company_rss(self, source_name: str, rss_url: str, limit: int = 8) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                response = await client.get(rss_url)
                if response.status_code != 200:
                    return []
            root = ET.fromstring(response.text)
            items = []
            for item in root.findall(".//item"):
                title = (item.findtext("title", "") or "").strip()
                link = (item.findtext("link", "") or "").strip()
                raw_description = item.findtext("description", "") or ""
                description = self._clean_html(raw_description)
                image_url = self._extract_first_image_url(raw_description)
                if not title or not link:
                    continue
                items.append(
                    {
                        "title": title,
                        "url": link,
                        "description": description[:260],
                        "image_url": image_url,
                        "source": source_name,
                    }
                )
                if len(items) >= limit:
                    break
            return items
        except Exception:
            return []

    async def _fetch_public_news_links(
        self,
        board_url: str,
        ticker: str,
        company_name: str,
        limit: int = 10,
    ) -> list[dict]:
        """
        Fetch outbound links from a Public.com stock news board.
        We only keep title/url/summary and do not fetch article content.
        """
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                response = await client.get(board_url)
                if response.status_code != 200:
                    return []
                html = response.text
        except Exception:
            return []

        aliases = [a.lower() for a in self._get_company_aliases(ticker, company_name)]
        links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL)
        results: list[dict] = []

        for href, inner_html in links:
            url = href.strip()
            if not url.startswith("http"):
                continue

            domain = (urlparse(url).netloc or "").lower().replace("www.", "")
            if domain.endswith("public.com"):
                continue

            title = self._clean_html(inner_html)
            if len(title) < 20 or len(title) > 220:
                continue

            title_lower = title.lower()
            if not any(alias in title_lower for alias in aliases):
                continue

            results.append(
                {
                    "title": title,
                    "url": url,
                    "description": f"Curated from Public.com {ticker} news board",
                    "source": "Public News",
                }
            )
            if len(results) >= limit:
                break

        return self._dedupe_items(results)[:limit]

    async def _scan_company_news_links(self, page_url: str, company_name: str, limit: int = 8) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                response = await client.get(page_url)
                if response.status_code != 200:
                    return []
                html = response.text
        except Exception:
            return []

        # Extract links from HTML
        links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL)
        candidates = []

        for href, inner_html in links:
            title = self._clean_html(inner_html)
            if len(title) < 18 or len(title) > 220:
                continue
            full_url = urljoin(page_url, href.strip())
            if not full_url.startswith("http"):
                continue
            combined = f"{title} {full_url}".lower()
            if not any(keyword in combined for keyword in OFFICIAL_NEWS_KEYWORDS):
                continue

            # Prefer links that look like article pages
            article_hint = any(token in full_url.lower() for token in ["/news", "/press", "/article", "/insight", "/media"])
            company_hint = company_name.split()[0].lower() in title.lower()
            score = (2 if article_hint else 0) + (2 if company_hint else 0) + (1 if "ai" in combined else 0)

            candidates.append(
                {
                    "title": title,
                    "url": full_url,
                    "description": f"Official update from {company_name}",
                    "source": f"{company_name.split()[0]} Official",
                    "_score": score,
                }
            )

        candidates.sort(key=lambda item: item.get("_score", 0), reverse=True)
        cleaned = []
        for item in candidates[: limit * 2]:
            item = {k: v for k, v in item.items() if k != "_score"}
            cleaned.append(item)

        return self._dedupe_items(cleaned)[:limit]

    async def _build_seed_page_item(self, page_url: str, company_name: str) -> Optional[dict]:
        """
        Create one fallback item from the configured official page itself
        so each company has at least one directly clickable official entry.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(page_url)
                if response.status_code != 200:
                    return None
                html = response.text
        except Exception:
            return None

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        page_title = self._clean_html(title_match.group(1)) if title_match else ""
        if not page_title:
            page_title = f"{company_name.split()[0]} Official News"

        return {
            "title": page_title,
            "url": page_url,
            "description": f"Official updates from {company_name}",
            "source": f"{company_name.split()[0]} Official",
            "original_source": f"{company_name.split()[0]} Official",
            "relevance_score": 1.0,
        }

    def _clean_html(self, text: str) -> str:
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _extract_first_image_url(self, html: str) -> str:
        if not html:
            return ""
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        if not match:
            return ""
        src = (match.group(1) or "").strip()
        if src.startswith("http://") or src.startswith("https://"):
            return src
        return ""

    def _extract_first_external_url_from_html(self, html: str) -> str:
        if not html:
            return ""
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        for href in hrefs:
            href = (href or "").strip()
            if self._is_likely_article_url(href):
                return href
        return ""

    def _is_google_owned_domain(self, domain: str) -> bool:
        normalized = (domain or "").lower().replace("www.", "")
        return (
            normalized.endswith("news.google.com")
            or normalized.endswith("google.com")
            or normalized.endswith("googleusercontent.com")
            or normalized.endswith("ggpht.com")
            or normalized.endswith("googleapis.com")
            or normalized.endswith("gstatic.com")
            or normalized.endswith("google-analytics.com")
            or normalized.endswith("googletagmanager.com")
            or normalized.endswith("doubleclick.net")
        )

    def _is_likely_article_url(self, url: str) -> bool:
        try:
            if not url.startswith(("http://", "https://")):
                return False
            parsed = urlparse(url)
            domain = (parsed.netloc or "").lower().replace("www.", "")
            if not domain:
                return False
            if self._is_google_owned_domain(domain):
                return False
            path = (parsed.path or "").lower()
            if any(
                path.endswith(ext)
                for ext in [
                    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
                    ".js", ".css", ".map", ".xml", ".json", ".txt",
                    ".woff", ".woff2", ".ttf", ".otf",
                ]
            ):
                return False
            if path in {"/css", "/css2"}:
                return False
            if any(token in path for token in ["/analytics", "/tracking", "/tag/"]):
                return False
            return True
        except Exception:
            return False

    def _is_google_news_domain(self, url: str) -> bool:
        try:
            domain = (urlparse(url).netloc or "").lower().replace("www.", "")
            return domain.endswith("news.google.com")
        except Exception:
            return False

    async def _resolve_google_news_redirect_url(self, url: str) -> str:
        if not url:
            return url
        cached = self._google_redirect_cache.get(url)
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
                if self._is_likely_article_url(candidate):
                    resolved = candidate
                    self._google_redirect_cache[url] = resolved
                    return resolved
        except Exception:
            pass

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
                response = await client.get(url)
                final_url = str(response.url)
                if self._is_likely_article_url(final_url):
                    resolved = final_url
                else:
                    html_external = self._extract_first_external_url_from_html(response.text)
                    if self._is_likely_article_url(html_external):
                        resolved = html_external
        except Exception:
            pass

        self._google_redirect_cache[url] = resolved
        return resolved

    def _extract_source_from_google_title(self, raw_title: str) -> tuple[str, str | None]:
        title = (raw_title or "").strip()
        if not title:
            return "", None
        if title.endswith(" - Google News"):
            title = title[: -len(" - Google News")].strip()

        base_title, source_candidate = self._extract_source_from_title_suffix(title)
        if source_candidate:
            return base_title, source_candidate
        return title, None

    def _extract_source_from_title_suffix(self, title: str) -> tuple[str, str | None]:
        text = (title or "").strip()
        if not text:
            return "", None
        parts = [part.strip() for part in re.split(r"\s+-\s+", text) if part.strip()]
        if len(parts) < 2:
            return text, None
        candidate = parts[-1]
        base = " - ".join(parts[:-1]).strip()
        if len(base) < 8:
            return text, None
        if not (2 <= len(candidate) <= 70):
            return text, None
        if candidate.lower() == "google news":
            return text, None
        if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", candidate.lower()):
            return text, None
        if re.search(r"\d{4}", candidate):
            return text, None
        if not re.search(r"[A-Za-z]", candidate):
            return text, None
        return base, candidate

    def _extract_source_from_google_description(self, raw_description: str) -> str | None:
        if not raw_description:
            return None

        # Common Google News RSS pattern: <font color="#6f6f6f">Publisher</font>
        fonts = re.findall(r"<font[^>]*>([^<]+)</font>", raw_description, flags=re.IGNORECASE)
        for text in reversed(fonts):
            candidate = self._clean_html(text)
            if not candidate:
                continue
            if candidate.lower() in {"google news"}:
                continue
            if 2 <= len(candidate) <= 60:
                return candidate

        cleaned = self._clean_html(raw_description)
        if not cleaned:
            return None
        tail_match = re.search(r"(?:•|·|\||-)\s*([A-Za-z][A-Za-z0-9&.'\-\s]{1,50})$", cleaned)
        if tail_match:
            candidate = tail_match.group(1).strip()
            if candidate and candidate.lower() != "google news":
                return candidate
        return None

    def _company_short_names(self) -> dict[str, str]:
        return {ticker: config["name"].split()[0] for ticker, config in COMPANIES.items()}

    def _mentions_tracked_company(self, content: str) -> bool:
        content_lower = content.lower()
        for short in self._company_short_names().values():
            if short.lower() in content_lower:
                return True
        return False

    def _is_ai_related(self, content: str) -> bool:
        content_lower = content.lower()
        return any(term in content_lower for term in AI_TERMS)

    def _get_company_aliases(self, ticker: str, company_name: str) -> list[str]:
        source = OFFICIAL_COMPANY_SOURCES.get(ticker, {})
        aliases = source.get("aliases") or []
        base = [company_name, company_name.split()[0], ticker]
        merged = [x.strip() for x in [*base, *aliases] if x and x.strip()]
        deduped: list[str] = []
        seen = set()
        for term in merged:
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(term)
        return deduped

    def _build_company_news_queries(self, ticker: str, company_name: str) -> list[str]:
        aliases = self._get_company_aliases(ticker, company_name)
        primary = aliases[0]
        short_name = company_name.split()[0]
        quoted_aliases = [f'"{a}"' if " " in a else a for a in aliases[:3]]
        alias_or = " OR ".join(quoted_aliases)
        return [
            # First pull broad company-linked news, then classify downstream.
            f"({alias_or}) news",
            f'{primary} ("press release" OR announcement OR earnings OR guidance OR partnership OR expansion)',
            f'"{short_name}" (manufacturing OR supply chain OR data center OR ai OR "liquid cooling" OR "immersion cooling")',
        ]

    def _is_company_related_item(self, item: dict, ticker: str, company_name: str) -> bool:
        content = f"{item.get('title', '')} {item.get('description', '')}".lower()
        aliases = self._get_company_aliases(ticker, company_name)
        if any(alias.lower() in content for alias in aliases):
            return True

        source = OFFICIAL_COMPANY_SOURCES.get(ticker, {})
        domain = (source.get("domain") or "").lower()
        if not domain:
            return False
        try:
            item_domain = (urlparse(item.get("url", "")).netloc or "").lower().replace("www.", "")
            if item_domain.endswith(domain):
                return True
        except Exception:
            pass

        source_text = (item.get("source") or "").lower()
        return company_name.split()[0].lower() in source_text

    def _parse_published_dt(self, published: str) -> Optional[datetime]:
        value = (published or "").strip()
        if not value:
            return None

        # Handle ISO-8601 formats first.
        iso_candidate = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(iso_candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass

        # Handle RFC2822 formats like "Fri, 06 Mar 2026 10:00:00 GMT".
        try:
            parsed = parsedate_to_datetime(value)
            if parsed is None:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    def _sort_items_by_recency_and_relevance(self, items: list[dict]) -> list[dict]:
        def sort_key(item: dict) -> tuple[int, float, float]:
            published_dt = self._parse_published_dt(item.get("published", ""))
            has_date = 1 if published_dt else 0
            published_epoch = published_dt.timestamp() if published_dt else 0.0
            relevance = float(item.get("relevance_score", 0.0) or 0.0)
            return (has_date, published_epoch, relevance)

        return sorted(items, key=sort_key, reverse=True)

    def _normalize_result(self, result: dict, company_name: str = "") -> Optional[dict]:
        title = (result.get("title") or "").strip()
        url = (result.get("url") or "").strip()
        if not title or not url:
            return None
        noise_content = f"{title} {result.get('description', '')} {url} {result.get('source', '')}".lower()
        if any(term in noise_content for term in EXCLUDED_NOISE_TERMS):
            return None
        if not self._is_likely_accessible(url):
            return None
        description = (result.get("description") or "").strip()
        categories = self._categorize_content(f"{title} {description}")
        backup_url = f"https://www.google.com/search?q={quote_plus(title)}"
        raw_source = (result.get("source") or "").strip()
        original_source = (result.get("original_source") or "").strip()
        source_from_url = self._extract_source(url)
        title_source = self._extract_source_from_title_suffix(title)[1]
        desc_source = self._extract_source_from_google_description(result.get("description", "") or "")
        if original_source:
            resolved_source = original_source
        elif raw_source and raw_source.lower() not in {"google news", "brave search"}:
            resolved_source = raw_source
        elif title_source:
            resolved_source = title_source
        elif desc_source:
            resolved_source = desc_source
        elif source_from_url and source_from_url != "Unknown":
            resolved_source = source_from_url
        else:
            resolved_source = raw_source or "Unknown"
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
            "relevance_score": self._calculate_relevance(
                {"title": title, "description": description}, company_name
            ),
        }

    def _is_likely_accessible(self, url: str) -> bool:
        try:
            domain = (urlparse(url).netloc or "").lower().replace("www.", "")
            if not domain:
                return False
            return all(not domain.endswith(blocked) for blocked in BLOCKED_OR_PAYWALL_DOMAINS)
        except Exception:
            return False

    def _dedupe_items(self, items: list[dict]) -> list[dict]:
        seen = set()
        deduped = []
        for item in items:
            key = (item.get("url", "").strip().lower(), item.get("title", "").strip().lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
    
    async def get_company_news(
        self,
        ticker: str,
        category: Optional[str] = None,
        count: int = 10,
        force_refresh: bool = False,
    ) -> dict:
        """
        Get recent news for a specific company.
        
        Args:
            ticker: Company ticker symbol
            category: Optional category filter (earnings, ai, capex, strategy, operations)
            count: Number of results to return
        """
        company = COMPANIES.get(ticker, {})
        company_name = company.get("name", ticker)
        short_name = company_name.split()[0]
        cache_key = f"company:{ticker}:{category or 'all'}:{count}"
        if not force_refresh and cache_key in self._runtime_cache:
            return self._runtime_cache[cache_key]

        query = f"{company_name} news"
        company_queries = self._build_company_news_queries(ticker, company_name)

        news_items: list[dict] = []

        # Source 0: official company website links (lightweight scraping)
        official_results = await self._fetch_official_company_news(
            ticker,
            company_name,
            limit=max(count * 2, 8),
        )
        for result in official_results:
            normalized = self._normalize_result(result, company_name)
            if normalized:
                news_items.append(normalized)

        # Source 0.5: Public.com stock news board (outbound link aggregator)
        source_cfg = OFFICIAL_COMPANY_SOURCES.get(ticker, {})
        public_news_url = source_cfg.get("public_news_url")
        public_results: list[dict] = []
        if public_news_url:
            public_results = await self._fetch_public_news_links(
                public_news_url,
                ticker,
                company_name,
                limit=max(count * 2, 10),
            )
            for result in public_results:
                normalized = self._normalize_result(result, company_name)
                if normalized:
                    news_items.append(normalized)

        # Source 1: Brave search (if key exists), fan out across multiple queries
        brave_tasks = [
            search_web_with_diagnostics(q, count=max(count * 2, 10))
            for q in [query, *company_queries]
        ]
        brave_responses = await asyncio.gather(*brave_tasks)
        search_results: list[dict] = []
        brave_errors = []
        for results, error in brave_responses:
            search_results.extend(results)
            if error:
                brave_errors.append(error)
        for result in search_results:
            result.setdefault("aggregator", "Brave Search")
            normalized = self._normalize_result(result, company_name)
            if normalized:
                news_items.append(normalized)

        # Source 2: Google News RSS (free), fan out across focused queries
        rss_tasks = [
            self._fetch_google_news_rss_with_diagnostics(q, limit=max(count * 2, 12))
            for q in company_queries
        ]
        rss_responses = await asyncio.gather(*rss_tasks)
        rss_results: list[dict] = []
        rss_errors = []
        for results, error in rss_responses:
            rss_results.extend(results)
            if error:
                rss_errors.append(error)
        for result in rss_results:
            normalized = self._normalize_result(result, company_name)
            if normalized:
                news_items.append(normalized)

        # Fallback source: curated static entries for reliability
        if not news_items:
            for item in FALLBACK_COMPANY_NEWS.get(ticker, []):
                normalized = self._normalize_result(item, company_name)
                if normalized:
                    news_items.append(normalized)

        # Keep only tracked-company relevant content
        filtered_items = []
        for item in self._dedupe_items(news_items):
            if self._is_company_related_item(item, ticker, company_name):
                filtered_items.append(item)

        # Category filter (if requested)
        if category and category in self.CATEGORIES:
            strict = [item for item in filtered_items if category in item.get("categories", [])]
            if strict:
                filtered_items = strict

        filtered_items = self._sort_items_by_recency_and_relevance(filtered_items)
        
        result = {
            "ticker": ticker,
            "company_name": company_name,
            "category_filter": category,
            "news": filtered_items[:count],
            "total_found": len(filtered_items),
            "timestamp": datetime.now().isoformat(),
            "diagnostics": {
                "source_counts": {
                    "official": len(official_results),
                    "public_board": len(public_results),
                    "brave": len(search_results),
                    "google_rss": len(rss_results),
                },
                "errors": {
                    "brave": brave_errors or None,
                    "google_rss": rss_errors or None,
                },
            },
        }
        self._runtime_cache[cache_key] = result
        self._persist_runtime_cache()
        return result
    
    async def get_industry_news(self, count: int = 15, force_refresh: bool = False) -> dict:
        """
        Get industry-wide EMS/electronics manufacturing news.
        """
        cache_key = f"industry:{count}"
        if not force_refresh and cache_key in self._runtime_cache:
            return self._runtime_cache[cache_key]

        queries = [
            "EMS AI infrastructure supply chain news",
            "electronics manufacturing data center demand",
            "Flex Jabil Celestica Benchmark Sanmina AI news",
            "NVIDIA hyperscaler manufacturing partners news",
            "liquid cooling data center manufacturing news",
            "immersion cooling AI server supply chain news",
        ]

        merged_items: list[dict] = []
        for query in queries:
            for result in await search_web(query, count=5):
                result.setdefault("aggregator", "Brave Search")
                normalized = self._normalize_result(result)
                if normalized:
                    merged_items.append(normalized)

            for result in await self._fetch_google_news_rss(query, limit=5):
                normalized = self._normalize_result(result)
                if normalized:
                    merged_items.append(normalized)

        if not merged_items:
            merged_items = [self._normalize_result(item) for item in FALLBACK_INDUSTRY_NEWS]
            merged_items = [item for item in merged_items if item]

        # Keep only AI-related or tracked-company-related stories
        unique_results = []
        for item in self._dedupe_items(merged_items):
            content = f"{item['title']} {item.get('description', '')}"
            if self._is_ai_related(content) or self._mentions_tracked_company(content):
                unique_results.append(item)

        result = {
            "news": unique_results[:count],
            "total_found": len(unique_results),
            "timestamp": datetime.now().isoformat(),
        }
        self._runtime_cache[cache_key] = result
        self._persist_runtime_cache()
        return result
    
    async def get_competitor_comparison_news(self, force_refresh: bool = False) -> dict:
        """
        Get comparative news mentioning multiple competitors.
        """
        cache_key = "comparative"
        if not force_refresh and cache_key in self._runtime_cache:
            return self._runtime_cache[cache_key]

        company_names = [c["name"].split()[0] for c in COMPANIES.values()]
        query = " OR ".join(company_names) + " EMS comparison AI manufacturing"

        raw_results = await search_web(query, count=10)
        for result in raw_results:
            result.setdefault("aggregator", "Brave Search")
        raw_results.extend(await self._fetch_google_news_rss(query, limit=8))

        comparative_news = []
        for result in raw_results:
            normalized = self._normalize_result(result)
            if not normalized:
                continue
            title = normalized.get("title", "")
            description = normalized.get("description", "")
            url = normalized.get("url", "")
            content = f"{title} {description}".lower()
            mentioned = [name for name in company_names if name.lower() in content]
            if len(mentioned) >= 2:
                comparative_news.append(
                    {
                        "title": title,
                        "url": url,
                        "backup_url": normalized.get("backup_url") or f"https://www.google.com/search?q={quote_plus(title)}",
                        "description": description,
                        "source": normalized.get("source"),
                        "original_source": normalized.get("original_source"),
                        "aggregator": normalized.get("aggregator"),
                        "companies_mentioned": mentioned,
                    }
                )

        comparative_news = self._dedupe_items(comparative_news)

        if not comparative_news:
            comparative_news = [
                {
                    "title": "EMS peers balance AI server growth with margin discipline",
                    "url": "https://www.eetimes.com/",
                    "description": "Market commentary compares execution quality across major EMS players serving cloud and AI programs.",
                    "source": "EE Times",
                    "companies_mentioned": company_names[:3],
                }
            ]

        result = {
            "comparative_news": comparative_news,
            "total_found": len(comparative_news),
            "timestamp": datetime.now().isoformat(),
        }
        self._runtime_cache[cache_key] = result
        self._persist_runtime_cache()
        return result
    
    async def get_all_companies_news(self, count_per_company: int = 3, force_refresh: bool = False) -> dict:
        """
        Get news for all tracked companies.
        """
        cache_key = f"all:{count_per_company}"
        if not force_refresh and cache_key in self._runtime_cache:
            return self._runtime_cache[cache_key]

        all_news = {}
        
        for ticker in COMPANIES.keys():
            news = await self.get_company_news(
                ticker,
                count=count_per_company,
                force_refresh=force_refresh,
            )
            all_news[ticker] = news
            # Add delay to avoid rate limiting
            await asyncio.sleep(0.5)
        
        result = {
            "companies": all_news,
            "total_companies": len(all_news),
            "timestamp": datetime.now().isoformat(),
        }
        self._runtime_cache[cache_key] = result
        self._persist_runtime_cache()
        return result

    async def get_flex_news_summary(
        self,
        days: int = 3,
        llm_mode: str = "combined",
        max_items: int = 16,
        force_refresh: bool = False,
    ) -> dict:
        """
        Generate a short Flex-angle summary from current fetched/cached news.

        llm_mode:
        - "anthropic": use direct Anthropic client
        - "openai": use direct OpenAI client
        - "combined": produce both when available, then synthesize
        """
        mode = (llm_mode or "combined").strip().lower()
        if mode not in {"anthropic", "openai", "combined"}:
            mode = "combined"

        cache_key = f"summary:flex:{days}:{mode}:{max_items}"
        if not force_refresh and cache_key in self._runtime_cache:
            return self._runtime_cache[cache_key]

        flex_data = await self.get_company_news("FLEX", count=24, force_refresh=force_refresh)
        industry_data = await self.get_industry_news(count=16, force_refresh=force_refresh)
        comparative_data = await self.get_competitor_comparison_news(force_refresh=force_refresh)

        flex_news = self._filter_recent_news(flex_data.get("news", []), days)
        industry_news = self._filter_recent_news(industry_data.get("news", []), days)
        comparative_news = comparative_data.get("comparative_news", []) or []

        selected_items = self._select_summary_items(
            flex_news=flex_news,
            industry_news=industry_news,
            comparative_news=comparative_news,
            max_items=max_items,
        )
        context = self._build_summary_context(selected_items)

        if not context.strip():
            result = {
                "summary": "No recent news context is available to summarize right now.",
                "llm_mode": mode,
                "providers_used": [],
                "items_used": 0,
                "window_days": days,
                "timestamp": datetime.now().isoformat(),
            }
            self._runtime_cache[cache_key] = result
            self._persist_runtime_cache()
            return result

        providers_used: list[str] = []
        anthropic_text = ""
        openai_text = ""

        if mode in {"anthropic", "combined"}:
            anthropic_text = self._summarize_with_anthropic(context)
            if anthropic_text:
                providers_used.append("anthropic")

        if mode in {"openai", "combined"}:
            openai_text = self._summarize_with_openai(context)
            if openai_text:
                providers_used.append("openai")

        if mode == "anthropic":
            summary = anthropic_text or "Anthropic summary is unavailable. Check ANTHROPIC_API_KEY."
        elif mode == "openai":
            summary = openai_text or "OpenAI summary is unavailable. Check OPENAI_API_KEY."
        else:
            summary = self._synthesize_combined_summary(anthropic_text, openai_text, context)

        result = {
            "summary": summary,
            "llm_mode": mode,
            "providers_used": providers_used,
            "items_used": len(selected_items),
            "window_days": days,
            "timestamp": datetime.now().isoformat(),
        }
        self._runtime_cache[cache_key] = result
        self._persist_runtime_cache()
        return result

    def _filter_recent_news(self, items: list[dict], days: int) -> list[dict]:
        if not items:
            return []
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max(1, int(days)))

        recent = []
        undated = []
        for item in items:
            parsed = self._parse_published_dt(item.get("published", ""))
            if parsed is None:
                undated.append(item)
                continue
            if parsed >= cutoff:
                recent.append(item)

        if recent:
            return recent
        return undated[: max(4, min(10, len(undated)))]

    def _select_summary_items(
        self,
        flex_news: list[dict],
        industry_news: list[dict],
        comparative_news: list[dict],
        max_items: int = 16,
    ) -> list[dict]:
        picks = []
        for item in flex_news[: max_items]:
            picks.append({"bucket": "flex", **item})

        room = max(0, max_items - len(picks))
        if room > 0:
            for item in industry_news[: min(room, max(4, room // 2 or 1))]:
                picks.append({"bucket": "industry", **item})

        room = max(0, max_items - len(picks))
        if room > 0:
            for item in comparative_news[:room]:
                picks.append({"bucket": "comparative", **item})
        return picks[:max_items]

    def _build_summary_context(self, items: list[dict]) -> str:
        lines = []
        for i, item in enumerate(items, 1):
            title = (item.get("title") or "").strip()
            desc = (item.get("description") or "").strip()
            source = (item.get("source") or "Unknown").strip()
            published = (item.get("published") or "").strip()
            bucket = (item.get("bucket") or "general").strip()
            if not title:
                continue
            line = f"{i}. [{bucket}] {title} | source={source}"
            if published:
                line += f" | published={published}"
            if desc:
                line += f"\n   {desc[:260]}"
            lines.append(line)
        return "\n".join(lines)

    def _summary_system_prompt(self) -> str:
        return (
            "You are an equity research assistant for Flex (FLEX). "
            "Write a concise, executive-ready summary from FLEX's perspective using only provided news context. "
            "Do not fabricate facts. If signal confidence is low, say it briefly.\n\n"
            "Output format:\n"
            "1) 3 bullet key takeaways\n"
            "2) 3 bullet implications for Flex (opportunity/risk)\n"
            "3) One-line watchlist for next 7 days"
        )

    def _summarize_with_anthropic(self, context: str) -> str:
        if not ANTHROPIC_API_KEY:
            return ""
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            model = ANTHROPIC_MODEL if "claude" in ANTHROPIC_MODEL else "claude-sonnet-4-6"
            resp = client.messages.create(
                model=model,
                max_tokens=500,
                system=self._summary_system_prompt(),
                messages=[{"role": "user", "content": f"News context:\n{context}"}],
            )
            if resp.content and getattr(resp.content[0], "text", ""):
                return resp.content[0].text.strip()
            return ""
        except Exception:
            return ""

    def _summarize_with_openai(self, context: str) -> str:
        if not OPENAI_API_KEY:
            return ""
        try:
            from openai import OpenAI

            client = OpenAI(api_key=OPENAI_API_KEY)
            model = LLM_MODEL if LLM_MODEL.startswith("gpt-") else "gpt-4o"
            resp = client.chat.completions.create(
                model=model,
                max_tokens=500,
                messages=[
                    {"role": "system", "content": self._summary_system_prompt()},
                    {"role": "user", "content": f"News context:\n{context}"},
                ],
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            return ""

    def _synthesize_combined_summary(self, anthropic_text: str, openai_text: str, context: str) -> str:
        if anthropic_text and openai_text:
            try:
                synthesis_prompt = (
                    "Merge the two candidate summaries below into one concise final summary for FLEX. "
                    "Keep only overlapping/high-confidence points and remove speculation.\n\n"
                    f"[Anthropic]\n{anthropic_text}\n\n[OpenAI]\n{openai_text}"
                )
                merged = llm_complete(
                    messages=[{"role": "user", "content": synthesis_prompt}],
                    system=self._summary_system_prompt(),
                    model_key="fast",
                    max_tokens=450,
                    stream=False,
                )
                if isinstance(merged, str) and merged.strip():
                    return merged.strip()
            except Exception:
                pass
            return anthropic_text
        if anthropic_text:
            return anthropic_text
        if openai_text:
            return openai_text

        fallback = (
            "Key Takeaways:\n"
            "- No LLM provider is currently available for summary generation.\n"
            "- News ingestion appears available, but summary synthesis could not run.\n"
            "- Please verify OpenAI/Enterprise credentials and provider settings.\n\n"
            "Implications for Flex:\n"
            "- Keep monitoring hyperscaler demand and peer execution signals.\n"
            "- Prioritize margin and capacity commentary from official updates.\n"
            "- Re-run summary once provider connectivity is restored.\n\n"
            "Watchlist (7d): FLEX press releases, peer guidance changes, AI infrastructure demand headlines."
        )
        if context.strip():
            return fallback
        return "Summary unavailable due to missing context and provider."
    
    def _extract_source(self, url: str) -> str:
        """Extract source name from URL."""
        url_lower = url.lower()
        for domain, source in SOURCE_DOMAIN_LABELS.items():
            if domain in url_lower:
                return source
        
        # Extract domain as fallback
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "")
        except:
            return "Unknown"
    
    def _categorize_content(self, content: str) -> list[str]:
        """Categorize content based on keywords."""
        content_lower = content.lower()
        categories = []
        
        for category, keywords in self.CATEGORIES.items():
            # Check if any keyword matches (case-insensitive)
            if any(kw.lower() in content_lower for kw in keywords):
                categories.append(category)
        
        # Also check for common patterns that indicate specific categories
        if not categories:
            # Check for earnings-related content
            if any(term in content_lower for term in ['q1', 'q2', 'q3', 'q4', 'quarter', 'fiscal', 'fy2', 'fy2025', 'fy2024', 'eps', 'beat', 'miss']):
                categories.append('earnings')
            # Check for AI/tech content
            if any(term in content_lower for term in ['nvidia', 'hyperscale', 'cloud', 'generative', 'llm', 'chip', 'semiconductor']):
                categories.append('ai')
            if any(term in content_lower for term in ['liquid cooling', 'immersion cooling', 'thermal management', 'heat exchanger', 'cold plate']):
                categories.append('cooling')
            # Check for investment content
            if any(term in content_lower for term in ['million', 'billion', 'invest', 'expand', 'new facility', 'build']):
                categories.append('capex')
            # Check for M&A/strategy
            if any(term in content_lower for term in ['acquire', 'deal', 'agreement', 'partner', 'announce']):
                categories.append('strategy')
        
        return categories if categories else ["general"]
    
    def _calculate_relevance(self, result: dict, company_name: str) -> float:
        """Calculate relevance score for a result."""
        score = 0.0
        content = (result["title"] + " " + result.get("description", "")).lower()
        company_lower = company_name.lower()
        
        # Company name mentioned
        if company_lower in content:
            score += 0.5
        
        # Recent news indicators
        current_year = datetime.now().year
        if any(term in content for term in ["today", "announces", "reports", str(current_year), str(current_year - 1)]):
            score += 0.2
        
        # Business relevance
        if any(term in content for term in ["earnings", "revenue", "investment", "strategy"]):
            score += 0.3

        # AI relevance
        if any(term in content for term in AI_TERMS):
            score += 0.2
        
        return min(score, 1.0)
