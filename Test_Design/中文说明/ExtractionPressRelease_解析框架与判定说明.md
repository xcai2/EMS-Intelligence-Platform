# ExtractionPressRelease.py 解析框架与判定说明（最新版）

本文档对应代码文件：`Test_Design/ExtractionPressRelease.py`。
目标是把这份解析器的框架、逻辑、chunk 可用性依据、成功判定标准、有效信息覆盖判定方法完整讲清楚，并覆盖你最近修复后的行为。

## 1. 脚本定位

这是一个 **Press Release parse-only 提取器**，核心职责是：

1. 从 `pdf/html/txt/md` 统一抽取可用文本。
2. 生成结构化输出（`sections/blocks/reading_order/cover_metadata/quality`）。
3. 产出可直接用于切块与向量化的 `full_text_core`。

默认目录：

- 输入：`Test_Design/File/Flex/Press Releases`
- 输出：`Test_Design/File/Extracted_<timestamp>/press_releases`

入口链路：`main()` -> `extract_all()` -> `parse_document()`。

## 2. 总体架构（7 层）

### 2.1 源文件解析层

关键函数：

- `_parse_source_text()`：按后缀分流。
- `_parse_docling_text()`：优先 Docling（markdown + 表格）。
- `_parse_pdf_text()`：Docling 不可用或失败时用 `pypdf`。
- `_parse_html_text()`：Docling HTML 失败时用 `bs4` 清洗 HTML。
- `_read_text_file()`：文本文件多编码读取。

行为特点：

1. PDF/HTML 都是 Docling 优先，失败自动降级。
2. 所有降级和异常会进 `warnings`。
3. 输出统一成 `(pages, full_text, parsed_tables, warnings)`。

### 2.2 文本清洗层

关键函数：`_clean_text()`。

当前清洗包括：

1. 换行标准化：`\r\n` / `\r` -> `\n`。
2. 去不可见字符：`\xa0`、`\u200b`、控制字符。
3. 清理 docling 噪音行：删除孤立的 `- •` 行。
4. 压缩多余空行（包含二次压缩）。
5. 压缩多空格。

这层确保后续 section 切分和 chunk 文本更稳定。

### 2.3 封面元数据层（cover_metadata）

关键函数：

- `_extract_cover_metadata(lines)`：先从文本头部抽键值信息。
- `_infer_registrant_name()`：公司名启发式兜底。
- `_infer_date_from_filename()`：日期文件名兜底。

`cover_metadata.fields` 采用三轨同步字段：

- 公司名：`registrant_name` / `registrant_name_raw` / `registrant_name_normalized`
- 日期：`date_of_report` / `date_of_report_raw` / `date_of_report_normalized`

另保留 `title/date/type/source/tags/...` 等字段。

### 2.4 Press Release 专项回填层（parse_document 内）

在 `classification.doc_subtype == "press_release"` 分支中，新增了 PDF 友好的专用抽取逻辑（你这轮重点修复）：

1. 搜索范围：`text_head = full_text[:800]`（从 500 提高到 800）。
2. 日期正则：匹配 `City, State, Month DD, YYYY`，且破折号改为可选。
3. 标题正则：匹配 `FLEX REPORTS ... RESULTS`。
4. 公司名抽取：
   - 先从 `^([A-Z][A-Z]+)\s+REPORTS` 抽（如 `FLEX`）。
   - 未命中再从 `pr_title_match` 第一词回填（`FLEX` -> `Flex`）。

写回规则是同步写三字段，避免字段不一致。

### 2.5 结构化层（sections）

关键函数：`_build_sections_from_items(lines)`。

核心逻辑：

1. 用 markdown 标题 `##`/`###` 建立 section 边界。
2. 若前言存在（第一标题前有正文），生成 `Overview` section。
3. 每个 section 生成：
   - `header/level/content/content_cleaned_for_embedding`
   - `has_legal_boilerplate/legal_boilerplate_lines`
4. 对 legal section 采用“整段路由”：
   - 只要 section 中任一行触发 legal 规则，整段 `body` 归入 legal。
   - `kept` 设为空，避免 forward-looking 只抽到一两行。

### 2.6 噪音结构治理层

在 `filtered_sections` 阶段加入了头部噪音治理：

噪音标题集合：

- `P R E S S  R E L E A S E`
- `P R E S S R E L E A S E`
- `EXHIBIT 99.1`

处理策略：

1. 噪音标题且无内容 -> 丢弃 section。
2. 噪音标题但有实质内容 -> 重命名为 `Notes and Disclosures`。

这避免了把大段说明文本挂在错误页眉标题下。

### 2.7 输出层（blocks/full_text_core/quality）

