"""
Chat API routes with SSE streaming, query analysis, and smart routing.
"""
import re
import json
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.rag.retriever import (
    search_documents,
    search_cross_company,
    search_multi_company_by_periods,
    _extract_quarter_range,
)
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
from backend.rag.web_search import search_web, search_web_with_diagnostics, format_web_results_for_context, enrich_web_results
from backend.aichat.financial_cache.service import answer_financial_query as _answer_financial_query
from backend.core.config import COMPANIES
from backend.core.config import OPENAI_API_KEY, ANTHROPIC_API_KEY, LLM_MODEL, ANTHROPIC_MODEL, GOOGLE_API_KEY, GEMINI_MODEL
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
    answer_provider: str = "openai"  # "openai" | "claude" | "gemini"
    fallback_to_general_llm: bool = False
    strict_grounding: bool = True
    hybrid_multi_output: bool = True
    max_response_words: Optional[int] = None

NO_HIT_MESSAGE = "I couldn't find relevant documents to answer your question. Try rephrasing or check that the data has been ingested."
CUSTOM_QUESTIONS_FILE = Path(DATA_DIR) / "chat_custom_questions.json"
PRESET_QUESTIONS_CACHE_FILE = Path(DATA_DIR) / "preset_questions_cache.json"
PRESET_QUESTIONS_CACHE_TTL_HOURS = 360

