'use client';

import { type ComponentProps, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Pill } from '@/components/ui/primitives';
import type { IconName } from '@/generated/icons';
import { fileUrl } from '@/lib/api/v13';
import { CHECKS, type CheckResult, type ItemState, type MediaFile, type MediaItem, type PublishRow } from '@/lib/api/v19';
import { cx, jDateTime } from '@/lib/format';

type Tone = ComponentProps<typeof Pill>['tone'];
type Label = { fa: string; tone: Tone };

// ------------------------------------------------------------------ labels (§22) --
/** The pipeline's eight columns (§22.2): each step a work item to its role, code moves the item on. */
export const STAGES: Array<{ key: string; fa: string; icon: IconName; states: ItemState[]; who: string }> = [
  { key: 'script', fa: 'سناریو', icon: 'edit', states: ['scripting'], who: 'سناریست' },
  { key: 'direction', fa: 'کارگردانی', icon: 'video', states: ['directing'], who: 'کارگردان' },
  { key: 'motion', fa: 'موشن', icon: 'code', states: ['composing'], who: 'طراح موشن، با کد' },
  { key: 'voice', fa: 'صدا', icon: 'mic', states: ['voicing'], who: 'تهیه‌کننده‌ی صدا' },
  { key: 'render', fa: 'رندر', icon: 'server', states: ['rendering'], who: 'کد، در سندباکس' },
  { key: 'checks', fa: 'چک‌ها', icon: 'seal', states: ['checking', 'review'], who: 'کد و مدیر رسانه' },
  { key: 'ready', fa: 'آماده', icon: 'time', states: ['scheduled', 'waiting_owner'], who: 'زمان‌بندی یا کارت تو' },
  { key: 'published', fa: 'منتشرشده', icon: 'send', states: ['published'], who: 'API رسمی' },
];
export const STOPPED: ItemState[] = ['held', 'failed', 'rejected'];
export const stageOf = (s: ItemState) => STAGES.findIndex((x) => x.states.includes(s));
export const ITEM_STATE: Record<ItemState | string, Label & { live?: boolean }> = {
  scripting: { fa: 'سناریو', tone: 'lapis', live: true }, directing: { fa: 'کارگردانی', tone: 'lapis', live: true }, composing: { fa: 'ترکیب‌بندی با کد', tone: 'lapis', live: true },
  voicing: { fa: 'ساخت صدا', tone: 'lapis', live: true }, rendering: { fa: 'رندر در سندباکس', tone: 'lapis', live: true }, checking: { fa: 'چک‌ها', tone: 'lapis', live: true },
  review: { fa: 'بازبینی مدیر رسانه', tone: 'gold' }, scheduled: { fa: 'زمان‌بندی‌شده', tone: 'pos' }, published: { fa: 'منتشر شد', tone: 'pos' },
  waiting_owner: { fa: 'منتظر تو', tone: 'gold' }, held: { fa: 'نگه‌داشته‌ی ناظر', tone: 'neg' }, failed: { fa: 'شکست', tone: 'neg' }, rejected: { fa: 'رد یا پایین آمد', tone: 'neutral' },
};
export const KIND_FA: Record<string, { fa: string; icon: IconName }> = {
  reel: { fa: 'ریلز', icon: 'video' }, story: { fa: 'استوری', icon: 'image' }, post: { fa: 'پست', icon: 'image' }, carousel: { fa: 'کاروسل', icon: 'image' }, design: { fa: 'طراحی رابط', icon: 'code' },
};
export const PLACEMENT_FA: Record<string, string> = {
  telegram_post: 'پست کانال تلگرام', telegram_story: 'استوری کانال تلگرام', instagram_reel: 'ریلز اینستاگرام', instagram_story: 'استوری اینستاگرام', instagram_post: 'پست اینستاگرام',
};
export const CHANNEL_FA: Record<string, string> = { telegram: 'تلگرام', instagram: 'اینستاگرام' };
export const CHECK_FA: Record<string, { fa: string; rule: string }> = {
  brand: { fa: 'برند', rule: 'فقط IRANYekanX، رنگ‌ها از پالت شرکت، نشان در جای خودش' },
  red_lines: { fa: 'خطوط قرمز', rule: 'الگوهای خط قرمز اساسنامه روی سناریو، متن تصویر و زیرنویس' },
  risk_warning: { fa: 'هشدار ریسک', rule: 'هر محتوای ترید هشدار ریسک دارد، در صدا یا زیرنویس و در caption' },
  facts: { fa: 'منبع عددها', rule: 'هر عدد سناریو منبع و تاریخ دارد' },
  rights: { fa: 'حق استفاده', rule: 'فقط فایل خود شرکت، ساخته‌شده یا موسیقی کتابخانه‌ی مجاز' },
  platform: { fa: 'محدودیت پلتفرم', rule: 'نسبت، طول، حجم و codec طبق محدودیت خود پلتفرم' },
  qc: { fa: 'بازبینی مدیر رسانه', rule: 'رأی مدیر رسانه (media.review)' },
};
export const RESULT: Record<string, Label & { icon: IconName }> = {
  pass: { fa: 'قبول', tone: 'pos', icon: 'seal' }, fail: { fa: 'رد', tone: 'neg', icon: 'urgent' }, 'n/a': { fa: 'لازم نیست', tone: 'neutral', icon: 'info' },
};
export const QC_VERDICT: Record<string, Label> = { pass: { fa: 'قبول', tone: 'pos' }, changes: { fa: 'اصلاح لازم', tone: 'warn' }, reject: { fa: 'رد', tone: 'neg' } };
export const PUBLISH_ERROR: Record<string, string> = {
  no_api: 'API رسمی ندارد؛ با دست خودت', account_not_configured: 'حساب کلید ندارد', removed: 'از API حذف شد', remove_by_hand: 'API حذف را اجازه نداد؛ از خود اپ پایین بیاور',
  platform_limit: 'سقف خود پلتفرم پر بود', series_not_sealed: 'برنامه مُهر نبود', held: 'نگه‌داشته‌ی ناظر',
};
export const SERIES_STATUS: Record<string, Label & { icon: IconName }> = {
  draft: { fa: 'پیش‌نویس، مُهرنشده', tone: 'neutral', icon: 'edit' }, proposed: { fa: 'منتظر مُهر تو', tone: 'gold', icon: 'seal' }, sealed: { fa: 'مُهرشده', tone: 'pos', icon: 'seal' },
  paused: { fa: 'متوقف', tone: 'warn', icon: 'pause' }, retired: { fa: 'بازنشسته', tone: 'neutral', icon: 'close' },
};
export const CASE_KIND: Record<string, string> = {
  platform_restriction: 'محدودیت پلتفرم', account_appeal: 'اعتراض حساب', takedown: 'درخواست حذف', partner_dispute: 'اختلاف با شریک', policy_review: 'بازبینی سیاست',
  contract_review: 'بازبینی قرارداد', compliance: 'انطباق', other: 'دیگر',
};
export const CASE_STATUS: Record<string, Label & { live?: boolean }> = {
  open: { fa: 'باز', tone: 'lapis' }, waiting_reply: { fa: 'منتظر جواب', tone: 'neutral', live: true }, waiting_owner: { fa: 'منتظر تو', tone: 'gold' }, resolved: { fa: 'حل شد', tone: 'pos' }, closed: { fa: 'بسته', tone: 'neutral' },
};
export const TIMELINE: Record<string, { fa: string; icon: IconName }> = {
  note: { fa: 'یادداشت', icon: 'edit' }, email_out: { fa: 'ایمیل رفت', icon: 'send' }, email_in: { fa: 'ایمیل آمد', icon: 'messages' }, form: { fa: 'فرم', icon: 'report' }, decision: { fa: 'تصمیم', icon: 'seal' },
};
export const ROLE_STATE: Record<string, Label & { live?: boolean }> = {
  drafting: { fa: 'مدیر مینویسد', tone: 'lapis', live: true }, in_review: { fa: 'بازبینی ناظر', tone: 'lapis', live: true }, eval: { fa: 'آزمون خودش', tone: 'lapis', live: true },
  proposed: { fa: 'منتظر تأیید', tone: 'gold' }, active: { fa: 'فعال', tone: 'pos' }, rejected: { fa: 'رد شد', tone: 'neg' }, retired: { fa: 'بازنشسته', tone: 'neutral' },
};
export const ROLE_GATES: Array<{ state: string; fa: string }> = [
  { state: 'drafting', fa: 'نوشتن' }, { state: 'in_review', fa: 'بازبینی ناظر' }, { state: 'eval', fa: 'آزمون' }, { state: 'proposed', fa: 'تأیید' }, { state: 'active', fa: 'فعال' },
];

