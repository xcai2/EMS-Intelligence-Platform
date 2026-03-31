# AI Chat Frontend Guide

Last updated: 2026-03-31 (America/Los_Angeles)

## 1) Frontend Module Layout

- frontend/src/app/chat/page.tsx
  - Thin route entry that renders the AI Chat feature component.
- frontend/src/features/chat/ChatPageFeature.tsx
  - Main AI Chat UI and client-side interaction logic.
- frontend/src/features/chat/api.ts
  - AI Chat-specific API request helpers.

## 2) Data Flow

ChatPageFeature.tsx requests:

- POST /api/chat
- GET /api/chat/custom-questions
- POST /api/chat/custom-questions
- DELETE /api/chat/custom-questions/{question_id}

Request payload (main fields in current UI):
- query
- mode (rag | web | hybrid)
- company_filter (comma-joined selected companies)
- include_web (auto-enabled in web/hybrid from backend logic)
- answer_provider (openai | claude | none)
- fallback_to_general_llm
- strict_grounding
- max_response_words (active only in hybrid + fallback + guardrails off)

## 3) Current UI Behavior (Code-Accurate)

- Search modes: Filing Search / Web Search / Hybrid Search
- Company filters: Flex, Jabil, Celestica, Benchmark, Sanmina (multi-select)
- Time horizon selector exists in UI state (Any Time, FY2026, FY2025, Last 12 Months)
- Prompt controls:
  - Quick Questions
  - Research Topics (QUESTION_BANK primary/secondary tree)
  - Custom Added Questions (persisted via backend)
- Message actions:
  - Assistant message: copy / reuse answer
  - User message: reuse question

## 4) Fallback and Guardrails Rules (Frontend)

Current UI behavior in ChatPageFeature.tsx:

1. In hybrid mode, fallback can be toggled.
2. If fallback is on, provider must be selected (openai or claude; not none).
3. Guardrails (strict_grounding) default to on.
4. Response length cap (max_response_words) is only applied when:
   - mode = hybrid
   - fallback = on
   - guardrails = off

## 5) Files to Edit

- Main AI Chat UI logic:
  - frontend/src/features/chat/ChatPageFeature.tsx
- AI Chat API helpers:
  - frontend/src/features/chat/api.ts
- Route wrapper only:
  - frontend/src/app/chat/page.tsx
- Navigation label/group:
  - frontend/src/components/layout/Sidebar.tsx

## 6) Validation

```bash
cd frontend && npm run lint -- src/features/chat/ChatPageFeature.tsx src/features/chat/api.ts src/app/chat/page.tsx
```