关键函数：

- `_build_blocks_and_reading_order()`
- `_build_full_text_core()`
- `_build_quality()`

行为要点：

1. `full_text_core` 现在是“标题 + 正文”格式：
   - 按 `level` 输出 `#` 标题行，再拼正文。
2. legal block 生成时过滤噪音：
   - 跳过 `<!-- image -->` 和空行，避免 docling 占位污染。
3. 质量指标统一输出：页数、文本量、section/block 数、warnings。

## 3. 为什么可以直接去 chunk

不是“凑合能切”，而是设计上就面向 chunk：

1. `usage_policy.chunk_source_field` 明确指定 `full_text_core`。
2. `full_text_core` 以结构化标题组织语义段落，天然适合 chunk 语义边界。
3. 清洗层已去掉大量技术噪声（控制字符、占位符、孤立 bullet 行）。
4. legal boilerplate 已被隔离，不会大面积污染语义向量。

建议下游默认使用：`full_text_core`。
`full_text` 仅用于追溯与人工排错。

## 4. 解析成功如何判断

建议分为工程成功和语义成功两层。

### 4.1 工程成功（硬标准）

满足以下全部条件：

1. 生成 `*.parsed.json`。
2. `extract_all()` 统计为 success。
3. JSON 必要字段齐全：
   - `source`、`classification`、`cover_metadata`
   - `full_text`、`full_text_core`
   - `sections`、`blocks`、`reading_order`
   - `quality`
4. 无致命错误 warning（信息型 parser warning 可接受）。

### 4.2 语义成功（质量标准）

建议阈值：

1. `quality.text_char_count > 0` 且词数合理。
2. `section_count >= 1`，`block_count` 与 section 数量匹配。
3. `full_text_core` 非空，且包含有效业务段落。
4. `cover_metadata` 关键字段可用：
   - `title`
   - `date_of_report*`
   - `registrant_name*`

## 5. 如何判断“有意义内容都解析到了”

从 5 个维度验收：

### 5.1 元数据完整性

检查：

1. `title` 是否正确（如 `FLEX REPORTS ... RESULTS`）。
2. `date_of_report/raw/normalized` 三字段是否一致且非空。
3. `registrant_name/raw/normalized` 三字段是否一致且非空（应能回填 `Flex`）。

### 5.2 主体正文完整性

检查核心业务内容是否在 `full_text_core`：

1. 季度结果摘要（营收、利润、EPS 等）。
2. 管理层评论/战略更新。
3. 附注说明段（应在合理标题下，不应挂在页眉噪音标题）。

### 5.3 法律声明处理正确性

检查：

1. Forward-Looking Statements 整段应进入 legal 通道。
2. `legal_disclaimer` 不应夹杂 `<!-- image -->`。
3. 正文区不应残留大段法律模板语句。

### 5.4 结构合理性

检查：

1. 噪音 section（如 `EXHIBIT 99.1` 空段）是否已消失。
2. 原页眉噪音标题是否改名为 `Notes and Disclosures`（有内容时）。
3. `reading_order` 顺序与文档阅读顺序一致。

### 5.5 噪音控制

检查：

1. `- •` 孤立行是否消失。
2. 空白压缩是否正常（无大量空行）。
3. `full_text_core` 不含明显技术占位符。

## 6. 关键字段用途建议

下游优先级建议：

1. `full_text_core`：主 chunk 输入。
2. `sections`：按段切块、保留标题上下文。
3. `cover_metadata.fields`：检索过滤、展示与聚合。
4. `quality`：自动验收与报警。
5. `full_text`：问题复盘和审计。

## 7. 当前已落地修复点（与旧版差异）

本说明已覆盖以下你要求并已实现的关键修复：

1. Press release PDF 日期抽取增强（范围扩大、破折号可选）。
2. 标题与公司名回填，`registrant_name` 三字段同步。
3. Forward-Looking legal 规则补齐。
4. legal 由“逐行抽取”改为“section 整段路由”。
5. legal block 过滤 `<!-- image -->` 占位符。
6. `full_text_core` 改为“标题 + 内容”格式。
7. 清洗层新增 `- •` 噪音行处理。
8. 噪音 section 头过滤与重命名治理。

## 8. 一句话结论

`ExtractionPressRelease.py` 已形成完整的“多源解析 -> 清洗 -> 元数据回填 -> 结构化分段 -> legal 隔离 -> chunk 核心文本生成 -> 质量评估”闭环；在当前版本下，输出可以直接用于 chunk/embedding，同时可通过 `cover_metadata + sections + legal blocks + quality` 对解析成功率与信息有效覆盖进行可审计验证。
