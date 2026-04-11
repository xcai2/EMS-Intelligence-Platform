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
  MapPin,
  FileText,
  ArrowLeft,
  RefreshCw,
  Globe,
  AlertTriangle,
  BarChart3,
  Minus,
  DollarSign,
  Newspaper,
  Factory,
  Briefcase,
  Lightbulb,
  Users,
  Cloud
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

type TabType = 'overview' | 'filings' | 'financials' | 'ai' | 'capex' | 'geographic' | 'news' | 'patents' | 'hiring' | 'ocp';

export default function CompanyDetailPage() {
  const params = useParams();
  const company = (params.company as string)?.charAt(0).toUpperCase() + (params.company as string)?.slice(1);
  const companyKey = params.company as string;
  
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [overview, setOverview] = useState<any>(null);
  const [filings, setFilings] = useState<any>(null);
  const [financials, setFinancials] = useState<any>(null);
  const [aiAnalysis, setAiAnalysis] = useState<any>(null);
  const [capexData, setCapexData] = useState<any>(null);
  const [geographic, setGeographic] = useState<any>(null);
  const [news, setNews] = useState<any>(null);
  const [patents, setPatents] = useState<any>(null);
  const [hiring, setHiring] = useState<any>(null);
  const [ocp, setOcp] = useState<any>(null);
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
        case 'ai':
          if (!aiAnalysis) {
            const res = await fetch(`${API_URL}/api/company/${company}/ai-analysis`);
            if (res.ok) setAiAnalysis(await res.json());
          }
          break;
        case 'capex':
          if (!capexData) {
            const res = await fetch(`${API_URL}/api/company/${company}/capex`);
            if (res.ok) setCapexData(await res.json());
          }
          break;
        case 'geographic':
          if (!geographic) {
            const res = await fetch(`${API_URL}/api/company/${company}/geographic`);
            if (res.ok) setGeographic(await res.json());
          }
          break;
        case 'news':
          if (!news) {
            const res = await fetch(`${API_URL}/api/company/${company}/news`);
            if (res.ok) setNews(await res.json());
          }
          break;
        case 'patents':
          if (!patents) {
            const res = await fetch(`${API_URL}/api/patents/${company}`);
            if (res.ok) setPatents(await res.json());
          }
          break;
        case 'hiring':
          if (!hiring) {
            const res = await fetch(`${API_URL}/api/jobs/${company}`);
            if (res.ok) setHiring(await res.json());
          }
          break;
        case 'ocp':
          if (!ocp) {
            const res = await fetch(`${API_URL}/api/ocp/${company}`);
            if (res.ok) setOcp(await res.json());
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
    { id: 'ai', label: 'AI Analysis', icon: Brain },
    { id: 'capex', label: 'CapEx', icon: BarChart3 },
    { id: 'geographic', label: 'Geographic', icon: Globe },
    { id: 'news', label: 'News', icon: Newspaper },
    { id: 'patents', label: 'Patents', icon: Lightbulb },
    { id: 'hiring', label: 'Hiring', icon: Users },
    { id: 'ocp', label: 'Open Compute', icon: Cloud },
  ];

  // Investment breakdown for chart
  const investmentData = aiAnalysis?.investment_breakdown ? [
    { name: 'AI/Data Center', value: aiAnalysis.investment_breakdown.ai_datacenter?.count || 0, fill: '#8B5CF6' },
    { name: 'Traditional', value: aiAnalysis.investment_breakdown.traditional?.count || 0, fill: '#94A3B8' },
    { name: 'Mixed', value: aiAnalysis.investment_breakdown.mixed?.count || 0, fill: '#F59E0B' },
  ] : [];

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
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5 text-green-600" />
                  Trend Analysis
                </CardTitle>
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
                <CardTitle className="flex items-center gap-2">
                  <Building2 className="h-5 w-5 text-blue-600" />
                  Company Information
                </CardTitle>
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
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-orange-600" />
                Recent Filings
              </CardTitle>
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

        {activeTab === 'ai' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Brain className="h-5 w-5 text-purple-600" />
                  AI Investment Focus
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center mb-4">
                  <p className="text-4xl font-bold text-purple-600">
                    {aiAnalysis?.ai_focus_percentage?.toFixed(1) || 0}%
                  </p>
                  <p className="text-slate-500">{aiAnalysis?.investment_focus || 'N/A'}</p>
                </div>
                {investmentData.length > 0 && (
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie data={investmentData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} dataKey="value">
                        {investmentData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.fill} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle>AI Mentions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3 max-h-80 overflow-y-auto">
                  {aiAnalysis?.sample_ai_mentions?.map((mention: any, idx: number) => (
                    <div key={idx} className="p-3 bg-purple-50 rounded-lg">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge variant="outline">{mention.source}</Badge>
                        <span className="text-xs text-slate-500">{mention.fiscal_year}</span>
                      </div>
                      <p className="text-sm text-slate-600 line-clamp-2">{mention.preview}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {activeTab === 'capex' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-orange-600" />
                  CapEx Breakdown
                </CardTitle>
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
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-red-600" />
                  CapEx Anomalies
                </CardTitle>
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

        {activeTab === 'geographic' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Globe className="h-5 w-5 text-blue-600" />
                  Regional Distribution
                </CardTitle>
              </CardHeader>
              <CardContent>
                {geographic?.regional_distribution && (
                  <div className="space-y-4">
                    {Object.entries(geographic.regional_distribution).map(([region, count]) => (
                      <div key={region}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium">{region}</span>
                          <span className="text-slate-500">{count as number} facilities</span>
                        </div>
                        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-blue-500 rounded-full"
                            style={{ width: `${(geographic.regional_percentages?.[region] || 0)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Factory className="h-5 w-5 text-green-600" />
                  Facilities
                </CardTitle>
              </CardHeader>
              <CardContent>
                {geographic?.headquarters && (
                  <div className="mb-4 p-4 bg-amber-50 rounded-xl border border-amber-200">
                    <div className="flex items-center gap-2 mb-1">
                      <Briefcase className="h-4 w-4 text-amber-600" />
                      <span className="font-medium text-amber-900">Headquarters</span>
                    </div>
                    <p className="text-amber-800">{geographic.headquarters.city}, {geographic.headquarters.country}</p>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2 max-h-60 overflow-y-auto">
                  {geographic?.facilities?.map((facility: any, idx: number) => (
                    <div key={idx} className="p-3 bg-slate-50 rounded-lg">
                      <p className="font-medium text-sm">{facility.city}</p>
                      <p className="text-xs text-slate-500">{facility.country}</p>
                      <Badge variant="outline" className="mt-1 text-xs">{facility.type}</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {activeTab === 'news' && (
          <Card className="border-0 shadow-xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Newspaper className="h-5 w-5 text-blue-600" />
                Recent News & Press Releases
              </CardTitle>
            </CardHeader>
            <CardContent>
              {news?.news?.length > 0 ? (
                <div className="space-y-4">
                  {news.news.map((item: any, idx: number) => (
                    <div key={idx} className="p-4 bg-slate-50 rounded-xl">
                      <div className="flex items-center gap-3 mb-2">
                        <Badge>{item.filing_type}</Badge>
                        <span className="text-sm text-slate-500">{item.fiscal_year}</span>
                      </div>
                      <p className="text-sm text-slate-600">{item.preview}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 text-center py-8">Loading news...</p>
              )}
            </CardContent>
          </Card>
        )}

        {activeTab === 'patents' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Lightbulb className="h-5 w-5 text-yellow-500" />
                  Patent Activity
                </CardTitle>
              </CardHeader>
              <CardContent>
                {patents ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-gradient-to-r from-yellow-50 to-amber-50 rounded-xl">
                      <div>
                        <p className="text-sm text-slate-500">Total Patents Found</p>
                        <p className="text-3xl font-bold text-yellow-600">{patents.total_patents || 0}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-slate-500">Innovation Score</p>
                        <p className="text-3xl font-bold text-amber-600">{patents.innovation_score?.innovation_score || 0}</p>
                      </div>
                    </div>
                    {patents.innovation_score?.focus_areas?.length > 0 && (
                      <div>
                        <p className="text-sm font-medium text-slate-700 mb-2">Focus Areas</p>
                        <div className="flex flex-wrap gap-2">
                          {patents.innovation_score.focus_areas.map((area: string, idx: number) => (
                            <Badge key={idx} className="bg-purple-100 text-purple-700">{area}</Badge>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className="border-t pt-4">
                      <p className="text-sm font-medium text-slate-700 mb-2">By Category</p>
                      <div className="space-y-2">
                        {patents.by_category && Object.entries(patents.by_category).map(([cat, data]: [string, any]) => (
                          <div key={cat} className="flex justify-between items-center p-2 bg-slate-50 rounded">
                            <span className="text-sm capitalize">{cat.replace(/_/g, ' ')}</span>
                            <Badge variant="outline">{data.count} patents</Badge>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-slate-500 text-center py-8">Loading patents...</p>
                )}
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle>Recent Patent Filings</CardTitle>
              </CardHeader>
              <CardContent>
                {patents?.patents?.length > 0 ? (
                  <div className="space-y-3 max-h-96 overflow-y-auto">
                    {patents.patents.slice(0, 10).map((patent: any, idx: number) => (
                      <a
                        key={idx}
                        href={patent.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block p-3 bg-slate-50 rounded-xl hover:bg-slate-100 transition-colors"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1">
                            <p className="font-medium text-sm text-blue-600 hover:underline line-clamp-2">{patent.title}</p>
                            <p className="text-xs text-slate-500 mt-1 line-clamp-2">{patent.snippet}</p>
                          </div>
                          <Badge variant="outline" className="text-xs shrink-0 capitalize">
                            {patent.category?.replace(/_/g, ' ')}
                          </Badge>
                        </div>
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-500 text-center py-8">No recent patents found</p>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {activeTab === 'hiring' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5 text-green-500" />
                  Hiring Activity
                </CardTitle>
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
                <CardTitle>Current Job Openings</CardTitle>
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

        {activeTab === 'ocp' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Cloud className="h-5 w-5 text-sky-500" />
                  Open Compute Project Involvement
                </CardTitle>
              </CardHeader>
              <CardContent>
                {ocp ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-gradient-to-r from-sky-50 to-blue-50 rounded-xl">
                      <div>
                        <p className="text-sm text-slate-500">Member Status</p>
                        <p className="text-xl font-bold text-sky-600">{ocp.member_status || 'Unknown'}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-slate-500">Engagement Score</p>
                        <p className="text-3xl font-bold text-blue-600">{ocp.engagement_score?.score || 0}</p>
                      </div>
                    </div>
                    
                    <div className="p-3 bg-slate-50 rounded-xl">
                      <p className="text-sm font-medium text-slate-700 mb-2">Engagement Level</p>
                      <Badge className={`${
                        ocp.engagement_score?.level === 'High' ? 'bg-green-100 text-green-700' :
                        ocp.engagement_score?.level === 'Medium' ? 'bg-yellow-100 text-yellow-700' :
                        'bg-slate-100 text-slate-700'
                      }`}>
                        {ocp.engagement_score?.level || 'Unknown'}
                      </Badge>
                    </div>

                    {ocp.focus_areas?.length > 0 && (
                      <div className="border-t pt-4">
                        <p className="text-sm font-medium text-slate-700 mb-2">Focus Areas</p>
                        <div className="flex flex-wrap gap-2">
                          {ocp.focus_areas.map((area: string, idx: number) => (
                            <Badge key={idx} variant="outline" className="bg-sky-50 text-sky-700">
                              {area}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}

                    {ocp.ocp_categories?.length > 0 && (
                      <div className="border-t pt-4">
                        <p className="text-sm font-medium text-slate-700 mb-2">Active Categories</p>
                        <div className="space-y-2">
                          {ocp.ocp_categories.map((cat: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center p-2 bg-slate-50 rounded">
                              <span className="text-sm">{cat.name}</span>
                              <Badge className={`${
                                cat.relevance === 'high' ? 'bg-green-100 text-green-700' :
                                'bg-blue-100 text-blue-700'
                              }`}>
                                {cat.relevance}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-slate-500 text-center py-8">Loading OCP data...</p>
                )}
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle>Known Contributions</CardTitle>
              </CardHeader>
              <CardContent>
                {ocp?.known_contributions?.length > 0 ? (
                  <div className="space-y-3">
                    {ocp.known_contributions.map((contribution: string, idx: number) => (
                      <div key={idx} className="p-3 bg-gradient-to-r from-sky-50 to-blue-50 rounded-xl flex items-start gap-3">
                        <div className="w-6 h-6 rounded-full bg-sky-100 flex items-center justify-center text-sky-600 text-xs font-bold">
                          {idx + 1}
                        </div>
                        <p className="text-sm text-slate-700">{contribution}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-500 text-center py-8">No specific contributions documented</p>
                )}

                {ocp?.recent_news?.length > 0 && (
                  <div className="mt-6 border-t pt-4">
                    <p className="text-sm font-medium text-slate-700 mb-3">Recent OCP News</p>
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {ocp.recent_news.slice(0, 5).map((news: any, idx: number) => (
                        <a
                          key={idx}
                          href={news.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block p-2 bg-slate-50 rounded hover:bg-slate-100 transition-colors"
                        >
                          <p className="text-sm text-blue-600 hover:underline line-clamp-2">{news.title}</p>
                          <p className="text-xs text-slate-500 mt-1 line-clamp-1">{news.description}</p>
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
