// Development-only fixtures (npm run dev:mock) for contract §29 ⟨1.11⟩, the same story the Android app's demo tells: the owner's home
// (an effective and a good suggestion, real progress from Instagram, five morning lines, the content group's KPIs per company, the orders,
// one critical item), the order reports (TradeYar's clip order blocked on an unsealed series and an empty publisher seat, FX's SEO article
// delivered with its end summary, Pro-Chart's posts waiting on budget), the secretary's preview by rules, long voice in chunks, the
// owner's rules, the content working group (members, seats, routines and their runs, KPIs, the week's experiment), readiness, the
// connections with their guides, each employee's state, the technical findings and notifications under «شرکت ← فنی», and a council v2.
// Every date and figure is fixed, so the end-to-end checks read the same page every day. Never bundled in production (reached only
// through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

const json = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const needStepUp = () => problem(403, 'step_up_required', 'این کار تأیید با اثر انگشت یا چهره میخواهد.');
const SECRETARY = { kind: 'agent', code: 'HQ-SECRETARY', display_fa: 'منشی هلدینگ' };

// The demo's «today» and its fixed hours (UTC; Tehran is +03:30).
const DAY = '2026-11-03';
const at = (day: string, hm: string) => `${day}T${hm}:00Z`;
const days = (n: number, last = DAY) => Array.from({ length: n }, (_, i) => new Date(Date.parse(`${last}T12:00:00Z`) - (n - 1 - i) * 86_400_000).toISOString().slice(0, 10));
const D14 = days(14);

const NAME: Record<string, string> = { HQ: 'هلدینگ کوینه‌پرو', TY: 'تریدیار', FX: 'کوینه‌پرو FX', PC: 'پرو-چارت' };

// ======================================================================================== the content group ==
const ROUTINES = [
  { key: 'morning_numbers', title_fa: 'عددهای دیروز', seat: 'analyst', schedule: 'FREQ=DAILY;BYHOUR=7;BYMINUTE=30', brief_md: 'عددهای دیروز هر پست از اتصال‌ها، با منبع و تاریخ.', max_tokens: 40_000, state: 'on' },
  { key: 'daily_plan', title_fa: 'برنامه‌ی امروز', seat: 'lead', schedule: 'FREQ=DAILY;BYHOUR=8', brief_md: 'حداکثر سه کار برای امروز، از روند، رقبا و عددهای دیروز.', max_tokens: 60_000, state: 'on' },
  { key: 'review', title_fa: 'بازبینی آیتم‌ها', seat: 'lead', schedule: 'FREQ=DAILY;BYHOUR=14', brief_md: 'هر آیتم آماده: پذیرفته، یا اصلاح با جای دقیق.', max_tokens: 50_000, state: 'on' },
  { key: 'owner_line', title_fa: 'یک خط برای مالک', seat: 'lead', schedule: 'FREQ=DAILY;BYHOUR=20', brief_md: 'امروز چه منتشر شد و بهترین دیروز.', max_tokens: 10_000, state: 'on' },
  { key: 'weekly_experiment', title_fa: 'آزمایش هفته', seat: 'lead', schedule: 'FREQ=WEEKLY;BYDAY=SA;BYHOUR=9', brief_md: 'یک آزمایش عمدی با فرضیه و عدد هدف.', max_tokens: 40_000, state: 'paused' },
];
const SEATS = [
  { seat: 'lead', role: 'media_director', title_fa: 'مدیر محتوا', count: 1 },
  { seat: 'writer', role: 'scriptwriter', title_fa: 'نویسنده', count: 1 },
  { seat: 'designer', role: 'visual_designer', title_fa: 'طراح تصویر', count: 1 },
  { seat: 'reels', role: 'motion_designer', title_fa: 'سازنده‌ی ریلز و موشن', count: 1 },
  { seat: 'publisher', role: 'publisher', title_fa: 'مسئول انتشار', count: 1 },
  { seat: 'analyst', role: 'content_analyst', title_fa: 'تحلیلگر عملکرد', count: 1 },
];
const GROUP = {
  key: 'content', title_fa: 'تولید محتوا و انتشار',
  purpose_fa: 'هر روز برای هر شرکتی که صفحه دارد دست‌کم یک خروجی واقعی، منتشرشده یا آماده‌ی انتشار، با عددی که از اتصال واقعی میاید.',
  seats: SEATS, routines: ROUTINES,
  kpis: [
    { key: 'reach', title_fa: 'بازدید روزانه', unit: '', source: 'instagram' },
    { key: 'followers', title_fa: 'دنبال‌کننده', unit: '', source: 'instagram' },
    { key: 'published', title_fa: 'خروجی منتشرشده', unit: '', source: 'hub' },
  ],
  connections: ['instagram', 'telegram'], eligible: 'has_channel', state: 'on',
};
const members: any[] = [
  { group: 'content', company: 'TY', state: 'on', joined_at: '2026-11-02T05:00:00Z', seats: [
    { seat: 'lead', employee: 'TY-MEDIA-MGR' }, { seat: 'writer', employee: 'TY-MEDIA-01' }, { seat: 'designer', employee: 'TY-MEDIA-02' },
    { seat: 'reels', employee: 'TY-MEDIA-04' }, { seat: 'publisher', employee: null }, { seat: 'analyst', employee: 'TY-GROWTH-02' },
  ] },
  { group: 'content', company: 'FX', state: 'on', joined_at: '2026-11-02T05:00:00Z', seats: [
    { seat: 'lead', employee: 'FX-MEDIA-MGR' }, { seat: 'writer', employee: 'FX-MEDIA-01' }, { seat: 'designer', employee: null },
    { seat: 'reels', employee: 'FX-MEDIA-03' }, { seat: 'publisher', employee: null }, { seat: 'analyst', employee: null },
  ] },
  { group: 'content', company: 'PC', state: 'paused', joined_at: '2026-11-02T05:00:00Z', seats: [
    { seat: 'lead', employee: 'PC-MEDIA-MGR' }, { seat: 'writer', employee: 'PC-MEDIA-03' }, { seat: 'designer', employee: 'PC-MEDIA-02' },
    { seat: 'reels', employee: null }, { seat: 'publisher', employee: null }, { seat: 'analyst', employee: null },
  ] },
];
const routineState: Record<string, string> = Object.fromEntries(ROUTINES.map((r) => [r.key, r.state]));
const groupOut = () => ({ ...GROUP, routines: ROUTINES.map((r) => ({ ...r, state: routineState[r.key] })), members });

const RUNS = [
  { id: 'rr-12', company: 'TY', routine: 'daily_plan', at: at(DAY, '04:30'), work_ref: null, state: 'done', note_fa: 'سه کار: دو ریلز آموزشی و یک استوری نظرسنجی.' },
  { id: 'rr-11', company: 'TY', routine: 'morning_numbers', at: at(DAY, '04:00'), work_ref: null, state: 'done', note_fa: 'بازدید دیروز 8,940؛ بهترین پست: ریلز «سه اشتباه رایج».' },
  { id: 'rr-10', company: 'FX', routine: 'daily_plan', at: at(DAY, '04:30'), work_ref: null, state: 'done', note_fa: 'دو کار: کاروسل آموزشی و یک پست خبری.' },
  { id: 'rr-09', company: 'FX', routine: 'morning_numbers', at: at(DAY, '04:00'), work_ref: null, state: 'failed', note_fa: 'تلگرام FX خوانده نشد؛ اتصالش خطا دارد.' },
  { id: 'rr-08', company: 'PC', routine: 'daily_plan', at: at(DAY, '04:30'), work_ref: null, state: 'skipped', note_fa: 'عضویت پرو-چارت متوقف است.' },
  { id: 'rr-07', company: 'TY', routine: 'owner_line', at: at('2026-11-02', '16:30'), work_ref: null, state: 'done', note_fa: 'امروز: یک ریلز و دو استوری آماده شد؛ انتشار منتظر مُهر سری.' },
  { id: 'rr-06', company: 'TY', routine: 'review', at: at('2026-11-02', '10:30'), work_ref: null, state: 'done', note_fa: 'سه ریلز پذیرفته شد؛ یکی با اصلاح زیرنویس.' },
  { id: 'rr-05', company: 'FX', routine: 'review', at: at('2026-11-02', '10:30'), work_ref: null, state: 'done', note_fa: 'یک کاروسل پذیرفته شد.' },
  { id: 'rr-04', company: 'TY', routine: 'daily_plan', at: at('2026-11-02', '04:30'), work_ref: null, state: 'done', note_fa: 'سه ریلز آموزشی برای شروع سری.' },
];
const EXPERIMENTS = [
  { id: 'ex-2', group: 'content', company: 'TY', week: '2026-W45', hypothesis_fa: 'ریلز 15 ثانیه‌ای بیشتر از ریلز 30 ثانیه‌ای تا آخر دیده میشود.', metric: 'نرخ تماشای کامل', target: '35%', result: '41%', kept: true },
  { id: 'ex-3', group: 'content', company: 'FX', week: '2026-W45', hypothesis_fa: 'کاروسل آموزشی بیشتر از پست تک‌تصویری ذخیره میشود.', metric: 'ذخیره در هفته', target: '120', result: null, kept: null },
];

