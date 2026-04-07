"""
Chat API routes with SSE streaming, query analysis, and smart routing.
"""
import re
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.rag.retriever import search_documents, search_cross_company
from backend.rag.generator import generate_response_streaming
from backend.rag.assembled_retriever import get_assembled_retriever
from backend.aichat.memory import (
    add_message,
    get_conversation_history,
    clear_session,
    get_session_info,
    get_all_sessions,
    cleanup_expired_sessions,
)
from backend.rag.web_search import search_web, format_web_results_for_context
from backend.core.config import COMPANIES
from backend.core.config import OPENAI_API_KEY, ANTHROPIC_API_KEY, LLM_MODEL, ANTHROPIC_MODEL
from backend.core.config import DATA_DIR
from backend.core.llm_client import llm_complete

router = APIRouter()

COMPANY_NAMES = {
    config["name"].split()[0].lower(): config["name"].split()[0]
    for config in COMPANIES.values()
}
COMPANY_NAMES.update({t.lower(): config["name"].split()[0] for t, config in COMPANIES.items()})

METRIC_KEYWORDS = {
    "capex": ["capex", "capital expenditure", "capital spending", "pp&e",
              "property plant and equipment", "property, plant"],
    "revenue": ["revenue", "sales", "top line", "top-line"],
    "margin": ["margin", "gross margin", "operating margin", "profit margin"],
    "ai": ["ai", "artificial intelligence", "machine learning", "gpu",
           "data center", "datacenter", "hyperscale"],
    "guidance": ["guidance", "outlook", "forecast", "expect"],
}

COMPARISON_TRIGGERS = [
    "compare", "comparison", "vs", "versus", "against", "between",
    "how does", "how do", "relative to", "compared to",
    "all companies", "each company", "every company",
]


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    mode: str = "rag"  # "rag" | "web" | "hybrid" | "assembled" (NEW)
    include_web: bool = False
    company_filter: Optional[str] = None
    retrieval_strategy: str = "auto"  # For assembled mode: "auto" | "vector" | "bm25" | "hybrid" | "table"
    use_reranking: bool = True
    answer_provider: str = "openai"  # "openai" | "claude"
    fallback_to_general_llm: bool = False
    strict_grounding: bool = True
    hybrid_multi_output: bool = True
    max_response_words: Optional[int] = None

NO_HIT_MESSAGE = "I couldn't find relevant documents to answer your question. Try rephrasing or check that the data has been ingested."
CUSTOM_QUESTIONS_FILE = Path(DATA_DIR) / "chat_custom_questions.json"


class CustomQuestionRequest(BaseModel):
    label: str
    query: str


