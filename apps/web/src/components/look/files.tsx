'use client';

// ⟨1.0.1⟩ Part C, the files of an output (C2.2; features 29 and 30). The thing itself is seen, not a label that stands for it: a strip
// of tiles, each a file as it is (a picture shows itself, a video its poster frame with its length, a document its type mark and
// name), captioned with its plain name and size. A tap opens it in place: a picture and a text file in the viewer, a video inline
// (muted, without controls; one more tap is the full screen with controls and sound). Nothing plays before the owner's own tap. A
// video that will not play says so in one sentence with its download. A PDF opens in the browser's own reader (a new tab).

import * as D from '@radix-ui/react-dialog';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { fileSize } from '@/components/media/attachments';
import { fileUrl } from '@/lib/api/v13';
import { cx } from '@/lib/format';
import { clock } from '@/lib/recorder';
import { Ltr } from './text';

/** A file as the hub's FileRef says it (an output's attachment, a desk card's file). */
export type StripFile = {
  id: string; name: string; mime: string; size: number;
  duration_s?: number | null; width?: number | null; height?: number | null; variants?: { thumb?: string | null; poster?: string | null } | null;
};
export const isVideo = (f: Pick<StripFile, 'mime'>) => f.mime.startsWith('video/');
export const isImage = (f: Pick<StripFile, 'mime'>) => f.mime.startsWith('image/');
/** ⟨1.0.3⟩ §58.1 a PDF opens in the full screen too (the browser's own reader inside it). */
export const isPdf = (f: Pick<StripFile, 'mime' | 'name'>) => f.mime === 'application/pdf' || /\.pdf$/i.test(f.name);
const isText = (f: Pick<StripFile, 'mime' | 'name'>) => f.mime.startsWith('text/') || /\.(md|markdown|txt|srt|csv)$/i.test(f.name);
const ext = (name: string) => (name.includes('.') ? name.split('.').pop()!.toUpperCase().slice(0, 4) : 'FILE');

export const VIDEO_FAILED_FA = 'این ویدیو پخش نشد؛ دانلودش کن';

/** A video's poster frame: the hub's own, and where there is none (or it does not load) the video's first frame. */
export function Poster({ f, className }: { f: StripFile; className?: string }) {
  const [broken, setBroken] = useState(false);
  if (broken) return <video src={`${fileUrl(f.id)}#t=0.1`} muted playsInline preload="metadata" aria-hidden className={className} />;
  // eslint-disable-next-line @next/next/no-img-element -- a file of the owner's, served by the API
  return <img src={f.variants?.poster ? fileUrl(f.variants.poster) : fileUrl(f.id, 'poster')} alt="" loading="lazy" decoding="async" onError={() => setBroken(true)} className={className} />;
}

/** The round play sign on a poster: ivory on a dark disc, never gold. */
export function PlaySign({ size = 40 }: { size?: number }) {
  return (
    <span aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-center">
      <span className="flex items-center justify-center rounded-full bg-black/55 text-white shadow-[0_0_0_1px_rgba(255,255,255,.35)]" style={{ width: size, height: size }}>
        <Icon name="resume" size={Math.round(size * 0.5)} />
      </span>
    </span>
  );
}

/** What a file shows of itself inside a frame of any size (the frame gives the shape). */
export function FileFace({ f, sign = 40 }: { f: StripFile; sign?: number }) {
  if (isVideo(f)) {
    return (
      <>
        <Poster f={f} className="size-full object-cover" />
        <PlaySign size={sign} />
        {f.duration_s ? <Ltr className="absolute bottom-1.5 start-1.5 rounded-full bg-black/65 px-1.5 text-[10px] leading-4 text-white">{clock(f.duration_s)}</Ltr> : null}
      </>
    );
  }
  if (isImage(f)) {
    // eslint-disable-next-line @next/next/no-img-element -- a file of the owner's, served by the API
    return <img src={fileUrl(f.variants?.thumb ?? f.id)} alt="" loading="lazy" decoding="async" className="size-full object-cover" />;
  }
  return (
    <span className="flex flex-col items-center gap-1.5 text-sec">
      <Icon name="report" size={26} />
      <Ltr tabular={false} className="rounded-[5px] border border-strong px-1.5 text-[10px] font-bold leading-4 text-sec">{ext(f.name)}</Ltr>
    </span>
  );
}

