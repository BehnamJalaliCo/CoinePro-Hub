'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Md } from '@/components/ui/md';
import { Card, ErrorState, FilterChip, PageHeader, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { Score, Spark, Stars } from '@/components/v14/bits';
import { useCompanies } from '@/lib/api/hooks';
import { useLessons, useRollup, useRubrics } from '@/lib/api/v14';
import { companyOf } from '@/lib/company';
import { cx, jDate } from '@/lib/format';

const PARTS: Array<[keyof import('@/lib/api/v14').CompanyStanding['parts'], string, number]> = [['kpi', 'KPI', 40], ['challenges', 'چالش‌ها', 25], ['compliance', 'انطباق', 20], ['people', 'ستاره‌ی کارمندها', 15]];

/** ستاره‌ها (contract §18.4): CEOs give their people 0–5 stars weekly under their own rubric; companies are ranked from KPIs,
 *  the overseer's challenges, compliance and their people. The owner gives no stars; the owner's 1–10 rating stays separate. */
export default function StarsPage() {
  const [period, setPeriod] = useState<'week' | 'month'>('week');
  const q = useRollup(period);
  const rubrics = useRubrics();
  const lessons = useLessons();
  const { data: companies } = useCompanies();
  const [co, setCo] = useState<string | null>(null);
  const r = q.data;
  const best = r?.companies.find((c) => c.company === r.best_company);
  const people = (r?.employees ?? []).filter((e) => !co || e.company === co);
  const rubric = rubrics.data?.find((x) => x.company === (co ?? r?.best_company));
  return (
    <>
      <PageHeader eyebrow="برآیند هفتگی شنبه صبح، ماهانه اول هر ماه" title="ستاره‌ها" actions={<Segmented label="بازه" value={period} onChange={setPeriod} options={[{ value: 'week', label: 'این هفته' }, { value: 'month', label: 'این ماه' }]} />}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">مدیرعامل هر شرکت طبق آیین‌نامه‌ی خودش به کارمندها ستاره میدهد؛ ناظر کل انصاف و شاهدش را میپاید. امتیاز ۱ تا ۱۰ تو جداست.</p>
      </PageHeader>
      {q.isLoading ? <Skeleton className="h-48" /> : q.error || !r ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <>
          {best ? (
            <Card className="tahrir flex flex-wrap items-center gap-5 p-5">
              <span className="flex size-14 items-center justify-center rounded-full bg-gold-soft text-gold-ink"><Icon name="star" size={28} active /></span>
              <div className="flex min-w-0 flex-[1_1_14rem] flex-col gap-1">
                <span className="text-caption text-muted">شرکت برتر {period === 'week' ? 'هفته' : 'ماه'} · {period === 'week' ? `هفته‌ی ${jDate(r.key)}` : r.key}</span>
                <span className="flex items-center gap-2 text-h2 font-semibold"><CompanyMark code={best.company} height={20} />{companyOf(companies, best.company).nameFa}</span>
              </div>
              <Stars value={best.stars} size={22} />
              <span className="fig text-[28px] font-semibold">{best.score}</span>
            </Card>
          ) : null}
          <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <Card className="flex flex-col gap-1 p-4">
              <SectionTitle title="رتبه‌ی شرکت‌ها" note="امتیاز = ۴۰٪ KPI + ۲۵٪ چالش‌ها + ۲۰٪ انطباق + ۱۵٪ ستاره‌ی کارمندها" />
              {r.companies.map((c) => (
                <div key={c.company} className="flex flex-col gap-2 border-b border-div py-3 last:border-0">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="fig w-6 text-[18px] font-semibold text-muted">{c.rank}</span>
                    <span className="flex min-w-0 flex-1 items-center gap-2 text-[14px] font-semibold"><CompanyMark code={c.company} height={15} mono />{companyOf(companies, c.company).nameFa}</span>
                    <Stars value={c.stars} />
                    <Spark values={c.trend} min={40} max={100} />
                  </div>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 ps-9 sm:grid-cols-4">
                    {PARTS.map(([k, fa, w]) => (
                      <span key={k} className="flex flex-col gap-0.5"><span className="text-[11px] text-muted">{fa} <span className="fig">{w}%</span></span><Score value={c.parts[k]} /></span>
                    ))}
                  </div>
                </div>
              ))}
            </Card>
            <Card className="flex flex-col gap-3 p-4">
              <SectionTitle title="کارمندهای برتر" note="ستاره‌ی مدیرعامل، با شاهد" />
              <div className="flex flex-wrap gap-2">
                <FilterChip selected={!co} onClick={() => setCo(null)}>همه</FilterChip>
                {r.companies.map((c) => <FilterChip key={c.company} selected={co === c.company} onClick={() => setCo(c.company)}><span className="flex items-center gap-1.5"><CompanyMark code={c.company} height={12} mono />{companyOf(companies, c.company).nameFa}</span></FilterChip>)}
              </div>
              <ul className="flex flex-col">
                {people.map((e) => (
                  <li key={e.code} className="border-b border-div last:border-0">
                    <Link href={`/employees/${e.code}`} className="flex items-center gap-3 rounded-[8px] px-1 py-2.5 hover:bg-hover">
                      <span className="fig w-5 text-[12px] text-muted">{co ? e.rank_company : e.rank_holding}</span>
                      <Avatar kind={e.code.endsWith('-MGR') ? 'manager' : 'employee'} dept={e.code.split('-')[1]} size={30} />
                      <span className="flex min-w-0 flex-1 flex-col"><span className="truncate text-[13px]">{e.title_fa}</span><span className="fig text-[11px] text-muted">{e.code}</span></span>
                      <Stars value={e.stars} size={13} />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
          <div className="grid items-start gap-4 xl:grid-cols-2">
            <Card className="flex flex-col gap-3 p-4">
              <SectionTitle title="درس‌ها از شرکت برتر" note="هر هفته ناظر مینویسد؛ بقیه پیشنهاد به‌کارگیری میدهند" />
              {(lessons.data?.items ?? []).map((l) => (
                <div key={l.ref} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
                  <div className="flex items-center gap-2"><CompanyMark code={l.source_company} height={13} mono /><span className="min-w-0 flex-1 text-[14px] font-semibold">{l.title_fa}</span><span className="fig text-[11px] text-muted">{l.ref}</span></div>
                  <Md text={l.body_md} className="text-[13px] leading-6 text-sec" />
                  <div className="flex flex-wrap gap-1.5">
                    {l.adoption.map((a) => <Pill key={a.company} tone={a.status === 'adopted' ? 'pos' : a.status === 'rejected' ? 'neg' : 'neutral'} dot><span className="flex items-center gap-1"><CompanyMark code={a.company} height={11} mono />{a.status === 'adopted' ? 'به‌کار گرفت' : a.status === 'rejected' ? 'رد کرد' : 'پیشنهاد داد'}</span></Pill>)}
                  </div>
                </div>
              ))}
            </Card>
            <Card className="flex flex-col gap-3 p-4">
              <SectionTitle title={<>آیین‌نامه‌ی ستاره{rubric ? <> · {companyOf(companies, rubric.company).nameFa}</> : null}</>} note="نوشته‌ی مدیرعامل همان شرکت؛ تو میبینی" />
              {rubric ? (
                <>
                  <ul className="flex flex-col gap-1.5">
                    {rubric.criteria.map((c) => (
                      <li key={c.key} className="flex items-center gap-3 text-[13px]">
                        <span className="min-w-0 flex-1">{c.name_fa}<span className="block text-[11px] text-muted">{c.description_md}</span></span>
                        <span className={cx('fig w-10 text-left text-sec')}>{c.weight}%</span>
                      </li>
                    ))}
                  </ul>
                  <p className="border-t border-div pt-2 text-[12px] leading-6 text-sec">{rubric.rules_md}</p>
                  <p className="text-[11px] text-muted">نسخه‌ی <span className="fig">{rubric.version}</span> · {jDate(rubric.updated_at)}</p>
                </>
              ) : <Skeleton className="h-32" />}
            </Card>
          </div>
        </>
      )}
    </>
  );
}
