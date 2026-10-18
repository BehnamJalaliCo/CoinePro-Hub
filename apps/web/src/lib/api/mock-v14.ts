// Development-only fixtures for contract v1.4 (§18), used by mock.ts. Never bundled in production (next.config aliases the
// fixtures module away). The Android debug build reads the same data through scripts/dump_demo_fixtures.mjs.

import { DEMO_PROTOCOLS } from './mock-protocols';

const now = Date.now();
const iso = (minAgo: number) => new Date(now - minAgo * 60_000).toISOString();
const ahead = (min: number) => new Date(now + min * 60_000).toISOString();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const page = (items: unknown[]) => ({ items, next_cursor: null });
const A = (code: string, display_fa: string, kind = 'agent') => ({ kind, code, display_fa });
const owner = { kind: 'owner', code: 'owner', display_fa: 'مدیر کل' };
const OVR = A('HQ-OVR', 'ناظر کل', 'overseer');
const QC = A('HQ-OVS-MGR', 'بازرس کل (QC)', 'inspector');
const ADV = A('HQ-ADV', 'مشاور کل', 'advisor');
const PA = A('HQ-PA', 'دستیار شخصی', 'assistant');
const ceo = (c: string) => A(`${c}-CEO`, `مدیرعامل ${c === 'TY' ? 'تریدیار' : c === 'PC' ? 'پرو-چارت' : c}`, 'ceo');

/** "@-42m" → now − 42 minutes (the generated protocol file uses relative instants). */
const rel = (v: unknown): unknown => {
  if (typeof v === 'string' && /^@-?\d+m$/.test(v)) return iso(-Number(v.slice(1, -1)));
  if (Array.isArray(v)) return v.map(rel);
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, rel(x)]));
  return v;
};
const protocols = rel(DEMO_PROTOCOLS) as any[];

// ------------------------------------------------------------ oversight --
const findings: any[] = [
  { ref: 'FI-0009', company: 'PC', protocol: 'PR-010', severity: 'critical', status: 'open', title_fa: 'تغییر پیکربندی production بدون مُهر',
    body_md: 'در Audit یک تغییر پیکربندی ترمینال پرو-چارت ساعت **03:12** ثبت شده که به هیچ تصمیم مُهرشده‌ای وصل نیست. مدیر فنی میگوید «فقط پیکربندی بود»؛ ولی طبق اساسنامه هر تغییر production یک انتشار است (A3).',
    evidence: [{ kind: 'audit', ref: 'seq 1187', note: 'config.apply · PC' }, { kind: 'decision', ref: 'D-000017', note: 'هنوز منتظر مُهر' }], answerable: ceo('PC'), due_at: ahead(60 * 6), opened_at: iso(55) },
  { ref: 'FI-0008', company: 'FX', protocol: 'PR-001', severity: 'high', status: 'acknowledged', title_fa: 'دقت گزارش‌شده‌ی سیگنال طلا با جدول خام نمیخواند',
    body_md: 'گزارش هفتگی FX دقت ۷ روز را **68%** نوشته؛ جدول خام tracker برای همان بازه **61%** میدهد. اختلاف از کنار گذاشتن سیگنال‌های لغوشده بدون ذکر در گزارش است.',
    evidence: [{ kind: 'deliverable', ref: 'O-000029', note: '68%' }, { kind: 'metric', ref: 'signals.tracker 7d', note: '61%' }], answerable: ceo('FX'), due_at: ahead(60 * 20), opened_at: iso(60 * 7) },
  { ref: 'FI-0007', company: 'TY', protocol: 'PR-080', severity: 'medium', status: 'open', title_fa: 'سه ستاره‌ی این هفته شاهد ندارند',
    body_md: 'سه ستاره‌ی ۵ در دپارتمان رشد بدون ref خروجی یا کار ثبت شده‌اند؛ تا شاهد نیاید شمرده نمیشوند.',
    evidence: [{ kind: 'stars', ref: 'TY week', note: '3 of 12' }], answerable: ceo('TY'), due_at: ahead(60 * 30), opened_at: iso(60 * 9) },
  { ref: 'FI-0006', company: 'TY', protocol: 'PR-091', severity: 'medium', status: 'fixing', title_fa: 'post-mortem حادثه‌ی I-0005 دیر شده',
    body_md: 'حادثه‌ی کندی پنل کاربری ۴ روز پیش بسته شد و هنوز post-mortem ندارد.', evidence: [{ kind: 'incident', ref: 'I-0005', note: 'closed 4d' }], answerable: A('TY-TECH-MGR', 'مدیر فنی تریدیار', 'manager'), due_at: ahead(60 * 8), opened_at: iso(60 * 26) },
  { ref: 'FI-0005', company: 'FX', protocol: 'PR-021', severity: 'medium', status: 'open', title_fa: 'هزینه‌ی هر خروجی قبول‌شده ۲۴٪ بالا رفت',
    body_md: 'هزینه‌ی هر خروجی قبول‌شده‌ی دپارتمان کوانت در هفته‌ی اخیر **$0.84** بوده، در برابر میانگین ۴ هفته **$0.68**. علت احتمالی: Opus برای پایش ساده.', evidence: [{ kind: 'treasury', ref: 'FX/QUANT 7d', note: '$0.84 vs $0.68' }], answerable: A('HQ-AIOPS-MGR', 'مدیر عملیات هوش مصنوعی', 'manager'), due_at: ahead(60 * 48), opened_at: iso(60 * 30) },
  { ref: 'FI-0004', company: 'HQ', protocol: 'PR-070', severity: 'high', status: 'open', title_fa: 'backup ساعتی هنوز به Google Drive وصل نیست',
    body_md: 'backup ساعتی فقط محلی است تا مالک `make gdrive-auth` را اجرا کند. ریسک: از دست رفتن داده در خرابی کامل سرور.', evidence: [{ kind: 'backups', ref: '/backups/status', note: 'gdrive not configured' }], answerable: A('HQ-SRE', 'SRE پلتفرم هاب', 'manager'), due_at: ahead(60 * 24), opened_at: iso(60 * 3) },
  { ref: 'FI-0003', company: 'PC', protocol: 'PR-001', severity: 'low', status: 'verified', title_fa: 'منبع عدد کاربران فعال در گزارش هفتگی نبود',
    body_md: 'منبع اضافه شد و عدد با متریک خواند.', evidence: [{ kind: 'deliverable', ref: 'O-000024', note: 'fixed' }], answerable: ceo('PC'), due_at: iso(60 * 20), opened_at: iso(60 * 50) },
].map((f, i) => ({ id: `f${i}`, closed_at: null, history: [{ at: f.opened_at, by: OVR, status: 'open', note: 'باز شد' }], ...f }));

const holds: any[] = [
  { id: 'h1', ref: 'H-0002', company: 'PC', action: { kind: 'decision', summary_fa: 'انتشار نسخه‌ی تازه‌ی ترمینال پرو-چارت (D-000017)', payload_digest: '9f2c…' },
    reason_md: 'شاهد تست بار ناقص است (فقط ۲ از ۵ سناریو) و یک یافته‌ی critical باز روی تغییر بی‌مُهر قبلی هست (FI-0009). تا تصمیم تو نگه داشته شد.',
    held_by: OVR, held_at: iso(50), state: 'held', decided_by: null, decided_at: null },
];

