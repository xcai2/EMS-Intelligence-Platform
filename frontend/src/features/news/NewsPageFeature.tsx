'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  RefreshCw,
  Flame,
  Clock3,
  ExternalLink,
  Rss,
  Globe2,
  Github,
  ChevronDown,
  Search,
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
const PROJECT_GITHUB_URL = 'https://github.com/xcai2/Flex-Practicum-Project-2026';

const COMPANY_TICKERS = ['FLEX', 'JBL', 'CLS', 'BHE', 'SANM'] as const;
type CompanyTicker = (typeof COMPANY_TICKERS)[number];

const COMPANY_NAMES: Record<CompanyTicker, string> = {
  FLEX: 'Flex',
  JBL: 'Jabil',
  CLS: 'Celestica',
  BHE: 'Benchmark',
  SANM: 'Sanmina',
};

const COMPANY_BADGE_LABELS: Record<CompanyTicker, string> = {
  FLEX: 'FLEX',
  JBL: 'Jabil',
  CLS: 'Celestica',
  BHE: 'Benchmark',
  SANM: 'Sanmina',
};

const COMPANY_COLORS: Record<CompanyTicker, string> = {
  FLEX: '#3B82F6',
  JBL: '#10B981',
  CLS: '#6366F1',
  BHE: '#F59E0B',
  SANM: '#EF4444',
};

const COMPANY_WEBSITES: Record<CompanyTicker, string> = {
  JBL: 'https://www.jabil.com/',
  FLEX: 'https://flex.com/newsroom',
  BHE: 'https://www.bench.com/',
  SANM: 'https://www.sanmina.com/',
  CLS: 'https://www.celestica.com/',
};

const KEYWORD_PRESETS = [
  { label: 'Data Center', value: 'data center' },
  { label: 'AI', value: 'ai' },
  { label: 'CapEx', value: 'capex, capital expenditure, capital spending, capital investment, facility expansion' },
  { label: 'Liquid Cooling', value: 'liquid cooling' },
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  earnings: 'Earnings',
  ai: 'AI',
  capex: 'CapEx',
  strategy: 'Strategy',
  operations: 'Operations',
  general: 'General',
};

const CATEGORY_TINTS: Record<string, string> = {
  earnings: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-400/20',
  ai: 'bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-500/15 dark:text-violet-300 dark:border-violet-400/20',
  capex: 'bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-500/15 dark:text-orange-300 dark:border-orange-400/20',
  strategy: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-400/20',
  operations: 'bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-500/15 dark:text-cyan-300 dark:border-cyan-400/20',
  general: 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-500/15 dark:text-slate-300 dark:border-slate-400/20',
};

const PRIORITY_TECH_TERMS = ['ai', 'artificial intelligence', 'data center'];
const STRICT_COMPANY_TERMS: Record<CompanyTicker, string[]> = {
  FLEX: ['flex ltd', 'nasdaq:flex', 'flex (nasdaq', 'flex ltd holdings', 'flextronics'],
  JBL: ['jabil', 'jabil inc'],
  CLS: ['celestica'],
  BHE: ['benchmark electronics'],
  SANM: ['sanmina'],
};
const COMPANY_DOMAIN_HINTS: Record<CompanyTicker, string[]> = {
  FLEX: ['flex.com'],
  JBL: ['jabil.com'],
  CLS: ['celestica.com'],
  BHE: ['bench.com'],
  SANM: ['sanmina.com'],
};
const EXCLUDED_NOISE_PATTERNS = [
  'flex office',
  'flex workspace',
  'flex industrial properties',
  'flex lng',
  'flex plan',
  'flex award',
  'flex pricing',
  'flex modular',
  'flex wing',
  'flex force',
  'flex system',
  'benchmark interest rate',
  'benchmark awards',
  'benchmark arena',
  'benchmark report',
  'benchmark test',
  'benchmark results',
  'ai benchmark',
  'cpu benchmark',
  'performance benchmark',
  'jbl speaker',
  'jbl speakers',
  'jbl earbud',
  'jbl earbuds',
  'jbl headphone',
  'jbl headphones',
  'jbl bluetooth',
  'jbl soundbar',
];
const TOP_TIER_SOURCE_DOMAINS = [
  'reuters.com',
  'bloomberg.com',
  'wsj.com',
  'ft.com',
  'cnbc.com',
  'marketwatch.com',
  'finance.yahoo.com',
  'yahoo.com',
  'fool.com',
  'seekingalpha.com',
  'tipranks.com',
  'investing.com',
  'flex.com',
  'jabil.com',
  'celestica.com',
  'bench.com',
  'sanmina.com',
];
const FINANCIAL_SOURCE_DOMAINS = [
  'investopedia.com',
  'thestreet.com',
  'barrons.com',
  'zacks.com',
  'morningstar.com',
  'markets.businessinsider.com',
  'stocktwits.com',
];
const LEAD_STORY_SOURCE_WHITELIST = [
  'finance.yahoo.com',
  'reuters.com',
  'bloomberg.com',
  'cnbc.com',
  'marketwatch.com',
  'tipranks.com',
];
const TOP_NEWS_RECENT_DAYS = 7;
const TOP_NEWS_EXCLUDED_TERMS = ['presentation', 'investor presentation', '.pdf', ' pdf '];

