"use client";

import React, { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
} from "recharts";

interface TimelinePoint {
  quarter: string;
  consensus_score: number;
  label: string;
}

interface TimelineResponse {
  ticker: string;
  company: string;
  timeline: TimelinePoint[];
  current_consensus: string;
  current_pt: string;
}

const TICKERS = ["FLEX", "JBL", "CLS", "BHE", "SANM", "PLXS"];

const TICKER_COLORS: Record<string, string> = {
  FLEX: "#3b82f6",
  JBL: "#10b981",
  CLS: "#f59e0b",
  BHE: "#ef4444",
  SANM: "#8b5cf6",
  PLXS: "#06b6d4",
};

const CONSENSUS_CONFIG: Record<string, { color: string; bg: string }> = {
  Bullish: { color: "text-green-400", bg: "bg-green-900/30" },
  Mixed:   { color: "text-yellow-400", bg: "bg-yellow-900/30" },
  Neutral: { color: "text-gray-400",  bg: "bg-gray-800/50" },
  Bearish: { color: "text-red-400",   bg: "bg-red-900/30" },
  Unknown: { color: "text-gray-500",  bg: "bg-gray-800/30" },
};

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#1a1f2e] border border-[#2a3045] rounded-lg p-3 shadow-xl">
      <p className="text-xs text-gray-400 mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2 text-xs">
          <span style={{ color: p.color }}>●</span>
          <span className="text-gray-300">{p.name}:</span>
          <span className="font-bold" style={{ color: p.color }}>
            {p.value > 0.5 ? "Bullish" : p.value > -0.2 ? "Neutral" : "Bearish"}
            {" "}({p.value > 0 ? "+" : ""}{p.value.toFixed(2)})
          </span>
        </div>
      ))}
    </div>
  );
}

export default function SentimentTimeline() {
  const [selected, setSelected] = useState<string[]>(["FLEX", "JBL", "CLS"]);
  const [data, setData] = useState<Record<string, TimelineResponse>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAll = async () => {
      setLoading(true);
      setError(null);
      try {
        const results = await Promise.all(
          TICKERS.map(async (t) => {
            const res = await fetch(`/api/analyst-view/sentiment-timeline?ticker=${t}&quarters=8`);
            const json: TimelineResponse = await res.json();
            return [t, json] as const;
          })
        );
        setData(Object.fromEntries(results));
      } catch {
        setError("Failed to load sentiment timeline.");
      } finally {
        setLoading(false);
      }
    };
    fetchAll();
  }, []);

  // Merge all timelines into a single series indexed by quarter
  const allQuarters = data[TICKERS[0]]?.timeline?.map((p) => p.quarter) ?? [];
  const chartData = allQuarters.map((q) => {
    const row: Record<string, string | number> = { quarter: q };
    for (const t of selected) {
      const point = data[t]?.timeline?.find((p) => p.quarter === q);
      if (point) row[t] = point.consensus_score;
    }
    return row;
  });

  const toggleTicker = (t: string) => {
    setSelected((prev) =>
      prev.includes(t) ? (prev.length > 1 ? prev.filter((x) => x !== t) : prev) : [...prev, t]
    );
  };

  return (
    <div className="space-y-4">
      {/* Ticker toggles */}
      <div className="flex flex-wrap gap-2">
        {TICKERS.map((t) => {
          const active = selected.includes(t);
          const consensus = data[t]?.current_consensus ?? "Unknown";
          const cfg = CONSENSUS_CONFIG[consensus] ?? CONSENSUS_CONFIG.Unknown;
          return (
            <button
              key={t}
              onClick={() => toggleTicker(t)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs transition-all ${
                active
                  ? "border-transparent text-white"
                  : "border-[#2a3045] bg-[#1a1f2e] text-gray-500"
              }`}
              style={active ? { backgroundColor: TICKER_COLORS[t] + "33", borderColor: TICKER_COLORS[t] } : {}}
            >
              {active && <span style={{ color: TICKER_COLORS[t] }}>●</span>}
              <span className="font-mono font-bold">{t}</span>
              {active && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${cfg.bg} ${cfg.color}`}>
                  {consensus}
                </span>
              )}
              {active && data[t]?.current_pt !== "—" && (
                <span className="text-gray-400">{data[t]?.current_pt}</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Chart */}
      <div className="bg-[#111827] border border-[#1e2535] rounded-xl p-4">
        {loading ? (
          <div className="h-64 flex items-center justify-center">
            <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
          </div>
        ) : error ? (
          <div className="h-64 flex items-center justify-center text-red-400 text-sm">{error}</div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2535" />
              <XAxis
                dataKey="quarter"
                tick={{ fill: "#6b7280", fontSize: 11 }}
                axisLine={{ stroke: "#1e2535" }}
                tickLine={false}
              />
              <YAxis
                domain={[-1, 1]}
                tick={{ fill: "#6b7280", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => (v > 0.5 ? "Bull" : v > -0.2 ? "Neut" : "Bear")}
                width={38}
              />
              <ReferenceLine y={0.5} stroke="#22c55e" strokeDasharray="4 2" strokeOpacity={0.4}
                label={{ value: "Bullish", fill: "#22c55e", fontSize: 10, position: "insideTopLeft" }} />
              <ReferenceLine y={-0.2} stroke="#ef4444" strokeDasharray="4 2" strokeOpacity={0.4}
                label={{ value: "Bearish", fill: "#ef4444", fontSize: 10, position: "insideBottomLeft" }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend
                formatter={(value) => (
                  <span style={{ color: TICKER_COLORS[value as string], fontSize: 12 }}>{value}</span>
                )}
              />
              {selected.map((t) => (
                <Line
                  key={t}
                  type="monotone"
                  dataKey={t}
                  stroke={TICKER_COLORS[t]}
                  strokeWidth={2}
                  dot={{ r: 3, fill: TICKER_COLORS[t] }}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Summary cards */}
      {!loading && !error && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {selected.map((t) => {
            const d = data[t];
            if (!d) return null;
            const cfg = CONSENSUS_CONFIG[d.current_consensus] ?? CONSENSUS_CONFIG.Unknown;
            const timeline = d.timeline ?? [];
            const trend = timeline.length >= 2
              ? timeline[timeline.length - 1].consensus_score - timeline[0].consensus_score
              : 0;
            return (
              <div key={t} className="bg-[#111827] border border-[#1e2535] rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono font-bold text-sm" style={{ color: TICKER_COLORS[t] }}>{t}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${cfg.bg} ${cfg.color}`}>
                    {d.current_consensus}
                  </span>
                </div>
                <div className="text-xs text-gray-500">{d.company}</div>
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs text-gray-400">PT: {d.current_pt}</span>
                  <span className={`text-xs ml-auto ${trend >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {trend >= 0 ? "↑" : "↓"} {Math.abs(trend).toFixed(2)} 8Q
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
