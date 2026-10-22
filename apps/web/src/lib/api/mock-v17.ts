// Development-only fixtures for contract v1.5 §20 (governance), used by mock.ts. Never bundled in production (next.config aliases the
// fixtures module away). Companies are data here as on the hub: every list below is built from rows, nothing counts them. Rules the hub
// runs as code (the budget trim, claim checks, conflict rules, the batch eligibility, verdicts) are reduced to what a demo needs.

import { supportArticles } from './mock-v16';

const now = Date.now();
const MIN = 60_000;
const DAY = 86_400_000;
const iso = (minAgo: number) => new Date(now - minAgo * MIN).toISOString();
const ahead = (min: number) => new Date(now + min * MIN).toISOString();
const stamp = () => new Date().toISOString();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const page = (items: unknown[]) => ({ items, next_cursor: null });
const problem = (status: number, code: string, message_fa: string, extra: Record<string, unknown> = {}) =>
  json({ type: 'about:blank', title: code, status, code, message_fa, ...extra }, status);
const pad = (n: number, w: number) => String(n).padStart(w, '0');
const dateKey = (d: Date) => d.toISOString().slice(0, 10);
/** Deterministic 0..1, so every reload of the demo draws the same month. */
const noise = (seed: number, i: number) => { const x = Math.sin(seed * 9301 + i * 49297) * 233280; return x - Math.floor(x); };
const seedOf = (s: string) => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 9973, 7);
async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
/** Canonical JSON: keys sorted at every depth, no spaces (the hub's `body_sha256` and batch targets). */
const canonical = (v: unknown): string => {
  if (Array.isArray(v)) return `[${v.map(canonical).join(',')}]`;
  if (v && typeof v === 'object') return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${canonical((v as Record<string, unknown>)[k])}`).join(',')}}`;
  return JSON.stringify(v);
};
const unmatched = (req: Request, version: number) => {
  const m = req.headers.get('If-Match');
  if (!m) return problem(428, 'precondition_required', 'نسخه همراه درخواست نیامد.');
  if (m.replace(/"/g, '') !== String(version)) return problem(409, 'version_conflict', 'همین حالا عوض شده؛ دوباره نگاه کن.');
  return null;
};
const needsStepUp = (req: Request) => (req.headers.get('X-Step-Up') ? null : problem(403, 'step_up_required', 'این کار تأیید با اثر انگشت یا چهره میخواهد.'));

// ------------------------------------------------------------------------ actors --
const NAME: Record<string, string> = { HQ: 'هلدینگ', TY: 'تریدیار', FX: 'FX', PC: 'پرو-چارت' };
const OPERATING = ['TY', 'FX', 'PC'];
const owner = { kind: 'owner', code: 'owner', display_fa: 'مدیر کل' };
const system = { kind: 'system', code: 'system', display_fa: 'سیستم' };
const agent = (code: string, display_fa: string, kind = 'agent') => ({ kind, code, display_fa });
const ceo = (c: string) => agent(`${c}-CEO`, `مدیرعامل ${NAME[c]}`);
const tech = (c: string) => agent(`${c}-TECH-MGR`, `مدیر فنی ${NAME[c]}`);
const growthMgr = (c: string) => agent(`${c}-GROWTH-MGR`, `مدیر مارکتینگ ${NAME[c]}`);
const inspector = agent('HQ-OVS-MGR', 'بازرس کل');
const advisor = agent('HQ-ADV', 'مشاور کل');
const overseer = agent('HQ-OVR', 'ناظر کل', 'overseer');
const secretary = agent('HQ-SEC', 'منشی', 'system');
const aiops = agent('HQ-AIOPS-MGR', 'مدیر عملیات هوش مصنوعی');

// ====================================================================== meetings (§20.1) ==
const types: any[] = [
  { key: 'board', title_fa: 'هیئت‌مدیره‌ی هلدینگ', schedule: 'FREQ=WEEKLY;BYDAY=SA;BYHOUR=10', members: { roles: ['ceo', 'inspector', 'advisor'], companies: 'all' }, max_rounds: 2, max_speakers: 6, budget_tokens: 120_000, turn_cap_tokens: 6000, owner_presence: 'live', enabled: true, version: 3 },
  { key: 'company', title_fa: 'مدیریت هر شرکت', schedule: 'FREQ=WEEKLY;BYDAY=SA,SU,MO,TU,WE;BYHOUR=11', members: { roles: ['ceo', 'manager', 'inspector'], companies: 'concerned' }, max_rounds: 2, max_speakers: 6, budget_tokens: 40_000, turn_cap_tokens: 6000, owner_presence: 'summary', enabled: true, version: 2 },
  { key: 'standup', title_fa: 'استندآپ دپارتمان', schedule: 'FREQ=DAILY;BYHOUR=9', members: { roles: ['manager'], companies: 'concerned' }, max_rounds: 1, max_speakers: 2, budget_tokens: 0, turn_cap_tokens: 6000, owner_presence: 'summary', enabled: true, version: 1 },
  { key: 'war_room', title_fa: 'اتاق جنگ', schedule: null, members: { roles: ['ceo', 'manager', 'sre'], companies: 'concerned' }, max_rounds: 3, max_speakers: 8, budget_tokens: null, turn_cap_tokens: 6000, owner_presence: 'live', enabled: true, version: 1 },
  { key: 'postmortem', title_fa: 'کالبدشکافی', schedule: null, members: { roles: ['ceo', 'manager', 'sre', 'inspector'], companies: 'concerned' }, max_rounds: 1, max_speakers: 6, budget_tokens: 30_000, turn_cap_tokens: 6000, owner_presence: 'summary', enabled: true, version: 1 },
  { key: 'strategy', title_fa: 'استراتژی ماهانه', schedule: 'FREQ=MONTHLY;BYDAY=-1TH;BYHOUR=10', members: { roles: ['ceo', 'advisor', 'inspector'], companies: 'all' }, max_rounds: 2, max_speakers: 6, budget_tokens: 150_000, turn_cap_tokens: 6000, owner_presence: 'live', enabled: true, version: 2 },
];
const typeOf = (k: string) => types.find((t) => t.key === k);

const part = (actor: any, role_fa: string, speaker = true, devil = false) => ({ actor, role_fa, speaker, devil });
const item = (id: string, n: number, title_fa: string, brief_md: string, sources: any[], time_box_min: number, speakers: any[], state = 'waiting', round = 0) => ({ id, n, title_fa, brief_md, sources, time_box_min, speakers, round, state });
const src = (kind: string, ref: string, note = '') => ({ kind, ref, note });
const board = [ceo('FX'), ceo('TY'), ceo('PC'), inspector];

const meetings: any[] = [
  {
    ref: 'MT-0012', type: 'board', company: 'HQ', title_fa: 'هیئت‌مدیره‌ی هلدینگ', starts_at: iso(26), state: 'live', mode: 'discussion',
    budget: { cap: 120_000, estimate: 104_000, reserved: 120_000, used: 41_000 }, trimmed_fa: null, owner_presence: 'live', minutes: null, incident: null, version: 4, created_at: iso(60 * 24),
    participants: [part(ceo('FX'), 'مدیرعامل FX'), part(ceo('TY'), 'مدیرعامل تریدیار'), part(ceo('PC'), 'مدیرعامل پرو-چارت'), part(inspector, 'بازرس کل', true, true), part(advisor, 'مشاور کل', false)],
    items: [
      item('mi-12-1', 1, 'گزارش هفته‌ی شرکت‌ها', 'گزارش هفتگی هر شرکت، **با ارجاع به خروجی‌ها** و نه متن تازه.', [src('deliverable', 'O-000030', 'گزارش صبحگاهی'), src('deliverable', 'O-000031', 'سئوی فنی تریدیار')], 12, [ceo('TY'), ceo('FX'), ceo('PC'), inspector], 'done', 1),
      item('mi-12-2', 2, 'انتشار اصلاح کندی ثبت‌نام FX: امروز یا شنبه؟', 'اصلاح روی شاخه‌ی `hq/S-0004` آماده است (ایندکس یکتا روی ایمیل). پرسش: امروز با canary، یا شنبه بعد از فریز؟', [src('work', 'W-000104', 'رفع کندی ثبت‌نام'), src('code_session', 'S-0004', 'جلسه‌ی کارگاه کد')], 10, board, 'round_1', 1),
      item('mi-12-3', 3, 'بودجه‌ی آبان', 'سقف توکن هر شرکت برای ماه بعد، از روی مصرف مهر و درآمد.', [src('treasury', 'treasury.month', 'خزانه‌ی توکن، مهر')], 10, board),
      item('mi-12-4', 4, 'پیشنهادهای رشد (سه دسته)', 'پیشنهادهای رشد در انتظار، دسته‌بندی‌شده به کم‌هزینه، آزمایشی و سنگین.', [src('decision', 'D-000035', 'پیشنهاد تریدیار')], 15, [ceo('TY'), ceo('FX'), ceo('PC'), inspector]),
    ],
    drafts: [{ id: 'dr-12-2', meeting: 'MT-0012', item: 'mi-12-2', text_md: 'انتشار امروز ساعت 14، با canary 10٪ و بازگشت خودکار؛ گزارش به هیئت ساعت 18.', proposer: ceo('FX'), votes: { support: 0, oppose: 0, abstain: 0 }, decision: null }],
  },
  {
    ref: 'MT-0013', type: 'company', company: 'TY', title_fa: 'مدیریت تریدیار', starts_at: ahead(60 * 20 + 14), state: 'prep', mode: 'discussion',
    budget: { cap: 40_000, estimate: 39_200, reserved: 0, used: 0 }, owner_presence: 'summary', minutes: null, incident: null, version: 2, created_at: iso(60 * 3),
    trimmed_fa: 'برآورد اول 46K بود و از بودجه‌ی 40K بیشتر شد؛ طبق قاعده دور دوم دستور ۴ (کم‌اهمیت‌ترین) حذف شد.',
    participants: [part(ceo('TY'), 'مدیرعامل تریدیار'), part(growthMgr('TY'), 'مدیر مارکتینگ تریدیار'), part(tech('TY'), 'مدیر فنی تریدیار'), part(inspector, 'بازرس کل', true, true)],
    items: [
      item('mi-13-1', 1, 'گزارش هفتگی تریدیار', 'گزارش هفته با ارجاع به خروجی‌ها.', [src('deliverable', 'O-000031')], 10, [ceo('TY'), inspector]),
      item('mi-13-2', 2, 'OKR فصل: نرخ حداقل موجودی', 'پیشرفت KR-0007 و check-in دیرکرده‌ی KR-0008.', [src('okr', 'OB-0003'), src('okr', 'KR-0007')], 10, [ceo('TY'), growthMgr('TY'), inspector]),
      item('mi-13-3', 3, 'ریسک‌های باز بالای 15', 'RK-0002 (وابستگی به یک صرافی) راه کاهش ندارد و بازبینی‌اش گذشته است.', [src('risk', 'RK-0002'), src('risk', 'RK-0003')], 8, [ceo('TY'), tech('TY'), inspector]),
      item('mi-13-4', 4, 'پیشنهاد رشد: پیام راهنمای حداقل موجودی', 'پیشنهاد D-000035 که در کارتابل است.', [src('decision', 'D-000035')], 8, [ceo('TY'), growthMgr('TY'), inspector]),
    ],
    drafts: [],
  },
  {
    ref: 'MT-0014', type: 'postmortem', company: 'FX', title_fa: 'کالبدشکافی حادثه‌ی سرور سیگنال', starts_at: ahead(60 * 22 + 31), state: 'scheduled', mode: 'discussion',
    budget: { cap: 30_000, estimate: 22_000, reserved: 0, used: 0 }, trimmed_fa: null, owner_presence: 'summary', minutes: null, incident: 'I-0009', version: 1, created_at: iso(60 * 20),
    participants: [part(ceo('FX'), 'مدیرعامل FX'), part(tech('FX'), 'مدیر فنی FX'), part(agent('FX-TECH-03', 'SRE کوینه‌پرو FX'), 'SRE'), part(inspector, 'بازرس کل', true, true)],
    items: [
      item('mi-14-1', 1, 'خط زمانی و علت ریشه‌ای', 'خط زمانی را کد از checkها، حادثه و audit ساخته است.', [src('incident', 'I-0009'), src('meeting', 'MT-0010')], 15, [tech('FX'), agent('FX-TECH-03', 'SRE کوینه‌پرو FX'), inspector]),
      item('mi-14-2', 2, 'اقدام‌ها و ریسک‌ها', 'هر اقدام یک پیش‌نویس کار؛ ریسک‌ها با risk.raise.', [src('risk', 'RK-0001')], 10, [ceo('FX'), tech('FX'), inspector]),
    ],
    drafts: [],
  },
  {
    ref: 'MT-0015', type: 'company', company: 'FX', title_fa: 'مدیریت کوینه‌پرو FX', starts_at: ahead(60 * 24 * 2 + 40), state: 'scheduled', mode: 'written',
    budget: { cap: 40_000, estimate: 6_000, reserved: 0, used: 0 }, owner_presence: 'summary', minutes: null, incident: null, version: 1, created_at: iso(60 * 2),
    trimmed_fa: 'سهم روزانه‌ی جلسه‌ها برای آن روز پر است؛ جلسه نوشتاری برگزار میشود: فقط بیانیه‌های نوشته‌شده، بی‌دور بحث.',
    participants: [part(ceo('FX'), 'مدیرعامل FX'), part(agent('FX-QUANT-MGR', 'مدیر کوانت FX'), 'مدیر کوانت FX'), part(inspector, 'بازرس کل', true, true)],
    items: [
      item('mi-15-1', 1, 'گزارش هفتگی FX', 'گزارش هفته با ارجاع به خروجی‌ها.', [src('deliverable', 'O-000029')], 10, [ceo('FX')]),
      item('mi-15-2', 2, 'OKR: دقت سیگنال طلا', 'KR-0010 به هدف رسید؛ KR-0011 منتظر انتشار اصلاح ثبت‌نام است.', [src('okr', 'OB-0004')], 10, [ceo('FX'), agent('FX-QUANT-MGR', 'مدیر کوانت FX')]),
    ],
    drafts: [],
  },
  {
    ref: 'MT-0016', type: 'strategy', company: 'HQ', title_fa: 'استراتژی ماهانه', starts_at: ahead(60 * 24 * 8 + 15), state: 'scheduled', mode: 'discussion',
    budget: { cap: 150_000, estimate: 132_000, reserved: 0, used: 0 }, trimmed_fa: null, owner_presence: 'live', minutes: null, incident: null, version: 1, created_at: iso(60 * 5),
    participants: [part(ceo('TY'), 'مدیرعامل تریدیار'), part(ceo('FX'), 'مدیرعامل FX'), part(ceo('PC'), 'مدیرعامل پرو-چارت'), part(advisor, 'مشاور کل'), part(inspector, 'بازرس کل', true, true)],
    items: [
      item('mi-16-1', 1, 'هدف‌های ماه بعد', 'پیش‌نویس هدف‌های آبان برای هر شرکت، از روی OKR و کارت‌ها.', [src('okr', 'OB-0003'), src('okr', 'OB-0004')], 20, [ceo('TY'), ceo('FX'), ceo('PC'), advisor, inspector]),
      item('mi-16-2', 2, 'دفتر ریسک هلدینگ', 'ریسک‌های بالای 15 و پذیرش‌هایی که تا ماه بعد تمام میشوند.', [src('risk', 'RK-0002'), src('risk', 'RK-0005')], 15, [advisor, inspector]),
    ],
    drafts: [],
  },
  {
    ref: 'MT-0011', type: 'board', company: 'HQ', title_fa: 'هیئت‌مدیره‌ی هلدینگ', starts_at: iso(60 * 24 * 7 + 30), state: 'ended', mode: 'discussion',
    budget: { cap: 120_000, estimate: 98_000, reserved: 120_000, used: 74_000 }, trimmed_fa: null, owner_presence: 'live', incident: null, version: 9, created_at: iso(60 * 24 * 8),
    minutes: {
      deliverable: 'O-000028',
      summary_md: '**چهار دستور، دو دور.** فقط ادعاهای منبع‌دار در این خلاصه‌اند.\n\n- گزارش هفته: درآمد رفرال هلدینگ 6٪ بالاتر از هفته‌ی قبل (O-000030).\n- پشتیبانی تلگرام تریدیار آزمون سایه را با 93٪ درست گذراند؛ کارت go-live در کارتابل است (D-000032).\n- پیش‌نویس «کالبدشکافی هر حادثه تا 24 ساعت» با 3 رأی موافق و 1 ممتنع به کارتابل رفت (D-000034).\n- یک ادعا درباره‌ی سهم بازار FX منبع نداشت و بیرون از صورت‌جلسه ماند.',
    },
    participants: [part(ceo('TY'), 'مدیرعامل تریدیار'), part(ceo('FX'), 'مدیرعامل FX'), part(ceo('PC'), 'مدیرعامل پرو-چارت'), part(inspector, 'بازرس کل', true, true), part(advisor, 'مشاور کل', false)],
    items: [
      item('mi-11-1', 1, 'گزارش هفته‌ی شرکت‌ها', 'گزارش هفتگی هر شرکت.', [src('deliverable', 'O-000030')], 12, [ceo('TY'), ceo('FX'), ceo('PC'), inspector], 'done', 1),
      item('mi-11-2', 2, 'پشتیبانی تلگرام تریدیار', 'نتیجه‌ی آزمون سایه و کارت go-live.', [src('decision', 'D-000032')], 10, [ceo('TY'), inspector], 'done', 1),
      item('mi-11-3', 3, 'کالبدشکافی حادثه‌ها', 'هر حادثه‌ی بسته‌شده تا کی کالبدشکافی میشود؟', [src('incident', 'I-0005')], 10, [ceo('TY'), ceo('FX'), ceo('PC'), inspector], 'done', 2),
      item('mi-11-4', 4, 'سهم بازار FX', 'برآورد سهم بازار سیگنال فارسی.', [], 8, [ceo('FX'), inspector], 'skipped', 0),
    ],
    drafts: [
      { id: 'dr-11-3', meeting: 'MT-0011', item: 'mi-11-3', text_md: 'هر حادثه‌ی بسته‌شده تا 24 ساعت بعد کالبدشکافی میشود؛ اقدام‌ها کار پیش‌نویس و ریسک‌ها در دفتر ریسک ثبت میشوند.', proposer: inspector, votes: { support: 3, oppose: 0, abstain: 1 }, decision: 'D-000034' },
    ],
  },
  {
    ref: 'MT-0010', type: 'war_room', company: 'FX', title_fa: 'اتاق جنگ کوینه‌پرو FX', starts_at: iso(60 * 21 + 14), state: 'ended', mode: 'discussion',
    budget: { cap: null, estimate: 0, reserved: 0, used: 6_000 }, trimmed_fa: null, owner_presence: 'live', incident: 'I-0009', version: 6, created_at: iso(60 * 21 + 14),
    minutes: { deliverable: 'O-000032', summary_md: 'سرور سیگنال FX به خاطر **پر شدن دیسک لاگ** 14 دقیقه از دسترس بیرون بود. مهار با پاک‌سازی لاگ قدیمی و تأیید تو (A3) انجام شد. کالبدشکافی فردا ساعت 10:00 (MT-0014).' },
    participants: [part(ceo('FX'), 'مدیرعامل FX'), part(tech('FX'), 'مدیر فنی FX'), part(agent('FX-TECH-02', 'مدیر برنامه‌نویسی FX'), 'مدیر برنامه‌نویسی'), part(agent('FX-TECH-03', 'SRE کوینه‌پرو FX'), 'SRE')],
    items: [item('mi-10-1', 1, 'مهار حادثه‌ی I-0009', 'سرور سیگنال جواب نمیدهد.', [src('incident', 'I-0009')], 30, [tech('FX'), agent('FX-TECH-03', 'SRE کوینه‌پرو FX'), ceo('FX')], 'done', 1)],
    drafts: [],
  },
  {
    ref: 'MT-0009', type: 'company', company: 'PC', title_fa: 'مدیریت پرو-چارت', starts_at: iso(60 * 24 * 3 + 50), state: 'ended', mode: 'discussion',
    budget: { cap: 40_000, estimate: 31_000, reserved: 40_000, used: 26_000 }, trimmed_fa: null, owner_presence: 'summary', incident: null, version: 5, created_at: iso(60 * 24 * 4),
    minutes: { deliverable: 'O-000027', summary_md: 'ترمینال تازه با 286 تست سبز آماده‌ی انتشار است (D-000017). pull درآمد پرو-چارت دو بار شکست خورد؛ IP هاب در whitelist افیلیت نیست (RK-0005، پذیرفته‌شده تا 60 روز).' },
    participants: [part(ceo('PC'), 'مدیرعامل پرو-چارت'), part(tech('PC'), 'مدیر فنی پرو-چارت'), part(inspector, 'بازرس کل', true, true)],
    items: [
      item('mi-9-1', 1, 'انتشار ترمینال', 'آمادگی انتشار.', [src('decision', 'D-000017')], 10, [tech('PC'), inspector], 'done', 1),
      item('mi-9-2', 2, 'pull درآمد', 'خطای whitelist.', [src('risk', 'RK-0005')], 8, [ceo('PC'), inspector], 'done', 1),
    ],
    drafts: [],
  },
].map((m, i) => ({ id: `mt${i}`, ...m }));

type T = { speaker: any; kind: string; statement_md: string; claims?: any[]; draft_md?: string | null; stance?: any; tokens: number; at: number; round?: number };
const claim = (id: string, text_fa: string, source: { kind: string; ref: string } | null, status = source ? 'sourced' : 'unsourced') => ({ id, text_fa, source, status });
const turnsOf = (meeting: string, itemId: string, xs: T[], start: number) => xs.map((t, k) => ({
  id: `${meeting}-t${start + k}`, meeting, item: itemId, n: start + k, round: t.round ?? 1, speaker: t.speaker, kind: t.kind, statement_md: t.statement_md,
  claims: t.claims ?? [], draft_md: t.draft_md ?? null, stance: t.stance ?? null, run_id: t.kind === 'owner' ? null : `run-${meeting}-${start + k}`, tokens: t.tokens, at: iso(t.at),
}));
const turns: any[] = [
  ...turnsOf('MT-0012', 'mi-12-1', [
    { speaker: ceo('TY'), kind: 'statement', statement_md: 'درآمد رفرال تریدیار این هفته 8٪ بالاتر بود و 41 کار تمام شد.', claims: [claim('c1', 'درآمد رفرال هفته 8٪ بالاتر', { kind: 'revenue', ref: 'revenue.week.TY' }), claim('c2', '41 کار تمام شد', { kind: 'deliverable', ref: 'O-000030' })], tokens: 4100, at: 25 },
    { speaker: ceo('FX'), kind: 'statement', statement_md: 'دقت ۷ روزه‌ی سیگنال طلا بعد از فیلتر رژیم نوسان به 68٪ برگشت.', claims: [claim('c3', 'دقت ۷ روزه 68٪', { kind: 'deliverable', ref: 'O-000029' })], tokens: 3800, at: 22 },
    { speaker: ceo('PC'), kind: 'statement', statement_md: 'ترمینال تازه با 286 تست سبز آماده‌ی انتشار است؛ کارتش در کارتابل است.', claims: [claim('c4', '286 تست سبز', { kind: 'decision', ref: 'D-000017' })], tokens: 3600, at: 19 },
    { speaker: inspector, kind: 'challenge', statement_md: 'عدد 8٪ درآمد با رادار درآمد میخواند. ادعای بی‌منبعی در این دستور نبود.', claims: [], tokens: 2900, at: 16 },
  ], 1),
  ...turnsOf('MT-0012', 'mi-12-2', [
    { speaker: ceo('FX'), kind: 'statement', statement_md: 'تست‌ها و دروازه‌ی بصری پاس شده‌اند. هر روز تأخیر حدود 90 ثبت‌نام کم میکند.', claims: [claim('c5', '46 تست ثبت‌نام سبز است', { kind: 'code_session', ref: 'S-0004' }), claim('c6', 'هر روز تأخیر حدود 90 ثبت‌نام کم میکند', { kind: 'metric', ref: 'funnel.signup.FX' })], draft_md: 'انتشار امروز ساعت 14، با canary 10٪ و بازگشت خودکار؛ گزارش به هیئت ساعت 18.', tokens: 5200, at: 4 },
    { speaker: ceo('TY'), kind: 'statement', statement_md: 'ثبت‌نام تریدیار هم از همین سرویس مشترک است؛ 12٪ از کندی سهم ما بوده.', claims: [claim('c7', '12٪ از کندی سهم تریدیار بوده', null)], tokens: 3100, at: 2.5 },
  ], 5),
  ...turnsOf('MT-0011', 'mi-11-3', [
    { speaker: inspector, kind: 'statement', statement_md: 'دو حادثه‌ی ماه گذشته هیچ‌وقت کالبدشکافی نشدند و یکی تکرار شد.', claims: [claim('c11', 'حادثه‌ی I-0005 تکرار I-0002 بود', { kind: 'incident', ref: 'I-0005' })], draft_md: 'هر حادثه‌ی بسته‌شده تا 24 ساعت بعد کالبدشکافی میشود؛ اقدام‌ها کار پیش‌نویس و ریسک‌ها در دفتر ریسک ثبت میشوند.', tokens: 4300, at: 60 * 24 * 7 + 5 },
    { speaker: ceo('FX'), kind: 'statement', statement_md: 'موافقم؛ سهم بازار سیگنال فارسی ما هم حدود 30٪ است و این اعتبار را باید نگه داریم.', claims: [claim('c12', 'سهم بازار سیگنال فارسی FX حدود 30٪', null)], tokens: 3500, at: 60 * 24 * 7 + 3 },
    { speaker: inspector, kind: 'challenge', statement_md: 'سهم بازار 30٪ منبع ندارد؛ وارد صورت‌جلسه نمیشود.', claims: [], tokens: 2100, at: 60 * 24 * 7 + 2 },
    { speaker: ceo('TY'), kind: 'vote', round: 2, statement_md: 'موافق.', stance: { draft: 'dr-11-3', vote: 'support', reason_fa: 'تکرار حادثه هزینه‌ی واقعی داشت.' }, tokens: 900, at: 60 * 24 * 7 + 1 },
    { speaker: ceo('FX'), kind: 'vote', round: 2, statement_md: 'موافق.', stance: { draft: 'dr-11-3', vote: 'support', reason_fa: 'با اتاق جنگ جور است.' }, tokens: 800, at: 60 * 24 * 7 + 0.8 },
    { speaker: ceo('PC'), kind: 'vote', round: 2, statement_md: 'ممتنع.', stance: { draft: 'dr-11-3', vote: 'abstain', reason_fa: 'پرو-چارت هنوز SRE ندارد.' }, tokens: 700, at: 60 * 24 * 7 + 0.6 },
    { speaker: inspector, kind: 'vote', round: 2, statement_md: 'موافق.', stance: { draft: 'dr-11-3', vote: 'support', reason_fa: 'PR-091 همین را میسنجد.' }, tokens: 600, at: 60 * 24 * 7 + 0.4 },
  ], 1),
  ...turnsOf('MT-0010', 'mi-10-1', [
    { speaker: system, kind: 'statement', statement_md: 'سه health check پشت هم رد شد؛ حادثه‌ی I-0009 با شدت sev1 باز شد.', claims: [claim('c21', 'سه check پشت هم رد شد', { kind: 'incident', ref: 'I-0009' })], tokens: 0, at: 60 * 21 + 14 },
    { speaker: system, kind: 'statement', statement_md: 'اتاق جنگ خودکار باز شد؛ 4 نفر دعوت شدند.', claims: [], tokens: 0, at: 60 * 21 + 14 },
    { speaker: tech('FX'), kind: 'statement', statement_md: 'علت: پر شدن دیسک لاگ روی سرور سیگنال.', claims: [claim('c22', 'دیسک لاگ 100٪ پر بود', { kind: 'metric', ref: 'node.disk.fx-signal' })], tokens: 5100, at: 60 * 21 + 10 },
    { speaker: tech('FX'), kind: 'statement', statement_md: 'مهار: پاک‌سازی لاگ قدیمی با تأیید تو (A3).', claims: [claim('c23', 'پاک‌سازی با مُهر مالک', { kind: 'audit', ref: 'audit:1188' })], tokens: 4200, at: 60 * 21 + 6 },
    { speaker: agent('FX-TECH-03', 'SRE کوینه‌پرو FX'), kind: 'statement', statement_md: 'سرویس برگشت؛ پایش 30 دقیقه.', claims: [claim('c24', 'سه check پشت هم سبز', { kind: 'incident', ref: 'I-0009' })], tokens: 2600, at: 60 * 21 },
  ], 1),
];
const whispers: any[] = [
  { id: 'wh-12-1', meeting: 'MT-0012', item: 'mi-12-1', text_md: 'عددهای این دستور همه منبع دارند؛ چیزی برای نگرانی نیست.', sources: [src('deliverable', 'O-000030')], at: iso(15) },
  { id: 'wh-12-2', meeting: 'MT-0012', item: 'mi-12-2', text_md: 'حرف بازرس درست است؛ ساعت 14 کم‌بارترین ساعت ثبت‌نام FX است (میانگین 8 ثبت‌نام).', sources: [src('metric', 'funnel.signup.FX.hourly', 'میانگین 4 هفته')], at: iso(1.5) },
];
// What the live demo reveals next, one turn per poll after a pause (the hub runs these as agent runs).
const script: Record<string, any[]> = {
  'MT-0012': [
    { item: 'mi-12-2', speaker: ceo('PC'), kind: 'statement', statement_md: 'پرو-چارت از این سرویس استفاده نمیکند؛ موافق انتشار در ساعت کم‌بارم.', claims: [], tokens: 2400 },
    { item: 'mi-12-2', speaker: inspector, kind: 'challenge', statement_md: 'اگر canary شکست بخورد، بازگشت خودکار تا 4 دقیقه طول میکشد؛ در آن مدت ثبت‌نام قطع است. پیشنهاد: ساعت کم‌بار. عدد 12٪ تریدیار منبع ندارد و تا منبع نیاید در مصوبه نمیاید.', claims: [claim('c8', 'بازگشت خودکار تا 4 دقیقه', { kind: 'decision', ref: 'D-000017' })], tokens: 2900, challenge: 'c7' },
  ],
};
let lastReveal = now;
const keys = new Map<string, { status: number; body: unknown }>();
const seq = { mt: 17, turn: 100, decision: 36, resolution: 13, batch: 1, deliverable: 33 };

const current = (m: any) => m.items.find((x: any) => x.state === 'round_1' || x.state === 'round_2') ?? null;
const meetingOut = (m: any) => {
  // `budget.used` holds what the demo spent before its recorded turns; the turns add theirs.
  const used = m.budget.used + turns.filter((t) => t.meeting === m.ref).reduce((a, t) => a + t.tokens, 0);
  return { ...m, budget: { ...m.budget, used: m.state === 'scheduled' || m.state === 'prep' ? 0 : used } };
};
function addTurn(m: any, t: any) {
  const it = m.items.find((x: any) => x.id === t.item) ?? current(m);
  const out = { id: `${m.ref}-t${++seq.turn}`, meeting: m.ref, item: it?.id ?? null, n: turns.filter((x) => x.meeting === m.ref).length + 1, round: it?.round ?? 1, speaker: t.speaker, kind: t.kind,
    statement_md: t.statement_md, claims: t.claims ?? [], draft_md: t.draft_md ?? null, stance: t.stance ?? null, run_id: t.kind === 'owner' ? null : `run-${seq.turn}`, tokens: t.tokens ?? 0, at: stamp() };
  turns.push(out);
  if (t.challenge) for (const x of turns) for (const c of x.claims) if (c.id === t.challenge && c.status === 'unsourced') c.status = 'challenged';
  if (out.stance) { const d = m.drafts.find((x: any) => x.id === out.stance.draft); if (d) d.votes[out.stance.vote] += 1; }
  m.version += 1;
  return out;
}
function nextItem(m: any) {
  const nx = [...m.items].sort((a, b) => a.n - b.n).find((x: any) => x.state === 'waiting');
  if (nx) Object.assign(nx, { state: 'round_1', round: 1 });
}
/** Closing: the minutes from sourced claims only, and each draft a `meeting_resolution` card for the owner's seal. */
function endMeeting(m: any, decisions: any[]) {
  for (const it of m.items) if (it.state === 'round_1' || it.state === 'round_2') it.state = 'done'; else if (it.state === 'waiting') it.state = 'skipped';
  const sourced = turns.filter((t) => t.meeting === m.ref).flatMap((t) => t.claims.filter((c: any) => c.status === 'sourced').map((c: any) => `- ${c.text_fa} (${c.source.ref})`));
  m.minutes = { deliverable: `O-0000${seq.deliverable++}`, summary_md: `**${m.items.filter((x: any) => x.state === 'done').length} دستور بررسی شد.** فقط ادعاهای منبع‌دار:\n\n${sourced.slice(0, 6).join('\n') || '- ادعای منبع‌داری ثبت نشد.'}` };
  for (const d of m.drafts) {
    if (d.decision) continue;
    const ref = `D-0000${seq.decision++}`;
    d.decision = ref;
    decisions.unshift(card({ id: `d-${ref}`, ref, kind: 'meeting_resolution', company: m.company, risk: 'low', title: d.text_md.replace(/[؛.].*$/, '').slice(0, 80), proposer: d.proposer, created_at: stamp(), expires_at: ahead(60 * 24 * 5),
      what: d.text_md, why: `پیش‌نویس دستور «${m.items.find((x: any) => x.id === d.item)?.title_fa ?? ''}» در ${m.ref}؛ فقط ادعاهای منبع‌دار همراه کارت است.`, risk_note: null, quota_estimate: { tokens: 8000, usd: '0.15' },
      payload: { meeting: m.ref, item: d.item, text_md: d.text_md, votes: d.votes, claims: turns.filter((t) => t.meeting === m.ref && t.item === d.item).flatMap((t) => t.claims.filter((c: any) => c.status === 'sourced')) } }));
  }
  m.state = 'ended';
}

// ====================================================================== charter (§20.2) ==
const HOLDING_BODY = `# اساسنامه‌ی هلدینگ کوینه‌پرو

نسخه‌ی ۱، مُهر مدیر کل. همه‌ی ایجنت‌ها آن را میخوانند و هیچ ایجنتی آن را نمینویسد.

## ۱. ما کی هستیم
کوینه‌پرو یک هلدینگ است که شرکت‌هایش در بازار رمزارز و فارکس به کاربرهای فارسی‌زبان خدمت میدهند. مدیر کل تصمیم میگیرد؛ ایجنت‌ها کار را با کیفیت، با شاهد و در اختیاری که به آن‌ها داده شده انجام میدهند. شرکت‌ها داده‌اند و تعدادشان ثابت نیست. هر قاعده‌ای در این سند برای هر تعداد شرکت درست است.

## ۲. ارزش‌ها
1. **راستی با شاهد.** هر ادعا منبع دارد. چیزی را که نمیدانیم، میگوییم نمیدانیم. حدس را با واقعیت قاطی نمیکنیم.
2. **امانت‌داری.** پول کاربر، داده‌ی کاربر و اعتماد مالک امانت است.
3. **خشت اول.** کیفیت پایه از سرعت مهم‌تر است. کار نیمه‌کاره یا سرسری تحویل داده نمیشود.
4. **صرفه‌جویی.** هر توکن پول هلدینگ است: اول قاعده، آخر هوش مصنوعی.
5. **شفافیت.** هر اقدام ثبت میشود و قابل پیگیری است. اشتباه را زود و روشن گزارش میکنیم.
6. **احترام.** به کاربر، به همکار و به رقیب.

## ۳. لحن برند (فارسی)
- فارسی روان و درست، گرم و محترمانه، با «شما». کوتاه و دقیق؛ اول جواب، بعد توضیح.
- بی‌اغراق و بی‌هیجان‌سازی: نه «فرصت طلایی»، نه «آخرین شانس»، نه وعده.
- عدد بازار با رقم لاتین، شمارش در متن با رقم فارسی؛ هر عدد با منبع و زمانش.
- هشدار ریسک روشن و بی‌پرده است.

## ۴. اولویت‌ها (به ترتیب)
1. **پایداری:** سرویس‌ها سالم، داده امن، backup و بازیابی آزموده.
2. **درآمد:** پشتیبانی درست و سریع، رفرال درست (کد و لینک رفرال فقط از دانشنامه‌ی تأییدشده).
3. **رشد:** سئو، محتوا و محصول، فقط وقتی دو اولویت بالا سالم‌اند.

## ۵. خطوط قرمز
این چهار خط هیچ استثنایی ندارند. نقض هرکدام یک یافته‌ی ناظر است، و متنی که به مشتری میرود پیش از ارسال نگه داشته میشود.

این‌ها هم همیشه برقرارند: **A3** فقط با مُهر مالک؛ **A4** هرگز. پشتیبانی هیچ‌وقت کلید، رمز، seed phrase یا کد تأیید نمیخواهد. کسی که پیشنهاد میدهد، همان کار را تأیید نمیکند.

## ۶. این سند چطور کار میکند
- یک سند هلدینگ، و هر شرکت میتواند یک الحاقیه داشته باشد که با این سند تعارض نکند.
- فقط مالک سند و الحاقیه‌ها را تغییر میدهد؛ هر تغییر نسخه‌ی تازه است و مُهر مالک را میخواهد.
- ایجنت‌ها اصلاحیه را فقط پیشنهاد میدهند: مدیرعامل برای الحاقیه‌ی شرکت خودش، ناظر و مشاور برای سند هلدینگ.`;
const HOLDING_RED: any[] = [
  { key: 'no_guaranteed_profit', text_fa: 'هیچ‌وقت به کاربر وعده‌ی سود قطعی داده نمیشود.', check: 'rule', patterns: ['سود\\s*(?:ی\\s*)?(?:قطعی|تضمینی|تضمین[\\s‌]*شده|حتمی|بی[\\s‌]*ریسک|بدون\\s+ریسک)', 'بدون\\s+(?:هیچ\\s+)?(?:ضرر|زیان|ریسک)', '(?:صد|۱۰۰|100)\\s*(?:درصد|٪|%)\\s*(?:سود|برد|تضمین)', '(?i)guaranteed\\s+(?:profit|return|gain)s?', '(?i)risk[\\s-]*free\\s+(?:profit|return|trading)'] },
  { key: 'no_data_out', text_fa: 'هیچ داده‌ی داخلی یا اطلاعات کاربرها بیرون نمیرود.', check: 'rule', patterns: null },
  { key: 'no_disparaging_competitors', text_fa: 'درباره‌ی رقبا هیچ‌وقت حرف بد زده نمیشود.', check: 'sample', patterns: null },
  { key: 'no_unsourced_figures', text_fa: 'هیچ عددی بدون منبع گفته نمیشود.', check: 'sample', patterns: null },
];
const TY_V1 = `# الحاقیه‌ی تریدیار

## مشتری‌های ما
کاربرهای تریدیار بیشتر تازه‌کارهای بازار رمزارزند. جواب‌ها ساده، گام‌به‌گام و بی‌اصطلاح است.

## رفرال
- کد و لینک رفرال فقط از دانشنامه‌ی تأییدشده.
- حداقل موجودی VIP همان عدد دانشنامه است (KB-0003).`;
const TY_V2 = `${TY_V1}

## پشتیبانی
- جواب کارمزد برداشت فقط با لینک صفحه‌ی کارمزد صرافی؛ عدد کارمزد از ما گفته نمیشود.
- بین ساعت 22 تا 9 فقط پاسخ انتظار میرود.`;
const TY_RED = [{ key: 'ty_no_trade_advice', text_fa: 'به کاربر تریدیار توصیه‌ی خرید و فروش داده نمیشود.', check: 'rule', patterns: ['(?:حتما|حتماً)\\s+(?:بخر|بفروش|بخرید|بفروشید)', 'سیگنال\\s+خرید\\s+قطعی'] }];
const FX_V1 = `# الحاقیه‌ی کوینه‌پرو FX

## سیگنال‌ها
- هر سیگنال با حد ضرر منتشر میشود؛ سیگنال بی‌حد ضرر منتشر نمیشود.
- دقت سیگنال‌ها فقط از گزارش ۷ روزه‌ی کوانت گفته میشود، با تاریخ.
- در ساعت انتشار خبرهای مهم اقتصادی آمریکا سیگنال تازه صادر نمیشود.

## لحن
هشدار ریسک فارکس در هر پیام تبلیغاتی میاید: معامله با اهرم ریسک بالایی دارد و ممکن است سرمایه از دست برود.`;
const FX_RED = [{ key: 'fx_stop_loss', text_fa: 'هیچ سیگنالی بدون حد ضرر منتشر نمیشود.', check: 'sample', patterns: null }];
const charters: any[] = [
  { scope: 'holding', version: 1, status: 'sealed', body_md: HOLDING_BODY, red_lines: HOLDING_RED, created_by: owner, created_at: iso(60 * 24 * 4), sealed_by: owner, sealed_at: iso(60 * 24 * 3) },
  { scope: 'TY', version: 1, status: 'superseded', body_md: TY_V1, red_lines: [], created_by: owner, created_at: iso(60 * 24 * 3), sealed_by: owner, sealed_at: iso(60 * 24 * 3 - 30) },
  { scope: 'TY', version: 2, status: 'sealed', body_md: TY_V2, red_lines: TY_RED, created_by: ceo('TY'), created_at: iso(60 * 24 * 2), sealed_by: owner, sealed_at: iso(60 * 24 * 2 - 90) },
  { scope: 'FX', version: 1, status: 'proposed', body_md: FX_V1, red_lines: FX_RED, created_by: owner, created_at: iso(60 * 9), sealed_by: null, sealed_at: null },
].map((c) => ({ body_sha256: '', ...c }));
const fillSha = async (c: any) => { if (!c.body_sha256) c.body_sha256 = await sha256(canonical({ body_md: c.body_md, red_lines: c.red_lines })); return c; };
const vref = (c: any) => ({ version: c.version, status: c.status, created_by: c.created_by, created_at: c.created_at, sealed_at: c.sealed_at });
async function charterScopes() {
  await Promise.all(charters.map(fillSha));
  return [...new Set(charters.map((c) => c.scope))].map((scope) => {
    const vs = charters.filter((c) => c.scope === scope).sort((a, b) => b.version - a.version);
    return { scope, sealed: vs.find((c) => c.status === 'sealed') ?? null, proposed: vs.find((c) => c.status === 'proposed') ?? null, versions: vs.map(vref) };
  }).sort((a, b) => (a.scope === 'holding' ? -1 : b.scope === 'holding' ? 1 : a.scope.localeCompare(b.scope)));
}
/** A unified diff of two texts, three lines of context, computed like the hub's difflib (line by line). */
function unified(a: string, b: string, la: string, lb: string): string {
  const x = a.split('\n'), y = b.split('\n');
  const n = x.length, m = y.length;
  const dp = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i]![j] = x[i] === y[j] ? dp[i + 1]![j + 1]! + 1 : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!);
  const ops: Array<[string, string, number, number]> = [];
  let i = 0, j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && x[i] === y[j]) { ops.push([' ', x[i]!, i, j]); i++; j++; }
    else if (j < m && (i >= n || dp[i]![j + 1]! >= dp[i + 1]![j]!)) { ops.push(['+', y[j]!, i, j]); j++; }
    else { ops.push(['-', x[i]!, i, j]); i++; }
  }
  const out = [`--- ${la}`, `+++ ${lb}`];
  const changed = ops.flatMap((o, k) => (o[0] !== ' ' ? [k] : []));
  for (let k = 0; k < changed.length; k++) {
    const start = Math.max(0, changed[k]! - 3);
    let end = Math.min(ops.length - 1, changed[k]! + 3);
    while (k + 1 < changed.length && changed[k + 1]! - 3 <= end + 1) { k++; end = Math.min(ops.length - 1, changed[k]! + 3); }
    const seg = ops.slice(start, end + 1);
    out.push(`@@ -${seg[0]![2] + 1},${seg.filter((o) => o[0] !== '+').length} +${seg[0]![3] + 1},${seg.filter((o) => o[0] !== '-').length} @@`, ...seg.map((o) => o[0] + o[1]));
  }
  return out.join('\n');
}
const redText = (rs: any[]) => rs.map((r) => `- [${r.check}] ${r.key}: ${r.text_fa}${r.patterns?.length ? ` (${r.patterns.length} الگو)` : ''}`).join('\n');
const charterText = (c: any) => `${c.body_md}\n\n## خطوط قرمز\n${redText(c.red_lines)}`;

