"""Company resolver: suggest and resolve company candidates (Phase 3 Part 1).

Two public async functions:

  suggest(query: str) -> list[dict]
    Layered strategy (§5.3.4):
      1. Local registry fuzzy match (ticker, full_name, aliases)
      2. LLM fallback ONLY if len(query) >= 2 AND local results < 3

  resolve(company_name: str, ticker: str, official_website: str = "") -> dict
    LLM-based standardization of a selected candidate; returns a structured
    company object with confidence score and reason.

Return shape for both functions (each candidate):
  {
    "company_name": str,
    "display_name": str,
    "ticker": str,
    "aliases": list[str],
    "official_website": str,
    "official_domain": str,
    "confidence": float,
    "reason": str,
    "source": "local" | "llm",
  }
"""
from __future__ import annotations

import asyncio
import re
import logging
from typing import Optional

from pydantic import BaseModel

from backend.core.llm_client import llm_structured
from backend.news.registry import list_companies

logger = logging.getLogger(__name__)


_STATIC_COMPANY_HINTS: tuple[dict, ...] = (
    {
        "company_name": "Alphabet Inc.",
        "display_name": "Google",
        "ticker": "GOOGL",
        "aliases": ["Google", "GOOG", "GOOGL", "谷歌", "Alphabet"],
        "official_domain": "abc.xyz",
    },
    {
        "company_name": "NVIDIA Corporation",
        "display_name": "NVIDIA",
        "ticker": "NVDA",
        "aliases": ["NVIDIA", "NVDA", "英伟达", "輝達", "Nvidia"],
        "official_domain": "nvidia.com",
    },
    {
        "company_name": "Advanced Micro Devices, Inc.",
        "display_name": "AMD",
        "ticker": "AMD",
        "aliases": ["AMD", "Advanced Micro Devices", "超威", "超微", "AMD公司"],
        "official_domain": "amd.com",
    },
)


