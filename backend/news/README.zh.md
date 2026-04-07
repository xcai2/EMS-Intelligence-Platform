# News 模块后端架构与实现说明

最后更新：2026-04-03（America/Los_Angeles）

## 1. 文档目的

这份文档用于完整说明 `backend/news` 这套 News 后端模块目前的实现方式，帮助新同学或后续维护者快速回答下面这些问题：

1. 这个模块整体负责什么功能。
2. 目录里每个文件分别负责什么。
3. 一次新闻请求从前端到后端、再到外部数据源，实际是怎么流转的。
4. 公司新闻、行业新闻、对比新闻三条主链路各自的抓取顺序是什么。
5. 这套实现用了什么设计原则、做了哪些降级和缓存处理。
6. 前端当前是如何调用后端、如何和后端协同工作的。
7. `backend/news` 目录里哪部分是当前主链路，哪部分是历史兼容逻辑。

这份文档重点讲“真实代码当前在做什么”，而不是理想状态下它应该做什么。

---

## 2. 模块定位

`backend/news` 是项目里专门负责“新闻采集、标准化、筛选、缓存、对外提供 API”的领域模块。

它当前主要服务于以下几类能力：

1. 按公司获取新闻：`/api/news/company/{ticker}`
2. 获取行业新闻：`/api/news/industry`
3. 获取对比新闻：`/api/news/comparative`
4. 获取全部跟踪公司新闻：`/api/news/all`

这套模块的目标不是做“全文新闻抓取器”，而是做一个更偏“竞争情报新闻聚合器”：

1. 尽量从多个来源抓到候选新闻。
2. 尽量把来源不统一的数据格式，归一成一套统一结构。
3. 用轻量规则判断这些新闻是否和我们跟踪的公司或行业主题有关。
4. 提供给前端可以直接消费的结构化结果。
5. 附带诊断信息，方便调试为什么某次新闻多、少、空、重复或来源异常。

---

## 3. 设计原则

当前这套实现的核心原则可以概括为下面几条：

### 3.1 先尽量收全，再逐层过滤

后端不会一开始就把条件卡得特别死，而是先从多个来源拉取候选项，再做：

1. 标准化
2. 去重
3. 公司相关性筛选
4. 行业主题筛选
5. 排序

这样做的好处是覆盖率更高，不容易因为某个来源格式变化导致整类新闻被完全漏掉。

### 3.2 官方源优先，但不只依赖官方源

对公司新闻来说，官方源最稳定、噪声最少，所以优先尝试：

1. 公司官方 RSS
2. 公司官网新闻页
3. 公司域名范围内的 Google News RSS
4. 某些公司的 Public.com 新闻板

但官方源不一定全，所以还会补：

1. Brave Search
2. Google News RSS 的公司搜索查询

### 3.3 后端做“广覆盖 + 基础可信筛选”，前端做“更严格展示筛选”

这点非常重要。

当前后端负责：

1. 多源抓取
2. 统一字段
3. 基础去重
4. 基础相关性判断
5. 基础排序信号
6. 缓存与诊断

当前前端还会再做一层：

1. 更严格的公司匹配
2. 相似标题去重
3. 热度和优先级排序
4. blocked domain 的跳转兜底

也就是说，后端返回的是“已经清洗过的一批候选结果”，但前端在展示前还会做第二次收敛。

### 3.4 出问题时优先降级，不优先报错

这套模块里很多逻辑都倾向于：

1. 某个源失败，不让整个请求失败。
2. 某个查询失败，只记录 diagnostics。
3. 结果太少时，使用 fallback 静态新闻。
4. 缓存不存在时，返回带 `refresh_required` 的空响应，而不是直接抛异常。

因此它更偏“稳态服务”而不是“全有或全无”的严格抓取器。

---

## 4. 目录结构总览

下面是 `backend/news` 目录的核心文件和职责：

```text
backend/news/
├── __init__.py
├── routes.py
├── service.py
├── company_news_service.py
├── industry_news_service.py
├── comparative_news_service.py
├── source_fetchers.py
├── source_parsing.py
├── news_filters.py
├── news_filter_policies.py
├── filtering.py
├── query_helpers.py
├── content_signals.py
├── normalizer.py
├── sources.py
├── aggregator.py
└── README.zh.md
```

### 每个文件的作用

#### `__init__.py`

包初始化文件，没有业务逻辑，只是标记 `backend/news` 是一个 Python package。

#### `routes.py`

News 模块的 API 入口层。

负责：

1. 定义 `/api/news/*` 路由。
2. 解析请求参数。
3. 校验公司 ticker 是否存在。
4. 通过 `Depends(get_news_feed)` 注入单例 `NewsFeed`。
5. 把请求转交给 service 层。

它本身不做抓取，不做过滤，不做缓存持久化。

#### `service.py`

News 模块的总控层，核心类是 `NewsFeed`。

负责：

1. 管理主链路缓存。
2. 加载和写回 `data/news_cache/*.json`。
3. 管理 aggregate cache，例如 `/news/all`。
4. 管理 Google News redirect URL 缓存。
5. 统一暴露三个主能力：
   - `get_company_news`
   - `get_industry_news`
   - `get_competitor_comparison_news`
6. 把实际业务分发给三个专门的 service 文件。

可以把它理解成“News 模块的 service facade + cache manager”。

#### `company_news_service.py`

公司新闻主链路的编排层，是当前 News 模块最核心的业务文件。

负责：

1. 为公司生成搜索查询。
2. 控制不同来源的抓取顺序。
3. 控制每类来源的候选条数上限。
4. 并发执行 Brave / Google RSS 的 query fan-out。
5. 把抓来的数据标准化后合并。
6. 去重。
7. 做公司相关性过滤。
8. 在结果不足时追加 fallback。
9. 构造带 diagnostics 的最终返回 payload。

如果你只想理解“公司新闻为什么会出来这些条目”，这个文件是第一优先级。

#### `industry_news_service.py`

行业新闻主链路。

负责：

1. 预设行业主题搜索词。
2. 对每个 query 同时调用 Brave Search 和 Google News RSS。
3. 归一化结果。
4. 通过行业主题规则筛选。
5. 当 live 结果为空时使用行业 fallback。

#### `comparative_news_service.py`

多公司对比新闻主链路。

负责：

1. 生成多公司比较 query。
2. 抓取 Brave Search + Google News RSS。
3. 找出同时提到两家及以上跟踪公司的新闻。
4. 构造适合 comparative view 的结构化数据。

#### `source_fetchers.py`

低层抓取层，是 News 模块和外部源之间的主要桥梁。

负责：

1. 发 HTTP 请求。
2. 拉公司 RSS。
3. 拉 Google News RSS。
4. 解析 Google News RSS 的 XML。
5. 扫公司官网新闻页。
6. 读取 Flex sitemap。
7. 读取 Public.com 公司新闻板。
8. 解析 Google News redirect。
9. 产出源级 diagnostics。

