'use client';

/**
 * ⟨1.0.1⟩ §51 «لغو»: a post that is set for an hour (or still on its way) is taken back from the app.
 *
 * Wherever a publication is listed, one that is not out yet gets a quiet «لغو». It asks once, in place, and the hub's answer takes the
 * row's place: «لغو شد», or the same state with «در حال لغو» while the other server is asked. One that is out already cannot be taken
 * back here, and the hub's own words say so on the row. On a hub before §51 the action hides itself after the first try.
 */
import { useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { notServed } from '@/lib/api/v28';
import type { SessionPublish } from '@/lib/api/v44';
import { cancellable, markAbsent, useAbsent, useCancelPublish } from '@/lib/api/v47';

/** The two pieces a row needs: the quiet button beside its state, and what goes under the row (the question, or why it was refused). */
export function useCancel(p: SessionPublish | null): { button: ReactNode; under: ReactNode } {
  const toast = useToast();
  const cancel = useCancelPublish();
  const absent = useAbsent('cancel');
  const [asking, setAsking] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const can = !!p && cancellable(p) && !absent;
  const go = () => {
    if (!p?.job) return;
    cancel.mutate(p.job, {
      onSuccess: (out) => {
        setAsking(false);
        toast({
          tone: out.state === 'cancelled' ? 'ok' : 'info',
          text: out.state === 'cancelled' ? 'لغو شد؛ منتشر نمیشود.' : out.state === 'published' ? 'پیش از لغو منتشر شده بود.' : out.note_fa ?? 'لغو در راه است؛ نتیجه همین‌جا می‌آید.',
        });
      },
      onError: (e) => {
        setAsking(false);
        if (notServed(e)) { markAbsent('cancel'); toast({ tone: 'info', text: 'لغو از داخل اپ بعد از به‌روزرسانی ستاد فعال میشود.' }); return; }
        // out already, failed, or its file still on its way: said on the row, in the hub's words
        if (e instanceof ApiError && e.status === 409) setRefused(e.messageFa);
        else toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'لغو نشد؛ دوباره بزن.' });
      },
    });
  };
  const button = can && !asking
    ? <button type="button" onClick={() => { setRefused(null); setAsking(true); }} className="h-8 flex-none rounded-[8px] px-2 text-[12px] font-semibold text-sec hover:bg-hover hover:text-ink">لغو</button>
    : null;
  const under = can && asking ? (
    <div role="group" aria-label="لغو انتشار" className="flex flex-wrap items-center gap-2">
      <span className="min-w-0 flex-1 text-[12px] text-sec">این انتشار لغو شود؟</span>
      <Button size="sm" variant="danger" loading={cancel.isPending} onClick={go}>لغو کن</Button>
      <Button size="sm" variant="ghost" disabled={cancel.isPending} onClick={() => setAsking(false)}>نه</Button>
    </div>
  ) : refused ? <p role="status" className="text-[11px] leading-5 text-neg" data-cancel-refused>{refused}</p> : null;
  return { button, under };
}

/** What the hub notes on a publication that is neither failed nor waiting (those say it in their own line): «در حال لغو», «لغو انجام نشد (…)». */
export const publishNote = (p: SessionPublish | null): string | null =>
  (p && p.note_fa && (p.state === 'scheduled' || p.state === 'publishing' || p.state === 'published' || p.state === 'cancelled') ? p.note_fa : null);
