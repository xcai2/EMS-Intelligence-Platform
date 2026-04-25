"""
Vector retrieval module for RAG pipeline.
Handles document search with year detection, recency boosting, and LLM re-ranking.

LLM Reranking (inspired by RAG-Challenge-2):
- First retrieve more candidates than needed (e.g., 3x)
- Use LLM to score relevance of each candidate to the query
- Return top-k based on LLM scores, not just vector similarity
"""
import re
import json
from datetime import date
from typing import Optional

from openai import OpenAI

from backend.core.database import (
    get_collection, 
    get_company_collection, 
    has_company_collections,
    embed_text,
)
from backend.core.config import OPENAI_API_KEY, RERANK_MODEL, TRACKED_COMPANY_NAMES


def _extract_year_from_query(query: str) -> Optional[str]:
    """Extract a 4-digit year from the query string."""
    match = re.search(r'\b(20[1-3]\d)\b', query)
    if match:
        return match.group(1)

    fy_match = re.search(r'\bFY\s*(\d{2,4})\b', query, re.IGNORECASE)
    if fy_match:
        y = fy_match.group(1)
        if len(y) == 2:
            return f"20{y}"
        return y

    return None


def _fiscal_year_variants(year: str) -> list[str]:
    """Generate all common fiscal-year string variants for a given year."""
    short = year[-2:]
    return [
        year,
        f"FY{year}",
        f"FY{short}",
        f"fiscal {year}",
        f"fiscal year {year}",
        f"Fiscal Year {year}",
        f"FY {year}",
        f"FY {short}",
    ]


def _should_auto_detect_year(query: str) -> bool:
    """Determine whether the query contains an explicit year reference."""
    if re.search(r'\b(20[1-3]\d)\b', query):
        return True
    if re.search(r'\bFY\s*\d{2,4}\b', query, re.IGNORECASE):
        return True
    if re.search(r'\bfiscal\s+(year\s+)?\d{4}\b', query, re.IGNORECASE):
        return True
    return False


_RECENCY_KEYWORDS = {
    "latest", "recent", "newest", "most recent", "current", "last quarter",
    "this year", "this quarter", "updated", "new",
}

# ---------------------------------------------------------------------------
# QUARTER RANGE EXTRACTION
# ---------------------------------------------------------------------------

# 各公司财年开始月份
COMPANY_FY_START = {
    "Flex": 4,      # 4月开始，3月结束
    "Jabil": 9,     # 9月开始，8月结束
    "Celestica": 1, # 自然年
    "Benchmark": 1, # 自然年
    "Sanmina": 10,  # 10月开始，9月结束
}

_QUARTER_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
}


def _extract_quarter_range(query: str) -> Optional[int]:
    """
    从问题中提取用户想要多少个季度的数据。
    支持以下变体：
      "last three quarters"      -> 3
      "past 3 quarters"          -> 3
      "recent 3 quarters"        -> 3
      "last few quarters"        -> 3 (默认)
      "last several quarters"    -> 3 (默认)
      "last quarter"             -> 1
      "recent quarter"           -> 1
    """
    q_lower = query.lower()

    # 变体1: last/past/previous/prior/recent + 英文数字 + quarter(s)
    pattern = r'\b(?:last|past|previous|prior|recent)\s+(\w+)\s+quarters?\b'
    match = re.search(pattern, q_lower)
    if match:
        word = match.group(1)
        count = _QUARTER_COUNT_WORDS.get(word)
        if count:
            return count

    # 变体2: last/past/previous/prior/recent + 阿拉伯数字 + quarter(s)
    digit_match = re.search(
        r'\b(?:last|past|previous|prior|recent)\s+(\d+)\s+quarters?\b',
        q_lower
    )
    if digit_match:
        count = int(digit_match.group(1))
        if 1 <= count <= 12:
            return count

    # 变体3: "last few/several/some/multiple quarters" -> 默认 3
    if re.search(
        r'\b(?:last|past|previous|prior|recent)\s+(?:few|several|some|multiple)\s+quarters?\b',
        q_lower
    ):
        return 3

    # 变体4: 单独的 "last/recent quarter"（单数）
    if re.search(r'\b(?:last|past|previous|prior|recent)\s+quarter\b', q_lower):
        return 1


def _extract_explicit_periods(query: str) -> list[tuple[str, str]]:
    """
    解析用户明确指定的季度范围。
    支持：
      "FY2025 Q1 to Q3"       -> [("2025","Q1"), ("2025","Q2"), ("2025","Q3")]
      "FY2025 Q1, Q2, Q3"     -> [("2025","Q1"), ("2025","Q2"), ("2025","Q3")]
      "Q2 and Q3 FY2024"      -> [("2024","Q2"), ("2024","Q3")]
      "FY24 Q3 and FY25 Q1"   -> [("2024","Q3"), ("2025","Q1")]
      "Q1 to Q3"              -> [("","Q1"), ("","Q2"), ("","Q3")]
      "Q1-Q3"                 -> [("","Q1"), ("","Q2"), ("","Q3")]
    没有匹配返回空列表。
    """
    q_lower = query.lower()
    periods = []

    # 模式1: FY2025 Q1 to/through/- Q3 (同一财年内的连续范围)
    m = re.search(
        r'\bfy\s*(\d{2,4})\s+q([1-4])\s*(?:to|through|-)\s*q([1-4])\b',
        q_lower
    )
    if m:
        year = m.group(1)
        year = f"20{year}" if len(year) == 2 else year
        start_q = int(m.group(2))
        end_q = int(m.group(3))
        for q in range(start_q, end_q + 1):
            periods.append((year, f"Q{q}"))
        return periods

    # 模式2: Q1 to Q3 / Q1-Q3 / Q1 through Q3 (没有指定财年)
    m2 = re.search(r'\bq([1-4])\s*(?:to|through|-)\s*q([1-4])\b', q_lower)
    if m2:
        start_q = int(m2.group(1))
        end_q = int(m2.group(2))
        if end_q >= start_q:
            for q in range(start_q, end_q + 1):
                periods.append(("", f"Q{q}"))
            return periods

    # 模式3: FY2024 Q1, Q2, Q3 或 Q2 and Q3 FY2024 (同一财年，列举)
    # 只有一个 FY 时才走这里，多个 FY 留给模式4处理
    all_years = re.findall(r'\bfy\s*(\d{2,4})\b', q_lower)
    q_matches = re.findall(r'\bq([1-4])\b', q_lower)
    if len(all_years) == 1 and q_matches:
        year = all_years[0]
        year = f"20{year}" if len(year) == 2 else year
        for q in q_matches:
            p = (year, f"Q{q}")
            if p not in periods:
                periods.append(p)
        return periods

    # 模式4: FY24 Q3 and FY25 Q1 (跨财年，各自指定)
    # 先找所有 FY+year 的位置，再找紧跟其后的 Q
    cross_matches = re.findall(r'\bfy\s*(\d{2,4})\b[^fy]*?\bq([1-4])\b', q_lower)
    if len(cross_matches) >= 2:
        for year, q in cross_matches:
            year = f"20{year}" if len(year) == 2 else year
            p = (year, f"Q{q}")
            if p not in periods:
                periods.append(p)
        return periods

    return periods


