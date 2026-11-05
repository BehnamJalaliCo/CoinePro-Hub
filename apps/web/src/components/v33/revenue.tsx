'use client';

// ⟨1.15⟩ Contract §33.3: `by_source` on the revenue summary — the referral commission (§19.1) and the customers' payments (§33.2) side by
// side, so the holding sees where its money comes from.

import { HBars } from '@/components/charts/charts';
import { Card, SectionTitle } from '@/components/ui/primitives';
import { fig } from '@/components/v29/text';
import { SOURCE_FA, useRevenueBySource } from '@/lib/api/v33';

export function BySourceCard({ period, company }: { period: string; company: string | null }) {
  const q = useRevenueBySource(period, company);
  const rows = q.data;
  if (!rows?.length) return null; // the hub has not added `by_source` yet: nothing new shows
  const total = rows.reduce((a, r) => a + r.usdt, 0);
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="درآمد به تفکیک منبع">
      <SectionTitle title="از کجا میاید" note={<>جمع <span className="fig">{fig(total)}</span> USDT</>} />
      <HBars rows={rows.map((r) => ({ key: r.source, label: SOURCE_FA[r.source] ?? r.source, value: r.usdt, fmt: `${fig(r.usdt)} USDT · ${fig(total ? (r.usdt / total) * 100 : 0)}%`, color: r.source === 'affiliate' ? 'var(--hq-gold-bright)' : 'var(--hq-lapis, #5B8DEF)' }))} />
    </Card>
  );
}