/** A KPI's fixed fourteen days: a gentle trend with a weekly ripple; a paused member's last days stay empty. */
function series(company: string, key: string): Array<{ day: string; value: number | null }> {
  const base: Record<string, Record<string, [number, number]>> = {
    TY: { reach: [5200, 290], followers: [17_640, 92], published: [1, 0.15] },
    FX: { reach: [3100, 120], followers: [9_850, 41], published: [0, 0.1] },
    PC: { reach: [1400, 35], followers: [4_210, 12], published: [0, 0.05] },
  };
  const [b, step] = base[company]?.[key] ?? [0, 0];
  return D14.map((day, i) => {
    if (company === 'PC' && i >= 11) return { day, value: null };
    const ripple = key === 'published' ? 0 : ((i * 7) % 5) * (b / 60);
    const v = key === 'published' ? Math.floor(b + step * i) : Math.round(b + step * i + ripple);
    return { day, value: v };
  });
}
const kpiRows = (company: string | null) =>
  (company ? [company] : ['TY', 'FX', 'PC']).flatMap((c) => GROUP.kpis.map((k) => ({ company: c, key: k.key, title_fa: k.title_fa, unit: k.unit, series: series(c, k.key) })));

// ======================================================================================== readiness ==
type Check = { key: string; ok: boolean; title_fa: string; detail_fa: string; fix: any };
const READINESS: Record<string, Check[]> = {
  TY: [
    { key: 'seats', ok: false, title_fa: 'هر جایگاه کارمند فعال دارد', detail_fa: 'جایگاه «مسئول انتشار» خالی است.', fix: { action: 'hire', label_fa: 'استخدام مسئول انتشار', target: 'content/publisher' } },
    { key: 'hiring', ok: true, title_fa: 'استخدام خودکار روشن است', detail_fa: 'مدیرعامل در پاکت ماه، بی کارت، استخدام میکند.', fix: null },
    { key: 'envelope', ok: true, title_fa: 'پاکت ماه تعیین شده', detail_fa: 'این ماه 18 میلیون واحد؛ 41% مصرف شده.', fix: null },
    { key: 'series', ok: false, title_fa: 'برای هر کانال یک سری مُهرشده', detail_fa: 'سری «ریلز آموزشی روزانه» برای اینستاگرام منتظر مُهر شماست.', fix: { action: 'series.propose', label_fa: 'دیدن سری‌های انتشار', target: null } },
    { key: 'channels', ok: true, title_fa: 'کانال‌های انتشار وصل‌اند', detail_fa: 'اینستاگرام از راه IG-Hub و کانال تلگرام.', fix: null },
    { key: 'media_tools', ok: true, title_fa: 'ساخت ویدیو و صدا', detail_fa: 'روی ستاد، هر وقت لازم شود روشن میشود.', fix: null },
    { key: 'players', ok: true, title_fa: 'بازیکن‌ها در دسترس‌اند', detail_fa: 'Claude و بازیکن‌های ذخیره آماده‌اند.', fix: null },
    { key: 'runner', ok: true, title_fa: 'دستیار سرور شرکت وصل است', detail_fa: 'کارهای روی سرور تریدیار انجام میشود.', fix: null },
  ],
  FX: [
    { key: 'seats', ok: false, title_fa: 'هر جایگاه کارمند فعال دارد', detail_fa: 'سه جایگاه خالی است: طراح تصویر، مسئول انتشار، تحلیلگر عملکرد.', fix: { action: 'hire', label_fa: 'استخدام هر سه', target: 'content/designer,publisher,analyst' } },
    { key: 'hiring', ok: true, title_fa: 'استخدام خودکار روشن است', detail_fa: 'مدیرعامل در پاکت ماه، بی کارت، استخدام میکند.', fix: null },
    { key: 'envelope', ok: true, title_fa: 'پاکت ماه تعیین شده', detail_fa: 'این ماه 12 میلیون واحد؛ 22% مصرف شده.', fix: null },
    { key: 'series', ok: true, title_fa: 'برای هر کانال یک سری مُهرشده', detail_fa: 'سری «آموزش فارکس» برای اینستاگرام مُهر شده است.', fix: null },
    { key: 'channels', ok: false, title_fa: 'کانال‌های انتشار وصل‌اند', detail_fa: 'تلگرام FX خوانده نمیشود؛ رمز ربات دیگر معتبر نیست.', fix: { action: 'connection.guide', label_fa: 'وصل کردن تلگرام', target: 'FX/telegram' } },
    { key: 'media_tools', ok: true, title_fa: 'ساخت ویدیو و صدا', detail_fa: 'روی ستاد، هر وقت لازم شود روشن میشود.', fix: null },
    { key: 'players', ok: true, title_fa: 'بازیکن‌ها در دسترس‌اند', detail_fa: 'Claude و بازیکن‌های ذخیره آماده‌اند.', fix: null },
    { key: 'runner', ok: true, title_fa: 'دستیار سرور شرکت وصل است', detail_fa: 'کارهای روی سرور FX انجام میشود.', fix: null },
  ],
  PC: [
    { key: 'membership', ok: false, title_fa: 'عضو کارگروه است', detail_fa: 'عضویت پرو-چارت متوقف است.', fix: { action: 'member.resume', label_fa: 'ادامه‌ی عضویت', target: 'content/PC' } },
    { key: 'seats', ok: false, title_fa: 'هر جایگاه کارمند فعال دارد', detail_fa: 'سه جایگاه خالی است: سازنده‌ی ریلز، مسئول انتشار، تحلیلگر عملکرد.', fix: { action: 'hire', label_fa: 'استخدام هر سه', target: 'content/reels,publisher,analyst' } },
    { key: 'media_tools', ok: false, title_fa: 'ساخت ویدیو و صدا', detail_fa: 'ساخت ویدیو روی ستاد هنوز برای پرو-چارت روشن نشده.', fix: { action: 'media.on', label_fa: 'روشن کن', target: 'PC' } },
    { key: 'channels', ok: true, title_fa: 'کانال‌های انتشار وصل‌اند', detail_fa: 'اینستاگرام از راه IG-Hub.', fix: null },
  ],
};
const readinessOut = (code: string) => {
  const checks = READINESS[code] ?? [];
  return { company: code, group: 'content', ready: checks.every((c) => c.ok), checks };
};

