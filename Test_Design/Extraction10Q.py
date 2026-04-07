#!/usr/bin/env python3
"""
10-Q Quarterly Report Extractor  —  Chunk & Embedding Ready
============================================================

Design goals
------------
1. Output is a list of *chunk-ready sections*, each with clean prose text,
   structured table markdown, and rich metadata for retrieval.
2. Financial tables (Income Statement, Balance Sheet, Cash Flow, etc.) are
   reconstructed as clean Markdown tables instead of flat noisy text.
3. Tables are assigned to sections via DOM position markers so every table
   goes to exactly the right section.
4. TOC / cover noise is stripped before section detection.
5. All Part I + Part II items are extracted so the RAG pipeline can filter.
6. Works for both HTML (.html / .htm) and PDF (.pdf) source files.
     PDF  -> docling (best quality) -> pdfplumber (tables + text) -> pypdf fallback
     HTML -> BeautifulSoup with XBRL/iXBRL tag stripping

Changelog vs original
---------------------
[FIX-1] PDF 表格抽取：_parse_pdf_plumber() 新增 pdfplumber.extract_tables() 路径，
        将每页识别到的表格转为 Markdown 并插入 __TBL_NNNN__ 标记，后续 section
        builder 可正确生成 type=table 的 chunk，不再退化为流水文本。

[FIX-2] type=table chunk 对 PDF 生效：_parse_source() PDF 分支现在返回
        pdf_table_objects（与 HTML table_tags 结构对齐），_build_sections() 统一消费。

[FIX-3] "Table of Contents" 页眉清理：_clean_prose() 新增对整行 "Table of Contents"
        的过滤；_filter_pdf_headers() 统计高频短行并自动移除页眉/页脚噪声。

[FIX-4] 页眉页脚高频行过滤：_filter_pdf_headers() 扫描所有页，对出现次数超过阈值
        的短行加入黑名单，在拼接全文前逐页过滤。

[FIX-5] "(Unaudited)" 等括号标注白名单清理：_clean_prose() 对高频财务括号标注做
        去重，避免重复字符串污染 embedding。

[FIX-6] _infer_fiscal_quarter() 兜底：当文件名和 period 均无法推断时，返回
        ("", "") 而非 KeyError 或空字符串拼错。

10-Q structure
--------------
  Part I  — Financial Information
    Item 1   Financial Statements
    Item 2   Management's Discussion and Analysis
    Item 3   Quantitative and Qualitative Disclosures About Market Risk
    Item 4   Controls and Procedures
  Part II — Other Information
    Item 1   Legal Proceedings
    Item 1A  Risk Factors
    Item 2   Unregistered Sales of Equity Securities
    Item 3   Defaults Upon Senior Securities
    Item 4   Mine Safety Disclosures
    Item 5   Other Information
    Item 6   Exhibits
  Signatures

Output JSON schema
------------------
{
  "source":   { file_name, suffix, size_bytes, ... },
  "document": { registrant_name, period_of_report, form_type,
                fiscal_quarter, fiscal_year_label, ... },
  "sections": [
    {
      "section_id":   "s001",
      "item_code":    "1",
      "item_label":   "Item 1",
      "header":       "Item 1  FINANCIAL STATEMENTS",
      "section_part": "Part I",
      "section_type": "filing_item",
      "is_tail":      false,
      "has_legal_boilerplate": false,
      "char_count":   ...,
      "word_count":   ...,
      "chunks": [ { chunk_id, text, has_table, type, ... }, ... ],
      "tables": [ { table_id, title, markdown, row_count }, ... ]
    }, ...
  ],
  "quality": { totals, item_codes_found, missing_expected_items, warnings, ... }
}

Chunking strategy
-----------------
* Target: ~800 words per prose chunk (CHUNK_TARGET_WORDS).
* Minimum: 50 words; shorter chunks are merged into the previous one.
* Overlap buffer: 100 words kept internally for sentence-boundary repair
  but NOT injected into chunk text (avoids embedding vector pollution).
* Tables are self-contained chunks (type="table"); never split mid-table.
* Every chunk carries full section metadata for vector-store filtering.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
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
INPUT_DIR = BASE_DIR / "File" / "Flex" / "quarterly_10Q"
OUTPUT_PARENT_DIR = BASE_DIR / "File"
SUPPORTED_SUFFIXES = {".pdf", ".html", ".htm", ".txt", ".md"}

CHUNK_TARGET_WORDS = 800
CHUNK_OVERLAP_WORDS = 100
CHUNK_MIN_WORDS = 50

# 10-Q tail items: Item 6 (Exhibits) and Signatures
TAIL_ITEMS = {"6"}

# [FIX-4] Header/footer dedup: lines appearing on more than this fraction of
# pages (and shorter than MAX_HEADER_LEN chars) are treated as page headers.
HEADER_FREQ_THRESHOLD = 0.40   # appears on >40% of pages → header/footer
MAX_HEADER_LINE_LEN   = 80     # only short lines qualify as headers

# [FIX-5] Bracket annotations that are noise when repeated throughout a doc.
_BRACKET_NOISE_RE = re.compile(
    r"\(\s*(?:Unaudited|In millions?|In thousands?|In billions?"
    r"|except (?:per )?share amounts?|except share data"
    r"|amounts? may not sum due to rounding)\s*\)",
    re.IGNORECASE,
)

# Regex patterns (unchanged from original)
_PART_RE      = re.compile(r"^\s*part\s+(I{1,3}V?|IV)\s*[.:\-\s]*(.*)$", re.IGNORECASE)
_ITEM_RE      = re.compile(r"^\s*item\s+(\d{1,2}[A-Ca-c]?)\s*[.:\-\s]*(.*)$", re.IGNORECASE)
_SIGNATURE_RE = re.compile(r"^\s*signatures?\s*$", re.IGNORECASE)
_PAGE_NUM_RE  = re.compile(r"^\s*\d{1,3}\s*$")
_LEGAL_PATTERNS = [
    re.compile(r"shall\s+not\s+be\s+deemed\s+[\"']?filed[\"']?", re.IGNORECASE),
    re.compile(r"incorporated\s+by\s+reference", re.IGNORECASE),
]
_DATE_RE = re.compile(
    r"([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"
)
_TBL_MARKER_RE = re.compile(r"__TBL_(\d{4})__")

# [FIX-3] TOC header line pattern
_TOC_LINE_RE = re.compile(r"^\s*table\s+of\s+contents\s*$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\u00ad", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_prose(text: str) -> str:
    """
    Line-level cleaning applied to every section body.

    Changes vs original:
    - [FIX-3] Skip lines that are solely "Table of Contents".
    - [FIX-5] Collapse repeated bracket-annotation noise within the text.
    """
    lines = text.splitlines()
    kept: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            kept.append("")
            continue
        # original filters
        if _PAGE_NUM_RE.match(s):
            continue
        if re.match(r"^[-=_*]{3,}$", s):
            continue
        if re.match(r"^[$%#&*]{1,2}$", s):
            continue
        # [FIX-3] drop standalone "Table of Contents" lines (PDF page headers)
        if _TOC_LINE_RE.match(s):
            continue
        kept.append(ln)

    result = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()

    # [FIX-5] Remove repeated bracket annotations (keep first occurrence per
    # paragraph to preserve context, strip subsequent duplicates).
    result = _dedupe_bracket_annotations(result)

    return result


def _dedupe_bracket_annotations(text: str) -> str:
    """
    [FIX-5] Within each paragraph, remove duplicate bracket annotations such as
    "(Unaudited)" or "(In millions)" after the first occurrence.
    Operates paragraph-by-paragraph so the annotation can appear once per table.
    """
    paragraphs = text.split("\n\n")
    cleaned: list[str] = []
    for para in paragraphs:
        seen: set[str] = set()
        def _replace(m: re.Match) -> str:
            key = m.group(0).lower()
            if key in seen:
                return ""
            seen.add(key)
            return m.group(0)
        cleaned.append(_BRACKET_NOISE_RE.sub(_replace, para))
    return "\n\n".join(cleaned)


def _read_text_file(filepath: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return filepath.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return filepath.read_text(errors="ignore")


# ---------------------------------------------------------------------------
# [FIX-4] PDF header/footer frequency filter
# ---------------------------------------------------------------------------

def _filter_pdf_headers(page_texts: list[str]) -> list[str]:
    """
    Scan all pages, identify lines that appear on >HEADER_FREQ_THRESHOLD of
    pages AND are shorter than MAX_HEADER_LINE_LEN chars.  Those lines are
    page headers/footers and are stripped from every page.

    This removes:
    - "Table of Contents" (appears on nearly every page of SEC filings)
    - Registrant name lines like "FLEX LTD."
    - "The accompanying notes are an integral part of these condensed
       consolidated financial statements." (repeated footer)
    """
    if not page_texts:
        return page_texts

    n_pages = len(page_texts)
    freq: Counter[str] = Counter()

    for page in page_texts:
        # Count each unique short line once per page
        seen_this_page: set[str] = set()
        for raw_ln in page.splitlines():
            ln = raw_ln.strip()
            if ln and len(ln) <= MAX_HEADER_LINE_LEN and ln not in seen_this_page:
                freq[ln] += 1
                seen_this_page.add(ln)

    # Build blacklist: lines appearing on >40% of pages
    blacklist: set[str] = {
        ln for ln, count in freq.items()
        if count / n_pages > HEADER_FREQ_THRESHOLD
    }

    if not blacklist:
        return page_texts

    cleaned: list[str] = []
    for page in page_texts:
        lines = page.splitlines()
        filtered = [ln for ln in lines if ln.strip() not in blacklist]
        cleaned.append("\n".join(filtered))
    return cleaned


# ---------------------------------------------------------------------------
# HTML parser  (unchanged from original)
# ---------------------------------------------------------------------------

def _parse_html(filepath: Path) -> tuple[str, list, list[str]]:
    """Returns (full_text_with_markers, raw_table_tags, warnings)."""
    warnings: list[str] = ["parser:bs4"]
    raw = _read_text_file(filepath)

    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        warnings.append("bs4_not_installed")
        return _clean_text(raw), [], warnings

    soup = BeautifulSoup(raw, "html.parser")

    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()

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

    # Remove TOC anchor links to avoid phantom "Table of Contents" noise
    for tag in soup.find_all("a", href=True):
        if (tag.get("href", "") or "").startswith("#"):
            tag.decompose()

    _BLOCK_TAGS = {
        "div", "p", "section", "article", "li",
        "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
    }
    for tag in soup.find_all(_BLOCK_TAGS):
        sentinel = soup.new_tag("span")
        sentinel.string = "\n"
        tag.append(sentinel)

    table_tags = soup.find_all("table")
    for i, tbl in enumerate(table_tags):
        marker_tag = soup.new_tag("span")
        marker_tag.string = f"__TBL_{i:04d}__"
        tbl.insert_before(marker_tag)

    root = soup.find("article") or soup.find("main") or soup.body or soup
    raw_text = root.get_text("\n", strip=False)
    return _clean_text(raw_text), table_tags, warnings


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


# ---------------------------------------------------------------------------
# [FIX-1/2] pdfplumber-based table + text extractor
# ---------------------------------------------------------------------------

class _PdfTable:
    """
    Lightweight stand-in for an HTML table tag, carrying the Markdown already
    rendered from pdfplumber rows, so _build_sections() can treat it uniformly
    alongside HTML table_tags.
    """
    __slots__ = ("markdown", "row_count", "title", "page_num", "marker")

    def __init__(self, markdown: str, row_count: int, title: str,
                 page_num: int, marker: str) -> None:
        self.markdown  = markdown
        self.row_count = row_count
        self.title     = title
        self.page_num  = page_num
        self.marker    = marker   # e.g. "__TBL_0003__"


def _pdfplumber_rows_to_markdown(rows: list[list[str | None]]) -> tuple[str, int]:
    """
    Convert a pdfplumber table (list of rows, each row a list of cell strings)
    into a GitHub-flavoured Markdown table string.

    Returns (markdown_str, data_row_count).  Returns ("", 0) for empty tables.
    """
    # Normalise cells
    grid: list[list[str]] = []
    for row in rows:
        cells = [re.sub(r"\s+", " ", (c or "")).strip() for c in row]
        if any(cells):
            grid.append(cells)

    if len(grid) < 2:   # need at least a header + one data row
        return "", 0

    # Pad to uniform column count
    max_cols = max(len(r) for r in grid)
    grid = [r + [""] * (max_cols - len(r)) for r in grid]

    # Drop entirely-empty columns
    keep_cols = [
        c for c in range(max_cols)
        if any(grid[r][c] for r in range(len(grid)))
    ]
    if not keep_cols:
        return "", 0
    grid = [[row[c] for c in keep_cols] for row in grid]

    def _md_row(cells: list[str]) -> str:
        return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"

    lines = [_md_row(grid[0]), _md_row(["---"] * len(grid[0]))]
    for row in grid[1:]:
        lines.append(_md_row(row))
    return "\n".join(lines), len(grid) - 1


def _find_pdf_table_title(page_text_lines: list[str], tbl_line_idx: int) -> str:
    """
    Look back up to 6 lines above the __TBL__ marker for a plausible title.
    Prefers lines containing financial keywords.
    """
    _FIN_KW = re.compile(
        r"(consolidated|balance\s+sheet|statement|income|cash\s+flow|"
        r"revenue|earnings|equity|segment|operations|comprehensive|"
        r"restructuring|fair\s+value|debt|intangible|inventory|derivative)",
        re.IGNORECASE,
    )
    _SKIP = re.compile(
        r"^(table\s+of\s+contents|\d{1,3}|[-=_*]{3,}|flex\s+ltd\.?)$",
        re.IGNORECASE,
    )
    candidates: list[str] = []
    start = max(0, tbl_line_idx - 6)
    for ln in reversed(page_text_lines[start:tbl_line_idx]):
        s = ln.strip()
        if not s or _SKIP.match(s) or _PAGE_NUM_RE.match(s) or len(s) < 8:
            continue
        if _FIN_KW.search(s):
            return s
        candidates.append(s)
    return candidates[0] if candidates else ""


def _parse_pdf_plumber(filepath: Path) -> tuple[list[dict], str, list[_PdfTable], list[str]]:
    """
    [FIX-1/2] Use pdfplumber to extract both text and structured tables from
    a PDF.  Tables are converted to Markdown and injected as __TBL_NNNN__
    markers into the per-page text.

    Returns:
        pages        – list of page dicts (page_num, text, char_count)
        full_text    – concatenated text with __TBL__ markers embedded
        pdf_tables   – list of _PdfTable objects (carries Markdown + metadata)
        warnings     – parser annotation strings
    """
    warnings_out: list[str] = []
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        warnings_out.append("pdfplumber_not_installed")
        return [], "", [], warnings_out

    pages_raw: list[str] = []     # raw text per page (before header filter)
    pdf_tables: list[_PdfTable] = []
    tbl_counter = 0

    try:
        with pdfplumber.open(str(filepath)) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):

                # --- 1. Extract structured tables first ---
                page_tbls = page.extract_tables() or []
                tbl_markers_this_page: list[tuple[str, _PdfTable]] = []

                for raw_tbl in page_tbls:
                    if not raw_tbl or len(raw_tbl) < 2:
                        continue
                    md, row_count = _pdfplumber_rows_to_markdown(raw_tbl)
                    if not md or row_count < 1:
                        continue
                    marker = f"__TBL_{tbl_counter:04d}__"
                    pt = _PdfTable(
                        markdown=md,
                        row_count=row_count,
                        title="",          # filled in below after we have text
                        page_num=page_idx,
                        marker=marker,
                    )
                    tbl_markers_this_page.append((marker, pt))
                    pdf_tables.append(pt)
                    tbl_counter += 1

                # --- 2. Extract page text ---
                page_text = page.extract_text() or ""
                page_text = _clean_text(page_text)

                # --- 3. Inject __TBL__ markers into page text.
                # Append them at the end of this page's text block so the
                # section builder can locate and assign them.
                if tbl_markers_this_page:
                    marker_block = "\n".join(m for m, _ in tbl_markers_this_page)
                    page_text = page_text + "\n" + marker_block if page_text else marker_block

                pages_raw.append(page_text)

    except Exception as exc:
        warnings_out.append(f"pdfplumber_error:{exc}")
        return [], "", [], warnings_out

    # --- 4. [FIX-4] Filter high-frequency header/footer lines across pages ---
    pages_filtered = _filter_pdf_headers(pages_raw)

    # --- 5. Back-fill table titles using filtered per-page text ---
    # Build a lookup: marker → line index within the page text
    for page_idx_0, page_text in enumerate(pages_filtered):
        page_lines = page_text.splitlines()
        for i, ln in enumerate(page_lines):
            m = _TBL_MARKER_RE.search(ln)
            if m:
                tbl_id = int(m.group(1))
                if tbl_id < len(pdf_tables):
                    pdf_tables[tbl_id].title = _find_pdf_table_title(page_lines, i)

    # --- 6. Build page dicts and concatenate full text ---
    pages_out: list[dict] = []
    texts: list[str] = []
    for i, txt in enumerate(pages_filtered, start=1):
        txt = _clean_text(txt)
        pages_out.append({"page_num": i, "text": txt, "char_count": len(txt)})
        if txt:
            texts.append(txt)

    full_text = _clean_text("\n\n".join(texts))
    warnings_out.append("parser:pdfplumber")
    return pages_out, full_text, pdf_tables, warnings_out


def _parse_pdf_fallback_text_only(filepath: Path) -> tuple[list[dict], str, list[str]]:
    """
    Last-resort text-only extraction via pypdf (no table structure).
    Used only when pdfplumber itself fails.
    """
    PdfReader = None
    for mod_name in ("pypdf", "PyPDF2"):
        try:
            import importlib
            _lib = importlib.import_module(mod_name)
            PdfReader = _lib.PdfReader
            break
        except ImportError:
            continue

    warnings_out: list[str] = []
    page_texts: list[str] = []

    if PdfReader is not None:
        try:
            reader = PdfReader(str(filepath))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    pass
            for page in reader.pages:
                try:
                    page_texts.append(page.extract_text() or "")
                except Exception:
                    page_texts.append("")
            warnings_out.append("parser:pypdf_text_only")
        except Exception as exc:
            warnings_out.append(f"pypdf_error:{exc}")

    if not page_texts:
        warnings_out.append("pdf_no_text_extracted")
        return [], "", warnings_out

    # [FIX-4] Apply header/footer filter even in text-only fallback
    page_texts = _filter_pdf_headers(page_texts)

    pages_out: list[dict] = []
    texts: list[str] = []
    for i, raw in enumerate(page_texts, start=1):
        txt = _clean_text(raw)
        pages_out.append({"page_num": i, "text": txt, "char_count": len(txt)})
        if txt:
            texts.append(txt)

    return pages_out, _clean_text("\n\n".join(texts)), warnings_out


# ---------------------------------------------------------------------------
# Unified source parser
# ---------------------------------------------------------------------------

def _parse_source(
    filepath: Path, suffix: str
) -> tuple[list[dict], str, list, list[str]]:
    """
    Returns (pages, full_text, table_objects, warnings).

    table_objects is either:
    - a list of BS4 Tag objects  (HTML path)
    - a list of _PdfTable objects (PDF path)
    - []  (docling path or text-only fallback)

    _build_sections() treats both uniformly via duck-typing.
    """
    if suffix == ".pdf":
        # Tier 1: docling (best quality, handles tables via Markdown export)
        docling_text, docling_warnings = _parse_pdf_docling(filepath)
        if docling_text:
            return [], docling_text, [], docling_warnings

        # Tier 2: [FIX-1/2] pdfplumber (tables + text)
        pages, text, pdf_tables, plumber_warnings = _parse_pdf_plumber(filepath)
        if text:
            return pages, text, pdf_tables, docling_warnings + plumber_warnings

        # Tier 3: pypdf text-only (last resort)
        pages, text, pypdf_warnings = _parse_pdf_fallback_text_only(filepath)
        return pages, text, [], docling_warnings + plumber_warnings + pypdf_warnings

    if suffix in {".html", ".htm"}:
        text, table_tags, warnings = _parse_html(filepath)
        return [], text, table_tags, warnings

    if suffix in {".txt", ".md"}:
        return [], _clean_text(_read_text_file(filepath)), [], []

    return [], "", [], [f"unsupported_file_type:{suffix}"]


# ---------------------------------------------------------------------------
# Table → Markdown  (HTML path — unchanged from original)
# ---------------------------------------------------------------------------

def _html_table_to_markdown(table_tag) -> tuple[str, int]:
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
                    i += 1
            elif cell:
                result.append(cell)
                i += 1
            else:
                i += 1
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
    """HTML-path title finder (unchanged from original)."""
    _SKIP = re.compile(
        r"^(table\s+of\s+contents|\d{1,3}|[-=_*]{3,})$", re.IGNORECASE
    )
    _FIN_KW = re.compile(
        r"(consolidated|balance\s+sheet|statement|income|cash\s+flow|"
        r"revenue|earnings|equity|segment|operations|comprehensive)",
        re.IGNORECASE,
    )

    def _clean(t: str) -> str:
        return re.sub(r"\s+", " ", t).strip()

    node = table_tag
    for _ in range(5):
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
# Body start detection  (unchanged from original)
# ---------------------------------------------------------------------------

def _find_body_start(lines: list[str]) -> int:
    """
    The TOC lists all Part/Item headings once.
    The real body repeats them with actual content.
    We look for the SECOND occurrence of 'Part I' or 'Item 1'.
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
# Section detection  (unchanged from original)
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
    section_meta: dict,
) -> list[dict]:
    if not prose.strip() and not tables:
        return []

    _SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z\(\"\'])')
    prose_normalised = re.sub(r'\n\n+', '.  ', prose)
    prose_normalised = re.sub(r'\n', ' ', prose_normalised)
    prose_normalised = re.sub(r'[ \t]{2,}', ' ', prose_normalised).strip()

    sentences = _SENT_SPLIT.split(prose_normalised)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks: list[dict] = []
    chunk_idx = 0
    current_sents: list[str] = []
    current_words = 0
    prev_tail_text: str = ""

    def _make_chunk_meta(extra: dict) -> dict:
        return {
            **extra,
            "section_id":   section_id,
            "item_code":    section_meta.get("item_code", ""),
            "item_label":   section_meta.get("item_label", ""),
            "section_part": section_meta.get("section_part", ""),
            "section_type": section_meta.get("section_type", ""),
            "header":       section_meta.get("header", ""),
        }

    def _flush_prose(sents: list[str]) -> None:
        nonlocal chunk_idx, prev_tail_text
        if not sents:
            return
        text = " ".join(sents).strip()
        wc = len(text.split())
        if wc < CHUNK_MIN_WORDS and chunks:
            last = chunks[-1]
            if last.get("type") == "prose":
                last["text"] = (last["text"] + " " + text).strip()
                last["word_count"] = len(last["text"].split())
                last["char_count"] = len(last["text"])
                return
        if not text:
            return
        chunk_idx += 1
        prev_tail_text = " ".join(sents[-CHUNK_OVERLAP_WORDS:]) if len(sents) > 1 else text
        chunks.append(_make_chunk_meta({
            "chunk_id":    f"{section_id}-c{chunk_idx:03d}",
            "type":        "prose",
            "text":        text,
            "char_count":  len(text),
            "word_count":  wc,
            "has_table":   False,
            "table_titles": [],
        }))

    for sent in sentences:
        wc = len(sent.split())
        current_sents.append(sent)
        current_words += wc
        if current_words >= CHUNK_TARGET_WORDS:
            _flush_prose(current_sents)
            current_sents = []
            current_words = 0

    _flush_prose(current_sents)

    # Append table chunks — self-contained, never split mid-table
    for tbl in tables:
        chunk_idx += 1
        md = tbl.get("markdown", "")
        chunks.append(_make_chunk_meta({
            "chunk_id":    f"{section_id}-c{chunk_idx:03d}",
            "type":        "table",
            "text":        md,
            "char_count":  len(md),
            "word_count":  len(md.split()),
            "has_table":   True,
            "table_titles": [tbl.get("title", "")],
        }))

    return chunks


# ---------------------------------------------------------------------------
# Document metadata (cover page)
# ---------------------------------------------------------------------------

def _infer_fiscal_quarter(filename: str, period_str: str) -> tuple[str, str]:
    """
    Infer fiscal quarter label for Flex's fiscal calendar (year ends ~March).
    Flex FY quarters:
      Q1: April–June    (10-Q filed ~July/Aug)
      Q2: July–Sep      (10-Q filed ~Oct/Nov)
      Q3: Oct–Dec       (10-Q filed ~Jan/Feb)
      (Q4 is the annual 10-K)
    Returns (fiscal_quarter, fiscal_year_label) e.g. ("Q2", "FY26").

    [FIX-6] Always returns a 2-tuple of strings; never raises KeyError.
    """
    stem = Path(filename).stem.upper()

    qtr: str = ""
    cal_year: int = 0

    # Pattern: 2025_Q2_Flex_10Q  or  Q2_2025_...
    m = re.search(r"(\d{4})[\s_\-]*(Q[1-4])", stem)
    if m:
        cal_year = int(m.group(1))
        qtr = m.group(2)
    else:
        m2 = re.search(r"(Q[1-4])[\s_\-]*(\d{4})", stem)
        if m2:
            qtr = m2.group(1)
            cal_year = int(m2.group(2))

    if not qtr:
        # Try to infer from a YYYY-MM-DD date in filename or period string
        dm = re.search(r"(\d{4})-(\d{2})-\d{2}", filename)
        if not dm and period_str:
            dm = re.search(r"(\d{4})-(\d{2})-\d{2}", period_str)
        if dm:
            cal_year = int(dm.group(1))
            month = int(dm.group(2))
            if month in (7, 8):
                qtr = "Q1"
            elif month in (10, 11):
                qtr = "Q2"
            elif month in (1, 2):
                qtr = "Q3"
            # else: unknown quarter, leave qtr=""

    if not cal_year:
        # [FIX-6] Last resort: try to parse year from period_str like "September 26, 2025"
        ym = re.search(r"\b(20\d{2})\b", period_str or "")
        if ym:
            cal_year = int(ym.group(1))

    # Compute fiscal year label
    fy_label: str = ""
    if cal_year:
        # Determine calendar month to decide FY offset
        dm3 = re.search(r"(\d{4})-(\d{2})-\d{2}", filename)
        month = int(dm3.group(2)) if dm3 else 0
        if month in (1, 2, 3):
            fy_short = str(cal_year)[2:]
        else:
            fy_short = str(cal_year + 1)[2:]
        fy_label = f"FY{fy_short}"

    return qtr, fy_label


def _extract_document_metadata(lines: list[str], filename: str) -> dict:
    fields: dict[str, str] = {
        "form_type": "10-Q",
        "registrant_name": "",
        "period_of_report": "",
        "fiscal_quarter": "",
        "fiscal_year_label": "",
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
        m2 = re.match(r"^(.+?)[-_]10[-_]?q", stem, re.IGNORECASE)
        if not m2:
            m2 = re.match(r"^\d{4}[-_]Q\d[-_](.+?)[-_]10", stem, re.IGNORECASE)
        if m2:
            fields["registrant_name"] = re.sub(r"[_\-]+", " ", m2.group(1)).strip()

    for line in lines[:150]:
        lw = line.lower()
        if any(kw in lw for kw in ("for the quarter", "for the three months", "period of report")):
            mt = _DATE_RE.search(line)
            if mt:
                fields["period_of_report"] = mt.group(1)
                break
    if not fields["period_of_report"]:
        mt = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
        if mt:
            fields["period_of_report"] = mt.group(1)

    for line in lines[:100]:
        if "commission file" in line.lower():
            mc = re.search(r"\b(\d{1,3}\s*-\s*\d{2,7})\b", line)
            if mc:
                fields["commission_file_number"] = re.sub(r"\s+", "", mc.group(1))
                break

    qtr, fy = _infer_fiscal_quarter(filename, fields["period_of_report"])
    fields["fiscal_quarter"] = qtr
    fields["fiscal_year_label"] = fy

    return fields


# ---------------------------------------------------------------------------
# Main section builder
# ---------------------------------------------------------------------------

def _resolve_table_object(tbl_obj: Any) -> tuple[str, int, str]:
    """
    Duck-type dispatch: handle both HTML BS4 table tags and _PdfTable objects.
    Returns (markdown, row_count, title).
    """
    if isinstance(tbl_obj, _PdfTable):
        return tbl_obj.markdown, tbl_obj.row_count, tbl_obj.title

    # HTML BS4 tag
    md, row_count = _html_table_to_markdown(tbl_obj)
    return md, row_count, ""


def _build_sections(
    body_lines: list[str],
    table_objects: list,           # list[BS4 Tag] or list[_PdfTable]
) -> list[dict]:
    headings = _detect_headings(body_lines)

    if not headings:
        clean, has_legal = _clean_section_body(body_lines)
        return [{
            "section_id": "s001",
            "item_code": "", "item_label": "", "header": "Full Document",
            "section_part": "", "section_type": "filing_item",
            "is_tail": False, "has_legal_boilerplate": has_legal,
            "char_count": len(clean), "word_count": len(clean.split()),
            "chunks": _split_into_chunks(clean, [], "s001", section_meta={
                "item_code": "", "item_label": "", "section_part": "",
                "section_type": "filing_item", "header": "Full Document",
            }),
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

    section_tables: dict[int, list[dict]] = {i: [] for i in range(len(headings))}

    for tbl_obj in table_objects:
        # Determine the marker string so we can locate it in body_lines
        if isinstance(tbl_obj, _PdfTable):
            marker = tbl_obj.marker
        else:
            # HTML: find the __TBL_NNNN__ that was injected before this tag
            tid = table_objects.index(tbl_obj)
            marker = f"__TBL_{tid:04d}__"

        marker_line = next(
            (li for li, line in enumerate(body_lines) if marker in line), None
        )
        if marker_line is None:
            continue

        md, row_count, title = _resolve_table_object(tbl_obj)

        # For HTML tags: apply quality filters (skip tiny / empty tables)
        if not isinstance(tbl_obj, _PdfTable):
            rows = tbl_obj.find_all("tr")
            if len(rows) < 2:
                continue
            if len(tbl_obj.find_all(["td", "th"])) < 4:
                continue

        if not md or row_count < 1:
            continue

        # For HTML: back-fill title from surrounding DOM if empty
        if not title and not isinstance(tbl_obj, _PdfTable):
            title = _find_table_title(tbl_obj, body_lines, marker_line)

        owner = _owner_idx(marker_line)
        section_tables[owner].append({
            "markdown":  md,
            "row_count": row_count,
            "title":     title,
        })

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
                "table_id":  f"{sid}-t{ti:03d}",
                "title":     tbl["title"],
                "markdown":  tbl["markdown"],
                "row_count": tbl["row_count"],
            })

        item_code = hd["item_code"]
        is_tail = item_code in TAIL_ITEMS or hd["header"].upper().startswith("SIGNATURE")

        chunks = _split_into_chunks(clean, sec_tables, sid, section_meta={
            "item_code":    item_code,
            "item_label":   f"Item {item_code}" if item_code else "",
            "section_part": hd["section_part"],
            "section_type": "tail" if is_tail else "filing_item",
            "header":       hd["header"],
        })

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
    total_words  = sum(s["word_count"] for s in sections)
    prose_sections = [
        s for s in sections
        if s["section_type"] == "filing_item" and s["word_count"] > 50
    ]
    item_codes = sorted({s["item_code"] for s in sections if s["item_code"]})
    expected   = {"1", "2", "3", "4"}
    missing    = sorted(expected - set(item_codes))

    q_warnings = list(warnings)
    if missing:
        q_warnings.append(f"missing_expected_items:{','.join(missing)}")
    if total_tables == 0:
        q_warnings.append("no_structured_tables_extracted")
    if total_words < 2000:
        q_warnings.append("low_word_count")

    return {
        "total_pages":            len(pages),
        "pages_with_text":        sum(1 for p in pages if p.get("char_count", 0) > 0),
        "total_sections":         len(sections),
        "prose_sections":         len(prose_sections),
        "item_codes_found":       item_codes,
        "missing_expected_items": missing,
        "total_chunks":           total_chunks,
        "total_tables":           total_tables,
        "total_words":            total_words,
        "warnings":               q_warnings,
        "parsed_at":              datetime.now().isoformat(),
        "source_file":            filename,
    }


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def parse_document(filepath: Path, rel_path: Path | None = None) -> dict:
    """Parse a 10-Q HTML or PDF and return a chunk-ready JSON structure."""
    if rel_path is None:
        rel_path = Path(filepath.name)

    suffix = filepath.suffix.lower()
    pages, full_text, table_objects, warnings = _parse_source(filepath, suffix)

    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
    doc_meta = _extract_document_metadata(lines, filepath.name)

    body_start = _find_body_start(lines)
    body_lines = lines[body_start:]

    sections = _build_sections(body_lines, table_objects)
    quality  = _build_quality(pages, sections, warnings, filepath.name)

    return {
        "source": {
            "doc_type":      "10-Q",
            "file_name":     filepath.name,
            "suffix":        suffix,
            "relative_path": str(rel_path),
            "absolute_path": str(filepath),
            "size_bytes":    filepath.stat().st_size,
            "parsed_at":     datetime.now().isoformat(),
        },
        "document": doc_meta,
        "sections": sections,
        "quality":  quality,
    }


# ---------------------------------------------------------------------------
# Batch extractor
# ---------------------------------------------------------------------------

def _prepare_output_dir() -> Path:
    return prepare_output_root(
        OUTPUT_PARENT_DIR,
        legacy_dir_globs=("Extracted_10Q_*",),
        current_dir_patterns=("flex_quarterly_10q", "flex_quarterly_10q_*"),
    )


def extract_all(
    input_dir: Path = INPUT_DIR,
    output_dir: Path | None = None,
) -> tuple[Path, int, int, int]:
    extracted_dir = Path(output_dir) if output_dir else _prepare_output_dir()
    extracted_dir.mkdir(parents=True, exist_ok=True)

    run_stamp = _now_stamp()

    out_10q = extracted_dir / f"flex_quarterly_10q_{run_stamp}"
    out_10q.mkdir(parents=True, exist_ok=True)

    files = [
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    ]

    success, failed = 0, 0
    errors: list[dict] = []

    for src in sorted(files):
        rel = src.relative_to(input_dir)
        tdir = out_10q / rel.parent
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
    first_sample = next(iter(sorted(out_10q.rglob("*.parsed.json"))), None)
    if first_sample is not None:
        shutil.copy2(first_sample, sample_dir / first_sample.name)

    return extracted_dir, len(files), success, failed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="10-Q Quarterly Report Chunk-Ready Extractor")
    ap.add_argument("--input-dir", type=str, default=None,
                    help="Input directory (default: File/Flex/quarterly_10Q)")
    ap.add_argument("--output-dir", type=str, default=None,
                    help="Output directory root (default: Test_Design/File/extracted)")
    ap.add_argument("--file", type=str, default=None,
                    help="Parse a single file and print quality summary")
    args = ap.parse_args()

    if args.file:
        fp = Path(args.file)
        if not fp.exists():
            print(f"File not found: {fp}")
            return
        result = parse_document(fp)
        q = result["quality"]
        d = result["document"]
        print(f"\n{'='*60}")
        print(f"File        : {fp.name}")
        print(f"Period      : {d.get('period_of_report')}  "
              f"({d.get('fiscal_quarter')} {d.get('fiscal_year_label')})")
        print(f"Sections    : {q['total_sections']}  (prose: {q['prose_sections']})")
        print(f"Items found : {', '.join(q['item_codes_found']) or 'none'}")
        print(f"Missing     : {', '.join(q['missing_expected_items']) or 'none'}")
        print(f"Chunks      : {q['total_chunks']}")
        print(f"Tables      : {q['total_tables']}")
        print(f"Words       : {q['total_words']:,}")
        print(f"Warnings    : {q['warnings'] or 'none'}")
        print(f"{'='*60}")
        out_path = fp.parent / f"{fp.stem}.parsed.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved: {out_path}")
        return

    input_dir  = Path(args.input_dir)  if args.input_dir  else INPUT_DIR
    output_dir = Path(args.output_dir) if args.output_dir else None

    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        return

    out, total, success, failed = extract_all(input_dir=input_dir, output_dir=output_dir)

    print("=" * 60)
    print("10-Q QUARTERLY REPORT EXTRACTION")
    print("=" * 60)
    print(f"Input  : {input_dir}")
    print(f"Output : {out}")
    print(f"Total source files : {total}")
    print(f"Extracted success  : {success}")
    print(f"Failed             : {failed}")


if __name__ == "__main__":
    main()
