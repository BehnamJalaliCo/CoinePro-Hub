'use client';

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { nextPulses, type Pulse } from './control';
import type { StreamEvent } from './stream';

// What the holding's agents are doing, per company, from the live stream (0.3.0; the Android app's LiveActivity): the companies list, the
// control room and the activity rings read it. Fed by the shell's stream (newest first); each event is taken once.

const Ctx = createContext<Record<string, Pulse>>({});

export function PulsesProvider({ feed, children }: { feed: StreamEvent[]; children: ReactNode }) {
  const [pulses, setPulses] = useState<Record<string, Pulse>>({});
  const seen = useRef(new Set<string>());
  useEffect(() => {
    const fresh = feed.filter((e) => !seen.current.has(e.id)).reverse();
    if (!fresh.length) return;
    for (const e of fresh) seen.current.add(e.id);
    if (seen.current.size > 2000) seen.current = new Set([...seen.current].slice(-500));
    setPulses((p) => fresh.reduce((acc, e) => nextPulses(acc, e), p));
  }, [feed]);
  return <Ctx.Provider value={pulses}>{children}</Ctx.Provider>;
}

export const usePulses = () => useContext(Ctx);