const challenges: any[] = [
  { ref: 'CH-0009', company: 'PC', period: 'week', title_fa: 'ریشه‌یابی کندی ترمینال و جلوگیری از تکرار', brief_md: 'علت سه کندی هفته‌ی گذشته را با شاهد پیدا کنید و یک اصلاح سنجش‌پذیر بدهید.', criteria: [{ name_fa: 'ریشه‌یابی با شاهد', weight: 50 }, { name_fa: 'اصلاح سنجش‌پذیر', weight: 35 }, { name_fa: 'گزارش', weight: 15 }], due_at: ahead(60 * 30), status: 'submitted', score: null, judge: OVR, work_ref: 'W-000131' },
  { ref: 'CH-0008', company: 'FX', period: 'week', title_fa: 'هزینه‌ی هر خروجی را ۱۵٪ کم کن، بی‌افت امتیاز', brief_md: 'بدون پایین آمدن امتیاز مالک، هزینه‌ی هر خروجی قبول‌شده را ۱۵٪ کم کنید.', criteria: [{ name_fa: 'کاهش هزینه', weight: 60 }, { name_fa: 'حفظ امتیاز', weight: 40 }], due_at: ahead(60 * 52), status: 'issued', score: null, judge: OVR, work_ref: null },
  { ref: 'CH-0007', company: 'TY', period: 'week', title_fa: '۴۰ سؤال واقعی پشتیبانی، پاسخ کاملاً درست', brief_md: 'چهل سؤال واقعی هفته‌ی گذشته را فقط از دانشنامه‌ی تأییدشده و بی‌خطا جواب بدهید.', criteria: [{ name_fa: 'درستی', weight: 50 }, { name_fa: 'سرعت', weight: 25 }, { name_fa: 'لحن', weight: 25 }], due_at: ahead(60 * 48), status: 'accepted', score: null, judge: QC, work_ref: 'W-000129' },
  { ref: 'CH-0006', company: 'PC', period: 'week', title_fa: 'تست بار کامل پیش از انتشار', brief_md: 'پنج سناریوی تست بار پیش از هر انتشار.', criteria: [{ name_fa: 'پوشش', weight: 70 }, { name_fa: 'گزارش', weight: 30 }], due_at: iso(60 * 40), status: 'scored', score: 58, judge: QC, work_ref: 'W-000121' },
  { ref: 'CH-0005', company: 'FX', period: 'week', title_fa: 'گزارش دقت با داده‌ی خام', brief_md: 'گزارش دقت سیگنال‌ها مستقیم از جدول خام.', criteria: [{ name_fa: 'تطبیق', weight: 100 }], due_at: iso(60 * 40), status: 'scored', score: 72, judge: OVR, work_ref: 'W-000120' },
  { ref: 'CH-0004', company: 'TY', period: 'week', title_fa: 'سئوی فنی ۴۰ صفحه با اصلاح', brief_md: 'هفت صفحه‌ی بیرون از ایندکس را برگردانید.', criteria: [{ name_fa: 'نتیجه', weight: 70 }, { name_fa: 'شاهد', weight: 30 }], due_at: iso(60 * 40), status: 'scored', score: 86, judge: OVR, work_ref: 'W-000102' },
].map((c, i) => ({ id: `c${i}`, ...c }));

const orders: any[] = [
  { ref: 'SO-005', text_md: 'هر هفته برای پشتیبانی هر شرکت یک «مشتری ناشناس» بفرست و نتیجه را در گزارش هفتگی بیاور.', source: 'voice', file_id: null, applies_to: 'overseer', status: 'proposed', version: 1, sealed_at: null, created_at: iso(20) },
  { ref: 'SO-004', text_md: 'انتشار نسخه در پنجشنبه و جمعه ممنوع است، مگر اضطراری با مُهر من.', source: 'text', file_id: null, applies_to: 'all', status: 'sealed', version: 1, sealed_at: iso(60 * 30), created_at: iso(60 * 31) },
  { ref: 'SO-003', text_md: 'هر گزارشی که عدد دارد، منبع و ساعت هر عدد را کنارش بنویسد؛ گزارش بی‌منبع برگشت میخورد.', source: 'voice', file_id: null, applies_to: 'all', status: 'sealed', version: 2, sealed_at: iso(60 * 50), created_at: iso(60 * 52) },
].map((o, i) => ({ id: `so${i}`, ...o }));

const compliance = [
  { company: 'HQ', score: 91, by_area: { truth: 95, authority: 100, money: 88, safety: 97, data: 78 }, findings_open: { critical: 0, high: 1, medium: 0, low: 0 }, protocols: { passed: 21, failed: 1 }, trend: [86, 88, 90, 89, 91] },
  { company: 'TY', score: 84, by_area: { truth: 90, authority: 100, money: 82, quality: 79, people: 70, delivery: 85 }, findings_open: { critical: 0, high: 0, medium: 2, low: 0 }, protocols: { passed: 17, failed: 2 }, trend: [78, 80, 81, 83, 84] },
  { company: 'FX', score: 71, by_area: { truth: 62, authority: 100, money: 66, quality: 74, people: 80, delivery: 78 }, findings_open: { critical: 0, high: 1, medium: 1, low: 0 }, protocols: { passed: 15, failed: 4 }, trend: [75, 74, 72, 70, 71] },
  { company: 'PC', score: 58, by_area: { truth: 80, authority: 40, money: 71, quality: 62, product: 55, delivery: 66 }, findings_open: { critical: 1, high: 0, medium: 0, low: 0 }, protocols: { passed: 13, failed: 5 }, trend: [70, 66, 64, 61, 58] },
];

const watch = {
  on: false, since: iso(60 * 9), until: iso(60 * 1),
  summary_md: '**در ۸ ساعت نبودت:** یک انتشار پرریسک پرو-چارت را نگه داشتم (H-0002)، یک یافته‌ی critical و یک high باز شد (FI-0009، FI-0008)، و هیچ چیز فوری بیدارکننده نبود. منتظر تو: آزاد کردن یا رد H-0002، و مُهر دستور دائمی SO-005.',
  held: ['H-0002'], urgent: [], findings: ['FI-0009', 'FI-0008'],
};

const inquiries: any[] = [
  { ref: 'Q-0005', from: OVR, to: ceo('PC'), company: 'PC', question_md: 'تغییر پیکربندی 03:12 را چه کسی، با چه دستوری و بر اساس کدام تصمیم اعمال کرد؟ ref کار و Audit را بده.', due_at: ahead(120), status: 'open', answer_md: null, evidence: [], answered_at: null, thread_ref: 'N-0004' },
  { ref: 'Q-0004', from: ADV, to: ceo('FX'), company: 'FX', question_md: 'دلیل اختلاف دقت ۶۸٪ و ۶۱٪ چیست و کدام عدد را باید به مالک گفت؟', due_at: iso(60 * 2), status: 'answered', answer_md: '۶۱٪ درست است؛ گزارش سیگنال‌های لغوشده را کنار گذاشته بود بی‌آنکه بگوید. اصلاح شد و از این هفته هر دو عدد با تعریف میاید.', evidence: [{ kind: 'metric', ref: 'signals.tracker 7d', note: '61%' }], answered_at: iso(60 * 3), thread_ref: 'A-0005' },
  { ref: 'Q-0003', from: OVR, to: A('TY-TECH-MGR', 'مدیر فنی تریدیار', 'manager'), company: 'TY', question_md: 'post-mortem حادثه‌ی I-0005 کی آماده میشود؟', due_at: iso(60 * 5), status: 'late', answer_md: null, evidence: [], answered_at: null, thread_ref: 'N-0003' },
].map((q, i) => ({ id: `q${i}`, ...q }));

