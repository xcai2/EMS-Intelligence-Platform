#!/usr/bin/env python3
"""
CapEx Intelligence — Page-Level Parent Document Retrieval Pipeline
Inspired by RAG-Challenge-2 winning solution

Key Features (RAG-Challenge-2 Style):

1. PAGE-LEVEL PARENT DOCUMENT RETRIEVAL:
   - PDF: Each PAGE is a Parent (tables, footnotes, units are on same page)
   - HTML: Each SECTION is a Parent
   - Child chunks: Small pieces (~250 words) for precise embedding search
   - On retrieval: Find child → Return FULL parent (page/section) as context

2. TWO-LEVEL INDEXING:
   ┌─────────────────────────────────────────────────┐
   │ PARENT (Page/Section) - stored for context     │
   │   Page 45: Cash Flow Statement                  │
   │   Contains: full text + tables + footnotes      │
   │                                                 │
   │   ┌─────────────────────────────────────────┐  │
   │   │ CHILD 1 (~250 words) - for retrieval   │  │
   │   │   "Purchases of property and equipment" │  │
   │   │   metadata.parent_id → Page 45          │  │
   │   └─────────────────────────────────────────┘  │
   │   ┌─────────────────────────────────────────┐  │
   │   │ CHILD 2 (~250 words) - for retrieval   │  │
   │   └─────────────────────────────────────────┘  │
   └─────────────────────────────────────────────────┘

3. RICH METADATA on every chunk:
   - company, fiscal_year, quarter, filing_type (basic)
   - section_header: "Item 7. MD&A", "Cash Flow Statement", etc.
   - page_num: Page number in original document
   - parent_type: "page" or "section"
   - table_name, table_type: For table chunks

4. TABLE SERIALIZATION:
   - Markdown format (for display)
   - Linearized format (for semantic search)

Run from the project root:
    cd Flex-Practicum-Project-2026
    python scripts/build_chromadb.py
"""

import re
import uuid
import hashlib
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# IMPORTS
# ---------------------------------------------------------------------------
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    from bs4 import BeautifulSoup
    import PyPDF2
except ImportError:
    import subprocess, sys
    for p in ["chromadb", "sentence-transformers", "beautifulsoup4", "lxml", "PyPDF2"]:
        subprocess.check_call([sys.executable, "-m", "pip", "install", p, "-q"])
    import chromadb
    from sentence_transformers import SentenceTransformer
    from bs4 import BeautifulSoup
    import PyPDF2

try:
    import pdfplumber
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber", "-q"])
    import pdfplumber

# ---------------------------------------------------------------------------
# CONFIG — auto-detect project root from this script's location
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
BASE = SCRIPT_DIR.parent                          # project root
DB_PATH = str(BASE / "chromadb_store")
RAW_DATA_DIR = BASE / "data" / "raw"              # company document files

# Company → list of (subfolder, filing_type) pairs.
# Paths are relative to RAW_DATA_DIR / company_folder.
SOURCES = {
    "Flex": [
        ("annual_10K",             "10-K"),
        ("quarterly_10Q",          "10-Q"),
        ("flex_8k_press_releases", "8-K"),
        ("flex_transcripts",       "Earnings Transcript"),
        ("Earnings Presentation",  "Earnings Presentation"),
        ("Press Releases",         "Press Release"),
    ],
    "Jabil": [
        ("10K",                    "10-K"),
        ("10Q",                    "10-Q"),
        ("8K",                     "8-K"),
        ("Earnings Call",          "Earnings Transcript"),
        ("Earnings Presentation",  "Earnings Presentation"),
        ("Press Release",          "Press Release"),
    ],
    "Celestica/Celestica": [
        ("10-K",                        "10-K"),
        ("10-Q",                        "10-Q"),
        ("Earnings Calls/Transcript",   "Earnings Transcript"),
        ("Earnings Presentation ",      "Earnings Presentation"),
        ("News Releases",               "Press Release"),
        ("ShareholderLetter",           "Shareholder Letter"),
    ],
    "Benchmark": [
        ("benchmark_filings",                             None),
        ("Annual Report",                                 "10-K"),
        ("Earnings Presentation/2022",                    "Earnings Presentation"),
        ("Earnings Presentation/2023",                    "Earnings Presentation"),
        ("Earnings Presentation/2024",                    "Earnings Presentation"),
        ("Earnings Presentation/2025",                    "Earnings Presentation"),
        ("Press Release/2022",                            "Press Release"),
        ("Press Release/2023",                            "Press Release"),
        ("Press Release/2024",                            "Press Release"),
        ("Press Release/2025",                            "Press Release"),
        ("Sidoti September Small-Cap Virtual Conference", "Earnings Presentation"),
    ],
    "Sanmina": [
        ("10K",                    "10-K"),
        ("10Q",                    "10-Q"),
        ("sanmina_8k",             "8-K"),
        ("SanminaEarningsPresentations", "Earnings Presentation"),
        ("SanminaPressReleases",   "Press Release"),
    ],
    "Plexus": [
        ("10K",                    "10-K"),
        ("10Q",                    "10-Q"),
        ("8K",                     "8-K"),
        ("Earnings Call",          "Earnings Transcript"),
        ("Earnings Presentation",  "Earnings Presentation"),
        ("Press Release",          "Press Release"),
    ],
}

COMPANY_DISPLAY = {
    "Flex": "Flex",
    "Jabil": "Jabil",
    "Celestica/Celestica": "Celestica",
    "Benchmark": "Benchmark",
    "Sanmina": "Sanmina",
    "Plexus": "Plexus",
}

# ---------------------------------------------------------------------------
# DATA STRUCTURES FOR PAGE-LEVEL PARENT DOCUMENT RETRIEVAL
# ---------------------------------------------------------------------------

@dataclass
class PageContent:
    """Represents a single page from a PDF document."""
    page_num: int
    text: str
    tables: list = field(default_factory=list)  # Serialized tables on this page
    section_header: str = ""  # Detected section header on this page
    
    def get_full_content(self) -> str:
        """Get the full page content including tables."""
        parts = [self.text]
        for table in self.tables:
            if table.get("linearized"):
                parts.append(f"\n[TABLE: {table.get('context', 'Data Table')}]\n{table['linearized']}")
        return "\n\n".join(parts)


@dataclass
class SectionContent:
    """Represents a section from an HTML document."""
    section_name: str
    section_level: int  # 1=Item, 2=Statement, 3=Subsection
    content: str
    tables: list = field(default_factory=list)
    
    def get_full_content(self) -> str:
        """Get the full section content including tables."""
        parts = [f"[{self.section_name}]\n{self.content}"]
        for table in self.tables:
            if table.get("linearized"):
                parts.append(f"\n[TABLE]\n{table['linearized']}")
        return "\n\n".join(parts)


@dataclass
class DocumentSection:
    """Represents a section of a document with structure preserved."""
    section_type: str  # "header", "paragraph", "table", "list"
    content: str
    header_level: int = 0  # 1=H1, 2=H2, etc.
    parent_header: str = ""
    page_num: int = 0
    
@dataclass
class ParsedDocument:
    """A fully parsed document with structure."""
    sections: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    pages: list = field(default_factory=list)  # List of PageContent
    full_text: str = ""
    metadata: dict = field(default_factory=dict)

@dataclass
class ChunkWithParent:
    """A chunk that knows its parent for Parent Document Retrieval."""
    chunk_id: str
    content: str
    parent_id: str
    parent_content: str  # FULL parent content (page or section)
    chunk_type: str  # "child", "parent", "table"
    parent_type: str = "page"  # "page" for PDF, "section" for HTML
    metadata: dict = field(default_factory=dict)

