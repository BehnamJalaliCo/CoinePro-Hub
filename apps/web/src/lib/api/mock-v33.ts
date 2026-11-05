// Development-only fixtures (npm run dev:mock) for contract §33 ⟨1.15⟩: the advisor's usage reports, payment sources with a payment list that
// agrees and disagrees (matched, ledger only, chain only, a lower amount, waiting for the chain) and a daily reconcile, a revenue board with a
// forecast band, cohorts and ROI, a small CRM (pipeline, leads, a follow-up draft), affiliate gaps, a money impact on some decisions, two order
// reports (a split work with a failed part; a work on the company's own server), each company's journey and personas with a message test.
// Everything is computed from fixed numbers and the day's date, never at random. Kept in memory so the end-to-end checks can add, edit and
// read. No wallet address, key or schema of any company is here: the addresses are placeholders. Never bundled in production (reached only
// through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

const json = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const needStepUp = () => problem(403, 'step_up_required', 'این کار تأیید با اثر انگشت یا چهره میخواهد.');
const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (d: string, n: number) => iso(new Date(Date.parse(`${d}T12:00:00Z`) + n * 86_400_000));
const today = () => iso(new Date());
const ago = (days: number, hm = '09:30') => `${addDays(today(), -days)}T${hm}:00Z`;
const code = (c: string) => [...c].reduce((a, ch) => a + ch.charCodeAt(0), 0);
const scale = (c: string) => ({ TY: 1, FX: 1.6, PC: 0.7 } as Record<string, number>)[c] ?? [1, 1.6, 0.7][code(c) % 3]!;
const monthsBack = (n: number) => { const d = new Date(); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() - n); return d.toISOString().slice(0, 7); };
const monthsAhead = (n: number) => monthsBack(-n);

// ================================================================================================== usage ==
const pack = (period: 'day' | 'week', k: number) => ({
  period, from: addDays(today(), period === 'day' ? -1 - k : -7 - k * 7), to: addDays(today(), period === 'day' ? -1 - k : -1 - k * 7),
  by_domain: [{ domain: 'content', tokens: 1_820_000, usd_equiv: 14.2, share: 0.46 }, { domain: 'growth', tokens: 940_000, usd_equiv: 7.4, share: 0.24 }, { domain: 'support', tokens: 610_000, usd_equiv: 4.8, share: 0.15 }, { domain: 'voice', tokens: 0, usd_equiv: 4.6, share: 0.15 }],
  by_company: [{ company: 'TY', tokens: 2_100_000, usd_equiv: 17.3, share: 0.56 }, { company: 'FX', tokens: 900_000, usd_equiv: 8.1, share: 0.26 }, { company: 'PC', tokens: 470_000, usd_equiv: 5.6, share: 0.18 }],
  top_runs: [{ ref: 'LR-0412', role: 'تحلیلگر سئو', tokens: 410_000 }, { ref: 'LR-0408', role: 'نویسنده‌ی ریلز', tokens: 330_000 }],
  voice_usd: 4.6, lines: { runs: 38, tokens: 1_250_000 }, ads_spend_usd: 220, vs_prev: { tokens_pct: 12.4, usd_pct: 9.8 },
  anomalies: k === 0 ? [{ kind: 'spike', note: 'مصرف تحلیل سئوی تریدیار سه‌شنبه ۲ برابر روز عادی بود.' }] : [],
});
const reports: any[] = [
  { ref: 'UR-0004', period: 'day', ...{ pack: pack('day', 0) }, text: { lines_fa: ['دیروز حدود 31 دلار مصرف شد؛ 10٪ بیشتر از روز قبل.', 'بیشترین سهم با تولید محتوا بود: 46٪.', 'تحلیل سئوی تریدیار 410 هزار توکن برد و از همه گران‌تر بود.'], saving_fa: 'تحلیل سئو را به یک بار در هفته ببرید؛ حدود 6 دلار در روز صرفه‌جویی میشود.' }, at: ago(0, '04:25') },
  { ref: 'UR-0003', period: 'week', pack: pack('week', 0), text: { lines_fa: ['هفته‌ی گذشته 188 دلار مصرف شد؛ 12٪ بیشتر از هفته‌ی قبل.', 'تولید محتوا نیمی از مصرف را برد و بیشتر آن برای تریدیار بود.', 'صدا 4.6 دلار شد و تبلیغات 220 دلار.', 'سه‌شنبه یک جهش مصرف در تحلیل سئو دیده شد.'], saving_fa: 'اجرای شبانه‌ی تحلیل سئو را به هفتگی ببرید؛ ماهانه حدود 40 دلار کم میشود.' }, at: ago(3, '05:30') },
  { ref: 'UR-0002', period: 'day', pack: pack('day', 1), text: { lines_fa: ['پریروز 28 دلار مصرف شد.', 'تولید محتوا بیشترین سهم را داشت.', 'چیز غیرعادی نبود.'], saving_fa: 'کار خاصی لازم نیست؛ فقط مصرف صدا را زیر نظر نگه دارید.' }, at: ago(1, '04:25') },
  { ref: 'UR-0001', period: 'week', pack: pack('week', 1), text: { lines_fa: ['دو هفته پیش 168 دلار مصرف شد.', 'بیشترین سهم با پشتیبانی تلگرام بود.', 'تبلیغات 180 دلار بود.'], saving_fa: 'پاسخ‌های تکراری پشتیبانی را از دانشنامه بدهید تا توکن کم‌تر برود.' }, at: ago(10, '05:30') },
];
let nUr = 5;

