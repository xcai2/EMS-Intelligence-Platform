# News 模块后端逻辑与架构说明

最后更新：2026-04-10（America/Los_Angeles）

## 1. 这份文档说明什么

这份文档只回答一件事：`backend/news` 现在这套后端代码到底是怎么工作的。

重点包括：

1. `backend/news` 目录里每个文件的真实职责。
2. 当前唯一维护的主链路是什么。
3. 一次新闻请求是谁先运行、谁后运行。
4. 抓取层、解析层、过滤层、资源配置层分别在哪里。
5. 文件命名为什么这样分。
6. 现在已经完成了什么，接下来最该改什么。
7. 如果要升级这套模块，第一站应该看哪个文件。

这份文档以当前代码实现为准，不讲理想方案，只讲现在真实发生的事情。

---

## 2. 先看结论

`backend/news` 现在只保留一条维护中的新闻主链路：

1. `routes.py -> service.py -> *_service.py -> source_fetchers.py -> news_filters.py`

其中：

1. `/api/news/*` 走的是主链路。
2. 历史上的 `aggregator.py` 和 `/api/news-aggregator/*` 已移除。
3. `/api/intelligence/news/*` 不是 `backend/news` 的实时抓取链路，而是静态监控数据接口。

如果你现在要改真正给前端 News 页面使用的逻辑，直接看主链路即可。

---

## 3. 模块目标

`backend/news` 的目标不是做全文爬虫，而是做一层“竞争情报新闻聚合后端”。

它负责：

1. 从多个来源抓公司新闻、行业新闻、对比新闻。
2. 把不同来源的数据归一成统一结构。
3. 做基础去重、分类、相关性判断、排序。
4. 把结果缓存到本地 JSON。
5. 为前端提供稳定的 `/api/news/*` 返回格式。

它不负责：

1. 深度正文抓取。
2. 强语义分类。
3. 全自动后台刷新。
4. 完整测试覆盖。

---

## 4. 分层架构

从代码职责来看，`backend/news` 可以分成 6 层：

| 层级 | 文件 | 作用 |
| --- | --- | --- |
| API 入口层 | `routes.py` | 定义 `/api/news/*` 路由，做参数校验和依赖注入 |
| 总控与缓存层 | `service.py` | `NewsFeed` 单例、缓存加载/持久化、主能力分发 |
| 业务编排层 | `company_news_service.py` `industry_news_service.py` `comparative_news_service.py` | 按不同场景安排抓取、合并、过滤、fallback |
| 抓取层 | `source_fetchers.py` | 真正访问外部 RSS、官网页面、Google News RSS、Public.com |
| 解析与过滤层 | `news_filters.py` `news_filter_policies.py` `source_parsing.py` `content_signals.py` `normalizer.py` | 统一字段、抽 source、分类、去重、排序、相关性判断 |
| 资源与规则层 | `sources.py` `filtering.py` `query_helpers.py` | 公司源配置、fallback 静态数据、分类关键词、query 生成规则 |

---

## 5. 目录与文件职责

下面按文件逐个说明。

### `__init__.py`

只负责把 `backend/news` 标记为 Python package，没有业务逻辑。

### `routes.py`

这是 News 模块对外 API 的入口。

它负责：

1. 暴露 4 个主接口：
   - `GET /api/news/company/{ticker}`
   - `GET /api/news/industry`
   - `GET /api/news/comparative`
   - `GET /api/news/all`
2. 通过 `get_news_feed()` 懒加载 `NewsFeed` 单例。
3. 校验 ticker 是否存在。
4. 校验 category 是否在 `filtering.py` 的 `CATEGORIES` 中。

它不负责抓取，不负责过滤，也不直接读写缓存。

### `service.py`

这是主链路的总控文件，核心类是 `NewsFeed`。

它负责：

1. 持有运行期缓存 `_runtime_cache`。
2. 持有聚合缓存 `_aggregate_cache`。
3. 持有 Google News redirect 缓存 `_google_redirect_cache`。
4. 启动时加载结构化缓存文件：
   - `data/news_cache/company_news.json`
   - `data/news_cache/industry_news.json`
   - `data/news_cache/comparative_news.json`
