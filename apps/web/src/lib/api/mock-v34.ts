// Development-only fixtures (npm run dev:mock) for contract §34 and §35 ⟨1.16 and 1.17⟩, the order as a session and the owner's office. Five
// sessions in every badge (the owner's turn with a question, a blocker with a one-tap fix, ready for his OK, moving, and one closed and
// archived), each with its own talk; participants (a person, a model seat), tasks, close / reopen / hide, the office (sessions, approvals,
// money, critical, suggestions, canvas) and the company links with the nodes' places. A new order opens its session at once. Answers are chosen by
// the owner's words, never at random, so the end-to-end checks can follow them. Kept in memory. Never bundled in production (reached only
// through ./mock-v21 when NEXT_PUBLIC_HQ_MOCK=1).
// ⟨1.0.1⟩ §54 and §55.1 for the redesigned session: three more sessions (F-0010 a workshop turn that builds a motion graphic, with its
// time cap; F-0011 a direct session whose holder works himself; F-0012 ready for his OK with a reel to publish), the activity's `mood`
// and each worker's `kind`, `cap_s`, `last_fa`, `last_at`, and the owner's stop of a live work (./mock-v55 routes it here). The e2e
// `hq.e2e.stuck=plain` makes F-0005 stuck with no fix of the hub's (the knot's own way out is then «ادامه بده»). The
// checks ask for the rarer states through `hq.e2e.ring=late` (the turn is past 90 percent of its cap), `hq.e2e.workers=2` (two work
// at once in F-0007), `hq.e2e.mood=thinking` (a run that has taken no step yet) and `hq.e2e.old55` (a hub before §55: none of these).
// ⟨2026-11-11⟩ The owner's 12-hour stall (Pro-Chart's daily reels, «با من», task 3 of 18), in its two states and in no list: F-0013 while
// the draft waits in ChatGPT's queue (an outside call at work, `kind: call`), F-0014 the next morning, when nothing ran after «… از ChatGPT
// خواسته شد و در صف است» and the hub still said «آرام» (the page says «ایستاده» with «ادامه بده»).

import { conversationCard, conversationCounts, conversationDrop, conversationFiles, conversationClosed, conversationSay, presentAdd, presentDrop, sessionConversation } from './mock-v32';
import { memoryOf, setSource, sourceOf } from './mock-v40';

const json = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const NOW = () => new Date().toISOString();
const NAME: Record<string, string> = { TY: 'تریدیار', FX: 'کوینه‌پرو اف‌ایکس', PC: 'پرو-چارت', HQ: 'هلدینگ' };

type Participant = { key: string; kind: 'holder' | 'person' | 'player'; title_fa: string; company: string | null };
type Task = { id: string; n: number; title_fa: string; state: 'todo' | 'doing' | 'done' | 'dropped'; by: 'owner' | 'agent'; who_fa: string | null; work_ref: string | null };
type S = {
  ref: string; conv: string; pace: 'auto' | 'step'; hidden: boolean; opened_at: string; closed_at: string | null; verdict: 'ok' | 'cancel' | null;
  participants: Participant[]; tasks: Task[]; turn: { question_fa: string; at: string; by: { kind: string; code: string; display_fa: string }; who_fa: string } | null;
  holder: { code: string; title_fa: string; company: string; company_fa: string } | null; persona: string; text_fa: string; last_at: string; state?: string;
  /** ⟨2026-11-11⟩ false: a session the checks open by its ref, in no list (the lists stay as they were). */
  listed?: boolean;
};
const sessions = new Map<string, S>();
/** ⟨1.19⟩ Orders erased for good: they answer 404 and never come back from the fixtures. */
const erased = new Set<string>();
let taskSeq = 0;

const holderP = (title_fa: string, company: string | null, key: string): Participant => ({ key, kind: 'holder', title_fa, company });
const task = (n: number, title_fa: string, state: Task['state'], by: Task['by'] = 'agent', who_fa: string | null = null, work_ref: string | null = null): Task => ({ id: `tk-${String(++taskSeq).padStart(4, '0')}`, n, title_fa, state, by, who_fa, work_ref });
const flag = (k: string): string | null => { try { return window.localStorage.getItem(k); } catch { return null; } };
const olderHub = () => flag('hq.e2e.old55') === '1';
const T = (day: string, hm: string) => `${day}T${hm}:00Z`;