// ------------------------------------------------------------------ schedules (RRULE, owner TZ) --
const DAY_ORDER = ['SA', 'SU', 'MO', 'TU', 'WE', 'TH', 'FR'] as const;
export const DAY_FA: Record<string, string> = { SA: 'شنبه', SU: 'یکشنبه', MO: 'دوشنبه', TU: 'سه‌شنبه', WE: 'چهارشنبه', TH: 'پنجشنبه', FR: 'جمعه' };
export const DAY_SHORT: Record<string, string> = { SA: 'ش', SU: 'ی', MO: 'د', TU: 'س', WE: 'چ', TH: 'پ', FR: 'ج' };
export type Rule = { freq: 'DAILY' | 'WEEKLY'; days: string[]; hour: number; minute: number };
/** The simple RRULEs the series editor writes (daily, or weekly on chosen days, at one time); anything else is shown raw. */
export function parseRrule(s: string): Rule | null {
  const p = Object.fromEntries(s.split(';').map((kv) => kv.split('=') as [string, string]));
  if (p.FREQ !== 'DAILY' && p.FREQ !== 'WEEKLY') return null;
  const hour = Number(p.BYHOUR), minute = Number(p.BYMINUTE ?? 0);
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || String(p.BYHOUR ?? '').includes(',')) return null;
  return { freq: p.FREQ, days: p.FREQ === 'WEEKLY' ? (p.BYDAY ?? '').split(',').filter(Boolean) : [], hour, minute };
}
export function buildRrule(r: Rule): string {
  const days = DAY_ORDER.filter((d) => r.days.includes(d));
  return r.freq === 'DAILY' || !days.length ? `FREQ=DAILY;BYHOUR=${r.hour};BYMINUTE=${r.minute}` : `FREQ=WEEKLY;BYDAY=${days.join(',')};BYHOUR=${r.hour};BYMINUTE=${r.minute}`;
}
export const hhmm = (h: number, m: number) => `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
/** «شنبه و سه‌شنبه» + the time as a Latin figure. */
export function Schedule({ rrule, className }: { rrule: string; className?: string }) {
  const r = parseRrule(rrule);
  if (!r) return <span dir="ltr" className={cx('fig text-[12px]', className)}>{rrule}</span>;
  const days = r.freq === 'DAILY' ? 'هر روز' : DAY_ORDER.filter((d) => r.days.includes(d)).map((d) => DAY_FA[d]).join('، ');
  return <span className={className}>{days}، ساعت <span className="fig">{hhmm(r.hour, r.minute)}</span></span>;
}

// ------------------------------------------------------------------ pieces --
const ratio = (a: string) => { const [w, h] = a.split(':').map(Number) as [number, number]; return `${w} / ${h}`; };
export const aspectOfItem = (x: Pick<MediaItem, 'kind' | 'render'>, fallback?: string) => {
  const r = x.render;
  if (r?.width && r.height) return `${r.width}:${r.height}`;
  return fallback ?? (x.kind === 'design' ? '16:10' : x.kind === 'post' ? '1:1' : x.kind === 'carousel' ? '4:5' : '9:16');
};

/** A render as the owner checks it: a plain <video> with its poster, or the still; a placeholder while there is none. */
export function RenderPreview({ file, aspect, label, className, compact }: { file: MediaFile | null; aspect: string; label: string; className?: string; compact?: boolean }) {
  const video = file?.mime.startsWith('video/');
  return (
    <div className={cx('relative flex items-center justify-center overflow-hidden rounded-[12px] bg-page', className)} style={{ aspectRatio: ratio(aspect) }}>
      {file && video ? (
        compact ? (
          // eslint-disable-next-line @next/next/no-img-element -- the render's poster frame, from the hub's own store (§17.1)
          <img src={fileUrl(file.id, 'poster')} alt={label} className="size-full object-cover" />
        ) : (
          <video src={fileUrl(file.id)} poster={fileUrl(file.id, 'poster')} controls playsInline preload="metadata" aria-label={label} className="size-full bg-black object-contain" />
        )
      ) : file && file.mime.startsWith('image/') ? (
        // eslint-disable-next-line @next/next/no-img-element -- the render, from the hub's own store (§17.1)
        <img src={fileUrl(file.id)} alt={label} className="size-full object-cover" />
      ) : (
        <span className="flex flex-col items-center gap-1.5 px-2 text-center text-muted" title="هنوز رندر نشده"><Icon name="video" size={compact ? 18 : 28} />{compact ? null : <span className="text-[11px]">هنوز رندر نشده</span>}</span>
      )}
      {file && video && compact ? <span className="absolute inset-0 flex items-center justify-center"><span className="flex size-9 items-center justify-center rounded-full bg-[rgba(11,13,20,.66)] text-[#F2EEE4]"><Icon name="resume" size={18} /></span></span> : null}
    </div>
  );
}

/** Where an item is in the pipeline: eight steps, the current one marked; a stopped item says why in a pill. */
export function StageTrack({ state, design }: { state: ItemState; design?: boolean }) {
  const at = stageOf(state);
  const steps = design ? STAGES.filter((s) => ['script', 'motion', 'render', 'checks'].includes(s.key)) : STAGES;
  const idx = design ? steps.findIndex((s) => s.states.includes(state)) : at;
  return (
    <ol className="flex flex-wrap items-center gap-1" aria-label="مرحله‌ی خط تولید">
      {steps.map((s, i) => {
        const done = idx > i || state === 'published';
        const now = idx === i && state !== 'published';
        return (
          <li key={s.key} className={cx('flex h-7 items-center gap-1 rounded-full px-2 text-[11px]', now ? 'bg-gold-soft font-semibold text-gold-ink' : done ? 'bg-pos-soft text-pos' : 'bg-tile text-muted')} aria-current={now ? 'step' : undefined}>
            <Icon name={done ? 'seal' : s.icon} size={12} />{design && s.key === 'script' ? 'brief' : s.fa}
          </li>
        );
      })}
      {STOPPED.includes(state) ? <li><Pill tone={ITEM_STATE[state]!.tone} icon="urgent">{ITEM_STATE[state]!.fa}</Pill></li> : null}
    </ol>
  );
}

/** The seven checks of §22.2 by code; a missing one is still running. */
export function CheckGrid({ checks, design }: { checks: CheckResult[]; design?: boolean }) {
  const keys = design ? (['brand', 'rights'] as string[]) : CHECKS;
  return (
    <ul className="grid gap-1.5 sm:grid-cols-2">
      {keys.map((k) => {
        const c = checks.find((x) => x.key === k);
        const r = c ? RESULT[c.result] ?? RESULT['n/a']! : null;
        return (
          <li key={k} className={cx('flex items-start gap-2 rounded-[10px] p-2.5', c?.result === 'fail' ? 'bg-neg-soft' : 'bg-tile')}>
            <span className={cx('mt-0.5', !r ? 'text-muted' : r.tone === 'pos' ? 'text-pos' : r.tone === 'neg' ? 'text-neg' : 'text-muted')}><Icon name={r?.icon ?? 'time'} size={15} /></span>
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="flex flex-wrap items-center gap-1.5 text-[12px] font-semibold text-ink">{CHECK_FA[k]?.fa ?? k}<span className={cx('text-[11px] font-normal', !r ? 'text-muted' : r.tone === 'neg' ? 'text-neg' : 'text-sec')}>{r ? r.fa : 'در صف'}</span></span>
              <span className="text-[11px] leading-5 text-muted">{c?.note_fa ?? CHECK_FA[k]?.rule}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** Where and when it goes out, through which official API, and what came back. */
export function PublishRows({ rows }: { rows: PublishRow[] }) {
  if (!rows.length) return <p className="text-[12px] text-muted">جای انتشاری ندارد.</p>;
  return (
    <ul className="flex flex-col gap-1.5">
      {rows.map((r) => (
        <li key={`${r.channel}-${r.placement}`} className="flex flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[12px]">
          <span className="font-semibold text-ink">{PLACEMENT_FA[r.placement] ?? r.placement}</span>
          {r.error ? <Pill tone={r.error === 'removed' ? 'neutral' : 'warn'} icon="urgent">{PUBLISH_ERROR[r.error] ?? r.error}</Pill>
            : r.external_id ? <Pill tone="pos" icon="seal">{r.external_id === 'manual' ? 'با دست تو گذاشته شد' : 'منتشر شد'}</Pill>
              : r.at ? <Pill tone="lapis" icon="time">در صف زمان‌بندی</Pill> : <Pill tone="neutral">هنوز نه</Pill>}
          {r.at ? <span className="text-muted">{jDateTime(r.at)}</span> : null}
          <span className="flex-1" />
          {r.url ? <a href={r.url} target="_blank" rel="noreferrer noopener" className="fig text-gold-ink hover:underline">{r.external_id ?? 'لینک'}</a> : r.external_id && r.external_id !== 'manual' ? <span className="fig text-muted">{r.external_id}</span> : null}
        </li>
      ))}
    </ul>
  );
}

/** A file as a small Latin chip (name and size); its content lives in the hub's store. */
export function FileChip({ f, icon = 'attach' }: { f: { name: string; size: number }; icon?: IconName }) {
  const kb = f.size >= 1_048_576 ? `${(f.size / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(f.size / 1024))} KB`;
  return <span className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-tile px-2.5 py-1 text-[11px] text-sec"><Icon name={icon} size={12} /><span className="fig truncate">{f.name}</span><span className="fig text-muted">{kb}</span></span>;
}

export function Block({ title, children, action, className }: { title: ReactNode; children: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <section className={cx('flex flex-col gap-2', className)}>
      <div className="flex items-center gap-2"><h3 className="min-w-0 flex-1 text-[12px] font-semibold text-gold-ink">{title}</h3>{action}</div>
      {children}
    </section>
  );
}

/** «غیرتجاری» is said on every use of such a voice (§22.3). */
export function LicenceBadge({ commercial, licence }: { commercial: boolean; licence: string }) {
  return commercial
    ? <span className="inline-flex items-center gap-1 rounded-full bg-tile px-2 py-0.5 text-[11px] text-sec"><Icon name="lock" size={11} /><span className="fig">{licence}</span></span>
    : <span className="inline-flex items-center gap-1 rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-semibold text-warn"><Icon name="urgent" size={11} />غیرتجاری · <span className="fig font-normal">{licence}</span></span>;
}
