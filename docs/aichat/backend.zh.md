# AI Chat 后端说明

最后更新：2026-03-31（America/Los_Angeles）

## 1）后端模块结构

- backend/main.py
  - 应用入口，负责挂载 AI Chat 路由。
- backend/aichat/routes.py
  - AI Chat 主接口（/api/chat*）与编排逻辑。
- backend/aichat/pipeline.py
  - 历史/工具型 Chat pipeline（当前未作为 API 入口挂载）。

AI Chat 主要依赖：
- 检索与生成：
  - backend/rag/retriever.py
  - backend/rag/assembled_retriever.py
  - backend/rag/generator.py
  - backend/rag/agentic.py
  - backend/rag/web_search.py
- 会话记忆：
  - backend/aichat/memory.py
- 配置与模型调用：
  - backend/core/config.py
  - backend/core/llm_client.py

## 2）主接口

定义于 backend/aichat/routes.py：

- POST /api/chat/stream
  - SSE 流式回复接口。
- POST /api/chat
  - 非流式回复接口。
- GET /api/chat/custom-questions
- POST /api/chat/custom-questions
- DELETE /api/chat/custom-questions/{question_id}
- GET /api/chat/sessions
- GET /api/chat/sessions/{session_id}
- GET /api/chat/sessions/{session_id}/history
- DELETE /api/chat/sessions/{session_id}

## 3）请求模型

ChatRequest 当前支持：
- query
- session_id
- mode（rag | web | hybrid | assembled）
- include_web
- company_filter
- retrieval_strategy（auto | vector | bm25 | hybrid | table）
- use_reranking
- answer_provider（openai | claude）
- fallback_to_general_llm
- strict_grounding
- hybrid_multi_output
- max_response_words

## 4）运行时行为（与代码一致）

- Query 分析会识别：
  - 公司实体
  - 指标关键词
  - 年份
  - 对比意图
- 路由/检索策略：
  - 对比类问题可走 agentic 路径
  - mode=assembled 时走 assembled retriever
  - rag / hybrid 走标准检索路径
- Hybrid 行为：
  - 可组合 filing 上下文 + web 上下文
  - 可在开启后使用通用大模型 fallback
  - 可输出 3 段式结构化结果
- Strict grounding：
  - 在 rag / assembled 下，证据不足会返回受保护的 no-answer

## 5）持久化与会话说明

- 自定义问题持久化文件：
  - data/chat_custom_questions.json（通过 DATA_DIR）
- 会话历史与清理逻辑：
  - backend/aichat/memory.py

## 6）主要改动文件

- AI Chat 主后端逻辑：
  - backend/aichat/routes.py
- 会话存储逻辑：
  - backend/aichat/memory.py
- 历史/工具型 pipeline：
  - backend/aichat/pipeline.py
- 应用路由挂载：
  - backend/main.py

## 7）校验

```bash
./.venv/bin/python -m py_compile backend/main.py backend/aichat/routes.py backend/aichat/memory.py backend/aichat/pipeline.py
```
