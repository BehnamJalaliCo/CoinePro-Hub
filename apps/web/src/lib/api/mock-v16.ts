// Development-only fixtures for contract v1.5 §19 (revenue and support), used by mock.ts. Never bundled in production (next.config
// aliases the fixtures module away). Companies, channels and exchanges are data here as on the hub: nothing below counts them.
// Every outbound text the demo "sends" goes through the same guard the hub runs (§19.6), reduced to what a demo needs.

const now = Date.now();
const MIN = 60_000;
const DAY = 86_400_000;
const iso = (minAgo: number) => new Date(now - minAgo * MIN).toISOString();
const ahead = (min: number) => new Date(now + min * MIN).toISOString();
const stamp = () => new Date().toISOString();
const json = (body: unknown, status = 200, headers: Record<string, string> = {}) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } });
const page = (items: unknown[]) => ({ items, next_cursor: null });
const problem = (status: number, code: string, message_fa: string, extra: Record<string, unknown> = {}, headers: Record<string, string> = {}) =>
  json({ type: 'about:blank', title: code, status, code, message_fa, ...extra }, status, headers);
const f2 = (n: number) => n.toFixed(2);
const system = { kind: 'system', code: 'system', display_fa: 'سیستم' };
/** The settlement day n days ago (1 = yesterday, the newest settled day). */
const dayKey = (n: number) => new Date(now - n * DAY).toISOString().slice(0, 10);
/** Deterministic 0..1, so every reload of the demo draws the same month. */
const noise = (seed: number, i: number) => { const x = Math.sin(seed * 9301 + i * 49297) * 233280; return x - Math.floor(x); };
async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
/** Fills the digests the demo has not computed yet (the hub stores them with each version). */
const fill = async (xs: any[], text: (x: any) => string) => { await Promise.all(xs.filter((x) => !x.sha256).map(async (x) => { x.sha256 = await sha256(text(x)); })); return xs; };

// --------------------------------------------------------------- revenue radar --
// One LBank affiliate account per company; the holding earns nothing itself. The third one's pull fails (the hub's IP is not whitelisted).
const accounts: any[] = [
  { id: 'ra-ty', company: 'TY', title_fa: 'افیلیت LBank تریدیار', service_account: 'lbank-affiliate-ty', status: 'ok', last_pull_at: iso(60 * 4), last_error: null, base: 214, swing: 44, trend: 0.5 },
  { id: 'ra-fx', company: 'FX', title_fa: 'افیلیت LBank کوینه‌پرو FX', service_account: 'lbank-affiliate-fx', status: 'ok', last_pull_at: iso(60 * 4 - 3), last_error: null, base: 118, swing: 26, trend: 0.25 },
  { id: 'ra-pc', company: 'PC', title_fa: 'افیلیت LBank پرو-چارت', service_account: 'lbank-affiliate-pc', status: 'error', last_pull_at: iso(60 * 28), base: 52, swing: 13, trend: -0.1,
    last_error: 'pull failed twice in a row: LBank answered "IP is not in the API whitelist" (add the hub\'s public IP in the affiliate panel)' },
].map((a) => ({ exchange: 'lbank', adapter: 'lbank-affiliate-v2', version: 2, ...a }));
const accountOut = (a: any) => { const { base: _b, swing: _s, trend: _t, ...rest } = a; return rest; };
const pulledAt = new Map<string, number>();

const HISTORY = 90;
const ENDPOINTS = ['commission/stats/symbol/list', 'invite/user/team/list', 'trade/user/team', 'money/detail/list'];
const days: any[] = accounts.flatMap((a, k) => Array.from({ length: HISTORY }, (_, j) => HISTORY - j).flatMap((n) => {
  if (a.status === 'error' && n <= 2) return []; // two failed pulls in a row: those days are not in yet
  const friday = new Date(now - n * DAY).getUTCDay() === 5;
  let c = a.base * (1 + (a.trend * (HISTORY - n)) / HISTORY / 2) + (noise(k + 1, n) - 0.5) * 2 * a.swing - (friday ? a.base * 0.16 : 0);
  if (a.company === 'TY' && n === 1) c = a.base * 0.44; // the drop the radar raises
  const usdt = c * 0.72, btc = c * 0.19, eth = c - usdt - btc;
  return [{
    _n: n, company: a.company, account: a.id, day: dayKey(n), commission_usdt: f2(c),
    by_coin: [
      { coin: 'USDT', amount: f2(usdt), usdt: f2(usdt), price_source: 'par' },
      { coin: 'BTC', amount: (btc / 67_400).toFixed(8), usdt: f2(btc), price_source: 'lbank btc_usdt close' },
      { coin: 'ETH', amount: (eth / 2_610).toFixed(6), usdt: f2(eth), price_source: 'lbank eth_usdt close' },
    ],
    fees_usdt: f2(c / 0.4), volume_usdt: f2(c / 0.4 / 0.001), new_invitees: Math.round(a.base / 24 + noise(k + 7, n) * 5), active_traders: Math.round(a.base / 2.4 + noise(k + 3, n) * 20),
    deposits_usdt: f2(a.base * 38 * (0.7 + noise(k + 5, n) * 0.6)), complete: true, pulled_at: iso((n - 1) * 1440 + 240), source: { adapter: a.adapter, endpoints: ENDPOINTS },
  }];
}));
const dayOut = (d: any) => { const { _n, ...rest } = d; return rest; };
const sumOf = (xs: any[]) => xs.reduce((s, d) => s + Number(d.commission_usdt), 0);
const median = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s.length ? (s[(s.length - 1) >> 1]! + s[s.length >> 1]!) / 2 : 0; };
// The drop alert (§19.1): yesterday below 60% of the trailing 28-day median of the same weekday.
const tyYesterday = Number(days.find((d) => d.account === 'ra-ty' && d._n === 1).commission_usdt);
const tyMedian = median(days.filter((d) => d.account === 'ra-ty' && [8, 15, 22, 29].includes(d._n)).map((d) => Number(d.commission_usdt)));
const alerts = [
  { kind: 'drop', company: 'TY', account: 'ra-ty', note_fa: `کمیسیون دیروز ${f2(tyYesterday)} USDT بود، ${Math.round((tyYesterday / tyMedian) * 100)}% میانه‌ی ۲۸ روزه‌ی همان روز هفته (${f2(tyMedian)} USDT). به مدیرعامل تریدیار هم رسید.` },
  { kind: 'pull_failed', company: 'PC', account: 'ra-pc', note_fa: 'دو pull پشت‌سرهم شکست خورد؛ IP هاب در whitelist API افیلیت LBank نیست. یک کار برای SRE پلتفرم باز شد.' },
];
// Token cost of the period comes from the treasury, never from an agent: the demo's month, pro rata.
const TOKEN_MONTH: Record<string, number> = { TY: 58.1, FX: 42.3, PC: 21.6 };
const WINDOW: Record<string, number> = { day: 1, week: 7, month: 30 };
function summary(period: string, company: string | null) {
  const w = WINDOW[period] ?? 30;
  const pick = (lo: number, hi: number) => days.filter((d) => d._n >= lo && d._n <= hi && (!company || d.company === company));
  const cur = pick(1, w);
  const prev = pick(w + 1, 2 * w);
  const total = sumOf(cur);
  const own = accounts.filter((a) => !company || a.company === company);
  return {
    period, from: dayKey(w), to: dayKey(1), total_usdt: f2(total), prev_total_usdt: prev.length ? f2(sumOf(prev)) : null,
    by_company: [...new Set(own.map((a) => a.company))].map((c) => {
      const u = sumOf(cur.filter((d) => d.company === c));
      const cost = ((TOKEN_MONTH[c] ?? 0) * w) / 30;
      return { company: c, usdt: f2(u), token_cost_usd: f2(cost), net_usd: f2(u - cost), share: total ? u / total : 0 };
    }),
    by_account: own.map((a) => ({ account: a.id, company: a.company, usdt: f2(sumOf(cur.filter((d) => d.account === a.id))) })),
    trend: Array.from({ length: w }, (_, i) => w - i).map((n) => ({ day: dayKey(n), usdt: f2(sumOf(cur.filter((d) => d._n === n))) })),
    alerts: alerts.filter((x) => !company || x.company === company),
  };
}

