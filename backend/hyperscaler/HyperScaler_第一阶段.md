# HyperScaler 第一阶段

最后更新：2026-05-01

## 1. 目标

第一阶段把 HyperScaler 页面的数据链路改成两条明确的来源：

```text
1. 上方页面数据（公司卡片、图表、Stargate）
   Gemini API（固定问题模板）
   -> 后端解析整理
   -> 写入本地缓存
   -> 前端展示

2. 底部 Historical CapEx Trend
   yfinance
   -> backend/hyperscaler/financials.py
   -> 前端折线图
```

同时把所有相关后端逻辑收口到 `backend/hyperscaler/`，断开旧的散落实现。

---

## 2. 页面范围

前端页面路径不变：

```text
frontend/src/app/ai-investments/page.tsx
```

前端请求路径不变：

```text
GET    /api/intelligence/big5-capex
DELETE /api/intelligence/hyperscaler/guidance/cache
GET    /api/intelligence/hyperscaler/all/financials
```

必须保留的页面区域：

- 页面标题 `Hyperscaler CapEx`
- 副标题 `FY2026 AI Infrastructure Spending`
- `Updated` badge
- `Refresh Guidance` 按钮和刷新状态文字
- 公司选择卡片
- `AI Investment Details`
- `Key Metrics`
- `AI Focus Subdomains`
- `Recent Announcements`
- `Total 2026 CapEx`
- `YoY Growth (Avg)`
- `Stargate Project`
- `Planned Capacity`
- `2025 vs 2026 CapEx Comparison`
- `2026 CapEx Distribution`
- `Historical CapEx Trend`
- `Source: yfinance (live)` badge
- Historical chart 内部 `Refresh` 按钮
- Historical chart 下方每家公司最新 CapEx 小卡片

---

## 3. 数据来源与图表颜色规则

### 3.1 两类数据

| 数据类型 | 来源 | 含义 |
|---|---|---|
| 2026 年 CapEx 展望值 | Gemini API | 预期值，会随财报更新而变化 |
| 历史年份数据（2024 及以前） | yfinance | 已公布财报数字，固定不变 |

### 3.2 颜色标注

图表中两类数据必须用不同颜色区分：

- **2026 展望值（Gemini 来源）**：用高亮色，例如橙色或金色，表示"预期/展望"
- **历史数据（yfinance 来源）**：用各公司固定品牌色

当前代码里公司品牌色有错误，第一阶段必须核对并修正：

```text
AMZN  #FF9900
MSFT  #00A4EF
GOOGL #4285F4
META  #0866FF
ORCL  #F80000
```

### 3.3 数据更新规则

- 2025 年及以前的历史数据：来自 yfinance，固定不变，不需要更新
- 2026 年展望值：来自 Gemini，定期通过点击 `Refresh Guidance` 更新
- 2026 年数据是展望值，页面上需要有明确标注（如 badge 或说明文字）

---

## 4. Gemini 问题模板

### 4.1 第一阶段使用的问题

固定在 `backend/hyperscaler/questions.py` 中，不允许前端传问题。

第一阶段推荐主问题：

```text
Search for the latest 2026 capital expenditure outlook for these five companies:
Amazon (AWS), Microsoft (Azure), Alphabet (Google Cloud), Meta, and Oracle (OCI).

For each company, return:
- company name and ticker
- latest 2026 full-year CapEx outlook in USD billions
- comparable 2025 CapEx in USD billions if stated
- YoY growth percentage if stated or calculable from sourced numbers
- AI infrastructure focus areas explicitly mentioned
- recent announcements related to AI infrastructure or cloud expansion
- any key metrics explicitly mentioned (e.g. revenue, growth rate)

Also return any details about the Stargate project if mentioned:
- total investment amount
- partners
- timeline
- planned capacity
- locations

Return JSON only. If a value is not explicitly available, return null, [], or {}.
Do not estimate. Do not use outside knowledge beyond what is in recent search results.
```

### 4.2 Gemini 期望返回结构

