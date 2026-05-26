"""
Hybrid RAG pipeline combining document retrieval, web search, and conversation memory.

Now supports AssembledRetriever for pluggable retrieval strategies:
- "rag" - Classic vector search with LLM reranking
- "assembled" - NEW: Pluggable strategies (vector + BM25 + parent expansion)
- "web" - Web search only
- "hybrid" - Classic RAG + web search
"""
from typing import Optional

from backend.rag.retriever import search_documents
from backend.rag.generator import generate_response, is_comparative_financial
from backend.rag.web_search import search_web
from backend.aichat.memory import add_message, get_conversation_history
from backend.rag.assembled_retriever import get_assembled_retriever
from backend.aichat.financial_cache.service import answer_financial_query, query_metric
from backend.aichat.financial_cache.companies import resolve_all_tickers, fiscal_label as fc_fiscal_label


def _build_financial_cache_context(query: str) -> str:
    """Pre-fetch capex + revenue from financial_cache for each company in the query.

    Injects authoritative yfinance numbers so the LLM can calculate % of revenue
    and correctly identify the most recent quarter without relying on prose in SEC filings.
    """
    tickers = resolve_all_tickers(query)
    if not tickers:
        return ""

    lines = ["## Financial Cache Data",
             "Source: yfinance. Use these figures as ground truth for numeric values.",
             ""]
    for ticker in tickers:
        capex_rows = query_metric(ticker, "Capital Expenditure", period_type="quarterly", limit=4)
        capex_rows = [r for r in capex_rows if r.get("value") is not None]
        rev_rows = query_metric(ticker, "Total Revenue", period_type="quarterly", limit=4)
        rev_rows = [r for r in rev_rows if r.get("value") is not None]
        ann_rev = query_metric(ticker, "Total Revenue", period_type="annual", limit=1)
        ann_rev = [r for r in ann_rev if r.get("value") is not None]

        if not capex_rows and not rev_rows:
            continue

        lines.append(f"### {ticker}")
        for r in capex_rows[:3]:
            lbl = fc_fiscal_label(ticker, r["period_end"]) or r["period_end"]
            v = abs(r["value"])
            lines.append(f"- CapEx {lbl} (period_end {r['period_end']}): ${v/1e6:,.0f}M")
        for r in rev_rows[:3]:
            lbl = fc_fiscal_label(ticker, r["period_end"]) or r["period_end"]
            v = r["value"]
            lines.append(f"- Revenue {lbl} (period_end {r['period_end']}): ${v/1e9:,.2f}B")
        for r in ann_rev[:1]:
            lbl = fc_fiscal_label(ticker, r["period_end"]) or r["period_end"]
            fy = lbl.split(" ")[0] if " " in lbl else lbl
            v = r["value"]
            lines.append(f"- Annual Revenue {fy} (period_end {r['period_end']}): ${v/1e9:,.2f}B")
        # Pre-compute quarterly CapEx as % of revenue for latest matching period
        if capex_rows and rev_rows:
            rev_by_period = {r["period_end"]: r["value"] for r in rev_rows if r.get("value")}
            latest_cap = capex_rows[0]
            period = latest_cap["period_end"]
            if period in rev_by_period and rev_by_period[period] > 0:
                cap_v = abs(latest_cap["value"])
                rev_v = rev_by_period[period]
                pct = cap_v / rev_v * 100
                lbl = fc_fiscal_label(ticker, period) or period
                lines.append(
                    f"- CapEx % of Revenue {lbl} (quarterly): {pct:.1f}%"
                    f" (${cap_v/1e6:,.0f}M / ${rev_v/1e9:,.2f}B)"
                )
        lines.append("")

    return "\n".join(lines)


def _format_docs(docs: list[dict]) -> str:
    """Format retrieved documents into context string."""
    if not docs:
        return ""
    parts = []
    for i, doc in enumerate(docs, 1):
        header = f"[{doc.get('company', '?')} | {doc.get('filing_type', '?')} | {doc.get('fiscal_year', '?')} {doc.get('quarter', '')}]"
        parts.append(f"--- Document {i} {header} ---\n{doc['content']}")
    return "\n\n".join(parts)


def _format_web_results(results: list[dict]) -> str:
    """Format web search results into context string."""
    if not results:
        return ""
    parts = []
    for r in results:
        parts.append(f"**{r.get('title', '')}**\n{r.get('description', '')}\nSource: {r.get('url', '')}")
    return "\n\n".join(parts)




