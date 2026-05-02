# 合并分析：`Merge_5_1` vs `Srinidhi_5_1`

**日期：** 2026-04-30  
**目的：** 为将 Srinidhi 的分支合并到 Merge_5_1 基础分支提供决策指南。  
**基础分支（作为 bug 修复的事实来源保留）：** `Merge_5_1` / `origin/Merge_5_1`  
**传入分支（新功能）：** `origin/Srinidhi_5_1`

---

## 汇总表

| 文件 | 状态 | 冲突风险 | 需要采取的行动 |
|---|---|---|---|
| `backend/analytics/hyperscaler_financials.py` | Srinidhi 中新增 | 无 | 原样接受 |
| `backend/analytics/hyperscaler_guidance.py` | Srinidhi 中新增 | 无 | 原样接受 |
| `backend/analytics/ems_ai_dynamics.py` | Srinidhi 中新增 | 无 | 原样接受 |
| `backend/analytics/financial_service.py` | Srinidhi 中新增 | 与已删除的 `financial_cache` **重叠** | 评估 — 见 §4 |
| `backend/analytics/sentiment.py` | Srinidhi 修改 | 无 | 接受 Srinidhi（更好） |
| `backend/analytics/anomaly.py` | Srinidhi 修改 | 无 | 接受 Srinidhi（更好） |
| `backend/core/database.py` | 双方均修改 | **Srinidhi 已包含 Merge_5_1 的修复** | 安全 — 修复已存在 |
| `backend/rag/retriever.py` | Srinidhi 修改 | **Plexus 财年被移除** | 验证 Plexus 意图 |
| `backend/aichat/routes.py` | Srinidhi 重写了部分内容 | `_TABLE_PATTERNS` 上有 **冲突** | 需要手动合并 |
| `backend/api/routes/intelligence.py` | Srinidhi 大幅重写 | 无 | 接受 Srinidhi |
| `backend/ingestion/transcript_ingester.py` | Srinidhi 中新增 | 无 | 原样接受 |
| `backend/ingestion/scheduler.py` | Srinidhi 修改 | 无 | 接受 Srinidhi（更好） |
| `backend/api/routes/ingestion.py` | Srinidhi 修改 | 无 | 接受 Srinidhi |
| `backend/requirements.txt` | Srinidhi **移除了 `yfinance`** | **破坏性变更** | 必须恢复 yfinance |
| `frontend/src/app/ai-investments/page.tsx` | Srinidhi 扩展 | 无 | 接受 Srinidhi |
| `frontend/src/app/companies/page.tsx` | Srinidhi 重写 | **模块级缓存丢失** | 重新应用缓存修复 |
| `frontend/src/app/companies/[company]/page.tsx` | Srinidhi 简化 | 无 | 接受 Srinidhi |
| `frontend/src/components/layout/Sidebar.tsx` | Srinidhi 重构 | **Tooltip 修复状态不明确** | 验证 tooltip 是否正常 |

---

## 1. Hyperscaler 部分

### 1.1 `backend/analytics/hyperscaler_financials.py`（Srinidhi 中新增）

**它的作用：** 通过 `yfinance` 获取 5 家 hyperscaler（AMZN、MSFT、GOOGL、META、ORCL）的利润表和现金流。返回过去 5 个财年的营收、营业收入、净利润、营业利润率和 CapEx（转换为十亿美元，CapEx 以正的绝对值存储）。结果缓存在 `SimpleCache` 中，**TTL 为 24 小时**。

关键函数：
- `fetch_hyperscaler_financials(company)` — 按公司获取
- `fetch_all_hyperscaler_financials()` — 获取全部 5 家公司
- `invalidate_cache(company=None)` — 手动清除缓存

**无冲突。** 这是一个全新模块。它使用 `yfinance` — 见 §1.4 中关于 requirements.txt 的说明。

---

### 1.2 `backend/analytics/hyperscaler_guidance.py`（Srinidhi 中新增）

**它的作用：** 使用 Brave 网页搜索 + LLM 抽取（通过 `llm_structured`）获取 Big 5 hyperscaler 的**前瞻性 CapEx 指引**（不是历史实际值）。结果缓存 **7 天**（`SimpleCache`）。如果 Brave 不可用（`ANALYST_VIEW_BRAVE_ENABLED=False` 或没有 key），则回退到 `_FALLBACK` 字典中的硬编码数字（截至 2025 年初）。

