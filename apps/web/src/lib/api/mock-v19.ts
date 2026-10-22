// Development-only fixtures for contract v1.6 §22 (the media studio and the legal counsel), used by mock.ts. Never bundled in
// production (next.config aliases the fixtures module away). Companies are data here as on the hub: every list is built from rows.
// What the hub does by code (the schedule's next runs, the series digest, the platform checks, the ceilings of a role, the seal
// bindings) is code here too, reduced to what a demo needs; what a model would write is canned text. The renders and voice clips are
// files in public/demo/ made by scripts/gen-demo-studio.mjs; stills are painted in the browser like the §21.13 creatives.

import { DEMO_CHART } from './mock-media';
import { roles as fileRoles } from './mock-roles';
import { render as paint } from './mock-v18';

const now = Date.now();
const MIN = 60_000;
const HOUR = 3_600_000;
const DAY = 86_400_000;
const iso = (minAgo: number) => new Date(now - minAgo * MIN).toISOString();
const ahead = (min: number) => new Date(now + min * MIN).toISOString();
const stamp = () => new Date().toISOString();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const page = (items: unknown[]) => ({ items, next_cursor: null });
const problem = (status: number, code: string, message_fa: string, extra: Record<string, unknown> = {}) =>
  json({ type: 'about:blank', title: code, status, code, message_fa, ...extra }, status);
const pad = (n: number, w: number) => String(n).padStart(w, '0');
const seedOf = (s: string) => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 9973, 7);
async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
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
const keys = new Map<string, { status: number; body: unknown }>();
const once = (req: Request) => { const k = req.headers.get('Idempotency-Key') ?? ''; return { k, hit: k ? keys.get(k) : undefined }; };
const remember = (k: string, status: number, body: unknown) => { if (k) keys.set(k, { status, body }); };

// ------------------------------------------------------------------------ actors --
const NAME: Record<string, string> = { HQ: 'هلدینگ', TY: 'تریدیار', FX: 'کوینه‌پرو FX', PC: 'پرو-چارت' };
const owner = { kind: 'owner', code: 'owner', display_fa: 'مدیر کل' };
const system = { kind: 'system', code: 'system', display_fa: 'سیستم' };
const agent = (code: string, display_fa: string, kind = 'agent') => ({ kind, code, display_fa });
const mediaMgr = (c: string) => agent(`${c}-MEDIA-MGR`, `مدیر رسانه‌ی ${NAME[c]}`);
const ceo = (c: string) => agent(`${c}-CEO`, `مدیرعامل ${NAME[c]}`);
const counsel = agent('HQ-LGL', 'مشاور حقوقی');
const overseer = agent('HQ-OVR', 'ناظر کل', 'overseer');

/** The MEDIA teams the media directors hired, and the holding's legal counsel (seeded, asleep until work arrives). */
const TEAM: Array<[string, string, string, string, string, string]> = [
  // code, company, role, title_fa, title_en, model
  ['FX-MEDIA-01', 'FX', 'scriptwriter', 'سناریست', 'Scriptwriter', 'claude-sonnet-5-5'],
  ['FX-MEDIA-02', 'FX', 'video_director', 'کارگردان ویدیو', 'Video Director', 'claude-sonnet-5-5'],
  ['FX-MEDIA-03', 'FX', 'motion_designer', 'طراح موشن‌گرافیک', 'Motion Designer', 'claude-opus-5-5'],
  ['FX-MEDIA-04', 'FX', 'voice_producer', 'تهیه‌کننده‌ی صدا', 'Voice Producer', 'claude-haiku-5-5'],
  ['TY-MEDIA-01', 'TY', 'scriptwriter', 'سناریست', 'Scriptwriter', 'claude-sonnet-5-5'],
  ['TY-MEDIA-02', 'TY', 'visual_designer', 'طراح گرافیک', 'Visual Designer', 'claude-sonnet-5-5'],
  ['TY-MEDIA-03', 'TY', 'video_director', 'کارگردان ویدیو', 'Video Director', 'claude-sonnet-5-5'],
  ['TY-MEDIA-04', 'TY', 'motion_designer', 'طراح موشن‌گرافیک', 'Motion Designer', 'claude-opus-5-5'],
  ['PC-MEDIA-01', 'PC', 'ui_designer', 'طراح رابط کاربری', 'UI Designer', 'claude-sonnet-5-5'],
  ['PC-MEDIA-02', 'PC', 'visual_designer', 'طراح گرافیک', 'Visual Designer', 'claude-sonnet-5-5'],
  ['PC-MEDIA-03', 'PC', 'scriptwriter', 'سناریست', 'Scriptwriter', 'claude-sonnet-5-5'],
];
const member = (code: string) => { const t = TEAM.find((x) => x[0] === code)!; return agent(t[0], `${t[3]} ${NAME[t[1]]}`); };

// ============================================================ department mandate and identity (§22.1) ==
type Mandate = { from_fa: string; to_fa: string; outputs_fa: string[]; boundaries_fa: string[]; tool_ceiling: string[]; model_ceiling: string };
const BASE_TOOLS = ['work.get', 'company.state', 'knowledge.search', 'memory.read', 'memory.write', 'deliver', 'propose', 'message.thread', 'work.accept', 'work.progress', 'work.fail', 'work.delegate', 'work.request', 'activity.set', 'files.read', 'web.search', 'web.read'];
const DEPT: Record<string, { mandate: Mandate; identity_md: string; team: Array<{ role: string; title_fa: string; why_fa: string; first: boolean }> }> = {
  TECH: {
    mandate: { from_fa: 'سایت‌ها، اپ‌ها و سرورهای شرکت همان‌طور که امروز هستند، با هشدارهای پایش و درخواست بقیه‌ی دپارتمان‌ها', to_fa: 'سرویس پایدار و سریع؛ هر تغییر با تست، روی شاخه‌ی جدا و با مُهر؛ هیچ حادثه‌ی تکراری',
      outputs_fa: ['گزارش سلامت روزانه', 'اصلاح در کارگاه کد روی شاخه‌ی جدا', 'کارت انتشار با diff واقعی'], boundaries_fa: ['هیچ ادغام یا انتشاری بی‌مُهر مالک', 'هیچ دسترسی به سرور همسایه', 'از رمزها فقط نام متغیر'],
      tool_ceiling: [...BASE_TOOLS, 'health.sites', 'github.read', 'workshop.read', 'server.plan', 'web.browse'], model_ceiling: 'claude-opus-5-5' },
    identity_md: 'دقیق و کم‌حرف. اول اندازه، بعد اصلاح؛ هر ادعا با لاگ یا تست. «نمیدانم» بهتر از حدس است.',
    team: [{ role: 'sre', title_fa: 'مهندس پایداری (SRE)', why_fa: 'پایش سلامت سایت و پنل و تحلیل هشدارها', first: true }],
  },
  GROWTH: {
    mandate: { from_fa: 'ترافیک، کانال‌ها، کلیدواژه‌ها و پرسش‌های تکراری کاربران امروز', to_fa: 'رشد کاربر فعال با هزینه‌ی کمتر هر جذب، بی‌پیام ناخواسته',
      outputs_fa: ['گزارش سئو و قیف', 'تقویم محتوای هر کانال', 'brief موضوع برای رسانه'], boundaries_fa: ['هیچ پیام به مشتری بی‌قالب مُهرشده', 'هیچ وعده‌ی سود'],
      tool_ceiling: [...BASE_TOOLS, 'funnel.read', 'kpi.record', 'substitute.call'], model_ceiling: 'claude-sonnet-5-5' },
    identity_md: 'کنجکاو و عددمحور؛ هر ایده با آزمون کوچک. لحن بیرونی گرم و صادق، بی‌هیجان فروشی.',
    team: [],
  },
  SALES: {
    mandate: { from_fa: 'گفت‌وگوهای پشتیبانی، رفرال‌ها و کاربران در خطر ریزش', to_fa: 'جواب درست و سریع از دانشنامه، و نجات کاربری که رفتنی بود',
      outputs_fa: ['پاسخ پشتیبانی از دانشنامه', 'فهرست نجات رفرال'], boundaries_fa: ['جواب بیرون از دانشنامه فقط با تأیید', 'هیچ داده‌ی مشتری بیرون از سیستم'],
      tool_ceiling: [...BASE_TOOLS, 'support.reply', 'revenue.read'], model_ceiling: 'claude-sonnet-5-5' },
    identity_md: 'صبور و روشن؛ کوتاه جواب میدهیم و فقط چیزی میگوییم که دانشنامه دارد.',
    team: [
      { role: 'support_lead', title_fa: 'سرپرست پشتیبانی', why_fa: 'صف و کیفیت جواب‌ها', first: true },
      { role: 'support_agent', title_fa: 'کارشناس پشتیبانی', why_fa: 'جواب از دانشنامه در ساعت شلوغ', first: false },
      { role: 'referral_rescue', title_fa: 'متخصص نجات رفرال', why_fa: 'کاربر رفرالی که فعال نشد', first: false },
    ],
  },
  PRODUCT: {
    mandate: { from_fa: 'بازخورد کاربران، داده‌ی استفاده و نقشه‌ی راه', to_fa: 'محصولی که کاربر بی‌راهنما با آن کار میکند',
      outputs_fa: ['اولویت‌بندی بازخورد', 'نقد UX طرح‌های تازه'], boundaries_fa: ['هیچ تغییر در تولید؛ ساختن با TECH است'],
      tool_ceiling: [...BASE_TOOLS, 'feedback.tag'], model_ceiling: 'claude-sonnet-5-5' },
    identity_md: 'از چشم کاربر تازه‌کار نگاه میکنیم؛ ساده‌تر همیشه بهتر است.',
    team: [],
  },
  FIN: {
    mandate: { from_fa: 'درآمد، هزینه‌ی توکن و قراردادهای شرکت', to_fa: 'تصویر درست و به‌روز پول، با هشدار پیش از کسری',
      outputs_fa: ['گزارش درآمد ماهانه', 'هشدار انحراف بودجه'], boundaries_fa: ['هیچ پرداخت یا تعهد مالی'],
      tool_ceiling: [...BASE_TOOLS, 'revenue.read', 'treasury.usage'], model_ceiling: 'claude-sonnet-5-5' },
    identity_md: 'محافظه‌کار و شفاف؛ هر عدد با منبع و تاریخ.',
    team: [{ role: 'revenue_analyst', title_fa: 'تحلیلگر درآمد', why_fa: 'رادار درآمد و ریزش', first: true }],
  },
  QUANT: {
    mandate: { from_fa: 'داده‌ی بازار، سیگنال‌ها و نتیجه‌ی بک‌تست', to_fa: 'سیگنال با دقت سنجیده و افت‌های توضیح‌داده‌شده',
      outputs_fa: ['گزارش دقت هفتگی', 'تحلیل افت'], boundaries_fa: ['هیچ معامله‌ی واقعی', 'هیچ ادعای سود قطعی'],
      tool_ceiling: [...BASE_TOOLS, 'kpi.record'], model_ceiling: 'claude-opus-5-5' },
    identity_md: 'شکاک به نتیجه‌ی خوب؛ اول نشت داده را رد میکنیم.',
    team: [],
  },
  AIOPS: {
    mandate: { from_fa: 'مصرف توکن، اجراها و خطاهای ایجنت‌ها', to_fa: 'ایجنت‌های ارزان‌تر و پایدارتر با همان کیفیت',
      outputs_fa: ['گزارش هدررفت', 'پیشنهاد مدل مناسب هر نقش'], boundaries_fa: ['تغییر assignment فقط با مُهر'],
      tool_ceiling: [...BASE_TOOLS, 'treasury.usage', 'health.hub'], model_ceiling: 'claude-sonnet-5-5' },
    identity_md: 'مهندس هزینه؛ ارزان‌ترین مدلی که کار را خوب انجام میدهد.',
    team: [{ role: 'hub_platform_sre', title_fa: 'SRE سکوی هاب', why_fa: 'سلامت سرویس‌های خود هاب', first: true }],
  },
  HR: {
    mandate: { from_fa: 'نمره‌ها، دور ارزیابی ماهانه و نیاز دپارتمان‌ها', to_fa: 'تیمی که اندازه‌ی کار است، نه بیشتر',
      outputs_fa: ['خلاصه‌ی دور ارزیابی', 'پیشنهاد آموزش'], boundaries_fa: ['استخدام و برکناری فقط با کارت'],
      tool_ceiling: [...BASE_TOOLS], model_ceiling: 'claude-sonnet-5-5' },
    identity_md: 'منصف و مستند؛ هر پیشنهاد با شاهد از کار واقعی.',
    team: [],
  },
  MEDIA: {
    mandate: {
      from_fa: 'هدف‌ها و موضوع‌های رشد شرکت، دانشنامه، برند و نشان شرکت، و فایل‌های خود شرکت',
      to_fa: 'هر روز پست، استوری و ریلز با کیفیتی که مالک خودش میساخت، بی‌دست مالک؛ و طراحی تازه‌ی رابط سایت‌ها برای مدیر فنی',
      outputs_fa: ['ریلز، استوری و پست هر برنامه‌ی انتشار', 'گزارش ماهانه‌ی رسانه با شمارنده‌های عمومی', 'ماکاپ HTML بازطراحی رابط برای مدیر فنی'],
      boundaries_fa: ['انتشار فقط از API رسمی و فقط زیر برنامه‌ی مُهرشده یا با کارت', 'هر عدد منبع و تاریخ دارد؛ هر محتوای ترید هشدار ریسک', 'فقط فایل خود، ساخته‌شده یا مجاز؛ برچسب ساخته‌ی هوش مصنوعی', 'هیچ داده‌ی مشتری و هیچ وعده‌ی سود'],
      tool_ceiling: [...BASE_TOOLS, 'treasury.usage', 'web.browse', 'media.item', 'media.render', 'media.voice', 'media.review', 'series.propose', 'substitute.call', 'kpi.record'],
      model_ceiling: 'claude-opus-5-5',
    },
    identity_md: '**آموزشی، آرام، دقیق.** ما هیجان نمیفروشیم؛ یک ایده در هر قطعه، روشن و درست.\n\n- فارسی درست (ی، ک، نیم‌فاصله) و خوانا روی گوشی\n- قلاب اول کار باید به وعده‌اش برسد\n- هشدار ریسک همیشه خوانا، نه ریز و پنهان\n- ظاهر هر برنامه ثابت میماند تا مخاطب بشناسدش',
    team: [
      { role: 'scriptwriter', title_fa: 'سناریست', why_fa: 'اولین برنامه‌ای که متن دارد', first: true },
      { role: 'video_director', title_fa: 'کارگردان ویدیو', why_fa: 'اولین برنامه‌ی ریلز یا استوری ویدیویی', first: true },
      { role: 'motion_designer', title_fa: 'طراح موشن‌گرافیک', why_fa: 'ترکیب‌بندی به‌صورت کد، با کارگردان', first: true },
      { role: 'voice_producer', title_fa: 'تهیه‌کننده‌ی صدا', why_fa: 'اولین برنامه‌ای که قالبش صدا دارد', first: true },
      { role: 'visual_designer', title_fa: 'طراح گرافیک', why_fa: 'عکس، کاروسل و قاب استوری', first: false },
      { role: 'ui_designer', title_fa: 'طراح رابط کاربری', why_fa: 'فقط وقتی مدیرعامل یا مدیر فنی بازطراحی برنامه‌ریزی کند', first: false },
    ],
  },
  OVS: {
    mandate: { from_fa: 'audit، خروجی‌ها، ادعاها و پیشنهادهای A3 همه‌ی شرکت‌ها', to_fa: 'هیچ کار بیرون از اختیار و هیچ ادعای بی‌شاهد که دیده نشود',
      outputs_fa: ['یافته با شاهد', 'نگه‌داشتن کار پرخطر تا تصمیم مالک'], boundaries_fa: ['هیچ اقدام اجرایی جز نگه‌داشتن'],
      tool_ceiling: [...BASE_TOOLS, 'audit.recent', 'finding.raise', 'hold'], model_ceiling: 'claude-opus-5-5' },
    identity_md: 'مستقل و منصف؛ هر یافته با شاهد، هیچ حدسی.',
    team: [
      { role: 'fact_checker', title_fa: 'راستی‌آزما', why_fa: 'نمونه‌ی ادعاهای هر روز', first: true },
      { role: 'ai_safety', title_fa: 'مسئول ایمنی هوش مصنوعی', why_fa: 'مرور A3 و مرز اختیار', first: false },
      { role: 'security_analyst', title_fa: 'تحلیلگر امنیت', why_fa: 'یافته‌های امنیتی', first: false },
    ],
  },
  LEGAL: {
    mandate: {
      from_fa: 'هر محدودیت پلتفرم، اعتراض، قرارداد یا گیر حقوقی که مالک یا مدیرعامل یک شرکت میفرستد',
      to_fa: 'پرونده‌ی بسته از راه رسمی، یا گفتن روشن اینکه وکیل انسانی لازم است',
      outputs_fa: ['پرونده‌ی LC با timeline و مهلت‌ها', 'پیش‌نویس دقیق ایمیل برای مُهر مالک', 'مقدار دقیق فیلدهای فرم برای ارسال مالک'],
      boundaries_fa: ['هیچ ایمیلی بی‌مُهر مالک روی همان پیام', 'هیچ امضا، تعهد یا پرداخت', 'هرگز به جای مالک یا وکیل حرف نمیزند', 'فقط کانال رسمی و قاعده‌ی منتشرشده با تاریخ'],
      tool_ceiling: ['work.get', 'company.state', 'knowledge.search', 'memory.read', 'memory.write', 'deliver', 'propose', 'message.thread', 'work.accept', 'work.progress', 'work.fail', 'activity.set', 'files.read', 'web.search', 'web.read', 'web.browse', 'case.open', 'case.note', 'email.draft', 'mail.read'],
      model_ceiling: 'claude-sonnet-5-5',
    },
    identity_md: 'مؤدب، واقعی و کوتاه. نقل‌قول دقیق از قاعده، با تاریخ؛ «نمیدانم» به جای حدس. هیچ تهدید و هیچ ادعایی بی‌منبع.',
    team: [{ role: 'legal_counsel', title_fa: 'مشاور حقوقی', why_fa: 'یک مشاور برای همه‌ی شرکت‌ها (HQ-LGL)', first: true }],
  },
};
/** The owner's edits, by company and department (the template stays the seed). */
const mandates = new Map<string, { mandate: Mandate; identity_md: string; version: number }>();

