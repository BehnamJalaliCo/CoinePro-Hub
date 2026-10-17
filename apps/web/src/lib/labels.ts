import type { IconName } from '@/generated/icons';

export const DECISION_KIND: Record<string, { fa: string; icon: IconName }> = {
  hire: { fa: 'استخدام', icon: 'hire' },
  dismissal: { fa: 'برکناری', icon: 'dismiss' },
  recurring_approval: { fa: 'کار دائمی', icon: 'time' },
  deploy: { fa: 'انتشار (deploy)', icon: 'server' },
  a3_action: { fa: 'اقدام بیرونی', icon: 'share' },
  proposal: { fa: 'پیشنهاد رشد', icon: 'chart' },
  budget_change: { fa: 'تغییر بودجه', icon: 'budget' },
  evaluation: { fa: 'ارزیابی', icon: 'rate' },
};

export const DECISION_STATUS: Record<string, string> = {
  pending: 'منتظر مُهر',
  approved: 'مُهر شد',
  rejected: 'رد شد',
  returned: 'برگشت خورد',
  expired: 'منقضی',
  withdrawn: 'پس گرفته شد',
};

export const RISK: Record<string, { fa: string; tone: 'pos' | 'warn' | 'neg' }> = {
  low: { fa: 'ریسک کم', tone: 'pos' },
  medium: { fa: 'ریسک متوسط', tone: 'warn' },
  high: { fa: 'ریسک بالا', tone: 'neg' },
};

export const WORK_STATUS: Record<string, string> = {
  queued: 'در صف',
  in_progress: 'در حال انجام',
  waiting: 'منتظر',
  delivered: 'تحویل شد',
  done: 'تمام شد',
  cancelled: 'لغو شد',
  failed: 'ناموفق',
};

export const WORK_KIND: Record<string, string> = {
  one_off: 'یک‌باره',
  recurring: 'دائمی',
  event: 'رویدادمحور',
  project: 'پروژه',
};

export const LEVEL: Record<string, { fa: string; icon: IconName; tone: string }> = {
  urgent: { fa: 'فوری', icon: 'urgent', tone: 'neg' },
  decision: { fa: 'تصمیم', icon: 'level-decision', tone: 'warn' },
  report: { fa: 'گزارش', icon: 'level-report', tone: 'lapis' },
  info: { fa: 'اطلاع', icon: 'info', tone: 'pos' },
  learning: { fa: 'یادگیری', icon: 'learning', tone: 'learn' },
};

export const EMPLOYEE_KIND: Record<string, string> = {
  ceo: 'مدیرعامل',
  manager: 'مدیر',
  employee: 'کارمند',
  advisor: 'مشاور کل',
  inspector: 'بازرس',
  system: 'سیستم',
};

export const ACTIVITY: Record<string, string> = {
  working: 'در حال کار',
  waiting: 'منتظر',
  idle: 'آماده',
  sleeping: 'خواب',
  error: 'خطا',
};

export const DEPT_ICON: Record<string, IconName> = {
  TECH: 'server', GROWTH: 'chart', SALES: 'messages', PRODUCT: 'deliverable', FIN: 'treasury',
  QUANT: 'budget', AIOPS: 'model', HR: 'department', OVS: 'search',
};

export const ACTOR_FA = (a: { kind: string; code: string; display_fa?: string | null } | null | undefined): string =>
  !a ? '—' : a.display_fa ?? (a.kind === 'owner' ? 'مدیر کل' : a.kind === 'system' ? 'سیستم' : a.code);
