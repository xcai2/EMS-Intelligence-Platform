# News Frontend Guide

Last updated: 2026-03-28 (America/Los_Angeles)

## 1) Frontend Module Layout

- `frontend/src/app/news/page.tsx`
  - Thin route entry that renders the News feature component.
- `frontend/src/features/news/NewsPageFeature.tsx`
  - Main News Desk UI and client-side feed processing.

## 2) Data Flow

`NewsPageFeature.tsx` requests:

- `/api/news/all?count_per_company=24`
- `/api/news/industry?count=20`
- `/api/news/comparative`

Refresh button requests the same endpoints with `force_refresh=true`.

The page then merges those feeds and applies client-side:
- strict company/noise filtering
- similar-title dedupe
- source-quality ranking
- Top News selection and Analyst View rendering

## 3) Current UI Behavior (Code-Accurate)

- Company switcher: `All / Flex / Jabil / Celestica / Benchmark / Sanmina`
- Keyword presets: `Data Center`, `AI`, `Liquid Cooling`
- Custom keyword input supports comma-separated terms
- Top News:
  - Lead story: first whitelist source if available, else fallback to first item
  - Trending list: top 5
  - Excludes terms like `presentation`, `investor presentation`, `.pdf`
  - Recency window preference: 7 days
- Analyst View:
  - Timeline list filtered to last 2 days when timestamps are available

## 4) Filtering Order (Important)

Current client-side filtering order in `NewsPageFeature.tsx`:

1. Negative/noise filter (`EXCLUDED_NOISE_PATTERNS`, JBL consumer-audio noise)
2. Strict tracked-company match (`isStrictTrackedCompanyMatch`)
3. Keep item once strict company match passes

Important:
- It is **not** currently enforcing `strict company match AND business keyword` on the frontend.
- Business relevance scoring still affects ranking signals, but strict company match is the hard gate.

## 5) Source Quality Rules in Frontend

- Source scoring tiers are defined in component constants.
- Lead story whitelist currently includes:
  - `finance.yahoo.com`, `reuters.com`, `bloomberg.com`, `cnbc.com`, `marketwatch.com`, `tipranks.com`

## 6) Files to Edit

- Main News UI logic:
  - `frontend/src/features/news/NewsPageFeature.tsx`
- Route wrapper only:
  - `frontend/src/app/news/page.tsx`
- Navigation label/group:
  - `frontend/src/components/layout/Sidebar.tsx`

## 7) Validation

```bash
cd frontend && npm run lint -- src/features/news/NewsPageFeature.tsx src/app/news/page.tsx
```
