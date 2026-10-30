'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark, Monogram } from '@/components/brand/marks';
import { Button, IconButton } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Bar, Card, FilterChip, Pill, SectionTitle, Skeleton, budgetTone } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { NewOrder } from '@/components/work/new-order';
import type { IconName } from '@/generated/icons';
import { ApiError, type Schemas } from '@/lib/api/client';
import { useBreakdown, useControl, useDecisions } from '@/lib/api/hooks';
import { useHiring } from '@/lib/api/v14';
import { useBudgets, useRuns, useSites, useIncidents } from '@/lib/api/v15';
import { freezeDeploys, liftFreezes, putMonthBudget, useControlHistory, useOutputs, type ControlEvent } from '@/lib/api/v21';
import { stepUp } from '@/lib/auth';
import { byFa, coState, pctOf, runsOf, stirred, type CoState } from '@/lib/control';
import { usePulses } from '@/lib/pulses';
import { ago, cx, jDateTime, jTime, tokens, until, usd } from '@/lib/format';
import { Consequences, inputCls, ownerDay } from './bits';
import { DeleteCompany } from './delete-company';
import { FeedLine, feedRowOf, type FeedRow } from './feed';

// The control layer (0.3.0; contract §9, OPERATING_MODEL §1.12; the Android app's ui/companies/Control.kt): each company at a glance in the
// companies list and on «کنترل» (its state chip, why it is stopped or what its agents are doing, four figures, the two switches), every
// action on it, and the company page's control room (state and switches, who changed them and why, the month's budget, live activity,
// hiring, its sites, removal). Stopping is instant and needs no passkey (speed matters); resuming and opening deploys take the passkey; a
// switch the owner engaged is released only by the owner. Every action shows its result at once and rolls back if the hub refuses.

type Company = Schemas['Company'];
type ControlState = Schemas['ControlState'];
export type CoTarget = { code: string; nameFa: string; holding: boolean };
type SheetKind = 'actions' | 'stop' | 'resume' | 'freeze' | 'unfreeze' | 'order' | 'delete';

// ================================================================================================== live data ==
/** What the companies list and the control room read: the switches, what runs now, today's spend per company, the stream's pulses. */
export function useControlData() {
  const control = useControl();
  const running = useRuns({ state: 'running', limit: 100 });
  const today = ownerDay(new Date());
  const spend = useBreakdown({ by: 'company', from: today, to: today });
  const pulses = usePulses();
  const runs = running.data?.items ?? [];
  return {
    control: control.data, pulses, spendLoaded: !!spend.data,
    state: (code: string, holding: boolean, company?: Company | null): CoState => coState(code, holding, control.data, company),
    runs: (code: string) => runsOf(code, pulses, runs),
    busy: (code: string) => runsOf(code, pulses, runs) > 0 || (pulses[code]?.working.length ?? 0) > 0,
    stirred: (code: string) => stirred(pulses[code]),
    spendOf: (code: string | null) => (spend.data ?? []).filter((r) => code == null || r.key === code).reduce((a, r) => a + Number(r.equiv_cost_usd || 0) + Number(r.cost_usd || 0), 0),
  };
}
export type ControlData = ReturnType<typeof useControlData>;

// ======================================================================================================= actions ==
/** The owner's control actions as the pages run them: optimistic, rolled back with a Persian error when the hub refuses. */
export function useControlUi() {
  const qc = useQueryClient();
  const toast = useToast();
  const [sheet, setSheet] = useState<{ kind: SheetKind; t: CoTarget } | null>(null);
  const [busy, setBusy] = useState(false);

  /** Patches the cached control state and company rows, runs [call], and puts everything back if it fails. */
  async function act(patch: (c: ControlState) => ControlState, row: (c: Company) => Company, code: string, call: () => Promise<unknown>, ok: () => void) {
    if (busy) return;
    setBusy(true);
    setSheet(null);
    const before = { control: qc.getQueryData<ControlState>(['control']), companies: qc.getQueryData<Company[]>(['companies']), one: qc.getQueryData<Company>(['companies', code]) };
    if (before.control) qc.setQueryData(['control'], patch(before.control));
    if (before.companies) qc.setQueryData(['companies'], before.companies.map((c) => (c.code === code ? row(c) : c)));
    if (before.one) qc.setQueryData(['companies', code], row(before.one));
    try {
      await call();
      ok();
    } catch (e) {
      qc.setQueryData(['control'], before.control);
      qc.setQueryData(['companies'], before.companies);
      qc.setQueryData(['companies', code], before.one);
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' });
    } finally {
      setBusy(false);
      for (const k of ['control', 'companies']) void qc.invalidateQueries({ queryKey: [k] });
    }
  }
  const sw = (t: CoTarget, engaged: boolean, reason: string) => (c: ControlState): ControlState => {
    const k = { scope: t.holding ? 'holding' : `company:${t.code}`, company: t.code, state: engaged ? 'engaged' : 'released', reason, changed_at: new Date().toISOString(), changed_by: 'owner' };
    return t.holding ? { ...c, holding: k } : { ...c, companies: c.companies.some((x) => x.company === t.code) ? c.companies.map((x) => (x.company === t.code ? k : x)) : [...c.companies, k] };
  };
  const fz = (t: CoTarget, until: string | null, reason: string) => (c: ControlState): ControlState => ({
    ...c, deploy_freezes: [...c.deploy_freezes.filter((f) => f.company !== t.code), ...(until ? [{ company: t.code, until, reason, created_by: 'owner' }] : [])],
  });
  const scope = (t: CoTarget) => (t.holding ? 'holding' : `company:${t.code}`);
  const post = (body: unknown, token?: string) => fetchJson('/control/kill-switch', body, token);

  return {
    sheet, busy, open: (kind: SheetKind, t: CoTarget) => setSheet({ kind, t }), close: () => setSheet(null),
    stop: (t: CoTarget, reason: string) => act(sw(t, true, reason), (c) => ({ ...c, kill_switch: 'engaged' }), t.code, () => post({ scope: scope(t), state: 'engaged', reason }),
      () => toast({ tone: 'info', text: t.holding ? 'همه‌چیز متوقف شد؛ فقط کارهای اضطراری (P0) اجرا میشوند.' : `${t.nameFa} متوقف شد؛ هیچ چیز از دست نرفت.` })),
    resume: async (t: CoTarget, reason: string) => {
      // The passkey comes before anything changes on screen: a cancelled passkey changes nothing.
      let token: string;
      try { token = await stepUp('kill_switch.release', scope(t)); } catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'تأیید انجام نشد.' }); return; }
      await act(sw(t, false, reason), (c) => ({ ...c, kill_switch: 'released' }), t.code, () => post({ scope: scope(t), state: 'released', reason }, token),
        () => toast({ tone: 'ok', text: t.holding ? 'هلدینگ دوباره کار میکند.' : `${t.nameFa} دوباره کار میکند.` }));
    },
    freeze: (t: CoTarget, hours: number, reason: string) => {
      const u = new Date(Date.now() + hours * 3_600_000).toISOString();
      return act(fz(t, u, reason), (c) => ({ ...c, deploy_freeze_until: u }), t.code, () => freezeDeploys(t.code, hours, reason), () => toast({ tone: 'info', text: `deploy ${t.nameFa} بسته شد؛ کارهای دیگر ادامه دارند.` }));
    },
    unfreeze: (t: CoTarget, reason: string) =>
      act(fz(t, null, reason), (c) => ({ ...c, deploy_freeze_until: null }), t.code, () => liftFreezes(t.code, reason), () => toast({ tone: 'ok', text: `deploy ${t.nameFa} باز شد.` })),
    budget: async (t: CoTarget, tokenLimit: number | null, usdLimit: string | null) => {
      setBusy(true);
      try {
        const out = await putMonthBudget(t.code, t.holding, tokenLimit, usdLimit);
        qc.setQueryData(['treasury', 'budgets'], out);
        for (const k of ['treasury', 'hiring']) void qc.invalidateQueries({ queryKey: [k] });
        toast({ tone: 'ok', text: `بودجه‌ی ماه ${t.nameFa} ذخیره شد.` });
        return true;
      } catch (e) {
        toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ذخیره نشد.' });
        return false;
      } finally { setBusy(false); }
    },
  };
}
export type ControlUi = ReturnType<typeof useControlUi>;

