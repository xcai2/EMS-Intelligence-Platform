"""
Advanced Prompts Module - RAG-Challenge-2 Style

Features:
1. Query Rephrasing - Split comparison questions into per-company sub-questions
2. Answer Type Detection - Name/Number/Boolean/Names list
3. Type-Specific Prompts - Optimized prompts for each answer type
4. Comparative Answer Merging - Combine sub-answers into final comparison
"""

import re
import json
from typing import Optional, Literal, Union
from pydantic import BaseModel, Field

from backend.core.config import LLM_PROVIDER, OPENAI_API_KEY, ANTHROPIC_API_KEY
from backend.core.llm_client import llm_structured


# ---------------------------------------------------------------------------
# PYDANTIC SCHEMAS FOR STRUCTURED OUTPUT
# ---------------------------------------------------------------------------

class RephrasedQuestion(BaseModel):
    """Individual question for a company."""
    company_name: str = Field(description="Company name, exactly as provided in the original question")
    question: str = Field(description="Rephrased question specific to this company")


class RephrasedQuestions(BaseModel):
    """List of rephrased questions for comparison queries."""
    questions: list[RephrasedQuestion] = Field(description="List of rephrased questions for each company")


class NameAnswer(BaseModel):
    """Schema for questions expecting a name (person, company, product)."""
    step_by_step_analysis: str = Field(
        description="Detailed analysis with at least 5 steps. Identify the entity type asked for, search context systematically."
    )
    reasoning_summary: str = Field(description="Concise summary of reasoning (50 words)")
    relevant_pages: list[int] = Field(description="Pages with direct answers")
    final_answer: Union[str, Literal["N/A"]] = Field(
        description="Exact name as it appears in context, or 'N/A' if not found"
    )


class NumberAnswer(BaseModel):
    """Schema for questions expecting a numeric answer."""
    step_by_step_analysis: str = Field(
        description="""Detailed analysis:
1. Identify the exact metric requested
2. Find matching metric in context (beware of similar but different metrics)
3. Check units (thousands/millions/billions)
4. Handle negative values (parentheses = negative)
5. Normalize to requested unit"""
    )
    reasoning_summary: str = Field(description="Concise summary (50 words)")
    raw_value_found: str = Field(description="Exact value as it appears in source")
    unit_in_source: str = Field(description="Unit from source: thousands/millions/billions")
    relevant_pages: list[int] = Field(description="Pages with direct answers")
    final_answer: Union[float, int, Literal["N/A"]] = Field(
        description="Normalized numeric value, or 'N/A' if not directly stated (no calculations)"
    )


class BooleanAnswer(BaseModel):
    """Schema for yes/no questions."""
    step_by_step_analysis: str = Field(
        description="Detailed analysis. Pay attention to exact wording - 'did X happen' vs 'was X mentioned'"
    )
    reasoning_summary: str = Field(description="Concise summary (50 words)")
    relevant_pages: list[int] = Field(description="Pages with direct answers")
    final_answer: bool = Field(description="True or False based on context evidence")


class NamesListAnswer(BaseModel):
    """Schema for questions expecting multiple names."""
    step_by_step_analysis: str = Field(
        description="Detailed analysis identifying all relevant entities"
    )
    reasoning_summary: str = Field(description="Concise summary (50 words)")
    relevant_pages: list[int] = Field(description="Pages with direct answers")
    final_answer: Union[list[str], Literal["N/A"]] = Field(
        description="List of names exactly as they appear in context, or 'N/A'"
    )


class ComparativeAnswer(BaseModel):
    """Schema for merged comparison answers."""
    step_by_step_analysis: str = Field(
        description="Analysis comparing each company's data systematically"
    )
    reasoning_summary: str = Field(description="Concise summary (50 words)")
    company_values: dict = Field(
        description="Dict mapping company to its value: {'Flex': 505, 'Jabil': 430}"
    )
    comparison_result: str = Field(
        description="Which company has higher/lower value, or comparison summary"
    )
    final_answer: Union[str, Literal["N/A"]] = Field(
        description="Company name that answers the question, or 'N/A'"
    )


# ---------------------------------------------------------------------------
# SYSTEM PROMPTS
# ---------------------------------------------------------------------------

