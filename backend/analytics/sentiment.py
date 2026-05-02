"""
Sentiment analysis for SEC filings and earnings documents.
Uses FinBERT (ProsusAI/finbert) — a BERT model fine-tuned on financial text.
Falls back to Loughran-McDonald lexicon if the model is unavailable.
"""
import re
import logging
from collections import Counter
from typing import Optional

from backend.core.config import TRACKED_COMPANY_NAMES
from backend.rag.retriever import search_documents, get_company_documents
from backend.core.cache import analytics_cache, cached

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Filing-type weights — earnings transcripts carry the most signal because
# management speaks directly and unscripted about strategy and outlook.
# ---------------------------------------------------------------------------
FILING_WEIGHTS: dict[str, float] = {
    "Earnings Transcript": 2.0,
    "Earnings Call":       2.0,
    "10-K":                1.5,
    "Annual Report":       1.5,
    "Press Release":       1.2,
    "8-K":                 1.1,
    "10-Q":                1.0,
}
_DEFAULT_FILING_WEIGHT = 1.0


def _filing_weight(filing_type: str) -> float:
    return FILING_WEIGHTS.get(filing_type, _DEFAULT_FILING_WEIGHT)


# ---------------------------------------------------------------------------
# FinBERT setup — loaded once at module level and reused across all calls
# ---------------------------------------------------------------------------
_finbert_pipeline = None

def _get_finbert():
    global _finbert_pipeline
    if _finbert_pipeline is None:
        try:
            from transformers import pipeline
            _finbert_pipeline = pipeline(
                "text-classification",
                model="ProsusAI/finbert",
                top_k=3,
                truncation=True,
                max_length=512,
            )
            logger.info("FinBERT loaded successfully")
        except Exception as e:
            logger.warning("FinBERT failed to load: %s — will use lexicon fallback", e)
    return _finbert_pipeline


# ---------------------------------------------------------------------------
# Loughran-McDonald lexicon — used as fallback only
# ---------------------------------------------------------------------------
POSITIVE_WORDS = {
    "growth", "increase", "improvement", "strong", "positive", "opportunity",
    "success", "successful", "gain", "profit", "profitable", "exceed", "exceeded",
    "outperform", "momentum", "expand", "expansion", "robust", "optimistic",
    "favorable", "benefit", "innovation", "innovative", "leading", "leader",
    "efficient", "efficiency", "progress", "achieve", "achievement", "advance",
    "superior", "excellent", "outstanding", "record", "milestone", "breakthrough",
}

NEGATIVE_WORDS = {
    "decline", "decrease", "loss", "losses", "weak", "weakness", "negative",
    "risk", "risks", "concern", "concerns", "challenge", "challenges", "difficult",
    "difficulty", "adverse", "adversely", "uncertain", "uncertainty", "volatile",
    "volatility", "impair", "impairment", "restructuring", "layoff", "downturn",
    "slowdown", "delay", "delayed", "disappointing", "shortfall", "pressure",
    "headwind", "headwinds", "litigation", "lawsuit", "penalty", "penalties",
}

AI_INVESTMENT_WORDS = {
    "ai", "artificial intelligence", "machine learning", "deep learning", "neural",
    "gpu", "data center", "datacenter", "hyperscale", "cloud", "generative ai",
    "llm", "large language model", "inference", "training", "compute", "nvidia",
}


def analyze_lexicon_sentiment(text: str) -> dict:
    """Public alias kept for backwards compatibility."""
    return _lexicon_sentiment(text)


async def analyze_sentiment_llm(text: str, context: str = "") -> dict:
    """Kept for backwards compatibility — now delegates to FinBERT."""
    return _finbert_sentiment(text)


def _lexicon_sentiment(text: str) -> dict:
    """Loughran-McDonald lexicon fallback. Returns score in [-1, 1]."""
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    total = pos + neg
    score = (pos - neg) / total if total > 0 else 0.0
    ai_count = sum(1 for phrase in AI_INVESTMENT_WORDS if phrase in text_lower)
    return {
        "sentiment_score": round(score, 3),
        "positive_words": pos,
        "negative_words": neg,
        "ai_mentions": ai_count,
        "method": "lexicon",
    }


def _chunk_text(text: str, max_tokens: int = 500) -> list[str]:
    """Split text into chunks that fit within FinBERT's 512-token limit (~500 words)."""
    words = text.split()
    return [
        " ".join(words[i: i + max_tokens])
        for i in range(0, len(words), max_tokens)
    ]


def _finbert_sentiment(text: str) -> dict:
    """
    Run FinBERT over the text in chunks and aggregate scores.
    Returns sentiment_score in [-1, 1] = positive_prob - negative_prob.
    """
    pipe = _get_finbert()
    if pipe is None:
        return _lexicon_sentiment(text)

    chunks = _chunk_text(text, max_tokens=450)
    if not chunks:
        return {"sentiment_score": 0.0, "method": "finbert"}

    pos_scores, neg_scores, neu_scores = [], [], []

    for chunk in chunks:
        try:
            results = pipe(chunk)[0]  # list of {label, score}
            label_map = {r["label"]: r["score"] for r in results}
            pos_scores.append(label_map.get("positive", 0.0))
            neg_scores.append(label_map.get("negative", 0.0))
            neu_scores.append(label_map.get("neutral", 0.0))
        except Exception as e:
            logger.debug("FinBERT chunk error: %s", e)

    if not pos_scores:
        return {"sentiment_score": 0.0, "method": "finbert"}

    avg_pos = sum(pos_scores) / len(pos_scores)
    avg_neg = sum(neg_scores) / len(neg_scores)
    avg_neu = sum(neu_scores) / len(neu_scores)

    # Score: positive probability minus negative probability → [-1, 1]
    score = round(avg_pos - avg_neg, 3)

    # Count AI mentions via simple scan (FinBERT doesn't classify this)
    text_lower = text.lower()
    ai_count = sum(1 for phrase in AI_INVESTMENT_WORDS if phrase in text_lower)

    return {
        "sentiment_score": score,
        "positive_prob": round(avg_pos, 3),
        "negative_prob": round(avg_neg, 3),
        "neutral_prob": round(avg_neu, 3),
        "chunks_analyzed": len(pos_scores),
        "ai_mentions": ai_count,
        "method": "finbert",
    }