async function fetchJson(path: string, body: unknown, token?: string) {
  const { call } = await import('@/lib/api/v13');
  return call<ControlState>('POST', path, body, token ? { 'X-Step-Up': token } : undefined);
}

// ========================================================================================================= chips ==
/** The state at a glance: a coloured chip with its icon and its word (colour never alone). */
export function StateChip({ s, busy }: { s: CoState; busy: boolean }) {
  if (s.stopped) return <Pill tone="neg" icon="pause">متوقف</Pill>;
  if (s.holdingStopped) return <Pill tone="neg" icon="pause">متوقف با هلدینگ</Pill>;
  if (s.frozen) return <Pill tone="warn" icon="lock">deploy بسته</Pill>;
  if (busy) return <Pill tone="pos" live>در حال کار</Pill>;
  return <Pill tone="pos" dot>فعال</Pill>;
}

const lampOf = (s: CoState) => (!s.running ? 'var(--hq-negative)' : s.frozen ? 'var(--hq-warning)' : 'var(--hq-positive)');

/** The company's mark in a ring that says what its agents are doing: a gold comet orbits while they work, the ring breathes once when
 *  something has just happened, it is still when they are idle, and red and dim when the company is stopped. */
export function ActivityRing({ code, holding, stopped, busy, stir, size = 56 }: { code: string; holding: boolean; stopped: boolean; busy: boolean; stir: boolean; size?: number }) {
  const ring = stopped ? 'var(--hq-negative)' : busy ? 'var(--hq-gold-fill)' : 'var(--hq-line-strong)';
  return (
    <span className="relative flex flex-none items-center justify-center rounded-full" style={{ width: size, height: size }} role="img" aria-label={stopped ? 'متوقف' : busy ? 'ایجنت‌ها در حال کارند' : 'آرام'}>
      <span className="absolute inset-0 rounded-full border-[1.5px] transition-colors duration-300" style={{ borderColor: ring, animation: (busy || stir) && !stopped ? 'hq-breath 2.4s ease-in-out infinite' : undefined, background: busy && !stopped ? 'color-mix(in srgb, var(--hq-gold-fill) 12%, transparent)' : undefined }} />
      {busy && !stopped ? (
        <span aria-hidden className="absolute inset-0 rounded-full" style={{
          background: 'conic-gradient(from 0deg, transparent 0 69%, var(--hq-gold-fill) 100%)',
          mask: 'radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 2.5px))',
          WebkitMask: 'radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 2.5px))',
          animation: 'hq-spin 2.2s linear infinite',
        }} />
      ) : null}
      <span className={cx('relative flex items-center justify-center rounded-full bg-tile text-ink transition-opacity', stopped && 'opacity-55')} style={{ width: size - 10, height: size - 10 }}>
        {holding ? <Monogram size={Math.round(size * 0.42)} /> : <CompanyMark code={code} height={Math.round(size * 0.34)} />}
      </span>
    </span>
  );
}

// ========================================================================================================= cards ==
/** The line under a company's name: why it is stopped, until when its deploys are closed, or what its agents are doing. */
function StateLine({ s, d, holdingName }: { s: CoState; d: ControlData; holdingName?: string | null }) {
  const runs = d.runs(s.code);
  const working = d.pulses[s.code]?.working.length ?? 0;
  const [dot, text] = s.stopped ? ['bg-neg', `متوقف از ${ago(s.sw?.changed_at)}، ${byFa(s.sw?.changed_by)}`]
    : s.holdingStopped ? ['bg-neg', `کلید ${holdingName ?? 'هلدینگ'} همه را نگه داشته است`]
    : d.busy(s.code) ? ['bg-pos', runs > 0 ? `${runs} اجرا در جریان` : `${working} نفر سر کار`]
    : d.stirred(s.code) ? ['bg-silver-ink', 'همین الان خبری رسید']
    : ['bg-muted', 'آرام؛ ایجنت‌ها تا رسیدن کار خواب‌اند'];
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="flex items-center gap-1.5 text-[12px] text-sec">
        <span className={cx('size-1.5 flex-none rounded-full', dot)} style={s.running && d.busy(s.code) ? { animation: 'hq-live 1.4s infinite' } : undefined} />
        <span className="truncate">{text}</span>
      </span>
      {s.freeze ? <span className="flex items-center gap-1.5 text-[12px] text-sec"><span className="text-warn"><Icon name="lock" size={12} /></span><span className="truncate">deploy بسته تا {jTime(s.freeze.until)}، {until(s.freeze.until)}</span></span> : null}
    </div>
  );
}

