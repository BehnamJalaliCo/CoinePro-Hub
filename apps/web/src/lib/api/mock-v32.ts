// Development-only fixtures (npm run dev:mock) for contract §32 ⟨1.14⟩, the talk page: the personas, three voice engines (the Google one has no
// key until the owner gives it, and the key is checked after a moment), a meter, a few stored conversations, and a turn that streams its
// text, its sentences and short silent audio, a card or two and the meter. Answers are chosen by the words of the owner, never at random, so
// the end-to-end checks can follow them. Kept in memory. Never bundled in production (reached only through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

const json = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const needStepUp = () => problem(403, 'step_up_required', 'این کار تأیید با اثر انگشت یا چهره میخواهد.');
const NOW = () => new Date().toISOString();

/** Fifty milliseconds of silence as a WAV data URL, so the audio queue has a real file to play and nothing is fetched. */
function silence(): string {
  const n = 400;
  const b = new Uint8Array(44 + n);
  const dv = new DataView(b.buffer);
  const tag = (o: number, s: string) => { for (let i = 0; i < s.length; i++) b[o + i] = s.charCodeAt(i); };
  tag(0, 'RIFF'); dv.setUint32(4, 36 + n, true); tag(8, 'WAVE'); tag(12, 'fmt '); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
  dv.setUint32(24, 8000, true); dv.setUint32(28, 8000, true); dv.setUint16(32, 1, true); dv.setUint16(34, 8, true); tag(36, 'data'); dv.setUint32(40, n, true);
  b.fill(128, 44);
  let s = '';
  for (const x of b) s += String.fromCharCode(x);
  return `data:audio/wav;base64,${btoa(s)}`;
}

