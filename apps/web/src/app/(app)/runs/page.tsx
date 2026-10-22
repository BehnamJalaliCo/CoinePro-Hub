'use client';

import { useState } from 'react';
import { Card, ErrorState, FilterChip, PageHeader, Skeleton, StatTile } from '@/components/ui/primitives';
import { RunList } from '@/components/v15/runs';
import { ClaimsCard, HealthBoard } from '@/components/v18/health';
import { useRuns, type RunState } from '@/lib/api/v15';
import { usd } from '@/lib/format';
import { useScope } from '@/lib/scope';

const TABS: Array<{ id: RunState | null; fa: string }> = [{ id: null, fa: 'همه' }, { id: 'running', fa: 'در جریان' }, { id: 'failed', fa: 'شکست' }, { id: 'refused', fa: 'رد شده' }, { id: 'queued', fa: 'در صف' }];

/** Every agent run, live (§16.2): steps, tools and usage; ⟨1.5⟩ and the health board of §21.9 (refuted claims, failures, loops). */
export default function RunsPage() {
  const { company } = useScope();
  const [tab, setTab] = useState<RunState | null>(null);
  const all = useRuns({ company, limit: 200 });
  const list = useRuns({ company, state: tab, limit: 100 });
  const items = all.data?.items ?? [];
  const live = items.filter((r) => r.state === 'running').length;
  const bad = items.filter((r) => r.state === 'failed' || r.state === 'refused').length;
  return (
    <>
      <PageHeader eyebrow="هر اجرای هر ایجنت، با قدم‌ها و ابزارها و مصرف" title="اجرای ایجنت‌ها" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="اجرای اخیر" value={items.length} />
        <StatTile label="در جریان" value={live} />
        <StatTile label="شکست یا رد" value={bad} tone={bad ? 'warn' : undefined} />
        <StatTile label="مصرف" value={<span className="fig">{usd(items.reduce((n, r) => n + Number(r.equiv_cost_usd), 0))}</span>} />
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card className="flex flex-col gap-3 p-4">
          <div className="flex flex-wrap gap-2">{TABS.map((t) => <FilterChip key={t.fa} selected={tab === t.id} onClick={() => setTab(t.id)}>{t.fa}</FilterChip>)}</div>
          {list.isLoading ? <Skeleton className="h-60" /> : list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
            : <RunList runs={list.data?.items ?? []} empty="اجرایی با این وضعیت نیست." />}
        </Card>
        <ClaimsCard company={company} />
      </div>
      <HealthBoard company={company} />
    </>
  );
}
