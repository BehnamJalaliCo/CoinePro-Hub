// Development-only fixtures (npm run dev:mock) for contract §30 ⟨1.12⟩, production lines: two templates, TradeYar's reel line as a draft
// with a run waiting for the owner's seal, FX's article line already automatic, a done run with every kind of output, the voices, the
// library, and a week of calendar. Everything is kept in memory so the end-to-end checks can create a line, save a version, test a step,
// run dry, seal and upload. Never bundled in production (reached only through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

const json = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const needStepUp = () => problem(403, 'step_up_required', 'این کار تأیید با اثر انگشت یا چهره میخواهد.');
const OWNER = { kind: 'owner', code: 'OWNER', display_fa: 'مدیر کل' };
const NOW = () => new Date().toISOString();
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

const step = (key: string, kind: string, title_fa: string, o: Partial<Record<string, unknown>> = {}) => ({
  key, kind, title_fa, prompt_fa: null, settings: {}, inputs: [], gate: 'auto', optional: false, enabled: true, max_attempts: 1, timeout_s: 300, ...o,
});
const REEL_STEPS = () => [
  step('script', 'gpt_text', 'نوشتن سناریو', { prompt_fa: 'برای صفحه‌ی {{channel}} یک سناریوی ریلز ۳۰ ثانیه‌ای درباره‌ی {{topic}} بنویس. لحن گرم و ساده، در پایان یک دعوت به کار.', max_attempts: 2, timeout_s: 240 }),
  step('dedupe', 'dedupe', 'تکراری نبودن', { inputs: ['script'], max_attempts: 3 }),
  step('voice', 'tts', 'صدا', { inputs: ['script'], settings: { speaker: 'Kore', style: 'آرام و گرم' } }),
  step('direction', 'gpt_text', 'کارگردانی', { prompt_fa: 'برای این سناریو نما به نما کارگردانی بنویس: {{script}}', inputs: ['script'], optional: true }),
  step('patterns', 'pattern_search', 'الگوها', { inputs: ['script'], settings: { query: 'ریلز آموزشی', count: 5 }, optional: true }),
  step('pick', 'council_pick', 'انتخاب شورا', { inputs: ['patterns'] }),
  step('build', 'opus_build', 'ساخت نهایی', { prompt_fa: 'سناریو، صدا و الگوی برگزیده را به مشخصات ساخت، کپشن و هشتگ تبدیل کن.', inputs: ['script', 'voice', 'pick'], timeout_s: 600 }),
  step('render', 'render', 'ساخت ویدیو', { inputs: ['build'], settings: { where: 'studio' }, timeout_s: 900 }),
  step('cover', 'cover', 'کاور', { inputs: ['build'], settings: { folder: '' } }),
  step('quality', 'quality', 'بررسی کیفیت', { inputs: ['render', 'build'] }),
  step('publish', 'publish', 'انتشار ریلز', { inputs: ['render', 'cover', 'build'], gate: 'owner', settings: { when: 'schedule', where: '' } }),
];
const POST_STEPS = () => [
  step('text', 'gpt_text', 'نوشتن پست', { prompt_fa: 'یک پست کوتاه تلگرام درباره‌ی {{topic}} بنویس.' }),
  step('quality', 'quality', 'بررسی کیفیت', { inputs: ['text'] }),
  step('publish', 'publish', 'انتشار در تلگرام', { inputs: ['text'], gate: 'owner', settings: { when: 'asap' } }),
];
const TEMPLATES = [
  { key: 'instagram_reel', title_fa: 'ریلز اینستاگرام', platform: 'instagram_reel', version: 1, steps: REEL_STEPS(), defaults: { caps: { runs_per_day: 1, tokens_per_run: 120000, opus_per_day: 2 } }, outputs_fa: 'یک ریلز کامل با صدا، کاور و کپشن؛ بعد از انتشار، استوری همان روز.' },
  { key: 'telegram_post', title_fa: 'پست تلگرام', platform: 'telegram_post', version: 1, steps: POST_STEPS(), defaults: { caps: { runs_per_day: 3, tokens_per_run: 30000, opus_per_day: 0 } }, outputs_fa: 'یک پست متنی کوتاه برای کانال.' },
];
const CAPS = { runs_per_day: 1, tokens_per_run: 120000, opus_per_day: 2 };

