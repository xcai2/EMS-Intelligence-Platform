'use client';

import { useState, useEffect, useMemo } from 'react';
import type { LatLngExpression } from 'leaflet';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { 
  MapPin, 
  Building2, 
  Globe, 
  RefreshCw,
  Factory,
  Briefcase,
  Users,
  ExternalLink
} from 'lucide-react';
import { MapContainer, TileLayer, CircleMarker, Tooltip as LeafletTooltip, useMap } from 'react-leaflet';
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
import 'leaflet/dist/leaflet.css';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

const COMPANY_COLORS: Record<string, string> = {
  Flex: '#0078FF',
  Jabil: '#16A34A',
  Celestica: '#7C3AED',
  Benchmark: '#F59E0B',
  Sanmina: '#E11D48',
  Plexus: '#14B8A6',
};

const SHARED_FILTER = '__shared__';

const COMPANY_SORT_ORDER: Record<string, number> = {
  Flex: 0,
  Jabil: 1,
  Celestica: 2,
  Benchmark: 3,
  Sanmina: 4,
  Plexus: 5,
};

const FLEX_REGION_SORT_ORDER: Record<string, number> = {
  APAC: 0,
  EMEA: 1,
  Americas: 2,
  Other: 3,
};

const FLEX_COUNTRY_SORT_ORDER: Record<string, number> = {
  China: 0,
  Singapore: 1,
  Malaysia: 2,
  India: 3,
  Thailand: 4,
  Taiwan: 5,
  Japan: 6,
  Romania: 7,
  Hungary: 8,
  Spain: 9,
  Germany: 10,
  Netherlands: 11,
  UK: 12,
  Ireland: 13,
  Poland: 14,
  USA: 15,
  Mexico: 16,
  Brazil: 17,
  Canada: 18,
};

const CONTINENT_SORT_ORDER: Record<string, number> = {
  Asia: 0,
  Europe: 1,
  'North America': 2,
  'South America': 3,
  Oceania: 4,
  Africa: 5,
  Antarctica: 6,
  Other: 7,
};

const COUNTRY_FLAGS: Record<string, string> = {
  USA: '🇺🇸',
  Canada: '🇨🇦',
  Mexico: '🇲🇽',
  Brazil: '🇧🇷',
  China: '🇨🇳',
  Malaysia: '🇲🇾',
  India: '🇮🇳',
  Singapore: '🇸🇬',
  UK: '🇬🇧',
  Hungary: '🇭🇺',
  Romania: '🇷🇴',
  Poland: '🇵🇱',
  Netherlands: '🇳🇱',
  Spain: '🇪🇸',
  Germany: '🇩🇪',
  Japan: '🇯🇵',
  Taiwan: '🇹🇼',
  Thailand: '🇹🇭',
  Ireland: '🇮🇪',
};

type MarketRegion = 'all' | 'americas' | 'europe' | 'asia';

const MARKET_REGION_LABELS: Record<MarketRegion, string> = {
  all: 'All Regions',
  americas: 'Americas',
  europe: 'Europe',
  asia: 'Asia',
};

const REGION_VIEW: Record<MarketRegion, { center: LatLngExpression; zoom: number }> = {
  all: { center: [20, 15], zoom: 2 },
  americas: { center: [28, -85], zoom: 3 },
  europe: { center: [50, 12], zoom: 4 },
  asia: { center: [28, 105], zoom: 4 },
};

function getCountryFlag(country: string): string {
  return COUNTRY_FLAGS[country] || '🌐';
}

function getMarketRegionByCountry(country: string): Exclude<MarketRegion, 'all'> | 'other' {
  if (['USA', 'Canada', 'Mexico', 'Brazil'].includes(country)) return 'americas';
  if (['Romania', 'Hungary', 'Spain', 'Germany', 'Netherlands', 'UK', 'Ireland', 'Poland'].includes(country)) return 'europe';
  if (['China', 'Singapore', 'Malaysia', 'India', 'Thailand', 'Taiwan', 'Japan'].includes(country)) return 'asia';
  return 'other';
}