const TILE_W = 116;

/** One file as a tile: itself, then its plain name and size. */
export function FileTile({ f, onOpen }: { f: StripFile; onOpen: () => void }) {
  const kind = isVideo(f) ? 'video' : isImage(f) ? 'image' : 'doc';
  const face = (
    <>
      <span className="relative flex h-[148px] w-full items-center justify-center overflow-hidden rounded-[12px] bg-tile shadow-[inset_0_0_0_1px_var(--hq-line-divider)]"><FileFace f={f} /></span>
      <span className="flex min-w-0 flex-col">
        <Ltr tabular={false} className="line-clamp-2 text-[12px] leading-4 text-ink [overflow-wrap:anywhere]">{f.name || 'فایل'}</Ltr>
        <Ltr className="text-[11px] text-muted">{fileSize(f.size)}</Ltr>
      </span>
    </>
  );
  const cls = 'flex flex-none flex-col gap-1.5 rounded-[12px] text-start';
  // A PDF (or any file the page cannot show) opens in the browser's own reader.
  if (kind === 'doc' && !isText(f)) {
    return <a href={fileUrl(f.id)} target="_blank" rel="noreferrer" data-file-tile={f.name} data-kind={kind} aria-label={`باز کردن ${f.name}`} className={cls} style={{ width: TILE_W }}>{face}</a>;
  }
  return (
    <button type="button" onClick={onOpen} data-file-tile={f.name} data-kind={kind} aria-label={`${kind === 'video' ? 'پخش' : 'باز کردن'} ${f.name}`} className={cls} style={{ width: TILE_W }}>
      {face}
    </button>
  );
}

/** «این ویدیو پخش نشد؛ دانلودش کن», with the download. */
export function VideoFailed({ f, className }: { f: StripFile; className?: string }) {
  return (
    <p role="alert" data-video-failed className={cx('flex flex-wrap items-center gap-2 rounded-[12px] bg-tile px-3 py-2.5 text-[13px] leading-6 text-sec', className)}>
      <span className="min-w-0 flex-1">{VIDEO_FAILED_FA}</span>
      <a href={fileUrl(f.id)} download={f.name} className="inline-flex h-9 flex-none items-center gap-1.5 rounded-[10px] border border-strong px-3 text-[13px] font-semibold text-ink hover:bg-hover">
        <Icon name="download" size={16} />دانلود
      </a>
    </p>
  );
}

/** A video playing inside the page: muted and bare; a tap on it is the full screen with controls and sound. */
function InlineVideo({ f, onFull, onClose }: { f: StripFile; onFull: (at: number) => void; onClose: () => void }) {
  const el = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => { void el.current?.play().catch(() => undefined); }, []);
  if (failed) return <VideoFailed f={f} />;
  return (
    <div className="hq-m1 flex flex-col items-start gap-1.5" data-inline-video={f.name}>
      <div className="relative max-w-full overflow-hidden rounded-[14px] bg-black">
        <video ref={el} src={fileUrl(f.id)} poster={f.variants?.poster ? fileUrl(f.variants.poster) : fileUrl(f.id, 'poster')} muted playsInline preload="metadata"
          onError={() => setFailed(true)} onClick={() => onFull(el.current?.currentTime ?? 0)}
          aria-label={`${f.name}؛ یک لمس دیگر: تمام‌صفحه با صدا`} className="block max-h-[360px] max-w-full cursor-pointer" />
        <button type="button" aria-label="بستن پخش" onClick={onClose} className="absolute end-2 top-2 flex size-8 items-center justify-center rounded-full bg-black/60 text-white hover:bg-black/75"><Icon name="close" size={16} /></button>
      </div>
      <span className="text-[11px] text-muted">بی‌صدا پخش میشود؛ یک لمس دیگر روی ویدیو: تمام‌صفحه با صدا.</span>
    </div>
  );
}

