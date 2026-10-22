'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Bar, Card, Empty, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { ActorAvatar, RefChip, Trend } from '@/components/v17/bits';
import { useDepartmentRanks, useHrRounds, type HrEmployee, type HrRound } from '@/lib/api/v18';
import { cx, faDecimal, jDate } from '@/lib/format';
import { ACTOR_FA, DEPT_FA, DEPT_ICON } from '@/lib/labels';
import { HR_FLAG, HR_STATE, jMonth, pct01 } from './bits';

const PARTS: Array<{ key: 'people' | 'delivery' | 'efficiency' | 'owner'; fa: string; w: string }> = [
  { key: 'people', fa: 'نیرو', w: '۳۵٪' }, { key: 'delivery', fa: 'تحویل', w: '۳۰٪' }, { key: 'efficiency', fa: 'کارایی', w: '۲۰٪' }, { key: 'owner', fa: 'امتیاز تو', w: '۱۵٪' },
];

// ------------------------------------------------------------- department rank (§21.5) --
/** Ranks of a company's departments, by rule: 35% people, 30% delivery, 20% efficiency, 15% the owner's ratings (spread when there are none). */
export function DepartmentRanks({ company }: { company: string }) {
  const [period, setPeriod] = useState<'week' | 'month'>('month');
  const q = useDepartmentRanks({ period, company });
  const rows = [...(q.data ?? [])].sort((a, b) => a.rank_company - b.rank_company);
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="رتبه‌ی دپارتمان‌ها" note="با برآیند ستاره‌ها حساب میشود؛ دپارتمان بی‌کارمند فعال رتبه نمیگیرد" action={<div className="w-36"><Segmented label="دوره" value={period} onChange={setPeriod} options={[{ value: 'week', label: 'هفته' }, { value: 'month', label: 'ماه' }]} /></div>} />
      {q.isLoading ? <Skeleton className="h-40" /> : !rows.length ? <Empty icon="department" title="هنوز دپارتمانی رتبه نگرفته" /> : (
        <ol className="flex flex-col gap-2.5">
          {rows.map((r) => (
            <li key={r.department} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
              <div className="flex items-center gap-2.5">
                <span className="fig flex size-7 flex-none items-center justify-center rounded-full bg-card text-[12px] font-semibold text-gold-ink">{r.rank_company}</span>
                <span className="text-silver-ink"><Icon name={DEPT_ICON[r.department] ?? 'department'} size={18} /></span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-[13px] font-semibold text-ink">{DEPT_FA[r.department] ?? r.department}</span>
                  <span className="text-[11px] text-muted">{r.employees} نفر{r.rank_holding ? `، رتبه‌ی ${r.rank_holding} میان همین دپارتمان در هلدینگ` : ''}</span>
                </span>
                <Trend values={r.trend} width={60} height={22} />
                <span className="fig w-12 text-left text-[18px] font-semibold text-ink">{r.score.toFixed(1)}</span>
              </div>
              <Bar pct={r.score} tone={r.score >= 75 ? 'gold' : r.score >= 60 ? 'silver' : 'warn'} label={`امتیاز ${DEPT_FA[r.department] ?? r.department}`} />
              <div className="grid grid-cols-4 gap-1.5 text-center text-[11px]">
                {PARTS.map((p) => (
                  <div key={p.key} className="flex flex-col rounded-[8px] bg-card px-1 py-1" title={`وزن ${p.w}`}>
                    <span className="text-muted">{p.fa}</span>
                    <span className={cx('fig text-[12px] font-semibold', r.parts[p.key] == null ? 'text-muted' : 'text-ink')}>{r.parts[p.key] ?? '—'}</span>
                  </div>
                ))}
              </div>
            </li>
          ))}
        </ol>
      )}
      <p className="text-[11px] leading-5 text-muted">جایی که امتیاز تو نیست («—»)، وزن ۱۵٪ آن میان سه جزء دیگر پخش شده است.</p>
    </Card>
  );
}