```json
{
  "companies": [
    {
      "ticker": "AMZN",
      "name": "Amazon",
      "capex_2026_billions": 200.0,
      "capex_2025_billions": 104.0,
      "yoy_growth_pct": 92,
      "ai_focus_areas": ["AWS infrastructure", "AI compute clusters"],
      "recent_announcements": ["Q1 2026 CapEx exceeded $44B in a single quarter"],
      "key_metrics": {"aws_quarterly_capex_billions": 44.0}
    }
  ],
  "stargate_project": {
    "total_investment_billions": 500,
    "partners": ["OpenAI", "SoftBank", "Oracle"],
    "timeline": "2025-2029",
    "planned_capacity_gw": 5.0,
    "locations": ["Texas", "Arizona"]
  },
  "sources": []
}
```

### 4.3 第一阶段问题模板的限制

第一阶段只用一个主问题，不拆分多个问题。第二阶段再优化问题边界和多问题组合策略。

---

## 5. 后端模块结构

```text
backend/hyperscaler/
  __init__.py      空文件，标识 Python 包
  models.py        Pydantic 模型
  questions.py     固定 Gemini 问题模板
  gemini_client.py 封装 Gemini API 调用
  service.py       解析 Gemini 回答，归一化，写缓存
  cache.py         读写缓存文件
  financials.py    yfinance Historical CapEx Trend
  routes.py        路由注册
```

### 5.1 `models.py`

只放 Pydantic 模型，不含业务逻辑。

```python
class HyperscalerCompany(BaseModel):
    name: str
    ticker: str
    color: str
    capex_2026_billions: Optional[float] = None   # Gemini 来源，展望值
    capex_2025_billions: Optional[float] = None   # yfinance 或 Gemini 来源
    yoy_growth_pct: Optional[int] = None
    ai_focus_areas: list[str] = []
    key_metrics: dict[str, float] = {}
    recent_announcements: list[str] = []

class StargateProject(BaseModel):
    total_investment_billions: Optional[float] = None
    timeline: str = ""
    partners: list[str] = []
    planned_capacity_gw: Optional[float] = None
    locations: list[str] = []

class Big5CapexResponse(BaseModel):
    companies: list[HyperscalerCompany]
    last_updated: str
    source: str = "Gemini API"
    source_status: str   # "gemini_cached" | "missing_cache"
    total_2026_capex_billions: Optional[float] = None
    stargate_project: StargateProject = StargateProject()

class HyperscalerFiscalYear(BaseModel):
    capex: Optional[float] = None
    revenue: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    operating_margin: Optional[float] = None

class HyperscalerCompanyFinancials(BaseModel):
    company: str
    ticker: str
    color: str
    fiscal_years: dict[str, HyperscalerFiscalYear] = {}
    source: str = "yfinance"
    fetched_at: str = ""
    error: Optional[str] = None

class HyperscalerFinancialsResponse(BaseModel):
    companies: list[HyperscalerCompanyFinancials]
    errors: list[str] = []
```

所有数字字段必须允许 `None`。

### 5.2 `questions.py`

只存问题模板常量，不含任何调用逻辑。

```python
BIG5_CAPEX_QUESTION: str = "..."   # 第 4.1 节的完整问题
```

### 5.3 `gemini_client.py`

只负责向 Gemini 发请求并返回原始回答字符串或 dict。不做解析，不写缓存。

```python
async def ask_gemini(question: str) -> str:
    """发送问题到 Gemini，返回原始回答文本。失败时抛异常。"""
```

### 5.4 `service.py`

负责完整的刷新流程：

```text
call gemini_client.ask_gemini(question)
-> parse JSON from response
-> normalize into HyperscalerCompany list
-> fill company color and name from COMPANY_CONFIG
-> write raw response to big5_capex_api_raw.json
-> write normalized result to big5_capex_view_model.json
-> return Big5CapexResponse
```

读取流程（页面加载时）：

```text
cache.read_view_model()
-> if None: return source_status="missing_cache" 空结构
-> normalize and return
```

公司 identity 配置（name、ticker、color）作为常量定义在 `service.py` 顶部：

