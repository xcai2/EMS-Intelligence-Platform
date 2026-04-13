/**
 * Section 2: Analyst intelligence — TipRanks expert profiles, optional firm site, optional X.
 * `core`: original designated list (#1–7). Rows #8–19 from earnings / IR follow-on coverage.
 *
 * `linkedinUrl`: use when a public profile is verified. For the first 11 rows, if omitted we link to
 * a LinkedIn people search (discovery); rows 12–19 show "—" when omitted (per reference doc).
 */
export type AnalystRow = {
  /** Original core roster (#1–7). */
  core: boolean;
  institution: string;
  leadAnalyst: string;
  coverageFocus: string;
  firmUrl?: string;
  tipranksUrl: string;
  /** Verified LinkedIn profile URL; if omitted, see `analystLinkedInHref`. */
  linkedinUrl?: string;
  /** Official X handle when confirmed (with or without @). Omitted → search link only in X tools. */
  xHandle?: string;
};

/** First N analyst rows use LinkedIn search when `linkedinUrl` is not set. */
export const ANALYST_LINKEDIN_SEARCH_ROW_COUNT = 11;

/** Article linked from stakeholder context (EMS industry / valuation). */
export const STAKEHOLDER_REFERENCE_ARTICLE = {
  title:
    'Unpacking Q4 Earnings: Flex (NASDAQ:FLEX) In The Context Of Other Electronic Components & Manufacturing Stocks',
  url: 'https://stockstory.org/us/stocks/nasdaq/flex/news/earnings/unpacking-q4-earnings-flex-nasdaqflex-in-the-context-of-other-electronic-components-and-manufacturing-stocks',
} as const;

