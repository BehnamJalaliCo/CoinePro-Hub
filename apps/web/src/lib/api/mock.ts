// Development-only fixtures (npm run dev:mock). Never bundled in production:
// the client imports this module only when NEXT_PUBLIC_HQ_MOCK=1.

import { DEMO_CHART, DEMO_SKETCH, DEMO_VOICE } from './mock-media';
import { handleOps } from './mock-ops';
import { handle14 } from './mock-v14';
import { roles } from './mock-roles';

const now = Date.now();
const iso = (minAgo: number) => new Date(now - minAgo * 60_000).toISOString();
const ahead = (min: number) => new Date(now + min * 60_000).toISOString();

const CO = [
  { code: 'HQ', kind: 'holding', name_fa: 'هلدینگ کوینه‌پرو', name_en: 'CoinePro HQ', color_index: null },
  { code: 'TY', kind: 'company', name_fa: 'تریدیار', name_en: 'TradeYar', color_index: 3 },
  { code: 'FX', kind: 'company', name_fa: 'کوینه‌پرو FX', name_en: 'CoinePro FX', color_index: 2 },
  { code: 'PC', kind: 'company', name_fa: 'پرو-چارت', name_en: 'Pro-Chart', color_index: 1 },
];
const companies = CO.map((c, i) => ({
  id: `co-${c.code}`, ...c, status: 'active', template: c.kind === 'holding' ? 'holding' : 'standard', kill_switch: 'released',
  deploy_freeze_until: c.code === 'FX' ? ahead(95) : null, version: 3, created_at: iso(60 * 24 * 3),
  counts: { decisions_pending: [0, 0, 0, 1][i] ?? 0, employees_active: [5, 9, 10, 9][i] ?? 0, work_open: [3, 7, 11, 4][i] ?? 0 },
}));

const actor = (code: string, display_fa: string, kind = 'agent') => ({ kind, code, display_fa });
const modelName = (id: string) => id.replace(/^claude-([a-z]+)-(\d+)-(\d+).*/, (_m, f: string, a: string, b: string) => `${f[0]!.toUpperCase()}${f.slice(1)} ${a}.${b}`);
const owner = { kind: 'owner', code: 'owner', display_fa: 'مدیر کل' };
const system = { kind: 'system', code: 'system', display_fa: 'سیستم' };

const decisions: any[] = [
  {
    ref: 'D-000014', kind: 'hire', company: 'TY', action_class: 'A1', risk: 'low', reversible: true, status: 'withdrawn',
    title: 'استخدام SRE تریدیار', proposer: actor('TY-TECH-MGR', 'مدیر فنی تریدیار'), created_at: iso(42),
    what: 'یک **مهندس پایداری (SRE)** برای پایش سلامت سایت و پنل کاربری تریدیار. فقط وقتی پایش‌های قاعده‌محور خطا پیدا کنند بیدار میشود.',
    why: 'در ۷ روز گذشته `user.tradeyar.trade-future.ir` دو بار بیش از ۵ دقیقه کند بود و کسی پیگیری نکرد (شاهد: I-0002، I-0005).',
    quota_estimate: { tokens: 420000, usd: '6.80' }, risk_note: 'فقط‌خواندنی؛ هیچ اقدام بیرونی ندارد.',
    payload: { department: 'TECH', title_fa: 'مهندس پایداری (SRE)', title_en: 'Site Reliability Engineer', role: 'sre', model: 'claude-haiku-5-5', effort: 'high', duties: ['بررسی هشدارهای سایت و پنل', 'خلاصه‌ی روزانه‌ی سلامت', 'پیشنهاد اصلاح آستانه‌ها'], permissions: ['health.sites', 'deliver', 'notify'], quota_estimate_month: 420000 },
    seal: null, decided_at: iso(20), decided_by: system, note: 'مالک: استخدام با شروع خود مالک', resolution: null, thread: 'TY-TECH-MGR', expires_at: ahead(60 * 46), version: 1, effect_status: 'none', work_id: null, id: 'd14', reason_code: null,
  },
  {
    ref: 'D-000015', kind: 'hire', company: 'FX', action_class: 'A1', risk: 'low', reversible: true, status: 'withdrawn',
    title: 'استخدام SRE کوینه‌پرو FX', proposer: actor('FX-TECH-MGR', 'مدیر فنی FX'), created_at: iso(38),
    what: 'یک SRE برای پایش `coineprofx.com` و `fx.trade-future.ir`، با خلاصه‌ی روزانه و تحلیل هشدارها.',
    why: 'سیگنال‌ها و ربات تلگرام به سلامت سرویس وابسته‌اند؛ امروز هیچ نقشی مسئول پایش نیست.',
    quota_estimate: { tokens: 380000, usd: '6.10' }, risk_note: null,
    payload: { department: 'TECH', title_fa: 'مهندس پایداری (SRE)', role: 'sre', model: 'claude-haiku-5-5', effort: 'high', duties: ['تحلیل هشدار', 'خلاصه‌ی روزانه'], permissions: ['health.sites', 'deliver', 'notify'], quota_estimate_month: 380000 },
    seal: null, decided_at: iso(20), decided_by: system, note: 'مالک: استخدام با شروع خود مالک', resolution: null, thread: 'FX-TECH-MGR', expires_at: ahead(60 * 47), version: 1, effect_status: 'none', work_id: null, id: 'd15', reason_code: null,
  },
  {
    ref: 'D-000016', kind: 'hire', company: 'HQ', action_class: 'A1', risk: 'medium', reversible: true, status: 'withdrawn',
    title: 'تیم نظارت: مسئول ایمنی هوش مصنوعی', proposer: actor('HQ-OVS-MGR', 'بازرس کل'), created_at: iso(33),
    what: 'مسئول ایمنی هوش مصنوعی برای بررسی اینکه ایجنت‌ها در محدوده‌ی اختیارشان میمانند.',
    why: 'با شروع کار ایجنت‌ها، یک نقش مستقل باید audit و پیشنهادهای A3 را مرور کند.',
    quota_estimate: { tokens: 900000, usd: '14.20' }, risk_note: 'دسترسی به audit (فقط متادیتا).',
    payload: { department: 'OVS', title_fa: 'مسئول ایمنی هوش مصنوعی', role: 'ai_safety', model: 'claude-sonnet-5-5', effort: 'high', duties: ['مرور audit', 'گزارش هفتگی ایمنی'], permissions: ['audit.recent', 'deliver', 'notify'], quota_estimate_month: 900000 },
    seal: null, decided_at: iso(20), decided_by: system, note: 'مالک: استخدام با شروع خود مالک', resolution: null, thread: 'HQ-OVS-MGR', expires_at: ahead(60 * 47), version: 1, effect_status: 'none', work_id: null, id: 'd16', reason_code: null,
  },
  {
    ref: 'D-000017', kind: 'deploy', company: 'PC', action_class: 'A3', risk: 'high', reversible: true, status: 'pending',
    title: 'انتشار نسخه‌ی تازه‌ی ترمینال پرو-چارت', proposer: actor('PC-TECH-MGR', 'مدیر فنی پرو-چارت'), created_at: iso(15),
    what: 'انتشار `terminal` نسخه‌ی 1017ce2 با canary ۱۰٪ و بازگشت خودکار.', why: 'رفع کندی بارگذاری نمودارها (میانگین ۲٫۴ ثانیه).',
    quota_estimate: { tokens: 60000, usd: '1.10' }, risk_note: 'اگر canary شکست بخورد، بازگشت خودکار حدود ۴ دقیقه طول میکشد.',
    payload: { repo: 'pro-chart', pr_url: 'https://github.com/…/pull/42', diff_stat: '+412 −188', ci: { status: 'passed' }, tests: { passed: 286, failed: 0 }, rollout: 'canary 10%' },
    seal: null, decided_at: null, decided_by: null, note: null, resolution: null, thread: 'PC-TECH-MGR', expires_at: ahead(60 * 6), version: 1, effect_status: 'none', work_id: null, id: 'd17', reason_code: null,
  },
  {
    ref: 'D-000011', kind: 'recurring_approval', company: 'TY', action_class: 'A2', risk: 'low', reversible: true, status: 'approved',
    title: 'گزارش هفتگی سئوی فنی', proposer: actor('TY-GROWTH-MGR', 'مدیر رشد تریدیار'), created_at: iso(60 * 20),
    what: 'بررسی هفتگی ۴۰ صفحه‌ی اصلی.', why: 'ورودی ارگانیک ۱۲٪ افت کرده.', quota_estimate: { tokens: 200000, usd: '3.20' }, risk_note: null,
    payload: {}, seal: { method: 'passkey_uv', sealed_at: iso(60 * 19), step_up_id: null }, decided_at: iso(60 * 19), decided_by: owner, note: null, resolution: 'M-0003', thread: null, expires_at: null, version: 2, effect_status: 'applied', work_id: null, id: 'd11', reason_code: null,
  },
];