它主要解决“怎么抓到原始候选新闻”。

#### `source_parsing.py`

来源解析与基础文本解析工具层。

负责：

1. HTML 清洗。
2. 提取图片 URL。
3. 提取 Google News description 里的真实外链。
4. 识别 Google 自有域名。
5. 从标题尾巴中提取 source。
6. 从 Google title / description 中提取 source。
7. 从 URL 推断 source。
8. 统一 source candidate 的规范化逻辑。

它主要解决“来源名到底应该叫什么”。

#### `news_filters.py`

通用标准化和轻量过滤层。

负责：

1. 统一不同来源的字段结构。
2. 计算 `categories`。
3. 计算 `relevance_score`。
4. 做 paywall / blocked domain 过滤。
5. 做噪声词过滤。
6. 基于 URL + title 做基础去重。

它主要解决“原始结果怎么变成统一的新闻对象”。

#### `news_filter_policies.py`

按 feed 类型区分的“业务规则层”。

负责：

1. 公司新闻的后置分类筛选。
2. 公司相关性判断。
3. 行业新闻主题判断。
4. comparative news 的多公司判定。

它主要解决“哪些候选新闻应该被保留”。

#### `filtering.py`

纯常量文件。

负责维护：

1. 分类关键词 `CATEGORIES`
2. AI 主题词
3. CapEx 主题词
4. blocked / paywall 域名
5. 噪声词

#### `query_helpers.py`

查询构造辅助层。

负责：

1. 提取公司别名。
2. 构造 alias query。
3. 构造 site-scoped query。
4. 提供公司短名映射。

#### `content_signals.py`

轻量内容信号文件。

负责：

1. 判断一段文本是否提到被跟踪公司。
2. 判断是否 AI / data center 相关。

#### `normalizer.py`

公共归一化工具。

负责：

1. `published` 时间解析。
2. 新闻排序。
3. 域名到更友好 source label 的映射。

#### `sources.py`

数据源配置层。

负责：

1. 配置每家公司的官网、新闻页、RSS、Public.com 页面、别名。
2. 配置 `OFFICIAL_NEWS_KEYWORDS`。
3. 配置公司 fallback 新闻。
4. 配置行业 fallback 新闻。

这是 News 模块的“静态配置中心”。

#### `aggregator.py`

旧版新闻聚合器。

它仍然在用，但不是当前 `/api/news/*` 这条主链路，而是主要给：

1. `backend/api/routes/advanced_data.py`
2. `/api/news-aggregator/*`

这套 legacy 实现和 `NewsFeed` 是两条并存链路，后续维护时不要混淆。

---

## 5. News 主链路的系统关系

### 5.1 后端入口关系

后端应用入口在 `backend/main.py`。

在应用启动时，FastAPI 通过：

```python
app.include_router(news_router, prefix="/api", tags=["News"])
```

把 `backend/news/routes.py` 里的路由挂载到 `/api/news/*`。

因此对前端来说，News 主接口就是：

1. `GET /api/news/company/{ticker}`
2. `GET /api/news/industry`
3. `GET /api/news/comparative`
4. `GET /api/news/all`

### 5.2 模块层次关系

可以把当前 News 主链路理解成下面这几层：

```text
前端页面
  -> FastAPI routes
    -> NewsFeed(service facade + cache)
      -> 各业务 service
        -> source fetchers / web search
          -> normalize / filter / policies
            -> 返回结构化 payload
```

### 5.3 端到端逻辑图

```mermaid
flowchart TD
    A[前端 NewsPageFeature] --> B[/api/news/all]
    A --> C[/api/news/industry]
    A --> D[/api/news/comparative]
    B --> E[routes.py]
    C --> E
    D --> E
    E --> F[NewsFeed in service.py]
    F --> G[company_news_service.py]
    F --> H[industry_news_service.py]
    F --> I[comparative_news_service.py]
    G --> J[source_fetchers.py]
    G --> K[rag/web_search.py]
    H --> J
    H --> K
    I --> J
    I --> K
    J --> L[source_parsing.py]
    G --> M[news_filters.py]
    H --> M
    I --> N[news_filter_policies.py]
    M --> N
    N --> O[结构化响应 + diagnostics]
```

---

## 6. 当前主接口与返回语义

### 6.1 `/api/news/company/{ticker}`

用途：

1. 获取某家公司的新闻。
2. 支持 `category` 参数做后置分类过滤。
3. 支持 `count` 控制返回条数。
4. 支持 `force_refresh` 强制重抓。

特点：

1. 这是最复杂的一条链路。
2. 会聚合官方源、搜索源、Google News RSS。
3. 会返回丰富的 diagnostics。

### 6.2 `/api/news/industry`

用途：

1. 获取 EMS / AI / data center 相关行业新闻。

特点：

1. 主要靠预定义 query。
2. 目前抓取逻辑相对简单。
3. 也支持 `force_refresh`。

### 6.3 `/api/news/comparative`

用途：

1. 获取同时提到多个被跟踪公司的新闻。

特点：

1. 主要服务于 competitor comparison 视图。
2. 返回字段名是 `comparative_news`。

### 6.4 `/api/news/all`

用途：

1. 一次拿所有跟踪公司的公司新闻。

特点：

1. 内部会循环调用每个公司的 `get_company_news`。
2. 支持 `count_per_company=0`，表示返回该公司所有已缓存新闻。
3. 结果会走 aggregate cache。

---

## 7. 公司新闻主链路：抓取顺序与逻辑

这一部分是整个 News 模块最重要的实现。

### 7.1 请求进入

前端或调用方发起：

```text
GET /api/news/company/FLEX?count=10&category=ai&force_refresh=true
```

处理过程：

1. `routes.py` 校验 ticker 是否在 `COMPANIES` 中。
2. `routes.py` 从 `get_news_feed()` 获取单例 `NewsFeed`。
3. 路由把请求转发给 `NewsFeed.get_company_news(...)`。
4. `NewsFeed` 再调用 `company_news_service.build_company_news_payload(...)`。

### 7.2 缓存优先语义

这条链路的行为有一个很重要的特点：

1. 如果 `force_refresh=false` 且缓存存在，直接返回缓存。
2. 如果 `force_refresh=false` 且缓存不存在，不会立刻去抓 live 数据。
3. 它会返回一个空 payload，并在 diagnostics 里标记：
   - `cache_status = miss`
   - `cache_only = true`
   - `refresh_required = true`

这意味着当前主链路是“缓存优先 + 显式刷新”的设计。

### 7.3 query 构造

当 `force_refresh=true` 时，开始进入实际抓取流程。

第一步是构造 company query。

构造逻辑来源于：

1. `query_helpers.get_company_aliases(...)`
2. `company_news_service.build_company_news_queries(...)`

别名来源包括：

