'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { Icon } from '@/components/icon';
import { Avatar, Orb } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Chat } from '@/components/chat/chat';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Skeleton } from '@/components/ui/primitives';
import { IconButton } from '@/components/ui/button';
import { useCompanies, useThreads } from '@/lib/api/hooks';
import { useMessageSearch } from '@/lib/api/v15';
import { ACTOR_FA } from '@/lib/labels';
import { useScope } from '@/lib/scope';
import { ago, cx, jDate } from '@/lib/format';
import { groupThreads, type Thread, type ThreadGroup } from '@/lib/threads';

const FOLDED = 'hq.messages.folded';
// The sections the owner folded, remembered in this browser.
const foldListeners = new Set<() => void>();
let foldCache: string[] | null = null;
const NONE: string[] = [];
const readFolded = (): string[] => { if (foldCache) return foldCache; try { foldCache = JSON.parse(localStorage.getItem(FOLDED) ?? '[]') as string[]; } catch { foldCache = []; } return foldCache; };
function toggleFolded(code: string) {
  const f = readFolded();
  foldCache = f.includes(code) ? f.filter((x) => x !== code) : [...f, code];
  try { localStorage.setItem(FOLDED, JSON.stringify(foldCache)); } catch { /* memory only */ }
  for (const l of foldListeners) l();
}
const useFolded = () => useSyncExternalStore((l) => { foldListeners.add(l); return () => foldListeners.delete(l); }, readFolded, () => NONE);
const agentKind = (k: string) => (['advisor', 'overseer', 'assistant', 'ceo', 'manager'].includes(k) ? k : 'employee');
const fa = (n: number) => n.toLocaleString('fa-IR');

