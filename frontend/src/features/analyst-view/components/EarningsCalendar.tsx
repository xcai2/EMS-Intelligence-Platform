'use client';

import { useCallback, useEffect, useState } from 'react';
import { ExternalLink } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type EarningsEvent = {
  ticker: string;
  company: string;
  kind: string;
  title: string;
  description: string;
  url: string;
  published: string;
};

type KindFilter = 'all' | 'EMS' | 'Hyperscaler';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function seekingAlphaUrl(ticker: string) {
  return `https://seekingalpha.com/symbol/${ticker}/earnings/transcripts`;
}

function formatPublished(iso: string | null | undefined) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
    });
  } catch {
    return null;
  }
}

function kindBadgeStyle(kind: string) {
  if (kind === 'EMS') {
    return 'bg-cyan-500/15 text-cyan-800 dark:text-cyan-300';
  }
  if (kind === 'Hyperscaler') {
    return 'bg-violet-500/15 text-violet-800 dark:text-violet-300';
  }
  return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';
}

function truncate(text: string, maxLen: number) {
  if (!text) return '';
  return text.length > maxLen ? text.slice(0, maxLen).trimEnd() + '…' : text;
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function EventSkeleton() {
  return (
    <div className="animate-pulse rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0a101c]">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="h-5 w-14 rounded-md bg-slate-200 dark:bg-slate-700" />
          <div className="h-5 w-16 rounded-full bg-slate-200 dark:bg-slate-700" />
        </div>
        <div className="h-4 w-20 rounded bg-slate-100 dark:bg-slate-800" />
      </div>
      <div className="mb-2 h-4 w-3/4 rounded bg-slate-200 dark:bg-slate-700" />
      <div className="space-y-1.5">
        <div className="h-3 w-full rounded bg-slate-100 dark:bg-slate-800" />
        <div className="h-3 w-5/6 rounded bg-slate-100 dark:bg-slate-800" />
      </div>
      <div className="mt-3 flex gap-2">
        <div className="h-7 w-28 rounded-lg bg-slate-200 dark:bg-slate-700" />
        <div className="h-7 w-28 rounded-lg bg-slate-200 dark:bg-slate-700" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Event card
// ---------------------------------------------------------------------------

function EventCard({ event }: { event: EarningsEvent }) {
  const published = formatPublished(event.published);

  return (
    <div className="flex flex-col rounded-2xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md dark:border-slate-800 dark:bg-[#0a101c]">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 border-b border-slate-100 p-4 dark:border-slate-800">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            {event.ticker}
          </span>
          <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${kindBadgeStyle(event.kind)}`}>
            {event.kind}
          </span>
          <span className="font-medium text-slate-800 dark:text-slate-200">{event.company}</span>
        </div>
        {published && (
          <span className="shrink-0 text-xs text-slate-400 dark:text-slate-500">{published}</span>
        )}
      </div>

      {/* Title + description */}
      <div className="flex-1 px-4 py-3">
        <p className="mb-1.5 text-sm font-semibold text-slate-800 dark:text-slate-100">
          {event.title}
        </p>
        {event.description && (
          <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
            {truncate(event.description, 180)}
          </p>
        )}
      </div>

      {/* Footer links */}
      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 px-4 py-2.5 dark:border-slate-800">
        {event.url && (
          <a
            href={event.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            <ExternalLink className="h-3 w-3" />
            Article
          </a>
        )}
        <a
          href={seekingAlphaUrl(event.ticker)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-400 dark:hover:bg-emerald-900/30"
        >
          <ExternalLink className="h-3 w-3" />
          SA Transcripts
        </a>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter tab bar
// ---------------------------------------------------------------------------

function KindTabs({
  value,
  onChange,
  counts,
}: {
  value: KindFilter;
  onChange: (v: KindFilter) => void;
  counts: Record<KindFilter, number>;
}) {
  const tabs: { key: KindFilter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'EMS', label: 'EMS' },
    { key: 'Hyperscaler', label: 'Hyperscalers' },
  ];

  return (
    <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 dark:bg-[#0f1726]">
      {tabs.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
            value === key
              ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-white'
              : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'
          }`}
        >
          {label}
          <span
            className={`rounded-full px-1.5 text-[11px] font-semibold ${
              value === key
                ? 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'
                : 'text-slate-400 dark:text-slate-500'
            }`}
          >
            {counts[key]}
          </span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function EarningsCalendar() {
  const [events, setEvents] = useState<EarningsEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<KindFilter>('all');

  const fetchEvents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API_URL}/api/analyst-view/earnings-calendar`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEvents(data.events ?? data.results ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load earnings calendar');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  const filtered =
    kindFilter === 'all' ? events : events.filter((e) => e.kind === kindFilter);

  const counts: Record<KindFilter, number> = {
    all: events.length,
    EMS: events.filter((e) => e.kind === 'EMS').length,
    Hyperscaler: events.filter((e) => e.kind === 'Hyperscaler').length,
  };

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <KindTabs value={kindFilter} onChange={setKindFilter} counts={counts} />
        <span className="text-xs text-slate-400 dark:text-slate-500">
          {filtered.length} event{filtered.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-400">
          Error: {error}
        </div>
      )}

      {/* Cards */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <EventSkeleton key={i} />
          ))}
        </div>
      ) : filtered.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {filtered.map((event, i) => (
            <EventCard key={`${event.ticker}-${event.published}-${i}`} event={event} />
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 py-16 text-center dark:border-slate-800 dark:bg-slate-900/30">
          <div className="mb-3 text-4xl">📅</div>
          <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
            No earnings events found
          </p>
          <p className="mt-1 max-w-xs text-xs text-slate-400 dark:text-slate-500">
            {kindFilter !== 'all'
              ? `No ${kindFilter} earnings events are currently available. Try switching to "All".`
              : 'Upcoming earnings transcripts and reports will appear here as they are published.'}
          </p>
        </div>
      )}
    </div>
  );
}