5. 兼容迁移旧缓存文件：
   - `data/news_runtime_cache.json`
6. 对外暴露三个主能力和一个聚合能力：
   - `get_company_news`
   - `get_industry_news`
   - `get_competitor_comparison_news`
   - `get_all_companies_news`
7. 把具体业务转发给各个 `*_service.py`。

它的角色可以理解成：

1. service facade
2. cache manager
3. pipeline dispatcher

### `company_news_service.py`

这是整个 `backend/news` 里最重要的文件，也是主 API 里最完整的一条链路。

它负责：

1. 基于公司别名生成查询语句。
2. 决定公司新闻抓取顺序。
3. 控制每个来源抓多少。
4. 并发跑 Brave Search 和 Google News RSS 的 query fan-out。
5. 按来源分桶。
6. 标准化结果。
7. 按来源优先级做 first-win merge。
8. 做公司相关性过滤。
9. 在结果太少时加 fallback。
10. 生成详细 diagnostics。
11. 持久化 raw cache。

如果用户问“为什么 FLEX 最后只出来这些新闻”，第一站看这个文件。

### `industry_news_service.py`

行业新闻编排层。

它负责：

1. 维护一组固定的行业查询。
2. 每个 query 分别调用 Brave Search 和 Google News RSS。
3. 对结果做统一 normalize。
4. 用 `filter_industry_news_items()` 保留 AI/主题相关结果。
5. live 结果为空时使用 `FALLBACK_INDUSTRY_NEWS`。

这条链路比公司新闻简单很多，目前没有 source-flow diagnostics，也没有 company pipeline 那么细的 merge 机制。

### `comparative_news_service.py`

对比新闻编排层。

它负责：

1. 从 `COMPANIES` 里拿公司简称。
2. 生成一个多公司 comparison query。
3. 调 Brave Search 和 Google News RSS。
4. 保留同时提到 2 家及以上公司的新闻。
5. 生成 `companies_mentioned` 字段。

它目前也是轻量实现，复杂度明显低于公司新闻链路。

### `source_fetchers.py`

这是底层抓取文件，也是主链路真正对外部世界发请求的地方。

它负责：

1. 建立 `httpx.AsyncClient`。
2. 抓 Google News RSS。
3. 抓公司官方 RSS。
4. 扫公司官网新闻页 HTML。
5. 读取 Flex sitemap。
6. 读取 Public.com 公司新闻板。
7. 构建 seed page fallback item。
8. 解析 Google News redirect。
9. 为各来源生成 source-level diagnostics。

主链路里凡是“真正发 HTTP 请求”的逻辑，基本都在这里。

### `source_parsing.py`

这是抓取后的基础解析工具层。

它负责：

1. HTML 清洗。
2. 提取第一张图片 URL。
3. 从 Google News description 里提取真实外链。
4. 判断 Google 自有域名。
5. 从标题后缀提取 publisher。
6. 从 Google title / description 提取 source。
7. 把 URL 域名映射为可展示的 publisher label。

如果结果里 source 名字不对，先看这个文件。

### `news_filters.py`

这是统一 normalize 和通用过滤文件。

它负责：

1. 把不同来源结果统一成一套字段。
2. 生成：
   - `title`
   - `url`
   - `backup_url`
   - `description`
   - `image_url`
   - `source`
   - `original_source`
   - `aggregator`
   - `published`
   - `categories`
   - `relevance_score`
3. 过滤 blocked / paywall domain。
4. 过滤噪声词。
5. 根据标题和描述做轻量分类。
6. 做 exact URL/title 去重。

这是“统一数据结构”的核心文件。

### `news_filter_policies.py`

这是按 feed 类型区分的“策略过滤层”。

它负责：

1. 公司新闻：
   - `is_company_related_item`
   - `filter_company_news_items`
   - `build_company_news_response`
2. 行业新闻：
   - `filter_industry_news_items`
3. 对比新闻：
   - `build_comparative_news_items`

可以把它理解成“同一套 normalize 后，按不同 feed 套不同策略”。

