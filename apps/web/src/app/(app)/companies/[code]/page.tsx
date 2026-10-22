'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, use, useState } from 'react';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { BrandBlock } from '@/components/brand/brand-block';
import { Seal } from '@/components/brand/seal';
import { Card, Empty, ErrorState, PageHeader, Pill, Segmented, Skeleton } from '@/components/ui/primitives';
import { DepartmentRanks, HrRoundLine } from '@/components/v18/people';
import { DepartmentSheet, RoleDraftSheet, RolesOnDemand } from '@/components/v19/org';
import { useCompany, useEmployees, useOrgChart, useWorkList } from '@/lib/api/hooks';
import { useDepartments19 } from '@/lib/api/v19';
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

function CompanyInner({ code }: { code: string }) {
  const router = useRouter();
  const search = useSearchParams();
  const company = useCompany(code);
  // ⟨1.6⟩ §22.1: each department with its mandate, identity and starting team.
  const deps = useDepartments19(code);
  const chart = useOrgChart(code);
  const emps = useEmployees({ company: [code] });
  const work = useWorkList({ company: [code] });
  const [tab, setTab] = useState<'overview' | 'people' | 'work' | 'brand'>(search.get('role') ? 'people' : 'overview');
  const dept = search.get('dept');
  const role = search.get('role');
  const go = (q: { dept?: string | null; role?: string | null }) => {
    const next = new URLSearchParams();
    const d = q.dept === undefined ? dept : q.dept;
    const r = q.role === undefined ? role : q.role;
    if (d) next.set('dept', d);
    if (r) next.set('role', r);
    router.replace(`/companies/${code}${next.size ? `?${next}` : ''}`, { scroll: false });
  };
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
      {/* ⟨1.4.6⟩ the company's brand and seal are data (§18.14); the holding's own seal is fixed and is not. */}
      <div className="max-w-xl"><Segmented label="بخش" value={tab} onChange={setTab} options={[{ value: 'overview', label: 'دپارتمان‌ها' }, { value: 'people', label: 'کارمندها' }, { value: 'work', label: 'کارها' }, ...(c && c.kind !== 'holding' ? [{ value: 'brand' as const, label: 'نشان و مُهر' }] : [])]} /></div>

      {tab === 'overview' ? (
        <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div className="grid gap-3 sm:grid-cols-2">
            {deps.isLoading ? Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-24 rounded-[16px]" />)
              : (deps.data ?? []).map((d) => {
                const staff = (emps.data?.items ?? []).filter((e) => e.department === d.code);
                const active = staff.filter((e) => e.activity === 'working').length;
                return (
                  <button key={d.code} type="button" onClick={() => go({ dept: d.code })} aria-label={`${d.name_fa}: مأموریت، شخصیت و نقش‌ها`} className="group min-w-0 text-start">
                    <Card className="flex h-full items-center gap-3 p-4 transition-colors group-hover:bg-tile">
                      <span className="flex size-11 flex-none items-center justify-center rounded-[12px] bg-tile text-silver-ink"><Icon name={DEPT_ICON[d.code] ?? 'department'} size={22} /></span>
                      <div className="flex min-w-0 flex-1 flex-col">
                        <span className="text-[14px] font-semibold">{d.name_fa}</span>
                        <span className="text-[12px] text-muted">{d.manager_title_fa}، {staff.length} نفر{active ? `، ${active} در حال کار` : ''}</span>
                        {d.mandate ? <span className="truncate text-[11px] text-muted" title={d.mandate.to_fa}>مقصد: {d.mandate.to_fa}</span> : null}
                      </div>
                      {active ? <span className="size-2 rounded-full bg-pos" style={{ animation: 'hq-live 1.4s infinite' }} /> : null}
                    </Card>
                  </button>
                );
              })}
          </div>
          <div className="flex min-w-0 flex-col gap-4">
            {/* ⟨1.5⟩ §21.5: the departments' rank and the latest monthly HR round. */}
            <DepartmentRanks company={code} />
            <HrRoundLine company={code} />
            <Card className="p-4">
              <h2 className="pb-2 text-[14px] font-semibold">چارت سازمانی</h2>
              {chart.isLoading ? <Skeleton className="h-64" /> : chart.data?.roots.length ? <ul className="flex flex-col gap-1">{chart.data.roots.map((n) => <OrgNode key={n.code} n={n} />)}</ul> : <Empty icon="department" title="هنوز کسی نیست" />}
            </Card>
          </div>
        </div>
      ) : tab === 'brand' && c ? (
        <Card className="p-4"><BrandBlock code={c.code} nameFa={c.name_fa ?? c.code} nameEn={c.name_en ?? c.code} /></Card>
      ) : tab === 'people' ? (
        <>
        {/* ⟨1.6⟩ §22.5: roles a department's manager wrote beyond the template. */}
        <RolesOnDemand company={code} onOpen={(r) => go({ role: r })} />
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
        </>
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
      {dept ? <DepartmentSheet company={code} code={dept} onClose={() => go({ dept: null })} onRole={(r) => go({ role: r })} /> : null}
      {role ? <RoleDraftSheet refId={role} onClose={() => go({ role: null })} /> : null}
    </>
  );
}

export default function CompanyPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  return <Suspense><CompanyInner code={code} /></Suspense>;
}
