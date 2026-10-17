'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Pill, Skeleton } from '@/components/ui/primitives';
import { useRun, type Run, type RunDetail } from '@/lib/api/v15';
import { ago, cx, jDateTime, modelLabel, tokens, usd } from '@/lib/format';

export const RUN_STATE: Record<string, { fa: string; tone: 'pos' | 'neg' | 'warn' | 'neutral' | 'gold'; live?: boolean }> = {
  queued: { fa: 'در صف', tone: 'neutral' },
  running: { fa: 'در حال اجرا', tone: 'gold', live: true },
  done: { fa: 'تمام شد', tone: 'pos' },
  failed: { fa: 'شکست', tone: 'neg' },
  refused: { fa: 'رد شد', tone: 'warn' },
};
const OUTCOME_TONE: Record<string, string> = { ok: 'text-pos', refused: 'text-warn', error: 'text-neg', held: 'text-warn' };

function Steps({ run }: { run: RunDetail }) {
  if (!run.steps_detail.length) return <p className="px-1 text-[12px] text-muted">هنوز قدمی ثبت نشده.</p>;
  return (
    <ol className="relative flex flex-col gap-3 pr-3">
      <span className="absolute bottom-2 right-[5px] top-2 w-px bg-div" aria-hidden />
      {run.steps_detail.map((s) => (
        <li key={s.n} className="relative flex flex-col gap-1">
          <span className="absolute -right-3 top-1.5 size-[11px] rounded-full border-2 border-[var(--hq-card)] bg-sec" aria-hidden />
          <span className="text-[13px] leading-6 text-ink">{s.summary_fa}</span>
          <span className="flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className="text-muted">{jDateTime(s.at)}</span>
            {s.actions.map((a, i) => (
              <span key={i} className="fig inline-flex items-center gap-1 rounded-full bg-tile px-2 py-0.5 text-sec">
                {a.tool}<span className={OUTCOME_TONE[a.outcome] ?? 'text-muted'}>{a.outcome}</span>{a.ref ? <span className="text-muted">{a.ref}</span> : null}
              </span>
            ))}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** One agent run (contract §16.2): who, why, model, tokens; opens to its steps and tool calls. Live runs refresh by themselves. */
export function RunRow({ run, detail, showEmployee = true }: { run: Run; detail?: RunDetail; showEmployee?: boolean }) {
  const [open, setOpen] = useState(false);
  const q = useRun(open && !detail ? run.id : null);
  const d = detail ?? q.data;
  const st = RUN_STATE[run.state] ?? { fa: run.state, tone: 'neutral' as const };
  const total = run.tokens.input + run.tokens.output;
  return (
    <li className="flex flex-col rounded-[12px] bg-tile">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full flex-col gap-1.5 rounded-[12px] p-3 text-start hover:bg-hover">
        <span className="flex flex-wrap items-center gap-2">
          <Pill tone={st.tone} dot live={st.live}>{st.fa}</Pill>
          {showEmployee ? <span className="fig text-[13px] font-semibold text-ink">{run.employee}</span> : null}
          <span className="min-w-0 flex-1 truncate text-[13px] text-sec">{run.reason}</span>
          <Icon name="chevron" size={14} className={cx('text-muted transition-transform', open && 'rotate-180')} />
        </span>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
          <span>{ago(run.started_at ?? run.queued_at)}</span>
          {run.model ? <span className="fig">{modelLabel(run.model)}</span> : null}
          <span>{run.steps.toLocaleString('fa-IR')} قدم · {run.tool_calls.toLocaleString('fa-IR')} ابزار</span>
          <span className="fig">{tokens(total)} · {usd(run.equiv_cost_usd)}</span>
          {run.work_ref ? <Link href={`/work/${run.work_ref}`} onClick={(e) => e.stopPropagation()} className="fig text-gold-ink hover:underline">{run.work_ref}</Link> : null}
          {run.error_code ? <span className="fig text-neg">{run.error_code}</span> : null}
        </span>
      </button>
      {open ? <div className="border-t border-div px-3 py-3">{d ? <Steps run={d} /> : <Skeleton className="h-16" />}</div> : null}
    </li>
  );
}

export function RunList({ runs, details, showEmployee, empty }: { runs: Run[]; details?: RunDetail[]; showEmployee?: boolean; empty: string }) {
  if (!runs.length) return <p className="py-4 text-center text-[13px] text-muted">{empty}</p>;
  return <ul className="flex flex-col gap-2">{runs.map((r) => <RunRow key={r.id} run={r} detail={details?.find((x) => x.id === r.id)} showEmployee={showEmployee} />)}</ul>;
}
