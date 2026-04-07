# Test_Design — 文档提取与质量校验

## 目录结构

```
Test_Design/
├── File/
│   ├── Flex/                          # 原始文件（按文档类型分文件夹）
│   │   ├── annual_10K/
│   │   ├── quarterly_10Q/
│   │   ├── flex_8k_press_releases/
│   │   ├── flex_transcripts/
│   │   ├── Earnings Presentation/
│   │   ├── News Releases/
│   │   └── Press Releases/
│   └── extracted/                     # 提取结果输出目录
│       ├── Flex10K_<timestamp>/       # 批次输出
│       ├── _test_samples_<timestamp>/ # 每类文档的代表样本
│       └── validation_reports/        # 校验报告（自动保留最近 5 次）
│
├── Extraction10k.py                   # 10-K 年报提取
├── Extraction10Q.py                   # 10-Q 季报提取
├── Extraction8k.py                    # 8-K 事件报告提取
├── ExtractionEP.py                    # Earnings Presentation 提取
├── ExtractionFlexTranscripts.py       # 电话会议记录提取
├── ExtractionNewsRelease.py           # 新闻稿提取
├── ExtractionPressRelease.py          # 新闻通稿提取
├── extraction_output_utils.py         # 输出工具函数（公用）
└── ValidateExtraction.py              # 解析结果质量校验脚本
```

---

## 提取脚本

每个 `Extraction*.py` 负责一种文档类型的解析，将原始 PDF/HTML/MD 转为结构化 `parsed.json`。

### 运行方式

```bash
cd ~/Desktop/Flex-Practicum-Project-2026/Test_Design

# 批量提取（处理对应 File/Flex/ 子目录下的所有文件）
python Extraction10k.py
python Extraction10Q.py
python Extraction8k.py
python ExtractionEP.py
python ExtractionFlexTranscripts.py
python ExtractionNewsRelease.py
python ExtractionPressRelease.py

# 单文件提取
python Extraction10k.py --file "File/Flex/annual_10K/2025_Flex_10K.pdf"
```

提取结果输出到 `File/extracted/` 下，同时会在 `_test_samples_<timestamp>/` 中保留每类文档的代表样本。

---

## 质量校验脚本 (ValidateExtraction.py)

对 `parsed.json` 进行质量检查，判断解析结果是否适合后续 chunk 和 embedding。  
校验时会优先读取 `source.absolute_path / source.relative_path` 指向的原文件，并做原文对齐、锚点、关键数字和标题回溯比对。

### 运行方式

**必须在终端中运行，且三种模式选一种：**

```bash
cd ~/Desktop/Flex-Practicum-Project-2026/Test_Design
```

#### 模式 1：`--batch`（推荐，日常使用）

自动找到 `extracted/` 下最新的 `_test_samples_*` 文件夹，批量校验所有样本。

```bash
python ValidateExtraction.py --batch
```

#### 模式 2：`--file`

只校验单个 `parsed.json` 文件。

```bash
python ValidateExtraction.py --file "File/extracted/_test_samples_2026-04-06_18-09-12/2025_Flex_10K.parsed.json"
```

#### 模式 3：`--samples-dir`

指定某个样本目录，批量校验该目录下所有 `*.parsed.json`。

```bash
python ValidateExtraction.py --samples-dir "File/extracted/_test_samples_2026-04-06_18-09-12"
```

### 可选参数

| 参数 | 说明 |
|------|------|
| `--out DIR` | 指定报告输出目录（默认 `File/extracted/validation_reports/`） |
| `--no-report` | 仅终端打印结果，不生成报告文件 |

### 检查项与评分

| 检查项 | 权重 | 说明 |
|--------|------|------|
| 必需字段完整性 | 8 | source、quality 等顶层字段是否齐全 |
| 关键 Section/Item 覆盖率 | 12 | 10-K 的 Item 1/1A/7/8、10-Q 的 Item 1/1A/2 是否存在 |
| 正文总量 (词数) | 10 | 总词数是否在文档类型的合理区间内 |
| 原文整体对齐 | 15 | parsed 正文与原文件的词汇对齐和覆盖是否合理 |
| 原文锚点覆盖率 | 10 | parsed chunk 是否能在原文件中找到对应锚点 |
| 关键数字一致性 | 8 | parsed 中的数字是否能在原文件中回溯到 |
| 标题回溯一致性 | 6 | parsed 标题是否能在原文件中回溯到 |
| 页眉/页脚污染 | 10 | 是否混入页码、页眉页脚样板，包含 inline 污染检测 |
| 目录 (TOC) 污染 | 6 | 是否混入目录条目，包含 inline “Table of Contents” 污染检测 |
| 残句截断 | 6 | 结合相邻 chunk 判断是否存在无法自然拼接的坏句截断 |
| Chunk 重复率 | 5 | 相邻 Chunk 之间是否存在过度重复 |
| 标题层级保留 | 2 | Section 标题是否非空 |
| 表格提取质量 | 2 | 财务类文档是否提取到结构化表格 |

### 评判标准

- **通过 (PASS)**: 总分 >= 80
- **部分通过 (PARTIAL)**: 总分 50–79
- **不通过 (FAIL)**: 总分 < 50

### 输出报告

每次运行在 `File/extracted/validation_reports/<timestamp>/` 下生成：

| 文件 | 说明 |
|------|------|
| `report.json` | 机器可读的完整结果 |
| `report.md` | 人类可读的汇总报告（含进度条和问题列表） |
| `examples.md` | 原文脱锚、数字不一致、污染、截断、重复的具体样本摘录 |

报告目录自动保留最近 5 次，更早的会被清理。
