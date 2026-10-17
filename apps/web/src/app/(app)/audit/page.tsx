'use client';

import { CompanyMark } from '@/components/brand/marks';
import { Card, ErrorState, PageHeader, Pill, Skeleton } from '@/components/ui/primitives';
import { useAudit, useAuditVerify } from '@/lib/api/hooks';
import { ACTOR_FA } from '@/lib/labels';
import { ago, jDateTime } from '@/lib/format';
import { useScope } from '@/lib/scope';

/** The append-only audit chain: every change, one row, hash-linked; verified nightly and anchored outside Postgres. */
export default function AuditPage() {
  const { company } = useScope();
  const q = useAudit({ company: company ? [company] : undefined, limit: 100 });
  const v = useAuditVerify();
  return (
    <>
      <PageHeader eyebrow="هر تغییر، یک ردیف زنجیره‌ای و تغییرناپذیر" title="دفتر Audit" actions={v.data ? (
        v.data.ok ? <Pill tone="pos" icon="seal">زنجیره سالم، {v.data.checked} ردیف، {ago(v.data.verified_at)}</Pill> : <Pill tone="neg" icon="urgent">زنجیره شکسته از ردیف {v.data.first_bad_seq}</Pill>
      ) : null} />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <Card className="overflow-x-auto p-2">
          <table className="w-full min-w-[760px] border-collapse text-[13px]">
            <thead><tr className="text-right text-[11px] text-muted">{['#', 'زمان', 'چه کسی', 'اقدام', 'کلاس', 'هدف', 'شرکت'].map((h) => <th key={h} className="px-3 py-2 font-semibold">{h}</th>)}</tr></thead>
            <tbody>
              {q.isLoading ? Array.from({ length: 8 }, (_, i) => <tr key={i}><td colSpan={7} className="p-1"><Skeleton className="h-10" /></td></tr>)
                : (q.data?.items ?? []).map((e) => (
                  <tr key={e.seq} className="h-12 border-t border-div">
                    <td className="fig px-3 text-muted">{e.seq}</td>
                    <td className="px-3 text-sec" title={e.at}>{jDateTime(e.at)}</td>
                    <td className="px-3">{ACTOR_FA(e.actor)}{e.step_up ? <span className="mr-1.5 text-gold-ink" title="با passkey">🔏</span> : null}</td>
                    <td className="fig px-3 text-ink">{e.action}</td>
                    <td className="px-3"><span className={e.action_class >= 'A3' ? 'fig font-bold text-warn' : 'fig text-sec'}>{e.action_class}</span></td>
                    <td className="fig px-3 text-sec">{Object.values(e.target ?? {}).filter(Boolean).join(' ')}</td>
                    <td className="px-3 text-sec"><CompanyMark code={e.company} height={12} mono /></td>
                  </tr>
                ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
