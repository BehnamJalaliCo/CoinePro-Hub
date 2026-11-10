'use client';

// ⟨1.0.1⟩ Part C, M14 «پیوستگی»: a tapped card grows into the page it opens. The browser's View Transitions API does it: the card
// carries the shared name while the old page is captured, the new page's header carries it after (`.hq-vt-hero`), and the browser
// morphs one into the other (320 ms, a spring without a bounce; app/globals.css). A browser without the API, or reduced motion: the
// page simply opens.

import { useRouter } from 'next/navigation';
import { useCallback, useEffect } from 'react';
import { usePathname } from 'next/navigation';

/** The class of the element that a card becomes on the next page (a page header). One per page. */
export const VT_HERO = 'hq-vt-hero';

type Doc = Document & { startViewTransition?: (update: () => Promise<void> | void) => { finished: Promise<void> } };

let settle: (() => void) | null = null;
/** The route has changed and its page is in the document: the waiting transition may go on. */
export function routeSettled(): void {
  const s = settle;
  settle = null;
  s?.();
}

/** Mounted once in the shell: tells a waiting transition that the new page is there. */
export function useRouteSettle(): void {
  const pathname = usePathname();
  useEffect(() => { routeSettled(); }, [pathname]);
}

const reduced = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/**
 * Runs [update] (a navigation, a state change that swaps a view) inside a view transition. [from]: the touched element, which takes
 * the shared name for the old snapshot. [update] may be a navigation: the transition then waits for `routeSettled`, at most [wait] ms.
 */
export function viewTransition(update: () => void, from?: HTMLElement | null, opts: { route?: boolean; wait?: number } = {}): void {
  const doc = typeof document === 'undefined' ? null : (document as Doc);
  if (!doc?.startViewTransition || reduced()) { update(); return; }
  if (from) from.style.setProperty('view-transition-name', 'hq-hero');
  const clear = () => { from?.style.removeProperty('view-transition-name'); };
  try {
    const t = doc.startViewTransition(() => {
      if (!opts.route) { update(); clear(); return; }
      return new Promise<void>((resolve) => {
        const done = () => { clear(); resolve(); };
        settle = done;
        update();
        // A slow page never holds the screen: the transition goes on with whatever is there.
        setTimeout(() => { if (settle === done) { settle = null; done(); } }, opts.wait ?? 900);
      });
    });
    void t.finished.catch(() => undefined).finally(clear);
  } catch {
    clear();
    update();
  }
}

/** `go(href, element)`: opens a page out of the card that was tapped. */
export function useViewNav() {
  const router = useRouter();
  return useCallback((href: string, from?: HTMLElement | null) => {
    viewTransition(() => router.push(href), from, { route: true });
  }, [router]);
}
