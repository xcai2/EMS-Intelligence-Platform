'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Building2,
  Target,
  Lightbulb,
  RefreshCw,
  ArrowUpRight,
  Cpu,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  Cell,
  LabelList,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

interface RevenueGrowth {
  growth_pct: number | null;
  latest_revenue: string | null;
  prior_revenue: string | null;
  years: string | null;
}

interface CompetitorInvestment {
  company: string;
  ticker: string;
  revenue_growth: RevenueGrowth;
  investment_focus: string[];
  outlook_label: string;
  sentiment_score: number;
  guidance_outlook: string;
  recent_highlights: string[];
}

interface HyperscalerDemand {
  outlook: string;
  drivers: string[];
  beneficiaries: string[];
}

interface CompetitorData {
  generated_at?: string;
  growth_definition?: string;
  competitors: CompetitorInvestment[];
  hyperscaler_demand: HyperscalerDemand;
}

interface CompanySentiment {
  company: string;
  documents_analyzed: number;
  sentiment_score: number;
  ai_mentions: number;
}

const COMPANY_COLORS: Record<string, string> = {
  'Flex': '#3B82F6',
  'Jabil': '#10B981',
  'Celestica': '#6366F1',
  'Benchmark': '#F59E0B',
  'Sanmina': '#EF4444',
  'Plexus': '#14B8A6',
};

const OUTLOOK_COLORS: Record<string, string> = {
  'Very bullish': 'border border-green-300 bg-green-100 text-green-700 dark:border-green-700 dark:bg-green-900/40 dark:text-green-200',
  'Strong': 'border border-emerald-300 bg-emerald-100 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200',
  'Positive': 'border border-blue-300 bg-blue-100 text-blue-700 dark:border-blue-700 dark:bg-blue-900/40 dark:text-blue-200',
  'Stable': 'border border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200',
  'Cautious': 'border border-amber-300 bg-amber-100 text-amber-700 dark:border-amber-700 dark:bg-amber-900/40 dark:text-amber-200',
};


function getOutlookStyle(outlook: string | undefined | null): string {
  if (!outlook) return 'border border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200';
  for (const [key, value] of Object.entries(OUTLOOK_COLORS)) {
    if (outlook.toLowerCase().includes(key.toLowerCase())) {
      return value;
    }
  }
  return 'border border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200';
}

