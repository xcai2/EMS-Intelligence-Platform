"""
Competitive Intelligence API Routes

Features:
1. Big 5 AI CapEx Tracker (AWS, Google, Microsoft, Meta, Oracle)
2. Competitor Investment Plans
3. Default Analyst Questions
4. News Monitoring (Press Releases, OCP, Industry News)
5. AI-related dynamics for EMS companies
"""

from collections import Counter
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from backend.analytics.classifier import classify_company_investments
from backend.analytics.sentiment import analyze_company_sentiment
from backend.analytics.trends import analyze_company_trends
from backend.rag.retriever import search_documents

router = APIRouter()


TRACKED_COMPANIES = ["Flex", "Jabil", "Celestica", "Benchmark", "Sanmina"]


def _outlook_from_sentiment(score: float) -> str:
    if score >= 0.25:
        return "Very bullish"
    if score >= 0.12:
        return "Strong"
    if score >= 0.03:
        return "Positive"
    if score <= -0.12:
        return "Cautious"
    return "Stable"


def _extract_focus_areas(company: str) -> list[str]:
    theme_keywords = {
        "Liquid cooling": ["liquid cooling", "thermal", "cooling"],
        "Power systems": ["power", "power module", "power management", "psu"],
        "AI server assembly": ["ai server", "server assembly", "rack", "gpu server"],
        "Cloud infrastructure": ["cloud", "hyperscale", "data center"],
        "Networking": ["network", "ethernet", "switch", "interconnect"],
        "Advanced packaging": ["advanced packaging", "packaging", "substrate"],
        "Optical components": ["optical", "photonics", "transceiver"],
        "Automation": ["automation", "robotics", "factory automation"],
    }

    docs = search_documents(
        query=f"{company} AI data center investment strategy manufacturing",
        company_filter=company,
        n_results=30,
    )

    theme_counter: Counter[str] = Counter()
    for doc in docs:
        content = doc.get("content", "").lower()
        for theme, keywords in theme_keywords.items():
            hits = sum(content.count(k) for k in keywords)
            if hits:
                theme_counter[theme] += hits

    top = [theme for theme, _ in theme_counter.most_common(3)]
    return top or ["General AI/Data Center investment"]


def _extract_evidence_highlights(company: str) -> list[str]:
    docs = search_documents(
        query=f"{company} expansion investment guidance AI data center",
        company_filter=company,
        n_results=6,
    )

    highlights: list[str] = []
    for doc in docs:
        content = (doc.get("content") or "").strip()
        if not content:
            continue
        first_sentence = content.split(".")[0].strip()
        if len(first_sentence) < 25:
            continue
        line = first_sentence[:180].rstrip()
        if line not in highlights:
            highlights.append(line)
        if len(highlights) >= 3:
            break

    return highlights or ["No high-confidence evidence snippet found in current indexed documents."]


def _build_dynamic_competitor_analysis() -> dict:
    companies = []
    generated_at = datetime.utcnow().isoformat() + "Z"

    for company in TRACKED_COMPANIES:
        classification = classify_company_investments(company, n_docs=60)
        sentiment = analyze_company_sentiment(company, n_chunks=30)
        trends = analyze_company_trends(company)

        if classification.get("error"):
            companies.append(
                {
                    "company": company,
                    "status": "no_data",
                    "message": classification["error"],
                }
            )
            continue

        sentiment_score = float(sentiment.get("sentiment_score", 0))
        companies.append(
            {
                "company": company,
                "status": "ok",
                "documents_analyzed": classification.get("documents_analyzed", 0),
                "ai_focus_pct": classification.get("overall_ai_focus_percentage", 0),
                "investment_profile": classification.get("investment_focus", "Balanced"),
                "sentiment_score": sentiment_score,
                "outlook": _outlook_from_sentiment(sentiment_score),
                "trend_outlook": trends.get("overall_outlook", "neutral"),
                "focus_areas": _extract_focus_areas(company),
                "evidence_highlights": _extract_evidence_highlights(company),
            }
        )

    return {
        "mode": "dynamic_from_indexed_documents",
        "generated_at": generated_at,
        "companies": companies,
    }


# ---------------------------------------------------------------------------
# BIG 5 AI CAPEX DATA (Based on Futurum Research Feb 2026)
# ---------------------------------------------------------------------------