// ==================================================================== knowledge (§20.3) ==
const ke = (x: any) => ({ id: `k-${x.ref}`, department: null, review: null, approved_by: null, version: 1, created_at: iso(60 * 24 * 30), updated_at: iso(60 * 24 * 30), ...x });
const days = (n: number) => dateKey(new Date(now + n * DAY));
const pass = (by: any, at: number, notes_md = 'تزریق، رمز، تناقض با اساسنامه و اختیار اضافه بررسی شد؛ مشکلی نبود.') => ({ by, at: iso(at), verdict: 'pass', checks: { injection: true, secrets: true, conflicts: true, policy: true }, notes_md });
const knowledge: any[] = [
  ke({ ref: 'K-0001', layer: 'holding', company: 'HQ', kind: 'principle', title_fa: 'اول قاعده، آخر هوش مصنوعی', body_md: 'هر کاری که با یک قاعده‌ی روشن (n8n یا کد) درست انجام میشود، با مدل انجام نمیشود. مدل فقط جایی میاید که نوشتن یا داوری لازم است.\n\n- جمع کردن داده، ساختن دستور جلسه، سنجش KPI و تشخیص تداخل تقویم کد است.\n- هر فراخوانی مدل از LLM Router میگذرد و در خزانه ثبت میشود.', sources: [src('doc', 'OPERATING_MODEL §1.3', 'مدل عملیاتی'), src('charter', 'holding@1', 'ارزش ۴')], valid_until: days(610), status: 'approved', review: pass(overseer, 60 * 24 * 31), approved_by: owner, created_by: owner }),
  ke({ ref: 'K-0002', layer: 'holding', company: 'HQ', kind: 'policy', title_fa: 'هر عدد با منبع و زمانش', body_md: 'هر عددی که در خروجی، پیام به مالک، استوری یا جلسه میاید یک منبع (`{kind, ref}`) و یک زمان دارد. ادعای بی‌منبع وارد صورت‌جلسه و مصوبه نمیشود.', sources: [src('charter', 'holding@1', 'خط قرمز ۴'), src('protocol', 'PR-001', 'راستی‌آزمایی ارقام')], valid_until: days(320), status: 'approved', review: pass(overseer, 60 * 24 * 20), approved_by: owner, created_by: owner }),
  ke({ ref: 'K-0003', layer: 'holding', company: 'HQ', kind: 'fact', title_fa: 'سقف روزانه‌ی توکن ایجنت‌ها 600K است', body_md: 'سقف روزانه‌ی همه‌ی ایجنت‌ها روی هم `600K` توکن است؛ جلسه‌ها حداکثر 15٪ آن را رزرو میکنند و نظارت سهم خودش را دارد.', sources: [src('setting', 'AGENT_DAILY_TOKEN_CAP', 'تنظیم هاب'), src('setting', 'MEETINGS_DAILY_SHARE', '0.15')], valid_until: days(9), status: 'approved', review: pass(overseer, 60 * 24 * 80), approved_by: owner, created_by: aiops, updated_at: iso(60 * 24 * 81) }),
  ke({ ref: 'K-0004', layer: 'holding', company: 'HQ', kind: 'playbook', title_fa: 'گزارش هفتگی با جدول منبع', body_md: 'هر گزارش هفتگی یک ستون «منبع» دارد: برای هر عدد، ref خروجی، KPI یا رکورد خزانه.\n\n1. عددها را از کارت‌ها بخوان، نه از حافظه.\n2. عدد قدیمی را «قدیمی» بنویس.\n3. پیشنهاد بی‌عدد قابل سنجش نیست.', sources: [src('lesson', 'L-0002', 'درس پذیرفته‌شده‌ی تریدیار')], valid_until: days(360), status: 'in_review', created_by: aiops, created_at: iso(60 * 6), updated_at: iso(60 * 6) }),
  ke({ ref: 'K-0013', layer: 'holding', company: 'HQ', kind: 'fact', title_fa: 'قیمت هر میلیون توکن Haiku 5.5', body_md: 'نسخه‌ی قدیمی جدول قیمت؛ جدول تازه در خزانه است.', sources: [src('connection', 'claude-max', 'جدول قیمت')], valid_until: days(-20), status: 'retired', approved_by: owner, created_by: aiops, version: 2 }),
  ke({ ref: 'K-0005', layer: 'company', company: 'TY', kind: 'policy', title_fa: 'حداقل موجودی VIP رایگان تریدیار 100 USDT است', body_md: 'برای VIP رایگان، موجودی حساب LBank کاربر دست‌کم **100 USDT** است. عدد ۵۰ در نسخه‌ی قدیمی ربات بود و اصلاح شد.', sources: [src('support_kb', 'KB-0003', 'دانشنامه‌ی پشتیبانی'), src('resolution', 'M-0006')], valid_until: days(200), status: 'approved', review: pass(overseer, 60 * 24 * 12), approved_by: ceo('TY'), created_by: growthMgr('TY') }),
  ke({ ref: 'K-0006', layer: 'company', company: 'FX', kind: 'fact', title_fa: 'ساعت‌های صدور سیگنال طلا', body_md: 'سیگنال‌های طلا در ساعت‌های باز بودن بازار لندن و نیویورک صادر میشوند.', sources: [src('deliverable', 'O-000029')], valid_until: days(-12), status: 'expired', review: pass(overseer, 60 * 24 * 100), approved_by: ceo('FX'), created_by: agent('FX-QUANT-MGR', 'مدیر کوانت FX') }),
  ke({ ref: 'K-0007', layer: 'company', company: 'PC', kind: 'faq', title_fa: 'نصب اپ پرو-چارت روی iOS', body_md: 'اپ iOS هنوز منتشر نشده؛ نسخه‌ی وب ترمینال روی Safari کار میکند.', sources: [src('work', 'W-000105')], valid_until: days(170), status: 'draft', created_by: growthMgr('PC'), created_at: iso(60 * 4), updated_at: iso(60 * 4) }),
  ke({ ref: 'K-0008', layer: 'department', company: 'TY', department: 'TECH', kind: 'playbook', title_fa: 'انتشار با canary و بازگشت خودکار', body_md: '1. هر انتشار با canary 10٪ شروع میشود.\n2. اگر نرخ خطا از دو برابر خط پایه بیشتر شد، بازگشت خودکار.\n3. انتشار در روزهای ممنوع ماتریس اختیار نیست.\n4. نتیجه در کار انتشار با شاهد ثبت میشود.', sources: [src('resolution', 'M-0004'), src('work', 'W-000102')], valid_until: days(300), status: 'approved', review: pass(overseer, 60 * 24 * 9), approved_by: ceo('TY'), created_by: tech('TY') }),
  ke({ ref: 'K-0009', layer: 'department', company: 'FX', department: 'QUANT', kind: 'playbook', title_fa: 'بازآموزی مدل پس از تغییر رژیم نوسان', body_md: '1. افت دقت ۷ روزه بیش از 5 واحد: بررسی رژیم.\n2. وزن LSTM کم میشود.\n3. سیگنال‌ها تا بازآموزی بدون حد ضرر منتشر میشوند.', sources: [src('deliverable', 'O-000029')], valid_until: days(340), status: 'in_review', created_by: agent('FX-QUANT-02', 'پایشگر سیگنال'), created_at: iso(60 * 20), updated_at: iso(60 * 3),
    review: { by: overseer, at: iso(60 * 3), verdict: 'changes', checks: { injection: true, secrets: true, conflicts: false, policy: true }, notes_md: 'مرحله‌ی ۳ با پیش‌نویس الحاقیه‌ی FX («سیگنال بی‌حد ضرر منتشر نمیشود») تناقض دارد؛ اصلاحش کنید.' } }),
  ke({ ref: 'K-0010', layer: 'department', company: 'TY', department: 'SALES', kind: 'faq', title_fa: 'جواب پرسش کارمزد برداشت', body_md: 'کارمزد برداشت را صرافی تعیین میکند؛ فقط لینک صفحه‌ی کارمزد LBank داده میشود و عدد از ما گفته نمیشود.', sources: [src('charter', 'TY@2'), src('support_kb', 'KB-0005')], valid_until: days(150), status: 'approved', review: pass(overseer, 60 * 24 * 2), approved_by: ceo('TY'), created_by: agent('TY-SALES-MGR', 'مدیر فروش تریدیار') }),
  ke({ ref: 'K-0011', layer: 'employee', company: 'TY', department: 'GROWTH', kind: 'fact', title_fa: 'canonical صفحه‌های بلاگ به نشانی خود صفحه', body_md: 'هفت قالب بلاگ و بازار canonical را به صفحه‌ی اصلی میدادند؛ اصلاح در S-0003.', sources: [src('deliverable', 'O-000031')], valid_until: days(80), status: 'approved', created_by: agent('TY-GROWTH-01', 'تحلیلگر سئوی فنی') }),
  ke({ ref: 'K-0012', layer: 'employee', company: 'FX', department: 'QUANT', kind: 'fact', title_fa: 'افت دقت بعد از خبر اشتغال آمریکا', body_md: 'بعد از هر داده‌ی اشتغال آمریکا، دقت سیگنال‌های طلا برای 30 دقیقه افت میکند.', sources: [src('deliverable', 'O-000029')], valid_until: days(60), status: 'approved', created_by: agent('FX-QUANT-02', 'پایشگر سیگنال') }),
];
const kHistory = new Map<string, any[]>(); // older versions by ref
const supportView = () => supportArticles().filter((a) => a.status === 'approved' || a.status === 'expired').map((a) => ({
  id: `kv-${a.ref}`, ref: a.ref, layer: 'company', company: a.company, department: null, kind: 'support', title_fa: a.question_fa, body_md: a.answer_md,
  sources: [src(a.source.kind, a.source.ref ?? 'owner', 'پشتیبانی §19')], valid_until: a.expires_at.slice(0, 10), status: a.status, review: null,
  approved_by: owner, version: a.version, created_by: owner, created_at: a.approved_at ?? a.expires_at, updated_at: a.approved_at ?? a.expires_at,
}));
const VALID: Record<string, number> = { fact: 90, faq: 180, playbook: 365, policy: 365, principle: 730 };
function knowledgeIn(b: any): string | null {
  if (!b.title_fa?.trim() || !b.body_md?.trim()) return 'عنوان و متن لازم است.';
  if (!['holding', 'company', 'department'].includes(b.layer)) return 'لایه‌ی کارمند حافظه‌ی خود کارمند است و این‌جا نوشته نمیشود.';
  if (!VALID[b.kind]) return 'مقاله‌ی پشتیبانی فقط از صفحه‌ی پشتیبانی نوشته میشود.';
  if (!Array.isArray(b.sources) || !b.sources.some((s: any) => s?.ref?.trim())) return 'دست‌کم یک منبع لازم است.';
  if (!b.valid_until || Date.parse(`${b.valid_until}T00:00:00Z`) > now + (VALID[b.kind]! + 1) * DAY) return `اعتبار ${b.kind} حداکثر ${VALID[b.kind]} روز است.`;
  if (b.layer === 'department' && !b.department) return 'دپارتمان را انتخاب کن.';
  return null;
}