# ---------------------------------------------------------------------------
# SEC FINANCIAL STATEMENT SECTION HEADERS (for structure detection)
# ---------------------------------------------------------------------------
SEC_SECTION_PATTERNS = [
    # 10-K / 10-Q Item headers
    (r"^ITEM\s*1\.?\s*BUSINESS", "Item 1. Business", 1),
    (r"^ITEM\s*1A\.?\s*RISK\s*FACTORS", "Item 1A. Risk Factors", 1),
    (r"^ITEM\s*2\.?\s*PROPERTIES", "Item 2. Properties", 1),
    (r"^ITEM\s*7\.?\s*MANAGEMENT", "Item 7. MD&A", 1),
    (r"^ITEM\s*7A\.?\s*QUANTITATIVE", "Item 7A. Market Risk", 1),
    (r"^ITEM\s*8\.?\s*FINANCIAL\s*STATEMENTS", "Item 8. Financial Statements", 1),
    
    # Financial statement headers
    (r"CONSOLIDATED\s*STATEMENTS?\s*OF\s*OPERATIONS", "Income Statement", 2),
    (r"CONSOLIDATED\s*STATEMENTS?\s*OF\s*CASH\s*FLOWS?", "Cash Flow Statement", 2),
    (r"CONSOLIDATED\s*BALANCE\s*SHEETS?", "Balance Sheet", 2),
    (r"CONSOLIDATED\s*STATEMENTS?\s*OF\s*COMPREHENSIVE", "Comprehensive Income", 2),
    
    # Common subsections
    (r"LIQUIDITY\s*AND\s*CAPITAL\s*RESOURCES", "Liquidity and Capital Resources", 3),
    (r"CAPITAL\s*EXPENDITURES?", "Capital Expenditures", 3),
    (r"RESULTS\s*OF\s*OPERATIONS", "Results of Operations", 3),
    (r"CRITICAL\s*ACCOUNTING", "Critical Accounting Policies", 3),
]

# CapEx related terms for table detection
CAPEX_TABLE_INDICATORS = [
    "capital expenditure", "capex", "property and equipment",
    "property, plant and equipment", "purchases of property",
    "cash flow", "investing activities", "additions to property",
]

# ---------------------------------------------------------------------------
# TEXT POST-PROCESSING
# ---------------------------------------------------------------------------
def _collapse_char_spaced(text):
    """Collapse character-spaced text like 'S t o c k  T r a d i n g' -> 'Stock Trading'."""
    return re.sub(
        r'(?<!\S)((?:\S ){3,}\S)(?!\S)',
        lambda m: m.group(1).replace(" ", ""),
        text,
    )

def _fix_word_boundaries(text):
    """Insert spaces at camelCase / punctuation boundaries.
    e.g. 'theCompany' -> 'the Company', 'operations.The' -> 'operations. The'
    """
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
    return text

