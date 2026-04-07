#!/usr/bin/env python3
"""
8-K parse-only extractor focused on main-event body text.

Current priority:
- Keep cover in cover_metadata
- Build sections from first valid Item x.xx
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
INPUT_DIR = BASE_DIR / "File" / "Flex" / "flex_8k_press_releases"
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
        return _parse_pdf_text(filepath)
    if suffix in {".html", ".htm"}:
        text, warnings = _parse_html_text(filepath)
        return [], text, warnings
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
    first_item = _find_first_item_index(lines)
    cover_lines = lines[:first_item] if first_item < len(lines) else lines[: min(80, len(lines))]
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
        "form_type": "",
        "registrant_name_raw": "",
        "registrant_name_normalized": "",
        "registrant_name": "",
        "date_of_report_raw": "",
        "date_of_report_normalized": "",
        "date_of_report": "",
        "telephone_raw": "",
        "telephone": "",
        "commission_file_number_raw": "",
        "commission_file_number_normalized": "",
        "commission_file_number": "",
        "address_line_raw": "",
        "city_raw": "",
        "postal_code_raw": "",
        "address_display": "",
    }

    def _norm_value(v: str) -> str:
        s = (v or "").strip()
        if s.lower() in {"not applicable", "n/a", "na"}:
            return ""
        return s

    for i, line in enumerate(clean_cover_lines):
        low = line.lower()
        if "form 8-k" in low or "form 8k" in low:
            fields["form_type"] = "8-K"

        if "commission file number" in low:
            m = re.search(r"\b(\d{1,3}\s*-\s*\d{2,7})\b", line)
            if not m:
                lo = max(0, i - 6)
                hi = min(len(clean_cover_lines), i + 4)
                for cand in clean_cover_lines[lo:hi]:
                    mm = re.search(r"\b(\d{1,3}\s*-\s*\d{2,7})\b", cand)
                    if mm:
                        m = mm
                        break
            if m:
                fields["commission_file_number_raw"] = re.sub(r"\s+", "", m.group(1))

        if "telephone number" in low:
            m = _PHONE_RE.search(line)
            parsed_phone = ""
            if not m:
                window = " ".join(clean_cover_lines[max(0, i - 2): min(len(clean_cover_lines), i + 6)])
                area_match = re.search(r"\(\s*(\d{1,4})\s*\)\s*([0-9][0-9\s.-]{5,})", window)
                if area_match:
                    area = area_match.group(1).strip()
                    local = re.sub(r"\s+", " ", area_match.group(2)).strip()
                    parsed_phone = f"({area}) {local}"
                m = _PHONE_RE.search(window)
            if parsed_phone:
                fields["telephone_raw"] = parsed_phone
            elif m:
                digits = re.sub(r"\D", "", m.group(0))
                if len(digits) >= 8:
                    if len(digits) == 10:
                        fields["telephone_raw"] = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
                    elif len(digits) == 9:
                        fields["telephone_raw"] = f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
                    else:
                        fields["telephone_raw"] = m.group(0).strip()

        if "date of report" in low:
            m = _DATE_RE.search(line)
            if not m and i + 1 < len(clean_cover_lines):
                m = _DATE_RE.search(clean_cover_lines[i + 1])
            if m:
                fields["date_of_report_raw"] = m.group(1)

        if "exact name of registrant" in low:
            candidates: list[str] = []
            if i > 0:
                candidates.append(clean_cover_lines[i - 1].strip())
            if i + 1 < len(clean_cover_lines):
                candidates.append(clean_cover_lines[i + 1].strip())
            for c in candidates:
                if not c:
                    continue
                lc = c.lower()
                if "exact name of registrant" in lc:
                    continue
                if "securities exchange act" in lc:
                    continue
                if "commission file number" in lc:
                    continue
                if "date of report" in lc:
                    continue
                if _PAGE_NUM_RE.match(c):
                    continue
                fields["registrant_name_raw"] = _norm_value(c)
                break

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

    # Best-effort cover address extraction while keeping raw field boundaries.
    for i, line in enumerate(clean_cover_lines):
        if "address of principal executive offices" not in line.lower():
            continue
        block = clean_cover_lines[max(0, i - 5): i]
        tokens = [t.strip() for t in block if t.strip() and not t.strip().startswith("(")]
        merged: list[str] = []
        for t in tokens:
            if t == "," and merged:
                merged[-1] = f"{merged[-1]},"
            else:
                merged.append(t)

        postal = ""
        for k in range(len(merged) - 1, -1, -1):
            if re.fullmatch(r"\d{4,10}(?:-\d{3,6})?", merged[k]):
                postal = merged.pop(k)
                break

        city = ""
        for k in range(len(merged) - 1, -1, -1):
            cand = merged[k].rstrip(",").strip()
            if cand and not re.search(r"\d", cand):
                city = cand
                merged.pop(k)
                break

        address_line = " ".join(merged).replace(" ,", ",").strip(" ,")
        fields["address_line_raw"] = address_line
        fields["city_raw"] = city
        fields["postal_code_raw"] = postal
        display_parts = [p for p in [address_line, city, postal] if p]
        fields["address_display"] = " ".join(display_parts[:1]) if len(display_parts) == 1 else (
            f"{display_parts[0]}, {' '.join(display_parts[1:])}" if display_parts else ""
        )
        break

    # Raw and normalized are separated; normalized is optional and never overwrites raw.
    fields["registrant_name_normalized"] = fields["registrant_name_raw"]
    fields["date_of_report_normalized"] = fields["date_of_report_raw"]
    fields["commission_file_number_normalized"] = fields["commission_file_number_raw"]
    fields["registrant_name"] = fields["registrant_name_raw"]
    fields["date_of_report"] = fields["date_of_report_raw"]
    fields["telephone"] = fields["telephone_raw"]
    fields["commission_file_number"] = fields["commission_file_number_raw"]

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


def _sync_signature_content_date(content: str, normalized_date: str) -> str:
    if not content or not normalized_date:
        return content

    date_token = r"([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"
    # Prefer replacing a date on "Date:" line.
    pat1 = rf"(?im)^(\s*date\s*[:\-]?\s*){date_token}\b"
    out, n = re.subn(pat1, rf"\1{normalized_date}", content, count=1)
    if n > 0:
        return out

    # Fallback: replace the first date-looking token in signature content.
    out, n = re.subn(date_token, normalized_date, content, count=1)
    return out if n > 0 else content


def _infer_date_from_filename(file_name: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", file_name)
    return m.group(1) if m else ""


def _build_sections_from_items(lines: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    headings: list[dict[str, Any]] = []

    for i, line in enumerate(lines):
        m = _ITEM_RE.match(line)
        if m:
            code = m.group(1)
            rest = m.group(2).strip()
            start = i + 1
            if not rest and i + 1 < len(lines) and _is_title_like(lines[i + 1]):
                rest = lines[i + 1].strip()
                start = i + 2
            header = f"Item {code}" + (f" {rest}" if rest else "")
            headings.append({"start": i, "body_start": start, "header": header, "item_code": code})
        elif _SIGNATURE_RE.match(line):
            headings.append({"start": i, "body_start": i + 1, "header": "SIGNATURES", "item_code": ""})

    if not headings:
        content_raw = "\n".join(lines).strip()
        content_clean = _clean_text(content_raw)
        return [
            {
                "section_id": "s1",
                "header": "Full Document",
                "level": 1,
                "item_code": "",
                "section_type": "filing_item",
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

    for idx, hd in enumerate(headings, start=1):
        end = headings[idx]["start"] if idx < len(headings) else len(lines)
        body = lines[hd["body_start"]: end]
        section_exhibit_ids: list[str] = []

        kept: list[str] = []
        legal: list[str] = []
        j = 0
        while j < len(body):
            line = body[j]
            nxt = body[j + 1] if j + 1 < len(body) else ""

            in_tail_exhibit_zone = hd["item_code"] == "9.01" or "exhibit" in hd["header"].lower()
            if in_tail_exhibit_zone and _is_exhibit_line(line):
                ex = _parse_exhibit(line, nxt)
                if ex is not None:
                    ex_id, title = ex
                    exhibits.append(
                        {
                            "exhibit_id": ex_id,
                            "title": title,
                            "line": line,
                            "section_header": hd["header"],
                        }
                    )
                    section_exhibit_ids.append(ex_id)
                    kept.append(line)
                    if re.match(r"^\s*\d{1,3}(?:\.\d+)?\s*$", line) and nxt.strip():
                        kept.append(nxt.strip())
                        j += 2
                    else:
                        j += 1
                    continue

            if _PAGE_NUM_RE.match(line):
                j += 1
                continue
            if _is_legal_line(line):
                legal.append(line)
                j += 1
                continue

            kept.append(line)
            j += 1

        while kept and _PAGE_NUM_RE.match(kept[-1]):
            kept.pop()

        legal_lines_all.extend(legal)

        is_tail = hd["item_code"] == "9.01" or hd["header"].upper() == "SIGNATURES"
        section_type = "tail" if is_tail else "filing_item"

        content_raw = "\n".join(kept).strip()
        content_clean = _clean_text(content_raw)
        signature_date_raw = _extract_signature_date(kept) if hd["header"].upper() == "SIGNATURES" else ""
        sections.append(
            {
                "section_id": f"s{idx}",
                "header": hd["header"],
                "level": 1,
                "item_code": hd["item_code"],
                "section_type": section_type,
                "is_tail": is_tail,
                "content": content_raw,
                "content_raw": content_raw,
                "content_cleaned_for_embedding": content_clean,
                "char_count": len(content_raw),
                "has_legal_boilerplate": bool(legal),
                "legal_boilerplate_lines": legal,
                "signature_date_raw": signature_date_raw,
                "signature_date_normalized": signature_date_raw,
                "signature_date": signature_date_raw,
            }
        )

    return sections, exhibits, legal_lines_all


def _build_full_text_core(sections: list[dict[str, Any]]) -> str:
    core: list[str] = []

    # Primary: only preferred event Items.
    for s in sections:
        if s.get("item_code") in PREFERRED_CORE_ITEMS and not s.get("is_tail"):
            c = str(s.get("content_cleaned_for_embedding", "") or s.get("content", "")).strip()
            if c:
                core.append(c)

    # Fallback: all non-tail filing items except 9.01.
    if not core:
        for s in sections:
            if s.get("is_tail"):
                continue
            if s.get("item_code") == "9.01":
                continue
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
    if "8-k" in text or "8k" in text:
        signals.append("8k_keyword")
    if "press release" in text:
        signals.append("press_release_keyword")
    if "current report" in text and "section 13 or 15(d)" in text:
        signals.append("sec_current_report_pattern")
    return {
        "doc_family": "regulatory_filing",
        "doc_subtype": "8k_press_release",
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

    first_item = _find_first_item_index(lines)
    body_lines = lines[first_item:] if first_item < len(lines) else []
    sections, exhibits, legal_lines = _build_sections_from_items(body_lines)
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
            normalized_target = report_date_raw or report_date_norm
            if normalized_target:
                section["signature_date_normalized"] = normalized_target
                section["signature_date"] = normalized_target
                original_content = str(section.get("content", ""))
                synced_content = _sync_signature_content_date(original_content, normalized_target)
                section["content"] = synced_content.strip()
                section["content_cleaned_for_embedding"] = _clean_text(section["content"])
                section["char_count"] = len(section["content"])
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
            "doc_type": "8k_only",
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
        legacy_marker_dirs=("flex_8k_press_releases",),
        current_dir_patterns=("flex_8k_press_releases", "flex_8k_press_releases_*"),
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

    out_8k = output_dir / f"flex_8k_press_releases_{run_stamp}"
    out_8k.mkdir(parents=True, exist_ok=True)

    files = [p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES]

    success, failed = 0, 0
    errors: list[dict[str, str]] = []

    for src in files:
        rel = src.relative_to(input_dir)
        tdir = out_8k / rel.parent
        tdir.mkdir(parents=True, exist_ok=True)
        try:
            parsed = parse_document(src, rel)
            out_file = tdir / f"{_safe_base_name(src)}.parsed.json"
            out_file.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            success += 1
        except Exception as e:
            failed += 1
            errors.append({"file": str(rel), "error": str(e)})

    errors_file = output_dir / "_errors.json"
    if errors:
        errors_file.write_text(
            json.dumps({"count": len(errors), "errors": errors}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif errors_file.exists():
        errors_file.unlink()

    sample_dir = prepare_shared_sample_dir(output_dir, run_stamp)
    first_sample = next(iter(sorted(out_8k.rglob("*.parsed.json"))), None)
    if first_sample is not None:
        shutil.copy2(first_sample, sample_dir / first_sample.name)

    return output_dir, len(files), success, failed


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="8-K main-event parse-only extractor")
    ap.add_argument("--input-dir", type=str, default=None, help="Input dir (default: Test_Design/File/Flex/flex_8k_press_releases)")
    ap.add_argument("--output-dir", type=str, default=None, help="Output dir root (default: Test_Design/File/extracted)")
    args = ap.parse_args()

    input_dir = Path(args.input_dir) if args.input_dir else INPUT_DIR
    output_dir = Path(args.output_dir) if args.output_dir else None

    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        return

    out, total, success, failed = extract_all(input_dir=input_dir, output_dir=output_dir)
    print("=" * 60)
    print("TEST DESIGN 8-K PARSE-ONLY EXTRACTION")
    print("=" * 60)
    print(f"Input : {input_dir}")
    print(f"Output: {out}")
    print(f"Total source files : {total}")
    print(f"Extracted success  : {success}")
    print(f"Failed             : {failed}")


if __name__ == "__main__":
    main()
