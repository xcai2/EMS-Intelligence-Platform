'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { 
  Building2,
  TrendingUp,
  TrendingDown,
  Brain,
  Activity,
  FileText,
  ArrowLeft,
  RefreshCw,
  Globe,
  AlertTriangle,
  BarChart3,
  Minus,
  DollarSign,
  Users
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  Legend,
} from 'recharts';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

const COMPANY_COLORS: Record<string, string> = {
  'flex': '#3B82F6',
  'jabil': '#10B981',
  'celestica': '#6366F1',
  'benchmark': '#F59E0B',
  'sanmina': '#EF4444',
  'plexus': '#14B8A6',
};

const COMPANY_NAMES: Record<string, string> = {
  'flex': 'Flex Ltd.',
  'jabil': 'Jabil Inc.',
  'celestica': 'Celestica Inc.',
  'benchmark': 'Benchmark Electronics',
  'sanmina': 'Sanmina Corporation',
  'plexus': 'Plexus Corp',
};

type TabType = 'overview' | 'filings' | 'financials' | 'capex' | 'hiring';

export default function CompanyDetailPage() {
  const params = useParams();
  const company = (params.company as string)?.charAt(0).toUpperCase() + (params.company as string)?.slice(1);
  const companyKey = params.company as string;
  
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [overview, setOverview] = useState<any>(null);
  const [filings, setFilings] = useState<any>(null);
  const [financials, setFinancials] = useState<any>(null);
  const [capexData, setCapexData] = useState<any>(null);
  const [hiring, setHiring] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (company) {
      fetchOverview();
    }
  }, [company]);

  useEffect(() => {
    if (company) {
      fetchTabData(activeTab);
    }
  }, [activeTab, company]);

  const fetchOverview = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/company/${company}/overview`);
      if (res.ok) {
        setOverview(await res.json());
      }
    } catch (err) {
      console.error('Failed to fetch overview:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTabData = async (tab: TabType) => {
    try {
      switch (tab) {
        case 'filings':
          if (!filings) {
            const res = await fetch(`${API_URL}/api/company/${company}/filings`);
            if (res.ok) setFilings(await res.json());
          }
          break;
        case 'financials':
          if (!financials) {
            const res = await fetch(`${API_URL}/api/company/${company}/financials`);
            if (res.ok) setFinancials(await res.json());
          }
          break;
        case 'capex':
          if (!capexData) {
            const res = await fetch(`${API_URL}/api/company/${company}/capex`);
            if (res.ok) setCapexData(await res.json());
          }
          break;
        case 'hiring':
          if (!hiring) {
            const res = await fetch(`${API_URL}/api/jobs/${company}`);
            if (res.ok) setHiring(await res.json());
          }
          break;
      }
    } catch (err) {
      console.error(`Failed to fetch ${tab} data:`, err);
    }
  };

  const getTrendIcon = (direction: string) => {
    if (direction === 'increasing') return <TrendingUp className="h-4 w-4 text-green-500" />;
    if (direction === 'decreasing') return <TrendingDown className="h-4 w-4 text-red-500" />;
    return <Minus className="h-4 w-4 text-gray-400" />;
  };

  const getOutlookColor = (outlook: string) => {
    if (outlook === 'positive') return 'bg-green-100 text-green-700 border-green-200';
    if (outlook === 'cautious') return 'bg-red-100 text-red-700 border-red-200';
    return 'bg-gray-100 text-gray-700 border-gray-200';
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
          <p className="text-slate-600 mt-4 font-medium">Loading {company} data...</p>
        </div>
      </div>
    );
  }

  const color = COMPANY_COLORS[companyKey] || '#64748B';
  const fullName = COMPANY_NAMES[companyKey] || company;

  const tabs = [
    { id: 'overview', label: 'Overview', icon: Building2 },
    { id: 'filings', label: 'Filings', icon: FileText },
    { id: 'financials', label: 'Financials', icon: DollarSign },
    { id: 'capex', label: 'CapEx', icon: BarChart3 },
    { id: 'hiring', label: 'Hiring', icon: Users },
  ];

  // CapEx breakdown for chart
  const capexBreakdownData = capexData?.breakdown ? Object.entries(capexData.breakdown).map(([key, val]: [string, any]) => ({
    name: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
    value: val.mentions || 0,
  })).filter(d => d.value > 0) : [];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 p-6">
      {/* Header */}
      <div className="mb-6">
        <Link 
          href="/companies"
          className="inline-flex items-center gap-2 text-slate-500 hover:text-slate-700 mb-4 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Companies
        </Link>
        
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div 
              className="w-16 h-16 rounded-2xl flex items-center justify-center text-white text-2xl font-bold shadow-lg"
              style={{ backgroundColor: color }}
            >
              {company?.charAt(0)}
            </div>
            <div>
              <h1 className="text-3xl font-bold text-slate-900">{company}</h1>
              <p className="text-slate-500">{fullName}</p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            {overview?.trends?.outlook && (
              <Badge className={`${getOutlookColor(overview.trends.outlook)} border px-4 py-2 text-sm`}>
                {overview.trends.outlook.charAt(0).toUpperCase() + overview.trends.outlook.slice(1)} Outlook
              </Badge>
            )}
            <button
              onClick={fetchOverview}
              className="flex items-center gap-2 px-4 py-2 bg-white rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all shadow-sm"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card className="border-0 shadow-lg">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-slate-500">AI Focus</span>
              <Brain className="h-4 w-4 text-purple-500" />
            </div>
            <p className="text-2xl font-bold text-slate-900">
              {overview?.investment?.ai_focus_percentage?.toFixed(0) || 0}%
            </p>
            <p className="text-xs text-slate-400 mt-1">SEC Filings · NLP</p>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-lg">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-slate-500">Sentiment</span>
              <Activity className="h-4 w-4 text-green-500" />
            </div>
            <p className="text-2xl font-bold text-slate-900">
              {((overview?.sentiment?.score || 0) * 100).toFixed(0)}%
            </p>
            <p className="text-xs text-slate-400 mt-1">
              {overview?.sentiment?.method === 'finbert' ? 'FinBERT · SEC Filings' : 'Lexicon · SEC Filings'}
            </p>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-lg">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-slate-500">Facilities</span>
              <Globe className="h-4 w-4 text-blue-500" />
            </div>
            <p className="text-2xl font-bold text-slate-900">
              {overview?.facilities?.total || 0}
            </p>
            <p className="text-xs text-slate-400 mt-1">SEC Filings · NLP</p>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-lg">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-slate-500">Documents</span>
              <FileText className="h-4 w-4 text-orange-500" />
            </div>
            <p className="text-2xl font-bold text-slate-900">
              {overview?.documents?.toLocaleString() || 0}
            </p>
            <p className="text-xs text-slate-400 mt-1">ChromaDB Vector DB</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="mb-6 border-b border-slate-200">
        <div className="flex gap-1 overflow-x-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as TabType)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all whitespace-nowrap ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                }`}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Content */}
      <div className="space-y-6">
        {activeTab === 'overview' && overview && (
          <>
            {/* Trend Analysis */}
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-green-600" />
                    Trend Analysis
                  </CardTitle>
                  <span className="text-xs px-2 py-1 rounded-full bg-slate-100 text-slate-500 border border-slate-200">
                    Source: ChromaDB · SEC Filings
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-slate-700">CapEx Trend</span>
                      {getTrendIcon(overview.trends?.capex_trend?.direction)}
                    </div>
                    <p className="text-sm text-slate-500">
                      {overview.trends?.capex_trend?.direction || 'N/A'} 
                      {overview.trends?.capex_trend?.confidence && 
                        ` (${overview.trends.capex_trend.confidence.toFixed(0)}% confidence)`}
                    </p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-slate-700">AI Focus Trend</span>
                      {getTrendIcon(overview.trends?.ai_focus_trend?.direction)}
                    </div>
                    <p className="text-sm text-slate-500">
                      {overview.trends?.ai_focus_trend?.direction || 'N/A'}
                      {overview.trends?.ai_focus_trend?.confidence && 
                        ` (${overview.trends.ai_focus_trend.confidence.toFixed(0)}% confidence)`}
                    </p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-slate-700">Sentiment Trend</span>
                      {getTrendIcon(overview.trends?.sentiment_trend?.direction)}
                    </div>
                    <p className="text-sm text-slate-500">
                      {overview.trends?.sentiment_trend?.direction || 'N/A'}
                      {overview.trends?.sentiment_trend?.confidence && 
                        ` (${overview.trends.sentiment_trend.confidence.toFixed(0)}% confidence)`}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Company Info */}
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <Building2 className="h-5 w-5 text-blue-600" />
                    Company Information
                  </CardTitle>
                  <span className="text-xs px-2 py-1 rounded-full bg-slate-100 text-slate-500 border border-slate-200">
                    Source: SEC EDGAR Config
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-sm text-slate-500">Ticker</p>
                    <p className="font-semibold">{overview.info?.ticker}</p>
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">Headquarters</p>
                    <p className="font-semibold">{overview.info?.headquarters}</p>
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">Fiscal Year End</p>
                    <p className="font-semibold">{overview.info?.fiscal_year_end}</p>
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">Industry</p>
                    <p className="font-semibold">{overview.info?.industry}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </>
        )}

        {activeTab === 'filings' && (
          <Card className="border-0 shadow-xl">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-orange-600" />
                  Recent Filings
                </CardTitle>
                <span className="text-xs px-2 py-1 rounded-full bg-orange-50 text-orange-600 border border-orange-200">
                  Source: ChromaDB · SEC EDGAR
                </span>
              </div>
            </CardHeader>
            <CardContent>
              {filings?.filings?.length > 0 ? (
                <div className="space-y-3">
                  {filings.filings.map((filing: any, idx: number) => (
                    <div key={idx} className="p-4 bg-slate-50 rounded-xl">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <Badge>{filing.filing_type}</Badge>
                          <span className="text-sm text-slate-500">{filing.fiscal_year}</span>
                        </div>
                        <span className="text-xs text-slate-400">{filing.chunk_count} chunks</span>
                      </div>
                      <p className="text-sm text-slate-600 line-clamp-2">{filing.preview}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 text-center py-8">Loading filings...</p>
              )}
            </CardContent>
          </Card>
        )}

        {activeTab === 'financials' && (
          <div className="space-y-6">
            {/* Source badge */}
            {financials && (
              <div className="flex items-center gap-2">
                <span className="text-xs px-2 py-1 rounded-full font-medium border bg-green-50 text-green-700 border-green-200">
                  {financials.source === 'yfinance' ? 'Live data via Yahoo Finance' : 'Extracted from SEC filings'}
                </span>
                {financials.ticker && <span className="text-xs text-slate-400">{financials.ticker}</span>}
              </div>
            )}

            {financials?.fiscal_years && Object.keys(financials.fiscal_years).length > 0 ? (() => {
              const years = Object.keys(financials.fiscal_years).sort();
              const barData = years.map(yr => ({
                year: yr,
                'Total Revenue': financials.fiscal_years[yr].revenue ?? null,
                'Operating Income': financials.fiscal_years[yr].operating_income ?? null,
                'Net Income': financials.fiscal_years[yr].net_income ?? null,
              }));
              const marginData = years.map(yr => ({
                year: yr,
                'Operating Margin %': financials.fiscal_years[yr].operating_margin ?? null,
              }));

              return (
                <>
                  {/* Revenue / Income bar chart */}
                  <Card className="border-0 shadow-xl">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <DollarSign className="h-5 w-5 text-blue-600" />
                        Revenue & Income (USD millions)
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ResponsiveContainer width="100%" height={280}>
                        <BarChart data={barData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="year" />
                          <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}B`} />
                          <Tooltip formatter={(v: any) => [`$${Number(v).toLocaleString()}M`, '']} />
                          <Legend />
                          <Bar dataKey="Total Revenue" fill="#3B82F6" radius={[4, 4, 0, 0]} />
                          <Bar dataKey="Operating Income" fill="#8B5CF6" radius={[4, 4, 0, 0]} />
                          <Bar dataKey="Net Income" fill="#10B981" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>

                  {/* Operating Margin line chart */}
                  <Card className="border-0 shadow-xl">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Activity className="h-5 w-5 text-purple-600" />
                        Operating Margin (%)
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ResponsiveContainer width="100%" height={220}>
                        <LineChart data={marginData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="year" />
                          <YAxis tickFormatter={(v) => `${v}%`} domain={['auto', 'auto']} />
                          <Tooltip formatter={(v: any) => [`${Number(v).toFixed(2)}%`, 'Operating Margin']} />
                          <Line type="monotone" dataKey="Operating Margin %" stroke="#8B5CF6" strokeWidth={2} dot={{ r: 4 }} />
                        </LineChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>

                  {/* Metrics table */}
                  <Card className="border-0 shadow-xl">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <BarChart3 className="h-5 w-5 text-slate-600" />
                        Key Metrics by Year
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-slate-200 bg-slate-50">
                              <th className="text-left py-3 px-4 font-semibold text-slate-700">Metric</th>
                              {years.map(yr => (
                                <th key={yr} className="text-right py-3 px-4 font-semibold text-slate-700">{yr}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {[
                              { key: 'revenue', label: 'Total Revenue', format: (v: number) => `$${v.toLocaleString()}M` },
                              { key: 'operating_income', label: 'Operating Income', format: (v: number) => `$${v.toLocaleString()}M` },
                              { key: 'net_income', label: 'Net Income', format: (v: number) => `$${v.toLocaleString()}M` },
                              { key: 'eps', label: 'EPS (Diluted)', format: (v: number) => `$${v.toFixed(2)}` },
                              { key: 'operating_margin', label: 'Operating Margin', format: (v: number) => `${v.toFixed(2)}%` },
                            ].map(({ key, label, format }) => (
                              <tr key={key} className="border-b border-slate-100 hover:bg-slate-50">
                                <td className="py-3 px-4 font-medium text-slate-700">{label}</td>
                                {years.map(yr => {
                                  const val = (financials.fiscal_years[yr] as any)[key];
                                  return (
                                    <td key={yr} className="py-3 px-4 text-right text-slate-600">
                                      {val != null ? format(val) : '—'}
                                    </td>
                                  );
                                })}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </CardContent>
                  </Card>
                </>
              );
            })() : (
              <Card className="border-0 shadow-xl">
                <CardContent className="py-12 text-center text-slate-500">Loading financials...</CardContent>
              </Card>
            )}
          </div>
        )}

        {activeTab === 'capex' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-orange-600" />
                    CapEx Breakdown
                  </CardTitle>
                  <span className="text-xs px-2 py-1 rounded-full bg-orange-50 text-orange-600 border border-orange-200">
                    Source: ChromaDB · SEC Filings
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                {capexBreakdownData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={capexBreakdownData} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" />
                      <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Bar dataKey="value" fill="#F59E0B" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="text-slate-500 text-center py-8">Loading CapEx data...</p>
                )}
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5 text-red-600" />
                    CapEx Anomalies
                  </CardTitle>
                  <span className="text-xs px-2 py-1 rounded-full bg-red-50 text-red-600 border border-red-200">
                    Source: ChromaDB · SEC Filings
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                {capexData?.has_anomalies ? (
                  <div className="space-y-3">
                    {capexData.anomalies?.map((anomaly: any, idx: number) => (
                      <div key={idx} className={`p-4 rounded-xl border ${
                        anomaly.severity === 'high' ? 'bg-red-50 border-red-200' : 'bg-orange-50 border-orange-200'
                      }`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium">{anomaly.period}</span>
                          <Badge className={anomaly.severity === 'high' ? 'bg-red-200 text-red-800' : 'bg-orange-200 text-orange-800'}>
                            {anomaly.direction}
                          </Badge>
                        </div>
                        <p className="text-sm text-slate-600">
                          {anomaly.pct_change_from_mean > 0 ? '+' : ''}{anomaly.pct_change_from_mean}% from mean
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <div className="bg-green-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
                      <TrendingUp className="h-8 w-8 text-green-600" />
                    </div>
                    <p className="text-slate-600">No anomalies detected</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {activeTab === 'hiring' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <Users className="h-5 w-5 text-green-500" />
                    Hiring Activity
                  </CardTitle>
                  <span className="text-xs px-2 py-1 rounded-full bg-green-50 text-green-600 border border-green-200">
                    Source: Web Search · DuckDuckGo
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                {hiring ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl">
                      <div>
                        <p className="text-sm text-slate-500">Total Openings</p>
                        <p className="text-3xl font-bold text-green-600">{hiring.total_jobs || 0}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-slate-500">Hiring Score</p>
                        <p className="text-3xl font-bold text-emerald-600">{hiring.hiring_score?.hiring_score || 0}</p>
                      </div>
                    </div>
                    {hiring.analysis && (
                      <>
                        <div className="grid grid-cols-2 gap-3">
                          <div className="p-3 bg-purple-50 rounded-xl text-center">
                            <p className="text-sm text-purple-600">AI Focus</p>
                            <p className="text-xl font-bold text-purple-700">{hiring.analysis.ai_hiring_focus || 0}%</p>
                          </div>
                          <div className="p-3 bg-blue-50 rounded-xl text-center">
                            <p className="text-sm text-blue-600">Tech Focus</p>
                            <p className="text-xl font-bold text-blue-700">{hiring.analysis.tech_hiring_focus || 0}%</p>
                          </div>
                        </div>
                        <div className="border-t pt-4">
                          <p className="text-sm font-medium text-slate-700 mb-2">By Category</p>
                          <div className="space-y-2">
                            {hiring.analysis.by_category && Object.entries(hiring.analysis.by_category).map(([cat, count]: [string, any]) => (
                              <div key={cat} className="flex justify-between items-center p-2 bg-slate-50 rounded">
                                <span className="text-sm capitalize">{cat.replace(/_/g, ' ')}</span>
                                <Badge variant="outline">{count} jobs</Badge>
                              </div>
                            ))}
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                ) : (
                  <p className="text-slate-500 text-center py-8">Loading hiring data...</p>
                )}
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Current Job Openings</CardTitle>
                  <span className="text-xs px-2 py-1 rounded-full bg-green-50 text-green-600 border border-green-200">
                    Source: LinkedIn · Indeed · Web
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                {hiring?.jobs?.length > 0 ? (
                  <div className="space-y-3 max-h-96 overflow-y-auto">
                    {hiring.jobs.slice(0, 10).map((job: any, idx: number) => (
                      <a
                        key={idx}
                        href={job.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block p-3 bg-slate-50 rounded-xl hover:bg-slate-100 transition-colors"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1">
                            <p className="font-medium text-sm text-blue-600 hover:underline line-clamp-2">{job.title}</p>
                            <p className="text-xs text-slate-500 mt-1 line-clamp-2">{job.snippet}</p>
                          </div>
                          <div className="flex flex-col gap-1">
                            <Badge variant="outline" className="text-xs capitalize">
                              {job.category?.replace(/_/g, ' ')}
                            </Badge>
                            <Badge variant="outline" className="text-xs capitalize bg-slate-100">
                              {job.seniority}
                            </Badge>
                          </div>
                        </div>
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-500 text-center py-8">No job openings found</p>
                )}
              </CardContent>
            </Card>
          </div>
        )}

      </div>
    </div>
  );
}