function seed() {
  const mk = (o: Partial<S> & Pick<S, 'ref' | 'text_fa' | 'persona' | 'holder' | 'participants'>, lines: Array<[string, string, string?]>) => {
    const conv = sessionConversation(o.persona, o.text_fa, o.ref, lines, o.opened_at ?? T('2026-11-05', '08:00'));
    for (const p of o.participants.slice(1)) presentAdd(conv.ref, p.key);
    sessions.set(o.ref, { conv: conv.ref, pace: 'auto', hidden: false, opened_at: T('2026-11-05', '08:00'), closed_at: null, verdict: null, tasks: [], turn: null, last_at: T('2026-11-05', '10:00'), ...o });
    return conv;
  };
  mk({
    ref: 'F-0008', text_fa: 'سه عنوان برای خبرنامه‌ی هفته‌ی تریدیار پیشنهاد بده', persona: 'ceo@TY', pace: 'step', last_at: T('2026-11-06', '06:10'),
    holder: { code: 'TY-CEO', title_fa: 'مدیرعامل', company: 'TY', company_fa: 'تریدیار' },
    participants: [holderP('مدیرعامل تریدیار', 'TY', 'ceo@TY')],
    tasks: [task(1, 'سه عنوان بنویس', 'done', 'agent', 'مدیرعامل'), task(2, 'عنوان برگزیده را با تو هماهنگ کن', 'doing', 'agent', 'مدیرعامل'), task(3, 'متن خبرنامه را بنویس', 'todo')],
    turn: { question_fa: 'کدام عنوان بهتر است: «هفته‌ای که بازار عوض شد»، «سه نکته برای حد ضرر» یا «کارمزد را دست‌کم نگیر»؟', at: T('2026-11-06', '06:10'), by: { kind: 'employee', code: 'TY-CEO', display_fa: 'مدیرعامل تریدیار' }, who_fa: 'مدیرعامل تریدیار' },
  }, [
    ['owner', 'سه عنوان برای خبرنامه‌ی هفته‌ی تریدیار پیشنهاد بده؛ مرحله به مرحله با من جلو برو.'],
    ['ceo@TY', 'سلام مدیر کل. سه عنوان آماده کردم و قبل از نوشتن متن، نظرت را میخواهم. کدام را بنویسم؟\n\n- هفته‌ای که بازار عوض شد\n- سه نکته برای حد ضرر\n- کارمزد را دست‌کم نگیر'],
  ]);
  mk({
    ref: 'F-0007', text_fa: 'برای تریدیار کلیپ بساز و منظم منتشر کن', persona: 'media_director@TY', last_at: T('2026-11-02', '12:06'),
    holder: { code: 'TY-MEDIA-MGR', title_fa: 'مدیر رسانه', company: 'TY', company_fa: 'تریدیار' },
    participants: [holderP('مدیر رسانه تریدیار', 'TY', 'media_director@TY'), { key: 'advisor', kind: 'person', title_fa: 'مشاور کل', company: null }],
    tasks: [task(1, 'نوشتن متن سه ریلز', 'done', 'agent', 'نویسنده'), task(2, 'ساخت سه ریلز', 'done', 'agent', 'سازنده‌ی ریلز', 'W-000311'), task(3, 'مُهر سری انتشار', 'todo', 'owner'), task(4, 'استخدام مسئول انتشار', 'todo', 'owner')],
  }, [
    ['owner', 'برای تریدیار کلیپ بساز و منظم منتشر کن.'],
    ['media_director@TY', 'سه ریلز اول ساخته و بازبینی شد. برای انتشار منظم، دو چیز لازم است: مُهر سری انتشار و یک مسئول انتشار. هر دو پایین همین صفحه آماده است.'],
  ]);
  mk({
    ref: 'F-0005', text_fa: 'برای پرو-چارت سه پست معرفی ابزار تحلیل تکنیکال آماده کن', persona: 'media_director@PC', last_at: T('2026-11-02', '12:10'),
    holder: { code: 'PC-MEDIA-MGR', title_fa: 'مدیر رسانه', company: 'PC', company_fa: 'پرو-چارت' },
    participants: [holderP('مدیر رسانه پرو-چارت', 'PC', 'media_director@PC')],
    tasks: [task(1, 'پست اول', 'done'), task(2, 'پست دوم', 'done'), task(3, 'پست سوم', 'doing')],
  }, [
    ['owner', 'برای پرو-چارت سه پست معرفی ابزار تحلیل تکنیکال آماده کن.'],
    ['media_director@PC', 'دو پست از سه آماده است. پست سوم به کمی بودجه‌ی بیشتر نیاز دارد؛ دکمه‌ی افزودن بودجه همین‌جاست.'],
  ]);
  mk({
    ref: 'F-0006', text_fa: 'یک مقاله‌ی سئو برای FX درباره‌ی آموزش فارکس برای تازه‌کارها', persona: 'media_director@FX', last_at: T('2026-11-01', '06:20'),
    holder: { code: 'FX-MEDIA-MGR', title_fa: 'مدیر رسانه', company: 'FX', company_fa: 'کوینه‌پرو اف‌ایکس' },
    participants: [holderP('مدیر رسانه اف‌ایکس', 'FX', 'media_director@FX'), { key: 'player:gpt', kind: 'player', title_fa: 'جی‌پی‌تی', company: null }],
    tasks: [task(1, 'نوشتن مقاله', 'done', 'agent', 'نویسنده'), task(2, 'بازبینی و انتشار', 'done', 'agent', 'مدیر رسانه')],
  }, [
    ['owner', 'یک مقاله‌ی سئو برای FX درباره‌ی آموزش فارکس برای تازه‌کارها.'],
    ['media_director@FX', 'مقاله نوشته و در وبلاگ منتشر شد. اگر خروجی را پسندیدی، جلسه را تأیید و ببند.'],
  ]);
  mk({
    ref: 'F-0004', text_fa: 'گزارش هزینه‌ی تبلیغات اکتبر', persona: 'advisor', last_at: T('2026-10-28', '15:00'), closed_at: T('2026-10-28', '15:30'), verdict: 'ok',
    holder: null, participants: [holderP('مشاور کل', null, 'advisor')], tasks: [task(1, 'جمع کردن عددها', 'done'), task(2, 'نوشتن گزارش', 'done')],
  }, [
    ['owner', 'گزارش هزینه‌ی تبلیغات اکتبر را بده.'],
    ['advisor', 'تبلیغات اکتبر 220 دلار شد؛ بیشترین سهم با تریدیار بود. گزارش کامل ضمیمه است.'],
  ]);
  conversationClosed(sessions.get('F-0004')!.conv, T('2026-10-28', '15:30'));
  // ⟨1.23⟩ a dense session: many system steps (two runs of them between real turns), two outputs, two blockers, a long answer.
  mk({
    ref: 'F-0009', text_fa: 'برای پرو-چارت یک کمپین یک‌هفته‌ای آموزشی راه بینداز', persona: 'media_director@PC', opened_at: T('2026-11-07', '08:00'), last_at: T('2026-11-07', '09:25'),
    holder: { code: 'PC-MEDIA-MGR', title_fa: 'مدیر رسانه', company: 'PC', company_fa: 'پرو-چارت' },
    participants: [holderP('مدیر رسانه پرو-چارت', 'PC', 'media_director@PC')],
    tasks: [task(1, 'برنامه‌ی هفته', 'done'), task(2, 'ساخت دو ریلز', 'done'), task(3, 'مُهر سری انتشار', 'todo', 'owner'), task(4, 'استخدام مسئول انتشار', 'todo', 'owner')],
  }, [
    ['owner', 'برای پرو-چارت یک کمپین یک‌هفته‌ای آموزشی راه بینداز.', T('2026-11-07', '08:00')],
    ['media_director@PC', 'فرمانت را گرفتم. اول برنامه‌ی هفته را میچینم و بعد ریلزها را میسازم.', T('2026-11-07', '08:05')],
    ['owner', 'خوب است؛ فقط حتماً هر شب یک گزارش کوتاه بده.', T('2026-11-07', '08:40')],
    ['media_director@PC', 'برنامه‌ی هفته به این شکل شد:\n\n1. شنبه: معرفی ابزار خط روند با یک ریلز کوتاه و یک پست ثابت\n2. یکشنبه: آموزش هشدار قیمت، از ساختن اولین هشدار تا دریافت آن روی تلگرام\n3. دوشنبه: پرسش و پاسخ زنده با کاربران درباره‌ی اشتباه‌های رایج در تحلیل تکنیکال\n4. سه‌شنبه: مقایسه‌ی دو روش ترسیم حمایت و مقاومت، با نمونه‌ی واقعی\n5. چهارشنبه: ریلز بلند درباره‌ی مدیریت ریسک و حد ضرر\n\nبرای هر روز یک متن، یک تصویر و یک ریلز آماده میکنم و هر شب گزارش کوتاهی برایت مینویسم. دو ریلز اول ساخته شده و پایین همین صفحه است؛ برای انتشار منظم دو چیز از تو لازم است: مُهر سری انتشار و یک مسئول انتشار.', T('2026-11-07', '09:00')],
  ]);
  // ⟨1.0.1⟩ a workshop turn that builds: the build ring fills against its 60 minutes.
  mk({
    ref: 'F-0010', text_fa: 'برای پرو-چارت یک موشن‌گرافی ۳۰ ثانیه‌ای درباره‌ی اندیکاتور ATR بساز', persona: 'media_director@PC', opened_at: T('2026-11-10', '07:00'), last_at: T('2026-11-10', '07:30'),
    holder: { code: 'PC-MEDIA-MGR', title_fa: 'مدیر رسانه', company: 'PC', company_fa: 'پرو-چارت' },
    participants: [holderP('مدیر رسانه پرو-چارت', 'PC', 'media_director@PC')],
    tasks: [task(1, 'نوشتن سناریو', 'done', 'agent', 'نویسنده'), task(2, 'ساخت موشن‌گرافی در کارگاه', 'doing', 'agent', 'سازنده‌ی موشن‌گرافی', 'W-000312'), task(3, 'بازبینی و تحویل', 'todo')],
  }, [
    ['owner', 'برای پرو-چارت یک موشن‌گرافی ۳۰ ثانیه‌ای درباره‌ی اندیکاتور ATR بساز.', T('2026-11-10', '07:00')],
    ['media_director@PC', 'سناریو آماده شد و ساخت را به کارگاه سپردم. تا یک ساعت دیگر فایل همین‌جا میرسد.', T('2026-11-10', '07:20')],
  ]);
  // ⟨1.0.1⟩ §54 a direct session: its holder is one session with the hub's tools and does the work himself.
  mk({
    ref: 'F-0011', text_fa: 'برای تریدیار کپشن سه ریلز این هفته را بنویس', persona: 'media_director@TY', opened_at: T('2026-11-10', '08:00'), last_at: T('2026-11-10', '08:10'),
    holder: { code: 'TY-MEDIA-MGR', title_fa: 'مدیر رسانه', company: 'TY', company_fa: 'تریدیار' },
    participants: [holderP('مدیر رسانه تریدیار', 'TY', 'media_director@TY')],
    tasks: [task(1, 'کپشن سه ریلز', 'doing', 'agent', 'مدیر رسانه', 'W-000313'), task(2, 'هشتگ‌ها', 'todo')],
  }, [
    ['owner', 'برای تریدیار کپشن سه ریلز این هفته را بنویس.', T('2026-11-10', '08:00')],
    ['media_director@TY', 'خودم مینویسم؛ تا چند دقیقه‌ی دیگر هر سه کپشن همین‌جاست.', T('2026-11-10', '08:02')],
  ]);
  // ⟨1.0.1⟩ ready for his OK, with a reel to publish: what the session waits on is in its decision bar.
  mk({
    ref: 'F-0012', text_fa: 'برای تریدیار یک ریلز درباره‌ی جای درست حد ضرر بساز', persona: 'media_director@TY', opened_at: T('2026-11-10', '05:00'), last_at: T('2026-11-10', '06:20'),
    holder: { code: 'TY-MEDIA-MGR', title_fa: 'مدیر رسانه', company: 'TY', company_fa: 'تریدیار' },
    participants: [holderP('مدیر رسانه تریدیار', 'TY', 'media_director@TY')],
    tasks: [task(1, 'نوشتن متن', 'done', 'agent', 'نویسنده'), task(2, 'ساخت ریلز', 'done', 'agent', 'سازنده‌ی ریلز')],
  }, [
    ['owner', 'برای تریدیار یک ریلز درباره‌ی جای درست حد ضرر بساز.', T('2026-11-10', '05:00')],
    ['media_director@TY', 'ریلز ساخته شد و با کاورش پایین همین صفحه است. اگر خوب است، تأیید کن تا منتشر شود.', T('2026-11-10', '06:20')],
  ]);
  // ⟨2026-11-11⟩ the owner's 12-hour stall, while the draft waits in ChatGPT's queue, and the next morning
  const ago41 = (sec: number) => new Date(Date.now() - sec * 1000).toISOString();
  const pc = { code: 'PC-CEO', title_fa: 'مدیرعامل', company: 'PC', company_fa: 'پرو-چارت' };
  mk({
    ref: 'F-0013', text_fa: 'هر روز یک ریلز آموزشی برای پرو-چارت بساز؛ قدم به قدم با من جلو برو', persona: 'ceo@PC', pace: 'step', listed: false,
    opened_at: ago41(40 * 60), last_at: ago41(4 * 60), holder: pc, participants: [holderP('مدیرعامل پرو-چارت', 'PC', 'ceo@PC')], tasks: reelsPlan(),
  }, [
    ['owner', 'هر روز یک ریلز آموزشی برای پرو-چارت بساز؛ قدم به قدم با من جلو برو.', ago41(40 * 60)],
    ['ceo@PC', 'سلام مدیر کل. سناریست را استخدام میکنم، گوینده را یک‌بار تنظیم میکنم و هر قدم را با تو جلو میبرم.', ago41(38 * 60)],
    ['owner', 'خودت تصمیم بگیر و ادامه بده', ago41(6 * 60)],
    ['ceo@PC', DRAFT_ASKED_FA, ago41(4 * 60)],
  ]);
  mk({
    ref: 'F-0014', text_fa: 'به هرچه میگویم دقت کن و هر روز یک ریلز برای پرو-چارت بساز؛ قدم به قدم با من', persona: 'ceo@PC', pace: 'step', listed: false,
    opened_at: ago41(830 * 60), last_at: ago41(812 * 60), holder: pc, participants: [holderP('مدیرعامل پرو-چارت', 'PC', 'ceo@PC')], tasks: reelsPlan(),
  }, [
    ['owner', 'به هرچه میگویم دقت کن و هر روز یک ریلز برای پرو-چارت بساز؛ قدم به قدم با من.', ago41(830 * 60)],
    ['ceo@PC', '**سؤال از تو** · گام ۱ انجام شد (استخدام سناریست و روش موضوع روزانه). تأیید یا اصلاح؟ اگر تأیید است، گام ۲ (متن گوینده و تنظیم یک‌بارِ صدا) را شروع کنم؟', ago41(815 * 60)],
    ['owner', 'خودت تصمیم بگیر و ادامه بده', ago41(813 * 60)],
  ]);
}
/** The eighteen steps of Pro-Chart's daily reels («با من»): two done, the third in hand. */
const REELS_PLAN = [
  'استخدام سناریست و روش موضوع روزانه', 'متن گوینده و تنظیم یک‌بار صدا', 'پیش‌نویس متن ریلز اول با ChatGPT', 'خواندن متن با صدای گوینده',
  'موشن‌گرافی ریلز اول', 'کاور ریلز اول', 'کپشن و کلمه‌ی کامنت', 'تأیید و انتشار ریلز اول', 'خواندن بازخورد ریلز اول',
  'موضوع روز دوم', 'متن روز دوم', 'صدا و موشن‌گرافی روز دوم', 'انتشار روز دوم', 'پیدا کردن بهترین ساعت انتشار',
  'کارگروه روزانه‌ی ریلز', 'انتشار خودکار هر روز', 'گزارش هفته‌ی اول', 'جمع‌بندی و بستن',
];
function reelsPlan(): Task[] { return REELS_PLAN.map((t, i) => task(i + 1, t, i < 2 ? 'done' : i === 2 ? 'doing' : 'todo', 'agent', 'مدیرعامل پرو-چارت')); }
/** The holder's last word of the owner's 12-hour stall, as it was (F-0014), and while the draft is in ChatGPT's queue (F-0013). */
const STALLED_FA = 'گام ۲ در جریان است. موضوع اول («معرفی ابزارهای ترسیم روی نمودار پرو-چارت») ثبت شد. گوینده‌ی ثابت پرو-چارت (Kore، فارسی معیار و گرم) یک‌بار برای همیشه تنظیم شد. '
  + 'پیش‌نویس متن ۱ تا ۱:۳۰ دقیقه با شعار «پرو چارت؛ همیشه با نمودار» و کلمه‌ی کامنت «چارت» از ChatGPT خواسته شد و در صف است.';
