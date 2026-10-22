'use client';

import { useState, type ComponentProps, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { FilterChip, Pill } from '@/components/ui/primitives';
import { rruleFa } from '@/components/v14/bits';
import { useCompanies } from '@/lib/api/hooks';
import { GUARD_FA, NO_OVERRIDE, type LifecycleRule } from '@/lib/api/v16';
import { cx } from '@/lib/format';

type Tone = ComponentProps<typeof Pill>['tone'];
type Label = { fa: string; tone: Tone };

// ------------------------------------------------------------------ labels (§19) --
export const CHANNEL_FA: Record<string, string> = {
  telegram_business: 'تلگرام بیزینس', telegram_bot: 'ربات پشتیبانی تلگرام', chatwoot: 'چت سایت (Chatwoot)', product_bot: 'ربات محصول', mystery: 'مشتری ناشناس ناظر',
};
export const CHANNEL_STATE: Record<string, Label> = {
  not_configured: { fa: 'راه‌اندازی نشده', tone: 'neutral' }, shadow: { fa: 'سایه، بی‌ارسال', tone: 'lapis' }, live: { fa: 'روشن', tone: 'pos' }, paused: { fa: 'متوقف', tone: 'warn' },
};
export const AUTO_SEND: Record<string, { fa: string; note: string }> = {
  kb_verbatim: { fa: 'فقط عین دانشنامه', note: 'فقط جواب‌هایی که عیناً یک مقاله‌ی تأییدشده‌اند بی‌تو میروند.' },
  kb_grounded: { fa: 'پیش‌نویس مستند هم', note: 'پیش‌نویسی هم که هر دو چک را پاس کرده و اطمینانش از آستانه بالاتر است بی‌تو میرود.' },
  off: { fa: 'هیچ', note: 'هیچ چیز بی‌تو نمیرود؛ همه در صف آموزش میمانند.' },
};
export const CONV_STATE: Record<string, Label> = {
  open: { fa: 'باز', tone: 'neutral' }, waiting_owner: { fa: 'منتظر تو', tone: 'gold' }, answered: { fa: 'جواب داده شد', tone: 'pos' }, closed: { fa: 'بسته', tone: 'neutral' },
};
export const HANDOFF_FA: Record<string, Label> = {
  no_kb: { fa: 'مقاله نبود', tone: 'neutral' }, low_confidence: { fa: 'اطمینان کم', tone: 'warn' }, blocked: { fa: 'رد نگهبان', tone: 'neg' },
  asked_for_human: { fa: 'آدم خواست', tone: 'lapis' }, complaint: { fa: 'شکایت', tone: 'warn' }, security: { fa: 'امنیتی', tone: 'neg' },
};
export const MSG_STATUS: Record<string, Label> = {
  draft: { fa: 'پیش‌نویس، منتظر تو', tone: 'gold' }, queued: { fa: 'در صف', tone: 'neutral' }, sent: { fa: 'فرستاده شد', tone: 'pos' }, blocked: { fa: 'رد نگهبان، فرستاده نشد', tone: 'neg' }, failed: { fa: 'ناموفق', tone: 'neg' },
};
export const AUTHOR_FA: Record<string, string> = { customer: 'مشتری', agent: 'ایجنت پشتیبانی', owner: 'تو', rule: 'قاعده' };
export const QUEUE_KIND: Record<string, Label> = {
  handoff: { fa: 'به تو سپرده شد', tone: 'gold' }, low_confidence: { fa: 'اطمینان کم', tone: 'warn' }, blocked: { fa: 'رد نگهبان', tone: 'neg' }, shadow_disagreement: { fa: 'اختلاف آزمون سایه', tone: 'lapis' },
};
export const KB_KIND: Record<string, string> = { faq: 'پرسش رایج', policy: 'سیاست', procedure: 'روال', referral: 'رفرال', official_link: 'لینک رسمی', safety: 'ایمنی' };
export const KB_STATUS: Record<string, Label> = {
  proposed: { fa: 'منتظر تأیید', tone: 'gold' }, approved: { fa: 'تأییدشده', tone: 'pos' }, expired: { fa: 'منقضی', tone: 'warn' }, retired: { fa: 'بازنشسته', tone: 'neutral' },
};
export const KB_SOURCE: Record<string, string> = { owner_answer: 'از جواب تو', owner: 'نوشته‌ی تو', doc: 'از سند', agent: 'پیشنهاد ایجنت' };
export const PURPOSE_FA: Record<string, string> = {
  welcome: 'خوش‌آمد', reactivation: 'بازگشت', rescue: 'نجات رفرال', nps: 'NPS', holding_reply: 'پاسخ انتظار', safety: 'جمله‌ی ایمنی', csat: 'رضایت',
};
export const TEMPLATE_STATUS: Record<string, Label> = { proposed: { fa: 'منتظر مُهر', tone: 'gold' }, sealed: { fa: 'مُهرشده', tone: 'pos' }, retired: { fa: 'بازنشسته', tone: 'neutral' } };
export const RULE_STATUS: Record<string, Label> = { proposed: { fa: 'منتظر مُهر', tone: 'gold' }, active: { fa: 'فعال', tone: 'pos' }, paused: { fa: 'متوقف', tone: 'warn' } };
export const RESCUE_STATE: Record<string, Label> = {
  open: { fa: 'باز', tone: 'lapis' }, contacted: { fa: 'پیگیری شد', tone: 'gold' }, rescued: { fa: 'نجات یافت', tone: 'pos' }, lost: { fa: 'از دست رفت', tone: 'neg' }, opted_out: { fa: 'لغو کرد', tone: 'neutral' },
};
export const RESCUE_STEP: Record<string, string> = { check: 'چک UID', message: 'پیام', follow_up: 'پیگیری', note: 'یادداشت' };
export const FEEDBACK_KIND: Record<string, Label> = {
  bug: { fa: 'باگ', tone: 'neg' }, feature: { fa: 'قابلیت تازه', tone: 'lapis' }, confusion: { fa: 'ابهام', tone: 'warn' }, complaint: { fa: 'شکایت', tone: 'warn' }, praise: { fa: 'تعریف', tone: 'pos' },
};
export const FEEDBACK_STATE: Record<string, Label> = {
  new: { fa: 'تازه', tone: 'gold' }, triaged: { fa: 'بررسی شد', tone: 'lapis' }, in_backlog: { fa: 'در صف کار', tone: 'neutral' }, done: { fa: 'انجام شد', tone: 'pos' }, wont_do: { fa: 'انجام نمیشود', tone: 'neutral' },
};
export const INTAKE_KIND: Record<string, string> = { telegram: 'تلگرام', chatwoot: 'Chatwoot', product: 'رویداد محصول' };
export const ALERT_FA: Record<string, { fa: string; icon: 'chart' | 'refresh' | 'time' }> = {
  drop: { fa: 'افت کمیسیون', icon: 'chart' }, pull_failed: { fa: 'pull ناموفق', icon: 'refresh' }, incomplete: { fa: 'روز ناقص', icon: 'time' },
};
export const EVENT_FA: Record<string, string> = { signup: 'ثبت‌نام', referral_failed: 'رفرال ناموفق', conversation_closed: 'بسته شدن گفت‌وگو' };

/** A rule's trigger in one line: the event (and its delay), the inactivity, or the calendar. Hours and days are prose counts. */
export function triggerFa(t: LifecycleRule['trigger']): string {
  if (t.rrule) return /FREQ=MONTHLY/.test(t.rrule) && /INTERVAL=3/.test(t.rrule) ? 'فصلی، روز اول' : rruleFa(t.rrule);
  if (t.inactive_days != null) return `بعد از ${t.inactive_days} روز بی‌فعالیتی`;
  if (t.event) return `بعد از ${EVENT_FA[t.event] ?? t.event}${t.after_hours ? `، ${t.after_hours} ساعت بعد` : ''}`;
  return '—';
}

// ------------------------------------------------------------------ figures --
/** USDT and dollars from decimal strings: Latin, two decimals, grouped. */
export const money = (v: string | number | null | undefined, unit = '') => {
  if (v == null || v === '') return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  return `${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${unit}`;
};
/** Axis ticks: 0 / 250 / 1.2K. */
export const compact = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(v >= 10_000 ? 0 : 1).replace(/\.0$/, '')}K` : String(Math.round(v)));
/** A 0..1 rate as a Latin figure ("38%"); null stays a dash, never an estimate. */
export const rate = (r: number | null | undefined) => (r == null ? '—' : `${Math.round(r * 100)}%`);

// ------------------------------------------------------------------ pieces --
// A run of Latin: words, refs (CR-005, SC-000411), numbers with their unit ("94.16 USDT", "40%"), kept together left to right.
const LATIN = /([A-Za-z0-9$+−][\w.$%/:+−-]*(?:[ \t]+[A-Za-z0-9$][\w.$%/:+−-]*)*)/;

/** Server prose (alerts, notes): Persian words read right to left; every Latin run and figure is one left-to-right figure. */
export function Prose({ text }: { text: string }) {
  return <>{text.split(LATIN).map((p, i) => (i % 2 === 1 ? <span key={i} className="fig">{p}</span> : p))}</>;
}

/** The company filter: the operating companies from the API (any number), plus «همه». */
export function CompanyChips({ value, onChange, all = true }: { value: string | null; onChange: (c: string | null) => void; all?: boolean }) {
  const { data } = useCompanies();
  const list = (data ?? []).filter((c) => c.kind !== 'holding');
  return (
    <div className="flex flex-wrap gap-2">
      {all ? <FilterChip selected={!value} onClick={() => onChange(null)}>همه‌ی شرکت‌ها</FilterChip> : null}
      {list.map((c) => <FilterChip key={c.code} selected={value === c.code} onClick={() => onChange(c.code)}><span className="flex items-center gap-1.5"><CompanyMark code={c.code} height={12} mono />{c.name_fa}</span></FilterChip>)}
    </div>
  );
}

/** A command the owner runs in their own terminal. Never a secret: only its name and the target. */
export function TerminalCommand({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <span dir="ltr" className="flex min-w-0 items-center gap-3 rounded-[10px] bg-page px-3 py-2">
      <span aria-hidden className="fig text-[13px] text-muted">$</span>
      <code className="fig min-w-0 flex-1 truncate text-[12px] text-ink">{text}</code>
      <button type="button" onClick={() => { void navigator.clipboard?.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); }} className="flex-none text-[12px] font-semibold text-gold-ink">{done ? 'کپی شد' : 'کپی'}</button>
    </span>
  );
}

/** Customer text as stored: masked parts ([ماسک: …]) stand out, so a masked secret is never mistaken for text; links, codes and
 *  figures stay Latin. */
export function Masked({ text, className }: { text: string; className?: string }) {
  const parts = text.split(/(\[(?:ماسک|masked)[^\]]*\])/);
  return (
    <span className={cx('block whitespace-pre-wrap break-words', className)}>
      {parts.map((x, i) => (i % 2 ? <span key={i} className="mx-0.5 inline-flex items-center gap-1 rounded-[6px] bg-tile px-1.5 text-[12px] text-muted"><Icon name="lock" size={12} />{x.slice(1, -1)}</span> : <Prose key={i} text={x} />))}
    </span>
  );
}

/** The outbound guard's refusals in Persian; the three without any exception say so. */
export function GuardReasons({ reasons, className }: { reasons: string[]; className?: string }) {
  if (!reasons.length) return null;
  const hard = reasons.some((r) => NO_OVERRIDE.has(r));
  return (
    <div role="alert" className={cx('flex flex-col gap-1.5 rounded-[12px] bg-neg-soft p-3 text-[13px]', className)}>
      <span className="flex items-center gap-2 font-semibold text-neg"><Icon name="lock" size={16} />نگهبان خروجی رد کرد</span>
      <ul className="flex flex-col gap-1 ps-6 text-ink">
        {reasons.map((r) => <li key={r} className="list-disc marker:text-neg">{GUARD_FA[r] ?? r} <span className="fig text-[11px] text-muted">{r}</span></li>)}
      </ul>
      <span className="text-[12px] text-sec">{hard ? 'برای این مورد هیچ استثنایی نیست، حتی برای تو؛ متن را عوض کن تا نگهبان دوباره بسنجد.' : 'متن را اصلاح کن و دوباره بفرست؛ نگهبان دوباره میسنجد.'}</span>
    </div>
  );
}

/** A labelled fact in a tile. */
export function Fact({ label, children, mono }: { label: ReactNode; children: ReactNode; mono?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-[12px] bg-tile p-3">
      <span className="text-[11px] text-muted">{label}</span>
      <span className={cx('min-w-0 break-words text-[14px] font-semibold text-ink', mono && 'fig')}>{children}</span>
    </div>
  );
}
