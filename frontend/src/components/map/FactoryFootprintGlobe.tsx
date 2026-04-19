'use client';

import { useEffect } from 'react';
import type { LatLngTuple } from 'leaflet';
import { CircleMarker, MapContainer, TileLayer, Tooltip as LeafletTooltip, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

type MarketRegion = 'all' | 'americas' | 'europe' | 'asia';

interface Facility {
  company: string;
  city: string;
  country: string;
  lat: number;
  lng: number;
}

interface FactoryFootprintGlobeProps {
  marketRegion: MarketRegion;
  facilities: Facility[];
  companyColors: Record<string, string>;
}

const REGION_VIEW: Record<MarketRegion, { center: LatLngTuple; zoom: number }> = {
  all: { center: [20, 15], zoom: 2 },
  americas: { center: [28, -85], zoom: 3 },
  europe: { center: [50, 12], zoom: 4 },
  asia: { center: [28, 105], zoom: 4 },
};

function RegionMapController({ region }: { region: MarketRegion }) {
  const map = useMap();

  useEffect(() => {
    const view = REGION_VIEW[region];
    map.flyTo(view.center, view.zoom, { duration: 0.8 });
  }, [map, region]);

  return null;
}

export default function FactoryFootprintGlobe({
  marketRegion,
  facilities,
  companyColors,
}: FactoryFootprintGlobeProps) {
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
      {facilities.map((facility, idx) => (
        <CircleMarker
          key={`${facility.company}-${facility.city}-${idx}`}
          center={[facility.lat, facility.lng]}
          radius={6}
          pathOptions={{
            color: companyColors[facility.company] || '#0ea5e9',
            fillColor: companyColors[facility.company] || '#0ea5e9',
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
  );
}
