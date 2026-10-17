'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { IconButton, Spinner } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { transcribe } from '@/lib/api/v13';
import { RECORDER_ERROR, clock, useRecorder } from '@/lib/recorder';
import { cx } from '@/lib/format';
import { AttachmentTray, PICKER_ACCEPT, useAttachments } from './attachments';

export const MAX_VOICE_S = 15 * 60;

/** Live loudness bars while the owner speaks; the newest bar sits at the reading end. */
export function Waveform({ levels, className, tone = 'gold' }: { levels: number[]; className?: string; tone?: 'gold' | 'neg' }) {
  return (
    <div aria-hidden className={cx('flex items-center justify-end gap-[3px] overflow-hidden', className)}>
      {levels.map((l, i) => (
        <span key={i} className={cx('w-[3px] flex-none rounded-full transition-[height] duration-100', tone === 'gold' ? 'bg-gold-ink' : 'bg-neg')} style={{ height: `${Math.max(10, Math.round(l * 100))}%`, opacity: 0.35 + 0.65 * Math.min(1, l * 1.6) }} />
      ))}
    </div>
  );
}

export type VoiceResult = { text: string; fileId: string; seconds: number };

/**
 * Speak → exact Persian text (contract §17.2). The text lands in the caller's field for the owner to read and fix
 * before anything is sent; the recording travels with it so what was said can always be replayed.
 * When the speech service cannot help, `onFallback` gets the audio itself.
 */
export function useVoiceInput({ purpose, onText, onFallback }: { purpose: 'message' | 'order' | 'note'; onText: (v: VoiceResult) => void; onFallback?: (audio: File) => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const ctrl = useRef<AbortController | null>(null);
  const rec = useRecorder({
    maxSeconds: MAX_VOICE_S,
    onFinish: (audio, seconds) => {
      if (seconds < 0.6) { toast({ tone: 'info', text: 'صدایی ضبط نشد؛ دکمه را بزن و بعد حرف بزن.' }); return; }
      const c = new AbortController();
      ctrl.current = c;
      setBusy(true);
      transcribe(audio, purpose, c.signal)
        .then((t) => {
          if (!t.text.trim()) { toast({ tone: 'info', text: 'حرفی شنیده نشد؛ دوباره بگو.' }); return; }
          onText({ text: t.text.trim(), fileId: t.file_id, seconds: t.duration_s || seconds });
        })
        .catch((e: unknown) => {
          if (c.signal.aborted) return;
          const ext = audio.type.includes('mp4') ? 'm4a' : audio.type.includes('ogg') ? 'ogg' : 'webm';
          if (onFallback) {
            onFallback(new File([audio], `voice-${Date.now()}.${ext}`, { type: audio.type }));
            toast({ tone: 'info', text: `${e instanceof ApiError ? e.messageFa : 'متن ساخته نشد.'} صدا به‌عنوان پیوست اضافه شد.` });
          } else {
            toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'متن ساخته نشد؛ دوباره بگو.' });
          }
        })
        .finally(() => { setBusy(false); ctrl.current = null; });
    },
  });
  const { state, reset } = rec;
  useEffect(() => {
    if (state === 'denied' || state === 'unsupported' || state === 'failed') {
      toast({ tone: 'error', text: RECORDER_ERROR[state] });
      reset();
    }
  }, [state, reset, toast]);
  const abort = useCallback(() => { ctrl.current?.abort(); setBusy(false); }, []);
  return { ...rec, transcribing: busy, abort, active: rec.state === 'recording' || rec.state === 'asking' || busy };
}

type Props = {
  placeholder: string;
  purpose?: 'message' | 'order' | 'note';
  /** Resolve when sent (the composer clears); throw to keep everything as it is. */
  onSend: (v: { body: string; attachments: string[] }) => Promise<void>;
  sending?: boolean;
  allowFiles?: boolean;
  maxLength?: number;
  label?: string;
};