/** Four figures of a company: today's spend (Latin), open work, cards waiting on the owner and active staff (counts, Persian). */
function Figures({ spend, work, pending, staff }: { spend: number | null; work: number; pending: number; staff: number }) {
  const cell = (label: string, value: ReactNode, gold = false) => (
    <div className="flex min-w-0 flex-col items-center gap-0.5 px-1.5 py-2 [&:not(:first-child)]:border-s [&:not(:first-child)]:border-div">
      <span className={cx('text-[17px] font-semibold leading-6', gold ? 'text-gold-ink' : 'text-ink')}>{value}</span>
      <span className="truncate text-[11px] text-muted">{label}</span>
    </div>
  );
  return (
    <div className="grid grid-cols-4 rounded-[12px] bg-tile">
      {cell('مصرف امروز', spend == null ? '—' : <span className="fig text-[15px]">{usd(spend)}</span>)}
      {cell('کار باز', work)}
      {cell('منتظر مُهر', pending, pending > 0)}
      {cell('کارمند فعال', staff)}
    </div>
  );
}

/** Stop or resume, close or open deploys, and ⋯ for the rest. */
function Switches({ s, t, ui }: { s: CoState; t: CoTarget; ui: ControlUi }) {
  return (
    <div className="flex items-center gap-2">
      {s.stopped
        ? <Button size="sm" className="flex-1" icon="resume" aria-label="ادامه با اثر انگشت" onClick={() => ui.open('resume', t)}>ادامه</Button>
        : <Button size="sm" variant="danger" className="flex-1" icon="pause" onClick={() => ui.open('stop', t)}>{t.holding ? 'توقف همه‌چیز' : 'توقف'}</Button>}
      {!t.holding ? (s.frozen
        ? <Button size="sm" className="flex-1" icon="resume" onClick={() => ui.open('unfreeze', t)}>باز کردن deploy</Button>
        : <Button size="sm" className="flex-1" icon="lock" onClick={() => ui.open('freeze', t)}>بستن deploy</Button>) : null}
      <IconButton icon="more" label={`کارهای ${t.nameFa}`} size={34} onClick={() => ui.open('actions', t)} />
    </div>
  );
}

/** One company in the list: its mark in the activity ring, its state chip, the line that says why or what, four figures, the switches. */
export function CompanyControlCard({ co, d, ui, holdingName }: { co: Company; d: ControlData; ui: ControlUi; holdingName?: string | null }) {
  const router = useRouter();
  const s = d.state(co.code, false, co);
  const t: CoTarget = { code: co.code, nameFa: co.name_fa ?? co.code, holding: false };
  return (
    <Card className="hq-rise relative flex flex-col gap-3 overflow-hidden p-4 transition-colors hover:bg-[color-mix(in_srgb,var(--hq-surface-card)_88%,var(--hq-surface-hover))]"
      onContextMenu={(e) => { e.preventDefault(); ui.open('actions', t); }}>
      {/* A thin bar of the state's colour on the card's start edge, so a long list reads at a glance. */}
      <span aria-hidden className="absolute inset-y-5 start-0 w-[3px] rounded-full transition-colors duration-300" style={{ background: lampOf(s) }} />
      <button type="button" onClick={() => router.push(`/companies/${co.code}`)} className="flex items-center gap-3 text-start" aria-label={`باز کردن ${t.nameFa}`}>
        <ActivityRing code={co.code} holding={false} stopped={!s.running} busy={d.busy(co.code)} stir={d.stirred(co.code)} />
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-[15px] font-semibold">{t.nameFa}</span>
            <span className="fig text-[11px] text-muted">{co.code}</span>
            <span className="flex-1" />
            <StateChip s={s} busy={d.busy(co.code)} />
          </span>
          <StateLine s={s} d={d} holdingName={holdingName} />
        </span>
      </button>
      <Figures spend={d.spendLoaded ? d.spendOf(co.code) : null} work={co.counts.work_open} pending={co.counts.decisions_pending} staff={co.counts.employees_active} />
      <Switches s={s} t={t} ui={ui} />
    </Card>
  );
}

/** The holding at the top of the list: the same at a glance (totals across the holding) and its own kill switch, the one that stops
 *  everything. When it is engaged the card says so plainly and offers only the way back. */
export function HoldingControlCard({ holding, all, d, ui }: { holding: Company; all: Company[]; d: ControlData; ui: ControlUi }) {
  const router = useRouter();
  const s = d.state(holding.code, true, holding);
  const t: CoTarget = { code: holding.code, nameFa: holding.name_fa ?? 'هلدینگ', holding: true };
  const busy = all.some((c) => d.busy(c.code));
  const stir = all.some((c) => d.stirred(c.code));
  const runs = all.reduce((a, c) => a + d.runs(c.code), 0);
  const stopped = all.filter((c) => c.kind !== 'holding' && d.state(c.code, false, c).stopped).length;
  const line = s.stopped ? `همه متوقف‌اند از ${ago(s.sw?.changed_at)}؛ فقط کار اضطراری`
    : runs > 0 ? `${runs} اجرا در جریان در کل هلدینگ${stopped ? `، ${stopped} شرکت متوقف` : ''}`
    : stopped ? `${stopped} شرکت متوقف؛ بقیه آرام` : 'همه‌ی شرکت‌ها روشن و آرام';
  return (
    <Card className={cx('hq-rise flex flex-col gap-3 p-4 transition-colors duration-300', s.stopped ? 'bg-neg-soft' : 'tahrir')} onContextMenu={(e) => { e.preventDefault(); ui.open('actions', t); }}>
      <button type="button" onClick={() => router.push(`/companies/${holding.code}`)} className="flex items-center gap-3 text-start" aria-label="باز کردن هلدینگ">
        <ActivityRing code={holding.code} holding stopped={s.stopped} busy={busy} stir={stir} size={60} />
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex items-center gap-2"><span className="flex-1 truncate text-h3 font-semibold">{t.nameFa}</span><StateChip s={s} busy={busy} /></span>
          <span className="flex items-center gap-1.5 text-[12px] text-sec">
            <span className={cx('size-1.5 rounded-full', s.stopped ? 'bg-neg' : busy ? 'bg-pos' : 'bg-muted')} style={!s.stopped && busy ? { animation: 'hq-live 1.4s infinite' } : undefined} />{line}
          </span>
        </span>
      </button>
      <Figures spend={d.spendLoaded ? d.spendOf(null) : null} work={all.reduce((a, c) => a + c.counts.work_open, 0)} pending={all.reduce((a, c) => a + c.counts.decisions_pending, 0)} staff={all.reduce((a, c) => a + c.counts.employees_active, 0)} />
      {s.stopped ? (
        <>
          {s.sw?.reason ? <span className="text-[12px] text-sec">«{s.sw.reason}»</span> : null}
          <Button variant="primary" icon="resume" onClick={() => ui.open('resume', t)}>ادامه‌ی همه با اثر انگشت</Button>
        </>
      ) : (
        <div className="flex items-center gap-2">
          <Button variant="danger" icon="pause" className="flex-1" onClick={() => ui.open('stop', t)}>کلید توقف کل هلدینگ</Button>
          <IconButton icon="more" label="کارهای هلدینگ" onClick={() => ui.open('actions', t)} />
        </div>
      )}
    </Card>
  );
}

