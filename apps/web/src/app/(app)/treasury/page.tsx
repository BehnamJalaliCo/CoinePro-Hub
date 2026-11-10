'use client';

import { useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { CumulativeChart, HBars, StackedBar } from '@/components/charts/charts';
import { Avatar } from '@/components/brand/avatar';
import { Button } from '@/components/ui/button';
import { BudgetEditor, CallsCard, ConnectionEditor, QuotaCard, WhatIfCard } from '@/components/v15/treasury';
import { CONN } from '@/components/v18/bits';
import { RoiCard, WasteCard } from '@/components/v18/treasury';
import Link from 'next/link';
import type { Connection } from '@/lib/api/v15';
import { TokenMeter } from '@/components/live/office';
import { Bar, Card, ErrorState, PageHeader, Pill, SectionTitle, Segmented, Skeleton, budgetTone } from '@/components/ui/primitives';
import { useBreakdown, useCompanies, useConnections, useTreasury } from '@/lib/api/hooks';
import { companyColor } from '@/lib/company';
import { useScope } from '@/lib/scope';
import { tokens, usd, cx, until, isRealModel } from '@/lib/format';
import { ModelMark, ModelName } from '@/components/brand/model-mark';
import { Icon } from '@/components/icon';
import { LimitsBlock } from '@/components/look/limits';
import { Amount, Facts, Ltr, clock } from '@/components/look/text';
import { useLimits } from '@/lib/api/v55';
import { DEPT_FA } from '@/lib/labels';

const TOKEN_COLOR = { input: 'var(--hq-chart-1)', output: 'var(--hq-chart-2)', cache: 'var(--hq-chart-3)', write: 'var(--hq-chart-5)', thinking: 'var(--hq-chart-4)' };


/** `llm.connections.status` (LLM layer, prompt 3): enabled, disabled or quota_exhausted. */
const CONNECTION_STATUS: Record<string, { label: string; tone: 'pos' | 'warn' | 'neutral' }> = {
  enabled: { label: 'روشن', tone: 'pos' },
  quota_exhausted: { label: 'سهمیه تمام', tone: 'warn' },
  disabled: { label: 'خاموش', tone: 'neutral' },
};
/** A role's code as the owner reads it: «مدیر فنی کوینه‌پرو اف‌ایکس», never «FX-TECH-MGR». */
function actorTitle(code: string, company: (c: string) => string): string {
  const [co = '', a = '', b = ''] = code.split('-');
  const name = company(co);
  if (a === 'CEO') return `مدیرعامل ${name}`;
  if (a === 'ADV') return 'مشاور کل';
  if (a === 'OVR') return 'ناظر کل';
  if (a === 'SYS') return 'سیستم';
  if (a === 'AST' || a === 'PA') return 'دستیار';
  const dept = DEPT_FA[a];
  if (dept && b === 'MGR') return `مدیر ${dept} ${name}`;
  if (dept && /^\d+$/.test(b)) return `کارمند ${dept} ${name}`;
  return name && name !== co ? `همکار ${name}` : 'همکار';
}

type Verdict = { tone: 'pos' | 'warn' | 'neg'; fa: string };
/** «تا آخر ماه میرسم یا نه»: this month's pace against its cap. The month is the hub's own (a calendar month, UTC). */
function verdictOf(used: number, limit: number | null | undefined, now = new Date()): Verdict | null {
  if (!limit) return null;
  const day = now.getUTCDate();
  const days = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0)).getUTCDate();
  const perDay = used / Math.max(1, day);
  const end = perDay * days;
  if (used >= limit) return { tone: 'neg', fa: 'سقف این ماه پر شده است.' };
  if (end > limit) return { tone: 'neg', fa: `با این آهنگ، حدود روز ${Math.min(days, Math.ceil(limit / perDay))} ماه به سقف میرسی.` };
  if (end > limit * 0.9) return { tone: 'warn', fa: 'با این آهنگ، آخر ماه به سقف نزدیک میشوی.' };
  return { tone: 'pos', fa: 'با این آهنگ، آخر ماه زیر سقف میمانی.' };
}
const VERDICT_CLS: Record<Verdict['tone'], string> = { pos: 'text-pos', warn: 'text-warn', neg: 'text-neg' };

/** One small figure of the row under the big number: Latin tabular digits, never cut. */
function Small({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-0.5 border-s border-div px-3 first:border-s-0 first:ps-0 last:pe-0">
      <Amount className="text-[17px] font-semibold leading-7 text-ink">{children}</Amount>
      <span className="text-[11px] leading-4 text-muted">{label}</span>
    </div>
  );
}

