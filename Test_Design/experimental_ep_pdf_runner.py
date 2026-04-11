"""
experimental_ep_pdf_runner.py
────────────────────────────────────────────────────────────────────────────────
直接运行此文件即可处理两个固定的 Flex Earnings Presentation PDF。

运行方式：
    python Test_Design/experimental_ep_pdf_runner.py

输出位置：
    Test_Design/File/EP_Extracted_YYYYMMDD_HHMMSS/
        ep_fy23q3_final.json
        ep_fy24q2_final.json
        run_log.json

每次运行会自动删除上一次的 EP_Extracted_* 文件夹，新建带时间戳的新文件夹。

新特性：
  · 视觉模式（USE_VISION=True）：PDF 每页转图片 + 文字同时发给模型，
    解决图片页内容缺失和 Bridge 表格结构混淆的问题
  · 自动分批：PDF 超过 MAX_PAGES_PER_BATCH 页时自动分批调用，支持 10-K 等长文档
  · doc_type 参数：根据文档类型动态调整 system prompt
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

# ── 第三方依赖 ──────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
except ImportError:
    raise ImportError("请先安装依赖：pip install pypdf anthropic pydantic python-dotenv")

try:
    from pypdf import PdfReader
except ImportError:
    raise ImportError("请先安装 pypdf：pip install pypdf")

try:
    import anthropic
except ImportError:
    raise ImportError("请先安装 anthropic：pip install anthropic")

try:
    from pydantic import BaseModel, ValidationError, field_validator
except ImportError:
    raise ImportError("请先安装 pydantic：pip install pydantic")

# pymupdf 是视觉模式的可选依赖
try:
    import fitz  # pymupdf
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# beautifulsoup4 是 HTML 提取的可选依赖
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


# ────────────────────────────────────────────────────────────────────────────────
# 配置（改这里）
# ────────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
ENV_FILE     = PROJECT_ROOT / "backend" / ".env"

# 两个固定 PDF 及其文档类型
FIXED_PDFS: list[tuple[Path, str]] = [
    (PROJECT_ROOT / "Test_Design/File/Flex/Earnings Presentation/EP_FY23Q3_FINAL.pdf", "ep"),
    (PROJECT_ROOT / "Test_Design/File/Flex/Earnings Presentation/ep_fy24q2_final.pdf", "ep"),
]

# 两个固定 Press Release PDF 测试文件（硬编码，不会扫描目录，防止误处理其他文件）
FIXED_PR_FILES: list[tuple[Path, str]] = [
    (PROJECT_ROOT / "Test_Design/File/Flex/Press Releases/FLEX_FY22Q3_Press-Release.pdf", "press_release"),
    (PROJECT_ROOT / "Test_Design/File/Flex/Press Releases/03.-PR_Earnings_FY22Q4_22-05-04-9am.pdf", "press_release"),
]

# 8-K HTML 文件（规则引擎提取，不调用 LLM）
# 2022-02-02: Nextracker/TPG 投资交割（Item 8.01，5800+ chars 实质内容）
# 2022-01-27: Patrick Ward 加入董事会（Item 5.02，3100+ chars）
FIXED_8K_HTML_FILES: list[Path] = [
    PROJECT_ROOT / "Test_Design/File/Flex/flex_8k_press_releases/Flex_8-K_2022-02-02.html",
    PROJECT_ROOT / "Test_Design/File/Flex/flex_8k_press_releases/Flex_8-K_2022-01-27.html",
]

# 输出根目录
OUTPUT_ROOT = SCRIPT_DIR / "File"

# 模型：claude-sonnet-4-20250514 原生支持视觉输入
MODEL      = "claude-sonnet-4-6"
MAX_TOKENS = 16000

# 视觉模式开关（需要 pip install pymupdf）
USE_VISION = True

# 超过此页数自动分批（每批单独调用 API，最后合并 chunks）
MAX_PAGES_PER_BATCH = 25

# 图片渲染分辨率倍数（1.5 = 1.5x；Anthropic 单图上限 5MB，过大会自动降采样）
IMAGE_SCALE = 1.5


# ────────────────────────────────────────────────────────────────────────────────
# 数据结构（pydantic schema）
# ────────────────────────────────────────────────────────────────────────────────

ChunkType = Literal[
    "overview",
    "disclosure",
    "summary",
    "business_update",
    "financials",
    "segment",
    "cash_flow",
    "outlook",
    "guidance",
    "guidance_bridge",
    "strategy",
    "appendix_table",
]


class ChunkMetadata(BaseModel):
    source_file: str
    document_type: str
    company: str
    period: str
    chunk_id: str
    section_title: str
    page_range: list[int]
    chunk_type: ChunkType

    @field_validator("page_range")
    @classmethod
    def page_range_must_have_two_elements(cls, v):
        if len(v) != 2:
            raise ValueError("page_range 必须是 [start, end] 两个整数")
        return v


class Chunk(BaseModel):
    chunk_id: str
    section_title: str
    page_range: list[int]
    chunk_type: ChunkType
    content: str
    metadata: ChunkMetadata

    @field_validator("page_range")
    @classmethod
    def page_range_must_have_two_elements(cls, v):
        if len(v) != 2:
            raise ValueError("page_range 必须是 [start, end] 两个整数")
        return v

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError("content 不能为空")
        return v


class ChunkDocument(BaseModel):
    source_file: str
    output_mode: str
    document_type: str
    company: str
    period: str
    quarter_end: str | None = None
    earnings_announcement: str | None = None
    chunks: list[Chunk]

    @field_validator("chunks")
    @classmethod
    def chunks_must_not_be_empty(cls, v):
        if len(v) == 0:
            raise ValueError("chunks 列表不能为空")
        return v


# ────────────────────────────────────────────────────────────────────────────────
# Prompt（根据 doc_type 动态生成）
# ────────────────────────────────────────────────────────────────────────────────

_DOC_TYPE_HINTS: dict[str, str] = {
    "ep": (
        "This is an Earnings Presentation (quarterly investor deck). "
        "Key sections: title/overview, forward-looking disclaimers, executive summary, "
        "business update, key financials, segment performance, cash flow, segment outlook, "
        "guidance (quarterly and full-year), guidance bridge, strategy/key takeaways, "
        "and appendix GAAP-to-Non-GAAP reconciliation tables."
    ),
    "10k": (
        "This is an Annual Report (Form 10-K). "
        "Key sections: business overview, risk factors, properties, legal proceedings, "
        "MD&A (management discussion and analysis), quantitative market risk disclosures, "
        "financial statements, notes to financial statements, and exhibits."
    ),
    "10q": (
        "This is a Quarterly Report (Form 10-Q). "
        "Key sections: financial statements, notes to financial statements, "
        "MD&A, quantitative market risk disclosures, and legal proceedings."
    ),
    "press_release": (
        "This is an Earnings Press Release PDF. "
        "Extract ONLY financially meaningful content: headline results, segment results, "
        "guidance, and GAAP-to-Non-GAAP reconciliation tables. "
        "SKIP boilerplate sections entirely — do NOT create chunks for: "
        "forward-looking statement disclaimers, Safe Harbor language, legal notices, "
        "about-the-company boilerplate, investor contact info, or signature blocks. "
        "These add no analytical value and waste tokens."
    ),
    "8k": (
        "This is an SEC Form 8-K Current Report (press release or material event filing). "
        "Key sections: headline announcement, financial highlights, segment results, "
        "guidance, and GAAP-to-Non-GAAP reconciliation tables. "
        "There are no page numbers — treat the entire document as a continuous flow."
    ),
}

_BASE_SYSTEM_PROMPT = """\
You are a financial document extraction specialist.

