// Development-only fixtures (npm run dev:mock) for contract §31 ⟨1.13⟩: the insights of TradeYar's reel line, two kits, a newsletter with one
// list and a draft, keywords with a month of ranks, competitors with figures, a campaign calendar with a conflict, an ad account with a
// campaign paused by a rule, and two automations. Kept in memory so the end-to-end checks can add, edit, seal and resume. Never bundled in
// production (reached only through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

const json = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const needStepUp = () => problem(403, 'step_up_required', 'این کار تأیید با اثر انگشت یا چهره میخواهد.');
const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (d: string, n: number) => iso(new Date(Date.parse(`${d}T12:00:00Z`) + n * 86_400_000));
const today = () => iso(new Date());
const lastDays = (n: number) => Array.from({ length: n }, (_, i) => addDays(today(), i - n + 1));

// The hub's shapes (OpenAPI KitSummary, NewsletterOut, CampaignCalendar, Ads, AutomationDetail), so the end-to-end checks test them.
const todo = (cs: Array<{ label_fa: string }>) => cs.map((c) => `اتصال ${c.label_fa} را وصل کن`);
const kit = (k: any) => ({ ...k, todo_fa: todo(k.connections) });
const KITS = [
  kit({ key: 'media_company', title_fa: 'شرکت رسانه‌ای', purpose_fa: 'یک شرکت با تیم محتوا، کارگروه تولید و انتشار و خط ریلز و تلگرام.', team_template: 'media', team: { departments: [{ code: 'content', name_fa: 'محتوا' }], positions: 2 },
    groups: [{ key: 'content', title_fa: 'تولید و انتشار' }],
    lines: [{ template: 'instagram_reel', platform: 'instagram_reel', title_fa: 'ریلز آموزشی', ref: null, why_fa: null }, { template: 'telegram_post', platform: 'telegram_post', title_fa: 'پست روزانه‌ی کانال', ref: null, why_fa: null }],
    kpis: [{ key: 'reach', name_fa: 'دسترسی', card: 'growth', manual: false }, { key: 'followers', name_fa: 'دنبال‌کننده', card: 'growth', manual: false }],
    connections: [{ kind: 'instagram', label_fa: 'اینستاگرام' }, { kind: 'telegram', label_fa: 'تلگرام' }] }),
  kit({ key: 'seo_site', title_fa: 'سایت سئو‌محور', purpose_fa: 'یک شرکت با تیم سئو و خط مقاله‌ی سایت و خبرنامه.', team_template: 'seo', team: { departments: [{ code: 'seo', name_fa: 'سئو' }], positions: 2 },
    groups: [{ key: 'content', title_fa: 'تولید و انتشار' }],
    lines: [{ template: 'site_article', platform: 'site_article', title_fa: 'مقاله‌ی هفتگی', ref: null, why_fa: null }], kpis: [{ key: 'clicks', name_fa: 'کلیک', card: 'growth', manual: false }],
    connections: [{ kind: 'search_console', label_fa: 'سرچ‌کنسول' }, { kind: 'newsletter', label_fa: 'خبرنامه' }] }),
];
const nl = {
  company: 'TY', active: true, size_limit: 5000, note_fa: null,
  lists: [{ id: 'L1', listmonk_id: 3, name: 'مشترک‌های تریدیار', subscribers: 4120 }],
  campaigns: [
    { id: 'NC1', company: 'TY', listmonk_id: 11, list_id: 3, subject: 'سه اشتباه رایج در حد ضرر', state: 'finished', send_at: '2026-11-01T06:00:00Z', list_size: 4120, sent: 4010, opens: 1620, clicks: 310, bounces: 4, created_at: '2026-10-30T06:00:00Z' },
    { id: 'NC2', company: 'TY', listmonk_id: 12, list_id: 3, subject: 'برنامه‌ی هفته‌ی بازار', state: 'draft', send_at: null, list_size: 4120, sent: null, opens: null, clicks: null, bounces: null, created_at: '2026-11-02T06:00:00Z' },
  ] as any[],
};
/** The PUT models forbid extra keys (422), as the hub's do. */
const EDITABLE: Record<string, string[]> = {
  keywords: ['phrase', 'site', 'target_url', 'state'], competitors: ['name_fa', 'site', 'instagram', 'youtube', 'telegram', 'state'],
  'ad-rules': ['scope', 'daily_cap', 'window_days', 'min_roas', 'min_spend_before_judging', 'action', 'state', 'note_fa'],
  campaigns: ['title_fa', 'goal_fa', 'starts', 'ends', 'channels', 'budget', 'state'],
};
const extra = (what: string, b: Record<string, unknown>) => Object.keys(b).filter((k) => !EDITABLE[what]!.includes(k));
const forbidden = (keys: string[]) => problem(422, 'validation_failed', `فیلدهای اضافه پذیرفته نمیشود: ${keys.join(', ')}`);
const keywords: any[] = [
  { id: 'K1', company: 'TY', phrase: 'آموزش حد ضرر', site: 'tradeyar.ir', target_url: null, state: 'on' },
  { id: 'K2', company: 'TY', phrase: 'سیگنال فارکس', site: 'tradeyar.ir', target_url: null, state: 'on' },
];
const ranks = () => lastDays(14).flatMap((day, i) => keywords.flatMap((k, j) => [{ keyword: k.id, day, source: 'search_console', position: 14 - i * 0.4 + j * 6, url: null }]));
const competitors: any[] = [{ id: 'C1', company: 'TY', name_fa: 'مرجع معامله', site: 'marjae.example', instagram: 'marjae', youtube: null, telegram: null, state: 'on' }];
const compDaily = () => lastDays(7).flatMap((day, i) => [{ competitor: 'C1', day, key: 'followers', value: 12000 + i * 40, source: 'instagram' }, { competitor: 'C1', day, key: 'new_pages', value: i % 3, source: 'sitemap' }]);
const campaigns: any[] = [{ id: 'CP1', company: 'TY', title_fa: 'هفته‌ی آموزش حد ضرر', goal_fa: 'هزار مشترک تازه', starts: today(), ends: addDays(today(), 7), channels: ['instagram_reel', 'telegram_post'], budget: 5000, state: 'planned' }];
const adCampaigns: any[] = [
  { platform: 'meta_ads', campaign_id: 'M1', name: 'ثبت‌نام آموزش', status: 'active', paused_by: null, paused_at: null, paused_reason_fa: null, totals: { spend: 820, clicks: 940, conversions: 31, revenue: 2100, roas: 2.56 }, days: [] },
  { platform: 'google_ads', campaign_id: 'G1', name: 'جست‌وجوی سیگنال', status: 'paused', paused_by: 'rule', paused_at: '2026-11-02T08:00:00Z', paused_reason_fa: 'بازده زیر کمترین ROAS', totals: { spend: 640, clicks: 410, conversions: 3, revenue: 210, roas: 0.33 }, days: [] },
];
const adRules: any[] = [{ id: 'R1', company: 'TY', platform: 'google_ads', scope: 'account', daily_cap: 100, window_days: 3, min_roas: 1, min_spend_before_judging: 200, action: 'pause', state: 'on', note_fa: null, summary_fa: '', created_at: '2026-11-01T06:00:00Z', updated_at: '2026-11-01T06:00:00Z' }];
const automations: any[] = [
  { ref: 'AT-0001', company: 'TY', sentence_fa: 'هر روز ساعت ۸ اگر بازدید دیروز کم شد به من خبر بده', rule: { trigger: { kind: 'schedule', rrule: 'FREQ=DAILY;BYHOUR=8' }, conditions: [], actions: [{ kind: 'notify.owner' }] }, state: 'on', runs: 3, last_run_at: '2026-11-03T04:30:00Z', n8n_workflow: null, preview_fa: 'هر روز ساعت ۸ بازدید دیروز را میسنجد و اگر کم شد به تو خبر میدهد.' },
  { ref: 'AT-0002', company: null, sentence_fa: 'اگر ارسال یک خط سه بار شکست خورد آن را متوقف کن', rule: { trigger: { kind: 'event', type: 'line_run.failed' }, conditions: [], actions: [{ kind: 'line.pause' }] }, state: 'off', runs: 0, last_run_at: null, n8n_workflow: null },
];
const kitOrder = { sealed: false };
let na = 3, nc = 3, nk = 3, nco = 2, nr = 2, ncp = 2;

