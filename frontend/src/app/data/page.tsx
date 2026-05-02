'use client';

import { useState, useEffect } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

interface SchedulerJob {
  id: string;
  name: string;
  trigger: string;
  next_run: string | null;
}

interface IngestionStatus {
  scheduler: {
    running: boolean;
    jobs: SchedulerJob[];
  };
  downloads: {
    total_downloaded: number;
    by_company: Record<string, number>;
    by_form: Record<string, number>;
  };
  raw_files: {
    total: number;
    by_company: Record<string, number>;
  };
}

interface Filing {
  ticker: string;
  company: string;
  form: string;
  filing_date: string;
  description: string;
  already_downloaded: boolean;
}


const COMPANY_FILE_COUNTS = [
  { name: 'Flex', ticker: 'FLEX' },
  { name: 'Jabil', ticker: 'JBL' },
  { name: 'Celestica', ticker: 'CLS' },
  { name: 'Benchmark', ticker: 'BHE' },
  { name: 'Plexus', ticker: 'PLXS' },
  { name: 'Sanmina', ticker: 'SANM' },
];

export default function DataManagementPage() {
  const [status, setStatus] = useState<IngestionStatus | null>(null);
  const [filings, setFilings] = useState<Record<string, Filing[]>>({});
  const [loading, setLoading] = useState(true);
  const [checkingFilings, setCheckingFilings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const pendingFilings = Object.entries(filings).flatMap(([ticker, tickerFilings]) =>
    tickerFilings
      .filter((filing) => !filing.already_downloaded)
      .map((filing) => ({ ...filing, ticker }))
  );
  const pendingToShow = pendingFilings.slice(0, 15);
  const pendingTypes = Array.from(new Set(pendingFilings.map((filing) => filing.form))).sort();
  const companiesWithDownloads = Object.keys(status?.downloads.by_company ?? {});
  const companyNameByTicker = Object.fromEntries(
    COMPANY_FILE_COUNTS.map((company) => [company.ticker, company.name])
  ) as Record<string, string>;

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statusRes] = await Promise.all([
        fetch(`${API_URL}/api/ingestion/status`),
      ]);

      if (statusRes.ok) {
        setStatus(await statusRes.json());
      }
      setError(null);
    } catch (err) {
      setError('Failed to connect to backend');
    } finally {
      setLoading(false);
    }
  };

  const checkForFilings = async () => {
    setCheckingFilings(true);
    setMessage(null);
    try {
      // First get available filings
      const filingsRes = await fetch(`${API_URL}/api/ingestion/filings?days_back=90`);
      if (filingsRes.ok) {
        const data = await filingsRes.json();
        setFilings(data.filings || {});
      }

      // Then trigger a check
      const checkRes = await fetch(`${API_URL}/api/ingestion/check-filings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days_back: 30, filing_types: ['10-K', '10-Q', '8-K'] }),
      });

      if (checkRes.ok) {
        setMessage('Filing check started. New filings will be downloaded in the background.');
      }
    } catch (err) {
      setError('Failed to check for filings');
    } finally {
      setCheckingFilings(false);
    }
  };

  const toggleScheduler = async (start: boolean) => {
    try {
      const endpoint = start ? 'start-scheduler' : 'stop-scheduler';
      const res = await fetch(`${API_URL}/api/ingestion/${endpoint}`, { method: 'POST' });
      if (res.ok) {
        fetchData();
        setMessage(`Scheduler ${start ? 'started' : 'stopped'} successfully`);
      }
    } catch (err) {
      setError(`Failed to ${start ? 'start' : 'stop'} scheduler`);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Data Management</h1>
          <p className="text-gray-600 mt-2">
            Manage automated SEC filing downloads and data ingestion
          </p>
        </div>

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            {error}
          </div>
        )}

        {message && (
          <div className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded mb-4">
            {message}
          </div>
        )}

        {/* Scheduler Status */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold">Automated Scheduler</h2>
            <div className="flex items-center gap-4">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                status?.scheduler.running 
                  ? 'bg-green-100 text-green-700' 
                  : 'bg-gray-100 text-gray-700'
              }`}>
                {status?.scheduler.running ? 'Running' : 'Stopped'}
              </span>
              <button
                onClick={() => toggleScheduler(!status?.scheduler.running)}
                className={`px-4 py-2 rounded text-white ${
                  status?.scheduler.running 
                    ? 'bg-red-600 hover:bg-red-700' 
                    : 'bg-green-600 hover:bg-green-700'
                }`}
              >
                {status?.scheduler.running ? 'Stop' : 'Start'}
              </button>
            </div>
          </div>

          {status?.scheduler.jobs && status.scheduler.jobs.length > 0 && (
            <div className="mt-4">
              <h3 className="font-medium mb-2">Scheduled Jobs:</h3>
              <div className="space-y-2">
                {status.scheduler.jobs.map(job => (
                  <div key={job.id} className="bg-gray-50 p-3 rounded">
                    <div className="font-medium">{job.name}</div>
                    <div className="text-sm text-gray-600">
                      Schedule: {job.trigger}
                    </div>
                    <div className="text-sm text-gray-600">
                      Next run: {job.next_run || 'N/A'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Manual Filing Check */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2 className="text-xl font-semibold">New SEC Filings</h2>
              <p className="text-gray-600 text-sm">
                Check for new 10-K, 10-Q, and 8-K filings from EDGAR
              </p>
              <p className="text-xs text-gray-500 mt-1">
                Hint: dropdowns show pending files and the companies with downloads.
              </p>
            </div>
            <button
              onClick={checkForFilings}
              disabled={checkingFilings}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {checkingFilings ? 'Checking...' : 'Check for New Filings'}
            </button>
          </div>

          {/* Download Stats */}
          {status?.downloads && (
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-blue-50 p-4 rounded">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-2xl font-bold text-blue-600">
                      {status.downloads.total_downloaded}
                    </div>
                    <div className="text-sm text-gray-600">Total Downloaded</div>
                  </div>
                  <details className="group text-right">
                    <summary className="cursor-pointer text-xs text-blue-700 hover:text-blue-800">
                      View files ({pendingToShow.length})
                    </summary>
                    <div className="mt-2 text-xs text-gray-600">
                      Up to 15 pending filings (form, date, description).
                    </div>
                    <ul className="mt-2 space-y-1 text-xs text-gray-700">
                      {pendingToShow.length > 0 ? (
                        pendingToShow.map((filing, idx) => (
                          <li key={`${filing.ticker}-${idx}`} className="text-left">
                            <span className="font-medium">{filing.ticker}</span>{' '}
                            {filing.form} · {filing.filing_date}
                            {filing.description ? ` — ${filing.description}` : ''}
                          </li>
                        ))
                      ) : (
                        <li className="text-left text-gray-500">No pending filings loaded.</li>
                      )}
                    </ul>
                  </details>
                </div>
              </div>
              <div className="bg-green-50 p-4 rounded">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-2xl font-bold text-green-600">
                      {Object.keys(status.downloads.by_company).length}
                    </div>
                    <div className="text-sm text-gray-600">Companies</div>
                  </div>
                  <details className="group text-right">
                    <summary className="cursor-pointer text-xs text-green-700 hover:text-green-800">
                      View list
                    </summary>
                    <div className="mt-2 text-xs text-gray-600">
                      Companies with downloaded filings.
                    </div>
                    <ul className="mt-2 space-y-1 text-xs text-gray-700">
                      {companiesWithDownloads.length > 0 ? (
                        companiesWithDownloads.map((ticker) => (
                          <li key={ticker} className="text-left">
                            {companyNameByTicker[ticker] || ticker} ({ticker})
                          </li>
                        ))
                      ) : (
                        <li className="text-left text-gray-500">No companies yet.</li>
                      )}
                    </ul>
                  </details>
                </div>
              </div>
              <div className="bg-purple-50 p-4 rounded">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-2xl font-bold text-purple-600">
                      {Object.keys(status.downloads.by_form).length}
                    </div>
                    <div className="text-sm text-gray-600">Filing Types</div>
                  </div>
                  <details className="group text-right">
                    <summary className="cursor-pointer text-xs text-purple-700 hover:text-purple-800">
                      View types
                    </summary>
                    <div className="mt-2 text-xs text-gray-600">
                      Filing types pending download.
                    </div>
                    <ul className="mt-2 space-y-1 text-xs text-gray-700">
                      {pendingTypes.length > 0 ? (
                        pendingTypes.map((form) => (
                          <li key={form} className="text-left">{form}</li>
                        ))
                      ) : (
                        <li className="text-left text-gray-500">No pending filing types.</li>
                      )}
                    </ul>
                  </details>
                </div>
              </div>
            </div>
          )}

          {/* Available Filings */}
          {Object.keys(filings).length > 0 && (
            <div className="mt-4">
              <h3 className="font-medium mb-2">Recent Available Filings:</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left">Company</th>
                      <th className="px-4 py-2 text-left">Form</th>
                      <th className="px-4 py-2 text-left">Date</th>
                      <th className="px-4 py-2 text-left">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {Object.entries(filings).flatMap(([ticker, tickerFilings]) =>
                      tickerFilings.slice(0, 3).map((filing, idx) => (
                        <tr key={`${ticker}-${idx}`}>
                          <td className="px-4 py-2">{ticker}</td>
                          <td className="px-4 py-2">{filing.form}</td>
                          <td className="px-4 py-2">{filing.filing_date}</td>
                          <td className="px-4 py-2">
                            <span className={`px-2 py-1 rounded text-xs ${
                              filing.already_downloaded 
                                ? 'bg-green-100 text-green-700' 
                                : 'bg-yellow-100 text-yellow-700'
                            }`}>
                              {filing.already_downloaded ? 'Downloaded' : 'Available'}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Company File Counts */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Company File Counts</h2>
          <p className="text-gray-600 text-sm mb-4">
            Downloaded filing totals by company
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {COMPANY_FILE_COUNTS.map((company) => {
              const count = status?.raw_files?.by_company?.[company.ticker] ?? 0;
              return (
                <div key={company.ticker} className="border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-semibold">{company.name}</h3>
                    <span className="text-sm text-gray-500">{company.ticker}</span>
                  </div>
                  <div className="text-2xl font-bold text-blue-600">{count}</div>
                  <div className="text-sm text-gray-500">Files downloaded</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
