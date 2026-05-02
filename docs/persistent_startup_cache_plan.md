# App 重启后优先读取本地缓存的改造方案

## 目标

现在的问题是：关闭前端进程、后端进程后，再重新运行 App，进入页面并点击左侧 tab，例如 News、Companies、Hyperscaler、Map、Analyst View，很多页面仍然会先 loading 一段时间。

目标是改成：

1. 页面打开时，**先立即显示上一次保存的本地缓存数据**；
2. 普通页面加载不主动刷新外部数据；
3. 只有用户点击页面上的 `Refresh` / `Refresh Guidance` / `Sync` 按钮时，才重新抓取或重新计算；
4. 如果本地缓存不存在，才显示 loading；
5. 如果后端暂时没起来，但前端 localStorage / IndexedDB 里有旧数据，也可以先显示旧数据。

这个方案是可行的，但需要区分两种缓存：

| 缓存类型 | 当前状态 | 是否能跨进程重启保留 |
|---|---|---|
| React state / module-level cache | Companies、Company Detail 已有一部分 | 否，前端 dev server 或浏览器刷新后会丢 |
| `sessionStorage` | Analyst View 有一部分 | 部分保留，但 TTL 很短，关 tab 会丢 |
| `localStorage` | 少量页面只保存状态/keyword | 可以跨前端/后端重启保留 |
| 后端内存 `SimpleCache` | analytics、hyperscaler financials 等 | 否，后端进程重启后会丢 |
| 后端磁盘 JSON / SQLite | News、Hyperscaler guidance、Financial cache、Map facilities 等 | 可以跨后端重启保留 |

所以整体策略应该是：**前端做持久化页面缓存，后端 GET 接口尽量改成 cache-first，Refresh 接口才触发真实刷新。**

---

## 1. 为什么现在重启后还会 loading

### 1.1 Companies

`frontend/src/app/companies/page.tsx` 现在有 module-level cache：

```ts
const _cache = { ... }
let _cachePopulated = false;
```

这个缓存只能在 Next.js 页面跳转时保留。只要前端 dev server 重启、浏览器刷新、页面重新加载，module-level cache 就没了。

所以它解决的是：

> 在 App 内部从 Companies 跳走再回来，不重新 loading。

但没有解决：

> 关闭前端进程后重新打开 App，不 loading。

### 1.2 Company Detail

`frontend/src/app/companies/[company]/page.tsx` 也用了 module-level cache：

```ts
const _detailCache: Record<string, DetailCache> = {};
```

同样只能在当前 JS runtime 里保留，不能跨前端重启。

### 1.3 News

News 后端本身已经有比较好的磁盘缓存：

```text
data/news_cache/company_{TICKER}.json
```

普通请求：

```text
GET /api/news/company/{ticker}
```

应该是读磁盘缓存。

强制刷新：

```text
GET /api/news/company/{ticker}?force_refresh=true
```

才重新抓新闻。

但前端 `NewsPageFeature.tsx` 页面加载时仍然会先 `setLoading(true)`，然后等所有 company news 请求回来。因此即使后端只是读磁盘缓存，前端也会看到 loading。

### 1.4 Hyperscaler

Hyperscaler guidance 后端已经是正确方向：

```text
data/hyperscaler/big5_capex_view_model.json
data/hyperscaler/big5_capex_api_raw.json
```

普通请求：

```text
GET /api/intelligence/big5-capex
```

只读 view model cache。

刷新：

```text
DELETE /api/intelligence/hyperscaler/guidance/cache
```

才调用 Gemini。

但前端页面仍然需要等 `GET /big5-capex` 和 `GET /hyperscaler/all/financials` 返回，所以页面刚打开还是会 loading。

### 1.5 Analyst View

Analyst View 有 `sessionStorage`：

```ts
const CACHE_KEY = "analyst_view_intel_cache";
const CACHE_TTL_MS = 5 * 60 * 1000;
```

问题是：

1. 用的是 `sessionStorage`，不是 `localStorage`；
2. TTL 只有 5 分钟；
3. 超过 5 分钟就会重新请求；
4. 这不符合“只要不按 Refresh，就一直用旧缓存”的设计。

### 1.6 Map

Map 后端接口本身读本地 JSON：

```text
GET /api/geographic/facilities
GET /api/geographic/compare
```

刷新才调用：

```text
POST /api/geographic/refresh
```

但是前端 `map/page.tsx` 的 `loadFromCache()` 仍然会先 `setLoading(true)`，然后请求后端。因此重启后仍然会看到 loading。

---

## 2. 总体改造原则

### 原则 1：页面加载先读前端持久缓存

每个主要页面都应该先从浏览器本地缓存读取上次展示的数据。