const employees: any[] = [
  ...['TY', 'FX', 'PC'].flatMap((c) => [
    { code: `${c}-CEO`, company: c, kind: 'ceo', department: null, title_fa: 'مدیرعامل', title_en: 'CEO', activity: c === 'FX' ? 'working' : 'sleeping' },
    { code: `${c}-TECH-MGR`, company: c, kind: 'manager', department: 'TECH', title_fa: 'مدیر فنی', title_en: 'CTO', activity: 'sleeping' },
    { code: `${c}-GROWTH-MGR`, company: c, kind: 'manager', department: 'GROWTH', title_fa: 'مدیر مارکتینگ', title_en: 'CMO', activity: 'sleeping' },
  ]),
  { code: 'TY-GROWTH-01', company: 'TY', kind: 'employee', department: 'GROWTH', title_fa: 'تحلیلگر سئوی فنی', title_en: 'Technical SEO analyst', activity: 'working' },
  { code: 'FX-QUANT-02', company: 'FX', kind: 'employee', department: 'QUANT', title_fa: 'پایشگر سیگنال', title_en: 'Signal monitor', activity: 'waiting', hired_at: iso(60 * 5), probation_until: ahead(60 * 24 * 7) },
  { code: 'HQ-OVS-MGR', company: 'HQ', kind: 'inspector', department: 'OVS', title_fa: 'بازرس کل', title_en: 'Inspector General', activity: 'sleeping' },
  { code: 'HQ-AIOPS-MGR', company: 'HQ', kind: 'manager', department: 'AIOPS', title_fa: 'مدیر عملیات هوش مصنوعی', title_en: 'Head of AI Ops', activity: 'idle' },
  { code: 'HQ-ADV', company: 'HQ', kind: 'advisor', department: null, title_fa: 'مشاور کل', title_en: 'Chief Advisor', activity: 'idle' },
  { code: 'HQ-OVR', company: 'HQ', kind: 'overseer', department: 'OVS', title_fa: 'ناظر کل', title_en: 'Chief Overseer', activity: 'working' },
  { code: 'HQ-PA', company: 'HQ', kind: 'assistant', department: null, title_fa: 'دستیار شخصی', title_en: 'Personal Assistant', activity: 'working' },
].map((e, i) => ({
  id: `e${i}`, status: 'active', display_name: null, duties: [], permissions: [], hired_at: iso(60 * 24 * 2), hired_by_decision: null, dismissed_at: null,
  activity_at: iso(i * 7), activity_note: e.activity === 'working' ? 'خواندن Search Console' : null, reports_to: null, version: 1,
  model: { connection: 'claude-max', model: e.kind === 'advisor' ? 'claude-opus-5-5' : e.kind === 'employee' ? 'claude-haiku-5-5' : 'claude-sonnet-5-5', effort: e.kind === 'advisor' ? 'xhigh' : 'high' },
  score: { value: e.kind === 'employee' ? 7.9 : null, owner_avg: e.kind === 'employee' ? 8.2 : null, rank_in_department: e.kind === 'employee' ? 1 : null, trend: [7.1, 7.4, 7.9] },
  ...e,
}));

const deliverables: any[] = [
  { ref: 'O-000031', company: 'TY', title: 'گزارش سئوی فنی هفته‌ی ۴', summary: '۴۰ صفحه بررسی شد؛ ۷ صفحه بیرون از ایندکس به خاطر canonical اشتباه. ۳ اصلاح فوری و ۵ پیشنهاد CR.', producer: { code: 'TY-GROWTH-01', company: 'TY', kind: 'employee', department: 'GROWTH', title_fa: 'تحلیلگر سئوی فنی' }, rating: null, created_at: iso(70), work_ref: 'W-000102' },
  { ref: 'O-000030', company: 'HQ', title: 'گزارش صبحگاهی', summary: 'دیروز ۴۱ کار تمام شد؛ ۴ تصمیم منتظر مُهر؛ مصرف توکن ۱۸٪ زیر میانگین هفته.', producer: { code: 'HQ-SYS', company: 'HQ', kind: 'system', department: null, title_fa: 'سیستم' }, rating: { score: 8, comment: null, history_count: 1, rated_at: iso(60 * 3), }, created_at: iso(60 * 5), work_ref: 'W-000099' },
  { ref: 'O-000029', company: 'FX', title: 'تحلیل افت دقت سیگنال‌های طلا', summary: 'دقت ۷ روز گذشته ۶۱٪ (میانگین ۶۸٪). علت احتمالی: تغییر رژیم نوسان بعد از خبر فدرال. پیشنهاد: کاهش وزن مدل LSTM.', producer: { code: 'FX-QUANT-02', company: 'FX', kind: 'employee', department: 'QUANT', title_fa: 'پایشگر سیگنال' }, rating: null, created_at: iso(60 * 9), work_ref: 'W-000096' },
].map((d, i) => ({ id: `o${i}`, body: d.summary + '\n\n### جزئیات\n- شاهد: پایش ۷ روزه\n- پیشنهاد: …', attachments: [], evidence: [{ kind: 'metric', ref: 'health.sites', note: '7d' }], produced_with: { model: 'claude-sonnet-5-5', effort: 'high', label_fa: 'Sonnet 5.5 · high' }, usage: { tokens: 48200, usd: '0.84' }, work_id: `w${i}`, ...d }));

const work: any[] = [
  { ref: 'W-000104', title: 'رفع کندی ثبت‌نام', company: 'FX', status: 'in_progress', priority: 'P1', depth: 1, assignee: { code: 'FX-TECH-MGR', company: 'FX', kind: 'manager', department: 'TECH', title_fa: 'مدیر فنی' }, due_at: ahead(60 * 5), progress_pct: 60 },
  { ref: 'W-000102', title: 'سئوی فنی ۴۰ صفحه', company: 'TY', status: 'delivered', priority: 'P3', depth: 2, assignee: { code: 'TY-GROWTH-01', company: 'TY', kind: 'employee', department: 'GROWTH', title_fa: 'تحلیلگر سئوی فنی' }, due_at: iso(-60), progress_pct: 100 },
  { ref: 'W-000105', title: 'پیشنهاد تیم فنی ماه ۱', company: 'PC', status: 'cancelled', priority: 'P3', depth: 1, assignee: { code: 'PC-TECH-MGR', company: 'PC', kind: 'manager', department: 'TECH', title_fa: 'مدیر فنی' }, due_at: ahead(60 * 20), progress_pct: null },
  { ref: 'W-000098', title: 'ممیزی امنیتی همه‌ی شرکت‌ها', company: 'HQ', status: 'waiting', priority: 'P2', depth: 0, assignee: { code: 'HQ-OVS-MGR', company: 'HQ', kind: 'inspector', department: 'OVS', title_fa: 'بازرس کل' }, due_at: iso(120), progress_pct: 20 },
].map((w, i) => ({ id: `w${i}`, kind: 'one_off', brief: 'جزئیات کار…', created_at: iso(60 * (i + 2)), updated_at: iso(i * 11), created_by: owner, department: w.assignee?.department ?? null, overdue: w.ref === 'W-000098', escalation_level: w.ref === 'W-000098' ? 1 : 0, parent_id: null, root_id: `w${i}`, requested_by_work_id: null, budget: { tokens: 200000, tokens_used: 46000 + i * 9000, usd: null, usd_used: '0.80' }, escrow: null, schedule: null, deliverable_ids: [], evidence: [], progress_note: null, version: 1, ...w }));

const threads: any[] = [
  { code: 'A', kind: 'advisor', company: 'HQ', title_fa: 'مشاور کل', unread: 0, last_message_at: iso(25), last_ref: 'A-0004', participants: [owner, actor('HQ-ADV', 'مشاور کل')] },
  { code: 'N', kind: 'overseer', company: 'HQ', title_fa: 'ناظر کل', unread: 1, last_message_at: iso(18), last_ref: 'N-0004', participants: [owner, actor('HQ-OVR', 'ناظر کل', 'overseer')] },
  { code: 'P', kind: 'assistant', company: 'HQ', title_fa: 'دستیار شخصی', unread: 0, last_message_at: iso(14), last_ref: 'P-0003', participants: [owner, actor('HQ-PA', 'دستیار شخصی', 'assistant')] },
  { code: 'FX-CEO', kind: 'ceo', company: 'FX', title_fa: 'مدیرعامل FX', unread: 1, last_message_at: iso(12), last_ref: 'FX-CEO-0010', participants: [owner, actor('FX-CEO', 'مدیرعامل FX')] },
  { code: 'TY-TECH-MGR', kind: 'manager', company: 'TY', title_fa: 'مدیر فنی تریدیار', unread: 1, last_message_at: iso(42), last_ref: 'TY-TECH-MGR-0002', participants: [owner, actor('TY-TECH-MGR', 'مدیر فنی تریدیار')] },
].map((t, i) => ({ id: `t${i}`, ...t }));

// ⟨1.3⟩ files: demo attachments are data URLs (the client's fileUrl passes them through); uploads made in mock
// mode are object URLs registered here by the client, so a sent message can show what was attached.
const ref = (id: string, kind: string, mime: string, name: string, size: number, extra: Record<string, unknown> = {}) =>
  ({ id, name, mime, size, sha256: 'demo', kind, status: 'ready', variants: {}, ...extra });
const CHART = ref(DEMO_CHART.url, 'image', 'image/webp', 'xauusd-h1.webp', 418_221, { width: DEMO_CHART.width, height: DEMO_CHART.height });
const SKETCH = ref(DEMO_SKETCH.url, 'image', 'image/webp', 'signup-sketch.webp', 1_912_004, { width: DEMO_SKETCH.width, height: DEMO_SKETCH.height });
const VOICE = ref(DEMO_VOICE.url, 'audio', 'audio/mp4', 'voice.m4a', 13_163, { duration_s: DEMO_VOICE.seconds, transcript: 'صفحه‌ی ثبت‌نام هنوز کند است…' });
const files = new Map<string, any>();
export function register(f: { id: string; [k: string]: unknown }): void { files.set(f.id, f); }

