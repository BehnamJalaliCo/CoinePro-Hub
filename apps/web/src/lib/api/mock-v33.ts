// Development-only fixtures (npm run dev:mock) for contract §33 ⟨1.15⟩, in the hub's own shapes (apps/api/openapi/hq-api.v1.json): a money
// amount the hub keeps as a Decimal is a string here too, ids the routes take as UUIDs are UUIDs, a list is a page or a bare array exactly as
// the route answers, and every request body is checked against its model the way the hub does it (any other key is a 422, `If-Match` and
// `Idempotency-Key` where the route needs them, the `payment.source` step-up on the SHA-256 of the exact body). The advisor's usage
// reports, payment sources with payments that agree and disagree and a daily reconcile, a revenue board with a forecast band, a small CRM,
// affiliate gaps, a money impact on some decisions (and the hub's `sort=impact`), two order reports (a split work with a failed part; a
// work on the company's own server, which can be stopped), each company's journey, and personas with the message test. Everything is
// computed from fixed numbers and the day's date, never at random; kept in memory so the end-to-end checks can add, edit and read. No wallet
// address, key or schema of any company is here: the addresses are placeholders. Never bundled in production (reached only through
// ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

const json = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string, fields?: Record<string, string>) => json({ code, message_fa, status, title: code, type: 'about:blank', fields: fields ?? null }, status);
const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (d: string, n: number) => iso(new Date(Date.parse(`${d}T12:00:00Z`) + n * 86_400_000));
const today = () => iso(new Date());
const ago = (days: number, hm = '09:30') => `${addDays(today(), -days)}T${hm}:00Z`;
const nowIso = () => new Date().toISOString();
const code = (c: string) => [...c].reduce((a, ch) => a + ch.charCodeAt(0), 0);
const scale = (c: string) => ({ TY: 1, FX: 1.6, PC: 0.7 } as Record<string, number>)[c] ?? [1, 1.6, 0.7][code(c) % 3]!;
const monthsBack = (n: number) => { const d = new Date(); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() - n); return d.toISOString().slice(0, 7); };
const monthsAhead = (n: number) => monthsBack(-n);
/** A Decimal as the hub writes it. */
const d2 = (n: number) => n.toFixed(2);
/** A stable UUID: `tag` names the kind of row, `n` the row. */
const uuid = (tag: number, n: number) => `${tag.toString(16).padStart(8, '0')}-0000-4000-8000-${n.toString(16).padStart(12, '0')}`;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** The hub's models forbid extra keys: the first unknown key is a 422. */
const extra = (b: Record<string, unknown>, keys: string[]) => {
  const bad = Object.keys(b).find((k) => !keys.includes(k));
  return bad ? problem(422, 'validation_failed', 'درخواست فیلد ناشناخته دارد.', { [bad]: 'extra fields not permitted' }) : null;
};
async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((x) => x.toString(16).padStart(2, '0')).join('');
}
/** The last step-up the panel asked for (`POST /auth/step-up/options {action, target}`), so a sealed route can check its target. */
let lastStepUp: { action: string; target: string } | null = null;

// ================================================================================================== usage ==
const pack = (period: 'day' | 'week', k: number) => ({
  period, from: `${addDays(today(), period === 'day' ? -1 - k : -7 - k * 7)}T00:00:00Z`, to: `${addDays(today(), period === 'day' ? -k : -k * 7)}T00:00:00Z`,
  by_domain: [{ domain: 'work', tokens: 1_820_000, usd_equiv: 14.2, share: 0.46 }, { domain: 'media', tokens: 940_000, usd_equiv: 7.4, share: 0.24 }, { domain: 'advisor', tokens: 610_000, usd_equiv: 4.8, share: 0.15 }, { domain: 'talk', tokens: 210_000, usd_equiv: 4.6, share: 0.15 }],
  by_company: [{ company: 'TY', tokens: 2_100_000, usd_equiv: 17.3, share: 0.56 }, { company: 'FX', tokens: 900_000, usd_equiv: 8.1, share: 0.26 }, { company: 'PC', tokens: 470_000, usd_equiv: 5.6, share: 0.18 }],
  top_runs: [{ ref: 'LR-0412', role: 'growth', tokens: 410_000 }, { ref: 'LR-0408', role: 'scriptwriter', tokens: 330_000 }, { ref: 'R-0099', role: null, tokens: 120_000 }],
  voice_usd: 4.6, lines: { runs: 38, tokens: 1_250_000 }, ads_spend_usd: 220, vs_prev: { tokens_pct: 12.4, usd_pct: 9.8 },
  anomalies: k === 0 ? [{ kind: 'spike', note: 'مصرف تحلیل سئوی تریدیار سه‌شنبه ۲ برابر روز عادی بود.' }] : [],
});
const reports: any[] = [
  { ref: 'UR-0004', period: 'day', pack: pack('day', 0), words: 'model', text: { lines_fa: ['دیروز حدود 31 دلار مصرف شد؛ 10٪ بیشتر از روز قبل.', 'بیشترین سهم با کار فرمان‌ها بود: 46٪.', 'تحلیل سئوی تریدیار 410 هزار توکن برد و از همه گران‌تر بود.'], saving_fa: 'تحلیل سئو را به یک بار در هفته ببرید؛ حدود 6 دلار در روز صرفه‌جویی میشود.' }, at: ago(0, '04:25') },
  { ref: 'UR-0003', period: 'week', pack: pack('week', 0), words: 'model', text: { lines_fa: ['هفته‌ی گذشته 188 دلار مصرف شد؛ 12٪ بیشتر از هفته‌ی قبل.', 'کار فرمان‌ها نیمی از مصرف را برد و بیشتر آن برای تریدیار بود.', 'صدا 4.6 دلار شد و تبلیغات 220 دلار.', 'سه‌شنبه یک جهش مصرف در تحلیل سئو دیده شد.'], saving_fa: 'اجرای شبانه‌ی تحلیل سئو را به هفتگی ببرید؛ ماهانه حدود 40 دلار کم میشود.' }, at: ago(3, '05:30') },
  { ref: 'UR-0002', period: 'day', pack: pack('day', 1), words: 'code', text: { lines_fa: ['پریروز 28 دلار مصرف شد.', 'بیشترین سهم با «کار فرمان‌ها و شرکت‌ها» بود (46٪).', 'چیز غیرعادی نبود.'], saving_fa: 'برای صرفه‌جویی، اول سقف مصرف «کار فرمان‌ها و شرکت‌ها» را ببینید.' }, at: ago(1, '04:25') },
  { ref: 'UR-0001', period: 'week', pack: pack('week', 1), words: 'model', text: { lines_fa: ['دو هفته پیش 168 دلار مصرف شد.', 'بیشترین سهم با مشاور بود.', 'تبلیغات 180 دلار بود.'], saving_fa: 'پاسخ‌های تکراری پشتیبانی را از دانشنامه بدهید تا توکن کم‌تر برود.' }, at: ago(10, '05:30') },
];
let nUr = 5;

