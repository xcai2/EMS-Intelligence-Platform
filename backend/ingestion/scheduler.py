"""
Automated scheduler for data ingestion tasks.
Uses APScheduler to run periodic data updates.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone
import logging

from backend.core.config import INGESTION_SCHEDULE
from backend.ingestion.sec_downloader import SECDownloader
from backend.ingestion.processor import process_new_filings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def scheduled_sec_check():
    """
    Scheduled task to check for new SEC filings.
    Runs daily to check for new 10-K, 10-Q, 8-K filings.
    """
    logger.info(f"[{datetime.now()}] Starting scheduled SEC filing check...")
    
    try:
        downloader = SECDownloader()
        new_filings = await downloader.check_and_download_new_filings(
            filing_types=["10-K", "10-Q", "8-K"],
            days_back=7,  # Check last week
        )
        
        if new_filings:
            logger.info(f"Found {len(new_filings)} new filings. Processing...")
            
            # Process and add to ChromaDB
            processed = await process_new_filings(new_filings)
            logger.info(f"Processed {processed} new documents into ChromaDB")
            
            # TODO: Send alert notification
            # await send_new_filing_alert(new_filings)
        else:
            logger.info("No new filings found.")
            
    except Exception as e:
        logger.error(f"Error in scheduled SEC check: {e}")


async def scheduled_web_update():
    """
    Scheduled task to fetch latest news and updates.
    """
    logger.info(f"[{datetime.now()}] Starting web content update...")

    # TODO: Implement news feed scraping
    # This could fetch from:
    # - Company press release pages
    # - Financial news APIs
    # - Industry news sources


async def warm_analyst_cache():
    """
    Pre-warm the analyst-view company intel cache.

    Runs every 30 minutes so the /company-intel endpoint always responds
    from cache (instant) rather than waiting for Brave + LLM calls.
    After refreshing, broadcasts a 'cache_refreshed' SSE event so any
    connected frontend clients silently pull the new data.
    """
    # Lazy imports to avoid circular dependencies at module load time
    from backend.analyst_view.service import get_all_company_intel, TRACKED_COMPANIES, _cache_key
    from backend.analyst_view.broadcaster import broadcast_update
    from backend.core.cache import analytics_cache

    logger.info("[scheduler] Starting analyst cache warm-up...")

    # Invalidate all per-ticker entries so get_all_company_intel re-fetches
    for ticker, _, _ in TRACKED_COMPANIES:
        analytics_cache.delete(_cache_key(ticker))

    try:
        result = await get_all_company_intel()
        company_count = len(result.get("companies", []))
        cached_at = result.get("cached_at", datetime.now(timezone.utc).isoformat())
        logger.info(f"[scheduler] Analyst cache warmed — {company_count} companies, cached_at={cached_at}")

        # Notify all connected SSE clients
        await broadcast_update("cache_refreshed", {
            "cached_at": cached_at,
            "companies": company_count,
        })
    except Exception as e:
        logger.error(f"[scheduler] Analyst cache warm-up failed: {e}")


def start_scheduler():
    """Start the background scheduler."""
    if scheduler.running:
        logger.info("Scheduler already running")
        return
    
    # Add SEC filing check job - runs daily at 4 PM ET (after market close)
    scheduler.add_job(
        scheduled_sec_check,
        CronTrigger.from_crontab(INGESTION_SCHEDULE),
        id="sec_filing_check",
        name="Check for new SEC filings",
        replace_existing=True,
    )
    
    # Add hourly quick check for 8-K filings (material events)
    scheduler.add_job(
        scheduled_sec_check,
        IntervalTrigger(hours=6),
        id="sec_8k_check",
        name="Quick check for 8-K filings",
        replace_existing=True,
    )

    # Pre-warm analyst-view cache every 30 min so API responses are instant
    scheduler.add_job(
        warm_analyst_cache,
        IntervalTrigger(minutes=30),
        id="analyst_cache_warmup",
        name="Pre-warm analyst view cache",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("Scheduler started with jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name}: {job.trigger}")


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


def get_scheduler_status() -> dict:
    """Get current scheduler status."""
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "trigger": str(job.trigger),
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            }
            for job in scheduler.get_jobs()
        ],
    }


async def run_manual_check():
    """Manually trigger a filing check."""
    logger.info("Manual SEC filing check triggered")
    await scheduled_sec_check()
