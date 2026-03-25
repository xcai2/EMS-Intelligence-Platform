"""
Report Generator
================
Generates reports in Markdown, HTML, and PDF formats.
"""

import json
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path
import base64


class ReportGenerator:
    """Generate analysis reports in multiple formats"""
    
    def __init__(self):
        self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    def to_markdown(self, company: str, results: Dict[str, Any]) -> str:
        """Generate Markdown report"""
        
        md = f"""# {company} - CapEx Intelligence Report

**Generated:** {self.generated_at}

---

## Executive Summary

"""
        
        # Add synthesis if available
        synthesis = results.get("synthesis", {})
        if synthesis:
            thesis = synthesis.get("thesis", {})
            md += f"""### Investment Thesis
**Classification:** {thesis.get('classification', 'N/A')}

{thesis.get('description', 'No description available.')}

### Key Findings
"""
            for i, finding in enumerate(synthesis.get("key_findings", [])[:5], 1):
                md += f"{i}. {finding}\n"
            
            md += "\n### Risk Profile\n"
            risk = synthesis.get("risk_profile", {})
            md += f"**Level:** {risk.get('level', 'N/A')}\n\n"
            md += f"{risk.get('explanation', '')}\n"
        
        md += "\n---\n\n"
        
        # Financial Context
        md += "## Financial Context\n\n"
        financial = results.get("financial_context", {})
        
        if financial.get("yearly_metrics"):
            md += "### Revenue & Profitability\n\n"
            md += "| Year | Revenue | Operating Income | Net Income | CapEx | CapEx/Revenue |\n"
            md += "|------|---------|------------------|------------|-------|---------------|\n"
            for row in financial["yearly_metrics"]:
                md += f"| {row.get('Year', 'N/A')} | {row.get('Revenue', 'N/A')} | {row.get('Operating_Income', 'N/A')} | {row.get('Net_Income', 'N/A')} | {row.get('CapEx', 'N/A')} | {row.get('CapEx_Revenue_Pct', 'N/A')} |\n"
            md += "\n"
        
        if financial.get("insights"):
            md += "### Financial Insights\n\n"
            for insight in financial["insights"]:
                md += f"- {insight}\n"
            md += "\n"
        
        md += "---\n\n"
        
        # CapEx Breakdown
        md += "## CapEx Breakdown\n\n"
        capex = results.get("capex_breakdown", {})
        
        if capex.get("by_type"):
            md += "### By Category\n\n"
            md += "| Category | Amount | Percentage |\n"
            md += "|----------|--------|------------|\n"
            for row in capex["by_type"]:
                md += f"| {row.get('Category', 'N/A')} | {row.get('Amount', 'N/A')} | {row.get('Percentage', 'N/A')} |\n"
            md += "\n"
        
        if capex.get("by_geography"):
            md += "### By Geography\n\n"
            md += "| Region | CapEx | Percentage | Key Projects |\n"
            md += "|--------|-------|------------|---------------|\n"
            for row in capex["by_geography"]:
                md += f"| {row.get('Region', 'N/A')} | {row.get('CapEx', 'N/A')} | {row.get('Percentage', 'N/A')} | {row.get('Key_Projects', 'N/A')} |\n"
            md += "\n"
        
        if capex.get("ai_traditional"):
            ai_data = capex["ai_traditional"]
            md += f"""### AI vs Traditional Split

- **AI/Data Center:** ${ai_data.get('ai', 0)}M ({ai_data.get('ai_pct', 0)}%)
- **Traditional:** ${ai_data.get('traditional', 0)}M ({100 - ai_data.get('ai_pct', 0)}%)

"""
        
        md += "---\n\n"
        
        # Strategic Initiatives
        md += "## Strategic Initiatives\n\n"
        strategic = results.get("strategic_initiatives", {})
        
        if strategic.get("projects"):
            md += "### Major Facility Projects\n\n"
            md += "| Project | Location | Investment | Timeline | Purpose |\n"
            md += "|---------|----------|------------|----------|----------|\n"
            for proj in strategic["projects"]:
                md += f"| {proj.get('Project Name', 'N/A')} | {proj.get('Location', 'N/A')} | {proj.get('Investment', 'N/A')} | {proj.get('Start Date', 'N/A')} - {proj.get('Completion', 'N/A')} | {proj.get('Purpose', 'N/A')} |\n"
            md += "\n"
        
        if strategic.get("technology"):
            md += "### Technology Investments\n\n"
            for tech in strategic["technology"]:
                md += f"- **{tech.get('type', 'N/A')}:** {tech.get('description', 'N/A')}"
                if tech.get('amount'):
                    md += f" ({tech['amount']})"
                md += "\n"
            md += "\n"
        
        if strategic.get("esg"):
            md += "### ESG Investments\n\n"
            for esg in strategic["esg"]:
                md += f"- **{esg.get('initiative', 'N/A')}:** {esg.get('details', 'N/A')}\n"
            md += "\n"
        
        md += "---\n\n"
        
        # Competitive Positioning
        md += "## Competitive Positioning\n\n"
        competitive = results.get("competitive_positioning", {})
        
        if competitive.get("customers"):
            md += "### Customer Concentration\n\n"
            md += "| Customer | Revenue % | Notes |\n"
            md += "|----------|-----------|-------|\n"
            for cust in competitive["customers"]:
                md += f"| {cust.get('Customer', 'N/A')} | {cust.get('Revenue %', 'N/A')} | {cust.get('Notes', 'N/A')} |\n"
            md += "\n"
        
        if competitive.get("competitive_advantages"):
            md += "### Competitive Advantages\n\n"
            for adv in competitive["competitive_advantages"]:
                md += f"- {adv}\n"
            md += "\n"
        
        if competitive.get("competitive_threats"):
            md += "### Competitive Threats\n\n"
            for threat in competitive["competitive_threats"]:
                md += f"- {threat}\n"
            md += "\n"
        
        md += "---\n\n"
        
        # Risk Factors
        md += "## Risk Assessment\n\n"
        risks = results.get("risk_factors", {})
        
        if risks.get("supply_chain"):
            md += "### Supply Chain Risks\n\n"
            for risk in risks["supply_chain"]:
                severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk.get("severity", "medium"), "⚪")
                md += f"- {severity_emoji} **{risk.get('risk', 'N/A')}:** {risk.get('description', 'N/A')}\n"
            md += "\n"
        
        if risks.get("geopolitical"):
            md += "### Geopolitical Risks\n\n"
            for risk in risks["geopolitical"]:
                severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk.get("severity", "medium"), "⚪")
                md += f"- {severity_emoji} **{risk.get('risk', 'N/A')}:** {risk.get('description', 'N/A')}\n"
            md += "\n"
        
        if risks.get("red_flags"):
            md += "### 🚩 Red Flags\n\n"
            for flag in risks["red_flags"]:
                md += f"- **{flag.get('flag', 'N/A')}:** {flag.get('explanation', 'N/A')}\n"
            md += "\n"
        
        md += "---\n\n"
        
        # Forward Guidance
        md += "## Forward Guidance\n\n"
        guidance = results.get("forward_guidance", {})
        
        if guidance.get("capex_guidance"):
            md += "### CapEx Guidance\n\n"
            md += "| Period | Low | High | Midpoint | Notes |\n"
            md += "|--------|-----|------|----------|-------|\n"
            for row in guidance["capex_guidance"]:
                md += f"| {row.get('Period', 'N/A')} | ${row.get('Low', 0)}M | ${row.get('High', 0)}M | ${row.get('Midpoint', 0)}M | {row.get('Notes', '')} |\n"
            md += "\n"
        
        if guidance.get("quotes"):
            md += "### Key Management Quotes\n\n"
            for quote in guidance["quotes"]:
                md += f"> \"{quote.get('text', '')}\"\n>\n> — {quote.get('speaker', 'N/A')}, {quote.get('context', 'N/A')}\n\n"
        
        if guidance.get("key_themes"):
            md += "### Key Themes\n\n"
            for theme in guidance["key_themes"]:
                md += f"- {theme}\n"
            md += "\n"
        
        md += "---\n\n"
        
        # Recommendations
        md += "## Recommendations for Flex\n\n"
        
        if synthesis.get("recommendations"):
            for rec in synthesis["recommendations"]:
                rec_type = rec.get("type", "insight")
                icon = {"opportunity": "🟢", "threat": "🔴", "strength": "🔵", "weakness": "🟡"}.get(rec_type, "💡")
                md += f"### {icon} {rec_type.title()}\n\n{rec.get('text', 'N/A')}\n\n"
        
        # Bottom Line
        if synthesis.get("bottom_line"):
            md += f"""---

## The Bottom Line

**{synthesis['bottom_line']}**

---

*Report generated by CapEx Intelligence Analyzer*
"""
        
        return md
    
    def to_html(self, company: str, results: Dict[str, Any]) -> str:
        """Generate HTML report with styling"""
        
        # Generate markdown first
        md_content = self.to_markdown(company, results)
        
        # Convert to HTML (basic conversion)
        html_content = self._markdown_to_html(md_content)
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{company} - CapEx Intelligence Report</title>
    <style>
        :root {{
            --primary: #1e40af;
            --secondary: #475569;
            --accent: #3b82f6;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #1e293b;
            --text-muted: #64748b;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 2rem;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: var(--card-bg);
            border-radius: 1rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            padding: 3rem;
        }}
        
        h1 {{
            color: var(--primary);
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            border-bottom: 4px solid var(--accent);
            padding-bottom: 1rem;
        }}
        
        h2 {{
            color: var(--primary);
            font-size: 1.75rem;
            margin: 2.5rem 0 1rem 0;
            border-bottom: 2px solid var(--accent);
            padding-bottom: 0.5rem;
        }}
        
        h3 {{
            color: var(--secondary);
            font-size: 1.25rem;
            margin: 1.5rem 0 0.75rem 0;
        }}
        
        p {{
            margin: 0.75rem 0;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
            font-size: 0.9rem;
        }}
        
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        
        th {{
            background: var(--primary);
            color: white;
            font-weight: 600;
        }}
        
        tr:hover {{
            background: #f1f5f9;
        }}
        
        ul {{
            margin: 1rem 0;
            padding-left: 1.5rem;
        }}
        
        li {{
            margin: 0.5rem 0;
        }}
        
        blockquote {{
            background: #f0f9ff;
            border-left: 4px solid var(--accent);
            padding: 1rem 1.5rem;
            margin: 1rem 0;
            border-radius: 0 0.5rem 0.5rem 0;
            font-style: italic;
        }}
        
        .metric-card {{
            background: linear-gradient(135deg, var(--primary) 0%, #3b82f6 100%);
            color: white;
            padding: 1.5rem;
            border-radius: 1rem;
            margin: 0.5rem;
            display: inline-block;
            min-width: 200px;
        }}
        
        .insight-box {{
            background: #f0f9ff;
            border-left: 4px solid var(--accent);
            padding: 1rem;
            margin: 1rem 0;
            border-radius: 0 0.5rem 0.5rem 0;
        }}
        
        .warning-box {{
            background: #fef3c7;
            border-left: 4px solid var(--warning);
            padding: 1rem;
            margin: 1rem 0;
            border-radius: 0 0.5rem 0.5rem 0;
        }}
        
        .success-box {{
            background: #d1fae5;
            border-left: 4px solid var(--success);
            padding: 1rem;
            margin: 1rem 0;
            border-radius: 0 0.5rem 0.5rem 0;
        }}
        
        .danger-box {{
            background: #fee2e2;
            border-left: 4px solid var(--danger);
            padding: 1rem;
            margin: 1rem 0;
            border-radius: 0 0.5rem 0.5rem 0;
        }}
        
        .bottom-line {{
            background: var(--text);
            color: white;
            padding: 2rem;
            border-radius: 1rem;
            margin: 2rem 0;
            font-size: 1.1rem;
        }}
        
        .timestamp {{
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-bottom: 2rem;
        }}
        
        hr {{
            border: none;
            border-top: 1px solid #e2e8f0;
            margin: 2rem 0;
        }}
        
        strong {{
            color: var(--primary);
        }}
        
        @media print {{
            body {{
                padding: 0;
            }}
            .container {{
                box-shadow: none;
                padding: 1rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        {html_content}
    </div>
</body>
</html>"""
        
        return html
    
    def _markdown_to_html(self, md: str) -> str:
        """Convert markdown to HTML (basic conversion)"""
        
        import re
        
        html = md
        
        # Headers
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        
        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        
        # Italic
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        
        # Blockquotes
        html = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)
        
        # Tables (basic)
        lines = html.split('\n')
        in_table = False
        table_lines = []
        result_lines = []
        
        for line in lines:
            if '|' in line and not line.strip().startswith('|--'):
                if not in_table:
                    in_table = True
                    table_lines = ['<table>']
                
                cells = [c.strip() for c in line.split('|')[1:-1]]
                if table_lines[-1] == '<table>':
                    # Header row
                    table_lines.append('<tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr>')
                else:
                    table_lines.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
            elif '|--' in line:
                continue  # Skip separator row
            else:
                if in_table:
                    table_lines.append('</table>')
                    result_lines.extend(table_lines)
                    table_lines = []
                    in_table = False
                result_lines.append(line)
        
        if in_table:
            table_lines.append('</table>')
            result_lines.extend(table_lines)
        
        html = '\n'.join(result_lines)
        
        # Lists
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'(<li>.*</li>\n)+', r'<ul>\g<0></ul>', html)
        
        # Numbered lists
        html = re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        
        # Horizontal rules
        html = re.sub(r'^---$', r'<hr>', html, flags=re.MULTILINE)
        
        # Paragraphs
        paragraphs = html.split('\n\n')
        processed = []
        for p in paragraphs:
            p = p.strip()
            if p and not p.startswith('<'):
                p = f'<p>{p}</p>'
            processed.append(p)
        html = '\n'.join(processed)
        
        return html
    
    def to_pdf(self, company: str, results: Dict[str, Any], output_path: str = None) -> bytes:
        """Generate PDF report (requires weasyprint)"""
        
        try:
            from weasyprint import HTML
        except ImportError:
            raise ImportError("weasyprint is required for PDF export. Install with: pip install weasyprint")
        
        html_content = self.to_html(company, results)
        
        if output_path:
            HTML(string=html_content).write_pdf(output_path)
            with open(output_path, 'rb') as f:
                return f.read()
        else:
            return HTML(string=html_content).write_pdf()
    
    def save_all_formats(self, company: str, results: Dict[str, Any], output_dir: str = "."):
        """Save report in all formats"""
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        base_name = f"{company}_analysis_{timestamp}"
        
        # Markdown
        md_path = output_path / f"{base_name}.md"
        with open(md_path, 'w') as f:
            f.write(self.to_markdown(company, results))
        print(f"Saved: {md_path}")
        
        # HTML
        html_path = output_path / f"{base_name}.html"
        with open(html_path, 'w') as f:
            f.write(self.to_html(company, results))
        print(f"Saved: {html_path}")
        
        # PDF (if weasyprint available)
        try:
            pdf_path = output_path / f"{base_name}.pdf"
            self.to_pdf(company, results, str(pdf_path))
            print(f"Saved: {pdf_path}")
        except ImportError:
            print("PDF export skipped (weasyprint not installed)")
        
        return {
            "markdown": str(md_path),
            "html": str(html_path),
        }