// ================================================================================================ payments ==
const sources: any[] = [
  { id: 'PS-TY-1', company: 'TY', kind: 'chain', adapter: 'bsc-usdt', network: 'bsc_usdt', address: 'demo-bsc-address-0001', state: 'ok', last_read_at: ago(0, '06:10'), last_error_fa: null },
  { id: 'PS-TY-2', company: 'TY', kind: 'chain', adapter: 'tron-usdt', network: 'trc20_usdt', address: 'demo-tron-address-0002', state: 'error', last_read_at: ago(1, '06:10'), last_error_fa: 'شبکه‌ی ترون جواب نداد؛ ساعتی دیگر دوباره امتحان میشود.' },
  { id: 'PS-TY-3', company: 'TY', kind: 'ledger', adapter: 'ledger-v1', network: null, address: null, state: 'ok', last_read_at: ago(0, '06:05'), last_error_fa: null },
  { id: 'PS-FX-1', company: 'FX', kind: 'ledger', adapter: 'ledger-v1', network: null, address: null, state: 'not_configured', last_read_at: null, last_error_fa: null },
];
let nSrc = 4;
const pay = (i: number, o: Record<string, unknown>): any => ({ id: `PM-${String(i).padStart(4, '0')}`, source: 'PS-TY-1', plan: 'پلن ماهانه', network: 'bsc_usdt', period_start: null, period_end: null, checked_at: ago(0, '06:20'), ...o });
const payRows = (c: string) => [
  pay(1, { company: c, ext_id: 'EX-1001', customer: 'cu_8f2a1c', amount_usdt: 49, tx_hash: '0xdemo0001aaaa1111bbbb2222cccc3333', paid_at: ago(1), status: 'matched' }),
  pay(2, { company: c, ext_id: 'EX-1002', customer: 'cu_19be77', amount_usdt: 49, tx_hash: '0xdemo0002aaaa1111bbbb2222cccc3333', paid_at: ago(2), status: 'matched' }),
  pay(3, { company: c, ext_id: 'EX-1003', customer: 'cu_c04d90', plan: 'پلن سالانه', amount_usdt: 390, network: 'trc20_usdt', tx_hash: 'demo0003aaaa1111bbbb2222cccc3333', paid_at: ago(4), status: 'ledger_only' }),
  pay(4, { company: c, ext_id: 'chain-7781', customer: 'cu_unknown1', plan: null, amount_usdt: 49, tx_hash: '0xdemo0004aaaa1111bbbb2222cccc3333', paid_at: ago(5), status: 'chain_only' }),
  pay(5, { company: c, ext_id: 'EX-1005', customer: 'cu_5d1e02', amount_usdt: 35, tx_hash: '0xdemo0005aaaa1111bbbb2222cccc3333', paid_at: ago(7), status: 'amount_mismatch' }),
  pay(6, { company: c, ext_id: 'EX-1006', customer: 'cu_a7733b', amount_usdt: 49, tx_hash: '0xdemo0006aaaa1111bbbb2222cccc3333', paid_at: ago(0, '05:00'), status: 'pending_chain' }),
  pay(7, { company: c, ext_id: 'EX-1007', customer: 'cu_store01', plan: 'اشتراک اپ‌استور', amount_usdt: null, network: null, tx_hash: null, paid_at: ago(3), status: 'matched' }),
];
const reconcile = (c: string) => Array.from({ length: 14 }, (_, i) => {
  const day = addDays(today(), -i);
  const lo = i === 4 ? 1 : 0, co = i === 5 ? 1 : 0, mm = i === 7 ? 1 : 0, m = 2 + (i % 3);
  return { company: c, day, ledger_count: m + lo + mm, chain_count: m + co + mm, matched: m, ledger_only: lo, chain_only: co, amount_mismatch: mm,
    note_fa: lo ? 'یک پرداخت تأییدشده روی زنجیره پیدا نشد.' : co ? 'یک واریز بدون مشتری رسیده.' : mm ? 'یک مبلغ از قیمت طرح کم‌تر بود.' : null };
});

