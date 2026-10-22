// Development-only fixtures for the owner's tools on existing APIs (docs/GAP_ANALYSIS_v2.md §5A), used by mock.ts. Never bundled in
// production. The Android debug build reads the same data through scripts/dump_demo_fixtures.mjs.

const now = Date.now();
const iso = (minAgo: number) => new Date(now - minAgo * 60_000).toISOString();
const ahead = (min: number) => new Date(now + min * 60_000).toISOString();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const page = (items: unknown[], next_cursor: string | null = null) => ({ items, next_cursor });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const owner = { kind: 'owner', code: 'owner', display_fa: 'مدیر کل' };

/** The shared demo state mock.ts owns; this module reads and changes it. */
export type OpsState = {
  work: any[]; employees: any[]; control: any; companies: any[]; messages: Record<string, any[]>; threads: any[];
  envelope: Record<string, number | null>; summary: any; connections: any[];
};

// ------------------------------------------------------------ resolutions --
const resolutions: any[] = [
  { ref: 'M-0007', company: 'PC', title: 'انتشار ترمینال پرو-چارت با canary ۱۰٪', body: 'انتشار نسخه‌ی 1017ce2 با canary ۱۰٪ و بازگشت خودکار تأیید شد. اگر خطای ۵xx بالای ۱٪ رفت، بازگشت فوری.', source: { decision: 'D-000017' }, sent_to: ['PC-TECH-MGR', 'PC-CEO'], sealed_at: iso(60 * 2), follow_up_work_id: 'w0' },
  { ref: 'M-0006', company: null, title: 'گزارش روزانه‌ی مدیرعامل‌ها تا اطلاع بعدی خاموش', body: 'تا وقتی استخدام باز نشده، گزارش روزانه‌ی مدیرعامل‌ها خاموش میماند. گزارش صبحگاهی هلدینگ کافی است.', source: { message: 'A-0003' }, sent_to: ['TY-CEO', 'FX-CEO', 'PC-CEO'], sealed_at: iso(60 * 9), follow_up_work_id: null },
  { ref: 'M-0005', company: 'FX', title: 'فیلتر رژیم نوسان بعد از خبرهای فدرال رزرو', body: 'سیگنال‌های طلا تا ۳۰ دقیقه بعد از خبر فدرال رزرو با فیلتر رژیم نوسان صادر شوند. اثرش ۳۰ روز بعد بازبینی شود.', source: { decision: 'D-000012' }, sent_to: ['FX-QUANT-MGR', 'FX-CEO'], sealed_at: iso(60 * 30), follow_up_work_id: null },
  { ref: 'M-0004', company: 'TY', title: 'canonical صفحه‌های بلاگ به نشانی خود صفحه', body: 'هفت قالب بلاگ و بازار canonical را به نشانی خود صفحه بدهند. سئوی فنی بعد از انتشار، ایندکس را دوباره بسنجد.', source: { message: 'TY-TECH-MGR-0002' }, sent_to: ['TY-TECH-MGR'], sealed_at: iso(60 * 50), follow_up_work_id: null },
  { ref: 'M-0003', company: 'TY', title: 'گزارش هفتگی سئوی فنی تریدیار', body: 'بررسی هفتگی ۴۰ صفحه‌ی اصلی تریدیار، هر شنبه، با سقف ۲۰۰ هزار توکن.', source: { decision: 'D-000011' }, sent_to: ['TY-GROWTH-MGR'], sealed_at: iso(60 * 19 + 60 * 24), follow_up_work_id: null },
].map((r, i) => ({ id: `r${i}`, sealed_by: owner, ...r }));

// --------------------------------------------------- notification settings --
const notify = {
  version: 3,
  matrix: {
    '*': { urgent: { in_app: true, push: true, sound: true }, decision: { in_app: true, push: true, sound: false }, report: { in_app: true, push: false, sound: false }, info: { in_app: true, push: false, sound: false }, learning: { in_app: true, push: false, sound: false } },
    PC: { decision: { push: true, sound: true } },
    TY: { info: { in_app: false } },
  } as Record<string, Record<string, Record<string, unknown>>>,
};

