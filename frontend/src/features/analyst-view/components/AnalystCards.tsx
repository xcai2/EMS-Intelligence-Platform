'use client';

import { useCallback, useEffect, useState } from 'react';
import { ExternalLink, Search, User } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type AnalystSummary = {
  name: string;
  institution: string;
  summary: string;
  source_url: string;
};

type AnalystRosterEntry = {
  name: string;
  institution: string;
  tipranksSlug: string;
  core: boolean;
};

// ---------------------------------------------------------------------------
// Hardcoded roster
// ---------------------------------------------------------------------------

const ANALYST_ROSTER: AnalystRosterEntry[] = [
  { name: 'Thanos Moschopoulos',  institution: 'BMO Capital Markets',      tipranksSlug: 'thanos-moschopoulos',  core: true  },
  { name: 'Matthew Sheerin',       institution: 'Stifel',                    tipranksSlug: 'matthew-sheerin',       core: true  },
  { name: 'Samik Chatterjee',      institution: 'JPMorgan',                  tipranksSlug: 'samik-chatterjee',      core: true  },
  { name: 'James Ricchiuti',       institution: 'Needham & Company',         tipranksSlug: 'james-ricchiuti',       core: true  },
  { name: 'Maxim Matushansky',     institution: 'RBC Capital Markets',       tipranksSlug: 'maxim-matushansky',     core: true  },
  { name: 'Daniel Chan',           institution: 'TD Securities',             tipranksSlug: 'daniel-chan',           core: true  },
  { name: 'Robert Young',          institution: 'Canaccord Genuity',         tipranksSlug: 'robert-young',          core: true  },
  { name: 'Mark Delaney',          institution: 'Goldman Sachs',             tipranksSlug: 'mark-delaney',          core: false },
  { name: 'Timothy Long',          institution: 'Barclays',                  tipranksSlug: 'timothy-long',          core: false },
  { name: 'George Wang',           institution: 'Barclays',                  tipranksSlug: 'george-wang',           core: false },
  { name: 'Ruplu Bhattacharya',    institution: 'Bank of America',           tipranksSlug: 'ruplu-bhattacharya',    core: false },
  { name: 'Jacob Moore',           institution: 'KeyBanc Capital Markets',   tipranksSlug: 'jacob-moore',           core: false },
  { name: 'Steven Barger',         institution: 'KeyBanc Capital Markets',   tipranksSlug: 'steven-barger',         core: false },
  { name: 'Steven Fox',            institution: 'Fox Advisors',              tipranksSlug: 'steven-fox',            core: false },
  { name: 'Ruben Roy',             institution: 'Stifel',                    tipranksSlug: 'ruben-roy',             core: false },
  { name: 'Todd Coupland',         institution: 'CIBC World Markets',        tipranksSlug: 'todd-coupland',         core: false },
  { name: 'Paul Treiber',          institution: 'RBC Capital Markets',       tipranksSlug: 'paul-treiber',          core: false },
  { name: 'Atif Malik',            institution: 'Citigroup',                 tipranksSlug: 'atif-malik',            core: false },
  { name: 'David Vogt',            institution: 'UBS',                       tipranksSlug: 'david-vogt',            core: false },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function tipranksUrl(slug: string) {
  return `https://www.tipranks.com/experts/analysts/${slug}`;
}

function linkedInSearchUrl(name: string, institution: string) {
  return `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(`${name} ${institution}`)}`;
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function CardSkeleton() {
  return (
    <div className="animate-pulse rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0a101c]">
      <div className="mb-3 flex items-start justify-between">
        <div className="space-y-1.5">
          <div className="h-4 w-36 rounded bg-slate-200 dark:bg-slate-700" />
          <div className="h-3 w-24 rounded bg-slate-200 dark:bg-slate-700" />
        </div>
        <div className="h-5 w-16 rounded-full bg-slate-200 dark:bg-slate-700" />
      </div>
      <div className="mb-4 space-y-1.5">
        <div className="h-3 w-full rounded bg-slate-100 dark:bg-slate-800" />
        <div className="h-3 w-5/6 rounded bg-slate-100 dark:bg-slate-800" />
      </div>
      <div className="flex gap-2">
        <div className="h-7 w-24 rounded-lg bg-slate-200 dark:bg-slate-700" />
        <div className="h-7 w-24 rounded-lg bg-slate-200 dark:bg-slate-700" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single card
// ---------------------------------------------------------------------------

function AnalystCard({
  entry,
  summary,
  loading,
}: {
  entry: AnalystRosterEntry;
  summary: AnalystSummary | undefined;
  loading: boolean;
}) {
  const hasSummary = summary && summary.summary && summary.summary !== '—';

  return (
    <div className="flex flex-col rounded-2xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md dark:border-slate-800 dark:bg-[#0a101c]">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-slate-100 p-4 dark:border-slate-800">
        <div className="min-w-0">
          <p
            className={`truncate text-base ${
              entry.core
                ? 'font-semibold text-slate-900 dark:text-white'
                : 'font-medium text-slate-800 dark:text-slate-200'
            }`}
          >
            {entry.name}
          </p>
          <p className="mt-0.5 truncate text-sm text-slate-500 dark:text-slate-400">{entry.institution}</p>
        </div>
        <span
          className={
            entry.core
              ? 'shrink-0 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-semibold text-emerald-800 dark:text-emerald-300'
              : 'shrink-0 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400'
          }
        >
          {entry.core ? 'Core' : 'Extended'}
        </span>
      </div>

      {/* Summary */}
      <div className="flex-1 px-4 py-3">
        {loading ? (
          <div className="space-y-1.5">
            <div className="h-3 w-full animate-pulse rounded bg-slate-100 dark:bg-slate-800" />
            <div className="h-3 w-4/5 animate-pulse rounded bg-slate-100 dark:bg-slate-800" />
          </div>
        ) : hasSummary ? (
          <a
            href={summary.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="group block"
          >
            <p className="line-clamp-2 text-sm italic leading-relaxed text-slate-600 group-hover:text-cyan-700 dark:text-slate-400 dark:group-hover:text-cyan-400">
              &ldquo;{summary.summary}&rdquo;
            </p>
          </a>
        ) : (
          <p className="text-xs italic text-slate-400 dark:text-slate-500">No AI summary available yet.</p>
        )}
      </div>

      {/* Footer links */}
      <div className="flex items-center gap-2 border-t border-slate-100 px-4 py-2.5 dark:border-slate-800">
        <a
          href={tipranksUrl(entry.tipranksSlug)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          <ExternalLink className="h-3 w-3" />
          TipRanks
        </a>
        <a
          href={linkedInSearchUrl(entry.name, entry.institution)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-lg bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100 dark:bg-blue-900/20 dark:text-blue-400 dark:hover:bg-blue-900/30"
        >
          <User className="h-3 w-3" />
          LinkedIn
        </a>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AnalystCards() {
  const [summaries, setSummaries] = useState<AnalystSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [institutionFilter, setInstitutionFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const fetchSummaries = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API_URL}/api/analyst-view/analyst-summaries`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSummaries(data.analysts ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load summaries');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSummaries();
  }, [fetchSummaries]);

  const institutions = Array.from(new Set(ANALYST_ROSTER.map((a) => a.institution))).sort();

  const filtered = ANALYST_ROSTER.filter((a) => {
    const matchesInstitution = !institutionFilter || a.institution === institutionFilter;
    const matchesSearch =
      !searchQuery || a.name.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesInstitution && matchesSearch;
  });

  const summaryMap = new Map(summaries.map((s) => [s.name, s]));

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search analyst name…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 dark:border-slate-700 dark:bg-[#0f1726] dark:text-white dark:placeholder-slate-500"
          />
        </div>
        <select
          value={institutionFilter}
          onChange={(e) => setInstitutionFilter(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 dark:border-slate-700 dark:bg-[#0f1726] dark:text-slate-300"
        >
          <option value="">All institutions</option>
          {institutions.map((inst) => (
            <option key={inst} value={inst}>
              {inst}
            </option>
          ))}
        </select>
        <span className="text-xs text-slate-400 dark:text-slate-500">
          {filtered.length} of {ANALYST_ROSTER.length} analysts
        </span>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-400">
          Error loading summaries: {error}
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {loading && summaries.length === 0
          ? Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)
          : filtered.map((entry) => (
              <AnalystCard
                key={`${entry.name}::${entry.institution}`}
                entry={entry}
                summary={summaryMap.get(entry.name)}
                loading={loading}
              />
            ))}
      </div>

      {!loading && filtered.length === 0 && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900/30 dark:text-slate-400">
          No analysts match your filters.
        </div>
      )}
    </div>
  );
}
