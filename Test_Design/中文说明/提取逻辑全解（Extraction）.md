# Test_Design 提取逻辑全解（只讲 Extraction，不讲后续 Embedding）

> 这份文档的目标：
> 1. 用人话讲清楚我们原项目里“提取（Extraction）”到底怎么做。  
> 2. 讲清楚它和 AI 的关系：哪些是 AI，哪些不是 AI。  
> 3. 讲清楚“AI 抽取验证入口”到底是什么意思。  
> 4. 带例子，能让不了解代码的人也看懂。  

---

## 0. 一句话先说结论

你记得的流程方向是对的：**先从原始文件里把文本提出来（Extraction），后面才会做切块、向量化、入库（Embedding/Index）**。

但项目里其实有两条“提取”线：

1. **通用文档提取线（非 AI）**  
   把 PDF / HTML / TXT / MD 变成纯文本（可附带表格结构），给后续 RAG / 建库用。

2. **CapEx 定向提取线（AI）**  
   不是把全文抽出来，而是针对“CapEx 数值”这个任务，让 LLM 从财报片段里抽一个关键数字，然后做验证。

很多人会把这两条线混在一起，所以会觉得“Extraction 到底是哪个 Extraction”。

---

## 1. 你现在关心的“建库前 extraction”，到底是哪一段

如果你的问题是：

- “数据库创建前，先把 data 里的文件提取出来的是哪段代码？”

那么最核心的是这条线：

### 1.1 生产/主流程里最核心的提取函数

- `backend/ingestion/processor.py`
  - `_extract_text(filepath)`

这个函数做的事非常直接：

- 输入：一个文件路径（可能是 `.pdf` / `.html` / `.htm` / `.txt` / `.md`）
- 输出：这个文件的纯文本字符串

它是“后续 chunk / embed / upsert 前”的基础动作。

### 1.2 可复现流水线里的提取阶段

- `scripts/pipeline_cli.py`
  - `stage_parse_documents()`
  - `parse_document()`
  - `parse_pdf()` / `parse_html()` / `parse_text()`

这套脚本把“提取结果”落盘为 JSON 文件，输出到：

- `pipeline_artifacts/parsed_documents/`

这一套更偏“离线阶段化流水线”，方便调试和复用。

### 1.3 建库脚本里也有解析逻辑

- `scripts/build_chromadb.py`

这个文件里也有 PDF/HTML 解析与结构化逻辑（尤其是 page/section 粒度），用于直接建向量库时做更结构化的提取与切分。

---

## 2. 原项目 Extraction（非 AI）到底怎么做

下面按文件类型讲，最容易理解。

## 2.1 HTML 提取

核心策略（`backend/ingestion/processor.py::_extract_text`）：

1. 用 `BeautifulSoup` 读 HTML。
2. 删除无关标签：`script` / `style` / `head` / `meta`。
3. `soup.get_text(separator="\n", strip=True)` 拉出文本。
4. 交给 `_clean_text()` 做清洗。

为什么这样做：

- 财报 HTML 会有大量脚本、样式、页面壳，直接提取会很脏。
- 把这些剔除后，剩下更接近“正文语义内容”。

人话例子：

- 文件里有一段 `<script>...</script>`，对理解财务数据没用。
- 提取时会把它删掉，只保留正文中像“Consolidated Statements of Cash Flows”这种文本。

## 2.2 PDF 提取

核心策略（同一个 `_extract_text`）：

1. **优先 `pdfplumber`** 逐页提取文本。
2. 如果失败，再 **fallback 到 `PyPDF2`**。
3. 两种方式都失败才返回空字符串。

为什么双引擎：

- 不同 PDF 版式差异很大。
- `pdfplumber` 对复杂布局通常更强；`PyPDF2` 是兜底。

人话例子：

- 一个扫描质量一般的 PDF，`pdfplumber` 可能提不全；
- 兜底用 `PyPDF2` 至少尽量拿到可用文本，避免整份文件直接废掉。

## 2.3 TXT / MD 提取

最简单：直接读取文本文件，再做 `_clean_text`。

## 2.4 清洗规则 `_clean_text`

主要做三件事：