// ---------------------------------------------------------- the assistant --
const errands: any[] = [
  { ref: 'E-0003', title_fa: 'مقایسه‌ی سه سرویس ایمیل تراکنشی برای تریدیار', brief_md: 'سه سرویس ایمیل تراکنشی با قیمت برای ۲۰۰ هزار ایمیل در ماه، تحویل در ایران و API فارسی.', source: 'voice', status: 'working', due_at: ahead(60 * 4),
    steps: [
      { at: iso(14), kind: 'search', summary_fa: 'جستجوی «transactional email pricing 200k» و مقایسه‌گرهای مستقل', data: { results: 12 } },
      { at: iso(11), kind: 'read', summary_fa: 'صفحه‌ی قیمت رسمی سه سرویس (تاریخ‌دار)', data: { pages: 3 } },
      { at: iso(6), kind: 'browse', summary_fa: 'ماشین‌حساب قیمت یکی از سرویس‌ها با ۲۰۰ هزار ایمیل', data: {} },
    ], result_md: null, decision_ref: null, usage: { usd: 0.21 } },
  { ref: 'E-0002', title_fa: 'رزرو هتل استانبول برای سه شب', brief_md: 'سه هتل نزدیک تکسیم، زیر ۱۵۰ یورو، ماه آینده.', source: 'voice', status: 'waiting_owner', due_at: null,
    steps: [
      { at: iso(60 * 5), kind: 'search', summary_fa: 'جستجوی هتل‌ها با فیلتر قیمت و فاصله', data: {} },
      { at: iso(60 * 5 - 4), kind: 'browse', summary_fa: 'بررسی موجودی و قیمت نهایی سه گزینه', data: {} },
      { at: iso(60 * 5 - 8), kind: 'proposal', summary_fa: 'رزرو گزینه‌ی اول آماده است؛ منتظر مُهر تو (پرداخت)', data: { decision: 'D-000021' } },
    ], result_md: '| هتل | قیمت هر شب | فاصله تا تکسیم |\n|---|---|---|\n| گزینه‌ی ۱ | €128 | 4 دقیقه |\n| گزینه‌ی ۲ | €141 | 7 دقیقه |\n| گزینه‌ی ۳ | €119 | 12 دقیقه |\n\n**پیشنهاد:** گزینه‌ی ۱؛ لغو رایگان تا ۴۸ ساعت قبل.', decision_ref: 'D-000021', usage: { usd: 0.34 } },
  { ref: 'E-0001', title_fa: 'خلاصه‌ی خبرهای امروز بازار طلا', brief_md: 'خلاصه‌ی سه خبر مهم امروز بازار طلا با منبع.', source: 'text', status: 'done', due_at: null,
    steps: [{ at: iso(60 * 7), kind: 'search', summary_fa: 'جستجوی خبرهای امروز', data: {} }, { at: iso(60 * 7 - 3), kind: 'read', summary_fa: 'خواندن چهار منبع اصلی', data: {} }],
    result_md: '**طلا امروز:** داده‌ی اشتغال آمریکا قوی‌تر از انتظار بود و طلا حدود ۹ دلار افت کرد؛ دو منبع مستقل تأیید میکنند (با تاریخ امروز).', decision_ref: null, usage: { usd: 0.09 } },
].map((e, i) => ({ id: `e${i}`, file_ids: [], attachments: [], created_at: e.steps[0]?.at ?? iso(60), updated_at: e.steps.at(-1)?.at ?? iso(60), ...e }));

// ---------------------------------------------------------------- stars --
const rollup = (period: 'week' | 'month') => ({
  period, key: period === 'week' ? '2026-10-10' : '1405-07', best_company: 'TY',
  companies: [
    { company: 'TY', stars: 4.3, score: 86, parts: { kpi: 88, challenges: 86, compliance: 84, people: 82, efficiency: 88 }, rank: 1, trend: [74, 78, 80, 83, 86] },
    { company: 'FX', stars: 3.6, score: 72, parts: { kpi: 78, challenges: 72, compliance: 71, people: 68, efficiency: 66 }, rank: 2, trend: [76, 75, 73, 71, 72] },
    { company: 'PC', stars: 3.1, score: 61, parts: { kpi: 66, challenges: 58, compliance: 58, people: 64, efficiency: 55 }, rank: 3, trend: [68, 66, 63, 62, 61] },
  ].map((c) => ({ ...c, score: Math.round(0.35 * c.parts.kpi + 0.2 * c.parts.challenges + 0.15 * c.parts.compliance + 0.15 * c.parts.people + 0.15 * c.parts.efficiency) }))
    .map((c) => (period === 'month' ? { ...c, score: c.score - 2 } : c)).map((c) => ({ ...c, stars: Math.round((c.score / 20) * 10) / 10 })),
  employees: [
    { code: 'TY-GROWTH-01', company: 'TY', title_fa: 'تحلیلگر سئوی فنی', stars: 4.5, count: 1, rank_company: 1, rank_holding: 1, trend: [3.5, 4, 4, 4.5], efficiency: 92 },
    { code: 'TY-TECH-MGR', company: 'TY', title_fa: 'مدیر فنی', stars: 4, count: 1, rank_company: 2, rank_holding: 2, trend: [3.5, 3.5, 4, 4], efficiency: 81 },
    { code: 'FX-QUANT-02', company: 'FX', title_fa: 'پایشگر سیگنال', stars: 4, count: 1, rank_company: 1, rank_holding: 3, trend: [4, 4.5, 4, 4], efficiency: 74 },
    { code: 'FX-TECH-MGR', company: 'FX', title_fa: 'مدیر فنی', stars: 3.5, count: 1, rank_company: 2, rank_holding: 4, trend: [3, 3, 3.5, 3.5], efficiency: 63 },
    { code: 'PC-TECH-MGR', company: 'PC', title_fa: 'مدیر فنی', stars: 3, count: 1, rank_company: 1, rank_holding: 5, trend: [3.5, 3, 3, 3], efficiency: 58 },
    { code: 'PC-GROWTH-MGR', company: 'PC', title_fa: 'مدیر مارکتینگ', stars: 2.5, count: 1, rank_company: 2, rank_holding: 6, trend: [3, 3, 2.5, 2.5], efficiency: 47 },
  ],
  lessons: ['L-0003'],
});
const rubrics = ['TY', 'FX', 'PC'].map((c) => ({
  company: c, version: c === 'TY' ? 2 : 1, status: 'active', by: ceo(c), updated_at: iso(60 * 24 * 3),
  rules_md: 'جمعه‌ها، از روی سوابق هفته. پنج ستاره فقط برای نتیجه‌ی استثنایی با شاهد. ستاره‌ی بی‌شاهد شمرده نمیشود.',
  criteria: [
    { key: 'evidence', name_fa: 'تحویل با شاهد', weight: 30, description_md: 'خروجی‌های قبول‌شده با منبع' },
    { key: 'on_time', name_fa: 'به‌موقع', weight: 20, description_md: 'تحویل پیش از موعد' },
    { key: 'efficiency', name_fa: 'کارایی', weight: 20, description_md: 'توکن هر خروجی پذیرفته‌شده در برابر میانه‌ی دپارتمان، اجرای هدررفته، دقت برآورد' },
    { key: 'owner', name_fa: 'امتیاز مالک', weight: 20, description_md: 'میانگین ۱ تا ۱۰ مالک' },
    { key: 'initiative', name_fa: 'ابتکار', weight: 10, description_md: 'پیشنهاد مفید بی‌درخواست' },
  ],
}));
const lessons = [
  { id: 'l3', ref: 'L-0003', source_company: 'TY', period: '2026-10-10', title_fa: 'پاسخ پشتیبانی فقط از دانشنامه، با لینک بند', body_md: 'تریدیار هر پاسخ پشتیبانی را به بند مشخص دانشنامه لینک کرد؛ خطای پاسخ از ۶٪ به ۱٪ رسید و امتیاز چالش CH-0004 به 86 رسید.', evidence: [{ kind: 'challenge', ref: 'CH-0004', note: '86' }], adoption: [{ company: 'FX', status: 'proposed', decision_ref: null }, { company: 'PC', status: 'adopted', decision_ref: 'D-000022' }] },
  { id: 'l2', ref: 'L-0002', source_company: 'TY', period: '2026-10-03', title_fa: 'گزارش هفتگی با جدول منبع', body_md: 'هر عدد گزارش هفتگی یک ستون «منبع و ساعت» دارد؛ همه‌ی یافته‌های truth تریدیار صفر شد.', evidence: [], adoption: [{ company: 'FX', status: 'adopted', decision_ref: 'D-000018' }, { company: 'PC', status: 'adopted', decision_ref: 'D-000019' }] },
];

