# CapEx Intelligence Analysis Tool

A personal document analysis tool that extracts competitive intelligence from SEC filings, earnings calls, and investor presentations using a local LLM (Ollama).

## Features

- **Document Processing**: Automatically extracts text from PDFs, HTML, and TXT files
- **LLM Analysis**: Uses Ollama (local LLM) for intelligent document analysis
- **Comprehensive Framework**: Follows the Advanced Document Reading Guide
- **Interactive Dashboard**: Streamlit-based UI with charts and visualizations
- **Multiple Export Formats**: Markdown, HTML, and PDF reports

## Analysis Sections

1. **Financial Context**: Revenue, profitability, CapEx ratios, cash flow health
2. **CapEx Breakdown**: By type, geography, segment, and AI vs Traditional
3. **Strategic Initiatives**: Major projects, technology investments, ESG
4. **Competitive Positioning**: Customer concentration, benchmarking, market share
5. **Risk Factors**: Supply chain, geopolitical, labor, red flags
6. **Forward Guidance**: CapEx forecasts, project pipeline, ROIC targets
7. **Earnings Call Analysis**: Management tone, key quotes, surprises

## Prerequisites

### 1. Install Ollama

```bash
# macOS
brew install ollama

# Or download from https://ollama.ai
```

### 2. Pull an LLM Model

```bash
# Recommended: Llama 3.1 (best quality)
ollama pull llama3.1

# Alternative: Mistral (faster)
ollama pull mistral

# Alternative: Phi-3 (smallest, fastest)
ollama pull phi3
```

### 3. Start Ollama Server

```bash
ollama serve
```

## Installation

```bash
# Navigate to the analysis tool directory
cd "SCU Flex Practicum 2026/analysis_tool"

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Run the Streamlit App

```bash
streamlit run app.py
```

This will open the dashboard in your browser at `http://localhost:8501`

### Using the Dashboard

1. **Select a Company**: Choose from Flex, Jabil, Celestica, Benchmark, or Sanmina
2. **Choose Analysis Sections**: Select which analyses to run
3. **Configure LLM**: Choose model and temperature
4. **Run Analysis**: Click "Run Analysis" to process documents
5. **View Results**: Navigate through tabs to see insights
6. **Export Reports**: Download as Markdown, HTML, or PDF

## Folder Structure

```
analysis_tool/
├── app.py                 # Main Streamlit application
├── document_processor.py  # Document loading and text extraction
├── llm_analyzer.py        # LLM-based analysis modules
├── report_generator.py    # Report export (MD, HTML, PDF)
├── visualizations.py      # Plotly chart generation
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Data Structure Expected

The tool expects company data in the parent directory:

```
SCU Flex Practicum 2026/
├── Flex/
│   ├── annual_10K/
│   ├── quarterly_10Q/
│   ├── flex_transcripts/
│   └── ...
├── Jabil/
├── Celestica/
├── Sanmina/
├── benchmark/
└── analysis_tool/     # This tool
```

## Configuration

### LLM Models

| Model | Quality | Speed | Memory |
|-------|---------|-------|--------|
| llama3.1 | Best | Slow | ~8GB |
| llama3 | Good | Medium | ~5GB |
| mistral | Good | Fast | ~4GB |
| mixtral | Best | Slow | ~26GB |
| phi3 | OK | Fastest | ~2GB |

### Temperature Setting

- **0.0-0.2**: More focused, factual responses (recommended for financial analysis)
- **0.3-0.5**: Balanced creativity and accuracy
- **0.6-1.0**: More creative responses (not recommended for this use case)

## Report Output

### Markdown Report
- Clean, readable format
- Tables and structured data
- Easy to version control

### HTML Report
- Styled with CSS
- Interactive tables
- Print-ready

### PDF Report (requires weasyprint)
```bash
pip install weasyprint
```

## Troubleshooting

### "ollama not installed"
```bash
pip install ollama
```

### "Connection refused" when running analysis
Make sure Ollama is running:
```bash
ollama serve
```

### Slow analysis
- Use a faster model (mistral, phi3)
- Reduce the number of documents
- Select fewer analysis sections

### PDF export fails
Install weasyprint system dependencies:
```bash
# macOS
brew install pango

# Ubuntu/Debian
sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0
```

## Example Workflow

1. Start Ollama: `ollama serve`
2. Run app: `streamlit run app.py`
3. Select "Jabil" from the dropdown
4. Enable all analysis sections
5. Click "Run Analysis" (takes 5-10 minutes)
6. Review insights in each tab
7. Export to HTML for sharing

## Analysis Quality Tips

- **Use llama3.1** for best extraction quality
- **Run overnight** if analyzing all 5 companies
- **Review red flags** section for anomalies
- **Cross-reference** quotes with original documents
- **Export to HTML** for executive presentations

---

*Built for the Flex Practicum project - Competitive Intelligence Analysis*