QUERY_REPHRASE_SYSTEM = """You are a question rephrasing system for financial document analysis.

Your task is to break down a comparative question into individual questions for each company mentioned.

Rules:
1. Each output question must be self-contained
2. Maintain the same intent and metric as the original question
3. Be specific to each company
4. Use consistent phrasing across all questions
5. Extract company names exactly as they appear (with quotes if present)

Example:
Input: "Which company had higher CapEx in FY24, Flex or Jabil?"
Output:
{
  "questions": [
    {"company_name": "Flex", "question": "What was Flex's CapEx in FY24?"},
    {"company_name": "Jabil", "question": "What was Jabil's CapEx in FY24?"}
  ]
}"""


NAME_ANSWER_SYSTEM = """You are a RAG answering system for financial documents.
Answer based ONLY on the provided context. Think step-by-step before answering.

For NAME questions (person, company, product):
1. Identify exactly what entity type is being asked for
2. Search context systematically for mentions
3. Extract the name EXACTLY as it appears
4. If multiple names match, take the most relevant one
5. Return 'N/A' if not found - do NOT guess

Important:
- CEO = Chief Executive Officer = President (sometimes)
- Full names preferred over partial names
- Company names should match official filings"""


NUMBER_ANSWER_SYSTEM = """You are a RAG answering system for financial documents.
Answer based ONLY on the provided context. Think step-by-step before answering.

For NUMERIC questions:
1. **Strict Metric Matching**: The context metric must EXACTLY match what's asked
   - "Total assets" ≠ "Net assets"
   - "Revenue" ≠ "Net revenue"
   - "CapEx" = "Purchases of PP&E" = "Capital expenditures" (these ARE equivalent)

2. **Unit Handling**:
   - Check header: "(in thousands)" → multiply by 1,000
   - Check header: "(in millions)" → already in millions
   - Benchmark/Sanmina often use thousands; Flex/Jabil use millions

3. **Negative Values**:
   - (505) = -505 = negative 505
   - Cash outflows (like CapEx) are shown as negative in cash flow statements
   - Report POSITIVE value for CapEx unless specifically asked for sign

4. **Period Matching**:
   - "Three Months Ended" = single quarter
   - "Six/Nine Months Ended" = YTD (don't use unless asked)
   - Match the fiscal year/quarter exactly

5. **Return 'N/A' if**:
   - Metric is not directly stated (even if calculable)
   - Currency doesn't match
   - Period doesn't match"""


BOOLEAN_ANSWER_SYSTEM = """You are a RAG answering system for financial documents.
Answer based ONLY on the provided context. Think step-by-step before answering.

For BOOLEAN (yes/no) questions:
1. Identify exactly what is being asked
2. Look for explicit statements in context
3. "Did X change?" means: was there an announced modification to X
4. "Did X increase?" means: is there evidence of growth

Important distinctions:
- "Changes to dividend policy" ≠ "Changes to dividend amount"
- "Announced" = formally stated in filing
- If context shows the opposite happened, answer False
- If no information found, consider the implication carefully"""


NAMES_LIST_SYSTEM = """You are a RAG answering system for financial documents.
Answer based ONLY on the provided context. Think step-by-step before answering.

For NAMES LIST questions:
1. Identify all entities matching the criteria
2. Extract EACH name exactly as it appears
3. For position changes: return position TITLES only (singular form)
4. For person names: return FULL names
5. For products: return product names as stated

Important:
- New appointments count as "position changes"
- If same position changed multiple times, list it once
- Order doesn't matter"""


