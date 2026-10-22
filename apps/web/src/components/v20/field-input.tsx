'use client';

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { FilterChip } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { faError, usePartyAction, type Field, type Money } from '@/lib/api/v20';
import { cx } from '@/lib/format';
import { JDay, REF_KIND_FA, bad, isMoney, useArchive, field, fieldArea } from './bits';

const NUM = /^-?\d+(\.\d+)?$/;
/** A typed number when it reads as one, the raw text while it is still being typed («4.»), nothing when empty. */
const numOrRaw = (s: string): number | string | undefined => (s.trim() === '' ? undefined : NUM.test(s.trim()) ? Number(s.trim()) : s);
const ltr = 'fig text-left';

/** A party from the registry, or a new one made right here (kind and Persian name; the rest later in settings). */
export function PartyPicker({ value, onChange, scope, invalid, label }: { value: string | null; onChange: (ref: string | null) => void; scope?: string | null; invalid?: boolean; label: string }) {
  const m = useArchive();
  const act = usePartyAction();
  const toast = useToast();
  const [making, setMaking] = useState(false);
  const [kind, setKind] = useState('');
  const [name, setName] = useState('');
  // One key per party: a retry after a lost answer reuses it, a new party (or a refused one corrected) gets a fresh one.
  const [key, setKey] = useState(() => crypto.randomUUID());
  const list = m.parties.filter((p) => p.status === 'active' || p.ref === value);
  // The scope's own parties first; a party of another scope is still allowed (a registry office serves every company).
  const sorted = scope ? [...list].sort((a, b) => Number(b.scopes.includes(scope)) - Number(a.scopes.includes(scope))) : list;
  const make = async () => {
    try {
      const p = await act.create.mutateAsync({ body: { kind: kind || m.schema?.party_kinds[0]?.key || 'other', name_fa: name.trim(), name_en: null, identifiers: {}, scopes: scope ? [scope] : [] }, key });
      onChange(p.ref);
      setKey(crypto.randomUUID());
      setMaking(false);
      setName('');
      toast({ tone: 'ok', text: <>طرف <span className="fig">{p.ref}</span> به رجیستری اضافه شد.</> });
    } catch (e) { if (e instanceof ApiError && e.status) setKey(crypto.randomUUID()); toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex min-w-0 gap-1.5">
        <select aria-label={label} value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} className={field('flex-1', invalid && bad)}>
          <option value="">—</option>
          {sorted.map((p) => <option key={p.ref} value={p.ref}>{p.name_fa}{p.name_en ? ` (${p.name_en})` : ''}</option>)}
        </select>
        <Button size="md" variant="ghost" icon="add" aria-label="طرف تازه" title="طرف تازه" onClick={() => setMaking((v) => !v)} className="px-2.5" />
      </div>
      {making ? (
        <div className="flex flex-wrap items-center gap-1.5 rounded-[10px] bg-tile p-2">
          <select aria-label="نوع طرف" value={kind} onChange={(e) => setKind(e.target.value)} className={field('h-9 w-auto flex-none')}>
            {(m.schema?.party_kinds ?? []).filter((k) => k.status !== 'retired').map((k) => <option key={k.key} value={k.key}>{k.title_fa}</option>)}
          </select>
          <input aria-label="نام طرف تازه" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="نام فارسی" className={field('h-9 min-w-[8rem] flex-1')} />
          <Button size="sm" variant="secondary" disabled={!name.trim()} loading={act.create.isPending} onClick={make}>بساز</Button>
        </div>
      ) : null}
    </div>
  );
}

