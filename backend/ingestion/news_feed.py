"""
News feed integration for competitive intelligence.
Aggregates news from multiple sources for tracked companies.
"""
import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus, urlparse, urljoin

import httpx

from backend.core.config import COMPANIES
from backend.rag.web_search import search_web


AI_TERMS = [
    "ai",
    "artificial intelligence",
    "data center",
    "gpu",
    "nvidia",
    "hyperscaler",
    "cloud",
    "llm",
    "semiconductor",
]

BLOCKED_OR_PAYWALL_DOMAINS = {
    "wsj.com",
    "ft.com",
    "barrons.com",
    "bloomberg.com",
    "seekingalpha.com",
    "fool.com",
}

OFFICIAL_COMPANY_SOURCES = {
    "FLEX": {
        "name": "Flex",
        "domain": "flex.com",
        "base_url": "https://flex.com",
        "news_url": "https://flex.com/newsroom",
        "rss_url": None,
    },
    "JBL": {
        "name": "Jabil",
        "domain": "jabil.com",
        "base_url": "https://www.jabil.com",
        "news_url": "https://jabil.com/blog.html",
        "rss_url": None,
    },
    "BHE": {
        "name": "Benchmark",
        "domain": "bench.com",
        "base_url": "https://www.bench.com",
        "news_url": "https://www.bench.com/setting-the-benchmark",
        "rss_url": None,
    },
    "SANM": {
        "name": "Sanmina",
        "domain": "sanmina.com",
        "base_url": "https://www.sanmina.com",
        "news_url": "https://www.sanmina.com/media-center/press-releases/",
        "rss_url": None,
    },
    "CLS": {
        "name": "Celestica",
        "domain": "celestica.com",
        "base_url": "https://www.celestica.com",
        "news_url": "https://www.celestica.com",
        "rss_url": None,
    },
}

OFFICIAL_NEWS_KEYWORDS = [
    "news",
    "press",
    "release",
    "announcement",
    "earnings",
    "ai",
    "data center",
    "infrastructure",
    "cloud",
    "server",
]

FALLBACK_COMPANY_NEWS = {
    "FLEX": [
        {
            "title": "Flex expands AI data-center manufacturing collaborations",
            "url": "https://flex.com/newsroom",
            "description": "Flex highlights accelerated demand for AI infrastructure programs and advanced manufacturing services.",
            "source": "Flex Newsroom",
            "categories": ["ai", "operations"],
        },
    ],
    "JBL": [
        {
            "title": "Jabil outlines AI and cloud infrastructure momentum",
            "url": "https://www.jabil.com/about-us/news.html",
            "description": "Jabil updates investors on AI server demand trends and supply-chain execution for hyperscaler customers.",
            "source": "Jabil Newsroom",
            "categories": ["ai", "strategy"],
        },
    ],
    "CLS": [
        {
            "title": "Celestica reports continued growth in CCS segment",
            "url": "https://www.celestica.com/about-us/news-events",
            "description": "Celestica points to sustained cloud and communications demand with AI-related infrastructure tailwinds.",
            "source": "Celestica News",
            "categories": ["earnings", "ai"],
        },
    ],
    "BHE": [
        {
            "title": "Benchmark highlights high-reliability manufacturing programs",
            "url": "https://www.bench.com/newsroom",
            "description": "Benchmark discusses advanced engineering and manufacturing support for compute and industrial customers.",
            "source": "Benchmark Newsroom",
            "categories": ["operations", "strategy"],
        },
    ],
    "SANM": [
        {
            "title": "Sanmina expands focus on complex cloud and networking platforms",
            "url": "https://www.sanmina.com/about/news-events",
            "description": "Sanmina emphasizes execution in compute-heavy and AI-adjacent infrastructure markets.",
            "source": "Sanmina News",
            "categories": ["ai", "operations"],
        },
    ],
}

