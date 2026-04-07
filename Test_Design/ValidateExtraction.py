#!/usr/bin/env python3
"""
ValidateExtraction.py — 解析结果质量校验脚本 (QC Validator)

对 parsed.json 提取结果进行质量检查：必需字段完整性、关键 Section/Item 覆盖率、
正文总量、原文对齐/锚点/数字/标题回溯、页眉页脚污染、目录污染、
残句截断、Chunk 重复率、标题层级保留、表格提取。

Usage
-----
  # 验证单个文件：
  python ValidateExtraction.py --file path/to/file.parsed.json

  # 自动检测最新 _test_samples_* 文件夹并批量验证：
  python ValidateExtraction.py --batch

  # 指定样本文件夹批量验证：
  python ValidateExtraction.py --samples-dir path/to/_test_samples_2026-04-06_18-09-12

报告输出至: Test_Design/File/extracted/validation_reports/<timestamp>/
  - report.json   — 机器可读的完整结果
  - report.md     — 人类可读的汇总报告
  - examples.md   — 原文脱锚/污染/截断/重复样本摘录
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
EXTRACTED_DIR = BASE_DIR / "File" / "extracted"
REPORTS_DIR = EXTRACTED_DIR / "validation_reports"
SOURCE_ROOT = BASE_DIR / "File" / "Flex"

MAX_REPORT_RUNS = 5  # 最多保留最近 N 次报告

# ---------------------------------------------------------------------------
# Doc-type configuration
# ---------------------------------------------------------------------------

DOC_TYPE_CONFIG: dict[str, dict] = {
    "10k": {
        "expected_items": ["1", "1A", "7", "8"],
        "min_words": 30_000,
        "max_words": 300_000,
        "expect_tables": True,
        "min_source_coverage": 0.45,
    },
    "10q": {
        "expected_items": ["1", "1A", "2"],
        "min_words": 8_000,
        "max_words": 100_000,
        "expect_tables": True,
        "min_source_coverage": 0.35,
    },
    "8k": {
        "expected_items": [],
        "min_words": 100,
        "max_words": 50_000,
        "expect_tables": False,
        "min_source_coverage": 0.08,
    },
    "ep": {
        "expected_items": [],
        "min_words": 2_000,
        "max_words": 50_000,
        "expect_tables": False,
        "min_source_coverage": 0.12,
    },
    "transcript": {
        "expected_items": [],
        "min_words": 2_000,
        "max_words": 100_000,
        "expect_tables": False,
        "min_source_coverage": 0.30,
    },
    "press_release": {
        "expected_items": [],
        "min_words": 100,
        "max_words": 15_000,
        "expect_tables": False,
        "min_source_coverage": 0.18,
    },
    "news_release": {
        "expected_items": [],
        "min_words": 100,
        "max_words": 15_000,
        "expect_tables": False,
        "min_source_coverage": 0.18,
    },
    "default": {
        "expected_items": [],
        "min_words": 50,
        "max_words": 500_000,
        "expect_tables": False,
        "min_source_coverage": 0.05,
    },
}

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# TOC 行: e.g. "Item 1 ......... 5" or "PART I ...... 12"
_TOC_PATTERNS = [
    re.compile(r"\.{5,}\s*\d+\s*$"),
    re.compile(
        r"^(?:item\s+\d+[a-c]?|part\s+[iv]+)\b.{0,70}\.{3,}",
        re.IGNORECASE,
    ),
]

# 页眉/页脚样板
_HF_PATTERNS = [
    re.compile(r"^\s*\d{1,3}\s*$"),                               # 孤立页码
    re.compile(r"^\s*flex\s+ltd\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*flextronics\s+international\s*$", re.IGNORECASE),
    re.compile(r"^\s*(annual|quarterly)\s+report\s*$", re.IGNORECASE),
    re.compile(r"^\s*form\s+(?:10-[kq]|8-k)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:1-877-factset|www\.callstreet\.com)\s*$", re.IGNORECASE),
]

# 正常句尾标点
_SENTENCE_END_CHARS = frozenset(".!?;:")

_DOC_TYPE_SOURCE_DIRS: dict[str, tuple[str, ...]] = {
    "10k": ("annual_10K",),
    "10q": ("quarterly_10Q",),
    "8k": ("flex_8k_press_releases",),
    "ep": ("Earnings Presentation",),
    "transcript": ("flex_transcripts",),
    "press_release": ("Press Releases",),
    "news_release": ("News Releases",),
}

_INLINE_TOC_PATTERN = re.compile(r"\btable\s+of\s+contents\b", re.IGNORECASE)
_INLINE_HF_PATTERNS = [
    re.compile(
        r"\bwashington,\s*d\.c\.\s*20549\b.{0,90}\bform\s+(?:10-[kq]|8-k)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bform\s+(?:10-[kq]|8-k)\b.{0,40}\bmark\s+one\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:annual|quarterly)\s+report\b.{0,60}\bpursuant\s+to\s+section\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:1-877-factset|www\.callstreet\.com|callstreet)\b", re.IGNORECASE),
]

_NUMERIC_TOKEN_RE = re.compile(
    r"(?<!\w)(?:[$€£]?\d[\d,]*(?:\.\d+)?(?:-\d+)?%?)(?!\w)"
)

_CONTINUATION_OPENERS = {
    "and", "or", "but", "with", "to", "of", "for", "in", "on", "by", "as",
    "that", "which", "who", "whose", "while", "including", "such", "because",
    "if", "when", "where", "than", "then", "also", "however",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_doc_type(data: dict) -> tuple[str, str]:
    """Return (raw_string, normalised_key)."""
    raw = data.get("source", {}).get("doc_type", "")
    if not raw:
        raw = data.get("document", {}).get("form_type", "")
    if not raw:
        raw = data.get("source", {}).get("file_name", "")
    return raw, _normalise(raw)


def _normalise(raw: str) -> str:
    s = raw.lower()
    if "10k" in s or "10-k" in s or "annual" in s:
        return "10k"
    if "10q" in s or "10-q" in s or "quarter" in s:
        return "10q"
    if "8k" in s or "8-k" in s:
        return "8k"
    if "transcript" in s:
        return "transcript"
    if "earning" in s or "presentation" in s:
        return "ep"
    if "press" in s:
        return "press_release"
    if "news" in s:
        return "news_release"
    return "default"


def _get_total_words(data: dict) -> int:
    q = data.get("quality", {})
    return q.get("total_words") or q.get("text_word_count") or 0


def _collect_text_units(data: dict) -> list[str]:
    """
    收集所有文本单元（chunks / blocks / section content），适配各种 schema。
    每个 parsed.json 只调用一次，结果缓存在 data["_text_units"]。
    """
    texts: list[str] = []

    # 10-K / 10-Q: sections → chunks[]
    for sec in data.get("sections", []):
        for chunk in sec.get("chunks", []):
            t = chunk.get("text", "").strip()
            if t:
                texts.append(t)

    # EP: top-level chunks[]
    for chunk in data.get("chunks", []):
        t = chunk.get("text", "").strip()
        if t:
            texts.append(t)

    # 8-K / transcript / press / news: blocks[]
    for block in data.get("blocks", []):
        t = block.get("content", "").strip()
        if t:
            texts.append(t)

    # fallback: sections with inline content
    if not texts:
        for sec in data.get("sections", []):
            for field in ("content_cleaned_for_embedding", "content"):
                t = sec.get(field, "").strip()
                if t:
                    texts.append(t)
                    break

    return texts


def _wc(text: str) -> int:
    return len(text.split())


def _jaccard(a: str, b: str) -> float:
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _looks_truncated(text: str) -> bool:
    """判断一段文本是否在句中被截断。"""
    stripped = text.rstrip()
    if len(stripped) < 50:
        return False  # 太短无法判断（可能是标题或 heading）
    # 向前跳过尾部引号/括号，找到真正的末尾字符
    i = len(stripped) - 1
    while i > 0 and stripped[i] in "\"')]\u201d\u2019\u00bb":
        i -= 1
    return stripped[i] not in _SENTENCE_END_CHARS


def _normalise_match_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _tokenise_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:['/&.-][a-z0-9]+)*", text.lower())


def _extract_numeric_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _NUMERIC_TOKEN_RE.finditer(text):
        token = match.group(0).strip().strip("()[]{}")
        token = token.lstrip("$€£").replace(",", "")
        if token.isdigit() and len(token) == 1:
            continue
        if token:
            tokens.append(token.lower())
    return tokens


def _snippet_around(text: str, start: int, end: int, width: int = 36) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    snippet = text[left:right].strip()
    if left > 0:
        snippet = "..." + snippet
    if right < len(text):
        snippet = snippet + "..."
    return repr(snippet)


def _collect_parsed_headings(data: dict) -> list[str]:
    seen: set[str] = set()
    headings: list[str] = []

    for sec in data.get("sections", []):
        heading = str(sec.get("header", "")).strip()
        if heading and heading not in seen:
            headings.append(heading)
            seen.add(heading)

    for block in data.get("blocks", []):
        if block.get("type") != "heading":
            continue
        heading = str(block.get("content", "")).strip()
        if heading and heading not in seen:
            headings.append(heading)
            seen.add(heading)

    return headings


def resolve_source_path(
    data: dict, parsed_path: Path | None = None
) -> tuple[Path | None, str]:
    """Resolve the original source file from source.absolute_path / relative_path."""
    src = data.get("source", {})
    raw_type, doc_type = _detect_doc_type(data)
    del raw_type  # 仅为保持 _detect_doc_type 的使用一致

    candidates: list[tuple[Path, str]] = []

    abs_path = src.get("absolute_path")
    if abs_path:
        candidates.append((Path(abs_path).expanduser(), "absolute_path"))

    rel_path = src.get("relative_path")
    if rel_path:
        rel = Path(rel_path)
        if rel.is_absolute():
            candidates.append((rel, "relative_path(abs)"))
        if parsed_path is not None:
            candidates.append((parsed_path.parent / rel, "relative_path@parsed_dir"))
        candidates.append((BASE_DIR / rel, "relative_path@base_dir"))
        candidates.append((SOURCE_ROOT / rel, "relative_path@source_root"))
        for folder in _DOC_TYPE_SOURCE_DIRS.get(doc_type, ()):
            candidates.append(
                (SOURCE_ROOT / folder / rel.name, f"relative_path@{folder}")
            )

    seen: set[str] = set()
    for candidate, method in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate, method

    for fallback_name in filter(None, [Path(abs_path).name if abs_path else "", Path(rel_path).name if rel_path else ""]):
        matches = sorted(SOURCE_ROOT.rglob(fallback_name))
        if len(matches) == 1:
            return matches[0], "filename_search"

    return None, "unresolved"


def _extract_html_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return re.sub(r"<[^>]+>", " ", raw)

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n")


def _extract_pdf_text(path: Path) -> str:
    try:
        import pdfplumber
    except Exception as exc:
        raise RuntimeError(f"pdfplumber 不可用: {exc}") from exc

    texts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                texts.append(text)
    return "\n\n".join(texts)


def extract_reference_text(source_path: Path) -> dict:
    """Read original source text for grounding comparison."""
    suffix = source_path.suffix.lower()

    if suffix in {".html", ".htm"}:
        text = _extract_html_text(source_path)
    elif suffix == ".pdf":
        text = _extract_pdf_text(source_path)
    else:
        text = source_path.read_text(encoding="utf-8", errors="ignore")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalised = _normalise_match_text(text)
    token_stream = " ".join(_tokenise_words(normalised))

    return {
        "path": str(source_path),
        "suffix": suffix,
        "text": text,
        "lines": lines,
        "normalised_text": normalised,
        "token_stream": token_stream,
        "word_count": len(_tokenise_words(normalised)),
        "char_count": len(text),
    }


def _build_anchor_candidates(text: str, window_words: int = 8) -> list[str]:
    words = _tokenise_words(_normalise_match_text(text))
    if len(words) < window_words:
        return []

    starts = {
        0,
        max(0, len(words) // 2 - window_words // 2),
        max(0, len(words) - window_words),
    }
    anchors: list[str] = []
    for start in sorted(starts):
        anchor = " ".join(words[start:start + window_words]).strip()
        if len(anchor) >= 24 and anchor not in anchors:
            anchors.append(anchor)
    return anchors


def compare_parsed_to_reference(data: dict, cfg: dict, parsed_path: Path) -> dict:
    """
    Compare parsed output to original source file.
    输出会缓存到 data["_reference_analysis"]，供多个检查项复用。
    """
    source_path, resolved_via = resolve_source_path(data, parsed_path=parsed_path)
    fallback_detail = {
        "score": 0.5,
        "issues": [],
        "examples": [],
        "note": "未执行原文比对。",
    }

    if source_path is None:
        issue = "无法解析 source.absolute_path / source.relative_path 指向的原文件。"
        detail = {
            **fallback_detail,
            "issues": [issue],
            "note": "原文件缺失时，仅能基于 parsed.json 自身做静态检查。",
        }
        return {
            "source_available": False,
            "source_path": "",
            "resolved_via": resolved_via,
            "error": issue,
            "source_alignment": detail,
            "anchor_coverage": detail,
            "numeric_consistency": detail,
            "heading_consistency": detail,
        }

    try:
        reference = extract_reference_text(source_path)
    except Exception as exc:
        issue = f"读取原文件失败: {exc}"
        detail = {
            **fallback_detail,
            "issues": [issue],
            "note": "原文件读取失败时，未执行对齐检查。",
        }
        return {
            "source_available": False,
            "source_path": str(source_path),
            "resolved_via": resolved_via,
            "error": issue,
            "source_alignment": detail,
            "anchor_coverage": detail,
            "numeric_consistency": detail,
            "heading_consistency": detail,
        }

    parsed_units = data.get("_text_units", [])
    parsed_text = "\n\n".join(t for t in parsed_units if t).strip()
    parsed_norm = _normalise_match_text(parsed_text)
    reference_norm = reference["normalised_text"]
    reference_tokens_text = reference["token_stream"]

    parsed_words = _tokenise_words(parsed_norm)
    ref_words = _tokenise_words(reference_norm)
    parsed_word_set = {w for w in parsed_words if len(w) > 2 or w.isdigit()}
    ref_word_set = {w for w in ref_words if len(w) > 2 or w.isdigit()}
    shared_word_ratio = (
        len(parsed_word_set & ref_word_set) / len(parsed_word_set)
        if parsed_word_set else 0.0
    )

    parsed_word_count = len(parsed_words)
    ref_word_count = len(ref_words)
    coverage_ratio = (
        parsed_word_count / ref_word_count if ref_word_count else 0.0
    )
    min_coverage = float(cfg.get("min_source_coverage", 0.05))
    coverage_score = min(1.0, coverage_ratio / max(min_coverage, 0.01))
    alignment_score = min(1.0, shared_word_ratio * 0.65 + coverage_score * 0.35)
    alignment_issues: list[str] = []
    alignment_examples: list[str] = []

    if parsed_word_count == 0:
        alignment_issues.append("parsed.json 未提取到可比对的正文文本。")
    if coverage_ratio < min_coverage:
        alignment_issues.append(
            f"parsed 正文仅覆盖原文约 {coverage_ratio:.1%}，低于当前类型阈值 {min_coverage:.0%}。"
        )
    if shared_word_ratio < 0.82:
        alignment_issues.append(
            f"parsed 词汇与原文的对齐率仅 {shared_word_ratio:.1%}，存在原文脱锚风险。"
        )
    if coverage_ratio > 1.2:
        alignment_issues.append(
            f"parsed 正文长度约为原文的 {coverage_ratio:.1%}，可能混入了重复或无关内容。"
        )
    if parsed_text:
        alignment_examples.append(
            repr(parsed_text[:160].replace("\n", " ").strip() + ("..." if len(parsed_text) > 160 else ""))
        )

    eligible_units = 0
    covered_units = 0
    anchor_examples: list[str] = []

    for idx, text in enumerate(parsed_units):
        anchors = _build_anchor_candidates(text)
        if not anchors:
            continue
        eligible_units += 1
        if any(anchor in reference_tokens_text for anchor in anchors):
            covered_units += 1
            continue
        if len(anchor_examples) < 6:
            anchor_examples.append(
                f"chunk#{idx + 1}: {repr(' '.join(_tokenise_words(text)[:10]))}"
            )

    anchor_ratio = covered_units / eligible_units if eligible_units else 1.0
    anchor_issues: list[str] = []
    if eligible_units == 0:
        anchor_issues.append("无足够长的 chunk 可用于锚点比对。")
    elif anchor_ratio < 0.75:
        anchor_issues.append(
            f"仅 {covered_units}/{eligible_units} 个 chunk 能在原文中找到锚点。"
        )

    parsed_number_counter = Counter(_extract_numeric_tokens(parsed_text))
    ref_number_counter = Counter(_extract_numeric_tokens(reference["text"]))
    total_number_mentions = sum(parsed_number_counter.values())
    matched_number_mentions = sum(
        count for num, count in parsed_number_counter.items() if num in ref_number_counter
    )
    numeric_ratio = (
        matched_number_mentions / total_number_mentions
        if total_number_mentions else 1.0
    )
    numeric_examples = [
        num for num, _ in parsed_number_counter.most_common()
        if num not in ref_number_counter
    ][:8]
    numeric_issues: list[str] = []
    if total_number_mentions and numeric_ratio < 0.9:
        numeric_issues.append(
            f"parsed 数值与原文的命中率仅 {numeric_ratio:.1%}。"
        )
    elif not total_number_mentions:
        numeric_issues.append("parsed 正文中未检测到可比较的数字。")

    parsed_headings = _collect_parsed_headings(data)
    eligible_headings = [
        h for h in parsed_headings if len(_tokenise_words(h)) >= 1
    ]
    matched_headings = [
        h for h in eligible_headings
        if " ".join(_tokenise_words(_normalise_match_text(h)))
        and " ".join(_tokenise_words(_normalise_match_text(h))) in reference_tokens_text
    ]
    heading_ratio = (
        len(matched_headings) / len(eligible_headings)
        if eligible_headings else 1.0
    )
    missing_headings = [
        h for h in eligible_headings if h not in matched_headings
    ][:6]
    heading_issues: list[str] = []
    if eligible_headings and heading_ratio < 0.8:
        heading_issues.append(
            f"仅 {len(matched_headings)}/{len(eligible_headings)} 个标题能在原文中回溯到。"
        )
    elif not eligible_headings:
        heading_issues.append("无可比较的 parsed 标题。")

    return {
        "source_available": True,
        "source_path": str(source_path),
        "resolved_via": resolved_via,
        "reference_word_count": ref_word_count,
        "parsed_word_count": parsed_word_count,
        "source_alignment": {
            "score": alignment_score,
            "parsed_word_count": parsed_word_count,
            "reference_word_count": ref_word_count,
            "coverage_ratio": round(coverage_ratio, 4),
            "shared_word_ratio": round(shared_word_ratio, 4),
            "issues": alignment_issues,
            "examples": alignment_examples[:4],
        },
        "anchor_coverage": {
            "score": anchor_ratio,
            "covered_units": covered_units,
            "eligible_units": eligible_units,
            "ratio": round(anchor_ratio, 4),
            "issues": anchor_issues,
            "examples": anchor_examples,
        },
        "numeric_consistency": {
            "score": numeric_ratio,
            "total_numeric_mentions": total_number_mentions,
            "matched_numeric_mentions": matched_number_mentions,
            "ratio": round(numeric_ratio, 4),
            "issues": numeric_issues,
            "examples": numeric_examples,
        },
        "heading_consistency": {
            "score": heading_ratio,
            "matched_headings": len(matched_headings),
            "total_headings": len(eligible_headings),
            "ratio": round(heading_ratio, 4),
            "issues": heading_issues,
            "examples": missing_headings,
        },
    }


def _reference_check_detail(data: dict, key: str) -> tuple[float, dict]:
    ref = data.get("_reference_analysis", {})
    detail = dict(ref.get(key, {}))
    score = float(detail.pop("score", 0.5))
    if ref.get("source_path"):
        detail.setdefault("source_path", ref["source_path"])
        detail.setdefault("resolved_via", ref.get("resolved_via", ""))
    if ref.get("error"):
        issues = list(detail.get("issues", []))
        if ref["error"] not in issues:
            issues.append(ref["error"])
        detail["issues"] = issues
    return score, detail


def check_inline_toc_contamination(text: str) -> list[str]:
    hits: list[str] = []
    for match in _INLINE_TOC_PATTERN.finditer(text):
        stripped = text.strip()
        if _INLINE_TOC_PATTERN.fullmatch(stripped):
            continue
        hits.append(_snippet_around(text, match.start(), match.end()))
    return hits


def check_inline_header_noise(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in _INLINE_HF_PATTERNS:
        for match in pattern.finditer(text):
            stripped = text.strip()
            if pattern.fullmatch(stripped):
                continue
            hits.append(_snippet_around(text, match.start(), match.end()))
    return hits


def _edge_overlap_words(prev_text: str, next_text: str, min_words: int = 4, max_words: int = 18) -> int:
    prev_words = _tokenise_words(_normalise_match_text(prev_text))
    next_words = _tokenise_words(_normalise_match_text(next_text))
    max_len = min(len(prev_words), len(next_words), max_words)
    for size in range(max_len, min_words - 1, -1):
        if prev_words[-size:] == next_words[:size]:
            return size
    return 0


def _looks_like_continuation_start(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return False
    if stripped[0].islower() or stripped[0] in ",;:)]}\"'":
        return True
    words = _tokenise_words(stripped[:80])
    return bool(words) and words[0] in _CONTINUATION_OPENERS


def _looks_like_boundary_start(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    first_line = stripped.splitlines()[0].strip()
    if not first_line:
        return False
    if first_line.startswith(("#", "|", "<!--")):
        return True
    if re.match(r"^(item|part)\b", first_line, re.IGNORECASE):
        return True
    words = _tokenise_words(first_line)
    if not words:
        return False
    if len(words) <= 8 and first_line == first_line.upper():
        return True
    titlecase_words = sum(
        1 for raw in first_line.split()
        if raw[:1].isalpha() and raw[:1].isupper()
    )
    return len(words) <= 6 and titlecase_words >= max(1, len(first_line.split()) - 1)


def _looks_like_structural_block(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if any(marker in stripped for marker in ("<!--", "|", "/s/")):
        return True

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if not lines:
        return False

    short_lines = sum(1 for line in lines if len(_tokenise_words(line)) <= 6)
    if len(lines) >= 3 and short_lines >= max(3, len(lines) - 1):
        return True

    words = _tokenise_words(stripped)
    sentence_punct = sum(stripped.count(ch) for ch in ".!?")
    return len(words) >= 1 and len(lines) >= 4 and sentence_punct == 0


# ---------------------------------------------------------------------------
# Individual checks  (all: data, cfg → (score 0..1, detail dict))
# text_units 由调用方预先注入到 data["_text_units"]
# ---------------------------------------------------------------------------


def check_structure(data: dict, cfg: dict) -> tuple[float, dict]:
    """必需的顶层字段是否齐全。"""
    issues: list[str] = []

    for field in ("source", "quality"):
        if field not in data:
            issues.append(f"缺少顶层字段: '{field}'")

    src = data.get("source", {})
    if not src.get("file_name"):
        issues.append("source.file_name 为空或缺失")
    if not src.get("absolute_path") and not src.get("relative_path"):
        issues.append("source 中既无 absolute_path 也无 relative_path")

    has_sections = bool(data.get("sections"))
    has_blocks = bool(data.get("blocks"))
    has_chunks = bool(data.get("chunks"))

    if not has_sections and not has_blocks and not has_chunks:
        issues.append("未找到 sections / blocks / chunks — 文档内容为空")

    score = max(0.0, 1.0 - len(issues) * 0.3)
    return score, {
        "issues": issues,
        "has_sections": has_sections,
        "has_blocks": has_blocks,
        "has_top_chunks": has_chunks,
    }


def check_key_items(data: dict, cfg: dict) -> tuple[float, dict]:
    """关键 Section/Item 是否被提取到。"""
    expected = cfg["expected_items"]
    if not expected:
        return 1.0, {"note": "该文档类型无预设的必需 Item。"}

    quality = data.get("quality", {})
    found: list[str] = list(quality.get("item_codes_found", []))

    if not found:
        for sec in data.get("sections", []):
            code = sec.get("item_code")
            if code:
                found.append(str(code))

    found_upper = {str(c).upper() for c in found}
    expected_upper = [e.upper() for e in expected]
    missing = [e for e in expected_upper if e not in found_upper]

    score = max(0.0, 1.0 - len(missing) / len(expected_upper))
    return score, {
        "expected": expected_upper,
        "found": sorted(found_upper),
        "missing": missing,
    }


def check_content_volume(data: dict, cfg: dict) -> tuple[float, dict]:
    """正文总量是否在合理区间内。"""
    total_words = _get_total_words(data)

    if total_words == 0:
        units = data.get("_text_units", [])
        total_words = sum(_wc(t) for t in units)

    min_w, max_w = cfg["min_words"], cfg["max_words"]
    issues: list[str] = []

    if total_words < min_w:
        issues.append(
            f"总词数 {total_words:,} 低于最低阈值 {min_w:,} — 可能提取失败或内容为空"
        )
        score = max(0.0, total_words / min_w)
    elif total_words > max_w:
        issues.append(
            f"总词数 {total_words:,} 超出上限 {max_w:,} — 可能混入了无关内容"
        )
        score = 0.6
    else:
        score = 1.0

    return score, {
        "total_words": total_words,
        "min_expected": min_w,
        "max_expected": max_w,
        "issues": issues,
    }


def check_source_alignment(data: dict, cfg: dict) -> tuple[float, dict]:
    """parsed 文本与原文件是否整体对齐。"""
    return _reference_check_detail(data, "source_alignment")


def check_anchor_coverage(data: dict, cfg: dict) -> tuple[float, dict]:
    """parsed 各 chunk 是否能在原文件中找到锚点。"""
    return _reference_check_detail(data, "anchor_coverage")


def check_numeric_consistency(data: dict, cfg: dict) -> tuple[float, dict]:
    """parsed 中的关键数字是否能在原文件中回溯到。"""
    return _reference_check_detail(data, "numeric_consistency")


def check_heading_consistency(data: dict, cfg: dict) -> tuple[float, dict]:
    """parsed 标题是否能在原文件中回溯到。"""
    return _reference_check_detail(data, "heading_consistency")


def check_hf_contamination(data: dict, cfg: dict) -> tuple[float, dict]:
    """正文中是否混入页码、页眉/页脚样板。"""
    units = data.get("_text_units", [])
    total_lines = 0
    full_line_hits = 0
    inline_hits = 0
    examples: list[str] = []

    for text in units:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            total_lines += 1
            matched_full_line = False
            for pat in _HF_PATTERNS:
                if pat.search(stripped):
                    full_line_hits += 1
                    if len(examples) < 8:
                        examples.append(f"[full-line] {repr(stripped[:80])}")
                    matched_full_line = True
                    break
            if matched_full_line:
                continue

            inline_examples = check_inline_header_noise(stripped)
            if inline_examples:
                inline_hits += len(inline_examples)
                if len(examples) < 8:
                    for sample in inline_examples[: 8 - len(examples)]:
                        examples.append(f"[inline] {sample}")

    if total_lines == 0:
        return 1.0, {"note": "无文本行可检查。"}

    total_hits = full_line_hits + inline_hits
    ratio = total_hits / total_lines
    score = max(0.0, 1.0 - ratio * 10)
    return score, {
        "contaminated_lines": total_hits,
        "full_line_hits": full_line_hits,
        "inline_hits": inline_hits,
        "total_lines": total_lines,
        "ratio": round(ratio, 4),
        "examples": examples,
    }


def check_toc_contamination(data: dict, cfg: dict) -> tuple[float, dict]:
    """正文中是否混入目录条目（带省略号 + 页码的 TOC 行）。"""
    units = data.get("_text_units", [])
    total_lines = 0
    full_line_hits = 0
    inline_hits = 0
    examples: list[str] = []

    for text in units:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            total_lines += 1
            matched_full_line = False
            for pat in _TOC_PATTERNS:
                if pat.search(stripped):
                    full_line_hits += 1
                    if len(examples) < 8:
                        examples.append(f"[full-line] {repr(stripped[:100])}")
                    matched_full_line = True
                    break
            if matched_full_line:
                continue

            inline_examples = check_inline_toc_contamination(stripped)
            if inline_examples:
                inline_hits += len(inline_examples)
                if len(examples) < 8:
                    for sample in inline_examples[: 8 - len(examples)]:
                        examples.append(f"[inline] {sample}")

    if total_lines == 0:
        return 1.0, {"note": "无文本行可检查。"}

    total_hits = full_line_hits + inline_hits
    ratio = total_hits / total_lines
    score = max(0.0, 1.0 - ratio * 20)
    return score, {
        "toc_lines": total_hits,
        "full_line_hits": full_line_hits,
        "inline_hits": inline_hits,
        "total_lines": total_lines,
        "ratio": round(ratio, 4),
        "examples": examples,
    }


def check_truncation(data: dict, cfg: dict) -> tuple[float, dict]:
    """Chunk 是否在句中被截断（跨页/跨段落切割）。"""
    units = data.get("_text_units", [])
    if not units:
        return 1.0, {"note": "无文本单元可检查。"}

    expected_overlap_truncation = 0
    broken_sentence_truncation = 0
    examples: list[str] = []

    for idx, text in enumerate(units):
        if not _looks_truncated(text):
            continue

        next_text = units[idx + 1] if idx + 1 < len(units) else ""
        overlap_words = _edge_overlap_words(text, next_text) if next_text else 0
        if (
            _looks_like_structural_block(text)
            or
            overlap_words >= 4
            or _looks_like_continuation_start(next_text)
            or _looks_like_boundary_start(next_text)
            or _looks_like_structural_block(next_text)
        ):
            expected_overlap_truncation += 1
            continue

        broken_sentence_truncation += 1
        tail = text.rstrip()[-100:]
        head = next_text.lstrip()[:60]
        preview = f"...{tail}"
        if head:
            preview += f" || next: {head}"
        if len(examples) < 6:
            examples.append(repr(preview))

    ratio = broken_sentence_truncation / len(units)
    score = max(0.0, 1.0 - ratio * 4)
    return score, {
        "expected_overlap_truncation": expected_overlap_truncation,
        "broken_sentence_truncation": broken_sentence_truncation,
        "total_chunks": len(units),
        "ratio": round(ratio, 4),
        "note": "已区分 chunk overlap 导致的预期截断与无法自然拼接的坏句截断。",
        "examples": examples,
    }


def check_duplication(data: dict, cfg: dict) -> tuple[float, dict]:
    """相邻 chunk 之间是否存在超出预期的重复。"""
    units = data.get("_text_units", [])
    if len(units) < 2:
        return 1.0, {"note": "文本单元不足 2 个，无法检查重复。"}

    HIGH = 0.45
    MED = 0.20
    high_pairs = 0
    med_pairs = 0
    examples: list[dict] = []

    for i in range(len(units) - 1):
        sim = _jaccard(units[i], units[i + 1])
        if sim >= HIGH:
            high_pairs += 1
            if len(examples) < 4:
                examples.append({
                    "chunk_indices": [i, i + 1],
                    "jaccard": round(sim, 3),
                    "preview_a": units[i][:100],
                    "preview_b": units[i + 1][:100],
                })
        elif sim >= MED:
            med_pairs += 1

    total_pairs = len(units) - 1
    high_ratio = high_pairs / total_pairs
    score = max(0.0, 1.0 - high_ratio * 5)

    return score, {
        "high_overlap_pairs": high_pairs,
        "med_overlap_pairs": med_pairs,
        "total_pairs": total_pairs,
        "high_ratio": round(high_ratio, 4),
        "examples": examples,
    }


def check_header_hierarchy(data: dict, cfg: dict) -> tuple[float, dict]:
    """Section 标题是否保留。"""
    sections = data.get("sections", [])
    if not sections:
        return 0.5, {"note": "未找到 sections 数组。"}

    with_header = sum(1 for s in sections if s.get("header", "").strip())
    ratio = with_header / len(sections)
    issues: list[str] = []
    if ratio < 0.5:
        issues.append(
            f"仅 {with_header}/{len(sections)} 个 section 具有非空标题。"
        )
    return ratio, {
        "sections_with_headers": with_header,
        "total_sections": len(sections),
        "ratio": round(ratio, 3),
        "issues": issues,
    }


def check_table_extraction(data: dict, cfg: dict) -> tuple[float, dict]:
    """财务类文档是否提取到结构化表格。"""
    if not cfg["expect_tables"]:
        return 1.0, {"note": "该文档类型不要求表格提取。"}

    quality = data.get("quality", {})
    warnings = quality.get("warnings", [])

    total_tables = quality.get("total_tables", 0) or quality.get("table_count", 0)
    if total_tables == 0:
        for sec in data.get("sections", []):
            total_tables += len(sec.get("tables", []))

    issues: list[str] = []
    score = 1.0

    if total_tables == 0:
        issues.append("未提取到结构化表格 — 财务报表可能缺乏表格结构")
        score = 0.3

    if any("no_structured_tables" in w for w in warnings):
        issues.append("quality.warnings 含 'no_structured_tables_extracted'")
        score = min(score, 0.5)

    return score, {
        "total_tables": total_tables,
        "quality_warnings": warnings,
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Check registry: (key, weight, function)
# ---------------------------------------------------------------------------

CHECKS: list[tuple[str, int, Any]] = [
    ("structure",            8, check_structure),
    ("key_items",           12, check_key_items),
    ("content_volume",      10, check_content_volume),
    ("source_alignment",    15, check_source_alignment),
    ("anchor_coverage",     10, check_anchor_coverage),
    ("numeric_consistency",  8, check_numeric_consistency),
    ("heading_consistency",  6, check_heading_consistency),
    ("hf_contamination",     10, check_hf_contamination),
    ("toc_contamination",     6, check_toc_contamination),
    ("truncation",            6, check_truncation),
    ("duplication",           5, check_duplication),
    ("header_hierarchy",      2, check_header_hierarchy),
    ("table_extraction",      2, check_table_extraction),
]

CHECK_LABELS = {
    "structure":            "必需字段完整性",
    "key_items":            "关键 Section/Item 覆盖率",
    "content_volume":       "正文总量 (词数)",
    "source_alignment":     "原文整体对齐",
    "anchor_coverage":      "原文锚点覆盖率",
    "numeric_consistency":  "关键数字一致性",
    "heading_consistency":  "标题回溯一致性",
    "hf_contamination":     "页眉/页脚污染",
    "toc_contamination":    "目录 (TOC) 污染",
    "truncation":           "残句截断",
    "duplication":          "Chunk 重复率",
    "header_hierarchy":     "标题层级保留",
    "table_extraction":     "表格提取质量",
}

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def validate_file(path: Path) -> dict:
    """校验单个 parsed.json，返回结构化结果。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "file": str(path),
            "file_name": path.name,
            "doc_type_raw": "",
            "doc_type": "unknown",
            "verdict": "FAIL",
            "total_score": 0.0,
            "error": str(exc),
            "checks": {},
        }

    raw_type, doc_type = _detect_doc_type(data)
    cfg = DOC_TYPE_CONFIG.get(doc_type, DOC_TYPE_CONFIG["default"])

    # 预先计算全部文本单元，供各检查项复用
    data["_text_units"] = _collect_text_units(data)
    data["_reference_analysis"] = compare_parsed_to_reference(data, cfg, path)

    check_results: dict[str, Any] = {}
    weighted_sum = 0.0
    total_weight = sum(w for _, w, _ in CHECKS)

    for key, weight, fn in CHECKS:
        try:
            score, detail = fn(data, cfg)
        except Exception as exc:
            score, detail = 0.0, {"error": str(exc)}

        clamped = max(0.0, min(1.0, float(score)))
        check_results[key] = {
            "score": round(clamped, 4),
            "weight": weight,
            "contribution": round(clamped * weight, 2),
            **detail,
        }
        weighted_sum += clamped * weight

    # 清理临时字段
    data.pop("_text_units", None)
    data.pop("_reference_analysis", None)

    final = round(weighted_sum / total_weight * 100, 1)

    if final >= 80:
        verdict = "PASS"
    elif final >= 50:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"

    return {
        "file": str(path),
        "file_name": path.name,
        "doc_type_raw": raw_type,
        "doc_type": doc_type,
        "verdict": verdict,
        "total_score": final,
        "checks": check_results,
    }


