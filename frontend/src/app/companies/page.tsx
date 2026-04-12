'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { 
  Building2, 
  MapPin, 
  Calendar,
  FileText,
  ExternalLink,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Brain,
  Activity,
  ArrowRight,
  Globe,
  Minus
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

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

const COMPANY_DISPLAY_NAMES: Record<string, string> = {
  'FLEX': 'Flex',
  'JBL': 'Jabil',
  'CLS': 'Celestica',
  'BHE': 'Benchmark',
  'SANM': 'Sanmina',
  'PLXS': 'Plexus',
};

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [analytics, setAnalytics] = useState<Record<string, AnalyticsData>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [companiesRes, classRes, sentimentRes, trendsRes, geoRes] = await Promise.all([
        fetch(`${API_URL}/api/companies`),
        fetch(`${API_URL}/api/analytics/classification`),
        fetch(`${API_URL}/api/sentiment/compare`),
        fetch(`${API_URL}/api/analytics/trends`),
        fetch(`${API_URL}/api/geographic/compare`),
      ]);

      if (companiesRes.ok) {
        const result = await companiesRes.json();
        setCompanies(result.companies);
      }

      // Build analytics map
      const analyticsMap: Record<string, AnalyticsData> = {};
      
      if (classRes.ok) {
        const data = await classRes.json();
        data.companies?.forEach((c: any) => {
          analyticsMap[c.company] = {
            ...analyticsMap[c.company],
            company: c.company,
            ai_focus: c.overall_ai_focus_percentage || 0,
          };
        });
      }
      
      if (sentimentRes.ok) {
        const data = await sentimentRes.json();
        data.companies?.forEach((c: any) => {
          if (analyticsMap[c.company]) {
            analyticsMap[c.company].sentiment = (c.sentiment_score || 0) * 100;
          }
        });
      }
      
      if (trendsRes.ok) {
        const data = await trendsRes.json();
        data.companies?.forEach((c: any) => {
          if (analyticsMap[c.company]) {
            analyticsMap[c.company].trend = c.overall_outlook || 'neutral';
          }
        });
      }
      
      if (geoRes.ok) {
        const data = await geoRes.json();
        data.companies?.forEach((c: any) => {
          if (analyticsMap[c.company]) {
            analyticsMap[c.company].facilities = c.total_facilities || 0;
          }
        });
      }
      
      setAnalytics(analyticsMap);
      setError(null);
    } catch (err) {
      setError('Failed to connect to backend. Make sure the server is running on port 8001.');
    } finally {
      setLoading(false);
    }
  };

  const getTrendIcon = (trend: string) => {
    if (trend === 'positive') return <TrendingUp className="h-4 w-4 text-green-500" />;
    if (trend === 'cautious') return <TrendingDown className="h-4 w-4 text-red-500" />;
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-3 rounded-xl shadow-lg shadow-blue-500/20">
              <Building2 className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-slate-900">Companies</h1>
              <p className="text-slate-500 mt-1">Electronics Manufacturing Services companies we track</p>
            </div>
          </div>
          <button
            onClick={fetchData}
            className="flex items-center gap-2 px-4 py-2 bg-white rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all shadow-sm"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Company Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {companies.map((company) => {
          const displayName = COMPANY_DISPLAY_NAMES[company.ticker] || company.name.split(' ')[0];
          const companyAnalytics = analytics[displayName] || {};
          
          return (
            <Link 
              key={company.ticker}
              href={`/companies/${displayName.toLowerCase()}`}
              className="block"
            >
              <Card className="border-0 shadow-xl hover:shadow-2xl transition-all duration-300 group cursor-pointer overflow-hidden h-full">
                <div 
                  className="h-2 w-full"
                  style={{ backgroundColor: company.color }}
                />
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
                        <Badge variant="outline" className="mt-1">{company.ticker}</Badge>
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

                  {/* Analytics Preview */}
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

      {/* Comparison Table */}
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
                  const displayName = COMPANY_DISPLAY_NAMES[company.ticker] || company.name.split(' ')[0];
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
                        <Badge className={(companyAnalytics.sentiment || 0) >= 50 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}>
                          {companyAnalytics.sentiment?.toFixed(0) || 0}%
                        </Badge>
                      </td>
                      <td className="py-4 px-4 text-center">
                        <div className="flex items-center justify-center gap-1">
                          {getTrendIcon(companyAnalytics.trend || 'neutral')}
                          <span className="text-sm capitalize">{companyAnalytics.trend || 'neutral'}</span>
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
    </div>
  );
}