还会通过单独的 Brave 查询（`fetch_stargate_update`）获取 **Stargate 项目**状态。

关键公开 API：
- `build_big5_capex_response()` — 完整响应（替换旧 `intelligence.py` 中硬编码的 `BIG5_AI_CAPEX` 字典）
- `fetch_all_guidance()` — 每家公司的原始 GuidanceResult
- `invalidate_guidance_cache(company=None)` — 清除缓存

**重要设计选择：** 种子文件 `data/big5_capex_seed.json` 只保存稳定的身份字段（名称、ticker、颜色）。所有财务数字都来自实时 Brave+LLM。这意味着如果 Brave 宕机且没有预热缓存，API 会返回静态 `_FALLBACK` 值。

**无冲突。** 全新模块。

---

### 1.3 `backend/analytics/ems_ai_dynamics.py`（Srinidhi 中新增）

**它的作用：** 用一个实时服务替换硬编码的 `EMS_AI_DYNAMICS` 字典（该字典原本是 `intelligence.py` 中约 110 行的常量），为每家 EMS 公司构建 AI dynamics 记录。并发使用三个数据源：
1. `backend.news.service.get_company_news()` — 来自磁盘缓存的前 3 条新闻标题
2. `backend.analytics.trends.analyze_company_trends()` — 基于 ChromaDB 的趋势/前景标签
3. Brave 搜索 + LLM 抽取 `ai_revenue_mix_pct`、`ai_revenue_growth_pct`、`guidance_summary`

结果缓存 **24 小时**。当 Brave 不可用时，所有三个数据源都回退到 `_FALLBACK` 字典。

关键函数：
- `get_all_dynamics()` — 全部 6 家 EMS 公司（每家公司并发任务）
- `get_company_dynamics(company)` — 单家公司
- `invalidate_cache(company=None)` — 清除缓存

**无冲突。** 全新模块。

---

### 1.4 `backend/requirements.txt` — **破坏性变更：yfinance 被移除**

```diff
-# Financial Data (AI Chat financial cache)
-yfinance>=0.2.40
```

Srinidhi 从 requirements 中删除了 `yfinance`，同时也删除了使用它的 `financial_cache` 模块。**但是，新的 `hyperscaler_financials.py` 和 `financial_service.py` 也都 import 了 `yfinance`。** 这是 Srinidhi 分支中的直接矛盾 — 功能代码使用 yfinance，但依赖被移除了。

**需要采取的行动：** 将 `yfinance>=0.2.40` 恢复到 requirements.txt。注释可以更新，说明它现在服务于 hyperscaler analytics 模块，而不是 financial_cache。

---

### 1.5 `backend/api/routes/intelligence.py` — Srinidhi 大幅重写

**Merge_5_1 中原有内容：**
- 硬编码的 `BIG5_AI_CAPEX` 字典（约 100 行，来源为 Futurum Research 2026 年 2 月）
- 硬编码的 `EMS_AI_DYNAMICS` 字典（约 110 行）
- 硬编码的 `MONITORED_NEWS` 字典（约 70 行）
- `GET /big5-capex` 直接返回静态字典
- `GET /ems-ai-dynamics` 返回静态字典
- `GET /news/*` 端点返回静态字符串

**Srinidhi 将它们替换为：**
- 删除全部三个大型字典
- `GET /big5-capex` → 调用 `hyperscaler_guidance.py` 中的 `build_big5_capex_response()`（实时）
- `GET /big5-capex/summary` → 同样使用实时来源
- **新增端点：**
  - `GET /hyperscaler/all/financials` → `fetch_all_hyperscaler_financials()`
  - `GET /hyperscaler/{company}/financials` → `fetch_hyperscaler_financials()`
  - `DELETE /hyperscaler/cache` → 清除缓存
  - `GET /hyperscaler/all/guidance` → `fetch_all_guidance()`
  - `GET /hyperscaler/{company}/guidance` → `_fetch_one()`
  - `DELETE /hyperscaler/guidance/cache` → 清除 guidance 缓存
