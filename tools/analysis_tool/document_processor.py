"""
Document Processor
==================
Handles loading and processing of SEC filings, earnings calls, and presentations.
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import re
from datetime import datetime

# PDF processing
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

# HTML processing
from bs4 import BeautifulSoup


@dataclass
class Document:
    """Represents a processed document"""
    filename: str
    filepath: str
    doc_type: str  # 10-K, 10-Q, 8-K, earnings_call, presentation, press_release
    company: str
    fiscal_year: Optional[str] = None
    quarter: Optional[str] = None
    date: Optional[str] = None
    content: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class DocumentProcessor:
    """Process and extract text from company documents"""
    
    # Document type patterns (includes foreign issuer forms: 20-F, 6-K)
    DOC_TYPE_PATTERNS = {
        "10-K": [r"10-?K", r"10K", r"annual.*report", r"20-?F", r"20F"],
        "10-Q": [r"10-?Q", r"10Q", r"quarterly.*report", r"6-?K", r"6K"],
        "8-K": [r"8-?K", r"8K"],
        "earnings_call": [r"earnings.*call", r"transcript", r"EarningsCall"],
        "earnings_presentation": [r"earnings.*presentation", r"EarningsPresentation", r"investor.*presentation"],
        "press_release": [r"press.*release", r"EarningsRelease", r"PR_"],
        "shareholder_letter": [r"shareholder.*letter", r"ShareholderLetter"],
    }

    CONTENT_DOC_PATTERNS = {
        "10-K": [
            r"ANNUAL\s*REPORT",
            r"FORM\s*10-K",
            r"FORM\s*20-F",
            r"pursuant\s*to\s*section\s*13\s*or\s*15\(d\)",
            r"fiscal\s*year\s*ended",
            r"annual\s*report\s*on\s*form\s*10-k",
            r"annual\s*report\s*on\s*form\s*20-f",
        ],
        "10-Q": [
            r"QUARTERLY\s*REPORT",
            r"FORM\s*10-Q",
            r"FORM\s*6-K",
            r"quarterly\s*report\s*on\s*form\s*10-q",
            r"quarter\s*ended",
            r"quarterly\s*period\s*ended",
            r"report\s*of\s*foreign\s*private\s*issuer",
        ],
    }
    
    # Fiscal year/quarter patterns
    FY_PATTERNS = [
        r"FY(\d{2,4})",
        r"(\d{4})_",
        r"_(\d{4})_",
        r"(\d{4})-\d{2}-\d{2}",
    ]
    
    QUARTER_PATTERNS = [
        r"Q(\d)",
        r"_Q(\d)",
        r"Q(\d)_",
    ]
    
    def __init__(self, data_dir: Path):
        """
        Initialize the document processor.
        
        Args:
            data_dir: Path to the company's data directory
        """
        self.data_dir = Path(data_dir)
        self.company = self.data_dir.name
        self.documents: List[Document] = []
    
    def load_all_documents(self) -> List[Document]:
        """Load and process all documents in the directory"""
        
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")
        
        # Find all PDF and HTML files
        pdf_files = list(self.data_dir.rglob("*.pdf"))
        html_files = list(self.data_dir.rglob("*.html")) + list(self.data_dir.rglob("*.htm"))
        txt_files = list(self.data_dir.rglob("*.txt"))
        
        all_files = pdf_files + html_files + txt_files
        
        print(f"Found {len(all_files)} documents in {self.data_dir}")
        
        for filepath in all_files:
            try:
                doc = self._process_file(filepath)
                if doc and doc.content:
                    self.documents.append(doc)
            except Exception as e:
                print(f"Error processing {filepath}: {e}")
        
        print(f"Successfully processed {len(self.documents)} documents")
        return self.documents
    
    def _process_file(self, filepath: Path) -> Optional[Document]:
        """Process a single file and extract content"""
        
        filename = filepath.name
        suffix = filepath.suffix.lower()
        
        # Extract content based on file type
        if suffix == ".pdf":
            content = self._extract_pdf(filepath)
        elif suffix in [".html", ".htm"]:
            content = self._extract_html(filepath)
        elif suffix == ".txt":
            content = self._extract_txt(filepath)
        else:
            return None
        
        if not content or len(content.strip()) < 100:
            return None
        
        # Extract document metadata (pass content for fallback detection)
        doc_type = self._detect_doc_type(filename, content)
        fiscal_year = self._extract_fiscal_year(filename, content)
        quarter = self._extract_quarter(filename)
        
        return Document(
            filename=filename,
            filepath=str(filepath),
            doc_type=doc_type,
            company=self.company,
            fiscal_year=fiscal_year,
            quarter=quarter,
            content=content,
            metadata={
                "file_size": filepath.stat().st_size,
                "word_count": len(content.split()),
                "char_count": len(content),
            }
        )
    
    def _detect_doc_type(self, filename: str, content: str = "") -> str:
        """Detect document type using filename patterns, then content-based fallback."""
        filename_lower = filename.lower()

        # Priority: explicit foreign issuer forms
        if re.search(r"6-?k|6k", filename_lower):
            return "10-Q"
        if re.search(r"20-?f|20f", filename_lower):
            return "10-K"

        # Filename pattern matching
        filename_match = None
        for doc_type, patterns in self.DOC_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, filename_lower, re.IGNORECASE):
                    filename_match = doc_type
                    break
            if filename_match:
                break

        # If filename gives a clear non-ambiguous type, use it
        if filename_match and filename_match not in ("10-K", "10-Q", "other", None):
            return filename_match

        # Content-based detection for ambiguous or missing types
        if content and (not filename_match or filename_match in ("10-K", "10-Q", "other")):
            content_sample = content[:5000]
            scores = {}
            for doc_type, patterns in self.CONTENT_DOC_PATTERNS.items():
                score = sum(1 for p in patterns if re.search(p, content_sample, re.IGNORECASE))
                scores[doc_type] = score

            best_type = max(scores, key=scores.get) if scores else None
            if best_type and scores[best_type] >= 2:
                return best_type

        return filename_match or "other"
    
    def _extract_fiscal_year(self, filename: str, content: str = "") -> Optional[str]:
        """Extract fiscal year from filename, falling back to content scanning."""
        for pattern in self.FY_PATTERNS:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                year = match.group(1)
                if len(year) == 2:
                    year = f"20{year}"
                return f"FY{year[-2:]}"

        # Content-based fallback for UUID or non-standard filenames
        if content:
            content_sample = content[:10000]
            fy_content_patterns = [
                r"fiscal\s*year\s*ended\s*.*?(20\d{2})",
                r"year\s*ended\s*(?:january|february|march|april|may|june|july|august|september|october|november|december)\s*\d{1,2}\s*,?\s*(20\d{2})",
                r"for\s*the\s*year\s*ended\s*.*?(20\d{2})",
                r"annual\s*report\s*.*?(20\d{2})",
                r"quarterly\s*(?:report|period)\s*ended\s*.*?(20\d{2})",
            ]
            for pattern in fy_content_patterns:
                match = re.search(pattern, content_sample, re.IGNORECASE)
                if match:
                    return f"FY{match.group(1)[-2:]}"

        return None
    
    def _extract_quarter(self, filename: str) -> Optional[str]:
        """Extract quarter from filename"""
        
        for pattern in self.QUARTER_PATTERNS:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return f"Q{match.group(1)}"
        
        return None
    
    def _extract_pdf(self, filepath: Path) -> str:
        """Extract text from PDF file"""
        
        text = ""
        
        # Try pdfplumber first (better for tables)
        if pdfplumber:
            try:
                with pdfplumber.open(filepath) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n\n"
                if text.strip():
                    return self._clean_text(text)
            except Exception as e:
                print(f"pdfplumber failed for {filepath}: {e}")
        
        # Fallback to PyPDF2
        if PyPDF2:
            try:
                with open(filepath, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n\n"
                return self._clean_text(text)
            except Exception as e:
                print(f"PyPDF2 failed for {filepath}: {e}")
        
        return ""
    
    def _extract_html(self, filepath: Path) -> str:
        """Extract text from HTML file"""
        
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
            
            # Remove script and style elements
            for element in soup(["script", "style", "head", "meta"]):
                element.decompose()
            
            text = soup.get_text(separator="\n", strip=True)
            return self._clean_text(text)
        
        except Exception as e:
            print(f"HTML extraction failed for {filepath}: {e}")
            return ""
    
    def _extract_txt(self, filepath: Path) -> str:
        """Extract text from TXT file"""
        
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            return self._clean_text(text)
        except Exception as e:
            print(f"TXT extraction failed for {filepath}: {e}")
            return ""
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        
        # Replace multiple newlines with double newline
        text = re.sub(r"\n{3,}", "\n\n", text)
        
        # Replace multiple spaces with single space
        text = re.sub(r" {2,}", " ", text)
        
        # Remove form feed and other control characters
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        
        # Strip leading/trailing whitespace
        text = text.strip()
        
        return text
    
    def get_documents_by_type(self, doc_type: str) -> List[Document]:
        """Get documents filtered by type"""
        return [doc for doc in self.documents if doc.doc_type == doc_type]
    
    def get_documents_by_year(self, fiscal_year: str) -> List[Document]:
        """Get documents filtered by fiscal year"""
        return [doc for doc in self.documents if doc.fiscal_year == fiscal_year]
    
    def get_10k_documents(self) -> List[Document]:
        """Get all 10-K documents"""
        return self.get_documents_by_type("10-K")
    
    def get_10q_documents(self) -> List[Document]:
        """Get all 10-Q documents"""
        return self.get_documents_by_type("10-Q")
    
    def get_earnings_calls(self) -> List[Document]:
        """Get all earnings call transcripts"""
        return self.get_documents_by_type("earnings_call")
    
    def get_presentations(self) -> List[Document]:
        """Get all earnings/investor presentations"""
        return self.get_documents_by_type("earnings_presentation")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of loaded documents"""
        
        type_counts = {}
        year_counts = {}
        total_words = 0
        
        for doc in self.documents:
            type_counts[doc.doc_type] = type_counts.get(doc.doc_type, 0) + 1
            if doc.fiscal_year:
                year_counts[doc.fiscal_year] = year_counts.get(doc.fiscal_year, 0) + 1
            total_words += doc.metadata.get("word_count", 0)
        
        return {
            "total_documents": len(self.documents),
            "by_type": type_counts,
            "by_year": year_counts,
            "total_words": total_words,
            "company": self.company,
        }


