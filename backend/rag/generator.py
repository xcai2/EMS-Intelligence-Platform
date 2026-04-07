"""
LLM generation module for RAG pipeline.
Enhanced with Structured Output + Chain of Thought (RAG-Challenge-2 style).

Features:
1. Pydantic schemas for structured responses
2. Chain of Thought reasoning before final answer
3. Query-type specific prompts (numeric, comparison, descriptive)
4. Source page tracking for verification
"""
import json
import re
from typing import Optional
from pydantic import BaseModel, Field

from backend.core.config import LLM_PROVIDER, OPENAI_API_KEY, ANTHROPIC_API_KEY
from backend.core.llm_client import llm_complete, llm_structured


# ---------------------------------------------------------------------------
# STRUCTURED OUTPUT SCHEMAS (RAG-Challenge-2 Style)
# ---------------------------------------------------------------------------

class ReasoningStep(BaseModel):
    """A single step in the chain of thought reasoning."""
    step: str = Field(description="Description of this reasoning step")
    finding: str = Field(description="What was found/concluded in this step")


class StructuredAnswer(BaseModel):
    """
    Structured response with Chain of Thought reasoning.
    Forces the model to think step-by-step before answering.
    """
    step_by_step_analysis: list[ReasoningStep] = Field(
        description="Chain of thought reasoning steps. Analyze the context systematically."
    )
    reasoning_summary: str = Field(
        description="Brief summary of the reasoning (1-2 sentences)"
    )
    final_answer: str = Field(
        description="The concise final answer to the question"
    )
    confidence: str = Field(
        description="Confidence level: 'high' (exact data found), 'medium' (inferred), 'low' (uncertain)"
    )
    relevant_sources: list[str] = Field(
        description="List of source files/sections that support the answer"
    )


class NumericAnswer(BaseModel):
    """Schema for questions expecting numeric answers (CapEx, revenue, etc.)."""
    step_by_step_analysis: list[ReasoningStep] = Field(
        description="Steps to extract and validate the numeric value"
    )
    raw_value_found: str = Field(
        description="The exact value as it appears in the source (e.g., '$(505)', '1,234')"
    )
    unit_in_source: str = Field(
        description="Unit from source header: 'thousands', 'millions', 'billions'"
    )
    normalized_value: float = Field(
        description="The value normalized to millions (e.g., 505.0)"
    )
    fiscal_period: str = Field(
        description="The fiscal period (e.g., 'FY24 Q2', 'Fiscal Year 2024')"
    )
    final_answer: str = Field(
        description="Human-readable answer with value, unit, and period"
    )
    confidence: str = Field(
        description="'high' if exact value found, 'medium' if calculated, 'low' if estimated"
    )
    source_section: str = Field(
        description="Section where value was found (e.g., 'Cash Flow Statement')"
    )


class ComparisonAnswer(BaseModel):
    """Schema for comparison questions (Company A vs Company B)."""
    step_by_step_analysis: list[ReasoningStep] = Field(
        description="Steps comparing each company's data"
    )
    company_data: dict = Field(
        description="Dict mapping company name to its value (e.g., {'Flex': 505, 'Jabil': 430})"
    )
    comparison_result: str = Field(
        description="Which company has higher/lower value or how they compare"
    )
    final_answer: str = Field(
        description="Concise comparison answer"
    )
    confidence: str = Field(
        description="Confidence level"
    )


class TablePayloadSchema(BaseModel):
    """Structured table data for frontend rendering."""
    title: str = Field(description="Short table title including units, e.g. 'Annual CapEx (USD Millions)'")
    columns: list[str] = Field(description="Column headers; first column is typically the entity/company name")
    rows: list[list[str]] = Field(
        description="Table rows. Each row is a list of strings matching columns length. Use 'N/A' for missing data."
    )


class TableOutput(BaseModel):
    """Structured output for table-intent queries."""
    narrative_text: str = Field(
        description="One sentence introducing the table (do not repeat the title). Empty string if none needed."
    )
    table_payload: TablePayloadSchema


