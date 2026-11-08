'use client';

// ⟨1.24⟩ NO-1 «رسیدن کار فوری و تصمیم» (design/LIVE_VIEWS.md §4 P): what needs the owner, while a tab is on screen. 🔴 urgent: one banner
// that settles from the top and stays until he says «دیدم», with one low bell (the only sound the panel makes for traffic: never). 🟡 a card
// for his seal: a toast with a gold hairline, and the cartable's badge. Everything else goes quietly to the list. The alerts themselves
// are made by components/v21/push.tsx (AlertCenter): it hands the urgent and the cards here instead of to the plain toast.

import { useSyncExternalStore } from 'react';
import type { Alert } from '@/lib/alerts';

type State = { urgent: Alert | null; decisions: Array<Alert & { id: number }> };
let state: State = { urgent: null, decisions: [] };
const subs = new Set<() => void>();
const set = (s: State) => { state = s; for (const l of subs) l(); };
let n = 0;

/** The single low bell (rule 6): a soft 110 Hz tone that fades in 0.9 s. Silent where the browser does not allow sound yet. */
function bell() {
  try {
    const AC = (window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext }).AudioContext
      ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = 'sine';
    o.frequency.value = 110;
    g.gain.setValueAtTime(0.0001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.9);
    o.connect(g).connect(ctx.destination);
    o.start();
    o.stop(ctx.currentTime + 0.95);
    o.onended = () => void ctx.close();
  } catch { /* no sound: the banner still says it */ }
}

export const attention = {
  /** 🔴: the banner (the newest replaces an older one, which is still in the list), and the bell once. */
  urgent(a: Alert) {
    const same = state.urgent?.key === a.key;
    set({ ...state, urgent: a });
    if (!same) bell();
  },
  /** 🟡: a toast with the gold hairline for six seconds. */
  decision(a: Alert) {
    const id = ++n;
    set({ ...state, decisions: [...state.decisions.filter((d) => d.key !== a.key).slice(-1), { ...a, id }] });
    setTimeout(() => attention.dropDecision(id), 6000);
  },
  dropDecision(id: number) { if (state.decisions.some((d) => d.id === id)) set({ ...state, decisions: state.decisions.filter((d) => d.id !== id) }); },
  /** «دیدم». */
  ack() { if (state.urgent) set({ ...state, urgent: null }); },
  /** A card decided elsewhere or a notification read elsewhere takes its alert away. */
  forget(key: string) {
    if (state.urgent?.key === key || state.decisions.some((d) => d.key === key)) set({ urgent: state.urgent?.key === key ? null : state.urgent, decisions: state.decisions.filter((d) => d.key !== key) });
  },
};

const subscribe = (l: () => void) => { subs.add(l); return () => { subs.delete(l); }; };
export const useAttention = () => useSyncExternalStore(subscribe, () => state, () => state);
