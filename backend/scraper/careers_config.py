"""
EMS Careers Scraper - Per-company configuration.
Each entry defines the official careers page URL and scraping strategy.
Mirrors scraper_config.py (Facilities Map) in structure.
"""

CAREERS_CONFIG = {
    "Flex": {
        "url": "https://flex.com/careers",
        "method": "selenium",
        # Flex careers listing is JS-rendered; search page requires interaction
        "search_url": "https://flex.com/careers/search-jobs",
        "selectors": {
            "job_card": [
                "[data-automation='jobTitle']",
                ".job-card",
                "li[class*='job']",
                "article[class*='job']",
            ],
            "title": [
                "[data-automation='jobTitle']",
                ".job-title",
                "h2", "h3",
            ],
            "location": [
                "[data-automation='jobLocation']",
                ".job-location",
                "[class*='location']",
            ],
            "department": [
                "[data-automation='jobCategory']",
                "[class*='department']",
                "[class*='category']",
            ],
            "link": [
                "a[href*='/careers/']",
                "a[href*='/jobs/']",
                "a",
            ],
        },
        "pagination": True,
        "max_pages": 3,
        "page_param": "page",
        "wait_seconds": 4,
    },
    "Jabil": {
        "url": "https://jobs.jabil.com/en",
        "method": "selenium",
        "search_url": "https://jobs.jabil.com/en/search-jobs",
        "selectors": {
            "job_card": [
                "li.search-results-list__item",
            ],
            "title": [
                ".search-results-list__job-title",
            ],
            "location": [
                ".job-location dd",
                ".job-location",
            ],
            "department": [
                ".job-category dd",
                ".job-category",
            ],
            "link": [
                "a.search-results-list__job-link",
                "a",
            ],
        },
        "pagination": True,
        "max_pages": 5,
        "page_param": "page",
        "wait_seconds": 6,
    },
    "Sanmina": {
        "url": "https://www.sanmina.com/careers/",
        "method": "selenium",
        "search_url": "https://www.sanmina.com/careers/",
        "selectors": {
            "job_card": [
                ".job",
                ".career-listing",
                "li[class*='job']",
                "[class*='position']",
                "tr[class*='job']",
            ],
            "title": [
                ".job-title",
                "h3", "h2",
                "td:first-child",
            ],
            "location": [
                "[class*='location']",
                ".city",
                "td:nth-child(2)",
            ],
            "department": [
                "[class*='dept']",
                "[class*='category']",
                "[class*='function']",
            ],
            "link": [
                "a[href*='/career']",
                "a[href*='/job']",
                "a",
            ],
        },
        "pagination": False,
        "max_pages": 1,
        "wait_seconds": 4,
    },
    "Celestica": {
        "url": "https://careers.celestica.com/",
        # Category pages are static HTML — requests works fine (bypasses JS cookie popup)
        "method": "requests",
        "search_url": "https://careers.celestica.com/go/Engineering-Jobs/1280201/",
        # Additional category pages scraped in sequence
        "additional_urls": [
            "https://careers.celestica.com/go/Operations-Jobs/1283401/",
            "https://careers.celestica.com/go/Corporate-Jobs/8944401/",
        ],
        "base_url": "https://careers.celestica.com",
        "selectors": {
            "job_card": [
                "tr.data-row",
            ],
            "title": [
                "a.jobTitle-link",
            ],
            "location": [
                ".jobLocation",
            ],
            "department": [
                ".jobCategory",
            ],
            "link": [
                "a.jobTitle-link",
            ],
        },
        "pagination": False,
        "max_pages": 1,
        "wait_seconds": 3,
    },
    "Plexus": {
        "url": "https://www.plexus.com/careers/",
        "method": "selenium",
        "search_url": "https://www.plexus.com/careers/",
        "selectors": {
            "job_card": [
                ".job-card",
                "[class*='position']",
                "li.job",
                "[class*='job-item']",
                "article",
            ],
            "title": [
                "h3", "h2",
                ".job-title",
                "[class*='title']",
            ],
            "location": [
                ".location",
                "[class*='location']",
                "[class*='city']",
            ],
            "department": [
                "[class*='category']",
                "[class*='dept']",
                "[class*='function']",
            ],
            "link": [
                "a[href*='/careers/']",
                "a[href*='/jobs/']",
                "a",
            ],
        },
        "pagination": True,
        "max_pages": 3,
        "page_param": "page",
        "wait_seconds": 4,
    },
    "Benchmark": {
        "url": "https://www.bench.com/careers",
        "method": "selenium",
        "search_url": "https://www.bench.com/careers",
        "selectors": {
            "job_card": [
                ".job",
                "[class*='position']",
                "li[class*='job']",
                "[class*='opening']",
                "article",
            ],
            "title": [
                "h3", "h2",
                ".job-title",
                ".position-title",
                "[class*='title']",
            ],
            "location": [
                "[class*='location']",
                ".city",
                "[class*='city']",
            ],
            "department": [
                "[class*='department']",
                "[class*='function']",
                "[class*='category']",
            ],
            "link": [
                "a[href*='/careers/']",
                "a[href*='/jobs/']",
                "a",
            ],
        },
        "pagination": False,
        "max_pages": 1,
        "wait_seconds": 4,
    },
}
