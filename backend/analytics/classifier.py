"""
Investment classifier for distinguishing AI/Data Center investments from Traditional manufacturing.
Uses keyword analysis and context classification.
"""
import re
from typing import Literal
from collections import defaultdict

from backend.core.cache import analytics_cache, cached
from backend.core.config import TRACKED_COMPANY_NAMES
from backend.rag.retriever import search_documents
from backend.analytics.sentiment import _filing_weight


# Classification keywords
AI_DATACENTER_KEYWORDS = {
    "high_confidence": [
        "artificial intelligence", "machine learning", "deep learning", "neural network",
        "gpu", "nvidia", "data center", "datacenter", "hyperscale", "cloud computing",
        "ai infrastructure", "inference", "training compute", "ai accelerator",
        "generative ai", "large language model", "llm",
    ],
    "medium_confidence": [
        "ai", "ml", "cloud", "server", "compute", "digital transformation",
        "automation", "robotics", "iot", "edge computing", "5g infrastructure",
    ],
}

TRADITIONAL_KEYWORDS = {
    "high_confidence": [
        "manufacturing facility", "assembly line", "production capacity",
        "factory expansion", "plant upgrade", "equipment upgrade",
        "traditional manufacturing", "pcb assembly", "smt line",
        "warehouse", "logistics", "supply chain facility",
    ],
    "medium_confidence": [
        "facility", "plant", "production", "manufacturing", "assembly",
        "capacity expansion", "operational efficiency", "lean manufacturing",
    ],
}


def classify_investment_text(text: str) -> dict:
    """
    Classify a text passage as AI/Data Center or Traditional investment.
    
    Returns:
        Dict with classification, confidence, and matching keywords
    """
    text_lower = text.lower()
    
    ai_score = 0
    traditional_score = 0
    ai_matches = []
    traditional_matches = []
    
    # Score AI/Data Center keywords
    for keyword in AI_DATACENTER_KEYWORDS["high_confidence"]:
        count = text_lower.count(keyword)
        if count > 0:
            ai_score += count * 3
            ai_matches.append({"keyword": keyword, "count": count, "weight": "high"})
    
    for keyword in AI_DATACENTER_KEYWORDS["medium_confidence"]:
        count = text_lower.count(keyword)
        if count > 0:
            ai_score += count * 1
            ai_matches.append({"keyword": keyword, "count": count, "weight": "medium"})
    
    # Score Traditional keywords
    for keyword in TRADITIONAL_KEYWORDS["high_confidence"]:
        count = text_lower.count(keyword)
        if count > 0:
            traditional_score += count * 3
            traditional_matches.append({"keyword": keyword, "count": count, "weight": "high"})
    
    for keyword in TRADITIONAL_KEYWORDS["medium_confidence"]:
        count = text_lower.count(keyword)
        if count > 0:
            traditional_score += count * 1
            traditional_matches.append({"keyword": keyword, "count": count, "weight": "medium"})
    
    # Determine classification
    total_score = ai_score + traditional_score
    
    if total_score == 0:
        classification = "unclassified"
        confidence = 0
        ai_percentage = 0
    else:
        ai_percentage = (ai_score / total_score) * 100
        
        if ai_percentage >= 70:
            classification = "ai_datacenter"
            confidence = min(95, 50 + ai_percentage / 2)
        elif ai_percentage <= 30:
            classification = "traditional"
            confidence = min(95, 50 + (100 - ai_percentage) / 2)
        else:
            classification = "mixed"
            confidence = 50 + abs(ai_percentage - 50)
    
    return {
        "classification": classification,
        "confidence": round(confidence, 1),
        "ai_score": ai_score,
        "traditional_score": traditional_score,
        "ai_percentage": round(ai_percentage, 1),
        "ai_keywords": sorted(ai_matches, key=lambda x: x["count"], reverse=True)[:5],
        "traditional_keywords": sorted(traditional_matches, key=lambda x: x["count"], reverse=True)[:5],
    }


