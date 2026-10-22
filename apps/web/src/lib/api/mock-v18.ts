// Development-only fixtures for contract v1.5 §21 (management tools), used by mock.ts. Never bundled in production (next.config
// aliases the fixtures module away). Companies are data here as on the hub: every list below is built from rows, nothing counts
// them. What the hub computes by rule (department scores, HR flags, reminders, waste, ROI, the baseline prediction, the "agrees"
// of a second opinion, seat caps) is code here too, reduced to what a demo needs; what a model would write is canned text.

import { DEMO_VOICE } from './mock-media';

const now = Date.now();
const MIN = 60_000;
const HOUR = 3_600_000;
const DAY = 86_400_000;
const iso = (minAgo: number) => new Date(now - minAgo * MIN).toISOString();
const ahead = (min: number) => new Date(now + min * MIN).toISOString();
const at = (t: number) => new Date(t).toISOString();
const stamp = () => new Date().toISOString();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const page = (items: unknown[]) => ({ items, next_cursor: null });
const problem = (status: number, code: string, message_fa: string, extra: Record<string, unknown> = {}) =>
  json({ type: 'about:blank', title: code, status, code, message_fa, ...extra }, status);
const pad = (n: number, w: number) => String(n).padStart(w, '0');
const f2 = (n: number) => n.toFixed(2);
/** Deterministic 0..1, so every reload of the demo draws the same month. */
const noise = (seed: number, i: number) => { const x = Math.sin(seed * 9301 + i * 49297) * 233280; return x - Math.floor(x); };
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

// --------------------------------------------------------------- calendar (owner TZ) --
const TEH_OFFSET = 3.5 * HOUR; // Asia/Tehran, no daylight saving since 2022
const tehMidnight = (t: number) => Math.floor((t + TEH_OFFSET) / DAY) * DAY - TEH_OFFSET;
function jParts(t: number) {
  const parts = new Intl.DateTimeFormat('en-US-u-ca-persian-nu-latn', { timeZone: 'Asia/Tehran', year: 'numeric', month: 'numeric', day: 'numeric' }).formatToParts(new Date(t));
  const get = (k: string) => Number(parts.find((p) => p.type === k)?.value ?? 0);
  return { y: get('year'), m: get('month'), d: get('day') };
}
const jKey = (t: number) => { const j = jParts(t); return `${j.y}-${pad(j.m, 2)}`; };
const J = jParts(now);
/** 10:00 Tehran on the 1st of this Jalali month: when the HR round runs (§21.5). */
const MONTH_START = tehMidnight(now - (J.d - 1) * DAY) + 10 * HOUR;
/** The latest Saturday 10:00 Tehran that has passed: the weekly review (§21.3) and, at 09:00, the CEO letters (§21.4). */
const LAST_SAT = (() => {
  const wd = new Date(now + TEH_OFFSET).getUTCDay(); // 6 = Saturday
  let sat = tehMidnight(now) - ((wd + 1) % 7) * DAY;
  if (now < sat + 10 * HOUR) sat -= 7 * DAY;
  return sat;
})();
const satKey = (t: number) => new Date(t + TEH_OFFSET).toISOString().slice(0, 10);
const dayKey = (n: number) => new Date(tehMidnight(now) - n * DAY + TEH_OFFSET).toISOString().slice(0, 10); // n days ago, Tehran

// ------------------------------------------------------------------------ actors --
const NAME: Record<string, string> = { HQ: 'هلدینگ', TY: 'تریدیار', FX: 'کوینه‌پرو FX', PC: 'پرو-چارت' };
const owner = { kind: 'owner', code: 'owner', display_fa: 'مدیر کل' };
const system = { kind: 'system', code: 'system', display_fa: 'سیستم' };
const agent = (code: string, display_fa: string, kind = 'agent') => ({ kind, code, display_fa });
const ceo = (c: string) => agent(`${c}-CEO`, `مدیرعامل ${NAME[c]}`);
const cmo = (c: string) => agent(`${c}-GROWTH-MGR`, `مدیر مارکتینگ ${NAME[c]}`);
const advisor = agent('HQ-ADV', 'مشاور کل', 'advisor');
const factChecker = agent('HQ-OVS-02', 'راستی‌آزما');
const overseer = agent('HQ-OVR', 'ناظر کل', 'overseer');
const qc = agent('HQ-OVS-MGR', 'بازرس کل', 'inspector');
const aiops = agent('HQ-AIOPS-MGR', 'مدیر عملیات هوش مصنوعی');

// ====================================================================== settings (§21.12) ==
const settings: any = {
  timezone: 'Asia/Tehran', calendars: ['jalali', 'gregorian'], morning_report_at: '08:00', digest_minutes: 30, ceo_daily_attention: 6, learning_daily_cap: 3, version: 4,
  advisor: { auto_memo: { enabled: true, max_per_day: 3 }, proactive_per_day: 3 },
  weekly_review: { enabled: true, day: 'sa', at: '10:00' },
  audio_briefings: { morning: true, ceo_letters: true },
  ceo_weekly_letter: { enabled: true, day: 'sa', at: '09:00' },
  reminders: { enabled: true, fraction: 0.5, before_expiry_h: 6, ages_h: [24, 72, 168] },
  digital_ceo: { enabled: true, reveal: 'after', model_predictions: true, max_model_per_day: 20 },
  substitutes: { behind_ratio: 0.4, creative_default_image: 'gpt' },
};

// ===================================================== the deploy card's diff (§21.6) ==
const HEAD = '1017ce2b9a4f6c0d83e2f71a5b9c4d6e0f8a2b13';
const BASE = 'c83d10f4e2a7b95d61f0a3c8e7b2d4f9a0c1e5b7';
const CACHE_PATCH = [
  '@@ -1,18 +1,26 @@',
  ' import { LRU } from \'../lib/lru\';',
  '+import { decodeInWorker } from \'./worker/decode\';',
  ' ',
  '-const MAX_ENTRIES = 64;',
  '+// Candles are cached per symbol and timeframe; the key carries the schema version so an old browser cache is ignored.',
  '+const MAX_ENTRIES = 256;',
  '+const SCHEMA = 3;',
  ' ',
  '-export function cacheKey(symbol: string, tf: string) {',
  '-  return `${symbol}:${tf}`;',
  '+export function cacheKey(symbol: string, tf: string): string {',
  '+  return `v${SCHEMA}:${symbol}:${tf}`;',
  ' }',
  '@@ -40,22 +48,31 @@ export class CandleCache {',
  '-  get(symbol: string, tf: string) {',
  '-    const hit = this.lru.get(cacheKey(symbol, tf));',
  '-    return hit ? JSON.parse(hit) : null;',
  '+  async get(symbol: string, tf: string): Promise<Candle[] | null> {',
  '+    const hit = this.lru.get(cacheKey(symbol, tf));',
  '+    if (!hit) return null;',
  '+    // Parsing 30 days of 1m candles blocked the main thread for ~1.9 s; it now runs in a worker.',
  '+    return decodeInWorker(hit);',
  '   }',
].join('\n');
const CACHE_FULL = `${CACHE_PATCH}\n${[
  '@@ -71,30 +88,44 @@ export class CandleCache {',
  '-  set(symbol: string, tf: string, candles: Candle[]) {',
  '-    this.lru.set(cacheKey(symbol, tf), JSON.stringify(candles));',
  '+  set(symbol: string, tf: string, candles: Candle[]): void {',
  '+    if (candles.length > 50_000) return; // a year of 1m candles is never cached whole',
  '+    this.lru.set(cacheKey(symbol, tf), encodeCandles(candles));',
  '   }',
  ' ',
  '+  /** Drops every entry of this symbol after a split or a delisting. */',
  '+  forget(symbol: string): number {',
  '+    let n = 0;',
  '+    for (const k of this.lru.keys()) if (k.split(\':\')[1] === symbol) { this.lru.delete(k); n++; }',
  '+    return n;',
  '+  }',
  '@@ -118,9 +149,6 @@ export class CandleCache {',
  '-  migrateLegacy(store: Storage) {',
  '-    for (const k of Object.keys(store)) if (k.startsWith(\'pc-cache:\')) store.removeItem(k);',
  '-  }',
].join('\n')}`;
const DIFF_FILES: any[] = [
  { path: 'src/chart/cache.ts', status: 'modified', additions: 142, deletions: 96, binary: false, patch: CACHE_PATCH, truncated: true, secret_masked: false },
  { path: 'src/chart/loader.ts', status: 'modified', additions: 88, deletions: 41, binary: false, truncated: false, secret_masked: false, patch: [
    '@@ -12,14 +12,19 @@ export async function loadCandles(req: CandleRequest) {',
    '-  const raw = await fetch(url(req)).then((r) => r.json());',
    '-  cache.set(req.symbol, req.tf, raw);',
    '-  return raw;',
    '+  const cached = await cache.get(req.symbol, req.tf);',
    '+  if (cached && fresh(cached, req.tf)) return cached;',
    '+  const res = await fetch(url(req), { signal: req.signal });',
    '+  if (!res.ok) throw new ChartLoadError(res.status);',
    '+  const candles = await res.json() as Candle[];',
    '+  cache.set(req.symbol, req.tf, candles);',
    '+  return candles;',
    ' }',
  ].join('\n') },
  { path: 'src/chart/worker/decode.ts', status: 'added', additions: 96, deletions: 0, binary: false, truncated: false, secret_masked: false, patch: [
    '@@ -0,0 +1,12 @@',
    '+// Decodes a cached candle block off the main thread.',
    '+const worker = new Worker(new URL(\'./decode.worker.ts\', import.meta.url), { type: \'module\' });',
    '+let seq = 0;',
    '+const waiting = new Map<number, (c: Candle[]) => void>();',
    '+worker.onmessage = (e: MessageEvent<{ id: number; candles: Candle[] }>) => {',
    '+  waiting.get(e.data.id)?.(e.data.candles);',
    '+  waiting.delete(e.data.id);',
    '+};',
    '+export function decodeInWorker(block: string): Promise<Candle[]> {',
    '+  const id = ++seq;',
    '+  return new Promise((resolve) => { waiting.set(id, resolve); worker.postMessage({ id, block }); });',
    '+}',
  ].join('\n') },
  { path: 'src/chart/legacy-cache.ts', status: 'removed', additions: 0, deletions: 31, binary: false, truncated: false, secret_masked: false, patch: [
    '@@ -1,6 +0,0 @@',
    '-// Kept for the 1.x terminal; nothing imports it since 2.3.',
    '-export const LEGACY_PREFIX = \'pc-cache:\';',
    '-export function readLegacy(store: Storage, key: string) {',
    '-  const v = store.getItem(LEGACY_PREFIX + key);',
    '-  return v ? JSON.parse(v) : null;',
    '-}',
  ].join('\n') },
  { path: 'test/chart/cache.test.ts', status: 'modified', additions: 74, deletions: 12, binary: false, truncated: false, secret_masked: false, patch: [
    '@@ -30,6 +30,18 @@ describe(\'CandleCache\', () => {',
    '+  it(\'ignores entries of an older schema\', async () => {',
    '+    store.set(\'v2:XAUUSD:1h\', block);',
    '+    expect(await cache.get(\'XAUUSD\', \'1h\')).toBeNull();',
    '+  });',
    '+',
    '+  it(\'never caches a year of 1m candles whole\', () => {',
    '+    cache.set(\'BTCUSDT\', \'1m\', candles(60_000));',
    '+    expect(store.size).toBe(0);',
    '+  });',
  ].join('\n') },
  { path: 'config/prod.env.example', status: 'modified', additions: 2, deletions: 1, binary: false, truncated: false, secret_masked: true, patch: [
    '@@ -3,4 +3,5 @@',
    ' CHART_CDN=https://cdn.pro-chart.example',
    '-CHART_CACHE_TTL=300',
    '+CHART_CACHE_TTL=900',
    '+MARKET_API_KEY=•••••••• (masked by the secret scan)',
  ].join('\n') },
  { path: 'public/icons/candle.webp', status: 'added', additions: 0, deletions: 0, binary: true, truncated: false, secret_masked: false, patch: null },
  { path: 'package.json', status: 'modified', additions: 10, deletions: 7, binary: false, truncated: false, secret_masked: false, patch: [
    '@@ -12,9 +12,10 @@',
    '   "dependencies": {',
    '-    "lru-cache": "^7.18.3",',
    '+    "lru-cache": "^11.0.2",',
    '+    "comlink": "4.4.2",',
    '     "lightweight-charts": "4.2.0"',
  ].join('\n') },
];
const FULL_PATCH: Record<string, string> = { 'src/chart/cache.ts': CACHE_FULL };
const SECOND_REVIEW = {
  player: 'gpt', model: 'gpt-5.5', verified: false,
  findings: [
    { path: 'src/chart/cache.ts', line: 31, severity: 'medium', title_fa: 'کلید نسخه‌دار هست، پاک‌سازی نسخه‌های قدیمی نیست', verified: true,
      detail_md: 'کلیدهای `v2:` در حافظه‌ی مرورگر کاربران میمانند و تا سقف ۲۵۶ ورودی جا میگیرند. یک پاک‌سازی یک‌باره در شروع لازم است.' },
    { path: 'src/chart/worker/decode.ts', line: 7, severity: 'low', title_fa: 'خطای worker به رشته‌ی اصلی برنمیگردد', verified: false,
      detail_md: 'اگر decode شکست بخورد، Promise هرگز تمام نمیشود. مدیر فنی پرو-چارت: در `loader.ts:88` با timeout پوشش داده شده؛ رد شد.' },
    { path: 'package.json', line: 15, severity: 'low', title_fa: 'نسخه‌ی lru-cache دقیق pin نشده', verified: null,
      detail_md: 'بقیه‌ی وابستگی‌ها نسخه‌ی دقیق دارند؛ `^11.0.2` با بقیه نمیخواند.' },
  ],
};

// ========================================================= decision cards (§21.1, §21.5, §21.8, §21.10) ==
const card = (d: Record<string, unknown>) => ({
  action_class: 'A1', reversible: true, status: 'pending', seal: null, decided_at: null, decided_by: null, note: null, resolution: null, thread: null,
  version: 1, effect_status: 'none', work_id: null, reason_code: null, quota_estimate: { tokens: 0, usd: '0.00' }, expected: null, warnings: [], ...d,
});
const ROUND_DUE = MONTH_START + 20 * HOUR;
/** The one new pending card of §21: the monthly HR round's evaluation (payload v2), sealed with a passkey (§21.5). */
export const DECISIONS_18: any[] = [
  card({
    id: 'd40', ref: 'D-000040', kind: 'evaluation', company: 'TY', risk: 'medium', title: 'ارتقای تحلیلگر سئوی فنی تریدیار', proposer: ceo('TY'), thread: 'TY-CEO',
    created_at: at(ROUND_DUE - 2 * HOUR), expires_at: null, quota_estimate: { tokens: 480_000, usd: '7.20' },
    what: 'تحلیلگر سئوی فنی (`TY-GROWTH-01`) **تحلیلگر ارشد** میشود: مدل از Haiku 5.5 به Sonnet 5.5 (effort high) و برآورد ماهانه از 420K به 900K توکن.',
    why: 'دو ماه پشت سر هم امتیاز ۸٫۵ به بالا (۸٫۷ و ۸٫۶)، ستاره‌ی ۴٫۳ و هیچ یافته‌ی high باز: پرچم `promote_candidate` در دور ارزیابی ماهانه.',
    risk_note: 'پاکت ماهانه‌ی تریدیار با این تغییر هم جا دارد. اگر تا لحظه‌ی مُهر پر شود، سرور تغییر را رد میکند و هیچ چیز عوض نمیشود.',
    payload: {
      employee: 'TY-GROWTH-01', recommendation: 'promote', round: 'HR-0021', transfer_to: null,
      change: { model: 'claude-sonnet-5-5', effort: 'high', title_fa: 'تحلیلگر ارشد سئوی فنی', quota_estimate_month: 900_000 },
      evidence: [{ kind: 'deliverable', ref: 'O-000031', note: 'امتیاز ۹ تو' }, { kind: 'metric', ref: 'stars.TY.week', note: '4.3' }, { kind: 'hr_round', ref: 'HR-0021', note: 'promote_candidate' }],
    },
  }),
];