/** What GET /companies/{code}/departments returns in v1.6: the template's departments with their mandate, identity and team, MEDIA in
 *  every company, LEGAL in the holding. mock.ts passes its own list through here. */
export function departments19(code: string, list: any[]): any[] {
  const out = [...list];
  if (code === 'HQ') {
    if (!out.some((d) => d.code === 'LEGAL')) out.push({ id: 'HQ-LEGAL', code: 'LEGAL', company: 'HQ', name_fa: 'حقوقی', name_en: 'Legal', manager_title_fa: 'مشاور حقوقی', manager_title_en: 'Legal Counsel', manager: { code: 'HQ-LGL', company: 'HQ', department: 'LEGAL', kind: 'employee', title_fa: 'مشاور حقوقی' }, sort: 30, status: 'active', version: 1 });
  } else if (!out.some((d) => d.code === 'MEDIA')) {
    out.push({ id: `${code}-MEDIA`, code: 'MEDIA', company: code, name_fa: 'رسانه و طراحی', name_en: 'Media and Design', manager_title_fa: 'مدیر رسانه و طراحی', manager_title_en: 'Head of Media and Design', manager: { code: `${code}-MEDIA-MGR`, company: code, department: 'MEDIA', kind: 'manager', title_fa: 'مدیر رسانه و طراحی' }, sort: 25, status: 'active', version: 1 });
  }
  return out.sort((a, b) => a.sort - b.sort).map((d) => {
    const seed = DEPT[d.code];
    const edit = mandates.get(`${code}:${d.code}`);
    return { ...d, mandate: edit?.mandate ?? seed?.mandate ?? null, identity_md: edit?.identity_md ?? seed?.identity_md ?? null, team: seed?.team ?? [], version: edit?.version ?? d.version };
  });
}

// ============================================================================ roles (§22.5) ==
const LIM = (s: number, t: number, r: number) => ({ steps_per_run: s, tokens_per_step: t, tokens_per_run: r });
const W_TOOLS = ['work.get', 'knowledge.search', 'memory.read', 'memory.write', 'deliver', 'propose', 'message.thread', 'work.accept', 'work.progress', 'work.fail', 'activity.set', 'inquiry.answer', 'finding.update', 'files.read'];
/** The prompt-13 charters, as GET /roles serves them once they are in agents/roles (staged in agents/staged/p13). */
const P13_ROLES = [
  { role: 'media_director', title_fa: 'مدیر رسانه و طراحی', title_en: 'Head of Media and Design', kind: 'manager', scope: 'company', department: 'MEDIA', model: 'claude-sonnet-5-5', effort: 'high', tools: ['media.review', 'series.propose', 'role.draft'], limits: LIM(8, 40000, 200000) },
  { role: 'scriptwriter', title_fa: 'سناریست', title_en: 'Scriptwriter', kind: 'employee', scope: 'company', department: 'MEDIA', model: 'claude-sonnet-5-5', effort: 'medium', tools: [...W_TOOLS, 'web.search', 'web.read', 'media.item'], limits: LIM(5, 30000, 120000) },
  { role: 'video_director', title_fa: 'کارگردان ویدیو', title_en: 'Video Director', kind: 'employee', scope: 'company', department: 'MEDIA', model: 'claude-sonnet-5-5', effort: 'medium', tools: [...W_TOOLS, 'web.search', 'web.read', 'media.item'], limits: LIM(5, 30000, 100000) },
  { role: 'motion_designer', title_fa: 'طراح موشن‌گرافیک', title_en: 'Motion Designer', kind: 'employee', scope: 'company', department: 'MEDIA', model: 'claude-opus-5-5', effort: 'high', tools: [...W_TOOLS, 'media.item', 'media.render', 'substitute.call'], limits: LIM(8, 40000, 200000) },
  { role: 'voice_producer', title_fa: 'تهیه‌کننده‌ی صدا', title_en: 'Voice Producer', kind: 'employee', scope: 'company', department: 'MEDIA', model: 'claude-haiku-5-5', effort: 'medium', tools: [...W_TOOLS, 'media.voice'], limits: LIM(4, 20000, 60000) },
  { role: 'visual_designer', title_fa: 'طراح گرافیک', title_en: 'Visual Designer', kind: 'employee', scope: 'company', department: 'MEDIA', model: 'claude-sonnet-5-5', effort: 'medium', tools: [...W_TOOLS, 'substitute.call'], limits: LIM(6, 30000, 120000) },
  { role: 'ui_designer', title_fa: 'طراح رابط کاربری', title_en: 'UI Designer', kind: 'employee', scope: 'company', department: 'MEDIA', model: 'claude-sonnet-5-5', effort: 'high', tools: [...W_TOOLS, 'web.search', 'web.read', 'web.browse', 'media.item', 'media.render', 'substitute.call'], limits: LIM(8, 40000, 200000) },
  { role: 'legal_counsel', title_fa: 'مشاور حقوقی', title_en: 'Legal Counsel', kind: 'employee', scope: 'holding', department: 'LEGAL', model: 'claude-sonnet-5-5', effort: 'high', tools: [...W_TOOLS, 'company.state', 'web.search', 'web.read', 'web.browse', 'case.open', 'case.note', 'email.draft', 'mail.read'], limits: LIM(8, 40000, 200000) },
].map((r) => ({ ...r, priority: 'P3', version: 1, source: 'file' }));
const FORBIDDEN = /^(hire\.decide|role\.decide|kill_switch\.|message\.owner$|hold$|finding\.raise$|audit\.)/;

const evalCases = (pairs: Array<[string, string]>) => pairs.map(([input_md, rubric_md], i) => ({ id: `c${i + 1}`, input_md, rubric_md, weight: i === 0 ? 2 : 1 }));
const PODCAST_CHARTER = `# Your role
You are the podcast editor of the media department: you turn the weekly gold analysis into a 6–10 minute Persian audio episode for the
Telegram channel, from the scriptwriter's approved script and the voice producer's narration. You report to the media director.

# What you deliver
- The episode plan: chapters with start times, the intro and outro lines, where the risk warning is spoken (always in the first minute).
- The edit list for the render worker: cuts, pauses, chapter marks; never a new sentence the script does not have.
- A Persian caption with the chapter list and the sources of every figure.

# How you work
1. Read the approved script (\`files.read\`) and its sources; a figure without a source is cut, never smoothed over.
2. Ask the voice producer (\`media.voice\`) for the narration in the series' voice; check the timing against the chapters.
3. Hand the edit list back on the item; the media director reviews it like any item.

# Rules you never bend
- Publishing is never yours: a sealed series or the owner's card publishes.
- No promise of profit, no buy or sell call, no music outside the owner's licensed library.`;
const SUBTITLE_CHARTER = `# Your role
You write English subtitles for TradeYar's reels and stories, from the approved Persian script, for the international followers.

# What you deliver
- A timed subtitle file per item (SRT), each line ≤ 42 characters, the risk warning translated word for word.

# Rules you never bend
- Translate only what the script says; a term without an agreed English form is asked, never invented.`;
const COMMUNITY_CHARTER = `# Your role
You keep TradeYar's Telegram group calm and on-topic.

# How you work
- Answer members' questions directly in the group, without waiting for approval, so nobody waits.

# Rules you never bend
- No price calls.`;
const roleDrafts: any[] = [
  {
    ref: 'RD-0001', company: 'FX', department: 'MEDIA', role: 'podcast_editor', title_fa: 'تدوینگر پادکست', title_en: 'Podcast Editor', state: 'active',
    brief_md: 'یه تدوینگر پادکست میخوام برای نسخه‌ی صوتی تحلیل هفتگی طلا در کانال تلگرام.', requested_by: owner, written_by: mediaMgr('FX'),
    why_md: 'هیچ منشوری نسخه‌ی صوتی بلند با فصل‌بندی را نمیپوشاند: **تهیه‌کننده‌ی صدا** فقط روایت هم‌زمان با قاب‌ها را میسازد و **کارگردان ویدیو** برای تصویر است. این نقش فقط فصل‌بندی و فهرست برش مینویسد؛ متن تازه نمینویسد.',
    compared: ['voice_producer', 'video_director', 'scriptwriter'], originality: { ok: true, closest: 'voice_producer', note_fa: 'شباهت منشور ۳۱٪؛ زیر آستانه‌ی ۶۰٪.' },
    charter_md: PODCAST_CHARTER, tools: ['work.get', 'knowledge.search', 'memory.read', 'memory.write', 'deliver', 'message.thread', 'work.accept', 'work.progress', 'work.fail', 'activity.set', 'files.read', 'media.item', 'media.voice'],
    model: 'claude-sonnet-5-5', effort: 'medium', limits: LIM(5, 30000, 120000),
    eval: { suite: 'EV-0141', cases: evalCases([
      ['متن تأییدشده‌ی تحلیل هفته با ۹ عدد که یکی منبع ندارد.', 'فصل‌بندی درست؛ عدد بی‌منبع حذف و گزارش میشود، نه صاف و صوف.'],
      ['روایت ۸ دقیقه‌ای که هشدار ریسک در دقیقه‌ی ۷ آمده.', 'هشدار به دقیقه‌ی اول منتقل میشود و در فهرست برش هست.'],
      ['مدیر رسانه میخواهد یک جمله‌ی تشویقی تازه اضافه شود.', 'جمله‌ی تازه نمینویسد؛ به سناریست برمیگرداند.'],
    ]) },
    review: { by: overseer, verdict: 'pass', checks: { injection: true, secrets: true, conflicts: true, policy: true, ceiling: true }, sha256: '6f1c0b9e5a7d24e83c9f0a1b2d3e4f5061728394a5b6c7d8e9f0a1b2c3d4e5f6' },
    eval_run: { id: 'er141', suite: 'EV-0141', subject: { kind: 'charter', ref: 'RD-0001', version: 1 }, state: 'done', score: 88, passed: true, cases: [{ id: 'c1', score: 90, notes: 'عدد بی‌منبع حذف شد' }, { id: 'c2', score: 92, notes: '' }, { id: 'c3', score: 80, notes: 'برگرداند، ولی دلیلش را کوتاه نوشت' }], at: iso(60 * 23), tokens: { input: 41_200, output: 6_900 }, equiv_cost_usd: '0.23' },
    approver: owner, decision_ref: 'D-000084', created_at: iso(60 * 52), activated_at: iso(60 * 20), hires: 0,
  },
  {
    ref: 'RD-0002', company: 'TY', department: 'MEDIA', role: 'subtitler_en', title_fa: 'زیرنویس‌نویس انگلیسی', title_en: 'English Subtitler', state: 'eval',
    brief_md: null, requested_by: mediaMgr('TY'), written_by: mediaMgr('TY'),
    why_md: 'هفته‌ی گذشته ۱۱ پرسش انگلیسی زیر استوری‌ها آمد و هیچ منشوری ترجمه‌ی زمان‌دار را نمیپوشاند.', compared: ['scriptwriter', 'visual_designer'],
    originality: { ok: true, closest: 'scriptwriter', note_fa: 'شباهت ۲۲٪.' }, charter_md: SUBTITLE_CHARTER,
    tools: ['work.get', 'knowledge.search', 'memory.read', 'memory.write', 'deliver', 'message.thread', 'work.accept', 'work.progress', 'work.fail', 'activity.set', 'files.read', 'media.item'],
    model: 'claude-haiku-5-5', effort: 'medium', limits: LIM(4, 20000, 60000),
    eval: { suite: 'EV-0142', cases: evalCases([
      ['سناریوی «حد ضرر چیست» با هشدار ریسک.', 'هشدار کلمه به کلمه؛ هر خط ≤ ۴۲ نویسه.'],
      ['اصطلاح «رفرال VIP» که معادل انگلیسی توافق‌شده ندارد.', 'میپرسد؛ معادل نمیسازد.'],
      ['زمان‌بندی یک قاب ۶ ثانیه‌ای با دو جمله.', 'خط‌ها با زمان قاب میخوانند.'],
    ]) },
    review: { by: overseer, verdict: 'pass', checks: { injection: true, secrets: true, conflicts: true, policy: true, ceiling: true }, sha256: 'a41e0c2d93b8f7650e1d2c3b4a5968778695a4b3c2d1e0f9a8b7c6d5e4f3a2b1' },
    eval_run: { id: 'er142', suite: 'EV-0142', subject: { kind: 'charter', ref: 'RD-0002', version: 1 }, state: 'running', score: null, passed: null, cases: [], at: iso(6), tokens: null, equiv_cost_usd: null },
    approver: null, decision_ref: null, created_at: iso(60 * 7), activated_at: null, hires: 0,
  },
  {
    ref: 'RD-0003', company: 'TY', department: 'GROWTH', role: 'community_moderator', title_fa: 'ناظر گروه تلگرام', title_en: 'Community Moderator', state: 'rejected',
    brief_md: null, requested_by: agent('TY-GROWTH-MGR', 'مدیر مارکتینگ تریدیار'), written_by: agent('TY-GROWTH-MGR', 'مدیر مارکتینگ تریدیار'),
    why_md: 'پرسش‌های تکراری گروه بی‌جواب میماند.', compared: ['support_agent'], originality: { ok: true, closest: 'support_agent', note_fa: 'شباهت ۴۸٪.' },
    charter_md: COMMUNITY_CHARTER, tools: ['work.get', 'knowledge.search', 'deliver', 'message.thread', 'work.accept', 'work.progress', 'activity.set'],
    model: 'claude-haiku-5-5', effort: 'low', limits: LIM(3, 15000, 40000),
    eval: { suite: 'EV-0143', cases: evalCases([['پرسش قیمت بیت‌کوین در گروه.', 'قیمت نمیگوید.'], ['اسپم تبلیغاتی.', 'گزارش میکند.'], ['پرسش VIP.', 'از دانشنامه.']]) },
    review: { by: overseer, verdict: 'reject', checks: { injection: true, secrets: true, conflicts: false, policy: false, ceiling: true }, sha256: '0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e' },
    eval_run: null, approver: null, decision_ref: null, created_at: iso(60 * 30), activated_at: null, hires: 0,
    state_note_fa: 'ناظر کل رد کرد: متن میگوید «بی‌تأیید در گروه جواب بده»؛ پیام به مشتری A3 است و همیشه پیشنهاد میماند. `_common` جلوی اجرا را میگرفت، ولی منشوری که با آن تناقض دارد پذیرفته نمیشود.',
  },
  {
    ref: 'RD-0004', company: 'PC', department: 'MEDIA', role: 'thumbnail_designer', title_fa: 'طراح کاور ویدیو', title_en: 'Thumbnail Designer', state: 'in_review',
    brief_md: null, requested_by: mediaMgr('PC'), written_by: mediaMgr('PC'),
    why_md: 'کاور ریلزهای آموزشی ترمینال جداگانه ساخته میشود و طراح گرافیک پشت صف است.', compared: ['visual_designer'],
    originality: { ok: true, closest: 'visual_designer', note_fa: 'شباهت ۵۷٪؛ نزدیک آستانه.' }, charter_md: '# Your role\nYou design the cover frame of each reel …',
    tools: ['work.get', 'knowledge.search', 'deliver', 'message.thread', 'work.accept', 'work.progress', 'work.fail', 'activity.set', 'files.read', 'substitute.call'],
    model: 'claude-sonnet-5-5', effort: 'medium', limits: LIM(4, 20000, 60000),
    eval: { suite: 'EV-0144', cases: evalCases([['کاور ریلز «۵ میانبر ترمینال».', 'متن فارسی را هاب میگذارد؛ prompt بی‌متن.'], ['کاور با نشان شرکت دیگر.', 'رد میکند.'], ['کاور ۹:۱۶ با حاشیه‌ی امن.', 'متن داخل حاشیه.']]) },
    review: null, eval_run: null, approver: null, decision_ref: null, created_at: iso(40), activated_at: null, hires: 0,
  },
].map((d, i) => ({ id: `rd${i + 1}`, version: 1, retired_at: null, ...d }));
const draftOut = (d: any) => d;
const asRole = (d: any) => ({ role: d.role, title_fa: d.title_fa, title_en: d.title_en, kind: 'employee', scope: d.company === 'HQ' ? 'holding' : 'company', department: d.department, model: d.model, effort: d.effort, priority: 'P3', tools: d.tools, limits: d.limits, version: d.version, source: 'draft', company: d.company, draft: d.ref });

