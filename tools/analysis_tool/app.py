"""
CapEx Intelligence Analysis Tool
================================
Personal document analysis tool for competitive intelligence gathering.
Uses local LLM (Ollama) for document analysis and generates comprehensive reports.

Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from pathlib import Path
from datetime import datetime
import json

# Import our modules
from document_processor import DocumentProcessor
from llm_analyzer import LLMAnalyzer
from report_generator import ReportGenerator
from visualizations import create_all_visualizations

# Page config
st.set_page_config(
    page_title="CapEx Intelligence Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1e40af;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #64748b;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 1rem;
        color: white;
    }
    .section-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #1e293b;
        border-bottom: 3px solid #3b82f6;
        padding-bottom: 0.5rem;
        margin-top: 2rem;
    }
    .insight-box {
        background: #f0f9ff;
        border-left: 4px solid #0284c7;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 0.5rem 0.5rem 0;
    }
    .warning-box {
        background: #fef3c7;
        border-left: 4px solid #f59e0b;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 0.5rem 0.5rem 0;
    }
    .success-box {
        background: #d1fae5;
        border-left: 4px solid #10b981;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 0.5rem 0.5rem 0;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = {}
if 'selected_company' not in st.session_state:
    st.session_state.selected_company = None
if 'documents_loaded' not in st.session_state:
    st.session_state.documents_loaded = False

# Company configurations
COMPANIES = {
    "Flex": {"symbol": "FLEX", "color": "#3b82f6", "folder": "Flex"},
    "Jabil": {"symbol": "JBL", "color": "#10b981", "folder": "Jabil"},
    "Celestica": {"symbol": "CLS", "color": "#8b5cf6", "folder": "Celestica/Celestica"},
    "Benchmark": {"symbol": "BHE", "color": "#f59e0b", "folder": "Benchmark"},
    "Sanmina": {"symbol": "SANM", "color": "#ef4444", "folder": "Sanmina"}
}

# Data directory (raw company documents)
_project_root = Path(__file__).parent.parent.parent
_raw_data_dir = _project_root / "data" / "raw"

DATA_DIR = _raw_data_dir if _raw_data_dir.exists() else _project_root


def main():
    # Header
    st.markdown('<p class="main-header">📊 CapEx Intelligence Analyzer</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Deep competitive intelligence from SEC filings, earnings calls, and investor presentations</p>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/combo-chart.png", width=80)
        st.markdown("### 🎯 Analysis Settings")
        
        # Company selection
        selected_company = st.selectbox(
            "Select Company",
            options=list(COMPANIES.keys()),
            index=0
        )
        st.session_state.selected_company = selected_company
        
        st.divider()
        
        # Analysis sections to run
        st.markdown("### 📋 Analysis Sections")
        sections = {
            "financial_context": st.checkbox("💰 Financial Context", value=True),
            "capex_breakdown": st.checkbox("📊 CapEx Breakdown", value=True),
            "strategic_initiatives": st.checkbox("🎯 Strategic Initiatives", value=True),
            "competitive_positioning": st.checkbox("🏆 Competitive Positioning", value=True),
            "risk_factors": st.checkbox("⚠️ Risk Factors", value=True),
            "forward_guidance": st.checkbox("🔮 Forward Guidance", value=True),
            "earnings_analysis": st.checkbox("📞 Earnings Call Analysis", value=True)
        }
        
        st.divider()
        
        # LLM Settings
        st.markdown("### 🤖 LLM Settings")
        
        # Mode selection
        analysis_mode = st.radio(
            "Analysis Mode",
            options=["🎯 Demo (Instant)", "⚡ Quick (1-2 min)", "📊 Full (5-10 min)"],
            index=0,
            help="Demo shows sample data instantly"
        )
        
        quick_mode = analysis_mode != "📊 Full (5-10 min)"
        demo_mode = analysis_mode == "🎯 Demo (Instant)"
        
        if not demo_mode:
            llm_model = st.selectbox(
                "Ollama Model",
                options=["phi3", "mistral", "llama3"],
                index=0
            )
        else:
            llm_model = "phi3"
        
        temperature = 0.1
        
        st.divider()
        
        # Run analysis button
        if st.button("🚀 Run Analysis", type="primary", use_container_width=True):
            if demo_mode:
                load_demo_data(selected_company)
            else:
                run_analysis(selected_company, sections, llm_model, temperature, quick_mode)
        
        st.divider()
        
        # Export options
        st.markdown("### 📥 Export Reports")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📝 MD"):
                export_markdown()
        with col2:
            if st.button("🌐 HTML"):
                export_html()
        with col3:
            if st.button("📄 PDF"):
                export_pdf()
    
    # Main content area
    if st.session_state.selected_company and st.session_state.analysis_results.get(st.session_state.selected_company):
        display_analysis_results()
    else:
        display_welcome_screen()


def load_demo_data(company: str):
    """Load sample demo data instantly without LLM"""
    
    # Sample data based on real industry patterns
    demo_results = {
        "financial_context": {
            "yearly_metrics": [
                {"Year": "FY22", "Revenue": "$6.5B", "CapEx": "$180M", "CapEx_Revenue_Pct": "2.8%"},
                {"Year": "FY23", "Revenue": "$7.2B", "CapEx": "$220M", "CapEx_Revenue_Pct": "3.1%"},
                {"Year": "FY24", "Revenue": "$8.5B", "CapEx": "$310M", "CapEx_Revenue_Pct": "3.6%"},
                {"Year": "FY25", "Revenue": "$9.8B", "CapEx": "$420M", "CapEx_Revenue_Pct": "4.3%"},
            ],
            "cash_flow": [
                {"Year": "FY23", "Operating_Cash_Flow": "$450M", "CapEx": "$220M", "Free_Cash_Flow": "$230M"},
                {"Year": "FY24", "Operating_Cash_Flow": "$520M", "CapEx": "$310M", "Free_Cash_Flow": "$210M"},
                {"Year": "FY25", "Operating_Cash_Flow": "$610M", "CapEx": "$420M", "Free_Cash_Flow": "$190M"},
            ],
            "latest_revenue": "$9.8B",
            "revenue_growth": "+15%",
            "capex_ratio": "4.3%",
            "ratio_change": "+0.7%",
            "insights": [
                "CapEx growing faster than revenue - increasing capital intensity",
                "Free cash flow declining as investment ramps up",
                "Strong revenue growth driven by AI/data center demand"
            ]
        },
        "capex_breakdown": {
            "total_capex": "$420M",
            "capex_growth": "+35%",
            "ai_percentage": "38%",
            "ai_change": "+12%",
            "by_type": [
                {"Category": "AI/Data Center", "Amount": "$160M", "Percentage": "38%"},
                {"Category": "Equipment/Machinery", "Amount": "$120M", "Percentage": "29%"},
                {"Category": "Facility Expansion", "Amount": "$80M", "Percentage": "19%"},
                {"Category": "IT/Automation", "Amount": "$40M", "Percentage": "9%"},
                {"Category": "Maintenance", "Amount": "$20M", "Percentage": "5%"},
            ],
            "by_geography": [
                {"Region": "North America", "CapEx": "$150M", "Percentage": "36%", "Key_Projects": "Austin liquid cooling facility"},
                {"Region": "Mexico", "CapEx": "$100M", "Percentage": "24%", "Key_Projects": "Guadalajara expansion"},
                {"Region": "Asia Pacific", "CapEx": "$120M", "Percentage": "28%", "Key_Projects": "Malaysia HPC center"},
                {"Region": "Europe", "CapEx": "$50M", "Percentage": "12%", "Key_Projects": "Ireland data center"},
            ],
            "ai_traditional": {
                "ai": 160,
                "traditional": 260,
                "ai_pct": 38
            },
            "breakdown": [
                {"Category": "AI/Data Center", "Amount": 160},
                {"Category": "Traditional", "Amount": 260}
            ]
        },
        "strategic_initiatives": {
            "projects": [
                {"Project Name": "Austin Liquid Cooling", "Location": "Austin, TX", "Investment": "$85M", "Start Date": "Q1 FY24", "Completion": "Q3 FY25", "Purpose": "AI data center cooling"},
                {"Project Name": "Guadalajara Expansion", "Location": "Mexico", "Investment": "$65M", "Start Date": "Q2 FY24", "Completion": "Q4 FY25", "Purpose": "Nearshoring capacity"},
                {"Project Name": "Malaysia HPC Center", "Location": "Penang, Malaysia", "Investment": "$45M", "Start Date": "Q3 FY24", "Completion": "Q2 FY26", "Purpose": "High-performance computing"},
            ],
            "technology": [
                {"type": "Automation", "description": "Industry 4.0 smart factory upgrades across 12 facilities", "amount": "$25M"},
                {"type": "AI Manufacturing", "description": "AI-powered quality control and predictive maintenance", "amount": "$15M"},
            ],
            "esg": [
                {"initiative": "Solar Installation", "details": "50MW solar capacity across North American facilities", "investment": "$20M"},
                {"initiative": "Water Recycling", "details": "Closed-loop cooling systems for data center operations", "investment": "$8M"},
            ],
            "esg_total": "$28M"
        },
        "competitive_positioning": {
            "customers": [
                {"Customer": "Hyperscale Cloud Provider A", "Revenue %": "18%", "Notes": "Major AI infrastructure partner"},
                {"Customer": "Enterprise Tech Company B", "Revenue %": "12%", "Notes": "Server and networking"},
                {"Customer": "Automotive OEM C", "Revenue %": "8%", "Notes": "EV components"},
                {"Customer": "Medical Device Co D", "Revenue %": "6%", "Notes": "Precision manufacturing"},
            ],
            "benchmarking": [
                {"Company": company, "CapEx/Revenue": 65, "AI Investment": 70, "Growth Rate": 75, "FCF Margin": 45, "ROIC": 55},
            ],
            "competitive_advantages": [
                "Leading liquid cooling manufacturing capability",
                "Strong hyperscale customer relationships",
                "Diversified geographic footprint"
            ],
            "competitive_threats": [
                "Asian competitors with lower labor costs",
                "Customer concentration risk with top 2 accounts",
                "Potential AI spending slowdown"
            ]
        },
        "risk_factors": {
            "supply_chain": [
                {"risk": "GPU Supply Constraints", "description": "Limited availability of AI accelerators affects delivery timelines", "severity": "high", "mitigation": "Multi-vendor sourcing strategy"},
                {"risk": "Specialty Components", "description": "Long lead times for liquid cooling components", "severity": "medium", "mitigation": "Inventory buffers"},
            ],
            "geopolitical": [
                {"risk": "China Operations", "description": "15% of revenue from China facilities facing trade tensions", "severity": "medium", "mitigation": "Nearshoring to Mexico"},
                {"risk": "Tariff Exposure", "description": "Potential new tariffs on electronics manufacturing", "severity": "low", "mitigation": "Geographic diversification"},
            ],
            "risk_matrix": [
                {"Risk": "AI Demand Slowdown", "Category": "Market", "Likelihood": 40, "Impact": 80, "Score": 32},
                {"Risk": "Customer Concentration", "Category": "Business", "Likelihood": 60, "Impact": 70, "Score": 42},
                {"Risk": "Supply Chain Disruption", "Category": "Operational", "Likelihood": 50, "Impact": 60, "Score": 30},
                {"Risk": "Geopolitical Tensions", "Category": "External", "Likelihood": 45, "Impact": 55, "Score": 25},
            ],
            "red_flags": [
                {"flag": "CapEx outpacing FCF", "explanation": "Free cash flow declining while CapEx increases - monitor cash reserves"},
            ]
        },
        "forward_guidance": {
            "capex_guidance": [
                {"Period": "FY25", "Low": 400, "High": 450, "Midpoint": 425, "Range": 50, "Notes": "Current year"},
                {"Period": "FY26", "Low": 480, "High": 550, "Midpoint": 515, "Range": 70, "Notes": "Preliminary estimate"},
            ],
            "pipeline": [
                {"Project": "Phase 2 Austin Expansion", "Status": "Planning", "Expected CapEx": "$60M", "Start Date": "H1 FY26"},
                {"Project": "Vietnam New Facility", "Status": "Under Review", "Expected CapEx": "$100M", "Start Date": "FY27"},
            ],
            "quotes": [
                {"text": "We expect AI-related investments to represent 40-45% of total CapEx in FY26, up from 38% this year.", "speaker": "CFO", "context": "Q3 FY25 Earnings Call"},
                {"text": "Our liquid cooling capacity investments are seeing strong demand signals from hyperscale customers.", "speaker": "CEO", "context": "Investor Day 2025"},
            ],
            "roic": {"target": "15%", "current": "12.5%", "gap": "-2.5%"},
            "key_themes": [
                "Accelerating AI infrastructure investment",
                "Nearshoring to Mexico continues",
                "Focus on higher-margin data center business"
            ]
        },
        "synthesis": {
            "thesis": {
                "classification": "Aggressive Growth",
                "description": f"{company} is betting heavily on AI/data center infrastructure with 38% of CapEx allocated to this segment. The company is prioritizing market share in high-growth areas over near-term cash flow, positioning for sustained demand from hyperscale customers."
            },
            "positioning": [
                {"dimension": "AI/Data Center Focus", "assessment": "Leader - 38% of CapEx to AI (vs industry avg 20%)"},
                {"dimension": "Geographic Strategy", "assessment": "Nearshoring - Heavy Mexico investment for US market access"},
                {"dimension": "Competitive Advantage", "assessment": "Technology - Leading in liquid cooling manufacturing"},
            ],
            "risk_profile": {
                "level": "Medium",
                "explanation": "Strong customer concentration (30% in top 2 accounts) and aggressive CapEx expansion create execution risk, but diversified geography and growing AI demand provide balance."
            },
            "key_findings": [
                f"{company} allocating 38% of CapEx to AI/data center - highest in peer group",
                "Free cash flow declining as investment ramps up - $190M in FY25 vs $230M in FY23",
                "Mexico nearshoring accelerating with $100M+ investment",
                "Liquid cooling capability is key differentiator for hyperscale customers",
                "Customer concentration risk: top 2 customers = 30% of revenue"
            ],
            "recommendations": [
                {"type": "opportunity", "text": f"Flex should monitor {company}'s liquid cooling expansion - potential partnership or competitive response needed"},
                {"type": "threat", "text": f"{company}'s aggressive AI investment could capture market share in hyperscale segment"},
                {"type": "strength", "text": f"Flex's more diversified portfolio provides stability if AI spending slows"},
                {"type": "weakness", "text": f"{company}'s lower labor costs in Mexico could pressure Flex's North American margins"},
            ],
            "bottom_line": f"{company} is making a strategic bet on AI infrastructure with 38% CapEx allocation, driven by hyperscale customer demand. While this creates concentration risk, their liquid cooling capabilities and nearshoring strategy position them well for continued growth. Flex should consider accelerating its own AI infrastructure investments to remain competitive."
        }
    }
    
    st.session_state.analysis_results[company] = demo_results
    st.success(f"✅ Demo data loaded for {company}!")
    st.rerun()


def display_welcome_screen():
    """Display welcome screen with instructions"""
    st.markdown("---")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 👋 Welcome to the CapEx Intelligence Analyzer")
        st.markdown("""
        This tool analyzes company documents to extract competitive intelligence following a comprehensive framework:
        
        **📊 What it analyzes:**
        - SEC Filings (10-K, 10-Q, 8-K)
        - Earnings Call Transcripts
        - Investor Presentations
        - Press Releases
        
        **🎯 What you get:**
        - Financial metrics & ratios
        - CapEx breakdown by type, geography, segment
        - Strategic initiative tracking
        - Competitive positioning insights
        - Risk factor analysis
        - Forward-looking guidance
        
        **🚀 To get started:**
        1. Select a company from the sidebar
        2. Choose which analysis sections to run
        3. Click "Run Analysis"
        """)
    
    with col2:
        st.markdown("### 📁 Available Data")
        for company, info in COMPANIES.items():
            folder_path = DATA_DIR / info["folder"]
            if folder_path.exists():
                file_count = sum(1 for _ in folder_path.rglob("*") if _.is_file())
                st.success(f"✅ **{company}**: {file_count} files")
            else:
                st.error(f"❌ **{company}**: No data found")
    
    # Sample visualizations
    st.markdown("---")
    st.markdown("### 📈 Sample Analysis Preview")
    
    # Create sample data for preview
    sample_data = pd.DataFrame({
        'Company': ['Flex', 'Jabil', 'Celestica', 'Benchmark', 'Sanmina'],
        'CapEx ($M)': [1300, 700, 200, 150, 250],
        'AI Investment %': [35, 20, 25, 15, 18],
        'Revenue ($B)': [25, 30, 8, 3, 7]
    })
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        fig = px.bar(sample_data, x='Company', y='CapEx ($M)', 
                     color='Company', title="CapEx by Company")
        fig.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = px.pie(sample_data, values='CapEx ($M)', names='Company',
                     title="CapEx Distribution", hole=0.4)
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    
    with col3:
        fig = px.scatter(sample_data, x='Revenue ($B)', y='AI Investment %',
                        size='CapEx ($M)', color='Company',
                        title="AI Investment vs Revenue")
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)


def run_analysis(company: str, sections: dict, model: str, temperature: float, quick_mode: bool = True):
    """Run the full analysis pipeline"""
    
    st.markdown("---")
    mode_text = "⚡ Quick" if quick_mode else "📊 Full"
    st.markdown(f"### 🔄 {mode_text} Analysis: {company}")
    
    progress = st.progress(0)
    status = st.empty()
    time_display = st.empty()
    
    import time
    start_time = time.time()
    
    try:
        # Initialize processors
        status.text("📂 Loading documents...")
        progress.progress(10)
        
        doc_processor = DocumentProcessor(DATA_DIR / COMPANIES[company]["folder"])
        documents = doc_processor.load_all_documents()
        
        # In quick mode, limit documents
        if quick_mode and len(documents) > 10:
            # Prioritize 10-K and earnings calls
            priority_docs = [d for d in documents if d.doc_type in ["10-K", "earnings_call"]]
            other_docs = [d for d in documents if d.doc_type not in ["10-K", "earnings_call"]]
            documents = priority_docs[:6] + other_docs[:4]
            status.text(f"⚡ Quick mode: Using {len(documents)} key documents")
        else:
            status.text(f"📄 Loaded {len(documents)} documents")
        
        progress.progress(20)
        time_display.text(f"⏱️ Elapsed: {time.time() - start_time:.0f}s")
        
        # Initialize LLM analyzer
        status.text("🤖 Initializing LLM...")
        progress.progress(30)
        time_display.text(f"⏱️ Elapsed: {time.time() - start_time:.0f}s")
        
        analyzer = LLMAnalyzer(model=model, temperature=temperature, quick_mode=quick_mode)
        
        # Run each selected section
        results = {}
        section_progress = 30
        section_increment = 60 / sum(sections.values())
        
        if sections.get("financial_context"):
            status.text("💰 Analyzing financial context...")
            results["financial_context"] = analyzer.analyze_financial_context(documents)
            section_progress += section_increment
            progress.progress(int(section_progress))
        
        if sections.get("capex_breakdown"):
            status.text("📊 Breaking down CapEx...")
            results["capex_breakdown"] = analyzer.analyze_capex_breakdown(documents)
            section_progress += section_increment
            progress.progress(int(section_progress))
        
        if sections.get("strategic_initiatives"):
            status.text("🎯 Identifying strategic initiatives...")
            results["strategic_initiatives"] = analyzer.analyze_strategic_initiatives(documents)
            section_progress += section_increment
            progress.progress(int(section_progress))
        
        if sections.get("competitive_positioning"):
            status.text("🏆 Analyzing competitive position...")
            results["competitive_positioning"] = analyzer.analyze_competitive_positioning(documents)
            section_progress += section_increment
            progress.progress(int(section_progress))
        
        if sections.get("risk_factors"):
            status.text("⚠️ Extracting risk factors...")
            results["risk_factors"] = analyzer.analyze_risk_factors(documents)
            section_progress += section_increment
            progress.progress(int(section_progress))
        
        if sections.get("forward_guidance"):
            status.text("🔮 Analyzing forward guidance...")
            results["forward_guidance"] = analyzer.analyze_forward_guidance(documents)
            section_progress += section_increment
            progress.progress(int(section_progress))
        
        if sections.get("earnings_analysis"):
            status.text("📞 Analyzing earnings calls...")
            results["earnings_analysis"] = analyzer.analyze_earnings_calls(documents)
            section_progress += section_increment
            progress.progress(int(section_progress))
        
        # Generate synthesis
        status.text("🧠 Generating synthesis...")
        results["synthesis"] = analyzer.generate_synthesis(results, company)
        progress.progress(95)
        
        # Store results
        st.session_state.analysis_results[company] = results
        st.session_state.documents_loaded = True
        
        progress.progress(100)
        status.text("✅ Analysis complete!")
        
        st.success(f"✅ Successfully analyzed {company}!")
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ Error during analysis: {str(e)}")
        st.exception(e)


def display_analysis_results():
    """Display the analysis results with visualizations"""
    
    company = st.session_state.selected_company
    results = st.session_state.analysis_results.get(company, {})
    
    if not results:
        st.warning("No analysis results available. Run analysis first.")
        return
    
    # Company header
    info = COMPANIES[company]
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {info['color']}20 0%, {info['color']}10 100%); 
                padding: 1.5rem; border-radius: 1rem; border-left: 5px solid {info['color']};">
        <h2 style="margin: 0; color: {info['color']};">{company} ({info['symbol']})</h2>
        <p style="margin: 0.5rem 0 0 0; color: #64748b;">Analysis generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Tabs for different sections
    tabs = st.tabs([
        "📊 Overview",
        "💰 Financial",
        "📈 CapEx",
        "🎯 Strategy",
        "🏆 Competition",
        "⚠️ Risks",
        "🔮 Outlook",
        "💡 Insights"
    ])
    
    # Tab 1: Overview
    with tabs[0]:
        display_overview(company, results)
    
    # Tab 2: Financial Context
    with tabs[1]:
        display_financial_context(results.get("financial_context", {}))
    
    # Tab 3: CapEx Breakdown
    with tabs[2]:
        display_capex_breakdown(results.get("capex_breakdown", {}))
    
    # Tab 4: Strategic Initiatives
    with tabs[3]:
        display_strategic_initiatives(results.get("strategic_initiatives", {}))
    
    # Tab 5: Competitive Positioning
    with tabs[4]:
        display_competitive_positioning(results.get("competitive_positioning", {}))
    
    # Tab 6: Risk Factors
    with tabs[5]:
        display_risk_factors(results.get("risk_factors", {}))
    
    # Tab 7: Forward Guidance
    with tabs[6]:
        display_forward_guidance(results.get("forward_guidance", {}))
    
    # Tab 8: Synthesis & Insights
    with tabs[7]:
        display_synthesis(results.get("synthesis", {}))


def display_overview(company: str, results: dict):
    """Display overview dashboard"""
    
    st.markdown('<p class="section-header">📊 Executive Summary</p>', unsafe_allow_html=True)
    
    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    financial = results.get("financial_context", {})
    capex = results.get("capex_breakdown", {})
    
    with col1:
        st.metric(
            label="Total Revenue",
            value=financial.get("latest_revenue", "N/A"),
            delta=financial.get("revenue_growth", None)
        )
    
    with col2:
        st.metric(
            label="CapEx (Latest)",
            value=capex.get("total_capex", "N/A"),
            delta=capex.get("capex_growth", None)
        )
    
    with col3:
        st.metric(
            label="AI Investment %",
            value=capex.get("ai_percentage", "N/A"),
            delta=capex.get("ai_change", None)
        )
    
    with col4:
        st.metric(
            label="CapEx/Revenue",
            value=financial.get("capex_ratio", "N/A"),
            delta=financial.get("ratio_change", None)
        )
    
    st.markdown("---")
    
    # Charts row
    col1, col2 = st.columns(2)
    
    with col1:
        # CapEx trend chart
        if "yearly_data" in financial:
            df = pd.DataFrame(financial["yearly_data"])
            fig = px.area(df, x='Year', y='CapEx', title="CapEx Trend Over Time",
                         color_discrete_sequence=[COMPANIES[company]["color"]])
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("CapEx trend data not available")
    
    with col2:
        # Investment breakdown pie
        if "breakdown" in capex:
            df = pd.DataFrame(capex["breakdown"])
            fig = px.pie(df, values='Amount', names='Category', 
                        title="CapEx Breakdown by Category", hole=0.4)
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("CapEx breakdown data not available")
    
    # Key findings
    st.markdown('<p class="section-header">🔑 Key Findings</p>', unsafe_allow_html=True)
    
    synthesis = results.get("synthesis", {})
    if synthesis.get("key_findings"):
        for i, finding in enumerate(synthesis["key_findings"][:5], 1):
            st.markdown(f"""
            <div class="insight-box">
                <strong>Finding {i}:</strong> {finding}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("Run analysis to generate key findings")