const PERSONAS = [
  { key: 'secretary', role: 'holding_secretary', title_fa: 'منشی هلدینگ', company: null, voice: { engine: 'gemini-3.8-flash-tts', voice: 'Kore', rate: 1 }, brain: { task_class: 'talk_turn', effort: 'medium' }, tools: ['work.get', 'company.state'], face: null, consult_only: false },
  { key: 'overseer', role: 'overseer', title_fa: 'ناظر کل', company: null, voice: { engine: 'gemini-3.8-flash-tts', voice: 'Charon', rate: 1 }, brain: { task_class: 'talk_turn', effort: 'high' }, tools: ['audit.recent'], face: null, consult_only: true },
  { key: 'assistant', role: 'assistant', title_fa: 'دستیار شخصی', company: null, voice: { engine: 'gemini-3.8-flash-tts', voice: 'Puck', rate: 1.05 }, brain: { task_class: 'talk_turn', effort: 'medium' }, tools: ['planner.add'], face: null, consult_only: false },
  { key: 'advisor', role: 'advisor', title_fa: 'مشاور کل', company: null, voice: { engine: 'gemini-3.8-flash-tts', voice: 'Orus', rate: 0.95 }, brain: { task_class: 'talk_turn', effort: 'xhigh' }, tools: ['knowledge.search'], face: null, consult_only: false },
  { key: 'manager', role: 'ceo', title_fa: 'مدیر شرکت', company: null, voice: { engine: 'piper', voice: 'fa-gyro', rate: 1 }, brain: { task_class: 'talk_turn', effort: 'medium' }, tools: ['company.state'], face: null, consult_only: false },
];
const VOICES = [
  { name: 'Kore', gender_fa: 'زنانه', sample_file: null }, { name: 'Aoede', gender_fa: 'زنانه', sample_file: null },
  { name: 'Charon', gender_fa: 'مردانه', sample_file: null }, { name: 'Puck', gender_fa: 'مردانه، جوان', sample_file: null }, { name: 'Orus', gender_fa: 'مردانه', sample_file: null },
];
const price = (t: number, a: number) => ({ text_in_per_m: t, audio_out_per_m: a, audio_tokens_per_s: 25, valid_until: null, next: null, source_url: 'https://ai.google.dev/pricing', as_of: '2026-11-01' });
const engines: any[] = [
  { key: 'gemini-3.8-flash-tts', title_fa: 'جمنای ۳٫۸ فلش (بهترین کیفیت)', provider: 'google', model: 'gemini-3.8-flash-tts', languages: 130, rank_fa: 'بهترین کیفیت؛ ۱۳۰ زبان', key_pattern: 'AIza[0-9A-Za-z_-]{35}', state: 'missing', reason_fa: 'هنوز کلیدی داده نشده.', checked_at: null, price: price(1, 20), voices: VOICES },
  { key: 'gemini-3.8-flash-lite-tts', title_fa: 'جمنای ۳٫۸ فلش لایت', provider: 'google', model: 'gemini-3.8-flash-lite-tts', languages: 101, rank_fa: 'حدود یک‌سوم ارزان‌تر؛ فارسی را با گوش خودت بسنج', key_pattern: 'AIza[0-9A-Za-z_-]{35}', state: 'missing', reason_fa: 'هنوز کلیدی داده نشده.', checked_at: null, price: { ...price(0.5, 13), next: { from: new Date(Date.now() + 9 * 86_400_000).toISOString().slice(0, 10), text_in_per_m: 1, audio_out_per_m: 26 } }, voices: VOICES },
  { key: 'piper', title_fa: 'پایپر (روی خود ستاد)', provider: 'local', model: 'piper', languages: 1, rank_fa: 'رایگان و همیشه آخر زنجیر', key_pattern: null, state: 'ok', reason_fa: null, checked_at: '2026-11-04T05:00:00Z', price: price(0, 0), voices: [{ name: 'fa-gyro', gender_fa: 'مردانه', sample_file: null }] },
];
let keyAt = 0;
let keyBad = false;
let cap: number | null = null;
let spent = { today: 0.012, month: 0.31 };
const personaSpend = { secretary: 0.1, overseer: 0.06, assistant: 0.02, advisor: 0.13 } as Record<string, number>;
const engineState = (e: any) => (e.provider === 'google' && keyAt ? (Date.now() - keyAt < 900 ? 'checking' : keyBad ? 'failing' : cap != null && spent.month >= cap ? 'capped' : 'ok') : e.state);
const engineOut = (e: any) => { const s = engineState(e); return { ...e, state: s, reason_fa: s === 'failing' ? 'کلید درست نیست.' : s === 'ok' ? null : s === 'capped' ? 'به سقف ماهانه رسید؛ صدا به موتور بعدی رفت.' : e.reason_fa }; };
const meter = (period: string) => {
  const k = period === 'today' ? spent.today : spent.month;
  const day = new Date().getUTCDate();
  return {
    period, voice_usd: Number(k.toFixed(4)), cap_usd: cap, projected_usd: Number(((spent.month / day) * 30).toFixed(3)),
    by_engine: [{ engine: 'gemini-3.8-flash-tts', usd: Number(k.toFixed(4)), seconds: Math.round(k * 4000), audio_tokens: Math.round(k * 100_000) }, { engine: 'piper', usd: 0, seconds: 40, audio_tokens: 0 }],
    by_persona: Object.entries(personaSpend).map(([persona, usd]) => ({ persona, usd: Number((period === 'today' ? usd / 25 : usd).toFixed(4)), seconds: Math.round(usd * 1000) })),
    talk_tokens: period === 'today' ? 18_400 : 412_000, talk_usd_equiv: period === 'today' ? 0.21 : 5.4,
    price_note_fa: 'شمارنده توکن‌های خود گوگل × جدول قیمت است؛ صورتحساب گوگل (مالیات و ارز) ممکن است کمی فرق کند.', updated_at: NOW(),
  };
};

