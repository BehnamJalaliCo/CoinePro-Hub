'use client';

// ⟨1.14⟩ Contract §32.7 hands-free: one tap and the app listens; a turn ends after [silenceMs] of silence (TALK_SILENCE_MS, default 1 200)
// and listening goes on for the next one. The phone's own recogniser does it. The first words of a new utterance are the barge-in
// ([onSpeech]): the caller stops the playback and the generation. Stops by itself on a fatal error (no permission, no network).

import { useEffect, useRef } from 'react';
import { recognizer } from './long-voice';

export const SILENCE_MS = 1_200;
const FATAL = new Set(['not-allowed', 'service-not-allowed', 'audio-capture', 'language-not-supported']);

export function useHandsFree({ enabled, silenceMs = SILENCE_MS, onSpeech, onUtterance, onFatal }: {
  enabled: boolean; silenceMs?: number; onSpeech: () => void; onUtterance: (text: string) => void; onFatal: (why: string) => void;
}) {
  const cb = useRef({ onSpeech, onUtterance, onFatal });
  useEffect(() => { cb.current = { onSpeech, onUtterance, onFatal }; });

  useEffect(() => {
    const Ctor = recognizer();
    if (!enabled || !Ctor) return;
    let alive = true;
    let text = '';
    let seen = 0; // results of earlier utterances in this session: a continuous recogniser keeps them
    let total = 0;
    let speaking = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const rec = new Ctor();
    rec.lang = 'fa-IR'; rec.continuous = true; rec.interimResults = true; rec.maxAlternatives = 1;
    const flush = () => {
      timer = undefined;
      const t = text.trim();
      text = ''; speaking = false; seen = total;
      if (t) cb.current.onUtterance(t);
    };
    rec.onresult = (e) => {
      total = e.results.length;
      let s = '';
      for (let i = seen; i < total; i++) s += `${e.results[i]?.[0]?.transcript ?? ''} `;
      text = s;
      if (!s.trim()) return;
      if (!speaking) { speaking = true; cb.current.onSpeech(); }
      clearTimeout(timer);
      timer = setTimeout(flush, silenceMs);
    };
    rec.onerror = (e) => { if (FATAL.has(e.error)) { alive = false; cb.current.onFatal(e.error); } };
    rec.onend = () => { seen = 0; total = 0; if (alive) setTimeout(() => { if (alive) { try { rec.start(); } catch { /* already running */ } } }, 250); };
    try { rec.start(); } catch { cb.current.onFatal('start'); }
    return () => { alive = false; clearTimeout(timer); rec.onresult = null; rec.onerror = null; rec.onend = null; try { rec.abort(); } catch { /* not started */ } };
  }, [enabled, silenceMs]);
}