// ============================================================================================ revenue board ==
const board = (c: string | null) => {
  const f = c ? scale(c) : 3.3;
  const mrr = [520, 740, 910, 1180, 1390, 1640, 1820, 2050].map((v) => Math.round(v * f));
  const months = mrr.map((v, i) => ({ month: monthsBack(7 - i), mrr_usdt: v, new_customers: Math.round((6 + i) * f), churned: Math.round((1 + (i % 3)) * f), active: Math.round((10 + i * 7) * f), arpu_usdt: Math.round((v / ((10 + i * 7) * f)) * 10) / 10 }));
  const fc = [2230, 2410, 2590].map((v, i) => ({ month: monthsAhead(i + 1), mrr_usdt: Math.round(v * f), low: Math.round((v - 120 - i * 60) * f), high: Math.round((v + 120 + i * 60) * f) }));
  return {
    company: c, period: 'month', months, churn_rate: 0.062, ltv_usdt: Math.round(790 * f) / f, cac_usdt: 18.4, payback_months: 1.6,
    cohorts: [0, 1, 2, 3, 4].map((k) => ({ start_month: monthsBack(7 - k), size: Math.round((9 + k * 2) * f), retained: [100, 92, 86, 81, 77, 74].slice(0, 6 - k) })),
    forecast: fc, forecast_basis_fa: 'روند خطی هولت روی MRR هشت ماه گذشته، با بازه‌ی ±1.28 انحراف معیار باقیمانده‌ها.',
    roi: { revenue_usdt: Math.round(2050 * f), cost_usd: { tokens: Math.round(310 * f), voice: Math.round(46 * f), ads: Math.round(220 * f), servers: null }, ratio: 3.5 },
    cost_per_output: [{ kind: 'line_run', count: Math.round(38 * f), usd_each: 0.42 }, { kind: 'deliverable', count: Math.round(64 * f), usd_each: 0.31 }, { kind: 'order', count: Math.round(12 * f), usd_each: 1.85 }],
  };
};

