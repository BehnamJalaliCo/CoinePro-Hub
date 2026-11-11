'use client';

/**
 * ⟨1.0.1⟩ §49 «بهترین ساعت، خودکار»: each day's package goes out at the hour the account does best at.
 *
 * The owner's order was «در ساعت‌های پربازدید طبق زمان‌بندی منتشر کند». The hub reads the account's posts once a day and names its best
 * hour once there are enough of them; until then it says how many there are, and the fixed hour (or the moment the package is ready)
 * stays in use. What is counted is likes and comments, and the hub's own note says so. The switch sits in the standing word's settings
 * (at the seal, at «به شرکت دیگر بده» and in a member's row); it is not offered on a hub before §49.
 */
import { Switch } from '@/components/ui/primitives';
import { FaText } from '@/components/v29/text';
import { Ltr } from '@/components/look/text';
import { clockOf, type MemberPublish } from '@/lib/api/v44';
import { bestHourOf, useBestHour } from '@/lib/api/v47';

export function BestHourChoice({ company, value, onChange }: { company: string | null | undefined; value: MemberPublish; onChange: (v: MemberPublish) => void }) {
  const q = useBestHour(company, value.account);
  const b = q.data;
  // no company chosen yet, or a hub that does not know the best hour
  if (!company || !b) return null;
  const on = !!value.best;
  const hour = bestHourOf(b);
  return (
    <div className="flex flex-col gap-1" data-testid="best-hour" data-enough={hour ? 'true' : 'false'}>
      <div className="flex items-center gap-3">
        <span className="min-w-0 flex-1 text-[13px] text-ink">بهترین ساعت، خودکار</span>
        <Switch checked={on} onChange={(v) => onChange({ ...value, best: v })} label="بهترین ساعت، خودکار" />
      </div>
      {hour ? (
        <>
          <p className="text-[12px] text-sec">بهترین ساعت این حساب: <Ltr>{hour}</Ltr></p>
          {b.note_fa ? <p className="text-[11px] leading-5 text-muted"><FaText text={b.note_fa} /></p> : null}
        </>
      ) : (
        <>
          {b.note_fa ? <p className="text-[11px] leading-5 text-sec"><FaText text={b.note_fa} /></p> : null}
          {on ? <p className="text-[11px] leading-5 text-muted">{clockOf(value.at) ? 'تا آن وقت: ساعت ثابت شما' : 'تا آن وقت: همان لحظه‌ی آماده شدن'}</p> : null}
        </>
      )}
    </div>
  );
}