// ================================================================================================ payments ==
const BSC_RE = /^0x[0-9a-fA-F]{40}$/, TRON_RE = /^T[1-9A-HJ-NP-Za-km-z]{33}$/;
const src = (n: number, o: Record<string, unknown>): any => ({ id: uuid(0x5a1e5, n), adapter: 'chain-read', network: null, address: null, server: null, enabled: true, state: 'ok', last_read_at: null, last_error_fa: null, ...o });
const sources: any[] = [
  src(1, { company: 'TY', kind: 'chain', network: 'bsc_usdt', address: '0x5a1e500000000000000000000000000000000a11', last_read_at: ago(0, '06:10') }),
  src(2, { company: 'TY', kind: 'chain', network: 'trc20_usdt', address: 'TDemoHubWaxxetPaymentsReadxnyQAbcd', state: 'error', last_read_at: ago(1, '06:10'), last_error_fa: 'شبکه‌ی ترون جواب نداد؛ ساعتی دیگر دوباره امتحان میشود.' }),
  src(3, { company: 'TY', kind: 'ledger', adapter: 'ledger_v1', server: 'ty-app', last_read_at: ago(0, '06:05') }),
  src(4, { company: 'FX', kind: 'ledger', adapter: 'ledger_v1', state: 'not_configured' }),
];
let nSrc = 5;
const pay = (i: number, o: Record<string, unknown>): any => ({
  id: uuid(0x9a7, i), source: sources[0].id, plan: 'پلن ماهانه', network: 'bsc_usdt', period_start: null, period_end: null, checked_at: ago(0, '06:20'), chain_amount: null, note_fa: null, ...o,
});
const payRows = (c: string) => [
  pay(1, { company: c, ext_id: 'EX-1001', customer: 'cu_8f2a1c', amount_usdt: '49.00', chain_amount: '49.00', tx_hash: '0xdemo0001aaaa1111bbbb2222cccc3333', paid_at: ago(1), status: 'matched' }),
  pay(2, { company: c, ext_id: 'EX-1002', customer: 'cu_19be77', amount_usdt: '49.00', chain_amount: '49.00', tx_hash: '0xdemo0002aaaa1111bbbb2222cccc3333', paid_at: ago(2), status: 'matched' }),
  pay(3, { company: c, ext_id: 'EX-1003', customer: 'cu_c04d90', plan: 'پلن سالانه', amount_usdt: '390.00', network: 'trc20_usdt', source: sources[1].id, tx_hash: 'demo0003aaaa1111bbbb2222cccc3333', paid_at: ago(4), status: 'ledger_only', note_fa: 'تأیید شده ولی واریزش روی شبکه پیدا نشد.' }),
  pay(4, { company: c, ext_id: 'chain-7781', customer: null, plan: null, amount_usdt: '49.00', chain_amount: '49.00', tx_hash: '0xdemo0004aaaa1111bbbb2222cccc3333', paid_at: ago(5), status: 'chain_only', note_fa: 'پول رسیده ولی در دفتر شرکت مشتری‌ای ندارد.' }),
  pay(5, { company: c, ext_id: 'EX-1005', customer: 'cu_5d1e02', amount_usdt: '49.00', chain_amount: '35.00', tx_hash: '0xdemo0005aaaa1111bbbb2222cccc3333', paid_at: ago(7), status: 'amount_mismatch' }),
  pay(6, { company: c, ext_id: 'EX-1006', customer: 'cu_a7733b', amount_usdt: '49.00', tx_hash: '0xdemo0006aaaa1111bbbb2222cccc3333', paid_at: ago(0, '05:00'), status: 'pending_chain' }),
  pay(7, { company: c, ext_id: 'EX-1007', customer: 'cu_store01', plan: 'اشتراک اپ‌استور', amount_usdt: null, network: null, source: sources[2].id, tx_hash: null, paid_at: ago(3), status: 'matched' }),
];
const reconcile = (c: string) => Array.from({ length: 14 }, (_, i) => {
  const day = addDays(today(), -i);
  const lo = i === 4 ? 1 : 0, co = i === 5 ? 1 : 0, mm = i === 7 ? 1 : 0, pc = i === 0 ? 1 : 0, m = 2 + (i % 3);
  return { company: c, day, ledger_count: m + lo + mm + pc, chain_count: m + co + mm, matched: m, ledger_only: lo, chain_only: co, amount_mismatch: mm, pending_chain: pc,
    note_fa: lo ? 'یک پرداخت تأییدشده روی شبکه پیدا نشد.' : co ? 'یک واریز بدون مشتری رسیده.' : mm ? 'یک مبلغ از قیمت طرح کم‌تر بود.' : '' };
});