@cached(analytics_cache, prefix="classifier")
def classify_company_investments(company: str, n_docs: int = 50) -> dict:
    """
    Analyze and classify all investments for a company.
    """
    # Search for investment-related content
    docs = search_documents(
        query=f"{company} investment capital expenditure CapEx spending expansion",
        company_filter=company,
        n_results=n_docs,
    )
    
    if not docs:
        return {"company": company, "error": "No investment documents found"}
    
    classifications = {
        "ai_datacenter": [],
        "traditional": [],
        "mixed": [],
        "unclassified": [],
    }
    
    total_ai_score = 0
    total_traditional_score = 0
    
    for doc in docs:
        filing_type = doc.get("filing_type", "Unknown")
        w = _filing_weight(filing_type)

        result = classify_investment_text(doc["content"])

        # Earnings transcripts count more — management's own words carry more
        # strategic signal than boilerplate 10-K disclosures.
        total_ai_score += result["ai_score"] * w
        total_traditional_score += result["traditional_score"] * w

        doc_info = {
            "source": doc.get("source", "Unknown"),
            "fiscal_year": doc.get("fiscal_year", "Unknown"),
            "filing_type": filing_type,
            "weight": w,
            "confidence": result["confidence"],
            "ai_percentage": result["ai_percentage"],
            "preview": doc["content"][:200] + "...",
        }

        classifications[result["classification"]].append(doc_info)
    
    # Calculate overall breakdown
    total_score = total_ai_score + total_traditional_score
    if total_score > 0:
        overall_ai_percentage = (total_ai_score / total_score) * 100
    else:
        overall_ai_percentage = 0
    
    return {
        "company": company,
        "documents_analyzed": len(docs),
        "investment_breakdown": {
            "ai_datacenter": {
                "count": len(classifications["ai_datacenter"]),
                "percentage": round(len(classifications["ai_datacenter"]) / len(docs) * 100, 1),
            },
            "traditional": {
                "count": len(classifications["traditional"]),
                "percentage": round(len(classifications["traditional"]) / len(docs) * 100, 1),
            },
            "mixed": {
                "count": len(classifications["mixed"]),
                "percentage": round(len(classifications["mixed"]) / len(docs) * 100, 1),
            },
        },
        "overall_ai_focus_percentage": round(overall_ai_percentage, 1),
        "investment_focus": "AI/Data Center" if overall_ai_percentage > 60 else "Traditional" if overall_ai_percentage < 40 else "Balanced",
        "sample_ai_investments": classifications["ai_datacenter"][:3],
        "sample_traditional_investments": classifications["traditional"][:3],
    }


@cached(analytics_cache, prefix="compare_invest")
def compare_investment_focus() -> dict:
    """
    Compare investment focus across all companies.
    """
    companies = list(TRACKED_COMPANY_NAMES)
    
    results = {
        "companies": [],
        "rankings": {
            "ai_focused": [],
            "traditional_focused": [],
        },
        "industry_average_ai_focus": 0,
    }
    
    total_ai_focus = 0
    
    for company in companies:
        analysis = classify_company_investments(company)
        
        if "error" not in analysis:
            results["companies"].append(analysis)
            total_ai_focus += analysis["overall_ai_focus_percentage"]
            
            results["rankings"]["ai_focused"].append({
                "company": company,
                "ai_focus": analysis["overall_ai_focus_percentage"],
            })
    
    # Sort rankings
    results["rankings"]["ai_focused"].sort(key=lambda x: x["ai_focus"], reverse=True)
    results["rankings"]["traditional_focused"] = sorted(
        results["rankings"]["ai_focused"],
        key=lambda x: x["ai_focus"]
    )
    
    # Calculate industry average
    if results["companies"]:
        results["industry_average_ai_focus"] = round(total_ai_focus / len(results["companies"]), 1)
    
    return results


def get_ai_investment_leaders() -> dict:
    """
    Identify companies leading in AI/Data Center investments.
    """
    comparison = compare_investment_focus()
    
    leaders = []
    for company_data in comparison["companies"]:
        if company_data["overall_ai_focus_percentage"] > comparison["industry_average_ai_focus"]:
            leaders.append({
                "company": company_data["company"],
                "ai_focus": company_data["overall_ai_focus_percentage"],
                "above_average_by": round(
                    company_data["overall_ai_focus_percentage"] - comparison["industry_average_ai_focus"],
                    1
                ),
            })
    
    return {
        "industry_average": comparison["industry_average_ai_focus"],
        "leaders": sorted(leaders, key=lambda x: x["ai_focus"], reverse=True),
        "leader_count": len(leaders),
    }
