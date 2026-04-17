'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  CalendarDays,
  Clock,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Filter,
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Confidence = 'high' | 'medium' | 'low';
type DataStatus = 'confirmed' | 'preliminary' | 'estimated';

type EarningsEvent = {
  company: string;
  ticker: string;
  exchange: string;
  quarter: string;
  period_end_date: string;
  release_date: string;
  release_timing: string;
  call_date: string;
  call_time: string;
  fiscal_year: number;
  calendar_quarter: string;
  ir_url: string;
  webcast_url: string | null;
  data_status: DataStatus;
  confidence: Confidence;
  source: string;
  last_verified: string;
};

type CalendarResponse = {
  generated_at: string;
  horizon: string;
  total_events: number;
  upcoming: EarningsEvent[];
  recent: EarningsEvent[];
  companies: string[];
};

type ViewMode = 'upcoming' | 'recent' | 'all';

// ---------------------------------------------------------------------------
// Company color mapping
// ---------------------------------------------------------------------------

const TICKER_COLORS: Record<string, { dot: string; bg: string; border: string }> = {
  FLEX: { dot: 'bg-blue-500', bg: 'bg-blue-500/10', border: 'border-blue-500' },
  CLS: { dot: 'bg-indigo-500', bg: 'bg-indigo-500/10', border: 'border-indigo-500' },
  JBL: { dot: 'bg-emerald-500', bg: 'bg-emerald-500/10', border: 'border-emerald-500' },
  SANM: { dot: 'bg-red-500', bg: 'bg-red-500/10', border: 'border-red-500' },
  BHE: { dot: 'bg-amber-500', bg: 'bg-amber-500/10', border: 'border-amber-500' },
  PLXS: { dot: 'bg-teal-500', bg: 'bg-teal-500/10', border: 'border-teal-500' },
};

