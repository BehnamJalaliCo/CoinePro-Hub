// Development-only fixtures (npm run dev:mock) for the Android app's 0.3.0–0.6.0 on the web; never bundled in production (the client
// reaches it only when NEXT_PUBLIC_HQ_MOCK=1). It answers what is new and hands everything else to the older fixtures (./mock), the way
// the Android debug build layers its Demo*.kt over the same fixtures — the same demo data, word for word:
//
// - Outputs ⟨1.7.3⟩ (DemoOutputs.kt): `category`, `seen_at`, `filed_as`, every filter, `POST /deliverables/seen` and `/file`, the morning
//   report with its table of companies, and two earlier days.
// - The owner's orders ⟨1.7.4⟩ (DemoOrders.kt): seven orders in every stage with their sub-works, events, runs and outputs; `created_by`,
//   `/tree-events`; a new order moves on its own; the live stream carries `work.*`, `run.*` and `deliverable.created`.
// - Notifications (DemoNotifications.kt): the overseer's hourly finding raised five times, a meeting, a founding, a read history;
//   `POST /notifications/read {ids}` ⟨1.7.5⟩.
// - Control (DemoControl.kt): Pro-Chart stopped by its CEO, CoinePro FX's deploys closed by the release pipeline, the switches' history
//   with reasons (`GET /audit?company&action`, `GET /owner/interactions?kind=control`); releasing and lifting need the step-up.
// - Companies (DemoCompanies.kt): `DELETE /companies/{code}` (409 for a company with a history), `PATCH` to archive; ⟨1.7.5⟩ a `blank`
//   founding registers a draft company.
// - The demo's live stream (DemoLive): runs starting and finishing, outputs and cards; with the tab hidden, a card and an urgent alert.
// - ⟨1.10⟩ §28: several outputs filed at once (`POST /deliverables/file {refs}`) or deleted for good (`DELETE /deliverables {refs}`, with
//   the step-up; one Audit row each), the TradeYar catalogue's output, and an order given to the council where only Claude answered
//   (`GET /work/{id}/council`: GPT refused its model in English, Gemini's recipe failed as raw JSON, DeepSeek was off). ./mock-v28 has
//   the catalogue, the watch and the client error reports.

// Through the alias, so a production build (where the alias points elsewhere) could never pull the fixtures in.
import { handle as base } from '@/lib/api/mock';
import { handle28 } from './mock-v28';

const json = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const page = (items: unknown[]) => ({ items, next_cursor: null });
const OWNER = { kind: 'owner', code: 'owner', display_fa: 'مدیر کل' };
const nowIso = () => new Date().toISOString();
const at = (min: number) => new Date(Date.now() - min * 60_000).toISOString();
const ahead = (min: number) => new Date(Date.now() + min * 60_000).toISOString();
const T0 = Date.now();
const ago = (min: number) => new Date(T0 - min * 60_000).toISOString();
async function baseJson<T>(req: Request, path: string): Promise<T> {
  const u = new URL(req.url);
  return (await (await base(new Request(new URL(`/api/v1${path}`, u.origin), { headers: req.headers }))).json()) as T;
}

// ==================================================================================================== the stream ==
type Ev = { id: string; type: string; at: string; company: string | null; ref: string | null; data: Record<string, unknown> };
let evSeq = 0;
const queue: Ev[] = [];
const ev = (company: string | null, type: string, ref: string | null, data: Record<string, unknown> = {}): Ev => ({ id: `d21-${++evSeq}`, type, at: nowIso(), company, ref, data });

// ==================================================================================================== control ==
type Switch = { scope: string; company: string; state: string; changed_at: string; changed_by: string | null; reason: string | null };
const control: { holding: Switch; companies: Switch[]; deploy_freezes: Array<{ company: string; until: string; reason: string; created_by: string }> } = {
  holding: { scope: 'holding', company: 'HQ', state: 'released', changed_at: ago(60 * 24 * 6 - 12), changed_by: 'owner', reason: 'آزمایش تمام شد.' },
  companies: [
    { scope: 'company:TY', company: 'TY', state: 'released', changed_at: ago(60 * 72 - 70), changed_by: 'owner', reason: 'سقف روزانه‌ی کمپین درست شد.' },
    { scope: 'company:FX', company: 'FX', state: 'released', changed_at: ago(60 * 24 * 9), changed_by: null, reason: null },
    // Pro-Chart: stopped by its CEO, who found the terminal's prices wrong in production.
    { scope: 'company:PC', company: 'PC', state: 'engaged', changed_at: ago(38), changed_by: 'PC-CEO', reason: 'قیمت‌های ترمینال در تولید اشتباه نمایش داده میشد؛ تا رفع خطا متوقف شد.' },
  ],
  // CoinePro FX: the release pipeline closed its deploys while a release is out.
  deploy_freezes: [{ company: 'FX', until: ahead(95), reason: 'انتشار در جریان', created_by: 'pipeline' }],
};
let auditSeq = 5000;
const audit: any[] = [];
const interactions: any[] = [];
function row(company: string, action: string, kind: string, ref: string, actor: any, when: string, summary: string, stepUp = false) {
  audit.push({ seq: auditSeq++, at: when, actor, principal_kind: actor.kind, company, action, action_class: 'A2', target: { kind, ref }, request_id: null, ip_hash: null, step_up: stepUp, summary, prev_hash: '…', hash: '…' });
}
function interaction(company: string, action: string, kind: string, ref: string, when: string, data: Record<string, unknown>) {
  interactions.push({ id: `i${auditSeq++}`, at: when, company, kind: 'control', action, target: { kind, ref }, data });
}
const agent = (code: string, display_fa: string) => ({ kind: 'agent', code, display_fa });
row('PC', 'kill_switch.engage', 'kill_switch', 'company:PC', agent('PC-CEO', 'مدیرعامل پرو-چارت'), ago(38), `changed: engaged: ${control.companies[2]!.reason}`);
row('HQ', 'kill_switch.release', 'kill_switch', 'holding', OWNER, ago(60 * 24 * 6 - 12), 'changed: released: آزمایش تمام شد.', true);
row('HQ', 'kill_switch.engage', 'kill_switch', 'holding', OWNER, ago(60 * 24 * 6), 'changed: engaged: آزمایش کلید توقف کل هلدینگ');
interaction('HQ', 'kill_switch.set', 'kill_switch', 'holding', ago(60 * 24 * 6 - 12), { state: 'released', reason: 'آزمایش تمام شد.' });
interaction('HQ', 'kill_switch.set', 'kill_switch', 'holding', ago(60 * 24 * 6), { state: 'engaged', reason: 'آزمایش کلید توقف کل هلدینگ' });
row('TY', 'kill_switch.release', 'kill_switch', 'company:TY', OWNER, ago(60 * 72 - 70), 'changed: released: سقف روزانه‌ی کمپین درست شد.', true);
row('TY', 'kill_switch.engage', 'kill_switch', 'company:TY', OWNER, ago(60 * 72), 'changed: engaged: مصرف کمپین پاییز از کنترل خارج شد.');
interaction('TY', 'kill_switch.set', 'kill_switch', 'company:TY', ago(60 * 72 - 70), { state: 'released', reason: 'سقف روزانه‌ی کمپین درست شد.' });
interaction('TY', 'kill_switch.set', 'kill_switch', 'company:TY', ago(60 * 72), { state: 'engaged', reason: 'مصرف کمپین پاییز از کنترل خارج شد.' });
row('FX', 'deploy_freeze.set', 'company', 'FX', { kind: 'service', code: 'pipeline', display_fa: 'خط انتشار' }, ago(25), 'active: انتشار در جریان');
const stopped = () => new Set(control.companies.filter((c) => c.state === 'engaged').map((c) => c.company));

// =================================================================================================== companies ==
const removed = new Set<string>();
const archived = new Set<string>();
const added: any[] = [];
const versions: Record<string, number> = {};
function decorateCompany(c: any) {
  const sw = control.companies.find((k) => k.company === c.code);
  const fz = control.deploy_freezes.filter((f) => f.company === c.code && f.until > nowIso()).sort((a, b) => b.until.localeCompare(a.until))[0];
  return {
    ...c, kill_switch: c.kind === 'holding' ? control.holding.state : sw?.state ?? c.kill_switch, deploy_freeze_until: fz?.until ?? null,
    status: archived.has(c.code) ? 'archived' : c.status, version: versions[c.code] ?? c.version,
  };
}

