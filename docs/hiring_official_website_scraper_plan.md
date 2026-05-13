# Hiring: Official Website Scraper — Implementation Plan

**Branch:** `512`  
**Date:** 2026-05-12  
**Scope:** Replace web-search-based job scraping (Indeed / LinkedIn) with direct scraping of each EMS company's official careers page.

---

## 1. Current State

`backend/ingestion/job_scraper.py` → `JobScraper.search_jobs()`

The current implementation uses `search_web()` (a Bing/DuckDuckGo web-search wrapper) to find job postings:

```python
career_query = f'{search_name} careers site:linkedin.com OR site:indeed.com'
career_results = await search_web(career_query, count=10)
```

**Problems with this approach:**
- Returns snippets only — no actual job title, location, or apply-link from the company itself
- Results depend on third-party indexing and are often stale
- LinkedIn and Indeed block programmatic access; many results are redirects
- No control over data freshness or structure

---

## 2. Target Architecture (mirrors Facilities Map pattern)

The Facilities Map was solved in the same way — official website scraping via Selenium, results cached to JSON, served through a loader function. We copy that exact pattern.

```
Facilities Map:                         Hiring (new):
  scraper_config.py (URLs)       →        careers_config.py (URLs)
  ems_scraper.py (Selenium)      →        careers_scraper.py (Selenium)
  data/ems_facilities.json       →        data/careers_cache.json
  geographic.py (loader)         →        job_scraper.py (loader, replaces search_web)
  GET /company/{id}/geographic   →        GET /jobs/{company} (unchanged)
```

The API endpoint shape (`GET /jobs/{company}`) stays **unchanged** so the frontend requires no modification.

---

## 3. Files to Create / Modify

### 3.1 New: `backend/scraper/careers_config.py`

Per-company careers page URL + scraping strategy.
Mirrors `scraper_config.py` exactly.

```python
CAREERS_CONFIG = {
    "Flex": {
        "url": "https://flex.com/careers",
        "method": "selenium",
        "parse_type": "job_card_list",
        "selectors": {
            "job_card": "[data-automation='jobTitle'], .job-card, .career-item",
            "title":    ".job-title, h3, [data-automation='jobTitle']",
            "location": ".job-location, .location",
            "department":"[class*='department'], [class*='category']",
            "link":      "a[href*='/careers/'], a[href*='/jobs/']",
        },
        "pagination": True,
    },
    "Jabil": {
        "url": "https://careers.jabil.com/en/search-jobs",
        "method": "selenium",
        "parse_type": "job_card_list",
        "selectors": {
            "job_card": ".job-list-item, article.job",
            "title":    ".job-title, h2",
            "location": ".job-location",
            "department":"[class*='dept'], [class*='function']",
            "link":      "a",
        },
        "pagination": True,
    },
    "Sanmina": {
        "url": "https://www.sanmina.com/careers/",
        "method": "selenium",
        "parse_type": "job_card_list",
        "selectors": {
            "job_card": ".job, .career-listing, li[class*='job']",
            "title":    ".job-title, h3",
            "location": "[class*='location']",
            "department":"[class*='dept'], [class*='category']",
            "link":      "a",
        },
        "pagination": False,
    },
    "Celestica": {
        "url": "https://www.celestica.com/careers/search-jobs",
        "method": "requests",           # static HTML
        "parse_type": "job_card_list",
        "selectors": {
            "job_card": ".job-listing, .career-item, tr.job-row",
            "title":    ".job-title, td:first-child",
            "location": ".location, td:nth-child(2)",
            "department":"[class*='dept']",
            "link":      "a",
        },
        "pagination": True,
    },
    "Plexus": {
        "url": "https://www.plexus.com/careers/",
        "method": "selenium",
        "parse_type": "job_card_list",
        "selectors": {
            "job_card": ".job-card, [class*='position'], li.job",
            "title":    "h3, .job-title",
            "location": ".location, [class*='location']",
            "department":"[class*='category'], [class*='dept']",
            "link":      "a",
        },
        "pagination": True,
    },
    "Benchmark": {
        "url": "https://www.bench.com/careers",
        "method": "selenium",
        "parse_type": "job_card_list",
        "selectors": {
            "job_card": ".job, [class*='position'], li[class*='job']",
            "title":    "h3, .job-title, .position-title",
            "location": "[class*='location'], .city",
            "department":"[class*='department'], [class*='function']",
            "link":      "a",
        },
        "pagination": False,
    },
}
```

> **Note on selectors:** CSS selectors are starting points based on publicly documented structures. The `careers_scraper.py` uses a multi-fallback strategy (tries each selector in order, takes the first non-empty match), so minor HTML changes on the company sites will not break the scraper.

---

### 3.2 New: `backend/scraper/careers_scraper.py`

Selenium-based scraper that mirrors `ems_scraper.py`'s structure.

**Key design decisions (same as Facilities):**