1. 多个空行压成最多双空行。
2. 连续多个空格压成一个空格。
3. 去掉不可见控制字符。

目的：

- 减少噪声，方便后续切块和检索。

---

## 3. 这条非 AI 提取线，和后面流程怎么衔接（只讲边界）

你现在只关心 extraction，所以我只说边界，不展开 embedding 细节。

边界是：

1. Extraction 产出“可读文本”。
2. 后面模块再拿这个文本去做 chunk / embedding / upsert。

在 `backend/ingestion/processor.py` 里能看到：

- `process_filing()` 一开始就是 `text = _extract_text(filepath)`。
- 也就是说 **提取是第一步，没有文本就无法走后面**。

所以你的理解“先提取，再 embedding”是正确的。

---

## 4. 你提到的“AI 抽取验证入口”到底是什么

这部分很关键，因为名字很容易误导。

## 4.1 `backend/extraction/` 这一套不是“全文提取管道”

这个目录里的核心目标是：

- **从财报中抽取 CapEx 数值**（定向信息抽取）
- 再和 ground truth 比较准确率

它不是在做“把文件统一转成文本”的基础 extraction。

## 4.2 关键文件职责

- `backend/extraction/ai_extractor.py`
  - `extract_capex(...)`
  - 做法：先在文本中定位现金流相关片段，再把片段给 LLM，请它输出 JSON。

- `backend/extraction/prompts.py`
  - 放 CapEx 提示词模板和标签词（如 “Purchases of property and equipment”）。

- `backend/extraction/json_parser.py`
  - 解析 LLM 输出 JSON；
  - 清洗数字格式；
  - 把单位（thousands/millions/billions）归一到 millions。

- `backend/extraction/validate.py`
  - 把抽取值和真值比较（误差、是否在容忍度内）；
  - 输出报告和 CSV。

- `backend/extraction/run_extraction.py`
  - 这是“批处理入口壳”。
  - 目前会展示 ground truth 和提示信息，且代码里明确写了：
    - `Full batch extraction not yet implemented`（全量批处理还没完整实现）。

## 4.3 为什么说它是“AI 抽取验证入口”

因为它做的是：

1. 用 prompt 指挥 LLM 抽特定字段（CapEx）。
2. 抽完以后做数值清洗与单位归一。
3. 再和标准答案比准确率。

这就是“AI 抽取 + 验证”。

它和“文档全文提取”不是一回事。

---

## 5. “Extraction 和 AI 的关系”用最直白的话解释

可以把系统想成两层：

1. **底层搬运工（非 AI）**
   - 负责把各种格式文件“翻成文本”。
   - 干的是格式转换和清洗。

2. **上层分析员（AI）**
   - 负责从文本里找你要的具体答案（例如 CapEx 值）。
   - 干的是语义理解和信息抽取。

如果底层文本提不好，上层 AI 再聪明也难稳定。

所以“先 extraction 再 AI/embedding”在工程上是非常常见的顺序。

---

## 6. 用一个完整例子走一遍（人话版）

假设有文件：

- `Test_Design/File/Flex/annual_10K/2025_Flex_10K.pdf`

### 6.1 非 AI Extraction 在做什么

1. 打开 PDF。
2. 每页把文字读出来。
3. 把全文空白/脏字符清理一下。
4. 输出为文本（例如 `.txt`）。

你拿到的是“这份 10-K 的可读全文文本”。

### 6.2 AI CapEx 抽取在做什么

1. 在全文里先搜索类似 “Purchases of property and equipment” 的行。
2. 截取附近片段（现金流表附近）。
3. 把片段喂给 LLM，并明确要求：
   - 找 CapEx 这一行；
   - 10-Q 要区分 Three Months vs Six/Nine Months；
   - 负数要转正；
   - 单位统一成 millions。
4. LLM 回 JSON：`capex_value/raw_value/period/confidence` 等。
5. 程序再做数值清洗、单位归一、验证。

这一步拿到的是“一个业务答案（数字）”，不是全文文本。

---

## 7. 你现在 Test_Design 里那份 `extraction.py` 是怎么对应原项目的

你现在新增的文件：

