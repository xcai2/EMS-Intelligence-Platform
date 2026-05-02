'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  DollarSign,
  TrendingUp,
  Building2,
  Cpu,
  RefreshCw,
  Server,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
  Legend,
  LineChart,
  Line,
} from 'recharts';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

interface Big5Company {
  name: string;
  ticker: string;
  capex_2026_billions?: number | null;
  capex_2025_billions?: number | null;
  yoy_growth_pct?: number | null;
  ai_focus_areas?: string[];
  key_metrics?: Record<string, number> | null;
  recent_announcements?: string[];
  color: string;
}

interface StargateProject {
  total_investment_billions?: number | null;
  timeline?: string;
  partners?: string[];
  initial_deployment_billions?: number | null;
  planned_capacity_gw?: number | null;
  locations?: string[];
}

interface Big5Data {
  last_updated?: string | null;
  source?: string;
  total_2026_capex_billions?: number | null;
  companies: Big5Company[];
  stargate_project?: StargateProject | null;
}

interface HyperscalerFiscalYear {
  revenue?: number;
  operating_income?: number;
  net_income?: number;
  operating_margin?: number;
  capex?: number;
}

interface HyperscalerCompanyFinancials {
  company: string;
  ticker: string;
  color: string;
  fiscal_years: Record<string, HyperscalerFiscalYear>;
  source: string;
  fetched_at: string;
}

interface HyperscalerFinancialsData {
  companies: HyperscalerCompanyFinancials[];
  fetched_at: string;
  source: string;
  errors: Array<{ company: string; error: string }> | null;
}

function formatAISubdomainLabel(area: string): string {
  const raw = area.trim();
  if (!raw) return "AI (General)";

  const noLeadingAI = raw.replace(/^ai[\s/-]+/i, "");
  const noTrailingAI = noLeadingAI.replace(/[\s/-]+ai$/i, "");

  const aiParenMatch = noTrailingAI.match(/^(.*)\(ai\)\s*$/i);
  if (aiParenMatch && aiParenMatch[1]?.trim()) {
    const sub = aiParenMatch[1].trim();
    const titledSub = sub
      .split(" ")
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
    return `AI (${titledSub})`;
  }

  const leadingStyleMatch = noTrailingAI.match(/^ai\s*\((.+)\)$/i);
  if (leadingStyleMatch?.[1]) {
    const sub = leadingStyleMatch[1].trim();
    return `AI (${sub})`;
  }

  const titled = noTrailingAI
    .split(" ")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

  return `AI (${titled})`;
}

const REFRESH_STATUS_KEY = 'hyperscaler_last_refresh_status';

function loadPersistedStatus(): string | null {
  try {
    const raw = localStorage.getItem(REFRESH_STATUS_KEY);
    if (!raw) return null;
    const { date, message } = JSON.parse(raw);
    return `${date} — ${message}`;
  } catch {
    return null;
  }
}

function savePersistedStatus(message: string) {
  const date = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  localStorage.setItem(REFRESH_STATUS_KEY, JSON.stringify({ date, message }));
}

const REFRESH_STEPS = [
  'Connecting to Gemini...',
  'Searching latest news...',
  'Fetching CapEx data...',
  'Analyzing results...',
  'Almost there...',
];

