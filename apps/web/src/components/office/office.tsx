'use client';

// ⟨1.17⟩ Contract §35.5 «دفتر مدیر کل»: the home is the owner's office, not a dashboard of one subject. What waits for him (answered right
// here, components/look/home.tsx), the pulse, the command entry (one row that opens the command sheet), the sessions (his turn first), the
// canvas of the companies and their links, the money in one line, what is critical, and suggestions on any subject («اجرا کن» opens a session).

import Link from 'next/link';
import { OfficeCanvas } from '@/components/canvas/office-canvas';
import { LiveCompanies, OfficePulse, TokenMeter } from '@/components/live/office';
import { Button } from '@/components/ui/button';
import { Card, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useVoiceOrder } from '@/components/work/voice-order';
import { UsageHomeCard } from '@/components/v33/usage';
import { CriticalCard, SuggestionCard } from '@/components/v29/home';
import { PlainText } from '@/components/v29/bits';
import { usePresence } from '@/lib/api/hooks';
import type { Office, OfficeMoney } from '@/lib/api/v34';
import { CommandRow } from '@/components/look/command';
import { SessionCards, TurnRow, state3, turnCount } from '@/components/look/home';
import { Facts, Ltr, faCount } from '@/components/look/text';
import { cx, jWeekday } from '@/lib/format';

export function OfficeHeader() {
  const { data: presence } = usePresence();
  const voice = useVoiceOrder();
  const today = new Date();
  const g = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(today);
  const h = Number(new Intl.DateTimeFormat('en-US', { hour: 'numeric', hourCycle: 'h23', timeZone: 'Asia/Tehran' }).format(today));
  const hello = h < 12 ? 'صبح بخیر' : h < 17 ? 'روز بخیر' : 'عصر بخیر';
  return (
    <header className="flex flex-wrap items-end gap-x-4 gap-y-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-caption text-muted"><Facts>{jWeekday(today.toISOString())}<Ltr>{g}</Ltr></Facts></span>
        <h1 className="text-h1 font-semibold sm:text-display">{hello}، مدیر کل</h1>
      </div>
      {presence?.khalvat ? <Pill tone="learn" icon="khalvat">خلوت روشن؛ فقط فوری میرسد</Pill> : null}
      <Button variant="ghost" size="sm" icon="seal" onClick={() => voice({ mode: 'rule' })}>قانون تازه برای هلدینگ</Button>
    </header>
  );
}

// ================================================================================================= the sessions ==
/** ⟨1.0.1⟩ part C: open sessions as cards with three states only, each opening out of itself (M14). */
export function OfficeSessions({ sessions }: { sessions: Office['sessions'] }) {
  const waiting = sessions.filter((s) => state3(s.badge) === 'waiting').length;
  return (
    <Card as="section" className="flex flex-col gap-1 p-4" aria-label="جلسه‌ها">
      <SectionTitle title="جلسه‌ها" note={waiting ? `${faCount(waiting)} جلسه منتظر توست` : 'هر فرمان یک جلسه است'}
        action={<span className="flex items-center text-[12px] font-semibold text-silver-ink"><Facts><Link href="/playbooks" className="hover:text-ink hover:underline">کارگروه‌های آماده</Link><Link href="/s" className="hover:text-ink hover:underline">همه و بایگانی</Link></Facts></span>} />
      <SessionCards sessions={sessions} />
    </Card>
  );
}

// ===================================================================================================== money ==
export function MoneyLine({ money }: { money: OfficeMoney }) {
  const pct = money.budget_month_usd ? Math.min(100, Math.round((money.spend_month_usd / money.budget_month_usd) * 100)) : null;
  return (
    <Card as="section" className="flex flex-col gap-2 p-4" aria-label="پول">
      <SectionTitle title="پول" action={<span className="flex items-center text-[12px] font-semibold text-silver-ink"><Facts><Link href="/services" className="hover:text-ink hover:underline">سرویس‌های هاب</Link><Link href="/revenue" className="hover:text-ink hover:underline">درآمد</Link></Facts></span>} />
      <p className="text-[14px] leading-7"><PlainText text={money.line_fa} /></p>
      {pct != null ? <div className="h-1.5 overflow-hidden rounded-full bg-tile" role="img" aria-label={`${pct}٪ از سقف ماه`}><div className={cx('h-full rounded-full', pct >= 90 ? 'bg-neg' : pct >= 70 ? 'bg-warn' : 'bg-pos')} style={{ width: `${pct}%` }} /></div> : null}
    </Card>
  );
}

export function OfficeSuggestions({ items }: { items: Office['suggestions'] }) {
  if (!items.length) return null;
  return (
    <section className="flex flex-col gap-3" aria-label="پیشنهادها">
      {/* The slot is the key, not the suggestion: «نه» or «اجرا کن» swaps the card's words and its toast must still arrive. */}
      {items.slice(0, 3).map((s, i) => <SuggestionCard key={`${s.kind}-${i}`} kind={s.kind} s={s} />)}
    </section>
  );
}

export function OfficeSkeleton() {
  return (
    <>
      <Skeleton className="h-16 rounded-[16px]" />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]"><Skeleton className="h-96 rounded-[16px]" /><Skeleton className="h-96 rounded-[16px]" /></div>
    </>
  );
}

/** The whole office from `GET /office`. ⟨1.0.1⟩ part C: what waits for the owner first, answered in place; then the pulse in one row,
 *  the one-row command entry, the sessions as cards; the rest as it was. */
export function OfficeBody({ o }: { o: Office }) {
  return (
    <>
      <TurnRow o={o} />
      {/* ⟨1.24⟩ OF-1: is the holding working, and is anything waiting for the owner? */}
      <OfficePulse waiting={turnCount(o)} />
      <CommandRow />
      <CriticalCard items={o.critical} />
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <OfficeSessions sessions={o.sessions} />
          {/* ⟨1.24⟩ CO-1: one live card per company, the busiest first. */}
          <LiveCompanies />
          <OfficeCanvas canvas={o.canvas} sessions={o.sessions} />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <MoneyLine money={o.money} />
          {/* ⟨1.24⟩ MO-1: today's spend against the daily budget, as it is spent. */}
          <TokenMeter />
          <UsageHomeCard />
          <OfficeSuggestions items={o.suggestions} />
        </div>
      </div>
    </>
  );
}
