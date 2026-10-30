'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Skeleton } from '@/components/ui/primitives';
import type { IconName } from '@/generated/icons';
import { useWorkLabel } from '@/lib/api/v21';
import { WORK_STATUS } from '@/lib/labels';
import { agentTitleOf } from '@/lib/orders';
import { isHuman, isWorkRef, refRoute } from '@/lib/refs';
import type { StreamEvent } from '@/lib/stream';
import { ago, cx } from '@/lib/format';

// One line of a live feed in words (0.3.0, 0.4.0; the Android app's FeedLine): who did what to which work, by its ref and title — never an
// id. A line about a work item carries the work's ref and title, looked up once per session when the event names only an id; a skeleton
// holds its place until it resolves. An event the feed has no sentence for names its topic, and a ref only when it is one a person can read.

export type FeedRow = { at: string; type: string; ref: string | null; employee: string | null; state: string | null; work: string | null; status: string | null; to: string | null };
const s = (v: unknown) => (typeof v === 'string' && v ? v : null);
export const feedRowOf = (e: StreamEvent): FeedRow => ({
  at: e.at || new Date().toISOString(), type: e.type, ref: e.ref, employee: s(e.data.employee), state: s(e.data.state), work: s(e.data.work), status: s(e.data.status), to: s(e.data.to),
});

/** Persian for a stream topic, for an event the feed has no sentence of its own for. */
const TOPIC_FA: Record<string, string> = {
  file: 'فایل', workshop: 'کارگاه کد', order: 'فرمان صوتی', oversight: 'ناظر کل', inquiry: 'استعلام', errand: 'دستیار', stars: 'ستاره‌ها', skill: 'مهارت‌ها',
  academy: 'آکادمی', founding: 'تأسیس', provision: 'سرور تازه', backup: 'پشتیبان‌گیری', brand: 'نشان شرکت', revenue: 'درآمد', support: 'پشتیبانی', rescue: 'نجات رفرال',
  lifecycle: 'پیام‌های رشد', nps: 'نظرسنجی', feedback: 'بازخورد', meeting: 'جلسه', charter: 'اساسنامه', kpi: 'شاخص‌ها', okr: 'OKR', outcome: 'بازبینی نتیجه',
  risk: 'ریسک', calendar: 'تقویم تغییرات', knowledge: 'دانشنامه', memo: 'یادداشت مشاور', advisor: 'مشاور کل', ask: 'پرسش از هاب', review: 'مرور هفتگی',
  briefing: 'گزارش صوتی', rankings: 'رتبه‌ها', hr: 'ارزیابی منابع انسانی', note: 'یادداشت‌ها', claim: 'ادعاها', dceo: 'مدیر کل دیجیتال', substitute: 'بازیکن ذخیره',
  creative: 'طرح‌ها', media: 'استودیوی رسانه', legal: 'مشاور حقوقی', role: 'نقش‌ها', record: 'بایگانی', reminder: 'یادآور بایگانی', hold: 'توقیف',
  fixity: 'سلامت بایگانی', schema: 'طرح بایگانی', message: 'پیام‌ها', notification: 'اعلان‌ها', employee: 'کارمندها', presence: 'خلوت', budget: 'بودجه',
  llm: 'مصرف مدل', hiring: 'استخدام', story: 'استوری‌ها', company: 'شرکت‌ها', server: 'سرورها', activity: 'فعالیت ایجنت‌ها',
};

function look(r: FeedRow): { icon: IconName; tint: string } {
  if (r.type === 'run.started') return { icon: 'agent', tint: 'text-gold-ink bg-gold-soft' };
  if (r.type === 'run.finished') return r.state === 'done' ? { icon: 'seal', tint: 'text-pos bg-pos-soft' } : { icon: 'urgent', tint: 'text-warn bg-warn-soft' };
  if (r.type === 'work.delegated') return { icon: 'delegate', tint: 'text-lapis bg-lapis-soft' };
  if (r.type === 'work.completed' || (r.type === 'work.updated' && (r.status === 'delivered' || r.status === 'done'))) return { icon: 'seal', tint: 'text-pos bg-pos-soft' };
  if (r.type === 'work.updated' && r.status === 'failed') return { icon: 'urgent', tint: 'text-neg bg-neg-soft' };
  if (r.type.startsWith('work')) return { icon: 'task', tint: 'text-gold-ink bg-gold-soft' };
  if (r.type.startsWith('deliverable')) return { icon: 'deliverable', tint: 'text-silver-ink bg-[var(--hq-silver-soft)]' };
  if (r.type.startsWith('decision')) return { icon: 'cartable', tint: 'text-gold-ink bg-gold-soft' };
  if (r.type.startsWith('control')) return { icon: 'lock', tint: 'text-neg bg-neg-soft' };
  return { icon: 'info', tint: 'text-silver-ink bg-[var(--hq-silver-soft)]' };
}

