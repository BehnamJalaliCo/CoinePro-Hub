// Development-only fixtures (npm run dev:mock) for contract §57 ⟨1.0.3⟩, the session's team, one person at a time. The demo's content
// session F-0093 (Pro-Chart's reel about RSI divergence, ./mock-v34) has a team in every state, so the end-to-end checks and the demo
// show each one:
// - §57.1 `GET /orders/F-0093/team`: the holder (Pro-Chart's media director), the scriptwriter at work with two lines the owner has not
//   read, the director's and the motion designer's seats empty, and the company's narrator (§48, read from ./mock-v47, so a change in
//   the picker shows on the chip);
// - §57.2 the scriptwriter's side talk, newest last; reading its newest page marks it read; a code that is no seat answers 404;
// - §57.3 a word to the scriptwriter is a side line at once (`woken`), and a moment later he answers in the side talk (one more unread
//   line); the holder's word is refused (409, «با مسئول جلسه از همین جای نوشتن حرف بزن.»);
// - §57.5 an empty seat is hired at once (the team as it now stands); with `hq.e2e.hire=refuse` the hub refuses it in its own words.
// - §57.6 three versions of the session's notes (`produced_with.revision_of`, and once `revision_of` on the deliverable itself) and a
//   voice-over beside them.
// Every other session answers `/team` with 404, as a hub before §57 does; `hq.e2e.old57` makes F-0093's do the same.
// Kept in memory, never bundled in production (reached only through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const refuse = (status: number, code: string, message_fa: string, fields?: Record<string, string>) =>
  json({ type: 'about:blank', title: code, status, code, message_fa, ...(fields ? { fields } : {}) }, status);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const flag = (k: string): string | null => { try { return window.localStorage.getItem(k); } catch { return null; } };
const NOW = () => new Date().toISOString();
const minsAgo = (n: number) => new Date(Date.now() - n * 60_000).toISOString();
type Next = (r: Request) => Promise<Response>;

const REF = 'F-0093';
const COMPANY = 'PC';

// ========================================================================================================= the team ==
type Seat = {
  key: string; role: string | null; role_fa: string; holder: boolean; employee: { code: string; title_fa: string; company: string } | null;
  state: 'working' | 'idle' | 'empty'; last: { at: string; who: 'owner' | 'seat'; text: string } | null; unread: number;
};
type Line = { id: string; at: string; who: 'owner' | 'seat'; who_fa: string; text: string; work_ref: string | null };

const filled = (key: string, role: string | null, role_fa: string, title_fa: string, state: Seat['state'] = 'idle', holder = false): Seat => ({
  key, role, role_fa, holder, employee: { code: key, title_fa, company: COMPANY }, state, last: null, unread: 0,
});
const empty = (role: string, role_fa: string): Seat => ({ key: `role:${role}`, role, role_fa, holder: false, employee: null, state: 'empty', last: null, unread: 0 });
/** Who a hire brings, by role. */
const HIRES: Record<string, { code: string; title_fa: string }> = {
  video_director: { code: 'PC-DIRECTOR-01', title_fa: 'کارگردان ریلز پرو-چارت' },
  motion_designer: { code: 'PC-MOTION-01', title_fa: 'طراح موشن‌گرافی پرو-چارت' },
};

let seats: Seat[] = [];
const lines = new Map<string, Line[]>();
let lineSeq = 0;
const lineId = () => `sl-${String(++lineSeq).padStart(5, '0')}`;
const said = new Map<string, unknown>();
const hired = new Map<string, unknown>();

function seed() {
  if (seats.length) return;
  const writer = filled('PC-SCRIPT-01', 'scriptwriter', 'نویسنده', 'نویسنده‌ی ریلز پرو-چارت', 'working');
  seats = [
    filled('PC-MEDIA-MGR', 'media_director', 'مسئول جلسه', 'مدیر رسانه پرو-چارت', 'idle', true),
    writer,
    empty('video_director', 'کارگردان'),
    empty('motion_designer', 'موشن‌گرافی'),
  ];
  const talk: Line[] = [
    { id: lineId(), at: minsAgo(52), who: 'owner', who_fa: 'مدیر کل', text: 'متن گوینده را کوتاه‌تر کن؛ زیر چهل ثانیه باشد.', work_ref: 'W-000341' },
    { id: lineId(), at: minsAgo(47), who: 'seat', who_fa: writer.employee!.title_fa, text: 'باشه؛ به سی‌وپنج ثانیه رساندم و جمله‌ی آخر را با شعار پرو-چارت تمام کردم.', work_ref: 'W-000341' },
    { id: lineId(), at: minsAgo(12), who: 'seat', who_fa: writer.employee!.title_fa, text: 'یادداشت‌های سناریو را هم به‌روز کردم؛ نسخه‌ی تازه در جلسه است.', work_ref: 'W-000341' },
  ];
  lines.set(writer.key, talk);
  writer.unread = 2;
  writer.last = lastOf(talk.at(-1)!);
}
const lastOf = (l: Line): Seat['last'] => ({ at: l.at, who: l.who, text: l.text.slice(0, 160) });