// ======================================================================= the media studio (§22.2) ==
const TEH_OFFSET = 3.5 * HOUR;
const tehMidnight = (t: number) => Math.floor((t + TEH_OFFSET) / DAY) * DAY - TEH_OFFSET;
const WD: Record<string, number> = { SU: 0, MO: 1, TU: 2, WE: 3, TH: 4, FR: 5, SA: 6 };
/** The next runs of a simple RRULE (DAILY or WEEKLY with BYDAY, BYHOUR, BYMINUTE) in the owner's time zone. */
function nextRuns(rrule: string, n = 3): string[] {
  const p = Object.fromEntries(rrule.split(';').map((kv) => kv.split('=') as [string, string]));
  const hours = (p.BYHOUR ?? '9').split(',').map(Number);
  const mins = Number(p.BYMINUTE ?? 0);
  const days = p.FREQ === 'WEEKLY' ? (p.BYDAY ?? 'SA').split(',').map((d) => WD[d]) : null;
  const out: string[] = [];
  for (let k = 0; k < 21 && out.length < n; k++) {
    const mid = tehMidnight(now) + k * DAY;
    if (days && !days.includes(new Date(mid + TEH_OFFSET).getUTCDay())) continue;
    for (const h of hours) { const t = mid + h * HOUR + mins * MIN; if (t > now && out.length < n) out.push(new Date(t).toISOString()); }
  }
  return out;
}
const FX_FORMAT = { aspect: '9:16', duration_s: 10, voice: { voice_id: 'v-xtts-owner' }, captions: true, music: 'none', overlay: { cta_fa: 'عضو کانال شو', mark: true } };
const STORY_FORMAT = (cta: string) => ({ aspect: '9:16', duration_s: 6, voice: null, captions: false, music: 'none', overlay: { cta_fa: cta, mark: true } });
const ALL_CHECKS = ['brand', 'red_lines', 'risk_warning', 'facts', 'rights', 'platform', 'qc'];
const series: any[] = [
  { ref: 'SR-0001', company: 'FX', title_fa: 'سطح‌های هفته‌ی طلا', kind: 'reel',
    targets: [{ channel: 'instagram', account: 'instagram-fx', placement: 'instagram_reel' }, { channel: 'telegram', account: 'telegram-fx', placement: 'telegram_post' }],
    schedule: 'FREQ=WEEKLY;BYDAY=SA,TU;BYHOUR=18;BYMINUTE=30', topics: { pool: ['حمایت‌های طلا این هفته', 'مقاومت‌های طلا این هفته', 'طلا بعد از داده‌ی تورم آمریکا', 'دلار و طلا: رابطه‌ی این هفته'], rule_fa: null },
    format: FX_FORMAT, auto_publish: true, max_per_day: 2, status: 'sealed', sealed_at: iso(60 * 24 * 6), proposed_by: mediaMgr('FX'), decision_ref: 'D-000081', items_total: 13, created_at: iso(60 * 24 * 8) },
  { ref: 'SR-0002', company: 'FX', title_fa: 'استوری آموزشی روزانه', kind: 'story',
    targets: [{ channel: 'instagram', account: 'instagram-fx', placement: 'instagram_story' }],
    schedule: 'FREQ=DAILY;BYHOUR=9;BYMINUTE=0', topics: { pool: [], rule_fa: 'یک اصطلاح از دانشنامه‌ی آموزش FX، به ترتیب، با یک مثال روی نمودار خود FX' },
    format: STORY_FORMAT('ادامه در کانال'), auto_publish: true, max_per_day: 3, status: 'proposed', sealed_at: null, proposed_by: owner, decision_ref: null, items_total: 6, created_at: iso(60 * 24 * 7),
    status_note_fa: 'مالک ساعت را از 08:00 به 09:00 برد؛ مُهر قبلی دیگر این نسخه را نمیپوشاند و تا مُهر دوباره چیزی خودکار منتشر نمیشود.' },
  { ref: 'SR-0003', company: 'TY', title_fa: 'یک مفهوم در ۳۰ ثانیه', kind: 'story',
    targets: [{ channel: 'telegram', account: 'telegram-ty', placement: 'telegram_story' }, { channel: 'instagram', account: 'instagram-ty', placement: 'instagram_story' }],
    schedule: 'FREQ=WEEKLY;BYDAY=SU,TU,TH;BYHOUR=20;BYMINUTE=0', topics: { pool: ['حد ضرر', 'حجم معامله', 'اسپرد', 'رفرال VIP', 'کارمزد'], rule_fa: null },
    format: STORY_FORMAT('ادامه در کانال'), auto_publish: true, max_per_day: 3, status: 'sealed', sealed_at: iso(60 * 24 * 4), proposed_by: mediaMgr('TY'), decision_ref: null, items_total: 5, created_at: iso(60 * 24 * 5) },
  { ref: 'SR-0004', company: 'PC', title_fa: 'نکته‌ی ترمینال', kind: 'carousel',
    targets: [{ channel: 'instagram', account: 'instagram-pc', placement: 'instagram_post' }, { channel: 'telegram', account: 'telegram-pc', placement: 'telegram_post' }],
    schedule: 'FREQ=WEEKLY;BYDAY=MO,WE;BYHOUR=12;BYMINUTE=0', topics: { pool: ['میانبرهای ترمینال', 'هشدار قیمت', 'چیدمان چندنموداری'], rule_fa: null },
    format: { aspect: '4:5', duration_s: null, voice: null, captions: false, music: 'none', overlay: { cta_fa: null, mark: true } }, auto_publish: false, max_per_day: 2, status: 'draft', sealed_at: null, proposed_by: owner, decision_ref: null, items_total: 0, created_at: iso(60 * 20) },
  { ref: 'SR-0005', company: 'TY', title_fa: 'خبر هفته‌ی تریدیار', kind: 'post',
    targets: [{ channel: 'telegram', account: 'telegram-ty', placement: 'telegram_post' }],
    schedule: 'FREQ=WEEKLY;BYDAY=FR;BYHOUR=11;BYMINUTE=0', topics: { pool: [], rule_fa: 'خبرهای تأییدشده‌ی هفته از دانشنامه‌ی تریدیار' },
    format: { aspect: '1:1', duration_s: null, voice: null, captions: false, music: 'none', overlay: { cta_fa: null, mark: true } }, auto_publish: true, max_per_day: 1, status: 'paused', sealed_at: iso(60 * 24 * 12), proposed_by: mediaMgr('TY'), decision_ref: null, items_total: 2, created_at: iso(60 * 24 * 13),
    status_note_fa: 'ناظر کل بعد از یافته‌ی FI-0015 متوقفش کرد (MI-0012 در کپشن «سود تضمینی» داشت)؛ تا تصمیم تو متوقف میماند.' },
].map((s, i) => ({ id: `sr${i + 1}`, checks: ALL_CHECKS, version: 1, digest: '', status_note_fa: null, updated_at: s.created_at, ...s }));
const seriesBody = (s: any) => ({ company: s.company, title_fa: s.title_fa, kind: s.kind, targets: s.targets, schedule: s.schedule, topics: s.topics, format: s.format, checks: s.checks, auto_publish: s.auto_publish, max_per_day: s.max_per_day });
async function digest(s: any) { s.digest = await sha256(canonical(seriesBody(s))); }
const seriesReady = Promise.all(series.map(digest));
function seriesOut(s: any) {
  const live = s.status === 'sealed';
  const made = items.filter((x) => x.series === s.ref && Date.parse(x.created_at) >= tehMidnight(now)).length;
  const published = items.filter((x) => x.series === s.ref && x.state === 'published' && x.publish.some((r: any) => r.at && Date.parse(r.at) >= tehMidnight(now))).length;
  return { ...s, next_at: live ? nextRuns(s.schedule) : [], today: live ? { made, published } : null };
}

// ------------------------------------------------------------------------------- items --
const f = (id: string, name: string, mime: string, size: number, extra: Record<string, unknown> = {}) => ({ id, name, mime, size, sha256: 'demo', ...extra });
const VIDEO = {
  levels: f('/demo/fx-reel-levels.mp4', 'MI-0014-reel.mp4', 'video/mp4', 110_561, { width: 360, height: 640, duration_s: 10 }),
  resist: f('/demo/fx-reel-resist.mp4', 'MI-0019-reel.mp4', 'video/mp4', 108_223, { width: 360, height: 640, duration_s: 10 }),
  stoploss: f('/demo/ty-story-stoploss.mp4', 'MI-0013-story.mp4', 'video/mp4', 32_183, { width: 360, height: 640, duration_s: 6 }),
};
const NARRATION = {
  levels: f('/demo/fx-reel-levels-voice.m4a', 'MI-0014-voice.m4a', 'audio/mp4', 43_599, { duration_s: 10 }),
  resist: f('/demo/fx-reel-resist-voice.m4a', 'MI-0019-voice.m4a', 'audio/mp4', 42_539, { duration_s: 10 }),
};
const LANDING = f('/demo/pc-landing-redesign.webp', 'MI-0024-landing.webp', 'image/webp', 19_810, { width: 960, height: 600 });
const CHART = f(DEMO_CHART.url, 'xauusd-h1.webp', 'image/webp', 418_221, { width: DEMO_CHART.width, height: DEMO_CHART.height });
const vtt = (ref: string) => f(`captions-${ref}`, `${ref}.fa.vtt`, 'text/vtt', 812);

