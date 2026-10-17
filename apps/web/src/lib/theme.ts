'use client';

import { usePersisted } from './store';

export type ThemeChoice = 'night' | 'day' | 'system';

export function useTheme(): [ThemeChoice, (t: ThemeChoice) => void] {
  const [v, setV] = usePersisted('hq-theme', 'system');
  const t: ThemeChoice = v === 'night' || v === 'day' ? v : 'system';
  const set = (next: ThemeChoice) => {
    const el = document.documentElement;
    if (next === 'system') delete el.dataset.theme;
    else el.dataset.theme = next;
    setV(next === 'system' ? null : next);
  };
  return [t, set];
}