async def process_query(
    query: str,
    mode: str = "rag",
    company_filter: Optional[str] = None,
    session_id: Optional[str] = None,
    n_results: int = 15,
    use_reranking: bool = True,
    retrieval_strategy: str = "auto",
) -> dict:
    """
    Process a user query through the hybrid pipeline.

    Args:
        query: User question
        mode: "rag" | "web" | "hybrid" | "assembled" (NEW)
        company_filter: Optional company to filter by
        session_id: Optional session for conversation memory
        n_results: Number of documents to retrieve
        use_reranking: Whether to use LLM reranking (default: True)
        retrieval_strategy: For "assembled" mode - "auto" | "vector" | "bm25" | "hybrid" | "table"

    Returns:
        Dict with response, sources, mode used
    """
    context = ""
    web_context = ""
    sources = []
    analysis = None

    # Financial cache short-circuit: numeric financial questions hit SQLite
    # and skip RAG/web entirely. CapEx breakdown / non-numeric questions
    # fall through to the original flow. See docs/financial_cache/design.zh.md §6.
    try:
        cache_result = answer_financial_query(query)
    except Exception:
        cache_result = None
    if cache_result is not None:
        if session_id:
            add_message(session_id, "user", query)
            add_message(session_id, "assistant", cache_result["response"])
        # Drop the internal `context` field before returning to API consumers.
        cache_result.pop("context", None)
        return cache_result

    # NEW: Assembled retriever mode with pluggable strategies
    if mode == "assembled":
        retriever = get_assembled_retriever()
        result = retriever.search(
            query=query,
            company=company_filter,
            top_k=n_results,
            strategy=retrieval_strategy,
            use_parent_expansion=True,
            use_reranking=use_reranking,
        )
        context = result["context"]
        analysis = result["analysis"]
        
        sources = [
            {
                "company": d.get("company"),
                "source": d.get("source"),
                "filing_type": d.get("filing_type"),
                "fiscal_year": d.get("fiscal_year"),
                "similarity": d.get("score"),
                "page_num": d.get("page_num"),
                "section_header": d.get("section_header"),
            }
            for d in result["results"][:5]
        ]
    
    elif mode in ("rag", "hybrid"):
        # Comparative financial queries need broader retrieval: more docs, no company filter
        is_comp = is_comparative_financial(query)
        eff_n = max(n_results, 20) if is_comp else n_results
        eff_company = None if is_comp else company_filter
        docs = search_documents(
            query,
            company_filter=eff_company,
            n_results=eff_n,
            use_reranking=use_reranking,
        )
        context = _format_docs(docs)
        # Prepend authoritative cache numbers so LLM can pick the most recent
        # quarter and calculate % of revenue without relying on SEC filing prose.
        if is_comp:
            cache_ctx = _build_financial_cache_context(query)
            if cache_ctx:
                context = f"{cache_ctx}\n\n{context}"
        sources = [
            {
                "company": d.get("company"),
                "source": d.get("source"),
                "filing_type": d.get("filing_type"),
                "fiscal_year": d.get("fiscal_year"),
                "similarity": d.get("similarity"),
            }
            for d in docs[:8]
        ]

    if mode in ("web", "hybrid"):
        try:
            web_results = await search_web(query)
            web_context = _format_web_results(web_results)
        except Exception:
            web_context = ""

    # Include conversation history if session exists
    if session_id:
        history = get_conversation_history(session_id)
        if history:
            history_text = "\n".join(
                f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
                for m in history[-4:]
            )
            context = f"## Conversation Context\n{history_text}\n\n{context}"

    response = generate_response(query, context, web_context)

    if session_id:
        add_message(session_id, "user", query)
        add_message(session_id, "assistant", response)

    result_dict = {
        "response": response,
        "sources": sources,
        "mode": mode,
        "reranking_enabled": use_reranking,
    }
    
    # Include query analysis for assembled mode
    if analysis:
        result_dict["query_analysis"] = analysis
        result_dict["retrieval_strategy"] = retrieval_strategy
    
    return result_dict


def process_query_sync(
    query: str,
    mode: str = "rag",
    company_filter: Optional[str] = None,
    session_id: Optional[str] = None,
    n_results: int = 15,
    use_reranking: bool = True,
    retrieval_strategy: str = "auto",
) -> dict:
    """Synchronous version of process_query."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    process_query(query, mode, company_filter, session_id, n_results, use_reranking, retrieval_strategy),
                )
                return future.result()
        else:
            return loop.run_until_complete(
                process_query(query, mode, company_filter, session_id, n_results, use_reranking, retrieval_strategy)
            )
    except RuntimeError:
        return asyncio.run(
            process_query(query, mode, company_filter, session_id, n_results, use_reranking, retrieval_strategy)
        )
