import type { IconName } from '@/generated/icons';

export type NavItem = { href: string; label: string; icon: IconName; badge?: 'decisions' | 'deliverables' | 'messages' };

export const NAV_MAIN: NavItem[] = [
  { href: '/', label: 'فرمان', icon: 'command' },
  { href: '/cartable', label: 'کارتابل', icon: 'cartable', badge: 'decisions' },
  { href: '/outputs', label: 'خروجی‌ها', icon: 'deliverable', badge: 'deliverables' },
  { href: '/advisor', label: 'مشاور کل', icon: 'advisor' },
  { href: '/oversight', label: 'ناظر کل', icon: 'overseer' },
  { href: '/assistant', label: 'دستیار', icon: 'assistant' },
  { href: '/companies', label: 'شرکت‌ها', icon: 'companies' },
  { href: '/messages', label: 'پیام‌ها', icon: 'messages', badge: 'messages' },
  { href: '/workshop', label: 'کارگاه کد', icon: 'code' },
];

// ⟨1.5⟩ governance (§20): the meeting room, the charter, knowledge, the cards, OKRs, outcomes, risks, the change calendar and authority.
export const NAV_GOVERNANCE: NavItem[] = [
  { href: '/meetings', label: 'اتاق جلسه', icon: 'meeting' },
  { href: '/charter', label: 'اساسنامه', icon: 'report' },
  { href: '/knowledge', label: 'دانشنامه', icon: 'knowledge' },
  { href: '/scorecard', label: 'کارت‌ها و امتیاز', icon: 'chart' },
  { href: '/okr', label: 'OKR', icon: 'planner' },
  { href: '/outcomes', label: 'بازبینی نتیجه', icon: 'refresh' },
  { href: '/risks', label: 'دفتر ریسک', icon: 'urgent' },
  { href: '/calendar', label: 'تقویم تغییرات', icon: 'time' },
  { href: '/authority', label: 'ماتریس اختیار', icon: 'lock' },
];

export const NAV_TOOLS: NavItem[] = [
  // ⟨1.5⟩ revenue and support (§19)
  { href: '/revenue', label: 'درآمد', icon: 'chart' },
  { href: '/support', label: 'پشتیبانی', icon: 'messages' },
  { href: '/growth', label: 'رشد و پیام‌ها', icon: 'send' },
  { href: '/feedback', label: 'بازخورد', icon: 'rate' },
  { href: '/stars', label: 'ستاره‌ها', icon: 'star' },
  { href: '/founding', label: 'تأسیس شرکت', icon: 'found' },
  { href: '/skills', label: 'مهارت‌ها', icon: 'skill' },
  { href: '/academy', label: 'آکادمی', icon: 'academy' },
  { href: '/tools', label: 'ابزارها و اینترنت', icon: 'globe' },
  { href: '/treasury', label: 'خزانه‌ی توکن', icon: 'treasury' },
  { href: '/planner', label: 'پلنر', icon: 'planner' },
  { href: '/resolutions', label: 'دفتر مصوبات', icon: 'seal' },
  { href: '/runs', label: 'اجرای ایجنت‌ها', icon: 'agent' },
  { href: '/sites', label: 'پایش سایت‌ها', icon: 'server' },
  { href: '/control', label: 'کنترل', icon: 'lock' },
  { href: '/audit', label: 'دفتر Audit', icon: 'report' },
  { href: '/settings', label: 'تنظیمات', icon: 'settings' },
];

/** Android-style bottom bar (D1 shell): the advisor orb sits in the middle. */
export const NAV_MOBILE: NavItem[] = [
  { href: '/', label: 'فرمان', icon: 'command' },
  { href: '/cartable', label: 'کارتابل', icon: 'cartable', badge: 'decisions' },
  { href: '/advisor', label: 'مشاور', icon: 'advisor' },
  { href: '/companies', label: 'شرکت‌ها', icon: 'companies' },
  { href: '/messages', label: 'پیام‌ها', icon: 'messages', badge: 'messages' },
];

export const isActive = (pathname: string, href: string) => (href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`));
