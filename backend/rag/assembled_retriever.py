"""
Assembled Retriever - Pluggable, Composable Retrieval System
Inspired by RAG-Challenge-2 winning solution

Features:
1. PLUGGABLE STRATEGIES - Mix and match retrieval methods
2. BM25 + VECTOR - Hybrid keyword + semantic search
3. CHILD → PARENT EXPANSION - Precise retrieval + rich context
4. QUERY ROUTING - Different strategies for different question types

Architecture:
┌─────────────────────────────────────────────────────────────┐
│                    AssembledRetriever                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ QueryRouter - detects question type                 │   │
│  │   numeric / comparison / descriptive / table_lookup │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│           ┌───────────────┼───────────────┐                │
│           ▼               ▼               ▼                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ VectorSearch│  │ BM25Search  │  │ TableSearch │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│           │               │               │                │
│           └───────────────┼───────────────┘                │
│                           ▼                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ResultMerger - RRF / weighted combination           │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ParentExpander - child → full page/section          │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ LLMReranker - final relevance scoring               │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
"""
import re
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from backend.core.database import (
    get_collection,
    get_company_collection,
    has_company_collections,
    embed_text,
    embed_texts,
)
from backend.core.config import OPENAI_API_KEY, RERANK_MODEL, TRACKED_COMPANY_NAMES


# ---------------------------------------------------------------------------
# DATA STRUCTURES
# ---------------------------------------------------------------------------

@dataclass
class RetrievalResult:
    """Standardized result from any retrieval strategy."""
    content: str
    score: float
    source: str
    company: str = ""
    filing_type: str = ""
    fiscal_year: str = ""
    quarter: str = ""
    page_num: int = 0
    section_header: str = ""
    chunk_type: str = ""
    parent_id: str = ""
    parent_content: str = ""  # Full parent for context
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "score": self.score,
            "source": self.source,
            "company": self.company,
            "filing_type": self.filing_type,
            "fiscal_year": self.fiscal_year,
            "quarter": self.quarter,
            "page_num": self.page_num,
            "section_header": self.section_header,
            "chunk_type": self.chunk_type,
            "parent_id": self.parent_id,
            "parent_content": self.parent_content,
            "metadata": self.metadata,
        }


@dataclass
class QueryAnalysis:
    """Analysis of a query for routing."""
    query_type: str  # "numeric", "comparison", "descriptive", "table_lookup", "summary"
    companies: list  # Companies mentioned
    is_comparison: bool
    suggested_sections: list  # Sections likely to have the answer
    time_reference: str  # "latest", "specific_year", "range", "none"
    detected_year: str = ""
    
    # Routing-determined parameters (RAG-Challenge-2 style)
    recommended_top_k: int = 15
    recommended_rerank_sample: int = 50
    use_reranking: bool = True
    parent_granularity: str = "page"  # "page", "section", "chunk"
    use_table_priority: bool = False


@dataclass 
class RetrievalConfig:
    """Configuration for retrieval based on query type."""
    top_k: int
    rerank_sample_size: int
    use_reranking: bool
    parent_granularity: str
    use_table_priority: bool
    strategy: str
    
    @classmethod
    def for_numeric(cls) -> "RetrievalConfig":
        """Config for numeric/fact questions - strict, table-focused."""
        return cls(
            top_k=10,
            rerank_sample_size=50,
            use_reranking=False,
            parent_granularity="page",  # Tables often span pages
            use_table_priority=True,
            strategy="hybrid",
        )

    @classmethod
    def for_comparison(cls) -> "RetrievalConfig":
        """Config for comparison questions - per-company search."""
        return cls(
            top_k=8,  # Per company
            rerank_sample_size=30,
            use_reranking=False,
            parent_granularity="page",
            use_table_priority=True,
            strategy="hybrid",
        )

    @classmethod
    def for_descriptive(cls) -> "RetrievalConfig":
        """Config for descriptive/discussion questions - broader context."""
        return cls(
            top_k=15,
            rerank_sample_size=40,
            use_reranking=False,
            parent_granularity="section",  # Larger chunks OK
            use_table_priority=False,
            strategy="vector",
        )
    
    @classmethod
    def for_summary(cls) -> "RetrievalConfig":
        """Config for summary questions - widest context."""
        return cls(
            top_k=20,
            rerank_sample_size=60,
            use_reranking=False,  # Summaries need breadth, not precision
            parent_granularity="section",
            use_table_priority=False,
            strategy="vector",
        )
    
    @classmethod
    def for_table_lookup(cls) -> "RetrievalConfig":
        """Config for explicit table queries."""
        return cls(
            top_k=10,
            rerank_sample_size=30,
            use_reranking=False,
            parent_granularity="page",
            use_table_priority=True,
            strategy="table",
        )


# ---------------------------------------------------------------------------
# BASE RETRIEVER INTERFACE
# ---------------------------------------------------------------------------

class BaseRetriever(ABC):
    """Abstract base class for all retrievers."""
    
    @abstractmethod
    def retrieve(
        self,
        query: str,
        company: Optional[str] = None,
        top_k: int = 10,
        **kwargs,
    ) -> list[RetrievalResult]:
        """Retrieve relevant documents."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of this retriever."""
        pass


# ---------------------------------------------------------------------------
# VECTOR RETRIEVER
# ---------------------------------------------------------------------------

