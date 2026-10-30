'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Card, ErrorState, PageHeader, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { CompanyControlCard, ControlSheets, HoldingControlCard, useControlData, useControlUi } from '@/components/v21/control';
import { useCompanies } from '@/lib/api/hooks';

/** Companies are data (0.3.0): the holding first, then every company, each with its live state at a glance (running, stopped, deploys
 *  closed), whether its agents are working right now, today's spend and its counts, and the switches to stop, resume, close or open
 *  deploys (contract §9); ⋯ (or a right click) opens every action on the company. One way to a new company: the founding wizard (0.5.0). */
export default function CompaniesPage() {
  const router = useRouter();
  const q = useCompanies();
  const d = useControlData();
  const ui = useControlUi();
  const list = q.data ?? [];
  const holding = list.find((c) => c.kind === 'holding');
  const running = list.filter((c) => c.kind !== 'holding' && c.status !== 'archived');
  const archived = list.filter((c) => c.status === 'archived');
  return (
    <>
      <PageHeader eyebrow="هلدینگ و شرکت‌هایش، زنده" title="شرکت‌ها" actions={<Button variant="primary" icon="found" onClick={() => router.push('/founding/new')}>تأسیس شرکت</Button>} />
      {q.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[236px] rounded-[16px]" />)}</div>
      ) : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <>
          {holding ? <div className="max-w-3xl"><HoldingControlCard holding={holding} all={list} d={d} ui={ui} /></div> : null}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {running.map((co) => <CompanyControlCard key={co.code} co={co} d={d} ui={ui} holdingName={holding?.name_fa} />)}
          </div>
          {/* An archived company (one with a history the owner no longer runs) stays reachable, apart, without its switches. */}
          {archived.length ? (
            <Card className="flex flex-col gap-1 p-4">
              <SectionTitle title="بایگانی‌شده" note="سوابقشان میماند؛ در گزارش‌ها و ستاره‌ها نیستند" />
              {archived.map((co) => (
                <Link key={co.code} href={`/companies/${co.code}`} className="flex items-center gap-3 rounded-[10px] px-2 py-2 text-sec hover:bg-hover">
                  <CompanyMark code={co.code} height={14} mono />
                  <span className="flex-1 text-[14px]">{co.name_fa ?? co.code}</span>
                  <span className="fig text-[12px] text-muted">{co.code}</span>
                </Link>
              ))}
            </Card>
          ) : null}
        </>
      )}
      <ControlSheets ui={ui} companies={list} />
    </>
  );
}