COMPARATIVE_FINANCIAL_PROMPT = """You are a senior equity research analyst covering the EMS (Electronics Manufacturing Services) sector. Your answers look like research notes: structured, evidence-grounded, and directly useful to an investment professional.

The user's prompt will include a "## Financial Cache Data" section with authoritative yfinance figures (capex, revenue) per company and quarter. Treat these as ground truth for numeric values — they take precedence over numbers you might infer from prose descriptions in SEC filings.

=== When to use this format ===
Use this format when the user asks you to compare TWO OR MORE companies on a financial metric (CapEx, revenue, margins, guidance, etc.) AND the query asks for management language, guidance narrative, or earnings commentary — not just a bare number.

=== Output format — follow EXACTLY ===

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[METRIC] COMPARISON · [COMPANY A] vs [COMPANY B]

**[COMPANY A] ([TICKER]) — [PERIOD] GUIDANCE / ACTUALS**
• Full-year [metric]: [value or "Not stated in sources"]
• As % of revenue: [annual guidance % stated by management, or quarterly % from Financial Cache, or "Not calculable"]
  _(label as "(annual guidance)" or "(quarterly, [period])")_
• Latest quarter ([label]): [value or "Not stated in sources"]
• Management commentary: "[verbatim quote]" ([source: filing type, date])
  — If no qualifying quote found: "No recent forward-looking capex commentary found in available filings"
• Stated purpose: [1-2 sentence context from filing/transcript]

**[COMPANY B] ([TICKER]) — [PERIOD] GUIDANCE / ACTUALS**
• Full-year [metric]: [value or "Not stated in sources"]
• As % of revenue: [annual guidance % stated by management, or quarterly % from Financial Cache, or "Not calculable"]
  _(label as "(annual guidance)" or "(quarterly, [period])")_
• Latest quarter ([label]): [value or "Not stated in sources"]
• Management commentary: "[verbatim quote]" ([source: filing type, date])
  — If no qualifying quote found: "No recent forward-looking capex commentary found in available filings"
• Stated purpose: [1-2 sentence context from filing/transcript]

**KEY TAKEAWAY**
[One sentence synthesizing the most important difference or similarity between the companies on this metric. Be specific: name the numbers, name the companies, state the implication.]

**SOURCES**
[1] [Company] · [Filing type] · [Date or fiscal period]
[2] [Company] · [Filing type] · [Date or fiscal period]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

=== Strict rules ===

NEVER INVENT NUMBERS. If a value is not present in the Retrieved Documents or Financial Cache Data, write exactly "Not stated in sources" — do not estimate or interpolate.

RECENCY RULE: When selecting 'latest quarter' data, you MUST use the most recent period available across ALL sources (Financial Cache Data, SEC filings, earnings transcripts). Sort all data points by period_end_date descending and use the first result. If the "## Financial Cache Data" section contains a period more recent than any SEC filing in context, ALWAYS use the financial_cache figure for that quarter. NEVER cite a quarter older than 6 months when a newer data point exists.

% OF REVENUE — MANDATORY RULE:
  Step 1: Does management explicitly state a % in their commentary (e.g. "approximately 6% of our latest annual revenue outlook")? If YES → use that value verbatim, label "(annual guidance)". Do NOT divide $1B by last year's revenue.
  Step 2: Does the Financial Cache Data section contain a line like "CapEx % of Revenue [period] (quarterly): X%"? If YES → copy that value, label "(quarterly, [period])". This ALWAYS takes priority over writing "Not calculable".
  Step 3: Only write "Not calculable from sources" if NEITHER step 1 nor step 2 applies.

QUOTE QUALITY: When selecting management commentary, you MUST prefer quotes that satisfy ALL THREE criteria:
  1. From a period within the last 12 months of the most recent data point in sources
  2. Contains at least one of: a specific dollar amount, a percentage, a fiscal year reference, or forward-looking language ("will", "expect", "anticipate", "target", "plan to", "guidance")
  3. Between 15 and 50 words in length
If no quote satisfying all three criteria exists in the Retrieved Documents, write exactly: "No recent forward-looking capex commentary found in available filings" — do NOT substitute an older, vaguer, or off-topic quote.

VERBATIM QUOTES: Copy exact words from the document. Use quotation marks. Include the source document type and date immediately after the closing quote. If you cannot find an exact qualifying quote, use the fallback phrase above.

PERIOD LABELS: Use the exact fiscal period label from the documents (e.g., "FY2026 Q1 ending March 2026"), not a guess.

SOURCES SECTION: List every document you drew from. Format: "[Company] · [10-K / 10-Q / 8-K / Earnings Transcript / Financial Cache] · [Date or fiscal period]"

ANSWER SCOPE: Only answer about the companies and metric the user asked about. Do not add commentary about companies not mentioned in the query."""


COMPARATIVE_MERGE_SYSTEM = """You are a comparison analysis system.
Your task is to analyze individual company answers and provide a comparative response.

Rules:
1. Base analysis ONLY on provided individual answers
2. Do NOT make assumptions or add external knowledge
3. When comparing metrics:
   - Same currency required (exclude mismatched currencies)
   - Same period required
4. If company has 'N/A', exclude from comparison
5. If all companies excluded, return 'N/A'
6. If only one company remains, return its name
7. Return company name exactly as in original question"""


# ---------------------------------------------------------------------------
# ANSWER TYPE DETECTION
# ---------------------------------------------------------------------------

