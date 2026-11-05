'use client';

// ⟨1.11⟩ Contract §29.11 «کارگروه‌ها» (growth groups, defined as data): the list, and one group's page — its purpose, the member companies
// (pause and resume), the seats and who fills them (with each employee's state, §29.14), the routines and their run history (pause and
// resume), the KPI charts per company, and the week's experiment.

import Link from 'next/link';
import { useMemo } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { LinesChart } from '@/components/charts/charts';
import { rruleFa } from '@/components/v14/bits';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, SectionTitle, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies, useEmployees } from '@/lib/api/hooks';
import {
  RUN_STATE, useExperiments, useGroup, useGroupActions, useGroupKpis, useGroupMembers, useGroupRuns, useGroups, type Group, type Membership,
} from '@/lib/api/v29';
import { companyColor } from '@/lib/company';
import { cx, jDate, jTime } from '@/lib/format';
import { EmployeeStateChip, FaPara, FaText, fig } from './bits';

const dayLabel = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { day: 'numeric', month: 'short', timeZone: 'Asia/Tehran' });
const MEMBER: Record<Membership['state'], { fa: string; tone: 'pos' | 'warn' }> = { on: { fa: 'فعال', tone: 'pos' }, paused: { fa: 'متوقف', tone: 'warn' } };

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
    <div className="grid items-start gap-4 lg:grid-cols-2">
      {list.map((g) => (
        <Link key={g.key} href={`/groups/${g.key}`} className="group min-w-0" aria-label={`کارگروه ${g.title_fa}`}>
          <Card className="flex h-full flex-col gap-3 p-5 transition-colors group-hover:bg-tile">
            <div className="flex items-center gap-2">
              <span className="flex size-10 items-center justify-center rounded-[12px] bg-gold-soft text-gold-ink"><Icon name="companies" size={20} /></span>
              <span className="flex-1 text-[16px] font-semibold">{g.title_fa}</span>
              <Pill tone={g.state === 'on' ? 'pos' : 'silver'} dot>{g.state === 'on' ? 'روشن' : 'خاموش'}</Pill>
            </div>
            <FaPara text={g.purpose_fa} className="text-[13px] leading-6 text-sec" />
            <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
              <span><span className="fig">{g.seats.length}</span> جایگاه</span>·<span><span className="fig">{g.routines.length}</span> روال</span>·<span><span className="fig">{g.kpis.length}</span> شاخص</span>
            </div>
            {g.members?.length ? (
              <div className="flex flex-wrap gap-1.5">
                {g.members.map((m) => (
                  <span key={m.company} className={cx('inline-flex h-7 items-center gap-1.5 rounded-full bg-tile px-2.5 text-[12px]', m.state === 'paused' && 'text-muted')}>
                    <CompanyMark code={m.company} height={12} mono />{name(m.company)}{m.state === 'paused' ? ' (متوقف)' : ''}
                  </span>
                ))}
              </div>
            ) : null}
          </Card>
        </Link>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------------ one group --
function Members({ g, list, onPick }: { g: Group; list: Membership[]; onPick: (c: string) => void }) {
  const toast = useToast();
  const act = useGroupActions(g.key);
  const { name } = useName();
  return (
    <Card className="flex flex-col gap-2 p-5" aria-label="شرکت‌های عضو">
      <SectionTitle title="شرکت‌های عضو" note={g.eligible === 'has_channel' ? 'هر شرکت فعالی که صفحه یا کانال دارد خودش عضو میشود' : 'همه‌ی شرکت‌های فعال'} />
      <ul className="flex flex-col">
        {list.map((m) => {
          const filled = m.seats.filter((s) => s.employee).length;
          const st = MEMBER[m.state] ?? MEMBER.on;
          const busy = act.member.isPending && act.member.variables?.company === m.company;
          return (
            <li key={m.company} className="flex flex-wrap items-center gap-3 border-t border-div py-3 first:border-0">
              <button type="button" onClick={() => onPick(m.company)} className="flex min-w-0 flex-[1_1_12rem] items-center gap-2 text-start">
                <CompanyMark code={m.company} height={14} mono />
                <span className="flex min-w-0 flex-col">
                  <span className="text-[14px] font-semibold">{name(m.company)}</span>
                  <span className="text-[11px] text-muted">عضو از {jDate(m.joined_at)}؛ <span className="fig">{filled}</span> از <span className="fig">{m.seats.length}</span> جایگاه پر</span>
                </span>
              </button>
              <Pill tone={st.tone} dot>{st.fa}</Pill>
              <Link href={`/companies/${m.company}?tab=readiness&group=${g.key}`} className="text-[12px] font-semibold text-gold-ink hover:underline">آمادگی</Link>
              <Button size="sm" variant="secondary" icon={m.state === 'on' ? 'pause' : 'resume'} loading={busy} aria-label={`${m.state === 'on' ? 'توقف' : 'ادامه'} عضویت ${name(m.company)}`}
                onClick={() => act.member.mutate({ company: m.company, state: m.state === 'on' ? 'paused' : 'on' }, {
                  onSuccess: (x) => toast({ tone: 'info', text: x.state === 'paused' ? `کارگروه در ${name(m.company)} متوقف شد؛ روال‌هایش اجرا نمیشوند.` : `کارگروه در ${name(m.company)} ادامه دارد.` }),
                  onError: (e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'تغییر نکرد.' }),
                })}>{m.state === 'on' ? 'توقف' : 'ادامه'}</Button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function Seats({ g, list }: { g: Group; list: Membership[] }) {
  const { name } = useName();
  const emps = useEmployees({});
  const byCode = new Map((emps.data?.items ?? []).map((e) => [e.code, e]));
  return (
    <Card className="flex flex-col gap-2 p-5" aria-label="جایگاه‌ها">
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
                          <span className="text-[12px] text-warn">خالی</span>
                          {blocked ? <span className="text-[11px] leading-5 text-warn">{blocked.why_fa} {blocked.fix_fa}</span> : null}
                        </span>
                      ) : (
                        <Link href={`/employees/${code}`} className="flex flex-col items-start gap-1 hover:text-gold-ink">
                          <span className="text-[12px]">{e?.display_name ?? e?.title_fa ?? s.title_fa}</span>
                          {e ? <EmployeeStateChip e={e as { state?: string | null; activity?: string | null }} /> : null}
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
    </Card>
  );
}

function Routines({ g, company }: { g: Group; company: string | null }) {
  const toast = useToast();
  const act = useGroupActions(g.key);
  const runs = useGroupRuns(g.key, company);
  const { name } = useName();
  const title = (k: string) => g.routines.find((r) => r.key === k)?.title_fa ?? k;
  const seat = (k: string) => g.seats.find((s) => s.seat === k)?.title_fa ?? k;
  return (
    <Card className="flex flex-col gap-3 p-5" aria-label="روال‌ها">
      <SectionTitle title="روال‌ها" note="هر روال کار کوچکی برای همان جایگاه میسازد؛ مدل فقط در اجرای کارمند، در سقف خودش" />
      <ul className="flex flex-col">
        {g.routines.map((r) => (
          <li key={r.key} className="flex flex-wrap items-center gap-3 border-t border-div py-2.5 first:border-0">
            <span className="flex min-w-0 flex-[1_1_12rem] flex-col">
              <span className="text-[14px] font-semibold">{r.title_fa}</span>
              <span className="text-[11px] text-muted">{seat(r.seat)} · <span className="fig">{rruleFa(r.schedule)}</span> به وقت تهران</span>
            </span>
            <Pill tone={r.state === 'on' ? 'pos' : 'warn'} dot>{r.state === 'on' ? 'روشن' : 'متوقف'}</Pill>
            <Switch label={`${r.state === 'on' ? 'توقف' : 'ادامه'} روال ${r.title_fa}`} checked={r.state === 'on'} disabled={act.routine.isPending}
              onChange={(v) => act.routine.mutate({ routine: r.key, state: v ? 'on' : 'paused' }, { onError: (e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'تغییر نکرد.' }) })} />
          </li>
        ))}
      </ul>
      <div className="flex flex-col gap-1 border-t border-div pt-3" aria-label="سابقه‌ی اجرا">
        <h3 className="text-[13px] font-semibold text-sec">سابقه‌ی اجرا</h3>
        {runs.isLoading ? <Skeleton className="h-24" /> : runs.error ? <ErrorState error={runs.error} onRetry={() => runs.refetch()} /> : !runs.data?.length ? <p className="text-[12px] text-muted">هنوز اجرایی نیست.</p> : (
          <ol className="flex flex-col">
            {runs.data.slice(0, 12).map((x) => {
              const st = RUN_STATE[x.state] ?? { fa: x.state, tone: 'neutral' as const };
              return (
                <li key={x.id} className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2">
                  <span className="fig w-[88px] flex-none text-[11px] text-muted">{jDate(x.at)} {jTime(x.at)}</span>
                  <span className="flex min-w-0 flex-[1_1_14rem] flex-col gap-0.5">
                    <span className="flex items-center gap-1.5 text-[13px]"><CompanyMark code={x.company} height={11} mono /><span className="text-sec">{name(x.company)}</span> · <span className="font-semibold">{title(x.routine)}</span></span>
                    {x.note_fa ? <span className="text-[12px] leading-5 text-sec"><FaText text={x.note_fa} /></span> : null}
                  </span>
                  <Pill tone={st.tone} dot className="h-5 text-[11px]">{st.fa}</Pill>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </Card>
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
              <span className="flex flex-wrap items-center gap-2 text-[12px] text-sec"><CompanyMark code={x.company} height={11} mono />{name(x.company)}<span className="fig text-muted">{x.week}</span>
                <span className="flex-1" />
                {x.result == null ? <Pill tone="lapis" dot>در جریان</Pill> : x.kept ? <Pill tone="pos" icon="seal">ماند</Pill> : <Pill tone="silver" dot>کنار رفت</Pill>}
              </span>
              <FaPara text={x.hypothesis_fa} className="text-[14px] font-semibold leading-7" />
              <span className="text-[12px] text-sec">معیار: {x.metric}؛ هدف <span className="fig">{String(x.target)}</span>{x.result != null ? <>؛ نتیجه <span className="fig font-semibold text-ink">{String(x.result)}</span></> : null}</span>
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
    <>
      <PageHeader eyebrow={<Link href="/groups" className="hover:text-ink">کارگروه‌ها</Link>} title={g.title_fa} actions={<Pill tone={g.state === 'on' ? 'pos' : 'silver'} dot>{g.state === 'on' ? 'روشن' : 'خاموش'}</Pill>}>
        <FaPara text={g.purpose_fa} className="max-w-3xl text-[14px] leading-7 text-sec" />
      </PageHeader>
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1" role="group" aria-label="شرکت">
        <FilterChip selected={!company} onClick={() => onCompany(null)}>همه</FilterChip>
        {list.map((m) => <FilterChip key={m.company} selected={company === m.company} onClick={() => onCompany(m.company)}><span className="flex items-center gap-1.5"><CompanyMark code={m.company} height={12} mono />{name(m.company)}</span></FilterChip>)}
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Kpis g={g} company={company} />
          <Seats g={g} list={shown} />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          {members.isLoading ? <Skeleton className="h-40 rounded-[16px]" /> : <Members g={g} list={list} onPick={(c) => onCompany(c)} />}
          <Routines g={g} company={company} />
          <Experiments g={g} company={company} />
        </div>
      </div>
    </>
  );
}
