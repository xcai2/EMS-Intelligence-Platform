"""
Visualizations
==============
Create charts and visualizations for the analysis dashboard.
"""

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from typing import Dict, Any, List, Optional


# Color schemes
COMPANY_COLORS = {
    "Flex": "#3b82f6",
    "Jabil": "#10b981",
    "Celestica": "#8b5cf6",
    "Benchmark": "#f59e0b",
    "Sanmina": "#ef4444"
}

CATEGORY_COLORS = px.colors.qualitative.Set2
AI_TRADITIONAL_COLORS = ["#3b82f6", "#94a3b8"]  # Blue for AI, Gray for traditional


def create_all_visualizations(results: Dict[str, Any], company: str) -> Dict[str, go.Figure]:
    """Create all visualizations for the dashboard"""
    
    figures = {}
    color = COMPANY_COLORS.get(company, "#3b82f6")
    
    # Financial visualizations
    financial = results.get("financial_context", {})
    if financial:
        figures["revenue_trend"] = create_revenue_trend(financial, color)
        figures["capex_ratio"] = create_capex_ratio_chart(financial, color)
        figures["cash_flow"] = create_cash_flow_chart(financial, color)
    
    # CapEx visualizations
    capex = results.get("capex_breakdown", {})
    if capex:
        figures["capex_by_type"] = create_capex_by_type(capex)
        figures["capex_by_geography"] = create_capex_by_geography(capex)
        figures["ai_vs_traditional"] = create_ai_vs_traditional(capex, color)
    
    # Risk visualizations
    risks = results.get("risk_factors", {})
    if risks:
        figures["risk_matrix"] = create_risk_matrix(risks)
    
    # Competitive visualizations
    competitive = results.get("competitive_positioning", {})
    if competitive:
        figures["customer_concentration"] = create_customer_concentration(competitive)
        figures["competitive_radar"] = create_competitive_radar(competitive)
    
    # Guidance visualizations
    guidance = results.get("forward_guidance", {})
    if guidance:
        figures["capex_guidance"] = create_capex_guidance_chart(guidance, color)
    
    return figures


def create_revenue_trend(data: Dict, color: str) -> go.Figure:
    """Create revenue and CapEx trend chart"""
    
    if not data.get("yearly_metrics"):
        return _empty_figure("No yearly metrics data")
    
    df = pd.DataFrame(data["yearly_metrics"])
    
    # Parse numeric values
    for col in ['Revenue', 'CapEx']:
        if col in df.columns:
            df[col] = df[col].apply(_parse_money)
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    if 'Revenue' in df.columns:
        fig.add_trace(
            go.Bar(x=df['Year'], y=df['Revenue'], name="Revenue ($B)", 
                   marker_color=color, opacity=0.7),
            secondary_y=False
        )
    
    if 'CapEx' in df.columns:
        fig.add_trace(
            go.Scatter(x=df['Year'], y=df['CapEx'], name="CapEx ($M)",
                      line=dict(color="#ef4444", width=3), mode='lines+markers'),
            secondary_y=True
        )
    
    fig.update_layout(
        title="Revenue & CapEx Trend",
        height=400,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02)
    )
    fig.update_yaxes(title_text="Revenue ($B)", secondary_y=False)
    fig.update_yaxes(title_text="CapEx ($M)", secondary_y=True)
    
    return fig


def create_capex_ratio_chart(data: Dict, color: str) -> go.Figure:
    """Create CapEx/Revenue ratio chart"""
    
    if not data.get("yearly_metrics"):
        return _empty_figure("No yearly metrics data")
    
    df = pd.DataFrame(data["yearly_metrics"])
    
    if 'CapEx_Revenue_Pct' in df.columns:
        df['Ratio'] = df['CapEx_Revenue_Pct'].apply(lambda x: float(str(x).replace('%', '')) if x != 'N/A' else 0)
    else:
        return _empty_figure("No CapEx/Revenue ratio data")
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df['Year'], y=df['Ratio'],
        mode='lines+markers+text',
        text=[f"{v:.1f}%" for v in df['Ratio']],
        textposition="top center",
        line=dict(color=color, width=3),
        marker=dict(size=12)
    ))
    
    # Add industry average line
    avg = df['Ratio'].mean()
    fig.add_hline(y=avg, line_dash="dash", line_color="#64748b",
                  annotation_text=f"Avg: {avg:.1f}%")
    
    fig.update_layout(
        title="CapEx as % of Revenue",
        height=350,
        yaxis_title="CapEx/Revenue (%)",
        showlegend=False
    )
    
    return fig