// ======================================================================================== connections ==
type Conn = { company: string; kind: string; label_fa: string; state: string; config: Record<string, unknown>; secret: string; last_read_at: string | null; last_error_fa: string | null; daily: Array<{ day: string; key: string; value: number }> };
const D3 = days(3);
const daily = (pairs: Array<[string, number, number]>) => D3.flatMap((day, i) => pairs.map(([key, v, step]) => ({ day, key, value: Math.round(v + step * i) })));
const off = (company: string, kind: string, label_fa: string): Conn => ({ company, kind, label_fa, state: 'not_connected', config: {}, secret: 'missing', last_read_at: null, last_error_fa: null, daily: [] });
const connections: Record<string, Conn[]> = {
  TY: [
    { company: 'TY', kind: 'search_console', label_fa: 'سایت تریدیار', state: 'connected', config: { site: 'https://tradeyar.com' }, secret: 'set', last_read_at: at(DAY, '02:10'), last_error_fa: null, daily: daily([['clicks', 1180, 64], ['impressions', 40_200, 1300]]) },
    { company: 'TY', kind: 'ga4', label_fa: 'آمار سایت تریدیار', state: 'connected', config: { property: '381204771' }, secret: 'set', last_read_at: at(DAY, '02:12'), last_error_fa: null, daily: daily([['users', 6420, 140], ['sessions', 9100, 210]]) },
    { company: 'TY', kind: 'instagram', label_fa: 'صفحه‌ی اینستاگرام تریدیار (از راه IG-Hub)', state: 'connected', config: { account: 'tradeyar' }, secret: 'set', last_read_at: at(DAY, '02:20'), last_error_fa: null, daily: daily([['reach', 8510, 215], ['followers', 18_790, 62]]) },
    { company: 'TY', kind: 'telegram', label_fa: 'کانال سیگنال تریدیار', state: 'connected', config: { channel: '@tradeyar_signals' }, secret: 'set', last_read_at: at(DAY, '02:22'), last_error_fa: null, daily: daily([['members', 12_440, 18], ['views', 31_900, 520]]) },
    off('TY', 'youtube', 'کانال یوتیوب تریدیار'), off('TY', 'x', 'حساب ایکس تریدیار'),
    { company: 'TY', kind: 'pagespeed', label_fa: 'سرعت صفحه‌ی اصلی', state: 'connected', config: { url: 'https://tradeyar.com' }, secret: 'missing', last_read_at: at(DAY, '02:30'), last_error_fa: null, daily: daily([['score', 71, 1]]) },
    off('TY', 'trends', 'روند جست‌وجوی «صرافی»'), off('TY', 'bing', 'سایت تریدیار در بینگ'), off('TY', 'play_console', 'اپ تریدیار در گوگل‌پلی'),
  ],
  FX: [
    off('FX', 'search_console', 'سایت کوینه‌پرو FX'),
    { company: 'FX', kind: 'ga4', label_fa: 'آمار سایت FX', state: 'connected', config: { property: '402118553' }, secret: 'set', last_read_at: at(DAY, '02:12'), last_error_fa: null, daily: daily([['users', 2140, 60], ['sessions', 3020, 75]]) },
    { company: 'FX', kind: 'instagram', label_fa: 'صفحه‌ی اینستاگرام FX (از راه IG-Hub)', state: 'connected', config: { account: 'coineprofx' }, secret: 'set', last_read_at: at(DAY, '02:20'), last_error_fa: null, daily: daily([['reach', 4480, 90], ['followers', 10_390, 30]]) },
    { company: 'FX', kind: 'telegram', label_fa: 'کانال FX', state: 'error', config: { channel: '@coineprofx' }, secret: 'set', last_read_at: at('2026-11-01', '02:22'), last_error_fa: 'رمز ربات دیگر معتبر نیست؛ یک رمز تازه از ربات‌ساز تلگرام بگیر و این‌جا بگذار.', daily: [] },
    off('FX', 'youtube', 'کانال یوتیوب FX'), off('FX', 'x', 'حساب ایکس FX'), off('FX', 'pagespeed', 'سرعت صفحه‌ی اصلی FX'), off('FX', 'trends', 'روند جست‌وجوی «فارکس»'),
    off('FX', 'bing', 'سایت FX در بینگ'), off('FX', 'play_console', 'اپ FX در گوگل‌پلی'),
  ],
  PC: [
    off('PC', 'search_console', 'سایت پرو-چارت'), off('PC', 'ga4', 'آمار سایت پرو-چارت'),
    { company: 'PC', kind: 'instagram', label_fa: 'صفحه‌ی اینستاگرام پرو-چارت (از راه IG-Hub)', state: 'connected', config: { account: 'prochart.ir' }, secret: 'set', last_read_at: at(DAY, '02:20'), last_error_fa: null, daily: daily([['reach', 1720, 20], ['followers', 4_340, 6]]) },
    off('PC', 'telegram', 'کانال پرو-چارت'), off('PC', 'youtube', 'کانال یوتیوب پرو-چارت'), off('PC', 'x', 'حساب ایکس پرو-چارت'), off('PC', 'pagespeed', 'سرعت صفحه‌ی اصلی پرو-چارت'),
    off('PC', 'trends', 'روند جست‌وجوی «نمودار»'), off('PC', 'bing', 'سایت پرو-چارت در بینگ'), off('PC', 'play_console', 'اپ پرو-چارت در گوگل‌پلی'),
  ],
  HQ: [],
};
const GUIDE: Record<string, { title_fa: string; steps: string[]; config: Array<{ key: string; label_fa: string; placeholder?: string; hint_fa?: string }>; secret_fa: string | null }> = {
  search_console: { title_fa: 'وصل کردن جست‌وجوی گوگل (سئو)', steps: ['در کنسول جست‌وجوی گوگل، سایت را با حساب شرکت باز کن.', 'در «تنظیمات ← کاربران»، نشانی حساب ستاد را با دسترسی «فقط خواندن» اضافه کن.', 'نشانی سایت را این‌جا بنویس و «ذخیره» بزن.', 'کلید حساب ستاد را در خانه‌ی رمز بگذار.'], config: [{ key: 'site', label_fa: 'نشانی سایت', placeholder: 'https://example.com' }], secret_fa: 'کلید حساب ستاد' },
  ga4: { title_fa: 'وصل کردن آمار بازدید سایت', steps: ['در آمار گوگل، «مدیریت ← دسترسی‌ها» را باز کن.', 'حساب ستاد را با نقش «بیننده» اضافه کن.', 'شماره‌ی ویژگی سایت را این‌جا بنویس.'], config: [{ key: 'property', label_fa: 'شماره‌ی ویژگی', placeholder: '123456789' }], secret_fa: 'کلید حساب ستاد' },
  instagram: { title_fa: 'وصل کردن اینستاگرام', steps: ['همه‌ی صفحه‌های اینستاگرام روی IG-Hub هستند؛ رمزی این‌جا لازم نیست.', 'نام صفحه را بنویس؛ عددها هر شب از خود IG-Hub خوانده میشوند.'], config: [{ key: 'account', label_fa: 'نام صفحه', placeholder: 'company' }], secret_fa: null },
  telegram: { title_fa: 'وصل کردن تلگرام', steps: ['در تلگرام با ربات‌ساز رسمی یک ربات بساز (یا رمز ربات فعلی را تازه کن).', 'ربات را در کانال، مدیر «فقط خواندن» کن.', 'نام کانال را بنویس و رمز ربات را در خانه‌ی رمز بگذار.'], config: [{ key: 'channel', label_fa: 'نام کانال', placeholder: '@channel' }], secret_fa: 'رمز ربات' },
};
function guideOf(kind: string) {
  const g = GUIDE[kind] ?? { title_fa: 'وصل کردن', steps: ['حساب شرکت را باز کن و دسترسی «فقط خواندن» به ستاد بده.', 'نشانی یا نام حساب را این‌جا بنویس.', 'اگر کلیدی لازم است، در خانه‌ی رمز بگذار.'], config: [{ key: 'account', label_fa: 'نام یا نشانی حساب' }], secret_fa: 'کلید' };
  return { kind, title_fa: g.title_fa, body_md: g.steps.map((s, i) => `${i + 1}. ${s}`).join('\n'), config: g.config, secret_fa: g.secret_fa, secret: !!g.secret_fa };
}