const DRAFT_ASKED_FA = 'پیش‌نویس متن ریلز اول از ChatGPT خواسته شد و در صف است؛ تا جوابش برسد، کاور را آماده میکنم.';
seed();

// -------------------------------------------------------------------------------------- ⟨1.23⟩ §41 live activity
type Line41 = { at: string; who_fa: string; text_fa: string; id?: string; company?: string | null; kind?: string; state?: 'running' | 'done' | 'failed'; task_n?: number | null };
type Work41 = {
  who_fa: string; company_fa: string; work_title_fa: string; started_at: string; step: number; doing_fa: string;
  kind?: 'run' | 'workshop' | 'direct' | 'server' | 'call'; cap_s?: number | null; last_fa?: string | null; last_at?: string | null;
};
type Act41 = { working: Work41[]; last: Line41[]; idle_since: string | null; waiting_fa: string | null; stuck_fa: string | null };
const MOOD_FA: Record<string, string> = { thinking: 'فکر میکند', working: 'کار میکند', waiting: 'منتظر تو', stuck: 'گیر کرده', idle: 'آرام' };
/** §55.1 the mood, by the hub's own rule: someone works (still thinking until a run's first step, or a turn's first act); else it waits for the owner; else stuck; else calm. */
const moodOf = (a: Act41): string => {
  if (a.working.length) return a.working.some((w) => ((w.kind ?? 'run') === 'run' ? w.step > 0 : w.kind === 'call' || w.last_fa != null)) ? 'working' : 'thinking';
  return a.waiting_fa ? 'waiting' : a.stuck_fa ? 'stuck' : 'idle';
};
/** The activity as the hub of §55 answers it; a hub before §55 says neither the mood nor a worker's kind, cap or last line. */
const actView = (a: Act41) => (olderHub()
  ? { ...a, working: a.working.map(({ kind: _k, cap_s: _c, last_fa: _l, last_at: _a, ...w }) => w) }
  : { ...a, working: a.working.map((w) => ({ kind: 'run', cap_s: null, last_fa: null, last_at: null, ...w })), mood: moodOf(a), mood_fa: MOOD_FA[moodOf(a)] });
/** What a live turn of the workshop says of itself, in the owner's words (never a path, never a command). */
const TURN_SAYS = ['صحنه‌ی ۳ را رندر میکند', 'فایل «scene-4.tsx» را مینویسد', 'دستور اجرا میکند', 'صحنه‌ی ۴ را رندر میکند', 'فایل «caption.md» را مینویسد'];
const activity = new Map<string, Act41>();
/** The workers the owner stopped with «نگه دار», by session: «ادامه بده» brings them back. */
const held = new Map<string, Work41[]>();
let actSeq = 0;
const SAYS = ['سایت pro-chart.com را خواند', 'از ChatGPT پرسید', 'پیش‌نویس سناریوی ریلز را نوشت', 'صدای گوینده را ساخت', 'تصویر کاور را انتخاب کرد', 'خروجی را برای بازبینی تحویل داد'];
const ago41 = (sec: number) => new Date(Date.now() - sec * 1000).toISOString();
/** The activity of a session, made on first look: F-0007 is working (its lines stream with the mock stream), F-0005 is stuck, F-0008 waits
 *  for the owner, the rest are quiet. ⟨1.24⟩ §42.2: each line has its id (run + step), kind and state; a working session's last step runs. */