function getFlexRegion(country: string): keyof typeof FLEX_REGION_SORT_ORDER {
  if (['China', 'Singapore', 'Malaysia', 'India', 'Thailand', 'Taiwan', 'Japan'].includes(country)) {
    return 'APAC';
  }
  if (['Romania', 'Hungary', 'Spain', 'Germany', 'Netherlands', 'UK', 'Ireland', 'Poland'].includes(country)) {
    return 'EMEA';
  }
  if (['USA', 'Canada', 'Mexico', 'Brazil'].includes(country)) {
    return 'Americas';
  }
  return 'Other';
}

function getContinentByCountry(country: string): keyof typeof CONTINENT_SORT_ORDER {
  if (['China', 'Singapore', 'Malaysia', 'India', 'Thailand', 'Taiwan', 'Japan'].includes(country)) {
    return 'Asia';
  }
  if (['Romania', 'Hungary', 'Spain', 'Germany', 'Netherlands', 'UK', 'Ireland', 'Poland'].includes(country)) {
    return 'Europe';
  }
  if (['USA', 'Canada', 'Mexico'].includes(country)) {
    return 'North America';
  }
  if (['Brazil'].includes(country)) {
    return 'South America';
  }
  return 'Other';
}

interface Facility {
  company: string;
  city: string;
  country: string;
  lat: number;
  lng: number;
  type: string;
  website?: string;
  is_headquarters: boolean;
}

interface CompanyComparisonRow {
  company: string;
  regional_distribution?: {
    Americas?: number;
    EMEA?: number;
    APAC?: number;
  };
}

interface MapComparison {
  companies?: CompanyComparisonRow[];
  overlap_analysis?: {
    locations?: Record<string, string[]>;
  };
  regional_leaders?: {
    APAC?: { company?: string; count?: number };
    Americas?: { company?: string; count?: number };
  };
}

function RegionMapController({ region }: { region: MarketRegion }) {
  const map = useMap();

  useEffect(() => {
    const view = REGION_VIEW[region];
    map.flyTo(view.center, view.zoom, { duration: 0.8 });
  }, [map, region]);

  return null;
}

