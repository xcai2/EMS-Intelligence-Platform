"""
Geographic analysis for EMS company facilities.
Provides facility mapping and regional investment analysis.
"""
from typing import Optional
from collections import defaultdict

from backend.core.config import TRACKED_COMPANY_NAMES
from backend.rag.retriever import search_documents


# Known EMS facility locations (from public filings and company information)
KNOWN_FACILITIES = {
    "Flex": {
        "headquarters": {"city": "Singapore", "country": "Singapore", "lat": 1.3521, "lng": 103.8198},
        "facilities": [
            {"city": "Guadalajara", "country": "Mexico", "lat": 20.6597, "lng": -103.3496, "type": "Manufacturing"},
            {"city": "Austin", "country": "USA", "lat": 30.2672, "lng": -97.7431, "type": "Design Center"},
            {"city": "Memphis", "country": "USA", "lat": 35.1495, "lng": -90.0490, "type": "Manufacturing"},
            {"city": "Tijuana", "country": "Mexico", "lat": 32.5149, "lng": -117.0382, "type": "Manufacturing"},
            {"city": "Ciudad Juarez", "country": "Mexico", "lat": 31.6904, "lng": -106.4245, "type": "Manufacturing"},
            {"city": "Aguascalientes", "country": "Mexico", "lat": 21.8853, "lng": -102.2916, "type": "Manufacturing"},
            {"city": "Shanghai", "country": "China", "lat": 31.2304, "lng": 121.4737, "type": "Manufacturing"},
            {"city": "Shenzhen", "country": "China", "lat": 22.5431, "lng": 114.0579, "type": "Manufacturing"},
            {"city": "Penang", "country": "Malaysia", "lat": 5.4141, "lng": 100.3288, "type": "Manufacturing"},
            {"city": "Johor", "country": "Malaysia", "lat": 1.4927, "lng": 103.7414, "type": "Manufacturing"},
            {"city": "Chennai", "country": "India", "lat": 13.0827, "lng": 80.2707, "type": "Design Center"},
            {"city": "Bangalore", "country": "India", "lat": 12.9716, "lng": 77.5946, "type": "Design Center"},
            {"city": "Pune", "country": "India", "lat": 18.5204, "lng": 73.8567, "type": "Design Center"},
            {"city": "Zhuhai", "country": "China", "lat": 22.2769, "lng": 113.5678, "type": "Manufacturing"},
            {"city": "Sorocaba", "country": "Brazil", "lat": -23.5015, "lng": -47.4526, "type": "Manufacturing"},
            {"city": "Manaus", "country": "Brazil", "lat": -3.1190, "lng": -60.0217, "type": "Manufacturing"},
            {"city": "Timisoara", "country": "Romania", "lat": 45.7489, "lng": 21.2087, "type": "Manufacturing"},
            {"city": "Tczew", "country": "Poland", "lat": 54.0924, "lng": 18.7779, "type": "Manufacturing"},
            {"city": "Taoyuan", "country": "Taiwan", "lat": 24.9937, "lng": 121.3010, "type": "Manufacturing", "website": "https://en.twf.com.tw"},
            {"city": "Suzhou", "country": "China", "lat": 31.2989, "lng": 120.5853, "type": "Manufacturing"},
        ]
    },
    "Jabil": {
        "headquarters": {"city": "St. Petersburg", "country": "USA", "lat": 27.7676, "lng": -82.6403},
        "facilities": [
            {"city": "Penang", "country": "Malaysia", "lat": 5.4141, "lng": 100.3288, "type": "Manufacturing"},
            {"city": "Wuxi", "country": "China", "lat": 31.4912, "lng": 120.3119, "type": "Manufacturing"},
            {"city": "Chihuahua", "country": "Mexico", "lat": 28.6353, "lng": -106.0889, "type": "Manufacturing"},
            {"city": "Livingston", "country": "UK", "lat": 55.9024, "lng": -3.5159, "type": "Manufacturing"},
            {"city": "Budapest", "country": "Hungary", "lat": 47.4979, "lng": 19.0402, "type": "Manufacturing"},
            {"city": "Guadalajara", "country": "Mexico", "lat": 20.6597, "lng": -103.3496, "type": "Manufacturing"},
            {"city": "Shenzhen", "country": "China", "lat": 22.5431, "lng": 114.0579, "type": "Manufacturing"},
            {"city": "San Jose", "country": "USA", "lat": 37.3382, "lng": -121.8863, "type": "Design Center"},
        ]
    },
    "Celestica": {
        "headquarters": {"city": "Toronto", "country": "Canada", "lat": 43.6532, "lng": -79.3832},
        "facilities": [
            {"city": "Monterrey", "country": "Mexico", "lat": 25.6866, "lng": -100.3161, "type": "Manufacturing"},
            {"city": "Suzhou", "country": "China", "lat": 31.2989, "lng": 120.5853, "type": "Manufacturing"},
            {"city": "Kulim", "country": "Malaysia", "lat": 5.3717, "lng": 100.5627, "type": "Manufacturing"},
            {"city": "Valencia", "country": "Spain", "lat": 39.4699, "lng": -0.3763, "type": "Manufacturing"},
            {"city": "Oradea", "country": "Romania", "lat": 47.0458, "lng": 21.9189, "type": "Manufacturing"},
            {"city": "Portland", "country": "USA", "lat": 45.5051, "lng": -122.6750, "type": "Design Center"},
            {"city": "Fremont", "country": "USA", "lat": 37.5485, "lng": -121.9886, "type": "Manufacturing"},
        ]
    },
    "Benchmark": {
        "headquarters": {"city": "Tempe", "country": "USA", "lat": 33.4255, "lng": -111.9400},
        "facilities": [
            {"city": "Rochester", "country": "USA", "lat": 43.1566, "lng": -77.6088, "type": "Manufacturing"},
            {"city": "Angleton", "country": "USA", "lat": 29.1694, "lng": -95.4316, "type": "Manufacturing"},
            {"city": "Suzhou", "country": "China", "lat": 31.2989, "lng": 120.5853, "type": "Manufacturing"},
            {"city": "Penang", "country": "Malaysia", "lat": 5.4141, "lng": 100.3288, "type": "Manufacturing"},
            {"city": "Guadalajara", "country": "Mexico", "lat": 20.6597, "lng": -103.3496, "type": "Manufacturing"},
            {"city": "Amsterdam", "country": "Netherlands", "lat": 52.3676, "lng": 4.9041, "type": "Design Center"},
        ]
    },
    "Sanmina": {
        "headquarters": {"city": "San Jose", "country": "USA", "lat": 37.3382, "lng": -121.8863},
        "facilities": [
            {"city": "Guadalajara", "country": "Mexico", "lat": 20.6597, "lng": -103.3496, "type": "Manufacturing"},
            {"city": "Shenzhen", "country": "China", "lat": 22.5431, "lng": 114.0579, "type": "Manufacturing"},
            {"city": "Chennai", "country": "India", "lat": 13.0827, "lng": 80.2707, "type": "Manufacturing"},
            {"city": "Kecskemet", "country": "Hungary", "lat": 46.8963, "lng": 19.6897, "type": "Manufacturing"},
            {"city": "Wuxi", "country": "China", "lat": 31.4912, "lng": 120.3119, "type": "Manufacturing"},
            {"city": "Kunshan", "country": "China", "lat": 31.3847, "lng": 120.9837, "type": "Manufacturing"},
            {"city": "Fremont", "country": "USA", "lat": 37.5485, "lng": -121.9886, "type": "Manufacturing"},
        ]
    },
}


