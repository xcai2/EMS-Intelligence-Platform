# 财务数据缓存方案（AI Chat 专用·设计草案）

> 状态：草案（待确认）
> 范围：**仅服务于 AI Chat 模块**。不修改 news / analytics / 现有 API 路由 / SEC 文档抽取链路。
> 起草日期：2026-04-28

---

## 1. 目标

为 AI Chat 提供一个本地财务数据缓存层，覆盖 **11 家公司**，分两组：

**组 A · EMS 目标公司（6 家）**

| 简称 | Ticker | 全名 |
|---|---|---|
| Flex | FLEX | Flex Ltd |
| Jabil | JBL | Jabil Inc |
| Celestica | CLS | Celestica Inc |
| Benchmark | BHE | Benchmark Electronics |
| Sanmina | SANM | Sanmina Corporation |
| Plexus | PLXS | Plexus Corp |

**组 B · 大客户/超大规模厂商（5 家）**

| 简称 | Ticker | 全名 |
|---|---|---|
| Amazon | AMZN | Amazon.com, Inc. |
| Google | GOOGL | Alphabet Inc. (Class A) |
| Microsoft | MSFT | Microsoft Corporation |
| Meta | META | Meta Platforms, Inc. |
| Oracle | ORCL | Oracle Corporation |

**两组使用完全相同的指标字段、相同的数据库 schema、相同的抓取流程。** 只是按用途分组便于阅读。

当用户在 AI Chat 中询问财务数字类问题（如 "Flex 最近一季营收"、"Microsoft 过去四季度自由现金流"），优先从本缓存查询，**命中则不再触发文档检索 / 网络搜索**。

---

## 2. 边界（明确不做）

- ❌ 不修改 `data/news_config.db` 的 schema 或数据
- ❌ 不修改 `backend/news/` 任何代码
- ❌ 不修改 `backend/analytics/table_extractor.py` 或其调用方
- ❌ 不修改 `backend/api/routes/financials.py` / `company_detail.py` / `intelligence.py`
- ❌ 不影响 dashboard / 公司详情页 / 情报页的现有数据来源

本方案是 **AI Chat 内部的、增量的、独立的**一层数据。

---

## 3. 总体架构

```
        AI Chat 用户问题
              │
              ▼
   ┌──────────────────────┐
   │ aichat/pipeline.py   │ ──── 数字类问题 ───► 查缓存 ──► 命中：返回数据
   │ （新增财务查询分支） │                              ──► 未命中：拉 yfinance 落库 → 返回
   └──────────────────────┘
              │
              └──── 非数字类（分类/段细/客户分布）─► 走原 RAG 流程（不变）

   ┌──────────────────────┐    pull     ┌────────────┐
   │  financial_cache     │ ──────────► │  yfinance  │
   │  （AI Chat 内置）    │ ◄────────── │            │
   └──────────────────────┘             └────────────┘
              │
              ▼
     data/aichat_financials.db
     （新文件，独立于其他所有 db）
```

公司主数据：模块内自带一份硬编码的 **11 家公司**映射，不依赖 news 模块。

---

## 4. 模块结构

新建目录，**完全位于 AI Chat 模块内部**：

```
backend/aichat/
  financial_cache/          ← 新增
    __init__.py
    companies.py            # 11 家公司 ticker / 别名 / 分组常量
    db.py                   # SQLite 初始化、连接
    fetcher.py              # 调 yfinance 抓数据
    repository.py           # 读写缓存
    service.py              # 对外门面：query_metric / query_snapshot
    intent.py               # 判断用户问题是否属于"数字型财务查询"
  pipeline.py               # 仅在此处接入财务查询分支（最小改动）
```

不在 `backend/` 顶层新建模块，**故意放在 `aichat/` 下**以表达"仅 AI Chat 使用"。

### 4.1 `companies.py` 草案

