// Alerts (0.6.0 on the web; the Android app's core/link/Alerts.kt): which events become an alert, and the alert each one becomes. While a
// tab of the panel is on screen an alert is a toast with a way in; when the tab is in the background it is a browser notification (the
// service worker shows the hub's Web Push ones when no tab is open at all, under the same tag, so nothing is told twice).

import { groupKey, categoryOf as notificationCategory } from './notify';
import { linkRoute } from './refs';
import { agentTitleOf, noticeHeadline, noticeText, type OrderNotice } from './orders';
import type { Notification } from './api/v21';

export type Channel = 'urgent' | 'cartable' | 'orders' | 'outputs';
export type Alert = {
  channel: Channel;
  /** The browser notification's tag: the same subject again replaces it, and a card decided elsewhere takes it away. */
  key: string;
  title: string;
  text: string;
  route: string | null;
  tone: 'ok' | 'info' | 'error';
  /** The toast's button. */
  action: string;
  /** The hub's notification it came from: reading it in the panel takes the alert away. */
  notificationId?: string;
  count?: number;
};

/** Levels that reach the browser: urgent, the owner's cards (`decision`) and reports. `info` and `learning` stay in the panel. */
export const LEVELS = new Set(['urgent', 'decision', 'report']);
export const channelOf = (level: string): Channel => (level === 'urgent' ? 'urgent' : level === 'decision' ? 'cartable' : 'outputs');

/** The tag of a notification's alert: a card by its ref, an output by its ref, anything else by what makes it the same alert (public/sw.js tagOf). */
export function keyOf(n: Notification): string {
  const ref = n.link?.ref?.trim();
  if (n.link?.kind === 'decision' && ref) return `decision:${ref}`;
  if (n.link?.kind === 'deliverable' && ref) return `deliverable:${ref}`;
  return `n:${groupKey(n)}`;
}

const short = (s: string, max: number) => { const t = s.trim().replace(/\s+/g, ' '); return t.length <= max ? t : `${t.slice(0, max - 1).trimEnd()}…`; };
/** Figures written Persian: the system's own font draws the notifications, not the panel's. */
export const faDigits = (s: string) => s.replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)]!);

export function ofNotification(n: Notification, count = 1): Alert {
  const channel = channelOf(n.level);
  const body = n.body_fa.split('\n').find((l) => l.trim())?.trim() ?? '';
  const text = [count > 1 ? `${faDigits(String(count))} بار` : null, body || notificationCategory(n)].filter(Boolean).join(' · ');
  return {
    channel, key: keyOf(n), title: short(n.title_fa, 90), text: short(text, 160), route: linkRoute(n.link?.kind, n.link?.ref) ?? '/notifications',
    tone: channel === 'urgent' ? 'error' : 'info', action: 'باز کن', notificationId: n.id, count,
  };
}

/** When the hub could not be read: an urgent notification still reaches the owner, in general words. */
export function ofUnreadable(id: string, level: string, kind?: string | null, ref?: string | null): Alert | null {
  if (level !== 'urgent') return null;
  return { channel: 'urgent', key: `n:${id}`, title: 'اعلان فوری تازه از ستاد', text: 'برای دیدن جزئیات، پنل را باز کن.', route: linkRoute(kind, ref) ?? '/notifications', tone: 'error', action: 'باز کن', notificationId: id };
}

/** A kill switch moved; the owner's own move is not told back to them. */
export function ofSwitch(scope: string, engaged: boolean, by: string | null): Alert | null {
  if (!by || by === 'owner') return null;
  const holding = scope === 'holding';
  const code = scope.replace('company:', '');
  const who = agentTitleOf(by) ?? (by.includes('OVR') || by.includes('OVERSEER') ? 'ناظر کل' : by);
  const title = holding ? (engaged ? 'کل هلدینگ متوقف شد' : 'هلدینگ دوباره راه افتاد') : engaged ? `شرکت ${code} متوقف شد` : `شرکت ${code} دوباره راه افتاد`;
  const text = engaged ? `کلید توقف را ${who} زد؛ کارها ایستاد تا تو یا او ادامه بدهید.` : `کلید توقف را ${who} برداشت.`;
  return { channel: 'urgent', key: `control:${scope}`, title, text, route: holding ? '/control' : `/companies/${code}`, tone: engaged ? 'error' : 'info', action: 'باز کن' };
}

