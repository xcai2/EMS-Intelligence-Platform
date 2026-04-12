"""
Analysis API endpoints for dashboard data.
"""
from fastapi import APIRouter, HTTPException
from backend.core.config import COMPANIES, TRACKED_COMPANY_NAMES
from backend.core.database import get_collection_stats, get_collection
from backend.rag.retriever import search_documents

router = APIRouter()


@router.get("/analysis/overview")
async def get_overview():
    """
    Get overview metrics for the dashboard.
    """
    stats = get_collection_stats()
    
    # Calculate metrics
    total_docs = stats["total_documents"]
    companies = stats.get("companies", {})
    filing_types = stats.get("filing_types", {})
    
    # Count SEC filings vs other documents
    sec_filings = sum(
        filing_types.get(ft, 0) 
        for ft in ["10-K", "10-Q", "8-K"]
    )
    earnings_docs = sum(
        filing_types.get(ft, 0) 
        for ft in ["Earnings Transcript", "Earnings Presentation"]
    )
    
    return {
        "total_documents": total_docs,
        "companies_tracked": len(companies),
        "sec_filings": sec_filings,
        "earnings_documents": earnings_docs,
        "documents_by_company": companies,
        "documents_by_type": filing_types,
    }


@router.get("/analysis/capex-mentions")
async def get_capex_mentions():
    """
    Search for capital expenditure mentions across all companies.
    """
    # Search for CapEx-related content
    results = search_documents(
        query="capital expenditure property plant equipment investment",
        n_results=50,
    )
    
    # Group by company
    by_company = {}
    for doc in results:
        company = doc["company"]
        if company not in by_company:
            by_company[company] = []
        by_company[company].append({
            "source": doc["source"],
            "fiscal_year": doc["fiscal_year"],
            "quarter": doc["quarter"],
            "similarity": doc["similarity"],
            "snippet": doc["content"][:200] + "..." if len(doc["content"]) > 200 else doc["content"],
        })
    
    return {
        "total_mentions": len(results),
        "by_company": by_company,
    }


@router.get("/analysis/capex")
async def get_capex_analysis():
    """
    Get CapEx mentions aggregated by company for the analysis page.
    """
    # Search for CapEx-related content
    results = search_documents(
        query="capital expenditure CapEx property plant equipment investment spending",
        n_results=100,
    )
    
    # Aggregate by company
    company_data = {}
    for doc in results:
        company = doc["company"]
        if company not in company_data:
            company_data[company] = {"count": 0, "contexts": []}
        company_data[company]["count"] += 1
        if len(company_data[company]["contexts"]) < 5:
            snippet = doc["content"][:300].strip()
            if snippet:
                company_data[company]["contexts"].append(snippet)
    
    mentions = [
        {
            "company": company,
            "count": data["count"],
            "recent_context": data["contexts"]
        }
        for company, data in sorted(company_data.items(), key=lambda x: x[1]["count"], reverse=True)
    ]
    
    return {"mentions": mentions}


@router.get("/analysis/company-data-summary")
async def get_company_data_summary():
    """
    Get a summary of what data is available for each company.
    """
    companies = list(TRACKED_COMPANY_NAMES)
    
    data_categories = {
        "capex": "capital expenditure CapEx million billion investment spending",
        "ai_initiatives": "AI artificial intelligence machine learning GPU neural",
        "data_center": "data center datacenter hyperscale cloud infrastructure",
        "revenue": "revenue quarterly earnings growth segment",
        "facilities": "facility plant expansion manufacturing location site",
        "strategy": "strategy outlook guidance forecast future",
    }
    
    summary = {}
    
    for company in companies:
        company_summary = {}
        for category, query in data_categories.items():
            results = search_documents(
                query=query,
                company_filter=company,
                n_results=5,
            )
            
            # Get sample excerpts
            excerpts = []
            for r in results[:2]:
                excerpt = r["content"][:200].strip().replace("\n", " ")
                if excerpt:
                    excerpts.append(excerpt)
            
            company_summary[category] = {
                "count": len(results),
                "has_data": len(results) > 0,
                "sample_excerpts": excerpts,
            }
        
        summary[company] = company_summary
    
    return {"summary": summary}