class VectorRetriever(BaseRetriever):
    """Vector similarity search using ChromaDB embeddings."""
    
    @property
    def name(self) -> str:
        return "vector"
    
    def retrieve(
        self,
        query: str,
        company: Optional[str] = None,
        top_k: int = 10,
        chunk_type_filter: Optional[str] = None,
        section_filter: Optional[str] = None,
        **kwargs,
    ) -> list[RetrievalResult]:
        """
        Retrieve documents using vector similarity.
        
        Args:
            query: Search query
            company: Filter by company
            top_k: Number of results
            chunk_type_filter: Filter by chunk type ("child", "parent", "table")
            section_filter: Filter by section header
        """
        query_embedding = embed_text(query)
        
        # Select collection
        if has_company_collections() and company:
            collection = get_company_collection(company)
        else:
            collection = get_collection()
        
        if collection.count() == 0:
            return []
        
        # Build filters
        filters = []
        if company and not has_company_collections():
            filters.append({"company": company})
        if chunk_type_filter:
            filters.append({"chunk_type": chunk_type_filter})
        if section_filter:
            filters.append({"section_header": section_filter})
        
        where_filter = None
        if len(filters) > 1:
            where_filter = {"$and": filters}
        elif len(filters) == 1:
            where_filter = filters[0]
        
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count()),
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )
        
        if not results or not results["documents"] or not results["documents"][0]:
            return []
        
        retrieval_results = []
        for doc_text, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            score = 1 - distance  # Convert distance to similarity
            
            retrieval_results.append(RetrievalResult(
                content=doc_text,
                score=round(score, 4),
                source=metadata.get("source_file", "Unknown"),
                company=metadata.get("company", ""),
                filing_type=metadata.get("filing_type", ""),
                fiscal_year=metadata.get("fiscal_year", ""),
                quarter=metadata.get("quarter", ""),
                page_num=metadata.get("page_num", 0),
                section_header=metadata.get("section_header", ""),
                chunk_type=metadata.get("chunk_type", ""),
                parent_id=metadata.get("parent_id", ""),
                metadata=metadata,
            ))
        
        return retrieval_results


# ---------------------------------------------------------------------------
# BM25 RETRIEVER
# ---------------------------------------------------------------------------