// ======================================================================================================== sheets ==
const stateFa = (s: CoState) => (s.stopped ? `متوقف از ${ago(s.sw?.changed_at)}، ${byFa(s.sw?.changed_by)}` : s.holdingStopped ? 'با کلید کل هلدینگ متوقف است' : s.frozen ? `روشن؛ deploy بسته، ${until(s.freeze?.until)}` : 'روشن؛ همه‌چیز عادی است');

function ActionRow({ icon, title, note, tint, onClick, href }: { icon: IconName; title: string; note: string; tint: string; onClick?: () => void; href?: string }) {
  const body = (
    <>
      <span className={cx('flex size-10 flex-none items-center justify-center rounded-[12px] bg-tile', tint)}><Icon name={icon} size={20} /></span>
      <span className="flex min-w-0 flex-1 flex-col"><span className="text-[14px] font-semibold text-ink">{title}</span><span className="truncate text-[12px] text-muted">{note}</span></span>
      <span className="text-muted"><Icon name="next" size={16} mirror /></span>
    </>
  );
  const cls = 'flex w-full items-center gap-3 rounded-[12px] px-2 py-2.5 text-start transition-colors hover:bg-hover';
  return href ? <Link href={href} className={cls} onClick={onClick}>{body}</Link> : <button type="button" className={cls} onClick={onClick}>{body}</button>;
}

const STOP_REASONS = ['رفتار غیرعادی', 'مصرف بالا', 'بررسی امنیتی', 'خطا در تولید'];
const SPANS: Array<[number, string]> = [[1, 'یک ساعت'], [4, 'چهار ساعت'], [24, 'یک روز'], [72, 'سه روز']];

