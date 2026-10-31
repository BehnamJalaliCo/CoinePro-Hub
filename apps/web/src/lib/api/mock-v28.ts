// Development-only fixtures (npm run dev:mock) for contract §28 ⟨1.10⟩: the company catalogue (TradeYar's, read from its server; Pro-Chart's
// running; CoinePro FX's not yet made, so «ساختن» starts one that finishes in a few seconds), the watch's findings in its five groups
// on the same `/oversight/findings` (with `kind`, `fix_md` and `fix`), and `POST /client/errors` (kept in memory; `GET` lists them). Never bundled
// in production (reached only through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const T0 = Date.now();
const ago = (min: number) => new Date(T0 - min * 60_000).toISOString();
const ahead = (min: number) => new Date(Date.now() + min * 60_000).toISOString();
const nowIso = () => new Date().toISOString();
const OWNER = { kind: 'owner', code: 'owner', display_fa: 'مدیر کل' };
const OVR = { kind: 'agent', code: 'HQ-OVR', display_fa: 'ناظر کل' };
const ADV = { kind: 'agent', code: 'HQ-ADV', display_fa: 'مشاور کل' };
const DCEO = { kind: 'agent', code: 'HQ-DCEO', display_fa: 'مدیر کل دیجیتال' };

// ============================================================================================== the catalogue ==
const table = (title_fa: string, columns: string[], rows: Array<Array<string | number | null>>) => ({ title_fa, columns, rows });
const TY_SECTIONS = [
  {
    key: 'products', title_fa: 'محصولات و سرویس‌ها', server: 'ty-app-01',
    summary_md: '۹ کانتینر در ۳ پروژه‌ی compose، ۴ سرویس systemd و ۳ دامنه. همه بالا هستند جز `ty-report-worker` که هر شب یک بار ری‌استارت میشود.',
    tables: [
      table('کانتینرها', ['نام', 'پروژه‌ی compose', 'ایمیج', 'وضعیت', 'کار'], [
        ['ty-api', 'tradeyar', 'tradeyar/api:2.14.1', 'up 6d', 'API اصلی صرافی (FastAPI)'],
        ['ty-web', 'tradeyar', 'tradeyar/web:2.14.1', 'up 6d', 'سایت و پنل کاربر (Next.js)'],
        ['ty-worker', 'tradeyar', 'tradeyar/api:2.14.1', 'up 6d', 'صف واریز و برداشت (Celery)'],
        ['ty-report-worker', 'tradeyar', 'tradeyar/api:2.14.1', 'restarting (1/شب)', 'گزارش روزانه‌ی معاملات'],
        ['ty-postgres', 'tradeyar', 'postgres:16.4', 'up 21d', 'دیتابیس اصلی'],
        ['ty-redis', 'tradeyar', 'redis:7.4', 'up 21d', 'کش و صف'],
        ['n8n', 'automation', 'n8nio/n8n:1.82.3', 'up 12d', 'خودکارسازی کمپین و پشتیبانی'],
        ['ty-bot', 'bots', 'tradeyar/bot:1.9.0', 'up 3d', 'ربات تلگرام پشتیبانی و قیمت'],
        ['caddy', '—', 'caddy:2.8', 'up 21d', 'TLS و پراکسی معکوس'],
      ]),
      table('پورت‌ها و دامنه‌ها', ['پورت', 'شنونده', 'رو به', 'دامنه'], [
        [443, 'caddy', 'اینترنت', 'tradeyar.com، app.tradeyar.com، api.tradeyar.com'],
        [80, 'caddy', 'اینترنت', 'تغییر مسیر به HTTPS'],
        [5678, 'n8n', '127.0.0.1', '—'],
        [5432, 'ty-postgres', '127.0.0.1', '—'],
        [9100, 'node_exporter', 'شبکه‌ی خصوصی', '—'],
      ]),
      table('سرویس‌های systemd', ['واحد', 'وضعیت', 'کار'], [
        ['docker.service', 'active', 'موتور کانتینرها'],
        ['hq-runner.service', 'active', 'ارتباط با هاب (همین کاتالوگ)'],
        ['node_exporter.service', 'active', 'آمار سرور برای پایش'],
        ['ty-backup.timer', 'active', 'پشتیبان شبانه‌ی دیتابیس'],
      ]),
    ],
  },
  {
    key: 'automations', title_fa: 'خودکارسازی و زمان‌بندی', server: 'ty-app-01',
    summary_md: '۱۴ گردش‌کار n8n (۱۱ فعال)، ۳ ردیف cron و ۱ timer. گردش‌کار «یادآوری تأیید هویت» در ۷ روز ۵ بار خطا داده است.',
    tables: [
      table('گردش‌کارهای n8n', ['نام', 'محرک', 'گره‌ها', 'زمان‌بندی', 'آخرین اجرا', 'خطا (۷ روز)'], [
        ['خوش‌آمد ثبت‌نام', 'وب‌هوک ثبت‌نام', 6, '—', ago(14).slice(0, 16).replace('T', ' '), 0],
        ['یادآوری تأیید هویت', 'زمان‌بندی', 9, 'هر ۲ ساعت', ago(37).slice(0, 16).replace('T', ' '), 5],
        ['گزارش روزانه به تلگرام', 'زمان‌بندی', 5, '08:00 هر روز', ago(300).slice(0, 16).replace('T', ' '), 0],
        ['پاسخ خودکار تیکت', 'وب‌هوک پشتیبانی', 11, '—', ago(6).slice(0, 16).replace('T', ' '), 1],
        ['کمپین برگشت کاربران', 'دستی', 8, '—', ago(60 * 24 * 9).slice(0, 16).replace('T', ' '), 0],
      ]),
      table('cron و timer', ['زمان', 'فرمان', 'کاربر'], [
        ['0 3 * * *', 'pg_dump به باکت پشتیبان', 'ty-backup.timer'],
        ['*/5 * * * *', 'به‌روزرسانی نرخ‌ها', 'root (crontab)'],
        ['30 23 * * *', 'پاک‌کردن لاگ‌های بالای ۱۴ روز', 'root (crontab)'],
      ]),
    ],
  },
  {
    key: 'data', title_fa: 'داده', server: 'ty-app-01',
    summary_md: 'یک دیتابیس PostgreSQL با ۴۲ جدول؛ بزرگ‌ترین‌ها در جدول زیر. فقط تعداد ردیف خوانده شد، نه محتوا.',
    tables: [
      table('جدول‌های بزرگ', ['دیتابیس', 'جدول', 'ردیف'], [
        ['tradeyar', 'trades', 18_402_311], ['tradeyar', 'orders', 9_116_870], ['tradeyar', 'ledger_entries', 7_540_102],
        ['tradeyar', 'users', 48_219], ['tradeyar', 'kyc_requests', 31_007], ['tradeyar', 'support_tickets', 12_884],
      ]),
      table('صف‌ها و باکت‌ها', ['نام', 'نوع', 'اندازه'], [
        ['deposits', 'صف Redis', '۰ در انتظار'], ['withdrawals', 'صف Redis', '۳ در انتظار'], ['ty-backups', 'باکت S3', '41 GB، ۳۰ نسخه'],
      ]),
    ],
  },
  {
    key: 'interfaces', title_fa: 'رابط‌ها', server: 'ty-app-01',
    summary_md: 'API با ۸۷ مسیر، یک ربات با ۱۲ دستور، ۴ وب‌هوک ورودی و ۶ سرویس بیرونی (فقط نام؛ هیچ کلیدی خوانده نشد).',
    tables: [
      table('گروه‌های مسیر API', ['پیشوند', 'مسیر', 'احراز هویت'], [
        ['/v1/auth', 9, 'عمومی'], ['/v1/markets', 14, 'عمومی'], ['/v1/orders', 18, 'کاربر'], ['/v1/wallet', 21, 'کاربر + 2FA'], ['/v1/admin', 25, 'ادمین'],
      ]),
      table('ربات تلگرام', ['دستور', 'کار'], [['/price', 'قیمت لحظه‌ای'], ['/support', 'باز کردن تیکت'], ['/kyc', 'وضعیت تأیید هویت'], ['/alerts', 'هشدار قیمت']]),
      table('سرویس‌های بیرونی', ['نام', 'کار'], [['درگاه پرداخت شاپرک', 'واریز ریالی'], ['سرویس پیامک', 'کد تأیید'], ['Cloudflare', 'DNS'], ['Sentry', 'خطاهای وب']]),
    ],
  },
  {
    key: 'code', title_fa: 'کد', server: 'ty-app-01',
    summary_md: 'سه مخزن روی سرور checkout شده‌اند. پرتکرارترین خطای لاگ ۷ روز: `IntegrityError` در ثبت سفارش هم‌زمان (۲۱۴ بار).',
    tables: [
      table('مخزن‌ها', ['مخزن', 'شاخه', 'آخرین commit', 'تاریخ'], [
        ['tradeyar/api', 'main', 'a41c9e2 · Fix fee rounding on IRT pairs', ago(60 * 26).slice(0, 10)],
        ['tradeyar/web', 'main', '7be03d1 · KYC step 3 copy', ago(60 * 50).slice(0, 10)],
        ['tradeyar/bot', 'release/1.9', 'c2f8a10 · /alerts command', ago(60 * 24 * 4).slice(0, 10)],
      ]),
      table('خطاهای تکراری لاگ (۷ روز)', ['سرویس', 'خطا', 'تعداد'], [
        ['ty-api', 'IntegrityError: duplicate key on orders.client_id', 214], ['ty-report-worker', 'MemoryError در ساخت گزارش ماهانه', 7], ['n8n', 'یادآوری تأیید هویت: 429 از سرویس پیامک', 5],
      ]),
    ],
  },
  {
    key: 'risks', title_fa: 'ریسک‌ها', server: 'ty-app-01',
    summary_md: 'دو مورد جدی: گواهی `api.tradeyar.com` تا ۹ روز دیگر منقضی میشود (تمدید خودکار Caddy دو بار شکست خورده) و `node_exporter` روی شبکه‌ی خصوصی بی‌رمز است.',
    tables: [
      table('ریسک‌ها', ['مورد', 'شدت', 'جزئیات'], [
        ['گواهی TLS رو به انقضا', 'بالا', 'api.tradeyar.com، ۹ روز مانده'], ['سرویس خراب', 'متوسط', 'ty-report-worker هر شب با کمبود حافظه ری‌استارت میشود'],
        ['بسته‌ی کهنه با CVE', 'متوسط', 'pillow 10.2 در ایمیج api (CVE-2026-25125)'], ['پورت روی شبکه‌ی خصوصی', 'کم', 'node_exporter بدون احراز هویت'],
      ]),
    ],
  },
];
type Cat = { company: string; at: string | null; state: 'running' | 'done' | 'failed'; record: string | null; deliverable: string | null; reason_fa?: string | null; started_at: string | null; servers: any[]; sections: any[]; diff: Record<string, { added: string[]; removed: string[] }> | null; until?: number };
const catalogues: Record<string, Cat> = {
  TY: {
    company: 'TY', at: ago(60 * 26), state: 'done', record: 'AR-000094', deliverable: 'O-000040', started_at: ago(60 * 26 + 9),
    servers: [{ id: 'srv-ty-1', name: 'ty-app-01', state: 'done', reason_fa: null }], sections: TY_SECTIONS,
    diff: { automations: { added: ['کمپین برگشت کاربران'], removed: [] }, interfaces: { added: ['/alerts'], removed: ['/news'] } },
  },
  PC: { company: 'PC', at: null, state: 'running', record: null, deliverable: null, started_at: ago(2), servers: [{ id: 'srv-pc-1', name: 'pc-web-01', state: 'running', reason_fa: null }], sections: [], diff: null, until: Number.POSITIVE_INFINITY },
};
let nextRecord = 140;
function settle(c: Cat): Cat {
  if (c.state === 'running' && c.until != null && Date.now() >= c.until) {
    // A finished run on CoinePro FX: its own server, the same six parts.
    Object.assign(c, {
      state: 'done', at: nowIso(), record: `AR-${String(nextRecord++).padStart(6, '0')}`, deliverable: null, until: undefined,
      servers: c.servers.map((s) => ({ ...s, state: 'done' })),
      sections: TY_SECTIONS.map((s) => ({ ...s, server: c.servers[0]?.name ?? s.server, summary_md: s.key === 'products' ? '۱۱ کانتینر در ۲ پروژه‌ی compose؛ همه بالا هستند.' : s.summary_md, tables: s.tables.slice(0, 1) })),
    });
  }
  return c;
}
const catView = (c: Cat) => { const { until: _u, ...rest } = settle(c); return rest; };