Your task:
  Given the pages of a financial document (text and/or images), extract ALL content
  into structured chunks suitable for embedding and RAG (retrieval-augmented generation) search.

Extraction rules:
  1. Every piece of content must be captured — nothing skipped, including all appendix tables.
  2. Each chunk must be semantically self-contained: a reader should understand it without
     needing to read other chunks.
  3. Guidance numbers and their footnotes belong in the SAME chunk — do not split them.
  4. Appendix reconciliation tables must preserve ALL numbers exactly as they appear.
  5. For image-only slides (charts, diagrams), describe the key data points visible in the image.
  6. chunk_id format: {period_snake_case}_{two_digit_seq}_{short_name}
     Example: "fy23q3_01_overview", "fy23q3_14_appendix_operating_income"
  7. chunk_type must be one of:
       overview | disclosure | summary | business_update | financials |
       segment | cash_flow | outlook | guidance | guidance_bridge |
       strategy | appendix_table
  8. Section title divider slides (e.g. "Business update / Revathi Advaithi") should be merged
     with the following content slide, not treated as standalone chunks.

Output format:
  Respond with ONLY valid JSON. No markdown code fences, no explanation text before or after.

JSON schema:
{
  "source_file": "<original PDF filename, no path>",
  "output_mode": "chunk_ready_high_fidelity",
  "document_type": "<document type>",
  "company": "<company name>",
  "period": "<e.g. Q3 Fiscal 2023>",
  "quarter_end": "<YYYY-MM-DD or null if not applicable>",
  "earnings_announcement": "<YYYY-MM-DD or null if not applicable>",
  "chunks": [
    {
      "chunk_id": "<string>",
      "section_title": "<string>",
      "page_range": [<start_page_int>, <end_page_int>],
      "chunk_type": "<ChunkType>",
      "content": "<full narrative content, all numbers preserved>",
      "metadata": {
        "source_file": "<same as top-level source_file>",
        "document_type": "<same as top-level document_type>",
        "company": "<same as top-level company>",
        "period": "<same as top-level period>",
        "chunk_id": "<same as chunk_id above>",
        "section_title": "<same as section_title above>",
        "page_range": [<start_page_int>, <end_page_int>],
        "chunk_type": "<same as chunk_type above>"
      }
    }
  ]
}"""


def build_system_prompt(doc_type: str = "ep") -> str:
    hint = _DOC_TYPE_HINTS.get(doc_type, "This is a financial document.")
    return _BASE_SYSTEM_PROMPT + f"\n\nDocument type context: {hint}"


# ────────────────────────────────────────────────────────────────────────────────
# PDF 提取：文字 + 图片
# ────────────────────────────────────────────────────────────────────────────────

def extract_text_pages(pdf_path: Path) -> list[dict]:
    """逐页提取文字，返回 [{"page": 1, "text": "..."}, ...]，跳过空页。"""
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append({"page": i + 1, "text": text})
    return pages


def extract_image_pages(pdf_path: Path, scale: float = IMAGE_SCALE) -> list[dict]:
    """
    用 pymupdf 把每页 PDF 渲染成 PNG 图片（base64 编码）。
    返回 [{"page": 1, "base64": "...", "media_type": "image/png"}, ...]（包含所有页）。
    需要 pip install pymupdf。
    """
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError(
            "视觉模式需要 pymupdf，请安装：pip install pymupdf\n"
            "或将 USE_VISION 设为 False 改用纯文字模式。"
        )
    _MAX_IMAGE_BYTES = 4_800_000  # Anthropic 单图上限 5MB，留 200KB 余量

    doc = fitz.open(str(pdf_path))
    results = []
    for i, page in enumerate(doc):
        s = scale
        while True:
            mat = fitz.Matrix(s, s)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            if len(img_bytes) <= _MAX_IMAGE_BYTES or s <= 0.5:
                break
            s = round(s * 0.75, 2)  # 每次缩小 25%，直到满足大小限制
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        results.append({"page": i + 1, "base64": b64, "media_type": "image/png"})
    doc.close()
    return results


def build_multimodal_content(
    pages_text: list[dict],
    pages_img: list[dict],
) -> list:
    """
    把图片和文字组合成 Anthropic Messages API 的多模态 content 列表。
    每页：先放图片，再放对应的文字（如果有）。
    图片覆盖所有页（包括纯图片页），文字只有能提取到内容的页才有。
    """
    text_by_page = {p["page"]: p["text"] for p in pages_text}
    content = []
    for img in pages_img:
        page_num = img["page"]
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["media_type"],
                "data": img["base64"],
            },
        })
        page_text = text_by_page.get(page_num, "")
        label = f"=== PAGE {page_num} ===\n{page_text}" if page_text else f"=== PAGE {page_num} === [image-only]"
        content.append({"type": "text", "text": label})
    return content


def build_text_content(pages_text: list[dict]) -> str:
    """纯文字模式：把所有页拼成一条消息。"""
    return "\n\n".join(f"=== PAGE {p['page']} ===\n{p['text']}" for p in pages_text)


# ────────────────────────────────────────────────────────────────────────────────
# HTML 提取（8-K / 10-K / 10-Q）
# ────────────────────────────────────────────────────────────────────────────────

def extract_html_text(html_path: Path) -> str:
    """
    用 BeautifulSoup 从 HTML（包括 SEC inline XBRL 格式）提取纯文字。
    需要 pip install beautifulsoup4 lxml
    返回：去除标签后的文本字符串（整个文档视为一个"页面"）。
    """
    if not BS4_AVAILABLE:
        raise RuntimeError(
            "HTML 提取需要 beautifulsoup4，请安装：pip install beautifulsoup4 lxml\n"
        )
    raw = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml")

    # 移除 script / style / ix:header（XBRL 隐藏元数据）
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(True, {"style": lambda s: s and "display:none" in s.replace(" ", "")}):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    # 合并连续空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ────────────────────────────────────────────────────────────────────────────────
# 8-K HTML 规则引擎（无需 LLM）
# ────────────────────────────────────────────────────────────────────────────────

# Item code → chunk_type 映射（SEC 8-K 各 Item 的业务含义）
_8K_ITEM_TO_CHUNK_TYPE: dict[str, str] = {
    "2.02": "summary",          # Results of Operations and Financial Condition
    "7.01": "disclosure",       # Regulation FD Disclosure
    "8.01": "business_update",  # Other Events
    "5.02": "business_update",  # Departure/Appointment of Directors or Officers
    "5.03": "business_update",  # Amendments to Charter
    "1.01": "business_update",  # Entry into a Material Definitive Agreement
    "1.02": "business_update",  # Termination of a Material Definitive Agreement
}
_8K_SKIP_ITEMS = {"9.01", "sig"}   # Exhibits index & Signatures — 无嵌入价值
_8K_MIN_CHARS   = 80               # 少于此字数的 section 不生成 chunk

_8K_ITEM_RE    = re.compile(r"^\s*item\s+(\d{1,2}\.\d{2})\b[\s\.:;-]*(.*)$", re.IGNORECASE)
_8K_SIG_RE     = re.compile(r"^\s*signatures?\s*$", re.IGNORECASE)
_8K_PAGE_RE    = re.compile(r"^\s*\d{1,3}\s*$")
_8K_DATE_RE    = re.compile(
    r"([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"
)
_8K_COMPANY_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&'.,-]*(?:\s+[A-Z][A-Za-z0-9&'.,-]*){0,5}"
    r"\s+(?:Ltd\.?|Inc\.?|Corporation|Corp\.?|PLC|LLC|Limited))\b"
)
_8K_LEGAL_RE = [
    re.compile(r"shall\s+not\s+be\s+deemed\s+[\"']?filed[\"']?", re.IGNORECASE),
    re.compile(r"incorporated\s+by\s+reference", re.IGNORECASE),
]


def _8k_parse_html(html_path: Path) -> str:
    """
    解析 SEC inline XBRL HTML。
    · ix:nonFraction / ix:nonNumeric → unwrap（保留数字文字）
    · ix:header / ix:hidden → decompose（纯 XBRL 元数据，无阅读价值）
    """
    if not BS4_AVAILABLE:
        raise RuntimeError("需要 beautifulsoup4：pip install beautifulsoup4")
    raw = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    for tag in soup.find_all(True):
        name = (tag.name or "").lower()
        if name in {"ix:header", "ix:hidden"}:
            tag.decompose()
            continue
        if name.startswith("ix:"):
            try:
                tag.unwrap()
            except Exception:
                pass
    root = soup.find("body") or soup
    text = root.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _8k_extract_cover(lines: list[str]) -> dict:
    """从封面行提取公司名和报告日期。"""
    company, date_str = "", ""
    for i, line in enumerate(lines[:80]):
        low = line.lower()
        if "date of report" in low:
            m = _8K_DATE_RE.search(line)
            if not m and i + 1 < len(lines):
                m = _8K_DATE_RE.search(lines[i + 1])
            if m:
                date_str = m.group(1)
        if "exact name of registrant" in low:
            for cand in [lines[i - 1] if i > 0 else "", lines[i + 1] if i + 1 < len(lines) else ""]:
                cand = cand.strip()
                if cand and "exact name" not in cand.lower() and not _8K_PAGE_RE.match(cand):
                    company = cand
                    break
    if not company:
        blob = "\n".join(lines[:200])
        for m in _8K_COMPANY_RE.finditer(blob):
            c = m.group(1).strip()
            if not re.search(r"\d", c) and len(c) < 60:
                company = c
                break
    return {"company": company, "date_of_report": date_str}


def _8k_build_sections(lines: list[str]) -> list[dict]:
    """按 Item X.XX / SIGNATURES 切分正文，过滤法律样板和页码行。"""
    headings = []
    for i, line in enumerate(lines):
        m = _8K_ITEM_RE.match(line)
        if m:
            code, rest = m.group(1), m.group(2).strip()
            body_start = i + 1
            if not rest and i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt and len(nxt) < 120 and not _8K_ITEM_RE.match(nxt):
                    rest, body_start = nxt, i + 2
            headings.append({
                "start": i, "body_start": body_start,
                "header": f"Item {code}" + (f"  {rest}" if rest else ""),
                "item_code": code,
            })
        elif _8K_SIG_RE.match(line):
            headings.append({"start": i, "body_start": i + 1, "header": "SIGNATURES", "item_code": "sig"})

    sections = []
    for idx, hd in enumerate(headings):
        end = headings[idx + 1]["start"] if idx + 1 < len(headings) else len(lines)
        kept = [
            ln for ln in lines[hd["body_start"]: end]
            if not _8K_PAGE_RE.match(ln) and not any(p.search(ln) for p in _8K_LEGAL_RE)
        ]
        content = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
        sections.append({
            "item_code": hd["item_code"],
            "header": hd["header"],
            "content": content,
            "is_skip": hd["item_code"] in _8K_SKIP_ITEMS,
        })
    return sections


def _8k_date_to_prefix(date_str: str) -> str:
    """把 'January 26, 2022' / '2022-01-26' 转成 '20220126'。"""
    for fmt in ("%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y%m%d")
        except Exception:
            continue
    return re.sub(r"\D", "", date_str)[:8].ljust(8, "0")


def _8k_to_chunk_document(html_path: Path, sections: list[dict], cover: dict) -> ChunkDocument:
    """把规则引擎的 sections 直接映射成 ChunkDocument（无 LLM）。"""
    source_file = html_path.name
    company     = cover.get("company") or "Unknown"
    date_str    = cover.get("date_of_report") or re.sub(r"[_\-]", " ", html_path.stem)
    date_prefix = _8k_date_to_prefix(date_str)

    chunks: list[Chunk] = []
    seq = 1
    for s in sections:
        if s["is_skip"] or len(s["content"].strip()) < _8K_MIN_CHARS:
            continue
        item_code  = s["item_code"]
        chunk_type: ChunkType = _8K_ITEM_TO_CHUNK_TYPE.get(item_code, "business_update")
        short_name = re.sub(r"\W+", "_", item_code)
        chunk_id   = f"{date_prefix}_{seq:02d}_item_{short_name}"
        meta = ChunkMetadata(
            source_file=source_file, document_type="8-K",
            company=company, period=date_str,
            chunk_id=chunk_id, section_title=s["header"],
            page_range=[1, 1], chunk_type=chunk_type,
        )
        chunks.append(Chunk(
            chunk_id=chunk_id, section_title=s["header"],
            page_range=[1, 1], chunk_type=chunk_type,
            content=s["content"], metadata=meta,
        ))
        seq += 1

    # 如果没有任何有内容的 section（全是封面/附件），生成一个占位 chunk
    if not chunks:
        fallback = "\n\n".join(
            s["content"] for s in sections if not s["is_skip"] and s["content"].strip()
        ).strip() or "(No extractable body content — this 8-K references attached exhibits only)"
        meta = ChunkMetadata(
            source_file=source_file, document_type="8-K",
            company=company, period=date_str,
            chunk_id=f"{date_prefix}_01_full", section_title="Full Document",
            page_range=[1, 1], chunk_type="summary",
        )
        chunks = [Chunk(
            chunk_id=f"{date_prefix}_01_full", section_title="Full Document",
            page_range=[1, 1], chunk_type="summary",
            content=fallback, metadata=meta,
        )]

    return ChunkDocument(
        source_file=source_file,
        output_mode="chunk_ready_rule_based",
        document_type="8-K",
        company=company,
        period=date_str,
        chunks=chunks,
    )


def process_one_8k_html(html_path: Path, output_dir: Path) -> dict:
    """规则引擎处理单个 8-K HTML 文件，不调用 LLM。"""
    source_file  = html_path.name
    output_path  = output_dir / f"{html_path.stem.lower()}.json"
    started_at   = now_iso()
    started_perf = time.perf_counter()

    print(f"\n{'─' * 60}")
    print(f"处理：{source_file}  [规则引擎 / 8-K HTML / 无 LLM]")
    print(f"{'─' * 60}")

    try:
        print("[1/2] 解析 HTML + 切分 Item...")
        text  = _8k_parse_html(html_path)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # 封面在第一个 Item 之前
        first_item_idx = next(
            (i for i, ln in enumerate(lines) if _8K_ITEM_RE.match(ln)), len(lines)
        )
        cover    = _8k_extract_cover(lines[:first_item_idx])
        sections = _8k_build_sections(lines[first_item_idx:])

        useful = sum(1 for s in sections if not s["is_skip"] and len(s["content"]) >= _8K_MIN_CHARS)
        print(f"      公司：{cover.get('company') or '(未识别)'}  "
              f"日期：{cover.get('date_of_report') or '(未识别)'}")
        print(f"      共 {len(sections)} 个 Item，有效内容：{useful} 个")

        print("[2/2] 构建 ChunkDocument...")
        doc = _8k_to_chunk_document(html_path, sections, cover)

        output_path.write_text(
            doc.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
        )
        print(f"      已保存：{output_path.name}，共 {len(doc.chunks)} 个 chunks")
        for c in doc.chunks:
            print(f"        [{c.chunk_id}]  {c.section_title}")

        elapsed = round(time.perf_counter() - started_perf, 2)
        return {
            "source_file":      source_file,
            "status":           "success",
            "started_at":       started_at,
            "finished_at":      now_iso(),
            "duration_seconds": elapsed,
            "mode":             "rule_based",
            "batched":          False,
            "input_tokens":     0,
            "output_tokens":    0,
            "cost_usd":         0.0,
            "chunks_count":     len(doc.chunks),
            "output_file":      output_path.name,
        }

    except Exception as exc:
        elapsed = round(time.perf_counter() - started_perf, 2)
        print(f"      [错误] {exc}")
        return {
            "source_file":      source_file,
            "status":           "failed",
            "started_at":       started_at,
            "finished_at":      now_iso(),
            "duration_seconds": elapsed,
            "error":            str(exc),
            "output_file":      None,
        }


# ────────────────────────────────────────────────────────────────────────────────
# 费用计算
# ────────────────────────────────────────────────────────────────────────────────

def calc_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """claude-sonnet-4: $3/M input, $15/M output"""
    return round(input_tokens / 1_000_000 * 3 + output_tokens / 1_000_000 * 15, 6)


# ────────────────────────────────────────────────────────────────────────────────
# Anthropic API 调用（单批）
# ────────────────────────────────────────────────────────────────────────────────

def call_anthropic_single(
    pages_text: list[dict],
    pages_img: list[dict] | None,
    api_key: str,
    output_dir: Path,
    doc_type: str = "ep",
    batch_label: str = "",
) -> tuple[dict, int, int, float]:
    """
    调用 Anthropic API 处理单批页面。
    pages_img=None 时为纯文字模式；有值时为视觉模式（图片+文字）。
    返回：(parsed_dict, input_tokens, output_tokens, cost_usd)
    """
    client = anthropic.Anthropic(api_key=api_key)
    system = build_system_prompt(doc_type)

    if pages_img is not None:
        user_content = build_multimodal_content(pages_text, pages_img)
    else:
        user_content = build_text_content(pages_text)

    if batch_label:
        # 分批模式：告知模型当前是哪一批，避免它重复输出完整文档头
        if isinstance(user_content, list):
            user_content.append({
                "type": "text",
                "text": f"\n\n[Batch note: {batch_label}. Return complete JSON including all top-level fields.]",
            })
        else:
            user_content += f"\n\n[Batch note: {batch_label}. Return complete JSON including all top-level fields.]"

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )

    input_tokens  = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    cost_usd      = calc_cost_usd(input_tokens, output_tokens)

    raw_text = message.content[0].text
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
    raw_text = re.sub(r"\s*```$", "", raw_text.strip())

    try:
        return json.loads(raw_text), input_tokens, output_tokens, cost_usd
    except json.JSONDecodeError as e:
        debug_path = output_dir / f"_debug_raw_{batch_label or 'response'}.txt"
        debug_path.write_text(raw_text, encoding="utf-8")
        raise ValueError(
            f"LLM 返回的内容不是合法 JSON（output_tokens={output_tokens}，上限={MAX_TOKENS}），"
            f"已保存到 {debug_path.name}\n错误详情：{e}"
        )


# ────────────────────────────────────────────────────────────────────────────────
# Anthropic API 调用（分批合并）
# ────────────────────────────────────────────────────────────────────────────────

def _split_into_batches(
    pages_text: list[dict],
    pages_img: list[dict] | None,
    batch_size: int,
) -> list[tuple[list[dict], list[dict] | None]]:
    """把 pages_text 和 pages_img 按 batch_size 分组。"""
    n = len(pages_img) if pages_img else len(pages_text)
    batches = []
    for start in range(0, n, batch_size):
        end = start + batch_size
        txt_batch = [p for p in pages_text if start < p["page"] <= end] if pages_img else pages_text[start:end]
        img_batch = pages_img[start:end] if pages_img else None
        if txt_batch or img_batch:
            batches.append((txt_batch, img_batch))
    return batches


def call_anthropic_batched(
    pages_text: list[dict],
    pages_img: list[dict] | None,
    api_key: str,
    output_dir: Path,
    doc_type: str = "ep",
) -> tuple[dict, int, int, float]:
    """
    分批调用 API，每批 MAX_PAGES_PER_BATCH 页，最后合并所有 chunks。
    top-level metadata（公司、期间等）取自第一批的结果。
    返回：(merged_dict, total_input_tokens, total_output_tokens, total_cost_usd)
    """
    batches = _split_into_batches(pages_text, pages_img, MAX_PAGES_PER_BATCH)
    total_pages = len(pages_img) if pages_img else len(pages_text)
    print(f"      共 {total_pages} 页，分 {len(batches)} 批处理（每批最多 {MAX_PAGES_PER_BATCH} 页）")

    all_chunks: list = []
    meta: dict = {}
    total_input = 0
    total_output = 0
    total_cost = 0.0

    for i, (txt_batch, img_batch) in enumerate(batches):
        page_start = txt_batch[0]["page"] if txt_batch else (img_batch[0]["page"] if img_batch else "?")
        page_end   = txt_batch[-1]["page"] if txt_batch else (img_batch[-1]["page"] if img_batch else "?")
        label = f"batch {i + 1}/{len(batches)}, pages {page_start}-{page_end}"
        print(f"      → {label} ...")

        result, inp, out, cost = call_anthropic_single(
            txt_batch, img_batch, api_key, output_dir, doc_type, batch_label=label
        )

        total_input  += inp
        total_output += out
        total_cost   += cost

        if i == 0:
            meta = {k: v for k, v in result.items() if k != "chunks"}
        all_chunks.extend(result.get("chunks", []))

        print(f"        input={inp} / output={out} / cost=${cost:.4f} / chunks={len(result.get('chunks', []))}")

    meta["chunks"] = all_chunks
    return meta, total_input, total_output, round(total_cost, 6)


# ────────────────────────────────────────────────────────────────────────────────
# pydantic 校验
# ────────────────────────────────────────────────────────────────────────────────

def validate_schema(data: dict) -> ChunkDocument:
    return ChunkDocument(**data)


# ────────────────────────────────────────────────────────────────────────────────
# 目录管理
# ────────────────────────────────────────────────────────────────────────────────

def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def clean_previous_extractions() -> None:
    for entry in OUTPUT_ROOT.iterdir():
        if entry.is_dir() and entry.name.startswith("EP_Extracted_"):
            shutil.rmtree(entry)
            print(f"[清理] 已删除旧文件夹：{entry.name}")


def create_output_dir() -> Path:
    output_dir = OUTPUT_ROOT / f"EP_Extracted_{now_stamp()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# ────────────────────────────────────────────────────────────────────────────────
# 单个 PDF 处理
# ────────────────────────────────────────────────────────────────────────────────

def process_one_pdf(
    pdf_path: Path,
    api_key: str,
    output_dir: Path,
    doc_type: str = "ep",
) -> dict:
    source_file  = pdf_path.name
    output_path  = output_dir / f"{pdf_path.stem.lower()}.json"
    started_at   = now_iso()
    started_perf = time.perf_counter()

    print(f"\n{'─' * 60}")
    print(f"处理：{source_file}  [doc_type={doc_type}]")
    print(f"{'─' * 60}")

    try:
        # Step 1: 提取文字
        print("[1/3] 提取 PDF 文字...")
        pages_text = extract_text_pages(pdf_path)
        total_text_pages = len(pages_text)
        print(f"      共提取 {total_text_pages} 页有效文字")

        # Step 1b: 提取图片（视觉模式）
        pages_img: list[dict] | None = None
        if USE_VISION and PYMUPDF_AVAILABLE:
            print("[1b]  渲染 PDF 页面为图片（视觉模式）...")
            pages_img = extract_image_pages(pdf_path)
            total_pages = len(pages_img)
            print(f"      共渲染 {total_pages} 页（含纯图片页）")
        elif USE_VISION and not PYMUPDF_AVAILABLE:
            print("[1b]  [警告] USE_VISION=True 但 pymupdf 未安装，回退到纯文字模式")
        else:
            total_pages = total_text_pages

        # 决定是否需要分批
        n_pages = len(pages_img) if pages_img else total_text_pages
        need_batch = n_pages > MAX_PAGES_PER_BATCH

        # Step 2: 调用 LLM
        mode_label = "视觉+文字" if pages_img else "纯文字"
        batch_label = "分批" if need_batch else "单批"
        print(f"[2/3] 调用 Anthropic API（{mode_label} / {batch_label} / 模型：{MODEL}）...")

        if need_batch:
            raw_data, input_tokens, output_tokens, cost_usd = call_anthropic_batched(
                pages_text, pages_img, api_key, output_dir, doc_type
            )
        else:
            raw_data, input_tokens, output_tokens, cost_usd = call_anthropic_single(
                pages_text, pages_img, api_key, output_dir, doc_type
            )

        n_chunks = len(raw_data.get("chunks", []))
        print(f"      API 完成，返回 {n_chunks} 个原始 chunks")
        print(f"      input={input_tokens} / output={output_tokens} / 上限={MAX_TOKENS} / 费用=${cost_usd:.4f}")

        # Step 3: pydantic 校验
        print("[3/3] 校验数据结构（pydantic）...")
        try:
            doc = validate_schema(raw_data)
        except ValidationError as e:
            raw_debug_path = output_path.with_suffix(".raw.json")
            raw_debug_path.write_text(
                json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"      [警告] Schema 校验失败，原始数据已保存到：{raw_debug_path.name}")
            raise

        print(f"      校验通过，共 {len(doc.chunks)} 个 chunks")

        # 写入输出文件
        output_path.write_text(
            doc.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
        )
        print(f"      已保存：{output_path.name}")
        for c in doc.chunks:
            print(f"        [{c.chunk_id}]  {c.section_title}  (pages {c.page_range})")

        elapsed = round(time.perf_counter() - started_perf, 2)
        return {
            "source_file":    source_file,
            "status":         "success",
            "started_at":     started_at,
            "finished_at":    now_iso(),
            "duration_seconds": elapsed,
            "mode":           mode_label,
            "batched":        need_batch,
            "input_tokens":   input_tokens,
            "output_tokens":  output_tokens,
            "max_tokens":     MAX_TOKENS,
            "cost_usd":       cost_usd,
            "chunks_count":   len(doc.chunks),
            "output_file":    output_path.name,
        }

    except Exception as exc:
        elapsed = round(time.perf_counter() - started_perf, 2)
        print(f"      [错误] {exc}")
        return {
            "source_file":    source_file,
            "status":         "failed",
            "started_at":     started_at,
            "finished_at":    now_iso(),
            "duration_seconds": elapsed,
            "error":          str(exc),
            "output_file":    None,
        }


# ────────────────────────────────────────────────────────────────────────────────
# 单个 HTML 处理（8-K / 10-K / 10-Q）
# ────────────────────────────────────────────────────────────────────────────────

def process_one_html(
    html_path: Path,
    api_key: str,
    output_dir: Path,
    doc_type: str = "8k",
) -> dict:
    source_file  = html_path.name
    output_path  = output_dir / f"{html_path.stem.lower()}.json"
    started_at   = now_iso()
    started_perf = time.perf_counter()

    print(f"\n{'─' * 60}")
    print(f"处理：{source_file}  [doc_type={doc_type}]")
    print(f"{'─' * 60}")

    try:
        # Step 1: 提取 HTML 文字
        print("[1/3] 提取 HTML 文字...")
        text = extract_html_text(html_path)
        char_count = len(text)
        print(f"      提取完成，共 {char_count:,} 字符")

        # HTML 文档视为单页传给 LLM
        pages_text = [{"page": 1, "text": text}]

        # Step 2: 调用 LLM（HTML 文档不分批，也不使用视觉模式）
        print(f"[2/3] 调用 Anthropic API（纯文字 / 单批 / 模型：{MODEL}）...")
        raw_data, input_tokens, output_tokens, cost_usd = call_anthropic_single(
            pages_text, None, api_key, output_dir, doc_type
        )

        n_chunks = len(raw_data.get("chunks", []))
        print(f"      API 完成，返回 {n_chunks} 个原始 chunks")
        print(f"      input={input_tokens} / output={output_tokens} / 上限={MAX_TOKENS} / 费用=${cost_usd:.4f}")

        # Step 3: pydantic 校验
        print("[3/3] 校验数据结构（pydantic）...")
        try:
            doc = validate_schema(raw_data)
        except ValidationError as e:
            raw_debug_path = output_path.with_suffix(".raw.json")
            raw_debug_path.write_text(
                json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"      [警告] Schema 校验失败，原始数据已保存到：{raw_debug_path.name}")
            raise

        print(f"      校验通过，共 {len(doc.chunks)} 个 chunks")

        # 写入输出文件
        output_path.write_text(
            doc.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
        )
        print(f"      已保存：{output_path.name}")
        for c in doc.chunks:
            print(f"        [{c.chunk_id}]  {c.section_title}  (pages {c.page_range})")

        elapsed = round(time.perf_counter() - started_perf, 2)
        return {
            "source_file":    source_file,
            "status":         "success",
            "started_at":     started_at,
            "finished_at":    now_iso(),
            "duration_seconds": elapsed,
            "mode":           "html_text",
            "batched":        False,
            "input_tokens":   input_tokens,
            "output_tokens":  output_tokens,
            "max_tokens":     MAX_TOKENS,
            "cost_usd":       cost_usd,
            "chunks_count":   len(doc.chunks),
            "output_file":    output_path.name,
        }

    except Exception as exc:
        elapsed = round(time.perf_counter() - started_perf, 2)
        print(f"      [错误] {exc}")
        return {
            "source_file":    source_file,
            "status":         "failed",
            "started_at":     started_at,
            "finished_at":    now_iso(),
            "duration_seconds": elapsed,
            "error":          str(exc),
            "output_file":    None,
        }


# ────────────────────────────────────────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # ── 加载 API key ────────────────────────────────────────────────────────────
    if not ENV_FILE.exists():
        raise FileNotFoundError(f"找不到 .env 文件：{ENV_FILE}")
    load_dotenv(ENV_FILE)
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            f"未找到 ANTHROPIC_API_KEY。\n请在 {ENV_FILE} 中添加：\n  ANTHROPIC_API_KEY=sk-ant-..."
        )

    # ── 确认文件存在 ─────────────────────────────────────────────────────────────
    for pdf_path, _ in FIXED_PDFS:
        if not pdf_path.exists():
            raise FileNotFoundError(f"找不到 PDF 文件：{pdf_path}")
    for pr_path, _ in FIXED_PR_FILES:
        if not pr_path.exists():
            raise FileNotFoundError(f"找不到 Press Release PDF：{pr_path}")
    for html_path in FIXED_8K_HTML_FILES:
        if not html_path.exists():
            raise FileNotFoundError(f"找不到 8-K HTML 文件：{html_path}")

    # ── 目录管理 ─────────────────────────────────────────────────────────────────
    clean_previous_extractions()
    output_dir = create_output_dir()

    vision_status = (
        "开启（pymupdf 已安装）" if (USE_VISION and PYMUPDF_AVAILABLE)
        else "关闭（USE_VISION=False）" if not USE_VISION
        else "关闭（pymupdf 未安装，pip install pymupdf）"
    )

    run_log: dict = {
        "started_at":       now_iso(),
        "finished_at":      None,
        "model":            MODEL,
        "vision_mode":      USE_VISION and PYMUPDF_AVAILABLE,
        "max_pages_per_batch": MAX_PAGES_PER_BATCH,
        "output_dir":       output_dir.name,
        "files":            [],
    }
    (output_dir / "run_log.json").write_text(
        json.dumps(run_log, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n{'=' * 60}")
    print(f"模型：{MODEL}")
    print(f"视觉模式：{vision_status}")
    print(f"分批阈值：>{MAX_PAGES_PER_BATCH} 页自动分批")
    print(f"输出目录：{output_dir.relative_to(PROJECT_ROOT)}")
    total_files = len(FIXED_PDFS) + len(FIXED_PR_FILES) + len(FIXED_8K_HTML_FILES)
    print(f"处理文件数：{total_files}（EP PDF: {len(FIXED_PDFS)}，"
          f"Press Release PDF: {len(FIXED_PR_FILES)}，8-K HTML: {len(FIXED_8K_HTML_FILES)}）")
    print(f"{'=' * 60}")

    # ── 处理每个 PDF ─────────────────────────────────────────────────────────────
    for pdf_path, doc_type in FIXED_PDFS:
        result = process_one_pdf(pdf_path, api_key, output_dir, doc_type)
        run_log["files"].append(result)
        (output_dir / "run_log.json").write_text(
            json.dumps(run_log, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── 处理每个 Press Release PDF ──────────────────────────────────────────────
    for pr_path, doc_type in FIXED_PR_FILES:
        result = process_one_pdf(pr_path, api_key, output_dir, doc_type)
        run_log["files"].append(result)
        (output_dir / "run_log.json").write_text(
            json.dumps(run_log, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── 处理每个 8-K HTML（规则引擎，不消耗 token）────────────────────────────────
    for html_path in FIXED_8K_HTML_FILES:
        result = process_one_8k_html(html_path, output_dir)
        run_log["files"].append(result)
        (output_dir / "run_log.json").write_text(
            json.dumps(run_log, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── 收尾 ─────────────────────────────────────────────────────────────────────
    run_log["finished_at"]   = now_iso()
    total_cost = sum(r.get("cost_usd", 0) for r in run_log["files"])
    run_log["total_cost_usd"] = round(total_cost, 6)
    (output_dir / "run_log.json").write_text(
        json.dumps(run_log, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    success = sum(1 for r in run_log["files"] if r["status"] == "success")
    total   = len(run_log["files"])
    print(f"\n{'=' * 60}")
    print(f"完成！成功 {success}/{total} 个文件  总费用 ${total_cost:.4f}")
    print(f"输出目录：{output_dir}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