// ==================================================================================================== outputs ==
const seen: Record<string, string> = {};
const filed: Record<string, string> = {};
let nextRecord = 97;
const sysProducer = { code: 'HQ-SYS', company: 'HQ', kind: 'system', department: null, title_fa: 'سیستم' };
const emp = (code: string, company: string, kind: string, department: string | null, title_fa: string) => ({ code, company, kind, department, title_fa });
const MORNING = `# گزارش صبحگاهی — شنبه ۲۵ مهر ۱۴۰۵ (2026-10-17)

> نسخه‌ی قاعده‌محور، بدون مدل: همه‌ی عددها مستقیم از دیتابیس هاب.

## صندوق‌ها
- **کارتابل تصمیم:** 11 مورد در انتظار (ریسک بالا: 1، ریسک متوسط: 4، ریسک کم: 6)
- **کارتابل خروجی:** 6 خروجی در ۲۴ ساعت گذشته؛ 5 خروجی هنوز امتیاز ندارد
- **پیام‌ها:** 3 پیام نخوانده
- **یادآوری کارتابل:** 11 کارت منتظر تو: 7 زیر ۲۴ ساعت، 3 بین ۱ تا ۳ روز، 1 بین ۳ تا ۷ روز، 0 بیش از ۷ روز.
- **هدررفت دیروز:** 182400 توکن ($1.84)، 6.2% از کل روز

## شرکت‌ها
| شرکت | تصمیم در انتظار | کار باز | عقب‌افتاده | خروجی تازه | فراخوانی مدل دیروز | توکن دیروز | هزینه‌ی دیروز (USD) | کلید توقف |
|---|---|---|---|---|---|---|---|---|
| هلدینگ کوینه‌پرو (HQ) | 3 | 12 | 1 | 2 | 412 | 1840221 | 4.1200 | — |
| تریدیار (TY) | 4 | 18 | 2 | 1 | 655 | 2210934 | 6.0310 | — |
| کوینه‌پرو FX (FX) | 3 | 9 | 0 | 2 | 389 | 1301229 | 3.2400 | — |
| پرو-چارت (PC) | 1 | 7 | 0 | 1 | 120 | 402331 | 0.9900 | فعال |

## بودجه‌ها
- TY · company:TY (month): به 72٪ رسیده

## بازیکن‌های ذخیره
- ChatGPT Plus: 41 فراخوانی این ماه، معادل $12.40
- Google AI Pro: سهمیه‌ی امروز تمام شد

**کلید توقف فعال:** PC
`;
function deliverable(ref: string, company: string, work: string, producer: any, title: string, summary: string, body: string, when: string, produced?: any) {
  return {
    id: `o-${ref.toLowerCase()}`, ref, company, work_id: `w-${work.toLowerCase()}`, work_ref: work, producer, title, summary, body, attachments: [], evidence: [],
    produced_with: produced ?? { model: 'claude-sonnet-5-5', effort: 'medium', label_fa: 'Sonnet 5.5 · medium' }, usage: {}, rating: null, created_at: when,
  };
}
const extraOutputs: any[] = [
  deliverable('O-000032', 'HQ', 'W-000131', sysProducer, 'گزارش صبحگاهی ۱۴۰۵/۰۷/۲۵ / 2026-10-17', '11 تصمیم در انتظار، 6 خروجی تازه (5 بی‌امتیاز)، 3 پیام نخوانده.', MORNING, ago(150), { label_fa: 'قاعده‌محور، بدون مدل', provider: 'rules' }),
  deliverable('O-000028', 'TY', 'W-000118', emp('TY-GROWTH-02', 'TY', 'employee', 'GROWTH', 'تحلیلگر کمپین'), 'تحلیل نرخ تبدیل کمپین پاییز',
    'نرخ تبدیل ثبت‌نام به واریز در کمپین پاییز 3.1٪ بود، 0.6 واحد بالاتر از تابستان؛ بیشترین افت در مرحله‌ی تأیید هویت.',
    '## یافته‌ها\n- نرخ تبدیل: **3.1%** (تابستان 2.5%)\n- بیشترین افت: تأیید هویت (41% رها)\n\n## پیشنهاد\n1. پیام یادآوری ۲ ساعت بعد\n2. راهنمای تصویری تأیید هویت', ago(60 * 24 + 200)),
  deliverable('O-000026', 'FX', 'W-000112', emp('FX-QUANT-02', 'FX', 'employee', 'QUANT', 'پایشگر سیگنال'), 'گزارش هفتگی دقت سیگنال‌ها',
    'دقت هفته 68٪، در محدوده‌ی هدف؛ دو سیگنال طلا بی‌دلیل منقضی شدند.', 'دقت هفته **68%**؛ جزئیات در پیوست پایش.', ago(3 * 60 * 24 + 90)),
];
// The demo's state: the earlier days read (one filed in the archive), and the polished morning report read this morning.
// ⟨1.10⟩ The deep catalogue of TradeYar's server (§28.2), also delivered to the owner.
extraOutputs.push(deliverable('O-000040', 'TY', 'W-000202', emp('TY-CEO', 'TY', 'ceo', null, 'مدیرعامل'), 'کاتالوگ کامل سرور تریدیار',
  '۹ کانتینر، ۱۴ گردش‌کار n8n، ۴۲ جدول، ۸۷ مسیر API و ۴ ریسک؛ دو ریسک جدی: گواهی رو به انقضا و پورت بی‌رمز روی شبکه‌ی خصوصی.',
  '## محصولات و سرویس‌ها\n۹ کانتینر در ۳ پروژه‌ی compose.\n\n## ریسک‌ها\n- گواهی `api.tradeyar.com` تا ۹ روز دیگر\n- `node_exporter` بی‌رمز\n\nجدول‌های کامل در کاتالوگ شرکت و سند بایگانی AR-000094.', ago(60 * 26)));
filed['O-000040'] = 'AR-000094';
seen['O-000030'] = ago(240);
seen['O-000028'] = ago(60 * 24 + 100);
seen['O-000026'] = ago(3 * 60 * 24 + 30);
filed['O-000026'] = 'AR-000092';
/** Outputs of the orders below: their own pages only, so the list stays as the fixtures have it. */
const orderOutputs = new Map<string, any>();
/** ⟨1.10⟩ Deleted for good by the owner: gone from every list and page. */
const deleted = new Set<string>();
const outView = (d: any) => ({ ...d, category: d.producer?.code?.endsWith('-SYS') ? 'report' : 'work', seen_at: seen[d.ref] ?? null, filed_as: filed[d.ref] ?? null });
const dayOf = (iso: string) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(iso));
async function allOutputs(req: Request) {
  const b = await baseJson<{ items: any[] }>(req, '/deliverables');
  return [...b.items, ...extraOutputs, ...[...orderOutputs.values()].filter((d) => d.listed)].filter((d) => !deleted.has(d.ref)).map(outView).sort((a, b2) => b2.created_at.localeCompare(a.created_at));
}

// ==================================================================================================== orders ==
type Emp = { code: string; company: string; kind: string; department: string | null; title_fa: string };
type WEv = { at: string; kind: string; actor: string; actor_kind: string; data: Record<string, string> };
type Step = { at: string; summary: string; tool: string; ref: string };
type RunRec = { id: string; employee: string; state: string; started: string; finished: string | null; steps: Step[] };
type Node = {
  id: string; ref: string; company: string; title: string; brief: string; priority: string; status: string; assignee: Emp; owner: boolean; parent: Node | null;
  created: string; updated: string; progress: number | null; note: string | null; deliverable: string | null; events: WEv[]; runs: RunRec[];
  /** ⟨1.9⟩ §27.1: `council` runs the brief on every available player. */
  mode?: 'single' | 'council';
  player?: string;
  media?: string | null;
};
/** ⟨1.9⟩ §27.2 the councils of the demo's orders, by work ref. */
const councils = new Map<string, any>();
const beats: Array<[number, () => Ev[]]> = [];
let tickNo = 0;
function beat(t: number, f: () => Ev[]) { beats.push([t, f]); }
const nodes: Node[] = [];
let seq = 219;
let outSeq = 47;
const idOf = (n: number) => `0193b1c2-${n.toString(16).padStart(4, '0')}-7d4f-8a2e-${(0x5a1000 + n).toString(16).padStart(12, '0')}`;
const E = (code: string, company: string, kind: string, department: string | null, title_fa: string): Emp => ({ code, company, kind, department, title_fa });
const depthOf = (n: Node): number => (n.parent ? depthOf(n.parent) + 1 : n.assignee.kind === 'ceo' ? 0 : 1);
const later = (a: string, b: string) => (a > b ? a : b);

