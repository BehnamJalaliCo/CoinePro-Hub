'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark, Monogram } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Bar, Card, ErrorState, PageHeader, Pill, Skeleton, budgetTone } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { api, ok, ApiError } from '@/lib/api/client';
import { useCompanies, useTreasury } from '@/lib/api/hooks';
import { stepUp } from '@/lib/auth';
import { cx, tokens, until } from '@/lib/format';
import { useQueryClient } from '@tanstack/react-query';

function NewCompany({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState({ code: '', name_fa: '', name_en: '' });
  const [busy, setBusy] = useState(false);
  const valid = /^[A-Z][A-Z0-9]{1,4}$/.test(f.code) && f.name_fa.trim() && f.name_en.trim();
  const create = async () => {
    setBusy(true);
    try {
      const token = await stepUp('company.create', f.code);
      await ok(api.POST('/api/v1/companies', { body: { code: f.code, name_fa: f.name_fa.trim(), name_en: f.name_en.trim(), template: 'standard' }, headers: { 'X-Step-Up': token } }));
      toast({ tone: 'ok', text: `${f.name_fa} ساخته شد: هشت دپارتمان و جایگاه‌های رهبری، همه خواب.` });
      void qc.invalidateQueries({ queryKey: ['companies'] });
      onOpenChange(false);
      setF({ code: '', name_fa: '', name_en: '' });
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ساخته نشد.' });
    } finally { setBusy(false); }
  };
  const field = 'h-11 rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink';
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="افزودن شرکت" description="شرکت داده است: یک رکورد، از روی قالب استاندارد (هشت دپارتمان)." footer={<Button variant="primary" icon="seal" className="w-full" disabled={!valid} loading={busy} onClick={create}>ساختن با تأیید passkey</Button>}>
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">کد (لاتین، ۲ تا ۵ حرف، تغییرناپذیر)</span><input dir="ltr" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 5) })} className={cx(field, 'fig')} placeholder="NX" /></label>
        <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">نام فارسی</span><input value={f.name_fa} onChange={(e) => setF({ ...f, name_fa: e.target.value })} className={field} /></label>
        <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">نام انگلیسی</span><input dir="ltr" value={f.name_en} onChange={(e) => setF({ ...f, name_en: e.target.value })} className={cx(field, 'fig')} /></label>
        <p className="text-[12px] leading-5 text-muted">نشان شرکت بعداً در <span className="fig">design/brand/companies/</span> اضافه میشود؛ تا آن موقع کد شرکت جای نشان را میگیرد.</p>
      </div>
    </Sheet>
  );
}

export default function CompaniesPage() {
  const q = useCompanies();
  const { data: t } = useTreasury({ period: 'month' });
  const [add, setAdd] = useState(false);
  const budget = (code: string) => t?.budgets.find((b) => b.company === code && b.scope_type !== 'holding');
  return (
    <>
      <PageHeader eyebrow={`${q.data?.filter((c) => c.kind !== 'holding').length ?? '…'} شرکت`} title="شرکت‌ها" actions={<Button variant="primary" icon="add" onClick={() => setAdd(true)}>افزودن شرکت</Button>} />
      {q.isLoading ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-56 rounded-[16px]" />)}</div>
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {(q.data ?? []).map((c) => {
              const b = budget(c.code);
              const locked = c.kill_switch === 'engaged';
              const holding = c.kind === 'holding';
              return (
                <Link key={c.code} href={`/companies/${c.code}`} className="group">
                  <Card className={cx('flex h-full flex-col gap-4 p-5 transition-colors group-hover:bg-tile', holding && 'tahrir')}>
                    <div className="flex items-start gap-3">
                      <span className="flex size-14 flex-none items-center justify-center rounded-full border border-strong bg-tile text-ink">
                        {holding ? <Monogram size={26} /> : <CompanyMark code={c.code} height={24} />}
                      </span>
                      <div className="flex min-w-0 flex-1 flex-col">
                        <span className="text-h3 font-semibold">{c.name_fa}</span>
                        <span className="fig text-[12px] text-muted">{c.name_en} · {c.code}</span>
                      </div>
                      {locked ? <Pill tone="neg" icon="lock">توقف</Pill> : holding ? <Pill tone="gold">هلدینگ</Pill> : <Pill tone="pos" dot>فعال</Pill>}
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      {[['کارمند فعال', c.counts.employees_active], ['کار باز', c.counts.work_open], ['منتظر مُهر', c.counts.decisions_pending]].map(([l, v]) => (
                        <div key={String(l)} className="flex flex-col rounded-[12px] bg-page px-3 py-2"><span className="text-[11px] text-muted">{l}</span><span className={cx('text-[20px] font-semibold', l === 'منتظر مُهر' && Number(v) > 0 && 'text-gold-ink')}>{v}</span></div>
                      ))}
                    </div>
                    {b ? (
                      <div className="flex flex-col gap-1.5">
                        <div className="flex items-center text-[12px] text-sec"><span className="flex-1">بودجه‌ی ماه</span><span className="fig text-muted">{tokens(b.tokens_used)} / {tokens(b.token_limit)}</span></div>
                        <Bar pct={b.pct ?? 0} tone={budgetTone(b.pct)} />
                      </div>
                    ) : null}
                    {c.deploy_freeze_until && new Date(c.deploy_freeze_until) > new Date() ? (
                      <span className="flex items-center gap-2 text-[12px] text-warn"><Icon name="pause" size={14} />توقف deploy، {until(c.deploy_freeze_until)}</span>
                    ) : null}
                  </Card>
                </Link>
              );
            })}
          </div>
        )}
      <NewCompany open={add} onOpenChange={setAdd} />
    </>
  );
}
