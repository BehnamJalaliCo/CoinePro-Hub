'use client';

// ⟨1.0.1⟩ Part C: a page whose body is a talk fills the screen under whatever sits above it (the top bar, a band, a banner), so the
// talk scrolls inside and the composer keeps its place at the bottom. The hook sets the element's height from where it starts to the
// bottom of the window, less [bottom] (the navigation and the page's own padding), and keeps it right as the window or the page changes.

import { useLayoutEffect, useRef, useSyncExternalStore } from 'react';

export function useFillHeight<T extends HTMLElement = HTMLDivElement>(bottom: () => number, min = 420) {
  const ref = useRef<T>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      const top = el.getBoundingClientRect().top + window.scrollY;
      // ⟨1.0.3⟩ §58.1 the visible height: with the keyboard up, what is left above it (a browser that overlays the keyboard).
      const vh = Math.min(window.innerHeight, window.visualViewport?.height ?? Number.POSITIVE_INFINITY);
      // The floor never pushes the bottom under a keyboard: it is at most what is visible below the frame's top.
      const h = `${Math.max(Math.min(min, Math.round(vh - top)), Math.round(vh - top - bottom()))}px`;
      if (el.style.height !== h) el.style.height = h;
    };
    fit();
    window.addEventListener('resize', fit);
    window.visualViewport?.addEventListener('resize', fit);
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(fit);
    ro?.observe(document.body);
    return () => { window.removeEventListener('resize', fit); window.visualViewport?.removeEventListener('resize', fit); ro?.disconnect(); };
  }, [bottom, min]);
  return ref;
}

/**
 * Whether the window is wide enough for two columns (a list beside its detail). Wide until the browser says otherwise, so a page that
 * also hides the same thing with CSS never flashes.
 */
export function useWide(query = '(min-width: 1024px)'): boolean {
  return useSyncExternalStore(
    (changed) => { const m = window.matchMedia(query); m.addEventListener('change', changed); return () => m.removeEventListener('change', changed); },
    () => window.matchMedia(query).matches,
    () => true,
  );
}