/** §48's narrator of the order's company, when one is set (read where the narrator lives, so the picker's change shows here). */
async function narratorOf(req: Request, next: Next) {
  const res = await next(new Request(new URL(`/api/v1/companies/${COMPANY}/narrator`, req.url)));
  if (!res.ok) return null;
  const n = (await res.json()) as { set?: boolean; voice?: string; style_fa?: string | null };
  return n.set && n.voice ? { company: COMPANY, voice: n.voice, voice_fa: n.voice, style_fa: n.style_fa?.trim() ? n.style_fa : null } : null;
}
const teamOf = async (req: Request, next: Next) => ({ seats: seats.map((s) => ({ ...s })), narrator: await narratorOf(req, next) });

// ============================================================================================ §57.6 the revised notes ==
const PRODUCER = { code: 'PC-SCRIPT-01', company: COMPANY, kind: 'employee', department: 'MEDIA', title_fa: 'نویسنده‌ی ریلز پرو-چارت' };
type Out = { title: string; summary: string; file: { id: string; name: string; mime: string; size: number }; at: number; revision_of?: string; own?: boolean };
const OUTS: Record<string, Out> = {
  'O-000581': { title: 'یادداشت‌های سناریو', summary: 'سناریوی ریلز واگرایی در RSI، صحنه به صحنه.', at: 140, file: { id: '/demo/archive/charting-license-2026.pdf?notes=1', name: 'rsi-divergence-notes.pdf', mime: 'application/pdf', size: 48_210 } },
  'O-000582': { title: 'نسخه‌ی تازه‌ی یادداشت‌های سناریو', summary: 'صحنه‌ی دوم کوتاه‌تر شد.', at: 70, revision_of: 'O-000581', file: { id: '/demo/archive/charting-license-2026.pdf?notes=2', name: 'rsi-divergence-notes-v2.pdf', mime: 'application/pdf', size: 49_870 } },
  // the newest names its earlier one on the deliverable itself (and in the report's line): the apps read it either way
  'O-000583': { title: 'نسخه‌ی تازه‌ی یادداشت‌های سناریو', summary: 'پایان با شعار پرو-چارت.', at: 12, revision_of: 'O-000582', own: true, file: { id: '/demo/archive/charting-license-2026.pdf?notes=3', name: 'rsi-divergence-notes-v3.pdf', mime: 'application/pdf', size: 50_115 } },
  'O-000584': { title: 'متن گوینده', summary: 'متن ۳۵ ثانیه‌ای گوینده.', at: 40, file: { id: '/demo/archive/charting-license-2026.pdf?voice=1', name: 'voiceover.pdf', mime: 'application/pdf', size: 21_400 } },
};
function deliverable(ref: string) {
  const o = OUTS[ref]!;
  const pw: Record<string, unknown> = { runtime: 'direct', files: 1, model: 'claude-opus-5-5', effort: 'high', ...(o.revision_of && !o.own ? { revision_of: o.revision_of } : {}) };
  return {
    id: `o-${ref.toLowerCase()}`, ref, company: COMPANY, work_id: null, work_ref: 'W-000341', producer: PRODUCER, title: o.title, summary: o.summary, body: `## خلاصه\n${o.summary}`,
    attachments: [o.file], evidence: [], produced_with: pw, usage: {}, rating: null, created_at: minsAgo(o.at), category: 'work', seen_at: null, filed_as: null,
    ...(o.revision_of && o.own ? { revision_of: o.revision_of } : {}),
  };
}