1. 公司全名
2. 公司短名
3. ticker
4. `sources.py` 中配置的 aliases

然后会拼成几类 query intent：

1. broad news
2. official releases
3. newsroom channels

例如会形成类似：

```text
("Flex Ltd" OR Flex OR FLEX) news
("Flex Ltd" OR Flex OR FLEX) ("press release" OR announcement OR earnings OR "investor relations")
("Flex Ltd" OR Flex OR FLEX) (newsroom OR press OR "media center" OR "news release")
```

### 7.4 官方源优先抓取

公司新闻主链路先抓官方源，再抓搜索源。

官方源由 `source_fetchers.official_company_news_with_diagnostics(...)` 执行。

这一步内部会按逻辑尝试：

1. FLEX 专属 sitemap 扫描
2. 公司 RSS
3. site-scoped Google News RSS
4. HTML 页面扫描
5. seed page fallback

#### 7.4.1 Flex sitemap

对 FLEX，会先尝试：

1. `https://flex.com/sitemap.xml`
2. `https://flex.com/sitemap_index.xml`

递归深度受 `SITEMAP_MAX_DEPTH = 1` 控制。

只保留 URL 中包含：

1. `/newsroom`
2. `/news/`
3. `/press`

的条目。

#### 7.4.2 公司 RSS

如果 `sources.py` 里配置了 `rss_url`，就抓 RSS。

例如：

1. Flex IR RSS
2. Jabil IR RSS
3. Sanmina IR RSS
4. Celestica 的 GlobeNewswire RSS

RSS 解析只读取 feed 里的：

1. `title`
2. `link`
3. `description`
4. `image_url`

当前不抓新闻正文。

#### 7.4.3 site-scoped Google News RSS

如果配置了公司主域名，就构造：

```text
site:company-domain (company aliases) ("news" OR "press release" OR ...)
```

然后走 Google News RSS。

它的作用是：

1. 弥补官网 RSS 不完整的情况。
2. 帮助补抓公司域名范围内被 Google News 索引的新闻页。

#### 7.4.4 HTML 页面扫描

如果某家公司没有 `disable_html_scan = True`，就会扫描：

1. `news_url`
2. `base_url`

流程是：

1. 读取 HTML。
2. 提取 `<a>` 链接。
3. 看标题和 URL 是否包含官方新闻关键词。
4. 给候选链接打分。
5. 取高分链接。

这里不会抓文章正文，只是轻量扫描页面里暴露出来的新闻链接。

#### 7.4.5 seed page fallback

如果配置了 `news_url`，会把该页面本身再包装成一条 fallback item。

它的作用是：

1. 即使没扫出具体新闻链接，至少能返回公司官方新闻页入口。
2. 避免官方链路完全空掉。

#### 7.4.6 Public.com 新闻板

如果公司配置了 `public_news_url`，当前主要是 FLEX，会尝试从 Public.com 的公司新闻板里提取外链。

逻辑是：

1. 拉 Public 页面 HTML。
2. 提取外链。
3. 排除 Public 自己域名。
4. 用公司 aliases 校验标题。
5. 输出外部新闻链接。

### 7.5 搜索源补充抓取

官方源跑完之后，再补抓两个“外部搜索源”。

#### 7.5.1 Brave Search

每个 company query 都会走：

```python
search_web_with_diagnostics(query, count=...)
```

特点：

1. 使用 Brave Search API。
2. 返回原始结果列表和错误信息。
3. query 之间并发执行。
4. 不会因为某个 query 失败而让整批失败。

#### 7.5.2 Google News RSS query fan-out

同样，每个 company query 还会再跑一轮 Google News RSS。

特点：

1. 每个 query 会尝试多个 Google News RSS URL 变体。
2. 有重试逻辑。
3. 会记录 query 级 diagnostics。
4. 会尝试把 Google redirect URL 还原成真实文章 URL。

### 7.6 标准化

无论来源于官方源、Brave 还是 Google News RSS，最终都会走 `normalize_result(...)`。

标准化之后，统一结构大致包括：

1. `title`
2. `url`
3. `backup_url`
4. `description`
5. `image_url`
6. `source`
7. `original_source`
8. `aggregator`
9. `published`
10. `categories`
11. `relevance_score`

这里还会额外做：

1. paywall / blocked domain 过滤
2. 噪声词过滤
3. source 规范化
4. 主题分类

### 7.7 去重和裁剪

候选项标准化后，不是立刻全部混成一个大列表，而是先按 source 暂存在各自 bucket 里，例如：

1. `official`
2. `public_board`
3. `brave`
4. `google_rss`

这样做的目的，是先保留“每一路在 normalize 之后还剩多少”，避免过早合流后看不清是哪一路在污染候选池。

然后才进入统一 merge：

1. 先按 source order 做 first-win merge
2. merge 的 identity 目前仍然是精确 URL/title 这一层
3. 再按 `sort_items_by_recency_and_relevance(...)` 做 `merge_cap` 裁剪

这里有一个很重要的语义边界：

1. 这一层更准确地说是“source-order first-win merge”，不是更强意义上的相似去重。
2. 它可以稳定解决“同一条精确候选在多路 source 同时出现”时谁优先保留的问题。
3. 但它不等于已经处理掉所有近似重复项，例如轻微标题变体、不同摘要包装、弱相似 URL。

所以如果你在 diagnostics 里看到 `merged_candidates`，应该理解成：

1. 已经经过 source 级 first-win merge。
2. 但不是已经完成所有层次的强去重。

### 7.8 公司相关性过滤

接下来通过 `filter_company_news_items(...)` 做公司相关性筛选。

判定逻辑包括：

1. 标题或摘要里出现公司 alias。
2. URL 域名命中该公司的官方域名。
3. `source` 里带公司短名。

这是公司新闻链路真正的“保留门槛”。

### 7.9 fallback 追加

如果过滤后结果数量低于阈值，会追加 `sources.py` 中的静态 fallback 公司新闻。

作用是：

1. 在 live 数据太薄时保证 UI 至少有内容。
2. 降低“空白新闻页”的概率。

### 7.10 响应构造

最终返回的 payload 包含：

1. `ticker`
2. `company_name`
3. `category_filter`
4. `news`
5. `total_found`
6. `timestamp`
7. `diagnostics`

其中 `diagnostics` 里还会包含：

1. 各源抓取数量
2. 各源错误
3. query 计划
4. 去重前后数量
5. fallback 是否使用
6. 官方源细分 diagnostics
7. `source_flow`
8. `fallback_flow`
9. `pre_fallback_source_counts`
10. `post_fallback_source_counts`
11. `final_source_counts`

因此这个接口除了给前端展示，也很适合用来排查抓取质量问题。

尤其是下面几个字段，联调时很有用：

1. `source_flow`
   能看到每一路从 `raw_count -> normalized_count -> merged_candidate_count -> capped_candidate_count -> pre_fallback_kept_count -> final_kept_count` 的流失过程。
