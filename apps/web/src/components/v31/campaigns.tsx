'use client';

// ⟨1.13⟩ Contract §31.5 one campaign calendar for every company: lines (§30), newsletters, ads, campaigns and manual items by day, with
// conflicts marked (two posts too close on one channel, a holiday), the kind as a filter (the lines view is the «خط تولید» filter), and
// the campaigns themselves added and edited here. A hub without `/campaign-calendar` falls back to the lines-only calendar.

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, FilterChip, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { useCompanies } from '@/lib/api/hooks';
import { LINE_STATE_FA, PLATFORM_FA, RUN_STATE_FA, platformFa, type LineState, type RunState } from '@/lib/api/v30';
import { CAMPAIGN_KIND_FA, useCampaignActions, useCampaignCalendar, useCampaigns, type Campaign, type CampaignItem, type CampaignKind } from '@/lib/api/v31';
import { OWNER_TZ, cx, jDate, jTime, jWeekday } from '@/lib/format';
import { FaPara, FaText, fig } from '@/components/v29/text';
import { errText, field } from './kit';

const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (d: string, n: number) => iso(new Date(Date.parse(`${d}T12:00:00Z`) + n * 86_400_000));
const noon = (d: string) => `${d}T12:00:00Z`;
/** Today as the owner's (Tehran) calendar day, not the UTC one. */
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: OWNER_TZ }).format(new Date());
const HREF: Record<CampaignKind, (ref: string) => string | null> = { line: (r) => `/lines/${r}`, newsletter: () => null, ad: () => null, campaign: () => null, manual: () => null };

function StateOf({ it }: { it: CampaignItem }) {
  const r = RUN_STATE_FA[it.state as RunState];
  if (r) return <Pill tone={r.tone} dot={!r.live} live={r.live}>{r.fa}</Pill>;
  const l = LINE_STATE_FA[it.state as LineState];
  return l ? <Pill tone={l.tone} dot>{l.fa}</Pill> : <Pill>{it.state}</Pill>;
}