const lines: any[] = [
  { ref: 'LN-0001', company: 'TY', template: 'instagram_reel', template_version: 1, platform: 'instagram_reel', channel: { kind: 'instagram', subject: 'tradeyar.ir' }, title_fa: 'ریلز آموزشی تریدیار',
    schedule: 'FREQ=DAILY;BYHOUR=18;BYMINUTE=0', state: 'on', mode: 'draft', good_runs: 3, auto_after: 7, caps: { ...CAPS }, version: 2, steps: REEL_STEPS(), library: [],
    created_at: '2026-11-03T05:00:00Z', updated_at: '2026-11-03T09:00:00Z', next_run_at: '2026-11-04T14:30:00Z', last_run: { ref: 'LR-000001', state: 'waiting', at: '2026-11-03T14:30:00Z' } },
  { ref: 'LN-0002', company: 'FX', template: 'telegram_post', template_version: 1, platform: 'telegram_post', channel: { kind: 'telegram', subject: '@coinepro_fx' }, title_fa: 'پست روزانه‌ی کانال FX',
    schedule: 'FREQ=DAILY;BYHOUR=9;BYMINUTE=0', state: 'on', mode: 'auto', good_runs: 9, auto_after: 7, caps: { runs_per_day: 3, tokens_per_run: 30000, opus_per_day: 0 }, version: 1, steps: POST_STEPS(), library: [],
    created_at: '2026-10-28T05:00:00Z', updated_at: '2026-10-28T05:00:00Z', next_run_at: '2026-11-05T05:30:00Z', last_run: { ref: 'LR-000002', state: 'done', at: '2026-11-03T05:30:00Z' } },
];
const versions: Record<string, any[]> = {
  'LN-0001': [
    { line: 'LN-0001', version: 1, body: null, by: OWNER, at: '2026-11-03T05:00:00Z', note_fa: 'ساخته شد از الگو' },
    { line: 'LN-0001', version: 2, body: null, by: OWNER, at: '2026-11-03T09:00:00Z', note_fa: 'لحن گرم‌تر' },
  ],
  'LN-0002': [{ line: 'LN-0002', version: 1, body: null, by: OWNER, at: '2026-10-28T05:00:00Z', note_fa: null }],
};
const stamp = (l: any) => { for (const v of versions[l.ref] ?? []) if (!v.body) v.body = clone({ ...l, version: v.version }); };
lines.forEach(stamp);