BIG5_AI_CAPEX = {
    "last_updated": "2026-02-25",
    "source": "Futurum Research, Company Earnings Reports",
    "total_2026_capex_billions": 675,  # $660-690B midpoint
    "companies": [
        {
            "name": "Amazon (AWS)",
            "ticker": "AMZN",
            "capex_2026_billions": 200,
            "capex_2025_billions": 100,
            "yoy_growth_pct": 100,
            "ai_focus_areas": ["AI compute", "Data centers", "Custom chips (Trainium)"],
            "key_metrics": {
                "aws_revenue_billions": 142,
                "aws_growth_pct": 24,
            },
            "recent_announcements": [
                "Q4 2025: $200B capex guidance for 2026",
                "AI capacity being monetized as quickly as installed",
                "Supply-constrained, not demand-constrained",
            ],
            "color": "#FF9900",
        },
        {
            "name": "Alphabet (Google)",
            "ticker": "GOOGL",
            "capex_2026_billions": 180,  # $175-185B midpoint
            "capex_2025_billions": 75,
            "yoy_growth_pct": 140,
            "ai_focus_areas": ["TPU clusters", "Gemini infrastructure", "Cloud AI"],
            "key_metrics": {
                "cloud_backlog_billions": 240,
                "gemini_cost_reduction_pct": 78,
            },
            "recent_announcements": [
                "Capex revised upward 3 times from initial $71-73B",
                "Cloud backlog surged 55% sequentially to $240B+",
                "Reduced Gemini serving costs by 78% through optimization",
            ],
            "color": "#4285F4",
        },
        {
            "name": "Microsoft",
            "ticker": "MSFT",
            "capex_2026_billions": 120,
            "capex_2025_billions": 80,
            "yoy_growth_pct": 50,
            "ai_focus_areas": ["Azure AI", "OpenAI partnership", "Copilot infrastructure"],
            "key_metrics": {
                "azure_backlog_billions": 80,
                "quarterly_capex_billions": 37.5,
            },
            "recent_announcements": [
                "$80B Azure backlog unfulfilled due to power constraints",
                "AI business larger than some established franchises",
                "Quarterly capex run rate of $37.5B",
            ],
            "color": "#00A4EF",
        },
        {
            "name": "Meta",
            "ticker": "META",
            "capex_2026_billions": 125,  # $115-135B midpoint
            "capex_2025_billions": 40,
            "yoy_growth_pct": 212,
            "ai_focus_areas": ["Llama models", "AI recommendation", "Reality Labs"],
            "key_metrics": {
                "ai_research_headcount": 25000,
            },
            "recent_announcements": [
                "Building 1GW data center in Ohio",
                "Louisiana facility could scale to 5GW",
                "Capex range $115-135B for 2026",
            ],
            "color": "#1877F2",
        },
        {
            "name": "Oracle",
            "ticker": "ORCL",
            "capex_2026_billions": 50,
            "capex_2025_billions": 21,
            "yoy_growth_pct": 136,
            "ai_focus_areas": ["OCI AI", "Stargate project", "Cloud infrastructure"],
            "key_metrics": {
                "remaining_obligations_billions": 523,
            },
            "recent_announcements": [
                "Part of Stargate $500B AI infrastructure project",
                "Capex increasing 136% from 2025",
                "OCI demand exceeding supply",
            ],
            "color": "#F80000",
        },
    ],
    "stargate_project": {
        "total_investment_billions": 500,
        "timeline": "2025-2029",
        "partners": ["OpenAI", "SoftBank", "Oracle", "MGX"],
        "initial_deployment_billions": 100,
        "planned_capacity_gw": 7,
        "locations": ["Texas", "New Mexico", "Ohio"],
    },
}


# ---------------------------------------------------------------------------
# DEFAULT ANALYST QUESTIONS (from earnings calls)
# ---------------------------------------------------------------------------

DEFAULT_ANALYST_QUESTIONS = [
    {
        "id": "q1",
        "question": "What is the AI/Data Center revenue mix for each company, and how has it changed YoY?",
        "category": "AI Investment",
        "complexity": "comparison",
        "companies": ["Flex", "Jabil", "Celestica", "Benchmark", "Sanmina"],
    },
    {
        "id": "q2",
        "question": "Compare CapEx guidance across all 5 EMS companies for the current fiscal year",
        "category": "Capital Expenditure",
        "complexity": "comparison",
        "companies": ["Flex", "Jabil", "Celestica", "Benchmark", "Sanmina"],
    },
    {
        "id": "q3",
        "question": "What liquid cooling and power management capabilities are each company developing?",
        "category": "AI Infrastructure",
        "complexity": "descriptive",
        "companies": ["Flex", "Jabil", "Celestica", "Benchmark", "Sanmina"],
    },
    {
        "id": "q4",
        "question": "Which hyperscaler customers are driving AI server demand for EMS companies?",
        "category": "Customer Analysis",
        "complexity": "descriptive",
        "companies": ["Flex", "Jabil", "Celestica"],
    },
    {
        "id": "q5",
        "question": "What are the gross margin trends for AI/DC vs traditional segments?",
        "category": "Financials",
        "complexity": "numeric",
        "companies": ["Flex", "Jabil", "Celestica", "Benchmark", "Sanmina"],
    },
    {
        "id": "q6",
        "question": "What manufacturing capacity expansions are planned for AI server production?",
        "category": "Operations",
        "complexity": "descriptive",
        "companies": ["Flex", "Jabil", "Celestica"],
    },
]


