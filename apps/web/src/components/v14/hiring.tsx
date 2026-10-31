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
import { hireableRoles, useHiring, useHiringAction, useRoles, type HireIn, type Hiring, type RoleInfo } from '@/lib/api/v14';
import type { Company } from '@/lib/company';
import { companyOf } from '@/lib/company';
import type { IconName } from '@/generated/icons';
import { ago, cx, modelLabel, tokens } from '@/lib/format';

const field = 'h-11 w-full rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink';
const EFFORTS = ['low', 'medium', 'high', 'xhigh'] as const;
const MODELS = ['claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5'];

/** Contract §18.11 (owner, 2026-10-17): closed until the owner brings the hub up; then each company's CEO hires with full authority inside
 *  the company's monthly envelope and picks the model each job needs, or every hire is the owner's card. The owner can always hire directly. */
export function HiringCard() {
  const { data: h, isLoading } = useHiring();
  const { data: companies } = useCompanies();
  const act = useHiringAction();
  const toast = useToast();
  const [sheet, setSheet] = useState(false);
  const [envelopes, setEnvelopes] = useState<null | 'edit' | 'open'>(null);
  const [confirm, setConfirm] = useState(false);
  const open = h?.state === 'open';
  const delegated = open && h?.mode === 'delegated';
  const fail = (e: unknown, fa: string) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : fa });

  const startProposals = async () => {
    try {
      await act.start.mutateAsync('proposals');
      setConfirm(false);
      toast({ tone: 'ok', text: 'استخدام باز شد؛ هر استخدام یک کارت برای مُهر توست.' });
    } catch (e) { fail(e, 'باز نشد.'); }
  };
  const close = async () => {
    try {
      await act.close.mutateAsync();
      toast({ tone: 'info', text: 'استخدام بسته شد؛ پیشنهادهای منتظر پس گرفته شدند.' });
    } catch (e) { fail(e, 'بسته نشد.'); }
  };

  return (
    <Card className="flex flex-col gap-4 p-5">
      <SectionTitle title="استخدام" note={delegated ? 'مدیرعامل‌ها با اختیار کامل، داخل پاکت ماهانه‌ی هر شرکت' : 'تا خودت باز نکنی، هیچ ایجنتی استخدام پیشنهاد نمیدهد.'}
        action={h ? <Pill tone={open ? 'pos' : 'neutral'} dot>{delegated ? 'با مدیرعامل‌ها' : open ? 'با مُهر من' : 'بسته'}</Pill> : undefined} />
      {isLoading || !h ? <Skeleton className="h-28" /> : (
        <>
          <p className="text-[13px] leading-6 text-sec">
            {delegated ? 'هر دپارتمان به اندازه‌ی نیازش نیرو میخواهد و مدیرعامل تصمیم میگیرد و مدل هر کار را خودش انتخاب میکند. هر استخدام یک استوری میسازد؛ از همان‌جا خوش‌آمد میگویی یا برمیگردانی. مصرف درست بودجه ستاره میگیرد.'
              : open ? 'هر استخدام یک کارت در کارتابل توست، با برآورد توکن.'
                : 'وقتی هاب را برای کار واقعی بالا آوردی، اختیار را به مدیرعامل‌ها بده. تا آن موقع ایجنت‌ها کمبود تیم را فقط در خروجی کارشان مینویسند.'}
            {h.changed_at ? <span className="text-muted">{' '}({h.changed_by?.kind === 'owner' ? 'تو' : 'سیستم'}، {ago(h.changed_at)})</span> : null}
          </p>
          <Envelopes h={h} companies={companies} onEdit={() => setEnvelopes('edit')} />
          <div className="grid gap-2 sm:grid-cols-2">
            {!delegated ? <Choice icon="seal" title="اختیار استخدام با مدیرعامل‌ها" note="پاکت ماهانه‌ی هر شرکت را تعیین کن؛ از آن به بعد استخدام با خود مدیرعامل‌هاست." onClick={() => setEnvelopes('open')} primary /> : null}
            <Choice icon="hire" title="خودم استخدام میکنم" note="نقش، دپارتمان، مدل و effort را خودت انتخاب میکنی و با گذرکلید مُهر میکنی." onClick={() => setSheet(true)} />
            {!open ? <Choice icon="decision" title="هر استخدام با مُهر من" note="مدیرها پیشنهاد میدهند و هر استخدام یک کارت در کارتابل توست." onClick={() => setConfirm(true)} /> : null}
            {open ? <Choice icon="close" title="بستن استخدام" note="پیشنهادهای منتظر پس گرفته میشوند؛ چیزی حذف نمیشود." onClick={close} busy={act.close.isPending} /> : null}
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
      {h && envelopes ? <EnvelopeSheet h={h} mode={envelopes} onClose={() => setEnvelopes(null)} /> : null}
      <Dialog open={confirm} onOpenChange={setConfirm} title="هر استخدام با مُهر تو؟"
        actions={<>
          <Button variant="primary" icon="seal" loading={act.start.isPending} onClick={startProposals}>با گذرکلید باز کن</Button>
          <Button variant="ghost" onClick={() => setConfirm(false)}>نه حالا</Button>
        </>}>
        هر مدیرعامل یک کار «تیم ماه اولت را پیشنهاد بده» میگیرد و هر استخدام یک کارت در کارتابل توست. هر وقت بخواهی اختیار را به مدیرعامل‌ها میدهی یا میبندی.
      </Dialog>
    </Card>
  );
}

/** Each operating company's month: used and committed against its envelope. */
function Envelopes({ h, companies, onEdit }: { h: Hiring; companies: Company[] | undefined; onEdit: () => void }) {
  if (!h.envelopes.length) return null;
  return (
    <div className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
      <div className="flex items-center gap-2"><span className="flex-1 text-[12px] text-muted">پاکت ماهانه‌ی هر شرکت (توکن)</span><Button variant="ghost" size="sm" icon="budget" onClick={onEdit}>پاکت‌ها</Button></div>
      {h.envelopes.map((e) => {
        const cap = e.tokens_month ?? 0;
        const usedPct = cap ? Math.min(100, (e.used_month / cap) * 100) : 0;
        const committedPct = cap ? Math.min(100, (e.committed_month / cap) * 100) : 0;
        return (
          <div key={e.company} className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2 text-[13px]">
              <CompanyMark code={e.company} height={13} mono />
              <span className="min-w-0 flex-1 truncate">{companyOf(companies, e.company).nameFa}</span>
              {e.tokens_month ? <span className="fig text-[12px] text-sec">{tokens(e.used_month)} / {tokens(e.tokens_month)}</span> : <span className="text-[12px] text-warn">پاکت تعیین نشده</span>}
            </div>
            {e.tokens_month ? (
              <span className="relative h-1.5 overflow-hidden rounded-full bg-page" dir="ltr" title={`تعهد ماهانه‌ی کارمندها ${tokens(e.committed_month)}`}>
                <span className="absolute inset-y-0 left-0 rounded-full bg-gold-soft" style={{ width: `${committedPct}%` }} />
                <span className={cx('absolute inset-y-0 left-0 rounded-full', usedPct >= 90 ? 'bg-neg' : usedPct >= 70 ? 'bg-warn' : 'bg-pos')} style={{ width: `${usedPct}%` }} />
              </span>
            ) : null}
            {e.tokens_month ? <span className="text-[11px] text-muted">تعهد کارمندها <span className="fig">{tokens(e.committed_month)}</span>، استخدام این ماه {e.hires_month}</span> : null}
          </div>
        );
      })}
    </div>
  );
}

/** The envelopes: each operating company's monthly token budget (contract §9 /budgets, §18.11). With `open`, opening delegated hiring follows. */
function EnvelopeSheet({ h, mode, onClose }: { h: Hiring; mode: null | 'edit' | 'open'; onClose: () => void }) {
  const act = useHiringAction();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const initial = useMemo(() => Object.fromEntries(h.envelopes.map((e) => [e.company, e.tokens_month ? String(e.tokens_month / 1_000_000) : ''])), [h.envelopes]);
  const [vals, setVals] = useState<Record<string, string>>(initial);
  const [busy, setBusy] = useState(false);
  const parsed = h.envelopes.map((e) => ({ company: e.company, m: Number((vals[e.company] ?? '').replace(/[٫,]/g, '.').replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))) }));
  const valid = parsed.every((x) => Number.isFinite(x.m) && x.m > 0);
  const changed = parsed.filter((x) => Number.isFinite(x.m) && x.m > 0 && x.m * 1_000_000 !== (h.envelopes.find((e) => e.company === x.company)?.tokens_month ?? 0));
  const total = parsed.reduce((a, x) => a + (Number.isFinite(x.m) && x.m > 0 ? x.m : 0), 0);

  const submit = async () => {
    setBusy(true);
    try {
      if (changed.length) await act.envelopes.mutateAsync(changed.map((x) => ({ company: x.company, tokens_month: Math.round(x.m * 1_000_000) })));
      if (mode === 'open') {
        await act.start.mutateAsync('delegated');
        toast({ tone: 'ok', text: 'اختیار استخدام با مدیرعامل‌هاست؛ هر استخدام یک استوری میسازد.' });
      } else toast({ tone: 'ok', text: 'پاکت‌ها ثبت شد.' });
      onClose();
    } catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : 'ثبت نشد.' }); }
    finally { setBusy(false); }
  };

  return (
    <Sheet open={mode !== null} onOpenChange={(v) => { if (!v) onClose(); }} title={mode === 'open' ? 'اختیار استخدام با مدیرعامل‌ها' : 'پاکت ماهانه‌ی شرکت‌ها'}
      description="هر شرکت تا سقف پاکت ماهانه‌اش استخدام میکند؛ استخدامی که در پاکت جا نشود پذیرفته نمیشود. پاکت همان بودجه‌ی ماهانه‌ی شرکت در خزانه است." width={520}
      footer={<Button variant="primary" icon="seal" className="w-full" disabled={!valid || (mode === 'edit' && !changed.length)} loading={busy} onClick={submit}>{mode === 'open' ? 'با گذرکلید ثبت کن و باز کن' : 'با گذرکلید ثبت کن'}</Button>}>
      <div className="flex flex-col gap-4">
        {h.envelopes.map((e) => (
          <label key={e.company} className="flex flex-col gap-1.5">
            <span className="flex items-center gap-2 text-[13px] text-sec"><CompanyMark code={e.company} height={13} mono />{companyOf(companies, e.company).nameFa}</span>
            <span className="flex items-center gap-2">
              <input value={vals[e.company] ?? ''} onChange={(ev) => setVals((v) => ({ ...v, [e.company]: ev.target.value }))} inputMode="decimal" dir="ltr" placeholder="—" aria-label={`پاکت ماهانه‌ی ${companyOf(companies, e.company).nameFa} به میلیون توکن`}
                className="fig h-11 w-28 rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink" />
              <span className="fig text-[13px] text-muted">M</span>
              <span className="flex-1 text-end text-[11px] text-muted">تعهد <span className="fig">{tokens(e.committed_month)}</span>، مصرف این ماه <span className="fig">{tokens(e.used_month)}</span></span>
            </span>
          </label>
        ))}
        <p className="rounded-[12px] bg-tile p-3 text-[12px] leading-6 text-sec">جمع پاکت‌ها <span className="fig font-semibold text-ink">{tokens(Math.round(total * 1_000_000))}</span> در ماه. استخدام‌های خود هلدینگ همیشه با مُهر توست.</p>
      </div>
    </Sheet>
  );
}

