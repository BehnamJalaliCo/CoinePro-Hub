// Development-only fixtures (npm run dev:mock) for contract §34 and §35 ⟨1.16 and 1.17⟩, the order as a session and the owner's office. Five
// sessions in every badge (the owner's turn with a question, a blocker with a one-tap fix, ready for his OK, moving, and one closed and
// archived), each with its own talk; participants (a person, a model seat), tasks, close / reopen / hide, the office (sessions, approvals,
// money, critical, suggestions, canvas) and the company links with the nodes' places. A new order opens its session at once. Answers are chosen by
// the owner's words, never at random, so the end-to-end checks can follow them. Kept in memory. Never bundled in production (reached only
// through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

import { conversationFiles, conversationClosed, conversationSay, presentAdd, presentDrop, sessionConversation } from './mock-v32';

const json = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const NOW = () => new Date().toISOString();
const NAME: Record<string, string> = { TY: 'تریدیار', FX: 'کوینه‌پرو اف‌ایکس', PC: 'پرو-چارت', HQ: 'هلدینگ' };

type Participant = { key: string; kind: 'holder' | 'person' | 'player'; title_fa: string; company: string | null };
type Task = { id: string; n: number; title_fa: string; state: 'todo' | 'doing' | 'done' | 'dropped'; by: 'owner' | 'agent'; who_fa: string | null; work_ref: string | null };
type S = {
  ref: string; conv: string; pace: 'auto' | 'step'; hidden: boolean; opened_at: string; closed_at: string | null; verdict: 'ok' | 'cancel' | null;
  participants: Participant[]; tasks: Task[]; turn: { question_fa: string; at: string; by: { kind: string; code: string; display_fa: string }; who_fa: string } | null;
  holder: { code: string; title_fa: string; company: string; company_fa: string } | null; persona: string; text_fa: string; last_at: string; state?: string;
};
const sessions = new Map<string, S>();
let taskSeq = 0;

const holderP = (title_fa: string, company: string | null, key: string): Participant => ({ key, kind: 'holder', title_fa, company });
const task = (n: number, title_fa: string, state: Task['state'], by: Task['by'] = 'agent', who_fa: string | null = null): Task => ({ id: `tk-${String(++taskSeq).padStart(4, '0')}`, n, title_fa, state, by, who_fa, work_ref: null });
const T = (day: string, hm: string) => `${day}T${hm}:00Z`;