def _extract_quarters_ago(query: str, company: str = None) -> list[tuple[str, str]]:
    """
    解析 "N quarters ago" 类型的相对时间表达。
    返回那一个特定季度的 (fiscal_year, quarter)。
    例如:
      "two quarters ago"   -> 2个季度前的那个季度
      "3 quarters ago"     -> 3个季度前的那个季度
      "last quarter"       -> 已在 _extract_quarter_range 处理，这里不重复
    """
    q_lower = query.lower()

    # 匹配 "N quarters ago"
    pattern = r'\b(\w+)\s+quarters?\s+ago\b'
    match = re.search(pattern, q_lower)
    if not match:
        return []

    word = match.group(1)
    count = _QUARTER_COUNT_WORDS.get(word)
    if not count:
        return []

    # 从今天往前数 count 个季度，再多数1个跳过当前季度
    today = date.today()
    fy_start = COMPANY_FY_START.get(company, 1) if company else 1

    month = today.month
    year = today.year

    # 先跳过当前季度
    month -= 3
    if month <= 0:
        month += 12
        year -= 1

    # 再往前数 count 个季度
    for _ in range(count - 1):
        month -= 3
        if month <= 0:
            month += 12
            year -= 1

    fy_month = (month - fy_start) % 12
    q_num = fy_month // 3 + 1
    if fy_start == 1:
        fy_year = year
    elif month >= fy_start:
        fy_year = year + 1
    else:
        fy_year = year
    fy_label = f"FY{fy_year % 100:02d}"

    return [(fy_label, f"Q{q_num}")]


def _get_recent_fiscal_periods(n_quarters: int, company: str = None) -> list[tuple[str, str]]:
    """
    根据今天日期，计算过去 N 个已完成季度对应的 (fiscal_year, quarter) 列表。
    没有指定公司时按自然年（1月开始）计算。
    """
    today = date.today()
    fy_start = COMPANY_FY_START.get(company, 1) if company else 1

    periods = []
    year = today.year
    month = today.month

    # 多算一个，用来跳过当前还没结束的季度
    for _ in range(n_quarters + 1):
        fy_month = (month - fy_start) % 12      # 在财年内是第几个月（0-based）
        q_num = fy_month // 3 + 1               # 第几季度

        # FY label logic:
        # - Calendar year (fy_start=1): FY = current year
        # - month >= fy_start: we just started a new FY that ends NEXT calendar year → FY = year+1
        # - month < fy_start:  we are in the FY that started LAST calendar year → FY = year
        if fy_start == 1:
            fy_year = year
        elif month >= fy_start:
            fy_year = year + 1  # FY started this calendar year, ends next
        else:
            fy_year = year      # FY started last calendar year, ends this year

        # Format to match ChromaDB metadata: "FY25", "FY26", etc.
        fy_label = f"FY{fy_year % 100:02d}"
        periods.append((fy_label, f"Q{q_num}"))

        # 往前退3个月
        month -= 3
        if month <= 0:
            month += 12
            year -= 1

    # 去重、跳过第一个（当前进行中的季度）、取 N 个
    seen = []
    for p in periods:
        if p not in seen:
            seen.append(p)
    return seen[1:n_quarters + 1]


def _build_quarter_range_note(n_quarters: int, company: str = None) -> str:
    """
    生成当前季度未完结的提示，注入给 LLM。
    例如: [TIME RANGE NOTE] Current quarter FY2026 Q1 is still in progress
          and has been excluded. The following covers the last 3 completed
          quarters: FY2025 Q4, FY2025 Q3, FY2025 Q2.
    """
    today = date.today()
    fy_start = COMPANY_FY_START.get(company, 1) if company else 1

    month = today.month
    year = today.year

    fy_month = (month - fy_start) % 12
    q_num = fy_month // 3 + 1
    if fy_start == 1:
        fy_year = year
    elif month >= fy_start:
        fy_year = year + 1
    else:
        fy_year = year
    current_fy = f"FY{fy_year % 100:02d}"
    current_q = f"Q{q_num}"

    target_periods = _get_recent_fiscal_periods(n_quarters, company)
    # Show oldest → newest for natural chronological order
    reversed_periods = list(reversed(target_periods))
    periods_str = ", ".join(f"{fy} {q}" for fy, q in reversed_periods)

    return (
        f"[TIME RANGE NOTE] The current quarter ({current_fy} {current_q}) "
        f"is still in progress and has been excluded. "
        f"The following data covers the last {n_quarters} completed quarter(s): "
        f"{periods_str}."
    )

# ---------------------------------------------------------------------------
# CAPEX SYNONYM EXPANSION
# Different companies use different labels for the same concept
# ---------------------------------------------------------------------------
CAPEX_SYNONYMS = [
    "capital expenditure",
    "capital expenditures", 
    "capex",
    "cap ex",
    "purchases of property and equipment",
    "purchase of property and equipment",
    "acquisition of property plant and equipment",
    "acquisition of property, plant and equipment",
    "additions to property and equipment",
    "capital spending",
    "payments for property and equipment",
    "property plant equipment purchases",
    "PPE purchases",
    "fixed asset purchases",
    "investing in property and equipment",
]

# Keywords that trigger CapEx expansion
CAPEX_TRIGGERS = {"capex", "cap ex", "capital expenditure", "capital expenditures", "capital spending"}

# Other financial term synonyms
FINANCIAL_SYNONYMS = {
    "revenue": ["revenue", "net revenue", "net sales", "total revenue", "sales"],
    "profit": ["profit", "net income", "earnings", "net profit", "income from operations"],
    "margin": ["margin", "gross margin", "operating margin", "profit margin", "gross profit margin"],
    "debt": ["debt", "long-term debt", "total debt", "borrowings", "indebtedness"],
    "cash": ["cash", "cash and cash equivalents", "cash position", "liquidity"],
}


def _expand_capex_query(query: str) -> str:
    """
    If query mentions CapEx-related terms, expand with synonyms for better retrieval.
    """
    query_lower = query.lower()
    
    # Check if query contains CapEx triggers
    if any(trigger in query_lower for trigger in CAPEX_TRIGGERS):
        # Add key synonyms to the query for better vector matching
        expansion = " ".join([
            "purchases of property and equipment",
            "capital expenditures",
            "property plant equipment",
        ])
        return f"{query} {expansion}"
    
    return query


def _expand_financial_terms(query: str) -> str:
    """
    Expand other financial terms with their synonyms.
    """
    query_lower = query.lower()
    expansions = []
    
    for term, synonyms in FINANCIAL_SYNONYMS.items():
        if term in query_lower:
            # Add a few key synonyms
            expansions.extend(synonyms[:3])
    
    if expansions:
        return f"{query} {' '.join(expansions)}"
    
    return query


def expand_query(query: str) -> str:
    """
    Apply all query expansions for better retrieval.
    """
    expanded = _expand_capex_query(query)
    expanded = _expand_financial_terms(expanded)
    return expanded


# ---------------------------------------------------------------------------
# QUERY ROUTING (RAG-Challenge-2 Style)
# ---------------------------------------------------------------------------

# Known companies in our database
KNOWN_COMPANIES = list(TRACKED_COMPANY_NAMES)


