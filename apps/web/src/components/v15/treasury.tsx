'use client';

import { useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Bar, Card, ErrorState, FilterChip, Pill, SectionTitle, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { downloadCsv, useBudgets, useCallPages, useQuota, useTreasuryAction, useWhatIf, type BudgetIn, type BudgetUse, type Connection } from '@/lib/api/v15';
import { cx, jDateTime, modelLabel, tokens, until, usd } from '@/lib/format';

const field = 'h-10 w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
const fail = (toast: ReturnType<typeof useToast>, e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' });

// ------------------------------------------------------------------ quota --
const QUOTA: Record<string, { fa: string; tone: 'pos' | 'warn' | 'neg' }> = { ok: { fa: 'عادی', tone: 'pos' }, warning: { fa: 'نزدیک سقف', tone: 'warn' }, limited: { fa: 'محدود', tone: 'neg' } };

/** The subscription quota (§16.5): the Quota Controller pauses P4 at "warning" and lets only P0–P2 through at "limited". */
export function QuotaCard() {
  const q = useQuota();
  const s = q.data?.subscription;
  const st = s ? QUOTA[s.status] ?? { fa: s.status, tone: 'pos' as const } : null;
  const used = s?.utilization != null ? Math.round(Number(s.utilization) * 100) : null;
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="سهمیه‌ی اشتراک" note="کنترل‌کننده‌ی سهمیه کد است، نه مدل" action={st ? <Pill tone={st.tone} dot>{st.fa}</Pill> : null} />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !s ? <Skeleton className="h-16" /> : (
        <>
          {used != null ? <><div className="flex items-center text-[12px] text-sec"><span className="flex-1">مصرف پنجره{s.window ? <> (<span className="fig">{s.window}</span>)</> : null}</span><span className="fig">{used}%</span></div><Bar pct={used} tone={used >= 90 ? 'neg' : used >= 70 ? 'warn' : 'silver'} /></> : null}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted">
            {s.resets_at ? <span>ریست {until(s.resets_at)}</span> : null}
            {s.connection ? <span className="fig">{s.connection}</span> : null}
            {s.changed_at ? <span>آخرین تغییر {jDateTime(s.changed_at)}</span> : null}
          </div>
          {q.data!.throttle.paused_priorities.length ? <p className="rounded-[10px] bg-warn-soft p-2.5 text-[12px]">کارهای <span className="fig">{q.data!.throttle.paused_priorities.join('، ')}</span> تا ریست سهمیه نگه داشته شده‌اند.</p> : null}
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- what-if --
const MODELS = ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'];
/** "What would this month have cost on model X" from our own price table (design list #22). */
export function WhatIfCard({ company }: { company: string | null }) {
  const [model, setModel] = useState(MODELS[2]!);
  const now = new Date();
  const from = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString().slice(0, 10);
  const to = now.toISOString().slice(0, 10);
  const q = useWhatIf({ model, from, to, company });
  const d = q.data;
  const diff = d?.difference_usd != null ? Number(d.difference_usd) : null;
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="اگر با این مدل بود…" note="همین فراخوانی‌های این ماه، با جدول قیمت خودمان" />
      <div className="flex flex-wrap gap-2">{MODELS.map((m) => <FilterChip key={m} selected={model === m} onClick={() => setModel(m)}><span className="fig">{modelLabel(m)}</span></FilterChip>)}</div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !d ? <Skeleton className="h-16" /> : (
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="flex flex-col gap-0.5 rounded-[12px] bg-tile p-3"><span className="text-[11px] text-muted">واقعی</span><span className="fig text-[16px] font-semibold">{usd(d.actual_usd)}</span></div>
          <div className="flex flex-col gap-0.5 rounded-[12px] bg-tile p-3"><span className="text-[11px] text-muted">با <span className="fig">{modelLabel(model)}</span></span><span className="fig text-[16px] font-semibold">{d.what_if_usd != null ? usd(d.what_if_usd) : '—'}</span></div>
          <div className={cx('flex flex-col gap-0.5 rounded-[12px] p-3', diff == null ? 'bg-tile' : diff < 0 ? 'bg-pos-soft' : 'bg-warn-soft')}><span className="text-[11px] text-muted">{diff == null ? 'فرق' : diff < 0 ? 'ارزان‌تر' : 'گران‌تر'}</span><span className="fig text-[16px] font-semibold">{diff != null ? usd(Math.abs(diff)) : '—'}</span></div>
        </div>
      )}
      {d ? <p className="text-[11px] text-muted"><span className="fig">{d.priced_calls}</span> از <span className="fig">{d.calls}</span> فراخوانی قیمت داشت{d.as_of ? <> · قیمت‌ها از <span className="fig">{d.as_of}</span></> : null}. فقط هزینه است، نه کیفیت؛ مقایسه‌ی کیفیت با ارزیابی آکادمی.</p> : null}
    </Card>
  );
}

// ---------------------------------------------------------------- budgets --
const M = 1_000_000;
const toM = (n: number | null | undefined) => (n == null ? '' : String(Math.round((n / M) * 100) / 100));
const fromM = (s: string) => (s.trim() === '' ? null : Math.round(Number(s.replace(/[٬,]/g, '').replace('٫', '.')) * M));
type Row = { key: string; company: string; scope_type: 'holding' | 'company'; period: 'day' | 'month'; tokens: string; usd: string };

/** Budgets per scope and period (§9 PUT /budgets): the holding's month in tokens and dollars, each company's month and day. Sealed on the body. */
export function BudgetEditor({ onClose }: { onClose: () => void }) {
  const q = useBudgets();
  const { data: companies } = useCompanies();
  const act = useTreasuryAction();
  const toast = useToast();
  const [rows, setRows] = useState<Row[] | null>(null);
  const holding = companies?.find((c) => c.kind === 'holding')?.code ?? 'HQ';
  if (q.data && companies && !rows) {
    const find = (scope: 'holding' | 'company', company: string, period: 'day' | 'month') => q.data.find((b: BudgetUse) => b.scope_type === scope && b.company === company && b.period === period);
    const mk = (scope: 'holding' | 'company', company: string, period: 'day' | 'month'): Row => { const b = find(scope, company, period); return { key: `${scope}-${company}-${period}`, company, scope_type: scope, period, tokens: toM(b?.token_limit), usd: b?.usd_limit ?? '' }; };
    setRows([mk('holding', holding, 'month'), ...companies.filter((c) => c.kind !== 'holding').flatMap((c) => [mk('company', c.code, 'month'), mk('company', c.code, 'day')])]);
  }
  const patch = (key: string, p: Partial<Row>) => setRows((rs) => rs!.map((r) => (r.key === key ? { ...r, ...p } : r)));
  const valid = !!rows && rows.every((r) => (r.tokens === '' || Number(r.tokens.replace('٫', '.')) > 0) && (r.usd === '' || Number(r.usd) > 0));
  const save = async () => {
    if (!rows) return;
    const items: BudgetIn[] = rows.filter((r) => r.tokens !== '' || r.usd !== '').map((r) => ({ company: r.company, scope_type: r.scope_type, scope_ref: r.company, period: r.period, token_limit: fromM(r.tokens), usd_limit: r.usd === '' ? null : Number(r.usd).toFixed(2), enabled: true }));
    try { await act.budgets.mutateAsync(items); toast({ tone: 'ok', text: 'بودجه‌ها ذخیره شد.' }); onClose(); } catch (e) { fail(toast, e); }
  };
  const label = (r: Row) => (r.scope_type === 'holding' ? 'کل هلدینگ' : companies?.find((c) => c.code === r.company)?.name_fa ?? r.company);
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} title="ویرایش بودجه‌ها" width={560} description="به میلیون توکن؛ خالی یعنی بی‌سقف. پاکت ماهانه‌ی هر شرکت همان سقف استخدام مدیرعامل است."
      footer={<><Button variant="primary" icon="seal" loading={act.budgets.isPending} disabled={!valid} onClick={save}>ذخیره با passkey</Button><Button variant="ghost" onClick={onClose}>انصراف</Button></>}>
      {!rows ? <Skeleton className="h-60" /> : (
        <div className="flex flex-col gap-2">
          <div className="grid grid-cols-[minmax(0,1fr)_5.5rem_5.5rem_5.5rem] items-center gap-2 px-1 text-[11px] text-muted"><span /><span>ماه (M)</span><span>روز (M)</span><span>ماه ($)</span></div>
          {rows.filter((r) => r.period === 'month').map((r) => {
            const day = rows.find((x) => x.key === `${r.scope_type}-${r.company}-day`);
            return (
              <div key={r.key} className="grid grid-cols-[minmax(0,1fr)_5.5rem_5.5rem_5.5rem] items-center gap-2 rounded-[12px] bg-tile p-2">
                <span className="flex items-center gap-2 text-[13px]">{r.scope_type === 'company' ? <CompanyMark code={r.company} height={13} mono /> : null}{label(r)}</span>
                <input value={r.tokens} onChange={(e) => patch(r.key, { tokens: e.target.value })} inputMode="decimal" dir="ltr" placeholder="—" aria-label={`${label(r)}: ماهانه به میلیون توکن`} className={cx(field, 'fig px-2 text-center')} />
                {day ? <input value={day.tokens} onChange={(e) => patch(day.key, { tokens: e.target.value })} inputMode="decimal" dir="ltr" placeholder="—" aria-label={`${label(r)}: روزانه به میلیون توکن`} className={cx(field, 'fig px-2 text-center')} /> : <span />}
                <input value={r.usd} onChange={(e) => patch(r.key, { usd: e.target.value })} inputMode="decimal" dir="ltr" placeholder="—" aria-label={`${label(r)}: ماهانه به دلار`} className={cx(field, 'fig px-2 text-center')} />
              </div>
            );
          })}
        </div>
      )}
    </Sheet>
  );
}