@router.get("/analysis/ai-investments")
async def get_ai_investments():
    """
    Search for AI and data center investment mentions aggregated by company.
    """
    # Search for AI-related content
    ai_results = search_documents(
        query="AI artificial intelligence machine learning GPU neural network deep learning",
        n_results=100,
    )
    
    # Search for data center content
    dc_results = search_documents(
        query="data center datacenter hyperscale cloud infrastructure server",
        n_results=100,
    )
    
    # Aggregate AI mentions by company
    ai_by_company = {}
    for doc in ai_results:
        company = doc["company"]
        content_lower = doc["content"].lower()
        if any(term in content_lower for term in ["ai", "artificial intelligence", "machine learning", "gpu", "neural", "deep learning"]):
            ai_by_company[company] = ai_by_company.get(company, 0) + 1
    
    # Aggregate data center mentions by company
    dc_by_company = {}
    for doc in dc_results:
        company = doc["company"]
        content_lower = doc["content"].lower()
        if any(term in content_lower for term in ["data center", "datacenter", "hyperscale", "cloud", "server farm"]):
            dc_by_company[company] = dc_by_company.get(company, 0) + 1
    
    # Combine into response format
    all_companies = set(ai_by_company.keys()) | set(dc_by_company.keys())
    mentions = [
        {
            "company": company,
            "ai_mentions": ai_by_company.get(company, 0),
            "data_center_mentions": dc_by_company.get(company, 0),
            "total": ai_by_company.get(company, 0) + dc_by_company.get(company, 0)
        }
        for company in sorted(all_companies)
    ]
    
    return {"mentions": mentions}


@router.get("/analysis/company/{ticker}")
async def get_company_analysis(ticker: str):
    """
    Get analysis data for a specific company.
    """
    ticker = ticker.upper()
    
    if ticker not in COMPANIES:
        raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
    
    company_name = COMPANIES[ticker]["name"].split()[0]
    
    # Get CapEx mentions for this company
    capex_results = search_documents(
        query=f"{company_name} capital expenditure investment property equipment",
        company_filter=company_name,
        n_results=20,
    )
    
    # Get AI mentions for this company
    ai_results = search_documents(
        query=f"{company_name} AI data center artificial intelligence investment",
        company_filter=company_name,
        n_results=20,
    )
    
    # Get recent filings
    collection = get_collection()
    filings_result = collection.get(
        where={"company": company_name},
        include=["metadatas"],
        limit=100,
    )
    
    # Deduplicate filings
    seen = set()
    filings = []
    for meta in filings_result.get("metadatas", []):
        source = meta.get("source_file", "")
        if source not in seen:
            seen.add(source)
            filings.append({
                "source": source,
                "type": meta.get("filing_type", "Unknown"),
                "fiscal_year": meta.get("fiscal_year", "Unknown"),
                "quarter": meta.get("quarter", ""),
            })
    
    return {
        "ticker": ticker,
        "company": company_name,
        "total_documents": len(filings),
        "capex_mentions": [
            {
                "source": r["source"],
                "fiscal_year": r["fiscal_year"],
                "snippet": r["content"][:200],
            }
            for r in capex_results[:10]
        ],
        "ai_mentions": [
            {
                "source": r["source"],
                "fiscal_year": r["fiscal_year"],
                "snippet": r["content"][:200],
            }
            for r in ai_results[:10]
        ],
        "filings": filings[:20],
    }


@router.get("/analysis/search")
async def search_analysis(
    query: str,
    company: str = None,
    filing_type: str = None,
    limit: int = 20,
):
    """
    Custom search across documents.
    """
    results = search_documents(
        query=query,
        company_filter=company,
        filing_type_filter=filing_type,
        n_results=limit,
    )
    
    return {
        "query": query,
        "filters": {
            "company": company,
            "filing_type": filing_type,
        },
        "results": [
            {
                "company": r["company"],
                "source": r["source"],
                "filing_type": r["filing_type"],
                "fiscal_year": r["fiscal_year"],
                "quarter": r["quarter"],
                "similarity": r["similarity"],
                "content": r["content"][:500],
            }
            for r in results
        ],
        "total": len(results),
    }
