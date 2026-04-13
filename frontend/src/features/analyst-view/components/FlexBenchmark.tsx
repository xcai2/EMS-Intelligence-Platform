"use client";

import React, { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface PeerData {
  ticker: string;
  company: string;
  consensus: string;
  consensus_score: number;
  price_target: string;
  price_target_val: number | null;
  key_view: string;
  action_count: number;
}

interface BenchmarkResponse {
  peers: PeerData[];
  flex: PeerData | null;
  leader: string;
  cached_at: string;
}

const CONSENSUS_CONFIG: Record<string, { bg: string; text: string; bar: string }> = {
  Bullish: { bg: "bg-green-900/30",  text: "text-green-300",  bar: "#22c55e" },
  Mixed:   { bg: "bg-yellow-900/30", text: "text-yellow-300", bar: "#f59e0b" },
  Neutral: { bg: "bg-gray-800/50",   text: "text-gray-300",   bar: "#6b7280" },
  Bearish: { bg: "bg-red-900/30",    text: "text-red-300",    bar: "#ef4444" },
  Unknown: { bg: "bg-gray-800/30",   text: "text-gray-500",   bar: "#374151" },
};

const TICKER_COLORS: Record<string, string> = {
  FLEX: "#3b82f6",
  JBL:  "#10b981",
  CLS:  "#f59e0b",
  BHE:  "#ef4444",
  SANM: "#8b5cf6",
  PLXS: "#06b6d4",
};

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: PeerData }>;
  label?: string;
}

function CustomTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const cfg = CONSENSUS_CONFIG[d.consensus] ?? CONSENSUS_CONFIG.Unknown;
  return (
    <div className="bg-[#1a1f2e] border border-[#2a3045] rounded-lg p-3 shadow-xl max-w-xs">
      <div className="flex items-center gap-2 mb-2">
        <span className="font-mono font-bold text-sm" style={{ color: TICKER_COLORS[d.ticker] ?? "#fff" }}>
          {d.ticker}
        </span>
        <span className={`text-xs px-1.5 py-0.5 rounded ${cfg.bg} ${cfg.text}`}>{d.consensus}</span>
      </div>
      <p className="text-xs text-gray-400 leading-relaxed">{d.key_view}</p>
      {d.price_target !== "—" && (
        <p className="text-xs text-gray-500 mt-1">PT: {d.price_target}</p>
      )}
    </div>
  );
}

