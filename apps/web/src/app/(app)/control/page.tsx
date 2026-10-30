'use client';

import Link from 'next/link';
import { Icon } from '@/components/icon';
import { ErrorState, PageHeader, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { BackupsCard } from '@/components/v14/backups';
import { CompanyControlCard, ControlSheets, HoldingControlCard, useControlData, useControlUi } from '@/components/v21/control';
import { useCompanies } from '@/lib/api/hooks';

/** Control (0.3.0; OPERATING_MODEL §1.12, contract §9): the holding's kill switch, the one that stops everything, then every company with
 *  its switch and its deploys — the same cards and sheets as the companies list. Stopping is instant (speed matters); resuming and opening
 *  deploys take the passkey; a switch the owner engaged is released only by the owner. Then backups and the authority matrix. */
export default function ControlPage() {
  const q = useCompanies();
  const d = useControlData();
  const ui = useControlUi();
  const list = q.data ?? [];
  const holding = list.find((c) => c.kind === 'holding');
  return (
    <>
      <PageHeader eyebrow="کلید توقف و deploy، برای کل هلدینگ و هر شرکت" title="کنترل" />
      {q.isLoading ? <div className="flex flex-col gap-4"><Skeleton className="h-[236px] max-w-3xl rounded-[16px]" /><Skeleton className="h-[222px] rounded-[16px]" /></div>
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
          <>
            {holding ? <div className="max-w-3xl"><HoldingControlCard holding={holding} all={list} d={d} ui={ui} /></div> : null}
            <SectionTitle title="شرکت‌ها" note="مدیرعامل هر شرکت هم میتواند کلید شرکت خودش را بزند؛ کلیدی را که تو زده‌ای فقط خودت آزاد میکنی." />
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {list.filter((c) => c.kind !== 'holding' && c.status !== 'archived').map((co) => <CompanyControlCard key={co.code} co={co} d={d} ui={ui} holdingName={holding?.name_fa} />)}
            </div>
          </>
        )}
      <BackupsCard />
      {/* ⟨1.5⟩ §20.7: who may do what, and up to how much, lives in the authority matrix. */}
      <Link href="/authority" className="flex items-center gap-3 rounded-[16px] bg-card p-4 transition-colors hover:bg-hover">
        <span className="flex size-10 items-center justify-center rounded-[12px] bg-tile text-gold-ink"><Icon name="lock" size={20} /></span>
        <span className="flex min-w-0 flex-1 flex-col"><span className="text-[14px] font-semibold">ماتریس اختیار</span><span className="text-[12px] text-muted">سقف‌ها، سهمیه‌ها و این‌که چه کسی تأیید میکند؛ ثابت‌های قفل مستقل از داده‌اند.</span></span>
        <Icon name="back" size={18} />
      </Link>
      <ControlSheets ui={ui} companies={list} />
    </>
  );
}