def display_financial_context(data: dict):
    """Display financial context analysis"""
    
    st.markdown('<p class="section-header">💰 Financial Context</p>', unsafe_allow_html=True)
    
    if not data:
        st.info("Financial context analysis not available. Run analysis first.")
        return
    
    try:
        # Revenue & Profitability table
        st.markdown("### Revenue & Profitability")
        
        if "yearly_metrics" in data:
            df = pd.DataFrame(data["yearly_metrics"])
            st.dataframe(df, use_container_width=True)
            
            # Visualization
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Parse revenue values
            if 'Revenue' in df.columns:
                df['Revenue_Val'] = df['Revenue'].apply(lambda x: float(str(x).replace('$', '').replace('B', '').replace('M', '')) if pd.notna(x) else 0)
                fig.add_trace(
                    go.Bar(x=df['Year'], y=df['Revenue_Val'], name="Revenue", marker_color='#3b82f6'),
                    secondary_y=False
                )
            
            # Handle different column names for ratio
            ratio_col = 'CapEx/Revenue' if 'CapEx/Revenue' in df.columns else 'CapEx_Revenue_Pct'
            if ratio_col in df.columns:
                df['Ratio'] = df[ratio_col].apply(lambda x: float(str(x).replace('%', '')) if pd.notna(x) else 0)
                fig.add_trace(
                    go.Scatter(x=df['Year'], y=df['Ratio'], name="CapEx/Revenue %", 
                              line=dict(color='#ef4444', width=3)),
                    secondary_y=True
                )
            fig.update_layout(title="Revenue vs CapEx Intensity", height=400)
            fig.update_yaxes(title_text="Revenue ($B)", secondary_y=False)
            fig.update_yaxes(title_text="CapEx/Revenue (%)", secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)
        
        # Cash Flow Health
        st.markdown("### Cash Flow Health")
        
        if "cash_flow" in data:
            col1, col2 = st.columns(2)
            
            with col1:
                cf_df = pd.DataFrame(data["cash_flow"])
                st.dataframe(cf_df, use_container_width=True)
            
            with col2:
                if len(cf_df) > 0:
                    # Use available columns
                    available_cols = [c for c in ['Operating_Cash_Flow', 'CapEx', 'Free_Cash_Flow'] if c in cf_df.columns]
                    if available_cols:
                        fig = px.bar(cf_df, x='Year', y=available_cols,
                                    title="Cash Flow Components", barmode='group')
                        fig.update_layout(height=350)
                        st.plotly_chart(fig, use_container_width=True)
        
        # Analysis insights
        if "insights" in data:
            st.markdown("### 💡 Financial Insights")
            for insight in data["insights"]:
                st.markdown(f"""
                <div class="insight-box">{insight}</div>
                """, unsafe_allow_html=True)
    
    except Exception as e:
        st.error(f"Error displaying financial data: {str(e)}")


