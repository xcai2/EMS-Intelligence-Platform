# Company Detail Page — 缓存实现方案

**目标文件：** `frontend/src/app/companies/[company]/page.tsx`

**需求：**
1. 进入某公司详情页时，立刻显示上次缓存的数据，不 Loading
2. 切换 Tab（Overview / Filings / Financials / CapEx / Hiring）时，如缓存存在，直接展示，不重新请求
3. 只有点击 Refresh 按钮才重新拉取数据
4. Refresh 后：与缓存对比，有变化才更新 state；无变化则保持缓存不变

---

## 1. 缓存结构

在组件函数**外部**（模块级别）声明缓存对象。Next.js App Router 在页面切换时会卸载并重新挂载组件，但模块级变量不会被销毁，因此可以保留上一次的数据。

```typescript
// 在 API_URL 声明之后、组件函数之前加入以下代码

type DetailCache = {
  overview: any;
  filings: any;
  financials: any;
  capexData: any;
  hiring: any;
};

// Key 为公司名（lowercase），例如 "flex"、"jabil"
const _detailCache: Record<string, DetailCache> = {};

function getCache(key: string): DetailCache {
  if (!_detailCache[key]) {
    _detailCache[key] = {
      overview: null,
      filings: null,
      financials: null,
      capexData: null,
      hiring: null,
    };
  }
  return _detailCache[key];
}
```

---

## 2. useState 初始化从缓存读取

将所有 state 的初始值改为从缓存读取：

```typescript
// 修改前
const [overview, setOverview] = useState<any>(null);
const [filings, setFilings] = useState<any>(null);
const [financials, setFinancials] = useState<any>(null);
const [capexData, setCapexData] = useState<any>(null);
const [hiring, setHiring] = useState<any>(null);
const [loading, setLoading] = useState(true);

// 修改后
const cache = getCache(companyKey);   // companyKey = params.company（lowercase）

const [overview, setOverview] = useState<any>(cache.overview);
const [filings, setFilings] = useState<any>(cache.filings);
const [financials, setFinancials] = useState<any>(cache.financials);
const [capexData, setCapexData] = useState<any>(cache.capexData);
const [hiring, setHiring] = useState<any>(cache.hiring);
const [loading, setLoading] = useState(!cache.overview);   // 有缓存则不显示 spinner
const [refreshing, setRefreshing] = useState(false);
const [refreshMsg, setRefreshMsg] = useState<string | null>(null);
```

> **注意：** `companyKey` 的值在 `useParams()` 之后才能获取，所以 `getCache(companyKey)` 需要在组件函数顶部调用（在 params 解析之后），确保在 useState 调用前执行。

---

## 3. useEffect — 只有缓存为空时才发起请求

```typescript
// 修改前
useEffect(() => {
  if (company) {
    fetchOverview();
  }
}, [company]);

useEffect(() => {
  if (company) {
    fetchTabData(activeTab);
  }
}, [activeTab, company]);

// 修改后
useEffect(() => {
  // 只有 overview 缓存为空时才拉取（首次访问该公司）
  if (company && !getCache(companyKey).overview) {
    fetchOverview();
  }
}, [company]);

useEffect(() => {
  if (company) {
    fetchTabData(activeTab);
  }
}, [activeTab, company]);
```

---

## 4. fetchOverview — 写入缓存

```typescript
const fetchOverview = async () => {
  setLoading(true);
  try {
    const res = await fetch(`${API_URL}/api/company/${company}/overview`);
    if (res.ok) {
      const data = await res.json();
      setOverview(data);
      getCache(companyKey).overview = data;   // 写入缓存
    }
  } catch (err) {
    console.error('Failed to fetch overview:', err);
  } finally {
    setLoading(false);
  }
};
```

---

## 5. fetchTabData — 先查缓存，再决定是否请求

