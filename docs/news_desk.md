# News Desk Implementation Notes

Last updated: 2026-03-11 (America/Los_Angeles)

## 1) What This Page Is

`News Desk` is the primary news workspace for the 5 tracked companies:
- Flex
- Jabil
- Celestica
- Benchmark
- Sanmina

It supports AI/Data Center-focused filtering, official company entry links, ranked feeds, and manual refresh.

## 2) Navigation Placement

Sidebar placement is now:
- `News Desk` (top-level)
- `News Monitor` (top-level, marked `OLD`)
- `AI Research Chat` (top-level, after News Monitor)

`News Desk` and `News Monitor` are parallel top-level entries (not nested under the same fold group).

## 3) Core UI Behavior

### Top line keyword control
At the line:
`Only 5 tracked companies + ...`
we now provide:
- quick keyword buttons (ordered):
  - `Data Center`
  - `AI`
  - `GPU`
  - `Liquid Cooling`
  - `Hyperscaler`
- a free input box for custom keywords
- comma-separated multi-keyword filtering (example: `ai, data center`)

### Keyword toggle behavior
- click keyword once: apply it
- click same keyword again: remove it (clear filter)

### Company filter
Buttons for `All / Flex / Jabil / Celestica / Benchmark / Sanmina` filter the feed by company.

### Refresh behavior
- page load: uses cached aggregated data
- click `Refresh`: forces re-fetch from backend (`force_refresh=true`)

## 4) Data Sources and Fetch Logic

## Backend entry
- Main news API: `backend/ingestion/news_feed.py`
- Frontend page: `frontend/src/app/news/page.tsx`

### Current source mix
For company news, backend aggregates from:
1. official company source paths (lightweight scraping / link scanning)
2. Google News RSS (including site-scoped queries)
3. optional Brave web search (if key available)
4. fallback curated entries when live sources are sparse

### Official links currently integrated
- Flex: `https://flex.com/newsroom`
- Jabil: `https://jabil.com/blog.html`
- Benchmark: `https://www.bench.com/setting-the-benchmark`
- Sanmina: `https://www.sanmina.com/media-center/press-releases/`
- Celestica: currently via broader domain path and fallback logic

### Accessibility filtering
High risk paywall/blocked domains are filtered or redirected via backup query links.

## 5) Caching Policy (Current)

Runtime cache is enabled in backend news service:
- repeated requests read from in-memory cache
- no full re-crawl every page refresh
- force refresh only when explicitly requested from UI
- backend restart clears runtime cache

## 6) Layout and Scrolling

Desktop layout is 3 columns with alignment adjustments:
- left: Top Story + additional cards
- middle: Hot Rank
- right: Fast Feed (internal scroll)

If content exceeds panel height, internal scroll is used to keep columns aligned.

## 7) Images

Image behavior is conditional:
- show image only when `image_url` exists
- if no image, keep text layout only (no large placeholder black block)

## 8) Upcoming Earnings Placement

`Upcoming Earnings` has been moved into the `Official Company Entrances` section for a tighter top information block.

Data source for this card:
- API: `/api/earnings/upcoming`
- current data is schedule-based (rule/estimated), not fully real-time confirmed calendar

## 9) Sidebar Collapse Feature

Sidebar now supports collapse/expand:
- collapse button inside sidebar (top-right area)
- when collapsed, a small fixed button remains at top-left to reopen

## 10) Known Limitations

- Some official websites are JS-heavy, so pure HTML link extraction may miss items.
- Image availability depends on source metadata (RSS descriptions, article metadata).
- Earnings card is currently estimated schedule logic, not guaranteed real-time announcements.

## 11) Useful Commands

Restart backend quickly:
```bash
pkill -f "uvicorn backend.main:app --host 0.0.0.0 --port 8001"; nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload >/tmp/flex-backend.log 2>&1 &
```

Check backend log:
```bash
tail -n 40 /tmp/flex-backend.log
```

Run News Desk lint:
```bash
cd frontend && npm run lint -- src/app/news/page.tsx
```
