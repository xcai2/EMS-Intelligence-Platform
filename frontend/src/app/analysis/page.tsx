'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { 
  RefreshCw, 
  TrendingUp, 
  DollarSign, 
  Cpu,
  Building2,
  ArrowUpRight,
  ArrowDownRight
} from 'lucide-react';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  LineChart,
  Line,
  Legend,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar
} from 'recharts';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

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

const COMPANY_COLORS: Record<string, string> = {
  'Flex': '#00A0E3',
  'Jabil': '#1E4D2B',
  'Celestica': '#003366',
  'Benchmark': '#B8860B',
  'Sanmina': '#C41E3A',
  'Plexus': '#0F766E',
};

export default function AnalysisPage() {
  const [capexData, setCapexData] = useState<CapExMention[]>([]);
  const [aiData, setAiData] = useState<AIInvestmentMention[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<string | null>(null);

  useEffect(() => {
    fetchAnalysisData();
  }, []);

  const fetchAnalysisData = async () => {
    setLoading(true);
    try {
      const [capexRes, aiRes] = await Promise.all([
        fetch(`${API_URL}/api/analysis/capex`),
        fetch(`${API_URL}/api/analysis/ai-investments`)
      ]);

      if (!capexRes.ok || !aiRes.ok) {
        throw new Error('Failed to fetch analysis data');
      }

      const capexResult = await capexRes.json();
      const aiResult = await aiRes.json();

      setCapexData(capexResult.mentions || []);
      setAiData(aiResult.mentions || []);
      setError(null);
    } catch (err) {
      setError('Failed to connect to backend. Make sure the server is running on port 8001.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Card className="bg-red-50 border-red-200">
          <CardContent className="p-6">
            <p className="text-red-600">{error}</p>
            <button 
              onClick={fetchAnalysisData}
              className="mt-4 text-sm text-red-600 underline"
            >
              Retry
            </button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Prepare chart data
  const capexChartData = capexData.map(item => ({
    name: item.company,
    mentions: item.count,
    fill: COMPANY_COLORS[item.company] || '#666'
  }));

  const aiChartData = aiData.map(item => ({
    name: item.company,
    'AI Mentions': item.ai_mentions,
    'Data Center': item.data_center_mentions,
  }));

  // Radar chart data for comparative analysis
  const radarData = [
    { metric: 'CapEx Focus', ...Object.fromEntries(capexData.map(c => [c.company, Math.min(c.count / 10, 100)])) },
    { metric: 'AI Investment', ...Object.fromEntries(aiData.map(c => [c.company, Math.min(c.ai_mentions / 5, 100)])) },
    { metric: 'Data Centers', ...Object.fromEntries(aiData.map(c => [c.company, Math.min(c.data_center_mentions / 5, 100)])) },
  ];

  const selectedCapex = selectedCompany ? capexData.find(c => c.company === selectedCompany) : null;

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Competitive Analysis</h1>
          <p className="text-slate-500">CapEx strategies and AI investment patterns across EMS companies</p>
        </div>
        <Button variant="outline" onClick={fetchAnalysisData}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card>
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

        <Card>
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

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-green-100 rounded-lg">
                <Building2 className="h-6 w-6 text-green-600" />
              </div>
              <div>
                <p className="text-sm text-slate-500">Data Center Mentions</p>
                <p className="text-2xl font-bold">
                  {aiData.reduce((sum, c) => sum + c.data_center_mentions, 0).toLocaleString()}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* CapEx Mentions by Company */}
        <Card>
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
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis dataKey="name" type="category" width={80} />
                  <Tooltip />
                  <Bar 
                    dataKey="mentions" 
                    radius={[0, 4, 4, 0]}
                    onClick={(data) => setSelectedCompany(data?.name ?? null)}
                    cursor="pointer"
                  >
                    {capexChartData.map((entry, index) => (
                      <Bar key={`bar-${index}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* AI vs Data Center Investments */}
        <Card>
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
                  <CartesianGrid strokeDasharray="3 3" />
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

      {/* Company Comparison Table */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Company Comparison</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4">Company</th>
                  <th className="text-right py-3 px-4">CapEx Mentions</th>
                  <th className="text-right py-3 px-4">AI/ML Mentions</th>
                  <th className="text-right py-3 px-4">Data Center</th>
                  <th className="text-right py-3 px-4">Total Tech Focus</th>
                  <th className="text-center py-3 px-4">Trend</th>
                </tr>
              </thead>
              <tbody>
                {capexData.map((company) => {
                  const aiInfo = aiData.find(a => a.company === company.company);
                  const totalTech = (aiInfo?.ai_mentions || 0) + (aiInfo?.data_center_mentions || 0);
                  const avgTech = aiData.reduce((sum, c) => sum + c.ai_mentions + c.data_center_mentions, 0) / aiData.length;
                  const isAboveAvg = totalTech > avgTech;

                  return (
                    <tr 
                      key={company.company} 
                      className="border-b hover:bg-slate-50 cursor-pointer"
                      onClick={() => setSelectedCompany(company.company)}
                    >
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <div 
                            className="w-3 h-3 rounded-full" 
                            style={{ backgroundColor: COMPANY_COLORS[company.company] }}
                          />
                          <span className="font-medium">{company.company}</span>
                        </div>
                      </td>
                      <td className="text-right py-3 px-4">{company.count.toLocaleString()}</td>
                      <td className="text-right py-3 px-4">{aiInfo?.ai_mentions.toLocaleString() || 0}</td>
                      <td className="text-right py-3 px-4">{aiInfo?.data_center_mentions.toLocaleString() || 0}</td>
                      <td className="text-right py-3 px-4 font-semibold">{totalTech.toLocaleString()}</td>
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

      {/* Selected Company Details */}
      {selectedCapex && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <div 
                className="w-4 h-4 rounded-full" 
                style={{ backgroundColor: COMPANY_COLORS[selectedCapex.company] }}
              />
              {selectedCapex.company} - Recent CapEx Context
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {selectedCapex.recent_context.length > 0 ? (
                selectedCapex.recent_context.slice(0, 5).map((context, i) => (
                  <div key={i} className="p-3 bg-slate-50 rounded-lg text-sm">
                    <p className="text-slate-700">{context}</p>
                  </div>
                ))
              ) : (
                <p className="text-slate-500">No recent context available. Try asking in chat for detailed analysis.</p>
              )}
            </div>
            <div className="mt-4">
              <Button variant="outline" onClick={() => setSelectedCompany(null)}>
                Clear Selection
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
