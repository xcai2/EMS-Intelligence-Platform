'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, ExternalLink, Minus, TrendingDown, TrendingUp } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Consensus = 'Bullish' | 'Neutral' | 'Bearish' | 'Mixed' | 'Unknown';

type CompanyIntel = {
  ticker: string;
  company: string;
  kind: string;
  consensus: Consensus;
  price_target: string;
  recent_actions: string[];
  key_view: string;
  sources: { title: string; url: string }[];
  updated_at: string;
  error?: string | null;
};

type SortMode = 'consensus' | 'name';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CONSENSUS_ORDER: Record<Consensus, number> = {
  Bullish: 0, Mixed: 1, Neutral: 2, Bearish: 3, Unknown: 4,
};

function benzingaUrl(ticker: string) {
  return `https://www.benzinga.com/quote/${ticker}/analyst-ratings`;
}

function tipranksUrl(ticker: string) {
  return `https://www.tipranks.com/stocks/${ticker.toLowerCase()}/forecast`;
}

function consensusConfig(c: Consensus) {
  switch (c) {
    case 'Bullish':
      return { bg: 'bg-emerald-500/15 dark:bg-emerald-500/20', text: 'text-emerald-800 dark:text-emerald-300', border: 'border-emerald-400/40', Icon: TrendingUp };
    case 'Bearish':
      return { bg: 'bg-rose-500/15 dark:bg-rose-500/20', text: 'text-rose-800 dark:text-rose-300', border: 'border-rose-400/40', Icon: TrendingDown };
    case 'Neutral':
      return { bg: 'bg-amber-500/15 dark:bg-amber-500/20', text: 'text-amber-800 dark:text-amber-300', border: 'border-amber-400/40', Icon: Minus };
    case 'Mixed':
      return { bg: 'bg-indigo-500/15 dark:bg-indigo-500/20', text: 'text-indigo-800 dark:text-indigo-300', border: 'border-indigo-400/40', Icon: Minus };
    default:
      return { bg: 'bg-slate-500/10 dark:bg-slate-500/15', text: 'text-slate-600 dark:text-slate-400', border: 'border-slate-400/30', Icon: Minus };
  }
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function CardSkeleton() {
  return (
    <div className="animate-pulse rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0a101c]">
      <div className="mb-3 flex items-start justify-between">
        <div className="space-y-1.5">
          <div className="h-4 w-28 rounded bg-slate-200 dark:bg-slate-700" />
          <div className="h-3 w-12 rounded bg-slate-200 dark:bg-slate-700" />
        </div>
        <div className="h-6 w-20 rounded-full bg-slate-200 dark:bg-slate-700" />
      </div>
      <div className="mb-2 h-3 w-24 rounded bg-slate-200 dark:bg-slate-700" />
      <div className="space-y-1.5">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-3 w-full rounded bg-slate-100 dark:bg-slate-800" />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Company card
// ---------------------------------------------------------------------------

function CompanyCard({ item }: { item: CompanyIntel }) {
  const cfg = consensusConfig(item.consensus);
  const { Icon } = cfg;

  return (
    <div className="flex flex-col rounded-2xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md dark:border-slate-800 dark:bg-[#0a101c]">
      {/* Header */}
      <div className="flex items-start justify-between gap-2 border-b border-slate-100 p-4 dark:border-slate-800">
        <div>
          <p className="font-semibold text-slate-900 dark:text-white">{item.company}</p>
          <div className="mt-0.5 flex items-center gap-2">
            <span className="font-mono text-xs font-medium text-slate-500 dark:text-slate-400">{item.ticker}</span>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              {item.kind}
            </span>
          </div>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold ${cfg.bg} ${cfg.text} ${cfg.border}`}
        >
          <Icon className="h-3 w-3" />
          {item.consensus}
        </span>
      </div>

      {/* Price target */}
      <div className="flex items-center gap-1.5 border-b border-slate-100 px-4 py-2 dark:border-slate-800">
        <span className="text-xs text-slate-500 dark:text-slate-400">Consensus PT:</span>
        <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">{item.price_target || '—'}</span>
      </div>

      {/* Recent actions */}
      <div className="flex-1 px-4 py-3">
        {item.recent_actions.length > 0 ? (
          <>
            <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
              Recent actions
            </p>
            <ul className="space-y-1">
              {item.recent_actions.slice(0, 4).map((action, i) => (
                <li key={i} className="flex items-start gap-1.5 text-sm text-slate-700 dark:text-slate-300">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-500" />
                  {action}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-xs italic text-slate-400 dark:text-slate-500">No recent actions.</p>
        )}
      </div>

      {/* Key view */}
      {item.key_view && (
        <div className="mx-4 mb-3 rounded-xl bg-slate-50 px-3 py-2.5 dark:bg-[#0f1726]">
          <p className="text-xs italic leading-relaxed text-slate-600 dark:text-slate-400">
            &ldquo;{item.key_view}&rdquo;
          </p>
        </div>
      )}

      {/* Footer links */}
      <div className="flex items-center gap-2 border-t border-slate-100 px-4 py-2.5 dark:border-slate-800">
        <a
          href={benzingaUrl(item.ticker)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[11px] text-cyan-700 hover:underline dark:text-cyan-400"
        >
          Benzinga <ExternalLink className="h-2.5 w-2.5" />
        </a>
        <span className="text-slate-300 dark:text-slate-700">·</span>
        <a
          href={tipranksUrl(item.ticker)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[11px] text-cyan-700 hover:underline dark:text-cyan-400"
        >
          TipRanks <ExternalLink className="h-2.5 w-2.5" />
        </a>
      </div>

      {/* Error state */}
      {item.error && (
        <div className="flex items-center gap-1.5 border-t border-rose-200 bg-rose-50/60 px-4 py-2 text-xs text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-400">
          <AlertCircle className="h-3 w-3 shrink-0" />
          {item.error}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section header
// ---------------------------------------------------------------------------

function SectionHeader({ title, count }: { title: string; count: number }) {
  return (
    <div className="flex items-center gap-3">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        {title}
      </h3>
      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
        {count}
      </span>
      <div className="flex-1 border-t border-slate-200 dark:border-slate-800" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type Props = {
  companies?: CompanyIntel[];
  loading?: boolean;
};

export default function ConsensusView({ companies: propCompanies, loading: propLoading }: Props = {}) {
  const [ownCompanies, setOwnCompanies] = useState<CompanyIntel[]>([]);
  const [ownLoading, setOwnLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>('consensus');

  // If parent passed data, use it directly; otherwise fetch independently
  const companies = propCompanies ?? ownCompanies;
  const loading = propLoading ?? ownLoading;

  const fetchIntel = useCallback(async () => {
    if (propCompanies !== undefined) return; // parent is managing data
    try {
      setOwnLoading(true);
      setError(null);
      const res = await fetch(`${API_URL}/api/analyst-view/company-intel`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setOwnCompanies(data.companies ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load company intel');
    } finally {
      setOwnLoading(false);
    }
  }, [propCompanies]);

  useEffect(() => {
    fetchIntel();
  }, [fetchIntel]);

  const sorted = [...companies].sort((a, b) => {
    if (sortMode === 'consensus') {
      const diff =
        (CONSENSUS_ORDER[a.consensus] ?? 4) - (CONSENSUS_ORDER[b.consensus] ?? 4);
      return diff !== 0 ? diff : a.company.localeCompare(b.company);
    }
    return a.company.localeCompare(b.company);
  });

  const ems = sorted.filter((c) => c.kind === 'EMS');
  const hyperscalers = sorted.filter((c) => c.kind === 'Hyperscaler');

  const skeletons = Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />);

  return (
    <div className="space-y-6">
      {/* Sort bar */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-500 dark:text-slate-400">Sort by:</span>
        {(['consensus', 'name'] as SortMode[]).map((mode) => (
          <button
            key={mode}
            onClick={() => setSortMode(mode)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              sortMode === mode
                ? 'bg-cyan-600 text-white dark:bg-cyan-500'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
            }`}
          >
            {mode === 'consensus' ? 'Consensus' : 'Company name'}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-400">
          Error: {error}
        </div>
      )}

      {/* EMS section */}
      <div className="space-y-3">
        <SectionHeader title="EMS Companies" count={loading ? 6 : ems.length} />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {loading ? skeletons : ems.map((c) => <CompanyCard key={c.ticker} item={c} />)}
        </div>
      </div>

      {/* Hyperscalers section */}
      <div className="space-y-3">
        <SectionHeader title="Hyperscalers" count={loading ? 6 : hyperscalers.length} />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {loading
            ? skeletons
            : hyperscalers.map((c) => <CompanyCard key={c.ticker} item={c} />)}
        </div>
      </div>
    </div>
  );
}
