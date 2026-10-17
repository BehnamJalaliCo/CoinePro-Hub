'use client';

import * as D from '@radix-ui/react-dialog';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { Spinner } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { fileUrl, kindOf, uploadFile, type FileKind, type MediaRef } from '@/lib/api/v13';
import { clock } from '@/lib/recorder';
import { cx } from '@/lib/format';

// ------------------------------------------------------------------ limits --
// Contract §17.1. The server checks again (by content, while streaming); this only saves a pointless upload.
const MB = 1024 * 1024;
const ACCEPT: Record<FileKind, { types: string[]; max: number; fa: string }> = {
  image: { types: ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'], max: 20 * MB, fa: 'عکس' },
  video: { types: ['video/mp4', 'video/webm', 'video/quicktime'], max: 200 * MB, fa: 'فیلم' },
  audio: { types: ['audio/mp4', 'audio/x-m4a', 'audio/aac', 'audio/ogg', 'audio/webm', 'audio/wav', 'audio/x-wav', 'audio/mpeg'], max: 25 * MB, fa: 'صدا' },
  document: { types: ['application/pdf'], max: 30 * MB, fa: 'PDF' },
};
const BY_EXT: Record<string, string> = { heic: 'image/heic', heif: 'image/heif', mov: 'video/quicktime', m4a: 'audio/mp4', opus: 'audio/ogg', pdf: 'application/pdf' };
export const PICKER_ACCEPT = [...ACCEPT.image.types, ...ACCEPT.video.types, ...ACCEPT.document.types, '.heic', '.heif', '.mov'].join(',');
const MAX_VIDEO_S = 600;

/** Desktop browsers often leave HEIC and MOV untyped. */
function mimeOf(f: File): string {
  if (f.type) return f.type;
  return BY_EXT[f.name.split('.').pop()?.toLowerCase() ?? ''] ?? '';
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < MB) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / MB).toFixed(bytes < 10 * MB ? 1 : 0)} MB`;
}

function rejectReason(f: File): string | null {
  const mime = mimeOf(f);
  const kind = kindOf(mime);
  const rule = ACCEPT[kind];
  if (!rule.types.includes(mime)) return `«${f.name}»: این نوع فایل پذیرفته نمیشود (عکس، فیلم یا PDF).`;
  if (f.size > rule.max) return `«${f.name}»: ${rule.fa} حداکثر ${fileSize(rule.max)} است.`;
  return null;
}

/** Length of a local video before it is uploaded; null when the browser cannot tell. */
function videoSeconds(url: string): Promise<number | null> {
  return new Promise((resolve) => {
    const v = document.createElement('video');
    const t = setTimeout(() => resolve(null), 4000);
    v.preload = 'metadata';
    v.onloadedmetadata = () => { clearTimeout(t); resolve(Number.isFinite(v.duration) ? v.duration : null); };
    v.onerror = () => { clearTimeout(t); resolve(null); };
    v.src = url;
  });
}

// ------------------------------------------------------------ the uploads --
export type Pending = {
  key: string; name: string; kind: FileKind; size: number; preview: string | null; seconds: number | null;
  pct: number; state: 'uploading' | 'ready' | 'failed'; ref: MediaRef | null; error: string | null;
};

/** Files the owner is attaching: checked, uploaded at once with progress, cancellable, retryable. */
export function useAttachments(max = 10) {
  const toast = useToast();
  const [items, setItems] = useState<Pending[]>([]);
  const files = useRef(new Map<string, { file: File; ctrl: AbortController }>());
  const count = useRef(0);
  useEffect(() => { count.current = items.length; }, [items.length]);

  const patch = useCallback((key: string, p: Partial<Pending>) => setItems((xs) => xs.map((x) => (x.key === key ? { ...x, ...p } : x))), []);

  const upload = useCallback((key: string) => {
    const f = files.current.get(key);
    if (!f) return;
    uploadFile(f.file, f.file.name, (pct) => patch(key, { pct }), f.ctrl.signal)
      .then((ref) => patch(key, { state: 'ready', pct: 100, ref }))
      .catch((e: unknown) => {
        if (f.ctrl.signal.aborted) return;
        patch(key, { state: 'failed', error: e instanceof ApiError ? e.messageFa : 'بارگذاری نشد.' });
      });
  }, [patch]);

  const add = useCallback(async (list: Iterable<File>) => {
    for (const file of list) {
      if (count.current >= max) { toast({ tone: 'error', text: `حداکثر ${max} پیوست در هر پیام.` }); return; }
      const why = rejectReason(file);
      if (why) { toast({ tone: 'error', text: why }); continue; }
      const mime = mimeOf(file);
      const kind = kindOf(mime);
      const typed = file.type ? file : new File([file], file.name, { type: mime, lastModified: file.lastModified });
      const preview = kind === 'image' || kind === 'video' ? URL.createObjectURL(typed) : null;
      const seconds = kind === 'video' && preview ? await videoSeconds(preview) : null;
      if (seconds != null && seconds > MAX_VIDEO_S) {
        if (preview) URL.revokeObjectURL(preview);
        toast({ tone: 'error', text: `«${file.name}»: فیلم حداکثر ۱۰ دقیقه است.` });
        continue;
      }
      const key = crypto.randomUUID();
      files.current.set(key, { file: typed, ctrl: new AbortController() });
      count.current += 1;
      setItems((xs) => [...xs, { key, name: file.name, kind, size: file.size, preview, seconds, pct: 0, state: 'uploading', ref: null, error: null }]);
      upload(key);
    }
  }, [max, toast, upload]);

  const remove = useCallback((key: string) => {
    files.current.get(key)?.ctrl.abort();
    files.current.delete(key);
    setItems((xs) => {
      const x = xs.find((y) => y.key === key);
      if (x?.preview) URL.revokeObjectURL(x.preview);
      return xs.filter((y) => y.key !== key);
    });
  }, []);

  const retry = useCallback((key: string) => {
    const f = files.current.get(key);
    if (!f) return;
    f.ctrl = new AbortController();
    patch(key, { state: 'uploading', pct: 0, error: null });
    upload(key);
  }, [patch, upload]);

  const clear = useCallback(() => {
    for (const f of files.current.values()) f.ctrl.abort();
    files.current.clear();
    setItems((xs) => { xs.forEach((x) => x.preview && URL.revokeObjectURL(x.preview)); return []; });
  }, []);

  useEffect(() => () => { for (const f of files.current.values()) f.ctrl.abort(); }, []);

  const ids = useMemo(() => items.flatMap((x) => (x.ref ? [x.ref.id] : [])), [items]);
  return { items, ids, add, remove, retry, clear, uploading: items.some((x) => x.state === 'uploading'), failed: items.some((x) => x.state === 'failed') };
}

function Ring({ pct, size = 30 }: { pct: number; size?: number }) {
  const r = size / 2 - 3;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,.28)" strokeWidth="3" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)} style={{ transition: 'stroke-dashoffset 160ms linear' }} />
    </svg>
  );
}

const KIND_ICON: Record<FileKind, 'image' | 'video' | 'mic' | 'report'> = { image: 'image', video: 'video', audio: 'mic', document: 'report' };

/** The composer's row of files on their way. */
export function AttachmentTray({ items, onRemove, onRetry }: { items: Pending[]; onRemove: (key: string) => void; onRetry: (key: string) => void }) {
  if (!items.length) return null;
  return (
    <ul className="flex gap-2 overflow-x-auto px-1 pb-1 pt-1" aria-label="پیوست‌ها">
      {items.map((x) => (
        <li key={x.key} className="relative flex-none" title={`${x.name} · ${fileSize(x.size)}`}>
          <div className={cx('relative flex size-16 items-center justify-center overflow-hidden rounded-[12px] bg-tile', x.state === 'failed' && 'ring-1 ring-[var(--hq-neg-line)]')}>
            {x.kind === 'image' && x.preview ? (
              // eslint-disable-next-line @next/next/no-img-element -- local object URL preview
              <img src={x.preview} alt="" className="size-full object-cover" />
            ) : x.kind === 'video' && x.preview ? (
              <video src={`${x.preview}#t=0.1`} muted playsInline preload="metadata" className="size-full object-cover" />
            ) : (
              <span className="flex flex-col items-center gap-0.5 text-sec"><Icon name={KIND_ICON[x.kind]} size={22} /><span className="fig text-[9px]">{x.name.split('.').pop()?.toUpperCase()}</span></span>
            )}
            {x.kind === 'video' ? <span className="fig absolute bottom-1 left-1 rounded-full bg-black/60 px-1.5 text-[10px] leading-4 text-white">{x.seconds != null ? clock(x.seconds) : '▶'}</span> : null}
            {x.state === 'uploading' ? <span className="absolute inset-0 flex items-center justify-center bg-black/45"><Ring pct={x.pct} /></span> : null}
            {x.state === 'failed' ? (
              <button type="button" onClick={() => onRetry(x.key)} aria-label={`دوباره بفرست: ${x.name}`} title={x.error ?? ''} className="absolute inset-0 flex items-center justify-center bg-black/55 text-white">
                <Icon name="refresh" size={20} />
              </button>
            ) : null}
          </div>
          <button type="button" onClick={() => onRemove(x.key)} aria-label={`حذف ${x.name}`} className="absolute -top-1.5 -start-1.5 flex size-6 items-center justify-center rounded-full bg-raised text-sec shadow-[0_2px_6px_rgba(0,0,0,.35)] hover:text-ink">
            <Icon name="close" size={14} />
          </button>
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------ in a message --
function Lightbox({ images, index, onIndex }: { images: MediaRef[]; index: number | null; onIndex: (i: number | null) => void }) {
  const cur = index == null ? null : images[index];
  const go = (d: number) => index != null && onIndex((index + d + images.length) % images.length);
  return (
    <D.Root open={cur != null} onOpenChange={(v) => !v && onIndex(null)}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[70] bg-black/90" />
        <D.Content
          className="fixed inset-0 z-[71] flex flex-col outline-none"
          onKeyDown={(e) => { if (e.key === 'ArrowLeft') go(1); if (e.key === 'ArrowRight') go(-1); }}
        >
          <div className="flex items-center gap-2 px-3 py-2 text-white">
            <D.Title className="min-w-0 flex-1 truncate text-[13px]">{cur?.name}</D.Title>
            <D.Description className="sr-only">نمایش عکس</D.Description>
            {images.length > 1 && index != null ? <span className="fig text-[12px] text-white/70">{index + 1}/{images.length}</span> : null}
            {cur ? <a href={fileUrl(cur.id)} download={cur.name} aria-label="دانلود" className="flex size-10 items-center justify-center rounded-full hover:bg-white/10"><Icon name="download" size={20} /></a> : null}
            <D.Close className="flex size-10 items-center justify-center rounded-full hover:bg-white/10" aria-label="بستن"><Icon name="close" size={22} /></D.Close>
          </div>
          <div className="relative flex min-h-0 flex-1 items-center justify-center p-3" onClick={(e) => { if (e.target === e.currentTarget) onIndex(null); }}>
            {cur ? (
              // eslint-disable-next-line @next/next/no-img-element -- owner files, served by the API
              <img src={fileUrl(cur.id)} alt={cur.name} className="max-h-full max-w-full rounded-[8px] object-contain" />
            ) : null}
            {images.length > 1 ? (
              <>
                <button type="button" onClick={() => go(-1)} aria-label="قبلی" className="absolute right-3 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"><Icon name="next" size={22} mirror /></button>
                <button type="button" onClick={() => go(1)} aria-label="بعدی" className="absolute left-3 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"><Icon name="next" size={22} /></button>
              </>
            ) : null}
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

function Images({ images }: { images: MediaRef[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const shown = images.slice(0, 4);
  const one = images.length === 1 ? images[0]! : null;
  return (
    <>
      {one ? (
        // Known size: the frame is exactly the picture, at most 420 wide and 320 tall. Unknown: a 320 frame.
        <button
          type="button" onClick={() => setOpen(0)} aria-label={`نمایش ${one.name}`}
          className="block overflow-hidden rounded-[12px] bg-tile"
          style={one.width && one.height
            ? { width: `min(100%, ${Math.round(Math.min(420, (320 * one.width) / one.height))}px)`, aspectRatio: `${one.width} / ${one.height}` }
            : { width: 'min(100%, 320px)' }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- owner files, served by the API */}
          <img src={fileUrl(one.variants?.thumb ?? one.id)} alt={one.name} loading="lazy" decoding="async" className="block size-full max-h-[320px] object-cover" />
        </button>
      ) : (
        <div className="grid w-[min(100%,360px)] grid-cols-2 gap-1 overflow-hidden rounded-[12px]">
          {shown.map((m, i) => (
            <button key={m.id} type="button" onClick={() => setOpen(i)} className="relative aspect-square overflow-hidden bg-tile" aria-label={`نمایش ${m.name}`}>
              {/* eslint-disable-next-line @next/next/no-img-element -- owner files, served by the API */}
              <img src={fileUrl(m.variants?.thumb ?? m.id)} alt={m.name} loading="lazy" decoding="async" className="size-full object-cover" />
              {i === 3 && images.length > 4 ? <span className="fig absolute inset-0 flex items-center justify-center bg-black/55 text-[20px] font-semibold text-white">+{images.length - 4}</span> : null}
            </button>
          ))}
        </div>
      )}
      <Lightbox images={images} index={open} onIndex={setOpen} />
    </>
  );
}

function Video({ v }: { v: MediaRef }) {
  if (v.status === 'failed') return <p className="text-[12px] text-neg">فیلم «{v.name}» پردازش نشد.</p>;
  return (
    <figure className="flex w-[min(100%,420px)] flex-col gap-1">
      <video
        controls playsInline preload="metadata" src={fileUrl(v.id)}
        poster={v.variants?.poster ? fileUrl(v.variants.poster) : undefined}
        className="max-h-[360px] w-full rounded-[12px] bg-black"
      />
      <figcaption className="flex items-center gap-2 px-1 text-[11px] text-muted">
        <Icon name="video" size={14} />
        {v.duration_s ? <span className="fig">{clock(v.duration_s)}</span> : null}
        <span className="fig">{fileSize(v.size)}</span>
        {v.status === 'processing' ? <span className="flex items-center gap-1"><Spinner size={12} />آماده‌سازی برای ایجنت‌ها</span> : null}
      </figcaption>
    </figure>
  );
}

/** Deterministic bar heights per file, so a voice note always looks the same. */
function bars(seed: string, n: number): number[] {
  let h = 2166136261;
  for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return Array.from({ length: n }, (_, i) => {
    h = Math.imul(h ^ (i + 1), 16777619);
    const r = ((h >>> 0) % 1000) / 1000;
    return 0.25 + 0.75 * Math.abs(Math.sin(i * 0.55 + r * 2.4)) * (0.55 + 0.45 * r);
  });
}

/** A voice note: play, scrub, time — and the exact text when the hub has it. */
export function AudioPlayer({ a, showTranscript = true }: { a: MediaRef; showTranscript?: boolean }) {
  const el = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [t, setT] = useState(0);
  const [dur, setDur] = useState(a.duration_s ?? 0);
  const [text, setText] = useState(false);
  const shape = useMemo(() => bars(a.id, 36), [a.id]);
  const p = dur > 0 ? Math.min(1, t / dur) : 0;
  const toggle = () => { const x = el.current; if (!x) return; if (x.paused) void x.play(); else x.pause(); };
  const seek = (e: React.PointerEvent<HTMLDivElement>) => {
    const x = el.current;
    if (!x || !dur) return;
    const r = e.currentTarget.getBoundingClientRect();
    x.currentTime = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * dur;
  };
  return (
    <div className="flex w-[min(100%,340px)] flex-col gap-1.5">
      <div className="flex items-center gap-3 rounded-[12px] bg-tile px-2.5 py-2">
        <audio
          ref={el} src={fileUrl(a.id)} preload="metadata"
          onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => { setPlaying(false); setT(0); }}
          onTimeUpdate={(e) => setT(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => { const d = e.currentTarget.duration; if (Number.isFinite(d) && d > 0) setDur(d); }}
        />
        <button type="button" onClick={toggle} aria-label={playing ? 'مکث' : 'پخش'} className="flex size-9 flex-none items-center justify-center rounded-full bg-gold text-on-gold">
          <Icon name={playing ? 'pause' : 'resume'} size={18} />
        </button>
        {/* Playback runs left to right like every media timeline, also in RTL. */}
        <div dir="ltr" role="slider" tabIndex={0} aria-label="جای پخش" aria-valuemin={0} aria-valuemax={Math.round(dur)} aria-valuenow={Math.round(t)}
          onPointerDown={seek}
          onKeyDown={(e) => { const x = el.current; if (!x) return; if (e.key === 'ArrowRight') x.currentTime = Math.min(dur, x.currentTime + 5); if (e.key === 'ArrowLeft') x.currentTime = Math.max(0, x.currentTime - 5); }}
          className="flex h-8 min-w-0 flex-1 cursor-pointer items-center gap-[2px]"
        >
          {shape.map((h, i) => (
            <span key={i} className={cx('w-[3px] flex-none rounded-full transition-colors duration-150', i / shape.length < p ? 'bg-gold-ink' : 'bg-strong')} style={{ height: `${Math.round(h * 100)}%` }} />
          ))}
        </div>
        <span className="fig w-10 flex-none text-left text-[11px] text-muted">{clock(playing || t > 0 ? t : dur)}</span>
      </div>
      {showTranscript && a.transcript ? (
        <div className="px-1">
          <button type="button" onClick={() => setText((v) => !v)} aria-expanded={text} className="text-[11px] font-semibold text-gold-ink">{text ? 'بستن متن' : 'متن ویس'}</button>
          {text ? <p className="pt-1 text-[13px] leading-6 text-sec">{a.transcript}</p> : null}
        </div>
      ) : a.status === 'processing' ? <span className="flex items-center gap-1 px-1 text-[11px] text-muted"><Spinner size={12} />در حال نوشتن متن…</span> : null}
    </div>
  );
}

function Doc({ d }: { d: MediaRef }) {
  return (
    <a href={fileUrl(d.id)} download={d.name} className="flex w-[min(100%,340px)] items-center gap-3 rounded-[12px] bg-tile px-3 py-2.5 hover:bg-hover">
      <span className="text-sec"><Icon name="report" size={22} /></span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-[13px] text-ink">{d.name}</span>
        <span className="fig text-[11px] text-muted">{fileSize(d.size)}</span>
      </span>
      <span className="text-sec"><Icon name="download" size={18} /></span>
    </a>
  );
}

/** Everything attached to one message, grouped: pictures first, then films, voice and documents. */
export function MessageMedia({ items, transcriptInBody = false }: { items: MediaRef[]; transcriptInBody?: boolean }) {
  if (!items.length) return null;
  const by = (k: FileKind) => items.filter((x) => x.kind === k);
  const images = by('image');
  return (
    <div className="flex flex-col gap-2">
      {images.length ? <Images images={images} /> : null}
      {by('video').map((v) => <Video key={v.id} v={v} />)}
      {by('audio').map((a) => <AudioPlayer key={a.id} a={a} showTranscript={!transcriptInBody} />)}
      {by('document').map((d) => <Doc key={d.id} d={d} />)}
    </div>
  );
}