function actOf(s: S): Act41 {
  let a = activity.get(s.ref);
  if (a) return a;
  const who = s.holder ? `${s.holder.title_fa} ${s.holder.company_fa}` : 'مشاور کل';
  const co = s.holder?.company ?? null;
  const lines = (n: number, running = false): Line41[] => SAYS.slice(0, n).map((t, i) => ({
    id: `run-${s.ref}-${i + 1}`, at: ago41((n - i) * 40), who_fa: who, company: co, text_fa: t, kind: i === 0 ? 'start' : 'step', state: running && i === n - 1 ? 'running' : 'done', task_n: null,
  }));
  if (s.ref === 'F-0007' && flag('hq.e2e.mood') === 'thinking') a = { working: [{ who_fa: who, company_fa: s.holder?.company_fa ?? '', work_title_fa: 'ساخت سه ریلز', started_at: ago41(8), step: 0, doing_fa: '' }], last: [], idle_since: null, waiting_fa: null, stuck_fa: null };
  else if (s.ref === 'F-0007') {
    a = { working: [{ who_fa: who, company_fa: s.holder?.company_fa ?? '', work_title_fa: 'ساخت سه ریلز', started_at: ago41(95), step: 3, doing_fa: SAYS[2]! }], last: lines(3, true), idle_since: null, waiting_fa: null, stuck_fa: null };
    if (flag('hq.e2e.workers') === '2') a.working.push({ who_fa: 'نویسنده', company_fa: s.holder?.company_fa ?? '', work_title_fa: 'نوشتن کپشن ریلزها', started_at: ago41(40), step: 1, doing_fa: 'کپشن ریلز دوم را مینویسد', kind: 'server' });
  } else if (s.ref === 'F-0010') {
    const late = flag('hq.e2e.ring') === 'late';
    a = {
      working: [{ who_fa: 'سازنده‌ی موشن‌گرافی', company_fa: s.holder?.company_fa ?? '', work_title_fa: 'ساخت موشن‌گرافی ATR', started_at: ago41((late ? 56 : 23) * 60), step: 0, doing_fa: 'موشن‌گرافی را میسازد', kind: 'workshop', cap_s: 3600, last_fa: TURN_SAYS[0]!, last_at: ago41(12) }],
      last: [
        { id: `turn-${s.ref}-1`, at: ago41(22 * 60), who_fa: 'سازنده‌ی موشن‌گرافی', company: co, text_fa: 'کار را در کارگاه شروع کرد', kind: 'start', state: 'done', task_n: 2 },
        { id: `turn-${s.ref}-2`, at: ago41(9 * 60), who_fa: 'سازنده‌ی موشن‌گرافی', company: co, text_fa: 'صحنه‌ی ۲ را رندر کرد', kind: 'step', state: 'done', task_n: 2 },
        { id: `turn-${s.ref}-3`, at: ago41(12), who_fa: 'سازنده‌ی موشن‌گرافی', company: co, text_fa: TURN_SAYS[0]!, kind: 'step', state: 'running', task_n: 2 },
      ],
      idle_since: null, waiting_fa: null, stuck_fa: null,
    };
  } else if (s.ref === 'F-0011') {
    a = {
      working: [{ who_fa: who, company_fa: s.holder?.company_fa ?? '', work_title_fa: 'کپشن سه ریلز', started_at: ago41(6 * 60), step: 0, doing_fa: 'روی فرمان کار میکند', kind: 'direct', cap_s: 3600, last_fa: TURN_SAYS[4]!, last_at: ago41(8) }],
      last: [{ id: `turn-${s.ref}-1`, at: ago41(8), who_fa: who, company: co, text_fa: TURN_SAYS[4]!, kind: 'step', state: 'running', task_n: 1 }],
      idle_since: null, waiting_fa: null, stuck_fa: null,
    };
  }
  else if (s.ref === 'F-0013') {
    a = {
      working: [{ who_fa: 'ChatGPT', company_fa: 'پرو-چارت', work_title_fa: 'پیش‌نویس متن ریلز اول', started_at: ago41(4 * 60), step: 0, doing_fa: 'در صف ChatGPT: پیش‌نویس متن', kind: 'call', cap_s: 900, last_fa: null, last_at: ago41(4 * 60) }],
      last: [
        { id: `run-${s.ref}-1`, at: ago41(5 * 60), who_fa: who, company: co, text_fa: 'دوباره سر کار آمد', kind: 'start', state: 'done', task_n: null },
        { id: `run-${s.ref}-2`, at: ago41(4 * 60), who_fa: who, company: co, text_fa: 'از ChatGPT پرسید', kind: 'step', state: 'done', task_n: 3 },
      ],
      idle_since: null, waiting_fa: null, stuck_fa: null,
    };
  } else if (s.ref === 'F-0014') {
    // As the hub said it that night: nobody works, nothing waits for the owner, nothing is stuck: «آرام».
    a = {
      working: [],
      last: [
        { id: `run-${s.ref}-1`, at: ago41(812 * 60 + 40), who_fa: who, company: co, text_fa: 'حرف تو را گرفت و دارد فکر میکند', kind: 'start', state: 'done', task_n: null },
        { id: `run-${s.ref}-2`, at: ago41(812 * 60), who_fa: who, company: co, text_fa: STALLED_FA, kind: 'step', state: 'done', task_n: null },
        { id: `run-${s.ref}-3`, at: ago41(812 * 60 - 5), who_fa: who, company: co, text_fa: 'این دور کارش را تمام کرد', kind: 'end', state: 'done', task_n: null },
      ],
      idle_since: ago41(812 * 60 - 5), waiting_fa: null, stuck_fa: null,
    };
  }
  else if (s.ref === 'F-0005') a = { working: [], last: lines(2), idle_since: ago41(1500), waiting_fa: null, stuck_fa: 'بودجه‌ی پست سوم تمام شده؛ بودجه را اضافه کن یا بگو ادامه بدهم.' };
  else if (s.ref === 'F-0008') a = { working: [], last: lines(1), idle_since: ago41(300), waiting_fa: 'انتخاب یکی از سه عنوان', stuck_fa: null };
  else a = { working: [], last: s.closed_at ? [] : lines(1), idle_since: ago41(600), waiting_fa: null, stuck_fa: null };
  activity.set(s.ref, a);
  return a;
}
/** One tick of the demo's stream: every working session ends its running step (the same line, now done) and starts the next
 *  (`session.activity` {order, line, working}). */