```typescript
const fetchTabData = async (tab: TabType) => {
  const cache = getCache(companyKey);
  try {
    switch (tab) {
      case 'filings':
        if (!cache.filings) {
          const res = await fetch(`${API_URL}/api/company/${company}/filings`);
          if (res.ok) {
            const data = await res.json();
            setFilings(data);
            cache.filings = data;
          }
        }
        break;
      case 'financials':
        if (!cache.financials) {
          const res = await fetch(`${API_URL}/api/company/${company}/financials`);
          if (res.ok) {
            const data = await res.json();
            setFinancials(data);
            cache.financials = data;
          }
        }
        break;
      case 'capex':
        if (!cache.capexData) {
          const res = await fetch(`${API_URL}/api/company/${company}/capex`);
          if (res.ok) {
            const data = await res.json();
            setCapexData(data);
            cache.capexData = data;
          }
        }
        break;
      case 'hiring':
        if (!cache.hiring) {
          const res = await fetch(`${API_URL}/api/jobs/${company}`);
          if (res.ok) {
            const data = await res.json();
            setHiring(data);
            cache.hiring = data;
          }
        }
        break;
    }
  } catch (err) {
    console.error(`Failed to fetch ${tab} data:`, err);
  }
};
```

---

## 6. 新增 refreshData — 拉取所有已缓存的 Tab，有变化才更新

只重新拉取"已经被访问过（缓存不为 null）"的 Tab，防止刷新到从未打开过的页面。

```typescript
const refreshData = async () => {
  const cache = getCache(companyKey);
  setRefreshing(true);
  setRefreshMsg(null);

  let changed = false;

  // 始终刷新 overview
  try {
    const res = await fetch(`${API_URL}/api/company/${company}/overview`);
    if (res.ok) {
      const data = await res.json();
      if (JSON.stringify(data) !== JSON.stringify(cache.overview)) {
        setOverview(data);
        cache.overview = data;
        changed = true;
      }
    }
  } catch {}

  // 只刷新已被访问过的 Tab
  const tabFetches: Array<[keyof DetailCache, string]> = [
    ['filings',   `${API_URL}/api/company/${company}/filings`],
    ['financials',`${API_URL}/api/company/${company}/financials`],
    ['capexData', `${API_URL}/api/company/${company}/capex`],
    ['hiring',    `${API_URL}/api/jobs/${company}`],
  ];

  await Promise.all(
    tabFetches
      .filter(([key]) => cache[key] !== null)   // 只刷新已缓存的 Tab
      .map(async ([key, url]) => {
        try {
          const res = await fetch(url);
          if (!res.ok) return;
          const data = await res.json();
          if (JSON.stringify(data) !== JSON.stringify(cache[key])) {
            // 对应 setter
            if (key === 'filings')    setFilings(data);
            if (key === 'financials') setFinancials(data);
            if (key === 'capexData')  setCapexData(data);
            if (key === 'hiring')     setHiring(data);
            cache[key] = data;
            changed = true;
          }
        } catch {}
      })
  );

  setRefreshing(false);
  setRefreshMsg(changed ? '数据已更新' : '数据无变化，缓存保持不变');
  setTimeout(() => setRefreshMsg(null), 3000);
};
```

---

## 7. Refresh 按钮 — 改为调用 refreshData

找到 header 区域的 Refresh 按钮（当前调用 `fetchOverview`），替换为：

```tsx
{/* 修改前 */}
<button onClick={fetchOverview} ...>
  <RefreshCw className="h-4 w-4" />
  Refresh
</button>

{/* 修改后 */}
<div className="flex items-center gap-3">
  {refreshMsg && (
    <span className={`text-sm font-medium ${
      refreshMsg.includes('无变化') ? 'text-slate-500' : 'text-green-600'
    }`}>
      {refreshMsg}
    </span>
  )}
  <button
    onClick={refreshData}
    disabled={refreshing}
    className="flex items-center gap-2 px-4 py-2 bg-white rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all shadow-sm disabled:opacity-60"
  >
    <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
    {refreshing ? '刷新中...' : '刷新'}
  </button>
</div>
```