// ======================================================== the three cards (§20.4) ==
type Def = { key: string; card: string; name_fa: string; unit: string; direction: 'up' | 'down'; query: string | null; freshness_hours: number; scorecard: boolean; aggregate: string; digits: number };
const def = (key: string, card: string, name_fa: string, unit: string, direction: 'up' | 'down', query: string | null, freshness_hours: number, scorecard: boolean, aggregate: string, digits: number): Def => ({ key, card, name_fa, unit, direction, query, freshness_hours, scorecard, aggregate, digits });
const DEFS: Def[] = [
  def('uptime_24h', 'stability', 'دسترس‌پذیری ۲۴ ساعت', '%', 'up', 'health.uptime_24h', 1, true, 'min', 2),
  def('p95_latency', 'stability', 'تأخیر p95', 'ms', 'down', 'health.p95_latency_ms', 1, false, 'max', 0),
  def('open_incidents', 'stability', 'حادثه‌ی باز', '', 'down', 'health.open_incidents', 1, false, 'sum', 0),
  def('revenue_month', 'growth', 'درآمد ۳۰ روز', 'USDT', 'up', 'revenue.month_usdt', 30, true, 'sum', 2),
  def('active_users', 'growth', 'کاربر فعال ماه', '', 'up', null, 72, true, 'sum', 0),
  def('min_balance_rate', 'growth', 'نرخ رسیدن به حداقل موجودی', '%', 'up', 'funnel.min_balance_rate', 30, true, 'avg', 1),
  def('signup_rate', 'growth', 'نرخ ثبت‌نام از بازدید', '%', 'up', 'funnel.signup_rate', 30, false, 'avg', 1),
  def('cost_month', 'safety_cost', 'هزینه‌ی توکن ماه', 'USD', 'down', 'treasury.cost_month_usd', 1, true, 'sum', 2),
  def('budget_use', 'safety_cost', 'مصرف بودجه‌ی ماه', '%', 'down', 'treasury.budget_use_pct', 1, false, 'max', 0),
  def('compliance', 'safety_cost', 'انطباق نظارت', '%', 'up', 'oversight.compliance', 24, false, 'min', 0),
  def('findings_high', 'safety_cost', 'یافته‌ی بالا و بحرانی باز', '', 'down', 'oversight.findings_open_high', 24, false, 'sum', 0),
];
const FX_EXTRA = def('signal_accuracy_7d', 'growth', 'دقت ۷ روزه‌ی سیگنال طلا', '%', 'up', null, 48, false, 'avg', 1);
// The closed registry of reviewed queries (§20.4): funnel.signup_rate waits for product events, so it is not in it.
const REGISTRY = new Set(DEFS.map((d) => d.query).filter((q): q is string => !!q && q !== 'funnel.signup_rate'));
type Prof = { base: number; swing: number; drift: number; target: number | null; ageMin?: number; none?: boolean };
const P = (base: number, swing: number, drift: number, target: number | null, ageMin = 12, none = false): Prof => ({ base, swing, drift, target, ageMin, none });
const PROFILE: Record<string, Record<string, Prof>> = {
  TY: { uptime_24h: P(99.82, 0.12, 0, 99.5), p95_latency: P(690, 110, -0.25, 800), open_incidents: P(0.2, 0.5, 0, 0), revenue_month: P(6380, 260, 0.14, 6000, 60 * 9), active_users: P(1840, 50, 0.08, 2200, 60 * 20), min_balance_rate: P(36.5, 1.6, 0.12, 45, 60 * 9), signup_rate: P(0, 0, 0, 12, 0, true), cost_month: P(58.1, 2, 0.4, 60), budget_use: P(74, 2, 0.4, 80), compliance: P(96, 1.5, 0, 95, 60 * 5), findings_high: P(1, 0.4, 0, 0, 60 * 5) },
  FX: { uptime_24h: P(99.21, 0.3, 0.003, 99.5), p95_latency: P(1450, 240, -0.4, 800), open_incidents: P(0.4, 0.6, 0, 0), revenue_month: P(3320, 160, 0.06, 3500, 60 * 9), active_users: P(960, 30, 0.03, 1200, 60 * 24 * 4), min_balance_rate: P(55.4, 2, 0.02, 55, 60 * 9), signup_rate: P(0, 0, 0, 10, 0, true), cost_month: P(42.3, 1.6, 0.4, 50), budget_use: P(41, 2, 0.4, 80), compliance: P(91, 2, -0.02, 95, 60 * 5), findings_high: P(2, 0.4, 0, 0, 60 * 5), signal_accuracy_7d: P(66, 2.4, 0.08, 68, 60 * 30) },
  PC: { uptime_24h: P(99.95, 0.04, 0, 99.5), p95_latency: P(980, 140, -0.2, 800), open_incidents: P(0.6, 0.5, 0, 0), revenue_month: P(1460, 90, -0.06, 1500, 60 * 52), active_users: P(0, 0, 0, 600, 0, true), min_balance_rate: P(52, 3, 0, 50, 60 * 9), signup_rate: P(0, 0, 0, 10, 0, true), cost_month: P(21.6, 1, 0.5, 25), budget_use: P(92, 2, 0.4, 80), compliance: P(94, 1.5, 0, 95, 60 * 5), findings_high: P(1, 0.4, 0, 0, 60 * 5) },
};
const defsOf = (c: string) => (c === 'FX' ? [...DEFS, FX_EXTRA] : DEFS);
const kpiSets: Record<string, any> = Object.fromEntries(OPERATING.map((c) => [c, {
  company: c, version: 3,
  kpis: defsOf(c).map((d, i) => ({ id: `kpi-${c}-${i}`, company: c, key: d.key, card: d.card, name_fa: d.name_fa, unit: d.unit, direction: d.direction,
    source: d.query ? { kind: 'query', query: d.query } : { kind: 'manual' }, freshness_hours: d.freshness_hours, target: PROFILE[c]?.[d.key]?.target ?? null,
    scorecard: d.scorecard, aggregate: d.aggregate, status: 'active', version: 1 })),
}]));
/** 30 daily values, oldest first; a KPI without a source has none (never zero). */
function series(c: string, d: Def): Array<number | null> {
  const p = PROFILE[c]?.[d.key];
  if (!p || p.none || (d.query && !REGISTRY.has(d.query))) return Array<number | null>(30).fill(null);
  const s = seedOf(`${c}.${d.key}`);
  return Array.from({ length: 30 }, (_, i) => {
    const v = p.base * (1 + (p.drift * (i - 29)) / 29 / 3) + (noise(s, i) - 0.5) * 2 * p.swing;
    const r = Math.max(0, d.unit === '%' ? Math.min(100, v) : v);
    return Number(r.toFixed(d.digits));
  });
}
const sourceRef = (c: string, d: Def) => (d.query ? src('query', d.query, `${c}`) : d.key === 'signal_accuracy_7d' ? src('deliverable', 'O-000029', 'kpi.record مدیر کوانت') : src('manual', `kpi.record:${c}.${d.key}`, 'ثبت مدیرعامل با شاهد'));
function cardKpi(c: string, d: Def) {
  const set = kpiSets[c]?.kpis.find((k: any) => k.key === d.key);
  const trend = series(c, d);
  const p = PROFILE[c]?.[d.key];
  const value = trend.at(-1) ?? null;
  const at = value == null ? null : iso(p?.ageMin ?? 12);
  const fresh = set?.freshness_hours ?? d.freshness_hours;
  const state = value == null ? 'no_source' : now - Date.parse(at!) > fresh * 3_600_000 ? 'stale' : 'ok';
  return { key: d.key, name_fa: d.name_fa, unit: d.unit, value, at, source_ref: value == null ? null : sourceRef(c, d), target: set?.target ?? null, trend, state, direction: d.direction, card: d.card, scorecard: set?.scorecard ?? d.scorecard, status: set?.status ?? 'active' };
}
const agg = (xs: number[], how: string) => (!xs.length ? null : how === 'sum' ? xs.reduce((a, b) => a + b, 0) : how === 'avg' ? xs.reduce((a, b) => a + b, 0) / xs.length : how === 'min' ? Math.min(...xs) : Math.max(...xs));
function holdingKpi(d: Def) {
  const per = OPERATING.map((c) => cardKpi(c, d));
  const vals = per.map((k) => k.value).filter((v): v is number => v != null);
  const value = agg(vals, d.aggregate);
  const trend = Array.from({ length: 30 }, (_, i) => { const xs = per.map((k) => k.trend[i]).filter((v): v is number => v != null); const v = agg(xs, d.aggregate); return v == null ? null : Number(v.toFixed(d.digits)); });
  const targets = per.map((k) => k.target).filter((v): v is number => v != null);
  const ats = per.map((k) => k.at).filter((v): v is string => !!v).sort();
  return { key: d.key, name_fa: d.name_fa, unit: d.unit, value: value == null ? null : Number(value.toFixed(d.digits)), at: ats[0] ?? null, source_ref: value == null ? null : src('aggregate', `${d.aggregate}(${OPERATING.join(',')})`, d.query ?? 'manual'),
    target: targets.length === per.length ? Number((agg(targets, d.aggregate) ?? 0).toFixed(d.digits)) : null,
    trend, state: value == null ? 'no_source' : per.some((k) => k.state === 'stale') ? 'stale' : 'ok' };
}
const HUB = def('hub_uptime', 'stability', 'سلامت هاب', '%', 'up', 'health.uptime_24h', 1, false, 'min', 2);
function cardsOf(company: string | null) {
  const cards = ['stability', 'growth', 'safety_cost'];
  if (!company || company === 'HQ') {
    return cards.map((card) => ({ company: 'HQ', card, kpis: [
      ...(card === 'stability' ? [{ key: HUB.key, name_fa: HUB.name_fa, unit: HUB.unit, value: 99.97, at: iso(8), source_ref: src('query', 'health.uptime_24h', 'HQ'), target: 99.9, trend: Array.from({ length: 30 }, (_, i) => Number((99.9 + noise(91, i) * 0.09).toFixed(2))), state: 'ok' }] : []),
      ...DEFS.filter((d) => d.card === card).map(holdingKpi),
    ] }));
  }
  return cards.map((card) => ({ company, card, kpis: defsOf(company).filter((d) => d.card === card).filter((d) => kpiSets[company]?.kpis.find((k: any) => k.key === d.key)?.status !== 'paused').map((d) => { const { direction: _d, card: _c, scorecard: _s, status: _st, ...k } = cardKpi(company, d); return k; }) }));
}

