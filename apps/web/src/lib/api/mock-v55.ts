// Development-only fixtures (npm run dev:mock) for contract §55 ⟨1.0.1⟩, the look. In every new state, so the end-to-end checks and
// the demo show each one:
// - §55.3 `GET /treasury/limits`: the owner's Claude accounts and today's meter. The demo's own state is the everyday one (the main
//   account works, the second is ready, the day is calm). The e2e checks ask for the others through `hq.e2e.limits`:
//   `both-full` (every account full, the queue waits), `warm` (the main one full, the second works), `near` (one off, one unknown),
//   `full-day` (the day's cap is reached), `unknown` (no figure read yet).
// - C2.1 the command sheet's order: an order that names its company (`company`) goes to that company, whatever its words say; with
//   `hq.e2e.order-fail` the hub refuses it (503 with its Persian sentence), so the sheet's failure is seen.
// - `hq.e2e.old55`: a hub before §55 (its routes answer 404 further on).
// Kept in memory, never bundled in production (reached only through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

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
  if (olderHub()) return null;
  if (p === '/treasury/limits' && m === 'GET') return json(limits());
  return null;
}
