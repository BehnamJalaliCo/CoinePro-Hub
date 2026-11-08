'use client';

// ⟨1.8⟩ «شبکه‌ی هلدینگ» (contract §26.6): what is broken in words, the map, then the selected server's roads to every other server.
// «بررسی دوباره» queues a `netcheck` on every online runner and follows the answers (Android: Network.kt NetworkScreen).
// ⟨1.24⟩ The map is the holding live (design/LIVE_VIEWS.md §5, contract §42): companies and their servers around the hub, the flows, the
// disconnects with when, why and the fix, and the table of every company.

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { Card, ErrorState, PageHeader, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { CheckButton, CheckCard, NodeDetail, SummaryCard, useNetNames, type NetCheckRun } from '@/components/v26/network';
import { HoldingMap } from '@/components/live/holding-map';
import { Iso } from '@/components/v26/bits';
import {
  checkDone, checkNetwork, checkProgress, isHub, netLastAt, netNode, netSummary, network, serverError, useNetwork, MAX_WAIT_MS, POLL_MS,
  type NetworkMap,
} from '@/lib/api/v26';
import { ago, jTime } from '@/lib/format';

export default function NetworkPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useNetwork();
  const m = q.data;
  const names = useNetNames(m);
  const [selected, setSelected] = useState<string | null>(null);
  const [run, setRun] = useState<NetCheckRun | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const checking = !!run && !run.ended;

  const check = async () => {
    if (checking) return;
    const before = q.data ?? null;
    setRun({ before, progress: { ...checkProgress(before, before ?? { at: null, nodes: [], links: [] }), reported: new Set() }, waitedMs: 0, ended: false });
    try {
      await checkNetwork();
    } catch (e) {
      setRun(null);
      toast({ tone: 'error', text: serverError(e) });
      return;
    }
    let waited = 0;
    let p = checkProgress(before, before ?? { at: null, nodes: [], links: [] });
    p = { ...p, reported: new Set() };
    // Every 3 s, at most a minute: the runners answer on their next poll, each in its own time.
    while (waited < MAX_WAIT_MS && alive.current) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      waited += POLL_MS;
      const now: NetworkMap | null = await network().catch(() => null);
      if (now) {
        qc.setQueryData(['network'], now);
        p = checkProgress(before, now);
      }
      setRun((x) => (x ? { ...x, progress: p, waitedMs: waited } : x));
      if (checkDone(p)) break;
    }
    if (!alive.current) return;
    setRun((x) => (x ? { ...x, progress: p, waitedMs: waited, ended: true } : x));
    void qc.invalidateQueries({ queryKey: ['servers'] });
    if (checkDone(p)) toast({ tone: 'ok', text: 'بررسی تمام شد؛ همه‌ی سرورها جواب دادند.' });
    else toast({ tone: 'info', text: `بررسی تمام شد؛ ${[...p.expected].filter((id) => !p.reported.has(id)).length} سرور در یک دقیقه جواب نداد.` });
  };

  const node = m && selected ? netNode(m, selected) : null;
  const last = m ? netLastAt(m) : null;
  return (
    <>
      <PageHeader eyebrow="هاب در مرکز؛ شرکت‌ها، سرورهایشان و پیوندها، زنده" title="شبکه‌ی هلدینگ" actions={<CheckButton checking={checking} disabled={!m} onClick={() => void check()} />} />
      {run ? <CheckCard x={run} names={names} /> : null}
      {/* ⟨1.24⟩ HM-1…HM-3, HM-8: the holding live — who is connected to whom, what crosses now, what dropped, when and why. */}
      <Card as="section" className="flex flex-col gap-3 p-4" aria-label="نقشه‌ی زنده‌ی شبکه‌ی هلدینگ">
        <h2 className="text-h3 font-semibold text-ink">نقشه‌ی زنده</h2>
        <HoldingMap onRoutes={(id) => setSelected(id)} />
        {last ? <span className="text-[11px] text-muted">آخرین بررسی راه‌ها <span className="fig">{jTime(last)}</span> · {ago(last)}</span> : null}
      </Card>
      {!m ? (q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : <Skeleton className="h-24 rounded-[16px]" />) : (
        <>
          <SummaryCard s={netSummary(m)} names={names} />
          {node && !isHub(node) ? <NodeDetail m={m} n={node} names={names} onClose={() => setSelected(null)} />
            : <p className="text-[12px] text-muted">روی هر سرور بزن تا حالش را ببینی؛ «راه‌های این سرور» نشان میدهد به سرورهای دیگر، پورت به پورت، میرسد یا نه.</p>}
          <p className="text-[11px] leading-5 text-muted"><Iso text="هر runner با HTTPS به هاب وصل میشود؛ هاب به هیچ سروری وارد نمیشود. «بررسی دوباره» از هر runner میخواهد هاب را روی پورت 443 و سرورهای دیگر را روی پورت‌های 22، 80 و 443 بسنجد؛ همین بررسی هر روز خودکار هم انجام میشود و ناظر اگر راهی که کار میکرد قطع شود خبر میدهد." /></p>
        </>
      )}
    </>
  );
}
