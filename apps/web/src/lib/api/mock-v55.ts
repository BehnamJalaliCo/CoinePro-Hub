// Development-only fixtures (npm run dev:mock) for contract §55 ⟨1.0.1⟩, the look. In every new state, so the end-to-end checks and
// the demo show each one:
// - §55.3 `GET /treasury/limits`: the owner's Claude accounts and today's meter. The demo's own state is the everyday one (the main
//   account works, the second is ready, the day is calm). The e2e checks ask for the others through `hq.e2e.limits`:
//   `both-full` (every account full, the queue waits), `warm` (the main one full, the second works), `near` (one off, one unknown),
//   `full-day` (the day's cap is reached), `unknown` (no figure read yet).
// - C2.1 the command sheet's order: an order that names its company (`company`) goes to that company, whatever its words say; with
//   `hq.e2e.order-fail` the hub refuses it (503 with its Persian sentence), so the sheet's failure is seen.
// - `hq.e2e.old55`: a hub before §55 (its routes answer 404 further on).
// - §55.2 `GET /publish-desk?company=`: the desk in every state, built from the outputs and publications of ./mock-v47 (so a publish
//   or a cancel shows on it at once): cards ready to go out (a reel with its cover, a picture, a carousel, a daily package of a working
//   group, one of a company whose publishing path is not set yet), a post set for its hour and one on its way, and what went out,
//   failed or was taken back. `hq.e2e.desk=empty`: nothing on it.
// - A list of outputs carries the files of the session's reels, so their cards show a poster.
// - «نگه دار» of a session: the live work's ref is found through the list's search and stopped (`POST /work/{id}/stop`).
// Kept in memory, never bundled in production (reached only through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

import { LIVE_WORKS, stopLiveWork } from './mock-v34';
import { deskOf, outputFiles } from './mock-v47';

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const refuse = (status: number, code: string, message_fa: string) => json({ type: 'about:blank', title: code, status, code, message_fa }, status);
type Next = (r: Request) => Promise<Response>;
const flag = (k: string): string | null => { try { return window.localStorage.getItem(k); } catch { return null; } };
const olderHub = () => flag('hq.e2e.old55') === '1';
const inMin = (n: number) => new Date(Date.now() + n * 60_000).toISOString();
const agoMin = (n: number) => new Date(Date.now() - n * 60_000).toISOString();

/** Midnight of the owner's zone (Tehran, +03:30 all year): when today's meter starts again. */
function nextMidnight(): string {
  const off = 210 * 60_000;
  const local = new Date(Date.now() + off);
  return new Date(Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate() + 1) - off).toISOString();
}

type Account = { key: string; name_fa: string; state: 'working' | 'ready' | 'full' | 'off'; utilization: string | null; window_fa: string | null; resets_at: string | null; observed_at: string | null };
const account = (key: string, name_fa: string, state: Account['state'], utilization: string | null, resetsIn: number | null): Account => ({
  key, name_fa, state, utilization, window_fa: 'پنجره‌ی پنج‌ساعته', resets_at: resetsIn == null ? null : inMin(resetsIn), observed_at: agoMin(2),
});
const meter = (spent: number, cap: number, note_fa: string) => {
  const share = cap ? spent / cap : 0;
  return { spent, cap, share: share.toFixed(4), state: share >= 1 ? 'full' : share >= 0.9 ? 'near' : share >= 0.7 ? 'warm' : 'calm', resets_at: nextMidnight(), note_fa };
};

function limits() {
  const main = 'اکانت اصلی';
  const second = 'اکانت دوم';
  switch (flag('hq.e2e.limits')) {
    case 'both-full':
      return { accounts: [account('main', main, 'full', '1', 130), account('second', second, 'full', '0.98', 220)], waiting: true, today: meter(546_000, 600_000, 'مصرف امروز به ۹۰٪ سقف نزدیک شده؛ کارهای کم‌اهمیت به فردا میروند.') };
    case 'warm':
      return { accounts: [account('main', main, 'full', '1', 65), account('second', second, 'working', '0.41', 190)], waiting: false, today: meter(456_000, 600_000, 'از ۷۰٪ سقف امروز گذشته‌ای؛ هنوز جا هست.') };
    case 'near':
      return { accounts: [{ ...account('main', main, 'off', null, null), observed_at: null }, { ...account('second', second, 'working', null, null) }], waiting: false, today: meter(558_000, 600_000, 'مصرف امروز به ۹۰٪ سقف نزدیک شده؛ کارهای کم‌اهمیت به فردا میروند.') };
    case 'full-day':
      return { accounts: [account('main', main, 'ready', '0.74', 95), account('second', second, 'ready', '0.12', 240)], waiting: false, today: meter(612_000, 600_000, 'سقف امروز پر شد؛ فقط کارهای فوری اجرا میشوند.') };
    case 'unknown':
      return { accounts: [{ ...account('main', main, 'ready', null, null), observed_at: null }, { ...account('second', second, 'ready', null, null), observed_at: null }], waiting: false, today: meter(0, 600_000, 'مصرف امروز آرام است.') };
    default:
      return { accounts: [account('main', main, 'working', '0.62', 148), account('second', second, 'ready', '0.08', 263)], waiting: false, today: meter(412_000, 600_000, 'مصرف امروز آرام است.') };
  }
}

