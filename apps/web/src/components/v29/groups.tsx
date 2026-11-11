'use client';

// ⟨1.11⟩ Contract §29.11 «کارگروه‌ها» (growth groups, defined as data): the list, and one group's page — its purpose, the member companies
// (pause and resume), the seats and who fills them (with each employee's state, §29.14), the routines and their run history (pause and
// resume), the KPI charts per company, and the week's experiment.
//
// ⟨1.0.1⟩ Part C (C3.4), in the app's look: the page opens with the member companies as tiles (state, last run, next run, a silver work
// line while something of it runs; one that stands still says why and has a quiet «راه بینداز»), then the routines with their last seven
// runs as dots; the KPI charts and the week's experiment follow, and who fills which seat folds under «تعریف کارگروه». Facts are
// separated by the hairline and a count in a sentence is in Persian digits.

import Link from 'next/link';
import { useMemo } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { LinesChart } from '@/components/charts/charts';
import { GroupHeader, MemberHead, QUIET_ACTION, QuietLink, RunDots, StateWord, WhenAt, nextRun } from '@/components/look/group';
import { stagger } from '@/components/look/stagger';
import { Facts, Ltr, Sep, clock, faCount } from '@/components/look/text';
import { rruleFa } from '@/components/v14/bits';
import { Card, Empty, ErrorState, FilterChip, Pill, SectionTitle, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies, useEmployees } from '@/lib/api/hooks';
import {
  RUN_STATE, useExperiments, useGroup, useGroupActions, useGroupKpis, useGroupMembers, useGroupRuns, useGroups, type Group, type Membership,
} from '@/lib/api/v29';
import { companyColor } from '@/lib/company';
import { cx, jDate } from '@/lib/format';
import { EmployeeStateChip, FaPara, FaText, fig } from './bits';

const dayLabel = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { day: 'numeric', month: 'short', timeZone: 'Asia/Tehran' });

function useName() {
  const { data } = useCompanies();
  return { name: (code: string) => data?.find((c) => c.code === code)?.name_fa ?? code, companies: data };
}

