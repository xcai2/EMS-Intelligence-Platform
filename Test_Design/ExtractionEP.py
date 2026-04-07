#!/usr/bin/env python3
"""
Earnings Presentation (EP) Extractor  —  Slide-by-Slide, Chunk & Embedding Ready
==================================================================================

Design goals
------------
1. Each slide (PDF page) becomes a structured section with clean text,
   inferred slide type, extracted key metrics, and rich metadata.
2. Fiscal period (FY / quarter) is inferred from the filename pattern
   (e.g. Flex_EP_FY25Q3.pdf -> fiscal_year=FY25, fiscal_quarter=Q3).
3. Financial metric keywords are tagged per slide (revenue, EPS, guidance,
   capex, margins, etc.) with structured labels for downstream retrieval.
4. full_text_core concatenates all content slides, skipping cover/appendix/
   disclaimer/section-divider noise, for clean chunk/embedding input.
5. Output JSON mirrors the shape of Extraction8k / Extraction10k outputs:
   source + document + slides + chunks + full_text + full_text_core + quality.

Fixes applied (v2)
------------------
  #1  Numeric-label fracture: hyphen line-breaks rejoined; number tokens
      re-associated with their nearest label via token-window heuristic.
  #2  Table flattening: tabular slides emitted as semi-structured text
      (Label: value pairs) in addition to raw text.
  #3  Broken sentence lines: PDF soft-hyphen / mid-word line-breaks merged.
  #4  Bullet fragmentation: bullet lines collected and rejoined into complete
      sentences before being stored.
  #5  full_text_core filtering: added "disclaimer", "section_divider" slide
      types to the exclusion set; low-content slides (<= 15 words) also
      excluded regardless of type.
  #6  Duplicate text removal: line-level and paragraph-level dedup applied
      within each slide and across the full_text_core assembly.
  #7  Numeric semantic labels: value-label pairs extracted and stored in
      structured metrics list per slide (e.g. {label, value, period}).
  #8  key_metrics upgraded: boolean metric map + structured value list
      stored separately; keyword list retained for backward compat.
  #10 Chunk-level metadata: slides list doubles as chunks; each entry
      carries company, period_label, fiscal_year, fiscal_quarter,
      page_num, slide_type for direct RAG filter use.

Filename patterns recognised
----------------------------
  Flex_EP_FY25Q3.pdf
  Flex_EP_FY24Q4.pdf
  02.-Flex_EP_FY22Q4.pdf
  FLEX_FY22Q3_Earnings-Presentation.pdf
  EP_FY23Q3_FINAL.pdf

Output folder structure
-----------------------
  Test_Design/File/
    Extracted_EP_<timestamp>/
      flex_earnings_presentation/
        Flex_EP_FY25Q3.pdf.parsed.json
        ...
      _test_samples/
        <first parsed file>
"""

from __future__ import annotations

import hashlib
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
INPUT_DIR = BASE_DIR / "File" / "Flex" / "Earnings Presentation"
OUTPUT_PARENT_DIR = BASE_DIR / "File"
SUPPORTED_SUFFIXES = {".pdf"}

# Slide types in order of detection priority
SLIDE_TYPE_KEYWORDS: dict[str, list[str]] = {
    # --- noise types (detected first so they are filtered early) ---
    "disclaimer": [
        "forward-looking statements", "forward looking statements",
        "safe harbor", "risks and uncertainties", "risk factors",
        "non-gaap disclosures", "non-gaap financial measures",
        "reconciling information",
    ],
    "title_slide": [
        "earnings presentation", "earnings call", "investor presentation",
        "quarterly results",
    ],
    "agenda": ["agenda", "table of contents", "contents"],
    # --- content types ---
    "financial_summary": [
        "revenue", "net income", "gaap", "non-gaap", "adjusted eps",
        "gross margin", "operating income", "diluted eps", "earnings per share",
    ],
    "segment": [
        "segment", "agility", "reliability", "flex agility", "flex reliability",
        "business segment", "end market",
    ],
    "guidance": [
        "guidance", "outlook", "next quarter",
        "q1 guidance", "q2 guidance", "q3 guidance", "q4 guidance",
    ],
    "capex": [
        "capital expenditure", "capex", "capital investment", "property plant",
        "pp&e", "ppe",
    ],
    "cash_flow": [
        "free cash flow", "operating cash flow", "cash from operations",
        "cash flow from", "fcf",
    ],
    "balance_sheet": [
        "balance sheet", "total assets", "total liabilities",
        "working capital", "net debt", "inventory",
    ],
    "shareholder_return": [
        "share repurchase", "buyback", "dividend", "return to shareholders",
        "repurchased", "returned to",
    ],
    "appendix": [
        "appendix", "non-gaap reconciliation", "reconciliation of gaap",
    ],
}

