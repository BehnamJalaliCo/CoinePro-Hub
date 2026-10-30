'use client';

import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { FilterChip } from '@/components/ui/primitives';
import { CompanyMark } from '@/components/brand/marks';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies, useCreateWork, useDepartments } from '@/lib/api/hooks';
import { cx } from '@/lib/format';
import { DEFAULT_PRIORITY } from '@/lib/priority';
import { PriorityPicker } from '@/components/v21/priority';

type Prio = 'P0' | 'P1' | 'P2' | 'P3' | 'P4';

/** The owner's order (OPERATING_MODEL §1.4): to a company's CEO, or straight to a department manager. */
export function NewOrder({ open, onOpenChange, company: initial }: { open: boolean; onOpenChange: (v: boolean) => void; company?: string | null }) {
  const { data: companies } = useCompanies();
  const [company, setCompany] = useState<string | null>(initial ?? null);
  const deps = useDepartments(company ?? '__none__');
  const [dept, setDept] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [brief, setBrief] = useState('');
  const [priority, setPriority] = useState<Prio>(DEFAULT_PRIORITY as Prio);
  const [due, setDue] = useState('');
  const create = useCreateWork();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const ok = company && title.trim().length >= 3;
  const field = 'rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink';
  const submit = async () => {
    if (!company) return;
    try {
      const out = await create.mutateAsync({ company, department: dept, title: title.trim(), brief: brief.trim(), priority, kind: 'one_off', due_at: due ? new Date(due).toISOString() : null });
      const o = out as { ref?: string; id?: string };
      // 0.4.0: the order is followed from here on («فرمان‌های من»).
      toast({ tone: 'ok', text: <>فرمان ثبت شد: <span className="fig">{o.ref ?? ''}</span>. {dept ? 'مدیر دپارتمان' : 'مدیرعامل'} بیدار شد.</>, action: o.id ? { label: 'پیگیری', run: () => router.push(`/work/${o.id}`) } : undefined });
      void qc.invalidateQueries({ queryKey: ['work', 'orders'] });
      onOpenChange(false);
      setTitle(''); setBrief(''); setDept(null);
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' });
    }
  };
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="فرمان تازه" description="به مدیرعامل شرکت؛ اگر کار روشن است، مستقیم به مدیر همان دپارتمان." width={520}
      footer={<Button variant="primary" icon="send" className="w-full" disabled={!ok} loading={create.isPending} onClick={submit}>بفرست</Button>}>
      <div className="flex flex-col gap-5">
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-[13px] text-sec">شرکت</legend>
          <div className="flex flex-wrap gap-2">
            {(companies ?? []).map((c) => (
              <FilterChip key={c.code} selected={company === c.code} onClick={() => { setCompany(c.code); setDept(null); }}>
                <span className="flex items-center gap-1.5"><CompanyMark code={c.code} height={13} mono />{c.name_fa}</span>
              </FilterChip>
            ))}
          </div>
        </fieldset>
        {company && deps.data?.length ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="pb-2 text-[13px] text-sec">دپارتمان (اختیاری؛ میانبر به مدیر)</legend>
            <div className="flex flex-wrap gap-2">
              <FilterChip selected={!dept} onClick={() => setDept(null)}>مدیرعامل تصمیم بگیرد</FilterChip>
              {deps.data.map((d) => <FilterChip key={d.code} selected={dept === d.code} onClick={() => setDept(d.code)}>{d.name_fa}</FilterChip>)}
            </div>
          </fieldset>
        ) : null}
        <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">چه کاری؟</span><input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} className={cx(field, 'h-12')} placeholder="مثلاً: علت کندی ثبت‌نام را پیدا کن و راه‌حل بده" /></label>
        <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">توضیح و معیار تمام شدن</span><textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={4} maxLength={10000} className={cx(field, 'py-3 leading-7')} /></label>
        {/* 0.4.0: priorities in words; the chosen one's meaning in one line beneath. */}
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-[13px] text-sec">اولویت</legend>
          <PriorityPicker value={priority} onChange={(c) => setPriority(c as Prio)} />
        </fieldset>
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">موعد (اختیاری)</span><input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} className={cx(field, 'fig h-10')} /></label>
        </div>
      </div>
    </Sheet>
  );
}