/** The sealed predictions of the digital CEO (§21.10): made before each decision, hidden until the owner decides (reveal "after"). */
const PRED: Record<string, { verdict: string; confidence: number; method: string; rationale_fa: string | null; principles: string[]; minutes_before: number }> = {
  'D-000011': { verdict: 'approve', confidence: 0.82, method: 'baseline', rationale_fa: null, principles: [], minutes_before: 40 },
  'D-000004': { verdict: 'approve', confidence: 0.74, method: 'baseline', rationale_fa: null, principles: [], minutes_before: 55 },
  'D-000003': { verdict: 'approve', confidence: 0.74, method: 'baseline', rationale_fa: null, principles: [], minutes_before: 30 },
  'D-000005': { verdict: 'approve', confidence: 0.71, method: 'baseline', rationale_fa: null, principles: [], minutes_before: 50 },
  'D-000008': { verdict: 'approve', confidence: 0.73, method: 'baseline', rationale_fa: null, principles: [], minutes_before: 35 },
  'D-000006': { verdict: 'approve', confidence: 0.88, method: 'baseline', rationale_fa: null, principles: [], minutes_before: 20 },
  'D-000007': { verdict: 'approve', confidence: 0.66, method: 'model', rationale_fa: 'اصلاحیه خط قرمز تازه میافزاید و چیزی را برنمیدارد؛ مالک این را تأیید میکند (DP-005).', principles: ['DP-005'], minutes_before: 70 },
  'D-000009': { verdict: 'reject', confidence: 0.55, method: 'model', rationale_fa: 'پذیرش ۶۰ روزه طولانی است و مالک تا امروز ریسک بی‌راه کاهش را نپذیرفته.', principles: ['DP-004'], minutes_before: 90 },
  'D-000017': { verdict: 'approve', confidence: 0.64, method: 'model', rationale_fa: 'تست‌ها سبزند و canary کوچک است؛ اما پنجره‌ی انتشار در ساعت پربار است (DP-001).', principles: ['DP-001'], minutes_before: 10 },
  'D-000031': { verdict: 'approve', confidence: 0.83, method: 'baseline', rationale_fa: null, principles: [], minutes_before: 30 },
  'D-000032': { verdict: 'approve', confidence: 0.71, method: 'model', rationale_fa: 'آزمون سایه با ۹۳٪ قبول شده و فقط جواب عین دانشنامه بی‌مالک میرود.', principles: ['DP-003'], minutes_before: 45 },
  'D-000033': { verdict: 'approve', confidence: 0.8, method: 'baseline', rationale_fa: null, principles: [], minutes_before: 25 },
  'D-000034': { verdict: 'approve', confidence: 0.86, method: 'baseline', rationale_fa: null, principles: [], minutes_before: 15 },
  'D-000035': { verdict: 'return', confidence: 0.57, method: 'baseline', rationale_fa: null, principles: ['DP-002'], minutes_before: 15 },
  'D-000040': { verdict: 'approve', confidence: 0.69, method: 'model', rationale_fa: 'پرچم قاعده‌محور، دو ماه امتیاز بالا و پاکت جا دارد؛ مالک ارتقای با شاهد را تأیید میکند.', principles: ['DP-003'], minutes_before: 60 },
};
const ACTUAL: Record<string, string> = { approved: 'approve', rejected: 'reject', returned: 'return' };
const brief = (d: any) => {
  const p = PRED[d.ref];
  const actual = ACTUAL[d.status];
  if (!p || !actual || d.decided_by?.kind !== 'owner') return null;
  return { verdict: p.verdict, confidence: p.confidence, method: p.method, correct: p.verdict === actual };
};

/** Reminders as code (§21.8): 50% of the time to expiry and 6 h before it; without expiry at 24 h, 72 h and 7 days. */
function remindersOf(d: any) {
  const c = Date.parse(d.created_at);
  const out: Array<{ at: string; kind: string }> = [];
  if (d.expires_at) {
    const e = Date.parse(d.expires_at);
    const half = c + (e - c) * settings.reminders.fraction;
    if (half <= now) out.push({ at: at(half), kind: 'half' });
    if (e - settings.reminders.before_expiry_h * HOUR <= now) out.push({ at: at(e - settings.reminders.before_expiry_h * HOUR), kind: 'before_expiry' });
  } else {
    const kinds = ['age_24h', 'age_72h', 'age_7d'];
    settings.reminders.ages_h.forEach((h: number, i: number) => { if (c + h * HOUR <= now) out.push({ at: at(c + h * HOUR), kind: kinds[i] ?? `age_${h}h` }); });
  }
  return out;
}

// ======================================================================== memos (§21.1) ==
const REC_FA: Record<string, string> = { approve: 'تأیید', reject: 'رد', return: 'برگشت', ask: 'اول بپرس' };
const memos: any[] = [];
let memoSeq = 1;
const opinion = (player: string, model: string, recommendation: string, confidence: number, summary_fa: string, differences: string[], base: string) =>
  ({ player, model, recommendation, confidence, summary_fa, differences, agrees: recommendation === base });
function cannedMemo(d: any, mode: 'standard' | 'devil') {
  const deploy = d.kind === 'deploy';
  const evaln = d.kind === 'evaluation';
  if (mode === 'devil') {
    return {
      summary_fa: `چرا نه: «${d.title}» را ${deploy ? 'امروز' : 'به همین شکل'} مُهر نکن، مگر جواب پرسش‌های زیر را بگیری.`,
      recommendation: 'reject', confidence: 0.58,
      options: [
        { title_fa: 'رد با دلیل', pros_md: 'هیچ اثر برگشت‌ناپذیری نمیماند.', cons_md: 'کار پیشنهاددهنده یک دور عقب میافتد.' },
        { title_fa: 'برگشت با یادداشت', pros_md: 'همان کار با شرط روشن دوباره میاید.', cons_md: 'یک روز وقت.' },
      ],
      against_md: deploy
        ? '- **ساعت انتشار:** پنجره‌ی CE-0002 در ساعت پربار پرو-چارت است؛ بازگشت خودکار ۴ دقیقه طول میکشد.\n- **یافته‌ی باز:** FI-0009 (تغییر پیکربندی بی‌مُهر) هنوز بسته نشده و H-0002 روی همین انتشار است.\n- **تست بار:** هیچ تست باری روی ۳۰ روز داده‌ی ۱ دقیقه‌ای اجرا نشده؛ ۲۸۶ تست سبز همه واحدی‌اند.'
        : evaln
          ? '- **یک خروجی درخشان:** نیمی از امتیاز این ماه از یک گزارش (O-000031) است.\n- **هزینه:** Sonnet تقریباً دو برابر Haiku است و کار سئوی فنی هنوز با Haiku خوب انجام شده.\n- **جایگزین:** میشود effort را بالا برد بی‌آنکه مدل عوض شود.'
          : `- شاهد این کارت به یک منبع تکیه دارد.\n- اثرش در ۳۰ روز اندازه‌پذیر نیست.\n- ${d.risk_note ?? 'ریسکش در کارت نوشته نشده.'}`,
      risks: [{ title_fa: deploy ? 'قطع ثبت‌نام در بازگشت خودکار' : 'هزینه‌ی بیشتر بی‌نتیجه‌ی اندازه‌پذیر', likelihood: 'medium', impact: deploy ? 'high' : 'medium', mitigation_fa: deploy ? 'انتشار در ساعت کم‌بار' : 'آزمون ۳۰ روزه پیش از تعهد ماهانه' }],
      questions: deploy ? ['تست بار کی و روی چه داده‌ای اجرا شد؟', 'چرا پنجره‌ی انتشار ساعت پربار است؟'] : ['اگر این تصمیم نتیجه نداد، از کجا میفهمیم و کی برمیگردیم؟'],
    };
  }
  if (deploy) {
    return {
      summary_fa: 'انتشار ترمینال پرو-چارت با ۲۸۶ تست سبز و canary ۱۰٪. بیشتر diff بازنویسی cache نمودار و انتقال decode به worker است؛ ریسک اصلی بازگشت ۴ دقیقه‌ای در ساعت پربار است.',
      recommendation: 'approve', confidence: 0.72,
      options: [
        { title_fa: 'مُهر الان، canary ۱۰٪', pros_md: 'کندی ۲٫۴ ثانیه‌ای نمودار از امروز برطرف میشود.', cons_md: 'پنجره‌ی CE-0002 در ساعت پربار است.' },
        { title_fa: 'مُهر با پنجره‌ی کم‌بار (۰۲:۰۰ تا ۰۴:۰۰)', pros_md: 'اگر canary شکست بخورد، کمتر از ۲۰ کاربر میبینند.', cons_md: 'یک شب دیرتر.' },
        { title_fa: 'برگشت برای تست بار', pros_md: 'ریسک cache روی داده‌ی واقعی سنجیده میشود.', cons_md: 'دست‌کم دو روز عقب میافتد.' },
      ],
      against_md: '- `src/chart/cache.ts` ۹۶ خط حذف دارد و هیچ تست باری روی داده‌ی ۳۰ روزه ندارد.\n- یافته‌ی FI-0009 روی همین سرور هنوز باز است.\n- بازبینی دوم GPT یک یافته‌ی تأییدشده دارد: کلیدهای قدیمی cache پاک نمیشوند.',
      risks: [
        { title_fa: 'بازگشت خودکار ۴ دقیقه در ساعت پربار', likelihood: 'low', impact: 'high', mitigation_fa: 'پنجره‌ی کم‌بار' },
        { title_fa: 'ماندن cache قدیمی در مرورگر کاربران', likelihood: 'medium', impact: 'medium', mitigation_fa: 'پاک‌سازی یک‌باره‌ی کلیدهای v2 در شروع' },
      ],
      questions: ['تست بار روی داده‌ی ۳۰ روزه‌ی ۱ دقیقه‌ای اجرا شده؟', 'اگر canary شکست بخورد، کاربران پرو در آن ۴ دقیقه چه میبینند؟'],
    };
  }
  return {
    summary_fa: `${d.title}: ${evaln ? 'پرچم قاعده‌محور و شاهد کافی دارد؛ هزینه‌ی تازه در پاکت جا میشود.' : 'شاهد کارت با سوابق میخواند و برگشت‌پذیر است.'}`,
    recommendation: d.risk === 'low' || evaln ? 'approve' : 'ask', confidence: evaln ? 0.68 : 0.63,
    options: [
      { title_fa: 'مُهر همین‌طور', pros_md: 'کار از امروز جلو میرود.', cons_md: d.risk_note ?? 'هزینه‌ی برآوردشده خرج میشود.' },
      { title_fa: evaln ? 'ارتقا با effort بالاتر، بی‌تغییر مدل' : 'برگشت با شرط روشن', pros_md: 'هزینه کمتر.', cons_md: 'شاید همان نتیجه را ندهد.' },
    ],
    against_md: evaln ? '- نیمی از امتیاز این ماه از یک گزارش است.\n- Sonnet تقریباً دو برابر Haiku خرج دارد.' : '- اثرش هنوز سنجیده نشده؛ تا بازبینی ۳۰ روزه معلوم نیست.',
    risks: [{ title_fa: evaln ? 'هزینه‌ی بیشتر بی‌بهبود کیفیت' : 'نتیجه‌ی کمتر از انتظار', likelihood: 'medium', impact: 'low', mitigation_fa: 'بازبینی در دور ارزیابی ماه بعد' }],
    questions: [evaln ? 'کدام کار این ماه با Haiku انجام نشد یا ضعیف شد؟' : 'سنجه‌ی موفقیت و تاریخش چیست؟'],
  };
}
const SECOND: Record<string, any> = {
  'D-000017': (base: string) => opinion('gpt', 'gpt-5.5', 'return', 0.61, 'تغییر خوب است ولی بدون تست بار روی داده‌ی واقعی نباید منتشر شود؛ canary ۱۰٪ ساعت پربار هم برای ترمینال زیاد است.', ['GPT تست بار را پیش‌شرط میداند؛ مشاور آن را با پنجره‌ی کم‌بار جبران میکند.', 'GPT به canary ۵٪ رأی میدهد، مشاور ۱۰٪.'], base),
};
const THIRD: Record<string, any> = {
  'D-000017': (base: string) => opinion('deepseek', 'deepseek-v3.2', 'approve', 0.66, 'با canary و بازگشت خودکار، ریسک پذیرفتنی است؛ فقط پنجره را به ساعت کم‌بار ببرید.', ['DeepSeek هم پنجره‌ی کم‌بار را شرط میکند.'], base),
};
function makeMemo(d: any, mode: 'standard' | 'devil', trigger: 'owner' | 'auto', state: 'writing' | 'ready', createdMin: number) {
  const body = cannedMemo(d, mode);
  const m: any = {
    id: `dm${memoSeq}`, ref: `DM-${pad(memoSeq++, 4)}`, decision: d.ref, decision_version: d.version, mode, state, trigger,
    ...body, citations: [{ kind: 'decision', ref: d.ref }, ...(d.kind === 'deploy' ? [{ kind: 'meeting', ref: 'MT-0009' }, { kind: 'finding', ref: 'FI-0009' }, { kind: 'calendar', ref: 'CE-0002' }] : d.kind === 'evaluation' ? [{ kind: 'deliverable', ref: 'O-000031' }] : [])],
    usage: { tokens: mode === 'devil' ? 28_400 : 41_200, usd: mode === 'devil' ? '0.610000' : '0.880000' },
    second_opinion: null, third_opinion: null, created_at: iso(createdMin),
  };
  if (state === 'writing') { Object.assign(m, { summary_fa: '', options: [], against_md: '', risks: [], questions: [], citations: [], usage: { tokens: 0, usd: '0.000000' } }); m._ready = Date.now() + 5_000; m._body = body; }
  else attachOpinions(m, d);
  memos.unshift(m);
  return m;
}
/** The seats beside a standard memo (§21.13): GPT's second opinion and DeepSeek's third, each under its daily cap; over it, skipped. */
function attachOpinions(m: any, d: any) {
  if (m.mode !== 'standard') return;
  const take = (player: string, seatKey: string) => {
    const s = subs.find((x) => x.player === player);
    const seat = s?.seats.find((x: any) => x.seat === seatKey);
    if (!s || !seat || !seat.enabled || s.status !== 'ready' || (seat.via === 'web' && s.web.state !== 'signed_in') || seat.used_today >= seat.per_day) { if (s) s.month.skipped += 1; return false; }
    seat.used_today += 1; s.month.calls += 1;
    return true;
  };
  const generic = (player: string, model: string) => opinion(player, model, m.recommendation, Math.max(0.5, m.confidence - 0.05), `روی همان بسته‌ی شاهد ماسک‌شده، بی‌دیدن یادداشت مشاور: ${REC_FA[m.recommendation]}.`, [], m.recommendation);
  if (take('gpt', 'advisor_second_opinion')) m.second_opinion = (SECOND[d.ref] ?? (() => generic('gpt', 'gpt-5.5')))(m.recommendation);
  if (take('deepseek', 'third_opinion')) m.third_opinion = (THIRD[d.ref] ?? (() => generic('deepseek', 'deepseek-v3.2')))(m.recommendation);
}

// ===================================================================== triggers (§21.1) ==
const triggers: any[] = [
  { id: 'at4', key: `okr:KR-0008:${dayKey(0)}`, kind: 'okr', company: 'TY', fired_at: iso(3), facts: { kr: 'KR-0008', pace: 0.62, half: true }, message_ref: null, state: 'capped' },
  { id: 'at3', key: `finding:FI-0009:${dayKey(0)}`, kind: 'finding', company: 'PC', fired_at: iso(6), facts: { finding: 'FI-0009', severity: 'critical', open_h: 27 }, message_ref: 'A-0009', state: 'sent' },
  { id: 'at2', key: `revenue:TY:${dayKey(0)}`, kind: 'revenue', company: 'TY', fired_at: iso(10), facts: { yesterday_usdt: '94.60', median_usdt: '214.80', ratio: 0.44 }, message_ref: 'A-0008', state: 'sent' },
  { id: 'at1', key: `budget:PC:${dayKey(0)}`, kind: 'budget', company: 'PC', fired_at: iso(23), facts: { pct: 92, used: 5_520_000, limit: 6_000_000 }, message_ref: 'A-0005', state: 'sent' },
];
const ADVISOR_MSGS = [
  { ref: 'A-0005', min: 22, author: advisor, meta: { proactive: { kind: 'budget', key: triggers[3].key } },
    body: '**گزارش فعال · بودجه:** مصرف ماه پرو-چارت به ۹۲٪ پاکت رسید (5.52M از 6M) و تا آخر ماه چند روز مانده. با همین آهنگ پیش از ریست سقف پر میشود و کارهای غیرفوری میایستند.\n\nدو راه: پاکت را 1M بالا ببری (کارت تغییر بودجه)، یا انتشار ترمینال (D-000017) را که 60K برآورد دارد بعد از ریست ببری.' },
  { ref: 'A-0006', min: 16, author: owner, meta: { mode: 'devil' }, body: 'قانعم کن که ترمینال پرو-چارت را امروز مُهر نکنم.' },
  { ref: 'A-0007', min: 15, author: advisor, meta: { mode: 'devil' },
    body: '**از زبان مخالف:**\n\n- پنجره‌ی انتشار (CE-0002) ساعت پربار پرو-چارت است و بازگشت خودکار ۴ دقیقه ثبت‌نام را قطع میکند.\n- یافته‌ی critical روی همین سرور (FI-0009) هنوز باز است و ناظر کل انتشار را نگه داشته (H-0002).\n- ۲۸۶ تست سبز همه واحدی‌اند؛ تست بار روی داده‌ی واقعی نیست.\n\nاگر فقط یک چیز بپرسی: «تست بار کی اجرا میشود؟» یادداشت کامل در DM-0001 است.' },
  { ref: 'A-0008', min: 9, author: advisor, meta: { proactive: { kind: 'revenue', key: triggers[2].key } },
    body: '**گزارش فعال · درآمد:** کمیسیون دیروز تریدیار 94.60 USDT بود، ۴۴٪ میانه‌ی ۲۸ روزه‌ی همان روز هفته. pull کامل بوده، پس افت واقعی است. رادار درآمد به مدیرعامل تریدیار هم خبر داده؛ پیشنهادم این است که در نامه‌ی هفتگی علتش را بخواهی.' },
  { ref: 'A-0009', min: 5, author: advisor, meta: { proactive: { kind: 'finding', key: triggers[1].key } },
    body: '**گزارش فعال · یافته:** FI-0009 (تغییر پیکربندی بی‌مُهر در پرو-چارت) بیش از ۲۴ ساعت critical و باز مانده. پرسش رسمی ناظر (Q-0005) هم هنوز جواب نگرفته. تا بسته نشود، مُهر D-000017 را عقب بینداز.' },
];