export function tickActivity(): Array<{ id: string; type: string; at: string; company: string | null; ref: string | null; data: Record<string, unknown> }> {
  const out = [];
  for (const s of sessions.values()) {
    const a = actOf(s);
    const w = a.working[0];
    if (!w || s.closed_at) continue;
    // an outside call takes no steps of its own: it is there until its answer comes
    if (a.working.every((x) => x.kind === 'call')) continue;
    const co = s.holder?.company ?? null;
    const open = a.last.findIndex((l) => l.state === 'running');
    if (open >= 0) {
      const done: Line41 = { ...a.last[open]!, state: 'done' };
      a.last = a.last.map((l, i) => (i === open ? done : l));
      out.push({ id: `d34-${++actSeq}`, type: 'session.activity', at: NOW(), company: co, ref: s.ref, data: { order: s.ref, line: done, working: a.working.length } });
    }
    w.step += 1;
    const turn = w.kind === 'workshop' || w.kind === 'direct';
    if (turn) { w.last_fa = TURN_SAYS[w.step % TURN_SAYS.length]!; w.last_at = NOW(); } else w.doing_fa = SAYS[w.step % SAYS.length]!;
    const line: Line41 = { id: `run-${s.ref}-${w.step}`, at: NOW(), who_fa: w.who_fa, company: co, text_fa: turn ? w.last_fa! : w.doing_fa, kind: 'step', state: 'running', task_n: null };
    a.last = [...a.last, line].slice(-30);
    out.push({ id: `d34-${++actSeq}`, type: 'session.activity', at: line.at, company: co, ref: s.ref, data: { order: s.ref, line, working: a.working.length } });
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------- the report
function badgeOf(s: S, rep: any): { badge: 'your_turn' | 'ready' | 'stuck' | 'moving' | 'closed'; reason_fa: string } {
  if (s.closed_at) return { badge: 'closed', reason_fa: s.verdict === 'cancel' ? 'لغو شد و بایگانی شد.' : 'تأیید شد و بایگانی شد.' };
  if (s.turn) return { badge: 'your_turn', reason_fa: `${s.turn.who_fa} میپرسد: ${s.turn.question_fa.slice(0, 60)}${s.turn.question_fa.length > 60 ? '…' : ''}` };
  if (rep?.state === 'delivered') return { badge: 'ready', reason_fa: 'کار تمام شده؛ منتظر تأیید توست.' };
  const fixable = (rep?.blockers ?? []).find((b: any) => b.fix);
  if (fixable) return { badge: 'your_turn', reason_fa: `${fixable.title_fa}؛ رفعش با توست.` };
  if ((rep?.blockers ?? []).length) return { badge: 'stuck', reason_fa: rep.blockers[0].title_fa };
  return { badge: 'moving', reason_fa: rep?.steps?.at(-1)?.what_fa ?? 'کار در جریان است.' };
}
function briefOf(rep: any, s: S) {
  const last = rep?.steps?.at(-1)?.what_fa;
  return {
    done_fa: rep?.summary?.done_fa ?? s.tasks.filter((t) => t.state === 'done').at(-1)?.title_fa ?? 'هنوز چیزی تمام نشده.',
    now_fa: s.turn ? 'منتظر جواب توست.' : rep?.blockers?.[0]?.title_fa ?? last ?? 'کار در جریان است.',
    need_fa: s.turn ? 'جواب سؤال بالا' : rep?.summary?.need_fa ?? rep?.blockers?.find((b: any) => b.fix)?.fix?.label_fa ?? 'چیزی از تو لازم نیست.',
  };
}
const counts = (s: S) => ({ done: s.tasks.filter((t) => t.state === 'done').length, total: s.tasks.filter((t) => t.state !== 'dropped').length });

/** The report of an order the session module made itself (the others come from §29's fixtures, decorated). */
const LOCAL: Record<string, any> = {
  'F-0008': {
    ref: 'F-0008', text_fa: 'سه عنوان برای خبرنامه‌ی هفته‌ی تریدیار پیشنهاد بده', at: T('2026-11-05', '08:00'), state: 'waiting',
    ack: { at: T('2026-11-05', '08:01'), by: { kind: 'employee', code: 'TY-CEO', display_fa: 'مدیرعامل تریدیار' }, plan_fa: 'مدیرعامل سه عنوان مینویسد، با مدیر کل یکی را انتخاب میکند و بعد متن را مینویسد.', assigned: [{ company: 'TY', code: 'TY-CEO', title_fa: 'مدیرعامل' }], due_at: null },
    route: { companies: ['TY'], department: null, collaborators: [], output_kind: 'answer', budget_tokens: 60_000, mode: 'single', player: 'auto' },
    steps: [{ at: T('2026-11-05', '08:00'), who_fa: 'منشی هلدینگ', what_fa: 'فرمان را به مدیرعامل تریدیار سپرد.' }, { at: T('2026-11-06', '06:10'), who_fa: 'مدیرعامل تریدیار', what_fa: 'سه عنوان نوشت و از تو سؤال کرد.' }],
    blockers: [], outputs: [], summary: null, updated_at: T('2026-11-06', '06:10'),
  },
  'F-0009': {
    ref: 'F-0009', text_fa: 'برای پرو-چارت یک کمپین یک‌هفته‌ای آموزشی راه بینداز', at: T('2026-11-07', '08:00'), state: 'in_progress',
    ack: { at: T('2026-11-07', '08:01'), by: { kind: 'employee', code: 'PC-MEDIA-MGR', display_fa: 'مدیر رسانه پرو-چارت' }, plan_fa: 'مدیر رسانه برنامه‌ی پنج روزه میچیند، ریلزها را میسازد و برای انتشار مُهر تو را میخواهد.', assigned: [{ company: 'PC', code: 'PC-MEDIA-MGR', title_fa: 'مدیر رسانه' }], due_at: null },
    route: { companies: ['PC'], department: 'MEDIA', collaborators: [], output_kind: 'reel', budget_tokens: 300_000, mode: 'single', player: 'auto' },
    steps: [{ at: T('2026-11-07', '08:00'), who_fa: 'منشی هلدینگ', what_fa: 'فرمان را به رسانه‌ی پرو-چارت سپرد. (F-0009)' },
      { at: T('2026-11-07', '08:10'), who_fa: 'مدیر رسانه', what_fa: 'برنامه‌ی پنج روزه را نوشت. (W-000201)' },
      { at: T('2026-11-07', '08:12'), who_fa: 'مدیر رسانه', what_fa: 'سایت pro-chart.com را خواند.' },
      { at: T('2026-11-07', '08:15'), who_fa: 'مدیر رسانه', what_fa: 'از ChatGPT پرسید. (O-000071)' },
      { at: T('2026-11-07', '08:20'), who_fa: 'نویسنده', what_fa: 'متن ریلز اول را نوشت و برای بازبینی گذاشت، با سه خط توضیح درباره‌ی لحن، طول و کلمه‌های کلیدی که باید در زیرنویس بیاید.' },
      { at: T('2026-11-07', '08:30'), who_fa: 'سازنده‌ی ریلز', what_fa: 'صدای گوینده را ساخت.' },
      { at: T('2026-11-07', '09:10'), who_fa: 'سازنده‌ی ریلز', what_fa: 'ریلز اول را ساخت و تحویل داد. (O-000071)' },
      { at: T('2026-11-07', '09:15'), who_fa: 'سازنده‌ی ریلز', what_fa: 'ریلز دوم را ساخت و تحویل داد. (D-000090)' },
      { at: T('2026-11-07', '09:25'), who_fa: 'مدیر رسانه', what_fa: 'انتشار منتظر ماند: سری انتشار هنوز مُهر نشده و مسئول انتشار نیست.' }],
    blockers: [{ kind: 'series_unsealed', title_fa: 'سری انتشار مُهر نشده', detail_fa: 'ریلزها آماده است، ولی سری هنوز مُهر تو را ندارد.', since: T('2026-11-07', '09:25'), fix: { action: 'series.seal', label_fa: 'مُهر سری انتشار', target: 'SR-0013' } },
      { kind: 'no_employee', title_fa: 'مسئول انتشار نیست', detail_fa: 'جایگاه مسئول انتشار پرو-چارت خالی است.', since: T('2026-11-07', '09:25'), fix: { action: 'hire', label_fa: 'استخدام مسئول انتشار', target: 'PC/publisher' } }],
    outputs: [{ ref: 'O-000071', title_fa: 'ریلز ۱: معرفی ابزار خط روند', kind: 'reel' }, { ref: 'O-000072', title_fa: 'ریلز ۲: ساختن اولین هشدار قیمت', kind: 'reel' }],
    summary: null, updated_at: T('2026-11-07', '09:25'),
  },
  'F-0010': {
    ref: 'F-0010', text_fa: 'برای پرو-چارت یک موشن‌گرافی ۳۰ ثانیه‌ای درباره‌ی اندیکاتور ATR بساز', at: T('2026-11-10', '07:00'), state: 'in_progress',
    ack: { at: T('2026-11-10', '07:01'), by: { kind: 'employee', code: 'PC-MEDIA-MGR', display_fa: 'مدیر رسانه پرو-چارت' }, plan_fa: 'نویسنده سناریو را مینویسد و کارگاه هلدینگ موشن‌گرافی را میسازد؛ فایل در همین جلسه میرسد.', assigned: [{ company: 'PC', code: 'PC-MEDIA-MGR', title_fa: 'مدیر رسانه' }], due_at: null },
    route: { companies: ['PC'], department: 'MEDIA', collaborators: [], output_kind: 'reel', budget_tokens: 600_000, mode: 'single', player: 'auto' },
    steps: [{ at: T('2026-11-10', '07:00'), who_fa: 'منشی هلدینگ', what_fa: 'فرمان را به رسانه‌ی پرو-چارت سپرد.' }, { at: T('2026-11-10', '07:18'), who_fa: 'نویسنده', what_fa: 'سناریوی موشن‌گرافی را نوشت.' }],
    blockers: [], outputs: [], summary: null, updated_at: T('2026-11-10', '07:30'),
  },
  'F-0011': {
    ref: 'F-0011', text_fa: 'برای تریدیار کپشن سه ریلز این هفته را بنویس', at: T('2026-11-10', '08:00'), state: 'in_progress',
    ack: null, route: { companies: ['TY'], department: 'MEDIA', collaborators: [], output_kind: 'answer', budget_tokens: 120_000, mode: 'single', player: 'auto' },
    steps: [{ at: T('2026-11-10', '08:00'), who_fa: 'منشی هلدینگ', what_fa: 'فرمان را به مدیر رسانه‌ی تریدیار سپرد.' }],
    blockers: [], outputs: [], summary: null, updated_at: T('2026-11-10', '08:10'),
  },
  'F-0012': {
    ref: 'F-0012', text_fa: 'برای تریدیار یک ریلز درباره‌ی جای درست حد ضرر بساز', at: T('2026-11-10', '05:00'), state: 'delivered',
    ack: null, route: { companies: ['TY'], department: 'MEDIA', collaborators: [], output_kind: 'reel', budget_tokens: 400_000, mode: 'single', player: 'auto' },
    steps: [{ at: T('2026-11-10', '05:00'), who_fa: 'منشی هلدینگ', what_fa: 'فرمان را به رسانه‌ی تریدیار سپرد.' }, { at: T('2026-11-10', '05:40'), who_fa: 'نویسنده', what_fa: 'متن ریلز را نوشت.' }, { at: T('2026-11-10', '06:18'), who_fa: 'سازنده‌ی ریلز', what_fa: 'ریلز را ساخت و تحویل داد.' }],
    blockers: [], outputs: [{ ref: 'O-000067', title_fa: 'ریلز: حد ضرر را کجا بگذاریم', kind: 'reel' }],
    summary: { done_fa: 'ریلز ۳۰ ثانیه‌ای با کاور ساخته شد.', left_fa: '', need_fa: 'اگر خوب است، تأیید کن تا منتشر شود.' }, updated_at: T('2026-11-10', '06:20'),
  },
  'F-0013': {
    ref: 'F-0013', text_fa: 'هر روز یک ریلز آموزشی برای پرو-چارت بساز؛ قدم به قدم با من جلو برو', at: ago41(40 * 60), state: 'in_progress',
    ack: null, route: { companies: ['PC'], department: 'MEDIA', collaborators: [], output_kind: 'reel', budget_tokens: 600_000, mode: 'single', player: 'auto' },
    steps: [{ at: ago41(38 * 60), who_fa: 'منشی هلدینگ', what_fa: 'فرمان را به مدیرعامل پرو-چارت سپرد.' }, { at: ago41(4 * 60), who_fa: 'مدیرعامل پرو-چارت', what_fa: DRAFT_ASKED_FA }],
    blockers: [], outputs: [], summary: null, updated_at: ago41(4 * 60),
  },
  'F-0014': {
    ref: 'F-0014', text_fa: 'به هرچه میگویم دقت کن و هر روز یک ریلز برای پرو-چارت بساز؛ قدم به قدم با من', at: ago41(830 * 60), state: 'in_progress',
    ack: null, route: { companies: ['PC'], department: 'MEDIA', collaborators: [], output_kind: 'reel', budget_tokens: 600_000, mode: 'single', player: 'auto' },
    steps: [
      { at: ago41(828 * 60), who_fa: 'منشی هلدینگ', what_fa: 'فرمان را به مدیرعامل پرو-چارت سپرد.' },
      { at: ago41(818 * 60), who_fa: 'مدیرعامل پرو-چارت', what_fa: 'روش موضوع بدون تکرار: سناریست هر روز با ChatGPT موضوع پیشنهاد میدهد و با دفتر موضوعات ثبت میکند؛ موضوع تکراری خودکار رد میشود.' },
      { at: ago41(815 * 60), who_fa: 'مدیرعامل پرو-چارت', what_fa: 'سناریست ریلز پرو-چارت استخدام شد و به همین جلسه آمد.' },
      { at: ago41(812 * 60), who_fa: 'مدیرعامل پرو-چارت', what_fa: STALLED_FA },
    ],
    blockers: [], outputs: [], summary: null, updated_at: ago41(812 * 60),
  },
  'F-0004': {
    ref: 'F-0004', text_fa: 'گزارش هزینه‌ی تبلیغات اکتبر', at: T('2026-10-28', '14:00'), state: 'delivered',
    ack: null, route: { companies: ['HQ'], department: null, collaborators: [], output_kind: 'report', budget_tokens: 80_000, mode: 'single', player: 'auto' },
    steps: [{ at: T('2026-10-28', '14:00'), who_fa: 'مشاور کل', what_fa: 'عددها را جمع کرد.' }, { at: T('2026-10-28', '15:00'), who_fa: 'مشاور کل', what_fa: 'گزارش را نوشت.' }],
    blockers: [], outputs: [], summary: { done_fa: 'تبلیغات اکتبر 220 دلار شد؛ گزارش نوشته شد.', left_fa: '', need_fa: '' }, updated_at: T('2026-10-28', '15:30'),
  },
};

function decorate(rep: any, s: S) {
  const { badge, reason_fa } = badgeOf(s, rep);
  const state = s.closed_at ? (s.verdict === 'cancel' ? 'cancelled' : 'delivered') : rep.state;
  return {
    ...rep, state, pace: s.pace, talk_ref: s.conv, conversation_ref: s.conv, turn: s.turn,
    session: { state: s.closed_at ? 'closed' : 'open', badge, reason_fa, closed_at: s.closed_at, hidden: s.hidden, source: sourceOf(s.ref) },
    memory_md: memoryOf(s.ref),
    brief: briefOf(rep, s), tasks: s.tasks, participants: s.participants,
    // ⟨1.18⟩ §36.3 the files of the owner's turns belong to the order, newest first
    files: conversationFiles(s.conv),
    // ⟨1.0.1⟩ §54 the holder of a direct session does the work himself
    ...(olderHub() ? {} : { direct: s.ref === 'F-0011' }),
  };
}
const card = (s: S, rep: any) => {
  const { badge, reason_fa } = badgeOf(s, rep);
  return {
    ref: s.ref, conversation_ref: s.conv, title_fa: s.text_fa.slice(0, 80), holder: s.holder, badge, reason_fa, brief: briefOf(rep, s), pace: s.pace,
    participants: s.participants, tasks: counts(s), opened_at: s.opened_at, last_at: s.last_at, closed_at: s.closed_at, hidden: s.hidden, source: sourceOf(s.ref),
  };
};

// ------------------------------------------------------------------------------------------------- the canvas
const nodePlace: Record<string, { x: number | null; y: number | null }> = { HQ: { x: null, y: null }, TY: { x: null, y: null }, FX: { x: 0.82, y: 0.3 }, PC: { x: null, y: null } };
const LINE: Record<string, string> = { HQ: 'هلدینگ · مرکز', TY: 'تریدیار · رسانه و رشد', FX: 'اف‌ایکس · مقاله و سئو', PC: 'پرو-چارت · پست و ابزار' };
type Link = { id: string; from: string; to: string; kind: string; purpose_fa: string; state: 'on' | 'off'; open_works: number; updated_at: string };
const links: Link[] = [
  { id: 'lk-0001', from: 'TY', to: 'PC', kind: 'publishes', purpose_fa: 'ریلزهای تریدیار را روی صفحه‌ی پرو-چارت هم منتشر میکند.', state: 'on', open_works: 2, updated_at: T('2026-11-04', '10:00') },
  { id: 'lk-0002', from: 'PC', to: 'TY', kind: 'feeds', purpose_fa: 'عددهای استفاده‌ی ابزار را برای محتوای تریدیار میدهد.', state: 'on', open_works: 0, updated_at: T('2026-11-04', '10:05') },
  { id: 'lk-0003', from: 'FX', to: 'TY', kind: 'supports', purpose_fa: 'پشتیبانی مشتری‌های تریدیار را هم جواب میدهد.', state: 'off', open_works: 0, updated_at: T('2026-11-03', '09:00') },
];
let linkSeq = 3;
const canvas = () => ({
  nodes: Object.keys(NAME).map((code) => ({
    code, name_fa: NAME[code]!, kind: code === 'HQ' ? 'holding' : 'company', x: nodePlace[code]!.x, y: nodePlace[code]!.y, line_fa: LINE[code]!,
    open_sessions: [...sessions.values()].filter((s) => !s.closed_at && s.listed !== false && s.holder?.company === code).length,
  })),
  links,
});

// --------------------------------------------------------------------------------------------------- persons
const COMPANY_OF = (k: string) => (k.includes('@') ? k.split('@')[1]! : null);
const ROLE_FA: Record<string, string> = { ceo: 'مدیرعامل', cto: 'مدیر فنی', media_director: 'مدیر رسانه', content_lead: 'مدیر محتوا' };
const FIXED_FA: Record<string, string> = { advisor: 'مشاور کل', overseer: 'ناظر کل', assistant: 'دستیار شخصی', secretary: 'منشی هلدینگ' };
const PLAYER_FA: Record<string, string> = { gpt: 'جی‌پی‌تی', gemini: 'جمنای', deepseek: 'دیپ‌سیک' };
function personOf(key: string): Participant | null {
  if (FIXED_FA[key]) return { key, kind: 'person', title_fa: FIXED_FA[key]!, company: null };
  const m = /^([a-z_]+)@([A-Z]{2,5})$/.exec(key);
  if (m && ROLE_FA[m[1]!]) return { key, kind: 'person', title_fa: `${ROLE_FA[m[1]!]} ${NAME[m[2]!] ?? m[2]}`, company: COMPANY_OF(key) };
  return null;
}

function open(order: { ref: string; text: string; company?: string; pace?: 'auto' | 'step' }): S {
  const company = order.company ?? 'TY';
  const conv = sessionConversation(`ceo@${company}`, order.text.slice(0, 80), order.ref, [
    ['owner', order.text],
    [`ceo@${company}`, `سلام مدیر کل. فرمانت را گرفتم و کار را شروع میکنم. هر وقت خواستی همین‌جا بگو چه بکنم یا چه را عوض کنم.`],
  ], NOW());
  const s: S = {
    ref: order.ref, conv: conv.ref, pace: order.pace ?? (/مرحله به مرحله|قدم به قدم|گام به گام|با فرمان من/.test(order.text) ? 'step' : 'auto'), hidden: false, opened_at: NOW(), closed_at: null, verdict: null,
    participants: [holderP(`مدیرعامل ${NAME[company] ?? company}`, company, `ceo@${company}`)], tasks: [], turn: null,
    holder: { code: `${company}-CEO`, title_fa: 'مدیرعامل', company, company_fa: NAME[company] ?? company }, persona: `ceo@${company}`, text_fa: order.text.slice(0, 80), last_at: NOW(),
  };
  sessions.set(order.ref, s);
  return s;
}

// ---------------------------------------------------------------------------------------------------- router
type Next = (r: Request) => Promise<Response>;
export async function handle34(req: Request, p: string, q: URLSearchParams, next: Next): Promise<Response | null> {
  const m = req.method;
  const body = async <T,>() => (await req.clone().json().catch(() => ({}))) as T;
  const reportOf = async (ref: string): Promise<any | null> => {
    if (LOCAL[ref]) return LOCAL[ref];
    const res = await next(new Request(new URL(`/api/v1/orders/${ref}/report`, req.url)));
    return res.ok ? res.json() : null;
  };
  const sync = async (s: S) => {
    // The report is read fresh each time; what the session changes in it is carried by the session itself.
    const rep = await reportOf(s.ref);
    return rep ? decorate(rep, s) : null;
  };

  // --------------------------------------------------------------------------------------------- the office
  if (p === '/office' && m === 'GET') {
    const cards = await Promise.all([...sessions.values()].filter((s) => !s.closed_at && !s.hidden && s.listed !== false).map(async (s) => card(s, await reportOf(s.ref))));
    const home = await (await next(new Request(new URL('/api/v1/home', req.url)))).json().catch(() => ({ cards: {}, critical: [] })) as any;
    const decs = await (await next(new Request(new URL('/api/v1/decisions?status=pending&limit=10', req.url)))).json().catch(() => ({ items: [] })) as any;
    const items = Array.isArray(decs) ? decs : decs.items ?? [];
    return json({
      sessions: cards.sort((a, b) => ['your_turn', 'ready', 'stuck', 'moving'].indexOf(a.badge) - ['your_turn', 'ready', 'stuck', 'moving'].indexOf(b.badge) || Date.parse(b.last_at) - Date.parse(a.last_at)).slice(0, 30),
      approvals: items.slice(0, 10), approvals_total: decs.total ?? items.length,
      money: { revenue_month_usd: 4210, spend_month_usd: 412.6, budget_month_usd: 1200, line_fa: 'این ماه 4,210 دلار درآمد و 413 دلار خرج داشتیم؛ 34٪ از سقف ماه رفته.' },
      critical: home.critical ?? [], suggestions: [home.cards?.effective, home.cards?.good].filter(Boolean), canvas: canvas(),
    });
  }

  // ------------------------------------------------------------------------------------------ the links
  if (p === '/links' && m === 'GET') return json(canvas());
  if (p === '/links' && m === 'POST') {
    const b = await body<any>();
    if (!NAME[b.from] || !NAME[b.to] || b.from === b.to) return problem(422, 'validation_failed', 'دو شرکت جدا انتخاب کن.');
    if (!b.purpose_fa?.trim()) return problem(422, 'validation_failed', 'بنویس این ارتباط برای چیست.');
    const l: Link = { id: `lk-${String(++linkSeq).padStart(4, '0')}`, from: b.from, to: b.to, kind: b.kind ?? 'serves', purpose_fa: b.purpose_fa.trim(), state: 'on', open_works: 0, updated_at: NOW() };
    links.push(l);
    return json(l, 201);
  }
  const lk = /^\/links\/([^/]+)$/.exec(p);
  if (lk && m === 'PATCH') {
    const l = links.find((x) => x.id === lk[1]);
    if (!l) return problem(404, 'not_found', 'این ارتباط پیدا نشد.');
    const b = await body<any>();
    if (b.kind) l.kind = b.kind;
    if (typeof b.purpose_fa === 'string' && b.purpose_fa.trim()) l.purpose_fa = b.purpose_fa.trim();
    if (b.state) l.state = b.state;
    l.updated_at = NOW();
    return json(l);
  }
  const nd = /^\/canvas\/nodes\/([^/]+)$/.exec(p);
  if (nd && m === 'PUT') {
    if (!nodePlace[nd[1]!]) return problem(404, 'not_found', 'این شرکت پیدا نشد.');
    const b = await body<any>();
    if (typeof b.x !== 'number' || typeof b.y !== 'number' || b.x < 0 || b.x > 1 || b.y < 0 || b.y > 1) return problem(422, 'validation_failed', 'جای شرکت باید روی بوم باشد.');
    nodePlace[nd[1]!] = { x: b.x, y: b.y };
    return json(canvas().nodes.find((n) => n.code === nd[1]));
  }

  // ---------------------------------------------------------------------------------------------- sessions
  if (p === '/sessions' && m === 'GET') {
    const st = q.get('state') ?? 'open';
    const all = await Promise.all([...sessions.values()].filter((s) => s.listed !== false).map(async (s) => card(s, await reportOf(s.ref))));
    const items = all.filter((c) => (st === 'all' ? true : st === 'closed' ? !!c.closed_at && !c.hidden : !c.closed_at && !c.hidden));
    const rank = ['your_turn', 'ready', 'stuck', 'moving', 'closed'];
    items.sort((a, b) => rank.indexOf(a.badge) - rank.indexOf(b.badge) || Date.parse(b.last_at) - Date.parse(a.last_at));
    return json({ items, next_cursor: null });
  }

  // A new order opens its session; a suggestion that is run does too.
  if (p === '/orders' && m === 'POST') {
    const b = await body<any>();
    const res = await next(req);
    if (!res.ok) return res;
    const out = (await res.clone().json()) as any;
    const s = sessions.get(out.ref) ?? open({ ref: out.ref, text: String(b.text ?? ''), company: out.routes?.[0]?.company, pace: b.pace === 'step' || b.pace === 'auto' ? b.pace : undefined });
    return json({ ...out, talk_ref: s.conv, pace: s.pace }, 201);
  }
  const sg = /^\/home\/suggestions\/([^/]+)$/.exec(p);
  if (sg && m === 'POST') {
    const res = await next(req);
    if (!res.ok) return res;
    const out = (await res.clone().json()) as any;
    if (out.order_ref && !sessions.has(out.order_ref)) open({ ref: out.order_ref, text: String(out.title_fa ?? 'پیشنهاد'), company: out.company });
    return res;
  }

  const o = /^\/orders\/(F-\d+)(?:\/([a-z]+)(?:\/([^/]+))?)?$/.exec(p);
  if (!o) return null;
  const s = sessions.get(o[1]!);
  const act = o[2];
  if (erased.has(o[1]!)) return problem(404, 'not_found', 'این فرمان پیدا نشد.');
  if (!s) {
    // An order of §29's fixtures that has no session yet gets one when it is first read (every order is a session).
    if (act === 'report' && m === 'GET') {
      const rep = await reportOf(o[1]!);
      if (!rep) return null;
      const made = open({ ref: o[1]!, text: rep.text_fa });
      return json(decorate(rep, made));
    }
    return null;
  }
  const touch = () => { s.last_at = NOW(); };

  // A stuck session with no fix to offer (asked for by the checks): its report names no blocker, its activity still says why.
  const plainStuck = s.ref === 'F-0005' && flag('hq.e2e.stuck') === 'plain';
  if (act === 'report' && m === 'GET') {
    const rep = await reportOf(s.ref);
    if (!rep) return problem(404, 'not_found', 'گزارش این فرمان پیدا نشد.');
    return json(decorate(plainStuck ? { ...rep, blockers: [] } : rep, s));
  }
  if (act === 'activity' && m === 'GET') {
    const a = actOf(s);
    // Once its knot is untied the session is no longer stuck (the hub then goes on by itself).
    if (a.stuck_fa && !plainStuck && !((await reportOf(s.ref))?.blockers ?? []).length) a.stuck_fa = null;
    return json(actView(a));
  }
  if (act === 'nudge' && m === 'POST') {
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(req.headers.get('Idempotency-Key') ?? '')) return problem(422, 'validation_failed', 'کلید یکتا باید UUID باشد.');
    if (s.closed_at) return problem(409, 'session_closed', 'این جلسه بسته شده است.');
    const a = actOf(s);
    const who = s.holder ? `${s.holder.title_fa} ${s.holder.company_fa}` : 'مشاور کل';
    const line: Line41 = { id: `wake-${s.ref}-${a.last.length + 1}`, at: NOW(), who_fa: who, company: s.holder?.company ?? null, text_fa: 'برنامه را از کار بعدی ادامه داد', kind: 'wake', state: 'done', task_n: null };
    a.stuck_fa = null; a.waiting_fa = null; a.idle_since = null;
    if (!a.working.length) a.working = held.get(s.ref)?.map((w) => ({ ...w, started_at: line.at, last_at: w.last_fa ? line.at : w.last_at })) ?? [{ who_fa: who, company_fa: s.holder?.company_fa ?? '', work_title_fa: s.tasks.find((t) => t.state !== 'done')?.title_fa ?? 'ادامه‌ی برنامه', started_at: line.at, step: 1, doing_fa: line.text_fa }];
    held.delete(s.ref);
    a.last = [...a.last, line].slice(-30);
    touch();
    return json(actView(a));
  }
  if (act === 'talk' && m === 'POST') return json({ conversation_ref: s.conv }, 201);
  if (act === 'reply' && m === 'POST') {
    const b = await body<any>();
    if (s.closed_at) return problem(409, 'conflict', 'این جلسه بسته شده؛ اول بازش کن.');
    if (!String(b.text ?? '').trim()) return problem(422, 'validation_failed', 'جوابت را بنویس.');
    s.turn = null; touch();
    // The wait is over: the holder takes the work up again with the owner's answer.
    const act41 = actOf(s);
    act41.waiting_fa = null; act41.idle_since = null;
    if (!act41.working.length) act41.working = [{ who_fa: s.holder ? `${s.holder.title_fa} ${s.holder.company_fa}` : 'مشاور کل', company_fa: s.holder?.company_fa ?? '', work_title_fa: s.tasks.find((t) => t.state !== 'done')?.title_fa ?? s.text_fa, started_at: NOW(), step: 1, doing_fa: 'با جواب تو ادامه میدهد' }];
    conversationSay(s.conv, 'owner', String(b.text).trim());
    conversationSay(s.conv, s.participants[0]!.key, 'ممنون، همین را انجام میدهم و نتیجه را همین‌جا میگویم.');
    if (LOCAL[s.ref]) { LOCAL[s.ref].steps.push({ at: NOW(), who_fa: 'مدیر کل', what_fa: String(b.text).trim() }); LOCAL[s.ref].state = 'in_progress'; }
    return json(await sync(s));
  }
  if (act === 'participants') {
    if (s.closed_at && m !== 'GET') return problem(409, 'conflict', 'این جلسه بسته شده؛ اول بازش کن.');
    if (m === 'POST') {
      const b = await body<any>();
      let part: Participant | null = null;
      if (b.kind === 'player') {
        const k = String(b.key).replace(/^player:/, '');
        if (!PLAYER_FA[k]) return problem(422, 'validation_failed', 'این مدل را نمیشناسم.');
        if (k === 'deepseek') return problem(409, 'player_signed_out', 'دیپ‌سیک الان وارد نیست؛ از «بازیکن‌های ذخیره» واردش کن.');
        part = { key: `player:${k}`, kind: 'player', title_fa: PLAYER_FA[k]!, company: null };
      } else part = personOf(String(b.key));
      if (!part) return problem(422, 'validation_failed', 'این آدم را نمیشناسم.');
      if (!s.participants.some((x) => x.key === part!.key)) { s.participants.push(part); presentAdd(s.conv, part.key); conversationSay(s.conv, s.participants[0]!.key, `${part.title_fa} به جلسه آمد.`); }
      touch();
      return json(await sync(s));
    }
    if (m === 'DELETE' && o[3]) {
      const key = decodeURIComponent(o[3]);
      const x = s.participants.find((y) => y.key === key);
      if (!x) return problem(404, 'not_found', 'این نفر در جلسه نیست.');
      if (x.kind === 'holder') return problem(409, 'conflict', 'مسئول فرمان را نمیشود بیرون برد.');
      s.participants = s.participants.filter((y) => y.key !== key); presentDrop(s.conv, key); touch();
      return json(await sync(s));
    }
  }
  if (act === 'tasks') {
    if (m === 'POST') {
      const b = await body<any>();
      if (!String(b.title_fa ?? '').trim()) return problem(422, 'validation_failed', 'عنوان کار را بنویس.');
      const t = task(s.tasks.length + 1, String(b.title_fa).trim(), 'todo', 'owner');
      s.tasks.push(t); touch();
      return json(t, 201);
    }
    if (m === 'PATCH' && o[3]) {
      const t = s.tasks.find((x) => x.id === decodeURIComponent(o[3]!));
      if (!t) return problem(404, 'not_found', 'این کار پیدا نشد.');
      const b = await body<any>();
      if (typeof b.title_fa === 'string' && b.title_fa.trim()) t.title_fa = b.title_fa.trim();
      if (b.state) t.state = b.state;
      if (typeof b.n === 'number') t.n = b.n;
      touch();
      return json(t);
    }
  }
  if (act === 'close' && m === 'POST') {
    const b = await body<any>();
    if (b.verdict !== 'ok' && b.verdict !== 'cancel') return problem(422, 'validation_failed', 'یا تأیید کن یا لغو.');
    // ⟨1.19⟩ §37.4 a close carries its own Idempotency-Key, a UUID (the Android 0.15.0 cancel sent another shape and got 422).
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(req.headers.get('Idempotency-Key') ?? '')) return problem(422, 'validation_failed', 'کلید یکتا باید UUID باشد.');
    s.closed_at = NOW(); s.verdict = b.verdict; s.turn = null; touch();
    conversationClosed(s.conv, s.closed_at);
    return json(await sync(s));
  }
  if (act === 'reopen' && m === 'POST') {
    s.closed_at = null; s.verdict = null; touch(); conversationClosed(s.conv, null);
    return json(await sync(s));
  }
  if (act === 'pace' && m === 'POST') {
    const b = await body<any>();
    if (b.pace !== 'auto' && b.pace !== 'step') return problem(422, 'validation_failed', 'روش کار یا «با من» است یا «خودکار».');
    s.pace = b.pace; touch();
    return json(await sync(s));
  }
  // ⟨1.19⟩ §37.1 erasing for good: the preview changes nothing; the erase is sealed (step-up), open or closed, and the session answers 404 after.
  if (act === 'erase') {
    const c = conversationCounts(s.conv);
    const counts = { turns: c.turns, files: c.files, outputs: 0, works: s.tasks.length ? 1 : 0, notifications: 0 };
    if (o[3] === 'preview' && m === 'GET') {
      return json({
        ref: s.ref, kind: 'session', title_fa: s.text_fa, counts,
        keeps_fa: ['یک خط در دفتر ممیزی می‌ماند.', 'عددهای توکن و پول می‌مانند تا حساب خزانه بخواند.'],
      });
    }
    if (!o[3] && m === 'POST') {
      if (!req.headers.get('X-Step-Up')) return problem(403, 'step_up_required', 'پاک کردن برای همیشه تأیید با اثر انگشت یا چهره میخواهد.');
      if (!req.headers.get('Idempotency-Key')) return problem(422, 'validation_failed', 'کلید یکتا لازم است.');
      conversationDrop(s.conv);
      sessions.delete(s.ref);
      erased.add(s.ref);
      return json({ ref: s.ref, erased: counts });
    }
  }
  if ((act === 'hide' || act === 'unhide') && m === 'POST') {
    s.hidden = act === 'hide'; touch();
    return json(await sync(s));
  }
  return null;
}