def create_cash_flow_chart(data: Dict, color: str) -> go.Figure:
    """Create cash flow waterfall chart"""
    
    if not data.get("cash_flow"):
        return _empty_figure("No cash flow data")
    
    df = pd.DataFrame(data["cash_flow"])
    
    # Parse numeric values
    for col in ['Operating_Cash_Flow', 'CapEx', 'Free_Cash_Flow']:
        if col in df.columns:
            df[col] = df[col].apply(_parse_money)
    
    fig = go.Figure()
    
    if 'Operating_Cash_Flow' in df.columns:
        fig.add_trace(go.Bar(
            x=df['Year'], y=df['Operating_Cash_Flow'],
            name="Operating Cash Flow", marker_color="#10b981"
        ))
    
    if 'CapEx' in df.columns:
        fig.add_trace(go.Bar(
            x=df['Year'], y=-df['CapEx'],  # Negative for outflow
            name="CapEx (Outflow)", marker_color="#ef4444"
        ))
    
    if 'Free_Cash_Flow' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['Year'], y=df['Free_Cash_Flow'],
            name="Free Cash Flow", mode='lines+markers',
            line=dict(color=color, width=3)
        ))
    
    fig.update_layout(
        title="Cash Flow Analysis",
        height=400,
        barmode='relative',
        yaxis_title="$ Millions",
        legend=dict(orientation="h", yanchor="bottom", y=1.02)
    )
    
    return fig


def create_capex_by_type(data: Dict) -> go.Figure:
    """Create CapEx breakdown by type pie chart"""
    
    if not data.get("by_type"):
        return _empty_figure("No CapEx type breakdown data")
    
    df = pd.DataFrame(data["by_type"])
    
    # Parse amounts
    if 'Amount' in df.columns:
        df['Value'] = df['Amount'].apply(_parse_money)
    elif 'Percentage' in df.columns:
        df['Value'] = df['Percentage'].apply(lambda x: float(str(x).replace('%', '')) if x != 'N/A' else 0)
    else:
        return _empty_figure("No amount data")
    
    fig = px.pie(
        df, values='Value', names='Category',
        title="CapEx by Category",
        hole=0.4,
        color_discrete_sequence=CATEGORY_COLORS
    )
    
    fig.update_layout(height=400)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    
    return fig


def create_capex_by_geography(data: Dict) -> go.Figure:
    """Create CapEx breakdown by geography bar chart"""
    
    if not data.get("by_geography"):
        return _empty_figure("No geographic breakdown data")
    
    df = pd.DataFrame(data["by_geography"])
    
    # Parse amounts
    if 'CapEx' in df.columns:
        df['Value'] = df['CapEx'].apply(_parse_money)
    elif 'Percentage' in df.columns:
        df['Value'] = df['Percentage'].apply(lambda x: float(str(x).replace('%', '')) if x != 'N/A' else 0)
    else:
        return _empty_figure("No amount data")
    
    fig = px.bar(
        df, x='Region', y='Value',
        title="CapEx by Geography",
        color='Region',
        color_discrete_sequence=CATEGORY_COLORS
    )
    
    fig.update_layout(height=400, showlegend=False)
    fig.update_yaxes(title_text="CapEx ($M)")
    
    return fig


