'use client';

import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { createContext, useContext, useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Waveform, useVoiceInput, type VoiceResult } from '@/components/media/composer';
import { Button, Spinner } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { MdInline } from '@/components/ui/md';
import { Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useEmployees } from '@/lib/api/hooks';
import { sendOrder, useOrders, type OrderOut, type OrderRoute } from '@/lib/api/v13';
import { clock } from '@/lib/recorder';
import { applyPlayer, optionOf, recogniseOption, type PlayerOption } from '@/lib/players';
import { PlayerPicker } from '@/components/work/player';
import { ago, cx } from '@/lib/format';

const KIND: Record<OrderRoute['kind'], { fa: string; icon: 'task' | 'code' | 'meeting' | 'advisor' }> = {
  work: { fa: 'کار', icon: 'task' },
  code: { fa: 'کارگاه کد', icon: 'code' },
  meeting: { fa: 'جلسه', icon: 'meeting' },
  question: { fa: 'پرسش', icon: 'advisor' },
};

function routeHref(r: OrderRoute): string | null {
  if (r.session_ref) return `/workshop/${r.session_ref}`;
  if (r.decision_ref) return `/cartable?ref=${r.decision_ref}`;
  if (r.work_ref) return `/work/${r.work_ref}`;
  if (r.kind === 'question') return '/advisor';
  return null;
}

/** Where an order went: company, who, what kind — and a way in. */
function Route({ r, onGo }: { r: OrderRoute; onGo?: () => void }) {
  const { data: employees } = useEmployees({});
  const who = employees?.items.find((e) => e.code === r.to)?.title_fa ?? r.to;
  const href = routeHref(r);
  const ref = r.session_ref ?? r.decision_ref ?? r.work_ref;
  const body = (
    <>
      <span className="text-sec"><CompanyMark code={r.company} height={13} mono /></span>
      <span className="text-sec"><Icon name={KIND[r.kind].icon} size={15} /></span>
      <span className="text-ink">{KIND[r.kind].fa}</span>
      <span className="text-muted">←</span>
      <span className="truncate text-ink">{who}</span>
      {ref ? <span className="fig text-muted">{ref}</span> : null}
    </>
  );
  const cls = 'inline-flex h-8 max-w-full items-center gap-1.5 rounded-full bg-tile px-3 text-[12px]';
  return href ? <Link href={href} onClick={onGo} className={cx(cls, 'hover:bg-hover')}>{body}</Link> : <span className={cls}>{body}</span>;
}

type Phase = 'ready' | 'review' | 'sent';

/** Opens the voice order from anywhere in the app (top bar, command center, palette). */
export const VoiceOrderContext = createContext<() => void>(() => {});
export const useVoiceOrder = () => useContext(VoiceOrderContext);

/**
 * The owner speaks an order; the hub routes it (contract §17.4): rules first, then the light model, then the advisor.
 * The owner reads the exact text before it goes, and sees where it went.
 */