```python
COMPANIES = {
    # EMS 目标公司
    "FLEX":  {"name": "Flex Ltd",                "group": "ems",          "aliases": ["Flex", "Flextronics"]},
    "JBL":   {"name": "Jabil Inc",               "group": "ems",          "aliases": ["Jabil"]},
    "CLS":   {"name": "Celestica Inc",           "group": "ems",          "aliases": ["Celestica"]},
    "BHE":   {"name": "Benchmark Electronics",   "group": "ems",          "aliases": ["Benchmark"]},
    "SANM":  {"name": "Sanmina Corporation",     "group": "ems",          "aliases": ["Sanmina"]},
    "PLXS":  {"name": "Plexus Corp",             "group": "ems",          "aliases": ["Plexus"]},
    # 大客户 / Hyperscaler
    "AMZN":  {"name": "Amazon.com, Inc.",        "group": "hyperscaler",  "aliases": ["Amazon", "AWS"]},
    "GOOGL": {"name": "Alphabet Inc.",           "group": "hyperscaler",  "aliases": ["Google", "GOOG", "Alphabet", "谷歌"]},
    "MSFT":  {"name": "Microsoft Corporation",   "group": "hyperscaler",  "aliases": ["Microsoft"]},
    "META":  {"name": "Meta Platforms, Inc.",    "group": "hyperscaler",  "aliases": ["Meta", "Facebook"]},
    "ORCL":  {"name": "Oracle Corporation",      "group": "hyperscaler",  "aliases": ["Oracle"]},
}
```

`group` 字段仅用于日志 / 调试 / 未来 UI 分组展示，**不影响抓取或查询逻辑**——两组共用同一套字段、同一套缓存表、同一套刷新策略。

---

## 5. 数据库 Schema

文件：`data/aichat_financials.db`（新建，独立）

### 5.1 `financial_snapshots`

```sql
CREATE TABLE IF NOT EXISTS financial_snapshots (
    ticker        TEXT NOT NULL,
    statement     TEXT NOT NULL,         -- 'income' | 'balance' | 'cashflow' | 'info'
    period_type   TEXT NOT NULL,         -- 'quarterly' | 'annual'
    period_end    TEXT NOT NULL,         -- 'YYYY-MM-DD'
    payload       TEXT NOT NULL,         -- 原始 yfinance 字段 JSON
    fetched_at    TEXT NOT NULL,
    PRIMARY KEY (ticker, statement, period_type, period_end)
);

CREATE INDEX IF NOT EXISTS idx_fs_ticker_period
    ON financial_snapshots(ticker, period_type, period_end DESC);
```

### 5.2 `fetch_log`

```sql
CREATE TABLE IF NOT EXISTS fetch_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    status       TEXT NOT NULL,           -- 'ok' | 'partial' | 'error'
    error        TEXT
);
```

第一阶段不做拍平指标表，全部从 JSON `payload` 取数。简单、好扩展。11 家公司 × 4 种报表 × ~5 期 ≈ 220 行，规模很小。

### 5.3 覆盖的财务指标

来自 yfinance 的标准报表字段，统一覆盖 11 家公司：

- **Income Statement**：Total Revenue / Cost of Revenue / Gross Profit / Operating Income / Net Income / EPS
- **Balance Sheet**：Total Assets / Total Liabilities / Total Debt / Cash & Equivalents / Stockholders Equity
- **Cash Flow**：Operating Cash Flow / **Capital Expenditures（总额）** / Free Cash Flow / Financing CF / Investing CF
- **Info**：Market Cap / P/E / Shares Outstanding（来自 `Ticker.info`）

> CapEx 仅是"总额"。**分类明细 / 项目级 / 地区级 CapEx 不在缓存中**，问到这类问题走原 RAG 文档检索（见 §6）。

---

## 6. AI Chat 集成方式（确认采用"选项 1"）

**核心策略**：缓存只服务"数字型"财务问题；非数字类（分类、段细、客户分布、CapEx 用途等）自然 fallback 到原有 RAG 流程。

### 6.1 流程

```
pipeline.py 收到 query
  │
  ├─ intent.is_numeric_financial_query(query)?
  │     │
  │     ├─ Yes → 提取 (ticker, metric, period)
  │     │       │
  │     │       ├─ 缓存命中 → 格式化结果返回，跳过 RAG / web search
  │     │       │
  │     │       └─ 缓存未命中 → 触发 fetcher 拉数据 → 落库 → 再查 → 返回
  │     │
  │     └─ No  → 走原有 RAG / hybrid / assembled 流程（不变）
  │
  └─ 兜底：若缓存查询过程中报错，fallback 到原流程，不影响用户体验
```

### 6.2 意图判别（`intent.py`）

简单规则即可，第一阶段不引入 LLM：

- **公司识别**：扫描 query 中是否出现 11 家公司的 ticker 或别名（来自 `companies.py`）。
- **指标识别**：关键词列表，如 `revenue / 营收 / sales / margin / 利润 / cash flow / 现金流 / capex / capital expenditure / EPS / net income / total assets / debt / market cap / 市值`。
- **期间识别**：`Q1/Q2/Q3/Q4 + 年份`、`fiscal year`、`last quarter`、`past N quarters/years`、`最近一季`、`过去四季度`。
- **CapEx 拆分识别**（重要）：若 query 同时包含 `capex` **以及** `breakdown / by category / by region / where / 用途 / 拆分 / 哪些` 这类关键词，**判定为非数字类**，走 RAG。

