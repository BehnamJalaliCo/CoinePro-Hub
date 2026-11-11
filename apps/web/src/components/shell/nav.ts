import type { IconName } from '@/generated/icons';

/** «میز انتشار» (⟨1.0.1⟩ §55.2), the other half of where outputs live. */
export const DESK_HREF = '/outputs/desk';

/** `exact`: active only on its own path, when a deeper page has an entry of its own (/media and /media/series). */
export type NavItem = { href: string; label: string; icon: IconName; badge?: 'decisions' | 'deliverables' | 'messages' | 'sessions'; exact?: boolean };

export const NAV_MAIN: NavItem[] = [
  // ⟨1.17⟩ §35: the owner's office, his sessions (every order is one), the cards for his seal, the companies, the messages, the outputs.
  { href: '/', label: 'دفتر', icon: 'holding', exact: true },
  { href: '/s', label: 'جلسه‌ها', icon: 'messages', badge: 'sessions' },
  { href: '/cartable', label: 'کارتابل', icon: 'cartable', badge: 'decisions' },
  { href: '/companies', label: 'شرکت‌ها', icon: 'companies' },
  // ⟨1.22⟩ §40: the working groups a session made, ready to give to any company or platform.
  { href: '/playbooks', label: 'کارگروه‌های آماده', icon: 'seal' },
  { href: '/messages', label: 'پیام‌ها', icon: 'messages', badge: 'messages' },
  { href: '/outputs', label: 'خروجی‌ها', icon: 'deliverable', badge: 'deliverables', exact: true },
  // ⟨1.0.1⟩ §55.2: everything that can go out, is set to go out, or went out. Hidden on a hub that does not serve the desk.
  { href: DESK_HREF, label: 'میز انتشار', icon: 'send' },
];

// The business, beside the office: talk, the working groups, the connections that measure them, the owner's rules, the people who advise.
export const NAV_BUSINESS: NavItem[] = [
  // ⟨1.14⟩ §32: the owner talks with the holding (secretary, overseer, assistant, advisor, any manager), by voice or text.
  { href: '/talk', label: 'گفتگو', icon: 'messages' },
  { href: '/orders', label: 'فرمان‌های قدیمی', icon: 'delegate' },
  // ⟨1.11⟩ §29: the business first — the working groups, the connections that measure them, the owner's rules.
  { href: '/groups', label: 'کارگروه‌ها', icon: 'companies' },
  { href: '/campaign-calendar', label: 'تقویم کمپین', icon: 'planner' },
  { href: '/automations', label: 'اتوماسیون از یک جمله', icon: 'task' },
  { href: '/company-kit', label: 'شرکت آماده', icon: 'companies' },
  { href: '/library', label: 'کتابخانه‌ی تولید', icon: 'attach' },
  { href: '/connections', label: 'اتصال‌ها', icon: 'globe' },
  { href: '/rules', label: 'قانون‌های من', icon: 'seal' },
  { href: '/advisor', label: 'مشاور کل', icon: 'advisor' },
  { href: '/oversight', label: 'ناظر کل', icon: 'overseer' },
  { href: '/assistant', label: 'دستیار', icon: 'assistant' },
  // ⟨1.5⟩ revenue and support (§19); ⟨1.15⟩ §33: usage in the advisor's words, and every company's journey on one timeline.
  { href: '/revenue', label: 'درآمد', icon: 'chart', exact: true },
  { href: '/usage', label: 'مصرف', icon: 'treasury' },
  { href: '/journeys', label: 'سفر شرکت‌ها', icon: 'planner' },
  { href: '/support', label: 'پشتیبانی', icon: 'messages' },
  { href: '/growth', label: 'رشد و پیام‌ها', icon: 'send' },
  { href: '/feedback', label: 'بازخورد', icon: 'rate' },
  { href: '/stars', label: 'ستاره‌ها', icon: 'star' },
  { href: '/founding', label: 'تأسیس شرکت', icon: 'found' },
  { href: '/skills', label: 'مهارت‌ها', icon: 'skill' },
  { href: '/academy', label: 'آکادمی', icon: 'academy' },
  { href: '/planner', label: 'پلنر', icon: 'planner' },
  { href: '/resolutions', label: 'دفتر مصوبات', icon: 'seal' },
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

/** «فنی» (⟨1.17⟩): everything technical, folded away from the owner's daily view. Each company's own technical part lives under «شرکت ← فنی». */
export const NAV_TECH: NavItem[] = [
  { href: '/tools', label: 'ابزارها و اینترنت', icon: 'globe' },
  { href: '/treasury', label: 'خزانه‌ی مصرف', icon: 'treasury' },
  { href: '/runs', label: 'اجرای ایجنت‌ها', icon: 'agent' },
  { href: '/sites', label: 'پایش سایت‌ها', icon: 'server' },
  // ⟨1.8⟩ §26: the companies' servers, the holding's network map and the few things that wait for the owner's seal there. ⟨1.11⟩ With the
  // watch and the code workshop, these are technical.
  { href: '/watch', label: 'دیده‌بان', icon: 'scope' },
  { href: '/workshop', label: 'کارگاه کد', icon: 'code' },
  { href: '/servers', label: 'همه‌ی سرورها', icon: 'server' },
  { href: '/network', label: 'شبکه‌ی هلدینگ', icon: 'globe' },
  { href: '/server-policy', label: 'قوانین سرورها', icon: 'seal' },
  { href: '/services', label: 'سرویس‌ها', icon: 'server' },
  { href: '/control', label: 'کنترل', icon: 'lock' },
  { href: '/audit', label: 'دفتر Audit', icon: 'report' },
  { href: '/notifications', label: 'اعلان‌ها', icon: 'bell' },
  { href: '/settings', label: 'تنظیمات', icon: 'settings' },
  { href: '/errors', label: 'خطاخوان', icon: 'urgent' },
];

/** Android-style bottom bar (D1 shell): the advisor orb sits in the middle. */
export const NAV_MOBILE: NavItem[] = [
  { href: '/', label: 'دفتر', icon: 'holding', exact: true },
  { href: '/s', label: 'جلسه‌ها', icon: 'messages', badge: 'sessions' },
  { href: '/cartable', label: 'کارتابل', icon: 'cartable', badge: 'decisions' },
  { href: '/companies', label: 'شرکت‌ها', icon: 'companies' },
  { href: '/messages', label: 'پیام‌ها', icon: 'messages', badge: 'messages' },
];

export const isActive = (pathname: string, href: string, exact = false) => (href === '/' || exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`));