def display_capex_breakdown(data: dict):
    """Display CapEx breakdown analysis"""
    
    st.markdown('<p class="section-header">📈 CapEx Breakdown</p>', unsafe_allow_html=True)
    
    if not data:
        st.info("CapEx breakdown analysis not available. Run analysis first.")
        return
    
    col1, col2 = st.columns(2)
    
    # By Type
    with col1:
        st.markdown("### By Category/Type")
        if "by_type" in data:
            df = pd.DataFrame(data["by_type"])
            fig = px.pie(df, values='Amount', names='Category', hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Set2)
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df, use_container_width=True)
    
    # By Geography
    with col2:
        st.markdown("### By Geography")
        if "by_geography" in data:
            df = pd.DataFrame(data["by_geography"])
            fig = px.bar(df, x='Region', y='CapEx', color='Region',
                        color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df, use_container_width=True)
    
    # By Segment
    st.markdown("### By Customer Segment")
    if "by_segment" in data:
        df = pd.DataFrame(data["by_segment"])
        # Handle missing color column
        color_col = 'CapEx/Revenue' if 'CapEx/Revenue' in df.columns else None
        fig = px.treemap(df, path=['Segment'], values='CapEx',
                        color=color_col, color_continuous_scale='Blues' if color_col else None,
                        title="CapEx by Segment")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    # AI vs Traditional
    st.markdown("### AI/Data Center vs Traditional")
    if "ai_traditional" in data:
        ai_data = data["ai_traditional"]
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            fig = go.Figure(go.Pie(
                labels=['AI/Data Center', 'Traditional'],
                values=[ai_data.get('ai', 0), ai_data.get('traditional', 0)],
                hole=0.6,
                marker_colors=['#3b82f6', '#94a3b8']
            ))
            fig.update_layout(
                title="Investment Split",
                annotations=[dict(text=f"{ai_data.get('ai_pct', 0):.0f}%<br>AI", 
                                 x=0.5, y=0.5, font_size=20, showarrow=False)],
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)