- `GET /ems-ai-dynamics` → 调用 `ems_ai_dynamics.py` 中的 `get_all_dynamics()`（实时）
- `GET /ems-ai-dynamics/{company}` → 调用 `get_company_dynamics()`（实时，未知公司时抛出 404）
- `GET /news/*` 端点 → 委托给 `backend.news.service`（实时新闻服务）

**功能变化：** 所有以前的静态数据现在都改为动态获取。Merge_5_1 中的静态数据反映的是 2026 年 2 月的数据。Srinidhi 的版本会始终返回最新数据。

**冲突风险：无**，仅就此文件而言 — Srinidhi 的版本是严格改进。

---

### 1.6 `frontend/src/app/ai-investments/page.tsx`

**变更内容：**
1. 所有 TypeScript 接口都更新为使用可选字段（`?`），以防御实时 API 在 Brave 搜索没有返回结果时给出的 `null` 值。
2. `avgGrowth` 计算现在会在求平均前过滤掉 `null` 项。
3. 在数据可能缺失的地方渲染 `'—'` 占位符。
4. **新增 section：** “Historical CapEx Trend” — 调用 `GET /api/intelligence/hyperscaler/all/financials`，并渲染一个 `LineChart`（Recharts），展示 yfinance 中每家 hyperscaler 按财年的实际 capex。包括每家公司的 summary tile 和 YoY delta。使用单独的 state `historicalData` / `historicalLoading`，并通过第二个 `useEffect` 中的 `fetchHistoricalData()` 获取。
5. 新增 Recharts 的 `LineChart`、`Line` import。

**无冲突。** 纯新增。

---

## 2. Company 部分

### 2.1 `frontend/src/app/companies/page.tsx` — **模块级缓存丢失**

**关键背景：** 当前工作分支（`Merge_423` / 你现在所在的分支）上的 commit `fc7f5ab` 添加了模块级缓存，以防止用户每次导航回 Companies 页面时都重新获取数据。这个修复*不在* `Merge_5_1` 上（该 diff 的远程基础分支）。该 diff 比较的是远程 `Merge_5_1` 基础分支（同样没有缓存）和 `Srinidhi_5_1`，因此 diff 不会显示它被移除了。**但是，该缓存存在于你当前工作分支中，并且在整合 Srinidhi 的变更时不能丢失。**

commit `fc7f5ab` 中的模块级缓存模式如下：
```ts
// Module-level cache outside the component — survives remounts
let _companiesCache: Company[] | null = null;
let _analyticsCache: Record<string, AnalyticsData> | null = null;
```

**Srinidhi 在此文件中修改的内容：**
- 添加 3 波加载：第 1 波（companies），第 2 波（analytics overlays 并行），第 3 波（capex/AI/anomaly 在渲染后加载）
- 添加 `safeFetch()` helper — 任何错误都返回 null，并静默处理次要失败
- 添加 3 个新的 state 变量：`capexData`、`aiData`、`anomalies`
- 添加新接口：`CapExMention`、`AIInvestmentMention`、`TrendData`
- 添加 `COMPANY_COLORS` 常量
- 添加 tab 布局（`Tab` 类型：`'overview' | 'analysis' | 'trends'`）
- 添加 `selectedCompany` state
- import Recharts 组件：`BarChart`、`Bar`、`RadarChart`、`Radar` 等
- 添加图表数据派生（capexChartData、aiChartData 等）

**需要采取的行动：** 整合时，在 Srinidhi 的版本之上重新应用 commit `fc7f5ab` 中的模块级缓存模式。Srinidhi 版本中的 `fetchData` 函数已经明显不同 — 必须小心地把缓存逻辑织入其中。

---

### 2.2 `frontend/src/app/companies/[company]/page.tsx` — 简化

**Srinidhi 移除的内容：**
- Tab 类型：`'ai'`、`'geographic'`、`'news'`、`'patents'`、`'ocp'`（10 个 tab 中移除了 5 个）
- State 变量：`aiAnalysis`、`geographic`、`news`、`patents`、`ocp`
- 图标 import：`MapPin`、`Newspaper`、`Factory`、`Briefcase`、`Lightbulb`、`Users`、`Cloud`
- `investmentData` 图表数组（原本从 `aiAnalysis.investment_breakdown` 计算而来）