// ------------------------------------------------------------------------------------------------------------------ the list --
export function GroupsList() {
  const q = useGroups();
  const { name } = useName();
  if (q.isLoading) return <div className="grid gap-4 lg:grid-cols-2">{Array.from({ length: 2 }, (_, i) => <Skeleton key={i} className="h-48 rounded-[16px]" />)}</div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (q.data === null) return <Card><Empty icon="companies" title="کارگروه‌ها بعد از به‌روزرسانی ستاد میایند" body="نخستینش «تولید محتوا و انتشار» است، برای هر شرکتی که صفحه دارد." /></Card>;
  const list = q.data ?? [];
  if (!list.length) return <Card><Empty icon="companies" title="هنوز کارگروهی نیست" /></Card>;
  return (
    <div className="grid items-start gap-3 lg:grid-cols-2">
      {list.map((g, i) => {
        const item = stagger(i);
        return (
          <Link key={g.key} href={`/groups/${g.key}`} className={cx('group min-w-0', item.className)} style={item.style} aria-label={`کارگروه ${g.title_fa}`}>
            <Card className="flex h-full flex-col gap-2.5 p-4 transition-colors group-hover:bg-hover">
              <div className="flex items-center gap-3">
                <span className="min-w-0 flex-1 text-[16px] font-semibold leading-7 text-ink">{g.title_fa}</span>
                <StateWord kind={g.state === 'on' ? 'on' : 'off'}>{g.state === 'on' ? 'روشن' : 'خاموش'}</StateWord>
              </div>
              <FaPara text={g.purpose_fa} className="text-[13px] leading-6 text-sec" />
              <span className="text-[12px] text-sec"><Facts>{`${faCount(g.seats.length)} جایگاه`}{`${faCount(g.routines.length)} روال`}{`${faCount(g.kpis.length)} شاخص`}</Facts></span>
              {g.members?.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {g.members.map((m) => (
                    <span key={m.company} className={cx('inline-flex h-7 items-center gap-1.5 rounded-full bg-tile px-2.5 text-[12px]', m.state === 'paused' ? 'text-muted' : 'text-sec')}>
                      <CompanyMark code={m.company} height={12} mono />{name(m.company)}{m.state === 'paused' ? '، ایستاده' : ''}
                    </span>
                  ))}
                </div>
              ) : null}
            </Card>
          </Link>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------------ one group --
/** When the group's next routine that is on runs. */
const soonest = (g: Group): string | null => g.routines.filter((r) => r.state === 'on').map((r) => nextRun(r.schedule)).filter((x): x is string => !!x).sort()[0] ?? null;

function Members({ g, list }: { g: Group; list: Membership[] }) {
  const toast = useToast();
  const act = useGroupActions(g.key);
  const runs = useGroupRuns(g.key, null);
  const { name } = useName();
  const next = g.state === 'on' ? soonest(g) : null;
  const turn = (company: string, state: 'on' | 'paused') => act.member.mutate({ company, state }, {
    onSuccess: (x) => toast({ tone: 'info', text: x.state === 'paused' ? `کارگروه در ${name(company)} متوقف شد؛ روال‌هایش اجرا نمیشوند.` : `کارگروه در ${name(company)} ادامه دارد.` }),
    onError: (e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'تغییر نکرد.' }),
  });
  return (
    <section className="flex flex-col gap-2.5" aria-label="شرکت‌های عضو">
      <SectionTitle title="شرکت‌های عضو" note={g.eligible === 'has_channel' ? 'هر شرکت فعالی که صفحه یا کانال دارد خودش عضو میشود' : 'همه‌ی شرکت‌های فعال'} />
      <ul className="grid items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
        {list.map((m, i) => {
          const filled = m.seats.filter((s) => s.employee).length;
          const busy = act.member.isPending && act.member.variables?.company === m.company;
          const item = stagger(i);
          return (
            <li key={m.company} {...item} data-member={m.company} className={cx('flex min-w-0 flex-col gap-2 rounded-[16px] bg-card p-4', item.className)}>
              <MemberHead m={{ company: m.company, name_fa: name(m.company), state: m.state }} runs={runs.data} next={m.state === 'on' ? next : null}
                onStart={() => turn(m.company, 'on')} starting={busy}
                action={m.state === 'on' ? <button type="button" disabled={busy} aria-label={`توقف عضویت ${name(m.company)}`} onClick={() => turn(m.company, 'paused')} className={QUIET_ACTION}>نگه دار</button> : null} />
              <div className="flex flex-wrap items-center gap-x-2 text-[12px] text-muted">
                <span className="min-w-0 flex-1"><Facts>{`عضو از ${jDate(m.joined_at)}`}{`${faCount(filled)} از ${faCount(m.seats.length)} جایگاه پر`}</Facts></span>
                <QuietLink href={`/companies/${m.company}?tab=readiness&group=${g.key}`}>آمادگی</QuietLink>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Seats({ g, list }: { g: Group; list: Membership[] }) {
  const { name } = useName();
  const emps = useEmployees({});
  const byCode = new Map((emps.data?.items ?? []).map((e) => [e.code, e]));
  return (
    <div className="flex flex-col gap-2" aria-label="جایگاه‌ها">
      <SectionTitle title="جایگاه‌ها و کسی که پر میکند" note="جای خالی را مدیرعامل در پاکت ماه، خودکار پر میکند" />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[440px] border-collapse text-[13px]">
          <thead><tr className="text-right text-[11px] text-muted"><th className="px-2 py-2 font-semibold">جایگاه</th>{list.map((m) => <th key={m.company} className="px-2 py-2 font-semibold"><span className="inline-flex items-center gap-1.5"><CompanyMark code={m.company} height={11} mono />{name(m.company)}</span></th>)}</tr></thead>
          <tbody>
            {g.seats.map((s) => (
              <tr key={s.seat} className="border-t border-div align-top">
                <td className="px-2 py-2.5 font-semibold">{s.title_fa}</td>
                {list.map((m) => {
                  const ms = m.seats.find((x) => x.seat === s.seat);
                  const code = ms?.employee ?? null;
                  const e = code ? byCode.get(code) : undefined;
                  const blocked = ms?.blocked;
                  return (
                    <td key={m.company} className="px-2 py-2.5">
                      {!code ? (
                        <span className="flex flex-col gap-0.5">
                          <span className="text-[12px] font-semibold text-sec">خالی</span>
                          {blocked ? <span className="text-[11px] leading-5 text-sec">{blocked.why_fa} {blocked.fix_fa}</span> : null}
                        </span>
                      ) : (
                        <Link href={`/employees/${code}`} className="flex flex-col items-start gap-1 hover:text-ink hover:underline">
                          <span className="text-[12px]">{e?.display_name ?? e?.title_fa ?? s.title_fa}</span>
                          {e ? <EmployeeStateChip code={code} e={e as { state?: string | null; activity?: string | null }} /> : null}
                        </Link>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Routines({ g, company }: { g: Group; company: string | null }) {
  const toast = useToast();
  const act = useGroupActions(g.key);
  const runs = useGroupRuns(g.key, company);
  const { name } = useName();
  const title = (k: string) => g.routines.find((r) => r.key === k)?.title_fa ?? k;
  const seat = (k: string) => g.seats.find((s) => s.seat === k)?.title_fa ?? k;
  const live = g.state === 'on';
  return (
    <section className="flex flex-col gap-2.5" aria-label="روال‌ها">
      <SectionTitle title="روال‌ها" note="هفت نوبت آخر هر روال؛ هر روال کار کوچکی برای همان جایگاه میسازد" />
      <ul className="flex flex-col divide-y divide-[var(--hq-line-divider)] rounded-[16px] bg-card px-4">
        {g.routines.map((r) => {
          const next = live && r.state === 'on' ? nextRun(r.schedule) : null;
          return (
            <li key={r.key} className="flex items-center gap-3 py-3" data-routine={r.key} data-state={r.state}>
              <span className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="flex items-center gap-3">
                  <b className={cx('min-w-0 flex-1 text-[14px] font-semibold leading-6', r.state === 'on' ? 'text-ink' : 'text-sec')}>{r.title_fa}</b>
                  {runs.data ? <RunDots runs={runs.data.filter((x) => x.routine === r.key)} label={r.title_fa} /> : null}
                </span>
                <span className="text-[12px] leading-5 text-sec">
                  <Facts>{seat(r.seat)}<span className="fig">{rruleFa(r.schedule)}</span>{r.state === 'on' ? (next ? <>نوبت بعد <WhenAt iso={next} /></> : null) : 'ایستاده'}</Facts>
                </span>
              </span>
              <Switch label={`${r.state === 'on' ? 'توقف' : 'ادامه'} روال ${r.title_fa}`} checked={r.state === 'on'} disabled={act.routine.isPending}
                onChange={(v) => act.routine.mutate({ routine: r.key, state: v ? 'on' : 'paused' }, { onError: (e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'تغییر نکرد.' }) })} />
            </li>
          );
        })}
      </ul>
      <details className="group rounded-[16px] bg-card" data-testid="run-history">
        <summary className="flex cursor-pointer select-none list-none items-center gap-2 px-4 py-3 text-[13px] font-semibold text-ink [&::-webkit-details-marker]:hidden">
          <span className="min-w-0 flex-1">سابقه‌ی اجرا</span>
          <Icon name="next" size={16} className="flex-none -rotate-90 text-muted transition-transform group-open:rotate-90" />
        </summary>
        <div className="px-4 pb-3" aria-label="سابقه‌ی اجرا">
          {runs.isLoading ? <Skeleton className="h-24" /> : runs.error ? <ErrorState error={runs.error} onRetry={() => runs.refetch()} /> : !runs.data?.length ? <p className="text-[12px] text-muted">هنوز اجرایی نیست.</p> : (
            <ol className="flex flex-col divide-y divide-[var(--hq-line-divider)]">
              {runs.data.slice(0, 12).map((x) => {
                const st = RUN_STATE[x.state] ?? { fa: x.state, tone: 'neutral' as const };
                return (
                  <li key={x.id} className="flex flex-col gap-0.5 py-2">
                    <span className="flex items-center gap-2 text-[13px]">
                      <CompanyMark code={x.company} height={11} mono />
                      <span className="min-w-0 flex-1"><span className="text-sec">{name(x.company)}</span><Sep /><span className="font-semibold">{title(x.routine)}</span></span>
                      <Pill tone={st.tone} dot className="h-5 text-[11px]">{st.fa}</Pill>
                    </span>
                    <span className="text-[11px] text-muted">{jDate(x.at)}، <Ltr>{clock(x.at)}</Ltr></span>
                    {x.note_fa ? <span className="text-[12px] leading-5 text-sec"><FaText text={x.note_fa} /></span> : null}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </details>
    </section>
  );
}

function Kpis({ g, company }: { g: Group; company: string | null }) {
  const q = useGroupKpis(g.key, company, 30);
  const { name, companies } = useName();
  const days = useMemo(() => [...new Set((q.data ?? []).flatMap((s) => s.series.map((p) => p.day)))].sort(), [q.data]);
  return (
    <Card className="flex flex-col gap-4 p-5" aria-label="شاخص‌ها">
      <SectionTitle title="شاخص‌ها" note="هر روز با کد از اتصال‌ها خوانده میشود؛ روز بی‌عدد خالی میماند، هرگز صفر" />
      {q.isLoading ? <Skeleton className="h-60" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.length ? <p className="text-[13px] text-muted">هنوز عددی نیامده؛ اتصال‌های شرکت‌ها را وصل کن.</p> : (
        g.kpis.map((k) => {
          const rows = (q.data ?? []).filter((s) => s.key === k.key);
          if (!rows.length) return null;
          const lines = rows.map((s) => ({
            key: s.company, color: companyColor(companies, s.company),
            label: <span className="flex items-center gap-1.5"><CompanyMark code={s.company} height={11} mono />{name(s.company)}</span>,
            values: days.map((d) => s.series.find((p) => p.day === d)?.value ?? null),
          }));
          return (
            <section key={k.key} className="flex flex-col gap-2" aria-label={k.title_fa}>
              <h3 className="text-[14px] font-semibold">{k.title_fa}</h3>
              <LinesChart label={`روند ${k.title_fa}`} days={days.map((d) => ({ key: d, label: dayLabel.format(new Date(`${d}T12:00:00Z`)) }))} lines={lines} fmt={(v) => fig(Math.round(v))} tick={(v) => (v < 10 && v % 1 ? v.toFixed(1) : fig(Math.round(v)))} height={200} />
            </section>
          );
        })
      )}
    </Card>
  );
}

function Experiments({ g, company }: { g: Group; company: string | null }) {
  const q = useExperiments(g.key, company);
  const { name } = useName();
  return (
    <Card className="flex flex-col gap-2 p-5" aria-label="آزمایش هفته">
      <SectionTitle title="آزمایش هفته" note="هر هفته برای هر شرکت یک آزمایش عمدی، با فرضیه و عدد هدف" />
      {q.isLoading ? <Skeleton className="h-24" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.length ? <p className="text-[13px] text-muted">این هفته آزمایشی نوشته نشده.</p> : (
        <ul className="flex flex-col gap-2">
          {q.data.map((x) => (
            <li key={x.id} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3">
              <span className="flex flex-wrap items-center gap-2 text-[12px] text-sec"><CompanyMark code={x.company} height={11} mono />{name(x.company)}<Ltr className="text-muted">{x.week}</Ltr>
                <span className="flex-1" />
                {x.result == null ? <Pill tone="lapis" dot>در جریان</Pill> : x.kept ? <Pill tone="pos" icon="seal">ماند</Pill> : <Pill tone="silver" dot>کنار رفت</Pill>}
              </span>
              <FaPara text={x.hypothesis_fa} className="text-[14px] font-semibold leading-7" />
              <span className="text-[12px] text-sec">معیار: {x.metric}؛ هدف <Ltr>{String(x.target)}</Ltr>{x.result != null ? <>؛ نتیجه <Ltr className="font-semibold text-ink">{String(x.result)}</Ltr></> : null}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function GroupDetail({ groupKey, company, onCompany }: { groupKey: string; company: string | null; onCompany: (c: string | null) => void }) {
  const q = useGroup(groupKey);
  const members = useGroupMembers(groupKey);
  const { name } = useName();
  const g = q.data;
  if (q.isLoading) return <><Skeleton className="h-16 w-2/3" /><Skeleton className="h-64 rounded-[16px]" /></>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!g) return <Card><Empty icon="companies" title="این کارگروه پیدا نشد" body="کارگروه‌ها بعد از به‌روزرسانی ستاد این‌جا میایند." /></Card>;
  const list = members.data ?? g.members ?? [];
  const shown = company ? list.filter((m) => m.company === company) : list;
  return (
    <div className="flex flex-col gap-5">
      <GroupHeader gap="-mb-5" eyebrow={<Link href="/groups" className="hover:text-ink">کارگروه‌ها</Link>} title={g.title_fa}
        state={<StateWord kind={g.state === 'on' ? 'on' : 'off'}>{g.state === 'on' ? 'روشن' : 'خاموش'}</StateWord>}>
        <FaPara text={g.purpose_fa} className="max-w-3xl text-[14px] leading-7 text-sec" />
      </GroupHeader>
      {members.isLoading ? <Skeleton className="h-40 rounded-[16px]" /> : <Members g={g} list={list} />}
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1" role="group" aria-label="شرکت">
        <FilterChip selected={!company} onClick={() => onCompany(null)}>همه</FilterChip>
        {list.map((m) => <FilterChip key={m.company} selected={company === m.company} onClick={() => onCompany(m.company)}><span className="flex items-center gap-1.5"><CompanyMark code={m.company} height={12} mono />{name(m.company)}</span></FilterChip>)}
      </div>
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div className="flex min-w-0 flex-col gap-5">
          <Routines g={g} company={company} />
          <Experiments g={g} company={company} />
        </div>
        <div className="flex min-w-0 flex-col gap-5">
          <Kpis g={g} company={company} />
          {/* Who fills which seat: the group's definition, folded until he wants it. */}
          <details className="group rounded-[16px] bg-card" data-testid="group-definition">
            <summary className="flex cursor-pointer select-none list-none items-center gap-2 px-4 py-3.5 text-[14px] font-semibold text-ink [&::-webkit-details-marker]:hidden">
              <span className="min-w-0 flex-1">تعریف کارگروه</span>
              <span className="text-[12px] font-normal text-muted"><Facts>{`${faCount(g.seats.length)} جایگاه`}{`${faCount(g.routines.length)} روال`}{`${faCount(g.kpis.length)} شاخص`}</Facts></span>
              <Icon name="next" size={16} className="flex-none -rotate-90 text-muted transition-transform group-open:rotate-90" />
            </summary>
            <div className="px-4 pb-4"><Seats g={g} list={shown} /></div>
          </details>
        </div>
      </div>
    </div>
  );
}
