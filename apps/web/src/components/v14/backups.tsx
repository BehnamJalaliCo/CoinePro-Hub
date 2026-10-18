'use client';

import { Icon } from '@/components/icon';
import { Card, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useBackups } from '@/lib/api/v14';
import { ago, until } from '@/lib/format';

const DEST_FA: Record<string, string> = { gdrive: 'Google Drive (حساب Pro تو)', hetzner: 'Hetzner Object Storage', local: 'خود سرور' };
const gb = (b: number) => (b >= 1e12 ? `${(b / 1e12).toFixed(1)} TB` : `${(b / 1e9).toFixed(1)} GB`);

/** Backups at a glance (contract §18.9): hourly encrypted snapshots, continuous WAL, destinations, the weekly restore test. */
export function BackupsCard() {
  const q = useBackups();
  const b = q.data;
  if (!b) return <Skeleton className="h-48 rounded-[16px]" />;
  // Measured against when the status was read (pure during render); PR-070 alarms past two hours.
  const stale = b.hourly.stale ?? (b.hourly.last_at ? q.dataUpdatedAt - new Date(b.hourly.last_at).getTime() > 2 * 3_600_000 : true);
  const walBroken = !!b.wal.failing;
  const destBroken = b.destinations.some((d) => d.configured && d.ok === false);
  const healthy = !!b.hourly.ok && !stale && !walBroken && b.check?.ok !== false && !destBroken;
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="پشتیبان‌گیری" note={<>ساعتی و رمزنگاری‌شده با <span className="fig">{b.encryption}</span>، به‌علاوه‌ی WAL پیوسته برای بازگشت به هر دقیقه</>}
        action={<Pill tone={healthy ? 'pos' : 'neg'} dot>{healthy ? 'سالم' : 'مشکل'}</Pill>} />
      {walBroken ? (
        <p className="flex items-start gap-2 rounded-[12px] bg-neg-soft p-3 text-[13px] leading-6 text-ink" role="alert">
          <span className="text-neg"><Icon name="urgent" size={18} /></span>
          <span>آرشیو WAL کار نمیکند: بازگشت به هر دقیقه قطع است و اگر بماند دیسک پر میشود. {b.wal.ready_count ? <><span className="fig">{b.wal.ready_count}</span> فایل منتظر است. </> : null}SRE پلتفرم خبر دارد.</span>
        </p>
      ) : null}
      {b.hourly.error && !walBroken ? <p className="rounded-[12px] bg-neg-soft p-3 text-[13px] leading-6 text-ink">{b.hourly.error}</p> : null}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="flex flex-col gap-0.5 rounded-[12px] bg-tile p-3"><span className="text-[11px] text-muted">آخرین backup ساعتی</span><span className="text-[14px] font-semibold">{ago(b.hourly.last_at)}</span><span className="text-[11px] text-muted">بعدی: {until(b.hourly.next_at)} · <span className="fig">{gb(b.hourly.size_bytes ?? 0)}</span></span></div>
        <div className="flex flex-col gap-0.5 rounded-[12px] bg-tile p-3"><span className="text-[11px] text-muted">عقب‌ماندگی WAL</span><span className={walBroken ? 'fig text-[14px] font-semibold text-neg' : 'fig text-[14px] font-semibold'}>{b.wal.lag_s ?? '—'}s</span><span className="text-[11px] text-muted">{b.base_backup ? <>بازگشت تا هر دقیقه، <span className="fig">{b.base_backup.count}</span> نسخه‌ی پایه</> : 'بازگشت تا هر دقیقه روی سرور'}</span></div>
        <div className="flex flex-col gap-0.5 rounded-[12px] bg-tile p-3"><span className="text-[11px] text-muted">آخرین تست بازیابی</span><span className={b.restore_test.ok ? 'text-[14px] font-semibold text-pos' : 'text-[14px] font-semibold text-neg'}>{b.restore_test.ok ? 'قبول' : 'رد'} · {ago(b.restore_test.last_at)}</span><span className="text-[11px] text-muted">{b.restore_test.notes}</span></div>
      </div>
      <ul className="flex flex-col">
        {b.destinations.map((d) => (
          <li key={d.key} className="flex items-center gap-3 border-b border-div py-2 text-[13px] last:border-0">
            <Icon name={d.key === 'gdrive' ? 'globe' : 'server'} size={16} className={d.configured && d.ok === false ? 'text-neg' : d.configured ? 'text-pos' : 'text-muted'} />
            <span className="flex-1">{DEST_FA[d.key]}</span>
            {d.configured && d.ok === false ? <span className="text-[12px] text-neg">{d.error ?? 'در دسترس نیست'}</span>
              : d.configured ? <span className="fig text-[12px] text-sec">{gb(d.used_bytes ?? 0)}{d.quota_bytes ? ` / ${gb(d.quota_bytes)}` : ''}</span>
              : <span className="text-[12px] text-muted">{d.key === 'gdrive' ? <code className="fig">make gdrive-auth</code> : 'خاموش'}</span>}
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-muted">نگهداری: <span className="fig">{b.retention.hourly}</span> ساعتی، <span className="fig">{b.retention.daily}</span> روزانه، <span className="fig">{b.retention.monthly}</span> ماهانه، <span className="fig">{b.retention.yearly}</span> سالانه. بازیابی فقط در ترمینال خودت.{b.check?.ok === false ? ' بررسی سلامت مخزن رد شد.' : ''}{b.openbao_snapshot.configured === false || (b.openbao_snapshot.configured === undefined && !b.openbao_snapshot.ok) ? ' snapshot گاوصندوق رمزها منتظر توکن تو است.' : b.openbao_snapshot.ok === false ? ' snapshot گاوصندوق رمزها شکست خورد.' : ''}</p>
    </Card>
  );
}
