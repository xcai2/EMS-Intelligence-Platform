# SCU Flex Practicum — Sprint Update
**Date:** April 17, 2026

---

## Summary

This sprint addressed three areas: UI polish on the Hyperscaler CapEx page, Analyst View performance and API cost reduction, and a full automatic content update pipeline combining a backend scheduler, stale-while-revalidate on the frontend, and SSE push notifications.

---

## 1. Hyperscaler CapEx Page (`ai-investments`)

### Stargate Project Panel Removed
The right-side Stargate Project module was removed from the AI Investment Details card. The left section — company selector buttons and the Key Metrics / AI Focus Subdomains / Recent Announcements detail panel — now spans the full card width, giving it significantly more room.

### Chart Font Sizes
| Chart | Before | After |
|-------|--------|-------|
| Bar chart (2025 vs 2026 CapEx) | No explicit size (browser default) | Axes `fontSize: 11`, Legend `fontSize: 11` |
| Pie chart (2026 Distribution) | No explicit size | Labels `fontSize: 10` |

### Data Sources Clarified
| Chart | Old Source Label | New Source Label |
|-------|-----------------|-----------------|
| Bar chart | `data.source` (raw API string) | "Financial Statements + Futurum Research" — linked to the Futurum report |
| Pie chart | "Company Earnings Reports" | "Financial Statements (SEC Filings)" |

The `ChartDescription` component was updated to accept an optional `sourceUrl` prop. When provided, the source renders as a clickable link with an external-link icon; otherwise it falls back to plain text as before.

---

## 2. Analyst View — Performance & API Cost

### Auto-Refresh Disabled
The `setInterval` that fired `fetchIntel()` every 5 minutes was removed to stop burning Brave Search API quota during development. The manual **Refresh** button remains fully functional.

A comment is left in two places to make reverting easy before final delivery:
```
// 5 min — revert to auto-refresh before delivery
// Auto-refresh disabled to reduce Brave API usage — revert before delivery
```

### sessionStorage Cache Added
On page load, the frontend now checks `sessionStorage` for data less than 5 minutes old and renders it immediately — no network call, no spinner. Fresh fetches update the cache so subsequent loads stay fast.

---

## 3. Automatic Content Updates

A full three-layer pipeline was built so the Analyst View always shows current data without manual refreshes or wasted API calls.

### How It Works

```
Scheduler (every 30 min)
  → invalidate analytics_cache (per-ticker entries)
  → get_all_company_intel()        ← Brave + LLM runs here, off the critical path
  → broadcast_update("cache_refreshed")
      → SSE push to all open browser tabs
          → sessionStorage cleared
          → silent doFetch()        ← instant (backend cache is warm)
              → UI updates automatically
```

### Layer A — Backend Scheduler (pre-warm)

**File:** `backend/ingestion/scheduler.py`

A new `warm_analyst_cache()` job was added to the existing APScheduler instance. It runs every 30 minutes:

1. Deletes all per-ticker `analytics_cache` entries so stale data is not served
2. Calls `get_all_company_intel()` — this triggers the Brave searches and LLM extractions, but happens in the background, not on a user request
3. After the cache is warm, calls `broadcast_update("cache_refreshed", {...})` to notify connected clients

Lazy imports inside the function prevent circular dependency issues at startup.

### Layer B — Stale-While-Revalidate (frontend SWR)

**File:** `frontend/src/features/analyst-view/AnalystViewPageFeature.tsx`

On every mount, two things happen in sequence:

1. **Serve from cache** — if sessionStorage has data less than 5 minutes old, render it immediately (zero latency)
2. **Revalidate in background** — always fire a silent `doFetch({ silent: true })` after rendering cached data. Since the backend cache is warm, this returns in milliseconds and updates the UI without any visible loading state

If the cache is stale or missing, `doFetch` runs normally and the loading state is shown until data arrives.

### Layer C — SSE Push

**Files:** `backend/analyst_view/broadcaster.py` (new), `backend/analyst_view/routes.py`

**Backend:**
- `broadcaster.py` — a lightweight in-memory event bus. Each connected SSE client registers an `asyncio.Queue`. `broadcast_update()` puts a message into every queue.
- `GET /api/analyst-view/stream` — new SSE endpoint. Sends an initial `connected` handshake, then yields messages from the client's queue. A 25-second timeout yields a `heartbeat` event to keep connections alive through proxies and load balancers. Cleans up the queue on disconnect.

**Frontend:**
- On mount, opens an `EventSource` to `/api/analyst-view/stream`
- On `cache_refreshed` event: clears sessionStorage and calls `doFetch({ silent: true })` — the backend responds instantly from its warm cache, and the UI updates silently
- Reconnects automatically with exponential back-off if the connection drops (3 s initial, doubles each attempt, capped at 60 s)
- Back-off resets to 3 s on a successful reconnect

---

## Files Changed

| File | Type | Change |
|------|------|--------|
| `frontend/src/app/ai-investments/page.tsx` | Edit | Remove Stargate panel, fix chart fonts, clarify source labels |
| `frontend/src/components/ui/chart-description.tsx` | Edit | Add `sourceUrl` prop for linked sources |
| `frontend/src/features/analyst-view/AnalystViewPageFeature.tsx` | Edit | SWR + SSE client, remove auto-refresh, rename `fetchIntel` → `doFetch` |
| `backend/analyst_view/broadcaster.py` | New | In-memory SSE event bus |
| `backend/analyst_view/routes.py` | Edit | Add `GET /analyst-view/stream` SSE endpoint |
| `backend/ingestion/scheduler.py` | Edit | Add `warm_analyst_cache` job (every 30 min) |

---

## Still To Do

- Explore automatic content updates for other pages (News, Competitor Investments)
- Revert `CACHE_TTL_MS` comment and re-enable auto-refresh before final delivery
- Test SSE connection stability under the deployment environment