// ===================================================================================================== sales ==
const leads: any[] = [
  { ref: 'LD-000001', company: 'TY', source: 'support', name_fa: 'علی ر.', contact: 'cu_8f2a1c', stage: 'new', value_usdt: 49, next_at: ago(-1), next_fa: 'پیام خوش‌آمد و معرفی پلن ماهانه', assignee: { kind: 'employee', code: 'TY-SALES-01', display_fa: 'کارشناس فروش تریدیار' }, lost_reason_fa: null, events: [{ at: ago(2), kind: 'created', note_fa: 'از پشتیبانی تلگرام ساخته شد.' }], created_at: ago(2), updated_at: ago(2) },
  { ref: 'LD-000002', company: 'TY', source: 'telegram', name_fa: 'سارا م.', contact: 'cu_19be77', stage: 'contacted', value_usdt: 49, next_at: ago(1), next_fa: 'پیگیری دوباره بعد از دو روز', assignee: null, lost_reason_fa: null, events: [{ at: ago(5), kind: 'created', note_fa: 'از ربات تلگرام آمد.' }, { at: ago(3), kind: 'stage', note_fa: 'به «تماس گرفته شد» رفت.' }], created_at: ago(5), updated_at: ago(3) },
  { ref: 'LD-000003', company: 'TY', source: 'payment', name_fa: null, contact: 'cu_unknown1', stage: 'qualified', value_usdt: 49, next_at: null, next_fa: null, assignee: null, lost_reason_fa: null, events: [{ at: ago(5), kind: 'created', note_fa: 'از یک واریز بدون مشتری ساخته شد.' }], created_at: ago(5), updated_at: ago(5) },
  { ref: 'LD-000004', company: 'TY', source: 'referral', name_fa: 'رضا ک.', contact: 'cu_5d1e02', stage: 'trial', value_usdt: 390, next_at: ago(-3), next_fa: 'یادآوری پایان دوره‌ی آزمایشی', assignee: { kind: 'employee', code: 'TY-SALES-01', display_fa: 'کارشناس فروش تریدیار' }, lost_reason_fa: null, events: [{ at: ago(9), kind: 'created', note_fa: 'معرفی از یک مشتری.' }], created_at: ago(9), updated_at: ago(4) },
  { ref: 'LD-000005', company: 'TY', source: 'site', name_fa: 'نیما ا.', contact: 'cu_a7733b', stage: 'paid', value_usdt: 49, next_at: null, next_fa: null, assignee: null, lost_reason_fa: null, events: [{ at: ago(0, '05:00'), kind: 'stage', note_fa: 'پرداخت رسید؛ خودکار «پرداخت کرد» شد.' }], created_at: ago(12), updated_at: ago(0) },
  { ref: 'LD-000006', company: 'TY', source: 'manual', name_fa: 'مریم ص.', contact: 'cu_zz90', stage: 'lost', value_usdt: 49, next_at: null, next_fa: null, assignee: null, lost_reason_fa: 'قیمت را بالا دید.', events: [{ at: ago(8), kind: 'stage', note_fa: 'از دست رفت.' }], created_at: ago(20), updated_at: ago(8) },
];
let nLd = 7;
const STAGES = ['new', 'contacted', 'qualified', 'trial', 'paid', 'lost'];
const MEDIAN: Record<string, number | null> = { new: 1.5, contacted: 2, qualified: 3, trial: 6, paid: null, lost: null };
const pipeline = (c: string) => {
  const mine = leads.filter((l) => l.company === c);
  const paid = mine.filter((l) => l.stage === 'paid').length, lost = mine.filter((l) => l.stage === 'lost').length;
  return { stages: STAGES.map((k) => ({ key: k, count: mine.filter((l) => l.stage === k).length, value_usdt: mine.filter((l) => l.stage === k).reduce((a, l) => a + (l.value_usdt ?? 0), 0), median_days: MEDIAN[k] })), win_rate: paid + lost ? paid / (paid + lost) : null };
};
const gaps = [
  { account: 'exchange-a/main', company: 'TY', month: `${monthsBack(1)}-01`, due_usdt: 412.5, received_usdt: 371.2, gap_pct: 10, state: 'open', draft_fa: 'سلام، کمیسیون ماه گذشته‌ی حساب اصلی 41 دلار کم‌تر از محاسبه‌ی ما رسیده. لطفاً گزارش تسویه را بفرستید.', planner: 'PL-0042' },
  { account: 'exchange-b/main', company: 'FX', month: `${monthsBack(1)}-01`, due_usdt: 188, received_usdt: 186.1, gap_pct: 1, state: 'in_window', draft_fa: null, planner: null },
  { account: 'exchange-a/main', company: 'TY', month: `${monthsBack(2)}-01`, due_usdt: 390, received_usdt: 390, gap_pct: 0, state: 'closed', draft_fa: null, planner: null },
];

