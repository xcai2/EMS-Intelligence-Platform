"""
Automatic facility extraction from SEC filings and company documents.
Extracts manufacturing locations, design centers, and headquarters from text.
"""
import re
import json
from pathlib import Path
from typing import Optional
from collections import defaultdict

from backend.rag.retriever import search_documents, get_company_documents
from backend.core.config import COMPANIES

# Known location patterns and their coordinates
LOCATION_COORDINATES = {
    # Americas
    "austin": {"country": "USA", "lat": 30.2672, "lng": -97.7431},
    "san jose": {"country": "USA", "lat": 37.3382, "lng": -121.8863},
    "fremont": {"country": "USA", "lat": 37.5485, "lng": -121.9886},
    "st. petersburg": {"country": "USA", "lat": 27.7676, "lng": -82.6403},
    "tempe": {"country": "USA", "lat": 33.4255, "lng": -111.9400},
    "rochester": {"country": "USA", "lat": 43.1566, "lng": -77.6088},
    "angleton": {"country": "USA", "lat": 29.1694, "lng": -95.4316},
    "portland": {"country": "USA", "lat": 45.5051, "lng": -122.6750},
    "huntsville": {"country": "USA", "lat": 34.7304, "lng": -86.5861},
    "memphis": {"country": "USA", "lat": 35.1495, "lng": -90.0490},
    "toronto": {"country": "Canada", "lat": 43.6532, "lng": -79.3832},
    "guadalajara": {"country": "Mexico", "lat": 20.6597, "lng": -103.3496},
    "monterrey": {"country": "Mexico", "lat": 25.6866, "lng": -100.3161},
    "chihuahua": {"country": "Mexico", "lat": 28.6353, "lng": -106.0889},
    "tijuana": {"country": "Mexico", "lat": 32.5149, "lng": -117.0382},
    "juarez": {"country": "Mexico", "lat": 31.6904, "lng": -106.4245},
    "sorocaba": {"country": "Brazil", "lat": -23.5015, "lng": -47.4526},
    "manaus": {"country": "Brazil", "lat": -3.1190, "lng": -60.0217},
    
    # APAC
    "singapore": {"country": "Singapore", "lat": 1.3521, "lng": 103.8198},
    "shanghai": {"country": "China", "lat": 31.2304, "lng": 121.4737},
    "shenzhen": {"country": "China", "lat": 22.5431, "lng": 114.0579},
    "suzhou": {"country": "China", "lat": 31.2989, "lng": 120.5853},
    "zhuhai": {"country": "China", "lat": 22.2769, "lng": 113.5678},
    "wuxi": {"country": "China", "lat": 31.4912, "lng": 120.3119},
    "kunshan": {"country": "China", "lat": 31.3847, "lng": 120.9837},
    "chengdu": {"country": "China", "lat": 30.5728, "lng": 104.0668},
    "guangzhou": {"country": "China", "lat": 23.1291, "lng": 113.2644},
    "penang": {"country": "Malaysia", "lat": 5.4141, "lng": 100.3288},
    "kulim": {"country": "Malaysia", "lat": 5.3717, "lng": 100.5627},
    "johor": {"country": "Malaysia", "lat": 1.4927, "lng": 103.7414},
    "chennai": {"country": "India", "lat": 13.0827, "lng": 80.2707},
    "bangalore": {"country": "India", "lat": 12.9716, "lng": 77.5946},
    "pune": {"country": "India", "lat": 18.5204, "lng": 73.8567},
    "tokyo": {"country": "Japan", "lat": 35.6762, "lng": 139.6503},
    "taipei": {"country": "Taiwan", "lat": 25.0330, "lng": 121.5654},
    "bangkok": {"country": "Thailand", "lat": 13.7563, "lng": 100.5018},
    
    # EMEA
    "livingston": {"country": "UK", "lat": 55.9024, "lng": -3.5159},
    "budapest": {"country": "Hungary", "lat": 47.4979, "lng": 19.0402},
    "kecskemet": {"country": "Hungary", "lat": 46.8963, "lng": 19.6897},
    "timisoara": {"country": "Romania", "lat": 45.7489, "lng": 21.2087},
    "oradea": {"country": "Romania", "lat": 47.0458, "lng": 21.9189},
    "amsterdam": {"country": "Netherlands", "lat": 52.3676, "lng": 4.9041},
    "valencia": {"country": "Spain", "lat": 39.4699, "lng": -0.3763},
    "cork": {"country": "Ireland", "lat": 51.8985, "lng": -8.4756},
    "munich": {"country": "Germany", "lat": 48.1351, "lng": 11.5820},
    "nuremberg": {"country": "Germany", "lat": 49.4521, "lng": 11.0767},
}