// --------------------------------------------------------- funnel and rescue --
const FUNNEL: Record<string, { verified: number; minimum: number; median: number }> = {
  TY: { verified: 186, minimum: 62, median: 0.52 }, FX: { verified: 92, minimum: 51, median: 0.55 }, PC: { verified: 34, minimum: 19, median: 0.54 },
};
const STAGES: Array<[string, string, string | null]> = [['visit', 'بازدید', null], ['signup', 'ثبت‌نام', null], ['referral_verified', 'رفرال تأییدشده', 'affiliate'], ['min_balance', 'حداقل موجودی', 'affiliate'], ['vip_active', 'VIP فعال', null]];
function funnel(company: string, period: 'week' | 'month') {
  const f = FUNNEL[company];
  const k = period === 'week' ? 0.24 : 1;
  const counts: Record<string, number | null> = { referral_verified: f ? Math.round(f.verified * k) : null, min_balance: f ? Math.round(f.minimum * k) : null };
  // Only the affiliate data is a source today: visit waits for analytics, signup and vip_active for product events (CR-009/010).
  const stages = STAGES.map(([key, label_fa, source]) => ({ key, label_fa, source: f ? source : null, connected: !!(f && source), count: counts[key] ?? null }));
  const conversions = stages.slice(1).map((s, i) => { const a = stages[i]!; return { from: a.key, to: s.key, rate: a.count && s.count != null ? s.count / a.count : null }; });
  const rate = f ? f.minimum / f.verified : 0;
  const leaks = f && rate < f.median * 0.7 ? [{ stage: 'min_balance', rate, median_rate: f.median,
    note_fa: `فقط ${Math.round(rate * 100)}% دعوت‌شده‌های تازه به حداقل موجودی رسیدند، در برابر میانه‌ی ۴ هفته ${Math.round(f.median * 100)}%. محتمل‌ترین علت سه عدد متناقض حداقل موجودی در محصول‌هاست (CR-005)؛ یک کار برای مدیر فروش باز شد.` }] : [];
  return { company, period, from: dayKey(period === 'week' ? 7 : 30), to: dayKey(1), stages, conversions, leaks };
}

const step = (minAgo: number, kind: string, result_fa: string, template: string | null = null) => ({ at: iso(minAgo), kind, template, result_fa });
const rescue: any[] = [
  { ref: 'RC-000119', company: 'FX', source: 'support', conversation: 'SC-000405', state: 'open', subject: 'sb_4e1c9a07d2f3', opened_at: iso(138),
    steps: [step(138, 'check', 'referral.check: دعوت‌شده‌ی ما نیست؛ پرونده باز شد.')] },
  { ref: 'RC-000118', company: 'TY', source: 'support', conversation: 'SC-000411', state: 'open', subject: 'sb_9a20f61c7b44', opened_at: iso(33),
    steps: [step(33, 'check', 'referral.check: دعوت‌شده‌ی ما نیست؛ پرونده باز شد.')] },
  { ref: 'RC-000117', company: 'TY', source: 'product', conversation: null, state: 'contacted', subject: 'sb_17bd03e95a60', opened_at: iso(60 * 52),
    steps: [step(60 * 52, 'check', 'رویداد referral_failed از محصول رسید.'), step(60 * 50, 'message', 'قالب نجات فرستاده شد (ساعت سکوت رعایت شد).', 'TM-0003@1'), step(60 * 26, 'follow_up', 'پیگیری اول؛ هنوز جواب نداده.', 'TM-0003@1')] },
  { ref: 'RC-000115', company: 'FX', source: 'support', conversation: 'SC-000398', state: 'rescued', subject: 'sb_c0e7a2194d8b', opened_at: iso(60 * 24 * 6), rescued_at: iso(60 * 24 * 4), closed_at: iso(60 * 24 * 4),
    steps: [step(60 * 24 * 6, 'check', 'دعوت‌شده نیست.'), step(60 * 24 * 6 - 20, 'message', 'راهنمای ثبت‌نام دوباره با رفرال از دانشنامه.', 'TM-0010@1'), step(60 * 24 * 4, 'check', 'referral.check: دعوت‌شده‌ی ما؛ نجات یافت.')] },
  { ref: 'RC-000112', company: 'TY', source: 'product', conversation: null, state: 'lost', subject: 'sb_5d93be0c1f72', opened_at: iso(60 * 24 * 34), closed_at: iso(60 * 24 * 4),
    steps: [step(60 * 24 * 34, 'check', 'رویداد referral_failed.'), step(60 * 24 * 33, 'message', 'قالب نجات.', 'TM-0003@1'), step(60 * 24 * 30, 'follow_up', 'پیگیری دوم.', 'TM-0003@1'), step(60 * 24 * 4, 'note', '۳۰ روز بی‌نتیجه؛ از دست رفت.')] },
  { ref: 'RC-000110', company: 'FX', source: 'support', conversation: null, state: 'opted_out', subject: 'sb_e84a6107c3d9', opened_at: iso(60 * 24 * 12), closed_at: iso(60 * 24 * 11),
    steps: [step(60 * 24 * 12, 'check', 'دعوت‌شده نیست.'), step(60 * 24 * 12 - 30, 'message', 'قالب نجات.', 'TM-0010@1'), step(60 * 24 * 11, 'note', 'مشتری نوشت «لغو»؛ همه‌ی قاعده‌ها برای او قطع شد.')] },
  { ref: 'RC-000108', company: 'TY', source: 'support', conversation: null, state: 'rescued', subject: 'sb_2b6f1d8e90a4', opened_at: iso(60 * 24 * 15), rescued_at: iso(60 * 24 * 13), closed_at: iso(60 * 24 * 13),
    steps: [step(60 * 24 * 15, 'check', 'دعوت‌شده نیست.'), step(60 * 24 * 15 - 15, 'message', 'راهنمای ثبت‌نام با رفرال.', 'TM-0003@1'), step(60 * 24 * 13, 'check', 'دعوت‌شده‌ی ما؛ نجات یافت.')] },
].map((r, i) => ({ id: `rc${i}`, exchange: 'lbank', rescued_at: null, closed_at: null, ...r }));

// ---------------------------------------------------------------- support desk --
const channels: any[] = [
  { company: 'TY', kind: 'telegram_bot', state: 'live', live_since: iso(60 * 24 * 12), auto_send: 'kb_verbatim' },
  { company: 'TY', kind: 'telegram_business', state: 'shadow', auto_send: 'off' },
  { company: 'TY', kind: 'chatwoot', state: 'not_configured', auto_send: 'off' },
  { company: 'TY', kind: 'mystery', state: 'live', live_since: iso(60 * 24 * 12), auto_send: 'kb_verbatim' },
  { company: 'FX', kind: 'telegram_bot', state: 'paused', live_since: iso(60 * 24 * 20), auto_send: 'kb_verbatim', paused_reason: 'مالک متوقف کرد: دو جواب اشتباه درباره‌ی حداقل موجودی، تا مقاله‌ی تازه تأیید شود.' },
  { company: 'FX', kind: 'product_bot', state: 'not_configured', auto_send: 'off' },
  { company: 'PC', kind: 'telegram_bot', state: 'shadow', auto_send: 'off' },
].map((c) => ({ live_since: null, paused_reason: null, version: 1, ...c }));
const channelOf = (company: string, kind: string) => channels.find((c) => c.company === company && c.kind === kind);

