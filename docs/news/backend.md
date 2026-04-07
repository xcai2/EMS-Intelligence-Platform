# News Backend Guide

Last updated: 2026-03-28 (America/Los_Angeles)

## 1) Backend Module Layout

- `backend/main.py`
  - App entrypoint; mounts News router.
- `backend/news/routes.py`
  - Main News endpoints (`/api/news/*`).
- `backend/news/service.py`
  - Primary News service (collection, normalization, filtering, dedupe, cache).
- `backend/news/sources.py`
  - Official source config + fallback items.
- `backend/news/filtering.py`
  - Filtering constants (AI terms, blocked/paywalled domains, noise terms).
- `backend/news/normalizer.py`
  - URL-domain to source-label mapping.
- `backend/news/aggregator.py`
  - Legacy aggregator for `advanced_data` endpoints (`/api/news-aggregator/*`).

## 2) Main News Endpoints

Defined in `backend/news/routes.py`:

- `/api/news/company/{ticker}` (`count` default `10`, optional `category`, `force_refresh`)
- `/api/news/industry` (`count` default `15`, optional `force_refresh`)
- `/api/news/comparative` (optional `force_refresh`)
- `/api/news/all` (`count_per_company` default `3`, optional `force_refresh`)

## 3) Main Service Source Mix (`backend/news/service.py`)

For company news (`get_company_news`), service aggregates from:

1. Official company source pipeline
   - company RSS (if configured)
   - site-scoped Google News RSS query
   - optional HTML link scan (disabled per company when configured)
   - optional Public.com board (currently FLEX)
2. Brave web search (`search_web_with_diagnostics`)
3. Google News RSS query fan-out
4. Fallback static items when no live results

### Responsibility Boundary (Fetch vs Filter)

- Backend focus in this stage: gather broadly, normalize, dedupe, company-relevance check, and rank support fields.
- Additional strict presentation filtering is applied in frontend (`NewsPageFeature.tsx`) before final display.
- This keeps backend collection broad while allowing UI-side precision tuning.

## 4) Official Company Sources

Configured in `backend/news/sources.py` (`OFFICIAL_COMPANY_SOURCES`):

### FLEX
- `https://investors.flex.com/rss/pressrelease.aspx`
- `https://investors.flex.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000866374`
- `https://investors.flex.com/rss/event.aspx`
- plus official paths on `flex.com` and Public board:
  - `https://public.com/stocks/flex/news`

### JBL (Jabil)
- `https://investors.jabil.com/rss/pressrelease.aspx`
- `https://investors.jabil.com/rss/event.aspx`
- `https://investors.jabil.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000898293`
- `disable_html_scan = True`

### CLS (Celestica)
- `https://www.globenewswire.com/rssfeed/organization/vlXa3ip4O0JMbJucCiUeUg==`
- `disable_html_scan = True`

### SANM (Sanmina)
- `https://ir.sanmina.com/rss/pressrelease.aspx`
- `https://ir.sanmina.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000897723`
- `https://ir.sanmina.com/rss/event.aspx`

### BHE (Benchmark)
- no dedicated RSS yet
- uses official path + search mix

## 5) Search / Aggregator Sources

### Brave Search
- Entry: `backend/rag/web_search.py`
- Used by main service + legacy aggregator
- API key config remains in backend `.env`

### Google News RSS
- Queried directly in main service
- Service tries to extract original source and resolve redirect URLs

## 6) Legacy Aggregator Endpoints (still active)

Exposed via `backend/api/routes/advanced_data.py` and implemented in `backend/news/aggregator.py`:

- `/api/news-aggregator/company/{company}`
- `/api/news-aggregator/industry`
- `/api/news-aggregator/all-companies`
- `/api/news-aggregator/trending`
- `/api/news-aggregator/categories`
- `/api/news-aggregator/feeds`

## 7) Cache Behavior (Code-Accurate)

### Main News service (`backend/news/service.py`)
- Runtime cache dict in memory
- Persisted files:
  `data/news_cache/company_news.json`
  `data/news_cache/industry_news.json`
  `data/news_cache/comparative_news.json`
- Normal request uses cache when key exists
- `force_refresh=true` bypasses cache and re-fetches
- Restart reloads persisted cache file

### Legacy aggregator (`backend/news/aggregator.py`)
- In-memory cache only (TTL 900s)
- No persisted cache file