// ======================================================================== OKR (§20.5) ==
const checkin = (minAgo: number, by: any, confidence: number, note_md: string, evidence: any[] = []) => ({ at: iso(minAgo), by, confidence, note_md, evidence });
const kr = (x: any) => {
  const down = x.target < x.start;
  const progress = x.current == null ? 0 : Math.max(0, Math.min(1, down ? (x.start - x.current) / (x.start - x.target) : (x.current - x.start) / (x.target - x.start)));
  return { id: `kr-${x.ref}`, kpi: null, metric_fa: null, checkins: [], ...x, progress: Number(progress.toFixed(3)) };
};
const objectives: any[] = [
  { ref: 'OB-0003', company: 'TY', quarter: '1405-Q3', title_fa: 'دعوت‌شده‌ها به حداقل موجودی برسند', why_md: 'فقط **33٪** دعوت‌شده‌های تازه به حداقل موجودی میرسند، در برابر میانه‌ی ۴ هفته **52٪**. هر دعوت‌شده‌ای که نرسد، کمیسیونی ندارد.', owner: ceo('TY'), status: 'active', decision: 'D-000006',
    key_results: [
      kr({ ref: 'KR-0007', objective: 'OB-0003', title_fa: 'نرخ رسیدن به حداقل موجودی', kpi: 'min_balance_rate', start: 33, target: 45, current: 37.2, confidence: 0.6, weight: 0.5, checkins: [checkin(60 * 24 * 6, ceo('TY'), 0.6, 'با پیام راهنمای بعد از ثبت UID انتظار داریم 5 واحد بالا برود (D-000035).', [src('kpi', 'min_balance_rate')]), checkin(60 * 24 * 20, ceo('TY'), 0.5, 'شروع فصل.', [])] }),
      kr({ ref: 'KR-0008', objective: 'OB-0003', title_fa: 'جواب‌های بی‌دخالت مالک', metric_fa: 'سهم جواب‌های عین دانشنامه (٪)', start: 40, target: 70, current: 58, confidence: 0.7, weight: 0.3, checkins: [checkin(60 * 24 * 16, growthMgr('TY'), 0.7, 'آزمون سایه قبول شد؛ کارت go-live منتظر مُهر است.', [src('decision', 'D-000032')])] }),
      kr({ ref: 'KR-0009', objective: 'OB-0003', title_fa: 'نجات رفرال‌های ازدست‌رفته', metric_fa: 'پرونده‌ی نجات‌یافته در فصل', start: 0, target: 30, current: 9, confidence: 0.5, weight: 0.2, checkins: [checkin(60 * 24 * 5, agent('TY-SALES-MGR', 'مدیر فروش تریدیار'), 0.5, '9 پرونده نجات یافت؛ قالب نجات تازه منتظر مُهر است.', [src('rescue', 'RC-000108')])] }),
    ] },
  { ref: 'OB-0004', company: 'FX', quarter: '1405-Q3', title_fa: 'سیگنال طلا دقیق و ثبت‌نام سریع', why_md: 'دقت پایین بعد از خبرها و کندی ثبت‌نام دو دلیل اصلی رها کردن اشتراک‌اند.', owner: ceo('FX'), status: 'active', decision: 'D-000002',
    key_results: [
      kr({ ref: 'KR-0010', objective: 'OB-0004', title_fa: 'دقت ۷ روزه‌ی سیگنال طلا', kpi: 'signal_accuracy_7d', start: 61, target: 68, current: 68.4, confidence: 0.8, weight: 0.6, checkins: [checkin(60 * 24 * 3, ceo('FX'), 0.8, 'فیلتر رژیم نوسان جواب داد.', [src('deliverable', 'O-000029')])] }),
      kr({ ref: 'KR-0011', objective: 'OB-0004', title_fa: 'ثبت‌نام زیر یک ثانیه', metric_fa: 'زمان ثبت‌نام p95 (ثانیه)', start: 2.9, target: 1, current: 2.9, confidence: 0.7, weight: 0.4, checkins: [checkin(60 * 24 * 9, tech('FX'), 0.7, 'اصلاح روی S-0004 آماده است؛ منتظر انتشار.', [src('code_session', 'S-0004')])] }),
    ] },
  { ref: 'OB-0002', company: 'TY', quarter: '1405-Q2', title_fa: 'راه‌اندازی پشتیبانی تلگرام', why_md: 'جواب‌ها دیر و ناهمگون بود.', owner: ceo('TY'), status: 'closed', decision: 'D-000001',
    key_results: [kr({ ref: 'KR-0004', objective: 'OB-0002', title_fa: 'دانشنامه‌ی تأییدشده', metric_fa: 'مقاله‌ی تأییدشده', start: 0, target: 10, current: 12, confidence: 1, weight: 1 })] },
].map((o, i) => ({ id: `ob${i}`, ...o }));