def _clean_extracted_text(text):
    """Apply all post-processing fixes to extracted text."""
    text = _collapse_char_spaced(text)
    text = _fix_word_boundaries(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text.strip()

# ---------------------------------------------------------------------------
# TEXT EXTRACTION
# ---------------------------------------------------------------------------
def extract_html(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    for el in soup(["script", "style", "head", "meta"]):
        el.decompose()
    return _clean_extracted_text(soup.get_text(separator="\n", strip=True))

def _extract_page_with_tables(page):
    """Extract text from a single pdfplumber page, rendering tables as Markdown."""
    parts = []
    tables = page.find_tables()
    table_bboxes = [t.bbox for t in tables]

    # Extract non-table text
    if table_bboxes:
        non_table_page = page
        for bbox in table_bboxes:
            clipped = (
                max(0, bbox[0]), max(0, bbox[1]),
                min(page.width, bbox[2]), min(page.height, bbox[3]),
            )
            try:
                non_table_page = non_table_page.outside_bbox(clipped)
            except Exception:
                pass
        text = non_table_page.extract_text() or ""
        if text.strip():
            parts.append(text)
    else:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)

    # Extract tables as Markdown
    for table in tables:
        rows = table.extract()
        if not rows or len(rows) < 2:
            continue
        header = [cell.strip() if cell else "" for cell in rows[0]]
        md_lines = ["| " + " | ".join(header) + " |"]
        md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        for row in rows[1:]:
            cells = [cell.strip() if cell else "" for cell in row]
            if any(cells):
                md_lines.append("| " + " | ".join(cells) + " |")
        parts.append("\n".join(md_lines))

    return "\n\n".join(parts)

def _extract_page_words(page):
    """Word-level extraction for multi-column pages (correct reading order)."""
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    if not words:
        return ""
    # Group by y-position (lines), then sort each line by x
    lines = {}
    for w in words:
        y_key = round(w["top"] / 3) * 3
        lines.setdefault(y_key, []).append(w)
    sorted_lines = sorted(lines.items())
    result = []
    for _, line_words in sorted_lines:
        line_words.sort(key=lambda w: w["x0"])
        result.append(" ".join(w["text"] for w in line_words))
    return "\n".join(result)

def extract_pdf(path):
    """Extract text from PDF using pdfplumber (with table + multi-column support).
    Falls back to PyPDF2 if pdfplumber fails entirely."""
    text = ""
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = _extract_page_with_tables(page)
                if not page_text or len(page_text.strip()) < 20:
                    page_text = _extract_page_words(page)
                if page_text:
                    text += page_text + "\n\n"
        if text.strip():
            return _clean_extracted_text(text)
    except Exception as e:
        print(f" ⚠️  pdfplumber error, falling back to PyPDF2: {e}")

    # PyPDF2 fallback
    text = ""
    try:
        with open(path, "rb") as f:
            for page in PyPDF2.PdfReader(f).pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except Exception as e:
        print(f" ⚠️  PDF error: {e}")
    return _clean_extracted_text(text)

def extract_txt(path):
    """Extract text from TXT/MD files."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return _clean_extracted_text(f.read())
    except Exception as e:
        print(f" ⚠️  TXT error {path.name}: {e}")
        return ""


def extract(path):
    """Extract text from any supported file type."""
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        return extract_html(path)
    elif suffix == ".pdf":
        return extract_pdf(path)
    elif suffix in (".txt", ".md"):
        return extract_txt(path)
    return ""


# ---------------------------------------------------------------------------
# ENHANCED TABLE SERIALIZATION (inspired by RAG-Challenge-2)
# ---------------------------------------------------------------------------
def _detect_table_type(rows: list) -> str:
    """Detect what type of financial table this is based on content."""
    if not rows:
        return "unknown"
    
    # Flatten all text in the table
    all_text = " ".join(
        " ".join(str(cell) for cell in row if cell) 
        for row in rows
    ).lower()
    
    # Check for specific table types
    if any(term in all_text for term in ["cash flow", "operating activities", "investing activities", "financing activities"]):
        return "cash_flow_statement"
    if any(term in all_text for term in ["total assets", "total liabilities", "stockholders equity"]):
        return "balance_sheet"
    if any(term in all_text for term in ["net revenue", "cost of sales", "gross profit", "operating income"]):
        return "income_statement"
    if any(term in all_text for term in CAPEX_TABLE_INDICATORS):
        return "capex_related"
    
    return "other"


def serialize_table_enhanced(rows: list, table_context: str = "") -> tuple:
    """
    Convert a table to multiple searchable formats:
    1. Markdown format (for display)
    2. Linearized format (for search - each row becomes a sentence)
    3. Key-value pairs (for structured extraction)
    
    Returns: (markdown_str, linearized_str, table_type)
    """
    if not rows or len(rows) < 2:
        return "", "", "empty"
    
    table_type = _detect_table_type(rows)
    
    # Clean cells
    def clean_cell(cell):
        if cell is None:
            return ""
        return str(cell).strip().replace("\n", " ")
    
    header = [clean_cell(c) for c in rows[0]]
    data_rows = [[clean_cell(c) for c in row] for row in rows[1:]]
    
    # 1. Markdown format
    md_lines = []
    if table_context:
        md_lines.append(f"**Table: {table_context}**\n")
    md_lines.append("| " + " | ".join(header) + " |")
    md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
    for row in data_rows:
        if any(row):
            # Pad row to match header length
            padded = row + [""] * (len(header) - len(row))
            md_lines.append("| " + " | ".join(padded[:len(header)]) + " |")
    markdown = "\n".join(md_lines)
    
    # 2. Linearized format (better for semantic search)
    # Convert each row to a natural language sentence
    linearized_parts = []
    if table_context:
        linearized_parts.append(f"From {table_context}:")
    
    for row in data_rows:
        if not any(row):
            continue
        # Create key-value pairs
        pairs = []
        for h, v in zip(header, row):
            if h and v and v not in ["-", "—", "–", ""]:
                pairs.append(f"{h}: {v}")
        if pairs:
            linearized_parts.append("; ".join(pairs))
    
    linearized = "\n".join(linearized_parts)
    
    # 3. Add CapEx-specific annotations
    if table_type == "cash_flow_statement":
        linearized = "[CASH FLOW STATEMENT] " + linearized
    elif table_type == "capex_related":
        linearized = "[CAPITAL EXPENDITURE DATA] " + linearized
    
    return markdown, linearized, table_type


def _extract_tables_from_html(soup) -> list:
    """Extract all tables from HTML with context."""
    tables = []
    for table in soup.find_all("table"):
        # Get table context (preceding header or caption)
        context = ""
        caption = table.find("caption")
        if caption:
            context = caption.get_text(strip=True)
        else:
            prev = table.find_previous(["h1", "h2", "h3", "h4", "p"])
            if prev:
                context = prev.get_text(strip=True)[:100]
        
        # Extract rows
        rows = []
        for tr in table.find_all("tr"):
            cells = []
            for td in tr.find_all(["td", "th"]):
                cells.append(td.get_text(strip=True))
            if cells:
                rows.append(cells)
        
        if rows and len(rows) >= 2:
            md, linear, ttype = serialize_table_enhanced(rows, context)
            tables.append({
                "markdown": md,
                "linearized": linear,
                "type": ttype,
                "context": context,
                "row_count": len(rows),
            })
    
    return tables

# ---------------------------------------------------------------------------
# CONTENT-BASED DOC TYPE PATTERNS (for ambiguous filenames)
# ---------------------------------------------------------------------------
CONTENT_DOC_PATTERNS = {
    "10-K": [
        r"ANNUAL\s*REPORT", r"FORM\s*10-K", r"FORM\s*20-F",
        r"pursuant\s*to\s*section\s*13\s*or\s*15\(d\)",
        r"fiscal\s*year\s*ended",
        r"annual\s*report\s*on\s*form\s*10-k",
        r"annual\s*report\s*on\s*form\s*20-f",
    ],
    "10-Q": [
        r"QUARTERLY\s*REPORT", r"FORM\s*10-Q", r"FORM\s*6-K",
        r"quarterly\s*report\s*on\s*form\s*10-q",
        r"quarter\s*ended", r"quarterly\s*period\s*ended",
        r"report\s*of\s*foreign\s*private\s*issuer",
    ],
}

# ---------------------------------------------------------------------------
# FILING TYPE: auto-detect with foreign issuer + content fallback
# ---------------------------------------------------------------------------
def detect_filing_type(path, content=""):
    name = path.name.lower()

    # Foreign issuer forms (Celestica: 20-F = annual, 6-K = quarterly)
    if re.search(r"20-?f|20f", name):       return "10-K"
    if re.search(r"6-?k|6k", name):         return "10-Q"

    # Standard US forms
    if name.startswith("10-k") or "10k" in name:   return "10-K"
    if name.startswith("10-q") or "10q" in name:   return "10-Q"
    if name.startswith("8-k")  or "8k"  in name:   return "8-K"
    if "annual" in name and "report" in name:       return "10-K"

    # Content-based fallback for ambiguous filenames
    if content:
        sample = content[:5000]
        scores = {}
        for dtype, patterns in CONTENT_DOC_PATTERNS.items():
            scores[dtype] = sum(1 for p in patterns if re.search(p, sample, re.IGNORECASE))
        best = max(scores, key=scores.get) if scores else None
        if best and scores[best] >= 2:
            return best

    return "Other"

# ---------------------------------------------------------------------------
# FISCAL QUARTER EXTRACTION
# ---------------------------------------------------------------------------
def get_fiscal_quarter(path, company, content=""):
    name = path.name

    # --- Pattern 1: FY22Q3 / FY2022Q3 / fy24q2 ---
    m = re.search(r"[Ff][Yy](\d{2,4})[_\-]?[Qq](\d)", name)
    if m:
        fy = m.group(1)[-2:]
        return f"FY{fy}", f"Q{m.group(2)}"

    # --- Pattern 2: Q3-FY26 / Q1_FY25 ---
    m = re.search(r"[Qq](\d)[_\-]?[Ff][Yy](\d{2,4})", name)
    if m:
        fy = m.group(2)[-2:]
        return f"FY{fy}", f"Q{m.group(1)}"

    # --- Pattern 3: JBL_2023_10Q_Q2 / JBL_2025_EarningsCall_Q3 ---
    m = re.search(r"(\d{4}).*[Qq](\d)", name)
    if m:
        return f"FY{m.group(1)[-2:]}", f"Q{m.group(2)}"

    # --- Pattern 4: 25Q2 / 23Q3 ---
    m = re.search(r"(\d{2})[Qq](\d)", name)
    if m:
        return f"FY{m.group(1)}", f"Q{m.group(2)}"

    # --- Pattern 5: Samsara 8K filenames like 8K_0824.pdf  (MMYY) ---
    # and 10Q like 10Q_0824.pdf
    m = re.search(r"(?:8[Kk]|10[Kk]|10[Qq])_(\d{2})(\d{2})", name)
    if m:
        mm, yy = int(m.group(1)), m.group(2)
        # Samsara FY ends late Jan/early Feb → Feb-Jan fiscal year
        # Q1=Feb-Apr, Q2=May-Jul, Q3=Aug-Oct, Q4=Nov-Jan
        if   mm in (2,3,4):     q = "Q1"
        elif mm in (5,6,7):     q = "Q2"
        elif mm in (8,9,10):    q = "Q3"
        elif mm in (11,12,1):   q = "Q4"
        else:                   q = ""
        # FY = calendar year of the end month (Jan belongs to prior FY end)
        fy_year = int(yy) if mm != 1 else int(yy) - 1
        return f"FY{yy}", q

    # --- Pattern 6: Benchmark/Flex HTML with date: 10-Q_2023-09-30 / Flex_10-Q_2024-07-26 ---
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))

        if company in ("Flex",):
            # Flex FY ends March. Filing months: Jul=Q1, Oct=Q2, Jan=Q3, May=Q4/10-K
            fy = y + 1 if mo >= 4 else y
            if   mo in (7,8):     q = "Q1"
            elif mo in (10,11):   q = "Q2"
            elif mo in (1,2):     q = "Q3"
            elif mo in (5,6):     q = "Q4"
            else:                 q = ""
            return f"FY{str(fy)[-2:]}", q

        elif company in ("Benchmark",):
            # Benchmark = calendar year. Date in filename IS the period-end date.
            # 2023-09-30 → Q3 FY23
            if   mo in (1,2,3):     q = "Q1"
            elif mo in (4,5,6):     q = "Q2"
            elif mo in (7,8,9):     q = "Q3"
            elif mo in (10,11,12):  q = "Q4"
            else:                   q = ""
            return f"FY{str(y)[-2:]}", q

    # --- Pattern 7: Q1-2025 (calendar) ---
    m = re.search(r"[Qq](\d)[_\-](\d{4})", name)
    if m:
        return f"FY{m.group(2)[-2:]}", f"Q{m.group(1)}"

    # --- Content-based fallback (for UUID filenames like Sanmina) ---
    if content:
        sample = content[:10000]
        fy_patterns = [
            r"fiscal\s*year\s*ended\s*.*?(20\d{2})",
            r"year\s*ended\s*(?:january|february|march|april|may|june|july|august|september|october|november|december)\s*\d{1,2}\s*,?\s*(20\d{2})",
            r"for\s*the\s*year\s*ended\s*.*?(20\d{2})",
            r"quarterly\s*(?:report|period)\s*ended\s*.*?(20\d{2})",
        ]
        for pat in fy_patterns:
            m = re.search(pat, sample, re.IGNORECASE)
            if m:
                return f"FY{m.group(1)[-2:]}", ""

    return "Unknown", ""

# ---------------------------------------------------------------------------
# STRUCTURE-AWARE CHUNKING (RAG-Challenge-2 Style)
# ---------------------------------------------------------------------------
# Strategy (NOT fixed word count!):
# 1. Split by SECTIONS first (Item 1, Item 7, Financial Statements, etc.)
# 2. Within sections, split by PARAGRAPHS (double newlines)
# 3. Tables are SEPARATE chunks with rich metadata
# 4. Then apply parent-child hierarchy within sections
# 5. Every chunk carries: section_header, page_num, table_name, etc.

# Size limits (soft targets, but respect natural boundaries)
MAX_SECTION_WORDS = 1500    # Max words before splitting a section
MIN_CHUNK_WORDS = 100       # Min words to form a chunk
TARGET_CHILD_WORDS = 250    # Target size for child chunks
TARGET_PARENT_WORDS = 800   # Target size for parent chunks


def _generate_chunk_id(company: str, filename: str, chunk_index: int, chunk_type: str) -> str:
    """Generate a unique, deterministic chunk ID."""
    base = f"{company}_{filename}_{chunk_type}_{chunk_index}"
    return hashlib.md5(base.encode()).hexdigest()[:16]


def _split_by_sections(text: str) -> list:
    """
    Split text by SEC filing section headers.
    Returns list of (section_name, section_content, header_level) tuples.
    """
    sections = []
    lines = text.split("\n")
    
    current_section = "Document Start"
    current_level = 0
    current_content = []
    
    for line in lines:
        line_clean = line.strip()
        line_upper = line_clean.upper()
        
        # Check if this line is a section header
        found_header = False
        for pattern, section_name, level in SEC_SECTION_PATTERNS:
            if re.search(pattern, line_upper):
                # Save current section
                if current_content:
                    content_text = "\n".join(current_content).strip()
                    if content_text:
                        sections.append((current_section, content_text, current_level))
                
                # Start new section
                current_section = section_name
                current_level = level
                current_content = [line_clean]  # Include header in content
                found_header = True
                break
        
        if not found_header:
            current_content.append(line)
    
    # Don't forget the last section
    if current_content:
        content_text = "\n".join(current_content).strip()
        if content_text:
            sections.append((current_section, content_text, current_level))
    
    return sections


def _split_by_paragraphs(text: str, min_words: int = MIN_CHUNK_WORDS) -> list:
    """
    Split text by paragraphs (double newlines).
    Merge small paragraphs to meet minimum word count.
    """
    # Split by double newlines or multiple newlines
    raw_paragraphs = re.split(r'\n\s*\n', text)
    
    paragraphs = []
    current_para = []
    current_words = 0
    
    for para in raw_paragraphs:
        para = para.strip()
        if not para:
            continue
        
        para_words = len(para.split())
        
        # If current accumulation + this para is still small, merge
        if current_words + para_words < min_words:
            current_para.append(para)
            current_words += para_words
        else:
            # Save current accumulation
            if current_para:
                paragraphs.append("\n\n".join(current_para))
            # Start new paragraph
            current_para = [para]
            current_words = para_words
    
    # Don't forget the last accumulation
    if current_para:
        paragraphs.append("\n\n".join(current_para))
    
    return paragraphs


def _create_parent_child_from_paragraphs(
    paragraphs: list,
    section_name: str,
    section_level: int,
    company: str,
    filename: str,
    page_num: int = 0,
    base_index: int = 0,
) -> list:
    """
    Create parent-child chunks from a list of paragraphs.
    
    Parent = multiple consecutive paragraphs (~800 words)
    Child = single paragraph or split paragraph (~250 words)
    """
    chunks = []
    
    # Group paragraphs into parent chunks
    parent_groups = []
    current_group = []
    current_words = 0
    
    for para in paragraphs:
        para_words = len(para.split())
        
        if current_words + para_words > TARGET_PARENT_WORDS and current_group:
            parent_groups.append(current_group)
            current_group = [para]
            current_words = para_words
        else:
            current_group.append(para)
            current_words += para_words
    
    if current_group:
        parent_groups.append(current_group)
    
    # Process each parent group
    for p_idx, parent_paragraphs in enumerate(parent_groups):
        parent_content = "\n\n".join(parent_paragraphs)
        parent_id = _generate_chunk_id(company, filename, base_index + p_idx, f"parent_{section_name[:10]}")
        
        # Create parent chunk
        chunks.append(ChunkWithParent(
            chunk_id=parent_id,
            content=parent_content,
            parent_id=parent_id,
            parent_content=parent_content,
            chunk_type="parent",
            metadata={
                "section_header": section_name,
                "section_level": section_level,
                "page_num": page_num,
            },
        ))
        
        # Create child chunks from paragraphs within this parent
        child_idx = 0
        for para in parent_paragraphs:
            para_words = len(para.split())
            
            # If paragraph is too long, split it further
            if para_words > TARGET_CHILD_WORDS * 1.5:
                # Split long paragraph by sentences or word count
                sub_chunks = _split_long_paragraph(para, TARGET_CHILD_WORDS)
            else:
                sub_chunks = [para] if para_words >= MIN_CHUNK_WORDS else []
            
            for sub_chunk in sub_chunks:
                if len(sub_chunk.split()) < MIN_CHUNK_WORDS // 2:
                    continue
                    
                child_id = _generate_chunk_id(
                    company, filename, 
                    base_index * 100 + p_idx * 10 + child_idx, 
                    f"child_{section_name[:10]}"
                )
                
                chunks.append(ChunkWithParent(
                    chunk_id=child_id,
                    content=sub_chunk,
                    parent_id=parent_id,
                    parent_content=parent_content,
                    chunk_type="child",
                    metadata={
                        "section_header": section_name,
                        "section_level": section_level,
                        "page_num": page_num,
                        "child_index": child_idx,
                    },
                ))
                child_idx += 1
    
    return chunks


def _split_long_paragraph(text: str, target_words: int) -> list:
    """Split a long paragraph into smaller chunks, preferring sentence boundaries."""
    # Try to split by sentences first
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = []
    current_words = 0
    
    for sentence in sentences:
        sentence_words = len(sentence.split())
        
        if current_words + sentence_words > target_words and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_words = sentence_words
        else:
            current_chunk.append(sentence)
            current_words += sentence_words
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks


def chunk_text_simple(text: str, chunk_words: int = 250, overlap_words: int = 50) -> list:
    """Simple word-based chunking (legacy fallback)."""
    words = text.split()
    if not words:
        return []
    chunks = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + chunk_words]).strip())
        i += chunk_words - overlap_words
    return [c for c in chunks if len(c) > 50]


def chunk_with_parent_child(
    text: str, 
    company: str, 
    filename: str,
    tables: list = None,
    page_nums: dict = None,  # Optional: {section_name: page_num}
) -> list:
    """
    Create STRUCTURE-AWARE hierarchical chunks (RAG-Challenge-2 style).
    
    Process:
    1. Split by SEC section headers (Item 1, MD&A, Financial Statements, etc.)
    2. Within each section, split by paragraphs
    3. Create parent-child relationships within sections
    4. Tables become separate chunks with context
    
    Returns list of ChunkWithParent objects with rich metadata:
    - section_header: The SEC filing section this chunk belongs to
    - section_level: Header hierarchy level (1=Item, 2=Statement, 3=Subsection)
    - page_num: Page number if available
    - table_type: For table chunks, the detected table type
    - table_context: The heading/caption near the table
    """
    chunks = []
    
    if not text or len(text.strip()) < MIN_CHUNK_WORDS:
        return chunks
    
    # === STEP 1: Split by SEC sections ===
    sections = _split_by_sections(text)
    
    # If no sections detected, treat entire document as one section
    if not sections or len(sections) == 1:
        sections = [("Full Document", text, 0)]
    
    # === STEP 2: Process each section ===
    chunk_base_idx = 0
    for section_name, section_content, section_level in sections:
        section_words = len(section_content.split())
        
        # Skip very small sections
        if section_words < MIN_CHUNK_WORDS:
            continue
        
        # Get page number if available
        page_num = 0
        if page_nums and section_name in page_nums:
            page_num = page_nums[section_name]
        
        # === STEP 3: Split section by paragraphs ===
        paragraphs = _split_by_paragraphs(section_content)
        
        # === STEP 4: Create parent-child chunks ===
        section_chunks = _create_parent_child_from_paragraphs(
            paragraphs=paragraphs,
            section_name=section_name,
            section_level=section_level,
            company=company,
            filename=filename,
            page_num=page_num,
            base_index=chunk_base_idx,
        )
        
        chunks.extend(section_chunks)
        chunk_base_idx += len(paragraphs) + 1
    
    # === STEP 5: Add Table Chunks with rich metadata ===
    if tables:
        for t_idx, table in enumerate(tables):
            if not table.get("linearized"):
                continue
                
            table_id = _generate_chunk_id(company, filename, t_idx, "table")
            
            # Combine linearized (for search) with markdown (for display)
            table_content = f"{table['linearized']}\n\n{table['markdown']}"
            
            # Determine which section the table belongs to
            table_context = table.get("context", "")
            table_section = "Financial Tables"
            
            # Try to match table context to a known section
            for pattern, section_name, level in SEC_SECTION_PATTERNS:
                if re.search(pattern, table_context.upper()):
                    table_section = section_name
                    break
            
            chunks.append(ChunkWithParent(
                chunk_id=table_id,
                content=table_content,
                parent_id=table_id,
                parent_content=table_content,
                chunk_type="table",
                metadata={
                    "section_header": table_section,
                    "table_type": table.get("type", "unknown"),
                    "table_context": table_context[:200],
                    "table_name": _extract_table_name(table_context),
                    "page_num": table.get("page_num", 0),
                    "row_count": table.get("row_count", 0),
                },
            ))
    
    return chunks


def _extract_table_name(context: str) -> str:
    """Extract a clean table name from context."""
    if not context:
        return "Unnamed Table"
    
    # Common table name patterns
    patterns = [
        r"(?:consolidated\s+)?statements?\s+of\s+[\w\s]+",
        r"(?:schedule|table)\s+[\w\s]+",
        r"note\s+\d+[\w\s]*",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, context.lower())
        if match:
            return match.group(0).title()
    
    # Fallback: first 50 chars
    return context[:50].strip()


# ---------------------------------------------------------------------------
# PAGE-LEVEL PARENT DOCUMENT RETRIEVAL CHUNKING
# ---------------------------------------------------------------------------
# RAG-Challenge-2 Strategy:
# - PDF: Each PAGE is a Parent (financial tables, footnotes, units on same page)
# - HTML: Each SECTION is a Parent
# - Child chunks (~250 words) for precise embedding search
# - Store FULL parent content for context

CHILD_CHUNK_WORDS = 250
CHILD_OVERLAP_WORDS = 50
MIN_CHILD_WORDS = 80


def chunk_page_as_parent(
    page: PageContent,
    company: str,
    filename: str,
) -> list:
    """
    Create Child chunks from a PDF page, with the PAGE as Parent.
    
    The full page content (text + tables) is stored as the parent.
    Small child chunks are created for precise retrieval.
    
    Returns: list of ChunkWithParent objects
    """
    chunks = []
    
    # Get full page content (this is the Parent)
    parent_content = page.get_full_content()
    parent_id = _generate_chunk_id(company, filename, page.page_num, "page")
    
    if len(parent_content.strip()) < MIN_CHILD_WORDS:
        return chunks
    
    # Store the Parent chunk (the full page)
    chunks.append(ChunkWithParent(
        chunk_id=parent_id,
        content=parent_content,
        parent_id=parent_id,
        parent_content=parent_content,
        chunk_type="parent",
        parent_type="page",
        metadata={
            "page_num": page.page_num,
            "section_header": page.section_header,
            "is_page_parent": True,
        },
    ))
    
    # Create Child chunks from the page text
    words = page.text.split()
    child_idx = 0
    i = 0
    
    while i < len(words):
        child_text = " ".join(words[i:i + CHILD_CHUNK_WORDS]).strip()
        
        if len(child_text.split()) >= MIN_CHILD_WORDS:
            child_id = _generate_chunk_id(company, filename, page.page_num * 100 + child_idx, "child")
            
            chunks.append(ChunkWithParent(
                chunk_id=child_id,
                content=child_text,
                parent_id=parent_id,
                parent_content=parent_content,  # FULL page content
                chunk_type="child",
                parent_type="page",
                metadata={
                    "page_num": page.page_num,
                    "section_header": page.section_header,
                    "child_index": child_idx,
                },
            ))
            child_idx += 1
        
        i += CHILD_CHUNK_WORDS - CHILD_OVERLAP_WORDS
    
    # Add table chunks (tables are their own parents for direct table search)
    for t_idx, table in enumerate(page.tables):
        if table.get("linearized"):
            table_id = _generate_chunk_id(company, filename, page.page_num * 1000 + t_idx, "table")
            table_content = f"{table['linearized']}\n\n{table.get('markdown', '')}"
            
            chunks.append(ChunkWithParent(
                chunk_id=table_id,
                content=table_content,
                parent_id=parent_id,  # Link to page parent
                parent_content=parent_content,  # Full page for context
                chunk_type="table",
                parent_type="page",
                metadata={
                    "page_num": page.page_num,
                    "section_header": page.section_header,
                    "table_type": table.get("type", "unknown"),
                    "table_context": table.get("context", ""),
                },
            ))
    
    return chunks


def chunk_section_as_parent(
    section: SectionContent,
    company: str,
    filename: str,
    section_idx: int,
) -> list:
    """
    Create Child chunks from an HTML section, with the SECTION as Parent.
    
    The full section content is stored as the parent.
    Small child chunks are created for precise retrieval.
    
    Returns: list of ChunkWithParent objects
    """
    chunks = []
    
    # Get full section content (this is the Parent)
    parent_content = section.get_full_content()
    parent_id = _generate_chunk_id(company, filename, section_idx, f"section_{section.section_name[:10]}")
    
    if len(parent_content.strip()) < MIN_CHILD_WORDS:
        return chunks
    
    # Store the Parent chunk (the full section)
    chunks.append(ChunkWithParent(
        chunk_id=parent_id,
        content=parent_content,
        parent_id=parent_id,
        parent_content=parent_content,
        chunk_type="parent",
        parent_type="section",
        metadata={
            "section_header": section.section_name,
            "section_level": section.section_level,
            "is_section_parent": True,
        },
    ))
    
    # Split section into paragraphs first
    paragraphs = _split_by_paragraphs(section.content)
    
    # Create Child chunks
    child_idx = 0
    for para in paragraphs:
        para_words = len(para.split())
        
        if para_words >= MIN_CHILD_WORDS:
            # If paragraph is too long, split further
            if para_words > CHILD_CHUNK_WORDS * 1.5:
                sub_chunks = _split_long_paragraph(para, CHILD_CHUNK_WORDS)
            else:
                sub_chunks = [para]
            
            for sub in sub_chunks:
                if len(sub.split()) < MIN_CHILD_WORDS:
                    continue
                
                child_id = _generate_chunk_id(
                    company, filename, 
                    section_idx * 100 + child_idx, 
                    f"child_{section.section_name[:10]}"
                )
                
                chunks.append(ChunkWithParent(
                    chunk_id=child_id,
                    content=sub,
                    parent_id=parent_id,
                    parent_content=parent_content,  # FULL section content
                    chunk_type="child",
                    parent_type="section",
                    metadata={
                        "section_header": section.section_name,
                        "section_level": section.section_level,
                        "child_index": child_idx,
                    },
                ))
                child_idx += 1
    
    # Add table chunks
    for t_idx, table in enumerate(section.tables):
        if table.get("linearized"):
            table_id = _generate_chunk_id(company, filename, section_idx * 1000 + t_idx, "table")
            table_content = f"{table['linearized']}\n\n{table.get('markdown', '')}"
            
            chunks.append(ChunkWithParent(
                chunk_id=table_id,
                content=table_content,
                parent_id=parent_id,
                parent_content=parent_content,
                chunk_type="table",
                parent_type="section",
                metadata={
                    "section_header": section.section_name,
                    "table_type": table.get("type", "unknown"),
                    "table_context": table.get("context", ""),
                },
            ))
    
    return chunks


def chunk_document_with_page_parents(
    filepath: Path,
    company: str,
) -> list:
    """
    Main chunking function that uses PAGE-LEVEL or SECTION-LEVEL parents.
    
    - PDF files: Use pages as parents (best for financial tables)
    - HTML files: Use sections as parents
    - TXT/MD files: Use sections or full document
    
    Returns: list of ChunkWithParent objects
    """
    suffix = filepath.suffix.lower()
    filename = filepath.stem
    
    if suffix == ".pdf":
        # PDF: Extract by pages
        pages = extract_pdf_by_pages(filepath)
        if not pages:
            return []
        
        all_chunks = []
        for page in pages:
            page_chunks = chunk_page_as_parent(page, company, filename)
            all_chunks.extend(page_chunks)
        
        return all_chunks
    
    elif suffix in (".html", ".htm"):
        # HTML: Extract by sections
        sections = extract_html_by_sections(filepath)
        if not sections:
            return []
        
        all_chunks = []
        for idx, section in enumerate(sections):
            section_chunks = chunk_section_as_parent(section, company, filename, idx)
            all_chunks.extend(section_chunks)
        
        return all_chunks
    
    elif suffix in (".txt", ".md"):
        # TXT/MD: Use section-based chunking
        text = extract_txt(filepath)
        if not text or len(text.strip()) < MIN_CHILD_WORDS:
            return []
        
        # Create a single section for the whole document
        section = SectionContent(
            section_name="Full Document",
            section_level=0,
            content=text,
            tables=[],
        )
        
        return chunk_section_as_parent(section, company, filename, 0)
    
    return []


def detect_section_headers(text: str) -> list:
    """Detect SEC filing section headers in text."""
    sections = []
    lines = text.split("\n")
    
    for i, line in enumerate(lines):
        line_clean = line.strip().upper()
        for pattern, section_name, level in SEC_SECTION_PATTERNS:
            if re.search(pattern, line_clean):
                sections.append({
                    "line_num": i,
                    "section_name": section_name,
                    "level": level,
                    "original_text": line.strip(),
                })
                break
    
    return sections

# ---------------------------------------------------------------------------
# FILE DISCOVERY
# ---------------------------------------------------------------------------
def discover_all_files():
    """
    Walk the explicit SOURCES map. Returns list of (path, company_display, filing_type).
    """
    results = []
    for company_folder, subdir_list in SOURCES.items():
        company_path = RAW_DATA_DIR / company_folder
        if not company_path.is_dir():
            print(f"  ⚠️  Skipping {company_folder}/ — not found")
            continue

        display = COMPANY_DISPLAY[company_folder]
        file_count = 0

        for subdir_name, ftype in subdir_list:
            subdir_path = company_path / subdir_name
            if not subdir_path.is_dir():
                print(f"  ⚠️  {company_folder}/{subdir_name}/ not found, skipping")
                continue

            # Grab all supported files (non-recursive — one level only)
            SUPPORTED_EXTENSIONS = (".html", ".htm", ".pdf", ".txt", ".md")
            files = sorted(
                [f for f in subdir_path.iterdir()
                 if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
            )

            for f in files:
                # For benchmark, ftype is None → auto-detect
                actual_ftype = ftype if ftype else detect_filing_type(f)
                results.append((f, display, actual_ftype))
                file_count += 1

        print(f"  📂 {display:<12} → {file_count} files")

    return results

# ---------------------------------------------------------------------------
# ENHANCED HTML EXTRACTION (with table serialization)
# ---------------------------------------------------------------------------
def extract_html_structured(path) -> tuple:
    """
    Extract text and tables from HTML with structure preservation.
    Returns: (text, tables_list)
    """
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    # Extract tables first
    tables = _extract_tables_from_html(soup)
    
    # Remove tables from soup for text extraction
    for table in soup.find_all("table"):
        table.decompose()
    
    # Remove scripts, styles, etc.
    for el in soup(["script", "style", "head", "meta"]):
        el.decompose()
    
    text = _clean_extracted_text(soup.get_text(separator="\n", strip=True))
    
    return text, tables


def extract_pdf_structured(path) -> tuple:
    """
    Extract text and tables from PDF with structure preservation.
    Returns: (text, tables_list)
    """
    text_parts = []
    tables = []
    
    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Extract tables from this page
                page_tables = page.find_tables()
                table_bboxes = [t.bbox for t in page_tables]
                
                # Extract non-table text
                if table_bboxes:
                    non_table_page = page
                    for bbox in table_bboxes:
                        clipped = (
                            max(0, bbox[0]), max(0, bbox[1]),
                            min(page.width, bbox[2]), min(page.height, bbox[3]),
                        )
                        try:
                            non_table_page = non_table_page.outside_bbox(clipped)
                        except Exception:
                            pass
                    page_text = non_table_page.extract_text() or ""
                else:
                    page_text = page.extract_text() or ""
                
                if page_text.strip():
                    text_parts.append(page_text)
                
                # Process tables with enhanced serialization
                for table in page_tables:
                    rows = table.extract()
                    if rows and len(rows) >= 2:
                        # Try to get context from nearby text
                        context = ""
                        if page_text:
                            # Get first line as potential context
                            first_lines = page_text.strip().split("\n")[:2]
                            context = " ".join(first_lines)[:100]
                        
                        md, linear, ttype = serialize_table_enhanced(rows, context)
                        tables.append({
                            "markdown": md,
                            "linearized": linear,
                            "type": ttype,
                            "context": context,
                            "page_num": page_num + 1,
                            "row_count": len(rows),
                        })
        
        text = _clean_extracted_text("\n\n".join(text_parts))
        return text, tables
        
    except Exception as e:
        print(f" ⚠️  pdfplumber error: {e}")
        # Fallback to simple extraction
        text = extract_pdf(path)
        return text, []


def extract_pdf_by_pages(path) -> list:
    """
    Extract PDF content PAGE BY PAGE for Parent Document Retrieval.
    
    Each page becomes a "Parent" document containing:
    - Full page text
    - Serialized tables on that page
    - Detected section header
    
    Returns: List of PageContent objects
    """
    pages = []
    current_section = "Document Start"
    
    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Extract tables from this page
                page_tables = page.find_tables()
                table_bboxes = [t.bbox for t in page_tables]
                
                # Extract non-table text
                if table_bboxes:
                    non_table_page = page
                    for bbox in table_bboxes:
                        clipped = (
                            max(0, bbox[0]), max(0, bbox[1]),
                            min(page.width, bbox[2]), min(page.height, bbox[3]),
                        )
                        try:
                            non_table_page = non_table_page.outside_bbox(clipped)
                        except Exception:
                            pass
                    page_text = non_table_page.extract_text() or ""
                else:
                    page_text = page.extract_text() or ""
                
                page_text = _clean_extracted_text(page_text)
                
                # Detect section headers on this page
                page_upper = page_text.upper()
                for pattern, section_name, level in SEC_SECTION_PATTERNS:
                    if re.search(pattern, page_upper):
                        current_section = section_name
                        break
                
                # Process tables on this page
                page_table_data = []
                for table in page_tables:
                    rows = table.extract()
                    if rows and len(rows) >= 2:
                        context = ""
                        if page_text:
                            first_lines = page_text.strip().split("\n")[:2]
                            context = " ".join(first_lines)[:100]
                        
                        md, linear, ttype = serialize_table_enhanced(rows, context)
                        page_table_data.append({
                            "markdown": md,
                            "linearized": linear,
                            "type": ttype,
                            "context": context,
                            "row_count": len(rows),
                        })
                
                # Create PageContent
                if page_text.strip() or page_table_data:
                    pages.append(PageContent(
                        page_num=page_num + 1,
                        text=page_text,
                        tables=page_table_data,
                        section_header=current_section,
                    ))
        
        return pages
        
    except Exception as e:
        print(f" ⚠️  pdfplumber error in page extraction: {e}")
        return []


def extract_html_by_sections(path) -> list:
    """
    Extract HTML content SECTION BY SECTION for Parent Document Retrieval.
    
    Each SEC filing section becomes a "Parent" document.
    
    Returns: List of SectionContent objects
    """
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    # Extract tables with context
    all_tables = _extract_tables_from_html(soup)
    
    # Remove tables from soup for text extraction
    for table in soup.find_all("table"):
        table.decompose()
    
    # Remove scripts, styles, etc.
    for el in soup(["script", "style", "head", "meta"]):
        el.decompose()
    
    full_text = soup.get_text(separator="\n", strip=True)
    
    # Split by sections
    sections = _split_by_sections(full_text)
    
    section_contents = []
    for section_name, section_text, section_level in sections:
        section_text = _clean_extracted_text(section_text)
        
        if len(section_text.strip()) < 50:
            continue
        
        # Find tables that belong to this section (by context matching)
        section_tables = []
        for table in all_tables:
            table_context = table.get("context", "").lower()
            if section_name.lower() in table_context or not table_context:
                section_tables.append(table)
        
        section_contents.append(SectionContent(
            section_name=section_name,
            section_level=section_level,
            content=section_text,
            tables=section_tables,
        ))
    
    # If no sections detected, treat entire document as one section
    if not section_contents:
        section_contents.append(SectionContent(
            section_name="Full Document",
            section_level=0,
            content=_clean_extracted_text(full_text),
            tables=all_tables,
        ))
    
    return section_contents


def extract_txt_structured(path) -> tuple:
    """Extract text from TXT/MD files (no tables)."""
    text = extract_txt(path)
    return text, []


def extract_structured(path) -> tuple:
    """Extract text and tables from any supported file type."""
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        return extract_html_structured(path)
    elif suffix == ".pdf":
        return extract_pdf_structured(path)
    elif suffix in (".txt", ".md"):
        return extract_txt_structured(path)
    return "", []


# ---------------------------------------------------------------------------
# PER-COMPANY COLLECTION HELPERS
# ---------------------------------------------------------------------------
COMPANY_COLLECTION_PREFIX = "company_"


def _normalize_company_name(company: str) -> str:
    """Normalize company name for collection naming."""
    return company.lower().replace(" ", "_").replace("-", "_")


def _get_company_collection_name(company: str) -> str:
    """Get the collection name for a specific company."""
    return f"{COMPANY_COLLECTION_PREFIX}{_normalize_company_name(company)}"


# ---------------------------------------------------------------------------
# MAIN (Enhanced with Per-Company Collections)
# ---------------------------------------------------------------------------
def build_db(use_per_company: bool = True):
    """
    Build ChromaDB vector store.
    
    Args:
        use_per_company: If True (default), creates separate collection per company.
                        This dramatically speeds up company-filtered queries.
                        If False, uses single 'capex_docs' collection (legacy mode).
    """
    mode_str = "Per-Company Collections" if use_per_company else "Single Collection"
    
    print("=" * 70)
    print("  ENHANCED CAPEX INTELLIGENCE — CHROMADB PIPELINE")
    print(f"  Mode: {mode_str}")
    print("  Features: Parent-Child Chunks | Table Serialization | Structure")
    print("=" * 70)

    # --- ChromaDB ---
    print(f"\n📁 DB path: {DB_PATH}")
    client = chromadb.PersistentClient(path=DB_PATH)
    
    # Company collections (if using per-company mode)
    company_collections = {}
    
    if use_per_company:
        # Delete existing company collections for fresh start
        for company in COMPANY_DISPLAY.values():
            col_name = _get_company_collection_name(company)
            try:
                client.delete_collection(name=col_name)
                print(f"   Deleted existing {col_name}")
            except:
                pass
        print("   Using per-company collections (RAG-Challenge-2 style)")
    else:
        # Legacy single collection mode
        try:
            client.delete_collection(name="capex_docs")
            print("   Deleted existing collection for fresh rebuild")
        except:
            pass
        
        collection = client.create_collection(
            name="capex_docs",
            metadata={"hnsw:space": "cosine"}
        )
        print(f"   Collection: capex_docs | Fresh start")

    # --- Embedding model ---
    print("\n🔄 Loading embedding model (all-mpnet-base-v2)...")
    model = SentenceTransformer("all-mpnet-base-v2")
    print("   ✓ Model loaded (768-dim vectors)")

    # --- Discover files ---
    print("\n📂 Scanning company folders...")
    all_files = discover_all_files()
    print(f"\n   Total files to process: {len(all_files)}")

    if not all_files:
        print("\n❌ No files found. Check folder structure.")
        return

    # --- Process with structure-aware chunking ---
    total_chunks = 0
    total_tables = 0
    stats = defaultdict(lambda: {"files": 0, "chunks": 0, "tables": 0})
    company_stats = defaultdict(lambda: {"files": 0, "chunks": 0, "tables": 0})
    chunk_type_stats = defaultdict(int)
    section_stats = defaultdict(int)  # Track sections discovered

    for filepath, company, filing_type in all_files:
        print(f"  📄 [{company:<11}] {filepath.name[:55]:<55} ", end="", flush=True)

        # Use PAGE-LEVEL Parent Document Retrieval
        # PDF: pages as parents, HTML: sections as parents
        chunks = chunk_document_with_page_parents(filepath, company)
        
        if not chunks:
            print("→ empty/no chunks")
            continue
        
        # Extract a sample for filing type and fiscal quarter detection
        sample_text = ""
        for chunk in chunks[:5]:
            sample_text += chunk.content[:500] + " "
        
        # Use content-based detection for filing type and fiscal quarter
        if not filing_type or filing_type == "Other":
            filing_type = detect_filing_type(filepath, sample_text)
        fy, q = get_fiscal_quarter(filepath, company, sample_text)

        # Count chunk types
        child_count = sum(1 for c in chunks if c.chunk_type == "child")
        parent_count = sum(1 for c in chunks if c.chunk_type == "parent")
        table_count = sum(1 for c in chunks if c.chunk_type == "table")
        
        print(f"→ {len(chunks)} chunks (C:{child_count} P:{parent_count} T:{table_count})", end="", flush=True)

        # Build batch for embedding
        ids, texts, metadatas = [], [], []
        for chunk in chunks:
            ids.append(chunk.chunk_id)
            texts.append(chunk.content)
            
            # Base metadata - always present
            meta = {
                "company": company,
                "source_file": filepath.name,
                "filing_type": filing_type,
                "fiscal_year": fy,
                "quarter": q,
                "chunk_type": chunk.chunk_type,
                "parent_id": chunk.parent_id,
                "parent_type": chunk.parent_type,  # "page" or "section"
            }
            
            # Add structure-aware metadata from chunk
            chunk_meta = chunk.metadata or {}
            
            # Section/Page metadata
            meta["section_header"] = chunk_meta.get("section_header", "")
            meta["section_level"] = chunk_meta.get("section_level", 0)
            meta["page_num"] = chunk_meta.get("page_num", 0)
            
            # For Parent chunks: flag them for easy filtering
            if chunk.chunk_type == "parent":
                meta["is_parent"] = True
            else:
                meta["is_parent"] = False
            
            # Table-specific metadata
            if chunk.chunk_type == "table":
                meta["table_type"] = chunk_meta.get("table_type", "unknown")
                meta["table_context"] = chunk_meta.get("table_context", "")
            
            # Child-specific metadata
            if chunk.chunk_type == "child":
                meta["child_index"] = chunk_meta.get("child_index", 0)
            
            metadatas.append(meta)

        # Get the appropriate collection
        if use_per_company:
            # Get or create company-specific collection
            if company not in company_collections:
                col_name = _get_company_collection_name(company)
                company_collections[company] = client.get_or_create_collection(
                    name=col_name,
                    metadata={"hnsw:space": "cosine", "company": company}
                )
            target_collection = company_collections[company]
        else:
            target_collection = collection
        
        # Embed + upsert in batches of 64
        for start in range(0, len(texts), 64):
            b_ids = ids[start:start + 64]
            b_txt = texts[start:start + 64]
            b_meta = metadatas[start:start + 64]

            embeddings = model.encode(b_txt, show_progress_bar=False)
            target_collection.upsert(
                ids=b_ids,
                embeddings=embeddings.tolist(),
                documents=b_txt,
                metadatas=b_meta,
            )

        total_chunks += len(chunks)
        total_tables += table_count
        stats[filing_type]["files"] += 1
        stats[filing_type]["chunks"] += len(chunks)
        stats[filing_type]["tables"] += table_count
        company_stats[company]["files"] += 1
        company_stats[company]["chunks"] += len(chunks)
        company_stats[company]["tables"] += table_count
        chunk_type_stats["child"] += child_count
        chunk_type_stats["parent"] += parent_count
        chunk_type_stats["table"] += table_count
        
        # Track section headers discovered
        for chunk in chunks:
            section = chunk.metadata.get("section_header", "")
            if section:
                section_stats[section] += 1
        
        print(" ✓")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("  ENHANCED EMBEDDING COMPLETE")
    print("=" * 70)
    
    if use_per_company:
        total_in_db = sum(col.count() for col in company_collections.values())
        print(f"\n  Mode: Per-Company Collections (RAG-Challenge-2 style)")
        print(f"  Collections created: {len(company_collections)}")
        print(f"  Total docs across all collections: {total_in_db}")
    else:
        print(f"\n  Mode: Single Collection (legacy)")
        print(f"  Total docs in collection: {collection.count()}")
    
    print(f"  Total chunks embedded:    {total_chunks}")
    print(f"  Total tables serialized:  {total_tables}\n")

    print(f"  BY CHUNK TYPE:")
    print(f"  {'Type':<14} {'Count':<8}")
    print(f"  {'-' * 24}")
    for ctype, count in sorted(chunk_type_stats.items()):
        print(f"  {ctype:<14} {count:<8}")

    print(f"\n  BY COMPANY:")
    print(f"  {'Company':<14} {'Files':<8} {'Chunks':<10} {'Tables'}")
    print(f"  {'-' * 44}")
    for co in sorted(company_stats.keys()):
        print(f"  {co:<14} {company_stats[co]['files']:<8} {company_stats[co]['chunks']:<10} {company_stats[co]['tables']}")

    print(f"\n  BY FILING TYPE:")
    print(f"  {'Filing Type':<28} {'Files':<8} {'Chunks':<10} {'Tables'}")
    print(f"  {'-' * 58}")
    for ftype in sorted(stats.keys()):
        print(f"  {ftype:<28} {stats[ftype]['files']:<8} {stats[ftype]['chunks']:<10} {stats[ftype]['tables']}")
    
    print(f"\n  BY SEC SECTION (Top 10):")
    print(f"  {'Section':<35} {'Chunks'}")
    print(f"  {'-' * 44}")
    sorted_sections = sorted(section_stats.items(), key=lambda x: -x[1])[:10]
    for section, count in sorted_sections:
        print(f"  {section:<35} {count}")

    print(f"\n  DB stored at: {DB_PATH}")
    
    print("\n  PARENT-CHILD RETRIEVAL READY:")
    print("  - Child chunks: Small, precise matching (~200 words)")
    print("  - Parent chunks: Large context windows (~800 words)")
    print("  - Table chunks: Serialized financial tables")
    print("  - Metadata includes parent_id for context retrieval")

    # --- Smoke tests ---
    print("\n" + "=" * 70)
    print("  SMOKE TESTS")
    print("=" * 70)

    test_queries = [
        ("Single company",  "Flex capital expenditure property equipment"),
        ("Cross-company",   "capital expenditure purchases property equipment manufacturing"),
        ("Competitor",      "Jabil capital investment facility expansion"),
        ("Transcript",      "AI data center liquid cooling investment outlook"),
    ]

    for label, query in test_queries:
        print(f"\n  🔍 [{label}] \"{query}\"")
        q_emb = model.encode([query])
        results = collection.query(
            query_embeddings=q_emb.tolist(),
            n_results=3,
            include=["documents", "metadatas", "distances"]
        )
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            sim = round(1 - dist, 3)
            print(f"     sim={sim}  [{meta['company']:<11}] {meta['source_file']:<50} {meta['filing_type']} | {meta['fiscal_year']} {meta['quarter']}")
            print(f"     {doc[:120]}...")

    print("\n✅ ChromaDB ready for all companies. Next: RAG query layer.")

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    build_db()