COMPANY_FY_START = {
    "Flex": 4,
    "Jabil": 9,
    "Celestica": 1,
    "Benchmark Electronics": 1,
    "Sanmina": 10,
    "Plexus": 10,
}


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
    - User must explicitly enable provider (openai/claude/gemini)
    """
    provider = _provider_value(request.answer_provider)
    return request.mode == "hybrid" and request.fallback_to_general_llm and provider in {"openai", "claude", "gemini"}


_TABLE_PATTERNS = re.compile(
    # Match any standalone mention of "table" (covers "provide table",
    # "provide a table", "give me a table", "in a table", etc.) plus a
    # few keyword phrases that imply tabular output without using the word.
    r"\btable\b|\b(not\s+paragraph|year.over.year\s+change|tabular\s+form)\b",
    re.IGNORECASE | re.DOTALL,
)


def is_table_query(query: str) -> bool:
    """Return True when the user explicitly asks for a table layout."""
    return bool(_TABLE_PATTERNS.search(query))


def _inject_web_links(text: str, web_results: list[dict]) -> str:
    """Replace 'Web N' references in LLM output with markdown hyperlinks."""
    url_map = {i + 1: r.get("url", "") for i, r in enumerate(web_results)}

    def _replace(m):
        idx = int(m.group(1))
        url = url_map.get(idx)
        if not url:
            return m.group(0)
        return f"[Web {idx}]({url})"

    text = re.sub(r"Web\s+(\d+)", _replace, text)
    # Clean up leftover parens: ([Web 1](url)) -> [Web 1](url)
    text = re.sub(r"\((\[Web \d+\]\([^)]+\))\)", r"\1", text)
    return text


def _clean_query_for_web_search(query: str) -> str:
    """
    Strip prompt instructions and constraints from the query,
    leaving only the user's actual question for web search.
    """
    text = query
    marker = re.search(r"(?i)^structure every response.+?\n\n", text, re.DOTALL)
    if marker:
        text = text[marker.end():]
    text = re.split(r"\n\nConstraints:", text, maxsplit=1)[0]
    text = re.sub(r"(?i)focus on these companies only:[^\n]*", "", text)
    text = re.sub(r"(?i)prioritize\s+FY\d{4}\.", "", text)
    return text.strip()


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
            if matches >= 1:
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

    def _try_gemini() -> tuple[str, str] | None:
        if not GOOGLE_API_KEY:
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=GOOGLE_API_KEY)
            model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                system_instruction=system,
            )
            resp = model.generate_content(
                [{"role": "user", "parts": [{"text": query}]}],
                generation_config={"max_output_tokens": 1200},
            )
            text = (resp.text or "").strip()
            if text:
                return text, "gemini"
        except Exception:
            return None
        return None

    # Preferred provider first, then fall back to the others
    all_providers = ["openai", "claude", "gemini"]
    provider_order = [selected] + [p for p in all_providers if p != selected]
    tryers = {"openai": _try_openai, "claude": _try_claude, "gemini": _try_gemini}
    for p in provider_order:
        fn = tryers.get(p)
        if not fn:
            continue
        result = fn()
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
    """Detect company names or tickers in the query.
    Only scans the actual question part, stripping any instruction prefix
    that appears before a double newline."""
    q = query.split("\n\n")[-1] if "\n\n" in query else query
    q_lower = q.lower()
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


def _get_available_et_periods(company: str, n_recent: int) -> list[tuple[str, str]]:
    """
    Query ChromaDB to find the N most recent (fiscal_year, quarter) pairs that have
    Earnings Transcript documents for the given company.
    Returns periods sorted most-recent-first.
    """
    from backend.core.database import get_company_collection, has_company_collections, get_collection

    try:
        if has_company_collections() and company:
            col = get_company_collection(company)
        else:
            col = get_collection()
        if col.count() == 0:
            return []

        # 先尝试搜 Earnings Transcript
        results = col.get(where={"filing_type": "Earnings Transcript"}, limit=5000)
        metas = results.get("metadatas", [])

        # 没有 transcript，fallback 到所有文档
        if not metas:
            results = col.get(limit=5000)
            metas = results.get("metadatas", [])

    except Exception:
        return []

    # Collect unique (fy, q) pairs with data
    seen: set = set()
    for m in metas:
        fy = m.get("fiscal_year", "")
        q = m.get("quarter", "")
        # quarter 为空时用 Q1 占位，保证有数据可以返回
        if fy and fy not in ("Unknown", ""):
            q = q if q else "Q1"
            seen.add((fy, q))

    # Sort: FY descending, then Q descending within each FY
    def sort_key(p):
        fy_str, q_str = p
        # Extract year number from "FY26" → 26
        try:
            fy_num = int(fy_str.replace("FY", ""))
        except ValueError:
            fy_num = 0
        try:
            q_num = int(q_str.replace("Q", ""))
        except ValueError:
            q_num = 0
        return (fy_num, q_num)

    sorted_periods = sorted(seen, key=sort_key, reverse=True)
    return sorted_periods[:n_recent]


def _search_historical_docs(
    query: str,
    scope: list[str],
    n_quarters: int,
    use_reranking: bool,
) -> list[dict]:
    """
    For historical (last N quarters) queries: retrieve docs per target quarter directly
    from ChromaDB with fiscal_year+quarter filters. Uses actual Earnings Transcript
    quarters in the DB (most recent N), not computed fiscal calendar quarters.
    """
    from backend.core.database import get_company_collection, embed_text, has_company_collections, get_collection

    per_quarter_n = 8  # docs per quarter
    merged: list[dict] = []
    seen: set = set()

    companies = scope if scope else []

    for company in (companies or [None]):
        # Find the N most recent quarters with actual Earnings Transcript data
        target_periods = _get_available_et_periods(company or "", n_quarters)
        if not target_periods:
            continue

        try:
            if has_company_collections() and company:
                col = get_company_collection(company)
            else:
                col = get_collection()
            if col.count() == 0:
                continue

            query_embedding = embed_text(query)

            for fy, q in target_periods:
                # quarter 是占位 Q1 时（原始元数据无 quarter 字段）不加 quarter 过滤
                if q == "Q1" and fy:
                    where_filter = {"fiscal_year": fy}
                else:
                    where_filter = {"$and": [{"fiscal_year": fy}, {"quarter": q}]}
                try:
                    results = col.query(
                        query_embeddings=[query_embedding],
                        n_results=min(per_quarter_n, col.count()),
                        where=where_filter,
                        include=["documents", "metadatas", "distances"],
                    )
                except Exception:
                    continue

                if not results or not results["documents"] or not results["documents"][0]:
                    continue

                for doc_text, metadata, distance in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    key = (
                        metadata.get("company", company or ""),
                        metadata.get("source_file", metadata.get("source", "")),
                        metadata.get("page_num", 0),
                        doc_text[:120],
                    )
                    if key not in seen:
                        seen.add(key)
                        merged.append({
                            "content": doc_text,
                            "company": metadata.get("company", company or ""),
                            "source": metadata.get("source_file", metadata.get("source", "")),
                            "filing_type": metadata.get("filing_type", ""),
                            "fiscal_year": metadata.get("fiscal_year", fy),
                            "quarter": metadata.get("quarter", q),
                            "similarity": round(1 - distance, 4),
                            "section_header": metadata.get("section_header", ""),
                            "page_num": metadata.get("page_num", 0),
                        })
        except Exception:
            continue

    merged.sort(key=lambda x: float(x.get("similarity", 0) or 0), reverse=True)
    return merged


def _extract_calendar_year(query: str) -> Optional[int]:
    """
    Disabled: all year references are treated as fiscal years by default.
    Only activate if user explicitly says 'calendar year'.
    """
    q = query.lower()
    # 只有明确说 calendar year 才走日历年逻辑
    if "calendar year" not in q and "calendar 20" not in q:
        return None
    # Reject FY forms
    if re.search(r"\bfy\s*\d{2,4}\b", q) or re.search(r"\bfiscal\s+(?:year\s+)?\d{2,4}\b", q):
        return None
    m = re.search(r"\b(?:in|during|throughout|for|across|over)\s+(20\d{2})\b", q)
    if m:
        return int(m.group(1))
    return None


def _calendar_year_to_fiscal_periods(calendar_year: int, company: str) -> list[tuple[str, str]]:
    """Return list of (fiscal_year_label, quarter_label) whose calendar months overlap
    with the given calendar year for the company. Uses COMPANY_FY_START from retriever."""
    from backend.rag.retriever import COMPANY_FY_START
    fy_start_month = COMPANY_FY_START.get(company, 1)
    periods: list[tuple[str, str]] = []
    # Check fiscal years that could overlap: the FY whose end falls in calendar_year,
    # plus the one whose start falls in calendar_year. Walk a generous range.
    for fy_actual in range(calendar_year - 1, calendar_year + 2):
        # FY starts in month fy_start_month of fy_actual (if fy_start_month==1)
        # or (fy_actual - 1) if fy_start_month > 1? Convention varies. We use:
        #   FY label year = actual calendar year the fiscal year ENDS in for most EMS companies,
        # but Jabil labels FY by the year it starts (FY2025 = Sept 2024 - Aug 2025 per user note above).
        # Safer: for each candidate fiscal period, compute its calendar (year, month) range
        # directly from fy_start_month and the FY-label convention used in the DB.
        # The DB stores fiscal_year like "FY25". For Jabil: FY25 Q1 = Sept 2024. For Flex: FY25 Q1 = Apr 2024.
        # So: FY_label_year (2 digits) = 2000 + yy; FY Q1 starts month fy_start_month of year:
        #   (fy_label_year - 1) if fy_start_month > 1 else fy_label_year.
        fy_label_year = fy_actual
        q1_start_cal_year = (fy_label_year - 1) if fy_start_month > 1 else fy_label_year
        for qi, q_label in enumerate(["Q1", "Q2", "Q3", "Q4"], start=0):
            start_month_idx = fy_start_month + qi * 3
            start_year = q1_start_cal_year + (start_month_idx - 1) // 12
            start_month = ((start_month_idx - 1) % 12) + 1
            # End month (inclusive) = start + 2
            end_month_idx = start_month_idx + 2
            end_year = q1_start_cal_year + (end_month_idx - 1) // 12
            end_month = ((end_month_idx - 1) % 12) + 1
            # Overlap with calendar_year: any month in [start..end] that is in calendar_year
            overlaps = False
            cur_y, cur_m = start_year, start_month
            for _ in range(3):
                if cur_y == calendar_year:
                    overlaps = True
                    break
                cur_m += 1
                if cur_m > 12:
                    cur_m = 1
                    cur_y += 1
            if overlaps:
                fy_label = f"FY{fy_label_year % 100:02d}"
                periods.append((fy_label, q_label))
    return periods


def _search_historical_docs_by_periods(
    query: str,
    company: str,
    periods: list[tuple[str, str]],
    per_quarter_n: int = 8,
) -> list[dict]:
    """Retrieve docs for an explicit list of (fy, q) periods for a single company."""
    from backend.core.database import get_company_collection, embed_text, has_company_collections, get_collection
    merged: list[dict] = []
    seen: set = set()
    try:
        col = get_company_collection(company) if has_company_collections() else get_collection()
        if col.count() == 0:
            return []
        query_embedding = embed_text(query)
    except Exception:
        return []
    for fy, q in periods:
        try:
            results = col.query(
                query_embeddings=[query_embedding],
                n_results=min(per_quarter_n, col.count()),
                where={"$and": [{"fiscal_year": fy}, {"quarter": q}]},
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            continue
        if not results or not results["documents"] or not results["documents"][0]:
            continue
        for doc_text, metadata, distance in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            key = (
                metadata.get("source_file", metadata.get("source", "")),
                metadata.get("page_num", 0),
                doc_text[:120],
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append({
                "content": doc_text,
                "company": metadata.get("company", company),
                "source": metadata.get("source_file", metadata.get("source", "")),
                "filing_type": metadata.get("filing_type", ""),
                "fiscal_year": metadata.get("fiscal_year", fy),
                "quarter": metadata.get("quarter", q),
                "similarity": round(1 - distance, 4),
                "section_header": metadata.get("section_header", ""),
                "page_num": metadata.get("page_num", 0),
            })
    merged.sort(key=lambda x: float(x.get("similarity", 0) or 0), reverse=True)
    return merged


def _build_calendar_year_note_doc(company: str, calendar_year: int, periods: list[tuple[str, str]]) -> dict:
    """Build a synthetic doc injected at the top of the context warning the LLM
    to restrict coverage to the given fiscal periods."""
    if periods:
        period_str = ", ".join(f"{fy} {q}" for fy, q in periods)
        body = (
            f"[CALENDAR YEAR NOTE] The user asked about CALENDAR {calendar_year}. "
            f"{company}'s fiscal quarters that overlap with calendar {calendar_year} and have data are: "
            f"{period_str}. Cover ONLY these quarters in your response. Do not include other quarters, "
            f"and make the Overview's quarter count and range string exactly describe this set."
        )
    else:
        body = (
            f"[CALENDAR YEAR NOTE] The user asked about CALENDAR {calendar_year}, but no "
            f"{company} fiscal quarters with data overlap that calendar year."
        )
    return {
        "content": body,
        "company": company,
        "source": "calendar_year_note",
        "filing_type": "Note",
        "fiscal_year": "",
        "quarter": "",
        "similarity": 1.0,
        "section_header": "CALENDAR YEAR NOTE",
        "page_num": 0,
    }


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


def _should_force_historical_format(query: str) -> bool:
    """Heuristic fallback for historical questions when query-type detection is inconsistent."""
    q = (query or "").lower()

    # Explicit multi-quarter references like "FY2025 Q2 and Q3", "Q1-Q3", "Q2 to Q4".
    if re.search(r"\bfy\d{2,4}\s*q[1-4]\b", q) and re.search(r"\b(and|to|through|-)\b|,", q):
        return True
    if re.search(r"\bq[1-4]\s*(?:and|to|through|-|,)\s*q[1-4]\b", q):
        return True

    # Relative quarter windows.
    if re.search(r"\b(last|past|previous|prior|recent)\s+(?:\w+|\d+)\s+quarters?\b", q):
        return True

    # Historical stance phrasing.
    if any(k in q for k in ["what did", "how has", "over time", "trend", "shift", "changed"]):
        return True

    return False


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


_HYPERSCALER_NAMES = {
    "amazon", "aws", "microsoft", "azure", "alphabet", "google", "meta",
    "facebook", "oracle", "oci", "hyperscaler", "hyperscalers",
    "big5", "big 5", "big tech",
}
_HYPERSCALER_CAPEX_KEYWORDS = {
    "capex", "capital expenditure", "capital expenditures", "infrastructure spend",
    "infrastructure investment", "data center spend", "datacenter spend",
    "ai investment", "ai spending", "fy2025", "fy2026", "stargate",
}

def _is_hyperscaler_capex_query(query: str) -> bool:
    """Return True if the query is asking about hyperscaler CapEx / AI infrastructure spend."""
    q = query.lower()
    has_hyperscaler = any(name in q for name in _HYPERSCALER_NAMES)
    has_capex_kw = any(kw in q for kw in _HYPERSCALER_CAPEX_KEYWORDS)
    # Also catch generic "how much are they spending" type questions when a hyperscaler is named
    return has_hyperscaler and (has_capex_kw or "spend" in q or "invest" in q or "guidance" in q)


async def _build_hyperscaler_capex_context() -> str:
    """
    Fetch the live Big-5 CapEx data (7-day cached) and format it as a
    plain-text context block for injection into the LLM prompt.
    """
    try:
        from backend.analytics.hyperscaler_guidance import build_big5_capex_response
        data = await build_big5_capex_response()
    except Exception:
        return ""

    companies = data.get("companies", [])
    if not companies:
        return ""

    lines = [
        "=== HYPERSCALER AI CAPEX DATA (Live — use this as source of truth) ===",
        f"Data as of: {data.get('last_updated', 'recent')} | "
        f"Source: {data.get('source', 'Earnings guidance')}",
        "",
    ]

    for c in companies:
        name = c.get("name", c.get("ticker", ""))
        cap26 = c.get("capex_2026_billions")
        cap25 = c.get("capex_2025_billions")
        yoy = c.get("yoy_growth_pct")
        src_date = c.get("guidance_source_date", "")
        confidence = c.get("guidance_confidence", "")

        capex_str = f"${cap26}B" if cap26 is not None else "N/A"
        prev_str  = f"${cap25}B" if cap25 is not None else "N/A"
        yoy_str   = f"+{yoy}%" if yoy is not None else "N/A"

        lines.append(f"**{name}**")
        lines.append(f"  2026 CapEx guidance: {capex_str} | 2025 actual: {prev_str} | YoY: {yoy_str}")
        if src_date:
            lines.append(f"  Source date: {src_date} | Confidence: {confidence}")

        focus = c.get("ai_focus_areas", [])
        if focus:
            lines.append(f"  AI focus: {', '.join(focus)}")

        metrics = c.get("key_metrics") or {}
        if metrics:
            metric_parts = [
                f"{k.replace('_', ' ').title()}: {v}"
                for k, v in metrics.items()
            ]
            lines.append(f"  Key metrics: {' | '.join(metric_parts)}")

        announcements = c.get("recent_announcements", [])
        for ann in announcements[:2]:
            lines.append(f"  • {ann}")
        lines.append("")

    stargate = data.get("stargate_project")
    if stargate:
        lines.append("**Stargate AI Project**")
        inv = stargate.get("total_investment_billions")
        if inv:
            lines.append(f"  Total investment: ${inv}B | Timeline: {stargate.get('timeline', '')}")
        partners = stargate.get("partners", [])
        if partners:
            lines.append(f"  Partners: {', '.join(partners)}")
        for upd in (stargate.get("latest_updates") or [])[:2]:
            lines.append(f"  • {upd}")
        lines.append("")

    total = data.get("total_2026_capex_billions")
    if total:
        lines.append(f"Combined Big-5 2026 CapEx: ${total}B")

    lines.append("=== END HYPERSCALER DATA ===")
    return "\n".join(lines)


def _format_historical_response(result: dict) -> str:
    """Render historical structured output with clear section headings and line breaks."""
    sections: list[str] = []

    opening = (result.get("opening") or "").strip()
    if opening:
        sections.append(f"**Overview**\n{opening}")

    for idx, q in enumerate(result.get("quarters", []) or [], 1):
        quarter = (q.get("quarter") or f"Quarter {idx}").strip()
        date_label = (q.get("date") or "").strip()
        title = f"**{idx}. {quarter}**"
        if date_label:
            title += f" ({date_label})"
        sections.append(title)

        tone_label = (q.get("tone_label") or "").strip()
        summary = (q.get("summary") or "").strip()
        if tone_label and summary:
            sections.append(f"**{tone_label}**\n{summary}")
        elif summary:
            sections.append(summary)
        elif tone_label:
            sections.append(f"**{tone_label}**")

        bullet_points = [bp for bp in (q.get("bullet_points") or []) if str(bp).strip()]
        if bullet_points:
            sections.append("**Key Points**\n\n" + "\n".join(f"- {bp}" for bp in bullet_points))

    formatted = "\n\n".join(s for s in sections if s.strip()).strip()
    if not formatted:
        fallback_answer = (result.get("answer") or "Not found in provided sources.").strip()
        fallback_answer = re.sub(r"\r\n?", "\n", fallback_answer)
        # Normalize single-line fallback text into sectioned lines.
        fallback_answer = re.sub(r"\s+(\d+\.\s*(?:FY\d{2,4}\s+Q[1-4]|Q[1-4]\s+FY\d{2,4})\b)", r"\n\1", fallback_answer)
        fallback_answer = re.sub(r"\s+(###\s*(?:FY\d{2,4}\s+Q[1-4]|Q[1-4]\s+FY\d{2,4})\b)", r"\n\1", fallback_answer)
        fallback_answer = re.sub(r"\s+([A-Za-z][A-Za-z'\-\s]+\bFY\d{2,4}\s+Q[1-4]\b[^\n:]*:)\s*", r"\n\1\n", fallback_answer)
        fallback_answer = re.sub(r"\s*[·•]\s*", "\n- ", fallback_answer)

        lines = [ln.rstrip() for ln in fallback_answer.split("\n")]
        # Group into blocks: preamble (overview), then one block per quarter heading + its bullets.
        blocks: list[list[str]] = [[]]  # start with preamble block
        seq = 1
        in_quarter_section = False
        quarter_ref_pattern = r"(?:FY\d{2,4}\s+Q[1-4]|Q[1-4]\s+FY\d{2,4})"
        quarter_heading_pattern = r"^(?:#{1,6}\s*)?(?:FY\d{2,4}\s+Q[1-4]|Q[1-4]\s+FY\d{2,4})\b"
        quarter_subtitle_pattern = r"^(?:#{1,6}\s*)?.*\b(?:FY\d{2,4}\s+Q[1-4]|Q[1-4]\s+FY\d{2,4})\b.*:\s*$"
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            quarter_refs = re.findall(quarter_ref_pattern, line)
            is_single_quarter_subtitle = re.match(quarter_subtitle_pattern, line) and len(quarter_refs) == 1
            if re.match(quarter_heading_pattern, line) or is_single_quarter_subtitle:
                clean_line = re.sub(r"^#{1,6}\s*", "", line)
                clean_line = re.sub(r"^\d+\.\s*", "", clean_line)
                blocks.append([f"**{seq}. {clean_line}**"])
                seq += 1
                in_quarter_section = True
            elif in_quarter_section and line:
                if line.startswith("- "):
                    blocks[-1].append(line)
                elif line.startswith("•") or line.startswith("·"):
                    blocks[-1].append(f"- {line.lstrip('·•').strip()}")
                else:
                    blocks[-1].append(f"- {line}")
            else:
                blocks[-1].append(raw_line)

        rendered_blocks = ["\n".join(b).strip() for b in blocks if any(x.strip() for x in b)]
        content = "\n\n".join(rendered_blocks).strip()
        content = re.sub(r"^(?:\*\*Overview\*\*|Overview)\s*", "", content, flags=re.IGNORECASE).strip()
        return f"**Overview**\n\n{content}" if content else "**Overview**\n\nNot found in provided sources."
    return formatted


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

    # Step 2: Financial cache check — numeric financial questions hit SQLite
    # and short-circuit the rest of the pipeline (any mode). Non-numeric
    # questions fall through to the normal retrieval flow below.
    # See docs/financial_cache/design.zh.md §6.
    try:
        cache_result = _answer_financial_query(query)
    except Exception:
        cache_result = None
    if cache_result is not None:
        yield _sse_event("step", {
            "icon": "📊",
            "label": "Financial Cache",
            "detail": (
                f"Hit · {cache_result['data']['ticker']} · "
                f"{cache_result['data']['metric']} · "
                f"{len(cache_result['data']['series'])} period(s) from yfinance cache"
            ),
        })
        # When the user asked for a table layout, emit narrative as token and
        # the structured table payload as a separate SSE event so the frontend
        # renders it with its dedicated table component.
        table_payload = cache_result.get("table_payload")
        if table_payload:
            narrative = cache_result.get("narrative_text") or cache_result["response"]
            yield _sse_event("token", {"text": narrative})
            yield _sse_event("table", {
                "narrative_text": narrative,
                "table_payload":  table_payload,
            })
            persisted_text = narrative
        else:
            yield _sse_event("token", {"text": cache_result["response"]})
            persisted_text = cache_result["response"]
        # Strip the frontend's STRUCTURED_RESPONSE_INSTRUCTION prefix so the
        # saved message and sidebar title only carry the user's real question.
        clean_query = query
        if "\n\n" in clean_query:
            clean_query = clean_query.split("\n\n")[-1].strip()
        if "Structure every response" in clean_query:
            clean_query = clean_query.strip().split("\n\n")[-1].strip()
        add_message(session_id, "user", clean_query)
        # Sidebar list — only add on the first message of a session.
        if len(get_conversation_history(session_id)) <= 1:
            _add_to_chat_history(session_id, clean_query)
        add_message(session_id, "assistant", persisted_text)
        # Persist to disk so the chat history sidebar picks this session up.
        # Attach table_payload / narrative_text to the last message so the
        # frontend can re-render the table when the user reopens this session.
        all_messages = get_conversation_history(session_id)
        if all_messages and table_payload:
            all_messages[-1]["table_payload"]  = table_payload
            all_messages[-1]["narrative_text"] = cache_result.get("narrative_text")
        _save_session_messages(session_id, all_messages)
        yield _sse_event("done", {"session_id": session_id})
        return

    yield _sse_event("step", {
        "icon": "📊",
        "label": "Financial Cache",
        "detail": "Miss — falling back to document retrieval",
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
            # 去掉 instruction prefix，只保存实际问题
            clean_query = query
            if "\n\n" in query:
                clean_query = query.split("\n\n")[-1].strip()
            if "Structure every response" in clean_query:
                parts = clean_query.strip().split("\n\n")
                clean_query = parts[-1].strip()
            add_message(session_id, "user", clean_query)
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
    n_quarters = _extract_quarter_range(query)

    if (
        request.mode in ("rag", "hybrid")
        and not use_agentic
        and is_comparison
        and len(effective_companies) >= 2
        and n_quarters
    ):
        docs = search_multi_company_by_periods(
            query=query,
            companies=effective_companies,
            n_quarters=n_quarters,
            n_results=15,
        )
        yield _sse_event("step", {
            "icon": "🗓",
            "label": "Time Alignment",
            "detail": f"Applied last {n_quarters} completed quarters per company fiscal calendar",
        })
    elif request.mode == "assembled":
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

    # Detect historical query early for routing decisions
    from backend.rag.generator import detect_query_type as detect_gen_query_type
    gen_query_type = detect_gen_query_type(query)
    is_historical = gen_query_type == "historical" or _should_force_historical_format(query)

    # For historical single-company queries: supplement with per-quarter retrieval
    # to ensure each target quarter is represented in context
    if is_historical and n_quarters and not is_comparison and len(effective_companies) == 1 and request.mode != "web":
        hist_docs = _search_historical_docs(
            query=query,
            scope=effective_companies,
            n_quarters=n_quarters,
            use_reranking=request.use_reranking,
        )
        if hist_docs:
            # Merge with existing docs, dedup, keep all
            existing_keys = {
                (d.get("company", ""), d.get("source", ""), d.get("page_num", 0), (d.get("content", "") or "")[:120])
                for d in docs
            }
            for d in hist_docs:
                key = (d.get("company", ""), d.get("source", ""), d.get("page_num", 0), (d.get("content", "") or "")[:120])
                if key not in existing_keys:
                    existing_keys.add(key)
                    docs.append(d)

    # Calendar-year historical queries (e.g. "in 2025"): restrict to fiscal quarters
    # whose months actually overlap with that calendar year.
    calendar_year = _extract_calendar_year(query)
    if is_historical and calendar_year and not is_comparison and len(effective_companies) == 1:
        company = effective_companies[0]
        candidate_periods = _calendar_year_to_fiscal_periods(calendar_year, company)
        available = set(_get_available_et_periods(company, n_recent=50))
        target_periods = [p for p in candidate_periods if p in available]
        cy_docs = _search_historical_docs_by_periods(query, company, target_periods) if target_periods else []
        note_doc = _build_calendar_year_note_doc(company, calendar_year, target_periods)
        # Prepend the note so it appears first in context
        docs = [note_doc] + cy_docs + [
            d for d in docs
            if (d.get("fiscal_year", ""), d.get("quarter", "")) in set(target_periods)
        ]
        yield _sse_event("step", {
            "icon": "🗓",
            "label": "Calendar Year Filter",
            "detail": f"Calendar {calendar_year} → {company} quarters: " + (", ".join(f"{fy} {q}" for fy, q in target_periods) or "none"),
        })

    # For historical queries in web mode, supplement with filing database results
    # so quarterly-specific transcript content is available to the LLM
    if is_historical and request.mode == "web" and not docs:
        filing_docs = (
            _search_historical_docs(
                query=query,
                scope=effective_companies,
                n_quarters=n_quarters,
                use_reranking=request.use_reranking,
            ) if (n_quarters and len(effective_companies) == 1) else _search_docs_for_scope(
                query=query, scope=effective_companies,
                n_results=30, use_reranking=request.use_reranking,
                is_comparison=is_comparison,
            )
        )
        if filing_docs:
            docs = filing_docs
            yield _sse_event("step", {
                "icon": "📁",
                "label": "Filing Supplement",
                "detail": f"Historical query: also searched {len(filing_docs)} filing chunks",
            })

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
            clean_q = _clean_query_for_web_search(query)
            web_results: list[dict] = []

            if is_historical and effective_companies and n_quarters and len(effective_companies) == 1:
                # Per-quarter search: one Brave request per target quarter for full coverage
                company_name = effective_companies[0]
                target_periods = _get_available_et_periods(company_name, n_quarters)
                seen_urls: set[str] = set()
                for fy, q in (target_periods or []):
                    q_query = (
                        f"{company_name} {q} {fy} earnings call transcript tariff "
                        f"site:fool.com OR site:marketbeat.com OR site:finance.yahoo.com"
                    )
                    q_results, _ = await search_web_with_diagnostics(q_query)
                    for r in q_results:
                        url = r.get("url", "")
                        if url not in seen_urls:
                            seen_urls.add(url)
                            web_results.append(r)
                if not web_results:
                    # Fallback: single broad search
                    web_results = await search_web(
                        f"{company_name} {clean_q} "
                        f"site:fool.com OR site:marketbeat.com OR site:finance.yahoo.com"
                    )
            elif is_historical and effective_companies:
                web_query = (
                    f"{' '.join(effective_companies)} {clean_q} "
                    f"site:fool.com OR site:marketbeat.com OR site:seekingalpha.com OR site:finance.yahoo.com"
                )
                web_results = await search_web(web_query)
            else:
                web_query = f"{' '.join(effective_companies)} {clean_q}" if effective_companies else clean_q
                web_results = await search_web(web_query)

            if web_results:
                web_results = await enrich_web_results(web_results, max_pages=3)
                web_result_count = len(web_results)
                raw_web_context = format_web_results_for_context(web_results)
                web_context = f"[USE THESE WEB RESULTS AS SOURCE OF TRUTH FOR QUARTER LABELS AND DATES]\n\n{raw_web_context}"
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
        if is_historical:
            try:
                web_query = f"{' '.join(effective_companies)} {query}" if effective_companies else query
                web_results = await search_web(web_query)
                if web_results:
                    web_result_count = len(web_results)
                    web_context = format_web_results_for_context(web_results)
                    has_doc_evidence = True
                    context = web_context
            except Exception:
                pass
        if not has_doc_evidence:
            yield _sse_event("token", {"text": "No sufficiently relevant filing evidence found for this question in current documents. Please refine the query or switch to Web/Hybrid mode."})
            yield _sse_event("done", {"session_id": session_id})
            return

    # Inject live hyperscaler CapEx data when the query is relevant
    if _is_hyperscaler_capex_query(query):
        hyp_context = await _build_hyperscaler_capex_context()
        if hyp_context:
            context = (hyp_context + "\n\n" + context).strip() if context else hyp_context

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
                # 去掉 instruction prefix，只保存实际问题
                clean_query = query
                if "\n\n" in query:
                    clean_query = query.split("\n\n")[-1].strip()
                if "Structure every response" in clean_query:
                    parts = clean_query.strip().split("\n\n")
                    clean_query = parts[-1].strip()
                add_message(session_id, "user", clean_query)
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

    # Save user message to session (去掉 instruction prefix，只保存实际问题)
    clean_query = query
    if "\n\n" in query:
        clean_query = query.split("\n\n")[-1].strip()
    if "Structure every response" in clean_query:
        parts = clean_query.strip().split("\n\n")
        clean_query = parts[-1].strip()
    add_message(session_id, "user", clean_query)

    # 保存到对话历史（只在第一条消息时触发）
    history = get_conversation_history(session_id)
    if len(history) <= 1:
        _add_to_chat_history(session_id, query)

    yield _sse_event("step", {
        "icon": "✨",
        "label": "Generating",
        "detail": "Streaming response from Claude",
    })

    # Stream tokens
    full_response = ""
    
    # Check if this is a historical query — use structured response instead
    from backend.rag.generator import generate_structured_response, detect_query_type as detect_gen_query_type
    gen_query_type = detect_gen_query_type(query)
    use_table = is_table_query(query) and (context or web_context)
    use_historical = (gen_query_type == "historical" or _should_force_historical_format(query)) and not is_comparison and not use_table

    if use_historical:
        result = generate_structured_response(query, context, web_context, force_query_type="historical")
        full_response = _format_historical_response(result)
        yield _sse_event("token", {"text": full_response})
    elif use_table:
        from backend.rag.generator import generate_table_response
        table_result = generate_table_response(query, context, web_context)
        if table_result:
            full_response = table_result.get("narrative_text", "") or ""
            yield _sse_event("token", {"text": full_response})
            yield _sse_event("table", table_result)
        else:
            for chunk in generate_response_streaming(query, context, web_context):
                full_response += chunk
                yield _sse_event("token", {"text": chunk})
    else:
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
    _save_session_messages(session_id, get_conversation_history(session_id))

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


# ---------------------------------------------------------------------------
# Financial cache manual refresh endpoint
# ---------------------------------------------------------------------------
# Runs `refresh_all()` synchronously inside the FastAPI thread pool (the
# endpoint is `def`, not `async def`, so FastAPI offloads it). The refresh
# fetches all 11 tickers from SEC EDGAR + yfinance and overwrites the SQLite
# cache. Takes ~5–10 minutes, so the frontend should show a loading state.
# ---------------------------------------------------------------------------

_FIN_REFRESH_LOCK = threading.Lock()


@router.post("/financial/refresh")
def refresh_financial_cache():
    """Manually re-fetch all tracked tickers and overwrite the cache.

    Returns the per-ticker result dict from `service.refresh_all()`.
    Returns HTTP 409 if a refresh is already in progress.
    """
    if not _FIN_REFRESH_LOCK.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="A financial cache refresh is already running. Please wait.",
        )
    try:
        # Lazy import — keeps yfinance off the import path until actually used.
        from backend.aichat.financial_cache.service import refresh_all
        return refresh_all()
    finally:
        _FIN_REFRESH_LOCK.release()


@router.post("/chat")
async def chat(request: ChatRequest):
    """Non-streaming chat endpoint (returns full response)."""
    from backend.rag.generator import generate_response

    session_id = request.session_id or str(uuid.uuid4())
    query = request.query.strip()

    # Step 1: Query analysis (mirrors /chat/stream order).
    companies = _detect_companies(query)
    company_scope = _parse_company_scope(request.company_filter)
    effective_companies = company_scope if company_scope else companies
    query_analysis = None
    strategy_used = None
    effective_include_web = request.include_web or request.mode in ("web", "hybrid")
    is_comparison = _is_comparison_query(query, effective_companies)
    n_quarters = _extract_quarter_range(query)

    # Step 2: Financial cache check — short-circuits the rest of the pipeline
    # for numeric financial questions (any mode). Non-numeric questions fall
    # through to the normal retrieval flow below.
    try:
        cache_result = _answer_financial_query(query)
    except Exception:
        cache_result = None
    if cache_result is not None:
        # Strip the frontend's STRUCTURED_RESPONSE_INSTRUCTION prefix so the
        # saved message and sidebar title only carry the user's real question.
        clean_query = query
        if "\n\n" in clean_query:
            clean_query = clean_query.split("\n\n")[-1].strip()
        if "Structure every response" in clean_query:
            clean_query = clean_query.strip().split("\n\n")[-1].strip()
        add_message(session_id, "user", clean_query)
        # Sidebar list — only add on the first message of a session.
        if len(get_conversation_history(session_id)) <= 1:
            _add_to_chat_history(session_id, clean_query)
        add_message(session_id, "assistant", cache_result["response"])
        # Persist to disk so the history sidebar picks this session up.
        all_messages = get_conversation_history(session_id)
        table_payload  = cache_result.get("table_payload")
        narrative_text = cache_result.get("narrative_text")
        if all_messages and table_payload:
            all_messages[-1]["table_payload"]  = table_payload
            all_messages[-1]["narrative_text"] = narrative_text
        _save_session_messages(session_id, all_messages)
        cache_result.pop("context", None)
        cache_result["session_id"] = session_id
        return cache_result

    # Detect historical query early so we can choose optimal retrieval strategy
    from backend.rag.generator import detect_query_type as detect_gen_query_type
    gen_query_type = detect_gen_query_type(query)
    is_historical = gen_query_type == "historical" or _should_force_historical_format(query)

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

    # For historical single-company queries: supplement with per-quarter retrieval
    # to ensure each target quarter is represented in context
    if is_historical and n_quarters and not is_comparison and len(effective_companies) == 1:
        hist_docs = _search_historical_docs(
            query=query,
            scope=effective_companies,
            n_quarters=n_quarters,
            use_reranking=request.use_reranking,
        )
        if hist_docs:
            existing_keys = {
                (d.get("company", ""), d.get("source", ""), d.get("page_num", 0), (d.get("content", "") or "")[:120])
                for d in docs
            }
            for d in hist_docs:
                key = (d.get("company", ""), d.get("source", ""), d.get("page_num", 0), (d.get("content", "") or "")[:120])
                if key not in existing_keys:
                    existing_keys.add(key)
                    docs.append(d)
            context = _build_context(docs)

    # Calendar-year historical queries: restrict to fiscal quarters that overlap.
    calendar_year = _extract_calendar_year(query)
    if is_historical and calendar_year and not is_comparison and len(effective_companies) == 1:
        company = effective_companies[0]
        candidate_periods = _calendar_year_to_fiscal_periods(calendar_year, company)
        available = set(_get_available_et_periods(company, n_recent=50))
        target_periods = [p for p in candidate_periods if p in available]
        cy_docs = _search_historical_docs_by_periods(query, company, target_periods) if target_periods else []
        note_doc = _build_calendar_year_note_doc(company, calendar_year, target_periods)
        docs = [note_doc] + cy_docs + [
            d for d in docs
            if (d.get("fiscal_year", ""), d.get("quarter", "")) in set(target_periods)
        ]
        context = _build_context(docs)

    # For historical queries in web mode, also search filing database.
    # Web search returns general articles; actual quarterly transcripts live in ChromaDB.
    if is_historical and request.mode == "web" and not docs:
        filing_docs = (
            _search_historical_docs(
                query=query,
                scope=effective_companies,
                n_quarters=n_quarters,
                use_reranking=request.use_reranking,
            ) if (n_quarters and len(effective_companies) == 1) else _search_docs_for_scope(
                query=query, scope=effective_companies,
                n_results=30, use_reranking=request.use_reranking,
                is_comparison=is_comparison,
            )
        )
        if filing_docs:
            docs = filing_docs
            context = _build_context(filing_docs)

    web_context = ""
    web_result_count = 0
    web_results_list = []
    if effective_include_web:
        try:
            clean_q = _clean_query_for_web_search(query)
            web_results: list[dict] = []

            if is_historical and effective_companies and n_quarters and len(effective_companies) == 1:
                # Per-quarter search: one Brave request per target quarter for full coverage
                company_name = effective_companies[0]
                target_periods = _get_available_et_periods(company_name, n_quarters)
                seen_urls: set[str] = set()
                for fy, q in (target_periods or []):
                    q_query = (
                        f"{company_name} {q} {fy} earnings call transcript tariff "
                        f"site:fool.com OR site:marketbeat.com OR site:finance.yahoo.com"
                    )
                    q_results, _ = await search_web_with_diagnostics(q_query)
                    for r in q_results:
                        url = r.get("url", "")
                        if url not in seen_urls:
                            seen_urls.add(url)
                            web_results.append(r)
                if not web_results:
                    # Fallback: single broad search
                    web_results = await search_web(
                        f"{company_name} {clean_q} "
                        f"site:fool.com OR site:marketbeat.com OR site:finance.yahoo.com"
                    )
            elif is_historical and effective_companies:
                web_query = (
                    f"{' '.join(effective_companies)} {clean_q} "
                    f"site:fool.com OR site:marketbeat.com OR site:seekingalpha.com OR site:finance.yahoo.com"
                )
                web_results = await search_web(web_query)
            else:
                web_query = f"{' '.join(effective_companies)} {clean_q}" if effective_companies else clean_q
                web_results = await search_web(web_query)

            if web_results:
                web_results = await enrich_web_results(web_results, max_pages=3)
                web_results_list = web_results
                web_result_count = len(web_results)
                raw_web_context = format_web_results_for_context(web_results)
                web_context = f"[USE THESE WEB RESULTS AS SOURCE OF TRUTH FOR QUARTER LABELS AND DATES]\n\n{raw_web_context}"
        except Exception:
            pass

    # Inject live hyperscaler CapEx data when the query is relevant
    if _is_hyperscaler_capex_query(query):
        hyp_context = await _build_hyperscaler_capex_context()
        if hyp_context:
            context = (hyp_context + "\n\n" + context).strip() if context else hyp_context

    fallback_used = False
    provider_used = None

    # 去掉 instruction prefix，只保存实际问题
    clean_query = query
    if "\n\n" in query:
        clean_query = query.split("\n\n")[-1].strip()
    if "Structure every response" in clean_query:
        parts = clean_query.strip().split("\n\n")
        clean_query = parts[-1].strip()
    add_message(session_id, "user", clean_query)

    # 保存到对话历史（只在第一条消息时触发）
    history = get_conversation_history(session_id)
    if len(history) <= 1:
        _add_to_chat_history(session_id, query)

    has_file_evidence = _has_sufficient_document_evidence(query, docs) if request.mode in ("rag", "assembled", "hybrid") else True
    has_web_evidence = web_result_count > 0
    fallback_allowed = _fallback_enabled(request)

    has_doc_evidence = _has_sufficient_document_evidence(query, docs) if request.mode in ("rag", "assembled") else True

    if request.strict_grounding and request.mode in ("rag", "assembled") and not has_doc_evidence:
        if is_historical:
            # Auto trigger web search for historical queries
            try:
                web_query = f"{' '.join(effective_companies)} {query}" if effective_companies else query
                import asyncio
                web_results = asyncio.get_event_loop().run_until_complete(search_web(web_query))
                if web_results:
                    web_result_count = len(web_results)
                    web_context = format_web_results_for_context(web_results)
                    has_doc_evidence = True  # allow answer generation with web context
            except Exception:
                pass
        if not has_doc_evidence:
            response_text = "No sufficiently relevant filing evidence found for this question in current documents. Please refine the query or switch to Web/Hybrid mode."
    elif request.mode == "hybrid" and request.hybrid_multi_output:
        # For historical queries, use structured quarter-by-quarter format instead of
        # the 3-part file/web/synthesis split (web articles never contain transcript detail)
        if is_historical and not is_comparison and (context or web_context):
            from backend.rag.generator import generate_structured_response
            result = generate_structured_response(query, context, web_context, force_query_type="historical")
            response_text = _format_historical_response(result)
        # Case A: no evidence in both retrieval channels
        elif not has_file_evidence and not has_web_evidence:
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
        from backend.rag.generator import generate_structured_response, detect_query_type as detect_gen_query_type
        gen_query_type = detect_gen_query_type(query)
        use_table = is_table_query(query) and (context or web_context)
        use_historical = (gen_query_type == "historical" or _should_force_historical_format(query)) and not is_comparison and not use_table

        if use_historical:
            result = generate_structured_response(query, context, web_context, force_query_type="historical")
            response_text = _format_historical_response(result)
        elif use_table:
            from backend.rag.generator import generate_table_response
            table_result = generate_table_response(query, context, web_context)
            if table_result:
                table_payload_out = table_result["table_payload"]
                narrative_text_out = table_result["narrative_text"]
                response_text = narrative_text_out or ""
            else:
                response_text = generate_response(query, context, web_context)
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

    if web_results_list:
        response_text = _inject_web_links(response_text, web_results_list)

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
    # 持久化保存，包含 table_payload 和 narrative_text
    all_messages = get_conversation_history(session_id)
    if all_messages and (table_payload_out or narrative_text_out):
        all_messages[-1]["table_payload"] = table_payload_out
        all_messages[-1]["narrative_text"] = narrative_text_out
    _save_session_messages(session_id, all_messages)

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
        "web_sources": [
            {"index": i + 1, "title": r.get("title", ""), "url": r.get("url", "")}
            for i, r in enumerate(web_results_list)
        ],
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


# ---------------------------------------------------------------------------
# Chat history — persistent across sessions (max 5 recent conversations)
# ---------------------------------------------------------------------------

CHAT_HISTORY_FILE = Path(DATA_DIR) / "chat_history.json"


def _load_chat_history() -> list[dict]:
    if not CHAT_HISTORY_FILE.exists():
        return []
    try:
        with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_chat_history(history: list[dict]) -> None:
    CHAT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _add_to_chat_history(session_id: str, first_message: str) -> None:
    """保存对话到历史记录，最多保留10条。"""
    history = _load_chat_history()
    if any(h["session_id"] == session_id for h in history):
        return

    # 去掉 STRUCTURED_RESPONSE_INSTRUCTION prefix
    clean_message = first_message
    if "\n\nConstraints:" in clean_message:
        clean_message = clean_message.split("\n\nConstraints:")[0]
    if "Structure every response" in clean_message:
        parts = clean_message.strip().split("\n\n")
        clean_message = parts[-1].strip()

    title = clean_message[:40] + ("..." if len(clean_message) > 40 else "")
    history.insert(0, {
        "session_id": session_id,
        "title": title,
        "created_at": datetime.utcnow().isoformat(),
    })
    history = history[:10]
    _save_chat_history(history)


@router.get("/chat/history")
async def get_chat_history():
    """获取最近5条对话记录。"""
    history = _load_chat_history()
    return {"history": history}


# 对话消息持久化文件目录
CHAT_MESSAGES_DIR = Path(DATA_DIR) / "chat_messages"


def _save_session_messages(session_id: str, messages: list[dict]) -> None:
    """持久化保存 session 消息到文件。"""
    CHAT_MESSAGES_DIR.mkdir(parents=True, exist_ok=True)
    file_path = CHAT_MESSAGES_DIR / f"{session_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


def _load_session_messages(session_id: str) -> list[dict]:
    """从文件读取 session 消息。"""
    file_path = CHAT_MESSAGES_DIR / f"{session_id}.json"
    if not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


@router.get("/chat/history/{session_id}")
async def get_chat_session_history(session_id: str):
    """获取某个对话的完整消息记录。先从文件读，文件没有再从内存读。"""
    messages = _load_session_messages(session_id)
    if not messages:
        messages = get_conversation_history(session_id)
    return {"session_id": session_id, "messages": messages}


@router.delete("/chat/history/{session_id}")
async def delete_chat_history_session(session_id: str):
    """删除某个对话的历史记录和消息文件。"""
    history = _load_chat_history()
    history = [h for h in history if h["session_id"] != session_id]
    _save_chat_history(history)

    file_path = CHAT_MESSAGES_DIR / f"{session_id}.json"
    if file_path.exists():
        file_path.unlink()

    return {"deleted": session_id}


# ---------------------------------------------------------------------------
# Preset questions — dynamically generated from latest earnings transcripts
# ---------------------------------------------------------------------------

CATEGORY_DEFINITIONS = {
    "ai-infra": {
        "label": "AI Infrastructure Leadership",
        "focus": "AI data center infrastructure, hyperscaler customers, AI server manufacturing, GPU/compute hardware ramps",
    },
    "capacity": {
        "label": "Capacity & Footprint",
        "focus": "manufacturing capacity expansion, geographic footprint, nearshoring, Mexico/India/Southeast Asia strategies, liquid cooling",
    },
    "financial": {
        "label": "Financial Performance",
        "focus": "revenue growth, gross margin, CapEx, backlog, cash flow, guidance",
    },
    "risks": {
        "label": "Risks & External Factors",
        "focus": "tariffs, geopolitical risks, supply chain, customer concentration, trade policy",
    },
}


def _load_preset_questions_cache() -> dict | None:
    """Load cached preset questions if still valid."""
    if not PRESET_QUESTIONS_CACHE_FILE.exists():
        return None
    try:
        with open(PRESET_QUESTIONS_CACHE_FILE, "r") as f:
            cache = json.load(f)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at < timedelta(hours=PRESET_QUESTIONS_CACHE_TTL_HOURS):
            return cache
    except Exception:
        pass
    return None


def _save_preset_questions_cache(data: dict) -> None:
    """Save preset questions to cache."""
    PRESET_QUESTIONS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["cached_at"] = datetime.now().isoformat()
    with open(PRESET_QUESTIONS_CACHE_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_latest_transcript_quarter(company: str) -> str:
    """
    计算该公司上一个已完结季度的标签（排除当前进行中的季度）。
    返回如 'Q2 FY2026' 的字符串。
    """
    from datetime import date
    today = date.today()
    fy_start = COMPANY_FY_START.get(company, 1)

    month_in_fy = (today.month - fy_start) % 12
    current_q = month_in_fy // 3 + 1

    prev_q = current_q - 1
    prev_month = today.month
    prev_year = today.year

    if prev_q == 0:
        prev_q = 4
        prev_month = (today.month - 3 - 1) % 12 + 1
        if today.month <= 3:
            prev_year = today.year - 1
    else:
        prev_month = today.month - (month_in_fy % 3) - 1
        if prev_month <= 0:
            prev_month += 12
            prev_year = today.year - 1

    if fy_start == 1:
        fy_year = prev_year
    else:
        if prev_month >= fy_start:
            fy_year = prev_year + 1
        else:
            fy_year = prev_year

    fy_label = f"FY{fy_year % 100:02d}"
    return f"Q{prev_q} {fy_label}"


async def _generate_preset_questions_from_transcripts() -> dict:
    """
    Generate preset questions by searching latest earnings transcripts from web.
    """
    companies = {
        "Flex": "Flex Ltd",
        "Jabil": "Jabil",
        "Celestica": "Celestica",
        "Benchmark Electronics": "Benchmark Electronics",
        "Sanmina": "Sanmina",
    }

    all_context_parts = []

    for company_key, company_name in companies.items():
        try:
            latest_q = _get_latest_transcript_quarter(company_key)

            results, _ = await search_web_with_diagnostics(
                f"{company_name} {latest_q} earnings call transcript",
                freshness="py",
            )

            if not results:
                results, _ = await search_web_with_diagnostics(
                    f"{company_name} latest earnings call transcript 2026",
                    freshness="py",
                )

            if results:
                enriched = await enrich_web_results(results[:2], max_pages=2)
                context = format_web_results_for_context(enriched)
                if context:
                    all_context_parts.append(
                        f"=== {company_name} ({latest_q}) ===\n{context[:2000]}"
                    )
        except Exception:
            continue

    if not all_context_parts:
        return {}

    combined_context = "\n\n".join(all_context_parts)

    system_prompt = """You are generating short analyst questions for a financial research tool.

