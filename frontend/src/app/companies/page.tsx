'use client';

import { useState, useEffect } from 'react';
import { readPersistentCache, writePersistentCache } from '@/lib/persistentCache';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Building2,
  MapPin,
  Calendar,
  FileText,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Brain,
  Activity,
  ArrowRight,
  Globe,
  Minus,
  DollarSign,
  Cpu,
  AlertTriangle,
  Zap,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from 'recharts';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

// Module-level cache — survives component unmount/remount on Next.js navigation
const _cache: {
  companies: Company[];
  analytics: Record<string, AnalyticsData>;
  capexData: CapExMention[];
  aiData: AIInvestmentMention[];
  trends: any;
  classification: any;
  anomalies: any;
} = {
  companies: [],
  analytics: {},
  capexData: [],
  aiData: [],
  trends: null,
  classification: null,
  anomalies: null,
};
let _cachePopulated = false;

interface Company {
  ticker: string;
  name: string;
  cik: string;
  fiscal_year_end: string;
  headquarters: string;
  color: string;
  document_count: number;
}

interface AnalyticsData {
  company: string;
  ai_focus: number;
  sentiment: number;
  trend: string;
  facilities: number;
}

interface CapExMention {
  company: string;
  count: number;
  recent_context: string[];
}

interface AIInvestmentMention {
  company: string;
  ai_mentions: number;
  data_center_mentions: number;
  total: number;
}

interface TrendData {
  company: string;
  overall_outlook: string;
  capex_trend: { direction: string; confidence: number };
  ai_focus_trend: { direction: string; confidence: number };
  sentiment_trend: { direction: string; confidence: number };
}

const COMPANY_DISPLAY_NAMES: Record<string, string> = {
  'FLEX': 'Flex',
  'JBL': 'Jabil',
  'CLS': 'Celestica',
  'BHE': 'Benchmark',
  'SANM': 'Sanmina',
  'PLXS': 'Plexus',
};

const COMPANY_COLORS: Record<string, string> = {
  'Flex': '#00A0E3',
  'Jabil': '#1E4D2B',
  'Celestica': '#003366',
  'Benchmark': '#B8860B',
  'Sanmina': '#C41E3A',
  'Plexus': '#0F766E',
};