# ---------------------------------------------------------------------------
# EMS COMPANY AI DYNAMICS
# ---------------------------------------------------------------------------

EMS_AI_DYNAMICS = {
    "last_updated": "2026-02-25",
    "companies": [
        {
            "company": "Flex",
            "ticker": "FLEX",
            "ai_revenue_growth_pct": 45,
            "ai_revenue_mix_pct": 28,
            "recent_highlights": [
                "Expanded liquid cooling production capacity in Mexico",
                "New AI server assembly line in Malaysia operational",
                "Won major hyperscaler contract for GPU server racks",
            ],
            "investment_focus": ["Liquid cooling", "Power modules", "AI server assembly"],
            "guidance_outlook": "Positive - expecting AI/DC to reach 35% of revenue by FY25",
        },
        {
            "company": "Jabil",
            "ticker": "JBL",
            "ai_revenue_growth_pct": 52,
            "ai_revenue_mix_pct": 32,
            "recent_highlights": [
                "Cloud segment revenue up 40% YoY",
                "Investing in advanced thermal solutions",
                "Partnership with major AI chip maker for packaging",
            ],
            "investment_focus": ["Cloud infrastructure", "Thermal management", "Advanced packaging"],
            "guidance_outlook": "Strong - cloud and AI driving double-digit growth",
        },
        {
            "company": "Celestica",
            "ticker": "CLS",
            "ai_revenue_growth_pct": 68,
            "ai_revenue_mix_pct": 42,
            "recent_highlights": [
                "Highest AI exposure among EMS peers",
                "HPS segment growing 50%+ for third consecutive quarter",
                "New Singapore facility dedicated to AI hardware",
            ],
            "investment_focus": ["HPC/AI servers", "Networking equipment", "Storage solutions"],
            "guidance_outlook": "Very bullish - AI/HPS now largest segment",
        },
        {
            "company": "Benchmark",
            "ticker": "BHE",
            "ai_revenue_growth_pct": 25,
            "ai_revenue_mix_pct": 15,
            "recent_highlights": [
                "Selective AI market entry through precision manufacturing",
                "Focus on high-reliability AI components",
                "Medical and Aerospace remain primary focus",
            ],
            "investment_focus": ["Precision manufacturing", "High-reliability components"],
            "guidance_outlook": "Cautious - prioritizing margin over AI growth",
        },
        {
            "company": "Sanmina",
            "ticker": "SANM",
            "ai_revenue_growth_pct": 30,
            "ai_revenue_mix_pct": 18,
            "recent_highlights": [
                "Optical interconnect capabilities for AI racks",
                "Defense and Industrial remain core",
                "Selective participation in AI infrastructure",
            ],
            "investment_focus": ["Optical components", "Industrial automation"],
            "guidance_outlook": "Stable - balanced portfolio approach",
        },
    ],
}


# ---------------------------------------------------------------------------
# NEWS MONITORING DATA
# ---------------------------------------------------------------------------

MONITORED_NEWS = {
    "press_releases": [
        {
            "company": "Flex",
            "title": "Flex Announces Expansion of AI Manufacturing Capabilities",
            "date": "2026-02-20",
            "url": "https://flex.com/newsroom",
            "summary": "New liquid cooling production line in Guadalajara, Mexico",
            "category": "Capacity Expansion",
        },
        {
            "company": "Jabil",
            "title": "Jabil Reports Q2 FY2026 Results, Cloud Segment Up 40%",
            "date": "2026-02-18",
            "url": "https://investors.jabil.com",
            "summary": "Cloud infrastructure demand driving record revenue",
            "category": "Earnings",
        },
        {
            "company": "Celestica",
            "title": "Celestica HPS Segment Achieves 50% YoY Growth",
            "date": "2026-02-15",
            "url": "https://www.celestica.com/investors-hub",
            "summary": "AI server demand from hyperscalers continues to accelerate",
            "category": "Segment Performance",
        },
    ],
    "ocp_news": [
        {
            "title": "OCP Open Chiplet Economy Leading Next Wave of AI: Inference",
            "date": "2026-02-17",
            "url": "https://www.opencompute.org/",
            "relevance": "Industry standard for AI hardware design",
            "companies_mentioned": ["Flex", "Jabil", "Celestica"],
        },
        {
            "title": "OCP Steering Committee Elections 2026-2028",
            "date": "2026-02-20",
            "url": "https://www.opencompute.org/",
            "relevance": "Industry governance and standards direction",
            "companies_mentioned": [],
        },
    ],
    "industry_news": [
        {
            "title": "AI Capex 2026: The $690B Infrastructure Sprint",
            "source": "Futurum Research",
            "date": "2026-02-12",
            "url": "https://futurumgroup.com/insights/ai-capex-2026-the-690b-infrastructure-sprint/",
            "summary": "Big 5 tech companies commit $660-690B to AI infrastructure",
            "relevance": "Major demand driver for EMS companies",
        },
        {
            "title": "Hyperscaler Demand for AI Servers Exceeds Supply",
            "source": "Industry Analysis",
            "date": "2026-02-22",
            "url": "#",
            "summary": "All major cloud providers report supply constraints",
            "relevance": "Strong tailwind for EMS manufacturing capacity",
        },
    ],
}


