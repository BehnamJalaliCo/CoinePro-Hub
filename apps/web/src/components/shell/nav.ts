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

export const NAV_TOOLS: NavItem[] = [
  { href: '/stars', label: 'ستاره‌ها', icon: 'star' },
  { href: '/founding', label: 'تأسیس شرکت', icon: 'found' },
  { href: '/skills', label: 'مهارت‌ها', icon: 'skill' },
  { href: '/academy', label: 'آکادمی', icon: 'academy' },
  { href: '/tools', label: 'ابزارها و اینترنت', icon: 'globe' },
  { href: '/treasury', label: 'خزانه‌ی توکن', icon: 'treasury' },
  { href: '/planner', label: 'پلنر', icon: 'planner' },
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