// ----------------------------------------------------------------- HR round (§21.5) --
function EmployeeHr({ e }: { e: HrEmployee }) {
  const drop = e.score_prev != null ? e.score - e.score_prev : null;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-x-5 gap-y-1">
        <div className="flex items-end gap-1.5"><span className="text-[28px] font-semibold leading-none">{faDecimal(e.score)}</span><span className="pb-0.5 text-[11px] text-muted">از ۱۰</span></div>
        {drop != null ? <span className={cx('pb-0.5 text-[12px]', drop <= -1.5 ? 'text-warn' : drop >= 0 ? 'text-pos' : 'text-sec')}>{drop >= 0 ? '▲' : '▼'} {faDecimal(Math.abs(drop))} از ماه قبل ({faDecimal(e.score_prev!)})</span> : <span className="pb-0.5 text-[12px] text-muted">ماه اول</span>}
      </div>
      <dl className="grid grid-cols-3 gap-1.5 text-[11px]">
        <div className="flex flex-col rounded-[8px] bg-tile p-2"><dt className="text-muted">ستاره</dt><dd className="text-[13px] font-semibold text-ink">{e.stars != null ? faDecimal(e.stars) : '—'}</dd></div>
        <div className="flex flex-col rounded-[8px] bg-tile p-2"><dt className="text-muted">کارایی</dt><dd className="text-[13px] font-semibold text-ink">{e.efficiency ?? '—'}</dd></div>
        <div className="flex flex-col rounded-[8px] bg-tile p-2"><dt className="text-muted">امتیاز تو</dt><dd className="text-[13px] font-semibold text-ink">{e.owner_avg != null ? faDecimal(e.owner_avg) : '—'}</dd></div>
        <div className="flex flex-col rounded-[8px] bg-tile p-2"><dt className="text-muted">اجرای شکست‌خورده</dt><dd className={cx('fig text-[13px] font-semibold', e.failed_share >= 0.25 ? 'text-warn' : 'text-ink')}>{pct01(e.failed_share)}</dd></div>
        <div className="flex flex-col rounded-[8px] bg-tile p-2"><dt className="text-muted">یافته‌ی باز</dt><dd className={cx('text-[13px] font-semibold', e.findings_open ? 'text-warn' : 'text-ink')}>{e.findings_open}</dd></div>
        <div className="flex flex-col rounded-[8px] bg-tile p-2"><dt className="text-muted">ادعای رد شده</dt><dd className={cx('text-[13px] font-semibold', e.refuted_claims ? 'text-neg' : 'text-ink')}>{e.refuted_claims}</dd></div>
      </dl>
      {e.probation_until ? <p className="text-[12px] text-sec">دوره‌ی آزمایشی تا {jDate(e.probation_until, true)}</p> : null}
      {e.flags.length ? <div className="flex flex-wrap gap-1.5">{e.flags.map((f) => <Pill key={f} tone={HR_FLAG[f]?.tone ?? 'neutral'} dot>{HR_FLAG[f]?.fa ?? f}</Pill>)}</div> : <span className="text-[12px] text-muted">بی‌پرچم؛ کارتی برایش ساخته نمیشود مگر با شاهد و دلیل.</span>}
    </div>
  );
}

