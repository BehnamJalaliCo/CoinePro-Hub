'use client';

import Link from 'next/link';
import { useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { useAccounts } from '@/lib/api/v14';
import { faError, useFunnel, useRescueCase, useRescueCases, useRevenueAccounts, useRevenueAction, type RescueCase, type RescueState, type RevenueAccount, type RevenueAccountIn, type RevenueSummary } from '@/lib/api/v16';
import { companyColor } from '@/lib/company';
import { ago, cx, jDateTime } from '@/lib/format';
import { ALERT_FA, CompanyChips, Fact, Prose, RESCUE_STATE, RESCUE_STEP, TerminalCommand, rate } from './bits';

const field = 'h-10 w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
const ACCOUNT_STATE: Record<RevenueAccount['status'], { fa: string; tone: 'pos' | 'neg' | 'neutral' }> = { ok: { fa: 'سالم', tone: 'pos' }, error: { fa: 'خطا', tone: 'neg' }, not_configured: { fa: 'بی‌کلید', tone: 'neutral' } };

// ------------------------------------------------------------------ alerts --
/** One per incident (§19.1): a drop below 60% of the weekday median, two failed pulls in a row, a day still incomplete after 36 h. */
export function AlertsCard({ alerts }: { alerts: RevenueSummary['alerts'] | undefined }) {
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="هشدارها" note="یکی برای هر رخداد؛ به مدیرعامل همان شرکت هم میرسد" />
      {!alerts ? <Skeleton className="h-20" /> : !alerts.length ? <p className="py-3 text-center text-[13px] text-muted">هشداری نیست.</p> : alerts.map((a, i) => (
        <div key={i} className={cx('flex items-start gap-3 rounded-[12px] p-3', a.kind === 'drop' ? 'bg-warn-soft' : 'bg-neg-soft')}>
          <span className={cx('mt-0.5', a.kind === 'drop' ? 'text-warn' : 'text-neg')}><Icon name={ALERT_FA[a.kind]?.icon ?? 'urgent'} size={18} /></span>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="flex items-center gap-2 text-[13px] font-semibold"><CompanyMark code={a.company} height={12} mono />{ALERT_FA[a.kind]?.fa ?? a.kind}</span>
            <p className="text-[13px] leading-6 text-ink"><Prose text={a.note_fa} /></p>
          </div>
        </div>
      ))}
    </Card>
  );
}

// ---------------------------------------------------------------- accounts --
/** The affiliate accounts (§19.1): a mapping to a service account; the key and secret are set in the owner's terminal, never here. */
export function AccountsCard() {
  const q = useRevenueAccounts();
  const act = useRevenueAction();
  const toast = useToast();
  const [edit, setEdit] = useState<RevenueAccount | 'new' | null>(null);
  const keys = useRef(new Map<string, string>());
  const [busy, setBusy] = useState<string | null>(null);
  const pull = async (a: RevenueAccount) => {
    const key = keys.current.get(a.id) ?? crypto.randomUUID();
    keys.current.set(a.id, key);
    setBusy(a.id);
    try {
      await act.pull.mutateAsync({ id: a.id, key });
      keys.current.delete(a.id);
      toast({ tone: 'ok', text: 'pull در صف رفت؛ روز تازه که برسد، رادار به‌روز میشود.' });
    } catch (e) {
      // Only a lost answer is retried with the same key; anything the hub answered starts afresh.
      if (!(e instanceof ApiError && e.status === 0)) keys.current.delete(a.id);
      toast({ tone: 'error', text: faError(e) });
    } finally { setBusy(null); }
  };
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="حساب‌های افیلیت" note="هر روز بعد از تسویه‌ی صرافی، خودکار" action={<Button variant="text" size="sm" icon="add" onClick={() => setEdit('new')}>حساب تازه</Button>} />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton className="h-28" /> : !q.data.length ? <Empty icon="treasury" title="حسابی ثبت نشده" /> : q.data.map((a) => (
        <div key={a.id} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
          <div className="flex items-center gap-2">
            <CompanyMark code={a.company} height={14} mono />
            <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{a.title_fa}</span>
            <Pill tone={ACCOUNT_STATE[a.status]?.tone ?? 'neutral'} dot>{ACCOUNT_STATE[a.status]?.fa ?? a.status}</Pill>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
            <span className="fig">{a.exchange} · {a.adapter}</span>
            <span>{a.last_pull_at ? <>آخرین pull {ago(a.last_pull_at)}</> : 'هنوز pull نشده'}</span>
          </div>
          {a.last_error ? <p dir="ltr" className="fig rounded-[8px] bg-neg-soft px-2.5 py-1.5 text-left text-[11px] leading-5 text-neg">{a.last_error}</p> : null}
          {a.status === 'not_configured' ? <TerminalCommand text={`make account-secret KEY=${a.service_account}`} /> : null}
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" icon="refresh" loading={busy === a.id} disabled={a.status === 'not_configured'} onClick={() => pull(a)}>pull الان</Button>
            <Button size="sm" variant="ghost" icon="edit" onClick={() => setEdit(a)}>تغییر</Button>
          </div>
        </div>
      ))}
      {edit ? <AccountSheet account={edit === 'new' ? null : edit} onClose={() => setEdit(null)} /> : null}
    </Card>
  );
}