- `Test_Design/extraction.py`

它的设计目标是“只保留 extraction 部分，不运行后续步骤”，并且针对你的目录：

- 输入：`Test_Design/File/Flex/**`
- 输出：`Test_Design/File/extracted/**`

它复用了原项目非 AI 提取思路：

1. HTML 用 BS4 去脚本样式后提取文本。
2. PDF 优先 `pdfplumber`，失败就 `PyPDF2`。
3. TXT/MD 直接读。
4. 做基础文本清洗。
5. 按原目录结构把结果输出成 `.txt`。

这就是你要的“只做 extraction，不做 embedding/建库”。

---

## 8. 容易混淆的点（重点避坑）

## 8.1 `backend/extraction/` 名字像“提取总线”，但其实是“CapEx 定向 AI 抽取”

不要因为目录名叫 extraction 就默认它是整个文档解析主流程。

## 8.2 `run_extraction.py` 不是你想的“把所有 data 文件统一提取成文本”的入口

它当前更像实验/验证入口，尤其围绕 CapEx ground truth。

## 8.3 真正“任何文档先转文本”的关键在 ingestion / pipeline 这条线

- `backend/ingestion/processor.py::_extract_text`
- `scripts/pipeline_cli.py::stage_parse_documents`
- `scripts/build_chromadb.py` 里的解析逻辑

---

## 9. 文件清单（你可以直接对照源码）

以下是“只看 extraction 相关”最关键的文件：

1. `backend/ingestion/processor.py`  
   生产流程最关键的文本提取入口（非 AI）。

2. `scripts/pipeline_cli.py`  
   阶段化流水线的“parse-documents”提取阶段（非 AI）。

3. `scripts/build_chromadb.py`  
   建库脚本内置解析与结构化提取（非 AI，含更丰富结构）。

4. `backend/extraction/ai_extractor.py`  
   AI 定向抽取 CapEx（不是全文提取）。

5. `backend/extraction/prompts.py`  
   AI 抽取提示词模板。

6. `backend/extraction/json_parser.py`  
   AI 输出 JSON 解析、数字清洗、单位归一。

7. `backend/extraction/validate.py`  
   AI 抽取结果与真值比较、报表导出。

8. `backend/extraction/run_extraction.py`  
   AI 抽取验证入口壳（当前全量批处理未完整实现）。

9. `Test_Design/extraction.py`  
   你当前测试目录的 extraction-only 脚本（已独立出来）。

---

## 10. 如果你只关心“现在怎么提取 Test_Design 里的文件”

一句话：

- 跑 `Test_Design/extraction.py`，它会递归读取 `Test_Design/File/Flex`，然后在 `Test_Design/File/extracted` 生成提取后的 `.txt`。

它只做你要的 extraction，不会触发 embedding 或数据库步骤。

---

## 11. 最后再用一句大白话总结

你可以把当前项目理解成：

- **文档提取（Extraction）**：把“文件格式”问题解决掉（PDF/HTML → 文本）。
- **AI 抽取（AI Extraction）**：把“业务问题”解决掉（例如 CapEx 到底是多少）。
- **验证（Validation）**：判断 AI 抽得准不准。

你现在要做的 `Test_Design` 任务，属于第一类：**文档提取（非 AI）**。

这也是为什么我们单独给你做了 `Test_Design/extraction.py`。

---

## 12. 把“建库前提取”画成流程图（文字版）

下面是最实用的理解方式：

1. 遍历文件目录（例如 `data/raw/...` 或 `Test_Design/File/Flex/...`）
2. 按文件后缀选择提取器：
   - `.pdf` -> PDF 提取器
   - `.html/.htm` -> HTML 提取器
   - `.txt/.md` -> 文本提取器
3. 提取得到 `text`
4. 对 `text` 做清洗
5. 如果 `text` 太短/为空：记为失败或跳过
6. 如果 `text` 可用：交给下一阶段（chunk / embedding / index）

你可以看到，这个阶段本质就是：

- 把“文件”转成“文本”
- 把“难处理格式”转成“机器可统一处理的输入”

---

## 13. 原项目里 Extraction 与后续模块的接口长什么样