# Patterns to identify facility types
FACILITY_TYPE_PATTERNS = {
    "Manufacturing": [
        r"manufactur\w*",
        r"production\s+facilit\w*",
        r"assembly\s+plant",
        r"factory",
        r"plant",
    ],
    "Design Center": [
        r"design\s+center",
        r"engineering\s+center",
        r"r&d\s+center",
        r"research\s+and\s+development",
        r"innovation\s+center",
    ],
    "Headquarters": [
        r"headquarters",
        r"corporate\s+office",
        r"principal\s+executive\s+office",
        r"head\s+office",
    ],
    "Data Center": [
        r"data\s+center",
        r"cloud\s+infrastructure",
        r"server\s+facility",
    ],
    "Distribution": [
        r"distribution\s+center",
        r"logistics\s+center",
        r"warehouse",
    ],
}

# Cache for extracted facilities
_facility_cache = {}
_cache_file = Path(__file__).parent.parent.parent / "data" / "extracted_facilities.json"


def _load_cache():
    """Load cached facilities from file."""
    global _facility_cache
    if _cache_file.exists():
        try:
            with open(_cache_file, "r") as f:
                _facility_cache = json.load(f)
        except:
            _facility_cache = {}
    return _facility_cache


def _save_cache():
    """Save facilities cache to file."""
    _cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(_cache_file, "w") as f:
        json.dump(_facility_cache, f, indent=2)


def _identify_facility_type(context: str) -> str:
    """Identify the type of facility from surrounding context."""
    context_lower = context.lower()
    
    for facility_type, patterns in FACILITY_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, context_lower):
                return facility_type
    
    return "Manufacturing"  # Default


def _extract_locations_from_text(text: str) -> list[dict]:
    """Extract location mentions from text and match to known coordinates."""
    found_locations = []
    text_lower = text.lower()
    
    for city, coords in LOCATION_COORDINATES.items():
        # Look for city name with word boundaries
        pattern = r'\b' + re.escape(city) + r'\b'
        matches = list(re.finditer(pattern, text_lower))
        
        if matches:
            for match in matches:
                # Get surrounding context (100 chars before and after)
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                context = text[start:end]
                
                facility_type = _identify_facility_type(context)
                
                found_locations.append({
                    "city": city.title(),
                    "country": coords["country"],
                    "lat": coords["lat"],
                    "lng": coords["lng"],
                    "type": facility_type,
                    "context": context.strip(),
                    "confidence": 0.8 if "facility" in context.lower() or "plant" in context.lower() else 0.5,
                })
    
    return found_locations