---

## 8. 行为总结

| 场景 | 行为 |
|------|------|
| 首次进入公司详情页 | `overview` 缓存为空 → 正常 Loading，完成后写入缓存 |
| 离开后再次进入 | `overview` 缓存存在 → 直接显示，无 Loading |
| 切换到未访问过的 Tab | Tab 缓存为空 → 正常请求，完成后写入缓存 |
| 切换到已访问过的 Tab | Tab 缓存存在 → 直接显示，无任何请求 |
| 点击刷新 | 拉取所有已缓存 Tab → 与缓存 diff → 有变化更新，无变化保持 |
| 页面跳转后再回来 | 缓存依然存在（模块级变量不随组件销毁），直接展示 |

---

## 9. 实现顺序

1. 在 `API_URL` 下方添加 `DetailCache` 类型 + `_detailCache` + `getCache()`
2. 修改 6 个 `useState` 初始值
3. 修改 `loading` 初始值为 `!cache.overview`
4. 添加 `refreshing` 和 `refreshMsg` state
5. 修改第一个 `useEffect`（overview 只在缓存空时拉取）
6. 修改 `fetchOverview` 写缓存
7. 修改 `fetchTabData` 写缓存
8. 新增 `refreshData` 函数
9. 修改 Refresh 按钮 JSX

---

## 10. CapEx Tab 新设计：近 5 年 CapEx Trend + 异常提示

### 10.1 当前逻辑的问题

当前 company detail 页里，用户点击 `View Detail` 后进入公司详情页，再切到 `CapEx` tab。这个 tab 现在有两块：

1. `CapEx Breakdown`
2. `CapEx Anomalies`

目前 `CapEx Anomalies` 的后端逻辑是：

- 从 ChromaDB 里搜索该公司的 CapEx 相关文档；
- 从文本中用正则抽取 dollar amount；
- 按 fiscal year / quarter 分组；
- 计算每个 period 的平均金额；
- 再和所有 period 的平均值比较；
- 如果高于或低于历史平均太多，就提示 spike / drop。

这个逻辑的问题是：它不是直接基于公司真实的财务 CapEx 表，而是基于文档文本里被搜索出来的金额。文本里可能同时出现 revenue、cash flow、investment、debt 等金额，正则不一定能保证每个金额都是真正的 CapEx。因此它适合做“文本信号异常”，但不适合做正式的近 5 年 CapEx 趋势分析。

新的设计应该改成：**用结构化财务表里的历史 CapEx 作为主数据源，再把当年 CapEx guidance / outlook 补进来，形成近 5 年趋势图，并在这个趋势图基础上判断异常。**

---

### 10.2 参考 Hyperscaler 的 AI Investment Details 逻辑

Hyperscaler 页面里的 `AI Investment Details` 已经采用了类似的混合数据逻辑：

| 数据 | 来源 | 用途 |
|---|---|---|
| 2025 历史实际 CapEx | `yfinance` / historical financials | 作为上一年真实值 |
| 2026 CapEx outlook | Gemini API + Google Search grounding | 作为当前年/未来年的 guidance |
| 页面缓存 | `data/hyperscaler/big5_capex_view_model.json` | 页面加载时直接读取，不每次调用 Gemini |
| 原始回答 | `data/hyperscaler/big5_capex_api_raw.json` | 调试用，不直接给前端 |

对应代码逻辑：

- 前端页面加载：
  - `GET /api/intelligence/big5-capex`
  - 只读取后端缓存好的 view model，不直接触发 Gemini。
- 前端读取历史值：
  - `GET /api/intelligence/hyperscaler/all/financials`
  - 从 yfinance 读取历史财务数据。
