"""
EMS Global Facilities Scraper v3.0
Scrapes facility data from all 6 EMS company official websites.
Uses Selenium for JS-rendered pages + LLM for structured extraction.
"""

import json
import time
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from backend.scraper.scraper_config import SCRAPER_CONFIG
from backend.core.config import BASE_DIR

OUTPUT_DIR = BASE_DIR / "data"
JSON_PATH = OUTPUT_DIR / "ems_facilities.json"
META_PATH = OUTPUT_DIR / "scrape_meta.json"

# --- Known coordinates for geocoding (avoids external API) ----------------
CITY_COORDS: dict[str, dict] = {
    # Americas - USA
    "austin": {"lat": 30.2672, "lng": -97.7431, "country": "United States", "region": "Americas"},
    "milpitas": {"lat": 37.4323, "lng": -121.8996, "country": "United States", "region": "Americas"},
    "san jose": {"lat": 37.3382, "lng": -121.8863, "country": "United States", "region": "Americas"},
    "fontana": {"lat": 34.0922, "lng": -117.4350, "country": "United States", "region": "Americas"},
    "buffalo grove": {"lat": 42.1663, "lng": -87.9631, "country": "United States", "region": "Americas"},
    "memphis": {"lat": 35.1495, "lng": -90.0490, "country": "United States", "region": "Americas"},
    "dallas": {"lat": 32.7767, "lng": -96.7970, "country": "United States", "region": "Americas"},
    "salt lake city": {"lat": 40.7608, "lng": -111.8910, "country": "United States", "region": "Americas"},
    "manchester": {"lat": 41.7760, "lng": -72.5218, "country": "United States", "region": "Americas"},
    "coopersville": {"lat": 43.0775, "lng": -85.9339, "country": "United States", "region": "Americas"},
    "farmington hills": {"lat": 42.4989, "lng": -83.3677, "country": "United States", "region": "Americas"},
    "northfield": {"lat": 44.4583, "lng": -93.1614, "country": "United States", "region": "Americas"},
    "hollis": {"lat": 42.7431, "lng": -71.5892, "country": "United States", "region": "Americas"},
    "nashua": {"lat": 42.7654, "lng": -71.4676, "country": "United States", "region": "Americas"},
    "orangeburg": {"lat": 33.4918, "lng": -80.8556, "country": "United States", "region": "Americas"},
    "west columbia": {"lat": 33.9935, "lng": -81.0740, "country": "United States", "region": "Americas"},
    "henrico": {"lat": 37.5388, "lng": -77.3653, "country": "United States", "region": "Americas"},
    "littleton": {"lat": 42.5334, "lng": -71.4570, "country": "United States", "region": "Americas"},
    "fremont": {"lat": 37.5485, "lng": -121.9886, "country": "United States", "region": "Americas"},
    "portland": {"lat": 45.5051, "lng": -122.6750, "country": "United States", "region": "Americas"},
    "tempe": {"lat": 33.4255, "lng": -111.9400, "country": "United States", "region": "Americas"},
    "rochester": {"lat": 44.0234, "lng": -92.4630, "country": "United States", "region": "Americas"},
    "angleton": {"lat": 29.1694, "lng": -95.4316, "country": "United States", "region": "Americas"},
    "st. petersburg": {"lat": 27.7676, "lng": -82.6403, "country": "United States", "region": "Americas"},
    "albuquerque": {"lat": 35.0844, "lng": -106.6504, "country": "United States", "region": "Americas"},
    "anaheim": {"lat": 33.8366, "lng": -117.9143, "country": "United States", "region": "Americas"},
    "asheville": {"lat": 35.5951, "lng": -82.5515, "country": "United States", "region": "Americas"},
    "auburn hills": {"lat": 42.6875, "lng": -83.2341, "country": "United States", "region": "Americas"},
    "atlanta": {"lat": 33.7490, "lng": -84.3880, "country": "United States", "region": "Americas"},
    "brandywine": {"lat": 39.8685, "lng": -75.5460, "country": "United States", "region": "Americas"},
    "burlington": {"lat": 42.5048, "lng": -71.1962, "country": "United States", "region": "Americas"},
    "clearwater": {"lat": 27.9659, "lng": -82.8001, "country": "United States", "region": "Americas"},
    "clinton": {"lat": 42.4168, "lng": -71.6828, "country": "United States", "region": "Americas"},
    "devens": {"lat": 42.5457, "lng": -71.6123, "country": "United States", "region": "Americas"},
    "elmira": {"lat": 42.0898, "lng": -76.8077, "country": "United States", "region": "Americas"},
    "claremont": {"lat": 43.3767, "lng": -72.3468, "country": "United States", "region": "Americas"},
    "neenah": {"lat": 44.1858, "lng": -88.4626, "country": "United States", "region": "Americas"},
    "appleton": {"lat": 44.2619, "lng": -88.4154, "country": "United States", "region": "Americas"},
    "nampa": {"lat": 43.5407, "lng": -116.5635, "country": "United States", "region": "Americas"},
    "boise": {"lat": 43.6150, "lng": -116.2023, "country": "United States", "region": "Americas"},
    "raleigh": {"lat": 35.7796, "lng": -78.6382, "country": "United States", "region": "Americas"},
    "chicago": {"lat": 41.8781, "lng": -87.6298, "country": "United States", "region": "Americas"},
    "carrollton": {"lat": 32.9537, "lng": -96.8903, "country": "United States", "region": "Americas"},
    "costa mesa": {"lat": 33.6412, "lng": -117.9187, "country": "United States", "region": "Americas"},
    "el paso": {"lat": 31.7619, "lng": -106.4850, "country": "United States", "region": "Americas"},
    "huntsville": {"lat": 34.7304, "lng": -86.5861, "country": "United States", "region": "Americas"},
    "kenosha": {"lat": 42.5847, "lng": -87.8212, "country": "United States", "region": "Americas"},
    "newark": {"lat": 37.5297, "lng": -122.0402, "country": "United States", "region": "Americas"},
    "turtle lake": {"lat": 45.3944, "lng": -92.1413, "country": "United States", "region": "Americas"},
    "arden hills": {"lat": 45.0505, "lng": -93.1577, "country": "United States", "region": "Americas"},
    "concord": {"lat": 37.9780, "lng": -122.0311, "country": "United States", "region": "Americas"},
    "mesa": {"lat": 33.4152, "lng": -111.8315, "country": "United States", "region": "Americas"},
    "phoenix": {"lat": 33.4484, "lng": -112.0740, "country": "United States", "region": "Americas"},
    "santa ana": {"lat": 33.7455, "lng": -117.8677, "country": "United States", "region": "Americas"},
    "winona": {"lat": 44.0500, "lng": -91.6393, "country": "United States", "region": "Americas"},
    # Americas - Canada
    "ottawa": {"lat": 45.4215, "lng": -75.6972, "country": "Canada", "region": "Americas"},
    # Americas - Mexico
    "guadalajara": {"lat": 20.6597, "lng": -103.3496, "country": "Mexico", "region": "Americas"},
    "tijuana": {"lat": 32.5149, "lng": -117.0382, "country": "Mexico", "region": "Americas"},
    "juarez": {"lat": 31.6904, "lng": -106.4245, "country": "Mexico", "region": "Americas"},
    "aguascalientes": {"lat": 21.8853, "lng": -102.2916, "country": "Mexico", "region": "Americas"},
    "reynosa": {"lat": 26.0508, "lng": -98.2279, "country": "Mexico", "region": "Americas"},
    "san luis": {"lat": 32.4543, "lng": -114.7220, "country": "Mexico", "region": "Americas"},
    "chihuahua": {"lat": 28.6353, "lng": -106.0889, "country": "Mexico", "region": "Americas"},
    "monterrey": {"lat": 25.6866, "lng": -100.3161, "country": "Mexico", "region": "Americas"},
    # Americas - Brazil
    "sorocaba": {"lat": -23.5015, "lng": -47.4526, "country": "Brazil", "region": "Americas"},
    "manaus": {"lat": -3.1190, "lng": -60.0217, "country": "Brazil", "region": "Americas"},
    "jaguariuna": {"lat": -22.7036, "lng": -46.9856, "country": "Brazil", "region": "Americas"},
    "belo horizonte": {"lat": -19.9191, "lng": -43.9386, "country": "Brazil", "region": "Americas"},
    # Americas - Other
    "alajuela": {"lat": 10.0167, "lng": -84.2167, "country": "Costa Rica", "region": "Americas"},
    "cayey": {"lat": 18.1119, "lng": -66.1660, "country": "Puerto Rico", "region": "Americas"},
    "vaughan": {"lat": 43.8361, "lng": -79.4983, "country": "Canada", "region": "Americas"},
    "toronto": {"lat": 43.6532, "lng": -79.3832, "country": "Canada", "region": "Americas"},
    # Europe
    "timisoara": {"lat": 45.7489, "lng": 21.2087, "country": "Romania", "region": "Europe"},
    "oradea": {"lat": 47.0458, "lng": 21.9189, "country": "Romania", "region": "Europe"},
    "tczew": {"lat": 54.0924, "lng": 18.7779, "country": "Poland", "region": "Europe"},
    "budapest": {"lat": 47.4979, "lng": 19.0402, "country": "Hungary", "region": "Europe"},
    "amsterdam": {"lat": 52.3676, "lng": 4.9041, "country": "Netherlands", "region": "Europe"},
    "valencia": {"lat": 39.4699, "lng": -0.3763, "country": "Spain", "region": "Europe"},
    "livingston": {"lat": 55.9024, "lng": -3.5159, "country": "United Kingdom", "region": "Europe"},
    "althofen": {"lat": 46.8744, "lng": 14.4639, "country": "Austria", "region": "Europe"},
    "vienna": {"lat": 48.2082, "lng": 16.3738, "country": "Austria", "region": "Europe"},
    "pardubice": {"lat": 50.0343, "lng": 15.7812, "country": "Czech Republic", "region": "Europe"},
    "sonderborg": {"lat": 54.9131, "lng": 9.7930, "country": "Denmark", "region": "Europe"},
    "stuttgart": {"lat": 48.7758, "lng": 9.1829, "country": "Germany", "region": "Europe"},
    "filderstadt": {"lat": 48.6602, "lng": 9.2250, "country": "Germany", "region": "Europe"},
    "nyiregyhaza": {"lat": 47.9553, "lng": 21.7173, "country": "Hungary", "region": "Europe"},
    "sarvar": {"lat": 47.2540, "lng": 16.9340, "country": "Hungary", "region": "Europe"},
    "tab": {"lat": 46.7314, "lng": 18.0305, "country": "Hungary", "region": "Europe"},
    "ullo": {"lat": 47.3852, "lng": 19.1848, "country": "Hungary", "region": "Europe"},
    "zalaegerszeg": {"lat": 46.8417, "lng": 16.8416, "country": "Hungary", "region": "Europe"},
    "gyal": {"lat": 47.3853, "lng": 19.2177, "country": "Hungary", "region": "Europe"},
    "cork": {"lat": 51.8969, "lng": -8.4863, "country": "Ireland", "region": "Europe"},
    "dundalk": {"lat": 54.0037, "lng": -6.4025, "country": "Ireland", "region": "Europe"},
    "limerick": {"lat": 52.6638, "lng": -8.6267, "country": "Ireland", "region": "Europe"},
    "manorhamilton": {"lat": 54.3052, "lng": -8.1792, "country": "Ireland", "region": "Europe"},
    "migdal haemek": {"lat": 32.6713, "lng": 35.2414, "country": "Israel", "region": "Europe"},
    "modiin": {"lat": 31.8982, "lng": 34.9681, "country": "Israel", "region": "Europe"},
    "ofakim": {"lat": 31.3156, "lng": 34.6154, "country": "Israel", "region": "Europe"},
    "milan": {"lat": 45.4642, "lng": 9.1900, "country": "Italy", "region": "Europe"},
    "somaglia": {"lat": 45.1500, "lng": 9.6300, "country": "Italy", "region": "Europe"},
    "hoogeveen": {"lat": 52.7236, "lng": 6.4764, "country": "Netherlands", "region": "Europe"},
    "venray": {"lat": 51.5262, "lng": 5.9730, "country": "Netherlands", "region": "Europe"},
    "woerden": {"lat": 52.0886, "lng": 4.8848, "country": "Netherlands", "region": "Europe"},
    "bielsko-biala": {"lat": 49.8224, "lng": 19.0441, "country": "Poland", "region": "Europe"},
    "lodz": {"lat": 51.7592, "lng": 19.4560, "country": "Poland", "region": "Europe"},
    "pamplona": {"lat": 42.8125, "lng": -1.6458, "country": "Spain", "region": "Europe"},
    "kalmar": {"lat": 56.6634, "lng": 16.3567, "country": "Sweden", "region": "Europe"},
    "hagglingen": {"lat": 47.3879, "lng": 8.2512, "country": "Switzerland", "region": "Europe"},
    "kussnacht": {"lat": 47.0857, "lng": 8.4411, "country": "Switzerland", "region": "Europe"},
    "warrington": {"lat": 53.3900, "lng": -2.5970, "country": "United Kingdom", "region": "Europe"},
    "cumbria": {"lat": 54.3280, "lng": -2.7471, "country": "United Kingdom", "region": "Europe"},
    "kendal": {"lat": 54.3280, "lng": -2.7471, "country": "United Kingdom", "region": "Europe"},
    "mukachevo": {"lat": 48.4414, "lng": 22.7177, "country": "Ukraine", "region": "Europe"},
    "kelso": {"lat": 55.5969, "lng": -2.4341, "country": "United Kingdom", "region": "Europe"},
    "bray": {"lat": 53.2034, "lng": -6.0986, "country": "Ireland", "region": "Europe"},
    "dublin": {"lat": 53.3498, "lng": -6.2603, "country": "Ireland", "region": "Europe"},
    "coatbridge": {"lat": 55.8622, "lng": -4.0277, "country": "United Kingdom", "region": "Europe"},
    "jena": {"lat": 50.9271, "lng": 11.5892, "country": "Germany", "region": "Europe"},
    "kharkiv": {"lat": 49.9935, "lng": 36.2304, "country": "Ukraine", "region": "Europe"},
    "kwidzyn": {"lat": 53.7340, "lng": 18.9309, "country": "Poland", "region": "Europe"},
    "hasselt": {"lat": 50.9307, "lng": 5.3375, "country": "Belgium", "region": "Europe"},
    "balsthal": {"lat": 47.3156, "lng": 7.6933, "country": "Switzerland", "region": "Europe"},
    "bettlach": {"lat": 47.2031, "lng": 7.4261, "country": "Switzerland", "region": "Europe"},
    "grenchen": {"lat": 47.1925, "lng": 7.3964, "country": "Switzerland", "region": "Europe"},
    "hagendorf": {"lat": 47.3838, "lng": 7.7625, "country": "Switzerland", "region": "Europe"},
    "le locle": {"lat": 47.0552, "lng": 6.7513, "country": "Switzerland", "region": "Europe"},
    "bar-lev": {"lat": 32.9250, "lng": 35.2817, "country": "Israel", "region": "Europe"},
    "kecskemet": {"lat": 46.8963, "lng": 19.6897, "country": "Hungary", "region": "Europe"},
    "tatabanya": {"lat": 47.5690, "lng": 18.3948, "country": "Hungary", "region": "Europe"},
    "tatabánya": {"lat": 47.5690, "lng": 18.3948, "country": "Hungary", "region": "Europe"},
    "plovdiv": {"lat": 42.6977, "lng": 24.7453, "country": "Bulgaria", "region": "Europe"},
    "haukipudas": {"lat": 65.1764, "lng": 25.3540, "country": "Finland", "region": "Europe"},
    "gunzenhausen": {"lat": 49.1157, "lng": 10.7534, "country": "Germany", "region": "Europe"},
    "fermoy": {"lat": 52.1374, "lng": -8.2742, "country": "Ireland", "region": "Europe"},
    "ornskoldsvik": {"lat": 63.2909, "lng": 18.7152, "country": "Sweden", "region": "Europe"},
    "örnsköldsvik": {"lat": 63.2909, "lng": 18.7152, "country": "Sweden", "region": "Europe"},
    "basingstoke": {"lat": 51.2667, "lng": -1.0876, "country": "United Kingdom", "region": "Europe"},
    "port glasgow": {"lat": 55.9345, "lng": -4.6893, "country": "United Kingdom", "region": "Europe"},
    "almelo": {"lat": 52.3570, "lng": 6.6628, "country": "Netherlands", "region": "Europe"},
    "brasov": {"lat": 45.6427, "lng": 25.5887, "country": "Romania", "region": "Europe"},
    "ma'alot": {"lat": 33.0161, "lng": 35.2727, "country": "Israel", "region": "Europe"},
    "maalot": {"lat": 33.0161, "lng": 35.2727, "country": "Israel", "region": "Europe"},
    # Africa
    "johannesburg": {"lat": -26.2041, "lng": 28.0473, "country": "South Africa", "region": "Europe"},
    # Asia
    "shanghai": {"lat": 31.2304, "lng": 121.4737, "country": "China", "region": "Asia"},
    "shenzhen": {"lat": 22.5431, "lng": 114.0579, "country": "China", "region": "Asia"},
    "zhuhai": {"lat": 22.2769, "lng": 113.5678, "country": "China", "region": "Asia"},
    "suzhou": {"lat": 31.2989, "lng": 120.5853, "country": "China", "region": "Asia"},
    "wuxi": {"lat": 31.4912, "lng": 120.3119, "country": "China", "region": "Asia"},
    "kunshan": {"lat": 31.3847, "lng": 120.9837, "country": "China", "region": "Asia"},
    "changsha": {"lat": 28.2282, "lng": 112.9388, "country": "China", "region": "Asia"},
    "dongguan": {"lat": 23.0208, "lng": 113.7518, "country": "China", "region": "Asia"},
    "nanjing": {"lat": 32.0603, "lng": 118.7969, "country": "China", "region": "Asia"},
    "hong kong": {"lat": 22.3193, "lng": 114.1694, "country": "China", "region": "Asia"},
    "xiamen": {"lat": 24.4798, "lng": 118.0894, "country": "China", "region": "Asia"},
    "guangzhou": {"lat": 23.1291, "lng": 113.2644, "country": "China", "region": "Asia"},
    "huangpu": {"lat": 23.1066, "lng": 113.4543, "country": "China", "region": "Asia"},
    "beijing": {"lat": 39.9042, "lng": 116.4074, "country": "China", "region": "Asia"},
    "taipei": {"lat": 25.0330, "lng": 121.5654, "country": "Taiwan", "region": "Asia"},
    "taoyuan": {"lat": 24.9937, "lng": 121.3010, "country": "Taiwan", "region": "Asia"},
    "changhua": {"lat": 24.0518, "lng": 120.5161, "country": "Taiwan", "region": "Asia"},
    "hsinchu": {"lat": 24.8015, "lng": 120.9718, "country": "Taiwan", "region": "Asia"},
    "penang": {"lat": 5.4141, "lng": 100.3288, "country": "Malaysia", "region": "Asia"},
    "kulim": {"lat": 5.3717, "lng": 100.5627, "country": "Malaysia", "region": "Asia"},
    "johor": {"lat": 1.4927, "lng": 103.7414, "country": "Malaysia", "region": "Asia"},
    "batu kawan": {"lat": 5.2551, "lng": 100.4285, "country": "Malaysia", "region": "Asia"},
    "chuping": {"lat": 6.5110, "lng": 100.1990, "country": "Malaysia", "region": "Asia"},
    "selangor": {"lat": 3.0738, "lng": 101.5183, "country": "Malaysia", "region": "Asia"},
    "shah alam": {"lat": 3.0738, "lng": 101.5183, "country": "Malaysia", "region": "Asia"},
    "chennai": {"lat": 13.0827, "lng": 80.2707, "country": "India", "region": "Asia"},
    "bangalore": {"lat": 12.9716, "lng": 77.5946, "country": "India", "region": "Asia"},
    "bengaluru": {"lat": 12.9716, "lng": 77.5946, "country": "India", "region": "Asia"},
    "pune": {"lat": 18.5204, "lng": 73.8567, "country": "India", "region": "Asia"},
    "coimbatore": {"lat": 11.0168, "lng": 76.9558, "country": "India", "region": "Asia"},
    "sriperumbudur": {"lat": 12.9676, "lng": 79.9416, "country": "India", "region": "Asia"},
    "wallajabad": {"lat": 12.8000, "lng": 79.7167, "country": "India", "region": "Asia"},
    "singapore": {"lat": 1.3521, "lng": 103.8198, "country": "Singapore", "region": "Asia"},
    "batam": {"lat": 1.0456, "lng": 104.0305, "country": "Indonesia", "region": "Asia"},
    "bandung": {"lat": -6.9175, "lng": 107.6191, "country": "Indonesia", "region": "Asia"},
    "ibaraki": {"lat": 36.3418, "lng": 140.4468, "country": "Japan", "region": "Asia"},
    "gotemba": {"lat": 35.3089, "lng": 138.9286, "country": "Japan", "region": "Asia"},
    "hachioji": {"lat": 35.6565, "lng": 139.3239, "country": "Japan", "region": "Asia"},
    "cebu": {"lat": 10.3157, "lng": 123.8854, "country": "Philippines", "region": "Asia"},
    "ho chi minh city": {"lat": 10.8231, "lng": 106.6297, "country": "Vietnam", "region": "Asia"},
    "bangkok": {"lat": 13.7563, "lng": 100.5018, "country": "Thailand", "region": "Asia"},
    "ayutthaya": {"lat": 14.3532, "lng": 100.5689, "country": "Thailand", "region": "Asia"},
    "korat": {"lat": 14.9799, "lng": 102.0978, "country": "Thailand", "region": "Asia"},
    "pathum thani": {"lat": 14.0208, "lng": 100.5253, "country": "Thailand", "region": "Asia"},
    "haining": {"lat": 30.5097, "lng": 120.6815, "country": "China", "region": "Asia"},
    "yasu": {"lat": 35.0678, "lng": 136.0247, "country": "Japan", "region": "Asia"},
    "chai chee": {"lat": 1.3370, "lng": 103.9400, "country": "Singapore", "region": "Asia"},
    "penjuru": {"lat": 1.3030, "lng": 103.7450, "country": "Singapore", "region": "Asia"},
}


