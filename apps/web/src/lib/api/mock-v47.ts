// Development-only fixtures (npm run dev:mock) for contract §47 to §53 ⟨1.0.1⟩, the gaps of the reels order. In every new state, so the
// end-to-end checks and the demo show each one:
// - §47 the ledger of a member («دفتر موضوع‌ها»): Pro-Chart's in the reels group is full (topics and outside samples, more than a page),
//   the others begin empty; adding one that is said already answers `409 topic_taken` with the line and its day; a line is freed.
// - §48 the narrator: Pro-Chart has one, the others none; the hub's speaker is signed out where CoinePro FX is read.
// - §49 the best hour: enough posts for TradeYar and Pro-Chart, too few for one account of CoinePro FX, nothing read for its other one.
// - §50 standing routines of the session F-0007: one on, one off with a note; a sentence without a time of repetition is refused (422).
// - §51 and §44.5 the publish panel of that session's three outputs (which the demo did not have): files to tap, a post set for an hour
//   (cancellable), one cancelled, one whose cancel is on its way, one still being sent (`409 not_cancellable`), one out with its link.
// - §52 pictures that are not JPEG among those files; §53 `produced_with` with the model and the effort on two of the outputs.
// Kept in memory, never bundled in production (reached only through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const refuse = (status: number, code: string, message_fa: string, fields?: Record<string, string>) =>
  json({ type: 'about:blank', title: code, status, code, message_fa, ...(fields ? { fields } : {}) }, status);
const NOW = () => new Date().toISOString();
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const latin = (s: string) => s.replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0));
const two = (n: number) => String(n).padStart(2, '0');

/** The owner's zone (Tehran, +03:30 all year): the next time the clock there reads `hm`, after `days` more days. */
function nextAt(hm: string, days = 0): string {
  const off = 210 * 60_000;
  const local = new Date(Date.now() + off);
  const [h, m] = hm.split(':').map(Number) as [number, number];
  let t = Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate() + days, h, m);
  if (t <= local.getTime()) t += 86_400_000;
  const d = new Date(t);
  return `${d.getUTCFullYear()}-${two(d.getUTCMonth() + 1)}-${two(d.getUTCDate())}T${two(d.getUTCHours())}:${two(d.getUTCMinutes())}:00+03:30`;
}
/** A moment in the past, so every seeded line is older than what the owner adds now. */
const minsAgo = (n: number) => new Date(Date.now() - n * 60_000).toISOString();