// ============================================================================================ revenue board ==
const board = (c: string | null) => {
  const f = c ? scale(c) : 3.3;
  const mrr = [520, 740, 910, 1180, 1390, 1640, 1820, 2050].map((v) => Math.round(v * f));
  const months = mrr.map((v, i) => ({ month: monthsBack(7 - i), mrr_usdt: d2(v), new_customers: Math.round((6 + i) * f), churned: Math.round((1 + (i % 3)) * f), active: Math.round((10 + i * 7) * f), arpu_usdt: d2(Math.round((v / ((10 + i * 7) * f)) * 10) / 10) }));
  const fc = [2230, 2410, 2590].map((v, i) => ({ month: monthsAhead(i + 1), mrr_usdt: d2(Math.round(v * f)), low: d2(Math.round((v - 120 - i * 60) * f)), high: d2(Math.round((v + 120 + i * 60) * f)) }));
  return {
    company: c, period: 'month', months, churn_rate: 0.062, ltv_usdt: d2(Math.round(790 * f)), cac_usdt: '18.40', payback_months: 1.6,
    cohorts: [0, 1, 2, 3, 4].map((k) => ({ start_month: monthsBack(7 - k), size: Math.round((9 + k * 2) * f), retained: [100, 92, 86, 81, 77, 74].slice(0, 6 - k) })),
    forecast: fc, forecast_basis_fa: 'روند هشت ماه گذشته (روش هولت)، با بازه‌ای که هشت بار از ده بار درست درمی‌آید.',
    roi: { revenue_usdt: d2(Math.round(2050 * f)), cost_usd: { tokens: d2(Math.round(310 * f)), voice: d2(Math.round(46 * f)), ads: d2(Math.round(220 * f)), servers: null }, ratio: 3.5 },
    cost_per_output: [{ kind: 'line_run', count: Math.round(38 * f), usd_each: '0.42' }, { kind: 'deliverable', count: Math.round(64 * f), usd_each: '0.31' }, { kind: 'order', count: Math.round(12 * f), usd_each: '1.85' }],
  };
};
const bySource = (c: string | null) => [
  { company: 'TY', affiliate_usdt: '1240.00', payments_usdt: '2050.00', store_payments: 3, total_usdt: '3290.00' },
  { company: 'FX', affiliate_usdt: '600.00', payments_usdt: '0.00', store_payments: 0, total_usdt: '600.00' },
  { company: 'PC', affiliate_usdt: '0.00', payments_usdt: '410.00', store_payments: 0, total_usdt: '410.00' },
].filter((r) => !c || r.company === c);

// ===================================================================================================== sales ==
const SALES = { kind: 'agent', code: 'TY-SALES-01', display_fa: 'کارشناس فروش تریدیار' };
const lead = (n: number, o: Record<string, unknown>): any => ({ ref: `LD-${String(n).padStart(6, '0')}`, company: 'TY', name_fa: null, value_usdt: '49.00', next_at: null, next_fa: null, assignee: null, lost_reason_fa: null, version: 1, ...o });
const leads: any[] = [
  lead(1, { source: 'support', name_fa: 'علی ر.', contact: 'cu_8f2a1c', stage: 'new', next_at: ago(-1), next_fa: 'پیام خوش‌آمد و معرفی پلن ماهانه', assignee: SALES, events: [{ at: ago(2), kind: 'created', note_fa: 'از پشتیبانی تلگرام ساخته شد.' }], created_at: ago(2), updated_at: ago(2) }),
  lead(2, { source: 'telegram', name_fa: 'سارا م.', contact: 'cu_19be77', stage: 'contacted', next_at: ago(1), next_fa: 'پیگیری دوباره بعد از دو روز', events: [{ at: ago(5), kind: 'created', note_fa: 'از ربات تلگرام آمد.' }, { at: ago(3), kind: 'stage', note_fa: 'به «تماس گرفته شد» رفت.' }], created_at: ago(5), updated_at: ago(3), version: 2 }),
  lead(3, { source: 'payment', contact: 'cu_unknown1', stage: 'qualified', events: [{ at: ago(5), kind: 'created', note_fa: 'از یک واریز بدون مشتری ساخته شد.' }], created_at: ago(5), updated_at: ago(5) }),
  lead(4, { source: 'referral', name_fa: 'رضا ک.', contact: 'cu_5d1e02', stage: 'trial', value_usdt: '390.00', next_at: ago(-3), next_fa: 'یادآوری پایان دوره‌ی آزمایشی', assignee: SALES, events: [{ at: ago(9), kind: 'created', note_fa: 'معرفی از یک مشتری.' }], created_at: ago(9), updated_at: ago(4) }),
  lead(5, { source: 'site', name_fa: 'نیما ا.', contact: 'cu_a7733b', stage: 'paid', events: [{ at: ago(0, '05:00'), kind: 'stage', note_fa: 'پرداخت رسید؛ خودکار «پرداخت کرد» شد.' }], created_at: ago(12), updated_at: ago(0) }),
  lead(6, { source: 'manual', name_fa: 'مریم ص.', contact: 'cu_zz90abcd', stage: 'lost', lost_reason_fa: 'قیمت را بالا دید.', events: [{ at: ago(8), kind: 'stage', note_fa: 'از دست رفت.' }], created_at: ago(20), updated_at: ago(8) }),
];
let nLd = 7;
const STAGES: Array<{ stage: string; title_fa: string; kind: 'open' | 'won' | 'lost'; median: number | null }> = [
  { stage: 'new', title_fa: 'تازه', kind: 'open', median: 1.5 }, { stage: 'contacted', title_fa: 'تماس گرفته شد', kind: 'open', median: 2 },
  { stage: 'qualified', title_fa: 'جدی', kind: 'open', median: 3 }, { stage: 'trial', title_fa: 'آزمایشی', kind: 'open', median: 6 },
  { stage: 'paid', title_fa: 'پرداخت کرد', kind: 'won', median: null }, { stage: 'lost', title_fa: 'از دست رفت', kind: 'lost', median: null },
];
const pipeline = (c: string) => {
  const mine = leads.filter((l) => l.company === c);
  const of = (k: string) => mine.filter((l) => l.stage === k);
  const sum = (xs: any[]) => xs.reduce((a, l) => a + Number(l.value_usdt ?? 0), 0);
  const won = STAGES.filter((s) => s.kind === 'won').flatMap((s) => of(s.stage)).length, lost = STAGES.filter((s) => s.kind === 'lost').flatMap((s) => of(s.stage)).length;
  const open = STAGES.filter((s) => s.kind === 'open').flatMap((s) => of(s.stage));
  return {
    company: c, stages: STAGES.map((s) => ({ stage: s.stage, title_fa: s.title_fa, kind: s.kind, count: of(s.stage).length, value_usdt: d2(sum(of(s.stage))), median_days: s.median })),
    total: mine.length, open_count: open.length, won_count: won, lost_count: lost, open_value_usdt: d2(sum(open)), win_rate: won + lost ? Math.round((won / (won + lost)) * 10_000) / 10_000 : null,
  };
};
const ACTOR_KEYS = ['kind', 'code', 'display_fa'];
const LEAD_IN = ['name_fa', 'contact', 'source', 'value_usdt', 'next_at', 'next_fa', 'note_fa', 'assignee'];
const LEAD_PATCH = ['stage', 'lost_reason_fa', 'name_fa', 'value_usdt', 'next_at', 'next_fa', 'note_fa', 'assignee'];
const money = (v: unknown) => (v == null ? null : d2(Number(v)));
const gaps = [
  { account: 'exchange-a/main', company: 'TY', exchange: 'exchange-a', month: `${monthsBack(1)}-01`, due_usdt: '412.50', received_usdt: '371.20', gap_usdt: '41.30', gap_pct: 10.01, settles_on: `${monthsBack(0)}-10`, state: 'open', draft_fa: 'سلام، کمیسیون ماه گذشته‌ی حساب اصلی 41 دلار کم‌تر از محاسبه‌ی ما رسیده. لطفاً گزارش تسویه را بفرستید.', work_ref: 'W-000420' },
  { account: 'exchange-b/main', company: 'FX', exchange: 'exchange-b', month: `${monthsBack(1)}-01`, due_usdt: '188.00', received_usdt: '120.00', gap_usdt: '68.00', gap_pct: 36.17, settles_on: addDays(today(), 6), state: 'waiting', draft_fa: null, work_ref: null },
  { account: 'exchange-a/main', company: 'TY', exchange: 'exchange-a', month: `${monthsBack(2)}-01`, due_usdt: '390.00', received_usdt: '390.00', gap_usdt: '0.00', gap_pct: 0, settles_on: `${monthsBack(1)}-10`, state: 'closed', draft_fa: null, work_ref: null },
];

