'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  MessageSquare,
  Building2,
  TrendingUp,
  Database,
  ChevronRight,
  Globe,
  Newspaper,
  LineChart,
  CalendarDays,
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  Moon,
} from 'lucide-react';
import { EMSIntelligenceLogo } from '@/components/EMSIntelligenceLogo';
import { cn } from '@/lib/utils';

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
};

type NavGroup = {
  id: string;
  label: string;
  items: NavItem[];
};

const navGroups: NavGroup[] = [
  {
    id: 'news',
    label: 'News',
    items: [
      { href: '/news', label: 'News', icon: Newspaper },
    ],
  },
  {
    id: 'analyst-view',
    label: 'Analyst View',
    items: [
      { href: '/analyst-view', label: 'Analyst View', icon: LineChart },
    ],
  },
  {
    id: 'ai-research-chat',
    label: 'AI Chat',
    items: [
      { href: '/chat', label: 'AI Chat', icon: MessageSquare },
    ],
  },
  {
    id: 'companies',
    label: 'Companies',
    items: [
      { href: '/companies', label: 'Companies', icon: Building2 },
    ],
  },
  {
    id: 'hyperscaler',
    label: 'Hyperscaler',
    items: [
      { href: '/ai-investments', label: 'Hyperscaler', icon: TrendingUp },
    ],
  },
  {
    id: 'facilities-map',
    label: 'Facilities Map',
    items: [
      { href: '/map', label: 'Facilities Map', icon: Globe },
    ],
  },
  {
    id: 'calendar',
    label: 'Calendar',
    items: [
      { href: '/calendar', label: 'Calendar', icon: CalendarDays },
    ],
  },
  {
    id: 'data-center',
    label: 'Document Center',
    items: [
      { href: '/data', label: 'Document Center', icon: Database },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isDark, setIsDark] = useState<boolean>(true);
  const [hydrated, setHydrated] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    news: true,
    'analyst-view': true,
    'ai-research-chat': true,
    companies: true,
    hyperscaler: true,
    'facilities-map': true,
    calendar: true,
  });

  const toggleGroup = (groupId: string) => {
    setOpenGroups((prev) => ({ ...prev, [groupId]: !prev[groupId] }));
  };

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme-mode');
    if (savedTheme) setIsDark(savedTheme === 'dark');
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    const root = document.documentElement;
    root.classList.toggle('dark', isDark);
    localStorage.setItem('theme-mode', isDark ? 'dark' : 'light');
  }, [isDark, hydrated]);

  const toggleTheme = () => {
    const nextDark = !isDark;
    setIsDark(nextDark);
  };

  const theme = isDark
    ? {
        asideBg: 'bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800',
        asideText: 'text-white',
        headerBorder: 'border-slate-700/60',
        collapseBtn:
          'border-slate-600 bg-slate-900/80 text-slate-300 hover:text-white hover:border-slate-500',
        expandBtn:
          'border-slate-600 bg-slate-900/90 text-slate-300 hover:text-white hover:border-slate-500',
        navTitle: 'text-slate-500',
        themeToggleBtn: 'border-slate-700 bg-slate-900/70 text-slate-200 hover:border-slate-600',
        groupCard: 'border-slate-800/80 bg-slate-900/20',
        groupHeaderActive:
          'text-white bg-slate-800/70 border-blue-500/40 shadow-[inset_0_0_0_1px_rgba(59,130,246,0.2)]',
        groupHeaderInactive: 'text-slate-300 border-transparent hover:text-white hover:bg-slate-800/40',
        itemActive: 'bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-lg shadow-blue-500/25',
        itemInactiveDirect: 'text-slate-300 hover:bg-slate-800/60 hover:text-white',
        itemInactiveNested: 'text-slate-400 hover:bg-slate-800/60 hover:text-white',
        badgeActive: 'bg-white/20 text-white',
        badgeInactive: 'bg-purple-500/20 text-purple-400',
      }
    : {
        asideBg: 'bg-gradient-to-b from-slate-100 via-white to-slate-100',
        asideText: 'text-slate-900',
        headerBorder: 'border-slate-300/80',
        collapseBtn:
          'border-slate-300 bg-white/90 text-slate-600 hover:text-slate-900 hover:border-slate-400',
        expandBtn:
          'border-slate-300 bg-white/95 text-slate-600 hover:text-slate-900 hover:border-slate-400',
        navTitle: 'text-slate-500',
        themeToggleBtn: 'border-slate-300 bg-white text-slate-700 hover:border-slate-400',
        groupCard: 'border-slate-300/90 bg-white/70 shadow-sm',
        groupHeaderActive:
          'text-slate-900 bg-blue-50 border-blue-300 shadow-[inset_0_0_0_1px_rgba(59,130,246,0.18)]',
        groupHeaderInactive: 'text-slate-700 border-transparent hover:text-slate-900 hover:bg-slate-100',
        itemActive: 'bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-md shadow-blue-500/20',
        itemInactiveDirect: 'text-slate-700 hover:bg-slate-100 hover:text-slate-900',
        itemInactiveNested: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
        badgeActive: 'bg-white/25 text-white',
        badgeInactive: 'bg-blue-100 text-blue-700',
      };

  return (
    <aside
      className={cn(
        'relative h-screen shrink-0 overflow-hidden flex flex-col transition-[width] duration-300 shadow-2xl',
        theme.asideBg,
        theme.asideText,
        isCollapsed ? 'w-16' : 'w-52'
      )}
    >
      {isCollapsed ? (
        <div className="flex h-full flex-col items-center justify-between py-3">
          <div className="flex flex-col items-center gap-1">
            <button
              type="button"
              onClick={() => setIsCollapsed(false)}
              className={cn(
                'inline-flex h-9 w-9 items-center justify-center rounded-xl border transition-colors',
                theme.expandBtn
              )}
              aria-label="Expand sidebar"
              title="Expand sidebar"
            >
              <PanelLeftOpen className="h-4 w-4" />
            </button>

            <Link
              href="/"
              className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-[#7C5CBF] shadow-lg shadow-purple-500/30"
              title="Go to home"
            >
              <span className="text-[11px] font-black tracking-tight text-white">Ei</span>
              <span className="absolute -top-0.5 -right-0.5 text-[8px] leading-none text-yellow-400">✦</span>
            </Link>

            <div className="mt-1 flex flex-col items-center gap-0.5 overflow-y-auto">
              {navGroups.flatMap((group) =>
                group.items.map((item) => {
                  const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      title={item.label}
                      className={cn(
                        'group relative inline-flex h-9 w-9 items-center justify-center rounded-xl transition-all duration-200',
                        isActive ? theme.itemActive : theme.itemInactiveDirect
                      )}
                    >
                      <Icon className="h-4 w-4" />
                    </Link>
                  );
                })
              )}
            </div>
          </div>

          <button
            type="button"
            onClick={toggleTheme}
            className={cn('inline-flex h-9 w-9 items-center justify-center rounded-xl border text-sm', theme.themeToggleBtn)}
            aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDark ? '🌞' : '🌛'}
          </button>
        </div>
      ) : (
        <>
          <div className={cn('border-b p-4', theme.headerBorder)}>
            <Link href="/" className="flex items-center gap-3">
              <EMSIntelligenceLogo size={40} />
              <div>
                <h1 className="text-xl font-bold leading-tight tracking-tight">EMS Intelligence</h1>
                <p className="mt-0.5 bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-xs font-medium text-transparent">AI Powered</p>
              </div>
            </Link>
          </div>

          <nav className="flex-1 overflow-y-auto p-4">
            <div className="mb-4 flex items-center justify-between px-1">
              <p className={cn('text-xs font-semibold uppercase tracking-wider', theme.navTitle)}>Navigation</p>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={toggleTheme}
                  className="p-1.5 rounded-md text-gray-400 hover:text-gray-200 hover:bg-white/5 transition-colors"
                  aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
                  title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
                >
                  {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                </button>
                <button
                  type="button"
                  onClick={() => setIsCollapsed(true)}
                  className="p-1.5 rounded-md text-gray-400 hover:text-gray-200 hover:bg-white/5 transition-colors"
                  aria-label="Collapse sidebar"
                  title="Collapse sidebar"
                >
                  <PanelLeftClose className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="space-y-3">
              {navGroups.map((group) => {
                const isDirectItem =
                  group.items.length === 1 && group.label.trim().toLowerCase() === group.items[0].label.trim().toLowerCase();
                const hasActiveItem = group.items.some(
                  (item) => pathname === item.href || pathname.startsWith(item.href + '/')
                );
                const isOpen = openGroups[group.id] ?? hasActiveItem;

                if (isDirectItem) {
                  const item = group.items[0];
                  const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
                  const Icon = item.icon;

                  return (
                    <div key={group.id}>
                      <Link
                        href={item.href}
                        className={cn(
                          'group relative flex items-center gap-3 rounded-xl px-3 py-2 transition-all duration-200',
                          isActive ? theme.itemActive : theme.itemInactiveDirect
                        )}
                      >
                        <Icon className={cn('h-4 w-4 transition-transform group-hover:scale-110', isActive && 'drop-shadow-lg')} />
                        <span className="text-[13px] font-semibold tracking-wide">{item.label}</span>
                        {item.badge && (
                          <span
                            className={cn(
                              'ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold',
                              isActive ? theme.badgeActive : theme.badgeInactive
                            )}
                          >
                            {item.badge}
                          </span>
                        )}
                      </Link>
                    </div>
                  );
                }

                return (
                  <div key={group.id}>
                    <button
                      type="button"
                      onClick={() => toggleGroup(group.id)}
                      className={cn(
                        'flex w-full items-center justify-between rounded-xl px-3 py-2 text-left transition-colors',
                        hasActiveItem ? theme.groupHeaderActive : theme.groupHeaderInactive
                      )}
                    >
                      <span className="text-[13px] font-semibold tracking-wide">{group.label}</span>
                      {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                    </button>

                    {isOpen && (
                      <ul className="space-y-1 px-1 pb-1">
                        {group.items.map((item) => {
                          const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
                          const Icon = item.icon;

                          return (
                            <li key={item.href}>
                              <Link
                                href={item.href}
                                className={cn(
                                  'group relative flex items-center gap-3 rounded-xl px-3 py-2 transition-all duration-200',
                                  isActive ? theme.itemActive : theme.itemInactiveNested
                                )}
                              >
                                <Icon className={cn('h-4 w-4 transition-transform group-hover:scale-110', isActive && 'drop-shadow-lg')} />
                                <span className="text-[13px] font-medium">{item.label}</span>
                                {item.badge && (
                                  <span
                                    className={cn(
                                      'ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold',
                                      isActive ? theme.badgeActive : theme.badgeInactive
                                    )}
                                  >
                                    {item.badge}
                                  </span>
                                )}
                              </Link>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          </nav>
        </>
      )}
    </aside>
  );
}
