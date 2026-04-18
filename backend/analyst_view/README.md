# Analyst View 模块 — 技术说明文档

## 一、模块概述

`analyst_view` 是面向华尔街卖方分析师覆盖追踪的后端模块，核心功能是通过 Brave 搜索引擎实时抓取分析师动态，经过 LLM 提炼后，向前端提供结构化的分析师观点、评级变化、价格目标、主题归纳等数据。

覆盖范围：
- **EMS 公司（6家）**：Flex、Jabil、Celestica、Foxconn、BYD Electronic、Sanmina
- **超大规模云厂商（6家）**：Amazon、Microsoft、Google、Meta、Apple、Tesla（作为 CapEx 基准参照）

---

## 二、文件结构与架构

```
analyst_view/
├── __init__.py          # 模块入口
├── config.py            # 搜索关键词配置（Brave 查询模板）
├── db.py                # SQLite 持久化层（三张表）
├── service.py           # 核心业务逻辑（公司情报 + 分析师摘要）
├── quotes_service.py    # 财报引述提取 + 偏差标记
├── themes_service.py    # 每周主题生成（Claude 驱动）
└── routes.py            # FastAPI 路由（15个端点）
```

### 数据流架构

```
Brave Search API
      │
      ▼
  service.py              ─────────────────────────────────────────────────────┐
  ├── get_all_company_intel()     (12家公司 × N条搜索结果 → LLM提炼)              │
  └── get_all_analyst_summaries() (19位分析师 → 去重 → 批量LLM摘要)              │
                                                                               │
ChromaDB (财报向量库)                                                            ▼
      │                                                               analytics_cache (30分钟)
      ▼                                                               api_cache (10分钟)
 quotes_service.py
  ├── extract_quotes_for_company()  (LLM提取关键问答)
  ├── fetch_key_quotes()            (从SQLite读取)
  └── compute_divergence_flags()   (解析价格目标偏差)

      │
      ▼
   db.py (SQLite: /data/analyst_intel.db)
  ├── weekly_themes    ← themes_service.py 写入
  ├── key_quotes       ← quotes_service.py 写入
  └── sentiment_snaps  ← ⚠️ 已建表但从未写入（见问题说明）

      │
      ▼
   routes.py (15个 FastAPI 端点，前缀 /api/analyst-view/...)
```

**注册位置**：`backend/main.py` 第88行
```python
app.include_router(analyst_view_router, prefix="/api", tags=["Analyst View"])
```

---

## 三、已实现功能与 API 端点

### 3.1 对外 REST 端点（共15个）

| 端点 | 方法 | 功能说明 |
|------|------|----------|
| `/analyst-view/company-intel` | GET | 12家公司的分析师共识、目标价、近期动作、核心观点（LLM提炼） |
| `/analyst-view/analyst-summaries` | GET | 19位分析师的近期评论摘要（每人一句话） |
| `/analyst-view/signals` | GET | Brave 实时新闻信号流（最多25条，5条查询去重） |
| `/analyst-view/ratings-feed` | GET | 聚合评级变化（含颜色编码），来源于公司情报 |
| `/analyst-view/consensus` | GET | 单一股票代码的共识数据查询 |
| `/analyst-view/coverage-map` | GET | 19位分析师 × 12家公司覆盖矩阵（静态硬编码） |
| `/analyst-view/divergence-flags` | GET | 价格目标偏离共识超过20%的异常分析师标记 |
| `/analyst-view/weekly-themes` | GET | Claude生成的5个战略主题 + 历史记录 |
| `/analyst-view/generate-weekly-themes` | POST | 强制重新生成本周战略主题 |
| `/analyst-view/key-quotes` | GET | 财报问答关键引述（可按公司/主题/日期范围过滤） |
| `/analyst-view/extract-quotes` | POST | 从财报文本或ChromaDB提取关键问答并存入数据库 |
| `/analyst-view/flex-benchmark` | GET | Flex 与 EMS 同行的共识评分排名对比 |
| `/analyst-view/earnings-calendar` | GET | 即将/近期财报日期（Brave搜索获取） |
| `/analyst-view/sentiment-timeline` | GET | 按季度的历史共识评分趋势（⚠️ 实为模拟数据，见问题说明） |
| `/analyst-view/coverage-map` | GET | 覆盖矩阵（静态数据） |

### 3.2 分析师覆盖名单

覆盖19位分析师，来自12家机构：
- BMO Capital、Stifel、JPMorgan、Baird、Needham
- Morgan Stanley、Goldman Sachs、Barclays、Deutsche Bank
- Raymond James、Wells Fargo、UBS

### 3.3 关键问答主题（6类）

`quotes_service.py` 预设6个战略主题，用于从财报中提取管理层表态：
1. CapEx & Investment（资本支出与投资）
2. AI/Data Center（人工智能/数据中心）
3. Geographic Expansion（地域扩展）
4. Margins & Profitability（利润率与盈利能力）
5. Customer Concentration（客户集中度）
6. Supply Chain（供应链）

---

## 四、外部依赖与技术栈

### 外部 API
| 服务 | 用途 | 限制 |
|------|------|------|
| **Brave Search API** | 实时抓取分析师报道、财报日期、新闻信号 | 免费层1 req/s，使用 `Semaphore(1)` + 1.1秒延迟控制 |
| **OpenAI** (gpt-4o / gpt-4o-mini) | 结构化数据提炼（默认LLM） | 需要 API Key |
| **Anthropic** (claude-sonnet-4-6) | 结构化数据提炼 + 主题生成 | 需要 API Key |
| **Google Gemini** (gemini-2.5-flash) | 结构化数据提炼（备用） | 需要 API Key |