function order(ref: string, n: number, ceo: Emp, title: string, priority: string, status: string, min: number, brief: string): Node {
  const node: Node = { id: idOf(n), ref, company: ceo.company, title, brief, priority, status, assignee: ceo, owner: true, parent: null, created: ago(min), updated: ago(min), progress: null, note: null, deliverable: null, events: [], runs: [] };
  node.events.push({ at: ago(min), kind: 'created', actor: 'owner', actor_kind: 'owner', data: { assignee: ceo.code } });
  nodes.push(node);
  return node;
}
function child(parent: Node, ref: string, to: Emp, title: string, status: string, min: number, progress: number | null = null, note: string | null = null): Node {
  const node: Node = { id: idOf(100 + nodes.length), ref, company: parent.company, title, brief: '', priority: parent.priority, status, assignee: to, owner: false, parent, created: ago(min), updated: ago(min), progress, note, deliverable: null, events: [], runs: [] };
  node.events.push({ at: ago(min), kind: 'created', actor: parent.assignee.code, actor_kind: 'agent', data: { assignee: to.code } });
  parent.events.push({ at: ago(min), kind: 'delegated', actor: parent.assignee.code, actor_kind: 'agent', data: { child: ref, to: to.code } });
  nodes.push(node);
  return node;
}
function agentWork(ref: string, to: Emp, by: string, title: string, priority: string, status: string, min: number) {
  const node: Node = { id: idOf(200 + nodes.length), ref, company: to.company, title, brief: '', priority, status, assignee: to, owner: false, parent: null, created: ago(min), updated: ago(min), progress: null, note: null, deliverable: null, events: [], runs: [] };
  node.events.push({ at: ago(min), kind: 'created', actor: by, actor_kind: 'agent', data: { assignee: to.code } });
  nodes.push(node);
}
function accepted(n: Node, min: number) { n.events.push({ at: ago(min), kind: 'accepted', actor: n.assignee.code, actor_kind: 'agent', data: {} }); n.updated = later(n.updated, ago(min)); }
function progress(n: Node, min: number, pct: number) { n.events.push({ at: ago(min), kind: 'progress', actor: n.assignee.code, actor_kind: 'agent', data: { pct: String(pct) } }); n.updated = later(n.updated, ago(min)); }
function delivered(n: Node, min: number, out: string | null) { n.deliverable = out; n.events.push({ at: ago(min), kind: 'delivered', actor: n.assignee.code, actor_kind: 'agent', data: out ? { deliverable: out } : {} }); n.updated = later(n.updated, ago(min)); }
function failed(n: Node, min: number, reason: string) { n.events.push({ at: ago(min), kind: 'failed', actor: n.assignee.code, actor_kind: 'agent', data: { reason } }); n.updated = later(n.updated, ago(min)); }
function run(n: Node, from: number, to: number | null, state: string, ...steps: Array<[string, string]>) {
  const span = Math.max(from - (to ?? 0), steps.length);
  const list = steps.map(([s, tool], i) => ({ at: ago(from - (span * i) / Math.max(steps.length, 1)), summary: s, tool, ref: n.ref }));
  n.runs.push({ id: idOf(500 + nodes.length * 10 + n.runs.length), employee: n.assignee.code, state, started: ago(from), finished: to == null ? null : ago(to), steps: list });
  n.updated = later(n.updated, list[list.length - 1]?.at ?? ago(from));
}
function outputOf(n: Node, ref: string, title: string, summary: string, when: string, listed = false): string {
  orderOutputs.set(ref, { ...deliverable(ref, n.company, n.ref, n.assignee, title, summary, `## خلاصه\n${summary}\n\n## منبع‌ها\n- پایش ۳۰ روزه\n- گزارش‌های عمومی`, when), work_id: n.id, listed });
  return ref;
}

