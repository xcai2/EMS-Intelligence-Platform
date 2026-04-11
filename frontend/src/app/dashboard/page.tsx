'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { DashboardSkeleton, CardSkeleton, ChartSkeleton } from '@/components/ui/skeleton';
import { ChartDescription } from '@/components/ui/chart-description';
import { 
  FileText, 
  Building2, 
  Database,
  BarChart3,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Zap,
  Brain,
  AlertTriangle,
  Globe,
  ArrowRight,
  Sparkles,
  Activity,
  MessageSquare,
  Cpu,
  DollarSign,
} from 'lucide-react';
import { 
  PieChart, 
  Pie, 
  Cell, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Legend,
  LineChart,
  Line,
  AreaChart,
  Area,
  RadialBarChart,
  RadialBar,
} from 'recharts';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

interface AnalystQuestion {
  id: string;
  question: string;
  category: string;
  complexity: string;
  companies: string[];
}

interface EMSAIDynamic {
  company: string;
  ticker: string;
  ai_revenue_growth_pct: number;
  ai_revenue_mix_pct: number;
  recent_highlights: string[];
  investment_focus: string[];
  guidance_outlook: string;
}

interface OverviewData {
  total_documents: number;
  companies_tracked: number;
  sec_filings: number;
  earnings_documents: number;
  documents_by_company: Record<string, number>;
  documents_by_type: Record<string, number>;
}

interface AnalyticsDashboard {
  anomalies: {
    capex_anomalies_count: number;
    sentiment_shifts_count: number;
    companies_with_anomalies: string[];
  };
  trends: {
    market_outlook: string;
    companies_growing_ai: Array<{ company: string; confidence: number }>;
  };
  classification: {
    industry_average_ai_focus: number;
    most_ai_focused: string;
    most_traditional: string;
  };
  leaders: {
    industry_average: number;
    leaders: Array<{ company: string; ai_focus: number; above_average_by: number }>;
  };
}

interface SentimentData {
  comparison: Array<{
    company: string;
    sentiment_score: number;
    positive_words: number;
    negative_words: number;
    documents_analyzed: number;
  }>;
  most_positive: string;
  most_negative: string;
}

const COMPANY_COLORS: Record<string, string> = {
  'Flex': '#3B82F6',
  'Jabil': '#10B981',
  'Celestica': '#6366F1',
  'Benchmark': '#F59E0B',
  'Sanmina': '#EF4444',
  'Plexus': '#14B8A6',
};