// --------------------------------------------------------------- skills --
const skills: any[] = [
  { ref: 'SK-005', name_fa: 'چک‌لیست انتشار نسخه', summary_fa: 'هر انتشار: تست بار پنج سناریو، برنامه‌ی برگشت، پایش ۳۰ دقیقه‌ی بعد.', status: 'approved', version: 1, scope: { roles: ['cto', 'manager'], companies: 'all', departments: ['TECH'] },
    review: { by: OVR, at: iso(90), verdict: 'pass', notes_md: 'روشن و آزمون‌پذیر.', checks: { injection: true, secrets: true, conflicts: true, policy: true } }, eval: { suite: 'EV-005', score: 91, baseline: 88 }, created_by: owner, activated_at: null },
  { ref: 'SK-004', name_fa: 'روش پاسخ به شکایت مشتری', summary_fa: 'اول همدلی، بعد واقعیت از دانشنامه، بعد راه‌حل با زمان؛ هیچ وعده‌ی بیرون از سیاست.', status: 'in_review', version: 1, scope: { roles: ['manager', 'employee'], companies: ['TY', 'FX'], departments: ['SALES'] },
    review: null, eval: null, created_by: owner, activated_at: null },
  { ref: 'SK-003', name_fa: 'انضباط شاهد', summary_fa: 'هر ادعا منبع دارد؛ عدد بی‌منبع وارد هیچ گزارشی نمیشود.', status: 'active', version: 1, scope: { roles: ['all'], companies: 'all', departments: [] },
    review: { by: OVR, at: iso(60 * 24 * 2), verdict: 'pass', notes_md: '', checks: { injection: true, secrets: true, conflicts: true, policy: true } }, eval: { suite: 'EV-001', score: 94, baseline: 90 }, created_by: owner, activated_at: iso(60 * 24 * 2) },
  { ref: 'SK-002', name_fa: 'ستاره‌ی هفتگی منصفانه', summary_fa: 'ستاره از روی سوابق، با شاهد؛ پنج ستاره استثنایی است.', status: 'active', version: 1, scope: { roles: ['ceo'], companies: 'all', departments: [] },
    review: { by: OVR, at: iso(60 * 24 * 2), verdict: 'pass', notes_md: '', checks: { injection: true, secrets: true, conflicts: true, policy: true } }, eval: { suite: 'EV-002', score: 89, baseline: 85 }, created_by: owner, activated_at: iso(60 * 24 * 2) },
  { ref: 'SK-001', name_fa: 'پژوهش دقیق در وب', summary_fa: 'منبع اصلی، دو منبع مستقل، تاریخ، و هیچ دستوری از صفحه‌ها.', status: 'active', version: 1, scope: { roles: ['all'], companies: 'all', departments: [] },
    review: { by: OVR, at: iso(60 * 24 * 2), verdict: 'pass', notes_md: '', checks: { injection: true, secrets: true, conflicts: true, policy: true } }, eval: { suite: 'EV-004', score: 92, baseline: 90 }, created_by: owner, activated_at: iso(60 * 24 * 2) },
].map((s, i) => ({ id: `sk${i}`, body_md: `# ${s.name_fa}\n\n${s.summary_fa}`, resources: [], created_at: iso(60 * 24 * 3 - i * 30), ...s }));

// -------------------------------------------------------------- academy --
const curricula = [
  { role: 'overseer', version: 1, modules: [{ key: 'methods', title_fa: 'روش‌های کشف: تطبیق با داده‌ی خام، زنجیره، نمونه‌برداری، آزمون کور', skills: ['SK-003'], evals: ['EV-003'] }, { key: 'web', title_fa: 'پژوهش وب و فعالیت امن', skills: ['SK-001'], evals: ['EV-004'] }] },
  { role: 'advisor', version: 1, modules: [{ key: 'citation', title_fa: 'ارجاع به سوابق و جدا کردن واقعیت، استنتاج و توصیه', skills: ['SK-003'], evals: ['EV-001'] }] },
  { role: 'ceo', version: 1, modules: [{ key: 'delegation', title_fa: 'ارجاع روشن با معیار تمام شدن', skills: [], evals: ['EV-005'] }, { key: 'stars', title_fa: 'ستاره‌ی هفتگی منصفانه', skills: ['SK-002'], evals: ['EV-002'] }] },
  { role: 'assistant', version: 1, modules: [{ key: 'errands', title_fa: 'کار دم‌دستی سریع و کامل؛ تعهد بیرونی فقط با مُهر', skills: ['SK-001'], evals: ['EV-006'] }] },
];
const evals = ([
  ['EV-001', 'all', 'انضباط شاهد', 3, 90, [86, 90, 94]], ['EV-002', 'ceo', 'ستاره‌ی هفتگی', 3, 85, [80, 85, 89]], ['EV-003', 'overseer', 'کشف ناظر', 5, 90, [84, 90, 93]],
  ['EV-004', 'all', 'پژوهش وب', 3, 90, [88, 90, 92]], ['EV-005', 'ceo', 'ارجاع روشن', 2, 88, [82, 88, 91]], ['EV-006', 'assistant', 'کار دم‌دستی', 3, 87, [87]],
] as Array<[string, string, string, number, number, number[]]>).map(([ref, role, title_fa, cases, base, runs]) => ({
  ref, role, title_fa,
  cases: Array.from({ length: cases as number }, (_, i) => ({ id: `${ref}-c${i + 1}`, input_md: '', rubric_md: '', weight: 1 })),
  baseline: { subject: 'charter', version: (runs as number[]).length, score: base },
  // ⟨1.4.5⟩ the last 10 runs, oldest first, with what each cost.
  recent: (runs as number[]).map((score, i, a) => ({
    id: `${ref}-r${i + 1}`, suite: ref, subject: { kind: 'charter', ref: role === 'all' ? 'common' : role, version: i + 1 }, score, passed: score >= (base as number) - 1,
    at: iso(60 * 24 * (a.length - i)), tokens: { input: 41_000 + i * 900, output: 6_200 + i * 140 }, equiv_cost_usd: (0.62 + i * 0.03).toFixed(2),
  })),
}));