**Srinidhi 保留的内容：** `'overview'`、`'filings'`、`'financials'`、`'capex'`、`'hiring'`

**Srinidhi 添加的内容：**
- 数据源徽章（“Source: ChromaDB · SEC Filings”、“Source: SEC EDGAR Config”）追加到 card header
- Sentiment 方法指示器：根据 `overview.sentiment.method` 渲染 “FinBERT · SEC Filings” 或 “Lexicon · SEC Filings”
- 在 AI Focus %、Facilities 和 Documents KPI cards 上添加副标题 “SEC Filings · NLP”

**功能变化：** AI Analysis tab、Geographic tab、News tab、Patents tab 和 Open Compute tab 被移除。这些 tab 原本调用 `/api/company/{company}/ai-analysis`、`/api/company/{company}/geographic`、`/api/company/{company}/news`、`/api/patents/{company}`、`/api/ocp/{company}` 等端点。如果有人使用这些功能，它们现在无法从 company detail 页面访问。

**此文件无合并冲突风险。** 该简化是有意为之。

---

## 3. 后端 Analytics

### 3.1 `backend/analytics/financial_service.py`（Srinidhi 中新增 — 但 Merge_5_1 的 `analytics/` 中没有）

**它的作用：** 为 6 家 EMS 公司（FLEX、JBL、CLS、BHE、SANM、PLXS）提供 `get_company_financials(company)`。主要来源：通过 `fetch_yfinance_financials()` 使用 `yfinance`。返回 2022–2026 年的营收、营业收入、净利润、EPS、营业利润率。回退方案：`backend.analytics.table_extractor.extract_company_financials()`（ChromaDB vector DB）。该模块中结果**没有缓存** — 调用方必须处理缓存。

**与已删除的 `financial_cache` 模块存在重叠 / 冗余：** 已删除的 `backend/aichat/financial_cache/` 模块（6 个文件：`__init__.py`、`companies.py`、`db.py`、`fetcher.py`、`intent.py`、`repository.py`、`service.py`）是一个复杂得多的系统：
- SQLite 支持的持久化缓存
- 覆盖 6 家 EMS 公司和 5 家 hyperscaler（共 11 家）
- 有 `FinancialIntent` 检测逻辑，用于将查询分类为 financial-cache 命中
- 集成到 chat pipeline 中（routes.py 中的 `_answer_financial_query`），用于对数字型财务问题短路 RAG
- 有 `refresh_all()` 函数和手动刷新端点（`POST /chat/financial/refresh`）

Srinidhi 的 `financial_service.py` 是一个轻量替代方案 — 它只覆盖 EMS 公司，没有 SQLite 持久化，没有 intent detection，也没有 chat 集成。`aichat/routes.py` 中的 `financial_cache` 短路路径也被移除（整个 Step 2 block 约 68 行被删除）。

**影响：** chat pipeline 不再有针对数字型财务查询的快速路径。类似 “What was Flex's revenue last quarter?” 的问题现在会走完整 RAG pipeline。如果 RAG pipeline 能从 ChromaDB 文档中正确回答，这可能可以接受；但 `financial_cache` 系统原本是专门为用 yfinance 中的精确结构化数据回答这类问题而设计的。

---

### 3.2 `backend/analytics/sentiment.py` — FinBERT 升级

**变更内容：** 基于 OpenAI LLM 的 sentiment analysis 被完全替换为 FinBERT（通过 HuggingFace `transformers.pipeline` 使用 ProsusAI/finbert）。

| 方面 | Merge_5_1 | Srinidhi_5_1 |
|---|---|---|
| 主要方法 | 通过 `analyze_sentiment_llm()` 使用 LLM（OpenAI） | FinBERT（`_finbert_sentiment()`） |
| 回退 | Loughran-McDonald lexicon | 相同 lexicon（现在是显式 fallback） |
| `UNCERTAINTY_WORDS` | 存在（用于 lexicon scoring） | **移除** |
| Filing 权重 | 未应用 | 已应用 — transcripts 权重 2×，10-K 权重 1.5×，8-K 权重 1.1× |
| `analyze_company_sentiment()` | 合并 doc text 后评分一次 | 对每个 doc 单独评分，并应用 filing weight |
| `detect_sentiment_changes()` | 对合并文本使用 lexicon | 每个 batch 使用 `_weighted_finbert_score()` |
| 新 helper | — | `_weighted_finbert_score()` 作为 utility 暴露 |
| `analyze_sentiment_llm()` | 真实 OpenAI 调用 | 现在是 `_finbert_sentiment()` 的别名（向后兼容） |

