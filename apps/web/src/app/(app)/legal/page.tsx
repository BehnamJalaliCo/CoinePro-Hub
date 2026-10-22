'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button, IconButton } from '@/components/ui/button';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, Skeleton } from '@/components/ui/primitives';
import { ScopeChips } from '@/components/v17/bits';
import { CASE_STATUS } from '@/components/v19/bits';
import { CaseDetail, CaseRow, CasesEmpty, NewCase } from '@/components/v19/legal';
import { useAccounts } from '@/lib/api/v14';
import { useCases, type CaseStatus } from '@/lib/api/v19';
import { cx } from '@/lib/format';

const STATUSES: Array<CaseStatus | null> = [null, 'waiting_owner', 'open', 'waiting_reply', 'resolved', 'closed'];

function Mailbox() {
  const q = useAccounts();
  const mail = q.data?.find((a) => a.key === 'mail');
  if (!q.data) return null;
  return (
    <p className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
      <Icon name="send" size={14} />صندوق ایمیل مشاور:
      {mail?.has_secret ? <Pill tone="pos" dot>وصل</Pill> : <Pill tone="warn" dot>وصل نیست؛ تا وصل نشود پیش‌نویس‌ها فقط کارت‌اند</Pill>}
      <span className="text-muted">ورود فقط با <span dir="ltr" className="fig">make account-secret</span> روی سرور، به دست خودت.</span>
    </p>
  );
}

function LegalInner() {
  const params = useSearchParams();
  const router = useRouter();
  const sel = params.get('case');
  const [company, setCompany] = useState<string | null>(null);
  const [status, setStatus] = useState<CaseStatus | null>(null);
  const [making, setMaking] = useState(false);
  const q = useCases({ company, status });
  const cases = q.data?.pages.flatMap((p) => p.items) ?? [];
  const open = (ref: string | null) => router.replace(ref ? `/legal?case=${ref}` : '/legal', { scroll: false });
  return (
    <>
      <PageHeader eyebrow="یک مشاور برای همه‌ی شرکت‌ها؛ فقط کانال رسمی، و هر ایمیل با مُهر تو روی همان پیام" title="مشاور حقوقی"
        actions={<>
          <Link href="/messages?thread=L" className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-strong px-4 text-[13px] font-semibold text-ink hover:bg-hover"><Icon name="messages" size={18} />رشته‌ی L</Link>
          <Button variant="primary" icon="add" onClick={() => setMaking(true)}>پرونده‌ی تازه</Button>
        </>}>
        <Mailbox />
      </PageHeader>
      <div className="flex flex-col gap-3">
        <ScopeChips value={company} onChange={setCompany} allLabel="همه" />
        <div className="flex flex-wrap gap-1.5">{STATUSES.map((s) => <FilterChip key={s ?? 'all'} selected={status === s} onClick={() => setStatus(s)}>{s ? CASE_STATUS[s]!.fa : 'همه'}</FilterChip>)}</div>
      </div>
      <div className="grid min-h-[60dvh] items-start gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Card className={cx('flex flex-col gap-1 p-2', sel && 'hidden lg:flex')}>
          {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="m-1 h-20" />)
            : !cases.length ? <CasesEmpty /> : cases.map((c) => <CaseRow key={c.ref} c={c} selected={sel === c.ref} onOpen={() => open(c.ref)} />)}
        </Card>
        <Card className={cx('flex min-w-0 flex-col gap-3 p-4 md:p-5', !sel && 'hidden lg:flex')}>
          {sel ? (
            <>
              <div className="lg:hidden"><IconButton icon="back" label="برگشت به فهرست" mirror onClick={() => open(null)} /></div>
              <CaseDetail refId={sel} />
            </>
          ) : <Empty icon="decision" title="یک پرونده را انتخاب کن" body="روند، مهلت‌ها و رشته‌ی ایمیل هر پرونده اینجاست؛ ایمیل منتظر مُهر بالای همه." />}
        </Card>
      </div>
      {making ? <NewCase onClose={() => setMaking(false)} onMade={(r) => { setMaking(false); open(r); }} /> : null}
    </>
  );
}

/** مشاور حقوقی (contract §22.4): the holding's cases LC-…, their timeline and deadlines, and every outgoing email sealed on the exact message. */
export default function LegalPage() {
  return <Suspense><LegalInner /></Suspense>;
}