const FALLBACK_FEED: UnifiedNewsItem[] = [
  {
    title: 'Flex expands AI infrastructure manufacturing programs',
    url: 'https://flex.com/newsroom',
    description: 'Flex reports sustained demand visibility across AI server and data-center related customer programs.',
    source: 'Flex Newsroom',
    categories: ['ai', 'operations'],
    company: 'FLEX',
    categoryLabel: 'AI',
    timestampLabel: 'Source feed',
  },
  {
    title: 'Jabil highlights cloud and AI platform momentum',
    url: 'https://www.jabil.com/about-us/news.html',
    description: 'Jabil comments on advanced compute and AI-capable infrastructure demand across enterprise and cloud customers.',
    source: 'Jabil Newsroom',
    categories: ['ai', 'strategy'],
    company: 'JBL',
    categoryLabel: 'AI',
    timestampLabel: 'Source feed',
  },
  {
    title: 'Industry watch: EMS capacity planning follows AI workload growth',
    url: 'https://www.eetimes.com/',
    description: 'Electronics manufacturing providers continue to rebalance investments around AI and data-center demand.',
    source: 'EE Times',
    categories: ['ai', 'capex'],
    categoryLabel: 'AI',
    timestampLabel: 'Source feed',
  },
];

interface NewsItem {
  title: string;
  url: string;
  backup_url?: string;
  description: string;
  image_url?: string;
  source: string;
  published?: string;
  categories: string[];
  relevance_score?: number;
}

interface UnifiedNewsItem extends NewsItem {
  company?: CompanyTicker;
  categoryLabel: string;
  timestampLabel: string;
}

interface CompanyBackendMeta {
  timestamp: string;
  totalFound: number;
  finalKeptCount: number;
}

interface BackendLoadMeta {
  mode: 'cache' | 'refresh';
  requestedAt: string;
  allTimestamp: string;
  industryTimestamp: string;
  industryTotalFound: number;
  comparativeTimestamp: string;
  comparativeTotalFound: number;
  companies: Record<CompanyTicker, CompanyBackendMeta>;
}

function getCategoryKey(categories?: string[]) {
  return categories?.[0] || 'general';
}

function formatPublishedLabel(raw?: string) {
  const value = (raw || '').trim();
  if (!value) return '';
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: '2-digit' });
  }
  return value;
}