**无冲突。** Srinidhi 的版本严格更好。注意：`transformers` 必须列在 requirements.txt 中（检查它是否已经存在）。

---

### 3.3 `backend/analytics/anomaly.py` — 输出增强

**变更内容：** `detect_capex_anomalies()` 和 `detect_ai_investment_changes()` 现在都包含：
- 每个 anomaly 的 `reason` 字段 — 人类可读的解释（例如 “CapEx spending in FY23 Q2 was 45% above the historical average ($320M reported vs $220M typical), suggesting an unusually large investment or one-time capital outlay.”）
- `sources` 字段 — 对该 anomaly period 有贡献的最多 5 个 source file label（filing type + filename）
- 在整个循环中跟踪 `sources_by_period` / `sources_by_year`

另外：全文中的 `doc.get("content")` 替换为 `doc.get("content") or ""`（防御性 null 处理）— 与 Merge_5_1 的 retriever 修复一致。

**无冲突。**

---

### 3.4 `backend/core/database.py` — **Merge_5_1 的关键修复已保留**

Merge_5_1 修复了 `has_company_collections()`，使其检查 collections 是否真的包含 documents（而不仅仅是作为空 collection 存在）。Srinidhi 的版本有**完全相同的修复** — 新实现会遍历 `list_company_collections()` 并对每个 collection 调用 `col.count() > 0`。该修复已保留。

---

### 3.5 `backend/rag/retriever.py` — **Plexus 从 `COMPANY_FY_START` 中移除；关键 ChromaDB 修复已应用**

**Plexus 移除：**
```python
# Merge_5_1 had:
"Plexus": 10,   # 10月开始，9月结束
# Srinidhi removed this entry entirely
```
这意味着 Plexus 现在会使用默认财年起始月份（`1` = 一月）。Plexus 的财年在九月结束（十月开始），所以这是**不正确的**。该移除看起来是意外的 — 它也从 `aichat/routes.py` 的 `COMPANY_FY_START` 字典中被移除了。**合并前必须调查这一点。** 如果 Plexus documents 被分配了错误的 quarter label，CapEx 和 trend analysis 会错位。

**ChromaDB 稳定性修复（Srinidhi 添加，必须保留）：**
- `_CHROMA_MAX = 150` — 将 ChromaDB 查询限制在 150，以避免大型 collections 上的 “Error finding id” 崩溃
- `fetch_n` 计算：`min(n_results * 3, _CHROMA_MAX, max(1, total - 1)) if total > 1 else 1`
- 当 `where_filter` 为 `None` 时，完全从 `query_kwargs` 中省略它（以前会显式传入，导致 ChromaDB 崩溃）
- 异常后的 retry 使用保守的小数量（`min(50, ...)`），而不是相同的 `fetch_n`
- 在 `search_documents()` 中 3 处添加了 `if metadata is None: metadata = {}` guard

这些 ChromaDB 修复是很有价值的稳定性改进，必须保留。

---

### 3.6 `backend/aichat/routes.py` — **冲突：`_TABLE_PATTERNS` regex**

两个分支都修改了 `_TABLE_PATTERNS`：

**Merge_5_1 版本**（简单，捕获任何地方出现的单词 “table”）：
```python
_TABLE_PATTERNS = re.compile(
    r"\btable\b|\b(not\s+paragraph|year.over.year\s+change|tabular\s+form)\b",
    re.IGNORECASE | re.DOTALL,
)
```