@cached(analytics_cache, prefix="sentiment")
def analyze_company_sentiment(company: str, n_chunks: int = 20) -> dict:
    """
    Analyze overall sentiment for a company using FinBERT.
    Earnings transcripts are weighted 2× vs standard filings.
    Falls back to lexicon if FinBERT is unavailable.
    """
    docs = search_documents(
        query=f"{company} outlook strategy growth investment",
        company_filter=company,
        n_results=n_chunks,
    )

    if not docs:
        return {"error": f"No documents found for {company}"}

    # Weighted aggregation: run FinBERT per document so each doc's filing-type
    # weight applies to its own score rather than diluting into a combined blob.
    total_weight = 0.0
    weighted_pos = weighted_neg = weighted_neu = 0.0
    total_ai_mentions = 0
    total_chunks = 0
    filing_types: Counter = Counter()
    fiscal_years: Counter = Counter()

    for doc in docs:
        content = doc.get("content")
        if not content:
            continue
        filing_type = doc.get("filing_type", "Unknown")
        w = _filing_weight(filing_type)

        result = _finbert_sentiment(content)
        weighted_pos += result.get("positive_prob", 0.0) * w
        weighted_neg += result.get("negative_prob", 0.0) * w
        weighted_neu += result.get("neutral_prob", 0.0) * w
        total_ai_mentions += result.get("ai_mentions", 0)
        total_chunks += result.get("chunks_analyzed", 1)
        total_weight += w

        filing_types[filing_type] += 1
        fiscal_years[doc.get("fiscal_year", "Unknown")] += 1

    if total_weight == 0:
        return {"error": f"No processable documents for {company}"}

    avg_pos = weighted_pos / total_weight
    avg_neg = weighted_neg / total_weight
    avg_neu = weighted_neu / total_weight

    return {
        "company": company,
        "documents_analyzed": len(docs),
        "filing_types": dict(filing_types),
        "fiscal_years": dict(fiscal_years),
        "sentiment_score": round(avg_pos - avg_neg, 3),
        "positive_prob": round(avg_pos, 3),
        "negative_prob": round(avg_neg, 3),
        "neutral_prob": round(avg_neu, 3),
        "chunks_analyzed": total_chunks,
        "ai_mentions": total_ai_mentions,
        "method": "finbert",
    }


def compare_company_sentiments(companies: list[str] = None) -> list[dict]:
    if companies is None:
        companies = list(TRACKED_COMPANY_NAMES)

    results = []
    for company in companies:
        analysis = analyze_company_sentiment(company)
        analysis.setdefault("company", company)
        results.append(analysis)

    results.sort(
        key=lambda x: x.get("sentiment_score", float("-inf")) if "error" not in x else float("-inf"),
        reverse=True,
    )
    return results


def _weighted_finbert_score(docs: list[dict], meta_key: str = "filing_type") -> dict:
    """Run FinBERT per doc, return filing-type-weighted aggregate sentiment."""
    total_weight = weighted_pos = weighted_neg = 0.0
    ai_mentions = 0
    for doc in docs:
        content = doc.get("content")
        if not content:
            continue
        filing_type = (doc.get("metadata") or {}).get(meta_key, doc.get(meta_key, "Unknown"))
        w = _filing_weight(filing_type)
        result = _finbert_sentiment(content)
        weighted_pos += result.get("positive_prob", 0.0) * w
        weighted_neg += result.get("negative_prob", 0.0) * w
        ai_mentions += result.get("ai_mentions", 0)
        total_weight += w
    if total_weight == 0:
        return {"sentiment_score": 0.0, "method": "finbert"}
    avg_pos = weighted_pos / total_weight
    avg_neg = weighted_neg / total_weight
    return {"sentiment_score": round(avg_pos - avg_neg, 3), "ai_mentions": ai_mentions, "method": "finbert"}


def detect_sentiment_changes(company: str) -> dict:
    docs = get_company_documents(company, limit=100)

    if len(docs) < 20:
        return {"error": "Not enough documents for trend analysis"}

    midpoint = len(docs) // 2
    recent = _weighted_finbert_score(docs[:midpoint], meta_key="filing_type")
    older = _weighted_finbert_score(docs[midpoint:], meta_key="filing_type")

    change = recent["sentiment_score"] - older["sentiment_score"]

    return {
        "company": company,
        "recent_sentiment": recent["sentiment_score"],
        "older_sentiment": older["sentiment_score"],
        "sentiment_change": round(change, 3),
        "trend": "improving" if change > 0.05 else "declining" if change < -0.05 else "stable",
        "recent_ai_focus": recent.get("ai_mentions", 0),
        "older_ai_focus": older.get("ai_mentions", 0),
        "method": recent.get("method", "unknown"),
    }