def create_ai_vs_traditional(data: Dict, color: str) -> go.Figure:
    """Create AI vs Traditional investment comparison"""
    
    ai_data = data.get("ai_traditional", {})
    
    if not ai_data:
        return _empty_figure("No AI vs Traditional data")
    
    ai_val = ai_data.get('ai', 0)
    trad_val = ai_data.get('traditional', 0)
    ai_pct = ai_data.get('ai_pct', 0)
    
    fig = go.Figure(go.Pie(
        labels=['AI/Data Center', 'Traditional'],
        values=[ai_val, trad_val],
        hole=0.65,
        marker_colors=AI_TRADITIONAL_COLORS,
        textinfo='label+percent',
        textposition='outside'
    ))
    
    fig.update_layout(
        title="AI vs Traditional Investment Split",
        height=400,
        annotations=[dict(
            text=f"<b>{ai_pct:.0f}%</b><br>AI/DC",
            x=0.5, y=0.5, font_size=20, showarrow=False
        )]
    )
    
    return fig


def create_risk_matrix(data: Dict) -> go.Figure:
    """Create risk assessment matrix bubble chart"""
    
    if not data.get("risk_matrix"):
        return _empty_figure("No risk matrix data")
    
    df = pd.DataFrame(data["risk_matrix"])
    
    # Ensure numeric values
    df['Likelihood'] = pd.to_numeric(df.get('Likelihood', 50), errors='coerce').fillna(50)
    df['Impact'] = pd.to_numeric(df.get('Impact', 50), errors='coerce').fillna(50)
    df['Score'] = pd.to_numeric(df.get('Score', 25), errors='coerce').fillna(25)
    
    fig = px.scatter(
        df, x='Likelihood', y='Impact',
        size='Score', color='Category',
        text='Risk',
        title="Risk Assessment Matrix",
        size_max=60
    )
    
    fig.update_traces(textposition='top center')
    
    # Add quadrant lines
    fig.add_hline(y=50, line_dash="dash", line_color="#64748b", opacity=0.5)
    fig.add_vline(x=50, line_dash="dash", line_color="#64748b", opacity=0.5)
    
    # Add quadrant labels
    fig.add_annotation(x=25, y=75, text="Low Prob, High Impact", showarrow=False, opacity=0.5)
    fig.add_annotation(x=75, y=75, text="High Risk Zone", showarrow=False, font=dict(color="red"), opacity=0.7)
    fig.add_annotation(x=25, y=25, text="Low Risk", showarrow=False, opacity=0.5)
    fig.add_annotation(x=75, y=25, text="Monitor", showarrow=False, opacity=0.5)
    
    fig.update_layout(
        height=500,
        xaxis_title="Likelihood (%)",
        yaxis_title="Impact (%)",
        xaxis=dict(range=[0, 100]),
        yaxis=dict(range=[0, 100])
    )
    
    return fig


def create_customer_concentration(data: Dict) -> go.Figure:
    """Create customer concentration pie chart"""
    
    if not data.get("customers"):
        return _empty_figure("No customer data")
    
    df = pd.DataFrame(data["customers"])
    
    # Parse percentage
    if 'Revenue %' in df.columns:
        df['Value'] = df['Revenue %'].apply(lambda x: float(str(x).replace('%', '')) if x != 'N/A' else 0)
    else:
        return _empty_figure("No revenue percentage data")
    
    # Add "Others" if doesn't sum to 100
    total = df['Value'].sum()
    if total < 100:
        others_df = pd.DataFrame([{'Customer': 'Others', 'Value': 100 - total}])
        df = pd.concat([df, others_df], ignore_index=True)
    
    fig = px.pie(
        df, values='Value', names='Customer',
        title="Customer Concentration",
        hole=0.4,
        color_discrete_sequence=CATEGORY_COLORS
    )
    
    fig.update_layout(height=400)
    
    return fig


def create_competitive_radar(data: Dict) -> go.Figure:
    """Create competitive positioning radar chart"""
    
    if not data.get("benchmarking"):
        return _empty_figure("No benchmarking data")
    
    df = pd.DataFrame(data["benchmarking"])
    
    if len(df) == 0:
        return _empty_figure("No benchmarking data")
    
    categories = ['CapEx/Revenue', 'AI Investment', 'Growth Rate', 'FCF Margin', 'ROIC']
    
    fig = go.Figure()
    
    for _, row in df.iterrows():
        company_name = row.get('Company', 'Unknown')
        values = [row.get(cat, 50) for cat in categories]
        values.append(values[0])  # Close the polygon
        
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories + [categories[0]],
            name=company_name,
            fill='toself',
            opacity=0.6
        ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100])
        ),
        title="Competitive Positioning",
        height=500,
        showlegend=True
    )
    
    return fig