LLM 提供商根据可用 API Key 自动切换（优先级：Anthropic → OpenAI → Gemini）。

### 内部依赖
| 模块 | 作用 |
|------|------|
| `backend.core.cache` | `analytics_cache`（30分钟）+ `api_cache`（10分钟）内存缓存 |
| `backend.core.config` | 读取 `BRAVE_API_KEY`、LLM 配置 |
| `backend.core.llm_client` | `llm_structured()` — 统一的结构化LLM调用 |
| `backend.core.database` | ChromaDB 客户端 + `embed_text()` 向量化 |
| `backend.rag.web_search` | Brave Search 封装 |

### 持久化
- **SQLite**：`/data/analyst_intel.db`（WAL模式）
  - `weekly_themes`：每周战略主题（**实际使用**）
  - `key_quotes`：财报关键问答（**实际使用**）
  - `sentiment_snaps`：历史共识快照（**建表但从未写入**）

---

## 五、已知问题与 Bug

### 🔴 严重问题

#### 问题1：缓存 TTL 参数被完全忽略
**文件**：[backend/core/cache.py](../core/cache.py)

`cache.set(key, value, ttl=X)` 中的 `ttl` 参数在实现中**从未被使用**，缓存永远使用默认 TTL。所有需要自定义过期时间的调用均失效。

```python
# 当前实现（有 bug）
def set(self, key, value, ttl=None):
    self._cache[key] = value
    self._timestamps[key] = datetime.now().timestamp()
    # ttl 参数完全没有被使用！
```

---

### 🟠 高优先级问题

#### 问题2：情感时间线返回的是随机模拟数据
**文件**：[routes.py](routes.py)（第338-354行）

`/sentiment-timeline` 端点用 `random.seed(ticker)` 生成一个随机游走序列来伪造历史评分，**不是真实的历史数据**。

- `db.py` 中定义的 `upsert_sentiment_snap()` 和 `get_sentiment_timeline()` **从未被调用**
- `sentiment_snaps` 表永远是空的
- 前端展示的"历史趋势"实际上是每次请求固定的伪数据

#### 问题3：财报日历和情感时间线的年份硬编码为2025年
**文件**：[routes.py](routes.py)（第257行、第342行）

```python
# earnings_calendar 端点
query = f"{company} {ticker} earnings date Q2 Q3 2025"  # 应为 2026

# sentiment_timeline 端点
year, q = 2025, 2  # 应根据 datetime.now() 动态计算
```

当前日期为2026年4月，但查询的是2025年的数据，导致财报日历结果不准确。

#### 问题4：除零风险（Divergence Flags）
**文件**：[quotes_service.py](quotes_service.py)（第261行）

```python
divergence_pct = (analyst_pt - consensus_pt) / consensus_pt * 100
# 若共识价格目标被解析为 $0，将触发 ZeroDivisionError
```

未做 `consensus_pt > 0` 的保护判断。

---

### 🟡 中等优先级问题

#### 问题5：分析师名称解析逻辑过于脆弱
**文件**：[quotes_service.py](quotes_service.py)（第265行）

```python
analyst_name = action.split(":")[0].split("raised")[0].split("cut")[0].strip()
```

这个启发式解析只对包含 "raised" 或 "cut" 的动作字符串有效。对于 "JPMorgan initiated coverage at Overweight" 这类字符串，会把整句话当作分析师名称，导致 divergence_flags 返回的分析师名称格式混乱。

#### 问题6：异常被静默吞掉
**文件**：[quotes_service.py](quotes_service.py)（第121行）

```python
except Exception:
    return ""  # ChromaDB 查询失败时无任何日志
```

ChromaDB 搜索发生网络错误或数据库异常时完全静默，无法排查问题。

---

### 🟢 低优先级问题

#### 问题7：coverage-map 覆盖矩阵为静态硬编码
**文件**：[routes.py](routes.py)（第60-80行）

19位分析师与12家公司的覆盖关系为硬编码字典，无法动态更新，也不与真实的分析师动态联动。

---

## 六、未实现 / 占位功能

| 功能 | 说明 |
|------|------|
| **历史情感趋势持久化** | `sentiment_snaps` 表已建，相关数据库函数已写，但整个写入流程从未被触发。端点返回假数据代替。 |
| **动态覆盖矩阵** | 分析师对公司的覆盖关系应来源于真实评级数据，目前为静态配置 |
| **偏差标记的LLM智能解析** | 分析师名称和价格目标当前依赖正则/字符串分割，应改为LLM提取更健壮 |
| **财报日历的结构化存储** | 财报日期通过Brave实时搜索获取，无持久化，无历史记录 |

---

## 七、整体评价

- **已实现端点**：15个，全部可访问，主要流程均跑通
- **代码结构**：清晰，Pydantic 模型、缓存、LLM 调用均有良好封装
- **最大问题**：情感时间线是假数据，财报日历年份过时，Cache TTL 实现有缺陷
- **次要问题**：解析逻辑脆弱，异常处理不完善，覆盖矩阵无法动态更新

---

*最后更新：2026年4月13日*
