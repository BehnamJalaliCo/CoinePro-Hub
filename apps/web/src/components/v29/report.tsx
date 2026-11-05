'use client';

// ⟨1.11⟩ Contract §29.2 «گزارش فرمان»: every order is answered. Its state; the receipt and the plan (who took it, by when); the route the
// secretary chose; each blocker with its one-tap fix; the steps in plain Persian; the outputs; and at the end «چه شد / چه ماند / از شما چه
// لازم است». Live: the stream's `order.report` reads it again.

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Card, Empty, ErrorState, PageHeader, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { Button } from '@/components/ui/button';
import { useCompanies } from '@/lib/api/hooks';
import {
  BLOCKER_ICON, ENDED_ORDER, OUTPUT_KIND_FA, orderSummaryFa, unitsFa, useOrderFix, useOrderItems, useOrderReport, type Blocker, type OrderReport, type OrderRouteFields, type OutputKind,
} from '@/lib/api/v29';
import { playerFa } from '@/lib/api/v28';
import { DEPT_FA } from '@/lib/labels';
import { useLive } from '@/lib/live';
import { useNow } from '@/lib/store';
import { ago, cx, jDate, jDateTime, jTime } from '@/lib/format';
import { ownerDay } from '@/components/v21/bits';
import { KitFlow } from '@/components/v31/kit';
import { SplitParts, WorkspaceCard } from '@/components/v33/parallel';
import type { OrderParallel } from '@/lib/api/v33';
import { FaPara, FaText, FixButton, OrderStatePill } from './bits';

function useNames() {
  const { data } = useCompanies();
  return (code: string) => data?.find((c) => c.code === code)?.name_fa ?? code;
}

/** The secretary's route in words: «تریدیار/رسانه + پرو-چارت؛ خروجی: ریلز؛ بودجه: 400 هزار واحد؛ تک‌نفره، خودکار». */
export function RouteLine({ r, count }: { r: OrderRouteFields; count?: number | null }) {
  const name = useNames();
  const lead = r.companies[0];
  return (
    <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[13px] leading-6 text-ink">
      <span className="text-muted">→</span>
      {lead ? <span className="inline-flex items-center gap-1"><CompanyMark code={lead} height={12} mono />{name(lead)}{r.department ? `/${DEPT_FA[r.department] ?? r.department}` : ''}</span> : null}
      {r.companies.slice(1).concat(r.collaborators).length ? <span className="text-sec">+ {r.companies.slice(1).concat(r.collaborators).map(name).join('، ')}</span> : null}
      <span className="text-muted">؛</span>
      <span>خروجی: {count ? <span className="fig">{count}</span> : null} {OUTPUT_KIND_FA[r.output_kind as OutputKind] ?? r.output_kind}</span>
      <span className="text-muted">؛</span>
      <span>بودجه: <FaText text={`${unitsFa(r.budget_tokens)} واحد`} /></span>
      <span className="text-muted">؛</span>
      <span>{r.mode === 'council' ? 'شورای مشاوران' : 'تک‌نفره'}، {playerFa(r.player)}</span>
    </span>
  );
}

function BlockerRow({ b, company, run }: { b: Blocker; company: string | null; run: (f: NonNullable<Blocker['fix']>) => Promise<unknown> }) {
  const now = useNow();
  return (
    <li className="flex flex-wrap items-start gap-3 rounded-[12px] bg-neg-soft p-3">
      <span className="mt-0.5 flex size-8 flex-none items-center justify-center rounded-full bg-[var(--hq-surface-card)] text-neg"><Icon name={BLOCKER_ICON[b.kind] ?? 'urgent'} size={16} /></span>
      <div className="flex min-w-0 flex-[1_1_14rem] flex-col gap-0.5">
        <span className="text-[14px] font-semibold text-ink"><FaText text={b.title_fa} /></span>
        <FaPara text={b.detail_fa} className="text-[13px] leading-6 text-sec" />
        <span className="text-[11px] text-muted">از {now ? ago(b.since, now) : jTime(b.since)}</span>
      </div>
      {b.fix ? <FixButton fix={b.fix} company={company} run={run} /> : null}
    </li>
  );
}