# Slides of these types are excluded from full_text_core
EXCLUDED_FROM_CORE = {"title_slide", "agenda", "appendix", "disclaimer", "section_divider"}

# Minimum word count for a slide to enter full_text_core
MIN_CORE_WORD_COUNT = 15

# Financial metric signal words for key_metrics boolean map
METRIC_KEYWORDS: list[str] = [
    "revenue", "net revenue", "gross profit", "gross margin",
    "operating income", "operating margin", "net income",
    "diluted eps", "adjusted eps", "earnings per share",
    "free cash flow", "fcf", "capex", "capital expenditure",
    "guidance", "outlook",
    "cash", "debt", "net debt",
    "inventory", "working capital",
    "segment", "agility", "reliability",
    "return on", "share repurchase",
]

# Patterns for extracting (label, value, period) triples  — Fix #7
# Matches well-bounded "Label: $Value" or "$Value Label" patterns.
_VALUE_LABEL_PATTERNS: list[re.Pattern[str]] = [
    # "Label: $X.XB" — explicit colon separator (produced by Fix #1/#2 pipeline)
    re.compile(
        r"(?P<label>[A-Z][A-Za-z\s&/.()\-]{2,45}?):\s*"
        r"(?P<value>\$[\d,]+(?:\.\d+)?[BMK%]?"
        r"(?:\s*[-–]\s*\$[\d,]+(?:\.\d+)?[BMK%]?)?)",
        re.IGNORECASE,
    ),
    # "$X.XB label" — value token followed by a short capitalized label
    re.compile(
        r"\$(?P<value>[\d,]+(?:\.\d+)?[BMK]?)"
        r"(?:\s*[-–]\s*\$[\d,]+(?:\.\d+)?[BMK]?)?"
        r"\s+(?P<label>[A-Z][A-Za-z ]{2,30}(?:\s[A-Z][A-Za-z ]{1,20})?)"
        r"(?=\s|$|\n)",
        re.IGNORECASE,
    ),
    # "X.X% Label" — percentage followed by a short label
    re.compile(
        r"(?P<value>\d+(?:\.\d+)?%)\s+"
        r"(?P<label>[A-Z][A-Za-z ]{2,30})"
        r"(?=\s|$|\n)",
        re.IGNORECASE,
    ),
]