function formatBackendTimestamp(raw?: string) {
  const value = (raw || '').trim();
  if (!value) return '--';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function toSafeNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function buildEmptyBackendLoadMeta(mode: 'cache' | 'refresh'): BackendLoadMeta {
  return {
    mode,
    requestedAt: new Date().toISOString(),
    allTimestamp: '',
    industryTimestamp: '',
    industryTotalFound: 0,
    comparativeTimestamp: '',
    comparativeTotalFound: 0,
    companies: {
      FLEX: { timestamp: '', totalFound: 0, finalKeptCount: 0 },
      JBL: { timestamp: '', totalFound: 0, finalKeptCount: 0 },
      CLS: { timestamp: '', totalFound: 0, finalKeptCount: 0 },
      BHE: { timestamp: '', totalFound: 0, finalKeptCount: 0 },
      SANM: { timestamp: '', totalFound: 0, finalKeptCount: 0 },
    },
  };
}

function extractCompanyBackendMeta(payload: unknown): CompanyBackendMeta {
  const companyPayload = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
  const diagnostics =
    companyPayload.diagnostics && typeof companyPayload.diagnostics === 'object'
      ? (companyPayload.diagnostics as Record<string, unknown>)
      : {};
  const pipelineCounts =
    diagnostics.pipeline_counts && typeof diagnostics.pipeline_counts === 'object'
      ? (diagnostics.pipeline_counts as Record<string, unknown>)
      : {};

  return {
    timestamp: typeof companyPayload.timestamp === 'string' ? companyPayload.timestamp : '',
    totalFound: toSafeNumber(companyPayload.total_found),
    finalKeptCount: toSafeNumber(pipelineCounts.final_kept) || toSafeNumber(companyPayload.total_found),
  };
}

function getPublishedTimestamp(raw?: string) {
  const value = (raw || '').trim();
  if (!value) return 0;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 0;
  return parsed.getTime();
}

function getPublishedDateKey(raw?: string) {
  const ts = getPublishedTimestamp(raw);
  if (!ts) return '';
  const d = new Date(ts);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function hasPublishedTime(raw?: string) {
  const value = (raw || '').trim();
  if (!value) return false;
  return /t\d{1,2}:\d{2}/i.test(value) || /\b\d{1,2}:\d{2}(:\d{2})?\b/.test(value);
}

function getPriorityScore(item: UnifiedNewsItem) {
  const content = `${item.title} ${item.description} ${(item.categories || []).join(' ')}`.toLowerCase();
  let score = 0;

  // Priority 1: tracked company news
  if (item.company) {
    score += 1000;
    // Flex gets the highest weight among tracked companies
    if (item.company === 'FLEX') score += 300;
  }

  // Priority 2: AI / Data Center intent
  if (PRIORITY_TECH_TERMS.some((term) => content.includes(term))) score += 200;

  // Secondary relevance signal from backend
  score += Math.round((item.relevance_score || 0) * 100);

  return score;
}

function toUnifiedItem(item: NewsItem, company?: CompanyTicker): UnifiedNewsItem {
  const categoryKey = getCategoryKey(item.categories);
  const publishedLabel = formatPublishedLabel(item.published);
  return {
    ...item,
    company,
    categoryLabel: CATEGORY_LABELS[categoryKey] || 'General',
    timestampLabel: publishedLabel || item.source || 'News source',
  };
}

function isTrackedOrAIRelated(item: UnifiedNewsItem) {
  const content = `${item.title} ${item.description} ${(item.categories || []).join(' ')}`.toLowerCase();

  // Step 1: hard negative filter for obvious misclassification.
  const hasExcludedPhrase = EXCLUDED_NOISE_PATTERNS.some((pattern) => content.includes(pattern));
  const isLikelyJblAudioNoise = /\bjbl\b/.test(content) && /(speaker|earbud|earbuds|headphone|headphones|soundbar|bluetooth)/.test(content);
  if (hasExcludedPhrase || isLikelyJblAudioNoise) return false;

  // Step 2: strict tracked-company matching.
  const strictCompanyMatch = isStrictTrackedCompanyMatch(item);
  if (!strictCompanyMatch) return false;

  // Step 3: once strict company matching passes, keep the item even if
  // business-keyword coverage is sparse to avoid dropping valid company news.
  return true;
}

function isStrictTrackedCompanyMatch(item: UnifiedNewsItem) {
  const text = `${item.title} ${item.description} ${(item.categories || []).join(' ')} ${item.source}`.toLowerCase();
  const domain = getDomain(item.url || item.backup_url || '');
  const hasTerm = (ticker: CompanyTicker) => STRICT_COMPANY_TERMS[ticker].some((term) => text.includes(term));
  const hasDomainHint = (ticker: CompanyTicker) => COMPANY_DOMAIN_HINTS[ticker].some((hint) => domain.endsWith(hint));

  // If backend provides ticker, still require textual/domain corroboration.
  if (item.company) {
    return hasTerm(item.company) || hasDomainHint(item.company);
  }

  // For non-tagged items, require strict textual company evidence only.
  return COMPANY_TICKERS.some((ticker) => hasTerm(ticker));
}

function normalizeTitle(raw: string) {
  return raw
    .toLowerCase()
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function getTitleSimilarity(a: string, b: string) {
  const na = normalizeTitle(a);
  const nb = normalizeTitle(b);
  if (!na || !nb) return 0;
  if (na === nb) return 1;
  const shorter = na.length <= nb.length ? na : nb;
  const longer = na.length > nb.length ? na : nb;
  const prefixLen = shorter
    .split('')
    .findIndex((char, idx) => longer[idx] !== char);
  const commonPrefix = prefixLen === -1 ? shorter.length : prefixLen;
  return commonPrefix / shorter.length;
}

function getSourceQualityScore(item: UnifiedNewsItem) {
  const domain = getDomain(item.url || item.backup_url || '');
  if (!domain) return 0;
  if (TOP_TIER_SOURCE_DOMAINS.some((d) => domain.endsWith(d))) return 3;
  if (FINANCIAL_SOURCE_DOMAINS.some((d) => domain.endsWith(d))) return 2;
  return 1;
}

function isLeadSourceAllowed(item: UnifiedNewsItem) {
  const domain = getDomain(item.url || item.backup_url || '');
  if (!domain) return false;
  return LEAD_STORY_SOURCE_WHITELIST.some((d) => domain.endsWith(d));
}

function pickHigherQualityItem(a: UnifiedNewsItem, b: UnifiedNewsItem) {
  const sourceDelta = getSourceQualityScore(b) - getSourceQualityScore(a);
  if (sourceDelta > 0) return b;
  if (sourceDelta < 0) return a;

  const timeDelta = getPublishedTimestamp(b.published) - getPublishedTimestamp(a.published);
  if (timeDelta > 0) return b;
  if (timeDelta < 0) return a;

  const relevanceDelta = (b.relevance_score || 0) - (a.relevance_score || 0);
  if (relevanceDelta > 0) return b;
  if (relevanceDelta < 0) return a;

  return a;
}

function dedupeBySimilarTitle(items: UnifiedNewsItem[]) {
  const deduped: UnifiedNewsItem[] = [];
  for (const current of items) {
    const duplicateIdx = deduped.findIndex((existing) => {
      // Avoid merging distinct company stories that happen to have similar wording.
      if (existing.company && current.company && existing.company !== current.company) return false;
      return getTitleSimilarity(existing.title, current.title) >= 0.8;
    });
    if (duplicateIdx === -1) {
      deduped.push(current);
    } else {
      deduped[duplicateIdx] = pickHigherQualityItem(deduped[duplicateIdx], current);
    }
  }
  return deduped;
}

function getDomain(url: string) {
  try {
    return new URL(url).hostname.replace('www.', '');
  } catch {
    return '';
  }
}

function getSafeHref(item: NewsItem) {
  const blocked = ['wsj.com', 'ft.com', 'barrons.com', 'bloomberg.com', 'seekingalpha.com', 'fool.com'];
  const domain = getDomain(item.url);
  const shouldUseBackup = blocked.some((d) => domain.endsWith(d));
  if (shouldUseBackup) return item.backup_url || `https://www.google.com/search?q=${encodeURIComponent(item.title)}`;
  return item.url || item.backup_url || '#';
}

function isTopNewsEligible(item: UnifiedNewsItem) {
  const content = `${item.title} ${item.description} ${item.source} ${item.url}`.toLowerCase();
  return !TOP_NEWS_EXCLUDED_TERMS.some((term) => content.includes(term));
}

export default function NewsPage() {
  const [selectedCompany, setSelectedCompany] = useState<string>('ALL');
  const [keyword, setKeyword] = useState('');
  const [companyNews, setCompanyNews] = useState<Record<CompanyTicker, NewsItem[]>>({
    FLEX: [],
    JBL: [],
    CLS: [],
    BHE: [],
    SANM: [],
  });
  const [industryNews, setIndustryNews] = useState<NewsItem[]>([]);
  const [comparativeNews, setComparativeNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [newsSummaryExpanded, setNewsSummaryExpanded] = useState(true);
  const [backendLoadMeta, setBackendLoadMeta] = useState<BackendLoadMeta | null>(null);

  const fetchAllNews = async (showLoader = false, forceRefresh = false) => {
    if (showLoader) setLoading(true);
    try {
      const nextBackendLoadMeta = buildEmptyBackendLoadMeta(forceRefresh ? 'refresh' : 'cache');
      const refreshNonce = forceRefresh ? Date.now() : null;
      const forceParam = forceRefresh ? `&force_refresh=true&_refresh=${refreshNonce}` : '';
      const comparativeForceParam = forceRefresh ? `?force_refresh=true&_refresh=${refreshNonce}` : '';
      const fetchOptions: RequestInit = forceRefresh ? { cache: 'no-store' } : {};
      const [allNewsRes, industryRes, comparativeRes] = await Promise.allSettled([
        fetch(`${API_URL}/api/news/all?count_per_company=0${forceParam}`, fetchOptions),
        fetch(`${API_URL}/api/news/industry?count=20${forceParam}`, fetchOptions),
        fetch(`${API_URL}/api/news/comparative${comparativeForceParam}`, fetchOptions),
      ]);

      if (allNewsRes.status === 'fulfilled' && allNewsRes.value.ok) {
        const data = await allNewsRes.value.json();
        const newsMap: Record<CompanyTicker, NewsItem[]> = {
          FLEX: data.companies?.FLEX?.news || [],
          JBL: data.companies?.JBL?.news || [],
          CLS: data.companies?.CLS?.news || [],
          BHE: data.companies?.BHE?.news || [],
          SANM: data.companies?.SANM?.news || [],
        };
        nextBackendLoadMeta.allTimestamp = typeof data.timestamp === 'string' ? data.timestamp : '';
        nextBackendLoadMeta.companies = {
          FLEX: extractCompanyBackendMeta(data.companies?.FLEX),
          JBL: extractCompanyBackendMeta(data.companies?.JBL),
          CLS: extractCompanyBackendMeta(data.companies?.CLS),
          BHE: extractCompanyBackendMeta(data.companies?.BHE),
          SANM: extractCompanyBackendMeta(data.companies?.SANM),
        };
        setCompanyNews(newsMap);
      }

      if (industryRes.status === 'fulfilled' && industryRes.value.ok) {
        const data = await industryRes.value.json();
        nextBackendLoadMeta.industryTimestamp = typeof data.timestamp === 'string' ? data.timestamp : '';
        nextBackendLoadMeta.industryTotalFound = toSafeNumber(data.total_found);
        setIndustryNews(data.news || []);
      }

      if (comparativeRes.status === 'fulfilled' && comparativeRes.value.ok) {
        const data = await comparativeRes.value.json();
        nextBackendLoadMeta.comparativeTimestamp = typeof data.timestamp === 'string' ? data.timestamp : '';
        nextBackendLoadMeta.comparativeTotalFound = toSafeNumber(data.total_found);
        setComparativeNews(data.comparative_news || []);
      }

      setBackendLoadMeta(nextBackendLoadMeta);
    } catch (err) {
      console.error('Failed to fetch news:', err);
    } finally {
      if (showLoader) setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllNews(true);
  }, []);

  const refreshNews = async () => {
    setRefreshing(true);
    await fetchAllNews(false, true);
    setRefreshing(false);
  };

  const applyKeywordPreset = (preset: string) => {
    setKeyword((prev) => {
      const current = prev.trim().toLowerCase();
      const next = preset.trim().toLowerCase();
      return current === next ? '' : preset;
    });
  };

  const allCompanyNews = useMemo(() => {
    const merged: UnifiedNewsItem[] = [];
    for (const ticker of COMPANY_TICKERS) {
      const items = companyNews[ticker] || [];
      for (const item of items) merged.push(toUnifiedItem(item, ticker));
    }
    return merged;
  }, [companyNews]);

  const unifiedIndustryNews = useMemo(() => industryNews.map((item) => toUnifiedItem(item)), [industryNews]);
  const unifiedComparativeNews = useMemo(() => comparativeNews.map((item) => toUnifiedItem(item)), [comparativeNews]);

  const displayFeed = useMemo(() => {
    const hasKeyword = Boolean(keyword.trim());
    let feed = [...allCompanyNews, ...unifiedIndustryNews, ...unifiedComparativeNews];

    if (selectedCompany !== 'ALL') {
      feed = feed.filter((item) => item.company === selectedCompany);
    }

    if (hasKeyword) {
      const terms = keyword
        .split(',')
        .map((term) => term.trim().toLowerCase())
        .filter(Boolean);
      feed = feed.filter(
        (item) =>
          terms.some((q) =>
            item.title.toLowerCase().includes(q) ||
            item.description.toLowerCase().includes(q) ||
            item.source.toLowerCase().includes(q) ||
            (item.company ? COMPANY_NAMES[item.company].toLowerCase().includes(q) : false) ||
            item.categories?.some((cat) => cat.toLowerCase().includes(q))
          )
      );
    }
    return feed;
  }, [allCompanyNews, unifiedIndustryNews, unifiedComparativeNews, selectedCompany, keyword]);

  const curatedFeed = useMemo(() => {
    return dedupeBySimilarTitle(displayFeed.filter(isTrackedOrAIRelated));
  }, [displayFeed]);

  const prioritizedFeed = useMemo(() => {
    return [...curatedFeed].sort((a, b) => {
      const sourceDelta = getSourceQualityScore(b) - getSourceQualityScore(a);
      if (sourceDelta !== 0) return sourceDelta;

      const priorityDelta = getPriorityScore(b) - getPriorityScore(a);
      if (priorityDelta !== 0) return priorityDelta;

      const timeDelta = getPublishedTimestamp(b.published) - getPublishedTimestamp(a.published);
      if (timeDelta !== 0) return timeDelta;

      return (b.relevance_score || 0) - (a.relevance_score || 0);
    });
  }, [curatedFeed]);

  const timeSortedFeed = useMemo(() => {
    return [...displayFeed].sort((a, b) => {
      const dateA = getPublishedDateKey(a.published);
      const dateB = getPublishedDateKey(b.published);
      if (dateA !== dateB) return dateB.localeCompare(dateA);

      const aHasTime = hasPublishedTime(a.published);
      const bHasTime = hasPublishedTime(b.published);
      if (aHasTime && bHasTime) {
        const timeDelta = getPublishedTimestamp(b.published) - getPublishedTimestamp(a.published);
        if (timeDelta !== 0) return timeDelta;
      }

      return (b.relevance_score || 0) - (a.relevance_score || 0);
    });
  }, [displayFeed]);

  const shouldUseFallback = selectedCompany === 'ALL' && !keyword.trim() && timeSortedFeed.length === 0;
  const filteredFeed = shouldUseFallback ? FALLBACK_FEED : timeSortedFeed;
  const recentFeed = useMemo(() => {
    if (shouldUseFallback) return FALLBACK_FEED;
    const now = Date.now();
    const twoDaysMs = 2 * 24 * 60 * 60 * 1000;
    return filteredFeed.filter((item) => {
      const ts = getPublishedTimestamp(item.published);
      if (!ts) return false;
      return now - ts <= twoDaysMs && now >= ts;
    });
  }, [filteredFeed, shouldUseFallback]);

  const topNewsFeed = useMemo(() => {
    const now = Date.now();
    const windowMs = TOP_NEWS_RECENT_DAYS * 24 * 60 * 60 * 1000;
    const topSource = prioritizedFeed.length > 0 ? prioritizedFeed : filteredFeed;
    const cleaned = topSource.filter(isTopNewsEligible);
    const recent = cleaned.filter((item) => {
      const ts = getPublishedTimestamp(item.published);
      if (!ts) return false;
      return now >= ts && now - ts <= windowMs;
    });
    if (recent.length > 0) return recent;
    if (cleaned.length > 0) return cleaned;
    return topSource;
  }, [filteredFeed, prioritizedFeed]);

  const leadStory = topNewsFeed.find(isLeadSourceAllowed) || topNewsFeed[0];
  const hotRank = topNewsFeed.slice(0, 10);
  const trendingTopFive = hotRank.slice(0, 5);
  const activeKeyword = keyword.trim();
  const normalizedKeyword = activeKeyword.toLowerCase();
  const selectedCompanyLabel =
    selectedCompany === 'ALL' ? 'All tracked companies' : COMPANY_NAMES[selectedCompany as CompanyTicker];

  const summaryStats = useMemo(() => {
    const companiesCovered = new Set<CompanyTicker>();
    const sourceCount = new Set<string>();
    const categoryCounts = new Map<string, number>();

    for (const item of filteredFeed) {
      if (item.company) companiesCovered.add(item.company);
      if (item.source) sourceCount.add(item.source);

      const categoryKey = getCategoryKey(item.categories);
      categoryCounts.set(categoryKey, (categoryCounts.get(categoryKey) || 0) + 1);
    }

    const topCategoryEntry = [...categoryCounts.entries()].sort((a, b) => b[1] - a[1])[0];
    const topCategoryLabel = topCategoryEntry ? CATEGORY_LABELS[topCategoryEntry[0]] || 'General' : 'General';

    return {
      companiesCovered: selectedCompany === 'ALL' ? companiesCovered.size : 1,
      sourceCount: sourceCount.size,
      topCategoryLabel,
    };
  }, [filteredFeed, selectedCompany]);

  const backendSyncSummary = useMemo(() => {
    if (!backendLoadMeta) {
      return {
        title: 'Backend snapshot not loaded yet.',
        detail: 'Open the news feed or trigger a refresh to inspect cache replacement behavior.',
      };
    }

    if (selectedCompany !== 'ALL') {
      const companyTicker = selectedCompany as CompanyTicker;
      const companyMeta = backendLoadMeta.companies[companyTicker];
      return {
        title: `${COMPANY_NAMES[companyTicker]} cache updated ${formatBackendTimestamp(companyMeta.timestamp)}.`,
        detail: `${backendLoadMeta.mode === 'refresh' ? 'Refresh write' : 'Cache read'} • ${companyMeta.finalKeptCount} kept stories (${companyMeta.totalFound} visible before local filters).`,
      };
    }

    const totalCompanyKept = COMPANY_TICKERS.reduce(
      (sum, ticker) => sum + backendLoadMeta.companies[ticker].finalKeptCount,
      0
    );
    const snapshotTimestamp = backendLoadMeta.allTimestamp || backendLoadMeta.requestedAt;
    return {
      title: `Backend snapshot ${formatBackendTimestamp(snapshotTimestamp)}.`,
      detail: `${backendLoadMeta.mode === 'refresh' ? 'Refresh write' : 'Cache read'} • Company kept ${totalCompanyKept} • Industry ${backendLoadMeta.industryTotalFound} • Comparative ${backendLoadMeta.comparativeTotalFound}.`,
    };
  }, [backendLoadMeta, selectedCompany]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-100 dark:bg-[#070b12] flex items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-16 w-16 animate-spin rounded-full border-4 border-slate-300 dark:border-slate-700 border-t-cyan-500" />
          <p className="mt-4 text-sm font-medium text-slate-600 dark:text-slate-400">Loading news intelligence...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white text-slate-900 dark:bg-[#060a12] dark:text-slate-100">
      <div className="mx-auto max-w-[1720px] px-4 py-5 sm:px-5">
        <div className="mb-4 rounded-[24px] border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-slate-100 p-4 dark:border-slate-800 dark:from-[#0b1220] dark:via-[#0a101c] dark:to-[#0b1220]">
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-cyan-50 px-3 py-1.5 text-sm font-medium text-cyan-700 dark:bg-[#0f1726] dark:text-cyan-300">
                  News Monitor
                </span>
                <span className="rounded-full border border-slate-300 bg-white/80 px-3 py-1.5 text-xs text-slate-600 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-400">
                  {COMPANY_TICKERS.length} tracked companies
                </span>
                <span className="rounded-full border border-slate-300 bg-white/80 px-3 py-1.5 text-xs text-slate-600 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-400">
                  {filteredFeed.length} stories
                </span>
                {activeKeyword && (
                  <span className="rounded-full border border-cyan-300 bg-cyan-50 px-3 py-1.5 text-xs text-cyan-700 dark:border-cyan-400/60 dark:bg-cyan-500/20 dark:text-cyan-200">
                    Keyword: {activeKeyword}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2 self-start lg:self-auto">
                <button
                  onClick={refreshNews}
                  disabled={refreshing}
                  title={refreshing ? 'Refreshing current content...' : 'Refresh current content'}
                  aria-label={refreshing ? 'Refreshing current content' : 'Refresh current content'}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-600 transition hover:border-slate-400 hover:bg-slate-50 hover:text-cyan-700 disabled:opacity-50 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-[#0f1726] dark:hover:text-cyan-300"
                >
                  <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
                </button>
                <a
                  href={PROJECT_GITHUB_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Open project GitHub repository"
                  aria-label="Open project GitHub repository"
                  className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-600 transition hover:border-slate-400 hover:bg-slate-50 hover:text-cyan-700 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-[#0f1726] dark:hover:text-cyan-300"
                >
                  <Github className="h-4 w-4" />
                </a>
              </div>
            </div>

            <div className="grid gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(280px,0.9fr)]">
              <div className="min-w-0 rounded-2xl border border-slate-200 bg-white/90 p-3 dark:border-slate-800 dark:bg-[#0a101c]">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-500">Topic Focus</div>
                  <span className="text-xs text-slate-500 dark:text-slate-500">
                    {activeKeyword ? `Active: ${activeKeyword}` : 'No keyword filter'}
                  </span>
                </div>

                <div className="flex flex-wrap gap-2">
                  {KEYWORD_PRESETS.map((preset) => (
                    <button
                      key={preset.value}
                      onClick={() => applyKeywordPreset(preset.value)}
                      className={`rounded-full border px-3 py-1.5 text-sm transition ${
                        normalizedKeyword === preset.value
                          ? 'border-cyan-300 bg-cyan-50 text-cyan-700 dark:border-cyan-400/60 dark:bg-cyan-500/20 dark:text-cyan-200'
                          : 'border-slate-300 bg-white text-slate-700 hover:border-slate-400 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-400 dark:hover:border-slate-600'
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>

                <div className="relative mt-3">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
                  <input
                    value={keyword}
                    onChange={(e) => setKeyword(e.target.value)}
                    placeholder="Search title, category, or company"
                    className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-3 text-sm text-slate-900 outline-none transition focus:border-cyan-400 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-100"
                  />
                </div>
              </div>

              <div className="min-w-0 rounded-2xl border border-slate-200 bg-white/90 p-3 dark:border-slate-800 dark:bg-[#0a101c]">
                <div className="mb-2 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-500">Company Scope</div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => setSelectedCompany('ALL')}
                    className={`rounded-full px-3 py-2 text-sm ${
                      selectedCompany === 'ALL'
                        ? 'bg-blue-500 text-white'
                        : 'border border-slate-300 bg-white text-slate-700 dark:border-slate-800 dark:bg-[#0b111d] dark:text-slate-300'
                    }`}
                  >
                    All
                  </button>
                  {COMPANY_TICKERS.map((ticker) => (
                    <button
                      key={ticker}
                      onClick={() => setSelectedCompany(ticker)}
                      className={`rounded-full px-3 py-2 text-sm ${
                        selectedCompany === ticker
                          ? 'text-white'
                          : 'border border-slate-300 bg-white text-slate-700 dark:border-slate-800 dark:bg-[#0b111d] dark:text-slate-300'
                      }`}
                      style={selectedCompany === ticker ? { backgroundColor: COMPANY_COLORS[ticker] } : {}}
                    >
                      {COMPANY_NAMES[ticker]}
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-500">
                  <span>{selectedCompanyLabel}</span>
                  <span>•</span>
                  <span>{summaryStats.sourceCount} sources</span>
                  <span>•</span>
                  <span>Top theme: {summaryStats.topCategoryLabel}</span>
                </div>
              </div>

              <div className="min-w-0 rounded-2xl border border-slate-200 bg-white/90 p-3 dark:border-slate-800 dark:bg-[#0a101c]">
                <div className={`flex items-center justify-between gap-2 ${newsSummaryExpanded ? 'mb-3' : ''}`}>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-500">News Summary</div>
                  <button
                    onClick={() => setNewsSummaryExpanded((prev) => !prev)}
                    title={newsSummaryExpanded ? 'Collapse summary panel' : 'Expand summary panel'}
                    aria-label={newsSummaryExpanded ? 'Collapse summary panel' : 'Expand summary panel'}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-slate-300 bg-white text-slate-600 transition hover:border-slate-400 hover:bg-slate-50 hover:text-cyan-700 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-[#0f1726] dark:hover:text-cyan-300"
                  >
                    <ChevronDown className={`h-4 w-4 transition-transform ${newsSummaryExpanded ? 'rotate-180' : ''}`} />
                  </button>
                </div>

                {newsSummaryExpanded && (
                  <>
                    <div className="grid grid-cols-3 gap-2">
                      <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-[#0b111d]">
                        <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500 dark:text-slate-500">Stories</div>
                        <p className="mt-1 text-xl font-semibold text-slate-900 dark:text-white">{filteredFeed.length}</p>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-[#0b111d]">
                        <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500 dark:text-slate-500">48h</div>
                        <p className="mt-1 text-xl font-semibold text-slate-900 dark:text-white">{recentFeed.length}</p>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-[#0b111d]">
                        <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500 dark:text-slate-500">Coverage</div>
                        <p className="mt-1 text-xl font-semibold text-slate-900 dark:text-white">{summaryStats.companiesCovered}</p>
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-500">
                      <span>{selectedCompanyLabel}</span>
                      {leadStory?.source && (
                        <>
                          <span>•</span>
                          <span>{leadStory.source}</span>
                        </>
                      )}
                      <span>•</span>
                      <span>{leadStory?.timestampLabel || '--'}</span>
                    </div>

                    <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-700 dark:text-slate-300">
                      {leadStory?.title || 'No lead story available yet.'}
                    </p>

                    <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-[#0b111d]">
                      <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500 dark:text-slate-500">Backend Sync</div>
                      <p className="mt-1 text-sm font-medium text-slate-800 dark:text-slate-200">{backendSyncSummary.title}</p>
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">{backendSyncSummary.detail}</p>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white/90 p-3 dark:border-slate-800 dark:bg-[#0a101c] lg:flex-row lg:items-center">
              <div className="shrink-0 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-500">
                Official Company Portals
              </div>
              <div className="flex flex-wrap gap-2">
                {COMPANY_TICKERS.map((ticker) => (
                  <a
                    key={ticker}
                    href={COMPANY_WEBSITES[ticker]}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex min-w-0 items-center gap-2 rounded-full border border-slate-300 bg-slate-50 px-3 py-1.5 text-sm text-slate-700 transition hover:border-slate-400 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-200 dark:hover:border-slate-600 dark:hover:text-white"
                  >
                    <span
                      className="inline-flex items-center justify-center rounded px-2 py-0.5 text-[11px] font-semibold leading-none text-white"
                      style={{ backgroundColor: COMPANY_COLORS[ticker] }}
                    >
                      {COMPANY_BADGE_LABELS[ticker]}
                    </span>
                    <span>{COMPANY_NAMES[ticker]}</span>
                    <ExternalLink className="h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500" />
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[1.7fr_1fr] xl:h-[860px]">
          <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 h-full flex flex-col overflow-hidden dark:border-slate-800 dark:bg-[#0a101c]">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-3xl font-semibold text-slate-900 dark:text-white">Top News</h2>
              <span className="text-xs text-slate-600 dark:text-slate-500">Published {leadStory?.timestampLabel || '--'}</span>
            </div>
            <div className="flex h-full min-h-0 flex-col gap-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0b1220]">
                {leadStory && (
                  <a href={getSafeHref(leadStory)} target="_blank" rel="noopener noreferrer" className="block min-w-0">
                    {leadStory.image_url && (
                      <div className="mb-3 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
                        <img
                          src={leadStory.image_url}
                          alt={leadStory.title}
                          className="h-[300px] w-full object-cover"
                          onError={(e) => {
                            (e.currentTarget as HTMLImageElement).style.display = 'none';
                          }}
                        />
                      </div>
                    )}
                    <h3 className="text-4xl font-semibold leading-tight text-slate-900 hover:text-cyan-700 dark:text-white dark:hover:text-cyan-300">{leadStory.title}</h3>
                    <p className="mt-3 text-base leading-7 text-slate-700 dark:text-slate-300">{leadStory.description}</p>
                    <div className="mt-3 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                      <Globe2 className="h-3.5 w-3.5" />
                      <span>{leadStory.source}</span>
                      <span>• {leadStory.timestampLabel}</span>
                      {leadStory.company && <span className="rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700">{COMPANY_NAMES[leadStory.company]}</span>}
                    </div>
                  </a>
                )}
              </div>

              <div className="flex min-h-0 flex-col rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0b1220]">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-2xl font-semibold text-slate-900 dark:text-white">Trending (Top 5)</h3>
                  <Flame className="h-5 w-5 text-orange-400" />
                </div>
                <div className="space-y-2 flex-1 overflow-y-auto pr-2 xl:[&::-webkit-scrollbar]:w-1.5 xl:[&::-webkit-scrollbar-thumb]:rounded-full xl:[&::-webkit-scrollbar-thumb]:bg-slate-700 xl:[&::-webkit-scrollbar-track]:bg-transparent">
                  {trendingTopFive.map((item, idx) => (
                    <a
                      key={`${item.title}-${idx}`}
                      href={getSafeHref(item)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block rounded-lg border border-slate-200 bg-slate-50 p-3 transition hover:border-slate-300 dark:border-slate-800 dark:bg-[#0a101c] dark:hover:border-slate-700"
                    >
                      <div className="flex gap-3">
                        <span className="text-2xl font-bold text-orange-400">{idx + 1}</span>
                        <div className="min-w-0">
                          <p className="line-clamp-2 text-base font-medium leading-6 text-slate-900 dark:text-slate-100">{item.title}</p>
                          <div className="mt-1 flex items-center gap-1 text-xs text-slate-600 dark:text-slate-500">
                            <Globe2 className="h-3.5 w-3.5" />
                            <span>{item.source}</span>
                            <span>• {item.timestampLabel}</span>
                          </div>
                        </div>
                      </div>
                    </a>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 h-full flex flex-col overflow-hidden dark:border-slate-800 dark:bg-[#0a101c]">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-2xl font-semibold text-slate-900 dark:text-white">Analyst View</h2>
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 dark:border-slate-700 dark:text-slate-400">
                <Rss className="h-3.5 w-3.5 text-cyan-600 dark:text-cyan-300" />
                {filteredFeed.length} items
              </div>
            </div>

            <div className="space-y-0 border-l border-slate-300 dark:border-slate-800 pl-4 flex-1 overflow-y-auto pr-2 xl:[&::-webkit-scrollbar]:w-1.5 xl:[&::-webkit-scrollbar-thumb]:rounded-full xl:[&::-webkit-scrollbar-thumb]:bg-slate-700 xl:[&::-webkit-scrollbar-track]:bg-transparent">
              {filteredFeed.map((item, idx) => (
                <a
                  key={`${item.title}-${idx}`}
                  href={getSafeHref(item)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="grid grid-cols-[64px_1fr_28px] gap-3 py-3 transition hover:bg-slate-100 dark:hover:bg-white/[0.02]"
                >
                  <div className="relative">
                    <div className="absolute -left-[11px] top-2 h-3 w-3 rounded-full border-2 border-cyan-400 bg-white dark:bg-[#060a12]" />
                    <p className="text-[11px] font-semibold text-cyan-700 dark:text-cyan-300">{item.timestampLabel}</p>
                  </div>
                  <div>
                    <p className="text-base font-semibold leading-6 text-cyan-700 dark:text-cyan-300">{item.title}</p>
                    <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{item.description}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                      {item.company && <span className="rounded border border-slate-300 px-2 py-0.5 text-slate-700 dark:border-slate-700 dark:text-slate-300">{COMPANY_NAMES[item.company]}</span>}
                      <span className={`rounded border px-2 py-0.5 ${CATEGORY_TINTS[getCategoryKey(item.categories)]}`}>{item.categoryLabel}</span>
                      <span className="text-slate-600 dark:text-slate-500">{item.source}</span>
                    </div>
                  </div>
                  <div className="flex items-start justify-end pt-1 text-slate-600 dark:text-slate-500">
                    <ExternalLink className="h-4 w-4" />
                    <Clock3 className="ml-2 h-4 w-4" />
                  </div>
                </a>
              ))}
            </div>
          </section>
        </div>

      </div>
    </div>
  );
}