class BM25Retriever(BaseRetriever):
    """
    BM25 keyword-based retrieval.
    Falls back to simple keyword matching if rank_bm25 not installed.
    """
    
    def __init__(self):
        self._bm25_available = False
        self._indices = {}  # company -> (bm25, chunks)
        
        try:
            from rank_bm25 import BM25Okapi
            self._bm25_available = True
            self._BM25Okapi = BM25Okapi
        except ImportError:
            pass
    
    @property
    def name(self) -> str:
        return "bm25"
    
    def _build_index(self, company: Optional[str] = None):
        """Build BM25 index from ChromaDB documents."""
        if not self._bm25_available:
            return None, []
        
        # Get documents from ChromaDB
        if has_company_collections() and company:
            collection = get_company_collection(company)
        else:
            collection = get_collection()
        
        if collection.count() == 0:
            return None, []
        
        # Get all documents
        results = collection.get(
            include=["documents", "metadatas"],
            limit=collection.count(),
        )
        
        if not results or not results["documents"]:
            return None, []
        
        # Tokenize documents
        tokenized_docs = []
        chunks = []
        
        for doc_text, metadata in zip(results["documents"], results["metadatas"]):
            tokens = doc_text.lower().split()
            tokenized_docs.append(tokens)
            chunks.append({
                "content": doc_text,
                "metadata": metadata,
            })
        
        # Build BM25 index
        bm25 = self._BM25Okapi(tokenized_docs)
        
        return bm25, chunks
    
    def retrieve(
        self,
        query: str,
        company: Optional[str] = None,
        top_k: int = 10,
        **kwargs,
    ) -> list[RetrievalResult]:
        """Retrieve documents using BM25 keyword matching."""
        if not self._bm25_available:
            return self._fallback_keyword_search(query, company, top_k)
        
        # Build or get cached index
        cache_key = company or "__all__"
        if cache_key not in self._indices:
            bm25, chunks = self._build_index(company)
            if bm25 is None:
                return []
            self._indices[cache_key] = (bm25, chunks)
        
        bm25, chunks = self._indices[cache_key]
        
        # Query
        tokenized_query = query.lower().split()
        scores = bm25.get_scores(tokenized_query)
        
        # Get top-k
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]
        
        retrieval_results = []
        for idx in top_indices:
            if scores[idx] > 0:
                chunk = chunks[idx]
                metadata = chunk["metadata"]
                
                retrieval_results.append(RetrievalResult(
                    content=chunk["content"],
                    score=round(float(scores[idx]), 4),
                    source=metadata.get("source_file", "Unknown"),
                    company=metadata.get("company", ""),
                    filing_type=metadata.get("filing_type", ""),
                    fiscal_year=metadata.get("fiscal_year", ""),
                    quarter=metadata.get("quarter", ""),
                    page_num=metadata.get("page_num", 0),
                    section_header=metadata.get("section_header", ""),
                    chunk_type=metadata.get("chunk_type", ""),
                    parent_id=metadata.get("parent_id", ""),
                    metadata=metadata,
                ))
        
        return retrieval_results
    
    def _fallback_keyword_search(
        self,
        query: str,
        company: Optional[str] = None,
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """Simple keyword matching fallback."""
        if has_company_collections() and company:
            collection = get_company_collection(company)
        else:
            collection = get_collection()
        
        if collection.count() == 0:
            return []
        
        # Get all documents
        results = collection.get(
            include=["documents", "metadatas"],
            limit=collection.count(),
        )
        
        if not results or not results["documents"]:
            return []
        
        # Simple keyword scoring
        query_terms = set(query.lower().split())
        scored = []
        
        for doc_text, metadata in zip(results["documents"], results["metadatas"]):
            doc_terms = set(doc_text.lower().split())
            overlap = len(query_terms & doc_terms)
            score = overlap / max(len(query_terms), 1)
            
            if score > 0:
                scored.append((doc_text, metadata, score))
        
        # Sort by score
        scored.sort(key=lambda x: x[2], reverse=True)
        
        retrieval_results = []
        for doc_text, metadata, score in scored[:top_k]:
            retrieval_results.append(RetrievalResult(
                content=doc_text,
                score=round(score, 4),
                source=metadata.get("source_file", "Unknown"),
                company=metadata.get("company", ""),
                filing_type=metadata.get("filing_type", ""),
                fiscal_year=metadata.get("fiscal_year", ""),
                quarter=metadata.get("quarter", ""),
                page_num=metadata.get("page_num", 0),
                section_header=metadata.get("section_header", ""),
                chunk_type=metadata.get("chunk_type", ""),
                parent_id=metadata.get("parent_id", ""),
                metadata=metadata,
            ))
        
        return retrieval_results


# ---------------------------------------------------------------------------
# TABLE RETRIEVER
# ---------------------------------------------------------------------------

class TableRetriever(BaseRetriever):
    """Specialized retriever for table chunks."""
    
    def __init__(self):
        self._vector_retriever = VectorRetriever()
    
    @property
    def name(self) -> str:
        return "table"
    
    def retrieve(
        self,
        query: str,
        company: Optional[str] = None,
        top_k: int = 10,
        table_type_filter: Optional[str] = None,
        **kwargs,
    ) -> list[RetrievalResult]:
        """Retrieve only table chunks."""
        results = self._vector_retriever.retrieve(
            query=query,
            company=company,
            top_k=top_k * 2,  # Get more to filter
            chunk_type_filter="table",
        )
        
        # Filter by table type if specified
        if table_type_filter:
            results = [
                r for r in results
                if r.metadata.get("table_type", "") == table_type_filter
            ]
        
        return results[:top_k]


# ---------------------------------------------------------------------------
# QUERY ROUTER
# ---------------------------------------------------------------------------

KNOWN_COMPANIES = list(TRACKED_COMPANY_NAMES)

CAPEX_TRIGGERS = {
    "capex", "cap ex", "capital expenditure", "capital expenditures",
    "capital spending", "property and equipment", "ppe",
}


class QueryRouter:
    """
    Route queries to appropriate retrieval strategies.
    
    RAG-Challenge-2 insight: Different question types need different:
    - top_k values
    - reranking settings
    - parent granularity (page vs section)
    - retrieval strategies
    
    Query Types:
    - numeric: Single fact/number → strict table focus, page-level parent
    - comparison: Multi-company compare → per-company search, aligned output
    - descriptive: Explain/discuss → broader context, section-level parent
    - summary: Overview/trend → widest context, less strict
    - table_lookup: Explicit table request → table chunks priority
    """
    
    SUMMARY_TRIGGERS = [
        "summarize", "summary", "overview", "describe", "explain",
        "tell me about", "what does", "how does", "discuss",
    ]
    
    def analyze(self, query: str) -> QueryAnalysis:
        """Analyze query to determine optimal retrieval strategy and config."""
        query_lower = query.lower()
        
        # Detect companies
        companies = [c for c in KNOWN_COMPANIES if c.lower() in query_lower]
        
        # Detect comparison
        comparison_keywords = [
            "compare", "versus", "vs", "differ", "between",
            "which company", "who has higher", "who has more", "who has lower",
            "rank", "ranking", "across companies",
        ]
        is_comparison = any(kw in query_lower for kw in comparison_keywords)
        
        # Detect query type with priority order
        if is_comparison and len(companies) >= 2:
            query_type = "comparison"
        elif any(kw in query_lower for kw in ["table", "statement", "balance sheet", "income statement", "cash flow"]):
            query_type = "table_lookup"
        elif any(kw in query_lower for kw in self.SUMMARY_TRIGGERS):
            query_type = "summary"
        elif any(kw in query_lower for kw in ["how much", "what is the", "what was", "value", "amount", "total", "number"]):
            query_type = "numeric"
        else:
            query_type = "descriptive"
        
        # Suggest sections
        suggested_sections = []
        if any(term in query_lower for term in CAPEX_TRIGGERS):
            suggested_sections.extend(["Capital Expenditures", "Cash Flow Statement"])
        if "revenue" in query_lower or "sales" in query_lower:
            suggested_sections.extend(["Income Statement", "Results of Operations"])
        if "asset" in query_lower or "liabilit" in query_lower:
            suggested_sections.append("Balance Sheet")
        if "risk" in query_lower:
            suggested_sections.append("Item 1A. Risk Factors")
        if "guidance" in query_lower or "outlook" in query_lower:
            suggested_sections.append("Management Discussion")
        
        # Detect time reference
        time_reference = "none"
        detected_year = ""
        if "latest" in query_lower or "recent" in query_lower or "current" in query_lower:
            time_reference = "latest"
        elif match := re.search(r'\b(20[1-3]\d)\b', query):
            time_reference = "specific_year"
            detected_year = match.group(1)
        elif re.search(r'\bFY\s*(\d{2,4})\b', query, re.IGNORECASE):
            time_reference = "specific_year"
            match = re.search(r'\bFY\s*(\d{2,4})\b', query, re.IGNORECASE)
            year = match.group(1)
            detected_year = f"20{year}" if len(year) == 2 else year
        
        # Get recommended config based on query type
        config = self.get_config(query_type)
        
        return QueryAnalysis(
            query_type=query_type,
            companies=companies,
            is_comparison=is_comparison,
            suggested_sections=suggested_sections,
            time_reference=time_reference,
            detected_year=detected_year,
            recommended_top_k=config.top_k,
            recommended_rerank_sample=config.rerank_sample_size,
            use_reranking=config.use_reranking,
            parent_granularity=config.parent_granularity,
            use_table_priority=config.use_table_priority,
        )
    
    def get_config(self, query_type: str) -> RetrievalConfig:
        """Get retrieval configuration for a query type."""
        configs = {
            "numeric": RetrievalConfig.for_numeric(),
            "comparison": RetrievalConfig.for_comparison(),
            "descriptive": RetrievalConfig.for_descriptive(),
            "summary": RetrievalConfig.for_summary(),
            "table_lookup": RetrievalConfig.for_table_lookup(),
        }
        return configs.get(query_type, RetrievalConfig.for_descriptive())
    
    def get_route_type(self, query: str, analysis: QueryAnalysis) -> str:
        """
        Determine the routing type (B2 from spec):
        - R1: 五家公司横向对比
        - R2: 实时投资动态
        - R3: 口径核对 (CapEx 指引/金额细节)
        """
        query_lower = query.lower()
        
        # R2: Real-time/recency focused
        recency_triggers = [
            "recent", "latest", "last 90 days", "this quarter",
            "this year", "新", "最近", "过去", "刚刚",
        ]
        if any(t in query_lower for t in recency_triggers):
            return "R2_REALTIME"
        
        # R3: Precise number/guidance verification
        precision_triggers = [
            "exactly", "precise", "guidance", "how much exactly",
            "specific", "confirm", "verify", "what number",
        ]
        if any(t in query_lower for t in precision_triggers):
            return "R3_PRECISION"
        
        # R1: Cross-company comparison (default for comparison)
        if analysis.is_comparison or len(analysis.companies) >= 2:
            return "R1_COMPARISON"
        
        # Default based on query type
        if analysis.query_type == "numeric":
            return "R3_PRECISION"
        
        return "R1_COMPARISON" if len(analysis.companies) == 0 else "R3_PRECISION"


# ---------------------------------------------------------------------------
# TIME DECAY (B3 - For recency-focused queries)
# ---------------------------------------------------------------------------

def apply_time_decay(
    results: list[RetrievalResult],
    decay_rate: float = 0.1,
    reference_date: Optional[str] = None,
    doc_type_weights: dict = None,
) -> list[RetrievalResult]:
    """
    Apply time-based decay to result scores.
    
    Recency boost for R2 queries:
    - News/Web: Strong decay (recent = better)
    - SEC: Light decay (authoritative even if older)
    - Transcript: Moderate decay
    
    Formula: decayed_score = score * exp(-decay_rate * days_old / 365)
    """
    import math
    from datetime import datetime
    
    if reference_date:
        ref = datetime.strptime(reference_date, "%Y-%m-%d")
    else:
        ref = datetime.now()
    
    # Default doc type decay weights (higher = decays faster)
    if doc_type_weights is None:
        doc_type_weights = {
            "SEC_10K": 0.02,  # Very light decay (authoritative)
            "SEC_10Q": 0.03,
            "SEC_8K": 0.05,
            "TRANSCRIPT": 0.08,
            "NEWS": 0.15,  # Strong decay
            "WEB": 0.20,  # Strongest decay
        }
    
    for result in results:
        # Try to get document date
        doc_date_str = result.metadata.get("doc_date") or result.fiscal_year
        
        days_old = 180  # Default assumption
        if doc_date_str:
            try:
                if len(doc_date_str) == 4:  # Just year
                    doc_date = datetime(int(doc_date_str), 6, 30)  # Mid-year
                else:
                    doc_date = datetime.strptime(doc_date_str[:10], "%Y-%m-%d")
                days_old = (ref - doc_date).days
            except ValueError:
                pass
        
        # Get doc type specific decay
        doc_type = result.metadata.get("doc_type", "")
        effective_decay = doc_type_weights.get(doc_type, decay_rate)
        
        # Apply decay
        decay_factor = math.exp(-effective_decay * days_old / 365)
        result.score = round(result.score * decay_factor, 4)
        result.metadata["time_decay_applied"] = True
        result.metadata["days_old"] = days_old
    
    return results


# ---------------------------------------------------------------------------
# PER-COMPANY EVIDENCE ALIGNMENT (B3 - Critical for comparison)
# ---------------------------------------------------------------------------

def align_evidence_per_company(
    results: list[RetrievalResult],
    companies: list[str],
    min_per_company: int = 2,
    max_per_company: int = 4,
) -> dict[str, list[RetrievalResult]]:
    """
    Ensure each company has balanced evidence coverage.
    
    For comparison queries, we need:
    - At least min_per_company results per company
    - At most max_per_company to limit context
    - Best results selected per company
    """
    from collections import defaultdict
    
    # Group by company
    by_company = defaultdict(list)
    for result in results:
        company = result.company
        if company:
            by_company[company].append(result)
    
    # Ensure requested companies are represented
    aligned = {}
    for company in companies:
        # Find results for this company (case-insensitive match)
        company_results = []
        for key, vals in by_company.items():
            if key.lower() == company.lower():
                company_results = vals
                break
        
        # Sort by score
        company_results.sort(key=lambda r: r.score, reverse=True)
        
        # Take best results up to max
        aligned[company] = company_results[:max_per_company]
    
    return aligned


def ensure_evidence_coverage(
    aligned: dict[str, list[RetrievalResult]],
    companies: list[str],
    min_per_company: int = 2,
) -> dict:
    """
    Check evidence coverage and report gaps.
    """
    coverage = {
        "complete": True,
        "gaps": [],
        "per_company": {},
    }
    
    for company in companies:
        results = aligned.get(company, [])
        count = len(results)
        
        coverage["per_company"][company] = {
            "count": count,
            "has_tables": any(r.chunk_type == "table" for r in results),
            "fiscal_years": list(set(r.fiscal_year for r in results if r.fiscal_year)),
        }
        
        if count < min_per_company:
            coverage["complete"] = False
            coverage["gaps"].append({
                "company": company,
                "found": count,
                "needed": min_per_company,
            })
    
    return coverage


# ---------------------------------------------------------------------------
# RESULT MERGER (RRF - Reciprocal Rank Fusion)
# ---------------------------------------------------------------------------

def merge_results_rrf(
    result_lists: list[list[RetrievalResult]],
    k: int = 60,
) -> list[RetrievalResult]:
    """
    Merge multiple result lists using Reciprocal Rank Fusion.
    
    RRF score = sum(1 / (k + rank)) for each list where doc appears
    
    This is more robust than simple score combination because it doesn't
    depend on score normalization across different retrieval methods.
    """
    # Build document ID -> (best result, RRF score) mapping
    doc_scores = {}  # doc_id -> (result, rrf_score)
    
    for results in result_lists:
        for rank, result in enumerate(results, 1):
            # Use content hash as document ID
            doc_id = hash(result.content)
            rrf_contribution = 1.0 / (k + rank)
            
            if doc_id in doc_scores:
                # Add to existing score
                existing_result, existing_score = doc_scores[doc_id]
                doc_scores[doc_id] = (existing_result, existing_score + rrf_contribution)
            else:
                doc_scores[doc_id] = (result, rrf_contribution)
    
    # Sort by RRF score
    sorted_results = sorted(
        doc_scores.values(),
        key=lambda x: x[1],
        reverse=True,
    )
    
    # Update scores and return
    merged = []
    for result, rrf_score in sorted_results:
        result.score = round(rrf_score, 4)
        result.metadata["rrf_score"] = rrf_score
        merged.append(result)
    
    return merged


# ---------------------------------------------------------------------------
# PARENT EXPANDER
# ---------------------------------------------------------------------------

class ParentExpander:
    """
    Expand child chunks to their full parent content (page/section).
    
    This implements Parent Document Retrieval:
    1. Child chunks are used for precise matching
    2. Full parent content provides complete context
    """
    
    def expand(
        self,
        results: list[RetrievalResult],
        collection=None,
    ) -> list[RetrievalResult]:
        """
        Expand child results to include full parent content.
        Returns unique parents with full content.
        """
        if not results:
            return []
        
        # Collect parent IDs from child chunks
        parent_ids = set()
        for result in results:
            if result.chunk_type == "child" and result.parent_id:
                parent_ids.add(result.parent_id)
        
        if not parent_ids:
            return results
        
        # Fetch parent content
        if collection is None:
            if has_company_collections() and results[0].company:
                collection = get_company_collection(results[0].company)
            else:
                collection = get_collection()
        
        try:
            parent_results = collection.get(
                ids=list(parent_ids),
                include=["documents", "metadatas"],
            )
            
            # Build parent_id -> content mapping
            parent_map = {}
            if parent_results and parent_results["documents"]:
                for pid, pdoc, pmeta in zip(
                    parent_results["ids"],
                    parent_results["documents"],
                    parent_results["metadatas"],
                ):
                    parent_map[pid] = {
                        "content": pdoc,
                        "metadata": pmeta,
                    }
            
            # Attach parent content to results
            for result in results:
                if result.parent_id in parent_map:
                    result.parent_content = parent_map[result.parent_id]["content"]
        
        except Exception:
            pass
        
        return results


# ---------------------------------------------------------------------------
# LLM RERANKER
# ---------------------------------------------------------------------------

class LLMReranker:
    """
    Rerank results using LLM scoring.
    Supports batch processing for efficiency.
    
    Key insight from RAG-Challenge-2:
    Score based on "CAN THIS PASSAGE SUPPORT AN ANSWER?" not "Does it mention the topic?"
    """
    
    SYSTEM_PROMPT = """You are an expert at evaluating whether a passage can DIRECTLY SUPPORT answering a financial question.

CRITICAL: Score based on "Can this passage provide the specific data needed to answer?" NOT just "Does it mention the topic?"

Scoring criteria (0-10):
- 10: Contains the EXACT answer (specific number, date, or fact directly answering the question)
- 8-9: Contains data that DIRECTLY supports computing/deriving the answer (e.g., table row with needed figures)
- 6-7: Contains CLOSELY related data (same metric but different period, or supporting context)
- 4-5: Mentions the topic but lacks the specific data needed
- 2-3: Only tangentially related (e.g., mentions company but wrong section/metric)
- 0-1: Not useful for answering this question

For financial questions, ask yourself:
1. Does it have the EXACT metric asked? (CapEx ≠ OpEx, Revenue ≠ Profit)
2. Does it have the CORRECT time period? (FY24 ≠ FY23, Q2 ≠ Full Year)
3. Does it have the CORRECT company? (Flex ≠ Jabil)
4. Is the data complete enough to answer? (partial data = lower score)

CapEx synonyms: "Purchases of property and equipment", "Capital expenditures", "Additions to PP&E", "Property, plant and equipment additions"

Return ONLY a JSON array of scores in the same order, e.g., [8, 3, 10, 5]"""
    
    def __init__(self, batch_size: int = 5, llm_weight: float = 0.7):
        self.batch_size = batch_size
        self.llm_weight = llm_weight
        self.vector_weight = 1 - llm_weight
    
    def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """Rerank results using LLM scoring with weighted combination."""
        if not OPENAI_API_KEY:
            return results[:top_k]
        
        if len(results) <= top_k:
            return results
        
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Process in batches
        for batch_start in range(0, len(results), self.batch_size):
            batch = results[batch_start:batch_start + self.batch_size]
            
            # Build passages
            passages = []
            for i, result in enumerate(batch):
                header = f"[{result.company} | {result.filing_type} | {result.fiscal_year}]"
                preview = result.content[:600]
                passages.append(f"Passage {i+1} {header}:\n{preview}")
            
            passages_text = "\n\n---\n\n".join(passages)
            
            user_prompt = f"""Question: {query}

Score each passage (0-10):

{passages_text}

Return JSON array of {len(batch)} scores:"""
            
            try:
                response = client.chat.completions.create(
                    model=RERANK_MODEL,
                    max_tokens=100,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                
                response_text = response.choices[0].message.content.strip()
                
                # Parse scores
                if "```" in response_text:
                    match = re.search(r'\[[\d,\s\.]+\]', response_text)
                    response_text = match.group(0) if match else "[]"
                
                scores = json.loads(response_text)
                
                # Apply weighted scoring
                for result, llm_score in zip(batch, scores):
                    llm_normalized = float(llm_score) / 10.0
                    combined = self.llm_weight * llm_normalized + self.vector_weight * result.score
                    result.score = round(combined, 4)
                    result.metadata["llm_score"] = llm_score
                    result.metadata["combined_score"] = combined
            
            except Exception:
                pass
        
        # Sort by score
        results.sort(key=lambda r: r.score, reverse=True)
        
        return results[:top_k]


# ---------------------------------------------------------------------------
# ASSEMBLED RETRIEVER
# ---------------------------------------------------------------------------

class AssembledRetriever:
    """
    Composable retrieval system with pluggable strategies.
    
    Combines multiple retrieval methods based on query analysis:
    - Vector search for semantic similarity
    - BM25 for keyword matching
    - Table search for financial data
    - Parent expansion for context
    - LLM reranking for final ranking
    
    Usage:
        retriever = AssembledRetriever()
        
        # Simple search
        results = retriever.search("What was Flex's CapEx in FY24?")
        
        # With specific strategy
        results = retriever.search(
            query="...",
            strategy="hybrid",  # "vector", "bm25", "hybrid", "auto"
            use_parent_expansion=True,
            use_reranking=True,
        )
    """
    
    def __init__(
        self,
        use_bm25: bool = True,
        use_reranking: bool = True,
        use_parent_expansion: bool = True,
        rerank_batch_size: int = 5,
        llm_weight: float = 0.7,
    ):
        self.vector_retriever = VectorRetriever()
        self.bm25_retriever = BM25Retriever() if use_bm25 else None
        self.table_retriever = TableRetriever()
        self.query_router = QueryRouter()
        self.parent_expander = ParentExpander()
        self.llm_reranker = LLMReranker(
            batch_size=rerank_batch_size,
            llm_weight=llm_weight,
        ) if use_reranking else None
        
        self.use_parent_expansion = use_parent_expansion
    
    def search(
        self,
        query: str,
        company: Optional[str] = None,
        top_k: Optional[int] = None,
        strategy: str = "auto",
        use_parent_expansion: Optional[bool] = None,
        use_reranking: Optional[bool] = None,
        use_structured_context: bool = True,
    ) -> dict:
        """
        Execute search with assembled retrieval pipeline.
        
        RAG-Challenge-2 routing: Parameters are auto-tuned based on query type.
        
        Args:
            query: Search query
            company: Filter by company
            top_k: Number of final results (auto if None)
            strategy: "auto", "vector", "bm25", "hybrid", "table"
            use_parent_expansion: Override default parent expansion setting
            use_reranking: Override default reranking setting
            use_structured_context: Group context by company/year/section
        
        Returns:
            dict with:
            - results: List of RetrievalResult
            - context: Combined context for LLM
            - analysis: Query analysis
            - strategy_used: Actual strategy used
            - config_used: Retrieval config parameters
        """
        # Analyze query and get recommended config
        analysis = self.query_router.analyze(query)
        config = self.query_router.get_config(analysis.query_type)
        route_type = self.query_router.get_route_type(query, analysis)
        
        # Use analysis-recommended values if not overridden
        effective_top_k = top_k if top_k is not None else analysis.recommended_top_k
        effective_rerank = use_reranking if use_reranking is not None else analysis.use_reranking
        rerank_sample = analysis.recommended_rerank_sample
        
        # Override company from analysis if not specified
        if not company and len(analysis.companies) == 1:
            company = analysis.companies[0]
        
        # Handle comparison queries specially (R1)
        if analysis.is_comparison and len(analysis.companies) >= 2:
            return self.search_comparison(
                query=query,
                companies=analysis.companies,
                top_k_per_company=config.top_k,
            )
        
        # Select strategy
        if strategy == "auto":
            strategy = config.strategy
        
        # Execute retrieval with rerank sample size
        retrieval_size = rerank_sample if effective_rerank else effective_top_k * 2
        
        if strategy == "hybrid" and self.bm25_retriever:
            results = self._hybrid_search(query, company, retrieval_size)
        elif strategy == "bm25" and self.bm25_retriever:
            results = self.bm25_retriever.retrieve(query, company, retrieval_size)
        elif strategy == "table":
            results = self.table_retriever.retrieve(query, company, retrieval_size)
        else:  # vector
            results = self.vector_retriever.retrieve(query, company, retrieval_size)
        
        # Apply time decay for R2 (realtime) queries
        if route_type == "R2_REALTIME":
            results = apply_time_decay(results, decay_rate=0.15)
            results.sort(key=lambda r: r.score, reverse=True)
        
        # Parent expansion based on query type
        should_expand = use_parent_expansion if use_parent_expansion is not None else self.use_parent_expansion
        if should_expand:
            results = self.parent_expander.expand(results)
        
        # Reranking
        if effective_rerank and self.llm_reranker:
            results = self.llm_reranker.rerank(query, results, effective_top_k)
        else:
            results = results[:effective_top_k]
        
        # Build context (structured or simple)
        context = self._build_context(
            results,
            structured=use_structured_context,
            deduplicate=True,
        )
        
        return {
            "results": [r.to_dict() for r in results],
            "context": context,
            "analysis": {
                "query_type": analysis.query_type,
                "companies": analysis.companies,
                "is_comparison": analysis.is_comparison,
                "suggested_sections": analysis.suggested_sections,
                "time_reference": analysis.time_reference,
                "detected_year": analysis.detected_year,
            },
            "config_used": {
                "top_k": effective_top_k,
                "rerank_sample_size": rerank_sample,
                "use_reranking": effective_rerank,
                "parent_granularity": config.parent_granularity,
                "strategy": strategy,
                "route_type": route_type,  # R1/R2/R3
            },
            "strategy_used": strategy,
            "route_type": route_type,
            "num_results": len(results),
        }
    
    def _auto_select_strategy(self, analysis: QueryAnalysis) -> str:
        """Auto-select retrieval strategy based on query analysis."""
        if analysis.query_type == "table_lookup":
            return "table"
        elif analysis.query_type == "numeric":
            return "hybrid"  # BM25 helps with exact number matching
        else:
            return "vector"
    
    def _hybrid_search(
        self,
        query: str,
        company: Optional[str],
        top_k: int,
    ) -> list[RetrievalResult]:
        """Combine vector and BM25 results using RRF."""
        vector_results = self.vector_retriever.retrieve(query, company, top_k)
        bm25_results = self.bm25_retriever.retrieve(query, company, top_k)
        
        return merge_results_rrf([vector_results, bm25_results])
    
    def _build_context(
        self,
        results: list[RetrievalResult],
        structured: bool = True,
        deduplicate: bool = True,
    ) -> str:
        """
        Build combined context from results.
        
        RAG-Challenge-2 Augmentation:
        1. Group by company/year/section for clarity
        2. Deduplicate similar passages (avoid wasting tokens)
        3. Preserve table headers and units
        """
        if not results:
            return ""
        
        if not structured:
            # Simple linear context
            parts = []
            for i, result in enumerate(results, 1):
                content = result.parent_content if result.parent_content else result.content
                header = f"[Source {i}: {result.company} | {result.source} | Page {result.page_num}]"
                parts.append(f"{header}\n{content}")
            return "\n\n---\n\n".join(parts)
        
        # Structured context: group by company → year → section
        return self._build_structured_context(results, deduplicate)
    
    def _build_structured_context(
        self,
        results: list[RetrievalResult],
        deduplicate: bool = True,
    ) -> str:
        """
        Build structured context grouped by Company → Fiscal Year → Section.
        Prioritizes tables and deduplicates similar content.
        """
        from collections import defaultdict
        
        # Group results
        grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        
        for result in results:
            company = result.company or "Unknown"
            year = result.fiscal_year or "Unknown"
            section = result.section_header or "General"
            
            content = result.parent_content if result.parent_content else result.content
            
            grouped[company][year][section].append({
                "content": content,
                "page": result.page_num,
                "source": result.source,
                "score": result.score,
                "is_table": result.chunk_type == "table" or "table" in result.metadata.get("table_type", ""),
            })
        
        # Build structured output
        parts = []
        
        for company in sorted(grouped.keys()):
            parts.append(f"═══ {company.upper()} ═══")
            
            for year in sorted(grouped[company].keys(), reverse=True):
                parts.append(f"\n▸ Fiscal Year {year}")
                
                for section in grouped[company][year]:
                    items = grouped[company][year][section]
                    
                    # Sort: tables first, then by score
                    items.sort(key=lambda x: (-int(x["is_table"]), -x["score"]))
                    
                    # Deduplicate
                    if deduplicate:
                        items = self._deduplicate_items(items)
                    
                    if items:
                        parts.append(f"\n  [{section}]")
                        for item in items:
                            prefix = "📊 " if item["is_table"] else ""
                            page_info = f"(Page {item['page']})" if item["page"] else ""
                            parts.append(f"  {prefix}{page_info}")
                            parts.append(f"  {item['content'][:2000]}")  # Limit per item
            
            parts.append("")  # Spacing between companies
        
        return "\n".join(parts)
    
    def _deduplicate_items(
        self,
        items: list[dict],
        similarity_threshold: float = 0.85,
    ) -> list[dict]:
        """
        Remove near-duplicate content to save tokens.
        Uses simple Jaccard similarity on word sets.
        """
        if len(items) <= 1:
            return items
        
        unique = []
        seen_word_sets = []
        
        for item in items:
            words = set(item["content"].lower().split())
            
            is_duplicate = False
            for seen_words in seen_word_sets:
                if not words or not seen_words:
                    continue
                intersection = len(words & seen_words)
                union = len(words | seen_words)
                jaccard = intersection / union if union > 0 else 0
                
                if jaccard >= similarity_threshold:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique.append(item)
                seen_word_sets.append(words)
        
        return unique
    
    def search_comparison(
        self,
        query: str,
        companies: list[str],
        top_k_per_company: int = 8,
    ) -> dict:
        """
        Special search for comparison queries with structured plan.
        
        RAG-Challenge-2 multi-company comparison:
        1. Generate a retrieval plan (what to find for each company)
        2. Search each company separately
        3. Build aligned comparison context
        4. Track missing data explicitly
        """
        # Generate comparison plan
        analysis = self.query_router.analyze(query)
        plan = self._generate_comparison_plan(query, companies, analysis)
        
        all_results = []
        per_company = {}
        data_found = {}  # Track what was found vs missing
        
        for company in companies:
            company_results = self.search(
                query=query,
                company=company,
                top_k=top_k_per_company,
                strategy="hybrid",
                use_structured_context=False,  # We'll build custom context
            )
            per_company[company] = company_results["results"]
            all_results.extend(company_results["results"])
            
            # Check what data was found
            data_found[company] = {
                "num_results": len(company_results["results"]),
                "has_tables": any(
                    r.get("chunk_type") == "table" or "table" in str(r.get("metadata", {}))
                    for r in company_results["results"]
                ),
                "fiscal_years": list(set(
                    r.get("fiscal_year", "") for r in company_results["results"] if r.get("fiscal_year")
                )),
            }
        
        # Ensure evidence alignment (min 2 per company)
        evidence_coverage = ensure_evidence_coverage(
            {c: [RetrievalResult(**r) if isinstance(r, dict) else r for r in results]
             for c, results in per_company.items()},
            companies,
            min_per_company=2,
        )
        
        # Build structured comparison context
        context = self._build_comparison_context(query, companies, per_company, plan, data_found)
        
        # Build comparison table (B4 output format)
        comparison_table = self._build_comparison_table(companies, per_company, plan)
        
        return {
            "results": all_results,
            "per_company": per_company,
            "context": context,
            "comparison_table": comparison_table,  # NEW: Formatted comparison table
            "companies_searched": companies,
            "comparison_plan": plan,
            "data_coverage": data_found,
            "evidence_coverage": evidence_coverage,  # NEW: Track evidence gaps
            "analysis": {
                "query_type": "comparison",
                "is_comparison": True,
                "suggested_sections": analysis.suggested_sections,
                "time_reference": analysis.time_reference,
            },
            "route_type": "R1_COMPARISON",
        }
    
    def _generate_comparison_plan(
        self,
        query: str,
        companies: list[str],
        analysis: QueryAnalysis,
    ) -> dict:
        """
        Generate a retrieval plan for comparison queries.
        Identifies what metrics/data to find for each company.
        """
        # Extract metrics from query
        metrics_to_find = []
        query_lower = query.lower()
        
        metric_patterns = {
            "capex": ["capex", "capital expenditure", "capital spending", "pp&e purchases"],
            "revenue": ["revenue", "sales", "net sales", "top line"],
            "profit": ["profit", "net income", "earnings", "income"],
            "margin": ["margin", "gross margin", "operating margin"],
            "assets": ["assets", "total assets", "net assets"],
            "debt": ["debt", "liabilities", "borrowings"],
        }
        
        for metric, keywords in metric_patterns.items():
            if any(kw in query_lower for kw in keywords):
                metrics_to_find.append(metric)
        
        if not metrics_to_find:
            metrics_to_find = ["general_comparison"]
        
        return {
            "companies": companies,
            "metrics": metrics_to_find,
            "sections_to_search": analysis.suggested_sections or ["Financial Statements"],
            "time_period": analysis.detected_year or "latest",
            "comparison_type": "side_by_side",
        }
    
    def _build_comparison_context(
        self,
        query: str,
        companies: list[str],
        per_company: dict,
        plan: dict,
        data_found: dict,
    ) -> str:
        """
        Build aligned comparison context for multi-company questions.
        
        Format:
        ┌─────────────────────────────────────────┐
        │ COMPARISON: [metric] across companies   │
        ├─────────────────────────────────────────┤
        │ Company A:                              │
        │   [extracted data]                      │
        │ Company B:                              │
        │   [extracted data]                      │
        │ Missing: Company C (not found)          │
        └─────────────────────────────────────────┘
        """
        parts = []
        
        # Header with plan
        parts.append("═══ COMPARISON ANALYSIS ═══")
        parts.append(f"Query: {query}")
        parts.append(f"Metrics: {', '.join(plan['metrics'])}")
        parts.append(f"Period: {plan['time_period']}")
        parts.append("")
        
        # Per-company data
        for company in companies:
            parts.append(f"▸ {company.upper()}")
            
            results = per_company.get(company, [])
            coverage = data_found.get(company, {})
            
            if not results:
                parts.append("  ⚠️ No relevant data found in filings")
            else:
                # Group by year
                by_year = {}
                for r in results:
                    year = r.get("fiscal_year", "Unknown")
                    if year not in by_year:
                        by_year[year] = []
                    by_year[year].append(r)
                
                for year in sorted(by_year.keys(), reverse=True):
                    parts.append(f"  FY{year}:")
                    for r in by_year[year][:3]:  # Limit per year
                        content = r.get("parent_content") or r.get("content", "")
                        is_table = r.get("chunk_type") == "table"
                        prefix = "  📊 " if is_table else "  • "
                        
                        # Truncate but preserve key numbers
                        content_preview = content[:800]
                        parts.append(f"{prefix}{content_preview}")
            
            # Coverage note
            years = coverage.get("fiscal_years", [])
            if years:
                parts.append(f"  📅 Years found: {', '.join(sorted(years, reverse=True))}")
            
            parts.append("")
        
        # Missing data warning
        missing = [c for c in companies if not per_company.get(c)]
        if missing:
            parts.append("⚠️ DATA NOT FOUND:")
            for c in missing:
                parts.append(f"  - {c}: No matching documents in database")
        
        return "\n".join(parts)
    
    def _build_comparison_table(
        self,
        companies: list[str],
        per_company: dict,
        plan: dict,
    ) -> str:
        """
        Build formatted comparison table (B4 output format).
        
        Output:
        | Company | Results | Has Tables | Years | Top Themes |
        |---------|---------|------------|-------|------------|
        | Flex    | 5       | Yes        | 2024  | CapEx      |
        """
        lines = [
            "## Comparison Table",
            "",
            "| Company | Results Found | Has Tables | Fiscal Years | Metrics |",
            "|---------|---------------|------------|--------------|---------|",
        ]
        
        for company in companies:
            results = per_company.get(company, [])
            count = len(results)
            
            # Check for tables
            has_tables = any(
                r.get("chunk_type") == "table" or "table" in str(r.get("metadata", {}))
                for r in results
            )
            tables_str = "✓" if has_tables else "✗"
            
            # Get fiscal years
            years = sorted(set(
                r.get("fiscal_year", "") for r in results if r.get("fiscal_year")
            ), reverse=True)
            years_str = ", ".join(years[:3]) if years else "N/A"
            
            # Metrics found
            metrics = plan.get("metrics", [])
            metrics_str = ", ".join(m.title() for m in metrics[:2]) if metrics else "General"
            
            lines.append(f"| {company} | {count} | {tables_str} | {years_str} | {metrics_str} |")
        
        # Add evidence pack section
        lines.append("")
        lines.append("## Evidence Pack")
        lines.append("")
        
        for company in companies:
            results = per_company.get(company, [])[:2]  # Top 2 per company
            
            if results:
                lines.append(f"### {company}")
                for i, r in enumerate(results, 1):
                    source = r.get("source", "Unknown")
                    fy = r.get("fiscal_year", "")
                    page = r.get("page_num", "")
                    content = (r.get("content", "") or "")[:200]
                    
                    lines.append(f"**[{i}] {source} | FY{fy} | Page {page}**")
                    lines.append(f"> {content}...")
                    lines.append("")
        
        # Add caveats
        lines.append("## Caveats")
        missing = [c for c in companies if not per_company.get(c)]
        if missing:
            lines.append(f"- Missing data for: {', '.join(missing)}")
        else:
            lines.append("- All companies have evidence")
        
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CONVENIENCE FUNCTION
# ---------------------------------------------------------------------------

_default_retriever = None


def get_assembled_retriever() -> AssembledRetriever:
    """Get or create the default AssembledRetriever instance."""
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = AssembledRetriever()
    return _default_retriever


def assembled_search(
    query: str,
    company: Optional[str] = None,
    top_k: int = 10,
    strategy: str = "auto",
) -> dict:
    """Convenience function for assembled retrieval."""
    retriever = get_assembled_retriever()
    return retriever.search(query, company, top_k, strategy)