/** Hosts whichever control sheet is open (the companies list, «کنترل», the company page). */
export function ControlSheets({ ui, companies }: { ui: ControlUi; companies?: Company[] }) {
  const control = useControl();
  const [reason, setReason] = useState('');
  const [span, setSpan] = useState(4);
  const sh = ui.sheet;
  const t = sh?.t;
  const st = t ? coState(t.code, t.holding, control.data) : null;
  const close = () => { ui.close(); setReason(''); };
  const field = <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} placeholder="دلیل (یک خط)" className={inputCls} />;
  const note = <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} placeholder="یادداشت (اختیاری)" className={inputCls} />;
  const holdingCo = companies?.find((c) => c.kind === 'holding');
  return (
    <>
      <Sheet open={sh?.kind === 'actions'} onOpenChange={(v) => !v && close()} title={t?.nameFa ?? ''} description={st ? stateFa(st) : undefined} width={420}>
        {t && st ? (
          <div className="flex flex-col gap-0.5">
            {st.stopped ? <ActionRow icon="resume" title="ادامه‌ی کار" note="با اثر انگشت یا چهره" tint="text-pos" onClick={() => ui.open('resume', t)} />
              : <ActionRow icon="pause" title={t.holding ? 'توقف همه‌چیز' : 'توقف فوری'} note="بی‌اثر انگشت؛ هیچ چیز از دست نمیرود" tint="text-neg" onClick={() => ui.open('stop', t)} />}
            {!t.holding ? (st.frozen ? <ActionRow icon="resume" title="باز کردن deploy" note="با اثر انگشت یا چهره" tint="text-warn" onClick={() => ui.open('unfreeze', t)} />
              : <ActionRow icon="lock" title="بستن deploy" note="تا زمانی که تعیین میکنی؛ بقیه‌ی کارها ادامه دارند" tint="text-warn" onClick={() => ui.open('freeze', t)} />) : null}
            <ActionRow icon="cartable" title={`کارتابل ${t.holding ? 'هلدینگ' : 'این شرکت'}`} note={`فقط کارت‌های ${t.nameFa}`} tint="text-gold-ink" href={`/cartable?company=${t.code}`} onClick={close} />
            <ActionRow icon="command" title={t.holding ? 'فرمان به هلدینگ' : 'فرمان به مدیرعامل'} note="کار تازه؛ مدیرعامل آن را به دپارتمان درست میسپارد" tint="text-gold-ink" onClick={() => ui.open('order', t)} />
            {!t.holding ? <ActionRow icon="messages" title="پیام به مدیرعامل" note={`گفت‌وگوی ${t.code}-CEO`} tint="text-sec" href={`/messages?thread=${t.code}-CEO`} onClick={close} /> : null}
            <ActionRow icon="settings" title="اتاق کنترل" note="وضعیت و تاریخچه، بودجه، استخدام، فعالیت زنده" tint="text-sec" href={`/companies/${t.code}`} onClick={close} />
            {!t.holding ? <ActionRow icon="dismiss" title="حذف شرکت" note="برای شرکتی که اشتباهی ساخته شده؛ با کد و گذرکلید" tint="text-neg" onClick={() => ui.open('delete', t)} /> : null}
          </div>
        ) : null}
      </Sheet>

      <Sheet open={sh?.kind === 'stop'} onOpenChange={(v) => !v && close()} title={t?.holding ? 'توقف کل هلدینگ' : `توقف ${t?.nameFa ?? ''}`} width={460}>
        {t ? (
          <div className="flex flex-col gap-4">
            <p className="text-[14px] leading-7 text-ink">همه‌ی ایجنت‌های {t.holding ? 'همه‌ی شرکت‌ها' : t.nameFa} همین حالا متوقف میشوند. هیچ چیز از دست نمیرود و هر وقت بخواهی ادامه میدهی.</p>
            <Consequences tone="neg" lines={[
              ['pause', 'هیچ ایجنتی اقدام نوشتنی نمیکند؛ اجراهای در جریان همان‌جا میایستند.'],
              ['urgent', <>فقط کارهای اضطراری (<span key="p" className="fig">P0</span>) اجرا میشوند.</>],
              ['memory', 'کارها، پیام‌ها و کارت‌ها سر جایشان میمانند؛ چیزی پاک نمیشود.'],
              ['lock', 'ادامه دادن با اثر انگشت یا چهره است.'],
            ]} />
            <Button variant="danger" size="lg" icon="pause" disabled={ui.busy} onClick={() => { void ui.stop(t, 'توقف فوری به دستور مدیر کل'); setReason(''); }}>فوری، بدون دلیل</Button>
            <span className="text-[12px] text-muted">یا با دلیلی کوتاه برای دفتر Audit:</span>
            <div className="flex flex-wrap gap-2">{STOP_REASONS.map((r) => <FilterChip key={r} selected={reason === r} onClick={() => setReason(reason === r ? '' : r)}>{r}</FilterChip>)}</div>
            {field}
            <div className="flex gap-2">
              <Button variant="danger" icon="pause" className="flex-1" disabled={!reason.trim() || ui.busy} loading={ui.busy} onClick={() => { void ui.stop(t, reason.trim()); setReason(''); }}>متوقف کن</Button>
              <Button variant="ghost" className="flex-1" onClick={close}>انصراف</Button>
            </div>
          </div>
        ) : null}
      </Sheet>

      <Sheet open={sh?.kind === 'resume'} onOpenChange={(v) => !v && close()} title={t?.holding ? 'ادامه‌ی کار هلدینگ' : `ادامه‌ی کار ${t?.nameFa ?? ''}`} width={460}>
        {t && st ? (
          <div className="flex flex-col gap-4">
            {st.sw ? (
              <div className="flex flex-col gap-0.5 rounded-[12px] bg-neg-soft p-3">
                <span className="text-[13px] font-semibold text-ink">متوقف از {ago(st.sw.changed_at)}، {byFa(st.sw.changed_by)}</span>
                {st.sw.reason ? <span className="text-[13px] text-sec">«{st.sw.reason}»</span> : null}
              </div>
            ) : null}
            <Consequences tone="pos" lines={[
              ['resume', t.holding ? 'همه‌ی شرکت‌ها از همان‌جا که ایستاده بودند ادامه میدهند؛ کلید هر شرکت سر جای خودش میماند.' : `ایجنت‌های ${t.nameFa} از همان‌جا که ایستاده بودند ادامه میدهند.`],
              ['seal', 'با اثر انگشت یا چهره تأیید میشود و در دفتر Audit میماند.'],
            ]} />
            {note}
            <div className="flex gap-2">
              <Button variant="primary" icon="resume" className="flex-1" loading={ui.busy} onClick={() => { void ui.resume(t, reason.trim() || 'ادامه به دستور مدیر کل'); setReason(''); }}>ادامه با اثر انگشت</Button>
              <Button variant="ghost" className="flex-1" onClick={close}>انصراف</Button>
            </div>
          </div>
        ) : null}
      </Sheet>

      <Sheet open={sh?.kind === 'freeze'} onOpenChange={(v) => !v && close()} title={`بستن deploy ${t?.nameFa ?? ''}`} width={460}>
        {t ? (
          <div className="flex flex-col gap-4">
            <p className="text-[14px] leading-7 text-ink">تا پایان این مدت هیچ deployی در {t.nameFa} انجام نمیشود؛ کارهای دیگر ادامه دارند.</p>
            <div className="flex flex-wrap gap-2">{SPANS.map(([h, l]) => <FilterChip key={h} selected={span === h} onClick={() => setSpan(h)}>{l}</FilterChip>)}</div>
            <Consequences tone="warn" lines={[['lock', 'هیچ انتشاری بیرون نمیرود؛ کارت‌های deploy منتظر میمانند.'], ['resume', 'زودتر باز کردن با اثر انگشت یا چهره است.']]} />
            {field}
            <div className="flex gap-2">
              <Button variant="primary" icon="lock" className="flex-1" loading={ui.busy} onClick={() => { void ui.freeze(t, span, reason.trim() || 'توقف deploy به دستور مدیر کل'); setReason(''); }}>ببند</Button>
              <Button variant="ghost" className="flex-1" onClick={close}>انصراف</Button>
            </div>
          </div>
        ) : null}
      </Sheet>

      <Sheet open={sh?.kind === 'unfreeze'} onOpenChange={(v) => !v && close()} title={`باز کردن deploy ${t?.nameFa ?? ''}`} width={460}>
        {t && st ? (
          <div className="flex flex-col gap-4">
            {st.freeze ? (
              <div className="flex flex-col gap-0.5 rounded-[12px] bg-warn-soft p-3">
                <span className="text-[13px] font-semibold text-ink">بسته تا {jTime(st.freeze.until)}، {until(st.freeze.until)}، {byFa(st.freeze.created_by)}</span>
                {st.freeze.reason ? <span className="text-[13px] text-sec">«{st.freeze.reason}»</span> : null}
              </div>
            ) : null}
            <Consequences tone="warn" lines={[['resume', `همه‌ی توقف‌های deploy ${t.nameFa} برداشته میشود، حتی آن‌هایی که خط انتشار یا مدیرعامل گذاشته‌اند.`], ['seal', 'با اثر انگشت یا چهره تأیید میشود.']]} />
            {note}
            <div className="flex gap-2">
              <Button variant="primary" icon="resume" className="flex-1" loading={ui.busy} onClick={() => { void ui.unfreeze(t, reason.trim() || 'deploy به دستور مدیر کل باز شد'); setReason(''); }}>باز کن با اثر انگشت</Button>
              <Button variant="ghost" className="flex-1" onClick={close}>انصراف</Button>
            </div>
          </div>
        ) : null}
      </Sheet>

      {sh?.kind === 'order' ? <NewOrder open onOpenChange={(v) => !v && close()} company={t?.holding ? holdingCo?.code ?? t.code : t?.code} /> : null}
      {sh?.kind === 'delete' && t ? <DeleteCompany t={t} company={companies?.find((c) => c.code === t.code) ?? null} onClose={close} /> : null}
    </>
  );
}

// ================================================================================================== control room ==
/** The company page's control room: the state and its switches, who changed them, when and why, the month's budget with a quick edit,
 *  the live activity of its agents, hiring, its sites' health, and removal. */
