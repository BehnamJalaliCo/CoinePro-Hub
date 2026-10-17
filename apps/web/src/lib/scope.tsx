'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

/** The scope switch (D0 brief): holding (all companies) or one company. Data-driven, any number of companies. */
type Scope = { company: string | null; setCompany: (c: string | null) => void };
const Ctx = createContext<Scope>({ company: null, setCompany: () => {} });

export function ScopeProvider({ children }: { children: ReactNode }) {
  const [company, set] = useState<string | null>(null);
  useEffect(() => {
    try { const v = localStorage.getItem('hq-scope'); if (v) set(v === '*' ? null : v); } catch { /* storage unavailable */ }
  }, []);
  const setCompany = (c: string | null) => {
    set(c);
    try { localStorage.setItem('hq-scope', c ?? '*'); } catch { /* storage unavailable */ }
  };
  return <Ctx.Provider value={{ company, setCompany }}>{children}</Ctx.Provider>;
}

export const useScope = () => useContext(Ctx);
/** Query-friendly company filter: undefined for the whole holding. */
export const scopeFilter = (c: string | null) => (c ? [c] : undefined);