def _make_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(options=options)


def _lookup_city(city_name: str) -> tuple[str | None, dict | None]:
    """Look up coordinates for a city name (case-insensitive).
    Returns (canonical_key, coords_dict) or (None, None).
    Only matches exact keys or the first word before punctuation."""
    key = city_name.lower().strip()
    if key in CITY_COORDS:
        return key, CITY_COORDS[key]
    # Try first token before comma/parenthesis (e.g. "Penang (Plant 1)" -> "penang")
    first = key.split(",")[0].split("(")[0].split("—")[0].strip()
    if first in CITY_COORDS:
        return first, CITY_COORDS[first]
    # Two-word city names (e.g. "San Jose, CA" -> "san jose")
    two_words = " ".join(first.split()[:2])
    if two_words in CITY_COORDS and len(two_words) > 4:
        return two_words, CITY_COORDS[two_words]
    three_words = " ".join(first.split()[:3])
    if three_words in CITY_COORDS:
        return three_words, CITY_COORDS[three_words]
    return None, None


def _extract_facilities_from_text(raw_text: str, company: str, source_url: str, region_hint: str = "") -> list[dict]:
    """
    Parse raw page text into facility records.
    Strategy: look for lines that ARE a city name (short lines), not lines that
    merely contain a city name buried in other text.
    """
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    facilities = []
    seen_cities: set[str] = set()  # canonical city keys already added
    now = datetime.now(timezone.utc).isoformat()
    color = SCRAPER_CONFIG.get(company, {}).get("color", "#64748B")

    # Skip navigation / footer / boilerplate lines
    skip_markers = [
        "INDUSTRIES", "PRODUCTS", "SERVICES", "NEWS", "COMPANY", "INVESTORS",
        "CAREERS", "STAY CONNECTED", "Subscribe", "Home", "Supplier",
        "Privacy", "Trademarks", "All rights reserved", "cookies",
        "CONTACT SALES", "SUPPLIER PORTAL", "CUSTOMER PORTAL", "SITEMAP",
        "INTEGRITY HOTLINE", "TERMS OF USE", "GLOBAL ENTITIES", "©",
        "LOGIN", "SEARCH", "MENU", "FOLLOW US", "GET IN TOUCH",
        "View careers", "JOBS IN", "Join the", "View website",
        "Learn more", "Read more", "Download", "Watch video",
    ]

    for i, line in enumerate(lines):
        # Skip long lines (addresses with zip codes are OK at ~60 chars, nav text is longer)
        if len(line) > 80:
            continue
        # Skip obvious non-location lines
        if any(m.lower() in line.lower() for m in skip_markers):
            continue
        # Skip lines that are just numbers, dates, or very short
        if len(line) < 3 or line.replace(" ", "").isdigit():
            continue

        # Try to match this line as a city
        canonical, coords = _lookup_city(line)
        if not coords:
            # Try cleaning: "Austin, Texas" -> "austin", "Penang – Plant 3" -> "penang"
            cleaned = line.split("–")[0].split("-")[0].strip()
            canonical, coords = _lookup_city(cleaned)

        if coords and canonical:
            # Deduplicate by canonical city name (same company + same city = skip)
            dedup_key = f"{company}|{canonical}"
            if dedup_key in seen_cities:
                continue
            seen_cities.add(dedup_key)

            # Determine facility type from surrounding context
            context = " ".join(lines[max(0, i - 2):min(len(lines), i + 4)]).lower()
            if "headquarter" in context or "corporate office" in context:
                ftype = "Headquarters"
            elif "design" in context or "r&d" in context or "innovation" in context:
                ftype = "Design Center"
            elif "warehouse" in context or "logistics" in context or "distribution" in context:
                ftype = "Logistics/Repair"
            else:
                ftype = "Manufacturing"

            # Display name: use canonical key, title-cased
            display_city = canonical.title()
            region = region_hint or coords.get("region", "")

            facilities.append({
                "id": f"{company.lower()}_{canonical.replace(' ', '_')}",
                "company": company,
                "company_color": color,
                "city": display_city,
                "state_province": "",
                "country": coords["country"],
                "region": region,
                "subregion": "",
                "latitude": coords["lat"],
                "longitude": coords["lng"],
                "facility_type": [ftype],
                "capabilities": [],
                "source_url": source_url,
                "source_page_title": f"Global Locations | {company}",
                "scraped_at": now,
                "notes": "",
            })

    return facilities


