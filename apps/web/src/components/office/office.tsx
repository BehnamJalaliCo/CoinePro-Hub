'use client';

// ⟨1.17⟩ Contract §35.5 «دفتر مدیر کل»: the home is the owner's office, not a dashboard of one subject. The command bar (words or voice → an
// order → its session), the sessions (his turn first), the canvas of the companies and their links, the cards waiting for his seal (sealed or
// rejected right here), the money in one line, what is critical, and suggestions on any subject («اجرا کن» opens a session).

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { OfficeCanvas } from '@/components/canvas/office-canvas';
import { LiveCompanies, OfficePulse, TokenMeter } from '@/components/live/office';
import { CompanyMark } from '@/components/brand/marks';
import { needsStepUp } from '@/components/cartable/decision-detail';
import { SessionRow } from '@/components/session/session-row';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Card, Empty, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { useVoiceOrder } from '@/components/work/voice-order';
import { UsageHomeCard } from '@/components/v33/usage';
import { CriticalCard, SuggestionCard } from '@/components/v29/home';
import { PlainText } from '@/components/v29/bits';
import { errText, field } from '@/components/v31/kit';
import { ApiError, type Schemas } from '@/lib/api/client';
import { useDecide, usePresence } from '@/lib/api/hooks';
import { sendOrder29 } from '@/lib/api/v29';
import { bySessionOrder, type Office, type OfficeMoney } from '@/lib/api/v34';
import { stepUp } from '@/lib/auth';
import { sealTarget } from '@/lib/api/v19';
import { DECISION_KIND, RISK } from '@/lib/labels';
import { ago, cx, jWeekday } from '@/lib/format';
import { useQueryClient } from '@tanstack/react-query';

type Decision = Schemas['Decision'];

export function OfficeHeader() {
  const { data: presence } = usePresence();
  const voice = useVoiceOrder();
  const today = new Date();
  const g = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(today);
  const h = Number(new Intl.DateTimeFormat('en-US', { hour: 'numeric', hourCycle: 'h23', timeZone: 'Asia/Tehran' }).format(today));
  const hello = h < 12 ? 'صبح بخیر' : h < 17 ? 'روز بخیر' : 'عصر بخیر';
  return (
    <header className="flex flex-wrap items-end gap-x-4 gap-y-2">
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-caption text-muted">{jWeekday(today.toISOString())} · <span className="fig">{g}</span></span>
        <h1 className="text-display font-semibold">{hello}، مدیر کل</h1>
      </div>
      {presence?.khalvat ? <Pill tone="learn" icon="khalvat">خلوت روشن؛ فقط فوری میرسد</Pill> : null}
      <Button variant="secondary" icon="seal" onClick={() => voice({ mode: 'rule' })} className="max-sm:w-full">قانون تازه برای هلدینگ</Button>
    </header>
  );
}

// ============================================================================================ the command bar ==
/** Words or voice → `POST /orders` → the session of that order. */
export function CommandBar() {
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const voice = useVoiceOrder();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const go = async () => {
    const t = text.trim();
    if (t.length < 3) return;
    setBusy(true);
    try {
      const o = await sendOrder29({ text: t, source: 'text' });
      setText('');
      for (const k of ['orders', 'office', 'home', 'work', 'planner']) void qc.invalidateQueries({ queryKey: [k] });
      toast({ tone: 'ok', text: 'فرمان رسید؛ جلسه‌اش باز شد.' });
      router.push(`/s/${encodeURIComponent(o.ref)}`);
    } catch (e) {
      toast({ tone: 'error', text: errText(e, 'فرمان نرسید؛ دوباره بزن.') });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card as="section" className="flex flex-col gap-2 p-3" aria-label="فرمان">
      <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); void go(); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} dir="auto" aria-label="فرمان تازه" placeholder="هر چه میخواهی بگو؛ برایش یک جلسه باز میشود…" autoComplete="off"
          className={cx(field, 'h-12 min-w-0 flex-[1_1_18rem] text-[15px]')} />
        <Button type="button" variant="secondary" icon="mic" onClick={() => voice({ text: text.trim() || undefined })} aria-label="فرمان صوتی">صوتی</Button>
        <Button type="submit" variant="primary" icon="send" disabled={text.trim().length < 3} loading={busy}>بفرست</Button>
      </form>
    </Card>
  );
}

// ================================================================================================= the sessions ==
export function OfficeSessions({ sessions }: { sessions: Office['sessions'] }) {
  const list = sessions.slice().sort(bySessionOrder);
  const turn = list.filter((s) => s.badge === 'your_turn').length;
  return (
    <Card as="section" className="flex flex-col gap-1 p-4" aria-label="جلسه‌ها">
      <SectionTitle title="جلسه‌ها" note={turn ? `${turn} جلسه منتظر جواب توست` : 'هر فرمان یک جلسه است'} action={<span className="flex items-center gap-3"><Link href="/playbooks" className="text-[12px] font-semibold text-gold-ink hover:underline">کارگروه‌های آماده</Link><Link href="/s" className="text-[12px] font-semibold text-gold-ink hover:underline">همه و بایگانی</Link></span>} />
      {list.length ? <ul className="flex flex-col">{list.slice(0, 8).map((s) => <li key={s.ref}><SessionRow s={s} /></li>)}</ul> : <Empty icon="messages" title="جلسه‌ی بازی نیست" body="یک فرمان بده تا جلسه‌اش باز شود." />}
    </Card>
  );
}

