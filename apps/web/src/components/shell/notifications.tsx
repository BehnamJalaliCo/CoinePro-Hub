'use client';

import Link from 'next/link';
import { Icon } from '@/components/icon';
import { Sheet } from '@/components/ui/overlay';
import { Button } from '@/components/ui/button';
import { Empty, Skeleton } from '@/components/ui/primitives';
import { CompanyMark } from '@/components/brand/marks';
import { useNotifications, useReadAll } from '@/lib/api/hooks';
import { LEVEL } from '@/lib/labels';
import { ago, cx } from '@/lib/format';

const href = (l: { kind: string; ref: string } | null | undefined) =>
  !l ? null : l.kind === 'decision' ? `/cartable?ref=${l.ref}` : l.kind === 'deliverable' ? `/outputs?ref=${l.ref}` : l.kind === 'work' ? `/work/${l.ref}` : l.kind === 'message' ? '/messages' : null;

const TONE: Record<string, string> = { neg: 'text-neg bg-neg-soft', warn: 'text-warn bg-warn-soft', lapis: 'text-lapis bg-lapis-soft', pos: 'text-pos bg-pos-soft', learn: 'text-learn bg-learn-soft' };

export function NotificationsSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const q = useNotifications({ limit: 50 });
  const readAll = useReadAll();
  const items = q.data?.items ?? [];
  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="اعلان‌ها"
      description="فوری همیشه میرسد؛ تصمیم‌ها دسته‌ای؛ بقیه بی‌صدا."
      width={440}
      footer={<Button variant="text" icon="seal" onClick={() => readAll.mutate()} loading={readAll.isPending} disabled={!items.some((n) => !n.read_at)}>همه را خواندم</Button>}
    >
      {q.isLoading ? (
        <div className="flex flex-col gap-3">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : items.length === 0 ? (
        <Empty icon="bell" title="اعلانی نیست" body="هر چیزی که به تو مربوط باشد این‌جا میاید." />
      ) : (
        <ul className="flex flex-col gap-1">
          {items.map((n) => {
            const lv = LEVEL[n.level] ?? LEVEL.info!;
            const to = href(n.link as never);
            const body = (
              <div className={cx('flex gap-3 rounded-[12px] p-3 transition-colors', to && 'hover:bg-hover', !n.read_at && 'bg-tile')}>
                <span className={cx('flex size-9 flex-none items-center justify-center rounded-full', TONE[lv.tone])}><Icon name={lv.icon} size={18} /></span>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <div className="flex items-center gap-2">
                    <span className={cx('flex-1 truncate text-[14px]', n.read_at ? 'text-sec' : 'font-semibold text-ink')}>{n.title_fa}</span>
                    {!n.read_at ? <span className="size-2 flex-none rounded-full bg-gold" aria-label="خوانده‌نشده" /> : null}
                  </div>
                  <span className="text-[12px] leading-5 text-muted">{n.body_fa}</span>
                  <span className="flex items-center gap-2 text-[11px] text-muted"><span className="text-sec"><CompanyMark code={n.company} height={12} mono /></span>{lv.fa}، {ago(n.created_at)}</span>
                </div>
              </div>
            );
            return <li key={n.id}>{to ? <Link href={to} onClick={() => onOpenChange(false)}>{body}</Link> : body}</li>;
          })}
        </ul>
      )}
    </Sheet>
  );
}