// ------------------------------------------------------------------- runs --
const tok = (i: number, o: number) => ({ input: i, output: o, cache_read: Math.round(i * 0.4), cache_write: Math.round(i * 0.05) });
const step = (run: string, n: number, minAgo: number, summary_fa: string, actions: Array<[string, string, string?]>) =>
  ({ run_id: run, n, at: iso(minAgo), summary_fa, actions: actions.map(([tool, outcome, ref]) => ({ tool, outcome, ref: ref ?? null, class: null })) });
const runs: any[] = [
  { employee: 'FX-TECH-MGR', company: 'FX', work_ref: 'W-000104', state: 'running', trigger: 'work', reason: 'کار تازه از مدیرعامل', model: 'claude-sonnet-5-5', at: 6, tokens: tok(48_200, 3_900), usd: '0.41',
    steps: [['کار را پذیرفت و brief را خواند', [['work.accept', 'ok', 'W-000104']]], ['زمان پاسخ ثبت‌نام را از پایش سایت خواند', [['health.sites', 'ok']]], ['جلسه‌ی کد S-0004 را بررسی میکند', [['workshop.read', 'ok', 'S-0004']]]] },
  { employee: 'TY-GROWTH-01', company: 'TY', work_ref: 'W-000102', state: 'done', trigger: 'schedule', reason: 'بررسی هفتگی سئو', model: 'claude-haiku-5-5', at: 75, tokens: tok(91_000, 8_400), usd: '0.22',
    steps: [['۴۰ صفحه را از نقشه‌ی سایت برداشت', [['web.read', 'ok']]], ['۷ صفحه‌ی بیرون از ایندکس پیدا کرد', [['web.read', 'ok'], ['memory.write', 'ok']]], ['گزارش را تحویل داد', [['deliver', 'ok', 'O-000031']]]] },
  { employee: 'FX-QUANT-02', company: 'FX', work_ref: 'W-000096', state: 'failed', trigger: 'work', reason: 'تحلیل افت دقت', model: 'claude-haiku-5-5', at: 140, tokens: tok(22_000, 1_100), usd: '0.05', error: 'tool_refused',
    steps: [['داده‌ی سیگنال ۷ روزه را خواست', [['knowledge.search', 'ok']]], ['خواست مستقیم به دیتابیس FX وصل شود', [['http.request', 'refused']]]] },
  { employee: 'FX-QUANT-02', company: 'FX', work_ref: 'W-000096', state: 'done', trigger: 'retry', reason: 'تلاش دوباره با داده‌ی خزانه‌ی دانش', model: 'claude-haiku-5-5', at: 120, tokens: tok(64_000, 6_200), usd: '0.16',
    steps: [['داده‌ی ۷ روزه را از دانشنامه خواند', [['knowledge.search', 'ok']]], ['تحلیل افت دقت را نوشت و تحویل داد', [['deliver', 'ok', 'O-000029']]]] },
  { employee: 'HQ-ADV', company: 'HQ', work_ref: null, state: 'done', trigger: 'message', reason: 'پرسش مالک در رشته‌ی A', model: 'claude-opus-5-5', at: 26, tokens: tok(35_100, 2_400), usd: '0.64',
    steps: [['تصمیم‌های منتظر و حادثه‌های تریدیار را خواند', [['knowledge.search', 'ok'], ['health.sites', 'ok']]], ['جواب داد', [['message.thread', 'ok', 'A-0004']]]] },
  { employee: 'HQ-OVR', company: 'HQ', work_ref: null, state: 'running', trigger: 'schedule', reason: 'پروتکل PR-001', model: 'claude-opus-5-5', at: 4, tokens: tok(18_400, 900), usd: '0.31',
    steps: [['۵ خروجی دیروز تریدیار را نمونه برداشت', [['knowledge.search', 'ok']]]] },
  { employee: 'PC-TECH-MGR', company: 'PC', work_ref: null, state: 'refused', trigger: 'work', reason: 'تغییر پیکربندی ترمینال', model: 'claude-sonnet-5-5', at: 300, tokens: tok(9_000, 300), usd: '0.03', error: 'company_locked',
    steps: [['خواست پیکربندی production را تغییر دهد', [['deploy.config', 'refused']]]] },
  { employee: 'TY-TECH-MGR', company: 'TY', work_ref: null, state: 'failed', trigger: 'incident', reason: 'حادثه‌ی I-0005', model: 'claude-sonnet-5-5', at: 60 * 26, tokens: tok(30_000, 1_800), usd: '0.12', error: 'budget_exceeded',
    steps: [['لاگ حادثه را خواند', [['health.sites', 'ok']]], ['بودجه‌ی کار تمام شد', [['runs.reserve', 'refused']]]] },
  { employee: 'TY-GROWTH-01', company: 'TY', work_ref: null, state: 'queued', trigger: 'schedule', reason: 'خلاصه‌ی سلامت سایت', model: 'claude-haiku-5-5', at: 1, tokens: tok(0, 0), usd: '0.00', steps: [] },
].map((r, i) => {
  const id = `run-${i}`;
  return {
    id, employee: r.employee, company: r.company, work_ref: r.work_ref, thread: r.employee === 'HQ-ADV' ? 'A' : null, state: r.state, trigger: r.trigger, reason: r.reason,
    priority: r.state === 'running' ? 'P1' : 'P3', model: r.model, effort: 'high', charter: r.employee.replace(/^[A-Z]+-/, '').toLowerCase(), charter_version: 3,
    queued_at: iso(r.at + 1), started_at: r.state === 'queued' ? null : iso(r.at), finished_at: ['running', 'queued'].includes(r.state) ? null : iso(r.at - 3),
    steps: r.steps.length, tool_calls: r.steps.reduce((n, s) => n + (s[1] as unknown[]).length, 0), tokens: r.tokens, cost_usd: '0.00', equiv_cost_usd: r.usd,
    error_code: (r as { error?: string }).error ?? null, partial: false,
    steps_detail: r.steps.map((s, n) => step(id, n + 1, r.at - n, s[0] as string, s[1] as Array<[string, string, string?]>)),
  };
});
const runOut = ({ steps_detail: _s, ...r }: any) => r;

