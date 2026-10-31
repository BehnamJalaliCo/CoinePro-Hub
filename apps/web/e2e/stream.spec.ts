import { expect, test, type Request, type Route } from '@playwright/test';

// The real stream code (lib/stream.ts) against a fake hub stream: the page's own fetch of /api/v1/stream is answered here, one response per
// connection. The demo's beat stands aside while `hq.e2e.stream` is set, so only these events reach the panel. Checked: one connection for
// every topic, any named event type (none listed in the panel), a reconnect that carries Last-Event-ID, and recovery after a 502.

const ev = (id: number, type: string, ref: string, data: Record<string, unknown> = {}) =>
  `id: ${id}\nevent: ${type}\ndata: ${JSON.stringify({ id: `e${id}`, type, at: new Date().toISOString(), company: 'TY', ref, data })}\n\n`;
const sse = (body: string) => ({ status: 200, headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-store' }, body: `: topics all\nretry: 3000\n\n${body}` });

test('reads every event on one connection, resumes with Last-Event-ID and survives a 502', async ({ page }) => {
  const seen: Array<{ url: string; lastId: string | null; status: number }> = [];
  let refused = false;
  await page.addInitScript(() => window.localStorage.setItem('hq.e2e.stream', '1'));
  // Answered by what the connection resumes from (a development build mounts the shell twice, so the first connection may be dropped):
  // fresh → two events and the hub closes the stream (a deploy); from 42 → once a 502 (the hub restarting), then what was missed;
  // from 44 → a quiet stream.
  await page.route('**/api/v1/stream**', async (route: Route, req: Request) => {
    const lastId = req.headers()['last-event-id'] ?? null;
    const reply = !lastId ? sse(ev(41, 'media.series', 'SR-0041', { status: 'sealed' }) + ev(42, 'decision.updated', 'D-000042', { status: 'withdrawn' }))
      : lastId === '42' && !refused ? null
      : lastId === '42' ? sse(ev(43, 'work.council', 'W-000209', { state: 'done' }) + ev(44, 'catalogue.updated', 'TY', { state: 'done' }))
      : sse('');
    seen.push({ url: req.url(), lastId, status: reply ? 200 : 502 });
    if (!reply) { refused = true; return route.fulfill({ status: 502, contentType: 'text/html', body: '<html>502 Bad Gateway</html>' }); }
    return route.fulfill(reply);
  });
  await page.goto('/');
  const feed = page.getByRole('list', { name: 'آخرین رویدادها' });
  await expect(feed.getByText(/W-000209/).first()).toBeVisible({ timeout: 30_000 });
  await expect(feed.getByText('رویداد تازه در کاتالوگ شرکت')).toBeVisible();
  await expect.poll(() => seen.some((s) => s.lastId === '44'), { timeout: 10_000 }).toBe(true);
  // One connection for every topic; the panel names none of them.
  expect(seen.every((s) => new URL(s.url).searchParams.get('topics') === 'all')).toBe(true);
  // After the 502 the panel asked again from the same id, and got what it had missed.
  const i502 = seen.findIndex((s) => s.status === 502);
  expect(i502).toBeGreaterThan(0);
  expect(seen[i502]!.lastId).toBe('42');
  expect(seen[i502 + 1]!.lastId).toBe('42');
  await expect(page.getByTitle('زنده')).toBeVisible();
});

test('shows the stream offline while the hub refuses it, and live again when it answers', async ({ page }) => {
  let refuse = true;
  await page.addInitScript(() => window.localStorage.setItem('hq.e2e.stream', '1'));
  await page.route('**/api/v1/stream**', (route) => (refuse ? route.fulfill({ status: 503, body: '' }) : route.fulfill(sse(ev(7, 'work.updated', 'W-000210', { status: 'in_progress' })))));
  await page.goto('/');
  await expect(page.getByTitle('قطع؛ دوباره وصل میشود')).toBeVisible();
  refuse = false;
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(page.getByTitle('زنده')).toBeVisible({ timeout: 15_000 });
});
