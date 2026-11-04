'use client';

// ⟨1.12⟩ Contract §30.3 one run of a line: the timeline of its steps with state, time, cost and outputs shown properly, the seal for a
// waiting run (approve or reject, behind the passkey), a run again from one step, and what was published.

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, PageHeader, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { LIVE_RUN, STEP_STATE_FA, platformFa, stepKind, useLine, useLineRun, useRunActions, type LineRun, type StepRun, type StepRunState } from '@/lib/api/v30';
import { cx, jDateTime, jTime, usd } from '@/lib/format';
import { FaPara, FaText, KindIcon, OutputView, RunStatePill, fig } from './bits';

const STEP_TONE: Record<StepRunState, string> = {
  pending: 'bg-tile text-muted', running: 'bg-gold-soft text-gold-ink', waiting: 'bg-warn-soft text-warn', done: 'bg-pos-soft text-pos', failed: 'bg-neg-soft text-neg', skipped: 'bg-tile text-muted',
};
const TRIGGER_FA: Record<LineRun['trigger'], string> = { schedule: 'زمان‌بندی', owner: 'دستی', test: 'آزمایش', n8n: 'روال خودکار', group: 'کارگروه' };
const errText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.messageFa : fallback);

function secs(a: string | null, b: string | null): string {
  if (!a || !b) return '';
  const s = Math.max(0, Math.round((Date.parse(b) - Date.parse(a)) / 1000));
  return s < 60 ? `${s} ثانیه` : `${Math.round(s / 60)} دقیقه`;
}