```python
COMPANY_CONFIG = [
    {"ticker": "AMZN", "name": "Amazon",    "color": "#FF9900"},
    {"ticker": "MSFT", "name": "Microsoft", "color": "#00A4EF"},
    {"ticker": "GOOGL", "name": "Alphabet", "color": "#4285F4"},
    {"ticker": "META",  "name": "Meta",     "color": "#0866FF"},
    {"ticker": "ORCL",  "name": "Oracle",   "color": "#F80000"},
]

CAPEX_2026_HIGHLIGHT_COLOR = "#F59E0B"  # 展望值专用颜色，用于图表区分
```

不调用 LLM、yfinance、数据库、ChromaDB。

### 5.5 `cache.py`

只负责文件读写。

读写以下文件：

```text
data/hyperscaler/big5_capex_api_raw.json      Gemini 原始回答，调试用
data/hyperscaler/big5_capex_view_model.json   归一化后的页面数据
```

```python
def read_view_model() -> dict | None:
    """文件不存在或解析失败时返回 None，不抛异常。"""

def write_view_model(payload: dict) -> bool:
    """先写 .tmp 再 rename，保证原子性。失败返回 False，不抛异常。"""

def write_raw(payload: dict) -> bool:
    """写 Gemini 原始回答，失败不影响主流程。"""
```

### 5.6 `financials.py`

从旧位置迁移：

```text
backend/analytics/hyperscaler_financials.py  ->  backend/hyperscaler/financials.py
```

职责不变，只负责 yfinance Historical CapEx Trend 数据。

```python
def fetch_hyperscaler_financials(company: str) -> HyperscalerCompanyFinancials:
    """单个公司，失败时返回含 error 字段的对象，不抛异常。"""

def fetch_all_hyperscaler_financials() -> HyperscalerFinancialsResponse:
    """所有 5 家公司，单个失败不影响其他。"""

def invalidate_financials_cache(company: str | None = None) -> None:
    """清除内存缓存。"""
```

不读写 `big5_capex_view_model.json`。

### 5.7 `routes.py`

只负责路由，每个 handler 不超过 10 行。

```text
GET    /big5-capex                        读 view_model 缓存返回
GET    /big5-capex/summary                基于缓存做简单汇总
DELETE /hyperscaler/guidance/cache        触发 Gemini 重新调用并覆盖缓存
GET    /hyperscaler/all/financials        调 financials.py 返回 yfinance 数据
GET    /hyperscaler/{company}/financials  单公司 yfinance 数据
DELETE /hyperscaler/cache                 清除 yfinance 内存缓存
```

挂载后完整路径：

```text
GET    /api/intelligence/big5-capex
GET    /api/intelligence/big5-capex/summary
DELETE /api/intelligence/hyperscaler/guidance/cache
GET    /api/intelligence/hyperscaler/all/financials
GET    /api/intelligence/hyperscaler/{company}/financials
DELETE /api/intelligence/hyperscaler/cache
```

不在 `routes.py` 里直接调用 Gemini、yfinance 或文件 I/O。

---

## 6. 缓存规则

缓存目录：

```text
data/hyperscaler/
```

第一阶段缓存文件：

```text
data/hyperscaler/big5_capex_api_raw.json      Gemini 原始回答
data/hyperscaler/big5_capex_view_model.json   页面使用的归一化数据
```

规则：

- 页面加载：只读 `view_model`，不调 Gemini
- 点击 Refresh Guidance：重新调 Gemini，覆盖两个缓存文件
- Gemini 调用失败：保留上一次的 `view_model`，不覆盖
- 缓存不存在：返回 `source_status: "missing_cache"` 空结构，不报错
- 字段缺失：`null` / `[]` / `{}` / `""`，不补硬编码数字

---

## 7. Refresh 行为

顶部 `Refresh Guidance` 按钮触发：

```text
DELETE /api/intelligence/hyperscaler/guidance/cache
-> 后端调用 Gemini API
-> 更新 big5_capex_api_raw.json
-> 更新 big5_capex_view_model.json
-> 前端重新 GET /api/intelligence/big5-capex
```

前端交互状态必须保留：

- `refreshing`
- `Fetching latest...`
- `Updated: ...`
- `No changes — data is current.`
- `Failed to fetch latest data.`
- `Error refreshing guidance data.`

底部 Historical chart 的 `Refresh` 按钮保持原样，只刷新 yfinance 数据。

---

## 8. 前端空值处理

以下字段可能为 `null`，前端必须处理：