def get_company_facilities(company: str, include_extracted: bool = True) -> dict:
    """Get facility information for a company, optionally including auto-extracted facilities."""
    
    if include_extracted:
        # Use combined facilities (known + extracted from documents)
        try:
            from backend.analytics.facility_extractor import get_combined_facilities
            combined = get_combined_facilities(company)
            
            # Find headquarters
            hq = None
            facilities = []
            for f in combined.get("facilities", []):
                if f.get("type") == "Headquarters":
                    hq = f
                else:
                    facilities.append(f)
            
            return {
                "company": company,
                "headquarters": hq,
                "facilities": facilities,
                "total_facilities": combined.get("total_facilities", 0),
                "known_count": combined.get("known_count", 0),
                "extracted_count": combined.get("extracted_count", 0),
                "new_discoveries": combined.get("new_discoveries", []),
                "data_source": "combined",
            }
        except Exception as e:
            # Fall back to known facilities
            pass
    
    # Fallback to hardcoded known facilities
    company_data = KNOWN_FACILITIES.get(company)
    
    if not company_data:
        return {"company": company, "error": "Company not found"}
    
    return {
        "company": company,
        "headquarters": company_data["headquarters"],
        "facilities": company_data["facilities"],
        "total_facilities": len(company_data["facilities"]) + 1,  # +1 for HQ
        "data_source": "known",
    }


