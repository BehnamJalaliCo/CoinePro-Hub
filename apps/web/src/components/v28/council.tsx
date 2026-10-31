'use client';

// ⟨1.9⟩ §27.2 the council of models on an order's page, ⟨1.10⟩ §28.4 robust: each player with its state; a failure in plain Persian (the
// hub's reason when it wrote one, «پاسخ نداد» otherwise, the raw text kept under «جزئیات», never shown as JSON); and the synthesis that
// says so plainly when only one player answered instead of pretending there was a council.

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { ModelMark } from '@/components/brand/model-mark';
import { Md } from '@/components/ui/md';
import { Card, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useOutput } from '@/lib/api/v21';
import { COUNCIL_STATE, MEMBER_STATE, PROVIDER_OF, councilProgressFa, humanReason, playerFa, soloOf, useCouncil, type Council, type CouncilMember } from '@/lib/api/v28';
import { cx, modelLabel } from '@/lib/format';

function Member({ m }: { m: CouncilMember }) {
  const [details, setDetails] = useState(false);
  const st = MEMBER_STATE[m.state] ?? { fa: m.state, tone: 'neutral' as const };
  const out = m.state === 'failed' || m.state === 'skipped';
  const why = humanReason(m);
  return (
    <li className="flex items-start gap-3 py-2.5" aria-label={`${playerFa(m.player)}: ${why?.text ?? st.fa}`}>
      <span className={cx('flex size-9 flex-none items-center justify-center rounded-[10px] bg-tile', out && 'opacity-50')}><ModelMark model={m.model ?? null} provider={PROVIDER_OF[m.player]} size={20} /></span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className={cx('text-[13px] font-semibold', out ? 'text-sec' : 'text-ink')}>{playerFa(m.player)}</span>
          {m.model ? <span className="fig text-[11px] text-muted">{m.player === 'claude' ? modelLabel(m.model) : m.model}</span> : null}
        </span>
        {why ? <span className={cx('text-[12px] leading-5', m.state === 'failed' ? 'text-neg' : 'text-muted')}>{why.text}</span> : null}
        {why?.raw ? (
          <>
            <button type="button" aria-expanded={details} onClick={() => setDetails(!details)} className="inline-flex items-center gap-1 self-start text-[11px] font-semibold text-sec hover:text-ink">
              <Icon name="info" size={12} />{details ? 'بستن جزئیات' : 'جزئیات'}
            </button>
            {details ? <pre dir="ltr" className="fig max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-[8px] bg-tile p-2 text-left text-[11px] leading-5 text-sec">{why.raw}</pre> : null}
          </>
        ) : null}
        {m.state === 'done' && m.deliverable_ref ? (
          <Link href={`/outputs?ref=${m.deliverable_ref}&tab=all`} className="inline-flex items-center gap-1 self-start text-[11px] font-semibold text-gold-ink hover:underline">
            <Icon name="deliverable" size={12} />پاسخ کامل <span className="fig">{m.deliverable_ref}</span>
          </Link>
        ) : null}
      </div>
      <Pill tone={st.tone} dot={m.state === 'queued'} live={m.state === 'working'}>{st.fa}</Pill>
    </li>
  );
}

function Synthesis({ c }: { c: Council }) {
  const solo = soloOf(c);
  const q = useOutput(c.synthesis_ref);
  const none = c.members.length > 0 && !c.members.some((m) => m.state === 'done') && c.members.every((m) => m.state === 'failed' || m.state === 'skipped');
  return (
    <div className="flex flex-col gap-3">
      {solo ? (
        <div role="note" className="flex items-start gap-2 rounded-[12px] bg-warn-soft p-3 text-[13px] leading-6 text-ink">
          <Icon name="info" size={16} className="mt-1 flex-none text-warn" />
          <span><b>{solo.text}</b>؛ بقیه پاسخ ندادند، پس این جمع‌بندی نظر شورا نیست و جای «هم‌نظری» و «اختلاف» خالی است.</span>
        </div>
      ) : null}
      {none ? <p className="rounded-[12px] bg-neg-soft p-3 text-[13px] text-ink">هیچ بازیکنی پاسخ نداد؛ جمع‌بندی‌ای نوشته نشد.</p> : null}
      {c.synthesis_ref ? (
        q.isLoading ? <Skeleton className="h-40 rounded-[14px]" /> : q.data?.ref ? (
          <div className="flex flex-col gap-3 rounded-[14px] bg-gold-soft p-4 ring-1 ring-[var(--hq-line-tahrir)]">
            <div className="flex items-center gap-2">
              <ModelMark model="claude" provider="anthropic" size={18} />
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="text-[14px] font-semibold text-gold-ink">{solo ? `پاسخ ${solo.player}` : 'جمع‌بندی Claude'}</span>
                <span className="truncate text-[11px] text-sec">{q.data.title}</span>
              </div>
              <span className="fig text-[11px] text-muted">{c.synthesis_ref}</span>
            </div>
            <Md text={q.data.body || q.data.summary} />
            <Link href={`/outputs?ref=${c.synthesis_ref}&tab=all`} className="inline-flex items-center gap-1 self-start text-[12px] font-semibold text-gold-ink hover:underline">دیدن در خروجی‌ها<Icon name="next" size={14} mirror /></Link>
          </div>
        ) : null
      ) : c.state === 'synthesising' ? <p className="rounded-[12px] bg-gold-soft p-3 text-[13px]">Claude جمع‌بندی را مینویسد: کجا هم‌نظرند، کجا نه و چرا، و پیشنهاد.</p>
        : c.state === 'running' ? <p className="text-[12px] text-muted">جمع‌بندی منتظر بازیکن‌هایی که هنوز کار میکنند نمیماند؛ بعد از پایان هر کدام نوشته میشود.</p> : null}
    </div>
  );
}

/** The «شورا» card of an order given with `mode: "council"`; nothing for a single-player order or a hub without councils. */
export function CouncilCard({ work, mode }: { work: string; mode?: string | null }) {
  const q = useCouncil(mode === 'council' ? work : null);
  if (mode !== 'council') return null;
  const c = q.data;
  if (q.isLoading) return <Skeleton className="h-56 rounded-[16px]" />;
  if (!c) return null;
  const moving = c.state === 'running' || c.state === 'synthesising';
  return (
    <Card className={cx('flex flex-col gap-3 p-5', c.state === 'done' && 'tahrir')}>
      <SectionTitle title="شورا" note="همان شرح، جدا از هم، روی هر بازیکنِ در دسترس"
        action={<Pill tone={c.state === 'failed' ? 'neg' : moving ? 'gold' : 'pos'} live={moving} icon={c.state === 'done' ? 'seal' : undefined}>{COUNCIL_STATE[c.state] ?? c.state}</Pill>} />
      <span className="text-[12px] text-sec">{councilProgressFa(c)}</span>
      <ul className="flex flex-col divide-y divide-[var(--hq-line-divider)]">{c.members.map((m) => <Member key={m.player} m={m} />)}</ul>
      {c.media ? null : <Synthesis c={c} />}
    </Card>
  );
}
