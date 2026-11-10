// Development-only fixtures (npm run dev:mock) for contract §40 ⟨1.22⟩: a session remembers («تا اینجا»), becomes a playbook (a working group as
// data), and the owner gives it to another company or platform. Two playbooks to begin with (a draft from the series session F-0007 and a
// sealed one from the SEO article session F-0006, with its first member), the sessions' memory text, drafting from a session (its card lands in
// the session's talk), light editing of a draft, seal and retire (sealed with the routine step-up), the library, and `apply`: a new session for
// that company whose first turn is the playbook as Markdown (`source` names it), or, with `as_is`, the company joins the sealed group at once.
// Kept in memory, never bundled in production (reached only through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

const json = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const NOW = () => new Date().toISOString();
const NAME: Record<string, string> = { TY: 'تریدیار', FX: 'کوینه‌پرو اف‌ایکس', PC: 'پرو-چارت' };
const PLATFORM_FA: Record<string, string> = { instagram: 'اینستاگرام', youtube: 'یوتیوب', telegram: 'تلگرام', site: 'سایت', any: 'همه' };

type Pb = any;
const playbooks = new Map<string, Pb>();
/** The memory of each session (§40.1), and the playbook a session was opened from (§40.3). */
const memory = new Map<string, string>();
const source = new Map<string, string>();
export const memoryOf = (order: string): string | null => memory.get(order) ?? null;
export const sourceOf = (order: string): string | null => source.get(order) ?? null;
export const setSource = (order: string, pb: string) => { source.set(order, pb); };
export const setMemory = (order: string, md: string) => { memory.set(order, md); };
let seq = 2;

memory.set('F-0007', '**تا اینجا**\n\n- هدف: برای تریدیار هر روز یک ریلز کوتاه آموزشی بسازیم و منظم منتشر کنیم.\n- نویسنده موضوع روز را با ChatGPT پیدا میکند و متن را مینویسد.\n- سازنده‌ی ریلز با جمنای تصویر و با ای‌آی استودیو صدا را میسازد.\n- سه ریلز اول ساخته و بازبینی شد.\n\n**کی چه میکند**\n\n- مدیر رسانه تریدیار: مسئول جلسه\n- نویسنده: موضوع و متن\n- سازنده‌ی ریلز: ساخت ویدیو\n\n**باز مانده**\n\n- مُهر سری انتشار\n- استخدام مسئول انتشار');
memory.set('F-0006', '- مقاله‌ی سئو برای FX نوشته و در وبلاگ منتشر شد.\n- نویسنده با جی‌پی‌تی کلیدواژه‌ها را پیدا میکند.\n- جلسه آماده‌ی تأیید است.');
memory.set('F-0008', '- سه عنوان پیشنهاد شد و منتظر انتخاب تو هستیم.\n- بعد از انتخاب، متن خبرنامه نوشته میشود.');