这个点非常关键，决定你后续怎么改造。

在 `backend/ingestion/processor.py` 里，`process_filing()` 的前半段可理解为：

1. `text = _extract_text(filepath)`
2. 判断 `text` 是否有效
3. 调 chunk 逻辑（`_chunk_with_parent_child` 或 `_chunk_text_simple`）
4. 再做 embedding + upsert

换句话说，Extraction 的“接口契约”可以理解成：

- 只要你能稳定返回 `str text`，后面的大部分流程就可以复用。
- 所以后续换提取器（比如 OCR、Docling、MinerU）时，最重要的是保证输出文本质量，而不是先改后面的 embedding。

---

## 14. 为什么项目里会有不止一种提取实现

你会看到至少三处提取逻辑（ingestion、pipeline_cli、build_chromadb），这是正常的工程演化结果：

1. `backend/ingestion/processor.py`：
   偏“线上/主流程调用”的提取入口。

2. `scripts/pipeline_cli.py`：
   偏“离线实验、可重复执行、分阶段产物落盘”。

3. `scripts/build_chromadb.py`：
   偏“高结构化建库策略”（尤其 parent-child/page-section 结构）。

它们的共同点：

- 都在解决“把原始文件变成可用文本/结构”的问题。

它们的差异：

- 输出形态和调用场景不同（直接内存传递 vs 产物文件 vs 结构化 chunk）。

---

## 15. AI 抽取线的“逐步解释”（更细）

以 `backend/extraction/ai_extractor.py::extract_capex()` 为例，完整过程可拆成 6 步：

1. 校验是否配置了 LLM API Key。
2. `_find_cashflow_section(document_text)`：
   在全文里找 CapEx 相关标签，并优先定位现金流相关上下文。
3. `_detect_unit_header(section_text)`：
   看这段是不是写了 `(in thousands)` / `(in millions)` / `(in billions)`。
4. 把上下文信息 + 现金流片段拼成 prompt，调 `llm_complete()`。
5. `parse_extraction_response()` 解析 LLM 返回 JSON。
6. `clean_capex()` + `normalize_units()`：
   统一数字格式并换算到 `millions`。

所以 AI 抽取线并不是“直接把整份 PDF 扔给模型就完事”，而是：

- 先用规则缩小范围，再让模型做定向抽取，再做程序化后处理。

---

## 16. “提取失败”常见原因与排查建议

如果你后面运行 extraction，最常见问题通常是这些：

1. PDF 是图片扫描件，文本层很弱
   - 症状：提取结果接近空
   - 方向：需要 OCR 类方案（当前脚本不做 OCR）

2. HTML 编码/结构异常
   - 症状：输出夹杂大量导航文本或空白
   - 方向：加强清洗规则，或指定更精准的正文容器

3. 库依赖缺失（`pdfplumber`、`bs4`）
   - 症状：某类文件全部失败
   - 方向：安装依赖，或保留 fallback 路径

4. 文件本身是损坏文件
   - 症状：单文件稳定失败
   - 方向：先手动打开验证文件可读性

---

## 17. 你这次 Test_Design 方案为何是对的

你这次目标是：

- 验证一批 `Test_Design/File/Flex/...` 的文件能不能先稳定提取出文本。

这时候先做独立 `Test_Design/extraction.py` 是对的，因为：

1. 把“提取质量”与“建库质量”解耦。
2. 出问题时更容易定位是提取问题还是 embedding 问题。
3. 输出到 `Test_Design/File/extracted`，可人工抽查，质量可视化最直观。

这是一种很工程化、很稳妥的拆分方法。

---

## 18. 你可以怎么用这份文档（实际用途）

这份文档可以直接用于：

1. 新同学入组 onboarding
2. 评审时解释“Extraction 与 AI 抽取的边界”
3. 和产品/研究同学对齐“为什么先做 extraction 验证”
4. 后续写实验记录（例如替换 PDF 解析器效果对比）

如果你后面要，我还可以继续在这个目录补两份：

- `提取流程图（简版）.md`：只给非技术同学看
- `提取质量检查清单.md`：逐条验收清单（例如抽样 30 份文档）