// =================================================================== decision outcomes (§20.6) ==
const or = (x: any) => ({ id: `or-${x.ref}`, measured: null, proposer_note_md: null, overseer_note_md: null, ...x });
const expD4 = { metric_fa: 'ورودی ارگانیک هفتگی', kpi: 'organic_week', baseline: 1200, target: 1500, by_days: 90 };
const expD3 = { metric_fa: 'دقت ۷ روزه‌ی سیگنال طلا (٪)', kpi: 'signal_accuracy_7d', baseline: 61, target: 68, by_days: 60 };
const expD5 = { metric_fa: 'نرخ تبدیل صفحه‌ی قیمت (٪)', kpi: null, baseline: 1.8, target: 2.5, by_days: 30 };
const expD8 = { metric_fa: 'کاربر بازگشتی در هفته', kpi: 'returning_week', baseline: 40, target: 100, by_days: 60 };
const outcomes: any[] = [
  or({ ref: 'OR-0001', decision: 'D-000004', company: 'TY', day: 30, due_at: iso(60 * 24 * 62), expected: expD4, measured: { value: 1380, at: iso(60 * 24 * 62), source_ref: src('query', 'growth.organic_week', 'Search Console') }, verdict: 'partly', proposer: ceo('TY'), status: 'verified' }),
  or({ ref: 'OR-0002', decision: 'D-000004', company: 'TY', day: 60, due_at: iso(60 * 24 * 32), expected: expD4, measured: { value: 1530, at: iso(60 * 24 * 32), source_ref: src('query', 'growth.organic_week', 'Search Console') }, verdict: 'met', proposer: ceo('TY'), status: 'verified' }),
  or({ ref: 'OR-0003', decision: 'D-000004', company: 'TY', day: 90, due_at: iso(60 * 2), expected: expD4, verdict: 'pending', proposer: ceo('TY'), status: 'due' }),
  or({ ref: 'OR-0004', decision: 'D-000003', company: 'FX', day: 30, due_at: iso(60 * 24 * 5), expected: expD3, measured: { value: 68.4, at: iso(60 * 24 * 5), source_ref: src('deliverable', 'O-000029', 'kpi.record') }, verdict: 'met', proposer: ceo('FX'), status: 'verified' }),
  or({ ref: 'OR-0005', decision: 'D-000003', company: 'FX', day: 60, due_at: ahead(60 * 24 * 25), expected: expD3, verdict: 'pending', proposer: ceo('FX'), status: 'due' }),
  or({ ref: 'OR-0006', decision: 'D-000005', company: 'PC', day: 30, due_at: iso(60 * 24), expected: expD5, verdict: 'pending', proposer: ceo('PC'), status: 'answered', proposer_note_md: 'از Analytics سایت: نرخ تبدیل صفحه‌ی قیمت در 30 روز **2.2٪** بود (شاهد: O-000024).' }),
  or({ ref: 'OR-0007', decision: 'D-000008', company: 'TY', day: 30, due_at: iso(60 * 24 * 35), expected: expD8, measured: { value: 46, at: iso(60 * 24 * 35), source_ref: src('query', 'funnel.returning_week', '') }, verdict: 'missed', proposer: ceo('TY'), status: 'verified' }),
  or({ ref: 'OR-0008', decision: 'D-000008', company: 'TY', day: 60, due_at: iso(60 * 24 * 5), expected: expD8, measured: { value: 58, at: iso(60 * 24 * 5), source_ref: src('query', 'funnel.returning_week', '') }, verdict: 'missed', proposer: ceo('TY'), status: 'verified', overseer_note_md: 'قالب بازگشت دو هفته مُهر نشده بود و قاعده متوقف ماند؛ پیش‌بینی بیش از اندازه خوش‌بین بود.' }),
];

// ==================================================================== authority (§20.7) ==
const rule = (x: any) => ({ scope: 'own_company', limit: null, bounds: null, step_up: false, class: 'A1', locked: false, note_fa: '', version: 1, ...x });
const authority: any[] = [
  rule({ key: 'hire.count_day', title_fa: 'سقف پیشنهاد استخدام در روز', action: 'propose.hire', actor: 'ceo', limit: { count_day: 5 }, bounds: { min: 0, max: 20 }, note_fa: 'برای هر شرکت جدا.', version: 2 }),
  rule({ key: 'ceo.attention_day', title_fa: 'سهمیه‌ی توجه مدیرعامل', action: 'notify', actor: 'ceo', limit: { count_day: 6 }, bounds: { min: 1, max: 20 }, note_fa: 'پیام غیرفوری بیشتر از این تا خلاصه‌ی بعد صبر میکند.' }),
  rule({ key: 'notify.urgent_hour', title_fa: 'اعلان فوری ایجنت‌ها در ساعت', action: 'notify.urgent', actor: 'agent', limit: { count_hour: 5 }, bounds: { min: 1, max: 10 }, note_fa: 'فقط با دسته‌های فهرست‌شده؛ بقیه «تصمیم» میشوند.' }),
  rule({ key: 'story.count_day', title_fa: 'استوری هر شرکت در روز', action: 'story.post', actor: 'ceo', limit: { count_day: 3 }, bounds: { min: 0, max: 5 } }),
  rule({ key: 'recurring.ceo_quota', title_fa: 'تأیید کار دائمی با مدیرعامل، داخل سهمیه', action: 'decision.approve.recurring_approval', actor: 'ceo', limit: { tokens_month: 2_000_000 }, bounds: { min: 0, max: 10_000_000 }, class: 'A2' }),
  rule({ key: 'knowledge.approve.company', title_fa: 'تأیید دانش لایه‌ی شرکت و دپارتمان', action: 'knowledge.approve', actor: 'ceo', class: 'A2', note_fa: 'بعد از بازبینی ناظر. میتوانی آن را به خودت برگردانی.' }),
  rule({ key: 'calendar.add_day', title_fa: 'افزودن کمپین و رویداد به تقویم', action: 'calendar.add', actor: 'ceo', limit: { count_day: 10 }, bounds: { min: 0, max: 50 }, class: 'A2' }),
  rule({ key: 'deploy.blackout_days', title_fa: 'روزهای ممنوع انتشار', action: 'deploy', actor: 'owner', scope: 'holding', limit: { days: ['TH', 'FR'] }, step_up: true, class: 'A3', note_fa: 'انتشار در این روزها تداخل «متوسط» در تقویم است.' }),
  rule({ key: 'batch.max_usd', title_fa: 'سقف دلاری هر کارت در مُهر گروهی', action: 'decision.batch', actor: 'owner', scope: 'holding', limit: { usd: 2 }, bounds: { min: 0, max: 10 }, step_up: true }),
  rule({ key: 'batch.max_items', title_fa: 'حداکثر کارت در هر مُهر گروهی', action: 'decision.batch', actor: 'owner', scope: 'holding', limit: { items: 20 }, bounds: { min: 1, max: 50 }, step_up: true }),
  rule({ key: 'a4.never', title_fa: 'A4 هرگز', action: '*', actor: 'agent', scope: 'holding', class: 'A4', locked: true, note_fa: 'ترید، برداشت و انتقال پول، حذف داده و backup، تغییر دسترسی‌های اصلی.' }),
  rule({ key: 'a3.owner_only', title_fa: 'A3 فقط با مُهر مالک', action: 'a3.*', actor: 'owner', scope: 'holding', class: 'A3', step_up: true, locked: true, note_fa: 'ارسالی که پیشاپیش مُهر کرده‌ای (قاعده و قالب مُهرشده، کانال زنده با go-live) همان تأیید توست و مجاز میماند.' }),
  rule({ key: 'proposer.not_approver', title_fa: 'پیشنهاددهنده ≠ تأییدکننده', action: 'decision.approve', actor: '*', scope: 'holding', locked: true }),
  rule({ key: 'release.owner_only', title_fa: 'آزاد کردن کلید توقف و hold فقط با مالک', action: 'kill_switch.release', actor: 'owner', scope: 'holding', class: 'A2', step_up: true, locked: true }),
  rule({ key: 'authority.no_agent', title_fa: 'هیچ ایجنتی ماتریس را تغییر نمیدهد', action: 'authority.update', actor: 'owner', scope: 'holding', step_up: true, locked: true, note_fa: 'ایجنت‌ها فقط با کارت authority_change پیشنهاد میدهند.' }),
  rule({ key: 'batch.never', title_fa: 'هرگز گروهی', action: 'decision.batch', actor: 'owner', scope: 'holding', locked: true, note_fa: 'هر A3، استخدام، برکناری، بودجه، انتشار، اساسنامه، ماتریس اختیار، پذیرش ریسک، OKR و هر چیز برگشت‌ناپذیر.' }),
];
const limitNumber = (l: any): [string, number] | null => { for (const k of ['tokens_month', 'usd', 'count_day', 'count_hour', 'items']) if (typeof l?.[k] === 'number') return [k, l[k]]; return null; };