**Srinidhi 版本**（更长，要求更明确的 table 意图表达）：
```python
_TABLE_PATTERNS = re.compile(
    r"\b(in\s+(?:a\s+)?table(?:\s+format)?|show.*?table|table.*?format|"
    r"compare.*?table|not\s+paragraph|year.over.year\s+change|"
    r"numbers?\s+in\s+a\s+table|tabular\s+form|"
    r"give.*?table|as\s+a\s+table|display.*?table|"
    r"table\s+of|put.*?table|in\s+table)\b",
    re.IGNORECASE | re.DOTALL,
)
```

**Merge_5_1 的 pattern** 会匹配任何地方的裸词 “table” — 包括 “provide a comparison table”、“show in table format”、“give me a table” 等短语。这是有意设计得更宽泛。

**Srinidhi 的 pattern** 要求明确的表格请求措辞（例如 “in a table format”、“show me a table”）。它会**漏掉**独立的单词 “table”（例如用户只输入 “table” 或 “provide table”）。

**需要决策：** Srinidhi 的 pattern 降低了误报，但可能漏掉简单的 “table” 请求。Merge_5_1 的 pattern 更宽泛，能匹配更多用户表达。建议使用 **Merge_5_1 的 pattern**，除非已经知道存在误报问题。

**`aichat/routes.py` 中的其他变更：**

| 变更 | 影响 |
|---|---|
| 移除 `financial_cache.service` import | 不再有 SQLite cache 短路 |
| 移除整个 Step 2 block（financial cache check，在 `_stream_response` 和 `chat` 中各约 68 行） | Chat pipeline 不再有数字型查询的快速路径 |
| 移除 `POST /chat/financial/refresh` 端点（约 40 行） | 前端中的手动 cache refresh 按钮会变成失效链接 |
| 移除 `import threading` | 不再需要（之前用于 refresh lock） |
| 移除 `COMPANY_FY_START["Plexus"]` 条目 | 与 retriever.py 变更一致 — 但这是错误的 |
| 添加 `_is_hyperscaler_capex_query()` + `_build_hyperscaler_capex_context()` | Chat 现在会为 hyperscaler 问题注入实时 CapEx 数据 |
| 检测到查询时，在 LLM 调用前注入 Hyperscaler context | 改善 Big-5 CapEx 问题上的 chat 回答 |

---

### 3.7 `backend/ingestion/transcript_ingester.py`（Srinidhi 中新增）

**它的作用：** 从 SEC EDGAR 8-K filings 下载并 ingest earnings transcripts 和 press releases 到 ChromaDB。策略：
1. 按 tracked company 从 SEC EDGAR submissions API 获取最近的 8-K filings
2. 解析 filing 的 HTML index 以获取 exhibit types
3. 将 exhibits 分类为 transcripts（`EX-99.1` 且 description 中包含 “transcript”）或 press releases（`EX-99.1`、`EX-99.2`）
4. 下载 exhibits，并传给 `process_filing()` 进行 chunking 和 embedding
5. 在 JSON manifest（`data/earnings_transcripts/ingested_exhibits.json`）中记录已 ingest 的 exhibit IDs，以保证幂等性

`_infer_fiscal_period()` helper 使用 `FISCAL_YEAR_END_MONTH` 将 period-of-report dates 转换为 fiscal year labels（镜像 `sec_downloader.py`，但单独存在以避免循环 import）。

**无冲突。** 全新模块。

---

### 3.8 `backend/ingestion/scheduler.py` — 添加 Transcript job

Srinidhi 添加了：
- 新 job `transcript_check` — 通过 `scheduled_transcript_check()` 在周一至周五每天东部时间下午 6 点运行
- 一次性 startup job `transcript_check_startup` — 启动后 60 秒运行
- 移除 `scheduled_web_update()` 函数（它是一个什么也不做的 TODO stub）
- 为所有 APScheduler jobs 添加 `max_instances=1`，防止并发运行
- `process_new_filings` 调用现在使用 `asyncio.to_thread()`（之前直接 await — 但它是 sync function）
- 添加 `run_manual_transcript_check()`

**无冲突。**

---

## 4. 新闻相关差异：前端新闻模块背后的数据来源

这一段说的不是前端页面本身，而是**前端新闻模块调用的后端 API 数据从哪里来**。

- 现有版本：`merge 5-1`
- 想要合并进去的版本：`Serenity 5-1`

