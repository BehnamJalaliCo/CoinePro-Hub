'use client';

import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { LinesChart } from '@/components/charts/charts';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, Pill, SectionTitle, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { useCompanies } from '@/lib/api/hooks';
import { faError, useKpiAction, useKpiValues, useKpis, useScorecards, type Card as KpiCard, type CardKpi, type Kpi, type KpiPatch } from '@/lib/api/v17';
import { useNow } from '@/lib/store';
import { ago, cx } from '@/lib/format';
import { CARD_FA, KPI_STATE, RefChip, Trend, kpiFig, onTarget } from './bits';

const field = 'h-9 rounded-[10px] border border-strong bg-tile px-2 text-[13px] text-ink outline-none focus:border-gold-ink';
const dayLabel = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { day: 'numeric', month: 'short', timeZone: 'Asia/Tehran' });

/** One KPI: its value with unit, the target, the trend, and how fresh it is. A KPI without a source shows a dash, never zero. */
function KpiRow({ k, direction, onOpen }: { k: CardKpi; direction?: 'up' | 'down'; onOpen?: () => void }) {
  const now = useNow();
  // §20.4's Card carries no direction: without the definition the row does not judge the target.
  const hit = direction ? onTarget(k.value, k.target, direction) : null;
  const st = KPI_STATE[k.state] ?? { fa: k.state, tone: 'neutral' as const };
  const inner = (
    <>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex items-center gap-2 text-[13px] text-sec"><span className="min-w-0 truncate">{k.name_fa}</span>{k.state !== 'ok' ? <Pill tone={st.tone} dot className="h-5 flex-none text-[10px]">{st.fa}</Pill> : null}</span>
        <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className={cx('fig text-[18px] font-semibold leading-7', k.value == null ? 'text-muted' : 'text-ink')}>{kpiFig(k.value, k.unit)}</span>
          {k.target != null ? <span className="flex items-center gap-1 text-[11px] text-muted">هدف <span className="fig">{kpiFig(k.target, k.unit)}</span>{hit != null ? <span className={hit ? 'text-pos' : 'text-warn'}><Icon name={hit ? 'seal' : 'urgent'} size={12} /></span> : null}</span> : null}
        </span>
        <span className="text-[11px] text-muted">{k.state === 'no_source' ? 'منبعی در رجیستری نیست؛ عدد ساخته نمیشود' : <>{now && k.at ? ago(k.at, now) : ''}{k.source_ref ? <> · <span className="fig">{k.source_ref.ref}</span></> : null}</>}</span>
      </div>
      <Trend values={k.trend} hit={hit} />
    </>
  );
  return onOpen ? <button type="button" onClick={onOpen} className="flex w-full items-center gap-3 rounded-[10px] px-2 py-2.5 text-right transition-colors hover:bg-hover">{inner}</button> : <div className="flex items-center gap-3 px-2 py-2.5">{inner}</div>;
}

export function CardPanel({ c, onOpen, dirs }: { c: KpiCard; onOpen?: (key: string) => void; dirs?: Record<string, 'up' | 'down'> }) {
  const meta = CARD_FA[c.card] ?? { fa: c.card, icon: 'chart' as const, note: '' };
  const stale = c.kpis.filter((k) => k.state === 'stale').length;
  return (
    <Card className="flex min-w-0 flex-col gap-1 p-3">
      <div className="flex items-center gap-2 px-2 pt-1">
        <span className="flex size-8 items-center justify-center rounded-[10px] bg-tile text-gold-ink"><Icon name={meta.icon} size={18} /></span>
        <span className="flex min-w-0 flex-1 flex-col"><span className="text-[15px] font-semibold">{meta.fa}</span><span className="text-[11px] text-muted">{meta.note}</span></span>
        {stale ? <Pill tone="warn" className="h-5 text-[11px]">{stale} قدیمی</Pill> : null}
      </div>
      <div className="flex flex-col divide-y divide-[var(--hq-line-divider)]">{c.kpis.map((k) => <KpiRow key={k.key} k={k} direction={dirs?.[k.key]} onOpen={onOpen ? () => onOpen(k.key) : undefined} />)}</div>
    </Card>
  );
}