// ================================================================================================== approvals ==
/** Kinds that are sealed on their own page against a digest: the office leads there instead of sealing in place. */
const OWN_PAGE = new Set(['server_plan', 'media_series', 'server_destructive']);

function ApprovalRow({ d }: { d: Decision }) {
  const toast = useToast();
  const qc = useQueryClient();
  const decide = useDecide();
  const k = DECISION_KIND[d.kind] ?? { fa: d.kind, icon: 'decision' as const };
  const r = RISK[d.risk] ?? RISK.medium!;
  const [sure, setSure] = useState(false);
  const [reject, setReject] = useState(false);
  const [note, setNote] = useState('');
  const done = () => { void qc.invalidateQueries({ queryKey: ['office'] }); };
  const fail = (e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' });
  const seal = async () => {
    try {
      const token = needsStepUp(d) ? await stepUp('decision.approve', sealTarget(d)) : undefined;
      await decide.mutateAsync({ ref: d.ref, verdict: 'approve', stepUpToken: token });
      toast({ tone: 'ok', text: 'مُهر خورد.' });
      done();
    } catch (e) { fail(e); setSure(false); }
  };
  const own = OWN_PAGE.has(d.kind);
  return (
    <li className="flex flex-col gap-2 rounded-[12px] bg-tile p-3" data-kind={d.kind}>
      <div className="flex items-start gap-2">
        <span className="mt-0.5 text-gold-ink"><CompanyMark code={d.company} height={14} mono /></span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-[14px] font-semibold leading-6 text-ink"><PlainText text={d.title} /></span>
          <span className="text-[11px] text-muted">{k.fa} · {ago(d.created_at)}</span>
        </div>
        <Pill tone={r.tone} dot>{r.fa}</Pill>
      </div>
      <div className="flex flex-wrap gap-2">
        {own ? <Link href={`/cartable?ref=${d.ref}`} className="inline-flex h-9 items-center rounded-[10px] bg-gold px-3 text-[13px] font-semibold text-on-gold hover:bg-gold-bright">بازش کن و مُهر بزن</Link> : sure ? (
          <>
            <Button size="sm" variant="primary" icon="seal" loading={decide.isPending} onClick={() => void seal()}>بله، مُهر بزن</Button>
            <Button size="sm" variant="ghost" onClick={() => setSure(false)}>نه</Button>
          </>
        ) : <Button size="sm" variant="primary" icon="seal" onClick={() => setSure(true)}>مُهر</Button>}
        {!own && !sure ? <Button size="sm" variant="secondary" icon="reject" onClick={() => setReject(true)}>رد</Button> : null}
        <Link href={`/cartable?ref=${d.ref}`} className="inline-flex h-9 items-center px-2 text-[12px] text-muted hover:text-ink">جزئیات</Link>
      </div>
      <Dialog open={reject} onOpenChange={setReject} title="رد این کارت" actions={(
        <Button variant="danger" loading={decide.isPending} onClick={() => decide.mutate({ ref: d.ref, verdict: 'reject', note: note.trim() || undefined }, { onSuccess: () => { setReject(false); toast({ tone: 'info', text: 'رد شد.' }); done(); }, onError: fail })}>رد کن</Button>
      )}>
        <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">چرا؟ (کوتاه)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} dir="auto" aria-label="دلیل رد" className={cx(field, 'h-10')} />
        </label>
      </Dialog>
    </li>
  );
}

export function OfficeApprovals({ items, total }: { items: Office['approvals']; total: number }) {
  return (
    <Card as="section" className="flex flex-col gap-2 p-4" aria-label="منتظر مُهر تو">
      <SectionTitle title="منتظر مُهر تو" note={total > items.length ? `${items.length} از ${total} کارت` : 'فقط کارت‌هایی که با توست'} action={<Link href="/cartable" className="text-[12px] font-semibold text-gold-ink hover:underline">کارتابل</Link>} />
      {items.length ? <ul className="flex flex-col gap-2">{items.map((d) => <ApprovalRow key={d.ref} d={d} />)}</ul> : <Empty icon="seal" title="چیزی منتظر مُهر تو نیست" />}
    </Card>
  );
}

// ===================================================================================================== money ==
export function MoneyLine({ money }: { money: OfficeMoney }) {
  const pct = money.budget_month_usd ? Math.min(100, Math.round((money.spend_month_usd / money.budget_month_usd) * 100)) : null;
  return (
    <Card as="section" className="flex flex-col gap-2 p-4" aria-label="پول">
      <SectionTitle title="پول" action={<span className="flex items-center gap-3"><Link href="/services" className="text-[12px] font-semibold text-gold-ink hover:underline">سرویس‌های هاب</Link><Link href="/revenue" className="text-[12px] font-semibold text-gold-ink hover:underline">درآمد</Link></span>} />
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

/** The whole office from `GET /office`. */
export function OfficeBody({ o }: { o: Office }) {
  return (
    <>
      {/* ⟨1.24⟩ OF-1: is the holding working, and is anything waiting for the owner? */}
      <OfficePulse />
      <CommandBar />
      <CriticalCard items={o.critical} />
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <OfficeSessions sessions={o.sessions} />
          {/* ⟨1.24⟩ CO-1: one live card per company, the busiest first. */}
          <LiveCompanies />
          <OfficeCanvas canvas={o.canvas} sessions={o.sessions} />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <OfficeApprovals items={o.approvals} total={o.approvals_total} />
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
