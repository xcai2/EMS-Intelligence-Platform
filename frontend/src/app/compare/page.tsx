'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { 
  BarChart3, 
  Brain,
  Activity,
  Globe,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus,
  ArrowRight,
  Check
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

const COMPANIES = ['Flex', 'Jabil', 'Celestica', 'Benchmark', 'Sanmina', 'Plexus'];

const COMPANY_COLORS: Record<string, string> = {
  'Flex': '#3B82F6',
  'Jabil': '#10B981',
  'Celestica': '#6366F1',
  'Benchmark': '#F59E0B',
  'Sanmina': '#EF4444',
  'Plexus': '#14B8A6',
};

export default function ComparePage() {
  const [selectedCompanies, setSelectedCompanies] = useState<string[]>(['Flex', 'Jabil']);
  const [classification, setClassification] = useState<any>(null);
  const [sentiment, setSentiment] = useState<any>(null);
  const [trends, setTrends] = useState<any>(null);
  const [geographic, setGeographic] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchComparisonData();
  }, []);

  const fetchComparisonData = async () => {
    setLoading(true);
    try {
      const [classRes, sentRes, trendsRes, geoRes] = await Promise.all([
        fetch(`${API_URL}/api/analytics/classification`),
        fetch(`${API_URL}/api/sentiment/compare`),
        fetch(`${API_URL}/api/analytics/trends`),
        fetch(`${API_URL}/api/geographic/compare`),
      ]);

      if (classRes.ok) setClassification(await classRes.json());
      if (sentRes.ok) setSentiment(await sentRes.json());
      if (trendsRes.ok) setTrends(await trendsRes.json());
      if (geoRes.ok) setGeographic(await geoRes.json());
    } catch (err) {
      console.error('Failed to fetch comparison data:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleCompany = (company: string) => {
    if (selectedCompanies.includes(company)) {
      if (selectedCompanies.length > 1) {
        setSelectedCompanies(selectedCompanies.filter(c => c !== company));
      }
    } else {
      setSelectedCompanies([...selectedCompanies, company]);
    }
  };

  const getTrendIcon = (direction: string) => {
    if (direction === 'increasing') return <TrendingUp className="h-4 w-4 text-green-500" />;
    if (direction === 'decreasing') return <TrendingDown className="h-4 w-4 text-red-500" />;
    return <Minus className="h-4 w-4 text-gray-400" />;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
          <p className="text-slate-600 mt-4 font-medium">Loading comparison data...</p>
        </div>
      </div>
    );
  }

  // Prepare filtered data based on selected companies
  const filteredClassification = classification?.companies?.filter((c: any) => 
    selectedCompanies.includes(c.company)
  ) || [];

  const filteredSentiment = sentiment?.companies?.filter((c: any) => 
    selectedCompanies.includes(c.company)
  ) || [];

  const filteredTrends = trends?.companies?.filter((c: any) => 
    selectedCompanies.includes(c.company)
  ) || [];

  const filteredGeographic = geographic?.companies?.filter((c: any) => 
    selectedCompanies.includes(c.company)
  ) || [];

  // Chart data
  const aiComparisonData = filteredClassification.map((c: any) => ({
    company: c.company,
    ai_focus: c.overall_ai_focus_percentage,
    traditional: 100 - c.overall_ai_focus_percentage,
    fill: COMPANY_COLORS[c.company],
  }));

  const sentimentComparisonData = filteredSentiment.map((c: any) => ({
    company: c.company,
    sentiment: Math.round(c.sentiment_score * 100),
    positive: c.positive_count,
    negative: c.negative_count,
  }));

  const radarData = [
    { metric: 'AI Focus', ...Object.fromEntries(filteredClassification.map((c: any) => [c.company, c.overall_ai_focus_percentage])) },
    { metric: 'Sentiment', ...Object.fromEntries(filteredSentiment.map((c: any) => [c.company, c.sentiment_score * 100])) },
    { metric: 'Facilities', ...Object.fromEntries(filteredGeographic.map((c: any) => [c.company, c.total_facilities * 10])) },
  ];

  const regionalData = filteredGeographic.map((c: any) => ({
    company: c.company,
    Americas: c.regional_distribution?.Americas || 0,
    EMEA: c.regional_distribution?.EMEA || 0,
    APAC: c.regional_distribution?.APAC || 0,
  }));

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="bg-gradient-to-br from-purple-500 to-blue-600 p-3 rounded-xl shadow-lg shadow-purple-500/20">
              <BarChart3 className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-slate-900">Company Comparison</h1>
              <p className="text-slate-500 mt-1">Side-by-side analysis of selected companies</p>
            </div>
          </div>
          <button
            onClick={fetchComparisonData}
            className="flex items-center gap-2 px-4 py-2 bg-white rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all shadow-sm"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Company Selector */}
      <Card className="border-0 shadow-xl mb-8">
        <CardHeader>
          <CardTitle>Select Companies to Compare</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            {COMPANIES.map((company) => {
              const isSelected = selectedCompanies.includes(company);
              return (
                <button
                  key={company}
                  onClick={() => toggleCompany(company)}
                  className={`flex items-center gap-2 px-4 py-3 rounded-xl font-medium transition-all ${
                    isSelected
                      ? 'text-white shadow-lg'
                      : 'bg-white text-slate-600 border border-slate-200 hover:border-slate-300'
                  }`}
                  style={{
                    backgroundColor: isSelected ? COMPANY_COLORS[company] : undefined,
                  }}
                >
                  {isSelected && <Check className="h-4 w-4" />}
                  {company}
                </button>
              );
            })}
          </div>
          <p className="text-sm text-slate-500 mt-3">
            Selected: {selectedCompanies.length} companies
          </p>
        </CardContent>
      </Card>

      {/* Comparison Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* AI Focus Comparison */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Brain className="h-5 w-5 text-purple-600" />
              AI Investment Focus
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={aiComparisonData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="company" />
                <YAxis domain={[0, 100]} unit="%" />
                <Tooltip />
                <Legend />
                <Bar dataKey="ai_focus" name="AI/Data Center" stackId="a" fill="#8B5CF6" />
                <Bar dataKey="traditional" name="Traditional" stackId="a" fill="#94A3B8" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Sentiment Comparison */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-green-600" />
              Sentiment Analysis
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={sentimentComparisonData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="company" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="sentiment" name="Sentiment Score" fill="#10B981" />
                <Bar dataKey="positive" name="Positive Count" fill="#3B82F6" />
                <Bar dataKey="negative" name="Negative Count" fill="#EF4444" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Radar & Regional Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Radar Comparison */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-blue-600" />
              Multi-Metric Comparison
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="#E2E8F0" />
                <PolarAngleAxis dataKey="metric" tick={{ fill: '#64748B', fontSize: 12 }} />
                <PolarRadiusAxis angle={30} domain={[0, 100]} />
                {selectedCompanies.map((company) => (
                  <Radar
                    key={company}
                    name={company}
                    dataKey={company}
                    stroke={COMPANY_COLORS[company]}
                    fill={COMPANY_COLORS[company]}
                    fillOpacity={0.2}
                  />
                ))}
                <Legend />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Regional Distribution */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-green-600" />
              Regional Distribution
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={regionalData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="company" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="Americas" fill="#3B82F6" />
                <Bar dataKey="EMEA" fill="#8B5CF6" />
                <Bar dataKey="APAC" fill="#10B981" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Detailed Comparison Table */}
      <Card className="border-0 shadow-xl">
        <CardHeader>
          <CardTitle>Detailed Comparison</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left py-4 px-4 font-semibold text-slate-700">Metric</th>
                  {selectedCompanies.map((company) => (
                    <th key={company} className="text-center py-4 px-4 font-semibold" style={{ color: COMPANY_COLORS[company] }}>
                      {company}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-slate-100">
                  <td className="py-4 px-4 text-slate-600">AI Focus %</td>
                  {selectedCompanies.map((company) => {
                    const data = filteredClassification.find((c: any) => c.company === company);
                    return (
                      <td key={company} className="text-center py-4 px-4 font-medium">
                        {data?.overall_ai_focus_percentage?.toFixed(1) || 0}%
                      </td>
                    );
                  })}
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-4 px-4 text-slate-600">Sentiment Score</td>
                  {selectedCompanies.map((company) => {
                    const data = filteredSentiment.find((c: any) => c.company === company);
                    const score = (data?.sentiment_score || 0) * 100;
                    return (
                      <td key={company} className="text-center py-4 px-4">
                        <span className={`font-medium ${score >= 50 ? 'text-green-600' : 'text-red-600'}`}>
                          {score.toFixed(0)}%
                        </span>
                      </td>
                    );
                  })}
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-4 px-4 text-slate-600">Total Facilities</td>
                  {selectedCompanies.map((company) => {
                    const data = filteredGeographic.find((c: any) => c.company === company);
                    return (
                      <td key={company} className="text-center py-4 px-4 font-medium">
                        {data?.total_facilities || 0}
                      </td>
                    );
                  })}
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-4 px-4 text-slate-600">Primary Region</td>
                  {selectedCompanies.map((company) => {
                    const data = filteredGeographic.find((c: any) => c.company === company);
                    return (
                      <td key={company} className="text-center py-4 px-4">
                        <Badge variant="outline">{data?.primary_region || 'N/A'}</Badge>
                      </td>
                    );
                  })}
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-4 px-4 text-slate-600">CapEx Trend</td>
                  {selectedCompanies.map((company) => {
                    const data = filteredTrends.find((c: any) => c.company === company);
                    return (
                      <td key={company} className="text-center py-4 px-4">
                        <div className="flex items-center justify-center gap-1">
                          {getTrendIcon(data?.capex_trend?.direction)}
                          <span className="text-sm">{data?.capex_trend?.direction || 'N/A'}</span>
                        </div>
                      </td>
                    );
                  })}
                </tr>
                <tr>
                  <td className="py-4 px-4 text-slate-600">Overall Outlook</td>
                  {selectedCompanies.map((company) => {
                    const data = filteredTrends.find((c: any) => c.company === company);
                    const outlook = data?.overall_outlook || 'neutral';
                    return (
                      <td key={company} className="text-center py-4 px-4">
                        <Badge className={
                          outlook === 'positive' ? 'bg-green-100 text-green-700' :
                          outlook === 'cautious' ? 'bg-red-100 text-red-700' :
                          'bg-gray-100 text-gray-700'
                        }>
                          {outlook}
                        </Badge>
                      </td>
                    );
                  })}
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
