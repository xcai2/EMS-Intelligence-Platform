# AI Chat 前端说明

最后更新：2026-03-31（America/Los_Angeles）

## 1）前端模块结构

- frontend/src/app/chat/page.tsx
  - 路由薄入口，仅负责渲染 AI Chat 功能组件。
- frontend/src/features/chat/ChatPageFeature.tsx
  - AI Chat 主界面与前端交互逻辑。
- frontend/src/features/chat/api.ts
  - AI Chat 专用接口请求封装。

## 2）数据流

ChatPageFeature.tsx 当前请求：

- POST /api/chat
- GET /api/chat/custom-questions
- POST /api/chat/custom-questions
- DELETE /api/chat/custom-questions/{question_id}

当前 UI 使用的主要请求字段：
- query
- mode（rag | web | hybrid）
- company_filter（多选公司后逗号拼接）
- include_web（在 web/hybrid 模式下由后端逻辑生效）
- answer_provider（openai | claude | none）
- fallback_to_general_llm
- strict_grounding
- max_response_words（仅在 hybrid + fallback 开启 + guardrails 关闭时生效）

## 3）当前页面行为（与代码一致）

- 搜索模式：Filing Search / Web Search / Hybrid Search
- 公司筛选：Flex、Jabil、Celestica、Benchmark、Sanmina（可多选）
- 时间范围选择器存在于页面状态（Any Time、FY2026、FY2025、Last 12 Months）
- Prompt 区域：
  - Quick Questions
  - Research Topics（QUESTION_BANK 的一级/二级结构）
  - Custom Added Questions（通过后端持久化）
- 消息操作：
  - assistant 消息：复制 / 复用答案
  - user 消息：复用问题

## 4）Fallback 与 Guardrails 规则（前端）

ChatPageFeature.tsx 当前规则：

1. hybrid 模式下可切换 fallback。
2. fallback 开启时，provider 必须是 openai 或 claude（不能是 none）。
3. guardrails（strict_grounding）默认开启。
4. 回复长度上限（max_response_words）仅在以下条件生效：
   - mode = hybrid
   - fallback = 开启
   - guardrails = 关闭

## 5）主要改动文件

- AI Chat 主 UI 逻辑：
  - frontend/src/features/chat/ChatPageFeature.tsx
- AI Chat API 封装：
  - frontend/src/features/chat/api.ts
- 路由包装层：
  - frontend/src/app/chat/page.tsx
- 侧边栏入口文案/分组：
  - frontend/src/components/layout/Sidebar.tsx

## 6）校验

```bash
cd frontend && npm run lint -- src/features/chat/ChatPageFeature.tsx src/features/chat/api.ts src/app/chat/page.tsx
```
