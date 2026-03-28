# News Desk

Last updated: 2026-03-28 (America/Los_Angeles)

## 1) Purpose

`News Desk` is the primary monitoring page for:
- Flex
- Jabil
- Celestica
- Benchmark
- Sanmina

It is focused on quick reading and triage (Top News + Analyst View), with manual refresh support.

## 2) Scope of This Doc

This is a **page/product-level** note (what users see and what changed).

Implementation docs:
- Frontend: `docs/news/frontend.md`
- Backend: `docs/news/backend.md`

## 3) Current User-Facing Summary

- Sidebar has a News entry (`/news`) under the `NEWs` group.
- Default load uses cached backend results.
- Clicking `Refresh` triggers backend `force_refresh=true`.
- Company and keyword controls update feed ranking/filtering in-page.

## 4) Useful Commands

Restart backend:
```bash
pkill -f "uvicorn backend.main:app --host 0.0.0.0 --port 8001"; nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload >/tmp/flex-backend.log 2>&1 &
```

Check backend log:
```bash
tail -n 40 /tmp/flex-backend.log
```

Lint News frontend files:
```bash
cd frontend && npm run lint -- src/features/news/NewsPageFeature.tsx src/app/news/page.tsx
```

## 5) Change Log

- 2026-03-28
  - Re-audited News docs against current code paths and behavior.
  - Updated frontend behavior notes (current keyword presets, Top News and fast-feed windows).
  - Updated backend notes (active endpoints, source mix, and cache behavior split by service vs aggregator).

- 2026-03-27
  - Moved News implementation into domain-oriented structure under `backend/news/*`.
  - Removed legacy compatibility shims from `backend/ingestion/`.
  - Split docs into frontend/backend/page-level references.
