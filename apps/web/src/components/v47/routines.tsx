'use client';

/**
 * ⟨1.0.1⟩ §50 «روال دائمی» («کارمند ۲۴ ساعته»): a standing routine made from one sentence, in the session.
 *
 * The owner's decision (2026-11-10): a «کارمند ۲۴ ساعته» is not a hire; it is a routine that keeps running, made where he says it,
 * without a card, without a passkey and without going through a working group. The session's details carry the action (one sentence
 * and «بساز») and, once there is one, the session's routines: when each runs, what it does, its next turn, and a switch. A hub before
 * §50 says nothing of routines in the session's report, and the card is not shown.
 */
import { useRef, useState } from 'react';
import { DecisionBar } from '@/components/look/decision-bar';
import { WhenAt } from '@/components/look/group';
import { SpringSheet } from '@/components/look/spring-sheet';
import { Button } from '@/components/ui/button';
import { Card, SectionTitle, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { PlainText } from '@/components/v29/text';
import { ApiError } from '@/lib/api/client';
import { notServed } from '@/lib/api/v28';
import { SENTENCE_MAX, markAbsent, useAbsent, useMakeRoutine, useRoutineState, type SessionRoutine } from '@/lib/api/v47';

const FIELD = 'w-full rounded-[10px] border border-strong bg-tile p-3 text-[14px] leading-7 text-ink outline-none transition-colors placeholder:text-muted focus:border-[var(--hq-silver-ink)]';

function Row({ order, x, closed }: { order: string; x: SessionRoutine; closed: boolean }) {
  const toast = useToast();
  const set = useRoutineState(order);
  const turn = (on: boolean) => set.mutate({ ref: x.ref, state: on ? 'on' : 'off' }, {
    onSuccess: () => toast({ tone: on ? 'ok' : 'info', text: on ? 'روال روشن شد.' : 'روال خاموش شد؛ هر وقت خواستی دوباره روشنش کن.' }),
    onError: (e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد؛ دوباره بزن.' }),
  });
  return (
    <li className="flex flex-col gap-1 rounded-[10px] bg-tile px-3 py-2.5" data-routine-state={x.state}>
      <div className="flex items-start gap-3">
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <b className="text-[13px] font-semibold leading-6 text-ink"><PlainText text={x.when_fa || x.sentence_fa} /></b>
          <span className="text-[12px] leading-5 text-sec [overflow-wrap:anywhere]"><PlainText text={x.preview_fa || x.sentence_fa} /></span>
        </span>
        {x.state === 'proposed' ? <span className="flex-none text-[12px] font-semibold text-sec">منتظر مُهر</span>
          : <Switch checked={x.state === 'on'} disabled={closed || set.isPending} onChange={turn} label={`روال ${x.when_fa || x.sentence_fa}`} />}
      </div>
      <span className="text-[11px] text-muted">
        {x.state === 'on' ? (x.next_at ? <>نوبت بعد: <WhenAt iso={x.next_at} /></> : 'روشن') : x.state === 'off' ? 'خاموش' : 'با مُهر تو روشن میشود'}
      </span>
      {x.note_fa ? <span className="text-[11px] leading-5 text-sec"><PlainText text={x.note_fa} /></span> : null}
    </li>
  );
}

function MakeSheet({ order, onClose }: { order: string; onClose: () => void }) {
  const toast = useToast();
  const make = useMakeRoutine(order);
  const [text, setText] = useState('');
  const [refused, setRefused] = useState<string | null>(null);
  // one key for one sentence: a second press of the same words (after a dropped answer) never makes it twice
  const keys = useRef(new Map<string, string>());
  const sentence = text.replace(/\s+/g, ' ').trim();
  const go = () => {
    if (sentence.length < 3) return;
    const key = keys.current.get(sentence) ?? crypto.randomUUID();
    keys.current.set(sentence, key);
    make.mutate({ sentence_fa: sentence, key }, {
      onSuccess: () => { toast({ tone: 'ok', text: 'روال دائمی ساخته شد و از همین حالا روشن است.' }); onClose(); },
      onError: (e) => {
        if (notServed(e)) { markAbsent('routine'); toast({ tone: 'info', text: 'روال دائمی بعد از به‌روزرسانی ستاد فعال میشود.' }); onClose(); return; }
        // not a routine (no time of repetition, or more than a routine): the hub's words under the field, his text kept
        if (e instanceof ApiError && e.status === 422) setRefused(e.messageFa);
        else toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ساخته نشد؛ دوباره بزن.' });
      },
    });
  };
  return (
    <SpringSheet open onOpenChange={(v) => { if (!v) onClose(); }} title="روال دائمی" description="با یک جمله بگو چه کاری، هر چند وقت یک بار" width={460} testid="routine-sheet"
      bar={(
        <DecisionBar label="ساختن روال" error={refused} context="بی کارت و بی اثر انگشت ساخته میشود؛ هر وقت خواستی با یک لمس خاموشش کن."
          primary={{ label: 'بساز', onClick: go, disabled: sentence.length < 3 }} state={make.isPending ? 'working' : 'idle'} />
      )}>
      <div className="flex flex-col gap-2">
        <textarea
          value={text} onChange={(e) => { setText(e.target.value.slice(0, SENTENCE_MAX)); setRefused(null); }} rows={3} dir="auto" maxLength={SENTENCE_MAX} aria-label="جمله‌ی روال"
          placeholder="مثلاً: هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده" className={FIELD}
        />
      </div>
    </SpringSheet>
  );
}

/** In the session's details: the action «روال دائمی», and the session's routines while there are any. */
export function Routines({ order, routines, closed }: { order: string; routines: SessionRoutine[] | undefined; closed: boolean }) {
  const absent = useAbsent('routine');
  const [making, setMaking] = useState(false);
  // a hub before §50 does not say `routines` at all
  if (routines === undefined) return null;
  const offer = !closed && !absent;
  if (!routines.length && !offer) return null;
  return (
    <Card className="flex flex-col gap-3 p-4" aria-label="روال دائمی">
      <SectionTitle title="روال دائمی" note="کاری که باید همیشه تکرار شود را با یک جمله بگو" />
      {routines.length ? (
        <section className="flex flex-col gap-1.5" aria-label="روال‌های دائمی">
          <h3 className="text-[12px] font-semibold text-muted">روال‌های دائمی</h3>
          <ul className="flex flex-col gap-1.5">{routines.map((x) => <Row key={x.ref} order={order} x={x} closed={closed} />)}</ul>
        </section>
      ) : null}
      {offer ? <div><Button variant="secondary" icon="add" aria-haspopup="dialog" onClick={() => setMaking(true)}>روال دائمی</Button></div> : null}
      {making ? <MakeSheet order={order} onClose={() => setMaking(false)} /> : null}
    </Card>
  );
}
