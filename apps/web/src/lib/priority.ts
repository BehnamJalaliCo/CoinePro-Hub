import type { IconName } from '@/generated/icons';

/**
 * A work priority as the owner reads it (0.4.0; OPERATING_MODEL, the model queue's priorities; contract §4 and §16.5): a Persian name
 * first, the code (`P0`…`P4`, Latin) small beside it, and one line on what it means for the queue. The tone follows the status colours'
 * meaning: red only for the emergency, amber for what users see, lapis for the owner's level, quiet for the rest. The same five as the
 * Android app's core/format/Priority.kt, word for word.
 */
export type PriorityTone = 'neg' | 'warn' | 'lapis' | 'neutral' | 'silver';
export type Priority = { code: string; fa: string; line: string; tone: PriorityTone; icon: IconName };

export const PRIORITIES: Priority[] = [
  { code: 'P0', fa: 'اضطراری', line: 'حادثه و اتاق جنگ؛ حتی وقتی کلید توقف روشن است اجرا میشود. فقط برای اتفاق واقعی.', tone: 'neg', icon: 'urgent' },
  { code: 'P1', fa: 'فوری', line: 'چیزی که کاربران محصول مستقیم میبینند؛ جلوتر از کارهای دیگر در صف.', tone: 'warn', icon: 'owner' },
  { code: 'P2', fa: 'مهم', line: 'هم‌سطح گفت‌وگوی تو با مشاور؛ همیشه یک جای خالی در صف برایش رزرو است.', tone: 'lapis', icon: 'star' },
  { code: 'P3', fa: 'عادی', line: 'کار عملیاتی و زمان‌بندی‌شده؛ پیش‌فرض بیشتر فرمان‌ها.', tone: 'neutral', icon: 'task' },
  { code: 'P4', fa: 'هر وقت شد', line: 'پس‌زمینه (محتوا، گزارش غیرفوری)؛ وقتی سهمیه به هشدار برسد اول همین‌ها مکث میکنند.', tone: 'silver', icon: 'sleeping' },
];

/** The default of a new order (contract §4: `priority` defaults to P3). */
export const DEFAULT_PRIORITY = 'P3';

/** A code from the API, as the owner reads it; an unknown code keeps its own text. */
export function priority(code: string | null | undefined): Priority {
  const c = code?.trim() ?? '';
  return PRIORITIES.find((p) => p.code.toLowerCase() === c.toLowerCase()) ?? { code: c || '—', fa: c || '—', line: 'اولویتی که پنل نمیشناسد.', tone: 'neutral', icon: 'task' };
}

/** "اضطراری (P0)", for sentences. */
export function priorityPhrase(code: string | null | undefined): string {
  const p = priority(code);
  return p.fa === p.code ? p.code : `${p.fa} (${p.code})`;
}

/** P0 and P1 come first; the rest are not urgent. */
export const isUrgentPriority = (code: string | null | undefined) => code === 'P0' || code === 'P1';
