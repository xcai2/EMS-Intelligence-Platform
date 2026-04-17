'use client';

import { ExternalLink, Info } from 'lucide-react';

interface ChartDescriptionProps {
  description: string;
  source?: string;
  sourceUrl?: string;
  lastUpdated?: string;
}

export function ChartDescription({ description, source, sourceUrl, lastUpdated }: ChartDescriptionProps) {
  return (
    <div className="mt-3 pt-3 border-t border-slate-100">
      <div className="flex items-start gap-2">
        <Info className="h-4 w-4 text-slate-400 mt-0.5 flex-shrink-0" />
        <div>
          <p className="text-sm text-slate-600">{description}</p>
          {(source || lastUpdated) && (
            <p className="text-xs text-slate-400 mt-1">
              {source && sourceUrl ? (
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-blue-500 hover:text-blue-400"
                >
                  Source: {source} <ExternalLink className="h-3 w-3" />
                </a>
              ) : (
                source && <span>Source: {source}</span>
              )}
              {source && lastUpdated && <span> • </span>}
              {lastUpdated && <span>Updated: {lastUpdated}</span>}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
