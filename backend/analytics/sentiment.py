"""
Sentiment analysis for SEC filings and earnings documents.
Uses a combination of financial lexicon and LLM for nuanced analysis.
"""
import re
from collections import Counter
from typing import Optional
from openai import OpenAI

from backend.core.config import OPENAI_API_KEY, LLM_MODEL, TRACKED_COMPANY_NAMES
from backend.rag.retriever import search_documents, get_company_documents
from backend.core.cache import analytics_cache, cached


# Financial sentiment lexicons (Loughran-McDonald inspired)
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

UNCERTAINTY_WORDS = {
    "may", "might", "could", "possibly", "uncertain", "uncertainty", "depends",
    "contingent", "subject to", "if", "whether", "approximately", "estimate",
    "estimated", "expect", "expected", "anticipate", "anticipated", "believe",
    "intend", "plan", "planned", "potential", "potentially", "likely", "unlikely",
}

AI_INVESTMENT_WORDS = {
    "ai", "artificial intelligence", "machine learning", "deep learning", "neural",
    "gpu", "data center", "datacenter", "hyperscale", "cloud", "generative ai",
    "llm", "large language model", "inference", "training", "compute", "nvidia",
}


def analyze_lexicon_sentiment(text: str) -> dict:
    """
    Analyze sentiment using financial lexicon.
    
    Returns:
        Dict with sentiment scores and word counts
    """
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    word_count = len(words)
    
    positive_count = sum(1 for w in words if w in POSITIVE_WORDS)
    negative_count = sum(1 for w in words if w in NEGATIVE_WORDS)
    uncertainty_count = sum(1 for w in words if w in UNCERTAINTY_WORDS)
    ai_count = sum(1 for phrase in AI_INVESTMENT_WORDS if phrase in text_lower)
    
    # Calculate sentiment score (-1 to 1)
    total_sentiment_words = positive_count + negative_count
    if total_sentiment_words > 0:
        sentiment_score = (positive_count - negative_count) / total_sentiment_words
    else:
        sentiment_score = 0.0
    
    # Normalize counts per 1000 words
    normalize = lambda x: round(x / word_count * 1000, 2) if word_count > 0 else 0
    
    return {
        "sentiment_score": round(sentiment_score, 3),
        "positive_words": positive_count,
        "negative_words": negative_count,
        "uncertainty_words": uncertainty_count,
        "ai_mentions": ai_count,
        "positive_per_1k": normalize(positive_count),
        "negative_per_1k": normalize(negative_count),
        "word_count": word_count,
    }


async def analyze_sentiment_llm(text: str, context: str = "") -> dict:
    """
    Use OpenAI to analyze sentiment with nuanced understanding.
    
    Args:
        text: Text to analyze
        context: Additional context (e.g., company name, filing type)
        
    Returns:
        Dict with LLM sentiment analysis
    """
    if not OPENAI_API_KEY:
        return {"error": "OPENAI_API_KEY not set"}
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # Truncate text if too long
    if len(text) > 10000:
        text = text[:10000] + "..."
    
    prompt = f"""Analyze the sentiment of the following financial text. {context}

Text:
{text}

Provide a JSON response with:
1. overall_sentiment: "positive", "negative", or "neutral"
2. sentiment_score: float from -1 (very negative) to 1 (very positive)
3. confidence: float from 0 to 1
4. key_themes: list of 3-5 main themes discussed
5. outlook: "bullish", "bearish", or "neutral" on company prospects
6. ai_focus: "high", "medium", "low", or "none" based on AI/data center discussion
7. risk_level: "high", "medium", or "low" based on risk language
8. brief_summary: 1-2 sentence summary of sentiment

Return only valid JSON, no other text."""

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Try to parse JSON
        import json
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = re.sub(r'^```json?\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)
        
        result = json.loads(response_text)
        result["tokens_used"] = response.usage.total_tokens
        return result
        
    except Exception as e:
        return {"error": str(e)}


@cached(analytics_cache, prefix="sentiment")
def analyze_company_sentiment(company: str, n_chunks: int = 20) -> dict:
    """
    Analyze overall sentiment for a company based on recent documents.
    
    Args:
        company: Company name
        n_chunks: Number of document chunks to analyze
        
    Returns:
        Aggregated sentiment analysis
    """
    # Get relevant documents
    docs = search_documents(
        query=f"{company} outlook strategy growth investment",
        company_filter=company,
        n_results=n_chunks,
    )
    
    if not docs:
        return {"error": f"No documents found for {company}"}
    
    # Combine text for analysis
    combined_text = " ".join([doc["content"] for doc in docs])
    
    # Run lexicon analysis
    lexicon_result = analyze_lexicon_sentiment(combined_text)
    
    # Get document metadata
    filing_types = Counter(doc.get("filing_type", "Unknown") for doc in docs)
    fiscal_years = Counter(doc.get("fiscal_year", "Unknown") for doc in docs)
    
    return {
        "company": company,
        "documents_analyzed": len(docs),
        "filing_types": dict(filing_types),
        "fiscal_years": dict(fiscal_years),
        **lexicon_result,
    }


def compare_company_sentiments(companies: list[str] = None) -> list[dict]:
    """
    Compare sentiment across multiple companies.
    
    Args:
        companies: List of company names (defaults to all tracked)
        
    Returns:
        List of sentiment analyses for comparison
    """
    if companies is None:
        companies = list(TRACKED_COMPANY_NAMES)
    
    results = []
    for company in companies:
        analysis = analyze_company_sentiment(company)
        analysis.setdefault("company", company)
        results.append(analysis)
    
    # Sort by sentiment score
    results.sort(
        key=lambda x: x.get("sentiment_score", float("-inf")) if "error" not in x else float("-inf"),
        reverse=True,
    )
    
    return results


def detect_sentiment_changes(company: str) -> dict:
    """
    Detect significant sentiment changes over time for a company.
    
    Note: This is a simplified version. Full implementation would
    require storing historical sentiment scores.
    """
    # Get recent vs older documents
    docs = get_company_documents(company, limit=100)
    
    if len(docs) < 20:
        return {"error": "Not enough documents for trend analysis"}
    
    # Split into recent and older
    midpoint = len(docs) // 2
    recent_docs = docs[:midpoint]
    older_docs = docs[midpoint:]
    
    recent_text = " ".join([d["content"] for d in recent_docs])
    older_text = " ".join([d["content"] for d in older_docs])
    
    recent_sentiment = analyze_lexicon_sentiment(recent_text)
    older_sentiment = analyze_lexicon_sentiment(older_text)
    
    sentiment_change = recent_sentiment["sentiment_score"] - older_sentiment["sentiment_score"]
    
    return {
        "company": company,
        "recent_sentiment": recent_sentiment["sentiment_score"],
        "older_sentiment": older_sentiment["sentiment_score"],
        "sentiment_change": round(sentiment_change, 3),
        "trend": "improving" if sentiment_change > 0.05 else "declining" if sentiment_change < -0.05 else "stable",
        "recent_ai_focus": recent_sentiment["ai_mentions"],
        "older_ai_focus": older_sentiment["ai_mentions"],
    }