function Steps({ r }: { r: OrderReport }) {
  if (!r.steps.length) return null;
  return (
    <Card className="flex flex-col gap-2 p-5">
      <SectionTitle title="روند کار" note="به زبان ساده، تازه‌ترین پایین" />
      <ol className="flex flex-col">
        {r.steps.map((s, i) => {
          const day = ownerDay(s.at);
          const head = i === 0 || ownerDay(r.steps[i - 1]!.at) !== day;
          return (
            <li key={`${s.at}-${i}`} className="flex flex-col">
              {head ? <span className={cx('pb-1 text-[11px] font-semibold text-muted', i > 0 && 'pt-2')}>{jDate(s.at)}</span> : null}
              <span className="flex items-start gap-2 py-1">
                <span className="fig w-10 flex-none pt-0.5 text-[11px] text-muted">{jTime(s.at)}</span>
                <span className={cx('mt-2 size-2 flex-none rounded-full', i === r.steps.length - 1 ? 'bg-gold-ink' : 'bg-silver-ink')} />
                <span className="min-w-0 flex-1 text-[13px] leading-6"><span className="font-semibold">{s.who_fa}</span>: <FaText text={s.what_fa} /></span>
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

/** «فرمان‌ها و جوابشان» on the orders page: every spoken or written order with its ⟨1.11⟩ state and one line, each opening its report. */
export function OrderReportsCard() {
  const q = useOrderItems();
  const [all, setAll] = useState(false);
  const list = q.data ?? [];
  if (q.isLoading) return <Skeleton className="h-40 rounded-[16px]" />;
  if (q.error || !list.length) return null;
  const shown = all ? list : list.slice(0, 5);
  return (
    <Card className="flex flex-col gap-1 p-4" aria-label="فرمان‌ها و جوابشان">
      <SectionTitle title="فرمان‌ها و جوابشان" note="هر فرمان: رسید، برنامه، گیر و رفع، خروجی و جمع‌بندی" />
      <ul className="flex flex-col">
        {shown.map((o) => {
          const line = orderSummaryFa(o);
          return (
            <li key={o.ref} className="border-t border-div first:border-0">
              <Link href={`/orders/${o.ref}`} className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2.5 hover:bg-hover/40">
                <span className="mt-1 text-muted"><Icon name={o.source === 'voice' ? 'mic' : 'edit'} size={14} /></span>
                <span className="flex min-w-0 flex-[1_1_16rem] flex-col gap-0.5">
                  <span className="line-clamp-2 text-[13px] font-semibold leading-6"><FaText text={o.text_fa ?? o.text} /></span>
                  {line ? <span className="line-clamp-1 text-[12px] text-sec"><FaText text={line} /></span> : null}
                </span>
                {o.state ? <OrderStatePill state={o.state} /> : null}
              </Link>
            </li>
          );
        })}
      </ul>
      {list.length > 5 ? <Button variant="text" size="sm" className="self-start" onClick={() => setAll(!all)}>{all ? 'کمتر' : 'همه'}</Button> : null}
    </Card>
  );
}

/** ⟨1.13⟩ §31.2: a «new company» order — the kit's form, preview and seal. The result stays on screen after the report refreshes as sealed. */
function KitCard({ refId, kit }: { refId: string; kit: NonNullable<OrderReport['kit']> }) {
  const [made, setMade] = useState(false);
  return (
    <section id="kit-card" className="flex scroll-mt-24 flex-col gap-3" aria-label="شرکت آماده">
      <SectionTitle title="شرکت آماده" note={kit.sealed && !made ? 'این شرکت ساخته شده' : 'کد و نام را بنویس، پیش‌نمایش را ببین و مُهر بزن'} />
      {kit.sealed && !made ? <Card className="p-5 text-[13px] text-sec">شرکت «{kit.name_fa ?? kit.title_fa}» با این فرمان ساخته شد.</Card> : <KitFlow kit={kit.summary} order={refId} nameFa={kit.name_fa} onStart={() => setMade(true)} />}
    </section>
  );
}

/** The whole report of one order. */
export function OrderReportView({ refId }: { refId: string }) {
  const q = useOrderReport(refId);
  const fix = useOrderFix(refId);
  const { state: live } = useLive();
  const name = useNames();
  const now = useNow();
  if (q.isLoading) return <><Skeleton className="h-16 w-2/3" /><Skeleton className="h-48 rounded-[16px]" /><Skeleton className="h-64 rounded-[16px]" /></>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const r = q.data;
  if (!r) {
    return (
      <>
        <PageHeader eyebrow={<Link href="/orders" className="hover:text-ink">فرمان‌های من</Link>} title="گزارش فرمان" />
        <Card><Empty icon="command" title="گزارش این فرمان هنوز آماده نیست" body="ستاد هر فرمان را ظرف ده دقیقه با رسید و برنامه جواب میدهد؛ بعد از به‌روزرسانی ستاد گزارشش این‌جا میاید." action={<Button variant="secondary" icon="next" onClick={() => history.back()}>بازگشت</Button>} /></Card>
      </>
    );
  }
  const company = r.route?.companies[0] ?? r.ack?.assigned[0]?.company ?? null;
  const run = (f: NonNullable<Blocker['fix']>) => fix.mutateAsync(f);
  const ended = ENDED_ORDER.has(r.state);
  const needFix = r.blockers.find((b) => b.fix)?.fix ?? null;
  return (
    <>
      <PageHeader eyebrow={<Link href="/orders" className="hover:text-ink">فرمان‌های من ← گزارش فرمان</Link>} title={<FaText text={r.text_fa} />}>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <OrderStatePill state={r.state} />
          {!ended ? (live === 'live' ? <Pill tone="pos" live>زنده</Pill> : <Pill tone="neutral" dot>در حال وصل</Pill>) : null}
          <span className="text-[12px] text-muted">داده شد {jDateTime(r.at)}؛ آخرین تغییر {now ? ago(r.updated_at, now) : jTime(r.updated_at)}</span>
        </div>
      </PageHeader>

      {r.summary ? (
        <Card className="tahrir flex flex-col gap-4 p-5" aria-label="جمع‌بندی پایان فرمان">
          <SectionTitle title="جمع‌بندی" note="پایان فرمان، به زبان ساده" />
          <div className="grid gap-3 md:grid-cols-3">
            {([['چه شد', r.summary.done_fa, 'seal', 'text-pos'], ['چه ماند', r.summary.left_fa, 'time', 'text-warn'], ['از شما چه لازم است', r.summary.need_fa, 'owner', 'text-gold-ink']] as const).map(([t, v, icon, tint]) => (
              <section key={t} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
                <h3 className={cx('flex items-center gap-1.5 text-[13px] font-semibold', tint)}><Icon name={icon} size={15} />{t}</h3>
                {v ? <FaPara text={v} className="text-[13px] leading-6 text-ink" /> : <p className="text-[13px] text-muted">—</p>}
                {t === 'از شما چه لازم است' && v && needFix ? <FixButton fix={needFix} company={company} run={run} className="self-start" /> : null}
              </section>
            ))}
          </div>
        </Card>
      ) : null}

      {r.kit ? <KitCard refId={refId} kit={r.kit} /> : null}

      {/* ⟨1.15⟩ §33.7 and §33.10: the parallel parts with their merge, and the workspace on the company's own server. */}
      <SplitParts r={r as OrderParallel} />
      <WorkspaceCard r={r as OrderParallel} />

      {r.blockers.length ? (
        <Card className="flex flex-col gap-3 p-5 ring-1 ring-[var(--hq-neg-line)]" aria-label="گیرها">
          <SectionTitle title="کجا گیر کرده" note="هر گیر با دکمه‌ی رفعش؛ یک ضربه کافی است" />
          <ul className="flex flex-col gap-2">{r.blockers.map((b, i) => <BlockerRow key={`${b.kind}-${i}`} b={b} company={company} run={run} />)}</ul>
        </Card>
      ) : null}

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex flex-col gap-3 p-5" aria-label="رسید و برنامه">
            <SectionTitle title="رسید و برنامه" note={r.ack ? `${r.ack.by.display_fa ?? 'ستاد'}، ${jDateTime(r.ack.at)}` : 'هر فرمان ظرف ده دقیقه رسید و برنامه میگیرد'} />
            {r.ack ? (
              <>
                <FaPara text={r.ack.plan_fa} className="text-[14px] leading-7 text-ink" />
                {r.ack.assigned.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {r.ack.assigned.map((a) => (
                      <Link key={a.code} href={`/employees/${a.code}`} className="inline-flex h-8 items-center gap-1.5 rounded-full bg-tile px-3 text-[12px] hover:bg-hover">
                        <CompanyMark code={a.company} height={12} mono />{a.title_fa}<span className="text-muted">· {name(a.company)}</span>
                      </Link>
                    ))}
                  </div>
                ) : null}
                {r.ack.due_at ? <span className="flex items-center gap-1.5 text-[12px] text-sec"><Icon name="time" size={14} />موعد: {jDateTime(r.ack.due_at)} به وقت تهران</span> : null}
              </>
            ) : <p className="text-[13px] text-sec">رسید؛ برنامه‌ی کار تا ده دقیقه‌ی دیگر میرسد.</p>}
            {r.route ? <div className="border-t border-div pt-3"><RouteLine r={r.route} count={(r.route as { count?: number | null }).count} /></div> : null}
          </Card>
          <Steps r={r} />
        </div>
        <Card className="flex flex-col gap-2 p-5" aria-label="خروجی‌ها">
          <SectionTitle title="خروجی‌ها" note={r.outputs.length ? 'آنچه تا حالا ساخته شده' : undefined} />
          {r.outputs.length ? (
            <ul className="flex flex-col gap-1.5">
              {r.outputs.map((o) => (
                <li key={o.ref}>
                  <Link href={`/outputs?ref=${o.ref}&tab=all`} className="flex items-center gap-2 rounded-[10px] bg-tile px-3 py-2.5 text-[13px] hover:bg-hover">
                    <Icon name={o.kind === 'reel' ? 'video' : o.kind === 'post' || o.kind === 'story' ? 'image' : 'deliverable'} size={16} className="text-silver-ink" />
                    <span className="min-w-0 flex-1 truncate"><FaText text={o.title_fa} /></span>
                    <span className="text-[11px] text-muted">{OUTPUT_KIND_FA[o.kind as OutputKind] ?? 'خروجی'}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : <p className="text-[13px] text-muted">{ended ? 'خروجی‌ای ثبت نشد.' : 'هنوز خروجی‌ای نیست؛ با هر خروجی این‌جا پر میشود.'}</p>}
        </Card>
      </div>
    </>
  );
}