/** One conversation in the list. */
function ThreadRow({ t, selected, onOpen }: { t: Thread; selected: boolean; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen} aria-current={selected || undefined} className={cx('flex w-full items-center gap-3 rounded-[12px] p-3 text-right transition-colors', selected ? 'tahrir bg-gold-soft' : 'hover:bg-hover')}>
      {t.kind === 'advisor' ? <Orb size={36} /> : <Avatar kind={agentKind(t.kind)} size={36} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <span className={cx('truncate text-[14px]', t.unread ? 'font-bold text-ink' : 'font-semibold text-sec')}>{t.title_fa}</span>
        <span className="flex items-center gap-2 text-[11px] text-muted"><span className="fig">{t.last_ref}</span>{t.last_message_at ? <span>{ago(t.last_message_at)}</span> : null}</span>
      </div>
      {t.unread ? <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-gold px-1.5 text-[11px] font-bold text-on-gold">{fa(t.unread)}</span> : null}
    </button>
  );
}

/** A company's conversations under its mark and name, folded or open, with its unread count. */
function Group({ g, name, open, onToggle, sel, onOpen }: { g: ThreadGroup; name: string; open: boolean; onToggle: () => void; sel: string | null; onOpen: (code: string) => void }) {
  return (
    <section aria-label={name} className="flex flex-col">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex items-center gap-2 rounded-[10px] px-2 py-2 text-start hover:bg-hover">
        <span className="text-sec">{g.holding ? <Icon name="holding" size={15} /> : <CompanyMark code={g.company} height={13} mono />}</span>
        <span className="flex-1 text-[13px] font-semibold text-sec">{name}</span>
        {g.unread ? <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-gold-soft px-1.5 text-[11px] font-bold text-gold-ink" aria-label={`${fa(g.unread)} نخوانده`}>{fa(g.unread)}</span> : <span className="text-[11px] text-muted">{fa(g.threads.length)}</span>}
        <Icon name="chevron" size={14} className={cx('text-muted transition-transform', open ? 'rotate-90' : '-rotate-90')} />
      </button>
      {open ? <div className="flex flex-col">{g.threads.map((t) => <ThreadRow key={t.code} t={t} selected={sel === t.code} onOpen={() => onOpen(t.code)} />)}</div> : null}
    </section>
  );
}

function MessagesInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { company: scope } = useScope();
  const q = useThreads();
  const { data: companies } = useCompanies();
  // ⟨owner, 2026-10-31⟩ per company: the holding first, then each company (its CEO, then its managers); a filter row on top.
  const groups = useMemo(() => groupThreads(q.data ?? [], companies), [q.data, companies]);
  const [only, setOnly] = useState<string | null>(params.get('company') ?? scope ?? null);
  const folded = useFolded();
  const shown = only ? groups.filter((g) => g.company === only) : groups;
  const nameOf = (g: ThreadGroup) => (g.holding ? 'هلدینگ' : companies?.find((c) => c.code === g.company)?.name_fa ?? g.company);
  const sel = params.get('thread');
  const current = (q.data ?? []).find((t) => t.code === sel);
  const [text, setText] = useState('');
  const [query, setQuery] = useState('');
  useEffect(() => { const t = setTimeout(() => setQuery(text.trim()), 300); return () => clearTimeout(t); }, [text]);
  // The search is global: every company's conversations, whatever the filter shows.
  const hits = useMessageSearch(query, {});
  const searching = query.length >= 2;
  const openThread = (code: string) => router.replace(`/messages?thread=${encodeURIComponent(code)}${only ? `&company=${only}` : ''}`, { scroll: false });

  return (
    <>
      <PageHeader eyebrow="گفت‌وگوی مستقیم، بدون منشی" title="پیام‌ها" />
      {/* One column of minmax(0, 1fr) on a phone: an implicit column grows to the chat's widest line (3px past 390). */}
      <div className="grid min-h-[60dvh] grid-cols-1 gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Card className={cx('flex min-w-0 flex-col gap-1 p-2', sel && 'hidden lg:flex')}>
          <label className="m-1 flex h-10 items-center gap-2 rounded-[10px] border border-strong bg-tile px-3 text-sec focus-within:border-gold-ink">
            <Icon name="search" size={16} />
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="جستجو در همه‌ی پیام‌ها" aria-label="جستجو در پیام‌ها" className="h-full min-w-0 flex-1 bg-transparent text-[14px] text-ink outline-none" />
            {text ? <button type="button" onClick={() => setText('')} aria-label="پاک کردن جستجو" className="text-muted hover:text-ink"><Icon name="close" size={14} /></button> : null}
          </label>
          {!searching && groups.length > 1 ? (
            <div className="no-scrollbar mx-1 flex gap-1.5 overflow-x-auto pb-1" role="group" aria-label="گفت‌وگوهای کدام شرکت">
              <FilterChip selected={!only} onClick={() => setOnly(null)}>همه</FilterChip>
              {groups.map((g) => (
                <FilterChip key={g.company} selected={only === g.company} count={g.unread || undefined} onClick={() => setOnly(only === g.company ? null : g.company)}>
                  <span className="flex items-center gap-1.5">{g.holding ? <Icon name="holding" size={13} /> : <CompanyMark code={g.company} height={12} mono />}{nameOf(g)}</span>
                </FilterChip>
              ))}
            </div>
          ) : null}
          {searching ? (
            hits.isLoading ? Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="m-1 h-16" />)
              : hits.error ? <ErrorState error={hits.error} onRetry={() => hits.refetch()} />
              : !hits.data?.items.length ? <p className="px-3 py-6 text-center text-[13px] text-muted">در پیام‌ها پیدا نشد.</p>
              : hits.data.items.map((h) => (
                <button key={h.id} type="button" onClick={() => openThread(h.thread)} className={cx('flex flex-col gap-1 rounded-[12px] p-3 text-right transition-colors', sel === h.thread ? 'bg-gold-soft' : 'hover:bg-hover')}>
                  <span className="line-clamp-2 text-[13px] leading-6 text-ink">{h.body.replace(/[*_`#>]/g, '')}</span>
                  <span className="flex items-center gap-2 text-[11px] text-muted"><span>{ACTOR_FA(h.author)}</span><span className="fig">{h.ref}</span><span>{jDate(h.created_at)}</span></span>
                </button>
              ))
          ) : q.isLoading ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="m-1 h-14" />)
            : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
            : !shown.length ? <Empty icon="messages" title="گفت‌وگویی نیست" />
            : shown.map((g) => <Group key={g.company} g={g} name={nameOf(g)} open={!!only || !folded.includes(g.company)} onToggle={() => (only ? setOnly(null) : toggleFolded(g.company))} sel={sel} onOpen={openThread} />)}
        </Card>
        <Card className={cx('flex min-h-[70dvh] min-w-0 flex-col p-4', !sel && 'hidden lg:flex')}>
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