function seed() {
  const mk = (o: Partial<S> & Pick<S, 'ref' | 'text_fa' | 'persona' | 'holder' | 'participants'>, lines: Array<[string, string]>) => {
    const conv = sessionConversation(o.persona, o.text_fa, o.ref, lines, o.opened_at ?? T('2026-11-05', '08:00'));
    for (const p of o.participants.slice(1)) presentAdd(conv.ref, p.key);
    sessions.set(o.ref, { conv: conv.ref, pace: 'auto', hidden: false, opened_at: T('2026-11-05', '08:00'), closed_at: null, verdict: null, tasks: [], turn: null, last_at: T('2026-11-05', '10:00'), ...o });
    return conv;
  };
  mk({
    ref: 'F-0008', text_fa: 'سه عنوان برای خبرنامه‌ی هفته‌ی تریدیار پیشنهاد بده', persona: 'ceo@TY', pace: 'step', last_at: T('2026-11-06', '06:10'),
    holder: { code: 'TY-CEO', title_fa: 'مدیرعامل', company: 'TY', company_fa: 'تریدیار' },
    participants: [holderP('مدیرعامل تریدیار', 'TY', 'ceo@TY')],
    tasks: [task(1, 'سه عنوان بنویس', 'done', 'agent', 'مدیرعامل'), task(2, 'عنوان برگزیده را با تو هماهنگ کن', 'doing', 'agent', 'مدیرعامل'), task(3, 'متن خبرنامه را بنویس', 'todo')],
    turn: { question_fa: 'کدام عنوان بهتر است: «هفته‌ای که بازار عوض شد»، «سه نکته برای حد ضرر» یا «کارمزد را دست‌کم نگیر»؟', at: T('2026-11-06', '06:10'), by: { kind: 'employee', code: 'TY-CEO', display_fa: 'مدیرعامل تریدیار' }, who_fa: 'مدیرعامل تریدیار' },
  }, [
    ['owner', 'سه عنوان برای خبرنامه‌ی هفته‌ی تریدیار پیشنهاد بده؛ مرحله به مرحله با من جلو برو.'],
    ['ceo@TY', 'سلام مدیر کل. سه عنوان آماده کردم و قبل از نوشتن متن، نظر شما را میخواهم. کدام را بنویسم؟\n\n- هفته‌ای که بازار عوض شد\n- سه نکته برای حد ضرر\n- کارمزد را دست‌کم نگیر'],
  ]);
  mk({
    ref: 'F-0007', text_fa: 'برای تریدیار کلیپ بساز و منظم منتشر کن', persona: 'media_director@TY', last_at: T('2026-11-02', '12:06'),
    holder: { code: 'TY-MEDIA-MGR', title_fa: 'مدیر رسانه', company: 'TY', company_fa: 'تریدیار' },
    participants: [holderP('مدیر رسانه تریدیار', 'TY', 'media_director@TY'), { key: 'advisor', kind: 'person', title_fa: 'مشاور کل', company: null }],
    tasks: [task(1, 'نوشتن متن سه ریلز', 'done', 'agent', 'نویسنده'), task(2, 'ساخت سه ریلز', 'done', 'agent', 'سازنده‌ی ریلز'), task(3, 'مُهر سری انتشار', 'todo', 'owner'), task(4, 'استخدام مسئول انتشار', 'todo', 'owner')],
  }, [
    ['owner', 'برای تریدیار کلیپ بساز و منظم منتشر کن.'],
    ['media_director@TY', 'سه ریلز اول ساخته و بازبینی شد. برای انتشار منظم، دو چیز لازم است: مُهر سری انتشار و یک مسئول انتشار. هر دو پایین همین صفحه آماده است.'],
  ]);
  mk({
    ref: 'F-0005', text_fa: 'برای پرو-چارت سه پست معرفی ابزار تحلیل تکنیکال آماده کن', persona: 'media_director@PC', last_at: T('2026-11-02', '12:10'),
    holder: { code: 'PC-MEDIA-MGR', title_fa: 'مدیر رسانه', company: 'PC', company_fa: 'پرو-چارت' },
    participants: [holderP('مدیر رسانه پرو-چارت', 'PC', 'media_director@PC')],
    tasks: [task(1, 'پست اول', 'done'), task(2, 'پست دوم', 'done'), task(3, 'پست سوم', 'doing')],
  }, [
    ['owner', 'برای پرو-چارت سه پست معرفی ابزار تحلیل تکنیکال آماده کن.'],
    ['media_director@PC', 'دو پست از سه آماده است. پست سوم به کمی بودجه‌ی بیشتر نیاز دارد؛ دکمه‌ی افزودن بودجه همین‌جاست.'],
  ]);
  mk({
    ref: 'F-0006', text_fa: 'یک مقاله‌ی سئو برای FX درباره‌ی آموزش فارکس برای تازه‌کارها', persona: 'media_director@FX', last_at: T('2026-11-01', '06:20'),
    holder: { code: 'FX-MEDIA-MGR', title_fa: 'مدیر رسانه', company: 'FX', company_fa: 'کوینه‌پرو اف‌ایکس' },
    participants: [holderP('مدیر رسانه اف‌ایکس', 'FX', 'media_director@FX'), { key: 'player:gpt', kind: 'player', title_fa: 'جی‌پی‌تی', company: null }],
    tasks: [task(1, 'نوشتن مقاله', 'done', 'agent', 'نویسنده'), task(2, 'بازبینی و انتشار', 'done', 'agent', 'مدیر رسانه')],
  }, [
    ['owner', 'یک مقاله‌ی سئو برای FX درباره‌ی آموزش فارکس برای تازه‌کارها.'],
    ['media_director@FX', 'مقاله نوشته و در وبلاگ منتشر شد. اگر خروجی را پسندیدی، جلسه را تأیید و ببند.'],
  ]);
  mk({
    ref: 'F-0004', text_fa: 'گزارش هزینه‌ی تبلیغات اکتبر', persona: 'advisor', last_at: T('2026-10-28', '15:00'), closed_at: T('2026-10-28', '15:30'), verdict: 'ok',
    holder: null, participants: [holderP('مشاور کل', null, 'advisor')], tasks: [task(1, 'جمع کردن عددها', 'done'), task(2, 'نوشتن گزارش', 'done')],
  }, [
    ['owner', 'گزارش هزینه‌ی تبلیغات اکتبر را بده.'],
    ['advisor', 'تبلیغات اکتبر 220 دلار شد؛ بیشترین سهم با تریدیار بود. گزارش کامل ضمیمه است.'],
  ]);
  conversationClosed(sessions.get('F-0004')!.conv, T('2026-10-28', '15:30'));
}
seed();

