/* CoinePro HQ — the panel's service worker (0.6.0 on the web). It only shows the hub's Web Push alerts (contract §6: VAPID; the hub sends
 * {title, level, count, company?, link_kind?, link_ref?, sound?} and nothing else) and opens the right page on a click. While a tab of the
 * panel is on screen it shows nothing: the page tells it itself (a toast), so an alert is never told twice. A tab in the background tells
 * the same alert under the same tag, so the browser keeps one notification, not two. No caching, no fetch handler. */

const LEVEL_FA = { urgent: 'فوری', decision: 'منتظر تو', report: 'گزارش', info: 'اطلاع', learning: 'یادگیری' };
const KIND_FA = {
  employee: 'کارمند', substitute: 'بازیکن ذخیره', academy: 'آکادمی', audit: 'دفتر Audit', device: 'دستگاه', support_queue: 'پشتیبانی',
  archive_fixity: 'سلامت بایگانی', provision_run: 'تأسیس', server_plan: 'تأسیس',
  decision: 'تصمیم', deliverable: 'خروجی', work: 'کار', thread: 'پیام', message: 'یادداشت مشاور', finding: 'یافته‌ی ناظر', hold: 'نگه‌داشت ناظر',
  challenge: 'چالش ناظر', inquiry: 'استعلام', meeting: 'جلسه', founding: 'تأسیس', code_session: 'کارگاه کد', archive_record: 'بایگانی',
  support_conversation: 'پشتیبانی', revenue_alert: 'درآمد', treasury: 'خزانه', backup: 'پشتیبان‌گیری', server: 'سرور',
};

/** Where a link opens: the same place as the notification inside the panel (lib/refs.ts linkRoute), for every kind a push carries. */
function route(kind, ref) {
  const r = ref || '';
  switch (kind) {
    case 'decision': return r ? `/cartable?ref=${encodeURIComponent(r)}` : '/cartable';
    case 'deliverable': return r ? `/outputs?ref=${encodeURIComponent(r)}` : '/outputs';
    case 'work': return /^W-\d+$/.test(r) || /^[0-9a-f-]{36}$/i.test(r) ? `/work/${r}` : '/orders';
    case 'meeting': return r ? `/meetings/${encodeURIComponent(r)}` : '/meetings';
    case 'thread': return r ? `/messages?thread=${encodeURIComponent(r)}` : '/messages';
    case 'message': case 'inquiry': return '/advisor';
    case 'finding': case 'hold': case 'challenge': return '/oversight';
    case 'founding': case 'provision_run': return /^C-\d+$/.test(r) ? `/founding/${r}` : '/founding';
    case 'server_plan': return '/founding';
    case 'code_session': return /^S-\d+$/.test(r) ? `/workshop/${r}` : '/workshop';
    case 'support_conversation': return /^SC-\d+$/.test(r) ? `/support/${r}` : '/support';
    case 'support_queue': return '/support';
    case 'archive_record': return /^AR-\d+$/.test(r) ? `/archive/${r}` : '/archive';
    case 'archive_fixity': return '/archive';
    case 'revenue_alert': return '/revenue';
    case 'substitute': return '/substitutes';
    case 'employee': return /^[A-Z][A-Z0-9-]+$/.test(r) ? `/employees/${r}` : '/notifications';
    case 'academy': return '/academy';
    case 'backup': return '/control';
    case 'audit': return '/audit';
    case 'device': return '/settings';
    case 'server': return r ? `/servers/${encodeURIComponent(r)}` : '/servers';
    case 'treasury': return '/treasury';
    default: return '/notifications';
  }
}

/** The same tag the page uses for the same alert (lib/alerts.ts keyOf): a card or an output by its ref, anything else by what makes it the same alert. */
function tagOf(d) {
  if (d.link_kind === 'decision' && d.link_ref) return `decision:${d.link_ref}`;
  if (d.link_kind === 'deliverable' && d.link_ref) return `deliverable:${d.link_ref}`;
  const norm = String(d.title || '').trim().replace(/\s+/g, ' ').replace(/[0-9۰-۹٠-٩]+(?:[.,٫/][0-9۰-۹٠-٩]+)*/g, '#');
  return `n:${[d.company || '', d.level || '', d.link_kind || '', norm].join('|')}`;
}

const fa = (s) => String(s).replace(/[0-9]/g, (c) => '۰۱۲۳۴۵۶۷۸۹'[Number(c)]);

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('push', (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = {}; }
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    if (wins.some((w) => w.visibilityState === 'visible')) return;
    const count = Number(d.count || 1);
    const what = KIND_FA[d.link_kind] || LEVEL_FA[d.level] || 'ستاد';
    // As the Android app since 0.6.0: the screen may be locked and seen by anyone, so the alert names only its kind and level; what it says
    // is read in the panel (a click opens it). The web cannot tell a locked screen apart, so it is the same everywhere.
    await self.registration.showNotification(d.level === 'urgent' ? 'پیام فوری از ستاد' : 'پیام تازه از ستاد', {
      body: count > 1 ? `${fa(count)} بار · ${what}` : what,
      tag: tagOf(d),
      icon: '/icon.svg',
      badge: '/icon.svg',
      lang: 'fa',
      dir: 'rtl',
      silent: d.level !== 'urgent' && d.sound !== '1',
      requireInteraction: d.level === 'urgent',
      data: { url: route(d.link_kind, d.link_ref) },
    });
  })());
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || '/', self.location.origin).href;
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const w = wins.find((x) => new URL(x.url).origin === self.location.origin);
    if (w) { await w.focus(); if ('navigate' in w) await w.navigate(url).catch(() => w.postMessage({ type: 'hq.open', url })); return; }
    await self.clients.openWindow(url);
  })());
});
