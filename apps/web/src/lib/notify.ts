// Notifications as the owner reads them (0.5.0; contract §6): the same alert raised again and again (the overseer's hourly finding) is one
// row with its count, what a notification is about comes from its link (a finding is not a decision, even when the hub raises it at the
// `decision` level), and marking read moves it out of the main list. The Android app's core/data/Notifications.kt, rule for rule.

import { ago, jDate } from './format';
import { LEVEL } from './labels';
import type { Notification } from './api/v21';

/** What a notification is about, from its link's kind (the kinds the hub raises: `raise_notification` callers in apps/api). */
export const KIND_FA: Record<string, string> = {
  decision: 'تصمیم', deliverable: 'خروجی', work: 'کار', thread: 'پیام', message: 'یادداشت مشاور',
  finding: 'یافته‌ی ناظر', hold: 'نگه‌داشت ناظر', challenge: 'چالش ناظر', inquiry: 'استعلام',
  meeting: 'جلسه', founding: 'تأسیس', provision_run: 'ساخت سرور', server_plan: 'طرح سرور',
  code_session: 'کارگاه کد', archive_record: 'بایگانی', archive_fixity: 'سلامت بایگانی',
  support_conversation: 'پشتیبانی', support_queue: 'صف پشتیبانی', revenue_alert: 'درآمد',
  substitute: 'بازیکن ذخیره', employee: 'کارمند', treasury: 'خزانه', academy: 'آکادمی',
  backup: 'پشتیبان‌گیری', audit: 'دفتر Audit', device: 'امنیت ورود', server: 'سرور',
};

/** The label on a notification: what it is about; without a link (a learning question), its level. */
export const categoryOf = (n: Notification) => (n.link?.kind ? KIND_FA[n.link.kind] : undefined) ?? LEVEL[n.level]?.fa ?? n.level;

const NUMBER = /[0-9۰-۹٠-٩]+(?:[.,٫/][0-9۰-۹٠-٩]+)*/g;
/** A title with its figures blanked: «disk 90.4%» and «disk 90.6%» an hour later are the same alert. */
export const normalize = (title: string) => title.trim().replace(/\s+/g, ' ').replace(NUMBER, '#');

/** Rows that are the same alert: one company, one level, one kind of link, one title (figures aside). A question with choices is never
 *  folded: each one waits for its own answer. */
export const groupKey = (n: Notification) => (n.choices?.length ? `id:${n.id}` : [n.company, n.level, n.link?.kind ?? '', normalize(n.title_fa)].join('|'));

export type NotificationGroup = { key: string; items: Notification[]; latest: Notification; count: number; ids: string[]; folded: boolean };

/** [list] folded into groups, in the order of each group's newest row; inside a group, newest first. */
export function groupNotifications(list: Notification[]): NotificationGroup[] {
  const out = new Map<string, Notification[]>();
  for (const n of [...list].sort((a, b) => b.created_at.localeCompare(a.created_at))) {
    const k = groupKey(n);
    const g = out.get(k);
    if (g) g.push(n); else out.set(k, [n]);
  }
  return [...out].map(([key, items]) => ({ key, items, latest: items[0]!, count: items.length, ids: items.map((n) => n.id), folded: items.length > 1 }));
}

/** «۵ بار، آخرین ۴۴ دقیقه پیش» (the text face draws the figures in Persian). */
export const countLine = (g: NotificationGroup) => `${g.count} بار، آخرین ${ago(g.latest.created_at)}`;

/**
 * The two lists the page shows, from the hub's unread and read pages and what the owner marked a moment ago ([marked]: id → when): a marked
 * row leaves «خوانده‌نشده» at once and stands in «خوانده‌شده» with its local time until the hub confirms it.
 */
export function splitNotifications(unread: Notification[], read: Notification[], marked: Record<string, string>): [Notification[], Notification[]] {
  const now = unread.filter((n) => !n.read_at && !marked[n.id]);
  const moved = unread.filter((n) => marked[n.id] || n.read_at).map((n) => ({ ...n, read_at: n.read_at ?? marked[n.id]! }));
  const seen = new Map<string, Notification>();
  for (const n of [...moved, ...read.map((r) => (!r.read_at && marked[r.id] ? { ...r, read_at: marked[r.id]! } : r))]) if (n.read_at && !seen.has(n.id)) seen.set(n.id, n);
  return [now, [...seen.values()].sort((a, b) => b.created_at.localeCompare(a.created_at))];
}