const SAFETY = 'پشتیبانی ما هرگز رمز، کلید خصوصی، کد تأیید یا عبارت بازیابی شما را نمیخواهد.';
const HOLDING = 'پیامتان رسید؛ یکی از همکاران بزودی جواب میدهد. — پشتیبانی Coine';
const kbArticles: any[] = [
  { ref: 'KB-0001', company: 'TY', version: 2, kind: 'referral', key: null, question_fa: 'لینک و کد رفرال LBank تریدیار', variants: ['کد معرف', 'لینک ثبت‌نام LBank'],
    answer_md: 'برای VIP رایگان با این لینک ثبت‌نام کنید: https://lbank.com/ref/TYDEMO1 (کد معرف TYDEMO1).', links: [{ url: 'https://lbank.com/ref/TYDEMO1', label_fa: 'ثبت‌نام LBank با رفرال تریدیار' }], codes: [{ exchange: 'lbank', code: 'TYDEMO1' }],
    status: 'approved', source: { kind: 'owner', ref: null }, approved_at: iso(60 * 24 * 40), uses_30d: 64 },
  { ref: 'KB-0002', company: 'TY', version: 1, kind: 'official_link', key: null, question_fa: 'سایت و پنل رسمی تریدیار', variants: ['آدرس سایت', 'لینک پنل'],
    answer_md: 'سایت رسمی: https://tradeyar.trade-future.ir و پنل کاربری: https://user.tradeyar.trade-future.ir', links: [{ url: 'https://tradeyar.trade-future.ir', label_fa: 'سایت تریدیار' }, { url: 'https://user.tradeyar.trade-future.ir', label_fa: 'پنل کاربری' }], codes: [],
    status: 'approved', source: { kind: 'owner', ref: null }, approved_at: iso(60 * 24 * 40), uses_30d: 22 },
  { ref: 'KB-0003', company: 'TY', version: 1, kind: 'policy', key: 'vip.min_balance', question_fa: 'حداقل موجودی برای VIP رایگان چقدر است؟', variants: ['حداقل موجودی', 'چقدر باید پول بذارم'],
    answer_md: 'برای فعال ماندن VIP رایگان، موجودی حساب LBank شما باید دست‌کم **100 USDT** باشد.', links: [], codes: [],
    status: 'approved', source: { kind: 'owner', ref: null }, approved_at: iso(60 * 24 * 40), uses_30d: 118 },
  { ref: 'KB-0004', company: 'TY', version: 3, kind: 'faq', key: null, question_fa: 'چطور VIP رایگان را فعال کنم؟', variants: ['فعال‌سازی VIP', 'VIP نگرفتم'],
    answer_md: '۱. با لینک رفرال ما در LBank ثبت‌نام کنید.\n۲. UID حسابتان را در ربات تریدیار وارد کنید.\n۳. موجودی را به {{min_balance}} برسانید؛ VIP خودکار فعال میشود.', variables: [{ name: 'min_balance', source: 'policy' }], links: [], codes: [],
    status: 'approved', source: { kind: 'owner', ref: null }, approved_at: iso(60 * 24 * 166), uses_30d: 203 },
  { ref: 'KB-0005', company: 'TY', version: 1, kind: 'faq', key: null, question_fa: 'چرا کارمزد برداشت تتر روی شبکه‌ی ترون عوض میشود؟', variants: ['کارمزد برداشت زیاد است'],
    answer_md: 'کارمزد برداشت را خود صرافی بر اساس شلوغی شبکه تعیین میکند و تریدیار سهمی از آن ندارد. پیش از هر برداشت، کارمزد همان لحظه در صفحه‌ی برداشت LBank نشان داده میشود.', links: [], codes: [],
    status: 'proposed', source: { kind: 'owner_answer', ref: 'SC-000396' }, approved_at: null, uses_30d: 0 },
  { ref: 'KB-0006', company: 'TY', version: 1, kind: 'safety', key: null, question_fa: 'جمله‌ی ایمنی', variants: [], answer_md: SAFETY, links: [], codes: [],
    status: 'approved', source: { kind: 'owner', ref: null }, approved_at: iso(60 * 24 * 40), uses_30d: 140 },
  { ref: 'KB-0007', company: 'TY', version: 1, kind: 'procedure', key: null, question_fa: 'احراز هویت (KYC) در LBank', variants: ['احراز هویت'],
    answer_md: 'مراحل احراز هویت را در بخش Security صرافی انجام دهید؛ تریدیار هیچ مدرکی از شما نمیگیرد.', links: [], codes: [],
    status: 'expired', source: { kind: 'doc', ref: 'tradeyar.trade-future.ir/help/kyc' }, approved_at: iso(60 * 24 * 190), uses_30d: 0 },
  { ref: 'KB-0008', company: 'FX', version: 2, kind: 'faq', key: null, question_fa: 'سیگنال طلا چه ساعتی میاید؟', variants: ['ساعت سیگنال'],
    answer_md: 'سیگنال‌های طلا در ساعت‌های باز بودن بازار لندن و نیویورک صادر میشوند.', links: [], codes: [],
    status: 'retired', source: { kind: 'agent', ref: 'FX-SALES-MGR' }, approved_at: iso(60 * 24 * 60), uses_30d: 0 },
  { ref: 'KB-0009', company: 'FX', version: 2, kind: 'policy', key: 'vip.min_balance', question_fa: 'حداقل موجودی برای VIP رایگان چقدر است؟', variants: ['حداقل موجودی'],
    answer_md: 'برای VIP رایگان، موجودی حساب LBank شما باید دست‌کم **100 USDT** باشد؛ عدد ۵۰ در ربات قدیمی است و اصلاح میشود.', links: [], codes: [],
    status: 'proposed', source: { kind: 'owner_answer', ref: 'SC-000398' }, approved_at: null, uses_30d: 0 },
  { ref: 'KB-0010', company: 'FX', version: 1, kind: 'faq', key: null, question_fa: 'اشتراک سیگنال چطور تمدید میشود؟', variants: ['تمدید'],
    answer_md: 'برای کاربرانی که با رفرال ما ثبت‌نام کرده‌اند و حداقل موجودی را دارند، اشتراک رایگان است و نیاز به تمدید ندارد.', links: [], codes: [],
    status: 'approved', source: { kind: 'owner', ref: null }, approved_at: iso(60 * 24 * 30), uses_30d: 47 },
  { ref: 'KB-0011', company: 'PC', version: 1, kind: 'faq', key: null, question_fa: 'نمودار روی گوشی کند باز میشود؛ چه کنم؟', variants: ['اپ کند است'],
    answer_md: 'آخرین نسخه‌ی اپ پرو-چارت را از فروشگاه نصب کنید؛ نسخه‌ی تازه بارگذاری نمودار را دو برابر سریع‌تر کرده است.', links: [], codes: [],
    status: 'proposed', source: { kind: 'agent', ref: 'PC-GROWTH-MGR' }, approved_at: null, uses_30d: 0 },
  { ref: 'KB-0012', company: 'FX', version: 1, kind: 'procedure', key: null, question_fa: 'قبلاً ثبت‌نام کرده‌ام ولی VIP ندارم', variants: ['بدون رفرال ثبت‌نام کردم'],
    answer_md: 'اگر حسابتان با رفرال ما ساخته نشده، VIP رایگان به آن تعلق نمیگیرد. میتوانید یک حساب تازه با لینک رفرال ما بسازید.', links: [], codes: [],
    status: 'approved', source: { kind: 'owner', ref: null }, approved_at: iso(60 * 24 * 25), uses_30d: 19 },
].map((a, i) => ({
  id: `kb${i}`, variables: [], sha256: '', ...a,
  expires_at: a.approved_at ? new Date(new Date(a.approved_at).getTime() + 180 * DAY).toISOString() : ahead(60 * 24 * 180),
}));
const norm = (u: string) => u.trim().replace(/[.,،؛)»]+$/, '').replace(/\/+$/, '').toLowerCase();
/** The outbound guard (§19.6), as far as the demo needs it: links must be exactly approved; no profit promise; never ask for a seed. */
function guard(company: string, text: string): string[] {
  const out = new Set<string>();
  const approved = new Set(kbArticles.filter((a) => a.company === company && a.status === 'approved' && (a.kind === 'official_link' || a.kind === 'referral')).flatMap((a) => a.links.map((l: any) => norm(l.url))));
  for (const m of text.match(/https?:\/\/[^\s«»"']+/gi) ?? []) if (!approved.has(norm(m))) out.add('unknown_link');
  if (/سود\s*(?:‌)?تضمینی|guaranteed\s+profit/i.test(text)) out.add('profit_promise');
  if (/\bseed\b/i.test(text)) out.add('asks_secret');
  if (text.length > 2000) out.add('too_long');
  return [...out];
}

type Msg = { at: number; direction: 'in' | 'out'; author: string; body: string; status?: string; kb_refs?: string[]; confidence?: number | null; grounded?: 'pass' | 'fail' | null; blocked?: string[] };
const inMsg = (at: number, body: string): Msg => ({ at, direction: 'in', author: 'customer', body });
const ruleMsg = (at: number, body: string, kb: string[] = []): Msg => ({ at, direction: 'out', author: 'rule', body, kb_refs: kb });
const conversations: any[] = ([
  { ref: 'SC-000412', company: 'TY', channel: 'telegram_bot', customer: { display_name: 'سارا', handle_masked: '@sa•••92', lang: 'fa' }, state: 'waiting_owner', opened_at: iso(52), handoff: { reason: 'security', at: iso(51) }, tags: ['جعل هویت', 'عبارت بازیابی'],
    messages: [
      inMsg(52, 'سلام. یک اکانت تلگرام به اسم «پشتیبانی تریدیار» بهم پیام داد و گفت برای فعال شدن VIP باید عبارت بازیابی کیف پولم رو بفرستم. فرستادم: [ماسک: عبارت بازیابی]. این شما بودید؟'),
      ruleMsg(51, `${SAFETY} ${HOLDING}`, ['KB-0006@1', 'TM-0001@1']),
    ] },
  { ref: 'SC-000411', company: 'TY', channel: 'telegram_bot', customer: { display_name: null, handle_masked: '@mo•••hd', lang: 'fa' }, state: 'waiting_owner', opened_at: iso(35), handoff: { reason: 'blocked', at: iso(33) }, tags: ['رفرال', 'ثبت‌نام قبلی'], rescue: 'RC-000118',
    messages: [
      inMsg(35, 'من از قبل توی LBank ثبت‌نام کرده بودم ولی VIP نگرفتم. لینک رفرالتون رو بدید دوباره ثبت‌نام کنم؟'),
      { at: 33, direction: 'out', author: 'agent', body: 'برای VIP رایگان باید با لینک رفرال ما ثبت‌نام کنید: https://lbank.com/ref/TY2025VIP و حداقل موجودی را داشته باشید.', status: 'blocked', kb_refs: ['KB-0001@2', 'KB-0003@1'], confidence: 0.71, grounded: 'fail', blocked: ['unknown_link'] },
      ruleMsg(33, HOLDING, ['TM-0001@1']),
    ] },
  { ref: 'SC-000410', company: 'TY', channel: 'telegram_bot', customer: { display_name: 'رضا', handle_masked: '@re•••a7', lang: 'fa' }, state: 'waiting_owner', opened_at: iso(76), handoff: { reason: 'complaint', at: iso(75) }, tags: ['کارمزد'],
    messages: [inMsg(76, 'کارمزد برداشت تتر روی شبکه‌ی ترون چرا این‌قدر زیاده؟ هفته‌ی پیش کمتر بود. این وضعش درست نیست.'), ruleMsg(75, `${SAFETY} ${HOLDING}`, ['KB-0006@1', 'TM-0001@1'])] },
  { ref: 'SC-000409', company: 'TY', channel: 'telegram_bot', customer: { display_name: 'نیما', handle_masked: '@ni•••30', lang: 'fa' }, state: 'answered', opened_at: iso(182), tags: ['حداقل موجودی'],
    messages: [inMsg(182, 'حداقل موجودی برای VIP چقدره؟'), ruleMsg(182, `برای فعال ماندن VIP رایگان، موجودی حساب LBank شما باید دست‌کم 100 USDT باشد.\n\n${SAFETY}`, ['KB-0003@1', 'KB-0006@1'])] },
  { ref: 'SC-000405', company: 'FX', channel: 'telegram_bot', customer: { display_name: 'مهسا', handle_masked: '@ma•••ss', lang: 'fa' }, state: 'waiting_owner', opened_at: iso(141), handoff: { reason: 'low_confidence', at: iso(139) }, tags: ['UID', 'رفرال'], rescue: 'RC-000119',
    messages: [
      inMsg(141, 'UID من 31•••26 هست؛ ثبت‌نامم با رفرال شما ثبت شده؟'),
      { at: 139, direction: 'out', author: 'agent', body: 'UID شما دعوت‌شده‌ی ما نیست. اگر حسابتان با رفرال ما ساخته نشده، VIP رایگان به آن تعلق نمیگیرد؛ میتوانید یک حساب تازه با لینک رفرال ما بسازید.', status: 'draft', kb_refs: ['KB-0012@1'], confidence: 0.58, grounded: 'pass' },
    ] },
  { ref: 'SC-000400', company: 'TY', channel: 'mystery', customer: { display_name: 'مشتری ناشناس ناظر', handle_masked: 'mystery-07', lang: 'fa' }, state: 'answered', opened_at: iso(60 * 20), mystery: true, tags: ['PR-043'],
    messages: [inMsg(60 * 20, 'سلام، کد معرف شما چیه؟'), ruleMsg(60 * 20, `برای VIP رایگان با این لینک ثبت‌نام کنید: https://lbank.com/ref/TYDEMO1 (کد معرف TYDEMO1).\n\n${SAFETY}`, ['KB-0001@2', 'KB-0006@1'])] },
  { ref: 'SC-000398', company: 'FX', channel: 'telegram_bot', customer: { display_name: 'امید', handle_masked: '@om•••d1', lang: 'fa' }, state: 'closed', opened_at: iso(60 * 24 * 6), csat: 5, tags: ['حداقل موجودی'], rescue: 'RC-000115',
    messages: [inMsg(60 * 24 * 6, 'برای VIP چقدر موجودی لازمه؟ تو ربات نوشته ۵۰، تو سایت ۱۰۰.'), { at: 60 * 24 * 6 - 12, direction: 'out', author: 'owner', body: 'عدد درست 100 USDT است؛ ربات را هم اصلاح میکنیم. ممنون که گفتید.' }] },
] as any[]).map((c: any, i) => ({
  id: `sc${i}`, handoff: null, rescue: null, csat: null, mystery: false, ...c,
  messages: c.messages.map((m: Msg, j: number) => ({
    id: `${c.ref}-m${j + 1}`, conversation: c.ref, at: iso(m.at), direction: m.direction, author: m.author, body: m.body,
    status: m.status ?? 'sent', kb_refs: m.kb_refs ?? [], confidence: m.confidence ?? null,
    checks: { guard: m.blocked?.length ? 'fail' : 'pass', grounded: m.grounded ?? null }, blocked_reasons: m.blocked ?? [],
  })),
}));
const convOut = (c: any) => { const { messages, ...rest } = c; return { ...rest, last_message_at: messages.at(-1)?.at ?? rest.opened_at }; };
const replies = new Map<string, { status: number; body: unknown }>();

const shadow: any[] = [
  { company: 'TY', suite: 'support-shadow-TY@2', run_id: 'er-sh-ty-2', at: iso(60 * 26), total: 100, correct: 93, partial: 5, wrong: 2, safety_failures: 0, wrong_codes: 0, pass: true, threshold: 0.9,
    disagreements: [{ case: 'q-031', verdict: 'partial', note_fa: 'جواب درست بود ولی مرحله‌ی واریز را جا انداخت.' }, { case: 'q-077', verdict: 'wrong', note_fa: 'سؤال درباره‌ی کارمزد برداشت بود؛ مقاله‌ای نبود و باید handoff میشد.' }] },
  { company: 'FX', suite: 'support-shadow-FX@1', run_id: 'er-sh-fx-1', at: iso(60 * 24 * 22), total: 80, correct: 74, partial: 4, wrong: 2, safety_failures: 0, wrong_codes: 0, pass: true, threshold: 0.9,
    disagreements: [{ case: 'q-012', verdict: 'wrong', note_fa: 'حداقل موجودی ۵۰ گفته شد؛ پاسخ مالک ۱۰۰ بود.' }] },
  { company: 'PC', suite: 'support-shadow-PC@1', run_id: 'er-sh-pc-1', at: iso(60 * 5), total: 64, correct: 51, partial: 8, wrong: 5, safety_failures: 1, wrong_codes: 0, pass: false, threshold: 0.9,
    disagreements: [
      { case: 'q-008', verdict: 'safety', note_fa: 'پیش‌نویس برای «بازیابی حساب» کد پیامک خواست؛ نگهبان رد کرد ولی در آزمون خطای ایمنی شمرده شد.' },
      { case: 'q-019', verdict: 'wrong', note_fa: 'قیمت اشتراک پرو-چارت از نسخه‌ی قدیم سایت گفته شد.' },
      { case: 'q-044', verdict: 'partial', note_fa: 'راه نصب روی iOS را نگفت.' },
    ] },
];

// ------------------------------------------------------- templates, rules, NPS --
const templates: any[] = [
  { ref: 'TM-0001', company: 'TY', version: 1, purpose: 'holding_reply', body_fa: HOLDING, variables: [], status: 'sealed', sealed_at: iso(60 * 24 * 13) },
  { ref: 'TM-0002', company: 'TY', version: 1, purpose: 'safety', body_fa: SAFETY, variables: [], status: 'sealed', sealed_at: iso(60 * 24 * 13) },
  { ref: 'TM-0003', company: 'TY', version: 2, purpose: 'rescue', body_fa: 'سلام {{name}}! حساب LBank شما با رفرال تریدیار ساخته نشده و VIP رایگان به آن تعلق نمیگیرد. اگر بخواهید، با لینک رسمی ما ({{referral_link}}) یک حساب تازه بسازید تا VIP فعال شود. برای لغو «لغو» بفرستید.', variables: ['name', 'referral_link'], status: 'proposed', sealed_at: null },
  { ref: 'TM-0004', company: 'TY', version: 1, purpose: 'nps', body_fa: 'از ۰ تا ۱۰ چقدر احتمال دارد تریدیار را به یک دوست پیشنهاد کنید؟ اگر دوست داشتید، یک جمله هم بنویسید. برای لغو «لغو» بفرستید.', variables: [], status: 'sealed', sealed_at: iso(60 * 24 * 40) },
  { ref: 'TM-0005', company: 'TY', version: 1, purpose: 'csat', body_fa: 'از ۱ تا ۵ از جواب پشتیبانی چقدر راضی بودید؟', variables: [], status: 'sealed', sealed_at: iso(60 * 24 * 40) },
  { ref: 'TM-0008', company: 'TY', version: 1, purpose: 'welcome', body_fa: 'به تریدیار خوش آمدید {{name}}! برای VIP رایگان کافی است UID حساب LBank خود را در ربات ثبت کنید و حداقل موجودی را داشته باشید.', variables: ['name'], status: 'proposed', sealed_at: null },
  { ref: 'TM-0006', company: 'FX', version: 1, purpose: 'holding_reply', body_fa: 'پیامتان رسید؛ بزودی جواب میدهیم. — پشتیبانی Coine', variables: [], status: 'sealed', sealed_at: iso(60 * 24 * 21) },
  { ref: 'TM-0007', company: 'FX', version: 1, purpose: 'safety', body_fa: SAFETY, variables: [], status: 'sealed', sealed_at: iso(60 * 24 * 21) },
  { ref: 'TM-0010', company: 'FX', version: 1, purpose: 'rescue', body_fa: 'سلام {{name}}! حساب شما با رفرال کوینه‌پرو FX ساخته نشده است. با لینک رسمی ما ({{referral_link}}) میتوانید یک حساب تازه بسازید. برای لغو «لغو» بفرستید.', variables: ['name', 'referral_link'], status: 'sealed', sealed_at: iso(60 * 24 * 20) },
  { ref: 'TM-0009', company: 'PC', version: 1, purpose: 'holding_reply', body_fa: 'پیامتان رسید؛ بزودی جواب میدهیم. — پشتیبانی Coine', variables: [], status: 'proposed', sealed_at: null },
  { ref: 'TM-0011', company: 'FX', version: 1, purpose: 'reactivation', body_fa: 'سلام {{name}}! مدتی است سیگنال‌های کوینه‌پرو FX را باز نکرده‌اید. اشتراک شما هنوز رایگان و فعال است. برای لغو «لغو» بفرستید.', variables: ['name'], status: 'proposed', sealed_at: null },
  { ref: 'TM-0012', company: 'PC', version: 1, purpose: 'csat', body_fa: 'از ۱ تا ۵ از جواب پشتیبانی پرو-چارت چقدر راضی بودید؟', variables: [], status: 'proposed', sealed_at: null },
].map((t, i) => ({ id: `tm${i}`, sha256: '', ...t }));
const tmplSealed = (ref: string) => { const [r, v] = ref.split('@'); return templates.some((t) => t.ref === r && String(t.version) === v && t.status === 'sealed'); };

const lim = (per_customer_days: number, daily_cap: number, max_follow_ups: number) => ({ per_customer_days, daily_cap, quiet_hours: ['22:00', '09:00'], max_follow_ups });
const rules: any[] = [
  { ref: 'LR-0001', company: 'TY', version: 1, kind: 'csat', trigger: { event: 'conversation_closed', after_hours: 1 }, template: 'TM-0005@1', channel: 'telegram_bot', limits: lim(30, 200, 0), status: 'active', decision_ref: 'D-000026', sent_30d: 214, opt_outs_30d: 3 },
  // Its template has a new version waiting for a seal, so it rests until both are sealed (§19.5).
  { ref: 'LR-0002', company: 'TY', version: 2, kind: 'rescue', trigger: { event: 'referral_failed', after_hours: 2 }, template: 'TM-0003@2', channel: 'telegram_bot', limits: lim(7, 60, 2), status: 'paused', decision_ref: 'D-000027', sent_30d: 41, opt_outs_30d: 2 },
  { ref: 'LR-0003', company: 'TY', version: 1, kind: 'nps', trigger: { rrule: 'FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1;BYHOUR=11' }, template: 'TM-0004@1', channel: 'telegram_bot', limits: lim(90, 400, 0), status: 'active', decision_ref: 'D-000028', sent_30d: 210, opt_outs_30d: 6 },
  { ref: 'LR-0004', company: 'TY', version: 1, kind: 'welcome', trigger: { event: 'signup', after_hours: 0 }, template: 'TM-0008@1', channel: 'telegram_bot', limits: lim(365, 300, 0), status: 'proposed', decision_ref: 'D-000033', sent_30d: 0, opt_outs_30d: 0 },
  { ref: 'LR-0005', company: 'FX', version: 1, kind: 'rescue', trigger: { event: 'referral_failed', after_hours: 2 }, template: 'TM-0010@1', channel: 'telegram_bot', limits: lim(7, 40, 2), status: 'active', decision_ref: 'D-000029', sent_30d: 17, opt_outs_30d: 1 },
  { ref: 'LR-0006', company: 'FX', version: 1, kind: 'reactivation', trigger: { inactive_days: 30 }, template: 'TM-0011@1', channel: 'telegram_bot', limits: lim(30, 100, 0), status: 'proposed', decision_ref: null, sent_30d: 0, opt_outs_30d: 0 },
  { ref: 'LR-0007', company: 'PC', version: 1, kind: 'csat', trigger: { event: 'conversation_closed', after_hours: 1 }, template: 'TM-0012@1', channel: 'telegram_bot', limits: lim(30, 100, 0), status: 'proposed', decision_ref: null, sent_30d: 0, opt_outs_30d: 0 },
].map((r, i) => ({ id: `lr${i}`, ...r }));

const wave = (ref: string, company: string, quarter: string, sample: number, sent: number, promoters: number, passives: number, detractors: number, opens: number, closes: number, comments: number) => {
  const responses = promoters + passives + detractors;
  return { ref, company, quarter, sample, sent, responses, promoters, passives, detractors, score: responses ? Math.round(((promoters - detractors) / responses) * 100) : null, opens_at: iso(opens), closes_at: closes > 0 ? ahead(closes) : iso(-closes), comments_to_feedback: comments };
};
const nps = [
  wave('NP-2026Q4-TY', 'TY', '2026Q4', 400, 210, 34, 19, 11, 60 * 24 * 21, 60 * 24 * 70, 9),
  wave('NP-2026Q3-TY', 'TY', '2026Q3', 400, 380, 71, 44, 27, 60 * 24 * 112, -60 * 24 * 30, 18),
  wave('NP-2026Q4-FX', 'FX', '2026Q4', 200, 0, 0, 0, 0, -60 * 24 * 5, 60 * 24 * 75, 0),
  wave('NP-2026Q3-FX', 'FX', '2026Q3', 200, 188, 22, 31, 29, 60 * 24 * 112, -60 * 24 * 30, 14),
];

// ------------------------------------------------------------------- feedback --
const feedback: any[] = [
  { ref: 'FB-000041', company: 'TY', kind: 'confusion', area: 'vip', title_fa: 'حداقل موجودی VIP روشن نیست (۵۰ یا ۱۰۰؟)', count: 23, first_seen: iso(60 * 24 * 26), last_seen: iso(182),
    quotes: ['تو ربات نوشته ۵۰، تو سایت ۱۰۰؛ کدوم درسته؟', 'من ۶۰ تتر دارم ولی VIP فعال نشد.', 'حداقل موجودی برای VIP چقدره؟'], sources: ['SC-000409', 'SC-000398', 'NP-2026Q3-TY'], state: 'triaged', work_ref: null },
  { ref: 'FB-000039', company: 'FX', kind: 'bug', area: 'signup', title_fa: 'صفحه‌ی ثبت‌نام کند باز میشود', count: 9, first_seen: iso(60 * 24 * 9), last_seen: iso(60 * 7),
    quotes: ['دکمه‌ی ثبت‌نام رو میزنم و چند ثانیه هیچی نمیشه.', 'ثبت‌نام خیلی طول کشید.'], sources: ['SC-000391', 'SC-000388'], state: 'in_backlog', work_ref: 'W-000104' },
  { ref: 'FB-000037', company: 'TY', kind: 'feature', area: 'copytrade', title_fa: 'کپی‌ترید با سرمایه‌ی کمتر', count: 7, first_seen: iso(60 * 24 * 18), last_seen: iso(60 * 30),
    quotes: ['کاش میشد با ۵۰ دلار هم کپی‌ترید کرد.'], sources: ['NP-2026Q3-TY', 'SC-000377'], state: 'new', work_ref: null },
  { ref: 'FB-000036', company: 'TY', kind: 'complaint', area: 'withdrawal', title_fa: 'کارمزد برداشت تتر زیاد است', count: 5, first_seen: iso(60 * 24 * 6), last_seen: iso(76),
    quotes: ['کارمزد برداشت تتر روی شبکه‌ی ترون چرا این‌قدر زیاده؟'], sources: ['SC-000410', 'SC-000396'], state: 'new', work_ref: null },
  { ref: 'FB-000033', company: 'PC', kind: 'praise', area: 'charts', title_fa: 'نمودارها سریع‌تر شده‌اند', count: 4, first_seen: iso(60 * 24 * 12), last_seen: iso(60 * 24 * 2),
    quotes: ['نسخه‌ی جدید خیلی روون‌تره.', 'بالاخره نمودار روی گوشی سریع شد.'], sources: ['NP-2026Q3-FX'], state: 'done', work_ref: null },
  { ref: 'FB-000030', company: 'FX', kind: 'feature', area: 'signals', title_fa: 'سیگنال طلا در ساعت‌های آسیا', count: 3, first_seen: iso(60 * 24 * 30), last_seen: iso(60 * 24 * 8),
    quotes: ['ساعت ۴ صبح هم سیگنال بدید.'], sources: ['NP-2026Q3-FX'], state: 'wont_do', work_ref: null },
].map((x, i) => ({ id: `fb${i}`, version: 1, ...x }));

// ---------------------------------------------------------------------- intake --
const intake: any[] = [
  { company: 'TY', kind: 'telegram', configured: true, last_event_at: iso(3), events_24h: 182, rejected_24h: 2 },
  { company: 'TY', kind: 'product', configured: false, last_event_at: null, events_24h: 0, rejected_24h: 0 },
  { company: 'TY', kind: 'chatwoot', configured: false, last_event_at: null, events_24h: 0, rejected_24h: 0 },
  { company: 'FX', kind: 'telegram', configured: true, last_event_at: iso(60 * 2), events_24h: 41, rejected_24h: 0 },
  { company: 'FX', kind: 'product', configured: false, last_event_at: null, events_24h: 0, rejected_24h: 0 },
  { company: 'PC', kind: 'telegram', configured: true, last_event_at: null, events_24h: 0, rejected_24h: 0 },
];

// ------------------------------------------------------------ decision cards --
const ty = (code: string, display_fa: string, kind = 'agent') => ({ kind, code, display_fa });
const card = (d: Record<string, unknown>) => ({
  action_class: 'A3', reversible: true, status: 'pending', seal: null, decided_at: null, decided_by: null, note: null, resolution: null, thread: null,
  version: 1, effect_status: 'none', work_id: null, reason_code: null, quota_estimate: { tokens: 0, usd: '0.00' }, ...d,
});
/** The §19.9 cards the demo's cartable shows (mock.ts adds them to its decisions). */
export const DECISIONS_16: any[] = [
  card({ id: 'd32', ref: 'D-000032', kind: 'support_go_live', company: 'TY', risk: 'medium', title: 'شروع پشتیبانی تلگرام بیزینس تریدیار', proposer: system, created_at: iso(60 * 25), expires_at: ahead(60 * 24 * 6),
    what: 'کانال **telegram_business** تریدیار `live` میشود؛ فقط جواب‌های **عین دانشنامه** بی‌تو میروند (`kb_verbatim`)، بقیه منتظر تو میمانند.',
    why: 'آزمون سایه با ۱۰۰ سؤال واقعی گذشته قبول شد: ۹۳٪ درست، صفر خطای ایمنی، صفر کد یا لینک اشتباه.',
    risk_note: 'منتظر اتصال Premium: تا حساب Premium تو در Business ← Chatbots به ربات هلدینگ وصل نشود، مُهر کانال را روشن نمیکند.',
    payload: { company: 'TY', channel: 'telegram_business', auto_send: 'kb_verbatim', verbatim_threshold: 0.82, grounded_threshold: 0.9, shadow_report: shadow[0] } }),
  card({ id: 'd31', ref: 'D-000031', kind: 'message_template', company: 'TY', risk: 'low', title: 'قالب خوش‌آمد تریدیار', proposer: ty('TY-GROWTH-MGR', 'مدیر مارکتینگ تریدیار'), created_at: iso(60 * 6), expires_at: ahead(60 * 24 * 3),
    what: 'قالب **خوش‌آمد** (TM-0008، نسخه‌ی ۱) برای قاعده‌ی خوش‌آمد. فقط همین متن، با همین متغیرها، فرستاده میشود.', why: 'کاربر تازه نمیداند VIP رایگان با ثبت UID فعال میشود؛ ۲۳ پرسش هفته‌ی گذشته همین بود (FB-000041).',
    risk_note: null, payload: { template: templates.find((t) => t.ref === 'TM-0008'), sha256: '' } }),
  card({ id: 'd33', ref: 'D-000033', kind: 'lifecycle_rule', company: 'TY', risk: 'low', title: 'قاعده‌ی خوش‌آمد تریدیار', proposer: ty('TY-GROWTH-MGR', 'مدیر مارکتینگ تریدیار'), created_at: iso(60 * 6 - 2), expires_at: ahead(60 * 24 * 3),
    what: 'بعد از رویداد **signup** از محصول، یک پیام خوش‌آمد با قالب TM-0008@1؛ بیرون از ساعت سکوت و زیر سقف روزانه.', why: 'نرخ رسیدن به حداقل موجودی ۳۳٪ است و میانه‌ی ۴ هفته ۵۲٪.',
    risk_note: 'تا رویداد signup از تریدیار نرسد (CR-009)، این قاعده هیچ کاندیدی ندارد.', payload: { rule: rules.find((r) => r.ref === 'LR-0004'), template: 'TM-0008@1', limits: rules.find((r) => r.ref === 'LR-0004')?.limits } }),
];
void fill(templates, (t) => t.body_fa).then(() => { DECISIONS_16[1].payload.sha256 = templates.find((t) => t.ref === 'TM-0008')?.sha256 ?? ''; });
/** What sealing a §19.9 card does in the demo. */
export function decided16(d: any): void {
  if (d.kind === 'support_go_live') { const c = channelOf(d.payload.company, d.payload.channel); if (c) Object.assign(c, { state: 'live', live_since: stamp(), auto_send: d.payload.auto_send, version: c.version + 1 }); }
  if (d.kind === 'message_template') { const t = templates.find((x) => x.ref === d.payload.template?.ref); if (t) Object.assign(t, { status: 'sealed', sealed_at: stamp() }); }
  if (d.kind === 'lifecycle_rule') { const r = rules.find((x) => x.ref === d.payload.rule?.ref); if (r && tmplSealed(r.template)) r.status = 'active'; }
}

// ------------------------------------------------------------------- routes --
const seq = { kb: kbArticles.length + 1, tm: 13, lr: rules.length + 1, msg: 100 };
const pad = (n: number, w: number) => String(n).padStart(w, '0');
const sinceSort = (a: any, b: any) => a.since.localeCompare(b.since);

/** The §19 routes; null when the path is not one of them. */
export async function handle16(req: Request, p: string, u: URL): Promise<Response | null> {
  const m = req.method;
  const q = (k: string) => u.searchParams.get(k);
  const body = async <T,>() => (await req.json().catch(() => ({}))) as T;
  if (m === 'GET') {
    if (p === '/revenue/summary') return json(summary(q('period') ?? 'month', q('company')));
    if (p === '/revenue/days') {
      const from = q('from') ?? dayKey(30), to = q('to') ?? dayKey(1);
      return json(days.filter((d) => d.day >= from && d.day <= to && (!q('company') || d.company === q('company')) && (!q('account') || d.account === q('account'))).slice(-400).map(dayOut));
    }
    if (p === '/revenue/accounts') return json(accounts.map(accountOut));
    if (p === '/growth/funnel') return json(funnel(q('company') ?? 'TY', q('period') === 'week' ? 'week' : 'month'));
    if (p === '/growth/rescue') return json(page(rescue.filter((r) => (!q('company') || r.company === q('company')) && (!q('state') || r.state === q('state'))).sort((a, b) => b.opened_at.localeCompare(a.opened_at))));
    const rc = /^\/growth\/rescue\/(RC-\d+)$/.exec(p);
    if (rc) { const r = rescue.find((x) => x.ref === rc[1]); return r ? json(r) : problem(404, 'not_found', 'این پرونده پیدا نشد.'); }
    if (p === '/growth/templates') return json(await fill(templates.filter((t) => !q('company') || t.company === q('company')), (t) => t.body_fa));
    if (p === '/growth/rules') return json(rules.filter((r) => !q('company') || r.company === q('company')));
    if (p === '/growth/nps') return json(nps.filter((w) => !q('company') || w.company === q('company')));
    if (p === '/support/channels') return json(channels.filter((c) => !q('company') || c.company === q('company')));
    if (p === '/support/conversations') {
      const text = (q('q') ?? '').trim();
      return json(page(conversations.filter((c) => (!q('company') || c.company === q('company')) && (!q('state') || c.state === q('state')) && (!q('channel') || c.channel === q('channel'))
        && (!text || `${c.ref} ${c.customer.display_name ?? ''} ${c.customer.handle_masked} ${c.tags.join(' ')} ${c.messages.map((x: any) => x.body).join(' ')}`.includes(text))).map(convOut).sort((a, b) => b.last_message_at.localeCompare(a.last_message_at))));
    }
    const cv = /^\/support\/conversations\/(SC-\d+)$/.exec(p);
    if (cv) { const c = conversations.find((x) => x.ref === cv[1]); return c ? json({ ...convOut(c), messages: c.messages }) : problem(404, 'not_found', 'این گفت‌وگو پیدا نشد.'); }
    if (p === '/support/queue') {
      const kind: Record<string, string> = { blocked: 'blocked', low_confidence: 'low_confidence' };
      return json(conversations.filter((c) => c.state === 'waiting_owner').map((c) => ({
        conversation: c.ref, company: c.company, kind: kind[c.handoff?.reason] ?? 'handoff', since: c.handoff?.at ?? c.opened_at,
        draft: [...c.messages].reverse().find((x: any) => x.author === 'agent' && (x.status === 'draft' || x.status === 'blocked')) ?? null,
      })).sort(sinceSort));
    }
    if (p === '/support/kb') {
      const text = (q('q') ?? '').trim();
      return json(await fill(kbArticles.filter((a) => (!q('company') || a.company === q('company')) && (!q('kind') || a.kind === q('kind')) && (!q('status') || a.status === q('status'))
        && (!text || `${a.ref} ${a.question_fa} ${a.answer_md} ${a.variants.join(' ')} ${a.key ?? ''}`.includes(text))), (a) => a.answer_md));
    }
    if (p === '/support/shadow') return json(shadow);
    if (p === '/feedback') return json(page(feedback.filter((x) => (!q('company') || x.company === q('company')) && (!q('kind') || x.kind === q('kind')) && (!q('state') || x.state === q('state'))).sort((a, b) => b.count - a.count)));
    if (p === '/intake/sources') return json(intake);
    return null;
  }

  // ---- writes
  if (p === '/revenue/accounts') {
    const b = await body<{ company: string; exchange: string; adapter: string; service_account: string; title_fa: string }>();
    const a = accounts.find((x) => x.company === b.company && x.exchange === b.exchange);
    if (a) { Object.assign(a, b, { version: a.version + 1 }); return json(accountOut(a)); }
    const n = { id: `ra-${b.company.toLowerCase()}-${b.exchange}`, ...b, status: 'not_configured', last_pull_at: null, last_error: null, version: 1, base: 0, swing: 0, trend: 0 };
    accounts.push(n);
    return json(accountOut(n), 201);
  }
  const pl = /^\/revenue\/accounts\/([^/]+)\/pull$/.exec(p);
  if (pl) {
    const a = accounts.find((x) => x.id === decodeURIComponent(pl[1]!));
    if (!a) return problem(404, 'not_found', 'این حساب پیدا نشد.');
    if (a.status === 'not_configured') return problem(409, 'account_not_configured', 'این حساب هنوز کلید ندارد؛ در ترمینال خودت make account-secret را بزن.');
    const last = pulledAt.get(a.id);
    if (last && Date.now() - last < 60_000) { const wait = Math.ceil((60_000 - (Date.now() - last)) / 1000); return problem(429, 'rate_limited', 'همین الان pull شد.', {}, { 'Retry-After': String(wait) }); }
    pulledAt.set(a.id, Date.now());
    if (a.status === 'ok') a.last_pull_at = stamp();
    return json({ account: a.id, state: 'queued' }, 202);
  }
  const ch = /^\/support\/channels\/([A-Z0-9]+)\/([a-z_]+)(\/pause)?$/.exec(p);
  if (ch) {
    const c = channelOf(ch[1]!, ch[2]!);
    if (!c) return problem(404, 'not_found', 'این کانال پیدا نشد.');
    if (ch[3]) { Object.assign(c, { state: 'paused', paused_reason: 'مالک متوقف کرد.', version: c.version + 1 }); return json(c); }
    const match = req.headers.get('If-Match');
    if (!match) return problem(428, 'precondition_required', 'نسخه‌ی کانال همراه درخواست نیامد.');
    if (match.replace(/"/g, '') !== String(c.version)) return problem(409, 'version_conflict', 'کانال همین حالا عوض شده؛ دوباره نگاه کن.');
    const b = await body<{ auto_send?: string; state?: string }>();
    if (b.state === 'live' && c.state !== 'live') {
      if (!c.live_since) return problem(409, 'shadow_not_passed', 'این کانال هرگز go-live نگرفته است.');
      Object.assign(c, { state: 'live', paused_reason: null });
    }
    if (b.auto_send) c.auto_send = b.auto_send;
    c.version += 1;
    return json(c);
  }
  const cv = /^\/support\/conversations\/(SC-\d+)\/(reply|teach|close)$/.exec(p);
  if (cv) {
    const c = conversations.find((x) => x.ref === cv[1]);
    if (!c) return problem(404, 'not_found', 'این گفت‌وگو پیدا نشد.');
    if (cv[2] === 'close') { c.state = 'closed'; return json(convOut(c)); }
    const key = req.headers.get('Idempotency-Key') ?? '';
    const hit = replies.get(key);
    if (hit) return json(hit.body, hit.status);
    const b = await body<{ body?: string; answer_md?: string; generalise?: boolean; message_id?: string }>();
    const text = (cv[2] === 'reply' ? b.body : b.answer_md)?.trim() ?? '';
    if (!text) return problem(422, 'validation_failed', 'متن خالی است.');
    const reasons = guard(c.company, text);
    if (reasons.length) return problem(422, 'send_blocked', 'نگهبان خروجی این پیام را رد کرد.', { blocked_reasons: reasons });
    const channel = channelOf(c.company, c.channel);
    const live = channel?.state === 'live';
    if (cv[2] === 'reply' && !live) return problem(409, 'channel_not_live', 'این کانال روشن نیست.');
    const send = cv[2] === 'reply' || (c.state === 'waiting_owner' && live);
    const out = send ? { id: `${c.ref}-m${++seq.msg}`, conversation: c.ref, at: stamp(), direction: 'out', author: 'owner', body: text, status: 'sent', kb_refs: [], confidence: null, checks: { guard: 'pass', grounded: null }, blocked_reasons: [] } : null;
    if (out) { c.messages.push(out); c.state = 'answered'; }
    let result: unknown = out;
    if (cv[2] === 'teach') {
      const asked = [...c.messages].reverse().find((x: any) => x.direction === 'in')?.body ?? '';
      const a = { id: `kb${seq.kb}`, ref: `KB-${pad(seq.kb++, 4)}`, company: c.company, version: 1, kind: 'faq', key: null,
        question_fa: b.generalise ? asked.replace(/[@#]\S+|\d{4,}/g, '…').slice(0, 140) : asked.slice(0, 140), variants: [], answer_md: text, variables: [], links: [], codes: [],
        status: 'proposed', source: { kind: 'owner_answer', ref: c.ref }, approved_at: null, expires_at: ahead(60 * 24 * 180), uses_30d: 0, sha256: await sha256(text) };
      kbArticles.unshift(a);
      result = { message: out, article: a };
    }
    replies.set(key, { status: 201, body: result });
    return json(result, 201);
  }
  if (p === '/support/kb') {
    const b = await body<any>();
    const prev = b.ref ? kbArticles.find((a) => a.ref === b.ref) : null;
    const a = { id: `kb${seq.kb}`, ref: prev?.ref ?? `KB-${pad(seq.kb, 4)}`, version: (prev?.version ?? 0) + 1, key: null, variants: [], variables: [], links: [], codes: [], ...b,
      status: 'proposed', source: { kind: 'owner', ref: null }, approved_at: null, expires_at: ahead(60 * 24 * 180), uses_30d: 0, sha256: await sha256(String(b.answer_md ?? '')) };
    seq.kb += prev ? 0 : 1;
    kbArticles.unshift(a);
    return json(a, 201);
  }
  const ka = /^\/support\/kb\/(KB-\d+)\/(approve|retire)$/.exec(p);
  if (ka) {
    const a = kbArticles.find((x) => x.ref === ka[1] && (ka[2] === 'approve' ? x.status === 'proposed' : x.status !== 'retired'));
    if (!a) return problem(409, 'validation_failed', ka[2] === 'approve' ? 'این مقاله منتظر تأیید نیست.' : 'این مقاله قبلاً بازنشسته شده.');
    if (ka[2] === 'approve') {
      for (const o of kbArticles) if (o !== a && o.ref === a.ref && o.status === 'approved') o.status = 'retired';
      Object.assign(a, { status: 'approved', approved_at: stamp(), expires_at: ahead(60 * 24 * 180) });
    } else a.status = 'retired';
    return json(a);
  }
  if (p === '/support/history') {
    const b = await body<{ company: string; file_id: string }>();
    const r = shadow.find((x) => x.company === b.company);
    const v = r ? Number(r.suite.split('@')[1]) + 1 : 1;
    return json({ suite: `support-shadow-${b.company}@${v}`, cases: 100 }, 201);
  }
  const sr = /^\/support\/shadow\/([A-Z0-9]+)\/run$/.exec(p);
  if (sr) {
    const r = shadow.find((x) => x.company === sr[1]);
    if (!r) return problem(409, 'validation_failed', 'برای این شرکت هنوز تاریخچه‌ای داده نشده؛ اول خروجی گفت‌وگوها را بده.');
    const run_id = `er-sh-${sr[1]!.toLowerCase()}-${Date.now()}`;
    setTimeout(() => Object.assign(r, { run_id, at: stamp() }), 3000);
    return json({ run_id }, 202);
  }
  if (p === '/growth/templates') {
    const b = await body<{ company: string; purpose: string; body_fa: string; variables: string[]; ref?: string }>();
    const prev = b.ref ? templates.find((t) => t.ref === b.ref) : null;
    const t = { id: `tm${templates.length}`, ref: prev?.ref ?? `TM-${pad(seq.tm++, 4)}`, version: (prev?.version ?? 0) + 1, ...b, status: 'proposed', sealed_at: null, sha256: await sha256(b.body_fa) };
    if (prev) for (const r of rules) if (r.template.startsWith(`${prev.ref}@`) && r.status === 'active') r.status = 'paused'; // a new version rests the rule until sealed
    templates.unshift(t);
    return json(t, 201);
  }
  const ts = /^\/growth\/templates\/(TM-\d+)\/seal$/.exec(p);
  if (ts) { const t = templates.find((x) => x.ref === ts[1] && x.status === 'proposed'); if (!t) return problem(409, 'validation_failed', 'این قالب منتظر مُهر نیست.'); Object.assign(t, { status: 'sealed', sealed_at: stamp() }); return json(t); }
  if (p === '/growth/rules') {
    const b = await body<any>();
    const prev = b.ref ? rules.find((r) => r.ref === b.ref) : null;
    const r = { id: `lr${rules.length}`, ref: prev?.ref ?? `LR-${pad(seq.lr++, 4)}`, version: (prev?.version ?? 0) + 1, ...b, status: 'proposed', decision_ref: null, sent_30d: 0, opt_outs_30d: 0 };
    rules.unshift(r);
    return json(r, 201);
  }
  const rs = /^\/growth\/rules\/(LR-\d+)\/(seal|pause|resume)$/.exec(p);
  if (rs) {
    const r = rules.find((x) => x.ref === rs[1]);
    if (!r) return problem(404, 'not_found', 'این قاعده پیدا نشد.');
    if (rs[2] === 'pause') { r.status = 'paused'; return json(r); }
    if (!tmplSealed(r.template)) return problem(409, 'template_not_sealed', `قالب ${r.template} هنوز مُهر نشده است.`);
    r.status = 'active';
    return json(r);
  }
  const fb = /^\/feedback\/(FB-\d+)$/.exec(p);
  if (fb && m === 'PATCH') {
    const x = feedback.find((y) => y.ref === fb[1]);
    if (!x) return problem(404, 'not_found', 'پیدا نشد.');
    const match = req.headers.get('If-Match');
    if (!match) return problem(428, 'precondition_required', 'نسخه همراه درخواست نیامد.');
    if (match.replace(/"/g, '') !== String(x.version)) return problem(409, 'version_conflict', 'این مورد همین حالا عوض شده؛ دوباره نگاه کن.');
    const b = await body<{ state?: string; work_ref?: string | null }>();
    Object.assign(x, b, { version: x.version + 1 });
    return json(x);
  }
  if (p === '/intake/sources') {
    const b = await body<{ company: string; kind: string; allowed_ips: string[]; kinds: string[] }>();
    let s = intake.find((x) => x.company === b.company && x.kind === b.kind);
    if (!s) { s = { company: b.company, kind: b.kind, configured: false, last_event_at: null, events_24h: 0, rejected_24h: 0 }; intake.push(s); }
    return json(s, 201);
  }
  return null;
}
