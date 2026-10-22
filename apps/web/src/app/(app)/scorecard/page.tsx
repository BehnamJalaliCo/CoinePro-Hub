'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ErrorState, PageHeader, Skeleton } from '@/components/ui/primitives';
import { ScopeChips } from '@/components/v17/bits';
import { CardPanel, KpiSheet, Scorecard, TargetsSheet } from '@/components/v17/cards';
import { useCompanies } from '@/lib/api/hooks';
import { useCards, useKpis } from '@/lib/api/v17';
import { useScope } from '@/lib/scope';

/** کارت‌ها و امتیاز (contract §20.4): the three cards of the holding and of each company, and the live scorecard. Every figure has a
 *  source and a time; an old value is «قدیمی» and a KPI without a source is a dash, never zero. */
export default function ScorecardPage() {
  const { company: scope } = useScope();
  const { data: companies } = useCompanies();
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const raw = picked !== undefined ? picked : scope;
  // The holding's own scope reads as the holding card (the server's default).
  const company = companies?.find((c) => c.code === raw)?.kind === 'holding' ? null : raw;
  const q = useCards(company);
  const defs = useKpis(company);
  const dirs = Object.fromEntries((defs.data?.kpis ?? []).map((k) => [k.key, k.direction]));
  const [open, setOpen] = useState<string | null>(null);
  const [targets, setTargets] = useState(false);
  const kpi = open ? q.data?.flatMap((c) => c.kpis).find((k) => k.key === open) : undefined;
  return (
    <>
      <PageHeader eyebrow="پایداری، رشد، ایمنی و هزینه؛ هر عدد با منبع و زمان" title="کارت‌ها و امتیاز"
        actions={company ? <Button variant="secondary" icon="settings" onClick={() => setTargets(true)}>هدف‌ها</Button> : undefined}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">منبع هر KPI از رجیستری بسته‌ی کوئری‌های بازبینی‌شده است، یا دستی با شاهد. عددی که از تازگی‌اش گذشته «قدیمی» است و KPIای که منبعش ساخته نشده خط تیره است، هرگز صفر. کارت هلدینگ تجمیع شرکت‌هاست.</p>
      </PageHeader>
      <ScopeChips value={company} onChange={setPicked} allLabel="هلدینگ" holding={false} />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <div className="grid items-start gap-3 lg:grid-cols-3">
          {!q.data ? Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-80 rounded-[16px]" />) : q.data.map((c) => <CardPanel key={c.card} c={c} dirs={dirs} onOpen={company ? setOpen : undefined} />)}
        </div>
      )}
      <Scorecard />
      {company && kpi ? <KpiSheet company={company} k={kpi} def={defs.data?.kpis.find((k) => k.key === kpi.key)} onClose={() => setOpen(null)} /> : null}
      {company && targets ? <TargetsSheet company={company} onClose={() => setTargets(false)} /> : null}
    </>
  );
}