export async function handle31(req: Request, p: string, q: URLSearchParams): Promise<Response | null> {
  const m = req.method;
  if (!/^\/(orders\/F-0099\/report|kits|companies\/[^/]+\/(newsletter|keywords|ranks|competitors|ads|ad-rules)|companies\/from-kit|newsletter\/|campaign-calendar|campaigns|ads\/|automations|lines\/[^/]+\/insights)/.test(p)) return null;
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;
  const stepUp = req.headers.get('X-Step-Up');

  if (p === '/orders/F-0099/report' && m === 'GET') {
    return json({ ref: 'F-0099', text_fa: 'یک شرکت تازه برای آموزش بساز', at: '2026-11-04T06:00:00Z', state: kitOrder.sealed ? 'delivered' : 'waiting', ack: null, route: null, steps: [], outputs: [], summary: null, updated_at: '2026-11-04T06:00:00Z',
      blockers: kitOrder.sealed ? [] : [{ kind: 'kit_unsealed', title_fa: 'ساخت شرکت منتظر مُهر توست', detail_fa: 'کد و نام را بنویس و مُهر بزن.', since: '2026-11-04T06:00:00Z', fix: { action: 'kit.create', label_fa: 'ساخت شرکت', target: 'media_company' } }],
      kit: { kit: 'media_company', title_fa: KITS[0]!.title_fa, name_fa: 'آموزش', sealed: kitOrder.sealed, summary: KITS[0] } });
  }
  if (p === '/kits' && m === 'GET') return json(KITS);
  if (p === '/companies/from-kit/preview' && m === 'POST') {
    const b = await body<any>(); const k = KITS.find((x) => x.key === b.kit);
    if (!k) return problem(404, 'not_found', 'این الگو پیدا نشد.');
    return json({ kit: k, code: b.code, name_fa: b.name_fa, name_en: b.name_en, code_free: b.code !== 'TY', problems: [], nothing_written: true });
  }
  if (p === '/companies/from-kit' && m === 'POST') {
    if (!stepUp) return needStepUp();
    const b = await body<any>(); const k = KITS.find((x) => x.key === b.kit);
    if (!k) return problem(404, 'not_found', 'این الگو پیدا نشد.');
    if (b.order === 'F-0099') kitOrder.sealed = true;
    return json({ company: { code: b.code, name_fa: b.name_fa }, kit: k.key, team: {}, groups: k.groups.map((g: any) => g.key), kpis: k.kpis.length, connections: k.connections.length,
      lines: k.lines.map((l: any, i: number) => ({ ...l, ref: `LN-0${100 + i}` })), lines_pending: [], groups_pending: [], todo_fa: k.todo_fa }, 201);
  }

  const ins = /^\/lines\/([^/]+)\/insights$/.exec(p);
  if (ins && m === 'GET') {
    if (ins[1] !== 'LN-0001') return problem(404, 'not_found', 'هنوز درسی نیست.');
    return json({ line: 'LN-0001', metric: 'views', window_runs: 12, updated_at: '2026-11-03T08:00:00Z', best: { hour: 18, length_bucket: '۲۵ تا ۳۵ ثانیه', voice: 'Kore', pattern_source: 'pinterest' },
      top_hooks: ['حد ضرر نذاری، بازار برات میذاره', 'این یک خط ساده سرمایه‌ات را نجات میدهد'], lessons_fa: ['ریلزهای ساعت ۱۸ حدود دو برابر بازدید گرفتند.', 'صدای زنانه‌ی آرام بهتر از سریع‌خوانی بود.'] });
  }

  if (p === '/companies/TY/newsletter' || /^\/companies\/[^/]+\/newsletter$/.test(p)) return m === 'GET' ? json(nl) : null;
  const nlc = /^\/companies\/[^/]+\/newsletter\/campaigns$/.exec(p);
  if (nlc && m === 'POST') {
    const b = await body<any>();
    if (!b.subject?.trim() || !b.body?.trim()) return problem(422, 'validation_failed', 'موضوع و متن ایمیل لازم است.');
    if (b.list_id != null && !nl.lists.some((l) => l.id === b.list_id)) return problem(422, 'validation_failed', 'این لیست مال این شرکت نیست.');
    const l = nl.lists.find((x) => x.id === b.list_id) ?? nl.lists[0]!;
    const c = { id: `NC${nc++}`, company: 'TY', listmonk_id: 20 + nc, list_id: l.listmonk_id, subject: b.subject, state: 'draft', send_at: null, list_size: l.subscribers, sent: null, opens: null, clicks: null, bounces: null, created_at: new Date().toISOString() };
    nl.campaigns.push(c); return json(c, 201);
  }
  const sch = /^\/newsletter\/campaigns\/([^/]+)\/schedule$/.exec(p);
  if (sch && m === 'POST') { const c = nl.campaigns.find((x) => x.id === sch[1]); if (!c) return problem(404, 'not_found', 'پیدا نشد.'); if (!stepUp) return needStepUp(); c.state = 'scheduled'; c.send_at = (await body<any>()).at; return json(c); }

  if (/^\/companies\/[^/]+\/ranks$/.test(p) && m === 'GET') return json(ranks());
  if (/^\/companies\/[^/]+\/competitors\/daily$/.test(p) && m === 'GET') return json(compDaily());
  const kc = /^\/companies\/([^/]+)\/(keywords|competitors|ad-rules)(?:\/([^/]+))?$/.exec(p);
  if (kc) {
    const arr = kc[2] === 'keywords' ? keywords : kc[2] === 'competitors' ? competitors : adRules;
    if (!kc[3] && m === 'GET') return json(arr.filter((x) => x.company === kc[1]));
    if (!kc[3] && m === 'POST') {
      const b = await body<any>();
      if (kc[2] === 'ad-rules') {
        if (b.platform !== 'google_ads' && b.platform !== 'meta_ads') return problem(422, 'validation_failed', 'سکوی قاعده لازم است.');
        if (b.daily_cap != null && !(Number(b.daily_cap) > 0)) return problem(422, 'validation_failed', 'سقف روزانه باید بیشتر از صفر باشد.');
        if (b.daily_cap == null && b.min_roas == null) return problem(422, 'validation_failed', 'سقف روزانه یا کمترین ROAS لازم است.');
      }
      const id = kc[2] === 'keywords' ? `K${nk++}` : kc[2] === 'competitors' ? `C${nco++}` : `R${nr++}`; const x = { ...b, id, company: kc[1] }; arr.push(x); return json(x, 201); }
    const i = arr.findIndex((x) => x.id === kc[3]);
    if (i < 0) return problem(404, 'not_found', 'پیدا نشد.');
    if (m === 'PUT') { const b = await body<any>(); const x = extra(kc[2]!, b); if (x.length) return forbidden(x); arr[i] = { ...arr[i], ...b }; return json(arr[i]); }
    if (m === 'DELETE') { arr.splice(i, 1); return json(null, 204); }
  }

  if (p === '/campaign-calendar' && m === 'GET') {
    const from = q.get('from') ?? today(), to = q.get('to') ?? addDays(from, 6), company = q.get('company');
    const items: any[] = [];
    for (let d = from; d <= to; d = addDays(d, 1)) {
      const push = (x: any) => { if (!company || x.company === company) items.push({ day: d, ...x }); };
      push({ at: `${d}T14:30:00Z`, company: 'TY', kind: 'line', ref: 'LN-0001', title_fa: 'ریلز آموزشی تریدیار', platform: 'instagram_reel', state: 'on', conflict_fa: null });
      push({ at: `${d}T05:30:00Z`, company: 'FX', kind: 'line', ref: 'LN-0002', title_fa: 'پست روزانه‌ی کانال FX', platform: 'telegram_post', state: 'on', conflict_fa: null });
      if (d === addDays(from, 2)) {
        push({ at: `${d}T06:00:00Z`, company: 'TY', kind: 'newsletter', ref: 'NC2', title_fa: 'برنامه‌ی هفته‌ی بازار', platform: null, state: 'draft', conflict_fa: null });
        push({ at: `${d}T14:50:00Z`, company: 'TY', kind: 'manual', ref: 'MN1', title_fa: 'پست دستی', platform: 'instagram_reel', state: 'draft', conflict_fa: 'فاصله‌اش با ریلز ساعت ۱۸ در همین صفحه از حد مجاز کمتر است.' });
      }
      if (d === addDays(from, 4)) push({ at: null, company: 'FX', kind: 'ad', ref: 'M1', title_fa: 'ثبت‌نام آموزش', platform: null, state: 'on', conflict_fa: 'روز تعطیل رسمی است.' });
    }
    return json({ from, to, items, holidays: [] });
  }
  const cp = /^\/campaigns(?:\/([^/]+))?$/.exec(p);
  if (cp) {
    if (!cp[1] && m === 'GET') return json(campaigns);
    if (!cp[1] && m === 'POST') { const x = { ...(await body<any>()), id: `CP${ncp++}` }; campaigns.push(x); return json(x, 201); }
    const i = campaigns.findIndex((x) => x.id === cp[1]);
    if (i < 0) return problem(404, 'not_found', 'پیدا نشد.');
    if (m === 'PUT') { const b = await body<any>(); const x = extra('campaigns', b); if (x.length) return forbidden(x); campaigns[i] = { ...campaigns[i], ...b }; return json(campaigns[i]); }
    if (m === 'DELETE') { campaigns.splice(i, 1); return json(null, 204); }
  }

  if (/^\/companies\/[^/]+\/ads$/.test(p) && m === 'GET') {
    const acc = (platform: string, label_fa: string) => ({ platform, label_fa, state: 'connected', secret: 'set', missing_fa: [], last_read_at: '2026-11-03T05:00:00Z', last_error_fa: null });
    return json({ company: p.split('/')[2], accounts: [acc('meta_ads', 'حساب متای تریدیار'), acc('google_ads', 'حساب گوگل تریدیار')], campaigns: adCampaigns, trips: [] });
  }
  const rs = /^\/ads\/campaigns\/([^/]+)\/([^/]+)\/resume$/.exec(p);
  if (rs && m === 'POST') {
    if (!stepUp) return needStepUp();
    const c = adCampaigns.find((x) => x.platform === rs[1] && x.campaign_id === rs[2]);
    if (!c) return problem(404, 'not_found', 'پیدا نشد.');
    c.status = 'active'; c.paused_by = null; c.paused_at = null; c.paused_reason_fa = null; return json(c);
  }

  if (p === '/automations/compile' && m === 'POST') {
    const b = await body<any>();
    if (!b.sentence_fa?.trim()) return problem(422, 'validation_failed', 'یک جمله بنویس.');
    const refused = /بودجه.*بالا|افزایش بودجه/.test(b.sentence_fa) ? ['بالا بردن بودجه‌ی تبلیغ انجام نمیشود؛ فقط با مُهر خودت.'] : [];
    return json({ rule: { trigger: { kind: 'schedule', rrule: 'FREQ=DAILY;BYHOUR=9' }, conditions: [], actions: [{ kind: 'notify.owner' }] }, preview_fa: 'هر روز ساعت ۹ صبح بازدید دیروز را میسنجد و اگر کم شده بود به تو خبر میدهد. چیزی منتشر یا پرداخت نمیکند.', refused_fa: refused });
  }
  if (p === '/automations' && m === 'GET') return json(automations);
  if (p === '/automations' && m === 'POST') { const b = await body<any>(); const a = { ref: `AT-${String(na++).padStart(4, '0')}`, company: b.company ?? null, sentence_fa: b.sentence_fa, rule: b.rule, state: 'proposed', runs: 0, last_run_at: null, n8n_workflow: null }; automations.push(a); return json(a, 201); }
  const au = /^\/automations\/([^/]+)(?:\/(seal|state))?$/.exec(p);
  if (au) {
    const a = automations.find((x) => x.ref === au[1]);
    if (!a) return problem(404, 'not_found', 'پیدا نشد.');
    if (!au[2] && m === 'GET') return json({ ...a, preview_fa: a.preview_fa ?? a.sentence_fa, created_at: '2026-11-01T06:00:00Z', run_log: a.runs ? [
      { key: 'r3', trigger: { kind: 'schedule' }, outcome: 'ok', steps: [{ kind: 'notify.owner' }], error_fa: null, at: '2026-11-03T04:30:00Z' },
      { key: 'r2', trigger: { kind: 'schedule' }, outcome: 'failed', steps: [], error_fa: 'بازدید دیروز خوانده نشد.', at: '2026-11-02T04:30:00Z' },
    ] : [] });
    if (au[2] === 'seal' && m === 'POST') { if (!stepUp) return needStepUp(); a.state = 'on'; return json(a); }
    if (au[2] === 'state' && m === 'POST') { a.state = (await body<any>()).state; return json(a); }
  }
  return null;
}
