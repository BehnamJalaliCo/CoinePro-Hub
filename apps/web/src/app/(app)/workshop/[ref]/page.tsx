'use client';

import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { use, useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Composer } from '@/components/media/composer';
import { Button } from '@/components/ui/button';
import { Md, MdInline } from '@/components/ui/md';
import { Dialog } from '@/components/ui/overlay';
import { Bar, Card, ErrorState, Pill, Skeleton, budgetTone } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { APPROVAL_FA, StatePill, companyOfWorkspace, isOpen } from '@/components/workshop/parts';
import { ApiError } from '@/lib/api/client';
import { answerApproval, sendToSession, stopSession, useCodeSession, useGrants, useSessionEvents, useWorkspaces, type SessionEvent } from '@/lib/api/v13';
import { stepUp } from '@/lib/auth';
import { ACTOR_FA } from '@/lib/labels';
import { cx, jDateTime, jTime, modelLabel, usd } from '@/lib/format';

const str = (v: unknown) => (typeof v === 'string' ? v : v == null ? '' : String(v));
const num = (v: unknown) => (typeof v === 'number' ? v : null);

function Approval({ e, answered, onAnswer }: { e: SessionEvent; answered: SessionEvent | undefined; onAnswer: (allow: boolean) => Promise<void> }) {
  const [busy, setBusy] = useState<'allow' | 'deny' | null>(null);
  const action = str(e.data.action);
  const run = async (allow: boolean) => { setBusy(allow ? 'allow' : 'deny'); try { await onAnswer(allow); } finally { setBusy(null); } };
  const allowed = answered?.data.allow === true;
  return (
    <div className={cx('flex flex-col gap-3 rounded-[14px] p-4', answered ? 'bg-tile' : 'bg-gold-soft ring-1 ring-[var(--hq-gold-ink)]')}>
      <div className="flex items-center gap-2">
        <span className="text-gold-ink"><Icon name="seal" size={18} active={!answered} /></span>
        <span className="flex-1 text-[14px] font-semibold text-ink"><MdInline text={e.summary_fa || `اجازه‌ی ${APPROVAL_FA[action] ?? action}`} /></span>
        <span className="fig text-[11px] text-muted">{str(e.data.approval_id)}</span>
      </div>
      {e.data.detail ? <code dir="ltr" className="fig block overflow-x-auto whitespace-pre rounded-[10px] bg-page px-3 py-2 text-left text-[12px] text-sec">{str(e.data.detail)}</code> : null}
      {answered ? (
        <span className={cx('flex items-center gap-1.5 text-[12px] font-semibold', allowed ? 'text-pos' : 'text-neg')}>
          <Icon name={allowed ? 'seal' : 'reject'} size={14} />{allowed ? 'اجازه دادی' : 'اجازه ندادی'} · {jTime(answered.at)}
        </span>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon="seal" loading={busy === 'allow'} disabled={!!busy} onClick={() => run(true)}>اجازه بده</Button>
          <Button variant="secondary" loading={busy === 'deny'} disabled={!!busy} onClick={() => run(false)}>نه</Button>
          <span className="self-center text-[11px] text-muted">اجازه با گذرکلید (اثر انگشت)</span>
        </div>
      )}
    </div>
  );
}

