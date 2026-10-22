'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useRef, useState, useSyncExternalStore, type ReactNode, type RefObject } from 'react';
import { Icon } from '@/components/icon';
import type { IconName } from '@/generated/icons';
import { CompanyMark, Monogram } from '@/components/brand/marks';
import { Seal } from '@/components/brand/seal';
import { Composer } from '@/components/media/composer';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Bar, Card, Empty, ErrorState, FilterChip, Pill, SectionTitle, Skeleton, Switch, budgetTone } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { rruleFa } from '@/components/v14/bits';
import { Prose } from '@/components/v16/bits';
import { useCompanies } from '@/lib/api/hooks';
import type { Actor } from '@/lib/api/v13';
import {
  faError, useMeetingAction, useMeetingSettings, useMeetings, useSaveMeetingSettings,
  type Meeting, type MeetingItem, type MeetingType, type MeetingTypeKey, type OwnerPresence, type Turn, type Whisper,
} from '@/lib/api/v17';
import { companyOf } from '@/lib/company';
import { useNow } from '@/lib/store';
import { cx, jDate, jTime, jWeekday, tokens, until } from '@/lib/format';
import { ACTOR_ROLE_FA, ActorAvatar, CLAIM_STATUS, MEETING_STATE, MEETING_TYPE, PRESENCE_FA, RefChip, VOTE_FA, budgetFig, pctOf } from './bits';

// A second clock for the room's timers; 0 on the server (timers render client-side only).
let sec = typeof window === 'undefined' ? 0 : Date.now();
const secSubs = new Set<() => void>();
let secTimer: ReturnType<typeof setInterval> | undefined;
const subscribeSec = (l: () => void) => {
  secSubs.add(l);
  if (!secTimer) secTimer = setInterval(() => { sec = Date.now(); secSubs.forEach((f) => f()); }, 1000);
  return () => { secSubs.delete(l); if (!secSubs.size && secTimer) { clearInterval(secTimer); secTimer = undefined; } };
};
const useSeconds = () => useSyncExternalStore(subscribeSec, () => sec, () => 0);
const mmss = (ms: number) => { const s = Math.max(0, Math.round(ms / 1000)); return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; };

const field = 'h-10 rounded-[10px] border border-strong bg-tile px-3 text-[13px] text-ink outline-none focus:border-gold-ink';
const sorted = (m: Meeting) => [...m.items].sort((a, b) => a.n - b.n);
export const currentItem = (m: Meeting) => sorted(m).find((x) => x.state === 'round_1' || x.state === 'round_2') ?? null;
const SPEAKING = new Set(['statement', 'challenge', 'vote']);

/** Who spoke in the current round of an item, and who is still in the queue (the devil's advocate last, by rule). */
function queueOf(m: Meeting, it: MeetingItem | null, turns: Turn[]) {
  if (!it) return { spoke: new Set<string>(), queue: [] as Actor[] };
  const spoke = new Set(turns.filter((t) => t.item === it.id && t.round === it.round && SPEAKING.has(t.kind)).map((t) => t.speaker.code));
  const devils = new Set(m.participants.filter((p) => p.devil).map((p) => p.actor.code));
  const order = [...it.speakers].sort((a, b) => Number(devils.has(a.code)) - Number(devils.has(b.code)));
  return { spoke, queue: order.filter((s) => !spoke.has(s.code)) };
}

function TypeMark({ m, size = 44 }: { m: Meeting; size?: number }) {
  const { data: companies } = useCompanies();
  const co = companyOf(companies, m.company);
  return <Seal code={m.company} nameFa={co.nameFa} nameEn={co.nameEn} holding={co.holding} state="sealed" size={size} />;
}

// ------------------------------------------------------------------ header --
function RoomHeader({ m, actions, tone }: { m: Meeting; actions?: ReactNode; tone?: 'war' }) {
  const s = useSeconds();
  const st = MEETING_STATE[m.state] ?? { fa: m.state, tone: 'neutral' as const };
  const t = MEETING_TYPE[m.type];
  const cap = m.budget.cap;
  const used = m.state === 'scheduled' || m.state === 'prep' ? m.budget.estimate : m.budget.used;
  const share = pctOf(used, cap);
  return (
    <Card className={cx('flex flex-wrap items-center gap-x-5 gap-y-4 p-4 md:p-5', tone === 'war' && 'bg-neg-soft ring-1 ring-[var(--hq-neg-line)]')}>
      <div className="flex min-w-0 flex-[1_1_18rem] items-center gap-3">
        <TypeMark m={m} />
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-[12px] text-muted">اتاق جلسه · {t?.fa ?? m.type} · {jWeekday(m.starts_at)}، {jTime(m.starts_at)} <span className="fig whitespace-nowrap">{m.ref}</span></span>
          <h1 className="text-h2 font-semibold text-ink">{m.title_fa}</h1>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Pill tone={st.tone} live={st.live} dot={!st.live}>{st.fa}{st.live && s ? <span className="fig">· {mmss(s - Date.parse(m.starts_at))}</span> : null}</Pill>
        {m.mode === 'written' ? <Pill tone="warn" icon="report">نوشتاری</Pill> : null}
        <div className="flex w-48 flex-col gap-1">
          <span className="flex items-baseline justify-between gap-2 text-[11px] text-muted"><span>{m.state === 'scheduled' || m.state === 'prep' ? 'برآورد توکن' : 'بودجه‌ی توکن جلسه'}</span><span className="fig text-sec">{cap == null ? `${tokens(used)} · بی‌سقف` : budgetFig(used, cap)}</span></span>
          <Bar pct={cap == null ? 0 : share} tone={cap == null ? 'silver' : budgetTone(share)} label="مصرف بودجه‌ی جلسه" />
        </div>
      </div>
      {actions ? <div className="flex w-full flex-wrap items-center gap-2 lg:w-auto">{actions}</div> : null}
    </Card>
  );
}

// ---------------------------------------------------------------- round table --
type Seat = { actor: Actor; role: string; status: string; tone: 'gold' | 'learn' | 'muted' | 'ink'; speaking?: boolean; owner?: boolean; devil?: boolean };
function seatsOf(m: Meeting, it: MeetingItem | null, turns: Turn[]): Seat[] {
  const { spoke, queue } = queueOf(m, it, turns);
  const liveNow = m.state === 'live' && m.mode === 'discussion';
  const status = (a: Actor, devil: boolean): Pick<Seat, 'status' | 'tone' | 'speaking'> => {
    if (liveNow && queue[0]?.code === a.code) return { status: 'در حال صحبت', tone: 'gold', speaking: true };
    if (liveNow && queue[1]?.code === a.code) return { status: 'نوبت بعد', tone: 'ink' };
    if (devil) return { status: 'مخالف‌خوان', tone: 'learn' };
    const mine = turns.filter((t) => it && t.item === it.id && t.speaker.code === a.code).flatMap((t) => t.claims);
    if (spoke.has(a.code) && mine.length) return { status: `${mine.length} ادعا، ${mine.filter((c) => c.status === 'sourced').length} منبع`, tone: 'muted' };
    return { status: it?.speakers.some((s) => s.code === a.code) ? 'منتظر نوبت' : 'بیانیه‌ی نوشته', tone: 'muted' };
  };
  const owner: Seat = { actor: { kind: 'owner', code: 'owner', display_fa: 'مالک' }, role: 'مالک', status: `گوش میدهد · ${PRESENCE_FA[m.owner_presence]?.fa ?? m.owner_presence}`, tone: 'gold', owner: true };
  const ps = m.participants.map((p) => ({ actor: p.actor, role: p.role_fa, devil: p.devil, speaker: p.speaker }));
  const seat = (p: (typeof ps)[number]): Seat => (p.speaker ? { actor: p.actor, role: p.role, devil: p.devil, ...status(p.actor, p.devil) } : { actor: p.actor, role: p.role, status: 'فقط برای تو', tone: 'gold' });
  return [owner, ...ps.filter((p) => p.speaker && !p.devil).map(seat), ...ps.filter((p) => !p.speaker).map(seat), ...ps.filter((p) => p.devil).map(seat)];
}