// ======================================================================== risks (§20.8) ==
const risk = ({ created, by, ...x }: any) => ({ id: `rk-${x.ref}`, mitigation_md: null, accepted: null, links: {}, version: 1, history: [{ at: created ?? iso(60 * 24 * 20), by: by ?? inspector, change: 'ثبت شد', note: '' }], ...x, score: x.likelihood * x.impact });
const risks: any[] = [
  risk({ ref: 'RK-0001', company: 'FX', title_fa: 'پر شدن دیسک لاگ سرور سیگنال', body_md: 'لاگ‌ها چرخش نداشتند و دیسک پر شد؛ حادثه‌ی I-0009.', category: 'ops', likelihood: 2, impact: 4, owner: tech('FX'), mitigation_md: 'چرخش روزانه‌ی لاگ و هشدار در 80٪ دیسک.', status: 'mitigating', review_at: ahead(60 * 24 * 20), links: { incident: 'I-0009' }, by: system }),
  risk({ ref: 'RK-0002', company: 'TY', title_fa: 'وابستگی کامل درآمد به یک صرافی', body_md: 'همه‌ی درآمد رفرال تریدیار از LBank است؛ تغییر سیاست افیلیت یعنی صفر شدن درآمد.', category: 'money', likelihood: 3, impact: 5, owner: ceo('TY'), status: 'open', review_at: iso(60 * 24 * 3), links: { finding: 'FI-0011' } }),
  risk({ ref: 'RK-0003', company: 'TY', title_fa: 'جعل هویت پشتیبانی در تلگرام', body_md: 'حساب‌هایی به اسم «پشتیبانی تریدیار» از کاربرها عبارت بازیابی میخواهند (SC-000412).', category: 'reputation', likelihood: 4, impact: 4, owner: growthMgr('TY'), mitigation_md: 'جمله‌ی ایمنی در هر پاسخ، هشدار جعل در کانال رسمی، گزارش حساب‌های جعلی به تلگرام.', status: 'mitigating', review_at: ahead(60 * 24 * 6), links: { work: 'W-000120' } }),
  risk({ ref: 'RK-0004', company: 'HQ', title_fa: 'نشت کلید API از لاگ', body_md: 'اگر کلیدی در لاگ یا پیام چاپ شود، از کنترل بیرون میرود.', category: 'security', likelihood: 1, impact: 5, owner: agent('HQ-SEC-01', 'تحلیلگر امنیت'), mitigation_md: 'اسکن secret در CI و ماسک خودکار لاگ.', status: 'mitigating', review_at: ahead(60 * 24 * 70) }),
  risk({ ref: 'RK-0005', company: 'PC', title_fa: 'IP هاب در whitelist افیلیت LBank نیست', body_md: 'pull درآمد پرو-چارت دو بار پشت‌سرهم شکست خورد.', category: 'vendor', likelihood: 5, impact: 3, owner: ceo('PC'), status: 'accepted', review_at: ahead(60 * 24 * 12), accepted: { decision: 'D-000009', until: ahead(60 * 24 * 60) }, links: { decision: 'D-000009' } }),
  risk({ ref: 'RK-0006', company: 'FX', title_fa: 'تک‌نقطه‌ی شکست در پایش کوانت', body_md: 'فقط یک پایشگر سیگنال داریم؛ اگر بخوابد، افت دقت دیر دیده میشود.', category: 'people', likelihood: 3, impact: 3, owner: ceo('FX'), status: 'open', review_at: ahead(60 * 24 * 25) }),
  risk({ ref: 'RK-0007', company: 'PC', title_fa: 'کندی ترمینال روی گوشی‌های ضعیف', body_md: 'بارگذاری نمودار روی گوشی‌های قدیمی بیش از 4 ثانیه بود.', category: 'product', likelihood: 3, impact: 2, owner: tech('PC'), mitigation_md: 'نسخه‌ی تازه بارگذاری را نصف کرد.', status: 'closed', review_at: iso(60 * 24 * 2) }),
  risk({ ref: 'RK-0008', company: 'HQ', title_fa: 'نسخه‌ی پشتیبان آزموده‌نشده', body_md: 'backup بدون آزمون بازیابی اعتبار ندارد.', category: 'data', likelihood: 2, impact: 5, owner: aiops, mitigation_md: 'آزمون بازیابی ماهانه در تقویم (CE-0003).', status: 'mitigating', review_at: ahead(60 * 24 * 14) }),
];

// ===================================================================== calendar (§20.9) ==
const ev = (x: any) => ({ id: `ce-${x.ref}`, company: null, source: {}, status: 'planned', risk: 'low', created_by: system, version: 1, ...x });
const events: any[] = [
  ev({ ref: 'CE-0001', company: 'FX', kind: 'freeze', title_fa: 'توقف deploy: انتشار در جریان', starts_at: iso(30), ends_at: ahead(95), risk: 'medium', created_by: agent('pipeline', 'خط انتشار', 'service') }),
  ev({ ref: 'CE-0002', company: 'PC', kind: 'deploy', title_fa: 'انتشار نسخه‌ی تازه‌ی ترمینال', starts_at: ahead(180), ends_at: ahead(210), source: { decision: 'D-000017' }, risk: 'high', created_by: tech('PC') }),
  ev({ ref: 'CE-0003', company: 'HQ', kind: 'maintenance', title_fa: 'آزمون بازیابی ماهانه', starts_at: ahead(190), ends_at: ahead(250), risk: 'medium' }),
  ev({ ref: 'CE-0004', company: 'FX', kind: 'deploy', title_fa: 'انتشار اصلاح کندی ثبت‌نام', starts_at: ahead(60 * 24 + 120), ends_at: ahead(60 * 24 + 150), source: { work: 'W-000104' }, risk: 'medium', created_by: tech('FX') }),
  ev({ ref: 'CE-0005', company: 'TY', kind: 'campaign', title_fa: 'کمپین آبان: VIP رایگان با رفرال', starts_at: ahead(60 * 24 * 2), ends_at: ahead(60 * 24 * 9), risk: 'low', created_by: growthMgr('TY') }),
  ev({ ref: 'CE-0006', company: 'TY', kind: 'deploy', title_fa: 'انتشار canonical بلاگ', starts_at: ahead(60 * 24 * 4 + 60), ends_at: ahead(60 * 24 * 4 + 90), source: { work: 'W-000106' }, risk: 'low', created_by: tech('TY') }),
  ev({ ref: 'CE-0007', company: 'FX', kind: 'freeze', title_fa: 'فریز پیش از تغییر مدل سیگنال', starts_at: ahead(60 * 24 * 6), ends_at: ahead(60 * 24 * 7), risk: 'medium', created_by: ceo('FX') }),
  ev({ ref: 'CE-0008', company: 'FX', kind: 'deploy', title_fa: 'انتشار مدل LightGBM تازه', starts_at: ahead(60 * 24 * 6 + 120), ends_at: ahead(60 * 24 * 6 + 150), source: { work: 'W-000129' }, risk: 'high', created_by: agent('FX-QUANT-MGR', 'مدیر کوانت FX') }),
  ev({ ref: 'CE-0009', company: null, kind: 'holiday', title_fa: 'شهادت حضرت فاطمه (س)', starts_at: '2026-11-12T20:30:00.000Z', ends_at: '2026-11-13T20:30:00.000Z' }),
  ev({ ref: 'CE-0010', company: 'HQ', kind: 'meeting', title_fa: 'هیئت‌مدیره‌ی هلدینگ', starts_at: iso(26), ends_at: ahead(34), source: { meeting: 'MT-0012' } }),
  ev({ ref: 'CE-0011', company: 'TY', kind: 'meeting', title_fa: 'مدیریت تریدیار', starts_at: ahead(60 * 20 + 14), ends_at: ahead(60 * 21 + 14), source: { meeting: 'MT-0013' } }),
  ev({ ref: 'CE-0012', company: 'FX', kind: 'meeting', title_fa: 'کالبدشکافی حادثه‌ی سرور سیگنال', starts_at: ahead(60 * 22 + 31), ends_at: ahead(60 * 23 + 1), source: { meeting: 'MT-0014' } }),
  ev({ ref: 'CE-0013', company: 'TY', kind: 'event', title_fa: 'وبینار آموزشی کاربران تازه', starts_at: ahead(60 * 24 * 12), ends_at: ahead(60 * 24 * 12 + 90), created_by: growthMgr('TY') }),
  ev({ ref: 'CE-0014', company: 'TY', kind: 'deploy', title_fa: 'انتشار cache داشبورد کاربر', starts_at: iso(60 * 24 * 3), ends_at: iso(60 * 24 * 3 - 30), status: 'done', source: { work: 'W-000101' }, created_by: tech('TY') }),
  ev({ ref: 'CE-0015', company: 'HQ', kind: 'meeting', title_fa: 'استراتژی ماهانه', starts_at: ahead(60 * 24 * 8 + 15), ends_at: ahead(60 * 24 * 8 + 105), source: { meeting: 'MT-0016' } }),
  ev({ ref: 'CE-0016', company: 'FX', kind: 'meeting', title_fa: 'مدیریت کوینه‌پرو FX (نوشتاری)', starts_at: ahead(60 * 24 * 2 + 40), ends_at: ahead(60 * 24 * 2 + 70), source: { meeting: 'MT-0015' } }),
];
const WD = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];
const tehranDay = (t: string) => WD[new Date(Date.parse(t) + 3.5 * 3_600_000).getUTCDay()]!;
const overlap = (a: any, b: any) => Date.parse(a.starts_at) < Date.parse(b.ends_at) && Date.parse(b.starts_at) < Date.parse(a.ends_at);
/** The conflict rules (§20.9), as code: the calendar never decides. */
function conflicts(xs: any[]) {
  const out: any[] = [];
  const live = xs.filter((e) => e.status === 'planned');
  const blackout = new Set<string>(authority.find((r) => r.key === 'deploy.blackout_days')?.limit?.days ?? []);
  for (const d of live.filter((e) => e.kind === 'deploy')) {
    for (const o of live) {
      if (o === d) continue;
      if (o.kind === 'freeze' && (o.company === d.company || o.company === 'HQ') && overlap(d, o)) out.push({ a: d.ref, b: o.ref, rule: 'deploy_in_freeze', severity: 'high', note_fa: `انتشار داخل فریز «${o.title_fa}».` });
      if ((o.kind === 'campaign' || o.kind === 'event') && o.company === d.company && overlap(d, o)) out.push({ a: d.ref, b: o.ref, rule: 'deploy_in_campaign', severity: 'high', note_fa: `انتشار هم‌زمان با ${o.kind === 'campaign' ? 'کمپین' : 'رویداد'} همان شرکت.` });
      if (o.kind === 'deploy' && o.company === d.company && d.ref < o.ref && overlap(d, o)) out.push({ a: d.ref, b: o.ref, rule: 'two_deploys', severity: 'medium', note_fa: 'دو انتشار هم‌زمان یک شرکت.' });
      if (o.kind === 'maintenance' && overlap(d, o)) out.push({ a: d.ref, b: o.ref, rule: 'maintenance_during_deploy', severity: 'medium', note_fa: 'نگه‌داری هم‌زمان با انتشار.' });
      if (o.kind === 'holiday' && overlap(d, o)) out.push({ a: d.ref, b: o.ref, rule: 'deploy_on_holiday', severity: 'medium', note_fa: 'انتشار در روز تعطیل.' });
    }
    if (blackout.has(tehranDay(d.starts_at))) out.push({ a: d.ref, b: d.ref, rule: 'deploy_on_blackout_day', severity: 'medium', note_fa: 'انتشار در روز ممنوع ماتریس اختیار.' });
  }
  return out;
}

// ============================================================ decision cards (§20.6, §20.11) ==
const card = (d: Record<string, unknown>) => ({
  action_class: 'A1', reversible: true, status: 'pending', seal: null, decided_at: null, decided_by: null, note: null, resolution: null, thread: null,
  version: 1, effect_status: 'none', work_id: null, reason_code: null, quota_estimate: { tokens: 0, usd: '0.00' }, expected: null, warnings: [], ...d,
});
const sealedAt = (minAgo: number, resolution: string) => ({ status: 'approved', decided_at: iso(minAgo), decided_by: owner, seal: { method: 'passkey_uv', sealed_at: iso(minAgo), step_up_id: 'demo' }, resolution, effect_status: 'applied', expires_at: null });
/** The §20 cards the demo's cartable shows (mock.ts adds them to its decisions): two pending and batch-sealable, the rest history. */
export const DECISIONS_17: any[] = [
  card({ id: 'd34', ref: 'D-000034', kind: 'meeting_resolution', company: 'HQ', risk: 'low', title: 'کالبدشکافی هر حادثه تا 24 ساعت', proposer: inspector, created_at: iso(60 * 24 * 7), expires_at: ahead(60 * 24 * 4),
    quota_estimate: { tokens: 12_000, usd: '0.20' }, thread: null,
    what: 'هر حادثه‌ی بسته‌شده تا **24 ساعت** بعد کالبدشکافی میشود؛ اقدام‌ها کار پیش‌نویس و ریسک‌ها در دفتر ریسک ثبت میشوند.',
    why: 'پیش‌نویس دستور «کالبدشکافی حادثه‌ها» در جلسه‌ی MT-0011. دو حادثه‌ی ماه گذشته هیچ‌وقت کالبدشکافی نشدند و یکی تکرار شد (I-0005).',
    risk_note: null,
    payload: { meeting: 'MT-0011', item: 'mi-11-3', text_md: meetings.find((m) => m.ref === 'MT-0011').drafts[0].text_md, votes: { support: 3, oppose: 0, abstain: 1 }, claims: [claim('c11', 'حادثه‌ی I-0005 تکرار I-0002 بود', { kind: 'incident', ref: 'I-0005' })] } }),
  card({ id: 'd35', ref: 'D-000035', kind: 'proposal', company: 'TY', risk: 'low', title: 'پیام راهنمای حداقل موجودی بعد از ثبت UID', proposer: ceo('TY'), created_at: iso(60 * 5), expires_at: ahead(60 * 24 * 3),
    quota_estimate: { tokens: 80_000, usd: '1.30' }, thread: 'TY-CEO',
    what: 'بعد از ثبت UID در ربات، یک پیام کوتاه از دانشنامه (KB-0003) حداقل موجودی **100 USDT** را یادآوری میکند. متن فقط از مقاله‌ی تأییدشده است.',
    why: 'فقط 37٪ دعوت‌شده‌ها به حداقل موجودی میرسند (KR-0007)؛ 23 پرسش هفته‌ی گذشته درباره‌ی همین عدد بود (FB-000041).',
    risk_note: 'برگشت‌پذیر؛ اگر نرخ لغو بالا رفت، قاعده متوقف میشود.',
    payload: { okr: 'KR-0007', cost: '1.30', risk: 'low', expected_impact: '+5 واحد نرخ حداقل موجودی در 30 روز', options: ['پیام بلافاصله بعد از ثبت UID', 'پیام 24 ساعت بعد اگر موجودی نرسید'] },
    expected: { metric_fa: 'نرخ رسیدن به حداقل موجودی (٪)', kpi: 'min_balance_rate', baseline: 37, target: 42, by_days: 30 } }),
  // History (sealed): the cards the outcome reviews, the OKRs, the TY addendum and an acceptance came from.
  card({ id: 'd4', ref: 'D-000004', kind: 'proposal', company: 'TY', risk: 'low', title: 'محتوای سئو برای صفحه‌های بازار', proposer: ceo('TY'), created_at: iso(60 * 24 * 93), quota_estimate: { tokens: 1_200_000, usd: '19.00' },
    what: 'چهل صفحه‌ی بازار محتوای آموزشی کوتاه میگیرند.', why: 'ورودی ارگانیک 12٪ افت کرده بود.', risk_note: null, payload: { options: [] }, expected: expD4, ...sealedAt(60 * 24 * 92, 'M-0013') }),
  card({ id: 'd3', ref: 'D-000003', kind: 'proposal', company: 'FX', risk: 'low', title: 'فیلتر رژیم نوسان بعد از خبرهای فدرال رزرو', proposer: ceo('FX'), created_at: iso(60 * 24 * 36), quota_estimate: { tokens: 300_000, usd: '4.80' },
    what: 'سیگنال‌های طلا تا 30 دقیقه بعد از خبر فدرال رزرو صادر نمیشوند.', why: 'دقت ۷ روزه 61٪ بود.', risk_note: null, payload: { options: [] }, expected: expD3, ...sealedAt(60 * 24 * 35, 'M-0005') }),
  card({ id: 'd5', ref: 'D-000005', kind: 'proposal', company: 'PC', risk: 'low', title: 'بازطراحی صفحه‌ی قیمت پرو-چارت', proposer: ceo('PC'), created_at: iso(60 * 24 * 32), quota_estimate: { tokens: 400_000, usd: '6.20' },
    what: 'صفحه‌ی قیمت ساده‌تر و با مقایسه‌ی پلن‌ها.', why: 'نرخ تبدیل 1.8٪ است.', risk_note: null, payload: { options: [] }, expected: expD5, ...sealedAt(60 * 24 * 31, 'M-0014') }),
  card({ id: 'd8', ref: 'D-000008', kind: 'proposal', company: 'TY', risk: 'low', title: 'پیام بازگشت کاربران غیرفعال', proposer: ceo('TY'), created_at: iso(60 * 24 * 66), quota_estimate: { tokens: 200_000, usd: '3.10' },
    what: 'پیام بازگشت برای کاربرهای 30 روز غیرفعال.', why: 'کاربر بازگشتی هفته 40 نفر است.', risk_note: null, payload: { options: [] }, expected: expD8, ...sealedAt(60 * 24 * 65, 'M-0015') }),
  card({ id: 'd6', ref: 'D-000006', kind: 'okr', company: 'TY', risk: 'low', title: 'OKR فصل سوم ۱۴۰۵ تریدیار', proposer: ceo('TY'), created_at: iso(60 * 24 * 23), quota_estimate: { tokens: 0, usd: '0.00' },
    what: 'هدف: دعوت‌شده‌ها به حداقل موجودی برسند (OB-0003)، با سه نتیجه‌ی کلیدی.', why: 'نرخ حداقل موجودی پایین‌ترین حلقه‌ی قیف است.', risk_note: null, payload: { objective: 'OB-0003', quarter: '1405-Q3' }, ...sealedAt(60 * 24 * 22, 'M-0016') }),
  card({ id: 'd7', ref: 'D-000007', kind: 'charter_amendment', company: 'TY', risk: 'medium', title: 'الحاقیه‌ی تریدیار، نسخه‌ی ۲', proposer: ceo('TY'), created_at: iso(60 * 24 * 2 + 200), quota_estimate: { tokens: 0, usd: '0.00' },
    what: 'دو بند پشتیبانی و یک خط قرمز (توصیه‌ی خرید و فروش) به الحاقیه اضافه میشود.', why: 'سه جواب پشتیبانی درباره‌ی کارمزد برداشت عدد اشتباه داشت.', risk_note: null,
    payload: { scope: 'TY', base_version: 1, body_md: TY_V2, red_lines: TY_RED, diff_md: unified(TY_V1, TY_V2, 'TY@1', 'TY@2'), body_sha256: '' }, ...sealedAt(60 * 24 * 2 - 90, 'M-0017') }),
  card({ id: 'd9', ref: 'D-000009', kind: 'risk_acceptance', company: 'PC', risk: 'medium', title: 'پذیرش ریسک whitelist افیلیت پرو-چارت', proposer: ceo('PC'), created_at: iso(60 * 24 * 31), quota_estimate: { tokens: 0, usd: '0.00' },
    what: 'ریسک RK-0005 تا 60 روز پذیرفته میشود.', why: 'اضافه کردن IP به پنل افیلیت فقط با حساب مالک ممکن است.', risk_note: 'درآمد پرو-چارت در این مدت با تأخیر دیده میشود.',
    payload: { risk: 'RK-0005', until: ahead(60 * 24 * 60), score: 15 }, ...sealedAt(60 * 24 * 30, 'M-0018') }),
];
void Promise.all(charters.map(fillSha)).then(() => { const d = DECISIONS_17.find((x) => x.ref === 'D-000007'); if (d) d.payload.body_sha256 = charters.find((c) => c.scope === 'TY' && c.version === 2)?.body_sha256 ?? ''; });
const BATCH_KINDS = new Set(['proposal', 'meeting_resolution', 'knowledge_entry']);
const maxUsd = () => authority.find((r) => r.key === 'batch.max_usd')?.limit?.usd ?? 2;
const maxItems = () => authority.find((r) => r.key === 'batch.max_items')?.limit?.items ?? 20;
const why = (d: any): string | null =>
  !d ? 'not_found' : d.status !== 'pending' ? 'not_pending' : !BATCH_KINDS.has(d.kind) ? 'kind' : d.action_class !== 'A1' ? 'action_class' : d.risk !== 'low' ? 'risk'
    : !d.reversible ? 'irreversible' : d.amendments ? 'amended' : Number(d.quota_estimate?.usd ?? 0) > maxUsd() ? 'over_max_usd' : null;
