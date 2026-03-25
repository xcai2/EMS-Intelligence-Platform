"""
LLM Analyzer
============
Analyzes documents using local LLM (Ollama) to extract insights.
Follows the Advanced Document Reading Guide framework.
"""

import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    import ollama
except ImportError:
    ollama = None
    print("Warning: ollama not installed. Install with: pip install ollama")

from document_processor import Document, extract_mda_section, extract_risk_factors, extract_capex_mentions


class LLMAnalyzer:
    """Analyze documents using local LLM (Ollama)"""
    
    def __init__(self, model: str = "llama3.1", temperature: float = 0.1, quick_mode: bool = True):
        """
        Initialize the LLM analyzer.
        
        Args:
            model: Ollama model name (llama3.1, mistral, etc.)
            temperature: LLM temperature (0.0-1.0)
            quick_mode: If True, use shorter prompts for faster analysis
        """
        self.model = model
        self.temperature = temperature
        self.quick_mode = quick_mode
        self.max_text_length = 8000 if quick_mode else 30000
        
        if ollama is None:
            raise ImportError("ollama package not installed")
    
    def _query_llm(self, prompt: str, system: str = None) -> str:
        """Query the local LLM"""
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={"temperature": self.temperature}
            )
            return response["message"]["content"]
        except Exception as e:
            print(f"LLM query failed: {e}")
            return ""
    
    def _parse_json_response(self, response: str) -> Dict:
        """Parse JSON from LLM response"""
        
        # Try to find JSON in the response
        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON array
        array_match = re.search(r"\[[\s\S]*\]", response)
        if array_match:
            try:
                return {"items": json.loads(array_match.group())}
            except json.JSONDecodeError:
                pass
        
        return {"raw_response": response}
    
    def analyze_financial_context(self, documents: List[Document]) -> Dict[str, Any]:
        """
        Analyze financial context from documents.
        Extracts: Revenue, Operating Income, Net Income, CapEx, ratios
        """
        
        # Get 10-K documents for annual data
        annual_docs = [d for d in documents if d.doc_type == "10-K"]
        
        if not annual_docs:
            # Try to find any document with financial data
            annual_docs = documents[:3]
        
        if not annual_docs:
            return {"error": "No documents found"}
        
        # Combine relevant sections - limit text in quick mode
        financial_text = ""
        doc_limit = 2 if self.quick_mode else 3
        text_per_doc = 4000 if self.quick_mode else 15000
        
        for doc in annual_docs[:doc_limit]:
            mda = extract_mda_section(doc.content)
            if mda:
                financial_text += f"\n\n=== {doc.fiscal_year} ===\n{mda[:text_per_doc]}"
        
        if not financial_text:
            financial_text = "\n".join([doc.content[:text_per_doc] for doc in annual_docs[:doc_limit]])
        
        # Shorter prompt for quick mode
        if self.quick_mode:
            prompt = f"""Extract key financial metrics from this text. Return JSON only.

TEXT (excerpt):
{financial_text[:self.max_text_length]}

Return this JSON format:
{{"yearly_metrics": [{{"Year": "FY24", "Revenue": "$XXB", "CapEx": "$XXXM", "CapEx_Revenue_Pct": "X%"}}], "latest_revenue": "$XXB", "capex_ratio": "X%", "insights": ["insight1", "insight2"]}}"""
        else:
            prompt = f"""Analyze the following financial documents and extract key metrics.

DOCUMENTS:
{financial_text[:30000]}

Extract the following information and return as JSON:

{{
    "yearly_metrics": [
        {{
            "Year": "FY24",
            "Revenue": "$XX.XB",
            "Operating_Income": "$XXXM",
            "Net_Income": "$XXXM",
            "CapEx": "$XXXM",
            "CapEx_Revenue_Pct": "X.X%"
        }}
    ],
    "cash_flow": [
        {{
            "Year": "FY24",
            "Operating_Cash_Flow": "$XXXM",
            "CapEx": "$XXXM",
            "Free_Cash_Flow": "$XXXM"
        }}
    ],
    "latest_revenue": "$XX.XB",
    "revenue_growth": "+X%",
    "capex_ratio": "X.X%",
    "ratio_change": "+X.X%",
    "insights": [
        "Insight 1 about financial health",
        "Insight 2 about CapEx trends",
        "Insight 3 about cash flow"
    ]
}}

Focus on extracting actual numbers from the documents. If exact numbers aren't found, note "N/A"."""

        system = """You are a financial analyst expert at extracting metrics from SEC filings.
Always return valid JSON. Extract actual numbers, don't make them up.
If a metric isn't found, use "N/A" as the value."""

        response = self._query_llm(prompt, system)
        return self._parse_json_response(response)
    
    def analyze_capex_breakdown(self, documents: List[Document]) -> Dict[str, Any]:
        """
        Analyze CapEx breakdown by type, geography, and segment.
        """
        
        # Get documents with CapEx mentions - limit in quick mode
        capex_content = []
        mention_limit = 5 if self.quick_mode else 10
        
        for doc in documents[:5] if self.quick_mode else documents:
            mentions = extract_capex_mentions(doc.content)
            if mentions:
                capex_content.extend(mentions[:mention_limit])
        
        # Also get MD&A sections
        mda_limit = 2000 if self.quick_mode else 5000
        for doc in documents[:3] if self.quick_mode else documents:
            if doc.doc_type in ["10-K", "10-Q"]:
                mda = extract_mda_section(doc.content)
                if mda:
                    capex_content.append(mda[:mda_limit])
        
        combined_text = "\n\n".join(capex_content[:10] if self.quick_mode else capex_content[:20])
        
        # Quick mode: shorter prompt
        if self.quick_mode:
            prompt = f"""Extract CapEx breakdown from this text. Return JSON only.

TEXT:
{combined_text[:self.max_text_length]}

Return JSON: {{"total_capex": "$XM", "ai_percentage": "X%", "by_type": [{{"Category": "AI/Data Center", "Amount": "$XM", "Percentage": "X%"}}], "ai_traditional": {{"ai": 100, "traditional": 200, "ai_pct": 33}}}}"""
        else:
            prompt = f"""Analyze the following document excerpts about capital expenditures.

DOCUMENTS:
{combined_text[:30000]}

Extract CapEx breakdown and return as JSON:

{{
    "total_capex": "$X.XB",
    "capex_growth": "+X%",
    "ai_percentage": "XX%",
    "ai_change": "+X%",
    
    "by_type": [
        {{"Category": "New Facilities", "Amount": "$XXXM", "Percentage": "XX%"}},
        {{"Category": "Equipment/Machinery", "Amount": "$XXXM", "Percentage": "XX%"}},
        {{"Category": "IT/Software", "Amount": "$XXXM", "Percentage": "XX%"}},
        {{"Category": "Maintenance", "Amount": "$XXXM", "Percentage": "XX%"}},
        {{"Category": "AI/Data Center", "Amount": "$XXXM", "Percentage": "XX%"}}
    ],
    
    "by_geography": [
        {{"Region": "North America", "CapEx": "$XXXM", "Percentage": "XX%", "Key_Projects": "Description"}},
        {{"Region": "Mexico", "CapEx": "$XXXM", "Percentage": "XX%", "Key_Projects": "Description"}},
        {{"Region": "Asia", "CapEx": "$XXXM", "Percentage": "XX%", "Key_Projects": "Description"}}
    ],
    
    "by_segment": [
        {{"Segment": "Cloud & Data Center", "Revenue": "$XB", "CapEx": "$XXXM", "CapEx/Revenue": "X%"}},
        {{"Segment": "Industrial", "Revenue": "$XB", "CapEx": "$XXXM", "CapEx/Revenue": "X%"}}
    ],
    
    "ai_traditional": {{
        "ai": 350,
        "traditional": 650,
        "ai_pct": 35
    }},
    
    "breakdown": [
        {{"Category": "AI/Data Center", "Amount": 350}},
        {{"Category": "Traditional", "Amount": 650}}
    ]
}}

Extract actual numbers from the documents. Use "N/A" if not found."""

        system = """You are a financial analyst expert at analyzing capital expenditure patterns.
Always return valid JSON. Extract actual breakdowns mentioned in the documents.
Pay special attention to AI/Data Center vs Traditional business allocations."""

        response = self._query_llm(prompt, system)
        return self._parse_json_response(response)
    
    def analyze_strategic_initiatives(self, documents: List[Document]) -> Dict[str, Any]:
        """
        Analyze strategic initiatives: major projects, technology investments, ESG.
        """
        
        # Combine press releases, 8-K, and presentations
        relevant_docs = [d for d in documents if d.doc_type in ["8-K", "press_release", "earnings_presentation"]]
        
        content = "\n\n".join([
            f"=== {d.filename} ===\n{d.content[:8000]}" 
            for d in relevant_docs[:10]
        ])
        
        # Add earnings call content
        earnings_docs = [d for d in documents if d.doc_type == "earnings_call"]
        for doc in earnings_docs[:3]:
            content += f"\n\n=== {doc.filename} ===\n{doc.content[:8000]}"
        
        prompt = f"""Analyze the following documents for strategic initiatives.

DOCUMENTS:
{content[:35000]}

Extract strategic initiatives and return as JSON:

{{
    "projects": [
        {{
            "Project Name": "Project name",
            "Location": "City, State/Country",
            "Investment": "$XXXM",
            "Start Date": "Q1 FY24",
            "Completion": "Q3 FY25",
            "Capacity": "XXX sq ft",
            "Purpose": "AI data center / Manufacturing / etc."
        }}
    ],
    
    "technology": [
        {{
            "type": "Automation",
            "description": "Description of technology investment",
            "amount": "$XXM"
        }},
        {{
            "type": "Industry 4.0",
            "description": "Smart factory initiatives",
            "amount": "$XXM"
        }}
    ],
    
    "esg": [
        {{
            "initiative": "Solar Installation",
            "details": "XX MW solar capacity at facility",
            "investment": "$XXM",
            "expected_impact": "XX% carbon reduction"
        }}
    ],
    
    "esg_total": "$XXM"
}}

Focus on concrete projects with specific investments and timelines."""

        system = """You are a strategic analyst expert at identifying major corporate initiatives.
Always return valid JSON. Focus on projects with clear investment amounts and timelines.
Include technology/automation and ESG/sustainability investments."""

        response = self._query_llm(prompt, system)
        return self._parse_json_response(response)
    
    def analyze_competitive_positioning(self, documents: List[Document]) -> Dict[str, Any]:
        """
        Analyze competitive positioning: customers, competitors, market share.
        """
        
        # Get 10-K for risk factors and business description
        annual_docs = [d for d in documents if d.doc_type == "10-K"]
        
        content = ""
        for doc in annual_docs[:2]:
            risk_section = extract_risk_factors(doc.content)
            if risk_section:
                content += f"\n\n=== Risk Factors ===\n{risk_section[:10000]}"
            content += f"\n\n=== Business ===\n{doc.content[:10000]}"
        
        prompt = f"""Analyze the following documents for competitive positioning.

DOCUMENTS:
{content[:30000]}

Extract competitive intelligence and return as JSON:

{{
    "customers": [
        {{"Customer": "Customer A (Hyperscale)", "Revenue %": "15%", "Notes": "Major cloud provider"}},
        {{"Customer": "Customer B", "Revenue %": "12%", "Notes": "Consumer electronics"}}
    ],
    
    "competitors": [
        {{"Company": "Competitor Name", "Strengths": "Description", "Weaknesses": "Description"}}
    ],
    
    "benchmarking": [
        {{
            "Company": "This Company",
            "CapEx/Revenue": 50,
            "AI Investment": 35,
            "Growth Rate": 60,
            "FCF Margin": 45,
            "ROIC": 55
        }}
    ],
    
    "market_share": [
        {{"Market": "AI Server Manufacturing", "TAM": "$50B", "Share %": 15, "Growth Rate": "+40%"}},
        {{"Market": "EMS General", "TAM": "$500B", "Share %": 5, "Growth Rate": "+8%"}}
    ],
    
    "competitive_advantages": [
        "Advantage 1",
        "Advantage 2"
    ],
    
    "competitive_threats": [
        "Threat 1",
        "Threat 2"
    ]
}}

Note: For benchmarking, use scores 0-100 representing relative positioning."""

        system = """You are a competitive intelligence analyst.
Always return valid JSON. Extract customer concentration, competitor mentions, and market positioning.
Try to identify unnamed customers based on descriptions (e.g., "hyperscale cloud provider" = AWS/Azure/Google)."""

        response = self._query_llm(prompt, system)
        return self._parse_json_response(response)
    
    def analyze_risk_factors(self, documents: List[Document]) -> Dict[str, Any]:
        """
        Analyze risk factors: supply chain, geopolitical, labor, etc.
        """
        
        # Get risk sections from 10-K
        annual_docs = [d for d in documents if d.doc_type == "10-K"]
        
        content = ""
        for doc in annual_docs[:2]:
            risk_section = extract_risk_factors(doc.content)
            if risk_section:
                content += f"\n\n=== {doc.fiscal_year} Risk Factors ===\n{risk_section[:15000]}"
        
        prompt = f"""Analyze the following risk factors sections.

DOCUMENTS:
{content[:30000]}

Extract risk analysis and return as JSON:

{{
    "supply_chain": [
        {{
            "risk": "Component Shortage",
            "description": "GPU and chip supply constraints",
            "severity": "high",
            "mitigation": "Dual sourcing strategy"
        }}
    ],
    
    "geopolitical": [
        {{
            "risk": "China Operations",
            "description": "Trade tensions and tariff exposure",
            "severity": "medium",
            "mitigation": "Nearshoring to Mexico"
        }}
    ],
    
    "labor": [
        {{
            "risk": "Talent Shortage",
            "description": "Difficulty finding skilled workers",
            "severity": "medium",
            "mitigation": "Automation investments"
        }}
    ],
    
    "risk_matrix": [
        {{"Risk": "Supply Chain", "Category": "Operational", "Likelihood": 70, "Impact": 80, "Score": 56}},
        {{"Risk": "Geopolitical", "Category": "External", "Likelihood": 50, "Impact": 70, "Score": 35}}
    ],
    
    "red_flags": [
        {{
            "flag": "CapEx exceeding guidance",
            "explanation": "Actual CapEx 15% above original guidance - may indicate cost overruns"
        }}
    ]
}}

Severity should be: low, medium, or high.
Likelihood and Impact are 0-100 scales. Score = Likelihood * Impact / 100."""

        system = """You are a risk analyst expert at identifying corporate risks.
Always return valid JSON. Categorize risks and assess their severity objectively.
Look for red flags and anomalies that could indicate problems."""

        response = self._query_llm(prompt, system)
        return self._parse_json_response(response)
    
    def analyze_forward_guidance(self, documents: List[Document]) -> Dict[str, Any]:
        """
        Analyze forward-looking guidance: CapEx forecasts, project pipeline, ROIC targets.
        """
        
        # Get earnings calls and presentations (most forward-looking)
        earnings_docs = [d for d in documents if d.doc_type in ["earnings_call", "earnings_presentation"]]
        
        content = "\n\n".join([
            f"=== {d.filename} ===\n{d.content[:10000]}" 
            for d in earnings_docs[:5]
        ])
        
        prompt = f"""Analyze the following earnings documents for forward-looking guidance.

DOCUMENTS:
{content[:30000]}

Extract forward guidance and return as JSON:

{{
    "capex_guidance": [
        {{"Period": "FY25", "Low": 1200, "High": 1400, "Midpoint": 1300, "Range": 200, "Notes": "Guidance from Q3 call"}},
        {{"Period": "FY26", "Low": 1300, "High": 1500, "Midpoint": 1400, "Range": 200, "Notes": "Preliminary"}}
    ],
    
    "pipeline": [
        {{"Project": "Austin Phase 2", "Status": "Planning", "Expected CapEx": "$100M", "Start Date": "H2 FY25"}},
        {{"Project": "Vietnam Facility", "Status": "Approved", "Expected CapEx": "$200M", "Start Date": "Q1 FY26"}}
    ],
    
    "quotes": [
        {{
            "text": "We expect AI-related CapEx to represent 40% of total spending in FY25",
            "speaker": "CFO Name",
            "context": "Q3 FY24 Earnings Call"
        }}
    ],
    
    "roic": {{
        "target": "15%",
        "current": "12%",
        "gap": "-3%"
    }},
    
    "key_themes": [
        "Increasing AI investment",
        "Nearshoring to Mexico",
        "Automation to offset labor costs"
    ]
}}

Focus on specific forward-looking statements with numbers."""

        system = """You are a financial analyst expert at analyzing earnings guidance.
Always return valid JSON. Extract specific forward-looking numbers and management quotes.
Note the source (which earnings call/presentation) for each piece of guidance."""

        response = self._query_llm(prompt, system)
        return self._parse_json_response(response)
    
    def analyze_earnings_calls(self, documents: List[Document]) -> Dict[str, Any]:
        """
        Deep analysis of earnings call transcripts for qualitative insights.
        """
        
        earnings_docs = [d for d in documents if d.doc_type == "earnings_call"]
        
        content = "\n\n".join([
            f"=== {d.filename} ===\n{d.content[:12000]}" 
            for d in earnings_docs[:4]
        ])
        
        prompt = f"""Analyze the following earnings call transcripts for strategic insights.

TRANSCRIPTS:
{content[:35000]}

Extract insights and return as JSON:

{{
    "analyst_questions": [
        {{
            "question": "Question about CapEx breakdown",
            "answer_summary": "Management's response",
            "key_data_point": "35% to AI"
        }}
    ],
    
    "management_tone": {{
        "overall": "confident",
        "ai_business": "very optimistic",
        "traditional_business": "cautious",
        "explanation": "Management expressed strong confidence in AI growth but noted headwinds in consumer electronics"
    }},
    
    "customer_mentions": [
        {{
            "customer_type": "Hyperscale cloud provider",
            "context": "Won new liquid cooling contract",
            "sentiment": "positive"
        }}
    ],
    
    "capex_discussion": [
        {{
            "topic": "CapEx allocation",
            "quote": "Direct quote from transcript",
            "implication": "What this means strategically"
        }}
    ],
    
    "surprises": [
        "Unexpected announcement or change",
        "New strategic direction revealed"
    ],
    
    "red_flags_from_calls": [
        "Any concerning statements or dodged questions"
    ]
}}

Pay special attention to the Q&A section and management's tone/confidence level."""

        system = """You are an expert at analyzing earnings call transcripts.
Always return valid JSON. Focus on qualitative insights that numbers alone don't reveal.
Note management's confidence level and any concerning patterns in their responses."""

        response = self._query_llm(prompt, system)
        return self._parse_json_response(response)
    
    def generate_synthesis(self, all_results: Dict[str, Any], company: str) -> Dict[str, Any]:
        """
        Generate final synthesis and recommendations.
        """
        
        # Summarize key data points - shorter in quick mode
        max_summary = 5000 if self.quick_mode else 15000
        summary = json.dumps(all_results, indent=2, default=str)[:max_summary]
        
        if self.quick_mode:
            prompt = f"""Summarize this {company} analysis. Return JSON only.

DATA:
{summary}

Return: {{"thesis": {{"classification": "Growth/Steady/Defensive", "description": "1 sentence"}}, "key_findings": ["finding1", "finding2", "finding3"], "risk_profile": {{"level": "Low/Medium/High", "explanation": "1 sentence"}}, "bottom_line": "1-2 sentence summary"}}"""
        else:
            prompt = f"""Based on the following analysis of {company}, generate a strategic synthesis.

ANALYSIS RESULTS:
{summary}

Generate synthesis and return as JSON:

{{
    "thesis": {{
        "classification": "Aggressive Growth | Steady State | Defensive",
        "description": "One paragraph describing the company's investment thesis"
    }},
    
    "positioning": [
        {{"dimension": "AI/Data Center", "assessment": "Leader/Follower/Minimal with explanation"}},
        {{"dimension": "Geographic Strategy", "assessment": "Nearshoring/Diversifying/China+ with explanation"}},
        {{"dimension": "Competitive Advantage", "assessment": "Technology/Scale/Flexibility with explanation"}}
    ],
    
    "risk_profile": {{
        "level": "Low | Medium | High",
        "explanation": "One paragraph explaining the risk level"
    }},
    
    "key_findings": [
        "Finding 1 - most important insight",
        "Finding 2",
        "Finding 3",
        "Finding 4",
        "Finding 5"
    ],
    
    "recommendations": [
        {{"type": "opportunity", "text": "Recommendation for Flex based on this company's moves"}},
        {{"type": "threat", "text": "Threat this company poses to Flex"}},
        {{"type": "strength", "text": "Strength Flex could leverage"}},
        {{"type": "weakness", "text": "Weakness Flex could exploit"}}
    ],
    
    "bottom_line": "2-3 sentence summary of what this analysis means for competitive strategy. This is the 'so what' that turns data into actionable intelligence."
}}

Be specific and actionable. This synthesis should help Flex make strategic decisions."""

        system = f"""You are a strategic consultant synthesizing competitive intelligence on {company}.
Always return valid JSON. Be direct and actionable in your recommendations.
The bottom line should be the key insight that matters most for competitive strategy."""

        response = self._query_llm(prompt, system)
        return self._parse_json_response(response)
