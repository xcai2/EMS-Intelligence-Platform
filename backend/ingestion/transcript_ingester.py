"""
Automated earnings transcript + press release ingester.

Strategy:
  1. For each tracked company, fetch recent 8-K filings from SEC EDGAR.
  2. For each 8-K, fetch the filing document index.
  3. Download exhibits identified as earnings transcripts or press releases.
  4. Chunk and embed them into ChromaDB via process_filing().
  5. Track ingested exhibit IDs so re-runs are idempotent.

Run context: called synchronously from a thread pool (asyncio.to_thread) by
the scheduler — do NOT use asyncio/AsyncClient inside this module.
"""
import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from backend.core.config import COMPANIES, SEC_USER_AGENT, DATA_DIR
from backend.ingestion.processor import process_filing

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FISCAL PERIOD HELPER
# (mirrors sec_downloader.py — kept separate to avoid circular imports)
# ---------------------------------------------------------------------------
FISCAL_YEAR_END_MONTH: dict[str, int] = {
    "FLEX": 3,   # March
    "JBL":  8,   # August
    "CLS":  12,  # December
    "BHE":  12,  # December
    "SANM": 9,   # September
    "PLXS": 9,   # September
}


def _infer_fiscal_period(period_of_report: str, ticker: str) -> tuple[str, str]:
    """
    Return (fiscal_year_label, quarter) from a period-end date and ticker.
    e.g. ("FY25", "Q3") or ("Unknown", "") on parse failure.
    """
    if not period_of_report or ticker not in FISCAL_YEAR_END_MONTH:
        return "Unknown", ""
    try:
        dt = datetime.strptime(period_of_report, "%Y-%m-%d")
    except ValueError:
        return "Unknown", ""

    fy_end = FISCAL_YEAR_END_MONTH[ticker]
    fy_year = dt.year if dt.month <= fy_end else dt.year + 1
    fy_label = f"FY{str(fy_year)[-2:]}"

    # Quarter: count 3-month blocks from the first month of the fiscal year
    fy_start_month = fy_end % 12 + 1
    months_into_fy = (dt.month - fy_start_month) % 12
    q_label = f"Q{months_into_fy // 3 + 1}"

    return fy_label, q_label


# ---------------------------------------------------------------------------
# EDGAR URL TEMPLATES
# ---------------------------------------------------------------------------
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
# HTML index — note: filename uses dash-formatted accession number
_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{accession_fmt}-index.htm"
)
_EXHIBIT_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}"
)

# ---------------------------------------------------------------------------
# EXHIBIT CLASSIFICATION RULES
# ---------------------------------------------------------------------------
_TRANSCRIPT_KEYWORDS = ["transcript"]
# Accept all EX-99.1/99.2 exhibits — they are company announcements
# (earnings results, strategic updates) valuable for sentiment analysis.
_PRESSRELEASE_EXHIBIT_TYPES = {"EX-99.1", "EX-99.2", "EX-99"}