def extract_companies_from_query(query: str) -> list[str]:
    """
    Extract company names mentioned in the query.
    Returns list of matched company names.
    """
    query_lower = query.lower()
    found = []
    for company in KNOWN_COMPANIES:
        if company.lower() in query_lower:
            found.append(company)
    return found


def detect_query_type(query: str) -> dict:
    """
    Analyze query to determine its type and routing strategy.
    
    Returns dict with:
    - type: "single_company" | "multi_company" | "cross_company"
    - companies: list of detected companies
    - is_comparison: whether this is a comparison query
    - suggested_sections: sections to boost based on query content
    """
    companies = extract_companies_from_query(query)
    query_lower = query.lower()
    
    # Detect comparison keywords
    comparison_keywords = [
        "compare", "comparison", "versus", "vs", "vs.", "differ",
        "which company", "who has higher", "who has more", "who has lower",
        "rank", "ranking", "between", "across companies"
    ]
    is_comparison = any(kw in query_lower for kw in comparison_keywords)
    
    # Detect suggested sections based on content
    suggested_sections = []
    
    if any(term in query_lower for term in CAPEX_TRIGGERS):
        suggested_sections.extend([
            "Capital Expenditures",
            "Cash Flow Statement", 
            "Liquidity and Capital Resources",
        ])
    
    if "revenue" in query_lower or "sales" in query_lower or "income" in query_lower:
        suggested_sections.append("Income Statement")
        suggested_sections.append("Results of Operations")
    
    if "asset" in query_lower or "liabilit" in query_lower or "equity" in query_lower:
        suggested_sections.append("Balance Sheet")
    
    if "risk" in query_lower:
        suggested_sections.append("Item 1A. Risk Factors")
    
    if "business" in query_lower and "overview" in query_lower:
        suggested_sections.append("Item 1. Business")
    
    # Determine query type
    if len(companies) == 0:
        query_type = "cross_company"
    elif len(companies) == 1 and not is_comparison:
        query_type = "single_company"
    else:
        query_type = "multi_company"
    
    return {
        "type": query_type,
        "companies": companies,
        "is_comparison": is_comparison,
        "suggested_sections": suggested_sections,
    }


def route_query(query: str) -> dict:
    """
    Route a query to the appropriate search strategy.
    
    For multi-company comparisons, this can be used to split the query
    into sub-queries (one per company).
    
    Returns:
        - strategy: "direct" | "split_by_company"
        - filters: suggested filters
        - boost_sections: sections to boost
        - sub_queries: for split strategy, the individual company queries
    """
    analysis = detect_query_type(query)
    
    if analysis["type"] == "single_company":
        return {
            "strategy": "direct",
            "filters": {"company": analysis["companies"][0]},
            "boost_sections": analysis["suggested_sections"],
            "sub_queries": None,
        }
    
    elif analysis["type"] == "multi_company" and analysis["is_comparison"]:
        # Split into sub-queries for each company
        sub_queries = []
        for company in analysis["companies"]:
            # Create a simplified query focused on this company
            sub_query = re.sub(
                r'\b(' + '|'.join(KNOWN_COMPANIES) + r')\b',
                company,
                query,
                flags=re.IGNORECASE,
            )
            sub_queries.append({
                "query": sub_query,
                "company": company,
            })
        
        return {
            "strategy": "split_by_company",
            "filters": None,
            "boost_sections": analysis["suggested_sections"],
            "sub_queries": sub_queries,
        }
    
    else:  # cross_company
        return {
            "strategy": "direct",
            "filters": None,
            "boost_sections": analysis["suggested_sections"],
            "sub_queries": None,
        }


def _wants_latest(query: str) -> bool:
    """Check if the query implies the user wants the most recent data."""
    q_lower = query.lower()
    for kw in _RECENCY_KEYWORDS:
        if kw in q_lower:
            return True
    if re.search(r'\brecent\b', q_lower):
        return True
    return False


def _fy_sort_key(doc: dict) -> str:
    """Sort key that orders documents by fiscal year descending."""
    fy = doc.get("fiscal_year", "") or ""
    match = re.search(r'(\d{4})', str(fy))
    return match.group(1) if match else "0000"


def _quarter_sort_key(doc: dict) -> int:
    """Sort key that orders documents by quarter descending."""
    q = doc.get("quarter", "") or ""
    match = re.search(r'Q(\d)', str(q))
    return int(match.group(1)) if match else 0


# ---------------------------------------------------------------------------
# LLM RERANKING (inspired by RAG-Challenge-2)
# ---------------------------------------------------------------------------

RERANK_SYSTEM_PROMPT = """You are a relevance scoring expert for financial document retrieval in the EMS (Electronics Manufacturing Services) industry.
Your task is to score how relevant each document passage is to answering the user's question.

Score each passage from 0 to 10:
- 10: Directly answers the question with specific data/facts
- 7-9: Highly relevant, contains key information needed
- 4-6: Somewhat relevant, provides useful context
- 1-3: Marginally relevant, tangentially related
- 0: Not relevant at all

=== CRITICAL: CapEx Synonym Awareness ===
Different companies use different labels for Capital Expenditure (CapEx):
- "Purchases of property and equipment" (Flex)
- "Acquisition of property, plant and equipment" (Jabil)
- "Purchase of property, plant and equipment" (Celestica)
- "Purchases of property, plant and equipment" (Benchmark)
- "Capital expenditures" (Sanmina)
- "Additions to property and equipment"
- "Capital spending"
- "Payments for property and equipment"
ALL of these refer to CapEx. Score them highly if the user asks about CapEx!

Consider:
- Does it contain the specific data/metrics asked about?
- Is it from the right time period (fiscal year/quarter)?
- Is it about the right company?
- Does it provide actionable information for the question?

Respond ONLY with a JSON array of scores in the same order as the passages.
Example: [8, 3, 10, 5, 2]"""


# Weights for combining vector and LLM scores (RAG-Challenge-2 style)
VECTOR_WEIGHT = 0.3
LLM_WEIGHT = 0.7