// --------------------------------------------------------------- treasury --
const MODELS = ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'];
const PRICE: Record<string, [number, number]> = { 'claude-opus-5-5': [15, 75], 'claude-sonnet-5-5': [3, 15], 'claude-haiku-5-5': [1, 5] };
const ACTORS = [['FX-TECH-MGR', 'FX', 'TECH'], ['TY-GROWTH-01', 'TY', 'GROWTH'], ['HQ-ADV', 'HQ', null], ['FX-QUANT-02', 'FX', 'QUANT'], ['HQ-OVR', 'HQ', 'OVS'], ['TY-TECH-MGR', 'TY', 'TECH']] as const;
const calls = Array.from({ length: 140 }, (_, i) => {
  const [actor, company, department] = ACTORS[i % ACTORS.length]!;
  const model = actor === 'HQ-ADV' || actor === 'HQ-OVR' ? MODELS[0]! : actor.endsWith('-MGR') ? MODELS[1]! : MODELS[2]!;
  const input = 2_000 + ((i * 7_919) % 28_000);
  const output = 200 + ((i * 3_331) % 3_000);
  const [pi, po] = PRICE[model]!;
  const status = i % 23 === 7 ? 'error' : i % 31 === 5 ? 'refused' : 'ok';
  return {
    id: `call-${i}`, started_at: iso(i * 9 + 2), finished_at: iso(i * 9), caller: 'claude-runtime', actor, company, department, work_ref: i % 3 ? `W-0001${String(i % 10).padStart(2, '0')}` : null,
    task_class: ['analysis', 'summary', 'code_review', 'advice'][i % 4], priority: 2 + (i % 3), connection: 'claude-max', model, effort: 'high', status,
    error_class: status === 'error' ? 'overloaded' : null, input_tokens: input, output_tokens: output, cache_read_tokens: Math.round(input * 0.35), cache_write_tokens: Math.round(input * 0.04), thinking_tokens: 0,
    latency_ms: 900 + ((i * 577) % 9_000), cost_usd: '0.00', equiv_cost_usd: ((input * pi + output * po) / 1e6).toFixed(4),
  };
});
const quota = { subscription: { status: 'ok', window: '5h', resets_at: ahead(140), source: 'rate-limit headers', utilization: '0.42', connection: 'claude-max', changed_at: iso(35) }, throttle: { paused_priorities: [] as string[] } };