# ---------------------------------------------------------------------------
# MAIN CLASS
# ---------------------------------------------------------------------------
class TranscriptIngester:
    """
    Downloads and ingests earnings transcripts and press releases from
    SEC EDGAR 8-K filings into ChromaDB.
    """

    def __init__(self):
        self.download_dir = DATA_DIR / "earnings_transcripts"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.tracking_file = self.download_dir / "ingested_exhibits.json"
        self.ingested: dict = self._load_tracking()
        self._http_headers = {
            "User-Agent": SEC_USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
        }

    # ------------------------------------------------------------------
    # TRACKING
    # ------------------------------------------------------------------
    def _load_tracking(self) -> dict:
        if self.tracking_file.exists():
            try:
                with open(self.tracking_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_tracking(self):
        with open(self.tracking_file, "w") as f:
            json.dump(self.ingested, f, indent=2)

    # ------------------------------------------------------------------
    # NETWORK (synchronous — called inside a thread pool)
    # ------------------------------------------------------------------
    def _get(self, url: str, timeout: float = 30.0) -> Optional[httpx.Response]:
        time.sleep(0.3)  # polite rate limit — SEC allows 10 req/s
        try:
            with httpx.Client(headers=self._http_headers, timeout=timeout) as c:
                resp = c.get(url)
                resp.raise_for_status()
                return resp
        except Exception as e:
            logger.debug("GET %s failed: %s", url, e)
            return None

    def _get_json(self, url: str, timeout: float = 30.0) -> Optional[dict]:
        resp = self._get(url, timeout)
        if resp is None:
            return None
        try:
            return resp.json()
        except Exception as e:
            logger.debug("JSON parse failed for %s: %s", url, e)
            return None

    def _get_bytes(self, url: str, timeout: float = 60.0) -> Optional[bytes]:
        resp = self._get(url, timeout)
        return resp.content if resp else None

    @staticmethod
    def _format_accession(accession_nodash: str) -> str:
        """Convert '000086637426000002' → '0000866374-26-000002'."""
        return f"{accession_nodash[:10]}-{accession_nodash[10:12]}-{accession_nodash[12:]}"

    # ------------------------------------------------------------------
    # CIK FORMATTING
    # ------------------------------------------------------------------
    @staticmethod
    def _padded_cik(raw_cik: str) -> str:
        """Zero-pad to 10 digits for submissions URL."""
        return raw_cik.lstrip("0").zfill(10)

    @staticmethod
    def _bare_cik(raw_cik: str) -> str:
        """Strip leading zeros for archive URLs."""
        return raw_cik.lstrip("0")

    # ------------------------------------------------------------------
    # EDGAR QUERIES
    # ------------------------------------------------------------------
    def _recent_8k_filings(self, ticker: str, days_back: int) -> list[dict]:
        """Return list of 8-K metadata dicts filed within days_back days."""
        cfg = COMPANIES.get(ticker)
        if not cfg:
            return []

        cik_padded = self._padded_cik(cfg["cik"])
        data = self._get_json(_SUBMISSIONS_URL.format(cik=cik_padded))
        if not data:
            return []

        recent = data.get("filings", {}).get("recent", {})
        if not recent:
            return []

        forms       = recent.get("form", [])
        dates       = recent.get("filingDate", [])
        accessions  = recent.get("accessionNumber", [])
        periods     = recent.get("periodOfReport", [])

        cutoff = datetime.now() - timedelta(days=days_back)
        results = []

        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            try:
                filing_date = datetime.strptime(dates[i], "%Y-%m-%d")
            except (ValueError, IndexError):
                continue
            if filing_date < cutoff:
                continue  # filings come newest-first; continue to check all

            acc_nodash = accessions[i].replace("-", "") if i < len(accessions) else ""
            period     = periods[i] if i < len(periods) else ""

            results.append({
                "ticker":           ticker,
                "cik_padded":       cik_padded,
                "accession":        acc_nodash,
                "period_of_report": period,
                "filing_date":      dates[i],
            })

        return results

    def _filing_index(self, cik_padded: str, accession_nodash: str) -> list[dict]:
        """
        Fetch the HTML filing index and return exhibit list.
        Each item: {name: filename, type: exhibit_type}.
        """
        acc_fmt = self._format_accession(accession_nodash)
        url = _INDEX_URL.format(
            cik=self._bare_cik(cik_padded),
            accession_nodash=accession_nodash,
            accession_fmt=acc_fmt,
        )
        resp = self._get(url)
        if not resp:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", {"class": "tableFile"}) or soup.find("table")
        if not table:
            return []

        items = []
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            # Columns: Seq | Description | Document (link) | Type | Size
            # Extract filename from the <a> href — use basename only
            link = cells[2].find("a")
            if link and link.get("href"):
                filename = link["href"].strip().rstrip("/").split("/")[-1]
            else:
                filename = cells[2].get_text(strip=True)
            exhibit_type = cells[3].get_text(strip=True).strip() if len(cells) > 3 else ""

            # Skip binary/stylesheet assets and the complete-submission bundle
            if not filename:
                continue
            skip_exts = (".jpg", ".jpeg", ".png", ".gif", ".css", ".js", ".txt")
            if any(filename.lower().endswith(e) for e in skip_exts):
                continue

            items.append({"name": filename, "type": exhibit_type})

        return items

    # ------------------------------------------------------------------
    # EXHIBIT CLASSIFICATION
    # ------------------------------------------------------------------
    @staticmethod
    def _classify_exhibit(item: dict) -> Optional[str]:
        """
        Return "Earnings Transcript", "Press Release", or None.
        """
        name = item.get("name", "").lower()
        exhibit_type = item.get("type", "")

        if any(kw in name for kw in _TRANSCRIPT_KEYWORDS):
            return "Earnings Transcript"

        if exhibit_type in _PRESSRELEASE_EXHIBIT_TYPES:
            return "Press Release"

        return None

    # ------------------------------------------------------------------
    # DOWNLOAD + INGEST
    # ------------------------------------------------------------------
    def _download_exhibit(
        self,
        ticker: str,
        cik_padded: str,
        accession: str,
        filename: str,
    ) -> Optional[Path]:
        url = _EXHIBIT_URL.format(
            cik=self._bare_cik(cik_padded),
            accession=accession,
            filename=filename,
        )
        content = self._get_bytes(url)
        if not content:
            return None

        out_dir = self.download_dir / ticker
        out_dir.mkdir(exist_ok=True)
        safe_name = filename.replace("/", "_").replace("\\", "_")
        out_path = out_dir / f"{accession}_{safe_name}"

        try:
            out_path.write_bytes(content)
            return out_path
        except Exception as e:
            logger.warning("Failed to save exhibit %s: %s", out_path, e)
            return None

    # ------------------------------------------------------------------
    # PER-COMPANY PIPELINE
    # ------------------------------------------------------------------
    def _ingest_one_company(self, ticker: str, days_back: int) -> dict:
        """Full pipeline for one ticker. Never raises."""
        cfg          = COMPANIES.get(ticker, {})
        short_name   = cfg.get("name", ticker).split()[0]  # "Flex" not "Flex Ltd"

        stats = {
            "ticker":            ticker,
            "filings_checked":   0,
            "exhibits_ingested": 0,
            "errors":            0,
        }

        try:
            eight_ks = self._recent_8k_filings(ticker, days_back)
        except Exception as e:
            logger.error("[TranscriptIngester] %s: failed to list 8-Ks: %s", ticker, e)
            stats["errors"] += 1
            return stats

        for filing in eight_ks:
            stats["filings_checked"] += 1
            accession        = filing["accession"]
            cik_padded       = filing["cik_padded"]
            period_of_report = filing.get("period_of_report", "")

            try:
                items = self._filing_index(cik_padded, accession)
            except Exception as e:
                logger.warning("[TranscriptIngester] %s/%s index error: %s", ticker, accession, e)
                stats["errors"] += 1
                continue

            for item in items:
                filename = item.get("name", "")
                if not filename or filename.endswith("/"):
                    continue  # skip directories

                filing_type = self._classify_exhibit(item)
                if filing_type is None:
                    continue

                exhibit_id = f"{ticker}_{accession}_{filename}"
                if exhibit_id in self.ingested:
                    continue

                try:
                    path = self._download_exhibit(ticker, cik_padded, accession, filename)
                    if not path:
                        stats["errors"] += 1
                        continue

                    fy_label, q_label = _infer_fiscal_period(period_of_report, ticker)

                    chunks = process_filing(
                        filepath=path,
                        company=short_name,
                        filing_type=filing_type,
                        fiscal_year=fy_label,
                        quarter=q_label,
                    )

                    self.ingested[exhibit_id] = str(path)
                    self._save_tracking()
                    stats["exhibits_ingested"] += 1

                    logger.info(
                        "[TranscriptIngester] %s: ingested %s (%s %s %s, %d chunks)",
                        ticker, filename, filing_type, fy_label, q_label, chunks,
                    )
                except Exception as e:
                    logger.error(
                        "[TranscriptIngester] %s/%s/%s: %s", ticker, accession, filename, e
                    )
                    stats["errors"] += 1

        return stats

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    def check_all_companies(self, days_back: int = 90) -> dict:
        """
        Run the full ingestion pipeline for all tracked companies.
        Each company is isolated — one failure never blocks others.
        """
        total = {
            "companies_checked":  0,
            "exhibits_ingested":  0,
            "errors":             0,
            "per_company":        {},
        }

        for ticker in COMPANIES:
            logger.info("[TranscriptIngester] Checking %s...", ticker)
            try:
                stats = self._ingest_one_company(ticker, days_back)
            except Exception as e:
                logger.error("[TranscriptIngester] Unexpected error for %s: %s", ticker, e)
                stats = {
                    "ticker": ticker,
                    "filings_checked": 0,
                    "exhibits_ingested": 0,
                    "errors": 1,
                }

            total["companies_checked"]  += 1
            total["exhibits_ingested"]  += stats["exhibits_ingested"]
            total["errors"]             += stats["errors"]
            total["per_company"][ticker] = stats

        logger.info(
            "[TranscriptIngester] Complete — %d ingested, %d errors, %d companies",
            total["exhibits_ingested"], total["errors"], total["companies_checked"],
        )
        return total

    def get_stats(self) -> dict:
        """Return counts of already-ingested exhibits."""
        by_ticker: dict[str, int] = {}
        for exhibit_id in self.ingested:
            ticker = exhibit_id.split("_")[0]
            by_ticker[ticker] = by_ticker.get(ticker, 0) + 1

        return {
            "total_ingested": len(self.ingested),
            "by_ticker":      by_ticker,
            "tracking_file":  str(self.tracking_file),
        }