def detect_answer_type(query: str) -> str:
    """
    Detect the expected answer type from the question.
    
    Returns: "name", "number", "boolean", "names_list", "comparison"
    """
    query_lower = query.lower()
    
    # Comparison (multi-company)
    comparison_triggers = [
        "which company", "who had higher", "who had lower", "compare",
        "versus", "vs", "which of the companies",
    ]
    if any(t in query_lower for t in comparison_triggers):
        return "comparison"
    
    # Boolean
    boolean_triggers = [
        "did ", "does ", "is there", "was there", "has ", "have ",
        "are there", "were there", "is it true",
    ]
    if any(t in query_lower for t in boolean_triggers):
        # Check if it's really boolean or just phrasing
        if "how much" not in query_lower and "what was" not in query_lower:
            return "boolean"
    
    # Names list
    list_triggers = [
        "what are the names", "list all", "list the", "who are the",
        "what were the names", "name all",
    ]
    if any(t in query_lower for t in list_triggers):
        return "names_list"
    
    # Number
    number_triggers = [
        "how much", "what was the", "what is the", "total", "amount",
        "value", "revenue", "profit", "capex", "capital expenditure",
        "million", "billion", "percent", "%", "ratio", "margin",
    ]
    if any(t in query_lower for t in number_triggers):
        return "number"
    
    # Default to name (who, what specific entity)
    return "name"


# ---------------------------------------------------------------------------
# QUERY REPHRASING
# ---------------------------------------------------------------------------

def rephrase_comparison_query(
    query: str,
    companies: list[str],
) -> list[dict]:
    """
    Split a comparison question into per-company sub-questions.
    
    Example:
        "Which company had higher CapEx, Flex or Jabil?"
        →
        [
            {"company_name": "Flex", "question": "What was Flex's CapEx?"},
            {"company_name": "Jabil", "question": "What was Jabil's CapEx?"},
        ]
    """
    active_key = ANTHROPIC_API_KEY if LLM_PROVIDER == "anthropic" else OPENAI_API_KEY
    if not active_key:
        return _rephrase_simple(query, companies)

    user_prompt = f"""Original comparative question: '{query}'
Companies mentioned: {', '.join(f'"{c}"' for c in companies)}"""

    try:
        result = llm_structured(
            messages=[{"role": "user", "content": user_prompt}],
            system=QUERY_REPHRASE_SYSTEM,
            model_key="fast",
            schema=RephrasedQuestions,
        )
        if result is None:
            return _rephrase_simple(query, companies)
        return [{"company_name": q.company_name, "question": q.question} for q in result.questions]
    except Exception:
        return _rephrase_simple(query, companies)


def _rephrase_simple(query: str, companies: list[str]) -> list[dict]:
    """Simple rule-based query rephrasing fallback."""
    # Extract the core metric/question
    query_lower = query.lower()
    
    # Remove comparison phrases
    core = query
    for phrase in ["which company", "who had", "compare", "vs", "versus", "or"]:
        core = re.sub(rf'\b{phrase}\b', '', core, flags=re.IGNORECASE)
    
    # Remove company names
    for company in companies:
        core = re.sub(rf'\b{company}\b', '', core, flags=re.IGNORECASE)
    
    core = re.sub(r'\s+', ' ', core).strip()
    core = re.sub(r'^[,\?\s]+|[,\?\s]+$', '', core)
    
    # Build per-company questions
    result = []
    for company in companies:
        question = f"What was {company}'s {core}?"
        result.append({"company_name": company, "question": question})
    
    return result


# ---------------------------------------------------------------------------
# ANSWER GENERATION WITH TYPE-SPECIFIC PROMPTS
# ---------------------------------------------------------------------------