# Period token patterns used to annotate extracted values
_PERIOD_RE = re.compile(
    r"\b(Q[1-4]\s*F(?:Y)?\d{2,4}|F(?:Y)?\d{2,4}\s*Q[1-4]|FY\d{2,4}|F\d{2})\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers — text cleaning  (Fix #3: hyphen line-break rejoining)
# ---------------------------------------------------------------------------

def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _rejoin_hyphen_linebreaks(text: str) -> str:
    """
    PDF extraction breaks hyphenated words across lines and also inserts a
    spurious space before hyphens, e.g.:
      'forward -\nlooking'  →  'forward-looking'
      'forward-\nlooking'   →  'forward-looking'
      'stock -based'        →  'stock-based'   (same-line space-hyphen)
    """
    # Hard hyphen at end of line (word split) — rejoin without hyphen
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    # Soft hyphen followed by newline
    text = re.sub(r"(\w)\xad\n\s*(\w)", r"\1\2", text)
    # Space-hyphen-space across line (e.g. "forward -\nlooking")
    text = re.sub(r"(\w) -\n\s*(\w)", r"\1-\2", text)
    # Same-line spurious space before hyphen in compound words
    # e.g. "forward -looking", "stock -based", "year -over -year"
    text = re.sub(r"(\w) -([a-z])", r"\1-\2", text)
    return text


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\u00ad", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = _rejoin_hyphen_linebreaks(text)          # Fix #3
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_slide_text(text: str) -> str:
    """Remove lone page numbers, separator lines, and footnote artifacts."""
    lines = text.splitlines()
    kept: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if re.match(r"^\d{1,3}$", s):                  # standalone page number
            continue
        if re.match(r"^[-=_*|]{3,}$", s):              # separator lines
            continue
        # Remove trailing footnote markers like "A." "B." at start of short lines
        if re.match(r"^[A-D]\.\s+.{0,120}$", s) and len(s) < 130:
            # Keep footnotes that contain financial data; skip pure citation text
            if not re.search(r"\$|\d+%|\bgaap\b|\bnon-gaap\b", s, re.I):
                continue
        kept.append(s)
    return "\n".join(kept).strip()


# ---------------------------------------------------------------------------
# Fix #6 — Duplicate removal helpers
# ---------------------------------------------------------------------------

def _line_hash(line: str) -> str:
    return hashlib.md5(line.strip().lower().encode()).hexdigest()


def _dedup_lines(text: str) -> str:
    """Remove consecutively repeated lines (exact match, case-insensitive)."""
    lines = text.splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines:
        h = _line_hash(ln)
        if h not in seen:
            seen.add(h)
            out.append(ln)
    return "\n".join(out)


def _dedup_paragraphs(text: str) -> str:
    """Remove duplicate paragraphs (blocks separated by blank lines)."""
    blocks = re.split(r"\n{2,}", text)
    seen: set[str] = set()
    out: list[str] = []
    for block in blocks:
        h = _line_hash(block)
        if h not in seen:
            seen.add(h)
            out.append(block)
    return "\n\n".join(out)


def _dedup_slide_text(text: str) -> str:
    """Apply both line-level and paragraph-level dedup to a slide's text."""
    text = _dedup_lines(text)
    text = _dedup_paragraphs(text)
    return text.strip()


# ---------------------------------------------------------------------------
# Fix #4 — Bullet fragment rejoiner
# ---------------------------------------------------------------------------

_BULLET_RE = re.compile(r"^[•·▪▸\-\*]\s*")


def _rejoin_bullets(text: str) -> str:
    """
    Merge multi-line bullet items into single lines.
    A continuation line is one that:
      - does not start with a bullet marker, AND
      - starts with a lower-case letter or a continuation word, AND
      - the previous line was a bullet or a continuation
    """
    lines = text.splitlines()
    result: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if _BULLET_RE.match(ln):
            # Start of a bullet — collect continuation lines
            combined = ln.rstrip()
            while i + 1 < len(lines):
                nxt = lines[i + 1]
                # Stop if next line is blank, another bullet, or a heading
                if not nxt.strip():
                    break
                if _BULLET_RE.match(nxt):
                    break
                # Stop if next line looks like a new section heading:
                # (a) pure ALL-CAPS line, or (b) ALL-CAPS segment label + value token
                nxt_s = nxt.strip()
                if re.match(r"^[A-Z][A-Z\s&/]{3,}$", nxt_s):
                    break
                if re.match(r"^[A-Z]{2,}\s+[\$\d(]", nxt_s):  # e.g. "AGILITY $3.6"
                    break
                # Stop if the combined line already ends with sentence punctuation
                if combined.rstrip().endswith((".", "!", "?")):
                    break
                # It is a continuation — append with a space
                combined = combined + " " + nxt_s
                i += 1
            result.append(combined)
        else:
            result.append(ln)
        i += 1
    return "\n".join(result)


# ---------------------------------------------------------------------------
# Fix #1 + #2 — Number/label repair and table semi-structuring
# ---------------------------------------------------------------------------

def _repair_number_label_fractures(text: str) -> str:
    """
    Heuristically rejoin number tokens that got separated from their labels
    by PDF column extraction order.

    Strategy:
    - If a line is purely a dollar/percent/number value AND the next line
      is a short label (no digits), merge them as "Label: Value".
    - If a line is a short label followed immediately on the next line by
      a value, merge them.
    """
    lines = text.splitlines()
    result: list[str] = []
    i = 0

    _is_value = re.compile(
        r"^\$?[\d,]+(?:\.\d+)?[BMK%]?(?:\s*[-–]\s*\$?[\d,]+(?:\.\d+)?[BMK%]?)?$"
    )
    _is_label = re.compile(r"^[A-Za-z][A-Za-z\s&/.,()]{1,50}$")
    _has_digit = re.compile(r"\d")

    while i < len(lines):
        cur = lines[i].strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""

        if _is_value.match(cur) and nxt and _is_label.match(nxt) and not _has_digit.search(nxt):
            # value line followed by label line → "Label: value"
            result.append(f"{nxt}: {cur}")
            i += 2
            continue

        if _is_label.match(cur) and not _has_digit.search(cur) and nxt and _is_value.match(nxt):
            # label line followed by value line → "Label: value"
            result.append(f"{cur}: {nxt}")
            i += 2
            continue

        result.append(lines[i])
        i += 1

    return "\n".join(result)


def _table_to_semi_structured(text: str) -> str:
    """
    Detect rows that look like tabular data (multiple numeric tokens on one line
    with text tokens) and reformat them as 'Label: v1; v2; ...' pairs.
    Leaves non-tabular lines unchanged.
    """
    lines = text.splitlines()
    out: list[str] = []

    # A "tabular" line has >= 2 dollar/percent values and at least one word
    _table_line = re.compile(
        r"(?:(?:\$[\d,]+(?:\.\d+)?[BMK%]?|\d+(?:\.\d+)?%|\(\d[\d,.]*\))[\s,]*){2,}"
    )

    for ln in lines:
        if _table_line.search(ln):
            # Extract all value tokens and the leading text label
            values = re.findall(
                r"\$[\d,]+(?:\.\d+)?[BMK%]?|\d+(?:\.\d+)?%|\(\d[\d,.]*\)", ln
            )
            # Leading label = everything before the first value token
            label_match = re.match(r"^([A-Za-z][A-Za-z\s&/.,()]{1,60}?)\s+(?=\$|\d)", ln)
            if label_match and values:
                label = label_match.group(1).strip().rstrip(":")
                out.append(f"{label}: {'; '.join(values)}")
            else:
                out.append(ln)
        else:
            out.append(ln)

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Fix #7 — Structured metric extraction
# ---------------------------------------------------------------------------

def _extract_structured_metrics(text: str, slide_title: str) -> list[dict[str, str]]:
    """
    Extract (label, value, period) triples from slide text.
    Returns a list of dicts, deduplicated by (label, value).
    """
    results: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    # Find period tokens near each match for annotation
    period_tokens = _PERIOD_RE.findall(text)
    period_hint = period_tokens[0] if period_tokens else ""

    for pattern in _VALUE_LABEL_PATTERNS:
        for m in pattern.finditer(text):
            label = m.group("label").strip().strip(":").strip()
            # Remove any embedded newlines left from PDF column extraction
            label = re.sub(r"\s*\n\s*", " ", label).strip()
            value = m.group("value").strip()
            # Skip trivially short, noisy, or pure-word labels
            if len(label) < 3 or re.match(r"^\d", label):
                continue
            # Skip labels that are just "for", "of", "in", etc.
            if re.match(r"^(for|of|in|and|the|a|an)$", label, re.I):
                continue
            key = (label.lower(), value.lower())
            if key in seen:
                continue
            seen.add(key)
            # Try to find a period closer to this match position
            surrounding = text[max(0, m.start() - 60): m.end() + 60]
            local_periods = _PERIOD_RE.findall(surrounding)
            period = local_periods[0] if local_periods else period_hint
            results.append({"label": label, "value": value, "period": period})

    return results


# ---------------------------------------------------------------------------
# Fix #8 — Structured key_metrics map
# ---------------------------------------------------------------------------

def _extract_key_metrics(text: str) -> dict[str, Any]:
    """
    Returns:
      {
        "keywords": [...],          # backward-compat list
        "flags": {metric: bool},    # boolean presence map
        "values": [{label, value, period}, ...]  # Fix #7
      }
    """
    lower = text.lower()
    keywords = [kw for kw in METRIC_KEYWORDS if kw in lower]
    flags = {kw.replace(" ", "_"): (kw in lower) for kw in METRIC_KEYWORDS}
    return {
        "keywords": keywords,
        "flags": flags,
    }


# ---------------------------------------------------------------------------
# Fiscal period parsing
# ---------------------------------------------------------------------------

_FY_RE = re.compile(
    r"FY\s*(\d{2,4})\s*Q([1-4])|Q([1-4])\s*FY\s*(\d{2,4})|"
    r"FY\s*(\d{2,4})\s*(Q[1-4])|(\d{4})\s*Q([1-4])",
    re.IGNORECASE,
)


def _infer_fiscal_period(filename: str) -> dict[str, str]:
    """Extract fiscal year and quarter from common EP filename patterns."""
    stem = Path(filename).stem.upper()
    m = _FY_RE.search(stem)
    fy = qtr = ""
    if m:
        if m.group(1) and m.group(2):
            yr = m.group(1)
            fy = f"FY{yr}" if len(yr) <= 2 else f"FY{yr[2:]}"
            qtr = f"Q{m.group(2)}"
        elif m.group(3) and m.group(4):
            yr = m.group(4)
            fy = f"FY{yr}" if len(yr) <= 2 else f"FY{yr[2:]}"
            qtr = f"Q{m.group(3)}"
        elif m.group(5) and m.group(6):
            yr = m.group(5)
            fy = f"FY{yr}" if len(yr) <= 2 else f"FY{yr[2:]}"
            qtr = m.group(6).upper()
        elif m.group(7) and m.group(8):
            fy = f"FY{str(m.group(7))[2:]}"
            qtr = f"Q{m.group(8)}"
    period_label = f"{fy}{qtr}" if fy or qtr else ""
    return {"fiscal_year": fy, "fiscal_quarter": qtr, "period_label": period_label}


# ---------------------------------------------------------------------------
# Slide classification  (Fix #5: added disclaimer + section_divider)
# ---------------------------------------------------------------------------

# Very short slides (section dividers) have few words and no financial data
_SECTION_DIVIDER_SIGNALS = re.compile(
    r"^(financial results|business update|thank you\.?|"
    r"q&a|questions? (and )?answers?)$",
    re.IGNORECASE,
)

# Slides whose title starts with "Appendix:" are reconciliation appendix slides
_APPENDIX_TITLE_RE = re.compile(r"^appendix[\s:—]", re.IGNORECASE)


def _classify_slide(text: str, page_num: int, word_count: int) -> str:
    """Infer the slide type from text content and position."""
    lower = text.lower().strip()
    first_line = lower.splitlines()[0].strip() if lower else ""

    # Appendix reconciliation slides — detected by first-line title
    if _APPENDIX_TITLE_RE.match(first_line):
        return "appendix"

    # Single-word "Appendix" divider slide
    if word_count <= 3 and "appendix" in lower:
        return "appendix"

    # Detect pure section-divider slides (very short, no data)
    if word_count <= 12 and _SECTION_DIVIDER_SIGNALS.match(lower.replace("\n", " ").strip()):
        return "section_divider"

    for slide_type, keywords in SLIDE_TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return slide_type

    if page_num == 1:
        return "title_slide"
    return "general"


def _extract_slide_title(text: str) -> str:
    """Return the first non-trivial line as the slide title."""
    for line in text.splitlines():
        s = line.strip()
        if not s or len(s) < 3:
            continue
        if re.match(r"^\d{1,3}$", s):
            continue
        # Skip pure value lines as title
        if re.match(r"^\$[\d,]+", s):
            continue
        return s[:200]
    return ""


# ---------------------------------------------------------------------------
# Full text pipeline per slide
# ---------------------------------------------------------------------------

def _process_slide_text(raw: str) -> str:
    """
    Apply the full cleaning + repair pipeline to a single slide's raw text.
    Order matters:
      1. Unicode / whitespace cleanup
      2. Hyphen line-break rejoining         (Fix #3)
      3. Strip page numbers / separators
      4. Bullet rejoining                    (Fix #4)
      5. Number-label fracture repair        (Fix #1)
      6. Table semi-structuring              (Fix #2)
      7. Duplicate line/paragraph removal    (Fix #6)
    """
    text = _clean_text(raw)
    text = _clean_slide_text(text)
    text = _rejoin_bullets(text)
    text = _repair_number_label_fractures(text)
    text = _table_to_semi_structured(text)
    text = _dedup_slide_text(text)
    return text


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------

def _parse_pdf_slides(
    filepath: Path,
    company: str,
    period: dict[str, str],
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """
    Parse each PDF page as one slide / chunk.
    Returns (slides_list, full_text, warnings).

    Each slide dict carries full chunk-level metadata (Fix #10).
    """
    slides: list[dict[str, Any]] = []
    warnings: list[str] = []

    # --- try docling first (higher quality for slide PDFs) ---
    full_md = ""
    try:
        from docling.document_converter import DocumentConverter  # type: ignore
        converter = DocumentConverter()
        result = converter.convert(str(filepath))
        doc = result.document
        full_md = doc.export_to_markdown()
        if full_md.strip():
            warnings.append("parser:docling_full_text_used")
    except Exception:
        full_md = ""

    # --- pypdf / PyPDF2 for per-slide text ---
    PdfReader = None
    for _mod in ("pypdf", "PyPDF2"):
        try:
            import importlib
            _lib = importlib.import_module(_mod)
            PdfReader = _lib.PdfReader
            break
        except ImportError:
            continue
    if PdfReader is None:
        warnings.append("pypdf_not_installed")
        return slides, full_md, warnings

    page_texts: list[str] = []
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
    except Exception as exc:
        try:
            import pdfplumber  # type: ignore
            with pdfplumber.open(str(filepath)) as pdf:
                page_texts = [(p.extract_text() or "") for p in pdf.pages]
            warnings.append("parser:pdfplumber_fallback")
        except Exception as exc2:
            warnings.append(f"pdf_open_error:{exc} | pdfplumber:{exc2}")
            return slides, full_md, warnings

    if not page_texts:
        warnings.append("pdf_no_pages_extracted")
        return slides, full_md, warnings

    all_texts: list[str] = []
    for i, raw in enumerate(page_texts, start=1):
        text = _process_slide_text(raw)            # full pipeline
        word_count = len(text.split())
        title = _extract_slide_title(text)
        slide_type = _classify_slide(text, i, word_count)
        key_metrics = _extract_key_metrics(text)
        structured_metrics = _extract_structured_metrics(text, title)  # Fix #7

        slides.append(
            {
                # --- identity ---
                "slide_id": f"slide_{i:03d}",
                "page_num": i,
                # --- Fix #10: chunk-level metadata ---
                "company": company,
                "fiscal_year": period["fiscal_year"],
                "fiscal_quarter": period["fiscal_quarter"],
                "period_label": period["period_label"],
                # --- classification ---
                "slide_type": slide_type,
                "title": title,
                # --- content ---
                "text": text,
                "char_count": len(text),
                "word_count": word_count,
                "has_numbers": bool(re.search(r"\d", text)),
                # --- metrics (Fix #7 + #8) ---
                "key_metrics": key_metrics,
                "structured_metrics": structured_metrics,
            }
        )
        if text:
            all_texts.append(f"[Slide {i}]\n{text}")

    # Prefer docling full text if available and richer
    if full_md and len(full_md) > len("\n\n".join(all_texts)):
        full_text = _clean_text(full_md)
    else:
        full_text = _clean_text("\n\n".join(all_texts))

    return slides, full_text, warnings


# ---------------------------------------------------------------------------
# full_text_core builder  (Fix #5 + #6)
# ---------------------------------------------------------------------------

def _build_full_text_core(slides: list[dict[str, Any]]) -> str:
    """
    Concatenate text from content slides only.
    Excluded: title, agenda, appendix, disclaimer, section_divider (Fix #5),
    and any slide with <= MIN_CORE_WORD_COUNT words (Fix #5).
    Also applies paragraph-level dedup across the assembled text (Fix #6).
    """
    parts: list[str] = []
    seen_blocks: set[str] = set()

    for s in slides:
        # Type-based exclusion
        if s["slide_type"] in EXCLUDED_FROM_CORE:
            continue
        # Content-based exclusion: too few words
        if s["word_count"] <= MIN_CORE_WORD_COUNT:
            continue
        text = s["text"].strip()
        if not text:
            continue

        # Block-level dedup across slides (Fix #6)
        block_hash = _line_hash(text)
        if block_hash in seen_blocks:
            continue
        seen_blocks.add(block_hash)

        header = f"[{s['slide_type'].upper()} — Slide {s['page_num']}]"
        if s["title"]:
            header += f" {s['title']}"
        parts.append(f"{header}\n{text}")

    combined = _clean_text("\n\n".join(parts))
    # Final paragraph dedup pass on the assembled core
    combined = _dedup_paragraphs(combined)
    return combined


# ---------------------------------------------------------------------------
# Chunk list builder  (Fix #10)
# ---------------------------------------------------------------------------

def _build_chunks(
    slides: list[dict[str, Any]],
    company: str,
    period: dict[str, str],
) -> list[dict[str, Any]]:
    """
    Build explicit chunk records from content slides.
    Each chunk is self-contained with all metadata needed for RAG filtering.
    """
    chunks: list[dict[str, Any]] = []
    for s in slides:
        if s["slide_type"] in EXCLUDED_FROM_CORE:
            continue
        if s["word_count"] <= MIN_CORE_WORD_COUNT:
            continue
        text = s["text"].strip()
        if not text:
            continue
        chunks.append(
            {
                "chunk_id": f"{period['period_label']}_slide_{s['page_num']:03d}",
                # RAG filter metadata
                "company": company,
                "fiscal_year": period["fiscal_year"],
                "fiscal_quarter": period["fiscal_quarter"],
                "period_label": period["period_label"],
                "doc_type": "earnings_presentation",
                "page_num": s["page_num"],
                "slide_type": s["slide_type"],
                "slide_title": s["title"],
                # Content
                "text": text,
                "word_count": s["word_count"],
                "char_count": s["char_count"],
                # Metrics
                "metric_keywords": s["key_metrics"]["keywords"],
                "metric_flags": s["key_metrics"]["flags"],
                "structured_metrics": s["structured_metrics"],
            }
        )
    return chunks


# ---------------------------------------------------------------------------
# Quality report
# ---------------------------------------------------------------------------

def _build_quality(
    slides: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    full_text: str,
    warnings: list[str],
) -> dict[str, Any]:
    total = len(slides)
    with_text = sum(1 for s in slides if s["char_count"] > 0)
    slide_types: dict[str, int] = {}
    for s in slides:
        slide_types[s["slide_type"]] = slide_types.get(s["slide_type"], 0) + 1
    all_metrics: set[str] = set()
    for s in slides:
        all_metrics.update(s["key_metrics"]["keywords"])
    total_structured = sum(len(s["structured_metrics"]) for s in slides)
    return {
        "total_slides": total,
        "slides_with_text": with_text,
        "slides_with_text_ratio": round(with_text / total, 4) if total else 0,
        "slide_type_counts": slide_types,
        "metrics_found": sorted(all_metrics),
        "total_structured_metric_values": total_structured,
        "chunk_count": len(chunks),
        "full_text_char_count": len(full_text),
        "full_text_word_count": len(full_text.split()),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse_document(filepath: Path, rel_path: Path) -> dict[str, Any]:
    suffix = filepath.suffix.lower()
    if suffix != ".pdf":
        return {
            "source": {"file_name": filepath.name, "suffix": suffix},
            "quality": {"warnings": [f"unsupported_suffix:{suffix}"]},
        }

    period = _infer_fiscal_period(filepath.name)

    # Infer company name from filename (e.g., "Flex_EP_FY25Q3" → "Flex")
    stem = filepath.stem
    company = ""
    m = re.match(r"^[\d.\-]*\s*([A-Za-z]+)[\s_\-]", stem)
    if m:
        company = m.group(1).strip()
    company = company or "Flex Ltd"

    slides, full_text, warnings = _parse_pdf_slides(filepath, company, period)
    full_text_core = _build_full_text_core(slides)
    chunks = _build_chunks(slides, company, period)

    return {
        "source": {
            "doc_type": "earnings_presentation",
            "suffix": suffix,
            "file_name": filepath.name,
            "relative_path": str(rel_path),
            "absolute_path": str(filepath),
            "size_bytes": filepath.stat().st_size,
            "parsed_at": datetime.now().isoformat(),
        },
        "document": {
            "company": company,
            "fiscal_year": period["fiscal_year"],
            "fiscal_quarter": period["fiscal_quarter"],
            "period_label": period["period_label"],
            "total_slides": len(slides),
        },
        "usage_policy": {
            "full_text_role": "inspection_full_text",
            "full_text_core_role": "chunk_embedding_input",
            "chunk_source_field": "chunks[].text",
            "chunk_filter_fields": [
                "company", "fiscal_year", "fiscal_quarter",
                "period_label", "slide_type", "metric_flags",
            ],
        },
        "full_text": full_text,
        "full_text_core": full_text_core,
        "slides": slides,
        "chunks": chunks,          # Fix #10: explicit chunk list
        "quality": _build_quality(slides, chunks, full_text, warnings),
    }


# ---------------------------------------------------------------------------
# Batch extraction
# ---------------------------------------------------------------------------

def _prepare_output_dir() -> Path:
    return prepare_output_root(
        OUTPUT_PARENT_DIR,
        legacy_dir_globs=("Extracted_EP_*",),
        current_dir_patterns=("flex_earnings_presentation", "flex_earnings_presentation_*"),
    )


def extract_all(
    input_dir: Path = INPUT_DIR,
    output_dir: Path | None = None,
) -> tuple[Path, int, int, int]:
    if output_dir is None:
        output_dir = _prepare_output_dir()
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    run_stamp = _now_stamp()

    out_ep = output_dir / f"flex_earnings_presentation_{run_stamp}"
    out_ep.mkdir(parents=True, exist_ok=True)

    files = [
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    ]

    success, failed = 0, 0
    errors: list[dict[str, str]] = []

    for src in sorted(files):
        rel = src.relative_to(input_dir)
        tdir = out_ep / rel.parent
        tdir.mkdir(parents=True, exist_ok=True)
        try:
            parsed = parse_document(src, rel)
            out_file = tdir / f"{src.name}.parsed.json"
            out_file.write_text(
                json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            success += 1
        except Exception as exc:
            failed += 1
            errors.append({"file": str(rel), "error": str(exc)})

    if errors:
        (output_dir / "_errors.json").write_text(
            json.dumps({"count": len(errors), "errors": errors}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    sample_dir = prepare_shared_sample_dir(output_dir, run_stamp)
    first_sample = next(iter(sorted(out_ep.rglob("*.parsed.json"))), None)
    if first_sample is not None:
        shutil.copy2(first_sample, sample_dir / first_sample.name)

    return output_dir, len(files), success, failed


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Earnings Presentation (EP) slide-by-slide PDF extractor"
    )
    ap.add_argument(
        "--input-dir",
        type=str,
        default=None,
        help="Input directory (default: Test_Design/File/Flex/Earnings Presentation)",
    )
    ap.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory root (default: Test_Design/File/extracted)",
    )
    args = ap.parse_args()

    input_dir = Path(args.input_dir) if args.input_dir else INPUT_DIR
    output_dir = Path(args.output_dir) if args.output_dir else None

    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        return

    out, total, success, failed = extract_all(
        input_dir=input_dir, output_dir=output_dir
    )

    print("=" * 60)
    print("TEST DESIGN — EARNINGS PRESENTATION EXTRACTION")
    print("=" * 60)
    print(f"Input  : {input_dir}")
    print(f"Output : {out}")
    print(f"Total source files : {total}")
    print(f"Extracted success  : {success}")
    print(f"Failed             : {failed}")


if __name__ == "__main__":
    main()