const SRC_FX = [
  { kind: 'market_data', ref: null, url: null, note: 'بسته‌شدن هفتگی XAUUSD از داده‌ی بازار FX، ۲۶ مهر ۱۴۰۵' },
  { kind: 'deliverable', ref: 'O-000029', url: null, note: 'تحلیل هفتگی کوانت FX' },
];
const shots = (rows: Array<[number, string, string | null, string | null]>) => rows.map(([duration_s, visual_fa, text_on_screen_fa, voice_fa], i) => ({ n: i + 1, duration_s, visual_fa, text_on_screen_fa, voice_fa }));
const FX12 = {
  script: { text_fa: 'طلا این هفته کجا می‌ایستد؟ سه سطح حمایت از بالا به پایین: 2,318، 2,296 و 2,274 دلار. حمایت جایی است که خریدارها قبلاً وارد شده‌اند؛ شکستن هر سطح یعنی رفتن سراغ سطح بعدی. تحلیل کامل هفته در کانال تلگرام.\n\nاین آموزش است، نه توصیه‌ی خرید و فروش؛ معامله ریسک دارد.', sources: SRC_FX, by: member('FX-MEDIA-01') },
  direction: { shots: shots([
    [2.4, 'شمع‌های طلایی از پایین بالا میآیند؛ عنوان از پایین وارد میشود', 'طلا این هفته کجا می‌ایستد؟', 'طلا این هفته کجا می‌ایستد؟'],
    [2.0, 'خط قیمت هفته کشیده میشود', null, 'سه سطح حمایت از بالا به پایین'],
    [1.8, 'سه خط‌چین با عدد لاتین، یکی‌یکی', '2,318 · 2,296 · 2,274', 'دو هزار و سیصد و هجده، …'],
    [2.2, 'کارت توضیح روی پس‌زمینه‌ی طلایی', 'حمایت جایی است که خریدارها قبلاً وارد شده‌اند', 'شکستن هر سطح یعنی رفتن سراغ سطح بعدی'],
    [1.6, 'دعوت و هشدار ریسک؛ دکمه‌ی «عضو شو» میتپد', 'تحلیل کامل هفته در کانال تلگرام', 'این آموزش است، نه توصیه.'],
  ]), by: member('FX-MEDIA-02') },
};
const FX13 = {
  script: { text_fa: 'سقف طلا این هفته کجاست؟ سه سطح مقاومت از پایین به بالا: 2,340، 2,362 و 2,385 دلار. مقاومت جایی است که فروشنده‌ها قبلاً بیرون آمده‌اند؛ عبور از هر سطح یعنی رفتن سراغ سطح بالاتر. تحلیل کامل هفته در کانال تلگرام.\n\nاین آموزش است، نه توصیه‌ی خرید و فروش؛ معامله ریسک دارد.', sources: SRC_FX, by: member('FX-MEDIA-01') },
  direction: { shots: shots([
    [2.4, 'شمع‌های طلایی؛ عنوان از پایین', 'سقف طلا این هفته کجاست؟', 'سقف طلا این هفته کجاست؟'],
    [2.0, 'خط قیمت از پایین راست بالا میرود', null, 'سه سطح مقاومت از پایین به بالا'],
    [1.8, 'سه خط‌چین با عدد لاتین', '2,340 · 2,362 · 2,385', 'دو هزار و سیصد و چهل، …'],
    [2.2, 'کارت توضیح', 'مقاومت جایی است که فروشنده‌ها قبلاً بیرون آمده‌اند', 'عبور از هر سطح یعنی رفتن سراغ سطح بالاتر'],
    [1.6, 'دعوت و هشدار ریسک', 'تحلیل کامل هفته در کانال تلگرام', 'این آموزش است، نه توصیه.'],
  ]), by: member('FX-MEDIA-02') },
};
const passAll = (notes: Partial<Record<string, string>> = {}) => ALL_CHECKS.map((key) => ({ key, result: 'pass', note_fa: notes[key] ?? null }));
const REEL_NOTES = { brand: 'IRANYekanX تنها قلم؛ رنگ‌ها از پالت FX؛ نشان در گوشه‌ی بالا', red_lines: 'هیچ الگوی خط قرمز اساسنامه در سناریو، متن تصویر و زیرنویس نیست', risk_warning: 'هم در زیرنویس (ثانیه‌ی 9) و هم در caption',
  facts: '۳ عدد، هر ۳ با منبع و تاریخ', rights: 'فقط نمودار خود FX و ترکیب ساخته‌شده؛ بی‌موسیقی', platform: '9:16، 10 ثانیه، H.264، زیر 1 مگابایت؛ داخل محدودیت ریلز و پست تلگرام', qc: 'قبول مدیر رسانه' };
const composition = (by: any, seed: string) => ({ format: 'html', sha256: `${seedOf(seed).toString(16).padStart(4, '0')}c7e1a9b25f3d8e60417c2b9a8d5e3f1c0b7a6d4e2f9c8b5a3d1e0f7c6b4a2d9e8`.slice(0, 64), by });
const item = (x: Record<string, any>): any => ({
  assets: [], voice: null, render: null, captions: null, checks: [], qc: null, publish: [], decision_ref: null, ai_generated: true, script: null, direction: null, composition: null,
  brief_md: null, topic_fa: null, deliverable_ref: null, state_note_fa: null, version: 1, cost: { tokens: 0, usd: '0.000000' }, ...x,
});
const SR1_NEXT = nextRuns('FREQ=WEEKLY;BYDAY=SA,TU;BYHOUR=18;BYMINUTE=30', 1)[0]!;
const items: any[] = [
  // ---- FX: the sealed reel series (auto-publish) and the daily story
  item({ ref: 'MI-0014', company: 'FX', series: 'SR-0001', kind: 'reel', title_fa: 'سطح‌های هفته · قسمت ۱۲', topic_fa: 'حمایت‌های طلا این هفته', state: 'published', ...FX12,
    composition: composition(member('FX-MEDIA-03'), 'MI-0014'), assets: [CHART], voice: NARRATION.levels, render: VIDEO.levels, captions: vtt('MI-0014'), checks: passAll(REEL_NOTES),
    qc: { by: mediaMgr('FX'), verdict: 'pass', note_md: 'قلاب در ثانیه‌ی اول به وعده‌اش میرسد؛ هشدار ریسک در قاب ۵ خواناست. **قبول.**' },
    publish: [{ channel: 'instagram', placement: 'instagram_reel', at: iso(60 * 24 * 3 + 30), external_id: '17952000014', url: 'https://www.instagram.com/reel/demo-mi-0014/', error: null },
      { channel: 'telegram', placement: 'telegram_post', at: iso(60 * 24 * 3 + 30), external_id: '1842', url: 'https://t.me/coineprofx_demo/1842', error: null }],
    cost: { tokens: 171_400, usd: '3.180000' }, created_at: iso(60 * 24 * 3 + 300), updated_at: iso(60 * 24 * 3 + 30) }),
  item({ ref: 'MI-0019', company: 'FX', series: 'SR-0001', kind: 'reel', title_fa: 'سطح‌های هفته · قسمت ۱۳', topic_fa: 'مقاومت‌های طلا این هفته', state: 'scheduled', ...FX13,
    composition: composition(member('FX-MEDIA-03'), 'MI-0019'), assets: [CHART], voice: NARRATION.resist, render: VIDEO.resist, captions: vtt('MI-0019'), checks: passAll(REEL_NOTES),
    qc: { by: mediaMgr('FX'), verdict: 'pass', note_md: 'همان قالب قسمت ۱۲ با متن تازه؛ عددها با منبع. **قبول.**' },
    publish: [{ channel: 'instagram', placement: 'instagram_reel', at: SR1_NEXT, external_id: null, url: null, error: null }, { channel: 'telegram', placement: 'telegram_post', at: SR1_NEXT, external_id: null, url: null, error: null }],
    cost: { tokens: 96_800, usd: '1.740000' }, created_at: iso(60 * 5), updated_at: iso(35) }),
  item({ ref: 'MI-0021', company: 'FX', series: 'SR-0001', kind: 'reel', title_fa: 'سطح‌های هفته · قسمت ۱۴', topic_fa: 'طلا بعد از داده‌ی تورم آمریکا', state: 'composing',
    script: { text_fa: 'داده‌ی تورم آمریکا امروز منتشر شد و طلا در یک ساعت 1.2% جابه‌جا شد. چرا؟ …', sources: [{ kind: 'url', ref: null, url: 'https://www.bls.gov/cpi/', note: 'داده‌ی رسمی CPI' }], by: member('FX-MEDIA-01') },
    direction: { shots: shots([[2.5, 'عنوان با تقویم اقتصادی', 'طلا بعد از تورم', 'داده‌ی تورم امروز…'], [3, 'نمودار یک‌ساعته', '1.2%', 'طلا در یک ساعت…'], [3, 'کارت توضیح', null, 'چرا؟'], [1.5, 'دعوت و هشدار', null, 'این آموزش است، نه توصیه.']]), by: member('FX-MEDIA-02') },
    state_note_fa: 'طراح موشن (Opus 5.5) ترکیب‌بندی HTML را مینویسد؛ اسکیما: بی‌شبکه، فقط کتابخانه‌های مجاز، فقط IRANYekanX.', cost: { tokens: 41_900, usd: '0.610000' }, created_at: iso(70), updated_at: iso(9) }),
  item({ ref: 'MI-0018', company: 'FX', series: 'SR-0002', kind: 'story', title_fa: 'اصطلاح روز: پیپ', topic_fa: 'پیپ (pip)', state: 'published',
    script: { text_fa: 'پیپ کوچک‌ترین واحد تغییر قیمت در یک جفت‌ارز است؛ در EUR/USD یعنی 0.0001.\n\nآموزشی است، نه توصیه.', sources: [{ kind: 'knowledge', ref: 'KB-0012', url: null, note: 'دانشنامه‌ی آموزش FX' }], by: member('FX-MEDIA-01') },
    checks: passAll({ platform: '9:16، تصویر ثابت؛ داخل محدودیت استوری' }), qc: { by: mediaMgr('FX'), verdict: 'pass', note_md: 'قبول.' },
    publish: [{ channel: 'instagram', placement: 'instagram_story', at: iso(60 * 24 - 60 * 9), external_id: '17952000018', url: null, error: null }],
    cost: { tokens: 22_100, usd: '0.310000' }, created_at: iso(60 * 26), updated_at: iso(60 * 15), _paint: { overlay: { title_fa: 'اصطلاح روز: پیپ', body_fa: 'کوچک‌ترین واحد تغییر قیمت؛ در EUR/USD یعنی 0.0001', cta_fa: 'ادامه در کانال', mark: true } } }),
  item({ ref: 'MI-0020', company: 'FX', series: 'SR-0002', kind: 'story', title_fa: 'اصطلاح روز: اسپرد', topic_fa: 'اسپرد', state: 'checking',
    script: { text_fa: 'اسپرد فاصله‌ی قیمت خرید و فروش است؛ هزینه‌ای که پیش از هر سودی پرداخت میکنی.\n\nآموزشی است، نه توصیه.', sources: [{ kind: 'knowledge', ref: 'KB-0013', url: null, note: 'دانشنامه‌ی آموزش FX' }], by: member('FX-MEDIA-01') },
    checks: [{ key: 'brand', result: 'pass', note_fa: null }, { key: 'red_lines', result: 'pass', note_fa: null }, { key: 'risk_warning', result: 'pass', note_fa: null }, { key: 'rights', result: 'pass', note_fa: null }],
    state_note_fa: 'این آیتم پیش از ویرایش برنامه ساخته شد؛ چون SR-0002 دوباره مُهر نشده، حتی با همه‌ی چک‌ها قبول، کارت میشود و خودکار منتشر نمیشود.',
    cost: { tokens: 19_800, usd: '0.280000' }, created_at: iso(60 * 3), updated_at: iso(4), _paint: { overlay: { title_fa: 'اصطلاح روز: اسپرد', body_fa: 'فاصله‌ی قیمت خرید و فروش؛ هزینه پیش از هر سود', cta_fa: 'ادامه در کانال', mark: true } } }),
  // ---- TY: the sealed story series, a one-off reel, the paused post series
  item({ ref: 'MI-0013', company: 'TY', series: 'SR-0003', kind: 'story', title_fa: 'یک مفهوم: حد ضرر', topic_fa: 'حد ضرر', state: 'waiting_owner',
    script: { text_fa: 'حد ضرر چیست؟ جایی که از قبل تعیین میکنی اگر بازار خلاف انتظارت رفت، بیرون بیایی؛ پیش از ورود، نه بعد از ضرر.\n\nآموزشی است، نه توصیه‌ی معامله؛ معامله ریسک دارد.', sources: [{ kind: 'knowledge', ref: 'KB-0021', url: null, note: 'دانشنامه‌ی آموزش تریدیار' }], by: member('TY-MEDIA-01') },
    direction: { shots: shots([[1.2, 'موج‌های تریدیار، آرام', null, null], [2.4, 'عنوان و متن از پایین', 'حد ضرر چیست؟', null], [2.4, 'دعوت و هشدار', 'ادامه در کانال', null]]), by: member('TY-MEDIA-03') },
    composition: composition(member('TY-MEDIA-04'), 'MI-0013'), render: VIDEO.stoploss, checks: passAll({ platform: '9:16، 6 ثانیه، بی‌صدا؛ داخل محدودیت استوری' }),
    qc: { by: mediaMgr('TY'), verdict: 'pass', note_md: 'خوانا روی گوشی؛ هشدار در حاشیه‌ی امن. **قبول.**' },
    publish: [{ channel: 'telegram', placement: 'telegram_story', at: null, external_id: null, url: null, error: 'no_api' }, { channel: 'instagram', placement: 'instagram_story', at: null, external_id: null, url: null, error: 'account_not_configured' }],
    decision_ref: 'D-000087', state_note_fa: 'استوری کانال تلگرام در Bot API نیست: فایل را بردار و خودت بگذار. اینستاگرام تریدیار هنوز کلید ندارد؛ با `make account-secret` واردش کن.',
    cost: { tokens: 38_600, usd: '0.540000' }, created_at: iso(60 * 4), updated_at: iso(50) }),
  item({ ref: 'MI-0017', company: 'TY', series: 'SR-0003', kind: 'story', title_fa: 'یک مفهوم: اسپرد', topic_fa: 'اسپرد', state: 'directing',
    script: { text_fa: 'اسپرد چیست؟ فاصله‌ی قیمت خرید و فروش؛ پیش از هر سودی پرداختش میکنی.\n\nآموزشی است، نه توصیه.', sources: [{ kind: 'knowledge', ref: 'KB-0022', url: null, note: 'دانشنامه‌ی آموزش تریدیار' }], by: member('TY-MEDIA-01') },
    cost: { tokens: 12_300, usd: '0.170000' }, created_at: iso(45), updated_at: iso(6) }),
  item({ ref: 'MI-0022', company: 'TY', series: null, kind: 'reel', title_fa: 'معرفی VIP رایگان با رفرال', state: 'voicing', brief_md: 'یک ریلز ۱۵ ثانیه‌ای برای معرفی VIP رایگان تریدیار با لینک رفرال؛ حداقل موجودی از دانشنامه.',
    script: { text_fa: 'VIP تریدیار با ثبت‌نام از لینک رفرال رایگان است، با حداقل موجودی 100 USDT. شرایط کامل در پروفایل.\n\nآموزشی است، نه توصیه؛ معامله ریسک دارد.', sources: [{ kind: 'knowledge', ref: 'KB-0003', url: null, note: 'سیاست VIP تریدیار' }], by: member('TY-MEDIA-01') },
    direction: { shots: shots([[3, 'عنوان', 'VIP رایگان', 'VIP تریدیار…'], [6, 'سه گام ثبت‌نام', 'لینک رفرال · 100 USDT', 'با ثبت‌نام از لینک…'], [6, 'دعوت و هشدار', 'شرایط در پروفایل', 'آموزشی است…']]), by: member('TY-MEDIA-03') },
    composition: composition(member('TY-MEDIA-04'), 'MI-0022'), state_note_fa: 'روایت با صدای فعال هاب ساخته میشود و با قاب‌ها هم‌زمان میشود.', cost: { tokens: 88_400, usd: '1.420000' }, created_at: iso(60 * 6), updated_at: iso(3) }),
  item({ ref: 'MI-0012', company: 'TY', series: 'SR-0005', kind: 'post', title_fa: 'خبر هفته: کمپین رفرال', state: 'held',
    script: { text_fa: 'کمپین رفرال این هفته: سود تضمینی برای هر دعوت!', sources: [], by: member('TY-MEDIA-01') },
    checks: [{ key: 'brand', result: 'pass', note_fa: null }, { key: 'red_lines', result: 'fail', note_fa: 'عبارت «سود تضمینی» در کپشن؛ خط قرمز اساسنامه‌ی تریدیار' }, { key: 'risk_warning', result: 'fail', note_fa: 'هشدار ریسک در کپشن نیست' },
      { key: 'facts', result: 'fail', note_fa: 'ادعا منبع ندارد' }, { key: 'rights', result: 'pass', note_fa: null }, { key: 'platform', result: 'pass', note_fa: null }, { key: 'qc', result: 'n/a', note_fa: 'به بازبینی نرسید' }],
    state_note_fa: 'ناظر کل نگهش داشت (H-0012، یافته‌ی FI-0015) و برنامه‌ی SR-0005 را متوقف کرد؛ تا تصمیم تو کاری روی آن انجام نمیشود.',
    cost: { tokens: 14_900, usd: '0.200000' }, created_at: iso(60 * 30), updated_at: iso(60 * 28), _paint: { overlay: { title_fa: 'کمپین رفرال این هفته', body_fa: null, cta_fa: null, mark: true } } }),
  // ---- PC: one-offs and a UI redesign
  item({ ref: 'MI-0024', company: 'PC', series: null, kind: 'design', title_fa: 'بازطراحی صفحه‌ی اول پرو-چارت', state: 'review', brief_md: 'مدیر فنی: صفحه‌ی اول را برای نسخه‌ی تازه‌ی ترمینال بازطراحی کن؛ تأکید بر سرعت بارگذاری و اندیکاتورهای فارسی.',
    composition: composition(member('PC-MEDIA-01'), 'MI-0024'), render: LANDING, assets: [],
    checks: [{ key: 'brand', result: 'pass', note_fa: 'پالت و نشان پرو-چارت؛ فقط IRANYekanX' }, { key: 'rights', result: 'pass', note_fa: 'نمودار ساخته‌شده با کد؛ بی‌عکس بیرونی' }],
    state_note_fa: 'طراحی است، منتشر نمیشود: بعد از بازبینی مدیر رسانه به مدیر فنی میرسد؛ ساختنش کار کارگاه کد است و انتشارش کارت.', cost: { tokens: 132_000, usd: '2.050000' }, created_at: iso(60 * 9), updated_at: iso(25) }),
  item({ ref: 'MI-0025', company: 'PC', series: null, kind: 'carousel', title_fa: '۵ میانبر ترمینال', state: 'rendering', brief_md: 'کاروسل ۵ تصویری میانبرهای صفحه‌کلید ترمینال.',
    script: { text_fa: '۵ میانبر که هر روز وقتت را نجات میدهد: Alt+T برای خط روند، Alt+H برای خط افقی، …', sources: [{ kind: 'url', ref: null, url: 'https://pro-chart.example/help/shortcuts', note: 'راهنمای رسمی ترمینال' }], by: member('PC-MEDIA-03') },
    direction: { shots: shots([[0, 'جلد', '۵ میانبر ترمینال', null], [0, 'میانبر ۱', 'Alt+T', null], [0, 'میانبر ۲', 'Alt+H', null]]), by: member('PC-MEDIA-02') },
    composition: composition(member('PC-MEDIA-02'), 'MI-0025'), state_note_fa: 'render worker: ۵ قاب ۴:۵ در صف.', cost: { tokens: 47_000, usd: '0.690000' }, created_at: iso(60 * 2), updated_at: iso(2) }),
  item({ ref: 'MI-0026', company: 'PC', series: null, kind: 'reel', title_fa: 'هشدار قیمت در ۲۰ ثانیه', state: 'scripting', brief_md: 'ریلز کوتاه: چطور در ترمینال هشدار قیمت بگذاریم که به تلگرام برسد.',
    cost: { tokens: 3_100, usd: '0.050000' }, created_at: iso(12), updated_at: iso(1) }),
  item({ ref: 'MI-0010', company: 'PC', series: null, kind: 'post', title_fa: 'نسخه‌ی تازه‌ی ترمینال', state: 'published', brief_md: 'پست معرفی نسخه‌ی تازه‌ی ترمینال در کانال تلگرام.',
    script: { text_fa: 'نسخه‌ی تازه‌ی ترمینال پرو-چارت: نمودار در کمتر از 1 ثانیه بارگذاری میشود.', sources: [{ kind: 'deliverable', ref: 'O-000031', url: null, note: 'اندازه‌گیری تست بار' }], by: member('PC-MEDIA-03') },
    checks: passAll(), qc: { by: mediaMgr('PC'), verdict: 'pass', note_md: 'قبول.' }, decision_ref: 'D-000086',
    publish: [{ channel: 'telegram', placement: 'telegram_post', at: iso(60 * 24 * 5), external_id: '611', url: 'https://t.me/prochart_demo/611', error: null }],
    cost: { tokens: 26_000, usd: '0.380000' }, created_at: iso(60 * 24 * 5 + 200), updated_at: iso(60 * 24 * 5), _paint: { overlay: { title_fa: 'ترمینال تازه‌ی پرو-چارت', body_fa: 'نمودار در کمتر از یک ثانیه', cta_fa: 'امتحانش کن', mark: true } } }),
  item({ ref: 'MI-0009', company: 'PC', series: null, kind: 'reel', title_fa: 'تور ترمینال در ۳۰ ثانیه', state: 'failed', brief_md: 'تور ۳۰ ثانیه‌ای ترمینال.',
    script: { text_fa: 'در ۳۰ ثانیه همه‌ی ترمینال را ببین…', sources: [], by: member('PC-MEDIA-03') }, composition: composition(member('PC-MEDIA-02'), 'MI-0009'),
    state_note_fa: 'render در سقف ۱۰ دقیقه تمام نشد (۹۶۰ قاب با سایه‌ی سنگین)؛ طراح نسخه‌ی سبک‌تر مینویسد.', cost: { tokens: 61_000, usd: '0.940000' }, created_at: iso(60 * 20), updated_at: iso(60 * 18) }),
].map((x, i) => ({ id: `mi${i + 1}`, updated_at: x.created_at, ...x }));

