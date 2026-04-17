'use client';

import { useState, useEffect, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  MapPin,
  Building2,
  Globe,
  RefreshCw,
  Factory,
  Users,
  ExternalLink,
  Star,
  Briefcase,
  Loader2,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  LabelList,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend,
} from 'recharts';

const GlobeMap = dynamic(() => import('./GlobeMap'), { ssr: false, loading: () => <div className="h-full w-full flex items-center justify-center text-slate-400">Loading map...</div> });

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

const COMPANY_COLORS: Record<string, string> = {
  Flex: '#2563EB',
  Jabil: '#16A34A',
  Sanmina: '#DC2626',
  Celestica: '#7C3AED',
  Plexus: '#D97706',
  Benchmark: '#0891B2',
};

const COMPANY_ORDER = ['Flex', 'Jabil', 'Sanmina', 'Celestica', 'Plexus', 'Benchmark'];

const COUNTRY_FLAGS: Record<string, string> = {
  'United States': '🇺🇸', USA: '🇺🇸', Canada: '🇨🇦', Mexico: '🇲🇽', Brazil: '🇧🇷',
  China: '🇨🇳', Malaysia: '🇲🇾', India: '🇮🇳', Singapore: '🇸🇬', 'United Kingdom': '🇬🇧',
  UK: '🇬🇧', Hungary: '🇭🇺', Romania: '🇷🇴', Poland: '🇵🇱', Netherlands: '🇳🇱',
  Spain: '🇪🇸', Germany: '🇩🇪', Japan: '🇯🇵', Taiwan: '🇹🇼', Thailand: '🇹🇭',
  Ireland: '🇮🇪',
};

type FacilityView = 'company' | 'continent';
type MarketRegion = 'all' | 'americas' | 'europe' | 'asia';

interface Facility {
  company: string;
  city: string;
  country: string;
  lat: number;
  lng: number;
  type: string;
  facility_type: string[];
  is_headquarters: boolean;
  source_url: string;
  source_page_title: string;
  capabilities: string[];
  region: string;
  subregion: string;
  is_shared_location: boolean;
  shared_with: string[];
}

interface MapComparison {
  companies?: { company: string; total_facilities: number; regional_distribution?: Record<string, number>; primary_region?: string }[];
  overlap_analysis?: { locations?: Record<string, string[]>; shared_locations?: number };
  regional_leaders?: Record<string, { company?: string; count?: number } | null>;
}

