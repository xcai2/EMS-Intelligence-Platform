"""
Automated SEC filing downloader using EDGAR API.
Downloads new 10-K, 10-Q, and 8-K filings for tracked companies.
"""
import httpx
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from backend.core.config import COMPANIES, SEC_USER_AGENT, DATA_DIR


# SEC EDGAR API endpoints
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}"

# ---------------------------------------------------------------------------
# FISCAL PERIOD HELPER
# ---------------------------------------------------------------------------
_FISCAL_YEAR_END_MONTH: dict[str, int] = {
    "FLEX": 3, "JBL": 8, "CLS": 12, "BHE": 12, "SANM": 9, "PLXS": 9,
}


def _infer_fiscal_period(period_of_report: str, ticker: str) -> tuple[str, str]:
    """
    Derive fiscal year label and quarter from a period-end date string and ticker.
    Returns ("FY25", "Q3") style labels, or ("Unknown", "") on failure.
    """
    if not period_of_report or ticker not in _FISCAL_YEAR_END_MONTH:
        return "Unknown", ""
    try:
        dt = datetime.strptime(period_of_report, "%Y-%m-%d")
    except ValueError:
        return "Unknown", ""

    fy_end = _FISCAL_YEAR_END_MONTH[ticker]
    fy_year = dt.year if dt.month <= fy_end else dt.year + 1
    fy_label = f"FY{str(fy_year)[-2:]}"

    fy_start_month = fy_end % 12 + 1
    months_into_fy = (dt.month - fy_start_month) % 12
    q_label = f"Q{months_into_fy // 3 + 1}"

    return fy_label, q_label