STRICT RULES — violations will be rejected:
1. Each question MUST be under 10 words
2. NO company names (not Flex, Jabil, Celestica, Benchmark, Sanmina)
3. NO specific numbers, percentages, or dates
4. Start with: Compare / Analyze / Who is / Which company / How has / What is

Respond with JSON only:
{
  "ai-infra": ["Q1?", "Q2?", "Q3?", "Q4?"],
  "capacity": ["Q1?", "Q2?", "Q3?", "Q4?"],
  "financial": ["Q1?", "Q2?", "Q3?", "Q4?"],
  "risks": ["Q1?", "Q2?", "Q3?", "Q4?"]
}

CORRECT examples (short, cross-company):
- "Who is gaining share in AI data center?"
- "Compare gross margin trends across companies"
- "Which company shows strongest revenue growth?"
- "Analyze tariff exposure by company"
- "Compare CapEx intensity across EMS peers"

WRONG examples (too long):
- "How is Flex positioned to capitalize on increasing AI demand with hyperscaler customers?"
- "Can Jabil elaborate on how AI server ramps are impacting production schedules?"

Category focus:
- ai-infra: AI data center, hyperscaler, AI server ramps
- capacity: manufacturing expansion, nearshoring, liquid cooling
- financial: revenue, margins, CapEx, backlog
- risks: tariffs, geopolitics, supply chain

