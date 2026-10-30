import type { IconName } from '@/generated/icons';

/** `exact`: active only on its own path, when a deeper page has an entry of its own (/media and /media/series). */
export type NavItem = { href: string; label: string; icon: IconName; badge?: 'decisions' | 'deliverables' | 'messages'; exact?: boolean };

export const NAV_MAIN: NavItem[] = [
  { href: '/', label: 'فرمان', icon: 'command' },
  { href: '/orders', label: 'فرمان‌های من', icon: 'delegate' },
  { href: '/cartable', label: 'کارتابل', icon: 'cartable', badge: 'decisions' },
  { href: '/outputs', label: 'خروجی‌ها', icon: 'deliverable', badge: 'deliverables' },
  { href: '/advisor', label: 'مشاور کل', icon: 'advisor' },
  { href: '/oversight', label: 'ناظر کل', icon: 'overseer' },
  { href: '/assistant', label: 'دستیار', icon: 'assistant' },
  { href: '/companies', label: 'شرکت‌ها', icon: 'companies' },
  { href: '/messages', label: 'پیام‌ها', icon: 'messages', badge: 'messages' },
  { href: '/workshop', label: 'کارگاه کد', icon: 'code' },
];

// ⟨1.5⟩ management tools (§21): quick notes, the spoken briefings and CEO letters, the substitute players, the digital CEO.
export const NAV_MANAGEMENT: NavItem[] = [
  { href: '/notes', label: 'یادداشت‌ها', icon: 'edit' },
  { href: '/letter', label: 'گزارش صوتی و نامه‌ها', icon: 'mic' },
  { href: '/substitutes', label: 'بازیکن‌های ذخیره', icon: 'agent' },
  { href: '/digital-ceo', label: 'مدیر کل دیجیتال', icon: 'holding' },
];

// ⟨1.6⟩ the media studio and the legal counsel (§22): each company's pipeline, the sealed publishing series, the hub's own voice, the cases.
export const NAV_MEDIA: NavItem[] = [
  { href: '/media', label: 'استودیوی رسانه', icon: 'video', exact: true },
  { href: '/media/series', label: 'برنامه‌های انتشار', icon: 'send' },
  { href: '/media/voice', label: 'صدای هاب', icon: 'mic' },
  { href: '/legal', label: 'مشاور حقوقی', icon: 'decision' },
];

// ⟨1.7⟩ the archive of record (§23): search and intake, legal holds, reminders, the end of retention, and the open layer.
export const NAV_ARCHIVE: NavItem[] = [
  { href: '/archive', label: 'بایگانی', icon: 'deliverable', exact: true },
  { href: '/archive/holds', label: 'توقیف‌ها', icon: 'lock' },
  { href: '/archive/reminders', label: 'یادآورها', icon: 'time' },
  { href: '/archive/retention', label: 'پایان نگهداری', icon: 'memory' },
  { href: '/archive/settings', label: 'طرح بایگانی', icon: 'settings' },
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
  // ⟨1.8⟩ §26: the companies' servers, the holding's network map and the few things that wait for the owner's seal there.
  { href: '/servers', label: 'همه‌ی سرورها', icon: 'server' },
  { href: '/network', label: 'شبکه‌ی هلدینگ', icon: 'globe' },
  { href: '/server-policy', label: 'قوانین سرورها', icon: 'seal' },
  { href: '/control', label: 'کنترل', icon: 'lock' },
  { href: '/audit', label: 'دفتر Audit', icon: 'report' },
  { href: '/notifications', label: 'اعلان‌ها', icon: 'bell' },
  { href: '/settings', label: 'تنظیمات', icon: 'settings' },
  { href: '/errors', label: 'خطاخوان', icon: 'urgent' },
];

/** Android-style bottom bar (D1 shell): the advisor orb sits in the middle. */
export const NAV_MOBILE: NavItem[] = [
  { href: '/', label: 'فرمان', icon: 'command' },
  { href: '/cartable', label: 'کارتابل', icon: 'cartable', badge: 'decisions' },
  { href: '/advisor', label: 'مشاور', icon: 'advisor' },
  { href: '/companies', label: 'شرکت‌ها', icon: 'companies' },
  { href: '/messages', label: 'پیام‌ها', icon: 'messages', badge: 'messages' },
];

export const isActive = (pathname: string, href: string, exact = false) => (href === '/' || exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`));