const TICKER_HEX: Record<string, string> = {
  FLEX: '#3B82F6',
  CLS: '#6366F1',
  JBL: '#10B981',
  SANM: '#EF4444',
  BHE: '#F59E0B',
  PLXS: '#14B8A6',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function confidenceBadge(c: Confidence) {
  switch (c) {
    case 'high':
      return {
        icon: CheckCircle2,
        label: 'High',
        cls: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
      };
    case 'medium':
      return {
        icon: AlertCircle,
        label: 'Medium',
        cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
      };
    case 'low':
      return {
        icon: HelpCircle,
        label: 'Low',
        cls: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
      };
  }
}

function daysUntil(isoDate: string): number {
  const target = new Date(isoDate + 'T00:00:00');
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

function formatDate(iso: string) {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function timingLabel(t: string) {
  if (t === 'before_open') return 'Pre-market';
  if (t === 'after_close') return 'After-close';
  return t;
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function RowSkeleton() {
  return (
    <div className="grid grid-cols-[1fr_1.2fr_1fr_0.8fr_0.7fr_0.6fr] gap-2 px-4 py-3 animate-pulse">
      <div className="h-4 w-16 rounded bg-slate-200 dark:bg-slate-700" />
      <div className="h-4 w-24 rounded bg-slate-200 dark:bg-slate-700" />
      <div className="h-4 w-20 rounded bg-slate-200 dark:bg-slate-700" />
      <div className="h-4 w-14 rounded bg-slate-200 dark:bg-slate-700" />
      <div className="h-4 w-14 rounded bg-slate-200 dark:bg-slate-700" />
      <div className="h-4 w-12 rounded bg-slate-200 dark:bg-slate-700" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Event row (table)
// ---------------------------------------------------------------------------

function EventRow({ event, isPast }: { event: EarningsEvent; isPast: boolean }) {
  const days = daysUntil(event.release_date);
  const conf = confidenceBadge(event.confidence);
  const ConfIcon = conf.icon;

  const daysDisplay = isPast
    ? `${Math.abs(days)}d ago`
    : days === 0
      ? 'Today'
      : days === 1
        ? 'Tomorrow'
        : `${days}d`;

  const colors = TICKER_COLORS[event.ticker] || { dot: 'bg-slate-400', bg: '', border: '' };

  return (
    <div
      className={`grid grid-cols-[1fr_1.2fr_1fr_0.8fr_0.7fr_0.6fr] gap-2 items-center px-4 py-3 border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors ${
        isPast ? 'opacity-60' : ''
      }`}
    >
      {/* Ticker */}
      <div className="flex items-center gap-2">
        <div className={`h-2.5 w-2.5 rounded-full ${colors.dot}`} />
        <div>
          <span className="font-mono text-sm font-semibold text-slate-800 dark:text-slate-200">
            {event.ticker}
          </span>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">{event.exchange}</p>
        </div>
      </div>

      {/* Quarter + period */}
      <div>
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{event.quarter}</p>
        <p className="text-[11px] text-slate-500 dark:text-slate-400">
          Period ends {formatDate(event.period_end_date)}
        </p>
      </div>

      {/* Release date + timing */}
      <div>
        <p className="text-sm font-medium text-slate-800 dark:text-slate-200">
          {formatDate(event.release_date)}
        </p>
        <p className="text-[11px] text-slate-500 dark:text-slate-400">
          {timingLabel(event.release_timing)} · Call {event.call_time}
        </p>
      </div>

      {/* Days until */}
      <div>
        <span
          className={`inline-block rounded-md px-2 py-0.5 text-xs font-semibold ${
            isPast
              ? 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
              : days <= 7
                ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                : days <= 30
                  ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                  : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
          }`}
        >
          {daysDisplay}
        </span>
      </div>

      {/* Confidence */}
      <div className="flex items-center gap-1">
        <ConfIcon className="h-3.5 w-3.5" />
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${conf.cls}`}>
          {conf.label}
        </span>
      </div>

      {/* IR link */}
      <div>
        <a
          href={event.ir_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          IR
        </a>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// View mode tabs
// ---------------------------------------------------------------------------

function ViewTabs({
  value,
  onChange,
  counts,
}: {
  value: ViewMode;
  onChange: (v: ViewMode) => void;
  counts: Record<ViewMode, number>;
}) {
  const tabs: { key: ViewMode; label: string }[] = [
    { key: 'upcoming', label: 'Upcoming' },
    { key: 'recent', label: 'Recent' },
    { key: 'all', label: 'All' },
  ];

  return (
    <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800">
      {tabs.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
            value === key
              ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white'
              : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'
          }`}
        >
          {label}
          <span
            className={`rounded-full px-1.5 text-[11px] font-semibold ${
              value === key
                ? 'bg-slate-100 text-slate-600 dark:bg-slate-600 dark:text-slate-200'
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
// Ticker filter
// ---------------------------------------------------------------------------

function TickerFilter({
  tickers,
  selected,
  onChange,
}: {
  tickers: string[];
  selected: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <Filter className="h-4 w-4 text-slate-400" />
      <button
        onClick={() => onChange('')}
        className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
          !selected
            ? 'bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900'
            : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
        }`}
      >
        All
      </button>
      {tickers.map((t) => (
        <button
          key={t}
          onClick={() => onChange(selected === t ? '' : t)}
          className={`rounded-md px-2.5 py-1 text-xs font-mono font-semibold transition-colors ${
            selected === t
              ? 'bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900'
              : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
          }`}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Calendar grid (month view)
// ---------------------------------------------------------------------------

function CalendarGrid({
  events,
  selectedMonth,
  selectedYear,
  onPrevMonth,
  onNextMonth,
}: {
  events: EarningsEvent[];
  selectedMonth: number;
  selectedYear: number;
  onPrevMonth: () => void;
  onNextMonth: () => void;
}) {
  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  const daysInMonth = new Date(selectedYear, selectedMonth + 1, 0).getDate();
  const firstDay = new Date(selectedYear, selectedMonth, 1).getDay();
  const monthStr = `${selectedYear}-${String(selectedMonth + 1).padStart(2, '0')}`;

  const monthEvents = events.filter((e) => e.release_date.startsWith(monthStr));

  const todayStr = new Date().toISOString().split('T')[0];

  const cells = [];
  for (let i = 0; i < firstDay; i++) {
    cells.push(
      <div key={`empty-${i}`} className="h-24 bg-slate-50 dark:bg-slate-900/30" />,
    );
  }
  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${selectedYear}-${String(selectedMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const dayEvents = monthEvents.filter((e) => e.release_date === dateStr);
    const isToday = todayStr === dateStr;

    cells.push(
      <div
        key={day}
        className={`h-24 border border-slate-100 dark:border-slate-800 p-1 ${
          isToday
            ? 'bg-blue-50 ring-2 ring-blue-500 dark:bg-blue-950/30'
            : 'bg-white dark:bg-slate-900/50'
        }`}
      >
        <div className={`text-sm font-medium ${isToday ? 'text-blue-600 dark:text-blue-400' : 'text-slate-600 dark:text-slate-400'}`}>
          {day}
        </div>
        <div className="mt-1 space-y-1 overflow-y-auto max-h-16">
          {dayEvents.map((event, idx) => (
            <div
              key={idx}
              className="text-[10px] px-1 py-0.5 rounded truncate font-medium"
              style={{
                backgroundColor: (TICKER_HEX[event.ticker] || '#94A3B8') + '20',
                borderLeft: `3px solid ${TICKER_HEX[event.ticker] || '#94A3B8'}`,
                color: TICKER_HEX[event.ticker] || '#64748B',
              }}
              title={`${event.company} ${event.quarter} - ${timingLabel(event.release_timing)}`}
            >
              {event.ticker} {event.quarter}
            </div>
          ))}
        </div>
      </div>,
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-[#0a101c] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <button onClick={onPrevMonth} className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors">
            <ChevronLeft className="h-5 w-5 text-slate-600 dark:text-slate-400" />
          </button>
          <h3 className="text-lg font-bold text-slate-800 dark:text-slate-200">
            {months[selectedMonth]} {selectedYear}
          </h3>
          <button onClick={onNextMonth} className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors">
            <ChevronRight className="h-5 w-5 text-slate-600 dark:text-slate-400" />
          </button>
        </div>
      </div>

      {/* DOW headers */}
      <div className="grid grid-cols-7">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
          <div key={d} className="text-center text-xs font-medium text-slate-500 dark:text-slate-400 py-2 bg-slate-50 dark:bg-slate-900/30">
            {d}
          </div>
        ))}
      </div>

      {/* Grid */}
      <div className="grid grid-cols-7 gap-px bg-slate-200 dark:bg-slate-800">
        {cells}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 px-5 py-3 border-t border-slate-100 dark:border-slate-800">
        {Object.entries(TICKER_HEX).map(([ticker, hex]) => (
          <div key={ticker} className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded" style={{ backgroundColor: hex }} />
            <span className="text-[11px] text-slate-600 dark:text-slate-400 font-mono font-medium">{ticker}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary cards
// ---------------------------------------------------------------------------

function SummaryCards({ data }: { data: CalendarResponse }) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const upcoming = data.upcoming;

  const within7 = upcoming.filter((e) => daysUntil(e.release_date) <= 7 && daysUntil(e.release_date) >= 0).length;
  const within30 = upcoming.filter((e) => daysUntil(e.release_date) <= 30 && daysUntil(e.release_date) >= 0).length;
  const highConf = upcoming.filter((e) => e.confidence === 'high').length;
  const nextEvent = upcoming[0];

  const cards = [
    { label: 'This Week', value: within7, gradient: 'from-blue-500 to-blue-600', iconColor: 'text-blue-200' },
    { label: 'Next 30 Days', value: within30, gradient: 'from-purple-500 to-purple-600', iconColor: 'text-purple-200' },
    { label: 'High Confidence', value: highConf, gradient: 'from-green-500 to-green-600', iconColor: 'text-green-200' },
    { label: 'Companies', value: (data.companies ?? []).length, gradient: 'from-amber-500 to-amber-600', iconColor: 'text-amber-200' },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((c) => (
        <div key={c.label} className={`bg-gradient-to-br ${c.gradient} rounded-2xl p-4 text-white shadow-lg`}>
          <p className="text-sm opacity-80">{c.label}</p>
          <p className="text-3xl font-bold mt-1">{c.value}</p>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Upcoming sidebar
// ---------------------------------------------------------------------------

function UpcomingSidebar({ events }: { events: EarningsEvent[] }) {
  const next5 = events.slice(0, 5);
  const nextEvent = events[0];

  return (
    <div className="space-y-4">
      {/* Next event highlight */}
      {nextEvent && (
        <div className="rounded-2xl bg-gradient-to-br from-slate-800 to-slate-900 text-white p-5 shadow-lg">
          <p className="text-xs uppercase tracking-wider text-slate-400 mb-2">Next Earnings</p>
          <p className="text-xl font-bold">{nextEvent.company}</p>
          <p className="text-sm text-slate-300 mt-1">{nextEvent.quarter}</p>
          <div className="mt-3 space-y-1.5 text-sm">
            <div className="flex items-center gap-2 text-slate-300">
              <CalendarDays className="h-4 w-4 text-slate-400" />
              {formatDate(nextEvent.release_date)}
            </div>
            <div className="flex items-center gap-2 text-slate-300">
              <Clock className="h-4 w-4 text-slate-400" />
              {timingLabel(nextEvent.release_timing)} · {nextEvent.call_time}
            </div>
          </div>
          <div className="mt-3">
            <span className="inline-block rounded-md bg-blue-500/20 px-2 py-1 text-xs font-semibold text-blue-300">
              {daysUntil(nextEvent.release_date) === 0
                ? 'Today'
                : daysUntil(nextEvent.release_date) === 1
                  ? 'Tomorrow'
                  : `In ${daysUntil(nextEvent.release_date)} days`}
            </span>
          </div>
        </div>
      )}

      {/* Upcoming list */}
      <div className="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0a101c] overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">Upcoming Events</h3>
        </div>
        <div className="divide-y divide-slate-100 dark:divide-slate-800 max-h-96 overflow-y-auto">
          {next5.map((event, idx) => {
            const days = daysUntil(event.release_date);
            const colors = TICKER_COLORS[event.ticker];
            return (
              <div
                key={idx}
                className={`px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors border-l-4 ${colors?.border || 'border-slate-300'}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-sm font-semibold text-slate-800 dark:text-slate-200">
                    {event.ticker}
                  </span>
                  <span className={`text-[11px] font-semibold rounded-full px-2 py-0.5 ${confidenceBadge(event.confidence).cls}`}>
                    {event.data_status === 'confirmed' ? 'Confirmed' : 'Estimated'}
                  </span>
                </div>
                <p className="text-xs text-slate-600 dark:text-slate-400">{event.quarter}</p>
                <div className="flex items-center justify-between mt-1.5">
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    {formatDate(event.release_date)}
                  </span>
                  <span className={`text-[11px] font-medium ${days <= 7 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-500 dark:text-slate-400'}`}>
                    {days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : `${days} days`}
                  </span>
                </div>
              </div>
            );
          })}
          {next5.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
              No upcoming events
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function CalendarPage() {
  const [data, setData] = useState<CalendarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('upcoming');
  const [tickerFilter, setTickerFilter] = useState('');
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth());
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());

  const fetchCalendar = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API_URL}/api/calendar`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: CalendarResponse = await res.json();
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load earnings calendar');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCalendar();
  }, [fetchCalendar]);

  const syncCalendar = async () => {
    setSyncing(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/calendar/sync`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      // sync endpoint returns {calendar: CalendarResponse, updated: [...], ...}
      if (json.calendar) {
        setData(json.calendar);
      } else {
        await fetchCalendar();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const prevMonth = () => {
    if (selectedMonth === 0) {
      setSelectedMonth(11);
      setSelectedYear(selectedYear - 1);
    } else {
      setSelectedMonth(selectedMonth - 1);
    }
  };

  const nextMonth = () => {
    if (selectedMonth === 11) {
      setSelectedMonth(0);
      setSelectedYear(selectedYear + 1);
    } else {
      setSelectedMonth(selectedMonth + 1);
    }
  };

  // Derive event lists
  const upcoming = data?.upcoming ?? [];
  const recent = data?.recent ?? [];
  const all = [...upcoming, ...recent].sort((a, b) => a.release_date.localeCompare(b.release_date));

  const eventsForView = viewMode === 'upcoming' ? upcoming : viewMode === 'recent' ? recent : all;
  const filtered = tickerFilter
    ? eventsForView.filter((e) => e.ticker === tickerFilter)
    : eventsForView;

  const counts: Record<ViewMode, number> = {
    upcoming: upcoming.length,
    recent: recent.length,
    all: all.length,
  };

  // All events for calendar grid (unfiltered by view mode, but respect ticker)
  const calendarEvents = tickerFilter ? all.filter((e) => e.ticker === tickerFilter) : all;

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto" />
          <p className="text-slate-600 dark:text-slate-400 mt-4 font-medium">Loading earnings calendar...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <div className="bg-gradient-to-br from-indigo-600 to-purple-700 p-3 rounded-xl shadow-lg shadow-indigo-500/20">
            <CalendarDays className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-slate-900 dark:text-white">EMS Earnings Calendar</h1>
            <p className="text-slate-500 dark:text-slate-400 mt-1">
              Track upcoming earnings for EMS peer companies
            </p>
          </div>
        </div>
        <button
          onClick={syncCalendar}
          disabled={syncing}
          className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors disabled:opacity-50 text-sm font-medium text-slate-700 dark:text-slate-300"
        >
          <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-400">
          Error: {error}
        </div>
      )}

      {/* Summary cards */}
      {data && <SummaryCards data={data} />}

      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 mt-6 mb-4">
        <ViewTabs value={viewMode} onChange={setViewMode} counts={counts} />
        <TickerFilter
          tickers={data?.companies ?? []}
          selected={tickerFilter}
          onChange={setTickerFilter}
        />
      </div>

      {/* Confidence legend */}
      <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-500 dark:text-slate-400 mb-4">
        <span className="flex items-center gap-1">
          <Clock className="h-3 w-3" /> Dates based on historical filing patterns
        </span>
        <span className="flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3 text-green-500" /> High confidence
        </span>
        <span className="flex items-center gap-1">
          <AlertCircle className="h-3 w-3 text-amber-500" /> Medium
        </span>
        <span className="flex items-center gap-1">
          <HelpCircle className="h-3 w-3 text-slate-400" /> Low
        </span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Left: Table + Calendar grid */}
        <div className="xl:col-span-2 space-y-6">
          {/* Table */}
          <div className="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0a101c] overflow-hidden shadow-sm">
            {/* Table header */}
            <div className="grid grid-cols-[1fr_1.2fr_1fr_0.8fr_0.7fr_0.6fr] gap-2 bg-slate-50 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:bg-[#0f1726] dark:text-slate-400">
              <span>Ticker</span>
              <span>Quarter</span>
              <span>Release Date</span>
              <span>Countdown</span>
              <span>Confidence</span>
              <span>Link</span>
            </div>

            {/* Table body */}
            {filtered.length > 0 ? (
              filtered.map((event, i) => (
                <EventRow
                  key={`${event.ticker}-${event.quarter}-${i}`}
                  event={event}
                  isPast={daysUntil(event.release_date) < 0}
                />
              ))
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
                  No earnings events found
                </p>
                <p className="mt-1 max-w-xs text-xs text-slate-400 dark:text-slate-500">
                  {tickerFilter
                    ? `No events for ${tickerFilter} in this view. Try clearing the filter.`
                    : 'No events in the selected time range.'}
                </p>
              </div>
            )}
          </div>

          {/* Calendar grid */}
          <CalendarGrid
            events={calendarEvents}
            selectedMonth={selectedMonth}
            selectedYear={selectedYear}
            onPrevMonth={prevMonth}
            onNextMonth={nextMonth}
          />
        </div>

        {/* Right: Upcoming sidebar */}
        <div>
          <UpcomingSidebar events={upcoming} />
        </div>
      </div>

      {/* Footer */}
      {data && (
        <p className="mt-6 text-[11px] text-slate-400 dark:text-slate-500">
          {data.total_events} total events across {(data.companies ?? []).length} companies
          {' · '}Horizon: {data.horizon}
          {' · '}Generated {new Date(data.generated_at).toLocaleString()}
        </p>
      )}
    </div>
  );
}
