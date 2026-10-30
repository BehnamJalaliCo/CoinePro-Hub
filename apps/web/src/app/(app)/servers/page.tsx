'use client';

// ⟨1.8⟩ «همه‌ی سرورها» (contract §26): every company's servers, the cards waiting for the seal first, then each company's servers.

import Link from 'next/link';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Empty, ErrorState, PageHeader, SectionTitle, Skeleton, StatTile } from '@/components/ui/primitives';
import { Iso, SealCards, ServerCardFor, ServersIntro, useServerSeals } from '@/components/v26/bits';
import { NetworkLink } from '@/components/v26/network';
import { useCompanies } from '@/lib/api/hooks';
import { byState, isOnline, useServers, type HubServer } from '@/lib/api/v26';
import { companyOf } from '@/lib/company';

const attach = (
  <Link href="/servers/attach" className="inline-flex h-8 items-center gap-1.5 rounded-[8px] bg-gold px-3 text-[12px] font-bold text-on-gold hover:bg-gold-bright"><Icon name="add" size={16} />وصل کردن</Link>
);

export default function ServersPage() {
  const q = useServers();
  const { data: companies } = useCompanies();
  const seals = useServerSeals();
  const list = q.data;
  // Companies are data: one group per company that has servers, in the companies' own order.
  const order = (companies ?? []).map((c) => c.code);
  const groups = new Map<string, HubServer[]>();
  for (const s of byState(list ?? [])) groups.set(s.company, [...(groups.get(s.company) ?? []), s]);
  const sorted = [...groups].sort(([a], [b]) => (order.indexOf(a) < 0 ? 1e9 : order.indexOf(a)) - (order.indexOf(b) < 0 ? 1e9 : order.indexOf(b)));
  return (
    <>
      <PageHeader eyebrow="دسترسی کامل هلدینگ به سرورهای شرکت‌ها" title="همه‌ی سرورها" actions={attach} />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <ServersIntro />
        {/* §26.6: how every server reaches the hub and the others, in one line, and the map a click away. */}
        <NetworkLink />
      </div>
      {list?.length ? (
        <div className="grid grid-cols-3 gap-3">
          <StatTile label="سرور" value={list.length} />
          <StatTile label="آنلاین" value={list.filter(isOnline).length} tone="pos" />
          <StatTile label="منتظر مُهر" value={seals.length} tone={seals.length ? 'warn' : undefined} />
        </div>
      ) : null}
      {seals.length ? <SealCards cards={seals} /> : null}
      {q.isLoading ? <div className="grid gap-3 md:grid-cols-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-[150px] rounded-[16px]" />)}</div>
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !list?.length ? (
          <Empty icon="server" title="هنوز سروری وصل نیست" body={<Iso text="Claude هر سرور runner ستاد را نصب میکند و یک کد کوتاه میدهد؛ با «وصل کردن» همان کد را اینجا تأیید کن." />}
            action={<Link href="/servers/attach" className="inline-flex h-10 items-center gap-2 rounded-[10px] bg-gold px-4 text-[13px] font-bold text-on-gold"><Icon name="add" size={18} />وصل کردن سرور</Link>} />
        ) : sorted.map(([co, servers]) => (
          <section key={co} className="flex flex-col gap-3" aria-label={companyOf(companies, co).nameFa}>
            <SectionTitle title={<span className="flex items-center gap-2"><span className="text-sec"><CompanyMark code={co} height={14} mono /></span>{companyOf(companies, co).nameFa}</span>} note={`${servers.length} سرور`} />
            <div className="grid gap-3 md:grid-cols-2">{servers.map((s) => <ServerCardFor key={s.id} s={s} />)}</div>
          </section>
        ))}
    </>
  );
}
