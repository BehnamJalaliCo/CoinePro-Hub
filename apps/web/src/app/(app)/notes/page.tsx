'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';
import { Icon } from '@/components/icon';
import { Composer } from '@/components/media/composer';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Dialog } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { AudioPlayer, NOTE_STATUS, PROMOTE } from '@/components/v18/bits';
import { CoMark } from '@/components/v17/bits';
import { useCompanies } from '@/lib/api/hooks';
import { faError, useNoteAction, useNotes, type NoteStatus, type OwnerNote, type PromoteIn } from '@/lib/api/v18';
import { ago, cx } from '@/lib/format';

const STATUSES: Array<NoteStatus | null> = ['open', 'promoted', 'archived', null];
const PROMOTED_HREF: Record<string, (r: string) => string> = { work: (r) => `/work/${r}`, order: () => '/', errand: () => '/assistant' };
const tagsOf = (s: string) => [...new Set(s.split(/[,،#]+/).map((x) => x.trim()).filter(Boolean))].slice(0, 8);

function PromoteDialog({ n, onClose }: { n: OwnerNote; onClose: () => void }) {
  const act = useNoteAction();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const [to, setTo] = useState<PromoteIn['to']>('work');
  const [company, setCompany] = useState<string | null>(null);
  const ok = to !== 'work' || !!company;
  const go = async () => {
    try {
      const out = await act.promote.mutateAsync({ ref: n.ref, body: { to, ...(to === 'work' && company ? { company } : {}) } });
      toast({ tone: 'ok', text: <>تبدیل شد به {PROMOTE[to]!.fa} <span className="fig">{out.promoted_to?.ref}</span>.</> });
      onClose();
    } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()} title="تبدیل یادداشت" actions={<><Button variant="primary" disabled={!ok} loading={act.promote.isPending} onClick={go}>تبدیل کن</Button><Button variant="secondary" onClick={onClose}>انصراف</Button></>}>
      <div className="flex flex-col gap-3">
        <p className="rounded-[10px] bg-tile p-3 text-[13px] leading-6 text-ink">{n.text_md}</p>
        <div className="flex flex-col gap-1.5">
          {(Object.keys(PROMOTE) as Array<PromoteIn['to']>).map((k) => (
            <button key={k} type="button" onClick={() => setTo(k)} aria-pressed={to === k} className={cx('flex items-center gap-3 rounded-[12px] p-2.5 text-start', to === k ? 'bg-gold-soft' : 'bg-tile hover:bg-hover')}>
              <span className={to === k ? 'text-gold-ink' : 'text-sec'}><Icon name={PROMOTE[k]!.icon} size={18} /></span>
              <span className="flex flex-col"><span className="text-[13px] font-semibold text-ink">{PROMOTE[k]!.fa}</span><span className="text-[11px] text-muted">{PROMOTE[k]!.note}</span></span>
            </button>
          ))}
        </div>
        {to === 'work' ? <div className="flex flex-wrap gap-1.5">{(companies ?? []).map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => setCompany(c.code)}><span className="flex items-center gap-1.5"><CoMark code={c.code} height={11} />{c.name_fa}</span></FilterChip>)}</div> : null}
      </div>
    </Dialog>
  );
}

function NoteCard({ n, onPromote }: { n: OwnerNote; onPromote: () => void }) {
  const act = useNoteAction();
  const toast = useToast();
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState(n.text_md);
  const [tags, setTags] = useState(n.tags.join('، '));
  const st = NOTE_STATUS[n.status] ?? NOTE_STATUS.open!;
  const save = async () => {
    try { await act.patch.mutateAsync({ n, patch: { text_md: text.trim(), tags: tagsOf(tags) } }); setEdit(false); toast({ tone: 'ok', text: 'یادداشت ذخیره شد.' }); } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <Card className={cx('flex flex-col gap-2.5 p-4', n.status === 'archived' && 'opacity-75')}>
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
        <span className="fig">{n.ref}</span>
        {n.source === 'voice' ? <span className="inline-flex items-center gap-1"><Icon name="mic" size={12} />از ویس</span> : null}
        <span>{ago(n.created_at)}</span>
        <span className="flex-1" />
        <Pill tone={st.tone} dot>{st.fa}</Pill>
      </div>
      {edit ? (
        <div className="flex flex-col gap-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={4000} aria-label="متن یادداشت" className="w-full rounded-[10px] border border-strong bg-tile p-3 text-[14px] leading-7 text-ink outline-none focus:border-gold-ink" />
          <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="برچسب‌ها، با ویرگول" aria-label="برچسب‌ها" className="h-9 rounded-[10px] border border-strong bg-tile px-3 text-[13px] text-ink outline-none focus:border-gold-ink" />
          <div className="flex gap-2"><Button size="sm" variant="primary" disabled={!text.trim()} loading={act.patch.isPending} onClick={save}>ذخیره</Button><Button size="sm" variant="ghost" onClick={() => { setEdit(false); setText(n.text_md); setTags(n.tags.join('، ')); }}>انصراف</Button></div>
        </div>
      ) : <Md text={n.text_md} className="text-[14px] leading-7 text-ink" />}
      {n.source === 'voice' && n.file_id ? <AudioPlayer fileId={n.file_id} label={`صدای اصلی ${n.ref}`} compact /> : null}
      {n.tags.length && !edit ? <div className="flex flex-wrap gap-1.5">{n.tags.map((t) => <span key={t} dir="auto" className="rounded-full bg-tile px-2 py-0.5 text-[11px] text-sec">#{t}</span>)}</div> : null}
      {n.promoted_to ? (
        <Link href={(PROMOTED_HREF[n.promoted_to.kind] ?? (() => '/'))(n.promoted_to.ref)} className="inline-flex items-center gap-1.5 self-start rounded-full bg-pos-soft px-2.5 py-1 text-[12px] text-pos hover:underline">
          <Icon name={PROMOTE[n.promoted_to.kind]?.icon ?? 'task'} size={13} />{PROMOTE[n.promoted_to.kind]?.fa ?? n.promoted_to.kind} <span className="fig">{n.promoted_to.ref}</span>
        </Link>
      ) : null}
      {n.status === 'open' && !edit ? (
        <div className="flex flex-wrap gap-1.5 pt-1">
          <Button size="sm" variant="secondary" icon="delegate" onClick={onPromote}>تبدیل</Button>
          <Button size="sm" variant="ghost" icon="edit" onClick={() => setEdit(true)}>ویرایش</Button>
          <Button size="sm" variant="ghost" icon="download" loading={act.patch.isPending} onClick={async () => { try { await act.patch.mutateAsync({ n, patch: { status: 'archived' } }); toast({ tone: 'info', text: 'بایگانی شد.' }); } catch (e) { toast({ tone: 'error', text: faError(e) }); } }}>بایگانی</Button>
        </div>
      ) : null}
    </Card>
  );
}

function NotesInner() {
  const params = useSearchParams();
  const highlight = params.get('ref');
  const [status, setStatus] = useState<NoteStatus | null>('open');
  const [text, setText] = useState('');
  const [promote, setPromote] = useState<OwnerNote | null>(null);
  const q = useNotes({ status, q: text });
  const act = useNoteAction();
  const toast = useToast();
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const create = async (v: { body: string; attachments: string[] }) => {
    // The composer sends the voice as its only attachment (files are off here): a voice note keeps its recording.
    const voice = v.attachments.at(-1) ?? null;
    try {
      const n = await act.create.mutateAsync({ text_md: v.body, source: voice ? 'voice' : 'text', file_id: voice, tags: tagsOf((v.body.match(/#[^\s#]+/g) ?? []).join(',')), key: crypto.randomUUID() });
      toast({ tone: 'ok', text: <>یادداشت <span className="fig">{n.ref}</span> ثبت شد.</> });
      if (status && status !== 'open') setStatus('open');
    } catch (e) { toast({ tone: 'error', text: faError(e) }); throw e; }
  };
  return (
    <>
      <PageHeader eyebrow="هر فکری، همان لحظه؛ بعداً به کار، فرمان یا کار دستیار تبدیلش کن" title="یادداشت‌های سریع">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">هیچ مدلی روی یادداشت‌ها اجرا نمیشود؛ مشاور کل یادداشت‌های باز را فقط در <Link href="/advisor" className="text-gold-ink">مرور هفتگی</Link> میخواند. یادداشت پاک نمیشود؛ بایگانی میشود. برچسب را با # در متن بنویس.</p>
      </PageHeader>
      <Composer purpose="note" allowFiles={false} maxLength={4000} label="یادداشت تازه" placeholder="یادداشت تازه… (ویس هم میشود؛ صدای اصلی کنارش میماند)" onSend={create} sending={act.create.isPending} />
      <div className="flex flex-wrap items-center gap-2">
        {STATUSES.map((s) => <FilterChip key={s ?? 'all'} selected={status === s} onClick={() => setStatus(s)}>{s ? NOTE_STATUS[s]!.fa : 'همه'}</FilterChip>)}
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="جستجو در یادداشت‌ها…" aria-label="جستجو در یادداشت‌ها" className="h-9 w-full max-w-xs rounded-[10px] border border-strong bg-tile px-3 text-[13px] text-ink outline-none focus:border-gold-ink sm:ms-auto" />
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-48" /> : !items.length ? <Empty icon="edit" title="یادداشتی نیست" body="بالای صفحه بنویس یا بگو." /> : (
        <div className="grid items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((n) => <div key={n.ref} className={cx(highlight === n.ref && 'rounded-[18px] ring-2 ring-[var(--hq-gold-ink)]')}><NoteCard n={n} onPromote={() => setPromote(n)} /></div>)}
        </div>
      )}
      {q.hasNextPage ? <Button variant="secondary" size="sm" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>بیشتر</Button> : null}
      {promote ? <PromoteDialog n={promote} onClose={() => setPromote(null)} /> : null}
    </>
  );
}

/** یادداشت‌های سریع مالک (contract §21.8): text or voice, promoted into work, an order or an errand; never deleted. */
export default function NotesPage() {
  return <Suspense><NotesInner /></Suspense>;
}