/** One KPI over 30 days, from its own values (every value with its source). */
export function KpiSheet({ company, k, def, onClose }: { company: string; k: CardKpi; def: Kpi | undefined; onClose: () => void }) {
  const now = useNow();
  const to = now ? new Date(now).toISOString().slice(0, 10) : '';
  const from = now ? new Date(now - 30 * 86_400_000).toISOString().slice(0, 10) : '';
  const q = useKpiValues(now ? company : null, k.key, from, to);
  const vs = q.data ?? [];
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={k.name_fa} description={def ? (def.source.kind === 'query' ? `از رجیستری: ${def.source.query}` : 'دستی، با kpi.record و شاهد') : undefined} width={620}>
      <div className="flex flex-col gap-4 text-[13px]">
        <div className="flex flex-wrap items-baseline gap-3"><span className="fig text-[26px] font-semibold">{kpiFig(k.value, k.unit)}</span>{k.target != null ? <span className="text-sec">هدف <span className="fig">{kpiFig(k.target, k.unit)}</span></span> : null}<Pill tone={KPI_STATE[k.state]?.tone ?? 'neutral'} dot>{KPI_STATE[k.state]?.fa}</Pill></div>
        {q.isLoading ? <Skeleton className="h-60" /> : vs.length < 2 ? <Empty icon="chart" title="مقداری برای نمودار نیست" body={k.state === 'no_source' ? 'تا منبع وصل نشود، این KPI عدد ندارد؛ هرگز صفر نشان داده نمیشود.' : undefined} /> : (
          <LinesChart label={`روند ${k.name_fa}`} days={vs.map((v) => ({ key: v.at, label: dayLabel.format(new Date(v.at)) }))} lines={[{ key: k.key, label: k.name_fa, color: 'var(--hq-chart-1)', values: vs.map((v) => v.value) }]} fmt={(v) => kpiFig(Number(v.toFixed(2)), k.unit)} height={220} />
        )}
        {def ? (
          <dl className="grid grid-cols-2 gap-2">
            {([['جهت', def.direction === 'up' ? 'بیشتر بهتر' : 'کمتر بهتر'], ['تازگی', `${def.freshness_hours} ساعت`], ['تجمیع در هلدینگ', def.aggregate], ['کارت امتیاز', def.scorecard ? 'بله' : 'نه']] as const).map(([a, b]) => (
              <div key={a} className="flex flex-col gap-0.5 rounded-[12px] bg-tile p-3"><dt className="text-[11px] text-muted">{a}</dt><dd className="text-[13px] font-semibold text-ink">{b}</dd></div>
            ))}
          </dl>
        ) : null}
        {vs.length ? <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">آخرین منبع: <RefChip r={vs.at(-1)!.source_ref.ref} note={vs.at(-1)!.source_ref.note || null} tone="neutral" /></div> : null}
      </div>
    </Sheet>
  );
}