# ---------------------------------------------------------------------------
# SYSTEM PROMPTS (Query-Type Specific)
# ---------------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """You are an expert competitive intelligence analyst specializing in the Electronics Manufacturing Services (EMS) industry. You analyze SEC filings, earnings transcripts, and financial data for Flex, Jabil, Celestica, Benchmark Electronics, and Sanmina.

=== CapEx / Capital Expenditure Extraction Rules ===

LABELS — Different companies use different labels for the same line item:
  * "Purchases of property and equipment" (Flex)
  * "Acquisition of property, plant and equipment" (Jabil)
  * "Purchase of property, plant and equipment" (Celestica)
  * "Purchases of property, plant and equipment" (Benchmark)
  * "Capital expenditures" (Sanmina)
  * "Additions to property and equipment"
  * "Capital spending"
  * "Payments for property and equipment"
All of these refer to CapEx. Look for any of them in the context.

YTD vs SINGLE-QUARTER (CRITICAL for 10-Q):
Quarterly reports (10-Q) show TWO sets of columns:
  "Three Months Ended ..."   → SINGLE quarter   ← EXTRACT THIS ONE
  "Six Months Ended ..."     → Year-to-date     ← DO NOT USE
  "Nine Months Ended ..."    → Year-to-date     ← DO NOT USE
Always extract the "Three Months Ended" value (the single-quarter figure).

NEGATIVE NUMBERS:
CapEx appears as negative in cash flow statements because it is a cash outflow.
Values like $(505), (505), -505, or −130 are all positive CapEx amounts.
Always report the absolute value.

UNIT HEADERS:
Check the unit header at the top of financial statements:
  * "(in thousands)" → divide by 1,000 to get millions
  * "(in millions)" → values are already in millions
  * "(in billions)" → values are already in billions
Benchmark and Sanmina typically report in thousands.
Flex, Jabil, and Celestica typically report in millions."""


COT_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """

=== Answer Instructions ===

Answer directly and concisely based on the provided context. Do NOT explain your methodology or analysis process.

Rules:
- Use ONLY facts present in "Retrieved Documents" and/or "Web Search Results".
- Never use outside knowledge or assumptions to fill missing facts.
- Give the answer immediately without describing steps you will take
- Use bullet points or tables for multi-company comparisons
- If data is not found in the context, say exactly: "Not found in provided sources."
- Do NOT hallucinate or make up numbers
- Do NOT show your reasoning process"""


NUMERIC_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """

=== Numeric Extraction Instructions ===

You are extracting a specific numeric value. Follow these steps precisely:

1. LOCATE: Find the exact line item in the context that matches the question
2. VERIFY PERIOD: Ensure the value is for the correct fiscal period
3. CHECK UNITS: Note the unit header (thousands/millions/billions)
4. EXTRACT RAW: Copy the exact value as it appears (including parentheses/signs)
5. NORMALIZE: Convert to millions for consistency
6. VALIDATE: Cross-check if multiple sources exist

If the value cannot be found with certainty, set confidence to 'low' and explain why."""


COMPARISON_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """

=== Comparison Instructions (RAG-Challenge-2 Style) ===

For comparison questions, you MUST follow a structured plan before answering:

STEP 1 - PLAN (do this first):
   - Identify: Which companies are being compared?
   - Identify: What metric(s) need to be found?
   - Identify: What time period(s) are relevant?
   - Identify: Which sections should contain this data? (e.g., Cash Flow Statement for CapEx)

STEP 2 - EXTRACT (for EACH company):
   - Find the relevant metric in the context
   - Note the exact value as it appears
   - Note the fiscal period (FY/quarter)
   - Note the units (thousands/millions)
   - Normalize to millions for comparison

STEP 3 - VALIDATE:
   - Same metric definition? (CapEx = PP&E purchases = capital expenditures)
   - Comparable time periods? (FY24 vs FY24, not FY24 vs FY23)
   - Same reporting basis? (GAAP vs non-GAAP)
   - If periods don't match exactly, note this caveat

STEP 4 - COMPARE:
   - State each company's value clearly
   - Rank from highest to lowest
   - Calculate differences/percentages if meaningful
   - Note any limitations or missing data