2. `pre_fallback_source_counts`
   能看 fallback 介入前，强来源和弱来源各自保留了多少。
3. `post_fallback_source_counts`
   能看 fallback 介入后，最终各 source 的保留分布有没有变化。
4. `final_source_counts`
   当前等价于最终 `news` 的 source trace 统计，可以快速回答“最终保留下来的新闻主要来自哪一路”。
5. `fallback_flow`
   能快速回答 fallback 到底只是被触发了，还是最后真的补进了结果。

---

## 8. 行业新闻主链路

行业新闻在 `industry_news_service.py` 中实现，相比公司新闻简单很多。

### 8.1 核心逻辑

固定使用一组主题 query，例如：

1. `EMS AI infrastructure supply chain news`
2. `electronics manufacturing data center demand`
3. `Flex Jabil Celestica Benchmark Sanmina AI news`
4. `NVIDIA hyperscaler manufacturing partners news`
5. `liquid cooling data center manufacturing news`
6. `immersion cooling AI server supply chain news`

### 8.2 对每个 query 的抓取顺序

对每个 query，按顺序执行：

1. Brave Search
2. Google News RSS

拿到结果后：

1. 统一 `normalize_result(...)`
2. 合并到 `merged_items`

### 8.3 行业筛选

之后通过 `filter_industry_news_items(...)` 保留：

1. AI / data center 相关
2. 或明确提到被跟踪公司的新闻

### 8.4 fallback

如果 `merged_items` 为空，会使用 `FALLBACK_INDUSTRY_NEWS`。

### 8.5 缓存行为

行业新闻缓存 key 是：

```text
industry:{count}
```

同样遵循：

1. `force_refresh=false` 且有缓存：直接返回缓存
2. `force_refresh=false` 且无缓存：返回空结果 + `refresh_required`
3. `force_refresh=true`：执行抓取并写缓存

---

## 9. 对比新闻主链路

对比新闻在 `comparative_news_service.py` 中实现。

### 9.1 query 构造

它会取所有跟踪公司的短名，例如：

1. Flex
2. Jabil
3. Celestica
4. Benchmark
5. Sanmina

然后拼成一个比较型 query：

```text
Flex OR Jabil OR Celestica OR Benchmark OR Sanmina EMS comparison AI manufacturing
```

### 9.2 抓取顺序

顺序为：

1. Brave Search
2. Google News RSS

### 9.3 comparative 筛选

通过 `build_comparative_news_items(...)`：

1. 先做标准化。
2. 再检查标题和摘要中是否提到两家及以上公司。
3. 满足条件才保留。

最终每条 comparative item 会额外包含：

1. `companies_mentioned`

### 9.4 fallback

如果 live comparative news 为空，会回退到一条静态行业比较新闻。

---

## 10. 低层抓取层：`source_fetchers.py`

这个文件是整个 News 模块与外部世界交互最多的地方。

### 10.1 它负责什么

1. HTTP client 创建
2. 文本 / XML 请求
3. Google News RSS 抓取与重试
4. Google News XML 解析
5. 公司 RSS 解析
6. 公司 HTML 页扫描
7. sitemap 递归提取
8. Public.com 外链提取
9. seed page 构造
10. redirect URL 解析

### 10.2 为什么单独做一层 gateway

`NewsFeed` 初始化时会创建：

```python
self.fetchers = NewsSourceFetcherGateway(self)
```

好处是：

1. `NewsFeed` 不需要直接知道每个低层函数名。
2. 上层 service 调用入口更稳定。
3. 可以把 `feed` 的缓存状态，比如 `_google_redirect_cache`，自然传到低层。

### 10.3 Google News RSS 的处理细节

Google News RSS 不是简单拿 XML 就结束，当前还做了几件事情：

1. 试多个 RSS URL 变体。
2. 每个 URL 支持重试。
3. 解析 `<item>`。
4. 从 title suffix 里提 publisher。
5. 从 description 里提 publisher。
6. 从 description 的 HTML 里提真实外链。
7. 如果还是 Google redirect，则继续解析跳转。

所以它实际上不只是“抓 Google RSS”，而是在努力把 Google 的中间层包装还原成真实新闻源。

### 10.4 官方源抓取策略

`fetch_official_company_news_with_diagnostics(...)` 是公司官方源总入口。

它做的事情不是“选一种源”，而是“把同一公司的多个官方候选源都拉一遍，再按质量层级合并”。

这意味着：

1. 官方 RSS 有就抓。
2. 站内 Google News RSS 有就补。
3. sitemap 命中的正文 URL 也可以补。
4. HTML 扫描能扫到也补。
5. seed page 作为最后兜底。

但这里有一个很重要的实现细节：

1. 当前不是把所有候选直接平铺后一次性裁掉。
2. 低层 fetcher 会先把候选分成几层：`rss_candidates`、`site_query_candidates`、`sitemap_candidates`、`html_scan_candidates`、`seed_candidates`。
3. 最后再按照这个顺序做去重和截断。

这样做的目的，是尽量保证：

1. 真正的官方正文类来源优先保留。
2. HTML scan 这类弱候选只在前面不够时补位。
3. seed page 不会因为“先进入候选池”而抢掉更强结果的位置。

所以这条链路更准确地说，是“按层级排序的官方候选池”，而不是完全平铺的候选池。

### 10.5 低层 fetcher 的基础输出结构

当前建议所有低层 fetcher 尽量返回同一批核心字段，再交给上层 `normalize_result(...)` 继续统一。

也就是说，在 `source_fetchers.py` 这一层，新闻 item 最好尽量带齐下面这些字段：

1. `title`
2. `url`
3. `description`
4. `image_url`
5. `source`
6. `original_source`
7. `aggregator`
8. `published`

这里的意思不是“每个字段都必须有真实值”，而是：

1. 字段集合尽量稳定。
2. 没有值时也尽量给出默认值，例如空字符串或 `None`。
3. 这样后面的 `normalize_result(...)`、filter、service 编排层拿到的数据结构会更一致。

这几个字段当前建议按下面的口径理解：

1. `source`
   给前端展示、搜索、统计时优先使用的来源名，尽量是用户能直接看懂的真实媒体名或官方源标签。
2. `original_source`
   fetcher 侧拿到的“最佳可用底层来源标签”。
   它不应该是噪音尾巴、HTML 残片或临时描述文本；如果拿不到更底层的来源，就可以回退到 `source`。
3. `aggregator`
   只在结果经过聚合器/搜索中转时填写，例如 `Google News`、`Brave Search`。
   官方 RSS、官网 HTML 扫描、官方 seed page 这类直接源通常应保持为 `None`。

为什么要这么做：

1. 不同 fetcher 返回字段不一致时，上层会出现“同类新闻 item 但字段完整度不同”的问题。
2. diagnostics 和联调时也会更难排查。
3. 新 source 接入时更容易遗漏某些字段。

