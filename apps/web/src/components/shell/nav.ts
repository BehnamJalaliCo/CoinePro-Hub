import type { IconName } from '@/generated/icons';

export type NavItem = { href: string; label: string; icon: IconName; badge?: 'decisions' | 'deliverables' | 'messages' };

export const NAV_MAIN: NavItem[] = [
  { href: '/', label: 'فرمان', icon: 'command' },
  { href: '/cartable', label: 'کارتابل', icon: 'cartable', badge: 'decisions' },
  { href: '/outputs', label: 'خروجی‌ها', icon: 'deliverable', badge: 'deliverables' },
  { href: '/advisor', label: 'مشاور کل', icon: 'advisor' },
  { href: '/companies', label: 'شرکت‌ها', icon: 'companies' },
  { href: '/messages', label: 'پیام‌ها', icon: 'messages', badge: 'messages' },
];

export const NAV_TOOLS: NavItem[] = [
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
