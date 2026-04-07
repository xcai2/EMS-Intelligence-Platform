# `ExtractionNewsRelease.py` 解析框架与判定说明

本文是对 `Test_Design/ExtractionNewsRelease.py` 的完整中文解读，目标是回答以下问题：
- 代码整体框架是什么。
- 每一步解析逻辑在做什么。
- 为什么产物可以直接用于 chunk（切分/向量化前处理）。
- 如何判断“解析成功”。
- 如何判断“有意义内容是否都解析出来了”。

---

## 1. 脚本定位与目标

该脚本是 **News Release（新闻稿）解析器**，它的定位不是做业务分析，而是做“结构化提取 + 可供下游检索/embedding 的文本准备”。

脚本顶部注释已经写明两个优先目标：
- 输出结构尽量与 `Extraction8k.py` 对齐。
- 生成干净的 `full_text_core`，用于下游 chunk/embedding。

输入目录默认是：
- `Test_Design/File/Flex/News Releases`

输出目录默认是：
- `Test_Design/File/Extracted_<timestamp>/news_releases/...`

---

## 2. 代码框架（模块分层）

该脚本可以理解为 5 层：

1) **I/O 与格式层**
- 文件读取、编码兼容、PDF/HTML/TXT/MD 路由。

2) **文本清洗层**
- 统一换行、去控制字符、压缩空白、保留结构性换行。

3) **结构提取层**
- 从全文切成 `sections`、`blocks`、`reading_order`。
- 提取 `cover_metadata`、`classification`、`quality` 等元信息。

4) **下游可用性层**
- 生成 `full_text_core`（也写入 `chunk_text`），并保留层级标题。

5) **批处理与落盘层**
- 扫描目录，逐文件解析，写 `.parsed.json`，输出错误汇总 `_errors.json`，并生成 `_test_samples`。

---

## 3. 端到端主流程（单文件）

单文件入口：`parse_document(filepath, rel_path)`

处理顺序如下：

1. 根据后缀调用 `_parse_source_text`。
- `.pdf`：优先 docling，失败回退 pypdf。
- `.html/.htm`：优先 docling，失败回退 bs4 纯文本提取。
- `.txt/.md`：直接读取并清洗。
- 记录 `warnings`（例如 `docling_not_installed`、`parser:pypdf`）。

2. `full_text -> lines`
- 用 `_split_nonempty_lines` 得到非空行序列，作为后续结构化输入。

3. 提取 `cover_metadata`
- `_extract_cover_metadata` 从前段区域抽取标题、日期、source、tags 等。
- 若缺关键字段，再用 `_infer_registrant_name`、`_infer_date_from_filename` 补充。

4. 建立正文结构
- `_build_sections_from_items(lines)` 生成 `sections`（支持 markdown `##`/`###` 层级与 parent-child）。
- 同时产出 `exhibits`（当前 News 流程大多为空）与 `legal_lines`。

5. 衍生结构
- `_build_blocks_and_reading_order`：把 section 映射成 `heading/paragraph/legal_disclaimer` block。
- `_build_full_text_core`：汇总“用于 chunk/embedding 的核心文本”。

6. 组装结果 JSON
- source / classification / cover_metadata / usage_policy / full_text / full_text_core / sections / blocks / quality 等。

---

## 4. 各关键部分的逻辑细节

## 4.1 解析器路由与回退策略

`_parse_source_text` 的特点是“有主有备”：
- PDF/HTML 先走 docling（结构保留更好）。
- docling 失败再回退到传统提取器（pypdf 或 bs4）。
- 无论走哪条路径，都会在 `quality.warnings` 里留下解析路径标签（如 `parser:docling`、`parser:pypdf`、`parser:bs4`）。

这使你后续可以按解析器路径做质量抽检。

## 4.2 清洗策略

`_clean_text` 做的是“温和规范化”：
- 保留段落边界（不会把全文压成一行）。
- 去掉控制字符、零宽字符、冗余空行与多空格。

目的：
- 保留可读性与结构线索。
- 降低 embedding 输入噪声。

## 4.3 封面元数据提取

`_extract_cover_metadata` 主要在前部区域抽字段：
- `title/date/type/source/tags/relevance/capex_related/ai_related`
- 公司名相关：`registrant_name_*`
- 日期相关：`date_of_report_*`

并会做“噪声行过滤”（例如纯布尔、超长数字 id 等），减少垃圾字段污染。

## 4.4 section 构建逻辑

`_build_sections_from_items` 当前以 markdown 标题为主：
- 有 `##`/`###`：按标题切 section。
- 没有标题：降级成一个 `Full Document` section。
- 若正文前有前言内容：单独做 `Overview` section。
- 会计算 `parent_section_id`，保留层级关系（`##` 父级、`###` 子级）。

同时，每个 section 都有：
- `content_raw`
- `content_cleaned_for_embedding`
- `content`（当前与 raw 通常一致）

## 4.5 block 与 reading order