- 用户点击 `Refresh Guidance`：
  - `DELETE /api/intelligence/hyperscaler/guidance/cache`
  - 后端调用 Gemini + Google Search grounding。
  - Gemini 搜索最新 2026 CapEx outlook。
  - 后端解析 JSON，写入 raw cache 和 view model cache。
  - 前端重新展示更新后的 2026 outlook。

Hyperscaler 的关键原则是：

1. **历史实际值用结构化财务数据，不用 LLM 猜。**
2. **当前年/未来年 outlook 才用 Gemini + Web Search。**
3. **LLM 原始回答不直接给前端，先归一化并缓存。**
4. **刷新是显式动作，不在页面每次加载时烧 API。**
5. **页面上明确标注数据来源，例如 2025 Actual / 2026 Outlook。**

Companies detail 的 CapEx Trend 可以复用这个设计思想。

---

### 10.3 新目标

把公司详情页的 `CapEx` tab 从现在的 “Breakdown + Anomalies” 改成：

1. **近 5 年 CapEx Trend 图**
   - 当年数据 + 前 4 年历史数据。
   - 例如当前年是 FY2026，则展示 FY2022、FY2023、FY2024、FY2025、FY2026。

2. **CapEx Anomaly Insight**
   - 不再基于文本里抽出来的一堆 dollar amount。
   - 改成基于近 5 年 CapEx trend 判断当年是否异常。
   - 如果当年 CapEx 明显高于/低于过去 4 年平均水平，则提示 spike / drop。

3. **保留 CapEx Breakdown，但定位要改清楚**
   - `CapEx Breakdown` 仍然可以保留为“CapEx 主题/用途提及次数”。
   - 它不是金额拆分图，不能和 CapEx Trend 混为一谈。
   - 页面上建议标注为 `Source: ChromaDB · SEC Filings · Mention-based`。

---

### 10.4 数据来源设计

近 5 年 CapEx Trend 的数据分两部分：

| 年份类型 | 数据来源 | 说明 |
|---|---|---|
| 前 4 年历史 CapEx | 已下载并整理好的财务 CapEx 分类表 | 直接读取结构化历史数据，作为真实 actual |
| 当年 CapEx | Web Search + Gemini/LLM extraction | 从 8-K、earnings calls、earnings release、annual meeting 等公开信息中找 management guidance 或 year-to-date / full-year outlook |

这里的“已下载并整理好的财务 CapEx 分类表”应作为历史数据的权威来源。后端应该优先从该表读取历史 CapEx，而不是重新从 ChromaDB 文本里正则抽金额。

当年数据如果已经有正式 10-K / 10-Q actual，则优先使用 actual；如果当前财年尚未结束，则使用 guidance / outlook，并在返回值里明确标注：

- `source_type: "actual"`：已披露真实值；
- `source_type: "guidance"`：管理层 guidance / outlook；
- `source_type: "estimated"`：只有区间或年化估算；
- `source_type: "missing"`：没有找到可靠数据。

---

### 10.5 后端建议结构

建议新增一个独立服务，而不是继续把逻辑塞进 `company_detail.py`：

```text
backend/analytics/company_capex_trend.py
```

职责：

1. 从财务 CapEx 分类表读取前 4 年历史 actual；
2. 获取当年 CapEx actual / guidance；
3. 组合成 5 年 trend；
4. 基于 trend 计算 anomaly；
5. 返回前端可直接渲染的数据结构。

建议保留现有接口路径，减少前端改动：

```text
GET /api/company/{company}/capex
```

但返回结构扩展为：