export function ControlRoom({ co, d, ui }: { co: Company; d: ControlData; ui: ControlUi }) {
  const holding = co.kind === 'holding';
  const t: CoTarget = { code: co.code, nameFa: co.name_fa ?? co.code, holding };
  const s = d.state(co.code, holding, co);
  return (
    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-4">
        <StateCard co={co} s={s} t={t} d={d} ui={ui} />
        <LiveFeedCard code={co.code} holding={holding} d={d} />
        {!holding ? <SitesCard code={co.code} /> : null}
      </div>
      <div className="flex min-w-0 flex-col gap-4">
        <BudgetCard t={t} ui={ui} />
        <HistoryCard code={co.code} holding={holding} s={s} />
        <HiringCard code={co.code} holding={holding} />
        {!holding ? (
          <Card className="flex items-center gap-3 p-4">
            <span className="flex size-9 flex-none items-center justify-center rounded-full bg-neg-soft text-neg"><Icon name="dismiss" size={18} /></span>
            <span className="flex min-w-0 flex-1 flex-col"><span className="text-[14px] font-semibold">حذف شرکت</span><span className="text-[12px] text-muted">اگر اشتباهی ساخته شده؛ شرکتی که سابقه دارد فقط بایگانی میشود.</span></span>
            <Button variant="ghost" size="sm" icon="dismiss" onClick={() => ui.open('delete', t)}>حذف</Button>
          </Card>
        ) : null}
      </div>
    </div>
  );
}

function SwitchRow({ icon, title, note, tint, action }: { icon: IconName; title: string; note: ReactNode; tint: string; action: ReactNode }) {
  return (
    <div className="flex items-center gap-3 p-3">
      <span className="flex size-9 flex-none items-center justify-center rounded-full" style={{ color: tint, background: `color-mix(in srgb, ${tint} 14%, transparent)` }}><Icon name={icon} size={18} /></span>
      <span className="flex min-w-0 flex-1 flex-col"><span className="text-[13px] font-semibold">{title}</span><span className="line-clamp-2 text-[12px] text-muted">{note}</span></span>
      {action}
    </div>
  );
}

function StateCard({ co, s, t, d, ui }: { co: Company; s: CoState; t: CoTarget; d: ControlData; ui: ControlUi }) {
  return (
    <Card className={cx('flex flex-col gap-4 p-5 transition-colors duration-300', s.stopped || s.holdingStopped ? 'bg-neg-soft' : '')}>
      <div className="flex items-center gap-4">
        <ActivityRing code={co.code} holding={t.holding} stopped={!s.running} busy={d.busy(co.code)} stir={d.stirred(co.code)} size={64} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <span className={cx('text-h2 font-semibold', !s.running && 'text-neg')}>{s.stopped ? 'متوقف' : s.holdingStopped ? 'متوقف با هلدینگ' : d.busy(co.code) ? 'در حال کار' : 'روشن و آرام'}</span>
          <StateLine s={s} d={d} />
        </div>
      </div>
      {s.stopped && s.sw?.reason ? <p className="text-[13px] text-sec">«{s.sw.reason}»</p> : null}
      <div className="divide-y divide-div rounded-[12px] bg-tile">
        <SwitchRow icon="pause" title="کلید توقف" note={s.stopped ? 'روشن: ایجنت‌ها ایستاده‌اند' : 'خاموش: ایجنت‌ها کار میکنند'} tint={s.stopped ? 'var(--hq-negative)' : 'var(--hq-silver-ink)'}
          action={s.stopped ? <Button size="sm" variant="primary" icon="resume" onClick={() => ui.open('resume', t)}>ادامه</Button> : <Button size="sm" variant="danger" icon="pause" onClick={() => ui.open('stop', t)}>توقف</Button>} />
        {!t.holding ? (
          <SwitchRow icon="lock" title="deploy" note={s.freeze ? <>بسته تا {jTime(s.freeze.until)}، {until(s.freeze.until)}</> : 'باز: انتشارها با مُهر تو بیرون میروند'} tint={s.frozen ? 'var(--hq-warning)' : 'var(--hq-silver-ink)'}
            action={s.frozen ? <Button size="sm" icon="resume" onClick={() => ui.open('unfreeze', t)}>باز کن</Button> : <Button size="sm" variant="ghost" icon="lock" onClick={() => ui.open('freeze', t)}>ببند</Button>} />
        ) : null}
      </div>
    </Card>
  );
}

const HISTORY: Record<ControlEvent['kind'], { icon: IconName; tint: string; title: string }> = {
  engage: { icon: 'pause', tint: 'var(--hq-negative)', title: 'متوقف شد' },
  release: { icon: 'resume', tint: 'var(--hq-positive)', title: 'ادامه داد' },
  freeze: { icon: 'lock', tint: 'var(--hq-warning)', title: 'deploy بسته شد' },
  unfreeze: { icon: 'resume', tint: 'var(--hq-silver-ink)', title: 'deploy باز شد' },
};
const actorLabel = (a: Schemas['Actor']) => (a.kind === 'owner' ? 'تو' : a.code === 'pipeline' ? 'خط انتشار' : a.display_fa || a.code);