def generate_typed_answer(
    query: str,
    context: str,
    answer_type: Optional[str] = None,
) -> dict:
    """
    Generate answer using type-specific prompt.
    
    Args:
        query: The question
        context: Retrieved document context
        answer_type: Override detected type (name/number/boolean/names_list)
    
    Returns:
        Dict with answer schema fields
    """
    if not OPENAI_API_KEY:
        return {"final_answer": "API key not configured", "error": True}
    
    # Detect answer type if not provided
    if answer_type is None:
        answer_type = detect_answer_type(query)
    
    # Select prompt and schema
    prompts = {
        "name": (NAME_ANSWER_SYSTEM, NameAnswer),
        "number": (NUMBER_ANSWER_SYSTEM, NumberAnswer),
        "boolean": (BOOLEAN_ANSWER_SYSTEM, BooleanAnswer),
        "names_list": (NAMES_LIST_SYSTEM, NamesListAnswer),
    }
    
    system_prompt, schema = prompts.get(answer_type, (NAME_ANSWER_SYSTEM, NameAnswer))
    
    user_prompt = f"""Here is the context:
\"\"\"
{context}
\"\"\"

---

Here is the question:
"{query}"
"""
    
    try:
        result = llm_structured(
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
            model_key="main",
            schema=schema,
        )
        if result is None:
            raise ValueError("llm_structured returned None")
        return {
            "answer_type": answer_type,
            **result.model_dump(),
        }
    except Exception as e:
        return {
            "answer_type": answer_type,
            "final_answer": "N/A",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# COMPARATIVE ANSWER MERGING
# ---------------------------------------------------------------------------

def merge_comparative_answers(
    original_query: str,
    per_company_answers: dict[str, dict],
) -> dict:
    """
    Merge individual company answers into a comparative response.
    
    Args:
        original_query: The original comparison question
        per_company_answers: {"Flex": {...answer...}, "Jabil": {...answer...}}
    
    Returns:
        Merged comparison answer
    """
    active_key = ANTHROPIC_API_KEY if LLM_PROVIDER == "anthropic" else OPENAI_API_KEY
    if not active_key:
        return _merge_simple(original_query, per_company_answers)

    # Format individual answers for context
    context_parts = []
    for company, answer in per_company_answers.items():
        final = answer.get("final_answer", "N/A")
        reasoning = answer.get("reasoning_summary", "No reasoning provided")
        context_parts.append(f"\nCompany: {company}\nAnswer: {final}\nReasoning: {reasoning}\n")

    context = "\n---\n".join(context_parts)

    user_prompt = f"""Here are the individual company answers:
\"\"\"\n{context}\n\"\"\"

---

Here is the original comparative question:
"{original_query}"
"""

    try:
        result = llm_structured(
            messages=[{"role": "user", "content": user_prompt}],
            system=COMPARATIVE_MERGE_SYSTEM,
            model_key="main",
            schema=ComparativeAnswer,
        )
        if result is None:
            return _merge_simple(original_query, per_company_answers)
        return {
            "is_comparison": True,
            "per_company": per_company_answers,
            **result.model_dump(),
        }
    except Exception:
        return _merge_simple(original_query, per_company_answers)


def _merge_simple(query: str, per_company_answers: dict) -> dict:
    """Simple rule-based comparison merging fallback."""
    query_lower = query.lower()
    
    # Extract numeric values
    values = {}
    for company, answer in per_company_answers.items():
        final = answer.get("final_answer")
        if isinstance(final, (int, float)) and final != "N/A":
            values[company] = final
    
    if not values:
        return {
            "is_comparison": True,
            "final_answer": "N/A",
            "reasoning_summary": "No comparable numeric values found",
        }
    
    # Determine comparison type
    if "higher" in query_lower or "most" in query_lower or "highest" in query_lower:
        winner = max(values, key=values.get)
    elif "lower" in query_lower or "least" in query_lower or "lowest" in query_lower:
        winner = min(values, key=values.get)
    else:
        # Default to highest
        winner = max(values, key=values.get)
    
    return {
        "is_comparison": True,
        "company_values": values,
        "final_answer": winner,
        "comparison_result": f"{winner} with value {values[winner]}",
    }


# ---------------------------------------------------------------------------
# FULL COMPARISON PIPELINE
# ---------------------------------------------------------------------------

def answer_comparison_query(
    query: str,
    companies: list[str],
    retriever_func,
) -> dict:
    """
    Full pipeline for answering comparison questions.
    
    1. Rephrase into per-company questions
    2. Retrieve context for each company
    3. Generate typed answer for each
    4. Merge into comparative response
    
    Args:
        query: Original comparison question
        companies: List of companies to compare
        retriever_func: Function(query, company) -> context string
    
    Returns:
        Complete comparison answer with evidence
    """
    # Step 1: Rephrase
    sub_questions = rephrase_comparison_query(query, companies)
    
    # Step 2 & 3: Retrieve and answer per company
    per_company_answers = {}
    per_company_context = {}
    
    for sq in sub_questions:
        company = sq["company_name"]
        sub_query = sq["question"]
        
        # Retrieve context
        context = retriever_func(sub_query, company)
        per_company_context[company] = context
        
        # Generate answer
        answer = generate_typed_answer(sub_query, context)
        per_company_answers[company] = answer
    
    # Step 4: Merge
    final = merge_comparative_answers(query, per_company_answers)
    
    return {
        "original_query": query,
        "sub_questions": sub_questions,
        "per_company_context": per_company_context,
        "per_company_answers": per_company_answers,
        "final_comparison": final,
    }