// ================================================================================================= journey ==
const J_STAGES = [['founded', 'تأسیس'], ['server_ready', 'سرور آماده'], ['first_content', 'اولین محتوا'], ['first_visitor', 'اولین بازدیدکننده'], ['first_lead', 'اولین سرنخ'], ['first_payment', 'اولین پرداخت'], ['ten_paying', 'ده مشتری پرداخت‌کننده'], ['break_even', 'سربه‌سر']] as const;
const EVIDENCE = [{ kind: 'company', ref: 'TY' }, { kind: 'server', ref: 'SRV-0003' }, { kind: 'deliverable', ref: 'DL-000012' }, { kind: 'analytics', ref: 'AN-0001' }, { kind: 'lead', ref: 'LD-000001' }, { kind: 'payment', ref: 'PM-0001' }, { kind: 'revenue', ref: 'RB-0001' }, { kind: 'revenue', ref: 'RB-0002' }];
const REACHED: Record<string, number> = { TY: 6, FX: 4, PC: 3 };
const journey = (c: string) => {
  const n = REACHED[c] ?? 2;
  return {
    company: c, stages: J_STAGES.map(([key, title_fa], i) => ({ key, title_fa, reached_at: i < n ? ago((n - i) * 14) : null, evidence: i < n ? { ...EVIDENCE[i]!, ref: i === 0 ? c : EVIDENCE[i]!.ref } : null })),
    current: J_STAGES[Math.min(n, J_STAGES.length - 1)]![0], next_fa: n >= 8 ? null : 'برای ده مشتری پرداخت‌کننده، پیگیری سرنخ‌های مرحله‌ی آزمایشی را هر روز انجام بده.', days_in_stage: 9,
  };
};

// ================================================================================================= personas ==
const personas: any[] = [
  { id: 'PR-1', company: 'TY', name_fa: 'معامله‌گر تازه‌کار', summary_fa: 'تازه وارد بازار شده، از ضرر میترسد و دنبال قاعده‌ی ساده است.', pains_fa: ['نمیداند حد ضرر کجا بگذارد', 'از سیگنال‌های بی‌دلیل خسته است'], objections_fa: ['اشتراک ماهانه گران است', 'به کانال‌های تلگرام اعتماد ندارد'], channel_fa: 'اینستاگرام و تلگرام', source: 'owner', version: 1 },
  { id: 'PR-2', company: 'TY', name_fa: 'معامله‌گر باتجربه', summary_fa: 'چند سال معامله کرده و دنبال ابزار مدیریت ریسک است.', pains_fa: ['حسابداری معاملات وقتش را میگیرد'], objections_fa: ['ابزار خودش را دارد'], channel_fa: 'سایت و ایمیل', source: 'owner', version: 1 },
  { id: 'PR-3', company: 'FX', name_fa: 'سرمایه‌گذار محتاط', summary_fa: 'پول کمی دارد و دنبال سود پایدار است.', pains_fa: ['ترس از نوسان'], objections_fa: ['ریسک را زیاد میبیند'], channel_fa: 'تلگرام', source: 'owner', version: 1 },
];
let nPr = 4;
const IDEAS = [
  { name_fa: 'دانشجوی علاقه‌مند به بازار', summary_fa: 'وقت دارد ولی سرمایه ندارد؛ دنبال آموزش رایگان است.', pains_fa: ['پول کافی برای شروع ندارد'], objections_fa: ['فقط محتوای رایگان میخواهد'], channel_fa: 'یوتیوب', source: 'kb_suggested' },
  { name_fa: 'کارمندی که کنار کار معامله میکند', summary_fa: 'فقط شب‌ها وقت دارد و نمیتواند بازار را دنبال کند.', pains_fa: ['نمیتواند همیشه پای نمودار باشد'], objections_fa: ['به ربات و سیگنال خودکار شک دارد'], channel_fa: 'تلگرام', source: 'kb_suggested' },
];

// ================================================================================================== impact ==
const IMPACT: Record<string, unknown> = {
  'D-000087': { revenue_usdt: 1200, cost_usd: 12, horizon_days: 30, basis_fa: 'بازدید و تبدیل سه استوری مشابه تریدیار در ۱۴ روز اخیر.', kind: 'measured' },
  'D-000035': { revenue_usdt: 900, cost_usd: 12, horizon_days: 60, basis_fa: 'کاهش ریزش بعد از ثبت شناسه در سه ماه گذشته.', kind: 'estimate' },
  'D-000085': { revenue_usdt: 300, cost_usd: 60, horizon_days: 60, basis_fa: 'پاسخ مثبت احتمالی به ایمیل‌های مشابه.', kind: 'estimate' },
  'D-000017': { revenue_usdt: null, cost_usd: -150, horizon_days: 30, basis_fa: 'کم شدن خرابی‌های ترمینال در سی روز اخیر.', kind: 'measured' },
};

