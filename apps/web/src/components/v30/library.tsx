'use client';

// ⟨1.12⟩ Contract §30.5 the production library: cover folders (uploaded as files), voices, prompts, patterns, music and brand assets,
// each for the holding (every company) or for one company.

import { useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { fileUrl } from '@/lib/api/v13';
import { KIND_FA, useLibrary, useLibraryActions, type Asset, type AssetKind } from '@/lib/api/v30';
import { useCompanies } from '@/lib/api/hooks';
import { cx, jDate } from '@/lib/format';
import { FaPara, FaText } from './bits';

const KINDS = Object.keys(KIND_FA) as AssetKind[];
const FILE_KINDS: ReadonlySet<AssetKind> = new Set(['cover_folder', 'voice', 'music', 'brand']);
const ACCEPT: Partial<Record<AssetKind, string>> = { cover_folder: 'image/*', voice: 'audio/*', music: 'audio/*', brand: 'image/*,.svg' };
const field = 'w-full rounded-[10px] border border-strong bg-tile px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
const errText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.messageFa : fallback);
/** The text a prompt or pattern asset keeps in its config. */
const textOf = (a: Pick<Asset, 'config'>) => String(a.config.text ?? a.config.query ?? '');

export function Library() {
  const [kind, setKind] = useState<AssetKind | null>(null);
  const [company, setCompany] = useState<string | 'all'>('all');
  const [adding, setAdding] = useState(false);
  const [del, setDel] = useState<Asset | null>(null);
  const cs = useCompanies();
  const q = useLibrary(company === 'all' ? null : company, kind);
  const act = useLibraryActions();
  const toast = useToast();
  const name = (code: string | null) => (code ? cs.data?.find((c) => c.code === code)?.name_fa ?? code : 'هلدینگ، همه‌ی شرکت‌ها');
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="no-scrollbar -mx-1 flex min-w-0 flex-1 gap-2 overflow-x-auto px-1" role="group" aria-label="نوع">
          <FilterChip selected={kind === null} onClick={() => setKind(null)}>همه</FilterChip>
          {KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{KIND_FA[k]}</FilterChip>)}
        </div>
        <Button variant="primary" size="sm" icon="add" onClick={() => setAdding(true)}>مورد تازه</Button>
      </div>
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1" role="group" aria-label="شرکت">
        <FilterChip selected={company === 'all'} onClick={() => setCompany('all')}>همه</FilterChip>
        {(cs.data ?? []).filter((c) => c.code !== 'HQ').map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => setCompany(c.code)}>{c.name_fa ?? c.code}</FilterChip>)}
      </div>
      {q.isLoading ? <Skeleton className="h-48 rounded-[16px]" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data === null ? (
        <Card><Empty icon="attach" title="کتابخانه بعد از به‌روزرسانی ستاد میاید" body="پوشه‌ی کاورها، صداها، پرامپت‌ها و الگوها این‌جا نگه داشته میشوند." /></Card>
      ) : !q.data?.length ? (
        <Card><Empty icon="attach" title="هنوز چیزی در کتابخانه نیست" action={<Button variant="primary" icon="add" onClick={() => setAdding(true)}>مورد تازه</Button>} /></Card>
      ) : (
        <ul className="grid items-start gap-3 md:grid-cols-2 xl:grid-cols-3" aria-label="کتابخانه">
          {q.data.map((a) => (
            <li key={a.id}>
              <Card as="article" className="hq-tile flex h-full flex-col gap-2 p-4" aria-label={`${KIND_FA[a.kind]}: ${a.title_fa}`}>
                <div className="flex items-center gap-2">
                  <span className="flex size-9 flex-none items-center justify-center rounded-[10px] bg-tile text-silver-ink"><Icon name={a.kind === 'voice' || a.kind === 'music' ? 'mic' : a.kind === 'prompt' || a.kind === 'pattern' ? 'edit' : 'image'} size={18} /></span>
                  <span className="min-w-0 flex-1 text-[14px] font-semibold"><FaText text={a.title_fa} /></span>
                  <Pill tone="silver">{KIND_FA[a.kind]}</Pill>
                </div>
                <div className="text-[11px] text-muted">{name(a.company)} · {jDate(a.created_at)}{a.files.length ? <> · <span className="fig">{a.files.length}</span> فایل</> : null}</div>
                {textOf(a) ? <FaPara text={textOf(a)} className="line-clamp-3 text-[12px] leading-5 text-sec" /> : null}
                {a.kind === 'voice' && a.files[0] ? <audio controls preload="none" src={fileUrl(a.files[0])} className="w-full" aria-label="نمونه‌ی صدا" /> : null}
                {a.kind === 'cover_folder' && a.files.length ? (
                  <div className="flex gap-1.5 overflow-hidden">{a.files.slice(0, 4).map((f) => <img key={f} src={fileUrl(f)} alt="" className="size-14 rounded-[8px] bg-tile object-cover" />)}</div>
                ) : null}
                <div><Button size="sm" aria-label={`حذف ${a.title_fa}`} onClick={() => setDel(a)}>حذف</Button></div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <AddSheet open={adding} onOpenChange={setAdding} defaultCompany={company === 'all' ? null : company} defaultKind={kind ?? 'cover_folder'} />
      <Dialog open={!!del} onOpenChange={(v) => !v && setDel(null)} title="حذف از کتابخانه"
        actions={<>
          <Button variant="primary" loading={act.remove.isPending} onClick={() => del && act.remove.mutate(del.id, {
            onSuccess: () => { toast({ tone: 'ok', text: 'حذف شد.' }); setDel(null); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'حذف نشد.') }),
          })}>حذف کن</Button>
          <Button onClick={() => setDel(null)}>بی‌خیال</Button>
        </>}>
        «{del?.title_fa}» از کتابخانه برداشته میشود؛ خط‌هایی که از آن استفاده میکنند دیگر آن را نمیبینند.
      </Dialog>
    </div>
  );
}

function AddSheet({ open, onOpenChange, defaultCompany, defaultKind }: { open: boolean; onOpenChange: (v: boolean) => void; defaultCompany: string | null; defaultKind: AssetKind }) {
  const act = useLibraryActions();
  const toast = useToast();
  const cs = useCompanies();
  const [kind, setKind] = useState<AssetKind>(defaultKind);
  const [company, setCompany] = useState<string | null>(defaultCompany);
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const withFiles = FILE_KINDS.has(kind);
  const ok = title.trim() && (withFiles ? files.length > 0 : text.trim());
  const reset = () => { setTitle(''); setText(''); setFiles([]); };
  const submit = () => act.add.mutate({ meta: { company, kind, title_fa: title.trim(), config: withFiles ? {} : kind === 'pattern' ? { query: text.trim() } : { text: text.trim() } }, files }, {
    onSuccess: () => { toast({ tone: 'ok', text: 'به کتابخانه اضافه شد.' }); reset(); onOpenChange(false); },
    onError: (e) => toast({ tone: 'error', text: errText(e, 'اضافه نشد؛ دوباره بزن.') }),
  });
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="مورد تازه" description="برای همه‌ی شرکت‌ها یا فقط یک شرکت"
      footer={<div className="flex gap-2"><Button variant="primary" loading={act.add.isPending} disabled={!ok} onClick={submit}>اضافه کن</Button><Button onClick={() => onOpenChange(false)}>بی‌خیال</Button></div>}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">نوع</span>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="نوع مورد">{KINDS.map((k) => (
            <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)} className={cx('h-9 rounded-full px-3.5 text-[13px] font-semibold', kind === k ? 'bg-gold text-on-gold' : 'bg-tile text-sec hover:bg-hover')}>{KIND_FA[k]}</button>
          ))}</div></div>
        <div className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">مال کدام شرکت</span>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="شرکت">
            <button type="button" role="radio" aria-checked={company === null} onClick={() => setCompany(null)} className={cx('h-9 rounded-full px-3.5 text-[13px] font-semibold', company === null ? 'bg-gold text-on-gold' : 'bg-tile text-sec hover:bg-hover')}>همه‌ی شرکت‌ها</button>
            {(cs.data ?? []).filter((c) => c.code !== 'HQ').map((c) => <button key={c.code} type="button" role="radio" aria-checked={company === c.code} onClick={() => setCompany(c.code)} className={cx('h-9 rounded-full px-3.5 text-[13px] font-semibold', company === c.code ? 'bg-gold text-on-gold' : 'bg-tile text-sec hover:bg-hover')}>{c.name_fa ?? c.code}</button>)}
          </div></div>
        <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">نام</span><input value={title} onChange={(e) => setTitle(e.target.value)} className={cx(field, 'h-11')} aria-label="نام مورد" /></label>
        {withFiles ? (
          <div className="flex flex-col gap-2"><span className="text-[12px] text-sec">{kind === 'cover_folder' ? 'عکس‌های پوشه' : 'فایل‌ها'}</span>
            <input ref={input} type="file" multiple accept={ACCEPT[kind]} className="sr-only" aria-label="انتخاب فایل" onChange={(e) => setFiles([...(e.target.files ?? [])])} />
            <Button icon="attach" onClick={() => input.current?.click()}>انتخاب فایل‌ها</Button>
            {files.length ? <p className="text-[12px] text-sec"><span className="fig">{files.length}</span> فایل انتخاب شد: <span dir="ltr">{files.map((f) => f.name).join(', ')}</span></p> : null}</div>
        ) : (
          <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">{kind === 'pattern' ? 'عبارت جست‌وجو' : 'متن'}</span>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} dir="auto" className={cx(field, 'py-2.5 leading-7')} aria-label="متن مورد" /></label>
        )}
      </div>
    </Sheet>
  );
}
