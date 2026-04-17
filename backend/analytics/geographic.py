"""
Geographic analysis for EMS company facilities.
Loads facility data from data/ems_facilities.json (populated by the scraper).
Provides facility mapping, regional distribution, and competitive overlap analysis.
"""
from collections import defaultdict

from backend.core.config import TRACKED_COMPANY_NAMES, BASE_DIR
from backend.rag.retriever import search_documents
from backend.scraper.ems_scraper import load_cached_facilities, load_scrape_meta

# --- Region mapping -------------------------------------------------------
_REGION_COUNTRIES = {
    "Americas": [
        "United States", "USA", "Canada", "Mexico", "Brazil",
    ],
    "EMEA": [
        "United Kingdom", "UK", "Hungary", "Romania", "Netherlands",
        "Spain", "Germany", "Poland", "Ireland",
    ],
    "APAC": [
        "China", "Malaysia", "Singapore", "India", "Japan",
        "Taiwan", "Thailand", "Vietnam", "Philippines", "Indonesia",
    ],
}

_COUNTRY_TO_REGION: dict[str, str] = {}
for _region, _countries in _REGION_COUNTRIES.items():
    for _c in _countries:
        _COUNTRY_TO_REGION[_c] = _region


def _market_region(country: str) -> str:
    return _COUNTRY_TO_REGION.get(country, "Other")


# --- Data loading ---------------------------------------------------------

def _load_all() -> list[dict]:
    """Load all facilities from the JSON cache file."""
    return load_cached_facilities()


# --- Public API -----------------------------------------------------------

def get_company_facilities(company: str, include_extracted: bool = True) -> dict:
    """Get facility information for a company from the cached JSON data."""
    all_data = _load_all()
    company_facilities = [f for f in all_data if f["company"] == company]

    if not company_facilities:
        return {"company": company, "error": "Company not found"}

    hq = None
    facilities = []
    for f in company_facilities:
        entry = {
            "city": f["city"],
            "country": f["country"],
            "lat": f.get("latitude"),
            "lng": f.get("longitude"),
            "type": f["facility_type"][0] if f.get("facility_type") else "Manufacturing",
            "source": "scraped",
            "confidence": 1.0,
            "source_url": f.get("source_url", ""),
        }
        if "Headquarters" in (f.get("facility_type") or []):
            hq = entry
        else:
            facilities.append(entry)

    return {
        "company": company,
        "headquarters": hq,
        "facilities": facilities,
        "total_facilities": len(company_facilities),
        "data_source": "ems_facilities.json",
    }


def get_regional_distribution(company: str) -> dict:
    """Get regional distribution of facilities."""
    company_data = get_company_facilities(company)

    if "error" in company_data:
        return {"company": company, "error": "Company not found"}

    distribution = {"Americas": 0, "EMEA": 0, "APAC": 0}

    hq = company_data.get("headquarters")
    if hq:
        region = _market_region(hq.get("country", ""))
        if region in distribution:
            distribution[region] += 1

    for facility in company_data.get("facilities", []):
        region = _market_region(facility.get("country", ""))
        if region in distribution:
            distribution[region] += 1

    total = sum(distribution.values())
    percentages = {
        k: round(v / total * 100, 1) if total > 0 else 0
        for k, v in distribution.items()
    }

    return {
        "company": company,
        "distribution": distribution,
        "percentages": percentages,
        "primary_region": max(distribution, key=distribution.get) if total > 0 else None,
    }


def get_all_facilities_map(include_extracted: bool = True) -> dict:
    """Get all facilities for map visualization from the cached JSON."""
    all_data = _load_all()
    meta = load_scrape_meta()

    facilities_out = []
    by_company: dict[str, int] = defaultdict(int)

    for f in all_data:
        company = f["company"]
        facility_types = f.get("facility_type") or ["Manufacturing"]
        is_hq = "Headquarters" in facility_types

        facilities_out.append({
            "company": company,
            "city": f["city"],
            "country": f["country"],
            "lat": f.get("latitude"),
            "lng": f.get("longitude"),
            "type": facility_types[0],
            "facility_type": facility_types,
            "is_headquarters": is_hq,
            "source": "scraped",
            "confidence": 1.0,
            "source_url": f.get("source_url", ""),
            "source_page_title": f.get("source_page_title", ""),
            "capabilities": f.get("capabilities", []),
            "region": f.get("region", _market_region(f.get("country", ""))),
            "subregion": f.get("subregion", ""),
            "is_shared_location": f.get("is_shared_location", False),
            "shared_with": f.get("shared_with", []),
        })
        by_company[company] += 1

    return {
        "facilities": facilities_out,
        "total_count": len(facilities_out),
        "by_company": dict(by_company),
        "last_scraped": meta.get("last_scraped"),
        "data_sources": meta.get("data_sources", {}),
    }


def analyze_regional_investments(company: str) -> dict:
    """Analyze regional investment mentions in company filings."""
    regions_to_search = [
        "Americas", "Asia", "Europe", "Mexico", "China", "Malaysia", "India",
    ]

    regional_mentions = {}

    for region in regions_to_search:
        docs = search_documents(
            query=f"{company} {region} investment expansion facility manufacturing",
            company_filter=company,
            n_results=20,
        )

        regional_mentions[region] = {
            "mentions": len(docs),
            "sample_context": docs[0]["content"][:200] if docs else None,
        }

    sorted_regions = sorted(
        regional_mentions.items(), key=lambda x: x[1]["mentions"], reverse=True
    )
    top_regions = sorted_regions[:3]

    return {
        "company": company,
        "regional_mentions": regional_mentions,
        "investment_focus": [
            {"region": r, "mentions": m["mentions"]} for r, m in top_regions
        ],
        "primary_focus": top_regions[0][0] if top_regions else None,
    }


def compare_geographic_footprints() -> dict:
    """Compare geographic footprints across all companies."""
    all_data = _load_all()
    companies = list(TRACKED_COMPANY_NAMES)

    results: dict = {
        "companies": [],
        "regional_leaders": {"Americas": None, "EMEA": None, "APAC": None},
        "overlap_analysis": {},
    }

    regional_counts: dict[str, dict[str, int]] = {
        "Americas": {}, "EMEA": {}, "APAC": {},
    }

    for company in companies:
        distribution = get_regional_distribution(company)
        facilities = get_company_facilities(company)

        if "error" not in distribution:
            results["companies"].append({
                "company": company,
                "total_facilities": facilities.get("total_facilities", 0),
                "regional_distribution": distribution["distribution"],
                "primary_region": distribution["primary_region"],
            })

            for region, count in distribution["distribution"].items():
                regional_counts[region][company] = count

    for region, counts in regional_counts.items():
        if counts:
            leader = max(counts, key=counts.get)
            results["regional_leaders"][region] = {
                "company": leader,
                "count": counts[leader],
            }

    # Overlap analysis from cached data
    city_companies: dict[str, list[str]] = defaultdict(list)
    for f in all_data:
        city = f.get("city", "")
        if city:
            city_companies[city].append(f["company"])

    # Deduplicate company names per city
    for city in city_companies:
        city_companies[city] = sorted(set(city_companies[city]))

    overlap_cities = {
        city: comps for city, comps in city_companies.items() if len(comps) > 1
    }
    results["overlap_analysis"] = {
        "shared_locations": len(overlap_cities),
        "locations": overlap_cities,
    }

    return results
