"""
EMS Careers Scraper
Scrapes job postings from all 6 EMS companies' official careers pages.
Uses Selenium for JS-rendered pages, requests+BeautifulSoup for static pages.
Mirrors ems_scraper.py in structure; output written to data/careers_cache.json.
"""

import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

import requests
from bs4 import BeautifulSoup

from backend.scraper.careers_config import CAREERS_CONFIG
from backend.core.config import BASE_DIR
from backend.ingestion.job_constants import JOB_CATEGORIES, LOCATION_REGIONS

logger = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "data"
JSON_PATH = OUTPUT_DIR / "careers_cache.json"
META_PATH = OUTPUT_DIR / "careers_scrape_meta.json"

_REQUESTS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Selenium driver factory (same flags as ems_scraper.py)
# ---------------------------------------------------------------------------

def _make_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(options=options)


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _first_text(soup_element, selectors: list[str]) -> str:
    """Try each CSS selector in order; return the first non-empty text found."""
    for sel in selectors:
        try:
            found = soup_element.select_one(sel)
            if found:
                text = found.get_text(separator=" ", strip=True)
                if text:
                    return text
        except Exception:
            continue
    # Fallback: the element's own text
    return soup_element.get_text(separator=" ", strip=True)[:120]


def _first_href(soup_element, selectors: list[str], base_url: str) -> str:
    """Return the first matching anchor href, made absolute."""
    for sel in selectors:
        try:
            found = soup_element.select_one(sel)
            if found and found.get("href"):
                href = found["href"].strip()
                if href.startswith("http"):
                    return href
                if href.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(base_url)
                    return f"{parsed.scheme}://{parsed.netloc}{href}"
        except Exception:
            continue
    return ""


def _classify_category(title: str) -> str:
    """Assign a JOB_CATEGORIES key based on job title keywords."""
    title_lower = title.lower()
    for cat, keywords in JOB_CATEGORIES.items():
        if any(kw.lower() in title_lower for kw in keywords):
            return cat
    return "general"


def _classify_region(location: str) -> str:
    """Map a location string to one of the LOCATION_REGIONS keys."""
    loc_lower = location.lower()
    for region, places in LOCATION_REGIONS.items():
        if any(p.lower() in loc_lower for p in places):
            return region
    return "unknown"


def _classify_seniority(title: str) -> str:
    t = title.lower()
    if any(w in t for w in ["director", "vp", "vice president", "head of", "chief", "manager"]):
        return "leadership"
    if any(w in t for w in ["senior", "sr.", "sr ", "lead", "principal", "staff"]):
        return "senior"
    if any(w in t for w in ["junior", "jr.", "jr ", "entry", "associate", "intern"]):
        return "junior"
    return "mid"


def _clean_field(text: str) -> str:
    """Strip known ATS label prefixes that bleed into text content."""
    import re
    text = re.sub(r'^locations\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^location\s*', '', text, flags=re.IGNORECASE)
    return text.strip()


def _normalize_job(
    title: str,
    location: str,
    department: str,
    apply_url: str,
    company: str,
    source_url: str,
) -> dict:
    """Build a normalized job record matching the shape expected by job_scraper.py."""
    location = _clean_field(location)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "company": company,
        "title": title.strip()[:200],
        "location": location[:200],
        "department": department.strip()[:100],
        "seniority": _classify_seniority(title),
        "region": _classify_region(location),
        "category": _classify_category(title),
        "apply_url": apply_url,
        "source": "official_website",
        "source_url": source_url,
        "scraped_at": now,
        # Legacy fields expected by _parse_job_result consumers
        "snippet": f"{location} | {department}".strip(" |"),
        "url": apply_url,
    }


# ---------------------------------------------------------------------------
# HTML parser (shared by both requests and selenium paths)
# ---------------------------------------------------------------------------