# --- Per-company scrapers -------------------------------------------------

def scrape_flex() -> list[dict]:
    """Flex: click Americas/EMEA/Asia tabs, extract text from each."""
    source_url = SCRAPER_CONFIG["Flex"]["url"]
    all_facilities = []
    driver = _make_driver()

    try:
        driver.get(source_url)
        time.sleep(5)

        tabs = driver.find_elements(By.CSS_SELECTOR, "div.tab")
        region_tabs = [t for t in tabs if t.text.strip() in ("Americas", "EMEA", "Asia")]

        region_map = {"Americas": "Americas", "EMEA": "Europe", "Asia": "Asia"}

        for tab in region_tabs:
            region_name = tab.text.strip()
            print(f"  [Flex] Clicking tab: {region_name}")
            driver.execute_script("arguments[0].click();", tab)
            time.sleep(3)

            body_text = driver.find_element(By.TAG_NAME, "body").text
            facilities = _extract_facilities_from_text(
                body_text, "Flex", source_url,
                region_hint=region_map.get(region_name, ""),
            )
            all_facilities.extend(facilities)
            print(f"  [Flex] {region_name}: {len(facilities)} facilities found")

    finally:
        driver.quit()

    return all_facilities


def scrape_jabil() -> list[dict]:
    """Jabil: navigate to each regional subpage (americas, asia, europe)."""
    base_url = SCRAPER_CONFIG["Jabil"]["url"]
    subpages = [
        ("https://www.jabil.com/about-us/global-locations/americas.html", "Americas"),
        ("https://www.jabil.com/about-us/global-locations/asia.html", "Asia"),
        ("https://www.jabil.com/about-us/global-locations/europe-and-middle-east.html", "Europe"),
    ]
    all_facilities = []
    driver = _make_driver()

    try:
        for url, region in subpages:
            print(f"  [Jabil] Loading: {region}")
            driver.get(url)
            time.sleep(4)

            body_text = driver.find_element(By.TAG_NAME, "body").text
            facilities = _extract_facilities_from_text(
                body_text, "Jabil", base_url, region_hint=region,
            )
            all_facilities.extend(facilities)
            print(f"  [Jabil] {region}: {len(facilities)} facilities found")

    finally:
        driver.quit()

    return all_facilities