### `filtering.py`

这是纯规则常量文件。

它定义：

1. 分类 `CATEGORIES`
2. AI 相关术语 `AI_TERMS`
3. CAPEX 相关术语 `CAPEX_TERMS`
4. 屏蔽域名 `BLOCKED_OR_PAYWALL_DOMAINS`
5. 噪声词 `EXCLUDED_NOISE_TERMS`

如果你要调分类词典，先改这个文件。

### `sources.py`

这是资源和静态配置文件。

它定义：

1. `OFFICIAL_COMPANY_SOURCES`
2. `OFFICIAL_NEWS_KEYWORDS`
3. `FALLBACK_COMPANY_NEWS`
4. `FALLBACK_INDUSTRY_NEWS`

`OFFICIAL_COMPANY_SOURCES` 里每家公司目前有这些字段：

1. `name`
2. `domain`
3. `base_url`
4. `news_url`
5. `rss_url`
6. `public_news_url`
7. `aliases`
8. `disable_html_scan`

如果你要新增公司官方源、修 RSS、修官网入口，先改这个文件。

### `query_helpers.py`

这是 query 生成层。

它负责：

1. 生成公司别名列表。
2. 生成 alias OR query。
3. 生成 site-scoped 官方 query。
4. 生成公司简称映射。

如果搜索 query 不准、别名不够、site query 需要调整，先看这里。

### `normalizer.py`

这是共享排序和时间解析文件。

它负责：

1. 解析发布时间。
2. 定义域名到显示 source label 的映射。
3. 按发布时间和 relevance_score 排序。

### `content_signals.py`

这是行业新闻过滤用的轻量信号层。

它负责：

1. 判断是否提到 tracked company。
2. 判断是否 AI / data center 相关。

## 6. 真正的入口和路由关系

### 6.1 主入口

`backend/main.py` 中：

```python
app.include_router(news_router, prefix="/api", tags=["News"])
```

这里接入的是 `backend/news/routes.py`。

所以真正的主接口是：

1. `/api/news/company/{ticker}`
2. `/api/news/industry`
3. `/api/news/comparative`
4. `/api/news/all`

### 6.2 非本模块实时链路

`backend/api/routes/intelligence.py` 中也有：

1. `/api/intelligence/news/all`
2. `/api/intelligence/news/industry`
3. `/api/intelligence/news/press-releases`
4. `/api/intelligence/news/ocp`

这些接口返回的是静态监控数据，不走 `backend/news` 的实时抓取流程。

---

## 7. 主链路执行顺序

下面只讲 `/api/news/*` 主链路。

### 7.1 公司新闻：`GET /api/news/company/{ticker}`

调用顺序如下：

1. `routes.py:get_company_news()`
2. `get_news_feed()` 创建或复用 `NewsFeed` 单例
3. `NewsFeed.get_company_news()`
4. `company_news_service.py:build_company_news_payload()`

接着进入真正逻辑。

#### 第一步：先看缓存，不自动抓

公司新闻的默认策略不是“没缓存就抓”，而是：

1. `force_refresh=false`
2. 如果 cache hit，直接返回缓存
3. 如果 cache miss，返回空结果加：
   - `cache_only: true`
   - `refresh_required: true`

也就是说，前端或调用方需要主动触发 `force_refresh=true` 才会真的去抓外部源。

#### 第二步：生成查询计划

`company_news_service.py` 会先做这些事：

1. 读取公司名和 aliases
2. 通过 `build_company_alias_query()` 生成 OR 别名块
3. 拼出三组 query pattern：
   - `broad_news`
   - `official_releases`
   - `newsroom_channels`
4. 去重、清洗，得到 `company_queries`

#### 第三步：按来源抓候选

来源按这 4 类收集：

1. `official`
2. `public_board`
3. `brave`
4. `google_rss`

执行顺序是：

1. 先抓 `official`
2. 再抓 `public_board`
3. 再并发 fan-out `brave`
4. 再并发 fan-out `google_rss`

这里“并发”的含义是：

1. 对每个 query 创建 task
2. 用 `asyncio.gather(..., return_exceptions=True)` 收集
3. 单个 query 报错不会让整批失败