def _parse_html(html: str, company: str, config: dict, source_url: str) -> list[dict]:
    """
    Extract job records from raw HTML using the config's CSS selector lists.
    Returns a (possibly empty) list of normalized job dicts.
    """
    soup = BeautifulSoup(html, "html.parser")
    selectors = config["selectors"]
    jobs: list[dict] = []
    seen_titles: set[str] = set()

    # Try each card selector to find job containers
    cards = []
    for card_sel in selectors["job_card"]:
        cards = soup.select(card_sel)
        if cards:
            logger.debug("[%s] card selector '%s' matched %d elements", company, card_sel, len(cards))
            break

    if not cards:
        # Fallback: treat every <li> or <article> as a potential card
        cards = soup.select("li, article")
        logger.debug("[%s] fallback: %d li/article elements", company, len(cards))

    for card in cards:
        title = _first_text(card, selectors["title"])
        location = _first_text(card, selectors["location"])
        department = _first_text(card, selectors["department"])
        apply_url = _first_href(card, selectors["link"], source_url)

        # Skip cards where no meaningful title was found
        if not title or len(title) < 4:
            continue
        # Skip bare ATS reference IDs (e.g. Workday "WD219341" entries with no real content)
        import re as _re
        if _re.match(r'^WD\d+$', title.strip()):
            continue
        # Skip navigation / footer noise
        if any(noise in title.lower() for noise in ["menu", "search", "login", "sign in", "cookie"]):
            continue

        dedup_key = title.lower()[:60]
        if dedup_key in seen_titles:
            continue
        seen_titles.add(dedup_key)

        jobs.append(_normalize_job(title, location, department, apply_url, company, source_url))

    return jobs


# ---------------------------------------------------------------------------
# Per-method scrapers
# ---------------------------------------------------------------------------

def _scrape_with_requests(company: str, config: dict) -> list[dict]:
    """Static-HTML scraping path using requests + BeautifulSoup.
    Supports multiple URLs via the optional 'additional_urls' config key,
    and offset-based pagination via 'startrow_step'.
    """
    all_jobs: list[dict] = []
    seen_titles: set[str] = set()
    base_url = config.get("base_url", config["search_url"])
    max_pages = config.get("max_pages", 1)
    page_param = config.get("page_param", "page")
    startrow_step = config.get("startrow_step")

    urls_to_scrape = [config["search_url"]] + config.get("additional_urls", [])

    for url in urls_to_scrape:
        for page_num in range(1, max_pages + 1):
            if startrow_step:
                offset = (page_num - 1) * startrow_step
                sep = "&" if "?" in url else "?"
                page_url = url if offset == 0 else f"{url}{sep}{page_param}={offset}"
            else:
                page_url = f"{url}?{page_param}={page_num}" if page_num > 1 else url

            try:
                resp = requests.get(page_url, headers=_REQUESTS_HEADERS, timeout=20)
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("[%s] requests GET failed for %s: %s", company, page_url, exc)
                break

            page_jobs = _parse_html(resp.text, company, config, base_url)
            new_jobs = [j for j in page_jobs if j["title"].lower()[:60] not in seen_titles]
            for j in new_jobs:
                seen_titles.add(j["title"].lower()[:60])
            logger.info("[%s] page %d (requests): %d jobs (%d new)", company, page_num, len(page_jobs), len(new_jobs))
            all_jobs.extend(new_jobs)

            if len(new_jobs) == 0:
                break

            time.sleep(1.5)

    return all_jobs


def _scrape_with_selenium(company: str, config: dict) -> list[dict]:
    """JS-rendered scraping path using Selenium."""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By

    all_jobs: list[dict] = []
    url = config["search_url"]
    max_pages = config.get("max_pages", 1)
    page_param = config.get("page_param", "page")
    wait_secs = config.get("wait_seconds", 4)

    driver = _make_driver()
    try:
        for page_num in range(1, max_pages + 1):
            page_url = f"{url}?{page_param}={page_num}" if page_num > 1 else url
            logger.info("[%s] selenium loading page %d: %s", company, page_num, page_url)
            try:
                driver.get(page_url)
                time.sleep(wait_secs)
            except Exception as exc:
                logger.warning("[%s] selenium navigation failed: %s", company, exc)
                break

            html = driver.page_source
            page_jobs = _parse_html(html, company, config, url)
            logger.info("[%s] page %d (selenium): %d jobs", company, page_num, len(page_jobs))
            all_jobs.extend(page_jobs)

            if not config.get("pagination") or len(page_jobs) == 0:
                break

            time.sleep(2)
    finally:
        driver.quit()

    return all_jobs