/** Two outputs of the demo's list that carry media of their own: a picture, and a short film with a picture. */
const media = (id: string, name: string, mime: string, size: number) => ({ id, name, mime, size, sha256: '' });
const LIST_MEDIA: Record<string, ReturnType<typeof media>[]> = {
  'O-000028': [media('/demo/pc-landing-redesign.webp', 'landing-autumn.jpg', 'image/jpeg', 19_810)],
  'O-000046': [media('/demo/fx-reel-levels.mp4', 'competitor-app.mp4', 'video/mp4', 110_561), media('/demo/fx-reel-resist-poster.webp', 'pricing-table.jpg', 'image/jpeg', 8_560)],
};
const filesOf = (ref: string) => outputFiles(ref) ?? LIST_MEDIA[ref] ?? null;

/** §55 and the command sheet's order; what is not its own goes on to [next] (the rest of the demo). */
export async function handle55(req: Request, p: string, next: Next): Promise<Response | null> {
  const m = req.method;
  if (p === '/orders' && m === 'POST') {
    if (flag('hq.e2e.order-fail') === '1') return refuse(503, 'hub_unavailable', 'ستاد الان جواب نمیدهد؛ کمی بعد دوباره بزن.');
    const b = (await req.clone().json().catch(() => ({}))) as { text?: string; company?: string | null; route?: unknown; [k: string]: unknown };
    if (!b.company || b.route) return null;
    // The order names its company: the secretary's reading of the words is kept, with that company in front.
    const read = await next(new Request(new URL('/api/v1/orders/preview', req.url), { method: 'POST', headers: req.headers, body: JSON.stringify({ text: b.text ?? '', source: 'text' }) }));
    const route = read.ok ? ((await read.json()) as { companies?: string[]; preview_fa?: string; confidence?: number; why_fa?: string; [k: string]: unknown }) : null;
    const { company, ...rest } = b;
    const body = route ? (() => { const { preview_fa: _p, confidence: _c, why_fa: _w, ...r } = route; return { ...rest, route: { ...r, companies: [company], collaborators: [] } }; })() : rest;
    return next(new Request(req.url, { method: 'POST', headers: req.headers, body: JSON.stringify(body) }));
  }
  // A hub before part A has no routine route at all (the demo's fallback would answer it with an empty success).
  if (p === '/routines' && m === 'POST' && flag('hq.e2e.old47') === '1') return refuse(404, 'not_found', 'پیدا نشد.');
  // «نگه دار»: the session's live work, named by ref, is resolved to its id and stopped (§33.10, §43; the work stays open).
  const q = new URL(req.url).searchParams;
  if (p === '/work' && m === 'GET' && LIVE_WORKS[q.get('q') ?? '']) {
    const ref = q.get('q')!;
    return json({ items: [{ id: LIVE_WORKS[ref], ref, company: 'TY', title: ref, status: 'in_progress' }], next_cursor: null });
  }
  const stop = /^\/work\/([^/]+)\/stop$/.exec(p);
  if (stop && m === 'POST') {
    const ref = Object.keys(LIVE_WORKS).find((k) => LIVE_WORKS[k] === stop[1]);
    if (ref) return json(stopLiveWork(ref) ?? { work_ref: ref, workspace: null, jobs_stopped: 0 });
  }
  // The outputs that carry media show it (§43.4 an output's attachments): in the list as a poster, on its page as the thing itself.
  const one = /^\/deliverables\/(O-\d+)$/.exec(p);
  if ((p === '/deliverables' || (one && LIST_MEDIA[one[1]!])) && m === 'GET' && flag('hq.e2e.old47') !== '1') {
    const res = await next(req);
    if (!res.ok) return res;
    type D = { ref: string; attachments?: unknown[] };
    const withFiles = (d: D): D => { const f = filesOf(d.ref); return f && !d.attachments?.length ? { ...d, attachments: f } : d; };
    const data = (await res.json()) as D & { items?: D[] };
    return json(one ? withFiles(data) : { ...data, items: (data.items ?? []).map(withFiles) });
  }
  if (olderHub()) return null;
  if (p === '/treasury/limits' && m === 'GET') return json(limits());
  // §55.2 the publish desk. A hub before §47 knows nothing of it either.
  if (p === '/publish-desk' && m === 'GET') {
    if (flag('hq.e2e.old47') === '1') return refuse(404, 'not_found', 'پیدا نشد.');
    if (flag('hq.e2e.desk') === 'empty') return json({ ready: [], queue: [], done: [] });
    const company = q.get('company');
    if (company && !['TY', 'FX', 'PC'].includes(company)) return refuse(404, 'not_found', 'این شرکت پیدا نشد.');
    return json(deskOf(company));
  }
  return null;
}
