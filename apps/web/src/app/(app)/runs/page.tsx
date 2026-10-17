'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { Card, ErrorState, FilterChip, PageHeader, SectionTitle, Skeleton, StatTile } from '@/components/ui/primitives';
import { RunList } from '@/components/v15/runs';
import { useRuns, type Run, type RunState } from '@/lib/api/v15';
import { cx, tokens, usd } from '@/lib/format';
import { useScope } from '@/lib/scope';

const TABS: Array<{ id: RunState | null; fa: string }> = [{ id: null, fa: 'همه' }, { id: 'running', fa: 'در جریان' }, { id: 'failed', fa: 'شکست' }, { id: 'refused', fa: 'رد شده' }, { id: 'queued', fa: 'در صف' }];

/** Health of the digital workforce per employee, from its recent runs (M16): failures, refusals, retries, cost. */
function health(runs: Run[]) {
  const by = new Map<string, { code: string; company: string; runs: number; failed: number; refused: number; retries: number; tokens: number; usd: number }>();
  for (const r of runs) {
    const h = by.get(r.employee) ?? { code: r.employee, company: r.company, runs: 0, failed: 0, refused: 0, retries: 0, tokens: 0, usd: 0 };
    h.runs++; if (r.state === 'failed') h.failed++; if (r.state === 'refused') h.refused++; if (r.trigger === 'retry') h.retries++;
    h.tokens += r.tokens.input + r.tokens.output; h.usd += Number(r.equiv_cost_usd);
    by.set(r.employee, h);
  }
  return [...by.values()].sort((a, b) => (b.failed + b.refused) / b.runs - (a.failed + a.refused) / a.runs || b.runs - a.runs);
}

/** Every agent run, live (§16.2): steps, tools and usage; and a health board of who fails, who is refused, who retries. */
export default function RunsPage() {
  const { company } = useScope();
  const [tab, setTab] = useState<RunState | null>(null);
  const all = useRuns({ company, limit: 200 });
  const list = useRuns({ company, state: tab, limit: 100 });
  const board = useMemo(() => health(all.data?.items ?? []), [all.data]);
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
        <Card className="flex flex-col gap-3 p-4">
          <SectionTitle title="سلامت کارمندها" note="از اجراهای اخیر؛ بدترین بالا" />
          {all.isLoading ? <Skeleton className="h-48" /> : !board.length ? <p className="py-4 text-center text-[13px] text-muted">هنوز اجرایی نیست.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[420px] border-collapse text-[12px]">
                <thead><tr className="text-right text-[11px] text-muted">{['کارمند', 'اجرا', 'شکست', 'رد', 'تکرار', 'مصرف'].map((h) => <th key={h} className="px-2 py-1.5 font-semibold">{h}</th>)}</tr></thead>
                <tbody>
                  {board.map((h) => {
                    const rate = (h.failed + h.refused) / h.runs;
                    return (
                      <tr key={h.code} className="h-10 border-t border-div">
                        <td className="px-2"><Link href={`/employees/${h.code}`} className="fig font-semibold text-ink hover:underline">{h.code}</Link></td>
                        <td className="fig px-2 text-sec">{h.runs}</td>
                        <td className={cx('fig px-2', h.failed ? 'text-neg' : 'text-muted')}>{h.failed}</td>
                        <td className={cx('fig px-2', h.refused ? 'text-warn' : 'text-muted')}>{h.refused}</td>
                        <td className={cx('fig px-2', h.retries ? 'text-warn' : 'text-muted')}>{h.retries}</td>
                        <td className="fig px-2 text-sec" title={`${Math.round(rate * 100)}% شکست یا رد`}>{tokens(h.tokens)} · {usd(h.usd)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-[12px] leading-5 text-muted">شکست یعنی اجرا نتیجه نداد؛ رد یعنی سیاست یا بودجه جلویش را گرفت. ناظر کل همین الگوها را در پروتکل‌هایش میسنجد.</p>
        </Card>
      </div>
    </>
  );
}
