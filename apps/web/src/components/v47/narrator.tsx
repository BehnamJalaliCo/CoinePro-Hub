'use client';

/**
 * ⟨1.0.1⟩ §48 «گوینده‌ی محتوا»: a company's narrator, set once.
 *
 * The owner's order was «گوینده یک بار برای همیشه تنظیم شود». The voice and its style used to be words a model passed along each time;
 * now they are the company's own, and every reel and video of that company is spoken with them. One row says who the narrator is and
 * opens the picker; the same row sits under a working group's member and on the company's own page. The hub's speaker has no key: when
 * it has fallen out of its account, one calm line says so (his one sign-in is the only step that is his). Nothing on a hub before §48.
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaText } from '@/components/v29/text';
import { ApiError } from '@/lib/api/client';
import { AISTUDIO_OUT_FA, GENDER_FA, NARRATOR_UNSET_FA, STYLE_MAX, useNarrator, useSetNarrator, type Narrator } from '@/lib/api/v47';
import { cx } from '@/lib/format';

const FIELD = 'w-full rounded-[10px] border border-strong bg-tile p-3 text-[14px] leading-7 text-ink outline-none transition-colors placeholder:text-muted focus:border-gold-ink';

/** The row: who speaks for this company, and the way to the picker. */
export function NarratorRow({ company, nameFa, className }: { company: string; nameFa: string; className?: string }) {
  const q = useNarrator(company);
  const [open, setOpen] = useState(false);
  const n = q.data;
  if (!n) return null;
  const style = (n.style_fa ?? '').trim();
  return (
    <div className={cx('flex flex-col gap-1', className)} data-narrator={company}>
      <div className="flex items-center gap-3">
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-[12px] text-sec">گوینده‌ی محتوا</span>
          <span className={cx('truncate text-[11px]', n.set ? 'text-gold-ink' : 'text-muted')} data-narrator-line>
            {n.set ? <><bdi className="fig">{n.voice}</bdi>{style ? ` · ${style}` : ''}</> : NARRATOR_UNSET_FA}
          </span>
        </span>
        <button type="button" aria-haspopup="dialog" aria-label={`گوینده‌ی محتوای ${nameFa}`} onClick={() => setOpen(true)} className="h-8 flex-none rounded-[8px] px-2 text-[12px] font-semibold text-gold-ink hover:bg-gold-soft">
          {n.set ? 'عوض کن' : 'انتخاب کن'}
        </button>
      </div>
      {n.aistudio === 'signed_out' ? <p className="text-[11px] leading-5 text-muted" data-aistudio="signed_out">{AISTUDIO_OUT_FA}</p> : null}
      {open ? <NarratorSheet n={n} company={company} nameFa={nameFa} onClose={() => setOpen(false)} /> : null}
    </div>
  );
}

/** The same row as a card of the company's own page; nothing when the hub does not know narrators. */
export function NarratorCard({ company, nameFa }: { company: string; nameFa: string }) {
  const q = useNarrator(company);
  if (!q.data) return null;
  return <Card className="p-4" aria-label="گوینده‌ی محتوا"><NarratorRow company={company} nameFa={nameFa} /></Card>;
}

function NarratorSheet({ n, company, nameFa, onClose }: { n: Narrator; company: string; nameFa: string; onClose: () => void }) {
  const toast = useToast();
  const save = useSetNarrator(company);
  // the one he chose before; with none yet, nothing is chosen for him
  const [voice, setVoice] = useState<string | null>(n.set ? n.voice ?? null : null);
  const [style, setStyle] = useState(n.set ? n.style_fa ?? '' : '');
  const [refused, setRefused] = useState<string | null>(null);
  const voices = n.voices ?? [];
  const go = () => {
    if (!voice) return;
    save.mutate({ voice, style_fa: style }, {
      onSuccess: () => { toast({ tone: 'ok', text: 'گوینده ثبت شد؛ از این به بعد همه با همین صدا گفته میشود.' }); onClose(); },
      onError: (e) => { if (e instanceof ApiError && e.status === 422) setRefused(e.messageFa); else toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد؛ دوباره بزن.' }); },
    });
  };
  return (
    <Sheet
      open onOpenChange={(v) => { if (!v) onClose(); }} title="گوینده‌ی محتوا" description={`${nameFa} · یک بار انتخاب میشود و همه‌ی ویدیوها با همین صدا گفته میشوند`} width={460}
      footer={<Button variant="primary" size="lg" icon="seal" className="w-full" disabled={!voice} loading={save.isPending} onClick={go}>ثبت</Button>}
    >
      <div className="flex flex-col gap-4">
        {n.aistudio === 'signed_out' ? <p className="rounded-[10px] bg-tile px-3 py-2 text-[12px] leading-6 text-sec">{AISTUDIO_OUT_FA}</p> : null}
        <div className="flex flex-col gap-2">
          <span className="text-[12px] font-semibold text-sec" id="narrator-voices">صدا</span>
          {voices.length ? (
            <div role="radiogroup" aria-labelledby="narrator-voices" className="grid grid-cols-2 gap-1.5">
              {voices.map((v) => {
                const on = voice === v.name;
                return (
                  <button
                    key={v.name} type="button" role="radio" aria-checked={on} onClick={() => { setVoice(v.name); setRefused(null); }}
                    className={cx('flex min-w-0 flex-col items-start gap-0.5 rounded-[10px] px-3 py-2 text-start transition-colors', on ? 'tahrir bg-gold-soft' : 'border border-strong hover:bg-hover')}
                  >
                    <bdi className={cx('fig max-w-full truncate text-[13px] font-semibold', on ? 'text-gold-ink' : 'text-ink')}>{v.name}</bdi>
                    <span className="max-w-full truncate text-[11px] text-muted">{[GENDER_FA[v.gender], v.trait_fa].filter(Boolean).join(' · ')}</span>
                  </button>
                );
              })}
            </div>
          ) : <p className="text-[13px] text-muted">فهرست صداها هنوز نرسیده است.</p>}
        </div>
        <label className="flex flex-col gap-2">
          <span className="text-[12px] font-semibold text-sec">سبک گفتن</span>
          <textarea value={style} onChange={(e) => { setStyle(e.target.value.slice(0, STYLE_MAX)); setRefused(null); }} rows={2} dir="auto" maxLength={STYLE_MAX} placeholder="آرام و مطمئن، مثل گوینده‌ی خبر" className={FIELD} />
        </label>
        {refused ? <p role="alert" className="text-[12px] leading-5 text-neg"><FaText text={refused} /></p> : null}
      </div>
    </Sheet>
  );
}