// ========================================================================================== order reports ==
const part = (ref: string, title_fa: string, role_fa: string, state: string, extra: Record<string, unknown> = {}) => ({ ref, title_fa, role_fa, state, progress_pct: state === 'done' ? 100 : null, summary_fa: null, outputs: [], failed_fa: null, ...extra });
const orderReport = (ref: string, text_fa: string, extra: Record<string, unknown>) => ({
  ref, text_fa, at: ago(1, '08:00'), state: 'in_progress', ack: { at: ago(1, '08:05'), by: { kind: 'employee', code: 'TY-CEO', display_fa: 'مدیرعامل تریدیار' }, plan_fa: 'کار به چند بخش مستقل بخش شد و همزمان پیش میرود.', assigned: [{ company: 'TY', code: 'TY-CEO', title_fa: 'مدیرعامل تریدیار' }], due_at: null },
  route: null, steps: [{ at: ago(1, '08:10'), who_fa: 'مدیرعامل تریدیار', what_fa: 'کار را به بخش‌های مستقل تقسیم کرد.' }], outputs: [], blockers: [], summary: null, updated_at: ago(0, '07:00'), ...extra,
});
const ORDERS: Record<string, unknown> = {
  'F-0097': orderReport('F-0097', 'بسته‌ی محتوای هفته‌ی آموزش حد ضرر را بساز', {
    state: 'delivered', summary: { done_fa: 'دو بخش از سه بخش آماده شد و ادغام نوشته شد.', left_fa: 'بخش ریلز تمام نشد.', need_fa: 'تصمیم بگیر ریلز دوباره ساخته شود یا نه.' },
    parts: [
      part('W-000301', 'متن مقاله', 'نویسنده‌ی سایت', 'done', { summary_fa: 'مقاله‌ی ۸۰۰ کلمه‌ای آماده است.', outputs: [{ ref: 'DL-000101', title_fa: 'مقاله‌ی حد ضرر' }] }),
      part('W-000302', 'پست تلگرام', 'مدیر کانال', 'done', { summary_fa: 'سه پست زمان‌بندی‌شده آماده است.', outputs: [{ ref: 'DL-000102', title_fa: 'پست‌های تلگرام' }] }),
      part('W-000303', 'ریلز آموزشی', 'ویرایشگر ویدیو', 'failed', { failed_fa: 'صدای فارسی ساخته نشد؛ موتور صدا کلید نداشت.' }),
    ],
    merge: { state: 'done', by_fa: 'مدیرعامل تریدیار', text_fa: 'مقاله و پست‌های تلگرام آماده‌اند. ریلز به‌خاطر نبود کلید موتور صدا ساخته نشد و در این بسته نیست.' },
  }),
  'F-0096': orderReport('F-0096', 'تحلیل سئوی سایت را روی سرور خودش انجام بده', {
    parts: [
      part('W-000311', 'جمع‌آوری صفحه‌ها', 'تحلیلگر سئو', 'done', { summary_fa: '۲۴۰ صفحه خوانده شد.' }),
      part('W-000312', 'بررسی سرعت', 'مهندس وب', 'running', { progress_pct: 60 }),
      part('W-000313', 'پیشنهاد محتوا', 'مدیر محتوا', 'queued'),
    ],
    merge: { state: 'waiting', by_fa: 'مدیرعامل تریدیار', text_fa: null },
    workspace: { mode: 'on_server', server_fa: 'تریدیار', state: 'working', progress_pct: 60, note_fa: 'Claude همان سرور در پوشه‌ی کار، فایل‌های سایت را میخواند و گزارش را مینویسد.', folder: '~/hq-workspace/W-000312' },
  }),
};