建议：

- 普通大小的数据用 `localStorage`；
- News 这种可能比较大的数据，用 `IndexedDB` 更稳；
- 如果先用最小改动，也可以先用 `localStorage`，但要注意浏览器 5MB 左右限制。

页面加载流程：

```text
进入页面
→ readPersistentCache(pageKey)
→ 如果有缓存：立即 setState，loading=false
→ 如果没有缓存：显示 loading，请求后端
→ 后端返回后：setState + writePersistentCache(pageKey)
```

### 原则 2：普通 GET 必须 cache-first

普通页面加载时调用的后端 GET 接口不应该主动触发外部 API、scraper、LLM 或昂贵计算。

普通 GET 的职责：

```text
读本地 JSON / SQLite / ChromaDB / 已有文件
返回已有结果
```

Refresh 的职责：

```text
重新抓取 / 重新计算 / 调 LLM / 调 Brave or Gemini
写入本地缓存
返回新结果
```

### 原则 3：Refresh 才覆盖缓存

用户不点击 Refresh，就一直显示上次缓存。

如果 Refresh 失败：

- 不清空旧缓存；
- 页面继续显示旧数据；
- 显示 `Refresh failed, showing cached data` 之类提示。

### 原则 4：前端不要因为 revalidate 而阻塞首屏

如果以后想加“后台静默检查”，也不能影响首屏。

推荐流程：

```text
显示旧缓存
→ 可选：后台 silent fetch 后端 cache-only endpoint
→ 如果返回不同数据，再无感更新
```

但按当前需求，最简单是：**不按 Refresh 就不重新拉取。**

---

## 3. 建议新增前端通用缓存工具

新增文件：

```text
frontend/src/lib/persistentCache.ts
```

建议 API：

```ts
type CacheEnvelope<T> = {
  version: number;
  savedAt: string;
  payload: T;
};

export function readPersistentCache<T>(key: string, version = 1): T | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEnvelope<T>;
    if (parsed.version !== version) return null;
    return parsed.payload;
  } catch {
    return null;
  }
}

export function writePersistentCache<T>(key: string, payload: T, version = 1) {
  try {
    const envelope: CacheEnvelope<T> = {
      version,
      savedAt: new Date().toISOString(),
      payload,
    };
    localStorage.setItem(key, JSON.stringify(envelope));
  } catch {
    // localStorage 可能满了；不要影响页面主流程
  }
}

export function clearPersistentCache(key: string) {
  try {
    localStorage.removeItem(key);
  } catch {}
}
```

命名建议：

```text
cache:news:v1
cache:companies:index:v1
cache:company-detail:{company}:v1
cache:hyperscaler:v1
cache:map:v1
cache:analyst-view:v1
```

注意：这里**不建议设置 TTL**，因为当前产品设计是“除非用户按 Refresh，否则一直使用旧缓存”。

---

## 4. 各页面改造方案

### 4.1 News

目标文件：

```text
frontend/src/features/news/NewsPageFeature.tsx
```

当前页面加载：

```ts
useEffect(() => {
  loadCompanies().then(() => fetchAllNews(true));
}, []);
```

问题：每次进页面都 `fetchAllNews(true)`，所以一定会 loading。

建议改成：

1. 页面 mount 时先读：

```text
cache:news:v1
```

2. 如果有缓存：

```text
setRegisteredCompanies(...)
setCompanyNews(...)
setCompanyTopNews(...)
setCompanyWeeklySummary(...)
setWeeklyTopNewsSummary(...)
setAllTrending(...)
setLoading(false)
```

3. 不自动调用 `fetchAllNews(true)`。

4. 点击 Refresh 时才：

```ts
refreshNews()
→ fetchAllNews(false, true)
→ writePersistentCache("cache:news:v1", currentNewsState)
```

后端现状：News 已经有磁盘 cache，基本符合设计。

需要注意：News 数据可能比较大。如果 localStorage 超限，可以改 IndexedDB。

---

### 4.2 Companies

目标文件：

```text
frontend/src/app/companies/page.tsx
```

当前是 module-level cache。建议保留 module-level cache，同时加 localStorage：

页面初始化：

```ts
const persisted = readPersistentCache<CompaniesPageCache>("cache:companies:index:v1");

if (persisted) {
  初始化 state 使用 persisted；
  _cache = persisted；
  _cachePopulated = true；
  loading = false；
}
```

首次没有 persisted cache 时，才调用 `fetchData()`。

`fetchData()` 成功后写入：

```text
cache:companies:index:v1
```

`refreshData()` 成功后也写入同一个 cache。

建议缓存结构：