const messages: Record<string, any[]> = {
  A: [
    { ref: 'A-0001', author: owner, body: 'وضعیت کلی هلدینگ امروز چطور است؟', created_at: iso(60 * 3) },
    { ref: 'A-0002', author: actor('HQ-ADV', 'مشاور کل'), body: '**خلاصه:** چهار تصمیم منتظر مُهر توست؛ سه تا پیشنهاد استخدام ماه ۱ و یکی انتشار پرو-چارت (ریسک بالا).\n\nمصرف توکن امروز `182K` است، ۱۸٪ زیر میانگین هفته (طبق خزانه). پیشنهادم: اول انتشار پرو-چارت را ببین چون تا ۶ ساعت دیگر منقضی میشود (D-000017).', created_at: iso(60 * 3 - 1), links: { decision: 'D-000017' } },
    { ref: 'A-0003', author: owner, body: 'استخدام SRE برای هر سه شرکت لازم است؟', created_at: iso(30) },
    { ref: 'A-0004', author: actor('HQ-ADV', 'مشاور کل'), body: 'برای تریدیار و FX شاهد دارد (دو حادثه‌ی کندی در تریدیار: I-0002، I-0005). برای پرو-چارت هنوز پیشنهادی نیامده. هزینه‌ی هر SRE با Haiku 5.5 حدود `$6–7` در ماه برآورد شده؛ برگشت‌پذیر است.\n\n**توصیه:** دو استخدام اول را مُهر کن؛ سومی را بعد از دیدن پیشنهاد پرو-چارت.', created_at: iso(25), links: { decision: 'D-000014' } },
  ].map((m, i) => ({ id: `m${i}`, thread: 'A', kind: 'text', attachments: [], links: {}, ...m })),
  N: [
    { ref: 'N-0001', author: owner, kind: 'voice_transcript', body: 'از این به بعد هر شرکتی که دو هفته پشت سر هم چالش را از دست داد، با مدیرعاملش جلسه بگذار و برنامه‌ی جبران با تاریخ بخواه.', created_at: iso(40), attachments: [] },
    { ref: 'N-0002', author: actor('HQ-OVR', 'ناظر کل', 'overseer'), body: 'دریافت شد. این را به قاعده‌ی دقیق تبدیل کردم و برای آزمون آکادمی فرستادم (TE-0002؛ نمره 93 در برابر خط پایه 90). با مُهر تو در منشورم میاید.', created_at: iso(36), links: { teaching: 'TE-0002' } },
    { ref: 'N-0003', author: actor('HQ-OVR', 'ناظر کل', 'overseer'), body: '**گزارش «در نبودت»:** یک انتشار پرریسک پرو-چارت را نگه داشتم (H-0002)، یک یافته‌ی critical باز شد (FI-0009: تغییر پیکربندی بی‌مُهر) و یک high (FI-0008: دقت گزارش‌شده‌ی FX). منتظر تو: آزاد یا رد H-0002.', created_at: iso(60) },
    { ref: 'N-0004', author: actor('HQ-OVR', 'ناظر کل', 'overseer'), body: 'از مدیرعامل پرو-چارت پرسش رسمی کردم که تغییر 03:12 را چه کسی و بر اساس کدام تصمیم اعمال کرد (Q-0005، مهلت ۲ ساعت).', created_at: iso(18) },
  ].map((m, i) => ({ id: `mn${i}`, thread: 'N', kind: 'text', attachments: [], links: {}, ...m })),
  P: [
    { ref: 'P-0001', author: owner, kind: 'voice_transcript', body: 'سه سرویس ایمیل تراکنشی برای تریدیار پیدا کن، برای حدود دویست هزار ایمیل در ماه، و قیمت‌ها را مقایسه کن.', created_at: iso(16), attachments: [] },
    { ref: 'P-0002', author: actor('HQ-PA', 'دستیار شخصی', 'assistant'), body: 'شروع کردم (E-0003). صفحه‌ی قیمت رسمی هر سه را میخوانم و تا یک ساعت دیگر جدول مقایسه با تاریخ میدهم.', created_at: iso(15), links: { errand: 'E-0003' } },
    { ref: 'P-0003', author: actor('HQ-PA', 'دستیار شخصی', 'assistant'), body: 'رزرو هتل استانبول آماده است؛ گزینه‌ی اول با لغو رایگان تا ۴۸ ساعت قبل. پرداخت با مُهر توست (D-000021).', created_at: iso(14), links: { errand: 'E-0002', decision: 'D-000021' } },
  ].map((m, i) => ({ id: `mp${i}`, thread: 'P', kind: 'text', attachments: [], links: {}, ...m })),
  'FX-CEO': [
    { ref: 'FX-CEO-0006', author: owner, body: 'این افت را ببین. دلیلش چه بود و سیگنال ما همان موقع چه گفت؟', created_at: iso(60 * 5), attachments: [CHART] },
    { ref: 'FX-CEO-0007', author: actor('FX-CEO', 'مدیرعامل FX'), body: '**خلاصه:** افت ۹ دلاری طلا درست بعد از داده‌ی اشتغال آمریکا بود. سیگنال ما ۲۰ دقیقه قبلش «فروش» داده بود و حد سود اول خورد.\n\nافت دقت این هفته (۶۱٪) از همین خبرهاست؛ تحلیل کامل در O-000029 آمده.', created_at: iso(60 * 5 - 3) },
    { ref: 'FX-CEO-0008', author: owner, kind: 'voice_transcript', body: 'صفحه‌ی ثبت‌نام هنوز کند است. به مدیر فنی بگو تا فردا ظهر علتش را پیدا کند و اصلاح را در کارگاه کد، روی شاخه‌ی جدا، آماده کند. قبل از ادغام خودم نگاه میکنم.', created_at: iso(41), attachments: [VOICE] },
    { ref: 'FX-CEO-0009', author: owner, body: 'این طرح فرم کوتاه‌تر است؛ دکمه‌ی آخر همان جایی است که کاربرها رها میکنند.', created_at: iso(40), attachments: [SKETCH] },
    { ref: 'FX-CEO-0010', author: actor('FX-CEO', 'مدیرعامل FX'), body: 'دریافت شد. کار به مدیر فنی سپرده شد و جلسه‌ی کد S-0004 روی شاخه‌ی `hq/S-0004` باز است؛ طرح فرم هم ضمیمه‌ی همان کار شد. قبل از push اجازه‌ی تو را میخواهد.', created_at: iso(12), links: { work: 'W-000104' } },
  ].map((m, i) => ({ id: `mf${i}`, thread: 'FX-CEO', kind: 'text', attachments: [], links: {}, ...m })),
};

const notifications: any[] = [
  { id: 'n1', level: 'decision', company: 'PC', title_fa: 'انتشار ترمینال منتظر مُهر', body_fa: 'D-000017 · ریسک بالا · ۶ ساعت تا انقضا', created_at: iso(15), read_at: null, link: { kind: 'decision', ref: 'D-000017' } },
  { id: 'n2', level: 'report', company: 'HQ', title_fa: 'گزارش صبحگاهی آماده است', body_fa: '۴۱ کار تمام شد · ۴ تصمیم منتظر', created_at: iso(60 * 5), read_at: iso(60 * 4), link: { kind: 'deliverable', ref: 'O-000030' } },
  { id: 'n3', level: 'urgent', company: 'TY', title_fa: 'پنل کاربری تریدیار کند است', body_fa: '۳ شکست پشت هم · I-0005 · مدیر فنی بیدار شد', created_at: iso(60 * 26), read_at: iso(60 * 25), link: { kind: 'work', ref: 'W-000101' } },
  { id: 'n4', level: 'learning', company: 'HQ', title_fa: 'چرا انتشار قبلی را برگرداندی؟', body_fa: 'جواب یک‌لمسی به یادگیری سیستم کمک میکند.', created_at: iso(60 * 30), read_at: null, link: null, choices: [{ id: 'timing', label_fa: 'زمان بد' }, { id: 'risk', label_fa: 'ریسک' }, { id: 'quality', label_fa: 'کیفیت' }] },
].map((n) => ({ state: n.read_at ? 'read' : 'delivered', delivered: { in_app: true, web_push: false, fcm: false, telegram: false }, answer: null, choices: null, ...n }));

const summary = {
  period: 'day', period_start: iso(60 * 14), company: null,
  totals: { calls: 214, input_tokens: 118400, output_tokens: 41200, cache_read_tokens: 22100, cache_write_tokens: 6400, thinking_tokens: 0, cost_usd: '0.00', equiv_cost_usd: '2.94' },
  budgets: [
    { company: 'HQ', scope_type: 'holding', scope_ref: 'HQ', period: 'month', level: 0, token_limit: 30_000_000, tokens_used: 6_240_000, pct: 21, usd_limit: '600.00', usd_used: '128.40' },
    { company: 'TY', scope_type: 'company', scope_ref: 'TY', period: 'month', level: 1, token_limit: 10_000_000, tokens_used: 7_400_000, pct: 74, usd_limit: null, usd_used: '58.10' },
    { company: 'FX', scope_type: 'company', scope_ref: 'FX', period: 'month', level: 1, token_limit: 10_000_000, tokens_used: 4_100_000, pct: 41, usd_limit: null, usd_used: '42.30' },
    { company: 'PC', scope_type: 'company', scope_ref: 'PC', period: 'month', level: 1, token_limit: 6_000_000, tokens_used: 5_520_000, pct: 92, usd_limit: null, usd_used: '21.60' },
  ],
  top_consumers: [
    { actor: 'FX-TECH-MGR', company: 'FX', calls: 31, tokens: 58100, usd: '0.98' },
    { actor: 'TY-GROWTH-01', company: 'TY', calls: 22, tokens: 41200, usd: '0.71' },
    { actor: 'HQ-ADV', company: 'HQ', calls: 6, tokens: 35100, usd: '0.64' },
    { actor: 'FX-QUANT-02', company: 'FX', calls: 48, tokens: 31700, usd: '0.41' },
    { actor: 'HQ-SYS', company: 'HQ', calls: 9, tokens: 12900, usd: '0.20' },
  ],
};

const breakdown = (by: string) => {
  if (by === 'model') return [['claude-sonnet-5-5', 96000, 28000], ['claude-haiku-5-5', 31000, 9200], ['claude-opus-5-5', 21000, 3600]].map(([k, i, o]) => row(k as string, i as number, o as number));
  if (by === 'company') return [['TY', 52000, 16000], ['FX', 61000, 18200], ['PC', 14000, 4100], ['HQ', 21000, 2900]].map(([k, i, o]) => row(k as string, i as number, o as number));
  // by day (hour buckets) for the cumulative chart
  return Array.from({ length: 14 }, (_, d) => row(new Date(now - (13 - d) * 86_400_000).toISOString().slice(0, 10), 90_000 + ((d * 37_000) % 80_000), 26_000 + ((d * 13_000) % 30_000)));
};
function row(key: string, input: number, output: number) {
  return { key, input_tokens: input, output_tokens: output, cache_read_tokens: Math.round(input * 0.18), cache_write_tokens: Math.round(input * 0.05), calls: Math.round(input / 900), cost_usd: '0.00', equiv_cost_usd: ((input * 2 + output * 10) / 1e6).toFixed(2) };
}

