'use client';

import { useEffect, useRef, useState, type RefObject } from 'react';
import { cx } from '@/lib/format';

/** ⟨1.19⟩ A small «کپی» under a turn: copies the plain text of the element it points at and says «کپی شد». The text itself stays selectable. */
export function CopyButton({ target, text, className }: { target?: RefObject<HTMLElement | null>; text?: string; className?: string }) {
  const [done, setDone] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const copy = async () => {
    const value = (text ?? target?.current?.innerText ?? '').trim();
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = value;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch { return; } finally { ta.remove(); }
    }
    setDone(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setDone(false), 1800);
  };
  return (
    <button type="button" onClick={() => void copy()} aria-label={done ? 'کپی شد' : 'کپی متن'} className={cx('self-start rounded-full px-2 py-0.5 text-[11px] text-muted hover:bg-hover hover:text-ink', className)}>
      <span aria-live="polite">{done ? 'کپی شد' : 'کپی'}</span>
    </button>
  );
}
