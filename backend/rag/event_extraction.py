"""
CapEx Event Extraction System

Event Lake Architecture:
- Structured event extraction from SEC filings, transcripts, news
- Bucket taxonomy: AI/DC vs Traditional with L2 categories
- Two-stage extraction: candidate filtering → structured extraction
- Deduplication and event merging

This module transforms "where is the money going" into aggregatable event records
that can be compared across tracked EMS companies.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from backend.core.config import OPENAI_API_KEY, RERANK_MODEL, LLM_MODEL, TRACKED_COMPANY_NAMES


# ---------------------------------------------------------------------------
# ENUMS: Event Types and Bucket Taxonomy
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """CapEx/Investment event types (A3 from spec)."""
    CAPEX_GUIDANCE = "CAPEX_GUIDANCE"
    FACILITY_OPEN_EXPAND = "FACILITY_OPEN_EXPAND"
    EQUIPMENT_PURCHASE = "EQUIPMENT_PURCHASE"
    DATA_CENTER_CAPACITY = "DATA_CENTER_CAPACITY"
    R_AND_D_INVESTMENT = "R_AND_D_INVESTMENT"
    M_AND_A = "M_AND_A"
    PARTNERSHIP_JV = "PARTNERSHIP_JV"
    SUPPLY_CHAIN_CAPACITY = "SUPPLY_CHAIN_CAPACITY"
    RESTRUCTURING_EXIT = "RESTRUCTURING_EXIT"
    HIRING_SKILL_BUILD = "HIRING_SKILL_BUILD"


class BucketL1(str, Enum):
    """Level 1 category: AI/DC vs Traditional."""
    AI_DC = "AI_DC"  # Hyperscaler / AI server / data center
    TRADITIONAL = "TRADITIONAL"  # Medical / Industrial / Auto / Aerospace
    MIXED = "MIXED"  # Serves both AI and traditional
    UNKNOWN = "UNKNOWN"


class BucketL2_AIDC(str, Enum):
    """Level 2 categories for AI/DC bucket."""
    POWER = "POWER"
    COMPUTE = "COMPUTE"
    COOLING = "COOLING"
    NETWORKING = "NETWORKING"
    DC_INFRASTRUCTURE = "DC_INFRASTRUCTURE"
    AI_SUPPLY_CHAIN = "AI_SUPPLY_CHAIN"


class BucketL2_Traditional(str, Enum):
    """Level 2 categories for Traditional bucket."""
    MEDICAL = "MEDICAL"
    INDUSTRIAL = "INDUSTRIAL"
    AUTOMOTIVE = "AUTOMOTIVE"
    AEROSPACE_DEFENSE = "AEROSPACE_DEFENSE"
    CONSUMER = "CONSUMER"
    OTHER = "OTHER"


class DocType(str, Enum):
    """Document types for source tracking."""
    SEC_10K = "SEC_10K"
    SEC_10Q = "SEC_10Q"
    SEC_8K = "SEC_8K"
    TRANSCRIPT = "TRANSCRIPT"
    NEWS = "NEWS"
    WEB = "WEB"
    INVESTOR_DECK = "INVESTOR_DECK"
    ANALYST_REPORT = "ANALYST_REPORT"


class ConfidenceTier(str, Enum):
    """Source confidence tiers."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ---------------------------------------------------------------------------
# DATA STRUCTURES: Event Schema (A2)
# ---------------------------------------------------------------------------

@dataclass
class EvidenceSpan:
    """A single piece of evidence supporting an event."""
    doc_id: str
    doc_type: str
    paragraph_id: str = ""
    timestamp: str = ""
    text_excerpt: str = ""
    url_or_locator: str = ""  # SEC accession / URL / transcript timestamp
    speaker: str = ""  # For transcripts: CEO/CFO/Analyst


