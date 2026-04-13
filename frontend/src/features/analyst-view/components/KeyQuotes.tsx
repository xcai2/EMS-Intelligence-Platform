"use client";

import React, { useEffect, useState, useCallback } from "react";

interface QuoteItem {
  id?: number;
  company: string;
  ticker: string;
  analyst_name: string;
  question: string;
  management_response: string;
  theme: string;
  strategic_implication: string;
  earnings_date: string;
  source_url: string;
  created_at: string;
}

interface QuotesResponse {
  quotes: QuoteItem[];
  total: number;
}

const THEMES = [
  "All",
  "CapEx & Investment",
  "AI/Data Center",
  "Geographic Expansion",
  "Margins & Profitability",
  "Customer Concentration",
  "Supply Chain",
];

const TICKERS = ["All", "FLEX", "JBL", "CLS", "BHE", "SANM", "PLXS", "AMZN", "MSFT", "GOOGL", "META", "AAPL", "ORCL"];

const THEME_COLORS: Record<string, string> = {
  "CapEx & Investment": "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700",
  "AI/Data Center": "bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 border-purple-300 dark:border-purple-700",
  "Geographic Expansion": "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700",
  "Margins & Profitability": "bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700",
  "Customer Concentration": "bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-700",
  "Supply Chain": "bg-cyan-100 dark:bg-cyan-900/40 text-cyan-700 dark:text-cyan-300 border-cyan-300 dark:border-cyan-700",
};

export default function KeyQuotes() {
  const [quotes, setQuotes] = useState<QuoteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [extracting, setExtracting] = useState<string | null>(null);
  const [selectedTheme, setSelectedTheme] = useState("All");
  const [selectedTicker, setSelectedTicker] = useState("All");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchQuotes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ days: "90" });
      if (selectedTicker !== "All") params.set("company", selectedTicker);
      if (selectedTheme !== "All") params.set("theme", selectedTheme);
      const res = await fetch(`/api/analyst-view/key-quotes?${params}`);
      const data: QuotesResponse = await res.json();
      setQuotes(data.quotes || []);
    } catch (e) {
      setError("Failed to load key quotes.");
    } finally {
      setLoading(false);
    }
  }, [selectedTheme, selectedTicker]);

  useEffect(() => {
    fetchQuotes();
  }, [fetchQuotes]);

  const handleExtract = async (ticker: string) => {
    setExtracting(ticker);
    try {
      const res = await fetch("/api/analyst-view/extract-quotes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
      });
      const data = await res.json();
      if (data.quotes?.length) {
        setQuotes((prev) => [...data.quotes, ...prev]);
      }
    } catch {
      // silent
    } finally {
      setExtracting(null);
    }
  };

  const EMS_TICKERS = ["FLEX", "JBL", "CLS", "BHE", "SANM", "PLXS", "AMZN", "MSFT", "GOOGL", "META"];

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-2">
          {THEMES.map((t) => (
            <button
              key={t}
              onClick={() => setSelectedTheme(t)}
              className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                selectedTheme === t
                  ? "bg-blue-600 border-blue-500 text-slate-900 dark:text-white"
                  : "bg-slate-100 dark:bg-[#1a1f2e] border-slate-300 dark:border-[#2a3045] text-slate-600 dark:text-gray-400 hover:border-slate-400 dark:hover:border-gray-500"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <select
          value={selectedTicker}
          onChange={(e) => setSelectedTicker(e.target.value)}
          className="ml-auto px-3 py-1.5 text-xs bg-slate-100 dark:bg-[#1a1f2e] border border-slate-300 dark:border-[#2a3045] rounded text-slate-700 dark:text-gray-300"
        >
          {TICKERS.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {/* Extract from ChromaDB buttons */}
      <div className="flex flex-wrap gap-2 p-3 bg-slate-50 dark:bg-[#111827] rounded-lg border border-slate-200 dark:border-[#1e2535]">
        <span className="text-xs text-slate-500 dark:text-gray-500 self-center mr-2">Extract from SEC filings:</span>
        {EMS_TICKERS.map((t) => (
          <button
            key={t}
            onClick={() => handleExtract(t)}
            disabled={extracting === t}
            className="px-3 py-1 text-xs rounded border border-slate-300 dark:border-[#2a3045] bg-slate-100 dark:bg-[#1a1f2e] text-slate-700 dark:text-gray-300 hover:border-blue-500 hover:text-blue-600 dark:hover:text-blue-400 disabled:opacity-50 disabled:cursor-wait transition-colors"
          >
            {extracting === t ? (
              <span className="flex items-center gap-1">
                <span className="animate-spin inline-block w-3 h-3 border border-t-transparent border-blue-400 rounded-full" />
                {t}
              </span>
            ) : t}
          </button>
        ))}
      </div>

      {/* Quote cards */}
      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 bg-slate-100 dark:bg-[#1a1f2e] rounded-lg animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="p-4 bg-red-100 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300 text-sm">{error}</div>
      ) : quotes.length === 0 ? (
        <div className="p-8 text-center">
          <div className="text-4xl mb-3">💬</div>
          <p className="text-slate-600 dark:text-gray-400 text-sm">No strategic insights yet. Use the Extract buttons above to pull key statements from SEC filings in ChromaDB.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {quotes.map((q, i) => (
            <div
              key={q.id ?? i}
              className="bg-slate-50 dark:bg-[#111827] border border-slate-200 dark:border-[#1e2535] rounded-lg overflow-hidden hover:border-slate-300 dark:hover:border-[#2a3045] transition-colors"
            >
              {/* Header */}
              <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-200 dark:border-[#1e2535]">
                <span className="font-mono text-xs font-bold text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/30 px-2 py-0.5 rounded">
                  {q.ticker}
                </span>
                <span className={`text-xs px-2 py-0.5 rounded border ${THEME_COLORS[q.theme] || "bg-slate-100 dark:bg-gray-800 text-slate-600 dark:text-gray-400 border-slate-200 dark:border-gray-700"}`}>
                  {q.theme}
                </span>
                <span className="text-xs text-slate-500 dark:text-gray-500 ml-auto">{q.earnings_date || q.created_at?.slice(0, 10)}</span>
              </div>

              {/* Topic */}
              <div className="px-4 pt-3 pb-1">
                <p className="text-sm text-slate-800 dark:text-gray-200 leading-relaxed font-medium">{q.question}</p>
              </div>

              {/* Key statement - collapsible */}
              <div className="px-4 pb-3">
                <button
                  className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 mt-2 mb-1"
                  onClick={() => setExpanded(expanded === i ? null : i)}
                >
                  {expanded === i ? "▲ Hide detail" : "▼ Key statement"}
                </button>
                {expanded === i && (
                  <p className="text-sm text-slate-700 dark:text-gray-300 leading-relaxed italic border-l-2 border-blue-300 dark:border-blue-700 pl-3 mt-1">
                    {q.management_response}
                  </p>
                )}
              </div>

              {/* Strategic implication */}
              <div className="px-4 pb-3">
                <div className="flex items-start gap-2 bg-slate-50 dark:bg-[#0d1117] rounded p-2">
                  <span className="text-yellow-600 dark:text-yellow-400 text-xs font-bold shrink-0">⚡ Flex Implication</span>
                  <p className="text-xs text-slate-700 dark:text-gray-300">{q.strategic_implication}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