// ================================================================================================= journey ==
const J_STAGES = [['founded', 'تأسیس'], ['server_ready', 'سرور آماده'], ['first_content', 'اولین محتوا'], ['first_visitor', 'اولین بازدیدکننده'], ['first_lead', 'اولین سرنخ'], ['first_payment', 'اولین پرداخت'], ['ten_paying', 'ده مشتری پرداخت‌کننده'], ['break_even', 'سربه‌سر']] as const;
const EVIDENCE = [{ kind: 'company', ref: null }, { kind: 'server', ref: 'SRV-0003' }, { kind: 'deliverable', ref: 'DL-000012' }, { kind: 'analytics', ref: null }, { kind: 'lead', ref: 'LD-000001' }, { kind: 'payment', ref: null }, { kind: 'revenue', ref: null }, { kind: 'revenue', ref: null }];
const REACHED: Record<string, number> = { TY: 6, FX: 5, PC: 4 };
const journey = (c: string) => {
  const n = REACHED[c] ?? 1;
  return {
    company: c, stages: J_STAGES.map(([key, title_fa], i) => ({ key, title_fa, reached_at: i < n ? ago((n - i) * 14) : null, evidence: i < n ? EVIDENCE[i] : null })),
    // The latest stage reached (the first stage when none is).
    current: J_STAGES[Math.max(0, n - 1)]![0], next_fa: n >= 8 ? null : 'برای ده مشتری پرداخت‌کننده، پیگیری سرنخ‌های مرحله‌ی آزمایشی را هر روز انجام بده.', days_in_stage: 14,
  };
};
const journeyBoard = () => {
  const js = ['TY', 'FX', 'PC'].map(journey);
  const timeline = js.flatMap((j) => j.stages.filter((s) => s.reached_at).map((s) => ({ at: s.reached_at!, company: j.company, stage: s.key, title_fa: s.title_fa }))).sort((a, b) => b.at.localeCompare(a.at));
  return { journeys: js, timeline };
};

// ================================================================================================= personas ==
const PERSONA_IN = ['name_fa', 'summary_fa', 'pains_fa', 'objections_fa', 'channel_fa', 'source'];
const PERSONA_PATCH = ['name_fa', 'summary_fa', 'pains_fa', 'objections_fa', 'channel_fa'];
const personas: any[] = [
  { id: uuid(0x9e5, 1), company: 'TY', name_fa: 'معامله‌گر تازه‌کار', summary_fa: 'تازه وارد بازار شده، از ضرر میترسد و دنبال قاعده‌ی ساده است.', pains_fa: ['نمیداند حد ضرر کجا بگذارد', 'از سیگنال‌های بی‌دلیل خسته است'], objections_fa: ['اشتراک ماهانه گران است', 'به کانال‌های تلگرام اعتماد ندارد'], channel_fa: 'اینستاگرام و تلگرام', source: 'owner', version: 1 },
  { id: uuid(0x9e5, 2), company: 'TY', name_fa: 'معامله‌گر باتجربه', summary_fa: 'چند سال معامله کرده و دنبال ابزار مدیریت ریسک است.', pains_fa: ['حسابداری معاملات وقتش را میگیرد'], objections_fa: ['ابزار خودش را دارد'], channel_fa: 'سایت و ایمیل', source: 'owner', version: 1 },
  { id: uuid(0x9e5, 3), company: 'FX', name_fa: 'سرمایه‌گذار محتاط', summary_fa: 'پول کمی دارد و دنبال سود پایدار است.', pains_fa: ['ترس از نوسان'], objections_fa: ['ریسک را زیاد میبیند'], channel_fa: 'تلگرام', source: 'owner', version: 1 },
];
let nPr = 4;
const IDEAS = [
  { name_fa: 'دانشجوی علاقه‌مند به بازار', summary_fa: 'وقت دارد ولی سرمایه ندارد؛ دنبال آموزش رایگان است.', pains_fa: ['پول کافی برای شروع ندارد'], objections_fa: ['فقط محتوای رایگان میخواهد'], channel_fa: 'یوتیوب' },
  { name_fa: 'کارمندی که کنار کار معامله میکند', summary_fa: 'فقط شب‌ها وقت دارد و نمیتواند بازار را دنبال کند.', pains_fa: ['نمیتواند همیشه پای نمودار باشد'], objections_fa: ['به ربات و سیگنال خودکار شک دارد'], channel_fa: 'تلگرام' },
];

