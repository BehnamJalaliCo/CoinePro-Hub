'use client';

import { useState } from 'react';
import { Orb } from '@/components/brand/avatar';
import { Chat } from '@/components/chat/chat';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Pill, Switch } from '@/components/ui/primitives';
import { MemosSheet, ReviewBanner, ReviewSheet, TriggersSheet } from '@/components/v18/advisor';
import { useInquiries } from '@/lib/api/v14';
import { ACTOR_FA } from '@/lib/labels';
import { ago, until } from '@/lib/format';

const SUGGEST = [
  'امروز اول به کدام تصمیم برسم؟',
  'مصرف توکن این هفته را با هفته‌ی قبل مقایسه کن.',
  'کدام شرکت بیشترین ریسک را دارد و چرا؟',
];

const Q_FA = { open: { fa: 'منتظر جواب', tone: 'lapis' }, answered: { fa: 'جواب داده شد', tone: 'pos' }, late: { fa: 'دیر شده', tone: 'neg' }, withdrawn: { fa: 'پس گرفته شد', tone: 'neutral' } } as const;

/** The advisor's formal questions to CEOs and managers (contract §18.2): answered with evidence, by a due time. */
function Inquiries({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const q = useInquiries('HQ-ADV');
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="پرسش‌های رسمی مشاور" description="مشاور وقتی سوابق جواب نمیدهد، از خود مدیرها میپرسد؛ جواب با شاهد میاید." width={520}>
      <ul className="flex flex-col gap-3">
        {(q.data?.items ?? []).map((x) => (
          <li key={x.ref} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
            <div className="flex items-center gap-2 text-[11px] text-muted"><span className="fig">{x.ref}</span><span>به {ACTOR_FA(x.to)}</span><span className="flex-1">{x.status === 'answered' ? ago(x.answered_at) : until(x.due_at)}</span><Pill tone={Q_FA[x.status].tone} dot>{Q_FA[x.status].fa}</Pill></div>
            <p className="text-[14px] leading-7 text-ink">{x.question_md}</p>
            {x.answer_md ? <Md text={x.answer_md} className="rounded-[10px] bg-card p-3 text-[13px] leading-7 text-sec" /> : null}
          </li>
        ))}
        {!q.data?.items.length ? <li className="text-[13px] text-muted">پرسشی نیست.</li> : null}
      </ul>
    </Sheet>
  );
}

const chip = 'flex h-8 flex-none items-center gap-1.5 whitespace-nowrap rounded-full border border-strong px-3 text-[12px] text-sec hover:bg-hover hover:text-ink';

/** مشاور کل: outside every company, only for the owner; rank two. Opus 5.5 (xhigh); reads everything, asks anyone, cites everything.
 *  ⟨1.5⟩ §21.1/§21.3: decision memos with the substitutes' second and third opinions, the devil's advocate, proactive notes and the
 *  weekly review. */
export default function AdvisorPage() {
  const [inq, setInq] = useState(false);
  const [memos, setMemos] = useState(false);
  const [review, setReview] = useState(false);
  const [triggers, setTriggers] = useState(false);
  const [devil, setDevil] = useState(false);
  return (
    <div className="mx-auto flex h-[calc(100dvh-64px-48px)] w-full max-w-[920px] flex-col lg:h-[calc(100dvh-64px-36px)]">
      <header className="flex flex-col gap-3 border-b border-div pb-3">
        <div className="flex items-center gap-4">
          <Orb size={52} state={devil ? 'thinking' : 'listening'} />
          <div className="flex min-w-0 flex-1 flex-col">
            <h1 className="text-h2 font-semibold">مشاور کل</h1>
            <p className="text-caption text-muted">رتبه‌ی دوم؛ همه‌چیز را میخواند (کد، فایل‌ها، کارگاه، وب) و از هر مدیری میپرسد؛ فقط مشورت میدهد. هر گفت‌وگو برای همیشه با شناسه میماند.</p>
          </div>
          <span className="fig hidden rounded-full bg-tile px-3 py-1 text-[12px] text-sec sm:inline">Opus 5.5 · xhigh</span>
        </div>
        <div className="-mx-1 flex items-center gap-2 overflow-x-auto px-1 pb-0.5">
          <label className={`${chip} cursor-pointer ${devil ? 'border-transparent bg-neg-soft font-semibold text-neg' : ''}`}>
            <Switch label="حالت مخالف‌خوان" checked={devil} onChange={setDevil} />مخالف‌خوان
          </label>
          <button type="button" onClick={() => setReview(true)} className={chip}>مرور هفتگی</button>
          <button type="button" onClick={() => setMemos(true)} className={chip}>یادداشت‌های تصمیم</button>
          <button type="button" onClick={() => setTriggers(true)} className={chip}>گزارش‌های فعال</button>
          <button type="button" onClick={() => setInq(true)} className={chip}>پرسش‌های رسمی</button>
        </div>
      </header>
      <ReviewBanner onOpen={() => setReview(true)} />
      {devil ? <p className="mt-3 rounded-[12px] bg-neg-soft px-3 py-2 text-[12px] leading-5 text-ink">حالت مخالف‌خوان: مشاور فقط برای همین پیام‌ها قوی‌ترین استدلال «چرا نه» را میاورد. پیام‌ها برچسب میگیرند.</p> : null}
      <Chat code="A" agentKind="advisor" mode={devil ? 'devil' : null} placeholder={devil ? 'بپرس چرا نه… (مشاور مخالف‌خوانی میکند)' : 'از مشاور بپرس… (Enter بفرست، Shift+Enter خط تازه)'} suggestions={SUGGEST} />
      <Inquiries open={inq} onOpenChange={setInq} />
      <MemosSheet open={memos} onOpenChange={setMemos} />
      <ReviewSheet open={review} onOpenChange={setReview} />
      <TriggersSheet open={triggers} onOpenChange={setTriggers} />
    </div>
  );
}
