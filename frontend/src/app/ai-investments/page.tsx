'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ChartDescription } from '@/components/ui/chart-description';
import {
  DollarSign,
  TrendingUp,
  Building2,
  Cpu,
  Zap,
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
} from 'recharts';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

interface Big5Company {
  name: string;
  ticker: string;
  capex_2026_billions: number;
  capex_2025_billions: number;
  yoy_growth_pct: number;
  ai_focus_areas: string[];
  key_metrics: Record<string, number>;
  recent_announcements: string[];
  color: string;
}

interface StargateProject {
  total_investment_billions: number;
  timeline: string;
  partners: string[];
  initial_deployment_billions: number;
  planned_capacity_gw: number;
  locations: string[];
}

interface Big5Data {
  last_updated: string;
  source: string;
  total_2026_capex_billions: number;
  companies: Big5Company[];
  stargate_project: StargateProject;
}

function formatAISubdomainLabel(area: string): string {
  const raw = area.trim();
  if (!raw) return "AI (General)";

  // Normalize inputs like "AI compute", "cloud AI", "Compute (AI)" into "AI (Compute)".
  const noLeadingAI = raw.replace(/^ai[\s/-]+/i, "");
  const noTrailingAI = noLeadingAI.replace(/[\s/-]+ai$/i, "");

  // Convert existing "X (AI)" to "AI (X)".
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

  // Keep already-correct style.
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

export default function AIInvestmentsPage() {
  const [data, setData] = useState<Big5Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedCompany, setSelectedCompany] = useState<Big5Company | null>(null);

  useEffect(() => {
    fetchData();
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

  const totalCapex = data.companies.reduce((sum, c) => sum + c.capex_2026_billions, 0);
  const avgGrowth = Math.round(data.companies.reduce((sum, c) => sum + c.yoy_growth_pct, 0) / data.companies.length);

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
              FY2026 AI Infrastructure Spending
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge className="bg-green-100 text-green-700">
              Updated: {data.last_updated}
            </Badge>
            <button
              onClick={fetchData}
            className="flex items-center gap-2 px-3 py-1.5 bg-white rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all shadow-sm"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
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
              <div className="grid grid-cols-1 md:grid-cols-5 gap-3 mb-4">
                {data.companies.map((company) => (
                  <button
                    key={company.ticker}
                    onClick={() => setSelectedCompany(company)}
                    className={`text-left p-3 rounded-xl border-2 transition-all ${
                      selectedCompany?.ticker === company.ticker
                        ? 'border-blue-500 bg-blue-50 shadow-lg dark:bg-blue-950/40'
                        : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-slate-600'
                    }`}
                  >
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center text-white font-bold mb-2"
                      style={{ backgroundColor: company.color }}
                    >
                      {company.name.charAt(0)}
                    </div>
                    <p className="font-semibold text-slate-900 dark:text-slate-100">{company.name.split(' ')[0]}</p>
                    <p className="text-sm text-slate-500 dark:text-slate-300">{company.ticker}</p>
                    <div className="mt-2">
                      <p className="text-base font-bold" style={{ color: company.color }}>
                        ${company.capex_2026_billions}B
                      </p>
                      <p className="text-xs text-green-600">+{company.yoy_growth_pct}% YoY</p>
                    </div>
                  </button>
                ))}
              </div>

              {selectedCompany && (
                <div className="rounded-xl border border-slate-200 p-3 bg-white dark:border-slate-700 dark:bg-slate-900">
                  <h3 className="mb-3 flex items-center gap-2 font-semibold text-slate-900 dark:text-slate-100">
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold"
                      style={{ backgroundColor: selectedCompany.color }}
                    >
                      {selectedCompany.name.charAt(0)}
                    </div>
                    {selectedCompany.name}
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <h4 className="mb-3 font-semibold text-slate-700 dark:text-slate-200">Key Metrics</h4>
                      <div className="space-y-2">
                        <div className="flex justify-between rounded-lg bg-slate-50 p-2 text-sm dark:bg-slate-800/80">
                          <span className="text-slate-600 dark:text-slate-300">2026 CapEx</span>
                          <span className="font-bold text-slate-900 dark:text-slate-100">${selectedCompany.capex_2026_billions}B</span>
                        </div>
                        <div className="flex justify-between rounded-lg bg-slate-50 p-2 text-sm dark:bg-slate-800/80">
                          <span className="text-slate-600 dark:text-slate-300">2025 CapEx</span>
                          <span className="font-bold text-slate-900 dark:text-slate-100">${selectedCompany.capex_2025_billions}B</span>
                        </div>
                        <div className="flex justify-between rounded-lg bg-green-50 p-2 text-sm dark:bg-emerald-900/35">
                          <span className="text-slate-600 dark:text-slate-200">YoY Growth</span>
                          <span className="font-bold text-green-600">+{selectedCompany.yoy_growth_pct}%</span>
                        </div>
                        {Object.entries(selectedCompany.key_metrics).map(([key, value]) => (
                          <div key={key} className="flex justify-between rounded-lg bg-slate-50 p-2 text-sm dark:bg-slate-800/80">
                            <span className="text-slate-600 dark:text-slate-300">{key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}</span>
                            <span className="font-bold text-slate-900 dark:text-slate-100">{typeof value === 'number' ? (value >= 1 ? `$${value}B` : `${value}%`) : value}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <h4 className="mb-3 font-semibold text-slate-700 dark:text-slate-200">AI Focus Subdomains</h4>
                      <div className="space-y-2">
                        {selectedCompany.ai_focus_areas.map((area, idx) => (
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
                        {selectedCompany.recent_announcements.map((announcement, idx) => (
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
        <div className="xl:col-span-2 self-start">
          <div className="grid grid-cols-1 auto-rows-min content-start gap-2">
            <Card className="border-0 shadow-xl bg-gradient-to-br from-orange-500 to-red-600 text-white">
              <CardContent className="p-2">
                <p className="text-orange-100 text-[10px] leading-tight">Total 2026 CapEx</p>
                <div className="mt-1 flex items-center gap-2">
                  <p className="text-lg font-bold leading-tight">${totalCapex}B</p>
                  <DollarSign className="h-5 w-5 text-orange-200" />
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl dark:border dark:border-slate-800 dark:bg-slate-900">
              <CardContent className="p-2">
                <p className="text-slate-500 text-[10px] leading-tight">YoY Growth (Avg)</p>
                <div className="mt-1 flex items-center gap-2">
                  <p className="text-base font-bold text-green-600 leading-tight">+{avgGrowth}%</p>
                  <TrendingUp className="h-5 w-5 text-green-500" />
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl dark:border dark:border-slate-800 dark:bg-slate-900">
              <CardContent className="p-2">
                <p className="text-slate-500 text-[10px] leading-tight">Stargate Project</p>
                <div className="mt-1 flex items-center gap-2">
                  <p className="text-base font-bold text-blue-600 leading-tight">${data.stargate_project.total_investment_billions}B</p>
                  <Server className="h-5 w-5 text-blue-500" />
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl dark:border dark:border-slate-800 dark:bg-slate-900">
              <CardContent className="p-2">
                <p className="text-slate-500 text-[10px] leading-tight">Planned Capacity</p>
                <div className="mt-1 flex items-center gap-2">
                  <p className="text-base font-bold text-purple-600 leading-tight">{data.stargate_project.planned_capacity_gw}GW</p>
                  <Zap className="h-5 w-5 text-purple-500" />
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        <div className="xl:col-span-6">
        {/* CapEx Comparison Bar Chart */}
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
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="capex_2025" name="2025 CapEx" fill="#A78BFA" radius={[0, 4, 4, 0]} />
                <Bar dataKey="capex_2026" name="2026 CapEx" radius={[0, 4, 4, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <ChartDescription
              description="2025 vs 2026 CapEx by company. 2026 projections reflect near-doubling of AI infrastructure investment."
              source="Financial Statements + Futurum Research"
              sourceUrl="https://futurumgroup.com/insights/ai-capex-2026-the-690b-infrastructure-sprint/"
              lastUpdated={data.last_updated}
            />
          </CardContent>
        </Card>
        </div>

        <div className="xl:col-span-4">
        {/* CapEx Distribution Pie Chart */}
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
            <ChartDescription
              description="Share of 2026 AI infrastructure spending by company."
              source="Financial Statements (SEC Filings)"
            />
          </CardContent>
        </Card>
        </div>
      </div>

      </div>
    </div>
  );
}