function SeatView({ s, size, compact }: { s: Seat; size: number; compact?: boolean }) {
  return (
    <div className={cx('flex flex-none flex-col items-center gap-1 text-center', compact ? 'w-[92px]' : 'w-[120px]')}>
      <span className={cx('rounded-full p-[3px]', s.speaking && 'ring-2 ring-[var(--hq-gold-ink)]')} style={s.speaking ? { animation: 'hq-breath 2.4s ease-in-out infinite' } : undefined}>
        <ActorAvatar a={s.actor} size={size} />
      </span>
      <span className="flex items-center gap-1 text-[12px] font-semibold text-ink">{s.speaking ? <span className="text-gold-ink"><Icon name="mic" size={12} /></span> : null}{s.actor.display_fa ?? s.actor.code}</span>
      <span className={cx('text-[11px]', s.tone === 'gold' ? 'text-gold-ink' : s.tone === 'learn' ? 'text-learn' : s.tone === 'ink' ? 'text-sec' : 'text-muted')}>{s.status}</span>
    </div>
  );
}

function TableCenter({ m, it, start, rounds, compact }: { m: Meeting; it: MeetingItem | null; start: number | null; rounds: number; compact?: boolean }) {
  const s = useSeconds();
  const items = sorted(m).filter((x) => x.state !== 'skipped');
  return (
    <div className={cx('flex flex-col items-center justify-center gap-0.5 text-center', compact ? 'rounded-[18px] px-4 py-5' : 'h-full w-full rounded-[50%] px-[9%]')} style={{ background: 'var(--hq-lapis-disc)', boxShadow: 'inset 0 0 0 1.5px var(--hq-gold-ink), inset 0 0 0 9px var(--hq-lapis-disc), inset 0 0 0 10px rgba(201,162,74,.35)' }}>
      {it ? (
        <>
          <span className="text-[11px] text-[#AEB8CF]">دستور {it.n} از {items.length}، دور {it.round} از {rounds}</span>
          <span className="line-clamp-2 text-[13px] font-semibold leading-6 text-[#EEF1F8] md:text-[14px]">{it.title_fa}</span>
          <span className="fig text-[24px] font-bold leading-8 text-[var(--hq-gold-bright)]">{s ? mmss(it.time_box_min * 60_000 - (s - (start ?? Date.parse(m.starts_at)))) : '—'}</span>
          <span className="text-[10px] text-[#AEB8CF]">باقی‌مانده از وقت این دستور</span>
        </>
      ) : <span className="text-[13px] text-[#AEB8CF]">{m.state === 'live' ? 'همه‌ی دستورها تمام شد؛ جلسه را ببند.' : MEETING_STATE[m.state]?.fa}</span>}
    </div>
  );
}
function RoundTable({ m, it, turns, rounds }: { m: Meeting; it: MeetingItem | null; turns: Turn[]; rounds: number }) {
  const seats = seatsOf(m, it, turns);
  // The item's clock starts at its first turn (the hub runs the time box; the room reads it from the turns).
  const mine = it ? turns.filter((t) => t.item === it.id).map((t) => Date.parse(t.at)) : [];
  const start = mine.length ? Math.min(...mine) : null;
  // Owner at the top, the devil's advocate opposite; the rest split between the two sides, the start side first.
  const [owner, ...rest] = seats;
  const devil = rest.at(-1)?.devil ? rest.pop()! : null;
  const right = rest.slice(0, Math.ceil(rest.length / 2));
  const left = rest.slice(right.length);
  const place = (a: number) => ({ left: `${50 + 40 * Math.cos((a * Math.PI) / 180)}%`, top: `${50 + 39 * Math.sin((a * Math.PI) / 180)}%` });
  const at: Array<[Seat, number]> = [[owner!, -90], ...right.map((s, i) => [s, -90 + (180 * (i + 1)) / (right.length + 1)] as [Seat, number]), ...(devil ? [[devil, 90] as [Seat, number]] : []), ...left.map((s, i) => [s, 90 + (180 * (i + 1)) / (left.length + 1)] as [Seat, number])];
  return (
    <>
      <div className="relative mx-auto hidden aspect-[16/10.5] w-full max-w-[700px] sm:block" aria-label="میز گرد">
        <div className="absolute left-1/2 top-1/2 aspect-[1.55] w-[48%] -translate-x-1/2 -translate-y-1/2"><TableCenter m={m} it={it} start={start} rounds={rounds} /></div>
        {at.map(([s, a]) => <div key={s.actor.code} className="absolute -translate-x-1/2 -translate-y-1/2" style={place(a)}><SeatView s={s} size={48} /></div>)}
      </div>
      <div className="flex flex-col gap-3 sm:hidden">
        <TableCenter m={m} it={it} start={start} rounds={rounds} compact />
        <div className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1" aria-label="حاضران">{seats.map((s) => <SeatView key={s.actor.code} s={s} size={40} compact />)}</div>
      </div>
    </>
  );
}