// -------------------------------------------------------------------- ops --
const site = (company: string, url: string, kind: string, extra: Record<string, unknown> = {}) => ({
  id: `site-${company}-${url}`, company, url, kind, method: 'GET', expect: { status: [200, 301] }, interval_s: 60, enabled: true, canary: false, consecutive_failures: 0,
  last: { at: iso(1), status: 200, ms: 240, ok: true }, uptime_24h: 1, version: 1, ...extra,
});
const sites: any[] = [
  site('TY', 'https://tradeyar.trade-future.ir', 'web', { uptime_24h: 0.998 }),
  site('TY', 'https://user.tradeyar.trade-future.ir', 'web', { uptime_24h: 0.962, consecutive_failures: 0, last: { at: iso(1), status: 200, ms: 1_840, ok: true } }),
  site('FX', 'https://coineprofx.com', 'web', { uptime_24h: 1 }),
  site('FX', 'https://fx.trade-future.ir', 'web', { uptime_24h: 1, last: { at: iso(1), status: 301, ms: 180, ok: true } }),
  site('FX', 'https://api.coineprofx.com/health', 'api', { uptime_24h: 0.999 }),
  site('PC', 'https://coinepro.com', 'web', { uptime_24h: 1 }),
  site('PC', 'https://terminal.coinepro.com', 'web', { uptime_24h: 0, consecutive_failures: 1440, last: { at: iso(1), status: null, ms: null, ok: false, error: 'dns: no such host' } }),
  site('HQ', 'https://hq.coinepro.com/api/v1/health', 'api', { canary: true, uptime_24h: 1 }),
];
const incidents: any[] = [
  { ref: 'I-0007', company: 'PC', url: 'https://terminal.coinepro.com', severity: 'high', opened_at: iso(60 * 24 * 3), closed_at: null, checks_failed: 4_320, last_status: null, last_error: 'dns: no such host', work_ref: null },
  { ref: 'I-0005', company: 'TY', url: 'https://user.tradeyar.trade-future.ir', severity: 'medium', opened_at: iso(60 * 27), closed_at: iso(60 * 25), checks_failed: 6, last_status: 504, last_error: 'timeout after 10s', work_ref: 'W-000101' },
  { ref: 'I-0002', company: 'TY', url: 'https://user.tradeyar.trade-future.ir', severity: 'medium', opened_at: iso(60 * 24 * 5), closed_at: iso(60 * 24 * 5 - 40), checks_failed: 9, last_status: 502, last_error: 'bad gateway', work_ref: null },
].map((x, i) => ({ id: `inc-${i}`, ...x }));