所以后续如果新增 fetcher，建议优先复用 `source_fetchers.py` 里的共享 item builder，而不是每个函数手写一份返回 dict。

---

## 11. 来源解析层：`source_parsing.py`

这个文件的主要职责不是抓新闻，而是解决“source 叫什么”。

### 11.1 它在处理哪些问题

不同来源里的 source 信息经常不统一：

1. 有些在标题尾巴，例如 `Headline - Reuters`
2. 有些在 Google News title 中
3. 有些在 Google description 中
4. 有些只能从 URL 域名推断
5. 有些尾巴看起来像 source，实际上是时间、栏目、控制文本

因此 `source_parsing.py` 做了：

1. HTML 清洗
2. Google 自有域识别
3. article URL 基础合法性判断
4. 外链提取
5. title suffix source 提取
6. Google title / description source 提取
7. URL source fallback
8. source candidate 规范化

### 11.2 当前 source 提取原则

现在这层已经统一为一个思路：

1. 各函数只负责“提取候选 source”。
2. 候选值统一走共享的 candidate normalization。
3. 对明显像时间戳、控制文本、无效尾巴的内容进行排除。
4. 域名型来源尽量映射成更稳定的展示名。

这样做的目的是：

1. 降低同一来源被提成多个名字的概率。
2. 降低 description 尾巴误判成 source 的概率。
3. 让上层 `normalize_result(...)` 的 source 输出更稳定。

这里还要特别注意一个边界：

1. `is_likely_article_url(...)` 当前主要用于“基础合法性过滤”。
2. 它会排除静态资源、Google 中间域、明显 tracking URL。
3. 但它当前还不是一个“正文页优先分类器”。
4. 也就是说，这一层不会保证把所有栏目页、tag 页、search 页都彻底识别并过滤掉。
5. 如果后续线上观察到这类页面开始明显混入，更合适的做法通常是在后续再补一轮更高层的 article-page 优先过滤，而不是把这一层改得过于激进，误伤合法新闻正文页。

---

## 12. 标准化与过滤层

### 12.1 `news_filters.py`

它是把原始抓取结果变成统一新闻对象的关键层。

核心动作有：

1. 判断 title / url 是否存在。
2. 屏蔽噪声词。
3. 屏蔽 paywall / blocked domain。
4. 计算分类。
5. 生成 `backup_url`。
6. 综合多个来源候选，决定最终 `source`。
7. 计算 `relevance_score`。

这层输出的结构是整个前后端协作最关键的数据契约之一。

### 12.2 `news_filter_policies.py`

这里是“按 feed 类型区别对待”的规则层。

为什么要单独拆？

因为：

1. 公司新闻需要“属于这家公司”
2. 行业新闻需要“符合主题”
3. 对比新闻需要“同时提两家以上公司”

这三个判断逻辑并不一样，拆开后更容易维护。

### 12.3 `filtering.py`

这是常量集中地。

如果后续你要：

1. 新增分类
2. 改主题词
3. 新增 blocked domain
4. 调整噪声词

通常都是先改这个文件。

---

## 13. 缓存与持久化策略

### 13.1 为什么有两层缓存

`NewsFeed` 里有两套缓存：

1. `_runtime_cache`
2. `_aggregate_cache`

#### `_runtime_cache`

作用：

1. 缓存公司新闻 raw payload
2. 缓存行业新闻
3. 缓存 comparative 新闻
4. 会持久化到磁盘

磁盘文件包括：

1. `data/news_cache/company_news.json`
2. `data/news_cache/industry_news.json`
3. `data/news_cache/comparative_news.json`

#### `_aggregate_cache`

作用：

1. 缓存类似 `/news/all` 这种聚合后的结果
2. 只存在内存，不落盘

### 13.2 旧缓存迁移

`service.py` 里保留了旧格式缓存迁移逻辑：

1. 旧文件：`data/news_runtime_cache.json`
2. 新结构：`data/news_cache/*.json`

启动时如果发现旧格式，会迁移后删除旧文件。

### 13.3 当前 TTL 语义

代码里定义了 `_cache_ttl = 3600`，并有 `_is_cache_entry_fresh(...)`。

但当前主路径更多使用的是：

1. 有缓存就读
2. `force_refresh=true` 才重抓

也就是说，TTL 工具存在，但当前并没有在主入口里作为强制淘汰条件广泛使用。

### 13.4 `/news/all` 的缓存失效

当某个公司新闻被重新抓取后，会调用：

```python
feed._invalidate_aggregate_cache("all:")
```

确保 `/news/all` 不继续持有旧聚合结果。

---

## 14. Diagnostics 机制

这是当前 News 模块一个很有价值的特点。

很多接口返回里都会带 `diagnostics`，用来告诉你：

1. 是缓存命中还是缓存未命中。
2. 哪个 source 抓到了多少条。
3. 哪个 source 报错了。
4. 每个 query 的执行状态。
5. 标准化前后数量变化。
6. fallback 是否被使用。

这让 News 模块不是一个“黑箱接口”，而是一个可调试的聚合系统。

对于排查下面这些问题特别有用：

1. 为什么某家公司今天新闻突然变少。
2. 为什么某个 query 什么都没回来。
3. 为什么只有官方源有数据。
4. 为什么 fallback 被触发了。

当前低层 fetcher 的 diagnostics，建议至少稳定带这四个核心字段：

1. `status`
2. `status_code`
3. `error`
4. `items_found`

当前这套实现里，`status` 建议理解成两组固定词表：

1. 结果状态：
   `ok`、`empty`
2. 失败状态：
   `request_error`、`parse_error`、`processing_error`、`http_xxx`、`error`
3. 编排占位状态：
   `not_attempted`、`not_applicable`、`missing_source_config`

也就是说，不同 fetcher 即使内部逻辑不同，遇到同类问题时也尽量往同一批状态名上收，而不是各自发明新的状态字符串。

其它字段可以按 source 自己补充，例如：

1. Google RSS 的 `query`、`rss_urls_tried`、`attempts`
2. RSS 的 `rss_url`、`source_name`
3. HTML scan 的 `raw_link_count`、`candidate_count`
4. official 汇总层的 `candidate_tier_counts`、`candidate_tier_kept_counts`、`candidate_tier_suppressed_counts`
5. official 汇总层的 `strong_candidate_*`、`weak_candidate_*`

特别是 `official_company_news_with_diagnostics(...)` 这条链路，现在除了 `rss_sources`、`html_scans`、`seed_page` 之外，也会保留 `site_query_diagnostics`，这样联调时可以区分：

1. 站内 Google RSS 是请求失败了
2. 站内 Google RSS 抓空了
3. 站内 Google RSS 有结果，但在 tier merge 里被更强来源压掉了

另外，`official_company_news_with_diagnostics(...)` 现在也会汇总：