def display_strategic_initiatives(data: dict):
    """Display strategic initiatives analysis"""
    
    st.markdown('<p class="section-header">🎯 Strategic Initiatives</p>', unsafe_allow_html=True)
    
    if not data:
        st.info("Strategic initiatives analysis not available. Run analysis first.")
        return
    
    try:
        # Major Projects
        st.markdown("### 🏗️ Major Facility Projects")
        if "projects" in data:
            projects_df = pd.DataFrame(data["projects"])
            st.dataframe(projects_df, use_container_width=True)
            
            # Bar chart for project investments
            if len(projects_df) > 0 and 'Project Name' in projects_df.columns and 'Investment' in projects_df.columns:
                # Parse investment values
                projects_df['Investment_Val'] = projects_df['Investment'].apply(
                    lambda x: float(str(x).replace('$', '').replace('M', '').replace('B', '')) if pd.notna(x) else 0
                )
                fig = px.bar(projects_df, x='Project Name', y='Investment_Val', 
                            color='Purpose' if 'Purpose' in projects_df.columns else None,
                            title="Project Investments ($M)")
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
        
        # Technology Investments
        st.markdown("### 🤖 Technology & Automation Investments")
        if "technology" in data:
            for item in data["technology"]:
                st.markdown(f"""
                <div class="success-box">
                    <strong>{item.get('type', 'N/A')}:</strong> {item.get('description', 'N/A')}
                    {f"<br><em>Investment: {item['amount']}</em>" if item.get('amount') else ""}
                </div>
                """, unsafe_allow_html=True)
        
        # ESG Investments
        st.markdown("### 🌱 Sustainability & ESG CapEx")
        if "esg" in data:
            col1, col2 = st.columns([2, 1])
            with col1:
                for item in data["esg"]:
                    st.markdown(f"- **{item.get('initiative', 'N/A')}**: {item.get('details', 'N/A')}")
            with col2:
                if data.get("esg_total"):
                    st.metric("Total ESG Investment", data["esg_total"])
    
    except Exception as e:
        st.error(f"Error displaying strategic initiatives: {str(e)}")


