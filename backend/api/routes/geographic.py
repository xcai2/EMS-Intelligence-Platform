"""
API routes for geographic analysis and facility mapping.
Data is loaded from data/ems_facilities.json (populated by the scraper).
"""
from fastapi import APIRouter, HTTPException, Query

from backend.analytics.geographic import (
    get_company_facilities,
    get_regional_distribution,
    get_all_facilities_map,
    analyze_regional_investments,
    compare_geographic_footprints,
)
from backend.scraper.ems_scraper import (
    load_cached_facilities,
    load_scrape_meta,
    run_full_scrape_async,
)

router = APIRouter()


@router.get("/geographic/facilities")
async def get_all_facilities():
    """
    Get all facilities for map visualization.
    Reads from the local JSON cache (no network calls).
    """
    try:
        return get_all_facilities_map()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/geographic/facilities/{company}")
async def get_facilities(company: str):
    """Get facilities for a specific company."""
    try:
        result = get_company_facilities(company)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/geographic/distribution/{company}")
async def get_distribution(company: str):
    """Get regional distribution for a company."""
    try:
        result = get_regional_distribution(company)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/geographic/investments/{company}")
async def get_regional_investments(company: str):
    """Analyze regional investment mentions for a company."""
    try:
        return analyze_regional_investments(company)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/geographic/compare")
async def compare_footprints():
    """Compare geographic footprints across all companies."""
    try:
        return compare_geographic_footprints()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/geographic/meta")
async def get_meta():
    """Get scrape metadata (last_scraped timestamp, data sources, etc.)."""
    try:
        return load_scrape_meta()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/geographic/refresh")
async def refresh_facilities():
    """
    Trigger a full re-scrape of all 6 EMS company websites.
    This may take 1-2 minutes as it fetches data from each site.
    Returns the updated facility data and scrape summary.
    """
    try:
        meta = await run_full_scrape_async()
        facilities = get_all_facilities_map()
        return {
            "success": True,
            "scrape_summary": meta,
            "facilities": facilities,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/geographic/heatmap")
async def get_geographic_heatmap():
    """Get data formatted for heatmap visualization."""
    try:
        all_facilities = get_all_facilities_map()
        comparison = compare_geographic_footprints()

        heatmap_data = []
        for facility in all_facilities["facilities"]:
            heatmap_data.append({
                "lat": facility["lat"],
                "lng": facility["lng"],
                "intensity": 1.0 if facility["is_headquarters"] else 0.5,
                "company": facility["company"],
                "city": facility["city"],
                "type": facility["type"],
                "source": facility.get("source", "scraped"),
                "confidence": facility.get("confidence", 1.0),
            })

        return {
            "heatmap_points": heatmap_data,
            "total_facilities": all_facilities["total_count"],
            "regional_leaders": comparison["regional_leaders"],
            "shared_locations": comparison["overlap_analysis"]["shared_locations"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
