'use client';

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { 
  Globe, 
  MapPin, 
  Building2, 
  RefreshCw,
  Factory,
  Briefcase,
  Filter
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

// Dynamically import the map component to avoid SSR issues
const MapComponent = dynamic(() => import('@/components/map/LeafletMap'), {
  ssr: false,
  loading: () => (
    <div className="h-[500px] bg-slate-100 rounded-xl flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600 mx-auto mb-4"></div>
        <p className="text-slate-600">Loading map...</p>
      </div>
    </div>
  ),
});

const COMPANY_COLORS: Record<string, string> = {
  Flex: '#3B82F6',
  Jabil: '#10B981',
  Celestica: '#6366F1',
  Benchmark: '#F59E0B',
  Sanmina: '#EF4444',
  Plexus: '#14B8A6',
};

interface Facility {
  company: string;
  city: string;
  country: string;
  lat: number;
  lng: number;
  type: string;
  is_headquarters: boolean;
}

export default function HeatmapPage() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [comparison, setComparison] = useState<any>(null);
  const [selectedCompanies, setSelectedCompanies] = useState<string[]>([
    'Flex', 'Jabil', 'Celestica', 'Benchmark', 'Sanmina', 'Plexus'
  ]);
  const [facilityType, setFacilityType] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
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
      console.error('Failed to fetch data:', err);
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

  const filteredFacilities = facilities.filter(f => {
    if (!selectedCompanies.includes(f.company)) return false;
    if (facilityType !== 'all' && f.type !== facilityType) return false;
    return true;
  });

  const facilityTypes = [...new Set(facilities.map(f => f.type))];
  const overlapLocations = comparison?.overlap_analysis?.locations || {};

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
          <p className="text-slate-600 mt-4 font-medium">Loading map data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="bg-gradient-to-br from-green-500 to-teal-600 p-3 rounded-xl shadow-lg shadow-green-500/20">
              <Globe className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-slate-900">Global Facility Heatmap</h1>
              <p className="text-slate-500 mt-1">Interactive map of EMS company manufacturing locations</p>
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

      {/* Filters */}
      <Card className="border-0 shadow-xl mb-6">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            {/* Company Filter */}
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-slate-500" />
              <span className="text-sm text-slate-600 font-medium">Companies:</span>
            </div>
            {Object.keys(COMPANY_COLORS).map((company) => {
              const isSelected = selectedCompanies.includes(company);
              return (
                <button
                  key={company}
                  onClick={() => toggleCompany(company)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                    isSelected
                      ? 'text-white shadow-md'
                      : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                  }`}
                  style={{
                    backgroundColor: isSelected ? COMPANY_COLORS[company] : undefined,
                  }}
                >
                  <div 
                    className={`w-2 h-2 rounded-full ${isSelected ? 'bg-white' : ''}`}
                    style={{ backgroundColor: isSelected ? undefined : COMPANY_COLORS[company] }}
                  />
                  {company}
                </button>
              );
            })}
            
            {/* Divider */}
            <div className="w-px h-6 bg-slate-200" />
            
            {/* Type Filter */}
            <span className="text-sm text-slate-600 font-medium">Type:</span>
            <select
              value={facilityType}
              onChange={(e) => setFacilityType(e.target.value)}
              className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm bg-white"
            >
              <option value="all">All Types</option>
              {facilityTypes.map(type => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
            
            <Badge variant="secondary" className="ml-auto">
              {filteredFacilities.length} locations
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Map */}
      <Card className="border-0 shadow-xl mb-6 overflow-hidden">
        <CardContent className="p-0">
          <MapComponent 
            facilities={filteredFacilities} 
            companyColors={COMPANY_COLORS}
          />
        </CardContent>
      </Card>

      {/* Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card className="border-0 shadow-lg">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="bg-blue-100 p-2 rounded-lg">
                <Building2 className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{filteredFacilities.length}</p>
                <p className="text-xs text-slate-500">Total Facilities</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-lg">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="bg-amber-100 p-2 rounded-lg">
                <Briefcase className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">
                  {filteredFacilities.filter(f => f.is_headquarters).length}
                </p>
                <p className="text-xs text-slate-500">Headquarters</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-lg">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="bg-green-100 p-2 rounded-lg">
                <Factory className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">
                  {filteredFacilities.filter(f => f.type === 'Manufacturing').length}
                </p>
                <p className="text-xs text-slate-500">Manufacturing Sites</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-lg">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="bg-purple-100 p-2 rounded-lg">
                <MapPin className="h-5 w-5 text-purple-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">
                  {Object.keys(overlapLocations).length}
                </p>
                <p className="text-xs text-slate-500">Shared Locations</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Shared Locations */}
      {Object.keys(overlapLocations).length > 0 && (
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MapPin className="h-5 w-5 text-purple-600" />
              Competitive Proximity - Shared Manufacturing Hubs
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {Object.entries(overlapLocations).map(([city, companies]) => (
                <div
                  key={city}
                  className="p-4 bg-gradient-to-br from-purple-50 to-blue-50 rounded-xl border border-purple-100"
                >
                  <h4 className="font-semibold text-slate-900 mb-2">{city}</h4>
                  <div className="flex flex-wrap gap-1">
                    {(companies as string[]).map((company) => (
                      <div
                        key={company}
                        className="w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold"
                        style={{ backgroundColor: COMPANY_COLORS[company] }}
                        title={company}
                      >
                        {company.charAt(0)}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
