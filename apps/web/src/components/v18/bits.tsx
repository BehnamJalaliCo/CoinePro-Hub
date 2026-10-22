'use client';

import { useEffect, useRef, useState, type ComponentProps, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { ModelMark } from '@/components/brand/model-mark';
import { Pill } from '@/components/ui/primitives';
import type { IconName } from '@/generated/icons';
import { fileUrl } from '@/lib/api/v13';
import type { AgendaKind, AudioState, CitationKind, ClaimVerdict, CreativeState, HealthFlag, HrFlag, Placement, Player, Recommendation, ReminderKind, TriggerKind, WasteCategory } from '@/lib/api/v18';
import { cx } from '@/lib/format';

type Tone = ComponentProps<typeof Pill>['tone'];
type Label = { fa: string; tone: Tone };

// ------------------------------------------------------------------ labels (§21) --
export const REC: Record<Recommendation | string, Label> = {
  approve: { fa: 'تأیید', tone: 'pos' }, reject: { fa: 'رد', tone: 'neg' }, return: { fa: 'برگشت', tone: 'warn' }, ask: { fa: 'اول بپرس', tone: 'lapis' },
};
export const MEMO_STATE: Record<string, Label & { live?: boolean }> = {
  writing: { fa: 'در حال نوشتن', tone: 'lapis', live: true }, ready: { fa: 'آماده', tone: 'pos' }, failed: { fa: 'نوشته نشد', tone: 'neg' }, stale: { fa: 'کهنه؛ کارت عوض شده', tone: 'warn' },
};
export const LEVEL3: Record<string, string> = { low: 'کم', medium: 'متوسط', high: 'زیاد' };
export const TRIGGER: Record<TriggerKind | string, { fa: string; icon: IconName }> = {
  budget: { fa: 'بودجه', icon: 'budget' }, quota: { fa: 'سهمیه', icon: 'treasury' }, compliance: { fa: 'انطباق', icon: 'overseer' }, incident: { fa: 'حادثه', icon: 'urgent' },
  revenue: { fa: 'درآمد', icon: 'chart' }, waiting_decisions: { fa: 'کارت‌های منتظر', icon: 'cartable' }, finding: { fa: 'یافته', icon: 'search' }, okr: { fa: 'OKR', icon: 'planner' },
};
export const TRIGGER_STATE: Record<string, Label> = { sent: { fa: 'فرستاده شد', tone: 'pos' }, deferred: { fa: 'فردا؛ سهم روز تمام', tone: 'warn' }, capped: { fa: 'بالای سقف روزانه', tone: 'neutral' } };
export const CITATION: Record<CitationKind | string, { fa: string; icon: IconName }> = {
  resolution: { fa: 'مصوبه', icon: 'seal' }, decision: { fa: 'تصمیم', icon: 'decision' }, deliverable: { fa: 'خروجی', icon: 'deliverable' }, work: { fa: 'کار', icon: 'task' },
  message: { fa: 'پیام', icon: 'messages' }, doc: { fa: 'سند', icon: 'report' }, code: { fa: 'کد', icon: 'code' },
};
export const AGENDA: Record<AgendaKind | string, { fa: string; icon: IconName }> = {
  decision: { fa: 'کارت منتظر', icon: 'cartable' }, risk: { fa: 'ریسک', icon: 'urgent' }, okr: { fa: 'OKR', icon: 'planner' }, finding: { fa: 'یافته', icon: 'search' },
  budget: { fa: 'بودجه', icon: 'budget' }, revenue: { fa: 'درآمد', icon: 'chart' }, outcome_review: { fa: 'بازبینی نتیجه', icon: 'refresh' }, note: { fa: 'یادداشت', icon: 'edit' },
};
export const REVIEW_STATE: Record<string, Label & { live?: boolean }> = {
  ready: { fa: 'آماده‌ی شروع', tone: 'gold' }, in_progress: { fa: 'در جریان', tone: 'lapis', live: true }, done: { fa: 'انجام شد', tone: 'pos' }, skipped: { fa: 'رد شد', tone: 'neutral' },
};
export const ITEM_STATUS: Record<string, Label> = { open: { fa: 'باز', tone: 'neutral' }, done: { fa: 'انجام شد', tone: 'pos' }, deferred: { fa: 'عقب افتاد', tone: 'warn' } };
export const AUDIO: Record<AudioState | string, Label> = { ready: { fa: 'صدا آماده', tone: 'pos' }, pending: { fa: 'در حال ساخت صدا', tone: 'lapis' }, off: { fa: 'صدا خاموش', tone: 'neutral' }, failed: { fa: 'صدا ساخته نشد', tone: 'warn' } };
export const HR_FLAG: Record<HrFlag | string, Label> = {
  promote_candidate: { fa: 'نامزد ارتقا', tone: 'pos' }, coach: { fa: 'آموزش', tone: 'lapis' }, demote_candidate: { fa: 'نامزد تنزل', tone: 'warn' },
  dismiss_candidate: { fa: 'نامزد برکناری', tone: 'neg' }, probation_end: { fa: 'پایان دوره‌ی آزمایشی', tone: 'gold' },
};
export const HR_STATE: Record<string, Label> = { drafting: { fa: 'در حال نوشتن', tone: 'lapis' }, proposed: { fa: 'کارت‌ها منتظر تو', tone: 'gold' }, done: { fa: 'تمام شد', tone: 'pos' } };
export const RECOMMENDATION: Record<string, { fa: string; tone: Tone; icon: IconName }> = {
  promote: { fa: 'ارتقا', tone: 'pos', icon: 'star' }, demote: { fa: 'تنزل', tone: 'warn', icon: 'back' }, dismiss: { fa: 'برکناری', tone: 'neg', icon: 'dismiss' }, confirm: { fa: 'تثبیت', tone: 'gold', icon: 'seal' },
};
export const WASTE: Record<WasteCategory | string, { fa: string; note: string }> = {
  failed_runs: { fa: 'اجرای شکست‌خورده', note: 'اجرای failed یا refused' }, cancelled_work: { fa: 'کار لغوشده', note: 'اجرای کاری که بعد لغو شد' },
  no_progress_runs: { fa: 'اجرای بی‌پیشرفت', note: 'تعریف PR-022' }, retry_loops: { fa: 'حلقه‌ی تکرار', note: '۳ اجرا یا بیشتر روی یک کار در ۲۴ ساعت' },
  router_errors: { fa: 'خطای مسیریاب', note: 'فراخوانی خطادار با هزینه' }, duplicate_calls: { fa: 'فراخوانی تکراری', note: 'همان درخواست در ۱۰ دقیقه' },
  cache_miss: { fa: 'از دست رفتن کش', note: 'ورودی بزرگ با همان پیشوند و بی‌خواندن کش' }, over_model: { fa: 'مدل بالاتر از لازم', note: 'بالاتر از assignment پیش‌فرض' },
};
export const NOTE_STATUS: Record<string, Label> = { open: { fa: 'باز', tone: 'gold' }, promoted: { fa: 'تبدیل شد', tone: 'pos' }, archived: { fa: 'بایگانی', tone: 'neutral' } };
export const PROMOTE: Record<string, { fa: string; icon: IconName; note: string }> = {
  work: { fa: 'کار', icon: 'task', note: 'یک کار برای مدیرعامل همان شرکت (§4)' },
  order: { fa: 'فرمان', icon: 'command', note: 'مثل فرمان صوتی، با مسیریابی قاعده‌محور (§17.4)' },
  errand: { fa: 'کار دستیار', icon: 'assistant', note: 'دستیار شخصی انجامش میدهد (§18.3)' },
};
export const REMINDER: Record<ReminderKind | string, string> = { half: 'نیمه‌ی زمان', before_expiry: '۶ ساعت پیش از انقضا', age_24h: '۲۴ ساعت', age_72h: '۷۲ ساعت', age_7d: '۷ روز' };
export const VERDICT_CLAIM: Record<ClaimVerdict | string, Label & { icon: IconName }> = {
  confirmed: { fa: 'تأیید شد', tone: 'pos', icon: 'seal' }, refuted: { fa: 'رد شد', tone: 'neg', icon: 'reject' }, unverifiable: { fa: 'سنجش‌ناپذیر', tone: 'neutral', icon: 'info' },
};
export const HEALTH: Record<HealthFlag | string, Label & { note: string }> = {
  truth: { fa: 'راستی', tone: 'neg', note: 'دست‌کم ۲۰٪ ادعای رد شده از ۵ بررسی یا بیشتر' },
  reliability: { fa: 'پایداری', tone: 'warn', note: 'دست‌کم ۲۵٪ اجرای شکست‌خورده' },
  loops: { fa: 'حلقه', tone: 'warn', note: 'دو حلقه‌ی تکرار یا بیشتر' },
};
export const VERDICT3: Record<string, Label> = { approve: { fa: 'تأیید', tone: 'pos' }, reject: { fa: 'رد', tone: 'neg' }, return: { fa: 'برگشت', tone: 'warn' } };
export const PRINCIPLE: Record<string, Label> = { proposed: { fa: 'پیشنهادی', tone: 'gold' }, active: { fa: 'فعال', tone: 'pos' }, retired: { fa: 'کنار گذاشته', tone: 'neutral' } };
export const PLAYER: Record<Player | string, { fa: string; provider: string }> = {
  gpt: { fa: 'ChatGPT', provider: 'openai' }, gemini: { fa: 'Gemini', provider: 'google' }, deepseek: { fa: 'DeepSeek', provider: 'deepseek' },
};
export const SEAT: Record<string, { fa: string; note: string }> = {
  advisor_second_opinion: { fa: 'نظر دوم مشاور', note: 'کنار هر یادداشت تصمیم، بی‌دیدن یادداشت مشاور' },
  code_review: { fa: 'بازبینی دوم کد', note: 'PR کارت انتشار، ممیزی تأسیس، diff کارگاه؛ هرگز تأیید یا مسدود نمیکند' },
  overseer_cross_check: { fa: 'بررسی دوم ناظر', note: 'ادعاهای نمونه‌ی PR-001 پیش از رأی' },
  assistant_errand: { fa: 'پیش‌نویس دستیار', note: 'خلاصه، ترجمه، بازنویسی؛ دستیار تمامش میکند' },
  content_draft: { fa: 'پیش‌نویس محتوا', note: 'کپشن، عنوان، توضیح متا برای ایجنت مسئول' },
  long_read: { fa: 'خواندن سند بلند', note: 'خلاصه با شماره‌ی خط یا صفحه که صداکننده میسنجد' },
  quick_search: { fa: 'جستجوی سریع', note: 'جواب با منبع؛ صداکننده هر منبع را خودش میخواند' },
  third_opinion: { fa: 'نظر سوم', note: 'کنار یادداشت مشاور و نظر دوم، بی‌دیدن هیچ‌کدام' },
  creative: { fa: 'عکس و ویدیو', note: 'از مرورگر لاگین‌شده؛ متن فارسی را هاب میگذارد' },
};
export const SUB_STATUS: Record<string, Label> = { ready: { fa: 'آماده', tone: 'pos' }, limited: { fa: 'محدود', tone: 'warn' }, off: { fa: 'خاموش', tone: 'neutral' }, error: { fa: 'خطا', tone: 'neg' } };
export const LOGIN: Record<string, Label> = { signed_in: { fa: 'وارد', tone: 'pos' }, signing_in: { fa: 'در حال ورود', tone: 'lapis' }, signed_out: { fa: 'خارج', tone: 'neutral' }, expired: { fa: 'منقضی', tone: 'warn' } };
export const CAP: Record<string, string> = { cli: 'CLI', web: 'وب', api: 'API', off: 'خاموش' };
export const PLACEMENT: Record<Placement | string, { fa: string; aspect: string }> = {
  telegram_post: { fa: 'پست تلگرام', aspect: '16:9' }, telegram_story: { fa: 'استوری تلگرام', aspect: '9:16' }, instagram_post: { fa: 'پست اینستاگرام', aspect: '4:5' },
  instagram_story: { fa: 'استوری اینستاگرام', aspect: '9:16' }, banner: { fa: 'بنر', aspect: '16:9' }, other: { fa: 'دیگر', aspect: '1:1' },
};
export const CREATIVE: Record<CreativeState | string, Label & { live?: boolean }> = {
  queued: { fa: 'در صف', tone: 'neutral', live: true }, generating: { fa: 'در حال ساخت', tone: 'lapis', live: true }, review: { fa: 'منتظر نظر تو', tone: 'gold' },
  accepted: { fa: 'پذیرفته', tone: 'pos' }, rejected: { fa: 'رد شد', tone: 'neutral' }, failed: { fa: 'ساخته نشد', tone: 'neg' },
};
/** Connection statuses, §10 and §21.7. */
export const CONN: Record<string, Label> = {
  enabled: { fa: 'روشن', tone: 'pos' }, ready: { fa: 'آماده', tone: 'pos' }, disabled: { fa: 'خاموش', tone: 'neutral' }, quota_exhausted: { fa: 'سهمیه تمام', tone: 'warn' },
  pending_secret: { fa: 'منتظر کلید', tone: 'gold' }, verifying: { fa: 'در حال بررسی', tone: 'lapis' }, error: { fa: 'خطا', tone: 'neg' },
};

// ------------------------------------------------------------------ figures and dates --
const J_MONTH = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
/** "1405-07" → «مهر ۱۴۰۵» (a date in prose: the text face draws the digits). */
export function jMonth(key: string | null | undefined): string {
  const m = /^(\d{4})-(\d{1,2})$/.exec(key ?? '');
  return m ? `${J_MONTH[Number(m[2]) - 1] ?? m[2]} ${m[1]}` : key ?? '—';
}
/** "gpt-5.5" → "GPT 5.5"; Claude ids keep their own label. */
export function subModel(id: string | null | undefined): string {
  if (!id) return '—';
  const m = /^(gpt|gemini|deepseek)-(.+)$/i.exec(id);
  if (!m) return id;
  const name = m[1]!.toLowerCase() === 'gpt' ? 'GPT' : m[1]!.toLowerCase() === 'gemini' ? 'Gemini' : 'DeepSeek';
  return `${name} ${m[2]!.toUpperCase().replace(/^V/, 'V')}`;
}
/** A 0..1 as a Latin percentage. */
export const pct01 = (v: number | null | undefined, digits = 0) => (v == null ? '—' : `${(v * 100).toFixed(digits)}%`);
export const hoursFa = (h: number) => (h < 48 ? `${h} ساعت` : `${Math.round(h / 24)} روز`);

// ------------------------------------------------------------------ pieces --
/** The provider's logo beside a substitute player's name. */
export function PlayerName({ player, model, size = 14, className }: { player: Player | string; model?: string | null; size?: number; className?: string }) {
  const p = PLAYER[player] ?? { fa: player, provider: player };
  return (
    <span className={cx('inline-flex items-center gap-1.5', className)}>
      <ModelMark provider={p.provider} model={model} size={size} />
      <span className="fig">{model ? subModel(model) : p.fa}</span>
    </span>
  );
}

/** What a substitute returns is labelled and never evidence (§21.13). */
export function SubstituteNote({ className }: { className?: string }) {
  return <span className={cx('inline-flex items-center gap-1 text-[11px] text-muted', className)}><Icon name="info" size={12} />بازیکن ذخیره؛ شاهد نیست</span>;
}

export function Section({ title, children, action, className }: { title: ReactNode; children: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <section className={cx('flex flex-col gap-1.5', className)}>
      <div className="flex items-center gap-2"><h3 className="min-w-0 flex-1 text-[12px] font-semibold text-gold-ink">{title}</h3>{action}</div>
      {children}
    </section>
  );
}

const clock = (s: number) => (Number.isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}` : '0:00');
const SPEEDS = [1, 1.25, 1.5];
/** The briefing player: play or pause, a seekable bar, Latin time and the speed (Ogg/Opus from the hub; nothing leaves it). */
export function AudioPlayer({ fileId, label, compact }: { fileId: string; label: string; compact?: boolean }) {
  const ref = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [t, setT] = useState(0);
  const [dur, setDur] = useState(0);
  const [speed, setSpeed] = useState(1);
  useEffect(() => { if (ref.current) ref.current.playbackRate = speed; }, [speed]);
  const toggle = () => { const a = ref.current; if (!a) return; if (a.paused) void a.play().catch(() => setPlaying(false)); else a.pause(); };
  const seek = (v: number) => { const a = ref.current; if (a && dur) { a.currentTime = (v / 100) * dur; setT(a.currentTime); } };
  const done = dur ? (t / dur) * 100 : 0;
  return (
    <div className={cx('flex items-center gap-3 rounded-[14px] bg-tile', compact ? 'p-2' : 'p-3')} role="group" aria-label={label}>
      <audio ref={ref} src={fileUrl(fileId)} preload="metadata" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => { setPlaying(false); setT(0); }}
        onTimeUpdate={(e) => setT(e.currentTarget.currentTime)} onLoadedMetadata={(e) => setDur(e.currentTarget.duration)} />
      <button type="button" onClick={toggle} aria-label={playing ? 'توقف' : 'پخش'} className={cx('flex flex-none items-center justify-center rounded-full bg-gold text-on-gold hover:bg-gold-bright', compact ? 'size-9' : 'size-11')}>
        <Icon name={playing ? 'pause' : 'resume'} size={compact ? 16 : 20} active />
      </button>
      <div className="flex min-w-0 flex-1 flex-col gap-1" dir="ltr">
        <input type="range" min={0} max={100} step={0.1} value={done} onChange={(e) => seek(Number(e.target.value))} aria-label="جای پخش" className="h-1.5 w-full cursor-pointer accent-[var(--hq-gold-fill)]" />
        <div className="flex items-center justify-between text-[11px] text-muted"><span className="fig">{clock(t)}</span><span className="fig">{clock(dur)}</span></div>
      </div>
      <button type="button" onClick={() => setSpeed(SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length]!)} aria-label="سرعت پخش" className="fig flex-none rounded-full border border-strong px-2 py-1 text-[11px] text-sec hover:bg-hover hover:text-ink">{speed}×</button>
    </div>
  );
}

/** A confidence as a short bar and a Latin percentage. */
export function Confidence({ v, tone = 'gold' }: { v: number; tone?: 'gold' | 'silver' }) {
  return (
    <span className="inline-flex items-center gap-1.5" title="اطمینان">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-tile" aria-hidden><span className="block h-full rounded-full" style={{ width: `${Math.round(v * 100)}%`, background: tone === 'gold' ? 'var(--hq-gold-fill)' : 'var(--hq-silver-ink)' }} /></span>
      <span className="fig text-[11px] text-sec">{pct01(v)}</span>
    </span>
  );
}