FALLBACK_INDUSTRY_NEWS = [
    {
        "title": "AI server demand continues to reshape electronics manufacturing priorities",
        "url": "https://www.eetimes.com/",
        "description": "Industry coverage tracks how EMS providers are adapting capacity plans for AI hardware and data-center systems.",
        "source": "EE Times",
        "categories": ["ai", "capex"],
    },
    {
        "title": "Hyperscaler build-outs keep supply-chain resilience in focus",
        "url": "https://www.supplychaindive.com/",
        "description": "Manufacturing and logistics teams are balancing lead-time pressure as AI infrastructure programs scale globally.",
        "source": "Supply Chain Dive",
        "categories": ["ai", "operations"],
    },
]


class NewsFeed:
    """
    Aggregates and manages company news from multiple sources.
    """
    
    # News categories for filtering (all lowercase for case-insensitive matching)
    CATEGORIES = {
        "earnings": ["earnings", "quarterly", "revenue", "profit", "results", "guidance", "eps", "beat", "miss", "forecast", "outlook", "fiscal"],
        "ai": ["artificial intelligence", "ai", "machine learning", "data center", "gpu", "nvidia", "hyperscale", "cloud computing", "generative", "llm", "semiconductor", "chip"],
        "capex": ["capital expenditure", "capex", "investment", "expansion", "factory", "facility", "million", "billion", "spending", "infrastructure"],
        "strategy": ["acquisition", "merger", "partnership", "restructuring", "strategy", "deal", "agreement", "acquire", "divest"],
        "operations": ["manufacturing", "supply chain", "production", "capacity", "logistics", "assembly", "plant"],
    }
    
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 3600  # 1 hour cache
        # Runtime cache: persists until backend process restarts.
        self._runtime_cache: dict[str, dict] = {}

    async def _fetch_google_news_rss(self, query: str, limit: int = 8) -> list[dict]:
        """Fetch Google News RSS results (free, no API key)."""
        rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.get(rss_url)
                if response.status_code != 200:
                    return []

            root = ET.fromstring(response.text)
            items = []
            for item in root.findall(".//item"):
                title = (item.findtext("title", "") or "").replace(" - Google News", "").strip()
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
                        "source": "Google News",
                        "published": item.findtext("pubDate", "") or "",
                    }
                )
                if len(items) >= limit:
                    break
            return items
        except Exception:
            return []

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
        if rss_url:
            collected.extend(await self._fetch_company_rss(source["name"], rss_url, limit=limit))

        # 1.5) Site-scoped Google News RSS (most reliable lightweight source)
        domain = source.get("domain")
        if domain:
            site_query = (
                f'site:{domain} ("news" OR "press release" OR "earnings" OR "AI" OR "data center") {company_name}'
            )
            collected.extend(await self._fetch_google_news_rss(site_query, limit=limit))

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

    def _normalize_result(self, result: dict, company_name: str = "") -> Optional[dict]:
        title = (result.get("title") or "").strip()
        url = (result.get("url") or "").strip()
        if not title or not url:
            return None
        if not self._is_likely_accessible(url):
            return None
        description = (result.get("description") or "").strip()
        categories = self._categorize_content(f"{title} {description}")
        backup_url = f"https://www.google.com/search?q={quote_plus(title)}"
        return {
            "title": title,
            "url": url,
            "backup_url": backup_url,
            "description": description,
            "image_url": (result.get("image_url") or "").strip(),
            "source": result.get("source") or self._extract_source(url),
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

        search_terms = [company_name, "AI", "data center", "earnings", "manufacturing"]
        if category and category in self.CATEGORIES:
            search_terms.extend(self.CATEGORIES[category][:2])
        query = " ".join(search_terms) + " news"

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

        # Source 1: Brave search (if key exists)
        search_results = await search_web(query, count=max(count * 2, 8))
        for result in search_results:
            normalized = self._normalize_result(result, company_name)
            if normalized:
                news_items.append(normalized)

        # Source 2: Google News RSS (free)
        rss_results = await self._fetch_google_news_rss(
            f"{company_name} OR {short_name} (AI OR data center OR earnings OR manufacturing)",
            limit=max(count * 2, 10),
        )
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
            content = f"{item['title']} {item.get('description', '')}"
            if short_name.lower() in content.lower() or ticker.lower() in content.lower():
                filtered_items.append(item)

        # Category filter (if requested)
        if category and category in self.CATEGORIES:
            strict = [item for item in filtered_items if category in item.get("categories", [])]
            if strict:
                filtered_items = strict

        filtered_items.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        result = {
            "ticker": ticker,
            "company_name": company_name,
            "category_filter": category,
            "news": filtered_items[:count],
            "total_found": len(filtered_items),
            "timestamp": datetime.now().isoformat(),
        }
        self._runtime_cache[cache_key] = result
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
        ]

        merged_items: list[dict] = []
        for query in queries:
            for result in await search_web(query, count=5):
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
        raw_results.extend(await self._fetch_google_news_rss(query, limit=8))

        comparative_news = []
        for result in raw_results:
            title = result.get("title", "")
            description = result.get("description", "")
            url = result.get("url", "")
            if not title or not url:
                continue
            content = f"{title} {description}".lower()
            mentioned = [name for name in company_names if name.lower() in content]
            if len(mentioned) >= 2:
                comparative_news.append(
                    {
                        "title": title,
                        "url": url,
                        "backup_url": f"https://www.google.com/search?q={quote_plus(title)}",
                        "description": description,
                        "source": result.get("source") or self._extract_source(url),
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
        return result
    
    def _extract_source(self, url: str) -> str:
        """Extract source name from URL."""
        domain_sources = {
            "reuters.com": "Reuters",
            "bloomberg.com": "Bloomberg",
            "wsj.com": "Wall Street Journal",
            "ft.com": "Financial Times",
            "cnbc.com": "CNBC",
            "yahoo.com": "Yahoo Finance",
            "seekingalpha.com": "Seeking Alpha",
            "fool.com": "Motley Fool",
            "marketwatch.com": "MarketWatch",
            "barrons.com": "Barron's",
            "businesswire.com": "Business Wire",
            "prnewswire.com": "PR Newswire",
            "globenewswire.com": "GlobeNewswire",
        }
        
        url_lower = url.lower()
        for domain, source in domain_sources.items():
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
            if any(term in content_lower for term in ['nvidia', 'gpu', 'hyperscale', 'cloud', 'generative', 'llm', 'chip', 'semiconductor']):
                categories.append('ai')
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


# API routes
from fastapi import APIRouter, HTTPException

router = APIRouter()
_news_feed = NewsFeed()


@router.get("/news/company/{ticker}")
async def get_company_news(ticker: str, category: Optional[str] = None, count: int = 10, force_refresh: bool = False):
    """Get news for a specific company."""
    ticker_upper = ticker.upper()
    if ticker_upper not in COMPANIES:
        raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
    
    return await _news_feed.get_company_news(ticker_upper, category, count, force_refresh=force_refresh)


@router.get("/news/industry")
async def get_industry_news(count: int = 15, force_refresh: bool = False):
    """Get industry-wide EMS news."""
    return await _news_feed.get_industry_news(count, force_refresh=force_refresh)


@router.get("/news/comparative")
async def get_comparative_news(force_refresh: bool = False):
    """Get news comparing multiple companies."""
    return await _news_feed.get_competitor_comparison_news(force_refresh=force_refresh)


@router.get("/news/all")
async def get_all_news(count_per_company: int = 3, force_refresh: bool = False):
    """Get news for all tracked companies."""
    return await _news_feed.get_all_companies_news(count_per_company, force_refresh=force_refresh)


# Convenience functions
async def get_company_news(ticker: str, category: Optional[str] = None) -> dict:
    """Get news for a company."""
    return await _news_feed.get_company_news(ticker, category)


async def get_latest_industry_news() -> dict:
    """Get latest industry news."""
    return await _news_feed.get_industry_news()