简单来说：`merge 5-1` 里，新闻相关 API 有一部分还在返回 `intelligence.py` 里写死的旧新闻；但项目里其实已经有一个完整的 `backend/news/service.py` 新闻服务。也就是说，同一类新闻数据同时存在“写死版本”和“新闻服务版本”，这就是这里说的“冗余”。

`Serenity 5-1` 的改动是：把 `intelligence.py` 里写死的新闻数据移除，让这些新闻 API 统一调用 `backend/news/service.py`。所以前端新闻模块看到的接口路径基本不变，但后端返回的数据来源从“硬编码旧数据”改成了“新闻服务中的实时/缓存数据”。

### 新闻逻辑所在位置

| 位置 | 作用 | 状态 |
|---|---|---|
| `backend/news/service.py` | 完整新闻服务：磁盘缓存（每家公司 JSON）、force-refresh、phase-2 pipeline、`get_company_news()`、`get_all_companies_news()` | 两个分支中都存在 |
| `backend/api/routes/intelligence.py`（`merge 5-1`） | `GET /news/all`、`/news/press-releases`、`/news/ocp`、`/news/industry` 返回硬编码的 `MONITORED_NEWS` 字典 | 静态、过期（2026 年 2 月），和新闻服务重复 |
| `backend/api/routes/intelligence.py`（`Serenity 5-1`） | 相同 4 个端点现在委托给 `backend.news.service` | 使用统一新闻服务，避免重复逻辑 |
| `backend/analytics/ems_ai_dynamics.py`（`Serenity 5-1`） | `_highlights_for(ticker)` 通过 `news_service.get_company_news()` 从磁盘缓存读取新闻 | 正确使用现有新闻服务 |

**Serenity 5-1 消除的冗余：** `merge 5-1` 中，`intelligence.py` 里的硬编码 `MONITORED_NEWS` 字典与完整的 `backend/news/` 模块重复。`Serenity 5-1` 正确地把这些接口委托给新闻服务。合并后，新闻逻辑会更集中：前端新闻模块仍然调用新闻 API，但 API 背后的数据统一来自 `backend/news/service.py`。

**对前端的影响：** 这不是“前端新闻页面被重写”的意思。更准确地说，是前端新闻模块拿到的数据会更接近实时/缓存服务中的内容，而不是 `intelligence.py` 里写死的 2026 年 2 月旧数据。

**已删除 docs：** `Serenity 5-1` 移除了 `docs/financial_cache/design.zh.md` 和 `docs/financial_cache/metrics_reference.zh.md`（它们记录的是现在已删除的 `financial_cache` 模块）。

---

## 5. 前端 — Sidebar

### `frontend/src/components/layout/Sidebar.tsx`

**Srinidhi 修改的内容：**

1. **导航结构完全重组：**

| Merge_5_1 groups | Srinidhi groups |
|---|---|
| News（独立） | `news-desk` — NEWs + Analyst View 放在一起 |
| Analyst View（独立） | |
| AI Chat（独立） | AI Chat（独立） |
| Companies（独立） | `intelligence` — Competitors + Hyperscaler + Map |
| Hyperscaler（独立） | `other` — Calendar + Companies（默认 collapsed） |
| Facilities Map（独立） | Reports & System |
| Calendar（独立） | |
| Reports & System | |

2. **新增 items：** `Competitors (/competitor-investments)`，使用 GitCompare icon；`Reports (/reports)`，使用 FileText icon。
3. **Sidebar 宽度扩大：** 展开时从 `w-52` → `w-72`。
4. **所有 items 都获得 `badge: 'NEW'`：** NEWs、AI Chat、Competitors、Hyperscaler、Facilities Map。
5. **图标尺寸增大：** `h-4 w-4` → `h-5 w-5`。
6. **Collapsed sidebar：** 整个 collapsed-mode 图标列表（带 `title={item.label}` 的 `Link` icons 滚动列表）被**移除**。在 Srinidhi 的 collapsed sidebar 中，只显示 expand button、FLEX logo 和 theme toggle。collapsed 状态下无法访问任何 nav items。
7. **为 nav groups 添加 card borders：** 每个 group div 外包裹 `rounded-2xl border`。

**关键：Tooltip 修复状态**