// ------------------------------------------------------------- the three cards --
function QueueCard({ m, it, turns }: { m: Meeting; it: MeetingItem | null; turns: Turn[] }) {
  const { queue } = queueOf(m, it, turns);
  const devils = new Set(m.participants.filter((p) => p.devil).map((p) => p.actor.code));
  const s = useSeconds();
  const last = turns.filter((t) => it && t.item === it.id).at(-1);
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="صف نوبت" note={it ? `دور ${it.round}` : undefined} />
      {!queue.length ? <p className="text-[12px] text-muted">{it ? 'این دور تمام شد؛ دور بعد یا دستور بعد با توست.' : 'دستوری در جریان نیست.'}</p> : (
        <ol className="flex flex-col gap-2">
          {queue.slice(0, 5).map((a, i) => (
            <li key={a.code} className="flex items-center gap-2.5">
              <span className="w-4 text-center text-[12px] text-muted">{i + 1}</span>
              <ActorAvatar a={a} size={28} />
              <span className="flex min-w-0 flex-1 flex-col"><span className="truncate text-[13px] font-semibold">{a.display_fa ?? a.code}</span><span className="text-[11px] text-muted">{i === 0 && m.state === 'live' ? 'در حال صحبت' : devils.has(a.code) ? `جمع‌بندی دور ${it?.round ?? 1}` : i === 1 ? 'نوبت بعد' : 'منتظر'}</span></span>
              {i === 0 && m.state === 'live' && s && last ? <span className="fig text-[12px] text-sec">{mmss(s - Date.parse(last.at))}</span> : null}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function ClaimsCard({ it, turns }: { it: MeetingItem | null; turns: Turn[] }) {
  const claims = turns.filter((t) => it && t.item === it.id).flatMap((t) => t.claims);
  const by = (k: string) => claims.filter((c) => c.status === k).length;
  const rows: Array<[string, number]> = [['sourced', by('sourced')], ['challenged', by('challenged')], ['unsourced', by('unsourced')]];
  const total = claims.length || 1;
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="ادعاها" note={`${claims.length} ادعا در این دستور`} />
      <div className="flex h-2 gap-[2px] overflow-hidden rounded-full" dir="ltr" aria-hidden>
        {rows.filter(([, n]) => n).map(([k, n]) => <span key={k} className={cx('h-full', k === 'sourced' ? 'bg-silver-ink' : k === 'challenged' ? 'bg-warn' : 'bg-neg')} style={{ width: `${(n / total) * 100}%` }} />)}
      </div>
      <ul className="flex flex-col gap-1.5">
        {rows.map(([k, n]) => {
          const c = CLAIM_STATUS[k]!;
          return <li key={k} className="flex items-center gap-2 text-[12px]"><span className={c.tone === 'pos' ? 'text-sec' : c.tone === 'warn' ? 'text-warn' : 'text-neg'}><Icon name={c.icon} size={14} /></span><span className="flex-1 text-sec">{c.fa}</span><span className="text-[13px] font-semibold text-ink">{n}</span></li>;
        })}
      </ul>
    </Card>
  );
}

function TokensCard({ turns }: { turns: Turn[] }) {
  const by = new Map<string, { a: Actor; n: number }>();
  for (const t of turns) if (t.tokens) by.set(t.speaker.code, { a: t.speaker, n: (by.get(t.speaker.code)?.n ?? 0) + t.tokens });
  const rows = [...by.values()].sort((a, b) => b.n - a.n);
  const max = Math.max(1, ...rows.map((r) => r.n));
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="توکن هر نفر" note={<span className="fig">{tokens(rows.reduce((a, r) => a + r.n, 0))}</span>} />
      <ul className="flex flex-col gap-2">
        {rows.slice(0, 6).map((r) => (
          <li key={r.a.code} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_auto] items-center gap-2 text-[12px]">
            <span className="truncate text-sec">{r.a.display_fa ?? r.a.code}</span>
            <span className="h-2 rounded-full bg-tile"><span className="block h-full rounded-full bg-silver-ink" style={{ width: `${(r.n / max) * 100}%` }} /></span>
            <span className="fig w-10 text-left text-ink">{tokens(r.n)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ------------------------------------------------------------------ side panel --
function Agenda({ m, pick, onPick }: { m: Meeting; pick: string | null; onPick: (id: string) => void }) {
  return (
    <ol className="flex flex-col gap-1">
      {sorted(m).map((x) => {
        const cur = x.state === 'round_1' || x.state === 'round_2';
        return (
          <li key={x.id}>
            <button type="button" onClick={() => onPick(x.id)} aria-pressed={pick === x.id} className={cx('flex w-full items-center gap-3 rounded-[10px] px-2 py-2 text-right transition-colors hover:bg-hover', pick === x.id && 'bg-hover')}>
              <span className={cx('flex size-7 flex-none items-center justify-center rounded-full text-[12px]', x.state === 'done' ? 'bg-silver-ink text-[var(--hq-text-on-silver)]' : cur ? 'ring-2 ring-[var(--hq-gold-ink)] text-gold-ink' : 'border border-strong text-muted')}>
                {x.state === 'done' ? <Icon name="seal" size={14} /> : cur ? <span className="size-2.5 rounded-full bg-gold-ink" /> : x.n}
              </span>
              <span className={cx('min-w-0 flex-1 text-[13px]', cur ? 'font-semibold text-ink' : x.state === 'skipped' ? 'text-muted line-through' : 'text-sec')}>{x.title_fa}</span>
              <span className="flex-none text-[11px] text-muted">{x.time_box_min} دقیقه</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function WhisperCard({ w }: { w: Whisper }) {
  return (
    <div className="flex gap-3 rounded-[14px] border border-[var(--hq-gold-ink)] bg-gold-soft p-3">
      <ActorAvatar a={{ kind: 'agent', code: 'HQ-ADV', display_fa: 'مشاور کل' }} size={24} />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="text-[12px] font-semibold text-ink">نجوای مشاور · فقط برای تو</span>
        <Md text={w.text_md} className="text-[13px] leading-6 text-sec" />
        {w.sources.length ? <div className="flex flex-wrap gap-1">{w.sources.map((s) => <RefChip key={s.ref} r={s.ref} note={s.note || null} tone="neutral" />)}</div> : null}
      </div>
    </div>
  );
}

function TurnView({ t, devil }: { t: Turn; devil: boolean }) {
  const flagged = t.claims.filter((c) => c.status === 'unsourced' || c.status === 'challenged');
  const v = t.stance ? VOTE_FA[t.stance.vote] : null;
  return (
    <li className={cx('flex gap-3 border-b border-div py-3 last:border-0', t.kind === 'owner' && '-mx-2 rounded-[12px] border-0 bg-gold-soft px-2')}>
      <ActorAvatar a={t.speaker} size={28} />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13px] font-semibold text-ink">{t.kind === 'owner' ? 'تو' : t.speaker.display_fa ?? t.speaker.code}</span>
          {devil ? <Pill tone="learn" className="h-5 text-[11px]">مخالف‌خوان</Pill> : null}
          {t.kind === 'challenge' ? <Pill tone="warn" className="h-5 text-[11px]">چالش</Pill> : null}
          {v ? <Pill tone={v.tone} dot className="h-5 text-[11px]">{v.fa}</Pill> : null}
          <span className="mr-auto text-[11px] text-muted">{jTime(t.at)}</span>
        </div>
        <Md text={t.statement_md} className="text-[13px] leading-6 text-sec" />
        {t.stance?.reason_fa ? <span className="text-[12px] text-muted">«{t.stance.reason_fa}»</span> : null}
        {t.draft_md ? <div className="rounded-[10px] bg-tile p-2 text-[12px] leading-6"><span className="font-semibold text-gold-ink">پیش‌نویس مصوبه: </span><span className="text-ink">{t.draft_md}</span></div> : null}
        {t.claims.some((c) => c.status === 'sourced') ? (
          <div className="flex flex-wrap gap-1.5">{t.claims.filter((c) => c.status === 'sourced' && c.source).map((c) => <RefChip key={c.id} r={c.source!.ref} />)}</div>
        ) : null}
        {flagged.map((c) => (
          <p key={c.id} className="flex items-start gap-1.5 rounded-[8px] bg-neg-soft px-2 py-1 text-[12px] leading-5 text-ink">
            <span className="mt-0.5 text-neg"><Icon name="urgent" size={12} /></span>
            <span>«{c.text_fa}» {c.status === 'challenged' ? 'به چالش کشیده شد' : 'منبع ندارد'}؛ تا منبع نیاید در صورت‌جلسه و مصوبه نمیاید.</span>
          </p>
        ))}
      </div>
    </li>
  );
}

function Transcript({ m, turns, item }: { m: Meeting; turns: Turn[]; item: string | null }) {
  const devils = new Set(m.participants.filter((p) => p.devil).map((p) => p.actor.code));
  const xs = turns.filter((t) => !item || t.item === item);
  if (!xs.length) return <p className="py-3 text-[12px] text-muted">در این دستور هنوز کسی حرف نزده.</p>;
  return <ul className="flex flex-col">{xs.map((t) => <TurnView key={t.id} t={t} devil={devils.has(t.speaker.code)} />)}</ul>;
}

function Drafts({ m }: { m: Meeting }) {
  const ds = m.drafts ?? [];
  if (!ds.length) return <p className="text-[12px] text-muted">هنوز پیش‌نویسی نیامده.</p>;
  return (
    <ul className="flex flex-col gap-2">
      {ds.map((d, i) => {
        const it = m.items.find((x) => x.id === d.item);
        const voted = d.votes.support + d.votes.oppose + d.votes.abstain;
        return (
          <li key={d.id} className="flex flex-col gap-2 rounded-[14px] bg-tile p-3">
            <span className="flex flex-wrap items-center justify-between gap-2 text-[11px]"><span className="font-semibold text-gold-ink">پیش‌نویس مصوبه {i + 1}</span><span className="text-muted">{voted ? <>رأی‌ها: {d.votes.support} موافق، {d.votes.oppose} مخالف، {d.votes.abstain} ممتنع</> : it?.state === 'round_1' ? 'رأی در دور ۲' : it?.state === 'round_2' ? 'در حال رأی' : 'بی‌رأی'}</span></span>
            <Md text={d.text_md} className="text-[13px] leading-6 text-ink" />
            <span className="flex items-center gap-2 text-[11px] text-muted">
              <Seal code="HQ" nameFa="هلدینگ" nameEn="Holding" holding state={d.decision ? 'sealed' : 'ready'} size={28} />
              {d.decision ? <>به کارتابل رفت: <RefChip r={d.decision} /></> : 'بعد از رأی به کارتابل میرود؛ مُهر هلدینگ'}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

// ------------------------------------------------------------------ live room --
function LiveControls({ m, it, onWrite }: { m: Meeting; it: MeetingItem | null; onWrite: () => void }) {
  const act = useMeetingAction();
  const toast = useToast();
  const [raise, setRaise] = useState(false);
  const [end, setEnd] = useState(false);
  const [extra, setExtra] = useState(20_000);
  const hasDraft = !!it && (m.drafts ?? []).some((d) => d.item === it.id);
  const run = (body: Parameters<typeof act.control.mutateAsync>[0]['body'], ok: string) =>
    act.control.mutateAsync({ ref: m.ref, body }).then(() => { toast({ tone: 'ok', text: ok }); return true; }).catch((e) => { toast({ tone: 'error', text: faError(e) }); return false; });
  return (
    <>
      <Button size="sm" variant="secondary" icon="edit" onClick={onWrite}>نوشتن</Button>
      <Button size="sm" variant="secondary" iconEnd="back" loading={act.control.isPending && act.control.variables?.body.action === 'next_round'} disabled={!it}
        onClick={() => void run({ action: 'next_round' }, it && it.round < 2 && hasDraft ? 'دور ۲ شروع شد: رأی روی پیش‌نویس.' : 'دستور بعد شروع شد.')}>{it && it.round < 2 && hasDraft ? 'رفتن به دور ۲' : 'دستور بعد'}</Button>
      <Button size="sm" variant="ghost" icon="next" disabled={!it} onClick={() => void run({ action: 'skip_item' }, 'این دستور رد شد.')}>رد کردن دستور</Button>
      <Button size="sm" variant="ghost" icon="budget" onClick={() => setRaise(true)}>افزایش بودجه</Button>
      <Button size="sm" variant="danger" onClick={() => setEnd(true)}>پایان جلسه</Button>
      <Button size="sm" variant="primary" icon="mic" onClick={onWrite}>ورود صوتی</Button>
      <Dialog open={raise} onOpenChange={setRaise} title="افزایش بودجه‌ی جلسه" actions={<>
        <Button variant="primary" loading={act.control.isPending} onClick={() => void run({ action: 'raise_budget', tokens: extra }, 'بودجه بیشتر شد.').then((ok) => ok && setRaise(false))}>اضافه کن</Button>
        <Button variant="secondary" onClick={() => setRaise(false)}>انصراف</Button>
      </>}>
        <div className="flex flex-col gap-3">
          <p>فقط تو بودجه را بالا میبری. مقدار تازه از سقف روزانه‌ی ایجنت‌ها رزرو میشود.</p>
          <div className="flex flex-wrap gap-2">{[10_000, 20_000, 40_000].map((n) => <FilterChip key={n} selected={extra === n} onClick={() => setExtra(n)}><span className="fig">+{tokens(n)}</span></FilterChip>)}</div>
        </div>
      </Dialog>
      <Dialog open={end} onOpenChange={setEnd} title="پایان جلسه" actions={<>
        <Button variant="danger" loading={act.control.isPending} onClick={() => void run({ action: 'end' }, 'جلسه بسته شد؛ صورت‌جلسه و کارت مصوبه‌ها ساخته شد.').then((ok) => ok && setEnd(false))}>ببند</Button>
        <Button variant="secondary" onClick={() => setEnd(false)}>انصراف</Button>
      </>}>
        <p>صورت‌جلسه را کد میسازد و منشی خلاصه را فقط از ادعاهای منبع‌دار مینویسد. هر پیش‌نویس یک کارت «مصوبه‌ی جلسه» در کارتابل میشود و فقط با مُهر تو مصوبه است.</p>
      </Dialog>
    </>
  );
}

function SpeakBox({ m, box }: { m: Meeting; box: RefObject<HTMLDivElement | null> }) {
  const act = useMeetingAction();
  const toast = useToast();
  const key = useRef<string | null>(null);
  return (
    <div ref={box} className="flex flex-col gap-1.5 scroll-mt-24">
      <span className="text-[12px] font-semibold text-sec">نوبت تو · صف را جلو میزند</span>
      <Composer placeholder="با متن یا صدا وارد شو…" allowFiles={false} label="حرف تو در جلسه" sending={act.speak.isPending}
        onSend={async ({ body, attachments }) => {
          key.current ??= crypto.randomUUID();
          try {
            await act.speak.mutateAsync({ ref: m.ref, text: body || undefined, file_id: attachments[0] ?? null, key: key.current });
            key.current = null;
            toast({ tone: 'ok', text: 'حرفت در جلسه ثبت شد؛ نوبت بعد جواب میدهد.' });
          } catch (e) { toast({ tone: 'error', text: faError(e) }); throw e; }
        }} />
    </div>
  );
}

export function LiveRoom({ m, turns, whispers }: { m: Meeting; turns: Turn[]; whispers: Whisper[] }) {
  const it = currentItem(m);
  const [pick, setPick] = useState<string | null>(null);
  const shown = pick ?? it?.id ?? null;
  const box = useRef<HTMLDivElement>(null);
  const settings = useMeetingSettings();
  const t = settings.data?.find((x) => x.key === m.type);
  const whisper = [...whispers].reverse().find((w) => w.item === (it?.id ?? shown)) ?? whispers.at(-1);
  const write = () => { box.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }); box.current?.querySelector('textarea')?.focus(); };
  return (
    <>
      <RoomHeader m={m} actions={m.state === 'live' ? <LiveControls m={m} it={it} onWrite={write} /> : null} />
      {m.mode === 'written' ? <p className="rounded-[12px] bg-warn-soft p-3 text-[13px] text-ink">این جلسه نوشتاری است: از سهم روزانه‌ی جلسه‌ها چیزی نمانده بود؛ فقط بیانیه‌های نوشته‌شده، بی‌دور بحث.</p> : null}
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="p-3 md:p-5"><RoundTable m={m} it={it} turns={turns} rounds={t?.max_rounds ?? 2} /></Card>
          <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr))]">
            <QueueCard m={m} it={it} turns={turns} />
            <ClaimsCard it={it} turns={turns} />
            <TokensCard turns={turns} />
          </div>
          <p className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted">
            <span className="font-semibold text-sec">قاعده‌های این جلسه</span>
            <span>حداکثر {t?.max_rounds ?? 2} دور بحث</span><span>حداکثر {t?.max_speakers ?? 6} سخنگو در هر دستور</span><span>هر ادعا با منبع</span><span>مخالف‌خوان از نظارت</span><span>تو هر وقت بخواهی نوبت را میگیری</span>
          </p>
        </div>
        <Card className="flex min-w-0 flex-col gap-5 p-4">
          <section className="flex flex-col gap-1"><h2 className="text-[14px] font-semibold">دستور جلسه</h2><Agenda m={m} pick={shown} onPick={setPick} /></section>
          {whisper ? <WhisperCard w={whisper} /> : null}
          <section className="flex flex-col gap-1">
            <h2 className="text-[14px] font-semibold">متن زنده{shown !== it?.id && shown ? <span className="font-normal text-muted"> · دستور {m.items.find((x) => x.id === shown)?.n}</span> : null}</h2>
            <Transcript m={m} turns={turns} item={shown} />
          </section>
          {m.state === 'live' ? <SpeakBox m={m} box={box} /> : null}
          <section className="flex flex-col gap-2"><h2 className="text-[14px] font-semibold">مصوبه‌ها</h2><Drafts m={m} /></section>
          <p className="text-[11px] leading-5 text-muted">رأی مدیرها جای امضای تو را نمیگیرد؛ هر مصوبه با مُهر تو قانونی و وارد پلنرها میشود.</p>
        </Card>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ prep room --
export function PrepRoom({ m }: { m: Meeting }) {
  const act = useMeetingAction();
  const toast = useToast();
  const now = useNow();
  const [order, setOrder] = useState<string[] | null>(null);
  const [skip, setSkip] = useState<Record<string, boolean>>({});
  const [cap, setCap] = useState('');
  const [presence, setPresence] = useState<OwnerPresence | null>(null);
  const base = sorted(m);
  const ids = order ?? base.map((x) => x.id);
  const items = ids.map((id) => base.find((x) => x.id === id)!).filter(Boolean);
  const skipped = (x: MeetingItem) => skip[x.id] ?? x.state === 'skipped';
  const capN = cap.trim() ? Math.round(Number(cap) * 1000) : null;
  const dirty = !!order || Object.keys(skip).length > 0 || capN != null || (presence != null && presence !== m.owner_presence);
  const capBad = capN != null && (!Number.isFinite(capN) || capN <= 0 || (m.budget.cap != null && capN > m.budget.cap));
  const move = (i: number, d: -1 | 1) => { const xs = [...ids]; const j = i + d; if (j < 0 || j >= xs.length) return; [xs[i], xs[j]] = [xs[j]!, xs[i]!]; setOrder(xs); };
  const save = () => act.patch.mutateAsync({ m, patch: {
    ...(order || Object.keys(skip).length ? { items: items.map((x, i) => ({ id: x.id, n: i + 1, skip: skipped(x) })) } : {}),
    ...(capN != null ? { budget_cap: capN } : {}),
    ...(presence && presence !== m.owner_presence ? { owner_presence: presence } : {}),
  } }).then(() => { toast({ tone: 'ok', text: 'دستور جلسه ذخیره شد؛ برآورد دوباره حساب شد.' }); setOrder(null); setSkip({}); setCap(''); setPresence(null); }).catch((e) => toast({ tone: 'error', text: faError(e) }));
  const share = pctOf(m.budget.estimate, m.budget.cap);
  return (
    <>
      <RoomHeader m={m} actions={<Button size="sm" variant="primary" icon="seal" disabled={!dirty || capBad} loading={act.patch.isPending} onClick={() => void save()}>ذخیره‌ی دستور</Button>} />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="flex min-w-0 flex-col gap-3 p-4 md:p-5">
          <SectionTitle title="دستور جلسه" note="دستور را کد ساخته؛ تو جابه‌جا یا حذفش میکنی" />
          <ol className="flex flex-col gap-2">
            {items.map((x, i) => (
              <li key={x.id} className={cx('flex flex-col gap-2 rounded-[14px] border border-div p-3', skipped(x) && 'opacity-55')}>
                <div className="flex items-start gap-2">
                  <span className="flex size-7 flex-none items-center justify-center rounded-full border border-strong text-[12px] text-sec">{i + 1}</span>
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <span className={cx('text-[14px] font-semibold text-ink', skipped(x) && 'line-through')}>{x.title_fa}</span>
                    <Md text={x.brief_md} className="text-[12px] leading-6 text-sec" />
                  </div>
                  <div className="flex flex-none items-center gap-0.5">
                    <Button size="sm" variant="ghost" aria-label="بالاتر" disabled={i === 0} onClick={() => move(i, -1)}><span className="inline-block rotate-180"><Icon name="chevron" size={14} /></span></Button>
                    <Button size="sm" variant="ghost" aria-label="پایین‌تر" disabled={i === items.length - 1} onClick={() => move(i, 1)}><Icon name="chevron" size={14} /></Button>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2 ps-9 text-[12px] text-muted">
                  <span>{x.time_box_min} دقیقه</span>
                  <span className="flex -space-x-1.5 space-x-reverse">{x.speakers.map((s) => <span key={s.code} title={s.display_fa ?? s.code}><ActorAvatar a={s} size={22} /></span>)}</span>
                  <span className="flex flex-wrap gap-1">{x.sources.map((s) => <RefChip key={s.ref} r={s.ref} note={s.note || null} tone="neutral" />)}</span>
                  <span className="mr-auto flex items-center gap-2"><span>در دستور</span><Switch checked={!skipped(x)} onChange={(v) => setSkip((o) => ({ ...o, [x.id]: !v }))} label={`در دستور: ${x.title_fa}`} /></span>
                </div>
              </li>
            ))}
          </ol>
        </Card>
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title="بودجه، پیش از شروع" note={now ? `شروع ${until(m.starts_at, now)}` : undefined} />
            <div className="flex items-baseline justify-between text-[13px]"><span className="text-sec">برآورد</span><span className="fig font-semibold text-ink">{budgetFig(m.budget.estimate, m.budget.cap)}</span></div>
            <Bar pct={share} tone={budgetTone(share)} label="برآورد در برابر بودجه" />
            {m.trimmed_fa ? <p className="flex items-start gap-2 rounded-[12px] bg-warn-soft p-3 text-[12px] leading-6 text-ink"><span className="text-warn"><Icon name="info" size={16} /></span><span><Prose text={m.trimmed_fa} /></span></p> : null}
            <label className="flex flex-col gap-1 text-[12px] text-sec">کم کردن بودجه (هزار توکن)
              <input inputMode="numeric" dir="ltr" value={cap} onChange={(e) => setCap(e.target.value.replace(/[^\d.]/g, ''))} placeholder={m.budget.cap != null ? String(m.budget.cap / 1000) : '—'} className={cx(field, 'fig', capBad && 'border-[var(--hq-neg-line)]')} />
              {capBad ? <span className="text-neg">فقط کمتر از سقف فعلی؛ افزایش فقط در جلسه‌ی زنده و با خود تو.</span> : <span className="text-muted">موقع شروع از سقف روزانه‌ی ایجنت‌ها رزرو میشود.</span>}
            </label>
          </Card>
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title="حضور تو" />
            <div className="flex flex-wrap gap-2">{(['live', 'summary', 'audio'] as const).map((k) => <FilterChip key={k} selected={(presence ?? m.owner_presence) === k} onClick={() => setPresence(k)}>{PRESENCE_FA[k]!.fa}</FilterChip>)}</div>
            <p className="text-[12px] text-muted">{PRESENCE_FA[presence ?? m.owner_presence]?.note}</p>
          </Card>
          <Card className="flex flex-col gap-2 p-4">
            <SectionTitle title="حاضران" note="سخنگوها با قاعده؛ بقیه بیانیه‌ی نوشته" />
            <ul className="flex flex-col gap-2">
              {m.participants.map((p) => (
                <li key={p.actor.code} className="flex items-center gap-2.5"><ActorAvatar a={p.actor} size={28} /><span className="flex-1 text-[13px]">{p.role_fa}</span>{p.devil ? <Pill tone="learn" className="h-5 text-[11px]">مخالف‌خوان</Pill> : !p.speaker ? <Pill className="h-5 text-[11px]">فقط برای تو</Pill> : null}</li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ minutes --
export function MinutesRoom({ m, turns }: { m: Meeting; turns: Turn[] }) {
  const done = m.items.filter((x) => x.state === 'done').length;
  return (
    <>
      <RoomHeader m={m} />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex flex-col gap-3 p-4 md:p-5">
            <SectionTitle title="خلاصه‌ی جلسه" note="نوشته‌ی منشی، فقط از ادعاهای منبع‌دار" action={m.minutes ? <RefChip r={m.minutes.deliverable} note="صورت‌جلسه" /> : null} />
            {m.minutes ? <Md text={m.minutes.summary_md} /> : <Empty icon="report" title={m.state === 'cancelled' ? 'جلسه لغو شد' : 'صورت‌جلسه هنوز ساخته نشده'} />}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted"><span>{done} دستور بررسی شد</span><span>توکن <span className="fig text-sec">{budgetFig(m.budget.used, m.budget.cap)}</span></span><span>{jDate(m.starts_at, true)}</span></div>
          </Card>
          <Card className="flex flex-col gap-2 p-4 md:p-5">
            <SectionTitle title="متن جلسه" note="با ادعاها و پرچم‌های بازرس" />
            {sorted(m).map((x) => (
              <details key={x.id} className="group rounded-[12px] border border-div p-3" open={x.id === turns.find((t) => t.item)?.item}>
                <summary className="flex cursor-pointer list-none items-center gap-2 text-[13px] font-semibold"><span className="text-muted">{x.n}.</span><span className={cx('flex-1', x.state === 'skipped' && 'text-muted line-through')}>{x.title_fa}</span><span className="text-[11px] font-normal text-muted">{turns.filter((t) => t.item === x.id).length} نوبت</span></summary>
                <Transcript m={m} turns={turns} item={x.id} />
              </details>
            ))}
          </Card>
        </div>
        <Card className="flex min-w-0 flex-col gap-3 p-4">
          <h2 className="text-[14px] font-semibold">مصوبه‌ها</h2>
          <Drafts m={m} />
          <p className="text-[11px] leading-5 text-muted">هر پیش‌نویس یک کارت «مصوبه‌ی جلسه» است؛ فقط مُهر تو مصوبه و کار پیگیری میسازد.</p>
        </Card>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ war room --
export function WarRoom({ m, turns }: { m: Meeting; turns: Turn[] }) {
  const pm = useMeetings({ type: 'postmortem' });
  const post = pm.data?.find((x) => x.incident && x.incident === m.incident && x.ref !== m.ref);
  const { data: companies } = useCompanies();
  const box = useRef<HTMLDivElement>(null);
  const icon = (t: Turn): IconName => (t.speaker.kind === 'system' ? 'urgent' : /مهار|تأیید/.test(t.statement_md) ? 'seal' : /علت/.test(t.statement_md) ? 'search' : 'server');
  return (
    <>
      <RoomHeader m={m} tone="war" />
      <Card className="flex flex-col gap-4 p-4 ring-1 ring-[var(--hq-neg-line)] md:p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-neg"><Icon name="urgent" size={20} /></span>
          <span className="text-[15px] font-semibold">اتاق جنگ · {companyOf(companies, m.company).nameFa}</span>
          {m.incident ? <RefChip r={m.incident} tone="neg" /> : null}
          <span className="text-[12px] text-muted">از {jTime(m.starts_at)} · اولویت <span className="fig">P0</span> · بی‌سقف جلسه، داخل سقف روزانه و کلید توقف</span>
          <span className="flex-1" />
          <Pill tone={m.state === 'ended' ? 'pos' : 'neg'} dot live={m.state === 'live'}>{m.state === 'ended' ? 'مهار شد' : 'در جریان'}</Pill>
        </div>
        <div className="grid gap-5 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <section className="flex flex-col gap-2">
            <h2 className="text-[14px] font-semibold">خط زمانی</h2>
            <ol className="flex flex-col gap-2.5">
              {turns.map((t) => (
                <li key={t.id} className="flex items-start gap-3 text-[13px]">
                  <span className="fig w-11 flex-none pt-0.5 text-[12px] text-muted">{jTime(t.at)}</span>
                  <span className={cx('pt-0.5', t.speaker.kind === 'system' ? 'text-neg' : 'text-gold-ink')}><Icon name={icon(t)} size={16} /></span>
                  <span className="flex min-w-0 flex-1 flex-col gap-1"><Md text={t.statement_md} className="text-[13px] leading-6 text-ink" /><span className="flex flex-wrap gap-1">{t.claims.filter((c) => c.source).map((c) => <RefChip key={c.id} r={c.source!.ref} tone="neutral" />)}</span></span>
                </li>
              ))}
            </ol>
          </section>
          <section className="flex flex-col gap-2">
            <h2 className="text-[14px] font-semibold">حاضران</h2>
            <ul className="flex flex-col gap-2">{m.participants.map((p) => <li key={p.actor.code} className="flex items-center gap-2.5"><ActorAvatar a={p.actor} size={28} /><span className="text-[13px]">{p.role_fa}</span></li>)}</ul>
            <p className="pt-2 text-[12px] leading-6 text-muted">
              {post ? <>کالبدشکافی {jWeekday(post.starts_at)} {jTime(post.starts_at)} در پلنر ثبت شد (<Link href={`/meetings/${post.ref}`} className="fig text-gold-ink">{post.ref}</Link>). </> : null}
              هر مهار بیرونی یک کارت A3 است. هشدار فوری حتی در خلوت میرسد.
            </p>
          </section>
        </div>
        {m.minutes ? <div className="rounded-[12px] bg-tile p-3"><Md text={m.minutes.summary_md} className="text-[13px] leading-6 text-sec" /></div> : null}
        {m.state === 'live' ? <SpeakBox m={m} box={box} /> : null}
      </Card>
    </>
  );
}

// ------------------------------------------------------------------ the list --
function MeetingRow({ m }: { m: Meeting }) {
  const t = MEETING_TYPE[m.type];
  const st = MEETING_STATE[m.state] ?? { fa: m.state, tone: 'neutral' as const };
  const now = useNow();
  const over = m.budget.cap != null && m.budget.estimate > m.budget.cap;
  return (
    <Link href={`/meetings/${m.ref}`} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-[12px] px-3 py-3 transition-colors hover:bg-hover">
      <span className={cx('flex size-9 flex-none items-center justify-center rounded-[10px] bg-tile', m.type === 'war_room' ? 'text-neg' : 'text-gold-ink')}><Icon name={t?.icon ?? 'meeting'} size={18} /></span>
      <span className="flex min-w-0 flex-[1_1_12rem] flex-col">
        <span className="truncate text-[14px] font-semibold text-ink">{m.title_fa}</span>
        <span className="flex flex-wrap items-center gap-x-2 text-[12px] text-muted">
          {m.company !== 'HQ' ? <CompanyMark code={m.company} height={12} mono /> : <Monogram size={12} />}<span>{t?.fa}</span><span>{jWeekday(m.starts_at)}، {jTime(m.starts_at)}</span>
          {m.state === 'scheduled' || m.state === 'prep' ? <span>{now ? until(m.starts_at, now) : ''}</span> : null}<span className="fig">{m.ref}</span>
        </span>
        {m.minutes ? <span className="line-clamp-1 text-[12px] text-sec">{m.minutes.summary_md.replace(/[*_`#>-]/g, '').split('\n').find((l) => l.trim())}</span> : null}
      </span>
      <span className="flex flex-wrap items-center gap-2">
        {m.mode === 'written' ? <Pill tone="warn">نوشتاری</Pill> : null}
        {m.trimmed_fa && m.mode !== 'written' ? <Pill tone="lapis" icon="info">کوتاه شد</Pill> : null}
        <span className={cx('fig text-[12px]', over ? 'text-neg' : 'text-sec')}>{m.state === 'scheduled' || m.state === 'prep' ? budgetFig(m.budget.estimate, m.budget.cap) : budgetFig(m.budget.used, m.budget.cap)}</span>
        <Pill tone={st.tone} live={st.live} dot={!st.live}>{st.fa}</Pill>
      </span>
    </Link>
  );
}

function LiveHero({ m }: { m: Meeting }) {
  const it = currentItem(m);
  const s = useSeconds();
  const share = pctOf(m.budget.used, m.budget.cap);
  return (
    <Card className="tahrir flex flex-wrap items-center gap-4 p-4 md:p-5">
      <TypeMark m={m} size={52} />
      <div className="flex min-w-0 flex-[1_1_14rem] flex-col gap-1">
        <span className="flex items-center gap-2 text-[12px] text-muted"><Pill tone="pos" live>زنده{s ? <span className="fig">· {mmss(s - Date.parse(m.starts_at))}</span> : null}</Pill><span className="fig">{m.ref}</span></span>
        <span className="text-h3 font-semibold">{m.title_fa}</span>
        {it ? <span className="text-[13px] text-sec">دستور {it.n} از {m.items.filter((x) => x.state !== 'skipped').length}، دور {it.round}: {it.title_fa}</span> : null}
      </div>
      <div className="flex w-full flex-col gap-1 sm:w-48"><span className="flex justify-between text-[11px] text-muted"><span>بودجه‌ی توکن</span><span className="fig">{budgetFig(m.budget.used, m.budget.cap)}</span></span><Bar pct={share} tone={budgetTone(share)} label="مصرف بودجه" /></div>
      <Link href={`/meetings/${m.ref}`} className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-[10px] bg-gold px-4 text-[13px] font-bold text-on-gold hover:bg-gold-bright sm:w-auto"><Icon name="meeting" size={18} />ورود به اتاق</Link>
    </Card>
  );
}

export function MeetingList({ type, company }: { type: MeetingTypeKey | null; company: string | null }) {
  const q = useMeetings({ type, company });
  const xs = q.data ?? [];
  const live = xs.filter((m) => m.state === 'live' || m.state === 'closing');
  const next = xs.filter((m) => m.state === 'scheduled' || m.state === 'prep').sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const past = xs.filter((m) => m.state === 'ended' || m.state === 'cancelled').sort((a, b) => b.starts_at.localeCompare(a.starts_at));
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (q.isLoading) return <Skeleton className="h-64" />;
  if (!xs.length) return <Empty icon="meeting" title="جلسه‌ای نیست" />;
  return (
    <div className="flex flex-col gap-4">
      {live.map((m) => <LiveHero key={m.ref} m={m} />)}
      <div className="grid items-start gap-4 xl:grid-cols-2">
        <Card className="flex flex-col gap-1 p-2"><div className="px-3 pt-2"><SectionTitle title="پیش رو" note="بودجه پیش از شروع جلوی توست" /></div>{next.length ? next.map((m) => <MeetingRow key={m.ref} m={m} />) : <p className="px-3 py-4 text-[13px] text-muted">جلسه‌ای پیش رو نیست.</p>}</Card>
        <Card className="flex flex-col gap-1 p-2"><div className="px-3 pt-2"><SectionTitle title="گذشته" note="با صورت‌جلسه و مصوبه‌ها" /></div>{past.length ? past.map((m) => <MeetingRow key={m.ref} m={m} />) : <p className="px-3 py-4 text-[13px] text-muted">هنوز جلسه‌ای تمام نشده.</p>}</Card>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ new meeting --
const AD_HOC: MeetingTypeKey[] = ['board', 'company', 'strategy', 'postmortem'];
export function NewMeetingSheet({ onClose }: { onClose: () => void }) {
  const act = useMeetingAction();
  const toast = useToast();
  const router = useRouter();
  const { data: companies } = useCompanies();
  const [type, setType] = useState<MeetingTypeKey>('company');
  const [company, setCompany] = useState<string | null>(null);
  const [when, setWhen] = useState('');
  const [items, setItems] = useState<Array<{ title_fa: string; time_box_min: number }>>([{ title_fa: '', time_box_min: 10 }]);
  const key = useRef<string | null>(null);
  const perCompany = type === 'company' || type === 'postmortem';
  const valid = !!when && (!perCompany || !!company) && items.some((x) => x.title_fa.trim());
  const create = () => act.create.mutateAsync({ key: (key.current ??= crypto.randomUUID()), body: { type, ...(perCompany ? { company: company! } : {}), starts_at: new Date(when).toISOString(), items: items.filter((x) => x.title_fa.trim()) } })
    .then((m) => { toast({ tone: 'ok', text: <>جلسه‌ی <span className="fig">{m.ref}</span> ساخته شد؛ بودجه و سخنگوها با قاعده.</> }); onClose(); router.push(`/meetings/${m.ref}`); })
    .catch((e) => toast({ tone: 'error', text: faError(e) }));
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title="جلسه‌ی تازه" description="سخنگوها، بودجه و سهم روزانه همان قاعده‌ی جلسه‌های زمان‌بندی‌شده است." width={540}
      footer={<Button variant="primary" icon="add" className="w-full" disabled={!valid} loading={act.create.isPending} onClick={() => void create()}>بساز</Button>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">نوع</span><div className="flex flex-wrap gap-2">{AD_HOC.map((k) => <FilterChip key={k} selected={type === k} onClick={() => setType(k)}>{MEETING_TYPE[k]!.fa}</FilterChip>)}</div></div>
        {perCompany ? (
          <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">شرکت</span>
            <div className="flex flex-wrap gap-2">{(companies ?? []).filter((c) => c.kind !== 'holding').map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => setCompany(c.code)}><span className="flex items-center gap-1.5"><CompanyMark code={c.code} height={12} mono />{c.name_fa}</span></FilterChip>)}</div>
          </div>
        ) : null}
        <label className="flex flex-col gap-1.5 font-semibold text-sec">زمان شروع<input type="datetime-local" dir="ltr" value={when} onChange={(e) => setWhen(e.target.value)} className={cx(field, 'fig')} /></label>
        <div className="flex flex-col gap-2">
          <span className="font-semibold text-sec">دستورها</span>
          {items.map((x, i) => (
            <div key={i} className="flex items-center gap-2">
              <input value={x.title_fa} onChange={(e) => setItems((xs) => xs.map((y, j) => (j === i ? { ...y, title_fa: e.target.value } : y)))} placeholder={`دستور ${i + 1}`} maxLength={200} className={cx(field, 'min-w-0 flex-1')} />
              <select value={x.time_box_min} onChange={(e) => setItems((xs) => xs.map((y, j) => (j === i ? { ...y, time_box_min: Number(e.target.value) } : y)))} aria-label="وقت دستور" className={cx(field, 'w-24')}>
                {[5, 10, 15, 20, 30].map((n) => <option key={n} value={n}>{n} دقیقه</option>)}
              </select>
              {items.length > 1 ? <Button size="sm" variant="ghost" icon="close" aria-label="حذف دستور" onClick={() => setItems((xs) => xs.filter((_, j) => j !== i))} /> : null}
            </div>
          ))}
          {items.length < 8 ? <Button size="sm" variant="ghost" icon="add" className="self-start" onClick={() => setItems((xs) => [...xs, { title_fa: '', time_box_min: 10 }])}>دستور دیگر</Button> : null}
        </div>
      </div>
    </Sheet>
  );
}

// ------------------------------------------------------------------ settings --
function scheduleFa(t: MeetingType): string {
  if (!t.schedule) return t.key === 'war_room' ? 'خودکار با هشدار فوری' : 'بعد از هر حادثه';
  if (t.key === 'company') return 'هفتگی · یکی برای هر شرکت، پخش بین روزها';
  if (/FREQ=MONTHLY/.test(t.schedule) && /BYDAY=-1TH/.test(t.schedule)) return 'ماهانه · آخرین پنجشنبه';
  return rruleFa(t.schedule.replace(/BYDAY=([A-Z]{2}),[^;]*/, 'BYDAY=$1'));
}
export function MeetingSettings() {
  const q = useMeetingSettings();
  const save = useSaveMeetingSettings();
  const toast = useToast();
  const [edit, setEdit] = useState<Record<string, Partial<MeetingType>>>({});
  const [confirm, setConfirm] = useState(false);
  const rows = useMemo(() => (q.data ?? []).map((t) => ({ ...t, ...edit[t.key] })), [q.data, edit]);
  const set = (k: string, p: Partial<MeetingType>) => setEdit((e) => ({ ...e, [k]: { ...e[k], ...p } }));
  const changed = Object.keys(edit).length > 0;
  const run = () => save.mutateAsync(rows).then(() => { toast({ tone: 'ok', text: 'تنظیمات جلسه‌ها مُهر و ذخیره شد.' }); setEdit({}); setConfirm(false); }).catch((e) => toast({ tone: 'error', text: faError(e) }));
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Skeleton className="h-72" />;
  return (
    <Card className="flex flex-col gap-3 p-4 md:p-5">
      <SectionTitle title="تنظیمات جلسه‌ها" note="روز، اعضا، سقف‌ها و حضور تو؛ ذخیره با اثر انگشت" action={<Button size="sm" variant="primary" icon="seal" disabled={!changed} onClick={() => setConfirm(true)}>ذخیره</Button>} />
      <div className="hidden grid-cols-[minmax(0,1.3fr)_minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] gap-3 px-2 text-[11px] text-muted lg:grid">
        <span>جلسه</span><span>زمان</span><span>اعضا</span><span>سقف بحث</span><span>بودجه‌ی توکن</span><span>حضور تو</span><span>فعال</span>
      </div>
      <ul className="flex flex-col">
        {rows.map((t) => (
          <li key={t.key} className="grid grid-cols-2 items-center gap-x-3 gap-y-2 border-t border-div px-2 py-3 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
            <span className="col-span-2 flex items-center gap-2 text-[14px] font-semibold lg:col-span-1"><span className={t.key === 'war_room' ? 'text-neg' : 'text-gold-ink'}><Icon name={MEETING_TYPE[t.key]?.icon ?? 'meeting'} size={16} /></span>{t.title_fa}</span>
            <span className="col-span-2 text-[12px] text-sec lg:col-span-1">{scheduleFa(t)}</span>
            <span className="text-[12px] text-sec">{t.members.roles.map((r) => ACTOR_ROLE_FA[r] ?? r).join('، ')}</span>
            <span className="flex items-center gap-1.5">
              <select value={t.max_rounds} onChange={(e) => set(t.key, { max_rounds: Number(e.target.value) })} aria-label={`دور ${t.title_fa}`} className={cx(field, 'h-8 w-16 px-2')}>{[1, 2, 3].map((n) => <option key={n} value={n}>{n} دور</option>)}</select>
              <select value={t.max_speakers} onChange={(e) => set(t.key, { max_speakers: Number(e.target.value) })} aria-label={`سخنگو ${t.title_fa}`} className={cx(field, 'h-8 w-16 px-2')}>{[2, 3, 4, 5, 6, 7, 8].map((n) => <option key={n} value={n}>{n} نفر</option>)}</select>
            </span>
            <span>
              {t.budget_tokens == null ? <span className="text-[12px] text-sec">بی‌سقف</span> : (
                <span className="flex items-center gap-1"><input inputMode="numeric" dir="ltr" value={String(Math.round(t.budget_tokens / 1000))} onChange={(e) => set(t.key, { budget_tokens: Number(e.target.value.replace(/\D/g, '') || 0) * 1000 })} aria-label={`بودجه ${t.title_fa}`} className={cx(field, 'fig h-8 w-16 px-2')} /><span className="fig text-[12px] text-muted">K</span></span>
              )}
            </span>
            <select value={t.owner_presence} onChange={(e) => set(t.key, { owner_presence: e.target.value as OwnerPresence })} aria-label={`حضور ${t.title_fa}`} className={cx(field, 'h-8 px-2')}>
              {(['live', 'summary', 'audio'] as const).map((k) => <option key={k} value={k}>{PRESENCE_FA[k]!.fa}</option>)}
            </select>
            <Switch checked={t.enabled} onChange={(v) => set(t.key, { enabled: v })} label={`فعال: ${t.title_fa}`} />
          </li>
        ))}
      </ul>
      <p className="text-[12px] leading-6 text-muted">«حضور تو»: زنده، خلاصه‌ی متنی، یا نسخه‌ی صوتی بعد از جلسه (تا text-to-speech بیاید مثل خلاصه). همه‌ی رزروهای جلسه‌ی یک روز روی هم حداکثر سهم روزانه‌ی جلسه‌ها از سقف ایجنت‌هاست؛ جلسه‌ای که جا نشود نوشتاری میشود. اتاق جنگ بیرون از این سهم است.</p>
      <Dialog open={confirm} onOpenChange={setConfirm} title="ذخیره‌ی تنظیمات جلسه‌ها" actions={<>
        <Button variant="primary" icon="seal" loading={save.isPending} onClick={() => void run()}>مُهر با passkey</Button>
        <Button variant="secondary" onClick={() => setConfirm(false)}>انصراف</Button>
      </>}>
        <div className="flex flex-col gap-2">
          <span>این جلسه‌ها عوض میشوند:</span>
          <ul className="flex flex-col gap-1">{Object.keys(edit).map((k) => <li key={k} className="text-ink">{rows.find((r) => r.key === k)?.title_fa}</li>)}</ul>
          <span className="text-[12px] text-muted">مُهر به همین فهرست دقیق بسته است.</span>
        </div>
      </Dialog>
    </Card>
  );
}