const turnsOf: Record<string, any[]> = {};
const convs: any[] = [];
const cards = new Map<string, any>();
let cvN = 0;
let turnN = 0;
let cardN = 0;
const stopped = new Set<string>();
const turnById = new Map<string, any>();
const newConv = (persona: string, title_fa: string, extra: Partial<any> = {}) => {
  const c = { ref: `CV-${String(++cvN).padStart(4, '0')}`, title_fa, persona, present: [persona], mode: 'consult', started_at: '2026-11-03T09:00:00Z', last_turn_at: null, turns: 0, summary_fa: null, cost: { tokens: 0, usd_equiv: 0, voice_usd: 0 }, open_cards: 0, ...extra };
  convs.unshift(c); turnsOf[c.ref] = [];
  return c;
};
const addTurn = (c: any, by: string, text: string, o: Partial<any> = {}) => {
  const t: any = { id: `tn-${String(++turnN).padStart(4, '0')}`, conversation: c.ref, n: turnsOf[c.ref]!.length + 1, by, source: by === 'owner' ? 'typed' : null, text, say_fa: null, show_md: null, cards: [], audio: [], tokens: null, voice: null, state: 'done', reason_fa: null, at: NOW(), ...o };
  turnsOf[c.ref]!.push(t); turnById.set(t.id, t); c.turns = turnsOf[c.ref]!.length; c.last_turn_at = t.at;
  return t;
};
const seed = () => {
  const a = newConv('secretary', 'برنامه‌ی هفته‌ی تریدیار', { turns: 2, last_turn_at: '2026-11-03T09:05:00Z', summary_fa: 'درباره‌ی برنامه‌ی انتشار هفته‌ی تریدیار حرف زدیم.' });
  turnsOf[a.ref] = [
    { id: 'tn-seed-1', conversation: a.ref, n: 1, by: 'owner', source: 'typed', text: 'این هفته برای تریدیار چه برنامه‌ای داریم؟', say_fa: null, show_md: null, cards: [], audio: [], tokens: null, voice: null, state: 'done', reason_fa: null, at: '2026-11-03T09:04:00Z' },
    { id: 'tn-seed-2', conversation: a.ref, n: 2, by: 'secretary', source: null, text: '', say_fa: 'این هفته سه ریلز و یک خبرنامه برنامه‌ریزی شده.', show_md: 'این هفته برای تریدیار:\n\n- سه ریلز آموزشی\n- یک خبرنامه‌ی هفتگی\n- بازبینی سقف تبلیغ', cards: [], audio: [], tokens: { input: 1200, output: 180, cache_read: 900, cache_write: 0 }, voice: null, state: 'done', reason_fa: null, at: '2026-11-03T09:05:00Z' },
  ];
  turnsOf[a.ref]!.forEach((t) => turnById.set(t.id, t));
  newConv('advisor', 'مرور هزینه‌ی ماه', { turns: 0, last_turn_at: '2026-11-02T10:00:00Z' });
};
seed();

const makeCard = (turn: string, kind: string, title_fa: string, body_fa: string, payload: Record<string, unknown> = {}) => {
  const c: any = { id: `cd-${String(++cardN).padStart(4, '0')}`, turn, kind, title_fa, body_fa, payload, state: 'offered', made: [], reason_fa: null };
  cards.set(c.id, c);
  return c;
};

