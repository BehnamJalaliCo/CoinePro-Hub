'use client';

// ⟨1.11⟩ Contract §29.5 «صدای بلند»: the owner speaks as long as he needs. The browser's own recogniser (Web Speech, fa-IR, continuous)
// writes as he speaks and is started again at every pause until he stops; the audio is recorded beside it in standalone pieces of at most
// 90 s. Past one minute, or when the recogniser fails or is missing, the pieces go to the hub's STT in order (`/transcribe/sessions`,
// up to 20 minutes) and the hub's text is the one kept; under a minute the recogniser's text is enough. Either way the whole text comes
// back to the caller to be read and corrected before anything is sent.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, isMock } from './api/client';
import { handled } from './api/observe';
import { transcribe } from './api/v13';
import { finishSttSession, openSttSession, putSttChunk, type SttPurpose } from './api/v29';

const TYPES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4;codecs=mp4a.40.2', 'audio/mp4', 'audio/webm'];
const BARS = 40;

type Limits = { minute: number; chunk: number; max: number };
const LIMITS: Limits = { minute: 60, chunk: 90, max: 20 * 60 };
/** The demo's end-to-end checks shorten the minute and the pieces (`hq.e2e.voice`); never outside mock mode. */
function limits(): Limits {
  if (!isMock) return LIMITS;
  try {
    const o = JSON.parse(localStorage.getItem('hq.e2e.voice') ?? 'null') as Partial<Limits> | null;
    return o ? { ...LIMITS, ...o } : LIMITS;
  } catch { return LIMITS; }
}

type RecognitionResult = { isFinal: boolean; 0?: { transcript: string } };
type RecognitionEvent = { results: ArrayLike<RecognitionResult> };
type Recognition = {
  lang: string; continuous: boolean; interimResults: boolean; maxAlternatives: number;
  start(): void; stop(): void; abort(): void;
  onresult: ((e: RecognitionEvent) => void) | null; onerror: ((e: { error: string }) => void) | null; onend: (() => void) | null;
};
type RecognitionCtor = new () => Recognition;
/** The browser's recogniser (Chrome, Edge and Safari name it with a prefix), or null. */
export function recognizer(): RecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}
/** Errors after which the recogniser will not come back in this session (the others are a pause or our own stop). */
const FATAL = new Set(['not-allowed', 'service-not-allowed', 'network', 'audio-capture', 'language-not-supported', 'bad-grammar']);
const join = (...xs: string[]) => xs.map((x) => x.trim()).filter(Boolean).join(' ');

export type LongVoicePhase = 'idle' | 'asking' | 'listening' | 'sending';
export type LongVoiceResult = { text: string; seconds: number; via: 'phone' | 'hub' };
export type LongVoiceFailure = 'denied' | 'unsupported' | 'empty' | 'hub';
export const LONG_VOICE_ERROR: Record<LongVoiceFailure, string> = {
  denied: 'اجازه‌ی میکروفون داده نشده؛ از تنظیمات مرورگر برای این سایت روشنش کن.',
  unsupported: 'این مرورگر نه ضبط صدا را پشتیبانی میکند و نه تبدیل گفتار را.',
  empty: 'حرفی شنیده نشد؛ دوباره بگو.',
  hub: 'صدا به متن تبدیل نشد؛ دوباره بگو یا بنویس.',
};

// Everything one recording needs; a new recording starts from a fresh object, so a late event of the last one changes nothing.
type Run = {
  L: Limits; stream: MediaStream | null; ctx: AudioContext | null; raf: number; timer: ReturnType<typeof setInterval> | null;
  rec: MediaRecorder | null; segStart: number; t0: number; segments: Blob[]; queued: number;
  recog: Recognition | null; recogFailed: boolean; recogEnded: Promise<void>; endRecog: () => void; restarts: number[];
  committed: string; finals: string; interim: string;
  stopped: boolean; cancelled: boolean; concluded: boolean; rotating: boolean; hubMode: boolean; session: string | null | undefined; chain: Promise<void>; uploadError: unknown;
  abort: AbortController; seconds: number;
};