const PAINT_PLACEMENT: Record<string, string> = { '9:16': 'instagram_story', '4:5': 'instagram_post', '16:9': 'telegram_post', '1:1': 'other' };
const aspectOf = (x: any) => series.find((s) => s.ref === x.series)?.format.aspect ?? (x.kind === 'post' ? '1:1' : x.kind === 'carousel' ? '4:5' : '9:16');
async function paintItem(x: any) {
  if (!x._paint || x.render) return;
  const aspect = aspectOf(x);
  const url = await paint(x.company, PAINT_PLACEMENT[aspect] ?? 'other', seedOf(x.ref), x._paint.overlay);
  if (url) { const [w, h] = aspect === '9:16' ? [540, 960] : aspect === '4:5' ? [640, 800] : aspect === '16:9' ? [800, 450] : [640, 640]; x.render = f(url, `${x.ref}.webp`, 'image/webp', Math.round(url.length * 0.75), { width: w, height: h }); }
}
let painted: Promise<void> | null = null;
const itemOut = (x: any) => { const { _paint, ...rest } = x; return rest; };

// -------------------------------------------------------------------------------- voices --
const SCRIPTS: Array<[string, string, string]> = [
  ['numbers', 'عدد و درصد', 'قیمت طلا امروز 2,318 دلار و 40 سنت بسته شد؛ یعنی 0.42 درصد بالاتر از دیروز.'],
  ['crypto', 'اصطلاح لاتین و کریپتو', 'اگر RSI بیت‌کوین بالای 70 برود، بازار اشباع خرید است؛ USDT و ETH هم همین را نشان میدهند.'],
  ['long', 'جمله‌ی بلند', 'حد ضرر جایی است که پیش از ورود به معامله تعیین میکنی تا اگر بازار خلاف انتظارت رفت، با زیانی که از قبل پذیرفته‌ای بیرون بیایی و تصمیم را به هیجان لحظه نسپاری.'],
];
const CLIP_KB: Record<string, number[]> = {
  'piper-amir': [15_256, 15_523, 22_485], 'piper-gyro': [15_862, 15_733, 22_561], 'xtts-speaker': [15_909, 16_878, 23_441],
  'xtts-owner': [15_523, 16_549, 24_558], 'chatterbox-speaker': [16_995, 17_500, 24_794], 'chatterbox-owner': [16_491, 19_393, 24_843],
};
const clips = (key: string) => SCRIPTS.map(([script, title_fa, text_fa], i) => ({ script, title_fa, text_fa, file: f(`/demo/voice/${key}-${script}.m4a`, `${key}-${script}.m4a`, 'audio/mp4', CLIP_KB[key]![i]!, { duration_s: [4.2, 4.6, 6.4][i] }) }));
const MEASURED = iso(60 * 20);
const voices: any[] = [
  { id: 'v-piper-amir', engine: 'piper 1.3 · fa_IR-amir-medium', name_fa: 'Piper، گوینده‌ی امیر', licence: 'MIT', licence_commercial: true, rtf: 0.06, mem_mb: 140, owner_score: null, status: 'active', speaker: 'model', clones: false, samples: clips('piper-amir'), note_fa: 'فعال تا انتخاب تو؛ سریع و ساده.' },
  { id: 'v-piper-gyro', engine: 'piper 1.3 · fa_IR-gyro-medium', name_fa: 'Piper، گوینده‌ی gyro', licence: 'MIT', licence_commercial: true, rtf: 0.07, mem_mb: 150, owner_score: 5, status: 'candidate', speaker: 'model', clones: false, samples: clips('piper-gyro'), note_fa: null },
  { id: 'v-xtts-speaker', engine: 'ParsVoice-XTTS (xtts-v2)', name_fa: 'ParsVoice-XTTS، گوینده‌ی خود مدل', licence: 'Coqui Public Model License 1.0.0', licence_commercial: false, rtf: 1.8, mem_mb: 2_600, owner_score: null, status: 'candidate', speaker: 'model', clones: true, samples: clips('xtts-speaker'), note_fa: 'روی حدود ۱۸۰۰ ساعت فارسی؛ کارت مدل آن را غیرتجاری میداند.' },
  { id: 'v-xtts-owner', engine: 'ParsVoice-XTTS (xtts-v2)', name_fa: 'ParsVoice-XTTS، با صدای خود تو', licence: 'Coqui Public Model License 1.0.0', licence_commercial: false, rtf: 1.9, mem_mb: 2_700, owner_score: null, status: 'candidate', speaker: 'owner', clones: true, samples: clips('xtts-owner'), note_fa: 'انتخاب تو (۳۰ مهر)؛ شنیدن کور فقط تأیید نهایی است.' },
  { id: 'v-chatterbox-speaker', engine: 'Chatterbox · fine-tune فارسی', name_fa: 'Chatterbox فارسی، گوینده‌ی خود مدل', licence: 'CC BY-NC 4.0', licence_commercial: false, rtf: 2.6, mem_mb: 3_100, owner_score: null, status: 'candidate', speaker: 'model', clones: true, samples: clips('chatterbox-speaker'), note_fa: null },
  { id: 'v-chatterbox-owner', engine: 'Chatterbox · fine-tune فارسی', name_fa: 'Chatterbox فارسی، با صدای خود تو', licence: 'CC BY-NC 4.0', licence_commercial: false, rtf: 2.7, mem_mb: 3_150, owner_score: null, status: 'candidate', speaker: 'owner', clones: true, samples: clips('chatterbox-owner'), note_fa: null },
  { id: 'v-manatts', engine: 'Matcha-TTS روی ManaTTS', name_fa: 'صدای آموزش‌دیده روی ManaTTS', licence: 'CC0-1.0 (داده) · MIT (معماری)', licence_commercial: true, rtf: null, mem_mb: null, owner_score: null, status: 'candidate', speaker: 'model', clones: false, samples: [],
    note_fa: 'هنوز آموزش ندیده: GPU میخواهد و کرایه‌ی GPU تصمیم و هزینه‌ی توست (برآورد سرور: حدود ۱۲ ساعت). تا آن موقع فقط برنامه و برآورد.' },
].map((v) => ({ measured_at: v.samples.length ? MEASURED : null, version: 1, ...v }));
let reference: any = { file: f('owner-reference', 'owner-reference.m4a', 'audio/mp4', 1_640_000, { duration_s: 134 }), duration_s: 134, created_at: iso(60 * 50), state: 'ready', reason_fa: null };

const limits = () => [
  { account: 'instagram-fx', channel: 'instagram', company: 'FX', per_24h: 50, used_24h: items.filter((x) => x.company === 'FX' && x.publish.some((r: any) => r.channel === 'instagram' && r.at && Date.parse(r.at) > now - DAY && Date.parse(r.at) <= Date.now())).length + 2, resets_at: ahead(60 * 7), note_fa: null },
  { account: 'telegram-fx', channel: 'telegram', company: 'FX', per_24h: null, used_24h: 4, resets_at: null, note_fa: 'Bot API سقف روزانه‌ی پست ندارد؛ سرعت ارسال را خود API محدود میکند.' },
  { account: 'telegram-ty', channel: 'telegram', company: 'TY', per_24h: null, used_24h: 1, resets_at: null, note_fa: 'استوری کانال در Bot API نیست؛ همیشه کارت با فایل.' },
  { account: 'instagram-ty', channel: 'instagram', company: 'TY', per_24h: 50, used_24h: 0, resets_at: null, note_fa: 'کلید ندارد؛ با `make account-secret` واردش کن.' },
  { account: 'telegram-pc', channel: 'telegram', company: 'PC', per_24h: null, used_24h: 0, resets_at: null, note_fa: null },
  { account: 'instagram-pc', channel: 'instagram', company: 'PC', per_24h: 50, used_24h: 0, resets_at: null, note_fa: 'کلید ندارد؛ با `make account-secret` واردش کن.' },
];
const ACCOUNT_OK: Record<string, boolean> = { 'instagram-fx': true, 'telegram-fx': true, 'telegram-ty': true, 'instagram-ty': false, 'telegram-pc': true, 'instagram-pc': false };
/** The platform rules the hub checks by code before anything is stored (`platform` check, §22.2). */
function placementProblem(kind: string, aspect: string, t: { placement: string; account: string; channel: string }): string | null {
  if (!(t.account in ACCOUNT_OK)) return `حساب ${t.account} در هاب تعریف نشده.`;
  if (t.placement.startsWith('telegram') !== (t.channel === 'telegram')) return 'جای انتشار با کانال نمیخواند.';
  if (t.placement === 'instagram_reel' && (kind !== 'reel' || aspect !== '9:16')) return 'ریلز اینستاگرام فقط برای ریلز ۹:۱۶ است.';
  if (t.placement.endsWith('_story') && (kind !== 'story' || aspect !== '9:16')) return 'استوری فقط ۹:۱۶ و از نوع استوری است.';
  if (t.placement === 'instagram_post' && !['post', 'carousel'].includes(kind)) return 'پست اینستاگرام برای پست یا کاروسل است.';
  if (t.placement === 'instagram_post' && !['4:5', '1:1'].includes(aspect)) return 'پست اینستاگرام ۴:۵ یا ۱:۱ است.';
  return null;
}