// ======================================================================================== orders and their reports ==
type Report = any;
const reports: Record<string, Report> = {
  'F-0007': {
    ref: 'F-0007', text_fa: 'برای تریدیار کلیپ بساز و منظم منتشر کن', at: at('2026-11-02', '06:40'), state: 'blocked',
    ack: {
      at: at('2026-11-02', '06:41'), by: SECRETARY,
      plan_fa: 'مدیر رسانه‌ی تریدیار هر روز یک ریلز آموزشی 30 ثانیه‌ای میسازد و در سری «ریلز آموزشی روزانه» منتشر میکند. نویسنده متن را مینویسد، سازنده‌ی ریلز آن را میسازد و مدیر رسانه پیش از انتشار بازبینی میکند.',
      assigned: [{ company: 'TY', code: 'TY-MEDIA-MGR', title_fa: 'مدیر رسانه' }, { company: 'TY', code: 'TY-MEDIA-01', title_fa: 'نویسنده' }, { company: 'TY', code: 'TY-MEDIA-04', title_fa: 'سازنده‌ی ریلز' }],
      due_at: at('2026-11-05', '14:30'),
    },
    route: { companies: ['TY'], department: 'MEDIA', collaborators: [], output_kind: 'reel', budget_tokens: 1_200_000, mode: 'single', player: 'auto' },
    steps: [
      { at: at('2026-11-02', '06:40'), who_fa: 'منشی هلدینگ', what_fa: 'فرمان را خواند و به رسانه‌ی تریدیار سپرد.' },
      { at: at('2026-11-02', '06:43'), who_fa: 'مدیر رسانه', what_fa: 'برنامه نوشت: هر روز یک ریلز 30 ثانیه‌ای، سه تای اول تا امروز.' },
      { at: at('2026-11-02', '08:10'), who_fa: 'نویسنده', what_fa: 'متن سه ریلز اول را نوشت.' },
      { at: at('2026-11-02', '11:25'), who_fa: 'سازنده‌ی ریلز', what_fa: 'سه ریلز را ساخت.' },
      { at: at('2026-11-02', '12:05'), who_fa: 'مدیر رسانه', what_fa: 'هر سه را بازبینی کرد و پذیرفت؛ یکی با اصلاح زیرنویس.' },
      { at: at('2026-11-02', '12:06'), who_fa: 'مدیر رسانه', what_fa: 'انتشار منتظر ماند: سری انتشار هنوز مُهر نشده و مسئول انتشار نیست.' },
    ],
    blockers: [
      { kind: 'series_unsealed', title_fa: 'سری انتشار مُهر نشده', detail_fa: 'سه ریلز آماده است، ولی سری «ریلز آموزشی روزانه» هنوز مُهر شما را ندارد.', since: at('2026-11-02', '12:06'), fix: { action: 'series.seal', label_fa: 'مُهر سری انتشار', target: 'SR-0012' } },
      { kind: 'no_employee', title_fa: 'مسئول انتشار نیست', detail_fa: 'جایگاه مسئول انتشار تریدیار خالی است؛ بعد از مُهر هم کسی باید منتشر کند.', since: at('2026-11-02', '12:06'), fix: { action: 'hire', label_fa: 'استخدام مسئول انتشار', target: 'TY/publisher' } },
    ],
    outputs: [
      { ref: 'O-000061', title_fa: 'ریلز ۱: سه اشتباه رایج تازه‌کارها', kind: 'reel' },
      { ref: 'O-000062', title_fa: 'ریلز ۲: حد ضرر در یک دقیقه', kind: 'reel' },
      { ref: 'O-000063', title_fa: 'ریلز ۳: کارمزد را کجا ببینیم', kind: 'reel' },
    ],
    summary: null, updated_at: at('2026-11-02', '12:06'),
  },
  'F-0006': {
    ref: 'F-0006', text_fa: 'یک مقاله‌ی سئو برای FX درباره‌ی آموزش فارکس برای تازه‌کارها', at: at('2026-10-31', '07:15'), state: 'delivered',
    ack: { at: at('2026-10-31', '07:16'), by: SECRETARY, plan_fa: 'نویسنده‌ی FX یک مقاله‌ی 1800 کلمه‌ای با کلمه‌ی کلیدی «آموزش فارکس» مینویسد؛ مدیر رسانه بازبینی و منتشر میکند.', assigned: [{ company: 'FX', code: 'FX-MEDIA-01', title_fa: 'نویسنده' }], due_at: at('2026-11-01', '14:30') },
    route: { companies: ['FX'], department: 'MEDIA', collaborators: [], output_kind: 'article', budget_tokens: 250_000, mode: 'single', player: 'auto' },
    steps: [
      { at: at('2026-10-31', '07:15'), who_fa: 'منشی هلدینگ', what_fa: 'فرمان را به رسانه‌ی FX سپرد.' },
      { at: at('2026-10-31', '09:40'), who_fa: 'نویسنده', what_fa: 'پیش‌نویس را با سه منبع نوشت.' },
      { at: at('2026-11-01', '06:20'), who_fa: 'مدیر رسانه', what_fa: 'بازبینی کرد و در وبلاگ FX منتشر شد.' },
    ],
    blockers: [
      { kind: 'connection_missing', title_fa: 'جست‌وجوی گوگل FX وصل نیست', detail_fa: 'تا وصل نشود، رتبه و کلیک مقاله سنجیده نمیشود.', since: at('2026-11-01', '06:20'), fix: { action: 'connection.guide', label_fa: 'وصل کردن جست‌وجوی گوگل', target: 'FX/search_console' } },
    ],
    outputs: [{ ref: 'O-000058', title_fa: 'آموزش فارکس برای تازه‌کارها: از صفر تا اولین معامله', kind: 'article' }],
    summary: { done_fa: 'مقاله‌ی 1800 کلمه‌ای نوشته و در وبلاگ FX منتشر شد.', left_fa: 'دو تصویر داخل مقاله هنوز ساده‌اند؛ طراح نسخه‌ی بهتر را تا پنجشنبه میدهد.', need_fa: 'جست‌وجوی گوگل FX را وصل کنید تا رتبه‌ی مقاله سنجیده شود.' },
    updated_at: at('2026-11-01', '06:20'),
  },
  'F-0005': {
    ref: 'F-0005', text_fa: 'برای پرو-چارت سه پست معرفی ابزار تحلیل تکنیکال آماده کن', at: at('2026-11-02', '09:00'), state: 'waiting',
    ack: { at: at('2026-11-02', '09:01'), by: SECRETARY, plan_fa: 'طراح پرو-چارت سه پست کاروسلی میسازد؛ نویسنده متن هر کدام را مینویسد.', assigned: [{ company: 'PC', code: 'PC-MEDIA-02', title_fa: 'طراح تصویر' }, { company: 'PC', code: 'PC-MEDIA-03', title_fa: 'نویسنده' }], due_at: at('2026-11-04', '14:30') },
    route: { companies: ['PC'], department: 'MEDIA', collaborators: [], output_kind: 'post', count: 3, budget_tokens: 300_000, mode: 'single', player: 'auto' },
    steps: [
      { at: at('2026-11-02', '09:00'), who_fa: 'منشی هلدینگ', what_fa: 'فرمان را به رسانه‌ی پرو-چارت سپرد.' },
      { at: at('2026-11-02', '11:30'), who_fa: 'طراح تصویر', what_fa: 'دو پست از سه آماده شد.' },
      { at: at('2026-11-02', '12:10'), who_fa: 'طراح تصویر', what_fa: 'کار ایستاد: بودجه‌ی این فرمان تمام شد.' },
    ],
    blockers: [
      { kind: 'budget', title_fa: 'بودجه‌ی این فرمان تمام شد', detail_fa: 'دو پست از سه آماده است؛ سومی حدود 120 هزار واحد بیشتر لازم دارد.', since: at('2026-11-02', '12:10'), fix: { action: 'budget.add', label_fa: '+200 هزار واحد بده', target: 'W-000225', tokens: 200_000 } },
    ],
    outputs: [{ ref: 'O-000059', title_fa: 'پست ۱: خط روند در یک نگاه', kind: 'post' }, { ref: 'O-000060', title_fa: 'پست ۲: هشدار قیمت', kind: 'post' }],
    summary: null, updated_at: at('2026-11-02', '12:10'),
  },
};
const OUTPUT_BODIES: Record<string, [string, string, string]> = {
  'O-000053': ['TY', 'پیشنهاد Claude: محتوای هفته‌ی آینده', 'کاپیتان: کار را به چهار بخش کرد و برنامه را نوشت.'],
  'O-000054': ['TY', 'پیشنهاد Gemini: روند و رقبا', 'سه رقیب و روند محتوای آموزشی صرافی‌ها، با منبع.'],
  'O-000055': ['TY', 'پیشنهاد DeepSeek: هزینه و بازده', 'هزینه‌ی هر ریلز و بازده پیش‌بینی‌شده؛ عددهای پژوهشگر سنجیده شد.'],
  'O-000056': ['TY', 'نقد GPT: زاویه‌ی دیگر', 'ریلز روزانه بدون آزمایش طول، هزینه را بالا میبرد؛ یک هفته آزمایش.'],
  'O-000058': ['FX', 'آموزش فارکس برای تازه‌کارها: از صفر تا اولین معامله', 'مقاله‌ی 1800 کلمه‌ای با کلمه‌ی کلیدی «آموزش فارکس»، با سه منبع.'],
  'O-000059': ['PC', 'پست ۱: خط روند در یک نگاه', 'کاروسل پنج‌تصویری؛ خط روند را با یک مثال واقعی نشان میدهد.'],
  'O-000060': ['PC', 'پست ۲: هشدار قیمت', 'کاروسل چهارتصویری؛ ساختن هشدار قیمت در سه قدم.'],
  'O-000061': ['TY', 'ریلز ۱: سه اشتباه رایج تازه‌کارها', 'ریلز 30 ثانیه‌ای با زیرنویس؛ آماده‌ی انتشار.'],
  'O-000062': ['TY', 'ریلز ۲: حد ضرر در یک دقیقه', 'ریلز 30 ثانیه‌ای با زیرنویس؛ آماده‌ی انتشار.'],
  'O-000063': ['TY', 'ریلز ۳: کارمزد را کجا ببینیم', 'ریلز 30 ثانیه‌ای با زیرنویس؛ آماده‌ی انتشار.'],
  // ⟨1.0.1⟩ §55.2 the outputs the publish desk shows beside the ones above (their files and publications are in ./mock-v47)
  'O-000064': ['FX', 'ریلز: مقاومت هفته', 'ریلز 30 ثانیه‌ای از سطح مقاومت این هفته.'],
  'O-000065': ['PC', 'موشن‌گرافی روز: واگرایی در RSI', 'موشن‌گرافی 30 ثانیه‌ای؛ بسته‌ی دیروز کارگروه.'],
  'O-000066': ['PC', 'موشن‌گرافی روز: باند بولینگر', 'موشن‌گرافی 30 ثانیه‌ای؛ بسته‌ی امروز کارگروه.'],
  'O-000067': ['TY', 'ریلز: حد ضرر را کجا بگذاریم', 'ریلز 30 ثانیه‌ای با کاور؛ آماده‌ی انتشار.'],
};
/** ⟨1.0.1⟩ when an output of a later session was made, and what it cost (the session's end leaf adds these up). */
const OUTPUT_AT: Record<string, string> = { 'O-000067': '2026-11-10T06:19:00Z', 'O-000066': '2026-11-10T04:10:00Z', 'O-000065': '2026-11-09T04:10:00Z', 'O-000064': '2026-11-10T02:00:00Z' };
const OUTPUT_USAGE: Record<string, Record<string, unknown>> = { 'O-000067': { input_tokens: 182_000, output_tokens: 41_000, cache_read_tokens: 96_000, cache_write_tokens: 12_000, equiv_cost_usd: '3.84' } };
const deliverable = (ref: string) => {
  const [company, title, summary] = OUTPUT_BODIES[ref]!;
  const producer = { code: `${company}-MEDIA-MGR`, company, kind: 'manager', department: 'MEDIA', title_fa: 'مدیر رسانه' };
  return {
    id: `o-${ref.toLowerCase()}`, ref, company, work_id: null, work_ref: null, producer, title, summary, body: `## خلاصه\n${summary}`, attachments: [], evidence: [],
    produced_with: { label_fa: 'Sonnet 5.5 · medium' }, usage: OUTPUT_USAGE[ref] ?? {}, rating: null, created_at: OUTPUT_AT[ref] ?? at('2026-11-02', '12:05'), category: 'work', seen_at: null, filed_as: null,
  };
};
let orderSeq = 10;
const created: any[] = [];
const ORDER_ITEMS = () => [
  ...created,
  ...['F-0007', 'F-0006', 'F-0005'].map((r) => reports[r]),
].map((r) => ({ ref: r.ref, text: r.text_fa, text_fa: r.text_fa, source: 'voice', file_id: null, created_at: r.at, state: r.state, summary: r.summary?.done_fa ?? null, summary_fa: summaryLine(r), routes: [] }));
function summaryLine(r: Report): string {
  if (r.summary) return r.summary.done_fa;
  if (r.blockers.length) return `گیر: ${r.blockers[0].title_fa}`;
  return r.steps.at(-1)?.what_fa ?? 'رسید؛ برنامه در راه است.';
}