`_build_blocks_and_reading_order` 把 section 展开为线性可遍历块：
- `heading`
- `paragraph`
- `legal_disclaimer`（若命中法律声明规则）

`reading_order` 提供顺序索引，便于前端或下游按“阅读流”重建文档。

## 4.6 quality 质量摘要

`_build_quality` 输出质量统计：
- 页数、有效页比例（PDF路径更有意义）
- section/block/table 数量
- 文本字符数/词数
- warnings（最关键）

它不是“绝对质量评分”，而是“可观测性仪表盘”。

---

## 5. 为什么“可以直接去 chunk”

这里的“可以直接 chunk”不是说“任何算法都完美”，而是说此脚本输出已经满足常见 chunk 前置条件：

1) **有稳定主文本源**
- `full_text_core` 已是清洗后的核心正文。
- 同时写入 `chunk_text`，让下游直接消费。

2) **保留结构锚点**
- `full_text_core` 在拼接时会带 `# / ## / ###` 标题。
- chunk 时可以利用标题作为语义边界，减少切坏上下文。

3) **噪声相对可控**
- 基础清洗 + 法律声明识别 + 页码过滤。
- 比直接对原始 OCR/PDF 文本切分更稳定。

4) **有可追溯字段**
- 失败时可回看 `sections[].content_raw`、`quality.warnings`，便于修复规则。

因此，这个脚本产物是“可直接用于 chunk 的工程化中间层”，并且便于持续迭代。

---

## 6. 如何判断“解析成功”

可以分三层判定：

## 6.1 程序层成功（最低层）
- 文件被成功写出 `.parsed.json`。
- 未进入 `_errors.json`。

## 6.2 结构层成功（建议必查）
- `sections` 非空。
- `full_text_core` 非空。
- `quality.text_char_count > 0`。
- `quality.section_count`、`quality.block_count` 在合理范围（非 0）。

## 6.3 语义层成功（业务抽检）
- 核心段（标题、摘要、财务表、前瞻声明）是否都在 `sections` 中出现。
- 表格 markdown 是否保留在对应 section。
- 关键数字（如营收、EPS）是否在文本中可检索到。

建议把 6.2 作为自动检查规则，6.3 做抽样人工验收。

---

## 7. 如何判断“有意义内容是否都解析成功”

“有意义内容”通常指：
- 新闻标题/摘要
- Guidance 段
- 财务表（Schedule）
- 风险与声明段

建议使用以下清单：

1. **覆盖性检查**
- `sections[].header` 是否包含预期章节（如 Guidance、Statements、Schedule）。

2. **关键字检查**
- 在 `full_text_core` 搜索关键 token（如 `Revenue`, `GAAP EPS`, `SCHEDULE I`）。

3. **数值一致性检查**
- 随机抽 3-5 个关键数值，核对是否完整出现在解析结果。

4. **格式保真检查（表格）**
- markdown 表格行 `| ... |` 是否仍在；列是否明显错位。

5. **warnings 检查**
- 若出现 `docling_not_installed` + `parser:pypdf`，对复杂表格文件建议重点复核。

---

## 8. 你当前样本为什么三字段看起来一样

你提到的示例里：
- `content`
- `content_raw`
- `content_cleaned_for_embedding`

几乎一致，是因为原段落本身规整、清洗前后差异小。并不代表它们设计上没有区别。

在工程意义上：
- `content_raw`：追溯原貌。
- `content_cleaned_for_embedding`：向量化输入。
- `content`：通用展示/消费字段（当前实现通常等于 raw）。

---

## 9. 批处理框架与输出策略

`extract_all()` 做了这些事：
- 递归扫描输入目录中的支持格式。
- 每个文件调用 `parse_document`。
- 写入 `news_releases/.../*.parsed.json`。
- 失败写 `_errors.json`。
- 自动拷贝一个样本到 `_test_samples`。

`_prepare_output_dir()` 会新建时间戳目录，并清理“旧的 news release 提取目录”（不会动 8-K 目录）。

---

## 10. 已知边界与注意事项

1. `section_type` 在 News 流程里固定为 `news_section`，不做更细粒度语义分类。
2. `exhibits` 在新闻稿场景通常为空（不是 bug）。
3. docling 不可用时，复杂 PDF 表格可能保真下降（需抽检）。
4. `quality` 是观测指标，不等同业务“正确率”。

---

## 11. 实操建议（你后续怎么用）

1. 下游 chunk 默认直接用：`chunk_text`（等于 `full_text_core`）。
2. 若要高可追溯：同时保留 section 级 `content_raw`。
3. 建议新增自动质检：
- `full_text_core` 为空即 fail。
- `warnings` 命中回退解析器时提高抽检比例。
- 对含 `SCHEDULE` 的文件做关键数值校验。

---

## 12. 一句话总结

`ExtractionNewsRelease.py` 不是“只提纯文本”的脚本，而是一个带回退策略、结构化切段、可观测质量指标、并对 chunk/embedding 友好的解析管线；它把“可解析性、可追溯性、可下游消费”三件事放在同一个输出里。