# Flex Practicum - UI Context Handoff (for AI)

Last updated: 2026-03-10 (America/Los_Angeles)

## 1) Reusable Prompt (copy this to another AI)

你现在接手 `Flex-Practicum-Project-2026` 项目，请不要全仓重读，按下面路径快速建立上下文并继续 UI 工作：

1. 先读 UI 设计规范：`docs/ui_design_new.md`
2. 再看前端页面入口（Next.js App Router）：`frontend/src/app/**/page.tsx`
3. 再看 API 封装：`frontend/src/lib/api.ts`
4. 按页面对应后端路由核对数据来源：`backend/api/routes/*.py`
5. 区分三类数据：
   - 写死/预置常量（重点：`backend/api/routes/intelligence.py`）
   - 文档检索与分析结果（RAG/analytics/sentiment/company detail）
   - 外部抓取/搜索（重点：`backend/ingestion/news_feed.py`、ingestion/earnings）
6. 先输出“页面 -> 数据来源 -> 风险点”表，再开始改 UI。

## 2) Key File Map

- UI 规范
  - `docs/ui_design_new.md`

- 前端核心
  - `frontend/src/app/dashboard/page.tsx`
  - `frontend/src/app/chat/page.tsx`
  - `frontend/src/app/companies/page.tsx`
  - `frontend/src/app/companies/[company]/page.tsx`
  - `frontend/src/app/analysis/page.tsx`
  - `frontend/src/app/analytics/page.tsx`
  - `frontend/src/app/sentiment/page.tsx`
  - `frontend/src/app/map/page.tsx`
  - `frontend/src/app/heatmap/page.tsx`
  - `frontend/src/app/news/page.tsx`
  - `frontend/src/app/news-monitor/page.tsx`
  - `frontend/src/app/calendar/page.tsx`
  - `frontend/src/app/alerts/page.tsx`
  - `frontend/src/app/reports/page.tsx`
  - `frontend/src/app/data/page.tsx`
  - `frontend/src/app/settings/page.tsx`
  - `frontend/src/components/layout/Sidebar.tsx`
  - `frontend/src/lib/api.ts`

- 后端路由核心
  - `backend/main.py`
  - `backend/api/routes/intelligence.py` (大量预置数据)
  - `backend/api/routes/analysis.py`
  - `backend/api/routes/analytics.py`
  - `backend/api/routes/sentiment.py`
  - `backend/api/routes/geographic.py`
  - `backend/api/routes/company_detail.py`
  - `backend/api/routes/dashboard.py`
  - `backend/api/routes/ingestion.py`
  - `backend/api/routes/earnings.py`
  - `backend/api/routes/reports.py`
  - `backend/api/routes/alerts.py`
  - `backend/api/routes/exports.py`
  - `backend/ingestion/news_feed.py`

- 数据与配置
  - `backend/core/config.py`
  - `backend/analytics/geographic.py` (KNOWN_FACILITIES)
  - `data/earnings_calendar.json`
  - `data/extracted_facilities.json`
  - `data/alerts.json`

## 3) Fast Classification Rules

- 看到 `backend/api/routes/intelligence.py` 返回常量：判定为“写死/预置”
- 看到 `search_documents` / `get_company_documents` / analytics.*：判定为“文件分析/RAG”
- 看到 web/news scraper（`search_web`、news feed、ingestion）：判定为“外部抓取/搜索”

## 4) Known Risk (important)

- `backend/alerts/detector.py` 中 `create_alert(...)` 的参数名与 `backend/alerts/alert_manager.py` 的函数签名不一致，`/api/alerts/detect` 可能异常。

## 5) Reusable Prompt - AI Research Chat

你现在要实现/优化 `AI Research Chat` 模块，请按下面要求执行：

1. 位置与导航
   - 该功能是侧边栏一级标签（非折叠子项）
   - 名称固定：`AI Research Chat`
   - 位置：紧跟在 `News Monitor` 后面
   - 路由：`/chat`

2. 页面定位（给用户一眼看懂）
   - 这是“聊天问问题”的入口，不是报表页
   - 页面主动作是提问：用户输入问题 -> 返回可追溯回答
   - 标题/文案必须明确是 AI 聊天助手，例如：
     - `AI Research Chat`
     - `Ask questions across filings, news, and company intelligence`

3. 背后功能逻辑（现有实现约束）
   - 前端页面：`frontend/src/app/chat/page.tsx`
   - 后端接口：`POST /api/chat`，流式可用 `POST /api/chat/stream`
   - 搜索模式：
     - `rag`：文档/SEC 为主
     - `web`：公开网页/新闻
     - `hybrid`：文档 + 网页
   - 关键输入：`query`、`mode`、`company_filter`、`session_id`
   - 关键输出：`response` + `sources`

4. 交互验收标准
   - 用户 1 次点击就能看到“这是聊天区”
   - 支持快速提问模板 + 自由输入
   - 回答展示来源（sources）且可追溯
   - 网络/后端错误时给出明确报错，不静默失败