#### 第四步：官方源内部还有一层 tier 顺序

`source_fetchers.py` 里，官方源不是一个来源，而是多个候选 tier 合并：

1. `rss_candidates`
2. `site_query_candidates`
3. `sitemap_candidates`
4. `html_scan_candidates`
5. `seed_candidates`

这些 tier 的含义：

1. `rss_candidates`：公司官方 RSS
2. `site_query_candidates`：Google News RSS 的 `site:domain` 查询
3. `sitemap_candidates`：主要给 FLEX 从 sitemap 直接提新闻 URL
4. `html_scan_candidates`：扫官网新闻页上的链接
5. `seed_candidates`：官网新闻页本身兜底成一条 item

官方源最终按上面顺序 merge，强候选优先。

#### 第五步：标准化

所有来源结果进入 `normalize_result()`：

1. 补统一字段
2. 过滤 paywall / blocked domain
3. 过滤噪声词
4. 推断 source
5. 分类
6. 算 relevance_score

#### 第六步：全局合并

标准化之后进入全局 merge。

公司新闻的来源优先级固定为：

1. `official`
2. `public_board`
3. `brave`
4. `google_rss`

merge 规则是：

1. exact identity 去重
2. identity key = `(url.lower(), title.lower())`
3. source-order first-win

也就是同一条新闻被多个来源抓到时，谁先出现就算谁赢。

#### 第七步：候选数量封顶

为了防止 fan-out 过大，`company_news_service.py` 会：

1. 先根据请求 count 算 `raw_target_count`
2. 再算 `merge_cap`
3. 如果合并后超过 cap，则按 `published + relevance_score` 排序后截断

#### 第八步：公司相关性过滤

`filter_company_news_items()` 会做：

1. 去重
2. 用 alias 判断标题/描述是否提到公司
3. 或者 URL 域名是否落在公司官方域名
4. 或者 source 是否带公司名

然后再做一次按时间和 relevance 排序。

#### 第九步：不足时补 fallback

如果过滤后条数低于阈值，就会启用 `FALLBACK_COMPANY_NEWS`。

流程是：

1. normalize fallback
2. 和现有候选池再做一次 source-order merge
3. 再走一次 company filter

这里 fallback 是最后一层兜底，不参与正常优先级竞争。

#### 第十步：写缓存并返回

最后会：

1. 把 raw 结果写到 `_runtime_cache["company:{ticker}:raw"]`
2. 失效掉 `/news/all` 相关 aggregate cache
3. 持久化到 `data/news_cache/company_news.json`
4. 通过 `build_company_news_response()` 再做 category post-filter 和 count 截断

所以公司新闻链路的完整顺序是：

```text
Route
-> NewsFeed facade
-> cache check
-> query planning
-> official/public/search/rss fetch
-> normalize
-> source-order merge
-> cap
-> company filter
-> fallback
-> persist cache
-> category filter for response
-> return
```

### 7.2 行业新闻：`GET /api/news/industry`

调用顺序：

1. `routes.py:get_industry_news()`
2. `NewsFeed.get_industry_news()`
3. `industry_news_service.py:build_industry_news_payload()`

执行机制：

1. 先查 `_runtime_cache["industry:{count}"]`
2. 默认不抓 live，cache miss 时返回 `refresh_required`
3. `force_refresh=true` 时才真正抓取
4. 使用固定 query 列表
5. 每个 query 顺序执行：
   - Brave Search
   - Google News RSS
6. 所有结果统一 `normalize_result()`
7. 用 `filter_industry_news_items()` 保留 AI / tracked-company 相关内容
8. 如果结果为空，用 `FALLBACK_INDUSTRY_NEWS`
9. 写 `data/news_cache/industry_news.json`

这条链路和公司新闻相比，缺少：

1. 来源优先级 merge trace
2. query diagnostics
3. source-flow diagnostics
4. 细粒度 fallback 追踪

### 7.3 对比新闻：`GET /api/news/comparative`

调用顺序：

