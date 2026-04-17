'use client';

import { useEffect } from 'react';
import type { LatLngExpression } from 'leaflet';
import { MapContainer, TileLayer, CircleMarker, Tooltip as LeafletTooltip, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

const COMPANY_COLORS: Record<string, string> = {
  Flex: '#2563EB',
  Jabil: '#16A34A',
  Sanmina: '#DC2626',
  Celestica: '#7C3AED',
  Plexus: '#D97706',
  Benchmark: '#0891B2',
};

type MarketRegion = 'all' | 'americas' | 'europe' | 'asia';

const REGION_VIEW: Record<MarketRegion, { center: LatLngExpression; zoom: number }> = {
  all: { center: [20, 15], zoom: 2 },
  americas: { center: [28, -85], zoom: 3 },
  europe: { center: [50, 12], zoom: 4 },
  asia: { center: [28, 105], zoom: 4 },
};

interface Facility {
  company: string;
  city: string;
  country: string;
  lat: number;
  lng: number;
  type: string;
  is_shared_location: boolean;
  shared_with: string[];
}

function RegionMapController({ region }: { region: MarketRegion }) {
  const map = useMap();
  useEffect(() => {
    const view = REGION_VIEW[region];
    map.flyTo(view.center, view.zoom, { duration: 0.8 });
  }, [map, region]);
  return null;
}

interface GlobeMapProps {
  facilities: Facility[];
  marketRegion: MarketRegion;
}

export default function GlobeMap({ facilities, marketRegion }: GlobeMapProps) {
  return (
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
      {facilities.map((facility, idx) => {
        const isShared = facility.is_shared_location;
        return (
          <CircleMarker
            key={`${facility.company}-${facility.city}-${idx}`}
            center={[facility.lat, facility.lng]}
            radius={isShared ? 9 : 6}
            pathOptions={{
              color: isShared ? '#a855f7' : (COMPANY_COLORS[facility.company] || '#0ea5e9'),
              fillColor: COMPANY_COLORS[facility.company] || '#0ea5e9',
              fillOpacity: isShared ? 0.8 : 1,
              weight: isShared ? 3 : 2,
            }}
          >
            <LeafletTooltip direction="top" offset={[0, -4]} opacity={0.95}>
              <div className="text-xs">
                <div className="font-semibold">
                  {facility.city}, {facility.country}
                  {isShared && ' ⭐'}
                </div>
                <div>{facility.company} ({facility.type})</div>
                {isShared && facility.shared_with.length > 0 && (
                  <div className="text-slate-500 mt-0.5">
                    Also: {facility.shared_with.join(', ')}
                  </div>
                )}
              </div>
            </LeafletTooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
