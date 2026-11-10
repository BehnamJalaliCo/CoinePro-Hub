'use client';

// ⟨1.0.1⟩ Part C, M18 «جمع شدن سربرگ»: a sticky header folds to one line once the page has scrolled under it. Put the ref on a
// zero-height sentinel right above the header; the hook says whether the header is stuck. The header takes `hq-m18` and
// `data-stuck`, and whatever folds away inside it takes `hq-m18-fold` (app/globals.css).

import { useEffect, useRef, useState } from 'react';

export function useStuck<T extends HTMLElement = HTMLDivElement>(offset = 0) {
  const sentinel = useRef<T>(null);
  const [stuck, setStuck] = useState(false);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(([e]) => setStuck(!!e && !e.isIntersecting), { rootMargin: `-${offset}px 0px 0px 0px`, threshold: 0 });
    io.observe(el);
    return () => io.disconnect();
  }, [offset]);
  return { sentinel, stuck };
}
