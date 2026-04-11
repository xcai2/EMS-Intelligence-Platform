'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  RefreshCw,
  Flame,
  ExternalLink,
  Rss,
  Globe2,
  Github,
  ChevronDown,
  Search,
  Check,
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
const PROJECT_GITHUB_URL = 'https://github.com/xcai2/Flex-Practicum-Project-2026';

const COMPANY_TICKERS = ['FLEX', 'JBL', 'CLS', 'BHE', 'SANM', 'PLXS'] as const;
type CompanyTicker = (typeof COMPANY_TICKERS)[number];

const COMPANY_NAMES: Record<CompanyTicker, string> = {
  FLEX: 'Flex',
  JBL: 'Jabil',
  CLS: 'Celestica',
  BHE: 'Benchmark',
  SANM: 'Sanmina',
  PLXS: 'Plexus',
};

const COMPANY_BADGE_LABELS: Record<CompanyTicker, string> = {
  FLEX: 'FLEX',
  JBL: 'Jabil',
  CLS: 'Celestica',
  BHE: 'Benchmark',
  SANM: 'Sanmina',
  PLXS: 'Plexus',
};

const COMPANY_COLORS: Record<CompanyTicker, string> = {
  FLEX: '#3B82F6',
  JBL: '#10B981',
  CLS: '#6366F1',
  BHE: '#F59E0B',
  SANM: '#EF4444',
  PLXS: '#14B8A6',
};

const COMPANY_WEBSITES: Record<CompanyTicker, string> = {
  JBL: 'https://www.jabil.com/',
  FLEX: 'https://flex.com/newsroom',
  BHE: 'https://www.bench.com/',
  SANM: 'https://www.sanmina.com/',
  CLS: 'https://www.celestica.com/',
  PLXS: 'https://www.plexus.com/news/',
};

const KEYWORD_PRESETS = [
  { label: 'Data Center', value: 'data center' },
  { label: 'AI', value: 'ai' },
  { label: 'CapEx', value: 'capex, capital expenditure' },
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
  'plexus.com',
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

function getCategoryKey(categories?: string[]) {
  return categories?.[0] || 'general';
}

function parsePublishedDate(raw?: string) {
  const value = (raw || '').trim();
  if (!value) return null;

  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed;
  }

  const lowered = value.toLowerCase();
  if (lowered === 'today' || lowered === 'just now') {
    return new Date();
  }
  if (lowered === 'yesterday') {
    return new Date(Date.now() - 24 * 60 * 60 * 1000);
  }

  const match = lowered.match(/^(a|an|\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago$/i);
  if (!match) return null;

  const count = match[1] === 'a' || match[1] === 'an' ? 1 : Number(match[1]);
  if (!Number.isFinite(count) || count <= 0) return null;

  const unit = match[2].toLowerCase();
  let deltaMs = 0;
  if (unit.startsWith('minute')) deltaMs = count * 60 * 1000;
  else if (unit.startsWith('hour')) deltaMs = count * 60 * 60 * 1000;
  else if (unit.startsWith('day')) deltaMs = count * 24 * 60 * 60 * 1000;
  else if (unit.startsWith('week')) deltaMs = count * 7 * 24 * 60 * 60 * 1000;
  else if (unit.startsWith('month')) deltaMs = count * 30 * 24 * 60 * 60 * 1000;
  else if (unit.startsWith('year')) deltaMs = count * 365 * 24 * 60 * 60 * 1000;
  else return null;

  return new Date(Date.now() - deltaMs);
}

function formatPublishedLabel(raw?: string) {
  const parsed = parsePublishedDate(raw);
  if (parsed) {
    return parsed.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: '2-digit' });
  }
  return (raw || '').trim();
}

