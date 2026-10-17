'use client';

import { Orb } from '@/components/brand/avatar';
import { Chat } from '@/components/chat/chat';

const SUGGEST = [
  'امروز اول به کدام تصمیم برسم؟',
  'مصرف توکن این هفته را با هفته‌ی قبل مقایسه کن.',
  'کدام شرکت بیشترین ریسک را دارد و چرا؟',
];

/** مشاور کل: outside every company, only for the owner. Opus 5.5 (xhigh), read-only, cites everything. */
export default function AdvisorPage() {
  return (
    <div className="mx-auto flex h-[calc(100dvh-64px-48px)] w-full max-w-[920px] flex-col lg:h-[calc(100dvh-64px-36px)]">
      <header className="flex items-center gap-4 border-b border-div pb-4">
        <Orb size={52} state="listening" />
        <div className="flex flex-1 flex-col">
          <h1 className="text-h2 font-semibold">مشاور کل</h1>
          <p className="text-caption text-muted">همه‌ی شرکت‌ها، تصمیم‌ها و خزانه را میبیند؛ فقط مشورت میدهد. هر گفت‌وگو برای همیشه با شناسه میماند.</p>
        </div>
        <span className="fig hidden rounded-full bg-tile px-3 py-1 text-[12px] text-sec sm:inline">Opus 5.5 · xhigh</span>
      </header>
      <Chat code="A" agentKind="advisor" placeholder="از مشاور بپرس… (Enter بفرست، Shift+Enter خط تازه)" suggestions={SUGGEST} />
    </div>
  );
}
