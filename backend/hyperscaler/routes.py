import asyncio
import logging

from fastapi import APIRouter, HTTPException

from backend.hyperscaler import service, financials as fin_mod

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/big5-capex")
async def get_big5_capex():
    return service.build_response_from_cache()


@router.get("/big5-capex/summary")
async def get_big5_capex_summary():
    response = service.build_response_from_cache()
    return service.build_summary(response)


@router.delete("/hyperscaler/guidance/cache")
async def refresh_guidance():
    try:
        result = await service.refresh_from_gemini()
        return result
    except Exception as exc:
        logger.error("Guidance refresh failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Gemini refresh failed: {exc}")


@router.get("/hyperscaler/all/financials")
async def get_all_hyperscaler_financials():
    return await asyncio.to_thread(fin_mod.fetch_all_hyperscaler_financials)


@router.get("/hyperscaler/{company}/financials")
async def get_hyperscaler_financials(company: str):
    result = await asyncio.to_thread(fin_mod.fetch_hyperscaler_financials, company.title())
    if result.error:
        raise HTTPException(status_code=404, detail=result.error)
    return result


@router.delete("/hyperscaler/cache")
async def invalidate_hyperscaler_cache(company: str | None = None):
    fin_mod.invalidate_financials_cache(company)
    return {"status": "ok", "company": company or "all"}
