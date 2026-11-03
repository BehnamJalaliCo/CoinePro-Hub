'use client';

// ⟨1.11⟩ Contract §29.9 «آمادگی»: is this company ready for this working group? Each check (seats filled, hiring automatic, the month's
// envelope, a sealed series per channel, channels connected, the media tools, the players, the company server's assistant), green or
// not, and every failed one with its fix in one tap.

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Card, Empty, ErrorState, FilterChip, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useGroups, useReadiness, useReadinessFix } from '@/lib/api/v29';
import { cx } from '@/lib/format';
import { FaPara, FaText, FixButton } from './bits';

export function CompanyReadiness({ code, group: initial }: { code: string; group?: string | null }) {
  const groups = useGroups();
  const [group, setGroup] = useState(initial || 'content');
  const q = useReadiness(code, group);
  const fix = useReadinessFix(code, group);
  const r = q.data;
  const bad = r?.checks.filter((c) => !c.ok).length ?? 0;
  return (
    <div className="flex flex-col gap-3">
      {(groups.data?.length ?? 0) > 1 ? (
        <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1" role="group" aria-label="کارگروه">
          {groups.data!.map((g) => <FilterChip key={g.key} selected={group === g.key} onClick={() => setGroup(g.key)}>{g.title_fa}</FilterChip>)}
        </div>
      ) : null}
      {q.isLoading ? <Skeleton className="h-72 rounded-[16px]" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !r ? (
        <Card><Empty icon="seal" title="آمادگی هنوز سنجیده نمیشود" body="بعد از به‌روزرسانی ستاد، هر کمبود این شرکت برای کارگروه با دکمه‌ی رفعش این‌جا میاید." /></Card>
      ) : (
        <Card className={cx('flex flex-col gap-3 p-5', r.ready && 'tahrir')} aria-label="آمادگی">
          <SectionTitle title={groups.data?.find((g) => g.key === r.group)?.title_fa ?? 'آمادگی'}
            note={r.ready ? 'همه‌چیز آماده است' : <><span className="fig">{bad}</span> کمبود، هر کدام با دکمه‌ی رفعش</>}
            action={<Pill tone={r.ready ? 'pos' : 'warn'} icon={r.ready ? 'seal' : 'urgent'}>{r.ready ? 'آماده' : 'هنوز آماده نیست'}</Pill>} />
          <ul className="flex flex-col">
            {r.checks.map((c) => (
              <li key={c.key} className="flex flex-wrap items-start gap-3 border-t border-div py-3 first:border-0" aria-label={`${c.title_fa}: ${c.ok ? 'آماده' : 'کمبود'}`}>
                <span className={cx('mt-0.5 flex size-7 flex-none items-center justify-center rounded-full', c.ok ? 'bg-pos-soft text-pos' : 'bg-warn-soft text-warn')}>
                  <Icon name={c.ok ? 'seal' : 'urgent'} size={15} active={c.ok} />
                </span>
                <span className="flex min-w-0 flex-[1_1_14rem] flex-col gap-0.5">
                  <span className={cx('text-[14px] font-semibold', !c.ok && 'text-ink')}><FaText text={c.title_fa} /></span>
                  <FaPara text={c.detail_fa} className="text-[12px] leading-5 text-sec" />
                </span>
                {!c.ok && c.fix ? <FixButton fix={c.fix} company={code} run={(f) => fix.mutateAsync(f)} /> : null}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
