'use client';

import Link from 'next/link';
import { use, useState } from 'react';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { Seal } from '@/components/brand/seal';
import { Card, Empty, ErrorState, PageHeader, Pill, Segmented, Skeleton } from '@/components/ui/primitives';
import { useCompany, useDepartments, useEmployees, useOrgChart, useWorkList } from '@/lib/api/hooks';
import { ACTIVITY, DEPT_ICON, WORK_STATUS } from '@/lib/labels';
import { ago, cx, jDate, modelLabel } from '@/lib/format';
import type { Schemas } from '@/lib/api/client';

type Node = Schemas['ChartNode'];

function OrgNode({ n, depth = 0 }: { n: Node; depth?: number }) {
  return (
    <li className="flex flex-col gap-2">
      <Link href={`/employees/${n.code}`} className="flex items-center gap-3 rounded-[12px] p-2 hover:bg-hover">
        <Avatar kind={n.kind} dept={n.department} state={n.activity} size={depth === 0 ? 44 : 36} />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[14px] font-semibold">{n.display_name ?? n.title_fa}</span>
          <span className="text-[11px] text-muted"><span className="fig">{n.code}</span>، {ACTIVITY[n.activity] ?? n.activity}</span>
        </div>
      </Link>
      {n.children.length ? (
        <ul className="mr-6 flex flex-col gap-1 border-r border-div pr-3">{n.children.map((c) => <OrgNode key={c.code} n={c} depth={depth + 1} />)}</ul>
      ) : null}
    </li>
  );
}

export default function CompanyPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const company = useCompany(code);
  const deps = useDepartments(code);
  const chart = useOrgChart(code);
  const emps = useEmployees({ company: [code] });
  const work = useWorkList({ company: [code] });
  const [tab, setTab] = useState<'overview' | 'people' | 'work'>('overview');
  const c = company.data;
  if (company.error) return <ErrorState error={company.error} onRetry={() => company.refetch()} />;
  return (
    <>
      <div className="flex flex-wrap items-center gap-5">
        {c ? <Seal code={c.code} nameFa={c.name_fa ?? c.code} nameEn={c.name_en ?? c.code} holding={c.kind === 'holding'} size={96} /> : <Skeleton className="size-24 rounded-full" />}
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <PageHeader eyebrow={<Link href="/companies" className="hover:text-ink">شرکت‌ها</Link>} title={c?.name_fa ?? '…'} />
          <div className="flex flex-wrap items-center gap-2">
            <span className="fig text-[12px] text-muted">{c?.name_en} · {code}</span>
            {c?.kill_switch === 'engaged' ? <Pill tone="neg" icon="lock">کلید توقف روشن</Pill> : <Pill tone="pos" dot>فعال</Pill>}
            {c?.deploy_freeze_until && new Date(c.deploy_freeze_until) > new Date() ? <Pill tone="warn" icon="pause">توقف deploy</Pill> : null}
          </div>
        </div>
        <Link href="/control" className="text-[13px] text-sec hover:text-ink"><span className="inline-flex items-center gap-1.5"><Icon name="lock" size={16} />کنترل</span></Link>
      </div>
      <div className="max-w-md"><Segmented label="بخش" value={tab} onChange={setTab} options={[{ value: 'overview', label: 'دپارتمان‌ها' }, { value: 'people', label: 'کارمندها' }, { value: 'work', label: 'کارها' }]} /></div>

      {tab === 'overview' ? (
        <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div className="grid gap-3 sm:grid-cols-2">
            {deps.isLoading ? Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-24 rounded-[16px]" />)
              : (deps.data ?? []).map((d) => {
                const staff = (emps.data?.items ?? []).filter((e) => e.department === d.code);
                const active = staff.filter((e) => e.activity === 'working').length;
                return (
                  <Card key={d.code} className="flex items-center gap-3 p-4">
                    <span className="flex size-11 flex-none items-center justify-center rounded-[12px] bg-tile text-silver-ink"><Icon name={DEPT_ICON[d.code] ?? 'department'} size={22} /></span>
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="text-[14px] font-semibold">{d.name_fa}</span>
                      <span className="text-[12px] text-muted">{d.manager_title_fa}، {staff.length} نفر{active ? `، ${active} در حال کار` : ''}</span>
                    </div>
                    {active ? <span className="size-2 rounded-full bg-pos" style={{ animation: 'hq-live 1.4s infinite' }} /> : null}
                  </Card>
                );
              })}
          </div>
          <Card className="p-4">
            <h2 className="pb-2 text-[14px] font-semibold">چارت سازمانی</h2>
            {chart.isLoading ? <Skeleton className="h-64" /> : chart.data?.roots.length ? <ul className="flex flex-col gap-1">{chart.data.roots.map((n) => <OrgNode key={n.code} n={n} />)}</ul> : <Empty icon="department" title="هنوز کسی نیست" />}
          </Card>
        </div>
      ) : tab === 'people' ? (
        <Card className="overflow-x-auto p-2">
          <table className="w-full min-w-[640px] border-collapse text-[13px]">
            <thead><tr className="text-right text-[11px] text-muted">{['کارمند', 'دپارتمان', 'وضعیت', 'مدل', 'نمره'].map((h) => <th key={h} className="px-3 py-2 font-semibold">{h}</th>)}</tr></thead>
            <tbody>
              {(emps.data?.items ?? []).map((e) => (
                <tr key={e.code} className="h-[52px] border-t border-div hover:bg-hover">
                  <td className="px-3"><Link href={`/employees/${e.code}`} className="flex items-center gap-2.5"><Avatar kind={e.kind} dept={e.department} state={e.activity} size={32} /><span className="flex flex-col"><span className="font-semibold">{e.display_name ?? e.title_fa}</span><span className="fig text-[11px] text-muted">{e.code}</span></span></Link></td>
                  <td className="fig px-3 text-sec">{e.department ?? '—'}</td>
                  <td className="px-3 text-sec">{ACTIVITY[e.activity] ?? e.activity}</td>
                  <td className="fig px-3 text-[12px] text-sec">{e.model ? `${modelLabel(String(e.model.model ?? ''))} · ${e.model.effort ?? ''}` : '—'}</td>
                  <td className="px-3">{e.score.value != null ? e.score.value.toFixed(1).replace('.', '٫') : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <Card className="flex flex-col gap-1 p-2">
          {(work.data?.items ?? []).length ? (work.data?.items ?? []).map((w) => (
            <Link key={w.id} href={`/work/${w.id}`} className="flex items-center gap-3 rounded-[12px] p-3 hover:bg-hover">
              <span className={cx('fig flex h-6 w-9 items-center justify-center rounded-[6px] text-[11px] font-bold', w.priority <= 'P1' ? 'bg-neg-soft text-neg' : 'bg-tile text-sec')}>{w.priority}</span>
              <div className="flex min-w-0 flex-1 flex-col"><span className="truncate text-[14px] font-semibold">{w.title}</span><span className="text-[11px] text-muted"><span className="fig">{w.ref}</span>، {w.assignee?.title_fa ?? 'بدون مسئول'}، {ago(w.updated_at)}</span></div>
              {w.overdue ? <Pill tone="neg">عقب‌افتاده</Pill> : null}
              <span className="text-[12px] text-sec">{WORK_STATUS[w.status] ?? w.status}</span>
              {w.due_at ? <span className="hidden text-[12px] text-muted sm:inline">{jDate(w.due_at)}</span> : null}
            </Link>
          )) : <Empty icon="task" title="کار بازی نیست" />}
        </Card>
      )}
    </>
  );
}
