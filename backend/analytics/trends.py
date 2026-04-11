"""
Trend analysis and forecasting for competitive intelligence.
Provides trend predictions based on historical data patterns.
"""
import re
from typing import Optional
from collections import defaultdict
from statistics import mean, stdev

from backend.core.cache import analytics_cache, cached
from backend.core.config import TRACKED_COMPANY_NAMES
from backend.rag.retriever import search_documents, get_company_documents


def extract_percentages(text: str) -> list[float]:
    """Extract percentage values from text."""
    percentages = []
    
    # Pattern for percentages
    pct_pattern = r'([\d,.]+)\s*(?:%|percent)'
    for match in re.finditer(pct_pattern, text.lower()):
        try:
            value = float(match.group(1).replace(',', ''))
            if -100 <= value <= 1000:  # Reasonable percentage range
                percentages.append(value)
        except ValueError:
            pass
    
    return percentages


def calculate_trend_direction(values: list[float]) -> str:
    """Calculate the trend direction from a list of values."""
    if len(values) < 2:
        return "insufficient_data"
    
    # Simple linear regression slope
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = mean(values)
    
    numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    
    if denominator == 0:
        return "stable"
    
    slope = numerator / denominator
    
    # Normalize slope by mean value
    if y_mean != 0:
        normalized_slope = slope / abs(y_mean)
    else:
        normalized_slope = slope
    
    if normalized_slope > 0.05:
        return "increasing"
    elif normalized_slope < -0.05:
        return "decreasing"
    else:
        return "stable"


def forecast_next_value(values: list[float], periods_ahead: int = 1) -> dict:
    """
    Simple linear forecast for next period(s).
    """
    if len(values) < 2:
        return {"error": "Need at least 2 data points"}
    
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = mean(values)
    
    numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    
    if denominator == 0:
        slope = 0
    else:
        slope = numerator / denominator
    
    intercept = y_mean - slope * x_mean
    
    # Forecast
    forecasts = []
    for p in range(1, periods_ahead + 1):
        forecast_value = intercept + slope * (n - 1 + p)
        forecasts.append(round(forecast_value, 2))
    
    # Calculate confidence based on data variability
    if len(values) > 2:
        residuals = [values[i] - (intercept + slope * i) for i in range(n)]
        residual_std = stdev(residuals) if len(residuals) > 1 else 0
        confidence = max(0, min(100, 100 - (residual_std / max(abs(y_mean), 1) * 100)))
    else:
        confidence = 50
    
    return {
        "forecasts": forecasts,
        "trend_direction": calculate_trend_direction(values),
        "slope": round(slope, 4),
        "confidence": round(confidence, 1),
    }