// ================================================================== ask the hub (§21.2) ==
type Rule = { re: RegExp; answer: string; citations: any[]; not_indexed?: string[] };
const CORPUS: Rule[] = [
  { re: /گزارش روزانه|خاموش|مدیرعامل‌ها/, answer: 'گزارش روزانه‌ی مدیرعامل‌ها با مصوبه‌ی **M-0006** خاموش ماند: «تا وقتی استخدام باز نشده، گزارش صبحگاهی هلدینگ کافی است.» این از گفت‌وگوی تو با مشاور در A-0003 آمد.',
    citations: [{ kind: 'resolution', ref: 'M-0006', snippet: 'تا وقتی استخدام باز نشده، گزارش روزانه‌ی مدیرعامل‌ها خاموش میماند.' }, { kind: 'message', ref: 'A-0003', snippet: 'استخدام SRE برای هر سه شرکت لازم است؟' }] },
  { re: /حداقل موجودی|VIP|100 ?USDT/i, answer: 'حداقل موجودی VIP **100 USDT** است. در ربات FX در `src/bot/handlers/vip.py` (خط‌های 41 تا 58) از سیاست `vip.min_balance` خوانده میشود و مقاله‌ی KB-0003 همین عدد را میگوید. عدد ۵۰ قدیمی ربات با O-000029 اصلاح شد.',
    citations: [{ kind: 'code', repo: 'behnamjalalico/CoineProFx', path: 'src/bot/handlers/vip.py', lines: [41, 58], commit: 'a91c3e2', snippet: 'MIN_BALANCE = policy.get("vip.min_balance")  # 100 USDT\nif balance < MIN_BALANCE:\n    return await reply(msg, kb("KB-0003"))' }, { kind: 'doc', path: 'contracts/HQ_CORE_API_v1.md', lines: [1160, 1164], snippet: 'policy keys, e.g. "vip.min_balance"' }],
    not_indexed: ['behnamjalalico/CoinePro-App'] },
  { re: /ثبت‌?نام|کندی|ایندکس|signup/i, answer: 'کندی ثبت‌نام FX از جستجوی بی‌ایندکس روی `users.email` بود (۲٫۸ ثانیه). اصلاح در جلسه‌ی کد S-0004 روی شاخه‌ی `hq/S-0004` آماده است: ایندکس یکتا و حذف دو کوئری تکراری؛ در تست بار از ۲٫۹ به ۰٫۳۱ ثانیه رسید (W-000104).',
    citations: [{ kind: 'work', ref: 'W-000104', snippet: 'رفع کندی ثبت‌نام' }, { kind: 'code', repo: 'behnamjalalico/CoineProFx', path: 'alembic/versions/0042_users_email_index.py', lines: [8, 24], commit: 'hq/S-0004', snippet: 'op.create_index("ix_users_email", "users", ["email"], unique=True)' }] },
  { re: /SRE|پایداری/, answer: 'برای تریدیار و FX شاهد بود (دو حادثه‌ی کندی: I-0002 و I-0005)؛ هر دو کارت استخدام (D-000014، D-000015) با بسته شدن استخدام پس گرفته شدند. برای پرو-چارت هنوز پیشنهادی نیامده.',
    citations: [{ kind: 'decision', ref: 'D-000014', snippet: 'استخدام SRE تریدیار' }, { kind: 'message', ref: 'A-0004', snippet: 'برای تریدیار و FX شاهد دارد…' }] },
  { re: /canary|ترمینال|انتشار|deploy/i, answer: 'انتشار ترمینال پرو-چارت (D-000017) با canary ۱۰٪ و بازگشت خودکار پیشنهاد شده؛ ۲۸۶ تست سبز دارد و جلسه‌ی مدیریت پرو-چارت (MT-0009) آمادگی‌اش را تأیید کرد. ناظر کل آن را با H-0002 نگه داشته تا FI-0009 روشن شود.',
    citations: [{ kind: 'decision', ref: 'D-000017', snippet: 'انتشار نسخه‌ی تازه‌ی ترمینال پرو-چارت' }, { kind: 'deliverable', ref: 'O-000027', snippet: 'ترمینال تازه با 286 تست سبز آماده‌ی انتشار است' }] },
  { re: /بودجه|پاکت|توکن/, answer: 'پاکت ماهانه‌ی تریدیار 6M و FX 5M توکن است؛ پرو-چارت هنوز پاکت ندارد و سقف بودجه‌اش 6M است که ۹۲٪ آن مصرف شده. مصوبه‌ی بودجه‌ها از ویرایش خزانه آمده است.',
    citations: [{ kind: 'doc', path: 'docs/OPERATING_MODEL.md', lines: [212, 230], snippet: 'پاکت ماهانه‌ی هر شرکت همان سقف استخدام مدیرعامل است' }] },
];
const asks: any[] = [
  { id: 'ak3', ref: 'AK-0003', q: 'چرا گزارش روزانه‌ی مدیرعامل‌ها خاموش است؟', scope: null, state: 'done', found: 7, answer_md: CORPUS[0]!.answer, citations: CORPUS[0]!.citations, not_indexed: [], usage: { tokens: 18_400, usd: '0.140000' }, created_at: iso(60 * 3), finished_at: iso(60 * 3 - 1) },
  { id: 'ak2', ref: 'AK-0002', q: 'حداقل موجودی VIP در کد ربات FX کجا تعریف شده؟', scope: { companies: ['FX'], kinds: ['code', 'doc'] }, state: 'done', found: 12, answer_md: CORPUS[1]!.answer, citations: CORPUS[1]!.citations, not_indexed: CORPUS[1]!.not_indexed, usage: { tokens: 22_900, usd: '0.170000' }, created_at: iso(60 * 26), finished_at: iso(60 * 26 - 1) },
  { id: 'ak1', ref: 'AK-0001', q: 'قرارداد ما با صرافی بایننس کی تمام میشود؟', scope: null, state: 'done', found: 0, answer_md: 'چیزی پیدا نشد. در مصوبه‌ها، تصمیم‌ها، خروجی‌ها و سندها هیچ قراردادی با بایننس نیست؛ حساب‌های افیلیت هلدینگ همه LBank‌اند. کلیدواژه‌ی دیگری امتحان کن، مثلاً «LBank» یا «افیلیت».', citations: [], not_indexed: [], usage: { tokens: 0, usd: '0.000000' }, created_at: iso(60 * 50), finished_at: iso(60 * 50) },
];
const askState = (a: any) => {
  if (a.state === 'done' || a.state === 'failed') return a;
  const age = Date.now() - Date.parse(a.created_at);
  if (a._rule === null) { if (age > 1_200) Object.assign(a, { state: 'done', finished_at: stamp() }); else a.state = 'searching'; return a; }
  if (age > 4_000) Object.assign(a, { state: 'done', answer_md: a._rule.answer, citations: a._rule.citations, not_indexed: a._rule.not_indexed ?? [], usage: { tokens: 19_800, usd: '0.150000' }, finished_at: stamp() });
  else if (age > 1_500) a.state = 'answering';
  else if (age > 500) a.state = 'searching';
  return a;
};
const askOut = (a: any) => { const { _rule, ...rest } = askState(a); return rest; };

// ================================================================ weekly review (§21.3) ==
const agendaRows = [
  ['decision', 'D-000040', 'TY', 'ارتقای تحلیلگر سئوی فنی تریدیار', 'قدیمی‌ترین کارت منتظر؛ سه یادآوری رفته.'],
  ['decision', 'D-000034', 'HQ', 'کالبدشکافی هر حادثه تا 24 ساعت', 'مصوبه‌ی جلسه‌ی هیئت؛ نیمه‌ی زمانش گذشته.'],
  ['decision', 'D-000017', 'PC', 'انتشار نسخه‌ی تازه‌ی ترمینال پرو-چارت', 'پرریسک؛ GPT نظر دوم «برگشت» داده و با مشاور اختلاف دارد.'],
  ['risk', 'RK-0002', 'TY', 'وابستگی درآمد به یک صرافی', 'امتیاز ۲۰ و بازبینی‌اش گذشته؛ راه کاهش ندارد.'],
  ['okr', 'KR-0008', 'TY', 'جواب‌های بی‌دخالت مالک', 'نیمه‌ی فصل با ۶۲٪ سرعت لازم.'],
  ['finding', 'FI-0009', 'PC', 'تغییر پیکربندی بی‌مُهر در پرو-چارت', 'critical و بیش از ۲۴ ساعت باز.'],
  ['budget', 'budget.PC.month', 'PC', 'بودجه‌ی ماه پرو-چارت ۹۲٪', 'پیش از ریست پر میشود.'],
  ['revenue', 'revenue.TY', 'TY', 'افت کمیسیون دیروز تریدیار', '۴۴٪ میانه‌ی همان روز هفته.'],
  ['outcome_review', 'OR-0003', 'TY', 'بازبینی ۹۰ روزه‌ی محتوای سئو (D-000004)', 'موعدش رسیده؛ پیشنهاددهنده هنوز یادداشت نداده.'],
  ['note', 'NT-0006', null, 'هزینه‌ی کارگاه کد در ماه اول', 'یادداشت باز خودت.'],
];
const reviews: any[] = [
  { id: 'wr6', ref: 'WR-0006', week: satKey(LAST_SAT), state: 'ready', brief_message_ref: null, minutes_ref: null, started_at: null, finished_at: null, duration_s: null, version: 1,
    agenda: agendaRows.map(([kind, ref, company, title_fa, why_fa], i) => ({ n: i + 1, kind, ref, company, title_fa, why_fa, status: 'open', owner_note: null })) },
  { id: 'wr5', ref: 'WR-0005', week: satKey(LAST_SAT - 7 * DAY), state: 'done', brief_message_ref: null, minutes_ref: 'O-000039', started_at: at(LAST_SAT - 7 * DAY + 10 * HOUR + 4 * MIN), finished_at: at(LAST_SAT - 7 * DAY + 10 * HOUR + 21 * MIN), duration_s: 17 * 60, version: 14,
    agenda: [
      { n: 1, kind: 'decision', ref: 'D-000007', company: 'TY', title_fa: 'الحاقیه‌ی تریدیار، نسخه‌ی ۲', why_fa: 'منتظر مُهر.', status: 'done', owner_note: 'مُهر شد.' },
      { n: 2, kind: 'risk', ref: 'RK-0005', company: 'PC', title_fa: 'whitelist افیلیت پرو-چارت', why_fa: 'pull درآمد شکست میخورد.', status: 'deferred', owner_note: 'هفته‌ی بعد خودم IP را اضافه میکنم.' },
      { n: 3, kind: 'okr', ref: 'KR-0007', company: 'TY', title_fa: 'نرخ حداقل موجودی', why_fa: 'عقب از برنامه.', status: 'done', owner_note: null },
    ] },
  { id: 'wr4', ref: 'WR-0004', week: satKey(LAST_SAT - 14 * DAY), state: 'skipped', brief_message_ref: null, minutes_ref: null, started_at: null, finished_at: null, duration_s: null, version: 2, agenda: [] },
];

// ======================================================= briefings and letters (§21.4) ==
const VOICE = { engine: 'piper', version: '1.3.0', voice: 'fa_IR-amir-medium', license: 'demo · از MODEL_CARD صدا' };
const AUDIO = (name: string) => ({ id: DEMO_VOICE.url, name, mime: 'audio/mp4', size: 13_163, sha256: 'demo' });
const MORNING = (n: number) => [
  `- **دیروز:** ${[41, 37, 44, 39][n] ?? 40} کار تمام شد؛ ${[4, 5, 3, 4][n] ?? 4} تصمیم منتظر مُهر توست، یکی پرریسک (D-000017).`,
  `- **توکن:** مصرف دیروز ${['1.42M', '1.61M', '1.38M', '1.55M'][n] ?? '1.5M'}، ${[18, 6, 21, 9][n] ?? 10}٪ زیر میانگین هفته.`,
  `- **هدررفت:** ${['$0.84', '$0.71', '$0.66', '$0.93'][n] ?? '$0.8'} از مصرف دیروز هدر رفت؛ بیشترش اجرای شکست‌خورده‌ی پرو-چارت.`,
  `- **کارتابل:** ۲ کارت بیش از ۷۲ ساعت منتظرند (D-000040، D-000034).`,
  `- **درآمد:** کمیسیون دیروز تریدیار ۴۴٪ میانه‌ی همان روز هفته بود.`,
  `- **بازیکن‌های ذخیره:** ChatGPT معادل $14.60 از $20 این ماه؛ Gemini $5.10 از $20 (پروفایل وب منقضی است)؛ DeepSeek رایگان.`,
].join('\n');
const LETTERS: Record<string, { o: string; text: string }> = {
  TY: { o: 'O-000041', text: [
    '**به مدیر کل، از مدیرعامل تریدیار**',
    '',
    'هفته‌ی خوبی بود ولی بی‌دردسر نه. ستاره‌ی هفته به تحلیلگر سئوی فنی رسید و امتیاز شرکت ۸۶ شد.',
    '',
    '- **درآمد:** کمیسیون هفته 1,512 USDT، ۸٪ بالاتر از هفته‌ی قبل؛ ولی دیروز به ۴۴٪ میانه افت کرد و علتش را بررسی میکنیم.',
    '- **مصرف:** 3.1M توکن از پاکت 6M.',
    '- **خروجی‌ها:** گزارش سئوی فنی (O-000031) امتیاز ۹ تو را گرفت.',
    '- **حادثه‌ها:** کندی پنل کاربری (I-0005) با cache داشبورد بسته شد.',
    '- **چالش:** نرخ رسیدن به حداقل موجودی ۳۷٪ مانده؛ پیشنهاد D-000035 در کارتابل است.',
    '',
    '**هفته‌ی بعد:** اصلاح canonical هفت صفحه (S-0003)، و اگر مُهر کنی، پیام راهنمای حداقل موجودی.',
  ].join('\n') },
  FX: { o: 'O-000042', text: [
    '> **عدد بی‌منبع:** «سهم بازار سیگنال فارسی حدود ۳۰٪» در بسته‌ی واقعیت‌ها نبود؛ نامه یک بار برگشت و بار دوم با همین برچسب منتشر شد و یافته‌ی PR-001 باز شد.',
    '',
    '**به مدیر کل، از مدیرعامل کوینه‌پرو FX**',
    '',
    'دقت هفت‌روزه‌ی سیگنال طلا بعد از فیلتر رژیم نوسان به ۶۸٪ برگشت (O-000029) و حادثه‌ی سرور سیگنال (I-0009) در ۱۴ دقیقه مهار شد.',
    '',
    '- **درآمد:** کمیسیون هفته 842 USDT.',
    '- **مصرف:** 2.2M توکن از پاکت 5M.',
    '- **کارگاه کد:** اصلاح کندی ثبت‌نام آماده‌ی انتشار است (S-0004).',
    '- **سهم بازار:** حدود ۳۰٪ بازار سیگنال فارسی با ماست.',
    '',
    '**هفته‌ی بعد:** کالبدشکافی I-0009 (MT-0014) و انتشار اصلاح ثبت‌نام در ساعت کم‌بار.',
  ].join('\n') },
  PC: { o: 'O-000043', text: [
    '**به مدیر کل، از مدیرعامل پرو-چارت**',
    '',
    'ترمینال تازه با ۲۸۶ تست سبز آماده است و کارتش (D-000017) منتظر مُهر توست.',
    '',
    '- **درآمد:** این هفته عددی نداریم؛ pull افیلیت دو بار شکست خورد چون IP هاب در whitelist نیست (RK-0005).',
    '- **مصرف:** 5.5M توکن، ۹۲٪ سقف ماه؛ بیشترش اجراهای شکست‌خورده‌ی مدیر فنی.',
    '- **یافته:** FI-0009 درباره‌ی تغییر پیکربندی بی‌مُهر باز است و پاسخش را تا امشب میدهم.',
    '',
    '**هفته‌ی بعد:** انتشار ترمینال در ساعت کم‌بار، و کم کردن اجرای شکست‌خورده.',
  ].join('\n') },
};
const briefings: any[] = (() => {
  const xs: any[] = [];
  [0, 1, 2, 3].forEach((n) => {
    const t = tehMidnight(now) - n * DAY + 8 * HOUR + 2 * MIN;
    if (t > now) return;
    xs.push({ kind: 'morning', company: 'HQ', period: { from: at(t - 8 * HOUR - DAY), to: at(t - 8 * HOUR) }, deliverable_ref: n === 0 ? 'O-000030' : `O-0000${26 - n}`, text_md: MORNING(n),
      audio: n === 2 ? null : AUDIO(`morning-${dayKey(n)}.m4a`), audio_state: n === 2 ? 'failed' : 'ready', voice: n === 2 ? null : VOICE, created_at: at(t) });
  });
  for (const c of Object.keys(LETTERS)) {
    xs.push({ kind: 'ceo_letter', company: c, period: { from: at(LAST_SAT - 7 * DAY), to: at(LAST_SAT) }, deliverable_ref: LETTERS[c]!.o, text_md: LETTERS[c]!.text,
      audio: AUDIO(`letter-${c}.m4a`), audio_state: 'ready', voice: VOICE, created_at: at(LAST_SAT + 9 * HOUR + Object.keys(LETTERS).indexOf(c) * 4 * MIN) });
  }
  xs.sort((a, b) => a.created_at.localeCompare(b.created_at));
  return xs.map((x, i) => ({ id: `br${i}`, ref: `BR-${pad(20 + i, 4)}`, ...x })).reverse();
})();

