'use client';

import { useState, useRef, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
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
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  Plus,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { createCustomQuestion, deleteCustomQuestion, fetchCustomQuestions, requestChat } from './api';
import { TableAnswer, type TablePayload } from './TableAnswer';

type SearchMode = 'rag' | 'web' | 'hybrid';
type CompanyFilter = 'Flex' | 'Jabil' | 'Celestica' | 'Benchmark' | 'Sanmina' | 'Plexus';
type AnswerProvider = 'openai' | 'claude' | 'none';
type TimeFocus = 'any' | 'fy2026' | 'fy2025' | 'last12m';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  narrative_text?: string;
  table_payload?: TablePayload;
  sources?: Source[];
  webSources?: WebSource[];
  timestamp: Date;
}

interface Source {
  company?: string;
  source?: string;
  filing_type?: string;
  fiscal_year?: string;
  similarity?: number;
}

interface WebSource {
  index: number;
  title: string;
  url: string;
}

interface CustomPresetQuestion {
  id: string;
  label: string;
  query: string;
}

function isCustomPresetQuestion(value: unknown): value is CustomPresetQuestion {
  if (!value || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return typeof v.id === 'string' && typeof v.label === 'string' && typeof v.query === 'string';
}

type QuestionSecondary = {
  id: string;
  label: string;
  prompts: { label: string; query: string }[];
};

type QuestionPrimary = {
  id: string;
  label: string;
  children: QuestionSecondary[];
};

const QUESTION_BANK: QuestionPrimary[] = [
  {
    id: 'market-demand',
    label: 'Market Demand',
    children: [
      {
        id: 'data-center-infra',
        label: 'Data Center Infrastructure',
        prompts: [
          {
            label: 'AI/DC Ramp',
            query: 'Analysts frequently ask about the ramp of new AI-driven data center infrastructure deployments. Analyze demand ramp signals and expected acceleration across EMS companies.',
          },
          {
            label: 'Deployment Pipeline',
            query: 'Analyze the deployment pipeline and expected production ramp for new data center infrastructure projects, including near-term bottlenecks and execution dependencies.',
          },
        ],
      },
      {
        id: 'hyperscale-customers',
        label: 'Hyperscale Customers',
        prompts: [
          {
            label: 'Hyperscale Ramps',
            query: 'Analyze the scale and profitability of Jabil/Flex hyperscale customer ramps, and assess whether recent wins represent a structural market-share shift or temporary execution strength.',
          },
        ],
      },
      {
        id: 'geo-nearshoring',
        label: 'Geographic & Nearshoring',
        prompts: [
          {
            label: 'Geo/Nearshoring',
            query: 'Given cautious sentiment in Europe, analyze geographic demand trends and how Jabil/Flex footprints in India and Mexico are being utilized for regionalization and nearshoring.',
          },
        ],
      },
    ],
  },
  {
    id: 'strategic-positioning',
    label: 'Strategic Positioning',
    children: [
      {
        id: 'competitive-differentiation',
        label: 'Competitive Differentiation',
        prompts: [
          {
            label: 'Compare strategic positioning',
            query: 'Analyze where Flex, Jabil, and Celestica differ most in strategic positioning for data center infrastructure manufacturing.',
          },
        ],
      },
    ],
  },
  {
    id: 'financial-performance',
    label: 'Financial Performance',
    children: [
      {
        id: 'margin-sustainability',
        label: 'Margin Sustainability',
        prompts: [
          {
            label: 'Margin Quality',
            query: 'Analyze how Flex/Jabil achieved sequential margin increases, and determine whether improvement is primarily product-mix shift into higher-value segments (e.g., Health and Industrial) or temporary tailwinds.',
          },
        ],
      },
    ],
  },
  {
    id: 'external-risks',
    label: 'External Risks',
    children: [
      {
        id: 'geopolitics',
        label: 'Geopolitics',
        prompts: [
          {
            label: 'Tariff Impact',
            query: 'Analyze geopolitical and tariff impacts and management response, including expected effects on cash generation and reported financial results.',
          },
        ],
      },
    ],
  },
];

const QUICK_QUESTIONS = [
  {
    label: 'AI/DC Ramp',
    query: 'Analysts frequently ask about the ramp of new AI-driven data center infrastructure deployments. Analyze demand ramp signals and expected acceleration across EMS companies.',
  },
  {
    label: 'Margin Quality',
    query: 'Analyze how Flex/Jabil achieved sequential margin increases, and determine whether improvement is primarily product-mix shift into higher-value segments (e.g., Health and Industrial) or temporary tailwinds.',
  },
  {
    label: 'Hyperscale Ramps',
    query: 'Analyze the scale and profitability of Jabil/Flex hyperscale customer ramps, and assess whether recent wins represent a structural market-share shift or temporary execution strength.',
  },
  {
    label: 'Geo/Nearshoring',
    query: 'Given cautious sentiment in Europe, analyze geographic demand trends and how Jabil/Flex footprints in India and Mexico are being utilized for regionalization and nearshoring.',
  },
  {
    label: 'Tariff Impact',
    query: 'Analyze geopolitical and tariff impacts and management response, including expected effects on cash generation and reported financial results.',
  },
  {
    label: 'AI/DC Revenue Mix',
    query: 'What is the AI/Data Center revenue mix for each company, and how has it changed YoY?',
  },
  {
    label: 'CapEx Guidance',
    query: 'Compare CapEx guidance across all 6 EMS companies for the current fiscal year.',
  },
  {
    label: 'Liquid Cooling',
    query: 'What liquid cooling and power management capabilities are each company developing?',
  },
  {
    label: 'Hyperscaler Demand',
    query: 'Which hyperscaler customers are driving AI server demand for EMS companies?',
  },
  {
    label: 'Gross Margin Trend',
    query: 'What are the gross margin trends for AI/DC vs traditional segments?',
  },
  {
    label: 'Capacity Expansion',
    query: 'What manufacturing capacity expansions are planned for AI server production?',
  },
];

const COMPANY_FILTERS: CompanyFilter[] = ['Flex', 'Jabil', 'Celestica', 'Benchmark', 'Sanmina', 'Plexus'];

const modeConfig = {
  rag: {
    icon: Database,
    label: 'Filing Search',
    color: 'bg-blue-100 text-blue-700 border-blue-200',
    activeClass: 'border-blue-300 bg-blue-50 text-blue-900 shadow-sm',
    desc: 'SEC docs',
  },
  web: {
    icon: Globe,
    label: 'Web Search',
    color: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    activeClass: 'border-emerald-300 bg-emerald-50 text-emerald-900 shadow-sm',
    desc: 'Public web',
  },
  hybrid: {
    icon: Sparkles,
    label: 'Hybrid Search',
    color: 'bg-cyan-100 text-cyan-700 border-cyan-200',
    activeClass: 'border-cyan-300 bg-cyan-50 text-cyan-900 shadow-sm',
    desc: 'Docs + web',
  },
} as const;

export default function ChatPageFeature() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [mode, setMode] = useState<SearchMode>('rag');
  const [selectedCompanies, setSelectedCompanies] = useState<CompanyFilter[]>([]);
  const [timeFocus, setTimeFocus] = useState<TimeFocus>('any');
  const [answerProvider, setAnswerProvider] = useState<AnswerProvider>('none');
  const [openPrimary, setOpenPrimary] = useState<Record<string, boolean>>(
    () =>
      QUESTION_BANK.reduce<Record<string, boolean>>((acc, item) => {
        acc[item.id] = false;
        return acc;
      }, {})
  );
  const [openSecondary, setOpenSecondary] = useState<Record<string, boolean>>(
    () =>
      QUESTION_BANK.reduce<Record<string, boolean>>((acc, item) => {
        item.children.forEach((child) => {
          acc[child.id] = false;
        });
        return acc;
      }, {})
  );
  const [lastCopiedId, setLastCopiedId] = useState<string | null>(null);
  const [customQuestions, setCustomQuestions] = useState<CustomPresetQuestion[]>([]);
  const [openCustomGroup, setOpenCustomGroup] = useState(true);
  const [showAddPresetForm, setShowAddPresetForm] = useState(false);
  const [newPresetLabel, setNewPresetLabel] = useState('');
  const [newPresetQuery, setNewPresetQuery] = useState('');
  const [sessionId] = useState(() => `session_${Date.now()}`);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputDockRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    const loadCustomQuestions = async () => {
      try {
        const data = await fetchCustomQuestions();
        const questions = Array.isArray(data?.questions) ? data.questions : [];
        setCustomQuestions(
          questions.filter(isCustomPresetQuestion)
        );
      } catch {
        // Keep empty list on failure.
      }
    };
    loadCustomQuestions();
  }, []);

  const togglePrimary = (id: string) => {
    setOpenPrimary((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleSecondary = (id: string) => {
    setOpenSecondary((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const focusInputArea = () => {
    inputDockRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    window.setTimeout(() => inputRef.current?.focus(), 120);
  };

  const fillInputFromPreset = (query: string) => {
    setInput(query);
    focusInputArea();
  };

  const cancelNewPreset = () => {
    setShowAddPresetForm(false);
    setNewPresetLabel('');
    setNewPresetQuery('');
  };

  const saveNewPreset = async () => {
    const label = newPresetLabel.trim();
    const query = newPresetQuery.trim();
    if (!label || !query) return;

    try {
      const data = await createCustomQuestion(label, query);
      const item = data?.question;
      if (item?.id && item?.label && item?.query) {
        setCustomQuestions((prev) => [item, ...prev]);
      }
      cancelNewPreset();
    } catch {
      // Ignore network errors; preserve form for retry.
    }
  };

  const deleteCustomPreset = async (id: string) => {
    try {
      await deleteCustomQuestion(id);
      setCustomQuestions((prev) => prev.filter((item) => item.id !== id));
    } catch {
      // Ignore network errors.
    }
  };

  const toggleAnswerProvider = (provider: Exclude<AnswerProvider, 'none'>) => {
    setAnswerProvider((prev) => (prev === provider ? 'none' : provider));
  };

  const isAllCompanies = selectedCompanies.length === 0;
  const companyScopeLabel = isAllCompanies ? 'All' : selectedCompanies.join(', ');
  const timeFocusLabel =
    timeFocus === 'fy2026' ? 'FY2026' : timeFocus === 'fy2025' ? 'FY2025' : timeFocus === 'last12m' ? 'Last 12 Months' : 'Any Time';

  const toggleCompany = (company: CompanyFilter | 'All') => {
    if (company === 'All') {
      setSelectedCompanies([]);
      return;
    }

    setSelectedCompanies((prev) => {
      if (prev.includes(company)) {
        return prev.filter((item) => item !== company);
      }
      return [...prev, company];
    });
  };

  const buildQuery = (query: string) => {
    const constraints: string[] = [];

    if (selectedCompanies.length > 0) {
      constraints.push(`Focus on these companies only: ${selectedCompanies.join(', ')}.`);
    }

    if (timeFocus === 'fy2026') {
      constraints.push('Prioritize FY2026.');
    } else if (timeFocus === 'fy2025') {
      constraints.push('Prioritize FY2025.');
    } else if (timeFocus === 'last12m') {
      constraints.push('Focus on the last 12 months.');
    }

    return constraints.length > 0 ? `${query}\n\nConstraints: ${constraints.join(' ')}` : query;
  };

  const sendMessage = async (query?: string) => {
    const rawText = query || input.trim();
    if (!rawText || isLoading) return;

    const userMsg: Message = {
      id: `user_${Date.now()}`,
      role: 'user',
      content: rawText,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const data = await requestChat({
        query: buildQuery(rawText),
        mode,
        include_web: mode === 'web' || mode === 'hybrid',
        session_id: sessionId,
        company_filter: selectedCompanies.length > 0 ? selectedCompanies.join(',') : null,
        answer_provider: answerProvider === 'none' ? 'openai' : answerProvider,
        fallback_to_general_llm: mode === 'hybrid' && answerProvider !== 'none',
        strict_grounding: true,
        max_response_words: null,
      });

      const assistantMsg: Message = {
        id: `assistant_${Date.now()}`,
        role: 'assistant',
        content: data.response || data.answer || 'No response received.',
        narrative_text: data.narrative_text ?? undefined,
        table_payload: data.table_payload ?? undefined,
        sources: data.sources || [],
        webSources: data.web_sources || [],
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg: Message = {
        id: `error_${Date.now()}`,
        role: 'assistant',
        content: `Failed to get a response. Make sure the backend is running on port 8001.\n\nError: ${err}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const clearChat = () => {
    setMessages([]);
    setLastCopiedId(null);
    inputRef.current?.focus();
  };

  const copyMessage = async (message: Message) => {
    try {
      await navigator.clipboard.writeText(message.content);
      setLastCopiedId(message.id);
      window.setTimeout(() => setLastCopiedId(null), 1500);
    } catch {
      setLastCopiedId(null);
    }
  };

  const mobilePrompts = QUESTION_BANK.flatMap((item) =>
    item.children.flatMap((sub) => sub.prompts.map((prompt) => ({ category: `${item.label} · ${sub.label}`, label: prompt.label, query: prompt.query })))
  ).slice(0, 8);

  return (
    <div className="flex h-full flex-col bg-gradient-to-br from-slate-100 via-slate-50 to-white dark:from-slate-950 dark:via-slate-900 dark:to-slate-950">
      <div className="border-b border-slate-200/80 bg-white/90 px-6 py-2.5 backdrop-blur dark:border-slate-700/70 dark:bg-slate-900/80">
        <div className="mx-auto max-w-7xl">
          {/* Single title row */}
          <div className="flex items-center justify-between gap-3">
            <h1 className="text-xl font-semibold tracking-tight text-slate-950 dark:text-slate-100">Research Chat</h1>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowSettings((prev) => !prev)}
                title="Settings"
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors ${
                  showSettings
                    ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-slate-600'
                }`}
              >
                <Settings className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Settings</span>
                {/* Active indicators */}
                {(mode !== 'rag' || !isAllCompanies || timeFocus !== 'any') && (
                  <span className="ml-0.5 h-1.5 w-1.5 rounded-full bg-blue-500" />
                )}
              </button>
              {messages.length > 0 && (
                <Button variant="outline" size="sm" onClick={clearChat} className="border-slate-300 text-slate-600 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800">
                  <Trash2 className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Clear</span>
                </Button>
              )}
              <Button
                size="sm"
                onClick={focusInputArea}
                className="h-8 bg-blue-600 px-3 text-xs text-white hover:bg-blue-700"
              >
                <ArrowUpRight className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Ask</span>
              </Button>
            </div>
          </div>

          {/* Collapsible settings panel */}
          {showSettings && (
            <div className="mt-2.5 flex flex-col gap-2">
              {/* Retrieval mode selector in settings */}
              <Card className="gap-2 border-slate-200 bg-white/95 p-2.5 shadow-sm dark:border-slate-700 dark:bg-slate-900/90">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
                  <Database className="h-4 w-4 text-blue-600" />
                  Retrieval Mode
                </div>
                <div className="grid gap-1.5 md:grid-cols-3">
                  {(Object.keys(modeConfig) as SearchMode[]).map((m) => {
                    const config = modeConfig[m];
                    const Icon = config.icon;
                    return (
                      <button
                        key={m}
                        title={config.desc}
                        onClick={() => setMode(m)}
                        className={`rounded-xl border px-2.5 py-1.5 text-left transition-all ${
                          mode === m
                            ? `${config.activeClass} dark:border-blue-800 dark:bg-slate-800 dark:text-slate-100`
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-800'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <Icon className="h-4 w-4" />
                          <span className="text-sm font-semibold leading-5">{config.label}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </Card>

              {/* Model selector in settings */}
              <div className="flex flex-wrap items-center gap-3">
                <div className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 p-1 text-xs dark:border-slate-700 dark:bg-slate-800">
                  <button
                    type="button"
                    onClick={() => toggleAnswerProvider('openai')}
                    className={`rounded-full px-2.5 py-1 transition ${
                      answerProvider === 'openai'
                        ? 'bg-blue-600 text-white'
                        : 'text-slate-600 hover:bg-white dark:text-slate-300 dark:hover:bg-slate-700'
                    }`}
                  >
                    OpenAI
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleAnswerProvider('claude')}
                    className={`rounded-full px-2.5 py-1 transition ${
                      answerProvider === 'claude'
                        ? 'bg-blue-600 text-white'
                        : 'text-slate-600 hover:bg-white dark:text-slate-300 dark:hover:bg-slate-700'
                    }`}
                  >
                    Claude
                  </button>
                </div>
              </div>

              {/* Company Filter + Time Focus */}
              <div className="grid gap-2 lg:grid-cols-2">
                <Card className="gap-2 border-slate-200 bg-white/95 p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900/90">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
                    <Building2 className="h-4 w-4 text-slate-600" />
                    Company Filter
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <button
                      onClick={() => toggleCompany('All')}
                      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
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
                          className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
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
                </Card>

                <Card className="gap-2 border-slate-200 bg-white/95 p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900/90">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
                    Time Focus
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <button
                      onClick={() => setTimeFocus('any')}
                      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                        timeFocus === 'any'
                          ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300'
                          : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-900'
                      }`}
                    >
                      Any Time
                    </button>
                    <button
                      onClick={() => setTimeFocus('fy2026')}
                      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                        timeFocus === 'fy2026'
                          ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300'
                          : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-900'
                      }`}
                    >
                      FY2026
                    </button>
                    <button
                      onClick={() => setTimeFocus('fy2025')}
                      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                        timeFocus === 'fy2025'
                          ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300'
                          : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-900'
                      }`}
                    >
                      FY2025
                    </button>
                    <button
                      onClick={() => setTimeFocus('last12m')}
                      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                        timeFocus === 'last12m'
                          ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300'
                          : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-900'
                      }`}
                    >
                      Last 12 Months
                    </button>
                  </div>
                </Card>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-hidden px-6 py-3">
        <div className={`mx-auto h-full grid min-h-0 gap-4 ${sidebarOpen ? 'xl:grid-cols-[350px_minmax(0,1fr)]' : 'xl:grid-cols-[minmax(0,1fr)]'}`}>
          {/* Preset Question Library - collapsible */}
          {sidebarOpen && (
          <Card className="hidden min-h-0 h-full overflow-hidden border-slate-200 bg-white/95 p-0 shadow-sm xl:flex xl:flex-col dark:border-slate-700 dark:bg-slate-900/90">
            <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-700 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Preset Question Library</h2>
                <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Click any question to send directly.</p>
              </div>
              <button
                onClick={() => setSidebarOpen(false)}
                title="Collapse library"
                className="flex items-center justify-center rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              >
                <PanelLeftClose className="h-4 w-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
              <div className="space-y-2">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-900/70">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">Top Analyst Questions</div>
                    <button
                      onClick={() => setShowAddPresetForm((prev) => !prev)}
                      className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-600 hover:border-slate-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-slate-500"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      Add Preset Question
                    </button>
                  </div>
                  {showAddPresetForm && (
                    <div className="mb-2 rounded-lg border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-800">
                      <div className="space-y-2">
                        <div>
                          <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                            Label
                          </label>
                          <Input
                            value={newPresetLabel}
                            onChange={(e) => setNewPresetLabel(e.target.value)}
                            placeholder="e.g. AI Supply Chain Risk"
                            className="h-8 text-xs"
                          />
                        </div>
                        <div>
                          <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                            Full Question
                          </label>
                          <textarea
                            value={newPresetQuery}
                            onChange={(e) => setNewPresetQuery(e.target.value)}
                            placeholder="Type the complete preset question..."
                            rows={3}
                            className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-300 focus:ring-1 focus:ring-blue-200 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                          />
                        </div>
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={cancelNewPreset}
                            className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:border-slate-400 dark:border-slate-600 dark:text-slate-200 dark:hover:border-slate-500"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={saveNewPreset}
                            disabled={!newPresetLabel.trim() || !newPresetQuery.trim()}
                            className="rounded-md bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Save
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                  <div className="space-y-1">
                    {QUICK_QUESTIONS.map((question, idx) => (
                      <button
                        key={`${question.label}-${idx}`}
                        onClick={() => sendMessage(question.query)}
                        className="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-slate-700 transition hover:bg-white dark:text-slate-200 dark:hover:bg-slate-800"
                      >
                        <span className="mt-1 h-2 w-2 shrink-0 rounded-full border border-slate-400 dark:border-slate-500" />
                        <span className="line-clamp-2">{question.label}</span>
                      </button>
                    ))}
                  </div>

                  <div className="mt-2 rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
                    <button
                      onClick={() => setOpenCustomGroup((prev) => !prev)}
                      className="flex w-full items-center justify-between px-3 py-1.5 text-left"
                    >
                      <span className="text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
                        Custom Added Questions
                      </span>
                      {openCustomGroup ? (
                        <ChevronDown className="h-4 w-4 text-slate-400" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-slate-400" />
                      )}
                    </button>
                    {openCustomGroup && (
                      <div className="border-t border-slate-200 px-2 py-1.5 dark:border-slate-700">
                        {customQuestions.length === 0 ? (
                          <p className="px-1 py-1 text-xs text-slate-500 dark:text-slate-400">No custom questions yet.</p>
                        ) : (
                          <div className="space-y-1">
                            {customQuestions.map((question) => (
                              <div
                                key={question.id}
                                className="flex w-full items-start gap-2 rounded-md px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
                              >
                                <button
                                  onClick={() => fillInputFromPreset(question.query)}
                                  className="flex min-w-0 flex-1 items-start gap-2 text-left"
                                >
                                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400 dark:bg-blue-500" />
                                  <span className="line-clamp-2">{question.label}</span>
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    deleteCustomPreset(question.id);
                                  }}
                                  aria-label={`Delete ${question.label}`}
                                  title="Delete"
                                  className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-[11px] text-slate-400 hover:bg-slate-200 hover:text-slate-700 dark:text-slate-500 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                                >
                                  ×
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                <div className="rounded-xl border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-900/70">
                  <div className="mb-2 px-1 text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Research Topics</div>
                  <div className="space-y-1">
                    {QUESTION_BANK.map((item) => {
                      const isOpen = openPrimary[item.id];
                      return (
                        <div key={item.id} className="rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
                          <button
                            onClick={() => togglePrimary(item.id)}
                            className="flex w-full items-center justify-between px-3 py-1.5 text-left"
                          >
                            <span className={`text-sm font-semibold ${isOpen ? 'text-blue-700 dark:text-blue-300' : 'text-slate-700 dark:text-slate-200'}`}>
                              {item.label}
                            </span>
                            {isOpen ? (
                              <ChevronDown className="h-4 w-4 text-slate-400" />
                            ) : (
                              <ChevronRight className="h-4 w-4 text-slate-400" />
                            )}
                          </button>

                          {isOpen && (
                            <div className="border-t border-slate-200 px-2 py-2 dark:border-slate-700">
                              <div className="space-y-1">
                                {item.children.map((sub) => {
                                  const isSecondaryOpen = openSecondary[sub.id];
                                  return (
                                    <div key={sub.id} className="rounded-md">
                                      <button
                                        onClick={() => toggleSecondary(sub.id)}
                                        className={`w-full rounded-md px-2 py-1 text-left text-sm ${
                                          isSecondaryOpen
                                            ? 'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                                            : 'text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800'
                                        }`}
                                      >
                                        {sub.label}
                                      </button>

                                      {isSecondaryOpen && (
                                        <div className="mt-1 space-y-1 pl-3">
                                          {sub.prompts.map((question, qIdx) => (
                                            <button
                                              key={`${sub.id}-${qIdx}`}
                                              onClick={() => sendMessage(question.query)}
                                              className="flex w-full items-start gap-2 rounded-md px-2 py-1 text-left text-xs text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800"
                                            >
                                              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400 dark:bg-blue-500" />
                                              <span>{question.label}</span>
                                            </button>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          </Card>
          )}

          <Card className="min-h-0 h-full overflow-hidden border-slate-200 bg-white/95 p-0 shadow-sm flex flex-col dark:border-slate-700 dark:bg-slate-900/90">
            {/* Re-open sidebar button (xl only, when sidebar is hidden) */}
            {!sidebarOpen && (
              <div className="hidden xl:flex border-b border-slate-200 px-4 py-2 dark:border-slate-700">
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
                >
                  <PanelLeftOpen className="h-3.5 w-3.5" />
                  Show Question Library
                </button>
              </div>
            )}
            <ScrollArea className="min-h-0 flex-1 px-6 py-4">
              {messages.length === 0 ? (
                <div className="flex min-h-[520px] flex-col items-center justify-center text-center">
                  <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-100 dark:bg-blue-950/50">
                    <Bot className="h-8 w-8 text-blue-600" />
                  </div>
                  <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">Research Workspace</h2>

                  <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
                    <Badge variant="outline" className="border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                      Company: {companyScopeLabel}
                    </Badge>
                    <Badge variant="outline" className="border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                      Time: {timeFocusLabel}
                    </Badge>
                  </div>

                  <div className="mt-8 grid w-full max-w-4xl grid-cols-1 gap-3 md:grid-cols-2 xl:hidden">
                    {mobilePrompts.map((item, i) => (
                      <button
                        key={i}
                        onClick={() => sendMessage(item.query)}
                        className="text-left rounded-2xl border border-slate-200 bg-white px-4 py-4 transition-all hover:border-blue-200 hover:bg-blue-50/60 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-blue-800 dark:hover:bg-slate-800"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                            {item.category}
                          </span>
                          <ArrowUpRight className="h-4 w-4 text-slate-300" />
                        </div>
                        <p className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-200">{item.label}</p>
                      </button>
                    ))}
                  </div>

                  <p className="mt-5 text-xs text-slate-400 dark:text-slate-500 xl:hidden">
                    Use structured prompts or type your own analyst question.
                  </p>
                </div>
              ) : (
                <div className="mx-auto max-w-4xl space-y-6">
                  {messages.map((msg) => (
                    <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                      {msg.role === 'assistant' && (
                        <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-100">
                          <Bot className="h-4 w-4 text-blue-600" />
                        </div>
                      )}

                      <div className={`max-w-[84%] ${msg.role === 'user' ? 'order-first' : ''}`}>
                        <div
                          className={`rounded-3xl px-5 py-4 ${
                            msg.role === 'user'
                              ? 'bg-slate-900 text-white'
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
                            <p className="text-sm leading-6">{msg.content}</p>
                          )}
                        </div>

                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          {msg.sources && msg.sources.length > 0 && (
                            <>
                              {msg.sources.slice(0, 4).map((src, i) => (
                                <Badge key={i} variant="outline" className="text-xs font-normal">
                                  {src.company} · {src.filing_type} · {src.fiscal_year}
                                </Badge>
                              ))}
                            </>
                          )}

                          {msg.webSources && msg.webSources.length > 0 && (
                            <div className="mt-1 w-full">
                              <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">Web Sources</p>
                              <div className="flex flex-wrap gap-1.5">
                                {msg.webSources.map((ws) => (
                                  <a
                                    key={ws.index}
                                    href={ws.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700 hover:bg-emerald-100 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400 dark:hover:bg-emerald-900/50"
                                  >
                                    <span className="font-semibold">Web {ws.index}</span>
                                    <span className="max-w-[200px] truncate">{ws.title}</span>
                                  </a>
                                ))}
                              </div>
                            </div>
                          )}

                          {msg.role === 'assistant' && (
                            <>
                              <Button
                                type="button"
                                variant="ghost"
                                size="xs"
                                onClick={() => copyMessage(msg)}
                                className="text-slate-500 dark:text-slate-300"
                              >
                                <Copy className="w-3 h-3" />
                                {lastCopiedId === msg.id ? 'Copied' : 'Copy'}
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="xs"
                                onClick={() => setInput(msg.content)}
                                className="text-slate-500 dark:text-slate-300"
                              >
                                Reuse Answer
                              </Button>
                            </>
                          )}

                          {msg.role === 'user' && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="xs"
                              onClick={() => {
                                setInput(msg.content);
                                inputRef.current?.focus();
                              }}
                              className="text-slate-500 dark:text-slate-300"
                            >
                              <RotateCcw className="w-3 h-3" />
                              Reuse Question
                            </Button>
                          )}
                        </div>
                      </div>

                      {msg.role === 'user' && (
                        <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-200">
                          <User className="h-4 w-4 text-slate-600" />
                        </div>
                      )}
                    </div>
                  ))}

                  {isLoading && (
                    <div className="flex gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-100">
                        <Bot className="h-4 w-4 text-blue-600" />
                      </div>
                      <div className="rounded-3xl border border-slate-200 bg-white px-5 py-4 dark:border-slate-700 dark:bg-slate-900">
                        <div className="flex items-center gap-3">
                          <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
                          <p className="text-sm text-slate-500 dark:text-slate-300">Searching sources and drafting response...</p>
                        </div>
                      </div>
                    </div>
                  )}
                  <div ref={scrollRef} />
                </div>
              )}
            </ScrollArea>

            <div ref={inputDockRef} className="border-t border-slate-200 bg-white px-6 py-4 dark:border-slate-700 dark:bg-slate-900">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  sendMessage();
                }}
                className="mx-auto max-w-4xl"
              >
                <div className="flex gap-3">
                  <Input
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask about CapEx, data center infrastructure, customer exposure, or earnings commentary..."
                    disabled={isLoading}
                    className="h-12 flex-1 border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-400"
                    autoFocus
                  />
                  <Button
                    type="submit"
                    disabled={isLoading || !input.trim()}
                    className="h-12 bg-blue-600 px-5 text-white hover:bg-blue-700"
                  >
                    {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    <span className="hidden sm:inline">Send</span>
                  </Button>
                </div>
              </form>
              <div className="mx-auto mt-3 flex max-w-4xl flex-wrap items-center justify-between gap-2 text-xs text-slate-400 dark:text-slate-500">
                <p>
                  Using SEC docs · Powered by Claude + ChromaDB
                </p>
                <p>
                  Scope: {companyScopeLabel} · Time: {timeFocusLabel}
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