- `data.companies` 可能为空数组
- `c.name` 可能缺失（用 ticker 兜底）
- `capex_2026_billions` 可能为 `null`
- `capex_2025_billions` 可能为 `null`
- `yoy_growth_pct` 可能为 `null`
- `stargate_project.total_investment_billions` 可能为 `null`
- `stargate_project.planned_capacity_gw` 可能为 `null`
- `key_metrics` 可能为 `{}`
- `ai_focus_areas` 可能为 `[]`
- `recent_announcements` 可能为 `[]`
- `historicalData.companies` 可能为空

图表规则：

- `CapEx Distribution`：只画有 `capex_2026_billions` 的公司，用 `CAPEX_2026_HIGHLIGHT_COLOR`
- `2025 vs 2026 Comparison`：2026 柱用高亮色，2025 柱用品牌色；只画有效数字
- `Total 2026 CapEx`：只对有效数字求和，无数据显示 `N/A`
- `YoY Growth (Avg)`：只对有效数字求平均，无数据显示 `N/A`
- 没有有效数字时保留图表卡片，显示空状态文字

2026 年展望值必须有视觉标注，例如 badge 文字：`2026 Outlook (as of [date])`

---

## 9. 旧代码处理

### 需要从 `intelligence.py` 移除的 endpoint

```text
@router.get("/big5-capex")               -> 迁移到 backend/hyperscaler/routes.py
@router.get("/big5-capex/summary")       -> 迁移到 backend/hyperscaler/routes.py
@router.delete("/hyperscaler/guidance/cache") -> 迁移到 backend/hyperscaler/routes.py
@router.get("/hyperscaler/all/financials")    -> 迁移到 backend/hyperscaler/routes.py
@router.get("/hyperscaler/{company}/financials") -> 迁移到 backend/hyperscaler/routes.py
@router.delete("/hyperscaler/cache")     -> 迁移到 backend/hyperscaler/routes.py
@router.get("/hyperscaler/all/guidance") -> 直接删除，前端未使用
```

### 需要删除的旧文件内容

```text
backend/analytics/hyperscaler_guidance.py   整个文件删除
BIG5_AI_CAPEX 硬编码数据                    删除
旧 fallback 数字                            删除
旧 Brave search 调用                        删除
data/big5_capex_seed.json                   删除
```

### 保留不动的 `intelligence.py` 内容

```text
DEFAULT_ANALYST_QUESTIONS
EMS_AI_DYNAMICS
MONITORED_NEWS
/default-questions
/ems-ai-dynamics
/competitor-investments
```

### `main.py` 挂载

新增：

```python
from backend.hyperscaler.routes import router as hyperscaler_router

app.include_router(
    hyperscaler_router,
    prefix="/api/intelligence",
    tags=["Hyperscaler"],
)
```

旧的 intelligence router 继续保留，但不能再有 hyperscaler 相关 endpoint。

---

## 10. 验收标准

### 后端接口

```bash
curl http://localhost:8001/api/intelligence/big5-capex
curl http://localhost:8001/api/intelligence/big5-capex/summary
curl http://localhost:8001/api/intelligence/hyperscaler/all/financials
curl -X DELETE http://localhost:8001/api/intelligence/hyperscaler/guidance/cache
```

旧接口不能被破坏：

```bash
curl http://localhost:8001/api/intelligence/default-questions
curl http://localhost:8001/api/intelligence/ems-ai-dynamics
curl http://localhost:8001/api/intelligence/competitor-investments
```

### 缓存文件

```text
data/hyperscaler/big5_capex_api_raw.json
data/hyperscaler/big5_capex_view_model.json
```

缓存不存在时接口不崩溃，返回 `source_status: "missing_cache"`。

### 前端

- 页面正常打开，布局不变
- 缺失数据显示 `N/A` 或空状态，不崩溃
- 2026 展望值和历史数据颜色明确区分
- 2026 数据有"展望值"标注
- Refresh Guidance 按钮正常工作
- Historical chart 和 yfinance Refresh 正常工作

### 编译检查

```bash
./.venv/bin/python -m compileall backend/hyperscaler backend/api/routes/intelligence.py backend/main.py
cd frontend && npm run build
```