@dataclass
class CapExEvent:
    """
    Structured CapEx/Investment event record (A2 schema).
    
    This is the core unit of the Event Lake - each event represents
    a concrete investment signal that can be aggregated and compared.
    """
    # Core identification
    event_id: str = ""  # Hash of key fields
    company: str = ""
    
    # Timing
    event_date: str = ""  # YYYY-MM-DD, prefer disclosure date
    period: str = ""  # FY2024, Q3'25, etc.
    
    # Event classification
    event_type: str = ""  # EventType enum value
    
    # Amount (nullable if not stated)
    amount_value: Optional[float] = None
    amount_currency: str = "USD"
    amount_unit: str = "millions"  # thousands / millions / billions
    time_horizon: str = ""  # one-time / annual / multi-year
    
    # Bucket taxonomy
    bucket_l1: str = ""  # AI_DC / TRADITIONAL / MIXED / UNKNOWN
    bucket_l2: str = ""  # Specific sub-category
    
    # Location and scope
    geo: str = ""  # NA / US:TX / APAC:MY etc.
    asset_or_scope: str = ""  # factory / line / equipment / JV / acquisition
    counterparty: str = ""  # Hyperscaler name, customer, acquired company
    
    # Evidence (critical for verification)
    evidence_spans: list = field(default_factory=list)
    
    # Confidence and notes
    confidence: float = 0.0  # 0-1
    notes: str = ""  # Caveats, estimation basis
    
    def generate_id(self) -> str:
        """Generate deterministic event_id from key fields."""
        key_string = f"{self.company}|{self.event_date}|{self.event_type}|{self.amount_value}|{self.geo}|{self.bucket_l1}"
        return hashlib.md5(key_string.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d["evidence_spans"] = [asdict(e) if hasattr(e, "__dict__") else e for e in self.evidence_spans]
        return d


# ---------------------------------------------------------------------------
# PYDANTIC SCHEMAS FOR LLM EXTRACTION
# ---------------------------------------------------------------------------

class CandidateSignal(BaseModel):
    """Stage 1 output: Is this passage an investment signal?"""
    has_investment_signal: bool = Field(description="Does this passage contain an investment signal?")
    trigger_keywords: list[str] = Field(description="Keywords that triggered detection")
    event_type_guess: str = Field(description="Likely event type from EventType enum")
    confidence: float = Field(description="Confidence 0-1")
    reasoning: str = Field(description="Brief explanation")


class ExtractedEvent(BaseModel):
    """Stage 2 output: Structured event extraction."""
    company: str = Field(description="Company name (Flex/Jabil/Celestica/Benchmark/Sanmina)")
    event_date: str = Field(description="Event date YYYY-MM-DD or best estimate")
    event_type: str = Field(description="Event type from EventType enum")
    
    amount_value: Optional[float] = Field(description="Numeric amount or null if not stated")
    amount_currency: str = Field(default="USD")
    amount_unit: str = Field(description="thousands/millions/billions")
    time_horizon: str = Field(description="one-time/annual/multi-year/over_N_years")
    
    bucket_l1: str = Field(description="AI_DC/TRADITIONAL/MIXED/UNKNOWN")
    bucket_l2: str = Field(description="Specific L2 category")
    
    geo: str = Field(description="Geographic region: NA/US:TX/APAC:MY/EMEA:PL etc.")
    asset_or_scope: str = Field(description="factory/line/equipment/JV/acquisition/capacity")
    counterparty: str = Field(description="Customer, partner, or acquired entity if mentioned")
    
    evidence_excerpt: str = Field(description="1-3 sentence quote from source")
    confidence: float = Field(description="Confidence 0-1")
    notes: str = Field(description="Caveats, estimation basis, unclear points")


# ---------------------------------------------------------------------------
# EXTRACTION PROMPTS (A5)
# ---------------------------------------------------------------------------

STAGE1_SYSTEM_PROMPT = """You are a financial signal detector for Electronics Manufacturing Services (EMS) companies.
Your task is to identify passages that contain investment/CapEx signals.

TRIGGER CRITERIA (must have at least one):
1. Explicit amounts: "$X million", "investing $Y", "capex of Z"
2. CapEx keywords: capital expenditure, capex, capital spending, PP&E purchases
3. Investment actions: building, expanding, acquiring, opening, launching
4. Capacity terms: new facility, production line, manufacturing capacity
5. M&A signals: acquisition, merger, joint venture, strategic partnership
6. Guidance: "expect to spend", "planning to invest", "capex guidance"

MUST be attributable to a company (Flex, Jabil, Celestica, Benchmark, Sanmina).
If the passage is about general industry trends without company-specific action, mark as NOT a signal.

Return JSON with: has_investment_signal, trigger_keywords, event_type_guess, confidence, reasoning"""


STAGE2_SYSTEM_PROMPT = """You are a structured data extractor for CapEx/investment events in the EMS industry.
Extract precise structured data from the passage. Be conservative - only extract what's explicitly stated.

COMPANIES: Flex, Jabil, Celestica, Benchmark Electronics, Sanmina

EVENT TYPES:
- CAPEX_GUIDANCE: Budget/guidance announcements
- FACILITY_OPEN_EXPAND: New or expanded facilities
- EQUIPMENT_PURCHASE: Equipment/machinery purchases
- DATA_CENTER_CAPACITY: Data center capacity expansion
- R_AND_D_INVESTMENT: R&D spending
- M_AND_A: Mergers, acquisitions
- PARTNERSHIP_JV: Joint ventures, partnerships
- SUPPLY_CHAIN_CAPACITY: Supply chain investments
- RESTRUCTURING_EXIT: Closures, restructuring (negative signal)
- HIRING_SKILL_BUILD: Major hiring initiatives

BUCKET L1:
- AI_DC: Hyperscaler, AI server, data center, liquid cooling, HPC, GPU
- TRADITIONAL: Medical, Industrial, Automotive, Aerospace, Consumer
- MIXED: Serves both (e.g., general facility serving multiple segments)
- UNKNOWN: Cannot determine from text

BUCKET L2 (AI_DC): POWER, COMPUTE, COOLING, NETWORKING, DC_INFRASTRUCTURE, AI_SUPPLY_CHAIN
BUCKET L2 (Traditional): MEDICAL, INDUSTRIAL, AUTOMOTIVE, AEROSPACE_DEFENSE, CONSUMER, OTHER

AMOUNT EXTRACTION:
- Extract exact number if stated
- Note unit from context: "in thousands" vs "in millions"
- Set amount_value=null if no specific number given
- For ranges like "$100-150M", use midpoint (125) and note in notes field

GEO FORMAT: Region:Country:State (e.g., NA:US:TX, APAC:MY, EMEA:PL)

CRITICAL:
- Only extract what's explicitly stated
- If uncertain, set confidence lower and explain in notes
- evidence_excerpt must be a direct quote (1-3 sentences)"""


# ---------------------------------------------------------------------------
# EXTRACTION FUNCTIONS
# ---------------------------------------------------------------------------

def detect_candidate_signal(
    text: str,
    metadata: dict,
) -> CandidateSignal:
    """
    Stage 1: Quick check if passage contains investment signal.
    Uses rule-based detection first, LLM only if needed.
    """
    # Rule-based quick filters
    text_lower = text.lower()
    
    # Must-have triggers
    amount_patterns = [
        r'\$[\d,]+\s*(million|billion|thousand|m|b|k)',
        r'[\d,]+\s*(million|billion)\s*dollars',
        r'capex\s+of\s+\$?[\d,]+',
    ]
    
    capex_keywords = [
        "capital expenditure", "capex", "capital spending",
        "property and equipment", "pp&e", "property, plant",
    ]
    
    action_keywords = [
        "building", "expanding", "acquiring", "opening", "launching",
        "invest", "investment", "constructing", "construct",
    ]
    
    capacity_keywords = [
        "new facility", "production line", "manufacturing capacity",
        "factory", "campus", "site expansion", "new plant",
    ]
    
    # Check triggers
    triggers = []
    
    for pattern in amount_patterns:
        if re.search(pattern, text_lower):
            triggers.append("amount_mentioned")
            break
    
    for kw in capex_keywords:
        if kw in text_lower:
            triggers.append(f"capex:{kw}")
            break
    
    for kw in action_keywords:
        if kw in text_lower:
            triggers.append(f"action:{kw}")
            break
    
    for kw in capacity_keywords:
        if kw in text_lower:
            triggers.append(f"capacity:{kw}")
            break
    
    # Quick decision
    has_signal = len(triggers) >= 1
    
    # Guess event type
    event_type_guess = "UNKNOWN"
    if "facility" in text_lower or "factory" in text_lower or "plant" in text_lower:
        event_type_guess = "FACILITY_OPEN_EXPAND"
    elif "acqui" in text_lower or "merger" in text_lower:
        event_type_guess = "M_AND_A"
    elif "capex" in text_lower or "capital expenditure" in text_lower:
        event_type_guess = "CAPEX_GUIDANCE"
    elif "data center" in text_lower or "hyperscale" in text_lower:
        event_type_guess = "DATA_CENTER_CAPACITY"
    elif "equipment" in text_lower:
        event_type_guess = "EQUIPMENT_PURCHASE"
    
    return CandidateSignal(
        has_investment_signal=has_signal,
        trigger_keywords=triggers[:5],
        event_type_guess=event_type_guess,
        confidence=0.8 if len(triggers) >= 2 else 0.5,
        reasoning=f"Found {len(triggers)} trigger(s)" if has_signal else "No investment signals detected",
    )


def extract_structured_event(
    text: str,
    metadata: dict,
    candidate: CandidateSignal,
) -> Optional[CapExEvent]:
    """
    Stage 2: Extract structured event using LLM.
    Only called if Stage 1 detected a signal.
    """
    if not OPENAI_API_KEY:
        return _extract_structured_event_rules(text, metadata)
    
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # Build context
    doc_context = f"""
Document metadata:
- Company context: {metadata.get('company', 'Unknown')}
- Document type: {metadata.get('doc_type', 'Unknown')}
- Document date: {metadata.get('doc_date', 'Unknown')}
- Period: {metadata.get('period', 'Unknown')}
- Section: {metadata.get('section', 'Unknown')}

Stage 1 analysis:
- Event type guess: {candidate.event_type_guess}
- Triggers: {', '.join(candidate.trigger_keywords)}
"""
    
    user_prompt = f"""{doc_context}

Text to extract from:
\"\"\"
{text[:3000]}
\"\"\"

Extract the investment event as structured JSON. If multiple events exist, extract the most significant one."""
    
    try:
        response = client.beta.chat.completions.parse(
            model=RERANK_MODEL,  # Use faster model for extraction
            messages=[
                {"role": "system", "content": STAGE2_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=ExtractedEvent,
        )
        
        extracted = response.choices[0].message.parsed
        
        # Convert to CapExEvent
        event = CapExEvent(
            company=extracted.company,
            event_date=extracted.event_date,
            event_type=extracted.event_type,
            amount_value=extracted.amount_value,
            amount_currency=extracted.amount_currency,
            amount_unit=extracted.amount_unit,
            time_horizon=extracted.time_horizon,
            bucket_l1=extracted.bucket_l1,
            bucket_l2=extracted.bucket_l2,
            geo=extracted.geo,
            asset_or_scope=extracted.asset_or_scope,
            counterparty=extracted.counterparty,
            evidence_spans=[EvidenceSpan(
                doc_id=metadata.get("doc_id", ""),
                doc_type=metadata.get("doc_type", ""),
                text_excerpt=extracted.evidence_excerpt,
                url_or_locator=metadata.get("source", ""),
            )],
            confidence=extracted.confidence,
            notes=extracted.notes,
        )
        event.event_id = event.generate_id()
        
        return event
        
    except Exception as e:
        print(f"LLM extraction error: {e}")
        return _extract_structured_event_rules(text, metadata)


def _extract_structured_event_rules(text: str, metadata: dict) -> Optional[CapExEvent]:
    """Fallback rule-based extraction when LLM unavailable."""
    text_lower = text.lower()
    
    # Detect company
    companies = [company.lower() for company in TRACKED_COMPANY_NAMES]
    company = metadata.get("company", "")
    if not company:
        for c in companies:
            if c in text_lower:
                company = c.title()
                break
    
    # Extract amount
    amount_match = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*(million|billion|m|b)', text_lower)
    amount_value = None
    amount_unit = "millions"
    if amount_match:
        try:
            amount_value = float(amount_match.group(1).replace(",", ""))
            unit = amount_match.group(2).lower()
            if unit in ["billion", "b"]:
                amount_unit = "billions"
            elif unit in ["million", "m"]:
                amount_unit = "millions"
        except ValueError:
            pass
    
    # Detect bucket
    bucket_l1 = BucketL1.UNKNOWN.value
    bucket_l2 = ""
    
    ai_keywords = ["data center", "hyperscale", "ai ", "artificial intelligence", 
                   "gpu", "liquid cooling", "hpc", "server"]
    trad_keywords = ["medical", "automotive", "industrial", "aerospace", "defense"]
    
    for kw in ai_keywords:
        if kw in text_lower:
            bucket_l1 = BucketL1.AI_DC.value
            if "cooling" in kw:
                bucket_l2 = BucketL2_AIDC.COOLING.value
            elif "server" in kw or "compute" in text_lower:
                bucket_l2 = BucketL2_AIDC.COMPUTE.value
            break
    
    if bucket_l1 == BucketL1.UNKNOWN.value:
        for kw in trad_keywords:
            if kw in text_lower:
                bucket_l1 = BucketL1.TRADITIONAL.value
                bucket_l2 = kw.upper()
                break
    
    # Create event
    event = CapExEvent(
        company=company,
        event_date=metadata.get("doc_date", datetime.now().strftime("%Y-%m-%d")),
        event_type=EventType.CAPEX_GUIDANCE.value,
        amount_value=amount_value,
        amount_unit=amount_unit,
        bucket_l1=bucket_l1,
        bucket_l2=bucket_l2,
        evidence_spans=[EvidenceSpan(
            doc_id=metadata.get("doc_id", ""),
            doc_type=metadata.get("doc_type", ""),
            text_excerpt=text[:500],
        )],
        confidence=0.5,
        notes="Rule-based extraction (LLM unavailable)",
    )
    event.event_id = event.generate_id()
    
    return event


# ---------------------------------------------------------------------------
# EVENT DEDUPLICATION (A6)
# ---------------------------------------------------------------------------

def deduplicate_events(
    events: list[CapExEvent],
    time_window_days: int = 30,
    similarity_threshold: float = 0.8,
) -> list[CapExEvent]:
    """
    Merge duplicate events from different sources.
    
    Canonical event rules:
    - Same company, same event_type, same geo, within time window
    - Keep most authoritative source as primary (SEC > Transcript > News)
    - Merge evidence spans
    """
    if not events:
        return []
    
    # Sort by authority (SEC first)
    authority_order = {
        "SEC_10K": 1, "SEC_10Q": 1, "SEC_8K": 2,
        "TRANSCRIPT": 3, "NEWS": 4, "WEB": 5,
    }
    
    events_sorted = sorted(events, key=lambda e: 
        authority_order.get(e.evidence_spans[0].doc_type if e.evidence_spans else "WEB", 5)
    )
    
    merged = []
    used_indices = set()
    
    for i, event in enumerate(events_sorted):
        if i in used_indices:
            continue
        
        # Find duplicates
        canonical = event
        duplicates = []
        
        for j, other in enumerate(events_sorted[i+1:], start=i+1):
            if j in used_indices:
                continue
            
            if _events_are_duplicates(event, other, time_window_days, similarity_threshold):
                duplicates.append(other)
                used_indices.add(j)
        
        # Merge evidence from duplicates
        if duplicates:
            for dup in duplicates:
                canonical.evidence_spans.extend(dup.evidence_spans)
            canonical.notes += f" | Merged from {len(duplicates)+1} sources"
        
        merged.append(canonical)
    
    return merged


def _events_are_duplicates(
    e1: CapExEvent,
    e2: CapExEvent,
    time_window_days: int,
    similarity_threshold: float,
) -> bool:
    """Check if two events are likely the same."""
    # Must be same company and event type
    if e1.company.lower() != e2.company.lower():
        return False
    if e1.event_type != e2.event_type:
        return False
    
    # Check geo (if both specified)
    if e1.geo and e2.geo and e1.geo.split(":")[0] != e2.geo.split(":")[0]:
        return False
    
    # Check amount (if both have values, should be similar)
    if e1.amount_value and e2.amount_value:
        ratio = min(e1.amount_value, e2.amount_value) / max(e1.amount_value, e2.amount_value)
        if ratio < 0.7:  # More than 30% difference
            return False
    
    # Time window check
    try:
        d1 = datetime.strptime(e1.event_date, "%Y-%m-%d")
        d2 = datetime.strptime(e2.event_date, "%Y-%m-%d")
        if abs((d1 - d2).days) > time_window_days:
            return False
    except ValueError:
        pass
    
    return True


# ---------------------------------------------------------------------------
# AGGREGATION FUNCTIONS (for comparison queries)
# ---------------------------------------------------------------------------

def aggregate_events_by_company(
    events: list[CapExEvent],
    bucket_filter: Optional[str] = None,
) -> dict:
    """
    Aggregate events by company for comparison.
    
    Returns:
        {
            "Flex": {"ai_dc_amount": 500, "traditional_amount": 200, "events": [...], ...},
            "Jabil": {...},
            ...
        }
    """
    from collections import defaultdict
    
    aggregation = defaultdict(lambda: {
        "ai_dc_amount": 0.0,
        "traditional_amount": 0.0,
        "ai_dc_events": [],
        "traditional_events": [],
        "mixed_events": [],
        "total_events": 0,
        "geos": set(),
        "event_types": defaultdict(int),
    })
    
    for event in events:
        company = event.company
        agg = aggregation[company]
        
        # Apply bucket filter if specified
        if bucket_filter and event.bucket_l1 != bucket_filter:
            continue
        
        # Aggregate amounts
        amount = event.amount_value or 0
        if event.amount_unit == "billions":
            amount *= 1000
        elif event.amount_unit == "thousands":
            amount /= 1000
        
        if event.bucket_l1 == BucketL1.AI_DC.value:
            agg["ai_dc_amount"] += amount
            agg["ai_dc_events"].append(event.to_dict())
        elif event.bucket_l1 == BucketL1.TRADITIONAL.value:
            agg["traditional_amount"] += amount
            agg["traditional_events"].append(event.to_dict())
        else:
            agg["mixed_events"].append(event.to_dict())
        
        agg["total_events"] += 1
        if event.geo:
            agg["geos"].add(event.geo.split(":")[0])  # Top-level region
        agg["event_types"][event.event_type] += 1
    
    # Convert sets to lists for JSON
    for company in aggregation:
        aggregation[company]["geos"] = list(aggregation[company]["geos"])
        aggregation[company]["event_types"] = dict(aggregation[company]["event_types"])
        
        # Calculate AI/DC ratio
        total = aggregation[company]["ai_dc_amount"] + aggregation[company]["traditional_amount"]
        if total > 0:
            aggregation[company]["ai_dc_ratio"] = round(
                aggregation[company]["ai_dc_amount"] / total, 3
            )
        else:
            aggregation[company]["ai_dc_ratio"] = None
    
    return dict(aggregation)


def build_comparison_table(
    aggregation: dict,
    companies: list[str] = None,
) -> str:
    """
    Build a formatted comparison table for LLM context.
    
    Output format:
    | Company | AI/DC ($M) | Traditional ($M) | AI/DC % | Top Themes | Geos |
    """
    if companies is None:
        companies = list(aggregation.keys())
    
    lines = [
        "| Company | AI/DC ($M) | Traditional ($M) | AI/DC % | Top Event Types | Regions |",
        "|---------|-----------|-----------------|---------|-----------------|---------|",
    ]
    
    for company in companies:
        data = aggregation.get(company, {})
        
        ai_dc = data.get("ai_dc_amount", 0)
        trad = data.get("traditional_amount", 0)
        ratio = data.get("ai_dc_ratio")
        ratio_str = f"{ratio:.0%}" if ratio is not None else "N/A"
        
        # Top event types
        event_types = data.get("event_types", {})
        top_types = sorted(event_types.items(), key=lambda x: x[1], reverse=True)[:2]
        types_str = ", ".join([t[0].split("_")[0] for t in top_types]) if top_types else "N/A"
        
        geos = ", ".join(data.get("geos", [])[:3]) or "N/A"
        
        lines.append(
            f"| {company} | {ai_dc:.0f} | {trad:.0f} | {ratio_str} | {types_str} | {geos} |"
        )
    
    return "\n".join(lines)