// ========================================================= ranks and HR rounds (§21.5) ==
type DeptRow = { company: string; department: string; employees: number; parts: { people: number; delivery: number; efficiency: number; owner: number | null } };
const DEPTS: DeptRow[] = [
  { company: 'TY', department: 'GROWTH', employees: 2, parts: { people: 83, delivery: 88, efficiency: 86, owner: 84 } },
  { company: 'TY', department: 'TECH', employees: 1, parts: { people: 74, delivery: 71, efficiency: 69, owner: null } },
  { company: 'FX', department: 'QUANT', employees: 1, parts: { people: 79, delivery: 76, efficiency: 72, owner: 77 } },
  { company: 'FX', department: 'TECH', employees: 1, parts: { people: 77, delivery: 81, efficiency: 74, owner: 80 } },
  { company: 'FX', department: 'GROWTH', employees: 1, parts: { people: 70, delivery: 64, efficiency: 77, owner: null } },
  { company: 'PC', department: 'TECH', employees: 1, parts: { people: 63, delivery: 58, efficiency: 61, owner: 70 } },
  { company: 'PC', department: 'GROWTH', employees: 1, parts: { people: 72, delivery: 69, efficiency: 66, owner: null } },
  { company: 'HQ', department: 'OVS', employees: 2, parts: { people: 85, delivery: 90, efficiency: 81, owner: 88 } },
  { company: 'HQ', department: 'AIOPS', employees: 1, parts: { people: 80, delivery: 78, efficiency: 84, owner: null } },
];
/** 35% people + 30% delivery + 20% efficiency + 15% owner; without owner ratings its weight is spread over the rest (§21.5). */
const deptScore = (p: DeptRow['parts']) => (p.owner == null ? (0.35 * p.people + 0.3 * p.delivery + 0.2 * p.efficiency) / 0.85 : 0.35 * p.people + 0.3 * p.delivery + 0.2 * p.efficiency + 0.15 * p.owner);
function ranks(period: 'week' | 'month') {
  const rows = DEPTS.map((d, i) => {
    const wob = period === 'week' ? (noise(seedOf(d.company + d.department), 3) - 0.5) * 8 : 0;
    const parts = { people: Math.round(d.parts.people + wob), delivery: Math.round(d.parts.delivery - wob / 2), efficiency: d.parts.efficiency, owner: d.parts.owner };
    const score = Math.round(deptScore(parts) * 10) / 10;
    const trend = Array.from({ length: 8 }, (_, k) => Math.round(score + (noise(i + 11, k) - 0.5) * 10 - (7 - k) * (d.company === 'PC' ? -0.9 : 0.4)));
    trend[7] = Math.round(score);
    return { period, key: period === 'month' ? jKey(now) : satKey(LAST_SAT), company: d.company, department: d.department, score, parts, employees: d.employees, rank_company: 0, rank_holding: null as number | null, trend, computed_at: at(period === 'month' ? MONTH_START : LAST_SAT + 9 * HOUR) };
  });
  for (const r of rows) {
    r.rank_company = rows.filter((x) => x.company === r.company && x.score > r.score).length + 1;
    const same = rows.filter((x) => x.department === r.department);
    r.rank_holding = same.length > 1 ? same.filter((x) => x.score > r.score).length + 1 : null;
  }
  return rows;
}
type Emp = { code: string; title_fa: string; score: number; prev: number | null; stars: number | null; eff: number | null; owner: number | null; failed: number; findings: number; refuted: number; probation: string | null; highFinding?: boolean };
/** The flags are rules (§21.5). */
function flagsOf(e: Emp): string[] {
  const out: string[] = [];
  if (e.score >= 8.5 && (e.prev ?? 0) >= 8.5 && (e.stars ?? 0) >= 4 && !e.highFinding) out.push('promote_candidate');
  if ((e.prev != null && e.prev - e.score >= 1.5) || (e.score >= 5 && e.score < 6)) out.push('coach');
  if (e.score < 5 && e.prev != null && e.prev < 5) out.push('demote_candidate');
  if ((e.score < 3.5 && e.prev != null && e.prev < 3.5) || (e.probation && Date.parse(e.probation) <= now && e.score < 5)) out.push('dismiss_candidate');
  if (e.probation && Date.parse(e.probation) <= now) out.push('probation_end');
  return out;
}
const HR_EMP: Record<string, Emp[]> = {
  TY: [
    { code: 'TY-GROWTH-01', title_fa: 'تحلیلگر سئوی فنی', score: 8.6, prev: 8.7, stars: 4.3, eff: 88, owner: 8.6, failed: 0.04, findings: 0, refuted: 0, probation: null },
    { code: 'TY-GROWTH-MGR', title_fa: 'مدیر مارکتینگ', score: 7.9, prev: 7.6, stars: 3.8, eff: 81, owner: 8.0, failed: 0.07, findings: 1, refuted: 0, probation: null },
    { code: 'TY-TECH-MGR', title_fa: 'مدیر فنی', score: 7.4, prev: 7.7, stars: 3.5, eff: 69, owner: null, failed: 0.11, findings: 0, refuted: 0, probation: null },
  ],
  FX: [
    { code: 'FX-TECH-MGR', title_fa: 'مدیر فنی', score: 7.7, prev: 7.5, stars: 3.9, eff: 74, owner: 8.1, failed: 0.09, findings: 0, refuted: 0, probation: null },
    { code: 'FX-GROWTH-MGR', title_fa: 'مدیر مارکتینگ', score: 7.0, prev: 7.2, stars: 3.4, eff: 77, owner: null, failed: 0.06, findings: 0, refuted: 0, probation: null },
    { code: 'FX-CEO', title_fa: 'مدیرعامل', score: 6.9, prev: 7.3, stars: null, eff: 72, owner: 7.4, failed: 0.05, findings: 1, refuted: 2, probation: null, highFinding: true },
  ],
  PC: [
    { code: 'PC-TECH-MGR', title_fa: 'مدیر فنی', score: 5.8, prev: 7.4, stars: 2.9, eff: 61, owner: 6.4, failed: 0.28, findings: 1, refuted: 1, probation: null },
    { code: 'PC-GROWTH-MGR', title_fa: 'مدیر مارکتینگ', score: 7.2, prev: 7.0, stars: 3.6, eff: 66, owner: 7.5, failed: 0.06, findings: 0, refuted: 0, probation: null },
  ],
  HQ: [
    { code: 'HQ-OVS-MGR', title_fa: 'بازرس کل', score: 8.4, prev: 8.2, stars: 4.1, eff: 81, owner: 8.2, failed: 0.03, findings: 0, refuted: 0, probation: null },
    { code: 'HQ-PA', title_fa: 'دستیار شخصی', score: 8.8, prev: 8.3, stars: 4.4, eff: 86, owner: 8.8, failed: 0.04, findings: 0, refuted: 0, probation: null },
  ],
};
const EVALUATOR: Record<string, any> = { TY: ceo('TY'), FX: ceo('FX'), PC: ceo('PC'), HQ: aiops };
const hrRounds: any[] = ['TY', 'FX', 'PC', 'HQ'].map((c, i) => {
  const emps = HR_EMP[c]!.map((e) => ({ code: e.code, title_fa: e.title_fa, score: e.score, score_prev: e.prev, stars: e.stars, efficiency: e.eff, owner_avg: e.owner, failed_share: e.failed, findings_open: e.findings, refuted_claims: e.refuted, probation_until: e.probation, flags: flagsOf(e) }));
  const decisions = c === 'TY' ? ['D-000040'] : [];
  const teachings = emps.some((e) => e.flags.includes('coach')) ? ['TE-0009'] : [];
  return { id: `hr${i}`, ref: `HR-${pad(21 + i, 4)}`, company: c, month: jKey(now), state: decisions.length ? 'proposed' : 'done', evaluator: EVALUATOR[c], due_at: at(ROUND_DUE), employees: emps, deliverable_ref: `O-0000${44 + i}`, decisions, teachings };
});

// ============================================================ waste and ROI (§21.7) ==
const CATS = ['failed_runs', 'cancelled_work', 'no_progress_runs', 'retry_loops', 'router_errors', 'duplicate_calls', 'cache_miss', 'over_model'];
const CAT_W = [0.3, 0.07, 0.12, 0.14, 0.04, 0.1, 0.15, 0.08];
const WASTE_CO: Record<string, { tokens: number; usdPerM: number; people: string[]; works: string[] }> = {
  TY: { tokens: 310_000, usdPerM: 13.5, people: ['TY-GROWTH-01', 'TY-TECH-MGR', 'TY-CEO'], works: ['W-000102', 'W-000110', 'W-000113'] },
  FX: { tokens: 360_000, usdPerM: 14.2, people: ['FX-TECH-MGR', 'FX-QUANT-02', 'FX-CEO'], works: ['W-000104', 'W-000096', 'W-000118'] },
  PC: { tokens: 150_000, usdPerM: 12.8, people: ['PC-TECH-MGR', 'PC-GROWTH-MGR', 'PC-CEO'], works: ['W-000105', 'W-000121', 'W-000122'] },
  HQ: { tokens: 200_000, usdPerM: 18, people: ['HQ-ADV', 'HQ-OVR', 'HQ-PA'], works: ['W-000098', 'W-000099', 'W-000125'] },
};
function wasteCo(co: string, n: number) {
  const c = WASTE_CO[co]!;
  const seed = seedOf(co);
  const total = Math.round(c.tokens * (0.85 + noise(seed, n) * 0.3));
  const share = co === 'PC' && n === 1 ? 0.19 : 0.05 + noise(seed + 3, n) * 0.08;
  const waste = Math.round(total * share);
  const w = CAT_W.map((x, i) => x * (0.5 + noise(seed + 11 + i, n)));
  if (co === 'PC' && n === 1) w[0] = w[0]! * 2.4;
  const sum = w.reduce((a, b) => a + b, 0);
  const items = CATS.map((category, i) => {
    const tokens = Math.round((waste * w[i]!) / sum);
    const k = Math.min(3, 1 + Math.floor(noise(seed + 31 + i, n) * 3));
    const cut = Array.from({ length: k }, (_, j) => 0.6 ** j);
    const cs = cut.reduce((a, b) => a + b, 0);
    const top = cut.map((x, j) => ({ employee: c.people[(i + j) % c.people.length], ...(category === 'cancelled_work' || category === 'retry_loops' || category === 'no_progress_runs' ? { work_ref: c.works[(i + j) % c.works.length] } : { run_id: `run-${(seed * 7 + i * 13 + j * 17 + n * 3).toString(16).padStart(6, '0').slice(0, 6)}` }), tokens: Math.round((tokens * x) / cs) }));
    return { category, tokens, usd: f2((tokens / 1e6) * c.usdPerM), count: Math.max(1, Math.round(tokens / 6_500)), top };
  }).filter((x) => x.tokens > 0);
  return { day: dayKey(n), company: co, total_tokens: total, total_usd: f2((total / 1e6) * c.usdPerM), waste_tokens: items.reduce((a, x) => a + x.tokens, 0), waste_usd: f2(items.reduce((a, x) => a + Number(x.usd), 0)), items };
}
function wasteDay(n: number, company: string | null) {
  const cos = company ? [company] : Object.keys(WASTE_CO);
  if (company && !WASTE_CO[company]) return null;
  const parts = (k: number) => cos.map((c) => wasteCo(c, k));
  const merge = (k: number) => {
    const ps = parts(k);
    const items = CATS.map((category) => {
      const xs = ps.flatMap((p) => p.items.filter((i: any) => i.category === category));
      return { category, tokens: xs.reduce((a, x) => a + x.tokens, 0), usd: f2(xs.reduce((a, x) => a + Number(x.usd), 0)), count: xs.reduce((a, x) => a + x.count, 0), top: xs.flatMap((x) => x.top).sort((a, b) => b.tokens - a.tokens).slice(0, 5) };
    }).filter((x) => x.tokens > 0);
    const total_tokens = ps.reduce((a, p) => a + p.total_tokens, 0);
    const waste_tokens = items.reduce((a, x) => a + x.tokens, 0);
    return { day: dayKey(k), company, total_tokens, total_usd: f2(ps.reduce((a, p) => a + Number(p.total_usd), 0)), waste_tokens, waste_usd: f2(items.reduce((a, x) => a + Number(x.usd), 0)), items };
  };
  const d: any = merge(n);
  const prev = Array.from({ length: 7 }, (_, k) => Number(merge(n + 1 + k).waste_usd));
  const avg = prev.reduce((a, b) => a + b, 0) / 7;
  d.share = d.total_tokens ? d.waste_tokens / d.total_tokens : 0;
  d.vs_7d = avg ? Number(d.waste_usd) / avg - 1 : 0;
  return d;
}
const REVENUE: Record<string, number> = { TY: 6390.4, FX: 3610.8, PC: 1488.2 };
const ROI_EMP: Array<[string, string, string | null, number, number, number | null, Record<string, number>]> = [
  ['TY-CEO', 'TY', null, 9.8, 6, 8.0, {}], ['TY-TECH-MGR', 'TY', 'TECH', 11.4, 7, 7.6, {}], ['TY-GROWTH-MGR', 'TY', 'GROWTH', 8.9, 9, 8.3, { rescued: 3 }], ['TY-GROWTH-01', 'TY', 'GROWTH', 6.2, 12, 8.6, {}],
  ['FX-CEO', 'FX', null, 10.2, 5, 7.4, {}], ['FX-TECH-MGR', 'FX', 'TECH', 14.6, 9, 8.1, {}], ['FX-GROWTH-MGR', 'FX', 'GROWTH', 5.3, 4, 7.0, { resolved_conversations: 12 }], ['FX-QUANT-02', 'FX', 'QUANT', 2.1, 3, 7.7, {}],
  ['PC-CEO', 'PC', null, 6.1, 3, 7.3, {}], ['PC-TECH-MGR', 'PC', 'TECH', 9.4, 4, 6.4, {}], ['PC-GROWTH-MGR', 'PC', 'GROWTH', 4.8, 5, 7.5, {}],
  ['HQ-ADV', 'HQ', null, 12.3, 4, 9.0, {}], ['HQ-OVR', 'HQ', 'OVS', 7.2, 6, 8.4, {}], ['HQ-OVS-MGR', 'HQ', 'OVS', 5.6, 8, 8.2, {}], ['HQ-PA', 'HQ', null, 3.9, 7, 8.8, {}], ['HQ-AIOPS-MGR', 'HQ', 'AIOPS', 4.4, 5, 8.0, {}],
];
function roi(by: string, period: 'week' | 'month', company: string | null, key: string | null) {
  const k = period === 'week' ? 0.23 : 1;
  const row = (rkey: string, co: string, cost: number, accepted: number, ratingSum: number, attributed: Record<string, number>, revenue: number | null) => {
    const avg = accepted ? Math.round((ratingSum / accepted) * 10) / 10 : null;
    const rev = revenue == null ? null : revenue * k;
    const r = rev != null && cost ? rev / cost : null;
    const base = r ?? (accepted ? cost / accepted : 0);
    return {
      by, key: rkey, company: co, period, period_key: period === 'month' ? jKey(now) : satKey(LAST_SAT),
      cost_usd: f2(cost), accepted, avg_rating: avg, value_points: Math.round((ratingSum / 10) * 10) / 10, cost_per_accepted_usd: accepted ? f2(cost / accepted) : null,
      attributed, revenue_usd: rev == null ? null : f2(rev), net_usd: rev == null ? null : f2(rev - cost), roi: r == null ? null : Math.round(r * 10) / 10,
      trend: Array.from({ length: 6 }, (_, i) => Math.round(base * (0.8 + noise(seedOf(rkey), i) * 0.4) * 100) / 100).map((x, i, a) => (i === a.length - 1 ? Math.round(base * 100) / 100 : x)),
    };
  };
  const emps = ROI_EMP.filter((e) => !company || e[1] === company).map(([code, co, dept, cost, acc, rating, attr]) => ({ code, co, dept, cost: cost * k, acc: Math.round(acc * (period === 'week' ? 0.25 : 1)), rating, attr }));
  if (by === 'employee') return emps.filter((e) => !key || e.code === key).map((e) => row(e.code, e.co, e.cost, e.acc, (e.rating ?? 0) * e.acc, e.attr, null));
  const group = (keyOf: (e: (typeof emps)[number]) => string | null) => {
    const m = new Map<string, typeof emps>();
    for (const e of emps) { const g = keyOf(e); if (g) m.set(g, [...(m.get(g) ?? []), e]); }
    return [...m.entries()];
  };
  const sumAttr = (xs: typeof emps) => xs.reduce((a, e) => { for (const [kk, v] of Object.entries(e.attr)) a[kk] = (a[kk] ?? 0) + v; return a; }, {} as Record<string, number>);
  if (by === 'department') return group((e) => (e.dept ? `${e.co}-${e.dept}` : null)).filter(([g]) => !key || g.endsWith(`-${key}`) || g === key)
    .map(([g, xs]) => row(g, xs[0]!.co, xs.reduce((a, e) => a + e.cost, 0), xs.reduce((a, e) => a + e.acc, 0), xs.reduce((a, e) => a + (e.rating ?? 0) * e.acc, 0), sumAttr(xs), null));
  return group((e) => e.co).filter(([g]) => !key || g === key)
    .map(([g, xs]) => row(g, g, xs.reduce((a, e) => a + e.cost, 0), xs.reduce((a, e) => a + e.acc, 0), xs.reduce((a, e) => a + (e.rating ?? 0) * e.acc, 0), sumAttr(xs), REVENUE[g] ?? null));
}