export function CampaignCalendar() {
  const [from, setFrom] = useState(() => today());
  const [company, setCompany] = useState<string | null>(null);
  const [kind, setKind] = useState<CampaignKind | null>(null);
  const to = addDays(from, 6);
  const q = useCampaignCalendar(from, to, company);
  const cs = useCompanies();
  const name = (code: string) => cs.data?.find((c) => c.code === code)?.name_fa ?? code;
  const days = useMemo(() => {
    const by = new Map<string, CampaignItem[]>();
    for (const it of q.data?.items ?? []) if (!kind || it.kind === kind) by.set(it.day, [...(by.get(it.day) ?? []), it]);
    return [...by.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [q.data, kind]);
  const conflicts = (q.data?.items ?? []).filter((i) => i.conflict_fa).length;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" icon="next" aria-label="هفته‌ی قبل" className="[&_svg]:rotate-180" onClick={() => setFrom(addDays(from, -7))} />
        <span className="min-w-0 flex-1 text-center text-[14px] font-semibold">{jDate(noon(from), true)} تا {jDate(noon(to), true)}</span>
        <Button size="sm" icon="back" aria-label="هفته‌ی بعد" className="[&_svg]:rotate-180" onClick={() => setFrom(addDays(from, 7))} />
        <Button size="sm" onClick={() => setFrom(today())}>امروز</Button>
      </div>
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1" role="group" aria-label="شرکت">
        <FilterChip selected={company === null} onClick={() => setCompany(null)}>همه‌ی شرکت‌ها</FilterChip>
        {(cs.data ?? []).filter((c) => c.code !== 'HQ').map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => setCompany(c.code)}>{c.name_fa ?? c.code}</FilterChip>)}
      </div>
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1" role="group" aria-label="نوع">
        <FilterChip selected={kind === null} onClick={() => setKind(null)}>همه</FilterChip>
        {(Object.keys(CAMPAIGN_KIND_FA) as CampaignKind[]).map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{CAMPAIGN_KIND_FA[k]}</FilterChip>)}
      </div>
      {conflicts ? <div className="rounded-[12px] bg-warn-soft px-4 py-2.5 text-[13px]" role="status"><span className="fig">{conflicts}</span> تداخل در این هفته؛ زیر هر مورد دلیلش نوشته شده.</div> : null}
      {q.isLoading ? <Skeleton className="h-64 rounded-[16px]" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data === null ? (
        <Card><Empty icon="planner" title="تقویم کمپین بعد از به‌روزرسانی ستاد میاید" body="خط‌ها، خبرنامه، تبلیغ و کمپین‌ها همه در یک تقویم." /></Card>
      ) : !days.length ? (
        <Card><Empty icon="planner" title="این هفته چیزی نیست" body="زمان‌بندی خط‌ها را از صفحه‌ی هر خط بگذار یا پایین کمپین تازه بساز." /></Card>
      ) : (
        <div className="flex flex-col gap-3">
          {days.map(([day, items]) => (
            <Card key={day} as="section" className="hq-rise flex flex-col gap-1 p-4" aria-label={`روز ${jDate(noon(day))}`}>
              <h2 className="pb-1 text-[14px] font-semibold">{jWeekday(noon(day))}، {jDate(noon(day))}</h2>
              <ul className="flex flex-col">
                {[...items].sort((a, b) => (a.at ?? '').localeCompare(b.at ?? '')).map((it, i) => {
                  const href = HREF[it.kind](it.ref);
                  return (
                    <li key={`${it.ref}-${i}`} className={cx('flex flex-col gap-1 border-t border-div py-2.5 first:border-0', it.conflict_fa && 'rounded-[10px] bg-warn-soft px-2')}>
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="fig w-12 text-[13px] font-semibold">{it.at ? jTime(it.at) : '—'}</span>
                        <span className="inline-flex min-w-0 flex-[1_1_10rem] items-center gap-2 text-[13px]"><CompanyMark code={it.company} height={12} mono />{name(it.company)}{it.platform ? <span className="text-muted">· {PLATFORM_FA[it.platform] ?? platformFa(it.platform)}</span> : null}</span>
                        <Pill tone="silver">{CAMPAIGN_KIND_FA[it.kind] ?? it.kind}</Pill>
                        {href ? <Link href={href} className="text-[12px] font-semibold text-gold-ink hover:underline"><FaText text={it.title_fa} /></Link> : <span className="text-[12px] font-semibold"><FaText text={it.title_fa} /></span>}
                        <StateOf it={it} />
                      </div>
                      {it.conflict_fa ? <FaPara text={it.conflict_fa} className="text-[12px] leading-5 text-warn" /> : null}
                    </li>
                  );
                })}
              </ul>
            </Card>
          ))}
        </div>
      )}
      {q.data && !q.data.lines_only ? <Campaigns /> : null}
    </div>
  );
}

const EMPTY: Omit<Campaign, 'id'> = { company: '', title_fa: '', goal_fa: '', starts: today(), ends: addDays(today(), 14), channels: [], budget: null, state: 'planned' };