def display_competitive_positioning(data: dict):
    """Display competitive positioning analysis"""
    
    st.markdown('<p class="section-header">🏆 Competitive Positioning</p>', unsafe_allow_html=True)
    
    if not data:
        st.info("Competitive positioning analysis not available. Run analysis first.")
        return
    
    # Customer Concentration
    st.markdown("### 👥 Customer Concentration")
    if "customers" in data:
        df = pd.DataFrame(data["customers"])
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.dataframe(df, use_container_width=True)
        
        with col2:
            fig = px.pie(df, values='Revenue %', names='Customer',
                        title="Revenue Concentration")
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)
    
    # Competitor Comparison
    st.markdown("### 📊 Peer Benchmarking")
    if "benchmarking" in data:
        df = pd.DataFrame(data["benchmarking"])
        
        # Radar chart
        categories = ['CapEx/Revenue', 'AI Investment', 'Growth Rate', 'FCF Margin', 'ROIC']
        fig = go.Figure()
        
        for _, row in df.iterrows():
            fig.add_trace(go.Scatterpolar(
                r=[row.get(cat, 0) for cat in categories],
                theta=categories,
                name=row['Company']
            ))
        
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            showlegend=True,
            title="Competitive Positioning Radar",
            height=500
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.dataframe(df, use_container_width=True)
    
    # Market Share
    if "market_share" in data:
        st.markdown("### 📈 Market Share & TAM")
        df = pd.DataFrame(data["market_share"])
        fig = px.bar(df, x='Market', y='Share %', color='Growth Rate',
                    title="Market Share by Segment")
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)


