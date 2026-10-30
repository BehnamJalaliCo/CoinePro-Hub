// Notifications as the owner reads them (0.5.0; contract §6): the same alert raised again and again (the overseer's hourly finding) is one
// row with its count, what a notification is about comes from its link (a finding is not a decision, even when the hub raises it at the
// `decision` level), and marking read moves it out of the main list. The Android app's core/data/Notifications.kt, rule for rule.

import { ago } from './format';
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
