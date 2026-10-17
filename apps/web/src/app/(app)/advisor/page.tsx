'use client';

import { useState } from 'react';
import { Orb } from '@/components/brand/avatar';
import { Chat } from '@/components/chat/chat';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Pill } from '@/components/ui/primitives';
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

/** مشاور کل: outside every company, only for the owner; rank two. Opus 5.5 (xhigh); reads everything, asks anyone, cites everything. */
export default function AdvisorPage() {
  const [inq, setInq] = useState(false);
  return (
    <div className="mx-auto flex h-[calc(100dvh-64px-48px)] w-full max-w-[920px] flex-col lg:h-[calc(100dvh-64px-36px)]">
      <header className="flex items-center gap-4 border-b border-div pb-4">
        <Orb size={52} state="listening" />
        <div className="flex flex-1 flex-col">
          <h1 className="text-h2 font-semibold">مشاور کل</h1>
          <p className="text-caption text-muted">رتبه‌ی دوم؛ همه‌چیز را میخواند (کد، فایل‌ها، کارگاه، وب) و از هر مدیری میپرسد؛ فقط مشورت میدهد. هر گفت‌وگو برای همیشه با شناسه میماند.</p>
        </div>
        <button type="button" onClick={() => setInq(true)} className="rounded-full border border-strong px-3 py-1 text-[12px] text-sec hover:bg-hover hover:text-ink">پرسش‌های رسمی</button>
        <span className="fig hidden rounded-full bg-tile px-3 py-1 text-[12px] text-sec sm:inline">Opus 5.5 · xhigh</span>
      </header>
      <Chat code="A" agentKind="advisor" placeholder="از مشاور بپرس… (Enter بفرست، Shift+Enter خط تازه)" suggestions={SUGGEST} />
      <Inquiries open={inq} onOpenChange={setInq} />
    </div>
  );
}