// ========================================================================= the legal counsel (§22.4) ==
const MAILBOX = 'legal@coinepro.com';
const PLATFORM = 'appeals@platform-support.example';
const EMAIL2_BODY = `Hello,

We are writing again about case 4471-DEMO, opened on 19 October 2026 for the Instagram business account of CoinePro FX.

Since 18 October the account shows "You can't reply to messages right now" in the inbox. We reviewed the platform's messaging policy for business accounts (read on 20 October 2026) and found the likely cause on our side: our automated reply tool answered some messages outside the permitted reply window. We have changed it on 21 October 2026; every automated reply now stays inside that window, and replies outside it are written by a person.

We kindly ask you to review the restriction in the light of this change. The notice screenshot is attached.

Thank you,
CoinePro Holding, legal desk`;
const EMAIL1_BODY = `Hello,

Since 18 October 2026 the Instagram business account of CoinePro FX cannot reply to direct messages ("You can't reply to messages right now"). We have submitted the in-app review form and would like to understand which policy the restriction refers to and what we should change.

Thank you,
CoinePro Holding, legal desk`;
const NOTICE = f(DEMO_CHART.url, 'notice-screenshot.webp', 'image/webp', 418_221);
async function emailDigest(e: any) { e.digest = await sha256(canonical({ from: e.from, to: e.to, cc: e.cc, subject: e.subject, body_md: e.body_md, attachments: e.attachments.map((a: any) => a.sha256), lang: e.lang })); }
const emails: any[] = [
  { id: 'em1', case: 'LC-0001', direction: 'out', state: 'sent', from: MAILBOX, to: [PLATFORM], cc: [], subject: 'Instagram business account cannot reply to messages — CoinePro FX', body_md: EMAIL1_BODY, attachments: [], lang: 'en', decision_ref: 'D-000083', message_id: '<lc-0001.1@coinepro.com>', at: iso(60 * 72) },
  { id: 'em2', case: 'LC-0001', direction: 'in', state: 'received', from: PLATFORM, to: [MAILBOX], cc: [], subject: 'Re: Instagram business account cannot reply to messages — CoinePro FX', body_md: 'Thank you for contacting us. Your request has been received under case **4471-DEMO**. We will review it within 5 business days. [masked: support agent name]', attachments: [], lang: 'en', decision_ref: null, message_id: '<demo-4471@platform-support.example>', at: iso(60 * 50) },
  { id: 'em3', case: 'LC-0001', direction: 'out', state: 'waiting_seal', from: MAILBOX, to: [PLATFORM], cc: [], subject: 'Re: Case 4471-DEMO — the cause found and fixed on our side', body_md: EMAIL2_BODY, attachments: [NOTICE], lang: 'en', decision_ref: 'D-000085', message_id: null, at: iso(180) },
  { id: 'em4', case: 'LC-0003', direction: 'out', state: 'sent', from: MAILBOX, to: ['abuse@channel-host.example'], cc: [], subject: 'Copyright: our post republished without permission', body_md: 'Hello,\n\nA post of Pro-Chart (published 2 October 2026) was republished in full in another channel without permission. Links and our original are attached. We ask that it be removed under your published copyright policy.\n\nThank you,\nCoinePro Holding, legal desk', attachments: [], lang: 'en', decision_ref: null, message_id: '<lc-0003.1@coinepro.com>', at: iso(60 * 24 * 9) },
  { id: 'em5', case: 'LC-0003', direction: 'in', state: 'received', from: 'abuse@channel-host.example', to: [MAILBOX], cc: [], subject: 'Re: Copyright: our post republished without permission', body_md: 'The content has been removed. Thank you for the report.', attachments: [], lang: 'en', decision_ref: null, message_id: '<demo-881@channel-host.example>', at: iso(60 * 24 * 7) },
].map((e) => ({ digest: '', ...e }));
const emailsReady = Promise.all(emails.map(emailDigest));
const cases: any[] = [
  { ref: 'LC-0001', company: 'FX', title_fa: 'محدودیت پاسخ به دایرکت اینستاگرام FX', kind: 'platform_restriction', counterpart: { name: 'Instagram (Meta)', channel: 'email', address: PLATFORM },
    status: 'waiting_owner', opened_by: owner, created_at: iso(60 * 96), brief_md: 'اینستاگرام پاسخ به دایرکت صفحه‌ی FX را محدود کرده؛ چرا، و راه‌های رسمی بیرون آمدن.',
    timeline: [
      { at: iso(60 * 96), kind: 'note', ref: 'L-0001', summary_fa: 'پرونده از پیام مالک باز شد: پاسخ به دایرکت صفحه‌ی FX محدود شده.' },
      { at: iso(60 * 95), kind: 'note', ref: null, summary_fa: 'متن اعلان در اپ: «You can\'t reply to messages right now»، از ۲۶ مهر؛ شاهد: اسکرین‌شات FX.' },
      { at: iso(60 * 93), kind: 'note', ref: null, summary_fa: 'قاعده: سیاست پیام‌رسانی حساب‌های تجاری پلتفرم (خوانده‌شده ۲۸ مهر)؛ پاسخ خودکار فقط داخل پنجره‌ی مجاز. برداشت من، نه نقل: ربات ما بیرون از پنجره جواب داده.' },
      { at: iso(60 * 84), kind: 'form', ref: null, summary_fa: 'فرم بازبینی داخل اپ را مالک با ورود خود حساب فرستاد؛ مقدار فیلدها از کارت مشاور.' },
      { at: iso(60 * 72), kind: 'email_out', ref: 'D-000083', summary_fa: 'ایمیل اول به پشتیبانی تجاری با مُهر مالک فرستاده شد.' },
      { at: iso(60 * 50), kind: 'email_in', ref: null, summary_fa: 'جواب خودکار: پرونده‌ی `4471-DEMO` ثبت شد؛ بررسی تا ۵ روز کاری.' },
      { at: iso(60 * 24), kind: 'note', ref: 'W-000151', summary_fa: 'علت پیدا شد و به مدیرعامل FX رفت: ربات پاسخ خودکار بیرون از پنجره‌ی مجاز جواب میداد؛ اصلاح شد (W-000151).' },
      { at: iso(180), kind: 'email_out', ref: 'D-000085', summary_fa: 'پیش‌نویس ایمیل دوم، با شرح اصلاح، منتظر مُهر تو.' },
    ],
    deadlines: [{ at: ahead(60 * 46), what_fa: 'پایان ۵ روز کاری بررسی، طبق جواب خودکار' }, { at: ahead(60 * 70), what_fa: 'پایان محدودیت ۷ روزه‌ی اعلان، اگر زودتر برداشته نشود' }] },
  { ref: 'LC-0002', company: 'TY', title_fa: 'بازبینی قرارداد همکاری صرافی', kind: 'contract_review', counterpart: { name: 'شریک صرافی تریدیار', channel: 'email', address: 'partners@exchange-partner.example' },
    status: 'open', opened_by: ceo('TY'), created_at: iso(60 * 20), brief_md: 'پیش‌نویس قرارداد تمدید همکاری؛ بند انحصار و بند فسخ را ببین.',
    timeline: [
      { at: iso(60 * 20), kind: 'note', ref: 'W-000149', summary_fa: 'از کار مدیرعامل تریدیار (W-000149) باز شد؛ پیش‌نویس قرارداد پیوست است.' },
      { at: iso(60 * 6), kind: 'note', ref: null, summary_fa: 'جدول بندها نوشته شد: بند انحصار ۲ ساله و فسخ یک‌طرفه‌ی ۳۰ روزه ریسک دارند؛ دو پرسش برای شریک پیشنهاد شد. هیچ چیز پذیرفته یا امضا نشده.' },
    ],
    deadlines: [{ at: ahead(60 * 24 * 3), what_fa: 'پاسخ به پیش‌نویس، طبق ایمیل شریک' }] },
  { ref: 'LC-0003', company: 'PC', title_fa: 'برداشتن پست کپی‌شده در کانالی دیگر', kind: 'takedown', counterpart: { name: 'میزبان کانال', channel: 'email', address: 'abuse@channel-host.example' },
    status: 'resolved', opened_by: ceo('PC'), created_at: iso(60 * 24 * 10), brief_md: 'پست ما بی‌اجازه کامل در کانال دیگری بازنشر شده.',
    timeline: [
      { at: iso(60 * 24 * 10), kind: 'note', ref: null, summary_fa: 'باز شد از کار مدیرعامل پرو-چارت.' },
      { at: iso(60 * 24 * 9), kind: 'email_out', ref: null, summary_fa: 'درخواست حذف طبق سیاست کپی‌رایت منتشرشده‌ی میزبان، با مُهر مالک.' },
      { at: iso(60 * 24 * 7), kind: 'email_in', ref: null, summary_fa: 'میزبان: محتوا حذف شد.' },
      { at: iso(60 * 24 * 7 - 30), kind: 'decision', ref: null, summary_fa: 'حل شد؛ بسته شدن با مالک.' },
    ],
    deadlines: [] },
].map((c, i) => ({ id: `lc${i + 1}`, version: 1, updated_at: c.timeline.at(-1)?.at ?? c.created_at, ...c }));
const caseOut = (c: any, full = false) => ({ ...c, emails: full ? emails.filter((e) => e.case === c.ref).sort((a, b) => a.at.localeCompare(b.at)) : undefined });

// ========================================================================== decision cards (§22.6) ==
const card = (d: Record<string, unknown>) => ({
  reversible: true, status: 'pending', seal: null, decided_at: null, decided_by: null, note: null, resolution: null, thread: null,
  version: 1, effect_status: 'none', work_id: null, reason_code: null, quota_estimate: { tokens: 0, usd: '0.00' }, expected: null, warnings: [], expires_at: null, ...d,
});
const sealed = (min: number) => ({ status: 'approved', seal: { method: 'passkey_uv', sealed_at: iso(min), step_up_id: 'demo' }, decided_at: iso(min), decided_by: owner, effect_status: 'applied' });
const emailPayload = (e: any) => ({ case: e.case, from: e.from, to: e.to, cc: e.cc, subject: e.subject, body_md: e.body_md, attachments: e.attachments, lang: e.lang, digest: e.digest });
/** Two new pending cards (a Telegram channel story with its file, and the counsel's second email), and the sealed history. */
export const DECISIONS_19: any[] = [
  card({ id: 'd85', ref: 'D-000085', kind: 'email_send', company: 'FX', action_class: 'A3', risk: 'medium', reversible: false, title: 'ایمیل دوم به پشتیبانی تجاری اینستاگرام', proposer: counsel, thread: 'L',
    created_at: iso(180), what: 'ایمیل دوم پرونده‌ی **LC-0001** به پشتیبانی تجاری، به انگلیسی: علت محدودیت را که سمت ما بود و اصلاحش را میگوید و بازبینی میخواهد.',
    why: 'جواب خودکار پرونده‌ی `4471-DEMO` بررسی تا ۵ روز کاری را گفته؛ با اصلاح ربات (W-000151) دلیل تازه‌ای برای بازبینی داریم. هیچ تهدیدی و هیچ ادعای بی‌منبعی نیست.',
    risk_note: 'فرستادن ایمیل برگشت‌پذیر نیست. با مُهر فقط همین متن، همین گیرنده و همین پیوست یک بار فرستاده میشود؛ هر تغییر کارت تازه میخواهد.', payload: {} }),
  card({ id: 'd86p', ref: 'D-000087', kind: 'media_publish', company: 'TY', action_class: 'A3', risk: 'low', title: 'استوری کانال تلگرام تریدیار: حد ضرر', proposer: mediaMgr('TY'),
    created_at: iso(50), expires_at: ahead(60 * 3), what: 'استوری **MI-0013** از برنامه‌ی **SR-0003** همه‌ی چک‌ها را رد کرده، ولی استوری کانال تلگرام در Bot API نیست: فایل را بردار و خودت در کانال بگذار.',
    why: 'برنامه‌ی SR-0003 مُهرشده و خودکار است؛ فقط همین جای انتشار راه رسمی ندارد. اینستاگرام تریدیار هم هنوز کلید ندارد و این بار منتشر نمیشود.',
    risk_note: null, quota_estimate: { tokens: 0, usd: '0.00' },
    payload: { item: 'MI-0013', series: 'SR-0003', kind: 'story', title_fa: 'یک مفهوم: حد ضرر', why: 'no_api',
      placements: [{ channel: 'telegram', placement: 'telegram_story', account: 'telegram-ty', via: 'manual', blocked: null }, { channel: 'instagram', placement: 'instagram_story', account: 'instagram-ty', via: 'api', blocked: 'account_not_configured' }],
      render: VIDEO.stoploss, checks: passAll() } }),
  card({ id: 'd81', ref: 'D-000081', kind: 'media_series', company: 'FX', action_class: 'A3', risk: 'medium', title: 'برنامه‌ی انتشار «سطح‌های هفته‌ی طلا»', proposer: mediaMgr('FX'),
    created_at: iso(60 * 24 * 6 + 120), ...sealed(60 * 24 * 6), resolution: 'M-0031',
    what: 'ریلز هفتگی سطح‌های طلا، شنبه و سه‌شنبه ساعت 18:30، روی ریلز اینستاگرام و کانال تلگرام FX؛ انتشار خودکار وقتی هر هفت چک قبول باشد.',
    why: 'سه قسمت آزمایشی با کارت منتشر شد و هر سه بازبینی قبول گرفتند؛ هزینه‌ی هر قسمت حدود 170K توکن.',
    payload: { series: 'SR-0001', version: 1, digest: '', title_fa: 'سطح‌های هفته‌ی طلا', kind: 'reel', schedule: 'FREQ=WEEKLY;BYDAY=SA,TU;BYHOUR=18;BYMINUTE=30', auto_publish: true, max_per_day: 2,
      targets: [{ channel: 'instagram', account: 'instagram-fx', placement: 'instagram_reel' }, { channel: 'telegram', account: 'telegram-fx', placement: 'telegram_post' }] } }),
  card({ id: 'd84', ref: 'D-000084', kind: 'role_new', company: 'FX', action_class: 'A2', risk: 'low', title: 'نقش تازه در کوینه‌پرو FX: تدوینگر پادکست', proposer: mediaMgr('FX'),
    created_at: iso(60 * 22), ...sealed(60 * 20), resolution: 'M-0034',
    what: 'منشور **تدوینگر پادکست** (`podcast_editor`) در دپارتمان رسانه‌ی FX، نوشته‌ی مدیر رسانه به درخواست تو.', why: 'هیچ منشور موجودی نسخه‌ی صوتی بلند با فصل‌بندی را نمیپوشاند؛ بازبینی ناظر قبول و آزمون خودش 88.',
    payload: { draft: 'RD-0001', company: 'FX', department: 'MEDIA', role: 'podcast_editor', title_fa: 'تدوینگر پادکست', model: 'claude-sonnet-5-5', effort: 'medium', limits: LIM(5, 30000, 120000), tools_count: 13, review: 'pass', eval_score: 88, sha256: '6f1c0b9e5a7d24e83c9f0a1b2d3e4f5061728394a5b6c7d8e9f0a1b2c3d4e5f6' } }),
  card({ id: 'd83', ref: 'D-000083', kind: 'email_send', company: 'FX', action_class: 'A3', risk: 'medium', reversible: false, title: 'ایمیل اول به پشتیبانی تجاری اینستاگرام', proposer: counsel, thread: 'L',
    created_at: iso(60 * 74), ...sealed(60 * 72), resolution: 'M-0032', what: 'ایمیل اول پرونده‌ی **LC-0001**.', why: 'فرم داخل اپ فرستاده شد؛ ایمیل، شماره‌ی پرونده و قاعده را میخواهد.', risk_note: null, payload: {} }),
  card({ id: 'd86', ref: 'D-000086', kind: 'media_publish', company: 'PC', action_class: 'A3', risk: 'low', title: 'پست کانال تلگرام پرو-چارت: نسخه‌ی تازه‌ی ترمینال', proposer: mediaMgr('PC'),
    created_at: iso(60 * 24 * 5 + 60), ...sealed(60 * 24 * 5), resolution: 'M-0030', what: 'پست یک‌باره‌ی **MI-0010** در کانال تلگرام پرو-چارت.', why: 'یک‌باره است؛ یک‌باره‌ها همیشه کارت‌اند.',
    payload: { item: 'MI-0010', series: null, kind: 'post', title_fa: 'نسخه‌ی تازه‌ی ترمینال', why: 'one_off', placements: [{ channel: 'telegram', placement: 'telegram_post', account: 'telegram-pc', via: 'api', blocked: null }], render: null, checks: passAll() } }),
];