CRITICAL - HANDLING MISSING DATA:
   - If data for a company is NOT found in the context, you MUST explicitly state:
     "Data for [Company] was not found in the provided documents."
   - Do NOT guess or interpolate missing values
   - Do NOT ignore missing companies - address each one mentioned
   - If some companies have data and others don't, compare those that have data and note the gaps"""


# Legacy prompt for backward compatibility
SYSTEM_PROMPT = COT_SYSTEM_PROMPT


TABLE_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """

=== Table Output Instructions ===

You MUST respond with a JSON object matching this exact schema:
{
  "narrative_text": "<one intro sentence or empty string>",
  "table_payload": {
    "title": "<short descriptive title with units>",
    "columns": ["<col1>", "<col2>", ...],
    "rows": [["<val1>", "<val2>", ...], ...]
  }
}

STRICT RULES:
1. All cell values must be strings. Numbers: "468", "1,030" (use comma separators for thousands).
2. If the title says USD Millions, do NOT add "$" or "M" inside cells — just the number string.
3. Missing data: use exactly "N/A" — never "unknown", "not available", "not found", "missing".
4. Footnotes like "145*" are allowed as cell strings.
5. ONLY use data verified from the Retrieved Documents / Web Results. Never fabricate numbers.
6. If almost all cells would be N/A, set table_payload rows to [] and explain in narrative_text.
7. Do NOT include markdown fences or extra keys — output pure JSON only."""


# ---------------------------------------------------------------------------
# QUERY TYPE DETECTION
# ---------------------------------------------------------------------------

def detect_query_type(query: str) -> str:
    """
    Detect the type of query to select appropriate schema and prompt.
    
    Returns: "numeric", "comparison", "descriptive"
    """
    query_lower = query.lower()
    
    # Comparison indicators
    comparison_keywords = [
        "compare", "versus", "vs", "vs.", "differ", "between",
        "which company", "who has higher", "who has more", "who has lower",
        "rank", "ranking", "across companies", "both", "all companies"
    ]
    if any(kw in query_lower for kw in comparison_keywords):
        return "comparison"
    
    # Numeric indicators
    numeric_keywords = [
        "how much", "what is the", "what was the", "what are the",
        "capex", "capital expenditure", "revenue", "profit", "margin",
        "value", "amount", "total", "number of", "how many",
        "million", "billion", "thousand", "percent", "%"
    ]
    if any(kw in query_lower for kw in numeric_keywords):
        return "numeric"
    
    # Default to descriptive
    return "descriptive"


def _build_prompt(query: str, context: str, web_context: str = "") -> str:
    """Build the user prompt combining query, RAG context, and optional web results."""
    parts = []
    if context:
        parts.append(f"## Retrieved Documents\n{context}")
    if web_context:
        parts.append(f"## Web Search Results\n{web_context}")
    parts.append(f"## Question\n{query}")
    return "\n\n".join(parts)


def _active_api_key() -> str:
    return ANTHROPIC_API_KEY if LLM_PROVIDER == "anthropic" else OPENAI_API_KEY


def generate_response(
    query: str,
    context: str,
    web_context: str = "",
) -> str:
    """Generate a response using the configured LLM provider (blocking call)."""
    if not _active_api_key():
        return f"Error: {LLM_PROVIDER.upper()}_API_KEY is not configured. Please set it in backend/.env"

    user_prompt = _build_prompt(query, context, web_context)
    try:
        return llm_complete(
            messages=[{"role": "user", "content": user_prompt}],
            system=SYSTEM_PROMPT,
            model_key="main",
            max_tokens=2000,
        )
    except Exception as e:
        return f"Error generating response: {e}"


def generate_response_streaming(
    query: str,
    context: str,
    web_context: str = "",
):
    """Generate a streaming response using the configured LLM provider."""
    if not _active_api_key():
        yield f"Error: {LLM_PROVIDER.upper()}_API_KEY is not configured. Please set it in backend/.env"
        return

    user_prompt = _build_prompt(query, context, web_context)
    try:
        gen = llm_complete(
            messages=[{"role": "user", "content": user_prompt}],
            system=SYSTEM_PROMPT,
            model_key="main",
            max_tokens=2000,
            stream=True,
        )
        yield from gen
    except Exception as e:
        yield f"\n\nError during streaming: {e}"