// ======================================================================================== the secretary ==
const OUTPUT_FA: Record<string, string> = { post: 'پست', reel: 'ریلز', story: 'استوری', article: 'مقاله', report: 'گزارش', plan: 'برنامه', code: 'تغییر نرم‌افزار', answer: 'پاسخ', other: 'خروجی' };
const DEPT_FA: Record<string, string> = { MEDIA: 'رسانه', GROWTH: 'رشد', TECH: 'فنی', SUPPORT: 'پشتیبانی' };
const BUDGET: Record<string, number> = { reel: 400_000, post: 120_000, story: 60_000, article: 250_000, report: 200_000, plan: 120_000, code: 300_000, answer: 60_000, other: 100_000 };
const NUM_FA: Record<string, number> = { یک: 1, دو: 2, سه: 3, چهار: 4, پنج: 5, شش: 6, هفت: 7, هشت: 8, نه: 9, ده: 10 };
const units = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')} میلیون` : `${Math.round(n / 1000)} هزار`);
function companiesIn(text: string): string[] {
  const out: Array<[number, string]> = [];
  for (const [code, re] of [['TY', /تریدیار|tradeyar/i], ['FX', /\bFX\b|اف‌?ایکس|کوینه‌پرو/i], ['PC', /پرو-?چارت|pro-?chart/i]] as Array<[string, RegExp]>) {
    const m = re.exec(text);
    if (m) out.push([m.index, code]);
  }
  return out.sort((a, b) => a[0] - b[0]).map(([, c]) => c);
}
function preview(text: string) {
  const cos = companiesIn(text);
  const kind = /کلیپ|ریلز|ویدیو|ویدئو/.test(text) ? 'reel' : /استوری/.test(text) ? 'story' : /مقاله|سئو/.test(text) ? 'article' : /پست|اینستاگرام|محتوا/.test(text) ? 'post'
    : /گزارش|تحلیل/.test(text) ? 'report' : /برنامه/.test(text) ? 'plan' : /باگ|کد|اصلاح/.test(text) ? 'code' : 'answer';
  const dept = ['reel', 'story', 'article', 'post'].includes(kind) ? 'MEDIA' : kind === 'report' ? 'GROWTH' : kind === 'code' ? 'TECH' : null;
  const n = /(\d+)\s*(?:تا|عدد)?\s*(?:ریلز|پست|استوری|مقاله|کلیپ)/.exec(text)?.[1] ?? Object.entries(NUM_FA).find(([w]) => new RegExp(`(^|\\s)${w}\\s+(ریلز|پست|استوری|مقاله|کلیپ)`).test(text))?.[1];
  const count = n == null ? null : Number(n);
  const council = /شورا/.test(text);
  const player = /با\s*جمنای/.test(text) ? 'gemini' : /با\s*جی‌?\s*پی‌?\s*تی/.test(text) ? 'gpt' : /با\s*دیپ‌?\s*سیک/.test(text) ? 'deepseek' : 'auto';
  const lead = cos[0] ?? 'HQ';
  const budget = BUDGET[kind]! * Math.max(1, count ?? 1);
  const collab = cos.slice(1);
  const preview_fa = `→ ${NAME[lead]}${dept ? `/${DEPT_FA[dept]}` : ''}${collab.length ? ` + ${collab.map((c) => NAME[c]).join('، ')}` : ''}؛ خروجی: ${count ? `${count} ` : ''}${OUTPUT_FA[kind]}؛ بودجه: ${units(budget)} واحد`;
  return {
    companies: [lead], department: dept, collaborators: collab, output_kind: kind, count, budget_tokens: budget, mode: council ? 'council' : 'single', player,
    preview_fa, confidence: cos.length ? 0.86 : 0.42,
    why_fa: cos.length ? `نام ${NAME[lead]} و کلمه‌ی «${OUTPUT_FA[kind]}» در فرمان آمد.` : 'شرکتی نام برده نشد؛ مدیرعامل هلدینگ تصمیم میگیرد.',
  };
}

// ======================================================================================== rules ==
const rules: any[] = [
  { id: 'r14', ref: 'SO-014', text_md: 'هیچ فرمان رسانه‌ای به مدیر عملیات هوش مصنوعی نرود؛ همیشه به مدیر رسانه‌ی همان شرکت.', text: 'فرمان رسانه دیگر به عملیات نرود', source: 'voice', file_id: null, applies_to: 'all', status: 'proposed', version: 1, sealed_at: null, created_at: at(DAY, '05:10'), counts: null, first_report_at: null },
  { id: 'r13', ref: 'SO-013', text_md: 'هر خروجی که عدد دارد، منبع و تاریخ هر عدد را کنارش بنویسد.', text: null, source: 'text', file_id: null, applies_to: { roles: ['content_analyst', 'media_director'] }, status: 'sealed', version: 2, sealed_at: at('2026-11-01', '08:00'), created_at: at('2026-10-31', '19:20'), counts: { applied: 46, violations: 3, fixed: 3 }, first_report_at: at('2026-11-02', '08:00') },
  { id: 'r12', ref: 'SO-012', text_md: 'هیچ پستی بیرون از سری مُهرشده منتشر نشود.', text: null, source: 'voice', file_id: null, applies_to: { companies: ['TY', 'FX'] }, status: 'sealed', version: 1, sealed_at: at('2026-10-30', '10:00'), created_at: at('2026-10-30', '09:40'), counts: { applied: 112, violations: 0, fixed: 0 }, first_report_at: at('2026-10-31', '10:00') },
  { id: 'r09', ref: 'SO-009', text_md: 'گزارش‌های فنی به مدیرعامل نرود.', text: null, source: 'text', file_id: null, applies_to: 'overseer', status: 'retired', version: 1, sealed_at: at('2026-10-20', '10:00'), created_at: at('2026-10-20', '09:00'), counts: { applied: 30, violations: 4, fixed: 4 }, first_report_at: at('2026-10-21', '10:00') },
];
let ruleSeq = 15;
/** The secretary's clean-up, by rules: no filler, one imperative sentence, a full stop. */
function cleanRule(text: string): string {
  let t = text.trim().replace(/^(لطفاً|لطفا|از این به بعد|از این پس)[،,\s]*/u, '').replace(/\s+/g, ' ');
  t = t.replace(/[.!؟?]+$/u, '');
  return `${t}.`;
}
function appliesOf(text: string): any {
  const cos = companiesIn(text);
  if (cos.length) return { companies: cos };
  if (/ناظر/.test(text)) return 'overseer';
  if (/رسانه|محتوا|پست|ریلز/.test(text)) return { roles: ['media_director', 'scriptwriter', 'publisher'] };
  return 'all';
}

// ======================================================================================== the home ==
const SUGGESTIONS: any[] = [
  { id: 'SG-0012', kind: 'effective', company: 'TY', title_fa: 'هر روز یک ریلز آموزشی 30 ثانیه‌ای از سیگنال‌های تریدیار', why_fa: 'ریلزهای آموزشی هفته‌ی پیش 3.4 برابر پست عادی دیده شدند.', impact_fa: 'حدود 1,200 دنبال‌کننده‌ی تازه در ماه', cost_fa: 'حدود 900 هزار واحد مصرف در ماه', source: 'group', state: 'new', reason_fa: null, order_ref: null, created_at: at(DAY, '04:00') },
  { id: 'SG-0013', kind: 'good', company: 'FX', title_fa: 'صفحه‌ی «آموزش فارکس برای تازه‌کارها» در سایت FX', why_fa: 'این عبارت ماهی 8,100 بار جست‌وجو میشود و FX در صفحه‌ی دوم گوگل است.', impact_fa: 'حدود 600 بازدید تازه در ماه از گوگل', cost_fa: 'حدود 250 هزار واحد، یک بار', source: 'council', state: 'new', reason_fa: null, order_ref: null, created_at: at(DAY, '04:00') },
  { id: 'SG-0014', kind: 'effective', company: 'PC', title_fa: 'سری پست «یک ابزار در هفته» برای پرو-چارت', why_fa: 'پست‌های معرفی ابزار پرو-چارت بیشترین ذخیره را داشتند.', impact_fa: 'حدود 300 دنبال‌کننده‌ی تازه در ماه', cost_fa: 'حدود 400 هزار واحد در ماه', source: 'advisor', state: 'new', reason_fa: null, order_ref: null, created_at: at(DAY, '04:00') },
  { id: 'SG-0015', kind: 'good', company: 'TY', title_fa: 'استوری نظرسنجی هفتگی «کدام ارز را آموزش بدهیم؟»', why_fa: 'استوری‌های پرسشی تریدیار دو برابر پاسخ گرفتند.', impact_fa: 'حدود 15% تعامل بیشتر', cost_fa: 'حدود 60 هزار واحد در هفته', source: 'group', state: 'new', reason_fa: null, order_ref: null, created_at: at(DAY, '04:00') },
];
const PROGRESS = { id: 'PG-0004', company: 'TY', title_fa: 'دنبال‌کننده‌های اینستاگرام تریدیار', before: { value: 18_240, at: '2026-10-27' }, after: { value: 18_915, at: DAY }, kpi: 'followers', source: 'instagram', work_ref: null };
const MORNING = [
  'دیروز 6 خروجی آماده شد: 3 ریلز تریدیار، 2 پست پرو-چارت و 1 مقاله‌ی FX.',
  'بهترین حرکت: بازدید ریلزهای تریدیار 38% بالا رفت.',
  'فرمان کلیپ تریدیار آماده است و منتظر مُهر سری انتشار شماست.',
  'پیشنهاد مؤثر امروز: ریلز آموزشی روزانه برای تریدیار.',
  'از شما: مُهر یک سری انتشار و یک تصمیم درباره‌ی بودجه‌ی پرو-چارت.',
];
const CRITICAL = [
  {
    id: '0193c0de-29a1-7c00-8e00-00000000c001', company: 'PC', level: 'urgent', title_fa: 'سایت پرو-چارت 22 دقیقه از دسترس خارج بود',
    body_fa: 'از 05:40 تا 06:02 به وقت تهران صفحه‌ی اصلی باز نمیشد. مدیر فنی پرو-چارت علت را پیدا کرد و سایت برگشت؛ گزارشش تا ظهر میاید.',
    created_at: at(DAY, '02:35'), read_at: null, state: 'sent', delivered: {}, choices: null, answer: null, link: null,
    domain: 'tech', owner_visible: true, routed_to: 'PC-TECH-MGR', critical_reason: 'product_down',
  },
];
const homeSlot = (kind: 'effective' | 'good') => SUGGESTIONS.find((s) => s.kind === kind && (s.state === 'new' || s.state === 'run')) ?? null;
const homeOut = () => ({
  cards: { effective: homeSlot('effective'), good: homeSlot('good'), progress: PROGRESS },
  morning: MORNING,
  groups: [{ key: 'content', title_fa: GROUP.title_fa, companies: ['TY', 'FX', 'PC'].map((c) => ({ code: c, name_fa: NAME[c], kpi: { key: 'reach', title_fa: 'بازدید روزانه', unit: '', series: series(c, 'reach') } })) }],
  orders: ORDER_ITEMS().slice(0, 4).map((o) => ({ ref: o.ref, text_fa: o.text_fa, state: o.state, summary_fa: o.summary_fa })),
  critical: CRITICAL,
});