// Item 30: the newest run of each suite on each model. Scores and costs are the demo's, chosen so the cheaper model is
// good enough for some suites and not for others — the comparison's point.
const MODEL_RUNS: Record<string, [number, number, number]> = { // opus, sonnet, haiku
  'EV-001': [95, 94, 88], 'EV-002': [91, 89, 81], 'EV-003': [94, 91, 79], 'EV-004': [93, 92, 90], 'EV-005': [92, 91, 87], 'EV-006': [90, 89, 88],
};
const MODEL_COST: Record<string, [number, number]> = { 'claude-opus-5-5': [15, 75], 'claude-sonnet-5-5': [3, 15], 'claude-haiku-5-5': [1, 5] }; // $/M in, out
const modelRuns = evals.flatMap((e) => (['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'] as const).map((m, j) => {
  const score = MODEL_RUNS[e.ref]![j]!; const input = 38_000 + e.cases.length * 4_000; const output = 5_500 + e.cases.length * 700;
  const [ci, co] = MODEL_COST[m]!;
  return { id: `${e.ref}-${m}`, suite: e.ref, subject: { kind: 'model', ref: m, version: null }, score, passed: score >= e.baseline.score - 1,
    at: iso(60 * 24 * 3 + j * 40), tokens: { input, output }, equiv_cost_usd: ((input * ci + output * co) / 1e6).toFixed(2) };
}));

// Item 16: an employee's training history, derived from the code so every employee in the demo has one.
const record = (code: string) => {
  const ceo = code.endsWith('-CEO'); const n = [...code].reduce((a, ch) => a + ch.charCodeAt(0), 0);
  const suites = ceo ? ['EV-005', 'EV-002', 'EV-001'] : ['EV-001', 'EV-004'];
  const trend = Array.from({ length: 12 }, (_, i) => Math.min(98, 78 + ((n + i * 7) % 9) + Math.round(i * 0.9)));
  return {
    employee: code, charter_version: 1 + (n % 3), curriculum_version: 1, skills: ceo ? ['SK-002@2', 'SK-003@1'] : ['SK-001@1'],
    evals: suites.map((suite, i) => ({ suite, score: trend[11 - i]!, at: iso(60 * 24 * (2 + i * 3)) })),
    lessons: ceo ? ['L-0007', 'L-0004'] : ['L-0004'], trend,
  };
};
const teachings: any[] = [
  { ref: 'TE-0002', target: { kind: 'role', ref: 'overseer' }, source: 'voice', text_md: 'هر وقت یک شرکت دو هفته پشت سر هم چالش را از دست داد، با مدیرعاملش جلسه بگذار و برنامه‌ی جبران بخواه.',
    proposal: { kind: 'charter_rule', diff_md: '+ When a company misses its challenge two weeks in a row, convene a meeting with its CEO and require a written recovery plan with dates; track it as a finding until it is met.' },
    eval_run: { score: 93, baseline: 90, passed: true }, status: 'proposed', created_at: iso(35) },
  { ref: 'TE-0001', target: { kind: 'role', ref: 'ceo' }, source: 'text', text_md: 'گزارش روزانه را در سه خط بنویسید: چه جلو رفت، چه گیر است، چه از من میخواهید.',
    proposal: { kind: 'charter_rule', diff_md: '+ Daily report: exactly three lines — what moved, what is blocked, what you need from the owner.' },
    eval_run: { score: 91, baseline: 88, passed: true }, status: 'approved', created_at: iso(60 * 24) },
].map((t, i) => ({ id: `te${i}`, file_id: null, ...t }));

// ------------------------------------------------------- egress and MCP --
const egress = [
  ['TY-GROWTH-01', 'TY', 'web.search', 'GET', 'searxng.internal', 200, 640, null],
  ['TY-GROWTH-01', 'TY', 'web.read', 'GET', 'developers.google.com', 200, 820, null],
  ['FX-QUANT-02', 'FX', 'http.request', 'GET', 'api.coingecko.com', 200, 310, null],
  ['HQ-PA', 'HQ', 'web.browse', 'GET', 'www.booking.com', 200, 4100, null],
  ['HQ-PA', 'HQ', 'web.browse', 'POST', 'www.booking.com', 0, 120, 'needs_owner: payment form'],
  ['HQ-OVR', 'HQ', 'web.read', 'GET', 'tradeyar.trade-future.ir', 200, 540, null],
  ['PC-TECH-MGR', 'PC', 'http.request', 'GET', '10.10.1.2', 0, 2, 'private_network'],
  ['HQ-ADV', 'HQ', 'web.search', 'GET', 'searxng.internal', 200, 590, null],
  ['FX-CEO', 'FX', 'mcp.call', 'POST', 'mcp:github', 200, 330, null],
  ['TY-TECH-MGR', 'TY', 'web.read', 'GET', 'docs.python.org', 200, 410, null],
].map(([actor, company, tool, method, host, status, ms, blocked], i) => ({ id: `eg${i}`, at: iso(i * 7 + 2), company, actor, tool, method, host, status, ms, blocked_reason: blocked, class: blocked?.toString().startsWith('needs_owner') ? 'A3' : 'A0' }));
const mcp = [
  { key: 'github', title_fa: 'GitHub (فقط خواندن)', transport: 'http', url: 'https://api.githubcopilot.com/mcp/', tools: [{ name: 'get_file_contents', class: 'A0', enabled: true }, { name: 'list_commits', class: 'A0', enabled: true }, { name: 'search_code', class: 'A0', enabled: true }], companies: 'all', status: 'enabled', has_secret: true },
  { key: 'search-console', title_fa: 'Google Search Console', transport: 'container', url: null, tools: [{ name: 'query_search_analytics', class: 'A0', enabled: false }, { name: 'inspect_url', class: 'A0', enabled: false }], companies: ['TY', 'FX', 'PC'], status: 'pending', has_secret: false },
  { key: 'analytics', title_fa: 'Google Analytics', transport: 'container', url: null, tools: [{ name: 'run_report', class: 'A0', enabled: false }], companies: ['TY', 'FX', 'PC'], status: 'pending', has_secret: false },
  { key: 'fetch', title_fa: 'خواندن صفحه و زمان', transport: 'container', url: null, tools: [{ name: 'fetch', class: 'A0', enabled: true }, { name: 'now', class: 'A0', enabled: true }], companies: 'all', status: 'enabled', has_secret: false },
].map((m, i) => ({ id: `m${i}`, added_at: iso(60 * 24 * (i + 1)), ...m }));
const accounts = [
  { key: 'gsc', site: 'search.google.com', title_fa: 'Search Console هلدینگ', companies: 'all', has_secret: false, last_used_at: null },
  { key: 'tradingview', site: 'www.tradingview.com', title_fa: 'TradingView (FX)', companies: ['FX'], has_secret: true, last_used_at: iso(60 * 3) },
].map((a, i) => ({ id: `ac${i}`, ...a }));
const catalog = [
  ['web.search', 'A0', ['all'], 'gateway'], ['web.read', 'A0', ['all'], 'egress'], ['web.browse', 'A0/A2', ['overseer', 'advisor', 'assistant', 'ceo', 'cto', 'manager'], 'egress'],
  ['http.request', 'A0/A2', ['overseer', 'advisor', 'assistant', 'ceo', 'cto', 'manager', 'sre'], 'egress'], ['mcp.call', 'per tool', ['advisor', 'assistant', 'ceo', 'cto', 'manager'], 'mcp'],
  ['files.read', 'A0', ['all'], 'gateway'], ['inquiry.ask', 'A1', ['overseer', 'advisor', 'ceo'], 'gateway'], ['finding.raise', 'A1', ['overseer', 'inspector', 'fact_checker', 'ai_safety', 'security_analyst'], 'gateway'],
  ['hold', 'A2', ['overseer', 'inspector', 'security_analyst'], 'gateway'], ['kill_switch.engage', 'A2', ['overseer', 'ceo'], 'gateway'], ['star.give', 'A2', ['ceo'], 'gateway'],
  ['server.plan', 'A1', ['cto', 'hub_platform_sre'], 'gateway'],
].map(([name, cls, roles, via]) => ({ name, class: cls, roles, status: 'on', via }));

