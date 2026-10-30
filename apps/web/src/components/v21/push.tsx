'use client';

import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, Pill, SectionTitle, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError, isMock } from '@/lib/api/client';
import { call } from '@/lib/api/v13';
import { revokePush, subscribePush, useOwnerOrders, vapidKey, type Notification, type Output } from '@/lib/api/v21';
import { forgetRequest } from '@/lib/api/observe';
import {
  LEVELS, alertsWanted, closeSystem, keyBytes, notificationsSupported, ofNotification, ofOrder, ofOutput, ofSwitch, ofUnreadable, permission, registration,
  setAlertsWanted, showSystem, type Alert,
} from '@/lib/alerts';
import { deviceName } from '@/lib/auth';
import { alreadyReached, noticeOf, type OrderBrief } from '@/lib/orders';
import type { StreamEvent } from '@/lib/stream';

// Alerts on the web (0.6.0; the Android app's AlertCenter): the stream's events and the order tracker's notices become alerts, one at a time
// in order. Before an alert is raised the hub is asked what it is (the events carry metadata only) and whether it still stands: a
// notification already read (here, on the phone), a card already decided, an output already seen, is not raised. Who speaks: while the
// tab is on screen, the panel does, with a toast; otherwise the browser's notifications do. Never both. Outputs make no toast: the badge shows
// them. Each event is handled once (its id is kept), so a reconnect's replay repeats nothing.

const TOLD = 'hq.alerts.told';
const KNOWN = 'hq.alerts.orders';
const read = (k: string): string[] => { try { return JSON.parse(localStorage.getItem(k) ?? '[]') as string[]; } catch { return []; } };
const write = (k: string, v: string[]) => { try { localStorage.setItem(k, JSON.stringify(v.slice(-600))); } catch { /* private mode */ } };
const str = (v: unknown) => (typeof v === 'string' && v ? v : null);
const visible = () => document.visibilityState === 'visible';

