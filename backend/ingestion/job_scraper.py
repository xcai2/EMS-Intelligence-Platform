"""
Job Posting Scraper for competitive intelligence.
Tracks hiring trends to identify strategic priorities.
"""
import re
from datetime import datetime
from typing import Optional
from collections import defaultdict

from backend.core.config import COMPANIES
from backend.rag.web_search import search_web
from backend.scraper.careers_scraper import load_cached_careers, is_cache_stale
from backend.ingestion.job_constants import JOB_CATEGORIES, LOCATION_REGIONS

# Disambiguate company names that share a prefix with other companies
SEARCH_NAME_OVERRIDES = {
    "Flex": '"Flex Ltd"',
}


def _get_cached_official_jobs(company: str, category: Optional[str] = None) -> list[dict]:
    """Read jobs for a company from the official-website JSON cache."""
    all_jobs = load_cached_careers()
    jobs = [j for j in all_jobs if j["company"].lower() == company.lower()]
    if category and category in JOB_CATEGORIES:
        keywords = [k.lower() for k in JOB_CATEGORIES[category]]
        jobs = [j for j in jobs if any(kw in j["title"].lower() for kw in keywords)]
    return jobs


class JobScraper:
    """Scrapes and analyzes job posting data."""
    
    def __init__(self):
        self._cache = {}
        self._cache_time = {}
        self._cache_ttl = 1800  # 30 min cache
    
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
    
    async def search_jobs(self, company: str, category: Optional[str] = None) -> dict:
        """
        Search for job postings at a company.
        """
        cache_key = f"jobs_{company}_{category}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        # Build search query
        search_name = SEARCH_NAME_OVERRIDES.get(company, company)
        if category and category in JOB_CATEGORIES:
            keywords = JOB_CATEGORIES[category][:3]
            query = f'{search_name} jobs careers {" OR ".join(keywords)}'
        else:
            query = f'{search_name} jobs careers hiring'

        all_jobs = []

        # Primary path: read from official-website JSON cache
        try:
            all_jobs = _get_cached_official_jobs(company, category)
        except Exception as e:
            print(f"Official careers cache read error for {company}: {e}")

        # Fallback: web search if cache is empty or stale
        if not all_jobs:
            try:
                results = await search_web(query, count=15)
                for result in results:
                    job_info = self._parse_job_result(result, company)
                    if job_info:
                        all_jobs.append(job_info)
            except Exception as e:
                print(f"Job search error for {company}: {e}")

            try:
                career_query = f'{search_name} careers site:linkedin.com OR site:indeed.com'
                career_results = await search_web(career_query, count=10)
                for result in career_results:
                    job_info = self._parse_job_result(result, company)
                    if job_info:
                        all_jobs.append(job_info)
            except Exception as e:
                print(f"Career search error for {company}: {e}")
        
        # Deduplicate
        seen = set()
        unique_jobs = []
        for job in all_jobs:
            key = job.get('title', '')[:40].lower()
            if key not in seen:
                seen.add(key)
                unique_jobs.append(job)
        
        # Analyze
        analysis = self._analyze_jobs(unique_jobs)
        
        result = {
            "company": company,
            "total_jobs": len(unique_jobs),
            "jobs": unique_jobs[:25],
            "analysis": analysis,
            "search_date": datetime.now().isoformat(),
        }
        
        self._set_cache(cache_key, result)
        return result
    
    def _parse_job_result(self, result: dict, company: str) -> Optional[dict]:
        """Parse a search result into job info."""
        title = result.get('title', '')
        snippet = result.get('snippet') or result.get('description') or result.get('body', '')
        url = result.get('url') or result.get('href', '')
        
        # Check if it's a job posting
        is_job = any(term in title.lower() or term in url.lower() 
                    for term in ['job', 'career', 'hiring', 'position', 'opening', 'linkedin.com/jobs', 'indeed.com'])
        
        if not is_job:
            return None
        
        # Determine category
        category = "general"
        for cat, keywords in JOB_CATEGORIES.items():
            if any(kw.lower() in (title + snippet).lower() for kw in keywords):
                category = cat
                break
        
        # Detect location/region
        region = "unknown"
        full_text = (title + ' ' + snippet).lower()
        for reg, locations in LOCATION_REGIONS.items():
            if any(loc.lower() in full_text for loc in locations):
                region = reg
                break
        
        # Detect seniority
        seniority = "mid"
        if any(term in title.lower() for term in ['senior', 'sr.', 'lead', 'principal']):
            seniority = "senior"
        elif any(term in title.lower() for term in ['junior', 'jr.', 'entry', 'associate']):
            seniority = "junior"
        elif any(term in title.lower() for term in ['director', 'vp', 'head', 'chief', 'manager']):
            seniority = "leadership"
        
        return {
            "title": title,
            "snippet": snippet,
            "url": url,
            "category": category,
            "region": region,
            "seniority": seniority,
            "company": company,
        }
    
    def _analyze_jobs(self, jobs: list) -> dict:
        """Analyze job postings for insights."""
        by_category = defaultdict(int)
        by_region = defaultdict(int)
        by_seniority = defaultdict(int)
        
        for job in jobs:
            by_category[job.get('category', 'general')] += 1
            by_region[job.get('region', 'unknown')] += 1
            by_seniority[job.get('seniority', 'mid')] += 1
        
        # Calculate focus areas
        total = len(jobs) or 1
        ai_focus = (by_category.get('ai_ml', 0) + by_category.get('data_center', 0)) / total
        tech_focus = (by_category.get('software', 0) + by_category.get('hardware', 0)) / total
        
        # Determine hiring priority
        sorted_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
        top_categories = [cat for cat, _ in sorted_categories[:3]]
        
        return {
            "by_category": dict(by_category),
            "by_region": dict(by_region),
            "by_seniority": dict(by_seniority),
            "ai_hiring_focus": round(ai_focus * 100, 1),
            "tech_hiring_focus": round(tech_focus * 100, 1),
            "top_categories": top_categories,
            "is_hiring_ai": ai_focus > 0.1,
            "is_expanding": len(jobs) > 10,
        }
    
    async def compare_hiring_trends(self) -> dict:
        """Compare hiring trends across all companies."""
        comparison = {}
        
        for ticker, config in COMPANIES.items():
            company_name = config['name'].split()[0]
            try:
                jobs = await self.search_jobs(company_name)
                analysis = jobs.get('analysis', {})
                comparison[company_name] = {
                    "total_jobs": jobs.get('total_jobs', 0),
                    "ai_focus": analysis.get('ai_hiring_focus', 0),
                    "tech_focus": analysis.get('tech_hiring_focus', 0),
                    "top_categories": analysis.get('top_categories', []),
                    "is_hiring_ai": analysis.get('is_hiring_ai', False),
                }
            except Exception as e:
                comparison[company_name] = {"total_jobs": 0, "error": str(e)}
        
        # Determine AI hiring leader
        ai_leader = max(comparison.items(), key=lambda x: x[1].get('ai_focus', 0))
        hiring_leader = max(comparison.items(), key=lambda x: x[1].get('total_jobs', 0))
        
        return {
            "companies": comparison,
            "ai_hiring_leader": ai_leader[0],
            "most_active_hiring": hiring_leader[0],
            "analysis_date": datetime.now().isoformat(),
        }
    
    def get_hiring_score(self, jobs: dict) -> dict:
        """Calculate hiring intensity score."""
        analysis = jobs.get('analysis', {})
        total = jobs.get('total_jobs', 0)
        
        # Weight factors
        ai_weight = analysis.get('ai_hiring_focus', 0) * 2
        tech_weight = analysis.get('tech_hiring_focus', 0) * 1.5
        volume_weight = min(total / 20, 1) * 30  # Cap at 20 jobs = 30 points
        
        score = ai_weight + tech_weight + volume_weight
        normalized = min(100, score)
        
        return {
            "hiring_score": round(normalized, 1),
            "total_openings": total,
            "ai_focus_pct": analysis.get('ai_hiring_focus', 0),
            "is_aggressively_hiring": total > 15,
            "strategic_focus": analysis.get('top_categories', [])[:2],
        }


# Singleton instance
_job_scraper = JobScraper()


async def search_company_jobs(company: str, category: Optional[str] = None) -> dict:
    """Search jobs for a company."""
    return await _job_scraper.search_jobs(company, category)


async def compare_all_hiring() -> dict:
    """Compare hiring trends across all companies."""
    return await _job_scraper.compare_hiring_trends()


def get_hiring_score(jobs: dict) -> dict:
    """Get hiring score for job data."""
    return _job_scraper.get_hiring_score(jobs)


def get_job_categories() -> dict:
    """Get available job categories."""
    return {
        cat: {"keywords": keywords[:3], "description": f"{cat.replace('_', ' ').title()} roles"}
        for cat, keywords in JOB_CATEGORIES.items()
    }