const seed = (o: Partial<Pb> & { ref: string }): Pb => {
  const pb = { version: 1, state: 'draft', platform: 'any', purpose_fa: '', seats: [], routines: [], kpis: [], connections: [], rules_fa: [], members: [], parent: null, group: null, note_fa: null, sealed_at: null, retired_at: null, created_at: NOW(), ...o };
  playbooks.set(pb.ref, pb);
  return pb;
};
seed({
  ref: 'PB-0001', title_fa: 'ریلز روزانه‌ی آموزشی', platform: 'instagram', created_at: '2026-11-06T09:00:00Z',
  purpose_fa: 'هر روز یک ریلز کوتاه آموزشی از موضوع روز پیدا میشود، نوشته و ساخته میشود و در ساعت ثابت منتشر میشود.',
  seats: [
    { seat: 'writer', role: 'content_writer', title_fa: 'نویسنده‌ی رسانه', duties_fa: 'موضوع روز را پیدا میکند و متن ریلز را مینویسد.', helpers: ['gpt'], model: null },
    { seat: 'maker', role: 'reel_maker', title_fa: 'سازنده‌ی ریلز', duties_fa: 'از متن، ویدیوی کوتاه میسازد.', helpers: ['gemini', 'aistudio'], model: null },
    { seat: 'publisher', role: 'publisher', title_fa: 'مسئول انتشار', duties_fa: 'ریلز تأییدشده را در ساعت مقرر منتشر میکند.', helpers: [], model: null },
  ],
  routines: [
    { key: 'topic', title_fa: 'پیدا کردن موضوع روز', seat: 'writer', schedule: 'FREQ=DAILY;BYHOUR=8;BYMINUTE=0', brief_md: 'موضوع امروز را از اخبار بازار پیدا کن و **سه پیشنهاد** بنویس؛ بهترین را با دلیل انتخاب کن.', max_tokens: 40000 },
    { key: 'reel', title_fa: 'ساخت ریلز', seat: 'maker', schedule: 'FREQ=DAILY;BYHOUR=11;BYMINUTE=30', brief_md: 'از متن تأییدشده یک ریلز ۳۰ ثانیه‌ای بساز.', max_tokens: 40000 },
    { key: 'review', title_fa: 'بازبینی هفتگی نتیجه‌ها', seat: 'publisher', schedule: 'FREQ=WEEKLY;BYDAY=SA,TU;BYHOUR=18;BYMINUTE=30', brief_md: 'ببین کدام ریلزها بیشتر دیده شدند و برای هفته‌ی بعد چه چیز را عوض کنیم.', max_tokens: 40000 },
  ],
  kpis: [{ key: 'reach', title_fa: 'بازدید هر ریلز', source: 'instagram.insights', unit: 'بازدید' }],
  connections: ['instagram'],
  rules_fa: ['هیچ ریلزی بدون تأیید مدیر رسانه منتشر نمیشود.', 'متن‌ها فارسی روان و بدون وعده‌ی سود باشد.'],
  source: { order: 'F-0007', company: 'TY', conversation: null },
  note_fa: 'یک روال بی‌جایگاه (مسئول مالی) کنار گذاشته شد.',
});
seed({
  ref: 'PB-0002', title_fa: 'مقاله‌ی هفتگی سئو', platform: 'site', state: 'sealed', version: 2, created_at: '2026-11-03T09:00:00Z', sealed_at: '2026-11-04T10:00:00Z', group: 'pb_2',
  purpose_fa: 'هر هفته یک مقاله‌ی سئو برای وبلاگ شرکت نوشته، بازبینی و منتشر میشود.',
  seats: [
    { seat: 'writer', role: 'content_writer', title_fa: 'نویسنده‌ی مقاله', duties_fa: 'کلیدواژه را پیدا میکند و مقاله را مینویسد.', helpers: ['gpt'], model: null },
    { seat: 'editor', role: 'editor', title_fa: 'ویراستار', duties_fa: 'مقاله را بازبینی میکند.', helpers: ['gemini'], model: null },
  ],
  routines: [{ key: 'article', title_fa: 'نوشتن مقاله‌ی هفته', seat: 'writer', schedule: 'FREQ=WEEKLY;BYDAY=SU;BYHOUR=9;BYMINUTE=0', brief_md: 'یک مقاله‌ی ۱۲۰۰ کلمه‌ای درباره‌ی موضوع هفته بنویس.', max_tokens: 40000 }],
  kpis: [], connections: ['wordpress'], rules_fa: ['هر مقاله دست‌کم یک تصویر و سه پیوند داخلی دارد.'],
  source: { order: 'F-0006', company: 'FX', conversation: null },
  members: [{ company: 'FX', name_fa: NAME.FX!, state: 'on', order: 'F-0006', publish: { mode: 'ask', account: null, story: false, since: null } }],
});

const playbookMd = (pb: Pb): string => [
  `# ${pb.title_fa}`, '', pb.purpose_fa, '', `پلتفرم: ${PLATFORM_FA[pb.platform] ?? pb.platform}`, '', '## جایگاه‌ها',
  ...pb.seats.map((s: any) => `- ${s.title_fa}: ${s.duties_fa ?? ''}`), '', '## روال‌ها',
  ...pb.routines.map((r: any) => `- ${r.title_fa}`), '', '## قانون‌ها', ...pb.rules_fa.map((t: string) => `- ${t}`),
].join('\n');

/** What the router needs from the session module (./mock-v34), passed in so the two files do not import each other. */
export type Hooks = {
  order: (ref: string) => Promise<{ text_fa: string; company: string; conversation: string | null } | null>;
  postCard: (order: string, pb: Pb) => void;
  openSession: (v: { company: string; text_fa: string; first_md: string; source: string }) => { ref: string; conversation: string };
};

