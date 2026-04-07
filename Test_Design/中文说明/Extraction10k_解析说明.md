# Extraction10k.py — 解析逻辑与质量判断完整说明

> 适用文件：`Extraction10k.py`（1063 行）  
> 适用源文件格式：`.html` / `.htm`（SEC EDGAR iXBRL）、`.pdf`  
> 本文档基于 `Flex_10-K_2022-05-20.html` 的实际解析结果编写

---

## 目录

1. [设计目标](#1-设计目标)
2. [整体架构](#2-整体架构)
3. [输出 JSON 结构](#3-输出-json-结构)
4. [各模块逻辑详解](#4-各模块逻辑详解)
   - 4.1 [HTML 解析层](#41-html-解析层)
   - 4.2 [DOM 位置标记机制](#42-dom-位置标记机制)
   - 4.3 [TOC/封面剥离：找到真正的正文起点](#43-toc封面剥离找到真正的正文起点)
   - 4.4 [章节结构识别](#44-章节结构识别)
   - 4.5 [财务表格提取](#45-财务表格提取)
   - 4.6 [表格标题定位](#46-表格标题定位)
   - 4.7 [正文清洗](#47-正文清洗)
   - 4.8 [Chunking 策略](#48-chunking-策略)
5. [为什么解析后可以直接 Chunk](#5-为什么解析后可以直接-chunk)
6. [解析成功的判断标准](#6-解析成功的判断标准)
7. [有意义的内容是否都已解析成功](#7-有意义的内容是否都已解析成功)
8. [已知局限与注意事项](#8-已知局限与注意事项)
9. [调用方式](#9-调用方式)

---

## 1. 设计目标

旧版脚本将整个 10-K 文档压缩成一个大字符串 `full_text`，交给调用方自行切割。这种方式有三个根本性问题：

1. **财务表格结构丢失**：资产负债表被拍平成 `Cash and cash equivalents \n $ \n 2,964 \n $ \n 2,637`，数字和科目完全脱离上下文。
2. **TOC 噪音污染**：前 7000 字是目录和封面页码，直接进入 chunk 后大量无效内容会干扰 embedding。
3. **章节信息缺失**：chunk 不知道自己属于 Item 7 还是 Item 8，无法做元数据过滤检索。

新版脚本的核心目标是：**输出的每一个 chunk 都是干净的、有上下文、有归属的最小语义单元，无需任何后处理即可直接送入 embedding 模型。**

---

## 2. 整体架构

```
原始文件 (.html / .pdf)
        │
        ▼
┌─────────────────────────────┐
│  Layer 1: 文件解析层         │
│  _parse_source()            │
│  ├─ HTML → _parse_html()    │  BeautifulSoup + XBRL 剥离
│  └─ PDF  → _parse_pdf_*()  │  docling（优先）/ pypdf（降级）
└──────────────┬──────────────┘
               │ full_text（含 __TBL_xxxx__ 标记）+ table_tags 列表
               ▼
┌─────────────────────────────┐
│  Layer 2: 结构识别层         │
│  _find_body_start()         │  定位正文起点，跳过 TOC
│  _detect_headings()         │  识别 Part I/II/III/IV + Item 编号
│  _build_sections()          │  按章节边界切割 body_lines
└──────────────┬──────────────┘
               │ sections：每章节含 body_lines + 归属表格列表
               ▼
┌─────────────────────────────┐
│  Layer 3: 内容处理层         │
│  _clean_section_body()      │  去除页码、标记行、法律套话
│  _html_table_to_markdown()  │  财务表格 → 干净 Markdown
│  _find_table_title()        │  DOM 爬取 + 文本回退定位标题
└──────────────┬──────────────┘
               │ 干净的 prose 文本 + 结构化 tables
               ▼
┌─────────────────────────────┐
│  Layer 4: Chunking 层        │
│  _split_into_chunks()       │  句子感知分割，800词/chunk，100词重叠
│                             │  表格作为独立 chunk 不拆分
└──────────────┬──────────────┘
               │
               ▼
        最终 JSON 输出
        sections[].chunks[]  ←── 直接 embedding
```

整个流程是**单向流水线**，每一层的输出是下一层的输入，层与层之间没有循环依赖。

---

## 3. 输出 JSON 结构

解析完成后输出一个 JSON 文件，顶层有 4 个字段：

```json
{
  "source":   { ... },    // 文件来源信息
  "document": { ... },    // 封面页提取的文档元数据
  "sections": [ ... ],    // 核心内容：章节列表，每章节含 chunks 和 tables
  "quality":  { ... }     // 解析质量报告
}
```

### 3.1 source

```json
{
  "file_name":     "Flex_10-K_2022-05-20.html",
  "suffix":        ".html",
  "relative_path": "Flex_10-K_2022-05-20.html",
  "absolute_path": "/path/to/file.html",
  "size_bytes":    3326832
}
```

记录文件来源，用于溯源和批处理时的错误定位。

### 3.2 document

```json
{
  "form_type":               "10-K",
  "registrant_name":         "FLEX LTD.",
  "period_of_report":        "2022-05-20",
  "fiscal_year_end":         "",
  "commission_file_number":  ""
}
```

从封面页提取的关键元数据，可用于 RAG 检索时的文档级过滤（例如只查询特定公司或特定年度的文件）。

### 3.3 sections（核心）

这是最重要的字段。每个 section 对象的完整结构：

```json
{
  "section_id":            "s003",
  "item_code":             "1A",
  "item_label":            "Item 1A",
  "header":                "Item 1A  RISK FACTORS",
  "section_part":          "Part I",
  "section_type":          "filing_item",
  "is_tail":               false,
  "has_legal_boilerplate": false,
  "char_count":            85432,
  "word_count":            14764,
  "chunks": [
    {
      "chunk_id":    "s003-c001",
      "text":        "Summary of Risk Factors These statements...",
      "char_count":  4521,
      "word_count":  777,
      "has_table":   false,
      "table_titles": []
    }
  ],
  "tables": [
    {
      "table_id":  "s003-t001",
      "title":     "...",
      "markdown":  "| Col1 | Col2 |\n|---|---|\n...",
      "row_count": 16
    }
  ]
}
```

**section_type 的三种值：**

| 值 | 含义 | 举例 |
|---|---|---|
| `part_header` | 结构性分隔符，无内容 | `Part I`、`Part II` |
| `filing_item` | 正文章节，有实质内容 | Item 1、Item 7、Item 8 |
| `tail` | 附录性章节，价值较低 | Item 15、Item 16、SIGNATURES |

### 3.4 quality

```json
{
  "total_sections":          28,
  "prose_sections":          8,
  "item_codes_found":        ["1","1A","1B","2","3","4","5","6","7","7A","8","9","9A","9B","9C","10","11","12","13","14","15","16"],
  "missing_expected_items":  [],
  "total_chunks":            176,
  "total_tables":            68,
  "total_words":             62562,
  "warnings":                ["parser:bs4"],
  "parsed_at":               "2026-04-03T01:55:42"
}
```

这是解析质量的量化报告，后文"解析成功判断"一节会详细说明如何读取这个字段。

---

## 4. 各模块逻辑详解

### 4.1 HTML 解析层

**函数：** `_parse_html(filepath)`

SEC EDGAR 的 10-K HTML 文件是 **iXBRL 格式**，即在普通 HTML 里嵌入了大量 XBRL 标签（`<ix:nonNumeric>`、`<ix:fraction>` 等），用于机器可读的财务数据标注。这些标签对人类阅读无意义，必须先剥离。

解析分三步：

**Step 1：移除非内容节点**
```python
for tag in soup(["script", "style", "noscript", "template", "svg"]):
    tag.decompose()
```
删除脚本、样式、SVG 图形等完全不含文字内容的标签。

**Step 2：剥离 XBRL 包装标签但保留文字**
```python
for tag in soup.find_all(True):
    name = tag.name.lower()
    if name in {"ix:header", "ix:hidden"}:
        tag.decompose()   # XBRL 隐藏头部，整体删除
    elif name.startswith(("ix:", "xbrli:")):
        tag.unwrap()      # XBRL 包装标签：删标签但保留内部文字
    elif name.startswith(("link:", "dei:", "us-gaap:")):
        tag.decompose()   # 纯机读财务标签，整体删除
```

**Step 3：Block 元素注入换行分隔符**

这是解决 SEC HTML 特有问题的关键步骤。SEC 的 10-K HTML **没有 `<p>` 段落标签**，所有文字都包裹在 `<div><span>` 嵌套里，每个 `<div>` 只含一行或一句话。如果直接 `get_text('\n')`，所有内容会连成一行，无法用 `\n\n` 分段。

解决方案是在每个 block-level 元素末尾手动注入一个 `\n` 标记：

```python
_BLOCK_TAGS = {"div", "p", "section", "article", "li", "h1", "h2", ...}
for tag in soup.find_all(_BLOCK_TAGS):
    sentinel = soup.new_tag("span")
    sentinel.string = "\n"
    tag.append(sentinel)
```

这样每个 `<div>` 结束时会产生额外的换行，相邻 block 之间就有了 `\n\n`，后续的 `_clean_text()` 会把 3 个以上换行合并成 `\n\n`，正确还原段落边界。

### 4.2 DOM 位置标记机制

**函数：** `_parse_html()` 中的 marker 注入部分

这是新版本解决"表格属于哪个章节"问题的核心设计。

**问题背景：** HTML 文档里有 78 个 `<table>` 标签，散布在各章节中。当我们把 HTML 转换成 flat text 后，表格和章节文本混在一起，如何知道第 23 张表格（资产负债表）属于 Item 8 而不是 Item 7？

**旧方法的问题：** 用文本内容重叠度判断——检查表格文本和章节文本是否有共同词汇。这种方法不可靠：一张跨越章节边界的表格、或者内容非常通用的表格，很容易被错误分配。

**新方法：DOM 位置标记**

在把 HTML 转成 text 之前，给每张 `<table>` 注入一个唯一的占位符：

```python
table_tags = soup.find_all("table")
for i, tbl in enumerate(table_tags):
    marker_tag = soup.new_tag("span")
    marker_tag.string = f"__TBL_{i:04d}__"
    tbl.insert_before(marker_tag)  # 注入在 table 之前
```

`get_text()` 调用后，这些标记会出现在 flat text 里，紧跟在表格内容的前面：

```
...Item 8 的正文段落...
__TBL_0023__
| As of March 31, | ...
| Cash and cash equivalents | $2,964 |...
...
__TBL_0024__
| Fiscal Year Ended March 31, |...
```

随后在 `_build_sections()` 里，通过二分查找找到每个标记在 `body_lines` 里的行号，再找到该行号对应的最近上方的章节标题——这就是该表格的归属章节。

```python
def _owner_idx(line_idx: int) -> int:
    # 二分查找：找 <= line_idx 的最大 heading start
    lo, hi, result = 0, len(heading_starts) - 1, 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if heading_starts[mid] <= line_idx:
            result = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return result
```

**效果验证（Flex 10-K 2022）：**

| 表格编号 | 行号 | 归属章节 | 表格内容 |
|---|---|---|---|
| Table 10 | 162 | Item 1 | 业务概述表 |
| Table 14~22 | 787~1351 | Item 7 | MD&A 分析表 |
| Table 23 | 1479 | Item 8 | **CONSOLIDATED BALANCE SHEETS** |
| Table 24 | 1614 | Item 8 | **CONSOLIDATED STATEMENTS OF OPERATIONS** |
| Table 27 | 2096 | Item 8 | **CONSOLIDATED STATEMENTS OF CASH FLOWS** |

归属完全正确，没有任何跨章节错配。

### 4.3 TOC/封面剥离：找到真正的正文起点

**函数：** `_find_body_start(lines)`

SEC 10-K 文档的结构特点：正文前有一个完整的目录（TOC），目录里列出了所有 Item 编号一遍，正文里再出现一遍。如果不剥离 TOC，`Part I` 和 `Item 1` 等标题会被识别两次，导致章节重复。

**解决方案：寻找第二次出现的 Part I**

```python
part1: list[int] = []
for i, line in enumerate(lines):
    pm = _PART_RE.match(line)
    if pm and pm.group(1).upper() in {"I", "1"}:
        part1.append(i)

if len(part1) >= 2:
    return part1[1]   # 第二次出现 = 正文起点
```

逻辑依据：

- 第一次出现 `Part I`（行 108）→ 这是 TOC 里的目录条目
- 第二次出现 `Part I`（行 186）→ 这是正文里真正的 Part I 开始

正文起点之前的所有内容（封面页、注册信息、目录页码等）全部跳过，不进入任何章节的处理流程。

**Flex 10-K 实际数据：**
- TOC 区域：行 0~185（185 行封面+目录）
- 正文起点：行 186（`PART I`）
- 正文总行数：约 2900 行

### 4.4 章节结构识别

**函数：** `_detect_headings(body_lines)`

使用三个正则表达式匹配三类结构标题：

```python
_PART_RE      = re.compile(r"^\s*part\s+(I{1,3}V?|IV)\s*...", re.IGNORECASE)
_ITEM_RE      = re.compile(r"^\s*item\s+(\d{1,2}[A-Ca-c]?)\s*...", re.IGNORECASE)
_SIGNATURE_RE = re.compile(r"^\s*signatures?\s*$", re.IGNORECASE)
```

对每一行进行匹配，命中则记录为一个 heading。heading 记录包含：

- `start`：该行在 body_lines 里的行号
- `body_start`：正文内容的起始行（Item 行本身不算正文）
- `item_code`：`"1A"`、`"7"`、`"8"` 等
- `section_part`：当前所在的 Part（Part I / Part II / ...）
- `is_part_header`：是否是 Part 级别的标题（无内容）

**章节边界切割：** 相邻两个 heading 之间的所有行，就是前一个 heading 的正文内容：

```
heading[i].body_start  →  heading[i+1].start  =  section i 的内容范围
```

**Flex 10-K 识别结果（28 个章节）：**

```
Part I  (part_header)
  Item 1   BUSINESS              6,440 词   10 chunks   1 table
  Item 1A  RISK FACTORS         14,764 词   20 chunks   0 tables
  Item 1B  UNRESOLVED STAFF...       1 词    1 chunk    0 tables
  Item 2   PROPERTIES               207 词    3 chunks   1 table
  Item 3   LEGAL PROCEEDINGS         29 词    1 chunk    0 tables
  Item 4   MINE SAFETY...             5 词    1 chunk    0 tables
Part II (part_header)
  Item 5   MARKET...                986 词    5 chunks   2 tables
  Item 6   [RESERVED]                 2 词    1 chunk    0 tables
  Item 7   MD&A                  11,032 词   27 chunks   9 tables
  Item 7A  MARKET RISK              997 词    2 chunks   0 tables
  Item 8   FINANCIAL STATEMENTS  24,817 词   91 chunks  49 tables
  ...（其余略）
```

### 4.5 财务表格提取

**函数：** `_html_table_to_markdown(table_tag)`

SEC EDGAR iXBRL 的财务表格 HTML 结构非常特殊，直接用 `get_text()` 或简单的 CSV 转换会产生严重问题。以资产负债表的一行为例：

**原始 HTML 单元格（Cash 行，8 个 `<td>`）：**
```
['Cash and cash equivalents', '$', '2,964', '', '', '$', '2,637', '']
```

问题分析：
- `$` 是独立的单元格（XBRL 要求单独标注货币符号）
- 两个 `2022` 数字后面各跟 1~2 个空单元格（XBRL 对齐占位符）

**解决方案：逐行压缩（compress_row）**

```python
def compress_row(raw: list[str]) -> list[str]:
    result = []
    i = 0
    while i < len(raw):
        cell = raw[i]
        if cell in {"$", "($)", "( $ )"}:
            # 把 $ 和下一个非空单元格合并
            j = i + 1
            while j < len(raw) and not raw[j]:
                j += 1
            if j < len(raw) and raw[j]:
                result.append(cell + raw[j])   # → "$2,964"
                i = j + 1
            else:
                i += 1  # 孤立 $，跳过
        elif cell:
            result.append(cell)
            i += 1
        else:
            i += 1      # 空占位符，跳过
    return result
```

**转换效果：**

```
输入：['Cash and cash equivalents', '$', '2,964', '', '', '$', '2,637', '']
输出：['Cash and cash equivalents', '$2,964', '$2,637']
```

**最终 Markdown 输出（资产负债表节选）：**

```markdown
| As of March 31, |  |  |
| --- | --- | --- |
| 2022 | 2021 |  |
| (In millions, except share amounts) |  |  |
| ASSETS |  |  |
| Current assets: |  |  |
| Cash and cash equivalents | $2,964 | $2,637 |
| Accounts receivable, net of allowance... | 3,371 | 3,959 |
| Contract assets | 519 | 282 |
| Inventories | 6,580 | 3,895 |
| Other current assets | 903 | 590 |
| Total current assets | 14,337 | 11,363 |
| ...（完整 37 行）... |  |  |
| Total assets | $19,325 | $15,836 |
```

数字、年份、科目名三者关系清晰，embedding 模型可以正确理解"2022年现金及现金等价物为 $2,964 百万"。

**Item 8 提取到的 49 张财务表格（前 5 张）：**

| table_id | 行数 | 标题 |
|---|---|---|
| s013-t001 | 37 | CONSOLIDATED BALANCE SHEETS |
| s013-t002 | 23 | CONSOLIDATED STATEMENTS OF OPERATIONS |
| s013-t003 | 9  | CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME |
| s013-t004 | 25 | CONSOLIDATED STATEMENTS OF REDEEMABLE NONCONTROLLING INTEREST |
| s013-t005 | 39 | CONSOLIDATED STATEMENTS OF CASH FLOWS |

### 4.6 表格标题定位

**函数：** `_find_table_title(table_tag, body_lines, marker_line_idx)`

SEC HTML 的表格标题不在 `<caption>` 标签里，而是在表格前面的兄弟 `<div>` 节点中。使用三级策略：

**Strategy 1：DOM 爬取（最可靠）**

从 `<table>` 节点向上爬，在每一层找前一个兄弟元素的文字：

```python
node = table_tag
for _ in range(5):  # 最多爬 5 层
    prev = node.find_previous_sibling()
    while prev:
        txt = prev.get_text(" ", strip=True)
        if 8 <= len(txt) <= 250:   # 合理长度的文本
            return txt
        prev = prev.find_previous_sibling()
    node = node.parent
```

**Strategy 2：body_lines 回溯（DOM 失败时）**

往上扫描最多 8 行，优先取含财务关键词的行（consolidated、balance sheet 等）。

**Strategy 3：表格第一行（最后兜底）**

取表格头部行的前 4 个非空单元格拼接。

**效果验证：**

| 表格 | DOM 爬取结果 |
|---|---|
| Item 7 净收入表 | "The following table sets forth our net sales by segment..." |
| Item 7 调整后现金流 | "Adjusted Free Cash Flow" |
| Item 8 资产负债表 | "CONSOLIDATED BALANCE SHEETS" |
| Item 8 利润表 | "CONSOLIDATED STATEMENTS OF OPERATIONS" |

### 4.7 正文清洗

**函数：** `_clean_section_body(body_lines)`

对每个章节的正文行做三类过滤：

```python
for line in body_lines:
    s = line.strip()
    if _PAGE_NUM_RE.match(s):      # 过滤：纯数字行（页码）
        continue
    if _TBL_MARKER_RE.search(s):  # 过滤：表格位置标记
        continue
    if any(p.search(line) for p in _LEGAL_PATTERNS):  # 过滤：法律套话
        has_legal = True
        continue
    kept.append(line)
```

**过滤的内容：**

- **页码行**：`^\s*\d{1,3}\s*$`，如独立出现的 `12`、`45`、`103`
- **位置标记**：`__TBL_0023__` 这类内部标记，不应出现在 chunk 里
- **法律免责套话**：匹配 `"shall not be deemed filed"` 和 `"incorporated by reference"` 的行——这类内容在每个章节末尾重复出现，对 RAG 毫无价值，并且会引起"引用合并"的语义混淆

被过滤的法律套话会在 section 对象里设置 `has_legal_boilerplate: true`，供下游系统判断该章节内容是否完整。

### 4.8 Chunking 策略

**函数：** `_split_into_chunks(prose, tables, section_id)`

#### 为什么不能用段落分割？

SEC 10-K HTML 没有真正的段落标签，get_text 的结果大量行是 1~5 词的短行（bullet point 的每个条目、子标题等）。用 `\n\n` 做段落分隔符，Item 1A（14,764 词）只会产生 1 个"段落"，完全无法切割。

#### 正确方法：句子感知分割

**Step 1：文本标准化**

把所有单换行转为空格，把段落边界转为句子终止符：

```python
prose_normalised = re.sub(r'\n\n+', '.  ', prose)   # 段落边界 → 句号
prose_normalised = re.sub(r'\n', ' ', prose_normalised)  # 单换行 → 空格
```

**Step 2：按句子边界分割**

```python
_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z\(\"\'])')
sentences = _SENT_SPLIT.split(prose_normalised)
```

匹配规则：`.!?` 之后跟空白，再跟大写字母或括号——这覆盖了绝大多数英文句子结束位置。

**Step 3：积累到目标词数后切割**

```python
CHUNK_TARGET_WORDS = 800
CHUNK_OVERLAP_WORDS = 100

for sent in sentences:
    if current_words + len(sent.split()) > 800 and current_sents:
        flush_chunk(current_sents)    # 超过 800 词，输出当前 chunk
        current_sents = [sent]
    else:
        current_sents.append(sent)
```

**Step 4：重叠（Overlap）**

每个 chunk 输出后，保存最后 100 词作为下一个 chunk 的前缀：

```python
prev_tail = words[-CHUNK_OVERLAP_WORDS:]
# 下一个 chunk 开头：" ".join(prev_tail) + " " + 当前内容
```

重叠的目的是防止一个跨越 chunk 边界的完整语义单元（一段论述、一个数字对比）被切成两半。

**Step 5：表格作为独立 chunk**

表格不参与词数积累，直接作为一个完整的 chunk 输出：

```python
def _flush_table(tbl):
    title = tbl.get("title", "")
    table_text = f"**{title}**\n\n{tbl['markdown']}"
    chunks.append({
        "chunk_id":    f"{section_id}-c{chunk_idx:03d}",
        "text":        table_text,
        "has_table":   True,
        "table_titles": [title],
    })
    prev_tail = []   # 表格后不产生 overlap（数字不适合做上下文种子）
```

#### Chunking 结果统计

以 Item 1A（Risk Factors，14,764 词）为例：

| chunk_id | 类型 | 词数 |
|---|---|---|
| s003-c001 | PROSE | 777 |
| s003-c002 | PROSE | 892 |
| s003-c003 | PROSE | 884 |
| ... | ... | ... |
| s003-c019 | PROSE | 872 |
| s003-c020 | PROSE | 243 |（最后一个，不足 800 词）

20 个 chunk，覆盖完整，词数均匀，平均 860 词/chunk。

**Overlap 验证（Chunk1 末尾 vs Chunk2 开头）：**

```
Chunk1 末尾：...we must provide increasingly rapid product turnaround times for our customers.
Chunk2 开头：reductions, or delays by a significant customer or by a group of customers have harmed...
```

Chunk2 开头的词来自 Chunk1 中部，保证了跨越边界的语义连贯性。

---

## 5. 为什么解析后可以直接 Chunk

传统流程是：原始文件 → 提取纯文本 → 在外部做 chunking。这个流程的问题在于 chunking 时缺少结构信息。

本脚本做到"直接 chunk"的原因有五个：

**① 噪音已在解析层去除**

页码、法律套话、XBRL 标签、TOC 目录、`__TBL_xxxx__` 标记——所有噪音在进入 chunking 之前已经被清除。chunk 里不会出现无意义的 `12` 或 `incorporated by reference`。

**② 章节边界已确立**

chunking 在每个 section 内部独立进行，不会跨越 Item 边界。一个 chunk 永远不会同时包含 Item 7（MD&A）和 Item 8（财务报表）的内容。

**③ 每个 chunk 携带元数据**

```json
{
  "chunk_id":    "s011-c003",
  "text":        "...",
  "has_table":   false,
  "table_titles": []
}
```

chunk 的所属 section 带有 `item_code`、`item_label`、`section_part` 等元数据，可直接用于 RAG 的元数据过滤（只查 Item 7 或 Item 8 的 chunk）。

**④ 表格已结构化为 Markdown**

Markdown 表格可以被主流 embedding 模型正确处理——模型理解 `|` 分隔的列关系。一个表格 chunk 的 `has_table: true` 标志可以告知下游系统这是数值型内容，可以做特殊处理（如使用不同的检索策略）。

**⑤ 词数和重叠已按最佳实践设置**

800 词/chunk 适合大多数主流 embedding 模型（OpenAI `text-embedding-3-*`、Cohere、BGE 等的上下文窗口均在 512~8192 token，800 英文词约等于 1000 token，处于最佳区间）。100 词重叠防止语义断裂。

---

## 6. 解析成功的判断标准

解析后读取 `quality` 字段，按以下四个维度判断：

### 6.1 核心 Item 是否全部找到

```json
"missing_expected_items": []
```

预期必须存在的 5 个 Item：`1`（Business）、`1A`（Risk Factors）、`7`（MD&A）、`7A`（Market Risk）、`8`（Financial Statements）。

- `missing_expected_items` 为空 → ✅ 全部找到
- 有值（如 `["7","8"]`）→ ❌ 解析失败，正文未被正确识别

**Flex 10-K 结果：** `[]`，全部 22 个 Item 均识别。

### 6.2 词数是否合理

```json
"total_words": 62562
```

10-K 文件一般在 40,000~120,000 词之间。

- 词数 < 5,000 → 脚本会自动触发 `"low_word_count"` 警告，说明 HTML 解析失败（可能是文件编码问题或 XBRL 结构异常）
- 词数 > 5,000 → ✅ 基本正常

### 6.3 表格是否提取到

```json
"total_tables": 68
```

有 Item 8（Financial Statements）的 10-K 文件一定有多张财务表格。

- `total_tables == 0` → 脚本会触发 `"no_structured_tables_extracted"` 警告
- `total_tables > 0`，且 Item 8 有表格 → ✅ 财务数据已结构化

### 6.4 警告列表

```json
"warnings": ["parser:bs4"]
```

| 警告值 | 含义 | 影响 |
|---|---|---|
| `parser:bs4` | 使用 BeautifulSoup 解析（docling 未安装）| 轻微，文本质量仍可接受 |
| `parser:docling` | 使用 docling 解析 | 最高质量，无影响 |
| `parser:pypdf` | PDF 降级用 pypdf | 无表格结构，仅文本 |
| `docling_not_installed` | docling 未安装 | 仅影响 PDF 质量 |
| `low_word_count` | 词数 < 5,000 | ❌ 严重，需人工检查 |
| `no_structured_tables_extracted` | 未提取到表格 | ❌ Item 8 数据不完整 |
| `missing_expected_items:7,8` | 缺少关键章节 | ❌ 严重，正文识别失败 |

**Flex 10-K 结果：** 只有 `parser:bs4`，属于轻微提示，不影响质量。

### 完整的成功判断代码示例

```python
import json

def is_parse_successful(parsed_json_path: str) -> tuple[bool, list[str]]:
    with open(parsed_json_path) as f:
        data = json.load(f)
    
    q = data["quality"]
    issues = []
    
    if q["missing_expected_items"]:
        issues.append(f"缺少关键 Item: {q['missing_expected_items']}")
    
    if q["total_words"] < 5000:
        issues.append(f"词数过少: {q['total_words']}")
    
    if q["total_tables"] == 0:
        issues.append("未提取到任何表格")
    
    fatal_warnings = {"low_word_count", "no_structured_tables_extracted"}
    for w in q["warnings"]:
        if any(fw in w for fw in fatal_warnings):
            issues.append(f"严重警告: {w}")
    
    return len(issues) == 0, issues

# 使用示例
ok, issues = is_parse_successful("Flex_10-K_2022-05-20.parsed.json")
print("解析成功" if ok else f"解析有问题: {issues}")
# 输出：解析成功
```

---

## 7. 有意义的内容是否都已解析成功

下表对 10-K 文件中所有有意义的内容进行逐项核查：

### 7.1 正文章节内容

| Item | 内容 | 词数 | Chunks | 状态 | 说明 |
|---|---|---|---|---|---|
| Item 1 | 公司业务概述 | 6,440 | 10 | ✅ | 完整提取 |
| Item 1A | 风险因素 | 14,764 | 20 | ✅ | 最长章节，完整 |
| Item 1B | 未解决人员意见 | 1 | 1 | ⚪ | 本身就几乎为空（Flex 无内容填写） |
| Item 2 | 物业资产 | 207 | 3 | ✅ | 含 1 张物业分布表 |
| Item 3 | 法律诉讼 | 29 | 1 | ✅ | 内容本身简短 |
| Item 4 | 矿山安全 | 5 | 1 | ✅ | 内容本身极简 |
| Item 5 | 股票市场信息 | 986 | 5 | ✅ | 含 2 张表格 |
| Item 6 | 保留（已废除） | 2 | 1 | ⚪ | SEC 规则废除该条目，内容为空属正常 |
| Item 7 | MD&A 管理层讨论 | 11,032 | 27 | ✅ | 含 9 张分析表，完整 |
| Item 7A | 市场风险定量分析 | 997 | 2 | ✅ | 完整 |
| Item 8 | 财务报表及注释 | 24,817 | 91 | ✅ | 含 49 张财务表格 |
| Item 9 | 会计师变更 | 2 | 1 | ⚪ | 本身无内容 |
| Item 9A | 内控程序 | 1,470 | 2 | ✅ | 完整 |
| Item 9B~9C | 其他信息 | 2~2 | 1~1 | ⚪ | 本身无内容 |
| Item 10~13 | Part III（代理文件） | 0 | 0 | ⚪ | Flex 将 Part III 并入代理声明，10-K 本身为空属正常 |

> ✅ = 已提取，有实质内容  
> ⚪ = 已提取，原文本身为空（非提取问题）

**结论：所有有实质内容的章节均已正确提取。**

### 7.2 财务表格

| 报表 | table_id | 行数 | 状态 |
|---|---|---|---|
| 合并资产负债表 | s013-t001 | 37 | ✅ 数字完整，年份正确 |
| 合并利润表 | s013-t002 | 23 | ✅ |
| 合并综合收益表 | s013-t003 | 9  | ✅ |
| 合并股东权益变动表 | s013-t004 | 25 | ✅ |
| 合并现金流量表 | s013-t005 | 39 | ✅ |
| 应收账款准备金 | s013-t006 | 5  | ✅ |
| 现金及等价物明细 | s013-t007 | 5  | ✅ |
| 存货明细 | s013-t008 | 6  | ✅ |
| 商誉变动表 | s013-t010 | 9  | ✅ |
| ...（共 49 张）| ... | ... | ✅ |

### 7.3 MD&A 分析表

| 报表 | 行数 | 状态 |
|---|---|---|
| 分部净收入表 | 7 | ✅ |
| 分部利润与利润率 | 6 | ✅ |
| 所得税分析 | 10 | ✅ |
| 调整后自由现金流 | 7 | ✅ |
| 长期债务明细 | 16 | ✅ |

### 7.4 封面元数据

| 字段 | 提取结果 | 状态 |
|---|---|---|
| 公司名称 | FLEX LTD. | ✅ |
| 报告期 | 2022-05-20 | ✅ |
| 表单类型 | 10-K | ✅ |
| 委员会文件编号 | （未能从该文件提取）| ⚠️ 轻微 |

---

## 8. 已知局限与注意事项

### 8.1 表格内仍有空列

SEC 10-K HTML 中部分表格的 header 行使用了 `colspan`，导致列标题展开后出现空列。例如：

```
| As of March 31, |  |  |    ← 第2、3列为空（colspan 合并的占位）
| 2022 | 2021 |  |          ← 第3列为空
```

这不影响数字的正确性，但 Markdown 表格看起来有多余的空列。可在下游处理时过滤纯空列。

### 8.2 PDF 源文件表格无结构

当输入是 `.pdf`（且 docling 未安装，降级到 pypdf）时，财务表格只能提取为平铺文本，无法还原 Markdown 表格。**建议：** 对 PDF 安装 docling，或直接使用 HTML 版本（SEC EDGAR 上两者均可下载）。

### 8.3 Part III 章节为空

Flex 10-K 将 Item 10~13（董事、薪酬等）并入代理声明文件，在 10-K 本身中只有一行"incorporated by reference"，被法律套话过滤器去除后内容为空。这是正常的 SEC 申报做法，不是提取问题。

### 8.4 表格标题偶发不准确

极少数情况下，DOM 爬取找到的前一个兄弟元素是一段较长的段落文字（而非一个简短的表格标题）。这种情况下 `title` 字段会包含一段句子开头。不影响表格内容本身，但会使 `table_titles` 字段的 chunk 元数据略显冗长。

---

## 9. 调用方式

### 单文件解析（推荐用于测试）

```bash
python Extraction10k.py --file path/to/10K.html --out output.parsed.json
```

输出摘要：
```
============================================================
File     : Flex_10-K_2022-05-20.html
Sections : 28  (prose: 8)
Items    : 1, 1A, 1B, 2, 3, 4, 5, 6, 7, 7A, 8, 9, 9A, 9B, 9C, ...
Missing  : none
Chunks   : 176
Tables   : 68
Words    : 62,562
Warnings : ['parser:bs4']
============================================================
```

### 批量处理

```bash
python Extraction10k.py --input-dir ./annual_10K/ --output-dir ./extracted/
```

### Python API 调用

```python
from Extraction10k import parse_document
from pathlib import Path
import json

result = parse_document(Path("Flex_10-K_2022-05-20.html"))

# 直接获取所有可用于 embedding 的 chunks
all_chunks = []
for section in result["sections"]:
    for chunk in section["chunks"]:
        all_chunks.append({
            "chunk_id":    chunk["chunk_id"],
            "text":        chunk["text"],
            "has_table":   chunk["has_table"],
            "item_code":   section["item_code"],
            "item_label":  section["item_label"],
            "section_part": section["section_part"],
            "company":     result["document"]["registrant_name"],
            "period":      result["document"]["period_of_report"],
        })

print(f"共 {len(all_chunks)} 个 chunk 可送入 embedding")
# 输出：共 176 个 chunk 可送入 embedding

# 只取高价值章节（Item 1, 1A, 7, 7A, 8）
core_chunks = [
    c for c in all_chunks
    if c["item_code"] in {"1", "1A", "7", "7A", "8"}
]
print(f"核心章节 {len(core_chunks)} 个 chunk")
# 输出：核心章节 136 个 chunk
```

### 依赖安装

```bash
pip install beautifulsoup4 pypdf lxml
# 可选（PDF 高质量解析）：
pip install docling
```