def _scrape_with_selenium_click(company: str, config: dict) -> list[dict]:
    """Selenium scraper that advances through click-based pagination (e.g. Eightfold AI)."""
    from selenium.webdriver.common.by import By

    all_jobs: list[dict] = []
    seen_titles: set[str] = set()
    url = config["search_url"]
    base_url = config.get("base_url", url)
    max_pages = config.get("max_pages", 5)
    wait_secs = config.get("wait_seconds", 6)
    next_btn_sel = config.get("next_button_selector", "[class*='pagination-next']")

    driver = _make_driver()
    try:
        driver.get(url)
        time.sleep(wait_secs)

        for page_num in range(1, max_pages + 1):
            html = driver.page_source
            page_jobs = _parse_html(html, company, config, base_url)
            new_jobs = [j for j in page_jobs if j["title"].lower()[:60] not in seen_titles]
            for j in new_jobs:
                seen_titles.add(j["title"].lower()[:60])
            logger.info("[%s] page %d (selenium-click): %d jobs (%d new)", company, page_num, len(page_jobs), len(new_jobs))
            all_jobs.extend(new_jobs)

            if page_num >= max_pages:
                break

            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, next_btn_sel)
                btn_classes = next_btn.get_attribute("class") or ""
                if "disabled" in btn_classes:
                    logger.info("[%s] reached last page at %d", company, page_num)
                    break
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(wait_secs)
            except Exception as exc:
                logger.info("[%s] pagination ended at page %d: %s", company, page_num, exc)
                break
    finally:
        driver.quit()

    return all_jobs


# ---------------------------------------------------------------------------
# Public scraping functions
# ---------------------------------------------------------------------------

def scrape_company_careers(company: str) -> list[dict]:
    """
    Scrape job postings for one company from its official careers page.
    Tries the configured method; falls back to selenium if requests returns < 5 jobs.
    """
    config = CAREERS_CONFIG.get(company)
    if not config:
        logger.error("No CAREERS_CONFIG entry for '%s'", company)
        return []

    method = config.get("method", "selenium")
    logger.info("[%s] scraping careers via %s from %s", company, method, config["search_url"])

    try:
        if method == "requests":
            jobs = _scrape_with_requests(company, config)
            if len(jobs) < 5:
                logger.info("[%s] requests returned %d jobs, escalating to selenium", company, len(jobs))
                jobs = _scrape_with_selenium(company, config)
        elif method == "selenium_click":
            jobs = _scrape_with_selenium_click(company, config)
        else:
            jobs = _scrape_with_selenium(company, config)
    except Exception as exc:
        logger.exception("[%s] scrape failed: %s", company, exc)
        jobs = []

    logger.info("[%s] total jobs scraped: %d", company, len(jobs))
    return jobs