/** The owner's composer everywhere: words, voice that becomes words, photos, films and PDFs. */
export function Composer({ placeholder, purpose = 'message', onSend, sending, allowFiles = true, maxLength = 10000, label = 'پیام' }: Props) {
  const [text, setText] = useState('');
  const [voice, setVoice] = useState<VoiceResult | null>(null);
  const [drag, setDrag] = useState(false);
  const files = useAttachments(10);
  const pick = useRef<HTMLInputElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const v = useVoiceInput({
    purpose,
    onText: (r) => {
      setText((t) => (t.trim() ? `${t.trimEnd()} ${r.text}` : r.text));
      setVoice(r);
      requestAnimationFrame(() => area.current?.focus());
    },
    onFallback: allowFiles ? (f) => void files.add([f]) : undefined,
  });
  const ready = (text.trim().length > 0 || files.ids.length > 0) && !files.uploading && !sending && !v.active;

  const submit = async () => {
    if (!ready) return;
    const attachments = [...files.ids, ...(voice ? [voice.fileId] : [])];
    try {
      await onSend({ body: text.trim(), attachments });
      setText('');
      setVoice(null);
      files.clear();
    } catch {
      // The caller reported it; keep the draft.
    }
  };

  return (
    <div
      className={cx('flex flex-col rounded-[16px] border bg-card p-2 transition-colors', drag ? 'border-gold-ink bg-gold-soft' : 'border-strong focus-within:border-gold-ink')}
      onDragOver={allowFiles ? (e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDrag(true); } } : undefined}
      onDragLeave={() => setDrag(false)}
      onDrop={allowFiles ? (e) => { e.preventDefault(); setDrag(false); void files.add(e.dataTransfer.files); } : undefined}
    >
      <AttachmentTray items={files.items} onRemove={files.remove} onRetry={files.retry} />
      {voice ? (
        <div className="flex items-center gap-2 px-2 pb-1 text-[12px] text-sec">
          <Icon name="mic" size={14} />
          <span>صدای اصلی <span className="fig">{clock(voice.seconds)}</span> همراه پیام میرود</span>
          <button type="button" onClick={() => setVoice(null)} className="text-muted underline-offset-2 hover:text-ink hover:underline">نفرست</button>
        </div>
      ) : null}
      <form onSubmit={(e) => { e.preventDefault(); void submit(); }} className="flex items-end gap-1.5">
        {allowFiles && !v.active ? (
          <>
            <input ref={pick} type="file" multiple accept={PICKER_ACCEPT} hidden onChange={(e) => { if (e.target.files) void files.add(e.target.files); e.target.value = ''; }} />
            <IconButton icon="attach" label="پیوست عکس، فیلم یا PDF" size={44} onClick={() => pick.current?.click()} />
          </>
        ) : null}
        {v.state === 'recording' || v.state === 'asking' ? (
          <>
            <IconButton icon="close" label="لغو ضبط" size={44} onClick={v.cancel} />
            <div className="flex h-11 min-w-0 flex-1 items-center gap-3 px-1" role="status" aria-label="در حال ضبط">
              <span className="size-2.5 flex-none rounded-full bg-neg" style={{ animation: 'hq-live 1.2s infinite' }} />
              <Waveform levels={v.levels} className="h-8 min-w-0 flex-1" />
              <span className="fig w-12 flex-none text-left text-[13px] text-sec">{clock(v.elapsed)}</span>
            </div>
            <button type="button" onClick={v.finish} aria-label="تمام؛ به متن تبدیل کن" title="تمام؛ به متن تبدیل کن" className="flex size-11 flex-none items-center justify-center rounded-full bg-gold text-on-gold hover:bg-gold-bright">
              <Icon name="stop" size={18} />
            </button>
          </>
        ) : v.transcribing ? (
          <>
            <IconButton icon="close" label="لغو" size={44} onClick={v.abort} />
            <div className="flex h-11 min-w-0 flex-1 items-center gap-2 px-1 text-[13px] text-sec" role="status">
              <Spinner size={16} className="text-gold-ink" />در حال تبدیل به متن فارسی…
            </div>
          </>
        ) : (
          <>
            <textarea
              ref={area}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); } }}
              onPaste={allowFiles ? (e) => { const fs = [...e.clipboardData.files]; if (fs.length) { e.preventDefault(); void files.add(fs); } } : undefined}
              rows={Math.min(6, Math.max(1, text.split('\n').length))}
              maxLength={maxLength}
              placeholder={placeholder}
              aria-label={label}
              className="min-h-11 min-w-0 flex-1 resize-none bg-transparent px-2 py-2.5 text-[15px] leading-6 text-ink outline-none placeholder:text-muted"
            />
            <IconButton icon="mic" label="بگو؛ به متن فارسی تبدیل میشود" size={44} onClick={() => void v.start()} />
            <button type="submit" disabled={!ready} aria-label="بفرست" title={files.uploading ? 'صبر کن بارگذاری تمام شود' : undefined} className="flex size-11 flex-none items-center justify-center rounded-full bg-gold text-on-gold transition-colors hover:bg-gold-bright disabled:bg-disabled-fill disabled:text-disabled">
              {sending ? <Spinner size={18} /> : <Icon name="send" size={20} mirror />}
            </button>
          </>
        )}
      </form>
    </div>
  );
}