// ------------------------------------------------------------ connections --
/** One connection (§10): name and on/off with If-Match and a passkey; its key is write-only and never comes back. */
export function ConnectionEditor({ c, onClose }: { c: Connection; onClose: () => void }) {
  const act = useTreasuryAction();
  const toast = useToast();
  const [name, setName] = useState(c.display_name);
  const [on, setOn] = useState(c.status !== 'disabled');
  const [secret, setSecret] = useState('');
  const takesKey = c.kind !== 'claude_subscription';
  const changed = name.trim() !== c.display_name || on !== (c.status !== 'disabled');
  const save = async () => {
    try {
      if (changed) await act.connection.mutateAsync({ c, patch: { ...(name.trim() !== c.display_name ? { display_name: name.trim() } : {}), ...(on !== (c.status !== 'disabled') ? { status: on ? 'enabled' : 'disabled' } : {}) } });
      if (secret.trim()) await act.secret.mutateAsync({ id: c.id, secret: secret.trim() });
      setSecret('');
      toast({ tone: 'ok', text: 'اتصال به‌روز شد.' });
      onClose();
    } catch (e) { fail(toast, e); }
  };
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} title={c.display_name} description={<span className="fig">{c.key} · {c.provider}</span>}
      footer={<><Button variant="primary" icon="seal" loading={act.connection.isPending || act.secret.isPending} disabled={!changed && !secret.trim()} onClick={save}>ذخیره با passkey</Button><Button variant="ghost" onClick={onClose}>انصراف</Button></>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <label className="flex flex-col gap-1.5 font-semibold text-sec">نام<input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className={field} /></label>
        <div className="flex items-center gap-3 rounded-[12px] bg-tile p-3"><span className="flex-1">{on ? 'روشن؛ مسیریاب از آن استفاده میکند' : 'خاموش؛ هیچ فراخوانی از آن رد نمیشود'}</span><Switch label="روشن" checked={on} onChange={setOn} /></div>
        {takesKey ? (
          <label className="flex flex-col gap-1.5 font-semibold text-sec">کلید تازه
            <input type="password" autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} dir="ltr" placeholder={c.has_secret_ref ? 'کلید فعلی میماند مگر کلید تازه بدهی' : 'کلید API'} className={cx(field, 'fig')} />
            <span className="text-[11px] font-normal text-muted">مستقیم به خزانه‌ی رمزها میرود؛ نه اینجا نمایش داده میشود و نه در Audit.</span>
          </label>
        ) : <p className="text-[12px] text-muted">اشتراک Claude کلید ندارد؛ اعتبارش روی خود سرور است.</p>}
        <p className="text-[12px] text-muted">مدل‌ها: <span className="fig">{c.models.map(modelLabel).join('، ')}</span></p>
      </div>
    </Sheet>
  );
}

