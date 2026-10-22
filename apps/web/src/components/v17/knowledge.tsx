'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Card, FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { useCompanies, useDepartments } from '@/lib/api/hooks';
import {
  VALID_DAYS, faError, useKnowledgeAction, useKnowledgeEntry, useKnowledgeVersions,
  type KnowledgeEntry, type KnowledgeIn, type Layer, type Source,
} from '@/lib/api/v17';
import { ACTOR_FA, DEPT_FA } from '@/lib/labels';
import { useNow } from '@/lib/store';
import { cx, jDate } from '@/lib/format';
import { CoMark, KNOWLEDGE_KIND, KNOWLEDGE_STATUS, LAYER_FA, REVIEW_CHECK, REVIEW_VERDICT, RefChip, daysFrom } from './bits';

const field = 'w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
const validIso = (d: string) => `${d}T20:29:00Z`; // the end of that day in Tehran

/** «۱۲ روز مانده», «منقضی»: the expiry in words; under 14 days it warns (a review work item is already out). */
export function Expiry({ e }: { e: Pick<KnowledgeEntry, 'valid_until' | 'status'> }) {
  const now = useNow();
  if (!now) return <span className="text-[11px] text-muted">تا {jDate(validIso(e.valid_until))}</span>;
  const d = daysFrom(validIso(e.valid_until), now);
  if (e.status === 'expired' || d < 0) return <span className="flex items-center gap-1 text-[11px] text-warn"><Icon name="time" size={12} />منقضی از {jDate(validIso(e.valid_until))}</span>;
  return <span className={cx('flex items-center gap-1 text-[11px]', d <= 14 ? 'text-warn' : 'text-muted')}>{d <= 14 ? <Icon name="time" size={12} /> : null}تا {jDate(validIso(e.valid_until), true)}{d <= 14 ? `، ${d} روز مانده` : ''}</span>;
}

