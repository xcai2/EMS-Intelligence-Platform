"""
Anomaly detection for CapEx and investment pattern changes.
Detects unusual spikes or drops in spending, sentiment shifts, and strategic pivots.
"""
import re
from typing import Optional
from collections import defaultdict
from statistics import mean, stdev

from backend.core.config import ANOMALY_THRESHOLD, TRACKED_COMPANY_NAMES
from backend.rag.retriever import search_documents, get_company_documents


def extract_dollar_amounts(text: str) -> list[float]:
    """
    Extract dollar amounts from text.
    Handles formats like: $1.5 billion, $500 million, $1,234,567
    """
    amounts = []
    
    # Pattern for billions
    billion_pattern = r'\$?([\d,.]+)\s*billion'
    for match in re.finditer(billion_pattern, text.lower()):
        try:
            value = float(match.group(1).replace(',', '')) * 1_000_000_000
            amounts.append(value)
        except ValueError:
            pass
    
    # Pattern for millions
    million_pattern = r'\$?([\d,.]+)\s*million'
    for match in re.finditer(million_pattern, text.lower()):
        try:
            value = float(match.group(1).replace(',', '')) * 1_000_000
            amounts.append(value)
        except ValueError:
            pass
    
    # Pattern for direct dollar amounts
    dollar_pattern = r'\$([\d,]+(?:\.\d+)?)'
    for match in re.finditer(dollar_pattern, text):
        try:
            value = float(match.group(1).replace(',', ''))
            if value > 10000:  # Only significant amounts
                amounts.append(value)
        except ValueError:
            pass
    
    return amounts


def detect_capex_anomalies(company: str, threshold: float = ANOMALY_THRESHOLD) -> dict:
    """
    Detect anomalies in CapEx mentions for a company.
    
    Args:
        company: Company name
        threshold: Percentage change threshold for anomaly (default 20%)
        
    Returns:
        Dict with anomaly information
    """
    # Search for CapEx-related content
    docs = search_documents(
        query=f"{company} capital expenditure CapEx spending investment million billion",
        company_filter=company,
        n_results=50,
    )
    
    if not docs:
        return {"company": company, "error": "No documents found"}
    
    # Group by fiscal year/quarter — also track sources per period
    amounts_by_period: defaultdict = defaultdict(list)
    mentions_by_period: defaultdict = defaultdict(int)
    sources_by_period: defaultdict = defaultdict(list)

    for doc in docs:
        fiscal_year = doc.get("fiscal_year", "Unknown")
        quarter = doc.get("quarter", "")
        period = f"{fiscal_year} {quarter}".strip()

        amounts = extract_dollar_amounts(doc.get("content") or "")
        amounts_by_period[period].extend(amounts)
        mentions_by_period[period] += 1

        src = doc.get("source") or doc.get("source_file", "")
        ftype = doc.get("filing_type", "")
        if src:
            label = f"{ftype} — {src.split('/')[-1]}" if ftype else src.split("/")[-1]
            if label not in sources_by_period[period]:
                sources_by_period[period].append(label)

    # Calculate average amounts per period
    period_averages = {}
    for period, amounts in amounts_by_period.items():
        if amounts:
            period_averages[period] = mean(amounts)

    # Detect anomalies
    anomalies = []
    if len(period_averages) >= 2:
        all_averages = list(period_averages.values())
        overall_mean = mean(all_averages)

        if len(all_averages) > 2:
            overall_std = stdev(all_averages)
        else:
            overall_std = overall_mean * 0.3

        for period, avg in period_averages.items():
            if overall_std > 0:
                z_score = (avg - overall_mean) / overall_std
                pct_change = (avg - overall_mean) / overall_mean if overall_mean > 0 else 0

                if abs(z_score) > 1.5 or abs(pct_change) > threshold:
                    direction = "spike" if z_score > 0 else "drop"
                    avg_m = avg / 1_000_000
                    mean_m = overall_mean / 1_000_000
                    pct_abs = abs(round(pct_change * 100, 1))
                    if direction == "spike":
                        reason = (
                            f"CapEx spending in {period} was {pct_abs}% above the historical "
                            f"average (${avg_m:,.0f}M reported vs ${mean_m:,.0f}M typical), "
                            f"suggesting an unusually large investment or one-time capital outlay."
                        )
                    else:
                        reason = (
                            f"CapEx spending in {period} fell {pct_abs}% below the historical "
                            f"average (${avg_m:,.0f}M reported vs ${mean_m:,.0f}M typical), "
                            f"indicating a possible investment pause or deferred spending."
                        )

                    anomalies.append({
                        "period": period,
                        "average_amount": avg,
                        "z_score": round(z_score, 2),
                        "pct_change_from_mean": round(pct_change * 100, 1),
                        "direction": direction,
                        "severity": "high" if abs(z_score) > 2 else "medium",
                        "reason": reason,
                        "sources": sources_by_period.get(period, [])[:5],
                    })

    return {
        "company": company,
        "periods_analyzed": len(period_averages),
        "anomalies": sorted(anomalies, key=lambda x: abs(x["z_score"]), reverse=True),
        "has_anomalies": len(anomalies) > 0,
        "period_data": {k: round(v, 0) for k, v in period_averages.items()},
    }