export default function HyperscalerPageFeature() {
  const [data, setData] = useState<Big5Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshStatus, setRefreshStatus] = useState<string | null>(loadPersistedStatus);
  const [refreshStep, setRefreshStep] = useState<string | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<Big5Company | null>(null);
  const [detailExpanded, setDetailExpanded] = useState(true);
  const [historicalData, setHistoricalData] = useState<HyperscalerFinancialsData | null>(null);
  const [historicalLoading, setHistoricalLoading] = useState(true);

  useEffect(() => {
    fetchData();
    fetchHistoricalData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/api/intelligence/big5-capex`);
      if (res.ok) {
        const json = await res.json();
        setData(json);
        if (json.companies && json.companies.length > 0) setSelectedCompany(json.companies[0]);
      }
    } catch (err) {
      console.error('Failed to fetch Big 5 data:', err);
    } finally {
      setLoading(false);
    }
  };

  const refreshGuidance = async () => {
    setRefreshing(true);
    setRefreshStatus(null);
    setRefreshStep(REFRESH_STEPS[0]);

    let stepIndex = 0;
    const stepInterval = setInterval(() => {
      stepIndex = Math.min(stepIndex + 1, REFRESH_STEPS.length - 1);
      setRefreshStep(REFRESH_STEPS[stepIndex]);
    }, 3000);

    try {
      const prevCompanies = data?.companies ?? [];
      const res = await fetch(`${API_URL}/api/intelligence/hyperscaler/guidance/cache`, { method: 'DELETE' });
      clearInterval(stepInterval);
      setRefreshStep(null);
      if (!res.ok) { setRefreshStatus('Failed to refresh data.'); return; }
      const json: Big5Data = await res.json();
      const changes: string[] = [];
      json.companies?.forEach((newC) => {
        const old = prevCompanies.find(o => o.ticker === newC.ticker);
        if (!old) return;
        if (old.capex_2026_billions !== newC.capex_2026_billions) {
          const oldVal = old.capex_2026_billions != null ? `$${old.capex_2026_billions}B` : '—';
          const newVal = newC.capex_2026_billions != null ? `$${newC.capex_2026_billions}B` : '—';
          changes.push(`${newC.name}: ${oldVal} → ${newVal}`);
        }
      });
      setData(json);
      if (json.companies && json.companies.length > 0) setSelectedCompany(json.companies[0]);
      const message = changes.length > 0 ? `Updated: ${changes.join(' | ')}` : 'No changes — data is current.';
      setRefreshStatus(message);
      savePersistedStatus(message);
    } catch (err) {
      clearInterval(stepInterval);
      setRefreshStep(null);
      setRefreshStatus('Error refreshing guidance data.');
    } finally {
      setRefreshing(false);
    }
  };

  const fetchHistoricalData = async () => {
    try {
      setHistoricalLoading(true);
      const res = await fetch(`${API_URL}/api/intelligence/hyperscaler/all/financials`);
      if (res.ok) setHistoricalData(await res.json());
    } catch (err) {
      console.error('Failed to fetch hyperscaler historical data:', err);
    } finally {
      setHistoricalLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6 flex items-center justify-center">
        <div className="text-slate-500">Loading AI investment data...</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6 flex items-center justify-center">
        <div className="text-red-500">Failed to load data</div>
      </div>
    );
  }

  const chartData = data.companies.map((c) => ({
    name: c.name.split(' ')[0],
    capex_2026: c.capex_2026_billions,
    capex_2025: c.capex_2025_billions,
    growth: c.yoy_growth_pct,
    color: c.color,
  }));

  const pieData = data.companies.map((c) => ({
    name: c.name.split(' ')[0],
    value: c.capex_2026_billions,
    color: c.color,
  }));

  const totalCapex2026 = data.companies.reduce((sum, c) => sum + (c.capex_2026_billions ?? 0), 0);
  const totalCapex2025 = data.companies.reduce((sum, c) => sum + (c.capex_2025_billions ?? 0), 0);
  const withGrowth = data.companies.filter(c => c.yoy_growth_pct != null);
  const avgGrowth = withGrowth.length > 0
    ? Math.round(withGrowth.reduce((sum, c) => sum + (c.yoy_growth_pct ?? 0), 0) / withGrowth.length)
    : null;
  const highestGrowthCompany = withGrowth.length > 0
    ? withGrowth.reduce((best, c) => (c.yoy_growth_pct ?? 0) > (best.yoy_growth_pct ?? 0) ? c : best)
    : null;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 p-4 dark:from-slate-950 dark:via-slate-950 dark:to-slate-950">
      {/* Header */}
      <div className="mb-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-3">
              <div className="bg-gradient-to-br from-orange-500 to-red-600 p-1.5 rounded-xl">
                <DollarSign className="h-5 w-5 text-white" />
              </div>
              Hyperscaler CapEx
            </h1>
            <p className="text-slate-500 mt-0.5 text-sm">
              2025 Actual vs 2026 Outlook · Capital Expenditure
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-2">
              {refreshStep && (
                <span className="text-xs text-blue-500 animate-pulse">{refreshStep}</span>
              )}
              {!refreshStep && data.last_updated && (
                <span className="text-xs text-slate-400">
                  Updated: {new Date(data.last_updated + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </span>
              )}
              <button
                onClick={refreshGuidance}
                disabled={refreshing}
                title={refreshing ? 'Fetching latest...' : 'Refresh Guidance'}
                aria-label="Refresh Guidance"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-500 transition hover:border-slate-400 hover:bg-slate-50 hover:text-blue-600 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              </button>
            </div>
            {refreshStatus && (
              <p className={`text-xs ${refreshStatus.startsWith('Updated') ? 'text-green-600' : 'text-slate-500'}`}>
                {refreshStatus}
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-5">
      <Card className="order-1 border-0 shadow-xl dark:bg-slate-900 dark:text-slate-100">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-blue-500" />
            AI Investment Details
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="grid grid-cols-1 gap-4">
            <div>
              <div className="grid grid-cols-5 gap-2 mb-3">
                {data.companies.map((company) => (
                  <button
                    key={company.ticker}
                    onClick={() => setSelectedCompany(company)}
                    className={`text-left p-2 rounded-xl border-2 transition-all ${
                      selectedCompany?.ticker === company.ticker
                        ? 'border-blue-500 bg-blue-50 shadow-md dark:bg-blue-950/40'
                        : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-slate-600'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-1">
                      <div
                        className="w-5 h-5 rounded flex items-center justify-center text-white text-[10px] font-bold flex-shrink-0"
                        style={{ backgroundColor: company.color }}
                      >
                        {company.name.charAt(0)}
                      </div>
                      <span className="text-xs font-semibold text-slate-900 dark:text-slate-100 truncate">{company.name.split(' ')[0]}</span>
                      <span className="text-[10px] text-slate-400 flex-shrink-0">{company.ticker}</span>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-sm font-bold" style={{ color: company.color }}>
                        {company.capex_2026_billions != null ? `$${company.capex_2026_billions}B` : '—'}
                      </span>
                      {company.yoy_growth_pct != null && (
                        <span className="text-[10px] text-green-600">+{company.yoy_growth_pct}%</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>

              {selectedCompany && (
                <div className="flex justify-end mb-1">
                  <button
                    onClick={() => setDetailExpanded(v => !v)}
                    className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
                  >
                    {detailExpanded ? '▲ Collapse' : '▼ Expand details'}
                  </button>
                </div>
              )}

              {selectedCompany && detailExpanded && (
                <div className="rounded-xl border border-slate-200 p-3 bg-white dark:border-slate-700 dark:bg-slate-900">
                  <h3 className="mb-3 flex items-center gap-2 font-semibold text-slate-900 dark:text-slate-100">
                    <div
                      className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-sm font-bold"
                      style={{ backgroundColor: selectedCompany.color }}
                    >
                      {selectedCompany.name.charAt(0)}
                    </div>
                    {selectedCompany.name}
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <h4 className="mb-3 font-semibold text-slate-700 dark:text-slate-200">Key Metrics</h4>
                      {(() => {
                        const yfCompany = historicalData?.companies.find(c => c.ticker === selectedCompany.ticker);
                        const fy2025 = yfCompany?.fiscal_years?.['2025'];
                        const fy2024 = yfCompany?.fiscal_years?.['2024'];
                        return (
                          <div className="space-y-2">
                            <div className="flex justify-between rounded-lg bg-amber-50 p-2 text-sm dark:bg-amber-900/20">
                              <span className="text-slate-600 dark:text-slate-300">2026 CapEx <span className="text-[10px] text-slate-400">(Gemini)</span></span>
                              <span className="font-bold text-amber-700 dark:text-amber-400">
                                {selectedCompany.capex_2026_billions != null ? `$${selectedCompany.capex_2026_billions}B` : '—'}
                              </span>
                            </div>
                            <div className="flex justify-between rounded-lg bg-slate-50 p-2 text-sm dark:bg-slate-800/80">
                              <span className="text-slate-600 dark:text-slate-300">2025 CapEx <span className="text-[10px] text-slate-400">(yfinance)</span></span>
                              <span className="font-bold text-slate-900 dark:text-slate-100">
                                {fy2025?.capex != null ? `$${fy2025.capex}B` : selectedCompany.capex_2025_billions != null ? `$${selectedCompany.capex_2025_billions}B` : '—'}
                              </span>
                            </div>
                            <div className="flex justify-between rounded-lg bg-slate-50 p-2 text-sm dark:bg-slate-800/80">
                              <span className="text-slate-600 dark:text-slate-300">2024 CapEx <span className="text-[10px] text-slate-400">(yfinance)</span></span>
                              <span className="font-bold text-slate-900 dark:text-slate-100">
                                {fy2024?.capex != null ? `$${fy2024.capex}B` : '—'}
                              </span>
                            </div>
                            <div className="flex justify-between rounded-lg bg-green-50 p-2 text-sm dark:bg-emerald-900/35">
                              <span className="text-slate-600 dark:text-slate-200">YoY Growth</span>
                              <span className="font-bold text-green-600">
                                {selectedCompany.yoy_growth_pct != null ? `+${selectedCompany.yoy_growth_pct}%` : '—'}
                              </span>
                            </div>
                            {fy2025?.revenue != null && (
                              <div className="flex justify-between rounded-lg bg-slate-50 p-2 text-sm dark:bg-slate-800/80">
                                <span className="text-slate-600 dark:text-slate-300">2025 Revenue <span className="text-[10px] text-slate-400">(yfinance)</span></span>
                                <span className="font-bold text-slate-900 dark:text-slate-100">${fy2025.revenue}B</span>
                              </div>
                            )}
                            {fy2025?.operating_margin != null && (
                              <div className="flex justify-between rounded-lg bg-slate-50 p-2 text-sm dark:bg-slate-800/80">
                                <span className="text-slate-600 dark:text-slate-300">2025 Op. Margin <span className="text-[10px] text-slate-400">(yfinance)</span></span>
                                <span className="font-bold text-slate-900 dark:text-slate-100">{fy2025.operating_margin}%</span>
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>

                    <div>
                      <h4 className="mb-3 font-semibold text-slate-700 dark:text-slate-200">AI Focus Subdomains</h4>
                      <div className="space-y-2">
                        {(selectedCompany.ai_focus_areas ?? []).map((area, idx) => (
                          <div key={idx} className="flex items-center gap-2 rounded-lg bg-purple-50 p-2 dark:bg-violet-900/35">
                            <Cpu className="h-4 w-4 text-purple-600 dark:text-violet-300" />
                            <span className="text-slate-700 dark:text-slate-100">{formatAISubdomainLabel(area)}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <h4 className="mb-3 font-semibold text-slate-700 dark:text-slate-200">Recent Announcements</h4>
                      <div className="space-y-2">
                        {(selectedCompany.recent_announcements ?? []).map((announcement, idx) => (
                          <div key={idx} className="rounded-lg bg-blue-50 p-3 dark:bg-sky-900/30">
                            <p className="text-sm text-slate-700 dark:text-slate-100">{announcement}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

          </div>
        </CardContent>
      </Card>

      {/* Top Analytics Row: KPI + Charts */}
      <div className="order-2 grid grid-cols-1 xl:grid-cols-12 gap-4">
        <div className="xl:col-span-3 grid grid-cols-2 grid-rows-2 gap-2">

          {/* A: Total 2026 CapEx — Gemini */}
          <Card className="border-0 shadow-md dark:border dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="p-3 flex flex-col justify-between h-full">
              <div className="flex items-center gap-1.5">
                <DollarSign className="h-3 w-3 text-slate-400" />
                <p className="text-[9px] text-slate-400 uppercase tracking-wide">Total 2026 CapEx</p>
              </div>
              <p className="text-xl font-bold text-slate-900 dark:text-slate-100 my-1">
                {totalCapex2026 > 0 ? `$${totalCapex2026.toFixed(0)}B` : '—'}
              </p>
              <p className="text-[9px] text-slate-400">Big 5 combined · Gemini</p>
            </CardContent>
          </Card>

          {/* C: Total 2025 CapEx — yfinance */}
          <Card className="border-0 shadow-md dark:border dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="p-3 flex flex-col justify-between h-full">
              <div className="flex items-center gap-1.5">
                <Server className="h-3 w-3 text-slate-400" />
                <p className="text-[9px] text-slate-400 uppercase tracking-wide">Total 2025 CapEx</p>
              </div>
              <p className="text-xl font-bold text-slate-900 dark:text-slate-100 my-1">
                {totalCapex2025 > 0 ? `$${totalCapex2025.toFixed(0)}B` : '—'}
              </p>
              <p className="text-[9px] text-slate-400">Big 5 actual · yfinance</p>
            </CardContent>
          </Card>

          {/* B: Avg YoY Growth — calculated */}
          <Card className="border-0 shadow-md dark:border dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="p-3 flex flex-col justify-between h-full">
              <div className="flex items-center gap-1.5">
                <TrendingUp className="h-3 w-3 text-slate-400" />
                <p className="text-[9px] text-slate-400 uppercase tracking-wide">Avg YoY Growth</p>
              </div>
              <p className="text-xl font-bold text-slate-900 dark:text-slate-100 my-1">
                {avgGrowth != null ? `+${avgGrowth}%` : '—'}
              </p>
              <p className="text-[9px] text-slate-400">2025 actual → 2026 outlook</p>
            </CardContent>
          </Card>

          {/* H: Highest Growth — calculated */}
          <Card className="border-0 shadow-md dark:border dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="p-3 flex flex-col justify-between h-full">
              <div className="flex items-center gap-1.5">
                <Cpu className="h-3 w-3 text-slate-400" />
                <p className="text-[9px] text-slate-400 uppercase tracking-wide">Highest Growth</p>
              </div>
              <p className="text-xl font-bold text-slate-900 dark:text-slate-100 my-1">
                {highestGrowthCompany ? `+${Math.round(highestGrowthCompany.yoy_growth_pct ?? 0)}%` : '—'}
              </p>
              <p className="text-[9px] text-slate-400">
                {highestGrowthCompany ? `${highestGrowthCompany.name.split(' ')[0]} · 2025→2026` : '—'}
              </p>
            </CardContent>
          </Card>

        </div>

        <div className="xl:col-span-5">
          <Card className="border-0 shadow-xl dark:border dark:border-slate-800 dark:bg-slate-900">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-blue-600" />
                2025 vs 2026 CapEx Comparison
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                  <XAxis type="number" unit="B" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value) => [`$${value}B`, '']}
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 40px rgba(0,0,0,0.1)' }}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 11 }}
                    content={() => (
                      <div className="flex gap-4 justify-center text-xs text-slate-600">
                        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: '#94A3B8' }} />2025 Actual (yfinance)</span>
                        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: '#F59E0B' }} />2026 Outlook (Gemini)</span>
                      </div>
                    )}
                  />
                  <Bar dataKey="capex_2025" name="2025 Actual" fill="#94A3B8" radius={[0, 4, 4, 0]} />
                  <Bar dataKey="capex_2026" name="2026 Outlook" fill="#F59E0B" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <p className="text-xs text-slate-400 mt-2">
                2025 actual from SEC filings (yfinance) · 2026 outlook from latest earnings guidance (Gemini)
                {data.last_updated && ` · Updated ${data.last_updated}`}
              </p>
            </CardContent>
          </Card>
        </div>

        <div className="xl:col-span-4 xl:col-start-9">
          <Card className="border-0 shadow-xl dark:border dark:border-slate-800 dark:bg-slate-900">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="h-5 w-5 text-purple-600" />
                2026 CapEx Distribution
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart margin={{ top: 8, right: 28, left: 28, bottom: 8 }}>
                  <Pie
                    data={pieData}
                    cx="54%"
                    cy="50%"
                    outerRadius={88}
                    innerRadius={46}
                    paddingAngle={2}
                    dataKey="value"
                    label={({ name, percent = 0 }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    labelLine={{ stroke: '#94a3b8', strokeWidth: 1 }}
                    style={{ fontSize: 10 }}
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => [`$${value}B`, 'CapEx']} />
                </PieChart>
              </ResponsiveContainer>
              <p className="text-xs text-slate-400 mt-2">Share of 2026 CapEx by company · Source: Gemini</p>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Historical CapEx Trend (live from yfinance) */}
      <Card className="order-3 border-0 shadow-xl dark:border dark:border-slate-800 dark:bg-slate-900">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-green-600" />
              Historical CapEx Trend
            </CardTitle>
            <div className="flex items-center gap-2">
              <span className="text-xs px-2 py-1 rounded-full bg-green-50 text-green-700 border border-green-200">
                Source: yfinance (live)
              </span>
              <button
                onClick={fetchHistoricalData}
                className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all shadow-sm text-xs"
              >
                <RefreshCw className="h-3 w-3" />
                Refresh
              </button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {historicalLoading ? (
            <div className="h-64 flex items-center justify-center text-slate-400 text-sm">
              Loading historical data from yfinance...
            </div>
          ) : historicalData && historicalData.companies.length > 0 ? (() => {
            const allYears = Array.from(
              new Set(historicalData.companies.flatMap(c => Object.keys(c.fiscal_years)))
            ).sort();

            const lineData = allYears.map(year => {
              const point: Record<string, string | number> = { year };
              historicalData.companies.forEach(c => {
                const capex = c.fiscal_years[year]?.capex;
                if (capex != null) point[c.company] = capex;
              });
              return point;
            });

            return (
              <div className="space-y-4">
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={lineData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                    <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                    <YAxis
                      tickFormatter={v => `$${v}B`}
                      tick={{ fontSize: 11 }}
                      label={{ value: 'USD Billions', angle: -90, position: 'insideLeft', style: { fontSize: 10 } }}
                    />
                    <Tooltip formatter={(v, name) => [v != null ? `$${Number(v).toFixed(2)}B` : '—', name]} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    {historicalData.companies.map(c => (
                      <Line
                        key={c.ticker}
                        type="monotone"
                        dataKey={c.company}
                        stroke={c.color}
                        strokeWidth={2}
                        dot={{ r: 4 }}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>

                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 pt-2 border-t border-slate-100">
                  {historicalData.companies.map(c => {
                    const years = Object.keys(c.fiscal_years).sort();
                    const latestYear = years[years.length - 1];
                    const latestCapex = c.fiscal_years[latestYear]?.capex;
                    const prevCapex = years.length > 1
                      ? c.fiscal_years[years[years.length - 2]]?.capex
                      : undefined;
                    const yoy = latestCapex != null && prevCapex != null
                      ? Math.round(((latestCapex - prevCapex) / prevCapex) * 100)
                      : null;
                    return (
                      <div key={c.ticker} className="text-center p-3 rounded-xl bg-slate-50 dark:bg-slate-800">
                        <div
                          className="w-7 h-7 rounded-md flex items-center justify-center text-white text-xs font-bold mx-auto mb-1.5"
                          style={{ backgroundColor: c.color }}
                        >
                          {c.company.charAt(0)}
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400">{c.company}</p>
                        <p className="font-bold text-slate-900 dark:text-slate-100 text-sm">
                          {latestCapex != null ? `$${latestCapex}B` : '—'}
                        </p>
                        <p className="text-xs text-slate-400">{latestYear}</p>
                        {yoy != null && (
                          <p className={`text-xs font-medium ${yoy >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                            {yoy >= 0 ? '+' : ''}{yoy}% YoY
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>

                {historicalData.errors && historicalData.errors.length > 0 && (
                  <p className="text-xs text-amber-600 mt-1">
                    Failed to load: {historicalData.errors.map(e => e.company).join(', ')}
                  </p>
                )}
              </div>
            );
          })() : (
            <div className="h-64 flex items-center justify-center text-slate-400 text-sm">
              No historical data available
            </div>
          )}
        </CardContent>
      </Card>

      </div>
    </div>
  );
}