```ts
type CompaniesPageCache = {
  companies: Company[];
  analytics: Record<string, AnalyticsData>;
  capexData: CapExMention[];
  aiData: AIInvestmentMention[];
  trends: any;
  classification: any;
  anomalies: any;
};
```

后端注意：

- `/api/companies` 主要读 config + ChromaDB stats，通常可以保留；
- `/api/analytics/classification`、`/api/analytics/trends`、`/api/analytics/anomalies` 当前多依赖内存 cache 和 ChromaDB 计算，后端重启后会重新算；
- 如果要彻底快，需要给这些 analytics endpoints 加后端 view model cache。

最小可行版本：前端 localStorage 先显示旧数据，Refresh 才重新请求这些接口。

---

### 4.3 Company Detail

目标文件：

```text
frontend/src/app/companies/[company]/page.tsx
```

当前也是 module-level cache：

```ts
const _detailCache: Record<string, DetailCache> = {};
```

建议变成：

```text
cache:company-detail:flex:v1
cache:company-detail:jabil:v1
cache:company-detail:celestica:v1
...
```

页面加载：

1. 先读该公司的 persistent cache；
2. 有缓存就立即显示 overview 和已访问过的 tab；
3. 没缓存才请求 overview；
4. 切 tab 时，如果 localStorage 里已有该 tab 数据，就直接显示；
5. 点击 Refresh 才重新请求已访问过的 tab。

这个和当前 `company_detail_cache_plan.md` 的方向一致，只是把 module-level cache 升级为 persistent cache。

---

### 4.4 Hyperscaler

目标文件：

```text
frontend/src/features/hyperscaler/HyperscalerPageFeature.tsx
```

后端已经有：

```text
data/hyperscaler/big5_capex_view_model.json
```

但前端仍然每次 mount 都请求：

```ts
fetchData();
fetchHistoricalData();
```

建议前端缓存：

```text
cache:hyperscaler:guidance:v1
cache:hyperscaler:historical:v1
```

页面加载：

1. 先读 localStorage；
2. 如果有 guidance cache，立即显示 `AI Investment Details`；
3. 如果有 historical cache，立即显示 historical chart；
4. 不自动 refresh Gemini；
5. 点击 `Refresh Guidance` 才调用：

```text
DELETE /api/intelligence/hyperscaler/guidance/cache
```

6. Refresh 成功后写入 localStorage。

后端注意：

- `/api/intelligence/big5-capex` 已经是 cache-first；
- `/api/intelligence/hyperscaler/all/financials` 目前使用后端内存 `SimpleCache` + yfinance，后端重启后会重新抓；
- 建议给 hyperscaler historical financials 也加磁盘 cache，例如：

```text
data/hyperscaler/hyperscaler_financials_view_model.json
```

普通 GET 读磁盘；Refresh/DELETE 才重新抓 yfinance。

---

### 4.5 Map

目标文件：

```text
frontend/src/app/map/page.tsx
```

后端已经是本地 JSON cache：

```text
GET /api/geographic/facilities
GET /api/geographic/compare
POST /api/geographic/refresh
```

建议前端缓存：

```text
cache:map:v1
```

页面加载：

1. 先读 localStorage；
2. 有缓存就直接 set `facilities`、`comparison`、`lastScraped`、`dataSources`；
3. 不显示 loading；
4. 没缓存才调用 `loadFromCache()`；
5. 点击 Refresh 才调用 `POST /api/geographic/refresh`；
6. Refresh 成功后写入 localStorage。

---

### 4.6 Analyst View

目标文件：

```text
frontend/src/features/analyst-view/AnalystViewPageFeature.tsx
```

当前问题：

```ts
sessionStorage
CACHE_TTL_MS = 5 * 60 * 1000
```

建议改成：

```ts
localStorage
不设置 TTL
```

普通进入页面：

```text
读 cache:analyst-view:v1
有则立即显示
没有才 GET /api/analyst-view/company-intel
```

点击 Refresh：

```text
GET /api/analyst-view/company-intel?force=true
```

成功后写入 localStorage。

其他 Analyst View 子组件也要统一：

- `RatingsFeed`
- `CoverageMap`
- `WeeklyThemes`
- `ConsensusView`
- `AnalystCards`
- `EarningsCalendar`

这些组件如果各自请求接口，也需要各自的 persistent cache key。否则父页面出来了，子卡片仍会 loading。

---

## 5. 后端需要补的 cache-first 设计

前端 localStorage 可以解决“首屏马上显示旧数据”。但如果用户第一次打开某页面，本地没有前端缓存，仍然要靠后端快。

建议把重页面的后端结果也做成 view model JSON。

### 5.1 Analytics view model

建议新增：