// ========================================================================= notes (§21.8) ==
const note = (n: number, minAgo: number, text_md: string, x: Record<string, unknown> = {}) => ({
  id: `nt${n}`, ref: `NT-${pad(n, 4)}`, text_md, source: 'text', file_id: null, tags: [], status: 'open', promoted_to: null, created_at: iso(minAgo), updated_at: iso(minAgo), version: 1, ...x,
});
const notes: any[] = [
  note(6, 50, 'از مشاور کل بپرس هزینه‌ی کارگاه کد در ماه اول چقدر شد و کدام جلسه‌ها بیشترین خرج را داشتند.', { tags: ['خزانه', 'کارگاه کد'] }),
  note(5, 60 * 3, 'برای نامه‌ی هفتگی پرو-چارت بپرس چرا pull درآمد دو هفته است شکست میخورد و کی درست میشود.', { source: 'voice', file_id: DEMO_VOICE.url, tags: ['پرو-چارت', 'درآمد'] }),
  note(4, 60 * 26, 'ایده: کمپین آموزش رایگان طلا برای FX در کانال تلگرام، با تصویر از بازیکن ذخیره. اول بودجه‌اش را ببینم.', { tags: ['FX', 'رشد'] }),
  note(3, 60 * 48, 'SRE برای پرو-چارت هم لازم است؟ از مدیر فنی بخواه با شاهد بیاورد.', { status: 'promoted', promoted_to: { kind: 'work', ref: 'W-000107' }, tags: ['پرو-چارت'], version: 2 }),
  note(2, 60 * 24 * 3, 'سه سرویس ایمیل تراکنشی برای تریدیار پیدا کن، برای حدود دویست هزار ایمیل در ماه.', { source: 'voice', file_id: DEMO_VOICE.url, status: 'promoted', promoted_to: { kind: 'errand', ref: 'E-0003' }, version: 2 }),
  note(1, 60 * 24 * 9, 'رنگ دکمه‌ی خرید در حالت شب خوانا نیست.', { status: 'archived', tags: ['طراحی'], version: 2 }),
];

// ============================================================ claims and health (§21.9) ==
const claim = (n: number, minAgo: number, company: string, employee: string, deliverable: string, claim_md: string, verdict: string, by: any, evidence: any[], protocol: string | null = 'PR-001') =>
  ({ id: `cl${n}`, ref: `CL-${pad(n, 4)}`, company, deliverable, employee, claim_md, verdict, checked_by: by, protocol, evidence, at: iso(minAgo) });
const claims: any[] = [
  claim(28, 40, 'FX', 'FX-CEO', 'O-000042', 'سهم بازار سیگنال فارسی FX حدود ۳۰٪ است.', 'refuted', factChecker, [{ kind: 'search', ref: 'web.search', note: 'هیچ منبع عمومی یا داخلی این عدد را ندارد' }]),
  claim(27, 60 * 5, 'FX', 'FX-QUANT-02', 'O-000029', 'دقت هفت‌روزه‌ی سیگنال طلا ۶۱٪ بود.', 'confirmed', factChecker, [{ kind: 'metric', ref: 'signals.tracker 7d', note: '61%' }]),
  claim(26, 60 * 5 + 2, 'FX', 'FX-QUANT-02', 'O-000029', 'علت افت دقت، تغییر رژیم نوسان بعد از خبر فدرال رزرو است.', 'unverifiable', factChecker, [{ kind: 'note', ref: 'O-000029', note: 'تحلیل علّی است، نه عدد' }]),
  claim(25, 60 * 9, 'TY', 'TY-GROWTH-01', 'O-000031', 'هفت صفحه به خاطر canonical اشتباه بیرون از ایندکس‌اند.', 'confirmed', qc, [{ kind: 'link', ref: 'search-console export', note: '7 URLs' }]),
  claim(24, 60 * 20, 'PC', 'PC-TECH-MGR', 'O-000027', 'زمان بارگذاری نمودار ۲٫۴ ثانیه است.', 'refuted', overseer, [{ kind: 'metric', ref: 'health.sites PC 24h', note: 'p50 3.1s' }]),
  claim(23, 60 * 20 + 1, 'PC', 'PC-TECH-MGR', 'O-000027', 'ترمینال ۲۸۶ تست سبز دارد.', 'confirmed', overseer, [{ kind: 'link', ref: 'ci run 1187', note: '286 passed' }]),
  claim(22, 60 * 30, 'FX', 'FX-CEO', 'O-000029', 'دقت هفت‌روزه‌ی سیگنال طلا ۶۸٪ است.', 'refuted', qc, [{ kind: 'finding', ref: 'FI-0008', note: '61% بعد از شمردن لغوشده‌ها' }]),
  claim(21, 60 * 50, 'TY', 'TY-CEO', 'O-000030', 'دیروز ۴۱ کار تمام شد.', 'confirmed', factChecker, [{ kind: 'metric', ref: 'work.done 24h', note: '41' }], null),
];
const H = (employee: string, company: string, runs: number, failed: number, refused: number, loops: number, returns: number, checked: number, refuted: number, cost: number) => {
  const refuted_share = checked ? refuted / checked : null;
  const flags = [...(refuted_share != null && checked >= 5 && refuted_share >= 0.2 ? ['truth'] : []), ...(failed >= 0.25 ? ['reliability'] : []), ...(loops >= 2 ? ['loops'] : [])];
  return { employee, company, runs, failed_share: failed, refused_share: refused, retry_loops: loops, owner_returns: returns, claims_checked: checked, refuted, refuted_share, cost_usd: f2(cost), flags };
};
const HEALTH_7D = [
  H('FX-CEO', 'FX', 41, 0.05, 0.02, 0, 1, 5, 2, 6.8), H('PC-TECH-MGR', 'PC', 36, 0.28, 0.06, 1, 0, 4, 1, 4.1), H('FX-TECH-MGR', 'FX', 58, 0.09, 0.03, 2, 0, 3, 0, 9.4),
  H('TY-GROWTH-01', 'TY', 22, 0.05, 0, 0, 0, 6, 0, 3.3), H('FX-QUANT-02', 'FX', 48, 0.06, 0.02, 0, 0, 2, 0, 2.1), H('TY-CEO', 'TY', 19, 0.05, 0.05, 0, 0, 3, 0, 4.4),
  H('PC-CEO', 'PC', 14, 0.07, 0, 0, 1, 1, 0, 2.6), H('TY-TECH-MGR', 'TY', 27, 0.11, 0.04, 1, 0, 1, 0, 5.2), H('HQ-ADV', 'HQ', 31, 0.03, 0, 0, 0, 0, 0, 7.9), H('HQ-PA', 'HQ', 26, 0.04, 0.08, 0, 0, 0, 0, 2.2),
];
const HEALTH_30D = HEALTH_7D.map((h) => H(h.employee, h.company, Math.round(h.runs * 4.1), Math.max(0.02, h.failed_share * 0.8), h.refused_share, h.retry_loops + (h.retry_loops ? 1 : 0), h.owner_returns + 1, h.claims_checked * 3, Math.max(0, h.refuted * 2 - 1), Number(h.cost_usd) * 4.2));

// =================================================================== digital CEO (§21.10) ==
const principles: any[] = [
  { id: 'dp1', ref: 'DP-001', text_fa: 'انتشار در ساعت پربار را مُهر نمیکنم؛ ساعت کم‌بار یا canary کوچک‌تر میخواهم.', sources: [{ kind: 'meeting', ref: 'MT-0012' }, { kind: 'decision', ref: 'D-000017' }], status: 'active', edited_by_owner: true, version: 3, updated_at: iso(60 * 24 * 4) },
  { id: 'dp2', ref: 'DP-002', text_fa: 'پیشنهاد رشد بی‌سنجه‌ی قابل اندازه‌گیری برمیگردد.', sources: [{ kind: 'decision', ref: 'D-000004' }], status: 'active', edited_by_owner: false, version: 1, updated_at: iso(60 * 24 * 12) },
  { id: 'dp3', ref: 'DP-003', text_fa: 'کار برگشت‌پذیر با شاهد کافی و هزینه‌ی ماهانه‌ی کم را تأیید میکنم.', sources: [{ kind: 'decision', ref: 'D-000011' }, { kind: 'decision', ref: 'D-000003' }], status: 'active', edited_by_owner: false, version: 2, updated_at: iso(60 * 24 * 12) },
  { id: 'dp4', ref: 'DP-004', text_fa: 'پذیرش ریسکی را که راه کاهشش دست خود من است، تا ۶۰ روز میپذیرم.', sources: [{ kind: 'decision', ref: 'D-000009' }], status: 'proposed', edited_by_owner: false, version: 1, updated_at: iso(60 * 24 * 5) },
  { id: 'dp5', ref: 'DP-005', text_fa: 'اصلاحیه‌ای که خط قرمز میافزاید تأیید میکنم؛ حذف خط قرمز نه.', sources: [{ kind: 'decision', ref: 'D-000007' }], status: 'proposed', edited_by_owner: false, version: 1, updated_at: iso(60 * 24 * 5) },
  { id: 'dp6', ref: 'DP-006', text_fa: 'هر استخدامی را که مدیرعامل پیشنهاد کند تأیید میکنم.', sources: [{ kind: 'decision', ref: 'D-000014' }], status: 'retired', edited_by_owner: true, version: 2, updated_at: iso(60 * 24 * 20) },
];
async function predictions(decisions: any[]) {
  const rows = decisions.filter((d) => PRED[d.ref] && d.status !== 'pending' && ACTUAL[d.status] && d.decided_by?.kind === 'owner').map((d) => {
    const p = PRED[d.ref]!;
    const actual = ACTUAL[d.status]!;
    const made = Date.parse(d.decided_at) - p.minutes_before * MIN;
    return { decision: d.ref, kind: d.kind, title: d.title, made_at: at(Math.max(made, Date.parse(d.created_at) + MIN)), method: p.method, verdict: p.verdict, confidence: p.confidence, rationale_fa: p.rationale_fa, principles: p.principles, sealed_hash: '', seen_before: false, actual, correct: p.verdict === actual, _decided: Date.parse(d.decided_at) };
  });
  await Promise.all(rows.map(async (r) => { r.sealed_hash = await sha256(canonical({ decision: r.decision, made_at: r.made_at, method: r.method, verdict: r.verdict, confidence: r.confidence })); }));
  return rows.sort((a, b) => b._decided - a._decided);
}
function stats(rows: any[], window: '30d' | '90d' | 'all') {
  const span = window === '30d' ? 30 : window === '90d' ? 90 : Infinity;
  const xs = rows.filter((r) => !r.seen_before && now - r._decided <= span * DAY + MIN);
  const acc = (ys: any[]) => (ys.length ? ys.filter((r) => r.correct).length / ys.length : null);
  const by_kind: Record<string, { n: number; accuracy: number }> = {};
  for (const r of xs) { const k = (by_kind[r.kind] ??= { n: 0, accuracy: 0 }); k.n += 1; }
  for (const k of Object.keys(by_kind)) by_kind[k]!.accuracy = acc(xs.filter((r) => r.kind === k)) ?? 0;
  const buckets = ['0.5-0.6', '0.6-0.7', '0.7-0.8', '0.8-0.9', '0.9-1.0'];
  const calibration = buckets.map((b) => { const [lo, hi] = b.split('-').map(Number) as [number, number]; const ys = xs.filter((r) => r.confidence >= lo && (r.confidence < hi || (hi === 1 && r.confidence <= 1))); return { bucket: b, n: ys.length, hit_rate: acc(ys) ?? 0 }; }).filter((c) => c.n);
  const brier = xs.length ? xs.reduce((a, r) => a + (r.correct ? (1 - r.confidence) ** 2 : r.confidence ** 2), 0) / xs.length : null;
  return { window, n: xs.length, accuracy: acc(xs), baseline_accuracy: acc(xs.filter((r) => r.method === 'baseline')), model_accuracy: acc(xs.filter((r) => r.method === 'model')), brier: brier == null ? null : Math.round(brier * 1000) / 1000, by_kind, calibration };
}

