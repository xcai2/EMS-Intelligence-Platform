"use client";

import React, { useEffect, useState } from "react";

interface ThemeItem {
  title: string;
  supporting_analysts: string[];
  supporting_companies: string[];
  explanation: string;
  flex_implication: string;
  severity: "High" | "Medium" | "Low";
}

interface HistoryEntry {
  id: number;
  week_start: string;
  themes: ThemeItem[];
  generated_at: string;
}

interface ThemesResponse {
  themes: ThemeItem[];
  generated_at: string;
  week_start: string;
  source: "cache" | "generated" | "error";
  warning?: string;
  history?: HistoryEntry[];
}

const SEVERITY_CONFIG = {
  High:   { bg: "bg-red-100 dark:bg-red-900/30",    text: "text-red-700 dark:text-red-300",    border: "border-red-300 dark:border-red-700",    dot: "bg-red-500"    },
  Medium: { bg: "bg-yellow-100 dark:bg-yellow-900/30", text: "text-yellow-700 dark:text-yellow-300", border: "border-yellow-300 dark:border-yellow-700", dot: "bg-yellow-500" },
  Low:    { bg: "bg-green-100 dark:bg-green-900/30",  text: "text-green-700 dark:text-green-300",  border: "border-green-300 dark:border-green-700",  dot: "bg-green-500"  },
};

