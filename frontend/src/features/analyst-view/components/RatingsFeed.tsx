'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ExternalLink, RefreshCw, Search } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
const AUTO_REFRESH_MS = 30 * 60 * 1000; // 30 minutes

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type RatingAction = {
  ticker: string;
  company: string;
  action: string;
  colour: 'green' | 'red' | 'grey';
  source_url: string;
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TICKERS = ['FLEX', 'JBL', 'CLS', 'BHE', 'SANM', 'PLXS', 'AMZN', 'MSFT', 'GOOGL', 'META', 'AAPL', 'ORCL'];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function borderColour(colour: RatingAction['colour']) {
  switch (colour) {
    case 'green': return 'border-l-emerald-500';
    case 'red':   return 'border-l-rose-500';
    default:      return 'border-l-slate-400';
  }
}

function actionBadgeColour(colour: RatingAction['colour']) {
  switch (colour) {
    case 'green': return 'bg-emerald-500/15 text-emerald-800 dark:text-emerald-300';
    case 'red':   return 'bg-rose-500/15 text-rose-800 dark:text-rose-300';
    default:      return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';
  }
}

function formatTimestamp(iso: string | null | undefined) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function FeedSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="animate-pulse rounded-xl border-l-4 border-l-slate-200 bg-white p-4 dark:border-l-slate-700 dark:bg-[#0a101c]"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="h-5 w-12 rounded bg-slate-200 dark:bg-slate-700" />
              <div className="h-4 w-48 rounded bg-slate-100 dark:bg-slate-800" />
            </div>
            <div className="h-4 w-16 rounded bg-slate-100 dark:bg-slate-800" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Feed item
// ---------------------------------------------------------------------------

function FeedItem({ item }: { item: RatingAction }) {
  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-xl border border-slate-100 border-l-4 bg-white px-4 py-3 shadow-sm transition-shadow hover:shadow-md dark:border-slate-800 dark:border-l-4 dark:bg-[#0a101c] ${borderColour(item.colour)}`}
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="shrink-0 rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
          {item.ticker}
        </span>
        <div className="min-w-0">
          <span className="truncate text-sm font-medium text-slate-800 dark:text-slate-200">
            {item.company}
          </span>
          <span
            className={`ml-2 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${actionBadgeColour(item.colour)}`}
          >
            {item.action}
          </span>
        </div>
      </div>
      <a
        href={item.source_url}
        target="_blank"
        rel="noopener noreferrer"
        className="ml-2 shrink-0 inline-flex items-center gap-1 text-xs text-cyan-700 hover:underline dark:text-cyan-400"
      >
        Source
        <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function RatingsFeed() {
  const [items, setItems] = useState<RatingAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tickerFilter, setTickerFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchFeed = useCallback(async (isManual = false) => {
    try {
      if (isManual) setRefreshing(true);
      else setLoading(true);
      setError(null);
      const res = await fetch(`${API_URL}/api/analyst-view/ratings-feed`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setItems(data.feed ?? data.ratings ?? data.results ?? []);
      setLastUpdated(data.cached_at ?? new Date().toISOString());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load ratings');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchFeed();
    timerRef.current = setInterval(() => fetchFeed(), AUTO_REFRESH_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchFeed]);

  const filtered = items.filter((item) => {
    const matchesTicker = !tickerFilter || item.ticker === tickerFilter;
    const matchesSearch =
      !searchQuery ||
      item.company.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.action.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesTicker && matchesSearch;
  });

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search company or action…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 dark:border-slate-700 dark:bg-[#0f1726] dark:text-white dark:placeholder-slate-500"
          />
        </div>
        <select
          value={tickerFilter}
          onChange={(e) => setTickerFilter(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 dark:border-slate-700 dark:bg-[#0f1726] dark:text-slate-300"
        >
          <option value="">All tickers</option>
          {TICKERS.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <button
          onClick={() => fetchFeed(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-[#0f1726] dark:text-slate-300 dark:hover:bg-slate-800"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
        {lastUpdated && (
          <span className="text-xs text-slate-400 dark:text-slate-500">
            Updated {formatTimestamp(lastUpdated)}
          </span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-400">
          Error: {error}
        </div>
      )}

      {/* Feed list */}
      <div className="max-h-[600px] overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-[#080e1a]">
        {loading && items.length === 0 ? (
          <FeedSkeleton />
        ) : filtered.length > 0 ? (
          <div className="space-y-2">
            {filtered.map((item, i) => (
              <FeedItem key={`${item.ticker}-${item.action}-${i}`} item={item} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-2 text-3xl">📭</div>
            <p className="text-sm font-medium text-slate-600 dark:text-slate-400">No rating actions found</p>
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
              {tickerFilter || searchQuery
                ? 'Try clearing your filters'
                : 'Rating actions will appear here as they are published'}
            </p>
          </div>
        )}
      </div>

      <p className="text-xs text-slate-400 dark:text-slate-500">
        Auto-refreshes every 30 minutes · {filtered.length} action{filtered.length !== 1 ? 's' : ''} shown
      </p>
    </div>
  );
}