export function HrRoundSheet({ r, onClose }: { r: HrRound; onClose: () => void }) {
  const st = HR_STATE[r.state] ?? HR_STATE.done!;
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={600} title={<span className="flex items-center gap-2">ارزیابی ماهانه‌ی {jMonth(r.month)}<span className="fig text-[13px] text-muted">{r.ref}</span></span>}
      description="پرچم‌ها قاعده‌اند؛ ارزیاب فقط برای پرچم‌خورده‌ها کارت ارزیابی میسازد. «آموزش» کارت ندارد: پیش‌نویس آموزش آکادمی برای مدیر عملیات AI.">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
          <Pill tone={st.tone} dot>{st.fa}</Pill>
          <span className="flex items-center gap-1.5"><ActorAvatar a={r.evaluator} size={20} />{ACTOR_FA(r.evaluator)}</span>
          <span>مهلت {jDate(r.due_at)}</span>
          {r.deliverable_ref ? <RefChip r={r.deliverable_ref} note="گزارش HR" /> : null}
          {r.decisions.map((x) => <RefChip key={x} r={x} note="کارت ارزیابی" />)}
          {r.teachings.map((x) => <RefChip key={x} r={x} note="آموزش" tone="neutral" />)}
        </div>
        <ul className="flex flex-col gap-2">
          {r.employees.map((e) => (
            <li key={e.code} className="flex flex-col gap-2 rounded-[12px] bg-card p-3">
              <Link href={`/employees/${e.code}`} className="flex items-center gap-2 hover:underline"><span className="text-[13px] font-semibold text-ink">{e.title_fa}</span><span className="fig text-[11px] text-muted">{e.code}</span></Link>
              <EmployeeHr e={e} />
            </li>
          ))}
        </ul>
      </div>
    </Sheet>
  );
}

/** The employee's line of the latest monthly HR round (§21.5): the facts pack, the rule flags, and the card if one was proposed. */
export function HrCard({ code, company }: { code: string; company: string }) {
  const q = useHrRounds({ company });
  const [open, setOpen] = useState(false);
  const rounds = [...(q.data ?? [])].sort((a, b) => b.month.localeCompare(a.month));
  const r = rounds.find((x) => x.employees.some((e) => e.code === code));
  const e = r?.employees.find((x) => x.code === code);
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="ارزیابی ماهانه" note={r ? `${jMonth(r.month)}، ارزیاب ${ACTOR_FA(r.evaluator)}` : 'اول هر ماه شمسی'} action={r ? <Button size="sm" variant="text" iconEnd="next" onClick={() => setOpen(true)}>کل دور</Button> : null} />
      {q.isLoading ? <Skeleton className="h-28" /> : !r || !e ? <p className="text-[13px] text-muted">در دور ارزیابی این ماه نیست (تازه آمده، یا ارزیاب خود اوست).</p> : (
        <>
          <EmployeeHr e={e} />
          {r.decisions.length ? <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-sec">کارت این دور:{r.decisions.map((x) => <RefChip key={x} r={x} />)}</div> : null}
        </>
      )}
      {open && r ? <HrRoundSheet r={r} onClose={() => setOpen(false)} /> : null}
    </Card>
  );
}

/** The company's latest HR round in one line, beside its department ranks. */
export function HrRoundLine({ company }: { company: string }) {
  const q = useHrRounds({ company });
  const [open, setOpen] = useState(false);
  const r = [...(q.data ?? [])].sort((a, b) => b.month.localeCompare(a.month))[0];
  if (!r) return null;
  const flagged = r.employees.filter((e) => e.flags.length).length;
  const st = HR_STATE[r.state] ?? HR_STATE.done!;
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="flex w-full items-center gap-3 rounded-[14px] bg-card p-3 text-start hover:bg-hover">
        <span className="flex size-9 flex-none items-center justify-center rounded-full bg-tile text-gold-ink"><Icon name="rate" size={18} /></span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-[13px] font-semibold text-ink">ارزیابی ماهانه‌ی {jMonth(r.month)} <span className="fig text-[11px] font-normal text-muted">{r.ref}</span></span>
          <span className="text-[12px] text-sec">{r.employees.length} نفر، {flagged} پرچم‌خورده{r.decisions.length ? `، ${r.decisions.length} کارت` : ''}</span>
        </span>
        <Pill tone={st.tone} dot>{st.fa}</Pill>
      </button>
      {open ? <HrRoundSheet r={r} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
