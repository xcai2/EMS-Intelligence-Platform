'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { 
  FileText, 
  Download, 
  FileSpreadsheet, 
  Presentation,
  File,
  Building2,
  RefreshCw,
  CheckCircle,
  XCircle,
  Eye,
  Loader2,
  Calendar,
  Filter,
  Clock,
  Zap
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

const COMPANIES = ['Flex', 'Jabil', 'Celestica', 'Benchmark', 'Sanmina', 'Plexus'];

interface ExportFormat {
  id: string;
  name: string;
  extension: string;
  available: boolean;
  description: string;
  native_pdf?: boolean;
}

export default function ReportsPage() {
  const [formats, setFormats] = useState<ExportFormat[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<string>('all');
  const [selectedFormat, setSelectedFormat] = useState<string>('excel');
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [recentExports, setRecentExports] = useState<any[]>([]);

  useEffect(() => {
    fetchFormats();
    loadRecentExports();
  }, []);

  const fetchFormats = async () => {
    try {
      const res = await fetch(`${API_URL}/api/exports/formats`);
      if (res.ok) {
        const data = await res.json();
        setFormats(data.formats);
      }
    } catch (err) {
      console.error('Failed to fetch formats:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadRecentExports = () => {
    const stored = localStorage.getItem('recentExports');
    if (stored) {
      try {
        setRecentExports(JSON.parse(stored).slice(0, 5));
      } catch {}
    }
  };

  const saveRecentExport = (company: string, format: string) => {
    const newExport = {
      company,
      format,
      timestamp: new Date().toISOString(),
    };
    const updated = [newExport, ...recentExports].slice(0, 5);
    setRecentExports(updated);
    localStorage.setItem('recentExports', JSON.stringify(updated));
  };

  const downloadReport = async (format: string, company: string) => {
    const key = `${format}-${company}`;
    setDownloading(key);
    
    try {
      let endpoint = '';
      
      if (company === 'all') {
        endpoint = `${API_URL}/api/exports/${format}/comparison/all`;
      } else {
        endpoint = `${API_URL}/api/exports/${format}/${company.toLowerCase()}`;
      }
      
      const res = await fetch(endpoint);
      
      if (!res.ok) {
        throw new Error('Export failed');
      }
      
      const blob = await res.blob();
      const contentDisposition = res.headers.get('Content-Disposition');
      let filename = `report.${format === 'excel' ? 'xlsx' : format === 'powerpoint' ? 'pptx' : 'pdf'}`;
      
      if (contentDisposition) {
        const match = contentDisposition.match(/filename=(.+)/);
        if (match) filename = match[1];
      }
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      
      saveRecentExport(company, format);
    } catch (err) {
      console.error('Download failed:', err);
      alert('Export failed. Make sure the required libraries are installed.');
    } finally {
      setDownloading(null);
    }
  };

  const openPreview = async (company: string) => {
    try {
      const endpoint = company === 'all'
        ? `${API_URL}/api/exports/preview/comparison/all`
        : `${API_URL}/api/exports/preview/${company.toLowerCase()}`;
      
      window.open(endpoint, '_blank');
    } catch (err) {
      console.error('Preview failed:', err);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getFormatIcon = (format: string) => {
    switch (format) {
      case 'excel': return <FileSpreadsheet className="h-5 w-5 text-green-600" />;
      case 'powerpoint': return <Presentation className="h-5 w-5 text-orange-600" />;
      case 'pdf': return <File className="h-5 w-5 text-red-600" />;
      default: return <FileText className="h-5 w-5 text-blue-600" />;
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
          <p className="text-slate-600 mt-4 font-medium">Loading export options...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-4">
          <div className="bg-gradient-to-br from-blue-600 to-indigo-700 p-3 rounded-xl shadow-lg shadow-blue-500/20">
            <FileText className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Reports</h1>
            <p className="text-slate-500 mt-1">Export comprehensive analysis reports</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Report Builder */}
        <div className="lg:col-span-2 space-y-6">
          {/* Company Selection */}
          <Card className="border-0 shadow-xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-blue-600" />
                Select Scope
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <button
                  onClick={() => setSelectedCompany('all')}
                  className={`p-4 rounded-xl border-2 transition-all ${
                    selectedCompany === 'all'
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-bold">
                      All
                    </div>
                    <div className="text-left">
                      <p className="font-medium">All Companies</p>
                      <p className="text-xs text-slate-500">Comparison report</p>
                    </div>
                  </div>
                </button>
                
                {COMPANIES.map((company) => (
                  <button
                    key={company}
                    onClick={() => setSelectedCompany(company)}
                    className={`p-4 rounded-xl border-2 transition-all ${
                      selectedCompany === company
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-slate-700 font-bold">
                        {company.charAt(0)}
                      </div>
                      <div className="text-left">
                        <p className="font-medium">{company}</p>
                        <p className="text-xs text-slate-500">Individual report</p>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Format Selection */}
          <Card className="border-0 shadow-xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Download className="h-5 w-5 text-green-600" />
                Select Format
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {formats.filter(f => f.id !== 'html').map((format) => (
                  <button
                    key={format.id}
                    onClick={() => setSelectedFormat(format.id)}
                    disabled={!format.available}
                    className={`p-4 rounded-xl border-2 transition-all text-left ${
                      selectedFormat === format.id
                        ? 'border-green-500 bg-green-50'
                        : format.available
                        ? 'border-slate-200 hover:border-slate-300'
                        : 'border-slate-100 bg-slate-50 opacity-50 cursor-not-allowed'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {getFormatIcon(format.id)}
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <p className="font-medium">{format.name}</p>
                          <Badge variant="outline" className="text-xs">{format.extension}</Badge>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">{format.description}</p>
                        {!format.available && (
                          <p className="text-xs text-red-500 mt-1">Library not installed</p>
                        )}
                        {format.id === 'pdf' && !format.native_pdf && format.available && (
                          <p className="text-xs text-amber-600 mt-1">HTML fallback (install WeasyPrint for native PDF)</p>
                        )}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Actions */}
          <Card className="border-0 shadow-xl bg-gradient-to-r from-blue-600 to-indigo-700">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div className="text-white">
                  <h3 className="font-semibold text-lg">
                    {selectedCompany === 'all' ? 'Industry Comparison' : `${selectedCompany} Analysis`}
                  </h3>
                  <p className="text-blue-100 text-sm">
                    Export as {selectedFormat.toUpperCase()}
                  </p>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={() => openPreview(selectedCompany)}
                    className="px-4 py-2 bg-white/20 text-white rounded-xl hover:bg-white/30 transition-all flex items-center gap-2"
                  >
                    <Eye className="h-4 w-4" />
                    Preview
                  </button>
                  <button
                    onClick={() => downloadReport(selectedFormat, selectedCompany)}
                    disabled={downloading !== null}
                    className="px-6 py-2 bg-white text-blue-600 rounded-xl hover:bg-blue-50 transition-all flex items-center gap-2 font-medium disabled:opacity-50"
                  >
                    {downloading === `${selectedFormat}-${selectedCompany}` ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4" />
                    )}
                    Download
                  </button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Quick Export */}
          <Card className="border-0 shadow-xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-yellow-500" />
                Quick Export
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {COMPANIES.slice(0, 3).map((company) => (
                <div key={company} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <span className="font-medium">{company}</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => downloadReport('excel', company)}
                      disabled={downloading !== null}
                      className="p-2 bg-green-100 text-green-600 rounded-lg hover:bg-green-200 transition-colors"
                      title="Download Excel"
                    >
                      <FileSpreadsheet className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => downloadReport('powerpoint', company)}
                      disabled={downloading !== null}
                      className="p-2 bg-orange-100 text-orange-600 rounded-lg hover:bg-orange-200 transition-colors"
                      title="Download PowerPoint"
                    >
                      <Presentation className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
              <button
                onClick={() => downloadReport('excel', 'all')}
                disabled={downloading !== null}
                className="w-full p-3 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition-colors font-medium"
              >
                Download Full Comparison
              </button>
            </CardContent>
          </Card>

          {/* Recent Exports */}
          <Card className="border-0 shadow-xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5 text-slate-500" />
                Recent Exports
              </CardTitle>
            </CardHeader>
            <CardContent>
              {recentExports.length > 0 ? (
                <div className="space-y-3">
                  {recentExports.map((exp, idx) => (
                    <div key={idx} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        {getFormatIcon(exp.format)}
                        <div>
                          <p className="font-medium text-sm">
                            {exp.company === 'all' ? 'Comparison' : exp.company}
                          </p>
                          <p className="text-xs text-slate-500">{formatDate(exp.timestamp)}</p>
                        </div>
                      </div>
                      <button
                        onClick={() => downloadReport(exp.format, exp.company)}
                        disabled={downloading !== null}
                        className="p-2 text-slate-400 hover:text-blue-600 transition-colors"
                      >
                        <Download className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500 text-center py-4">
                  No recent exports
                </p>
              )}
            </CardContent>
          </Card>

          {/* Format Status */}
          <Card className="border-0 shadow-xl">
            <CardHeader>
              <CardTitle>Library Status</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {formats.filter(f => f.id !== 'html').map((format) => (
                <div key={format.id} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {getFormatIcon(format.id)}
                    <span className="text-sm">{format.name}</span>
                  </div>
                  {format.available ? (
                    <CheckCircle className="h-4 w-4 text-green-500" />
                  ) : (
                    <XCircle className="h-4 w-4 text-red-500" />
                  )}
                </div>
              ))}
              <div className="mt-4 p-3 bg-blue-50 rounded-lg">
                <p className="text-xs text-blue-700">
                  Install missing libraries:
                </p>
                <pre className="mt-1 text-xs bg-white p-2 rounded overflow-x-auto">
                  pip install openpyxl python-pptx weasyprint
                </pre>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
