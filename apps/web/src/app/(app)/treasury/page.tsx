'use client';

import { useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { CumulativeChart, HBars, StackedBar } from '@/components/charts/charts';
import { Avatar } from '@/components/brand/avatar';
import { Button } from '@/components/ui/button';
import { BudgetEditor, CallsCard, ConnectionEditor, QuotaCard, WhatIfCard } from '@/components/v15/treasury';
import type { Connection } from '@/lib/api/v15';
import { Bar, Card, ErrorState, PageHeader, Pill, SectionTitle, Segmented, Skeleton, StatTile, budgetTone } from '@/components/ui/primitives';
import { useBreakdown, useCompanies, useConnections, useTreasury } from '@/lib/api/hooks';
import { companyColor } from '@/lib/company';
import { useScope } from '@/lib/scope';
import { tokens, usd, cx, until } from '@/lib/format';
import { ModelMark, ModelName } from '@/components/brand/model-mark';

const TOKEN_COLOR = { input: 'var(--hq-chart-1)', output: 'var(--hq-chart-2)', cache: 'var(--hq-chart-3)', write: 'var(--hq-chart-5)', thinking: 'var(--hq-chart-4)' };


/** `llm.connections.status` (LLM layer, prompt 3): enabled, disabled or quota_exhausted. */
const CONNECTION_STATUS: Record<string, { label: string; tone: 'pos' | 'warn' | 'neutral' }> = {
  enabled: { label: 'روشن', tone: 'pos' },
  quota_exhausted: { label: 'سهمیه تمام', tone: 'warn' },
  disabled: { label: 'خاموش', tone: 'neutral' },
};
export default function TreasuryPage() {
  const { company } = useScope();
  const [period, setPeriod] = useState<'day' | 'month'>('month');
  const sum = useTreasury({ period, company: company ?? undefined });
  const byCompany = useBreakdown({ by: 'company' });
  const byModel = useBreakdown({ by: 'model', company: company ?? undefined });
  const byDay = useBreakdown({ by: 'day' as never, company: company ?? undefined });
  const conns = useConnections();
  const { data: companies } = useCompanies();
  const t = sum.data?.totals;
  const [editBudgets, setEditBudgets] = useState(false);
  const [editConn, setEditConn] = useState<Connection | null>(null);
  const budget = sum.data?.budgets.find((b) => (company ? b.scope_type === 'company' && b.company === company : b.scope_type === 'holding'));

  const days = (byDay.data ?? []).filter((r) => r.key).sort((a, b) => String(a.key).localeCompare(String(b.key))).map((r) => ({
    key: String(r.key),
    label: new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { day: 'numeric', month: 'short', timeZone: 'Asia/Tehran' }).format(new Date(`${r.key}T12:00:00Z`)),
    value: r.input_tokens + r.output_tokens,
  }));
  const daysInMonth = 30;

  return (
    <>
      <PageHeader eyebrow="مصرف هر فراخوانی، از یک مسیر واحد" title="خزانه‌ی توکن" actions={<div className="w-56"><Segmented label="دوره" value={period} onChange={setPeriod} options={[{ value: 'day', label: 'امروز' }, { value: 'month', label: 'این ماه' }]} /></div>} />
      {sum.error ? <ErrorState error={sum.error} onRetry={() => sum.refetch()} /> : null}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {!t ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[104px] rounded-[14px]" />) : (
          <>
            <StatTile label="توکن ورودی و خروجی" value={<span className="fig">{tokens(t.input_tokens + t.output_tokens)}</span>} sub={<span><span className="fig">{tokens(t.cache_read_tokens)}</span> از کش خوانده شد</span>} />
            <StatTile label="هزینه‌ی معادل" value={<span className="fig">{usd(t.equiv_cost_usd)}</span>} sub={<span>پرداخت واقعی API: <span className="fig">{usd(t.cost_usd)}</span></span>} />
            <StatTile label="فراخوانی" value={t.calls} sub={period === 'day' ? 'از نیمه‌شب تهران' : 'از اول ماه'} />
            <StatTile label="بودجه‌ی مصرف‌شده" value={budget?.pct != null ? `${Math.round(budget.pct)}٪` : '—'} tone={(budget?.pct ?? 0) >= 90 ? 'neg' : (budget?.pct ?? 0) >= 70 ? 'warn' : undefined} sub={budget ? <span className="fig">{tokens(budget.tokens_used)} / {tokens(budget.token_limit)}</span> : 'بودجه‌ای تعیین نشده'} />
          </>
        )}
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {days.length > 1 ? (
            <Card className="flex flex-col gap-3 p-5">
              <SectionTitle title="مصرف تجمعی ماه" note="خط قرمز سقف بودجه؛ خط‌چین پیش‌بینی تا آخر ماه با همین آهنگ" />
              <CumulativeChart days={days} budget={budget?.token_limit} forecastTo={daysInMonth} fmt={tokens} />
            </Card>
          ) : null}
          <Card className="flex flex-col gap-4 p-5">
            <SectionTitle title="نوع توکن" note="فکر در اشتراک جدا گزارش نمیشود و داخل خروجی است" />
            {t ? <StackedBar label="سهم انواع توکن" segs={[
              { key: 'in', label: 'ورودی', value: t.input_tokens, color: TOKEN_COLOR.input, fmt: tokens(t.input_tokens) },
              { key: 'out', label: 'خروجی', value: t.output_tokens, color: TOKEN_COLOR.output, fmt: tokens(t.output_tokens) },
              { key: 'cr', label: 'خواندن کش', value: t.cache_read_tokens, color: TOKEN_COLOR.cache, fmt: tokens(t.cache_read_tokens) },
              { key: 'cw', label: 'نوشتن کش', value: t.cache_write_tokens, color: TOKEN_COLOR.write, fmt: tokens(t.cache_write_tokens) },
              ...(t.thinking_tokens ? [{ key: 'th', label: 'فکر', value: t.thinking_tokens, color: TOKEN_COLOR.thinking, fmt: tokens(t.thinking_tokens) }] : []),
            ]} /> : <Skeleton className="h-20" />}
          </Card>
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="flex flex-col gap-4 p-5">
              <SectionTitle title="شرکت‌ها" note="رنگ هر شرکت ثابت است، نه بر اساس رتبه" />
              {byCompany.data ? <HBars rows={byCompany.data.filter((r) => r.key).map((r) => ({ key: String(r.key), label: <span className="flex items-center gap-2"><CompanyMark code={String(r.key)} height={14} mono />{companies?.find((c) => c.code === r.key)?.name_fa ?? r.key}</span>, value: r.input_tokens + r.output_tokens, fmt: usd(r.equiv_cost_usd), sub: <span className="fig">{tokens(r.input_tokens + r.output_tokens)}</span>, color: companyColor(companies, String(r.key)) }))} /> : <Skeleton className="h-40" />}
            </Card>
            <Card className="flex flex-col gap-4 p-5">
              <SectionTitle title="مدل‌ها" />
              {byModel.data ? <HBars rows={byModel.data.filter((r) => r.key).map((r) => ({ key: String(r.key), label: <ModelName model={String(r.key)} />, value: Number(r.equiv_cost_usd), fmt: usd(r.equiv_cost_usd), sub: <span><span className="fig">{tokens(r.input_tokens + r.output_tokens)}</span>، {r.calls} فراخوانی</span> }))} /> : <Skeleton className="h-40" />}
            </Card>
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <QuotaCard />
          <Card className="flex flex-col gap-3 p-5">
            <SectionTitle title="بودجه‌ها" note="هشدار ۷۰٪ و ۹۰٪؛ در ۱۰۰٪ کارهای غیرفوری میایستند" action={<Button variant="text" size="sm" icon="edit" onClick={() => setEditBudgets(true)}>ویرایش</Button>} />
            {(sum.data?.budgets ?? []).map((b) => (
              <div key={`${b.scope_type}-${b.scope_ref}-${b.period}`} className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2 text-[12px]">
                  <span className="flex flex-1 items-center gap-1.5 text-sec">{b.scope_type === 'holding' ? 'کل هلدینگ' : <><CompanyMark code={b.company} height={12} mono />{companies?.find((c) => c.code === b.company)?.name_fa ?? b.scope_ref}</>}</span>
                  <span className="fig text-muted">{tokens(b.tokens_used)} / {tokens(b.token_limit)}</span>
                  <span className={cx('w-10 text-left font-semibold', (b.pct ?? 0) >= 90 ? 'text-neg' : (b.pct ?? 0) >= 70 ? 'text-warn' : 'text-sec')}>{Math.round(b.pct ?? 0)}٪</span>
                </div>
                <Bar pct={b.pct ?? 0} tone={budgetTone(b.pct)} />
              </div>
            ))}
          </Card>
          <Card className="flex flex-col gap-2 p-5">
            <SectionTitle title="پرمصرف‌ها" />
            {(sum.data?.top_consumers ?? []).map((c, i) => (
              <div key={c.actor} className="flex items-center gap-3 border-b border-div py-2 last:border-0">
                <span className="w-4 text-[12px] text-muted">{i + 1}</span>
                <Avatar kind={c.actor.endsWith('-ADV') ? 'advisor' : c.actor.endsWith('-CEO') ? 'ceo' : c.actor.endsWith('-MGR') ? 'manager' : c.actor.endsWith('-SYS') ? 'system' : 'employee'} dept={c.actor.split('-')[1]} size={30} />
                <div className="flex min-w-0 flex-1 flex-col"><span className="fig truncate text-[13px] text-ink">{c.actor}</span><span className="text-[11px] text-muted">{c.calls} فراخوانی</span></div>
                <span className="fig text-[12px] text-sec">{tokens(c.tokens)}</span>
                <span className="fig w-14 text-left text-[13px] font-semibold">{usd(c.usd)}</span>
              </div>
            ))}
          </Card>
          <Card className="flex flex-col gap-2 p-5">
            <SectionTitle title="اتصال‌ها" note="کلیدها هرگز نمایش داده نمیشوند" />
            {(conns.data ?? []).map((c) => {
              const st = CONNECTION_STATUS[c.status] ?? { label: c.status, tone: 'neutral' as const };
              return (
                <button type="button" key={c.id} onClick={() => setEditConn(c)} className="flex items-center gap-3 rounded-[12px] bg-tile p-3 text-start hover:bg-hover">
                  <ModelMark model={c.default_model ?? c.models[0]} provider={c.provider} size={22} />
                  <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="text-[13px] font-semibold">{c.display_name}</span>
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted">
                      <span className="fig">{c.key}</span>
                      {c.models.map((m) => <ModelName key={m} model={m} size={11} />)}
                    </span>
                    {c.status === 'quota_exhausted' && c.quota_reset_at ? <span className="text-[11px] text-warn">ریست سهمیه {until(c.quota_reset_at)}</span> : null}
                    {c.status_reason ? <span className="text-[11px] text-muted">{c.status_reason}</span> : null}
                  </div>
                  <Pill tone={st.tone} dot>{st.label}</Pill>
                </button>
              );
            })}
          </Card>
          <WhatIfCard company={company} />
        </div>
      </div>
      <CallsCard company={company} />
      {editBudgets ? <BudgetEditor onClose={() => setEditBudgets(false)} /> : null}
      {editConn ? <ConnectionEditor c={editConn as Connection} onClose={() => setEditConn(null)} /> : null}
    </>
  );
}