| Decision | Choice | Reason |
|---|---|---|
| Browser driver | `selenium` + headless Chrome | All 6 career sites use heavy JS rendering |
| Fallback | `requests` + `BeautifulSoup` | For static pages (Celestica) |
| Output | `data/careers_cache.json` | Same pattern as `ems_facilities.json` |
| Cache TTL | 24 hours | Job listings change daily at most |
| Pagination | Collect up to 3 pages per company | Balance completeness vs. scrape time |
| Rate limiting | 2–3 s sleep between page loads | Respect server load |

**Output JSON schema per job entry:**

```json
{
  "company": "Flex",
  "title": "Senior Manufacturing Engineer",
  "location": "Guadalajara, Mexico",
  "department": "Manufacturing",
  "seniority": "senior",
  "region": "Americas",
  "category": "manufacturing",
  "apply_url": "https://flex.com/careers/job/123",
  "source": "official_website",
  "scraped_at": "2026-05-12T10:00:00Z"
}
```

**Main functions:**

```python
def scrape_company_careers(company: str, config: dict) -> list[dict]
    # Selenium or requests → parse → normalize → return job list

def run_all_careers_scrape() -> dict
    # Loops over CAREERS_CONFIG, calls scrape_company_careers, writes JSON

def load_cached_careers() -> list[dict]
    # Reads careers_cache.json, same interface as load_cached_facilities()

def load_scrape_meta_careers() -> dict
    # Returns last-scraped timestamps per company
```

**Selector fallback strategy** (key difference from facilities, which used regex):

```python
def _extract_field(element, selectors: list[str]) -> str:
    for sel in selectors:
        found = element.select_one(sel)
        if found and found.get_text(strip=True):
            return found.get_text(strip=True)
    return ""
```

---

### 3.3 Modified: `backend/ingestion/job_scraper.py`

**Replace** the `search_web()` calls in `search_jobs()` with a read from the JSON cache.

**Before (current):**
```python
results = await search_web(query, count=15)
career_results = await search_web(career_query, count=10)  # site:linkedin.com OR site:indeed.com
```

**After (new):**
```python
from backend.scraper.careers_scraper import load_cached_careers

def _get_cached_official_jobs(company: str, category: Optional[str] = None) -> list[dict]:
    all_jobs = load_cached_careers()
    jobs = [j for j in all_jobs if j["company"].lower() == company.lower()]
    if category and category in JOB_CATEGORIES:
        keywords = [k.lower() for k in JOB_CATEGORIES[category]]
        jobs = [j for j in jobs if any(kw in j["title"].lower() for kw in keywords)]
    return jobs
```

`search_jobs()` becomes synchronous for the cache read path; `async` signature preserved for API compatibility.  
The `_parse_job_result()`, `_analyze_jobs()`, and `get_hiring_score()` functions are **unchanged** — they receive the same job dict shape.

---

### 3.4 Not modified

| File | Reason |
|---|---|
| `backend/api/routes/supplemental_data.py` | API endpoint unchanged |
| `backend/api/routes/company_detail.py` | No hiring calls here |
| All frontend files | API response shape preserved |
| `ems_scraper.py` / `scraper_config.py` | Facilities scraper untouched |

---

## 4. Official Careers URLs (verified)

| Company | Ticker | Careers URL | Method |
|---|---|---|---|
| Flex | FLEX | https://flex.com/careers | Selenium |
| Jabil | JBL | https://careers.jabil.com/en/search-jobs | Selenium |
| Sanmina | SANM | https://www.sanmina.com/careers/ | Selenium |
| Celestica | CLS | https://www.celestica.com/careers/search-jobs | requests |
| Plexus | PLXS | https://www.plexus.com/careers/ | Selenium |
| Benchmark | BHE | https://www.bench.com/careers | Selenium |

---

## 5. Data Flow (end-to-end)

```
[Cron / manual trigger]
        ↓
careers_scraper.run_all_careers_scrape()
        ↓  Selenium / requests → parse HTML
data/careers_cache.json   ←──── writes
        ↓
job_scraper.load_cached_careers()   (replaces search_web)
        ↓
GET /jobs/{company}  →  frontend Hiring tab
```

---

## 6. Execution Order

1. **Create** `backend/scraper/careers_config.py`
2. **Create** `backend/scraper/careers_scraper.py`
3. **Modify** `backend/ingestion/job_scraper.py` — swap `search_web` for cache loader
4. **Run** `careers_scraper.run_all_careers_scrape()` once to populate `data/careers_cache.json`
5. **Test** `GET /jobs/flex`, `GET /jobs/jabil` etc. and verify response shape matches existing format
6. Commit, PR `512 → main`

---

## 7. Risk & Mitigation

| Risk | Mitigation |
|---|---|
| Company site HTML changes break selectors | Multi-fallback CSS selector list; alert logged on empty result |
| Career site blocks headless Chrome | Rotate user-agent; add `--disable-blink-features=AutomationControlled` flag |
| Empty cache on first deploy | Fall back to `search_web` path if `careers_cache.json` missing or empty |
| Pagination depth unknown | Cap at 3 pages; log total extracted per company |
| Celestica uses client-side routing | Start with `requests`; escalate to Selenium if <5 jobs returned |
