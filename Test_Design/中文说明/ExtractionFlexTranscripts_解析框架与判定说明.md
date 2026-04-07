# ExtractionFlexTranscripts.py 解析框架与判定说明（覆盖版）

本文档对应代码：`Test_Design/ExtractionFlexTranscripts.py`。  
目标是完整说明该解析器的框架、逻辑、为何可直接用于 chunk、如何判断解析成功，以及如何验证“有意义内容”是否已经被充分提取。

## 1. 脚本定位

这是一个 **Flex earnings call transcript 的 parse-only 提取器**，用于把多源文档统一转换为结构化 JSON，服务下游：

1. 检索与问答（RAG）
2. chunk + embedding
3. 可追溯审计（结构与质量指标）

默认 I/O：

- 输入目录：`Test_Design/File/Flex/flex_transcripts`
- 输出目录：`Test_Design/File/Extracted_<timestamp>/flex_transcripts`

执行链路：`main()` -> `extract_all()` -> `parse_document()`。

## 2. 总体架构（8 层）

### 2.1 源解析层

核心函数：`_parse_source_text()`。

当前策略（最新版）：

1. `PDF`：**直接走 `pypdf`**，不再先尝试 docling。
2. `HTML/HTM`：docling 优先，失败回退到 bs4。
3. `TXT/MD`：直接文本读取 + 清洗。

对应函数：

- `_parse_pdf_text()`
- `_parse_docling_text()`
- `_parse_html_text()`
- `_read_text_file()`

输出统一为：`pages, full_text, parsed_tables, warnings`。

### 2.2 文本清洗层

核心函数：`_clean_text()`。

关键清洗规则：

1. 换行统一（`\r\n`/`\r` -> `\n`）。
2. 去不可见字符（例如 `\xa0`, `\u200b`, 控制字符）。
3. 删除点状分隔线（`\.{5,}`）。
4. 替换私有区 bullet 字符（`\uf0b7`, `\uf0a7` -> `-`）。
5. 压缩多余空白与空行。

目标：减少 OCR/PDF 噪音，提升 section/speaker 识别准确度。

### 2.3 封面元数据层（cover_metadata）

核心函数：

- `_extract_cover_metadata()`
- `_infer_registrant_name()`
- `_infer_date_from_filename()`

字段采用三轨同步：

- 公司名：`registrant_name` / `registrant_name_raw` / `registrant_name_normalized`
- 日期：`date_of_report` / `date_of_report_raw` / `date_of_report_normalized`

并保留 `title/date/type/source/tags/relevance` 等字段。

### 2.4 Transcript 分类层

核心函数：`_basic_classification()`。

默认输出：

- `doc_family = corporate_communication`
- `doc_subtype = earnings_call_transcript`

依据信号：`transcript`、`earnings call`、`q&a`、`fiscal/quarter/earnings` 等关键词。

### 2.5 Section 构建层

核心函数：`_build_sections_from_items()`。

#### 2.5.1 正常路径（有 markdown heading）

1. `##` -> level 2；`###` -> level 3
2. 基于 heading 区间切 body
3. 输出 section 结构：`header/level/content/content_cleaned_for_embedding/section_type/...`

#### 2.5.2 无 markdown heading 的 fallback（新版）

新增逻辑：

1. 用全大写行识别 section：`_ALLCAPS_SECTION_RE`
2. 限制 header 最大长度（`_MAX_HEADER_LEN = 80`）防止免责声明误判
3. 过滤纯点线和纯数字噪音行
4. 若识别到全大写 heading：转换为 `headings` 并复用主流程
5. 若仍无结构：全文作为一个 `Transcript` section

这一步是为 pypdf transcript 的“无 markdown 结构”场景设计的关键增强。

### 2.6 Speaker Turn 解析层（重点）

核心函数：

- `_is_likely_speaker_name()`
- `_extract_speaker_turns()`

#### 2.6.1 speaker 名字判定

`_is_likely_speaker_name()` 通过名字形态 + 屏蔽词过滤判定。  
已加入封面噪音词：`pages`, `total`, `copyright`, `formatted`, `report`，避免误识别为 speaker。

#### 2.6.2 turn 抽取逻辑（最新版）

支持三种模式：

1. 经典：`Speaker: text`（正则 `_SPEAKER_LINE_RE`）
2. Corrected Transcript：
   - 当前行是人名
   - 下一行是角色描述
3. 宽松触发：下一行末尾是 ` A` 或 ` Q` 也可触发 speaker 识别

并且支持 role+turn_type：

1. 若下一行形如 `Chief Financial Officer A`：
   - `role = Chief Financial Officer`
   - `turn_type = answer`（`Q` 则 `question`）
2. 否则：
   - `role = next_line`
   - `turn_type = ""`

`_flush()` 输出 turn 结构已包含：

- `speaker`
- `role`
- `turn_type`
- `text`
- `char_count`

