'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Send,
  Bot,
  User,
  Loader2,
  Database,
  Globe,
  Sparkles,
  Trash2,
  Copy,
  RotateCcw,
  Building2,
  Clock3,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { TableAnswer } from '@/features/chat/TableAnswer';
import remarkGfm from 'remark-gfm';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

type SearchMode = 'rag' | 'web' | 'hybrid';
type CompanyFilter = 'Flex' | 'Jabil' | 'Celestica' | 'Benchmark' | 'Sanmina';
type TimeHorizon = 'Any Time' | 'FY2026' | 'FY2025' | 'Last 12 Months';
type AnswerProvider = 'openai' | 'claude' | 'gemini' | 'none';
type ThreatLevel = 'HIGH' | 'MEDIUM' | 'LOW';

interface TablePayload {
  title: string;
  columns: string[];
  rows: string[][];
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  webSources?: { index: number; title: string; url: string }[];
  table_payload?: TablePayload;
  narrative_text?: string;
  mode?: SearchMode;
  timestamp: Date;
}

interface Source {
  company?: string;
  source?: string;
  filing_type?: string;
  fiscal_year?: string;
  similarity?: number;
}

// ── Static data ───────────────────────────────────────────────────────────────

const COMPANY_COLORS: Record<string, string> = {
  Flex: '#0078FF',
  Jabil: '#10B981',
  Celestica: '#7C3AED',
  Benchmark: '#F59E0B',
  Sanmina: '#EF4444',
};

interface SignalCard {
  company: string;
  event: string;
  signal: string;
  insight: string;
  threat: ThreatLevel;
}

const SIGNAL_CARDS: SignalCard[] = [
  {
    company: 'Jabil',
    event: 'AI server revenue accelerating',
    signal: 'AI-related revenue +32% YoY',
    insight: 'Jabil scaling faster in hyperscaler infrastructure than Flex',
    threat: 'HIGH',
  },
  {
    company: 'Celestica',
    event: 'Expanded AMD partnership',
    signal: 'AI networking platform integration announced',
    insight: 'Strengthening position in AI switching layer, direct overlap with Flex',
    threat: 'HIGH',
  },
  {
    company: 'Benchmark',
    event: 'New facility in Penang',
    signal: '$45M investment, 2026 Q3 online',
    insight: 'Expanding SEA footprint, potential to undercut Flex on regional pricing',
    threat: 'MEDIUM',
  },
  {
    company: 'Sanmina',
    event: 'Server ecosystem wins',
    signal: '3 new hyperscaler qualifications in Q1',
    insight: 'Gaining credibility in AI server supply chain',
    threat: 'MEDIUM',
  },
  {
    company: 'Celestica',
    event: 'Q4 earnings beat',
    signal: 'Revenue +18% YoY, margin expansion',
    insight: 'Strong execution gives them pricing power and investment capacity',
    threat: 'LOW',
  },
];

type StrategyCategory = { id: string; label: string; questions: string[] };

const DEFAULT_STRATEGY_CATEGORIES: StrategyCategory[] = [
  {
    id: 'ai-infra',
    label: 'AI Infrastructure Leadership',
    questions: [
      'Who is gaining share in AI data center hardware?',
      'Compare AI revenue exposure across all 5 companies',
      'Which company is scaling fastest in AI infrastructure?',
      'Compare hyperscaler customer relationships',
    ],
  },
  {
    id: 'capacity',
    label: 'Capacity & Footprint',
    questions: [
      'Where is each company expanding manufacturing capacity?',
      'Compare Mexico / India / Southeast Asia strategies',
      'Who is investing most in liquid cooling production?',
      'Which regions show highest capacity growth risk for Flex?',
    ],
  },
  {
    id: 'financial',
    label: 'Financial Performance',
    questions: [
      'Compare gross margin trends across companies',
      'Which company shows strongest revenue growth momentum?',
      'Analyze backlog and demand signals by company',
      'Compare CapEx intensity as % of revenue',
    ],
  },
  {
    id: 'risks',
    label: 'Risks & External Factors',
    questions: [
      'Compare tariff and geopolitical exposure by company',
      'Identify supply chain concentration risks',
      'Analyze customer concentration risk',
      'Which competitor is most exposed to AI spending slowdown?',
    ],
  },
];