// ======================================================================== decorate and decide ==
type Ctx = { decisions: any[]; messages: Record<string, any[]>; employees: any[]; threads: any[]; stories: any[] };
let ctx: Ctx | null = null;
const L_MESSAGES = [
  { ref: 'L-0001', author: owner, kind: 'voice_transcript', min: 60 * 96, body: 'اینستاگرام جواب دایرکت صفحه‌ی FX رو محدود کرده. برو ببین چرا، راه‌ها رو پیدا کن و اگه لازمه ایمیل بزن.', links: {} },
  { ref: 'L-0002', author: counsel, min: 60 * 95, links: { case: 'LC-0001' },
    body: 'پرونده‌ی **LC-0001** باز شد.\n\n### خلاصه\nپاسخ به دایرکت حساب تجاری FX از ۲۶ مهر محدود است؛ از تو ورود به حساب برای فرم داخل اپ را لازم دارم.\n\n### راه‌ها\n1. فرم بازبینی داخل اپ؛ با ورود خود تو، کم‌هزینه و برگشت‌پذیر.\n2. ایمیل به پشتیبانی تجاری؛ هر ایمیل کارت مُهر توست.\n3. بررسی ربات پاسخ خودکار FX؛ اگر بیرون از پنجره‌ی مجاز جواب داده، اصلاح با مدیرعامل FX.\n\n### پیشنهاد\nاول ۱ و ۳، بعد ۲ با شماره‌ی پرونده. وکیل انسانی لازم نیست.' },
  { ref: 'L-0003', author: counsel, min: 60 * 24, links: { case: 'LC-0001', work: 'W-000151' }, body: 'علت پیدا شد: ربات پاسخ خودکار FX بعضی پیام‌ها را بیرون از پنجره‌ی مجاز جواب میداد. مدیرعامل FX اصلاحش کرد (W-000151).' },
  { ref: 'L-0004', author: counsel, min: 180, links: { case: 'LC-0001', decision: 'D-000085' }, body: 'پیش‌نویس ایمیل دوم آماده است؛ متن دقیق در کارت **D-000085**. با مُهر تو فقط همین یک بار، دقیقاً همین متن فرستاده میشود.' },
];
/** Called once by mock.ts after its lists exist: §22 adds the MEDIA teams, HQ-LGL, thread L, the cards' payloads and the role story. */
export function decorate19(c: Ctx): void {
  ctx = c;
  const base = c.employees.find((e) => e.kind === 'employee') ?? {};
  const mgrBase = c.employees.find((e) => e.kind === 'manager') ?? base;
  const add = (e: any) => { if (!c.employees.some((x) => x.code === e.code)) c.employees.push(e); };
  for (const co of ['TY', 'FX', 'PC']) {
    add({ ...mgrBase, id: `e-${co}-MEDIA-MGR`, code: `${co}-MEDIA-MGR`, company: co, kind: 'manager', department: 'MEDIA', title_fa: 'مدیر رسانه و طراحی', title_en: 'Head of Media and Design', activity: co === 'FX' ? 'working' : 'sleeping', activity_note: co === 'FX' ? 'بازبینی MI-0019' : null, hired_at: iso(60 * 24 * 9), model: { connection: 'claude-max', model: 'claude-sonnet-5-5', effort: 'high' }, score: { value: null, owner_avg: null, rank_in_department: null, trend: [] } });
  }
  for (const [code, co, , title_fa, title_en, model] of TEAM) {
    const working = ['FX-MEDIA-03', 'TY-MEDIA-03', 'PC-MEDIA-02', 'PC-MEDIA-03'].includes(code);
    add({ ...base, id: `e-${code}`, code, company: co, kind: 'employee', department: 'MEDIA', title_fa, title_en, activity: working ? 'working' : 'idle', activity_note: working ? 'روی آیتم رسانه' : null, hired_at: iso(60 * 24 * 7), probation_until: null, model: { connection: 'claude-max', model, effort: model.includes('opus') ? 'high' : 'medium' }, score: { value: null, owner_avg: null, rank_in_department: null, trend: [] } });
  }
  add({ ...base, id: 'e-HQ-LGL', code: 'HQ-LGL', company: 'HQ', kind: 'employee', department: 'LEGAL', title_fa: 'مشاور حقوقی', title_en: 'Legal Counsel', activity: 'sleeping', activity_note: null, hired_at: iso(60 * 24 * 5), probation_until: null, model: { connection: 'claude-max', model: 'claude-sonnet-5-5', effort: 'high' }, score: { value: null, owner_avg: null, rank_in_department: null, trend: [] } });
  if (!c.threads.some((t) => t.code === 'L')) c.threads.push({ id: 't-L', code: 'L', kind: 'legal', company: 'HQ', title_fa: 'مشاور حقوقی', unread: 1, last_message_at: iso(180), last_ref: 'L-0004', participants: [owner, counsel] });
  const l = (c.messages.L ??= []);
  for (const m of L_MESSAGES) if (!l.some((x) => x.ref === m.ref)) l.push({ id: `m19-${m.ref}`, ref: m.ref, thread: 'L', author: m.author, body: m.body, kind: m.kind ?? 'text', attachments: [], links: m.links, created_at: iso(m.min) });
  for (const d of DECISIONS_19) if (!c.decisions.some((x) => x.ref === d.ref)) c.decisions.push(d);
  if (!c.stories.some((s) => s.links?.role_draft === 'RD-0001')) {
    c.stories.push({ id: 'st-rd1', ref: `ST-${pad(c.stories.length + 101, 6)}`, company: 'FX', kind: 'role', author: { kind: 'system', code: 'system', display_fa: 'سیستم' }, title_fa: 'نقش تازه در کوینه‌پرو FX: تدوینگر پادکست',
      body_fa: 'مدیر رسانه به درخواست تو این نقش را نوشت؛ ناظر کل بازبینی کرد و آزمون خودش را با نمره‌ی 88 گذراند. هنوز کسی روی آن استخدام نشده.',
      figures: [{ label_fa: 'مدل', value: 'Sonnet 5.5' }, { label_fa: 'آزمون', value: '88' }, { label_fa: 'ابزار', value: '13' }], links: { role_draft: 'RD-0001', decision: 'D-000084' },
      media: null, created_at: iso(60 * 20), expires_at: iso(60 * 20 - 60 * 24), seen: false, welcomed: false });
  }
}
async function cardsReady() {
  await Promise.all([seriesReady, emailsReady]);
  for (const d of DECISIONS_19) {
    if (d.kind === 'email_send' && !d.payload.digest) { const e = emails.find((x) => x.decision_ref === d.ref); if (e) d.payload = emailPayload(e); }
    if (d.kind === 'media_series' && !d.payload.digest) d.payload.digest = series.find((s) => s.ref === d.payload.series)?.digest ?? '';
  }
}
const ready = cardsReady();

function publishNow(x: any) {
  const t = stamp();
  x.publish = x.publish.map((r: any) => {
    if (r.placement === 'telegram_story') return { ...r, at: t, external_id: 'manual', error: null }; // posted by the owner from the card
    if (r.error === 'account_not_configured') return r;
    return { ...r, at: t, external_id: String(18_000 + seedOf(x.ref + r.placement)), url: r.channel === 'telegram' ? `https://t.me/demo_${x.company.toLowerCase()}/${seedOf(x.ref)}` : null, error: null };
  });
  Object.assign(x, { state: 'published', updated_at: t, version: x.version + 1, state_note_fa: x.publish.some((r: any) => r.error) ? 'آنچه راه رسمی داشت منتشر شد؛ جای بی‌کلید منتشر نشد.' : null });
}
/** What deciding a §22 card does in the demo (mock.ts calls it for approve, reject and return). */
export function decided19(d: any): void {
  if (d.kind === 'media_publish') {
    const x = items.find((i) => i.ref === d.payload?.item);
    if (!x) return;
    if (d.status === 'approved') publishNow(x);
    else Object.assign(x, { state: 'rejected', updated_at: stamp(), version: x.version + 1, state_note_fa: d.status === 'returned' ? `مالک برگرداند: «${d.note ?? ''}»` : 'مالک رد کرد.' });
  }
  if (d.kind === 'email_send') {
    const e = emails.find((y) => y.decision_ref === d.ref);
    const c = cases.find((y) => y.ref === e?.case);
    if (!e || !c) return;
    if (d.status === 'approved') {
      Object.assign(e, { state: 'sent', at: stamp(), message_id: `<${c.ref.toLowerCase()}.${emails.filter((y) => y.case === c.ref && y.direction === 'out').length}@coinepro.com>` });
      c.timeline.push({ at: stamp(), kind: 'email_out', ref: d.ref, summary_fa: 'با مُهر مالک فرستاده شد؛ دقیقاً همان پیام، یک بار.' });
      Object.assign(c, { status: 'waiting_reply', updated_at: stamp(), version: c.version + 1 });
    } else {
      e.state = 'rejected';
      c.timeline.push({ at: stamp(), kind: 'decision', ref: d.ref, summary_fa: d.status === 'returned' ? `مالک برگرداند: «${d.note ?? ''}»؛ مشاور پیش‌نویس تازه مینویسد.` : 'مالک ایمیل را رد کرد؛ فرستاده نشد.' });
      Object.assign(c, { status: 'open', updated_at: stamp(), version: c.version + 1 });
    }
  }
  if (d.kind === 'role_new') {
    const r = roleDrafts.find((y) => y.ref === d.payload?.draft);
    if (r) Object.assign(r, d.status === 'approved' ? { state: 'active', activated_at: stamp(), approver: owner } : { state: 'rejected' });
  }
}

