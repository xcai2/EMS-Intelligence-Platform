"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw, TrendingUp, TrendingDown, Minus, AlertCircle } from "lucide-react";

// Components
import AnalystCards from "./components/AnalystCards";
import RatingsFeed from "./components/RatingsFeed";
import ConsensusView from "./components/ConsensusView";
import CoverageMap from "./components/CoverageMap";
import EarningsCalendar from "./components/EarningsCalendar";
import KeyQuotes from "./components/KeyQuotes";
import WeeklyThemes from "./components/WeeklyThemes";
import FlexBenchmark from "./components/FlexBenchmark";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const REFRESH_INTERVAL_MS = 5 * 60 * 1000;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Consensus = "Bullish" | "Neutral" | "Bearish" | "Mixed" | "Unknown";

type CompanyIntelResult = {
  ticker: string;
  company: string;
  kind: "EMS" | "Hyperscaler";
  consensus: Consensus;
  price_target: string;
  recent_actions: string[];
  key_view: string;
  sources: { title: string; url: string }[];
  updated_at: string;
  error?: string | null;
};

type CompanyIntelResponse = {
  companies: CompanyIntelResult[];
  cached_at?: string | null;
  warning?: string | null;
};

type Tab =
  | "executive"
  | "companies"
  | "analysts"
  | "quotes"
  | "calendar"
  | "feed";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(iso: string | undefined | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

const CONSENSUS_CONFIG: Record<
  Consensus,
  { bg: string; text: string; border: string; Icon: typeof TrendingUp }
> = {
  Bullish: { bg: "bg-green-100 dark:bg-green-900/30",  text: "text-green-700 dark:text-green-300",  border: "border-green-300 dark:border-green-700", Icon: TrendingUp  },
  Mixed:   { bg: "bg-yellow-100 dark:bg-yellow-900/30", text: "text-yellow-700 dark:text-yellow-300", border: "border-yellow-300 dark:border-yellow-700", Icon: Minus       },
  Neutral: { bg: "bg-slate-200/50 dark:bg-gray-800/50",   text: "text-slate-700 dark:text-gray-300",   border: "border-slate-300 dark:border-gray-600",   Icon: Minus       },
  Bearish: { bg: "bg-red-100 dark:bg-red-900/30",    text: "text-red-700 dark:text-red-300",    border: "border-red-300 dark:border-red-700",    Icon: TrendingDown },
  Unknown: { bg: "bg-slate-200/30 dark:bg-gray-800/30",   text: "text-slate-500 dark:text-gray-500",   border: "border-slate-200 dark:border-gray-700",   Icon: Minus       },
};

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------

const TABS: { id: Tab; label: string; icon: string; description: string }[] = [
  { id: "executive",  label: "Executive",  icon: "⚡", description: "Strategic themes" },
  { id: "companies",  label: "Companies",  icon: "🏢", description: "Consensus & PTs" },
  { id: "analysts",   label: "Analysts",   icon: "👥", description: "Analyst roster" },
  { id: "quotes",     label: "Quotes",     icon: "💬", description: "Key Q&A" },
  { id: "calendar",   label: "Calendar",   icon: "📅", description: "Earnings dates" },
  { id: "feed",       label: "Feed",       icon: "📡", description: "Live signals" },
];

// ---------------------------------------------------------------------------
// Header stat strip
// ---------------------------------------------------------------------------

function StatStrip({ intel }: { intel: CompanyIntelResponse | null }) {
  if (!intel?.companies?.length) return null;

  const ems = intel.companies.filter((c) => c.kind === "EMS");
  const flex = intel.companies.find((c) => c.ticker === "FLEX");
  const bullish = ems.filter((c) => c.consensus === "Bullish").length;
  const bearish = ems.filter((c) => c.consensus === "Bearish").length;

  return (
    <div className="flex flex-wrap gap-3 px-4 py-2 bg-slate-50 dark:bg-[#0d1117] border-b border-slate-200 dark:border-[#1e2535] text-xs">
      {flex && (
        <>
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500 dark:text-gray-500">FLEX</span>
            {(() => {
              const cfg = CONSENSUS_CONFIG[flex.consensus] ?? CONSENSUS_CONFIG.Unknown;
              return (
                <span className={`px-1.5 py-0.5 rounded text-[11px] ${cfg.bg} ${cfg.text}`}>
                  {flex.consensus}
                </span>
              );
            })()}
            {flex.price_target !== "—" && (
              <span className="text-slate-600 dark:text-gray-400">{flex.price_target}</span>
            )}
          </div>
          <span className="text-slate-300 dark:text-[#1e2535]">|</span>
        </>
      )}
      <div className="flex items-center gap-1.5 text-slate-500 dark:text-gray-500">
        <span className="text-green-600 dark:text-green-400 font-semibold">{bullish}</span> bull
        <span className="text-gray-600 mx-1">/</span>
        <span className="text-red-600 dark:text-red-400 font-semibold">{bearish}</span> bear
        <span className="text-gray-600 ml-1">across EMS</span>
      </div>
      {intel.cached_at && (
        <>
          <span className="text-slate-300 dark:text-[#1e2535]">|</span>
          <span className="text-gray-600">Updated {timeAgo(intel.cached_at)}</span>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AnalystViewPageFeature() {
  const [activeTab, setActiveTab] = useState<Tab>("executive");
  const [intel, setIntel] = useState<CompanyIntelResponse | null>(null);
  const [intelLoading, setIntelLoading] = useState(true);
  const [intelWarning, setIntelWarning] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const fetchIntel = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const res = await fetch(`${API_URL}/api/analyst-view/company-intel`);
      const data: CompanyIntelResponse = await res.json();
      setIntel(data);
      setIntelWarning(data.warning ?? null);
    } catch (e) {
      setIntelWarning("Failed to connect to backend.");
    } finally {
      setIntelLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchIntel();
    timerRef.current = setInterval(() => fetchIntel(), REFRESH_INTERVAL_MS);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [fetchIntel]);

  return (
    <div className="flex flex-col h-full bg-slate-50 dark:bg-[#0a0e1a] text-slate-900 dark:text-gray-100">
      {/* Page header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-[#1e2535]">
        <div>
          <h1 className="text-base font-semibold text-slate-900 dark:text-white tracking-tight">
            Analyst Intelligence
          </h1>
          <p className="text-xs text-slate-500 dark:text-gray-500 mt-0.5">
            EMS &amp; Hyperscaler coverage · auto-refreshes every 5 min
          </p>
        </div>
        <button
          onClick={() => fetchIntel(true)}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-slate-100 dark:bg-[#1a1f2e] border border-slate-300 dark:border-[#2a3045] text-slate-600 dark:text-gray-400 hover:text-slate-800 dark:hover:text-gray-200 hover:border-slate-400 dark:hover:border-gray-500 disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {/* Warning banner */}
      {intelWarning && (
        <div className="flex items-center gap-2 px-4 py-2 bg-yellow-100 dark:bg-yellow-900/20 border-b border-yellow-200 dark:border-yellow-800/50 text-yellow-700 dark:text-yellow-300 text-xs">
          <AlertCircle size={12} className="shrink-0" />
          {intelWarning}
        </div>
      )}

      {/* Stats strip */}
      {!intelLoading && <StatStrip intel={intel} />}

      {/* Tab bar */}
      <div className="flex items-center gap-0.5 px-3 pt-2 border-b border-slate-200 dark:border-[#1e2535] overflow-x-auto scrollbar-none">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs rounded-t-lg border-b-2 whitespace-nowrap transition-colors ${
              activeTab === tab.id
                ? "border-blue-500 text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/10"
                : "border-transparent text-slate-500 dark:text-gray-500 hover:text-slate-700 dark:hover:text-gray-300 hover:bg-slate-100 dark:hover:bg-[#1a1f2e]"
            }`}
          >
            <span>{tab.icon}</span>
            <span className="font-medium">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === "executive" && (
          <div className="max-w-3xl mx-auto">
            <WeeklyThemes />
          </div>
        )}

        {activeTab === "companies" && (
          <div className="space-y-6">
            <ConsensusView />
            <div className="border-t border-slate-200 dark:border-[#1e2535] pt-6">
              <p className="text-xs font-semibold text-slate-600 dark:text-gray-400 uppercase tracking-wider mb-4">
                Flex vs EMS Peers
              </p>
              <FlexBenchmark />
            </div>
          </div>
        )}

        {activeTab === "analysts" && (
          <div className="space-y-6">
            <AnalystCards />
            <div className="border-t border-slate-200 dark:border-[#1e2535] pt-6">
              <p className="text-xs font-semibold text-slate-600 dark:text-gray-400 uppercase tracking-wider mb-4">
                Coverage Matrix
              </p>
              <CoverageMap />
            </div>
          </div>
        )}

        {activeTab === "quotes" && (
          <div className="max-w-3xl mx-auto">
            <KeyQuotes />
          </div>
        )}

{activeTab === "calendar" && (
          <div className="max-w-3xl mx-auto">
            <EarningsCalendar />
          </div>
        )}

        {activeTab === "feed" && (
          <div className="space-y-6">
            <div>
              <p className="text-xs font-semibold text-slate-600 dark:text-gray-400 uppercase tracking-wider mb-4">
                Ratings &amp; Actions Feed
              </p>
              <RatingsFeed />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