1. `strong_candidate_total_count`
2. `strong_candidate_kept_count`
3. `weak_candidate_total_count`
4. `weak_candidate_kept_count`

这几个数字的意义很直接：

1. 如果 `weak_candidate_kept_count` 很高，说明 `scan/seed` 这类弱候选正在明显补位。
2. 如果 `weak_candidate_total_count` 很高但 `weak_candidate_kept_count` 很低，说明 tier merge 已经把大部分弱候选压住了。
3. 如果联调里发现弱候选经常占满最终结果，就优先继续收紧 `scan` 和 `seed` 的保留条件，而不是先重写整个 merge 架构。

---

## 15. 前端如何调用后端

当前主前端调用入口在：

`frontend/src/features/news/NewsPageFeature.tsx`

### 15.1 页面初次加载时做什么

页面初始化会并行请求三个接口：

1. `/api/news/all?count_per_company=0`
2. `/api/news/industry?count=20`
3. `/api/news/comparative`

也就是说，前端不是逐公司单独拉，而是：

1. 一次拿到所有公司的公司新闻
2. 一次拿行业新闻
3. 一次拿 comparative 新闻

然后在前端本地把这三类数据拼成统一展示流。

### 15.2 刷新按钮怎么工作

当前前端刷新时会携带：

1. `force_refresh=true`
2. `_refresh=<timestamp>` 防缓存 nonce
3. `cache: 'no-store'`

这意味着：

1. 前端非常明确地区分“读缓存”和“强制重抓”。
2. News 后端的设计是配合这种交互语义的。

### 15.3 前端收到数据后会再做什么

前端并不会把后端结果原样直接展示，还会额外做：

1. `toUnifiedItem(...)`，给 UI 增加 `categoryLabel` 和 `timestampLabel`
2. 更严格的公司匹配
3. 标题相似度去重
4. lead story 选择
5. blocked domain 跳转到 `backup_url`
6. feed 排序
7. fallback feed 展示

### 15.4 为什么说是“前后端协同”

因为当前新闻页不是后端一层就完成所有最终展示筛选，而是：

#### 后端负责

1. 多源抓取
2. 标准化
3. 基础过滤
4. source 解析
5. diagnostics
6. 缓存

#### 前端负责

1. 更严格的展示收敛
2. 交互层排序
3. UI fallback
4. 安全跳转处理

因此这不是“后端单独完成一切”的架构，而是“后端提供可控候选结果，前端做产品级展示决策”的架构。

---

## 16. 前端与后端协作时的一个关键事实

目前 News 主接口在缓存缺失但未显式刷新时，可能返回空结果和 `refresh_required`。

这直接影响前端行为：

1. 前端首次打开页面，如果后端缓存里本来没有数据，可能拿到空结果。
2. 前端当前通过自己的 fallback feed 避免页面空白。
3. 用户点击刷新后，才会真正触发 live 抓取。

因此如果未来要改产品体验，需要优先明确一个策略问题：

1. 保持当前“缓存优先，刷新才抓”
2. 还是改成“缓存 miss 时自动 live 抓取”

这不是单纯代码细节，而是一个前后端协作策略选择。

---

## 17. 依赖的外部模块与外部能力

虽然主逻辑都在 `backend/news`，但它依赖几个目录外模块：

### `backend/core/config.py`

提供：

1. `COMPANIES`
2. `BRAVE_API_KEY`
3. `BRAVE_SEARCH_URL`
4. 其它全局配置

### `backend/rag/web_search.py`

提供 Brave Search API 封装。

### `backend/main.py`

负责挂载 News 路由。

### `frontend/src/features/news/NewsPageFeature.tsx`

是当前主消费端。

---

## 18. Legacy Aggregator：为什么它还存在

`backend/news/aggregator.py` 是一套较早的新闻聚合实现。

它和当前主链路的区别大致是：

1. 结构更简单
2. 数据源更少
3. 只做内存缓存
4. 没有当前这套详细 diagnostics
5. 主要服务 `/api/news-aggregator/*`

当前应当把它理解为：

1. 仍在运行的兼容逻辑
2. 不是主新闻页的核心链路

如果后续要继续演进 News 模块，建议优先围绕 `routes.py + service.py + *_news_service.py + source_fetchers.py` 这套主链路做，不要把新逻辑继续往 legacy aggregator 里堆。

---

## 19. 当前这套架构的优点

### 19.1 优点

1. 模块分层已经比较清楚。
2. 公司新闻主链路有明显的编排中心。
3. source fetcher 和业务策略是分离的。
4. diagnostics 设计比较实用。
5. 官方源和搜索源并行存在，抗单点失效能力较强。
6. 前后端边界比较明确。
7. fallback 机制让页面更稳定。

### 19.2 当前的代价

1. 主链路和 legacy aggregator 并存，容易让新人混淆。
2. 缓存 miss 时默认不自动抓取，这个语义需要前端配合理解。
3. 过滤逻辑有一部分在前端，意味着展示行为不能只看后端。
4. source 命名的一致性要持续维护。

---

## 20. 阅读代码的推荐顺序

如果你是第一次接手这个模块，建议按下面顺序看：

1. `backend/news/README.zh.md`
2. `backend/news/routes.py`
3. `backend/news/service.py`
4. `backend/news/company_news_service.py`
5. `backend/news/source_fetchers.py`
6. `backend/news/news_filters.py`
7. `backend/news/news_filter_policies.py`
8. `backend/news/source_parsing.py`
9. `backend/news/sources.py`
10. `frontend/src/features/news/NewsPageFeature.tsx`

如果你要查“为什么某条新闻出现了”：

1. 先看前端是否保留或过滤了它。
2. 再看后端 `diagnostics`。
3. 再看该条新闻是从哪个 source 进来的。
4. 再看 `normalize_result(...)` 和 policy 层是否把它保留了。

---

## 21. 后续如何新增 Source / RSS / API（实操说明）

这一节专门回答一个很实际的问题：

如果后面我们想补充新的新闻 source，尤其是：

1. 给现有公司补一个新的 RSS
2. 给现有公司补一个新的官网新闻页
3. 给行业新闻补一个固定 RSS / API
4. 接一个全新的第三方新闻 API
5. 增加一个新的跟踪公司

那代码应该写在什么位置，哪些情况只改配置，哪些情况必须写新代码。

### 21.1 先做一个判断：你要加的到底是哪一类 source

最常见的情况其实只有下面几类：

#### A. 现有公司增加一个官方 RSS

例如：

1. Flex 新增一个 IR feed
2. Jabil 新增一个 press feed
3. Sanmina 新增一个 event feed

这种通常只需要改配置，不需要改路由。

#### B. 现有公司增加一个新的官网新闻入口页

例如：

1. 官网新开了 `media-center`
2. 官网新闻入口从 `/newsroom` 改成 `/news-events`
3. 想把某个公司主页也作为扫描入口

这种大多数时候还是配置级改动。