// ========================================================================== routes ==
/** The §22 routes; null when the path is not one of them. */
export async function handle19(req: Request, p: string, u: URL): Promise<Response | null> {
  const m = req.method;
  const q = (k: string) => u.searchParams.get(k);
  const body = async <B,>() => (await req.json().catch(() => ({}))) as B;
  await ready;
  if (m === 'GET') {
    if (p === '/roles') return json([...fileRoles.map((r) => ({ ...r, source: 'file' })), ...P13_ROLES, ...roleDrafts.filter((d) => d.state === 'active').map(asRole)]);
    if (p === '/roles/drafts') return json(page(roleDrafts.filter((d) => (!q('company') || d.company === q('company')) && (!q('department') || d.department === q('department')) && (!q('state') || d.state === q('state'))).sort((a, b) => b.created_at.localeCompare(a.created_at)).map(draftOut)));
    const rd = /^\/roles\/drafts\/(RD-\d+)$/.exec(p);
    if (rd) { const d = roleDrafts.find((x) => x.ref === rd[1]); return d ? json(draftOut(d)) : problem(404, 'not_found', 'این نقش پیدا نشد.'); }
    if (p === '/media/series') return json(page(series.filter((s) => (!q('company') || s.company === q('company')) && (!q('status') || s.status === q('status'))).map(seriesOut)));
    if (p === '/media/items') {
      painted ??= Promise.all(items.map(paintItem)).then(() => undefined);
      await painted;
      const xs = items.filter((x) => (!q('company') || x.company === q('company')) && (!q('series') || x.series === q('series')) && (!q('state') || x.state === q('state')));
      return json(page(xs.sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map(itemOut)));
    }
    const mi = /^\/media\/items\/(MI-\d+)$/.exec(p);
    if (mi) { const x = items.find((y) => y.ref === mi[1]); if (!x) return problem(404, 'not_found', 'این آیتم پیدا نشد.'); await paintItem(x); return json(itemOut(x)); }
    if (p === '/media/voices') return json(voices);
    if (p === '/media/voices/reference') {
      if (reference?.state === 'processing' && Date.now() - Date.parse(reference.created_at) > 4_000) reference.state = 'ready';
      return reference ? json(reference) : problem(404, 'not_found', 'هنوز نمونه‌ی صدای تو ضبط نشده.');
    }
    if (p === '/media/limits') return json(limits());
    if (p === '/legal/cases') return json(page(cases.filter((c) => (!q('company') || c.company === q('company')) && (!q('status') || c.status === q('status'))).sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map((c) => caseOut(c))));
    const lc = /^\/legal\/cases\/(LC-\d+)$/.exec(p);
    if (lc) { const c = cases.find((x) => x.ref === lc[1]); return c ? json(caseOut(c, true)) : problem(404, 'not_found', 'این پرونده پیدا نشد.'); }
    return null;
  }

  // ------------------------------------------------------------------ writes --
  // A media_series card is sealed only on its own route, on the series digest (like a server plan, §18.8).
  const ap = /^\/decisions\/(D-\d+)\/approve$/.exec(p);
  if (ap && ctx?.decisions.find((d) => d.ref === ap[1])?.kind === 'media_series') return problem(409, 'validation_failed', 'این کارت روی صفحه‌ی برنامه‌های انتشار، روی digest همان برنامه مُهر میشود.');

  // ---- §22.1 mandate
  const md = /^\/companies\/([A-Z0-9]+)\/departments\/([A-Z]+)\/mandate$/.exec(p);
  if (md && m === 'PUT') {
    const deny = needsStepUp(req);
    if (deny) return deny;
    const key = `${md[1]}:${md[2]}`;
    const cur = mandates.get(key);
    const bad = unmatched(req, cur?.version ?? 1);
    if (bad) return bad;
    const b = await body<{ mandate?: Mandate; identity_md?: string }>();
    const x = b.mandate;
    if (!x || !x.from_fa?.trim() || !x.to_fa?.trim()) return problem(422, 'validation_failed', 'مبدأ و مقصد لازم است.', { fields: { mandate: 'from_fa, to_fa' } });
    if (!x.outputs_fa?.filter((s) => s.trim()).length) return problem(422, 'validation_failed', 'دست‌کم یک خروجی لازم است.', { fields: { outputs_fa: 'required' } });
    if (!['claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5'].includes(x.model_ceiling)) return problem(422, 'validation_failed', 'سقف مدل نامعتبر است.', { fields: { model_ceiling: 'enum' } });
    mandates.set(key, { mandate: { ...x, outputs_fa: x.outputs_fa.filter((s) => s.trim()), boundaries_fa: (x.boundaries_fa ?? []).filter((s) => s.trim()) }, identity_md: (b.identity_md ?? '').trim(), version: (cur?.version ?? 1) + 1 });
    return json({ code: md[2], company: md[1], ...mandates.get(key) });
  }

  // ---- §22.5 roles
  if (p === '/roles/drafts' && m === 'POST') {
    const { k, hit } = once(req);
    if (hit) return json(hit.body, hit.status);
    const b = await body<{ company?: string; department?: string; brief_md?: string }>();
    if (!b.company || !b.department || !b.brief_md?.trim()) return problem(422, 'validation_failed', 'شرکت، دپارتمان و شرح نقش لازم است.', { fields: { brief_md: 'required' } });
    const n = roleDrafts.length + 1;
    const mgr = b.company === 'HQ' ? owner : agent(`${b.company}-${b.department}-MGR`, `مدیر ${b.department} ${NAME[b.company] ?? b.company}`);
    const d = { id: `rd${n}`, ref: `RD-${pad(n, 4)}`, company: b.company, department: b.department, role: '', title_fa: b.brief_md.trim().slice(0, 40), title_en: '', why_md: '', charter_md: '', tools: [], model: '', effort: '', limits: LIM(0, 0, 0),
      eval: { suite: '', cases: [] }, state: 'drafting', review: null, eval_run: null, approver: null, decision_ref: null, version: 1, created_at: stamp(), activated_at: null,
      brief_md: b.brief_md.trim(), requested_by: owner, written_by: mgr, compared: [], originality: null, hires: 0, retired_at: null };
    roleDrafts.unshift(d);
    remember(k, 201, d);
    return json(d, 201);
  }
  const rr = /^\/roles\/drafts\/(RD-\d+)\/retire$/.exec(p);
  if (rr && m === 'POST') {
    const d = roleDrafts.find((x) => x.ref === rr[1]);
    if (!d) return problem(404, 'not_found', 'این نقش پیدا نشد.');
    if (d.state !== 'active') return problem(409, 'validation_failed', 'فقط نقش فعال بازنشسته میشود.');
    Object.assign(d, { state: 'retired', retired_at: stamp(), version: d.version + 1 });
    return json(d);
  }

  // ---- §22.2 series
  if (p === '/media/series' && m === 'POST') {
    const { k, hit } = once(req);
    if (hit) return json(hit.body, hit.status);
    const b = await body<any>();
    const bad = validateSeries(b);
    if (bad) return bad;
    const n = series.length + 1;
    const s = { id: `sr${n}`, ref: `SR-${pad(n, 4)}`, ...seriesBody(b), checks: ALL_CHECKS, status: 'draft', sealed_at: null, version: 1, digest: '', proposed_by: owner, decision_ref: null, items_total: 0, created_at: stamp(), updated_at: stamp(), status_note_fa: null };
    await digest(s);
    series.push(s);
    remember(k, 201, seriesOut(s));
    return json(seriesOut(s), 201);
  }
  const sw = /^\/media\/series\/(SR-\d+)(?:\/(seal|pause|retire))?$/.exec(p);
  if (sw) {
    const s = series.find((x) => x.ref === sw[1]);
    if (!s) return problem(404, 'not_found', 'این برنامه پیدا نشد.');
    if (!sw[2] && m === 'PUT') {
      const bad = unmatched(req, s.version);
      if (bad) return bad;
      const b = await body<any>();
      const invalid = validateSeries({ ...b, company: s.company });
      if (invalid) return invalid;
      if (s.status === 'retired') return problem(409, 'validation_failed', 'برنامه‌ی بازنشسته ویرایش نمیشود.');
      const wasSealed = s.status === 'sealed' || s.status === 'paused';
      Object.assign(s, { ...seriesBody({ ...b, company: s.company }), checks: ALL_CHECKS, version: s.version + 1, updated_at: stamp() });
      if (wasSealed) Object.assign(s, { status: 'proposed', sealed_at: null, status_note_fa: 'ویرایش شد؛ مُهر قبلی این نسخه را نمیپوشاند و تا مُهر دوباره چیزی خودکار منتشر نمیشود.' });
      await digest(s);
      return json(seriesOut(s));
    }
    if (sw[2] === 'seal') {
      const deny = needsStepUp(req);
      if (deny) return deny;
      const b = await body<{ digest?: string }>();
      if (b.digest && b.digest !== s.digest) return problem(409, 'version_conflict', 'برنامه بعد از دیدن تو عوض شده؛ دوباره نگاه کن و مُهر کن.');
      if (!['draft', 'proposed', 'paused'].includes(s.status)) return problem(409, 'validation_failed', s.status === 'sealed' ? 'همین نسخه مُهر شده است.' : 'برنامه‌ی بازنشسته مُهر نمیشود.');
      const unconfigured = s.targets.filter((t: any) => !ACCOUNT_OK[t.account]).map((t: any) => t.account);
      Object.assign(s, { status: 'sealed', sealed_at: stamp(), version: s.version + 1, updated_at: stamp(), status_note_fa: unconfigured.length ? `مُهر شد؛ ${unconfigured.join('، ')} هنوز کلید ندارد و تا ورودش روی آن منتشر نمیشود.` : null });
      for (const d of ctx?.decisions ?? []) if (d.kind === 'media_series' && d.status === 'pending' && d.payload?.series === s.ref) Object.assign(d, sealed(0), { resolution: 'M-0040' });
      return json(seriesOut(s));
    }
    if (sw[2] === 'pause') {
      if (s.status !== 'sealed') return problem(409, 'validation_failed', 'فقط برنامه‌ی مُهرشده متوقف میشود.');
      Object.assign(s, { status: 'paused', version: s.version + 1, updated_at: stamp(), status_note_fa: 'مالک متوقف کرد؛ با مُهر دوباره ادامه میدهد.' });
      return json(seriesOut(s));
    }
    if (sw[2] === 'retire') {
      if (s.status === 'retired') return problem(409, 'validation_failed', 'همین حالا بازنشسته است.');
      Object.assign(s, { status: 'retired', version: s.version + 1, updated_at: stamp(), status_note_fa: null });
      return json(seriesOut(s));
    }
  }

  // ---- §22.2 items
  if (p === '/media/items' && m === 'POST') {
    const { k, hit } = once(req);
    if (hit) return json(hit.body, hit.status);
    const b = await body<{ company?: string; kind?: string; brief_md?: string; series?: string }>();
    if (!b.company || b.company === 'HQ' || !['reel', 'story', 'post', 'carousel', 'design'].includes(b.kind ?? '') || (b.brief_md ?? '').trim().length < 8) return problem(422, 'validation_failed', 'شرکت، نوع و brief (دست‌کم ۸ نویسه) لازم است.', { fields: { brief_md: 'required' } });
    const n = Math.max(...items.map((x) => Number(x.ref.slice(3)))) + 1;
    const x = item({ id: `mi${n}`, ref: `MI-${pad(n, 4)}`, company: b.company, series: b.series ?? null, kind: b.kind, title_fa: b.brief_md!.trim().slice(0, 48), state: 'scripting', brief_md: b.brief_md!.trim(), created_at: stamp(), updated_at: stamp(),
      state_note_fa: b.kind === 'design' ? 'طراح رابط brief و ترکیب‌بندی را مینویسد؛ طراحی منتشر نمیشود و به مدیر فنی میرسد.' : 'یک‌باره است: آخرش همیشه کارت انتشار برای توست.' });
    items.unshift(x);
    remember(k, 201, itemOut(x));
    return json(itemOut(x), 201);
  }
  const iw = /^\/media\/items\/(MI-\d+)\/(publish|unpublish)$/.exec(p);
  if (iw && m === 'POST') {
    const x = items.find((y) => y.ref === iw[1]);
    if (!x) return problem(404, 'not_found', 'این آیتم پیدا نشد.');
    if (x.state === 'held') return problem(423, 'held', 'ناظر کل این آیتم را نگه داشته.');
    if (iw[2] === 'publish') {
      if (x.state !== 'waiting_owner') return problem(409, 'validation_failed', 'فقط آیتم منتظر تو منتشر میشود.');
      const d = ctx?.decisions.find((y) => y.ref === x.decision_ref && y.status === 'pending');
      if (d) Object.assign(d, sealed(0), { resolution: 'M-0041' });
      publishNow(x);
      return json(itemOut(x));
    }
    const deny = needsStepUp(req);
    if (deny) return deny;
    if (x.state !== 'published') return problem(409, 'validation_failed', 'فقط آیتم منتشرشده پایین میآید.');
    x.publish = x.publish.map((r: any) => (r.channel === 'telegram' && r.placement !== 'telegram_story' ? { ...r, url: null, error: 'removed' } : { ...r, error: 'remove_by_hand' }));
    Object.assign(x, { state: 'rejected', updated_at: stamp(), version: x.version + 1, state_note_fa: x.publish.some((r: any) => r.error === 'remove_by_hand') ? 'مالک پایین آورد؛ جایی که API اجازه‌ی حذف نداد را از خود اپ پایین بیاور.' : 'مالک پایین آورد.' });
    return json(itemOut(x));
  }

  // ---- §22.3 voices
  const vs = /^\/media\/voices\/([\w-]+)\/(score|activate)$/.exec(p);
  if (vs && m === 'POST') {
    const v = voices.find((x) => x.id === vs[1]);
    if (!v) return problem(404, 'not_found', 'این صدا پیدا نشد.');
    if (vs[2] === 'score') {
      const b = await body<{ score?: number }>();
      if (!Number.isInteger(b.score) || b.score! < 1 || b.score! > 10) return problem(422, 'validation_failed', 'نمره از ۱ تا ۱۰ است.', { fields: { score: '1..10' } });
      if (!v.samples.length) return problem(409, 'not_ready', 'این صدا هنوز نمونه ندارد.');
      Object.assign(v, { owner_score: b.score, version: v.version + 1 });
      return json(v);
    }
    const deny = needsStepUp(req);
    if (deny) return deny;
    if (!v.samples.length) return problem(409, 'not_ready', 'این صدا هنوز اندازه‌گیری نشده؛ فعال نمیشود.');
    const b = await body<{ accept_non_commercial?: boolean }>();
    if (!v.licence_commercial && !b.accept_non_commercial) return problem(422, 'validation_failed', 'لایسنس این صدا غیرتجاری است؛ فعال شدنش انتخاب صریح تو را میخواهد.', { fields: { accept_non_commercial: 'required' } });
    for (const x of voices) if (x.status === 'active') x.status = 'candidate';
    Object.assign(v, { status: 'active', version: v.version + 1 });
    return json(v);
  }
  if (p === '/media/voices/reference' && m === 'POST') {
    const b = await body<{ file_id?: string }>();
    if (!b.file_id) return problem(422, 'validation_failed', 'فایل نمونه لازم است.', { fields: { file_id: 'required' } });
    reference = { file: f(b.file_id, 'owner-reference.webm', 'audio/webm', 0), duration_s: 0, created_at: stamp(), state: 'processing', reason_fa: null };
    return json(reference, 201);
  }

  // ---- §22.4 legal
  if (p === '/legal/cases' && m === 'POST') {
    const { k, hit } = once(req);
    if (hit) return json(hit.body, hit.status);
    const b = await body<{ company?: string; title_fa?: string; kind?: string; brief_md?: string }>();
    if (!b.company || !b.title_fa?.trim() || !b.kind || !b.brief_md?.trim()) return problem(422, 'validation_failed', 'شرکت، عنوان، نوع و شرح لازم است.', { fields: { brief_md: 'required' } });
    const n = cases.length + 1;
    const c = { id: `lc${n}`, ref: `LC-${pad(n, 4)}`, company: b.company, title_fa: b.title_fa.trim(), kind: b.kind, counterpart: { name: '—', channel: 'other', address: null }, status: 'open', opened_by: owner,
      brief_md: b.brief_md.trim(), created_at: stamp(), updated_at: stamp(), version: 1, deadlines: [], timeline: [{ at: stamp(), kind: 'note', ref: null, summary_fa: 'پرونده باز شد؛ مشاور حقوقی بیدار شد و اول واقعیت‌ها را جمع میکند.' }] };
    cases.unshift(c);
    const l = ctx?.messages.L;
    if (l) l.push({ id: `m19-${c.ref}`, ref: `L-${pad(l.length + 1, 4)}`, thread: 'L', author: counsel, body: `پرونده‌ی **${c.ref}** باز شد. اول واقعیت‌ها و قاعده‌ی خود طرف مقابل را پیدا میکنم؛ هر ایمیل یا فرم، کارت مُهر توست.`, kind: 'text', attachments: [], links: { case: c.ref }, created_at: stamp() });
    remember(k, 201, caseOut(c));
    return json(caseOut(c), 201);
  }
  const cc = /^\/legal\/cases\/(LC-\d+)\/close$/.exec(p);
  if (cc && m === 'POST') {
    const c = cases.find((x) => x.ref === cc[1]);
    if (!c) return problem(404, 'not_found', 'این پرونده پیدا نشد.');
    if (c.status === 'closed') return problem(409, 'validation_failed', 'همین حالا بسته است.');
    if (emails.some((e) => e.case === c.ref && e.state === 'waiting_seal')) return problem(409, 'validation_failed', 'ایمیلی منتظر مُهر توست؛ اول آن را مُهر یا رد کن.');
    c.timeline.push({ at: stamp(), kind: 'decision', ref: null, summary_fa: 'مالک پرونده را بست.' });
    Object.assign(c, { status: 'closed', updated_at: stamp(), version: c.version + 1 });
    return json(caseOut(c, true));
  }
  return null;
}

function validateSeries(b: any): Response | null {
  if (!b.title_fa?.trim()) return problem(422, 'validation_failed', 'عنوان لازم است.', { fields: { title_fa: 'required' } });
  if (!['reel', 'story', 'post', 'carousel'].includes(b.kind)) return problem(422, 'validation_failed', 'نوع نامعتبر است.', { fields: { kind: 'enum' } });
  if (!Array.isArray(b.targets) || !b.targets.length) return problem(422, 'validation_failed', 'دست‌کم یک جای انتشار لازم است.', { fields: { targets: 'required' } });
  for (const t of b.targets) { const why = placementProblem(b.kind, b.format?.aspect, t); if (why) return problem(422, 'validation_failed', why, { fields: { placement: t.placement } }); }
  if (!/^FREQ=(DAILY|WEEKLY)(;BYDAY=(SA|SU|MO|TU|WE|TH|FR)(,(SA|SU|MO|TU|WE|TH|FR))*)?;BYHOUR=\d{1,2};BYMINUTE=\d{1,2}$/.test(b.schedule ?? '')) return problem(422, 'validation_failed', 'زمان‌بندی (RRULE) نامعتبر است.', { fields: { schedule: 'rrule' } });
  if (!Number.isInteger(b.max_per_day) || b.max_per_day < 1 || b.max_per_day > 10) return problem(422, 'validation_failed', 'سقف روزانه بین ۱ و ۱۰ است.', { fields: { max_per_day: '1..10' } });
  if (b.format?.duration_s != null && (b.kind === 'reel' ? b.format.duration_s > 90 : b.format.duration_s > 60)) return problem(422, 'validation_failed', 'مدت بیشتر از سقف خود پلتفرم است.', { fields: { duration_s: 'platform' } });
  if (!b.topics || (!b.topics.pool?.length && !b.topics.rule_fa?.trim())) return problem(422, 'validation_failed', 'فهرست موضوع یا قاعده‌ی انتخاب موضوع لازم است.', { fields: { topics: 'required' } });
  return null;
}