```json
{
  "company": "Flex",
  "capex_trend": [
    {
      "fiscal_year": "FY2022",
      "capex_millions": 520,
      "source_type": "actual",
      "source": "financial_capex_table"
    },
    {
      "fiscal_year": "FY2023",
      "capex_millions": 610,
      "source_type": "actual",
      "source": "financial_capex_table"
    },
    {
      "fiscal_year": "FY2024",
      "capex_millions": 680,
      "source_type": "actual",
      "source": "financial_capex_table"
    },
    {
      "fiscal_year": "FY2025",
      "capex_millions": 438,
      "source_type": "actual",
      "source": "financial_capex_table"
    },
    {
      "fiscal_year": "FY2026",
      "capex_millions": 500,
      "source_type": "guidance",
      "source": "earnings_call_or_8k"
    }
  ],
  "anomaly": {
    "has_anomaly": true,
    "direction": "spike",
    "severity": "medium",
    "current_year": "FY2026",
    "current_value_millions": 500,
    "historical_average_millions": 562,
    "pct_change_from_history": -11.0,
    "reason": "FY2026 CapEx guidance is 11.0% below the prior four-year average.",
    "basis": "Compared current-year CapEx against the previous four fiscal years."
  },
  "breakdown": {},
  "primary_focus": "technology_infrastructure",
  "sample_mentions": []
}
```

注意：上面的数字只是结构示例，不代表真实值。

---

### 10.6 当年 CapEx 的搜索逻辑

可以参考 Hyperscaler 的 Gemini 问题模板，但针对 EMS 公司改小范围：

```text
Search for the latest current fiscal year capital expenditure actuals or outlook for {company} ({ticker}).

Use reliable sources only:
- Form 8-K earnings release
- latest 10-Q or 10-K
- earnings call transcript
- investor presentation
- annual meeting / management guidance

Return JSON only:
{
  "company": "{company}",
  "ticker": "{ticker}",
  "fiscal_year": "FY2026",
  "capex_millions": null,
  "value_type": "actual | guidance | range_midpoint | ytd_annualized | missing",
  "range_low_millions": null,
  "range_high_millions": null,
  "source_title": "",
  "source_url": "",
  "source_date": "",
  "quote": "",
  "confidence": 0
}

Rules:
- Do not estimate if no CapEx value is mentioned.
- If management gives a range, return the midpoint in capex_millions and preserve range_low/range_high.
- If only year-to-date CapEx is available, mark value_type as "ytd_annualized" and lower confidence.
- Prefer full-year guidance over quarterly actuals.
- Prefer company filings and investor relations pages over third-party summaries.
```

当年数据的优先级建议：

1. 最新 10-K / 10-Q 中已经披露的 full-year actual；
2. 8-K earnings release 中明确的 CapEx actual 或 full-year guidance；
3. earnings call transcript 中 management 提到的 CapEx outlook；
4. investor presentation / annual meeting；
5. 第三方新闻只作为 fallback，并降低 confidence。

---

### 10.7 新的异常判断逻辑

旧逻辑：每个 period 的文本抽取金额 vs 全部 period 平均。

新逻辑：当前年 CapEx vs 前 4 年历史 actual。

建议算法：

```python
historical = [FY2022, FY2023, FY2024, FY2025]  # 只用 actual
current = FY2026  # actual 或 guidance

historical_avg = mean(historical)
pct_change = (current - historical_avg) / historical_avg

if abs(pct_change) >= 0.20:
    has_anomaly = True
    direction = "spike" if pct_change > 0 else "drop"
else:
    has_anomaly = False
```

如果历史值至少有 3 年，也可以同时计算 z-score：

```python
z_score = (current - historical_avg) / stdev(historical)
```

异常规则建议：

| 条件 | severity |
|---|---|
| `abs(pct_change) >= 50%` 或 `abs(z_score) >= 2.0` | high |
| `abs(pct_change) >= 20%` 或 `abs(z_score) >= 1.5` | medium |
| 低于以上阈值 | no anomaly |

如果当年值是 `guidance` 而不是 `actual`，则文案必须写清楚：

```text
FY2026 CapEx guidance is 28.4% above the previous four-year actual average.
This is based on management outlook, not final reported actuals.
```

---

### 10.8 前端展示设计

`CapEx` tab 建议改为四块：

1. **CapEx Trend + 衍生指标**（详见 10.8.1）
2. **CapEx Anomaly Insight**
3. **CapEx 占营收百分比 + 同比增长率**（详见 10.8.2）
4. **Investment Focus**（原 CapEx Breakdown，详见 10.11）

