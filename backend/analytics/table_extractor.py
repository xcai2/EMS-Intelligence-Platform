"""
PDF Table Extractor for financial data.
Extracts tables from SEC filings and earnings presentations.
"""
import re
from typing import Optional
from pathlib import Path
from collections import defaultdict

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

from backend.core.config import TRACKED_COMPANY_NAMES
from backend.rag.retriever import search_documents


def extract_tables_from_pdf(pdf_path: str) -> list[dict]:
    """
    Extract tables from a PDF file using pdfplumber.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        List of extracted tables with metadata
    """
    if not HAS_PDFPLUMBER:
        return [{"error": "pdfplumber not installed. Run: pip install pdfplumber"}]
    
    tables = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_tables = page.extract_tables()
                
                for table_idx, table in enumerate(page_tables):
                    if table and len(table) > 1:
                        # Clean up table data
                        cleaned_table = []
                        for row in table:
                            cleaned_row = [
                                cell.strip() if cell else "" 
                                for cell in row
                            ]
                            if any(cleaned_row):  # Skip empty rows
                                cleaned_table.append(cleaned_row)
                        
                        if cleaned_table:
                            tables.append({
                                "page": page_num,
                                "table_index": table_idx,
                                "headers": cleaned_table[0] if cleaned_table else [],
                                "rows": cleaned_table[1:] if len(cleaned_table) > 1 else [],
                                "row_count": len(cleaned_table) - 1,
                            })
    except Exception as e:
        return [{"error": f"Failed to extract tables: {str(e)}"}]
    
    return tables


def extract_financial_data_from_text(text: str) -> dict:
    """
    Extract financial metrics from text using regex patterns.
    Works with any text content (HTML, PDF extracted text, etc.)
    """
    patterns = {
        "revenue": [
            r"(?:net\s+)?revenue[s]?\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
            r"\$?([\d,.]+)\s*(billion|million|B|M)?\s+(?:in\s+)?(?:net\s+)?revenue",
        ],
        "net_income": [
            r"net\s+income\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
            r"\$?([\d,.]+)\s*(billion|million|B|M)?\s+(?:in\s+)?net\s+income",
        ],
        "operating_income": [
            r"operating\s+income\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
        ],
        "gross_profit": [
            r"gross\s+profit\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
        ],
        "capex": [
            r"capital\s+expenditure[s]?\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
            r"capex\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
            r"\$?([\d,.]+)\s*(billion|million|B|M)?\s+(?:in\s+)?(?:capital\s+expenditure|capex)",
            r"purchases?\s+of\s+property\s+(?:and|,)\s*(?:plant\s+(?:and|,)\s*)?equipment\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
            r"acquisition\s+of\s+property\s*,?\s*plant\s+(?:and|,)\s*equipment\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
            r"additions?\s+to\s+property\s+(?:and|,)\s*equipment\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
            r"capital\s+spending\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
            r"payments?\s+for\s+property\s+(?:and|,)\s*equipment\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
        ],
        "free_cash_flow": [
            r"free\s+cash\s+flow\s*(?:of|was|were|:)?\s*\$?([\d,.]+)\s*(billion|million|B|M)?",
        ],
        "eps": [
            r"(?:diluted\s+)?(?:earnings\s+per\s+share|eps)\s*(?:of|was|were|:)?\s*\$?([\d,.]+)",
            r"\$?([\d,.]+)\s+(?:diluted\s+)?(?:earnings\s+per\s+share|eps)",
        ],
        "gross_margin": [
            r"gross\s+margin\s*(?:of|was|were|:)?\s*([\d,.]+)\s*%",
        ],
        "operating_margin": [
            r"operating\s+margin\s*(?:of|was|were|:)?\s*([\d,.]+)\s*%",
        ],
    }
    
    results = {}
    text_lower = text.lower()
    
    for metric, metric_patterns in patterns.items():
        for pattern in metric_patterns:
            match = re.search(pattern, text_lower)
            if match:
                value = match.group(1).replace(",", "")
                try:
                    value = abs(float(value))
                    # Apply multiplier if present
                    if len(match.groups()) > 1 and match.group(2):
                        multiplier = match.group(2).lower()
                        if multiplier in ["billion", "b"]:
                            value *= 1_000_000_000
                        elif multiplier in ["million", "m"]:
                            value *= 1_000_000
                    results[metric] = value
                    break
                except ValueError:
                    continue
    
    return results