export function RunView({ runRef }: { runRef: string }) {
  const q = useLineRun(runRef);
  const run = q.data;
  const line = useLine(run?.line ?? '');
  const act = useRunActions(runRef);
  const toast = useToast();
  const [note, setNote] = useState('');

  if (q.isLoading) return <div className="flex flex-col gap-4"><Skeleton className="h-24 rounded-[16px]" /><Skeleton className="h-72 rounded-[16px]" /></div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!run) return <Card><Empty icon="video" title="این اجرا پیدا نشد" /></Card>;

  const titleOf = (s: StepRun) => line.data?.steps.find((d) => d.key === s.key)?.title_fa ?? stepKind(s.kind).fa;
  const live = LIVE_RUN.has(run.state);
  const seal = (approve: boolean) => act.seal.mutate({ approve, note_fa: note.trim() || undefined }, {
    onSuccess: () => { toast({ tone: 'ok', text: approve ? 'تأیید شد؛ خط ادامه میدهد.' : 'رد شد؛ این اجرا منتشر نمیشود.' }); setNote(''); },
    onError: (e) => toast({ tone: 'error', text: errText(e, 'مُهر نشد؛ دوباره بزن.') }),
  });

  return (
    <div className="flex flex-col gap-4">
      <PageHeader eyebrow={<Link href={`/lines/${run.line}`} className="hover:text-gold-ink">{line.data ? <FaText text={line.data.title_fa} /> : run.line} · {line.data ? platformFa(line.data.platform) : ''}</Link>}
        title={<span className="fig">{run.ref}</span>}
        actions={<>
          <RunStatePill state={run.state} />
          {run.dry ? <Pill tone="silver">آزمایشی</Pill> : null}
          {live ? <Button size="sm" loading={act.cancel.isPending} onClick={() => act.cancel.mutate(undefined, { onError: (e) => toast({ tone: 'error', text: errText(e, 'لغو نشد.') }) })}>لغو</Button> : null}
        </>} />

      <Card className="hq-rise flex flex-wrap items-center gap-x-6 gap-y-2 p-4 text-[13px] text-sec" aria-label="خلاصه‌ی اجرا">
        <span>شروع: {jDateTime(run.at)}</span>
        <span>راه‌انداز: {TRIGGER_FA[run.trigger]}</span>
        <span>نسخه‌ی خط: <span className="fig">{run.line_version}</span></span>
        <span><span className="fig">{fig(run.cost.tokens)}</span> توکن · <span className="fig">{usd(run.cost.usd_equiv)}</span> معادل دلار</span>
        {run.note_fa ? <FaPara text={run.note_fa} className="w-full text-[12px]" /> : null}
      </Card>

      {run.state === 'waiting' ? (
        <Card as="section" className="tahrir hq-rise flex flex-col gap-3 p-5" aria-label="منتظر مُهر تو">
          <SectionTitle title="منتظر مُهر تو" note="بعد از دیدن خروجی‌ها، انتشار را تأیید یا رد کن" />
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="یادداشت (اختیاری)" aria-label="یادداشت مُهر"
            className="h-11 w-full rounded-[10px] border border-strong bg-tile px-3 text-[14px] outline-none focus:border-gold-ink" />
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" icon="seal" loading={act.seal.isPending && act.seal.variables?.approve === true} onClick={() => seal(true)}>تأیید و منتشر کن</Button>
            <Button icon="reject" loading={act.seal.isPending && act.seal.variables?.approve === false} onClick={() => seal(false)}>رد کن</Button>
          </div>
        </Card>
      ) : null}

      <ol className="flex flex-col" aria-label="قدم‌های اجرا">
        {run.steps.map((s, i) => (
          <li key={`${s.key}-${i}`} className="relative flex gap-3 pb-4">
            {i < run.steps.length - 1 ? <span aria-hidden className="absolute bottom-0 right-[19px] top-10 w-px bg-div" /> : null}
            <KindIcon kind={s.kind} className={cx('relative z-[1]', s.state === 'running' && 'ring-2 ring-gold')} />
            <Card as="article" className="hq-rise flex min-w-0 flex-1 flex-col gap-3 p-4" aria-label={`${titleOf(s)}: ${STEP_STATE_FA[s.state]}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-[1_1_10rem] text-[14px] font-semibold"><FaText text={titleOf(s)} /></span>
                <span className={cx('inline-flex h-6 items-center rounded-full px-2.5 text-[12px] font-semibold', STEP_TONE[s.state])}>{STEP_STATE_FA[s.state]}</span>
                {s.attempt > 1 ? <Pill tone="warn">تلاش <span className="fig">{s.attempt}</span></Pill> : null}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
                {s.started_at ? <span>{jTime(s.started_at)}{s.ended_at ? ` تا ${jTime(s.ended_at)}` : ''} {secs(s.started_at, s.ended_at) ? <>({secs(s.started_at, s.ended_at)})</> : null}</span> : null}
                {s.via ? <span>با <span dir="ltr">{s.via}</span></span> : null}
                {s.tokens ? <span><span className="fig">{fig(s.tokens)}</span> توکن · <span className="fig">{usd(s.usd_equiv)}</span></span> : null}
              </div>
              {s.error_fa ? <div className="rounded-[10px] bg-neg-soft px-3 py-2 text-[13px] leading-6"><FaPara text={s.error_fa} /></div> : null}
              <OutputView out={s.output} kind={s.kind} />
              {(s.state === 'done' || s.state === 'failed') && !live ? (
                <div><Button size="sm" icon="refresh" loading={act.rerun.isPending && act.rerun.variables === s.key} aria-label={`دوباره از ${titleOf(s)}`}
                  onClick={() => act.rerun.mutate(s.key, { onSuccess: () => toast({ tone: 'ok', text: 'از این قدم دوباره شروع شد.' }), onError: (e) => toast({ tone: 'error', text: errText(e, 'شروع نشد.') }) })}>دوباره از این قدم</Button></div>
              ) : null}
            </Card>
          </li>
        ))}
      </ol>

      {run.published.length ? (
        <Card as="section" className="flex flex-col gap-2 p-5" aria-label="منتشر شده">
          <SectionTitle title="منتشر شد" />
          <ul className="flex flex-col">{run.published.map((p, i) => (
            <li key={i} className="flex flex-wrap items-center gap-3 border-t border-div py-2.5 text-[13px] first:border-0">
              <Icon name="send" size={16} className="text-pos" /><span className="flex-1">{platformFa(p.platform)} · {p.kind}</span><span className="text-[11px] text-muted">{jDateTime(p.at)}</span>
              {p.url ? <a href={p.url} target="_blank" rel="noopener noreferrer" className="font-semibold text-gold-ink hover:underline">باز کن</a> : null}
            </li>
          ))}</ul>
        </Card>
      ) : null}
      {run.metrics.h24 || run.metrics.d7 ? (
        <Card as="section" className="flex flex-col gap-2 p-5" aria-label="عملکرد">
          <SectionTitle title="عملکرد بعد از انتشار" note="عددها از اتصال خود پلتفرم میاید" />
          {([['h24', 'بعد از ۲۴ ساعت'], ['d7', 'بعد از ۷ روز']] as const).map(([k, fa]) => run.metrics[k] ? (
            <div key={k} className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]"><span className="font-semibold text-sec">{fa}</span>
              {Object.entries(run.metrics[k]!).map(([m, v]) => <span key={m}><span dir="ltr" className="text-muted">{m}</span> <span className="fig">{fig(v)}</span></span>)}</div>
          ) : null)}
        </Card>
      ) : null}
    </div>
  );
}
