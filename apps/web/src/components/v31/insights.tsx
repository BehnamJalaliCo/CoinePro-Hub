'use client';

// ⟨1.13⟩ Contract §31.1 «درس‌ها»: what the line's own published runs taught (best hour, length, voice, pattern; top hooks; lessons).

import { Card, SectionTitle } from '@/components/ui/primitives';
import { METRIC_FA, useInsights } from '@/lib/api/v31';
import { jDate } from '@/lib/format';
import { FaText } from '@/components/v29/text';

export function LineInsights({ lineRef }: { lineRef: string }) {
  const q = useInsights(lineRef);
  const d = q.data;
  if (!d) return null; // not served yet, or nothing learned yet: nothing new shows
  const best: Array<[string, string | null]> = [
    ['بهترین ساعت', d.best.hour == null ? null : `${String(d.best.hour).padStart(2, '0')}:00`], ['بهترین طول', d.best.length_bucket],
    ['بهترین صدا', d.best.voice], ['بهترین الگو', d.best.pattern_source],
  ];
  return (
    <Card as="section" className="hq-rise flex flex-col gap-4 p-5" aria-label="درس‌ها">
      <SectionTitle title="درس‌ها" note={<>از <span className="fig">{d.window_runs}</span> اجرای اخیر، با معیار {METRIC_FA[d.metric] ?? d.metric}؛ به‌روز شده {jDate(d.updated_at)}</>} />
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {best.map(([k, v]) => <div key={k} className="rounded-[12px] bg-tile p-3"><dt className="text-[11px] text-muted">{k}</dt><dd className="fig pt-1 text-[15px] font-semibold"><FaText text={v ?? '—'} /></dd></div>)}
      </dl>
      {d.lessons_fa.length ? <ul className="flex flex-col gap-1.5" aria-label="درس‌های آموخته">{d.lessons_fa.map((l) => <li key={l} className="text-[13px] leading-6"><FaText text={l} /></li>)}</ul> : null}
      {d.top_hooks.length ? (
        <div className="flex flex-col gap-1.5"><h3 className="text-[13px] font-semibold text-sec">قلاب‌های برتر</h3>
          <ol className="flex list-decimal flex-col gap-1 pr-5 text-[13px] leading-6 marker:text-muted">{d.top_hooks.map((h) => <li key={h}><FaText text={h} /></li>)}</ol></div>
      ) : null}
    </Card>
  );
}