def extract_company_financials(company: str, fiscal_year: Optional[str] = None) -> dict:
    """
    Extract financial data for a company from document context.
    
    Args:
        company: Company name
        fiscal_year: Optional fiscal year filter
        
    Returns:
        Dict with extracted financial metrics
    """
    # Search for financial documents
    query = f"{company} revenue net income operating income gross profit capital expenditure"
    
    docs = search_documents(
        query=query,
        company_filter=company,
        n_results=30,
    )
    
    if not docs:
        return {"company": company, "error": "No documents found"}
    
    # Aggregate financials by fiscal year
    financials_by_year = defaultdict(lambda: defaultdict(list))
    
    for doc in docs:
        year = doc.get("fiscal_year", "Unknown")
        if fiscal_year and year != fiscal_year:
            continue
            
        extracted = extract_financial_data_from_text(doc["content"])
        
        for metric, value in extracted.items():
            financials_by_year[year][metric].append(value)
    
    # Calculate averages/medians for each year
    results = {
        "company": company,
        "fiscal_years": {},
    }
    
    for year, metrics in financials_by_year.items():
        year_data = {}
        for metric, values in metrics.items():
            if values:
                # Use median to avoid outliers
                sorted_values = sorted(values)
                mid = len(sorted_values) // 2
                year_data[metric] = sorted_values[mid]
        
        if year_data:
            results["fiscal_years"][year] = year_data
    
    return results


def extract_capex_breakdown(company: str) -> dict:
    """
    Extract detailed CapEx breakdown by category.
    """
    # Search for detailed CapEx content
    docs = search_documents(
        query=f"{company} capital expenditure property plant equipment machinery technology infrastructure data center",
        company_filter=company,
        n_results=50,
    )
    
    if not docs:
        return {"company": company, "error": "No documents found"}
    
    # Categories to look for
    categories = {
        "property_plant_equipment": [
            r"property[,\s]+plant[,\s]+(?:and\s+)?equipment",
            r"pp&e",
            r"ppe",
        ],
        "technology_infrastructure": [
            r"technology\s+infrastructure",
            r"it\s+infrastructure",
            r"technology\s+investments?",
        ],
        "data_center": [
            r"data\s+center",
            r"datacenter",
            r"server\s+infrastructure",
        ],
        "machinery_equipment": [
            r"machinery\s+(?:and\s+)?equipment",
            r"manufacturing\s+equipment",
            r"production\s+equipment",
        ],
        "facility_expansion": [
            r"facility\s+expansion",
            r"plant\s+expansion",
            r"manufacturing\s+expansion",
        ],
    }
    
    category_mentions = defaultdict(int)
    category_quotes: dict = defaultdict(list)

    for doc in docs:
        content = doc["content"]
        content_lower = content.lower()

        for category, patterns in categories.items():
            for pattern in patterns:
                for match in re.finditer(pattern, content_lower):
                    category_mentions[category] += 1
                    if len(category_quotes[category]) < 3:
                        start = max(0, match.start() - 20)
                        end = min(len(content), match.end() + 180)
                        snippet = content[start:end].strip().replace("\n", " ")
                        if snippet and snippet not in category_quotes[category]:
                            category_quotes[category].append(snippet)

    # Calculate summary
    total_mentions = sum(category_mentions.values())
    breakdown = {}

    for category in categories:
        mentions = category_mentions[category]
        breakdown[category] = {
            "mentions": mentions,
            "percentage_of_mentions": round(mentions / total_mentions * 100, 1) if total_mentions > 0 else 0,
            "sample_quotes": category_quotes[category],
        }
    
    return {
        "company": company,
        "total_mentions": total_mentions,
        "breakdown": breakdown,
        "primary_focus": max(category_mentions, key=category_mentions.get) if category_mentions else None,
    }


def compare_company_financials() -> dict:
    """
    Compare extracted financials across all companies.
    """
    companies = list(TRACKED_COMPANY_NAMES)
    
    results = {
        "companies": [],
        "latest_data": {},
    }
    
    for company in companies:
        financials = extract_company_financials(company)
        capex = extract_capex_breakdown(company)
        
        company_data = {
            "company": company,
            "financials": financials.get("fiscal_years", {}),
            "capex_focus": capex.get("primary_focus"),
            "capex_breakdown": capex.get("breakdown", {}),
        }
        
        results["companies"].append(company_data)
        
        # Get latest year data
        if financials.get("fiscal_years"):
            latest_year = max(financials["fiscal_years"].keys())
            results["latest_data"][company] = {
                "year": latest_year,
                "data": financials["fiscal_years"][latest_year],
            }
    
    return results
