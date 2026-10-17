'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import { Avatar, Orb } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Chat } from '@/components/chat/chat';
import { Card, Empty, ErrorState, PageHeader, Skeleton } from '@/components/ui/primitives';
import { IconButton } from '@/components/ui/button';
import { useThreads } from '@/lib/api/hooks';
import { useScope } from '@/lib/scope';
import { ago, cx } from '@/lib/format';

function MessagesInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { company } = useScope();
  const q = useThreads();
  const threads = (q.data ?? []).filter((t) => !company || t.company === company || ['advisor', 'overseer', 'assistant'].includes(t.kind));
  const sel = params.get('thread');
  const current = threads.find((t) => t.code === sel);
  const agentKind = (k: string) => (['advisor', 'overseer', 'assistant', 'ceo', 'manager'].includes(k) ? k : 'employee');

  return (
    <>
      <PageHeader eyebrow="گفت‌وگوی مستقیم، بدون منشی" title="پیام‌ها" />
      <div className="grid min-h-[60dvh] gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Card className={cx('flex flex-col gap-1 p-2', sel && 'hidden lg:flex')}>
          {q.isLoading ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="m-1 h-14" />)
            : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
            : !threads.length ? <Empty icon="messages" title="گفت‌وگویی نیست" />
            : threads.map((t) => (
              <button key={t.code} type="button" onClick={() => router.replace(`/messages?thread=${t.code}`, { scroll: false })} className={cx('flex items-center gap-3 rounded-[12px] p-3 text-right transition-colors', sel === t.code ? 'tahrir bg-gold-soft' : 'hover:bg-hover')}>
                {t.kind === 'advisor' ? <Orb size={36} /> : <Avatar kind={agentKind(t.kind)} size={36} />}
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className={cx('truncate text-[14px]', t.unread ? 'font-bold text-ink' : 'font-semibold text-sec')}>{t.title_fa}</span>
                  <span className="flex items-center gap-2 text-[11px] text-muted">{t.company && t.kind !== 'advisor' ? <CompanyMark code={t.company} height={11} mono /> : null}<span className="fig">{t.last_ref}</span>{t.last_message_at ? <span>{ago(t.last_message_at)}</span> : null}</span>
                </div>
                {t.unread ? <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-gold px-1.5 text-[11px] font-bold text-on-gold">{t.unread}</span> : null}
              </button>
            ))}
        </Card>
        <Card className={cx('flex min-h-[70dvh] flex-col p-4', !sel && 'hidden lg:flex')}>
          {current ? (
            <>
              <div className="flex items-center gap-3 border-b border-div pb-3">
                <IconButton icon="back" label="برگشت" className="lg:hidden" mirror onClick={() => router.replace('/messages')} />
                {current.kind === 'advisor' ? <Orb size={36} /> : <Avatar kind={agentKind(current.kind)} size={36} />}
                <div className="flex flex-col"><span className="text-[15px] font-semibold">{current.title_fa}</span><span className="fig text-[11px] text-muted">{current.code}</span></div>
              </div>
              <Chat code={current.code} agentKind={agentKind(current.kind)} placeholder="پیام…" />
            </>
          ) : <Empty icon="messages" title="یک گفت‌وگو را انتخاب کن" body="مدیرعامل‌ها گزارش و پیشنهاد میدهند؛ پیام‌های غیرفوری‌شان دسته‌ای میرسد." />}
        </Card>
      </div>
    </>
  );
}

export default function MessagesPage() {
  return <Suspense><MessagesInner /></Suspense>;
}