/** The first lines of a text file, read once it is opened. */
function TextBody({ f }: { f: StripFile }) {
  const [text, setText] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let off = false;
    fetch(fileUrl(f.id), { credentials: 'same-origin' }).then((r) => (r.ok ? r.text() : Promise.reject(new Error('not ok')))).then((t) => { if (!off) setText(t.slice(0, 20_000)); }).catch(() => { if (!off) setFailed(true); });
    return () => { off = true; };
  }, [f.id]);
  if (failed) return <p className="text-[13px] text-white/80">این فایل این‌جا باز نشد؛ دانلودش کن.</p>;
  return <pre dir="auto" className="max-h-full w-[min(100%,44rem)] overflow-auto whitespace-pre-wrap rounded-[12px] bg-card p-4 text-start font-sans text-[14px] leading-7 text-ink">{text ?? '…'}</pre>;
}

/**
 * ⟨1.0.3⟩ §58.1 a PDF on the full screen: its mark, its name and size, and «باز کن» in the browser's own reader (a new tab). It is not
 * framed in the page: the app and the hub forbid framing (`frame-ancestors 'none'`).
 */
function PdfBody({ f }: { f: StripFile }) {
  return (
    <div className="flex w-[min(100%,24rem)] flex-col items-center gap-4 rounded-[16px] bg-card p-6 text-center" data-pdf>
      <span className="flex h-40 w-32 items-center justify-center rounded-[12px] bg-tile shadow-[inset_0_0_0_1px_var(--hq-line-divider)]"><FileFace f={f} /></span>
      <span className="flex flex-col gap-0.5">
        <Ltr tabular={false} className="text-[14px] font-semibold text-ink [overflow-wrap:anywhere]">{f.name}</Ltr>
        <Ltr className="text-[12px] text-muted">{fileSize(f.size)}</Ltr>
      </span>
      <a href={fileUrl(f.id)} target="_blank" rel="noreferrer" className="inline-flex h-11 items-center gap-2 rounded-[12px] border border-strong px-5 text-[14px] font-semibold text-ink hover:bg-hover">
        <Icon name="report" size={18} />باز کن
      </a>
    </div>
  );
}

/** A video on the full screen: its controls and its sound, from where the inline one was. */
function FullVideo({ f, at }: { f: StripFile; at: number }) {
  const [failed, setFailed] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    if (at > 0) { try { v.currentTime = at; } catch { /* not seekable yet */ } }
    void v.play().catch(() => undefined);
  }, [at]);
  if (failed) return <VideoFailed f={f} className="max-w-md" />;
  return <video ref={video} src={fileUrl(f.id)} controls playsInline onError={() => setFailed(true)} className="max-h-full max-w-full rounded-[8px] bg-black" />;
}

/**
 * The full screen: a picture, a text file, a PDF, or a video with its controls and sound from where the inline one was. ⟨1.0.3⟩
 * [title]: what the bar names (an output's own title), the file's name under it; [onCloseAutoFocus]: where the focus goes back to.
 */