# Utility functions for specific document sections
def extract_mda_section(content: str) -> str:
    """Extract MD&A (Management Discussion & Analysis) section from 10-K/10-Q"""
    
    # Common MD&A headers
    patterns = [
        r"ITEM\s*7[\.:]\s*MANAGEMENT.S\s*DISCUSSION\s*AND\s*ANALYSIS",
        r"Management.s\s*Discussion\s*and\s*Analysis",
        r"MD&A",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            start = match.start()
            # Find the next ITEM section
            next_item = re.search(r"ITEM\s*\d+[\.:A-Z]", content[start + 100:], re.IGNORECASE)
            if next_item:
                end = start + 100 + next_item.start()
            else:
                end = start + 50000  # Take up to 50k chars
            return content[start:end]
    
    return ""


def extract_risk_factors(content: str) -> str:
    """Extract Risk Factors section from 10-K"""
    
    patterns = [
        r"ITEM\s*1A[\.:]\s*RISK\s*FACTORS",
        r"Risk\s*Factors",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            start = match.start()
            next_item = re.search(r"ITEM\s*\d+[\.:A-Z]", content[start + 100:], re.IGNORECASE)
            if next_item:
                end = start + 100 + next_item.start()
            else:
                end = start + 50000
            return content[start:end]
    
    return ""


def extract_financial_statements(content: str) -> str:
    """Extract Financial Statements section"""
    
    patterns = [
        r"ITEM\s*8[\.:]\s*FINANCIAL\s*STATEMENTS",
        r"Consolidated\s*Statements\s*of\s*Operations",
        r"Consolidated\s*Balance\s*Sheet",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            start = match.start()
            end = start + 30000
            return content[start:end]
    
    return ""


def extract_capex_mentions(content: str) -> List[str]:
    """Extract paragraphs mentioning capital expenditures"""
    
    keywords = [
        r"capital\s*expenditure",
        r"capex",
        r"property.*plant.*equipment",
        r"facility\s*expansion",
        r"new\s*facility",
        r"manufacturing\s*capacity",
        r"invested\s*in",
        r"investment\s*in\s*\$",
    ]
    
    paragraphs = content.split("\n\n")
    matches = []
    
    for para in paragraphs:
        for keyword in keywords:
            if re.search(keyword, para, re.IGNORECASE):
                if len(para) > 50 and para not in matches:
                    matches.append(para)
                break
    
    return matches