// ================================================================================================== impact ==
const IMPACT: Record<string, unknown> = {
  'D-000087': { revenue_usdt: 1200, cost_usd: 12, horizon_days: 30, basis_fa: 'بازدید و تبدیل سه استوری مشابه تریدیار در ۱۴ روز اخیر.', kind: 'measured' },
  'D-000035': { revenue_usdt: 900, cost_usd: 12, horizon_days: 60, basis_fa: 'کاهش ریزش بعد از ثبت شناسه در سه ماه گذشته.', kind: 'estimate' },
  'D-000085': { revenue_usdt: 300, cost_usd: 60, horizon_days: 60, basis_fa: 'پاسخ مثبت احتمالی به ایمیل‌های مشابه.', kind: 'estimate' },
  'D-000017': { revenue_usdt: null, cost_usd: -150, horizon_days: 30, basis_fa: 'کم شدن خرابی‌های ترمینال در سی روز اخیر.', kind: 'measured' },
};
/** `domain/impact.py` `score`: the size of an impact per 30 days. */
const impactScore = (i: any) => ((Math.abs(i.revenue_usdt ?? 0) + Math.abs(i.cost_usd ?? 0)) * 30) / Math.max(i.horizon_days || 1, 1);

// ========================================================================================== order reports ==
const WORK_IDS: Record<string, string> = { 'W-000300': uuid(0x30c, 300), 'W-000310': uuid(0x30c, 310) };
const part = (n: number, ref: string, title_fa: string, role: string, who_fa: string, state: 'working' | 'delivered' | 'failed', extra: Record<string, unknown> = {}) => ({
  n, ref, title_fa, role, assignee: `TY-${role.toUpperCase()}-01`, who_fa, status: state === 'delivered' ? 'done' : state === 'failed' ? 'failed' : 'in_progress', state,
  progress_pct: null, output_ref: null, output_title_fa: null, failed_fa: null, tokens_used: 0, budget_tokens: 120_000, ...extra,
});
const orderReport = (ref: string, text_fa: string, extra: Record<string, unknown>) => ({
  ref, text_fa, at: ago(1, '08:00'), state: 'in_progress', ack: { at: ago(1, '08:05'), by: { kind: 'agent', code: 'TY-CEO', display_fa: 'مدیرعامل تریدیار' }, plan_fa: 'کار به چند بخش مستقل بخش شد و همزمان پیش میرود.', assigned: [{ company: 'TY', code: 'TY-CEO', title_fa: 'مدیرعامل تریدیار' }], due_at: null },
  route: null, steps: [{ at: ago(1, '08:10'), who_fa: 'مدیرعامل تریدیار', what_fa: 'کار را به بخش‌های مستقل تقسیم کرد.' }], outputs: [], blockers: [], summary: null, kit: null, updated_at: ago(0, '07:00'), parts: [], workspaces: [], ...extra,
});
const ORDERS: Record<string, any> = {
  'F-0097': orderReport('F-0097', 'بسته‌ی محتوای هفته‌ی آموزش حد ضرر را بساز', {
    state: 'delivered', summary: { done_fa: 'دو بخش از سه بخش آماده شد و جمع‌بندی نوشته شد.', left_fa: 'بخش ریلز تمام نشد.', need_fa: 'تصمیم بگیر ریلز دوباره ساخته شود یا نه.' },
    outputs: [{ kind: 'final', ref: 'DL-000103', title_fa: 'جمع‌بندی بسته‌ی حد ضرر' }, { kind: 'part', ref: 'DL-000101', title_fa: 'مقاله‌ی حد ضرر' }, { kind: 'part', ref: 'DL-000102', title_fa: 'پست‌های تلگرام' }],
    parts: [{
      work_ref: 'W-000300', state: 'done', proposed_by: 'TY-CEO', merge_queued_at: ago(0, '06:00'), created_at: ago(1, '08:10'),
      parts: [
        part(1, 'W-000301', 'متن مقاله', 'writer', 'نویسنده‌ی سایت', 'delivered', { output_ref: 'DL-000101', output_title_fa: 'مقاله‌ی حد ضرر', tokens_used: 84_000 }),
        part(2, 'W-000302', 'پست تلگرام', 'publisher', 'مدیر کانال', 'delivered', { output_ref: 'DL-000102', output_title_fa: 'پست‌های تلگرام', tokens_used: 31_000 }),
        part(3, 'W-000303', 'ریلز آموزشی', 'motion_designer', 'ویرایشگر ویدیو', 'failed', { failed_fa: 'صدای فارسی ساخته نشد؛ موتور صدا کلید نداشت.', tokens_used: 12_000 }),
      ],
    }],
  }),
  'F-0096': orderReport('F-0096', 'تحلیل سئوی سایت را روی سرور خودش انجام بده', {
    parts: [{
      work_ref: 'W-000310', state: 'running', proposed_by: 'TY-CEO', merge_queued_at: null, created_at: ago(1, '08:10'),
      parts: [
        part(1, 'W-000311', 'جمع‌آوری صفحه‌ها', 'analyst', 'تحلیلگر سئو', 'delivered', { output_ref: 'DL-000111', output_title_fa: 'فهرست ۲۴۰ صفحه', tokens_used: 22_000 }),
        part(2, 'W-000312', 'بررسی سرعت', 'cto', 'مهندس وب', 'working', { progress_pct: 60, tokens_used: 40_000 }),
        part(3, 'W-000313', 'پیشنهاد محتوا', 'content_lead', 'مدیر محتوا', 'working'),
      ],
    }],
    workspaces: [{
      work_ref: 'W-000310', server: 'ty-app', where_fa: 'سرور تریدیار', path: '~/hq-workspace/W-000310', state: 'working', turns: 4, session_ref: 'CS-0042',
      last_step_fa: 'فایل‌های سایت را خواند و گزارش سرعت را مینویسد.', note_fa: null, updated_at: ago(0, '07:00'), closed_at: null, remove_after: null,
    }],
  }),
};
const splitOf = (id: string) => Object.values(ORDERS).flatMap((o) => o.parts).find((s: any) => WORK_IDS[s.work_ref] === id) ?? null;