// ⟨1.0.1⟩ Part C (C3.5): three levels only, the day a row belongs to, what asks something of the owner, and a machine-written title
// said in Persian.

/** Three levels: «فوری» (red, it rings), «تصمیم» (gold), «خبر» (silent: the hub's report, info and learning together). */
export type Level3 = 'urgent' | 'decision' | 'news';
export const LEVELS3: Level3[] = ['urgent', 'decision', 'news'];
export const level3 = (level: string): Level3 => (level === 'urgent' ? 'urgent' : level === 'decision' ? 'decision' : 'news');
export const LEVEL3_FA: Record<Level3, string> = { urgent: 'فوری', decision: 'تصمیم', news: 'خبر' };
/** The hub's levels a row of the settings stands for. */
export const LEVEL3_OF: Record<Level3, Array<'urgent' | 'decision' | 'report' | 'info' | 'learning'>> = { urgent: ['urgent'], decision: ['decision'], news: ['report', 'info', 'learning'] };

/** It wants something of the owner: urgent or a decision, not read yet and not answered. */
export const asksOwner = (n: Notification): boolean => !n.read_at && !n.answer && level3(n.level) !== 'news';

const DAY = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit' });
/** The owner's calendar day of an instant («2026-11-10»), to group rows by. */
export const dayKey = (iso: string): string => DAY.format(new Date(iso));
/** «امروز», «دیروز», else the date. */
export function dayLabel(iso: string, now = Date.now()): string {
  const k = dayKey(iso);
  if (k === DAY.format(new Date(now))) return 'امروز';
  if (k === DAY.format(new Date(now - 86_400_000))) return 'دیروز';
  return jDate(iso);
}

const FA_DIGIT = '۰۱۲۳۴۵۶۷۸۹';
const fa = (n: number | string) => String(n).replace(/\d/g, (d) => FA_DIGIT[Number(d)]!);
const WORD_N: Record<number, string> = { 1: 'یک', 2: 'دو', 3: 'سه', 4: 'چهار', 5: 'پنج' };
/**
 * A title (or a line) the machine wrote, said in Persian: «disk 90.4%» is «دیسک ۹۰٪ پر است», «down: a, b» is «دو سرویس پایین است»,
 * «company:TY» is the company's name, a bare period «(2026-10)» goes. What it does not know it leaves as it is. The raw text stays
 * one tap away (the caller shows it when this differs from it).
 */
export function humanize(text: string | null | undefined, companyName: (code: string) => string | null | undefined = () => null): string {
  if (!text) return '';
  let t = text
    .replace(/\bcompany:([A-Z][A-Z0-9]{1,9})\b/g, (_m, c: string) => companyName(c) ?? c)
    .replace(/\s*\(\d{4}-\d{2}\)/g, '')
    .replace(/\bdown:\s*([a-z0-9_.-]+(?:\s*,\s*[a-z0-9_.-]+)*)/gi, (_m, list: string) => { const n = list.split(',').length; return n === 1 ? 'یک سرویس پایین است' : `${WORD_N[n] ?? fa(n)} سرویس پایین است`; })
    .replace(/\bdisk\s+(\d+(?:\.\d+)?)\s*%/gi, (_m, p: string) => `دیسک ${fa(Math.round(Number(p)))}٪ پر است`)
    .replace(/\b(cpu|memory|ram)\s+(\d+(?:\.\d+)?)\s*%/gi, (_m, k: string, p: string) => `${/cpu/i.test(k) ? 'پردازنده' : 'حافظه'} ${fa(Math.round(Number(p)))}٪ پر است`);
  if (t !== text) t = t.replace(/\s*[—–]\s*/g, '؛ ').replace(/\s*;\s*/g, '؛ ').replace(/\s*,\s*/g, '، ').replace(/؛\s*؛/g, '؛').replace(/\s{2,}/g, ' ').trim();
  return t;
}