@cached(analytics_cache, prefix="trends")
def analyze_company_trends(company: str) -> dict:
    """
    Analyze trends for a company across multiple metrics.
    """
    results = {
        "company": company,
        "capex_trend": {},
        "ai_focus_trend": {},
        "sentiment_trend": {},
        "overall_outlook": "",
    }
    
    # Analyze CapEx mentions by period
    capex_docs = search_documents(
        query=f"{company} capital expenditure CapEx investment spending",
        company_filter=company,
        n_results=100,
    )
    
    capex_by_year = defaultdict(int)
    for doc in capex_docs:
        year = doc.get("fiscal_year", "Unknown")
        if year != "Unknown":
            capex_by_year[year] += 1
    
    if len(capex_by_year) >= 2:
        sorted_years = sorted(capex_by_year.keys())
        values = [capex_by_year[y] for y in sorted_years]
        forecast = forecast_next_value(values)
        results["capex_trend"] = {
            "historical": {y: capex_by_year[y] for y in sorted_years},
            "direction": forecast["trend_direction"],
            "next_period_forecast": forecast["forecasts"][0] if forecast.get("forecasts") else None,
            "confidence": forecast.get("confidence", 0),
        }
    
    # Analyze AI focus trend
    ai_docs = search_documents(
        query=f"{company} AI artificial intelligence machine learning data center",
        company_filter=company,
        n_results=100,
    )
    
    ai_by_year = defaultdict(int)
    ai_keywords = ["ai", "artificial intelligence", "machine learning", "gpu", "data center"]
    
    for doc in ai_docs:
        year = doc.get("fiscal_year", "Unknown")
        if year != "Unknown":
            content_lower = doc["content"].lower()
            for keyword in ai_keywords:
                ai_by_year[year] += content_lower.count(keyword)
    
    if len(ai_by_year) >= 2:
        sorted_years = sorted(ai_by_year.keys())
        values = [ai_by_year[y] for y in sorted_years]
        forecast = forecast_next_value(values)
        results["ai_focus_trend"] = {
            "historical": {y: ai_by_year[y] for y in sorted_years},
            "direction": forecast["trend_direction"],
            "next_period_forecast": forecast["forecasts"][0] if forecast.get("forecasts") else None,
            "confidence": forecast.get("confidence", 0),
        }
    
    # Analyze sentiment trend
    from backend.analytics.sentiment import analyze_lexicon_sentiment
    
    docs = get_company_documents(company, limit=100)
    sentiment_by_year = defaultdict(list)
    
    for doc in docs:
        year = doc.get("metadata", {}).get("fiscal_year", "Unknown")
        if year != "Unknown":
            analysis = analyze_lexicon_sentiment(doc["content"])
            sentiment_by_year[year].append(analysis["sentiment_score"])
    
    if len(sentiment_by_year) >= 2:
        avg_sentiment_by_year = {y: mean(scores) for y, scores in sentiment_by_year.items()}
        sorted_years = sorted(avg_sentiment_by_year.keys())
        values = [avg_sentiment_by_year[y] for y in sorted_years]
        forecast = forecast_next_value(values)
        results["sentiment_trend"] = {
            "historical": {y: round(avg_sentiment_by_year[y], 3) for y in sorted_years},
            "direction": forecast["trend_direction"],
            "next_period_forecast": round(forecast["forecasts"][0], 3) if forecast.get("forecasts") else None,
            "confidence": forecast.get("confidence", 0),
        }
    
    # Determine overall outlook
    trends = []
    if results["capex_trend"].get("direction"):
        trends.append(("capex", results["capex_trend"]["direction"]))
    if results["ai_focus_trend"].get("direction"):
        trends.append(("ai", results["ai_focus_trend"]["direction"]))
    if results["sentiment_trend"].get("direction"):
        trends.append(("sentiment", results["sentiment_trend"]["direction"]))
    
    increasing = sum(1 for _, d in trends if d == "increasing")
    decreasing = sum(1 for _, d in trends if d == "decreasing")
    
    if increasing > decreasing:
        results["overall_outlook"] = "positive"
    elif decreasing > increasing:
        results["overall_outlook"] = "cautious"
    else:
        results["overall_outlook"] = "neutral"
    
    return results


@cached(analytics_cache, prefix="compare_trends")
def compare_company_trends() -> dict:
    """
    Compare trends across all tracked companies.
    """
    companies = list(TRACKED_COMPANY_NAMES)
    
    results = {
        "companies": [],
        "rankings": {
            "ai_focus_growth": [],
            "sentiment_improvement": [],
            "capex_growth": [],
        },
        "market_outlook": "",
    }
    
    for company in companies:
        trend = analyze_company_trends(company)
        results["companies"].append(trend)
        
        # Track for rankings
        if trend["ai_focus_trend"].get("direction") == "increasing":
            results["rankings"]["ai_focus_growth"].append({
                "company": company,
                "confidence": trend["ai_focus_trend"].get("confidence", 0),
            })
        
        if trend["sentiment_trend"].get("direction") == "increasing":
            results["rankings"]["sentiment_improvement"].append({
                "company": company,
                "confidence": trend["sentiment_trend"].get("confidence", 0),
            })
        
        if trend["capex_trend"].get("direction") == "increasing":
            results["rankings"]["capex_growth"].append({
                "company": company,
                "confidence": trend["capex_trend"].get("confidence", 0),
            })
    
    # Sort rankings by confidence
    for key in results["rankings"]:
        results["rankings"][key].sort(key=lambda x: x["confidence"], reverse=True)
    
    # Determine market outlook
    positive_outlooks = sum(1 for c in results["companies"] if c["overall_outlook"] == "positive")
    cautious_outlooks = sum(1 for c in results["companies"] if c["overall_outlook"] == "cautious")
    
    if positive_outlooks > cautious_outlooks:
        results["market_outlook"] = "The EMS sector shows positive momentum with multiple companies expanding AI and CapEx investments."
    elif cautious_outlooks > positive_outlooks:
        results["market_outlook"] = "The EMS sector shows mixed signals with some companies pulling back on investments."
    else:
        results["market_outlook"] = "The EMS sector is in a transitional phase with balanced growth and consolidation trends."
    
    return results
