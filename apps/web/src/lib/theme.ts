'use client';

import { useEffect, useState } from 'react';

export type ThemeChoice = 'night' | 'day' | 'system';

export function useTheme(): [ThemeChoice, (t: ThemeChoice) => void] {
  const [t, setT] = useState<ThemeChoice>('system');
  useEffect(() => {
    try { const v = localStorage.getItem('hq-theme'); if (v === 'night' || v === 'day') setT(v); } catch { /* ignore */ }
  }, []);
  const set = (v: ThemeChoice) => {
    setT(v);
    const el = document.documentElement;
    if (v === 'system') { delete el.dataset.theme; try { localStorage.removeItem('hq-theme'); } catch { /* ignore */ } }
    else { el.dataset.theme = v; try { localStorage.setItem('hq-theme', v); } catch { /* ignore */ } }
  };
  return [t, set];
}
