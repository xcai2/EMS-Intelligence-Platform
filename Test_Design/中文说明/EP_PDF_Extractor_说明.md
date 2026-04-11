# EP_PDF_Extractor — 模型与运行逻辑说明

> 本文档说明 `experimental_ep_pdf_runner.py` 和 `EP_PDF_Extractor.py` 的工作原理：  
> 用的什么模型、每一步在做什么、为什么这样设计、输出是什么格式。

---

## 一、用的什么模型

**模型：`claude-sonnet-4-20250514`**，由 Anthropic 提供。

| 参数 | 值 |
|---|---|
| 模型名 | `claude-sonnet-4-20250514` |
| 调用方式 | Anthropic Python SDK（`anthropic` 包） |
| 最大输出 token | 16,000（可在脚本顶部 `MAX_TOKENS` 调整） |
| 计费单价 | 输入 $3 / 百万 token，输出 $15 / 百万 token |

API Key 从 `backend/.env` 文件读取，字段名为 `ANTHROPIC_API_KEY`。

---

## 二、整体流程（四步）

```
PDF 文件
   │
   ▼
[Step 1] pypdf 逐页提取文字
   │  → 跳过纯图片页（扫描件无法提取）
   │  → 每页保留页码 + 文字内容
   ▼
[Step 2] 调用 Anthropic API（Claude）
   │  → 把所有页面文字拼成一条消息发给模型
   │  → 模型按照预设 schema 返回结构化 JSON
   ▼
[Step 3] pydantic 校验
   │  → 检查字段类型、必填项、枚举值是否合规
   │  → 校验失败会保存原始响应方便 debug
   ▼
[Step 4] 写入 JSON 文件
      → 输出到 Test_Design/File/EP_Extracted_YYYYMMDD_HHMMSS/
```

---

## 三、Step 1 — pypdf 文字提取

使用 `pypdf` 库的 `PdfReader`，逐页调用 `extract_text()`。

- 返回格式：`[{"page": 1, "text": "..."}, {"page": 2, "text": "..."}, ...]`
- 页码从 1 开始，与 PDF 阅读器一致
- 纯图片页（扫描件）提取结果为空字符串，自动跳过
- 这步**不涉及 AI**，纯本地处理，速度很快

---

## 四、Step 2 — 调用 Claude

### 发送内容

把所有页面拼成以下格式发给模型：

```
=== PAGE 1 ===
（第1页文字）

=== PAGE 2 ===
（第2页文字）

...
```

### System Prompt 的核心指令

告诉模型：

1. 每一块内容都要提取，不能跳过（包括附录表格）
2. 每个 chunk 必须语义完整，读者不需要参考其他 chunk 就能理解
3. Guidance 数字和脚注要放在**同一个** chunk 里，不能拆分
4. 附录对账表格必须**完整保留所有数字**
5. 章节分隔页（如 "Business update / Revathi Advaithi"）要和下一页内容合并，不单独成 chunk
6. 只输出 JSON，不加任何 Markdown 围栏或解释文字

### chunk_type 枚举

模型给每个 chunk 标注类型，共 12 种：

| chunk_type | 含义 |
|---|---|
| `overview` | 封面/总览页 |
| `disclosure` | 风险声明、非 GAAP 披露 |
| `summary` | 季度业绩摘要 |
| `business_update` | 业务动态、市场趋势 |
| `financials` | 关键财务指标对比 |
| `segment` | 业务分部业绩 |
| `cash_flow` | 现金流 |
| `outlook` | 分部展望 |
| `guidance` | 财务指引（下季度/全年） |
| `guidance_bridge` | 指引对比桥接（前后版本对比） |
| `strategy` | 长期战略、关键结论 |
| `appendix_table` | 附录 GAAP to Non-GAAP 对账表 |

### chunk_id 命名规则

格式：`{期间}_{序号}_{短名}`

示例：
- `fy23q3_01_overview`
- `fy24q2_14_appendix_gross_profit`

---

## 五、Step 3 — pydantic 校验

用 `pydantic` 的 `BaseModel` 验证模型返回的 JSON 是否符合规范。

**顶层字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `source_file` | str | PDF 文件名（不含路径） |
| `output_mode` | str | 固定为 `chunk_ready_high_fidelity` |
| `document_type` | str | 固定为 `earnings_presentation` |
| `company` | str | 公司名称 |
| `period` | str | 如 `Q3 Fiscal 2023` |
| `quarter_end` | str | 季度结束日期，格式 `YYYY-MM-DD` |
| `earnings_announcement` | str | 财报发布日期，格式 `YYYY-MM-DD` |
| `chunks` | list | 所有 chunk，不能为空 |

**每个 chunk 的字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `chunk_id` | str | 唯一标识 |
| `section_title` | str | 章节标题 |
| `page_range` | [int, int] | 起始页和结束页 |
| `chunk_type` | ChunkType | 上方 12 种之一 |
| `content` | str | 正文内容，不能为空 |
| `metadata` | ChunkMetadata | 与顶层字段重复一份，方便检索时使用 |

校验失败时会把原始响应存成 `.raw.json` 文件，方便对比排查。

---

## 六、输出文件结构

每次运行会在 `Test_Design/File/` 下新建一个文件夹：

```
Test_Design/File/
└── EP_Extracted_20260407_120000/       ← 文件夹名带运行时间戳
    ├── EP_FY23Q3_FINAL.json            ← 第一个 PDF 的结构化结果
    ├── ep_fy24q2_final.json            ← 第二个 PDF 的结构化结果
    └── run_log.json                    ← 运行日志（含 token 用量和费用）
```

**每次运行会自动删除上一次的 `EP_Extracted_*` 文件夹**，保证目录下只有一份最新结果。

### run_log.json 示例

```json
{
  "started_at": "2026-04-07T12:00:00+00:00",
  "finished_at": "2026-04-07T12:05:00+00:00",
  "model": "claude-sonnet-4-20250514",
  "output_dir": "EP_Extracted_20260407_120000",
  "total_cost_usd": 0.421580,
  "files": [
    {
      "source_file": "EP_FY23Q3_FINAL.pdf",
      "status": "success",
      "duration_seconds": 132.56,
      "input_tokens": 14820,
      "output_tokens": 11340,
      "max_tokens": 16000,
      "cost_usd": 0.214710,
      "chunks_count": 18,
      "output_file": "EP_FY23Q3_FINAL.json"
    }
  ]
}
```

---

## 七、两个固定处理的 PDF

脚本目前硬编码处理以下两个文件：

| 文件 | 期间 |
|---|---|
| `EP_FY23Q3_FINAL.pdf` | Q3 Fiscal 2023（季末 2022-12-31） |
| `ep_fy24q2_final.pdf` | Q2 FY24（季末 2023-09-29） |

路径：`Test_Design/File/Flex/Earnings Presentation/`

---

## 八、常见问题

| 现象 | 原因 | 处理方式 |
|---|---|---|
| `status: failed` + `Unterminated string` | `MAX_TOKENS` 不够，输出被截断 | 调大 `MAX_TOKENS`（上调到 20000 或更高） |
| `output_tokens` 等于 `max_tokens` | 输出刚好卡在上限，大概率截断 | 必须调大 |
| `output_tokens` 远小于 `max_tokens` | 正常，token 够用 | 无需处理 |
| `PDF 中没有提取到任何文字` | PDF 是扫描图片 | 该脚本无法处理纯扫描件 |
| `未找到 ANTHROPIC_API_KEY` | `.env` 文件路径或内容有误 | 确认 `backend/.env` 里有该字段 |
