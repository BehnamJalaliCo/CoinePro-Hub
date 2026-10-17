// Development-only fixtures (npm run dev:mock). Never bundled in production:
// the client imports this module only when NEXT_PUBLIC_HQ_MOCK=1.

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
  counts: { decisions_pending: [1, 2, 1, 1][i] ?? 0, employees_active: [5, 9, 10, 9][i] ?? 0, work_open: [3, 7, 11, 4][i] ?? 0 },
}));

const actor = (code: string, display_fa: string, kind = 'agent') => ({ kind, code, display_fa });
const owner = { kind: 'owner', code: 'owner', display_fa: 'مدیر کل' };

const decisions: any[] = [
  {
    ref: 'D-000014', kind: 'hire', company: 'TY', action_class: 'A1', risk: 'low', reversible: true, status: 'pending',
    title: 'استخدام SRE تریدیار', proposer: actor('TY-TECH-MGR', 'مدیر فنی تریدیار'), created_at: iso(42),
    what: 'یک **مهندس پایداری (SRE)** برای پایش سلامت سایت و پنل کاربری تریدیار. فقط وقتی پایش‌های قاعده‌محور خطا پیدا کنند بیدار میشود.',
    why: 'در ۷ روز گذشته `user.tradeyar.trade-future.ir` دو بار بیش از ۵ دقیقه کند بود و کسی پیگیری نکرد (شاهد: I-0002، I-0005).',
    quota_estimate: { tokens: 420000, usd: '6.80' }, risk_note: 'فقط‌خواندنی؛ هیچ اقدام بیرونی ندارد.',
    payload: { department: 'TECH', title_fa: 'مهندس پایداری (SRE)', title_en: 'Site Reliability Engineer', role: 'sre', model: 'claude-haiku-5-5', effort: 'high', duties: ['بررسی هشدارهای سایت و پنل', 'خلاصه‌ی روزانه‌ی سلامت', 'پیشنهاد اصلاح آستانه‌ها'], permissions: ['health.sites', 'deliver', 'notify'], quota_estimate_month: 420000 },
    seal: null, decided_at: null, decided_by: null, note: null, resolution: null, thread: 'TY-TECH-MGR', expires_at: ahead(60 * 46), version: 1, effect_status: 'none', work_id: null, id: 'd14', reason_code: null,
  },
  {
    ref: 'D-000015', kind: 'hire', company: 'FX', action_class: 'A1', risk: 'low', reversible: true, status: 'pending',
    title: 'استخدام SRE کوینه‌پرو FX', proposer: actor('FX-TECH-MGR', 'مدیر فنی FX'), created_at: iso(38),
    what: 'یک SRE برای پایش `coineprofx.com` و `fx.trade-future.ir`، با خلاصه‌ی روزانه و تحلیل هشدارها.',
    why: 'سیگنال‌ها و ربات تلگرام به سلامت سرویس وابسته‌اند؛ امروز هیچ نقشی مسئول پایش نیست.',
    quota_estimate: { tokens: 380000, usd: '6.10' }, risk_note: null,
    payload: { department: 'TECH', title_fa: 'مهندس پایداری (SRE)', role: 'sre', model: 'claude-haiku-5-5', effort: 'high', duties: ['تحلیل هشدار', 'خلاصه‌ی روزانه'], permissions: ['health.sites', 'deliver', 'notify'], quota_estimate_month: 380000 },
    seal: null, decided_at: null, decided_by: null, note: null, resolution: null, thread: 'FX-TECH-MGR', expires_at: ahead(60 * 47), version: 1, effect_status: 'none', work_id: null, id: 'd15', reason_code: null,
  },
  {
    ref: 'D-000016', kind: 'hire', company: 'HQ', action_class: 'A1', risk: 'medium', reversible: true, status: 'pending',
    title: 'تیم نظارت: مسئول ایمنی هوش مصنوعی', proposer: actor('HQ-OVS-MGR', 'بازرس کل'), created_at: iso(33),
    what: 'مسئول ایمنی هوش مصنوعی برای بررسی اینکه ایجنت‌ها در محدوده‌ی اختیارشان میمانند.',
    why: 'با شروع کار ایجنت‌ها، یک نقش مستقل باید audit و پیشنهادهای A3 را مرور کند.',
    quota_estimate: { tokens: 900000, usd: '14.20' }, risk_note: 'دسترسی به audit (فقط متادیتا).',
    payload: { department: 'OVS', title_fa: 'مسئول ایمنی هوش مصنوعی', role: 'ai_safety', model: 'claude-sonnet-5-5', effort: 'high', duties: ['مرور audit', 'گزارش هفتگی ایمنی'], permissions: ['audit.recent', 'deliver', 'notify'], quota_estimate_month: 900000 },
    seal: null, decided_at: null, decided_by: null, note: null, resolution: null, thread: 'HQ-OVS-MGR', expires_at: ahead(60 * 47), version: 1, effect_status: 'none', work_id: null, id: 'd16', reason_code: null,
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
  { code: 'FX-QUANT-02', company: 'FX', kind: 'employee', department: 'QUANT', title_fa: 'پایشگر سیگنال', title_en: 'Signal monitor', activity: 'waiting' },
  { code: 'HQ-OVS-MGR', company: 'HQ', kind: 'inspector', department: 'OVS', title_fa: 'بازرس کل', title_en: 'Inspector General', activity: 'sleeping' },
  { code: 'HQ-AIOPS-MGR', company: 'HQ', kind: 'manager', department: 'AIOPS', title_fa: 'مدیر عملیات هوش مصنوعی', title_en: 'Head of AI Ops', activity: 'idle' },
  { code: 'HQ-ADV', company: 'HQ', kind: 'advisor', department: null, title_fa: 'مشاور کل', title_en: 'Chief Advisor', activity: 'idle' },
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
  { ref: 'W-000105', title: 'پیشنهاد تیم فنی ماه ۱', company: 'PC', status: 'queued', priority: 'P3', depth: 1, assignee: { code: 'PC-TECH-MGR', company: 'PC', kind: 'manager', department: 'TECH', title_fa: 'مدیر فنی' }, due_at: ahead(60 * 20), progress_pct: null },
  { ref: 'W-000098', title: 'ممیزی امنیتی همه‌ی شرکت‌ها', company: 'HQ', status: 'waiting', priority: 'P2', depth: 0, assignee: { code: 'HQ-OVS-MGR', company: 'HQ', kind: 'inspector', department: 'OVS', title_fa: 'بازرس کل' }, due_at: iso(120), progress_pct: 20 },
].map((w, i) => ({ id: `w${i}`, kind: 'one_off', brief: 'جزئیات کار…', created_at: iso(60 * (i + 2)), updated_at: iso(i * 11), created_by: owner, department: w.assignee?.department ?? null, overdue: w.ref === 'W-000098', escalation_level: w.ref === 'W-000098' ? 1 : 0, parent_id: null, root_id: `w${i}`, requested_by_work_id: null, budget: { tokens: 200000, tokens_used: 46000 + i * 9000, usd: null, usd_used: '0.80' }, escrow: null, schedule: null, deliverable_ids: [], evidence: [], progress_note: null, version: 1, ...w }));

const threads: any[] = [
  { code: 'A', kind: 'advisor', company: 'HQ', title_fa: 'مشاور کل', unread: 0, last_message_at: iso(25), last_ref: 'A-0004', participants: [owner, actor('HQ-ADV', 'مشاور کل')] },
  { code: 'FX-CEO', kind: 'ceo', company: 'FX', title_fa: 'مدیرعامل FX', unread: 2, last_message_at: iso(12), last_ref: 'FX-CEO-0009', participants: [owner, actor('FX-CEO', 'مدیرعامل FX')] },
  { code: 'TY-TECH-MGR', kind: 'manager', company: 'TY', title_fa: 'مدیر فنی تریدیار', unread: 1, last_message_at: iso(42), last_ref: 'TY-TECH-MGR-0002', participants: [owner, actor('TY-TECH-MGR', 'مدیر فنی تریدیار')] },
].map((t, i) => ({ id: `t${i}`, ...t }));

const messages: Record<string, any[]> = {
  A: [
    { ref: 'A-0001', author: owner, body: 'وضعیت کلی هلدینگ امروز چطور است؟', created_at: iso(60 * 3) },
    { ref: 'A-0002', author: actor('HQ-ADV', 'مشاور کل'), body: '**خلاصه:** چهار تصمیم منتظر مُهر توست؛ سه تا پیشنهاد استخدام ماه ۱ و یکی انتشار پرو-چارت (ریسک بالا).\n\nمصرف توکن امروز `182K` است، ۱۸٪ زیر میانگین هفته (طبق خزانه). پیشنهادم: اول انتشار پرو-چارت را ببین چون تا ۶ ساعت دیگر منقضی میشود (D-000017).', created_at: iso(60 * 3 - 1), links: { decision: 'D-000017' } },
    { ref: 'A-0003', author: owner, body: 'استخدام SRE برای هر سه شرکت لازم است؟', created_at: iso(30) },
    { ref: 'A-0004', author: actor('HQ-ADV', 'مشاور کل'), body: 'برای تریدیار و FX شاهد دارد (دو حادثه‌ی کندی در تریدیار: I-0002، I-0005). برای پرو-چارت هنوز پیشنهادی نیامده. هزینه‌ی هر SRE با Haiku 5.5 حدود `$6–7` در ماه برآورد شده؛ برگشت‌پذیر است.\n\n**توصیه:** دو استخدام اول را مُهر کن؛ سومی را بعد از دیدن پیشنهاد پرو-چارت.', created_at: iso(25), links: { decision: 'D-000014' } },
  ].map((m, i) => ({ id: `m${i}`, thread: 'A', kind: 'text', attachments: [], links: {}, ...m })),
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

const planner = () => {
  const days = Array.from({ length: 7 }, (_, d) => {
    const date = new Date(now + d * 86_400_000);
    const at = (h: number) => { const x = new Date(date); x.setUTCHours(h, 30, 0, 0); return x.toISOString(); };
    const items = [
      d === 0 && { ref: 'W-000104', title: 'رفع کندی ثبت‌نام', company: 'FX', priority: 'P1', status: 'in_progress', at: at(10), assignee: 'FX-TECH-MGR', recurring: false },
      { ref: `W-1${d}0`, title: 'گزارش صبحگاهی', company: 'HQ', priority: 'P3', status: d === 0 ? 'done' : 'queued', at: at(4), assignee: 'HQ-SYS', recurring: true },
      d % 2 === 0 && { ref: `W-2${d}0`, title: 'خلاصه‌ی سلامت سایت‌ها', company: ['TY', 'FX', 'PC'][d % 3], priority: 'P3', status: 'queued', at: at(6), assignee: null, recurring: true },
      d === 1 && { ref: 'W-000105', title: 'پیشنهاد تیم فنی ماه ۱', company: 'PC', priority: 'P3', status: 'queued', at: at(8), assignee: 'PC-TECH-MGR', recurring: false },
      d === 3 && { ref: 'W-000098', title: 'ممیزی امنیتی همه‌ی شرکت‌ها', company: 'HQ', priority: 'P2', status: 'waiting', at: at(9), assignee: 'HQ-OVS-MGR', recurring: false },
      d === 5 && { ref: 'W-000120', title: 'جلسه‌ی هفتگی هیئت‌مدیره', company: 'HQ', priority: 'P2', status: 'queued', at: at(6), assignee: null, recurring: true },
    ].filter(Boolean);
    return { date: date.toISOString().slice(0, 10), items };
  });
  return { scope: 'holding', timezone: 'Asia/Tehran', days };
};

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

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const page = (items: unknown[]) => ({ items, next_cursor: null });

export async function handle(req: Request): Promise<Response> {
  const u = new URL(req.url);
  const p = u.pathname.replace(/^\/api\/v1/, '');
  const m = req.method;
  await new Promise((r) => setTimeout(r, 120 + Math.random() * 180));
  if (m !== 'GET') {
    if (p.startsWith('/auth/passkey/') && p.endsWith('/options')) return json({ challenge: 'mock', rpId: 'localhost', timeout: 60000, userVerification: 'required' });
    if (p === '/auth/step-up/options') return json({ challenge: 'mock' });
    if (p === '/auth/step-up/verify') return json({ step_up_token: 'mock-step-up', expires_at: ahead(2) });
    if (p === '/auth/passkey/login/verify') return json({ session: { expires_at: ahead(60 * 24 * 30) } });
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
      const body = (await req.json()) as { body: string };
      const list = (messages[t[1]!] ??= []);
      const msg = { id: `m${Date.now()}`, ref: `${t[1]}-${String(list.length + 1).padStart(4, '0')}`, thread: t[1], author: owner, body: body.body, created_at: new Date().toISOString(), kind: 'text', attachments: [], links: {} };
      list.push(msg);
      return json({ message: msg, reply: { state: 'queued' } }, 201);
    }
    if (p === '/owner/presence') { const b = (await req.json()) as { khalvat: boolean }; presence.khalvat = b.khalvat; presence.since = new Date().toISOString(); return json(presence); }
    if (p === '/control/kill-switch') { const b = (await req.json()) as { scope: string; state: string; reason: string }; const k = b.scope === 'holding' ? control.holding : control.companies.find((c) => c.scope === b.scope); if (k) Object.assign(k, { state: b.state, reason: b.reason, changed_at: new Date().toISOString(), changed_by: 'owner' }); return json(control); }
    return json({}, 200);
  }
  if (p === '/auth/session') return json({ principal: { kind: 'owner', code: 'owner' }, device: { id: 'dev1', name: 'Chrome · Android', kind: 'session', created_at: iso(600), last_used_at: iso(0), current: true }, expires_at: ahead(60 * 24 * 30) });
  if (p === '/meta') return json({ api_version: '1.1', service_version: 'mock', login_configured: true, public_origin: u.origin, stream_retention_days: 30, channels: { in_app: true, web_push: true, fcm: false, telegram: false } });
  if (p === '/inbox/summary') return json({ decisions_pending: decisions.filter((d) => d.status === 'pending').length, decisions_by_risk: { low: 2, medium: 1, high: 1 }, deliverables_unrated: deliverables.filter((d) => !d.rating).length, messages_unread: 3, khalvat: presence.khalvat, notifications: { urgent: 0, decision: 1, report: 0, info: 2, learning: 1 } });
  if (p === '/owner/presence') return json(presence);
  if (p === '/owner/away-summary') return json({ since: iso(60 * 9), until: iso(0), companies: CO.map((c, i) => ({ company: c.code, decisions_new: [1, 1, 1, 1][i], deliverables_new: [1, 1, 1, 0][i], messages_new: [0, 1, 2, 0][i], notifications_new: [1, 1, 0, 1][i] })), decisions: { new: 4, pending: 4, top: decisions.filter((d) => d.status === 'pending').map((d) => ({ ref: d.ref, company: d.company, kind: d.kind, risk: d.risk, status: d.status, title: d.title, created_at: d.created_at })) }, deliverables: { new: 3, unrated: 2, top: deliverables.map((d) => ({ ref: d.ref, company: d.company, title: d.title, created_at: d.created_at })) }, messages: { new: 3, unread: 3, top_threads: threads.map((t) => ({ thread: t.code, company: t.company, new_messages: t.unread, last_at: t.last_message_at })) }, notifications: { by_level: { decision: 1, report: 1, learning: 1 }, held: 2, top: [] } });
  if (p === '/decisions') { const st = u.searchParams.get('status') ?? 'pending'; return json(page(decisions.filter((d) => st === 'all' || d.status === st))); }
  const dd = /^\/decisions\/(D-\d+)$/.exec(p); if (dd) return json(decisions.find((d) => d.ref === dd[1]) ?? {}, decisions.some((d) => d.ref === dd[1]) ? 200 : 404);
  if (p === '/deliverables') return json(page(u.searchParams.get('unrated') === 'true' ? deliverables.filter((d) => !d.rating) : deliverables));
  const od = /^\/deliverables\/(O-\d+)$/.exec(p); if (od) return json(deliverables.find((d) => d.ref === od[1]) ?? {});
  if (p === '/companies') return json(companies);
  const cd = /^\/companies\/([A-Z0-9]+)$/.exec(p); if (cd) return json(companies.find((c) => c.code === cd[1]) ?? {});
  const dep = /^\/companies\/([A-Z0-9]+)\/departments$/.exec(p);
  if (dep) return json(['TECH', 'GROWTH', 'SALES', 'PRODUCT', 'FIN', 'QUANT', 'AIOPS', 'HR'].map((k, i) => ({ id: `${dep[1]}-${k}`, code: k, company: dep[1], name_fa: ['فنی', 'رشد و مارکتینگ', 'فروش و پشتیبانی', 'محصول', 'مالی', 'کوانت', 'عملیات هوش مصنوعی', 'منابع انسانی'][i], name_en: k, manager_title_fa: ['مدیر فنی', 'مدیر مارکتینگ', 'مدیر فروش', 'مدیر محصول', 'مدیر مالی', 'مدیر کوانت', 'مدیر عملیات AI', 'مدیر منابع انسانی'][i], manager_title_en: k, manager: { code: `${dep[1]}-${k}-MGR`, company: dep[1], department: k, kind: 'manager', title_fa: 'مدیر' }, sort: i, status: 'active', version: 1 })));
  if (p === '/employees') { const c = u.searchParams.getAll('company'); return json(page(c.length ? employees.filter((e) => c.includes(e.company)) : employees)); }
  const ed = /^\/employees\/([A-Z0-9-]+)$/.exec(p); if (ed) { const e = employees.find((x) => x.code === ed[1]); return e ? json({ ...e, recent_ratings: [{ deliverable: 'O-000031', score: 8, rated_at: iso(60) }], recent_work: work.slice(0, 2).map((w) => ({ ref: w.ref, title: w.title, status: w.status })) }) : json({}, 404); }
  if (p === '/work') return json(page(work));
  const wd = /^\/work\/([^/]+)$/.exec(p); if (wd) { const w = work.find((x) => x.id === wd[1] || x.ref === wd[1]) ?? work[0]; return json({ ...w, chain: [{ id: 'c0', ref: w.ref, depth: 0, status: 'delivered', assignee: { code: `${w.company}-CEO`, company: w.company, kind: 'ceo', title_fa: 'مدیرعامل' }, created_at: iso(300), tokens_used: 6200, usd_used: 0.1 }, { id: 'c1', ref: w.ref, depth: 1, status: w.status, assignee: w.assignee, created_at: iso(280), tokens_used: 41000, usd_used: 0.7 }], children: [] }); }
  if (p.endsWith('/events')) return json(page([]));
  if (p === '/planner') return json(planner());
  if (p === '/threads') return json(threads);
  const tm = /^\/threads\/([^/]+)\/messages$/.exec(p); if (tm) return json(page(messages[tm[1]!] ?? []));
  if (p === '/notifications') return json({ items: notifications, next_cursor: null });
  if (p === '/control/state') return json(control);
  if (p === '/treasury/summary') return json(summary);
  if (p === '/treasury/breakdown') return json(breakdown(u.searchParams.get('by') ?? 'day'));
  if (p === '/treasury/calls') return json(page([]));
  if (p === '/connections') return json([{ id: 'c1', key: 'claude-max', display_name: 'اشتراک Claude (Max)', kind: 'claude_subscription', provider: 'anthropic', status: 'enabled', status_reason: null, models: ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'], default_model: 'claude-sonnet-5-5', fallback_priority: 1, has_secret_ref: true, limits: {}, pricing: {}, quota_reset_at: ahead(60 * 30), updated_at: iso(60), version: 1 }]);
  if (p === '/audit') return json(page(audit));
  if (p === '/audit/verify') return json({ ok: true, checked: 1200, first_bad_seq: null, verified_at: iso(60 * 6), anchor: 'ok' });
  if (p === '/resolutions') return json(page([{ ref: 'M-0003', title: 'گزارش هفتگی سئوی فنی تریدیار', body: '…', company: 'TY', sealed_at: iso(60 * 19), sealed_by: owner, sent_to: ['TY-GROWTH-MGR'], source: { decision: 'D-000011' }, follow_up_work_id: null, id: 'r3' }]));
  if (p === '/auth/devices') return json({ items: [{ id: 'dev1', name: 'Chrome · Android', kind: 'passkey', created_at: iso(60 * 20), last_used_at: iso(0), current: true }, { id: 'dev2', name: 'Safari · macOS', kind: 'passkey', created_at: iso(60 * 19), last_used_at: iso(60 * 3) }], next_cursor: null });
  if (p === '/owner/settings') return json({ timezone: 'Asia/Tehran', calendars: ['jalali', 'gregorian'], morning_report_at: '08:00', digest_minutes: 30, ceo_daily_attention: 6, learning_daily_cap: 3, version: 1 });
  const ch = /^\/org\/([A-Z0-9]+)\/chart$/.exec(p);
  if (ch) { const es = employees.filter((e) => e.company === ch[1]); const ceo = es.find((e) => e.kind === 'ceo'); const node = (e: any): any => ({ code: e.code, kind: e.kind, title_fa: e.title_fa, display_name: null, department: e.department, activity: e.activity, status: 'active', children: [] }); return json({ company: ch[1], roots: ceo ? [{ ...node(ceo), children: es.filter((e) => e.kind !== 'ceo').map(node) }] : es.map(node) }); }
  return json({ code: 'not_found', message_fa: 'پیدا نشد.', status: 404, title: 'Not found', type: 'about:blank' }, 404);
}

const presence = { khalvat: false, since: iso(60 * 9), until: null as string | null };