def get_regional_distribution(company: str) -> dict:
    """Get regional distribution of facilities."""
    company_data = get_company_facilities(company)

    if "error" in company_data:
        return {"company": company, "error": "Company not found"}
    
    regions = {
        "Americas": ["USA", "Canada", "Mexico", "Brazil"],
        "EMEA": ["UK", "Hungary", "Romania", "Netherlands", "Spain", "Germany", "Poland"],
        "APAC": ["China", "Malaysia", "Singapore", "India", "Japan", "Taiwan"],
    }
    
    distribution = {"Americas": 0, "EMEA": 0, "APAC": 0}
    
    # Count HQ
    headquarters = company_data.get("headquarters")
    if headquarters:
        hq_country = headquarters.get("country")
        for region, countries in regions.items():
            if hq_country in countries:
                distribution[region] += 1
                break
    
    # Count facilities
    for facility in company_data.get("facilities", []):
        country = facility.get("country")
        for region, countries in regions.items():
            if country in countries:
                distribution[region] += 1
                break
    
    total = sum(distribution.values())
    percentages = {k: round(v / total * 100, 1) if total > 0 else 0 for k, v in distribution.items()}
    
    return {
        "company": company,
        "distribution": distribution,
        "percentages": percentages,
        "primary_region": max(distribution, key=distribution.get) if total > 0 else None,
    }


def get_all_facilities_map(include_extracted: bool = True) -> dict:
    """Get all facilities for map visualization, including auto-extracted ones."""
    all_facilities = []
    by_company = {}
    new_discoveries = []
    
    companies = list(TRACKED_COMPANY_NAMES)
    
    for company in companies:
        company_facilities = get_company_facilities(company, include_extracted=include_extracted)
        
        if "error" in company_facilities:
            continue
        
        # Add headquarters
        hq = company_facilities.get("headquarters")
        if hq:
            all_facilities.append({
                "company": company,
                "city": hq.get("city"),
                "country": hq.get("country"),
                "lat": hq.get("lat"),
                "lng": hq.get("lng"),
                "type": "Headquarters",
                "is_headquarters": True,
                "source": hq.get("source", "known"),
                "confidence": hq.get("confidence", 1.0),
            })
        
        # Add facilities
        for facility in company_facilities.get("facilities", []):
            all_facilities.append({
                "company": company,
                "city": facility.get("city"),
                "country": facility.get("country"),
                "lat": facility.get("lat"),
                "lng": facility.get("lng"),
                "type": facility.get("type", "Manufacturing"),
                "website": facility.get("website"),
                "is_headquarters": False,
                "source": facility.get("source", "known"),
                "confidence": facility.get("confidence", 1.0),
            })
        
        by_company[company] = company_facilities.get("total_facilities", 0)
        
        # Track new discoveries
        for discovery in company_facilities.get("new_discoveries", []):
            discovery["company"] = company
            new_discoveries.append(discovery)
    
    return {
        "facilities": all_facilities,
        "total_count": len(all_facilities),
        "by_company": by_company,
        "new_discoveries": new_discoveries,
        "includes_extracted": include_extracted,
    }


def analyze_regional_investments(company: str) -> dict:
    """
    Analyze regional investment mentions in company filings.
    """
    # Search for regional investment content
    regions_to_search = ["Americas", "Asia", "Europe", "Mexico", "China", "Malaysia", "India"]
    
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
    
    # Determine investment focus
    sorted_regions = sorted(regional_mentions.items(), key=lambda x: x[1]["mentions"], reverse=True)
    top_regions = sorted_regions[:3]
    
    return {
        "company": company,
        "regional_mentions": regional_mentions,
        "investment_focus": [{"region": r, "mentions": m["mentions"]} for r, m in top_regions],
        "primary_focus": top_regions[0][0] if top_regions else None,
    }


def compare_geographic_footprints() -> dict:
    """
    Compare geographic footprints across all companies.
    """
    companies = list(TRACKED_COMPANY_NAMES)
    
    results = {
        "companies": [],
        "regional_leaders": {
            "Americas": None,
            "EMEA": None,
            "APAC": None,
        },
        "overlap_analysis": {},
    }
    
    regional_counts = {"Americas": {}, "EMEA": {}, "APAC": {}}
    
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
            
            # Track for leaders
            for region, count in distribution["distribution"].items():
                regional_counts[region][company] = count
    
    # Determine regional leaders
    for region, counts in regional_counts.items():
        if counts:
            leader = max(counts, key=counts.get)
            results["regional_leaders"][region] = {
                "company": leader,
                "count": counts[leader],
            }
    
    # Analyze overlap (cities with multiple companies)
    city_companies = defaultdict(list)
    for company in companies:
        facilities = get_company_facilities(company)
        if "error" in facilities:
            continue
        for facility in facilities.get("facilities", []):
            city = facility.get("city")
            if city:
                city_companies[city].append(company)
    
    overlap_cities = {city: companies for city, companies in city_companies.items() if len(companies) > 1}
    results["overlap_analysis"] = {
        "shared_locations": len(overlap_cities),
        "locations": overlap_cities,
    }
    
    return results
