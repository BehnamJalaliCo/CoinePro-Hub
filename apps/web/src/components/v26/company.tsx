'use client';

// ⟨1.8⟩ The company page's «سرورها» tab (§26): locked when the company is stopped, its seal cards, its servers, a task and attaching one
// (Android: Servers.kt CompanyServers).

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Empty, ErrorState, Skeleton } from '@/components/ui/primitives';
import { byState, isOnline, useLocked, useServers } from '@/lib/api/v26';
import { Iso, LockedBanner, SealCards, ServerCard, ServersIntro, useServerSeals } from './bits';
import { ServerTaskSheet } from './task';

export function CompanyServers({ code }: { code: string }) {
  const q = useServers();
  const locked = useLocked(code);
  const seals = useServerSeals(code);
  const [task, setTask] = useState(false);
  const list = q.data?.filter((s) => s.company === code);
  const online = (list ?? []).filter(isOnline);
  return (
    <div className="flex max-w-4xl flex-col gap-4">
      {locked ? <LockedBanner company={code} /> : null}
      <ServersIntro />
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" icon="code" disabled={locked || !online.length} onClick={() => setTask(true)}>یک کار بسپار</Button>
        <Link href={`/servers/attach?company=${code}`} className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-strong px-4 text-[13px] font-semibold text-ink hover:bg-hover"><Icon name="add" size={18} />وصل کردن سرور</Link>
      </div>
      {seals.length ? <SealCards cards={seals} /> : null}
      {q.isLoading ? <Skeleton className="h-40 rounded-[16px]" />
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !list?.length ? <Empty icon="server" title="این شرکت هنوز سروری به هاب نداده" body={<Iso text="Claude سرور این شرکت runner ستاد را نصب میکند و یک کد کوتاه میدهد؛ با «وصل کردن سرور» همان کد را تأیید کن." />} />
        : <div className="grid grid-cols-1 gap-3 md:grid-cols-2 [&>*]:min-w-0">{byState(list).map((s) => <ServerCard key={s.id} s={s} locked={locked} />)}</div>}
      <p className="text-[11px] leading-5 text-muted"><Iso text="روی هر سرور runner ستاد با کاربر کاری همان سرور کار میکند و خودش با HTTPS به هاب وصل میشود؛ هاب به هیچ سروری وارد نمیشود، پورتی باز نمیشود و کلیدی از سرور دست هاب نیست. اعتبار هر runner هر ۲۴ ساعت عوض میشود و با «جدا کردن» همان لحظه باطل میشود." /></p>
      {list ? <ServerTaskSheet open={task} onOpenChange={setTask} servers={online} initial={null} /> : null}
    </div>
  );
}