---

#### 10.8.1 CapEx Trend 图

- 柱状图展示近 5 年 CapEx 总额（单位：百万美元）。
- 前 4 年 actual 用统一颜色（如 blue-500）。
- 当前年 guidance/outlook 用高亮色（amber-400），并在柱顶加 badge `Guidance`。
- tooltip 显示：金额、fiscal year、source_type、数据来源名称。

图例：
```text
■ Actual  (financial CapEx table · yfinance)
■ Guidance  (earnings release / 8-K / earnings call)
```

前端数据派生：
```typescript
const capexTrendData = capexData?.capex_trend?.map((row) => ({
  year: row.fiscal_year,
  capex: row.capex_millions,
  sourceType: row.source_type,   // “actual” | “guidance” | “estimated” | “missing”
}));
```

---

#### 10.8.2 CapEx 占营收百分比 + 同比增长率

**为什么有意义：**

- **CapEx / Revenue（资本密集度）**：EMS 公司通常在 2–5% 之间。比例上升说明公司在加大产能或技术投入；比例下降可能代表收缩或提效。跨公司对比时，绝对金额意义有限，占营收比例才能反映战略倾向。
- **YoY Growth Rate（同比增长率）**：直观反映投资加速还是放缓，在判断异常时比绝对值更有参考价值。

**数据来源：**

- CapEx：来自 `capex_trend[].capex_millions`（已有）
- Revenue：来自 `financials` tab 已有的 `fiscal_years[year].revenue`（yfinance 拉取，已有）
- 两者时间轴对齐：按 fiscal year 对应（注意各公司 fiscal year 起止月份不同，见 `config.py`）

**前端计算（客户端派生，不需要后端新增字段）：**

```typescript
// capexTrend 来自 capexData.capex_trend
// financialsByYear 来自 financials.fiscal_years（key 为 fiscal year 标签，如 “FY2024”）

const capexWithRatios = capexTrendData?.map((row, idx, arr) => {
  const rev = financials?.fiscal_years?.[row.year]?.revenue;        // 单位：百万美元
  const capexPct = rev && rev > 0 ? (row.capex / rev) * 100 : null; // CapEx / Revenue %

  const prev = arr[idx - 1];
  const yoy = prev?.capex && prev.capex > 0
    ? ((row.capex - prev.capex) / prev.capex) * 100
    : null;                                                          // YoY %

  return { ...row, capexPct, yoy };
});
```

**前端展示方式：**

在 CapEx Trend 图下方，用一排小 KPI 卡片展示每年数据：

| FY | CapEx | CapEx/Revenue | YoY |
|----|-------|---------------|-----|
| FY2022 | $520M | 3.1% | — |
| FY2023 | $610M | 3.6% | ▲ +17.3% |
| FY2024 | $680M | 3.9% | ▲ +11.5% |
| FY2025 | $438M | 2.5% | ▼ -35.6% |
| FY2026 | $500M* | 2.8%* | ▲ +14.2% |

> `*` 标注当年为 guidance；Revenue 若为估算则加说明。

或者更简洁：在柱状图旁边加一条 CapEx/Revenue % 的折线（双轴图），直观对比绝对值与资本密集度的变化。

**注意事项：**

- 如果某年 Revenue 数据缺失（financials 里没有），该年 CapEx/Revenue 显示为 `—`，不报错。
- 当年如果是 guidance CapEx 但 actual Revenue 已披露（大多数情况），可以混合计算，但需加注释。
- YoY 第一年（最早年）固定显示 `—`，无法计算同比。

---

#### 10.8.3 CapEx Anomaly Insight

- 如果异常：显示 spike/drop、百分比、原因文字。
- 如果没有异常：显示 “No abnormal CapEx movement detected based on the 5-year trend.”
- 如果当前年是 guidance：在 insight 卡片上加 badge `Based on guidance`。