// ======================================================================================== employee state ==
const STATE: Record<string, { state: string; stuck?: any }> = {
  'TY-MEDIA-MGR': { state: 'waiting' }, 'TY-MEDIA-01': { state: 'done' }, 'TY-MEDIA-02': { state: 'thinking' }, 'TY-MEDIA-04': { state: 'done' },
  'TY-GROWTH-02': { state: 'working' }, 'TY-CEO': { state: 'idle' },
  'FX-MEDIA-MGR': { state: 'working' }, 'FX-MEDIA-01': { state: 'done' },
  'FX-MEDIA-03': { state: 'stuck', stuck: { reason_fa: 'تلگرام FX وصل نیست؛ ریلز آماده نمیتواند آن‌جا منتشر شود.', fix: { action: 'connection.guide', label_fa: 'وصل کردن تلگرام', target: 'FX/telegram' } } },
  'PC-MEDIA-02': { state: 'stuck', stuck: { reason_fa: 'بودجه‌ی فرمان پست‌های پرو-چارت تمام شد.', fix: { action: 'budget.add', label_fa: '+200 هزار واحد بده', target: 'W-000225', tokens: 200_000, order: 'F-0005' } } },
};
const decorate = (e: any) => {
  if (!e || typeof e !== 'object' || !e.code) return e;
  const s = STATE[e.code];
  const state = s?.state ?? (e.activity === 'working' ? 'working' : e.activity === 'waiting' ? 'waiting' : 'idle');
  return { ...e, state, stuck: s?.stuck ?? null };
};

// ======================================================================================== «شرکت ← فنی» ==
const TECH_FINDINGS: any[] = [
  { id: 'tf1', ref: 'FI-0031', company: 'PC', protocol: 'PR-070', severity: 'high', title_fa: 'پورت دیتابیس پرو-چارت روی اینترنت باز است', body_md: 'پورت 5432 از بیرون جواب میدهد؛ فقط باید روی شبکه‌ی خصوصی باشد.', evidence: [], answerable: null, due_at: null, closed_at: null, history: [], status: 'open', opened_at: at(DAY, '01:10'), updated_at: at(DAY, '01:10'), owner: null, domain: 'security', owner_visible: false, routed_to: 'PC-TECH-MGR', critical_reason: null },
  { id: 'tf2', ref: 'FI-0030', company: 'PC', protocol: 'PR-012', severity: 'medium', title_fa: 'گواهی امنیتی سایت پرو-چارت 9 روز دیگر تمام میشود', body_md: 'تمدید خودکار دو بار ناموفق بوده است.', evidence: [], answerable: null, due_at: null, closed_at: null, history: [], status: 'open', opened_at: at('2026-11-02', '22:00'), updated_at: at('2026-11-02', '22:00'), owner: null, domain: 'infra', owner_visible: false, routed_to: 'PC-TECH-MGR', critical_reason: null },
  { id: 'tf3', ref: 'FI-0029', company: 'TY', protocol: 'PR-031', severity: 'low', title_fa: 'گزارش شبانه‌ی معاملات تریدیار هر شب یک بار دوباره راه میافتد', body_md: 'کار گزارش روزانه هر شب یک بار از نو شروع میشود؛ داده گم نشده.', evidence: [], answerable: null, due_at: null, closed_at: null, history: [], status: 'open', opened_at: at('2026-11-02', '20:00'), updated_at: at('2026-11-02', '20:00'), owner: null, domain: 'tech', owner_visible: false, routed_to: 'TY-TECH-MGR', critical_reason: null },
  { id: 'tf4', ref: 'FI-0027', company: 'FX', protocol: 'PR-031', severity: 'medium', title_fa: 'صفحه‌ی ثبت‌نام FX روی موبایل کند است', body_md: 'میانگین بارگذاری 4.2 ثانیه؛ هدف زیر 2 ثانیه.', evidence: [], answerable: null, due_at: null, closed_at: null, history: [], status: 'acknowledged', opened_at: at('2026-11-01', '09:00'), updated_at: at('2026-11-02', '09:00'), owner: null, domain: 'tech', owner_visible: false, routed_to: 'FX-TECH-MGR', critical_reason: null },
];
const TECH_NOTIFICATIONS: any[] = [
  { id: '0193c0de-29a1-7c00-8e00-00000000c101', company: 'PC', level: 'urgent', title_fa: 'سایت پرو-چارت 22 دقیقه از دسترس خارج بود', body_fa: 'مدیر فنی پرو-چارت علت را پیدا کرد؛ سایت برگشت.', created_at: at(DAY, '02:35'), read_at: null, state: 'sent', delivered: {}, choices: null, answer: null, link: null, domain: 'tech', owner_visible: true, routed_to: 'PC-TECH-MGR', critical_reason: 'product_down' },
  { id: '0193c0de-29a1-7c00-8e00-00000000c102', company: 'PC', level: 'info', title_fa: 'پشتیبان شبانه‌ی پرو-چارت کامل شد', body_fa: 'پشتیبان دیتابیس و فایل‌ها ساعت 03:00 ساخته و آزموده شد.', created_at: at(DAY, '00:00'), read_at: null, state: 'sent', delivered: {}, choices: null, answer: null, link: null, domain: 'infra', owner_visible: false, routed_to: 'PC-TECH-MGR', critical_reason: null },
  { id: '0193c0de-29a1-7c00-8e00-00000000c103', company: 'TY', level: 'report', title_fa: 'بازبینی ماهانه‌ی کد تریدیار آماده شد', body_fa: 'دو مورد کد مرده و یک تست جاافتاده؛ مدیر فنی تا پنجشنبه اصلاح میکند.', created_at: at('2026-11-02', '18:00'), read_at: null, state: 'sent', delivered: {}, choices: null, answer: null, link: null, domain: 'tech', owner_visible: false, routed_to: 'TY-TECH-MGR', critical_reason: null },
];

// ======================================================================================== council v2 ==
export const COUNCIL_V2 = {
  work_ref: 'W-000199', state: 'done', synthesis_ref: 'O-000057', media: null, round: 3,
  roles: { claude: 'captain', gemini: 'researcher', deepseek: 'numbers', gpt: 'devil' },
  fact_pack_ref: 'FP-0003',
  fact_pack: {
    company: 'TY', at: at('2026-11-02', '05:00'),
    figures: [
      { key: 'followers', title_fa: 'دنبال‌کننده‌ی اینستاگرام', value: 18_790, source: 'instagram', at: '2026-11-02' },
      { key: 'reach', title_fa: 'بازدید روزانه‌ی اینستاگرام', value: 8_510, source: 'instagram', at: '2026-11-02' },
      { key: 'members', title_fa: 'اعضای کانال سیگنال', value: 12_440, source: 'telegram', at: '2026-11-02' },
      { key: 'clicks', title_fa: 'کلیک روزانه از گوگل', value: 1_180, source: 'search_console', at: '2026-11-02' },
    ],
    recent_posts: [{ title_fa: 'ریلز: سه اشتباه رایج تازه‌کارها', at: '2026-11-01', kind: 'reel', reach: 14_200 }, { title_fa: 'پست: کارمزد معامله‌ی آنی', at: '2026-10-31', kind: 'post', reach: 3_900 }],
    notes_fa: 'بی‌رمز و بی‌داده‌ی شخصی؛ از داده‌ی ستاد و اتصال‌ها.',
  },
  plan_md: [
    '1. **این هفته:** هر روز یک ریلز آموزشی 30 ثانیه‌ای؛ موضوع‌ها از پرسش‌های پرتکرار پشتیبانی. (مدیر رسانه، تا پنجشنبه)',
    '2. **دوشنبه و چهارشنبه:** یک کاروسل «مقایسه‌ی کارمزد» با عدد واقعی و منبع. (طراح، هر هفته)',
    '3. **هر شب:** خلاصه‌ی سیگنال‌های روز در کانال تلگرام با لینک ریلز همان روز. (مسئول انتشار)',
    '4. **سئو:** صفحه‌ی «آموزش خرید تتر» برای عبارتی که ماهی 12,000 بار جست‌وجو میشود. (نویسنده، تا 10 روز)',
    '5. **آزمایش:** ریلز 15 ثانیه‌ای در برابر 30 ثانیه‌ای؛ معیار: نرخ تماشای کامل. (تحلیلگر، یک هفته)',
    '6. **هزینه:** حدود 1.1 میلیون واحد در هفته؛ اگر رشد دنبال‌کننده زیر 1% ماند، ریلز یک روز در میان.',
  ].join('\n'),
  members: [
    { player: 'claude', model: 'claude-opus-5-5', state: 'done', run_id: null, deliverable_ref: 'O-000053', reason: null },
    { player: 'gemini', model: 'gemini-3-pro', state: 'done', run_id: null, deliverable_ref: 'O-000054', reason: null },
    { player: 'deepseek', model: 'deepseek-v4', state: 'done', run_id: null, deliverable_ref: 'O-000055', reason: null },
    { player: 'gpt', model: 'gpt-5.5', state: 'done', run_id: null, deliverable_ref: 'O-000056', reason: null },
  ],
};