// ---------------------------------------------------------------------------------------------------- the report
function badgeOf(s: S, rep: any): { badge: 'your_turn' | 'ready' | 'stuck' | 'moving' | 'closed'; reason_fa: string } {
  if (s.closed_at) return { badge: 'closed', reason_fa: s.verdict === 'cancel' ? 'لغو شد و بایگانی شد.' : 'تأیید شد و بایگانی شد.' };
  if (s.turn) return { badge: 'your_turn', reason_fa: `${s.turn.who_fa} میپرسد: ${s.turn.question_fa.slice(0, 60)}${s.turn.question_fa.length > 60 ? '…' : ''}` };
  if (rep?.state === 'delivered') return { badge: 'ready', reason_fa: 'کار تمام شده؛ منتظر تأیید توست.' };
  const fixable = (rep?.blockers ?? []).find((b: any) => b.fix);
  if (fixable) return { badge: 'your_turn', reason_fa: `${fixable.title_fa}؛ رفعش با توست.` };
  if ((rep?.blockers ?? []).length) return { badge: 'stuck', reason_fa: rep.blockers[0].title_fa };
  return { badge: 'moving', reason_fa: rep?.steps?.at(-1)?.what_fa ?? 'کار در جریان است.' };
}
function briefOf(rep: any, s: S) {
  const last = rep?.steps?.at(-1)?.what_fa;
  return {
    done_fa: rep?.summary?.done_fa ?? s.tasks.filter((t) => t.state === 'done').at(-1)?.title_fa ?? 'هنوز چیزی تمام نشده.',
    now_fa: s.turn ? 'منتظر جواب توست.' : rep?.blockers?.[0]?.title_fa ?? last ?? 'کار در جریان است.',
    need_fa: s.turn ? 'جواب سؤال بالا' : rep?.summary?.need_fa ?? rep?.blockers?.find((b: any) => b.fix)?.fix?.label_fa ?? 'چیزی از تو لازم نیست.',
  };
}
const counts = (s: S) => ({ done: s.tasks.filter((t) => t.state === 'done').length, total: s.tasks.filter((t) => t.state !== 'dropped').length });

/** The report of an order the session module made itself (the others come from §29's fixtures, decorated). */
const LOCAL: Record<string, any> = {
  'F-0008': {
    ref: 'F-0008', text_fa: 'سه عنوان برای خبرنامه‌ی هفته‌ی تریدیار پیشنهاد بده', at: T('2026-11-05', '08:00'), state: 'waiting',
    ack: { at: T('2026-11-05', '08:01'), by: { kind: 'employee', code: 'TY-CEO', display_fa: 'مدیرعامل تریدیار' }, plan_fa: 'مدیرعامل سه عنوان مینویسد، با مدیر کل یکی را انتخاب میکند و بعد متن را مینویسد.', assigned: [{ company: 'TY', code: 'TY-CEO', title_fa: 'مدیرعامل' }], due_at: null },
    route: { companies: ['TY'], department: null, collaborators: [], output_kind: 'answer', budget_tokens: 60_000, mode: 'single', player: 'auto' },
    steps: [{ at: T('2026-11-05', '08:00'), who_fa: 'منشی هلدینگ', what_fa: 'فرمان را به مدیرعامل تریدیار سپرد.' }, { at: T('2026-11-06', '06:10'), who_fa: 'مدیرعامل تریدیار', what_fa: 'سه عنوان نوشت و از شما سؤال کرد.' }],
    blockers: [], outputs: [], summary: null, updated_at: T('2026-11-06', '06:10'),
  },
  'F-0004': {
    ref: 'F-0004', text_fa: 'گزارش هزینه‌ی تبلیغات اکتبر', at: T('2026-10-28', '14:00'), state: 'delivered',
    ack: null, route: { companies: ['HQ'], department: null, collaborators: [], output_kind: 'report', budget_tokens: 80_000, mode: 'single', player: 'auto' },
    steps: [{ at: T('2026-10-28', '14:00'), who_fa: 'مشاور کل', what_fa: 'عددها را جمع کرد.' }, { at: T('2026-10-28', '15:00'), who_fa: 'مشاور کل', what_fa: 'گزارش را نوشت.' }],
    blockers: [], outputs: [], summary: { done_fa: 'تبلیغات اکتبر 220 دلار شد؛ گزارش نوشته شد.', left_fa: '', need_fa: '' }, updated_at: T('2026-10-28', '15:30'),
  },
};