# ---------------------------------------------------------------------------
# Local fuzzy matching helpers
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Casefold + strip punctuation for fuzzy comparison while preserving Unicode letters."""
    value = re.sub(r"[^\w\s]", " ", (s or "").casefold(), flags=re.UNICODE)
    value = value.replace("_", " ")
    return re.sub(r"\s+", " ", value).strip()


def _company_to_candidate(company, source: str = "local") -> dict:
    aliases = [a.strip() for a in (company.aliases or "").split(",") if a.strip()]
    domain = company.official_domain or ""
    website = f"https://www.{domain}" if domain else ""
    return {
        "company_name": company.full_name,
        "display_name": company.full_name.split()[0],
        "ticker": company.ticker,
        "aliases": aliases,
        "official_website": website,
        "official_domain": domain,
        "confidence": 1.0,
        "reason": "Matched registered company",
        "source": source,
    }


def _static_hint_to_candidate(entry: dict) -> dict:
    domain = entry.get("official_domain", "")
    return {
        "company_name": entry["company_name"],
        "display_name": entry["display_name"],
        "ticker": entry["ticker"],
        "aliases": list(entry.get("aliases") or []),
        "official_website": f"https://www.{domain}" if domain else "",
        "official_domain": domain,
        "confidence": 0.95,
        "reason": "Matched local public-company alias dictionary",
        "source": "local",
    }


def _local_suggest(query: str) -> list[dict]:
    """Search registered companies and a small public-company alias dictionary."""
    q = _normalize(query)
    if not q:
        return []

    results: list[dict] = []
    seen: set[str] = set()

    for company in list_companies():
        ticker = company.ticker.upper()
        if ticker in seen:
            continue

        ticker_lower = ticker.lower()
        full_lower = _normalize(company.full_name)

        # Ticker: exact substring or prefix
        if q == ticker_lower or ticker_lower.startswith(q) or q in ticker_lower:
            results.append(_company_to_candidate(company))
            seen.add(ticker)
            continue

        # Full name: substring
        if q in full_lower:
            results.append(_company_to_candidate(company))
            seen.add(ticker)
            continue

        # Aliases: substring
        if company.aliases:
            for alias in company.aliases.split(","):
                alias_norm = _normalize(alias.strip())
                if alias_norm and q in alias_norm:
                    results.append(_company_to_candidate(company))
                    seen.add(ticker)
                    break

    for entry in _STATIC_COMPANY_HINTS:
        ticker = entry["ticker"].upper()
        if ticker in seen:
            continue

        haystacks = [
            _normalize(entry.get("company_name", "")),
            _normalize(entry.get("display_name", "")),
            _normalize(entry.get("ticker", "")),
        ] + [_normalize(alias) for alias in entry.get("aliases") or []]

        if any(h and (q == h or h.startswith(q) or q in h) for h in haystacks):
            results.append(_static_hint_to_candidate(entry))
            seen.add(ticker)

    return results


# ---------------------------------------------------------------------------
# LLM suggest fallback
# ---------------------------------------------------------------------------

async def _llm_suggest(query: str) -> list[dict]:
    """Ask LLM for company candidates when local registry returns fewer than 3."""

    class _Candidate(BaseModel):
        company_name: str
        display_name: str
        ticker: str
        official_domain: str
        confidence: float
        reason: str

    class _SuggestSchema(BaseModel):
        candidates: list[_Candidate]

    result: Optional[_SuggestSchema] = await asyncio.to_thread(
        llm_structured,
        messages=[{
            "role": "user",
            "content": f"Suggest up to 5 publicly listed companies matching this input: {query}",
        }],
        system=(
            "You are a public company identifier. "
            "Return JSON with a 'candidates' list. Each item must have: "
            "company_name (official full legal name), "
            "display_name (common short name), "
            "ticker (exchange ticker symbol only, no exchange prefix), "
            "official_domain (domain only, no https://, e.g. nvidia.com), "
            "confidence (float 0.0-1.0), "
            "reason (one short sentence). "
            "Only include real publicly listed companies. "
            "Do not invent tickers or domains."
        ),
        model_key="fast",
        schema=_SuggestSchema,
    )

    if not result:
        return []

    candidates: list[dict] = []
    for c in result.candidates:
        ticker = c.ticker.upper().split(":")[-1]  # strip exchange prefix if LLM adds one
        domain = (c.official_domain or "").lstrip("https://").lstrip("http://").lstrip("www.").split("/")[0]
        candidates.append({
            "company_name": c.company_name,
            "display_name": c.display_name,
            "ticker": ticker,
            "aliases": [],
            "official_website": f"https://www.{domain}" if domain else "",
            "official_domain": domain,
            "confidence": max(0.0, min(1.0, float(c.confidence))),
            "reason": c.reason,
            "source": "llm",
        })

    return candidates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def suggest(query: str) -> list[dict]:
    """Return candidate companies matching the query.

    Strategy (§5.3.4):
      - len(query) < 2: return [] immediately, no LLM call
      - local results >= 3: return local results, no LLM call
      - otherwise: merge local + LLM results (local first, dedup by ticker)
    """
    query = query.strip()
    if len(query) < 2:
        return []

    local_results = _local_suggest(query)

    if len(local_results) >= 3:
        return local_results[:8]

    # LLM fallback
    try:
        llm_results = await _llm_suggest(query)
    except Exception as exc:
        logger.warning("LLM suggest failed for %r: %s", query, exc)
        llm_results = []

    seen = {r["ticker"] for r in local_results}
    merged = list(local_results)
    for r in llm_results:
        if r["ticker"] not in seen:
            merged.append(r)
            seen.add(r["ticker"])

    return merged[:8]


async def resolve(
    company_name: str,
    ticker: str,
    official_website: str = "",
) -> dict:
    """Standardize a selected candidate into a full company object with confidence.

    Uses LLM to validate ticker, fill official_website, generate aliases.
    Returns the structured company object per §5.4 schema.
    """

    class _ResolveSchema(BaseModel):
        company_name: str
        display_name: str
        ticker: str
        aliases: list[str]
        official_website: str
        official_domain: str
        confidence: float
        reason: str

    hint = f"company_name={company_name}, ticker={ticker}"
    if official_website:
        hint += f", official_website={official_website}"

    result: Optional[_ResolveSchema] = await asyncio.to_thread(
        llm_structured,
        messages=[{
            "role": "user",
            "content": f"Standardize this public company: {hint}",
        }],
        system=(
            "You are a public company standardization assistant. "
            "Given a company hint, return a structured JSON object. Fields: "
            "company_name (full legal name), "
            "display_name (common short name), "
            "ticker (exchange ticker only, no prefix), "
            "aliases (list of known names/abbreviations), "
            "official_website (full https:// URL to the IR or main site), "
            "official_domain (domain only, e.g. nvidia.com), "
            "confidence (float 0.0-1.0 — how certain you are this is a real listed company), "
            "reason (one sentence). "
            "Do not invent tickers or domains. "
            "If uncertain, set confidence < 0.60 and explain in reason."
        ),
        model_key="fast",
        schema=_ResolveSchema,
    )

    if not result:
        return {
            "company_name": company_name,
            "display_name": company_name.split()[0] if company_name else ticker,
            "ticker": ticker.upper(),
            "aliases": [],
            "official_website": official_website,
            "official_domain": "",
            "confidence": 0.0,
            "reason": "LLM resolve failed — could not standardize company info.",
        }

    domain = (result.official_domain or "").lstrip("https://").lstrip("http://").lstrip("www.").split("/")[0]
    return {
        "company_name": result.company_name,
        "display_name": result.display_name,
        "ticker": result.ticker.upper().split(":")[-1],
        "aliases": result.aliases,
        "official_website": result.official_website,
        "official_domain": domain,
        "confidence": max(0.0, min(1.0, float(result.confidence))),
        "reason": result.reason,
    }