function Campaigns() {
  const q = useCampaigns();
  const act = useCampaignActions();
  const cs = useCompanies();
  const toast = useToast();
  const [f, setF] = useState<(Omit<Campaign, 'id'> & { id?: string }) | null>(null);
  const name = (code: string) => cs.data?.find((c) => c.code === code)?.name_fa ?? code;
  const save = () => {
    if (!f) return;
    const done = { onSuccess: () => setF(null), onError: (e: unknown) => toast({ tone: 'error', text: errText(e, 'ذخیره نشد.') }) };
    if (f.id) act.edit.mutate({ ...f, id: f.id }, done); else act.add.mutate(f, done);
  };
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="کمپین‌ها">
      <SectionTitle title="کمپین‌ها" note="یک هدف، یک بازه، چند کانال" action={<Button size="sm" variant="primary" icon="add" onClick={() => setF({ ...EMPTY, company: (cs.data ?? []).find((c) => c.code !== 'HQ')?.code ?? '' })}>کمپین تازه</Button>} />
      {f ? (
        <div className="hq-rise flex flex-col gap-3 rounded-[12px] bg-tile p-4" aria-label="مشخصات کمپین">
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="شرکت کمپین">{(cs.data ?? []).filter((c) => c.code !== 'HQ').map((c) => (
            <button key={c.code} type="button" role="radio" aria-checked={f.company === c.code} disabled={!!f.id && f.company !== c.code} onClick={() => setF({ ...f, company: c.code })} className={cx('h-9 rounded-full px-3.5 text-[13px] font-semibold disabled:opacity-40', f.company === c.code ? 'bg-gold text-on-gold' : 'bg-card text-sec')}>{c.name_fa ?? c.code}</button>
          ))}</div>
          <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">نام کمپین</span><input value={f.title_fa} onChange={(e) => setF({ ...f, title_fa: e.target.value })} aria-label="نام کمپین" className={cx(field, 'h-10')} /></label>
          <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">هدف</span><input value={f.goal_fa} onChange={(e) => setF({ ...f, goal_fa: e.target.value })} aria-label="هدف کمپین" className={cx(field, 'h-10')} /></label>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">شروع</span><input type="date" value={f.starts} dir="ltr" onChange={(e) => setF({ ...f, starts: e.target.value })} aria-label="شروع کمپین" className={cx(field, 'h-10 text-left')} /></label>
            <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">پایان</span><input type="date" value={f.ends} dir="ltr" onChange={(e) => setF({ ...f, ends: e.target.value })} aria-label="پایان کمپین" className={cx(field, 'h-10 text-left')} /></label>
            <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">بودجه (اختیاری)</span><input type="number" min={0} value={f.budget ?? ''} dir="ltr" onChange={(e) => setF({ ...f, budget: e.target.value === '' ? null : Number(e.target.value) })} aria-label="بودجه‌ی کمپین" className={cx(field, 'h-10 text-left')} /></label>
          </div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="کانال‌ها">{Object.keys(PLATFORM_FA).map((p) => (
            <button key={p} type="button" aria-pressed={f.channels.includes(p)} onClick={() => setF({ ...f, channels: f.channels.includes(p) ? f.channels.filter((x) => x !== p) : [...f.channels, p] })}
              className={cx('h-8 rounded-full px-3 text-[12px] font-semibold', f.channels.includes(p) ? 'bg-gold text-on-gold' : 'bg-card text-sec')}>{PLATFORM_FA[p]}</button>
          ))}</div>
          <div className="flex gap-2"><Button variant="primary" loading={act.add.isPending || act.edit.isPending} disabled={!f.company || !f.title_fa.trim()} onClick={save}>ذخیره</Button><Button onClick={() => setF(null)}>بی‌خیال</Button></div>
        </div>
      ) : null}
      {q.isLoading ? <Skeleton className="h-16" /> : !(q.data ?? []).length ? <p className="text-[13px] text-muted">هنوز کمپینی نیست.</p> : (
        <ul className="flex flex-col">{(q.data ?? []).map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-3 border-t border-div py-3 first:border-0" aria-label={`کمپین ${c.title_fa}`}>
            <span className="flex min-w-0 flex-[1_1_12rem] flex-col"><span className="text-[14px] font-semibold"><FaText text={c.title_fa} /></span>
              <span className="text-[11px] text-muted">{name(c.company)} · {jDate(noon(c.starts))} تا {jDate(noon(c.ends))}{c.budget != null ? <> · بودجه <span className="fig">{fig(c.budget)}</span></> : null}</span></span>
            <Button size="sm" aria-label={`ویرایش ${c.title_fa}`} onClick={() => setF({ ...c })}>ویرایش</Button>
            <Button size="sm" aria-label={`حذف ${c.title_fa}`} onClick={() => act.remove.mutate(c.id, { onError: (e) => toast({ tone: 'error', text: errText(e, 'حذف نشد.') }) })}>حذف</Button>
          </li>
        ))}</ul>
      )}
    </Card>
  );
}