---

### 10.9 缓存策略

这个设计要和前面 company detail cache 保持一致：

- 页面第一次进入 CapEx tab 时，请求 `/api/company/{company}/capex`；
- 返回结果写入 `cache.capexData`；
- 离开再回来直接显示缓存；
- 只有点击 Refresh 时才重新请求；
- 如果后端要重新跑 Web/Gemini 搜索，建议只在 Refresh 或单独的 refresh endpoint 中触发，不要每次普通 GET 都触发。

建议后端也增加文件级或磁盘缓存：

```text
data/company_capex_trend/{ticker}_capex_trend_view_model.json
data/company_capex_trend/{ticker}_capex_trend_raw.json
```

普通 GET：

```text
GET /api/company/{company}/capex
```

优先读取 view model cache + 财务表历史数据。

手动刷新：

```text
DELETE /api/company/{company}/capex/cache
```

触发当年数据 Web/Gemini 搜索，更新 raw cache 和 view model cache。

这样和 Hyperscaler 的 `Refresh Guidance` 逻辑保持一致，也可以避免页面加载时频繁调用外部 API。

---

### 10.10 实现顺序建议

1. 确认”已下载并整理好的财务 CapEx 分类表”的具体文件/表结构，以及字段名。
2. 新增 `backend/analytics/company_capex_trend.py`。
3. 实现 `load_historical_capex(company, years=4)`：从财务 CapEx 分类表读取前 4 年 actual。
4. 实现 `fetch_current_year_capex_guidance(company)`：参考 Hyperscaler 的 Gemini + Search 逻辑获取当年 guidance。
5. 实现 `build_company_capex_trend(company)`：合并前 4 年 actual + 当年 actual/guidance。
6. 实现 `detect_capex_trend_anomaly(trend)`：基于近 5 年趋势判断异常。
7. 扩展 `GET /api/company/{company}/capex` 返回 `capex_trend` 和新的 `anomaly` 字段，同时在 `breakdown` 每个类目下补充 `sample_quotes[]`（见 10.11）。
8. 前端 `CapEx` tab 新增 `CapEx Trend` 图 + 衍生指标卡片（10.8.1 + 10.8.2）。
9. 前端 `CapEx Anomalies` 改为读取新的 `anomaly` 字段，而不是旧的 `anomalies[]` 文本抽取结果。
10. 前端 `CapEx Breakdown` 改为 `Investment Focus` 展示方式（见 10.11）。

---

## 11. CapEx Breakdown 改为”Investment Focus”

### 11.1 问题诊断

当前 `CapEx Breakdown` 的实际含义是：在 SEC 文件里，和 CapEx 相关的段落中，某些关键词出现了多少次。后端返回：

```json
“breakdown”: {
  “data_center”:   { “mentions”: 15 },
  “facility”:      { “mentions”: 8 },
  “machinery”:     { “mentions”: 12 },
  “automation”:    { “mentions”: 6 }
}
```

前端用饼图或柱图展示这些数字，样式和金额拆分图一模一样。**用户会以为这是 CapEx 的金额分配，实际上只是提及次数。** 这是误导性设计。

---

### 11.2 改造目标

把这个模块从”伪金额拆分图”改成”定性投资重点展示”，清楚传达：

> 这些是从 SEC 文件（10-K / 10-Q / 8-K）里提取的投资主题，展示公司在 CapEx 相关讨论中最常提到哪些领域，不是实际金额的分配。

---

### 11.3 后端改动

在现有 `breakdown` 每个类目下，新增 `sample_quotes` 字段（最多 3 条），直接返回文本原文，让用户能看到每个主题对应的真实文字，而不仅仅是一个数字。

**修改位置：** `backend/api/routes/company_detail.py` 中构建 breakdown 的逻辑。

**改动前返回结构：**
```json
“data_center”: { “mentions”: 15 }
```