function AccountSheet({ account, onClose }: { account: RevenueAccount | null; onClose: () => void }) {
  const act = useRevenueAction();
  const toast = useToast();
  const sa = useAccounts();
  const [v, setV] = useState<RevenueAccountIn>({
    company: account?.company ?? '', exchange: account?.exchange ?? 'lbank', adapter: account?.adapter ?? 'lbank-affiliate-v2',
    service_account: account?.service_account ?? '', title_fa: account?.title_fa ?? '',
  });
  const set = (p: Partial<RevenueAccountIn>) => setV((x) => ({ ...x, ...p }));
  const valid = !!v.company && /^[a-z0-9_-]+$/.test(v.exchange) && /^[a-z0-9_.-]+$/.test(v.adapter) && /^[a-z0-9_.-]+$/.test(v.service_account) && v.title_fa.trim().length >= 2;
  const save = () => act.save.mutateAsync({ ...v, title_fa: v.title_fa.trim() })
    .then(() => { toast({ tone: 'ok', text: account ? 'حساب به‌روز شد.' : 'حساب ثبت شد؛ حالا کلیدش را در ترمینال خودت بگذار.' }); onClose(); })
    .catch((e) => toast({ tone: 'error', text: faError(e) }));
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={account ? 'تغییر حساب افیلیت' : 'حساب افیلیت تازه'} description="یک حساب برای هر صرافی و هر شرکت؛ ثبت با passkey و روی همین متن." width={520}
      footer={<Button variant="primary" icon="seal" className="w-full" disabled={!valid} loading={act.save.isPending} onClick={save}>ثبت با passkey</Button>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">شرکت</span><CompanyChips value={v.company || null} onChange={(c) => set({ company: c ?? '' })} all={false} /></div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5 font-semibold text-sec">صرافی<input value={v.exchange} onChange={(e) => set({ exchange: e.target.value.trim().toLowerCase() })} dir="ltr" className={cx(field, 'fig')} /></label>
          <label className="flex flex-col gap-1.5 font-semibold text-sec">adapter<input value={v.adapter} onChange={(e) => set({ adapter: e.target.value.trim() })} dir="ltr" className={cx(field, 'fig')} /></label>
        </div>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">حساب سرویس (§18.13)
          <input value={v.service_account} onChange={(e) => set({ service_account: e.target.value.trim() })} list="hq-service-accounts" dir="ltr" placeholder="lbank-affiliate-ty" className={cx(field, 'fig')} />
          <datalist id="hq-service-accounts">{(sa.data ?? []).map((a) => <option key={a.key} value={a.key}>{a.title_fa}</option>)}</datalist>
        </label>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">نام<input value={v.title_fa} onChange={(e) => set({ title_fa: e.target.value })} maxLength={120} placeholder="افیلیت LBank تریدیار" className={field} /></label>
        <div className="flex flex-col gap-2 rounded-[12px] bg-tile p-3 leading-6">
          <span className="flex items-center gap-2 font-semibold text-ink"><Icon name="lock" size={16} className="text-gold-ink" />کلید این‌جا پرسیده نمیشود</span>
          <span className="text-sec">کلید و secret صرافی هرگز از API و این صفحه رد نمیشود؛ فقط در egress خوانده میشود. بعد از ثبت، در ترمینال خودت روی سرور:</span>
          <TerminalCommand text={`make account-secret KEY=${v.service_account || '<service-account>'}`} />
          <span className="text-[12px] text-muted">و IP عمومی هاب را در whitelist API افیلیت همان صرافی بگذار؛ بدون آن صرافی جواب نمیدهد.</span>
        </div>
      </div>
    </Sheet>
  );
}

// ------------------------------------------------------------------ funnel --
const WAITING: Record<string, string> = { visit: 'منتظر منبع analytics', signup: 'منتظر رویداد محصول (CR-009/010)', vip_active: 'منتظر رویداد محصول (CR-009/010)' };
const SOURCE_FA: Record<string, string> = { affiliate: 'داده‌ی افیلیت', product_events: 'رویداد محصول', support: 'پشتیبانی', analytics: 'analytics' };