export default function MapPage() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [comparison, setComparison] = useState<MapComparison | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<string | null>(null);
  const [marketRegion, setMarketRegion] = useState<MarketRegion>('all');
  const [selectedMapCompany, setSelectedMapCompany] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchGeographicData();
  }, []);

  useEffect(() => {
    if (selectedCompany && selectedCompany !== SHARED_FILTER) {
      setSelectedMapCompany(selectedCompany);
      return;
    }
    setSelectedMapCompany(null);
  }, [selectedCompany]);

  const fetchGeographicData = async () => {
    setLoading(true);
    try {
      const [facilitiesRes, compareRes] = await Promise.all([
        fetch(`${API_URL}/api/geographic/facilities`),
        fetch(`${API_URL}/api/geographic/compare`),
      ]);

      if (facilitiesRes.ok) {
        const data = await facilitiesRes.json();
        setFacilities(data.facilities || []);
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

  const filteredFacilities = useMemo(() => {
    if (!selectedCompany) return facilities;
    if (selectedCompany === SHARED_FILTER) return [];
    return facilities.filter((f) => f.company === selectedCompany);
  }, [facilities, selectedCompany]);

  const sortedFacilities = useMemo(() => {
    return [...filteredFacilities].sort((a, b) => {
      // In "All" mode, prioritize by company order first.
      if (selectedCompany === null) {
        const aCompanyRank = COMPANY_SORT_ORDER[a.company] ?? 999;
        const bCompanyRank = COMPANY_SORT_ORDER[b.company] ?? 999;
        if (aCompanyRank !== bCompanyRank) return aCompanyRank - bCompanyRank;

        // In "All" mode, apply custom country ordering only within Flex cards.
        if (a.company === 'Flex' && b.company === 'Flex') {
          const aRegionRank = FLEX_REGION_SORT_ORDER[getFlexRegion(a.country)];
          const bRegionRank = FLEX_REGION_SORT_ORDER[getFlexRegion(b.country)];
          if (aRegionRank !== bRegionRank) return aRegionRank - bRegionRank;

          const aCountryRank = FLEX_COUNTRY_SORT_ORDER[a.country] ?? 999;
          const bCountryRank = FLEX_COUNTRY_SORT_ORDER[b.country] ?? 999;
          if (aCountryRank !== bCountryRank) return aCountryRank - bCountryRank;
        }
      }

      // In single-company mode, group by continent first, then country.
      if (selectedCompany !== null) {
        const aContinentRank = CONTINENT_SORT_ORDER[getContinentByCountry(a.country)];
        const bContinentRank = CONTINENT_SORT_ORDER[getContinentByCountry(b.country)];
        if (aContinentRank !== bContinentRank) return aContinentRank - bContinentRank;
      }

      const countryCmp = a.country.localeCompare(b.country);
      if (countryCmp !== 0) return countryCmp;
      if (a.is_headquarters !== b.is_headquarters) return a.is_headquarters ? -1 : 1;
      return a.city.localeCompare(b.city);
    });
  }, [filteredFacilities, selectedCompany]);

  const chartFacilities = useMemo(() => {
    if (selectedCompany && selectedCompany !== SHARED_FILTER) {
      return facilities.filter((f) => f.company === selectedCompany);
    }
    return facilities;
  }, [facilities, selectedCompany]);

  const facilityCountData = useMemo(() => {
    const counts = chartFacilities.reduce((acc, f) => {
      acc[f.company] = (acc[f.company] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    return Object.entries(counts)
      .sort((a, b) => (COMPANY_SORT_ORDER[a[0]] ?? 999) - (COMPANY_SORT_ORDER[b[0]] ?? 999))
      .map(([company, count]) => ({
        company,
        count,
        fill: COMPANY_COLORS[company] || '#64748B',
      }));
  }, [chartFacilities]);

  const regionalData = useMemo(() => {
    const distributionByCompany: Record<string, { Americas: number; EMEA: number; APAC: number }> = {};

    chartFacilities.forEach((facility) => {
      const company = facility.company;
      if (!distributionByCompany[company]) {
        distributionByCompany[company] = { Americas: 0, EMEA: 0, APAC: 0 };
      }

      const region = getMarketRegionByCountry(facility.country);
      if (region === 'americas') distributionByCompany[company].Americas += 1;
      if (region === 'europe') distributionByCompany[company].EMEA += 1;
      if (region === 'asia') distributionByCompany[company].APAC += 1;
    });

    return Object.entries(distributionByCompany)
      .sort((a, b) => (COMPANY_SORT_ORDER[a[0]] ?? 999) - (COMPANY_SORT_ORDER[b[0]] ?? 999))
      .map(([company, values]) => ({
        company,
        total: values.Americas + values.EMEA + values.APAC,
        ...values,
      }));
  }, [chartFacilities]);

  const overlapLocations = useMemo(
    () => comparison?.overlap_analysis?.locations || {},
    [comparison]
  );
  const isSharedMode = selectedCompany === SHARED_FILTER;

  const sharedLocationCards = useMemo(() => {
    return Object.entries(overlapLocations)
      .map(([city, companies]) => ({ city, companies: companies as string[] }))
      .sort((a, b) => a.city.localeCompare(b.city));
  }, [overlapLocations]);

  const marketTabs = useMemo(() => {
    const regions = new Set<Exclude<MarketRegion, 'all'>>();
    facilities.forEach((facility) => {
      const region = getMarketRegionByCountry(facility.country);
      if (region !== 'other') regions.add(region);
    });
    const ordered: Exclude<MarketRegion, 'all'>[] = ['americas', 'europe', 'asia'];
    return ['all', ...ordered.filter((r) => regions.has(r))] as MarketRegion[];
  }, [facilities]);

  const visibleMapFacilities = useMemo(() => {
    const regionFiltered = marketRegion === 'all'
      ? facilities
      : facilities.filter(
      (facility) => getMarketRegionByCountry(facility.country) === marketRegion
    );
    if (!selectedMapCompany) return regionFiltered;
    return regionFiltered.filter((facility) => facility.company === selectedMapCompany);
  }, [facilities, marketRegion, selectedMapCompany]);

  const marketCompanyCards = useMemo(() => {
    const companies = Object.keys(COMPANY_SORT_ORDER).sort(
      (a, b) => (COMPANY_SORT_ORDER[a] ?? 999) - (COMPANY_SORT_ORDER[b] ?? 999)
    );

    return companies.map((company) => {
      const companyFacilities = facilities.filter((facility) => facility.company === company);
      const scopedFacilities =
        marketRegion === 'all'
          ? companyFacilities
          : companyFacilities.filter(
              (facility) => getMarketRegionByCountry(facility.country) === marketRegion
            );

      const total = companyFacilities.length;
      const scoped = scopedFacilities.length;
      const regionSet = new Set<Exclude<MarketRegion, 'all'>>();
      companyFacilities.forEach((facility) => {
        const region = getMarketRegionByCountry(facility.country);
        if (region !== 'other') regionSet.add(region);
      });
      const regions = (['americas', 'europe', 'asia'] as const)
        .filter((region) => regionSet.has(region))
        .map((region) => MARKET_REGION_LABELS[region]);

      return {
        company,
        total,
        scoped,
        regions,
      };
    });
  }, [facilities, marketRegion]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="relative">
            <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
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
              <Globe className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Geographic Analysis</h1>
              <p className="text-slate-500 dark:text-slate-400 mt-0.5 text-sm">Global facility mapping and regional distribution</p>
            </div>
          </div>
          <button
            onClick={fetchGeographicData}
            className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all shadow-sm"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Top Analytics Block */}
      <div className="grid items-start grid-cols-1 xl:grid-cols-[260px_minmax(0,1fr)_minmax(0,1fr)] gap-4 mb-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-1 gap-3">
          <Card className="border-0 shadow-xl !py-0 h-[64px]">
            <CardContent className="p-2 h-full">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-500 dark:text-slate-400 leading-none">Total Facilities</span>
                <Building2 className="h-4 w-4 text-blue-500" />
              </div>
              <p className="text-[17px] leading-none font-bold text-slate-900 dark:text-slate-100 mt-0.5">{facilities.length}</p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400 leading-none mt-0.5">Across all companies</p>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-xl !py-0 h-[64px]">
            <CardContent className="p-2 h-full">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-500 dark:text-slate-400 leading-none">Shared Locations</span>
                <Users className="h-4 w-4 text-purple-500" />
              </div>
              <p className="text-[17px] leading-none font-bold text-slate-900 dark:text-slate-100 mt-0.5">{Object.keys(overlapLocations).length}</p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400 leading-none mt-0.5">Cities with multiple companies</p>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-xl !py-0 h-[64px]">
            <CardContent className="p-2 h-full">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-500 dark:text-slate-400 leading-none">APAC Leader</span>
                <MapPin className="h-4 w-4 text-green-500" />
              </div>
              <p className="text-[17px] leading-none font-bold text-slate-900 dark:text-slate-100 mt-0.5">{comparison?.regional_leaders?.APAC?.company || 'N/A'}</p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400 leading-none mt-0.5">{comparison?.regional_leaders?.APAC?.count || 0} facilities</p>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-xl !py-0 h-[64px]">
            <CardContent className="p-2 h-full">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-500 dark:text-slate-400 leading-none">Americas Leader</span>
                <Factory className="h-4 w-4 text-orange-500" />
              </div>
              <p className="text-[17px] leading-none font-bold text-slate-900 dark:text-slate-100 mt-0.5">{comparison?.regional_leaders?.Americas?.company || 'N/A'}</p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400 leading-none mt-0.5">{comparison?.regional_leaders?.Americas?.count || 0} facilities</p>
            </CardContent>
          </Card>
        </div>

        {/* Facility Count by Company */}
        <Card className="border-0 shadow-xl !py-0 h-fit self-start">
          <CardHeader className="pb-1 pt-3 px-4">
            <CardTitle className="flex items-center gap-2 text-xl">
              <Building2 className="h-5 w-5 text-blue-600" />
              Facilities by Company
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 pb-3 px-3">
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={facilityCountData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="company" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" name="Facilities" radius={[4, 4, 0, 0]}>
                  <LabelList
                    dataKey="count"
                    position="top"
                    offset={6}
                    className="fill-slate-600 text-xs font-medium"
                  />
                  {facilityCountData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Regional Distribution */}
        <Card className="border-0 shadow-xl !py-0 h-fit self-start">
          <CardHeader className="pb-1 pt-3 px-4">
            <CardTitle className="flex items-center gap-2 text-xl">
              <Globe className="h-5 w-5 text-green-600" />
              Regional Distribution
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 pb-3 px-3">
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={regionalData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="company" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="Americas" stackId="a" fill="#3B82F6" />
                <Bar dataKey="EMEA" stackId="a" fill="#8B5CF6" />
                <Bar dataKey="APAC" stackId="a" fill="#10B981">
                  <LabelList
                    dataKey="total"
                    position="top"
                    offset={6}
                    className="fill-slate-600 text-xs font-medium"
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Facility List */}
      <Card className="border-0 shadow-xl">
        <CardHeader className="pb-2">
          <CardTitle>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <MapPin className="h-5 w-5 text-red-500" />
                Facility Locations
              </div>
              <Badge variant="secondary">
                {isSharedMode ? sharedLocationCards.length : filteredFacilities.length} locations
              </Badge>
            </div>
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              <span className="text-sm font-normal text-slate-500 dark:text-slate-400 mr-1">Filter:</span>
              <button
                onClick={() => setSelectedCompany(null)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  selectedCompany === null
                    ? 'bg-slate-900 text-white'
                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700'
                }`}
              >
                All
              </button>
              {Object.keys(COMPANY_COLORS).map((company) => (
                <button
                  key={company}
                  onClick={() => setSelectedCompany(company)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                    selectedCompany === company
                      ? 'text-white'
                      : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700'
                  }`}
                  style={{
                    backgroundColor: selectedCompany === company ? COMPANY_COLORS[company] : undefined,
                  }}
                >
                  {company}
                </button>
              ))}
              <button
                onClick={() => setSelectedCompany(SHARED_FILTER)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  isSharedMode
                    ? 'bg-purple-600 text-white'
                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700'
                }`}
              >
                Shared
              </button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0 h-[270px] overflow-y-auto pr-1" style={{ scrollbarGutter: 'stable' }}>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-5 gap-2.5">
            {isSharedMode
              ? sharedLocationCards.map(({ city, companies }) => (
                  <div
                    key={city}
                    className="p-2 rounded-lg border-2 transition-all hover:shadow-sm bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600"
                  >
                    <div className="mb-1.5 flex items-center gap-2">
                      <div className="flex items-center gap-2">
                        <Users className="h-4 w-4 text-purple-600" />
                        <span className="text-[15px] font-semibold leading-tight text-slate-900 dark:text-slate-100">{city}</span>
                      </div>
                    </div>
                    <div className="mb-1.5 flex flex-wrap gap-1">
                      {companies.map((company) => (
                        <Badge
                          key={company}
                          className="text-[11px]"
                          style={{
                            backgroundColor: COMPANY_COLORS[company],
                            color: 'white',
                            borderColor: COMPANY_COLORS[company],
                          }}
                        >
                          {company}
                        </Badge>
                      ))}
                    </div>
                    <div className="mt-1 text-[12px] text-slate-500 dark:text-slate-400">
                      Shared by {companies.length} companies
                    </div>
                  </div>
                ))
              : sortedFacilities.map((facility, idx) => (
                  <div
                    key={idx}
                    className="p-2 rounded-lg border-2 transition-all hover:shadow-sm bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 min-h-[84px]"
                  >
                    <div className="mb-1.5 flex items-center gap-2">
                      <div className="flex items-center gap-2">
                        {facility.is_headquarters ? (
                          <Briefcase className="h-4 w-4 text-amber-600" />
                        ) : (
                          <Factory className="h-4 w-4 text-slate-400" />
                        )}
                        <span className="text-[15px] font-semibold leading-tight text-slate-900 dark:text-slate-100">{facility.city}</span>
                      </div>
                      <Badge 
                        className="text-[11px]"
                        style={{ 
                          backgroundColor: `${COMPANY_COLORS[facility.company]}20`,
                          color: COMPANY_COLORS[facility.company],
                          borderColor: COMPANY_COLORS[facility.company],
                        }}
                      >
                        {facility.company}
                      </Badge>
                      {facility.website && (
                        <a
                          href={facility.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          title="Open site"
                          aria-label={`Open site for ${facility.city}`}
                          className="inline-flex items-center justify-center h-6 w-6 rounded-md border border-slate-200 dark:border-slate-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-slate-800"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                    </div>
                    <div className="mt-1 grid grid-cols-2 gap-1.5 text-[12px]">
                      <span className="inline-flex items-center gap-1 text-slate-500 dark:text-slate-400">
                        <span aria-hidden="true">{getCountryFlag(facility.country)}</span>
                        <span>{facility.country}</span>
                      </span>
                      <span className="text-slate-400 dark:text-slate-500">{facility.type}</span>
                    </div>
                  </div>
                ))}
          </div>
        </CardContent>
      </Card>

      {/* Market Index Map (V1) */}
      <Card className="border-0 shadow-xl mt-4 overflow-hidden bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100">
        <CardHeader className="pb-2">
          <CardTitle>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Globe className="h-5 w-5 text-emerald-500 dark:text-emerald-400" />
                Factory Footprint Globe
              </div>
              <Badge className="bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700">
                Beta
              </Badge>
            </div>
          </CardTitle>
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            {marketTabs.map((region) => (
              <button
                key={region}
                onClick={() => setMarketRegion(region)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all border ${
                  marketRegion === region
                    ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 border-slate-900 dark:border-slate-100'
                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'
                }`}
              >
                {MARKET_REGION_LABELS[region]}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="pt-1 pb-4">
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4">
            <div className="relative h-full min-h-[440px] overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
              <MapContainer
                center={REGION_VIEW.all.center}
                zoom={REGION_VIEW.all.zoom}
                minZoom={2}
                maxZoom={7}
                scrollWheelZoom={false}
                className="h-full w-full"
              >
                <RegionMapController region={marketRegion} />
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                {visibleMapFacilities.map((facility, idx) => (
                  <CircleMarker
                    key={`${facility.company}-${facility.city}-${idx}`}
                    center={[facility.lat, facility.lng]}
                    radius={6}
                    pathOptions={{
                      color: COMPANY_COLORS[facility.company] || '#0ea5e9',
                      fillColor: COMPANY_COLORS[facility.company] || '#0ea5e9',
                      fillOpacity: 1,
                      weight: 2,
                    }}
                  >
                    <LeafletTooltip direction="top" offset={[0, -4]} opacity={0.95}>
                      <div className="text-xs">
                        <div className="font-semibold">{facility.city}</div>
                        <div>{facility.company} • {facility.country}</div>
                      </div>
                    </LeafletTooltip>
                  </CircleMarker>
                ))}
              </MapContainer>
              <div className="pointer-events-none absolute left-3 bottom-3 z-[500] rounded-md bg-white/90 dark:bg-slate-900/85 border border-slate-200 dark:border-slate-700 px-2 py-1 text-[12px] text-slate-600 dark:text-slate-300">
                View: {MARKET_REGION_LABELS[marketRegion]} • {selectedMapCompany || 'All Companies'} • {visibleMapFacilities.length} sites
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2.5">
              {marketCompanyCards.map((row) => (
                <button
                  key={row.company}
                  type="button"
                  onClick={() =>
                    setSelectedMapCompany((prev) => (prev === row.company ? null : row.company))
                  }
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
                    <div>
                      Sites: <span className="font-semibold text-slate-900 dark:text-slate-100">{row.total}</span>
                    </div>
                    <div className="mt-1">
                      Regions: <span className="font-semibold text-slate-900 dark:text-slate-100">{row.regions.join(' • ') || 'N/A'}</span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

    </div>
  );
}