/** One metadata input, typed by its field (§23.2): the editor never offers a shape the server would refuse. */
export function FieldInput({ f, value, onChange, error, scope }: { f: Field; value: unknown; onChange: (v: unknown) => void; error?: string | null; scope?: string | null }) {
  const m = useArchive();
  const { data: companies } = useCompanies();
  const invalid = !!error;
  const label = f.title_fa;
  let body: React.ReactNode;
  switch (f.type) {
    case 'long_text':
      body = <textarea aria-label={label} value={String(value ?? '')} onChange={(e) => onChange(e.target.value || undefined)} rows={3} maxLength={10_000} className={fieldArea(invalid && bad)} />;
      break;
    case 'number':
    case 'percent':
      body = (
        <span className="flex items-center gap-1.5">
          <input aria-label={label} inputMode="decimal" dir="ltr" value={value == null ? '' : String(value)} onChange={(e) => onChange(numOrRaw(e.target.value))} className={field(ltr, invalid && bad)} />
          {f.type === 'percent' ? <span className="fig text-muted">%</span> : null}
        </span>
      );
      break;
    case 'money': {
      const v = isMoney(value) ? value : null;
      const cur = f.currency ?? v?.currency ?? m.vocab?.currencies[0] ?? 'USD';
      const other = v && f.currency && v.currency !== f.currency;
      body = (
        <span className="flex flex-col gap-1">
          <span className="flex items-center gap-1.5">
            <input aria-label={label} inputMode="decimal" dir="ltr" value={v?.amount ?? ''} placeholder="0.00"
              onChange={(e) => onChange(e.target.value.trim() ? ({ amount: e.target.value.trim().replace(/,/g, ''), currency: f.currency ?? v?.currency ?? cur } satisfies Money) : undefined)} className={field(ltr, invalid && bad)} />
            {f.currency ? <span className="fig flex-none text-[13px] text-sec">{f.currency}</span> : (
              <select aria-label={`${label}: واحد`} value={cur} onChange={(e) => onChange({ amount: v?.amount ?? '', currency: e.target.value })} className={field('fig w-24 flex-none')}>
                {(m.vocab?.currencies ?? [cur]).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            )}
          </span>
          {other ? <span className="text-[11px] text-warn">واحد این مبلغ <span className="fig">{v.currency}</span> است؛ این فیلد <span className="fig">{f.currency}</span> میخواهد. با ویرایش مبلغ، واحد درست میشود.</span> : null}
        </span>
      );
      break;
    }
    case 'date':
      body = (
        <span className="flex flex-wrap items-center gap-2">
          <input aria-label={label} type="date" dir="ltr" value={typeof value === 'string' ? value : ''} onChange={(e) => onChange(e.target.value || undefined)} className={field('fig w-auto min-w-[10rem]', invalid && bad)} />
          {typeof value === 'string' && value ? <JDay d={value} className="text-[12px] text-sec" /> : null}
        </span>
      );
      break;
    case 'date_range': {
      const r = (value && typeof value === 'object' ? value : {}) as { from?: string; to?: string };
      const set = (k: 'from' | 'to', v: string) => { const n = { ...r, [k]: v || undefined }; onChange(n.from || n.to ? n : undefined); };
      body = (
        <span className="flex flex-wrap items-center gap-2">
          <input aria-label={`${label}: از`} type="date" dir="ltr" value={r.from ?? ''} onChange={(e) => set('from', e.target.value)} className={field('fig w-auto min-w-[10rem]', invalid && bad)} />
          <span className="text-muted">تا</span>
          <input aria-label={`${label}: تا`} type="date" dir="ltr" value={r.to ?? ''} onChange={(e) => set('to', e.target.value)} className={field('fig w-auto min-w-[10rem]', invalid && bad)} />
        </span>
      );
      break;
    }
    case 'enum':
      body = (
        <select aria-label={label} value={typeof value === 'string' ? value : ''} onChange={(e) => onChange(e.target.value || undefined)} className={field(invalid && bad)}>
          <option value="">—</option>
          {(f.options ?? []).map((o) => <option key={o.key} value={o.key}>{o.title_fa}</option>)}
        </select>
      );
      break;
    case 'multi_enum': {
      const xs = Array.isArray(value) ? (value as string[]) : [];
      body = <span className="flex flex-wrap gap-1.5">{(f.options ?? []).map((o) => <FilterChip key={o.key} selected={xs.includes(o.key)} onClick={() => { const n = xs.includes(o.key) ? xs.filter((x) => x !== o.key) : [...xs, o.key]; onChange(n.length ? n : undefined); }}>{o.title_fa}</FilterChip>)}</span>;
      break;
    }
    case 'boolean':
      body = (
        <span role="radiogroup" aria-label={label} className="flex gap-1.5">
          <FilterChip selected={value === true} onClick={() => onChange(value === true ? undefined : true)}>بله</FilterChip>
          <FilterChip selected={value === false} onClick={() => onChange(value === false ? undefined : false)}>نه</FilterChip>
        </span>
      );
      break;
    case 'party':
      body = <PartyPicker label={label} value={typeof value === 'string' ? value : null} onChange={(v) => onChange(v ?? undefined)} scope={scope} invalid={invalid} />;
      break;
    case 'company':
      body = (
        <select aria-label={label} value={typeof value === 'string' ? value : ''} onChange={(e) => onChange(e.target.value || undefined)} className={field(invalid && bad)}>
          <option value="">—</option>
          {(companies ?? []).map((c) => <option key={c.code} value={c.code}>{c.name_fa}</option>)}
        </select>
      );
      break;
    case 'ref': {
      const r = (value && typeof value === 'object' ? value : {}) as { kind?: string; ref?: string };
      const kinds = f.ref_kinds?.length ? f.ref_kinds : (m.vocab?.ref_kinds ?? []);
      const kind = r.kind && kinds.includes(r.kind as never) ? r.kind : kinds[0] ?? 'record';
      body = (
        <span className="flex min-w-0 gap-1.5">
          {kinds.length > 1 ? (
            <select aria-label={`${label}: نوع`} value={kind} onChange={(e) => onChange(r.ref ? { kind: e.target.value, ref: r.ref } : undefined)} className={field('w-auto flex-none')}>
              {kinds.map((k) => <option key={k} value={k}>{REF_KIND_FA[k] ?? k}</option>)}
            </select>
          ) : <span className="flex h-10 flex-none items-center text-[12px] text-muted">{REF_KIND_FA[kind] ?? kind}</span>}
          <input aria-label={label} dir="ltr" value={r.ref ?? ''} placeholder={kind === 'case' ? 'LC-0001' : kind === 'decision' ? 'D-000000' : kind === 'record' ? 'AR-000000' : ''} onChange={(e) => onChange(e.target.value.trim() ? { kind, ref: e.target.value.trim() } : undefined)} className={field(ltr, invalid && bad)} />
        </span>
      );
      break;
    }
    case 'url': case 'email': case 'phone': case 'id_code': case 'iban':
      body = <input aria-label={label} dir="ltr" type={f.type === 'email' ? 'email' : f.type === 'url' ? 'url' : 'text'} inputMode={f.type === 'phone' ? 'tel' : undefined} value={String(value ?? '')} onChange={(e) => onChange(e.target.value.trim() ? e.target.value : undefined)} className={field(ltr, invalid && bad)} />;
      break;
    default:
      // text, and any type added to the closed list later: a plain line of text until the editor learns it.
      body = <input aria-label={label} value={String(value ?? '')} onChange={(e) => onChange(e.target.value || undefined)} maxLength={500} className={field(invalid && bad)} />;
  }
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <span className="flex flex-wrap items-center gap-1.5 text-[12px] font-semibold text-sec">
        {f.title_fa}{f.required ? <span className="text-neg" aria-label="لازم">*</span> : null}
        <span className="font-normal text-muted">{m.typeFa(f.type)}</span>
        {f.sensitive ? <span className="inline-flex items-center gap-0.5 font-normal text-muted"><Icon name="lock" size={11} />حساس</span> : null}
      </span>
      {body}
      {error ? <span className="text-[12px] text-neg">{error}</span> : f.help_fa ? <span className="text-[11px] text-muted">{f.help_fa}</span> : null}
    </div>
  );
}

/** Is a value empty, as the server reads it (an empty money amount too)? */
export const emptyValue = (v: unknown) => v == null || v === '' || (Array.isArray(v) && !v.length) || (isMoney(v) && !v.amount);
/** The required, active fields a metadata object still misses. */
export const missingRequired = (fields: Field[], md: Record<string, unknown>) => fields.filter((f) => f.required && f.status === 'active' && emptyValue(md[f.key]));
/** The server's `metadata.<key>` errors, by field key. */
export const metaErrors = (fields: Record<string, string>) => Object.fromEntries(Object.entries(fields).filter(([k]) => k.startsWith('metadata.')).map(([k, v]) => [k.slice(9), v]));