// ================================================================================================= handler ==
export async function handle33(req: Request, p: string, q: URLSearchParams, next: () => Promise<Response>): Promise<Response | null> {
  if (!/^\/(usage\/|payment-sources|personas\/|companies\/[^/]+\/(payment-sources|payments|reconcile|leads|pipeline|journey|personas)|revenue\/(board|affiliate-gaps|summary)|leads\/|journeys$|decisions|orders\/F-009[67]\/report)/.test(p)) return null;
  const m = req.method;
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;
  const stepUp = req.headers.get('X-Step-Up');

  // ----------------------------------------------------------------------------------------------- usage --
  if (p === '/usage/reports' && m === 'GET') { const per = q.get('period'); return json({ items: reports.filter((r) => !per || r.period === per), next_cursor: null }); }
  if (p === '/usage/reports' && m === 'POST') {
    const b = await body<{ period: 'day' | 'week' }>();
    const r = { ref: `UR-${String(nUr++).padStart(4, '0')}`, period: b.period, pack: pack(b.period, 0), text: { lines_fa: ['گزارش تازه نوشته شد؛ مصرف امروز عادی است.', 'تولید محتوا بیشترین سهم را دارد.', 'چیز غیرعادی دیده نشد.'], saving_fa: 'فعلاً صرفه‌جویی تازه‌ای پیدا نشد؛ مصرف صدا را زیر نظر نگه دارید.' }, at: new Date().toISOString() };
    reports.unshift(r);
    return json(r, 201);
  }

  // ------------------------------------------------------------------------------------------- payments --
  const ps = /^\/companies\/([^/]+)\/payment-sources$/.exec(p);
  if (ps && m === 'GET') return json(sources.filter((s) => s.company === ps[1]));
  if (ps && m === 'POST') {
    if (!stepUp) return needStepUp();
    const b = await body<any>();
    const i = b.id ? sources.findIndex((s) => s.id === b.id) : -1;
    if (i >= 0) { Object.assign(sources[i], { adapter: b.adapter, network: b.network, address: b.address, state: 'ok' }); return json(sources[i]); }
    const s = { id: `PS-${ps[1]}-${nSrc++}`, company: ps[1], kind: b.kind, adapter: b.adapter, network: b.network, address: b.address, state: 'ok', last_read_at: null, last_error_fa: null };
    sources.push(s);
    return json(s, 201);
  }
  const rd = /^\/payment-sources\/([^/]+)\/read$/.exec(p);
  if (rd && m === 'POST') {
    const s = sources.find((x) => x.id === rd[1]);
    if (!s) return problem(404, 'not_found', 'این منبع پیدا نشد.');
    if (s.state === 'error') return problem(502, 'upstream_error', 'شبکه‌ی ترون جواب نداد؛ کمی بعد دوباره بخوان.');
    s.last_read_at = new Date().toISOString();
    return json(s);
  }
  const pm = /^\/companies\/([^/]+)\/payments$/.exec(p);
  if (pm && m === 'GET') {
    const st = q.get('status'), from = q.get('from') ?? '0000', to = q.get('to') ?? '9999';
    return json({ items: payRows(pm[1]!).filter((x) => (!st || x.status === st) && String(x.paid_at).slice(0, 10) >= from && String(x.paid_at).slice(0, 10) <= to), next_cursor: null });
  }
  const rc = /^\/companies\/([^/]+)\/reconcile$/.exec(p);
  if (rc && m === 'GET') { const from = q.get('from') ?? '0000', to = q.get('to') ?? '9999'; return json(reconcile(rc[1]!).filter((d) => d.day >= from && d.day <= to)); }

  // ----------------------------------------------------------------------------------------------- revenue --
  if (p === '/revenue/board' && m === 'GET') return json(board(q.get('company')));
  if (p === '/revenue/summary' && m === 'GET') {
    const r = await next();
    if (!r.ok) return r;
    const s = (await r.clone().json().catch(() => null)) as Record<string, unknown> | null;
    return s ? json({ ...s, by_source: [{ source: 'affiliate', usdt: 1840 }, { source: 'payments', usdt: 2050 }] }) : r;
  }
  if (p === '/revenue/affiliate-gaps' && m === 'GET') { const c = q.get('company'); return json({ items: gaps.filter((g) => !c || g.company === c) }); }

  // -------------------------------------------------------------------------------------------------- crm --
  const ld = /^\/companies\/([^/]+)\/leads$/.exec(p);
  if (ld && m === 'GET') return json({ items: leads.filter((l) => l.company === ld[1]), next_cursor: null });
  if (ld && m === 'POST') {
    const b = await body<any>();
    if (!b.contact?.trim()) return problem(422, 'validation_failed', 'شناسه‌ی تماس لازم است.');
    const l = { ref: `LD-${String(nLd++).padStart(6, '0')}`, company: ld[1], source: b.source ?? 'manual', name_fa: b.name_fa ?? null, contact: b.contact, stage: 'new', value_usdt: b.value_usdt ?? null, next_at: null, next_fa: null, assignee: null, lost_reason_fa: null, events: [{ at: new Date().toISOString(), kind: 'created', note_fa: 'دستی ثبت شد.' }], created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
    leads.push(l);
    return json(l, 201);
  }
  const pl = /^\/companies\/([^/]+)\/pipeline$/.exec(p);
  if (pl && m === 'GET') return json(pipeline(pl[1]!));
  const lo = /^\/leads\/([^/]+)$/.exec(p);
  if (lo && m === 'GET') { const l = leads.find((x) => x.ref === lo[1]); return l ? json(l) : problem(404, 'not_found', 'این سرنخ پیدا نشد.'); }
  if (lo && m === 'PATCH') {
    const l = leads.find((x) => x.ref === lo[1]);
    if (!l) return problem(404, 'not_found', 'این سرنخ پیدا نشد.');
    const b = await body<any>();
    if (b.stage && b.stage !== l.stage) l.events.push({ at: new Date().toISOString(), kind: 'stage', note_fa: `به «${b.stage}» رفت.` });
    Object.assign(l, b, { updated_at: new Date().toISOString() });
    return json(l);
  }
  const dr = /^\/leads\/([^/]+)\/draft$/.exec(p);
  if (dr && m === 'POST') {
    const l = leads.find((x) => x.ref === dr[1]);
    if (!l) return problem(404, 'not_found', 'این سرنخ پیدا نشد.');
    return json({ text_fa: `سلام ${l.name_fa ?? ''}، از تیم تریدیار می‌نویسیم. دیدیم به پلن ماهانه علاقه نشان دادید؛ اگر سؤالی درباره‌ی حد ضرر یا پرداخت دارید همین‌جا بپرسید تا کمک کنیم.`.replace('  ', ' ') });
  }

  // ----------------------------------------------------------------------------------------------- journey --
  const jo = /^\/companies\/([^/]+)\/journey$/.exec(p);
  if (jo && m === 'GET') return json(journey(jo[1]!));
  if (p === '/journeys' && m === 'GET') return json(['TY', 'FX', 'PC'].map(journey));

  // ---------------------------------------------------------------------------------------------- personas --
  const pr = /^\/companies\/([^/]+)\/personas(?:\/([^/]+))?$/.exec(p);
  if (pr && !pr[2] && m === 'GET') return json({ items: personas.filter((x) => x.company === pr[1]) });
  if (pr && !pr[2] && m === 'POST') {
    const b = await body<any>();
    const x = { ...b, id: `PR-${nPr++}`, company: pr[1], version: 1 };
    personas.push(x);
    return json(x, 201);
  }
  if (pr && pr[2] === 'suggest' && m === 'POST') return json({ items: IDEAS });
  if (pr && pr[2] === 'test' && m === 'POST') {
    const b = await body<{ text: string }>();
    if (!b.text?.trim()) return problem(422, 'validation_failed', 'متن پیام لازم است.');
    const mine = personas.filter((x) => x.company === pr[1]);
    return json({ text: b.text, at: new Date().toISOString(), results: mine.map((x, i) => {
      const score = 35 + ((b.text.length * (i + 3)) % 60);
      return { persona: x.id, score, would_act: score >= 60, objection_fa: score >= 60 ? null : (x.objections_fa[0] ?? null), fix_fa: score >= 60 ? null : 'قیمت را کنار یک نمونه‌ی ملموس از صرفه‌جویی بگذار.' };
    }) });
  }
  const one = /^\/personas\/([^/]+)$/.exec(p); // PATCH and DELETE /personas/{id} (contract §33.9)
  if (one && m === 'PATCH') {
    const i = personas.findIndex((x) => x.id === one[1]);
    if (i < 0) return problem(404, 'not_found', 'این پرسونا پیدا نشد.');
    const b = await body<any>();
    personas[i] = { ...personas[i], ...b, version: personas[i].version + 1 };
    return json(personas[i]);
  }
  if (one && m === 'DELETE') { const i = personas.findIndex((x) => x.id === one[1]); if (i >= 0) personas.splice(i, 1); return json(null, 204); }

  // ---------------------------------------------------------------------------------------------- impact --
  if (p === '/decisions' && m === 'GET') {
    const r = await next();
    if (!r.ok) return r;
    const s = (await r.clone().json().catch(() => null)) as { items?: Array<{ ref: string }> } | null;
    if (!s?.items) return r;
    return json({ ...s, items: s.items.map((d) => (IMPACT[d.ref] ? { ...d, impact: IMPACT[d.ref] } : d)) });
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
  return null;
}