#### C. 现有公司增加一个“聚合页型 source”

例如：

1. Public.com 这种新闻板
2. 一个券商/资讯站的公司新闻聚合页
3. 某个专门的 company hub 页面

如果当前已有类似 fetcher，可以只改配置；如果页面结构特殊，就要加一个新的 fetcher。

#### D. 行业新闻要接一个新的 RSS 或 API

例如：

1. 新增一个固定行业 RSS
2. 新增一个付费新闻 API
3. 新增一个行业数据库接口

这种通常需要改 `industry_news_service.py`，如果接口格式特殊，还要改 `source_fetchers.py`。

#### E. 新增一个全新的跟踪公司

例如：

1. 我们决定把另一家 EMS 公司纳入跟踪名单

这种不只是加 source，而是要同时改：

1. `core/config.py`
2. `sources.py`
3. 前端 ticker 常量
4. 可能还要调 query / alias / UI 展示

所以它比“补一个 source”大一个量级。

---

### 21.2 最常见场景：给现有公司补一个新的 RSS

这是最简单、也最推荐优先尝试的方式。

#### 要改哪里

主要改：

1. `backend/news/sources.py`

通常不需要改：

1. `routes.py`
2. `service.py`
3. `company_news_service.py`
4. `source_parsing.py`

#### 为什么

因为公司新闻主链路已经默认会调用：

1. `fetch_official_company_news_with_diagnostics(...)`
2. 这个函数会自动读取 `OFFICIAL_COMPANY_SOURCES[ticker]["rss_url"]`
3. 如果 `rss_url` 是字符串或列表，它都会抓

也就是说，只要你的 RSS 是标准 RSS / XML 格式，现有抓取流程通常已经能接住。

#### 代码位置

文件：

`backend/news/sources.py`

例如你要给 `BHE` 增加 RSS，可以像这样改：

```python
"BHE": {
    "name": "Benchmark",
    "domain": "bench.com",
    "base_url": "https://www.bench.com",
    "news_url": "https://www.bench.com/newsroom",
    "rss_url": [
        "https://www.bench.com/rss/news.xml",
    ],
    "public_news_url": None,
    "aliases": ["Benchmark Electronics", "NYSE:BHE"],
},
```

#### 这类改动之后，现有链路会自动做什么

它会自动：

1. 抓 RSS
2. 解析 `title/link/description/image`
3. 走 `normalize_result(...)`
4. 做公司相关性过滤
5. 进入 diagnostics

#### 什么时候只改 `sources.py` 还不够

如果你的 RSS：

1. 不是标准 `<item>` 结构
2. 需要鉴权 header
3. 返回 JSON 而不是 XML
4. 需要额外参数或签名

那就不能只改配置，必须补一个自定义 fetcher。

---

### 21.3 场景二：给现有公司补一个新的官网新闻页或扫描入口

这种也很常见，比如公司官网改版。

#### 要改哪里

通常还是改：

1. `backend/news/sources.py`

相关字段包括：

1. `base_url`
2. `news_url`
3. `disable_html_scan`

#### 为什么

因为 `source_fetchers.py` 里已经有现成的：

1. HTML 页面扫描
2. seed page fallback
3. 站内 Google News RSS

只要你把入口页地址配对，现有逻辑通常就会自动把它纳入官方候选池。

#### 例子

如果某家公司新闻页从：

```text
https://example.com/newsroom
```

迁移到：

```text
https://example.com/media-center/news
```

那优先改：

```python
"news_url": "https://example.com/media-center/news"
```

如果公司主页也值得扫，可以同时确认：

```python
"base_url": "https://example.com"
```

#### 什么时候要去改 `source_fetchers.py`

如果新页面：

1. 不是简单的 `<a href>` 链接页
2. 新闻链接藏在 JS 数据块里
3. 页面 HTML 特别规整，值得专门提取
4. 页面结构跟其它公司完全不一样

那就可以考虑写一个专门 fetcher，而不是强行复用通用扫描器。

---

### 21.4 场景三：给现有公司补一个聚合页型 source

例如：

1. Public.com 某公司新闻页
2. 某个券商提供的公司新闻聚合页
3. 某个行业站的公司专栏页

#### 当前现成模式

目前代码里已经有一个例子：

1. `public_news_url`
2. `fetch_public_news_links_with_diagnostics(...)`

这意味着：

1. 如果你的新 source 和 Public.com 这种“页面里挂外链”的结构类似，可以考虑沿用这个模式。
2. 如果结构完全不一样，就写一个新的专用 fetcher。

#### 只改配置的情况

如果你已经有一个现成 fetcher 能处理这种页面，那么只要在 `sources.py` 补字段即可。

#### 需要写代码的情况

如果这个聚合页：

1. HTML 结构特殊
2. 需要登录或 token
3. 有特殊分页
4. 外链提取方式跟现有逻辑不同

那建议：

1. 在 `source_fetchers.py` 写新的低层函数
2. 在 `NewsSourceFetcherGateway` 增加一个 gateway 方法
3. 在 `company_news_service.py` 把它接进公司新闻编排

---

### 21.5 场景四：给行业新闻补一个新的 RSS 或 API

行业新闻目前的主逻辑在：

1. `backend/news/industry_news_service.py`

它现在主要靠：

1. 预设 query
2. Brave Search
3. Google News RSS

所以如果你要加一个新的行业 source，通常分两种情况。

#### 情况一：只是想补一组新的搜索 query

例如你觉得现在对液冷、AI server、OCP 相关主题抓得不够。

这种直接改：

1. `backend/news/industry_news_service.py`

里的 `queries = [...]` 列表即可。

这是最轻量、最低风险的方式。

#### 情况二：你要接一个固定 RSS 或固定 API

例如：

1. 一个行业站固定 RSS
2. 一个付费资讯 API
3. 一个你们内部的行业源接口

这时应该改：

1. `backend/news/source_fetchers.py`
2. `backend/news/industry_news_service.py`

#### 推荐接法

第一步，在 `source_fetchers.py` 写一个低层抓取函数，例如：

```python
async def fetch_industry_partner_api_with_diagnostics(
    api_url: str,
    limit: int = 10,
) -> tuple[list[dict], dict[str, Any]]:
    ...
```

返回结果尽量整理成这种原始 shape：

```python
{
    "title": "...",
    "url": "...",
    "description": "...",
    "image_url": "...",
    "source": "Partner API",
    "published": "...",
}
```

第二步，在 `NewsSourceFetcherGateway` 里加一个包装方法：

```python
async def industry_partner_api_with_diagnostics(self, api_url: str, limit: int = 10):
    return await fetch_industry_partner_api_with_diagnostics(api_url, limit)
```

第三步，在 `industry_news_service.py` 调用它，然后继续走 `normalize_result(...)`：

