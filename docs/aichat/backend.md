# AI Chat Backend Guide

Last updated: 2026-03-31 (America/Los_Angeles)

## 1) Backend Module Layout

- backend/main.py
  - App entrypoint; mounts AI Chat router.
- backend/aichat/routes.py
  - Main AI Chat endpoints (/api/chat*) and orchestration logic.
- backend/aichat/pipeline.py
  - Legacy/utility chat pipeline helper (currently not mounted as API endpoint).

Core dependencies used by AI Chat flow:
- Retrieval and generation:
  - backend/rag/retriever.py
  - backend/rag/assembled_retriever.py
  - backend/rag/generator.py
  - backend/rag/agentic.py
  - backend/rag/web_search.py
- Session memory:
  - backend/aichat/memory.py
- Config / provider setup:
  - backend/core/config.py
  - backend/core/llm_client.py

## 2) Main Endpoints

Defined in backend/aichat/routes.py:

- POST /api/chat/stream
  - SSE streaming response endpoint.
- POST /api/chat
  - Non-streaming response endpoint.
- GET /api/chat/custom-questions
- POST /api/chat/custom-questions
- DELETE /api/chat/custom-questions/{question_id}
- GET /api/chat/sessions
- GET /api/chat/sessions/{session_id}
- GET /api/chat/sessions/{session_id}/history
- DELETE /api/chat/sessions/{session_id}

## 3) Chat Request Model

ChatRequest supports:
- query
- session_id
- mode (rag | web | hybrid | assembled)
- include_web
- company_filter
- retrieval_strategy (auto | vector | bm25 | hybrid | table)
- use_reranking
- answer_provider (openai | claude)
- fallback_to_general_llm
- strict_grounding
- hybrid_multi_output
- max_response_words

## 4) Runtime Behavior (Code-Accurate)

- Query analysis detects:
  - company mentions
  - metric keywords
  - year references
  - comparison intent
- Routing behavior:
  - optional agentic path for comparison-like queries
  - assembled retriever path when mode=assembled
  - standard retrieval path for rag / hybrid
- Hybrid behavior:
  - can combine filing context + web context
  - supports explicit fallback to general LLM when enabled
  - can return structured 3-part output in hybrid mode
- Strict grounding:
  - in rag / assembled, no sufficient evidence leads to guarded no-answer response

## 5) Persistence and Session Notes

- Custom preset questions are persisted to:
  - data/chat_custom_questions.json (via DATA_DIR)
- Session history and cleanup are managed through:
  - backend/aichat/memory.py

## 6) Files to Edit

- Primary AI Chat backend logic:
  - backend/aichat/routes.py
- Session storage logic:
  - backend/aichat/memory.py
- Legacy/utility pipeline:
  - backend/aichat/pipeline.py
- App router mounting:
  - backend/main.py

## 7) Validation

```bash
./.venv/bin/python -m py_compile backend/main.py backend/aichat/routes.py backend/aichat/memory.py backend/aichat/pipeline.py
```