def detect_sentiment_shifts(company: str) -> dict:
    """
    Detect significant shifts in sentiment over time.
    """
    from backend.analytics.sentiment import analyze_lexicon_sentiment
    
    docs = get_company_documents(company, limit=100)
    
    if len(docs) < 10:
        return {"company": company, "error": "Not enough documents for analysis"}
    
    # Group documents by fiscal year
    docs_by_year = defaultdict(list)
    for doc in docs:
        year = doc.get("metadata", {}).get("fiscal_year", "Unknown")
        docs_by_year[year].append(doc.get("content") or "")
    
    # Calculate sentiment per year
    sentiment_by_year = {}
    for year, contents in docs_by_year.items():
        combined = " ".join(contents)
        analysis = analyze_lexicon_sentiment(combined)
        sentiment_by_year[year] = analysis["sentiment_score"]
    
    # Detect shifts
    shifts = []
    sorted_years = sorted([y for y in sentiment_by_year.keys() if y != "Unknown"])
    
    for i in range(1, len(sorted_years)):
        prev_year = sorted_years[i-1]
        curr_year = sorted_years[i]
        
        prev_sentiment = sentiment_by_year[prev_year]
        curr_sentiment = sentiment_by_year[curr_year]
        
        change = curr_sentiment - prev_sentiment
        
        if abs(change) > 0.15:  # 15% shift threshold
            shifts.append({
                "from_period": prev_year,
                "to_period": curr_year,
                "from_sentiment": round(prev_sentiment, 3),
                "to_sentiment": round(curr_sentiment, 3),
                "change": round(change, 3),
                "direction": "improving" if change > 0 else "declining",
                "severity": "high" if abs(change) > 0.3 else "medium",
            })
    
    return {
        "company": company,
        "years_analyzed": len(sorted_years),
        "sentiment_by_year": {k: round(v, 3) for k, v in sentiment_by_year.items()},
        "shifts": shifts,
        "has_significant_shifts": len(shifts) > 0,
    }