def _load_custom_questions() -> list[dict]:
    if not CUSTOM_QUESTIONS_FILE.exists():
        return []
    try:
        with open(CUSTOM_QUESTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _save_custom_questions(items: list[dict]) -> None:
    CUSTOM_QUESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CUSTOM_QUESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _provider_value(provider: str) -> str:
    return (provider or "openai").strip().lower()


def _fallback_enabled(request: ChatRequest) -> bool:
    """
    Product rule:
    - Fallback only allowed in Hybrid mode
    - User must explicitly enable provider (openai/claude)
    """
    provider = _provider_value(request.answer_provider)
    return request.mode == "hybrid" and request.fallback_to_general_llm and provider in {"openai", "claude"}


_TABLE_PATTERNS = re.compile(
    r"\b(in\s+(?:a\s+)?table(?:\s+format)?|show.*?table|table.*?format|"
    r"compare.*?table|not\s+paragraph|year.over.year\s+change|"
    r"numbers?\s+in\s+a\s+table|tabular\s+form)\b",
    re.IGNORECASE | re.DOTALL,
)


def is_table_query(query: str) -> bool:
    """Return True when the user explicitly asks for a table layout."""
    return bool(_TABLE_PATTERNS.search(query))


def _extract_query_terms(query: str) -> list[str]:
    """Extract meaningful query terms for lightweight evidence checks."""
    terms = re.findall(r"[a-zA-Z][a-zA-Z0-9&/-]{2,}", (query or "").lower())
    stop = {
        "what", "which", "when", "where", "why", "how", "does", "did", "is", "are",
        "the", "and", "for", "with", "from", "into", "that", "this", "these", "those",
        "company", "companies", "across", "about", "than", "then", "have", "has",
        "had", "can", "could", "would", "should", "your", "their", "them", "our",
        "all", "any", "its", "his", "her", "who", "whom", "whose", "been", "being",
    }
    return [t for t in terms if t not in stop]


def _has_sufficient_document_evidence(query: str, docs: list[dict], min_docs: int = 1) -> bool:
    """
    Strict evidence gate for RAG-only answers.
    Requires at least one reasonably relevant document and basic term overlap.
    """
    if not docs or len(docs) < min_docs:
        return False

    query_terms = _extract_query_terms(query)
    top_docs = docs[:5]

    # Similarity gate (works for both regular and assembled outputs where score is 0..1)
    has_similarity = any(float(d.get("similarity", 0) or 0) >= 0.35 for d in top_docs)

    # Lexical overlap gate to prevent unrelated snippets from authorizing an answer
    if query_terms:
        overlap_hits = 0
        for d in top_docs:
            text = (
                (d.get("content") or "") + " " +
                (d.get("parent_content") or "") + " " +
                (d.get("section_header") or "") + " " +
                (d.get("source") or "")
            ).lower()
            matches = sum(1 for t in query_terms[:12] if t in text)
            if matches >= 2:
                overlap_hits += 1
        has_overlap = overlap_hits >= 1
    else:
        has_overlap = True

    return has_similarity and has_overlap


def _compose_hybrid_three_part_response(
    file_answer: str,
    web_answer: str,
    ai_answer: str,
) -> str:
    """Render hybrid response in 3 explicit sections."""
    return (
        "## 1) Filing Search Result\n"
        f"{file_answer}\n\n"
        "## 2) Web Search Result\n"
        f"{web_answer}\n\n"
        "## 3) AI Synthesis\n"
        f"{ai_answer}"
    )


def _compose_generic_fallback_synthesis(answer: str, provider_used: Optional[str] = None) -> str:
    """Explicitly label fallback as generic when retrieval channels have no evidence."""
    provider_label = provider_used or "general model"
    return (
        "Notice: Filing search and web search both returned no evidence for this query.\n"
        "We are now using a generic AI fallback response.\n"
        "This part is not grounded in filing/web evidence.\n"
        f"Fallback provider: {provider_label}\n\n"
        f"{answer}"
    )


def _local_backup_answer(query: str) -> str:
    """Deterministic local fallback to avoid empty/error-like responses."""
    return (
        "I could not retrieve reliable source context right now, but here is a working analysis outline:\n\n"
        f"1. Core question: {query}\n"
        "2. What to compare: demand trend, capacity ramp, margin impact, and customer concentration.\n"
        "3. Recommended scope: Flex, Jabil, Celestica, Benchmark, Sanmina over FY2025-FY2026.\n"
        "4. Risk checks: tariff/policy exposure, supply constraints, execution bottlenecks.\n"
        "5. Next step: retry with updated filings/news sync for evidence-backed numbers."
    )


def _looks_like_no_hit(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    markers = [
        "couldn't find relevant documents",
        "i couldn't find relevant documents",
        "not enough context",
        "insufficient context",
        "no relevant documents",
        "unable to find",
        "cannot find",
        "don't have enough information",
        "do not have enough information",
    ]
    return any(m in t for m in markers)


def _is_no_hit_answer(text: str) -> bool:
    """Detect no-hit style answers used by filing/web sub-answers."""
    t = (text or "").strip().lower()
    if not t:
        return True
    markers = [
        "not found in provided sources",
        "not found in web sources",
        "i couldn't find relevant documents",
        "no answer generated due to insufficient evidence",
    ]
    return any(m in t for m in markers)


def _truncate_by_max_words(text: str, max_words: Optional[int]) -> str:
    """
    Truncate response length for UX control.
    - For CJK-heavy text: limit by CJK character count
    - Otherwise: limit by whitespace-separated word count
    """
    if not text or not max_words or max_words <= 0:
        return text

    import re as _re
    cjk_chars = _re.findall(r"[\u4e00-\u9fff]", text)
    # If many CJK chars exist, user likely expects "字数" control
    if len(cjk_chars) >= 20:
        count = 0
        out = []
        for ch in text:
            if _re.match(r"[\u4e00-\u9fff]", ch):
                count += 1
            out.append(ch)
            if count >= max_words:
                break
        trimmed = "".join(out).rstrip()
        return trimmed + ("..." if len(trimmed) < len(text) else "")

    # Preserve original whitespace/newlines; do not collapse formatting with split/join.
    token_matches = list(_re.finditer(r"\S+", text))
    if len(token_matches) <= max_words:
        return text
    cut_end = token_matches[max_words - 1].end()
    return text[:cut_end].rstrip() + "..."


def _truncate_hybrid_ai_section_only(text: str, max_words: Optional[int]) -> str:
    """
    Apply max length only to the `3) AI Synthesis` section in hybrid responses.
    Keep Filing/Web sections untouched and preserve markdown formatting.
    """
    if not text or not max_words or max_words <= 0:
        return text
    marker = "## 3) AI Synthesis\n"
    idx = text.find(marker)
    if idx < 0:
        return _truncate_by_max_words(text, max_words)
    head = text[: idx + len(marker)]
    body = text[idx + len(marker):]
    return head + _truncate_by_max_words(body, max_words)


def _general_fallback_answer(
    query: str,
    provider: str = "openai",
    required_companies: Optional[list[str]] = None,
) -> tuple[str, str]:
    """
    Fallback answer when retrieval context is empty or clearly insufficient.
    Returns (answer_text, provider_used).
    """
    selected = _provider_value(provider)
    system = (
        "You are a senior EMS industry research assistant. "
        "Provide concise, analyst-style answers focused on data center infrastructure, "
        "CapEx, margins, customers, risks, and strategy. "
        "If exact facts are uncertain, state assumptions briefly and suggest what to verify."
    )
    if required_companies:
        system += (
            " You must explicitly cover every company in this list and do not omit any: "
            + ", ".join(required_companies)
            + ". If evidence is missing for a company, still include it with a brief assumption label."
        )
    messages = [{"role": "user", "content": query}]

    def _try_openai() -> tuple[str, str] | None:
        if not OPENAI_API_KEY:
            return None
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            model = LLM_MODEL if LLM_MODEL.startswith("gpt-") else "gpt-4o"
            resp = client.chat.completions.create(
                model=model,
                max_tokens=1200,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": query},
                ],
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                return text, "openai"
        except Exception:
            return None
        return None

    def _try_claude() -> tuple[str, str] | None:
        if not ANTHROPIC_API_KEY:
            return None
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            model = ANTHROPIC_MODEL if "claude" in ANTHROPIC_MODEL else "claude-sonnet-4-6"
            resp = client.messages.create(
                model=model,
                max_tokens=1200,
                system=system,
                messages=[{"role": "user", "content": query}],
            )
            if resp.content and getattr(resp.content[0], "text", ""):
                return resp.content[0].text.strip(), "claude"
        except Exception:
            return None
        return None

    # Preferred provider, then automatic fallback to the other
    provider_order = ["openai", "claude"] if selected == "openai" else ["claude", "openai"]
    for p in provider_order:
        result = _try_openai() if p == "openai" else _try_claude()
        if result:
            return result

    # Fallback to configured provider path
    try:
        text = llm_complete(messages=messages, system=system, model_key="main", max_tokens=1200, stream=False)
        if isinstance(text, str) and text.strip():
            return text.strip(), "configured-provider"
    except Exception:
        pass

    return _local_backup_answer(query), "local-backup"


def _detect_companies(query: str) -> list[str]:
    """Detect company names or tickers in the query."""
    q_lower = query.lower()
    found = []
    for key, canonical in COMPANY_NAMES.items():
        if key in q_lower and canonical not in found:
            found.append(canonical)
    return found


def _parse_company_scope(raw_filter: Optional[str]) -> list[str]:
    """Parse request.company_filter into canonical company names."""
    if not raw_filter:
        return []
    parts = [p.strip() for p in str(raw_filter).split(",") if p.strip()]
    seen = set()
    scoped: list[str] = []
    for part in parts:
        key = part.lower()
        canonical = COMPANY_NAMES.get(key)
        if not canonical:
            # accept already-canonical names
            canonical = part
        if canonical not in seen:
            seen.add(canonical)
            scoped.append(canonical)
    return scoped


def _search_docs_for_scope(
    query: str,
    scope: list[str],
    n_results: int,
    use_reranking: bool,
    is_comparison: bool,
) -> list[dict]:
    """
    Retrieve docs using explicit company scope when provided.
    If multiple companies are selected, search each one and merge.
    """
    if not scope:
        if is_comparison:
            return search_cross_company(query, n_results=max(30, n_results))
        return search_documents(query, n_results=n_results, use_reranking=use_reranking)

    if len(scope) == 1:
        return search_documents(
            query,
            company_filter=scope[0],
            n_results=n_results,
            use_reranking=use_reranking,
        )

    # Multi-company hard filter: query each selected company and merge.
    per_company_n = max(8, (max(30, n_results) // len(scope)) + 2)
    merged: list[dict] = []
    for company in scope:
        try:
            sub = search_documents(
                query,
                company_filter=company,
                n_results=per_company_n,
                use_reranking=use_reranking,
            )
            merged.extend(sub)
        except Exception:
            continue

    # De-duplicate by source+page+company+prefix content, then rank by similarity.
    dedup = {}
    for d in merged:
        key = (
            d.get("company", ""),
            d.get("source", ""),
            d.get("page_num", 0),
            (d.get("content", "") or "")[:120],
        )
        if key not in dedup:
            dedup[key] = d

    docs = list(dedup.values())
    docs.sort(key=lambda x: float(x.get("similarity", 0) or 0), reverse=True)
    target_n = max(30, n_results) if is_comparison else n_results
    return docs[:target_n]


def _detect_metrics(query: str) -> list[str]:
    """Detect financial metric categories in the query."""
    q_lower = query.lower()
    found = []
    for metric, keywords in METRIC_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            found.append(metric)
    return found


def _is_comparison_query(query: str, companies: list[str]) -> bool:
    """Check if the query is asking for a comparison."""
    q_lower = query.lower()
    if len(companies) >= 2:
        return True
    return any(trigger in q_lower for trigger in COMPARISON_TRIGGERS)


def _build_context(docs: list[dict]) -> str:
    """Format retrieved documents into a context string for the LLM."""
    if not docs:
        return ""
    parts = []
    for i, doc in enumerate(docs, 1):
        header = f"[{doc['company']} | {doc['filing_type']} | {doc['fiscal_year']}"
        if doc.get("quarter"):
            header += f" {doc['quarter']}"
        header += f" | sim={doc['similarity']:.2f}]"
        # Use full parent content when available (page/section with tables included)
        # This ensures financial tables (like cash flow statements) are fully visible
        content = doc.get("parent_content") or doc["content"]
        if len(content) > 3000:
            content = content[:3000] + "..."
        parts.append(f"{header}\n{content}")
    return "\n\n---\n\n".join(parts)


def _sse_event(event: str, data: dict) -> str:
    """Format a server-sent event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_response(request: ChatRequest):
    """Main streaming generator that handles the full RAG pipeline."""
    session_id = request.session_id or str(uuid.uuid4())
    query = request.query.strip()

    # Step 1: Analyse the query
    companies = _detect_companies(query)
    company_scope = _parse_company_scope(request.company_filter)
    effective_companies = company_scope if company_scope else companies
    metrics = _detect_metrics(query)
    is_comparison = _is_comparison_query(query, effective_companies)

    yield _sse_event("step", {
        "icon": "🔍",
        "label": "Query Analysis",
        "detail": f"Companies: {effective_companies or 'auto'} | Metrics: {metrics or 'general'}",
    })

    # Step 2: Determine routing
    use_agentic = is_comparison and len(effective_companies) >= 2 and not company_scope

    if use_agentic:
        yield _sse_event("step", {
            "icon": "🤖",
            "label": "Routing",
            "detail": "Using agentic multi-step retrieval for comparison query",
        })
    else:
        yield _sse_event("step", {
            "icon": "📄",
            "label": "Routing",
            "detail": "Using single-call retrieval",
        })

    # Step 3: Retrieve documents
    if use_agentic:
        try:
            from backend.rag.agentic import agentic_stream
            add_message(session_id, "user", query)
            async for event_type, event_data in agentic_stream(query):
                yield _sse_event(event_type, event_data)
            return
        except ImportError:
            pass

    effective_include_web = request.include_web or request.mode in ("web", "hybrid")

    # NEW: Use AssembledRetriever for "assembled" mode
    docs = []
    assembled_context = ""
    query_analysis = None
    
    if request.mode == "assembled":
        retriever = get_assembled_retriever()
        result = retriever.search(
            query=query,
            company=(company_scope[0] if len(company_scope) == 1 else None) or (companies[0] if len(companies) == 1 else None),
            top_k=15,
            strategy=request.retrieval_strategy,
            use_parent_expansion=True,
            use_reranking=request.use_reranking,
        )
        docs = [
            {
                "company": d.get("company", ""),
                "filing_type": d.get("filing_type", ""),
                "fiscal_year": d.get("fiscal_year", ""),
                "quarter": d.get("quarter", ""),
                "similarity": d.get("score", 0),
                "content": d.get("parent_content") or d.get("content", ""),
                "source": d.get("source", ""),
                "page_num": d.get("page_num", 0),
                "section_header": d.get("section_header", ""),
            }
            for d in result["results"]
        ]
        assembled_context = result.get("context", "")
        query_analysis = result.get("analysis", {})
        
        yield _sse_event("step", {
            "icon": "🔧",
            "label": "Assembled Retriever",
            "detail": f"Strategy: {result.get('strategy_used', 'auto')} | Type: {query_analysis.get('query_type', 'unknown')}",
        })
    elif request.mode == "web":
        docs = []
    elif request.mode in ("rag", "hybrid"):
        docs = _search_docs_for_scope(
            query=query,
            scope=effective_companies,
            n_results=15,
            use_reranking=request.use_reranking,
            is_comparison=is_comparison,
        )

    yield _sse_event("step", {
        "icon": "📚",
        "label": "Retrieved",
        "detail": f"{len(docs)} document chunks",
    })

    # Step 4: Optional web search
    web_context = ""
    web_result_count = 0
    if effective_include_web:
        try:
            web_query = query
            if effective_companies:
                web_query = f"{' '.join(effective_companies)} {query}"
            web_results = await search_web(web_query)
            if web_results:
                web_result_count = len(web_results)
                web_context = format_web_results_for_context(web_results)
                yield _sse_event("step", {
                    "icon": "🌐",
                    "label": "Web Search",
                    "detail": f"{len(web_results)} web results found",
                })
        except Exception:
            pass

    # Step 5: Build context and generate
    # For assembled mode, use pre-built context; otherwise build from docs
    if request.mode == "assembled" and assembled_context:
        context = assembled_context
    else:
        context = _build_context(docs)

    has_doc_evidence = _has_sufficient_document_evidence(query, docs) if request.mode in ("rag", "assembled") else True

    if (request.strict_grounding and request.mode in ("rag", "assembled") and not has_doc_evidence):
        yield _sse_event("token", {"text": "No sufficiently relevant filing evidence found for this question in current documents. Please refine the query or switch to Web/Hybrid mode."})
        yield _sse_event("done", {"session_id": session_id})
        return

    if not context and not web_context:
        fallback_allowed = _fallback_enabled(request)
        if request.mode == "hybrid":
            if fallback_allowed:
                fallback_text, provider_used = _general_fallback_answer(
                    query,
                    request.answer_provider,
                    required_companies=effective_companies if effective_companies else None,
                )
                yield _sse_event("step", {
                    "icon": "🛟",
                    "label": "Fallback",
                    "detail": f"Filing/Web no-hit; using {provider_used} generic answer",
                })
                hybrid_text = _compose_hybrid_three_part_response(
                    "Not found in filing sources.",
                    "Not found in web sources.",
                    _compose_generic_fallback_synthesis(fallback_text, provider_used),
                )
                yield _sse_event("token", {"text": hybrid_text})
                add_message(session_id, "user", query)
                add_message(session_id, "assistant", hybrid_text)
            else:
                yield _sse_event("token", {"text": _compose_hybrid_three_part_response(
                    "Not found in filing sources.",
                    "Not found in web sources.",
                    "Generic AI fallback is disabled. Enable provider/fallback to get a general answer."
                )})
        else:
            # Keep original no-hit behavior for Filing Search and Web Search modes.
            yield _sse_event("token", {"text": NO_HIT_MESSAGE})
        yield _sse_event("done", {"session_id": session_id})
        return

    # Save user message to session
    add_message(session_id, "user", query)

    yield _sse_event("step", {
        "icon": "✨",
        "label": "Generating",
        "detail": "Streaming response from Claude",
    })

    # Stream tokens
    full_response = ""
    for chunk in generate_response_streaming(query, context, web_context):
        full_response += chunk
        yield _sse_event("token", {"text": chunk})

    # Secondary fallback for streaming if generated text indicates no retrieval hit
    if _fallback_enabled(request) and _looks_like_no_hit(full_response):
        fallback_text, provider_used = _general_fallback_answer(
            query,
            request.answer_provider,
            required_companies=effective_companies if effective_companies else None,
        )
        yield _sse_event("step", {
            "icon": "🛟",
            "label": "Fallback",
            "detail": f"Switching to {provider_used}",
        })
        yield _sse_event("token", {"text": f"\n\n{fallback_text}"})
        full_response = fallback_text

    # Save assistant response to session
    add_message(session_id, "assistant", full_response)

    yield _sse_event("done", {"session_id": session_id})


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE streaming chat endpoint."""
    return StreamingResponse(
        _stream_response(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat")
async def chat(request: ChatRequest):
    """Non-streaming chat endpoint (returns full response)."""
    from backend.rag.generator import generate_response

    session_id = request.session_id or str(uuid.uuid4())
    query = request.query.strip()

    companies = _detect_companies(query)
    company_scope = _parse_company_scope(request.company_filter)
    effective_companies = company_scope if company_scope else companies
    query_analysis = None
    strategy_used = None
    effective_include_web = request.include_web or request.mode in ("web", "hybrid")
    is_comparison = _is_comparison_query(query, effective_companies)

    # NEW: Use AssembledRetriever for "assembled" mode
    if request.mode == "assembled":
        retriever = get_assembled_retriever()
        result = retriever.search(
            query=query,
            company=(company_scope[0] if len(company_scope) == 1 else None) or (companies[0] if len(companies) == 1 else None),
            top_k=15,
            strategy=request.retrieval_strategy,
            use_parent_expansion=True,
            use_reranking=request.use_reranking,
        )
        docs = [
            {
                "company": d.get("company", ""),
                "filing_type": d.get("filing_type", ""),
                "fiscal_year": d.get("fiscal_year", ""),
                "source": d.get("source", ""),
                "similarity": d.get("score", 0),
                "content": d.get("parent_content") or d.get("content", ""),
                "page_num": d.get("page_num", 0),
                "section_header": d.get("section_header", ""),
            }
            for d in result["results"]
        ]
        context = result.get("context", "")
        query_analysis = result.get("analysis", {})
        strategy_used = result.get("strategy_used", "auto")
    elif request.mode in ("rag", "hybrid"):
        docs = _search_docs_for_scope(
            query=query,
            scope=effective_companies,
            n_results=15,
            use_reranking=request.use_reranking,
            is_comparison=is_comparison,
        )
        context = _build_context(docs)
    else:
        docs = []
        context = ""

    web_context = ""
    web_result_count = 0
    if effective_include_web:
        try:
            web_query = f"{' '.join(effective_companies)} {query}" if effective_companies else query
            web_results = await search_web(web_query)
            if web_results:
                web_result_count = len(web_results)
                web_context = format_web_results_for_context(web_results)
        except Exception:
            pass

    fallback_used = False
    provider_used = None

    add_message(session_id, "user", query)
    has_file_evidence = _has_sufficient_document_evidence(query, docs) if request.mode in ("rag", "assembled", "hybrid") else True
    has_web_evidence = web_result_count > 0
    fallback_allowed = _fallback_enabled(request)

    has_doc_evidence = _has_sufficient_document_evidence(query, docs) if request.mode in ("rag", "assembled") else True
    if request.strict_grounding and request.mode in ("rag", "assembled") and not has_doc_evidence:
        response_text = "No sufficiently relevant filing evidence found for this question in current documents. Please refine the query or switch to Web/Hybrid mode."
    elif request.mode == "hybrid" and request.hybrid_multi_output:
        # Case A: no evidence in both retrieval channels
        if not has_file_evidence and not has_web_evidence:
            if fallback_allowed:
                fallback_text, provider_used = _general_fallback_answer(
                    query,
                    request.answer_provider,
                    required_companies=effective_companies if effective_companies else None,
                )
                fallback_used = True
                response_text = _compose_hybrid_three_part_response(
                    "Not found in filing sources.",
                    "Not found in web sources.",
                    _compose_generic_fallback_synthesis(fallback_text, provider_used),
                )
            else:
                response_text = _compose_hybrid_three_part_response(
                    "Not found in filing sources.",
                    "Not found in web sources.",
                    "Generic AI fallback is disabled. Enable provider/fallback to get a general answer.",
                )
        else:
            # Case B: at least one source has evidence -> output file/web answers + AI synthesis
            file_answer = (
                generate_response(query, context, "")
                if has_file_evidence and context
                else "Not found in filing sources."
            )
            web_answer = (
                generate_response(query, "", web_context)
                if has_web_evidence and web_context
                else "Not found in web sources."
            )

            # If both channel answers are effectively no-hit, force generic fallback.
            # This handles false-positive evidence gating and web failure/empty results.
            both_no_hit = _is_no_hit_answer(file_answer) and _is_no_hit_answer(web_answer)
            if both_no_hit and fallback_allowed:
                fallback_text, provider_used = _general_fallback_answer(
                    query,
                    request.answer_provider,
                    required_companies=effective_companies if effective_companies else None,
                )
                fallback_used = True
                response_text = _compose_hybrid_three_part_response(
                    file_answer,
                    web_answer,
                    _compose_generic_fallback_synthesis(fallback_text, provider_used),
                )
            elif both_no_hit and not fallback_allowed:
                response_text = _compose_hybrid_three_part_response(
                    file_answer,
                    web_answer,
                    "Generic AI fallback is disabled. Enable provider/fallback to get a general answer.",
                )
            else:
                synthesis_query = (
                    "Summarize and reconcile the two evidence channels for the question below. "
                    "Prefer evidence-backed statements, flag conflicts, and be concise.\n\n"
                    f"Original question: {query}"
                )
                ai_answer = generate_response(
                    synthesis_query,
                    f"## Filing Answer\n{file_answer}",
                    f"## Web Answer\n{web_answer}",
                )
                response_text = _compose_hybrid_three_part_response(file_answer, web_answer, ai_answer)
    elif not context and not web_context:
        # Keep original no-hit behavior for non-hybrid modes.
        if fallback_allowed:
            response_text, provider_used = _general_fallback_answer(
                query,
                request.answer_provider,
                required_companies=effective_companies if effective_companies else None,
            )
            fallback_used = True
        else:
            response_text = NO_HIT_MESSAGE
    else:
        response_text = generate_response(query, context, web_context)

        # Secondary fallback if generated answer clearly indicates no retrieval hit
        if _fallback_enabled(request) and _looks_like_no_hit(response_text):
            response_text, provider_used = _general_fallback_answer(
                query,
                request.answer_provider,
                required_companies=effective_companies if effective_companies else None,
            )
            fallback_used = True

    if request.mode == "hybrid":
        response_text = _truncate_hybrid_ai_section_only(response_text, request.max_response_words)
    else:
        response_text = _truncate_by_max_words(response_text, request.max_response_words)

    # --- Structured table payload (for table-intent queries) ---
    table_payload_out = None
    narrative_text_out = None

    if is_table_query(query) and (context or web_context):
        from backend.rag.generator import generate_table_response
        table_result = generate_table_response(query, context, web_context)
        if table_result:
            table_payload_out = table_result["table_payload"]
            narrative_text_out = table_result["narrative_text"]
            # Replace response_text with the short narrative so markdown table is not shown
            response_text = narrative_text_out or response_text

    add_message(session_id, "assistant", response_text)

    response_dict = {
        "response": response_text,
        "session_id": session_id,
        "sources": [
            {
                "company": d.get("company", ""),
                "source": d.get("source", ""),
                "fiscal_year": d.get("fiscal_year", ""),
                "page_num": d.get("page_num"),
                "section_header": d.get("section_header"),
            }
            for d in docs[:5]
        ],
        "fallback_used": fallback_used,
        "provider_used": provider_used,
        "retrieval_summary": {
            "filing_hits": len(docs),
            "web_hits": web_result_count,
            "strict_grounding": request.strict_grounding,
            "fallback_enabled": _fallback_enabled(request),
        },
        "table_payload": table_payload_out,
        "narrative_text": narrative_text_out,
    }

    # Include assembled mode metadata
    if query_analysis:
        response_dict["query_analysis"] = query_analysis
        response_dict["strategy_used"] = strategy_used

    return response_dict


# ---------------------------------------------------------------------------
# Custom preset question endpoints
# ---------------------------------------------------------------------------

@router.get("/chat/custom-questions")
async def list_custom_questions():
    """List user-added preset questions (persisted)."""
    items = _load_custom_questions()
    return {"questions": items, "total": len(items)}


@router.post("/chat/custom-questions")
async def create_custom_question(request: CustomQuestionRequest):
    """Create and persist a user-added preset question."""
    label = (request.label or "").strip()
    query = (request.query or "").strip()
    if not label or not query:
        raise HTTPException(status_code=400, detail="Both label and query are required")

    items = _load_custom_questions()
    item = {
        "id": f"custom_{uuid.uuid4().hex[:12]}",
        "label": label,
        "query": query,
        "created_at": datetime.utcnow().isoformat(),
    }
    items.insert(0, item)
    _save_custom_questions(items)
    return {"question": item, "total": len(items)}


@router.delete("/chat/custom-questions/{question_id}")
async def delete_custom_question(question_id: str):
    """Delete a persisted custom preset question."""
    items = _load_custom_questions()
    filtered = [q for q in items if q.get("id") != question_id]
    if len(filtered) == len(items):
        raise HTTPException(status_code=404, detail="Question not found")
    _save_custom_questions(filtered)
    return {"deleted": question_id, "total": len(filtered)}


# ---------------------------------------------------------------------------
# Session management endpoints
# ---------------------------------------------------------------------------

@router.get("/chat/sessions")
async def list_sessions():
    """List all active chat sessions."""
    cleanup_expired_sessions()
    return {"sessions": get_all_sessions()}


@router.get("/chat/sessions/{session_id}")
async def get_session(session_id: str):
    """Get info about a specific session."""
    return get_session_info(session_id)


@router.get("/chat/sessions/{session_id}/history")
async def get_history(session_id: str):
    """Get conversation history for a session."""
    return {"messages": get_conversation_history(session_id)}


@router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    clear_session(session_id)
    return {"status": "deleted", "session_id": session_id}