1. `routes.py:get_comparative_news()`
2. `NewsFeed.get_competitor_comparison_news()`
3. `comparative_news_service.py:build_comparative_news_payload()`

执行机制：

1. 先查 `_runtime_cache["comparative"]`
2. 默认 cache-only，miss 时返回 `refresh_required`
3. `force_refresh=true` 时抓 live
4. 基于 tracked company 名称生成一个 comparison query
5. 抓 Brave Search + Google News RSS
6. 用 `build_comparative_news_items()`：
   - normalize
   - 检查是否至少提到 2 家公司
   - 生成 `companies_mentioned`
7. 如果没有结果，使用内置 fallback
8. 写 `data/news_cache/comparative_news.json`

### 7.4 聚合新闻：`GET /api/news/all`

调用顺序：

1. `routes.py:get_all_news()`
2. `NewsFeed.get_all_companies_news()`

执行机制：

1. 先查内存 `_aggregate_cache["all:{count_per_company}"]`
2. 如果 miss，顺序遍历 `COMPANIES`
3. 对每个 ticker 调一次 `get_company_news()`
4. 如果本轮是 `force_refresh=true`，每家公司之间 sleep `0.5s`
5. 最终拼成 `companies` 字典

注意：

1. `/news/all` 只缓存聚合结果，不单独持久化到 JSON。
2. 它依赖公司新闻缓存。
3. 任意公司新闻 refresh 后会主动失效 `all:` 前缀聚合缓存。

---

## 8. 底层抓取层到底有哪些资源

`source_fetchers.py` 当前接的外部资源有这些：

1. 公司官方 RSS
2. Google News RSS
3. 公司官网新闻页 HTML
4. Flex sitemap
5. Public.com 公司 news board
6. Google News redirect 目标页
7. Brave Search API

其中：

1. Brave Search API 不在 `backend/news` 里实现，实际调用在 `backend/rag/web_search.py`
2. `backend/news` 只是把它作为外部搜索能力接进来

### 8.1 官方资源配置来自哪里

官方资源统一配置在 `sources.py:OFFICIAL_COMPANY_SOURCES`。

当前跟踪公司包括：

1. FLEX
2. JBL
3. BHE
4. SANM
5. CLS
6. PLXS

每家公司是否启用 HTML scan、有没有 Public.com 页面、有没有 RSS，都由这里决定。

### 8.2 抓取规则来自哪里

规则不是集中在一个文件，而是分散在 4 类文件里：

1. `sources.py`
   - 官方源地址
   - fallback 数据
   - official news keywords
2. `filtering.py`
   - 分类词典
   - AI / CAPEX 关键词
   - 屏蔽域名
   - 噪声词
3. `query_helpers.py`
   - alias 规则
   - site query 规则
4. `company_news_service.py`
   - query pattern
   - source bucket 顺序
   - merge cap
   - fallback threshold

---

## 9. 分类、命名和文件夹划分是怎么来的

`backend/news` 的命名方式基本遵循“领域 + 层级职责”。

### 9.1 为什么有 `company_`、`industry_`、`comparative_`

因为这三个不是数据源，而是三种业务视角：

1. 单公司新闻
2. 行业主题新闻
3. 多公司对比新闻

所以它们被拆成三个 service 文件，而不是塞进一个大文件。

### 9.2 为什么有 `source_fetchers.py` 和 `source_parsing.py`

因为抓取和解析是两层不同职责：

1. `source_fetchers.py` 负责请求和收原始内容
2. `source_parsing.py` 负责从标题、HTML、URL 里抽 publisher / link / image

这样做的好处是：

1. 修网络抓取问题时不用动解析逻辑
2. 修 source 抽取问题时不用动 HTTP 请求逻辑

### 9.3 为什么有 `news_filters.py` 和 `news_filter_policies.py`

因为这里也拆成了两层：

1. `news_filters.py` 是共享 normalize 和通用过滤
2. `news_filter_policies.py` 是按 feed 类型定制策略

这意味着：

1. 通用字段统一在一个地方维护
2. 公司 / 行业 / 对比的筛选标准可以分开演进

### 9.4 为什么有 `sources.py` 和 `filtering.py`