function getPublishedTimestamp(raw?: string) {
  const parsed = parsePublishedDate(raw);
  if (!parsed) return 0;
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

function getPriorityScore(item: UnifiedNewsItem) {
  let score = 0;
  if (item.company) {
    score += 1000;
    if (item.company === 'FLEX') score += 300;
  }
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
  const [inputKeyword, setInputKeyword] = useState('');
  const [companyNews, setCompanyNews] = useState<Record<CompanyTicker, NewsItem[]>>({
    FLEX: [],
    JBL: [],
    CLS: [],
    BHE: [],
    SANM: [],
    PLXS: [],
  });
  const [industryNews, setIndustryNews] = useState<NewsItem[]>([]);
  const [comparativeNews, setComparativeNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [topControlsExpanded, setTopControlsExpanded] = useState(true);

  const fetchAllNews = async (showLoader = false, forceRefresh = false) => {
    if (showLoader) setLoading(true);
    try {
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
          PLXS: data.companies?.PLXS?.news || [],
        };
        setCompanyNews(newsMap);
      }

      if (industryRes.status === 'fulfilled' && industryRes.value.ok) {
        const data = await industryRes.value.json();
        setIndustryNews(data.news || []);
      }

      if (comparativeRes.status === 'fulfilled' && comparativeRes.value.ok) {
        const data = await comparativeRes.value.json();
        setComparativeNews(data.comparative_news || []);
      }
    } catch (err) {
      console.error('Failed to fetch news:', err);
    } finally {
      if (showLoader) setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllNews(true);
  }, []);

  useEffect(() => {
    const saved = localStorage.getItem('news_keyword');
    if (saved) {
      setKeyword(saved);
      setInputKeyword(saved);
    }
  }, []);

  const refreshNews = async () => {
    setRefreshing(true);
    await fetchAllNews(false, true);
    setRefreshing(false);
  };

  const applyKeyword = (value: string) => {
    setKeyword(value);
    setInputKeyword(value);
    if (value.trim()) {
      localStorage.setItem('news_keyword', value.trim());
    } else {
      localStorage.removeItem('news_keyword');
    }
  };

  const applyKeywordPreset = (preset: string) => {
    const next = keyword.trim().toLowerCase() === preset.trim().toLowerCase() ? '' : preset;
    applyKeyword(next);
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
    return dedupeBySimilarTitle(displayFeed);
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
      const timeDelta = getPublishedTimestamp(b.published) - getPublishedTimestamp(a.published);
      if (timeDelta !== 0) return timeDelta;

      const dateA = getPublishedDateKey(a.published);
      const dateB = getPublishedDateKey(b.published);
      if (dateA !== dateB) return dateB.localeCompare(dateA);

      return (b.relevance_score || 0) - (a.relevance_score || 0);
    });
  }, [displayFeed]);

  const shouldUseFallback = selectedCompany === 'ALL' && !keyword.trim() && timeSortedFeed.length === 0;
  const filteredFeed = shouldUseFallback ? FALLBACK_FEED : timeSortedFeed;

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

  const hotRank = topNewsFeed.slice(0, 10);
  const trendingTopTen = hotRank;
  const activeKeyword = keyword.trim();
  const normalizedKeyword = activeKeyword.toLowerCase();

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
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">News Monitor</h1>
                {topControlsExpanded ? (
                  <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                    Expand filters when needed, then collapse the panel to focus on the feed.
                  </p>
                ) : (
                  <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                    Filters hidden. Showing the live news layout only.
                  </p>
                )}
              </div>

              <div className="flex items-center gap-2 self-start">
                <button
                  onClick={() => setTopControlsExpanded((prev) => !prev)}
                  title={topControlsExpanded ? 'Collapse top filters' : 'Expand top filters'}
                  aria-label={topControlsExpanded ? 'Collapse top filters' : 'Expand top filters'}
                  className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 text-sm font-medium text-slate-600 transition hover:border-slate-400 hover:bg-slate-50 hover:text-cyan-700 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-[#0f1726] dark:hover:text-cyan-300"
                >
                  <span>{topControlsExpanded ? 'Collapse' : 'Expand'}</span>
                  <ChevronDown className={`h-4 w-4 transition-transform ${topControlsExpanded ? 'rotate-180' : ''}`} />
                </button>
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

            {topControlsExpanded && (
              <div className="grid gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
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

                  <div className="relative mt-3 flex gap-2">
                    <div className="relative flex-1">
                      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
                      <input
                        value={inputKeyword}
                        onChange={(e) => setInputKeyword(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') applyKeyword(inputKeyword); }}
                        placeholder="Search title, category, or company"
                        className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-3 text-sm text-slate-900 outline-none transition focus:border-cyan-400 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-100"
                      />
                    </div>
                    <button
                      onClick={() => applyKeyword(inputKeyword)}
                      className="flex items-center gap-1.5 rounded-xl border border-cyan-400 bg-cyan-50 px-3 py-2 text-sm font-medium text-cyan-700 transition hover:bg-cyan-100 dark:border-cyan-500/50 dark:bg-cyan-500/10 dark:text-cyan-300 dark:hover:bg-cyan-500/20"
                    >
                      <Check className="h-4 w-4" />
                      Confirm
                    </button>
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
                </div>
              </div>
            )}

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
            </div>
            <div className="flex h-full min-h-0 flex-col gap-4">
              <div className="flex min-h-0 flex-col gap-2 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0b1220] xl:[&::-webkit-scrollbar]:w-1.5 xl:[&::-webkit-scrollbar-thumb]:rounded-full xl:[&::-webkit-scrollbar-thumb]:bg-slate-700 xl:[&::-webkit-scrollbar-track]:bg-transparent">
                {topNewsFeed.slice(0, 5).map((item, idx) => (
                  <a
                    key={`top-${item.title}-${idx}`}
                    href={getSafeHref(item)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block rounded-xl border border-slate-200 bg-slate-50 p-3 transition hover:border-cyan-300 dark:border-slate-800 dark:bg-[#0a101c] dark:hover:border-cyan-500/40"
                  >
                    <div className="flex gap-3">
                      <span className="shrink-0 text-xl font-bold text-cyan-500 dark:text-cyan-400">{idx + 1}</span>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold leading-snug text-slate-900 hover:text-cyan-700 dark:text-white dark:hover:text-cyan-300 line-clamp-2">{item.title}</p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                          <Globe2 className="h-3 w-3 shrink-0" />
                          <span>{item.source}</span>
                          <span>•</span>
                          <span>{item.timestampLabel}</span>
                          {item.company && <span className="rounded border border-slate-300 px-1.5 py-0.5 dark:border-slate-700">{COMPANY_NAMES[item.company]}</span>}
                        </div>
                      </div>
                    </div>
                  </a>
                ))}
              </div>

              <div className="flex min-h-0 flex-col rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0b1220]">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-2xl font-semibold text-slate-900 dark:text-white">Trending (Top 10)</h3>
                  <Flame className="h-5 w-5 text-orange-400" />
                </div>
                <div className="space-y-2 flex-1 overflow-y-auto pr-2 xl:[&::-webkit-scrollbar]:w-1.5 xl:[&::-webkit-scrollbar-thumb]:rounded-full xl:[&::-webkit-scrollbar-thumb]:bg-slate-700 xl:[&::-webkit-scrollbar-track]:bg-transparent">
                  {trendingTopTen.map((item, idx) => (
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
              <h2 className="text-2xl font-semibold text-slate-900 dark:text-white">News Flash</h2>
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 dark:border-slate-700 dark:text-slate-400">
                <Rss className="h-3.5 w-3.5 text-cyan-600 dark:text-cyan-300" />
                {filteredFeed.length} items
              </div>
            </div>

            <div className="space-y-0 flex-1 overflow-y-auto pr-2 xl:[&::-webkit-scrollbar]:w-1.5 xl:[&::-webkit-scrollbar-thumb]:rounded-full xl:[&::-webkit-scrollbar-thumb]:bg-slate-700 xl:[&::-webkit-scrollbar-track]:bg-transparent">
              {filteredFeed.map((item, idx) => (
                <a
                  key={`${item.title}-${idx}`}
                  href={getSafeHref(item)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="grid grid-cols-[64px_1fr_20px] gap-3 py-3 transition hover:bg-slate-100 dark:hover:bg-white/[0.02]"
                >
                  <div>
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
