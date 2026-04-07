'use client';

import { useEffect, useState, type ReactNode } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
const HEALTHCHECK_TIMEOUT_MS = 2500;
const HEALTHCHECK_INTERVAL_MS = 5000;

type BackendStatus = 'checking' | 'online' | 'offline';

async function checkBackendHealth(): Promise<boolean> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), HEALTHCHECK_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_URL}/api/health`, {
      cache: 'no-store',
      signal: controller.signal,
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export function BackendGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<BackendStatus>('checking');

  useEffect(() => {
    let active = true;

    const runHealthcheck = async () => {
      const isAvailable = await checkBackendHealth();
      if (!active) return;
      setStatus(isAvailable ? 'online' : 'offline');
    };

    if (status !== 'online') {
      void runHealthcheck();
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void runHealthcheck();
      }
    };
    const handleWindowFocus = () => {
      void runHealthcheck();
    };

    const intervalId =
      status === 'online' ? null : window.setInterval(runHealthcheck, HEALTHCHECK_INTERVAL_MS);

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleWindowFocus);

    return () => {
      active = false;
      if (intervalId !== null) {
        window.clearInterval(intervalId);
      }
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleWindowFocus);
    };
  }, [status]);

  if (status === 'online') {
    return <>{children}</>;
  }

  const title = status === 'checking' ? 'Connecting to backend...' : 'Backend unavailable';
  const message =
    status === 'checking'
      ? 'Waiting for the API before rendering the application.'
      : 'Start the backend service to access the frontend application.';

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-slate-100">
      <div className="w-full max-w-md rounded-3xl border border-slate-800 bg-slate-900/90 p-8 text-center shadow-2xl shadow-slate-950/50">
        <div className="mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-full border border-slate-700 bg-slate-950">
          <div
            className={`h-5 w-5 rounded-full border-2 border-slate-500 border-t-cyan-400 ${
              status === 'checking' ? 'animate-spin' : ''
            }`}
          />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-white">{title}</h1>
        <p className="mt-3 text-sm leading-6 text-slate-400">{message}</p>
      </div>
    </div>
  );
}