export function EntryCard({ e, onOpen }: { e: KnowledgeEntry; onOpen: () => void }) {
  const st = KNOWLEDGE_STATUS[e.status] ?? { fa: e.status, tone: 'neutral' as const };
  const l = LAYER_FA[e.layer];
  return (
    <button type="button" onClick={onOpen} className={cx('flex min-w-0 flex-col gap-2 rounded-[16px] bg-card p-4 text-right transition-colors hover:bg-hover', (e.status === 'retired' || e.status === 'expired') && 'opacity-70')}>
      <span className="flex items-center gap-2 text-[12px] text-muted">
        <span className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden whitespace-nowrap">
          <span className="flex flex-none items-center gap-1 text-sec"><Icon name={l?.icon ?? 'knowledge'} size={14} />{l?.fa ?? e.layer}</span>
          <span className="flex-none"><CoMark code={e.company} /></span>
          {e.department ? <span className="flex-none">{DEPT_FA[e.department] ?? e.department}</span> : null}
          <span className="truncate">· {KNOWLEDGE_KIND[e.kind] ?? e.kind}</span>
        </span>
        <Pill tone={st.tone} dot className="h-5 text-[11px]">{st.fa}</Pill>
      </span>
      <span className="text-[15px] font-semibold leading-7 text-ink">{e.title_fa}</span>
      <span className="line-clamp-2 text-[13px] leading-6 text-sec">{e.body_md.replace(/[*_`#>]/g, '').replace(/\n+/g, ' ')}</span>
      <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="fig text-[11px] text-muted">{e.ref}@{e.version}</span>
        <Expiry e={e} />
        <span className="text-[11px] text-muted">{e.sources.length} منبع</span>
        {e.review ? <Pill tone={REVIEW_VERDICT[e.review.verdict]?.tone ?? 'neutral'} className="h-5 text-[11px]">بازبینی: {REVIEW_VERDICT[e.review.verdict]?.fa}</Pill> : null}
      </span>
    </button>
  );
}

export function EntrySheet({ refId, onClose, onEdit }: { refId: string; onClose: () => void; onEdit: (e: KnowledgeEntry) => void }) {
  const q = useKnowledgeEntry(refId);
  const versions = useKnowledgeVersions(refId);
  const act = useKnowledgeAction();
  const toast = useToast();
  const [retire, setRetire] = useState(false);
  const e = q.data;
  const readOnly = !e || e.layer === 'employee' || e.kind === 'support';
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={e?.title_fa ?? 'دانشنامه'} description={e ? `${LAYER_FA[e.layer]?.fa ?? e.layer} · ${KNOWLEDGE_KIND[e.kind] ?? e.kind}` : undefined} width={600}
      footer={e && !readOnly && e.status !== 'retired' ? (
        <div className="flex gap-2"><Button variant="primary" icon="edit" className="flex-1" onClick={() => onEdit(e)}>نسخه‌ی تازه</Button><Button variant="danger" onClick={() => setRetire(true)}>بازنشسته</Button></div>
      ) : undefined}>
      {!e ? <Skeleton className="h-64" /> : (
        <div className="flex flex-col gap-4 text-[13px]">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={KNOWLEDGE_STATUS[e.status]?.tone ?? 'neutral'} dot>{KNOWLEDGE_STATUS[e.status]?.fa ?? e.status}</Pill>
            <span className="fig text-[12px] text-muted">{e.ref}@{e.version}</span>
            <Expiry e={e} />
          </div>
          {e.kind === 'support' ? <p className="rounded-[12px] bg-tile p-3 text-[12px] leading-6 text-sec">مقاله‌ی دانشنامه‌ی پشتیبانی است: این‌جا فقط دیده میشود. ویرایش و مُهرش فقط از <Link href="/support" className="text-gold-ink">پشتیبانی</Link> است.</p> : null}
          {e.layer === 'employee' ? <p className="rounded-[12px] bg-tile p-3 text-[12px] leading-6 text-sec">حافظه‌ی خود کارمند است (<span className="fig">{e.created_by.code}</span>)؛ فقط خواندنی و کپی نمیشود.</p> : null}
          <Md text={e.body_md} />
          <section className="flex flex-col gap-1.5">
            <h3 className="text-[12px] font-semibold text-gold-ink">منبع‌ها</h3>
            <ul className="flex flex-col gap-1">{e.sources.map((s, i) => <li key={i} className="flex flex-wrap items-center gap-2"><span className="fig text-[11px] text-muted">{s.kind}</span><RefChip r={s.ref} tone="neutral" />{s.note ? <span className="text-[12px] text-sec">{s.note}</span> : null}</li>)}</ul>
          </section>
          {e.review ? (
            <section className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
              <span className="flex items-center gap-2"><span className="text-[12px] font-semibold text-gold-ink">بازبینی</span><Pill tone={REVIEW_VERDICT[e.review.verdict]?.tone ?? 'neutral'} className="h-5 text-[11px]">{REVIEW_VERDICT[e.review.verdict]?.fa}</Pill><span className="text-[11px] text-muted">{ACTOR_FA(e.review.by)}، {jDate(e.review.at)}</span></span>
              <div className="flex flex-wrap gap-2">{Object.entries(e.review.checks).map(([k, ok]) => <span key={k} className={cx('flex items-center gap-1 text-[12px]', ok ? 'text-pos' : 'text-neg')}><Icon name={ok ? 'seal' : 'urgent'} size={12} />{REVIEW_CHECK[k] ?? k}</span>)}</div>
              {e.review.notes_md ? <Md text={e.review.notes_md} className="text-[12px] leading-6 text-sec" /> : null}
            </section>
          ) : e.status === 'in_review' ? <p className="text-[12px] text-muted">منتظر بازبینی ناظر یا ایمنی AI است (تزریق، رمز، تناقض با اساسنامه، اختیار).</p> : null}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted"><span>نوشته‌ی {ACTOR_FA(e.created_by)}</span>{e.approved_by ? <span>تأیید {ACTOR_FA(e.approved_by)}</span> : null}<span>به‌روز {jDate(e.updated_at, true)}</span></div>
          {(versions.data?.length ?? 0) > 1 ? (
            <section className="flex flex-col gap-1.5">
              <h3 className="text-[12px] font-semibold text-gold-ink">نسخه‌ها</h3>
              <ul className="flex flex-col gap-1">{versions.data!.map((v) => <li key={v.version} className="flex items-center gap-2 text-[12px]"><span className="fig w-8 text-ink">v{v.version}</span><span className="flex-1 truncate text-sec">{v.title_fa}</span><Pill tone={KNOWLEDGE_STATUS[v.status]?.tone ?? 'neutral'} className="h-5 text-[11px]">{KNOWLEDGE_STATUS[v.status]?.fa}</Pill></li>)}</ul>
            </section>
          ) : null}
        </div>
      )}
      <Dialog open={retire} onOpenChange={setRetire} title="بازنشسته کردن این ورودی" actions={<>
        <Button variant="danger" loading={act.retire.isPending} onClick={() => e && act.retire.mutateAsync(e.ref).then(() => { toast({ tone: 'info', text: 'بازنشسته شد؛ از جستجوی ایجنت‌ها بیرون رفت.' }); setRetire(false); onClose(); }).catch((x) => toast({ tone: 'error', text: faError(x) }))}>بازنشسته کن</Button>
        <Button variant="secondary" onClick={() => setRetire(false)}>انصراف</Button>
      </>}>
        <p>ورودی پاک نمیشود؛ فقط دیگر به ایجنت‌ها نمیرسد و به‌عنوان منبع پذیرفته نمیشود.</p>
      </Dialog>
    </Sheet>
  );
}

/** The company's departments, from the API (departments are data too). */
function DeptSelect({ company, value, onChange }: { company: string; value: string | null; onChange: (d: string | null) => void }) {
  const deps = useDepartments(company);
  return (
    <label className="flex flex-col gap-1.5 font-semibold text-sec">دپارتمان
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} className={cx(field, 'h-10')}><option value="">—</option>{(deps.data ?? []).map((d) => <option key={d.code} value={d.code}>{d.name_fa}</option>)}</select>
    </label>
  );
}

const KINDS = ['principle', 'policy', 'fact', 'faq', 'playbook'] as const;
const SOURCE_KINDS = ['doc', 'deliverable', 'decision', 'resolution', 'work', 'kpi', 'charter', 'support_kb', 'url'];
const addDays = (now: number, n: number) => new Date(now + n * 86_400_000).toISOString().slice(0, 10);

export function EntryEditor({ from, onClose }: { from: KnowledgeEntry | null; onClose: () => void }) {
  const act = useKnowledgeAction();
  const toast = useToast();
  const now = useNow();
  const { data: companies } = useCompanies();
  const holding = companies?.find((c) => c.kind === 'holding')?.code ?? 'HQ';
  const [layer, setLayer] = useState<Exclude<Layer, 'employee'>>(from && from.layer !== 'employee' ? from.layer : 'company');
  const [company, setCompany] = useState<string | null>(from?.company ?? null);
  const [department, setDepartment] = useState<string | null>(from?.department ?? null);
  const [kind, setKind] = useState<(typeof KINDS)[number]>(from && from.kind !== 'support' ? from.kind : 'faq');
  const [title, setTitle] = useState(from?.title_fa ?? '');
  const [body, setBody] = useState(from?.body_md ?? '');
  const [sources, setSources] = useState<Source[]>(from?.sources.length ? from.sources : [{ kind: 'doc', ref: '', note: '' }]);
  const [until, setUntil] = useState(from?.valid_until ?? '');
  const co = layer === 'holding' ? holding : company;
  const max = now ? addDays(now, VALID_DAYS[kind]) : '';
  const min = now ? addDays(now, 1) : '';
  const valid = !!co && !!title.trim() && !!body.trim() && sources.some((s) => s.ref.trim()) && !!until && (!max || until <= max) && (layer !== 'department' || !!department);
  const body_: KnowledgeIn = { layer, company: co ?? '', ...(layer === 'department' ? { department } : {}), kind, title_fa: title.trim(), body_md: body.trim(), sources: sources.filter((s) => s.ref.trim()).map((s) => ({ kind: s.kind, ref: s.ref.trim(), note: s.note.trim() })), valid_until: until };
  const save = () => (from ? act.update.mutateAsync({ ref: from.ref, body: body_ }) : act.create.mutateAsync(body_))
    .then((e) => { toast({ tone: 'ok', text: <>ورودی <span className="fig">{e.ref}@{e.version}</span> ثبت شد؛ نوشته‌ی تو با همین کار تأیید است.</> }); onClose(); })
    .catch((e) => toast({ tone: 'error', text: faError(e) }));
  const setSrc = (i: number, p: Partial<Source>) => setSources((xs) => xs.map((s, j) => (j === i ? { ...s, ...p } : s)));
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={from ? <>نسخه‌ی تازه‌ی <span className="fig">{from.ref}</span></> : 'ورودی تازه‌ی دانشنامه'} description="هر ورودی دست‌کم یک منبع و تاریخ انقضا دارد." width={600}
      footer={<Button variant="primary" icon="knowledge" className="w-full" disabled={!valid} loading={act.create.isPending || act.update.isPending} onClick={() => void save()}>ثبت</Button>}>
      <div className="flex flex-col gap-4 text-[13px]">
        {!from ? (
          <>
            <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">لایه</span><div className="flex flex-wrap gap-2">{(['holding', 'company', 'department'] as const).map((l) => <FilterChip key={l} selected={layer === l} onClick={() => setLayer(l)}>{LAYER_FA[l]!.fa}</FilterChip>)}</div></div>
            {layer !== 'holding' ? (
              <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">شرکت</span>
                <div className="flex flex-wrap gap-2">{(companies ?? []).filter((c) => c.kind !== 'holding').map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => { setCompany(c.code); setDepartment(null); }}><span className="flex items-center gap-1.5"><CompanyMark code={c.code} height={12} mono />{c.name_fa}</span></FilterChip>)}</div>
              </div>
            ) : null}
            {layer === 'department' && company ? (
              <DeptSelect company={company} value={department} onChange={setDepartment} />
            ) : null}
          </>
        ) : null}
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">نوع</span><div className="flex flex-wrap gap-2">{KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{KNOWLEDGE_KIND[k]}</FilterChip>)}</div></div>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">عنوان<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} className={cx(field, 'h-10')} /></label>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">متن<textarea value={body} onChange={(e) => setBody(e.target.value)} rows={7} className={cx(field, 'py-2 leading-7')} /></label>
        <div className="flex flex-col gap-2">
          <span className="font-semibold text-sec">منبع‌ها</span>
          {sources.map((s, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <select value={s.kind} onChange={(e) => setSrc(i, { kind: e.target.value })} aria-label="نوع منبع" className={cx(field, 'fig h-9 w-28 text-[12px]')}>{SOURCE_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}</select>
              <input value={s.ref} onChange={(e) => setSrc(i, { ref: e.target.value })} dir="ltr" placeholder="O-000031" aria-label="ارجاع منبع" className={cx(field, 'fig h-9 w-36 text-[12px]')} />
              <input value={s.note} onChange={(e) => setSrc(i, { note: e.target.value })} placeholder="یادداشت" aria-label="یادداشت منبع" className={cx(field, 'h-9 min-w-0 flex-1 text-[12px]')} />
              {sources.length > 1 ? <Button size="sm" variant="ghost" icon="close" aria-label="حذف منبع" onClick={() => setSources((xs) => xs.filter((_, j) => j !== i))} /> : null}
            </div>
          ))}
          <Button size="sm" variant="ghost" icon="add" className="self-start" onClick={() => setSources((xs) => [...xs, { kind: 'doc', ref: '', note: '' }])}>منبع دیگر</Button>
        </div>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">معتبر تا
          <input type="date" dir="ltr" value={until} min={min} max={max} onChange={(e) => setUntil(e.target.value)} className={cx(field, 'fig h-10')} />
          <span className="text-[11px] font-normal text-muted">حداکثر {VALID_DAYS[kind]} روز برای «{KNOWLEDGE_KIND[kind]}». چهارده روز پیش از انقضا یک کار بازبینی برای نگه‌دار لایه ساخته میشود.</span>
        </label>
      </div>
    </Sheet>
  );
}

export function ExpiringCard({ items, onOpen }: { items: KnowledgeEntry[]; onOpen: (ref: string) => void }) {
  if (!items.length) return null;
  return (
    <Card className="flex flex-col gap-2 bg-warn-soft p-4">
      <span className="flex items-center gap-2 text-[13px] font-semibold text-ink"><span className="text-warn"><Icon name="time" size={16} /></span>{items.length} ورودی تا ۱۴ روز دیگر منقضی میشود</span>
      <ul className="flex flex-col gap-1">{items.map((e) => <li key={e.ref}><button type="button" onClick={() => onOpen(e.ref)} className="flex w-full flex-wrap items-center gap-2 text-right text-[13px] hover:underline"><span className="fig text-[11px] text-muted">{e.ref}</span><span className="text-ink">{e.title_fa}</span><Expiry e={e} /></button></li>)}</ul>
    </Card>
  );
}
