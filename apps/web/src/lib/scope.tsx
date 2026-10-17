'use client';

import { createContext, useContext, type ReactNode } from 'react';
import { usePersisted } from './store';

/** The scope switch (D0 brief): the whole holding or one company. Data-driven, any number of companies. */
type Scope = { company: string | null; setCompany: (c: string | null) => void };
const Ctx = createContext<Scope>({ company: null, setCompany: () => {} });

export function ScopeProvider({ children }: { children: ReactNode }) {
  const [v, setV] = usePersisted('hq-scope', '*');
  const company = v === '*' ? null : v;
  return <Ctx.Provider value={{ company, setCompany: (c) => setV(c ?? '*') }}>{children}</Ctx.Provider>;
}

export const useScope = () => useContext(Ctx);
