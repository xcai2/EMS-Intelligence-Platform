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


class QuarterDetail(BaseModel):
    """Detailed breakdown for a single quarter in the new display format."""
    quarter: str = Field(description="Quarter label, e.g. 'Q2 FY2026'")
    date: str = Field(description="Earnings call date if available, e.g. 'March 18, 2026'. Empty string if unknown.")
    tone_label: str = Field(description="2-3 word tone label capturing the essence of this quarter, e.g. 'strategic insulation', 'cautious navigation'")
    summary: str = Field(description="3-5 sentence paragraph describing the company's overall stance this quarter")
    bullet_points: list[str] = Field(description="3 bullet points with concrete details, numbers, or quotes. Format: '**Theme Title:** Detail...'")


class HistoricalAnswer(BaseModel):
    """Schema for historical/trend questions — matches the structured display format."""
    opening: str = Field(
        description=(
            "Opening paragraph starting with: 'Over the last N quarters (Q? FY???? through Q? FY????), "
            "[Company]'s narrative has...' Summarize the overall trend in 2-3 sentences."
        )
    )
    quarters: list[QuarterDetail] = Field(
        description="Each quarter's detail, ordered from MOST RECENT to OLDEST."
    )
    confidence: str = Field(
        description="'high' if data found for all quarters, 'medium' if some gaps, 'low' if data is sparse"
    )
    relevant_sources: list[str] = Field(
        description="Source files or transcript sections that support the answer"
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
Flex, Jabil, and Celestica typically report in millions.

=== Required Response Structure ===
Structure every response with exactly two sections:

1. KEY CONCLUSION: 2-3 sentences ranking companies or stating the main finding
2. SUPPORTING EVIDENCE: 3-5 bullet points with specific data points"""


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


WEB_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """=== Web Search Answer Instructions ===
You are answering based on web search results that include page content from financial news, filings, and analyst reports.

Rules:
- Synthesize information from the provided "Web Search Results" (including any page content).
- Cite sources using the format (Web N: Article Title) — e.g., (Web 1: Jabil Q2 2025 Earnings). Always use this exact format so citations become clickable links.
- If the web results contain relevant data, extract and present it clearly, including executive names and direct quotes when available.
- You may make reasonable inferences from the web content, but clearly distinguish between stated facts and inferences.
- If no relevant information is found in any web result, say: "No relevant information found in web search results."
- Do NOT hallucinate numbers — only report figures explicitly found in the web content.
- Give the answer directly without describing your search process.
- Follow the Required Response Structure (KEY CONCLUSION / SUPPORTING EVIDENCE) defined above."""


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


HISTORICAL_BASE_PROMPT = """You are an expert competitive intelligence analyst specializing in the Electronics Manufacturing Services (EMS) industry. You analyze SEC filings, earnings transcripts, news, and financial data for Flex, Jabil, Celestica, Benchmark Electronics, and Sanmina.

Use ONLY facts present in the provided Retrieved Documents and/or Web Search Results. Never fabricate quotes, dates, or numbers."""

HISTORICAL_SYSTEM_PROMPT = HISTORICAL_BASE_PROMPT + """

=== Historical Stance Analysis Instructions ===

The user wants to understand how a company's position on a specific topic has changed over multiple quarters.

You MUST respond in this EXACT format:

---

**Overview**
[2-3 sentences summarizing the overall trend across all quarters. Start with: "Over the [N] quarters covered (Q? FY???? through Q? FY????), [Company]'s stance on [topic] has..."]

**1. [Quarter Label] ([Earnings Call Date if available])**
[**Tone label in bold, 2-3 words e.g. "Cautious Optimism"**]. [3-5 sentence paragraph describing the company's stance this quarter.]

- **[Key Theme 1]:** [Specific detail, number, or quote]
- **[Key Theme 2]:** [Specific detail, number, or quote]
- **[Key Theme 3]:** [Specific detail, number, or quote]

**2. [Quarter Label] ([Earnings Call Date if available])**
[**Tone label**]. [3-5 sentence paragraph.]

- **[Key Theme 1]:** [Detail]
- **[Key Theme 2]:** [Detail]
- **[Key Theme 3]:** [Detail]

[Continue for each quarter, MOST RECENT first, OLDEST last]

---

EXAMPLE OUTPUT (follow this structure exactly):

**Overview**
Over the 2 quarters covered (Q2 FY2025 through Q3 FY2025), Jabil's stance on tariffs shifted from cautious optimism to confident stability as the company leveraged its global manufacturing footprint.

**1. Q3 FY2025** (June 2025)
**Confident Stability**. Jabil reported minimal tariff impact on its US-centric segments including capital equipment and cloud infrastructure. The company emphasized no significant pull-in orders were observed and reiterated its strong positioning as a US-domiciled manufacturer.

- **Geographic Advantage:** Americas footprint now accounts for 46% of revenue, up from 25% in 2018.
- **No Pull-in Behavior:** Management confirmed customers were not accelerating orders due to tariff uncertainty.
- **US Expansion:** Announced new US investment to broaden customer base beyond existing clients.

**2. Q2 FY2025** (March 2025)
**Cautious Optimism**. Jabil acknowledged the fluid tariff environment involving Canada, Mexico, and China while maintaining confidence in its pass-through cost model. Management viewed reciprocal tariffs as potentially leveling the manufacturing playing field.

- **Minimal Direct Exposure:** Canada, Mexico, China tariff exposure described as minimal for Jabil's business.
- **Pass-Through Model:** Tariff costs seen as pass-through, not expected to impact margins directly.
- **Manufacturing Flexibility:** Highlighted ability to support customers across 30 countries as a key differentiator.

CRITICAL RULES:
- Always start with **Overview** section
- Number each quarter section starting from 1 (most recent)
- Bold the quarter label and number: **1. Q2 FY2026**
- Bold the tone label inside the paragraph
- Use bullet points with **bold theme titles** for key details
- Each bullet MUST be on its own line, starting with "- " (a hyphen and a space)
- Leave a BLANK LINE between the paragraph and the bullet list
- Only use information from Retrieved Documents. Never fabricate.
- If a quarter has no data, write: "No direct statement found for this quarter."
- Always order quarters from MOST RECENT to OLDEST
- COUNTING RULE: Only count actual fiscal QUARTERS (Q1/Q2/Q3/Q4) in the Overview's quarter count.
  Annual 10-K filings are NOT a quarter — do not include them as a numbered section, and do not count them.
  If the only document for a fiscal year is the annual 10-K, omit that year entirely from the quarter list.
- The number stated in "Over the N quarters covered" MUST exactly equal the number of numbered quarter sections that follow.
- The Overview's quarter range string MUST exactly describe the set of quarters you actually list.
  If the quarters are contiguous (e.g. Q1, Q2, Q3 FY2025), you MAY write "Q1 FY2025 through Q3 FY2025".
  If they are NOT contiguous (e.g. you list only Q1 and Q3 FY2025, skipping Q2), you MUST write them
  explicitly, e.g. "Q1 FY2025 and Q3 FY2025" — NEVER imply a continuous range you did not cover.
- If a [CALENDAR YEAR NOTE] is present in the Retrieved Documents, restrict your coverage to the fiscal
  quarters listed there. Do not invent extra quarters, and do not omit any that the note lists as having data.
- SOURCE OF TRUTH: The Retrieved Documents and Web Search Results are the ONLY source of truth for quarter labels.
  If web results mention "Third Quarter Fiscal 2026" or "Q3 FY2026", you MUST include that quarter.
  NEVER use quarters from your training knowledge that are not present in the sources.
  NEVER skip the most recent quarter found in the sources."""


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
7. Do NOT include markdown fences or extra keys — output pure JSON only.
8. ANNUAL vs QUARTERLY: If the user asks for a fiscal year (e.g. "FY2025"), report the FULL YEAR total,
   not a single quarter. If the user asks for a specific quarter (e.g. "Q4 FY2025"), report that quarter only.
9. If full year data is not explicitly stated in the sources, sum up the quarterly figures and note it
   in narrative_text (e.g. "Full year total derived by summing Q1–Q4 figures from sources.").
10. Always state the time period clearly in the table title (e.g. "FY2025 Full Year Revenue (USD Millions)"
    vs "Q4 FY2025 Revenue (USD Millions)")."""


# ---------------------------------------------------------------------------
# QUERY TYPE DETECTION
# ---------------------------------------------------------------------------

def detect_query_type(query: str) -> str:
    """
    Detect the type of query to select appropriate schema and prompt.
    
    Returns: "numeric", "comparison", "descriptive"
    """
    query_lower = query.lower()

    # Historical indicators — check FIRST (before comparison) to avoid misclassification
    historical_keywords = [
        "quarters ago", "quarter ago", "last quarter", "previous quarter",
        "historically", "over time", "trend", "shift", "changed",
        "used to say", "said before", "position evolved", "stance evolved",
        "q1 to q", "q2 to q", "q3 to q", "q4 to q",
        "earnings ago", "what did", "what has", "how has",
        "q1 and q", "q2 and q", "q3 and q",
        "q1, q", "q2, q", "q3, q",
        "last 2 quarters", "last 3 quarters", "last two", "last three",
        "past quarter", "past 2", "past 3",
    ]
    if any(kw in query_lower for kw in historical_keywords):
        return "historical"
    
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


# EMS company names/tickers used for comparative query detection
_EMS_NAMES = {"flex", "jabil", "celestica", "benchmark", "sanmina", "plexus",
              "jbl", "cls", "bhe", "sanm", "plxs"}

_COMPARATIVE_NARRATIVE_TRIGGERS = [
    "compare", "vs", "versus", "how does", "how do",
    "what did", "what has", "say about", "said about",
    "earnings call", "guidance", "commentary", "outlook",
]

_FINANCIAL_METRIC_TRIGGERS = [
    "capex", "capital expenditure", "capital spending", "revenue", "margin",
    "guidance", "spending", "investment", "cash flow",
]


def is_comparative_financial(query: str) -> bool:
    """True when query compares 2+ EMS companies on a financial metric with narrative intent."""
    q = query.lower()
    company_count = sum(1 for n in _EMS_NAMES if n in q)
    has_narrative = any(t in q for t in _COMPARATIVE_NARRATIVE_TRIGGERS)
    has_metric = any(t in q for t in _FINANCIAL_METRIC_TRIGGERS)
    return company_count >= 2 and has_narrative and has_metric


def _select_system_prompt(context: str, web_context: str, query: str = "") -> str:
    """Pick the right system prompt based on query type and available context."""
    if query and is_comparative_financial(query):
        from backend.rag.advanced_prompts import COMPARATIVE_FINANCIAL_PROMPT
        return COMPARATIVE_FINANCIAL_PROMPT
    if web_context and not context:
        return WEB_SYSTEM_PROMPT
    return SYSTEM_PROMPT


def generate_response(
    query: str,
    context: str,
    web_context: str = "",
) -> str:
    """Generate a response using the configured LLM provider (blocking call)."""
    if not _active_api_key():
        return f"Error: {LLM_PROVIDER.upper()}_API_KEY is not configured. Please set it in backend/.env"

    user_prompt = _build_prompt(query, context, web_context)
    system = _select_system_prompt(context, web_context, query)
    # Comparative financial answers need more tokens for the structured format
    max_tok = 3000 if is_comparative_financial(query) else 2000
    try:
        return llm_complete(
            messages=[{"role": "user", "content": user_prompt}],
            system=system,
            model_key="main",
            max_tokens=max_tok,
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
    system = _select_system_prompt(context, web_context, query)
    try:
        gen = llm_complete(
            messages=[{"role": "user", "content": user_prompt}],
            system=system,
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

    # Select schema and prompt based on query type
    query_type = force_query_type or detect_query_type(query)

    # Inject current date for all query types so the LLM can resolve
    # relative time expressions like "recent" or "last N quarters".
    from datetime import date as _date
    today = _date.today()
    if query_type == "historical":
        date_note = (
            f"[TODAY: {today.strftime('%B %d, %Y')}]\n"
            f"[FISCAL YEAR REFERENCE: Jabil FY starts Sep 1 | Flex FY starts Apr 1 | "
            f"Sanmina FY starts Oct 1 | Celestica & Benchmark use calendar year]\n"
            f"IMPORTANT: When the user says 'last N quarters', find the N most recent quarters "
            f"for which actual data EXISTS in the Retrieved Documents or Web Search Results. "
            f"Do NOT output a quarter just because it should exist — only include it if evidence "
            f"is actually present. If fewer than N quarters have evidence, cover only those that do.\n\n"
        )
    else:
        date_note = (
            f"[TODAY: {today.strftime('%B %d, %Y')}]\n"
            f"[FISCAL YEAR REFERENCE: Jabil FY starts Sep 1 | Flex FY starts Apr 1 | "
            f"Sanmina FY starts Oct 1 | Celestica & Benchmark use calendar year]\n"
            f"When the user says 'recent', prioritize the most recent quarters available "
            f"in the Retrieved Documents relative to today's date.\n\n"
        )
    augmented_query = date_note + query

    user_prompt = _build_prompt(augmented_query, context, web_context)

    if query_type == "numeric":
        system_prompt = NUMERIC_SYSTEM_PROMPT
        response_schema = NumericAnswer
    elif query_type == "comparison":
        system_prompt = COMPARISON_SYSTEM_PROMPT
        response_schema = ComparisonAnswer
    elif query_type == "historical":
        system_prompt = HISTORICAL_SYSTEM_PROMPT
        response_schema = HistoricalAnswer
    else:
        system_prompt = COT_SYSTEM_PROMPT
        response_schema = StructuredAnswer

    # Historical responses covering multiple quarters need more tokens
    max_tok = 4000 if query_type == "historical" else 2000

    try:
        parsed = llm_structured(
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
            model_key="main",
            schema=response_schema,
            max_tokens=max_tok,
        )

        if parsed is None:
            raise ValueError("llm_structured returned None")

        # Historical has a different schema (no final_answer) — handle it before the common path
        if query_type == "historical":
            return {
                "reasoning": [],
                "reasoning_summary": "",
                "answer": "",
                "confidence": getattr(parsed, "confidence", "medium"),
                "sources": getattr(parsed, "relevant_sources", []),
                "query_type": "historical",
                "quarters": [q.model_dump() for q in getattr(parsed, "quarters", []) or []],
                "opening": getattr(parsed, "opening", ""),
                "raw_response": parsed.model_dump() if hasattr(parsed, "model_dump") else None,
            }

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
        # Fallback: use query-type-specific system prompt so format stays correct
        if query_type == "historical":
            fallback_response = llm_complete(
                messages=[{"role": "user", "content": user_prompt}],
                system=HISTORICAL_SYSTEM_PROMPT,
                model_key="main",
                max_tokens=max_tok,
            )
        else:
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