// ------------------------------------------------------------------ calls --
const CALL_STATUS: Record<string, { fa: string; cls: string }> = { ok: { fa: 'موفق', cls: 'text-sec' }, error: { fa: 'خطا', cls: 'text-neg' }, refused: { fa: 'رد', cls: 'text-warn' } };

/** Every model call, metadata only (§10 GET /treasury/calls): never the prompt or the response. */
export function CallsCard({ company }: { company: string | null }) {
  const [status, setStatus] = useState<string | null>(null);
  const [actor, setActor] = useState('');
  const q = useCallPages({ company, status, actor: actor.trim() || null });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const exportCsv = () => downloadCsv('calls.csv', ['started_at', 'company', 'actor', 'work', 'model', 'status', 'input', 'output', 'cache_read', 'latency_ms', 'equiv_usd'],
    items.map((c) => [c.started_at, c.company, c.actor, c.work_ref, c.model, c.status, c.input_tokens, c.output_tokens, c.cache_read_tokens, c.latency_ms, c.equiv_cost_usd]));
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="فراخوانی‌ها" note="فقط متادیتا؛ متن پرامپت و پاسخ هرگز اینجا نیست" action={items.length ? <Button variant="text" size="sm" icon="download" onClick={exportCsv}>Excel</Button> : null} />
      <div className="flex flex-wrap items-center gap-2">
        {[null, 'ok', 'error', 'refused'].map((s) => <FilterChip key={s ?? 'all'} selected={status === s} onClick={() => setStatus(s)}>{s ? CALL_STATUS[s]!.fa : 'همه'}</FilterChip>)}
        <input value={actor} onChange={(e) => setActor(e.target.value.toUpperCase())} dir="ltr" placeholder="FX-TECH-MGR" aria-label="کد کارمند" className="fig h-9 w-44 rounded-[10px] border border-strong bg-tile px-3 text-[13px] text-ink outline-none focus:border-gold-ink" />
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-60" /> : !items.length ? <p className="py-6 text-center text-[13px] text-muted">فراخوانی‌ای نیست.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] border-collapse text-[12px]">
            <thead><tr className="text-right text-[11px] text-muted">{['زمان', 'کارمند', 'کار', 'مدل', 'وضعیت', 'ورودی', 'خروجی', 'کش', 'تأخیر', 'هزینه'].map((h) => <th key={h} className="px-2 py-1.5 font-semibold">{h}</th>)}</tr></thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="h-10 border-t border-div">
                  <td className="whitespace-nowrap px-2 text-sec">{jDateTime(c.started_at)}</td>
                  <td className="px-2"><span className="flex items-center gap-1.5"><CompanyMark code={c.company} height={10} mono /><span className="fig text-ink">{c.actor}</span></span></td>
                  <td className="fig px-2 text-muted">{c.work_ref ?? '—'}</td>
                  <td className="fig px-2 text-sec">{modelLabel(c.model)}</td>
                  <td className={cx('px-2', CALL_STATUS[c.status]?.cls ?? 'text-sec')}><span className="inline-flex items-center gap-1.5">{CALL_STATUS[c.status]?.fa ?? c.status}{c.error_class ? <span className="fig text-muted">{c.error_class}</span> : null}</span></td>
                  <td className="fig px-2 text-sec">{tokens(c.input_tokens)}</td>
                  <td className="fig px-2 text-sec">{tokens(c.output_tokens)}</td>
                  <td className="fig px-2 text-muted">{tokens(c.cache_read_tokens)}</td>
                  <td className="fig px-2 text-muted">{c.latency_ms != null ? `${(c.latency_ms / 1000).toFixed(1)}s` : '—'}</td>
                  <td className="fig px-2 font-semibold">{usd(c.equiv_cost_usd, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {q.hasNextPage ? <Button variant="secondary" size="sm" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>بیشتر</Button> : null}
    </Card>
  );
}