// ============================================================== substitute players (§21.13) ==
const seat = (s: string, via: string, model: string, per_day: number, used_today: number, enabled = true, extra: Record<string, unknown> = {}) => ({ seat: s, via, model, enabled, per_day, used_today, ...extra });
const subs: any[] = [
  { player: 'gpt', connection: 'chatgpt-plus', runner: 'codex_cli', status: 'ready', limited_until: null, status_reason: null, version: 3,
    login: { state: 'signed_in', plan_fa: 'ChatGPT Plus', since: iso(60 * 24 * 12), last_ok_at: iso(14) },
    models: [{ id: 'gpt-5.5', label: 'GPT 5.5', tier: 'strong', available: true }, { id: 'gpt-5.3', label: 'GPT 5.3', tier: 'light', available: true }],
    capabilities: { text: 'cli', image: 'web', video: 'off' },
    web: { account: 'chatgpt-web', state: 'signed_in', last_ok_at: iso(60 * 2), recipe_version: 'chatgpt-web@4', last_failure: null },
    seats: [seat('advisor_second_opinion', 'cli', 'gpt-5.5', 3, 1), seat('code_review', 'cli', 'gpt-5.5', 10, 3), seat('overseer_cross_check', 'cli', 'gpt-5.5', 20, 7), seat('assistant_errand', 'cli', 'gpt-5.3', 30, 4), seat('creative', 'web', 'gpt-5.5', 20, 2)],
    month: { key: jKey(now), calls: 214, skipped: 3, input_tokens: 3_180_000, output_tokens: 412_000, estimated: false, equiv_usd: '14.60', price_usd: '20.00', value_ratio: 0.73 } },
  { player: 'gemini', connection: 'gemini-pro', runner: 'gemini_cli', status: 'limited', limited_until: ahead(140), status_reason: 'سقف روزانه‌ی Gemini CLI زیر اشتراک پر شد؛ جایگاه‌های متنی تا ریست رد میشوند.', version: 5,
    login: { state: 'signed_in', plan_fa: 'Google AI Pro', since: iso(60 * 24 * 12), last_ok_at: iso(60 * 3) },
    models: [{ id: 'gemini-3.8', label: 'Gemini 3.8', tier: 'strong', available: true }],
    capabilities: { text: 'cli', image: 'web', video: 'web' },
    web: { account: 'gemini-web', state: 'expired', last_ok_at: iso(60 * 31), recipe_version: 'gemini-web@2', last_failure: 'صفحه‌ی ورود دیده شد؛ پروفایل منقضی است.' },
    seats: [seat('content_draft', 'cli', 'gemini-3.8', 30, 11), seat('long_read', 'cli', 'gemini-3.8', 10, 2), seat('code_review', 'cli', 'gemini-3.8', 10, 0, false), seat('creative', 'web', 'gemini-3.8', 20, 0, true, { per_day_video: 3, used_today_video: 0 })],
    month: { key: jKey(now), calls: 96, skipped: 14, input_tokens: 2_040_000, output_tokens: 188_000, estimated: true, equiv_usd: '5.10', price_usd: '20.00', value_ratio: 0.26 } },
  { player: 'deepseek', connection: 'deepseek-free', runner: null, status: 'ready', limited_until: null, status_reason: null, version: 2,
    login: { state: 'signed_out', plan_fa: 'رایگان (فقط وب)', since: null, last_ok_at: null },
    models: [{ id: 'deepseek-v3.2', label: 'DeepSeek V3.2', tier: 'strong', available: true }],
    capabilities: { text: 'web', image: 'off', video: 'off' },
    web: { account: 'deepseek-web', state: 'signed_in', last_ok_at: iso(8), recipe_version: 'deepseek-web@1', last_failure: null },
    seats: [seat('quick_search', 'web', 'deepseek-v3.2', 60, 23), seat('third_opinion', 'web', 'deepseek-v3.2', 5, 1)],
    month: { key: jKey(now), calls: 311, skipped: 0, input_tokens: 610_000, output_tokens: 940_000, estimated: true, equiv_usd: '3.20', price_usd: '0.00', value_ratio: null } },
];
/** The subscription connections of §21.7 ⟨1.5⟩ and §21.13 (mock.ts adds them to its connections). */
export const CONNECTIONS_18: any[] = [
  { id: 'c6', key: 'chatgpt-plus', display_name: 'ChatGPT Plus (بازیکن ذخیره)', kind: 'subscription', provider: 'openai', status: 'enabled', status_reason: null, models: ['gpt-5.5', 'gpt-5.3'], default_model: 'gpt-5.5', fallback_priority: null, has_secret_ref: true, limits: {}, pricing: {}, quota_reset_at: null, updated_at: iso(60 * 24 * 12), version: 2 },
  { id: 'c7', key: 'gemini-pro', display_name: 'Google AI Pro (بازیکن ذخیره)', kind: 'subscription', provider: 'google', status: 'quota_exhausted', status_reason: 'Gemini CLI daily limit', models: ['gemini-3.8'], default_model: 'gemini-3.8', fallback_priority: null, has_secret_ref: true, limits: {}, pricing: {}, quota_reset_at: ahead(140), updated_at: iso(60 * 3), version: 4 },
  { id: 'c8', key: 'deepseek-free', display_name: 'DeepSeek رایگان (فقط وب)', kind: 'subscription', provider: 'deepseek', status: 'enabled', status_reason: null, models: ['deepseek-v3.2'], default_model: 'deepseek-v3.2', fallback_priority: null, has_secret_ref: false, limits: {}, pricing: {}, quota_reset_at: null, updated_at: iso(60 * 24 * 1), version: 1 },
];
const logins: any[] = [];
const verifying = new Map<string, number>();

// ====================================================================== creatives (§21.13) ==
const ASPECT: Record<string, string> = { telegram_post: '16:9', telegram_story: '9:16', instagram_post: '4:5', instagram_story: '9:16', banner: '16:9', other: '1:1' };
const SIZE: Record<string, [number, number]> = { '1:1': [640, 640], '4:5': [640, 800], '9:16': [540, 960], '16:9': [800, 450] };
const SAFE: Record<string, { top: number; bottom: number; side: number }> = {
  telegram_post: { top: 0.07, bottom: 0.09, side: 0.06 }, telegram_story: { top: 0.14, bottom: 0.2, side: 0.08 }, instagram_post: { top: 0.06, bottom: 0.08, side: 0.06 },
  instagram_story: { top: 0.14, bottom: 0.2, side: 0.08 }, banner: { top: 0.08, bottom: 0.08, side: 0.05 }, other: { top: 0.06, bottom: 0.06, side: 0.06 },
};
const BRAND: Record<string, { bg: [string, string]; accent: string; motif: 'candles' | 'waves' | 'rings'; mark: string }> = {
  FX: { bg: ['#0E1422', '#3A2A0C'], accent: '#D8A848', motif: 'candles', mark: 'CoinePro FX' },
  TY: { bg: ['#06221E', '#0B3B4A'], accent: '#00AB8E', motif: 'waves', mark: 'TradeYar' },
  PC: { bg: ['#101830', '#2A1E40'], accent: '#6591E1', motif: 'rings', mark: 'Pro-Chart' },
  HQ: { bg: ['#0B0D14', '#2A2418'], accent: '#D8A848', motif: 'rings', mark: 'CoinePro HQ' },
};
/** The demo's stand-in for the substitute's render and the hub's composition (resvg on the hub): a canvas, in the browser. */
export async function render(company: string, placement: string, seed: number, overlay: any | null): Promise<string> {
  if (typeof document === 'undefined') return '';
  const [w, h] = SIZE[ASPECT[placement] ?? '1:1'] ?? [640, 640];
  const b = BRAND[company] ?? BRAND.HQ!;
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const g = c.getContext('2d');
  if (!g) return '';
  const lg = g.createLinearGradient(0, 0, w, h);
  lg.addColorStop(0, b.bg[0]); lg.addColorStop(1, b.bg[1]);
  g.fillStyle = lg; g.fillRect(0, 0, w, h);
  const rnd = (i: number) => noise(seed, i);
  g.globalAlpha = 0.9;
  if (b.motif === 'candles') {
    const n = 22; const cw = w / n;
    let y = h * 0.55;
    for (let i = 0; i < n; i++) {
      const up = rnd(i) > 0.42; const body = h * (0.03 + rnd(i + 40) * 0.08); y += (up ? -1 : 1) * body * 0.6;
      g.strokeStyle = g.fillStyle = up ? b.accent : '#C94B5B';
      g.lineWidth = 2; g.beginPath(); g.moveTo(i * cw + cw / 2, y - body * 0.9); g.lineTo(i * cw + cw / 2, y + body * 1.4); g.stroke();
      g.fillRect(i * cw + cw * 0.22, y, cw * 0.56, body);
    }
  } else if (b.motif === 'waves') {
    for (let k = 0; k < 6; k++) {
      g.strokeStyle = k % 2 ? b.accent : '#F2EEE4'; g.globalAlpha = 0.25 + k * 0.1; g.lineWidth = 3;
      g.beginPath();
      for (let x = 0; x <= w; x += 8) g.lineTo(x, h * (0.3 + k * 0.07) + Math.sin(x / (40 + k * 9) + rnd(k) * 6) * (18 + k * 4));
      g.stroke();
    }
  } else {
    for (let k = 0; k < 7; k++) { g.strokeStyle = k % 2 ? b.accent : '#AEB8C7'; g.globalAlpha = 0.2 + k * 0.08; g.lineWidth = 2 + k; g.beginPath(); g.arc(w * 0.72, h * 0.32, 30 + k * 34, 0, Math.PI * (1 + rnd(k))); g.stroke(); }
  }
  g.globalAlpha = 1;
  if (overlay) {
    try { await Promise.all(['700 40px IRANYekanXFaNum', '400 24px IRANYekanXFaNum', '600 20px IRANYekanX'].map((f) => document.fonts.load(f))); } catch { /* fonts API missing: system face */ }
    const s = SAFE[placement] ?? SAFE.other!;
    const x0 = w * s.side, x1 = w * (1 - s.side), maxW = x1 - x0;
    const scrim = g.createLinearGradient(0, h * 0.42, 0, h);
    scrim.addColorStop(0, 'rgba(11,13,20,0)'); scrim.addColorStop(1, 'rgba(11,13,20,0.88)');
    g.fillStyle = scrim; g.fillRect(0, h * 0.42, w, h * 0.58);
    g.direction = 'rtl'; g.textAlign = 'right'; g.textBaseline = 'alphabetic';
    const wrap = (text: string, font: string, lh: number) => {
      g.font = font; const out: string[] = []; let line = '';
      for (const word of text.split(/\s+/)) { const t = line ? `${line} ${word}` : word; if (g.measureText(t).width > maxW && line) { out.push(line); line = word; } else line = t; }
      if (line) out.push(line);
      return out.map((l) => ({ l, font, lh }));
    };
    const tSize = Math.round(w * (h > w ? 0.085 : 0.06)); const bSize = Math.round(tSize * 0.52);
    const lines = [...wrap(overlay.title_fa, `700 ${tSize}px IRANYekanXFaNum`, tSize * 1.25), ...(overlay.body_fa ? wrap(overlay.body_fa, `400 ${bSize}px IRANYekanXFaNum`, bSize * 1.5) : [])];
    const ctaH = overlay.cta_fa ? bSize * 2.2 : 0;
    let y = h * (1 - s.bottom) - ctaH - lines.reduce((a, x) => a + x.lh, 0) - (ctaH ? bSize : 0);
    for (const x of lines) { y += x.lh; g.font = x.font; g.fillStyle = '#F2EEE4'; g.fillText(x.l, x1, y); }
    if (overlay.cta_fa) {
      g.font = `700 ${bSize}px IRANYekanXFaNum`;
      const tw = g.measureText(overlay.cta_fa).width + bSize * 2;
      const by = h * (1 - s.bottom) - ctaH;
      g.fillStyle = b.accent; g.beginPath(); g.roundRect(x1 - tw, by, tw, ctaH, ctaH / 2); g.fill();
      g.fillStyle = '#0B0D14'; g.fillText(overlay.cta_fa, x1 - bSize, by + ctaH * 0.66);
    }
    if (overlay.mark) { g.direction = 'ltr'; g.textAlign = 'left'; g.font = `600 ${Math.round(bSize * 0.9)}px IRANYekanX`; g.fillStyle = b.accent; g.fillText(b.mark, x0, h * s.top + bSize); }
  }
  return c.toDataURL('image/webp', 0.86);
}
const fileOf = (url: string, name: string) => ({ id: url, name, mime: url.startsWith('data:image/webp') ? 'image/webp' : 'image/png', size: Math.round(url.length * 0.75), sha256: 'demo' });
const creatives: any[] = [
  { ref: 'CR-0007', company: 'FX', kind: 'image', placement: 'instagram_story', player: 'gpt', model: 'gpt-5.5', state: 'generating', requested_by: cmo('FX'), work_ref: 'W-000131', created: 4,
    brief_md: 'استوری اینستاگرام برای یادآوری جلسه‌ی دوم دوره‌ی رایگان تحلیل طلا.', overlay: { title_fa: 'جلسه‌ی دوم: سطوح حمایت طلا', body_fa: 'شنبه ساعت ۲۰، زنده در تلگرام', cta_fa: 'یادآوری بگذار', mark: true } },
  { ref: 'CR-0006', company: 'FX', kind: 'image', placement: 'telegram_post', player: 'gpt', model: 'gpt-5.5', state: 'review', requested_by: owner, work_ref: null, created: 75,
    brief_md: 'تصویر تبلیغ کانال تلگرام FX برای دوره‌ی آموزش رایگان تحلیل طلا.', overlay: { title_fa: 'دوره‌ی رایگان تحلیل طلا', body_fa: 'پنج جلسه‌ی زنده، شنبه‌ها ساعت ۲۰', cta_fa: 'ثبت‌نام در ربات', mark: true },
    review_md: 'با brief میخواند: نمودار شمعی طلایی، بی‌متن داخل تصویر، و متن فارسی در حاشیه‌ی امن پست تلگرام. نسبت ۱۶:۹ درست است. پیشنهاد: دکمه‌ی دعوت کمی بزرگ‌تر شود.' },
  { ref: 'CR-0005', company: 'TY', kind: 'image', placement: 'instagram_post', player: 'gemini', model: 'gemini-3.8', state: 'accepted', requested_by: cmo('TY'), work_ref: 'W-000128', created: 60 * 30,
    brief_md: 'پست اینستاگرام تریدیار: VIP رایگان با رفرال، حداقل موجودی ۱۰۰ تتر.', overlay: { title_fa: 'VIP رایگان تریدیار', body_fa: 'با ثبت‌نام از لینک رفرال و حداقل موجودی ۱۰۰ USDT', cta_fa: 'راهنما در پروفایل', mark: true },
    review_md: 'تصویر بی‌متن است و متن از دانشنامه (KB-0003) آمده؛ عدد ۱۰۰ USDT با سیاست میخواند.' },
  { ref: 'CR-0004', company: 'PC', kind: 'video', placement: 'telegram_story', player: 'gemini', model: 'gemini-3.8', state: 'failed', requested_by: cmo('PC'), work_ref: 'W-000126', created: 60 * 5, duration_s: 8,
    brief_md: 'تیزر ۸ ثانیه‌ای ترمینال تازه‌ی پرو-چارت برای استوری تلگرام.', overlay: { title_fa: 'ترمینال تازه‌ی پرو-چارت', body_fa: null, cta_fa: 'به‌زودی', mark: true },
    review_md: 'ساخته نشد: پروفایل `gemini-web` منقضی است. مالک باید دوباره وارد شود (`make gemini-web-login`)؛ هیچ تلاش ورود خودکاری نیست.' },
  { ref: 'CR-0003', company: 'TY', kind: 'image', placement: 'telegram_story', player: 'gpt', model: 'gpt-5.5', state: 'rejected', requested_by: owner, work_ref: null, created: 60 * 50,
    brief_md: 'استوری تلگرام برای وبینار آموزشی کاربران تازه‌ی تریدیار.', overlay: { title_fa: 'وبینار کاربران تازه', body_fa: 'چهارشنبه، ساعت ۲۱', cta_fa: null, mark: true },
    review_md: 'رنگ‌ها با پالت تریدیار نمیخواند؛ مالک رد کرد: «پالت برند را رعایت کن».' },
].map((x, i) => ({
  id: `cr${i}`, aspect: ASPECT[x.placement], duration_s: null, composed: null, path: 'web', files: [], review_md: null, errand_ref: null, ai_generated: true, version: 1,
  prompt_md: `Advertising ${x.kind === 'video' ? 'teaser video' : 'image'} for ${BRAND[x.company]?.mark}, aspect ${ASPECT[x.placement]}, palette ${BRAND[x.company]?.bg.join(' / ')} with ${BRAND[x.company]?.accent} accents. ${x.company === 'FX' ? 'Gold candlestick chart, calm and premium.' : x.company === 'TY' ? 'Soft flowing waves, trustworthy.' : 'Abstract chart rings, modern.'} No text, no letters, no logos anywhere in the image; keep the lower third calm for an overlay.`,
  source: x.state === 'failed' || x.state === 'generating' ? null : { player: x.player, model: x.model, at: iso(x.created - 3) },
  created_at: iso(x.created), updated_at: iso(Math.max(0, x.created - 5)), _ready: x.state === 'generating' ? now + 25_000 : undefined, ...x,
}));
let rendered: Promise<void> | null = null;
async function renderCreative(x: any) {
  if (x.state === 'failed' || x.state === 'generating' || x.state === 'queued' || x.files.length) return;
  const seed = seedOf(x.ref);
  const raw = await render(x.company, x.placement, seed, null);
  const comp = await render(x.company, x.placement, seed, x.overlay);
  if (raw) x.files = [fileOf(raw, `${x.ref}-${x.player}.webp`)];
  if (comp) x.composed = fileOf(comp, `${x.ref}-composed.webp`);
}
function tickCreative(x: any) {
  const age = Date.now() - Date.parse(x.created_at);
  if (x.state === 'queued' && age > 1_500) x.state = 'generating';
  if (x.state === 'generating' && x._ready && Date.now() > x._ready) {
    Object.assign(x, { state: 'review', source: { player: x.player, model: x.model, at: stamp() }, updated_at: stamp(), version: x.version + 1,
      review_md: `مدیر مارکتینگ ${NAME[x.company]}: با brief میخواند؛ تصویر بی‌متن است و متن فارسی در حاشیه‌ی امن ${x.placement} نشسته.` });
  }
}
const creativeOut = (x: any) => { const { _ready, created: _c, ...rest } = x; return rest; };