const Fig = ({ t, gold }: { t: string; gold?: boolean }) => <span className={cx('fig whitespace-nowrap', gold && 'text-gold-ink')}>{t}</span>;

export function FeedLine({ r, compact }: { r: FeedRow; compact?: boolean }) {
  const workKey = (r.type.startsWith('work.') ? r.ref : r.type.startsWith('run.') || r.type.startsWith('deliverable.') ? r.work : null) || null;
  const label = useWorkLabel(workKey);
  const known = label.data ?? null;
  const loading = !!workKey && label.isLoading && (isWorkRef(workKey) || !isHuman(workKey));
  const { icon, tint } = look(r);
  const who = r.employee ? <> <Fig t={r.employee} /></> : null;
  const work = known ? <><Fig t={known.ref} gold /> · {known.title}</> : workKey && isHuman(workKey) ? <Fig t={workKey} gold /> : 'کاری که دیگر در دسترس نیست';
  const humanRef = r.ref && isHuman(r.ref) ? <Fig t={r.ref} gold /> : null;
  let text: ReactNode;
  // The verb first, so a line cut short still says what happened; then the work by ref and title.
  switch (true) {
    case r.type === 'run.started': text = <>اجرای{who} شروع شد{workKey ? <>: {work}</> : null}</>; break;
    case r.type === 'run.finished': text = <>اجرای{who}{r.state === 'done' ? ' تمام شد' : r.state === 'failed' ? ' شکست خورد' : r.state === 'refused' ? ' ایستاد' : ' بسته شد'}{workKey ? <>: {work}</> : null}</>; break;
    case r.type === 'deliverable.created': text = <>خروجی تازه {humanRef}{workKey ? <> برای {work}</> : null}</>; break;
    case r.type === 'deliverable.rated': text = <>امتیاز تو به {humanRef}</>; break;
    case r.type === 'decision.created': text = <>کارت تازه در کارتابل {humanRef}</>; break;
    case r.type === 'decision.decided': text = <>تصمیم {humanRef} گرفته شد</>; break;
    case r.type === 'control.changed': text = 'کلیدها تغییر کرد'; break;
    case r.type === 'work.created': text = <>کار تازه: {work}</>; break;
    case r.type === 'work.delegated': text = <>واگذار شد{r.to ? <> به {agentTitleOf(r.to) ?? <Fig t={r.to} />}</> : null}: {work}</>; break;
    case r.type === 'work.completed': text = <>تمام شد: {work}</>; break;
    case r.type === 'work.updated': text = <>{(r.status && WORK_STATUS[r.status]) || 'به‌روز شد'}: {work}</>; break;
    case r.type.startsWith('work.'): text = <>به‌روز شد: {work}</>; break;
    default: text = <>رویداد تازه در {TOPIC_FA[r.type.split('.')[0]!] ?? 'هاب'}{humanRef ? <> {humanRef}</> : null}</>;
  }
  const href = known ? `/work/${known.id}` : workKey && isWorkRef(workKey) && r.type.startsWith('work') ? `/work/${workKey}`
    : r.ref && (r.type.startsWith('deliverable') || r.type.startsWith('decision')) && isHuman(r.ref) ? refRoute(r.ref) : null;
  const body = (
    <>
      <span className={cx('flex size-7 flex-none items-center justify-center rounded-full', tint)}><Icon name={icon} size={14} /></span>
      {loading ? <span className="flex-1"><Skeleton className="h-3.5 w-4/5" /></span> : <span className={cx('min-w-0 flex-1 text-[13px] leading-6 text-ink', compact ? 'truncate' : 'line-clamp-2')}>{text}</span>}
      <span className="flex-none text-[11px] text-muted">{ago(r.at)}</span>
    </>
  );
  return href
    ? <Link href={href} className="flex items-center gap-2.5 rounded-[8px] px-1 py-1.5 transition-colors hover:bg-hover">{body}</Link>
    : <div className="flex items-center gap-2.5 px-1 py-1.5">{body}</div>;
}
