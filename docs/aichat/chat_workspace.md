# AI Chat Workspace

Last updated: 2026-03-31 (America/Los_Angeles)

## 1) Purpose

AI Chat is the analysis workspace for filing-grounded and web-augmented Q&A across:
- Flex
- Jabil
- Celestica
- Benchmark
- Sanmina

The page focuses on analyst-style prompt workflows, reusable question sets, and configurable grounding/fallback behavior.

## 2) Scope of This Doc

This is a page/product-level note (what users see and what changed).

Implementation docs:
- Frontend: docs/aichat/frontend.md
- Backend: docs/aichat/backend.md

## 3) Current User-Facing Summary

- Sidebar includes AI Chat entry at route /chat.
- Route is a thin page wrapper; main UI lives in feature module.
- Users can switch mode (Filing/Web/Hybrid), select companies, and use question presets.
- Custom added questions are persisted and can be deleted.
- In hybrid mode, fallback and guardrails can be configured before sending queries.

## 4) Useful Commands

Restart backend:

    pkill -f "uvicorn backend.main:app --host 0.0.0.0 --port 8001"; nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload >/tmp/flex-backend.log 2>&1 &

Check backend log:

    tail -n 40 /tmp/flex-backend.log

Lint AI Chat frontend files:

    cd frontend && npm run lint -- src/features/chat/ChatPageFeature.tsx src/app/chat/page.tsx

## 5) Change Log

- 2026-03-31
  - Moved AI Chat implementation into domain-oriented structure under backend/aichat/*.
  - Added frontend feature split with thin route wrapper at frontend/src/app/chat/page.tsx.
  - Added dedicated AI Chat docs set (frontend/backend/page-level + zh variants).