export function Viewer({ file, at = 0, onClose, title, onCloseAutoFocus, testid = 'file-viewer' }: {
  file: StripFile | null; at?: number; onClose: () => void; title?: ReactNode; onCloseAutoFocus?: (e: Event) => void; testid?: string;
}) {
  return (
    <D.Root open={!!file} onOpenChange={(v) => { if (!v) onClose(); }}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[70] bg-black/90" />
        <D.Content data-testid={testid} onCloseAutoFocus={onCloseAutoFocus} className="fixed inset-0 z-[71] flex flex-col outline-none">
          <div className="flex items-center gap-2 px-3 py-2 text-white">
            {title ? (
              <span className="flex min-w-0 flex-1 flex-col">
                <D.Title className="truncate text-[14px] font-semibold">{title}</D.Title>
                <bdi dir="ltr" className="truncate text-start text-[11px] text-white/70">{file?.name}</bdi>
              </span>
            ) : <D.Title className="min-w-0 flex-1 truncate text-[13px]"><bdi dir="ltr">{file?.name}</bdi></D.Title>}
            <D.Description className="sr-only">نمایش فایل</D.Description>
            {file ? <a href={fileUrl(file.id)} download={file.name} aria-label="دانلود" className="flex size-10 items-center justify-center rounded-full hover:bg-white/10"><Icon name="download" size={20} /></a> : null}
            <D.Close className="flex size-10 items-center justify-center rounded-full hover:bg-white/10" aria-label="بستن"><Icon name="close" size={22} /></D.Close>
          </div>
          <div className="flex min-h-0 flex-1 items-center justify-center p-3" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
            {!file ? null : isVideo(file) ? <FullVideo key={file.id} f={file} at={at} /> : isImage(file) ? (
              // eslint-disable-next-line @next/next/no-img-element -- a file of the owner's, served by the API
              <img src={fileUrl(file.id)} alt={file.name} className="max-h-full max-w-full rounded-[8px] object-contain" />
            ) : isPdf(file) ? <PdfBody f={file} /> : <TextBody f={file} />}
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

/**
 * The files of one output as a horizontal strip that scrolls. [under]: what sits under a tile (its publish action or where its
 * publication stands). A video plays under the strip, in place.
 */
export function FilesStrip({ files, label, under, className }: { files: StripFile[]; label: string; under?: (f: StripFile) => ReactNode; className?: string }) {
  const [playing, setPlaying] = useState<string | null>(null);
  const [full, setFull] = useState<{ id: string; at: number } | null>(null);
  if (!files.length) return null;
  const byId = (id: string | null | undefined) => files.find((x) => x.id === id) ?? null;
  const inline = byId(playing);
  return (
    <div className={cx('flex min-w-0 flex-col gap-2', className)} data-testid="files-strip">
      <ul aria-label={label} className="no-scrollbar -mx-1 flex gap-2.5 overflow-x-auto px-1 pb-0.5">
        {files.map((f) => (
          <li key={f.id} className="flex flex-none flex-col gap-1.5" style={{ width: TILE_W }}>
            <FileTile f={f} onOpen={() => (isVideo(f) ? setPlaying(f.id) : setFull({ id: f.id, at: 0 }))} />
            {under?.(f)}
          </li>
        ))}
      </ul>
      {inline ? <InlineVideo key={inline.id} f={inline} onClose={() => setPlaying(null)} onFull={(at) => { setPlaying(null); setFull({ id: inline.id, at }); }} /> : null}
      <Viewer file={byId(full?.id)} at={full?.at} onClose={() => setFull(null)} />
    </div>
  );
}

/**
 * One file large, in a frame of its network's shape ([ratio] width / height): the picture itself, or the video's poster; a tap opens
 * the full screen (a video with its controls and sound).
 */
export function HeroMedia({ f, cover, ratio, maxHeight = 420, label, className }: { f: StripFile; cover?: StripFile | null; ratio: number; maxHeight?: number; label?: string; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} data-hero-media={f.name} aria-label={label ?? `${isVideo(f) ? 'پخش' : 'نمایش'} ${f.name}`}
        className={cx('relative mx-auto flex w-full items-center justify-center overflow-hidden rounded-[16px] bg-tile shadow-[inset_0_0_0_1px_var(--hq-line-divider)]', className)}
        style={{ aspectRatio: String(ratio), maxWidth: Math.round(maxHeight * ratio) }}>
        {/* A reel's cover is what the feed shows: it stands for the video until he plays it. */}
        {cover && isVideo(f) && isImage(cover) ? <><FileFace f={cover} /><PlaySign size={52} />{f.duration_s ? <Ltr className="absolute bottom-1.5 start-1.5 rounded-full bg-black/65 px-1.5 text-[10px] leading-4 text-white">{clock(f.duration_s)}</Ltr> : null}</> : <FileFace f={f} sign={52} />}
      </button>
      <Viewer file={open ? f : null} onClose={() => setOpen(false)} />
    </>
  );
}