const COMPANY_FILTERS: CompanyFilter[] = ['Flex', 'Jabil', 'Celestica', 'Benchmark', 'Sanmina'];
const TIME_HORIZONS: TimeHorizon[] = ['Any Time', 'FY2026', 'FY2025', 'Last 12 Months'];

const COMPARE_SUFFIX = ' — Compare Flex vs Jabil vs Celestica vs Benchmark vs Sanmina';

const STRUCTURED_RESPONSE_INSTRUCTION = `Structure every response with exactly three sections:
1. KEY CONCLUSION: 2-3 sentences ranking companies or stating the main finding
2. SUPPORTING EVIDENCE: 3-5 bullet points with specific data points
3. IMPLICATION FOR FLEX: 1-2 sentences on what Flex should do or watch

`;

const modeConfig = {
  rag:    { icon: Database,  label: 'Filing Search', color: 'bg-blue-100 text-blue-700 border-blue-200',    activeClass: 'border-blue-300 bg-blue-50 text-blue-900 shadow-sm',    desc: 'SEC docs' },
  web:    { icon: Globe,     label: 'Web Search',    color: 'bg-emerald-100 text-emerald-700 border-emerald-200', activeClass: 'border-emerald-300 bg-emerald-50 text-emerald-900 shadow-sm', desc: 'Public web' },
  hybrid: { icon: Sparkles,  label: 'Hybrid Search', color: 'bg-cyan-100 text-cyan-700 border-cyan-200',    activeClass: 'border-cyan-300 bg-cyan-50 text-cyan-900 shadow-sm',    desc: 'Docs + web' },
} as const;

// ── Sub-components ────────────────────────────────────────────────────────────

function ThreatPill({ level }: { level: ThreatLevel }) {
  const styles: Record<ThreatLevel, string> = {
    HIGH:   'bg-red-500 text-white',
    MEDIUM: 'bg-orange-500 text-white',
    LOW:    'bg-green-500 text-white',
  };
  const labels: Record<ThreatLevel, string> = { HIGH: '🔴 HIGH', MEDIUM: '🟠 MED', LOW: '🟢 LOW' };
  return (
    <span className={`rounded-full px-1.5 py-px text-[9px] font-bold whitespace-nowrap ${styles[level]}`}>
      {labels[level]}
    </span>
  );
}