// ======================================================================== decorate ==
type Ctx = { decisions: any[]; messages: Record<string, any[]>; employees: any[]; threads: any[]; deliverables: any[]; connections: any[] };
let ctx: Ctx | null = null;
/** Called once by mock.ts after its lists exist: §21 adds fields to them (deploy diff, memos, reminders, predictions, thread A, letters). */
export function decorate18(c: Ctx): void {
  ctx = c;
  const d17 = c.decisions.find((d) => d.ref === 'D-000017');
  if (d17) {
    Object.assign(d17, {
      risk_note: `${d17.risk_note} یافته‌ی تأییدشده‌ی بازبینی دوم: کلیدهای قدیمی cache پاک نمیشوند (\`cache.ts:31\`).`,
      payload: {
        repo: 'behnamjalalico/pro-chart', pr_url: 'https://github.com/behnamjalalico/pro-chart/pull/42', head_sha: HEAD, diff_stat: '+412 −188',
        ci: { status: 'passed', url: 'https://github.com/behnamjalalico/pro-chart/actions/runs/1187' }, tests: { passed: 286, failed: 0 }, rollout: 'canary 10%',
        window: { from: ahead(180), to: ahead(210) }, calendar_conflicts: [],
        diff: { base_sha: BASE, head_sha: HEAD, total_files: DIFF_FILES.length, total_additions: 412, total_deletions: 188, truncated: false, fetched_at: iso(14), files: DIFF_FILES },
        diff_unavailable: null, second_review: SECOND_REVIEW,
      },
    });
    makeMemo(d17, 'standard', 'auto', 'ready', 13);
  }
  const d32 = c.decisions.find((d) => d.ref === 'D-000032');
  if (d32) makeMemo(d32, 'standard', 'owner', 'ready', 60 * 20);
  for (const d of c.decisions) {
    if (d.status === 'pending' && (d.approver == null)) { d.waiting_h = Math.round((now - Date.parse(d.created_at)) / HOUR); d.reminders = remindersOf(d); }
    d.digital_ceo_prediction = brief(d);
    d.memos = memos.filter((m) => m.decision === d.ref).map((m) => ({ ref: m.ref, mode: m.mode, state: m.state }));
  }
  // The demo's devil memo the advisor cited in A-0007.
  if (d17) { makeMemo(d17, 'devil', 'owner', 'ready', 15); d17.memos = memos.filter((m) => m.decision === d17.ref).map((m) => ({ ref: m.ref, mode: m.mode, state: m.state })); }
  // TY-GROWTH-01 as the HR round read it.
  const e = c.employees.find((x) => x.code === 'TY-GROWTH-01');
  if (e) e.score = { ...e.score, value: 8.6, owner_avg: 8.6, trend: [7.9, 8.4, 8.7, 8.6] };
  const a = (c.messages.A ??= []);
  for (const m of ADVISOR_MSGS) if (!a.some((x) => x.ref === m.ref)) a.push({ id: `m18-${m.ref}`, ref: m.ref, thread: 'A', author: m.author, body: m.body, kind: 'text', attachments: [], links: {}, meta: m.meta, created_at: iso(m.min) });
  const t = c.threads.find((x) => x.code === 'A');
  if (t) Object.assign(t, { last_message_at: iso(5), last_ref: 'A-0009' });
  for (const b of briefings.filter((x) => x.kind === 'ceo_letter')) {
    if (c.deliverables.some((x) => x.ref === b.deliverable_ref)) continue;
    c.deliverables.push({ id: `o-${b.deliverable_ref}`, ref: b.deliverable_ref, company: b.company, title: `نامه‌ی هفتگی مدیرعامل ${NAME[b.company]}`, summary: b.text_md.split('\n').find((l: string) => l && !l.startsWith('>') && !l.startsWith('**')) ?? '', body: b.text_md,
      producer: { code: `${b.company}-CEO`, company: b.company, kind: 'ceo', department: null, title_fa: 'مدیرعامل' }, rating: null, created_at: b.created_at, work_ref: null, attachments: [], evidence: [{ kind: 'metric', ref: 'facts.pack', note: 'بسته‌ی واقعیت‌ها' }],
      produced_with: { model: 'claude-sonnet-5-5', effort: 'high', label_fa: 'Sonnet 5.5 · high' }, usage: { tokens: 21_400, usd: '0.38' }, work_id: null });
  }
}

/** What deciding a card does for §21 (mock.ts calls it for approve, reject and return). */
export function decided18(d: any): void {
  d.digital_ceo_prediction = brief(d);
  d.waiting_h = null;
  for (const m of memos) if (m.decision === d.ref && m.state === 'writing') m.state = 'stale';
  if (d.kind === 'evaluation' && d.status === 'approved' && ctx) {
    const p = d.payload ?? {};
    const e = ctx.employees.find((x) => x.code === p.employee);
    if (e && p.change) Object.assign(e, { title_fa: p.change.title_fa ?? e.title_fa, model: { ...e.model, model: p.change.model ?? e.model?.model, effort: p.change.effort ?? e.model?.effort } });
    if (e && p.recommendation === 'confirm') e.probation_until = null;
  }
  for (const r of hrRounds) if (r.decisions.includes(d.ref) && ctx && r.decisions.every((ref: string) => ctx!.decisions.find((x) => x.ref === ref)?.status !== 'pending')) r.state = 'done';
}

function tick() {
  for (const m of memos) if (m.state === 'writing' && m._ready && Date.now() > m._ready) {
    Object.assign(m, m._body, { state: 'ready', citations: [{ kind: 'decision', ref: m.decision }], usage: { tokens: m.mode === 'devil' ? 27_900 : 39_600, usd: m.mode === 'devil' ? '0.590000' : '0.840000' } });
    delete m._ready; delete m._body;
    const d = ctx?.decisions.find((x) => x.ref === m.decision);
    if (d) { attachOpinions(m, d); d.memos = memos.filter((x) => x.decision === d.ref).map((x) => ({ ref: x.ref, mode: x.mode, state: x.state })); }
  }
  for (const [id, when] of verifying) if (Date.now() > when && ctx) {
    const c = ctx.connections.find((x) => x.id === id);
    if (c) Object.assign(c, { status: 'ready', status_reason: null, updated_at: stamp(), version: c.version + 1 });
    verifying.delete(id);
  }
  for (const l of logins) if (l.state === 'waiting' && l.method === 'device_code' && Date.now() - l._t > 8_000) finishLogin(l);
  for (const l of logins) if (l.state === 'waiting' && Date.parse(l.expires_at) < Date.now()) l.state = 'expired';
  for (const x of creatives) tickCreative(x);
}
function finishLogin(l: any) {
  l.state = 'done';
  const s = subs.find((x) => x.connection === l.connection);
  if (s) { Object.assign(s.login, { state: 'signed_in', since: stamp(), last_ok_at: stamp() }); if (s.status === 'off') Object.assign(s, { status: 'ready', status_reason: null }); s.version += 1; }
}
const loginOut = (l: any) => { const { _t, ...rest } = l; return rest; };
const memoOut = (m: any) => { const { _ready, _body, ...rest } = m; return rest; };

