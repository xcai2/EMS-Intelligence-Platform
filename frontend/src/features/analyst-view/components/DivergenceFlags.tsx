"use client";

import React, { useEffect, useState } from "react";

interface DivergenceFlag {
  analyst: string;
  company: string;
  ticker: string;
  analyst_pt: string;
  consensus_pt: string;
  divergence_pct: number;
  direction: "Bull outlier" | "Bear outlier";
}

interface FlagsResponse {
  flags: DivergenceFlag[];
  total: number;
  cached_at: string;
}

export default function DivergenceFlags() {
  const [flags, setFlags] = useState<DivergenceFlag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cachedAt, setCachedAt] = useState<string>("");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/analyst-view/divergence-flags");
        const data: FlagsResponse = await res.json();
        setFlags(data.flags || []);
        setCachedAt(data.cached_at || "");
      } catch {
        setError("Failed to load divergence flags.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const timeAgo = (iso: string) => {
    if (!iso) return "";
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return "just now";
    if (m < 60) return `${m}m ago`;
    return `${Math.floor(m / 60)}h ago`;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-white">Analyst Price Target Outliers</h3>
          <p className="text-xs text-gray-500 mt-0.5">Analysts with PTs ≥20% above or below consensus</p>
        </div>
        {cachedAt && (
          <span className="text-xs text-gray-600">Updated {timeAgo(cachedAt)}</span>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-20 bg-[#1a1f2e] rounded-lg animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="p-4 bg-red-900/20 border border-red-800 rounded-lg text-red-300 text-sm">{error}</div>
      ) : flags.length === 0 ? (
        <div className="p-8 text-center">
          <div className="text-4xl mb-3">✅</div>
          <p className="text-gray-400 text-sm font-medium">No significant outliers detected</p>
          <p className="text-gray-600 text-xs mt-1">All analyst price targets are within 20% of consensus</p>
        </div>
      ) : (
        <div className="space-y-3">
          {flags.map((f, i) => {
            const isBull = f.direction === "Bull outlier";
            return (
              <div
                key={i}
                className={`rounded-xl border p-4 ${
                  isBull
                    ? "bg-green-900/10 border-green-800/60"
                    : "bg-red-900/10 border-red-800/60"
                }`}
              >
                <div className="flex items-start gap-3">
                  {/* Divergence badge */}
                  <div
                    className={`shrink-0 w-14 h-14 rounded-lg flex flex-col items-center justify-center ${
                      isBull ? "bg-green-900/40" : "bg-red-900/40"
                    }`}
                  >
                    <span className={`text-xl ${isBull ? "text-green-400" : "text-red-400"}`}>
                      {isBull ? "↑" : "↓"}
                    </span>
                    <span className={`text-xs font-bold ${isBull ? "text-green-400" : "text-red-400"}`}>
                      {isBull ? "+" : ""}{f.divergence_pct.toFixed(0)}%
                    </span>
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-sm text-white">{f.analyst}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        isBull
                          ? "bg-green-900/50 text-green-300"
                          : "bg-red-900/50 text-red-300"
                      }`}>
                        {f.direction}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <span className="font-mono text-xs font-bold text-blue-400 bg-blue-900/30 px-1.5 py-0.5 rounded">
                        {f.ticker}
                      </span>
                      <span className="text-xs text-gray-400">{f.company}</span>
                    </div>

                    {/* PT comparison */}
                    <div className="flex items-center gap-4 mt-2">
                      <div className="text-center">
                        <div className={`text-base font-bold ${isBull ? "text-green-400" : "text-red-400"}`}>
                          {f.analyst_pt}
                        </div>
                        <div className="text-[10px] text-gray-500">Analyst PT</div>
                      </div>
                      <div className="text-gray-600 text-sm">vs</div>
                      <div className="text-center">
                        <div className="text-base font-bold text-gray-300">{f.consensus_pt}</div>
                        <div className="text-[10px] text-gray-500">Consensus PT</div>
                      </div>
                    </div>
                  </div>

                  {/* Rank badge */}
                  <div className="shrink-0 text-gray-700 text-xs font-bold">#{i + 1}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Legend */}
      <div className="flex gap-4 pt-2 border-t border-[#1e2535]">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="w-3 h-3 rounded-full bg-green-500/50" />
          Bull outlier: PT ≥20% above consensus
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="w-3 h-3 rounded-full bg-red-500/50" />
          Bear outlier: PT ≥20% below consensus
        </div>
      </div>
    </div>
  );
}