# ---------------------------------------------------------------------------
# API ENDPOINTS
# ---------------------------------------------------------------------------

@router.get("/big5-capex")
async def get_big5_capex():
    """Get Big 5 AI CapEx tracker data."""
    return BIG5_AI_CAPEX


@router.get("/big5-capex/summary")
async def get_big5_capex_summary():
    """Get summary of Big 5 AI investments."""
    total = sum(c["capex_2026_billions"] for c in BIG5_AI_CAPEX["companies"])
    return {
        "total_2026_billions": total,
        "companies": [
            {
                "name": c["name"],
                "capex_billions": c["capex_2026_billions"],
                "growth_pct": c["yoy_growth_pct"],
            }
            for c in BIG5_AI_CAPEX["companies"]
        ],
        "stargate_project": BIG5_AI_CAPEX["stargate_project"],
    }


@router.get("/default-questions")
async def get_default_questions():
    """Get default analyst questions for the chat interface."""
    return {
        "questions": DEFAULT_ANALYST_QUESTIONS,
        "categories": list(set(q["category"] for q in DEFAULT_ANALYST_QUESTIONS)),
    }


@router.get("/ems-ai-dynamics")
async def get_ems_ai_dynamics():
    """Get AI-related dynamics for EMS companies."""
    return EMS_AI_DYNAMICS


@router.get("/ems-ai-dynamics/{company}")
async def get_company_ai_dynamics(company: str):
    """Get AI dynamics for a specific company."""
    company_lower = company.lower()
    for c in EMS_AI_DYNAMICS["companies"]:
        if c["company"].lower() == company_lower:
            return c
    return {"error": f"Company {company} not found"}


@router.get("/news/all")
async def get_all_news():
    """Get all monitored news."""
    return MONITORED_NEWS


@router.get("/news/press-releases")
async def get_press_releases():
    """Get company press releases."""
    return {"press_releases": MONITORED_NEWS["press_releases"]}


@router.get("/news/ocp")
async def get_ocp_news():
    """Get OCP-related news."""
    return {"ocp_news": MONITORED_NEWS["ocp_news"]}


@router.get("/news/industry")
async def get_industry_news():
    """Get industry-wide AI news."""
    return {"industry_news": MONITORED_NEWS["industry_news"]}


@router.get("/competitor-investments")
async def get_competitor_investments(mode: str = "hybrid"):
    """Get competitor investment plans and guidance."""
    payload = {
        "as_of": EMS_AI_DYNAMICS.get("last_updated"),
        "growth_definition": "AI/DC revenue composite growth (proxy)",
        "growth_period": "FY2025-FY2026",
        "competitors": [
            {
                "company": c["company"],
                "investment_focus": c["investment_focus"],
                "guidance_outlook": c["guidance_outlook"],
                "recent_highlights": c["recent_highlights"],
                "ai_growth_pct": c["ai_revenue_growth_pct"],
            }
            for c in EMS_AI_DYNAMICS["companies"]
        ],
        "hyperscaler_demand": {
            "outlook": "Very Strong",
            "drivers": [
                "Big 5 spending $675B+ on AI infrastructure in 2026",
                "Supply-constrained across all major cloud providers",
                "Liquid cooling and power density requirements driving EMS demand",
            ],
            "beneficiaries": ["Celestica", "Jabil", "Flex"],
        },
    }

    # Optional dynamic section built from indexed filings/transcripts in Chroma.
    if mode in {"hybrid", "dynamic"}:
        try:
            payload["dynamic_analysis"] = _build_dynamic_competitor_analysis()
        except Exception as e:
            payload["dynamic_analysis"] = {
                "mode": "dynamic_from_indexed_documents",
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "error": f"Dynamic analysis failed: {e}",
                "companies": [],
            }

    return payload