function ThemeCard({ theme, rank }: { theme: ThemeItem; rank: number }) {
  const [expanded, setExpanded] = useState(rank === 0);
  const sev = SEVERITY_CONFIG[theme.severity] ?? SEVERITY_CONFIG.Low;

  return (
    <div className={`rounded-xl border overflow-hidden ${sev.border} ${sev.bg}`}>
      <button
        className="w-full text-left px-4 py-3 flex items-center gap-3"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${sev.dot} text-slate-900 dark:text-white`}>
          {rank + 1}
        </span>
        <span className={`text-sm font-semibold flex-1 ${sev.text}`}>{theme.title}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${sev.border} ${sev.text} shrink-0`}>
          {theme.severity}
        </span>
        <span className="text-gray-600 text-xs ml-1">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/5 pt-3">
          {/* Explanation */}
          <p className="text-sm text-slate-700 dark:text-gray-300 leading-relaxed">{theme.explanation}</p>

          {/* Flex implication */}
          <div className="flex items-start gap-2 bg-slate-50 dark:bg-[#0d1117] rounded-lg p-3">
            <span className="text-yellow-600 dark:text-yellow-400 text-xs font-bold shrink-0 mt-0.5">⚡ Flex</span>
            <p className="text-xs text-slate-700 dark:text-gray-300 leading-relaxed">{theme.flex_implication}</p>
          </div>

          {/* Supporting data */}
          <div className="grid grid-cols-2 gap-3">
            {theme.supporting_analysts?.length > 0 && (
              <div>
                <p className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-gray-500 mb-1.5">Analysts</p>
                <div className="flex flex-wrap gap-1">
                  {theme.supporting_analysts.map((a) => (
                    <span key={a} className="text-[11px] bg-slate-100 dark:bg-[#1a1f2e] border border-slate-300 dark:border-[#2a3045] text-slate-700 dark:text-gray-300 px-2 py-0.5 rounded">
                      {a}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {theme.supporting_companies?.length > 0 && (
              <div>
                <p className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-gray-500 mb-1.5">Companies</p>
                <div className="flex flex-wrap gap-1">
                  {theme.supporting_companies.map((c) => (
                    <span key={c} className="text-[11px] font-mono font-bold text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/30 px-2 py-0.5 rounded">
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function WeeklyThemes() {
  const [data, setData] = useState<ThemesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadThemes = async (force = false) => {
    if (force) setRegenerating(true);
    else setLoading(true);
    setError(null);
    try {
      const url = force
        ? "/api/analyst-view/generate-weekly-themes"
        : "/api/analyst-view/weekly-themes";
      const res = await fetch(url, { method: force ? "POST" : "GET" });
      const json: ThemesResponse = await res.json();
      if (json.warning && json.themes?.length === 0) {
        setError(json.warning);
      } else {
        setData(json);
      }
    } catch {
      setError("Failed to load weekly themes.");
    } finally {
      setLoading(false);
      setRegenerating(false);
    }
  };

  useEffect(() => {
    loadThemes(false);
  }, []);

  const timeAgo = (iso: string) => {
    if (!iso) return "";
    const diff = Date.now() - new Date(iso).getTime();
    const h = Math.floor(diff / 3600000);
    if (h < 1) return `${Math.floor(diff / 60000)}m ago`;
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Strategic Themes</h3>
          <p className="text-xs text-slate-500 dark:text-gray-500 mt-0.5">
            {data?.source === "cache"
              ? `Cached themes — generated ${timeAgo(data.generated_at)}`
              : data?.source === "generated"
              ? `Generated ${timeAgo(data?.generated_at ?? "")}`
              : "AI-synthesized from analyst actions, summaries, and live signals"}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowHistory((v) => !v)}
            className="px-3 py-1.5 text-xs rounded-lg bg-slate-100 dark:bg-[#1a1f2e] border border-slate-300 dark:border-[#2a3045] text-slate-600 dark:text-gray-400 hover:text-slate-800 dark:hover:text-gray-200 hover:border-slate-400 dark:hover:border-gray-500 transition-colors"
          >
            {showHistory ? "Hide History" : "History"}
          </button>
          <button
            onClick={() => loadThemes(true)}
            disabled={regenerating}
            className="px-3 py-1.5 text-xs rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-wait text-slate-900 dark:text-white transition-colors flex items-center gap-2"
          >
            {regenerating ? (
              <>
                <span className="animate-spin w-3 h-3 border border-t-transparent border-white rounded-full" />
                Generating…
              </>
            ) : (
              <>⚡ Regenerate</>
            )}
          </button>
        </div>
      </div>

      {/* History panel */}
      {showHistory && data?.history && data.history.length > 0 && (
        <div className="bg-slate-50 dark:bg-[#111827] border border-slate-200 dark:border-[#1e2535] rounded-xl p-4">
          <p className="text-xs font-semibold text-slate-600 dark:text-gray-400 uppercase tracking-wider mb-3">Past Weeks</p>
          <div className="space-y-2">
            {data.history.map((h) => (
              <div key={h.id} className="flex items-start gap-3 py-2 border-b border-slate-200 dark:border-[#1e2535] last:border-0">
                <span className="text-xs text-slate-500 dark:text-gray-500 shrink-0 w-24">{h.week_start}</span>
                <div className="flex-1 flex flex-wrap gap-1">
                  {(h.themes || []).map((t, i) => (
                    <span key={i} className="text-xs text-slate-600 dark:text-gray-400 bg-slate-100 dark:bg-[#1a1f2e] px-2 py-0.5 rounded">
                      {t.title}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main content */}
      {loading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-14 bg-slate-100 dark:bg-[#1a1f2e] rounded-xl animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="p-6 bg-slate-50 dark:bg-[#111827] border border-slate-200 dark:border-[#1e2535] rounded-xl text-center">
          <p className="text-slate-600 dark:text-gray-400 text-sm mb-3">{error}</p>
          <p className="text-gray-600 text-xs mb-4">
            Themes are synthesized from company intel and analyst summary caches.
            Make sure those have been populated first (visit Companies and Analysts tabs).
          </p>
          <button
            onClick={() => loadThemes(true)}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 hover:bg-blue-500 text-slate-900 dark:text-white"
          >
            Try Generating Now
          </button>
        </div>
      ) : !data?.themes?.length ? (
        <div className="p-8 text-center">
          <div className="text-4xl mb-3">🔍</div>
          <p className="text-slate-600 dark:text-gray-400 text-sm">No themes available yet.</p>
          <button
            onClick={() => loadThemes(true)}
            className="mt-3 px-4 py-2 text-sm rounded-lg bg-blue-600 hover:bg-blue-500 text-slate-900 dark:text-white"
          >
            Generate Themes
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {data.themes.map((t, i) => (
            <ThemeCard key={i} theme={t} rank={i} />
          ))}
        </div>
      )}
    </div>
  );
}