const FIELDS = ['title_fa', 'purpose_fa', 'platform', 'seats', 'routines', 'kpis', 'connections', 'rules_fa'];

// ⟨0.19.9⟩ §45 the standing word: the accounts each company registered (FX has two, so its word asks which), and what the hub answers.
const ASK = { mode: 'ask', account: null, story: false, since: null };
const ACCOUNTS: Record<string, string[]> = { TY: ['tradeyar'], FX: ['coineprofx', 'coineprofx.academy'], PC: ['pro.chart'] };
/** The word a body carries: null when it says nothing, a string (the accounts to pick from) when the company has several and none is named. */
function wordOf(company: string, b: any): Record<string, unknown> | string | null {
  if (!b || typeof b !== 'object' || !b.mode) return null;
  if (b.mode !== 'auto') return ASK;
  const mine = ACCOUNTS[company] ?? [];
  const asked = b.account ? String(b.account).replace(/^@/, '') : mine.length === 1 ? mine[0]! : null;
  if (mine.length && (!asked || !mine.includes(asked))) return `one of: ${mine.map((a) => `@${a}`).join(', ')}`;
  return { mode: 'auto', account: asked, story: !!b.story, since: NOW(), at: typeof b.at === 'string' && /^\d\d:\d\d$/.test(b.at) ? b.at : null };
}
const pick = (accounts: string) => new Response(JSON.stringify({ type: 'about:blank', title: 'validation_failed', status: 422, code: 'validation_failed', message_fa: 'این شرکت چند حساب دارد؛ یکی را انتخاب کنید.', fields: { account: accounts } }), { status: 422, headers: { 'Content-Type': 'application/problem+json' } });