def extract_facilities_from_documents(company: str, force_refresh: bool = False) -> dict:
    """
    Extract facility locations from company documents.
    Searches for location mentions in SEC filings, especially Properties sections.
    """
    _load_cache()
    
    # Check cache
    if not force_refresh and company in _facility_cache:
        cached = _facility_cache[company]
        if cached.get("facilities"):
            return cached
    
    # Search for properties/facilities sections
    property_docs = search_documents(
        query=f"{company} properties facilities manufacturing plants locations operations",
        company_filter=company,
        n_results=30,
    )
    
    # Also search for specific investment mentions
    investment_docs = search_documents(
        query=f"{company} facility expansion investment new plant construction",
        company_filter=company,
        n_results=20,
    )
    
    # Combine documents
    all_docs = property_docs + investment_docs
    
    # Extract locations from all documents
    location_mentions = defaultdict(lambda: {
        "count": 0,
        "types": [],
        "contexts": [],
        "confidence": 0,
    })
    
    for doc in all_docs:
        content = doc.get("content", "")
        locations = _extract_locations_from_text(content)
        
        for loc in locations:
            key = f"{loc['city']}_{loc['country']}"
            location_mentions[key]["city"] = loc["city"]
            location_mentions[key]["country"] = loc["country"]
            location_mentions[key]["lat"] = loc["lat"]
            location_mentions[key]["lng"] = loc["lng"]
            location_mentions[key]["count"] += 1
            location_mentions[key]["types"].append(loc["type"])
            location_mentions[key]["contexts"].append(loc["context"])
            location_mentions[key]["confidence"] = max(
                location_mentions[key]["confidence"],
                loc["confidence"]
            )
    
    # Process and deduplicate
    extracted_facilities = []
    for key, data in location_mentions.items():
        if data["count"] >= 1:  # At least 1 mention
            # Determine most common facility type
            type_counts = defaultdict(int)
            for t in data["types"]:
                type_counts[t] += 1
            primary_type = max(type_counts, key=type_counts.get) if type_counts else "Manufacturing"
            
            extracted_facilities.append({
                "city": data["city"],
                "country": data["country"],
                "lat": data["lat"],
                "lng": data["lng"],
                "type": primary_type,
                "mentions": data["count"],
                "confidence": round(min(data["confidence"] + (data["count"] * 0.1), 1.0), 2),
                "source": "extracted",
            })
    
    # Sort by confidence and mentions
    extracted_facilities.sort(key=lambda x: (x["confidence"], x["mentions"]), reverse=True)
    
    result = {
        "company": company,
        "facilities": extracted_facilities,
        "total_extracted": len(extracted_facilities),
        "documents_analyzed": len(all_docs),
    }
    
    # Cache result
    _facility_cache[company] = result
    _save_cache()
    
    return result


def get_combined_facilities(company: str) -> dict:
    """
    Get facilities combining hardcoded known facilities with extracted ones.
    Deduplicates based on city name.
    """
    from backend.analytics.geographic import KNOWN_FACILITIES
    
    # Get hardcoded facilities
    known = KNOWN_FACILITIES.get(company, {})
    known_facilities = []
    
    if known:
        # Add headquarters
        hq = known.get("headquarters")
        if hq:
            known_facilities.append({
                "city": hq["city"],
                "country": hq["country"],
                "lat": hq["lat"],
                "lng": hq["lng"],
                "type": "Headquarters",
                "website": hq.get("website"),
                "source": "known",
                "confidence": 1.0,
            })
        
        # Add known facilities
        for f in known.get("facilities", []):
            known_facilities.append({
                "city": f["city"],
                "country": f["country"],
                "lat": f["lat"],
                "lng": f["lng"],
                "type": f["type"],
                "website": f.get("website"),
                "source": "known",
                "confidence": 1.0,
            })
    
    # Get extracted facilities
    extracted = extract_facilities_from_documents(company)
    extracted_facilities = extracted.get("facilities", [])
    
    # Combine and deduplicate (prefer known over extracted)
    known_cities = {f["city"].lower() for f in known_facilities}
    
    combined = known_facilities.copy()
    new_discoveries = []
    
    for f in extracted_facilities:
        if f["city"].lower() not in known_cities and f["confidence"] >= 0.6:
            combined.append(f)
            new_discoveries.append(f)
    
    return {
        "company": company,
        "facilities": combined,
        "total_facilities": len(combined),
        "known_count": len(known_facilities),
        "extracted_count": len(extracted_facilities),
        "new_discoveries": new_discoveries,
        "documents_analyzed": extracted.get("documents_analyzed", 0),
    }


def extract_all_companies() -> dict:
    """Extract facilities for all tracked companies."""
    results = {}
    
    for ticker, config in COMPANIES.items():
        company_name = config["name"].split()[0]  # First word of company name
        results[company_name] = get_combined_facilities(company_name)
    
    return results


def get_new_facility_discoveries() -> list:
    """Get list of newly discovered facilities not in hardcoded data."""
    all_discoveries = []
    
    for ticker, config in COMPANIES.items():
        company_name = config["name"].split()[0]
        result = get_combined_facilities(company_name)
        
        for facility in result.get("new_discoveries", []):
            facility["company"] = company_name
            all_discoveries.append(facility)
    
    return all_discoveries
