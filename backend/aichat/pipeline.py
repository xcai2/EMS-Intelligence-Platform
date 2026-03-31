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
from backend.rag.generator import generate_response
from backend.rag.web_search import search_web
from backend.aichat.memory import add_message, get_conversation_history
from backend.rag.assembled_retriever import get_assembled_retriever


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
        docs = search_documents(
            query, 
            company_filter=company_filter, 
            n_results=n_results,
            use_reranking=use_reranking,
        )
        context = _format_docs(docs)
        sources = [
            {
                "company": d.get("company"),
                "source": d.get("source"),
                "filing_type": d.get("filing_type"),
                "fiscal_year": d.get("fiscal_year"),
                "similarity": d.get("similarity"),
            }
            for d in docs[:5]
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
