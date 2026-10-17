'use client';

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import type { IconName } from '@/generated/icons';
import { cx } from '@/lib/format';

type Toast = { id: number; tone: 'ok' | 'error' | 'info'; text: ReactNode; action?: { label: string; run: () => void } };
const Ctx = createContext<(t: Omit<Toast, 'id'>) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, 'id'>) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs.slice(-2), { ...t, id }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), t.tone === 'error' ? 7000 : 4200);
  }, []);
  const v = useMemo(() => push, [push]);
  return (
    <Ctx.Provider value={v}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-20 z-[60] flex flex-col items-center gap-2 px-4 md:bottom-6">
        {items.map((t) => {
          const icon: IconName = t.tone === 'ok' ? 'seal' : t.tone === 'error' ? 'urgent' : 'info';
          return (
            <div key={t.id} className="hq-rise pointer-events-auto flex min-h-12 w-full max-w-md items-center gap-3 rounded-[14px] bg-raised px-4 py-2 shadow-[0_12px_32px_rgba(0,0,0,.35)]">
              <span className={cx(t.tone === 'ok' ? 'text-gold-ink' : t.tone === 'error' ? 'text-neg' : 'text-sec')}><Icon name={icon} size={20} active={t.tone === 'ok'} /></span>
              <span className="flex-1 text-[13px] text-ink">{t.text}</span>
              {t.action ? <button type="button" className="text-[13px] font-semibold text-gold-ink" onClick={t.action.run}>{t.action.label}</button> : null}
            </div>
          );
        })}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