因为这两个文件保存的是两种不同的“规则资源”：

1. `sources.py` 偏“来源配置和静态 fallback 数据”
2. `filtering.py` 偏“分类词典和过滤关键词”

### 9.5 为什么 cache 文件按公司/行业/对比分开

在 `service.py` 中，缓存被拆成：

1. `company_news.json`
2. `industry_news.json`
3. `comparative_news.json`

这样拆的原因是：

1. 公司新闻量最大，更新最频繁
2. 行业和对比新闻结构不同
3. 分开持久化更容易迁移和排错

---

## 10. 模块里的“模式”

当前主链路里有几种很明确的实现模式。

### 10.1 cache-first but not auto-refresh

默认不主动抓 live。

规则是：

1. `force_refresh=false` 时只看缓存
2. miss 就返回空结果和 `refresh_required`
3. `force_refresh=true` 才会真的拉外部源

这是当前 News 模块最重要的运行模式。

### 10.2 source-local normalize, then global merge

不是先全局混一起再处理，而是：

1. 每个来源先独立 normalize
2. 再进入全局 merge

这样 diagnostics 更清楚，方便看每个来源的损耗。

### 10.3 source-order first-win

公司新闻主链路使用固定来源优先级：

1. official
2. public_board
3. brave
4. google_rss
5. fallback

同一条新闻谁先赢，后面的重复来源直接丢掉。

### 10.4 post-fetch category filtering

公司新闻的分类过滤不是抓取时做，而是：

1. 先抓一批 broad company-linked items
2. 再通过 `build_company_news_response()` 做 category filter

这样缓存里保留的是 raw broad pool，不是某个 category 的窄结果。

### 10.5 graceful degradation

当前代码尽量避免“一个源失败，整个请求失败”。

具体表现是：

1. `asyncio.gather(..., return_exceptions=True)`
2. 单个 query 报错只记 diagnostics
3. 某个官方源失败不影响其他源
4. live 结果太少时走 fallback

---

## 11. 缓存和持久化机制

### 11.1 内存缓存

`NewsFeed` 维护 3 类运行期缓存：

1. `_runtime_cache`
   - 主缓存
   - 存公司 / 行业 / 对比新闻 raw payload
2. `_aggregate_cache`
   - 只存 `/news/all` 这种聚合结果
3. `_google_redirect_cache`
   - Google News redirect URL 解析结果

### 11.2 持久化缓存

结构化缓存文件位置：

```text
data/news_cache/
├── company_news.json
├── industry_news.json
└── comparative_news.json
```

缓存 key 形态：

1. 公司新闻：`company:{ticker}:raw`
2. 行业新闻：`industry:{count}`
3. 对比新闻：`comparative`
4. 聚合新闻：`all:{count_per_company}`，只在内存，不落盘

### 11.3 旧缓存迁移

如果历史上存在：

```text
data/news_runtime_cache.json
```

`service.py` 会尝试迁移成新的结构化缓存文件，然后删掉旧文件。

### 11.4 TTL

`NewsFeed` 当前 `_cache_ttl = 3600` 秒。

但要注意：

1. TTL 主要用于判断缓存是否新鲜
2. 当前各条 service 在 `force_refresh=false` 时并不会主动基于 TTL 补抓 live
3. 也就是说，这里更像 freshness metadata，不是完整的 auto-refresh 调度器

---

## 12. 当前完成度

### 12.1 已经比较完整的部分

当前最完整的是公司新闻主链路，已经具备：

1. 多源抓取
2. 官方源优先
3. query fan-out
4. normalize
5. exact 去重
6. source-order merge
7. 公司相关性过滤
8. fallback
9. diagnostics
10. 结构化缓存持久化

### 12.2 已完成但仍偏轻量的部分

1. 行业新闻链路可用，但规则还比较粗
2. 对比新闻链路可用，但 query 和判定逻辑都比较轻量
3. Google News redirect 解析可用，但仍是 best-effort

### 12.3 还明显需要补的部分

当前最值得继续完成的部分有 5 个：

1. 给行业新闻和对比新闻补齐 diagnostics parity
   - 现在公司新闻最完整，另外两条链路信息太少