公司 + 指标都识别到 → 视为数字型，进入缓存查询。

### 6.3 命中后行为

- **完全跳过 RAG / web search**（不并行跑），直接把缓存数据格式化为结构化 context 喂给 generator。
- 在响应里附带 `mode: "financial_cache"` 与数据来源时间戳 `fetched_at`，前端可标识。

### 6.4 未命中或异常

- 数据库里没有该期间数据 → 实时调 yfinance 抓，落库后返回。
- yfinance 调用失败 → fallback 到原 RAG 流程，**不让用户看到错误**。

---

## 7. 缓存刷新策略（已确认：手动）

**采用方案：手动触发刷新**。不做 TTL 过期、不做定时调度。

### 7.1 提供一个内部刷新接口

在 `backend/aichat/financial_cache/service.py` 暴露：

```python
def refresh_all() -> dict:           # 拉取全部 11 家
def refresh_one(ticker: str) -> dict # 拉取指定 ticker
```

并配套一个 API 路由（仅供内部 / 开发使用），例如：

```
POST /api/aichat/financial-cache/refresh           # 全量刷新
POST /api/aichat/financial-cache/refresh/{ticker}  # 单家刷新
```

返回每家公司的抓取状态、写入行数、错误信息。

### 7.2 查询时不主动检查新鲜度

- `intent` 判定为财务查询 → 直接读 SQLite，**不比对 yfinance 是否有更新**。
- 数据陈旧由人手动 `refresh` 解决。
- 若数据库里完全没有该 ticker 数据（首次启动）→ 仍然 fallback 到原 RAG 流程，不阻塞用户；提示开发者去跑一次 refresh 初始化。

### 7.3 一次性初始化

模块上线时手动调用一次 `refresh_all()` 即可把 11 家公司的历史数据全部抓回来。后续财报发布后再人工触发刷新。

---

## 8. 实施步骤

**阶段一 · 基础（约 1 天）**
- `companies.py`（11 家硬编码常量）
- `db.py` + 表结构创建
- `fetcher.py`：能拉一家公司的 income/balance/cashflow/info 并落库
- 跑一次全量初始化，**验证 11 家都能成功落库**

**阶段二 · 查询服务（0.5 天）**
- `repository.py`：按 ticker / 指标 / 期间查询
- `service.py`：对 pipeline 暴露的简单接口
- `intent.py`：财务问题判别（关键词 + 公司名 + CapEx 拆分识别）

**阶段三 · pipeline 接入（0.5 天）**
- 在 `backend/aichat/pipeline.py` 入口处加一个分支
- 端到端测试 10–15 个典型问题（覆盖 EMS 与 hyperscaler 两组）

**全过程零接触 news / analytics / 其他 API 路由。**

---

## 9. 已确认决定（汇总）

| 项 | 决定 | 备注 |
|---|---|---|
| 缓存刷新策略 | **手动触发** | 提供 `refresh_all()` / `refresh_one(ticker)` + 内部 API |
| 历史深度 | **yfinance 默认** | ~4 年年报 + ~5 季度，足够 AI Chat 使用 |
| Google ticker | **`GOOGL`** | 与项目其他模块（analyst_view / news / quotes_service）保持一致；`GOOG` 作为别名 |
| 缓存命中响应格式 | **默认结构** | `{response, mode: "financial_cache", data: {ticker, metric, period, value}, fetched_at, sources}` |
| CapEx 处理 | 缓存只存总额；分类/拆分类问题 fallback 到 RAG | "选项 1" |

---

## 10. 风险

- yfinance 是非官方接口，可能限流或字段变更 → 落库保留原始 JSON `payload`，便于回填。
- Flex / Jabil 财年与日历年错位（Flex FY 截至 3 月，Jabil FY 截至 8 月）→ `period_end` 一律用 yfinance 返回的真实报告期，不要按日历季推断。
- 11 家公司一次抓取约 30–60 秒（受 yfinance 速率限制）→ 全量初始化 / 定时刷新建议串行 + 每家间隔 1–2 秒。
- Hyperscaler（AMZN / GOOGL / MSFT 等）报表披露口径不同（如 Microsoft 不单独披露 CapEx 总额，而是以 "Property and equipment" 形式）→ `payload` 字段名以 yfinance 为准，查询层做映射兼容。