def display_risk_factors(data: dict):
    """Display risk factors analysis"""
    
    st.markdown('<p class="section-header">⚠️ Risk Factors</p>', unsafe_allow_html=True)
    
    if not data:
        st.info("Risk factors analysis not available. Run analysis first.")
        return
    
    col1, col2 = st.columns(2)
    
    # Supply Chain Risks
    with col1:
        st.markdown("### 🔗 Supply Chain Risks")
        if "supply_chain" in data:
            for risk in data["supply_chain"]:
                severity = risk.get("severity", "medium")
                box_class = "warning-box" if severity == "high" else "insight-box"
                st.markdown(f"""
                <div class="{box_class}">
                    <strong>{risk['risk']}:</strong> {risk['description']}
                </div>
                """, unsafe_allow_html=True)
    
    # Geopolitical Risks
    with col2:
        st.markdown("### 🌍 Geopolitical Risks")
        if "geopolitical" in data:
            for risk in data["geopolitical"]:
                severity = risk.get("severity", "medium")
                box_class = "warning-box" if severity == "high" else "insight-box"
                st.markdown(f"""
                <div class="{box_class}">
                    <strong>{risk['risk']}:</strong> {risk['description']}
                </div>
                """, unsafe_allow_html=True)
    
    # Risk Matrix
    st.markdown("### 📊 Risk Assessment Matrix")
    if "risk_matrix" in data:
        df = pd.DataFrame(data["risk_matrix"])
        fig = px.scatter(df, x='Likelihood', y='Impact', size='Score',
                        color='Category', text='Risk',
                        title="Risk Matrix (Likelihood vs Impact)")
        fig.update_traces(textposition='top center')
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)
    
    # Red Flags
    st.markdown("### 🚩 Red Flags & Anomalies")
    if "red_flags" in data:
        for flag in data["red_flags"]:
            st.markdown(f"""
            <div class="warning-box">
                <strong>🚩 {flag['flag']}:</strong> {flag['explanation']}
            </div>
            """, unsafe_allow_html=True)