const connections: any[] = [
  { id: 'c1', key: 'claude-max', display_name: 'اشتراک Claude (Max)', kind: 'claude_subscription', provider: 'anthropic', status: 'enabled', status_reason: null, models: ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'], default_model: 'claude-sonnet-5-5', fallback_priority: 1, has_secret_ref: true, limits: {}, pricing: {}, quota_reset_at: ahead(60 * 30), updated_at: iso(60), version: 1 },
  { id: 'c2', key: 'anthropic-api', display_name: 'API Anthropic (پشتیبان)', kind: 'api_key', provider: 'anthropic', status: 'disabled', status_reason: 'set by the owner', models: ['claude-sonnet-5-5', 'claude-haiku-5-5'], default_model: 'claude-haiku-5-5', fallback_priority: 2, has_secret_ref: false, limits: {}, pricing: {}, quota_reset_at: null, updated_at: iso(60 * 40), version: 2 },
  // As seeded on the server (services/llm-router/seed/connections.yaml): other providers start disabled and without a key.
  { id: 'c3', key: 'openai', display_name: 'OpenAI API', kind: 'api_key', provider: 'openai', status: 'disabled', status_reason: 'no key yet', models: ['gpt-5', 'gpt-5-mini'], default_model: 'gpt-5-mini', fallback_priority: 3, has_secret_ref: false, limits: {}, pricing: {}, quota_reset_at: null, updated_at: iso(60 * 40), version: 1 },
  { id: 'c4', key: 'google-gemini', display_name: 'Google Gemini API', kind: 'api_key', provider: 'gemini', status: 'disabled', status_reason: 'no key yet', models: ['gemini-2.5-pro', 'gemini-2.5-flash'], default_model: 'gemini-2.5-flash', fallback_priority: 4, has_secret_ref: false, limits: {}, pricing: {}, quota_reset_at: null, updated_at: iso(60 * 40), version: 1 },
  { id: 'c5', key: 'openai-compatible', display_name: 'سازگار با OpenAI (Kimi، GLM، DeepSeek …)', kind: 'api_key', provider: 'openai_compatible', status: 'disabled', status_reason: 'no key yet', models: ['deepseek-chat', 'kimi-k2', 'glm-4.6'], default_model: 'deepseek-chat', fallback_priority: 5, has_secret_ref: false, limits: {}, pricing: {}, quota_reset_at: null, updated_at: iso(60 * 40), version: 1 },
];

const control = {
  holding: { scope: 'holding', company: 'HQ', state: 'released', changed_at: iso(60 * 48), changed_by: null, reason: null },
  companies: ['TY', 'FX', 'PC'].map((c) => ({ scope: `company:${c}`, company: c, state: 'released', changed_at: iso(60 * 48), changed_by: null, reason: null })),
  deploy_freezes: [{ company: 'FX', until: ahead(95), reason: 'انتشار در جریان', created_by: 'pipeline' }],
};

const audit = Array.from({ length: 12 }, (_, i) => ({
  seq: 1200 - i, at: iso(i * 13), actor: i % 3 === 0 ? owner : actor(['FX-TECH-MGR', 'TY-GROWTH-01', 'HQ-ADV'][i % 3]!, ''), principal_kind: i % 3 === 0 ? 'owner' : 'agent', company: ['TY', 'FX', 'PC', 'HQ'][i % 4],
  action: ['decision.approve', 'work.deliver', 'message.post', 'work.delegate', 'kill_switch.engage', 'deliverable.rate'][i % 6], action_class: ['A1', 'A2', 'A0', 'A2', 'A2', 'A1'][i % 6], target: { kind: 'work', ref: `W-000${90 + i}` },
  request_id: null, ip_hash: null, step_up: i % 6 === 0, summary: 'ok', prev_hash: 'a3f1…', hash: '9c2e…',
}));

// ------------------------------------------------- ⟨1.3⟩ workshop, voice, orders --
const tech = (c: string) => actor(`${c}-TECH-MGR`, `مدیر فنی ${c === 'TY' ? 'تریدیار' : c === 'PC' ? 'پرو-چارت' : c}`, 'manager');
const workspaces = [
  { code: 'HQ-HUB', company: 'HQ', repo: 'behnamjalalico/CoinePro-Hub', default_branch: 'claude/coinepro-hub-setup-hsvnw7', title_fa: 'ستاد کوینه‌پرو (همین هاب)' },
  { code: 'TY-WEB', company: 'TY', repo: 'behnamjalalico/TradeYar', default_branch: 'main', title_fa: 'سایت و پنل تریدیار' },
  { code: 'FX-APP', company: 'FX', repo: 'behnamjalalico/CoineProFx', default_branch: 'main', title_fa: 'پلتفرم سیگنال کوینه‌پرو FX' },
  { code: 'PC-APP', company: 'PC', repo: 'behnamjalalico/CoinePro-App', default_branch: 'main', title_fa: 'اپ اندروید پرو-چارت' },
].map((w, i) => ({ id: `ws${i}`, policy: { branch_prefix: 'hq/', may_open_pr: true, merge: 'owner_seal', deploy: 'owner_seal' }, status: 'active', ...w }));

const grants: any[] = [
  { ref: 'G-0003', workspace: 'FX-APP', actions: ['read', 'edit', 'run', 'push_branch', 'open_pr'], driver: tech('FX'), budget_usd: 25, expires_at: ahead(60 * 70), decision_ref: 'D-000019' },
  { ref: 'G-0002', workspace: 'TY-WEB', actions: ['read', 'edit', 'run', 'push_branch', 'open_pr'], driver: tech('TY'), budget_usd: 10, expires_at: ahead(60 * 20), decision_ref: null },
  { ref: 'G-0001', workspace: 'HQ-HUB', actions: ['read', 'run'], driver: actor('HQ-AIOPS-MGR', 'مدیر عملیات هوش مصنوعی', 'manager'), budget_usd: 5, expires_at: ahead(60 * 24 * 5), decision_ref: null },
].map((g, i) => ({ id: `g${i}`, granted_by: owner, revoked_at: null, ...g }));

type Ev = { seq: number; at: string; type: string; actor: any; summary_fa: string; data: Record<string, unknown> };
const ev = (minAgo: number, type: string, who: any, summary_fa: string, data: Record<string, unknown> = {}): Omit<Ev, 'seq'> => ({ at: iso(minAgo), type, actor: who, summary_fa, data });
const sys = { kind: 'system', code: 'HQ-SYS', display_fa: 'سیستم' };
const number = (xs: Array<Omit<Ev, 'seq'>>): Ev[] => xs.map((e, i) => ({ seq: i + 1, ...e }));

const sessions: any[] = [
  {
    ref: 'S-0004', workspace: 'FX-APP', grant: 'G-0003', title: 'رفع کندی ثبت‌نام', brief: 'از فرمان صوتی F-0002: علت کندی صفحه‌ی ثبت‌نام را پیدا کن و اصلاح را روی شاخه‌ی جدا آماده کن.',
    opened_by: owner, driver: tech('FX'), state: 'waiting_approval', branch: 'hq/S-0004', pr_url: null, usage: { usd: 3.12, input_tokens: 412_000, output_tokens: 38_400 }, created_at: iso(38),
    events: number([
      ev(38, 'state', sys, 'جلسه شروع شد؛ کلون تازه از main', { state: 'working' }),
      ev(37, 'message', tech('FX'), 'از فرمان صوتی F-0002: کندی صفحه‌ی ثبت‌نام. اول اندازه میگیرم، بعد اصلاح.'),
      ev(33, 'command', tech('FX'), 'تست‌های فعلی ثبت‌نام سبز است', { cmd: 'pytest tests/test_phase7_auth.py -q', exit_code: 0, duration_s: 41 }),
      ev(27, 'progress', tech('FX'), 'پیدا شد: هر ثبت‌نام سه بار جدول کاربران را بدون ایندکس روی ایمیل میگردد (۲.۸ ثانیه).'),
      ev(21, 'file_change', tech('FX'), 'ایندکس یکتا روی ایمیل', { path: 'alembic/versions/0042_users_email_index.py', added: 24, removed: 0 }),
      ev(19, 'file_change', tech('FX'), 'حذف دو کوئری تکراری', { path: 'src/api/routes/auth.py', added: 11, removed: 17 }),
      ev(12, 'command', tech('FX'), '۴۶ تست سبز؛ ثبت‌نام در تست بار از ۲.۹ به ۰.۳۱ ثانیه رسید', { cmd: 'pytest tests/ -q -k "auth or signup"', exit_code: 0, duration_s: 96 }),
      ev(9, 'message', tech('FX'), '**آماده است.** دو commit روی `hq/S-0004`: ایندکس یکتا روی `users.email` و حذف دو کوئری تکراری. migration برگشت‌پذیر است. برای push اجازه میخواهم.'),
      ev(9, 'approval_request', tech('FX'), 'اجازه‌ی push به شاخه‌ی hq/S-0004', { approval_id: 'AP-0007', action: 'push_branch', detail: 'git push origin hq/S-0004 · 2 commits · +35 −17' }),
    ]),
    script: [],
  },
  {
    ref: 'S-0003', workspace: 'TY-WEB', grant: 'G-0002', title: 'اصلاح canonical هفت صفحه', brief: 'از گزارش O-000031: هفت صفحه canonical اشتباه دارند؛ اصلاح و تست سئو.',
    opened_by: tech('TY'), driver: tech('TY'), state: 'working', branch: 'hq/S-0003', pr_url: null, usage: { usd: 0.84, input_tokens: 96_000, output_tokens: 7_100 }, created_at: iso(14),
    events: number([
      ev(14, 'state', sys, 'جلسه شروع شد؛ کلون تازه از main', { state: 'working' }),
      ev(13, 'message', tech('TY'), 'از گزارش O-000031: هفت صفحه canonical اشتباه دارند. قالب‌ها را میگردم.'),
      ev(11, 'command', tech('TY'), '۵۸ تگ canonical پیدا شد', { cmd: 'grep -rn \'rel="canonical"\' templates/ | wc -l', exit_code: 0, duration_s: 1 }),
    ]),
    script: [
      { type: 'progress', actor: tech('TY'), summary_fa: '۷ قالب canonical را به صفحه‌ی اصلی میدهند، نه به خودشان.', data: {} },
      { type: 'file_change', actor: tech('TY'), summary_fa: 'canonical به نشانی خود صفحه', data: { path: 'templates/blog/post.html', added: 1, removed: 1 } },
      { type: 'file_change', actor: tech('TY'), summary_fa: 'canonical به نشانی خود صفحه', data: { path: 'templates/markets/symbol.html', added: 1, removed: 1 } },
      { type: 'command', actor: tech('TY'), summary_fa: 'ساخت و تست سئو سبز', data: { cmd: 'npm run build && npm run test:seo', exit_code: 0, duration_s: 74 } },
      { type: 'approval_request', actor: tech('TY'), summary_fa: 'اجازه‌ی باز کردن PR', data: { approval_id: 'AP-0008', action: 'open_pr', detail: 'PR: hq/S-0003 → main · 7 فایل · +7 −7' } },
    ],
  },
  {
    ref: 'S-0002', workspace: 'HQ-HUB', grant: 'G-0001', title: 'بررسی هزینه‌ی مدل‌ها در خزانه', brief: 'فقط خواندن: کدام نقش‌ها با مدل سنگین‌تر از لازم کار میکنند؟',
    opened_by: owner, driver: actor('HQ-AIOPS-MGR', 'مدیر عملیات هوش مصنوعی', 'manager'), state: 'done', branch: null, pr_url: null, usage: { usd: 0.41, input_tokens: 58_000, output_tokens: 4_900 }, created_at: iso(60 * 26),
    events: number([
      ev(60 * 26, 'state', sys, 'جلسه شروع شد (فقط خواندن)', { state: 'working' }),
      ev(60 * 25, 'message', actor('HQ-AIOPS-MGR', 'مدیر عملیات هوش مصنوعی', 'manager'), '**نتیجه:** دو نقش پایشگر با Sonnet کار میکنند ولی Haiku کافی است؛ صرفه‌جویی تقریبی ۱۸٪ بودجه‌ی FX. پیشنهادش را به کارتابل فرستادم.'),
      ev(60 * 25, 'state', sys, 'تمام شد', { state: 'done' }),
    ]),
    script: [],
  },
  {
    ref: 'S-0001', workspace: 'FX-APP', grant: 'G-0003', title: 'به‌روزرسانی وابستگی‌ها', brief: 'به‌روزرسانی وابستگی‌های پایتون با تست کامل.',
    opened_by: tech('FX'), driver: tech('FX'), state: 'stopped', branch: 'hq/S-0001', pr_url: null, usage: { usd: 1.06, input_tokens: 131_000, output_tokens: 9_800 }, created_at: iso(60 * 50),
    events: number([
      ev(60 * 50, 'state', sys, 'جلسه شروع شد', { state: 'working' }),
      ev(60 * 49, 'command', tech('FX'), 'دو تست بک‌تست قرمز شد', { cmd: 'pytest tests/test_phase12_backtest.py -q', exit_code: 1, duration_s: 212 }),
      ev(60 * 48, 'state', owner, 'مدیر کل متوقف کرد: «اول افت دقت سیگنال‌ها»', { state: 'stopped' }),
    ]),
    script: [],
  },
].map((x, i) => ({ id: `s${i}`, runtime: 'managed', model: 'claude-sonnet-5-5', effort: 'high', updated_at: x.events.at(-1)?.at ?? x.created_at, ...x }));

const sessionOut = (x: any) => { const { events: _e, script: _s, ...rest } = x; return rest; };
function reveal(x: any, e: Omit<Ev, 'seq' | 'at'>) {
  const out: Ev = { seq: x.events.length + 1, at: new Date().toISOString(), ...e };
  x.events.push(out);
  x.updated_at = out.at;
  if (e.type === 'approval_request') x.state = 'waiting_approval';
  if (e.type === 'state' && typeof e.data.state === 'string') x.state = e.data.state;
  if (e.type !== 'approval_request' && e.type !== 'state' && x.state === 'starting') x.state = 'working';
  x.usage.usd = Math.round((x.usage.usd + 0.07) * 100) / 100;
  return out;
}

const TRANSCRIPTS = {
  message: [
    'سلام. گزارش امروز دقت سیگنال‌های طلا را تا ساعت پنج بفرست و اگر افت ادامه داشت، دو پیشنهاد اصلاح هم کنارش بگذار.',
    'این عکس را ببین؛ رنگ دکمه‌ی خرید در حالت شب خوانا نیست. با تیم طراحی هماهنگ کن و نسخه‌ی اصلاح‌شده را نشانم بده.',
  ],
  order: [
    'به مدیر فنی کوینه‌پرو FX بگو کندی صفحه‌ی ثبت‌نام را تا فردا ظهر بررسی کند و اصلاحش را در کارگاه کد روی شاخه‌ی جدا آماده کند.',
    'برای پنجشنبه یک جلسه با مدیرعامل‌های تریدیار و پرو-چارت بگذار؛ موضوع: برنامه‌ی رشد سه ماه آینده.',
  ],
  note: ['یادداشت: از مشاور کل بپرس هزینه‌ی کارگاه کد در ماه اول چقدر شد.'],
};
const said = { message: 0, order: 0, note: 0 };

const orders: any[] = [
  { ref: 'F-0002', text: 'صفحه‌ی ثبت‌نام FX کند است؛ مدیر فنی علتش را پیدا کند و اصلاح را در کارگاه کد روی شاخه‌ی جدا آماده کند.', source: 'voice', file_id: VOICE.id, created_at: iso(40),
    summary_fa: 'به مدیر فنی FX رسید: کار W-000104 و جلسه‌ی کد S-0004.', routes: [{ company: 'FX', to: 'FX-TECH-MGR', kind: 'work', work_ref: 'W-000104' }, { company: 'FX', to: 'FX-TECH-MGR', kind: 'code', session_ref: 'S-0004' }] },
  { ref: 'F-0001', text: 'خلاصه‌ی وضعیت سئوی تریدیار را برای جلسه‌ی هفتگی آماده کنید.', source: 'text', file_id: null, created_at: iso(60 * 30),
    summary_fa: 'به مدیر مارکتینگ تریدیار رسید: کار W-000102.', routes: [{ company: 'TY', to: 'TY-GROWTH-MGR', kind: 'work', work_ref: 'W-000102' }] },
];

/** Rules first, like the hub (§17.4): a named company, then the kind of work from known words. */
function routeOrder(text: string) {
  const co = /تریدیار|tradeyar/i.test(text) ? 'TY' : /پرو-?چارت|pro-?chart/i.test(text) ? 'PC' : /FX|اف‌?ایکس|کوینه‌پرو FX/i.test(text) ? 'FX' : null;
  const routes: any[] = [];
  if (/جلسه/.test(text)) routes.push({ company: 'HQ', to: 'HQ-ADV', kind: 'meeting', decision_ref: null });
  if (co && /کد|شاخه|باگ|اصلاح|کارگاه/.test(text)) {
    const live = sessions.find((x) => x.workspace.startsWith(co) && ['working', 'waiting_approval', 'idle'].includes(x.state));
    routes.push({ company: co, to: `${co}-TECH-MGR`, kind: 'work', work_ref: 'W-000106' }, { company: co, to: `${co}-TECH-MGR`, kind: 'code', ...(live ? { session_ref: live.ref } : { decision_ref: 'D-000020' }) });
  } else if (co) routes.push({ company: co, to: `${co}-CEO`, kind: 'work', work_ref: 'W-000106' });
  if (!routes.length) routes.push({ company: 'HQ', to: 'HQ-ADV', kind: 'question' });
  const who: Record<string, string> = { work: 'کار', code: 'کارگاه کد', meeting: 'جلسه', question: 'پرسش از مشاور کل' };
  return { routes, summary_fa: `رسید: ${routes.map((r) => `${who[r.kind]} (${r.company})`).join('، ')}.` };
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const page = (items: unknown[]) => ({ items, next_cursor: null });

export async function handle(req: Request): Promise<Response> {
  const u = new URL(req.url);
  const p = u.pathname.replace(/^\/api\/v1/, '');
  const m = req.method;
  await new Promise((r) => setTimeout(r, 120 + Math.random() * 180));
  const v14 = await handle14(req, p, u);
  if (v14) return v14;
  const ops = await handleOps(req, p, u, { work, employees, control, companies, messages, threads, envelope, summary, connections });
  if (ops) return ops;
  if (m !== 'GET') {
    if (p.startsWith('/auth/passkey/') && p.endsWith('/options')) return json({ challenge: 'mock', rpId: 'localhost', timeout: 60000, userVerification: 'required' });
    if (p === '/auth/step-up/options') return json({ challenge: 'mock' });
    if (p === '/auth/step-up/verify') return json({ step_up_token: 'mock-step-up', expires_at: ahead(2) });
    if (p === '/auth/passkey/login/verify') return json({ session: { expires_at: ahead(60 * 24 * 30) } });
    if (p === '/owner/hiring/start') {
      const b = (await req.json().catch(() => ({}))) as { mode: 'delegated' | 'proposals' };
      const missing = CO.filter((c) => c.kind !== 'holding' && !envelope[c.code]).map((c) => c.code);
      if (b.mode === 'delegated' && missing.length) return json({ code: 'envelope_required', message_fa: `برای ${missing.join('، ')} پاکت ماهانه تعیین نشده است.`, status: 422, title: 'Unprocessable', type: 'about:blank', fields: { envelopes: missing.join(', ') } }, 422);
      Object.assign(hiring, { state: 'open', mode: b.mode, changed_at: iso(0), changed_by: owner });
      // One "build your first month's team" item for each CEO, once.
      if (b.mode) for (const c of CO.filter((x) => x.kind !== 'holding')) if (!work.some((w) => w.title === 'پیشنهاد تیم ماه اول' && w.company === c.code)) work.unshift({ ...work[0], id: `wh-${c.code}`, ref: `W-0002${work.length}`, title: 'پیشنهاد تیم ماه اول', company: c.code, status: 'queued', priority: 'P3', depth: 0, assignee: { code: `${c.code}-CEO`, company: c.code, kind: 'ceo', department: null, title_fa: 'مدیرعامل' }, created_at: iso(0) });
      return json(hiringView());
    }
    if (p === '/owner/hiring/close') {
      for (const d of decisions) if (d.kind === 'hire' && d.status === 'pending') { Object.assign(d, { status: 'withdrawn', decided_at: iso(0), decided_by: system, note: 'مالک: استخدام با شروع خود مالک' }); hiring.withdrawn.push(d.ref); }
      Object.assign(hiring, { state: 'closed', mode: null, changed_at: iso(0), changed_by: owner });
      return json(hiringView());
    }
    if (p === '/org/hires') {
      const b = (await req.json().catch(() => ({}))) as { company: string; department: string; role: string; title_fa: string; title_en?: string; model?: string; effort?: string; reason?: string; duties?: string[] };
      const r = roles.find((x) => x.role === b.role);
      const co = CO.find((c) => c.code === b.company);
      if (!r || !co || r.kind !== 'employee' || r.scope !== (co.kind === 'holding' ? 'holding' : 'company') || (r.department && r.department !== b.department)) return json({ code: 'validation_failed', message_fa: 'این نقش با این شرکت و دپارتمان نمیخواند.', status: 422, title: 'Unprocessable', type: 'about:blank', fields: { role: 'does not fit' } }, 422);
      const n = employees.filter((e) => e.company === b.company && e.department === b.department && e.kind === 'employee').length + 1;
      const ref = `D-0000${decisions.length + 30}`;
      const emp = { ...employees.find((e) => e.kind === 'employee'), id: `e-${ref}`, code: `${b.company}-${b.department}-${String(n).padStart(2, '0')}`, company: b.company, department: b.department, kind: 'employee', title_fa: b.title_fa, title_en: b.title_en ?? r.title_en, activity: 'idle', activity_at: iso(0), activity_note: null, hired_at: iso(0), hired_by_decision: ref, model: { connection: 'claude-max', model: b.model ?? r.model, effort: b.effort ?? r.effort }, score: { value: null, owner_avg: null, rank_in_department: null, trend: [] } };
      const dec = { ...decisions[0], id: `d-${ref}`, ref, company: b.company, status: 'approved', title: `استخدام ${b.title_fa}`, proposer: owner, created_at: iso(0), what: `${b.title_fa} (${r.title_en}) در دپارتمان ${b.department}.`, why: b.reason ?? 'استخدام مستقیم مالک', payload: { ...b, role: r.role, title_en: b.title_en ?? r.title_en, model: b.model ?? r.model, effort: b.effort ?? r.effort }, seal: { method: 'passkey_uv', sealed_at: iso(0), step_up_id: null }, decided_at: iso(0), decided_by: owner, note: null, resolution: `M-00${decisions.length + 10}`, effect_status: 'applied', thread: null, expires_at: null };
      employees.push(emp); decisions.unshift(dec);
      stories.push({ id: `st-${ref}`, ref: `ST-${String(stories.length + 101).padStart(6, '0')}`, company: b.company, kind: 'hire', author: system, title_fa: `${b.title_fa} به تیم پیوست`, body_fa: b.reason ?? 'استخدام مستقیم مالک', figures: [{ label_fa: 'مدل', value: modelName(b.model ?? r.model) }, { label_fa: 'effort', value: b.effort ?? r.effort }], links: { employee: emp.code, decision: ref }, media: null, created_at: iso(0), expires_at: iso(-60 * 24), seen: false, welcomed: false });
      hiresMonth[b.company] = (hiresMonth[b.company] ?? 0) + 1;
      return json({ employee: emp, decision: dec }, 201);
    }
    if (p === '/stories/seen') {
      const b = (await req.json().catch(() => ({ refs: [] }))) as { refs: string[] };
      for (const x of stories) if (b.refs.includes(x.ref)) x.seen = true;
      return json({ updated: b.refs.length });
    }
    const sw = /^\/stories\/(ST-\d+)\/welcome$/.exec(p);
    if (sw) { const x = stories.find((y) => y.ref === sw[1]); if (!x) return json({}, 404); if (x.kind !== 'hire') return json({ code: 'validation_failed', message_fa: 'فقط استوری استخدام خوش‌آمد دارد.', status: 422, title: 'Unprocessable', type: 'about:blank' }, 422); x.welcomed = true; return json(x); }
    const d = /^\/decisions\/(D-\d+)\/(approve|reject|return)$/.exec(p);
    if (d) {
      const x = decisions.find((y) => y.ref === d[1]);
      if (x) Object.assign(x, { status: d[2] === 'approve' ? 'approved' : d[2] === 'reject' ? 'rejected' : 'returned', decided_at: new Date().toISOString(), decided_by: owner, seal: d[2] === 'approve' ? { method: 'passkey_uv', sealed_at: new Date().toISOString(), step_up_id: 'mock' } : null, resolution: d[2] === 'approve' ? 'M-0007' : null });
      return json(x);
    }
    const r = /^\/deliverables\/(O-\d+)\/rating$/.exec(p);
    if (r) {
      const body = (await req.json()) as { score: number };
      const x = deliverables.find((y) => y.ref === r[1]);
      if (x) x.rating = { score: body.score, comment: null, history_count: 1, rated_at: new Date().toISOString() };
      return json(x);
    }
    const t = /^\/threads\/([^/]+)\/messages$/.exec(p);
    if (t) {
      const body = (await req.json()) as { body: string; attachments?: string[] };
      const list = (messages[t[1]!] ??= []);
      const attachments = (body.attachments ?? []).map((id) => files.get(id) ?? ref(id, 'document', 'application/octet-stream', 'file', 0));
      const kind = body.body && attachments.some((a) => a.kind === 'audio') ? 'voice_transcript' : 'text';
      const msg = { id: `m${Date.now()}`, ref: `${t[1]}-${String(list.length + 1).padStart(4, '0')}`, thread: t[1], author: owner, body: body.body, created_at: new Date().toISOString(), kind, attachments, links: {} };
      list.push(msg);
      return json({ message: msg, reply: { state: 'queued' } }, 201);
    }
    if (p === '/transcribe') {
      await new Promise((r) => setTimeout(r, 700));
      const purpose = (u.searchParams.get('purpose') ?? 'message') as keyof typeof TRANSCRIPTS;
      const list = TRANSCRIPTS[purpose] ?? TRANSCRIPTS.message;
      const text = list[said[purpose]++ % list.length]!;
      return json({ text, language: 'fa', duration_s: 6.4, confidence: 0.94, segments: [{ start_s: 0, end_s: 6.4, text }], file_id: 'mock', engine: { name: 'faster-whisper', model: 'large-v3-turbo', version: 'mock' } });
    }
    if (p === '/orders') {
      const b = (await req.json()) as { text: string; source: string; file_id: string | null };
      const o = { ref: `F-${String(orders.length + 1).padStart(4, '0')}`, text: b.text, source: b.source, file_id: b.file_id, created_at: new Date().toISOString(), ...routeOrder(b.text) };
      orders.unshift(o);
      return json(o, 201);
    }
    if (p === '/workshop/grants') {
      const b = (await req.json()) as { workspace: string; actions: string[]; driver: string | null; budget_usd: number; expires_at: string };
      const d = employees.find((e) => e.code === b.driver);
      const g = { id: `g${grants.length}`, ref: `G-${String(grants.length + 1).padStart(4, '0')}`, ...b, driver: d ? actor(d.code, d.title_fa, d.kind) : null, granted_by: owner, decision_ref: null, revoked_at: null };
      grants.unshift(g);
      return json(g, 201);
    }
    const gr = /^\/workshop\/grants\/(G-\d+)\/revoke$/.exec(p);
    if (gr) {
      const g = grants.find((x) => x.ref === gr[1]);
      if (!g) return json({ code: 'not_found', message_fa: 'پیدا نشد.' }, 404);
      g.revoked_at = new Date().toISOString();
      for (const x of sessions) if (x.grant === g.ref && !['done', 'failed', 'stopped'].includes(x.state)) reveal(x, { type: 'state', actor: owner, summary_fa: `مجوز ${g.ref} لغو شد؛ جلسه متوقف شد`, data: { state: 'stopped' } });
      return json(g);
    }
    if (p === '/workshop/sessions') {
      const b = (await req.json()) as { grant: string; title: string; brief: string; attachments?: string[] };
      const g = grants.find((x) => x.ref === b.grant && !x.revoked_at);
      if (!g) return json({ code: 'grant_not_active', message_fa: 'این مجوز فعال نیست.' }, 409);
      const x: any = {
        id: `s${sessions.length}`, ref: `S-${String(sessions.length + 1).padStart(4, '0')}`, workspace: g.workspace, grant: g.ref, title: b.title, brief: b.brief, opened_by: owner, driver: g.driver ?? owner,
        runtime: 'managed', model: 'claude-sonnet-5-5', effort: 'high', state: 'starting', branch: null, pr_url: null, usage: { usd: 0, input_tokens: 0, output_tokens: 0 },
        created_at: new Date().toISOString(), updated_at: new Date().toISOString(), events: [],
      };
      const who = g.driver ?? owner;
      x.branch = `hq/${x.ref}`;
      x.script = [
        { type: 'state', actor: sys, summary_fa: 'جلسه شروع شد؛ کلون تازه', data: { state: 'working' } },
        { type: 'message', actor: who, summary_fa: `شروع کردم: ${b.title}. اول کد مربوط را میخوانم و اندازه میگیرم.`, data: {} },
        { type: 'command', actor: who, summary_fa: 'نقشه‌ی ریپو خوانده شد', data: { cmd: 'git log --oneline -20 && ls', exit_code: 0, duration_s: 2 } },
        { type: 'progress', actor: who, summary_fa: 'فایل‌های مرتبط پیدا شد؛ در حال نوشتن اصلاح.', data: {} },
      ];
      sessions.unshift(x);
      return json(sessionOut(x), 201);
    }
    const sm = /^\/workshop\/sessions\/(S-\d+)\/(messages|stop|approvals\/([^/]+))$/.exec(p);
    if (sm) {
      const x = sessions.find((y) => y.ref === sm[1]);
      if (!x) return json({ code: 'not_found', message_fa: 'پیدا نشد.' }, 404);
      if (sm[2] === 'stop') { x.script = []; reveal(x, { type: 'state', actor: owner, summary_fa: 'مدیر کل متوقف کرد؛ شاخه میماند', data: { state: 'stopped' } }); return json(sessionOut(x)); }
      if (sm[2] === 'messages') {
        const b = (await req.json()) as { body: string };
        const e = reveal(x, { type: 'message', actor: owner, summary_fa: b.body, data: {} });
        if (!['done', 'failed', 'stopped'].includes(x.state)) x.script.unshift({ type: 'message', actor: x.driver, summary_fa: 'دریافت شد؛ همین را اعمال میکنم و نتیجه را میگویم.', data: {} });
        return json(e, 201);
      }
      const b = (await req.json()) as { allow: boolean; note: string | null };
      const req0 = x.events.find((e: Ev) => e.type === 'approval_request' && e.data.approval_id === sm[3]);
      if (!req0 || x.events.some((e: Ev) => e.type === 'approval_result' && e.data.approval_id === sm[3])) return json({ code: 'conflict', message_fa: 'این درخواست قبلاً جواب گرفته.' }, 409);
      const e = reveal(x, { type: 'approval_result', actor: owner, summary_fa: b.allow ? 'مدیر کل اجازه داد' : 'مدیر کل اجازه نداد', data: { approval_id: sm[3], allow: b.allow, note: b.note } });
      x.state = 'working';
      if (!b.allow) x.script.push({ type: 'message', actor: x.driver, summary_fa: 'باشد؛ دست نگه میدارم. اگر راه دیگری مد نظرت است بگو.', data: {} }, { type: 'state', actor: sys, summary_fa: 'منتظر راهنمایی', data: { state: 'idle' } });
      else if (req0.data.action === 'push_branch') x.script.push(
        { type: 'command', actor: x.driver, summary_fa: `push شد به ${x.branch}`, data: { cmd: `git push origin ${x.branch}`, exit_code: 0, duration_s: 3 } },
        { type: 'approval_request', actor: x.driver, summary_fa: 'اجازه‌ی باز کردن PR', data: { approval_id: `AP-${String(Number(String(sm[3]).slice(3)) + 10).padStart(4, '0')}`, action: 'open_pr', detail: `PR: ${x.branch} → main` } },
      );
      else {
        const w = workspaces.find((y) => y.code === x.workspace)!;
        x.pr_url = `https://github.com/${w.repo}/pull/${40 + sessions.indexOf(x)}`;
        x.script.push({ type: 'progress', actor: x.driver, summary_fa: 'PR باز شد؛ ادغام و انتشار با مُهر تو', data: { pr_url: x.pr_url } }, { type: 'state', actor: sys, summary_fa: 'تمام شد', data: { state: 'done' } });
      }
      return json(e, 201);
    }
    if (p === '/owner/presence') { const b = (await req.json()) as { khalvat: boolean }; presence.khalvat = b.khalvat; presence.since = new Date().toISOString(); return json(presence); }
    if (p === '/control/kill-switch') { const b = (await req.json()) as { scope: string; state: string; reason: string }; const k = b.scope === 'holding' ? control.holding : control.companies.find((c) => c.scope === b.scope); if (k) Object.assign(k, { state: b.state, reason: b.reason, changed_at: new Date().toISOString(), changed_by: 'owner' }); return json(control); }
    return json({}, 200);
  }
  if (p === '/workshop/workspaces') return json(workspaces);
  if (p === '/workshop/grants') return json(u.searchParams.get('active') === 'true' ? grants.filter((g) => !g.revoked_at && g.expires_at > new Date().toISOString()) : grants);
  if (p === '/workshop/sessions') return json(page(sessions.map(sessionOut)));
  const ss = /^\/workshop\/sessions\/(S-\d+)(\/events)?$/.exec(p);
  if (ss) {
    const x = sessions.find((y) => y.ref === ss[1]);
    if (!x) return json({ code: 'not_found', message_fa: 'این جلسه پیدا نشد.' }, 404);
    if (!ss[2]) return json(sessionOut(x));
    const after = Number(u.searchParams.get('after') ?? 0);
    // Live mock: each poll reveals the next scripted step, so a working session visibly moves.
    if (after && x.script.length && Math.random() < 0.8) reveal(x, x.script.shift());
    return json(page(x.events.filter((e: Ev) => e.seq > after)));
  }
  if (p === '/orders') return json(page(orders));
  if (p === '/auth/session') return json({ principal: { kind: 'owner', code: 'owner' }, device: { id: 'dev1', name: 'Chrome · Android', kind: 'session', created_at: iso(600), last_used_at: iso(0), current: true }, expires_at: ahead(60 * 24 * 30) });
  if (p === '/meta') return json({ api_version: '1.4', service_version: 'mock', login_configured: true, public_origin: u.origin, stream_retention_days: 30, channels: { in_app: true, web_push: true, fcm: false, telegram: false }, workshop: { runtime: null }, precedence: [{ rank: 1, kinds: ['owner'], note_fa: 'مدیر کل' }, { rank: 2, kinds: ['overseer', 'advisor'], note_fa: 'ناظر کل و مشاور کل' }, { rank: 3, kinds: ['ceo', 'inspector'], note_fa: 'مدیرعامل‌ها، بازرس کل (QC)' }, { rank: 4, kinds: ['manager'], note_fa: 'مدیرها' }, { rank: 5, kinds: ['employee'], note_fa: 'کارمندها' }] });
  if (p === '/inbox/summary') return json({ decisions_pending: decisions.filter((d) => d.status === 'pending').length, decisions_by_risk: Object.fromEntries(['low', 'medium', 'high'].map((r) => [r, decisions.filter((d) => d.status === 'pending' && d.risk === r).length])), deliverables_unrated: deliverables.filter((d) => !d.rating).length, messages_unread: 3, khalvat: presence.khalvat, notifications: { urgent: 0, decision: 1, report: 0, info: 2, learning: 1 } });
  if (p === '/owner/presence') return json(presence);
  if (p === '/owner/away-summary') return json({ since: iso(60 * 9), until: iso(0), companies: CO.map((c, i) => ({ company: c.code, decisions_new: [1, 1, 1, 1][i], deliverables_new: [1, 1, 1, 0][i], messages_new: [0, 1, 2, 0][i], notifications_new: [1, 1, 0, 1][i] })), decisions: { new: 4, pending: decisions.filter((d) => d.status === 'pending').length, top: decisions.filter((d) => d.status === 'pending').map((d) => ({ ref: d.ref, company: d.company, kind: d.kind, risk: d.risk, status: d.status, title: d.title, created_at: d.created_at })) }, deliverables: { new: 3, unrated: 2, top: deliverables.map((d) => ({ ref: d.ref, company: d.company, title: d.title, created_at: d.created_at })) }, messages: { new: 3, unread: 3, top_threads: threads.map((t) => ({ thread: t.code, company: t.company, new_messages: t.unread, last_at: t.last_message_at })) }, notifications: { by_level: { decision: 1, report: 1, learning: 1 }, held: 2, top: [] } });
  if (p === '/decisions') { const st = u.searchParams.get('status') ?? 'pending'; return json(page(decisions.filter((d) => st === 'all' || d.status === st))); }
  const dd = /^\/decisions\/(D-\d+)$/.exec(p); if (dd) return json(decisions.find((d) => d.ref === dd[1]) ?? {}, decisions.some((d) => d.ref === dd[1]) ? 200 : 404);
  if (p === '/deliverables') return json(page(u.searchParams.get('unrated') === 'true' ? deliverables.filter((d) => !d.rating) : deliverables));
  const od = /^\/deliverables\/(O-\d+)$/.exec(p); if (od) return json(deliverables.find((d) => d.ref === od[1]) ?? {});
  if (p === '/companies') return json(companies);
  const cd = /^\/companies\/([A-Z0-9]+)$/.exec(p); if (cd) return json(companies.find((c) => c.code === cd[1]) ?? {});
  const dep = /^\/companies\/([A-Z0-9]+)\/departments$/.exec(p);
  if (dep && dep[1] === 'HQ') return json([['OVS', 'نظارت و کنترل کیفیت', 'بازرس کل', 'Oversight'], ['AIOPS', 'عملیات هوش مصنوعی', 'مدیر عملیات AI', 'AI Operations']].map(([k, fa, mgr, en], i) => ({ id: `HQ-${k}`, code: k, company: 'HQ', name_fa: fa, name_en: en, manager_title_fa: mgr, manager_title_en: en, manager: { code: `HQ-${k}-MGR`, company: 'HQ', department: k, kind: 'manager', title_fa: mgr }, sort: i, status: 'active', version: 1 })));
  if (dep) return json(['TECH', 'GROWTH', 'SALES', 'PRODUCT', 'FIN', 'QUANT', 'AIOPS', 'HR'].map((k, i) => ({ id: `${dep[1]}-${k}`, code: k, company: dep[1], name_fa: ['فنی', 'رشد و مارکتینگ', 'فروش و پشتیبانی', 'محصول', 'مالی', 'کوانت', 'عملیات هوش مصنوعی', 'منابع انسانی'][i], name_en: k, manager_title_fa: ['مدیر فنی', 'مدیر مارکتینگ', 'مدیر فروش', 'مدیر محصول', 'مدیر مالی', 'مدیر کوانت', 'مدیر عملیات AI', 'مدیر منابع انسانی'][i], manager_title_en: k, manager: { code: `${dep[1]}-${k}-MGR`, company: dep[1], department: k, kind: 'manager', title_fa: 'مدیر' }, sort: i, status: 'active', version: 1 })));
  if (p === '/employees') { const c = u.searchParams.getAll('company'); return json(page(c.length ? employees.filter((e) => c.includes(e.company)) : employees)); }
  const ed = /^\/employees\/([A-Z0-9-]+)$/.exec(p); if (ed) { const e = employees.find((x) => x.code === ed[1]); return e ? json({ ...e, recent_ratings: [{ deliverable: 'O-000031', score: 8, rated_at: iso(60) }], recent_work: work.slice(0, 2).map((w) => ({ ref: w.ref, title: w.title, status: w.status })) }) : json({}, 404); }
  if (p === '/work') return json(page(work));
  const wd = /^\/work\/([^/]+)$/.exec(p); if (wd) { const w = work.find((x) => x.id === wd[1] || x.ref === wd[1]) ?? work[0]; return json({ ...w, chain: [{ id: 'c0', ref: w.ref, depth: 0, status: 'delivered', assignee: { code: `${w.company}-CEO`, company: w.company, kind: 'ceo', title_fa: 'مدیرعامل' }, created_at: iso(300), tokens_used: 6200, usd_used: 0.1 }, { id: 'c1', ref: w.ref, depth: 1, status: w.status, assignee: w.assignee, created_at: iso(280), tokens_used: 41000, usd_used: 0.7 }], children: [] }); }
  if (p.endsWith('/events')) return json(page([]));
  if (p === '/threads') return json(threads);
  const tm = /^\/threads\/([^/]+)\/messages$/.exec(p); if (tm) return json(page(messages[tm[1]!] ?? []));
  if (p === '/notifications') return json({ items: notifications, next_cursor: null });
  if (p === '/control/state') return json(control);
  if (p === '/treasury/summary') return json(summary);
  if (p === '/treasury/breakdown') return json(breakdown(u.searchParams.get('by') ?? 'day'));
  if (p === '/connections') return json(connections);
  if (p === '/audit') return json(page(audit));
  if (p === '/audit/verify') return json({ ok: true, checked: 1200, first_bad_seq: null, verified_at: iso(60 * 6), anchor: 'ok' });
  if (p === '/auth/devices') return json({ items: [{ id: 'dev1', name: 'Chrome · Android', kind: 'passkey', created_at: iso(60 * 20), last_used_at: iso(0), current: true }, { id: 'dev2', name: 'Safari · macOS', kind: 'passkey', created_at: iso(60 * 19), last_used_at: iso(60 * 3) }], next_cursor: null });
  if (p === '/owner/hiring') return json(hiringView());
  if (p === '/stories') return json(rings());
  if (p === '/roles') return json(roles);
  if (p === '/owner/settings') return json({ timezone: 'Asia/Tehran', calendars: ['jalali', 'gregorian'], morning_report_at: '08:00', digest_minutes: 30, ceo_daily_attention: 6, learning_daily_cap: 3, version: 1 });
  const ch = /^\/org\/([A-Z0-9]+)\/chart$/.exec(p);
  if (ch) { const es = employees.filter((e) => e.company === ch[1]); const ceo = es.find((e) => e.kind === 'ceo'); const node = (e: any): any => ({ code: e.code, kind: e.kind, title_fa: e.title_fa, display_name: null, department: e.department, activity: e.activity, status: 'active', children: [] }); return json({ company: ch[1], roots: ceo ? [{ ...node(ceo), children: es.filter((e) => e.kind !== 'ceo').map(node) }] : es.map(node) }); }
  return json({ code: 'not_found', message_fa: 'پیدا نشد.', status: 404, title: 'Not found', type: 'about:blank' }, 404);
}

// Contract §18.11: hiring is closed until the owner opens it; the owner's decision withdrew the pending hire cards.
const hiring = { state: 'closed' as 'closed' | 'open', mode: null as 'delegated' | 'proposals' | null, changed_at: iso(20) as string | null, changed_by: system as typeof system | typeof owner, withdrawn: ['D-000014', 'D-000015', 'D-000016'] };
// Envelopes are company month budgets (§9 /budgets); the demo sets two and leaves one for the owner.
const envelope: Record<string, number | null> = { TY: 6_000_000, FX: 5_000_000, PC: null };
const committed: Record<string, number> = { TY: 2_400_000, FX: 1_900_000, PC: 1_100_000 };
const usedMonth: Record<string, number> = { TY: 3_100_000, FX: 2_200_000, PC: 1_400_000 };
const hiresMonth: Record<string, number> = { TY: 0, FX: 1, PC: 0 };
const hiringView = () => ({ ...hiring, envelopes: CO.filter((c) => c.kind !== 'holding').map((c) => ({ company: c.code, tokens_month: envelope[c.code] ?? null, committed_month: committed[c.code] ?? 0, used_month: usedMonth[c.code] ?? 0, hires_month: hiresMonth[c.code] ?? 0 })) });

// ---------------------------------------------------------------- stories (§18.12) --
const ceoOf = (c: string) => ({ kind: 'agent', code: `${c}-CEO`, display_fa: 'مدیرعامل' });
const stories: any[] = [
  { company: 'TY', kind: 'stars', author: system, at: 60 * 7, title_fa: 'تریدیار، شرکت برتر هفته', body_fa: 'بهترین کارمند هفته تحلیلگر سئوی فنی است. کمترین هزینه‌ی هر خروجی پذیرفته‌شده در هلدینگ هم مال تریدیار بود.', figures: [{ label_fa: 'امتیاز', value: '86' }, { label_fa: 'ستاره', value: '4.3' }, { label_fa: 'کارایی', value: '88' }], links: { period: '2026-10-10' } },
  { company: 'TY', kind: 'deliverable', author: system, at: 60 * 3, title_fa: 'گزارش سئوی فنی، امتیاز ۹ تو', body_fa: '۷ صفحه‌ی بیرون از ایندکس پیدا شد که علتش canonical اشتباه بود؛ ۳ اصلاح فوری انجام شد.', figures: [{ label_fa: 'صفحه', value: '40' }, { label_fa: 'اصلاح فوری', value: '3' }, { label_fa: 'امتیاز تو', value: '9' }], links: { deliverable: 'O-000031' } },
  { company: 'TY', kind: 'post', author: ceoOf('TY'), at: 45, title_fa: 'پنل کاربری سریع‌تر شد', body_fa: 'تیم فنی دو کوئری سنگین داشبورد کاربر را cache کرد و زمان بارگذاری نصف شد.', figures: [{ label_fa: 'قبل', value: '2.4s' }, { label_fa: 'بعد', value: '1.1s' }], links: {} },
  { company: 'FX', kind: 'hire', author: system, at: 60 * 5, title_fa: 'پایشگر سیگنال به تیم کوانت پیوست', body_fa: 'برای پایش دقت سیگنال‌های طلا بعد از خبرهای مهم؛ ارزان‌ترین مدلی که این کار را خوب انجام میدهد.', figures: [{ label_fa: 'مدل', value: 'Haiku 5.5' }, { label_fa: 'effort', value: 'high' }, { label_fa: 'برآورد ماهانه', value: '420K' }], links: { employee: 'FX-QUANT-02' } },
  { company: 'FX', kind: 'milestone', author: ceoOf('FX'), at: 60 * 2, title_fa: 'دقت سیگنال طلا برگشت', body_fa: 'فیلتر رژیم نوسان بعد از خبر فدرال رزرو اضافه شد؛ دقت ۷ روزه دوباره به میانگین رسید.', figures: [{ label_fa: 'قبل', value: '61%' }, { label_fa: 'حالا', value: '68%' }], links: { deliverable: 'O-000029' } },
  { company: 'PC', kind: 'post', author: ceoOf('PC'), at: 60 * 4, seen: true, title_fa: 'ترمینال آماده‌ی انتشار', body_fa: 'نسخه‌ی تازه‌ی ترمینال با canary ۱۰٪ آماده است و در کارتابل تو منتظر مُهر است.', figures: [{ label_fa: 'تست', value: '286' }, { label_fa: 'شکست', value: '0' }], links: { decision: 'D-000017' } },
].map((x, i) => ({ id: `st${i}`, ref: `ST-${String(i + 101).padStart(6, '0')}`, media: null, created_at: iso(x.at), expires_at: iso(x.at - 60 * 24), seen: false, welcomed: false, ...x }));
const rings = () => {
  const by = new Map<string, any[]>();
  for (const x of [...stories].sort((a, b) => a.created_at.localeCompare(b.created_at))) by.set(x.company, [...(by.get(x.company) ?? []), x]);
  return [...by].map(([company, items]) => ({ company, unseen: items.filter((x) => !x.seen).length, latest_at: items.at(-1).created_at, items }))
    .sort((a, b) => Number(b.unseen > 0) - Number(a.unseen > 0) || b.latest_at.localeCompare(a.latest_at));
};


const presence = { khalvat: false, since: iso(60 * 9), until: null as string | null };
