import { expect, type Page } from '@playwright/test';

// Shared by the e2e suites. In the demo (NEXT_PUBLIC_HQ_MOCK=1) the API answers inside the page, so there is no network response to
// watch; «خطاخوان» records every failed call the panel made (and every crash), so the checks read it as the owner would.

type Entry = { id: number; kind: string; level: string; method?: string | null; path?: string | null; status?: number | null; title?: string | null; detail?: string | null };

/** The warnings and errors «خطاخوان» kept in this test's browser. */
export async function loggedFailures(page: Page): Promise<string[]> {
  const entries = await page.evaluate(() => {
    try { return (JSON.parse(localStorage.getItem('hq.errors.current') ?? 'null') as { entries: unknown[] } | null)?.entries ?? []; } catch { return []; }
  }).catch(() => [] as unknown[]);
  return (entries as Entry[]).filter((e) => e.level !== 'info')
    .map((e) => `«خطاخوان» #${e.id} ${e.kind}: ${[e.method, e.path].filter(Boolean).join(' ')}${e.status != null ? ` → ${e.status}` : ''} ${e.title ?? ''} ${e.detail ?? ''}`.trim());
}

/**
 * Fails the test on any page error, console error, failed API call (on the network, when there is one) or warning in «خطاخوان» while
 * [run] is going on. [allow]: «خطاخوان» lines a test provokes on purpose.
 */
export async function clean(page: Page, run: () => Promise<void>, allow: RegExp[] = []) {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('response', (r) => { if (r.url().includes('/api/v1/') && r.status() >= 400) errors.push(`HTTP ${r.status()} ${r.url()}`); });
  await run();
  errors.push(...(await loggedFailures(page)).filter((l) => !allow.some((re) => re.test(l))));
  expect(errors, errors.join('\n')).toEqual([]);
}
