'use client';

// ⟨1.11⟩ Contract §29.8 the council v2: outside advisors with a fact pack. The owner reads the captain's plan in 5–10 lines and runs it with
// «اجرا کن» (which makes an order from it, through the secretary's line); the role each player had; the fact pack the council was given
// (no secret, no personal data); the round it reached; and each member's own answer behind «جزئیات».

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { ModelMark } from '@/components/brand/model-mark';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Card, Pill, SectionTitle } from '@/components/ui/primitives';
import { useVoiceOrder } from '@/components/work/voice-order';
import { COUNCIL_STATE, MEMBER_STATE, PROVIDER_OF, humanReason, playerFa } from '@/lib/api/v28';
import { ROUND_FA, councilRoleFa, sourceFa, type Council29 } from '@/lib/api/v29';
import { cx, jDate } from '@/lib/format';
import { FaText, fig } from './text';

/** The plan as plain words for an order: its lines without Markdown marks. */
export const planText = (md: string) => md.replace(/\*\*|__|\*|_|`/g, '').replace(/^\s*[-•]\s*/gm, '').trim();

export function CouncilV2({ c, title }: { c: Council29; title?: string | null }) {
  const voice = useVoiceOrder();
  const [details, setDetails] = useState(false);
  const roles = c.roles ?? {};
  const fp = c.fact_pack ?? null;
  const moving = c.state === 'running' || c.state === 'synthesising';
  return (
    <Card className={cx('flex flex-col gap-4 p-5', c.state === 'done' && 'tahrir')} aria-label="شورای مشاوران">
      <SectionTitle title="شورای مشاوران" note={c.round ? ROUND_FA[c.round] : 'مشاوران بیرونی، با بسته‌ی واقعیت'}
        action={<Pill tone={c.state === 'failed' ? 'neg' : moving ? 'gold' : 'pos'} live={moving} icon={c.state === 'done' ? 'seal' : undefined}>{COUNCIL_STATE[c.state] ?? c.state}</Pill>} />

      {c.plan_md ? (
        <section className="flex flex-col gap-3 rounded-[14px] bg-gold-soft p-4 ring-1 ring-[var(--hq-line-tahrir)]" aria-label="برنامه">
          <div className="flex items-center gap-2">
            <ModelMark model="claude" provider="anthropic" size={18} />
            <h3 className="flex-1 text-[14px] font-semibold text-gold-ink">برنامه‌ی کاپیتان</h3>
          </div>
          <div className="hq-prose text-[14px]"><Md text={c.plan_md} /></div>
          <Button variant="primary" icon="send" className="self-start"
            onClick={() => voice({ mode: 'order', text: `${title ? `اجرای برنامه‌ی شورا: ${title}\n` : ''}${planText(c.plan_md!)}` })}>اجرا کن</Button>
        </section>
      ) : <p className="text-[13px] text-muted">برنامه‌ی کاپیتان بعد از دور سوم این‌جا میاید.</p>}

      {Object.keys(roles).length ? (
        <section className="flex flex-col gap-2" aria-label="نقش‌ها">
          <h3 className="text-[13px] font-semibold text-sec">نقش هر بازیکن</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(roles).map(([p, role]) => (
              <span key={p} className="inline-flex h-8 items-center gap-1.5 rounded-full bg-tile px-3 text-[12px]">
                <ModelMark provider={PROVIDER_OF[p]} size={14} />{playerFa(p)}<span className="text-muted">·</span><span className="text-sec">{councilRoleFa(role)}</span>
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {fp ? (
        <section className="flex flex-col gap-2" aria-label="بسته‌ی واقعیت">
          <h3 className="text-[13px] font-semibold text-sec">بسته‌ی واقعیت <span className="font-normal text-muted">(آنچه شورا از عددهای واقعی داشت، {jDate(fp.at)})</span></h3>
          <dl className="grid gap-2 sm:grid-cols-2">
            {fp.figures.map((f) => (
              <div key={f.key} className="flex flex-col gap-0.5 rounded-[10px] bg-tile p-2.5">
                <dt className="text-[11px] text-muted">{f.title_fa}</dt>
                <dd className="flex items-baseline justify-between gap-2"><span className="fig text-[15px] font-semibold">{typeof f.value === 'number' ? fig(f.value) : f.value}</span><span className="text-[11px] text-muted">{sourceFa(f.source)}، {jDate(f.at)}</span></dd>
              </div>
            ))}
          </dl>
          {fp.recent_posts?.length ? (
            <ul className="flex flex-col gap-1 text-[12px] text-sec">
              {fp.recent_posts.map((p, i) => <li key={i} className="flex items-center gap-2"><Icon name="image" size={13} className="text-muted" /><span className="min-w-0 flex-1 truncate"><FaText text={p.title_fa ?? ''} /></span>{p.reach != null ? <span className="text-muted">بازدید <span className="fig">{fig(p.reach)}</span></span> : null}</li>)}
            </ul>
          ) : null}
          {fp.notes_fa ? <span className="text-[11px] text-muted"><FaText text={fp.notes_fa} /></span> : null}
        </section>
      ) : null}

      <div className="flex flex-col gap-2 border-t border-div pt-3">
        <button type="button" aria-expanded={details} onClick={() => setDetails(!details)} className="inline-flex items-center gap-1 self-start text-[12px] font-semibold text-sec hover:text-ink">
          <Icon name="info" size={13} />{details ? 'بستن جزئیات' : 'جزئیات: پاسخ هر عضو'}
        </button>
        {details ? (
          <ul className="flex flex-col divide-y divide-[var(--hq-line-divider)]">
            {c.members.map((m) => {
              const st = MEMBER_STATE[m.state] ?? { fa: m.state, tone: 'neutral' as const };
              const why = humanReason(m);
              return (
                <li key={m.player} className="flex items-center gap-3 py-2.5">
                  <span className="flex size-8 flex-none items-center justify-center rounded-[10px] bg-tile"><ModelMark model={m.model ?? null} provider={PROVIDER_OF[m.player]} size={18} /></span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="text-[13px] font-semibold">{playerFa(m.player)}{roles[m.player] ? <span className="font-normal text-muted"> · {councilRoleFa(roles[m.player]!)}</span> : null}</span>
                    {why ? <span className="text-[12px] text-neg"><FaText text={why.text} /></span> : null}
                  </span>
                  {m.state === 'done' && m.deliverable_ref ? <Link href={`/outputs?ref=${m.deliverable_ref}&tab=all`} className="text-[12px] font-semibold text-gold-ink hover:underline">پاسخ کامل</Link> : <Pill tone={st.tone} dot>{st.fa}</Pill>}
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </Card>
  );
}