function Event({ e, driverKind }: { e: SessionEvent; driverKind: string }) {
  const mine = e.actor.kind === 'owner';
  switch (e.type) {
    case 'message':
      return (
        <div className={cx('flex gap-3', mine && 'flex-row-reverse')}>
          {!mine ? <span className="mt-1"><Avatar kind={driverKind} size={28} /></span> : null}
          <div className={cx('flex max-w-[min(680px,88%)] flex-col gap-1', mine ? 'items-end' : 'items-start')}>
            <div className={cx('rounded-[14px] px-4 py-2.5', mine ? 'rounded-tl-[6px] bg-raised' : 'rounded-tr-[6px] bg-card')}>
              <Md text={e.summary_fa} className="flex flex-col gap-2 text-[14px] leading-7 text-ink" />
            </div>
            <span className="px-1 text-[11px] text-muted" title={jDateTime(e.at)}>{mine ? 'تو' : ACTOR_FA(e.actor)} · {jTime(e.at)}</span>
          </div>
        </div>
      );
    case 'command': {
      const code = num(e.data.exit_code);
      const d = num(e.data.duration_s);
      return (
        <div className="flex flex-col gap-1.5 rounded-[12px] bg-tile px-3 py-2.5">
          <code dir="ltr" className="fig block overflow-x-auto whitespace-pre text-left text-[12px] text-ink"><span className="text-muted">$ </span>{str(e.data.cmd)}</code>
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
            {code != null ? <Pill tone={code === 0 ? 'pos' : 'neg'} dot><span className="fig">exit {code}</span></Pill> : null}
            <span className="min-w-0 flex-1"><MdInline text={e.summary_fa} /></span>
            {d != null ? <span className="fig text-muted">{d}s</span> : null}
            <span className="text-muted">{jTime(e.at)}</span>
          </div>
        </div>
      );
    }
    case 'file_change':
      return (
        <div className="flex items-center gap-2.5 px-1 text-[12px]">
          <span className="text-sec"><Icon name="edit" size={16} /></span>
          <span dir="ltr" className="fig min-w-0 flex-1 truncate text-left text-ink">{str(e.data.path)}</span>
          <span className="fig text-pos">+{num(e.data.added) ?? 0}</span>
          <span className="fig text-neg">−{num(e.data.removed) ?? 0}</span>
        </div>
      );
    case 'state':
      return (
        <div className="flex items-center gap-3 py-1 text-[11px] text-muted">
          <span className="h-px flex-1 bg-div" /><span><MdInline text={e.summary_fa} /> · {jTime(e.at)}</span><span className="h-px flex-1 bg-div" />
        </div>
      );
    case 'error':
      return <div role="alert" className="flex items-center gap-2 rounded-[12px] bg-neg-soft px-3 py-2 text-[13px] text-neg"><Icon name="urgent" size={16} /><MdInline text={e.summary_fa} /></div>;
    case 'approval_result':
      return null; // shown on its request
    default:
      return (
        <div className="flex items-start gap-2.5 px-1 text-[13px] text-sec">
          <span className="mt-2 size-1.5 flex-none rounded-full bg-silver-ink" />
          <span className="min-w-0 flex-1"><MdInline text={e.summary_fa} /></span>
          <span className="text-[11px] text-muted">{jTime(e.at)}</span>
        </div>
      );
  }
}