function CompactSignalCard({ card }: { card: SignalCard }) {
  const color = COMPANY_COLORS[card.company] || '#64748B';
  return (
    <div className="w-[280px] shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-900/80">
      {/* Top row: badge + company name + threat pill */}
      <div className="mb-1.5 flex items-center gap-1.5">
        <div
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[10px] font-bold text-white"
          style={{ backgroundColor: color }}
        >
          {card.company.charAt(0)}
        </div>
        <span className="min-w-0 flex-1 truncate text-xs font-semibold text-slate-900 dark:text-slate-100">
          {card.company}
        </span>
        <ThreatPill level={card.threat} />
      </div>
      {/* Event headline — 1 line, truncated */}
      <p className="mb-0.5 truncate text-[11px] font-medium leading-tight text-slate-700 dark:text-slate-200">
        {card.event}
      </p>
      {/* Signal metric — blue, 1 line */}
      <p className="truncate text-[11px] font-semibold leading-tight text-blue-700 dark:text-blue-300">
        {card.signal}
      </p>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [strategyCategories, setStrategyCategories] = useState<StrategyCategory[]>(DEFAULT_STRATEGY_CATEGORIES);
  const [categoriesLoading, setCategoriesLoading] = useState(true);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [mode, setMode] = useState<SearchMode>('rag');
  const [selectedCompanies, setSelectedCompanies] = useState<CompanyFilter[]>([]);
  const [timeHorizon, setTimeHorizon] = useState<TimeHorizon>('Any Time');
  const [answerProvider, setAnswerProvider] = useState<AnswerProvider>('none');
  const [enableFallback, setEnableFallback] = useState(false);
  const [strictGrounding, setStrictGrounding] = useState(true);
  const [maxResponseWords] = useState('200');
  const [lastCopiedId, setLastCopiedId] = useState<string | null>(null);
  const [currentSessionId, setCurrentSessionId] = useState(() => `session_${Date.now()}`);
  const [chatHistory, setChatHistory] = useState<{ session_id: string; title: string; created_at: string }[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  // Dropdown per category pill (replaces openCategory + expanded section)
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  // Signals collapse toggle
  const [signalsCollapsed, setSignalsCollapsed] = useState(false);
  // Recents sidebar toggle
  const [recentsOpen, setRecentsOpen] = useState(true);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);

  const messagesAreaRef   = useRef<HTMLDivElement>(null);
  const inputRef          = useRef<HTMLInputElement>(null);
  const inputDockRef      = useRef<HTMLDivElement>(null);
  const settingsBtnRef    = useRef<HTMLButtonElement>(null);
  const settingsPanelRef  = useRef<HTMLDivElement>(null);
  const dropdownBtnRefs   = useRef<Record<string, HTMLButtonElement | null>>({});
  const dropdownPanelRef  = useRef<HTMLDivElement>(null);

  // Load preset questions from backend on mount
  useEffect(() => {
    const loadPresetQuestions = async () => {
      try {
        const res = await fetch(`${API_URL}/api/chat/preset-questions`);
        if (!res.ok) throw new Error('Failed to fetch');
        const data = await res.json();
        if (data.categories && data.categories.length > 0) {
          setStrategyCategories(data.categories);
        }
      } catch {
        // 加载失败时保留默认问题
      } finally {
        setCategoriesLoading(false);
      }
    };
    loadPresetQuestions();
  }, []);

  // Load chat history on mount
  useEffect(() => {
    const loadHistory = async () => {
      try {
        const res = await fetch(`${API_URL}/api/chat/history`);
        const data = await res.json();
        setChatHistory(data.history || []);
      } catch {}
    };
    loadHistory();
  }, []);

  // Auto-scroll messages to bottom
  useEffect(() => {
    const el = messagesAreaRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, isLoading]);

  // Sync mode → provider/fallback
  useEffect(() => {
    if (mode === 'hybrid') {
      setAnswerProvider((prev) => (prev === 'none' ? 'openai' : prev));
      setEnableFallback(true);
    } else {
      setAnswerProvider('none');
      setEnableFallback(false);
      setStrictGrounding(true);
    }
  }, [mode]);

  // Close settings on outside click or ESC
  useEffect(() => {
    if (!showSettings) return;
    const handleClick = (e: MouseEvent) => {
      if (
        settingsBtnRef.current?.contains(e.target as Node) ||
        settingsPanelRef.current?.contains(e.target as Node)
      ) return;
      setShowSettings(false);
    };
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowSettings(false); };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [showSettings]);

  // Close question dropdown on outside click or ESC
  useEffect(() => {
    if (!openMenuId) return;
    const handleClick = () => setOpenMenuId(null);
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [openMenuId]);

  useEffect(() => {
    if (!openDropdown) return;
    const handleClick = (e: MouseEvent) => {
      if (dropdownBtnRefs.current[openDropdown]?.contains(e.target as Node)) return;
      if (dropdownPanelRef.current?.contains(e.target as Node)) return;
      setOpenDropdown(null);
    };
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpenDropdown(null); };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [openDropdown]);

  // Fixed-position style for settings panel
  const getSettingsPanelStyle = useCallback((): React.CSSProperties => {
    const rect = settingsBtnRef.current?.getBoundingClientRect();
    if (!rect) return { position: 'fixed', top: 60, right: 20, zIndex: 9999 };
    return { position: 'fixed', top: rect.bottom + 8, right: window.innerWidth - rect.right, zIndex: 9999 };
  }, []);

  // Fixed-position style for question dropdown
  const getDropdownStyle = useCallback((categoryId: string): React.CSSProperties => {
    const btn = dropdownBtnRefs.current[categoryId];
    if (!btn) return { position: 'fixed', top: 100, left: 0, zIndex: 9999 };
    const rect = btn.getBoundingClientRect();
    return { position: 'fixed', top: rect.bottom + 4, left: rect.left, zIndex: 9999 };
  }, []);

  const isAllCompanies   = selectedCompanies.length === 0;
  const companyScopeLabel = isAllCompanies ? 'All' : selectedCompanies.join(', ');
  const isLengthCapActive = mode === 'hybrid' && enableFallback && !strictGrounding;

  const toggleCompany = (company: CompanyFilter | 'All') => {
    if (company === 'All') { setSelectedCompanies([]); return; }
    setSelectedCompanies((prev) =>
      prev.includes(company) ? prev.filter((c) => c !== company) : [...prev, company]
    );
  };

  const isHistoricalQuery = (q: string) => {
    const lower = q.toLowerCase();
    return /\b(last|past|previous|recent)\s+(one|two|three|four|five|\d+)\s+quarters?\b/.test(lower) ||
      /\bhow has\b|\bwhat did\b|\bover time\b|\btrend\b/.test(lower);
  };

  const buildQuery = (query: string) => {
    const constraints: string[] = [];
    if (selectedCompanies.length > 0) constraints.push(`Focus on these companies only: ${selectedCompanies.join(', ')}.`);
    if (timeHorizon !== 'Any Time') constraints.push(`Prioritize ${timeHorizon}.`);
    const base = constraints.length > 0 ? `${query}\n\nConstraints: ${constraints.join(' ')}` : query;
    if (isHistoricalQuery(query)) return base;
    return STRUCTURED_RESPONSE_INSTRUCTION + base;
  };

  const loadHistorySession = async (session_id: string) => {
    try {
      const res = await fetch(`${API_URL}/api/chat/history/${session_id}`);
      const data = await res.json();
      const msgs: Message[] = (data.messages || []).map((m: any, i: number) => ({
        id: `${m.role}_${i}`,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        table_payload: m.table_payload ?? undefined,
        narrative_text: m.narrative_text ?? undefined,
        timestamp: new Date(),
      }));
      setMessages(msgs);
      setCurrentSessionId(session_id);
    } catch {}
  };

  const deleteHistorySession = async (session_id: string) => {
    try {
      setChatHistory((prev) => prev.filter((h) => h.session_id !== session_id));
      if (currentSessionId === session_id) {
        setMessages([]);
        setCurrentSessionId(`session_${Date.now()}`);
      }
      await fetch(`${API_URL}/api/chat/sessions/${session_id}`, { method: 'DELETE' });
      await fetch(`${API_URL}/api/chat/history/${session_id}`, { method: 'DELETE' });
    } catch {}
    setOpenMenuId(null);
  };

  const sendMessage = async (query?: string, forceMode?: SearchMode) => {
    const rawText = query || input.trim();
    if (!rawText || isLoading) return;

    const activeMode = forceMode || mode;

    const userMsg: Message = { id: `user_${Date.now()}`, role: 'user', content: rawText, timestamp: new Date() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: buildQuery(rawText),
          mode: activeMode,
          include_web: activeMode === 'web' || activeMode === 'hybrid',
          session_id: currentSessionId,
          company_filter: selectedCompanies.length > 0 ? selectedCompanies.join(',') : null,
          answer_provider: answerProvider === 'none' ? 'openai' : answerProvider,
          fallback_to_general_llm: activeMode === 'hybrid' && enableFallback && answerProvider !== 'none',
          strict_grounding: activeMode === 'hybrid' ? strictGrounding : true,
          max_response_words: isLengthCapActive && Number(maxResponseWords) > 0 ? Number(maxResponseWords) : null,
        }),
      });

      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const data = await res.json();

      const assistantMsg: Message = {
        id: `assistant_${Date.now()}`,
        role: 'assistant',
        content: data.response || data.answer || 'No response received.',
        sources: data.sources || [],
        webSources: data.web_sources || [],
        table_payload: data.table_payload ?? undefined,
        narrative_text: data.narrative_text ?? undefined,
        mode: activeMode,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Refresh history sidebar after first message
      try {
        const histRes = await fetch(`${API_URL}/api/chat/history`);
        const histData = await histRes.json();
        setChatHistory(histData.history || []);
      } catch {}
    } catch (err) {
      setMessages((prev) => [...prev, {
        id: `error_${Date.now()}`,
        role: 'assistant',
        content: `Failed to get a response. Make sure the backend is running on port 8001.\n\nError: ${err}`,
        timestamp: new Date(),
      }]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleStrategyQuestion = (question: string) => {
    const fullQuery = question + COMPARE_SUFFIX;
    setMode('web');
    setInput(fullQuery);
    setOpenDropdown(null);
    sendMessage(fullQuery, 'web');
  };

  const clearChat = () => { setMessages([]); setLastCopiedId(null); inputRef.current?.focus(); };

  const copyMessage = async (message: Message) => {
    try {
      await navigator.clipboard.writeText(message.content);
      setLastCopiedId(message.id);
      window.setTimeout(() => setLastCopiedId(null), 1500);
    } catch { setLastCopiedId(null); }
  };

  const focusInputArea = () => {
    inputDockRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    window.setTimeout(() => inputRef.current?.focus(), 120);
  };

  const fmtTime = (d: Date) =>
    d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-screen bg-gradient-to-br from-slate-100 via-slate-50 to-white dark:from-slate-950 dark:via-slate-900 dark:to-slate-950">

      {/* ── PAGE HEADER ─────────────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-slate-200/80 bg-white/90 px-6 py-3 backdrop-blur dark:border-slate-700/70 dark:bg-slate-900/80">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <h1 className="text-xl font-semibold tracking-tight text-slate-950 dark:text-slate-100">AI Chat</h1>
          <div className="flex items-center gap-2">
            {messages.length > 0 && (
              <Button variant="outline" size="sm" onClick={clearChat} className="border-slate-300 text-slate-600 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800">
                <Trash2 className="h-4 w-4" />
                Clear Chat
              </Button>
            )}
            <Button size="sm" onClick={focusInputArea} className="h-8 bg-blue-600 px-3 text-xs text-white hover:bg-blue-700">
              <ArrowUpRight className="h-3.5 w-3.5" />
              Ask Question
            </Button>
            <button
              ref={settingsBtnRef}
              onClick={() => setShowSettings((p) => !p)}
              className={`flex h-8 w-8 items-center justify-center rounded-lg border transition-colors ${
                showSettings
                  ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                  : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:border-slate-600'
              }`}
              title="Advanced settings"
            >
              <Settings className="h-4 w-4" />
            </button>

            {showSettings && typeof document !== 'undefined' && createPortal(
              <div
                ref={settingsPanelRef}
                style={getSettingsPanelStyle()}
                className="w-72 rounded-xl border border-slate-200 bg-white p-3 shadow-2xl dark:border-slate-700 dark:bg-slate-900"
              >
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Retrieval Mode</p>
                <div className="mb-3 grid grid-cols-3 gap-1">
                  {(Object.keys(modeConfig) as SearchMode[]).map((m) => {
                    const cfg = modeConfig[m];
                    const Icon = cfg.icon;
                    return (
                      <button
                        key={m}
                        onClick={() => setMode(m)}
                        className={`rounded-lg border px-2 py-1.5 text-xs font-medium transition-all ${
                          mode === m ? `${cfg.activeClass} dark:border-blue-800 dark:bg-slate-800 dark:text-slate-100` : 'border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'
                        }`}
                      >
                        <Icon className="mx-auto mb-0.5 h-3.5 w-3.5" />
                        {cfg.label}
                      </button>
                    );
                  })}
                </div>
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Model (Hybrid only)</p>
                <div className="flex gap-1">
                  {(['openai', 'claude', 'gemini'] as const).map((p) => (
                    <button
                      key={p}
                      disabled={mode !== 'hybrid'}
                      onClick={() => setAnswerProvider((prev) => prev === p ? 'none' : p)}
                      className={`flex-1 rounded-lg border px-2 py-1.5 text-xs font-medium transition-all ${
                        answerProvider === p ? 'bg-blue-600 text-white border-blue-600' : 'border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'
                      } ${mode !== 'hybrid' ? 'cursor-not-allowed opacity-40' : ''}`}
                    >
                      {p === 'openai' ? 'OpenAI' : p === 'claude' ? 'Claude' : 'Gemini'}
                    </button>
                  ))}
                </div>
              </div>,
              document.body
            )}
          </div>
        </div>
      </div>

      {/* ── MAIN LAYOUT ─────────────────────────────────────────────────── */}
      <div className="mx-auto flex min-h-0 w-full max-w-7xl flex-1 flex-col overflow-hidden px-6 py-3">

        {/* ── SECTION 1: Competitive Signals strip ─────────────────────── */}
        <div className="mb-2 shrink-0">
          {/* Header row with collapse toggle */}
          <div className="mb-1.5 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="text-[13px] font-semibold text-slate-800 dark:text-slate-100">
                Today&rsquo;s Competitive Signals
              </span>
              <Badge className="bg-blue-100 px-1.5 text-[9px] text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                Live
              </Badge>
            </div>
            <button
              type="button"
              onClick={() => setSignalsCollapsed((p) => !p)}
              className="flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[11px] text-slate-400 transition-colors hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300"
            >
              {signalsCollapsed
                ? <><ChevronDown className="h-3 w-3" /> Show</>
                : <><ChevronUp className="h-3 w-3" /> Hide</>
              }
            </button>
          </div>

          {/* Card strip — hidden when collapsed */}
          {!signalsCollapsed && (
            <div className="flex gap-2.5 overflow-x-auto pb-1.5 [&::-webkit-scrollbar]:h-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-slate-300 dark:[&::-webkit-scrollbar-thumb]:bg-slate-700">
              {SIGNAL_CARDS.map((card, idx) => (
                <CompactSignalCard key={idx} card={card} />
              ))}
            </div>
          )}
        </div>

        {/* ── SECTION 2: Category pill bar with dropdowns ───────────────── */}
        <div className="mb-2 flex shrink-0 items-center gap-2 overflow-x-auto">
          {categoriesLoading ? (
            ['AI Infrastructure Leadership', 'Capacity & Footprint', 'Financial Performance', 'Risks & External Factors'].map((label) => (
              <div
                key={label}
                className="h-8 w-40 animate-pulse rounded-full border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800"
              />
            ))
          ) : (
            strategyCategories.map((cat) => (
              <button
                key={cat.id}
                type="button"
                ref={(el) => { dropdownBtnRefs.current[cat.id] = el; }}
                onClick={() => setOpenDropdown(openDropdown === cat.id ? null : cat.id)}
                className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold whitespace-nowrap transition-all ${
                  openDropdown === cat.id
                    ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                    : 'border-slate-200 bg-white/80 text-slate-600 hover:border-slate-300 hover:bg-white dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-900'
                }`}
              >
                {cat.label}
                <ChevronDown
                  className={`h-3 w-3 transition-transform duration-150 ${openDropdown === cat.id ? 'rotate-180' : ''}`}
                />
              </button>
            ))
          )}
        </div>

        {/* ── SECTION 3: 历史侧边栏 + 聊天区域 ── */}
        <div className="flex flex-1 min-h-0 gap-3">

          {/* 左侧历史记录 */}
          {recentsOpen && (
            <div className="flex w-44 shrink-0 flex-col rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/50">
              <div className="flex items-center justify-between px-3 pt-3 pb-2">
                <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                  Recents
                </p>
                <button
                  onClick={() => setRecentsOpen(false)}
                  className="flex h-5 w-5 items-center justify-center rounded text-slate-400 hover:bg-slate-200 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-200 transition-colors"
                  title="Collapse"
                >
                  <PanelLeftClose className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto">
                {chatHistory.length === 0 ? (
                  <p className="px-3 py-2 text-[11px] text-slate-400">No recent chats</p>
                ) : (
                  chatHistory.map((h) => (
                    <div key={h.session_id} className="relative group">
                      <button
                        onClick={() => loadHistorySession(h.session_id)}
                        className={`w-full text-left px-3 py-2 text-[12px] leading-tight text-slate-600 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800 transition-colors rounded-md pr-8 ${
                          currentSessionId === h.session_id
                            ? 'bg-white dark:bg-slate-800 font-medium'
                            : ''
                        }`}
                      >
                        <p className="truncate">{h.title}</p>
                      </button>

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpenMenuId(openMenuId === h.session_id ? null : h.session_id);
                        }}
                        className="absolute right-1 top-1/2 -translate-y-1/2 flex h-5 w-5 items-center justify-center rounded text-slate-400 opacity-0 group-hover:opacity-100 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all"
                      >
                        <span className="text-slate-500 text-[10px]">•••</span>
                      </button>

                      {openMenuId === h.session_id && (
                        <div className="absolute right-0 top-8 z-50 w-28 rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteHistorySession(h.session_id);
                            }}
                            className="flex w-full items-center gap-2 px-3 py-2 text-xs text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20 rounded-lg"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
              <div className="p-3">
                <button
                  onClick={() => {
                    setMessages([]);
                    setCurrentSessionId(`session_${Date.now()}`);
                  }}
                  className="w-full rounded-lg border border-slate-200 dark:border-slate-600 px-3 py-1.5 text-[11px] text-slate-500 hover:bg-white dark:hover:bg-slate-800 transition-colors text-center"
                >
                  + New Chat
                </button>
              </div>
            </div>
          )}

          {/* 折叠后显示的展开按钮 */}
          {!recentsOpen && (
            <button
              onClick={() => setRecentsOpen(true)}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-400 hover:bg-white hover:text-slate-600 dark:border-slate-700 dark:bg-slate-900/50 dark:hover:bg-slate-800 transition-colors self-start mt-1"
              title="Show Recents"
            >
              <PanelLeftOpen className="h-3.5 w-3.5" />
            </button>
          )}

          {/* 右侧聊天区域 */}
          <Card className="flex min-h-0 flex-1 flex-col overflow-hidden border-slate-200 bg-white/95 p-0 shadow-sm dark:border-slate-700 dark:bg-slate-900/90">

          {/* Filter bar */}
          <div className="flex shrink-0 flex-wrap items-center gap-4 border-b border-slate-200 px-4 py-2 dark:border-slate-700">
            <div className="flex items-center gap-1.5">
              <Building2 className="h-3.5 w-3.5 shrink-0 text-slate-500" />
              <span className="mr-1 text-[11px] font-semibold text-slate-500 dark:text-slate-400">Company:</span>
              <button
                onClick={() => toggleCompany('All')}
                className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                  isAllCompanies
                    ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300'
                    : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-900'
                }`}
              >
                All
              </button>
              {COMPANY_FILTERS.map((company) => {
                const isSelected = selectedCompanies.includes(company);
                return (
                  <button
                    key={company}
                    onClick={() => toggleCompany(company)}
                    className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                      isSelected
                        ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300'
                        : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-900'
                    }`}
                  >
                    {company}
                  </button>
                );
              })}
            </div>

            <div className="flex items-center gap-1.5">
              <Clock3 className="h-3.5 w-3.5 shrink-0 text-slate-500" />
              <span className="mr-1 text-[11px] font-semibold text-slate-500 dark:text-slate-400">Time:</span>
              {TIME_HORIZONS.map((range) => (
                <button
                  key={range}
                  onClick={() => setTimeHorizon(range)}
                  className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                    timeHorizon === range
                      ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300'
                      : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-900'
                  }`}
                >
                  {range}
                </button>
              ))}
            </div>
          </div>

          {/* ── Messages area — takes all remaining Card height ─────────── */}
          <div
            ref={messagesAreaRef}
            className="flex-1 overflow-y-auto border-t border-slate-100 px-5 py-4 dark:border-slate-800"
          >
            {messages.length === 0 ? (
              /* Empty state */
              <div className="flex h-full min-h-[260px] flex-col items-center justify-center text-center">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-2xl bg-blue-100 dark:bg-blue-950/50">
                  <Bot className="h-5 w-5 text-blue-600" />
                </div>
                <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Research Workspace</h2>
                <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                  Ask a question or click a topic above
                </p>
                <div className="mt-3 flex flex-wrap items-center justify-center gap-1.5">
                  <Badge variant="outline" className="border-slate-200 bg-slate-50 text-[11px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                    Active Mode: {modeConfig[mode].label}
                  </Badge>
                  <Badge variant="outline" className="border-slate-200 bg-slate-50 text-[11px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                    Company: {companyScopeLabel}
                  </Badge>
                  <Badge variant="outline" className="border-slate-200 bg-slate-50 text-[11px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                    Time: {timeHorizon}
                  </Badge>
                </div>
              </div>
            ) : (
              /* Message list */
              <div className="mx-auto max-w-4xl space-y-5">
                {messages.map((msg) => (
                  <div key={msg.id} className={`flex gap-2.5 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                    {msg.role === 'assistant' && (
                      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-blue-100 dark:bg-blue-950/50">
                        <Bot className="h-4 w-4 text-blue-600" />
                      </div>
                    )}

                    <div className={`min-w-0 ${msg.role === 'user' ? 'max-w-[70%]' : 'max-w-[85%]'}`}>
                      <div
                        className={`rounded-xl px-4 py-2.5 ${
                          msg.role === 'user'
                            ? 'bg-blue-600 text-white'
                            : 'border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900'
                        }`}
                      >
                        {msg.role === 'assistant' ? (
                          msg.table_payload ? (
                            <TableAnswer
                              narrativeText={msg.narrative_text}
                              tablePayload={msg.table_payload}
                            />
                          ) : (
                            <div className="prose prose-sm max-w-none prose-slate dark:prose-invert">
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                            </div>
                          )
                        ) : (
                          <p className="text-sm leading-5">{msg.content}</p>
                        )}
                      </div>

                      {/* Timestamp + source badges + actions */}
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        <span className="text-[10px] text-slate-400 dark:text-slate-500">
                          {fmtTime(msg.timestamp)}
                        </span>
                        {msg.webSources && msg.webSources.length > 0 && msg.webSources.map((ws) => (
                          <a
                            key={ws.index}
                            href={ws.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-normal text-slate-600 hover:border-slate-400 hover:bg-slate-50 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-slate-500 dark:hover:text-slate-100"
                          >
                            <ArrowUpRight className="h-2.5 w-2.5 shrink-0" />
                            <span className="max-w-[140px] truncate">{ws.title || ws.url}</span>
                          </a>
                        ))}
                        {msg.mode && (
                          <Badge className={`border text-[10px] ${modeConfig[msg.mode].color}`}>
                            {modeConfig[msg.mode].label}
                          </Badge>
                        )}
                        {msg.role === 'assistant' && (
                          <>
                            <Button type="button" variant="ghost" size="xs" onClick={() => copyMessage(msg)} className="h-5 px-1.5 text-[10px] text-slate-400 dark:text-slate-500">
                              <Copy className="h-2.5 w-2.5" />
                              {lastCopiedId === msg.id ? 'Copied' : 'Copy'}
                            </Button>
                            <Button type="button" variant="ghost" size="xs" onClick={() => setInput(msg.content)} className="h-5 px-1.5 text-[10px] text-slate-400 dark:text-slate-500">
                              Reuse
                            </Button>
                          </>
                        )}
                        {msg.role === 'user' && (
                          <Button type="button" variant="ghost" size="xs" onClick={() => { setInput(msg.content); inputRef.current?.focus(); }} className="h-5 px-1.5 text-[10px] text-slate-400 dark:text-slate-500">
                            <RotateCcw className="h-2.5 w-2.5" />
                            Reuse
                          </Button>
                        )}
                      </div>
                    </div>

                    {msg.role === 'user' && (
                      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-blue-100 dark:bg-blue-900/40">
                        <User className="h-4 w-4 text-blue-600 dark:text-blue-300" />
                      </div>
                    )}
                  </div>
                ))}

                {isLoading && (
                  <div className="flex gap-2.5">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-blue-100">
                      <Bot className="h-4 w-4 text-blue-600" />
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 dark:border-slate-700 dark:bg-slate-900">
                      <div className="flex items-center gap-2.5">
                        <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                        <p className="text-sm text-slate-500 dark:text-slate-300">Searching sources and drafting response...</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ── Input dock ───────────────────────────────────────────────── */}
          <div
            ref={inputDockRef}
            className="shrink-0 border-t border-slate-200 bg-white px-5 py-3 dark:border-slate-700 dark:bg-slate-900"
          >
            <form
              onSubmit={(e) => { e.preventDefault(); sendMessage(); }}
              className="mx-auto max-w-4xl"
            >
              <div className="flex gap-2.5">
                <Input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask about CapEx, AI strategy, hyperscaler exposure, earnings trends..."
                  disabled={isLoading}
                  className="h-10 flex-1 rounded-lg border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-400"
                  autoFocus
                />
                <Button
                  type="submit"
                  disabled={isLoading || !input.trim()}
                  className="h-10 bg-blue-600 px-4 text-white hover:bg-blue-700"
                >
                  {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  <span className="hidden sm:inline ml-1">Send</span>
                </Button>
              </div>
            </form>
            <div className="mx-auto mt-1.5 flex max-w-4xl items-center justify-between gap-2 text-[11px] text-slate-400 dark:text-slate-500">
              <span>Using SEC docs · Powered by Claude + ChromaDB</span>
              <span>Scope: {companyScopeLabel} · {timeHorizon}</span>
            </div>
          </div>
        </Card>
        </div>{/* end sidebar+chat flex row */}
      </div>

      {/* ── Question dropdown portal ─────────────────────────────────────── */}
      {openDropdown && typeof document !== 'undefined' && createPortal(
        <div
          ref={dropdownPanelRef}
          style={getDropdownStyle(openDropdown)}
          className="w-72 rounded-xl border border-slate-200 bg-white py-1.5 shadow-xl dark:border-slate-700 dark:bg-slate-900"
        >
          {strategyCategories.find((c) => c.id === openDropdown)?.questions.map((q, i) => (
            <button
              key={i}
              type="button"
              onClick={() => handleStrategyQuestion(q)}
              className="block w-full px-4 py-2 text-left text-xs text-slate-700 transition-colors hover:bg-blue-50 hover:text-blue-700 dark:text-slate-300 dark:hover:bg-blue-950/30 dark:hover:text-blue-300"
            >
              {q}
            </button>
          ))}
        </div>,
        document.body
      )}
    </div>
  );
}
