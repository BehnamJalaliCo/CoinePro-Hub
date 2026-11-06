'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Bar, budgetTone, Card, Empty, ErrorState, PageHeader, Pill, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { errText } from '@/components/v31/kit';
import { STATE_FA, useHubServices, useToggleService, type HubJob, type HubService } from '@/lib/api/v38';

const mb = (n: number) => (n >= 1024 ? `${(n / 1024).toFixed(1)} GB` : `${Math.round(n)} MB`);
const TONE = { on: 'pos', off: 'silver', starting: 'gold', failed: 'neg' } as const;

/** ⟨1.20⟩ §38.3 «سرویس‌ها»: the hub's optional services with a switch each, and the memory they may take. */
export default function ServicesPage() {
  const q = useHubServices();
  const toggle = useToggleService();
  const toast = useToast();
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [refused, setRefused] = useState<{ svc: HubService; job: HubJob } | null>(null);
  const data = q.data;
  const mem = data?.memory ?? null;
  const byKey = (k: string) => data?.services.find((s) => s.key === k);

  const run = async (svc: HubService, on: boolean, turnOff?: string[]) => {
    const keys = [svc.key, ...(turnOff ?? [])];
    setPending((p) => new Set([...p, ...keys]));
    try {
      const job = await toggle.mutateAsync({ key: svc.key, on, turn_off: turnOff });
      if (job.state === 'refused') setRefused({ svc, job });
      else toast({ tone: job.state === 'done' ? 'ok' : 'error', text: job.result_fa ?? (job.state === 'done' ? (on ? 'روشن شد' : 'خاموش شد') : 'انجام نشد؛ دوباره بزن.') });
    } catch (e) {
      toast({ tone: 'error', text: errText(e, 'انجام نشد؛ دوباره بزن.') });
    } finally {
      setPending((p) => { const n = new Set(p); keys.forEach((k) => n.delete(k)); return n; });
    }
  };

  const pct = mem && mem.budget_mb ? (mem.caps_mb / mem.budget_mb) * 100 : 0;
  const first = refused?.job.blocking[0];
  return (
    <>
      <PageHeader eyebrow="سرور هاب" title="سرویس‌ها" />
      {q.isLoading ? <Skeleton className="h-64 rounded-[16px]" />
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !data || !mem ? <Card><Empty icon="server" title="بخش سرور هنوز نصب نشده است" body="تا آن موقع سرویس‌ها فقط دیده میشوند و کلیدهایشان خاموش است." /></Card>
        : null}
      {data && !mem ? <ServiceList services={data.services} pending={pending} disabled onToggle={run} /> : null}
      {data && mem ? (
        <>
          <Card as="section" className="flex flex-col gap-2 p-5" aria-label="حافظه">
            <div className="flex flex-wrap items-baseline gap-x-3">
              <h2 className="text-h3 font-semibold">حافظه‌ی سرور</h2>
              <span className="text-[13px] text-sec"><span className="fig">{mb(mem.free_mb)}</span> آزاد از <span className="fig">{mb(mem.budget_mb)}</span> بودجه</span>
            </div>
            <Bar pct={pct} tone={budgetTone(pct)} height={8} label="حافظه‌ی گرفته‌شده از بودجه" />
            <p className="text-[12px] text-muted">هر سرویس روشن، سقف حافظه‌اش را از بودجه برمیدارد؛ اگر جا نباشد، میگوید کدام را خاموش کنی.</p>
          </Card>
          <ServiceList services={data.services} pending={pending} onToggle={run} />
        </>
      ) : null}
      <Dialog
        open={!!refused} onOpenChange={(v) => { if (!v) setRefused(null); }} title="جا نیست؛ این‌ها جا را گرفته‌اند"
        actions={refused && first ? (
          <>
            <Button variant="primary" onClick={() => { const r = refused; setRefused(null); void run(r.svc, true, [first.key]); }}>
              {byKey(first.key)?.title_fa ?? first.title_fa} را خاموش کن و {refused.svc.title_fa} را روشن کن
            </Button>
            <Button variant="ghost" onClick={() => setRefused(null)}>ولش کن</Button>
          </>
        ) : <Button variant="ghost" onClick={() => setRefused(null)}>باشه</Button>}
      >
        <ul className="flex flex-col gap-1.5" aria-label="سرویس‌هایی که جا را گرفته‌اند">
          {refused?.job.blocking.map((b) => <li key={b.key} className="flex items-center gap-2 text-[13px]"><span className="flex-1">{b.title_fa}</span><span className="fig text-muted">{mb(b.mem_cap_mb)}</span></li>)}
        </ul>
      </Dialog>
    </>
  );
}

function ServiceList({ services, pending, disabled, onToggle }: { services: HubService[]; pending: Set<string>; disabled?: boolean; onToggle: (s: HubService, on: boolean) => void }) {
  return (
    <Card as="section" className="flex flex-col p-2" aria-label="سرویس‌ها">
      <ul className="flex flex-col divide-y divide-[var(--hq-divider,transparent)]">
        {services.map((s) => {
          const busy = pending.has(s.key);
          const on = s.state === 'on' || s.state === 'starting';
          return (
            <li key={s.key} data-service={s.key} data-state={busy ? 'pending' : s.state} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-3">
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="flex flex-wrap items-center gap-2 text-[14px] font-semibold">{s.title_fa}{!s.optional ? <Pill tone="neutral">پایه</Pill> : null}</span>
                <span className="text-[12px] leading-5 text-sec">{s.what_fa}</span>
                {s.note_fa ? <span className="text-[12px] text-warn">{s.note_fa}</span> : null}
              </div>
              <Pill tone={busy ? 'gold' : TONE[s.state]} live={busy || s.state === 'starting'}>{busy ? 'در حال انجام…' : STATE_FA[s.state]}</Pill>
              <span className="fig w-32 text-[12px] text-muted">{s.mem_used_mb != null ? mb(s.mem_used_mb) : '—'} / {mb(s.mem_cap_mb)}</span>
              {s.can_toggle ? <Switch checked={on} onChange={(v) => onToggle(s, v)} label={`${s.title_fa}`} disabled={disabled || busy} /> : <span className="w-[44px]" />}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