export const ANALYST_ROSTER: AnalystRow[] = [
  {
    core: true,
    institution: 'BMO Capital Markets',
    leadAnalyst: 'Thanos Moschopoulos',
    coverageFocus: 'Celestica, Jabil, broad EMS tech.',
    firmUrl: 'https://capitalmarkets.bmo.com/en/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/thanos-moschopoulos',
  },
  {
    core: true,
    institution: 'Stifel (now independent)',
    leadAnalyst: 'Matthew Sheerin',
    coverageFocus: 'Flex, Sanmina, Plexus.',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/matthew-sheerin',
  },
  {
    core: true,
    institution: 'JPMorgan',
    leadAnalyst: 'Samik Chatterjee',
    coverageFocus: 'Broad IT Networking & EMS; Sanmina.',
    firmUrl: 'https://www.jpmorgan.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/samik-chatterjee',
  },
  {
    core: true,
    institution: 'Needham & Company',
    leadAnalyst: 'James Ricchiuti',
    coverageFocus: 'Advanced manufacturing, Benchmark, Plexus.',
    firmUrl: 'https://www.needhamco.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/james-ricchiuti',
  },
  {
    core: true,
    institution: 'RBC Capital Markets',
    leadAnalyst: 'Maxim Matushansky',
    coverageFocus: 'Celestica, diversified industrials.',
    firmUrl: 'https://www.rbccm.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/maxim-matushansky',
  },
  {
    core: true,
    institution: 'TD Securities',
    leadAnalyst: 'Daniel Chan',
    coverageFocus: 'Canadian tech corridor, Celestica.',
    firmUrl: 'https://tdsecurities.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/daniel-chan',
  },
  {
    core: true,
    institution: 'Canaccord Genuity',
    leadAnalyst: 'Robert Young',
    coverageFocus: 'Small-to-mid cap tech, supply chain.',
    firmUrl: 'https://www.canaccordgenuity.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/robert-young',
  },
  {
    core: false,
    institution: 'Goldman Sachs',
    leadAnalyst: 'Mark Delaney',
    coverageFocus: 'Flex, Jabil, broad EMS/tech hardware.',
    firmUrl: 'https://www.gs.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/mark-delaney',
  },
  {
    core: false,
    institution: 'Barclays',
    leadAnalyst: 'Timothy Long',
    coverageFocus: 'Flex, Celestica, EMS sector.',
    firmUrl: 'https://www.investmentbank.barclays.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/timothy-long',
  },
  {
    core: false,
    institution: 'Barclays',
    leadAnalyst: 'George Wang',
    coverageFocus: 'Flex, EMS sector.',
    firmUrl: 'https://www.investmentbank.barclays.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/george-wang',
  },
  {
    core: false,
    institution: 'Bank of America',
    leadAnalyst: 'Ruplu Bhattacharya',
    coverageFocus: 'Flex, Jabil, supply chain tech.',
    firmUrl: 'https://business.bofa.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/ruplu-bhattacharya',
  },
  {
    core: false,
    institution: 'KeyBanc Capital Markets',
    leadAnalyst: 'Jacob Moore',
    coverageFocus: 'Flex, industrials, EMS.',
    firmUrl: 'https://www.key.com/kcb/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/jacob-moore',
  },
  {
    core: false,
    institution: 'KeyBanc Capital Markets',
    leadAnalyst: 'Steven Barger',
    coverageFocus: 'Flex, industrials.',
    firmUrl: 'https://www.key.com/kcb/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/steven-barger',
  },
  {
    core: false,
    institution: 'Fox Advisors (independent)',
    leadAnalyst: 'Steven Fox',
    coverageFocus: 'Flex, EMS sector specialist.',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/steven-fox',
  },
  {
    core: false,
    institution: 'Stifel',
    leadAnalyst: 'Ruben Roy',
    coverageFocus: 'Flex, Celestica.',
    firmUrl: 'https://www.stifel.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/ruben-roy',
  },
  {
    core: false,
    institution: 'CIBC World Markets',
    leadAnalyst: 'Todd Coupland',
    coverageFocus: 'Celestica, Canadian tech.',
    firmUrl: 'https://www.cibc.com/en/commercial-banking/cibc-world-markets.html',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/todd-coupland',
  },
  {
    core: false,
    institution: 'RBC Capital Markets',
    leadAnalyst: 'Paul Treiber',
    coverageFocus: 'Celestica.',
    firmUrl: 'https://www.rbccm.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/paul-treiber',
  },
  {
    core: false,
    institution: 'Citigroup',
    leadAnalyst: 'Atif Malik',
    coverageFocus: 'Celestica, semiconductors/EMS.',
    firmUrl: 'https://www.citigroup.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/atif-malik',
  },
  {
    core: false,
    institution: 'UBS',
    leadAnalyst: 'David Vogt',
    coverageFocus: 'Celestica, tech hardware.',
    firmUrl: 'https://www.ubs.com/',
    tipranksUrl: 'https://www.tipranks.com/experts/analysts/david-vogt',
  },
];

export function rosterRowKey(row: AnalystRow): string {
  return `${row.leadAnalyst}::${row.institution}`;
}

/** LinkedIn people search when no verified profile URL exists (rows 1–11 only). */
export function linkedInPeopleSearchUrl(analystName: string, institution: string): string {
  const cleaned = institution.replace(/\s*\(now independent\)\s*/i, '').trim();
  const q = `${analystName} ${cleaned}`;
  return `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(q)}`;
}

/**
 * Resolved href for the LinkedIn column: explicit profile, else search (first N rows), else null (show —).
 */
export function analystLinkedInHref(row: AnalystRow, indexZeroBased: number): string | null {
  if (row.linkedinUrl) return row.linkedinUrl;
  if (indexZeroBased < ANALYST_LINKEDIN_SEARCH_ROW_COUNT) {
    return linkedInPeopleSearchUrl(row.leadAnalyst, row.institution);
  }
  return null;
}

export function normalizeXHandle(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  const t = raw.trim();
  if (!t) return undefined;
  return t.startsWith('@') ? t.slice(1) : t;
}

export function xProfileUrl(handle: string | undefined): string | null {
  const h = normalizeXHandle(handle);
  if (!h) return null;
  return `https://x.com/${encodeURIComponent(h)}`;
}

export function xSearchUrlForAnalyst(leadAnalyst: string): string {
  const q = `${leadAnalyst} EMS OR "electronics manufacturing"`;
  return `https://x.com/search?q=${encodeURIComponent(q)}`;
}