const out = (o: Partial<Record<string, unknown>> = {}) => ({ text: null, file_id: null, files: [], data: {}, ...o });
const sr = (key: string, kind: string, state: string, at: string, end: string | null, output: any, extra: Partial<Record<string, unknown>> = {}) => ({
  key, kind, state, attempt: 1, started_at: at, ended_at: end, output, via: null, tokens: 0, usd_equiv: 0, error_fa: null, ...extra,
});
const runs: any[] = [
  { ref: 'LR-000001', line: 'LN-0001', line_version: 2, trigger: 'schedule', dry: false, state: 'waiting', at: '2026-11-03T14:30:00Z', ended_at: null,
    steps: [
      sr('script', 'gpt_text', 'done', '2026-11-03T14:30:00Z', '2026-11-03T14:31:10Z', out({ text: '## سناریوی ریلز\n\nنمای اول: یک معامله‌گر خسته جلوی نمودار.\n\n- نما ۲: خط حد ضرر روی نمودار\n- نما ۳: دعوت به یادگیری' }), { via: 'chatgpt', tokens: 2400, usd_equiv: 0.02 }),
      sr('dedupe', 'dedupe', 'done', '2026-11-03T14:31:10Z', '2026-11-03T14:31:12Z', out({ data: { similarity: 0.12, closest: 'LR-000000', verdict: 'متفاوت' } })),
      sr('voice', 'tts', 'done', '2026-11-03T14:31:12Z', '2026-11-03T14:32:00Z', out({ file_id: '/demo/fx-reel-levels-voice.m4a' }), { via: 'aistudio-web' }),
      sr('render', 'render', 'done', '2026-11-03T14:32:00Z', '2026-11-03T14:36:00Z', out({ file_id: '/demo/fx-reel-levels.mp4' }), { via: 'studio' }),
      sr('cover', 'cover', 'done', '2026-11-03T14:36:00Z', '2026-11-03T14:37:00Z', out({ file_id: '/demo/fx-reel-levels-poster.webp' }), { via: 'chatgpt' }),
      sr('quality', 'quality', 'done', '2026-11-03T14:37:00Z', '2026-11-03T14:37:01Z', out({ data: { repeat: false, sources: 'ok', length: 'ok', banned_words: 0 } })),
      sr('publish', 'publish', 'waiting', '2026-11-03T14:37:01Z', null, out()),
    ], cost: { tokens: 18200, usd_equiv: 0.31 }, published: [], metrics: { h24: null, d7: null }, note_fa: 'منتظر مُهر تو برای انتشار.' },
  { ref: 'LR-000002', line: 'LN-0002', line_version: 1, trigger: 'schedule', dry: false, state: 'done', at: '2026-11-03T05:30:00Z', ended_at: '2026-11-03T05:32:00Z',
    steps: [
      sr('text', 'gpt_text', 'done', '2026-11-03T05:30:00Z', '2026-11-03T05:31:00Z', out({ text: 'سطح‌های امروز بازار را با یک نمودار ساده ببینید.' }), { via: 'chatgpt', tokens: 900, usd_equiv: 0.01 }),
      sr('quality', 'quality', 'done', '2026-11-03T05:31:00Z', '2026-11-03T05:31:01Z', out({ data: { repeat: false } })),
      sr('publish', 'publish', 'done', '2026-11-03T05:31:01Z', '2026-11-03T05:32:00Z', out({ data: { external_id: 'tg-1042' } })),
    ], cost: { tokens: 900, usd_equiv: 0.01 }, published: [{ platform: 'telegram_post', kind: 'post', external_id: 'tg-1042', at: '2026-11-03T05:32:00Z', url: null }],
    metrics: { h24: { views: 1830, reactions: 41 }, d7: null }, note_fa: null },
];
const VOICES = [
  { name: 'Kore', title_fa: 'کوره', gender: 'female', sample_file: '/demo/fx-reel-levels-voice.m4a' },
  { name: 'Charon', title_fa: 'شارون', gender: 'male', sample_file: '/demo/fx-reel-resist-voice.m4a' },
  { name: 'Puck', title_fa: 'پاک', gender: 'male', sample_file: null },
];
const assets: any[] = [
  { id: 'AS-1', company: 'TY', kind: 'cover_folder', title_fa: 'کاورهای تریدیار', config: {}, files: ['/demo/ty-story-stoploss-poster.webp', '/demo/pc-landing-redesign.webp'], created_at: '2026-11-02T05:00:00Z' },
  { id: 'AS-2', company: null, kind: 'voice', title_fa: 'صدای گرم', config: {}, files: ['/demo/fx-reel-levels-voice.m4a'], created_at: '2026-11-02T05:10:00Z' },
  { id: 'AS-3', company: 'FX', kind: 'prompt', title_fa: 'لحن کانال FX', config: { text: 'کوتاه، بدون وعده‌ی سود، همیشه با منبع عدد.' }, files: [], created_at: '2026-11-02T05:20:00Z' },
  { id: 'AS-4', company: null, kind: 'pattern', title_fa: 'الگوهای آموزشی', config: { query: 'آموزش معامله‌گری ریلز' }, files: [], created_at: '2026-11-02T05:30:00Z' },
];

