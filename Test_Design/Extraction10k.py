#!/usr/bin/env python3
"""
10-K Annual Report Extractor  —  Chunk & Embedding Ready
=========================================================

Design goals
------------
1. Output is a list of *chunk-ready sections*, each with clean prose text,
   structured table markdown, and rich metadata for retrieval.
2. Financial tables (Balance Sheet, Income Statement, Cash Flow, etc.) are
   reconstructed as clean Markdown tables instead of flat noisy text.
3. Tables are assigned to sections via DOM position markers — not text
   overlap — so every table goes to exactly the right section.
4. TOC / cover noise is stripped before section detection by locating the
   second occurrence of "Part I" (the true document body start).
5. ALL Item sections are extracted (not only the "preferred" 5) so the
   caller's RAG pipeline can decide which items to include.
6. Works for both HTML (.html / .htm) and PDF (.pdf) source files.
     PDF  -> docling (best quality) -> pypdf fall-back
     HTML -> BeautifulSoup with XBRL/iXBRL tag stripping

Output JSON schema
------------------
{
  "source":   { file_name, suffix, size_bytes, ... },
  "document": { registrant_name, period_of_report, form_type, ... },
  "sections": [
    {
      "section_id":   "s001",
      "item_code":    "8",
      "item_label":   "Item 8",
      "header":       "Item 8  FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA",
      "section_part": "Part II",
      "section_type": "filing_item",
      "is_tail":      false,
      "has_legal_boilerplate": false,
      "char_count":   161481,
      "word_count":   24817,
      "chunks": [
        {
          "chunk_id":    "s008-c001",
          "text":        "... clean prose or markdown table ...",
          "char_count":  1400,
          "word_count":  210,
          "has_table":   false,
          "table_titles": []
        }, ...
      ],
      "tables": [
        {
          "table_id":   "s008-t001",
          "title":      "CONSOLIDATED BALANCE SHEETS",
          "markdown":   "| Item | 2022 | 2021 |\\n|---|---|---|\\n...",
          "row_count":  37
        }, ...
      ]
    }, ...
  ],
  "quality": { totals, item_codes_found, missing_items, warnings, ... }
}

Chunking strategy
-----------------
* Target: ~800 words per prose chunk, ~100-word overlap between chunks.
* Tables are emitted as self-contained chunks (never split mid-table).
* Each chunk carries section_id / item_code as metadata.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .extraction_output_utils import prepare_output_root, prepare_shared_sample_dir
except ImportError:
    from extraction_output_utils import prepare_output_root, prepare_shared_sample_dir

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "File" / "Flex" / "annual_10K"
OUTPUT_PARENT_DIR = BASE_DIR / "File"
SUPPORTED_SUFFIXES = {".pdf", ".html", ".htm", ".txt", ".md"}
ENABLE_DOCLING_PDF = False

CHUNK_TARGET_WORDS = 800
CHUNK_OVERLAP_WORDS = 100

TAIL_ITEMS = {"15", "16"}

_PART_RE = re.compile(r"^\s*part\s+(I{1,3}V?|IV)\s*[.:\-\s]*(.*)$", re.IGNORECASE)
_ITEM_RE = re.compile(r"^\s*item\s+(\d{1,2}[A-Ca-c]?)\s*[.:\-\s]*(.*)$", re.IGNORECASE)
_SIGNATURE_RE = re.compile(r"^\s*signatures?\s*$", re.IGNORECASE)
_PAGE_NUM_RE = re.compile(r"^\s*\d{1,3}\s*$")
_LEGAL_PATTERNS = [
    re.compile(r"shall\s+not\s+be\s+deemed\s+[\"']?filed[\"']?", re.IGNORECASE),
    re.compile(r"incorporated\s+by\s+reference", re.IGNORECASE),
]
_DATE_RE = re.compile(
    r"([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"
)
_TBL_MARKER_RE = re.compile(r"__TBL_(\d{4})__")

# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\u00ad", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_prose(text: str) -> str:
    """Strip page numbers, lone punctuation, and separator lines."""
    lines = text.splitlines()
    kept = []
    for ln in lines:
        s = ln.strip()
        if not s:
            kept.append("")
            continue
        if _PAGE_NUM_RE.match(s):
            continue
        if re.match(r"^[-=_*]{3,}$", s):
            continue
        if re.match(r"^[$%#&*]{1,2}$", s):
            continue
        kept.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _read_text_file(filepath: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return filepath.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return filepath.read_text(errors="ignore")


# ---------------------------------------------------------------------------
# HTML parser  (returns full_text with DOM markers + raw table objects)
# ---------------------------------------------------------------------------

def _parse_html(filepath: Path) -> tuple[str, list, list[str]]:
    """
    Parse HTML file.
    Returns (full_text_with_markers, raw_table_tags, warnings).

    Each <table> element gets a unique text marker injected just before it:
        __TBL_0012__
    This marker survives get_text() so we can later locate each table within
    a section purely by string position — no fragile text-overlap heuristics.
    """
    warnings: list[str] = ["parser:bs4"]
    raw = _read_text_file(filepath)

    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        warnings.append("bs4_not_installed")
        return _clean_text(raw), [], warnings

    soup = BeautifulSoup(raw, "html.parser")

    # Remove non-content nodes
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()

    # Strip XBRL wrappers but preserve text
    for tag in soup.find_all(True):
        name = (tag.name or "").lower()
        if name in {"ix:header", "ix:hidden"}:
            tag.decompose()
            continue
        if name.startswith(("ix:", "xbrli:")):
            try:
                tag.unwrap()
            except Exception:
                pass
            continue
        if name.startswith(("link:", "dei:", "us-gaap:")):
            tag.decompose()

    # Inject a '\n' sentinel at the end of every block-level element so that
    # adjacent <div>/<p>/<li> blocks produce double-newlines in get_text(),
    # which later become paragraph boundaries for chunking.
    _BLOCK_TAGS = {
        "div", "p", "section", "article", "li",
        "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
    }
    for tag in soup.find_all(_BLOCK_TAGS):
        sentinel = soup.new_tag("span")
        sentinel.string = "\n"
        tag.append(sentinel)

    # Save raw table elements, then inject position markers
    table_tags = soup.find_all("table")
    for i, tbl in enumerate(table_tags):
        marker_tag = soup.new_tag("span")
        marker_tag.string = f"__TBL_{i:04d}__"
        tbl.insert_before(marker_tag)

    root = soup.find("article") or soup.find("main") or soup.body or soup
    # strip=False to preserve the sentinel newlines we just injected
    raw_text = root.get_text("\n", strip=False)
    text = _clean_text(raw_text)
    return text, table_tags, warnings


# ---------------------------------------------------------------------------
# PDF parsers
# ---------------------------------------------------------------------------

def _parse_pdf_docling(filepath: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        from docling.document_converter import DocumentConverter  # type: ignore
    except ImportError:
        warnings.append("docling_not_installed")
        return "", warnings
    try:
        converter = DocumentConverter()
        result = converter.convert(str(filepath))
        doc = getattr(result, "document", None)
        if doc is None:
            warnings.append("docling_no_document")
            return "", warnings
        if hasattr(doc, "export_to_markdown"):
            text = doc.export_to_markdown() or ""
        elif hasattr(doc, "export_to_text"):
            text = doc.export_to_text() or ""
        else:
            text = str(doc)
        return _clean_text(text), warnings + ["parser:docling"]
    except Exception as e:
        warnings.append(f"docling_error:{e}")
        return "", warnings


def _parse_pdf_pypdf(filepath: Path) -> tuple[list[dict], str, list[str]]:
    warnings: list[str] = ["parser:pypdf"]
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        warnings.append("pypdf_not_installed")
        return [], "", warnings
    try:
        reader = PdfReader(str(filepath))
    except Exception as e:
        warnings.append(f"pdf_open_error:{e}")
        return [], "", warnings

    pages = []
    texts = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = _clean_text(page.extract_text() or "")
        except Exception:
            txt = ""
        pages.append({"page_num": i, "text": txt, "char_count": len(txt)})
        if txt:
            texts.append(txt)
    return pages, _clean_text("\n\n".join(texts)), warnings


def _parse_pdf_pdfplumber(filepath: Path) -> tuple[list[dict], str, list[str]]:
    warnings: list[str] = ["parser:pdfplumber"]
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        warnings.append("pdfplumber_not_installed")
        return [], "", warnings

    pages = []
    texts = []
    try:
        with pdfplumber.open(str(filepath)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    txt = _clean_text(page.extract_text() or "")
                except Exception:
                    txt = ""
                pages.append({"page_num": i, "text": txt, "char_count": len(txt)})
                if txt:
                    texts.append(txt)
    except Exception as e:
        warnings.append(f"pdfplumber_open_error:{e}")
        return [], "", warnings

    return pages, _clean_text("\n\n".join(texts)), warnings


def _parse_pdf_text_fallback(filepath: Path) -> tuple[list[dict], str, list[str]]:
    pages, text, warnings = _parse_pdf_pypdf(filepath)
    if text:
        return pages, text, warnings

    pdfplumber_pages, pdfplumber_text, pdfplumber_warnings = _parse_pdf_pdfplumber(filepath)
    return pdfplumber_pages, pdfplumber_text, warnings + pdfplumber_warnings


# ---------------------------------------------------------------------------
# Unified source parser
# ---------------------------------------------------------------------------

def _parse_source(
    filepath: Path, suffix: str
) -> tuple[list[dict], str, list, list[str]]:
    """Returns (pages, full_text, table_tags, warnings)."""
    if suffix == ".pdf":
        docling_warnings: list[str] = []
        if ENABLE_DOCLING_PDF:
            docling_text, docling_warnings = _parse_pdf_docling(filepath)
            if docling_text:
                return [], docling_text, [], docling_warnings
        pages, text, warnings = _parse_pdf_text_fallback(filepath)
        return pages, text, [], docling_warnings + warnings

    if suffix in {".html", ".htm"}:
        text, table_tags, warnings = _parse_html(filepath)
        return [], text, table_tags, warnings

    if suffix in {".txt", ".md"}:
        return [], _clean_text(_read_text_file(filepath)), [], []

    return [], "", [], [f"unsupported_file_type:{suffix}"]


# ---------------------------------------------------------------------------
# Table -> Markdown  (SEC EDGAR HTML specialised)
# ---------------------------------------------------------------------------

def _html_table_to_markdown(table_tag) -> tuple[str, int]:
    """
    Convert a BeautifulSoup <table> to clean Markdown.

    SEC EDGAR HTML tables have a quirky structure:
    * Standalone '$' cells precede numeric cells:
        ['Cash ...', '$', '2,964', '', '$', '2,637', '']
    * Empty <td> cells are XBRL alignment spacers with no content.

    Strategy per row:
    1. Merge a bare '$' cell into the next non-empty cell -> "$2,964"
    2. Drop all remaining empty cells.
    Then normalise every row to the same column count and build Markdown.
    """
    rows_raw = table_tag.find_all("tr")
    if not rows_raw:
        return "", 0

    def cell_text(cell) -> str:
        return re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip()

    def compress_row(raw: list[str]) -> list[str]:
        result: list[str] = []
        i = 0
        while i < len(raw):
            cell = raw[i]
            if cell in {"$", "($)", "( $ )"}:
                j = i + 1
                while j < len(raw) and not raw[j]:
                    j += 1
                if j < len(raw) and raw[j]:
                    result.append(cell + raw[j])
                    i = j + 1
                else:
                    i += 1  # orphaned $, skip
            elif cell:
                result.append(cell)
                i += 1
            else:
                i += 1  # empty spacer, skip
        return result

    grid: list[list[str]] = []
    for tr in rows_raw:
        cells = [cell_text(c) for c in tr.find_all(["th", "td"])]
        if not any(cells):
            continue
        compressed = compress_row(cells)
        if compressed:
            grid.append(compressed)

    if not grid:
        return "", 0

    max_cols = max(len(r) for r in grid)
    grid = [r + [""] * (max_cols - len(r)) for r in grid]

    # Drop completely-empty columns
    keep_cols = [
        c for c in range(max_cols)
        if any(grid[r][c] for r in range(len(grid)))
    ]
    if not keep_cols:
        return "", 0
    grid = [[row[c] for c in keep_cols] for row in grid]

    def md_row(cells: list[str]) -> str:
        return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"

    lines = [md_row(grid[0]), md_row(["---"] * len(grid[0]))]
    for row in grid[1:]:
        lines.append(md_row(row))
    return "\n".join(lines), len(grid) - 1


def _find_table_title(table_tag, body_lines: list[str], marker_line_idx: int) -> str:
    """
    Find the best title for a table.

    Strategy (in priority order):
    1. Walk up the DOM from the table, then scan backward through previous
       siblings at each level.  The first non-trivial text node (8–200 chars,
       not a page number, not another table marker) is taken as the title.
       This works well for SEC EDGAR HTML where the caption is in a sibling
       <div> rather than a <caption> element.
    2. Fall back to scanning body_lines backwards from the marker position.
    3. Last resort: use the first non-empty header row of the table itself.
    """
    _SKIP = re.compile(
        r"^(table\s+of\s+contents|\d{1,3}|[-=_*]{3,})$", re.IGNORECASE
    )

    def _clean(t: str) -> str:
        return re.sub(r"\s+", " ", t).strip()

    # --- Strategy 1: DOM traversal ---
    node = table_tag
    for _ in range(5):  # climb at most 5 levels
        prev = node.find_previous_sibling()
        while prev:
            try:
                txt = _clean(prev.get_text(" ", strip=True))
            except Exception:
                txt = ""
            if txt and 8 <= len(txt) <= 250 and not _SKIP.match(txt) and not _TBL_MARKER_RE.search(txt):
                return txt
            prev = prev.find_previous_sibling()
        parent = getattr(node, "parent", None)
        if parent is None:
            break
        node = parent

    # --- Strategy 2: scan body_lines backward ---
    _FIN_KW = re.compile(
        r"(consolidated|balance\s+sheet|statement|income|cash\s+flow|"
        r"revenue|earnings|equity|segment|operations|comprehensive)",
        re.IGNORECASE,
    )
    start = max(0, marker_line_idx - 8)
    candidates: list[str] = []
    for line in reversed(body_lines[start:marker_line_idx]):
        s = line.strip()
        if not s or _PAGE_NUM_RE.match(s) or _TBL_MARKER_RE.search(s) or _SKIP.match(s):
            continue
        if len(s) < 8:
            continue
        candidates.append(s)
        if _FIN_KW.search(s):
            return s

    if candidates:
        return max(candidates, key=len)

    # --- Strategy 3: first header row ---
    rows = table_tag.find_all("tr")
    for row in rows[:3]:
        cells = [
            _clean(c.get_text(" ", strip=True))
            for c in row.find_all(["th", "td"])
        ]
        non_empty = [c for c in cells if c]
        if non_empty and len(" ".join(non_empty)) > 8:
            return " | ".join(non_empty[:4])
    return ""


# ---------------------------------------------------------------------------
# Body start detection  (skip TOC / cover page)
# ---------------------------------------------------------------------------

def _find_body_start(lines: list[str]) -> int:
    """
    The TOC lists all Part / Item headings once.
    The real body repeats them with actual content.
    We look for the SECOND occurrence of "Part I" or "Item 1".
    """
    part1: list[int] = []
    item1: list[int] = []
    for i, line in enumerate(lines):
        pm = _PART_RE.match(line)
        if pm and pm.group(1).upper() in {"I", "1"}:
            part1.append(i)
        im = _ITEM_RE.match(line)
        if im and im.group(1).upper() == "1":
            item1.append(i)

    if len(part1) >= 2:
        return part1[1]
    if len(item1) >= 2:
        return item1[1]
    if part1:
        return part1[0]
    if item1:
        return item1[0]
    for i, line in enumerate(lines):
        if _ITEM_RE.match(line) or _PART_RE.match(line):
            return i
    return 0


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

def _detect_headings(body_lines: list[str]) -> list[dict]:
    headings: list[dict] = []
    current_part = ""
    for i, line in enumerate(body_lines):
        if _TBL_MARKER_RE.match(line.strip()):
            continue
        pm = _PART_RE.match(line)
        if pm:
            current_part = f"Part {pm.group(1).upper()}"
            rest = (pm.group(2) or "").strip()
            headings.append({
                "start": i,
                "body_start": i + 1,
                "header": current_part + (f"  {rest}" if rest else ""),
                "item_code": "",
                "section_part": current_part,
                "is_part_header": True,
            })
            continue
        im = _ITEM_RE.match(line)
        if im:
            code = im.group(1).upper()
            rest = (im.group(2) or "").strip()
            body_start = i + 1
            if not rest and i + 1 < len(body_lines):
                nxt = body_lines[i + 1].strip()
                if (nxt and not _ITEM_RE.match(nxt) and not _PART_RE.match(nxt)
                        and not _TBL_MARKER_RE.search(nxt) and len(nxt) < 150):
                    rest = nxt
                    body_start = i + 2
            headings.append({
                "start": i,
                "body_start": body_start,
                "header": f"Item {code}" + (f"  {rest}" if rest else ""),
                "item_code": code,
                "section_part": current_part,
                "is_part_header": False,
            })
            continue
        if _SIGNATURE_RE.match(line):
            headings.append({
                "start": i,
                "body_start": i + 1,
                "header": "SIGNATURES",
                "item_code": "",
                "section_part": "",
                "is_part_header": False,
            })
    return headings


# ---------------------------------------------------------------------------
# Section content cleaning
# ---------------------------------------------------------------------------

def _clean_section_body(body_lines: list[str]) -> tuple[str, bool]:
    """Remove page numbers, table markers, and legal boilerplate lines."""
    kept: list[str] = []
    has_legal = False
    for line in body_lines:
        s = line.strip()
        if _PAGE_NUM_RE.match(s):
            continue
        if _TBL_MARKER_RE.search(s):
            continue
        if any(p.search(line) for p in _LEGAL_PATTERNS):
            has_legal = True
            continue
        kept.append(line)
    while kept and _PAGE_NUM_RE.match(kept[-1].strip()):
        kept.pop()
    return _clean_prose("\n".join(kept)), has_legal


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _split_into_chunks(
    prose: str,
    tables: list[dict],
    section_id: str,
) -> list[dict]:
    """
    Split section text + tables into overlapping chunks.

    Chunking strategy
    -----------------
    * Tables are emitted as whole, self-contained chunks (never split).
    * Prose is split by sentence boundary (period/question/exclamation
      followed by whitespace + capital letter).  Sentences are accumulated
      until CHUNK_TARGET_WORDS is reached, then flushed.  The last
      CHUNK_OVERLAP_WORDS of each chunk seed the next one for context
      continuity.
    * Short paragraphs / bullet points that don't end with terminal
      punctuation are treated as single sentence units.
    """
    if not prose.strip() and not tables:
        return []

    table_by_title: dict[str, dict] = {
        t["title"]: t for t in tables if t.get("title")
    }

    # ---- Sentence splitting ----
    # Split on sentence-ending punctuation followed by whitespace + uppercase.
    # This handles most English prose; bullet lists are left intact.
    _SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z\(\"\'])')

    # Normalise prose: collapse single newlines to spaces, keep double-newlines
    # as paragraph boundaries (converted to ". " so they act as sentence breaks)
    prose_normalised = re.sub(r'\n\n+', '.  ', prose)   # paragraph = sentence boundary
    prose_normalised = re.sub(r'\n', ' ', prose_normalised)
    prose_normalised = re.sub(r'[ \t]{2,}', ' ', prose_normalised).strip()

    sentences = _SENT_SPLIT.split(prose_normalised)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks: list[dict] = []
    chunk_idx = 0
    current_sents: list[str] = []
    current_words = 0
    prev_tail: list[str] = []

    def _flush_prose(sents: list[str]) -> None:
        nonlocal chunk_idx, prev_tail
        if not sents:
            return
        text = " ".join(sents)
        if prev_tail:
            text = " ".join(prev_tail) + " " + text
        text = text.strip()
        chunk_idx += 1
        words = text.split()
        chunks.append({
            "chunk_id": f"{section_id}-c{chunk_idx:03d}",
            "text": text,
            "char_count": len(text),
            "word_count": len(words),
            "has_table": False,
            "table_titles": [],
        })
        prev_tail = words[-CHUNK_OVERLAP_WORDS:] if len(words) > CHUNK_OVERLAP_WORDS else words[:]

    def _flush_table(tbl: dict) -> None:
        nonlocal chunk_idx, prev_tail
        title = tbl.get("title", "")
        table_text = (f"**{title}**\n\n{tbl['markdown']}" if title else tbl["markdown"])
        chunk_idx += 1
        chunks.append({
            "chunk_id": f"{section_id}-c{chunk_idx:03d}",
            "text": table_text,
            "char_count": len(table_text),
            "word_count": len(table_text.split()),
            "has_table": True,
            "table_titles": [title],
        })
        prev_tail = []  # tables don't seed prose overlap

    for sent in sentences:
        sent_words = len(sent.split())

        # Check if this sentence anchors a table title
        matched_table = None
        for title, tbl in table_by_title.items():
            if title and title[:50] in sent:
                matched_table = tbl
                break

        if matched_table:
            _flush_prose(current_sents)
            current_sents = []
            current_words = 0
            _flush_table(matched_table)
            continue

        if current_words + sent_words > CHUNK_TARGET_WORDS and current_sents:
            _flush_prose(current_sents)
            current_sents = [sent]
            current_words = sent_words
        else:
            current_sents.append(sent)
            current_words += sent_words

    _flush_prose(current_sents)

    # Tables not anchored in prose -> append at end
    anchored = {
        t["title"] for t in tables
        if t.get("title") and t["title"][:50] in prose
    }
    for tbl in tables:
        if tbl.get("title", "") not in anchored:
            _flush_table(tbl)

    return chunks


# ---------------------------------------------------------------------------
# Document metadata (cover page)
# ---------------------------------------------------------------------------

def _extract_document_metadata(lines: list[str], filename: str) -> dict:
    fields: dict[str, str] = {
        "form_type": "10-K",
        "registrant_name": "",
        "period_of_report": "",
        "fiscal_year_end": "",
        "commission_file_number": "",
    }
    for i, line in enumerate(lines[:100]):
        if "exact name of registrant" in line.lower():
            for delta in (-1, 1, 2):
                idx = i + delta
                if 0 <= idx < len(lines):
                    cand = lines[idx].strip()
                    if cand and len(cand) > 3 and "exact name" not in cand.lower():
                        fields["registrant_name"] = cand
                        break
            break

    if not fields["registrant_name"]:
        blob = "\n".join(lines[:200])
        m = re.search(
            r"\b([A-Z][A-Za-z0-9&.,'\- ]{1,60}?"
            r"(?:Ltd\.?|Inc\.?|Corporation|Corp\.?|PLC|LLC|Limited))\b",
            blob,
        )
        if m:
            fields["registrant_name"] = m.group(1).strip()

    if not fields["registrant_name"]:
        stem = Path(filename).stem
        m2 = re.match(r"^(.+?)[-_]10[-_]?k", stem, re.IGNORECASE)
        if m2:
            fields["registrant_name"] = re.sub(r"[_\-]+", " ", m2.group(1)).strip()

    for line in lines[:150]:
        if any(kw in line.lower() for kw in ("fiscal year ended", "for the fiscal year", "period of report")):
            m = _DATE_RE.search(line)
            if m:
                fields["period_of_report"] = m.group(1)
                break
    if not fields["period_of_report"]:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
        if m:
            fields["period_of_report"] = m.group(1)

    for line in lines[:100]:
        if "commission file" in line.lower():
            m = re.search(r"\b(\d{1,3}\s*-\s*\d{2,7})\b", line)
            if m:
                fields["commission_file_number"] = re.sub(r"\s+", "", m.group(1))
                break

    return fields


# ---------------------------------------------------------------------------
# Main section builder  (uses DOM markers for table assignment)
# ---------------------------------------------------------------------------

def _build_sections(
    body_lines: list[str],
    table_tags: list,
) -> list[dict]:
    """
    1. Detect section headings in body_lines.
    2. Find which lines contain table markers; determine each table's owner
       section by binary-searching backward to the nearest heading.
    3. For each section: clean prose, convert owned tables to Markdown, chunk.
    """
    headings = _detect_headings(body_lines)

    if not headings:
        clean, has_legal = _clean_section_body(body_lines)
        return [{
            "section_id": "s001",
            "item_code": "", "item_label": "", "header": "Full Document",
            "section_part": "", "section_type": "filing_item",
            "is_tail": False, "has_legal_boilerplate": has_legal,
            "char_count": len(clean), "word_count": len(clean.split()),
            "chunks": _split_into_chunks(clean, [], "s001"),
            "tables": [],
        }]

    heading_starts = [h["start"] for h in headings]

    def _owner_idx(line_idx: int) -> int:
        lo, hi, result = 0, len(heading_starts) - 1, 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if heading_starts[mid] <= line_idx:
                result = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return result

    # Map table index -> list of table dicts for that section
    section_tables: dict[int, list[dict]] = {i: [] for i in range(len(headings))}

    for tid, tbl_tag in enumerate(table_tags):
        marker = f"__TBL_{tid:04d}__"
        marker_line = next(
            (li for li, line in enumerate(body_lines) if marker in line), None
        )
        if marker_line is None:
            continue  # table is in cover/TOC, skip

        # Skip tiny tables (formatting artifacts)
        rows = tbl_tag.find_all("tr")
        if len(rows) < 2:
            continue
        if len(tbl_tag.find_all(["td", "th"])) < 4:
            continue

        md, row_count = _html_table_to_markdown(tbl_tag)
        if not md or row_count < 1:
            continue

        title = _find_table_title(tbl_tag, body_lines, marker_line)
        owner = _owner_idx(marker_line)
        section_tables[owner].append({
            "markdown": md,
            "row_count": row_count,
            "title": title,
        })

    # Build final section objects
    sections: list[dict] = []
    for idx, hd in enumerate(headings):
        end = headings[idx + 1]["start"] if idx + 1 < len(headings) else len(body_lines)
        body = body_lines[hd["body_start"]: end]
        sid = f"s{idx + 1:03d}"

        if hd.get("is_part_header"):
            sections.append({
                "section_id": sid,
                "item_code": "", "item_label": "",
                "header": hd["header"],
                "section_part": hd["section_part"],
                "section_type": "part_header",
                "is_tail": False, "has_legal_boilerplate": False,
                "char_count": 0, "word_count": 0,
                "chunks": [], "tables": [],
            })
            continue

        clean, has_legal = _clean_section_body(body)

        raw_tables = section_tables.get(idx, [])
        sec_tables: list[dict] = []
        for ti, tbl in enumerate(raw_tables, start=1):
            sec_tables.append({
                "table_id": f"{sid}-t{ti:03d}",
                "title": tbl["title"],
                "markdown": tbl["markdown"],
                "row_count": tbl["row_count"],
            })

        chunks = _split_into_chunks(clean, sec_tables, sid)
        item_code = hd["item_code"]
        is_tail = item_code in TAIL_ITEMS or hd["header"].upper().startswith("SIGNATURE")

        sections.append({
            "section_id": sid,
            "item_code": item_code,
            "item_label": f"Item {item_code}" if item_code else "",
            "header": hd["header"],
            "section_part": hd["section_part"],
            "section_type": "tail" if is_tail else "filing_item",
            "is_tail": is_tail,
            "has_legal_boilerplate": has_legal,
            "char_count": len(clean),
            "word_count": len(clean.split()),
            "chunks": chunks,
            "tables": sec_tables,
        })

    return sections


# ---------------------------------------------------------------------------
# Quality report
# ---------------------------------------------------------------------------

def _build_quality(
    pages: list[dict],
    sections: list[dict],
    warnings: list[str],
    filename: str,
) -> dict:
    total_chunks = sum(len(s["chunks"]) for s in sections)
    total_tables = sum(len(s["tables"]) for s in sections)
    total_words = sum(s["word_count"] for s in sections)
    prose_sections = [
        s for s in sections
        if s["section_type"] == "filing_item" and s["word_count"] > 50
    ]
    item_codes = sorted({s["item_code"] for s in sections if s["item_code"]})
    expected = {"1", "1A", "7", "7A", "8"}
    missing = sorted(expected - set(item_codes))

    q_warnings = list(warnings)
    if missing:
        q_warnings.append(f"missing_expected_items:{','.join(missing)}")
    if total_tables == 0:
        q_warnings.append("no_structured_tables_extracted")
    if total_words < 5000:
        q_warnings.append("low_word_count")

    return {
        "total_pages": len(pages),
        "pages_with_text": sum(1 for p in pages if p.get("char_count", 0) > 0),
        "total_sections": len(sections),
        "prose_sections": len(prose_sections),
        "item_codes_found": item_codes,
        "missing_expected_items": missing,
        "total_chunks": total_chunks,
        "total_tables": total_tables,
        "total_words": total_words,
        "warnings": q_warnings,
        "parsed_at": datetime.now().isoformat(),
        "source_file": filename,
    }


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def parse_document(filepath: Path, rel_path: Path | None = None) -> dict:
    """Parse a 10-K HTML or PDF and return a chunk-ready JSON structure."""
    if rel_path is None:
        rel_path = Path(filepath.name)

    suffix = filepath.suffix.lower()
    pages, full_text, table_tags, warnings = _parse_source(filepath, suffix)

    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
    doc_meta = _extract_document_metadata(lines, filepath.name)

    body_start = _find_body_start(lines)
    body_lines = lines[body_start:]

    sections = _build_sections(body_lines, table_tags)
    quality = _build_quality(pages, sections, warnings, filepath.name)

    return {
        "source": {
            "file_name": filepath.name,
            "suffix": suffix,
            "relative_path": str(rel_path),
            "absolute_path": str(filepath),
            "size_bytes": filepath.stat().st_size,
        },
        "document": doc_meta,
        "sections": sections,
        "quality": quality,
    }


# ---------------------------------------------------------------------------
# Batch extractor
# ---------------------------------------------------------------------------

def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _prepare_output_dir() -> Path:
    return prepare_output_root(
        OUTPUT_PARENT_DIR,
        legacy_dir_globs=("Extracted_10K_*",),
        current_dir_patterns=("Flex10K", "Flex10K_*"),
    )


def extract_all(
    input_dir: Path = INPUT_DIR,
    output_dir: Path | None = None,
) -> tuple[Path, int, int, int]:
    extracted_dir = Path(output_dir) if output_dir else _prepare_output_dir()
    extracted_dir.mkdir(parents=True, exist_ok=True)

    run_stamp = _now_stamp()

    out_10k = extracted_dir / f"Flex10K_{run_stamp}"
    out_10k.mkdir(parents=True, exist_ok=True)

    files = [
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    ]

    success, failed = 0, 0
    errors: list[dict] = []

    for src in files:
        rel = src.relative_to(input_dir)
        tdir = out_10k / rel.parent
        tdir.mkdir(parents=True, exist_ok=True)
        try:
            parsed = parse_document(src, rel)
            out_file = tdir / f"{src.stem}.parsed.json"
            out_file.write_text(
                json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            success += 1
        except Exception as e:
            failed += 1
            errors.append({"file": str(rel), "error": str(e)})

    if errors:
        (extracted_dir / "_errors.json").write_text(
            json.dumps({"count": len(errors), "errors": errors}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    sample_dir = prepare_shared_sample_dir(extracted_dir, run_stamp)
    first_sample = next(iter(sorted(out_10k.rglob("*.parsed.json"))), None)
    if first_sample is not None:
        shutil.copy2(first_sample, sample_dir / first_sample.name)

    return extracted_dir, len(files), success, failed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    global ENABLE_DOCLING_PDF

    ap = argparse.ArgumentParser(description="10-K Chunk-Ready Extractor")
    ap.add_argument("--input-dir", type=str, default=None)
    ap.add_argument("--output-dir", type=str, default=None,
                    help="Output dir root (default: Test_Design/File/extracted)")
    ap.add_argument("--use-docling", action="store_true",
                    help="Re-enable Docling PDF parsing for this run")
    ap.add_argument("--file", type=str, default=None,
                    help="Parse a single file and write .parsed.json next to it")
    ap.add_argument("--out", type=str, default=None,
                    help="Override output path for --file mode")
    args = ap.parse_args()

    ENABLE_DOCLING_PDF = args.use_docling

    if args.file:
        fp = Path(args.file)
        if not fp.exists():
            print(f"File not found: {fp}")
            return
        result = parse_document(fp)
        q = result["quality"]
        print(f"\n{'='*60}")
        print(f"File     : {fp.name}")
        print(f"Sections : {q['total_sections']}  (prose: {q['prose_sections']})")
        print(f"Items    : {', '.join(q['item_codes_found']) or 'none'}")
        print(f"Missing  : {', '.join(q['missing_expected_items']) or 'none'}")
        print(f"Chunks   : {q['total_chunks']}")
        print(f"Tables   : {q['total_tables']}")
        print(f"Words    : {q['total_words']:,}")
        print(f"Warnings : {q['warnings'] or 'none'}")
        print(f"{'='*60}")
        out_path = Path(args.out) if args.out else fp.parent / f"{fp.stem}.parsed.json"
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Output   : {out_path}\n")
        return

    input_dir = Path(args.input_dir) if args.input_dir else INPUT_DIR
    output_dir = Path(args.output_dir) if args.output_dir else None
    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        return
    out, total, success, failed = extract_all(input_dir=input_dir, output_dir=output_dir)
    print(f"\n{'='*60}")
    print("10-K CHUNK-READY EXTRACTION")
    print(f"{'='*60}")
    print(f"Input  : {input_dir}")
    print(f"Output : {out}")
    print(f"Total  : {total}  |  Success: {success}  |  Failed: {failed}\n")


if __name__ == "__main__":
    main()