// ================================================================================================== the watch ==
// As the hub serves them (§28.3): `kind`, the fix in words (`fix_md`) and, when the overseer made one, the card or session (`fix`).
type Fix = { kind: 'work' | 'workshop' | 'decision'; summary_fa: string; ref: string | null };
let fiSeq = 160;
function finding(watch: string, company: string, severity: string, title_fa: string, body_md: string, min: number, fix: Fix | null, extra: Record<string, unknown> = {}) {
  const ref = `FI-${String(fiSeq++).padStart(4, '0')}`;
  return {
    id: `fi-${ref.toLowerCase()}`, ref, company, protocol: extra.protocol ?? null, severity, title_fa, body_md, evidence: extra.evidence ?? [], status: extra.status ?? 'open',
    answerable: extra.answerable ?? { kind: 'agent', code: `${company}-CEO`, display_fa: 'مدیرعامل' }, due_at: ahead(60 * 24 * 2), opened_at: ago(min), closed_at: null,
    history: [{ at: ago(min), by: extra.raised_by ?? OVR, status: 'open', note: 'از پایش دیده‌بان' }], kind: watch,
    fix_md: fix ? `${fix.summary_fa}${extra.impact_fa ? `\n\n**اثر پیش‌بینی‌شده:** ${extra.impact_fa}` : ''}` : null,
    fix: fix && fix.ref ? { kind: fix.kind, ref: fix.ref, summary_fa: fix.summary_fa } : null,
  };
}
const fix = (kind: 'work' | 'workshop' | 'decision', summary_fa: string, ref: string | null = null): Fix => ({ kind, summary_fa, ref });
const watch: any[] = [
  finding('security', 'TY', 'high', 'گواهی TLS ‏api.tradeyar.com تا ۹ روز دیگر منقضی میشود',
    'تمدید خودکار Caddy دو بار با خطای `rate limited` شکست خورده است. اگر تا انقضا تمدید نشود، API و اپ موبایل تریدیار از کار میافتند.', 95,
    fix('work', 'مدیر فنی تریدیار تمدید را دستی اجرا کند و هشدار ۲۱ روزه برای همه‌ی دامنه‌ها بگذارد.'), { protocol: 'PR-031', server: 'ty-app-01', evidence: [{ kind: 'catalogue', ref: 'AR-000094', note: 'ریسک‌ها' }] }),
  finding('security', 'PC', 'critical', 'پورت 5432 پرو-چارت روی اینترنت باز است',
    'PostgreSQL پرو-چارت روی `0.0.0.0:5432` منتشر شده و فایروال هتزنر آن را نمیبندد. در ۲۴ ساعت گذشته ۳۱۲ تلاش ورود ناموفق از ۴۰ IP ثبت شده.', 40,
    fix('workshop', 'جلسه‌ی کارگاه کد روی سرور پرو-چارت: انتشار پورت در compose به 127.0.0.1 محدود شود.', 'S-0002'), { protocol: 'PR-030', server: 'pc-web-01', occurrences: 312 }),
  finding('security', 'HQ', 'medium', 'پشتیبان سرور هاب ۳۰ ساعت است تازه نشده',
    'آخرین پشتیبان موفق هاب ۳۰ ساعت پیش بود؛ هدف ۲۴ ساعت است. اجرای دیشب با پر بودن دیسک متوقف شد.', 180,
    fix('work', 'مهندس پلتفرم هاب فضای دیسک را آزاد کند و پشتیبان را دوباره اجرا کند.'), { protocol: 'PR-034' }),
  finding('security', 'FX', 'low', 'بسته‌ی pyasn1 با CVE در قفل وابستگی‌های FX',
    'نسخه‌ی 0.6.1 در `requirements.lock` آسیب‌پذیری شناخته‌شده دارد؛ 0.6.5 رفعش کرده.', 60 * 20,
    fix('workshop', 'به‌روزرسانی pyasn1 به 0.6.5 با هش‌ها از PyPI، در شاخه‌ی تازه و با تست‌ها.', 'coinepro-fx/app'), { protocol: 'PR-032' }),
  finding('app_health', 'HQ', 'high', 'اپ اندروید: صفحه‌ی خروجی‌ها روی نسخه‌ی 0.9.0 بسته میشود',
    '۴۷ گزارش از اپ اندروید در ۲۴ ساعت، همه با `IllegalStateException` در بارگذاری صفحه‌ی بعدی خروجی‌ها. علت در کد پیدا شد: صفحه‌بندی بعد از حذف یک خروجی کلید تکراری میسازد.', 70,
    fix('workshop', 'اصلاح کلید فهرست در Outputs.kt و یک تست واحد برای حذف وسط فهرست.', 'coinepro-hub/apps/android'), { occurrences: 47, evidence: [{ kind: 'client_errors', ref: 'android 0.9.0', note: '۴۷ مورد' }] }),
  finding('app_health', 'HQ', 'medium', 'پنل وب: ۵۰۲ پشت‌سرهم هنگام راه‌اندازی دوباره‌ی هاب',
    '۱۲ گزارش «هاب در دسترس نیست» از پنل وب، همه در ۴۰ ثانیه‌ی deploy. پنل درست رفتار کرد؛ پیشنهاد: deploy بدون قطعی با دو نسخه‌ی api.', 60 * 7,
    fix('work', 'مهندس پلتفرم هاب deploy غلتان api را طراحی کند.'), { occurrences: 12, status: 'acknowledged' }),
  finding('code', 'TY', 'high', 'ثبت سفارش هم‌زمان در API تریدیار رقابت (race) دارد',
    'بازبینی هفتگی `tradeyar/api`: در `orders/service.py` بررسی تکراری‌بودن `client_id` بیرون از تراکنش است؛ ۲۱۴ بار `IntegrityError` در لاگ هفته همین است.', 60 * 30,
    fix('workshop', 'قفل در سطح ردیف یا `ON CONFLICT` در ثبت سفارش، با تست هم‌زمانی.', 'tradeyar/api'), { protocol: 'PR-036', occurrences: 214 }),
  finding('code', 'FX', 'medium', 'کد مرده و تست جاافتاده در موتور سیگنال FX',
    '۳ ماژول بی‌استفاده در `src/signals/legacy` و هیچ تستی برای `risk_manager.position_cap`. فهرست رتبه‌دار در پیوست.', 60 * 30,
    fix('work', 'مدیر فنی FX حذف کد مرده و نوشتن تست‌های `position_cap` را برنامه‌ریزی کند.'), { protocol: 'PR-036' }),
  finding('growth', 'TY', 'info', 'سه حرکت پرارزش تریدیار این هفته',
    '1. **یادآوری تأیید هویت ۲ ساعت بعد از ثبت‌نام** (۴۱٪ رها در این مرحله) — اثر پیش‌بینی‌شده: +۰٫۶ واحد نرخ تبدیل\n2. **پاسخ خودکار تیکت برای ۵ پرسش رایج** — ‎−۳۰٪ زمان پاسخ\n3. **کمپین برگشت کاربران مهر** با پیشنهاد کارمزد صفر یک‌هفته‌ای', 60 * 40,
    fix('work', 'مدیرعامل تریدیار حرکت اول را به مدیر رشد بسپارد.'), { raised_by: ADV, impact_fa: '+۰٫۶ واحد نرخ تبدیل', answerable: { kind: 'agent', code: 'TY-CEO', display_fa: 'مدیرعامل' } }),
  finding('growth', 'FX', 'info', 'سه حرکت پرارزش CoinePro FX این هفته',
    '1. **صفحه‌ی عمومی دقت سیگنال‌ها** — اعتماد و ثبت‌نام\n2. **ربات تلگرام: خلاصه‌ی هفتگی برای مشترکان**\n3. **بسته‌ی سالانه با تخفیف**', 60 * 40, null, { raised_by: ADV, impact_fa: '+۱۲٪ ثبت‌نام ماهانه' }),
  finding('holding', 'HQ', 'info', 'پیشنهاد هلدینگ آبان: یک ورود و یک کیف پول برای سه شرکت',
    'کاربران تریدیار و CoinePro FX هم‌پوشانی ۲۳٪ دارند. یک ورود مشترک و نمایش سیگنال FX داخل تریدیار، فروش متقابل را باز میکند. پرو-چارت میتواند نمودار هر دو را بدهد.', 60 * 24 * 3,
    fix('work', 'مدیر کل دیجیتال طرح یک‌صفحه‌ای ورود مشترک را برای جلسه‌ی مدیرعامل‌ها آماده کند.'), { raised_by: DCEO, impact_fa: 'فروش متقابل میان شرکت‌ها', answerable: DCEO }),
];

