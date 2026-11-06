'use client';

// ⟨1.14⟩ Contract §32.3–§32.4: what the owner says becomes work only through a card he taps. A card runs the existing route with that
// route's own confirmation and step-up («اجرا کن»), can be edited first («ویرایش»), or put aside («نه»).

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Pill } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import Link from 'next/link';
import { FaPara, FaText } from '@/components/v29/text';
import { errText, field } from '@/components/v31/kit';
import { ApiError } from '@/lib/api/client';
import { stepUp } from '@/lib/auth';
import { CARD_FA, useTalkActions, type TalkCard } from '@/lib/api/v32';
import { cx } from '@/lib/format';

type Task = { title_fa: string; company?: string; department?: string; due?: string };
const STATE_FA = { offered: '', done: 'انجام شد', dismissed: 'کنار گذاشته شد', failed: 'نشد' } as const;
// ⟨1.17⟩ The owner never reads a ref: what a card made is a link in words (an order is its session, a decision its card in the cartable).
const linkOf = (ref: string): { href: string; fa: string } | null => (/^F-/.test(ref) ? { href: `/s/${ref}`, fa: 'جلسه‌اش را باز کن' } : /^D-/.test(ref) ? { href: `/cartable?ref=${ref}`, fa: 'کارتش در کارتابل' } : null);

/** One card under an answer. [onChanged] lets the page refresh the conversation after a run. */
export function TalkCardView({ card }: { card: TalkCard }) {
  const act = useTalkActions();
  const toast = useToast();
  const kind = CARD_FA[card.kind] ?? CARD_FA.order;
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(typeof card.payload.text === 'string' ? card.payload.text : '');
  const [tasks, setTasks] = useState<Task[]>(Array.isArray(card.payload.tasks) ? (card.payload.tasks as Task[]) : []);
  const [made, setMade] = useState<string[]>(card.made ?? []);
  const [state, setState] = useState(card.state);
  const [reason, setReason] = useState(card.reason_fa);

  const payload = (): Record<string, unknown> | undefined => {
    const p: Record<string, unknown> = {};
    if (card.kind === 'minutes' && tasks.length) p.tasks = tasks;
    if (text && text !== card.payload.text) p.text = text;
    return Object.keys(p).length ? p : undefined;
  };
  const run = async () => {
    const send = () => act.run.mutateAsync({ id: card.id, payload: payload() });
    try {
      let r: { made: string[] };
      try { r = await send(); } catch (e) {
        // The card keeps the step-up of the route it runs: the hub asks, the passkey answers, the call is repeated once.
        if (!(e instanceof ApiError && e.status === 403 && e.code === 'step_up_required')) throw e;
        await stepUp('talk.card', card.id);
        r = await send();
      }
      setMade(r.made ?? []); setState('done'); setReason(null); setEditing(false);
    } catch (e) {
      setState('failed'); setReason(errText(e, 'اجرا نشد؛ دوباره بزن.'));
      toast({ tone: 'error', text: errText(e, 'اجرا نشد.') });
    }
  };
  const dismiss = () => act.dismiss.mutate(card.id, { onSuccess: () => setState('dismissed'), onError: (e) => toast({ tone: 'error', text: errText(e, 'انجام نشد.') }) });
  const open = state === 'offered' || state === 'failed';
  const setTask = (i: number, patch: Partial<Task>) => setTasks((ts) => ts.map((t, j) => (j === i ? { ...t, ...patch } : t)));

  return (
    <section aria-label={`کارت ${kind.fa}: ${card.title_fa}`} data-kind={card.kind} data-state={state}
      className={cx('flex flex-col gap-2 rounded-[14px] border p-3.5', state === 'done' ? 'border-div bg-pos-soft' : 'border-div bg-tile')}>
      <header className="flex items-center gap-2">
        <span className="text-gold-ink"><Icon name={kind.icon} size={18} /></span>
        <Pill tone="neutral">{kind.fa}</Pill>
        <b className="min-w-0 flex-1 text-[14px] leading-6 text-ink"><FaText text={card.title_fa} /></b>
        {STATE_FA[state] ? <Pill tone={state === 'done' ? 'pos' : state === 'failed' ? 'neg' : 'neutral'} dot>{STATE_FA[state]}</Pill> : null}
      </header>
      <FaPara text={card.body_fa} className="text-[13px] leading-6 text-sec" />
      {reason ? <p className="text-[12px] leading-5 text-neg"><FaText text={reason} /></p> : null}

      {editing && open ? (
        <div className="flex flex-col gap-2" aria-label="ویرایش کارت">
          {typeof card.payload.text === 'string' ? (
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} dir="auto" aria-label="متن فرمان" className={cx(field, 'py-2 leading-6')} />
          ) : null}
          {card.kind === 'minutes' ? tasks.map((t, i) => (
            <div key={i} className="grid grid-cols-1 gap-1.5 rounded-[10px] bg-page p-2 sm:grid-cols-[1fr_5rem_7rem_9rem_auto]">
              <input value={t.title_fa} onChange={(e) => setTask(i, { title_fa: e.target.value })} aria-label={`عنوان کار ${i + 1}`} dir="auto" className={cx(field, 'h-9')} />
              <input value={t.company ?? ''} onChange={(e) => setTask(i, { company: e.target.value.toUpperCase() })} aria-label={`شرکت کار ${i + 1}`} dir="ltr" className={cx(field, 'fig h-9')} />
              <input value={t.department ?? ''} onChange={(e) => setTask(i, { department: e.target.value })} aria-label={`بخش کار ${i + 1}`} dir="ltr" className={cx(field, 'fig h-9')} />
              <input type="date" value={t.due ?? ''} onChange={(e) => setTask(i, { due: e.target.value })} aria-label={`سررسید کار ${i + 1}`} className={cx(field, 'fig h-9')} />
              <Button size="sm" variant="ghost" onClick={() => setTasks((ts) => ts.filter((_, j) => j !== i))}>حذف</Button>
            </div>
          )) : null}
        </div>
      ) : null}
      {card.kind === 'minutes' && !editing && tasks.length && open ? (
        <ul className="flex flex-col gap-1 text-[13px] text-sec" aria-label="کارها">{tasks.map((t, i) => <li key={i} className="flex flex-wrap gap-x-2"><FaText text={t.title_fa} /><span className="fig text-muted">{[t.company, t.department, t.due].filter(Boolean).join(' · ')}</span></li>)}</ul>
      ) : null}

      {made.length ? (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-sec" aria-label="ساخته شد">ساخته شد.
          {made.map((r) => linkOf(r)).filter((l): l is { href: string; fa: string } => !!l).map((l) => <Link key={l.href} href={l.href} className="font-semibold text-gold-ink hover:underline">{l.fa}</Link>)}
        </p>
      ) : null}

      {open ? (
        <footer className="flex flex-wrap gap-2">
          <Button size="sm" variant="primary" icon="seal" loading={act.run.isPending} onClick={() => void run()}>اجرا کن</Button>
          {card.kind !== 'invite' ? <Button size="sm" icon="edit" aria-pressed={editing} onClick={() => setEditing(!editing)}>{editing ? 'بستن ویرایش' : 'ویرایش'}</Button> : null}
          <Button size="sm" variant="ghost" loading={act.dismiss.isPending} onClick={dismiss}>نه</Button>
          {editing ? <span className="self-center text-[12px] text-muted">با همین ویرایش اجرا میشود</span> : null}
        </footer>
      ) : null}
    </section>
  );
}