export default function FlexBenchmark() {
  const [data, setData] = useState<BenchmarkResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"consensus" | "pt">("consensus");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/analyst-view/flex-benchmark");
        const json: BenchmarkResponse = await res.json();
        setData(json);
      } catch {
        setError("Failed to load benchmark data.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-64 bg-[#1a1f2e] rounded-xl animate-pulse" />
        <div className="grid grid-cols-3 gap-3">
          {[...Array(6)].map((_, i) => <div key={i} className="h-28 bg-[#1a1f2e] rounded-lg animate-pulse" />)}
        </div>
      </div>
    );
  }

  if (error) {
    return <div className="p-4 bg-red-900/20 border border-red-800 rounded-lg text-red-300 text-sm">{error}</div>;
  }

  if (!data?.peers?.length) {
    return <div className="p-8 text-center text-gray-500 text-sm">No benchmark data available.</div>;
  }

  const flex = data.flex;
  const flexRank = data.peers.findIndex((p) => p.ticker === "FLEX") + 1;
  const isLeader = data.leader === "FLEX";

  // Chart data
  const chartData = view === "consensus"
    ? data.peers.map((p) => ({ ...p, value: p.consensus_score }))
    : data.peers.filter((p) => p.price_target_val !== null).map((p) => ({ ...p, value: p.price_target_val! }));

  return (
    <div className="space-y-5">
      {/* Flex highlight */}
      {flex && (
        <div className={`rounded-xl border p-4 ${isLeader ? "border-blue-600 bg-blue-900/10" : "border-[#2a3045] bg-[#111827]"}`}>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xl font-bold text-blue-400">FLEX</span>
              {isLeader && (
                <span className="text-xs bg-blue-600 text-white px-2 py-0.5 rounded-full font-medium">
                  #1 Leader
                </span>
              )}
              {!isLeader && (
                <span className="text-xs text-gray-500">Ranked #{flexRank} of {data.peers.length}</span>
              )}
            </div>
            <span className={`text-sm px-2 py-0.5 rounded font-medium ${CONSENSUS_CONFIG[flex.consensus]?.bg} ${CONSENSUS_CONFIG[flex.consensus]?.text}`}>
              {flex.consensus}
            </span>
            {flex.price_target !== "—" && (
              <span className="text-sm text-gray-300">PT: {flex.price_target}</span>
            )}
            <span className="text-xs text-gray-500 ml-auto">{flex.action_count} recent actions</span>
          </div>
          {flex.key_view && (
            <p className="text-sm text-gray-400 mt-2 leading-relaxed italic">{flex.key_view}</p>
          )}
        </div>
      )}

      {/* Chart toggle */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setView("consensus")}
          className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
            view === "consensus"
              ? "bg-blue-600 border-blue-500 text-white"
              : "bg-[#1a1f2e] border-[#2a3045] text-gray-400 hover:text-gray-200"
          }`}
        >
          Consensus Score
        </button>
        <button
          onClick={() => setView("pt")}
          className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
            view === "pt"
              ? "bg-blue-600 border-blue-500 text-white"
              : "bg-[#1a1f2e] border-[#2a3045] text-gray-400 hover:text-gray-200"
          }`}
        >
          Price Targets
        </button>
      </div>

      {/* Bar chart */}
      <div className="bg-[#111827] border border-[#1e2535] rounded-xl p-4">
        <p className="text-xs text-gray-500 mb-3">
          {view === "consensus"
            ? "Analyst consensus score (3=Bullish, 2=Mixed, 1=Neutral, 0=Bearish)"
            : "Consensus price targets (USD)"}
        </p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData} margin={{ top: 0, right: 10, left: 0, bottom: 0 }}>
            <XAxis
              dataKey="ticker"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: "#6b7280", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              domain={view === "consensus" ? [0, 3.5] : ["auto", "auto"]}
              tickFormatter={(v) => view === "pt" ? `$${v}` : v.toString()}
            />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {chartData.map((d) => (
                <Cell
                  key={d.ticker}
                  fill={d.ticker === "FLEX"
                    ? "#3b82f6"
                    : (CONSENSUS_CONFIG[d.consensus]?.bar ?? "#374151")}
                  opacity={d.ticker === "FLEX" ? 1 : 0.7}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Peer cards grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {data.peers.map((p, i) => {
          const cfg = CONSENSUS_CONFIG[p.consensus] ?? CONSENSUS_CONFIG.Unknown;
          const isFlexCard = p.ticker === "FLEX";
          return (
            <div
              key={p.ticker}
              className={`rounded-lg border p-3 ${
                isFlexCard
                  ? "border-blue-700 bg-blue-900/10"
                  : "border-[#1e2535] bg-[#111827]"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span
                  className="font-mono font-bold text-sm"
                  style={{ color: TICKER_COLORS[p.ticker] ?? "#9ca3af" }}
                >
                  {p.ticker}
                </span>
                <span className="text-[10px] text-gray-600">#{i + 1}</span>
              </div>
              <div className="text-[11px] text-gray-500 mb-2 truncate">{p.company}</div>
              <div className={`text-xs px-2 py-0.5 rounded inline-block ${cfg.bg} ${cfg.text}`}>
                {p.consensus}
              </div>
              {p.price_target !== "—" && (
                <div className="text-xs text-gray-400 mt-1.5">PT {p.price_target}</div>
              )}
              {p.action_count > 0 && (
                <div className="text-[10px] text-gray-600 mt-1">{p.action_count} actions</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