def display_forward_guidance(data: dict):
    """Display forward guidance analysis"""
    
    st.markdown('<p class="section-header">🔮 Forward Guidance</p>', unsafe_allow_html=True)
    
    if not data:
        st.info("Forward guidance analysis not available. Run analysis first.")
        return
    
    # CapEx Guidance
    st.markdown("### 📊 CapEx Guidance")
    if "capex_guidance" in data:
        df = pd.DataFrame(data["capex_guidance"])
        
        col1, col2 = st.columns([2, 1])
        with col1:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df['Period'], y=df['Midpoint'],
                error_y=dict(type='data', array=df['Range']/2),
                marker_color='#3b82f6'
            ))
            fig.update_layout(title="Guided CapEx Forecast", height=350)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.dataframe(df, use_container_width=True)
    
    # Project Pipeline
    st.markdown("### 🏗️ Project Pipeline")
    if "pipeline" in data:
        df = pd.DataFrame(data["pipeline"])
        st.dataframe(df, use_container_width=True)
    
    # Management Quotes
    st.markdown("### 💬 Key Management Quotes")
    if "quotes" in data:
        for quote in data["quotes"]:
            st.markdown(f"""
            <div class="insight-box">
                <em>"{quote['text']}"</em>
                <br><strong>— {quote['speaker']}, {quote['context']}</strong>
            </div>
            """, unsafe_allow_html=True)
    
    # ROIC Targets
    if "roic" in data:
        st.markdown("### 📈 Return on Invested Capital")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Target ROIC", data["roic"].get("target", "N/A"))
        with col2:
            st.metric("Current ROIC", data["roic"].get("current", "N/A"))
        with col3:
            st.metric("Gap", data["roic"].get("gap", "N/A"))