{
  const tyCeo = E('TY-CEO', 'TY', 'ceo', null, 'مدیرعامل');
  const tyGrowth = E('TY-GROWTH-MGR', 'TY', 'manager', 'GROWTH', 'مدیر رشد');
  const tySeo = E('TY-GROWTH-01', 'TY', 'employee', 'GROWTH', 'تحلیلگر سئوی فنی');
  const tyCamp = E('TY-GROWTH-02', 'TY', 'employee', 'GROWTH', 'تحلیلگر کمپین');
  const fxCeo = E('FX-CEO', 'FX', 'ceo', null, 'مدیرعامل');
  const fxTech = E('FX-TECH-MGR', 'FX', 'manager', 'TECH', 'مدیر فنی');
  const pcCeo = E('PC-CEO', 'PC', 'ceo', null, 'مدیرعامل');
  const pcGrowth = E('PC-GROWTH-MGR', 'PC', 'manager', 'GROWTH', 'مدیر رشد');
  const pcTech = E('PC-TECH-MGR', 'PC', 'manager', 'TECH', 'مدیر فنی');
  const hqAi = E('HQ-AIOPS-MGR', 'HQ', 'manager', 'AIOPS', 'مدیر عملیات AI');

  // At work: the CEO gave it to the growth manager, who split it between two analysts (one delivered, one at 40%).
  const o1 = order('W-000210', 1, tyCeo, 'گزارش رقبای صرافی در ۳۰ روز گذشته', 'P2', 'waiting', 190, 'کارمزد، کمپین‌ها و تغییرات محصول سه رقیب اصلی در ۳۰ روز گذشته؛ با منبع برای هر ادعا. تا پایان امروز.');
  accepted(o1, 186); run(o1, 186, 171, 'done', ['فرمان را خواند و دامنه‌ی کار را روشن کرد', 'work.read'], ['کار را به مدیر رشد سپرد', 'work.delegate']);
  const k1 = child(o1, 'W-000215', tyGrowth, 'تحلیل رقبا: کارمزد، کمپین و محصول', 'waiting', 170);
  accepted(k1, 160); run(k1, 160, 150, 'done', ['دو بخش کار را جدا کرد', 'work.read'], ['به دو تحلیلگر سپرد', 'work.delegate']);
  const g1 = child(k1, 'W-000217', tySeo, 'کارمزد و کمپین‌های سه رقیب', 'in_progress', 150, 40, 'دو رقیب از سه بررسی شد.');
  accepted(g1, 120); progress(g1, 25, 40);
  run(g1, 30, null, 'running', ['صفحه‌ی کارمزد رقیب اول را خواند', 'web.fetch'], ['جدول کارمزدها را ساخت', 'sheet.write'], ['کمپین‌های رقیب دوم را جمع کرد', 'web.fetch']);
  const g2 = child(k1, 'W-000218', tyCamp, 'تغییرات محصول سه رقیب', 'delivered', 150);
  accepted(g2, 140); run(g2, 140, 95, 'done', ['یادداشت‌های انتشار سه رقیب را خواند', 'web.fetch'], ['خلاصه را با منبع تحویل داد', 'work.deliver']);
  delivered(g2, 95, outputOf(g2, 'O-000046', 'تغییرات محصول سه رقیب، ۳۰ روز', 'دو رقیب کارمزد معامله‌ی آنی را کم کردند؛ یکی اپ موبایل تازه داد.', ago(95)));

  // Delegated: the FX CEO gave it to its technical manager, who has not started yet.
  const o2 = order('W-000211', 2, fxCeo, 'کاهش زمان بارگذاری داشبورد سیگنال', 'P1', 'waiting', 45, 'داشبورد سیگنال روی موبایل بیش از ۴ ثانیه بالا میاید؛ زیر ۲ ثانیه شود. بدون تغییر ظاهر.');
  accepted(o2, 42); run(o2, 42, 31, 'done', ['گزارش سرعت صفحه را خواند', 'health.sites'], ['کار را به مدیر فنی سپرد', 'work.delegate']);
  const k2 = child(o2, 'W-000214', fxTech, 'بهینه‌سازی بارگذاری داشبورد سیگنال', 'queued', 30);

  // Taken: the CEO is on it, nobody under it yet.
  const o3 = order('W-000212', 3, fxCeo, 'خلاصه‌ی عملکرد سیگنال‌های هفته', 'P3', 'in_progress', 14, 'دقت، سود و زیان و سیگنال‌های منقضی هفته، در یک صفحه.');
  accepted(o3, 12); run(o3, 11, null, 'running', ['گزارش‌های دقت هفته را خواند', 'knowledge.search'], ['سیگنال‌های منقضی را شمرد', 'db.read']);

  // Just given: in the queue.
  const o4 = order('W-000213', 4, tyCeo, 'پیش‌نویس سیاست بازگشت وجه کاربران', 'P3', 'queued', 3, 'یک صفحه، روشن و قابل انتشار؛ با موارد استثنا.');

  // Delivered: its output waits for the owner's look.
  const o5 = order('W-000206', 5, tyCeo, 'تحلیل ریزش کاربران مهر', 'P2', 'delivered', 1560, 'چرا کاربران مهر ریزش کردند و سه پیشنهاد برای برگرداندنشان.');
  accepted(o5, 1550);
  const k5 = child(o5, 'W-000207', tyCamp, 'داده‌ی ریزش مهر به تفکیک مرحله', 'done', 1540);
  accepted(k5, 1530); delivered(k5, 400, null); run(k5, 1500, 410, 'done', ['داده‌ی ورود و واریز مهر را خواند', 'db.read'], ['مرحله‌ی بیشترین افت را پیدا کرد', 'sheet.write']);
  delivered(o5, 70, outputOf(o5, 'O-000044', 'تحلیل ریزش کاربران مهر', 'بیشترین ریزش بعد از تأیید هویت بود (۴۱٪)؛ سه پیشنهاد: یادآوری، راهنمای تصویری، پشتیبانی زنده.', ago(70)));
  run(o5, 120, 70, 'done', ['یافته‌های تحلیلگر را خواند', 'work.read'], ['گزارش نهایی را نوشت و تحویل داد', 'work.deliver']);

  // Done: delivered and closed by the owner.
  const o6 = order('W-000201', 6, fxCeo, 'گزارش هزینه‌ی سرورهای مهر', 'P4', 'done', 4320, 'هزینه‌ی هر سرور در مهر، با مقایسه‌ی شهریور.');
  accepted(o6, 4300); run(o6, 4300, 4200, 'done', ['صورت‌حساب‌های مهر را خواند', 'archive.search'], ['جدول مقایسه را تحویل داد', 'work.deliver']);
  delivered(o6, 4200, outputOf(o6, 'O-000045', 'هزینه‌ی سرورهای مهر', 'هزینه‌ی مهر ۸٪ کمتر از شهریور؛ یک سرور بی‌کار شناسایی شد.', ago(4200)));
  o6.events.push({ at: ago(3000), kind: 'completed', actor: 'owner', actor_kind: 'owner', data: { evidence: '1' } });
  o6.updated = ago(3000);

  // Failed: the company is stopped and the campaign had no approved e-mail policy.
  const o7 = order('W-000204', 7, pcCeo, 'کمپین ایمیلی نوروز', 'P3', 'failed', 2880, 'پیش‌نویس و زمان‌بندی کمپین ایمیلی نوروز برای کاربران فعال.');
  accepted(o7, 2870);
  const k7 = child(o7, 'W-000205', pcGrowth, 'متن و زمان‌بندی کمپین نوروز', 'cancelled', 2860);
  k7.events.push({ at: ago(40), kind: 'cancelled', actor: 'PC-CEO', actor_kind: 'agent', data: { reason: 'شرکت متوقف شد.' } });
  failed(o7, 38, 'پرو-چارت متوقف است و سیاست ارسال ایمیل هنوز مُهر نشده؛ کمپین بدون آن اجرا نمیشود.');

  // ⟨1.10⟩ Given to the council (§27.2): only Claude answered; the other three failed or were left out (§28.4).
  const o8 = order('W-000209', 8, tyCeo, 'سرور تریدیار را بگرد و همه‌چیز را استخراج کن', 'P2', 'delivered', 600, 'همه‌ی محصولات، خودکارسازی‌ها، داده، رابط‌ها، کد و ریسک‌های سرور تریدیار؛ کامل، نه خلاصه.');
  o8.mode = 'council';
  accepted(o8, 598); run(o8, 598, 560, 'done', ['شرح را به چهار بازیکن داد', 'council.start'], ['پاسخ Claude را خواند', 'work.read'], ['جمع‌بندی را نوشت', 'work.deliver']);
  const solo = outputOf(o8, 'O-000049', 'پاسخ Claude: سرور تریدیار', '۹ کانتینر، ۱۴ گردش‌کار n8n و ۴۲ جدول؛ برای فهرست کامل کاتالوگ شرکت ساخته شد.', ago(570));
  const synth = outputOf(o8, 'O-000050', 'جمع‌بندی: سرور تریدیار', 'فقط Claude پاسخ داد؛ این یک پاسخ است، نه نظر شورا.', ago(560));
  orderOutputs.get(synth).body = '## فقط Claude پاسخ داد\nسه بازیکن دیگر پاسخی ندادند، پس جای «هم‌نظری» و «اختلاف» خالی است و این متن نظر شورا نیست.\n\n## پیشنهاد\nبرای فهرست کامل، **کاتالوگ کامل** تریدیار ساخته شد (AR-000094): ۹ کانتینر، ۱۴ گردش‌کار، ۴۲ جدول، ۸۷ مسیر API و ۴ ریسک.\n\n## پاسخ Claude، کامل\nسرور `ty-app-01` سه پروژه‌ی compose دارد: صرافی، خودکارسازی و ربات‌ها. جزئیات در کاتالوگ.';
  delivered(o8, 560, synth);
  councils.set(o8.ref, {
    work_ref: o8.ref, state: 'done', synthesis_ref: synth, media: null,
    members: [
      { player: 'claude', model: 'claude-opus-5-5', state: 'done', run_id: idOf(880), deliverable_ref: solo, reason: null },
      { player: 'gpt', model: 'gpt-5.3', state: 'failed', run_id: idOf(881), deliverable_ref: null, reason: "The 'gpt-5.3' model is not supported when using Codex with a ChatGPT account." },
      { player: 'gemini', model: 'gemini-3-pro', state: 'failed', run_id: idOf(882), deliverable_ref: null, reason: '{"code":"recipe_failed","step":"submit","detail":"selector textarea[aria-label=Prompt] not found after 30000ms"}' },
      { player: 'deepseek', model: 'deepseek-v4', state: 'skipped', run_id: null, deliverable_ref: null, reason: 'بازیکن ذخیره‌ی DeepSeek خاموش است؛ شورا بدون او برگزار شد.' },
    ],
  });

  // Opened by agents, not the owner (the live stream talks about them too).
  agentWork('W-000108', pcTech, 'PC-CEO', 'رفع خطای نمایش قیمت در ترمینال', 'P1', 'in_progress', 300);
  agentWork('W-000130', hqAi, 'HQ-AIOPS-MGR', 'بازبینی مصرف توکن هفته', 'P3', 'in_progress', 90);

  // Live: the queued one is taken and delegated; the delegated order's manager starts, then delivers.
  beat(4, () => take(o4));
  beat(8, () => delegate(o4, tyGrowth, 'پیش‌نویس سیاست بازگشت وجه', 'W-000216'));
  beat(13, () => start(k2));
  beat(20, () => deliverUp(k2, o2));
}