export default function DashboardPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsDashboard | null>(null);
  const [sentiment, setSentiment] = useState<SentimentData | null>(null);
  const [classification, setClassification] = useState<any>(null);
  const [analystQuestions, setAnalystQuestions] = useState<AnalystQuestion[]>([]);
  const [emsAIDynamics, setEmsAIDynamics] = useState<EMSAIDynamic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAllData();
  }, []);

  const fetchAllData = async () => {
    try {
      setLoading(true);
      
      // First, get quick data for fast initial render
      const quickRes = await fetch(`${API_URL}/api/dashboard/quick`);
      if (quickRes.ok) {
        const quickData = await quickRes.json();
        setData({
          total_documents: quickData.stats?.total_documents || 0,
          companies_tracked: quickData.stats?.companies_tracked || 6,
          sec_filings: 0,
          earnings_documents: 0,
          documents_by_company: {},
          documents_by_type: {},
        });
        setLoading(false);
      }
      
      // Then fetch full data in parallel
      const [overviewRes, analyticsRes, sentimentRes, classificationRes, questionsRes, dynamicsRes] = await Promise.all([
        fetch(`${API_URL}/api/analysis/overview`),
        fetch(`${API_URL}/api/analytics/dashboard`),
        fetch(`${API_URL}/api/sentiment/compare`),
        fetch(`${API_URL}/api/analytics/classification`),
        fetch(`${API_URL}/api/intelligence/default-questions`),
        fetch(`${API_URL}/api/intelligence/ems-ai-dynamics`),
      ]);

      if (overviewRes.ok) setData(await overviewRes.json());
      if (analyticsRes.ok) setAnalytics(await analyticsRes.json());
      if (sentimentRes.ok) setSentiment(await sentimentRes.json());
      if (classificationRes.ok) setClassification(await classificationRes.json());
      if (questionsRes.ok) {
        const qData = await questionsRes.json();
        setAnalystQuestions(qData.questions || []);
      }
      if (dynamicsRes.ok) {
        const dData = await dynamicsRes.json();
        setEmsAIDynamics(dData.companies || []);
      }
      
      setError(null);
    } catch (err) {
      setError('Failed to connect to backend. Make sure the server is running on port 8001.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center p-6">
        <Card className="max-w-md w-full shadow-xl border-0">
          <CardContent className="p-8 text-center">
            <div className="bg-red-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
              <Database className="h-8 w-8 text-red-600" />
            </div>
            <h2 className="text-xl font-bold text-slate-900 mb-2">Connection Error</h2>
            <p className="text-slate-600 mb-6">{error}</p>
            <button
              onClick={fetchAllData}
              className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-500 text-white rounded-xl hover:shadow-lg hover:shadow-blue-500/25 transition-all font-medium"
            >
              <RefreshCw className="h-4 w-4" />
              Retry Connection
            </button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const companyChartData = data?.documents_by_company 
    ? Object.entries(data.documents_by_company).map(([name, value]) => ({
        name,
        value,
        color: COMPANY_COLORS[name] || '#64748B',
      }))
    : [];

  const typeChartData = data?.documents_by_type
    ? Object.entries(data.documents_by_type).map(([name, value]) => ({
        name: name.length > 12 ? name.substring(0, 12) + '...' : name,
        fullName: name,
        value,
      }))
    : [];

  // AI Focus data for radial bar
  const aiFocusData = classification?.companies?.map((c: any, idx: number) => ({
    name: c.company,
    ai_focus: c.overall_ai_focus_percentage,
    fill: COMPANY_COLORS[c.company] || '#64748B',
  })) || [];

  // Sentiment data for line chart
  const sentimentChartData = sentiment?.comparison?.map((c) => ({
    company: c.company,
    sentiment: Math.round(c.sentiment_score * 100),
    positive: c.positive_words,
    negative: c.negative_words,
  })) || [];

  const statsCards = [
    {
      title: 'Total Documents',
      value: data?.total_documents.toLocaleString() || '0',
      icon: FileText,
      gradient: 'from-blue-500 to-blue-600',
      shadow: 'shadow-blue-500/20',
    },
    {
      title: 'AI Focus (Avg)',
      value: `${analytics?.classification?.industry_average_ai_focus || 0}%`,
      icon: Brain,
      gradient: 'from-purple-500 to-purple-600',
      shadow: 'shadow-purple-500/20',
    },
    {
      title: 'Anomalies',
      value: ((analytics?.anomalies?.capex_anomalies_count || 0) + (analytics?.anomalies?.sentiment_shifts_count || 0)).toString(),
      icon: AlertTriangle,
      gradient: 'from-orange-500 to-orange-600',
      shadow: 'shadow-orange-500/20',
    },
    {
      title: 'Companies',
      value: data?.companies_tracked.toString() || '5',
      icon: Building2,
      gradient: 'from-emerald-500 to-emerald-600',
      shadow: 'shadow-emerald-500/20',
    },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Intelligence Overview</h1>
            <p className="text-slate-500 mt-1">Cross-company view of AI investment, sentiment, anomalies, and company signals.</p>
          </div>
          <button
            onClick={fetchAllData}
            className="flex items-center gap-2 px-4 py-2 bg-white rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition-all shadow-sm"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Market Outlook Banner */}
      {analytics?.trends?.market_outlook && (
        <Card className="border-0 shadow-xl bg-gradient-to-r from-slate-900 to-slate-800 mb-8">
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="bg-gradient-to-br from-purple-500 to-blue-600 p-3 rounded-xl">
                <Sparkles className="h-6 w-6 text-white" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-white mb-1">Market Outlook</h3>
                <p className="text-slate-300">{analytics.trends.market_outlook}</p>
              </div>
              <Link
                href="/analytics"
                className="flex items-center gap-2 px-4 py-2 bg-white/10 rounded-xl text-white hover:bg-white/20 transition-all"
              >
                View Analytics
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {statsCards.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card 
              key={stat.title} 
              className={`border-0 shadow-xl ${stat.shadow} overflow-hidden group hover:scale-[1.02] transition-transform duration-200`}
            >
              <CardContent className="p-6">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-slate-500 mb-1">{stat.title}</p>
                    <p className="text-3xl font-bold text-slate-900">{stat.value}</p>
                  </div>
                  <div className={`bg-gradient-to-br ${stat.gradient} p-3 rounded-xl shadow-lg`}>
                    <Icon className="h-6 w-6 text-white" />
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Main Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* AI Focus Comparison */}
        <Card className="border-0 shadow-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <Brain className="h-5 w-5 text-purple-600" />
              AI/Data Center Investment Focus
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={aiFocusData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis type="number" domain={[0, 100]} unit="%" />
                <YAxis type="category" dataKey="name" width={80} />
                <Tooltip 
                  formatter={(value) => [`${Number(value || 0).toFixed(1)}%`, 'AI Focus']}
                  contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 40px rgba(0,0,0,0.1)' }}
                />
                <Bar dataKey="ai_focus" radius={[0, 8, 8, 0]}>
                  {aiFocusData.map((entry: any, index: number) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="mt-4 flex items-center justify-between text-sm">
              <span className="text-slate-500">Industry Average: <strong className="text-slate-900">{analytics?.classification?.industry_average_ai_focus || 0}%</strong></span>
              <Badge className="bg-purple-100 text-purple-700">
                Leader: {analytics?.classification?.most_ai_focused || 'N/A'}
              </Badge>
            </div>
            <ChartDescription
              description="Percentage of earnings call mentions and SEC filing content focused on AI, data center, and related infrastructure investments across EMS companies."
              source="SEC Filings & Earnings Calls"
            />
          </CardContent>
        </Card>

        {/* Sentiment Analysis */}
        <Card className="border-0 shadow-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <Activity className="h-5 w-5 text-green-600" />
              Sentiment Analysis
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={sentimentChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="company" />
                <YAxis domain={[0, 100]} unit="%" />
                <Tooltip 
                  contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 40px rgba(0,0,0,0.1)' }}
                />
                <Legend />
                <Bar dataKey="sentiment" name="Sentiment Score" fill="#10B981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="mt-4 grid grid-cols-5 gap-2">
              {sentimentChartData.map((company) => (
                <div key={company.company} className="text-center">
                  <span className="text-xs text-slate-500">{company.company}</span>
                  <div className={`text-sm font-semibold ${company.sentiment >= 50 ? 'text-green-600' : 'text-red-600'}`}>
                    {company.sentiment >= 50 ? '↑' : '↓'} {company.sentiment}%
                  </div>
                </div>
              ))}
            </div>
            <ChartDescription
              description="Sentiment scores derived from NLP analysis of earnings calls and SEC filings. Higher scores indicate more positive outlook and confidence in company communications."
              source="Earnings Calls & 10-K/10-Q Analysis"
            />
          </CardContent>
        </Card>
      </div>

      {/* Secondary Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Company Distribution */}
        <Card className="border-0 shadow-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <Building2 className="h-5 w-5 text-blue-600" />
              Documents by Company
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={companyChartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={4}
                  dataKey="value"
                  animationDuration={800}
                >
                  {companyChartData.map((entry, index) => (
                    <Cell 
                      key={`cell-${index}`} 
                      fill={entry.color}
                      className="hover:opacity-80 transition-opacity cursor-pointer"
                    />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 40px rgba(0,0,0,0.1)' }} 
                />
                <Legend layout="horizontal" verticalAlign="bottom" />
              </PieChart>
            </ResponsiveContainer>
            <ChartDescription
              description="Distribution of indexed documents across the 5 tracked EMS companies. Includes SEC filings, earnings calls, press releases, and other public disclosures."
              source="ChromaDB Index"
            />
          </CardContent>
        </Card>

        {/* Document Types */}
        <Card className="border-0 shadow-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <FileText className="h-5 w-5 text-purple-600" />
              Documents by Type
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={typeChartData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis type="number" axisLine={false} tickLine={false} />
                <YAxis 
                  type="category" 
                  dataKey="name" 
                  width={90} 
                  axisLine={false} 
                  tickLine={false}
                  tick={{ fill: '#64748B', fontSize: 11 }}
                />
                <Tooltip 
                  contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 40px rgba(0,0,0,0.1)' }}
                  formatter={(value, name, props) => [value, props.payload.fullName]}
                />
                <Bar 
                  dataKey="value" 
                  fill="url(#colorGradient)" 
                  radius={[0, 8, 8, 0]}
                  animationDuration={800}
                />
                <defs>
                  <linearGradient id="colorGradient" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#6366F1" />
                    <stop offset="100%" stopColor="#8B5CF6" />
                  </linearGradient>
                </defs>
              </BarChart>
            </ResponsiveContainer>
            <ChartDescription
              description="Breakdown of document types in the knowledge base including 10-K annual reports, 10-Q quarterly filings, earnings call transcripts, and press releases."
              source="SEC EDGAR & Company IR"
            />
          </CardContent>
        </Card>
      </div>

      {/* AI Leaders & Anomalies */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* AI Leaders */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-green-600" />
              AI Investment Leaders
            </CardTitle>
          </CardHeader>
          <CardContent>
            {analytics?.leaders?.leaders?.length ? (
              <div className="space-y-3">
                {analytics.leaders.leaders.map((leader, idx) => (
                  <div key={leader.company} className="flex items-center justify-between p-3 bg-green-50 rounded-xl">
                    <div className="flex items-center gap-3">
                      <span className="w-6 h-6 rounded-full bg-green-600 text-white text-xs flex items-center justify-center font-bold">
                        {idx + 1}
                      </span>
                      <span className="font-medium text-slate-900">{leader.company}</span>
                    </div>
                    <div className="text-right">
                      <div className="font-bold text-green-700">{leader.ai_focus.toFixed(1)}%</div>
                      <div className="text-xs text-green-600">+{leader.above_average_by.toFixed(1)}% above avg</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-500 text-center py-4">No clear AI leaders identified</p>
            )}
          </CardContent>
        </Card>

        {/* Detected Anomalies */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-orange-600" />
              Detected Anomalies
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="p-4 bg-orange-50 rounded-xl border border-orange-200">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-orange-900">CapEx Anomalies</span>
                  <Badge className="bg-orange-200 text-orange-800">
                    {analytics?.anomalies?.capex_anomalies_count || 0}
                  </Badge>
                </div>
                <p className="text-sm text-orange-700">
                  {analytics?.anomalies?.companies_with_anomalies?.join(', ') || 'None detected'}
                </p>
              </div>
              <div className="p-4 bg-purple-50 rounded-xl border border-purple-200">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-purple-900">Sentiment Shifts</span>
                  <Badge className="bg-purple-200 text-purple-800">
                    {analytics?.anomalies?.sentiment_shifts_count || 0}
                  </Badge>
                </div>
                <p className="text-sm text-purple-700">
                  Significant changes in document sentiment
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Quick Links */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <Zap className="h-5 w-5 text-yellow-600" />
              Quick Actions
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <Link 
                href="/chat"
                className="flex items-center justify-between p-3 bg-blue-50 rounded-xl hover:bg-blue-100 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <Brain className="h-5 w-5 text-blue-600" />
                  <span className="font-medium text-blue-900">AI Chat</span>
                </div>
                <ArrowRight className="h-4 w-4 text-blue-600 group-hover:translate-x-1 transition-transform" />
              </Link>
              <Link 
                href="/analytics"
                className="flex items-center justify-between p-3 bg-purple-50 rounded-xl hover:bg-purple-100 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <BarChart3 className="h-5 w-5 text-purple-600" />
                  <span className="font-medium text-purple-900">Analytics</span>
                </div>
                <ArrowRight className="h-4 w-4 text-purple-600 group-hover:translate-x-1 transition-transform" />
              </Link>
              <Link 
                href="/map"
                className="flex items-center justify-between p-3 bg-green-50 rounded-xl hover:bg-green-100 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <Globe className="h-5 w-5 text-green-600" />
                  <span className="font-medium text-green-900">Facilities Map</span>
                </div>
                <ArrowRight className="h-4 w-4 text-green-600 group-hover:translate-x-1 transition-transform" />
              </Link>
              <Link 
                href="/reports"
                className="flex items-center justify-between p-3 bg-orange-50 rounded-xl hover:bg-orange-100 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-orange-600" />
                  <span className="font-medium text-orange-900">Reports</span>
                </div>
                <ArrowRight className="h-4 w-4 text-orange-600 group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Company Cards */}
      <div className="mb-8">
        <h2 className="text-xl font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <Building2 className="h-5 w-5 text-blue-500" />
          Company Overview
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          {companyChartData.map((company) => {
            const sentimentData = sentimentChartData.find(s => s.company === company.name);
            const aiData = aiFocusData.find((a: any) => a.name === company.name);
            
            return (
              <Link 
                key={company.name}
                href={`/companies/${company.name.toLowerCase()}`}
                className="block"
              >
                <Card className="border-0 shadow-lg hover:shadow-xl transition-all duration-200 group cursor-pointer overflow-hidden h-full">
                  <div 
                    className="h-1.5 w-full"
                    style={{ backgroundColor: company.color }}
                  />
                  <CardContent className="p-5">
                    <div className="flex items-center gap-3 mb-3">
                      <div 
                        className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold shadow-lg"
                        style={{ backgroundColor: company.color }}
                      >
                        {company.name.charAt(0)}
                      </div>
                      <span className="font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">
                        {company.name}
                      </span>
                    </div>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-500">Documents</span>
                        <span className="font-semibold">{company.value.toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-500">AI Focus</span>
                        <span className="font-semibold text-purple-600">{aiData?.ai_focus?.toFixed(0) || 0}%</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-500">Sentiment</span>
                        <span className={`font-semibold ${(sentimentData?.sentiment || 0) >= 50 ? 'text-green-600' : 'text-red-600'}`}>
                          {sentimentData?.sentiment || 0}%
                        </span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Analyst Questions & AI Dynamics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Default Analyst Questions */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <MessageSquare className="h-5 w-5 text-blue-600" />
              Analyst Questions
              <Badge className="ml-2 bg-blue-100 text-blue-700 text-xs">From Earnings Calls</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-500 mb-4">
              Common questions analysts ask during EMS company earnings calls. Click to explore.
            </p>
            <div className="grid grid-cols-1 gap-3">
              {analystQuestions.slice(0, 6).map((q) => (
                <Link
                  key={q.id}
                  href={`/chat?q=${encodeURIComponent(q.question)}`}
                  className="p-3 bg-slate-50 rounded-xl hover:bg-blue-50 transition-colors group"
                >
                  <div className="flex items-start gap-3">
                    <Badge variant="outline" className="text-xs shrink-0 mt-0.5">
                      {q.category}
                    </Badge>
                    <p className="text-sm text-slate-700 group-hover:text-blue-700 transition-colors">
                      {q.question}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
            <Link
              href="/chat"
              className="mt-4 flex items-center justify-center gap-2 text-blue-600 hover:text-blue-700 text-sm font-medium"
            >
              Ask Your Own Question <ArrowRight className="h-4 w-4" />
            </Link>
          </CardContent>
        </Card>

        {/* EMS AI Dynamics */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <Cpu className="h-5 w-5 text-purple-600" />
              EMS AI Dynamics
              <Badge className="ml-2 bg-purple-100 text-purple-700 text-xs">Latest Updates</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {emsAIDynamics.slice(0, 5).map((company) => (
                <div
                  key={company.company}
                  className="p-4 rounded-xl border border-slate-200 hover:border-purple-300 transition-colors"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div 
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold text-sm"
                        style={{ backgroundColor: COMPANY_COLORS[company.company] || '#64748B' }}
                      >
                        {company.company.charAt(0)}
                      </div>
                      <span className="font-semibold text-slate-900">{company.company}</span>
                      <span className="text-xs text-slate-400">{company.ticker}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge className="bg-green-100 text-green-700">
                        +{company.ai_revenue_growth_pct}% AI Growth
                      </Badge>
                      <Badge className="bg-purple-100 text-purple-700">
                        {company.ai_revenue_mix_pct}% AI Mix
                      </Badge>
                    </div>
                  </div>
                  <p className="text-sm text-slate-600 mb-2">
                    {company.recent_highlights[0]}
                  </p>
                  <div className="flex items-center gap-2 flex-wrap">
                    {company.investment_focus.slice(0, 3).map((focus, idx) => (
                      <span key={idx} className="text-xs px-2 py-1 bg-slate-100 text-slate-600 rounded-full">
                        {focus}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <Link
              href="/ai-investments"
              className="mt-4 flex items-center justify-center gap-2 text-purple-600 hover:text-purple-700 text-sm font-medium"
            >
              View Big 5 AI CapEx Tracker <ArrowRight className="h-4 w-4" />
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* Big 5 AI Investment Summary Banner */}
      <Card className="border-0 shadow-xl bg-gradient-to-r from-orange-500 to-red-600 mb-6">
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div className="bg-white/20 p-4 rounded-xl">
                <DollarSign className="h-8 w-8 text-white" />
              </div>
              <div className="text-white">
                <h3 className="text-xl font-bold mb-1">Big 5 AI CapEx 2026: $675B+</h3>
                <p className="text-orange-100">
                  AWS, Google, Microsoft, Meta, Oracle collectively investing in AI infrastructure
                </p>
              </div>
            </div>
            <Link
              href="/ai-investments"
              className="flex items-center gap-2 px-6 py-3 bg-white/20 rounded-xl text-white hover:bg-white/30 transition-all"
            >
              View Details <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