// ========================================================================== routes ==
/** The §21 routes; null when the path is not one of them. */
export async function handle18(req: Request, p: string, u: URL): Promise<Response | null> {
  const m = req.method;
  const q = (k: string) => u.searchParams.get(k);
  const body = async <B,>() => (await req.json().catch(() => ({}))) as B;
  tick();
  const decisions = ctx?.decisions ?? [];
  if (m === 'GET') {
    if (p === '/owner/settings') return json(settings);
    // ---- §21.1
    const mm = /^\/decisions\/(D-\d+)\/memo$/.exec(p);
    if (mm) { const x = memos.find((y) => y.decision === mm[1] && y.mode === (q('mode') ?? 'standard')); return x ? json(memoOut(x)) : problem(404, 'not_found', 'برای این کارت هنوز یادداشتی نوشته نشده.'); }
    if (p === '/advisor/memos') return json(page(memos.filter((x) => !q('decision') || x.decision === q('decision')).map(memoOut)));
    if (p === '/advisor/triggers') return json(triggers.filter((x) => (!q('kind') || x.kind === q('kind')) && (!q('since') || x.fired_at >= q('since')!)));
    // ---- §21.2
    if (p === '/ask') return json(page(asks.map(askOut)));
    const ak = /^\/ask\/(AK-\d+)$/.exec(p);
    if (ak) { const x = asks.find((y) => y.ref === ak[1]); return x ? json(askOut(x)) : problem(404, 'not_found', 'این پرسش پیدا نشد.'); }
    // ---- §21.3
    if (p === '/reviews/weekly') return json(reviews);
    if (p === '/reviews/weekly/current') return json(reviews[0]);
    // ---- §21.4
    if (p === '/briefings') return json(page(briefings.filter((b) => (!q('kind') || b.kind === q('kind')) && (!q('company') || b.company === q('company')))));
    if (p === '/briefings/latest') { const b = briefings.find((x) => x.kind === (q('kind') ?? 'morning') && (!q('company') || x.company === q('company'))); return b ? json(b) : problem(404, 'not_found', 'هنوز گزارشی نیست.'); }
    const br = /^\/briefings\/(BR-\d+)$/.exec(p);
    if (br) { const b = briefings.find((x) => x.ref === br[1]); return b ? json(b) : problem(404, 'not_found', 'این گزارش پیدا نشد.'); }
    // ---- §21.5
    if (p === '/rankings/departments') return json(ranks(q('period') === 'week' ? 'week' : 'month').filter((r) => (!q('company') || r.company === q('company'))).sort((a, b) => b.score - a.score));
    if (p === '/hr/rounds') return json(hrRounds.filter((r) => (!q('company') || r.company === q('company')) && (!q('month') || r.month === q('month'))));
    const hr = /^\/hr\/rounds\/(HR-\d+)$/.exec(p);
    if (hr) { const r = hrRounds.find((x) => x.ref === hr[1]); return r ? json(r) : problem(404, 'not_found', 'این دور ارزیابی پیدا نشد.'); }
    // ---- §21.6
    const df = /^\/decisions\/(D-\d+)\/diff$/.exec(p);
    if (df) {
      const d = decisions.find((x) => x.ref === df[1]);
      const f = d?.payload?.diff?.files?.find((x: any) => x.path === q('file'));
      if (!f) return problem(404, 'not_found', 'این فایل در diff این کارت نیست.');
      return json({ ...f, patch: FULL_PATCH[f.path] ?? f.patch, truncated: false });
    }
    // ---- §21.7
    if (p === '/treasury/waste') {
      const co = q('company');
      if (q('from') && q('to')) {
        const out = Array.from({ length: 30 }, (_, i) => i + 1).map((n) => wasteDay(n, co)).filter((x) => x && x.day >= q('from')! && x.day <= q('to')!);
        return json(out.sort((a, b) => a!.day.localeCompare(b!.day)));
      }
      const day = q('day');
      const n = day ? Array.from({ length: 30 }, (_, i) => i + 1).find((k) => dayKey(k) === day) : 1;
      const w = n ? wasteDay(n, co) : null;
      return w ? json(w) : problem(404, 'not_found', 'هدررفت آن روز هنوز حساب نشده؛ هر روز ۰۷:۴۵ برای دیروز.');
    }
    if (p === '/treasury/roi') return json(roi(q('by') ?? 'company', q('period') === 'week' ? 'week' : 'month', q('company'), q('key')));
    // ---- §21.8
    if (p === '/notes') {
      const text = (q('q') ?? '').trim();
      return json(page(notes.filter((n) => (q('status') ? n.status === q('status') : true) && (!text || `${n.text_md} ${n.tags.join(' ')} ${n.ref}`.includes(text))).sort((a, b) => b.created_at.localeCompare(a.created_at))));
    }
    // ---- §21.9
    if (p === '/claims') return json(page(claims.filter((c) => (!q('company') || c.company === q('company')) && (!q('employee') || c.employee === q('employee')) && (!q('verdict') || c.verdict === q('verdict')))));
    if (p === '/runs/health') return json(page((q('period') === '30d' ? HEALTH_30D : HEALTH_7D).filter((h) => !q('company') || h.company === q('company')).map((h) => ({ ...h, period: q('period') === '30d' ? '30d' : '7d' }))));
    // ---- §21.10
    if (p === '/digital-ceo') { const rows = await predictions(decisions); return json({ stats: (['30d', '90d', 'all'] as const).map((w) => stats(rows, w)), settings: settings.digital_ceo, hidden: rows.filter((r) => !r.seen_before).length }); }
    if (p === '/digital-ceo/predictions') {
      const rows = await predictions(decisions);
      const c = q('correct');
      return json(page(rows.filter((r) => (c == null || String(r.correct) === c) && (!q('kind') || r.kind === q('kind'))).map(({ _decided, ...r }) => r)));
    }
    if (p === '/digital-ceo/principles') return json(principles);
    // ---- §21.13
    if (p === '/substitutes') return json(subs);
    const lg = /^\/connections\/([\w-]+)\/login\/([\w-]+)$/.exec(p);
    if (lg) { const l = logins.find((x) => x.id === lg[2]); return l ? json(loginOut(l)) : problem(404, 'not_found', 'این ورود پیدا نشد.'); }
    if (p === '/creatives') {
      rendered ??= Promise.all(creatives.map(renderCreative)).then(() => undefined);
      await rendered;
      await Promise.all(creatives.map(renderCreative));
      return json(page(creatives.filter((c) => (!q('company') || c.company === q('company')) && (!q('state') || c.state === q('state')) && (!q('kind') || c.kind === q('kind'))).sort((a, b) => b.created_at.localeCompare(a.created_at)).map(creativeOut)));
    }
    const cr = /^\/creatives\/(CR-\d+)$/.exec(p);
    if (cr) { const x = creatives.find((y) => y.ref === cr[1]); if (!x) return problem(404, 'not_found', 'این درخواست پیدا نشد.'); await renderCreative(x); return json(creativeOut(x)); }
    return null;
  }

  // ------------------------------------------------------------------ writes --
  if (p === '/owner/settings' && m === 'PUT') {
    const bad = unmatched(req, settings.version);
    if (bad) return bad;
    const b = await body<Record<string, any>>();
    for (const [k, v] of Object.entries(b)) settings[k] = v && typeof v === 'object' && !Array.isArray(v) && settings[k] && typeof settings[k] === 'object' ? { ...settings[k], ...v } : v;
    settings.version += 1;
    return json(settings);
  }
  // ---- §21.1
  const mw = /^\/decisions\/(D-\d+)\/memo$/.exec(p);
  if (mw && m === 'POST') {
    const d = decisions.find((x) => x.ref === mw[1]);
    if (!d) return problem(404, 'not_found', 'این کارت پیدا نشد.');
    if (d.status !== 'pending') return problem(409, 'decision_not_pending', 'این کارت دیگر منتظر تصمیم نیست.');
    const { mode = 'standard' } = await body<{ mode?: 'standard' | 'devil' }>();
    if (mode !== 'standard' && mode !== 'devil') return problem(422, 'validation_failed', 'حالت یادداشت standard یا devil است.');
    const old = memos.find((x) => x.decision === d.ref && x.mode === mode && x.decision_version === d.version && x.state !== 'failed');
    const x = old ?? makeMemo(d, mode, 'owner', 'writing', 0);
    d.memos = memos.filter((y) => y.decision === d.ref).map((y) => ({ ref: y.ref, mode: y.mode, state: y.state }));
    return json(memoOut(x), 202);
  }
  // ---- §21.2
  if (p === '/ask' && m === 'POST') {
    const key = req.headers.get('Idempotency-Key') ?? '';
    const hit = keys.get(key);
    if (hit) return json(hit.body, hit.status);
    const b = await body<{ q?: string; scope?: any }>();
    const text = (b.q ?? '').trim();
    if (!text) return problem(422, 'validation_failed', 'پرسش خالی است.', { fields: { q: 'required' } });
    if (text.length > 500) return problem(422, 'validation_failed', 'پرسش حداکثر ۵۰۰ نویسه است.', { fields: { q: 'max 500' } });
    const rule = CORPUS.find((r) => r.re.test(text)) ?? null;
    const a = { id: `ak${asks.length + 1}`, ref: `AK-${pad(asks.length + 1, 4)}`, q: text, scope: b.scope ?? null, state: 'queued', found: rule ? 6 + (seedOf(text) % 9) : 0,
      answer_md: rule ? null : `چیزی پیدا نشد. در مصوبه‌ها، تصمیم‌ها، خروجی‌ها، پیام‌ها، سندها و کد چیزی درباره‌ی «${text.slice(0, 40)}» نیست؛ مدلی هم اجرا نشد. کلیدواژه‌ی دیگری امتحان کن.`,
      citations: [], not_indexed: [], usage: { tokens: 0, usd: '0.000000' }, created_at: stamp(), finished_at: null, _rule: rule };
    asks.unshift(a);
    const out = askOut(a);
    keys.set(key, { status: 202, body: out });
    return json(out, 202);
  }
  // ---- §21.3
  const rv = /^\/reviews\/weekly\/(WR-\d+)\/(start|finish|items\/(\d+))$/.exec(p);
  if (rv) {
    const r = reviews.find((x) => x.ref === rv[1]);
    if (!r) return problem(404, 'not_found', 'این مرور پیدا نشد.');
    if (rv[2] === 'start') { if (r.state !== 'ready') return problem(409, 'validation_failed', 'این مرور شروع‌شدنی نیست.'); Object.assign(r, { state: 'in_progress', started_at: stamp(), version: r.version + 1 }); return json(r); }
    if (rv[2] === 'finish') {
      if (r.state !== 'in_progress') return problem(409, 'validation_failed', 'مرور شروع نشده.');
      const dur = Math.round((Date.now() - Date.parse(r.started_at)) / 1000);
      Object.assign(r, { state: 'done', finished_at: stamp(), duration_s: dur, minutes_ref: 'O-000048', version: r.version + 1 });
      ctx?.deliverables.unshift({ id: 'o-O-000048', ref: 'O-000048', company: 'HQ', title: `صورت‌جلسه‌ی مرور هفتگی ${r.ref}`, summary: `${r.agenda.filter((i: any) => i.status === 'done').length} مورد انجام شد، ${r.agenda.filter((i: any) => i.status === 'deferred').length} مورد عقب افتاد.`, body: r.agenda.map((i: any) => `- ${i.title_fa}: ${i.status}${i.owner_note ? ` (${i.owner_note})` : ''}`).join('\n'),
        producer: { code: 'HQ-ADV', company: 'HQ', kind: 'advisor', department: null, title_fa: 'مشاور کل' }, rating: null, created_at: stamp(), work_ref: null, attachments: [], evidence: [], produced_with: { model: 'claude-opus-5-5', effort: 'xhigh', label_fa: 'Opus 5.5 · xhigh' }, usage: { tokens: 0, usd: '0.00' }, work_id: null });
      return json(r);
    }
    if (m === 'PATCH') {
      const bad = unmatched(req, r.version);
      if (bad) return bad;
      const it = r.agenda.find((x: any) => x.n === Number(rv[3]));
      if (!it) return problem(404, 'not_found', 'این مورد در دستور نیست.');
      const b = await body<{ status?: string; owner_note?: string }>();
      if (b.status && !['open', 'done', 'deferred'].includes(b.status)) return problem(422, 'validation_failed', 'وضعیت نامعتبر.');
      Object.assign(it, { ...(b.status ? { status: b.status } : {}), ...(b.owner_note !== undefined ? { owner_note: b.owner_note || null } : {}) });
      r.version += 1;
      return json(r);
    }
  }
  // ---- §21.7 a new connection
  if (p === '/connections' && m === 'POST') {
    const deny = needsStepUp(req);
    if (deny) return deny;
    const key = req.headers.get('Idempotency-Key');
    if (!key) return problem(422, 'validation_failed', 'Idempotency-Key لازم است.');
    const hit = keys.get(key);
    if (hit) return json(hit.body, hit.status);
    const b = await body<any>();
    const list = ctx?.connections ?? [];
    if (!/^[a-z0-9][a-z0-9-]{2,39}$/.test(b.key ?? '')) return problem(422, 'validation_failed', 'کلید فقط حروف کوچک لاتین، عدد و خط تیره است.', { fields: { key: 'pattern' } });
    if (list.some((c) => c.key === b.key)) return problem(409, 'version_conflict', 'اتصالی با همین کلید هست.');
    if (!['anthropic', 'openai', 'google', 'deepseek', 'mistral', 'openai_compatible'].includes(b.provider)) return problem(422, 'validation_failed', 'مسیریاب این ارائه‌دهنده را نمیشناسد.', { fields: { provider: 'unsupported' } });
    if (b.base_url && (b.provider !== 'openai_compatible' || !/^https:\/\//.test(b.base_url) || /\/\/(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(b.base_url))) return problem(422, 'validation_failed', 'نشانی پایه فقط برای سازگار با OpenAI، با https و نه نشانی خصوصی.', { fields: { base_url: 'egress guard' } });
    if (!Array.isArray(b.models) || !b.models.length) return problem(422, 'validation_failed', 'دست‌کم یک مدل لازم است.', { fields: { models: 'required' } });
    const c = { id: `c${list.length + 1}`, key: b.key, display_name: b.display_name, kind: b.kind, provider: b.provider, status: 'pending_secret', status_reason: 'منتظر کلید', models: b.models, default_model: b.default_model ?? b.models[0], fallback_priority: b.fallback_priority ?? null, has_secret_ref: false, limits: b.limits ?? {}, pricing: b.pricing ?? {}, quota_reset_at: null, base_url: b.base_url ?? null, updated_at: stamp(), version: 1 };
    list.push(c);
    keys.set(key, { status: 201, body: c });
    return json(c, 201);
  }
  const cs = /^\/connections\/([\w-]+)\/secret$/.exec(p);
  if (cs && m === 'POST' && ctx) {
    const c = ctx.connections.find((x) => x.id === cs[1]);
    if (c && c.status === 'pending_secret') {
      const deny = needsStepUp(req);
      if (deny) return deny;
      await body();
      Object.assign(c, { status: 'verifying', status_reason: 'بررسی با فراخوانی بی‌هزینه (فهرست مدل‌ها)', has_secret_ref: true, version: c.version + 1, updated_at: stamp() });
      verifying.set(c.id, Date.now() + 3_500);
      return json({ connection: c.key, stored: true });
    }
  }
  // ---- §21.8
  if (p === '/notes' && m === 'POST') {
    const key = req.headers.get('Idempotency-Key') ?? '';
    const hit = keys.get(key);
    if (hit) return json(hit.body, hit.status);
    const b = await body<{ text_md?: string; source?: string; file_id?: string; tags?: string[] }>();
    if (!b.text_md?.trim()) return problem(422, 'validation_failed', 'یادداشت خالی است.');
    const n = Math.max(...notes.map((x) => Number(x.ref.slice(3)))) + 1;
    const x = note(n, 0, b.text_md.trim(), { source: b.source === 'voice' ? 'voice' : 'text', file_id: b.file_id ?? null, tags: (b.tags ?? []).slice(0, 8) });
    Object.assign(x, { created_at: stamp(), updated_at: stamp() });
    notes.unshift(x);
    keys.set(key, { status: 201, body: x });
    return json(x, 201);
  }
  const nw = /^\/notes\/(NT-\d+)(\/promote)?$/.exec(p);
  if (nw) {
    const x = notes.find((y) => y.ref === nw[1]);
    if (!x) return problem(404, 'not_found', 'این یادداشت پیدا نشد.');
    if (nw[2]) {
      if (x.status !== 'open') return problem(409, 'validation_failed', 'فقط یادداشت باز تبدیل میشود.');
      const b = await body<{ to?: string; company?: string }>();
      if (b.to === 'work' && !b.company) return problem(422, 'validation_failed', 'برای کار، شرکت را انتخاب کن.', { fields: { company: 'required' } });
      const ref = b.to === 'work' ? `W-0001${40 + notes.length}` : b.to === 'order' ? `F-00${10 + notes.length}` : b.to === 'errand' ? `E-00${10 + notes.length}` : null;
      if (!ref) return problem(422, 'validation_failed', 'مقصد کار، فرمان یا کار دستیار است.');
      Object.assign(x, { status: 'promoted', promoted_to: { kind: b.to, ref }, updated_at: stamp(), version: x.version + 1 });
      return json(x);
    }
    if (m === 'PATCH') {
      const bad = unmatched(req, x.version);
      if (bad) return bad;
      const b = await body<{ text_md?: string; tags?: string[]; status?: string }>();
      if (b.status && b.status !== 'archived') return problem(422, 'validation_failed', 'فقط بایگانی؛ یادداشت حذف نمیشود.');
      if (b.text_md !== undefined && !b.text_md.trim()) return problem(422, 'validation_failed', 'یادداشت خالی نمیشود.');
      Object.assign(x, { ...(b.text_md !== undefined ? { text_md: b.text_md.trim() } : {}), ...(b.tags ? { tags: b.tags.slice(0, 8) } : {}), ...(b.status ? { status: b.status } : {}), updated_at: stamp(), version: x.version + 1 });
      return json(x);
    }
  }
  // ---- §21.10
  if (p === '/digital-ceo/principles' && m === 'POST') {
    const b = await body<{ text_fa?: string }>();
    if (!b.text_fa?.trim()) return problem(422, 'validation_failed', 'متن اصل خالی است.');
    const x = { id: `dp${principles.length + 1}`, ref: `DP-${pad(principles.length + 1, 3)}`, text_fa: b.text_fa.trim(), sources: [{ kind: 'owner', ref: 'owner' }], status: 'active', edited_by_owner: true, version: 1, updated_at: stamp() };
    principles.push(x);
    return json(x, 201);
  }
  const pw = /^\/digital-ceo\/principles\/(DP-\d+)(\/accept)?$/.exec(p);
  if (pw) {
    const x = principles.find((y) => y.ref === pw[1]);
    if (!x) return problem(404, 'not_found', 'این اصل پیدا نشد.');
    if (pw[2]) { if (x.status !== 'proposed') return problem(409, 'validation_failed', 'فقط اصل پیشنهادی پذیرفته میشود.'); Object.assign(x, { status: 'active', version: x.version + 1, updated_at: stamp() }); return json(x); }
    if (m === 'PUT') {
      const bad = unmatched(req, x.version);
      if (bad) return bad;
      const b = await body<{ text_fa?: string; status?: string }>();
      if (!b.text_fa?.trim()) return problem(422, 'validation_failed', 'متن اصل خالی است.');
      Object.assign(x, { text_fa: b.text_fa.trim(), status: b.status === 'retired' ? 'retired' : 'active', edited_by_owner: x.edited_by_owner || b.text_fa.trim() !== x.text_fa, version: x.version + 1, updated_at: stamp() });
      return json(x);
    }
  }
  // ---- §21.13
  const st = /^\/substitutes\/(gpt|gemini|deepseek)\/(seats|web\/logout)$/.exec(p);
  if (st) {
    const s = subs.find((x) => x.player === st[1]);
    if (!s) return problem(404, 'not_found', 'این بازیکن پیدا نشد.');
    const deny = needsStepUp(req);
    if (deny) return deny;
    if (st[2] === 'web/logout') { Object.assign(s.web, { state: 'signed_out', last_failure: null }); s.version += 1; return json(s); }
    const bad = unmatched(req, s.version);
    if (bad) return bad;
    const b = await body<any[]>();
    if (!Array.isArray(b)) return problem(422, 'validation_failed', 'فهرست جایگاه‌ها لازم است.');
    for (const x of b) {
      if (x.per_day < 0 || x.per_day > 500) return problem(422, 'validation_failed', `سقف روزانه‌ی ${x.seat} بین ۰ و ۵۰۰ است.`);
      if (!s.models.some((mm: any) => mm.id === x.model)) return problem(422, 'validation_failed', `مدل ${x.model} در اتصال این بازیکن نیست.`);
      if (s.runner == null && x.via === 'cli') return problem(422, 'validation_failed', 'این بازیکن CLI ندارد؛ فقط وب.');
    }
    s.seats = b.map((x) => ({ ...x, used_today: s.seats.find((y: any) => y.seat === x.seat)?.used_today ?? 0, ...(x.per_day_video != null ? { used_today_video: s.seats.find((y: any) => y.seat === x.seat)?.used_today_video ?? 0 } : {}) }));
    s.version += 1;
    return json(s);
  }
  const cl = /^\/connections\/([\w-]+)\/(login|logout)$/.exec(p);
  if (cl && m === 'POST') {
    const c = ctx?.connections.find((x) => x.id === cl[1]);
    const s = subs.find((x) => x.connection === c?.key);
    if (!c || !s) return problem(404, 'not_found', 'این اتصال پیدا نشد.');
    const deny = needsStepUp(req);
    if (deny) return deny;
    if (cl[2] === 'logout') { Object.assign(s.login, { state: 'signed_out', since: null }); Object.assign(s, { status: 'off', status_reason: 'ورود CLI پاک شد؛ جایگاه‌های CLI رد میشوند.', version: s.version + 1 }); return json({ connection: c.key, signed_out: true }); }
    if (!s.runner) return problem(409, 'not_ready', 'این بازیکن CLI ندارد؛ فقط از مرورگر لاگین‌شده‌ی هاب کار میکند.');
    const l = { id: `lg${logins.length + 1}`, connection: c.key, method: s.player === 'gemini' ? 'auth_code' : 'device_code',
      verification_url: s.player === 'gemini' ? 'https://accounts.google.com/o/oauth2/v2/auth?client_id=gemini-cli&response_type=code' : 'https://auth.openai.com/codex/device',
      user_code: s.player === 'gemini' ? null : `${String.fromCharCode(65 + (logins.length % 20))}K7M-4TZP`, expires_at: ahead(10), state: 'waiting', status_reason: null, _t: Date.now() };
    logins.push(l);
    Object.assign(s.login, { state: 'signing_in' });
    return json(loginOut(l), 201);
  }
  const lc = /^\/connections\/([\w-]+)\/login\/([\w-]+)\/code$/.exec(p);
  if (lc && m === 'POST') {
    const l = logins.find((x) => x.id === lc[2]);
    if (!l || l.state !== 'waiting' || l.method !== 'auth_code') return problem(409, 'validation_failed', 'این ورود منتظر کد نیست.');
    const b = await body<{ code?: string }>();
    if (!b.code || b.code.trim().length < 6) return problem(422, 'validation_failed', 'کد کوتاه است.');
    finishLogin(l);
    return json(loginOut(l));
  }
  if (p === '/creatives' && m === 'POST') {
    const key = req.headers.get('Idempotency-Key') ?? '';
    const hit = keys.get(key);
    if (hit) return json(hit.body, hit.status);
    const b = await body<any>();
    if (!b.company || !b.brief_md?.trim()) return problem(422, 'validation_failed', 'شرکت و brief لازم است.');
    if (!ASPECT[b.placement]) return problem(422, 'validation_failed', 'جای انتشار نامعتبر است.');
    if (b.kind === 'video' && (!b.duration_s || b.duration_s > 10)) return problem(422, 'validation_failed', 'ویدیو حداکثر ۱۰ ثانیه است.', { fields: { duration_s: '≤ 10' } });
    const player = b.kind === 'video' ? 'gemini' : b.player ?? settings.substitutes.creative_default_image;
    const s = subs.find((x) => x.player === player);
    const seatRow = s?.seats.find((x: any) => x.seat === 'creative');
    const n = Math.max(...creatives.map((x) => Number(x.ref.slice(3)))) + 1;
    const x: any = { id: `cr${n}`, ref: `CR-${pad(n, 4)}`, company: b.company, kind: b.kind === 'video' ? 'video' : 'image', brief_md: b.brief_md.trim(), placement: b.placement, aspect: ASPECT[b.placement], duration_s: b.kind === 'video' ? b.duration_s : null,
      overlay: b.overlay ?? null, composed: null, player, model: s?.models[0]?.id ?? '', path: 'web', state: 'queued', requested_by: owner, work_ref: null, errand_ref: null, files: [], review_md: null, source: null, ai_generated: true,
      prompt_md: `Advertising ${b.kind === 'video' ? `teaser video, ${b.duration_s} s` : 'image'} for ${BRAND[b.company]?.mark ?? b.company}, aspect ${ASPECT[b.placement]}, in the brand palette. Brief (masked): ${b.brief_md.trim().slice(0, 160)} No text, no letters, no logos anywhere; keep the lower third calm for an overlay.`,
      created_at: stamp(), updated_at: stamp(), version: 1, created: 0, _ready: Date.now() + 6_000 };
    if (!s || s.web.state !== 'signed_in' || !seatRow?.enabled) Object.assign(x, { state: 'failed', _ready: undefined, review_md: `ساخته نشد: پروفایل وب ${player === 'gemini' ? 'gemini-web' : 'chatgpt-web'} وارد نیست یا جایگاه creative خاموش است؛ هیچ جابه‌جایی پنهانی به بازیکن دیگر نیست.` });
    else if (x.kind === 'image' && seatRow.used_today >= seatRow.per_day) return problem(429, 'rate_limited', 'سقف روزانه‌ی عکس این بازیکن پر شده.', { retry_after: 3600 });
    else if (x.kind === 'image') seatRow.used_today += 1;
    creatives.unshift(x);
    const out = creativeOut(x);
    keys.set(key, { status: 201, body: out });
    return json(out, 201);
  }
  const ca = /^\/creatives\/(CR-\d+)\/(accept|reject)$/.exec(p);
  if (ca) {
    const x = creatives.find((y) => y.ref === ca[1]);
    if (!x) return problem(404, 'not_found', 'این درخواست پیدا نشد.');
    if (x.state !== 'review') return problem(409, 'validation_failed', 'فقط نتیجه‌ی در بازبینی پذیرفته یا رد میشود.');
    const b = await body<{ note?: string }>();
    Object.assign(x, { state: ca[2] === 'accept' ? 'accepted' : 'rejected', review_md: b.note ? `${x.review_md ?? ''}\n\nمالک: «${b.note}»` : x.review_md, updated_at: stamp(), version: x.version + 1 });
    return json(creativeOut(x));
  }
  return null;
}
