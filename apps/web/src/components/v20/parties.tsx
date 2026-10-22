'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { useParties, usePartyAction, type Party, type PartyIn } from '@/lib/api/v20';
import { cx } from '@/lib/format';
import { ErrorLine, FieldValue, bad, fieldErrors, useArchive, field } from './bits';
import { FieldInput, metaErrors } from './field-input';

/** One party of the registry: its kind decides which identifiers it has (the kind's fields, typed). No passkey: the registry is
 *  data the archivist keeps too; a party is retired, never deleted. */
function PartySheet({ p, onClose }: { p: Party | null; onClose: () => void }) {
  const m = useArchive();
  const { data: companies } = useCompanies();
  const act = usePartyAction();
  const toast = useToast();
  const kinds = (m.schema?.party_kinds ?? []).filter((k) => k.status !== 'retired' || k.key === p?.kind);
  const [d, setD] = useState<PartyIn>(() => ({ kind: p?.kind ?? kinds[0]?.key ?? 'other', name_fa: p?.name_fa ?? '', name_en: p?.name_en ?? null, identifiers: { ...(p?.identifiers ?? {}) }, scopes: [...(p?.scopes ?? [])] }));
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<unknown>(null);
  const k = m.partyKind(d.kind);
  const fields = (k?.identifier_fields ?? []).filter((f) => f.status !== 'retired' || d.identifiers[f.key] != null);
  const ie = Object.fromEntries(Object.entries(metaErrors(errors)));
  const body = (): PartyIn => ({ ...d, name_fa: d.name_fa.trim(), name_en: d.name_en?.trim() || null, identifiers: Object.fromEntries(Object.entries(d.identifiers).filter(([key2, v]) => v != null && v !== '' && fields.some((f) => f.key === key2))) });
  const save = async (status?: Party['status']) => {
    setErrors({}); setFailure(null);
    try {
      if (p) await act.patch.mutateAsync({ p, body: status ? { status } : body() });
      else await act.create.mutateAsync({ body: body(), key });
      toast({ tone: 'info', text: status === 'retired' ? 'طرف بازنشسته شد؛ سندهایش میمانند.' : 'رجیستری طرف‌ها ذخیره شد.' });
      onClose();
    } catch (e) { if (e instanceof ApiError && e.status) setKey(crypto.randomUUID()); setErrors(fieldErrors(e)); setFailure(e); }
  };
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={560} title={p ? p.name_fa : 'طرف تازه'} description={p ? <span className="fig">{p.ref}</span> : 'صرافی، تأمین‌کننده، بانک، نهاد دولتی یا شخص؛ شناسه‌ها طبق نوعش.'}
      footer={<div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={!d.name_fa.trim()} loading={act.create.isPending || act.patch.isPending} onClick={() => save()}>ذخیره</Button>
        <Button variant="ghost" onClick={onClose}>انصراف</Button>
        <span className="flex-1" />
        {p && p.status !== 'retired' ? <Button size="sm" variant="danger" icon="pause" onClick={() => save('retired')}>بازنشسته کن</Button> : null}
      </div>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <label className="flex flex-col gap-1.5 font-semibold text-sec">نوع
          <select aria-label="نوع طرف" value={d.kind} onChange={(e) => setD({ ...d, kind: e.target.value })} className={field(errors.kind && bad)}>
            {kinds.map((x) => <option key={x.key} value={x.key}>{x.title_fa}</option>)}
          </select>
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex min-w-0 flex-col gap-1.5 font-semibold text-sec">نام فارسی<input value={d.name_fa} onChange={(e) => setD({ ...d, name_fa: e.target.value })} maxLength={160} className={field(errors.name_fa && bad)} /></label>
          <label className="flex min-w-0 flex-col gap-1.5 font-semibold text-sec">نام لاتین<input dir="ltr" value={d.name_en ?? ''} onChange={(e) => setD({ ...d, name_en: e.target.value })} maxLength={160} className={field('fig text-left')} /></label>
        </div>
        <fieldset className="flex flex-col gap-2"><legend className="pb-2 font-semibold text-sec">برای کدام دامنه‌ها</legend>
          <span className="flex flex-wrap gap-1.5">{(companies ?? []).map((c) => <FilterChip key={c.code} selected={d.scopes.includes(c.code)} onClick={() => setD({ ...d, scopes: d.scopes.includes(c.code) ? d.scopes.filter((x) => x !== c.code) : [...d.scopes, c.code] })}>{c.name_fa}</FilterChip>)}</span>
        </fieldset>
        {fields.length ? <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">{fields.map((f) => <FieldInput key={f.key} f={f} value={d.identifiers[f.key]} error={ie[f.key] ?? null} onChange={(v) => setD({ ...d, identifiers: { ...d.identifiers, [f.key]: v } })} />)}</div> : null}
        <ErrorLine error={failure} />
      </div>
    </Sheet>
  );
}

export function PartiesTab({ sel, onOpen }: { sel: string | null; onOpen: (ref: string | null) => void }) {
  const m = useArchive();
  const q = useParties({});
  const [making, setMaking] = useState(false);
  const xs = [...(q.data ?? [])].sort((a, b) => Number(a.status === 'retired') - Number(b.status === 'retired'));
  const open = sel ? xs.find((p) => p.ref === sel) ?? null : null;
  return (
    <Card className="flex min-w-0 flex-col gap-1 p-2">
      <div className="flex flex-wrap items-center gap-2 px-2 py-1.5">
        <p className="min-w-0 flex-1 text-[12px] leading-5 text-muted">رجیستری طرف‌ها: هر سند به طرف‌هایش وصل است و قاعده‌ها طرف شناخته را از متن پیدا میکنند. شناسه‌های حساس فقط تا چهار رقم آخر نشان داده میشوند.</p>
        <Button size="sm" variant="secondary" icon="add" onClick={() => setMaking(true)}>طرف تازه</Button>
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-40" /> : !xs.length ? <Empty icon="companies" title="طرفی نیست" /> : (
        <ul className="flex flex-col">
          {xs.map((p) => {
            const k = m.partyKind(p.kind);
            return (
              <li key={p.ref} className={cx('flex min-w-0 items-start gap-2 rounded-[12px] px-3 py-2.5 hover:bg-hover', p.status === 'retired' && 'opacity-60')}>
                <button type="button" onClick={() => onOpen(p.ref)} className="flex min-w-0 flex-1 flex-col gap-1 text-start">
                  <span className="flex min-w-0 flex-wrap items-center gap-2"><span className="min-w-0 truncate text-[14px] font-semibold text-ink">{p.name_fa}</span>{p.name_en ? <span className="fig truncate text-[12px] text-muted">{p.name_en}</span> : null}{p.status === 'retired' ? <Pill className="h-5 text-[11px]">بازنشسته</Pill> : null}</span>
                  <span className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted">
                    <span className="fig">{p.ref}</span><span>{k?.title_fa ?? p.kind}</span><span className="fig">{p.scopes.join(' · ')}</span>
                    {(k?.identifier_fields ?? []).filter((f) => p.identifiers[f.key] != null).slice(0, 2).map((f) => <span key={f.key} className="inline-flex items-center gap-1">{f.title_fa}: <FieldValue f={f} v={p.identifiers[f.key]} plain /></span>)}
                  </span>
                </button>
                {p.records ? <Link href={`/archive?party=${p.ref}`} className="flex-none text-[12px] font-semibold text-gold-ink hover:underline">{p.records} سند</Link> : null}
              </li>
            );
          })}
        </ul>
      )}
      {open ? <PartySheet key={`${open.ref}:${open.version ?? 1}`} p={open} onClose={() => onOpen(null)} /> : null}
      {making ? <PartySheet p={null} onClose={() => setMaking(false)} /> : null}
    </Card>
  );
}