export async function handle40(req: Request, p: string, hooks: Hooks): Promise<Response | null> {
  const m = req.method;
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;
  const needStep = () => (req.headers.get('X-Step-Up') ? null : problem(403, 'step_up_required', 'این کار تأیید با اثر انگشت یا چهره میخواهد.'));

  const od = /^\/orders\/(F-\d+)\/playbook$/.exec(p);
  if (od && m === 'POST') {
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(req.headers.get('Idempotency-Key') ?? '')) return problem(422, 'validation_failed', 'کلید یکتا باید UUID باشد.');
    const o = await hooks.order(od[1]!);
    if (!o) return problem(404, 'not_found', 'این جلسه پیدا نشد.');
    const pb = seed({
      ref: `PB-${String(++seq).padStart(4, '0')}`, title_fa: `کارگروه «${o.text_fa.slice(0, 40)}»`, platform: 'any',
      purpose_fa: (memory.get(od[1]!) ?? o.text_fa).replace(/[#*]/g, '').split('\n').find((x) => x.trim().length > 12)?.replace(/^-\s*/, '') ?? o.text_fa,
      seats: [{ seat: 'holder', role: 'media_director', title_fa: 'مسئول کار', duties_fa: 'کار را پیش میبرد و نتیجه را بازبینی میکند.', helpers: [], model: null }, { seat: 'writer', role: 'content_writer', title_fa: 'نویسنده', duties_fa: 'متن را مینویسد.', helpers: ['gpt'], model: null }],
      routines: [{ key: 'daily', title_fa: 'نوشتن متن روز', seat: 'writer', schedule: 'FREQ=DAILY;BYHOUR=9;BYMINUTE=0', brief_md: 'متن امروز را بنویس و برای بازبینی بفرست.', max_tokens: 40000 }],
      rules_fa: ['هیچ چیز بدون تأیید مسئول منتشر نمیشود.'], source: { order: od[1], company: o.company, conversation: o.conversation }, created_at: NOW(),
    });
    hooks.postCard(od[1]!, pb);
    return json(pb, 201);
  }

  if (p === '/playbooks' && m === 'GET') {
    const st = new URL(req.url).searchParams.get('state');
    return json([...playbooks.values()].filter((x) => !st || x.state === st).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)));
  }
  // ⟨0.19.9⟩ §45 the owner's standing word for one member of a playbook's group (his tap, no step-up)
  const gm = /^\/groups\/(pb_\d+)\/members\/([A-Z][A-Z0-9]{1,9})\/publish$/.exec(p);
  if (gm && m === 'PUT') {
    const of = [...playbooks.values()].find((x) => x.group === gm[1]);
    const member = of?.members.find((x: any) => x.company === gm[2]);
    if (!of || !member) return problem(404, 'not_found', 'این شرکت عضو این کارگروه نیست.');
    const said = wordOf(gm[2]!, await body<any>());
    if (typeof said === 'string') return pick(said);
    member.publish = said ?? ASK;
    return json({ group: gm[1], company: gm[2], state: member.state, seats: [], publish: member.publish });
  }
  const pm = /^\/playbooks\/(PB-\d+)(?:\/(seal|apply|retire))?$/.exec(p);
  if (!pm) return null;
  const pb = playbooks.get(pm[1]!);
  if (!pb) return problem(404, 'not_found', 'این کارگروه پیدا نشد.');
  const act = pm[2];

  if (!act && m === 'GET') return json(pb);
  if (!act && m === 'PATCH') {
    if (pb.state !== 'draft') return problem(409, 'validation_failed', 'این کارگروه مُهر شده است؛ پیش‌نویسش دیگر عوض نمیشود.');
    const b = await body<any>();
    const keys = Object.keys(b);
    if (!keys.length || keys.some((k) => !FIELDS.includes(k))) return problem(422, 'validation_failed', 'دست‌کم یک فیلد درست بفرست.');
    if ('title_fa' in b && !String(b.title_fa ?? '').trim()) return problem(422, 'validation_failed', 'عنوان خالی نباشد.');
    for (const k of keys) pb[k] = b[k];
    // A routine on no seat is dropped, as the hub's normaliser does.
    pb.routines = pb.routines.filter((r: any) => pb.seats.some((s: any) => s.seat === r.seat));
    pb.version += 1;
    return json(pb);
  }
  if (act === 'seal' && m === 'POST') {
    const need = needStep();
    if (need) return need;
    if (pb.state !== 'draft') return problem(409, 'conflict', 'این کارگروه پیش‌نویس نیست.');
    pb.state = 'sealed'; pb.sealed_at = NOW(); pb.group = `pb_${pm[1]!.slice(3).replace(/^0+/, '')}`;
    const co = pb.source.company;
    const said = co ? wordOf(co, (await body<any>())?.publish) : null;
    pb.members = co ? [{ company: co, name_fa: NAME[co] ?? co, state: 'on', order: pb.source.order, publish: typeof said === 'object' && said ? said : ASK }] : [];
    return json(pb);
  }
  if (act === 'retire' && m === 'POST') {
    const need = needStep();
    if (need) return need;
    if (pb.state !== 'sealed') return problem(409, 'conflict', 'فقط کارگروه مُهرشده بازنشسته میشود.');
    pb.state = 'retired'; pb.retired_at = NOW();
    return json(pb);
  }
  if (act === 'apply' && m === 'POST') {
    const b = await body<any>();
    if (!/^[A-Z][A-Z0-9]{1,9}$/.test(String(b.company ?? '')) || !NAME[b.company]) return problem(422, 'validation_failed', 'شرکت را درست انتخاب کن.');
    if (pb.state === 'retired') return problem(409, 'conflict', 'این کارگروه بازنشسته شده است.');
    if (b.as_is) {
      if (pb.state !== 'sealed') return problem(409, 'conflict', 'بدون تغییر فقط برای کارگروه مُهرشده است.');
      const said = wordOf(b.company, b.publish);
      if (typeof said === 'string') return pick(said);
      let member = pb.members.find((x: any) => x.company === b.company);
      if (!member) { member = { company: b.company, name_fa: NAME[b.company], state: 'on', order: null, publish: said ?? ASK }; pb.members.push(member); }
      return json({ playbook: pb, member, order: null, conversation: null });
    }
    const note = String(b.note_fa ?? '').trim();
    const platform = PLATFORM_FA[b.platform] ?? PLATFORM_FA[pb.platform];
    const first = [`این کارگروه را برای ${NAME[b.company]} روی ${platform} پیاده کن.`, note, '', playbookMd(pb)].filter((x) => x !== null).join('\n');
    const s = hooks.openSession({ company: b.company, text_fa: `کارگروه «${pb.title_fa}» برای ${NAME[b.company]} روی ${platform}`, first_md: first, source: pb.ref });
    return json({ playbook: pb, member: null, order: s.ref, conversation: s.conversation });
  }
  return null;
}