tooltip 修复应用在 commits `5eb568d`（onMouseEnter/Leave）、`069999d`（CSS tooltip 方案）和 `c3340a5`（overflow-hidden 修复）中 — 它们都在**当前工作分支**（`Merge_423`）上，不在 `Merge_5_1` 上。Srinidhi 的分支从更早的点分叉，因此没有这些 commits。

Srinidhi 的 Sidebar 没有 `onMouseEnter`/`onMouseLeave` state，也没有自定义 CSS tooltip。它还**完全移除了 collapsed icon list**，所以 tooltip 问题（只出现在 collapsed icon rail 中）在 Srinidhi 的版本中已经不存在，因为 collapsed mode 下没有 nav icons。

**需要采取的行动：** 决定是否应恢复 collapsed-mode nav icons。如果要恢复，则重新应用 commits `5eb568d`/`069999d` 中的 tooltip 修复。如果新的最小化 collapsed sidebar（只有 expand button + logo）可以接受，则不需要 tooltip 修复。

---

## 6. 优先行动项

1. **CRITICAL — `requirements.txt`：** 加回 `yfinance>=0.2.40`。`hyperscaler_financials.py` 和 `financial_service.py` 都 import 它。没有它，应用会在 import 时崩溃。

2. **HIGH — Plexus 财年：** `retriever.py` 和 `aichat/routes.py` 都从 `COMPANY_FY_START` 中移除了 `"Plexus": 10`。这意味着 Plexus documents 会被分配错误的 quarter label（一月财年开始，而不是十月）。验证这是否是有意的；如果不是，请恢复。

3. **HIGH — Companies 页面模块级缓存：** commit `fc7f5ab` 添加的缓存可以防止导航时重复获取数据。Srinidhi 的 page.tsx 是大幅重写，并不包含该缓存。必须在 Srinidhi 版本之上手动重新应用缓存。

4. **MEDIUM — `_TABLE_PATTERNS` regex：** Srinidhi 的版本要求像 “in a table format” 这样的明确表达。Merge_5_1 的版本会匹配裸词 “table”。决定哪种覆盖范围是正确的，并明确选择一种 — 这里会产生合并冲突。

5. **MEDIUM — Financial cache 短路：** Srinidhi 删除了 `financial_cache` 模块和 chat pipeline 的 Step 2 数字型财务查询快速路径。评估这是否会降低 revenue/EPS/margin 问题的 chat 质量，或者 RAG pipeline 是否已经足够覆盖。

6. **LOW — `POST /chat/financial/refresh`：** 该端点被移除。如果前端有 “Refresh Financial Data” 按钮，它会调用一个失效端点并得到 404。可以从前端移除按钮，或者暂时保留（它会静默失败）。

7. **LOW — Collapsed sidebar nav icons：** Srinidhi 从 collapsed sidebar 中移除了 icon rail。决定是否恢复它（然后重新应用 commits `5eb568d`/`069999d` 的 tooltip 修复），或接受新的最小化 collapsed sidebar。

8. **LOW — Company detail tabs 被移除：** `[company]/page.tsx` 丢失了 5 个 tab（AI Analysis、Geographic、News、Patents、Open Compute）。如果用户依赖这些功能，它们现在已经消失。这是否是有意的？如果是，可以考虑是否也应移除 `/api/company/{company}/ai-analysis` 等后端端点。

---

## 7. 无功能冲突的文件

这些文件被 Srinidhi 修改过，但没有合并冲突，也没有引入回归：

- `backend/analytics/sentiment.py` — 纯改进（FinBERT 升级）
- `backend/analytics/anomaly.py` — 纯改进（reason/sources 增强）
- `backend/api/routes/ingestion.py` — 添加 `TranscriptIngester` stats，并正确使用 `asyncio.to_thread`
- `backend/ingestion/scheduler.py` — 添加 transcript job，移除无效 stub，添加 `max_instances=1`
- `backend/ingestion/transcript_ingester.py` — 新模块，无冲突
- `frontend/src/app/ai-investments/page.tsx` — 添加历史图表 section，修复 null-safety
- `frontend/src/app/companies/[company]/page.tsx` — 简化 tabs，添加 source badges