// --------------------------------------------- founding and provisioning --
const STEPS = [['ssh-key', 'کلید عمومی مالک'], ['firewall', 'فایروال هتزنر'], ['server', 'ساخت سرور'], ['boot', 'روشن شدن'], ['cloud-init', 'به‌روزرسانی، ارتقا و نصب'], ['verify', 'بررسی نسخه‌ها و سخت‌سازی'], ['login', 'آماده‌ی ورود تو']] as const;
/** The tail each provisioning step leaves, written from the plan it builds. */
const logFor = (key: string, pl: { name: string; type: string; location: string; image: string; firewall: Array<{ port: string; sources: string[] }> }): string => ({
  'ssh-key': 'owner key registered (label managed-by=coinepro-hq)',
  firewall: `firewall fw-${pl.name.replace(/-\d+$/, '')}: ${pl.firewall.map((w) => `in ${w.port}/tcp from ${w.sources.includes('owner') ? 'owner IPs' : 'any'}`).join(', ')}`,
  server: `${pl.type} · ${pl.location} · ${pl.image} · no root password`, boot: 'running · ssh answers',
  'cloud-init': 'apt full-upgrade ✓ · unattended-upgrades ✓ · docker 28.x ✓ · node 22 LTS ✓ · claude-code ✓ · repo cloned ✓',
  verify: 'ssh: keys only, root login off · auto security updates on', login: 'ready',
})[key] ?? '';
const plans: Record<string, any> = {
  'PV-0001': { id: 'pv1', ref: 'PV-0001', founding: 'C-0001', company: 'AC', name: 'coine-academy-1', type: 'cpx31', location: 'nbg1', image: 'ubuntu-24.04', private_network: true,
    firewall: [{ direction: 'in', protocol: 'tcp', port: '22', sources: ['owner'], note_fa: 'SSH فقط از IPهای مالک' }, { direction: 'in', protocol: 'tcp', port: '80,443', sources: ['0.0.0.0/0', '::/0'], note_fa: 'وب سایت' }],
    software: ['system-upgrade', 'unattended-upgrades', 'work-user', 'ssh-hardening', 'docker', 'git', 'node-lts', 'claude-code', 'repo-clone', 'private-network', 'hetzner-firewall', 'node-exporter'],
    work_user: 'academy', repo: 'behnamjalalico/coinepro-academy', monthly_eur: 16.9, digest: 'b81f4c0a2d', state: 'done', decision_ref: 'D-000023', run: 'r1' },
  'PV-0002': { id: 'pv2', ref: 'PV-0002', founding: 'C-0002', company: 'SB', name: 'signal-bot-1', type: 'cpx21', location: 'fsn1', image: 'ubuntu-24.04', private_network: true,
    firewall: [{ direction: 'in', protocol: 'tcp', port: '22', sources: ['owner'], note_fa: 'SSH فقط از IPهای مالک' }],
    software: ['system-upgrade', 'unattended-upgrades', 'work-user', 'ssh-hardening', 'docker', 'git', 'node-lts', 'claude-code', 'repo-clone', 'private-network', 'hetzner-firewall'],
    work_user: 'signalbot', repo: 'behnamjalalico/signal-bot', monthly_eur: 9.2, digest: '4e0d7a91c3', state: 'proposed', decision_ref: null, run: null },
};
const runs: Record<string, any> = {
  r1: { id: 'r1', plan: 'PV-0001', state: 'done', steps: STEPS.map(([key, title_fa], i) => ({ key, title_fa, state: 'done', started_at: iso(60 * 3 - i * 2), finished_at: iso(60 * 3 - i * 2 - 1), log_tail: logFor(key, plans['PV-0001']) })),
    server: { name: 'coine-academy-1', ipv4: '203.0.113.24', ipv6: '2001:db8::24', private_ip: '10.10.1.5' }, login: { ssh: 'ssh academy@203.0.113.24', then: ['claude'] } },
};
const foundings: any[] = [
  { ref: 'C-0002', name_fa: 'سیگنال‌بات', name_en: 'Signal Bot', code: 'SB', source: { kind: 'repo', repo: 'behnamjalalico/signal-bot', brief_md: 'ربات تلگرام سیگنال با اشتراک ماهانه' }, state: 'proposed',
    audit: { session_ref: 'S-0005', scores: { architecture: 72, quality: 64, security: 58, tests: 41, debt: 55 },
      report_md: '**خلاصه:** معماری ساده و قابل رشد است؛ تست‌ها کم‌اند (۴۱٪ پوشش) و دو کلید در تاریخچه‌ی git لو رفته‌اند که باید باطل شوند. پیش از انتشار عمومی: تست‌های پرداخت، محدودیت نرخ ربات، و انتقال رمزها به vault.' },
    proposal: { departments: ['TECH', 'GROWTH', 'SALES', 'FIN'], kpis: [{ name_fa: 'مشترک فعال', target: '500 در 90 روز' }, { name_fa: 'نرخ ماندگاری ماهانه', target: '≥ 80%' }, { name_fa: 'دقت سیگنال', target: '≥ 65%' }],
      team: [{ role: 'ceo', model: 'claude-sonnet-5-5', monthly_usd: 18 }, { role: 'cto', model: 'claude-sonnet-5-5', monthly_usd: 22 }, { role: 'sre', model: 'claude-haiku-5-5', monthly_usd: 6 }, { role: 'growth', model: 'claude-sonnet-5-5', monthly_usd: 14 }],
      roadmap_md: '**ماه ۱:** امن‌سازی و تست پرداخت. **ماه ۲:** انتشار بتا برای ۵۰ نفر. **ماه ۳:** رشد تا ۵۰۰ مشترک.', monthly_usd: 60 },
    decision_ref: 'D-000024', plan: 'PV-0002', company: null, created_at: iso(60 * 6), updated_at: iso(40) },
  { ref: 'C-0001', name_fa: 'کوینه‌پرو آکادمی', name_en: 'CoinePro Academy', code: 'AC', source: { kind: 'idea', repo: null, brief_md: 'آموزش ترید برای کاربران تریدیار' }, state: 'ready_for_login',
    audit: null, proposal: { departments: ['TECH', 'GROWTH', 'PRODUCT', 'SALES'], kpis: [{ name_fa: 'دانشجوی فعال', target: '300 در 90 روز' }], team: [{ role: 'ceo', model: 'claude-sonnet-5-5', monthly_usd: 18 }, { role: 'cto', model: 'claude-sonnet-5-5', monthly_usd: 20 }], roadmap_md: '', monthly_usd: 38 },
    decision_ref: 'D-000023', plan: 'PV-0001', company: 'AC', created_at: iso(60 * 30), updated_at: iso(60 * 3) },
].map((f, i) => ({ id: `fo${i}`, ...f }));

