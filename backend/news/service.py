"""
News feed integration for competitive intelligence.
Aggregates news from multiple sources for tracked companies.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.core.config import COMPANIES
from backend.news.company_news_service import (
    build_company_news_payload,
)
from backend.news.comparative_news_service import build_comparative_news_payload
from backend.news.industry_news_service import build_industry_news_payload
from backend.news.normalizer import parse_published_dt
from backend.news.source_fetchers import NewsSourceFetcherGateway

logger = logging.getLogger(__name__)
LEGACY_CACHE_FILE = Path("data/news_runtime_cache.json")
NEWS_CACHE_DIR = Path("data/news_cache")
COMPANY_CACHE_FILE = NEWS_CACHE_DIR / "company_news.json"
INDUSTRY_CACHE_FILE = NEWS_CACHE_DIR / "industry_news.json"
COMPARATIVE_CACHE_FILE = NEWS_CACHE_DIR / "comparative_news.json"
CACHE_SCHEMA_VERSION = 1


class NewsFeed:
    """
    Aggregates and manages company news from multiple sources.
    """

    def __init__(self):
        self._cache_ttl = 3600  # 1 hour cache
        # Persisted cache for the three primary news pipelines.
        self._runtime_cache: dict[str, dict] = {}
        # Non-persisted aggregate cache for assembled responses such as /news/all.
        self._aggregate_cache: dict[str, dict] = {}
        self._google_redirect_cache: dict[str, str] = {}
        self.fetchers = NewsSourceFetcherGateway(self)
        self._load_runtime_cache()

    def _load_runtime_cache(self) -> None:
        try:
            self._runtime_cache = {}

            structured_paths = [COMPANY_CACHE_FILE, INDUSTRY_CACHE_FILE, COMPARATIVE_CACHE_FILE]
            if any(path.exists() for path in structured_paths):
                self._load_structured_cache_files()
                self._cleanup_legacy_cache_file()
                logger.info("Loaded structured news cache with %d keys", len(self._runtime_cache))
                return

            if LEGACY_CACHE_FILE.exists():
                migrated = self._migrate_legacy_cache_file()
                if migrated:
                    logger.info("Migrated legacy news cache into structured files with %d keys", len(self._runtime_cache))
                    return
        except Exception as e:
            logger.warning("Failed to load news runtime cache: %s", e)

    def _persist_runtime_cache(self) -> None:
        try:
            NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

            company_payload = {
                "version": CACHE_SCHEMA_VERSION,
                "updated_at": self._now_utc_iso(),
                "companies": {},
            }
            industry_payload = {
                "version": CACHE_SCHEMA_VERSION,
                "updated_at": self._now_utc_iso(),
                "entries": {},
            }
            comparative_payload = {
                "version": CACHE_SCHEMA_VERSION,
                "updated_at": self._now_utc_iso(),
                "entry": None,
            }

            for key, value in self._runtime_cache.items():
                if key.startswith("company:") and key.endswith(":raw"):
                    ticker = key.split(":")[1]
                    company_payload["companies"][ticker] = value
                elif key.startswith("industry:"):
                    industry_payload["entries"][key.split(":", 1)[1]] = value
                elif key == "comparative":
                    comparative_payload["entry"] = value

            self._write_json_file(COMPANY_CACHE_FILE, company_payload)
            self._write_json_file(INDUSTRY_CACHE_FILE, industry_payload)
            self._write_json_file(COMPARATIVE_CACHE_FILE, comparative_payload)
        except Exception as e:
            logger.warning("Failed to persist news runtime cache: %s", e)

    def _write_json_file(self, path: Path, payload: dict) -> None:
        temp_file = path.with_suffix(path.suffix + ".tmp")
        temp_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_file.replace(path)

    def _read_json_file(self, path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else None

    def _load_structured_cache_files(self) -> None:
        company_payload = self._read_json_file(COMPANY_CACHE_FILE) or {}
        for ticker, payload in (company_payload.get("companies") or {}).items():
            if isinstance(payload, dict):
                self._runtime_cache[f"company:{ticker}:raw"] = payload

        industry_payload = self._read_json_file(INDUSTRY_CACHE_FILE) or {}
        for count_key, payload in (industry_payload.get("entries") or {}).items():
            if isinstance(payload, dict):
                self._runtime_cache[f"industry:{count_key}"] = payload

        comparative_payload = self._read_json_file(COMPARATIVE_CACHE_FILE) or {}
        comparative_entry = comparative_payload.get("entry")
        if isinstance(comparative_entry, dict):
            self._runtime_cache["comparative"] = comparative_entry

    def _migrate_legacy_cache_file(self) -> bool:
        legacy_payload = self._read_json_file(LEGACY_CACHE_FILE)
        if not legacy_payload:
            self._cleanup_legacy_cache_file()
            return False

        latest_company_entries: dict[str, tuple[int, dict]] = {}
        for key, value in legacy_payload.items():
            if not isinstance(value, dict):
                continue
            company_match = re.match(r"company:([A-Z]+):all:(\d+)$", key)
            if company_match:
                ticker, count_text = company_match.groups()
                requested_count = int(count_text)
                current = latest_company_entries.get(ticker)
                if current is None or requested_count > current[0]:
                    latest_company_entries[ticker] = (requested_count, value)
                continue

            if key.startswith("industry:"):
                self._runtime_cache[key] = value
                continue

            if key == "comparative":
                self._runtime_cache[key] = value

        for ticker, (_requested_count, value) in latest_company_entries.items():
            stored_news = value.get("news") or []
            self._runtime_cache[f"company:{ticker}:raw"] = {
                "ticker": value.get("ticker") or ticker,
                "company_name": value.get("company_name") or COMPANIES.get(ticker, {}).get("name", ticker),
                "fetched_count": len(stored_news),
                "news": stored_news,
                "timestamp": value.get("timestamp") or datetime.now().isoformat(),
                "diagnostics": value.get("diagnostics", {}),
            }

        if self._runtime_cache:
            self._persist_runtime_cache()

        self._cleanup_legacy_cache_file()
        return bool(self._runtime_cache)

    def _cleanup_legacy_cache_file(self) -> None:
        try:
            if LEGACY_CACHE_FILE.exists():
                LEGACY_CACHE_FILE.unlink()
        except Exception as e:
            logger.warning("Failed to remove legacy news cache file: %s", e)

    def _now_utc_iso(self) -> str:
        """Return a timezone-aware ISO-8601 timestamp for cache persistence."""
        return datetime.now(timezone.utc).isoformat()

    def _is_cache_entry_fresh(self, payload: Optional[dict], max_age_seconds: Optional[int] = None) -> bool:
        """Check whether a cached payload is fresh enough to reuse."""
        if not payload:
            return False
        ttl = max_age_seconds or self._cache_ttl
        cached_at = parse_published_dt(payload.get("timestamp", ""))
        if not cached_at:
            return False
        age_seconds = (datetime.now(timezone.utc) - cached_at).total_seconds()
        return 0 <= age_seconds <= ttl

    def _invalidate_aggregate_cache(self, prefix: str = "all:") -> None:
        """Invalidate aggregate runtime caches without touching persisted raw caches."""
        stale_keys = [key for key in self._aggregate_cache if key.startswith(prefix)]
        for key in stale_keys:
            self._aggregate_cache.pop(key, None)

    async def get_company_news(
        self,
        ticker: str,
        category: Optional[str] = None,
        count: int = 10,
        force_refresh: bool = False,
    ) -> dict:
        """
        Get recent news for a specific company.

        Args:
            ticker: Company ticker symbol
            category: Optional category filter (earnings, ai, capex, strategy, operations)
            count: Number of results to return
        """
        raw_cache_key = f"company:{ticker}:raw"
        if force_refresh:
            # Force refresh must replace old company payload, never merge with it.
            self._runtime_cache.pop(raw_cache_key, None)
        return await build_company_news_payload(
            self,
            ticker,
            category=category,
            count=count,
            force_refresh=force_refresh,
        )
    
    async def get_industry_news(self, count: int = 15, force_refresh: bool = False) -> dict:
        """
        Get industry-wide EMS/electronics manufacturing news.
        """
        if force_refresh:
            # Drop all industry cached variants so refresh result fully replaces old entries.
            industry_keys = [key for key in self._runtime_cache.keys() if key.startswith("industry:")]
            for key in industry_keys:
                self._runtime_cache.pop(key, None)
        return await build_industry_news_payload(self, count=count, force_refresh=force_refresh)
    
    async def get_competitor_comparison_news(self, force_refresh: bool = False) -> dict:
        """
        Get comparative news mentioning multiple competitors.
        """
        if force_refresh:
            self._runtime_cache.pop("comparative", None)
        return await build_comparative_news_payload(self, force_refresh=force_refresh)
    
    async def get_all_companies_news(self, count_per_company: int = 100, force_refresh: bool = False) -> dict:
        """
        Get news for all tracked companies.
        """
        cache_key = f"all:{count_per_company}"
        if not force_refresh and cache_key in self._aggregate_cache:
            return self._aggregate_cache[cache_key]
        if force_refresh:
            company_cache_keys = [
                key for key in self._runtime_cache.keys()
                if key.startswith("company:") and key.endswith(":raw")
            ]
            for key in company_cache_keys:
                self._runtime_cache.pop(key, None)
            self._invalidate_aggregate_cache("all:")

        all_news = {}

        for ticker in COMPANIES.keys():
            will_fetch = force_refresh
            news = await self.get_company_news(
                ticker,
                count=count_per_company,
                force_refresh=force_refresh,
            )
            all_news[ticker] = news
            if will_fetch:
                # Add delay when external source fetches are actually running
                # (either explicit force_refresh or auto-fetch for uncached companies).
                await asyncio.sleep(0.5)
        
        result = {
            "companies": all_news,
            "total_companies": len(all_news),
            "timestamp": self._now_utc_iso(),
        }
        self._aggregate_cache[cache_key] = result
        return result
    