def run_all_careers_scrape() -> dict:
    """
    Scrape all 6 EMS companies and write results to data/careers_cache.json.
    Returns a summary dict with per-company counts.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_jobs: list[dict] = []
    summary: dict[str, int] = {}
    meta: dict[str, str] = {}
    now = datetime.now(timezone.utc).isoformat()

    for company in CAREERS_CONFIG:
        logger.info("=== Scraping %s ===", company)
        jobs = scrape_company_careers(company)
        all_jobs.extend(jobs)
        summary[company] = len(jobs)
        meta[company] = now

    # Write cache
    with open(JSON_PATH, "w") as f:
        json.dump(all_jobs, f, indent=2)
    logger.info("Written %d total jobs to %s", len(all_jobs), JSON_PATH)

    # Write meta
    with open(META_PATH, "w") as f:
        json.dump({"scraped_at": now, "companies": meta, "totals": summary}, f, indent=2)

    return {"total": len(all_jobs), "by_company": summary, "scraped_at": now}


# ---------------------------------------------------------------------------
# Cache loaders (called by job_scraper.py)
# ---------------------------------------------------------------------------

def load_cached_careers() -> list[dict]:
    """Load all cached job records from careers_cache.json."""
    if not JSON_PATH.exists():
        logger.warning("careers_cache.json not found at %s — returning empty list", JSON_PATH)
        return []
    try:
        with open(JSON_PATH) as f:
            return json.load(f)
    except Exception as exc:
        logger.error("Failed to read careers_cache.json: %s", exc)
        return []


def load_scrape_meta_careers() -> dict:
    """Return last-scraped metadata (timestamps, per-company totals)."""
    if not META_PATH.exists():
        return {}
    try:
        with open(META_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def is_cache_stale(max_age_hours: int = 24) -> bool:
    """Return True if the cache is missing or older than max_age_hours."""
    if not JSON_PATH.exists():
        return True
    meta = load_scrape_meta_careers()
    scraped_at_str = meta.get("scraped_at")
    if not scraped_at_str:
        return True
    try:
        scraped_at = datetime.fromisoformat(scraped_at_str)
        age_hours = (datetime.now(timezone.utc) - scraped_at).total_seconds() / 3600
        return age_hours > max_age_hours
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Per-company refresh with change detection
# ---------------------------------------------------------------------------

def refresh_company_careers(company: str) -> dict:
    """
    Re-scrape one company's careers page and update careers_cache.json only if jobs changed.
    Returns a diff summary: {changed, added, removed, total, jobs, scraped_at}.
    Designed to be called from a background thread (Selenium is blocking).
    """
    all_cached = load_cached_careers()
    old_jobs = [j for j in all_cached if j["company"].lower() == company.lower()]
    old_titles = {j["title"].lower()[:60] for j in old_jobs}

    new_jobs = scrape_company_careers(company)
    new_titles = {j["title"].lower()[:60] for j in new_jobs}

    added = len(new_titles - old_titles)
    removed = len(old_titles - new_titles)
    changed = added > 0 or removed > 0

    if changed:
        other_jobs = [j for j in all_cached if j["company"].lower() != company.lower()]
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(JSON_PATH, "w") as f:
            json.dump(other_jobs + new_jobs, f, indent=2)

        meta = load_scrape_meta_careers()
        now = datetime.now(timezone.utc).isoformat()
        meta.setdefault("companies", {})[company] = now
        meta["scraped_at"] = now
        with open(META_PATH, "w") as f:
            json.dump(meta, f, indent=2)

        logger.info("[%s] cache updated: +%d added, -%d removed", company, added, removed)
    else:
        logger.info("[%s] no changes detected; cache unchanged", company)

    return {
        "changed": changed,
        "added": added,
        "removed": removed,
        "total": len(new_jobs),
        "jobs": new_jobs,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    company_arg = sys.argv[1] if len(sys.argv) > 1 else None

    if company_arg:
        if company_arg not in CAREERS_CONFIG:
            print(f"Unknown company '{company_arg}'. Available: {list(CAREERS_CONFIG)}")
            sys.exit(1)
        jobs = scrape_company_careers(company_arg)
        print(f"\n{company_arg}: {len(jobs)} jobs scraped")
        for j in jobs[:5]:
            print(f"  {j['title']} | {j['location']} | {j['category']}")
    else:
        result = run_all_careers_scrape()
        print("\n=== Scrape complete ===")
        print(f"Total: {result['total']} jobs")
        for company, count in result["by_company"].items():
            print(f"  {company}: {count} jobs")