export function ofOutput(o: { ref: string; title: string; report: boolean }): Alert {
  return { channel: 'outputs', key: `deliverable:${o.ref}`, title: o.report ? 'گزارش تازه' : 'خروجی تازه', text: short(o.title, 120), route: `/outputs?ref=${o.ref}`, tone: 'ok', action: 'بخوان' };
}

export function ofOrder(n: OrderNotice): Alert {
  return {
    channel: 'orders', key: `order:${n.ref}`, title: noticeHeadline(n), text: noticeText(n),
    route: n.kind === 'delivered' && n.deliverable ? `/outputs?ref=${n.deliverable}` : `/work/${n.workId ?? n.ref}`,
    tone: n.kind === 'failed' ? 'error' : n.kind === 'delegated' ? 'info' : 'ok', action: n.kind === 'delivered' && n.deliverable ? 'خروجی' : 'باز کن',
  };
}

// --------------------------------------------------------------------------------------------- the owner's choice --
const PREF = 'hq.alerts';
/** Whether the owner wants browser notifications from this browser (on once permitted, unless switched off here). */
export function alertsWanted(): boolean {
  try { return localStorage.getItem(PREF) !== 'off'; } catch { return true; }
}
export function setAlertsWanted(on: boolean) {
  try { localStorage.setItem(PREF, on ? 'on' : 'off'); } catch { /* private mode */ }
}
export const notificationsSupported = () => typeof window !== 'undefined' && 'Notification' in window;
export const permission = (): NotificationPermission | 'unsupported' => (notificationsSupported() ? Notification.permission : 'unsupported');

/** The service worker's registration (it shows the panel's notifications, the only way on Android browsers, and the hub's pushes). */
export async function registration(): Promise<ServiceWorkerRegistration | null> {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return null;
  try { return (await navigator.serviceWorker.getRegistration('/')) ?? (await navigator.serviceWorker.register('/sw.js', { scope: '/' })); } catch { return null; }
}

const CHANNEL_FA: Record<Channel, string> = { urgent: 'فوری', cartable: 'کارتابل', orders: 'فرمان‌های تو', outputs: 'خروجی‌ها' };
/**
 * Shows [a] as a browser notification; false when the browser does not allow it. As the Android app since 0.6.0 and the service worker:
 * the screen may be locked, so the notification names only where it belongs, never what it says (a click opens it in the panel; on screen
 * the panel's own toast shows it whole).
 */
export async function showSystem(a: Alert): Promise<boolean> {
  if (permission() !== 'granted' || !alertsWanted()) return false;
  const options: NotificationOptions & { renotify?: boolean; requireInteraction?: boolean } = {
    body: CHANNEL_FA[a.channel], tag: a.key, lang: 'fa', dir: 'rtl', icon: '/icon.svg', badge: '/icon.svg', silent: a.channel === 'outputs',
    requireInteraction: a.channel === 'urgent', data: { url: a.route ?? '/notifications', nid: a.notificationId ?? null },
  };
  const reg = await registration();
  try {
    const title = a.channel === 'urgent' ? 'پیام فوری از ستاد' : 'پیام تازه از ستاد';
    if (reg) await reg.showNotification(title, options);
    else new Notification(title, options);
    return true;
  } catch { return false; }
}

/** Takes the browser's notifications for [tags] (or for hub notifications [ids], read in the panel) away. */
export async function closeSystem(f: { tags?: string[]; ids?: string[] }) {
  const reg = await registration();
  if (!reg) return;
  const list = await reg.getNotifications().catch(() => [] as globalThis.Notification[]);
  for (const n of list) if (f.tags?.includes(n.tag) || (f.ids && f.ids.includes((n.data as { nid?: string } | null)?.nid ?? ''))) n.close();
}

/** base64url → the bytes `PushManager.subscribe` takes as its server key. */
export function keyBytes(b64: string): Uint8Array<ArrayBuffer> {
  const pad = '='.repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}