def rerank_with_llm(
    query: str,
    docs: list[dict],
    top_k: int = 10,
    batch_size: int = 10,
    use_weighted_scoring: bool = True,
) -> list[dict]:
    """
    Use LLM to rerank retrieved documents by relevance to the query.
    
    Uses weighted scoring (RAG-Challenge-2 style):
    - final_score = VECTOR_WEIGHT * vector_score + LLM_WEIGHT * llm_score
    
    Uses gpt-4o-mini for cost efficiency (reranking is called frequently).
    
    Args:
        query: The user's question
        docs: List of retrieved documents with 'content' and metadata
        top_k: Number of top documents to return after reranking
        batch_size: Number of documents to score per LLM call
        use_weighted_scoring: Combine vector and LLM scores (default: True)
        
    Returns:
        Reranked list of documents (top_k most relevant)
    """
    if not OPENAI_API_KEY:
        return docs[:top_k]
    
    if len(docs) <= top_k:
        return docs
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # Score documents in batches
    scored_docs = []
    
    for batch_start in range(0, len(docs), batch_size):
        batch = docs[batch_start:batch_start + batch_size]
        
        # Build passage list for LLM (include section info for better context)
        passages = []
        for i, doc in enumerate(batch):
            section = doc.get('section_header', '')
            section_str = f" | {section}" if section else ""
            header = f"[{doc.get('company', '?')} | {doc.get('filing_type', '?')} | {doc.get('fiscal_year', '?')} {doc.get('quarter', '')}{section_str}]"
            content_preview = doc.get('content', '')[:600]
            passages.append(f"Passage {i+1} {header}:\n{content_preview}")
        
        passages_text = "\n\n---\n\n".join(passages)
        
        user_prompt = f"""Question: {query}

Please score the relevance of each passage below (0-10):

{passages_text}

Return ONLY a JSON array of {len(batch)} scores, e.g., [8, 3, 10, ...]"""

        try:
            response = client.chat.completions.create(
                model=RERANK_MODEL,  # Uses gpt-4o-mini for cost efficiency
                max_tokens=200,
                messages=[
                    {"role": "system", "content": RERANK_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Parse JSON scores
            # Handle potential markdown code blocks
            if "```" in response_text:
                match = re.search(r'\[[\d,\s\.]+\]', response_text)
                response_text = match.group(0) if match else "[]"
            
            scores = json.loads(response_text)
            
            # Assign scores to documents with weighted combination
            for doc, score in zip(batch, scores):
                llm_score = float(score) if isinstance(score, (int, float)) else 0
                llm_score_normalized = llm_score / 10.0  # Normalize to 0-1
                
                doc["llm_score"] = llm_score
                
                if use_weighted_scoring:
                    # Weighted average of vector and LLM scores (RAG-Challenge-2 style)
                    vector_score = doc.get("vector_score", doc.get("similarity", 0))
                    combined_score = VECTOR_WEIGHT * vector_score + LLM_WEIGHT * llm_score_normalized
                    doc["rerank_score"] = combined_score
                else:
                    doc["rerank_score"] = llm_score_normalized
                
                scored_docs.append(doc)
                
        except Exception as e:
            # If reranking fails, use original similarity scores
            for doc in batch:
                doc["rerank_score"] = doc.get("vector_score", doc.get("similarity", 0))
                doc["llm_score"] = None
                scored_docs.append(doc)
    
    # Sort by combined rerank score descending
    scored_docs.sort(key=lambda d: d.get("rerank_score", 0), reverse=True)
    
    return scored_docs[:top_k]


def search_documents(
    query: str,
    company_filter: Optional[str] = None,
    filing_type_filter: Optional[str] = None,
    section_filter: Optional[str] = None,
    n_results: int = 20,
    use_reranking: bool = False,
    boost_sections: Optional[list[str]] = None,
) -> list[dict]:
    """
    Search ChromaDB for relevant document chunks with optional LLM re-ranking.

    Pipeline (RAG-Challenge-2 style):
    1. Vector search to get initial candidates (3x n_results)
    2. Apply metadata filters (company, filing_type, section)
    3. Apply year/recency/section boosting
    4. LLM reranking with weighted scoring
    5. Parent document retrieval (expand child → parent context)
    
    Args:
        query: Search query
        company_filter: Optional company to filter by
        filing_type_filter: Optional filing type to filter by
        section_filter: Optional section header to filter by (e.g., "Cash Flow Statement")
        n_results: Number of final results to return
        use_reranking: Whether to use LLM reranking (default: True)
        boost_sections: List of section headers to boost (e.g., ["Capital Expenditures", "Cash Flow Statement"])
    """
    # Expand query with synonyms for better retrieval (CapEx, revenue, etc.)
    expanded_query = expand_query(query)
    query_embedding = embed_text(expanded_query)
    
    # Determine which collection(s) to search
    # If per-company collections exist and company filter is specified, use company collection
    use_company_collection = has_company_collections() and company_filter

    if use_company_collection:
        # RAG-Challenge-2 style: search only the company's collection
        collection = get_company_collection(company_filter)
        if collection.count() == 0:
            return []
        
        # Build metadata filters (no need for company filter since we're in company collection)
        filters = []
        if filing_type_filter:
            filters.append({"filing_type": filing_type_filter})
        if section_filter:
            filters.append({"section_header": section_filter})
    elif has_company_collections() and not company_filter:
        # Per-company collections exist but no company filter — search all companies
        from backend.core.database import KNOWN_COMPANIES
        all_docs = []
        per_company_n = max(n_results, 10)
        for company in KNOWN_COMPANIES:
            try:
                col = get_company_collection(company)
                if col.count() == 0:
                    continue
                sub_filters = []
                if filing_type_filter:
                    sub_filters.append({"filing_type": filing_type_filter})
                if section_filter:
                    sub_filters.append({"section_header": section_filter})
                where = {"$and": sub_filters} if len(sub_filters) > 1 else (sub_filters[0] if sub_filters else None)
                query_embedding = embed_text(query)
                kwargs = {"query_embeddings": [query_embedding], "n_results": per_company_n, "include": ["documents", "metadatas", "distances"]}
                if where:
                    kwargs["where"] = where
                results = col.query(**kwargs)
                docs_list = results.get("documents", [[]])[0]
                metas_list = results.get("metadatas", [[]])[0]
                dists_list = results.get("distances", [[]])[0]
                for doc, meta, dist in zip(docs_list, metas_list, dists_list):
                    similarity = 1 - dist
                    all_docs.append({**meta, "content": doc, "similarity": similarity})
            except Exception:
                continue
        all_docs.sort(key=lambda d: d["similarity"], reverse=True)
        docs = all_docs[:n_results]
        if use_reranking and len(all_docs) > n_results:
            docs = rerank_with_llm(query, all_docs, top_k=n_results)
        return docs
    else:
        # Legacy mode: search main collection with filters
        collection = get_collection()
        if collection.count() == 0:
            return []

        # Build metadata filters
        filters = []
        if company_filter:
            filters.append({"company": company_filter})
        if filing_type_filter:
            filters.append({"filing_type": filing_type_filter})
        if section_filter:
            filters.append({"section_header": section_filter})
    
    where_filter = None
    if len(filters) > 1:
        where_filter = {"$and": filters}
    elif len(filters) == 1:
        where_filter = filters[0]

    total = collection.count()
    # ChromaDB raises "Error finding id" above ~150 results on large collections;
    # also crashes when where=None is passed explicitly — omit the kwarg when unused.
    _CHROMA_MAX = 150
    fetch_n = min(n_results * 3, _CHROMA_MAX, max(1, total - 1)) if total > 1 else 1

    query_kwargs: dict = {
        "query_embeddings": [query_embedding],
        "n_results": fetch_n,
        "include": ["documents", "metadatas", "distances"],
    }
    if where_filter is not None:
        query_kwargs["where"] = where_filter

    try:
        results = collection.query(**query_kwargs)
    except Exception:
        # Retry without filter at a conservatively small count
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(50, max(1, total - 1)) if total > 1 else 1,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return []

    if not results or not results["documents"] or not results["documents"][0]:
        return []

    docs = []
    parent_ids_to_fetch = set()
    
    for doc_text, metadata, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        if metadata is None:
            metadata = {}
        similarity = 1 - distance
        chunk_type = metadata.get("chunk_type", "unknown")
        parent_id = metadata.get("parent_id", "")
        section_header = metadata.get("section_header", "")
        
        doc = {
            "content": doc_text,
            "company": metadata.get("company", "Unknown"),
            "source": metadata.get("source_file", metadata.get("source", "Unknown")),
            "filing_type": metadata.get("filing_type", "Unknown"),
            "fiscal_year": metadata.get("fiscal_year", "Unknown"),
            "quarter": metadata.get("quarter", ""),
            "similarity": round(similarity, 4),
            "vector_score": round(similarity, 4),  # Keep original for weighted scoring
            "chunk_type": chunk_type,
            "parent_id": parent_id,
            "section_header": section_header,
            "page_num": metadata.get("page_num", 0),
        }
        
        # Track parent IDs for Parent Document Retrieval
        if chunk_type == "child" and parent_id:
            parent_ids_to_fetch.add(parent_id)
        
        docs.append(doc)
    
    # === PARENT DOCUMENT RETRIEVAL (RAG-Challenge-2 Style) ===
    # Fetch full parent content for all child chunks
    if parent_ids_to_fetch:
        try:
            parent_results = collection.get(
                ids=list(parent_ids_to_fetch),
                include=["documents", "metadatas"],
            )
            
            # Build parent_id -> content mapping
            parent_content_map = {}
            if parent_results and parent_results["documents"]:
                for pid, pdoc in zip(parent_results["ids"], parent_results["documents"]):
                    parent_content_map[pid] = pdoc
            
            # Attach FULL parent content to child docs
            for doc in docs:
                if doc["chunk_type"] == "child":
                    parent_id = doc.get("parent_id", "")
                    if parent_id in parent_content_map:
                        # Store full parent content for context
                        doc["parent_content"] = parent_content_map[parent_id]
                        # Also add a preview to the content for reranking
                        parent_preview = parent_content_map[parent_id][:500]
                        doc["content"] = f"[Page/Section Context: {parent_preview}...]\n\n{doc['content']}"
        except Exception as e:
            # If parent fetch fails, continue without parent content
            pass

    # Year boosting
    detected_year = _extract_year_from_query(query)
    if detected_year:
        variants = _fiscal_year_variants(detected_year)
        for doc in docs:
            fy = str(doc.get("fiscal_year", ""))
            if any(v.lower() in fy.lower() for v in variants):
                doc["similarity"] += 0.15

    # 最高优先：用户说了 "N quarters ago"（特指某一个季度）
    ago_periods = _extract_quarters_ago(query, company_filter)
    explicit_periods = _extract_explicit_periods(query)
    n_quarters = _extract_quarter_range(query)
    if ago_periods:
        fy, q = ago_periods[0]
        note_doc = {
            "content": (
                f"[TIME RANGE NOTE] User is asking about a specific point in time: "
                f"FY{fy} {q}. Only return data from this quarter."
            ),
            "company": "SYSTEM",
            "source": "system",
            "filing_type": "SYSTEM",
            "fiscal_year": "",
            "quarter": "",
            "similarity": 99.0,
            "section_header": "",
            "page_num": 0,
        }
        docs.insert(0, note_doc)

        # 检测缺失
        found = any(
            str(doc.get("fiscal_year", "")) == fy and doc.get("quarter", "") == q
            for doc in docs
        )
        if not found:
            warning_doc = {
                "content": (
                    f"[DATA GAP WARNING] FY{fy} {q} was requested but has NO data "
                    f"in the database. Explicitly tell the user this data is unavailable."
                ),
                "company": "SYSTEM",
                "source": "system",
                "filing_type": "SYSTEM",
                "fiscal_year": "",
                "quarter": "",
                "similarity": 98.0,
                "section_header": "",
                "page_num": 0,
            }
            docs.insert(1, warning_doc)

        # boost / 降权
        for doc in docs:
            period = (str(doc.get("fiscal_year", "")), doc.get("quarter", ""))
            if period == (fy, q):
                doc["similarity"] += 0.25
            else:
                doc["similarity"] -= 0.15

    # 次优先：用户显式指定了具体 periods（如 "FY2025 Q1 to Q3"）
    elif explicit_periods:
        # 生成时间范围说明
        periods_str = ", ".join(
            f"FY{fy} {q}" if fy else q for fy, q in explicit_periods
        )
        note_doc = {
            "content": (
                f"[TIME RANGE NOTE] Using explicitly specified periods: {periods_str}."
            ),
            "company": "SYSTEM",
            "source": "system",
            "filing_type": "SYSTEM",
            "fiscal_year": "",
            "quarter": "",
            "similarity": 99.0,
            "section_header": "",
            "page_num": 0,
        }
        docs.insert(0, note_doc)

        # 检测缺失
        found_periods = set()
        for doc in docs:
            period = (str(doc.get("fiscal_year", "")), doc.get("quarter", ""))
            if period in explicit_periods:
                found_periods.add(period)

        missing_periods = [p for p in explicit_periods if p not in found_periods]
        if missing_periods:
            missing_str = ", ".join(
                f"FY{fy} {q}" if fy else q for fy, q in missing_periods
            )
            warning_doc = {
                "content": (
                    f"[DATA GAP WARNING] The following quarter(s) were requested "
                    f"but have NO data in the database: {missing_str}. "
                    f"You MUST explicitly tell the user that data for these quarters "
                    f"is not available."
                ),
                "company": "SYSTEM",
                "source": "system",
                "filing_type": "SYSTEM",
                "fiscal_year": "",
                "quarter": "",
                "similarity": 98.0,
                "section_header": "",
                "page_num": 0,
            }
            docs.insert(1, warning_doc)

        # boost / 降权
        for doc in docs:
            period = (str(doc.get("fiscal_year", "")), doc.get("quarter", ""))
            if period in explicit_periods:
                doc["similarity"] += 0.25
            else:
                doc["similarity"] -= 0.15

    # 其次：用户说了 last N quarters
    elif n_quarters is not None:
        # 根据今天日期精确计算目标 periods
        target_periods = _get_recent_fiscal_periods(n_quarters, company_filter)

        # 检测数据库中实际存在哪些 target periods
        found_periods = set()
        for doc in docs:
            period = (str(doc.get("fiscal_year", "")), doc.get("quarter", ""))
            if period in target_periods:
                found_periods.add(period)

        # 找出缺失的 periods
        missing_periods = [p for p in target_periods if p not in found_periods]

        # 生成当前季度未完结的提示，注入到 docs 最前面
        quarter_note = _build_quarter_range_note(n_quarters, company_filter)
        note_doc = {
            "content": quarter_note,
            "company": "SYSTEM",
            "source": "system",
            "filing_type": "SYSTEM",
            "fiscal_year": "",
            "quarter": "",
            "similarity": 99.0,
            "section_header": "",
            "page_num": 0,
        }
        docs.insert(0, note_doc)

        # 如果有缺失，再插入一条数据缺失警告
        if missing_periods:
            # fy already has "FY" prefix ("FY26") — don't prepend again
            missing_str = ", ".join(f"{fy} {q}" for fy, q in missing_periods)
            warning_doc = {
                "content": (
                    f"[DATA GAP WARNING] The following quarter(s) were requested "
                    f"but have NO data in the database: {missing_str}. "
                    f"You MUST explicitly tell the user that data for these quarters "
                    f"is not available."
                ),
                "company": "SYSTEM",
                "source": "system",
                "filing_type": "SYSTEM",
                "fiscal_year": "",
                "quarter": "",
                "similarity": 98.0,
                "section_header": "",
                "page_num": 0,
            }
            docs.insert(1, warning_doc)

        # boost / 降权
        for doc in docs:
            period = (str(doc.get("fiscal_year", "")), doc.get("quarter", ""))
            if period in target_periods:
                doc["similarity"] += 0.25
            else:
                doc["similarity"] -= 0.15

    elif _wants_latest(query):
        docs.sort(key=lambda d: (_fy_sort_key(d), _quarter_sort_key(d)), reverse=True)
        for i, doc in enumerate(docs):
            doc["similarity"] += max(0, 0.10 - i * 0.005)
    
    # Section boosting (RAG-Challenge-2 style)
    # Boost documents from sections that are likely to contain the answer
    if boost_sections:
        for doc in docs:
            doc_section = doc.get("section_header", "").lower()
            for boost_section in boost_sections:
                if boost_section.lower() in doc_section:
                    doc["similarity"] += 0.12  # Significant boost for matching sections
                    break
    
    # Auto-detect sections to boost based on query content
    query_lower = query.lower()
    auto_boost_sections = []
    
    if any(term in query_lower for term in CAPEX_TRIGGERS):
        auto_boost_sections.extend([
            "Capital Expenditures", "Cash Flow Statement", 
            "Liquidity and Capital Resources", "Item 7. MD&A"
        ])
    if "revenue" in query_lower or "sales" in query_lower:
        auto_boost_sections.extend(["Income Statement", "Results of Operations"])
    if "asset" in query_lower or "liabilit" in query_lower:
        auto_boost_sections.extend(["Balance Sheet"])
    
    if auto_boost_sections:
        for doc in docs:
            doc_section = doc.get("section_header", "").lower()
            for boost_section in auto_boost_sections:
                if boost_section.lower() in doc_section:
                    doc["similarity"] += 0.08  # Moderate auto-boost
                    break

    docs.sort(key=lambda d: d["similarity"], reverse=True)

    # === CAPEX TABLE INJECTION ===
    # Cash flow statement tables have poor semantic embeddings (lots of empty cells
    # in multi-column SEC HTML tables). For CapEx queries, directly fetch cash flow
    # table chunks by metadata and inject the best ones into the result set.
    query_lower = query.lower()
    if any(trigger in query_lower for trigger in CAPEX_TRIGGERS) and use_company_collection:
        # Track chunk IDs already in docs to avoid duplicates
        existing_content_hashes = {hash(d.get("content", "")) for d in docs}
        try:
            # Fetch ALL cash flow statement table chunks (no vector search - by metadata)
            cf_all = collection.get(
                where={"table_type": "cash_flow_statement"},
                include=["documents", "metadatas"],
            )
            if cf_all and cf_all.get("documents"):
                # Score and rank cash flow table chunks
                filing_priority = {"10-K": 3, "10-Q": 2, "8-K": 1, "Press Release": 1}
                injection_candidates = []

                for doc_text, metadata in zip(cf_all["documents"], cf_all["metadatas"]):
                    if metadata is None:
                        metadata = {}
                    # Skip if not containing actual CapEx data
                    if not any(kw in doc_text.lower() for kw in [
                        "purchases of property", "capital expenditure", "investing activities",
                        "acquisition of property", "additions to property",
                    ]):
                        continue
                    # Skip duplicates already in docs
                    if hash(doc_text) in existing_content_hashes:
                        continue

                    # Compute injection score based on year match + filing type priority
                    score = 0.80  # base score for targeted retrieval

                    ftype = metadata.get("filing_type", "")
                    score += filing_priority.get(ftype, 0) * 0.05  # 10-K gets +0.15

                    if detected_year:
                        fy = str(metadata.get("fiscal_year", ""))
                        variants = _fiscal_year_variants(detected_year)
                        # Content year match is more reliable than metadata label
                        # (some companies have off-calendar fiscal years where labels don't match)
                        content_has_year = detected_year in doc_text
                        meta_year_match = any(v.lower() in fy.lower() for v in variants)
                        if content_has_year:
                            score += 0.20  # Strong boost — year appears in table column header
                        elif meta_year_match:
                            score += 0.10  # Weaker boost — only metadata matches

                    injection_candidates.append({
                        "content": doc_text,
                        "company": metadata.get("company", company_filter or "Unknown"),
                        "source": metadata.get("source_file", metadata.get("source", "Unknown")),
                        "filing_type": ftype,
                        "fiscal_year": metadata.get("fiscal_year", "Unknown"),
                        "quarter": metadata.get("quarter", ""),
                        "similarity": round(score, 4),
                        "vector_score": 0.0,
                        "chunk_type": metadata.get("chunk_type", "table"),
                        "parent_id": metadata.get("parent_id", ""),
                        "section_header": metadata.get("section_header", "Cash Flow Statement"),
                        "page_num": metadata.get("page_num", 0),
                        "parent_content": doc_text,
                    })

                # Sort candidates: 10-K annual first, then by year match, then by score
                injection_candidates.sort(key=lambda d: d["similarity"], reverse=True)

                # Inject top candidates (limit to 5 to leave room for regular results)
                for candidate in injection_candidates[:5]:
                    docs.append(candidate)
                    existing_content_hashes.add(hash(candidate["content"]))

        except Exception:
            pass

        # Re-sort after injection
        docs.sort(key=lambda d: d["similarity"], reverse=True)

    # === CAPEX TEXT INJECTION (fallback for PDF companies) ===
    # Triggered when table injection found < 2 high-confidence CapEx results.
    # PDFs like Celestica store CapEx as plain text paragraphs, not tagged tables.
    # Uses ChromaDB where_document filter to find chunks explicitly mentioning
    # "capital expenditure" — bypasses embedding quality issues for short sentences.
    if any(trigger in query_lower for trigger in CAPEX_TRIGGERS) and use_company_collection:
        # Only skip text injection if we already have high-confidence results
        # from the CORRECT year that also contain a dollar value near the CapEx mention.
        # Intro/cover pages that just mention "capital expenditures" in passing don't count.
        def _capex_with_value(text: str) -> bool:
            """True if text has a CapEx keyword within 300 chars of a dollar/numeric value."""
            for kw in ["capital expenditure", "purchases of property"]:
                idx = text.lower().find(kw)
                while idx >= 0:
                    window = text[max(0, idx - 200):idx + 300]
                    if re.search(r'\$\s*[\d,]+|\d[\d,.]+\s*million', window, re.IGNORECASE):
                        return True
                    idx = text.lower().find(kw, idx + 1)
            return False

        capex_in_docs = sum(
            1 for d in docs
            if d.get("similarity", 0) >= 0.90
            and _capex_with_value(d.get("parent_content") or d.get("content", ""))
            and (
                not detected_year
                or detected_year in (d.get("parent_content") or d.get("content", ""))
            )
        )
        if capex_in_docs < 2:
            existing_content_hashes = {hash(d.get("content", "")) for d in docs}
            try:
                text_results = collection.get(
                    where_document={
                        "$or": [
                            {"$contains": "capital expenditure"},
                            {"$contains": "Capital expenditure"},
                            {"$contains": "Capital Expenditure"},
                            {"$contains": "CAPITAL EXPENDITURE"},
                        ]
                    },
                    include=["documents", "metadatas"],
                )
                if text_results and text_results.get("documents"):
                    filing_priority = {"10-K": 3, "10-Q": 2, "8-K": 1, "Press Release": 1}
                    text_candidates = []
                    # Build a lookup so we can boost existing docs instead of skipping
                    existing_by_hash = {
                        hash(d.get("content", "")): d for d in docs
                    }

                    for doc_text, metadata in zip(
                        text_results["documents"], text_results["metadatas"]
                    ):
                        if metadata is None:
                            metadata = {}
                        # Skip if already handled as a cash_flow_statement table chunk
                        if metadata.get("table_type") == "cash_flow_statement":
                            continue
                        # Must contain a dollar/numeric value to be useful
                        if not re.search(
                            r'\$\s*[\d,]+|\d[\d,.]+\s*million', doc_text, re.IGNORECASE
                        ):
                            continue

                        score = 0.75
                        ftype = metadata.get("filing_type", "")
                        score += filing_priority.get(ftype, 0) * 0.05

                        if detected_year:
                            content_has_year = detected_year in doc_text
                            fy = str(metadata.get("fiscal_year", ""))
                            variants = _fiscal_year_variants(detected_year)
                            meta_year_match = any(
                                v.lower() in fy.lower() for v in variants
                            )
                            # Cumulative: docs FROM the target year (meta_year_match)
                            # AND mentioning it in content score highest.
                            if content_has_year:
                                score += 0.15
                            if meta_year_match:
                                score += 0.10

                        # For long parent chunks, extract a 2500-char window
                        # centered on the most relevant CapEx + year mention so
                        # _build_context (which truncates at 3000 from the start)
                        # doesn't cut off the actual numeric value.
                        excerpt = doc_text
                        if len(doc_text) > 2500 and detected_year:
                            best_pos = -1
                            for kw in ["capital expenditure", "purchases of property"]:
                                idx = doc_text.lower().find(kw)
                                while idx >= 0:
                                    window = doc_text[max(0, idx-150):idx+300]
                                    if detected_year in window and re.search(
                                        r'\$\s*[\d,]+|\d[\d,.]+\s*million|\(\d', window
                                    ):
                                        best_pos = idx
                                        break
                                    idx = doc_text.lower().find(kw, idx + 1)
                                if best_pos >= 0:
                                    break
                            if best_pos >= 0:
                                start = max(0, best_pos - 500)
                                excerpt = doc_text[start:start + 2500]

                        doc_hash = hash(doc_text)
                        if doc_hash in existing_by_hash:
                            # Chunk already in docs from vector search — boost its score
                            # if the injection score is higher (don't add a duplicate).
                            existing = existing_by_hash[doc_hash]
                            if score > existing.get("similarity", 0):
                                existing["similarity"] = round(score, 4)
                                # Also update parent_content to the focused excerpt
                                if len(doc_text) > 2500:
                                    existing["parent_content"] = excerpt
                        else:
                            text_candidates.append({
                                "content": excerpt,
                                "company": metadata.get("company", company_filter or "Unknown"),
                                "source": metadata.get(
                                    "source_file", metadata.get("source", "Unknown")
                                ),
                                "filing_type": ftype,
                                "fiscal_year": metadata.get("fiscal_year", "Unknown"),
                                "quarter": metadata.get("quarter", ""),
                                "similarity": round(score, 4),
                                "vector_score": 0.0,
                                "chunk_type": metadata.get("chunk_type", "text"),
                                "parent_id": metadata.get("parent_id", ""),
                                "section_header": metadata.get(
                                    "section_header", "Capital Expenditures"
                                ),
                                "page_num": metadata.get("page_num", 0),
                                "parent_content": excerpt,
                            })

                    # Secondary sort: boost chunks that have detected_year AND a
                    # dollar amount within 200 chars of a CapEx keyword — these are
                    # the most direct answers (e.g. "CapEx for 2024 were $170.9M").
                    def _has_capex_year_dollar(d: dict) -> bool:
                        if not detected_year:
                            return False
                        txt = d.get("parent_content") or d.get("content", "")
                        for kw in ["capital expenditure", "purchases of property"]:
                            idx = txt.lower().find(kw)
                            while idx >= 0:
                                window = txt[max(0, idx - 50):idx + 250]
                                if detected_year in window and re.search(
                                    r'\$\s*[\d,]+(?:\.\d+)?(?:\s*million)?', window, re.IGNORECASE
                                ):
                                    return True
                                idx = txt.lower().find(kw, idx + 1)
                        return False

                    text_candidates.sort(
                        key=lambda d: (d["similarity"], _has_capex_year_dollar(d)),
                        reverse=True,
                    )
                    for candidate in text_candidates[:5]:
                        docs.append(candidate)
                    if text_candidates:
                        docs.sort(key=lambda d: d["similarity"], reverse=True)
                    elif any(existing_by_hash):
                        # Scores may have been updated in-place; re-sort
                        docs.sort(key=lambda d: d["similarity"], reverse=True)
            except Exception:
                pass

    # LLM Reranking (if enabled and we have enough candidates)
    if use_reranking and len(docs) > n_results:
        docs = rerank_with_llm(query, docs, top_k=n_results)
    else:
        docs = docs[:n_results]

    return docs


def search_by_company(
    query: str,
    company: str,
    n_results: int = 20,
    use_reranking: bool = False,
) -> list[dict]:
    """Convenience wrapper to search within a single company."""
    return search_documents(
        query, 
        company_filter=company, 
        n_results=n_results,
        use_reranking=use_reranking,
    )


def search_cross_company(
    query: str,
    n_results: int = 50,
    use_reranking: bool = False,
) -> list[dict]:
    """Search across all companies without a company filter."""
    return search_documents(query, n_results=n_results, use_reranking=use_reranking)


def search_multi_company_by_periods(
    query: str,
    companies: list[str],
    n_quarters: int,
    n_results: int = 20,
) -> list[dict]:
    """
    多公司查询时，按各自财年分别计算 target periods，再合并结果。
    保证每家公司的时间窗口都对齐到正确的财年季度。
    """
    all_docs = []
    all_missing = []
    company_period_info = []

    for company in companies:
        target_periods = _get_recent_fiscal_periods(n_quarters, company)
        company_period_info.append(
            f"  - {company}: " + ", ".join(f"{fy} {q}" for fy, q in target_periods)
        )

        # 用该公司自己的 target_periods 去检索
        company_docs = search_documents(
            query=query,
            company_filter=company,
            n_results=n_results,
        )

        # 检测缺失
        found_periods = set()
        for doc in company_docs:
            period = (str(doc.get("fiscal_year", "")), doc.get("quarter", ""))
            if period in target_periods:
                found_periods.add(period)

        missing = [p for p in target_periods if p not in found_periods]
        for p in missing:
            all_missing.append((company, p[0], p[1]))

        # boost / 降权
        for doc in company_docs:
            period = (str(doc.get("fiscal_year", "")), doc.get("quarter", ""))
            if period in target_periods:
                doc["similarity"] += 0.25
            else:
                doc["similarity"] -= 0.15

        all_docs.extend(company_docs)

    # 注入多公司财年对齐说明
    alignment_note = (
        "[MULTI-COMPANY TIME ALIGNMENT] Each company uses its own fiscal calendar. "
        f"The last {n_quarters} completed quarters for each company are:\n"
        + "\n".join(company_period_info)
    )
    note_doc = {
        "content": alignment_note,
        "company": "SYSTEM",
        "source": "system",
        "filing_type": "SYSTEM",
        "fiscal_year": "",
        "quarter": "",
        "similarity": 99.0,
        "section_header": "",
        "page_num": 0,
    }
    all_docs.insert(0, note_doc)

    # 如果有缺失数据，再注入警告
    if all_missing:
        missing_str = ", ".join(f"{company} FY{fy} {q}" for company, fy, q in all_missing)
        warning_doc = {
            "content": (
                f"[DATA GAP WARNING] The following company-quarter combinations "
                f"have NO data in the database: {missing_str}. "
                f"You MUST explicitly tell the user which ones are missing."
            ),
            "company": "SYSTEM",
            "source": "system",
            "filing_type": "SYSTEM",
            "fiscal_year": "",
            "quarter": "",
            "similarity": 98.0,
            "section_header": "",
            "page_num": 0,
        }
        all_docs.insert(1, warning_doc)

    all_docs.sort(key=lambda d: float(d.get("similarity", 0)), reverse=True)
    return all_docs[:n_results * len(companies)]


def search_with_parent_retrieval(
    query: str,
    company_filter: Optional[str] = None,
    n_results: int = 10,
    use_reranking: bool = False,
) -> dict:
    """
    Parent Document Retrieval (RAG-Challenge-2 style).
    
    Process:
    1. Search for relevant CHILD chunks (precise matching)
    2. Get unique PARENT documents (pages/sections) for matched children
    3. Return full parent content as context (tables, footnotes included)
    
    This is the recommended search method for financial QA.
    
    Returns:
        dict with:
        - parents: List of unique parent documents (pages/sections) 
        - children: List of matched child chunks
        - context: Combined parent content for LLM
    """
    # Search for documents
    docs = search_documents(
        query=query,
        company_filter=company_filter,
        n_results=n_results * 3,  # Get more to ensure we find good parents
        use_reranking=use_reranking,
    )
    
    if not docs:
        return {"parents": [], "children": [], "context": ""}
    
    # Collect unique parents
    seen_parent_ids = set()
    unique_parents = []
    children = []
    
    for doc in docs:
        parent_id = doc.get("parent_id", "")
        
        if doc["chunk_type"] == "child":
            children.append(doc)
            
            # Get parent content (fetched in search_documents)
            parent_content = doc.get("parent_content", "")
            
            if parent_id and parent_id not in seen_parent_ids and parent_content:
                seen_parent_ids.add(parent_id)
                unique_parents.append({
                    "parent_id": parent_id,
                    "content": parent_content,
                    "page_num": doc.get("page_num", 0),
                    "section_header": doc.get("section_header", ""),
                    "company": doc.get("company", ""),
                    "source": doc.get("source", ""),
                    "fiscal_year": doc.get("fiscal_year", ""),
                    "quarter": doc.get("quarter", ""),
                    "filing_type": doc.get("filing_type", ""),
                })
                
                # Limit to n_results parents
                if len(unique_parents) >= n_results:
                    break
        
        elif doc["chunk_type"] == "parent":
            # If we found a parent directly, include it
            if parent_id not in seen_parent_ids:
                seen_parent_ids.add(parent_id)
                unique_parents.append({
                    "parent_id": parent_id,
                    "content": doc["content"],
                    "page_num": doc.get("page_num", 0),
                    "section_header": doc.get("section_header", ""),
                    "company": doc.get("company", ""),
                    "source": doc.get("source", ""),
                    "fiscal_year": doc.get("fiscal_year", ""),
                    "quarter": doc.get("quarter", ""),
                    "filing_type": doc.get("filing_type", ""),
                })
                
                if len(unique_parents) >= n_results:
                    break
        
        elif doc["chunk_type"] == "table":
            # Tables are their own parents
            if parent_id not in seen_parent_ids:
                seen_parent_ids.add(parent_id)
                unique_parents.append({
                    "parent_id": parent_id,
                    "content": doc["content"],
                    "page_num": doc.get("page_num", 0),
                    "section_header": doc.get("section_header", ""),
                    "company": doc.get("company", ""),
                    "source": doc.get("source", ""),
                    "fiscal_year": doc.get("fiscal_year", ""),
                    "quarter": doc.get("quarter", ""),
                    "filing_type": doc.get("filing_type", ""),
                    "is_table": True,
                })
    
    # Build combined context from parents
    context_parts = []
    for i, parent in enumerate(unique_parents, 1):
        header = f"[Source {i}: {parent['company']} | {parent['source']} | Page {parent['page_num']} | {parent['section_header']}]"
        context_parts.append(f"{header}\n{parent['content']}")
    
    combined_context = "\n\n---\n\n".join(context_parts)
    
    return {
        "parents": unique_parents,
        "children": children[:n_results],
        "context": combined_context,
        "num_parents": len(unique_parents),
        "num_children": len(children),
    }


def smart_search(
    query: str,
    n_results: int = 20,
    use_reranking: bool = False,
) -> dict:
    """
    Intelligent search with automatic query routing (RAG-Challenge-2 style).
    
    Automatically:
    - Detects companies mentioned in query
    - Routes to single-company or cross-company search
    - Boosts relevant sections based on query content
    - Handles multi-company comparisons by splitting queries
    
    Returns:
        dict with:
        - results: list of documents
        - routing: information about how query was routed
        - companies_found: companies detected in query
    """
    routing = route_query(query)
    
    if routing["strategy"] == "split_by_company" and routing["sub_queries"]:
        # Multi-company comparison: search each company separately
        all_results = []
        per_company_results = {}
        
        for sub in routing["sub_queries"]:
            company_results = search_documents(
                query=sub["query"],
                company_filter=sub["company"],
                n_results=n_results // len(routing["sub_queries"]),
                use_reranking=use_reranking,
                boost_sections=routing["boost_sections"],
            )
            per_company_results[sub["company"]] = company_results
            all_results.extend(company_results)
        
        return {
            "results": all_results,
            "routing": routing,
            "companies_found": [s["company"] for s in routing["sub_queries"]],
            "per_company_results": per_company_results,
        }
    
    else:
        # Direct search (single company or cross-company)
        filters = routing["filters"] or {}
        results = search_documents(
            query=query,
            company_filter=filters.get("company"),
            n_results=n_results,
            use_reranking=use_reranking,
            boost_sections=routing["boost_sections"],
        )
        
        return {
            "results": results,
            "routing": routing,
            "companies_found": extract_companies_from_query(query),
        }


def get_company_documents(company: str, limit: int = 100) -> list[dict]:
    """
    Retrieve raw document chunks for a company (no query embedding needed).

    Returns dicts with 'content' and 'metadata' keys, matching the format
    expected by analytics modules.
    """
    collection = get_collection()
    if collection.count() == 0:
        return []

    try:
        results = collection.get(
            where={"company": company},
            include=["documents", "metadatas"],
            limit=limit,
        )
    except Exception:
        return []

    docs = []
    for doc_text, metadata in zip(
        results.get("documents", []),
        results.get("metadatas", []),
    ):
        docs.append({
            "content": doc_text,
            "metadata": metadata,
        })

    return docs