/**
 * One standalone piece of audio at a time (each one a whole file the STT can read): when a piece stops, turned over at its limit or at
 * the end, [onPiece] gets it and the next one starts, unless the recording is over ([onOver]).
 */
function recordPiece(r: Run, onPiece: (blob: Blob) => void, onOver: () => void) {
  const stream = r.stream;
  if (!stream) return;
  const mimeType = TYPES.find((t) => MediaRecorder.isTypeSupported(t));
  const rec = new MediaRecorder(stream, mimeType ? { mimeType, audioBitsPerSecond: 32_000 } : undefined);
  const parts: Blob[] = [];
  rec.ondataavailable = (e) => { if (e.data.size) parts.push(e.data); };
  rec.onstop = () => {
    if (r.cancelled) return;
    const blob = new Blob(parts, { type: (rec.mimeType || mimeType || 'audio/webm').split(';')[0] });
    if (blob.size) onPiece(blob);
    if (!r.stopped) recordPiece(r, onPiece, onOver); else onOver();
  };
  r.rec = rec;
  r.rotating = false;
  r.segStart = performance.now();
  rec.start(1000);
}

/**
 * Long voice (§29.5). `live` is the text as it grows; `hub` says the pieces are going to the hub, `sent` of `total` of them so far.
 * `finish` ends it and hands the whole text to `onText`; `cancel` throws everything away.
 */