function Choice({ icon, title, note, onClick, busy, primary }: { icon: IconName; title: string; note: string; onClick: () => void; busy?: boolean; primary?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={busy}
      className={cx('flex items-start gap-3 rounded-[12px] p-3 text-start transition-colors disabled:opacity-60', primary ? 'bg-gold-soft ring-1 ring-[var(--hq-gold-ink)] hover:brightness-105' : 'bg-tile hover:bg-hover')}>
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
  const depts = useDepartments(company);
  const co = companies?.find((c) => c.code === company);
  const fitting = useMemo(() => (co && department ? hireableRoles(roles ?? [], co.kind, department, co.code) : []), [roles, co, department]);
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
            {!fitting.length ? <p className="rounded-[12px] bg-tile px-3 py-3 text-[13px] leading-6 text-muted">برای این دپارتمان هنوز منشور کارمندی نیست. مدیر همین دپارتمان هر نقشی که کار لازم دارد مینویسد؛ از صفحه‌ی شرکت، روی دپارتمان بزن و «نقش تازه بخواه».</p> : (
              <div className="flex flex-col gap-1.5">
                {fitting.map((r) => (
                  <button key={r.role} type="button" aria-pressed={role?.role === r.role} onClick={() => pickRole(r)}
                    className={cx('flex items-center gap-3 rounded-[12px] px-3 py-2.5 text-start transition-colors', role?.role === r.role ? 'bg-gold-soft ring-1 ring-[var(--hq-gold-ink)]' : 'bg-tile hover:bg-hover')}>
                    <span className="text-sec"><Icon name="hire" size={20} /></span>
                    <span className="flex min-w-0 flex-1 flex-col"><span className="flex items-center gap-2 text-[14px] text-ink">{r.title_fa}{r.source === 'draft' ? <span className="rounded-full bg-lapis-soft px-2 py-px text-[10px] font-semibold text-lapis">نوشته‌ی مدیر دپارتمان{r.draft ? <> · <span className="fig">{r.draft}</span></> : null}</span> : null}</span><span className="fig truncate text-[11px] text-muted">{r.title_en}, {modelLabel(r.model)}, {r.effort}</span></span>
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
