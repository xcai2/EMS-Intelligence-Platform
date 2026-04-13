/**
 * Section 1: Company intelligence — outbound links by ticker.
 * URL patterns follow public Benzinga / Seeking Alpha / TipRanks stock pages.
 */

export type CompanyIntelKind = 'EMS' | 'Hyperscaler';

export type CompanyIntelRow = {
  company: string;
  ticker: string;
  kind: CompanyIntelKind;
};

/** EMS competitors + Plexus + hyperscalers per practicum reference (April 2026). */
export const COMPANY_INTEL_ROSTER: CompanyIntelRow[] = [
  { company: 'Flex', ticker: 'FLEX', kind: 'EMS' },
  { company: 'Jabil', ticker: 'JBL', kind: 'EMS' },
  { company: 'Celestica', ticker: 'CLS', kind: 'EMS' },
  { company: 'Benchmark Electronics', ticker: 'BHE', kind: 'EMS' },
  { company: 'Sanmina', ticker: 'SANM', kind: 'EMS' },
  { company: 'Plexus', ticker: 'PLXS', kind: 'EMS' },
  { company: 'Amazon (AWS)', ticker: 'AMZN', kind: 'Hyperscaler' },
  { company: 'Microsoft (Azure)', ticker: 'MSFT', kind: 'Hyperscaler' },
  { company: 'Alphabet (Google Cloud)', ticker: 'GOOGL', kind: 'Hyperscaler' },
  { company: 'Meta', ticker: 'META', kind: 'Hyperscaler' },
  { company: 'Apple', ticker: 'AAPL', kind: 'Hyperscaler' },
  { company: 'Oracle', ticker: 'ORCL', kind: 'Hyperscaler' },
];

export function benzingaAnalystRatingsUrl(ticker: string): string {
  return `https://www.benzinga.com/quotev2/${encodeURIComponent(ticker)}/analyst-ratings`;
}

export function seekingAlphaTranscriptsUrl(ticker: string): string {
  return `https://seekingalpha.com/symbol/${encodeURIComponent(ticker)}/earnings/transcripts`;
}

export function tipRanksStockForecastUrl(ticker: string): string {
  return `https://www.tipranks.com/stocks/${encodeURIComponent(ticker)}/forecast`;
}