type Tab = 'overview' | 'analysis' | 'trends';

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[]>(_cache.companies);
  const [analytics, setAnalytics] = useState<Record<string, AnalyticsData>>(_cache.analytics);
  const [capexData, setCapexData] = useState<CapExMention[]>(_cache.capexData);
  const [aiData, setAiData] = useState<AIInvestmentMention[]>(_cache.aiData);
  const [trends, setTrends] = useState<any>(_cache.trends);
  const [classification, setClassification] = useState<any>(_cache.classification);
  const [anomalies, setAnomalies] = useState<any>(_cache.anomalies);
  const [loading, setLoading] = useState(!_cachePopulated);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [selectedCompany, setSelectedCompany] = useState<string | null>(null);

  useEffect(() => {
    if (_cachePopulated) return;
    // Seed module-level cache from localStorage so the page renders instantly
    const persisted = readPersistentCache<typeof _cache>('cache:companies:index:v1');
    if (persisted) {
      _cache.companies = persisted.companies ?? [];
      _cache.analytics = persisted.analytics ?? {};
      _cache.capexData = persisted.capexData ?? [];
      _cache.aiData = persisted.aiData ?? [];
      _cache.trends = persisted.trends ?? null;
      _cache.classification = persisted.classification ?? null;
      _cache.anomalies = persisted.anomalies ?? null;
      _cachePopulated = true;
      setCompanies(_cache.companies);
      setAnalytics(_cache.analytics);
      setCapexData(_cache.capexData);
      setAiData(_cache.aiData);
      setTrends(_cache.trends);
      setClassification(_cache.classification);
      setAnomalies(_cache.anomalies);
      setLoading(false);
    } else {
      fetchData();
    }
  }, []);

  // Per-request fetch that never throws — returns null on any error or non-2xx
  const safeFetch = async (url: string) => {
    try {
      const res = await fetch(url);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  };

  const fetchData = async () => {
    setLoading(true);

    // Wave 1: core data — page won't load without /api/companies
    const companiesData = await safeFetch(`${API_URL}/api/companies`);
    if (!companiesData) {
      setError('Failed to connect to backend. Make sure the server is running on port 8001.');
      setLoading(false);
      return;
    }
    const newCompanies = companiesData.companies ?? [];
    setCompanies(newCompanies);

    // Wave 2: analytics overlays — run in parallel but failures are silent
    const [classData, sentimentData, trendsData, geoData] = await Promise.all([
      safeFetch(`${API_URL}/api/analytics/classification`),
      safeFetch(`${API_URL}/api/sentiment/compare`),
      safeFetch(`${API_URL}/api/analytics/trends`),
      safeFetch(`${API_URL}/api/geographic/compare`),
    ]);

    const analyticsMap: Record<string, AnalyticsData> = {};

    if (classData) {
      setClassification(classData);
      classData.companies?.forEach((c: any) => {
        analyticsMap[c.company] = {
          company: c.company,
          ai_focus: c.overall_ai_focus_percentage || 0,
          sentiment: 0,
          trend: 'neutral',
          facilities: 0,
        };
      });
    }

    if (sentimentData) {
      sentimentData.companies?.forEach((c: any) => {
        if (analyticsMap[c.company])
          analyticsMap[c.company].sentiment = (c.sentiment_score || 0) * 100;
      });
    }

    if (trendsData) {
      setTrends(trendsData);
      trendsData.companies?.forEach((c: any) => {
        if (analyticsMap[c.company])
          analyticsMap[c.company].trend = c.overall_outlook || 'neutral';
      });
    }

    if (geoData) {
      geoData.companies?.forEach((c: any) => {
        if (analyticsMap[c.company])
          analyticsMap[c.company].facilities = c.total_facilities || 0;
      });
    }

    setAnalytics(analyticsMap);
    setError(null);
    setLoading(false);

    // Wave 3: secondary analytics — fetched after page renders, failures are silent
    const [capexResult, aiResult, anomalyResult] = await Promise.all([
      safeFetch(`${API_URL}/api/analysis/capex`),
      safeFetch(`${API_URL}/api/analysis/ai-investments`),
      safeFetch(`${API_URL}/api/analytics/anomalies`),
    ]);
    const newCapex = capexResult?.mentions ?? [];
    const newAi = aiResult?.mentions ?? [];
    if (capexResult) setCapexData(newCapex);
    if (aiResult) setAiData(newAi);
    if (anomalyResult) setAnomalies(anomalyResult);

    // Populate module-level cache
    _cache.companies = newCompanies;
    _cache.analytics = analyticsMap;
    _cache.capexData = newCapex;
    _cache.aiData = newAi;
    _cache.trends = trendsData ?? _cache.trends;
    _cache.classification = classData ?? _cache.classification;
    _cache.anomalies = anomalyResult ?? _cache.anomalies;
    _cachePopulated = true;
    writePersistentCache('cache:companies:index:v1', { ..._cache });
  };

  const refreshData = async () => {
    setRefreshing(true);
    setRefreshMsg(null);

    const companiesData = await safeFetch(`${API_URL}/api/companies`);
    if (!companiesData) {
      setRefreshing(false);
      setRefreshMsg('Refresh failed, unable to connect to backend');
      return;
    }
    const newCompanies = companiesData.companies ?? [];

    const [classData, sentimentData, trendsData, geoData] = await Promise.all([
      safeFetch(`${API_URL}/api/analytics/classification`),
      safeFetch(`${API_URL}/api/sentiment/compare`),
      safeFetch(`${API_URL}/api/analytics/trends`),
      safeFetch(`${API_URL}/api/geographic/compare`),
    ]);

    const analyticsMap: Record<string, AnalyticsData> = {};
    if (classData) {
      classData.companies?.forEach((c: any) => {
        analyticsMap[c.company] = {
          company: c.company,
          ai_focus: c.overall_ai_focus_percentage || 0,
          sentiment: 0,
          trend: 'neutral',
          facilities: 0,
        };
      });
    }
    if (sentimentData) {
      sentimentData.companies?.forEach((c: any) => {
        if (analyticsMap[c.company])
          analyticsMap[c.company].sentiment = (c.sentiment_score || 0) * 100;
      });
    }
    if (trendsData) {
      trendsData.companies?.forEach((c: any) => {
        if (analyticsMap[c.company])
          analyticsMap[c.company].trend = c.overall_outlook || 'neutral';
      });
    }
    if (geoData) {
      geoData.companies?.forEach((c: any) => {
        if (analyticsMap[c.company])
          analyticsMap[c.company].facilities = c.total_facilities || 0;
      });
    }

    const [capexResult, aiResult, anomalyResult] = await Promise.all([
      safeFetch(`${API_URL}/api/analysis/capex`),
      safeFetch(`${API_URL}/api/analysis/ai-investments`),
      safeFetch(`${API_URL}/api/analytics/anomalies`),
    ]);
    const newCapex = capexResult?.mentions ?? _cache.capexData;
    const newAi = aiResult?.mentions ?? _cache.aiData;
    const newAnomalies = anomalyResult ?? _cache.anomalies;

    // Only update state + cache when something actually changed
    let changed = false;
    if (JSON.stringify(newCompanies) !== JSON.stringify(_cache.companies)) {
      setCompanies(newCompanies);
      _cache.companies = newCompanies;
      changed = true;
    }
    if (JSON.stringify(analyticsMap) !== JSON.stringify(_cache.analytics)) {
      setAnalytics(analyticsMap);
      _cache.analytics = analyticsMap;
      changed = true;
    }
    if (classData && JSON.stringify(classData) !== JSON.stringify(_cache.classification)) {
      setClassification(classData);
      _cache.classification = classData;
      changed = true;
    }
    if (trendsData && JSON.stringify(trendsData) !== JSON.stringify(_cache.trends)) {
      setTrends(trendsData);
      _cache.trends = trendsData;
      changed = true;
    }
    if (JSON.stringify(newCapex) !== JSON.stringify(_cache.capexData)) {
      setCapexData(newCapex);
      _cache.capexData = newCapex;
      changed = true;
    }
    if (JSON.stringify(newAi) !== JSON.stringify(_cache.aiData)) {
      setAiData(newAi);
      _cache.aiData = newAi;
      changed = true;
    }
    if (JSON.stringify(newAnomalies) !== JSON.stringify(_cache.anomalies)) {
      setAnomalies(newAnomalies);
      _cache.anomalies = newAnomalies;
      changed = true;
    }

    if (changed) writePersistentCache('cache:companies:index:v1', { ..._cache });
    setRefreshing(false);
    setRefreshMsg(changed ? '数据已更新' : '数据无变化，缓存保持不变');
    setTimeout(() => setRefreshMsg(null), 3000);
  };

  const getTrendIcon = (direction: string) => {
    if (direction === 'positive' || direction === 'increasing')
      return <TrendingUp className="h-4 w-4 text-green-500" />;
    if (direction === 'cautious' || direction === 'decreasing')
      return <TrendingDown className="h-4 w-4 text-red-500" />;
    return <Minus className="h-4 w-4 text-slate-400" />;
  };

  const getOutlookBadge = (trend: string) => {
    if (trend === 'positive') return 'bg-green-100 text-green-700 border-green-200';
    if (trend === 'cautious') return 'bg-red-100 text-red-700 border-red-200';
    return 'bg-slate-100 text-slate-700 border-slate-200';
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
          <p className="text-slate-600 mt-4 font-medium">Loading companies...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center p-6">
        <Card className="max-w-md w-full shadow-xl border-0">
          <CardContent className="p-8 text-center">
            <div className="bg-red-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
              <Building2 className="h-8 w-8 text-red-600" />
            </div>
            <h2 className="text-xl font-bold text-slate-900 mb-2">Connection Error</h2>
            <p className="text-slate-600 mb-6">{error}</p>
            <button
              onClick={fetchData}
              className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-500 text-white rounded-xl hover:shadow-lg transition-all font-medium"
            >
              <RefreshCw className="h-4 w-4" />
              Retry
            </button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Derived chart data
  const capexChartData = capexData.map((item) => ({
    name: item.company,
    mentions: item.count,
    fill: COMPANY_COLORS[item.company] || '#666',
  }));

  const aiChartData = aiData.map((item) => ({
    name: item.company,
    'AI Mentions': item.ai_mentions,
    'Data Center': item.data_center_mentions,
  }));

  const aiClassificationData = classification?.companies?.map((c: any) => ({
    company: c.company,
    ai_focus: c.overall_ai_focus_percentage,
    traditional: 100 - c.overall_ai_focus_percentage,
  })) || [];

  const trendComparisonData = trends?.companies?.map((t: TrendData) => ({
    company: t.company,
    capex: t.capex_trend?.confidence || 0,
    ai: t.ai_focus_trend?.confidence || 0,
    sentiment: t.sentiment_trend?.confidence || 0,
  })) || [];

  const selectedCapex = selectedCompany
    ? capexData.find((c) => c.company === selectedCompany)
    : null;

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Overview', icon: <Building2 className="h-4 w-4" /> },
    { id: 'analysis', label: 'Investment Analysis', icon: <DollarSign className="h-4 w-4" /> },
    { id: 'trends', label: 'Trend Intelligence', icon: <BarChart3 className="h-4 w-4" /> },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-3 rounded-xl shadow-lg shadow-blue-500/20">
              <Building2 className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-slate-900">Companies</h1>
              <p className="text-slate-500 mt-1">Electronics Manufacturing Services intelligence hub</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {refreshMsg && (
              <span className={`text-sm font-medium ${refreshMsg.includes('无变化') ? 'text-slate-500' : 'text-green-600'}`}>
                {refreshMsg}
              </span>
            )}
            <button
              onClick={refreshData}
              disabled={refreshing}
              className="flex items-center gap-2 px-4 py-2 bg-white rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all shadow-sm disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-white rounded-xl border border-slate-200 p-1 w-fit shadow-sm">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
              activeTab === tab.id
                ? 'bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-md'
                : 'text-slate-600 hover:bg-slate-50'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* ───────────────────── OVERVIEW TAB ───────────────────── */}
      {activeTab === 'overview' && (
        <>
          {/* Company Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
            {companies.map((company) => {
              const displayName =
                COMPANY_DISPLAY_NAMES[company.ticker] || company.name.split(' ')[0];
              const companyAnalytics = analytics[displayName] || {};

              return (
                <Link
                  key={company.ticker}
                  href={`/companies/${displayName.toLowerCase()}`}
                  className="block"
                >
                  <Card className="border-0 shadow-xl hover:shadow-2xl transition-all duration-300 group cursor-pointer overflow-hidden h-full">
                    <div className="h-2 w-full" style={{ backgroundColor: company.color }} />
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div
                            className="w-12 h-12 rounded-xl flex items-center justify-center text-white text-lg font-bold shadow-lg group-hover:scale-110 transition-transform"
                            style={{ backgroundColor: company.color }}
                          >
                            {displayName.charAt(0)}
                          </div>
                          <div>
                            <CardTitle className="text-lg group-hover:text-blue-600 transition-colors">
                              {company.name}
                            </CardTitle>
                            <Badge variant="outline" className="mt-1">
                              {company.ticker}
                            </Badge>
                          </div>
                        </div>
                        {companyAnalytics.trend && (
                          <Badge className={`${getOutlookBadge(companyAnalytics.trend)} border`}>
                            {companyAnalytics.trend}
                          </Badge>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3 mt-2">
                        <div className="flex items-center gap-2 text-sm text-slate-600">
                          <MapPin className="h-4 w-4 text-slate-400" />
                          <span>{company.headquarters}</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm text-slate-600">
                          <Calendar className="h-4 w-4 text-slate-400" />
                          <span>FY ends: {company.fiscal_year_end}</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm text-slate-600">
                          <FileText className="h-4 w-4 text-slate-400" />
                          <span>{company.document_count.toLocaleString()} document chunks</span>
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-3 mt-4 pt-4 border-t border-slate-100">
                        <div className="text-center">
                          <div className="flex items-center justify-center gap-1 mb-1">
                            <Brain className="h-3 w-3 text-purple-500" />
                          </div>
                          <p className="text-lg font-bold text-slate-900">
                            {companyAnalytics.ai_focus?.toFixed(0) || 0}%
                          </p>
                          <p className="text-xs text-slate-500">AI Focus</p>
                        </div>
                        <div className="text-center">
                          <div className="flex items-center justify-center gap-1 mb-1">
                            <Activity className="h-3 w-3 text-green-500" />
                          </div>
                          <p className="text-lg font-bold text-slate-900">
                            {companyAnalytics.sentiment?.toFixed(0) || 0}%
                          </p>
                          <p className="text-xs text-slate-500">Sentiment</p>
                        </div>
                        <div className="text-center">
                          <div className="flex items-center justify-center gap-1 mb-1">
                            <Globe className="h-3 w-3 text-blue-500" />
                          </div>
                          <p className="text-lg font-bold text-slate-900">
                            {companyAnalytics.facilities || 0}
                          </p>
                          <p className="text-xs text-slate-500">Facilities</p>
                        </div>
                      </div>

                      <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-100">
                        <span className="text-sm text-blue-600 font-medium group-hover:underline">
                          View Details
                        </span>
                        <ArrowRight className="h-4 w-4 text-blue-600 group-hover:translate-x-1 transition-transform" />
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              );
            })}
          </div>

          {/* Overview Comparison Table */}
          <Card className="border-0 shadow-xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-blue-600" />
                Company Comparison
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50">
                      <th className="text-left py-4 px-4 font-semibold text-slate-700">Company</th>
                      <th className="text-left py-4 px-4 font-semibold text-slate-700">Ticker</th>
                      <th className="text-left py-4 px-4 font-semibold text-slate-700">Headquarters</th>
                      <th className="text-center py-4 px-4 font-semibold text-slate-700">AI Focus</th>
                      <th className="text-center py-4 px-4 font-semibold text-slate-700">Sentiment</th>
                      <th className="text-center py-4 px-4 font-semibold text-slate-700">Outlook</th>
                      <th className="text-right py-4 px-4 font-semibold text-slate-700">Documents</th>
                    </tr>
                  </thead>
                  <tbody>
                    {companies.map((company) => {
                      const displayName =
                        COMPANY_DISPLAY_NAMES[company.ticker] || company.name.split(' ')[0];
                      const companyAnalytics = analytics[displayName] || {};
                      return (
                        <tr key={company.ticker} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="py-4 px-4">
                            <Link
                              href={`/companies/${displayName.toLowerCase()}`}
                              className="flex items-center gap-3 hover:text-blue-600"
                            >
                              <div
                                className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm font-bold"
                                style={{ backgroundColor: company.color }}
                              >
                                {displayName.charAt(0)}
                              </div>
                              <span className="font-medium">{company.name}</span>
                            </Link>
                          </td>
                          <td className="py-4 px-4">
                            <Badge variant="outline">{company.ticker}</Badge>
                          </td>
                          <td className="py-4 px-4 text-slate-600">{company.headquarters}</td>
                          <td className="py-4 px-4 text-center">
                            <Badge className="bg-purple-100 text-purple-700">
                              {companyAnalytics.ai_focus?.toFixed(0) || 0}%
                            </Badge>
                          </td>
                          <td className="py-4 px-4 text-center">
                            <Badge
                              className={
                                (companyAnalytics.sentiment || 0) >= 50
                                  ? 'bg-green-100 text-green-700'
                                  : 'bg-red-100 text-red-700'
                              }
                            >
                              {companyAnalytics.sentiment?.toFixed(0) || 0}%
                            </Badge>
                          </td>
                          <td className="py-4 px-4 text-center">
                            <div className="flex items-center justify-center gap-1">
                              {getTrendIcon(companyAnalytics.trend || 'neutral')}
                              <span className="text-sm capitalize">
                                {companyAnalytics.trend || 'neutral'}
                              </span>
                            </div>
                          </td>
                          <td className="py-4 px-4 text-right font-medium">
                            {company.document_count.toLocaleString()}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* ───────────────────── INVESTMENT ANALYSIS TAB ───────────────────── */}
      {activeTab === 'analysis' && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <Card className="border-0 shadow-xl">
              <CardContent className="p-6">
                <div className="flex items-center gap-4">
                  <div className="p-3 bg-blue-100 rounded-lg">
                    <DollarSign className="h-6 w-6 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">Total CapEx Mentions</p>
                    <p className="text-2xl font-bold">
                      {capexData.reduce((sum, c) => sum + c.count, 0).toLocaleString()}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-xl">
              <CardContent className="p-6">
                <div className="flex items-center gap-4">
                  <div className="p-3 bg-purple-100 rounded-lg">
                    <Cpu className="h-6 w-6 text-purple-600" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">AI/ML Mentions</p>
                    <p className="text-2xl font-bold">
                      {aiData.reduce((sum, c) => sum + c.ai_mentions, 0).toLocaleString()}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-xl">
              <CardContent className="p-6">
                <div className="flex items-center gap-4">
                  <div className="p-3 bg-green-100 rounded-lg">
                    <Building2 className="h-6 w-6 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">Data Center Mentions</p>
                    <p className="text-2xl font-bold">
                      {aiData
                        .reduce((sum, c) => sum + c.data_center_mentions, 0)
                        .toLocaleString()}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <DollarSign className="h-5 w-5" />
                  CapEx Mentions by Company
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={capexChartData} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                      <XAxis type="number" />
                      <YAxis dataKey="name" type="category" width={80} />
                      <Tooltip />
                      <Bar
                        dataKey="mentions"
                        radius={[0, 4, 4, 0]}
                        fill="#3B82F6"
                        onClick={(data) => setSelectedCompany(data?.name ?? null)}
                        cursor="pointer"
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Cpu className="h-5 w-5" />
                  AI & Data Center Focus
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={aiChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                      <XAxis dataKey="name" />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="AI Mentions" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Data Center" fill="#10b981" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Investment Comparison Table */}
          <Card className="border-0 shadow-xl mb-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-blue-600" />
                Investment Focus Comparison
                <span className="ml-auto text-xs font-normal text-slate-400">
                  Source: SEC Filings · NLP
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50">
                      <th className="text-left py-3 px-4 font-semibold text-slate-700">Company</th>
                      <th className="text-right py-3 px-4 font-semibold text-slate-700">CapEx Mentions</th>
                      <th className="text-right py-3 px-4 font-semibold text-slate-700">AI/ML Mentions</th>
                      <th className="text-right py-3 px-4 font-semibold text-slate-700">Data Center</th>
                      <th className="text-right py-3 px-4 font-semibold text-slate-700">Total Tech Focus</th>
                      <th className="text-center py-3 px-4 font-semibold text-slate-700">vs. Avg</th>
                    </tr>
                  </thead>
                  <tbody>
                    {capexData.map((company) => {
                      const aiInfo = aiData.find((a) => a.company === company.company);
                      const totalTech =
                        (aiInfo?.ai_mentions || 0) + (aiInfo?.data_center_mentions || 0);
                      const avgTech =
                        aiData.reduce(
                          (sum, c) => sum + c.ai_mentions + c.data_center_mentions,
                          0
                        ) / Math.max(aiData.length, 1);
                      const isAboveAvg = totalTech > avgTech;

                      return (
                        <tr
                          key={company.company}
                          className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer"
                          onClick={() =>
                            setSelectedCompany(
                              selectedCompany === company.company ? null : company.company
                            )
                          }
                        >
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <div
                                className="w-3 h-3 rounded-full"
                                style={{
                                  backgroundColor:
                                    COMPANY_COLORS[company.company] || '#94A3B8',
                                }}
                              />
                              <span className="font-medium">{company.company}</span>
                            </div>
                          </td>
                          <td className="text-right py-3 px-4">
                            {company.count.toLocaleString()}
                          </td>
                          <td className="text-right py-3 px-4">
                            {aiInfo?.ai_mentions.toLocaleString() || 0}
                          </td>
                          <td className="text-right py-3 px-4">
                            {aiInfo?.data_center_mentions.toLocaleString() || 0}
                          </td>
                          <td className="text-right py-3 px-4 font-semibold">
                            {totalTech.toLocaleString()}
                          </td>
                          <td className="text-center py-3 px-4">
                            {isAboveAvg ? (
                              <Badge className="bg-green-100 text-green-700">
                                <ArrowUpRight className="h-3 w-3 mr-1" />
                                Above Avg
                              </Badge>
                            ) : (
                              <Badge className="bg-orange-100 text-orange-700">
                                <ArrowDownRight className="h-3 w-3 mr-1" />
                                Below Avg
                              </Badge>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* CapEx Context Drill-down */}
          {selectedCapex && (
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <div
                    className="w-4 h-4 rounded-full"
                    style={{
                      backgroundColor:
                        COMPANY_COLORS[selectedCapex.company] || '#94A3B8',
                    }}
                  />
                  {selectedCapex.company} — Recent CapEx Context
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {selectedCapex.recent_context.length > 0 ? (
                    selectedCapex.recent_context.slice(0, 5).map((ctx, i) => (
                      <div key={i} className="p-3 bg-slate-50 rounded-lg text-sm">
                        <p className="text-slate-700">{ctx}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-slate-500 text-sm">
                      No recent context available. Try asking in AI Chat for detailed analysis.
                    </p>
                  )}
                </div>
                <button
                  onClick={() => setSelectedCompany(null)}
                  className="mt-4 text-sm text-slate-500 hover:text-slate-700 underline"
                >
                  Clear selection
                </button>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* ───────────────────── TREND INTELLIGENCE TAB ───────────────────── */}
      {activeTab === 'trends' && (
        <>
          {/* Market Outlook Banner */}
          {trends?.market_outlook && (
            <Card className="border-0 shadow-xl bg-gradient-to-r from-slate-900 to-slate-800 mb-8">
              <CardContent className="p-6">
                <div className="flex items-center gap-4">
                  <div className="bg-gradient-to-br from-purple-500 to-blue-600 p-3 rounded-xl shrink-0">
                    <Zap className="h-6 w-6 text-white" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-white mb-1">Market Outlook</h3>
                    <p className="text-slate-300">{trends.market_outlook}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <Card className="border-0 shadow-xl">
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-slate-500">Industry AI Focus</span>
                  <Brain className="h-5 w-5 text-purple-500" />
                </div>
                <p className="text-3xl font-bold text-slate-900">
                  {classification?.industry_average_ai_focus || 0}%
                </p>
                <p className="text-sm text-slate-500">Average across companies</p>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-xl">
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-slate-500">Anomalies Detected</span>
                  <AlertTriangle className="h-5 w-5 text-orange-500" />
                </div>
                <p className="text-3xl font-bold text-slate-900">
                  {(anomalies?.capex_anomalies?.reduce((n: number, a: any) => n + (a.anomalies?.length || 0), 0) || 0) +
                    (anomalies?.sentiment_shifts?.reduce((n: number, s: any) => n + (s.shifts?.length || 0), 0) || 0) +
                    (anomalies?.ai_investment_changes?.reduce((n: number, a: any) => n + (a.changes?.length || 0), 0) || 0)}
                </p>
                <p className="text-sm text-slate-500">Across all metrics</p>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-xl">
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-slate-500">AI Leaders</span>
                  <TrendingUp className="h-5 w-5 text-green-500" />
                </div>
                <p className="text-3xl font-bold text-slate-900">
                  {trends?.rankings?.ai_focus_growth?.length || 0}
                </p>
                <p className="text-sm text-slate-500">Companies growing AI focus</p>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-xl">
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-slate-500">Companies Analyzed</span>
                  <Building2 className="h-5 w-5 text-blue-500" />
                </div>
                <p className="text-3xl font-bold text-slate-900">
                  {trends?.companies?.length || 0}
                </p>
                <p className="text-sm text-slate-500">Full trend analysis</p>
              </CardContent>
            </Card>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Brain className="h-5 w-5 text-purple-600" />
                  AI vs Traditional Investment Focus
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={aiClassificationData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                    <XAxis type="number" domain={[0, 100]} />
                    <YAxis type="category" dataKey="company" width={80} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="ai_focus" name="AI/Data Center" stackId="a" fill="#8B5CF6" />
                    <Bar dataKey="traditional" name="Traditional" stackId="a" fill="#94A3B8" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5 text-green-600" />
                  Trend Analysis Confidence
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <RadarChart data={trendComparisonData}>
                    <PolarGrid stroke="#E2E8F0" />
                    <PolarAngleAxis dataKey="company" tick={{ fill: '#64748B', fontSize: 12 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} />
                    <Radar name="CapEx" dataKey="capex" stroke="#3B82F6" fill="#3B82F6" fillOpacity={0.3} />
                    <Radar name="AI Focus" dataKey="ai" stroke="#8B5CF6" fill="#8B5CF6" fillOpacity={0.3} />
                    <Radar name="Sentiment" dataKey="sentiment" stroke="#10B981" fill="#10B981" fillOpacity={0.3} />
                    <Legend />
                  </RadarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          {/* Company Trend Cards */}
          <div className="mb-8">
            <h2 className="text-xl font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-green-500" />
              Company Trend Analysis
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
              {trends?.companies?.map((company: TrendData) => (
                <Card key={company.company} className="border-0 shadow-lg hover:shadow-xl transition-all">
                  <CardContent className="p-5">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-semibold text-slate-900 text-sm">{company.company}</h3>
                      <Badge className={`${getOutlookBadge(company.overall_outlook)} border text-xs`}>
                        {company.overall_outlook}
                      </Badge>
                    </div>
                    <div className="space-y-3">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">CapEx</span>
                        <div className="flex items-center gap-1">
                          {getTrendIcon(company.capex_trend?.direction)}
                          <span className="text-slate-700 text-xs">
                            {company.capex_trend?.direction || 'N/A'}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">AI Focus</span>
                        <div className="flex items-center gap-1">
                          {getTrendIcon(company.ai_focus_trend?.direction)}
                          <span className="text-slate-700 text-xs">
                            {company.ai_focus_trend?.direction || 'N/A'}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Sentiment</span>
                        <div className="flex items-center gap-1">
                          {getTrendIcon(company.sentiment_trend?.direction)}
                          <span className="text-slate-700 text-xs">
                            {company.sentiment_trend?.direction || 'N/A'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>

          {/* Anomalies */}
          {anomalies &&
            (anomalies.capex_anomalies?.length > 0 ||
              anomalies.sentiment_shifts?.length > 0 ||
              anomalies.ai_investment_changes?.length > 0) && (
              <Card className="border-0 shadow-xl">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5 text-orange-500" />
                    Detected Anomalies
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-6">

                    {/* CapEx anomalies — one sub-card per anomalous period */}
                    {anomalies.capex_anomalies?.map((anomaly: any) =>
                      anomaly.anomalies?.map((item: any, i: number) => (
                        <div
                          key={`capex-${anomaly.company}-${i}`}
                          className="p-4 bg-orange-50 rounded-xl border border-orange-200"
                        >
                          <div className="flex items-start justify-between gap-3 mb-2">
                            <div>
                              <span className="font-semibold text-orange-900">
                                {anomaly.company}
                              </span>
                              <span className="ml-2 text-sm text-orange-700">· {item.period}</span>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <Badge className={`border ${item.direction === 'spike' ? 'bg-red-100 text-red-700 border-red-300' : 'bg-blue-100 text-blue-700 border-blue-300'}`}>
                                {item.direction === 'spike' ? '▲ Spike' : '▼ Drop'}
                              </Badge>
                              <Badge className="bg-orange-100 text-orange-700 border border-orange-300">
                                CapEx · {item.severity}
                              </Badge>
                            </div>
                          </div>

                          {/* Reason */}
                          {item.reason && (
                            <p className="text-sm text-orange-800 mb-3">{item.reason}</p>
                          )}

                          {/* Sources */}
                          {item.sources?.length > 0 && (
                            <div className="flex flex-wrap gap-1.5">
                              <span className="text-xs text-orange-600 font-medium mr-1">Sources:</span>
                              {item.sources.map((src: string, si: number) => (
                                <span
                                  key={si}
                                  className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 border border-orange-200"
                                >
                                  {src}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))
                    )}

                    {/* Sentiment shifts */}
                    {anomalies.sentiment_shifts?.map((shift: any) =>
                      shift.shifts?.map((item: any, i: number) => (
                        <div
                          key={`sentiment-${shift.company}-${i}`}
                          className="p-4 bg-purple-50 rounded-xl border border-purple-200"
                        >
                          <div className="flex items-start justify-between gap-3 mb-2">
                            <div>
                              <span className="font-semibold text-purple-900">{shift.company}</span>
                              <span className="ml-2 text-sm text-purple-700">
                                · {item.from_period} → {item.to_period}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <Badge className={`border ${item.direction === 'improving' ? 'bg-green-100 text-green-700 border-green-300' : 'bg-red-100 text-red-700 border-red-300'}`}>
                                {item.direction === 'improving' ? '▲ Improving' : '▼ Declining'}
                              </Badge>
                              <Badge className="bg-purple-100 text-purple-700 border border-purple-300">
                                Sentiment · {item.severity}
                              </Badge>
                            </div>
                          </div>
                          <p className="text-sm text-purple-800">
                            Sentiment score shifted from {item.from_sentiment} to {item.to_sentiment}
                            {' '}({item.change > 0 ? '+' : ''}{item.change} points) between {item.from_period} and {item.to_period}.
                          </p>
                        </div>
                      ))
                    )}

                    {/* AI investment changes */}
                    {anomalies.ai_investment_changes?.map((ai: any) =>
                      ai.changes?.map((item: any, i: number) => (
                        <div
                          key={`ai-${ai.company}-${i}`}
                          className="p-4 bg-blue-50 rounded-xl border border-blue-200"
                        >
                          <div className="flex items-start justify-between gap-3 mb-2">
                            <div>
                              <span className="font-semibold text-blue-900">{ai.company}</span>
                              <span className="ml-2 text-sm text-blue-700">
                                · {item.from_period} → {item.to_period}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <Badge className={`border ${item.direction === 'increasing' ? 'bg-green-100 text-green-700 border-green-300' : 'bg-red-100 text-red-700 border-red-300'}`}>
                                {item.direction === 'increasing' ? '▲ Rising' : '▼ Falling'}
                              </Badge>
                              <Badge className="bg-blue-100 text-blue-700 border border-blue-300">
                                AI Focus
                              </Badge>
                            </div>
                          </div>

                          {/* Reason */}
                          {item.reason && (
                            <p className="text-sm text-blue-800 mb-3">{item.reason}</p>
                          )}

                          {/* Sources */}
                          {item.sources?.length > 0 && (
                            <div className="flex flex-wrap gap-1.5">
                              <span className="text-xs text-blue-600 font-medium mr-1">Sources:</span>
                              {item.sources.map((src: string, si: number) => (
                                <span
                                  key={si}
                                  className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 border border-blue-200"
                                >
                                  {src}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))
                    )}

                  </div>
                </CardContent>
              </Card>
            )}
        </>
      )}
    </div>
  );
}
