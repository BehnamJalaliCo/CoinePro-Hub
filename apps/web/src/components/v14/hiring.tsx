'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Card, FilterChip, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies, useConnections, useDepartments } from '@/lib/api/hooks';
import { hireableRoles, useHiring, useHiringAction, useRoles, type HireIn, type RoleInfo } from '@/lib/api/v14';
import { ago, cx, modelLabel, tokens } from '@/lib/format';

const field = 'h-11 w-full rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink';
const EFFORTS = ['low', 'medium', 'high', 'xhigh'] as const;
const MODELS = ['claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5'];

/** Contract §18.11: hiring starts with the owner (owner, 2026-10-17). Closed until the owner opens it, by hiring directly or by asking the CEOs. */
export function HiringCard() {
  const { data: h, isLoading } = useHiring();
  const act = useHiringAction();
  const toast = useToast();
  const [sheet, setSheet] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const open = h?.state === 'open';

  const startProposals = async () => {
    try {
      await act.start.mutateAsync('proposals');
      setConfirm(false);
      toast({ tone: 'ok', text: 'استخدام باز شد؛ هر مدیرعامل یک کار «تیم ماه اول» گرفت.' });
    } catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : 'باز نشد.' }); }
  };
  const close = async () => {
    try {
      await act.close.mutateAsync();
      toast({ tone: 'info', text: 'استخدام بسته شد؛ پیشنهادهای منتظر پس گرفته شدند.' });
    } catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'بسته نشد.' }); }
  };

  return (
    <Card className="flex flex-col gap-4 p-5">
      <SectionTitle title="استخدام" note="تا خودت شروع نکنی، هیچ ایجنتی استخدام پیشنهاد نمیدهد."
        action={h ? <Pill tone={open ? 'pos' : 'neutral'} dot>{open ? 'باز برای پیشنهاد' : 'بسته'}</Pill> : undefined} />
      {isLoading || !h ? <Skeleton className="h-28" /> : (
        <>
          <p className="text-[13px] leading-6 text-sec">
            {open ? 'مدیرعامل‌ها تیم ماه اول را پیشنهاد میدهند؛ هر پیشنهاد با برآورد توکن به کارتابل تو میرسد.'
              : h.mode === 'self' ? 'فقط خودت استخدام میکنی؛ ایجنت‌ها پیشنهاد نمیدهند و کمبود تیم را در خروجی کارشان مینویسند.'
                : 'وقتی هاب را برای کار واقعی بالا آوردی، یکی از دو راه را انتخاب کن. تا آن موقع ایجنت‌ها کمبود تیم را فقط در خروجی کارشان مینویسند.'}
            {h.changed_at ? <span className="text-muted">{' '}({h.changed_by?.kind === 'owner' ? 'تو' : 'سیستم'}، {ago(h.changed_at)})</span> : null}
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <Choice icon="hire" title="خودم استخدام میکنم" note="نقش، دپارتمان، مدل و effort را خودت انتخاب میکنی و با گذرکلید مُهر میکنی." onClick={() => setSheet(true)} />
            {open
              ? <Choice icon="close" title="بستن استخدام" note="پیشنهادهای منتظر پس گرفته میشوند؛ چیزی حذف نمیشود." onClick={close} busy={act.close.isPending} />
              : <Choice icon="seal" title="مدیرعامل‌ها پیشنهاد بدهند" note="هر مدیرعامل یک کار «تیم ماه اول» میگیرد؛ پیشنهادها همان لحظه در کارتابل." onClick={() => setConfirm(true)} />}
          </div>
          {h.withdrawn.length ? (
            <div className="flex flex-col gap-2">
              <span className="text-[12px] text-muted">پیشنهادهای پس‌گرفته (در تاریخچه میمانند)</span>
              <div className="flex flex-wrap gap-1.5">
                {h.withdrawn.map((r) => <Link key={r} href={`/cartable?ref=${r}`} className="fig inline-flex h-7 items-center rounded-full bg-tile px-2.5 text-[12px] text-sec hover:bg-hover">{r}</Link>)}
              </div>
            </div>
          ) : null}
        </>
      )}
      <HireSheet open={sheet} onOpenChange={setSheet} />
      <Dialog open={confirm} onOpenChange={setConfirm} title="استخدام برای مدیرعامل‌ها باز شود؟"
        actions={<>
          <Button variant="primary" icon="seal" loading={act.start.isPending} onClick={startProposals}>با گذرکلید باز کن</Button>
          <Button variant="ghost" onClick={() => setConfirm(false)}>نه حالا</Button>
        </>}>
        هر مدیرعامل (و هر نقش هلدینگ با وظیفه‌ی استخدام) یک کار «تیم ماه اولت را پیشنهاد بده» میگیرد. هیچ استخدامی بدون مُهر تو انجام نمیشود و هر وقت بخواهی میبندی.
      </Dialog>
    </Card>
  );
}

