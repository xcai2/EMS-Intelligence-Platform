"""
API routes for data ingestion management.
"""
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from typing import Optional
from pydantic import BaseModel

from backend.ingestion.sec_downloader import SECDownloader
from backend.ingestion.scheduler import (
    start_scheduler,
    stop_scheduler,
    get_scheduler_status,
    run_manual_check,
    run_manual_transcript_check,
)
from backend.ingestion.processor import process_new_filings
from backend.ingestion.transcript_ingester import TranscriptIngester

router = APIRouter()
logger = logging.getLogger(__name__)


class FilingCheckRequest(BaseModel):
    """Request body for filing check."""
    days_back: int = 30
    filing_types: list[str] = ["10-K", "10-Q", "8-K"]


@router.get("/ingestion/status")
async def get_ingestion_status():
    """Get current ingestion scheduler status and download stats."""
    scheduler_status = get_scheduler_status()
    downloader = SECDownloader()
    download_stats = downloader.get_download_stats()
    transcript_stats = TranscriptIngester().get_stats()

    return {
        "scheduler":   scheduler_status,
        "downloads":   download_stats,
        "transcripts": transcript_stats,
    }


@router.post("/ingestion/start-scheduler")
async def api_start_scheduler():
    """Start the automated ingestion scheduler."""
    try:
        start_scheduler()
        return {"status": "started", "scheduler": get_scheduler_status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingestion/stop-scheduler")
async def api_stop_scheduler():
    """Stop the automated ingestion scheduler."""
    try:
        stop_scheduler()
        return {"status": "stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingestion/check-filings")
async def check_filings(
    background_tasks: BackgroundTasks,
    request: FilingCheckRequest,
):
    """
    Manually trigger a check for new SEC filings.
    Returns immediately; processing runs in the background.
    """
    async def check_and_process():
        downloader = SECDownloader()
        new_filings = await downloader.check_and_download_new_filings(
            filing_types=request.filing_types,
            days_back=request.days_back,
        )
        if new_filings:
            processed = await asyncio.to_thread(process_new_filings, new_filings)
            logger.info(
                "Manual filing check: %d files, %d chunks",
                processed["files_processed"], processed["chunks_added"],
            )

    background_tasks.add_task(check_and_process)
    return {
        "status":       "checking",
        "message":      f"Checking for filings from last {request.days_back} days",
        "filing_types": request.filing_types,
    }


@router.get("/ingestion/filings")
async def get_available_filings(
    ticker: Optional[str] = None,
    days_back: int = 90,
):
    """Get list of available SEC filings (metadata only, no download)."""
    downloader = SECDownloader()

    if ticker:
        filings = await downloader.get_company_filings(ticker.upper(), days_back=days_back)
        return {"ticker": ticker, "filings": filings}

    from backend.core.config import COMPANIES
    all_filings = {}
    for company_ticker in COMPANIES.keys():
        all_filings[company_ticker] = await downloader.get_company_filings(
            company_ticker, days_back=days_back
        )
    return {"filings": all_filings}


@router.post("/ingestion/download-filing")
async def download_specific_filing(
    ticker: str,
    form: str,
    filing_date: str,
    background_tasks: BackgroundTasks,
):
    """Download and ingest a specific SEC filing by ticker/form/date."""
    downloader = SECDownloader()
    filings = await downloader.get_company_filings(ticker.upper(), days_back=365)

    target = next(
        (f for f in filings if f["form"] == form and f["filing_date"] == filing_date),
        None,
    )
    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Filing not found: {ticker} {form} {filing_date}",
        )

    if target["already_downloaded"]:
        return {"status": "already_downloaded", "filing": target}

    async def download_and_process():
        path = await downloader.download_filing(target)
        if path:
            target["filepath"] = str(path)
            target["company"]  = target["company_short"]
            processed = await asyncio.to_thread(process_new_filings, [target])
            logger.info(
                "Single filing ingested: %d chunks", processed["chunks_added"]
            )

    background_tasks.add_task(download_and_process)
    return {"status": "downloading", "filing": target}


# ---------------------------------------------------------------------------
# TRANSCRIPT ENDPOINTS
# ---------------------------------------------------------------------------

@router.get("/ingestion/transcript-stats")
async def get_transcript_stats():
    """
    Return statistics about earnings transcripts / press releases
    that have already been ingested into ChromaDB.
    """
    try:
        return TranscriptIngester().get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingestion/check-transcripts")
async def check_transcripts(
    background_tasks: BackgroundTasks,
    days_back: int = 90,
):
    """
    Scan 8-K filings for new earnings transcripts / press releases and
    ingest any that haven't been processed yet. Runs in the background.
    """
    async def _run():
        ingester = TranscriptIngester()
        result = await asyncio.to_thread(ingester.check_all_companies, days_back)
        logger.info("Manual transcript check complete: %s", result)

    background_tasks.add_task(_run)
    return {
        "status":    "checking",
        "message":   f"Scanning 8-K exhibits from last {days_back} days",
        "days_back": days_back,
    }