/** One Code Workshop session, live (contract §17.3): what the driver does, the owner's approvals, steering and stop. */
export default function SessionPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params);
  const q = useCodeSession(ref);
  const { events, live, error } = useSessionEvents(ref);
  const { data: workspaces } = useWorkspaces();
  const { data: grants } = useGrants();
  const qc = useQueryClient();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [stopping, setStopping] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: 'end', behavior: 'smooth' }); }, [events.length]);
  const results = useMemo(() => new Map(events.filter((e) => e.type === 'approval_result').map((e) => [str(e.data.approval_id), e])), [events]);

  if (q.isLoading) return <div className="flex flex-col gap-4"><Skeleton className="h-28" /><Skeleton className="h-96" /></div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data!;
  const ws = workspaces?.find((w) => w.code === s.workspace);
  const grant = grants?.find((g) => g.ref === s.grant);
  const pct = grant ? Math.min(100, (s.usage.usd / grant.budget_usd) * 100) : null;
  const active = isOpen(s.state);

  const answer = async (id: string, allow: boolean) => {
    try {
      const token = allow ? await stepUp('workshop.approval', `${s.ref}/${id}`) : undefined;
      await answerApproval(s.ref, id, allow, token);
      void qc.invalidateQueries({ queryKey: ['workshop'] });
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : 'ثبت نشد.' });
    }
  };
  const stop = async () => {
    setStopping(true);
    try {
      await stopSession(s.ref);
      void qc.invalidateQueries({ queryKey: ['workshop'] });
      setConfirm(false);
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'متوقف نشد.' });
    } finally {
      setStopping(false);
    }
  };
  const steer = async (v: { body: string; attachments: string[] }) => {
    try {
      await sendToSession(s.ref, v.body, v.attachments);
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'فرستاده نشد.' });
      throw e;
    }
  };

  return (
    <div className="flex min-h-[calc(100dvh-9rem)] flex-col gap-4">
      <Link href="/workshop" className="inline-flex items-center gap-1 self-start text-[13px] text-sec hover:text-ink"><Icon name="back" size={16} mirror />کارگاه کد</Link>
      <Card className="flex flex-col gap-3 p-4 md:p-5">
        <div className="flex flex-wrap items-start gap-3">
          <span className="mt-1 text-sec"><CompanyMark code={companyOfWorkspace(workspaces, s.workspace)} height={18} mono /></span>
          <div className="flex min-w-0 flex-[1_1_16rem] flex-col gap-0.5">
            <h1 className="text-h2 font-semibold text-ink">{s.title}</h1>
            <span className="flex flex-wrap items-center gap-x-2 text-[12px] text-muted">
              <span className="fig">{s.ref}</span><span className="fig">{ws?.repo ?? s.workspace}</span>{s.branch ? <span className="fig">{s.branch}</span> : null}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <StatePill state={s.state} />
            {active ? <Button variant="danger" size="sm" icon="stop" onClick={() => setConfirm(true)}>توقف</Button> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[12px] text-sec">
          <span className="flex items-center gap-1.5"><Avatar kind={s.driver.kind} size={22} state={s.state === 'working' ? 'working' : 'idle'} />{ACTOR_FA(s.driver)}</span>
          <span className="fig">{modelLabel(s.model)} · {s.effort}</span>
          <span>{s.runtime === 'managed' ? 'Managed Agents' : 'میزبانی خودمان'}</span>
          {grant ? <span>زیر مجوز <span className="fig">{grant.ref}</span></span> : null}
          {s.pr_url ? <a href={s.pr_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 font-semibold text-gold-ink hover:underline"><Icon name="share" size={14} />PR در GitHub</a> : null}
          <span className="flex-1" />
          <span className="fig">{usd(s.usage.usd)}{grant ? <span className="text-muted"> / {usd(grant.budget_usd, 0)}</span> : null}</span>
        </div>
        {pct != null ? <Bar pct={pct} tone={budgetTone(pct)} height={4} label="بودجه‌ی جلسه" /> : null}
        {s.brief ? <p className="border-t border-div pt-3 text-[13px] leading-6 text-sec"><MdInline text={s.brief} /></p> : null}
      </Card>

      <section aria-label="رویدادهای جلسه" aria-live="polite" className="flex flex-1 flex-col gap-3">
        <div className="flex items-center gap-2 text-[12px] text-muted">
          <span className="flex-1">رویدادها</span>
          {active ? <Pill tone={live ? 'pos' : 'warn'} live={live}>{live ? 'زنده' : 'در حال اتصال'}</Pill> : null}
        </div>
        {error ? <ErrorState error={error} /> : !events.length ? <Skeleton className="h-40" /> : events.map((e) =>
          e.type === 'approval_request'
            ? <Approval key={e.seq} e={e} answered={results.get(str(e.data.approval_id))} onAnswer={(allow) => answer(str(e.data.approval_id), allow)} />
            : <Event key={e.seq} e={e} driverKind={s.driver.kind} />,
        )}
        <div ref={end} />
      </section>

      <div className="sticky bottom-[76px] z-10 -mx-1 bg-page/95 px-1 pb-3 pt-2 backdrop-blur-md lg:bottom-0">
        {active ? (
          <Composer placeholder="راهنمایی یا تغییر مسیر؛ با متن یا ویس" purpose="message" onSend={steer} label="پیام به جلسه" />
        ) : (
          <p className="rounded-[14px] bg-tile px-4 py-3 text-center text-[13px] text-muted">این جلسه بسته است؛ شاخه و تاریخچه‌اش میماند.</p>
        )}
      </div>

      <Dialog open={confirm} onOpenChange={setConfirm} title="جلسه متوقف شود؟"
        actions={<><Button variant="danger" icon="stop" loading={stopping} onClick={stop}>متوقف کن</Button><Button variant="ghost" onClick={() => setConfirm(false)}>نه</Button></>}>
        کار همین لحظه می‌ایستد. شاخه‌ی <span className="fig">{s.branch ?? '—'}</span> و تاریخچه میمانند و میشود بعداً از همان‌جا ادامه داد.
      </Dialog>
    </div>
  );
}
