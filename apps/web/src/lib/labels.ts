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
  code_session: { fa: 'جلسه‌ی کارگاه کد', icon: 'code' },
  protocol: { fa: 'پروتکل نظارت', icon: 'overseer' },
  tool_enable: { fa: 'روشن کردن ابزار', icon: 'globe' },
  errand_action: { fa: 'تعهد دستیار', icon: 'assistant' },
  company_found: { fa: 'تأسیس شرکت', icon: 'found' },
  server_plan: { fa: 'طرح سرور', icon: 'server' },
  lesson_adoption: { fa: 'پذیرش درس', icon: 'learning' },
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

export const DEPT_FA: Record<string, string> = {
  TECH: 'فنی', GROWTH: 'رشد', SALES: 'فروش', PRODUCT: 'محصول', FIN: 'مالی', QUANT: 'کوانت', AIOPS: 'عملیات AI', HR: 'منابع انسانی', OVS: 'نظارت',
};

/** Charter role keys (agents/roles/*.md) as the owner reads them. */
export const ROLE_FA: Record<string, string> = {
  ceo: 'مدیرعامل', manager: 'مدیر', cto: 'مدیر فنی', sre: 'مهندس پایداری', growth: 'مدیر رشد', sales: 'فروش', support: 'پشتیبانی', quant: 'کوانت',
  advisor: 'مشاور کل', overseer: 'ناظر کل', assistant: 'دستیار', inspector: 'بازرس کیفیت', fact_checker: 'راستی‌آزما', security_analyst: 'تحلیلگر امنیت',
  aiops_head: 'مدیر عملیات AI', ai_safety: 'ایمنی AI', hub_platform_sre: 'پایداری پلتفرم هاب',
};

export const ACTOR_FA =(a: { kind: string; code: string; display_fa?: string | null } | null | undefined): string =>
  !a ? '—' : a.display_fa ?? (a.kind === 'owner' ? 'مدیر کل' : a.kind === 'system' || a.kind === 'service' ? 'سیستم' : a.code);