export function AlertCenter({ feed }: { feed: StreamEvent[] }) {
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const orders = useOwnerOrders();
  const told = useRef<Set<string>>(new Set());
  const known = useRef<Map<string, OrderBrief>>(new Map());
  const seen = useRef<Set<string>>(new Set());
  const counts = useRef<Map<string, number>>(new Map());
  const switches = useRef<Map<string, number>>(new Map());
  const queue = useRef<Promise<void>>(Promise.resolve());
  const started = useRef(false);

  const deliver = useCallback(async (a: Alert) => {
    if (visible()) {
      if (a.channel === 'outputs') return;
      toast({ tone: a.tone, text: a.channel === 'orders' ? a.text : `${a.title}؛ ${a.text}`, action: a.route ? { label: a.action, run: () => router.push(a.route!) } : undefined });
      return;
    }
    await showSystem(a);
  }, [router, toast]);

  // The orders the owner gave: what each has already reached is told already (opening the panel never repeats it); an order this browser
  // knew before and that moved on meanwhile is told now, the newest three at most (a long absence is not a flood).
  useEffect(() => {
    if (!orders.data) return;
    if (!started.current) { started.current = true; for (const k of read(TOLD)) told.current.add(k); }
    const before = new Set(read(KNOWN));
    const missed: Array<{ ref: string; key: string; updated: string }> = [];
    for (const w of orders.data) {
      if (known.current.has(w.ref)) continue;
      for (const k of alreadyReached(w)) {
        if (told.current.has(k)) continue;
        told.current.add(k);
        if (before.has(w.ref)) missed.push({ ref: w.ref, key: k, updated: w.updated_at });
      }
    }
    known.current = new Map(orders.data.map((w) => [w.ref, { id: w.id, ref: w.ref, title: w.title, company: w.company }]));
    write(KNOWN, [...before, ...orders.data.map((w) => w.ref)].filter((x, i, a) => a.indexOf(x) === i));
    write(TOLD, [...told.current]);
    const last = new Map<string, (typeof missed)[number]>();
    for (const m of missed) last.set(m.ref, m);
    for (const m of [...last.values()].sort((a, b) => b.updated.localeCompare(a.updated)).slice(0, 3)) {
      const o = known.current.get(m.ref)!;
      void deliver(ofOrder({ kind: m.key.split(':').pop() as 'delivered', ref: o.ref, title: o.title, company: o.company, workId: o.id }));
    }
  }, [orders.data, deliver]);

  const handle = useCallback(async (e: StreamEvent) => {
    if (e.type === 'work.created') { void qc.invalidateQueries({ queryKey: ['work', 'orders'] }); return; }
    const n = noticeOf(e, known.current, told.current);
    if (n) { write(TOLD, [...told.current]); await deliver(ofOrder(n)); return; }
    if (e.type === 'decision.decided' && e.ref) { await closeSystem({ tags: [`decision:${e.ref}`] }); counts.current.delete(`decision:${e.ref}`); return; }
    if (e.type === 'control.changed') {
      const k = str(e.data.kill_switch) ?? (['engaged', 'released'].includes(str(e.data.state) ?? '') ? str(e.data.state) : null);
      if (!k) return;
      const scope = str(e.data.scope) ?? e.ref ?? 'holding';
      const key = `${scope}:${k}`;
      if (Date.now() - (switches.current.get(key) ?? 0) < 10 * 60_000) return;
      const a = ofSwitch(scope, k === 'engaged', str(e.data.by));
      if (a) { switches.current.set(key, Date.now()); await deliver(a); }
      return;
    }
    if (e.type === 'deliverable.created' && e.ref) {
      const root = str(e.data.root_ref);
      const work = str(e.data.work);
      // An order's output is told as the order's delivery.
      if ((root && known.current.has(root)) || (work && known.current.has(work)) || visible()) return;
      const o = await call<Output>('GET', `/deliverables/${encodeURIComponent(e.ref)}`).catch(() => null);
      if (!o || o.seen_at) return;
      await deliver(ofOutput({ ref: o.ref, title: o.title, report: o.producer.code.endsWith('-SYS') }));
      return;
    }
    if (e.type === 'notification.created') {
      const level = str(e.data.level);
      const id = e.ref ?? str(e.data.id);
      if (!level || !LEVELS.has(level) || !id) return;
      let list: Notification[] | null = null;
      try { list = (await call<{ items: Notification[] }>('GET', '/notifications?unread=true&limit=30')).items; } catch { list = null; }
      if (!list) { const a = ofUnreadable(id, level, str(e.data.link_kind), str(e.data.link_ref)); if (a) await deliver(a); return; }
      const hit = list.find((x) => x.id === id);
      if (!hit || hit.read_at) return;
      if (hit.link?.kind === 'decision' && hit.link.ref) {
        const d = await call<{ status: string }>('GET', `/decisions/${encodeURIComponent(hit.link.ref)}`).catch(() => null);
        if (d && d.status !== 'pending') return;
      }
      const base = ofNotification(hit);
      const count = (counts.current.get(base.key) ?? 0) + 1;
      counts.current.set(base.key, count);
      await deliver(count > 1 ? ofNotification(hit, count) : base);
    }
  }, [deliver, qc]);

  useEffect(() => {
    const fresh = feed.filter((e) => !seen.current.has(e.id)).reverse();
    for (const e of fresh) {
      seen.current.add(e.id);
      queue.current = queue.current.then(() => handle(e)).catch(() => undefined);
    }
    if (seen.current.size > 3000) seen.current = new Set([...seen.current].slice(-1000));
  }, [feed, handle]);

  // The service worker: registered once (it shows the hub's pushes when no tab is open); a click on a notification it could not open in
  // place arrives here.
  useEffect(() => {
    void registration();
    if (!('serviceWorker' in navigator)) return;
    const on = (m: MessageEvent) => { const d = m.data as { type?: string; url?: string } | null; if (d?.type === 'hq.open' && d.url) router.push(new URL(d.url).pathname + new URL(d.url).search); };
    navigator.serviceWorker.addEventListener('message', on);
    return () => navigator.serviceWorker.removeEventListener('message', on);
  }, [router]);
  return null;
}

