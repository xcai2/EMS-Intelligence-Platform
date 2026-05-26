"""
Document processing pipeline for new SEC filings.
Enhanced with STRUCTURE-AWARE chunking (RAG-Challenge-2 style).

Features:
- Split by SEC section headers (not fixed word count)
- Rich metadata: section_header, section_level, page_num, etc.
- Parent-child hierarchy for context retrieval
"""
import re
import hashlib
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from backend.core.database import get_collection, embed_texts


# ---------------------------------------------------------------------------
# SEC SECTION PATTERNS (same as build_chromadb.py)
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


# ---------------------------------------------------------------------------
# TEXT CLEANING
# ---------------------------------------------------------------------------
def _clean_text(text: str) -> str:
    """Clean extracted text."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# TEXT EXTRACTION (supports HTML, PDF, TXT)
# ---------------------------------------------------------------------------
def _extract_text(filepath: Path) -> str:
    """Extract text from HTML, PDF, or TXT files."""
    suffix = filepath.suffix.lower()

    if suffix in (".html", ".htm"):
        from bs4 import BeautifulSoup
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        for el in soup(["script", "style", "head", "meta"]):
            el.decompose()
        return _clean_text(soup.get_text(separator="\n", strip=True))

    elif suffix == ".pdf":
        try:
            import pdfplumber
            text = ""
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n\n"
            if text.strip():
                return _clean_text(text)
        except Exception:
            pass

        try:
            import PyPDF2
            text = ""
            with open(filepath, "rb") as f:
                for page in PyPDF2.PdfReader(f).pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
            return _clean_text(text)
        except Exception:
            pass
    
    elif suffix in (".txt", ".md"):
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return _clean_text(f.read())
        except Exception:
            pass

    return ""


# ---------------------------------------------------------------------------
# STRUCTURE-AWARE CHUNKING (RAG-Challenge-2 Style)
# ---------------------------------------------------------------------------
# Size limits (soft targets, respect natural boundaries)
MAX_SECTION_WORDS = 1500
MIN_CHUNK_WORDS = 100
TARGET_CHILD_WORDS = 250
TARGET_PARENT_WORDS = 800


@dataclass
class ChunkWithParent:
    """A chunk with parent reference for Parent Document Retrieval."""
    chunk_id: str
    content: str
    parent_id: str
    parent_content: str
    chunk_type: str
    metadata: dict = field(default_factory=dict)


def _generate_chunk_id(company: str, filename: str, chunk_index: int, chunk_type: str) -> str:
    """Generate a unique chunk ID."""
    base = f"{company}_{filename}_{chunk_type}_{chunk_index}"
    return hashlib.md5(base.encode()).hexdigest()[:16]


def _split_by_sections(text: str) -> list:
    """Split text by SEC filing section headers."""
    sections = []
    lines = text.split("\n")
    
    current_section = "Document Start"
    current_level = 0
    current_content = []
    
    for line in lines:
        line_clean = line.strip()
        line_upper = line_clean.upper()
        
        found_header = False
        for pattern, section_name, level in SEC_SECTION_PATTERNS:
            if re.search(pattern, line_upper):
                if current_content:
                    content_text = "\n".join(current_content).strip()
                    if content_text:
                        sections.append((current_section, content_text, current_level))
                
                current_section = section_name
                current_level = level
                current_content = [line_clean]
                found_header = True
                break
        
        if not found_header:
            current_content.append(line)
    
    if current_content:
        content_text = "\n".join(current_content).strip()
        if content_text:
            sections.append((current_section, content_text, current_level))
    
    return sections


def _split_by_paragraphs(text: str) -> list:
    """Split text by paragraphs, merging small ones."""
    raw_paragraphs = re.split(r'\n\s*\n', text)
    
    paragraphs = []
    current_para = []
    current_words = 0
    
    for para in raw_paragraphs:
        para = para.strip()
        if not para:
            continue
        
        para_words = len(para.split())
        
        if current_words + para_words < MIN_CHUNK_WORDS:
            current_para.append(para)
            current_words += para_words
        else:
            if current_para:
                paragraphs.append("\n\n".join(current_para))
            current_para = [para]
            current_words = para_words
    
    if current_para:
        paragraphs.append("\n\n".join(current_para))
    
    return paragraphs


def _split_long_paragraph(text: str, target_words: int) -> list:
    """Split a long paragraph by sentences."""
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


def _chunk_text_simple(text: str, chunk_words: int = 250, overlap_words: int = 50) -> list[str]:
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


def _chunk_with_parent_child(text: str, company: str, filename: str) -> list[ChunkWithParent]:
    """
    Create STRUCTURE-AWARE parent-child chunks.
    
    Process:
    1. Split by SEC section headers
    2. Within sections, split by paragraphs
    3. Create parent-child relationships within sections
    """
    chunks = []
    
    if not text or len(text.strip()) < MIN_CHUNK_WORDS:
        return chunks
    
    # Step 1: Split by sections
    sections = _split_by_sections(text)
    if not sections or len(sections) == 1:
        sections = [("Full Document", text, 0)]
    
    # Step 2: Process each section
    chunk_base_idx = 0
    for section_name, section_content, section_level in sections:
        section_words = len(section_content.split())
        
        if section_words < MIN_CHUNK_WORDS:
            continue
        
        # Split by paragraphs
        paragraphs = _split_by_paragraphs(section_content)
        
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
        
        # Create parent-child chunks
        for p_idx, parent_paragraphs in enumerate(parent_groups):
            parent_content = "\n\n".join(parent_paragraphs)
            parent_id = _generate_chunk_id(company, filename, chunk_base_idx + p_idx, f"parent_{section_name[:10]}")
            
            # Parent chunk
            chunks.append(ChunkWithParent(
                chunk_id=parent_id,
                content=parent_content,
                parent_id=parent_id,
                parent_content=parent_content,
                chunk_type="parent",
                metadata={
                    "section_header": section_name,
                    "section_level": section_level,
                },
            ))
            
            # Child chunks
            child_idx = 0
            for para in parent_paragraphs:
                para_words = len(para.split())
                
                if para_words > TARGET_CHILD_WORDS * 1.5:
                    sub_chunks = _split_long_paragraph(para, TARGET_CHILD_WORDS)
                else:
                    sub_chunks = [para] if para_words >= MIN_CHUNK_WORDS else []
                
                for sub_chunk in sub_chunks:
                    if len(sub_chunk.split()) < MIN_CHUNK_WORDS // 2:
                        continue
                    
                    child_id = _generate_chunk_id(
                        company, filename,
                        chunk_base_idx * 100 + p_idx * 10 + child_idx,
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
                            "child_index": child_idx,
                        },
                    ))
                    child_idx += 1
        
        chunk_base_idx += len(paragraphs) + 1
    
    return chunks


def process_filing(
    filepath: Path,
    company: str,
    filing_type: str,
    fiscal_year: str = "Unknown",
    quarter: str = "",
    use_parent_child: bool = True,
    collection=None,
) -> int:
    """
    Process a single filing: extract, chunk, embed, and upsert into ChromaDB.

    Uses parent-child chunking for better retrieval when use_parent_child=True.
    Pass `collection` to write to a specific collection (e.g. company-specific);
    defaults to the shared collection from get_collection().

    Returns the number of chunks added.
    """
    text = _extract_text(filepath)
    if not text or len(text.strip()) < 100:
        return 0

    if collection is None:
        collection = get_collection()
    safe_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", filepath.stem)

    if use_parent_child:
        # Structure-aware parent-child chunking
        chunks = _chunk_with_parent_child(text, company, safe_stem)
        if not chunks:
            return 0
        
        ids = []
        texts = []
        metadatas = []
        
        for chunk in chunks:
            ids.append(chunk.chunk_id)
            texts.append(chunk.content)
            
            # Base metadata
            meta = {
                "company": company,
                "source_file": filepath.name,
                "filing_type": filing_type,
                "fiscal_year": fiscal_year,
                "quarter": quarter,
                "chunk_type": chunk.chunk_type,
                "parent_id": chunk.parent_id,
                "parent_preview": chunk.parent_content[:500] if chunk.chunk_type == "child" else "",
            }
            
            # Structure-aware metadata from chunk
            chunk_meta = chunk.metadata or {}
            meta["section_header"] = chunk_meta.get("section_header", "")
            meta["section_level"] = chunk_meta.get("section_level", 0)
            meta["page_num"] = chunk_meta.get("page_num", 0)
            
            if chunk.chunk_type == "child":
                meta["child_index"] = chunk_meta.get("child_index", 0)
            
            metadatas.append(meta)
        
        embeddings = embed_texts(texts)
        
    else:
        # Legacy simple chunking (fallback)
        simple_chunks = _chunk_text_simple(text)
        if not simple_chunks:
            return 0
        
        ids = []
        texts = simple_chunks
        metadatas = []
        
        for i, chunk in enumerate(simple_chunks):
            ids.append(f"{company}_{safe_stem}_chunk{i:04d}")
            metadatas.append({
                "company": company,
                "source_file": filepath.name,
                "filing_type": filing_type,
                "fiscal_year": fiscal_year,
                "quarter": quarter,
                "chunk_index": i,
                "total_chunks": len(simple_chunks),
                "chunk_type": "legacy",
                "parent_id": "",
                "section_header": "",
                "section_level": 0,
                "page_num": 0,
            })
        
        embeddings = embed_texts(texts)

    # Upsert in batches
    batch_size = 64
    for start in range(0, len(texts), batch_size):
        end = start + batch_size
        collection.upsert(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            documents=texts[start:end],
            metadatas=metadatas[start:end],
        )

    return len(texts)


def process_new_filings(filings: list[dict]) -> dict:
    """
    Process a batch of newly downloaded filings.

    Args:
        filings: List of dicts with keys: filepath, company, filing_type, etc.

    Returns:
        Summary dict with counts
    """
    total_files = 0
    total_chunks = 0
    errors = []

    for filing in filings:
        filepath = Path(filing.get("filepath", ""))
        if not filepath.exists():
            errors.append(f"File not found: {filepath}")
            continue

        try:
            chunks = process_filing(
                filepath=filepath,
                company=filing.get("company", "Unknown"),
                filing_type=filing.get("filing_type", "Unknown"),
                fiscal_year=filing.get("fiscal_year", "Unknown"),
                quarter=filing.get("quarter", ""),
            )
            total_files += 1
            total_chunks += chunks
            print(f"  Processed {filepath.name}: {chunks} chunks")
        except Exception as e:
            errors.append(f"{filepath.name}: {e}")

    return {
        "files_processed": total_files,
        "chunks_added": total_chunks,
        "errors": errors,
    }