// ------------------------------------------------------------------------------------ ⟨1.22⟩ §40 for ./mock-v40
/** What the playbook router reads of a session: its words, its company, its talk. */
export async function playbookOrder(ref: string) {
  const s = sessions.get(ref);
  if (!s || erased.has(ref)) return null;
  return { text_fa: s.text_fa, company: s.holder?.company ?? 'TY', conversation: s.conv };
}
/** The holder posts the playbook card («کارگروه از این جلسه») into the session's talk. */
export function postPlaybookCard(ref: string, pb: { ref: string; title_fa: string; purpose_fa: string }) {
  const s = sessions.get(ref);
  if (!s) return;
  conversationCard(s.conv, s.participants[0]!.key, 'کارگروه از این جلسه آماده است. باز کنید، ویرایش کنید و مُهر بزنید.', 'playbook', `کارگروه از این جلسه: ${pb.title_fa}`, pb.purpose_fa, { playbook: pb.ref });
  s.last_at = NOW();
}
let applySeq = 200;
/** A session for a company, opened by giving it a playbook: the owner's first turn is the playbook as Markdown. */
export function openFromPlaybook(v: { company: string; text_fa: string; first_md: string; source: string }) {
  const ref = `F-${String(++applySeq).padStart(4, '0')}`;
  const conv = sessionConversation(`ceo@${v.company}`, v.text_fa.slice(0, 80), ref, [
    ['owner', v.first_md],
    [`ceo@${v.company}`, 'سلام مدیر کل. کارگروه را گرفتم و برای ما تطبیقش میدهم؛ پیش‌نویس را همین‌جا میبینی و اگر درست بود مُهرش میکنی.'],
  ], NOW());
  sessions.set(ref, {
    ref, conv: conv.ref, pace: 'auto', hidden: false, opened_at: NOW(), closed_at: null, verdict: null,
    participants: [holderP(`مدیرعامل ${NAME[v.company] ?? v.company}`, v.company, `ceo@${v.company}`)], tasks: [], turn: null,
    holder: { code: `${v.company}-CEO`, title_fa: 'مدیرعامل', company: v.company, company_fa: NAME[v.company] ?? v.company }, persona: `ceo@${v.company}`, text_fa: v.text_fa.slice(0, 80), last_at: NOW(),
  });
  LOCAL[ref] = {
    ref, text_fa: v.text_fa, at: NOW(), state: 'in_progress', ack: null,
    route: { companies: [v.company], department: null, collaborators: [], output_kind: 'answer', budget_tokens: 60_000, mode: 'single', player: 'auto' },
    steps: [{ at: NOW(), who_fa: 'مدیر کل', what_fa: 'کارگروه را به این شرکت داد.' }], blockers: [], outputs: [], summary: null, updated_at: NOW(),
  };
  setSource(ref, v.source);
  return { ref, conversation: conv.ref };
}

// ------------------------------------------------------------------------------- ⟨1.0.1⟩ the owner's stop, for ./mock-v55
/** The works of the demo's sessions that can be live, by ref, with the id the list's search answers. */
export const LIVE_WORKS: Record<string, string> = {
  'W-000311': '0b1c55a0-0000-4000-8000-000000000311', 'W-000312': '0b1c55a0-0000-4000-8000-000000000312', 'W-000313': '0b1c55a0-0000-4000-8000-000000000313',
};
/** «نگه دار»: the live work of the session that carries this work stops (nothing more runs for it until the owner speaks). */
export function stopLiveWork(workRef: string): { work_ref: string; workspace: null; jobs_stopped: number } | null {
  const s = [...sessions.values()].find((x) => x.tasks.some((t) => t.work_ref === workRef));
  if (!s) return null;
  const a = actOf(s);
  const n = a.working.length;
  if (n) held.set(s.ref, a.working);
  a.last = a.last.map((l) => (l.state === 'running' ? { ...l, state: 'done' as const } : l));
  a.working = [];
  a.idle_since = NOW();
  return { work_ref: workRef, workspace: null, jobs_stopped: n };
}