2. 补测试
   - 当前仓库里没有看到 `backend/news` 的专门测试文件
3. 补自动刷新机制
   - 现在 cache miss 时默认只返回 `refresh_required`
4. 提升相关性判断
   - 目前公司相关性仍是 alias / domain / source 的轻规则
5. 继续提升 source 质量
   - 主要集中在官网扫描、publisher 提取、行业 query 精度

---

## 13. 如果要升级修改，先改哪个文件

这个问题要分两种情况回答。

### 13.1 如果你要改主 `/api/news/*` 的结果质量

第一站先看：

`backend/news/company_news_service.py`

原因：

1. 它控制公司新闻 query 怎么生成。
2. 它控制来源顺序。
3. 它控制 merge cap 和 fallback threshold。
4. 它决定最终 diagnostics 长什么样。
5. `/api/news/all` 也是间接依赖这条链路。

换句话说，主链路里“结果为什么是这样”，大多数都要回到这个文件。

### 13.2 如果你要做整体架构升级

第一站先处理：

1. `backend/news/service.py`
2. `backend/news/company_news_service.py`

原因：

1. 旧聚合链路已经移除。
2. 现在所有新闻主能力都汇总到 `NewsFeed` 主链路。
3. 架构升级主要会落在缓存结构、service facade 和编排策略上。

---

## 14. 不同修改目标对应先看哪个文件

### 想改路由或增加新接口

先看：`routes.py`

作用：定义 `/api/news/*` 的 API 入口和参数规范。

### 想改缓存读写、缓存文件结构、聚合缓存失效

先看：`service.py`

作用：`NewsFeed` facade、cache manager、structured cache persistence。

### 想改公司新闻抓取顺序、阈值、来源优先级、fallback 机制

先看：`company_news_service.py`

作用：主链路编排中心。

### 想给某家公司加官方源、修官网地址、加 alias、禁用 HTML scan

先看：`sources.py`

作用：来源配置与 fallback 静态资源。

### 想修外部抓取失败、RSS 解析、官网扫描、Google redirect

先看：`source_fetchers.py`

作用：底层抓取与 source diagnostics。

### 想修 source 名字错误、标题尾巴 publisher 抽取不准、Google description 解析不准

先看：`source_parsing.py`

作用：publisher / URL / image 抽取规则。

### 想改 category 分类、blocked domain、噪声词

先看：

1. `filtering.py`
2. `news_filters.py`

作用：

1. `filtering.py` 定义词典
2. `news_filters.py` 把词典应用到 normalize 和分类

### 想改公司相关性判断、行业保留规则、对比新闻判定规则

先看：`news_filter_policies.py`

作用：按 feed 类型应用不同过滤策略。

### 想补行业新闻或对比新闻能力

先看：

1. `industry_news_service.py`
2. `comparative_news_service.py`

作用：两条轻量链路的编排层。

## 15. 推荐升级顺序

如果现在要继续把 News 模块做稳，推荐按下面顺序推进。

### P0：补齐行业 / 对比链路

目标：

1. 给 `industry_news_service.py` 和 `comparative_news_service.py` 加 source diagnostics
2. 引入更清楚的 merge / fallback trace
3. 和公司新闻返回结构尽量对齐

### P1：提升抓取质量

目标：

1. 增强 `source_fetchers.py` 的官网扫描质量
2. 增强 `source_parsing.py` 的 publisher 解析
3. 增强 `news_filter_policies.py` 的相关性判断

### P2：补测试和运维能力

目标：

1. 为 normalize / source parsing / cache migration 加单元测试
2. 为公司新闻主链路加 mocked integration test
3. 为 cache miss -> refresh_required 语义补回归测试

---

## 16. 一句话维护指南

维护 `backend/news` 时，先记住下面 4 句就够了：

1. 主接口看 `routes.py + service.py + company_news_service.py`
2. 真正抓外部源看 `source_fetchers.py`
3. 真正统一字段和过滤看 `news_filters.py + news_filter_policies.py`
4. 当前的主要改进空间在行业链路、对比链路和测试覆盖