/** What sealing a §20 card does in the demo. */
export function decided17(d: any): void {
  if (d.expected && d.kind === 'proposal') {
    for (const day of [30, 60, 90].filter((x) => x <= d.expected.by_days)) {
      outcomes.push(or({ ref: `OR-${pad(outcomes.length + 1, 4)}`, decision: d.ref, company: d.company, day, due_at: ahead(60 * 24 * day), expected: d.expected, verdict: 'pending', proposer: d.proposer, status: 'due' }));
    }
  }
}

// ======================================================================= routes ==
type Ctx = { decisions: any[] };
/** The §20 routes; null when the path is not one of them. */
export async function handle17(req: Request, p: string, u: URL, ctx: Ctx): Promise<Response | null> {
  const m = req.method;
  const q = (k: string) => u.searchParams.get(k);
  const body = async <B,>() => (await req.json().catch(() => ({}))) as B;
  if (m === 'GET') {
    // ---- meetings
    if (p === '/meetings/settings') return json(types);
    if (p === '/meetings') {
      return json(page(meetings.filter((x) => (!q('type') || x.type === q('type')) && (!q('company') || x.company === q('company')) && (!q('state') || x.state === q('state'))).map(meetingOut).sort((a, b) => b.starts_at.localeCompare(a.starts_at))));
    }
    const mt = /^\/meetings\/(MT-\d+)(\/turns)?$/.exec(p);
    if (mt) {
      const x = meetings.find((y) => y.ref === mt[1]);
      if (!x) return problem(404, 'not_found', 'این جلسه پیدا نشد.');
      if (!mt[2]) return json(meetingOut(x));
      const sc = script[x.ref];
      if (x.state === 'live' && sc?.length && Date.now() - lastReveal > 8_000) { addTurn(x, sc.shift()); lastReveal = Date.now(); }
      return json({ items: turns.filter((t) => t.meeting === x.ref && (!q('item') || t.item === q('item'))).sort((a, b) => a.at.localeCompare(b.at) || a.n - b.n), whispers: whispers.filter((w) => w.meeting === x.ref), next_cursor: null });
    }
    // ---- charter
    if (p === '/charter') return json(await charterScopes());
    const cv = /^\/charter\/([A-Za-z0-9_]+)\/versions(?:\/(\d+)(\/diff)?)?$/.exec(p);
    if (cv) {
      await Promise.all(charters.map(fillSha));
      const vs = charters.filter((c) => c.scope === cv[1]).sort((a, b) => b.version - a.version);
      if (!cv[2]) return json(vs);
      const c = vs.find((x) => x.version === Number(cv[2]));
      if (!c) return problem(404, 'not_found', 'این نسخه پیدا نشد.');
      if (!cv[3]) return json(c);
      const o = vs.find((x) => x.version === Number(q('against')));
      if (!o) return problem(404, 'not_found', 'نسخه‌ی مقایسه پیدا نشد.');
      const [a, b] = o.version < c.version ? [o, c] : [c, o];
      return json({ scope: c.scope, version: c.version, against: o.version, diff: unified(charterText(a), charterText(b), `${a.scope}@${a.version}`, `${b.scope}@${b.version}`) });
    }
    // ---- knowledge
    if (p === '/knowledge') {
      const text = (q('q') ?? '').trim();
      const all = [...knowledge, ...supportView()];
      return json(page(all.filter((k) => (!q('layer') || k.layer === q('layer')) && (!q('company') || k.company === q('company')) && (!q('department') || k.department === q('department'))
        && (!q('kind') || k.kind === q('kind')) && (q('status') ? k.status === q('status') : q('include_expired') === 'true' || k.status !== 'expired')
        && (!text || `${k.ref} ${k.title_fa} ${k.body_md}`.includes(text))).sort((a, b) => b.updated_at.localeCompare(a.updated_at))));
    }
    const kn = /^\/knowledge\/((?:K|KB)-\d+)(\/versions)?$/.exec(p);
    if (kn) {
      const k = [...knowledge, ...supportView()].find((x) => x.ref === kn[1]);
      if (!k) return problem(404, 'not_found', 'این ورودی پیدا نشد.');
      return json(kn[2] ? [k, ...(kHistory.get(k.ref) ?? [])] : k);
    }
    // ---- cards and KPIs
    if (p === '/cards') return json(cardsOf(q('company')));
    if (p === '/scorecards') {
      const text = (q('q') ?? '').trim();
      return json(page(OPERATING.filter((c) => !text || `${c} ${NAME[c]}`.includes(text) || text.includes(c)).map((c) => ({ company: c, kpis: defsOf(c).filter((d) => kpiSets[c]?.kpis.find((k: any) => k.key === d.key)?.scorecard).map((d) => { const { scorecard: _s, status: _st, ...k } = cardKpi(c, d); return k; }) }))));
    }
    const kp = /^\/kpis\/([A-Z0-9]+)(?:\/([a-z0-9_]+)\/values)?$/.exec(p);
    if (kp) {
      const set = kpiSets[kp[1]!];
      if (!set) return problem(404, 'not_found', 'برای این شرکت KPI تعریف نشده.');
      if (!kp[2]) return json(set);
      const d = defsOf(kp[1]!).find((x) => x.key === kp[2]);
      if (!d) return problem(404, 'not_found', 'این KPI پیدا نشد.');
      const vs = series(kp[1]!, d);
      const from = q('from') ?? '0000', to = q('to') ?? '9999';
      return json(vs.flatMap((v, i) => { const day = new Date(now - (29 - i) * DAY); const k = dateKey(day); return v == null || k < from || k > to ? [] : [{ kpi: d.key, at: `${k}T08:30:00.000Z`, value: v, source_ref: sourceRef(kp[1]!, d) }]; }));
    }
    // ---- OKR and outcomes
    if (p === '/okr') return json(objectives.filter((o) => (!q('company') || o.company === q('company')) && (!q('quarter') || o.quarter === q('quarter')) && (!q('status') || o.status === q('status'))));
    const ob = /^\/okr\/(OB-\d+)$/.exec(p);
    if (ob) { const o = objectives.find((x) => x.ref === ob[1]); return o ? json(o) : problem(404, 'not_found', 'این هدف پیدا نشد.'); }
    if (p === '/outcomes') {
      return json(page(outcomes.filter((r) => (!q('company') || r.company === q('company')) && (!q('verdict') || r.verdict === q('verdict')) && (!q('decision') || r.decision === q('decision'))
        && (q('due') !== 'true' || (r.status === 'due' && Date.parse(r.due_at) <= Date.now()))).sort((a, b) => a.due_at.localeCompare(b.due_at))));
    }
    // ---- authority, risks, calendar
    if (p === '/authority') return json(authority);
    if (p === '/risks/matrix') {
      const counts = Array.from({ length: 5 }, () => Array<number>(5).fill(0));
      for (const r of risks) if (r.status !== 'closed' && (!q('company') || r.company === q('company'))) counts[r.likelihood - 1]![r.impact - 1]! += 1;
      return json({ company: q('company'), counts });
    }
    if (p === '/risks') {
      const min = Number(q('min_score') ?? 0);
      return json(page(risks.filter((r) => (!q('company') || r.company === q('company')) && (!q('status') || r.status === q('status')) && (!q('category') || r.category === q('category')) && r.score >= min).sort((a, b) => b.score - a.score || a.ref.localeCompare(b.ref))));
    }
    const rk = /^\/risks\/(RK-\d+)$/.exec(p);
    if (rk) { const r = risks.find((x) => x.ref === rk[1]); return r ? json(r) : problem(404, 'not_found', 'این ریسک پیدا نشد.'); }
    if (p === '/calendar') {
      const from = q('from') ? Date.parse(q('from')!) : -Infinity, to = q('to') ? Date.parse(q('to')!) : Infinity;
      const xs = events.filter((e) => Date.parse(e.ends_at) >= from && Date.parse(e.starts_at) <= to && (!q('kind') || e.kind === q('kind')) && (!q('company') || e.company === q('company') || e.company == null || e.company === 'HQ'));
      const all = conflicts(events);
      const refs = new Set(xs.map((e) => e.ref));
      return json({ events: xs.sort((a, b) => a.starts_at.localeCompare(b.starts_at)), conflicts: all.filter((c) => refs.has(c.a) || refs.has(c.b)) });
    }
    // ---- batch seal
    if (p === '/decisions/batchable') {
      return json(ctx.decisions.filter((d) => !why(d)).slice(0, maxItems()).map((d) => ({ ref: d.ref, version: d.version, kind: d.kind, company: d.company, title: d.title, quota_estimate: d.quota_estimate, proposer: d.proposer, risk: d.risk, created_at: d.created_at, expires_at: d.expires_at })));
    }
    return null;
  }

  // ------------------------------------------------------------------ writes --
  if (p === '/meetings/settings' && m === 'PUT') {
    const deny = needsStepUp(req);
    if (deny) return deny;
    const b = await body<{ types: any[] }>();
    for (const t of b.types ?? []) {
      const x = typeOf(t.key);
      if (!x) continue;
      if (t.max_rounds < 1 || t.max_rounds > 3 || t.max_speakers < 2 || t.max_speakers > 8) return problem(422, 'validation_failed', 'دور بین ۱ و ۳ و سخنگو بین ۲ و ۸ است.');
      if (t.budget_tokens == null && t.key !== 'war_room') return problem(422, 'validation_failed', 'فقط اتاق جنگ بی‌سقف است.');
      if (t.version !== x.version) return problem(409, 'version_conflict', 'تنظیمات همین حالا عوض شده؛ دوباره نگاه کن.');
      const changed = ['max_rounds', 'max_speakers', 'budget_tokens', 'turn_cap_tokens', 'owner_presence', 'enabled'].some((k) => t[k] !== x[k]);
      Object.assign(x, { max_rounds: t.max_rounds, max_speakers: t.max_speakers, budget_tokens: t.budget_tokens, turn_cap_tokens: t.turn_cap_tokens, owner_presence: t.owner_presence, enabled: t.enabled });
      if (changed) x.version += 1;
    }
    return json(types);
  }
  if (p === '/meetings' && m === 'POST') {
    const key = req.headers.get('Idempotency-Key') ?? '';
    const hit = keys.get(key);
    if (hit) return json(hit.body, hit.status);
    const b = await body<{ type: string; company?: string; starts_at: string; items?: Array<{ title_fa: string; brief_md?: string; time_box_min?: number }> }>();
    const t = typeOf(b.type);
    if (!t || b.type === 'war_room' || b.type === 'standup') return problem(422, 'validation_failed', 'این نوع جلسه را کد باز میکند، نه دست.');
    const company = b.type === 'company' || b.type === 'postmortem' ? b.company : 'HQ';
    if (!company) return problem(422, 'validation_failed', 'شرکت را انتخاب کن.');
    const speakers = b.type === 'company' || b.type === 'postmortem' ? [ceo(company), tech(company), inspector] : [...OPERATING.map(ceo), inspector].slice(-t.max_speakers);
    const its = (b.items?.length ? b.items : [{ title_fa: 'دستور آزاد', time_box_min: 10 }]).map((x, i) => item(`mi-${seq.mt}-${i + 1}`, i + 1, x.title_fa, x.brief_md ?? '', [], x.time_box_min ?? 10, speakers));
    const estimate = its.length * speakers.length * Math.min(t.max_rounds, 2) * 2400 + 6000;
    const cap = t.budget_tokens ?? null;
    const x = { id: `mt${seq.mt}`, ref: `MT-${pad(seq.mt++, 4)}`, type: b.type, company, title_fa: company === 'HQ' ? t.title_fa : `${t.title_fa === 'مدیریت هر شرکت' ? 'مدیریت' : t.title_fa} ${NAME[company]}`, starts_at: b.starts_at, state: 'scheduled', mode: 'discussion',
      budget: { cap, estimate: cap != null ? Math.min(estimate, cap) : estimate, reserved: 0, used: 0 }, trimmed_fa: cap != null && estimate > cap ? `برآورد اول ${Math.round(estimate / 1000)}K بود و از بودجه بیشتر شد؛ دور دوم دستورهای آخر حذف شد.` : null,
      items: its, participants: speakers.map((s) => part(s, s.display_fa, true, s.code === inspector.code)), owner_presence: t.owner_presence, minutes: null, incident: null, version: 1, created_at: stamp(), drafts: [] };
    meetings.push(x);
    events.push(ev({ ref: `CE-${pad(events.length + 1, 4)}`, company, kind: 'meeting', title_fa: x.title_fa, starts_at: x.starts_at, ends_at: new Date(Date.parse(x.starts_at) + 60 * MIN).toISOString(), source: { meeting: x.ref }, created_by: owner }));
    const out = meetingOut(x);
    keys.set(key, { status: 201, body: out });
    return json(out, 201);
  }
  const mw = /^\/meetings\/(MT-\d+)(?:\/(speak|control))?$/.exec(p);
  if (mw) {
    const x = meetings.find((y) => y.ref === mw[1]);
    if (!x) return problem(404, 'not_found', 'این جلسه پیدا نشد.');
    if (!mw[2] && m === 'PATCH') {
      const bad = unmatched(req, x.version);
      if (bad) return bad;
      if (x.state === 'ended' || x.state === 'cancelled') return problem(409, 'validation_failed', 'جلسه‌ی تمام‌شده عوض نمیشود.');
      const b = await body<{ items?: Array<{ id: string; n: number; skip?: boolean }>; budget_cap?: number; owner_presence?: string }>();
      if (b.budget_cap != null) {
        if (x.budget.cap != null && b.budget_cap > x.budget.cap) return problem(422, 'validation_failed', 'این‌جا فقط کم کردن بودجه است؛ افزایش با «افزایش بودجه» در جلسه‌ی زنده.');
        x.budget.cap = b.budget_cap;
        if (x.budget.estimate > b.budget_cap) { x.trimmed_fa = `برآورد ${Math.round(x.budget.estimate / 1000)}K از بودجه‌ی تازه‌ی ${Math.round(b.budget_cap / 1000)}K بیشتر بود؛ طبق قاعده اول دور دوم دستورهای کم‌اهمیت، بعد سخنگوها کم شد.`; x.budget.estimate = b.budget_cap; }
      }
      for (const it of b.items ?? []) { const y = x.items.find((z: any) => z.id === it.id); if (!y) continue; y.n = it.n; if (it.skip && y.state === 'waiting') y.state = 'skipped'; if (it.skip === false && y.state === 'skipped') y.state = 'waiting'; }
      x.items.sort((a: any, c: any) => a.n - c.n);
      if (b.owner_presence) x.owner_presence = b.owner_presence;
      x.version += 1;
      return json(meetingOut(x));
    }
    if (mw[2] === 'speak') {
      const key = req.headers.get('Idempotency-Key');
      if (!key) return problem(422, 'validation_failed', 'Idempotency-Key لازم است.');
      const hit = keys.get(key);
      if (hit) return json(hit.body, hit.status);
      if (x.state !== 'live') return problem(409, 'meeting_not_live', 'جلسه زنده نیست.');
      const b = await body<{ text?: string; file_id?: string }>();
      if (!b.text?.trim() && !b.file_id) return problem(422, 'validation_failed', 'متن یا صدا لازم است.');
      const t = addTurn(x, { speaker: owner, kind: 'owner', statement_md: b.text?.trim() || '(پیام صوتی)', claims: [], tokens: 0 });
      const it = current(x);
      const next = it?.speakers.find((s: any) => s.code !== inspector.code);
      if (next) (script[x.ref] ??= []).unshift({ item: it.id, speaker: next, kind: 'statement', statement_md: 'دریافت شد؛ این را در جمع‌بندی همین دستور میاورم و منبعش را میگذارم.', claims: [], tokens: 1600 });
      lastReveal = Date.now() - 5_000;
      keys.set(key, { status: 201, body: t });
      return json(t, 201);
    }
    if (mw[2] === 'control') {
      const b = await body<{ action: string; tokens?: number }>();
      if (x.state !== 'live' && x.state !== 'closing') return problem(409, 'meeting_not_live', 'جلسه زنده نیست.');
      const it = current(x);
      if (b.action === 'raise_budget') {
        if (!b.tokens || b.tokens <= 0) return problem(422, 'validation_failed', 'مقدار افزایش را بنویس.');
        if (x.budget.cap != null) { x.budget.cap += b.tokens; x.budget.reserved += b.tokens; }
      } else if (b.action === 'skip_item') {
        if (it) it.state = 'skipped';
        nextItem(x);
      } else if (b.action === 'next_round') {
        const max = typeOf(x.type)?.max_rounds ?? 2;
        const drafts = x.drafts.filter((d: any) => it && d.item === it.id);
        // The round in progress finishes first: what the demo still had queued for it is said before the next round opens.
        const sc = script[x.ref] ?? [];
        while (sc.length && sc[0].kind !== 'vote' && sc[0].item === it?.id) addTurn(x, sc.shift());
        if (it && it.round < max && drafts.length) {
          Object.assign(it, { round: it.round + 1, state: 'round_2' });
          const votes = ['support', 'support', 'support', 'abstain'] as const;
          (script[x.ref] ??= []).push(...it.speakers.map((s: any, k: number) => ({ item: it.id, speaker: s, kind: 'vote', statement_md: votes[k % 4] === 'support' ? 'موافق.' : 'ممتنع.', claims: [], tokens: 700,
            stance: { draft: drafts[0].id, vote: votes[k % 4], reason_fa: votes[k % 4] === 'support' ? 'ساعت کم‌بار ریسک بازگشت را کم میکند.' : 'تا منبع عدد سهم کندی نیاید نظری ندارم.' } })));
          lastReveal = Date.now() - 6_000;
        } else {
          if (it) it.state = 'done';
          nextItem(x);
        }
      } else if (b.action === 'end') {
        endMeeting(x, ctx.decisions);
        script[x.ref] = [];
      } else return problem(422, 'validation_failed', 'این کار شناخته نیست.');
      x.version += 1;
      return json(meetingOut(x));
    }
  }
  // ---- charter
  const cs = /^\/charter\/([A-Za-z0-9_]+)(?:\/versions\/(\d+)\/seal)?$/.exec(p);
  if (cs) {
    const scope = cs[1]!;
    if (scope !== 'holding' && !OPERATING.includes(scope)) return problem(404, 'not_found', 'این دامنه پیدا نشد.');
    if (!cs[2] && m === 'PUT') {
      const b = await body<{ body_md: string; red_lines: any[] }>();
      const max = scope === 'holding' ? 6000 : 3000;
      if (!b.body_md?.trim()) return problem(422, 'validation_failed', 'متن خالی است.');
      if (b.body_md.length > max) return problem(422, 'validation_failed', `متن از سقف ${max} نویسه بلندتر است؛ این سند در هر اجرا خوانده میشود.`);
      if ((b.red_lines ?? []).some((r) => !r.key?.trim() || !r.text_fa?.trim())) return problem(422, 'validation_failed', 'هر خط قرمز کلید و متن دارد.');
      for (const c of charters) if (c.scope === scope && c.status === 'proposed') c.status = 'superseded';
      const v = Math.max(0, ...charters.filter((c) => c.scope === scope).map((c) => c.version)) + 1;
      const c = await fillSha({ scope, version: v, status: 'proposed', body_md: b.body_md, red_lines: b.red_lines ?? [], body_sha256: '', created_by: owner, created_at: stamp(), sealed_by: null, sealed_at: null });
      charters.push(c);
      return json(c, 201);
    }
    if (cs[2] && m === 'POST') {
      const deny = needsStepUp(req);
      if (deny) return deny;
      const c = charters.find((x) => x.scope === scope && x.version === Number(cs[2]));
      if (!c || c.status !== 'proposed') return problem(409, 'decision_not_pending', 'این نسخه منتظر مُهر نیست.');
      for (const o of charters) if (o.scope === scope && o.status === 'sealed') o.status = 'superseded';
      Object.assign(c, { status: 'sealed', sealed_by: owner, sealed_at: stamp() });
      return json(c);
    }
  }
  // ---- knowledge
  if (p === '/knowledge' && m === 'POST') {
    const b = await body<any>();
    const bad = knowledgeIn(b);
    if (bad) return problem(422, 'validation_failed', bad);
    const n = Math.max(...knowledge.map((k) => Number(k.ref.slice(2)))) + 1;
    const k = ke({ ref: `K-${pad(n, 4)}`, ...b, department: b.layer === 'department' ? b.department : null, status: 'approved', approved_by: owner, created_by: owner, created_at: stamp(), updated_at: stamp() });
    knowledge.unshift(k);
    return json(k, 201);
  }
  const kw = /^\/knowledge\/(K-\d+)(\/retire)?$/.exec(p);
  if (kw) {
    const k = knowledge.find((x) => x.ref === kw[1]);
    if (!k) return problem(404, 'not_found', 'این ورودی پیدا نشد.');
    if (k.layer === 'employee') return problem(405, 'validation_failed', 'لایه‌ی کارمند حافظه‌ی خود اوست؛ فقط خواندنی.');
    if (kw[2]) { k.status = 'retired'; k.updated_at = stamp(); return json(k); }
    if (m === 'PUT') {
      const b = await body<any>();
      const bad = knowledgeIn({ ...b, layer: b.layer ?? k.layer });
      if (bad) return problem(422, 'validation_failed', bad);
      kHistory.set(k.ref, [{ ...k, status: k.status === 'approved' ? 'retired' : k.status }, ...(kHistory.get(k.ref) ?? [])]);
      Object.assign(k, b, { version: k.version + 1, status: 'approved', approved_by: owner, review: null, updated_at: stamp() });
      return json(k);
    }
  }
  if (/^\/knowledge\/KB-\d+/.test(p)) return problem(405, 'validation_failed', 'مقاله‌ی پشتیبانی فقط از صفحه‌ی پشتیبانی ویرایش میشود.');
  // ---- KPIs
  const kps = /^\/kpis\/([A-Z0-9]+)$/.exec(p);
  if (kps && m === 'PUT') {
    const set = kpiSets[kps[1]!];
    if (!set) return problem(404, 'not_found', 'برای این شرکت KPI تعریف نشده.');
    const bad = unmatched(req, set.version);
    if (bad) return bad;
    const b = await body<{ kpis: Array<{ key: string; target: number | null; scorecard: boolean; status: string; freshness_hours: number }> }>();
    for (const x of b.kpis ?? []) {
      const k = set.kpis.find((y: any) => y.key === x.key);
      if (!k) return problem(422, 'validation_failed', `KPI ${x.key} تعریف نشده.`);
      if (x.freshness_hours < 1 || x.freshness_hours > 24 * 30) return problem(422, 'validation_failed', 'تازگی بین ۱ ساعت و ۳۰ روز است.');
      Object.assign(k, { target: x.target, scorecard: x.scorecard, status: x.status, freshness_hours: x.freshness_hours, version: k.version + 1 });
      const pr = PROFILE[kps[1]!]?.[x.key];
      if (pr) pr.target = x.target;
    }
    set.version += 1;
    return json(set);
  }
  // ---- authority
  if (p === '/authority' && m === 'PUT') {
    const deny = needsStepUp(req);
    if (deny) return deny;
    const b = await body<{ rules: Array<{ key: string; actor?: string; limit: any; version: number }> }>();
    for (const x of b.rules ?? []) {
      const r = authority.find((y) => y.key === x.key);
      if (!r) return problem(422, 'validation_failed', `ردیف ${x.key} پیدا نشد.`);
      if (r.locked) return problem(422, 'validation_failed', `«${r.title_fa}» قفل است و از داده عوض نمیشود.`);
      if (r.version !== x.version) return problem(409, 'version_conflict', 'ماتریس همین حالا عوض شده؛ دوباره نگاه کن.');
      const num = limitNumber(x.limit);
      if (num && r.bounds && (num[1] < r.bounds.min || num[1] > r.bounds.max)) return problem(422, 'validation_failed', `«${r.title_fa}» بیرون از محدوده‌ی ${r.bounds.min} تا ${r.bounds.max} است.`);
    }
    for (const x of b.rules ?? []) { const r = authority.find((y) => y.key === x.key); Object.assign(r, { limit: x.limit, ...(x.actor ? { actor: x.actor } : {}), version: r.version + 1 }); }
    return json(authority);
  }
  // ---- risks
  if (p === '/risks' && m === 'POST') {
    const b = await body<any>();
    if (!b.title_fa?.trim() || !b.company) return problem(422, 'validation_failed', 'عنوان و شرکت لازم است.');
    if (![1, 2, 3, 4, 5].includes(b.likelihood) || ![1, 2, 3, 4, 5].includes(b.impact)) return problem(422, 'validation_failed', 'احتمال و اثر بین ۱ و ۵ است.');
    const score = b.likelihood * b.impact;
    const r = risk({ ref: `RK-${pad(risks.length + 1, 4)}`, ...b, body_md: b.body_md ?? '', owner: inspector, status: 'open', review_at: b.review_at ?? ahead(60 * 24 * (score >= 15 ? 14 : score >= 8 ? 30 : 90)), by: owner, created: stamp() });
    risks.push(r);
    return json(r, 201);
  }
  const rw = /^\/risks\/(RK-\d+)$/.exec(p);
  if (rw && m === 'PATCH') {
    const r = risks.find((x) => x.ref === rw[1]);
    if (!r) return problem(404, 'not_found', 'این ریسک پیدا نشد.');
    const bad = unmatched(req, r.version);
    if (bad) return bad;
    const b = await body<any>();
    if (b.status === 'closed') return problem(422, 'validation_failed', 'بستن ریسک با تأیید بازرس کل (QC) است؛ از او بخواه.');
    const change = Object.keys(b).map((k) => `${k}: ${String(r[k] ?? '—').slice(0, 24)} ← ${String(b[k] ?? '—').slice(0, 24)}`).join('، ');
    Object.assign(r, b, { version: r.version + 1 });
    r.score = r.likelihood * r.impact;
    r.history.unshift({ at: stamp(), by: owner, change, note: '' });
    return json(r);
  }
  // ---- calendar
  if (p === '/calendar' && m === 'POST') {
    const b = await body<any>();
    if (!b.title_fa?.trim() || !b.starts_at || !b.ends_at || Date.parse(b.ends_at) <= Date.parse(b.starts_at)) return problem(422, 'validation_failed', 'عنوان و بازه‌ی درست لازم است.');
    const e = ev({ ref: `CE-${pad(events.length + 1, 4)}`, ...b, created_by: owner });
    events.push(e);
    return json(e, 201);
  }
  const cw = /^\/calendar\/(CE-\d+)$/.exec(p);
  if (cw && m === 'PATCH') {
    const e = events.find((x) => x.ref === cw[1]);
    if (!e) return problem(404, 'not_found', 'این رویداد پیدا نشد.');
    const bad = unmatched(req, e.version);
    if (bad) return bad;
    Object.assign(e, await body<any>(), { version: e.version + 1 });
    return json(e);
  }
  // ---- batch seal
  if (p === '/decisions/batch/approve') {
    const deny = needsStepUp(req);
    if (deny) return deny;
    const key = req.headers.get('Idempotency-Key');
    if (!key) return problem(422, 'validation_failed', 'Idempotency-Key لازم است.');
    const hit = keys.get(key);
    if (hit) return json(hit.body, hit.status);
    const b = await body<{ items: Array<{ ref: string; version: number }> }>();
    const xs = b.items ?? [];
    if (!xs.length) return problem(422, 'validation_failed', 'هیچ کارتی انتخاب نشده.');
    const bad = xs.flatMap((x) => {
      const d = ctx.decisions.find((y) => y.ref === x.ref);
      const r = why(d) ?? (d.version !== x.version ? 'changed' : null);
      return r ? [{ ref: x.ref, reason: r }] : [];
    });
    if (xs.length > maxItems()) bad.push({ ref: xs[maxItems()]!.ref, reason: 'over_max_items' });
    if (bad.length) return problem(422, 'batch_not_eligible', 'یکی از کارت‌ها دیگر شایسته‌ی مُهر گروهی نیست؛ هیچ کارتی مُهر نشد.', { fields: { items: bad } });
    const batch = `B-${pad(seq.batch++, 4)}`;
    const out = xs.map((x) => {
      const d = ctx.decisions.find((y) => y.ref === x.ref);
      const resolution = `M-${pad(seq.resolution++ + 6, 4)}`;
      Object.assign(d, { status: 'approved', decided_at: stamp(), decided_by: owner, seal: { method: 'passkey_uv', sealed_at: stamp(), step_up_id: 'mock', batch }, resolution, effect_status: 'applied' });
      decided17(d);
      return { ref: d.ref, resolution };
    });
    const res = { batch, items: out };
    keys.set(key, { status: 200, body: res });
    return json(res);
  }
  return null;
}