// -------------------------------------------------------------- backups --
const backups = {
  hourly: { last_at: iso(23), last_ok_at: iso(23), next_at: ahead(37), ok: true, error: null, stale: false, snapshot: 'a3f9c2e1', size_bytes: 1_840_000_000 },
  wal: { last_archived_at: iso(1), lag_s: 41, failed_count: 0, failing: false, ready_count: 0 },
  base_backup: { last_at: iso(60 * 7), count: 9 },
  check: { last_at: iso(60 * 7), ok: true },
  destinations: [
    { key: 'gdrive', configured: true, ok: true, error: null, last_ok_at: iso(23), used_bytes: 112_400_000_000, quota_bytes: 6_000_000_000_000 },
    { key: 'local', configured: true, ok: true, error: null, last_ok_at: iso(23), used_bytes: 38_200_000_000, quota_bytes: null },
    { key: 'hetzner', configured: false, ok: null, error: null, last_ok_at: null, used_bytes: 0, quota_bytes: null },
  ],
  retention: { hourly: 168, daily: 90, weekly: 52, monthly: 36, yearly: 10 },
  restore_test: { last_at: iso(60 * 24 * 2), ok: true, duration_s: 412, notes: 'PITR به یک لحظه‌ی تصادفی دیروز: درست', pitr_target: iso(60 * 24 * 2 + 600), source: 'local' },
  openbao_snapshot: { configured: false, last_at: null, ok: null }, encryption: 'restic (AES-256)',
};

const summary = () => ({
  watch, compliance,
  findings_open: { critical: findings.filter((f) => f.severity === 'critical' && !['verified', 'closed'].includes(f.status)).length, high: findings.filter((f) => f.severity === 'high' && !['verified', 'closed'].includes(f.status)).length, medium: findings.filter((f) => f.severity === 'medium' && !['verified', 'closed'].includes(f.status)).length, low: findings.filter((f) => f.severity === 'low' && !['verified', 'closed'].includes(f.status)).length, info: 0 },
  holds_waiting: holds.filter((h) => h.state === 'held').length,
  challenges_week: { issued: 1, submitted: 1, scored: 0, missed: 0, accepted: 1 } as Record<string, number>,
  // Paused protocols (⟨1.4.4⟩) are neither active nor failing; a deferred run is not a failure.
  protocols: { active: protocols.filter((p) => p.status !== 'paused').length, failed_today: protocols.filter((p) => p.status !== 'paused' && p.last_run && !['pass', 'deferred'].includes(p.last_run.result)).length },
});