// ======================================================================================== transcribe sessions ==
const stt: Record<string, { chunks: Set<number>; purpose: string }> = {};
let sttSeq = 0;
const STT_TEXT = ['برای تریدیار یک برنامه‌ی محتوای یک‌ماهه بنویس', 'هر روز یک ریلز آموزشی و دو استوری', 'و هر هفته یک گزارش از عددهای اینستاگرام و تلگرام برای من بفرست', 'با بودجه‌ای که از پاکت ماه بیرون نزند'];

// ======================================================================================== the router ==
/** §29's routes in the demo; null hands the request on. [next] answers what is not §29 (decorated where §29 adds fields). */
export async function handle29(req: Request, p: string, q: URLSearchParams, next: (r: Request) => Promise<Response>): Promise<Response | null> {
  const m = req.method;
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;
  const stepUp = req.headers.get('X-Step-Up');

  // ---------------------------------------------------------------------------------------------- the home --
  if (p === '/home' && m === 'GET') return json(homeOut());
  const sg = /^\/home\/suggestions\/([^/]+)$/.exec(p);
  if (sg && m === 'POST') {
    const s = SUGGESTIONS.find((x) => x.id === sg[1]);
    if (!s) return problem(404, 'not_found', 'این پیشنهاد پیدا نشد.');
    const b = await body<{ action: string; reason_fa?: string }>();
    if (b.action === 'no' && !b.reason_fa?.trim()) return problem(422, 'validation_failed', 'یک دلیل کوتاه بنویس.');
    s.state = b.action;
    s.reason_fa = b.reason_fa ?? null;
    if (b.action === 'run') s.order_ref = makeOrder(s.title_fa, preview(`${NAME[s.company]} ${s.title_fa}`)).ref;
    return json(s);
  }

  // ---------------------------------------------------------------------------------------------- orders --
  if (p === '/orders/preview' && m === 'POST') {
    const b = await body<{ text: string }>();
    if (!b.text?.trim()) return problem(422, 'validation_failed', 'متن فرمان لازم است.');
    return json(preview(b.text));
  }
  if (p === '/orders' && m === 'GET') {
    const old = ((await (await next(req)).json()) as { items?: any[] }).items ?? [];
    return json({ items: [...ORDER_ITEMS(), ...old.map((o) => ({ ...o, state: o.state ?? 'delivered' }))], next_cursor: null });
  }
  if (p === '/orders' && m === 'POST') {
    const b = await body<{ text: string; route?: any }>();
    if (!b.text?.trim()) return problem(422, 'validation_failed', 'متن فرمان لازم است.');
    const route = b.route ?? preview(b.text);
    const r = makeOrder(b.text.trim(), route);
    const lead = route.companies?.[0] ?? 'HQ';
    const to = route.department ? `${lead}-${route.department}-MGR` : `${lead}-CEO`;
    return json({ ref: r.ref, summary_fa: `دریافت شد؛ به ${route.department ? `${DEPT_FA[route.department] ?? 'دپارتمان'}ی ${NAME[lead]}` : `مدیرعامل ${NAME[lead]}`} سپرده شد.`, routes: [{ company: lead, to, kind: 'work' }] }, 201);
  }
  const rep = /^\/orders\/(F-\d+)\/report$/.exec(p);
  if (rep && m === 'GET') {
    const r = reports[rep[1]!];
    return r ? json(r) : problem(404, 'not_found', 'گزارش این فرمان پیدا نشد.');
  }
  const fix = /^\/orders\/(F-\d+)\/fix$/.exec(p);
  if (fix && m === 'POST') {
    const r = reports[fix[1]!];
    if (!r) return problem(404, 'not_found', 'این فرمان پیدا نشد.');
    const b = await body<{ action: string; target?: string; tokens?: number }>();
    const i = r.blockers.findIndex((x: any) => x.fix?.action === b.action);
    if (i < 0) return problem(409, 'conflict', 'این گیر دیگر باز نیست.');
    if ((b.action === 'series.seal' || b.action === 'hiring.open') && !stepUp) return needStepUp();
    const t = at(DAY, '06:30');
    const said: Record<string, string> = {
      'series.seal': 'سری انتشار مُهر شد؛ انتشار از فردا صبح شروع میشود.', hire: 'مسئول انتشار استخدام شد و کار را برداشت.',
      'budget.add': `${units(b.tokens ?? 200_000)} واحد به بودجه اضافه شد؛ کار ادامه دارد.`, 'player.auto': 'بازیکن به «خودکار» برگشت؛ کار ادامه دارد.',
      'hiring.open': 'استخدام باز شد.',
    };
    r.blockers.splice(i, 1);
    r.steps.push({ at: t, who_fa: 'مدیر کل', what_fa: said[b.action] ?? 'گیر برطرف شد.' });
    if (!r.blockers.length && (r.state === 'blocked' || r.state === 'waiting')) r.state = 'in_progress';
    r.updated_at = t;
    if (b.action === 'hire') { const mem = members.find((x) => x.company === 'TY'); const s = mem?.seats.find((x: any) => x.seat === 'publisher'); if (s) s.employee = 'TY-MEDIA-03'; }
    if (b.action === 'budget.add') STATE['PC-MEDIA-02'] = { state: 'working' };
    return json(r);
  }

  // ---------------------------------------------------------------------------------------------- long voice --
  if (p === '/transcribe/sessions' && m === 'POST') {
    const id = `ts-${++sttSeq}`;
    stt[id] = { chunks: new Set(), purpose: (await body<{ purpose?: string }>()).purpose ?? 'order' };
    return json({ id }, 201);
  }
  const ck = /^\/transcribe\/sessions\/([^/]+)\/chunks\/(\d+)$/.exec(p);
  if (ck && m === 'PUT') {
    const s = stt[ck[1]!];
    if (!s) return problem(404, 'not_found', 'این جلسه‌ی صدا پیدا نشد یا منقضی شد.');
    s.chunks.add(Number(ck[2]));
    await new Promise((ok) => setTimeout(ok, 150));
    return json({ n: Number(ck[2]), received: true });
  }
  const fin = /^\/transcribe\/sessions\/([^/]+)\/finish$/.exec(p);
  if (fin && m === 'POST') {
    const s = stt[fin[1]!];
    if (!s) return problem(404, 'not_found', 'این جلسه‌ی صدا پیدا نشد یا منقضی شد.');
    await new Promise((ok) => setTimeout(ok, 400));
    const n = Math.max(1, s.chunks.size);
    const text = STT_TEXT.slice(0, Math.min(STT_TEXT.length, n + 1)).join('، ');
    return json({ text: `${text}.`, duration_s: n * 90, chunks: n, segments: [] });
  }

  // ---------------------------------------------------------------------------------------------- rules --
  if (p === '/rules' && m === 'GET') return json([...rules].sort((a, b) => b.created_at.localeCompare(a.created_at)));
  if (p === '/rules' && m === 'POST') {
    const b = await body<{ text: string; source: string; file_id?: string | null }>();
    if (!b.text?.trim()) return problem(422, 'validation_failed', 'متن قانون لازم است.');
    const r = { id: `r${ruleSeq}`, ref: `SO-${String(ruleSeq++).padStart(3, '0')}`, text_md: cleanRule(b.text), text: b.text, source: b.source, file_id: b.file_id ?? null, applies_to: appliesOf(b.text), status: 'proposed', version: 1, sealed_at: null, created_at: at(DAY, '06:00'), counts: null, first_report_at: null };
    rules.unshift(r);
    return json(r, 201);
  }
  const rs = /^\/oversight\/orders\/(SO-\d+)\/seal$/.exec(p);
  if (rs && m === 'POST' && rules.some((r) => r.ref === rs[1])) {
    if (!stepUp) return needStepUp();
    const r = rules.find((x) => x.ref === rs[1])!;
    Object.assign(r, { status: 'sealed', sealed_at: at(DAY, '06:05') });
    return json(r);
  }
  const ru = /^\/rules\/(SO-\d+)(\/retire)?$/.exec(p);
  if (ru) {
    const r = rules.find((x) => x.ref === ru[1]);
    if (!r) return problem(404, 'not_found', 'این قانون پیدا نشد.');
    if (ru[2] && m === 'POST') { r.status = 'retired'; return json(r); }
    if (!ru[2] && m === 'PUT') {
      if (!stepUp) return needStepUp();
      const b = await body<{ text: string }>();
      if (!b.text?.trim()) return problem(422, 'validation_failed', 'متن قانون لازم است.');
      Object.assign(r, { text_md: cleanRule(b.text), text: b.text, version: r.version + 1, status: 'sealed', sealed_at: at(DAY, '06:10') });
      return json(r);
    }
  }

  // ---------------------------------------------------------------------------------------------- groups --
  if (p === '/groups' && m === 'GET') return json([groupOut()]);
  const gr = /^\/groups\/([a-z_]+)(?:\/(members|runs|kpis|experiments)(?:\/([A-Z][A-Z0-9]{1,9}))?|\/routines\/([a-z_]+))?$/.exec(p);
  if (gr) {
    if (gr[1] !== 'content') return problem(404, 'not_found', 'این کارگروه پیدا نشد.');
    const co = q.get('company');
    if (!gr[2] && !gr[4] && m === 'GET') return json(groupOut());
    if (gr[2] === 'members' && !gr[3] && m === 'GET') return json(members);
    if (gr[2] === 'members' && gr[3] && m === 'PUT') {
      const mem = members.find((x) => x.company === gr[3]);
      if (!mem) return problem(404, 'not_found', 'این شرکت عضو کارگروه نیست.');
      mem.state = (await body<{ state: string }>()).state === 'paused' ? 'paused' : 'on';
      const pc = READINESS[mem.company]?.find((c) => c.key === 'membership');
      if (pc) pc.ok = mem.state === 'on';
      return json(mem);
    }
    if (gr[2] === 'runs' && m === 'GET') return json(RUNS.filter((r) => !co || r.company === co).map((r) => ({ ...r, group: 'content' })));
    if (gr[2] === 'kpis' && m === 'GET') return json(kpiRows(co));
    if (gr[2] === 'experiments' && m === 'GET') return json(EXPERIMENTS.filter((x) => !co || x.company === co));
    if (gr[4] && m === 'PUT') {
      if (!(gr[4] in routineState)) return problem(404, 'not_found', 'این روال پیدا نشد.');
      routineState[gr[4]] = (await body<{ state: string }>()).state === 'paused' ? 'paused' : 'on';
      return json({ ...ROUTINES.find((r) => r.key === gr[4]), state: routineState[gr[4]] });
    }
  }

  // ---------------------------------------------------------------------------------------------- readiness --
  const rd = /^\/companies\/([A-Z][A-Z0-9]{1,9})\/readiness(\/fix)?$/.exec(p);
  if (rd) {
    const code = rd[1]!;
    if (!rd[2] && m === 'GET') return READINESS[code] ? json(readinessOut(code)) : problem(404, 'not_found', 'این شرکت عضو این کارگروه نیست.');
    if (rd[2] && m === 'POST') {
      const b = await body<{ action: string; target?: string }>();
      const c = READINESS[code]?.find((x) => x.fix?.action === b.action && !x.ok);
      if (!c) return problem(409, 'conflict', 'این مورد دیگر باز نیست.');
      c.ok = true;
      c.detail_fa = b.action === 'hire' ? 'استخدام شد؛ همه‌ی جایگاه‌ها پر است.' : b.action === 'media.on' ? 'روشن شد؛ هر وقت لازم شود کار میکند.' : b.action === 'member.resume' ? 'عضویت ادامه دارد.' : 'درست شد.';
      c.fix = null;
      if (b.action === 'member.resume') { const mem = members.find((x) => x.company === code); if (mem) mem.state = 'on'; }
      if (b.action === 'hire') { const mem = members.find((x) => x.company === code); for (const s of mem?.seats ?? []) if (!s.employee) s.employee = `${code}-MEDIA-0${(mem!.seats.indexOf(s) % 4) + 1}`; }
      return json(readinessOut(code));
    }
  }

  // ---------------------------------------------------------------------------------------------- connections --
  const cn = /^\/companies\/([A-Z][A-Z0-9]{1,9})\/connections(?:\/([a-z_0-9]+)(\/secret|\/test)?)?$/.exec(p);
  if (cn) {
    const code = cn[1]!;
    const list = connections[code];
    if (!list) return problem(404, 'not_found', 'این شرکت پیدا نشد.');
    if (!cn[2] && m === 'GET') return json(list);
    const c = list.find((x) => x.kind === cn[2]);
    if (!c) return problem(404, 'not_found', 'این اتصال پیدا نشد.');
    if (!cn[3] && m === 'PUT') {
      const b = await body<{ config?: Record<string, unknown> }>();
      c.config = { ...c.config, ...(b.config ?? {}) };
      if (c.state === 'not_connected' && (c.secret === 'set' || c.kind === 'instagram' || c.kind === 'pagespeed')) c.state = 'connected';
      return json(c);
    }
    if (cn[3] === '/secret' && m === 'PUT') {
      if (!stepUp) return needStepUp();
      const b = await body<{ secret?: string }>();
      if (!b.secret?.trim()) return problem(422, 'validation_failed', 'رمز خالی است.');
      c.secret = 'set';
      if (c.state === 'error') { c.state = 'connected'; c.last_error_fa = null; c.last_read_at = at(DAY, '06:20'); }
      // Write-only: the answer never carries what was written.
      return json(c);
    }
    if (cn[3] === '/test' && m === 'POST') {
      const good = c.state === 'connected' || (c.secret === 'set' && Object.keys(c.config).length > 0);
      if (good && c.state !== 'connected') { c.state = 'connected'; c.last_error_fa = null; }
      return json({ ok: good, message_fa: good ? 'اتصال درست است؛ عددهای امروز خوانده شد.' : c.last_error_fa ?? 'هنوز تنظیم یا رمز کامل نیست.', ...c });
    }
  }
  const gd = /^\/connections\/guides\/([a-z_0-9]+)$/.exec(p);
  if (gd && m === 'GET') return json(guideOf(gd[1]!));

  // ---------------------------------------------------------------------------------------------- outputs --
  const dv = /^\/deliverables\/(O-\d+)$/.exec(p);
  if (dv && m === 'GET' && OUTPUT_BODIES[dv[1]!]) return json(deliverable(dv[1]!));

  // ---------------------------------------------------------------------------------------------- the council v2 --
  if (p === '/work/W-000199/council' && m === 'GET') return json(COUNCIL_V2);

  // ---------------------------------------------------------------------------------------------- «شرکت ← فنی» --
  if ((p === '/oversight/findings' || p === '/notifications') && m === 'GET' && q.get('scope') === 'all') {
    const co = q.get('company');
    const d = q.get('domain');
    const src = p === '/notifications' ? TECH_NOTIFICATIONS : TECH_FINDINGS;
    return json({ items: src.filter((x) => (!co || x.company === co) && (!d || x.domain === d)), next_cursor: null });
  }

  // ---------------------------------------------------------------------------------------------- employee state --
  if (m === 'GET' && (p === '/employees' || /^\/employees\/[A-Z][A-Z0-9-]+$/.test(p) || /^\/companies\/[A-Z][A-Z0-9]{1,9}\/employees$/.test(p))) {
    const fwd = /^\/companies\/([A-Z][A-Z0-9]{1,9})\/employees$/.exec(p);
    const res = await next(fwd ? new Request(new URL(`/api/v1/employees?company=${fwd[1]}`, new URL(req.url).origin), { headers: req.headers }) : req);
    if (!res.ok) return res;
    const out = (await res.json()) as any;
    if (Array.isArray(out)) return json(out.map(decorate));
    if (out && Array.isArray(out.items)) return json({ ...out, items: out.items.map(decorate) });
    return json(decorate(out));
  }

  return null;
}