def detect_ai_investment_changes(company: str) -> dict:
    """
    Detect changes in AI and data center investment focus.
    """
    # Search for AI-related content
    docs = search_documents(
        query=f"{company} AI artificial intelligence data center GPU machine learning",
        company_filter=company,
        n_results=100,
    )
    
    # Group by fiscal year — also track sources per year
    ai_mentions_by_year: defaultdict = defaultdict(int)
    total_docs_by_year: defaultdict = defaultdict(int)
    sources_by_year: defaultdict = defaultdict(list)

    ai_keywords = ["ai", "artificial intelligence", "machine learning", "gpu",
                   "neural", "deep learning", "data center", "hyperscale"]

    for doc in docs:
        year = doc.get("fiscal_year", "Unknown")
        content_lower = (doc.get("content") or "").lower()
        total_docs_by_year[year] += 1
        for keyword in ai_keywords:
            ai_mentions_by_year[year] += content_lower.count(keyword)

        src = doc.get("source") or doc.get("source_file", "")
        ftype = doc.get("filing_type", "")
        if src:
            label = f"{ftype} — {src.split('/')[-1]}" if ftype else src.split("/")[-1]
            if label not in sources_by_year[year]:
                sources_by_year[year].append(label)

    # Calculate AI focus intensity per year
    ai_focus_by_year = {}
    for year in total_docs_by_year:
        if total_docs_by_year[year] > 0:
            ai_focus_by_year[year] = ai_mentions_by_year[year] / total_docs_by_year[year]

    # Detect changes
    changes = []
    sorted_years = sorted([y for y in ai_focus_by_year.keys() if y != "Unknown"])

    for i in range(1, len(sorted_years)):
        prev_year = sorted_years[i - 1]
        curr_year = sorted_years[i]

        prev_focus = ai_focus_by_year[prev_year]
        curr_focus = ai_focus_by_year[curr_year]

        if prev_focus > 0:
            pct_change = (curr_focus - prev_focus) / prev_focus
        else:
            pct_change = 1.0 if curr_focus > 0 else 0

        if abs(pct_change) > 0.25:
            direction = "increasing" if pct_change > 0 else "decreasing"
            pct_abs = abs(round(pct_change * 100, 1))
            if direction == "increasing":
                reason = (
                    f"AI/tech keyword density rose {pct_abs}% from {prev_year} to {curr_year} "
                    f"({prev_focus:.1f} → {curr_focus:.1f} mentions per document), "
                    f"reflecting a measurable shift toward AI and data-center investment themes."
                )
            else:
                reason = (
                    f"AI/tech keyword density fell {pct_abs}% from {prev_year} to {curr_year} "
                    f"({prev_focus:.1f} → {curr_focus:.1f} mentions per document), "
                    f"suggesting reduced emphasis on AI and data-center topics in filings."
                )

            # Combine sources from both years (up to 5 total)
            combined_sources = list(dict.fromkeys(
                sources_by_year.get(prev_year, []) + sources_by_year.get(curr_year, [])
            ))[:5]

            changes.append({
                "from_period": prev_year,
                "to_period": curr_year,
                "from_intensity": round(prev_focus, 2),
                "to_intensity": round(curr_focus, 2),
                "pct_change": round(pct_change * 100, 1),
                "direction": direction,
                "reason": reason,
                "sources": combined_sources,
            })
    
    return {
        "company": company,
        "years_analyzed": len(sorted_years),
        "ai_focus_by_year": {k: round(v, 2) for k, v in ai_focus_by_year.items()},
        "changes": changes,
        "trend": "increasing" if len(changes) > 0 and changes[-1]["direction"] == "increasing" else "stable",
    }


def get_all_anomalies() -> dict:
    """
    Detect anomalies across all tracked companies.
    """
    companies = list(TRACKED_COMPANY_NAMES)
    
    results = {
        "capex_anomalies": [],
        "sentiment_shifts": [],
        "ai_investment_changes": [],
        "summary": {
            "companies_with_capex_anomalies": [],
            "companies_with_sentiment_shifts": [],
            "companies_increasing_ai_focus": [],
        }
    }
    
    for company in companies:
        # CapEx anomalies
        capex = detect_capex_anomalies(company)
        if capex.get("has_anomalies"):
            results["capex_anomalies"].append(capex)
            results["summary"]["companies_with_capex_anomalies"].append(company)
        
        # Sentiment shifts
        sentiment = detect_sentiment_shifts(company)
        if sentiment.get("has_significant_shifts"):
            results["sentiment_shifts"].append(sentiment)
            results["summary"]["companies_with_sentiment_shifts"].append(company)
        
        # AI investment changes
        ai_changes = detect_ai_investment_changes(company)
        if ai_changes.get("trend") == "increasing":
            results["ai_investment_changes"].append(ai_changes)
            results["summary"]["companies_increasing_ai_focus"].append(company)
    
    return results