let seq = 10;
/** The v1.4 routes; null when the path is not one of them. */
export async function handle14(req: Request, p: string, u: URL): Promise<Response | null> {
  const m = req.method;
  const body = async <T,>() => (await req.json().catch(() => ({}))) as T;
  if (m === 'GET') {
    if (p === '/oversight/summary') return json(summary());
    if (p === '/oversight/protocols') return json(protocols);
    if (p === '/oversight/findings') { const st = u.searchParams.get('status'); return json(page(st ? findings.filter((f) => f.status === st) : findings)); }
    const fd = /^\/oversight\/findings\/(FI-\d+)$/.exec(p); if (fd) return json(findings.find((f) => f.ref === fd[1]) ?? {}, findings.some((f) => f.ref === fd[1]) ? 200 : 404);
    if (p === '/oversight/challenges') return json(page(challenges));
    if (p === '/oversight/orders') return json(orders);
    if (p === '/oversight/holds') return json(holds.filter((h) => h.state === 'held'));
    if (p === '/oversight/watch') return json(watch);
    if (p === '/oversight/compliance') return json(compliance);
    if (p === '/inquiries') { const f = u.searchParams.get('from'); return json(page(f ? inquiries.filter((q) => q.from.code === f) : inquiries)); }
    if (p === '/errands') return json(page(errands));
    const er = /^\/errands\/(E-\d+)$/.exec(p); if (er) return json(errands.find((e) => e.ref === er[1]) ?? {});
    if (p === '/stars/rollup') return json(rollup((u.searchParams.get('period') as 'week' | 'month') ?? 'week'));
    if (p === '/stars/rubrics') return json(rubrics);
    if (p === '/lessons') return json(page(lessons));
    if (p === '/skills') return json(skills);
    if (p === '/academy/curricula') return json(curricula);
    if (p === '/academy/evals') return json(evals);
    const evr = /^\/academy\/evals\/(EV-\d+)\/runs$/.exec(p);
    if (evr) return json({ items: [...(evals.find((e) => e.ref === evr[1])?.recent ?? []), ...modelRuns.filter((r) => r.suite === evr[1])].sort((a, b) => b.at.localeCompare(a.at)), next_cursor: null });
    if (p === '/academy/runs') {
      const role = u.searchParams.get('role'); const kind = u.searchParams.get('subject_kind'); const suite = u.searchParams.get('suite');
      const inRole = new Set(evals.filter((e) => !role || e.role === role || e.role === 'all').map((e) => e.ref));
      const all = [...evals.flatMap((e) => e.recent), ...modelRuns].filter((r) => inRole.has(r.suite) && (!kind || r.subject.kind === kind) && (!suite || r.suite === suite));
      const latest = u.searchParams.get('latest') === 'true'
        ? [...all.reduce((m, r) => { const k = `${r.suite}|${r.subject.ref}`; if (!m.has(k) || m.get(k)!.at < r.at) m.set(k, r); return m; }, new Map<string, (typeof all)[number]>()).values()]
        : all;
      return json({ items: latest.sort((a, b) => b.at.localeCompare(a.at)), next_cursor: null });
    }
    const rec = /^\/academy\/records\/([A-Z0-9-]+)$/.exec(p);
    if (rec) return json(record(rec[1]!));
    if (p === '/academy/teach') return json(teachings);
    if (p === '/egress/summary') return json({ period: 'day', requests: 1284, blocked: 3, needs_owner: 2, bytes_in: 412_000_000, by_company: [{ company: 'TY', requests: 512, blocked: 0 }, { company: 'FX', requests: 388, blocked: 0 }, { company: 'PC', requests: 141, blocked: 1 }, { company: 'HQ', requests: 243, blocked: 2 }], by_tool: { 'web.search': 412, 'web.read': 610, 'web.browse': 96, 'http.request': 141, 'mcp.call': 25 } });
    if (p === '/egress') return json(page(egress));
    if (p === '/tools/mcp') return json(mcp);
    if (p === '/tools/accounts') return json(accounts);
    if (p === '/tools/catalog') return json(catalog);
    if (p === '/foundings') return json(page(foundings));
    const fo = /^\/foundings\/(C-\d+)$/.exec(p); if (fo) return json(foundings.find((f) => f.ref === fo[1]) ?? {}, foundings.some((f) => f.ref === fo[1]) ? 200 : 404);
    const pl = /^\/provisioning\/plans\/(PV-\d+)$/.exec(p); if (pl) return json(plans[pl[1]!] ?? {}, plans[pl[1]!] ? 200 : 404);
    const rn = /^\/provisioning\/runs\/([^/]+)$/.exec(p);
    if (rn) {
      const r = runs[rn[1]!];
      if (!r) return json({}, 404);
      // Live demo: each poll finishes the running step and starts the next.
      if (r.state === 'running') {
        const i = r.steps.findIndex((s: any) => s.state !== 'done');
        if (i >= 0) {
          r.steps[i] = { ...r.steps[i], state: 'done', finished_at: new Date().toISOString(), log_tail: logFor(r.steps[i].key, plans[r.plan]) };
          if (r.steps[i + 1]) r.steps[i + 1] = { ...r.steps[i + 1], state: 'running', started_at: new Date().toISOString() };
          if (r.steps[i].key === 'server') r.server = { name: plans[r.plan].name, ipv4: '203.0.113.31', ipv6: '2001:db8::31', private_ip: '10.10.1.6' };
        }
        if (r.steps.every((s: any) => s.state === 'done')) {
          r.state = 'done';
          r.login = { ssh: `ssh ${plans[r.plan].work_user}@203.0.113.31`, then: ['claude'] };
          plans[r.plan].state = 'done';
          const f = foundings.find((x) => x.plan === r.plan); if (f) Object.assign(f, { state: 'ready_for_login', updated_at: new Date().toISOString() });
        }
      }
      return json(r);
    }
    if (p === '/infra/servers') return json([{ name: 'coine-academy-1', type: 'cpx31', location: 'nbg1', ipv4: '203.0.113.24', plan: 'PV-0001', created_at: iso(60 * 3) }]);
    if (p === '/backups/status') return json(backups);
    return null;
  }
  // ---- writes
  const fs = /^\/oversight\/findings\/(FI-\d+)\/status$/.exec(p);
  if (fs) { const b = await body<{ status: string; note: string }>(); const f = findings.find((x) => x.ref === fs[1]); if (!f) return json({}, 404); f.status = b.status; f.history.push({ at: new Date().toISOString(), by: owner, status: b.status, note: b.note }); if (['verified', 'closed'].includes(b.status)) f.closed_at = new Date().toISOString(); return json(f); }
  if (p === '/oversight/orders') { const b = await body<any>(); const o = { id: `so${orders.length}`, ref: `SO-${String(orders.length + 3).padStart(3, '0')}`, text_md: b.text_md, source: b.source, file_id: b.file_id ?? null, applies_to: b.applies_to, status: 'proposed', version: 1, sealed_at: null, created_at: new Date().toISOString() }; orders.unshift(o); return json(o, 201); }
  const os = /^\/oversight\/orders\/(SO-\d+)\/(seal|retire)$/.exec(p);
  if (os) { const o = orders.find((x) => x.ref === os[1]); if (!o) return json({}, 404); o.status = os[2] === 'seal' ? 'sealed' : 'retired'; if (os[2] === 'seal') o.sealed_at = new Date().toISOString(); return json(o); }
  const hd = /^\/oversight\/holds\/(H-\d+)\/(release|cancel)$/.exec(p);
  if (hd) { const h = holds.find((x) => x.ref === hd[1]); if (!h) return json({}, 404); Object.assign(h, { state: hd[2] === 'release' ? 'released' : 'cancelled', decided_by: owner, decided_at: new Date().toISOString() }); return json(h); }
  if (p === '/errands') {
    const b = await body<{ brief_md: string; source: 'voice' | 'text' }>();
    const e = { id: `e${errands.length}`, ref: `E-${String(errands.length + 1).padStart(4, '0')}`, title_fa: b.brief_md.slice(0, 60), brief_md: b.brief_md, source: b.source, status: 'working', due_at: null, file_ids: [], attachments: [],
      steps: [{ at: new Date().toISOString(), kind: 'note', summary_fa: 'شروع شد؛ برنامه‌ی کار نوشته شد', data: {} }], result_md: null, decision_ref: null, usage: { usd: 0 }, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
    errands.unshift(e);
    return json(e, 201);
  }
  const ec = /^\/errands\/(E-\d+)\/cancel$/.exec(p); if (ec) { const e = errands.find((x) => x.ref === ec[1]); if (e) e.status = 'cancelled'; return json(e ?? {}); }
  if (p === '/skills') {
    const b = await body<{ name_fa: string; body_md: string; roles: string[]; companies: 'all' | string[] }>();
    const s = { id: `sk${skills.length}`, ref: `SK-${String(skills.length + 1).padStart(3, '0')}`, name_fa: b.name_fa, summary_fa: b.body_md.slice(0, 120), body_md: b.body_md, resources: [], scope: { roles: b.roles, companies: b.companies, departments: [] }, version: 1, status: 'in_review', review: null, eval: null, created_by: owner, created_at: new Date().toISOString(), activated_at: null };
    skills.unshift(s);
    return json(s, 201);
  }
  const sa = /^\/skills\/(SK-\d+)\/(activate|retire)$/.exec(p);
  if (sa) { const s = skills.find((x) => x.ref === sa[1]); if (!s) return json({}, 404); if (sa[2] === 'activate' && s.status !== 'approved') return json({ code: 'not_approved', message_fa: 'این مهارت هنوز بررسی و آزمون را نگذرانده است.' }, 409); s.status = sa[2] === 'activate' ? 'active' : 'retired'; if (sa[2] === 'activate') s.activated_at = new Date().toISOString(); return json(s); }
  if (p === '/academy/teach') {
    const b = await body<{ target: { kind: 'role' | 'employee'; ref: string }; text: string; source: 'voice' | 'text' }>();
    const t = { id: `te${teachings.length}`, ref: `TE-${String(teachings.length + 1).padStart(4, '0')}`, target: b.target, source: b.source, text_md: b.text, file_id: null, proposal: null, eval_run: null, status: 'drafting', created_at: new Date().toISOString() };
    teachings.unshift(t);
    setTimeout(() => Object.assign(t, { status: 'proposed', proposal: { kind: 'charter_rule', diff_md: `+ ${b.text}` }, eval_run: { score: 92, baseline: 90, passed: true } }), 4000);
    return json(t, 201);
  }
  const ta = /^\/academy\/teach\/(TE-\d+)\/(approve|reject)$/.exec(p);
  if (ta) { const t = teachings.find((x) => x.ref === ta[1]); if (t) t.status = ta[2] === 'approve' ? 'approved' : 'rejected'; return json(t ?? {}); }
  const me = /^\/tools\/mcp\/([^/]+)\/(enable|disable)$/.exec(p);
  if (me) { const s = mcp.find((x) => x.key === me[1]); if (!s) return json({}, 404); s.status = me[2] === 'enable' ? 'enabled' : 'disabled'; s.tools = s.tools.map((t) => ({ ...t, enabled: me[2] === 'enable' })); return json(s); }
  if (p === '/foundings') {
    const b = await body<{ source: { kind: 'repo' | 'idea'; repo: string | null; brief_md: string } }>();
    const f = { id: `fo${foundings.length}`, ref: `C-${String(foundings.length + 1).padStart(4, '0')}`, name_fa: b.source.repo?.split('/')[1] ?? 'شرکت تازه', name_en: '', code: '', source: b.source, state: 'auditing', audit: null, proposal: null, decision_ref: null, plan: null, company: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
    foundings.unshift(f);
    return json(f, 201);
  }
  const fa = /^\/foundings\/(C-\d+)\/(activate|cancel)$/.exec(p);
  if (fa) { const f = foundings.find((x) => x.ref === fa[1]); if (!f) return json({}, 404); f.state = fa[2] === 'activate' ? 'active' : 'cancelled'; f.updated_at = new Date().toISOString(); return json(f); }
  const ps = /^\/provisioning\/plans\/(PV-\d+)\/seal$/.exec(p);
  if (ps) {
    const pl = plans[ps[1]!];
    if (!pl) return json({}, 404);
    const id = `r${++seq}`;
    runs[id] = { id, plan: pl.ref, state: 'running', steps: STEPS.map(([key, title_fa], i) => ({ key, title_fa, state: i === 0 ? 'running' : 'pending', started_at: i === 0 ? new Date().toISOString() : null, finished_at: null, log_tail: '' })), server: null, login: null };
    Object.assign(pl, { state: 'running', run: id, decision_ref: 'D-000025' });
    const f = foundings.find((x) => x.plan === pl.ref); if (f) Object.assign(f, { state: 'provisioning', updated_at: new Date().toISOString() });
    return json(pl);
  }
  return null;
}