// ================================================================================================ client errors ==
const clientErrors: any[] = [];

/** §28 routes of the demo; null hands the request on. */
export async function handle28(req: Request, p: string, q: URLSearchParams, base: (r: Request) => Promise<Response>): Promise<Response | null> {
  const m = req.method;

  const cat = /^\/companies\/([A-Z][A-Z0-9]{1,9})\/catalogue$/.exec(p);
  if (cat) {
    const code = cat[1]!;
    if (m === 'GET') { const c = catalogues[code]; return c ? json(catView(c)) : problem(404, 'not_found', 'هنوز کاتالوگی برای این شرکت ساخته نشده.'); }
    if (m === 'POST') {
      if (code === 'HQ') return problem(422, 'validation_failed', 'هلدینگ سرور شرکتی ندارد؛ کاتالوگ برای شرکت‌هاست.');
      const old = catalogues[code];
      if (old && settle(old).state === 'running') return json(catView(old), 202);
      const servers = old?.servers?.length ? old.servers : [{ id: `srv-${code.toLowerCase()}-1`, name: `${code.toLowerCase()}-app-01`, state: 'queued', reason_fa: null }];
      catalogues[code] = { ...(old ?? { company: code, at: null, record: null, deliverable: null, sections: [], diff: null }), servers: servers.map((s: any) => ({ ...s, state: 'running' })), state: 'running', started_at: nowIso(), until: Date.now() + 6_000 } as Cat;
      return json(catView(catalogues[code]!), 202);
    }
  }

  // The watch's findings join the overseer's own on the same list (the base fixtures answer the rest).
  if (p === '/oversight/findings' && m === 'GET') {
    const st = q.get('status');
    const res = await base(req);
    const old = ((await res.json()) as { items?: any[] }).items ?? [];
    return json({ items: [...watch.filter((f) => !st || f.status === st), ...old], next_cursor: null });
  }

  if (p === '/client/errors') {
    if (m === 'POST') {
      const b = (await req.clone().json().catch(() => ({}))) as { app?: string; version?: string; entries?: any[] };
      if (!b.app || !Array.isArray(b.entries)) return problem(422, 'validation_failed', 'app و entries لازم است.');
      let n = 0;
      for (const e of b.entries) {
        const i = clientErrors.findIndex((x) => x.app === b.app && x.version === b.version && x.entry.id === e.id);
        if (i >= 0) clientErrors[i] = { ...clientErrors[i], entry: e }; else { clientErrors.push({ app: b.app, version: b.version, received_at: nowIso(), entry: e }); n++; }
      }
      return json({ accepted: b.entries.length, new: n }, 202);
    }
    if (m === 'GET') {
      const app = q.get('app');
      const version = q.get('version');
      return json({ items: clientErrors.filter((x) => (!app || x.app === app) && (!version || x.version === version)), next_cursor: null });
    }
  }
  return null;
}