```text
data/view_cache/analytics_classification.json
data/view_cache/analytics_trends.json
data/view_cache/analytics_anomalies.json
data/view_cache/sentiment_compare.json
data/view_cache/geographic_compare.json
```

普通 GET：

```text
如果 view_cache 文件存在，直接返回
如果不存在，再计算一次并写入
```

Refresh：

```text
POST /api/cache/refresh/analytics
```

或页面已有 Refresh 按钮直接调用对应 force endpoint。

### 5.2 Companies index view model

建议新增：

```text
data/view_cache/companies_index.json
```

保存 Companies 页面需要的聚合数据：

```json
{
  "companies": [],
  "analytics": {},
  "classification": {},
  "trends": {},
  "anomalies": {},
  "capexData": [],
  "aiData": [],
  "saved_at": "2026-05-02T..."
}
```

这样 Companies 页面可以从一个接口拿完整缓存：

```text
GET /api/view-cache/companies
POST /api/view-cache/companies/refresh
```

这是更干净的版本；最小版本也可以先只做前端 localStorage。

### 5.3 Company detail view model

建议新增：

```text
data/view_cache/company_detail/FLEX.json
data/view_cache/company_detail/JBL.json
...
```

保存：

```json
{
  "overview": {},
  "filings": {},
  "financials": {},
  "capexData": {},
  "hiring": {},
  "saved_at": "..."
}
```

### 5.4 Hyperscaler financials 磁盘缓存

目前 guidance 有磁盘 cache，但 historical financials 还是内存 cache + yfinance。

建议新增：

```text
data/hyperscaler/hyperscaler_financials_view_model.json
```

普通 GET 读这个文件；Refresh 才重新抓 yfinance。

---

## 6. 推荐实现顺序

### 第一阶段：只改前端，最快见效

1. 新增 `frontend/src/lib/persistentCache.ts`
2. News 页面加 `cache:news:v1`
3. Companies 页面加 `cache:companies:index:v1`
4. Company Detail 页面加 `cache:company-detail:{company}:v1`
5. Hyperscaler 页面加 `cache:hyperscaler:guidance:v1` 和 `cache:hyperscaler:historical:v1`
6. Map 页面加 `cache:map:v1`
7. Analyst View 从 `sessionStorage + 5min TTL` 改成 `localStorage + no TTL`

第一阶段效果：

- 只要用户曾经打开过页面，之后重启前端/后端再打开，页面可以先显示旧数据；
- 后端还没起来时，也可以显示前端缓存；
- Refresh 按钮仍然可以更新。

### 第二阶段：后端 view model cache

1. 新增 `backend/core/view_cache.py`
2. 给 analytics / companies / company detail 聚合数据写磁盘 JSON
3. 普通 GET 先读 view model
4. Refresh endpoint 才重新计算并覆盖 view model

第二阶段效果：

- 即使浏览器 localStorage 没有数据，只要后端磁盘 cache 在，页面也能很快返回；
- 后端重启后不用重新跑昂贵计算。

### 第三阶段：统一 Cache Status

加一个接口：

```text
GET /api/cache/status
```

返回：

```json
{
  "news": {"exists": true, "saved_at": "..."},
  "companies": {"exists": true, "saved_at": "..."},
  "hyperscaler": {"exists": true, "saved_at": "..."},
  "map": {"exists": true, "saved_at": "..."},
  "analyst_view": {"exists": true, "saved_at": "..."}
}
```

Settings 页面可以显示缓存状态，也可以提供：

```text
Clear local cache
Clear backend view cache
Refresh all cached data
```

---

## 7. 哪些情况不可避免仍会 loading

这个设计可行，但以下情况仍然必须 loading：

1. 用户第一次打开某页面，从来没有前端缓存；
2. 后端磁盘 cache 文件也不存在；
3. 浏览器 localStorage / IndexedDB 被清空；
4. 数据结构版本升级，旧 cache version 被拒绝；
5. 页面需要的资产本身很大，浏览器解析 localStorage 也需要一点时间；
6. 用户主动点击 Refresh。

也就是说：**只要至少有一份可用缓存，就可以避免每次重启都 loading。没有缓存时，第一次 loading 是合理的。**

---

## 8. 最终建议

这个需求是可行的，而且很适合当前项目。

建议先做最小可行版本：

1. 前端统一加 persistent cache；
2. 页面启动先读 localStorage；
3. 不自动刷新；
4. Refresh 按钮才请求 force refresh；
5. 成功后覆盖 localStorage。

后端 view model cache 可以第二阶段做。因为从用户体验上看，前端 persistent cache 已经能解决“重启 App 后先看到旧数据”的核心问题。

