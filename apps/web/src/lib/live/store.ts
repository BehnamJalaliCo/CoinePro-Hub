'use client';

// ⟨1.24⟩ K-2, the live store (design/LIVE_VIEWS.md §2.1, contract §42): one per tab. Seeded from `GET /live/summary`, then every stream
// event after the seed's sequence goes through the reducers of lib/live/model.ts. A burst limiter applies what arrived at most every
// 120 ms and tells the views once; the motion of those events (the map's particles) is handed on only while the tab is on screen and the
// stream is live. A hidden tab, or a reconnect that delivers what was missed, applies the state at once without motion; past 20 such
// events a chip says «n رویداد در نبودت» instead of replaying them (rule 7).

import { useEffect, useRef, useSyncExternalStore } from 'react';
import type { StreamEvent, StreamState } from '@/lib/stream';
import type { LiveSummary } from '@/lib/api/v42';
import { EMPTY, effectsOf, reduce, seedPeople, seedSessions, seedSummary, seedTokenKinds, type Effect, type LiveState } from './model';

const FLUSH_MS = 120;
/** An event older than this when it arrives is history (a reconnect's catch-up): applied, not animated. */
const STALE_EVENT_MS = 15_000;
/** Past this many events applied without motion, the owner is told how many (rule 7). */
export const AWAY_CHIP_AT = 20;
/** No byte from the hub (not even its heartbeat) for this long: the figures are old (GL-1). */
export const STALE_MS = 45_000;

export type Beacon = 'live' | 'reconnecting' | 'stale' | 'offline';
export type StreamMeta = { state: StreamState; lastByteAt: number; downSince: number | null; beat: number; online: boolean };

type Listener = () => void;

export class LiveStore {
  private state: LiveState = EMPTY;
  private listeners = new Set<Listener>();
  private effectListeners = new Set<(fx: Effect[]) => void>();
  private queue: Array<{ e: StreamEvent; silent: boolean }> = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private quiet = 0;
  /** «n رویداد در نبودت»: set when the owner comes back to more than 20 events applied without motion. */
  private away: { n: number; at: number } | null = null;
  private metaV: StreamMeta = { state: 'connecting', lastByteAt: 0, downSince: null, beat: 0, online: true };
  private metaListeners = new Set<Listener>();
  private firstSeed: Promise<number | null>;
  private resolveSeed!: (seq: number | null) => void;
  private seeded = false;

