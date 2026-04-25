"""
Automated scheduler for data ingestion tasks.
Uses APScheduler to run periodic data updates.

Jobs:
  sec_filing_check   — daily at 4 PM ET (Mon–Fri): downloads new 10-K/10-Q/8-K
  sec_8k_check       — every 6 h: quick 8-K check for material events
  transcript_check   — daily at 6 PM ET (Mon–Fri): ingests earnings transcripts
  analyst_cache_warmup — every 30 min: pre-warms analyst-view cache
  transcript_check_startup — one-shot 60 s after startup
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.core.config import INGESTION_SCHEDULE
from backend.ingestion.sec_downloader import SECDownloader
from backend.ingestion.processor import process_new_filings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


# ---------------------------------------------------------------------------
# JOB: SEC FILING CHECK
# ---------------------------------------------------------------------------
async def scheduled_sec_check():
    """Check for new 10-K / 10-Q / 8-K filings and ingest them into ChromaDB."""
    logger.info("[scheduler] Starting SEC filing check...")
    try:
        downloader = SECDownloader()
        new_filings = await downloader.check_and_download_new_filings(
            filing_types=["10-K", "10-Q", "8-K"],
            days_back=7,
        )

        if new_filings:
            logger.info("[scheduler] Found %d new filings — processing...", len(new_filings))
            # process_new_filings is synchronous; run in thread pool
            processed = await asyncio.to_thread(process_new_filings, new_filings)
            logger.info(
                "[scheduler] SEC ingestion done — %d files, %d chunks",
                processed["files_processed"],
                processed["chunks_added"],
            )
            if processed.get("errors"):
                logger.warning("[scheduler] Processing errors: %s", processed["errors"])
        else:
            logger.info("[scheduler] No new SEC filings found.")

    except Exception as e:
        logger.error("[scheduler] SEC filing check failed: %s", e)


# ---------------------------------------------------------------------------
# JOB: EARNINGS TRANSCRIPT CHECK
# ---------------------------------------------------------------------------
async def scheduled_transcript_check():
    """
    Scan recent 8-K filings for earnings transcript / press-release exhibits
    and ingest any newly found documents into ChromaDB.
    """
    logger.info("[scheduler] Starting earnings transcript check...")
    try:
        from backend.ingestion.transcript_ingester import TranscriptIngester
        ingester = TranscriptIngester()
        # TranscriptIngester.check_all_companies() is synchronous
        result = await asyncio.to_thread(ingester.check_all_companies, 30)
        logger.info(
            "[scheduler] Transcript check done — %d ingested, %d errors, %d companies",
            result["exhibits_ingested"],
            result["errors"],
            result["companies_checked"],
        )
    except Exception as e:
        logger.error("[scheduler] Transcript check failed: %s", e)


# ---------------------------------------------------------------------------
# JOB: ANALYST CACHE WARMUP
# ---------------------------------------------------------------------------
async def warm_analyst_cache():
    """
    Pre-warm the analyst-view company intel cache every 30 min so the
    /company-intel endpoint always responds instantly from cache.
    Broadcasts a 'cache_refreshed' SSE event to connected frontend clients.
    """
    from backend.analyst_view.service import get_all_company_intel, TRACKED_COMPANIES, _cache_key
    from backend.analyst_view.broadcaster import broadcast_update
    from backend.core.cache import analytics_cache

    logger.info("[scheduler] Starting analyst cache warm-up...")

    for ticker, _, _ in TRACKED_COMPANIES:
        analytics_cache.delete(_cache_key(ticker))

    try:
        result = await get_all_company_intel()
        company_count = len(result.get("companies", []))
        cached_at = result.get("cached_at", datetime.now(timezone.utc).isoformat())
        logger.info(
            "[scheduler] Analyst cache warmed — %d companies, cached_at=%s",
            company_count, cached_at,
        )
        await broadcast_update("cache_refreshed", {
            "cached_at": cached_at,
            "companies": company_count,
        })
    except Exception as e:
        logger.error("[scheduler] Analyst cache warm-up failed: %s", e)


# ---------------------------------------------------------------------------
# SCHEDULER MANAGEMENT
# ---------------------------------------------------------------------------
def start_scheduler():
    """Start the background scheduler with all ingestion and cache jobs."""
    if scheduler.running:
        logger.info("[scheduler] Already running")
        return

    # 1. Daily SEC filing check at 4 PM ET (Mon–Fri)
    scheduler.add_job(
        scheduled_sec_check,
        CronTrigger.from_crontab(INGESTION_SCHEDULE),
        id="sec_filing_check",
        name="Check for new SEC filings",
        replace_existing=True,
        max_instances=1,
    )

    # 2. Quick 8-K check every 6 hours (material events)
    scheduler.add_job(
        scheduled_sec_check,
        IntervalTrigger(hours=6),
        id="sec_8k_check",
        name="Quick check for 8-K filings",
        replace_existing=True,
        max_instances=1,
    )

    # 3. Earnings transcript check daily at 6 PM ET (Mon–Fri, 2 h after SEC check)
    scheduler.add_job(
        scheduled_transcript_check,
        CronTrigger(hour=18, minute=0, day_of_week="mon-fri", timezone="America/New_York"),
        id="transcript_check",
        name="Ingest earnings transcripts from 8-K exhibits",
        replace_existing=True,
        max_instances=1,
    )

    # 4. One-shot transcript check 60 s after startup (index warm-up)
    startup_time = datetime.now(timezone.utc) + timedelta(seconds=60)
    scheduler.add_job(
        scheduled_transcript_check,
        DateTrigger(run_date=startup_time),
        id="transcript_check_startup",
        name="One-shot transcript check on startup",
        replace_existing=True,
    )

    # 5. Analyst cache warmup every 30 min
    scheduler.add_job(
        warm_analyst_cache,
        IntervalTrigger(minutes=30),
        id="analyst_cache_warmup",
        name="Pre-warm analyst view cache",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("[scheduler] Started with jobs:")
    for job in scheduler.get_jobs():
        logger.info("  - %s: %s", job.name, job.trigger)


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("[scheduler] Stopped")


def get_scheduler_status() -> dict:
    """Return current scheduler status and job list."""
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id":       job.id,
                "name":     job.name,
                "trigger":  str(job.trigger),
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            }
            for job in scheduler.get_jobs()
        ],
    }


async def run_manual_check():
    """Manually trigger a full SEC filing check."""
    logger.info("[scheduler] Manual SEC check triggered")
    await scheduled_sec_check()


async def run_manual_transcript_check():
    """Manually trigger a full transcript ingestion check."""
    logger.info("[scheduler] Manual transcript check triggered")
    await scheduled_transcript_check()