// ============================================================================================================ routes ==
/** §57; what is not its own goes on to [next]. */
export async function handle57(req: Request, p: string, next: Next): Promise<Response | null> {
  const m = req.method;
  const dv = /^\/deliverables\/(O-\d+)$/.exec(p);
  if (dv && OUTS[dv[1]!] && m === 'GET') return json(deliverable(dv[1]!));

  const t = /^\/orders\/(F-\d+)\/team(?:\/(hire)|\/([^/]+)\/(lines|say))?$/.exec(p);
  if (!t) return null;
  // A hub before §57, and every session of the demo but the one that has a team: the route is not there.
  if (t[1] !== REF || flag('hq.e2e.old57') === '1') return refuse(404, 'not_found', 'پیدا نشد.');
  seed();
  const q = new URL(req.url).searchParams;
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;
  const key = req.headers.get('Idempotency-Key') ?? '';

  if (!t[2] && !t[3] && m === 'GET') return json(await teamOf(req, next));

  if (t[2] === 'hire' && m === 'POST') {
    if (!UUID.test(key)) return refuse(422, 'validation_failed', 'کلید یکتا باید UUID باشد.');
    if (hired.has(key)) return json(await teamOf(req, next));
    const b = await body<{ role?: string }>();
    const i = seats.findIndex((s) => s.state === 'empty' && s.role === b.role);
    if (i < 0) return refuse(409, 'validation_failed', 'این جای این جلسه خالی نیست.', { role: 'an empty media seat of this session' });
    if (flag('hq.e2e.hire') === 'refuse') return refuse(409, 'envelope_full', 'پاکت این ماه برای یک نفر دیگر جا ندارد؛ سقف پاکت را بالا ببر یا یکی را کنار بگذار.');
    const who = HIRES[b.role!]!;
    seats[i] = filled(who.code, b.role!, seats[i]!.role_fa, who.title_fa);
    hired.set(key, true);
    return json(await teamOf(req, next));
  }

  const code = decodeURIComponent(t[3] ?? '');
  const seat = seats.find((s) => s.key === code && s.state !== 'empty');
  if (t[4] === 'lines' && m === 'GET') {
    if (!seat) return refuse(404, 'not_found', 'این آدم در این جلسه نیست.');
    const all = lines.get(code) ?? [];
    const before = q.get('before');
    const limit = Math.max(1, Math.min(200, Number(q.get('limit') ?? 50)));
    const end = before ? Math.max(0, all.findIndex((l) => l.id === before)) : all.length;
    const start = Math.max(0, end - limit);
    if (!before) seat.unread = 0;
    return json({ items: all.slice(start, end), next_cursor: start > 0 ? all[start]!.id : null });
  }
  if (t[4] === 'say' && m === 'POST') {
    if (!UUID.test(key)) return refuse(422, 'validation_failed', 'کلید یکتا باید UUID باشد.');
    const again = said.get(key);
    if (again) return json(again);
    if (seat?.holder) return refuse(409, 'validation_failed', 'با مسئول جلسه از همین جای نوشتن حرف بزن.');
    if (!seat || !seat.employee) return refuse(404, 'not_found', 'این آدم در این جلسه نیست.');
    const text = String((await body<{ text?: string }>()).text ?? '').replace(/\s+$/g, '').trim();
    if (!text) return refuse(422, 'validation_failed', 'حرفت را بنویس.', { text: 'the words' });
    const talk = lines.get(code) ?? [];
    const line: Line = { id: lineId(), at: NOW(), who: 'owner', who_fa: 'مدیر کل', text: text.slice(0, 4000), work_ref: 'W-000341' };
    talk.push(line);
    lines.set(code, talk);
    Object.assign(seat, { state: 'working', last: lastOf(line) });
    const out = { line, work_ref: 'W-000341', woken: true };
    said.set(key, out);
    // He answers in the side talk a moment later, as §57.4's `order.progress` would.
    setTimeout(() => {
      const answer: Line = { id: lineId(), at: NOW(), who: 'seat', who_fa: seat.employee!.title_fa, text: 'گرفتم؛ همین را اعمال میکنم و نتیجه را همین‌جا میگویم.', work_ref: 'W-000341' };
      talk.push(answer);
      Object.assign(seat, { last: lastOf(answer), unread: seat.unread + 1 });
    }, 1200);
    return json(out, 201);
  }
  return refuse(405, 'method_not_allowed', 'این کار این‌جا نیست.');
}