def create_capex_guidance_chart(data: Dict, color: str) -> go.Figure:
    """Create CapEx guidance forecast chart"""
    
    if not data.get("capex_guidance"):
        return _empty_figure("No CapEx guidance data")
    
    df = pd.DataFrame(data["capex_guidance"])
    
    # Ensure numeric
    df['Midpoint'] = pd.to_numeric(df.get('Midpoint', 0), errors='coerce').fillna(0)
    df['Low'] = pd.to_numeric(df.get('Low', 0), errors='coerce').fillna(0)
    df['High'] = pd.to_numeric(df.get('High', 0), errors='coerce').fillna(0)
    
    fig = go.Figure()
    
    # Add range area
    fig.add_trace(go.Scatter(
        x=list(df['Period']) + list(df['Period'])[::-1],
        y=list(df['High']) + list(df['Low'])[::-1],
        fill='toself',
        fillcolor=f'rgba(59, 130, 246, 0.2)',
        line=dict(color='rgba(255,255,255,0)'),
        name='Guidance Range'
    ))
    
    # Add midpoint line
    fig.add_trace(go.Scatter(
        x=df['Period'], y=df['Midpoint'],
        mode='lines+markers',
        name='Midpoint',
        line=dict(color=color, width=3),
        marker=dict(size=10)
    ))
    
    fig.update_layout(
        title="CapEx Guidance Forecast",
        height=400,
        yaxis_title="CapEx ($M)",
        showlegend=True
    )
    
    return fig


def create_investment_comparison(all_results: Dict[str, Dict]) -> go.Figure:
    """Create cross-company investment comparison chart"""
    
    companies = []
    capex_values = []
    ai_percentages = []
    
    for company, results in all_results.items():
        capex = results.get("capex_breakdown", {})
        ai_data = capex.get("ai_traditional", {})
        
        companies.append(company)
        capex_values.append(ai_data.get('ai', 0) + ai_data.get('traditional', 0))
        ai_percentages.append(ai_data.get('ai_pct', 0))
    
    df = pd.DataFrame({
        'Company': companies,
        'Total CapEx': capex_values,
        'AI %': ai_percentages
    })
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    colors = [COMPANY_COLORS.get(c, "#64748b") for c in companies]
    
    fig.add_trace(
        go.Bar(x=df['Company'], y=df['Total CapEx'], name="Total CapEx",
               marker_color=colors),
        secondary_y=False
    )
    
    fig.add_trace(
        go.Scatter(x=df['Company'], y=df['AI %'], name="AI Investment %",
                  mode='lines+markers', line=dict(color='#ef4444', width=3)),
        secondary_y=True
    )
    
    fig.update_layout(
        title="Cross-Company CapEx Comparison",
        height=450,
        legend=dict(orientation="h", yanchor="bottom", y=1.02)
    )
    fig.update_yaxes(title_text="Total CapEx ($M)", secondary_y=False)
    fig.update_yaxes(title_text="AI Investment (%)", secondary_y=True)
    
    return fig


def _empty_figure(message: str) -> go.Figure:
    """Create empty figure with message"""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=16, color="#64748b")
    )
    fig.update_layout(
        height=300,
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(showgrid=False, showticklabels=False)
    )
    return fig


def _parse_money(value) -> float:
    """Parse money string to float"""
    if value is None or value == 'N/A':
        return 0
    
    value = str(value)
    
    # Remove currency symbols and commas
    value = value.replace('$', '').replace(',', '').strip()
    
    # Handle billions
    if 'B' in value.upper():
        value = value.upper().replace('B', '')
        try:
            return float(value) * 1000  # Convert to millions
        except:
            return 0
    
    # Handle millions
    if 'M' in value.upper():
        value = value.upper().replace('M', '')
        try:
            return float(value)
        except:
            return 0
    
    # Try direct parse
    try:
        return float(value)
    except:
        return 0