export function useLongVoice({ purpose, onText, onError }: { purpose: SttPurpose; onText: (r: LongVoiceResult) => void; onError: (f: LongVoiceFailure, detail?: string) => void }) {
  const [phase, setPhase] = useState<LongVoicePhase>('idle');
  const [elapsed, setElapsed] = useState(0);
  const [levels, setLevels] = useState<number[]>(() => Array<number>(BARS).fill(0));
  const [live, setLive] = useState('');
  const [hub, setHub] = useState(false);
  const [sent, setSent] = useState(0);
  const [total, setTotal] = useState(0);
  const cb = useRef({ onText, onError });
  useEffect(() => { cb.current = { onText, onError }; });

  const run = useRef<Run | null>(null);

  const release = useCallback((r: Run) => {
    cancelAnimationFrame(r.raf);
    if (r.timer) clearInterval(r.timer);
    r.timer = null;
    r.stream?.getTracks().forEach((t) => t.stop());
    r.stream = null;
    void r.ctx?.close().catch(() => undefined);
    r.ctx = null;
  }, []);

  /** Piece [i] to the hub, after the ones before it; the first failure stops the rest (they must arrive in order). */
  const enqueue = useCallback((r: Run, i: number) => {
    r.queued = Math.max(r.queued, i + 1);
    r.chain = r.chain.then(async () => {
      if (r.cancelled || r.uploadError) return;
      try {
        if (r.session === undefined) r.session = await openSttSession(purpose);
        if (!r.session) return; // a hub without sessions: the pieces are read one by one at the end
        await putSttChunk(r.session, i, r.segments[i]!, r.abort.signal);
        if (run.current === r) setSent(i + 1);
      } catch (e) { r.uploadError = e; }
    });
  }, [purpose]);

  const goHub = useCallback((r: Run) => {
    if (r.hubMode || (!r.stream && !r.segments.length)) return;
    r.hubMode = true;
    if (run.current === r) setHub(true);
    for (let i = r.queued; i < r.segments.length; i++) enqueue(r, i);
  }, [enqueue]);

  /** The recording is over: the recogniser's text when it is enough, else the hub's. */
  const conclude = useCallback(async (r: Run) => {
    if (r.concluded) return;
    r.concluded = true;
    release(r);
    await Promise.race([r.recogEnded, new Promise((ok) => setTimeout(ok, 1500))]);
    if (r.cancelled) return;
    const phone = join(r.committed, r.finals, r.interim);
    const seconds = r.seconds;
    const done = (res: LongVoiceResult) => { if (run.current === r) { setPhase('idle'); cb.current.onText(res); } };
    const fail = (f: LongVoiceFailure, detail?: string) => { if (run.current === r) { setPhase('idle'); cb.current.onError(f, detail); } };
    if (!r.hubMode && phone) return done({ text: phone, seconds, via: 'phone' });
    if (!r.segments.length) return phone ? done({ text: phone, seconds, via: 'phone' }) : fail('empty');
    setPhase('sending');
    goHub(r);
    for (let i = r.queued; i < r.segments.length; i++) enqueue(r, i);
    await r.chain;
    if (r.cancelled) return;
    try {
      if (r.uploadError) throw r.uploadError;
      if (r.session) {
        const out = await finishSttSession(r.session);
        if (!out.text?.trim()) return phone ? done({ text: phone, seconds, via: 'phone' }) : fail('empty');
        return done({ text: out.text.trim(), seconds: out.duration_s || seconds, via: 'hub' });
      }
      // A hub before §29.5: each piece through the one-shot `/transcribe`, joined in order.
      const texts: string[] = [];
      for (const [i, b] of r.segments.entries()) {
        texts.push((await transcribe(b, purpose === 'rule' ? 'order' : purpose, r.abort.signal)).text);
        if (run.current === r) setSent(i + 1);
      }
      const text = join(...texts);
      return text ? done({ text, seconds, via: 'hub' }) : phone ? done({ text: phone, seconds, via: 'phone' }) : fail('empty');
    } catch (e) {
      if (r.cancelled) return;
      if (e instanceof ApiError) handled(e);
      // The recogniser's words are better than nothing; the owner reads them before sending.
      if (phone) return done({ text: phone, seconds, via: 'phone' });
      return fail('hub', e instanceof ApiError ? e.messageFa : undefined);
    }
  }, [enqueue, goHub, purpose, release]);

  const startSegment = useCallback((r: Run) => recordPiece(r, (blob) => {
    r.segments.push(blob);
    if (run.current === r) setTotal(r.segments.length);
    if (r.hubMode) enqueue(r, r.segments.length - 1);
  }, () => void conclude(r)), [conclude, enqueue]);

  const finish = useCallback(() => {
    const r = run.current;
    if (!r || r.stopped) return;
    r.stopped = true;
    r.seconds = (performance.now() - r.t0) / 1000;
    try { r.recog?.stop(); } catch { r.endRecog(); }
    // A piece being turned over concludes from its own stop.
    if (r.rec?.state === 'recording') r.rec.stop(); else if (!r.rotating) void conclude(r);
  }, [conclude]);

  const startRecognition = useCallback((r: Run, R: RecognitionCtor) => {
    const g = new R();
    g.lang = 'fa-IR';
    g.continuous = true;
    g.interimResults = true;
    g.maxAlternatives = 1;
    g.onresult = (e) => {
      let fin = '';
      let mid = '';
      for (let i = 0; i < e.results.length; i++) {
        const x = e.results[i]!;
        const t = x[0]?.transcript ?? '';
        if (x.isFinal) fin = join(fin, t); else mid = join(mid, t);
      }
      r.finals = fin;
      r.interim = mid;
      if (run.current === r) setLive(join(r.committed, fin, mid));
    };
    g.onerror = (e) => {
      if (!FATAL.has(e.error)) return; // a pause, or our own stop: `end` follows and starts it again
      r.recogFailed = true;
      if (r.stream) goHub(r);
    };
    g.onend = () => {
      r.committed = join(r.committed, r.finals);
      r.finals = '';
      r.interim = '';
      if (r.stopped || r.cancelled || r.recogFailed) { r.endRecog(); return; }
      // Started again at every pause; one that ends at once again and again is broken, and the hub takes over.
      const now = performance.now();
      r.restarts = [...r.restarts.filter((t) => now - t < 10_000), now];
      if (r.restarts.length > 20) { r.recogFailed = true; r.endRecog(); if (r.stream) goHub(r); else finish(); return; }
      try { g.start(); } catch { r.recogFailed = true; r.endRecog(); if (r.stream) goHub(r); else finish(); }
    };
    r.recog = g;
    try { g.start(); } catch { r.recogFailed = true; r.endRecog(); }
  }, [finish, goHub]);

  const start = useCallback(async () => {
    if (run.current && !run.current.stopped) return;
    let endRecog = () => {};
    const r: Run = {
      L: limits(), stream: null, ctx: null, raf: 0, timer: null, rec: null, segStart: 0, t0: 0, segments: [], queued: 0,
      recog: null, recogFailed: false, recogEnded: new Promise<void>((ok) => { endRecog = ok; }), endRecog: () => endRecog(), restarts: [],
      committed: '', finals: '', interim: '', stopped: false, cancelled: false, concluded: false, rotating: false, hubMode: false, session: undefined, chain: Promise.resolve(), uploadError: null,
      abort: new AbortController(), seconds: 0,
    };
    run.current = r;
    setLive(''); setHub(false); setSent(0); setTotal(0); setElapsed(0);
    setPhase('asking');
    const R = recognizer();
    const canRecord = typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined';
    if (canRecord) {
      try {
        r.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
      } catch (e) {
        if ((e as DOMException)?.name === 'NotAllowedError') { setPhase('idle'); run.current = null; cb.current.onError('denied'); return; }
      }
    }
    if (r.cancelled) { release(r); return; }
    if (!r.stream && !R) { setPhase('idle'); run.current = null; cb.current.onError('unsupported'); return; }
    r.t0 = performance.now();
    if (r.stream) startSegment(r);
    if (R) startRecognition(r, R); else { r.endRecog(); goHub(r); }
    setPhase('listening');

    // The clock, the pieces' turn-over, the minute and the 20-minute cap; it keeps going in a background tab (throttled).
    r.timer = setInterval(() => {
      if (r.stopped) return;
      const sec = (performance.now() - r.t0) / 1000;
      setElapsed(sec);
      if (!r.hubMode && r.stream && (sec >= r.L.minute || r.recogFailed)) goHub(r);
      if (!r.stream && r.recogFailed) { finish(); return; }
      if (r.rec?.state === 'recording' && (performance.now() - r.segStart) / 1000 >= r.L.chunk) { r.rotating = true; r.rec.stop(); }
      if (sec >= r.L.max) finish();
    }, 200);

    // Loudness for the waveform, as the recorder does it.
    if (r.stream) {
      try {
        const ctx = new AudioContext();
        r.ctx = ctx;
        const an = ctx.createAnalyser();
        an.fftSize = 1024;
        ctx.createMediaStreamSource(r.stream).connect(an);
        const buf = new Float32Array(an.fftSize);
        let last = 0;
        let eased = 0;
        const tick = (now: number) => {
          if (r.stopped) return;
          an.getFloatTimeDomainData(buf);
          let sum = 0;
          for (const v of buf) sum += v * v;
          eased = Math.max(Math.min(1, Math.sqrt(sum / buf.length) * 5.5), eased * 0.82);
          if (now - last > 90) { last = now; setLevels((l) => [...l.slice(1), eased]); }
          r.raf = requestAnimationFrame(tick);
        };
        r.raf = requestAnimationFrame(tick);
      } catch { /* no Web Audio: still recording */ }
    }
  }, [finish, goHub, release, startRecognition, startSegment]);

  const cancel = useCallback(() => {
    const r = run.current;
    if (!r) { setPhase('idle'); return; }
    r.cancelled = true;
    r.stopped = true;
    r.abort.abort();
    try { r.recog?.abort(); } catch { /* already ended */ }
    if (r.rec?.state === 'recording') r.rec.stop();
    release(r);
    r.endRecog();
    run.current = null;
    setPhase('idle'); setLive(''); setHub(false); setSent(0); setTotal(0); setElapsed(0);
    setLevels(Array<number>(BARS).fill(0));
  }, [release]);

  useEffect(() => () => {
    const r = run.current;
    if (!r) return;
    r.cancelled = true;
    r.stopped = true;
    r.abort.abort();
    try { r.recog?.abort(); } catch { /* ended */ }
    if (r.rec?.state === 'recording') r.rec.stop();
    release(r);
  }, [release]);

  return { phase, elapsed, levels, live, hub, sent, total, start, finish, cancel, maxSeconds: LIMITS.max, minuteSeconds: LIMITS.minute };
}
