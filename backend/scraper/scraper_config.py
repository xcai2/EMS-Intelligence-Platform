"""
EMS Facilities Scraper - Per-company configuration.
Each entry defines the official source URL and scraping strategy.
"""

SCRAPER_CONFIG = {
    "Flex": {
        "url": "https://flex.com/company/global-locations",
        "method": "selenium",
        "interaction": "click_regions",
        "parse_type": "interactive_map",
        "color": "#2563EB",
    },
    "Jabil": {
        "url": "https://www.jabil.com/about-us/global-locations.html",
        "method": "selenium",
        "interaction": "click_regions",
        "parse_type": "interactive_map",
        "color": "#16A34A",
    },
    "Sanmina": {
        "url": "https://www.sanmina.com/locations/",
        "method": "selenium",
        "interaction": "click_map_regions",
        "parse_type": "region_list",
        "color": "#DC2626",
    },
    "Celestica": {
        "url": "https://www.celestica.com/about-us/locations",
        "method": "requests",
        "interaction": None,
        "parse_type": "text_list",
        "color": "#7C3AED",
    },
    "Plexus": {
        "url": "https://www.plexus.com/about/locations/",
        "method": "selenium",
        "interaction": "scroll_load",
        "parse_type": "card_list",
        "color": "#D97706",
    },
    "Benchmark": {
        "url": "https://www.bench.com/worldwide-locations",
        "method": "requests",
        "interaction": None,
        "parse_type": "address_list",
        "color": "#0891B2",
    },
}