/** Targets and which KPIs make the scorecard: the owner's to set (If-Match on the company's set). */
export function TargetsSheet({ company, onClose }: { company: string; onClose: () => void }) {
  const q = useKpis(company);
  const save = useKpiAction();
  const toast = useToast();
  const [edit, setEdit] = useState<Record<string, Partial<KpiPatch>>>({});
  const rows = (q.data?.kpis ?? []).map((k) => ({ ...k, ...edit[k.key] }));
  const set = (key: string, p: Partial<KpiPatch>) => setEdit((e) => ({ ...e, [key]: { ...e[key], ...p } }));
  const run = () => q.data && save.mutateAsync({ set: q.data, kpis: rows.filter((r) => edit[r.key]).map((r) => ({ key: r.key, target: r.target, scorecard: r.scorecard, status: r.status, freshness_hours: r.freshness_hours })) })
    .then(() => { toast({ tone: 'ok', text: 'هدف‌ها ذخیره شد؛ کارت‌ها و امتیاز شرکت از همین حساب میشوند.' }); onClose(); })
    .catch((e) => toast({ tone: 'error', text: faError(e) }));
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title="هدف‌ها و کارت امتیاز" description="تحقق KPI در امتیاز شرکت (۳۵٪) از همین هدف‌هاست، وقتی OKR فعالی نیست." width={640}
      footer={<Button variant="primary" className="w-full" disabled={!Object.keys(edit).length} loading={save.isPending} onClick={() => void run()}>ذخیره</Button>}>
      {!q.data ? <Skeleton className="h-64" /> : (
        <ul className="flex flex-col">
          {rows.map((k) => (
            <li key={k.key} className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-div py-3 last:border-0">
              <span className="flex min-w-0 flex-[1_1_12rem] flex-col"><span className="text-[13px] font-semibold">{k.name_fa}</span><span className="fig text-[11px] text-muted">{k.source.kind === 'query' ? k.source.query : 'manual'} · {CARD_FA[k.card]?.fa}</span></span>
              <label className="flex items-center gap-1.5 text-[12px] text-sec">هدف
                <input inputMode="decimal" dir="ltr" value={k.target ?? ''} onChange={(e) => set(k.key, { target: e.target.value.trim() === '' ? null : Number(e.target.value.replace(/[^\d.]/g, '')) })} aria-label={`هدف ${k.name_fa}`} className={cx(field, 'fig w-24')} />
                <span className="fig text-[11px] text-muted">{k.unit}</span>
              </label>
              <label className="flex items-center gap-1.5 text-[12px] text-sec">تازگی
                <input inputMode="numeric" dir="ltr" value={k.freshness_hours} onChange={(e) => set(k.key, { freshness_hours: Number(e.target.value.replace(/\D/g, '') || 1) })} aria-label={`تازگی ${k.name_fa}`} className={cx(field, 'fig w-14')} />h
              </label>
              <label className="flex items-center gap-1.5 text-[12px] text-sec"><Switch checked={k.scorecard} onChange={(v) => set(k.key, { scorecard: v })} label={`کارت امتیاز: ${k.name_fa}`} />امتیاز</label>
              <label className="flex items-center gap-1.5 text-[12px] text-sec"><Switch checked={k.status === 'active'} onChange={(v) => set(k.key, { status: v ? 'active' : 'paused' })} label={`فعال: ${k.name_fa}`} />فعال</label>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}

/** The live scorecard: one row per company (any number, paged and searchable), each cell a scorecard KPI with value, target and trend. */
export function Scorecard() {
  const [text, setText] = useState('');
  const q = useScorecards(text);
  const { data: companies } = useCompanies();
  const rows = useMemo(() => q.data?.pages.flatMap((p) => p.items) ?? [], [q.data]);
  const cols = useMemo(() => {
    const m = new Map<string, { key: string; name_fa: string }>();
    for (const r of rows) for (const k of r.kpis) if (!m.has(k.key)) m.set(k.key, { key: k.key, name_fa: k.name_fa });
    return [...m.values()];
  }, [rows]);
  const name = (c: string) => companies?.find((x) => x.code === c)?.name_fa ?? c;
  return (
    <Card className="flex flex-col gap-3 p-4 md:p-5">
      <SectionTitle title="کارت امتیاز" note="یک ردیف برای هر شرکت؛ هر عدد با زمان و منبع" action={<input value={text} onChange={(e) => setText(e.target.value)} placeholder="جستجوی شرکت" aria-label="جستجوی شرکت در کارت امتیاز" className={cx(field, 'w-40')} />} />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-40" /> : !rows.length ? <Empty icon="chart" title="شرکتی پیدا نشد" /> : (
        <>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full border-collapse text-[13px]">
              <thead><tr className="text-right text-[11px] text-muted"><th className="px-2 py-2 font-semibold">شرکت</th>{cols.map((c) => <th key={c.key} className="px-2 py-2 font-semibold">{c.name_fa}</th>)}</tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.company} className="border-t border-div align-top">
                    <td className="px-2 py-3"><span className="flex items-center gap-2 font-semibold"><CompanyMark code={r.company} height={14} mono />{name(r.company)}</span></td>
                    {cols.map((c) => {
                      const k = r.kpis.find((x) => x.key === c.key);
                      if (!k) return <td key={c.key} className="px-2 py-3 text-muted">—</td>;
                      const hit = k.direction ? onTarget(k.value, k.target, k.direction) : null;
                      return (
                        <td key={c.key} className="px-2 py-3">
                          <span className="flex flex-col gap-1">
                            <span className="flex items-center gap-1.5"><span className={cx('fig font-semibold', k.value == null ? 'text-muted' : hit === false ? 'text-warn' : 'text-ink')}>{kpiFig(k.value, k.unit)}</span><Trend values={k.trend} hit={hit} width={44} height={16} /></span>
                            <span className="text-[11px] text-muted">{k.state !== 'ok' ? KPI_STATE[k.state]?.fa : k.target != null ? <>هدف <span className="fig">{kpiFig(k.target, k.unit)}</span></> : ''}</span>
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="flex flex-col gap-3 md:hidden">
            {rows.map((r) => (
              <li key={r.company} className="flex flex-col gap-1 rounded-[14px] bg-tile p-3">
                <span className="flex items-center gap-2 text-[14px] font-semibold"><CompanyMark code={r.company} height={14} mono />{name(r.company)}</span>
                <div className="flex flex-col divide-y divide-[var(--hq-line-divider)]">{r.kpis.map((k) => <KpiRow key={k.key} k={k} direction={k.direction} />)}</div>
              </li>
            ))}
          </ul>
          {q.hasNextPage ? <Button variant="secondary" size="sm" className="self-start" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>شرکت‌های بیشتر</Button> : null}
        </>
      )}
    </Card>
  );
}