def display_synthesis(data: dict):
    """Display synthesis and insights"""
    
    st.markdown('<p class="section-header">💡 Synthesis & Recommendations</p>', unsafe_allow_html=True)
    
    if not data:
        st.info("Synthesis not available. Run analysis first.")
        return
    
    # Investment Thesis
    st.markdown("### 📌 Investment Thesis")
    if "thesis" in data:
        thesis = data["thesis"]
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #667eea20 0%, #764ba220 100%); 
                    padding: 2rem; border-radius: 1rem; border: 2px solid #667eea;">
            <h4 style="margin: 0 0 1rem 0;">Classification: {thesis.get('classification', 'N/A')}</h4>
            <p style="margin: 0; font-size: 1.1rem;">{thesis.get('description', '')}</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Strategic Position
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🎯 Strategic Positioning")
        if "positioning" in data:
            for item in data["positioning"]:
                st.markdown(f"- **{item['dimension']}:** {item['assessment']}")
    
    with col2:
        st.markdown("### ⚖️ Risk Profile")
        if "risk_profile" in data:
            risk = data["risk_profile"]
            color = {"Low": "#10b981", "Medium": "#f59e0b", "High": "#ef4444"}.get(risk.get("level", "Medium"), "#64748b")
            st.markdown(f"""
            <div style="background: {color}20; border-left: 5px solid {color}; padding: 1rem; border-radius: 0 0.5rem 0.5rem 0;">
                <h4 style="margin: 0; color: {color};">Risk Level: {risk.get('level', 'N/A')}</h4>
                <p style="margin: 0.5rem 0 0 0;">{risk.get('explanation', '')}</p>
            </div>
            """, unsafe_allow_html=True)
    
    # Recommendations
    st.markdown("### 💼 Recommendations for Flex")
    if "recommendations" in data:
        for i, rec in enumerate(data["recommendations"], 1):
            rec_type = rec.get("type", "insight")
            icon = {"opportunity": "🟢", "threat": "🔴", "strength": "🔵", "weakness": "🟡"}.get(rec_type, "💡")
            st.markdown(f"""
            <div class="success-box">
                <strong>{icon} {rec_type.title()} {i}:</strong> {rec['text']}
            </div>
            """, unsafe_allow_html=True)
    
    # The Bottom Line
    st.markdown("### 📝 The Bottom Line")
    if "bottom_line" in data:
        st.markdown(f"""
        <div style="background: #1e293b; color: white; padding: 2rem; border-radius: 1rem;">
            <p style="margin: 0; font-size: 1.1rem; line-height: 1.6;">{data['bottom_line']}</p>
        </div>
        """, unsafe_allow_html=True)


def export_markdown():
    """Export analysis to Markdown"""
    if not st.session_state.analysis_results:
        st.warning("No analysis to export")
        return
    
    generator = ReportGenerator()
    for company, results in st.session_state.analysis_results.items():
        md_content = generator.to_markdown(company, results)
        filename = f"{company}_analysis_{datetime.now().strftime('%Y%m%d')}.md"
        
        st.download_button(
            label=f"📥 Download {company} Report (MD)",
            data=md_content,
            file_name=filename,
            mime="text/markdown"
        )


def export_html():
    """Export analysis to HTML"""
    if not st.session_state.analysis_results:
        st.warning("No analysis to export")
        return
    
    generator = ReportGenerator()
    for company, results in st.session_state.analysis_results.items():
        html_content = generator.to_html(company, results)
        filename = f"{company}_analysis_{datetime.now().strftime('%Y%m%d')}.html"
        
        st.download_button(
            label=f"📥 Download {company} Report (HTML)",
            data=html_content,
            file_name=filename,
            mime="text/html"
        )


def export_pdf():
    """Export analysis to PDF"""
    if not st.session_state.analysis_results:
        st.warning("No analysis to export")
        return
    
    st.info("PDF export requires weasyprint. Install with: pip install weasyprint")
    # PDF generation would go here


if __name__ == "__main__":
    main()