# ---------------------------------------------------------------------------
# Report rendering (中文)
# ---------------------------------------------------------------------------


def _bar(score_0_1: float, width: int = 18) -> str:
    n = round(score_0_1 * width)
    return "[" + "█" * n + "░" * (width - n) + "]"


_VERDICT_CN = {"PASS": "通过", "PARTIAL": "部分通过", "FAIL": "不通过"}


def render_report_md(results: list[dict], stamp: str) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    n = len(results)
    passes = sum(1 for r in results if r["verdict"] == "PASS")
    partials = sum(1 for r in results if r["verdict"] == "PARTIAL")
    fails = sum(1 for r in results if r["verdict"] == "FAIL")

    lines = [
        "# 解析结果质量校验报告",
        "",
        f"**批次:** `{stamp}`  ",
        f"**生成时间:** {now}  ",
        f"**校验文件数:** {n}",
        "",
        "---",
        "",
        "## 总体概览",
        "",
        "| 结论 | 数量 |",
        "|------|-----:|",
        f"| 通过 (PASS) | {passes} |",
        f"| 部分通过 (PARTIAL) | {partials} |",
        f"| 不通过 (FAIL) | {fails} |",
        "",
        "---",
        "",
        "## 逐文件详情",
        "",
    ]

    for res in sorted(results, key=lambda r: r["total_score"]):
        verdict = res["verdict"]
        verdict_cn = _VERDICT_CN.get(verdict, verdict)
        score = res["total_score"]
        fname = res["file_name"]
        dtype = res["doc_type"]
        raw = res.get("doc_type_raw", "")

        lines += [
            f"### `{fname}`",
            "",
            f"- **文档类型:** `{dtype}` (原始值: `{raw}`)",
            f"- **结论:** **{verdict_cn} ({verdict})**  &nbsp; 得分: **{score}/100**",
            "",
            "| 检查项 | 权重 | 得分 | 进度条 |",
            "|--------|------|-----:|--------|",
        ]

        for key, weight, _ in CHECKS:
            ch = res["checks"].get(key, {})
            s = ch.get("score", 0.0)
            label = CHECK_LABELS.get(key, key)
            lines.append(f"| {label} | {weight} | {s:.2f} | `{_bar(s)}` |")

        all_issues: list[str] = []
        for key, _, _ in CHECKS:
            ch = res["checks"].get(key, {})
            for iss in ch.get("issues", []):
                all_issues.append(f"- `[{key}]` {iss}")
            if ch.get("missing"):
                all_issues.append(
                    f"- `[key_items]` 缺失 Item: {ch['missing']}"
                )
            if ch.get("error"):
                all_issues.append(f"- `[{key}]` 错误: {ch['error']}")

        if all_issues:
            lines += ["", "**发现的问题:**", ""] + all_issues

        lines += ["", "---", ""]

    return "\n".join(lines)