// ------------------------------------------------------------------------------------------------- the subscription --
const SUB = 'hq.push.sub';
type PushState = { permission: NotificationPermission | 'unsupported'; wanted: boolean; push: 'on' | 'off' | 'unavailable' | 'unknown' };

async function probe(): Promise<PushState> {
  const reg = await registration();
  const sub = await reg?.pushManager?.getSubscription().catch(() => null);
  let stored: string | null = null;
  try { stored = localStorage.getItem(SUB); } catch { /* ignore */ }
  return { permission: permission(), wanted: alertsWanted(), push: !reg?.pushManager || isMock ? 'unavailable' : sub && stored ? 'on' : 'off' };
}

/** This browser's notifications: the permission, the owner's switch, and the hub's Web Push subscription (`POST /push/web-subscriptions`). */
export function useBrowserAlerts() {
  const toast = useToast();
  const [s, setS] = useState<PushState>({ permission: 'default', wanted: true, push: 'unknown' });
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(() => probe().then(setS), []);
  useEffect(() => {
    let off = false;
    void probe().then((x) => { if (!off) setS(x); });
    return () => { off = true; };
  }, []);

  /** Asks the browser, then subscribes to the hub's pushes (when the hub has a VAPID key; without one, alerts come while a tab is open). */
  const enable = useCallback(async () => {
    if (!notificationsSupported()) { toast({ tone: 'error', text: 'این مرورگر اعلان ندارد.' }); return; }
    setBusy(true);
    try {
      const p = await Notification.requestPermission();
      setAlertsWanted(true);
      if (p !== 'granted') { toast({ tone: 'info', text: 'مرورگر اجازه‌ی اعلان نداد؛ از تنظیمات سایت در مرورگر روشنش کن.' }); return; }
      const reg = await registration();
      let push: PushState['push'] = 'unavailable';
      if (reg?.pushManager && !isMock) {
        try {
          const { public_key } = await vapidKey();
          const sub = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(public_key) }));
          const j = sub.toJSON() as { endpoint: string; keys: { p256dh: string; auth: string } };
          const dev = await subscribePush({ endpoint: j.endpoint, keys: j.keys, device_name: deviceName() });
          try { localStorage.setItem(SUB, dev.id); } catch { /* ignore */ }
          push = 'on';
        } catch (e) {
          // 503 channel_not_configured: the hub has no VAPID key yet; the alerts still come while a tab is open.
          if (e instanceof ApiError) forgetRequest(e.requestId);
          push = 'unavailable';
        }
      }
      setS({ permission: 'granted', wanted: true, push });
      toast({ tone: 'ok', text: push === 'on' ? 'اعلان مرورگر روشن شد؛ حتی با پنل بسته میرسد.' : 'اعلان مرورگر روشن شد؛ تا هاب Web Push را راه بیندازد، وقتی زبانه‌ای از پنل باز است میرسد.' });
    } finally { setBusy(false); }
  }, [toast]);

  const disable = useCallback(async () => {
    setBusy(true);
    try {
      setAlertsWanted(false);
      const reg = await registration();
      const sub = await reg?.pushManager?.getSubscription().catch(() => null);
      await sub?.unsubscribe().catch(() => false);
      let id: string | null = null;
      try { id = localStorage.getItem(SUB); localStorage.removeItem(SUB); } catch { /* ignore */ }
      if (id) await revokePush(id).catch(() => undefined);
      setS((x) => ({ ...x, wanted: false, push: x.push === 'unavailable' ? 'unavailable' : 'off' }));
      toast({ tone: 'info', text: 'اعلان مرورگر در این مرورگر خاموش شد.' });
    } finally { setBusy(false); }
  }, [toast]);

  const test = useCallback(async () => {
    const ok = await showSystem({ channel: 'cartable', key: 'test', title: 'آزمایش اعلان ستاد', text: 'اعلان‌های این مرورگر کار میکنند.', route: '/settings', tone: 'info', action: 'باز کن' });
    if (!ok) toast({ tone: 'error', text: 'مرورگر اعلان را نشان نداد؛ اجازه را در تنظیمات سایت ببین.' });
  }, [toast]);
  return { ...s, busy, on: s.permission === 'granted' && s.wanted, enable, disable, test, refresh };
}

