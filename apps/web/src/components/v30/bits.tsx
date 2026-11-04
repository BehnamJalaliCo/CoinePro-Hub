'use client';

// ⟨1.12⟩ Shared pieces of §30's screens: the states, a step's kind badge, and a step's output shown properly (markdown text, an audio
// player, an image, a video, JSON as a table), the same for a run page and for «آزمایش همین مرحله».

import { Icon } from '@/components/icon';
import { Md } from '@/components/ui/md';
import { Pill } from '@/components/ui/primitives';
import { fileUrl } from '@/lib/api/v13';
import { LINE_STATE_FA, RUN_STATE_FA, stepKind, type LineState, type RunState, type StepOutput } from '@/lib/api/v30';
import { cx } from '@/lib/format';
import { FaText } from '@/components/v29/text';

export { FaPara, FaText, fig } from '@/components/v29/text';

export function RunStatePill({ state }: { state: RunState | string }) {
  const s = RUN_STATE_FA[state as RunState] ?? { fa: state, tone: 'neutral' as const };
  return <Pill tone={s.tone} dot={!s.live} live={s.live}>{s.fa}</Pill>;
}
export function LineStatePill({ state }: { state: LineState | string }) {
  const s = LINE_STATE_FA[state as LineState] ?? { fa: state, tone: 'neutral' as const };
  return <Pill tone={s.tone} dot>{s.fa}</Pill>;
}

/** A step kind's round icon. */
export function KindIcon({ kind, className }: { kind: string; className?: string }) {
  return (
    <span className={cx('flex size-10 flex-none items-center justify-center rounded-[12px] bg-tile text-silver-ink', className)} title={stepKind(kind).fa}>
      <Icon name={stepKind(kind).icon} size={20} />
    </span>
  );
}

const EXT = {
  audio: /\.(m4a|mp3|wav|ogg|opus|aac|webm)(\?|$)/i, video: /\.(mp4|mov|m4v)(\?|$)/i, image: /\.(png|jpe?g|webp|gif|avif)(\?|$)/i,
};
export type MediaKind = 'audio' | 'video' | 'image' | 'other';
/** What a file is, from the hub's hint (`data.mime`/`data.kind`), its name, or the step that made it. */
export function mediaKindOf(id: string, step: string, data?: Record<string, unknown> | null): MediaKind {
  const hint = String(data?.mime ?? data?.kind ?? '');
  if (hint.startsWith('audio') || hint === 'audio') return 'audio';
  if (hint.startsWith('video') || hint === 'video') return 'video';
  if (hint.startsWith('image') || hint === 'image') return 'image';
  for (const k of ['audio', 'video', 'image'] as const) if (EXT[k].test(id)) return k;
  return step === 'tts' ? 'audio' : step === 'render' ? 'video' : step === 'cover' ? 'image' : 'other';
}

const cell = (v: unknown): string => (v == null ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));
const HIDDEN = new Set(['mime', 'kind']);

/** JSON as a table: a key and its value, a nested value kept as small JSON. */
export function DataTable({ data }: { data: Record<string, unknown> }) {
  const rows = Object.entries(data).filter(([k]) => !HIDDEN.has(k));
  if (!rows.length) return null;
  return (
    <div className="overflow-x-auto rounded-[10px] bg-tile">
      <table className="w-full border-collapse text-[12px]" aria-label="داده‌ی خروجی">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="border-t border-div first:border-0 align-top">
              <th className="w-[34%] px-3 py-2 text-right font-semibold text-sec"><span dir="ltr" className="inline-block">{k}</span></th>
              <td className="px-3 py-2 text-ink">{typeof v === 'object' && v !== null ? <code dir="ltr" className="inline-block break-all text-[11px] text-sec">{cell(v)}</code> : <FaText text={cell(v)} />}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A step's output: its text as markdown, each file by its kind, its data as a table. */
export function OutputView({ out, kind }: { out: StepOutput | null | undefined; kind: string }) {
  if (!out) return null;
  const ids = [...new Set([out.file_id, ...(out.files ?? [])].filter((x): x is string => !!x))];
  const hasData = out.data && Object.keys(out.data).filter((k) => !HIDDEN.has(k)).length > 0;
  if (!out.text && !ids.length && !hasData) return null;
  return (
    <div className="flex flex-col gap-3" aria-label="خروجی">
      {out.text ? <Md text={out.text} className="text-[13px] leading-7" /> : null}
      {ids.map((id) => {
        const k = mediaKindOf(id, kind, out.data);
        const src = fileUrl(id);
        return k === 'audio' ? <audio key={id} controls preload="none" src={src} className="w-full" aria-label="صدا" />
          : k === 'video' ? <video key={id} controls preload="metadata" src={src} poster={fileUrl(id, 'poster')} className="max-h-[420px] w-full rounded-[12px] bg-tile" aria-label="ویدیو" />
          : k === 'image' ? <img key={id} src={src} alt="تصویر خروجی" className="max-h-[420px] w-auto max-w-full self-start rounded-[12px] bg-tile object-contain" />
          : <a key={id} href={src} download className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-gold-ink hover:underline"><Icon name="download" size={16} />دانلود فایل</a>;
      })}
      {hasData ? <DataTable data={out.data} /> : null}
    </div>
  );
}