// ================================================================================================= handler ==
export async function handle33(req: Request, p: string, q: URLSearchParams, next: () => Promise<Response>): Promise<Response | null> {
  if (!/^\/(usage\/|payment-sources|personas\/|companies\/[^/]+\/(payment-sources|payments|reconcile|leads|pipeline|journey|personas)|revenue\/(board|affiliate-gaps|summary)|leads\/|journeys$|decisions|orders\/F-009[67]\/report|auth\/step-up\/options$|work$|work\/[^/]+\/(split|stop)$)/.test(p)) return null;
  const m = req.method;
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;

  // The step-up the panel asks for is recorded (its target is checked where a route binds it to the body); the base answers it.
  if (p === '/auth/step-up/options' && m === 'POST') { lastStepUp = await body<{ action: string; target: string }>(); return null; }

  // ----------------------------------------------------------------------------------------------- usage --
  if (p === '/usage/reports' && m === 'GET') { const per = q.get('period'); return json({ items: reports.filter((r) => !per || r.period === per).slice(0, Number(q.get('limit') ?? 20)), next_cursor: null }); }
  if (p === '/usage/reports' && m === 'POST') {
    const b = await body<{ period: 'day' | 'week' }>();
    const bad = extra(b, ['period']); if (bad) return bad;
    if (b.period !== 'day' && b.period !== 'week') return problem(422, 'validation_failed', 'دوره روزانه یا هفتگی است.');
    const r = { ref: `UR-${String(nUr++).padStart(4, '0')}`, period: b.period, pack: pack(b.period, 0), words: 'model', text: { lines_fa: ['گزارش تازه نوشته شد؛ مصرف امروز عادی است.', 'کار فرمان‌ها بیشترین سهم را دارد.', 'چیز غیرعادی دیده نشد.'], saving_fa: 'فعلاً صرفه‌جویی تازه‌ای پیدا نشد؛ مصرف صدا را زیر نظر نگه دارید.' }, at: nowIso() };
    reports.unshift(r);
    return json(r, 201);
  }

  // ------------------------------------------------------------------------------------------- payments --
  const ps = /^\/companies\/([^/]+)\/payment-sources$/.exec(p);
  if (ps && m === 'GET') return json(sources.filter((s) => s.company === ps[1]));
  if (ps && m === 'POST') {
    const raw = await req.clone().text();
    const b = JSON.parse(raw || '{}') as Record<string, any>;
    if (!req.headers.get('X-Step-Up')) return problem(403, 'step_up_required', 'این کار تأیید با اثر انگشت یا چهره میخواهد.');
    if (lastStepUp?.action !== 'payment.source' || lastStepUp.target !== (await sha256(raw))) return problem(403, 'step_up_invalid', 'تأیید برای همین تغییر نبود؛ دوباره ذخیره کن.');
    lastStepUp = null;
    const bad = extra(b, ['kind', 'network', 'address', 'server', 'enabled']); if (bad) return bad;
    const enabled = b.enabled ?? true;
    if (b.kind === 'ledger') {
      if (b.network != null || b.address != null) return problem(422, 'validation_failed', 'دفتر شرکت نشانی کیف پول ندارد.', { address: 'not for a ledger source' });
      const s = sources.find((x) => x.company === ps[1] && x.kind === 'ledger');
      if (s) { Object.assign(s, { server: b.server ?? null, enabled }); return json(s, 201); }
      const n = src(nSrc++, { company: ps[1], kind: 'ledger', adapter: 'ledger_v1', server: b.server ?? null, enabled, state: 'not_configured' });
      sources.push(n);
      return json(n, 201);
    }
    if (b.kind !== 'chain') return problem(422, 'validation_failed', 'نوع منبع درست نیست.', { kind: 'ledger or chain' });
    if (!b.network || !b.address) return problem(422, 'validation_failed', 'شبکه و نشانی لازم است.', { network: 'required', address: 'required' });
    if (b.server != null) return problem(422, 'validation_failed', 'کیف پول سرور ندارد.', { server: 'not for a chain source' });
    if (!(b.network === 'bsc_usdt' ? BSC_RE : TRON_RE).test(b.address)) return problem(422, 'validation_failed', 'نشانی کیف پول برای این شبکه درست نیست.', { address: 'not an address of this network' });
    const address = b.network === 'bsc_usdt' ? String(b.address).toLowerCase() : b.address;
    const s = sources.find((x) => x.company === ps[1] && x.kind === 'chain' && x.network === b.network && x.address === address);
    if (s) { s.enabled = enabled; return json(s, 201); }
    const n = src(nSrc++, { company: ps[1], kind: 'chain', network: b.network, address, enabled });
    sources.push(n);
    return json(n, 201);
  }
  const rd = /^\/payment-sources\/([^/]+)\/read$/.exec(p);
  if (rd && m === 'POST') {
    if (!UUID_RE.test(rd[1]!)) return problem(422, 'validation_failed', 'شناسه‌ی منبع درست نیست.', { id: 'uuid' });
    if (!req.headers.get('Idempotency-Key')) return problem(422, 'validation_failed', 'کلید یکتایی درخواست لازم است.', { 'Idempotency-Key': 'required' });
    const s = sources.find((x) => x.id === rd[1]);
    if (!s) return problem(404, 'not_found', 'این منبع پیدا نشد.');
    if (s.kind === 'ledger') return json({ source: s, queued: true, payments: 0, transfers: 0, pages: 0 });
    if (s.network === 'trc20_usdt') return problem(502, 'connector_failed', 'شبکه‌ی ترون جواب نداد؛ کمی بعد دوباره بخوان.');
    s.last_read_at = nowIso(); s.state = 'ok'; s.last_error_fa = null;
    return json({ source: s, queued: false, payments: 0, transfers: 2, pages: 1 });
  }
  const pm = /^\/companies\/([^/]+)\/payments$/.exec(p);
  if (pm && m === 'GET') {
    const st = q.get('status'), from = q.get('from') ?? '0000', to = q.get('to') ?? '9999';
    return json({ items: payRows(pm[1]!).filter((x) => (!st || x.status === st) && String(x.paid_at).slice(0, 10) >= from && String(x.paid_at).slice(0, 10) <= to).slice(0, Number(q.get('limit') ?? 50)), next_cursor: null });
  }
  const rc = /^\/companies\/([^/]+)\/reconcile$/.exec(p);
  if (rc && m === 'GET') { const from = q.get('from') ?? '0000', to = q.get('to') ?? '9999'; return json(reconcile(rc[1]!).filter((d) => d.day >= from && d.day <= to)); }

  // ----------------------------------------------------------------------------------------------- revenue --
  if (p === '/revenue/board' && m === 'GET') return json(board(q.get('company')));
  if (p === '/revenue/summary' && m === 'GET') {
    const r = await next();
    if (!r.ok) return r;
    const s = (await r.clone().json().catch(() => null)) as Record<string, unknown> | null;
    return s ? json({ ...s, by_source: bySource(q.get('company')) }) : r;
  }
  if (p === '/revenue/affiliate-gaps' && m === 'GET') { const c = q.get('company'), st = q.get('state'); return json(gaps.filter((g) => (!c || g.company === c) && (!st || g.state === st))); }

  // -------------------------------------------------------------------------------------------------- crm --
  const ld = /^\/companies\/([^/]+)\/leads$/.exec(p);
  if (ld && m === 'GET') { const st = q.get('stage'); return json({ items: leads.filter((l) => l.company === ld[1] && (!st || l.stage === st)).slice(0, Number(q.get('limit') ?? 50)), next_cursor: null }); }
  if (ld && m === 'POST') {
    const b = await body<Record<string, any>>();
    const bad = extra(b, LEAD_IN) ?? (b.assignee ? extra(b.assignee, ACTOR_KEYS) : null); if (bad) return bad;
    if (b.contact != null && !/^[A-Za-z0-9_:.-]{8,128}$/.test(b.contact)) return problem(422, 'validation_failed', 'شناسه درست نیست؛ شماره یا نشانی تماس پذیرفته نمیشود.', { contact: 'pseudonym' });
    if (b.source != null && !['site', 'referral', 'manual', 'support', 'telegram'].includes(b.source)) return problem(422, 'validation_failed', 'منبع سرنخ درست نیست.', { source: 'enum' });
    const contact = b.contact ?? `cu_auto${String(nLd).padStart(4, '0')}`;
    const same = leads.find((l) => l.company === ld[1] && l.contact === contact);
    if (same) return json(same, 201);
    const at = nowIso();
    const l = lead(nLd++, { company: ld[1], source: b.source ?? 'manual', name_fa: b.name_fa ?? null, contact, stage: 'new', value_usdt: money(b.value_usdt), next_at: b.next_at ?? null, next_fa: b.next_fa ?? null, assignee: b.assignee ?? null,
      events: [{ at, kind: 'created', note_fa: b.note_fa || 'دستی ثبت شد.' }], created_at: at, updated_at: at });
    leads.push(l);
    return json(l, 201);
  }
  const pl = /^\/companies\/([^/]+)\/pipeline$/.exec(p);
  if (pl && m === 'GET') return json(pipeline(pl[1]!));
  const lo = /^\/leads\/([^/]+)$/.exec(p);
  if (lo && m === 'GET') { const l = leads.find((x) => x.ref === lo[1]); return l ? json(l) : problem(404, 'not_found', 'این سرنخ پیدا نشد.'); }
  if (lo && m === 'PATCH') {
    const im = req.headers.get('If-Match');
    if (im == null) return problem(428, 'precondition_required', 'نسخه‌ی سرنخ لازم است.', { 'If-Match': 'required (the current version)' });
    const l = leads.find((x) => x.ref === lo[1]);
    if (!l) return problem(404, 'not_found', 'این سرنخ پیدا نشد.');
    if (Number(im.replace(/^W\//, '').replaceAll('"', '')) !== l.version) return problem(409, 'version_conflict', 'این سرنخ عوض شده؛ دوباره باز کن.');
    const b = await body<Record<string, any>>();
    const bad = extra(b, LEAD_PATCH) ?? (b.assignee ? extra(b.assignee, ACTOR_KEYS) : null); if (bad) return bad;
    const at = nowIso();
    if (b.stage != null && b.stage !== l.stage) {
      const s = STAGES.find((x) => x.stage === b.stage);
      if (!s) return problem(422, 'validation_failed', 'این مرحله برای این شرکت نیست.', { stage: 'unknown' });
      l.stage = s.stage;
      l.lost_reason_fa = s.kind === 'lost' ? (b.lost_reason_fa ?? null) : null;
      l.events.push({ at, kind: 'stage', note_fa: `به «${s.title_fa}» رفت.` });
    } else if ('lost_reason_fa' in b) l.lost_reason_fa = b.lost_reason_fa;
    for (const k of ['name_fa', 'next_at', 'next_fa', 'assignee'] as const) if (k in b && !(k === 'name_fa' && b[k] == null)) l[k] = b[k];
    if ('value_usdt' in b) l.value_usdt = money(b.value_usdt);
    if (b.note_fa) l.events.push({ at, kind: 'note', note_fa: b.note_fa });
    l.version += 1; l.updated_at = at;
    return json(l);
  }
  const dr = /^\/leads\/([^/]+)\/draft$/.exec(p);
  if (dr && m === 'POST') {
    const l = leads.find((x) => x.ref === dr[1]);
    if (!l) return problem(404, 'not_found', 'این سرنخ پیدا نشد.');
    l.events.push({ at: nowIso(), kind: 'draft', note_fa: 'پیش‌نویس پیگیری نوشته شد (فرستاده نشد).' });
    return json({ lead: l.ref, draft_fa: `سلام ${l.name_fa ?? ''}، از تیم تریدیار می‌نویسیم. دیدیم به پلن ماهانه علاقه نشان دادید؛ اگر سؤالی درباره‌ی حد ضرر یا پرداخت دارید همین‌جا بپرسید تا کمک کنیم.`.replace('  ', ' '), guard_ok: true, blocked_reasons: [], sent: false });
  }

  // ----------------------------------------------------------------------------------------------- journey --
  const jo = /^\/companies\/([^/]+)\/journey$/.exec(p);
  if (jo && m === 'GET') return json(journey(jo[1]!));
  if (p === '/journeys' && m === 'GET') return json(journeyBoard());

  // ---------------------------------------------------------------------------------------------- personas --
  const pr = /^\/companies\/([^/]+)\/personas(?:\/([^/]+))?$/.exec(p);
  if (pr && !pr[2] && m === 'GET') return json(personas.filter((x) => x.company === pr[1]));
  if (pr && !pr[2] && m === 'POST') {
    const b = await body<Record<string, any>>();
    const bad = extra(b, PERSONA_IN); if (bad) return bad;
    if (!b.name_fa?.trim() || !b.summary_fa?.trim()) return problem(422, 'validation_failed', 'نام و خلاصه لازم است.');
    if ((b.pains_fa ?? []).length > 8 || (b.objections_fa ?? []).length > 8) return problem(422, 'validation_failed', 'حداکثر ۸ مورد.');
    if (personas.filter((x) => x.company === pr[1]).length >= 8) return problem(422, 'validation_failed', 'هر شرکت حداکثر ۸ مخاطب دارد.');
    const x = { id: uuid(0x9e5, nPr++), company: pr[1], name_fa: b.name_fa, summary_fa: b.summary_fa, pains_fa: b.pains_fa ?? [], objections_fa: b.objections_fa ?? [], channel_fa: b.channel_fa ?? '', source: b.source ?? 'owner', version: 1 };
    personas.push(x);
    return json(x, 201);
  }
  if (pr && pr[2] === 'suggest' && m === 'POST') {
    const have = new Set(personas.filter((x) => x.company === pr[1]).map((x) => x.name_fa));
    return json({ company: pr[1], basis_fa: 'از سه مقاله‌ی دانشنامه و پرسش‌های پرتکرار پشتیبانی.', personas: IDEAS.filter((x) => !have.has(x.name_fa)) });
  }
  if (pr && pr[2] === 'test' && m === 'POST') {
    const b = await body<{ text: string }>();
    const bad = extra(b, ['text']); if (bad) return bad;
    if (!b.text?.trim()) return problem(422, 'validation_failed', 'متن پیام لازم است.');
    const mine = personas.filter((x) => x.company === pr[1]);
    if (!mine.length) return problem(422, 'validation_failed', 'این شرکت هنوز مخاطبی ندارد.');
    const results = mine.map((x, i) => {
      const score = 35 + ((b.text.length * (i + 3)) % 60);
      return { persona: x.id, name_fa: x.name_fa, score, would_act: score >= 60, objection_fa: score >= 60 ? null : (x.objections_fa[0] ?? null), fix_fa: score >= 60 ? null : 'قیمت را کنار یک نمونه‌ی ملموس از صرفه‌جویی بگذار.' };
    });
    return json({ id: uuid(0x7e57, results.length + b.text.length), text: b.text, at: nowIso(), average: Math.round(results.reduce((a, r) => a + r.score, 0) / results.length), lowest: Math.min(...results.map((r) => r.score)), results });
  }
  const one = /^\/personas\/([^/]+)$/.exec(p); // PATCH and DELETE /personas/{id} (contract §33.9)
  if (one && (m === 'PATCH' || m === 'DELETE')) {
    if (!UUID_RE.test(one[1]!)) return problem(422, 'validation_failed', 'شناسه‌ی مخاطب درست نیست.', { pid: 'uuid' });
    const i = personas.findIndex((x) => x.id === one[1]);
    if (i < 0) return problem(404, 'not_found', 'این مخاطب پیدا نشد.');
    if (m === 'DELETE') { personas.splice(i, 1); return json(null, 204); }
    const b = await body<Record<string, any>>();
    const bad = extra(b, PERSONA_PATCH); if (bad) return bad;
    const set = Object.fromEntries(Object.entries(b).filter(([, v]) => v != null));
    if (!Object.keys(set).length) return problem(422, 'validation_failed', 'چیزی برای تغییر نیست.');
    personas[i] = { ...personas[i], ...set, source: 'owner', version: personas[i].version + 1 };
    return json(personas[i]);
  }

  // ---------------------------------------------------------------------------------------------- impact --
  if (p === '/decisions' && m === 'GET') {
    const r = await next();
    if (!r.ok) return r;
    const s = (await r.clone().json().catch(() => null)) as { items?: Array<{ ref: string; created_at?: string }> } | null;
    if (!s?.items) return r;
    const items = s.items.map((d) => (IMPACT[d.ref] ? { ...d, impact: IMPACT[d.ref] } : d)) as Array<{ ref: string; created_at?: string; impact?: unknown }>;
    // `?sort=impact`: the largest impact per 30 days first, the cards without one last, then oldest.
    if (q.get('sort') === 'impact') items.sort((a, b) => (b.impact ? impactScore(b.impact) : -1) - (a.impact ? impactScore(a.impact) : -1) || String(a.created_at).localeCompare(String(b.created_at)));
    return json({ ...s, items });
  }
  const dd = /^\/decisions\/(D-\d+)$/.exec(p);
  if (dd && m === 'GET') {
    const r = await next();
    if (!r.ok || !IMPACT[dd[1]!]) return r;
    const s = (await r.clone().json().catch(() => null)) as Record<string, unknown> | null;
    return s ? json({ ...s, impact: IMPACT[dd[1]!] }) : r;
  }

  // ----------------------------------------------------------------------------------------- order reports --
  const or = /^\/orders\/(F-009[67])\/report$/.exec(p);
  if (or && m === 'GET') return json(ORDERS[or[1]!]);
  // A work named by ref is found through the list's search (as the panel resolves a ref to the work's UUID).
  if (p === '/work' && m === 'GET') {
    const ref = q.get('q') ?? '';
    return WORK_IDS[ref] ? json({ items: [{ id: WORK_IDS[ref], ref, company: 'TY', title: ref, status: 'in_progress' }], next_cursor: null }) : null;
  }
  const sp = /^\/work\/([^/]+)\/split$/.exec(p);
  if (sp && m === 'GET') { const s = splitOf(sp[1]!); return s ? json(s) : problem(404, 'not_found', 'این کار بخش موازی ندارد.'); }
  const stop = /^\/work\/([^/]+)\/stop$/.exec(p);
  if (stop && m === 'POST') {
    if (!UUID_RE.test(stop[1]!)) return problem(422, 'validation_failed', 'شناسه‌ی کار درست نیست.', { id: 'uuid' });
    const ref = Object.keys(WORK_IDS).find((k) => WORK_IDS[k] === stop[1]);
    if (!ref) return problem(404, 'not_found', 'این کار پیدا نشد.');
    const w = Object.values(ORDERS).flatMap((o) => o.workspaces).find((x: any) => x.work_ref === ref);
    if (w) { w.state = 'stopped'; w.updated_at = nowIso(); w.last_step_fa = 'تو کار روی سرور را متوقف کردی.'; }
    return json({ work_ref: ref, workspace: w ? 'stopped' : null, jobs_stopped: w ? 1 : 0 });
  }
  return null;
}