def scrape_sanmina() -> list[dict]:
    """Sanmina: interactive map - click activateLargeMap(1..7) sequentially to reveal all regions."""
    source_url = SCRAPER_CONFIG["Sanmina"]["url"]
    driver = _make_driver()
    all_facilities: list[dict] = []

    try:
        driver.get(source_url)
        time.sleep(5)

        # Must click all map regions in sequence (each adds a region cumulatively)
        for map_id in [1, 3, 4, 5, 6, 7]:
            driver.execute_script(f"activateLargeMap({map_id})")
            time.sleep(2)

        # Now extract the full cumulative location list
        body_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
        start = None
        end = None
        for i, line in enumerate(lines):
            if line == "LOCATIONS":
                start = i + 1
            if start and "Search plants" in line:
                end = i
                break
        if start and end:
            location_text = "\n".join(lines[start:end])
        else:
            location_text = body_text

        all_facilities = _extract_facilities_from_text(
            location_text, "Sanmina", source_url,
        )
        print(f"  [Sanmina] Map regions: {len(all_facilities)} facilities found")

    finally:
        driver.quit()

    return all_facilities


def scrape_generic_selenium(company: str) -> list[dict]:
    """Generic: load the page, extract text for facility matching."""
    config = SCRAPER_CONFIG[company]
    source_url = config["url"]
    driver = _make_driver()

    try:
        driver.get(source_url)
        time.sleep(5)

        body_text = driver.find_element(By.TAG_NAME, "body").text
        facilities = _extract_facilities_from_text(
            body_text, company, source_url,
        )
        print(f"  [{company}] Page: {len(facilities)} facilities found")

    finally:
        driver.quit()

    return facilities