  constructor() {
    this.firstSeed = new Promise((r) => { this.resolveSeed = r; });
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => { if (!document.hidden) this.back(); });
      window.addEventListener('online', () => this.setMeta({ online: true }));
      window.addEventListener('offline', () => this.setMeta({ online: false }));
      this.metaV.online = navigator.onLine !== false;
    }
  }

  getState = () => this.state;
  subscribe = (l: Listener) => { this.listeners.add(l); return () => { this.listeners.delete(l); }; };
  private emit() { for (const l of this.listeners) l(); }

  /** The map's motion: the effects of the events just applied, only while they can be seen. */
  onEffects(l: (fx: Effect[]) => void) { this.effectListeners.add(l); return () => { this.effectListeners.delete(l); }; }

  // ------------------------------------------------------------------------------------------------- seeds --
  /** The first seed: the stream waits for its sequence (at most a few seconds) so it resumes exactly after it. */
  whenSeeded(timeoutMs = 4000): Promise<number | null> {
    return Promise.race([this.firstSeed, new Promise<number | null>((r) => setTimeout(() => r(null), timeoutMs))]);
  }
  /** No summary to seed from (a hub before §42, or the read failed): the stream starts live. */
  noSeed() { if (!this.seeded) { this.seeded = true; this.resolveSeed(null); } }
  seed(sum: LiveSummary) {
    this.state = seedSummary(this.state, sum);
    // §42.5: `seq` is null while the hub's event bus is down; the stream then starts live, with no resume point.
    if (!this.seeded) { this.seeded = true; const q = sum.seq == null ? NaN : Number(sum.seq); this.resolveSeed(Number.isFinite(q) && q > 0 ? q : null); }
    this.emit();
  }
  seedSessions(cards: Parameters<typeof seedSessions>[1]) { const s = seedSessions(this.state, cards); if (s !== this.state) { this.state = s; this.emit(); } }
  seedPeople(list: Parameters<typeof seedPeople>[1]) { const s = seedPeople(this.state, list); if (s !== this.state) { this.state = s; this.emit(); } }
  seedTokenKinds(t: Parameters<typeof seedTokenKinds>[1]) { this.state = seedTokenKinds(this.state, t); this.emit(); }

  // ------------------------------------------------------------------------------------------------ events --
  /** One accepted stream event (the stream's door has already de-duplicated it). */
  push(e: StreamEvent) {
    const hidden = typeof document !== 'undefined' && document.hidden;
    const old = e.at ? Date.now() - Date.parse(e.at) > STALE_EVENT_MS : false;
    this.queue.push({ e, silent: hidden || old || this.metaV.state !== 'live' });
    // The burst limiter: whatever arrives within 120 ms is applied together, and the views hear once.
    if (!this.timer) this.timer = setTimeout(() => this.flush(), FLUSH_MS);
  }

  flush() {
    this.timer = null;
    const batch = this.queue.splice(0);
    if (!batch.length) return;
    let s = this.state;
    const fx: Effect[] = [];
    let silent = 0;
    for (const { e, silent: quiet } of batch) {
      if (!quiet) fx.push(...effectsOf(e, s)); else silent += 1;
      s = reduce(s, e);
    }
    this.state = s;
    this.quiet += silent;
    const visible = typeof document === 'undefined' || !document.hidden;
    if (visible && silent === 0) this.settle();
    this.emit();
    if (fx.length && visible) for (const l of this.effectListeners) l(fx);
  }

  /** Back on screen: what was applied without motion is told in one chip when it is more than 20 events. */
  private back() { this.flush(); this.settle(); }
  private settle() {
    if (this.quiet > AWAY_CHIP_AT) { this.away = { n: this.quiet, at: Date.now() }; this.emitMeta(); }
    this.quiet = 0;
  }
  /** The chip «n رویداد در نبودت» (shown for 8 s). */
  awayChip(now = Date.now()): number | null { return this.away && now - this.away.at < 8000 ? this.away.n : null; }
  dismissAway() { this.away = null; this.emitMeta(); }

  // -------------------------------------------------------------------------------------------- the stream --
  getMeta = () => this.metaV;
  subscribeMeta = (l: Listener) => { this.metaListeners.add(l); return () => { this.metaListeners.delete(l); }; };
  private emitMeta() { this.metaV = { ...this.metaV }; for (const l of this.metaListeners) l(); }
  private setMeta(p: Partial<StreamMeta>) { this.metaV = { ...this.metaV, ...p }; for (const l of this.metaListeners) l(); }

  /** A byte from the hub (an event or the 15 s heartbeat): the beacon breathes once, at most every 2 s. */
  byte(now = Date.now()) {
    const beat = now - this.metaV.beat >= 2000 ? now : this.metaV.beat;
    if (beat === this.metaV.beat && now - this.metaV.lastByteAt < 1000) { this.metaV.lastByteAt = now; return; }
    this.setMeta({ lastByteAt: now, beat });
  }
  streamState(st: StreamState, now = Date.now()) {
    if (st === this.metaV.state) return;
    const downSince = st === 'live' ? null : this.metaV.downSince ?? now;
    this.setMeta({ state: st, downSince, ...(st === 'live' ? { lastByteAt: now } : {}) });
    // Back after a drop: what the stream resumes with is history; the next flush will tell its count.
    if (st === 'live') this.settle();
  }
}

/** GL-1 «چراغ زنده»: live / reconnecting / stale (with since when) / offline (the browser has no network). */
export function beaconOf(m: StreamMeta, now = Date.now()): { state: Beacon; since: number | null } {
  if (!m.online) return { state: 'offline', since: m.downSince ?? now };
  if (m.state === 'live') return now - m.lastByteAt >= STALE_MS && m.lastByteAt > 0 ? { state: 'stale', since: m.lastByteAt } : { state: 'live', since: null };
  const since = m.downSince ?? now;
  return now - since >= STALE_MS ? { state: 'stale', since } : { state: 'reconnecting', since };
}

/** The tab's one store. */
export const liveStore = new LiveStore();

// ------------------------------------------------------------------------------------------------------ hooks --
/** A slice of the live state; [sel] must return a value or a part of the state (stable between events). */
export function useLiveState<T>(sel: (s: LiveState) => T): T {
  return useSyncExternalStore(liveStore.subscribe, () => sel(liveStore.getState()), () => sel(EMPTY));
}
export const useStreamMeta = () => useSyncExternalStore(liveStore.subscribeMeta, liveStore.getMeta, liveStore.getMeta);

/** The map's motion, as it happens. */
export function useLiveEffects(on: (fx: Effect[]) => void) {
  const cb = useRef(on);
  useEffect(() => { cb.current = on; });
  useEffect(() => liveStore.onEffects((fx) => cb.current(fx)), []);
}