function HistoryCard({ code, holding, s }: { code: string; holding: boolean; s: CoState }) {
  const q = useControlHistory(code, holding);
  const rows = q.data ?? [];
  const firstSwitch = rows.findIndex((e) => e.kind === 'engage' || e.kind === 'release');
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="تاریخچه‌ی کلیدها" note="چه کسی، کی و چرا" />
      {q.isLoading ? <Skeleton className="h-32" /> : !rows.length ? <p className="text-[12px] text-muted">هنوز هیچ کلیدی زده نشده.</p> : (
        <ol className="flex flex-col">
          {rows.map((e, i) => {
            const h = HISTORY[e.kind];
            // The switch as it stands carries its reason, whoever pulled it.
            const why = e.reason ?? (i === firstSwitch && s.sw && s.sw.changed_by === e.by.code && (s.sw.state === 'engaged') === (e.kind === 'engage') ? s.sw.reason : null);
            return (
              <li key={`${e.at}-${i}`} className="relative flex gap-3 pb-4 last:pb-0">
                {i < rows.length - 1 ? <span aria-hidden className="absolute bottom-0 start-[11.5px] top-7 w-px bg-div" /> : null}
                <span className="mt-0.5 flex size-6 flex-none items-center justify-center rounded-full" style={{ color: h.tint, background: `color-mix(in srgb, ${h.tint} 14%, transparent)` }}><Icon name={h.icon} size={13} /></span>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="flex items-center gap-1.5 text-[13px]"><span className="font-semibold">{h.title}</span><span className={cx('truncate text-sec', e.by.kind !== 'owner' && !e.by.display_fa && 'fig')}>{actorLabel(e.by)}</span>{e.stepUp ? <span className="text-gold-ink" title="با اثر انگشت"><Icon name="seal" size={12} /></span> : null}</span>
                  <span className="text-[11px] text-muted">{ago(e.at)}، {jDateTime(e.at)}{e.until ? <>، تا {jTime(e.until)}</> : null}</span>
                  {why ? <span className="text-[12px] text-sec">«{why}»</span> : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}

/** A half-ring meter: silver below 70%, warning to 90%, red above; it fills when it appears. */
export function Gauge({ pct }: { pct: number | null | undefined }) {
  const v = Math.max(0, Math.min(100, pct ?? 0));
  const tone = budgetTone(pct);
  const color = tone === 'neg' ? 'var(--hq-negative)' : tone === 'warn' ? 'var(--hq-warning)' : 'var(--hq-silver-ink)';
  const len = Math.PI * 50;
  return (
    <div className="relative flex h-[96px] w-[132px] flex-none items-end justify-center" role="meter" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100} aria-label="مصرف بودجه‌ی ماه">
      <svg viewBox="0 0 120 66" className="absolute inset-x-0 top-1 w-full" aria-hidden>
        <path d="M10 60 A50 50 0 0 1 110 60" fill="none" stroke="var(--hq-surface-tile)" strokeWidth="10" strokeLinecap="round" />
        {/* Right to left: the fill grows from the start of the reading direction. */}
        <path d="M110 60 A50 50 0 0 0 10 60" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" strokeDasharray={len} strokeDashoffset={len * (1 - v / 100)}
          style={{ transition: 'stroke-dashoffset var(--hq-dur-ceremony) var(--hq-ease-ceremony)' }} />
      </svg>
      <span className="relative flex flex-col items-center">
        <span className={cx('text-h2 font-semibold', tone === 'neg' ? 'text-neg' : tone === 'warn' ? 'text-warn' : 'text-ink')}>{pct == null ? '—' : `${Math.round(pct)}٪`}</span>
        <span className="text-[11px] text-muted">از سقف ماه</span>
      </span>
    </div>
  );
}

const millions = (n: number) => { const m = n / 1_000_000; return Number.isInteger(m) ? String(m) : m.toFixed(2).replace(/0+$/, '').replace(/\.$/, ''); };
const parseMillions = (s: string): number | null => { const n = Number(s.replace(/[٫,]/g, '.').replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))); return Number.isFinite(n) && n > 0 ? Math.round(n * 1_000_000) : null; };

/** The month's budget as a gauge, with a quick edit sealed with the passkey on the exact body (PUT /budgets, `budgets.update`). */
function BudgetCard({ t, ui }: { t: CoTarget; ui: ControlUi }) {
  const q = useBudgets();
  const [editing, setEditing] = useState(false);
  const b = q.data?.find((x) => x.company === t.code && x.scope_type === (t.holding ? 'holding' : 'company') && x.period === 'month');
  const pct = b ? b.pct ?? pctOf(b.tokens_used, b.token_limit, b.usd_used, b.usd_limit) : null;
  const base = b?.token_limit ?? null;
  const [text, setText] = useState('');
  const parsed = parseMillions(text);
  const diff = parsed != null && base != null ? parsed - base : null;
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="بودجه‌ی ماه" note={t.holding ? 'سقف کل هلدینگ؛ هشدار در ۷۰٪ و ۹۰٪' : 'پاکت ماه؛ هشدار در ۷۰٪ و ۹۰٪'}
        action={<Button variant="text" size="sm" icon={editing ? 'close' : 'edit'} onClick={() => { setEditing(!editing); setText(base ? millions(base) : ''); }}>{editing ? 'بستن' : 'ویرایش'}</Button>} />
      {q.isLoading ? <Skeleton className="h-28" /> : (
        <div className="flex items-center gap-5">
          <Gauge pct={pct} />
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-col"><span className="text-[11px] text-muted">توکن</span><span className="fig text-[15px] font-semibold">{tokens(b?.tokens_used ?? 0)} / {tokens(b?.token_limit)}</span></div>
            <div className="flex flex-col"><span className="text-[11px] text-muted">{b?.usd_limit == null ? 'دلار معادل (بی‌سقف)' : 'دلار معادل'}</span><span className="fig text-[15px] font-semibold">{b?.usd_limit ? `${usd(b.usd_used)} / ${usd(b.usd_limit)}` : usd(b?.usd_used ?? '0')}</span></div>
            {b?.token_limit == null && b?.usd_limit == null ? <span className="text-[12px] text-warn">سقفی تعیین نشده؛ این شرکت بی‌پاکت است.</span> : null}
          </div>
        </div>
      )}
      {editing ? (
        <div className="hq-rise flex flex-col gap-3 border-t border-div pt-4">
          <span className="text-[12px] text-muted">سقف تازه به میلیون توکن</span>
          {base ? <div className="flex flex-wrap gap-2">{([[0.8, '−۲۰٪'], [1.2, '+۲۰٪'], [1.5, '+۵۰٪'], [2, 'دو برابر']] as const).map(([k, l]) => { const v = Math.round(base * k); return <FilterChip key={l} selected={parsed === v} onClick={() => setText(millions(v))}>{l}</FilterChip>; })}</div> : null}
          <input dir="ltr" inputMode="decimal" value={text} onChange={(e) => setText(e.target.value)} maxLength={10} placeholder="6" className={cx(inputCls, 'fig text-left')} aria-label="سقف به میلیون توکن" />
          {diff ? <span className={cx('text-[12px]', diff > 0 ? 'text-warn' : 'text-pos')}>{diff > 0 ? 'افزایش ' : 'کاهش '}<span className="fig">{tokens(Math.abs(diff))}</span> توکن در ماه</span> : null}
          <Button variant="primary" icon="seal" disabled={parsed == null || parsed === base} loading={ui.busy} onClick={async () => { if (await ui.budget(t, parsed, b?.usd_limit ?? null)) setEditing(false); }}>ذخیره با اثر انگشت</Button>
        </div>
      ) : null}
    </Card>
  );
}

/** What its agents are doing: runs started and finished, outputs, cards, from the stream as they happen and the latest before. */
function LiveFeedCard({ code, holding, d }: { code: string; holding: boolean; d: ControlData }) {
  const runs = useRuns({ company: code, limit: 12 });
  const outs = useOutputs({ company: code });
  const cards = useDecisions({ company: [code] });
  const rows = useMemo<FeedRow[]>(() => {
    const live = (d.pulses[code]?.recent ?? []).map(feedRowOf);
    const loaded: FeedRow[] = [
      ...(runs.data?.items ?? []).flatMap((r) => [
        ...(r.started_at ? [{ at: r.started_at, type: 'run.started', ref: r.id, employee: r.employee, state: null, work: r.work_ref, status: null, to: null }] : []),
        ...(r.finished_at ? [{ at: r.finished_at, type: 'run.finished', ref: r.id, employee: r.employee, state: r.state, work: r.work_ref, status: null, to: null }] : []),
      ]),
      ...(outs.data?.pages[0]?.items ?? []).filter((o) => o.company === code).slice(0, 6).map((o) => ({ at: o.created_at, type: 'deliverable.created', ref: o.ref, employee: o.producer.code, state: null, work: o.work_ref, status: null, to: null })),
      ...(cards.data?.items ?? []).filter((k) => k.company === code).slice(0, 20).flatMap((k) => [
        { at: k.created_at, type: 'decision.created', ref: k.ref, employee: null, state: null, work: null, status: null, to: null },
        ...(k.decided_at ? [{ at: k.decided_at, type: 'decision.decided', ref: k.ref, employee: null, state: k.status, work: null, status: null, to: null }] : []),
      ]),
    ];
    const seen = new Set<string>();
    return [...live, ...loaded].filter((r) => { const k = `${r.type}|${r.ref}`; if (seen.has(k)) return false; seen.add(k); return true; }).sort((a, b) => b.at.localeCompare(a.at));
  }, [d.pulses, code, runs.data, outs.data, cards.data]);
  const live = d.busy(code);
  return (
    <Card className="flex flex-col gap-2 p-5">
      <SectionTitle title="فعالیت زنده" note={holding ? 'مشاور، ناظر، دستیار و کارهای خود هلدینگ' : 'اجراها، خروجی‌ها و کارت‌ها، همان لحظه'} action={<Pill tone={live ? 'pos' : 'neutral'} live={live} dot={!live}>{live ? 'در حال کار' : 'آرام'}</Pill>} />
      {!rows.length && runs.isLoading ? <Skeleton className="h-40" /> : !rows.length ? <p className="text-[12px] text-muted">هنوز خبری نیست؛ ایجنت‌ها تا رسیدن کار خواب‌اند.</p>
        : <div className="flex flex-col">{rows.slice(0, 8).map((r) => <FeedLine key={`${r.type}|${r.ref}|${r.at}`} r={r} />)}</div>}
    </Card>
  );
}

/** Hiring: whether it is open and how, and this company's envelope this month (§18.11). */
function HiringCard({ code, holding }: { code: string; holding: boolean }) {
  const q = useHiring();
  const h = q.data;
  const e = h?.envelopes.find((x) => x.company === code);
  const limit = e?.tokens_month ?? null;
  return (
    <Link href="/settings" className="block rounded-[16px] focus-visible:outline-2">
      <Card className="flex flex-col gap-2 p-5 transition-colors hover:bg-hover">
        <SectionTitle title="استخدام" action={<span className="text-muted"><Icon name="next" size={16} mirror /></span>} />
        {!h ? <Skeleton className="h-14" /> : (
          <>
            <div className="flex items-center gap-2">
              {h.state !== 'open' ? <Pill tone="neutral" icon="lock">بسته</Pill> : h.mode === 'delegated' ? <Pill tone="pos" dot>باز؛ مدیرعامل‌ها در پاکت</Pill> : <Pill tone="gold" dot>باز؛ هر استخدام کارت تو</Pill>}
              {h.changed_at ? <span className="text-[12px] text-muted">از {ago(h.changed_at)}</span> : null}
            </div>
            {!holding && e ? (
              <>
                <span className="text-[12px] text-sec">پاکت ماه <span className="fig">{tokens(limit)}</span>؛ تعهد <span className="fig">{tokens(e.committed_month)}</span>، مصرف <span className="fig">{tokens(e.used_month)}</span>؛ {e.hires_month} استخدام این ماه</span>
                {limit ? <Bar pct={(100 * e.committed_month) / limit} tone={budgetTone((100 * e.committed_month) / limit)} /> : <span className="text-[12px] text-warn">بی‌پاکت: استخدام واگذارشده برای این شرکت ممکن نیست.</span>}
              </>
            ) : null}
          </>
        )}
      </Card>
    </Link>
  );
}

/** The company's sites (§16.4): up or down, the last check, the day's uptime, and open incidents. Nothing when it has none. */
function SitesCard({ code }: { code: string }) {
  const sites = useSites(code);
  const incidents = useIncidents({ company: code, open: true });
  const list = (sites.data ?? []).filter((s) => s.enabled);
  if (!list.length) return null;
  const open = incidents.data ?? [];
  return (
    <Link href="/sites" className="block rounded-[16px]">
      <Card className="flex flex-col gap-2 p-5 transition-colors hover:bg-hover">
        <SectionTitle title="سلامت سایت‌ها" note={open.length ? `${open.length} رخداد باز` : 'هیچ رخداد بازی نیست'} action={open.length ? <Pill tone="neg" icon="urgent">رخداد</Pill> : <Pill tone="pos" dot>سالم</Pill>} />
        {list.map((s) => {
          const last = (s.last ?? {}) as { ok?: boolean; ms?: number };
          const ok = last.ok !== false && !s.consecutive_failures;
          return (
            <div key={s.url} className="flex items-center gap-2 py-1">
              <span className={cx('size-2 rounded-full', ok ? 'bg-pos' : 'bg-neg')} />
              <span className="fig min-w-0 flex-1 truncate text-[12px] text-ink">{s.url.replace(/^https?:\/\//, '')}</span>
              {last.ms != null ? <span className={cx('fig text-[12px]', last.ms > 1500 ? 'text-warn' : 'text-muted')}>{last.ms}ms</span> : null}
              {s.uptime_24h != null ? <span className="fig text-[12px] text-sec">{(s.uptime_24h * 100).toFixed(1)}%</span> : null}
            </div>
          );
        })}
      </Card>
    </Link>
  );
}