function take(n: Node): Ev[] {
  const t = nowIso();
  n.status = 'in_progress'; n.updated = t;
  n.events.push({ at: t, kind: 'accepted', actor: n.assignee.code, actor_kind: 'agent', data: {} });
  const r: RunRec = { id: idOf(900 + n.runs.length + nodes.length), employee: n.assignee.code, state: 'running', started: t, finished: null, steps: [{ at: t, summary: 'فرمان را خواند و دامنه‌ی کار را روشن کرد', tool: 'work.read', ref: n.ref }] };
  n.runs.push(r);
  return [ev(n.company, 'work.updated', n.ref, { status: 'in_progress', root_ref: n.ref }), ev(n.company, 'run.started', r.id, { employee: n.assignee.code, trigger: 'work', work: n.ref })];
}
function delegate(n: Node, to: Emp, title: string, ref: string): Ev[] {
  const t = nowIso();
  const k: Node = { id: idOf(300 + nodes.length), ref, company: n.company, title, brief: '', priority: n.priority, status: 'queued', assignee: to, owner: false, parent: n, created: t, updated: t, progress: null, note: null, deliverable: null, events: [], runs: [] };
  k.events.push({ at: t, kind: 'created', actor: n.assignee.code, actor_kind: 'agent', data: { assignee: to.code } });
  nodes.push(k);
  n.status = 'waiting'; n.updated = t;
  n.events.push({ at: t, kind: 'delegated', actor: n.assignee.code, actor_kind: 'agent', data: { child: ref, to: to.code } });
  const r = n.runs[n.runs.length - 1];
  if (r) { r.state = 'done'; r.finished = t; r.steps.push({ at: t, summary: `کار را به ${to.title_fa} سپرد`, tool: 'work.delegate', ref }); }
  return [
    ev(n.company, 'work.created', ref, { assignee: to.code, depth: String(depthOf(k)), root_ref: n.ref }),
    ev(n.company, 'work.delegated', n.ref, { child: ref, to: to.code, root_ref: n.ref }),
    ...(r ? [ev(n.company, 'run.finished', r.id, { employee: r.employee, state: 'done', work: n.ref })] : []),
  ];
}
function start(k: Node): Ev[] {
  const t = nowIso();
  k.status = 'in_progress'; k.updated = t; k.progress = 20;
  k.events.push({ at: t, kind: 'accepted', actor: k.assignee.code, actor_kind: 'agent', data: {} });
  const r: RunRec = { id: idOf(950 + nodes.length + k.runs.length), employee: k.assignee.code, state: 'running', started: t, finished: null, steps: [{ at: t, summary: 'اندازه‌ی بسته‌های صفحه را خواند', tool: 'health.sites', ref: k.ref }] };
  k.runs.push(r);
  const root = rootOf(k);
  return [ev(k.company, 'work.updated', k.ref, { status: 'in_progress', root_ref: root.ref }), ev(k.company, 'run.started', r.id, { employee: k.assignee.code, trigger: 'work', work: k.ref })];
}
function deliverUp(k: Node, root: Node): Ev[] {
  const t = nowIso();
  const kidOut = outputOf(k, `O-${String(outSeq++).padStart(6, '0')}`, 'بهینه‌سازی بارگذاری داشبورد', 'بسته‌ها کوچک شدند؛ بارگذاری روی موبایل از ۴٫۲ به ۱٫۷ ثانیه رسید.', t, true);
  k.status = 'delivered'; k.updated = t; k.progress = 100; k.deliverable = kidOut;
  k.events.push({ at: t, kind: 'delivered', actor: k.assignee.code, actor_kind: 'agent', data: { deliverable: kidOut } });
  const r = k.runs[k.runs.length - 1];
  if (r) { r.state = 'done'; r.finished = t; r.steps.push({ at: t, summary: 'تغییر را با شاهد سرعت تحویل داد', tool: 'work.deliver', ref: k.ref }); }
  const out = outputOf(root, `O-${String(outSeq++).padStart(6, '0')}`, root.title, 'زمان بارگذاری داشبورد سیگنال روی موبایل به ۱٫۷ ثانیه رسید؛ ظاهر دست نخورد.', t, true);
  root.status = 'delivered'; root.updated = t; root.deliverable = out;
  root.events.push({ at: t, kind: 'delivered', actor: root.assignee.code, actor_kind: 'agent', data: { deliverable: out } });
  k.status = 'done';
  return [
    ev(k.company, 'deliverable.created', kidOut, { work: k.ref, producer: k.assignee.code, root_ref: root.ref }),
    ev(k.company, 'work.updated', k.ref, { status: 'delivered', root_ref: root.ref }),
    ev(root.company, 'deliverable.created', out, { work: root.ref, producer: root.assignee.code, root_ref: root.ref }),
    ev(root.company, 'work.updated', root.ref, { status: 'delivered', root_ref: root.ref }),
    ev(k.company, 'work.completed', k.ref, { by: root.assignee.code, root_ref: root.ref }),
  ];
}
const rootOf = (n: Node): Node => (n.parent ? rootOf(n.parent) : n);
const empJson = (e: Emp) => ({ code: e.code, company: e.company, kind: e.kind, department: e.department, title_fa: e.title_fa });
function workJson(n: Node) {
  const used = 12000 * (n.runs.length + 1);
  return {
    id: n.id, ref: n.ref, company: n.company, department: n.assignee.department, title: n.title, brief: n.brief, kind: 'one_off', priority: n.priority, status: n.status,
    assignee: empJson(n.assignee), created_by: n.owner ? OWNER : { kind: 'agent', code: n.parent?.assignee.code ?? n.events[0]?.actor ?? n.assignee.code, display_fa: null },
    created_at: n.created, updated_at: n.updated, due_at: null, overdue: false, escalation_level: 0, progress_pct: n.progress, progress_note: n.note,
    budget: { tokens: 400000, tokens_used: used, usd: null, usd_used: (0.21 * (n.runs.length + 1)).toFixed(2) }, escrow: null, schedule: null,
    depth: depthOf(n), parent_id: n.parent?.id ?? null, root_id: rootOf(n).id, requested_by_work_id: null,
    deliverable_ids: n.deliverable ? [`o-${n.deliverable.toLowerCase()}`] : [], deliverable_refs: n.deliverable ? [n.deliverable] : [], evidence: [], version: 1 + n.events.length,
    player: n.player ?? 'auto', mode: n.mode ?? 'single', media: n.media ?? null, player_fallback: false,
  };
}
const kidsOf = (n: Node) => nodes.filter((x) => x.parent === n).sort((a, b) => a.created.localeCompare(b.created));
function stepJson(n: Node) {
  return { id: n.id, ref: n.ref, depth: depthOf(n), status: n.status, assignee: empJson(n.assignee), created_at: n.created, tokens_used: 12000 * (n.runs.length + 1), usd_used: 0.21 * (n.runs.length + 1) };
}
function childJson(n: Node, level: number): any {
  return { ...stepJson(n), title: n.title, updated_at: n.updated, progress: n.progress == null ? null : n.progress / 100, deliverable_refs: n.deliverable ? [n.deliverable] : [], children: level < 2 ? kidsOf(n).map((k) => childJson(k, level + 1)) : [] };
}
function detailJson(n: Node) {
  const chain: Node[] = [];
  for (let x: Node | null = n; x; x = x.parent) chain.unshift(x);
  return { ...workJson(n), chain: chain.map(stepJson), children: kidsOf(n).map((k) => childJson(k, 1)) };
}
function runJson(n: Node, r: RunRec) {
  return {
    id: r.id, employee: r.employee, company: n.company, work_ref: n.ref, thread: null, state: r.state, trigger: 'work', reason: `کار ${n.ref}`, priority: n.priority, model: 'claude-sonnet-5-5', effort: 'medium',
    queued_at: r.started, started_at: r.started, finished_at: r.finished, steps: r.steps.length, tool_calls: r.steps.length,
    tokens: { input: 21000 * r.steps.length, output: 1800 * r.steps.length, cache_read: 9000, cache_write: 1200 }, cost_usd: '0.00', equiv_cost_usd: (0.12 * r.steps.length).toFixed(2), error_code: null, partial: false,
    steps_detail: r.steps.map((s, i) => ({ run_id: r.id, n: i + 1, at: s.at, summary_fa: s.summary, actions: [{ tool: s.tool, outcome: 'ok', ref: s.ref, class: null }] })),
  };
}
function treeEvents(n: Node) {
  const tree: Node[] = [n, ...kidsOf(n), ...kidsOf(n).flatMap(kidsOf)];
  const out: any[] = [];
  let k = 0;
  for (const x of tree) {
    for (const e of x.events) out.push({ id: `e${String(++k).padStart(6, '0')}`, at: e.at, kind: `work.${e.kind}`, work_id: x.id, work_ref: x.ref, depth: depthOf(x), actor_kind: e.actor_kind, actor_code: e.actor, data: e.data });
    for (const r of x.runs) r.steps.forEach((s, i) => out.push({ id: `s${String(++k).padStart(6, '0')}`, at: s.at, kind: 'run.step', work_id: x.id, work_ref: x.ref, depth: depthOf(x), actor_kind: 'agent', actor_code: r.employee, data: { run_id: r.id, n: i + 1, summary_fa: s.summary, actions: [{ tool: s.tool, outcome: 'ok', ref: s.ref }] } }));
  }
  return out.sort((a, b) => (a.at === b.at ? a.id.localeCompare(b.id) : a.at.localeCompare(b.at)));
}
const findNode = (key: string) => nodes.find((x) => x.id === key || x.ref === key);

// ============================================================================================== notifications ==
let notes: any[] | null = null;
const nrow = (id: string, level: string, co: string, title: string, body: string, kind: string | null, ref: string | null, when: string, read: string | null = null) => ({
  id, level, company: co, title_fa: title, body_fa: body, link: kind ? { kind, ref } : null, created_at: when, read_at: read, choices: null, answer: null,
  state: read ? 'read' : 'delivered', delivered: { in_app: true, web_push: false, fcm: false, telegram: false },
});
async function notifications(req: Request) {
  if (notes) return notes;
  const finding = 'یافته‌ی جدی ناظر کل: سلامت خود هاب — down: otel-collector, tempo; disk 90.4%';
  const body = 'پایش ساعتی سلامت هاب: دو سرویس پایش پایین‌اند و دیسک از ۹۰٪ گذشته. مسئول: مهندس پلتفرم هلدینگ.';
  const rows: any[] = [];
  // The overseer's hourly finding: five times since this morning, each a new FI-… with the same words.
  [44, 104, 164, 224, 284].forEach((m, i) => rows.push(nrow(`f${i + 1}`, 'decision', 'HQ', finding, body, 'finding', `FI-${String(212 - i).padStart(4, '0')}`, at(m))));
  rows.push(...(await baseJson<{ items: any[] }>(req, '/notifications')).items);
  rows.push(nrow('m1', 'info', 'HQ', 'جلسه‌ی هیئت‌مدیره‌ی هلدینگ شروع شد', 'MT-0012 · مدیر کل حاضر است، دستورِ جلسه سه بند دارد', 'meeting', 'MT-0012', at(26)));
  rows.push(nrow('c1', 'decision', 'HQ', 'سرور تأسیس C-0001 آماده‌ی ورود توست', 'وارد شو، Claude Code را باز کن و شرکت را فعال کن.', 'founding', 'C-0001', at(70)));
  // Read: the same budget alert three times yesterday, and the backup.
  [1300, 1360, 1420].forEach((m, i) => rows.push(nrow(`b${i + 1}`, 'report', 'TY', 'بودجه‌ی company:TY (2026-10) به 72٪ رسید', '', 'treasury', 'budget:company:TY:month', at(m), at(m - 20))));
  rows.push(nrow('k1', 'info', 'HQ', 'پشتیبان ساعتی انجام شد', '۱۲ پایگاه داده، ۴۱۰ مگابایت', 'backup', 'BK-0091', at(1500), at(1490)));
  notes = rows.sort((a, b) => b.created_at.localeCompare(a.created_at));
  return notes;
}
function raise(level: string, co: string, title: string, body: string, kind: string | null, ref: string | null): Ev {
  const id = `live-${(notes?.length ?? 0) + 1}`;
  notes?.unshift(nrow(id, level, co, title, body, kind, ref, nowIso()));
  return ev(co, 'notification.created', id, { level, ...(kind ? { link_kind: kind, link_ref: ref } : {}) });
}