fallback turn 也补齐了 `role` 和 `turn_type` 空字段，保持 schema 一致。

### 2.7 Speaker 继承状态机层

`_build_sections_from_items()` 里有 `current_speaker_section` 状态机：

1. 看到人名 header -> 更新当前 speaker
2. 若 section 无 turn 但有正文 -> 继承当前 speaker
3. 进入 `qa_section` 时清空当前 speaker，避免匿名分析师问题误归到上一个管理层

这一步是解决“Formatted/Corrected transcript 结构拆分导致 speaker 丢失或误归属”的关键。

### 2.8 Block 与顺序层

核心函数：`_build_blocks_and_reading_order()`。

输出：

1. `heading` block
2. `speaker_turn` block（含 `speaker/role/turn_type/content`）
3. `paragraph` block（无 turn 时）
4. `legal_disclaimer` block

并维护 `reading_order`，确保可重建阅读路径。

## 3. full_text_core 如何构建

核心函数：`_build_full_text_core()`。

规则：

1. 每个 section 先写 markdown 标题（按 level 生成 `#`）
2. 若有 turn：按 `speaker: text` 写入
3. 无 turn：写 section 正文
4. 跳过 `is_tail` section

最终结果：`full_text_core` 同时保留结构、说话人归属和语义文本。

## 4. 为什么可以直接去 chunk

可直接 chunk 的原因：

1. `usage_policy.chunk_source_field` 明确指定 `full_text_core`
2. `full_text_core` 已是“结构化 + 语义化”文本，不是原始脏文本直拼
3. speaker turns 已展开，问答上下文更稳定
4. 法律声明与正文可在 block 层分离，降低 embedding 噪音

建议下游默认用 `full_text_core` 做 chunk 输入。

## 5. 如何判断解析成功

采用“双层验收”：工程成功 + 语义成功。

### 5.1 工程成功

满足以下条件：

1. 输出 `*.parsed.json`
2. `extract_all()` 计为 success
3. 关键字段存在：
   - `source`, `classification`, `cover_metadata`
   - `full_text`, `full_text_core`
   - `sections`, `blocks`, `reading_order`
   - `quality`
4. 无致命异常（轻量 parser warning 可接受）

### 5.2 语义成功

建议检查：

1. `quality.text_char_count > 0`
2. `section_count` 与 `block_count` 不异常偏低
3. prepared remarks / q&a 等主段存在
4. `speaker_turn_count` 在关键 section 非零
5. `cover_metadata` 关键字段可用（标题、日期、公司）

## 6. 如何判断“有意义部分都解析到了”

建议按 6 维度验收：

### 6.1 元数据

1. `title` 是否正确（如 `Qx YYYY Earnings Call`）
2. 日期是否可解析并归一化（支持 `%d-%b-%Y`，如 `31-Jan-2024`）
3. 公司名三字段是否一致

### 6.2 结构

1. 主 section 是否齐全（prepared remarks / q&a / participants）
2. `parent_section_id` 层级是否合理
3. `reading_order` 是否符合阅读顺序

### 6.3 speaker 归属

1. 人名 + 职位两行能否正确识别
2. 职位行是否被跳过（不误当 speaker）
3. Q&A 匿名问题是否未误归属管理层

### 6.4 内容完整性

1. 关键财务指标段是否在 `full_text_core`
2. 管理层回答与分析师提问是否保留
3. 是否有整段被异常丢失

### 6.5 噪音控制

1. 点状分隔线是否清除
2. `\uf0b7/\uf0a7` 是否已替换
3. 封面噪音行是否未进入 speaker 名称

### 6.6 质量指标

1. `warnings` 是否在可接受范围
2. `pages_with_text_ratio` 是否异常
3. `section_count` 与文档复杂度是否匹配

## 7. 下游字段使用建议

推荐优先级：

1. `full_text_core`：chunk 主输入
2. `sections`：细粒度语义分块与筛选
3. `blocks`：界面展示与追溯
4. `cover_metadata.fields`：索引过滤条件
5. `quality`：自动验收与质量报警

## 8. 当前版本关键改动总览（已覆盖）

本覆盖版说明已包含你近期全部关键修复：

1. PDF 解析改为 transcript 直走 pypdf
2. 日期格式新增 `%d-%b-%Y`
3. FactSet cover metadata 三字段同步
4. role + `A/Q` 抽取并输出 `turn_type`
5. `speaker_turn` block 增加 `role/turn_type`
6. standalone speaker 宽松触发（next line 末尾 `A/Q`）
7. 无 heading 时全大写 heading 切分
8. 封面噪音词加入 speaker blocked 集合
9. 点状分隔线与私有 bullet 字符清洗

## 9. 一句话结论

`ExtractionFlexTranscripts.py` 现在是一个“可结构化、可审计、可直接 chunk”的 transcript 解析器：它不仅能提取正文，还能稳定识别 speaker/role/turn_type，并通过质量指标与结构输出支持下游查询、检索和排错。