Generate exactly 4 questions per category. Under 10 words each. No company names."""

    user_prompt = f"""Based on these latest EMS earnings transcript excerpts, generate analyst questions:

{combined_context[:8000]}"""

    try:
        response = llm_complete(
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
            model_key="main",
            max_tokens=1500,
        )
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip()
        return json.loads(clean)
    except Exception:
        return {}


@router.get("/chat/preset-questions")
async def get_preset_questions(force_refresh: bool = False):
    """
    Get dynamically generated preset questions from latest earnings transcripts.
    Cached for 24 hours. Use ?force_refresh=true to regenerate.
    """
    if not force_refresh:
        cache = _load_preset_questions_cache()
        if cache:
            return {
                "categories": cache.get("categories", []),
                "cached_at": cache.get("cached_at"),
                "from_cache": True,
            }

    questions_by_category = await _generate_preset_questions_from_transcripts()

    categories = []
    for cat_id, cat_def in CATEGORY_DEFINITIONS.items():
        questions = questions_by_category.get(cat_id, [])
        if not questions:
            questions = [
                f"Analyze {cat_def['label'].lower()} trends across EMS companies",
                f"Compare {cat_def['label'].lower()} positioning for Flex vs peers",
            ]
        categories.append({
            "id": cat_id,
            "label": cat_def["label"],
            "questions": questions,
        })

    result = {"categories": categories}
    _save_preset_questions_cache(result)

    return {
        "categories": categories,
        "cached_at": datetime.now().isoformat(),
        "from_cache": False,
    }