// ================================================================================================ foundings ==
const chosen: Record<string, { name_fa?: string | null; code?: string | null; tagline?: string | null; color_index?: number | null }> = {};

// =================================================================================================== restart ==
let restartUntil = 0;
/** The demo's «راه‌اندازی دوباره‌ی هاب»: for eight seconds every call answers 502, as Caddy does while the hub restarts. */
export function simulateRestart() {
  restartUntil = Date.now() + 8_000;
  queue.push(ev('HQ', 'work.updated', 'W-000130', { status: 'in_progress' }), ev('HQ', 'decision.created', 'D-000014'), ev('HQ', 'deliverable.rated', 'O-000031'), ev('HQ', 'budget.alert', null));
}

// ================================================================================================ live script ==
const SCRIPT: Array<[string, string, string | null, Record<string, string>]> = [
  ['TY', 'run.started', 'run-d1', { employee: 'TY-GROWTH-01', trigger: 'work', work: 'W-000102' }],
  ['FX', 'run.step', 'run-0', { employee: 'FX-TECH-MGR' }],
  ['PC', 'run.started', 'run-d2', { employee: 'PC-TECH-MGR', trigger: 'work', work: 'W-000108' }],
  ['TY', 'deliverable.created', 'O-000041', { producer: 'TY-GROWTH-01' }],
  ['TY', 'run.finished', 'run-d1', { employee: 'TY-GROWTH-01', state: 'done' }],
  ['FX', 'decision.created', 'D-000085', { kind: 'email_send' }],
  ['PC', 'run.finished', 'run-d2', { employee: 'PC-TECH-MGR', state: 'done' }],
  ['FX', 'run.started', 'run-d3', { employee: 'FX-QUANT-02', trigger: 'schedule' }],
  ['HQ', 'work.updated', 'W-000130', { status: 'in_progress' }],
  ['FX', 'deliverable.created', 'O-000042', { producer: 'FX-QUANT-02' }],
  ['FX', 'run.finished', 'run-d3', { employee: 'FX-QUANT-02', state: 'done' }],
];
let step = 0;
const running: Record<string, Array<[string, string]>> = {};
let hiddenPlayed = false;
function scriptBeat(): Ev[] {
  for (let i = 0; i < SCRIPT.length; i++) {
    const [co, type, ref, data] = SCRIPT[step++ % SCRIPT.length]!;
    if (stopped().has(co) && type !== 'run.finished') continue;
    const employee = data.employee;
    if (type === 'run.started' && employee && ref) (running[co] ??= []).push([ref, employee]);
    if (type === 'run.finished') { const list = running[co] ?? []; const j = list.findIndex(([r]) => r === ref); if (j < 0) continue; list.splice(j, 1); }
    const out = [ev(co, type, ref, data)];
    if (type === 'run.started' && employee) out.push(ev(co, 'activity.changed', employee, { activity: 'working' }));
    if (type === 'run.finished' && employee) out.push(ev(co, 'activity.changed', employee, { activity: 'sleeping' }));
    return out;
  }
  return [];
}

/** One tick of the demo's live stream (every 2.4 s): what is due now. */
export function tick21(): Ev[] {
  tickNo += 1;
  const out = queue.splice(0, queue.length);
  const due = beats.filter(([t]) => t <= tickNo);
  for (const d of due) { beats.splice(beats.indexOf(d), 1); out.push(...d[1]()); }
  if (tickNo % 2 === 0) out.push(...scriptBeat());
  // Two lines an older hub sends with an id where a ref belongs: the feed resolves the first and names the second's topic.
  if (tickNo === 2) out.push(ev('FX', 'work.updated', idOf(2), { status: 'in_progress' }));
  if (tickNo === 3) out.push(ev('HQ', 'file.ready', '01a187f8-e3e9-7b4f-8dd2-3c4e5f607182'));
  // With the tab hidden, the hub keeps talking: a card waits for the seal, the orders move on, then an urgent alert (0.6.0's script).
  if (!hiddenPlayed && typeof document !== 'undefined' && document.visibilityState === 'hidden' && notes) {
    hiddenPlayed = true;
    beat(tickNo + 2, () => [raise('decision', 'FX', 'تصمیم تازه D-000085: ایمیل دوم به پشتیبانی تجاری اینستاگرام', 'پیشنهاد HQ-LGL · ریسک medium · برگشت‌ناپذیر', 'decision', 'D-000085')]);
    beat(tickNo + 3, () => { for (const b of beats) b[0] = Math.min(b[0], tickNo + 1); return []; });
    beat(tickNo + 7, () => [raise('urgent', 'HQ', 'دیسک سرور هاب از ۹۵٪ گذشت', 'پایش ساعتی: ۹۵٫۲٪ پر؛ پشتیبان ساعتی در خطر است. مسئول: مهندس پلتفرم هلدینگ.', null, null)]);
  }
  return out;
}

