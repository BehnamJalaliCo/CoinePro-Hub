'use client';

// ⟨1.14⟩ Contract §32.7: the sentences of an answer arrive as `audio` events (one file per sentence) and are played in order, the first as
// soon as it is there. `stop()` is the barge-in: what is playing stops and what is waiting is dropped. A file that cannot be played is
// skipped, so the text on screen never waits for the voice.

import { useCallback, useEffect, useRef, useState } from 'react';
import { fileUrl } from './api/v13';

export type AudioItem = { seq: number; file_id: string };

export function useAudioQueue() {
  const [playing, setPlaying] = useState(false);
  const q = useRef<AudioItem[]>([]);
  const el = useRef<HTMLAudioElement | null>(null);
  const busy = useRef(false);
  const dead = useRef(false);

  const nextRef = useRef<() => void>(() => undefined);
  const next = useCallback(() => {
    if (dead.current) return;
    const item = q.current.shift();
    if (!item) { busy.current = false; setPlaying(false); return; }
    busy.current = true;
    setPlaying(true);
    const a = new Audio(fileUrl(item.file_id));
    el.current = a;
    const again = () => { if (el.current === a) { el.current = null; nextRef.current(); } };
    a.onended = again;
    a.onerror = again;
    a.play().catch(again);
  }, []);
  useEffect(() => { nextRef.current = next; }, [next]);

  const push = useCallback((item: AudioItem) => {
    dead.current = false;
    const at = q.current.findIndex((x) => x.seq > item.seq);
    if (at < 0) q.current.push(item); else q.current.splice(at, 0, item);
    if (!busy.current) next();
  }, [next]);

  /** Barge-in: stop what is playing and forget what is waiting. */
  const stop = useCallback(() => {
    q.current = [];
    const a = el.current;
    el.current = null;
    if (a) { a.onended = null; a.onerror = null; a.pause(); }
    busy.current = false;
    setPlaying(false);
  }, []);

  useEffect(() => () => { dead.current = true; const a = el.current; if (a) { a.onended = null; a.onerror = null; a.pause(); } }, []);
  return { playing, push, stop };
}
