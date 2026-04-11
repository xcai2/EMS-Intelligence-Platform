'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Calendar,
  CalendarDays,
  Clock,
  Building2,
  RefreshCw,
  Download,
  ChevronLeft,
  ChevronRight,
  Bell,
  Check,
  Filter,
  AlertCircle
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

const COMPANY_COLORS: Record<string, string> = {
  'Flex': '#3B82F6',
  'Jabil': '#10B981',
  'Celestica': '#6366F1',
  'Benchmark': '#F59E0B',
  'Sanmina': '#EF4444',
  'Plexus': '#14B8A6',
};

interface CalendarEvent {
  id: string;
  company: string;
  ticker: string;
  quarter: string;
  fiscal_year: number;
  estimated_date: string;
  time: string;
  event_type: string;
  confirmed: boolean;
  status: string;
  days_until?: number;
}

interface CalendarSummary {
  total_events: number;
  confirmed_events: number;
  upcoming_30_days: number;
  upcoming_7_days: number;
  next_event: CalendarEvent | null;
  companies_tracked: number;
}

export default function CalendarPage() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [upcoming, setUpcoming] = useState<CalendarEvent[]>([]);
  const [summary, setSummary] = useState<CalendarSummary | null>(null);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth());
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [selectedCompany, setSelectedCompany] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const companies = Object.keys(COMPANY_COLORS);
  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  useEffect(() => {
    fetchCalendarData();
  }, [selectedYear]);

  const fetchCalendarData = async () => {
    setLoading(true);
    try {
      const [calendarRes, upcomingRes, summaryRes] = await Promise.all([
        fetch(`${API_URL}/api/calendar?year=${selectedYear}`),
        fetch(`${API_URL}/api/calendar/upcoming?days=60`),
        fetch(`${API_URL}/api/calendar/summary`),
      ]);

      if (calendarRes.ok) {
        const data = await calendarRes.json();
        setEvents(data.events || []);
      }
      if (upcomingRes.ok) {
        const data = await upcomingRes.json();
        setUpcoming(data.events || []);
      }
      if (summaryRes.ok) {
        setSummary(await summaryRes.json());
      }
    } catch (err) {
      console.error('Failed to fetch calendar:', err);
    } finally {
      setLoading(false);
    }
  };

  const syncCalendar = async () => {
    setSyncing(true);
    try {
      await fetch(`${API_URL}/api/calendar/sync`, { method: 'POST' });
      await fetchCalendarData();
    } catch (err) {
      console.error('Failed to sync:', err);
    } finally {
      setSyncing(false);
    }
  };

  const downloadIcal = () => {
    window.open(`${API_URL}/api/calendar/export/ical`, '_blank');
  };

  const getMonthEvents = () => {
    const monthStr = `${selectedYear}-${String(selectedMonth + 1).padStart(2, '0')}`;
    return events.filter(e => {
      const matchesMonth = e.estimated_date.startsWith(monthStr);
      const matchesCompany = selectedCompany === 'all' || e.company === selectedCompany;
      return matchesMonth && matchesCompany;
    });
  };

  const getFilteredUpcoming = () => {
    if (selectedCompany === 'all') return upcoming;
    return upcoming.filter(e => e.company === selectedCompany);
  };

  const prevMonth = () => {
    if (selectedMonth === 0) {
      setSelectedMonth(11);
      setSelectedYear(selectedYear - 1);
    } else {
      setSelectedMonth(selectedMonth - 1);
    }
  };

  const nextMonth = () => {
    if (selectedMonth === 11) {
      setSelectedMonth(0);
      setSelectedYear(selectedYear + 1);
    } else {
      setSelectedMonth(selectedMonth + 1);
    }
  };

  const getDaysInMonth = (year: number, month: number) => {
    return new Date(year, month + 1, 0).getDate();
  };

  const getFirstDayOfMonth = (year: number, month: number) => {
    return new Date(year, month, 1).getDay();
  };

  const renderCalendarGrid = () => {
    const daysInMonth = getDaysInMonth(selectedYear, selectedMonth);
    const firstDay = getFirstDayOfMonth(selectedYear, selectedMonth);
    const monthEvents = getMonthEvents();

    const days = [];
    
    // Empty cells for days before the first of the month
    for (let i = 0; i < firstDay; i++) {
      days.push(<div key={`empty-${i}`} className="h-24 bg-slate-50"></div>);
    }

    // Days of the month
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${selectedYear}-${String(selectedMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const dayEvents = monthEvents.filter(e => e.estimated_date === dateStr);
      const isToday = new Date().toISOString().split('T')[0] === dateStr;

      days.push(
        <div
          key={day}
          className={`h-24 border border-slate-100 p-1 ${isToday ? 'bg-blue-50 ring-2 ring-blue-500' : 'bg-white'}`}
        >
          <div className={`text-sm font-medium ${isToday ? 'text-blue-600' : 'text-slate-600'}`}>
            {day}
          </div>
          <div className="mt-1 space-y-1 overflow-y-auto max-h-16">
            {dayEvents.map((event, idx) => (
              <div
                key={idx}
                className="text-xs p-1 rounded truncate"
                style={{ 
                  backgroundColor: COMPANY_COLORS[event.company] + '20',
                  borderLeft: `3px solid ${COMPANY_COLORS[event.company]}`,
                }}
                title={`${event.company} ${event.quarter} Earnings`}
              >
                {event.company} {event.quarter}
              </div>
            ))}
          </div>
        </div>
      );
    }

    return days;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
          <p className="text-slate-600 mt-4 font-medium">Loading calendar...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <div className="bg-gradient-to-br from-indigo-600 to-purple-700 p-3 rounded-xl shadow-lg shadow-indigo-500/20">
            <CalendarDays className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Earnings Calendar</h1>
            <p className="text-slate-500 mt-1">Track upcoming earnings announcements</p>
          </div>
        </div>
        <div className="flex gap-3">
          <button
            onClick={syncCalendar}
            disabled={syncing}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
            Sync
          </button>
          <button
            onClick={downloadIcal}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors"
          >
            <Download className="h-4 w-4" />
            Export iCal
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <Card className="border-0 shadow-lg bg-gradient-to-br from-blue-500 to-blue-600 text-white">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-blue-100 text-sm">This Week</p>
                  <p className="text-3xl font-bold">{summary.upcoming_7_days}</p>
                </div>
                <Calendar className="h-8 w-8 text-blue-200" />
              </div>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-lg bg-gradient-to-br from-purple-500 to-purple-600 text-white">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-purple-100 text-sm">Next 30 Days</p>
                  <p className="text-3xl font-bold">{summary.upcoming_30_days}</p>
                </div>
                <Clock className="h-8 w-8 text-purple-200" />
              </div>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-lg bg-gradient-to-br from-green-500 to-green-600 text-white">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-green-100 text-sm">Confirmed</p>
                  <p className="text-3xl font-bold">{summary.confirmed_events}</p>
                </div>
                <Check className="h-8 w-8 text-green-200" />
              </div>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-lg bg-gradient-to-br from-amber-500 to-amber-600 text-white">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-amber-100 text-sm">Companies</p>
                  <p className="text-3xl font-bold">{summary.companies_tracked}</p>
                </div>
                <Building2 className="h-8 w-8 text-amber-200" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Calendar View */}
        <div className="lg:col-span-2">
          <Card className="border-0 shadow-xl">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <button
                    onClick={prevMonth}
                    className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
                  >
                    <ChevronLeft className="h-5 w-5" />
                  </button>
                  <CardTitle>
                    {months[selectedMonth]} {selectedYear}
                  </CardTitle>
                  <button
                    onClick={nextMonth}
                    className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
                  >
                    <ChevronRight className="h-5 w-5" />
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <Filter className="h-4 w-4 text-slate-400" />
                  <select
                    value={selectedCompany}
                    onChange={(e) => setSelectedCompany(e.target.value)}
                    className="text-sm border rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="all">All Companies</option>
                    {companies.map(c => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {/* Day headers */}
              <div className="grid grid-cols-7 mb-2">
                {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                  <div key={day} className="text-center text-sm font-medium text-slate-500 py-2">
                    {day}
                  </div>
                ))}
              </div>
              {/* Calendar grid */}
              <div className="grid grid-cols-7 gap-px bg-slate-200 rounded-lg overflow-hidden">
                {renderCalendarGrid()}
              </div>
              {/* Legend */}
              <div className="flex flex-wrap gap-3 mt-4 pt-4 border-t">
                {companies.map(company => (
                  <div key={company} className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded"
                      style={{ backgroundColor: COMPANY_COLORS[company] }}
                    ></div>
                    <span className="text-xs text-slate-600">{company}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Upcoming Events */}
        <div className="space-y-6">
          <Card className="border-0 shadow-xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5 text-blue-600" />
                Upcoming Earnings
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {getFilteredUpcoming().length > 0 ? (
                  getFilteredUpcoming().map((event, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl border border-slate-100 hover:border-slate-200 transition-colors"
                      style={{ borderLeftColor: COMPANY_COLORS[event.company], borderLeftWidth: '4px' }}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium">{event.company}</span>
                        <Badge variant="outline" className={event.confirmed ? 'bg-green-50 text-green-700' : ''}>
                          {event.confirmed ? 'Confirmed' : 'Estimated'}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">{event.quarter} FY{event.fiscal_year}</span>
                        <span className="text-slate-600">{event.estimated_date}</span>
                      </div>
                      {event.days_until !== undefined && (
                        <div className="mt-2 flex items-center gap-1 text-xs">
                          <Clock className="h-3 w-3 text-slate-400" />
                          <span className={event.days_until <= 7 ? 'text-amber-600 font-medium' : 'text-slate-500'}>
                            {event.days_until === 0 ? 'Today' : `${event.days_until} days`}
                          </span>
                        </div>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="text-center py-8 text-slate-500">
                    <AlertCircle className="h-8 w-8 mx-auto mb-2 text-slate-300" />
                    No upcoming events
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Next Event Highlight */}
          {summary?.next_event && (
            <Card className="border-0 shadow-xl bg-gradient-to-br from-slate-800 to-slate-900 text-white">
              <CardHeader>
                <CardTitle className="text-white">Next Earnings</CardTitle>
              </CardHeader>
              <CardContent>
                <div
                  className="p-4 rounded-xl"
                  style={{ backgroundColor: COMPANY_COLORS[summary.next_event.company] + '30' }}
                >
                  <p className="text-2xl font-bold">{summary.next_event.company}</p>
                  <p className="text-slate-300">{summary.next_event.quarter} FY{summary.next_event.fiscal_year}</p>
                  <div className="mt-3 flex items-center gap-2">
                    <CalendarDays className="h-4 w-4 text-slate-400" />
                    <span>{summary.next_event.estimated_date}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <Clock className="h-4 w-4 text-slate-400" />
                    <span>{summary.next_event.time}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