// ================================================================================================== handler ==
export async function handle(req: Request): Promise<Response> {
  const u = new URL(req.url);
  const p = u.pathname.replace(/^\/api\/v1/, '');
  const m = req.method;
  const q = u.searchParams;
  if (Date.now() < restartUntil) {
    await new Promise((r) => setTimeout(r, 150));
    return new Response('<html><body>502 Bad Gateway</body></html>', { status: 502, headers: { 'content-type': 'text/html', server: 'Caddy' } });
  }
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;
  const stepUp = req.headers.get('X-Step-Up');
  // ⟨1.10⟩ §28: the catalogue, the watch and the client error reports.
  const v28 = await handle28(req, p, q, base);
  if (v28) return v28;

  // ------------------------------------------------------------------------------------------- control --
  if (p === '/control/state' && m === 'GET') return json(control);
  if (p === '/control/kill-switch' && m === 'POST') {
    const b = await body<{ scope: string; state: string; reason?: string }>();
    if (!b.scope) return problem(422, 'validation_failed', 'دامنه لازم است.');
    if (b.state === 'released' && !stepUp) return problem(403, 'step_up_required', 'این کار تأیید با اثر انگشت یا چهره میخواهد.');
    const code = b.scope === 'holding' ? 'HQ' : b.scope.replace('company:', '');
    const t = nowIso();
    const reason = b.reason ?? '';
    const k = b.scope === 'holding' ? control.holding : control.companies.find((x) => x.scope === b.scope);
    if (!k) return problem(404, 'not_found', 'این دامنه پیدا نشد.');
    Object.assign(k, { state: b.state, reason, changed_at: t, changed_by: 'owner' });
    row(code, `kill_switch.${b.state === 'engaged' ? 'engage' : 'release'}`, 'kill_switch', b.scope, OWNER, t, `changed: ${b.state}: ${reason}`, !!stepUp);
    interaction(code, 'kill_switch.set', 'kill_switch', b.scope, t, { state: b.state, reason });
    queue.push(ev(code, 'control.changed', b.scope, { state: b.state, kill_switch: b.state, scope: b.scope, by: 'owner' }));
    if (b.state === 'engaged') for (const [r, e] of running[code]?.splice(0) ?? []) queue.push(ev(code, 'run.finished', r, { employee: e, state: 'refused', code: 'company_locked' }), ev(code, 'activity.changed', e, { activity: 'sleeping' }));
    return json(control);
  }
  if (p === '/control/deploy-freeze' && m === 'POST') {
    const b = await body<{ company: string; until: string; reason?: string }>();
    if (b.company === 'HQ') return problem(422, 'validation_failed', 'هلدینگ deploy ندارد؛ کلید توقفش را بزن.');
    const active = b.until > nowIso();
    if (!active && !stepUp) return problem(403, 'step_up_required', 'باز کردن deploy تأیید با اثر انگشت یا چهره میخواهد.');
    control.deploy_freezes = control.deploy_freezes.filter((f) => f.company !== b.company);
    if (active) control.deploy_freezes.push({ company: b.company, until: b.until, reason: b.reason ?? '', created_by: 'owner' });
    const t = nowIso();
    row(b.company, 'deploy_freeze.set', 'company', b.company, OWNER, t, `${active ? 'active' : 'lifted'}: ${b.reason ?? ''}`, !!stepUp);
    interactions.push({ id: `i${auditSeq++}`, at: t, company: b.company, kind: 'control', action: 'deploy_freeze.set', target: { kind: 'company', ref: b.company }, data: { until: b.until, reason: b.reason ?? '' } });
    queue.push(ev(b.company, 'control.changed', `company:${b.company}`, { state: active ? 'frozen' : 'open', by: 'owner' }));
    return json({ company: b.company, active, until: b.until });
  }
  if (p === '/audit' && m === 'GET' && (q.get('company') || q.get('action'))) {
    const co = q.get('company');
    const ac = q.get('action');
    const rows = (await baseJson<{ items: any[] }>(req, '/audit')).items.filter((r) => !/^(kill_switch|deploy_freeze)\./.test(r.action));
    return json(page([...audit, ...rows].filter((r) => (!co || r.company === co) && (!ac || r.action === ac)).sort((a, b) => b.at.localeCompare(a.at)).slice(0, Number(q.get('limit') ?? 50))));
  }
  if (p === '/owner/interactions' && m === 'GET') {
    const kind = q.get('kind');
    return json(page(interactions.filter((i) => !kind || i.kind === kind).sort((a, b) => b.at.localeCompare(a.at))));
  }

  // ----------------------------------------------------------------------------------------- companies --
  if (p === '/companies' && m === 'GET') {
    const list = await baseJson<any[]>(req, '/companies');
    return json([...list, ...added].filter((c) => !removed.has(c.code)).map(decorateCompany));
  }
  const cm = /^\/companies\/([A-Z][A-Z0-9]{1,9})$/.exec(p);
  if (cm) {
    const code = cm[1]!;
    const extra = added.find((c) => c.code === code);
    if (removed.has(code)) return problem(404, 'not_found', 'این شرکت پیدا نشد.');
    const co = extra ?? (m === 'GET' || m === 'PATCH' || m === 'DELETE' ? await baseJson<any>(req, `/companies/${code}`) : null);
    if (!co?.code) return problem(404, 'not_found', 'این شرکت پیدا نشد.');
    if (m === 'GET') return json(decorateCompany(co));
    if (m === 'DELETE') {
      if (!stepUp) return problem(403, 'step_up_required', 'این کار تأیید با گذرکلید لازم دارد.');
      if (co.kind === 'holding') return problem(422, 'validation_failed', 'هلدینگ حذف نمیشود.');
      if (!extra) return problem(409, 'company_has_history', 'این شرکت کار، خروجی یا درآمد دارد و حذف نمیشود؛ بایگانی‌اش کن.');
      removed.add(code);
      queue.push(ev(code, 'control.changed', code, { change: 'company.deleted' }));
      return new Response(null, { status: 204 });
    }
    if (m === 'PATCH') {
      const cur = versions[code] ?? co.version;
      const im = Number((req.headers.get('If-Match') ?? '').replace(/"/g, ''));
      if (!im) return problem(428, 'validation_failed', 'If-Match لازم است.');
      if (im !== cur) return problem(409, 'version_conflict', 'این شرکت تازه عوض شده؛ دوباره باز کن.');
      const b = await body<{ status?: string }>();
      if (b.status === 'archived') { if (!stepUp) return problem(403, 'step_up_required', 'این کار تأیید با گذرکلید لازم دارد.'); archived.add(code); }
      versions[code] = cur + 1;
      return json(decorateCompany(co));
    }
  }

  // ------------------------------------------------------------------------------------------ foundings --
  if (p === '/foundings' && m === 'POST') {
    const b = await body<{ source: { kind: string; repo?: string; brief_md?: string }; name_fa?: string; code?: string; tagline?: string; color_index?: number; logo_file_id?: string }>();
    const all = [...(await baseJson<any[]>(req, '/companies')), ...added].filter((c) => !removed.has(c.code));
    if (b.code && (all.some((c) => c.code === b.code) || Object.values(chosen).some((c) => c.code === b.code))) return json({ code: 'code_taken', message_fa: `${b.code} را شرکت یا تأسیس دیگری دارد.`, status: 409, title: 'code_taken', type: 'about:blank', fields: { code: 'taken' } }, 409);
    if (b.color_index && all.some((c) => c.color_index === b.color_index)) return json({ code: 'validation_failed', message_fa: 'این رنگ مال شرکت دیگری است؛ رنگ دیگری انتخاب کن.', status: 409, title: 'validation_failed', type: 'about:blank', fields: { color_index: 'taken' } }, 409);
    if (b.source.kind === 'blank') {
      if (!b.code || !b.name_fa) return problem(422, 'validation_failed', 'برای «فقط ثبت کن» نام فارسی و کد شرکت لازم است.');
      const t = nowIso();
      added.push({ id: `co-${b.code}`, code: b.code, kind: 'company', name_fa: b.name_fa, name_en: b.code, color_index: b.color_index ?? null, status: 'draft', template: 'standard', kill_switch: 'released', deploy_freeze_until: null, version: 1, created_at: t, counts: { decisions_pending: 0, employees_active: 0, work_open: 0 } });
      control.companies.push({ scope: `company:${b.code}`, company: b.code, state: 'released', changed_at: t, changed_by: null, reason: null });
      const ref = `C-${String(90 + added.length).padStart(4, '0')}`;
      queue.push(ev(b.code, 'control.changed', b.code, { change: 'company.created' }));
      return json({ id: `fo-${ref}`, ref, name_fa: b.name_fa, name_en: b.code, code: b.code, source: { kind: 'blank', repo: null, brief_md: b.source.brief_md ?? '' }, state: 'sealed', audit: null, proposal: null, decision_ref: null, plan: null, company: b.code, created_at: t, updated_at: t }, 201);
    }
    const res = await base(new Request(req.url, { method: 'POST', headers: req.headers, body: JSON.stringify({ source: b.source }) }));
    const f = (await res.clone().json()) as { ref?: string };
    if (f.ref) chosen[f.ref] = { name_fa: b.name_fa, code: b.code, tagline: b.tagline, color_index: b.color_index };
    return res;
  }
  if ((p === '/foundings' || /^\/foundings\/C-\d+$/.test(p)) && m === 'GET') {
    const res = await base(req);
    const data = (await res.json()) as any;
    const fix = (f: any) => (chosen[f.ref] ? { ...f, name_fa: f.name_fa ?? chosen[f.ref]!.name_fa, code: f.code ?? chosen[f.ref]!.code } : f);
    return json(Array.isArray(data?.items) ? { ...data, items: data.items.map(fix) } : fix(data), res.status);
  }

  // -------------------------------------------------------------------------------------------- outputs --
  if (p === '/deliverables' && m === 'GET') {
    const list = await allOutputs(req);
    const s = q.get('seen');
    const cat = q.get('category');
    const cos = q.getAll('company');
    const text = q.get('q')?.trim();
    const from = q.get('from');
    const to = q.get('to');
    const producer = q.get('producer');
    const work = q.get('work');
    return json(page(list.filter((d) =>
      (s == null || (s === 'true') === !!d.seen_at) && (!cat || d.category === cat) && (!cos.length || cos.includes(d.company)) && (q.get('unrated') !== 'true' || !d.rating) &&
      (!producer || d.producer.code === producer) && (!work || d.work_ref === work || d.work_id === work) &&
      (!from || dayOf(d.created_at) >= from) && (!to || dayOf(d.created_at) <= to) &&
      (!text || d.ref === text || d.title.includes(text) || d.summary.includes(text)))));
  }
  if (p === '/deliverables/seen' && m === 'POST') {
    const b = await body<{ refs: string[]; seen: boolean }>();
    let n = 0;
    for (const r of b.refs ?? []) if (b.seen !== false && !seen[r]) { seen[r] = nowIso(); n++; } else if (b.seen === false && seen[r]) { delete seen[r]; n++; }
    return json({ updated: n });
  }
  // ⟨1.10⟩ §28.1: several at once.
  if (p === '/deliverables/file' && m === 'POST') {
    const b = await body<{ refs?: string[] }>();
    if (!b.refs?.length) return problem(422, 'validation_failed', 'دست‌کم یک خروجی لازم است.');
    const list = await allOutputs(req);
    const missing = b.refs.filter((r) => !list.some((d) => d.ref === r) && !orderOutputs.has(r));
    if (missing.length) return problem(404, 'not_found', `پیدا نشد: ${missing.join('، ')}`);
    for (const r of b.refs) filed[r] ??= `AR-${String(nextRecord++).padStart(6, '0')}`;
    return json({ records: b.refs.map((r) => ({ ref: r, record: filed[r] })) });
  }
  if (p === '/deliverables' && m === 'DELETE') {
    const b = await body<{ refs?: string[] }>();
    if (!b.refs?.length) return problem(422, 'validation_failed', 'دست‌کم یک خروجی لازم است.');
    if (!stepUp) return problem(403, 'step_up_required', 'حذف برای همیشه تأیید با اثر انگشت یا چهره میخواهد.');
    const list = await allOutputs(req);
    let n = 0;
    for (const r of b.refs) {
      const d = list.find((x) => x.ref === r) ?? (orderOutputs.has(r) && !deleted.has(r) ? outView(orderOutputs.get(r)) : null);
      if (!d) continue;
      deleted.add(r); delete seen[r]; n++;
      // The Audit chain keeps one line: what it was, whose, who deleted it and when. A filed one's archive record stays.
      row(d.company, 'deliverable.delete', 'deliverable', r, OWNER, nowIso(), `deleted: ${r} · ${d.title}`, true);
      queue.push(ev(d.company, 'deliverable.deleted', r, { by: 'owner' }));
    }
    return json({ deleted: n });
  }
  const fl = /^\/deliverables\/(O-\d+)\/file$/.exec(p);
  if (fl && m === 'POST') { filed[fl[1]!] ??= `AR-${String(nextRecord++).padStart(6, '0')}`; return json({ record: filed[fl[1]!] }); }
  const od = /^\/deliverables\/(O-\d+)$/.exec(p);
  if (od && m === 'GET') {
    if (deleted.has(od[1]!)) return problem(404, 'not_found', 'این خروجی برای همیشه پاک شده است.');
    const mine = orderOutputs.get(od[1]!) ?? extraOutputs.find((d) => d.ref === od[1]);
    if (mine) return json(outView(mine));
    const res = await base(req);
    return json(outView(await res.json()), res.status);
  }
  if (p === '/inbox/summary' && m === 'GET') {
    const [inbox, list, ns] = await Promise.all([baseJson<any>(req, '/inbox/summary'), allOutputs(req), notifications(req)]);
    const unread = (l: string) => ns.filter((n) => !n.read_at && n.level === l).length;
    return json({ ...inbox, deliverables_unseen: list.filter((d) => !d.seen_at).length, notifications: { urgent: unread('urgent'), decision: unread('decision'), report: unread('report'), info: unread('info'), learning: unread('learning') } });
  }

  // ----------------------------------------------------------------------------------------------- work --
  if (p === '/work' && m === 'GET') {
    const fixtures = (await baseJson<{ items: any[] }>(req, '/work')).items;
    const mine = [...nodes].sort((a, b) => b.created.localeCompare(a.created)).map(workJson);
    const by = q.get('created_by');
    const text = q.get('q')?.trim();
    const cos = q.getAll('company');
    return json(page([...mine, ...fixtures].filter((w) =>
      (!by || (by === 'owner' ? w.created_by?.kind === 'owner' : w.created_by?.code === by)) && (!cos.length || cos.includes(w.company)) &&
      (!q.get('status') || w.status === q.get('status')) && (!text || w.ref === text || String(w.title).includes(text))).slice(0, Number(q.get('limit') ?? 100))));
  }
  if (p === '/work' && m === 'POST') {
    const b = await body<{ company: string; title: string; brief?: string; priority?: string; player?: string; mode?: 'single' | 'council'; media?: string | null }>();
    if (!b.company) return problem(422, 'validation_failed', 'شرکت لازم است.');
    const ceo = E(`${b.company}-CEO`, b.company, 'ceo', null, 'مدیرعامل');
    const t = nowIso();
    const ref = `W-${String(++seq).padStart(6, '0')}`;
    const n: Node = { id: idOf(400 + seq), ref, company: b.company, title: b.title ?? '', brief: b.brief ?? '', priority: b.priority ?? 'P3', status: 'queued', assignee: ceo, owner: true, parent: null, created: t, updated: t, progress: null, note: null, deliverable: null, events: [], runs: [] };
    n.events.push({ at: t, kind: 'created', actor: 'owner', actor_kind: 'owner', data: { assignee: ceo.code } });
    n.player = b.player ?? 'auto'; n.mode = b.mode ?? 'single'; n.media = b.media ?? null;
    nodes.push(n);
    // It moves on its own: taken, delegated, started and delivered over about half a minute.
    const mgr = E(`${b.company}-GROWTH-MGR`, b.company, 'manager', 'GROWTH', 'مدیر رشد');
    const k = `W-${String(++seq).padStart(6, '0')}`;
    beat(tickNo + 2, () => take(n));
    beat(tickNo + 5, () => delegate(n, mgr, n.title, k));
    beat(tickNo + 8, () => { const x = findNode(k); return x ? start(x) : []; });
    beat(tickNo + 12, () => { const x = findNode(k); return x ? deliverUp(x, n) : []; });
    queue.push(ev(b.company, 'work.created', ref, { assignee: ceo.code, root_ref: ref }));
    return json(workJson(n), 201);
  }
  const wc = /^\/work\/([^/]+)\/council$/.exec(p);
  if (wc && m === 'GET') {
    const n = findNode(wc[1]!);
    const c = n && councils.get(n.ref);
    return c ? json(c) : problem(404, 'not_found', 'این کار به شورا داده نشده است.');
  }
  const wm = /^\/work\/([^/]+?)(\/events|\/runs|\/tree-events)?$/.exec(p);
  if (wm && m === 'GET') {
    const n = findNode(wm[1]!);
    if (n) {
      if (wm[2] === '/events') return json(page(n.events.map((e, i) => ({ id: i + 1, at: e.at, kind: e.kind, actor_code: e.actor, actor_kind: e.actor_kind, data: e.data })).sort((a, b) => a.at.localeCompare(b.at))));
      if (wm[2] === '/runs') return json(n.runs.map((r) => runJson(n, r)));
      if (wm[2] === '/tree-events') return json(page(treeEvents(n)));
      return json(detailJson(n));
    }
    if (/^[0-9a-f]{8}-/.test(wm[1]!)) return problem(404, 'not_found', 'این کار پیدا نشد.');
    if (wm[2] === '/tree-events') {
      // The fixtures' own work: its own events as its tree.
      const own = await baseJson<{ items: any[] }>(req, `/work/${wm[1]}/events`).catch(() => ({ items: [] }));
      const w = await baseJson<any>(req, `/work/${wm[1]}`);
      return json(page((own.items ?? []).map((e: any, i: number) => ({ id: `e${i}`, at: e.at, kind: `work.${e.kind}`, work_id: w.id, work_ref: w.ref, depth: w.depth ?? 0, actor_kind: e.actor_kind, actor_code: e.actor_code, data: e.data ?? {} }))));
    }
    if (!wm[2]) {
      // The fixtures' work, with ⟨1.7.4⟩ children (none) and refs of its outputs.
      const res = await base(req);
      const w = (await res.json()) as any;
      return json({ ...w, children: (w.children ?? []).map((c: any) => ({ ...c, title: c.title ?? c.ref, updated_at: c.updated_at ?? c.created_at, progress: null, deliverable_refs: [], children: [] })), deliverable_refs: w.deliverable_refs ?? [] }, res.status);
    }
  }

  // -------------------------------------------------------------------------------------- notifications --
  if (p === '/notifications' && m === 'GET') {
    const rows = await notifications(req);
    const unread = q.get('unread');
    const level = q.get('level');
    return json(page(rows.filter((n) => (unread == null || (!n.read_at) === (unread === 'true')) && (!level || n.level === level)).slice(0, Number(q.get('limit') ?? 50))));
  }
  if (p === '/notifications/read' && m === 'POST') {
    const rows = await notifications(req);
    const b = await body<{ ids: string[] }>();
    let n = 0;
    for (const r of rows) if (b.ids?.includes(r.id) && !r.read_at) { r.read_at = nowIso(); r.state = 'read'; n++; }
    return json({ updated: n });
  }
  const nr = /^\/notifications\/([^/]+)\/(read|answer)$/.exec(p);
  if (nr && m === 'POST' && nr[1] !== 'read-all') {
    const rows = await notifications(req);
    const r = rows.find((x) => x.id === nr[1]);
    if (!r) return problem(404, 'not_found', 'این اعلان پیدا نشد.');
    if (nr[2] === 'answer') { const b = await body<{ choice_id: string }>(); if (r.answer) return problem(409, 'validation_failed', 'به این پرسش جواب داده شده.'); r.answer = b.choice_id; }
    r.read_at ??= nowIso(); r.state = 'read';
    return json(r);
  }
  if (p === '/notifications/read-all' && m === 'POST') {
    const rows = await notifications(req);
    const b = await body<{ before?: string; level?: string }>();
    let n = 0;
    for (const r of rows) if (!r.read_at && (!b.level || r.level === b.level) && (!b.before || r.created_at <= b.before)) { r.read_at = nowIso(); r.state = 'read'; n++; }
    return json({ updated: n });
  }

  // ------------------------------------------------------------------------------------------ web push --
  // The demo has no push service: the browser's notifications come from the open tab only.
  if (p === '/push/vapid-public-key') return problem(503, 'channel_not_configured', 'Web Push در حالت نمایشی نیست.');

  return base(req);
}
