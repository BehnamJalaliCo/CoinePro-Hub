'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export type RecorderState = 'idle' | 'asking' | 'recording' | 'denied' | 'unsupported' | 'failed';

// Opus first (small and what Whisper reads best); Safari records AAC in MP4.
const TYPES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4;codecs=mp4a.40.2', 'audio/mp4', 'audio/webm'];
const BARS = 40;

/**
 * The owner's voice, recorded in the browser (contract §17.2 takes the result).
 * `levels` is the last few seconds of loudness for the waveform; `finish` hands the recording to `onFinish`,
 * and so does reaching `maxSeconds`; `cancel` throws it away.
 */
export function useRecorder({ maxSeconds, onFinish }: { maxSeconds: number; onFinish: (audio: Blob, seconds: number) => void }) {
  const [state, setState] = useState<RecorderState>('idle');
  const [elapsed, setElapsed] = useState(0);
  const [levels, setLevels] = useState<number[]>(() => Array<number>(BARS).fill(0));
  const rec = useRef<MediaRecorder | null>(null);
  const media = useRef<MediaStream | null>(null);
  const audio = useRef<AudioContext | null>(null);
  const raf = useRef(0);
  const keep = useRef(true);
  const done = useRef(onFinish);
  useEffect(() => { done.current = onFinish; });

  const release = useCallback(() => {
    cancelAnimationFrame(raf.current);
    media.current?.getTracks().forEach((t) => t.stop());
    media.current = null;
    void audio.current?.close().catch(() => undefined);
    audio.current = null;
    rec.current = null;
  }, []);

  const finish = useCallback(() => {
    keep.current = true;
    if (rec.current?.state === 'recording') rec.current.stop();
  }, []);

  const cancel = useCallback(() => {
    keep.current = false;
    if (rec.current?.state === 'recording') rec.current.stop();
    else release();
    setState('idle');
  }, [release]);

  const start = useCallback(async () => {
    if (typeof window === 'undefined' || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setState('unsupported');
      return;
    }
    setState('asking');
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
    } catch (e) {
      setState((e as DOMException)?.name === 'NotAllowedError' ? 'denied' : 'failed');
      return;
    }
    media.current = stream;
    const mimeType = TYPES.find((t) => MediaRecorder.isTypeSupported(t));
    const r = new MediaRecorder(stream, mimeType ? { mimeType, audioBitsPerSecond: 32_000 } : undefined);
    const chunks: Blob[] = [];
    const t0 = performance.now();
    r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    r.onstop = () => {
      const seconds = (performance.now() - t0) / 1000;
      const type = r.mimeType || mimeType || 'audio/webm';
      release();
      setState('idle');
      setElapsed(0);
      setLevels(Array<number>(BARS).fill(0));
      if (keep.current && chunks.length) done.current(new Blob(chunks, { type: type.split(';')[0] }), seconds);
    };
    rec.current = r;
    keep.current = true;
    r.start(1000);
    setState('recording');

    // Loudness for the waveform: RMS of the time-domain signal, eased so the bars breathe instead of flicker.
    try {
      const ctx = new AudioContext();
      audio.current = ctx;
      const an = ctx.createAnalyser();
      an.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(an);
      const buf = new Float32Array(an.fftSize);
      let last = 0;
      let eased = 0;
      const tick = (now: number) => {
        an.getFloatTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += v * v;
        const rms = Math.sqrt(sum / buf.length);
        eased = Math.max(Math.min(1, rms * 5.5), eased * 0.82);
        if (now - last > 90) {
          last = now;
          const sec = (now - t0) / 1000;
          setElapsed(sec);
          setLevels((l) => [...l.slice(1), eased]);
          if (sec >= maxSeconds) { finish(); return; }
        }
        raf.current = requestAnimationFrame(tick);
      };
      raf.current = requestAnimationFrame(tick);
    } catch {
      // No Web Audio: still record, and keep the clock running.
      const timer = setInterval(() => {
        const sec = (performance.now() - t0) / 1000;
        setElapsed(sec);
        if (sec >= maxSeconds || !rec.current) { clearInterval(timer); if (rec.current) finish(); }
      }, 250);
    }
  }, [finish, maxSeconds, release]);

  useEffect(() => () => { keep.current = false; if (rec.current?.state === 'recording') rec.current.stop(); release(); }, [release]);

  const reset = useCallback(() => setState('idle'), []);
  return { state, elapsed, levels, start, finish, cancel, reset };
}

/** "0:42", "12:05" — figures stay Latin. */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export const RECORDER_ERROR: Record<'denied' | 'unsupported' | 'failed', string> = {
  denied: 'اجازه‌ی میکروفون داده نشده؛ از تنظیمات مرورگر برای این سایت روشنش کن.',
  unsupported: 'این مرورگر ضبط صدا را پشتیبانی نمیکند.',
  failed: 'میکروفون در دسترس نیست.',
};