def generate_summary(text: str) -> str:
    """Generate a brief summary of the given text."""
    if not _active_api_key():
        return text[:500] + "..."

    try:
        return llm_complete(
            messages=[{"role": "user", "content": text[:8000]}],
            system="Summarize the following financial/business text in 2-3 concise sentences.",
            model_key="main",
            max_tokens=300,
        )
    except Exception:
        return text[:500] + "..."


# ---------------------------------------------------------------------------
# STRUCTURED OUTPUT GENERATION (RAG-Challenge-2 Style)
# ---------------------------------------------------------------------------

def generate_structured_response(
    query: str,
    context: str,
    web_context: str = "",
    force_query_type: Optional[str] = None,
) -> dict:
    """
    Generate a response using Chain of Thought with structured output.
    
    This forces the model to reason step-by-step before providing the final answer,
    which significantly improves accuracy on complex questions.
    
    Args:
        query: The user question
        context: Retrieved document context
        web_context: Optional web search context
        force_query_type: Override auto-detected query type ("numeric", "comparison", "descriptive")
    
    Returns:
        Dict containing:
        - reasoning: The chain of thought steps
        - answer: The final answer
        - confidence: Confidence level
        - sources: Relevant source information
        - raw_response: Full structured response object
    """
    if not _active_api_key():
        return {
            "reasoning": [],
            "answer": f"Error: {LLM_PROVIDER.upper()}_API_KEY is not configured",
            "confidence": "low",
            "sources": [],
            "raw_response": None,
        }

    user_prompt = _build_prompt(query, context, web_context)

    # Select schema and prompt based on query type
    query_type = force_query_type or detect_query_type(query)

    if query_type == "numeric":
        system_prompt = NUMERIC_SYSTEM_PROMPT
        response_schema = NumericAnswer
    elif query_type == "comparison":
        system_prompt = COMPARISON_SYSTEM_PROMPT
        response_schema = ComparisonAnswer
    else:
        system_prompt = COT_SYSTEM_PROMPT
        response_schema = StructuredAnswer

    try:
        parsed = llm_structured(
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
            model_key="main",
            schema=response_schema,
            max_tokens=2000,
        )

        if parsed is None:
            raise ValueError("llm_structured returned None")

        # Extract common fields
        reasoning_steps = []
        if hasattr(parsed, 'step_by_step_analysis'):
            reasoning_steps = [
                {"step": step.step, "finding": step.finding}
                for step in parsed.step_by_step_analysis
            ]
        
        result = {
            "reasoning": reasoning_steps,
            "reasoning_summary": getattr(parsed, 'reasoning_summary', ''),
            "answer": parsed.final_answer,
            "confidence": getattr(parsed, 'confidence', 'medium'),
            "sources": getattr(parsed, 'relevant_sources', []) or getattr(parsed, 'source_section', ''),
            "query_type": query_type,
            "raw_response": parsed.model_dump() if hasattr(parsed, 'model_dump') else None,
        }
        
        # Add numeric-specific fields
        if query_type == "numeric" and hasattr(parsed, 'normalized_value'):
            result["numeric_value"] = parsed.normalized_value
            result["fiscal_period"] = parsed.fiscal_period
            result["unit"] = parsed.unit_in_source
            result["raw_value"] = parsed.raw_value_found
        
        # Add comparison-specific fields
        if query_type == "comparison" and hasattr(parsed, 'company_data'):
            result["company_data"] = parsed.company_data
            result["comparison_result"] = parsed.comparison_result
        
        return result
        
    except Exception as e:
        # Fallback to regular generation if structured output fails
        fallback_response = generate_response(query, context, web_context)
        return {
            "reasoning": [],
            "answer": fallback_response,
            "confidence": "medium",
            "sources": [],
            "query_type": query_type,
            "error": str(e),
            "raw_response": None,
        }


