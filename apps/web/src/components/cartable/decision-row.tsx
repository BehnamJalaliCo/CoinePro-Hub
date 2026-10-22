'use client';

import Link from 'next/link';
import { useNow } from '@/lib/store';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Pill } from '@/components/ui/primitives';
import { DECISION_KIND, RISK } from '@/lib/labels';
import { ago, cx, until } from '@/lib/format';

type Row = { ref: string; title: string; kind: string; risk: string; company: string; created_at: string; status?: string; expires_at?: string | null; proposer?: { display_fa?: string | null; code: string } | null };
/** ⟨1.5⟩ §21.8: how long a card has waited for the owner (hours), when the server says. */
const waitingOf = (d: Row) => (d as Row & { waiting_h?: number | null }).waiting_h ?? null;

/** One decision in a list: what, who, risk, time left. Selected = soft gold. */
export function DecisionRow({ d, href, selected, onSelect }: { d: Row; href?: string; selected?: boolean; onSelect?: () => void }) {
  const k = DECISION_KIND[d.kind] ?? { fa: d.kind, icon: 'decision' as const };
  const r = RISK[d.risk] ?? RISK.medium!;
  const now = useNow();
  const soon = !!now && !!d.expires_at && new Date(d.expires_at).getTime() - now < 12 * 3600_000;
  const inner = (
    <div className={cx('flex items-start gap-3 rounded-[12px] p-3 transition-colors', selected ? 'tahrir bg-gold-soft' : 'hover:bg-hover')}>
      <span className="mt-0.5 flex size-9 flex-none items-center justify-center rounded-[10px] bg-tile text-gold-ink"><Icon name={k.icon} size={18} /></span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[14px] font-semibold text-ink">{d.title}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-muted">
          <span className="text-sec"><CompanyMark code={d.company} height={13} mono /></span>
          <span>{k.fa}</span>
          {d.proposer ? <span>، {d.proposer.display_fa ?? d.proposer.code}</span> : null}
          <span>، {ago(d.created_at)}</span>
          <span className="fig text-[11px]">{d.ref}</span>
        </div>
      </div>
      <div className="flex flex-none flex-col items-end gap-1">
        <Pill tone={r.tone} dot>{r.fa}</Pill>
        {d.expires_at && d.status === 'pending' ? <span className={cx('text-[11px]', soon ? 'text-warn' : 'text-muted')}>{until(d.expires_at)}</span>
          : d.status === 'pending' && (waitingOf(d) ?? 0) >= 24 ? <span className={cx('text-[11px]', (waitingOf(d) ?? 0) >= 72 ? 'text-warn' : 'text-muted')}>منتظر {Math.round((waitingOf(d) ?? 0) / 24)} روز</span> : null}
      </div>
    </div>
  );
  if (onSelect) return <button type="button" onClick={onSelect} className="w-full text-right" aria-pressed={selected}>{inner}</button>;
  return href ? <Link href={href} className="block">{inner}</Link> : inner;
}
