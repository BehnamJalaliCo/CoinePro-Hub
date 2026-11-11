'use client';

// ⟨1.0.1⟩ Part C, M18 «جمع شدن سربرگ»: a sticky header folds to one line once the page has scrolled under it. Put the ref on a
// zero-height sentinel right above the header; the hook says whether the header is stuck. The header takes `hq-m18` and
// `data-stuck`, and whatever folds away inside it takes `hq-m18-fold` (app/globals.css). The header sticks under the shell's bar,
// whose height the shell publishes as `--hq-top` (the bar grows when a band rides on it): `STICKY_TOP` is that place.

import { useCallback, useEffect, useState } from 'react';

/** Where a sticky header of a page stops: right under the shell's top bar, whatever rides on it. */
export const STICKY_TOP = 'top-[var(--hq-top,64px)]';

const shellTop = () => {
  if (typeof document === 'undefined') return 64;
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--hq-top'));
  return Number.isFinite(v) && v > 0 ? v : 64;
};

export function useStuck<T extends HTMLElement = HTMLDivElement>() {
  // The sentinel may arrive after the first paint (a page that waits for its data): the element is state, not a plain ref.
  const [el, setEl] = useState<T | null>(null);
  const [stuck, setStuck] = useState(false);
  const sentinel = useCallback((node: T | null) => setEl(node), []);
  useEffect(() => {
    if (!el) return;
    let frame = 0;
    const read = () => { frame = 0; setStuck(el.getBoundingClientRect().top < shellTop() - 1); };
    const ask = () => { if (!frame) frame = requestAnimationFrame(read); };
    read();
    window.addEventListener('scroll', ask, { passive: true });
    window.addEventListener('resize', ask);
    return () => { window.removeEventListener('scroll', ask); window.removeEventListener('resize', ask); if (frame) cancelAnimationFrame(frame); };
  }, [el]);
  return { sentinel, stuck: !!el && stuck };
}