/** On «فرمان‌های من»: until the owner allows it, the orders' changes are told in the panel only. */
export function BrowserNotifyCard() {
  const b = useBrowserAlerts();
  if (b.on || b.permission === 'unsupported') return null;
  return (
    <Card className="flex flex-wrap items-center gap-3 bg-lapis-soft p-4">
      <span className="text-lapis"><Icon name="bell" size={20} /></span>
      <span className="flex min-w-0 flex-[1_1_16rem] flex-col gap-0.5">
        <span className="text-[13px] font-semibold">اعلان فرمان‌ها روی مرورگر خاموش است</span>
        <span className="text-[12px] text-sec">واگذاری، تحویل، شکست یا پایان هر فرمان، وقتی زبانه‌ی پنل پشت کارهای دیگر است، در اعلان‌های مرورگر گفته میشود.</span>
      </span>
      <Button size="sm" loading={b.busy} onClick={b.enable}>{b.permission === 'denied' ? 'راهنما' : 'روشن کن'}</Button>
    </Card>
  );
}

/** Settings: the browser's notifications — the switch, what comes, the connection to the hub's push, and a test. */
export function BrowserNotificationsCard() {
  const b = useBrowserAlerts();
  return (
    <Card className="flex flex-col gap-4 p-5">
      <SectionTitle title="اعلان مرورگر" note="آنچه این‌جا یا در اپ خوانده‌ای دوباره اعلان نمیشود." />
      <div className="flex items-center gap-3">
        <span className="flex-1 text-[14px]">{b.on ? 'روشن' : b.permission === 'denied' ? 'مرورگر اجازه نداده' : 'خاموش'}</span>
        <Switch label="اعلان مرورگر" checked={b.on} disabled={b.busy || b.permission === 'unsupported'} onChange={(v) => void (v ? b.enable() : b.disable())} />
      </div>
      <ul className="flex flex-col gap-1.5 text-[13px] text-sec">
        <li className="flex items-center gap-2"><span className="text-neg"><Icon name="urgent" size={15} /></span>هشدار فوری، با صدا</li>
        <li className="flex items-center gap-2"><span className="text-gold-ink"><Icon name="cartable" size={15} /></span>کارت منتظر مُهر تو</li>
        <li className="flex items-center gap-2"><span className="text-lapis"><Icon name="command" size={15} /></span>تحویل یا پایان فرمان</li>
        <li className="flex items-center gap-2"><span className="text-silver-ink"><Icon name="deliverable" size={15} /></span>خروجی تازه (بی‌صدا)</li>
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[12px] text-muted">اتصال به هاب:</span>
        {b.push === 'on' ? <Pill tone="pos" dot>Web Push وصل؛ با پنل بسته هم میرسد</Pill>
          : b.push === 'unavailable' ? <Pill tone="neutral" dot>فقط وقتی زبانه‌ای از پنل باز است</Pill>
          : <Pill tone="neutral" dot>وصل نیست</Pill>}
      </div>
      {b.permission === 'denied' ? <p className="rounded-[10px] bg-warn-soft p-3 text-[12px] leading-6 text-ink">مرورگر اعلان این سایت را بسته است؛ از نماد قفل کنار نشانی، «اعلان‌ها» را روی «اجازه» بگذار و صفحه را دوباره باز کن.</p> : null}
      {b.on ? <Button variant="secondary" size="sm" icon="bell" className="self-start" onClick={b.test}>اعلان آزمایشی</Button> : null}
    </Card>
  );
}