function decorate(rep: any, s: S) {
  const { badge, reason_fa } = badgeOf(s, rep);
  const state = s.closed_at ? (s.verdict === 'cancel' ? 'cancelled' : 'delivered') : rep.state;
  return {
    ...rep, state, pace: s.pace, talk_ref: s.conv, conversation_ref: s.conv, turn: s.turn,
    session: { state: s.closed_at ? 'closed' : 'open', badge, reason_fa, closed_at: s.closed_at, hidden: s.hidden },
    brief: briefOf(rep, s), tasks: s.tasks, participants: s.participants,
    // ⟨1.18⟩ §36.3 the files of the owner's turns belong to the order, newest first
    files: conversationFiles(s.conv),
  };
}
const card = (s: S, rep: any) => {
  const { badge, reason_fa } = badgeOf(s, rep);
  return {
    ref: s.ref, conversation_ref: s.conv, title_fa: s.text_fa.slice(0, 80), holder: s.holder, badge, reason_fa, brief: briefOf(rep, s), pace: s.pace,
    participants: s.participants, tasks: counts(s), opened_at: s.opened_at, last_at: s.last_at, closed_at: s.closed_at, hidden: s.hidden,
  };
};

// ------------------------------------------------------------------------------------------------- the canvas
const nodePlace: Record<string, { x: number | null; y: number | null }> = { HQ: { x: null, y: null }, TY: { x: null, y: null }, FX: { x: 0.82, y: 0.3 }, PC: { x: null, y: null } };
const LINE: Record<string, string> = { HQ: 'هلدینگ · مرکز', TY: 'تریدیار · رسانه و رشد', FX: 'اف‌ایکس · مقاله و سئو', PC: 'پرو-چارت · پست و ابزار' };
type Link = { id: string; from: string; to: string; kind: string; purpose_fa: string; state: 'on' | 'off'; open_works: number; updated_at: string };
const links: Link[] = [
  { id: 'lk-0001', from: 'TY', to: 'PC', kind: 'publishes', purpose_fa: 'ریلزهای تریدیار را روی صفحه‌ی پرو-چارت هم منتشر میکند.', state: 'on', open_works: 2, updated_at: T('2026-11-04', '10:00') },
  { id: 'lk-0002', from: 'PC', to: 'TY', kind: 'feeds', purpose_fa: 'عددهای استفاده‌ی ابزار را برای محتوای تریدیار میدهد.', state: 'on', open_works: 0, updated_at: T('2026-11-04', '10:05') },
  { id: 'lk-0003', from: 'FX', to: 'TY', kind: 'supports', purpose_fa: 'پشتیبانی مشتری‌های تریدیار را هم جواب میدهد.', state: 'off', open_works: 0, updated_at: T('2026-11-03', '09:00') },
];
let linkSeq = 3;
const canvas = () => ({
  nodes: Object.keys(NAME).map((code) => ({
    code, name_fa: NAME[code]!, kind: code === 'HQ' ? 'holding' : 'company', x: nodePlace[code]!.x, y: nodePlace[code]!.y, line_fa: LINE[code]!,
    open_sessions: [...sessions.values()].filter((s) => !s.closed_at && s.holder?.company === code).length,
  })),
  links,
});

// --------------------------------------------------------------------------------------------------- persons
const COMPANY_OF = (k: string) => (k.includes('@') ? k.split('@')[1]! : null);
const ROLE_FA: Record<string, string> = { ceo: 'مدیرعامل', cto: 'مدیر فنی', media_director: 'مدیر رسانه', content_lead: 'مدیر محتوا' };
const FIXED_FA: Record<string, string> = { advisor: 'مشاور کل', overseer: 'ناظر کل', assistant: 'دستیار شخصی', secretary: 'منشی هلدینگ' };
const PLAYER_FA: Record<string, string> = { gpt: 'جی‌پی‌تی', gemini: 'جمنای', deepseek: 'دیپ‌سیک' };
function personOf(key: string): Participant | null {
  if (FIXED_FA[key]) return { key, kind: 'person', title_fa: FIXED_FA[key]!, company: null };
  const m = /^([a-z_]+)@([A-Z]{2,5})$/.exec(key);
  if (m && ROLE_FA[m[1]!]) return { key, kind: 'person', title_fa: `${ROLE_FA[m[1]!]} ${NAME[m[2]!] ?? m[2]}`, company: COMPANY_OF(key) };
  return null;
}