export default function CompetitorInvestmentsPage() {
  const [data, setData] = useState<CompetitorData | null>(null);
  const [sentiment, setSentiment] = useState<CompanySentiment[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCompany, setSelectedCompany] = useState<CompetitorInvestment | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async (forceRefresh = false) => {
    try {
      setLoading(true);
      const forceParam = forceRefresh ? '?force_refresh=true' : '';
      const [competitorRes, sentimentRes] = await Promise.all([
        fetch(`${API_URL}/api/intelligence/competitor-investments${forceParam}`),
        fetch(`${API_URL}/api/sentiment/compare`),
      ]);

      if (competitorRes.ok) {
        const json = await competitorRes.json();
        setData(json);
        setSelectedCompany(json.competitors?.[0] || null);
      }

      if (sentimentRes.ok) {
        const sentimentJson = await sentimentRes.json();
        setSentiment(sentimentJson.comparison || []);
      }
    } catch (err) {
      console.error('Failed to fetch competitor data:', err);
    } finally {
      setLoading(false);
    }
  };

  const sentimentChartData = sentiment.map((row) => ({
    company: row.company,
    sentiment: Math.round((row.sentiment_score || 0) * 100),
  }));

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6 flex items-center justify-center">
        <div className="text-slate-500">Loading competitor investment data...</div>
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 p-4">
      {/* Header */}
      <div className="mb-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-3">
              <div className="bg-gradient-to-br from-indigo-500 to-purple-600 p-1.5 rounded-xl">
                <Target className="h-5 w-5 text-white" />
              </div>
              Competitor Investment Overview
            </h1>
            <p className="text-slate-500 mt-0.5 text-sm">
              Peer investment themes, management tone, and recent strategic moves across key EMS competitors.
            </p>
          </div>
          <button
            onClick={() => fetchData(true)}
            className="flex items-center gap-2 px-3 py-1.5 bg-white rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all shadow-sm"
          >
            <RefreshCw className="h-4 w-4" />
            Re-analyze
          </button>
        </div>
      </div>

      <Card className="border-0 shadow-xl">
        <CardContent className="p-4 lg:p-5">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.45fr_1fr] xl:h-[calc(100vh-165px)]">
            <section className="min-h-0 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/50">
              <h2 className="mb-3 flex items-center gap-2 text-base font-semibold text-slate-900 dark:text-slate-100">
                <Cpu className="h-4 w-4 text-purple-600" />
                Competitive Snapshot
              </h2>
              <p className="mb-2 text-[11px] text-slate-500 dark:text-slate-300">
                {data.growth_definition || 'Revenue growth'}
                {data.generated_at ? ` · generated ${new Date(data.generated_at).toLocaleDateString()}` : ''}
              </p>
              <div className="grid grid-cols-[1.4fr_0.7fr_0.7fr_1fr] gap-2 border-b border-slate-200 pb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-300">
                <span>Company</span>
                <span>Growth</span>
                <span>Focus</span>
                <span>Outlook</span>
              </div>
              <div className="mt-2 space-y-2">
                {data.competitors.map((company) => {
                  const isSelected = selectedCompany?.company === company.company;
                  return (
                    <button
                      key={company.company}
                      type="button"
                      onClick={() => setSelectedCompany(company)}
                      className={`grid w-full grid-cols-[1.4fr_0.7fr_0.7fr_1fr] items-center gap-2 rounded-xl border px-3 py-2 text-left transition ${
                        isSelected
                          ? 'border-indigo-500 bg-indigo-50 shadow-lg dark:bg-indigo-950/40'
                          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900/60 dark:hover:border-slate-600 dark:hover:bg-slate-900'
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <div
                            className="h-7 w-7 rounded-lg flex items-center justify-center text-xs font-bold text-white"
                            style={{ backgroundColor: COMPANY_COLORS[company.company] }}
                          >
                            {company.company.charAt(0)}
                          </div>
                          <p className="truncate font-semibold text-slate-900 dark:text-slate-100">{company.company}</p>
                        </div>
                      </div>
                      <div>
                        {company.revenue_growth?.growth_pct != null ? (
                          <>
                            <p className={`font-semibold ${company.revenue_growth.growth_pct >= 0 ? 'text-green-700 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                              {company.revenue_growth.growth_pct >= 0 ? '+' : ''}{company.revenue_growth.growth_pct}%
                            </p>
                            <p className="text-[10px] text-slate-500 dark:text-slate-300">{company.revenue_growth.years}</p>
                          </>
                        ) : (
                          <p className="text-xs text-slate-400">—</p>
                        )}
                      </div>
                      <p className="font-semibold text-slate-900 dark:text-slate-100">{company.investment_focus.length}</p>
                      <div>
                        <Badge className={getOutlookStyle(company.outlook_label)}>
                          {company.outlook_label || '—'}
                        </Badge>
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="mt-3 rounded-xl border border-slate-200 bg-white px-2.5 py-4 dark:border-slate-700 dark:bg-slate-900">
                <h4 className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-200">
                  <Cpu className="h-4 w-4 text-purple-500" />
                  Sentiment Signals
                </h4>
                <div className="grid grid-cols-1 gap-1.5 lg:grid-cols-[1.1fr_1fr]">
                  <div className="rounded-md border border-slate-200 px-2 py-3 dark:border-slate-700">
                    <ResponsiveContainer width="100%" height={130}>
                      <BarChart
                        data={sentimentChartData}
                        barCategoryGap="4%"
                        margin={{ top: 2, right: 4, left: -14, bottom: -4 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="company" tick={{ fontSize: 9 }} />
                        <YAxis domain={[0, 100]} tick={{ fontSize: 8 }} width={20} />
                        <Tooltip />
                        <Bar dataKey="sentiment" barSize={16} radius={[3, 3, 0, 0]}>
                          <LabelList
                            dataKey="sentiment"
                            position="top"
                            offset={4}
                            className="fill-slate-500 dark:fill-slate-300 text-[9px] font-medium"
                          />
                          {sentimentChartData.map((entry) => (
                            <Cell key={`sentiment-cell-${entry.company}`} fill={COMPANY_COLORS[entry.company] || '#3B82F6'} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  <div className="rounded-md border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <div className="grid grid-cols-[1.15fr_0.6fr_0.8fr_1fr] gap-1 bg-slate-50 px-1.5 py-1 text-[9px] font-medium uppercase text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                      <span>Company</span>
                      <span>Docs</span>
                      <span>Sent.</span>
                      <span>AI/DC Mentions</span>
                    </div>
                    <div className="divide-y divide-slate-200 dark:divide-slate-700">
                      {sentiment.map((row) => (
                        <div key={row.company} className="grid grid-cols-[1.15fr_0.6fr_0.8fr_1fr] gap-1 px-1.5 py-1.5 text-[10px] text-slate-700 dark:text-slate-200">
                          <span className="truncate font-medium">{row.company}</span>
                          <span>{row.documents_analyzed}</span>
                          <span>{Math.round((row.sentiment_score || 0) * 100)}%</span>
                          <span>{row.ai_mentions}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <p className="mt-2 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
                  Sentiment reflects overall tone in analyzed documents; AI/DC mentions indicate how often data-center and AI infrastructure topics appear in company coverage.
                </p>
              </div>
            </section>

            {selectedCompany && (
              <section className="min-h-0 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/50">
                <h2 className="mb-3 flex items-center gap-2 text-base font-semibold text-slate-900 dark:text-slate-100">
                  <Building2 className="h-4 w-4 text-blue-600" />
                  {selectedCompany.company} Strategy Detail
                </h2>

                <div className="space-y-3">
                  {/* Revenue snapshot */}
                  {selectedCompany.revenue_growth?.latest_revenue && (
                    <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
                      <h4 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">Revenue</h4>
                      <p className="text-lg font-bold text-slate-900 dark:text-white">
                        {selectedCompany.revenue_growth.latest_revenue}
                        {selectedCompany.revenue_growth.growth_pct != null && (
                          <span className={`ml-2 text-sm font-semibold ${selectedCompany.revenue_growth.growth_pct >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                            {selectedCompany.revenue_growth.growth_pct >= 0 ? '+' : ''}{selectedCompany.revenue_growth.growth_pct}% YoY
                          </span>
                        )}
                      </p>
                      <p className="text-[10px] text-slate-500 dark:text-slate-400">
                        {selectedCompany.revenue_growth.years}
                        {selectedCompany.revenue_growth.prior_revenue && ` · prior: ${selectedCompany.revenue_growth.prior_revenue}`}
                      </p>
                    </div>
                  )}

                  {/* Guidance Outlook */}
                  <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
                    <h4 className="mb-1 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                      <Lightbulb className="h-4 w-4 text-amber-500" />
                      Guidance Outlook
                      <Badge className={getOutlookStyle(selectedCompany.outlook_label)}>
                        {selectedCompany.outlook_label}
                      </Badge>
                    </h4>
                    <p className="text-sm text-slate-700 dark:text-slate-200 leading-relaxed">{selectedCompany.guidance_outlook}</p>
                  </div>

                  {/* Focus Areas */}
                  <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
                    <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                      <Target className="h-4 w-4 text-indigo-500" />
                      Focus Areas
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedCompany.investment_focus.map((focus, idx) => (
                        <span key={idx} className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-200">
                          {focus}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Recent Highlights */}
                  <div className="min-h-0 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
                    <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                      <ArrowUpRight className="h-4 w-4 text-green-500" />
                      Recent Highlights
                    </h4>
                    <ul className="space-y-1.5 text-sm text-slate-700 dark:text-slate-200">
                      {selectedCompany.recent_highlights.map((highlight, idx) => (
                        <li key={idx} className="rounded-lg bg-green-50 px-2.5 py-2 dark:bg-emerald-900/35 dark:text-emerald-100">
                          • {highlight}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </section>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