/** What the persona answers, chosen by the owner's words. */
function answer(c: any, text: string, id: string) {
  const who = c.present[c.present.length - 1] as string;
  const base = { who, say: 'باشه، همین را میبینم و جواب میدهم.', md: 'نگاه کوتاهی کردم؛ چیز نگران‌کننده‌ای نیست.\n\n- فرمان‌های امروز در جریان‌اند\n- تصمیم منتظری ندارم', cards: [] as any[], invite: null as { role: string; company: string } | null, slow: false };
  if (/طولانی/.test(text)) {
    base.say = 'این جواب طولانی است.'; base.md = Array.from({ length: 40 }, (_, i) => `بند شماره ${i + 1} از جواب طولانی`).join(' ');
    base.slow = true;
  } else if (c.order_ref && /استخدام|استخدامش/.test(text)) {
    base.say = 'یک پیشنهاد استخدام آماده کردم.'; base.md = 'برای این فرمان یک مسئول انتشار لازم است. پیشنهاد استخدام را ساختم؛ تا نزنی «اجرا کن» چیزی نمیشود.';
    base.cards.push(makeCard(id, 'hire', 'استخدام مسئول انتشار تریدیار', 'نقش: مسئول انتشار · شرکت: تریدیار', { role: 'publisher', company: 'TY' }));
  } else if (c.order_ref && /بسپار|به او بده/.test(text)) {
    base.say = 'کار را به نویسنده میسپارم.'; base.md = 'این کار را به نویسنده‌ی رسانه‌ی تریدیار میسپارم.';
    base.cards.push(makeCard(id, 'delegate', 'نوشتن متن سه ریلز', 'به: نویسنده‌ی رسانه‌ی تریدیار', { to: 'TY-MEDIA-01', text: 'متن سه ریلز را بنویس' }));
  } else if (c.order_ref && /کارگروه/.test(text)) {
    base.say = 'تریدیار را به کارگروه محتوا میبرم.'; base.md = 'اگر موافقی، تریدیار عضو کارگروه محتوا شود تا شاخص‌هایش کنار بقیه دیده شود.';
    base.cards.push(makeCard(id, 'group', 'تریدیار به کارگروه محتوا', 'شرکت: تریدیار · کارگروه: محتوا', { company: 'TY', group: 'content' }));
  } else if (c.order_ref && /خط تولید/.test(text)) {
    base.say = 'یک خط تولید راه میاندازم.'; base.md = 'یک خط تولید ریلز روزانه برای تریدیار، از قالب آماده.';
    base.cards.push(makeCard(id, 'line', 'خط تولید ریلز روزانه', 'شرکت: تریدیار · قالب: ریلز روزانه', { company: 'TY', template: 'daily-reel' }));
  } else if (/صورت.?جلسه|تسک|پایان جلسه/.test(text)) {
    base.say = 'صورت‌جلسه را آماده کردم؛ نگاهش کن.'; base.md = 'صورت‌جلسه آماده است. کارها را ببین، اگر لازم بود ویرایش کن و اجرا کن.';
    base.cards.push(makeCard(id, 'minutes', 'صورت‌جلسه‌ی همین گفتگو', 'خلاصه: برنامه‌ی انتشار هفته را سنجیدیم. تصمیم: خبرنامه روز پنجشنبه برود.', { tasks: [{ title_fa: 'نوشتن خبرنامه‌ی هفته', company: 'TY', department: 'content', due: '2026-11-06' }, { title_fa: 'بازبینی سقف تبلیغ', company: 'TY', department: 'growth', due: '2026-11-07' }] }));
  } else if (/بیاور/.test(text) && /تریدیار/.test(text)) {
    base.say = 'مدیرعامل تریدیار را صدا میزنم.'; base.md = 'مدیرعامل تریدیار را دعوت میکنم.'; base.invite = { role: 'ceo', company: 'TY' };
  } else if (/بساز|بنویس|فرمان|ریلز/.test(text) && !c.persona.startsWith('overseer')) {
    base.say = 'یک فرمان آماده کردم؛ اگر درست است اجرا کن.'; base.md = 'این فرمان را از حرف تو ساختم. تا نزنی «اجرا کن» چیزی انجام نمیشود.';
    base.cards.push(makeCard(id, 'order', 'سه ریلز آموزشی برای تریدیار', 'شرکت: تریدیار · بخش: محتوا · خروجی: ۳ ریلز', { text: text, company: 'TY', department: 'content' }));
  } else if (/تحلیل|ماه گذشته/.test(text)) {
    base.say = 'این سؤال عمیق است؛ بهتر است از یک متخصص بپرسم.'; base.md = 'این را حدسی جواب نمیدهم. اگر بخواهی از متخصص مربوط میپرسم و جوابش به همین گفتگو برمیگردد.';
    base.cards.push(makeCard(id, 'ask', 'تحلیل فروش ماه گذشته‌ی تریدیار', 'پرسش از تحلیلگر تریدیار؛ جواب به همین گفتگو برمیگردد.', { text }));
  } else if (/کلید/.test(text)) {
    base.say = 'کلید را با دکمه‌ی کلید بدهید.'; base.md = 'کلید را با دکمه‌ی 🔑 بدهید.';
  }
  return base;
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const sse = (name: string, data: unknown) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;

function stream(turn: any, a: ReturnType<typeof answer>) {
  const enc = new TextEncoder();
  let cancelled = false;
  return new ReadableStream<Uint8Array>({
    async start(ctl) {
      const send = (name: string, data: unknown) => { if (!cancelled) ctl.enqueue(enc.encode(sse(name, data))); };
      const parts = a.md.split(/(?<=[\s])/);
      let shown = '';
      for (let i = 0; i < parts.length && !stopped.has(turn.id); i++) { shown += parts[i]; send('text', { delta: parts[i] }); if (a.slow ? i % 2 === 0 : i % 4 === 0) await sleep(a.slow ? 120 : 25); }
      if (!stopped.has(turn.id)) { send('say', { text: a.say }); send('audio', { seq: 1, file_id: silence(), seconds: 0.05, engine: 'gemini-3.8-flash-tts' }); await sleep(30); }
      if (!stopped.has(turn.id)) {
        for (const c of a.cards) send('card', { card: c });
        if (a.invite) send('invite', a.invite);
      }
      const ended = stopped.has(turn.id);
      turn.state = ended ? 'stopped' : 'done'; turn.say_fa = ended ? null : a.say; turn.show_md = shown; turn.cards = ended ? [] : a.cards;
      turn.audio = ended ? [] : [{ seq: 1, file_id: silence(), seconds: 0.05, engine: 'gemini-3.8-flash-tts' }];
      turn.tokens = { input: 1800, output: 140, cache_read: 1500, cache_write: 0 }; turn.voice = ended ? null : { engine: 'gemini-3.8-flash-tts', seconds: 0.05, audio_tokens: 2, usd: 0.0004 };
      if (!ended) { spent = { today: spent.today + 0.004, month: spent.month + 0.004 }; }
      const c = convs.find((x) => x.ref === turn.conversation);
      if (c) c.open_cards += turn.cards.length;
      send('meter', { voice_usd: spent.today, talk_usd_equiv: 0.21 });
      send('done', { turn });
      if (!cancelled) ctl.close();
    },
    cancel() { cancelled = true; },
  });
}

export async function handle32(req: Request, p: string): Promise<Response | null> {
  if (!/^\/(talk\/|voice\/|owner\/settings$)/.test(p)) return null;
  const m = req.method;
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;
  const stepUp = req.headers.get('X-Step-Up');

  if (p === '/owner/settings') {
    if (m !== 'PUT') return null;
    const b = await body<any>();
    if (!b.voice) return null;
    cap = b.voice.month_cap_usd ?? null;
    return json({ voice: { month_cap_usd: cap } });
  }

  if (p === '/talk/personas' && m === 'GET') return json(PERSONAS);
  const ps = /^\/talk\/personas\/([^/]+)$/.exec(p);
  if (ps && m === 'PUT') {
    const x = PERSONAS.find((y) => y.key === ps[1]);
    if (!x) return problem(404, 'not_found', 'این چهره پیدا نشد.');
    const b = await body<any>();
    if (b.voice) x.voice.voice = b.voice;
    if (b.engine) x.voice.engine = b.engine;
    if (b.effort) x.brain.effort = b.effort;
    return json(x);
  }

  if (p === '/talk/conversations') {
    if (m === 'GET') {
      const q = new URL(req.url).searchParams;
      const s = q.get('q')?.trim();
      const per = q.get('persona');
      return json(convs.filter((c) => (!per || c.persona === per) && (!s || c.title_fa.includes(s) || (turnsOf[c.ref] ?? []).some((t) => (t.text + (t.show_md ?? '')).includes(s)))));
    }
    if (m === 'POST') {
      const b = await body<any>();
      if (!PERSONAS.some((x) => x.key === b.persona)) return problem(422, 'validation_failed', 'این چهره را نمیشناسم.');
      const mgr = b.persona === 'manager' && b.role && b.company ? `${b.role}@${b.company}` : null;
      const c = newConv(mgr ?? b.persona, mgr ? `گفتگو با ${b.role === 'ceo' ? 'مدیرعامل' : b.role} ${b.company}` : `گفتگوی تازه با ${PERSONAS.find((x) => x.key === b.persona)!.title_fa}`, { mode: b.mode ?? 'consult', started_at: NOW() });
      return json(c, 201);
    }
  }
  const cv = /^\/talk\/conversations\/([^/]+)(?:\/(turns|invite|minutes))?$/.exec(p);
  if (cv) {
    const c = convs.find((x) => x.ref === cv[1]);
    if (!c) return problem(404, 'not_found', 'این گفتگو پیدا نشد.');
    if (!cv[2] && m === 'GET') return json({ ...c, turns_page: turnsOf[c.ref] ?? [], next: null });
    if (!cv[2] && m === 'PATCH') { const b = await body<any>(); if (b.mode) c.mode = b.mode; if (b.title_fa) c.title_fa = b.title_fa; return json(c); }
    if (cv[2] === 'turns' && m === 'POST') {
      const b = await body<any>();
      const text = String(b.text ?? '').trim();
      if (!text) return problem(422, 'validation_failed', 'متن خالی است.');
      // The server's defence: a key-shaped string is never kept.
      const safe = /AIza[0-9A-Za-z_-]{35}/.test(text) ? '[کلید حذف شد]' : text;
      // ⟨1.18⟩ §36.2 `file_ids` (≤ 10): the owner's own uploads come back on his turn; a font gets its family from the file name.
      const ids: string[] = Array.isArray(b.file_ids) ? b.file_ids : [];
      if (ids.length > 10) return problem(422, 'validation_failed', 'حداکثر ۱۰ فایل در هر پیام.');
      const fileRef = ids.length ? (await import('./mock')).fileRef : () => null; // the big fixtures module loads only when files come along
      const refs = ids.map((id) => fileRef(id)).filter((x): x is Record<string, unknown> => !!x).map((f) => (f.kind === 'font' ? { ...f, meta: { family: String(f.name).replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ') } } : f));
      addTurn(c, 'owner', safe, { source: b.source ?? 'typed', files: refs });
      // ⟨1.17⟩ §35.4 `to`: a participant answers; «all» lets each present participant say a line first, then the holder sums up.
      const holder = c.order_ref ? c.present[0] : c.present[c.present.length - 1];
      const aimed = typeof b.to === 'string' && b.to !== 'all' && c.present.includes(b.to) ? b.to : holder;
      if (b.to === 'all') for (const k of c.present.slice(1)) addTurn(c, k, '', { show_md: `نظر ${k.startsWith('player:') ? 'این مدل' : 'من'}: با همین برنامه جلو برویم؛ فقط زمان‌بندی را یک بار دیگر ببینید.` });
      const t = addTurn(c, aimed, '', { state: 'streaming' });
      stopped.delete(t.id);
      const a = answer(c, safe, t.id);
      streams.set(t.id, a);
      return json({ turn: t, events: `/api/v1/talk/turns/${t.id}/events` }, 202);
    }
    if (cv[2] === 'invite' && m === 'POST') {
      const b = await body<any>();
      const who = `${b.role}@${b.company}`;
      if (!c.present.includes(who)) c.present.push(who);
      addTurn(c, 'secretary', '', { show_md: `${b.role === 'ceo' ? 'مدیرعامل' : b.role} ${b.company} آمد.`, say_fa: null });
      return json(c);
    }
    if (cv[2] === 'minutes' && m === 'POST') {
      const t = addTurn(c, 'secretary', '', { show_md: 'صورت‌جلسه‌ی این گفتگو را آماده کردم.' });
      const card = makeCard(t.id, 'minutes', 'صورت‌جلسه‌ی همین گفتگو', 'خلاصه: برنامه‌ی هفته را سنجیدیم.', { tasks: [{ title_fa: 'نوشتن خبرنامه‌ی هفته', company: 'TY', department: 'content', due: '2026-11-06' }] });
      t.cards = [card]; c.open_cards += 1;
      return json({ turn: t, card }, 201);
    }
  }
  const sx = /^\/talk\/turns\/([^/]+)\/(events|stop)$/.exec(p);
  if (sx) {
    const t = turnById.get(sx[1]!);
    if (!t) return problem(404, 'not_found', 'این نوبت پیدا نشد.');
    if (sx[2] === 'stop' && m === 'POST') { stopped.add(t.id); return json(null, 204); }
    if (sx[2] === 'events' && m === 'GET') {
      const a = streams.get(t.id) ?? answer({ persona: 'secretary', present: ['secretary'] }, '', t.id);
      return new Response(stream(t, a), { status: 200, headers: { 'content-type': 'text/event-stream' } });
    }
  }
  const cd = /^\/talk\/cards\/([^/]+)\/(run|dismiss)$/.exec(p);
  if (cd && m === 'POST') {
    const c = cards.get(cd[1]!);
    if (!c) return problem(404, 'not_found', 'این کارت پیدا نشد.');
    if (cd[2] === 'dismiss') { c.state = 'dismissed'; return json(c); }
    const b = await body<any>();
    c.payload = { ...c.payload, ...(b.payload ?? {}) };
    c.state = 'done';
    const n = c.kind === 'minutes' ? ((c.payload.tasks as unknown[] | undefined)?.length ?? 1) : 1;
    c.made = Array.from({ length: n }, (_, i) => `F-${String(130 + i)}`);
    return json({ made: c.made });
  }

  if (p === '/voice/engines' && m === 'GET') return json(engines.map(engineOut));
  const ev = /^\/voice\/engines\/([^/]+)\/(voices|check|price)$/.exec(p);
  if (ev) {
    const e = engines.find((x) => x.key === ev[1]);
    if (!e) return problem(404, 'not_found', 'این موتور را نمیشناسم.');
    if (ev[2] === 'voices' && m === 'GET') return json(e.voices);
    if (ev[2] === 'check' && m === 'POST') { if (e.provider === 'google' && !keyAt) return problem(502, 'upstream_refused', 'کلیدی داده نشده است.'); keyAt = Date.now(); return json(engineOut(e)); }
    if (ev[2] === 'price' && m === 'PUT') { e.price = { ...e.price, ...(await body<any>()) }; return json(engineOut(e)); }
  }
  const sec = /^\/voice\/providers\/([^/]+)\/secret$/.exec(p);
  if (sec) {
    if (!stepUp) return needStepUp();
    if (m === 'PUT') {
      const b = await body<any>();
      if (!b.secret || b.secret.length < 20) return problem(422, 'validation_failed', 'کلید درست نیست.');
      keyAt = Date.now(); keyBad = /BAD/.test(b.secret);
      return json({ state: 'checking' }, 202);
    }
    if (m === 'DELETE') { keyAt = 0; keyBad = false; return json(null, 204); }
  }
  if (p === '/voice/meter' && m === 'GET') return json(meter(new URL(req.url).searchParams.get('period') === 'today' ? 'today' : 'month'));
  if (p === '/voice/sample' && m === 'POST') {
    const b = await body<any>();
    const e = engines.find((x) => x.key === b.engine);
    if (!e) return problem(404, 'not_found', 'این موتور را نمیشناسم.');
    if (engineState(e) !== 'ok') return problem(502, 'upstream_refused', 'این موتور الان جواب نمیدهد؛ کلید را ببین.');
    spent = { today: spent.today + 0.001, month: spent.month + 0.001 };
    return json({ file_id: silence(), seconds: 0.05 });
  }
  return null;
}
const streams = new Map<string, ReturnType<typeof answer>>();

// ============================================================================== ⟨1.17⟩ §35 a session's conversation ==
/** The session module (./mock-v34) makes, reads and closes the conversation of an order here. */
export function sessionConversation(persona: string, title_fa: string, order_ref: string, lines: Array<[string, string, string?]>, at = '2026-11-05T09:00:00Z') {
  const c: any = newConv(persona, title_fa, { mode: 'work', order_ref, started_at: at, closed_at: null });
  for (const [by, md, when] of lines) addTurn(c, by, by === 'owner' ? md : '', by === 'owner' ? { at: when ?? at } : { show_md: md, at: when ?? at });
  return c;
}
export const conversationOf = (ref: string): any => convs.find((x) => x.ref === ref);
export const presentAdd = (ref: string, key: string) => { const c = conversationOf(ref); if (c && !c.present.includes(key)) c.present.push(key); };
export const presentDrop = (ref: string, key: string) => { const c = conversationOf(ref); if (c) c.present = c.present.filter((x: string) => x !== key); };
export const conversationClosed = (ref: string, at: string | null) => { const c = conversationOf(ref); if (c) c.closed_at = at; };
export const conversationSay = (ref: string, by: string, md: string) => { const c = conversationOf(ref); if (c) addTurn(c, by, by === 'owner' ? md : '', by === 'owner' ? {} : { show_md: md }); };

/** ⟨1.22⟩ §40.2 a card the holder posts into a session's talk (the playbook card of a fresh draft): a turn of the holder's with one offered card. */
export function conversationCard(ref: string, by: string, md: string, kind: string, title_fa: string, body_fa: string, payload: Record<string, unknown>) {
  const c = conversationOf(ref);
  if (!c) return null;
  const t = addTurn(c, by, '', { show_md: md });
  const card = makeCard(t.id, kind, title_fa, body_fa, payload);
  t.cards = [card]; c.open_cards += 1;
  return card;
}

/** ⟨1.18⟩ Every file of the owner's turns in a conversation, newest first (§36.3). */
export const conversationFiles = (ref: string): unknown[] => [...(turnsOf[ref] ?? [])].reverse().filter((t) => t.by === 'owner').flatMap((t) => [...(t.files ?? [])].reverse());

/** ⟨1.19⟩ §37.1 What an erased talk takes with it, and the erasing itself (the turns, their files; the conversation leaves every list). */
export const conversationCounts = (ref: string) => ({ turns: (turnsOf[ref] ?? []).length, files: conversationFiles(ref).length });
export function conversationDrop(ref: string) {
  const i = convs.findIndex((x) => x.ref === ref);
  if (i >= 0) convs.splice(i, 1);
  for (const t of turnsOf[ref] ?? []) turnById.delete(t.id);
  delete turnsOf[ref];
}