function open(order: { ref: string; text: string; company?: string }): S {
  const company = order.company ?? 'TY';
  const conv = sessionConversation(`ceo@${company}`, order.text.slice(0, 80), order.ref, [
    ['owner', order.text],
    [`ceo@${company}`, `سلام مدیر کل. فرمانت را گرفتم و کار را شروع میکنم. هر وقت خواستی همین‌جا بگو چه بکنم یا چه را عوض کنم.`],
  ], NOW());
  const s: S = {
    ref: order.ref, conv: conv.ref, pace: /مرحله به مرحله|قدم به قدم|گام به گام|با فرمان من/.test(order.text) ? 'step' : 'auto', hidden: false, opened_at: NOW(), closed_at: null, verdict: null,
    participants: [holderP(`مدیرعامل ${NAME[company] ?? company}`, company, `ceo@${company}`)], tasks: [], turn: null,
    holder: { code: `${company}-CEO`, title_fa: 'مدیرعامل', company, company_fa: NAME[company] ?? company }, persona: `ceo@${company}`, text_fa: order.text.slice(0, 80), last_at: NOW(),
  };
  sessions.set(order.ref, s);
  return s;
}

// ---------------------------------------------------------------------------------------------------- router
type Next = (r: Request) => Promise<Response>;
export async function handle34(req: Request, p: string, q: URLSearchParams, next: Next): Promise<Response | null> {
  const m = req.method;
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;
  const reportOf = async (ref: string): Promise<any | null> => {
    if (LOCAL[ref]) return LOCAL[ref];
    const res = await next(new Request(new URL(`/api/v1/orders/${ref}/report`, req.url)));
    return res.ok ? res.json() : null;
  };
  const sync = async (s: S) => {
    // The report is read fresh each time; what the session changes in it is carried by the session itself.
    const rep = await reportOf(s.ref);
    return rep ? decorate(rep, s) : null;
  };

  // --------------------------------------------------------------------------------------------- the office
  if (p === '/office' && m === 'GET') {
    const cards = await Promise.all([...sessions.values()].filter((s) => !s.closed_at && !s.hidden).map(async (s) => card(s, await reportOf(s.ref))));
    const home = await (await next(new Request(new URL('/api/v1/home', req.url)))).json().catch(() => ({ cards: {}, critical: [] })) as any;
    const decs = await (await next(new Request(new URL('/api/v1/decisions?status=pending&limit=10', req.url)))).json().catch(() => ({ items: [] })) as any;
    const items = Array.isArray(decs) ? decs : decs.items ?? [];
    return json({
      sessions: cards.sort((a, b) => ['your_turn', 'ready', 'stuck', 'moving'].indexOf(a.badge) - ['your_turn', 'ready', 'stuck', 'moving'].indexOf(b.badge) || Date.parse(b.last_at) - Date.parse(a.last_at)).slice(0, 30),
      approvals: items.slice(0, 10), approvals_total: decs.total ?? items.length,
      money: { revenue_month_usd: 4210, spend_month_usd: 412.6, budget_month_usd: 1200, line_fa: 'این ماه 4,210 دلار درآمد و 413 دلار خرج داشتیم؛ 34٪ از سقف ماه رفته.' },
      critical: home.critical ?? [], suggestions: [home.cards?.effective, home.cards?.good].filter(Boolean), canvas: canvas(),
    });
  }

  // ------------------------------------------------------------------------------------------ the links
  if (p === '/links' && m === 'GET') return json(canvas());
  if (p === '/links' && m === 'POST') {
    const b = await body<any>();
    if (!NAME[b.from] || !NAME[b.to] || b.from === b.to) return problem(422, 'validation_failed', 'دو شرکت جدا انتخاب کن.');
    if (!b.purpose_fa?.trim()) return problem(422, 'validation_failed', 'بنویس این ارتباط برای چیست.');
    const l: Link = { id: `lk-${String(++linkSeq).padStart(4, '0')}`, from: b.from, to: b.to, kind: b.kind ?? 'serves', purpose_fa: b.purpose_fa.trim(), state: 'on', open_works: 0, updated_at: NOW() };
    links.push(l);
    return json(l, 201);
  }
  const lk = /^\/links\/([^/]+)$/.exec(p);
  if (lk && m === 'PATCH') {
    const l = links.find((x) => x.id === lk[1]);
    if (!l) return problem(404, 'not_found', 'این ارتباط پیدا نشد.');
    const b = await body<any>();
    if (b.kind) l.kind = b.kind;
    if (typeof b.purpose_fa === 'string' && b.purpose_fa.trim()) l.purpose_fa = b.purpose_fa.trim();
    if (b.state) l.state = b.state;
    l.updated_at = NOW();
    return json(l);
  }
  const nd = /^\/canvas\/nodes\/([^/]+)$/.exec(p);
  if (nd && m === 'PUT') {
    if (!nodePlace[nd[1]!]) return problem(404, 'not_found', 'این شرکت پیدا نشد.');
    const b = await body<any>();
    if (typeof b.x !== 'number' || typeof b.y !== 'number' || b.x < 0 || b.x > 1 || b.y < 0 || b.y > 1) return problem(422, 'validation_failed', 'جای شرکت باید روی بوم باشد.');
    nodePlace[nd[1]!] = { x: b.x, y: b.y };
    return json(canvas().nodes.find((n) => n.code === nd[1]));
  }

  // ---------------------------------------------------------------------------------------------- sessions
  if (p === '/sessions' && m === 'GET') {
    const st = q.get('state') ?? 'open';
    const all = await Promise.all([...sessions.values()].map(async (s) => card(s, await reportOf(s.ref))));
    const items = all.filter((c) => (st === 'all' ? true : st === 'closed' ? !!c.closed_at && !c.hidden : !c.closed_at && !c.hidden));
    const rank = ['your_turn', 'ready', 'stuck', 'moving', 'closed'];
    items.sort((a, b) => rank.indexOf(a.badge) - rank.indexOf(b.badge) || Date.parse(b.last_at) - Date.parse(a.last_at));
    return json({ items, next_cursor: null });
  }

  // A new order opens its session; a suggestion that is run does too.
  if (p === '/orders' && m === 'POST') {
    const b = await body<any>();
    const res = await next(req);
    if (!res.ok) return res;
    const out = (await res.clone().json()) as any;
    const s = sessions.get(out.ref) ?? open({ ref: out.ref, text: String(b.text ?? ''), company: out.routes?.[0]?.company });
    return json({ ...out, talk_ref: s.conv, pace: s.pace }, 201);
  }
  const sg = /^\/home\/suggestions\/([^/]+)$/.exec(p);
  if (sg && m === 'POST') {
    const res = await next(req);
    if (!res.ok) return res;
    const out = (await res.clone().json()) as any;
    if (out.order_ref && !sessions.has(out.order_ref)) open({ ref: out.order_ref, text: String(out.title_fa ?? 'پیشنهاد'), company: out.company });
    return res;
  }

  const o = /^\/orders\/(F-\d+)(?:\/([a-z]+)(?:\/([^/]+))?)?$/.exec(p);
  if (!o) return null;
  const s = sessions.get(o[1]!);
  const act = o[2];
  if (!s) {
    // An order of §29's fixtures that has no session yet gets one when it is first read (every order is a session).
    if (act === 'report' && m === 'GET') {
      const rep = await reportOf(o[1]!);
      if (!rep) return null;
      const made = open({ ref: o[1]!, text: rep.text_fa });
      return json(decorate(rep, made));
    }
    return null;
  }
  const touch = () => { s.last_at = NOW(); };

  if (act === 'report' && m === 'GET') {
    const rep = await reportOf(s.ref);
    if (!rep) return problem(404, 'not_found', 'گزارش این فرمان پیدا نشد.');
    return json(decorate(rep, s));
  }
  if (act === 'talk' && m === 'POST') return json({ conversation_ref: s.conv }, 201);
  if (act === 'reply' && m === 'POST') {
    const b = await body<any>();
    if (s.closed_at) return problem(409, 'conflict', 'این جلسه بسته شده؛ اول بازش کن.');
    if (!String(b.text ?? '').trim()) return problem(422, 'validation_failed', 'جوابت را بنویس.');
    s.turn = null; touch();
    conversationSay(s.conv, 'owner', String(b.text).trim());
    conversationSay(s.conv, s.participants[0]!.key, 'ممنون، همین را انجام میدهم و نتیجه را همین‌جا میگویم.');
    if (LOCAL[s.ref]) { LOCAL[s.ref].steps.push({ at: NOW(), who_fa: 'مدیر کل', what_fa: String(b.text).trim() }); LOCAL[s.ref].state = 'in_progress'; }
    return json(await sync(s));
  }
  if (act === 'participants') {
    if (s.closed_at && m !== 'GET') return problem(409, 'conflict', 'این جلسه بسته شده؛ اول بازش کن.');
    if (m === 'POST') {
      const b = await body<any>();
      let part: Participant | null = null;
      if (b.kind === 'player') {
        const k = String(b.key).replace(/^player:/, '');
        if (!PLAYER_FA[k]) return problem(422, 'validation_failed', 'این مدل را نمیشناسم.');
        if (k === 'deepseek') return problem(409, 'player_signed_out', 'دیپ‌سیک الان وارد نیست؛ از «بازیکن‌های ذخیره» واردش کن.');
        part = { key: `player:${k}`, kind: 'player', title_fa: PLAYER_FA[k]!, company: null };
      } else part = personOf(String(b.key));
      if (!part) return problem(422, 'validation_failed', 'این آدم را نمیشناسم.');
      if (!s.participants.some((x) => x.key === part!.key)) { s.participants.push(part); presentAdd(s.conv, part.key); conversationSay(s.conv, s.participants[0]!.key, `${part.title_fa} به جلسه آمد.`); }
      touch();
      return json(await sync(s));
    }
    if (m === 'DELETE' && o[3]) {
      const key = decodeURIComponent(o[3]);
      const x = s.participants.find((y) => y.key === key);
      if (!x) return problem(404, 'not_found', 'این نفر در جلسه نیست.');
      if (x.kind === 'holder') return problem(409, 'conflict', 'مسئول فرمان را نمیشود بیرون برد.');
      s.participants = s.participants.filter((y) => y.key !== key); presentDrop(s.conv, key); touch();
      return json(await sync(s));
    }
  }
  if (act === 'tasks') {
    if (m === 'POST') {
      const b = await body<any>();
      if (!String(b.title_fa ?? '').trim()) return problem(422, 'validation_failed', 'عنوان کار را بنویس.');
      const t = task(s.tasks.length + 1, String(b.title_fa).trim(), 'todo', 'owner');
      s.tasks.push(t); touch();
      return json(t, 201);
    }
    if (m === 'PATCH' && o[3]) {
      const t = s.tasks.find((x) => x.id === decodeURIComponent(o[3]!));
      if (!t) return problem(404, 'not_found', 'این کار پیدا نشد.');
      const b = await body<any>();
      if (typeof b.title_fa === 'string' && b.title_fa.trim()) t.title_fa = b.title_fa.trim();
      if (b.state) t.state = b.state;
      if (typeof b.n === 'number') t.n = b.n;
      touch();
      return json(t);
    }
  }
  if (act === 'close' && m === 'POST') {
    const b = await body<any>();
    if (b.verdict !== 'ok' && b.verdict !== 'cancel') return problem(422, 'validation_failed', 'یا تأیید کن یا لغو.');
    s.closed_at = NOW(); s.verdict = b.verdict; s.turn = null; touch();
    conversationClosed(s.conv, s.closed_at);
    return json(await sync(s));
  }
  if (act === 'reopen' && m === 'POST') {
    s.closed_at = null; s.verdict = null; touch(); conversationClosed(s.conv, null);
    return json(await sync(s));
  }
  if (act === 'pace' && m === 'POST') {
    const b = await body<any>();
    if (b.pace !== 'auto' && b.pace !== 'step') return problem(422, 'validation_failed', 'روش کار یا «با من» است یا «خودکار».');
    s.pace = b.pace; touch();
    return json(await sync(s));
  }
  if ((act === 'hide' || act === 'unhide') && m === 'POST') {
    s.hidden = act === 'hide'; touch();
    return json(await sync(s));
  }
  return null;
}