def generate_with_cot(
    query: str,
    context: str,
    web_context: str = "",
) -> str:
    """
    Generate response with Chain of Thought, returning formatted text.
    
    This is a convenience wrapper that uses structured output internally
    but returns a nicely formatted text response.
    """
    result = generate_structured_response(query, context, web_context)
    
    # Format the response with reasoning visible (optional)
    parts = []
    
    # Optionally show reasoning (can be controlled via config)
    # For now, just return the answer
    if result.get("confidence") == "low":
        parts.append(f"**Note:** Confidence is low. {result.get('reasoning_summary', '')}\n")
    
    parts.append(result["answer"])
    
    return "\n".join(parts)


def format_structured_response_for_display(result: dict, show_reasoning: bool = False) -> str:
    """
    Format a structured response for user display.
    
    Args:
        result: The result from generate_structured_response
        show_reasoning: Whether to include the reasoning steps
    
    Returns:
        Formatted markdown string
    """
    parts = []
    
    if show_reasoning and result.get("reasoning"):
        parts.append("### Reasoning Steps\n")
        for i, step in enumerate(result["reasoning"], 1):
            parts.append(f"{i}. **{step['step']}**")
            parts.append(f"   → {step['finding']}\n")
        parts.append("---\n")
    
    # Main answer
    parts.append("### Answer\n")
    parts.append(result["answer"])
    
    # Confidence indicator
    confidence = result.get("confidence", "medium")
    confidence_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "⚪")
    parts.append(f"\n\n*Confidence: {confidence_emoji} {confidence}*")
    
    # Numeric details
    if result.get("numeric_value") is not None:
        parts.append(f"\n*Value: {result['numeric_value']} million ({result.get('fiscal_period', 'N/A')})*")
    
    # Sources
    sources = result.get("sources", [])
    if sources:
        if isinstance(sources, list):
            parts.append(f"\n*Sources: {', '.join(sources)}*")
        else:
            parts.append(f"\n*Source: {sources}*")
    
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# ADVANCED PROMPTS INTEGRATION (RAG-Challenge-2 Style)
# ---------------------------------------------------------------------------

def generate_with_typed_prompt(
    query: str,
    context: str,
    answer_type: str = None,
) -> dict:
    """
    Generate answer using type-specific prompt from advanced_prompts module.
    
    This wraps the advanced_prompts functionality for easy use.
    
    Args:
        query: The question
        context: Retrieved document context
        answer_type: Override type (name/number/boolean/names_list)
    
    Returns:
        Structured answer dict
    """
    from backend.rag.advanced_prompts import generate_typed_answer, detect_answer_type
    
    if answer_type is None:
        answer_type = detect_answer_type(query)
    
    return generate_typed_answer(query, context, answer_type)


def generate_comparison_answer(
    query: str,
    companies: list[str],
    retriever_func,
) -> dict:
    """
    Full comparison pipeline with query rephrasing.

    1. Splits comparison question into per-company sub-questions
    2. Retrieves and answers each sub-question
    3. Merges answers into comparative response

    Args:
        query: Original comparison question
        companies: List of companies to compare
        retriever_func: Function(query, company) -> context string

    Returns:
        Complete comparison result
    """
    from backend.rag.advanced_prompts import answer_comparison_query

    return answer_comparison_query(query, companies, retriever_func)


def generate_table_response(query: str, context: str, web_context: str = "") -> "dict | None":
    """
    Generate a structured table response using llm_structured.

    Returns a dict with keys: narrative_text, table_payload (title, columns, rows).
    Returns None if structured output fails — caller should fall back to generate_response().
    """
    if not _active_api_key():
        return None

    user_prompt = _build_prompt(query, context, web_context)
    try:
        parsed: TableOutput = llm_structured(
            messages=[{"role": "user", "content": user_prompt}],
            system=TABLE_SYSTEM_PROMPT,
            model_key="main",
            schema=TableOutput,
            max_tokens=2000,
        )
        if parsed is None:
            return None
        return {
            "narrative_text": parsed.narrative_text,
            "table_payload": {
                "title": parsed.table_payload.title,
                "columns": parsed.table_payload.columns,
                "rows": parsed.table_payload.rows,
            },
        }
    except Exception:
        return None