**改动后返回结构：**
```json
“data_center”: {
  “mentions”: 15,
  “sample_quotes”: [
    “Capital expenditures related to data center infrastructure increased by $42M in FY2024...”,
    “We continue to invest in hyperscale data center manufacturing capabilities...”,
    “Data center capacity expansion drove approximately 30% of our total CapEx spend...”
  ]
}
```

`sample_quotes` 从 ChromaDB 已有的文档中抽取，按相关性排序取前 3 条，截断到 200 字以内。这不需要新的数据源，直接用现有 RAG 检索即可。

---

### 11.4 前端改动

**模块标题改为：**
```
Investment Focus  ·  Source: SEC Filings · Keyword Frequency
```

**移除原有饼图/柱图，改为”主题卡片列表”：**

每个类目显示为一张卡片，包含：
- 类目名称（如 Data Center、Facility Expansion）
- 提及次数（如 `15 mentions`）
- 一个横向进度条（相对于所有类目的最大提及次数做归一化，仅表示相对频率，不代表金额占比）
- 折叠展示的原文 quotes（默认折叠，点击展开）

**示例 UI 结构（伪代码）：**

```tsx
<div className=”space-y-3”>
  {Object.entries(breakdown).map(([category, data]) => (
    <div key={category} className=”p-4 rounded-xl border border-slate-200 bg-slate-50”>
      {/* 标题行 */}
      <div className=”flex items-center justify-between mb-2”>
        <span className=”font-semibold text-slate-800 capitalize”>
          {category.replace(/_/g, ' ')}
        </span>
        <Badge className=”bg-blue-100 text-blue-700”>
          {data.mentions} mentions
        </Badge>
      </div>

      {/* 进度条（仅表示相对频率） */}
      <div className=”h-1.5 bg-slate-200 rounded-full mb-3”>
        <div
          className=”h-1.5 bg-blue-400 rounded-full”
          style={{ width: `${(data.mentions / maxMentions) * 100}%` }}
        />
      </div>

      {/* 原文 quotes（折叠展开） */}
      {data.sample_quotes?.length > 0 && (
        <details className=”text-sm text-slate-600”>
          <summary className=”cursor-pointer text-blue-500 hover:underline”>
            View quotes from filings
          </summary>
          <ul className=”mt-2 space-y-1.5”>
            {data.sample_quotes.map((q, i) => (
              <li key={i} className=”pl-3 border-l-2 border-blue-200 italic”>
                “{q}”
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  ))}
</div>

{/* 底部免责说明 */}
<p className=”text-xs text-slate-400 mt-4”>
  Investment Focus is based on keyword frequency analysis of SEC filings (10-K, 10-Q, 8-K).
  It reflects how often each topic is discussed in CapEx-related contexts — not the actual dollar allocation.
</p>
```

---

### 11.5 关键措辞变化

| 位置 | 改动前 | 改动后 |
|------|--------|--------|
| 模块标题 | `CapEx Breakdown` | `Investment Focus` |
| 图表类型 | 饼图 / 柱图（看起来像金额占比） | 卡片列表 + 进度条（明确是频率） |
| 进度条标签 | 无，让用户自行理解 | 鼠标 hover 显示 `Relative mention frequency` |
| 底部说明 | 无 | `Based on keyword frequency · not dollar allocation` |
| 数值单位 | 无单位（让人误以为是百分比） | 明确标 `X mentions` |
| 原文支撑 | 无 | 每个类目展示最多 3 条原文 quotes |

---

### 11.6 不需要改动的内容

- 后端 ChromaDB 搜索逻辑不需要改，只需在构建 breakdown 时顺带提取 quotes。
- 接口路径 `GET /api/company/{company}/capex` 不变。
- 返回结构向后兼容：`mentions` 字段依然存在，只是新增了 `sample_quotes`。
- 如果 `sample_quotes` 为空（搜索无结果），前端直接不显示 quotes 区域，不报错。