// --------------------------------------------------------------- planner --
/** The planner as a view over work (§4): one row per day in [from, to], items filtered by scope. */
function planner(scope: string, from: string, to: string, work: any[]) {
  const [kind, ref] = scope.includes(':') ? scope.split(':') : ['owner', ''];
  const days: any[] = [];
  for (let d = new Date(`${from}T00:00:00Z`); d <= new Date(`${to}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + 1)) {
    const key = d.toISOString().slice(0, 10);
    const n = Math.round((d.getTime() - now) / 86_400_000);
    const at = (h: number) => { const x = new Date(d); x.setUTCHours(h, 30, 0, 0); return x.toISOString(); };
    const items = [
      { ref: `W-1${String(Math.abs(n)).padStart(2, '0')}0`, title: 'گزارش صبحگاهی', company: 'HQ', department: null, priority: 'P3', status: n < 0 ? 'done' : 'queued', at: at(4), assignee: 'HQ-SYS', recurring: true },
      n % 2 === 0 && { ref: `W-2${String(Math.abs(n)).padStart(2, '0')}0`, title: 'خلاصه‌ی سلامت سایت‌ها', company: ['TY', 'FX', 'PC'][Math.abs(n) % 3], department: 'TECH', priority: 'P3', status: n < 0 ? 'done' : 'queued', at: at(6), assignee: null, recurring: true },
      n % 7 === 5 && { ref: `W-3${String(Math.abs(n)).padStart(2, '0')}0`, title: 'گزارش هفتگی سئوی فنی', company: 'TY', department: 'GROWTH', priority: 'P3', status: n < 0 ? 'done' : 'queued', at: at(7), assignee: 'TY-GROWTH-01', recurring: true },
      ...work.filter((w) => w.due_at?.slice(0, 10) === key && !['cancelled'].includes(w.status)).map((w) => ({ ref: w.ref, title: w.title, company: w.company, department: w.department, priority: w.priority, status: w.status, at: w.due_at, assignee: w.assignee?.code ?? null, recurring: false })),
    ].filter(Boolean).filter((it: any) => kind === 'owner' || kind === 'holding' || (kind === 'company' && it.company === ref) || (kind === 'department' && `${it.company}-${it.department}` === ref));
    days.push({ date: key, items });
  }
  return { scope, timezone: 'Asia/Tehran', days };
}

// ------------------------------------------------------------------ router --
export async function handleOps(req: Request, p: string, u: URL, s: OpsState): Promise<Response | null> {
  const m = req.method;
  const body = async <T,>() => (await req.json().catch(() => ({}))) as T;
  const findWork = (id: string) => s.work.find((w) => w.id === id || w.ref === id);
  if (m === 'GET') {
    if (p === '/resolutions') {
      const q = (u.searchParams.get('q') ?? '').trim();
      const co = u.searchParams.get('company');
      return json(page(resolutions.filter((r) => (!co || r.company === co) && (!q || `${r.title} ${r.body} ${r.ref}`.includes(q)))));
    }
    const rd = /^\/resolutions\/(M-\d+)$/.exec(p); if (rd) { const r = resolutions.find((x) => x.ref === rd[1]); return r ? json(r) : problem(404, 'not_found', 'این مصوبه پیدا نشد.'); }
    if (p === '/notification-settings') return json(notify);
    if (p === '/search/messages') {
      const q = (u.searchParams.get('q') ?? '').trim();
      if (q.length < 2) return problem(422, 'validation_failed', 'دست‌کم دو حرف.');
      const thread = u.searchParams.get('thread');
      const hits = Object.entries(s.messages).filter(([t]) => !thread || t === thread).flatMap(([t, list]) => list.filter((x) => String(x.body ?? '').includes(q)).map((x, i) => ({ id: x.id, ref: x.ref, thread: t, author: x.author, body: x.body, kind: x.kind ?? 'text', attachments: x.attachments ?? [], links: x.links ?? {}, created_at: x.created_at, rank: 1 / (i + 1) })));
      return json(page(hits.sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 20)));
    }
    if (p === '/runs') {
      const emp = u.searchParams.get('employee'); const st = u.searchParams.get('state'); const co = u.searchParams.getAll('company');
      return json(page(runs.filter((r) => (!emp || r.employee === emp) && (!st || r.state === st) && (!co.length || co.includes(r.company))).map(runOut)));
    }
    const rn = /^\/runs\/([\w-]+)$/.exec(p); if (rn) { const r = runs.find((x) => x.id === rn[1]); return r ? json(r) : problem(404, 'not_found', 'این اجرا پیدا نشد.'); }
    const wr = /^\/work\/([^/]+)\/runs$/.exec(p); if (wr) { const w = findWork(wr[1]!); return json(runs.filter((r) => w && r.work_ref === w.ref)); }
    if (p === '/treasury/quota') return json(quota);
    if (p === '/treasury/what-if') {
      const model = u.searchParams.get('model') ?? MODELS[1]!;
      const [pi, po] = PRICE[model] ?? [0, 0];
      const actual = calls.reduce((n, c) => n + Number(c.equiv_cost_usd), 0);
      const what = calls.reduce((n, c) => n + (c.input_tokens * pi + c.output_tokens * po) / 1e6, 0);
      return json({ model, calls: calls.length, priced_calls: calls.length, actual_usd: actual.toFixed(2), what_if_usd: what.toFixed(2), difference_usd: (what - actual).toFixed(2), source_url: 'https://www.anthropic.com/pricing', as_of: '2026-10-01' });
    }
    if (p === '/treasury/calls') {
      const co = u.searchParams.get('company'); const actor = u.searchParams.get('actor'); const st = u.searchParams.get('status');
      const list = calls.filter((c) => (!co || c.company === co) && (!actor || c.actor === actor) && (!st || c.status === st));
      const at = Number(u.searchParams.get('cursor') ?? 0); const n = Number(u.searchParams.get('limit') ?? 50);
      return json(page(list.slice(at, at + n), at + n < list.length ? String(at + n) : null));
    }
    if (p === '/budgets') {
      const day = Object.keys(s.envelope).map((c) => ({ company: c, scope_type: 'company', scope_ref: c, period: 'day', level: 1, token_limit: null, tokens_used: Math.round((s.summary.totals.input_tokens + s.summary.totals.output_tokens) / 3), pct: null, usd_limit: null, usd_used: '0.90' }));
      const month = s.summary.budgets.map((b: any) => (b.scope_type === 'company' ? { ...b, token_limit: s.envelope[b.company] ?? b.token_limit } : b));
      return json([...month, ...day]);
    }
    if (p === '/ops/sites') { const co = u.searchParams.get('company'); return json(sites.filter((x) => !co || x.company === co)); }
    if (p === '/ops/incidents') { const co = u.searchParams.get('company'); const open = u.searchParams.get('open'); return json(incidents.filter((x) => (!co || x.company === co) && (open == null || (open === 'true') === !x.closed_at))); }
    if (p === '/planner') {
      const from = u.searchParams.get('from') ?? new Date(now).toISOString().slice(0, 10);
      const to = u.searchParams.get('to') ?? new Date(now + 6 * 86_400_000).toISOString().slice(0, 10);
      return json(planner(u.searchParams.get('scope') ?? 'owner', from, to, s.work));
    }
    return null;
  }
  if (p === '/resolutions' && m === 'POST') {
    const b = await body<{ title: string; body: string; source_message?: string | null }>();
    if (!b.title?.trim() || !b.body?.trim()) return problem(422, 'validation_failed', 'عنوان و متن لازم است.');
    const thread = b.source_message ? Object.entries(s.messages).find(([, list]) => list.some((x) => x.ref === b.source_message))?.[0] : undefined;
    const r = { id: `r${resolutions.length}`, ref: `M-${String(resolutions.length + 3 + 1).padStart(4, '0')}`, company: s.threads.find((t) => t.code === thread)?.company ?? null, title: b.title, body: b.body, source: b.source_message ? { message: b.source_message } : {}, sealed_by: owner, sealed_at: new Date().toISOString(), sent_to: [], follow_up_work_id: null };
    resolutions.unshift(r);
    return json(r, 201);
  }
  if (p === '/notification-settings' && m === 'PUT') {
    const v = Number((req.headers.get('If-Match') ?? '').replaceAll('"', ''));
    if (v !== notify.version) return problem(409, 'version_conflict', 'تنظیمات را جای دیگری عوض کرده‌ای؛ دوباره باز کن.');
    const b = await body<{ matrix: typeof notify.matrix }>();
    notify.matrix = b.matrix; notify.version += 1;
    return json(notify);
  }
  if (p === '/control/deploy-freeze' && m === 'POST') {
    const b = await body<{ company: string; until: string; reason: string }>();
    const co = s.companies.find((c) => c.code === b.company);
    if (!co) return problem(404, 'not_found', 'این شرکت پیدا نشد.');
    if (new Date(b.until).getTime() > Date.now()) {
      s.control.deploy_freezes = [...s.control.deploy_freezes.filter((f: any) => !(f.company === b.company && f.created_by === 'owner')), { company: b.company, until: b.until, reason: b.reason, created_by: 'owner' }];
      co.deploy_freeze_until = b.until;
    } else {
      s.control.deploy_freezes = s.control.deploy_freezes.filter((f: any) => f.company !== b.company);
      co.deploy_freeze_until = null;
    }
    return json({ company: b.company, active: !!co.deploy_freeze_until, until: b.until });
  }
  const wa = /^\/work\/([^/]+)\/(cancel|complete)$/.exec(p);
  if (wa && m === 'POST') {
    const w = findWork(wa[1]!);
    if (!w) return problem(404, 'not_found', 'این کار پیدا نشد.');
    if (['done', 'cancelled', 'failed'].includes(w.status)) return problem(409, 'validation_failed', 'این کار بسته است.');
    if (wa[2] === 'cancel') Object.assign(w, { status: 'cancelled', close_reason: (await body<{ reason: string }>()).reason, updated_at: new Date().toISOString(), version: w.version + 1 });
    else { const b = await body<{ evidence: unknown[] }>(); if (!b.evidence?.length) return problem(422, 'validation_failed', 'دست‌کم یک شاهد لازم است.'); Object.assign(w, { status: 'done', evidence: [...w.evidence, ...b.evidence], progress_pct: 100, updated_at: new Date().toISOString(), version: w.version + 1 }); }
    return json(w);
  }
  const we = /^\/work\/([^/]+)$/.exec(p);
  if (we && m === 'PATCH') {
    const w = findWork(we[1]!);
    if (!w) return problem(404, 'not_found', 'این کار پیدا نشد.');
    if (Number((req.headers.get('If-Match') ?? '').replaceAll('"', '')) !== w.version) return problem(409, 'version_conflict', 'این کار عوض شده؛ دوباره باز کن.');
    Object.assign(w, await body<Record<string, unknown>>(), { version: w.version + 1, updated_at: new Date().toISOString() });
    return json(w);
  }
  const ep = /^\/employees\/([A-Z0-9-]+)\/(pause|resume)$/.exec(p);
  if (ep && m === 'POST') {
    const e = s.employees.find((x) => x.code === ep[1]);
    if (!e) return problem(404, 'not_found', 'این کارمند پیدا نشد.');
    if (e.status === 'dismissed') return problem(409, 'validation_failed', 'این کارمند اخراج شده است.');
    e.status = ep[2] === 'pause' ? 'paused' : 'active';
    return json(e);
  }
  const ed = /^\/employees\/([A-Z0-9-]+)\/dismiss$/.exec(p);
  if (ed && m === 'POST') {
    const e = s.employees.find((x) => x.code === ed[1]);
    if (!e) return problem(404, 'not_found', 'این کارمند پیدا نشد.');
    const b = await body<{ reason: string; transfer_to?: string }>();
    const open = s.work.filter((w) => w.assignee?.code === e.code && !['done', 'cancelled', 'failed', 'delivered'].includes(w.status));
    Object.assign(e, { status: 'dismissed', dismissed_at: new Date().toISOString(), activity: 'sleeping' });
    return json({ employee: e, work_returned: open.length, transfer_work: `W-0002${s.work.length}`, reason: b.reason });
  }
  if (p === '/budgets' && m === 'PUT') {
    const b = await body<{ budgets: Array<{ company: string; scope_type: string; period: string; token_limit: number | null; usd_limit: string | null }> }>();
    for (const x of b.budgets) {
      if (x.scope_type === 'company' && x.period === 'month') s.envelope[x.company] = x.token_limit;
      const cur = s.summary.budgets.find((y: any) => y.scope_type === x.scope_type && y.company === x.company && (y.period ?? 'month') === x.period);
      if (cur) Object.assign(cur, { token_limit: x.token_limit, usd_limit: x.usd_limit ?? null, pct: x.token_limit ? Math.round((cur.tokens_used / x.token_limit) * 100) : null });
    }
    return json(b.budgets.map((x) => ({ ...x, scope_ref: x.company, level: x.scope_type === 'holding' ? 0 : 1, tokens_used: 0, usd_used: '0', pct: 0 })));
  }
  const cn = /^\/connections\/([\w-]+)(\/secret)?$/.exec(p);
  if (cn && (m === 'PATCH' || m === 'POST')) {
    const c = s.connections.find((x) => x.id === cn[1]);
    if (!c) return problem(404, 'not_found', 'این اتصال پیدا نشد.');
    if (cn[2]) { await body(); c.has_secret_ref = true; return json({ connection: c.key, stored: true }); }
    if (Number((req.headers.get('If-Match') ?? '').replaceAll('"', '')) !== c.version) return problem(409, 'version_conflict', 'این اتصال عوض شده؛ دوباره باز کن.');
    Object.assign(c, await body<Record<string, unknown>>(), { version: c.version + 1, updated_at: new Date().toISOString() });
    return json(c);
  }
  if (p === '/ops/sites' && m === 'PUT') {
    const b = await body<{ company: string; sites: Array<{ url: string; kind: string; method: string; interval_s: number; enabled: boolean }> }>();
    if (b.sites.some((x) => /localhost|127\.|10\.|192\.168\./.test(x.url))) return problem(422, 'validation_failed', 'نشانی داخلی یا خصوصی پایش نمیشود.');
    for (const x of sites) if (x.company === b.company && !x.canary && !b.sites.some((y) => y.url === x.url)) x.enabled = false;
    for (const y of b.sites) { const x = sites.find((z) => z.company === b.company && z.url === y.url); if (x) Object.assign(x, y, { version: x.version + 1 }); else sites.push(site(b.company, y.url, y.kind, { ...y, last: null, uptime_24h: null })); }
    return json(sites.filter((x) => x.company === b.company));
  }
  return null;
}