```python
api_results, api_diagnostics = await feed.fetchers.industry_partner_api_with_diagnostics(
    "https://api.example.com/news",
    limit=10,
)

for result in api_results:
    normalized = normalize_result(feed, result)
    if normalized:
        merged_items.append(normalized)
```

第四步，如果这个 source 很关键，建议把它也写进 diagnostics。

---

### 21.6 场景五：接一个全新的第三方 API Source

这个场景和“补固定 RSS”不同，因为它往往有自己独特的返回格式、鉴权方式、速率限制。

#### 代码应该写在哪里

优先写在：

1. `backend/news/source_fetchers.py`

而不是直接写在：

1. `company_news_service.py`
2. `industry_news_service.py`
3. `comparative_news_service.py`

#### 原因

因为这几个 service 文件应该主要负责“编排”和“策略”，不应该承担复杂的外部 API 适配细节。

#### 推荐分层方式

##### 第 1 层：低层请求和原始解析

放在 `source_fetchers.py`。

负责：

1. 发请求
2. 处理 header / token
3. 处理分页
4. 处理第三方返回格式
5. 产出 diagnostics

##### 第 2 层：gateway 暴露统一调用入口

放在 `NewsSourceFetcherGateway`。

这样 service 层用的时候接口会更一致。

##### 第 3 层：在业务 service 里决定接入位置

例如：

1. 如果这个 API 是公司新闻源，就接到 `company_news_service.py`
2. 如果是行业新闻源，就接到 `industry_news_service.py`
3. 如果是对比型新闻源，就接到 `comparative_news_service.py`

##### 第 4 层：统一标准化

新 API 的原始结果仍然建议交给：

1. `normalize_result(...)`

来完成最终统一。

这样可以保证新 source 和旧 source 输出结构一致。

#### 一个更完整的示例

如果你要给公司新闻接一个新 API，例如 `Example News API`，可以按这个顺序：

1. `source_fetchers.py`
   - 新增 `fetch_example_news_api_with_diagnostics(...)`
2. `source_fetchers.py`
   - 在 `NewsSourceFetcherGateway` 里新增 `example_news_api_with_diagnostics(...)`
3. `company_news_service.py`
   - 在官方源之后、Brave 之前或之后接入这批结果
4. `company_news_service.py`
   - 用 `_append_normalized_items(...)` 把结果并入 `news_items`
5. `company_news_service.py`
   - 在 `normalized_counts`、`source_counts`、`errors` 里加 diagnostics
6. `source_parsing.py` / `normalizer.py`
   - 只有当这个 API 的 source 命名很特殊时，才需要补 source 解析或 source label 映射

---

### 21.7 场景六：新增一个新的跟踪公司

这不是简单“加 source”，而是“扩一整条跟踪对象”。

#### 至少要改哪些地方

1. `backend/core/config.py`
   - 把公司加到 `COMPANIES`
2. `backend/news/sources.py`
   - 加 `OFFICIAL_COMPANY_SOURCES`
   - 加 `FALLBACK_COMPANY_NEWS`
3. `frontend/src/features/news/NewsPageFeature.tsx`
   - 加 `COMPANY_TICKERS`
   - 加 `COMPANY_NAMES`
   - 加颜色、badge、domain hints 等前端常量

#### 视情况可能要改的地方

1. `query_helpers.py`
   - 如果别名策略要特殊处理
2. `content_signals.py`
   - 通常不用单独改，因为它依赖 `COMPANIES`
3. `news_filter_policies.py`
   - 一般也不用单独改，因为它也依赖 alias / domain 配置

#### 推荐顺序

1. 先把 `COMPANIES` 和 `OFFICIAL_COMPANY_SOURCES` 配齐
2. 先试跑公司新闻主链路
3. 看 diagnostics
4. 再补前端 ticker 和 UI 配置
5. 最后补 fallback 新闻

---

### 21.8 哪些文件通常不用碰

后面你如果只是加 source，很多时候不需要去动下面这些文件：

1. `backend/news/routes.py`
2. `backend/news/service.py`
3. `backend/news/source_parsing.py`
4. `backend/news/news_filter_policies.py`

只有在下面情况才考虑改它们：

#### 改 `routes.py`

当你要增加一个全新的 API endpoint。

#### 改 `service.py`

当你要增加一种新的顶层 feed 类型，或者改缓存结构。

#### 改 `source_parsing.py`

当新 source 的：

1. source 命名很特殊
2. description 结构很特殊
3. Google title / description 提取规则不够用了

#### 改 `news_filter_policies.py`

当你要改的是“保留规则”，不是“抓取来源”。

---

### 21.9 一个简单判断表：我到底该改哪里

| 需求 | 主要改动文件 | 通常是否要写新代码 |
|---|---|---|
| 给现有公司补一个标准 RSS | `sources.py` | 通常不用 |
| 给现有公司补一个新闻页 URL | `sources.py` | 通常不用 |
| 给现有公司补一个 Public 类聚合页 | `sources.py`，必要时 `source_fetchers.py` | 有时需要 |
| 给行业新闻补新 query | `industry_news_service.py` | 不用 |
| 给行业新闻补固定 RSS / API | `source_fetchers.py` + `industry_news_service.py` | 通常要 |
| 给公司新闻接第三方 API | `source_fetchers.py` + `company_news_service.py` | 通常要 |
| 新增一整个跟踪公司 | `core/config.py` + `sources.py` + 前端文件 | 要 |

---

### 21.10 建议的接入顺序

以后你让我加新 source 时，我建议默认按下面顺序做：

1. 先判断能不能只改配置。
2. 如果不能，再把抓取逻辑写进 `source_fetchers.py`。
3. 用 gateway 暴露统一入口。
4. 再接入对应的业务 service。
5. 保持最终都走 `normalize_result(...)`。
6. 把 diagnostics 一起补全。
7. 最后用 `force_refresh=true` 联调真实结果。

这个顺序的好处是：

1. 改动面最小。
2. 分层清晰。
3. 出问题容易定位。
4. 不会把“抓取细节”和“业务编排”搅在一起。

---

### 21.11 一个很重要的经验规则

如果你的目标只是“多抓到一点新闻”，优先顺序一般应该是：

1. 先补 `aliases`
2. 再补官方 `rss_url`
3. 再补 `news_url` / `base_url`
4. 再补行业 query
5. 最后才考虑新第三方 API

因为前四种方式：

1. 成本更低
2. 风险更小
3. 更符合当前架构
4. 后续维护也更轻

第三方 API 虽然强，但通常是维护成本最高的一类 source。

---

## 22. 一句话总结

当前 `backend/news` 的主链路本质上是一套“多源新闻候选收集 + 统一标准化 + 规则筛选 + 缓存化输出”的竞争情报新闻聚合系统。

它不是全文爬虫，也不是纯搜索接口，而是一个介于“新闻抓取器”和“情报 feed service”之间的领域服务；并且它和前端采用的是“后端广覆盖、前端再收敛”的协同模式。
