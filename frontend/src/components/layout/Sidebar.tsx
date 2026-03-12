'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  MessageSquare,
  Building2,
  Settings,
  FileText,
  BarChart3,
  TrendingUp,
  Database,
  Sparkles,
  ChevronRight,
  Brain,
  Globe,
  GitCompare,
  Bell,
  Newspaper,
  CalendarDays,
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
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
    id: 'news-desk',
    label: 'News Desk',
    items: [
      { href: '/news', label: 'News Desk', icon: Newspaper, badge: 'NEW' },
    ],
  },
  {
    id: 'ai-research-chat',
    label: 'Research Chat',
    items: [
      { href: '/chat', label: 'Research Chat', icon: MessageSquare, badge: 'AI' },
    ],
  },
  {
    id: 'intelligence',
    label: 'Competitive Intelligence',
    items: [
      { href: '/competitor-investments', label: 'Competitors', icon: GitCompare, badge: 'NEW' },
      { href: '/ai-investments', label: 'Big Five CapEx', icon: TrendingUp, badge: 'NEW' },
      { href: '/map', label: 'Facilities Map', icon: Globe, badge: 'NEW' },
      { href: '/calendar', label: 'Calendar', icon: CalendarDays },
      { href: '/companies', label: 'Companies', icon: Building2 },
      { href: '/analysis', label: 'Analysis', icon: BarChart3 },
      { href: '/analytics', label: 'Analytics', icon: Brain },
    ],
  },
  {
    id: 'reports',
    label: 'Reports & System',
    items: [
      { href: '/reports', label: 'Reports', icon: FileText },
      { href: '/alerts', label: 'Alerts', icon: Bell },
      { href: '/data', label: 'Data Center', icon: Database },
      { href: '/settings', label: 'Settings', icon: Settings },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isDark, setIsDark] = useState<boolean>(() => {
    if (typeof window === 'undefined') return true;
    const savedTheme = localStorage.getItem('theme-mode');
    return savedTheme ? savedTheme === 'dark' : true;
  });
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    'news-desk': true,
    'ai-research-chat': true,
    intelligence: true,
    reports: false,
  });

  const toggleGroup = (groupId: string) => {
    setOpenGroups((prev) => ({ ...prev, [groupId]: !prev[groupId] }));
  };

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', isDark);
    localStorage.setItem('theme-mode', isDark ? 'dark' : 'light');
  }, [isDark]);

  const toggleTheme = () => {
    const nextDark = !isDark;
    setIsDark(nextDark);
  };

  return (
    <>
      <aside
        className={cn(
          'relative h-screen flex flex-col transition-all duration-300',
          'bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white shadow-2xl',
          isCollapsed ? 'w-0 overflow-hidden' : 'w-72'
        )}
      >
      {!isCollapsed && (
        <button
          type="button"
          onClick={() => setIsCollapsed(true)}
          className="absolute right-3 top-3 z-20 inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-600 bg-slate-900/80 text-slate-300 hover:text-white hover:border-slate-500 transition-colors"
          aria-label="Collapse sidebar"
        >
          <PanelLeftClose className="h-4 w-4" />
        </button>
      )}

      <div className={cn('p-6 border-b border-slate-700/50 transition-opacity', isCollapsed ? 'opacity-0' : 'opacity-100')}>
        <Link href="/" className="flex items-center gap-4 group">
          <div className="bg-gradient-to-br from-blue-600 to-cyan-500 rounded-xl h-12 w-12 flex items-center justify-center shadow-lg shadow-blue-500/25 group-hover:shadow-blue-500/40 transition-shadow">
            <span className="text-white font-black text-[10px] tracking-[0.08em]">FLEX</span>
          </div>
          <div>
            <h1 className="font-bold text-2xl leading-tight tracking-tight">FLEX Pulse</h1>
            <div className="flex items-center gap-1.5 mt-1">
              <Sparkles className="h-3 w-3 text-purple-400" />
              <p className="text-xs font-medium bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">AI Powered</p>
            </div>
          </div>
        </Link>
      </div>

      <nav className={cn('flex-1 p-4 overflow-y-auto transition-opacity', isCollapsed ? 'opacity-0' : 'opacity-100')}>
        <div className="mb-4 px-4 flex items-center justify-between">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Navigation</p>
          <button
            type="button"
            onClick={toggleTheme}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-700 bg-slate-900/70 text-sm hover:border-slate-600"
            aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDark ? '🌞' : '🌛'}
          </button>
        </div>
        <div className="space-y-3">
          {navGroups.map((group) => {
            const isDirectItem =
              group.items.length === 1 && group.label.trim().toLowerCase() === group.items[0].label.trim().toLowerCase();
            const hasActiveItem = group.items.some(
              (item) => pathname === item.href || pathname.startsWith(item.href + '/')
            );
            const isOpen = openGroups[group.id] || hasActiveItem;

            if (isDirectItem) {
              const item = group.items[0];
              const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
              const Icon = item.icon;

              return (
                <div key={group.id} className="rounded-2xl border border-slate-800/80 bg-slate-900/20">
                  <Link
                    href={item.href}
                    className={cn(
                      'flex items-center gap-3 px-4 py-3 rounded-2xl transition-all duration-200 group relative',
                      isActive
                        ? 'bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-lg shadow-blue-500/25'
                        : 'text-slate-300 hover:bg-slate-800/60 hover:text-white'
                    )}
                  >
                    <Icon className={cn('h-5 w-5 transition-transform group-hover:scale-110', isActive && 'drop-shadow-lg')} />
                    <span className="font-semibold tracking-wide">{item.label}</span>
                    {item.badge && (
                      <span
                        className={cn(
                          'ml-auto text-xs px-2 py-0.5 rounded-full font-semibold',
                          isActive ? 'bg-white/20 text-white' : 'bg-purple-500/20 text-purple-400'
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
              <div key={group.id} className="rounded-2xl border border-slate-800/80 bg-slate-900/20">
                <button
                  type="button"
                  onClick={() => toggleGroup(group.id)}
                  className={cn(
                    'flex w-full items-center justify-between px-4 py-3 text-left transition-colors',
                    hasActiveItem ? 'text-white' : 'text-slate-300 hover:text-white'
                  )}
                >
                  <span className="text-sm font-semibold tracking-wide">{group.label}</span>
                  {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </button>

                {isOpen && (
                  <ul className="px-2 pb-2 space-y-1.5">
                    {group.items.map((item) => {
                      const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
                      const Icon = item.icon;

                      return (
                        <li key={item.href}>
                          <Link
                            href={item.href}
                            className={cn(
                              'flex items-center gap-3 px-3 py-3 rounded-xl transition-all duration-200 group relative',
                              isActive
                                ? 'bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-lg shadow-blue-500/25'
                                : 'text-slate-400 hover:bg-slate-800/60 hover:text-white'
                            )}
                          >
                            <Icon className={cn('h-5 w-5 transition-transform group-hover:scale-110', isActive && 'drop-shadow-lg')} />
                            <span className="font-medium">{item.label}</span>
                            {item.badge && (
                              <span
                                className={cn(
                                  'ml-auto text-xs px-2 py-0.5 rounded-full font-semibold',
                                  isActive ? 'bg-white/20 text-white' : 'bg-purple-500/20 text-purple-400'
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

      <div className={cn('p-4 transition-opacity', isCollapsed ? 'opacity-0' : 'opacity-100')}>
        <div className="bg-gradient-to-br from-slate-800 to-slate-800/50 rounded-xl p-4 border border-slate-700/50">
          <div className="flex items-center gap-2 mb-3">
            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse"></div>
            <span className="text-xs font-medium text-slate-400">System Active</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-2xl font-bold text-white">5</p>
              <p className="text-xs text-slate-500">Companies</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-white">18k+</p>
              <p className="text-xs text-slate-500">Documents</p>
            </div>
          </div>
        </div>
      </div>

      <div className={cn('p-4 border-t border-slate-700/50 transition-opacity', isCollapsed ? 'opacity-0' : 'opacity-100')}>
        <div className="flex flex-wrap gap-1.5">
          {['Flex', 'Jabil', 'Celestica', 'Benchmark', 'Sanmina'].map((company) => (
            <span
              key={company}
              className="text-xs px-2 py-1 bg-slate-800 rounded-md text-slate-400 hover:text-white hover:bg-slate-700 transition-colors cursor-default"
            >
              {company}
            </span>
          ))}
        </div>
      </div>
      </aside>

      {isCollapsed && (
        <button
          type="button"
          onClick={() => setIsCollapsed(false)}
          className="fixed left-2 top-2 z-30 inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-600 bg-slate-900/90 text-slate-300 hover:text-white hover:border-slate-500 transition-colors"
          aria-label="Expand sidebar"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </button>
      )}
    </>
  );
}
