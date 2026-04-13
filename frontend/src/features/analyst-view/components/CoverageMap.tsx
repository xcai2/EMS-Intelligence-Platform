'use client';

import { useCallback, useEffect, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type CoverageCell = {
  covered: boolean;
  consensus?: string;
  price_target?: string;
};

type CoverageRow = {
  analyst: string;
  coverage: Record<string, CoverageCell>;
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TICKERS = ['FLEX', 'JBL', 'CLS', 'BHE', 'SANM', 'PLXS', 'AMZN', 'MSFT', 'GOOGL', 'META', 'AAPL', 'ORCL'];

const EMS_TICKERS = new Set(['FLEX', 'JBL', 'CLS', 'BHE', 'SANM', 'PLXS']);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type ConsensusKey = 'Bullish' | 'Bearish' | 'Neutral' | 'Mixed' | 'Unknown';

function dotColour(consensus: string | undefined) {
  switch (consensus as ConsensusKey) {
    case 'Bullish': return 'bg-emerald-500 ring-emerald-400/30';
    case 'Bearish': return 'bg-rose-500 ring-rose-400/30';
    case 'Neutral': return 'bg-amber-500 ring-amber-400/30';
    case 'Mixed':   return 'bg-indigo-500 ring-indigo-400/30';
    default:        return 'bg-slate-400 ring-slate-300/30';
  }
}

function consensusBadgeColour(consensus: string | undefined) {
  switch (consensus as ConsensusKey) {
    case 'Bullish': return 'bg-emerald-500/15 text-emerald-800 dark:text-emerald-300';
    case 'Bearish': return 'bg-rose-500/15 text-rose-800 dark:text-rose-300';
    case 'Neutral': return 'bg-amber-500/15 text-amber-800 dark:text-amber-300';
    case 'Mixed':   return 'bg-indigo-500/15 text-indigo-800 dark:text-indigo-300';
    default:        return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';
  }
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

function CellTooltip({ cell, ticker }: { cell: CoverageCell; ticker: string }) {
  return (
    <div className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 -translate-x-1/2 whitespace-nowrap rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-lg dark:border-slate-700 dark:bg-[#0f1726]">
      <div className="flex flex-col items-center gap-1">
        <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">{ticker}</span>
        {cell.consensus && (
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${consensusBadgeColour(cell.consensus)}`}
          >
            {cell.consensus}
          </span>
        )}
        {cell.price_target && (
          <span className="text-[11px] text-slate-500 dark:text-slate-400">PT: {cell.price_target}</span>
        )}
      </div>
      {/* Arrow */}
      <div className="absolute -bottom-1.5 left-1/2 h-3 w-3 -translate-x-1/2 rotate-45 border-b border-r border-slate-200 bg-white dark:border-slate-700 dark:bg-[#0f1726]" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Coverage cell
// ---------------------------------------------------------------------------

function CovCell({ cell, ticker }: { cell: CoverageCell | undefined; ticker: string }) {
  const [hover, setHover] = useState(false);

  if (!cell?.covered) {
    return (
      <td className="border-b border-r border-slate-100 px-3 py-2 text-center dark:border-slate-800">
        <span className="text-slate-200 dark:text-slate-800">—</span>
      </td>
    );
  }

  return (
    <td className="relative border-b border-r border-slate-100 px-3 py-2 text-center dark:border-slate-800">
      <div
        className="relative inline-block"
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        <span
          className={`inline-block h-3 w-3 cursor-default rounded-full ring-2 ${dotColour(cell.consensus)}`}
        />
        {hover && <CellTooltip cell={cell} ticker={ticker} />}
      </div>
    </td>
  );
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function TableSkeleton() {
  return (
    <div className="animate-pulse overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
      <table className="min-w-full">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-[#0f1726]">
            <th className="sticky left-0 z-10 bg-slate-50 px-4 py-3 dark:bg-[#0f1726]">
              <div className="h-3 w-20 rounded bg-slate-200 dark:bg-slate-700" />
            </th>
            {TICKERS.map((t) => (
              <th key={t} className="px-3 py-3">
                <div className="mx-auto h-3 w-10 rounded bg-slate-200 dark:bg-slate-700" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 8 }).map((_, i) => (
            <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
              <td className="sticky left-0 bg-white px-4 py-3 dark:bg-[#0a101c]">
                <div className="h-3 w-32 rounded bg-slate-100 dark:bg-slate-800" />
              </td>
              {TICKERS.map((t) => (
                <td key={t} className="px-3 py-3 text-center">
                  <div className="mx-auto h-3 w-3 rounded-full bg-slate-100 dark:bg-slate-800" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------

function Legend() {
  const items = [
    { label: 'Bullish', colour: 'bg-emerald-500' },
    { label: 'Bearish', colour: 'bg-rose-500' },
    { label: 'Neutral', colour: 'bg-amber-500' },
    { label: 'Mixed',   colour: 'bg-indigo-500' },
    { label: 'Unknown', colour: 'bg-slate-400' },
  ];
  return (
    <div className="flex flex-wrap items-center gap-4">
      {items.map(({ label, colour }) => (
        <div key={label} className="flex items-center gap-1.5">
          <span className={`h-2.5 w-2.5 rounded-full ${colour}`} />
          <span className="text-xs text-slate-500 dark:text-slate-400">{label}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function CoverageMap() {
  const [rows, setRows] = useState<CoverageRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMap = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API_URL}/api/analyst-view/coverage-map`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRows(data.rows ?? data.coverage ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load coverage map');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMap();
  }, [fetchMap]);

  if (loading) return <TableSkeleton />;

  if (error) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-400">
        Error: {error}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Legend />
      <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-[#0f1726]">
              {/* Sticky analyst column header */}
              <th className="sticky left-0 z-10 whitespace-nowrap border-r border-slate-200 bg-slate-50 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 dark:border-slate-800 dark:bg-[#0f1726] dark:text-slate-400">
                Analyst
              </th>
              {/* EMS tickers */}
              {TICKERS.map((ticker) => (
                <th
                  key={ticker}
                  className={`px-3 py-3 text-center text-xs font-semibold uppercase tracking-wide ${
                    EMS_TICKERS.has(ticker)
                      ? 'text-cyan-700 dark:text-cyan-400'
                      : 'text-violet-700 dark:text-violet-400'
                  }`}
                >
                  {ticker}
                </th>
              ))}
            </tr>
            {/* Section sub-headers */}
            <tr className="border-b border-slate-100 bg-white text-[10px] dark:border-slate-800 dark:bg-[#0a101c]">
              <td className="sticky left-0 border-r border-slate-100 bg-white px-4 py-1 dark:border-slate-800 dark:bg-[#0a101c]" />
              {TICKERS.map((ticker) => (
                <td key={ticker} className="px-3 py-1 text-center text-slate-400 dark:text-slate-600">
                  {EMS_TICKERS.has(ticker) ? 'EMS' : 'Hyper'}
                </td>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={row.analyst}
                className={`border-b border-slate-100 transition-colors hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900/40 ${
                  i % 2 === 0 ? 'bg-white dark:bg-[#0a101c]' : 'bg-slate-50/50 dark:bg-[#080e1a]'
                }`}
              >
                <td className="sticky left-0 z-10 whitespace-nowrap border-r border-slate-100 bg-inherit px-4 py-2.5 font-medium text-slate-800 dark:border-slate-800 dark:text-slate-200">
                  {row.analyst}
                </td>
                {TICKERS.map((ticker) => (
                  <CovCell key={ticker} cell={row.coverage[ticker]} ticker={ticker} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>

        {rows.length === 0 && (
          <div className="py-12 text-center text-sm text-slate-500 dark:text-slate-400">
            No coverage data available.
          </div>
        )}
      </div>
      <p className="text-xs text-slate-400 dark:text-slate-500">
        Hover a dot to see consensus and price target details.
      </p>
    </div>
  );
}