export default function TreasuryPage() {
  const { company } = useScope();
  const [period, setPeriod] = useState<'day' | 'month'>('month');
  const sum = useTreasury({ period, company: company ?? undefined });
  const byCompany = useBreakdown({ by: 'company' });
  const byModel = useBreakdown({ by: 'model', company: company ?? undefined });
  const byDay = useBreakdown({ by: 'day' as never, company: company ?? undefined });
  const conns = useConnections();
  const { data: companies } = useCompanies();
  const limits = useLimits();
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
  const companyName = (code: string) => companies?.find((c) => c.code === code)?.name_fa ?? code;
  const verdict = period === 'month' && budget ? verdictOf(budget.tokens_used, budget.token_limit) : null;
  const readAt = sum.dataUpdatedAt ? clock(sum.dataUpdatedAt) : null;

  return (
    <>
      <PageHeader eyebrow="مصرف هر فراخوانی، از یک مسیر واحد" title="خزانه‌ی توکن" actions={<div className="w-56"><Segmented label="دوره" value={period} onChange={setPeriod} options={[{ value: 'day', label: 'امروز' }, { value: 'month', label: 'این ماه' }]} /></div>} />
      {/* ⟨1.0.1⟩ §55.3: the Claude accounts as rings and today's meter. A hub before it: nothing here, and the older cards stay. */}
      <LimitsBlock limits={limits.data} className="max-w-3xl" />
      {/* ⟨1.24⟩ MO-1: today's spend in its four kinds, moving with every tick; under the limits it is the detail, alone it leads. */}
      {limits.data ? null : <TokenMeter named className="max-w-3xl" />}
      {sum.error ? <ErrorState error={sum.error} onRetry={() => sum.refetch()} /> : null}
      {!t ? <Skeleton className="h-[148px] max-w-3xl rounded-[16px]" /> : (
        <Card as="section" aria-label={period === 'month' ? 'مصرف این ماه' : 'مصرف امروز'} data-testid="treasury-hero" className="flex max-w-3xl flex-col gap-3 p-4 sm:p-5">
          {verdict ? (
            <p className={cx('flex items-start gap-2 text-[14px] font-semibold leading-6', VERDICT_CLS[verdict.tone])} data-verdict={verdict.tone}>
              <span className="mt-0.5 flex-none"><Icon name={verdict.tone === 'pos' ? 'seal' : 'urgent'} size={16} /></span>{verdict.fa}
            </p>
          ) : null}
          <div className="flex flex-wrap items-end gap-x-3 gap-y-1">
            <Amount className="max-w-full text-[40px] font-bold leading-[46px] text-ink" style={{ flex: '0 1 auto' }}>{period === 'month' && budget ? tokens(budget.tokens_used) : tokens(t.input_tokens + t.output_tokens)}</Amount>
            <span className="pb-1.5 text-[12px] leading-5 text-sec">
              {period === 'month' && budget
                ? <Facts><span>از <Ltr>{tokens(budget.token_limit)}</Ltr> سقف ماه</span>{budget.pct != null ? <Ltr className={cx('font-semibold', budget.pct >= 90 ? 'text-neg' : budget.pct >= 70 ? 'text-warn' : 'text-sec')}>{Math.round(budget.pct)}%</Ltr> : null}</Facts>
                : period === 'month' ? 'توکن این ماه' : 'توکن امروز، از نیمه‌شب تهران'}
            </span>
          </div>
          <div className="flex items-stretch" data-small-figures>
            <Small label="توکن ورودی و خروجی">{tokens(t.input_tokens + t.output_tokens)}</Small>
            <Small label="هزینه‌ی معادل">{usd(t.equiv_cost_usd)}</Small>
            <Small label="فراخوانی">{t.calls.toLocaleString('en-US')}</Small>
          </div>
          <p className="text-[11px] text-muted" data-read-at>
            <Facts>{period === 'month' ? 'از اول ماه' : 'امروز'}{readAt ? <span>خوانده‌شده در <Ltr>{readAt}</Ltr></span> : null}<span>پرداخت واقعی: <Ltr>{usd(t.cost_usd)}</Ltr></span></Facts>
          </p>
        </Card>
      )}

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
          {/* ⟨1.5⟩ §21.7: yesterday's waste, by category, with the 14 days before. */}
          <WasteCard company={company} />
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="flex flex-col gap-4 p-5">
              <SectionTitle title="شرکت‌ها" note="رنگ هر شرکت ثابت است، نه بر اساس رتبه" />
              {byCompany.data ? <HBars rows={byCompany.data.filter((r) => r.key).map((r) => ({ key: String(r.key), label: <span className="flex items-center gap-2"><CompanyMark code={String(r.key)} height={14} mono />{companies?.find((c) => c.code === r.key)?.name_fa ?? r.key}</span>, value: r.input_tokens + r.output_tokens, fmt: usd(r.equiv_cost_usd), sub: <span className="fig">{tokens(r.input_tokens + r.output_tokens)}</span>, color: companyColor(companies, String(r.key)) }))} /> : <Skeleton className="h-40" />}
            </Card>
            <Card className="flex flex-col gap-4 p-5">
              <SectionTitle title="مدل‌ها" />
              {byModel.data ? <HBars rows={byModel.data.filter((r) => isRealModel(r.key)).map((r) => ({ key: String(r.key), label: <ModelName model={String(r.key)} />, value: Number(r.equiv_cost_usd), fmt: usd(r.equiv_cost_usd), sub: <span><span className="fig">{tokens(r.input_tokens + r.output_tokens)}</span>، {r.calls} فراخوانی</span> }))} /> : <Skeleton className="h-40" />}
            </Card>
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          {limits.data ? <TokenMeter named /> : <QuotaCard />}
          <Card className="flex flex-col gap-3 p-5">
            <SectionTitle title="بودجه‌ها" note="هشدار ۷۰٪ و ۹۰٪؛ در ۱۰۰٪ کارهای غیرفوری میایستند" action={<Button variant="text" size="sm" icon="edit" onClick={() => setEditBudgets(true)}>ویرایش</Button>} />
            {(sum.data?.budgets ?? []).map((b) => (
              <div key={`${b.scope_type}-${b.scope_ref}-${b.period}`} className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2 text-[12px]">
                  <span className="flex flex-1 items-center gap-1.5 text-sec">{b.scope_type === 'holding' ? 'کل هلدینگ' : <><CompanyMark code={b.company} height={12} mono />{companies?.find((c) => c.code === b.company)?.name_fa ?? b.scope_ref}</>}</span>
                  <span className="fig text-muted">{tokens(b.tokens_used)} / {tokens(b.token_limit)}</span>
                  <Ltr className={cx('w-10 text-left font-semibold', (b.pct ?? 0) >= 90 ? 'text-neg' : (b.pct ?? 0) >= 70 ? 'text-warn' : 'text-sec')}>{Math.round(b.pct ?? 0)}%</Ltr>
                </div>
                <Bar pct={b.pct ?? 0} tone={budgetTone(b.pct)} />
              </div>
            ))}
          </Card>
          <Card as="section" aria-label="پرمصرف‌ها" className="flex flex-col gap-2 p-5">
            <SectionTitle title="پرمصرف‌ها" />
            {(sum.data?.top_consumers ?? []).map((c, i) => (
              <div key={c.actor} className="flex items-center gap-3 border-b border-div py-2 last:border-0">
                <span className="w-4 text-[12px] text-muted">{i + 1}</span>
                <Avatar kind={c.actor.endsWith('-ADV') ? 'advisor' : c.actor.endsWith('-CEO') ? 'ceo' : c.actor.endsWith('-MGR') ? 'manager' : c.actor.endsWith('-SYS') ? 'system' : 'employee'} dept={c.actor.split('-')[1]} size={30} />
                <div className="flex min-w-0 flex-1 flex-col"><span className="truncate text-[13px] text-ink">{actorTitle(c.actor, companyName)}</span><span className="text-[11px] text-muted"><Ltr>{c.calls}</Ltr> فراخوانی</span></div>
                <span className="fig text-[12px] text-sec">{tokens(c.tokens)}</span>
                <span className="fig w-14 text-left text-[13px] font-semibold">{usd(c.usd)}</span>
              </div>
            ))}
          </Card>
          <Card className="flex flex-col gap-2 p-5">
            <SectionTitle title="اتصال‌ها" note="کلیدها هرگز نمایش داده نمیشوند" action={<Link href="/tools" className="inline-flex h-8 items-center gap-1.5 rounded-[8px] px-3 text-[12px] font-semibold text-silver-ink hover:bg-[var(--hq-silver-soft)] hover:text-ink">اتصال تازه</Link>} />
            {(conns.data ?? []).map((c) => {
              // ⟨1.5⟩ §21.7 adds pending_secret, verifying, ready and error.
              const st: { label: string; tone: (typeof CONN)[string]['tone'] } = CONNECTION_STATUS[c.status] ?? { label: CONN[c.status]?.fa ?? c.status, tone: CONN[c.status]?.tone ?? 'neutral' };
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
      {/* ⟨1.5⟩ §21.7: ROI by company, department and employee. */}
      <RoiCard company={company} />
      <CallsCard company={company} />
      {editBudgets ? <BudgetEditor onClose={() => setEditBudgets(false)} /> : null}
      {editConn ? <ConnectionEditor c={editConn as Connection} onClose={() => setEditConn(null)} /> : null}
    </>
  );
}