/** A new order and its report: received at once, with the secretary's receipt. */
function makeOrder(text: string, route: any) {
  const ref = `F-${String(orderSeq++).padStart(4, '0')}`;
  const lead = route.companies?.[0] ?? 'HQ';
  const t = at(DAY, '06:15');
  const r = {
    ref, text_fa: text, at: t, state: 'received',
    ack: { at: t, by: SECRETARY, plan_fa: `منشی فرمان را خواند و به ${route.department ? `${DEPT_FA[route.department] ?? 'دپارتمان'}ی ${NAME[lead]}` : `مدیرعامل ${NAME[lead]}`} سپرد؛ برنامه‌ی کار تا ده دقیقه‌ی دیگر میرسد.`, assigned: [], due_at: null },
    route: { companies: route.companies ?? [lead], department: route.department ?? null, collaborators: route.collaborators ?? [], output_kind: route.output_kind ?? 'answer', budget_tokens: route.budget_tokens ?? 100_000, mode: route.mode ?? 'single', player: route.player ?? 'auto' },
    steps: [{ at: t, who_fa: 'منشی هلدینگ', what_fa: 'فرمان را خواند و سپرد.' }],
    blockers: [], outputs: [], summary: null, updated_at: t,
  };
  reports[ref] = r;
  created.unshift(r);
  return r;
}