export default function MapPage() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [comparison, setComparison] = useState<MapComparison | null>(null);
  const [lastScraped, setLastScraped] = useState<string | null>(null);
  const [dataSources, setDataSources] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshProgress, setRefreshProgress] = useState('');

  // UI state
  const [facilityView, setFacilityView] = useState<FacilityView>('company');
  const [selectedCompany, setSelectedCompany] = useState<string | null>(null);
  const [showSharedOnly, setShowSharedOnly] = useState(false);
  const [marketRegion, setMarketRegion] = useState<MarketRegion>('all');
  const [selectedMapCompany, setSelectedMapCompany] = useState<string | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const toggleGroup = (key: string) =>
    setExpandedGroups(prev => ({ ...prev, [key]: !prev[key] }));

  useEffect(() => { loadFromCache(); }, []);

  const loadFromCache = async () => {
    setLoading(true);
    try {
      const [facilitiesRes, compareRes] = await Promise.all([
        fetch(`${API_URL}/api/geographic/facilities`),
        fetch(`${API_URL}/api/geographic/compare`),
      ]);
      if (facilitiesRes.ok) {
        const data = await facilitiesRes.json();
        setFacilities(data.facilities || []);
        setLastScraped(data.last_scraped || null);
        setDataSources(data.data_sources || {});
      }
      if (compareRes.ok) {
        setComparison(await compareRes.json());
      }
    } catch (err) {
      console.error('Failed to fetch geographic data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setRefreshProgress('Scraping official websites...');
    try {
      const res = await fetch(`${API_URL}/api/geographic/refresh`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.facilities) {
          setFacilities(data.facilities.facilities || []);
          setLastScraped(data.facilities.last_scraped || null);
          setDataSources(data.facilities.data_sources || {});
        }
        // Refresh comparison too
        const compareRes = await fetch(`${API_URL}/api/geographic/compare`);
        if (compareRes.ok) setComparison(await compareRes.json());
      }
    } catch (err) {
      console.error('Refresh failed:', err);
    } finally {
      setIsRefreshing(false);
      setRefreshProgress('');
    }
  };

  // --- Derived data ---

  const filteredFacilities = useMemo(() => {
    let result = facilities;
    if (selectedCompany) result = result.filter(f => f.company === selectedCompany);
    if (showSharedOnly) result = result.filter(f => f.is_shared_location);
    return result;
  }, [facilities, selectedCompany, showSharedOnly]);

  const overlapLocations = useMemo(() => comparison?.overlap_analysis?.locations || {}, [comparison]);

  // --- Charts data ---

  const facilityCountData = useMemo(() => {
    const counts: Record<string, number> = {};
    facilities.forEach(f => { counts[f.company] = (counts[f.company] || 0) + 1; });
    return COMPANY_ORDER
      .filter(c => counts[c])
      .map(company => ({ company, count: counts[company] || 0, fill: COMPANY_COLORS[company] }));
  }, [facilities]);

  const regionalData = useMemo(() => {
    const dist: Record<string, { Americas: number; EMEA: number; APAC: number }> = {};
    facilities.forEach(f => {
      if (!dist[f.company]) dist[f.company] = { Americas: 0, EMEA: 0, APAC: 0 };
      if (f.region === 'Americas') dist[f.company].Americas += 1;
      else if (f.region === 'Europe') dist[f.company].EMEA += 1;
      else if (f.region === 'Asia') dist[f.company].APAC += 1;
    });
    return COMPANY_ORDER
      .filter(c => dist[c])
      .map(company => ({
        company,
        total: (dist[company]?.Americas || 0) + (dist[company]?.EMEA || 0) + (dist[company]?.APAC || 0),
        ...dist[company],
      }));
  }, [facilities]);

  // --- By Continent grouping ---

  const continentGroups = useMemo(() => {
    const groups: Record<string, { countries: Record<string, Facility[]> }> = {};
    const order = ['Asia', 'Americas', 'Europe'];
    order.forEach(r => { groups[r] = { countries: {} }; });

    filteredFacilities.forEach(f => {
      const region = f.region || 'Other';
      if (!groups[region]) groups[region] = { countries: {} };
      if (!groups[region].countries[f.country]) groups[region].countries[f.country] = [];
      groups[region].countries[f.country].push(f);
    });

    return Object.entries(groups)
      .filter(([, v]) => Object.keys(v.countries).length > 0)
      .sort((a, b) => (order.indexOf(a[0]) === -1 ? 99 : order.indexOf(a[0])) - (order.indexOf(b[0]) === -1 ? 99 : order.indexOf(b[0])));
  }, [filteredFacilities]);

  // --- By Company grouping ---

  const companyGroups = useMemo(() => {
    const groups: Record<string, Facility[]> = {};
    filteredFacilities.forEach(f => {
      if (!groups[f.company]) groups[f.company] = [];
      groups[f.company].push(f);
    });
    return COMPANY_ORDER
      .filter(c => groups[c])
      .map(company => ({ company, facilities: groups[company] }));
  }, [filteredFacilities]);

  // --- Globe visible facilities ---

  const visibleMapFacilities = useMemo(() => {
    let result = facilities;
    if (marketRegion !== 'all') {
      const regionMap: Record<string, string> = { americas: 'Americas', europe: 'Europe', asia: 'Asia' };
      result = result.filter(f => f.region === regionMap[marketRegion]);
    }
    if (selectedMapCompany) result = result.filter(f => f.company === selectedMapCompany);
    return result;
  }, [facilities, marketRegion, selectedMapCompany]);

  const marketCompanyCards = useMemo(() => {
    return COMPANY_ORDER.map(company => {
      const all = facilities.filter(f => f.company === company);
      const regionSet = new Set(all.map(f => f.region));
      return {
        company,
        total: all.length,
        regions: ['Americas', 'Europe', 'Asia'].filter(r => regionSet.has(r)),
        sourceUrl: dataSources[company] || '',
      };
    });
  }, [facilities, dataSources]);

  // --- Render ---

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="relative">
            <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto" />
            <Globe className="h-6 w-6 text-blue-600 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
          </div>
          <p className="text-slate-600 dark:text-slate-300 mt-4 font-medium">Loading facility data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 dark:from-slate-950 dark:via-slate-950 dark:to-slate-900 p-4">
      {/* Header */}
      <div className="mb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="bg-gradient-to-br from-blue-500 to-green-600 p-3 rounded-xl shadow-lg shadow-blue-500/20">
              <Factory className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">EMS Global Facilities Intelligence Map</h1>
              <p className="text-slate-500 dark:text-slate-400 mt-0.5 text-sm">
                Data Sources: {COMPANY_ORDER.join(' · ')}
                {lastScraped && (
                  <span className="ml-2 text-slate-400 dark:text-slate-500">
                    Last updated: {new Date(lastScraped).toLocaleDateString()}
                  </span>
                )}
              </p>
            </div>
          </div>
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all shadow-sm disabled:opacity-50"
          >
            {isRefreshing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-sm">{refreshProgress || 'Refreshing...'}</span>
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4" />
                Refresh
              </>
            )}
          </button>
        </div>
      </div>

      {/* ============ Section 1: Geographic Analysis ============ */}
      <div className="space-y-4 mb-4">
          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Card className="border-0 shadow-xl !py-0 h-[72px]">
              <CardContent className="p-3 h-full">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500 dark:text-slate-400">Total Facilities</span>
                  <Building2 className="h-4 w-4 text-blue-500" />
                </div>
                <p className="text-xl font-bold text-slate-900 dark:text-slate-100 mt-0.5">{facilities.length}</p>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-xl !py-0 h-[72px]">
              <CardContent className="p-3 h-full">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500 dark:text-slate-400">Shared Locations</span>
                  <Users className="h-4 w-4 text-purple-500" />
                </div>
                <p className="text-xl font-bold text-slate-900 dark:text-slate-100 mt-0.5">{Object.keys(overlapLocations).length}</p>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-xl !py-0 h-[72px]">
              <CardContent className="p-3 h-full">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500 dark:text-slate-400">APAC Leader</span>
                  <MapPin className="h-4 w-4 text-green-500" />
                </div>
                <p className="text-xl font-bold text-slate-900 dark:text-slate-100 mt-0.5">{comparison?.regional_leaders?.APAC?.company || 'N/A'}</p>
                <p className="text-[10px] text-slate-500 dark:text-slate-400">{comparison?.regional_leaders?.APAC?.count || 0} facilities</p>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-xl !py-0 h-[72px]">
              <CardContent className="p-3 h-full">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500 dark:text-slate-400">Americas Leader</span>
                  <Factory className="h-4 w-4 text-orange-500" />
                </div>
                <p className="text-xl font-bold text-slate-900 dark:text-slate-100 mt-0.5">{comparison?.regional_leaders?.Americas?.company || 'N/A'}</p>
                <p className="text-[10px] text-slate-500 dark:text-slate-400">{comparison?.regional_leaders?.Americas?.count || 0} facilities</p>
              </CardContent>
            </Card>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <Card className="border-0 shadow-xl !py-0">
              <CardHeader className="pb-1 pt-3 px-4">
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Building2 className="h-5 w-5 text-blue-600" />
                  Facilities by Company
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 pb-3 px-3">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={facilityCountData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                    <XAxis dataKey="company" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="count" name="Facilities" radius={[4, 4, 0, 0]}>
                      <LabelList dataKey="count" position="top" offset={6} className="fill-slate-600 text-xs font-medium" />
                      {facilityCountData.map((entry, i) => (
                        <Cell key={i} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-xl !py-0">
              <CardHeader className="pb-1 pt-3 px-4">
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Globe className="h-5 w-5 text-green-600" />
                  Regional Distribution
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 pb-3 px-3">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={regionalData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                    <XAxis dataKey="company" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="Americas" stackId="a" fill="#3B82F6" />
                    <Bar dataKey="EMEA" stackId="a" fill="#8B5CF6" />
                    <Bar dataKey="APAC" stackId="a" fill="#10B981">
                      <LabelList dataKey="total" position="top" offset={6} className="fill-slate-600 text-xs font-medium" />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
      </div>

      {/* ============ Section 2: Facility Locations ============ */}
      <div className="space-y-4 mb-4">
          {/* Controls */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-slate-500 dark:text-slate-400 mr-1">View:</span>
              <button
                onClick={() => setFacilityView('company')}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all border ${
                  facilityView === 'company'
                    ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 border-slate-900 dark:border-slate-100'
                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50'
                }`}
              >
                By Company
              </button>
              <button
                onClick={() => setFacilityView('continent')}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all border ${
                  facilityView === 'continent'
                    ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 border-slate-900 dark:border-slate-100'
                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50'
                }`}
              >
                By Continent
              </button>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-slate-500 dark:text-slate-400 mr-1">Filter:</span>
              <button
                onClick={() => { setSelectedCompany(null); setShowSharedOnly(false); }}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all border ${
                  !selectedCompany && !showSharedOnly
                    ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 border-slate-900'
                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50'
                }`}
              >
                All
              </button>
              {COMPANY_ORDER.map(company => (
                <button
                  key={company}
                  onClick={() => { setSelectedCompany(company); setShowSharedOnly(false); }}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all border ${
                    selectedCompany === company
                      ? 'text-white'
                      : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50'
                  }`}
                  style={{
                    backgroundColor: selectedCompany === company ? COMPANY_COLORS[company] : undefined,
                    borderColor: selectedCompany === company ? COMPANY_COLORS[company] : undefined,
                  }}
                >
                  {company}
                </button>
              ))}
              <button
                onClick={() => { setShowSharedOnly(!showSharedOnly); setSelectedCompany(null); }}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all border flex items-center gap-1 ${
                  showSharedOnly
                    ? 'bg-purple-600 text-white border-purple-600'
                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50'
                }`}
              >
                <Star className="h-3.5 w-3.5" />
                Shared Only
              </button>
            </div>
          </div>

          <Badge variant="secondary" className="ml-1">{filteredFacilities.length} locations</Badge>

          {/* By Company View */}
          {facilityView === 'company' && (
            <div className="space-y-4">
              {companyGroups.map(({ company, facilities: compFacilities }) => {
                const isExpanded = !!expandedGroups[company];
                return (
                  <Card key={company} className="border-0 shadow-xl">
                    <CardHeader className="pb-2 pt-3">
                      <CardTitle className="flex items-center justify-between">
                        <button
                          onClick={() => toggleGroup(company)}
                          className="flex items-center gap-3 hover:opacity-80 transition-opacity text-left"
                        >
                          <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: COMPANY_COLORS[company] }} />
                          <span>{company}</span>
                          <Badge variant="secondary">{compFacilities.length}</Badge>
                          {isExpanded
                            ? <ChevronUp className="h-4 w-4 text-slate-400" />
                            : <ChevronDown className="h-4 w-4 text-slate-400" />}
                        </button>
                        {dataSources[company] && (
                          <a
                            href={dataSources[company]}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
                          >
                            <ExternalLink className="h-3 w-3" />
                            Source
                          </a>
                        )}
                      </CardTitle>
                    </CardHeader>
                    {isExpanded && (
                      <CardContent className="pt-0 pb-3">
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-5 gap-2.5">
                          {compFacilities.map((f, i) => (
                            <FacilityCard key={`${f.city}-${i}`} facility={f} />
                          ))}
                        </div>
                      </CardContent>
                    )}
                  </Card>
                );
              })}
            </div>
          )}

          {/* By Continent View */}
          {facilityView === 'continent' && (
            <div className="space-y-4">
              {continentGroups.map(([region, { countries }]) => {
                const regionEmoji = region === 'Asia' ? '🌏' : region === 'Americas' ? '🌎' : '🌍';
                const sortedCountries = Object.entries(countries).sort((a, b) => b[1].length - a[1].length);
                const groupKey = `continent-${region}`;
                const isExpanded = !!expandedGroups[groupKey];
                return (
                  <Card key={region} className="border-0 shadow-xl">
                    <CardHeader className="pb-2 pt-3">
                      <CardTitle>
                        <button
                          onClick={() => toggleGroup(groupKey)}
                          className="flex items-center gap-3 hover:opacity-80 transition-opacity text-left w-full"
                        >
                          <span className="text-xl">{regionEmoji}</span>
                          <span>{region}</span>
                          <Badge variant="secondary">
                            {Object.values(countries).reduce((s, arr) => s + arr.length, 0)} facilities
                          </Badge>
                          {isExpanded
                            ? <ChevronUp className="h-4 w-4 text-slate-400" />
                            : <ChevronDown className="h-4 w-4 text-slate-400" />}
                        </button>
                      </CardTitle>
                      <div className="flex items-center gap-2 flex-wrap mt-2">
                        {sortedCountries.map(([country, facs]) => (
                          <Badge key={country} variant="outline" className="text-xs">
                            {COUNTRY_FLAGS[country] || '🌐'} {country} ({facs.length})
                          </Badge>
                        ))}
                      </div>
                    </CardHeader>
                    {isExpanded && (
                      <CardContent className="pt-0 pb-3">
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-5 gap-2.5">
                          {sortedCountries.flatMap(([, facs]) =>
                            facs.map((f, i) => (
                              <FacilityCard key={`${f.company}-${f.city}-${i}`} facility={f} />
                            ))
                          )}
                        </div>
                      </CardContent>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
      </div>

      {/* ============ Section 3: Factory Footprint Globe ============ */}
      <Card className="border-0 shadow-xl overflow-hidden bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100">
          <CardHeader className="pb-2">
            <CardTitle>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Globe className="h-5 w-5 text-emerald-500 dark:text-emerald-400" />
                  Factory Footprint Globe
                </div>
              </div>
            </CardTitle>
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              {(['all', 'americas', 'europe', 'asia'] as const).map(region => (
                <button
                  key={region}
                  onClick={() => setMarketRegion(region)}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all border ${
                    marketRegion === region
                      ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 border-slate-900 dark:border-slate-100'
                      : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'
                  }`}
                >
                  {{ all: 'All Regions', americas: 'Americas', europe: 'Europe', asia: 'Asia' }[region]}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="pt-1 pb-4">
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4">
              <div className="relative h-full min-h-[440px] overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
                <GlobeMap facilities={visibleMapFacilities} marketRegion={marketRegion} />
                <div className="pointer-events-none absolute left-3 bottom-3 z-[500] rounded-md bg-white/90 dark:bg-slate-900/85 border border-slate-200 dark:border-slate-700 px-2 py-1 text-[12px] text-slate-600 dark:text-slate-300">
                  {selectedMapCompany || 'All Companies'} · {visibleMapFacilities.length} sites
                </div>

                {/* Legend */}
                <div className="pointer-events-none absolute right-3 bottom-3 z-[500] rounded-md bg-white/90 dark:bg-slate-900/85 border border-slate-200 dark:border-slate-700 px-2 py-1.5 text-[11px] text-slate-600 dark:text-slate-300 space-y-1">
                  {COMPANY_ORDER.map(c => (
                    <div key={c} className="flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ backgroundColor: COMPANY_COLORS[c] }} />
                      {c}
                    </div>
                  ))}
                  <div className="flex items-center gap-1.5 pt-0.5 border-t border-slate-200 dark:border-slate-700">
                    <span className="text-sm leading-none">⭐</span>
                    Shared Location
                  </div>
                </div>
              </div>

              {/* Right sidebar: company cards */}
              <div className="grid grid-cols-1 gap-2.5">
                {marketCompanyCards.map(row => (
                  <button
                    key={row.company}
                    type="button"
                    onClick={() => setSelectedMapCompany(prev => prev === row.company ? null : row.company)}
                    className={`text-left rounded-lg border p-2.5 transition-all ${
                      selectedMapCompany === row.company
                        ? 'border-slate-900 dark:border-slate-100 bg-slate-100 dark:bg-slate-800'
                        : 'border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/80 hover:border-slate-300 dark:hover:border-slate-500'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-slate-900 dark:text-slate-100">{row.company}</span>
                      <span
                        className="text-[11px] px-2 py-0.5 rounded-full border"
                        style={{
                          color: COMPANY_COLORS[row.company],
                          borderColor: COMPANY_COLORS[row.company],
                          backgroundColor: `${COMPANY_COLORS[row.company]}1a`,
                        }}
                      >
                        {selectedMapCompany === row.company ? 'Focused' : 'View'}
                      </span>
                    </div>
                    <div className="mt-2 text-[12px] text-slate-600 dark:text-slate-300">
                      <div>Sites: <span className="font-semibold text-slate-900 dark:text-slate-100">{row.total}</span></div>
                      <div className="mt-1">Regions: <span className="font-semibold text-slate-900 dark:text-slate-100">{row.regions.join(' · ') || 'N/A'}</span></div>
                    </div>
                    {row.sourceUrl && (
                      <a
                        href={row.sourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={e => e.stopPropagation()}
                        className="mt-1.5 flex items-center gap-1 text-[11px] text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        <ExternalLink className="h-3 w-3" />
                        {row.sourceUrl.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')}
                      </a>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
      </Card>

      {/* Footer: data source attribution */}
      <div className="mt-4 text-center text-[11px] text-slate-400 dark:text-slate-500">
        Data sourced from official company websites.
        {lastScraped && ` Last scraped: ${new Date(lastScraped).toLocaleString()}`}
      </div>
    </div>
  );
}

// --- Facility Card Component ---

function FacilityCard({ facility }: { facility: Facility }) {
  const isShared = facility.is_shared_location;
  const isHQ = facility.is_headquarters;

  return (
    <div
      className={`p-2 rounded-lg border-2 transition-all hover:shadow-sm bg-white dark:bg-slate-900 min-h-[84px] relative ${
        isShared
          ? 'border-purple-300 dark:border-purple-700 hover:border-purple-400'
          : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600'
      }`}
    >
      {isShared && (
        <div className="absolute top-1 right-1">
          <Badge className="text-[9px] px-1 py-0 bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-300 border-purple-300 dark:border-purple-700">
            <Star className="h-2.5 w-2.5 mr-0.5 inline" />
            SHARED
          </Badge>
        </div>
      )}

      <div className="mb-1.5 flex items-center gap-2">
        {isHQ ? (
          <Briefcase className="h-4 w-4 text-amber-600 shrink-0" />
        ) : (
          <Factory className="h-4 w-4 text-slate-400 shrink-0" />
        )}
        <span className="text-[15px] font-semibold leading-tight text-slate-900 dark:text-slate-100">{facility.city}</span>
        <Badge
          className="text-[11px] shrink-0"
          style={{
            backgroundColor: `${COMPANY_COLORS[facility.company]}20`,
            color: COMPANY_COLORS[facility.company],
            borderColor: COMPANY_COLORS[facility.company],
          }}
        >
          {facility.company}
        </Badge>
      </div>

      <div className="mt-1 grid grid-cols-2 gap-1.5 text-[12px]">
        <span className="inline-flex items-center gap-1 text-slate-500 dark:text-slate-400">
          <span>{COUNTRY_FLAGS[facility.country] || '🌐'}</span>
          <span>{facility.country}</span>
        </span>
        <span className="text-slate-400 dark:text-slate-500">{facility.type}</span>
      </div>

      {isShared && facility.shared_with.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {facility.shared_with.map(c => (
            <Badge
              key={c}
              className="text-[9px] px-1"
              style={{ backgroundColor: COMPANY_COLORS[c], color: 'white', borderColor: COMPANY_COLORS[c] }}
            >
              {c}
            </Badge>
          ))}
        </div>
      )}

      {facility.source_url && (
        <a
          href={facility.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-1.5 flex items-center gap-1 text-[10px] text-slate-400 dark:text-slate-500 hover:text-blue-600 dark:hover:text-blue-400"
        >
          <ExternalLink className="h-2.5 w-2.5" />
          {facility.source_page_title || 'Source'}
        </a>
      )}
    </div>
  );
}
