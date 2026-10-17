'use client';

import { useSyncExternalStore } from 'react';

/** Small external stores read with useSyncExternalStore: no setState-in-effect, no hydration mismatch. */
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
const subscribe = (l: () => void) => {
  listeners.add(l);
  const onStorage = () => l();
  window.addEventListener('storage', onStorage);
  return () => { listeners.delete(l); window.removeEventListener('storage', onStorage); };
};

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

export function usePersisted(key: string, fallback: string): [string, (v: string | null) => void] {
  const v = useSyncExternalStore(subscribe, () => read(key) ?? fallback, () => fallback);
  const set = (next: string | null) => {
    try { if (next == null) localStorage.removeItem(key); else localStorage.setItem(key, next); } catch { /* storage unavailable */ }
    emit();
  };
  return [v, set];
}

// A minute clock for "time left" labels; 0 on the server (those labels render client-side only).
let now = typeof window === 'undefined' ? 0 : Date.now();
const clockSubs = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | undefined;
const subscribeClock = (l: () => void) => {
  clockSubs.add(l);
  if (!timer) timer = setInterval(() => { now = Date.now(); clockSubs.forEach((f) => f()); }, 30_000);
  return () => { clockSubs.delete(l); if (!clockSubs.size && timer) { clearInterval(timer); timer = undefined; } };
};
export const useNow = () => useSyncExternalStore(subscribeClock, () => now, () => 0);

/** True once on the client (for browser-only capabilities). */
const noop = () => () => {};
export const useIsClient = () => useSyncExternalStore(noop, () => true, () => false);
