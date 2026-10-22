'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, ErrorState, PageHeader, Pill, Skeleton } from '@/components/ui/primitives';
import { ScopeChips } from '@/components/v17/bits';
import { LicenceBadge, SERIES_STATUS } from '@/components/v19/bits';
import { ItemSheet, KindFilter, NeedsYou, NewItemSheet, PipelineBoard, StageCounts } from '@/components/v19/studio';
import { useMediaItems, useSeriesList, useVoices } from '@/lib/api/v19';
import { useScope } from '@/lib/scope';
import { jDateTime, until } from '@/lib/format';

function Overview() {
  const series = useSeriesList();
  const voices = useVoices();
  const xs = series.data ?? [];
  const next = xs.flatMap((s) => (s.next_at ?? []).map((at) => ({ at, s }))).sort((a, b) => a.at.localeCompare(b.at))[0];
  const active = voices.data?.find((v) => v.status === 'active');
  const counts = (['sealed', 'proposed', 'draft', 'paused'] as const).map((k) => [k, xs.filter((s) => s.status === k).length] as const).filter(([, n]) => n);
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Card className="flex flex-col gap-2 p-4">
        <span className="flex items-center gap-1.5 text-[12px] text-muted"><Icon name="time" size={14} />انتشار خودکار بعدی</span>
        {series.isLoading ? <Skeleton className="h-10" /> : next ? (
          <>
            <span className="text-[15px] font-semibold text-ink">{next.s.title_fa}</span>
            <span className="text-[12px] text-sec">{jDateTime(next.at)}، {until(next.at)} · <span className="fig">{next.s.ref}</span></span>
          </>
        ) : <span className="text-[13px] text-sec">برنامه‌ی مُهرشده‌ای در صف نیست.</span>}
      </Card>
      <Link href="/media/series" className="group">
        <Card className="flex h-full flex-col gap-2 p-4 transition-colors group-hover:bg-tile">
          <span className="flex items-center gap-1.5 text-[12px] text-muted"><Icon name="send" size={14} />برنامه‌های انتشار</span>
          <span className="flex flex-wrap gap-1.5">{counts.length ? counts.map(([k, n]) => <Pill key={k} tone={SERIES_STATUS[k]!.tone} icon={SERIES_STATUS[k]!.icon}>{n} {SERIES_STATUS[k]!.fa}</Pill>) : <span className="text-[13px] text-sec">هنوز برنامه‌ای نیست.</span>}</span>
          <span className="text-[12px] text-muted">مُهر روی برنامه است، نه روی هر پست؛ فقط آیتمی که همه‌ی چک‌ها را رد کند خودکار میرود.</span>
        </Card>
      </Link>
      <Link href="/media/voice" className="group">
        <Card className="flex h-full flex-col gap-2 p-4 transition-colors group-hover:bg-tile">
          <span className="flex items-center gap-1.5 text-[12px] text-muted"><Icon name="mic" size={14} />صدای فعال هاب</span>
          {voices.isLoading ? <Skeleton className="h-10" /> : active ? (
            <>
              <span className="text-[15px] font-semibold text-ink">{active.name_fa}</span>
              <span><LicenceBadge commercial={active.licence_commercial} licence={active.licence} /></span>
            </>
          ) : <span className="text-[13px] text-sec">هنوز صدایی فعال نیست.</span>}
        </Card>
      </Link>
    </div>
  );
}

function MediaInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { company: scope } = useScope();
  const [company, setCompany] = useState<string | null>(scope);
  const [kind, setKind] = useState<string | null>(null);
  const [making, setMaking] = useState(false);
  const open = params.get('item');
  const setOpen = (ref: string | null) => router.replace(ref ? `/media?item=${ref}` : '/media', { scroll: false });
  const q = useMediaItems({ company });
  const all = q.data?.pages.flatMap((p) => p.items) ?? [];
  const items = kind ? all.filter((x) => x.kind === kind) : all;
  return (
    <>
      <PageHeader eyebrow="هر شرکت، هر روز، بی‌دست تو؛ انتشار فقط از API رسمی تلگرام و اینستاگرام" title="استودیوی رسانه"
        actions={<Button variant="primary" icon="add" onClick={() => setMaking(true)}>آیتم یک‌باره</Button>}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">سناریو، کارگردانی، موشن‌گرافیک به‌صورت کد، صدای ساخته‌ی خود هاب، رندر در سندباکس، چک‌های کدی و بازبینی مدیر رسانه. برنامه‌ی مُهرشده خودش منتشر میکند؛ هر چک ردشده یا هر چیزی بیرون از برنامه کارت توست.</p>
      </PageHeader>
      <Overview />
      <div className="flex flex-col gap-3">
        <ScopeChips value={company} onChange={setCompany} holding={false} allLabel="همه‌ی شرکت‌ها" />
        <KindFilter value={kind} onChange={setKind} />
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <>
          <StageCounts items={items} />
          <NeedsYou items={items} onOpen={setOpen} />
          <PipelineBoard items={items} loading={q.isLoading} onOpen={setOpen} />
        </>
      )}
      {open ? <ItemSheet refId={open} onClose={() => setOpen(null)} /> : null}
      {making ? <NewItemSheet onClose={() => setMaking(false)} onMade={(r) => { setMaking(false); setOpen(r); }} /> : null}
    </>
  );
}

/** استودیوی رسانه (contract §22.2): each company's pipeline, item by item, from script to the official API. */
export default function MediaPage() {
  return <Suspense><MediaInner /></Suspense>;
}