export function VoiceOrder({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const orders = useOrders();
  const [phase, setPhase] = useState<Phase>('ready');
  const [text, setText] = useState('');
  const [voice, setVoice] = useState<VoiceResult | null>(null);
  const [out, setOut] = useState<OrderOut | null>(null);
  const [busy, setBusy] = useState(false);
  // ⟨1.9⟩ §27.1: «با جمنای / با جی‌پی‌تی / شورا» in the words picks the player; the owner sees what was heard and can change it.
  const heard = useMemo(() => recogniseOption(text), [text]);
  const [chosen, setChosen] = useState<PlayerOption | null>(null);
  const option = chosen ?? heard?.option ?? optionOf('auto');
  const v = useVoiceInput({ purpose: 'order', onText: (r) => { setText(r.text); setVoice(r); setPhase('review'); } });
  const recording = v.state === 'recording' || v.state === 'asking';

  const reset = () => { setPhase('ready'); setText(''); setVoice(null); setOut(null); setChosen(null); };
  const close = (x: boolean) => { if (!x) { v.cancel(); v.abort(); reset(); } onOpenChange(x); };
  const send = async () => {
    setBusy(true);
    try {
      const o = await sendOrder(text.trim(), voice ? 'voice' : 'text', voice?.fileId ?? null);
      // The hub read the words; where the owner chose otherwise, the works it made follow the owner's choice.
      const changed = await applyPlayer(o, option);
      if (changed) toast({ tone: 'info', text: `بازیکن ${changed.toLocaleString('fa-IR')} کار به «${option.fa}» تغییر کرد.` });
      setOut(o);
      setPhase('sent');
      for (const k of ['orders', 'work', 'planner', 'workshop', 'decisions', 'inbox']) void qc.invalidateQueries({ queryKey: [k] });
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'فرمان نرسید.' });
    } finally {
      setBusy(false);
    }
  };

  const footer = phase === 'review'
    ? <Button variant="primary" icon="send" className="w-full" disabled={text.trim().length < 3} loading={busy} onClick={send}>بفرست</Button>
    : phase === 'sent'
      ? <Button variant="secondary" icon="mic" className="w-full" onClick={reset}>فرمان بعدی</Button>
      : undefined;

  return (
    <Sheet open={open} onOpenChange={close} title="فرمان صوتی" description="بگو چه میخواهی؛ خودشان میدانند کجا و به دست چه کسی انجام شود." width={540} footer={footer}>
      <div className="flex flex-col gap-6">
        {phase === 'ready' ? (
          <div className="flex flex-col items-center gap-4 py-4">
            <button
              type="button"
              onClick={() => (recording ? v.finish() : void v.start())}
              disabled={v.transcribing}
              aria-label={recording ? 'تمام؛ به متن تبدیل کن' : 'شروع ضبط فرمان'}
              className="relative flex size-28 items-center justify-center rounded-full bg-gold text-on-gold shadow-[0_8px_32px_rgba(216,168,72,.35)] transition-transform active:scale-95 disabled:opacity-70"
            >
              {recording ? <span aria-hidden className="absolute inset-0 rounded-full bg-gold" style={{ animation: 'hq-ring 1.6s ease-out infinite' }} /> : null}
              <span className="relative">{v.transcribing ? <Spinner size={34} /> : <Icon name={recording ? 'stop' : 'mic'} size={40} />}</span>
            </button>
            {recording ? (
              <div className="flex w-full max-w-sm flex-col items-center gap-2">
                <Waveform levels={v.levels} className="h-10 w-full justify-center" />
                <div className="flex items-center gap-3 text-[13px] text-sec">
                  <span className="fig">{clock(v.elapsed)}</span>
                  <button type="button" onClick={v.cancel} className="text-muted hover:text-ink">لغو</button>
                </div>
              </div>
            ) : v.transcribing ? (
              <p className="text-[14px] text-sec">در حال تبدیل به متن فارسی…</p>
            ) : (
              <div className="flex flex-col items-center gap-1 text-center">
                <p className="text-[15px] font-semibold text-ink">بزن و بگو؛ دوباره بزن تا تمام شود</p>
                <p className="max-w-sm text-[13px] leading-6 text-sec">مثلاً «به مدیر فنی FX بگو کندی ثبت‌نام را تا فردا ظهر اصلاح کند». کار، کارگاه کد، جلسه یا پرسش از مشاور؛ مسیرش را هاب پیدا میکند.</p>
                <button type="button" onClick={() => setPhase('review')} className="pt-2 text-[13px] font-semibold text-gold-ink hover:underline">به‌جایش مینویسم</button>
              </div>
            )}
          </div>
        ) : phase === 'review' ? (
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-[13px] text-sec">{voice ? 'متن دقیق آنچه گفتی؛ اگر لازم است اصلاح کن' : 'فرمان'}</span>
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} maxLength={4000} autoFocus={!voice}
                className="w-full rounded-[12px] border border-strong bg-tile px-3 py-3 text-[15px] leading-7 text-ink outline-none focus:border-gold-ink" />
            </label>
            <PlayerPicker value={option} onChange={setChosen} heard={heard} />
            <div className="flex flex-wrap items-center gap-3 text-[12px] text-sec">
              {voice ? <span className="flex items-center gap-1.5"><Icon name="mic" size={14} />صدای اصلی <span className="fig">{clock(voice.seconds)}</span> با فرمان میماند</span> : null}
              <span className="flex-1" />
              <button type="button" onClick={() => { reset(); void v.start(); }} className="flex items-center gap-1 font-semibold text-gold-ink hover:underline"><Icon name="mic" size={14} />دوباره بگو</button>
            </div>
          </div>
        ) : out ? (
          <div className="flex flex-col gap-3 rounded-[14px] bg-tile p-4">
            <div className="flex items-center gap-2">
              <span className="text-gold-ink"><Icon name="seal" size={20} active /></span>
              <span className="flex-1 text-[14px] font-semibold">فرمان <span className="fig">{out.ref}</span> رسید</span>
            </div>
            <p className="text-[13px] leading-6 text-sec"><MdInline text={out.summary_fa} /></p>
            <div className="flex flex-col items-start gap-1.5">{out.routes.map((r, i) => <Route key={i} r={r} onGo={() => close(false)} />)}</div>
          </div>
        ) : null}

        <section className="flex flex-col gap-2 border-t border-div pt-4" aria-label="فرمان‌های اخیر">
          <h3 className="text-[13px] font-semibold text-sec">فرمان‌های اخیر</h3>
          {orders.isLoading ? <Skeleton className="h-20" /> : !orders.data?.items.length ? <p className="text-[12px] text-muted">هنوز فرمانی نداده‌ای.</p> : (
            <ul className="flex flex-col gap-3">
              {orders.data.items.slice(0, 5).map((o) => (
                <li key={o.ref} className="flex flex-col gap-1.5">
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 text-muted"><Icon name={o.source === 'voice' ? 'mic' : 'edit'} size={14} /></span>
                    <p className="line-clamp-2 min-w-0 flex-1 text-[13px] leading-6 text-ink"><MdInline text={o.text} /></p>
                    <span className="flex-none text-[11px] text-muted">{ago(o.created_at)}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5 ps-6">{o.routes.map((r, i) => <Route key={i} r={r} onGo={() => close(false)} />)}</div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Sheet>
  );
}
