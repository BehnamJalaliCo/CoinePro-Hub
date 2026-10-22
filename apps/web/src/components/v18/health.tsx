'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { MdInline } from '@/components/ui/md';
import { Card, ErrorState, FilterChip, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { ActorAvatar, CoMark, RefChip } from '@/components/v17/bits';
import { useClaims, useRunsHealth, type ClaimVerdict } from '@/lib/api/v18';
import { ago, cx, usd } from '@/lib/format';
import { ACTOR_FA } from '@/lib/labels';
import { HEALTH, VERDICT_CLAIM, pct01 } from './bits';

/** The agent health board (§21.9), one row per employee, by rule: refuted claims, failures, refusals, retry loops and the owner's returns. */
export function HealthBoard({ company }: { company: string | null }) {
  const [period, setPeriod] = useState<'7d' | '30d'>('7d');
  const q = useRunsHealth({ company, period });
  const rows = [...(q.data?.pages.flatMap((p) => p.items) ?? [])].sort((a, b) => b.flags.length - a.flags.length || b.failed_share - a.failed_share);
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="سلامت کارمندها" note="پرچم‌ها قاعده‌اند؛ ادعای رد شده به بسته‌ی ارزیابی ماهانه هم میرود" action={<div className="w-32"><Segmented label="دوره" value={period} onChange={setPeriod} options={[{ value: '7d', label: '۷ روز' }, { value: '30d', label: '۳۰ روز' }]} /></div>} />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-48" /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] border-collapse text-[12px]">
            <thead><tr className="text-right text-[11px] text-muted">{['کارمند', 'اجرا', 'شکست', 'رد', 'حلقه', 'برگشت تو', 'ادعا (رد)', 'مصرف', 'پرچم'].map((h) => <th key={h} className="px-2 py-1.5 font-semibold">{h}</th>)}</tr></thead>
            <tbody>
              {rows.map((h) => (
                <tr key={h.employee} className="h-10 border-t border-div">
                  <td className="px-2"><span className="flex items-center gap-1.5"><CoMark code={h.company} height={10} /><Link href={`/employees/${h.employee}`} className="fig font-semibold text-ink hover:underline">{h.employee}</Link></span></td>
                  <td className="fig px-2 text-sec">{h.runs}</td>
                  <td className={cx('fig px-2', h.failed_share >= 0.25 ? 'text-neg' : 'text-sec')}>{pct01(h.failed_share)}</td>
                  <td className={cx('fig px-2', h.refused_share >= 0.1 ? 'text-warn' : 'text-muted')}>{pct01(h.refused_share)}</td>
                  <td className={cx('fig px-2', h.retry_loops >= 2 ? 'text-warn' : 'text-muted')}>{h.retry_loops}</td>
                  <td className={cx('fig px-2', h.owner_returns ? 'text-warn' : 'text-muted')}>{h.owner_returns}</td>
                  <td className="fig px-2 text-sec">{h.claims_checked} <span className={h.refuted ? 'text-neg' : 'text-muted'}>({h.refuted}{h.refuted_share != null && h.claims_checked ? ` · ${pct01(h.refuted_share)}` : ''})</span></td>
                  <td className="fig px-2 text-sec">{usd(h.cost_usd)}</td>
                  <td className="px-2"><span className="flex flex-wrap gap-1">{h.flags.map((f) => <Pill key={f} tone={HEALTH[f]?.tone ?? 'neutral'} className="h-5 px-2 text-[11px]">{HEALTH[f]?.fa ?? f}</Pill>)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] leading-5 text-muted">{Object.values(HEALTH).map((x) => `${x.fa}: ${x.note}`).join(' · ')}</p>
    </Card>
  );
}

/** Claims checked by the fact checker, the overseer or QC (§21.9); a refuted one always carries its evidence. */
export function ClaimsCard({ company }: { company: string | null }) {
  const [verdict, setVerdict] = useState<ClaimVerdict | null>('refuted');
  const q = useClaims({ company, verdict });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="ادعاهای بررسی‌شده" note="هیچ ادعایی فقط با حرف یک بازیکن ذخیره رد یا تأیید نمیشود" />
      <div className="flex flex-wrap gap-2">
        <FilterChip selected={!verdict} onClick={() => setVerdict(null)}>همه</FilterChip>
        {(['refuted', 'confirmed', 'unverifiable'] as const).map((v) => <FilterChip key={v} selected={verdict === v} onClick={() => setVerdict(v)}>{VERDICT_CLAIM[v]!.fa}</FilterChip>)}
      </div>
      {q.isLoading ? <Skeleton className="h-32" /> : !items.length ? <p className="py-4 text-center text-[13px] text-muted">ادعایی با این حکم نیست.</p> : (
        <ul className="flex flex-col gap-2">
          {items.map((c) => {
            const v = VERDICT_CLAIM[c.verdict] ?? VERDICT_CLAIM.unverifiable!;
            return (
              <li key={c.ref} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3">
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
                  <span className="fig">{c.ref}</span><CoMark code={c.company} height={10} /><Link href={`/employees/${c.employee}`} className="fig text-sec hover:underline">{c.employee}</Link><RefChip r={c.deliverable} />
                  <span className="flex-1" /><span>{ago(c.at)}</span>
                </div>
                <p className="text-[13px] leading-6 text-ink">«<MdInline text={c.claim_md} />»</p>
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={v.tone} icon={v.icon}>{v.fa}</Pill>
                  <span className="flex items-center gap-1.5 text-[11px] text-sec"><ActorAvatar a={c.checked_by} size={18} />{ACTOR_FA(c.checked_by)}</span>
                  {c.protocol ? <span className="fig text-[11px] text-muted">{c.protocol}</span> : null}
                </div>
                {c.evidence.length ? <ul className="flex flex-col gap-0.5 text-[11px] text-sec">{c.evidence.map((e, i) => <li key={i} className="flex items-center gap-1.5"><Icon name="seal" size={12} /><span className="fig">{e.ref}</span>{e.note ? <span className="text-muted">· <MdInline text={e.note} /></span> : null}</li>)}</ul> : null}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