# --- Shared locations post-processing ------------------------------------

def compute_shared_locations(facilities: list[dict]) -> list[dict]:
    city_companies: dict[str, set[str]] = defaultdict(set)
    for f in facilities:
        key = f"{f['city'].lower()}_{f['country'].lower()}"
        city_companies[key].add(f["company"])

    for f in facilities:
        key = f"{f['city'].lower()}_{f['country'].lower()}"
        companies_in_city = city_companies[key]
        f["is_shared_location"] = len(companies_in_city) > 1
        f["shared_with"] = sorted(c for c in companies_in_city if c != f["company"])

    return facilities


# --- Main flow ------------------------------------------------------------

def run_full_scrape() -> dict:
    print("=" * 60)
    print("EMS Facilities Scraper v3.0")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_facilities: list[dict] = []
    scrape_errors: dict[str, str] = {}

    scrapers = {
        "Flex": scrape_flex,
        "Jabil": scrape_jabil,
        "Sanmina": scrape_sanmina,
        "Celestica": lambda: scrape_generic_selenium("Celestica"),
        "Plexus": lambda: scrape_generic_selenium("Plexus"),
        "Benchmark": lambda: scrape_generic_selenium("Benchmark"),
    }

    for company, scraper_fn in scrapers.items():
        print(f"\n[{company}] Starting scrape...")
        try:
            results = scraper_fn()
            print(f"[{company}] Found {len(results)} facilities")
            all_facilities.extend(results)
        except Exception as e:
            msg = str(e)
            print(f"[{company}] Error: {msg}")
            scrape_errors[company] = msg

    # Deduplicate (same company + same city + same country)
    seen: set[str] = set()
    unique: list[dict] = []
    for f in all_facilities:
        key = f"{f['company']}|{f['city'].lower()}|{f['country'].lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(f)

    # Post-process: shared locations
    unique = compute_shared_locations(unique)

    # Save
    if unique:
        OUTPUT_DIR.mkdir(exist_ok=True)
        with open(JSON_PATH, "w", encoding="utf-8") as fp:
            json.dump(unique, fp, ensure_ascii=False, indent=2)

    meta = {
        "last_scraped": datetime.now(timezone.utc).isoformat(),
        "total_facilities": len(unique),
        "by_company": {
            company: len([f for f in unique if f["company"] == company])
            for company in SCRAPER_CONFIG.keys()
        },
        "shared_locations": len([f for f in unique if f.get("is_shared_location")]),
        "errors": scrape_errors,
        "data_sources": {
            company: cfg["url"] for company, cfg in SCRAPER_CONFIG.items()
        },
    }
    with open(META_PATH, "w", encoding="utf-8") as fp:
        json.dump(meta, fp, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Complete! {len(unique)} unique facilities saved.")
    for company in SCRAPER_CONFIG:
        count = meta["by_company"].get(company, 0)
        print(f"  {company}: {count}")
    print(f"  Shared locations: {meta['shared_locations']}")
    print(f"{'=' * 60}")

    return meta


async def run_full_scrape_async() -> dict:
    return await asyncio.to_thread(run_full_scrape)


def load_cached_facilities() -> list[dict]:
    if JSON_PATH.exists():
        with open(JSON_PATH, "r", encoding="utf-8") as fp:
            return json.load(fp)
    return []


def load_scrape_meta() -> dict:
    if META_PATH.exists():
        with open(META_PATH, "r", encoding="utf-8") as fp:
            return json.load(fp)
    return {}


if __name__ == "__main__":
    run_full_scrape()
