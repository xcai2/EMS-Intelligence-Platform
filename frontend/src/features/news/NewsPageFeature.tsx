'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  RefreshCw,
  Flame,
  ExternalLink,
  Rss,
  Globe2,
  // eslint-disable-next-line deprecation/deprecation
  Github,
  ChevronDown,
  ChevronRight,
  Search,
  Check,
  Plus,
  X,
  HelpCircle,
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
const PROJECT_GITHUB_URL = 'https://github.com/xcai2/Flex-Practicum-Project-2026';

interface RegisteredCompany {
  ticker: string;
  full_name: string;
  display_name: string;
  official_domain: string;
  official_website: string;
  aliases: string;
  industry: string;
  color: string;
  is_builtin?: boolean;
  is_deletable?: boolean;
}

interface ResolvedCompany {
  company_name: string;
  display_name: string;
  ticker: string;
  aliases: string[];
  official_website: string;
  official_domain: string;
  confidence: number;
  reason: string;
  source?: string;
}

// Rotating color palette for dynamically added companies.
const COMPANY_COLOR_PALETTE = [
  '#3B82F6', '#10B981', '#6366F1', '#F59E0B', '#EF4444', '#14B8A6',
  '#8B5CF6', '#F97316', '#06B6D4', '#EC4899', '#84CC16', '#A855F7',
];

// Hardcoded overrides for the original 6 companies so their colors never change.
const COMPANY_COLOR_OVERRIDES: Record<string, string> = {
  FLEX: '#3B82F6', JBL: '#10B981', CLS: '#6366F1',
  BHE: '#F59E0B', SANM: '#EF4444', PLXS: '#14B8A6',
};

// Default seed for initial render (replaced by API data on mount).
const DEFAULT_COMPANIES: RegisteredCompany[] = [
  { ticker: 'FLEX', full_name: 'Flex Ltd',              display_name: 'Flex',      official_domain: 'flex.com',       official_website: 'https://flex.com/newsroom',         aliases: 'Flextronics,FLEX', industry: 'EMS', color: '#3B82F6' },
  { ticker: 'JBL',  full_name: 'Jabil Inc',             display_name: 'Jabil',     official_domain: 'jabil.com',      official_website: 'https://www.jabil.com/',            aliases: 'Jabil Inc',        industry: 'EMS', color: '#10B981' },
  { ticker: 'CLS',  full_name: 'Celestica Inc',         display_name: 'Celestica', official_domain: 'celestica.com',  official_website: 'https://www.celestica.com/',        aliases: 'Celestica Inc',    industry: 'EMS', color: '#6366F1' },
  { ticker: 'BHE',  full_name: 'Benchmark Electronics', display_name: 'Benchmark', official_domain: 'bench.com',      official_website: 'https://www.bench.com/',            aliases: 'Benchmark Electronics Inc', industry: 'EMS', color: '#F59E0B' },
  { ticker: 'SANM', full_name: 'Sanmina Corporation',   display_name: 'Sanmina',   official_domain: 'sanmina.com',    official_website: 'https://www.sanmina.com/',          aliases: 'Sanmina Corporation', industry: 'EMS', color: '#EF4444' },
  { ticker: 'PLXS', full_name: 'Plexus Corp',           display_name: 'Plexus',    official_domain: 'plexus.com',     official_website: 'https://www.plexus.com/news/',      aliases: 'Plexus Corp',      industry: 'EMS', color: '#14B8A6' },
];

// Phase 2 Part 3: preset themes with hidden keyword lists (OR matching).
// Each preset is independent of the manual search input.
const KEYWORD_PRESETS: { label: string; keywords: string[] }[] = [
  { label: 'Data Center', keywords: ['data center', 'datacenter', 'server', 'rack', 'storage'] },
  { label: 'Power',       keywords: ['power', 'power supply', 'power systems', 'power products'] },
  { label: 'Cooling',     keywords: ['cooling', 'liquid cooling', 'thermal', 'thermal management'] },
  { label: 'Networking',  keywords: ['networking', 'switch', 'router', 'interconnect'] },
  { label: 'Semiconductor', keywords: ['semiconductor', 'chip', 'chips', 'silicon'] },
  { label: 'AI Infrastructure', keywords: ['artificial intelligence', 'ai server', 'gpu', 'accelerator', 'inference', 'ai factory'] },
];

const UNDATED_LABEL = 'Undated';

const SOURCE_TYPE_LABELS: Record<string, string> = {
  brave: 'Web',
  company_news_rss: 'IR RSS',
  sec_filing_rss: 'SEC RSS',
  market_commentary_rss: 'Commentary RSS',
};

const SOURCE_TYPE_TINTS: Record<string, string> = {
  brave: 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-500/15 dark:text-sky-300 dark:border-sky-400/20',
  company_news_rss: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-400/20',
  sec_filing_rss: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-400/20',
  market_commentary_rss: 'bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-500/15 dark:text-violet-300 dark:border-violet-400/20',
};

interface NewsItem {
  title: string;
  url: string;
  backup_url?: string;
  description: string;
  content?: string;
  image_url?: string;
  source: string;
  source_type?: string;
  intent?: string | null;
  published?: string;
  categories?: string[];
  relevance_score?: number;
  summary?: string;
  matched_intents?: string[];
  match_count?: number;
  canonical_url?: string;
}

interface UnifiedNewsItem extends NewsItem {
  company?: string;
  timestampLabel: string;
}

