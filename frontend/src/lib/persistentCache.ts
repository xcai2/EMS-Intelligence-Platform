/**
 * Persistent browser-local cache that survives frontend/backend restarts.
 * Uses localStorage with a versioned envelope. No TTL — data stays until
 * the user clicks Refresh or the version number bumps.
 */

type CacheEnvelope<T> = {
  version: number;
  savedAt: string;
  payload: T;
};

export function readPersistentCache<T>(key: string, version = 1): T | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEnvelope<T>;
    if (parsed.version !== version) return null;
    return parsed.payload ?? null;
  } catch {
    return null;
  }
}

export function writePersistentCache<T>(key: string, payload: T, version = 1): void {
  if (typeof window === 'undefined') return;
  try {
    const envelope: CacheEnvelope<T> = {
      version,
      savedAt: new Date().toISOString(),
      payload,
    };
    localStorage.setItem(key, JSON.stringify(envelope));
  } catch {
    // localStorage full or unavailable — don't crash the page
  }
}

export function clearPersistentCache(key: string): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(key);
  } catch {}
}