function Choice({ icon, title, note, onClick, busy }: { icon: 'hire' | 'seal' | 'close'; title: string; note: string; onClick: () => void; busy?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={busy}
      className="flex items-start gap-3 rounded-[12px] bg-tile p-3 text-start transition-colors hover:bg-hover disabled:opacity-60">
      <span className="mt-0.5 text-gold-ink"><Icon name={icon} size={20} /></span>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5"><span className="text-[14px] font-semibold text-ink">{title}</span><span className="text-[12px] leading-5 text-muted">{note}</span></span>
    </button>
  );
}

/** The owner's own hire (POST /org/hires): a charter that fits the company and the department, sealed with a passkey bound to the exact body. */
export function HireSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const toast = useToast();
  const act = useHiringAction();
  const { data: companies } = useCompanies();
  const { data: roles } = useRoles();
  const { data: connections } = useConnections();
  const [company, setCompany] = useState<string | null>(null);
  const [department, setDepartment] = useState<string | null>(null);
  const [role, setRole] = useState<RoleInfo | null>(null);
  const [titleFa, setTitleFa] = useState('');
  const [model, setModel] = useState('');
  const [effort, setEffort] = useState('high');
  const [reason, setReason] = useState('');
  const depts = useDepartments(company ?? '');
  const co = companies?.find((c) => c.code === company);
  const fitting = useMemo(() => (co && department ? hireableRoles(roles ?? [], co.kind, department) : []), [roles, co, department]);
  const models = useMemo(() => {
    const offered = new Set((connections ?? []).filter((c) => c.status === 'enabled').flatMap((c) => c.models));
    return MODELS.filter((m) => !offered.size || offered.has(m));
  }, [connections]);
  const ready = !!(company && department && role && titleFa.trim());

  const pickRole = (r: RoleInfo) => { setRole(r); setTitleFa(r.title_fa); setModel(r.model); setEffort(r.effort); };
  const reset = () => { setCompany(null); setDepartment(null); setRole(null); setTitleFa(''); setReason(''); };

  const submit = async () => {
    if (!ready || !role) return;
    const body: HireIn = { company: company!, department: department!, role: role.role, title_fa: titleFa.trim(), model, effort, ...(reason.trim() ? { reason: reason.trim() } : {}) };
    try {
      const out = await act.hire.mutateAsync(body);
      toast({ tone: 'ok', text: <><span className="fig">{out.employee.code}</span> استخدام شد (<span className="fig">{out.decision.ref}</span>).</> });
      onOpenChange(false);
      reset();
    } catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : 'استخدام نشد.' }); }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="استخدام مستقیم" description="با مُهر خودت؛ کارمند همان لحظه کارش را شروع میکند و کارت تصمیمش در تاریخچه میماند." width={560}
      footer={<Button variant="primary" icon="seal" className="w-full" disabled={!ready} loading={act.hire.isPending} onClick={submit}>با گذرکلید استخدام کن</Button>}>
      <div className="flex flex-col gap-5">
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-[13px] text-sec">کدام شرکت</legend>
          <div className="flex flex-wrap gap-2">
            {(companies ?? []).filter((c) => c.status === 'active').map((c) => (
              <button key={c.code} type="button" aria-pressed={company === c.code} onClick={() => { setCompany(c.code); setDepartment(null); setRole(null); }}
                className={cx('flex h-10 items-center gap-2 rounded-[10px] px-3 text-[13px] transition-colors', company === c.code ? 'bg-gold-soft text-ink ring-1 ring-[var(--hq-gold-ink)]' : 'bg-tile text-sec hover:bg-hover')}>
                <CompanyMark code={c.code} height={14} mono />{c.name_fa ?? c.code}
              </button>
            ))}
          </div>
        </fieldset>
        {company ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="pb-2 text-[13px] text-sec">کدام دپارتمان</legend>
            {depts.isLoading ? <Skeleton className="h-10" /> : (
              <div className="flex flex-wrap gap-2">
                {(depts.data ?? []).filter((d) => d.status === 'active').map((d) => <FilterChip key={d.code} selected={department === d.code} onClick={() => { setDepartment(d.code); setRole(null); }}>{d.name_fa}</FilterChip>)}
              </div>
            )}
          </fieldset>
        ) : null}
        {department ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="pb-2 text-[13px] text-sec">کدام نقش</legend>
            {!fitting.length ? <p className="rounded-[12px] bg-tile px-3 py-3 text-[13px] leading-6 text-muted">برای این دپارتمان هنوز منشور کارمندی نیست. منشور تازه را Claude سشن مشورت مینویسد؛ بگو چه نقشی میخواهی.</p> : (
              <div className="flex flex-col gap-1.5">
                {fitting.map((r) => (
                  <button key={r.role} type="button" aria-pressed={role?.role === r.role} onClick={() => pickRole(r)}
                    className={cx('flex items-center gap-3 rounded-[12px] px-3 py-2.5 text-start transition-colors', role?.role === r.role ? 'bg-gold-soft ring-1 ring-[var(--hq-gold-ink)]' : 'bg-tile hover:bg-hover')}>
                    <span className="text-sec"><Icon name="hire" size={20} /></span>
                    <span className="flex min-w-0 flex-1 flex-col"><span className="text-[14px] text-ink">{r.title_fa}</span><span className="fig truncate text-[11px] text-muted">{r.title_en}, {modelLabel(r.model)}, {r.effort}</span></span>
                    <span className="flex flex-col items-end text-[11px] text-muted"><span className="fig">{tokens(r.limits.tokens_per_run)}</span><span>سقف هر اجرا</span></span>
                  </button>
                ))}
              </div>
            )}
          </fieldset>
        ) : null}
        {role ? (
          <>
            <label className="flex flex-col gap-2">
              <span className="text-[13px] text-sec">عنوان فارسی</span>
              <input value={titleFa} onChange={(e) => setTitleFa(e.target.value)} maxLength={200} className={field} />
            </label>
            <div className="flex flex-wrap gap-5">
              <div className="flex flex-col gap-2">
                <span className="text-[13px] text-sec">مدل</span>
                <Segmented label="مدل" value={model} onChange={setModel} options={models.map((m) => ({ value: m, label: <span className="fig">{modelLabel(m).replace(/ [\d.]+$/, '')}</span> }))} />
              </div>
              <div className="flex flex-col gap-2">
                <span className="text-[13px] text-sec">effort</span>
                <Segmented label="effort" value={effort} onChange={setEffort} options={EFFORTS.map((x) => ({ value: x, label: <span className="fig">{x}</span> }))} />
              </div>
            </div>
            <p className="text-[12px] leading-5 text-muted">پیش‌فرض‌ها از منشور نقش‌اند (<span className="fig">{modelLabel(role.model)}</span>، <span className="fig">{role.effort}</span>). ارزان‌ترین مدلی که کار را خوب انجام میدهد بهترین است.</p>
            <label className="flex flex-col gap-2">
              <span className="text-[13px] text-sec">چرا (اختیاری)</span>
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} maxLength={5000} placeholder="مثلاً: پایش سایت و پنل کاربری" className={cx(field, 'h-auto py-3 leading-7')} />
            </label>
          </>
        ) : null}
      </div>
    </Sheet>
  );
}