// ===================================================================================================== §47 the ledger ==
type Topic = { id: string; kind: 'topic' | 'reference'; title_fa: string; url: string | null; at: string; by: string; source: 'claim' | 'package' | 'owner'; work_ref: string | null; output: string | null };
const ledgers = new Map<string, Topic[]>();
let topicSeq = 0;
const topicId = () => `0d1c47a0-0000-4000-8000-${String(++topicSeq).padStart(12, '0')}`;
const ledgerOf = (group: string, company: string): Topic[] => {
  const key = `${group}/${company}`;
  let l = ledgers.get(key);
  if (!l) { l = []; ledgers.set(key, l); }
  return l;
};
const SUBJECTS = ['اندیکاتور RSI', 'میانگین متحرک', 'حد ضرر', 'خط روند', 'الگوی سر و شانه', 'کندل دوجی', 'حمایت و مقاومت', 'مدیریت سرمایه', 'واگرایی در RSI', 'سطح‌های فیبوناچی', 'باند بولینگر', 'حجم معاملات', 'تایم‌فریم مناسب', 'اهرم در معامله'];
const ANGLES = ['در یک دقیقه', 'سه اشتباه رایج', 'با یک مثال واقعی'];
{
  // Pro-Chart's daily reels: 42 topics (one of them the owner's own line) and 40 outside samples, one of each a day, newest first.
  const pc = ledgerOf('pb_3', 'PC');
  for (let i = 0; i < 41; i++) {
    pc.push({
      id: topicId(), kind: 'topic', title_fa: `${SUBJECTS[i % SUBJECTS.length]}: ${ANGLES[Math.floor(i / SUBJECTS.length) % ANGLES.length]}`, url: null, at: minsAgo(i * 1440 + 90),
      by: i % 9 === 4 ? 'publish' : 'PC-MEDIA-01', source: i % 9 === 4 ? 'package' : 'claim', work_ref: null, output: null,
    });
  }
  for (let i = 0; i < 40; i++) {
    pc.push({
      id: topicId(), kind: 'reference', title_fa: `نمونه‌ی موشن ${SUBJECTS[i % SUBJECTS.length]}`, url: `https://www.pinterest.com/pin/${5_348_210_000 + i * 7919}/`, at: minsAgo(i * 1440 + 85),
      by: 'PC-MEDIA-01', source: 'claim', work_ref: null, output: null,
    });
  }
  pc.unshift({ id: topicId(), kind: 'topic', title_fa: 'هشدار قیمت در پرو-چارت', url: null, at: minsAgo(30), by: 'owner', source: 'owner', work_ref: null, output: null });
}
/** The same topic, roughly as the hub compares it: letters unified, marks and filler words out, the words in any order. */
const FILLER = new Set(['آموزش', 'معرفی', 'ویدیو', 'چیست', 'در', 'با', 'یک', 'و', 'را', 'به', 'از']);
const wordsOf = (t: string) => latin(t).toLowerCase().replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').replace(/‌/g, ' ').replace(/[^\p{L}\p{N}\s]/gu, ' ').split(/\s+/).filter((w) => w && !FILLER.has(w)).map((w) => w.replace(/(های|ها)$/, '')).sort();
const sameTopic = (a: string, b: string) => { const x = wordsOf(a); const y = wordsOf(b); return x.length > 0 && x.join(' ') === y.join(' '); };
const urlKey = (u: string) => u.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/[?#].*$/, '').replace(/\/+$/, '');
const dayOf = (iso: string) => iso.slice(0, 10);
const counts = (l: Topic[]) => ({ topics: l.filter((t) => t.kind === 'topic').length, references: l.filter((t) => t.kind === 'reference').length });

// ==================================================================================================== §48 the narrator ==
const VOICES: Array<[string, string, string]> = [
  ['Zephyr', 'female', 'روشن'], ['Puck', 'male', 'سرزنده'], ['Charon', 'male', 'اطلاع‌رسان'], ['Kore', 'female', 'محکم'], ['Fenrir', 'male', 'پرشور'], ['Leda', 'female', 'جوان'],
  ['Orus', 'male', 'محکم'], ['Aoede', 'female', 'نرم و هوایی'], ['Callirrhoe', 'female', 'راحت'], ['Autonoe', 'female', 'روشن'], ['Enceladus', 'male', 'نفس‌دار'], ['Iapetus', 'male', 'شفاف'],
  ['Umbriel', 'male', 'راحت'], ['Algieba', 'male', 'نرم'], ['Despina', 'female', 'نرم'], ['Erinome', 'female', 'شفاف'], ['Algenib', 'male', 'خش‌دار'], ['Rasalgethi', 'male', 'اطلاع‌رسان'],
  ['Laomedeia', 'female', 'سرزنده'], ['Achernar', 'female', 'آرام'], ['Alnilam', 'male', 'محکم'], ['Schedar', 'male', 'یکنواخت'], ['Gacrux', 'female', 'پخته'], ['Pulcherrima', 'female', 'رو به جلو'],
  ['Achird', 'male', 'دوستانه'], ['Zubenelgenubi', 'male', 'خودمانی'], ['Vindemiatrix', 'female', 'ملایم'], ['Sadachbia', 'male', 'پرجنب‌وجوش'], ['Sadaltager', 'male', 'دانا'], ['Sulafat', 'female', 'گرم'],
];
const narrators = new Map<string, { voice: string; style_fa: string; by: string; updated_at: string }>([
  ['PC', { voice: 'Charon', style_fa: 'آرام و مطمئن', by: 'owner', updated_at: minsAgo(3 * 1440) }],
]);
const AISTUDIO: Record<string, string> = { PC: 'signed_in', FX: 'signed_out', TY: 'unknown' };
const narratorOf = (company: string) => {
  const n = narrators.get(company);
  return {
    company, set: !!n, voice: n?.voice ?? 'Kore', style_fa: n?.style_fa ?? '', by: n?.by ?? null, updated_at: n?.updated_at ?? null,
    voices: VOICES.map(([name, gender, trait_fa]) => ({ name, gender, trait_fa })), aistudio: AISTUDIO[company] ?? 'unknown',
  };
};

// =================================================================================================== §49 the best hour ==
const ACCOUNTS: Record<string, string[]> = { TY: ['tradeyar'], FX: ['coineprofx', 'coineprofx.academy'], PC: ['pro.chart'] };
const READ: Record<string, { hour: string | null; posts: number; days: number; read: boolean }> = {
  tradeyar: { hour: '21:00', posts: 38, days: 62, read: true }, 'pro.chart': { hour: '19:00', posts: 27, days: 41, read: true },
  coineprofx: { hour: null, posts: 7, days: 9, read: true }, 'coineprofx.academy': { hour: null, posts: 0, days: 0, read: false },
};
function bestOf(company: string, account: string | null) {
  const mine = ACCOUNTS[company] ?? [];
  const handle = (account ?? '').replace(/^@/, '') || (mine.length === 1 ? mine[0]! : '');
  const r = READ[handle];
  if (!r || !r.read) return { account: handle || null, hour: null, at: null, enough: false, posts: 0, days: 0, basis: 'likes_comments', note_fa: 'آمار پست‌های این حساب هنوز از IG-Hub خوانده نشده است', read_at: null };
  if (!r.hour) return { account: handle, hour: null, at: null, enough: false, posts: r.posts, days: r.days, basis: 'likes_comments', note_fa: `هنوز داده‌ی کافی نیست (${r.posts} پست در ${r.days} روز؛ دست‌کم 12 پست در 28 روز لازم است)`, read_at: minsAgo(300) };
  return { account: handle, hour: r.hour, at: nextAt(r.hour), enough: true, posts: r.posts, days: r.days, basis: 'likes_comments', note_fa: `از روی لایک و کامنت ${r.posts} پست در ${r.days} روز اخیر (بازدید و reach هنوز خوانده نمیشود)`, read_at: minsAgo(300) };
}

// ====================================================================================== §50 the routines of a session ==
type Routine = { ref: string; company: string | null; sentence_fa: string; when_fa: string; preview_fa: string; state: 'proposed' | 'on' | 'off'; next_at: string | null; last_run_at: string | null; runs: number; order: string | null; note_fa: string | null; hm: string };
let routineSeq = 102;
const routines: Routine[] = [
  {
    ref: 'AT-0102', company: 'TY', sentence_fa: 'هر شنبه ساعت ۱۰ خلاصه‌ی بازدید ریلزهای هفته را برایم بفرست', when_fa: 'هر شنبه ساعت 10:00', preview_fa: 'برای شما این خبر فرستاده میشود: «خلاصه‌ی بازدید ریلزهای هفته»',
    state: 'off', next_at: null, last_run_at: minsAgo(9 * 1440), runs: 2, order: 'F-0007', note_fa: 'آخرین نوبت انجام نشد: سقف پاکت این ماه پر بود.', hm: '10:00',
  },
  {
    ref: 'AT-0101', company: 'TY', sentence_fa: 'هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده', when_fa: 'هر روز ساعت 09:00', preview_fa: 'یک کار تازه برای «تحلیلگر سئو» با عنوان «رتبه‌های سئوی سایت» ساخته میشود',
    state: 'on', next_at: nextAt('09:00'), last_run_at: minsAgo(200), runs: 6, order: 'F-0007', note_fa: null, hm: '09:00',
  },
];
const madeByKey = new Map<string, Routine>();
const routineView = ({ hm: _hm, ...r }: Routine) => r;
const routinesOf = (order: string) => routines.filter((r) => r.order === order).sort((a, b) => b.ref.localeCompare(a.ref)).map(routineView);
/** When a sentence repeats, as the hub would say it; null when it names no repetition (it is no routine then). */
function whenOf(sentence: string): { when_fa: string; hm: string } | null {
  const t = latin(sentence);
  const h = /ساعت\s*(\d{1,2})(?::(\d{2}))?/.exec(t);
  const hm = h && Number(h[1]) < 24 ? `${two(Number(h[1]))}:${h[2] ?? '00'}` : '09:00';
  const every = /هر\s*(\d{1,2})\s*ساعت/.exec(t);
  if (every) return { when_fa: `هر ${every[1]} ساعت`, hm };
  if (/هر ساعت/.test(t)) return { when_fa: 'هر ساعت، دقیقه‌ی 0', hm };
  const day = /هر\s*(شنبه|یکشنبه|دوشنبه|سه‌شنبه|چهارشنبه|پنجشنبه|جمعه)/.exec(t);
  if (day) return { when_fa: `هر ${day[1]} ساعت ${hm}`, hm };
  if (/هر (روز|شب|صبح)|روزانه|۲۴ ساعته|24 ساعته/.test(t)) return { when_fa: `هر روز ساعت ${hm}`, hm };
  if (/هر هفته|هفتگی/.test(t)) return { when_fa: `هر شنبه ساعت ${hm}`, hm };
  if (/هر ماه|ماهانه/.test(t)) return { when_fa: `هر ماه، روز 1 ساعت ${hm}`, hm };
  return null;
}
const titleOf = (sentence: string) => sentence.replace(/هر\s*(روز|شب|صبح|هفته|ماه|ساعت|شنبه|یکشنبه|دوشنبه|سه‌شنبه|چهارشنبه|پنجشنبه|جمعه)|روزانه|هفتگی|ماهانه/g, '').replace(/ساعت\s*[0-9۰-۹:]+/g, '').replace(/\s+/g, ' ').trim().slice(0, 60);

// ============================================================================= §44.5, §51, §52, §53 a session's outputs ==
type File47 = { id: string; name: string; mime: string; size: number; sha256: string };
type Publish = {
  job: string | null; output: string; file_id: string; file_name: string; cover_name: string | null; channel: 'instagram'; kind: string; account: string | null; state: string;
  url: string | null; note_fa: string | null; at: string; published_at: string | null; auto: boolean; scheduled_at: string | null; comment: string | null; files: number;
  /** demo only: a file still on its way cannot be cancelled; a publication the other server holds is cancelled a moment later */
  busy?: boolean; held?: boolean; key?: string; since?: number;
};
const file = (id: string, name: string, mime: string, size: number): File47 => ({ id, name, mime, size, sha256: '' });
const OUTPUTS: Record<string, { order: string; company: string; files: File47[]; produced_with?: Record<string, unknown>; caption: string }> = {
  'O-000061': {
    order: 'F-0007', company: 'TY', caption: 'سه اشتباهی که تازه‌کارها در هفته‌ی اول میکنند.\n#تریدیار #آموزش_ترید',
    files: [file('/demo/ty-story-stoploss.mp4', 'reel-01.mp4', 'video/mp4', 32_183), file('/demo/ty-story-stoploss-poster.webp', 'cover-01.png', 'image/png', 11_962), file('/demo/pc-landing-redesign.webp', 'frame-01.jpg', 'image/jpeg', 19_810)],
    produced_with: { runtime: 'workshop', files: 3, model: 'claude-opus-5-5', effort: 'max' },
  },
  'O-000062': {
    order: 'F-0007', company: 'TY', caption: 'حد ضرر را کجا بگذاریم؟ یک دقیقه، یک قانون.\n#تریدیار #حد_ضرر',
    files: [file('/demo/fx-reel-levels.mp4', 'reel-02.mp4', 'video/mp4', 110_561), file('/demo/fx-reel-levels-poster.webp', 'post-02.jpg', 'image/jpeg', 8_530), file('/demo/fx-reel-resist-poster.webp', 'slide-02.webp', 'image/webp', 8_560)],
    produced_with: { runtime: 'workshop', files: 3, model: 'claude-opus-5-5', effort: 'xhigh' },
  },
  'O-000063': {
    order: 'F-0007', company: 'TY', caption: 'کارمزد هر معامله را کجا ببینیم.\n#تریدیار',
    files: [file('/demo/fx-reel-resist.mp4', 'reel-03.mp4', 'video/mp4', 108_223), file('/demo/pc-landing-redesign.webp?post=3', 'post-03.jpg', 'image/jpeg', 19_810)],
  },
};
let pubSeq = 400;
const pub = (o: Partial<Publish> & Pick<Publish, 'output' | 'file_id' | 'file_name' | 'kind' | 'state'>): Publish => ({
  job: `pub-${String(++pubSeq).padStart(4, '0')}`, cover_name: null, channel: 'instagram', account: 'tradeyar', url: null, note_fa: null, at: NOW(), published_at: null, auto: false,
  scheduled_at: null, comment: null, files: 1, ...o,
});
const publishes: Publish[] = [
  pub({ output: 'O-000062', file_id: '/demo/fx-reel-levels.mp4', file_name: 'reel-02.mp4', kind: 'reel', state: 'scheduled', scheduled_at: nextAt('18:30', 1), at: minsAgo(50) }),
  pub({ output: 'O-000062', file_id: '/demo/fx-reel-levels-poster.webp', file_name: 'post-02.jpg', kind: 'post', state: 'cancelled', scheduled_at: nextAt('12:00', 1), at: minsAgo(55) }),
  pub({ output: 'O-000062', file_id: '/demo/fx-reel-resist-poster.webp', file_name: 'slide-02.webp', kind: 'post', state: 'scheduled', scheduled_at: nextAt('20:00', 1), note_fa: 'در حال لغو', held: true, at: minsAgo(60) }),
  pub({ output: 'O-000063', file_id: '/demo/fx-reel-resist.mp4', file_name: 'reel-03.mp4', kind: 'reel', state: 'publishing', busy: true, at: minsAgo(70) }),
  pub({ output: 'O-000063', file_id: '/demo/pc-landing-redesign.webp?post=3', file_name: 'post-03.jpg', kind: 'post', state: 'published', url: 'https://www.instagram.com/p/demo-post-03/', published_at: minsAgo(1440), at: minsAgo(1442) }),
];
const publishView = ({ busy: _b, held: _h, key: _k, since: _s, ...p }: Publish) => p;
/** A publish of the demo goes out a few seconds after the tap. */
function settle() {
  for (const p of publishes) {
    if (p.state === 'publishing' && !p.busy && p.since && Date.now() - p.since > 4000) Object.assign(p, { state: 'published', published_at: NOW(), url: `https://www.instagram.com/reel/demo-${p.job}/` });
  }
}
const publishesOf = (pick: (p: Publish) => boolean) => { settle(); return publishes.filter(pick).sort((a, b) => b.at.localeCompare(a.at)).map(publishView); };
const panelOf = (ref: string) => {
  const o = OUTPUTS[ref]!;
  const accounts = ACCOUNTS[o.company] ?? [];
  const best = bestOf(o.company, null);
  return {
    order: o.order, channel: 'instagram', accounts, ready: true, publishes: publishesOf((p) => p.output === ref), tap: true, caption: o.caption, group: null, group_fa: null, mode: null,
    comment: null, best: best.enough ? best : null,
  };
};

// ============================================================================================================ routes ==
type Next = (r: Request) => Promise<Response>;
const olderHub = () => { try { return window.localStorage.getItem('hq.e2e.old47') === '1'; } catch { return false; } };

/** §47 to §53; what is not its own goes on to [next] (the rest of the demo), decorated where §47 to §53 add to it. */
export async function handle47(req: Request, p: string, next: Next): Promise<Response | null> {
  const m = req.method;
  const q = new URL(req.url).searchParams;
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;
  // The e2e checks' older hub: with this set, nothing of §47 to §53 is served (its routes answer 404 further on, no field is added).
  if (olderHub()) return null;

  // ------------------------------------------------------------------------------------------------- the ledger --
  const lg = /^\/groups\/([a-z0-9_]+)\/members\/([A-Z][A-Z0-9]{1,9})\/topics(?:\/([^/]+))?$/.exec(p);
  if (lg) {
    const list = ledgerOf(lg[1]!, lg[2]!);
    if (!lg[3] && m === 'GET') {
      const kind = q.get('kind');
      const text = (q.get('q') ?? '').trim().toLowerCase();
      const before = q.get('cursor');
      const limit = Math.max(1, Math.min(200, Number(q.get('limit') ?? 50)));
      const rows = list.filter((t) => (!kind || t.kind === kind) && (!text || t.title_fa.toLowerCase().includes(text) || (t.url ?? '').toLowerCase().includes(text)) && (!before || t.at < before))
        .sort((a, b) => b.at.localeCompare(a.at));
      const page = rows.slice(0, limit);
      return json({ items: page, ...counts(list), next_cursor: rows.length > limit ? page.at(-1)!.at : null });
    }
    if (!lg[3] && m === 'POST') {
      const b = await body<{ kind?: string; title_fa?: string | null; url?: string | null }>();
      const kind = b.kind === 'reference' ? 'reference' : 'topic';
      const title = String(b.title_fa ?? '').replace(/\s+/g, ' ').trim().slice(0, 300);
      const url = String(b.url ?? '').trim().slice(0, 2000) || null;
      if (kind === 'reference' && !/^https:\/\/\S+\.\S+/.test(url ?? title)) return refuse(422, 'validation_failed', 'نمونه نشانی (لینک) میخواهد.', { url: "the reference's https address" });
      if (kind === 'topic' && !wordsOf(title).length) return refuse(422, 'validation_failed', 'موضوع را در چند کلمه بنویس.', { title_fa: 'the topic in a few words' });
      const link = kind === 'reference' ? url ?? title : url;
      const hit = list.find((t) => t.kind === kind && (kind === 'reference' ? urlKey(t.url ?? '') === urlKey(link ?? '') : sameTopic(t.title_fa, title)));
      if (hit) {
        const day = dayOf(hit.at);
        return refuse(409, 'topic_taken', `این پیش‌تر گفته شده: «${hit.title_fa.slice(0, 160)}» (${day}). یک موضوع تازه انتخاب کن.`, {
          title_fa: `taken: «${hit.title_fa.slice(0, 160)}» (${day})`, recent: list.filter((t) => t.kind === kind).slice(0, 5).map((t) => t.title_fa).join('؛ '),
        });
      }
      const row: Topic = { id: topicId(), kind, title_fa: title || link || '', url: link, at: NOW(), by: 'owner', source: 'owner', work_ref: null, output: null };
      list.unshift(row);
      return json(row, 201);
    }
    if (lg[3] && m === 'DELETE') {
      const i = list.findIndex((t) => t.id === decodeURIComponent(lg[3]!));
      if (i < 0) return refuse(404, 'not_found', 'این خط در دفتر نیست.');
      const [row] = list.splice(i, 1);
      return json(row);
    }
  }

  // ----------------------------------------------------------------------------- the narrator and the best hour --
  const co = /^\/companies\/([A-Z][A-Z0-9]{1,9})\/(narrator|best-hour)$/.exec(p);
  if (co) {
    const code = co[1]!;
    if (co[2] === 'best-hour' && m === 'GET') {
      const asked = (q.get('account') ?? '').replace(/^@/, '');
      const mine = ACCOUNTS[code] ?? [];
      if (asked && mine.length && !mine.includes(asked)) return refuse(422, 'validation_failed', 'این حساب برای این شرکت ثبت نشده است.', { account: `one of: ${mine.map((a) => `@${a}`).join(', ')}` });
      return json(bestOf(code, asked || null));
    }
    if (co[2] === 'narrator' && m === 'GET') return json(narratorOf(code));
    if (co[2] === 'narrator' && m === 'PUT') {
      const b = await body<{ voice?: string; style_fa?: string | null }>();
      const voice = VOICES.find(([name]) => name.toLowerCase() === String(b.voice ?? '').trim().toLowerCase());
      if (!voice) return refuse(422, 'validation_failed', `صدای «${String(b.voice ?? '').slice(0, 30)}» در ای‌آی استودیو نیست؛ یکی از صداهای آماده مثل Zephyr، Puck، Charon، Kore، Fenrir، Leda.`, { voice: "not one of AI Studio's prebuilt voices" });
      if (String(b.style_fa ?? '').length > 500) return refuse(422, 'validation_failed', 'سبک گفتن حداکثر ۵۰۰ نویسه است.', { style_fa: 'at most 500 characters' });
      narrators.set(code, { voice: voice[0], style_fa: String(b.style_fa ?? '').replace(/\s+/g, ' ').trim(), by: 'owner', updated_at: NOW() });
      return json(narratorOf(code));
    }
  }

  // ------------------------------------------------------------------------------------------------ the routines --
  if (p === '/routines' && m === 'GET') return json(routines.filter((r) => (!q.get('order') || r.order === q.get('order')) && (!q.get('company') || r.company === q.get('company'))).sort((a, b) => b.ref.localeCompare(a.ref)).map(routineView));
  if (p === '/routines' && m === 'POST') {
    const key = req.headers.get('Idempotency-Key') ?? '';
    if (!UUID.test(key)) return refuse(422, 'validation_failed', 'کلید یکتا باید UUID باشد.');
    const again = madeByKey.get(key);
    if (again) return json(routineView(again), 201);
    const b = await body<{ sentence_fa?: string; company?: string | null; order?: string | null }>();
    const sentence = String(b.sentence_fa ?? '').replace(/\s+/g, ' ').trim();
    if (sentence.length < 3) return refuse(422, 'validation_failed', 'جمله را بنویس.', { sentence_fa: 'at least 3 characters' });
    if (/تبلیغ|کمپین|خط تولید/.test(sentence)) {
      const why = 'این بیشتر از یک روال است (تبلیغ یا خط تولید را عوض میکند) و مُهر شما را میخواهد.';
      return refuse(422, 'validation_failed', why, { sentence_fa: why });
    }
    const when = whenOf(sentence);
    if (!when) {
      const why = 'این جمله نمیگوید هر چند وقت یک بار؛ مثلاً بنویس «هر روز ساعت ۹».';
      return refuse(422, 'validation_failed', why, { sentence_fa: why });
    }
    const made: Routine = {
      ref: `AT-${String(++routineSeq).padStart(4, '0')}`, company: b.company ?? 'TY', sentence_fa: sentence, when_fa: when.when_fa, preview_fa: `یک کار تازه برای «مسئول کار» با عنوان «${titleOf(sentence)}» ساخته میشود`,
      state: 'on', next_at: nextAt(when.hm), last_run_at: null, runs: 0, order: b.order ?? null, note_fa: null, hm: when.hm,
    };
    routines.push(made);
    madeByKey.set(key, made);
    return json(routineView(made), 201);
  }
  const st = /^\/automations\/(AT-\d+)\/state$/.exec(p);
  if (st && m === 'POST') {
    const r = routines.find((x) => x.ref === st[1]);
    // not a routine of this module: one of §31.7's own automations (./mock-v31)
    if (r) {
      const b = await body<{ state?: string }>();
      if (b.state !== 'on' && b.state !== 'off') return refuse(422, 'validation_failed', 'یا روشن یا خاموش.');
      Object.assign(r, { state: b.state, next_at: b.state === 'on' ? nextAt(r.hm) : null, ...(b.state === 'on' ? { note_fa: null } : {}) });
      return json({ ...routineView(r), rule: { trigger: { kind: 'schedule' }, conditions: [], actions: [] }, n8n_workflow: null, routine: true });
    }
  }

  // ---------------------------------------------------------------------------- the outputs and their publishes --
  const pc = /^\/publishes\/([^/]+)\/cancel$/.exec(p);
  if (pc && m === 'POST') {
    settle();
    const x = publishes.find((y) => y.job === decodeURIComponent(pc[1]!));
    if (!x) return refuse(404, 'not_found', 'این انتشار پیدا نشد.');
    if (x.state !== 'scheduled' && x.state !== 'publishing') return refuse(409, 'not_cancellable', 'این انتشار دیگر لغوشدنی نیست.');
    if (x.busy) return refuse(409, 'not_cancellable', 'فایل هنوز در راه IG-Hub است؛ چند لحظه بعد دوباره لغو کنید.');
    // one the other server holds already: the cancel is on its way, and a second tap answers the same
    if (x.held) return json(publishView(x));
    Object.assign(x, { state: 'cancelled', note_fa: null });
    return json(publishView(x));
  }
  const dv = /^\/deliverables\/(O-\d+)(\/publish)?$/.exec(p);
  if (dv && OUTPUTS[dv[1]!]) {
    const ref = dv[1]!;
    const o = OUTPUTS[ref]!;
    if (!dv[2] && m === 'GET') {
      const res = await next(req);
      if (!res.ok) return res;
      const d = (await res.json()) as Record<string, unknown>;
      return json({ ...d, attachments: o.files, ...(o.produced_with ? { produced_with: o.produced_with } : {}) });
    }
    if (dv[2] && m === 'GET') return json(panelOf(ref));
    if (dv[2] && m === 'POST') {
      const key = req.headers.get('Idempotency-Key') ?? '';
      if (!UUID.test(key)) return refuse(422, 'validation_failed', 'کلید یکتا باید UUID باشد.');
      const b = await body<{ file_id?: string; kind?: string; caption?: string; account?: string | null; cover_file_id?: string | null; file_ids?: string[]; scheduled_at?: string | null; comment?: { keywords?: string[] } | null }>();
      const f = o.files.find((x) => x.id === b.file_id);
      if (!f) return refuse(422, 'validation_failed', 'این فایل از این خروجی نیست.', { file_id: 'a file of this output' });
      const kind = b.kind ?? (f.mime.startsWith('video/') ? 'reel' : 'post');
      if (kind === 'reel' && !f.mime.startsWith('video/')) return refuse(422, 'validation_failed', 'ریلز باید ویدیو باشد.', { kind: 'a reel is a video' });
      const when = b.scheduled_at ? Date.parse(b.scheduled_at) : null;
      if (when != null && (Number.isNaN(when) || when < Date.now() - 60_000)) return refuse(422, 'validation_failed', 'زمان انتشار باید در آینده باشد.', { scheduled_at: 'in the future' });
      const account = (b.account ?? ACCOUNTS[o.company]?.[0] ?? '').replace(/^@/, '') || null;
      // the same file to the same account in the same kind is never sent twice while it is live or out
      const live = publishes.find((x) => x.key === key || (x.output === ref && x.file_id === f.id && x.kind === kind && x.account === account && ['publishing', 'scheduled', 'published'].includes(x.state)));
      if (live) return json(publishView(live), 202);
      const cover = kind === 'reel' ? o.files.find((x) => x.id === b.cover_file_id && x.mime.startsWith('image/')) : undefined;
      const made = pub({
        output: ref, file_id: f.id, file_name: f.name, kind, account, state: when != null ? 'scheduled' : 'publishing', scheduled_at: when != null ? b.scheduled_at! : null, cover_name: cover?.name ?? null,
        comment: kind !== 'story' ? b.comment?.keywords?.[0] ?? null : null, files: kind === 'carousel' ? 1 + (b.file_ids?.length ?? 0) : 1, key, since: Date.now(),
      });
      publishes.push(made);
      return json(publishView(made), 202);
    }
  }

  // The session's report says its standing routines and its publishes (newest first).
  const rp = /^\/orders\/(F-\d+)\/report$/.exec(p);
  if (rp && m === 'GET') {
    const res = await next(req);
    if (!res.ok) return res;
    const rep = (await res.json()) as Record<string, unknown>;
    return json({ ...rep, routines: routinesOf(rp[1]!), publishes: publishesOf((x) => OUTPUTS[x.output]?.order === rp[1]) });
  }
  return null;
}