interface TrendingCluster {
  id: string;
  trend_cluster_key?: string;
  trend_title: string;
  trend_summary?: string;
  summary?: string; // Phase 2 compat
  keywords?: string[];
  window_label?: string;
  supporting_count_7d?: number;
  supporting_count_30d?: number;
  supporting_count_60d?: number;
  cluster_size: number;
  companies: string[];
  representative_items: NewsItem[];
  updated_at: string;
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

function toUnifiedItem(item: NewsItem, company?: string): UnifiedNewsItem {
  const publishedLabel = formatPublishedLabel(item.published);
  return {
    ...item,
    company,
    timestampLabel: publishedLabel || UNDATED_LABEL,
  };
}

/**
 * Lightweight company input pre-processor (§5.3.1).
 * Strips conversational prefixes and noise before sending to suggest/resolver.
 * "帮我查一下英伟达" → "英伟达"
 * "I want to add Google" → "Google"
 */
function preprocessCompanyInput(raw: string): string {
  let s = raw.trim();
  // Remove common Chinese conversational prefixes
  s = s.replace(/^(帮我查一下|帮我找|请帮我找|我想添加|我想查|查一下|请查|帮查|添加|请添加)\s*/u, '');
  // Remove trailing noise
  s = s.replace(/\s*(的官网是什么|的官方网站|官网|官方网站|是什么|公司)$/u, '');
  // Remove common English conversational prefixes
  s = s.replace(/^(please\s+)?(help\s+me\s+)?(find|add|look\s+up|search\s+for|i\s+want\s+to\s+add)\s+/i, '');
  s = s.replace(/^(a\s+company\s+called\s+|the\s+company\s+)/i, '');
  // Collapse whitespace
  s = s.replace(/\s+/g, ' ').trim();
  return s;
}

/**
 * Returns true if the input looks like multiple company names/tickers at once (§5.3.2).
 * Heuristic: 2+ whitespace-separated tokens that are each 2-5 uppercase letters.
 */
function looksLikeMultipleCompanies(raw: string): boolean {
  const tokens = raw.trim().split(/\s+/);
  if (tokens.length < 2) return false;
  const tickerLike = tokens.filter((t) => /^[A-Z]{2,5}$/.test(t));
  return tickerLike.length >= 2;
}

function normalizeSearchText(raw: string) {
  return ` ${raw.toLowerCase().replace(/[^a-z0-9]+/g, ' ').replace(/\s+/g, ' ').trim()} `;
}

function splitKeywordTerms(raw: string) {
  return raw
    .split(',')
    .map((term) => term.trim().toLowerCase())
    .filter(Boolean);
}

function matchesKeywordTerm(text: string, term: string) {
  const normalizedText = normalizeSearchText(text);
  const normalizedTerm = term.replace(/[^a-z0-9]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (!normalizedTerm) return false;
  return normalizedText.includes(` ${normalizedTerm} `);
}

function getSourceTypeLabel(sourceType?: string) {
  if (!sourceType) return '';
  return SOURCE_TYPE_LABELS[sourceType] || sourceType;
}

function getSourceTypeTint(sourceType?: string) {
  if (!sourceType) return 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-500/15 dark:text-slate-300 dark:border-slate-400/20';
  return SOURCE_TYPE_TINTS[sourceType] || 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-500/15 dark:text-slate-300 dark:border-slate-400/20';
}


// Inline tooltip button — shows a ? icon; clicking toggles a popover below it.
function InfoTip({ text, id, active, onToggle }: { text: string; id: string; active: boolean; onToggle: (id: string) => void }) {
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        onClick={() => onToggle(id)}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300"
        aria-label="More information"
      >
        <HelpCircle className="h-3.5 w-3.5" />
      </button>
      {active && (
        <div className="absolute left-0 top-5 z-50 w-72 rounded-xl border border-slate-200 bg-white p-3 text-[11px] leading-relaxed text-slate-600 shadow-lg dark:border-slate-700 dark:bg-[#0f1726] dark:text-slate-400">
          {text}
        </div>
      )}
    </span>
  );
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

export default function NewsPage() {
  const [registeredCompanies, setRegisteredCompanies] = useState<RegisteredCompany[]>(DEFAULT_COMPANIES);
  const [selectedCompany, setSelectedCompany] = useState<string>('ALL');
  const [keyword, setKeyword] = useState('');
  const [inputKeyword, setInputKeyword] = useState('');
  const [companyNews, setCompanyNews] = useState<Record<string, NewsItem[]>>({});
  const [companyTopNews, setCompanyTopNews] = useState<Record<string, NewsItem[]>>({});
  const [companyWeeklySummary, setCompanyWeeklySummary] = useState<Record<string, { text: string; status: string }>>({});

  // New-company input state
  const [showAddInput, setShowAddInput] = useState(false);
  const [companyInput, setCompanyInput] = useState('');
  const [suggestions, setSuggestions] = useState<ResolvedCompany[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [pendingCompany, setPendingCompany] = useState<ResolvedCompany | null>(null);
  const [savingCompany, setSavingCompany] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [deletingTicker, setDeletingTicker] = useState<string | null>(null);
  const suggestDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Derived: companyMeta for fast ticker lookups
  const companyMeta = useMemo(() => {
    const meta: Record<string, RegisteredCompany> = {};
    registeredCompanies.forEach((c) => { meta[c.ticker] = c; });
    return meta;
  }, [registeredCompanies]);
  const [weeklyTopNewsSummary, setWeeklyTopNewsSummary] = useState<{ text: string; status: string }>({ text: '', status: '' });
  const [allTrending, setAllTrending] = useState<TrendingCluster[]>([]);
  const [allSecItems, setAllSecItems] = useState<UnifiedNewsItem[]>([]);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<'news' | 'sec'>('news');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [topControlsExpanded, setTopControlsExpanded] = useState(true);
  const [weeklySummaryExpanded, setWeeklySummaryExpanded] = useState(false);
  const [trendingExpanded, setTrendingExpanded] = useState(true);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [tooltip, setTooltip] = useState<string | null>(null);

  // ── Load registered companies from API ──────────────────────────────────
  const loadCompanies = useCallback(async () => {
    try {
      const resp = await fetch(`${API_URL}/api/news/companies`);
      if (!resp.ok) return;
      const data = await resp.json();
      const apiCompanies: RegisteredCompany[] = (data.companies || []).map(
        (c: { ticker: string; full_name: string; display_name: string; official_domain: string; official_website: string; aliases: string; industry: string; is_builtin?: boolean; is_deletable?: boolean }, idx: number) => ({
          ticker: c.ticker,
          full_name: c.full_name,
          display_name: c.display_name,
          official_domain: c.official_domain,
          official_website: c.official_website,
          aliases: c.aliases,
          industry: c.industry,
          is_builtin: c.is_builtin,
          is_deletable: c.is_deletable,
          color: COMPANY_COLOR_OVERRIDES[c.ticker] ?? COMPANY_COLOR_PALETTE[idx % COMPANY_COLOR_PALETTE.length],
        })
      );
      if (apiCompanies.length > 0) setRegisteredCompanies(apiCompanies);
    } catch {
      // keep default seed on error
    }
  }, []);

  // ── Suggest autocomplete ─────────────────────────────────────────────────
  const fetchSuggestions = useCallback(async (query: string) => {
    const cleaned = preprocessCompanyInput(query);
    if (cleaned.length < 2) { setSuggestions([]); setShowSuggestions(false); return; }
    if (looksLikeMultipleCompanies(cleaned)) { setSuggestions([]); setShowSuggestions(false); return; }
    try {
      const resp = await fetch(`${API_URL}/api/news/companies/suggest?q=${encodeURIComponent(cleaned)}`);
      if (resp.ok) {
        const data = await resp.json();
        setSuggestions(data.candidates || []);
        setShowSuggestions(true);
      }
    } catch { /* ignore */ }
  }, []);

  const handleCompanyInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setCompanyInput(value);
    if (suggestDebounceRef.current) clearTimeout(suggestDebounceRef.current);
    suggestDebounceRef.current = setTimeout(() => fetchSuggestions(value), 300);
  };

  // ── Resolve → confirmation card ──────────────────────────────────────────
  const handleSelectSuggestion = async (candidate: ResolvedCompany) => {
    setShowSuggestions(false);
    setResolving(true);
    try {
      const resp = await fetch(`${API_URL}/api/news/companies/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_name: candidate.company_name, ticker: candidate.ticker, official_website: candidate.official_website }),
      });
      if (resp.ok) setPendingCompany(await resp.json());
    } catch { /* ignore */ }
    finally { setResolving(false); }
  };

  // ── Save company ─────────────────────────────────────────────────────────
  const handleSaveCompany = async () => {
    if (!pendingCompany) return;
    setSavingCompany(true);
    setSaveError('');
    try {
      // Step 1: generate templates
      const previewResp = await fetch(`${API_URL}/api/news/companies/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: pendingCompany.ticker,
          full_name: pendingCompany.company_name,
          aliases: pendingCompany.aliases.join(','),
          industry: '',
        }),
      });
      if (!previewResp.ok) throw new Error('Template generation failed');
      const previewData = await previewResp.json();

      // Step 2: save
      const saveResp = await fetch(`${API_URL}/api/news/companies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company: {
            ticker: pendingCompany.ticker,
            full_name: pendingCompany.company_name,
            aliases: pendingCompany.aliases.join(','),
            industry: '',
            official_domain: pendingCompany.official_domain,
            official_website: pendingCompany.official_website,
          },
          queries: previewData.templates,
        }),
      });
      if (!saveResp.ok) {
        const err = await saveResp.json();
        throw new Error(err.detail || 'Save failed');
      }

      // Step 3: fetch only this company's freshly-initialized cache
      try {
        const companyResp = await fetch(`${API_URL}/api/news/company/${pendingCompany.ticker}`);
        if (companyResp.ok) {
          const companyData = await companyResp.json();
          setCompanyNews((prev) => ({ ...prev, [pendingCompany.ticker]: companyData.items || [] }));
          setCompanyTopNews((prev) => ({ ...prev, [pendingCompany.ticker]: companyData.top_news || [] }));
          setCompanyWeeklySummary((prev) => ({ ...prev, [pendingCompany.ticker]: { text: companyData.weekly_summary || '', status: companyData.weekly_summary_meta?.summary_status || '' } }));
          const companySecItems = (companyData.sec_items || []).map((item: NewsItem) => toUnifiedItem(item, pendingCompany.ticker));
          setAllSecItems((prev) => [
            ...prev.filter((item) => item.company !== pendingCompany.ticker),
            ...companySecItems,
          ]);
        }
      } catch {
        // non-blocking
      }

      // Refresh aggregate summary/trending cheaply from caches only.
      try {
        const allResp = await fetch(`${API_URL}/api/news/all`);
        if (allResp.ok) {
          const allData = await allResp.json();
          setWeeklyTopNewsSummary({ text: allData.weekly_summary || '', status: allData.weekly_summary_meta?.summary_status || '' });
          setAllTrending(allData.trending || []);
        }
      } catch {
        // non-blocking
      }

      // Step 4: reload list, close panel
      setSelectedCompany(pendingCompany.ticker);
      setPendingCompany(null);
      setCompanyInput('');
      setShowAddInput(false);
      await loadCompanies();
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setSavingCompany(false);
    }
  };

  const handleDeleteCompany = async (ticker: string) => {
    if (!window.confirm(`Delete ${ticker} and remove its cache, summaries, and related data?`)) return;
    setDeletingTicker(ticker);
    try {
      const resp = await fetch(`${API_URL}/api/news/companies/${ticker}`, { method: 'DELETE' });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || 'Delete failed');
      }
      setRegisteredCompanies((prev) => prev.filter((company) => company.ticker !== ticker));
      setCompanyNews((prev) => {
        const next = { ...prev };
        delete next[ticker];
        return next;
      });
      setCompanyTopNews((prev) => {
        const next = { ...prev };
        delete next[ticker];
        return next;
      });
      setCompanyWeeklySummary((prev) => {
        const next = { ...prev };
        delete next[ticker];
        return next;
      });
      setAllSecItems((prev) => prev.filter((item) => item.company !== ticker));
      if (selectedCompany === ticker) {
        setSelectedCompany('ALL');
      }
      try {
        const allResp = await fetch(`${API_URL}/api/news/all`);
        if (allResp.ok) {
          const allData = await allResp.json();
          setWeeklyTopNewsSummary({ text: allData.weekly_summary || '', status: allData.weekly_summary_meta?.summary_status || '' });
          setAllTrending(allData.trending || []);
        }
      } catch {
        // non-blocking
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setDeletingTicker(null);
    }
  };

  const fetchAllNews = async (showLoader = false, forceRefresh = false) => {
    if (showLoader) setLoading(true);
    try {
      const forceParam = forceRefresh ? '?force_refresh=true' : '';
      const fetchOptions: RequestInit = forceRefresh ? { cache: 'no-store' } : {};

      const tickers = registeredCompanies.map((c) => c.ticker);
      const results = await Promise.allSettled(
        tickers.map((ticker) =>
          fetch(`${API_URL}/api/news/company/${ticker}${forceParam}`, fetchOptions).then((r) =>
            r.ok ? r.json() : Promise.resolve({ items: [] })
          )
        )
      );

      const newsMap: Record<string, NewsItem[]> = {};
      const topNewsMap: Record<string, NewsItem[]> = {};
      const weeklySummaryMap: Record<string, { text: string; status: string }> = {};
      const secItems: UnifiedNewsItem[] = [];
      tickers.forEach((ticker, idx) => {
        const result = results[idx];
        if (result.status === 'fulfilled') {
          newsMap[ticker] = result.value.items || [];
          topNewsMap[ticker] = result.value.top_news || [];
          weeklySummaryMap[ticker] = { text: result.value.weekly_summary || '', status: result.value.weekly_summary_meta?.summary_status || '' };
          (result.value.sec_items || []).forEach((item: NewsItem) =>
            secItems.push(toUnifiedItem(item, ticker))
          );
        }
      });
      // Merge with existing data so UI doesn't flash empty during refresh
      setCompanyNews((prev) => ({ ...prev, ...newsMap }));
      setCompanyTopNews((prev) => ({ ...prev, ...topNewsMap }));
      setCompanyWeeklySummary((prev) => ({ ...prev, ...weeklySummaryMap }));
      setAllSecItems(secItems);

      // Fetch aggregate view: global weekly summary and trending
      try {
        const allResp = await fetch(`${API_URL}/api/news/all`, forceRefresh ? { cache: 'no-store' } : {});
        if (allResp.ok) {
          const allData = await allResp.json();
          setWeeklyTopNewsSummary({ text: allData.weekly_summary || '', status: allData.weekly_summary_meta?.summary_status || '' });
          setAllTrending(allData.trending || []);
        }
      } catch {
        // Non-blocking
      }
    } catch (err) {
      console.error('Failed to fetch news:', err);
    } finally {
      if (showLoader) setLoading(false);
    }
  };

  useEffect(() => {
    loadCompanies().then(() => fetchAllNews(true));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const saved = localStorage.getItem('news_keyword');
    if (saved) setKeyword(saved);
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

  const togglePreset = (label: string) => {
    setActivePreset((prev) => (prev === label ? null : label));
  };

  const allCompanyNews = useMemo(() => {
    const merged: UnifiedNewsItem[] = [];
    for (const { ticker } of registeredCompanies) {
      for (const item of (companyNews[ticker] || [])) merged.push(toUnifiedItem(item, ticker));
    }
    return merged;
  }, [companyNews, registeredCompanies]);

  const allCompanyTopNews = useMemo(() => {
    const merged: UnifiedNewsItem[] = [];
    for (const { ticker } of registeredCompanies) {
      for (const item of (companyTopNews[ticker] || [])) merged.push(toUnifiedItem(item, ticker));
    }
    return merged;
  }, [companyTopNews, registeredCompanies]);

  const displayFeed = useMemo(() => {
    const hasKeyword = Boolean(keyword.trim());
    let feed = [...allCompanyNews];

    if (selectedCompany !== 'ALL') {
      feed = feed.filter((item) => item.company === selectedCompany);
    }

    // Preset filter (independent of manual keyword)
    if (activePreset) {
      const presetDef = KEYWORD_PRESETS.find((p) => p.label === activePreset);
      if (presetDef) {
        feed = feed.filter((item) => {
          const searchBase = [item.title, item.description].join(' ');
          return presetDef.keywords.some((kw) => matchesKeywordTerm(searchBase, kw));
        });
      }
    }

    // Manual keyword filter (AND with preset if both active)
    if (hasKeyword) {
      const terms = splitKeywordTerms(keyword);
      feed = feed.filter((item) => {
        const searchBase = [item.title, item.description, item.source,
          item.company ? companyMeta[item.company]?.display_name || item.company : ''].join(' ');
        return terms.some((term) => matchesKeywordTerm(searchBase, term));
      });
    }
    return [...feed].sort((a, b) => getPublishedTimestamp(b.published) - getPublishedTimestamp(a.published));
  }, [allCompanyNews, selectedCompany, keyword, activePreset]);

  const filteredFeed = displayFeed;

  const topNewsFeed = useMemo(() => {
    let feed = [...allCompanyTopNews];

    if (selectedCompany !== 'ALL') {
      feed = feed.filter((item) => item.company === selectedCompany);
    }

    if (activePreset) {
      const presetDef = KEYWORD_PRESETS.find((p) => p.label === activePreset);
      if (presetDef) {
        feed = feed.filter((item) => {
          const searchBase = [item.title, item.description].join(' ');
          return presetDef.keywords.some((kw) => matchesKeywordTerm(searchBase, kw));
        });
      }
    }

    if (keyword.trim()) {
      const terms = splitKeywordTerms(keyword);
      feed = feed.filter((item) => {
        const searchBase = [
          item.title,
          item.description,
          item.source,
          item.company ? companyMeta[item.company]?.display_name || item.company : '',
        ].join(' ');
        return terms.some((term) => matchesKeywordTerm(searchBase, term));
      });
    }

    return [...feed].sort((a, b) => getPublishedTimestamp(b.published) - getPublishedTimestamp(a.published));
  }, [allCompanyTopNews, selectedCompany, keyword, activePreset]);

  const TOP_NEWS_COUNT = 7;
  const activePresetDef = useMemo(
    () => KEYWORD_PRESETS.find((preset) => preset.label === activePreset) || null,
    [activePreset]
  );
  const hasPendingKeyword = inputKeyword.trim() !== keyword.trim();
  const hasActiveFilters = Boolean(activePreset || keyword.trim());

  // Pick the weekly summary that matches the current scope
  const activeWeeklySummary = useMemo(() => {
    if (selectedCompany === 'ALL') return weeklyTopNewsSummary;
    return companyWeeklySummary[selectedCompany] || { text: '', status: '' };
  }, [selectedCompany, weeklyTopNewsSummary, companyWeeklySummary]);

  // SEC feed — company-filtered, sorted by recency
  const secFeed = useMemo(() => {
    let feed = [...allSecItems];
    if (selectedCompany !== 'ALL') {
      feed = feed.filter((item) => item.company === selectedCompany);
    }
    return feed.sort((a, b) => getPublishedTimestamp(b.published) - getPublishedTimestamp(a.published));
  }, [allSecItems, selectedCompany]);

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
      <div className="mx-auto max-w-[1720px] px-4 py-3 sm:px-5">
        <div className="mb-3 rounded-[24px] border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-slate-100 p-3 dark:border-slate-800 dark:from-[#0b1220] dark:via-[#0a101c] dark:to-[#0b1220]">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2.5">
                <h1 className="shrink-0 text-xl font-semibold tracking-tight text-slate-900 dark:text-white">News Monitor</h1>
                <InfoTip
                  id="news-monitor"
                  active={tooltip === 'news-monitor'}
                  onToggle={(id) => setTooltip((prev) => (prev === id ? null : id))}
                  text="Company search uses fuzzy matching and AI-assisted identification. Coverage focuses on common listed companies. Results are advisory candidates — accuracy improves with stronger data sources."
                />
                <div className="flex flex-wrap gap-1">
                  {registeredCompanies.map((company) => (
                    <div key={company.ticker} className="group relative inline-flex">
                      <a
                        href={company.official_website || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={`${company.display_name} — official portal`}
                        className="inline-flex items-center justify-center rounded px-2 py-0.5 text-[10px] font-bold leading-none text-white opacity-90 transition hover:opacity-100"
                        style={{ backgroundColor: company.color }}
                      >
                        {company.ticker}
                      </a>
                      {company.is_deletable ? (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            void handleDeleteCompany(company.ticker);
                          }}
                          title={`Delete ${company.ticker}`}
                          disabled={deletingTicker === company.ticker}
                          className="absolute -right-1 -top-1 hidden h-3.5 w-3.5 items-center justify-center rounded-full border border-slate-300 bg-white text-slate-500 shadow-sm transition hover:border-rose-300 hover:text-rose-600 disabled:opacity-50 group-hover:inline-flex group-focus-within:inline-flex dark:border-slate-600 dark:bg-[#0b111d] dark:text-slate-300 dark:hover:border-rose-500/50 dark:hover:text-rose-300"
                        >
                          <X className="h-2.5 w-2.5" />
                        </button>
                      ) : null}
                    </div>
                  ))}
                  {/* Add company button */}
                  <button
                    onClick={() => { setShowAddInput((v) => !v); setCompanyInput(''); setSuggestions([]); setShowSuggestions(false); }}
                    title="Add company"
                    className="inline-flex items-center justify-center rounded px-1.5 py-0.5 text-[10px] font-bold leading-none border border-dashed border-slate-400 text-slate-500 opacity-80 transition hover:opacity-100 hover:border-cyan-400 hover:text-cyan-600 dark:border-slate-600 dark:text-slate-400 dark:hover:border-cyan-500 dark:hover:text-cyan-400"
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-1.5">
                <button
                  onClick={() => setTopControlsExpanded((prev) => !prev)}
                  title={topControlsExpanded ? 'Collapse filters' : 'Expand filters'}
                  aria-label={topControlsExpanded ? 'Collapse filters' : 'Expand filters'}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-500 transition hover:border-slate-400 hover:bg-slate-50 hover:text-cyan-700 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-400 dark:hover:border-slate-600 dark:hover:bg-[#0f1726] dark:hover:text-cyan-300"
                >
                  <ChevronDown className={`h-3.5 w-3.5 transition-transform ${topControlsExpanded ? 'rotate-180' : ''}`} />
                </button>
                <button
                  onClick={refreshNews}
                  disabled={refreshing}
                  title={refreshing ? 'Refreshing...' : 'Refresh'}
                  aria-label={refreshing ? 'Refreshing' : 'Refresh'}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-500 transition hover:border-slate-400 hover:bg-slate-50 hover:text-cyan-700 disabled:opacity-50 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-400 dark:hover:border-slate-600 dark:hover:bg-[#0f1726] dark:hover:text-cyan-300"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
                </button>
                <a
                  href={PROJECT_GITHUB_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Project repository"
                  aria-label="Project repository"
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-500 transition hover:border-slate-400 hover:bg-slate-50 hover:text-cyan-700 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-400 dark:hover:border-slate-600 dark:hover:bg-[#0f1726] dark:hover:text-cyan-300"
                >
                  {/* eslint-disable-next-line deprecation/deprecation */}
                  <Github className="h-3.5 w-3.5" />
                </a>
              </div>
            </div>

            {/* Add-company input row */}
            {showAddInput && (
              <div className="relative flex items-center gap-2">
                <div className="relative flex-1 max-w-xs">
                  <input
                    autoFocus
                    value={companyInput}
                    onChange={handleCompanyInputChange}
                    onKeyDown={(e) => { if (e.key === 'Escape') { setShowAddInput(false); setShowSuggestions(false); } }}
                    placeholder="Company name, ticker, or alias…"
                    maxLength={64}
                    className="w-full rounded-lg border border-slate-300 bg-white py-1 pl-3 pr-8 text-xs text-slate-900 outline-none transition focus:border-cyan-400 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-100 dark:focus:border-cyan-500"
                  />
                  {resolving && (
                    <span className="absolute right-2 top-1/2 -translate-y-1/2">
                      <RefreshCw className="h-3 w-3 animate-spin text-slate-400" />
                    </span>
                  )}
                  {/* Multi-company warning (§5.3.2) */}
                  {companyInput.trim().length >= 2 && looksLikeMultipleCompanies(preprocessCompanyInput(companyInput)) && (
                    <div className="absolute left-0 top-full z-50 mt-1 w-full rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700 shadow dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                      Please enter one company at a time.
                    </div>
                  )}
                  {/* Suggestions dropdown */}
                  {showSuggestions && suggestions.length > 0 && (
                    <div className="absolute left-0 top-full z-50 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-[#0f1726]">
                      {suggestions.map((s) => (
                        <button
                          key={s.ticker}
                          onClick={() => handleSelectSuggestion(s)}
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-slate-50 dark:hover:bg-white/5"
                        >
                          <span className="font-bold text-slate-900 dark:text-white">{s.ticker}</span>
                          <span className="text-slate-600 dark:text-slate-400">{s.company_name}</span>
                          {s.source === 'llm' && (
                            <span className="ml-auto rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">AI</span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => { setShowAddInput(false); setShowSuggestions(false); setCompanyInput(''); }}
                  className="inline-flex h-6 w-6 items-center justify-center rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            )}

            {topControlsExpanded && (
              <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-slate-200 bg-white/90 px-2.5 py-2 dark:border-slate-800 dark:bg-[#0a101c]">
                {/* Topic presets — state is independent of the search input */}
                {KEYWORD_PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    onClick={() => togglePreset(preset.label)}
                    className={`rounded-full border px-2.5 py-0.5 text-xs transition ${
                      activePreset === preset.label
                        ? 'border-cyan-300 bg-cyan-50 text-cyan-700 dark:border-cyan-400/60 dark:bg-cyan-500/20 dark:text-cyan-200'
                        : 'border-slate-300 bg-white text-slate-600 hover:border-slate-400 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-400 dark:hover:border-slate-600'
                    }`}
                  >
                    {preset.label}
                  </button>
                ))}

                {/* Search input — narrowed, shows only user-typed text */}
                <div className="relative w-36">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
                  <input
                    value={inputKeyword}
                    onChange={(e) => setInputKeyword(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') applyKeyword(inputKeyword); }}
                    placeholder="Search…"
                    className="w-full rounded-lg border border-slate-300 bg-white py-0.5 pl-7 pr-2 text-xs text-slate-900 outline-none transition focus:border-cyan-400 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-100"
                  />
                </div>
                <button
                  onClick={() => applyKeyword(inputKeyword)}
                  disabled={!hasPendingKeyword}
                  title={hasPendingKeyword ? 'Apply search keyword' : 'No pending search changes'}
                  className={`inline-flex h-6 w-6 items-center justify-center rounded-md border transition ${
                    hasPendingKeyword
                      ? 'border-cyan-400 bg-cyan-50 text-cyan-700 hover:bg-cyan-100 dark:border-cyan-500/50 dark:bg-cyan-500/10 dark:text-cyan-300 dark:hover:bg-cyan-500/20'
                      : 'border-slate-300 bg-slate-50 text-slate-400 cursor-default dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-600'
                  }`}
                >
                  <Check className="h-3.5 w-3.5" />
                </button>

                <span className="h-4 w-px shrink-0 bg-slate-200 dark:bg-slate-700" />

                {/* Company scope */}
                <button
                  onClick={() => setSelectedCompany('ALL')}
                  className={`rounded-full px-2.5 py-0.5 text-xs transition ${
                    selectedCompany === 'ALL'
                      ? 'bg-blue-500 text-white'
                      : 'border border-slate-300 bg-white text-slate-600 hover:border-slate-400 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-400'
                  }`}
                >
                  All
                </button>
                {registeredCompanies.map((company) => (
                  <button
                    key={company.ticker}
                    onClick={() => setSelectedCompany(company.ticker)}
                    className={`rounded-full px-2.5 py-0.5 text-xs transition ${
                      selectedCompany === company.ticker
                        ? 'text-white'
                        : 'border border-slate-300 bg-white text-slate-600 hover:border-slate-400 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-400'
                    }`}
                    style={selectedCompany === company.ticker ? { backgroundColor: company.color } : {}}
                  >
                    {company.display_name}
                  </button>
                ))}
              </div>
            )}

            {/* Active filter state — always visible regardless of topControlsExpanded (§9.3) */}
            {(activePresetDef || keyword.trim()) && (
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-600 dark:border-slate-800 dark:bg-[#0b1220] dark:text-slate-400">
                {activePresetDef && (
                  <div>
                    <span className="font-semibold text-slate-700 dark:text-slate-300">{activePresetDef.label}</span>
                    <span className="ml-2 text-slate-500 dark:text-slate-500">
                      {activePresetDef.keywords.join(' · ')}
                    </span>
                    <button
                      onClick={() => setActivePreset(null)}
                      className="ml-2 text-slate-400 hover:text-rose-500 dark:hover:text-rose-400"
                      title="Clear preset"
                    >×</button>
                  </div>
                )}
                {keyword.trim() && (
                  <div className={activePresetDef ? 'mt-1' : ''}>
                    <span className="font-semibold text-slate-700 dark:text-slate-300">Search</span>
                    <span className="ml-2 text-slate-500 dark:text-slate-500">{keyword.trim()}</span>
                    <button
                      onClick={() => applyKeyword('')}
                      className="ml-2 text-slate-400 hover:text-rose-500 dark:hover:text-rose-400"
                      title="Clear search"
                    >×</button>
                  </div>
                )}
              </div>
            )}

          </div>
        </div>

        <div className="flex gap-4 items-start">
          <section className="flex-1 min-w-0 rounded-2xl border border-slate-200 bg-white p-4 flex flex-col dark:border-slate-800 dark:bg-[#0a101c]">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h2 className="text-3xl font-semibold text-slate-900 dark:text-white">Top News</h2>
                <InfoTip
                  id="top-news"
                  active={tooltip === 'top-news'}
                  onToggle={(id) => setTooltip((prev) => (prev === id ? null : id))}
                  text="Top News ranks articles from the current news pipeline using recency and relevance signals. Single-article summaries and the Weekly Summary are generated by an AI model and cached. Quality improves with more complete article context."
                />
              </div>
              <button
                onClick={() => setWeeklySummaryExpanded((prev) => !prev)}
                className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-semibold text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-200 dark:hover:border-slate-600 dark:hover:bg-[#0f1726]"
              >
                <span className="text-slate-400 dark:text-slate-500 font-normal">Weekly</span>
                <span>Summary</span>
                <ChevronDown className={`h-3.5 w-3.5 transition-transform ${weeklySummaryExpanded ? 'rotate-180' : ''}`} />
              </button>
            </div>

            <div className="flex flex-col gap-3">
              {/* Top News list + weekly summary side-by-side */}
              <div className="flex gap-3">
                {/* Left: ranked article list */}
                <div className="flex flex-col gap-1.5 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-[#0b1220] flex-1 min-w-0">
                  {topNewsFeed.slice(0, TOP_NEWS_COUNT).map((item, idx) => {
                    return (
                      <a
                        key={`top-${item.title}-${idx}`}
                        href={getSafeHref(item)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block rounded-lg border border-slate-200 bg-slate-50 p-2 transition hover:border-cyan-300 dark:border-slate-800 dark:bg-[#0a101c] dark:hover:border-cyan-500/40"
                      >
                        <div className="flex gap-2">
                          <span className="shrink-0 text-base font-bold text-cyan-500 dark:text-cyan-400">{idx + 1}</span>
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-semibold leading-snug text-slate-900 hover:text-cyan-700 dark:text-white dark:hover:text-cyan-300 line-clamp-2">{item.title}</p>
                            {item.summary && (
                              <p className="mt-0.5 text-[11px] leading-snug text-slate-500 dark:text-slate-400 line-clamp-2">{item.summary}</p>
                            )}
                            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                              {item.source_type && (
                                <span className={`rounded border px-1.5 py-0.5 ${getSourceTypeTint(item.source_type)}`}>
                                  {getSourceTypeLabel(item.source_type)}
                                </span>
                              )}
                              <Globe2 className="h-3 w-3 shrink-0" />
                              <span>Source: {item.source}</span>
                              <span>•</span>
                              <span>{item.timestampLabel}</span>
                              {item.company && <span className="rounded border border-slate-300 px-1.5 py-0.5 dark:border-slate-700">{companyMeta[item.company]?.display_name || item.company}</span>}
                            </div>
                          </div>
                        </div>
                      </a>
                    );
                  })}
                </div>

                {/* Right: weekly summary panel */}
                {weeklySummaryExpanded && (
                  <div className="w-60 shrink-0 rounded-xl border border-slate-200 bg-slate-50 p-3 flex flex-col gap-2 dark:border-slate-800 dark:bg-[#0b1220]">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-300">Weekly Summary</p>
                    {hasActiveFilters ? (
                      <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                        Weekly Summary reflects the unfiltered Top News scope. Clear keyword filters to view the generated summary.
                      </p>
                    ) : activeWeeklySummary.text ? (
                      <>
                        <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">{activeWeeklySummary.text}</p>
                        {activeWeeklySummary.status === 'fallback_used' && (
                          <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-600 italic">Some articles used description as fallback input.</p>
                        )}
                      </>
                    ) : activeWeeklySummary.status === 'failed' ? (
                      <p className="text-xs text-slate-400 dark:text-slate-600 italic">Not enough articles to generate a summary.</p>
                    ) : (
                      <p className="text-xs text-slate-400 dark:text-slate-600 italic">Summary generating…</p>
                    )}
                  </div>
                )}
              </div>

              {selectedCompany === 'ALL' && (
                <div className="flex flex-col rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-[#0b1220]">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Flame className="h-5 w-5 text-orange-400" />
                      <h3 className="text-base font-semibold text-slate-900 dark:text-white">Trending</h3>
                      <span className="text-[11px] text-slate-400 dark:text-slate-500">7d · 30d · 60d</span>
                      <InfoTip
                        id="trending"
                        active={tooltip === 'trending'}
                        onToggle={(id) => setTooltip((prev) => (prev === id ? null : id))}
                        text="Trending clusters are discovered dynamically from the current news snapshot using keyword overlap. 7d / 30d / 60d counts show how often a theme appears across time windows — based on articles still in the current snapshot, not a full historical archive."
                      />
                    </div>
                    <button
                      onClick={() => setTrendingExpanded((prev) => !prev)}
                      className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-[#0f1726]"
                    >
                      <span>{trendingExpanded ? 'Collapse' : 'Expand'}</span>
                      <ChevronDown className={`h-3.5 w-3.5 transition-transform ${trendingExpanded ? 'rotate-180' : ''}`} />
                    </button>
                  </div>
                  {!trendingExpanded ? null : allTrending.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-slate-300 p-3 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
                      No trending topics found. Refresh to fetch latest news.
                    </div>
                  ) : (
                    <div className="grid gap-3 lg:grid-cols-2">
                      {allTrending.map((cluster, idx) => (
                        <div key={cluster.trend_cluster_key || cluster.id} className="flex flex-col rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-[#0a101c]">
                          <div className="mb-1 flex items-start justify-between gap-2">
                            <div className="flex min-w-0 items-start gap-2">
                              <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-orange-100 text-[10px] font-bold text-orange-700 dark:bg-orange-500/15 dark:text-orange-300">
                                {idx + 1}
                              </span>
                              <div className="min-w-0">
                                <p className="text-sm font-semibold leading-snug text-slate-900 dark:text-white">{cluster.trend_title}</p>
                                {cluster.keywords && cluster.keywords.length > 0 && (
                                  <p className="mt-1 text-[11px] leading-snug text-slate-500 dark:text-slate-500">
                                    {cluster.keywords.slice(0, 4).join(' · ')}
                                  </p>
                                )}
                              </div>
                            </div>
                            <span className="shrink-0 rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-bold text-orange-700 dark:bg-orange-500/15 dark:text-orange-300">
                              {cluster.supporting_count_30d ?? cluster.cluster_size} articles
                            </span>
                          </div>
                          {(cluster.trend_summary || cluster.summary) && (
                            <p className="mb-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">{cluster.trend_summary || cluster.summary}</p>
                          )}
                          <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                            {cluster.supporting_count_7d !== undefined ? (
                              <>
                                <span className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">7d: {cluster.supporting_count_7d}</span>
                                <span className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">30d: {cluster.supporting_count_30d}</span>
                                <span className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">60d: {cluster.supporting_count_60d}</span>
                                <span>•</span>
                              </>
                            ) : (
                              <><span>{cluster.cluster_size} articles</span><span>•</span></>
                            )}
                            <span>{cluster.companies.length} {cluster.companies.length === 1 ? 'company' : 'companies'}</span>
                          </div>
                          {cluster.companies.length > 0 && (
                            <div className="mb-2 flex flex-wrap gap-1">
                              {cluster.companies.map((co) => (
                                <span key={co} className="rounded border border-slate-300 px-1.5 py-0.5 text-[10px] text-slate-600 dark:border-slate-700 dark:text-slate-400">{co}</span>
                              ))}
                            </div>
                          )}
                          <div className="flex flex-col gap-1">
                            {cluster.representative_items.length === 0 ? (
                              <p className="text-[11px] leading-relaxed text-slate-500 dark:text-slate-500">
                                No matching news in the current window for this theme.
                              </p>
                            ) : (
                              cluster.representative_items.slice(0, 3).map((item, i) => (
                                <a
                                  key={i}
                                  href={getSafeHref(item)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="line-clamp-2 text-xs leading-snug text-cyan-700 hover:text-cyan-500 dark:text-cyan-300 dark:hover:text-cyan-200"
                                >
                                  {i + 1}. {item.title}
                                </a>
                              ))
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>

          <section
            className={`shrink-0 rounded-2xl border flex flex-col xl:sticky xl:top-4 overflow-hidden transition-all duration-200 ${
              rightPanelCollapsed
                ? 'w-8 p-0 border-slate-300 bg-slate-100 dark:border-slate-600 dark:bg-[#111827] cursor-pointer hover:bg-slate-200 dark:hover:bg-[#1a2236]'
                : 'w-[37%] p-4 border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0a101c]'
            }`}
            style={{ maxHeight: 'calc(100vh - 2rem)' }}
            onClick={rightPanelCollapsed ? () => setRightPanelCollapsed(false) : undefined}
            title={rightPanelCollapsed ? 'Expand News Flash panel' : undefined}
          >
            {/* Collapsed state: full-height bar with arrow + rotated label */}
            {rightPanelCollapsed ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 py-4 select-none">
                <ChevronRight className="h-4 w-4 rotate-180 text-slate-400 dark:text-slate-500" />
                <span className="[writing-mode:vertical-rl] rotate-180 text-[10px] font-semibold tracking-widest uppercase text-slate-400 dark:text-slate-500">
                  News Flash
                </span>
              </div>
            ) : (
            <>
            <div className="mb-3 flex items-center justify-between gap-2">
              {/* View toggle tabs */}
              <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-slate-800 dark:bg-[#0b111d]">
                <button
                  onClick={() => setActiveView('news')}
                  className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                    activeView === 'news'
                      ? 'bg-white text-slate-900 shadow-sm dark:bg-[#0f1726] dark:text-white'
                      : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                  }`}
                >
                  News Flash
                </button>
                <button
                  onClick={() => setActiveView('sec')}
                  className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                    activeView === 'sec'
                      ? 'bg-white text-slate-900 shadow-sm dark:bg-[#0f1726] dark:text-white'
                      : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                  }`}
                >
                  SEC Filings
                </button>
              </div>
              <div className="flex items-center gap-1.5">
                <InfoTip
                  id="news-flash"
                  active={tooltip === 'news-flash'}
                  onToggle={(id) => setTooltip((prev) => (prev === id ? null : id))}
                  text="News Flash pulls from Brave News API, company IR RSS feeds, and SEC RSS. SEC RSS may have rate limits or inconsistent availability — results can vary between refreshes. Coverage improves with more stable paid data sources."
                />
                <div className="inline-flex items-center gap-2 rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 dark:border-slate-700 dark:text-slate-400">
                  <Rss className="h-3.5 w-3.5 text-cyan-600 dark:text-cyan-300" />
                  {activeView === 'sec' ? secFeed.length : filteredFeed.length} items
                </div>
                <button
                  onClick={() => setRightPanelCollapsed(true)}
                  title="Collapse panel"
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-500 transition hover:border-slate-400 hover:text-cyan-700 dark:border-slate-700 dark:bg-[#0b111d] dark:text-slate-400 dark:hover:text-cyan-300"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            <div className="space-y-0 flex-1 overflow-y-auto pr-2 xl:[&::-webkit-scrollbar]:w-1.5 xl:[&::-webkit-scrollbar-thumb]:rounded-full xl:[&::-webkit-scrollbar-thumb]:bg-slate-700 xl:[&::-webkit-scrollbar-track]:bg-transparent">
              {activeView === 'news' ? (
                <>
                  {filteredFeed.length === 0 && (
                    <div className="rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
                      No news available for the current company and keyword filters.
                    </div>
                  )}
                  {filteredFeed.map((item, idx) => (
                    <a
                      key={`${item.title}-${idx}`}
                      href={getSafeHref(item)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="grid grid-cols-[56px_minmax(0,1fr)_16px] gap-2 py-2 transition hover:bg-slate-100 dark:hover:bg-white/[0.02]"
                    >
                      <div className="min-w-0">
                        <p className="text-[11px] font-semibold text-cyan-700 dark:text-cyan-300 truncate">{item.timestampLabel}</p>
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold leading-5 text-cyan-700 dark:text-cyan-300 line-clamp-2">{item.title}</p>
                        <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400 line-clamp-2">{item.description}</p>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                          {item.company && <span className="rounded border border-slate-300 px-2 py-0.5 text-slate-700 dark:border-slate-700 dark:text-slate-300">{companyMeta[item.company]?.display_name || item.company}</span>}
                          {item.source_type && (
                            <span className={`rounded border px-2 py-0.5 ${getSourceTypeTint(item.source_type)}`}>
                              {getSourceTypeLabel(item.source_type)}
                            </span>
                          )}
                          <span className="text-slate-600 dark:text-slate-500 truncate">Source: {item.source}</span>
                        </div>
                      </div>
                      <div className="flex items-start justify-end pt-1 text-slate-600 dark:text-slate-500">
                        <ExternalLink className="h-4 w-4 shrink-0" />
                      </div>
                    </a>
                  ))}
                </>
              ) : (
                <>
                  {secFeed.length === 0 && (
                    <div className="rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
                      No SEC filings available. Refresh to fetch the latest filings.
                    </div>
                  )}
                  {secFeed.map((item, idx) => (
                    <a
                      key={`sec-${item.title}-${idx}`}
                      href={getSafeHref(item)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="grid grid-cols-[56px_minmax(0,1fr)_16px] gap-2 py-2 transition hover:bg-slate-100 dark:hover:bg-white/[0.02]"
                    >
                      <div className="min-w-0">
                        <p className="text-[11px] font-semibold text-amber-600 dark:text-amber-400 truncate">{item.timestampLabel}</p>
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold leading-5 text-slate-800 dark:text-slate-100 line-clamp-2">{item.title}</p>
                        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400 line-clamp-2">{item.description}</p>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                          {item.company && <span className="rounded border border-slate-300 px-2 py-0.5 text-slate-700 dark:border-slate-700 dark:text-slate-300">{companyMeta[item.company]?.display_name || item.company}</span>}
                          <span className={`rounded border px-2 py-0.5 ${getSourceTypeTint('sec_filing_rss')}`}>SEC RSS</span>
                          {item.source && <span className="text-slate-600 dark:text-slate-500 truncate">Source: {item.source}</span>}
                        </div>
                      </div>
                      <div className="flex items-start justify-end pt-1 text-slate-600 dark:text-slate-500">
                        <ExternalLink className="h-4 w-4 shrink-0" />
                      </div>
                    </a>
                  ))}
                </>
              )}
            </div>
            </>
            )}
          </section>
        </div>

      </div>

      {/* Confirmation card modal */}
      {pendingCompany && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-[#0f1726]">
            <div className="mb-3 flex items-start justify-between gap-2">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Confirm new company</h3>
              <button onClick={() => { setPendingCompany(null); setSaveError(''); }} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Confidence badge */}
            <div className={`mb-3 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
              pendingCompany.confidence >= 0.85
                ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'
                : pendingCompany.confidence >= 0.60
                ? 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300'
                : 'bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300'
            }`}>
              <span>{Math.round(pendingCompany.confidence * 100)}% confidence</span>
              <span>·</span>
              <span>{pendingCompany.confidence >= 0.85 ? 'High' : pendingCompany.confidence >= 0.60 ? 'Medium — review required' : 'Low — cannot save'}</span>
            </div>

            <dl className="mb-3 space-y-1.5 text-xs">
              <div className="flex gap-2"><dt className="w-24 shrink-0 text-slate-500 dark:text-slate-400">Company</dt><dd className="font-semibold text-slate-900 dark:text-white">{pendingCompany.company_name}</dd></div>
              <div className="flex gap-2"><dt className="w-24 shrink-0 text-slate-500 dark:text-slate-400">Ticker</dt><dd className="font-mono font-bold text-slate-900 dark:text-white">{pendingCompany.ticker}</dd></div>
              <div className="flex gap-2"><dt className="w-24 shrink-0 text-slate-500 dark:text-slate-400">Website</dt><dd className="truncate text-cyan-700 dark:text-cyan-400">{pendingCompany.official_website || '—'}</dd></div>
              <div className="flex gap-2"><dt className="w-24 shrink-0 text-slate-500 dark:text-slate-400">Reason</dt><dd className="text-slate-600 dark:text-slate-400">{pendingCompany.reason}</dd></div>
            </dl>

            {saveError && (
              <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-500/15 dark:text-red-300">{saveError}</p>
            )}

            <div className="flex gap-2">
              <button
                onClick={() => { setPendingCompany(null); setSaveError(''); }}
                className="flex-1 rounded-lg border border-slate-300 py-1.5 text-xs text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveCompany}
                disabled={pendingCompany.confidence < 0.60 || savingCompany}
                className={`flex-1 rounded-lg py-1.5 text-xs font-semibold text-white transition ${
                  pendingCompany.confidence < 0.60
                    ? 'cursor-not-allowed bg-slate-300 dark:bg-slate-700'
                    : 'bg-cyan-600 hover:bg-cyan-500 disabled:opacity-60'
                }`}
              >
                {savingCompany ? 'Saving…' : pendingCompany.confidence < 0.60 ? 'Confidence too low' : 'Confirm & Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
