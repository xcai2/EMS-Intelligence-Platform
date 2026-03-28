"""
News Aggregator for competitive intelligence.
Aggregates news from multiple sources including RSS feeds.
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

import httpx

from backend.core.config import COMPANIES
from backend.rag.web_search import search_web


# Industry RSS feeds
RSS_FEEDS = {
    "electronics_weekly": "https://www.electronicsweekly.com/feed/",
    "eetimes": "https://www.eetimes.com/feed/",
    "supply_chain_dive": "https://www.supplychaindive.com/feeds/news/",
    "manufacturing_net": "https://www.manufacturing.net/rss/all",
}

# Keywords for categorization
NEWS_CATEGORIES = {
    "earnings": ["earnings", "quarterly results", "revenue", "profit", "EPS", "financial results"],
    "ai": ["artificial intelligence", "AI", "machine learning", "data center", "GPU"],
    "acquisition": ["acquisition", "merger", "acquire", "M&A", "deal", "takeover"],
    "expansion": ["expansion", "new facility", "investment", "plant", "factory"],
    "partnership": ["partnership", "collaboration", "agreement", "contract", "deal"],
    "layoffs": ["layoff", "restructuring", "job cuts", "workforce reduction"],
    "leadership": ["CEO", "CFO", "executive", "appointment", "leadership"],
    "supply_chain": ["supply chain", "shortage", "logistics", "components"],
}


class NewsAggregator:
    """Aggregates news from multiple sources."""
    
    def __init__(self):
        self._cache = {}
        self._cache_time = {}
        self._cache_ttl = 900  # 15 min cache
        self._client = httpx.AsyncClient(timeout=15.0)
    
    def _get_cached(self, key: str) -> Optional[dict]:
        """Get cached data if still valid."""
        if key in self._cache:
            if datetime.now().timestamp() - self._cache_time.get(key, 0) < self._cache_ttl:
                return self._cache[key]
        return None
    
    def _set_cache(self, key: str, data: dict):
        """Cache data."""
        self._cache[key] = data
        self._cache_time[key] = datetime.now().timestamp()
    
    async def fetch_rss_feed(self, feed_url: str, feed_name: str) -> list:
        """Fetch and parse an RSS feed."""
        try:
            response = await self._client.get(feed_url)
            if response.status_code != 200:
                return []
            
            # Parse XML
            root = ET.fromstring(response.text)
            
            items = []
            # Try RSS format
            for item in root.findall('.//item'):
                title = item.findtext('title', '')
                link = item.findtext('link', '')
                description = item.findtext('description', '')
                pub_date = item.findtext('pubDate', '')
                
                items.append({
                    "title": title,
                    "url": link,
                    "snippet": self._clean_html(description)[:200],
                    "published": pub_date,
                    "source": feed_name,
                    "type": "rss",
                })
            
            # Try Atom format if no items
            if not items:
                for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
                    title = entry.findtext('{http://www.w3.org/2005/Atom}title', '')
                    link_elem = entry.find('{http://www.w3.org/2005/Atom}link')
                    link = link_elem.get('href', '') if link_elem is not None else ''
                    summary = entry.findtext('{http://www.w3.org/2005/Atom}summary', '')
                    
                    items.append({
                        "title": title,
                        "url": link,
                        "snippet": self._clean_html(summary)[:200],
                        "source": feed_name,
                        "type": "rss",
                    })
            
            return items[:10]  # Limit per feed
            
        except Exception as e:
            print(f"RSS feed error for {feed_name}: {e}")
            return []
    
    def _clean_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        clean = re.sub(r'<[^>]+>', '', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean
    
    def _categorize_article(self, title: str, snippet: str) -> str:
        """Categorize an article based on content."""
        full_text = (title + ' ' + snippet).lower()
        
        for category, keywords in NEWS_CATEGORIES.items():
            if any(kw.lower() in full_text for kw in keywords):
                return category
        
        return "general"
    
    def _extract_companies_mentioned(self, title: str, snippet: str) -> list:
        """Extract company names mentioned in article."""
        full_text = (title + ' ' + snippet).lower()
        mentioned = []
        
        for ticker, config in COMPANIES.items():
            company_name = config['name'].split()[0].lower()
            if company_name in full_text or ticker.lower() in full_text:
                mentioned.append(config['name'].split()[0])
        
        return mentioned
    
    async def get_company_news(self, company: str, count: int = 10) -> dict:
        """Get news for a specific company."""
        cache_key = f"news_{company}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        all_news = []
        
        # Search web for company news
        try:
            query = f'{company} news latest'
            results = await search_web(query, count=count)

            for result in results:
                category = self._categorize_article(
                    result.get('title', ''), 
                    result.get('snippet', '')
                )
                
                all_news.append({
                    **result,
                    "category": category,
                    "company": company,
                    "type": "web_search",
                })
        except Exception as e:
            print(f"Company news error for {company}: {e}")
        
        result = {
            "company": company,
            "articles": all_news,
            "total": len(all_news),
            "fetch_date": datetime.now().isoformat(),
        }
        
        self._set_cache(cache_key, result)
        return result
    
    async def get_industry_news(self, count: int = 20) -> dict:
        """Get general industry news from RSS feeds and web search."""
        cache_key = "industry_news"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        all_news = []
        
        # Fetch from RSS feeds
        for feed_name, feed_url in RSS_FEEDS.items():
            try:
                items = await self.fetch_rss_feed(feed_url, feed_name)
                for item in items:
                    item['category'] = self._categorize_article(
                        item.get('title', ''),
                        item.get('snippet', '')
                    )
                    item['companies_mentioned'] = self._extract_companies_mentioned(
                        item.get('title', ''),
                        item.get('snippet', '')
                    )
                    all_news.append(item)
            except Exception as e:
                print(f"RSS fetch error for {feed_name}: {e}")
        
        # Also search for EMS industry news
        try:
            query = "EMS electronics manufacturing services industry news"
            results = await search_web(query, count=10)

            for result in results:
                all_news.append({
                    **result,
                    "category": self._categorize_article(
                        result.get('title', ''),
                        result.get('snippet', '')
                    ),
                    "companies_mentioned": self._extract_companies_mentioned(
                        result.get('title', ''),
                        result.get('snippet', '')
                    ),
                    "type": "web_search",
                })
        except Exception as e:
            print(f"Industry news search error: {e}")
        
        # Sort by relevance (articles mentioning tracked companies first)
        all_news.sort(key=lambda x: len(x.get('companies_mentioned', [])), reverse=True)
        
        # Categorize
        by_category = defaultdict(list)
        for article in all_news:
            by_category[article.get('category', 'general')].append(article)
        
        result = {
            "articles": all_news[:count],
            "total": len(all_news),
            "by_category": {cat: len(articles) for cat, articles in by_category.items()},
            "sources": list(RSS_FEEDS.keys()) + ["web_search"],
            "fetch_date": datetime.now().isoformat(),
        }
        
        self._set_cache(cache_key, result)
        return result
    
    async def get_all_companies_news(self, count_per_company: int = 5) -> dict:
        """Get news for all tracked companies."""
        all_company_news = {}
        
        for ticker, config in COMPANIES.items():
            company_name = config['name'].split()[0]
            try:
                news = await self.get_company_news(company_name, count_per_company)
                all_company_news[company_name] = news
            except Exception as e:
                all_company_news[company_name] = {"error": str(e), "articles": []}
        
        return {
            "companies": all_company_news,
            "total_articles": sum(n.get('total', 0) for n in all_company_news.values()),
            "fetch_date": datetime.now().isoformat(),
        }
    
    async def get_trending_topics(self) -> dict:
        """Analyze trending topics across all news."""
        industry_news = await self.get_industry_news(count=30)
        
        # Count category occurrences
        category_counts = industry_news.get('by_category', {})
        
        # Find most mentioned companies
        company_mentions = defaultdict(int)
        for article in industry_news.get('articles', []):
            for company in article.get('companies_mentioned', []):
                company_mentions[company] += 1
        
        # Determine trending topics
        sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
        trending = [cat for cat, _ in sorted_categories[:5]]
        
        return {
            "trending_categories": trending,
            "company_mentions": dict(company_mentions),
            "most_mentioned_company": max(company_mentions.items(), key=lambda x: x[1])[0] if company_mentions else None,
            "category_breakdown": category_counts,
            "analysis_date": datetime.now().isoformat(),
        }


# Singleton instance
_news_aggregator = NewsAggregator()


async def get_company_news(company: str, count: int = 10) -> dict:
    """Get news for a specific company."""
    return await _news_aggregator.get_company_news(company, count)


async def get_industry_news(count: int = 20) -> dict:
    """Get general industry news."""
    return await _news_aggregator.get_industry_news(count)


async def get_all_companies_news(count_per_company: int = 5) -> dict:
    """Get news for all tracked companies."""
    return await _news_aggregator.get_all_companies_news(count_per_company)


async def get_trending_topics() -> dict:
    """Get trending topics in industry news."""
    return await _news_aggregator.get_trending_topics()


def get_news_categories() -> dict:
    """Get available news categories."""
    return {
        cat: {"keywords": keywords[:3]}
        for cat, keywords in NEWS_CATEGORIES.items()
    }


def get_rss_feeds() -> dict:
    """Get configured RSS feeds."""
    return {name: url for name, url in RSS_FEEDS.items()}
