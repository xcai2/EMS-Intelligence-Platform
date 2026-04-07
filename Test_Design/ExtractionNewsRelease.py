#!/usr/bin/env python3
"""
News Release parse-only extractor.

Current priority:
- Keep output schema aligned with Extraction8k.py
- Produce clean full_text_core for downstream chunk/embedding
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

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "File" / "Flex" / "News Releases"
OUTPUT_PARENT_DIR = BASE_DIR / "File"
SUPPORTED_SUFFIXES = {".pdf", ".html", ".htm", ".txt", ".md"}

_ITEM_RE = re.compile(r"^\s*item\s+(\d{1,2}\.\d{2})\b[\s\.:;-]*(.*)$", re.IGNORECASE)
_SIGNATURE_RE = re.compile(r"^\s*signatures?\s*$", re.IGNORECASE)
_LEGAL_RE = [
    re.compile(r"shall\s+not\s+be\s+deemed\s+[\"']?filed[\"']?", re.IGNORECASE),
    re.compile(r"incorporated\s+by\s+reference", re.IGNORECASE),
]
_EXHIBIT_RE = re.compile(r"^\s*(?:exhibit\s+)?(\d{1,3}(?:\.\d+)?)\b\s*[:\-\s]*(.*)$", re.IGNORECASE)
_PAGE_NUM_RE = re.compile(r"^\s*\d{1,3}\s*$")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
_DATE_RE = re.compile(
    r"([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"
)
_MD_H2_RE = re.compile(r"^\s*##\s+(.+?)\s*$")
_MD_H3_RE = re.compile(r"^\s*###\s+(.+?)\s*$")

PREFERRED_CORE_ITEMS = {"2.02", "7.01", "8.01"}


def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _read_text_file(filepath: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return filepath.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return filepath.read_text(errors="ignore")


def _parse_pdf_text(filepath: Path) -> tuple[list[dict[str, Any]], str, list[str]]:
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []

    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        warnings.append("pypdf_not_installed")
        return pages, "", warnings

    try:
        reader = PdfReader(str(filepath))
    except Exception as e:
        warnings.append(f"pdf_open_error:{e}")
        return pages, "", warnings

    texts: list[str] = []
    for i, p in enumerate(reader.pages, start=1):
        try:
            txt = _clean_text(p.extract_text() or "")
        except Exception:
            txt = ""
        pages.append({"page_num": i, "text": txt, "char_count": len(txt)})
        if txt:
            texts.append(txt)

    return pages, _clean_text("\n\n".join(texts)), warnings


def _parse_docling_text(filepath: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        from docling.document_converter import DocumentConverter  # type: ignore
    except Exception:
        warnings.append("docling_not_installed")
        return "", warnings

    try:
        converter = DocumentConverter()
        result = converter.convert(str(filepath))
        doc = getattr(result, "document", None)
        if doc is None:
            warnings.append("docling_no_document")
            return "", warnings

        # Prefer markdown output for better structure retention.
        if hasattr(doc, "export_to_markdown"):
            text = doc.export_to_markdown() or ""
        elif hasattr(doc, "export_to_text"):
            text = doc.export_to_text() or ""
        else:
            text = str(doc) or ""

        text = _clean_text(text)
        if not text:
            warnings.append("docling_empty_text")
        return text, warnings
    except Exception as e:
        warnings.append(f"docling_error:{e}")
        return "", warnings


def _parse_html_text(filepath: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    raw = _read_text_file(filepath)
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        warnings.append("bs4_not_installed")
        return _clean_text(raw), warnings

    soup = BeautifulSoup(raw, "html.parser")
    for t in soup(["script", "style", "noscript", "template", "svg"]):
        t.decompose()
    for t in soup.find_all(True):
        n = (t.name or "").lower()
        # Drop hidden Inline XBRL payload blocks from human-readable text.
        if n in {"ix:header", "ix:hidden"}:
            t.decompose()
            continue
        # Keep inline XBRL text payload by unwrapping ix:* tags.
        if n.startswith("ix:"):
            try:
                t.unwrap()
            except Exception:
                pass
            continue
        # Remove pure schema/technical nodes that are not narrative body.
        if n.startswith(("xbrli:", "link:", "dei:", "us-gaap:")):
            t.decompose()

    root = soup.find("article") or soup.find("main") or soup.body or soup
    return _clean_text(root.get_text("\n", strip=True)), warnings


def _parse_source_text(filepath: Path, suffix: str) -> tuple[list[dict[str, Any]], str, list[str]]:
    if suffix == ".pdf":
        docling_text, docling_warnings = _parse_docling_text(filepath)
        if docling_text:
            return [], docling_text, docling_warnings + ["parser:docling"]
        pages, text, warnings = _parse_pdf_text(filepath)
        return pages, text, docling_warnings + warnings + ["parser:pypdf"]
    if suffix in {".html", ".htm"}:
        docling_text, docling_warnings = _parse_docling_text(filepath)
        if docling_text:
            return [], docling_text, docling_warnings + ["parser:docling"]
        text, warnings = _parse_html_text(filepath)
        return [], text, docling_warnings + warnings + ["parser:bs4"]
    if suffix in {".txt", ".md"}:
        return [], _clean_text(_read_text_file(filepath)), []
    return [], "", [f"unsupported_file_type:{suffix}"]


def _is_legal_line(line: str) -> bool:
    return any(p.search(line) for p in _LEGAL_RE)


def _is_exhibit_line(line: str) -> bool:
    low = line.lower()
    return bool(_EXHIBIT_RE.match(line)) or "description of exhibit" in low


def _is_title_like(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 120 or _PAGE_NUM_RE.match(s):
        return False
    if re.search(r"[.!?]$", s):
        return True
    words = [w for w in s.split() if w]
    if 1 <= len(words) <= 8:
        caps = sum(1 for w in words if w[:1].isupper())
        return caps >= max(1, len(words) - 1)
    return False


def _split_nonempty_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _find_first_item_index(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if _ITEM_RE.match(line):
            return i
    return len(lines)


def _extract_cover_metadata(lines: list[str]) -> dict[str, Any]:
    first_h2_idx = next((i for i, ln in enumerate(lines) if _MD_H2_RE.match(ln)), len(lines))
    cover_lines = lines[:first_h2_idx] if first_h2_idx < len(lines) else lines[: min(80, len(lines))]
    def _is_cover_noise(line: str) -> bool:
        s = line.strip()
        if not s:
            return True
        low = s.lower()
        if low in {"true", "false"}:
            return True
        # Keep plausible postal codes (often 4-7 digits), drop long technical ids.
        if re.fullmatch(r"\d{8,}", s):
            return True
        if re.fullmatch(r"\d{2}-\d{7,}", s):
            return True
        if re.fullmatch(r"[A-Z]{2}", s):
            return True
        return False

    clean_cover_lines = [ln for ln in cover_lines if not _is_cover_noise(ln)]

    fields = {
        "title": "",
        "date": "",
        "type": "",
        "source": "",
        "tags": "",
        "relevance": "",
        "capex_related": "",
        "ai_related": "",
        "registrant_name_raw": "",
        "registrant_name_normalized": "",
        "registrant_name": "",
        "date_of_report_raw": "",
        "date_of_report_normalized": "",
        "date_of_report": "",
    }

    def _norm_value(v: str) -> str:
        s = (v or "").strip()
        if s.lower() in {"not applicable", "n/a", "na"}:
            return ""
        return s

    for i, line in enumerate(clean_cover_lines):
        low = line.lower()

        if line.startswith("# ") and not fields["title"]:
            fields["title"] = _norm_value(line.lstrip("#").strip())

        if low.startswith("**date:**"):
            value = re.sub(r"^\*\*date:\*\*\s*", "", line, flags=re.IGNORECASE)
            fields["date"] = _norm_value(value)
            if not fields["date_of_report_raw"]:
                fields["date_of_report_raw"] = fields["date"]

        if low.startswith("**type:**"):
            value = re.sub(r"^\*\*type:\*\*\s*", "", line, flags=re.IGNORECASE)
            fields["type"] = _norm_value(value)

        if low.startswith("**source:**"):
            value = re.sub(r"^\*\*source:\*\*\s*", "", line, flags=re.IGNORECASE)
            fields["source"] = _norm_value(value)

        if low.startswith("**tags:**"):
            value = re.sub(r"^\*\*tags:\*\*\s*", "", line, flags=re.IGNORECASE)
            fields["tags"] = _norm_value(value)

        if low.startswith("**relevance:**"):
            value = re.sub(r"^\*\*relevance:\*\*\s*", "", line, flags=re.IGNORECASE)
            fields["relevance"] = _norm_value(value)

        if low.startswith("**capex related:**"):
            value = re.sub(r"^\*\*capex related:\*\*\s*", "", line, flags=re.IGNORECASE)
            fields["capex_related"] = _norm_value(value)

        if low.startswith("**ai related:**"):
            value = re.sub(r"^\*\*ai related:\*\*\s*", "", line, flags=re.IGNORECASE)
            fields["ai_related"] = _norm_value(value)

    if not fields["registrant_name_raw"]:
        cover_blob = "\n".join(clean_cover_lines)
        m = re.search(
            r"\b([A-Z][A-Za-z0-9&.,' ]{1,80}?(?:Ltd\.?|Inc\.?|Corporation|Corp\.?|PLC|LLC|Limited))\b",
            cover_blob,
        )
        if m:
            candidate = m.group(1).strip()
            if "date of report" not in candidate.lower():
                fields["registrant_name_raw"] = _norm_value(candidate)

    # Keep compatibility fields used downstream.
    fields["registrant_name_normalized"] = fields["registrant_name_raw"]
    fields["date_of_report_normalized"] = fields["date_of_report_raw"]
    fields["registrant_name"] = fields["registrant_name_raw"]
    fields["date_of_report"] = fields["date_of_report_raw"]

    for k in list(fields.keys()):
        fields[k] = _norm_value(fields[k])

    return {
        "line_count": len(clean_cover_lines),
        "raw_lines": clean_cover_lines,
        "fields": fields,
    }


def _infer_registrant_name(file_name: str, full_text: str) -> str:
    # Prefer explicit legal suffix company names seen in document text.
    pat = re.compile(
        r"\b([A-Z][A-Za-z0-9&'.,-]*(?:\s+[A-Z][A-Za-z0-9&'.,-]*){0,5}\s+(?:Ltd\.?|Inc\.?|Corporation|Corp\.?|PLC|LLC|Limited))\b"
    )
    candidates: list[str] = []
    for m in pat.finditer(full_text[:4000]):
        c = m.group(1).strip()
        lc = c.lower()
        if any(x in lc for x in ("on january", "on february", "on march", "on april", "on may", "on june", "on july", "on august", "on september", "on october", "on november", "on december")):
            continue
        if re.search(r"\d", c):
            continue
        candidates.append(c)
    if candidates:
        # Prefer shorter clean company names (e.g., "Flex Ltd.")
        candidates.sort(key=len)
        return candidates[0]

    # Fallback from naming convention: Flex_8-K_YYYY-MM-DD.html -> Flex
    stem = Path(file_name).stem
    m2 = re.match(r"^(.+?)_8-?k_", stem, re.IGNORECASE)
    if m2:
        candidate = re.sub(r"[_\-]+", " ", m2.group(1)).strip()
        return candidate
    return ""


def _parse_exhibit(line: str, next_line: str = "") -> tuple[str, str] | None:
    m = _EXHIBIT_RE.match(line)
    if not m:
        return None
    ex_id = m.group(1)
    title = (m.group(2) or "").strip()

    # Guard: avoid treating footer page numbers like "2" as exhibits.
    if ex_id.isdigit() and int(ex_id) < 10 and "exhibit" not in line.lower():
        return None

    if not title and next_line.strip() and not _ITEM_RE.match(next_line):
        title = next_line.strip()

    # If still no title and id looks like footer-ish tiny integer, skip.
    if not title and ex_id.isdigit() and int(ex_id) < 10:
        return None

    return ex_id, title


def _extract_signature_date(lines: list[str]) -> str:
    # Only inspect lines in SIGNATURES section to avoid picking unrelated dates.
    for i, line in enumerate(lines):
        low = line.lower()
        if re.match(r"^\s*date\s*[:\-]?", low):
            m = _DATE_RE.search(line)
            if m:
                return m.group(1)
            if i + 1 < len(lines):
                m2 = _DATE_RE.search(lines[i + 1])
                if m2:
                    return m2.group(1)
    for i, line in enumerate(lines):
        low = line.lower()
        if "date of report" in low:
            continue
        if "date" in low:
            m = _DATE_RE.search(line)
            if m:
                return m.group(1)
            if i + 1 < len(lines):
                m2 = _DATE_RE.search(lines[i + 1])
                if m2:
                    return m2.group(1)
    # Fallback: any date-looking token inside signatures block.
    for line in lines:
        if "date of report" in line.lower():
            continue
        m = _DATE_RE.search(line)
        if m:
            return m.group(1)
    return ""


def _parse_date_value(value: str) -> datetime | None:
    for fmt in ("%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except Exception:
            continue
    return None


def _infer_date_from_filename(file_name: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", file_name)
    return m.group(1) if m else ""


def _build_sections_from_items(lines: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    headings: list[dict[str, Any]] = []

    for i, line in enumerate(lines):
        m2 = _MD_H2_RE.match(line)
        if m2:
            headings.append({"start": i, "body_start": i + 1, "header": m2.group(1).strip(), "level": 2})
            continue

        m3 = _MD_H3_RE.match(line)
        if m3:
            headings.append({"start": i, "body_start": i + 1, "header": m3.group(1).strip(), "level": 3})

    if not headings:
        content_raw = "\n".join(lines).strip()
        content_clean = _clean_text(content_raw)
        return [
            {
                "section_id": "s1",
                "header": "Full Document",
                "level": 1,
                "item_code": "",
                "section_type": "news_section",
                "is_tail": False,
                "content": content_raw,
                "content_raw": content_raw,
                "content_cleaned_for_embedding": content_clean,
                "char_count": len(content_raw),
                "has_legal_boilerplate": False,
            }
        ], [], []

    sections: list[dict[str, Any]] = []
    exhibits: list[dict[str, Any]] = []
    legal_lines_all: list[str] = []

    # Add preface as a section if there is content before first markdown heading.
    if headings[0]["start"] > 0:
        preface = "\n".join(lines[: headings[0]["start"]]).strip()
        if preface:
            sections.append(
                {
                    "section_id": "s1",
                    "header": "Overview",
                    "level": 1,
                    "item_code": "",
                    "section_type": "news_section",
                    "is_tail": False,
                    "content": preface,
                    "content_raw": preface,
                    "content_cleaned_for_embedding": _clean_text(preface),
                    "char_count": len(preface),
                    "has_legal_boilerplate": False,
                }
            )

    start_id = len(sections) + 1
    for idx, hd in enumerate(headings, start=start_id):
        heading_pos = (idx - start_id)
        end = headings[heading_pos + 1]["start"] if heading_pos + 1 < len(headings) else len(lines)
        body = [ln for ln in lines[hd["body_start"]: end] if not _PAGE_NUM_RE.match(ln)]
        legal = [ln for ln in body if _is_legal_line(ln)]
        kept = [ln for ln in body if not _is_legal_line(ln)]

        content_raw = "\n".join(kept).strip()
        content_clean = _clean_text(content_raw)
        legal_lines_all.extend(legal)
        sections.append(
            {
                "section_id": f"s{idx}",
                "header": hd["header"],
                "level": hd["level"],
                "item_code": "",
                "section_type": "news_section",
                "is_tail": False,
                "content": content_raw,
                "content_raw": content_raw,
                "content_cleaned_for_embedding": content_clean,
                "char_count": len(content_raw),
                "has_legal_boilerplate": bool(legal),
                "legal_boilerplate_lines": legal,
            }
        )

    # Keep section IDs compact and deterministic.
    for i, s in enumerate(sections, start=1):
        s["section_id"] = f"s{i}"

    # Build explicit parent-child relationships from markdown heading levels.
    stack: list[dict[str, Any]] = []
    for s in sections:
        level = int(s.get("level", 0) or 0)
        while stack and int(stack[-1].get("level", 0) or 0) >= level:
            stack.pop()
        s["parent_section_id"] = stack[-1]["section_id"] if stack else ""
        stack.append(s)

    return sections, exhibits, legal_lines_all


def _build_full_text_core(sections: list[dict[str, Any]]) -> str:
    core: list[str] = []

    for s in sections:
        if s.get("is_tail"):
            continue

        level = int(s.get("level", 1) or 1)
        level = min(6, max(1, level))
        header = str(s.get("header", "")).strip()
        if header:
            core.append(f"{'#' * level} {header}")

        c = str(s.get("content_cleaned_for_embedding", "") or s.get("content", "")).strip()
        if c:
            core.append(c)

    return _clean_text("\n\n".join(core))


def _build_blocks_and_reading_order(
    sections: list[dict[str, Any]], legal_lines: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blocks: list[dict[str, Any]] = []
    reading_order: list[dict[str, Any]] = []
    order = 1

    for s in sections:
        hid = f"{s['section_id']}:h"
        blocks.append({
            "block_id": hid,
            "type": "heading",
            "section_id": s["section_id"],
            "page_num": 0,
            "content": s["header"],
            "char_count": len(s["header"]),
        })
        reading_order.append({"order": order, "type": "heading", "ref": hid, "page_num": 0, "preview": s["header"][:120]})
        order += 1

        c = str(s.get("content", "")).strip()
        if c:
            pid = f"{s['section_id']}:p"
            blocks.append({
                "block_id": pid,
                "type": "paragraph",
                "section_id": s["section_id"],
                "page_num": 0,
                "content": c,
                "char_count": len(c),
                "is_tail": s.get("is_tail", False),
            })
            reading_order.append({"order": order, "type": "paragraph", "ref": pid, "page_num": 0, "preview": c[:120]})
            order += 1

    for i, line in enumerate(legal_lines, start=1):
        bid = f"legal:{i}"
        blocks.append({
            "block_id": bid,
            "type": "legal_disclaimer",
            "section_id": "",
            "page_num": 0,
            "content": line,
            "char_count": len(line),
        })
        reading_order.append({"order": order, "type": "legal_disclaimer", "ref": bid, "page_num": 0, "preview": line[:120]})
        order += 1

    return blocks, reading_order


def _build_quality(
    pages: list[dict[str, Any]], sections: list[dict[str, Any]], blocks: list[dict[str, Any]],
    tables: list[dict[str, Any]], full_text: str, warnings: list[str],
) -> dict[str, Any]:
    pages_with_text = sum(1 for p in pages if p.get("char_count", 0) > 0)
    return {
        "total_pages": len(pages),
        "pages_with_text": pages_with_text,
        "pages_with_text_ratio": round(pages_with_text / len(pages), 4) if pages else 0,
        "table_count": len(tables),
        "section_count": len(sections),
        "block_count": len(blocks),
        "text_char_count": len(full_text),
        "text_word_count": len(full_text.split()),
        "warnings": warnings,
    }


def _basic_classification(rel_path: Path, file_name: str, full_text: str) -> dict[str, Any]:
    text = f"{rel_path} {file_name} {full_text[:3000]}".lower()
    signals: list[str] = []
    if "press release" in text:
        signals.append("press_release_keyword")
    if "news release" in text:
        signals.append("news_release_keyword")
    if "fiscal" in text or "quarter" in text or "earnings" in text:
        signals.append("results_keyword")
    return {
        "doc_family": "corporate_communication",
        "doc_subtype": "news_release",
        "confidence": 0.9 if len(signals) >= 2 else 0.7,
        "signals_used": signals,
    }


def parse_document(filepath: Path, rel_path: Path) -> dict[str, Any]:
    suffix = filepath.suffix.lower()
    pages, full_text, warnings = _parse_source_text(filepath, suffix)

    lines = _split_nonempty_lines(full_text)
    cover_metadata = _extract_cover_metadata(lines)
    if not cover_metadata["fields"].get("registrant_name_normalized"):
        inferred_name = _infer_registrant_name(filepath.name, full_text)
        if inferred_name:
            cover_metadata["fields"]["registrant_name_normalized"] = inferred_name
    if not cover_metadata["fields"].get("date_of_report_normalized"):
        inferred = _infer_date_from_filename(filepath.name)
        if inferred:
            cover_metadata["fields"]["date_of_report_normalized"] = inferred

    sections, exhibits, legal_lines = _build_sections_from_items(lines)
    report_date_raw = str(cover_metadata["fields"].get("date_of_report_raw", "")).strip()
    report_date_norm = str(cover_metadata["fields"].get("date_of_report_normalized", "")).strip()
    report_date = _parse_date_value(report_date_raw or report_date_norm)
    for section in sections:
        if section.get("header", "").upper() != "SIGNATURES":
            continue
        sig_raw = str(section.get("signature_date_raw", "")).strip()
        sig_date = _parse_date_value(sig_raw) if sig_raw else None
        section["signature_date"] = sig_raw
        section["signature_date_normalized"] = sig_raw
        if report_date and sig_date and abs((report_date - sig_date).days) > 45:
            if report_date_raw:
                section["signature_date_normalized"] = report_date_raw
            warnings.append("signature_date_differs_from_report_date")
    blocks, reading_order = _build_blocks_and_reading_order(sections, legal_lines)

    full_text_core = _build_full_text_core(sections)

    tables: list[dict[str, Any]] = []
    if exhibits:
        tables.append(
            {
                "table_id": "table:exhibits",
                "table_type": "exhibit_index",
                "header": ["exhibit_id", "title", "section_header"],
                "rows": [[e.get("exhibit_id", ""), e.get("title", ""), e.get("section_header", "")] for e in exhibits],
                "row_count": len(exhibits),
            }
        )

    classification = _basic_classification(rel_path, filepath.name, full_text)

    return {
        "source": {
            "doc_type": "news_release_only",
            "suffix": suffix,
            "file_name": filepath.name,
            "relative_path": str(rel_path),
            "absolute_path": str(filepath),
            "size_bytes": filepath.stat().st_size,
            "parsed_at": datetime.now().isoformat(),
        },
        "classification": classification,
        "cover_metadata": cover_metadata,
        "usage_policy": {
            "full_text_role": "inspection_full_text",
            "full_text_core_role": "chunk_embedding_input",
            "chunk_source_field": "full_text_core",
        },
        "full_text": full_text,
        "chunk_text": full_text_core,
        "full_text_core": full_text_core,
        "pages": pages,
        "blocks": blocks,
        "sections": sections,
        "exhibits": exhibits,
        "tables": tables,
        "reading_order": reading_order,
        "quality": _build_quality(pages, sections, blocks, tables, full_text, warnings),
    }


def _prepare_output_dir() -> Path:
    return prepare_output_root(
        OUTPUT_PARENT_DIR,
        legacy_marker_dirs=("news_releases",),
        current_dir_patterns=("news_releases", "news_releases_*"),
    )


def _safe_base_name(src: Path) -> str:
    ext = src.suffix.lower().lstrip(".") or "file"
    return f"{src.stem}.{ext}"


def extract_all(input_dir: Path = INPUT_DIR, output_dir: Path | None = None) -> tuple[Path, int, int, int]:
    if output_dir is None:
        output_dir = _prepare_output_dir()
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    run_stamp = _now_stamp()

    out_news = output_dir / f"news_releases_{run_stamp}"
    out_news.mkdir(parents=True, exist_ok=True)

    files = [p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES]

    success, failed = 0, 0
    errors: list[dict[str, str]] = []

    for src in files:
        rel = src.relative_to(input_dir)
        tdir = out_news / rel.parent
        tdir.mkdir(parents=True, exist_ok=True)
        try:
            parsed = parse_document(src, rel)
            out_file = tdir / f"{_safe_base_name(src)}.parsed.json"
            out_file.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            success += 1
        except Exception as e:
            failed += 1
            errors.append({"file": str(rel), "error": str(e)})

    if errors:
        (output_dir / "_errors.json").write_text(
            json.dumps({"count": len(errors), "errors": errors}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    sample_dir = prepare_shared_sample_dir(output_dir, run_stamp)
    first_sample = next(iter(sorted(out_news.rglob("*.parsed.json"))), None)
    if first_sample is not None:
        shutil.copy2(first_sample, sample_dir / first_sample.name)

    return output_dir, len(files), success, failed


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="News Release parse-only extractor")
    ap.add_argument("--input-dir", type=str, default=None, help="Input dir (default: Test_Design/File/Flex/News Releases)")
    ap.add_argument("--output-dir", type=str, default=None, help="Output dir root (default: Test_Design/File/extracted)")
    args = ap.parse_args()

    input_dir = Path(args.input_dir) if args.input_dir else INPUT_DIR
    output_dir = Path(args.output_dir) if args.output_dir else None

    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        return

    out, total, success, failed = extract_all(input_dir=input_dir, output_dir=output_dir)
    print("=" * 60)
    print("TEST DESIGN NEWS RELEASE PARSE-ONLY EXTRACTION")
    print("=" * 60)
    print(f"Input : {input_dir}")
    print(f"Output: {out}")
    print(f"Total source files : {total}")
    print(f"Extracted success  : {success}")
    print(f"Failed             : {failed}")


if __name__ == "__main__":
    main()