def render_examples_md(results: list[dict]) -> str:
    lines = [
        "# 质量问题样本摘录",
        "",
        "以下为各检查项中检测到的问题样例，供人工快速确认。",
        "",
        "---",
        "",
    ]

    def _section(
        title: str, check_key: str, example_key: str = "examples"
    ) -> None:
        lines.extend([f"## {title}", ""])
        found_any = False
        for res in results:
            ch = res["checks"].get(check_key, {})
            exs = ch.get(example_key, [])
            if exs:
                found_any = True
                lines.append(
                    f"**`{res['file_name']}`** (得分 {ch.get('score', 0):.2f})"
                )
                for ex in exs[:4]:
                    if isinstance(ex, dict):
                        sim = ex.get("jaccard", 0)
                        idx = ex.get("chunk_indices", [])
                        lines.append(
                            f"  - Chunk {idx} · Jaccard 相似度: **{sim}**"
                        )
                        lines.append(
                            f"    - A: `{ex.get('preview_a', '')[:80]}...`"
                        )
                        lines.append(
                            f"    - B: `{ex.get('preview_b', '')[:80]}...`"
                        )
                    else:
                        lines.append(f"  - {ex}")
                lines.append("")
        if not found_any:
            lines.extend(["_该检查项未发现问题样本。_", ""])
        lines.extend(["---", ""])

    _section("原文整体对齐异常样本", "source_alignment")
    _section("原文锚点缺失样本", "anchor_coverage")
    _section("关键数字不一致样本", "numeric_consistency")
    _section("标题回溯异常样本", "heading_consistency")
    _section("页眉/页脚污染样本", "hf_contamination")
    _section("目录 (TOC) 污染样本", "toc_contamination")
    _section("残句截断样本", "truncation")
    _section("Chunk 重复样本", "duplication")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def find_latest_samples_dir() -> Path | None:
    if not EXTRACTED_DIR.exists():
        return None
    candidates = sorted(
        EXTRACTED_DIR.glob("_test_samples_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _cleanup_old_reports(reports_root: Path, keep: int = MAX_REPORT_RUNS) -> list[Path]:
    """只保留最近 keep 次报告，删除更早的目录。返回被删除的路径列表。"""
    import shutil

    if not reports_root.exists():
        return []

    # 按目录名排序（时间戳格式天然可比）
    dirs = sorted(
        [d for d in reports_root.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )
    to_remove = dirs[:-keep] if len(dirs) > keep else []
    for d in to_remove:
        shutil.rmtree(d)
    return to_remove


def write_reports(
    results: list[dict], stamp: str, out_root: Path | None = None
) -> Path:
    reports_root = out_root or REPORTS_DIR
    report_dir = reports_root / stamp
    report_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "run_stamp": stamp,
        "generated_at": datetime.now().isoformat(),
        "total_files": len(results),
        "pass": sum(1 for r in results if r["verdict"] == "PASS"),
        "partial": sum(1 for r in results if r["verdict"] == "PARTIAL"),
        "fail": sum(1 for r in results if r["verdict"] == "FAIL"),
        "results": results,
    }

    (report_dir / "report.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (report_dir / "report.md").write_text(
        render_report_md(results, stamp), encoding="utf-8"
    )
    (report_dir / "examples.md").write_text(
        render_examples_md(results), encoding="utf-8"
    )

    # 清理旧报告，只保留最近 N 次
    removed = _cleanup_old_reports(reports_root)
    if removed:
        names = [d.name for d in removed]
        print(f"  已清理 {len(removed)} 个旧报告: {', '.join(names)}")

    return report_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="解析结果质量校验脚本 (QC Validator)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--file", "-f",
        type=Path,
        metavar="PATH",
        help="验证单个 parsed.json 文件",
    )
    group.add_argument(
        "--batch", "-b",
        action="store_true",
        help="自动检测最新 _test_samples_* 文件夹并批量验证",
    )
    group.add_argument(
        "--samples-dir", "-s",
        type=Path,
        metavar="DIR",
        help="验证指定目录下的所有 *.parsed.json 文件",
    )
    parser.add_argument(
        "--out", "-o",
        type=Path,
        metavar="DIR",
        default=None,
        help="报告输出根目录 (默认: File/extracted/validation_reports/)",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="仅在终端输出结果，不写入报告文件",
    )

    args = parser.parse_args()

    # --- 收集待验证文件 ---
    files: list[Path] = []

    if args.file:
        p = args.file
        if not p.exists():
            print(f"ERROR: 文件不存在: {p}", file=sys.stderr)
            sys.exit(1)
        files = [p]

    else:
        samples_dir = (
            args.samples_dir if args.samples_dir else find_latest_samples_dir()
        )
        if not samples_dir or not samples_dir.exists():
            print(
                f"ERROR: 找不到 _test_samples_* 目录: {EXTRACTED_DIR}",
                file=sys.stderr,
            )
            sys.exit(1)
        files = sorted(samples_dir.glob("*.parsed.json"))
        if not files:
            print(
                f"ERROR: 目录下无 *.parsed.json 文件: {samples_dir}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"扫描目录: {samples_dir}  ({len(files)} 个文件)")

    # --- 执行校验 ---
    all_results: list[dict] = []
    for fp in files:
        print(f"  {fp.name:<50s}", end=" ", flush=True)
        result = validate_file(fp)
        all_results.append(result)
        v_cn = _VERDICT_CN.get(result["verdict"], result["verdict"])
        print(f"{v_cn:6s}  {result['total_score']:5.1f}/100")

    # --- 写入报告 ---
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if not args.no_report:
        report_dir = write_reports(all_results, stamp, out_root=args.out)
        print(f"\n报告已输出至: {report_dir}")
        print("  report.json · report.md · examples.md")

    # --- 终端汇总 ---
    print("\n" + "=" * 60)
    print("校验汇总")
    print("=" * 60)
    for res in sorted(all_results, key=lambda r: r["total_score"]):
        v_cn = _VERDICT_CN.get(res["verdict"], res["verdict"])
        print(f"  {v_cn:8s}  {res['total_score']:5.1f}/100  {res['file_name']}")

    passes = sum(1 for r in all_results if r["verdict"] == "PASS")
    partials = sum(1 for r in all_results if r["verdict"] == "PARTIAL")
    fails = sum(1 for r in all_results if r["verdict"] == "FAIL")

    parts: list[str] = []
    if passes:
        parts.append(f"{passes} 个通过")
    if partials:
        parts.append(f"{partials} 个部分通过")
    if fails:
        parts.append(f"{fails} 个不通过")
    print(f"\n共 {len(all_results)} 个文件: {'、'.join(parts)}。")

    if fails:
        print("存在不通过的文件，请查看报告了解详情。")
        sys.exit(1)


if __name__ == "__main__":
    main()