class SECDownloader:
    """Downloads SEC filings from EDGAR."""
    
    def __init__(self):
        self.headers = {
            "User-Agent": SEC_USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
        }
        self.download_dir = DATA_DIR / "sec_filings"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.tracking_file = self.download_dir / "downloaded_filings.json"
        self.downloaded = self._load_tracking()
    
    def _load_tracking(self) -> dict:
        """Load tracking of already downloaded filings."""
        if self.tracking_file.exists():
            with open(self.tracking_file) as f:
                return json.load(f)
        return {}
    
    def _save_tracking(self):
        """Save tracking of downloaded filings."""
        with open(self.tracking_file, "w") as f:
            json.dump(self.downloaded, f, indent=2)
    
    def _format_cik(self, cik: str) -> str:
        """Format CIK to 10 digits with leading zeros."""
        return cik.lstrip("0").zfill(10)
    
    async def get_company_filings(
        self,
        ticker: str,
        filing_types: list[str] = ["10-K", "10-Q", "8-K"],
        days_back: int = 90,
    ) -> list[dict]:
        """
        Get recent filings for a company.
        
        Args:
            ticker: Company ticker
            filing_types: Types of filings to look for
            days_back: How many days back to check
            
        Returns:
            List of filing metadata
        """
        company = COMPANIES.get(ticker)
        if not company:
            print(f"Unknown ticker: {ticker}")
            return []
        
        cik = self._format_cik(company["cik"])
        url = EDGAR_SUBMISSIONS_URL.format(cik=cik)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers, timeout=30.0)
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            print(f"Error fetching filings for {ticker}: {e}")
            return []
        
        # Parse recent filings
        filings = []
        recent = data.get("filings", {}).get("recent", {})
        
        if not recent:
            return []
        
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        forms        = recent.get("form", [])
        dates        = recent.get("filingDate", [])
        accessions   = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])
        periods      = recent.get("periodOfReport", [])

        for i in range(len(forms)):
            form = forms[i]
            if form not in filing_types:
                continue

            filing_date = datetime.strptime(dates[i], "%Y-%m-%d")
            if filing_date < cutoff_date:
                continue

            accession  = accessions[i].replace("-", "")
            filing_id  = f"{ticker}_{form}_{dates[i]}_{accession}"
            period_of_report = periods[i] if i < len(periods) else ""
            fy_label, q_label = _infer_fiscal_period(period_of_report, ticker)

            filings.append({
                "ticker":             ticker,
                "company":            company["name"],
                "cik":                cik,
                "form":               form,
                "filing_date":        dates[i],
                "accession":          accession,
                "accession_formatted": accessions[i],
                "primary_doc":        primary_docs[i],
                "description":        descriptions[i] if i < len(descriptions) else "",
                "filing_id":          filing_id,
                "already_downloaded": filing_id in self.downloaded,
                "period_of_report":   period_of_report,
                # Aliases expected by process_new_filings():
                "filing_type":        form,
                "filepath":           "",                          # set after download
                "company_short":      company["name"].split()[0],  # "Flex" not "Flex Ltd"
                "fiscal_year":        fy_label,
                "quarter":            q_label,
            })
        
        return filings
    
    async def download_filing(self, filing: dict) -> Optional[Path]:
        """
        Download a filing document.
        
        Args:
            filing: Filing metadata dict
            
        Returns:
            Path to downloaded file, or None if failed
        """
        if filing["filing_id"] in self.downloaded:
            print(f"Already downloaded: {filing['filing_id']}")
            return Path(self.downloaded[filing["filing_id"]])
        
        # Create company directory
        company_dir = self.download_dir / filing["ticker"]
        company_dir.mkdir(exist_ok=True)
        
        # Build download URL
        url = EDGAR_FILING_URL.format(
            cik=filing["cik"].lstrip("0"),
            accession=filing["accession"],
            filename=filing["primary_doc"],
        )
        
        # Determine output filename
        ext = Path(filing["primary_doc"]).suffix or ".htm"
        filename = f"{filing['form']}_{filing['filing_date']}{ext}"
        output_path = company_dir / filename
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers, timeout=60.0)
                response.raise_for_status()
                
                with open(output_path, "wb") as f:
                    f.write(response.content)
            
            # Track download
            self.downloaded[filing["filing_id"]] = str(output_path)
            self._save_tracking()
            
            print(f"Downloaded: {filing['ticker']} {filing['form']} ({filing['filing_date']})")
            return output_path
            
        except Exception as e:
            print(f"Error downloading {filing['filing_id']}: {e}")
            return None
    
    async def check_and_download_new_filings(
        self,
        filing_types: list[str] = ["10-K", "10-Q", "8-K"],
        days_back: int = 30,
    ) -> list[dict]:
        """
        Check all tracked companies for new filings and download them.
        
        Returns:
            List of newly downloaded filings
        """
        new_filings = []
        
        for ticker in COMPANIES.keys():
            print(f"\nChecking {ticker} for new filings...")
            filings = await self.get_company_filings(ticker, filing_types, days_back)
            
            for filing in filings:
                if filing["already_downloaded"]:
                    continue
                
                path = await self.download_filing(filing)
                if path:
                    filing["local_path"] = str(path)
                    # Populate aliases that process_new_filings() requires
                    filing["filepath"] = str(path)
                    filing["company"]  = filing["company_short"]
                    new_filings.append(filing)
        
        return new_filings
    
    def get_download_stats(self) -> dict:
        """Get statistics about downloaded filings."""
        stats = {
            "total_downloaded": len(self.downloaded),
            "by_company": {},
            "by_form": {},
        }
        
        for filing_id in self.downloaded:
            parts = filing_id.split("_")
            if len(parts) >= 2:
                ticker, form = parts[0], parts[1]
                stats["by_company"][ticker] = stats["by_company"].get(ticker, 0) + 1
                stats["by_form"][form] = stats["by_form"].get(form, 0) + 1
        
        return stats


# Sync wrapper functions for use in scheduler
def check_new_filings_sync(
    filing_types: list[str] = ["10-K", "10-Q", "8-K"],
    days_back: int = 30,
) -> list[dict]:
    """Synchronous wrapper for checking and downloading new filings."""
    import asyncio
    
    downloader = SECDownloader()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            downloader.check_and_download_new_filings(filing_types, days_back)
        )
    finally:
        loop.close()


async def download_all_recent_filings():
    """Download all recent filings for all companies."""
    downloader = SECDownloader()
    return await downloader.check_and_download_new_filings(days_back=365)
