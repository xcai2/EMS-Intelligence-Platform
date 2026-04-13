"""
Key Quote Extractor service (Component 6).

Queries ChromaDB for earnings transcript documents, sends them to Claude
using the prescribed executive-intelligence prompt, and persists the
5 most strategically relevant Q&A pairs per earnings call in SQLite.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from backend.analyst_view.db import get_key_quotes, save_key_quotes
from backend.core.llm_client import llm_structured

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class QuoteItem(BaseModel):
    analyst_name: Optional[str] = None
    question: str
    management_response: str
    theme: str          # CapEx & Investment | AI/Data Center | Geographic Expansion |
                        # Margins & Profitability | Customer Concentration | Supply Chain
    strategic_implication: str


class QuotesExtraction(BaseModel):
    quotes: list[QuoteItem]


VALID_THEMES = {
    "CapEx & Investment",
    "AI/Data Center",
    "Geographic Expansion",
    "Margins & Profitability",
    "Customer Concentration",
    "Supply Chain",
}

COMPANIES = {
    "FLEX": "Flex Ltd",
    "JBL":  "Jabil",
    "CLS":  "Celestica",
    "BHE":  "Benchmark Electronics",
    "SANM": "Sanmina",
    "PLXS": "Plexus",
    "AMZN": "Amazon",
    "MSFT": "Microsoft",
    "GOOGL":"Alphabet",
    "META": "Meta",
    "AAPL": "Apple",
    "ORCL": "Oracle",
}

# Short names as stored in ChromaDB metadata `company` field
_CHROMA_NAME: dict[str, str] = {
    "FLEX": "Flex",
    "JBL":  "Jabil",
    "CLS":  "Celestica",
    "BHE":  "Benchmark",
    "SANM": "Sanmina",
    "PLXS": "Plexus",
    "AMZN": "Amazon",
    "MSFT": "Microsoft",
    "GOOGL":"Alphabet",
    "META": "Meta",
}


# ---------------------------------------------------------------------------
# ChromaDB transcript search (queries capex_docs directly — no openai dep)
# ---------------------------------------------------------------------------

def _search_transcripts(ticker: str, max_chunks: int = 20) -> str:
    """
    Pull strategic document chunks for a company from the main capex_docs
    ChromaDB collection, filtered by the `company` metadata field.
    Returns joined text ready to send to Claude.
    """
    chroma_name = _CHROMA_NAME.get(ticker.upper())
    if not chroma_name:
        return ""
    try:
        from backend.core.database import get_chroma_client, embed_text
        client = get_chroma_client()
        col = client.get_collection("capex_docs")

        # Embed a strategic query and retrieve similar chunks
        query_text = (
            f"{chroma_name} strategy capital expenditure revenue growth "
            "margins outlook risk factors management discussion"
        )
        query_embedding = embed_text(query_text)

        results = col.query(
            query_embeddings=[query_embedding],
            n_results=max_chunks,
            where={"company": chroma_name},
            include=["documents", "metadatas"],
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        parts = []
        for doc, meta in zip(docs, metas):
            if not doc or not doc.strip():
                continue
            filing = meta.get("filing_type", "")
            fy = meta.get("fiscal_year", "")
            header = f"[{chroma_name} {filing} {fy}]" if (filing or fy) else f"[{chroma_name}]"
            parts.append(f"{header}\n{doc[:800]}")

        return "\n\n---\n\n".join(parts)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Extract quotes via Claude
# ---------------------------------------------------------------------------

async def extract_quotes_for_company(
    ticker: str,
    transcript_text: str = "",
    source_url: str = "",
    earnings_date: str = "",
) -> dict:
    """
    Extract the 5 most strategically relevant analyst Q&A pairs from a
    transcript (supplied or fetched from ChromaDB).
    """
    company_name = COMPANIES.get(ticker.upper(), ticker)

    # Fall back to ChromaDB if no transcript supplied
    if not transcript_text.strip():
        transcript_text = await asyncio.to_thread(_search_transcripts, ticker)

    if not transcript_text.strip():
        return {
            "company": company_name,
            "ticker": ticker.upper(),
            "quotes": [],
            "warning": "No documents found in ChromaDB for this company.",
        }

    extracted: QuotesExtraction | None = await asyncio.to_thread(
        llm_structured,
        messages=[{
            "role": "user",
            "content": (
                f"Analyze these strategic filings excerpts from {company_name} "
                f"and extract the 5 most strategically important management statements "
                f"or Q&A exchanges relevant to CapEx, AI, growth, margins, or supply chain:\n\n{transcript_text[:6000]}"
            ),
        }],
        system=(
            "You are a strategic intelligence analyst for Flex, a global contract manufacturer. "
            "Extract 5 key strategic insights from these company filings. "
            "For each insight: "
            "1) analyst_name: set to 'Management' or the specific executive if named, "
            "2) question: a concise headline summarising the strategic topic (1 sentence), "
            "3) management_response: the key statement or data point from the filing (2-3 sentences), "
            "4) theme: one of: CapEx & Investment, AI/Data Center, "
            "Geographic Expansion, Margins & Profitability, Customer Concentration, Supply Chain, "
            "5) strategic_implication: what this means for Flex's competitive position (1 sentence). "
            "Return JSON with a 'quotes' list, each with fields: "
            "analyst_name, question, management_response, theme, strategic_implication."
        ),
        model_key="main",
        schema=QuotesExtraction,
        max_tokens=3000,
    )

    if not extracted:
        return {
            "company": company_name,
            "ticker": ticker.upper(),
            "quotes": [],
            "warning": "LLM extraction failed.",
        }

    now = datetime.now(timezone.utc).isoformat()
    rows_to_save = []
    quotes_out = []
    for q in extracted.quotes:
        theme = q.theme if q.theme in VALID_THEMES else "Supply Chain"
        row = {
            "company": company_name,
            "ticker": ticker.upper(),
            "analyst_name": q.analyst_name or "Unnamed analyst",
            "question": q.question,
            "management_response": q.management_response,
            "theme": theme,
            "strategic_implication": q.strategic_implication,
            "earnings_date": earnings_date or now[:10],
            "source_url": source_url,
            "created_at": now,
        }
        rows_to_save.append(row)
        quotes_out.append(row)

    if rows_to_save:
        save_key_quotes(rows_to_save)

    return {
        "company": company_name,
        "ticker": ticker.upper(),
        "quotes": quotes_out,
    }


# ---------------------------------------------------------------------------
# Read quotes from SQLite
# ---------------------------------------------------------------------------

def fetch_key_quotes(
    company: str | None = None,
    theme: str | None = None,
    days: int = 90,
) -> list[dict]:
    rows = get_key_quotes(company=company, theme=theme, days=days)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Divergence flags (Component 8) — derived from existing company intel
# ---------------------------------------------------------------------------

def compute_divergence_flags(companies: list[dict]) -> list[dict]:
    """
    Flag analyst price-target outliers relative to consensus.
    Derives data from the recent_actions strings already in company intel.
    Threshold: 20% above or below consensus PT.
    """
    flags: list[dict] = []
    import re

    for c in companies:
        consensus_pt_str = c.get("price_target", "—")
        if consensus_pt_str == "—":
            continue
        # Extract numeric consensus PT
        m = re.search(r"\$([\d.]+)", consensus_pt_str)
        if not m:
            continue
        consensus_pt = float(m.group(1))

        # Scan recent_actions for individual analyst PTs
        for action in (c.get("recent_actions") or []):
            pt_match = re.search(r"\$([\d.]+)", action)
            if not pt_match:
                continue
            analyst_pt = float(pt_match.group(1))
            divergence_pct = (analyst_pt - consensus_pt) / consensus_pt * 100
            if abs(divergence_pct) >= 20:
                direction = "Bull outlier" if divergence_pct > 0 else "Bear outlier"
                # Extract analyst name from beginning of action string
                analyst_name = action.split(":")[0].split("raised")[0].split("cut")[0].strip()
                flags.append({
                    "analyst": analyst_name or "Unknown analyst",
                    "company": c.get("company", ""),
                    "ticker": c.get("ticker", ""),
                    "analyst_pt": f"${analyst_pt:.0f}",
                    "consensus_pt": f"${consensus_pt:.0f}",
                    "divergence_pct": round(divergence_pct, 1),
                    "direction": direction,
                })

    flags.sort(key=lambda x: abs(x["divergence_pct"]), reverse=True)
    return flags[:10]