let nl = 3, nr = 3, na = 5;
const pad = (n: number, w: number) => String(n).padStart(w, '0');
const addDays = (d: string, n: number) => new Date(Date.parse(`${d}T12:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10);

export async function handle30(req: Request, p: string, q: URLSearchParams): Promise<Response | null> {
  const m = req.method;
  if (!/^\/(line-templates|lines|line-runs|calendar\/lines|library|tts\/voices|companies\/[^/]+\/lines)/.test(p)) return null;
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;
  const stepUp = req.headers.get('X-Step-Up');

  if (p === '/line-templates' && m === 'GET') return json(TEMPLATES);
  const tk = /^\/line-templates\/([^/]+)$/.exec(p);
  if (tk && m === 'GET') { const t = TEMPLATES.find((x) => x.key === tk[1]); return t ? json(t) : problem(404, 'not_found', 'این الگو پیدا نشد.'); }

  const cl = /^\/companies\/([^/]+)\/lines$/.exec(p);
  if (cl && m === 'GET') return json(lines.filter((l) => l.company === cl[1]));
  if (cl && m === 'POST') {
    const b = await body<{ template: string; platform: string; channel: any; title_fa: string }>();
    const t = TEMPLATES.find((x) => x.key === b.template);
    if (!t || !b.title_fa?.trim()) return problem(422, 'validation_failed', 'الگو و نام خط لازم است.');
    const l = { ref: `LN-${pad(nl++, 4)}`, company: cl[1], template: t.key, template_version: t.version, platform: b.platform, channel: b.channel, title_fa: b.title_fa, schedule: null, state: 'draft', mode: 'draft',
      good_runs: 0, auto_after: 7, caps: { ...(t.defaults as any).caps }, version: 1, steps: clone(t.steps), library: [], created_at: NOW(), updated_at: NOW(), next_run_at: null, last_run: null };
    lines.push(l); versions[l.ref] = [{ line: l.ref, version: 1, body: null, by: OWNER, at: NOW(), note_fa: 'ساخته شد از الگو' }]; stamp(l);
    return json(l, 201);
  }

  const ln = /^\/lines\/([^/]+)$/.exec(p);
  const find = (ref: string) => lines.find((l) => l.ref === ref);
  if (ln && m === 'GET') { const l = find(ln[1]!); return l ? json(l) : problem(404, 'not_found', 'این خط پیدا نشد.'); }
  if (ln && m === 'PUT') {
    const l = find(ln[1]!);
    if (!l) return problem(404, 'not_found', 'این خط پیدا نشد.');
    const b = await body<any>();
    if (b.caps && (b.caps.runs_per_day > l.caps.runs_per_day || b.caps.tokens_per_run > l.caps.tokens_per_run || b.caps.opus_per_day > l.caps.opus_per_day) && !stepUp) return needStepUp();
    for (const k of ['title_fa', 'schedule', 'steps', 'caps', 'library']) if (k in b) l[k] = b[k];
    l.version += 1; l.updated_at = NOW();
    versions[l.ref]!.push({ line: l.ref, version: l.version, body: null, by: OWNER, at: NOW(), note_fa: b.note_fa ?? null }); stamp(l);
    return json(l);
  }
  const lv = /^\/lines\/([^/]+)\/(state|mode|versions|revert|copy|runs)$/.exec(p);
  if (lv) {
    const l = find(lv[1]!);
    if (!l) return problem(404, 'not_found', 'این خط پیدا نشد.');
    if (lv[2] === 'versions' && m === 'GET') return json(versions[l.ref]);
    if (lv[2] === 'runs' && m === 'GET') return json(runs.filter((r) => r.line === l.ref).sort((a, b) => b.at.localeCompare(a.at)));
    if (m !== 'POST') return null;
    const b = await body<any>();
    if (lv[2] === 'state') { l.state = b.state; return json(l); }
    if (lv[2] === 'mode') {
      if (b.mode === 'auto' && !stepUp) return needStepUp();
      if (b.mode === 'auto' && l.good_runs < l.auto_after) return problem(409, 'conflict', 'هنوز اجرای خوب کافی نیست.');
      l.mode = b.mode; return json(l);
    }
    if (lv[2] === 'revert') {
      const v = versions[l.ref]!.find((x) => x.version === b.version);
      if (!v) return problem(404, 'not_found', 'این نسخه پیدا نشد.');
      Object.assign(l, clone({ ...v.body, version: l.version + 1, state: l.state, mode: l.mode, good_runs: l.good_runs }));
      versions[l.ref]!.push({ line: l.ref, version: l.version, body: null, by: OWNER, at: NOW(), note_fa: `برگشت به نسخه‌ی ${b.version}` }); stamp(l);
      return json(l);
    }
    if (lv[2] === 'copy') {
      const c = { ...clone(l), ref: `LN-${pad(nl++, 4)}`, company: b.company, state: 'draft', mode: 'draft', good_runs: 0, version: 1, channel: { ...l.channel, subject: '' }, created_at: NOW(), updated_at: NOW(), next_run_at: null, last_run: null };
      lines.push(c); versions[c.ref] = [{ line: c.ref, version: 1, body: null, by: OWNER, at: NOW(), note_fa: `کپی از ${l.ref}` }]; stamp(c);
      return json(c, 201);
    }
    if (lv[2] === 'runs') {
      const steps = l.steps.filter((s: any) => s.enabled).map((s: any) => sr(s.key, s.kind, b.dry && (s.kind === 'publish' || s.kind === 'deliver') ? 'skipped' : 'done', NOW(), NOW(),
        s.kind === 'gpt_text' ? out({ text: `خروجی آزمایشی «${s.title_fa}»` }) : out({ data: { dry: true } })));
      const r = { ref: `LR-${pad(nr++, 6)}`, line: l.ref, line_version: l.version, trigger: b.dry ? 'test' : 'owner', dry: !!b.dry, state: 'done', at: NOW(), ended_at: NOW(), steps, cost: { tokens: 3200, usd_equiv: 0.05 }, published: [], metrics: { h24: null, d7: null }, note_fa: b.dry ? 'آزمایشی: انتشار و تحویل انجام نشد.' : null };
      runs.push(r);
      return json(r, 201);
    }
  }
  const st = /^\/lines\/([^/]+)\/steps\/([^/]+)\/test$/.exec(p);
  if (st && m === 'POST') {
    const l = find(st[1]!);
    const s = l?.steps.find((x: any) => x.key === st[2]);
    if (!s) return problem(404, 'not_found', 'این قدم پیدا نشد.');
    return json(sr(s.key, s.kind, 'done', NOW(), NOW(), s.kind === 'gpt_text' ? out({ text: `**آزمایش «${s.title_fa}»**\n\nجواب نمونه برای دستور ذخیره‌شده.` }) : out({ data: { ok: true, kind: s.kind } }), { tokens: 800 }));
  }

  const lr = /^\/line-runs\/([^/]+)(?:\/(rerun|seal|cancel))?$/.exec(p);
  if (lr) {
    const r = runs.find((x) => x.ref === lr[1]);
    if (!r) return problem(404, 'not_found', 'این اجرا پیدا نشد.');
    if (!lr[2] && m === 'GET') return json(r);
    if (m !== 'POST') return null;
    const b = await body<any>();
    if (lr[2] === 'seal') {
      if (!stepUp) return needStepUp();
      if (r.state !== 'waiting') return problem(409, 'conflict', 'این اجرا منتظر مُهر نیست.');
      const pub = r.steps.find((s: any) => s.state === 'waiting');
      if (b.approve) {
        pub.state = 'done'; pub.ended_at = NOW(); r.state = 'done'; r.ended_at = NOW();
        r.published.push({ platform: 'instagram_reel', kind: 'reel', external_id: 'ig-77', at: NOW(), url: null });
        const l = find(r.line); if (l) l.good_runs += 1;
        r.note_fa = null;
      } else { pub.state = 'skipped'; r.state = 'cancelled'; r.ended_at = NOW(); r.note_fa = 'مالک رد کرد.'; }
      return json(r);
    }
    if (lr[2] === 'cancel') { r.state = 'cancelled'; return json(r); }
    if (lr[2] === 'rerun') {
      const i = r.steps.findIndex((s: any) => s.key === b.from_step);
      for (const s of r.steps.slice(Math.max(0, i))) { s.state = 'done'; s.attempt += 1; }
      return json(r);
    }
  }

  if (p === '/calendar/lines' && m === 'GET') {
    const from = q.get('from') ?? NOW().slice(0, 10), to = q.get('to') ?? addDays(from, 6), company = q.get('company');
    const days: any[] = [];
    for (let d = from; d <= to; d = addDays(d, 1)) {
      const items = lines.filter((l) => l.schedule && l.state !== 'paused' && (!company || l.company === company)).map((l) => {
        const h = /BYHOUR=(\d+)/.exec(l.schedule)?.[1] ?? '9';
        return { line: l.ref, company: l.company, platform: l.platform, at: `${d}T${pad(Number(h) - 4, 2)}:30:00Z`, state: l.state, run: null, title_fa: l.title_fa };
      });
      days.push({ day: d, items });
    }
    return json({ days });
  }

  if (p === '/tts/voices' && m === 'GET') return json(VOICES);

  if (p === '/library' && m === 'GET') {
    const c = q.get('company'), k = q.get('kind');
    return json(assets.filter((a) => (!c || a.company === c || a.company === null) && (!k || a.kind === k)));
  }
  if (p === '/library' && m === 'POST') {
    const b = await body<{ meta: any; files: string[] }>();
    if (!b.meta?.title_fa?.trim()) return problem(422, 'validation_failed', 'نام لازم است.');
    const a = { id: `AS-${na++}`, company: b.meta.company ?? null, kind: b.meta.kind, title_fa: b.meta.title_fa, config: b.meta.config ?? {}, files: (b.files ?? []).map(() => '/demo/pc-landing-redesign.webp'), created_at: NOW() };
    assets.push(a);
    return json(a, 201);
  }
  const la = /^\/library\/([^/]+)$/.exec(p);
  if (la) {
    const i = assets.findIndex((a) => a.id === la[1]);
    if (i < 0) return problem(404, 'not_found', 'این مورد پیدا نشد.');
    if (m === 'PUT') { const b = await body<any>(); if (b.title_fa) assets[i].title_fa = b.title_fa; if (b.config) assets[i].config = b.config; return json(assets[i]); }
    if (m === 'DELETE') { assets.splice(i, 1); return json(null, 204); }
  }
  return null;
}