/** The funnel of one company (§19.2). A stage without a source says so and shows no number; a rate is never estimated. */
export function FunnelCard({ initial }: { initial: string | null }) {
  const { data: companies } = useCompanies();
  const first = companies?.find((c) => c.kind !== 'holding')?.code ?? null;
  const [picked, setPicked] = useState<string | null>(null);
  const company = picked ?? initial ?? first;
  const [period, setPeriod] = useState<'week' | 'month'>('month');
  const q = useFunnel(company, period);
  const f = q.data;
  const max = Math.max(1, ...(f?.stages ?? []).map((s) => s.count ?? 0));
  const color = company ? companyColor(companies, company) : 'var(--hq-silver-ink)';
  return (
    <Card className="flex flex-col gap-4 p-5">
      <SectionTitle title="قیف" note="بازدید ← ثبت‌نام ← رفرال تأییدشده ← حداقل موجودی ← VIP فعال" action={<div className="w-40"><Segmented label="دوره‌ی قیف" value={period} onChange={setPeriod} options={[{ value: 'week', label: 'هفته' }, { value: 'month', label: 'ماه' }]} /></div>} />
      <CompanyChips value={company} onChange={(c) => setPicked(c)} all={false} />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !f ? <Skeleton className="h-48" /> : (
        <>
          <ol className="flex flex-col">
            {f.stages.map((s, i) => {
              const conv = i ? f.conversions.find((c) => c.from === f.stages[i - 1]!.key && c.to === s.key) : null;
              return (
                <li key={s.key} className="flex flex-col">
                  {i ? <span className="flex items-center gap-1.5 py-1 ps-3 text-[11px] text-muted"><Icon name="chevron" size={12} />{conv?.rate != null ? <>تبدیل <span className="fig text-sec">{rate(conv.rate)}</span></> : 'تبدیل: —'}</span> : null}
                  <div className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3">
                    <div className="flex items-center gap-2 text-[13px]">
                      <span className="flex-1 font-semibold">{s.label_fa}</span>
                      {s.connected && s.count != null ? <span className="fig text-[15px] font-semibold">{s.count.toLocaleString('en-US')}</span> : <Pill tone="neutral">وصل نیست</Pill>}
                    </div>
                    {s.connected && s.count != null ? (
                      <div className="h-2 rounded-full bg-card"><span className="block h-full rounded-l-[4px] rounded-r-full" style={{ width: `${Math.max(2, (s.count / max) * 100)}%`, background: color }} /></div>
                    ) : null}
                    <span className="text-[11px] text-muted">{s.connected ? `از ${SOURCE_FA[s.source ?? ''] ?? s.source}` : <Prose text={WAITING[s.key] ?? 'منبعی ندارد'} />}</span>
                  </div>
                </li>
              );
            })}
          </ol>
          {f.leaks.map((l) => (
            <div key={l.stage} className="flex items-start gap-3 rounded-[12px] bg-warn-soft p-3 text-[13px] leading-6">
              <span className="mt-0.5 text-warn"><Icon name="urgent" size={18} /></span>
              <div className="flex flex-col gap-0.5">
                <span className="font-semibold">نشتی در «{f.stages.find((s) => s.key === l.stage)?.label_fa ?? l.stage}»: <span className="fig">{rate(l.rate)}</span> در برابر میانه‌ی <span className="fig">{rate(l.median_rate)}</span></span>
                <span className="text-sec"><Prose text={l.note_fa} /></span>
              </div>
            </div>
          ))}
        </>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ rescue --
const STATES: RescueState[] = ['open', 'contacted', 'rescued', 'lost', 'opted_out'];

/** Referral rescue (§19.2): a case opens when a UID check says "not our invitee"; follow-ups run only under a sealed rescue rule. */
export function RescueCard({ company }: { company: string | null }) {
  const [state, setState] = useState<RescueState | null>(null);
  const all = useRescueCases({ company });
  const list = useRescueCases({ company, state });
  const [open, setOpen] = useState<RescueCase | null>(null);
  const every = all.data?.pages.flatMap((p) => p.items) ?? [];
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const rescued = every.filter((r) => r.state === 'rescued').length;
  const lost = every.filter((r) => r.state === 'lost').length;
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="نجات رفرال" note="پیگیری فقط با قالب و قاعده‌ی مُهرشده؛ هیچ ایجنتی متن آزاد نمیفرستد"
        action={rescued + lost ? <span className="text-[12px] text-sec">نرخ نجات <span className="fig font-semibold text-ink">{rate(rescued / (rescued + lost))}</span></span> : null} />
      <div className="flex flex-wrap gap-2">
        <FilterChip selected={!state} onClick={() => setState(null)} count={every.length}>همه</FilterChip>
        {STATES.map((s) => <FilterChip key={s} selected={state === s} onClick={() => setState(s)} count={every.filter((r) => r.state === s).length}>{RESCUE_STATE[s]!.fa}</FilterChip>)}
      </div>
      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : list.isLoading ? <Skeleton className="h-32" /> : !items.length ? <p className="py-4 text-center text-[13px] text-muted">پرونده‌ای نیست.</p> : (
        <ul className="flex flex-col">
          {items.map((r) => (
            <li key={r.ref} className="border-b border-div last:border-0">
              <button type="button" onClick={() => setOpen(r)} className="flex w-full items-center gap-3 rounded-[8px] px-1 py-2.5 text-start hover:bg-hover">
                <CompanyMark code={r.company} height={13} mono />
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate text-[13px] text-ink">{r.steps.at(-1)?.result_fa ?? '—'}</span>
                  <span className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted"><span className="fig">{r.ref}</span><span>{r.source === 'support' ? 'از پشتیبانی' : 'از محصول'}</span><span>{ago(r.opened_at)}</span></span>
                </span>
                <Pill tone={RESCUE_STATE[r.state]?.tone ?? 'neutral'} dot>{RESCUE_STATE[r.state]?.fa ?? r.state}</Pill>
              </button>
            </li>
          ))}
        </ul>
      )}
      {list.hasNextPage ? <Button variant="secondary" size="sm" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>بیشتر</Button> : null}
      <p className="text-[11px] text-muted">نرخ نجات = نجات‌یافته ÷ (نجات‌یافته + از دست رفته)، روی پرونده‌های همین فهرست.</p>
      {open ? <RescueSheet seed={open} onClose={() => setOpen(null)} /> : null}
    </Card>
  );
}

function RescueSheet({ seed, onClose }: { seed: RescueCase; onClose: () => void }) {
  const q = useRescueCase(seed.ref);
  const r = q.data ?? seed;
  const { data: companies } = useCompanies();
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={<span className="flex items-center gap-2"><span className="fig text-[13px] text-muted">{r.ref}</span>پرونده‌ی نجات</span>} width={520}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2"><Pill tone={RESCUE_STATE[r.state]?.tone ?? 'neutral'} dot>{RESCUE_STATE[r.state]?.fa ?? r.state}</Pill><span className="flex items-center gap-1.5 text-[12px] text-sec"><CompanyMark code={r.company} height={12} mono />{companies?.find((c) => c.code === r.company)?.name_fa ?? r.company}</span></div>
        <div className="grid grid-cols-2 gap-2">
          <Fact label="صرافی" mono>{r.exchange}</Fact>
          <Fact label="منبع">{r.source === 'support' ? 'گفت‌وگوی پشتیبانی' : 'رویداد محصول'}</Fact>
          <Fact label="مشتری (نام مستعار)" mono>{r.subject}</Fact>
          <Fact label="باز شد">{jDateTime(r.opened_at)}</Fact>
        </div>
        {r.conversation ? <Link href={`/support/${r.conversation}`} className="flex items-center gap-2 rounded-[12px] bg-tile p-3 text-[13px] hover:bg-hover"><Icon name="messages" size={16} className="text-gold-ink" /><span className="flex-1">گفت‌وگوی <span className="fig">{r.conversation}</span></span><Icon name="next" size={14} mirror className="text-muted" /></Link> : null}
        <div className="flex flex-col gap-1.5">
          <span className="text-[12px] font-semibold text-sec">گام‌ها</span>
          <ol className="flex flex-col gap-2 border-s border-div ps-4">
            {r.steps.map((s, i) => (
              <li key={i} className="flex flex-col gap-0.5 text-[13px]">
                <span className="flex flex-wrap items-center gap-2 text-[11px] text-muted"><span className="font-semibold text-sec">{RESCUE_STEP[s.kind] ?? s.kind}</span><span>{jDateTime(s.at)}</span>{s.template ? <span className="fig">{s.template}</span> : null}</span>
                <span className="leading-6 text-ink">{s.result_fa}</span>
              </li>
            ))}
          </ol>
        </div>
        {r.rescued_at ? <p className="text-[12px] text-pos">نجات یافت، {jDateTime(r.rescued_at)}</p> : r.closed_at ? <p className="text-[12px] text-muted">بسته شد، {jDateTime(r.closed_at)}</p> : null}
        <p className="text-[11px] text-muted">در این‌جا فقط نام مستعار مشتری است؛ UID و نام کاربری خام هرگز از شرکتش بیرون نمیاید.</p>
      </div>
    </Sheet>
  );
}
