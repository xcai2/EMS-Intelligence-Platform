# News 后端说明

最后更新：2026-03-28（America/Los_Angeles）

## 1）后端模块结构

- `backend/main.py`
  - 应用入口，负责挂载 News 路由。
- `backend/news/routes.py`
  - 主 News 接口（`/api/news/*`）。
- `backend/news/service.py`
  - 主 News 服务（采集、标准化、过滤、去重、缓存）。
- `backend/news/sources.py`
  - 官方来源配置与回退内容。
- `backend/news/filtering.py`
  - 过滤常量（AI 词、屏蔽域名、噪声词）。
- `backend/news/normalizer.py`
  - 域名到来源名称映射。
- `backend/news/aggregator.py`
  - 旧版聚合器，供 `advanced_data` 的 `/api/news-aggregator/*` 使用。

## 2）主 News 接口

定义于 `backend/news/routes.py`：

- `/api/news/company/{ticker}`（`count` 默认 `10`，可选 `category`、`force_refresh`）
- `/api/news/industry`（`count` 默认 `15`，可选 `force_refresh`）
- `/api/news/comparative`（可选 `force_refresh`）
- `/api/news/all`（`count_per_company` 默认 `3`，可选 `force_refresh`）

## 3）主服务数据源组合（`backend/news/service.py`）

公司新闻（`get_company_news`）来源为：

1. 官方公司来源管道
   - 公司 RSS（如已配置）
   - 按公司域名的 Google News RSS 查询
   - 可选 HTML 链接扫描（可按公司关闭）
   - 可选 Public.com 看板（目前 FLEX 使用）
2. Brave Web Search（`search_web_with_diagnostics`）
3. Google News RSS 查询扩展
4. live 结果不足时使用静态回退

### 职责边界（抓取 vs 筛选）

- 后端这一层重点是：尽量收全、标准化、去重、公司相关性检查、提供排序信号。
- 更严格的展示筛选会在前端 `NewsPageFeature.tsx` 再做一层。
- 这样可以保持后端抓取覆盖度，同时在 UI 侧控制展示精度。

## 4）各公司官方来源

配置位置：`backend/news/sources.py` 的 `OFFICIAL_COMPANY_SOURCES`。

### FLEX
- `https://investors.flex.com/rss/pressrelease.aspx`
- `https://investors.flex.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000866374`
- `https://investors.flex.com/rss/event.aspx`
- 另外使用 `flex.com` 官方路径和 Public 看板：
  - `https://public.com/stocks/flex/news`

### JBL（Jabil）
- `https://investors.jabil.com/rss/pressrelease.aspx`
- `https://investors.jabil.com/rss/event.aspx`
- `https://investors.jabil.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000898293`
- `disable_html_scan = True`

### CLS（Celestica）
- `https://www.globenewswire.com/rssfeed/organization/vlXa3ip4O0JMbJucCiUeUg==`
- `disable_html_scan = True`

### SANM（Sanmina）
- `https://ir.sanmina.com/rss/pressrelease.aspx`
- `https://ir.sanmina.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000897723`
- `https://ir.sanmina.com/rss/event.aspx`

### BHE（Benchmark）
- 暂无专用 RSS
- 使用官方路径 + 搜索混合来源

## 5）搜索与聚合来源

### Brave Search
- 入口：`backend/rag/web_search.py`
- 主 service 和 legacy aggregator 都会调用
- API key 仍由 backend `.env` 提供

### Google News RSS
- 主 service 直接查询
- 会尝试解析原始来源并解析跳转 URL

## 6）Legacy Aggregator 接口（仍在使用）

由 `backend/api/routes/advanced_data.py` 暴露，实现位于 `backend/news/aggregator.py`：

- `/api/news-aggregator/company/{company}`
- `/api/news-aggregator/industry`
- `/api/news-aggregator/all-companies`
- `/api/news-aggregator/trending`
- `/api/news-aggregator/categories`
- `/api/news-aggregator/feeds`

## 7）缓存行为（与代码一致）

### 主 News service（`backend/news/service.py`）
- 运行时内存缓存
- 持久化文件：`data/news_runtime_cache.json`
- 普通请求：命中缓存直接返回
- `force_refresh=true`：跳过缓存并重抓
- 重启后端：会加载持久化缓存文件

### Legacy aggregator（`backend/news/aggregator.py`）
- 仅内存缓存（TTL 900 秒）
- 不落盘
