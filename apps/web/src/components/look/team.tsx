'use client';

// ⟨1.0.3⟩ Contract §57 «the session's team, one person at a time» (the owner, 2026-11-13: «مستقیم بزنم روی کارمند باهاش توی یه فضای
// کوچیک حرف بزنم و ببندم و اون ادامه بده کارشو»). Under the session's header, ONE row «تیم این جلسه»:
// - a chip per seat: its mark and its role in the owner's words; a ring while that person works in this order; an unread dot when he
//   said something the owner has not read; an empty media seat is a dashed «+ نقش»;
// - «گوینده: …» when the company has a narrator (§48), which opens the same picker as the company's page;
// - the holder's chip brings the main composer into reach (his word is the main thread's);
// - a filled seat opens a small sheet «با …»: that person's side talk alone, a composer and close; while it is open it is read again
//   every four seconds (and on `session.team`). Nothing of it fills the main thread;
// - an empty seat asks once «… استخدام شود؟» and hires at once (no card, no passkey); a refusal is said in the hub's own words.
// A hub before §57 has no team: the row is not there.

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Avatar } from '@/components/brand/avatar';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { FaText } from '@/components/v29/text';
import { NarratorPicker } from '@/components/v47/narrator';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import {
  NARRATOR_FA, SIDE_EMPTY_FA, TEAM_FA, hireAskFa, hireable, linesOf, seatWho, talkable, teamKey, useSessionTeam, useSessionTeamActions, useSideLines,
  withFa, type Seat, type SideLine,
} from '@/lib/api/v57';
import { cx, jTime } from '@/lib/format';
import { DecisionBar } from './decision-bar';
import { haptic } from './haptics';
import { SpringSheet } from './spring-sheet';
import { Facts, Ltr, faCount } from './text';

const MEDIA = new Set(['scriptwriter', 'video_director', 'motion_designer']);
const CHIP = 'relative inline-flex h-9 flex-none items-center gap-1.5 rounded-full text-[13px] outline-none transition-colors duration-[120ms] focus-visible:ring-2 focus-visible:ring-[var(--hq-silver-line)]';

/** «نسخه‌ی ۳»: §57.6 the newest of a revision chain says which version it is (a count in a sentence). */
export const versionFa = (n: number) => `نسخه‌ی ${faCount(n)}`;

/** A seat's mark: the holder wears the manager's medallion, the others a colleague's; the medallion's own arc turns while he works. */
function SeatMark({ s }: { s: Seat }) {
  return (
    <span aria-hidden className="flex flex-none">
      <Avatar kind={s.holder ? 'manager' : 'employee'} dept={s.role && MEDIA.has(s.role) ? 'MEDIA' : null} size={28} state={s.state === 'working' ? 'working' : 'idle'} />
    </span>
  );
}

/** One seat of the row. */
function SeatChip({ s, closed, onOpen }: { s: Seat; closed: boolean; onOpen: (s: Seat) => void }) {
  const who = seatWho(s);
  if (s.state === 'empty') {
    // An empty seat of a closed session cannot be filled any more.
    if (closed || !hireable(s)) return null;
    return (
      <li className="flex flex-none">
        <button type="button" aria-haspopup="dialog" data-seat={s.key} data-state="empty" onClick={() => onOpen(s)}
          className={cx(CHIP, 'border border-dashed border-strong px-3 text-sec hover:bg-hover hover:text-ink')}>
          {`+ ${s.role_fa}`}
        </button>
      </li>
    );
  }
  const working = s.state === 'working';
  const unread = s.unread > 0;
  return (
    <li className="flex flex-none">
      <button type="button" aria-haspopup={s.holder ? undefined : 'dialog'} title={who} data-seat={s.key} data-state={s.state} data-holder={s.holder ? '' : undefined}
        onClick={() => onOpen(s)}
        className={cx(CHIP, 'pe-3 ps-1 hover:bg-hover', working ? 'bg-raised text-ink shadow-[inset_0_0_0_1px_var(--hq-silver-line)]' : 'bg-tile text-ink')}>
        <SeatMark s={s} />
        <span className="font-semibold">{s.role_fa}</span>
        {who !== s.role_fa ? <span className="sr-only">، {who}</span> : null}
        {working ? <span className="sr-only">، الان سر کار است</span> : null}
        {unread ? <><span aria-hidden data-unread className="absolute end-1 top-1 size-2 rounded-full bg-gold-ink ring-2 ring-[var(--hq-surface-page)]" /><span className="sr-only">، {faCount(s.unread)} حرف تازه</span></> : null}
      </button>
    </li>
  );
}

/** The row under the session's header; nothing on a hub before §57. [onHolder]: the holder's chip, which brings the composer into reach. */
export function TeamRow({ refId, closed, onHolder }: { refId: string; closed: boolean; onHolder: () => void }) {
  const q = useSessionTeam(refId);
  const qc = useQueryClient();
  const companies = useCompanies();
  const [talk, setTalk] = useState<string | null>(null);
  const [hiring, setHiring] = useState<Seat | null>(null);
  const [narrating, setNarrating] = useState(false);
  const team = q.data;
  if (!team || !team.seats.length) return null;
  const n = team.narrator;
  const open = (s: Seat) => {
    if (s.holder) { onHolder(); return; }
    if (s.state === 'empty') { if (!closed && hireable(s)) setHiring(s); return; }
    if (talkable(s)) setTalk(s.key);
  };
  const seat = talk ? team.seats.find((s) => s.key === talk) ?? null : null;
  const nameOf = (code: string) => companies.data?.find((c) => c.code === code)?.name_fa ?? code;
  return (
    <section aria-label={TEAM_FA} data-testid="session-team" className="flex flex-none items-center gap-2">
      <span className="flex-none text-[12px] text-muted">{TEAM_FA}</span>
      <ul className="no-scrollbar flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto py-0.5">
        {team.seats.map((s) => <SeatChip key={s.key} s={s} closed={closed} onOpen={open} />)}
        {n ? (
          <li className="flex flex-none">
            <button type="button" aria-haspopup="dialog" data-narrator-chip onClick={() => setNarrating(true)}
              className={cx(CHIP, 'border border-strong px-3 text-sec hover:bg-hover hover:text-ink')}>
              <Icon name="mic" size={15} className="text-silver-ink" />
              <span>{NARRATOR_FA}: <bdi className="font-semibold text-ink">{n.voice_fa || n.voice}</bdi></span>
            </button>
          </li>
        ) : null}
      </ul>
      {seat ? <SideTalk refId={refId} seat={seat} closed={closed} onClose={() => setTalk(null)} /> : null}
      {hiring ? <HireSheet refId={refId} seat={hiring} onClose={() => setHiring(null)} /> : null}
      {narrating && n ? (
        <NarratorPicker company={n.company} nameFa={nameOf(n.company)} onClose={() => { setNarrating(false); void qc.invalidateQueries({ queryKey: teamKey(refId) }); }} />
      ) : null}
    </section>
  );
}

// ======================================================================================================= the side talk ==
/** One line of a side talk: the owner's on his side with the gold edge, the person's on the other, each with its clock time. */
function Line({ l }: { l: SideLine }) {
  const own = l.who === 'owner';
  return (
    <li data-side-line data-who={l.who} className={cx('flex max-w-[88%] flex-col gap-0.5', own ? 'self-start' : 'self-end')}>
      <span className={cx('rounded-[14px] px-3 py-2 text-[14px] leading-7 text-ink [overflow-wrap:anywhere]', own ? 'hq-edge bg-raised' : 'bg-tile')}>
        <FaText text={l.text} />
      </span>
      <span className={cx('px-1 text-[11px] text-muted', own ? 'self-start' : 'self-end')}>
        <Facts>{own ? null : l.who_fa}<Ltr>{jTime(l.at)}</Ltr></Facts>
      </span>
    </li>
  );
}

/** «با …»: one person's side talk, read again every four seconds while it is open; his word goes to him alone. */
function SideTalk({ refId, seat, closed, onClose }: { refId: string; seat: Seat; closed: boolean; onClose: () => void }) {
  const who = seatWho(seat);
  const q = useSideLines(refId, seat.key);
  const act = useSessionTeamActions(refId);
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  // One key for one word: a retry of the same words reuses it, so the hub never takes it twice; new words get a new key.
  const said = useRef<{ text: string; key: string } | null>(null);
  const end = useRef<HTMLLIElement>(null);
  const lines = linesOf(q.data);
  const last = lines.at(-1)?.id;
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }); }, [last]);
  const send = (e?: FormEvent) => {
    e?.preventDefault();
    const t = text.trim();
    if (!t || act.say.isPending) return;
    if (said.current?.text !== t) said.current = { text: t, key: crypto.randomUUID() };
    setError(null);
    act.say.mutate({ code: seat.key, text: t, key: said.current.key }, {
      onSuccess: () => { haptic('tick'); said.current = null; setText(''); },
      onError: (err) => { haptic('error'); setError(err instanceof ApiError ? err.messageFa : 'نرسید؛ دوباره بزن.'); },
    });
  };
  const composer = closed ? (
    <p className="border-t border-div px-5 pb-[calc(16px+env(safe-area-inset-bottom))] pt-3 text-[12px] leading-5 text-muted">این جلسه بسته شده؛ این گفتگو فقط خواندنی است.</p>
  ) : (
    <form onSubmit={send} className="flex flex-col gap-1.5 border-t border-div px-5 pb-[calc(12px+env(safe-area-inset-bottom))] pt-3" aria-label={`نوشتن به ${who}`}>
      {error ? <p role="alert" className="text-[12px] leading-5 text-neg" data-side-error>{error}</p> : null}
      <div className="flex items-end gap-2">
        <textarea value={text} rows={1} dir="auto" aria-label={`پیام به ${who}`} placeholder={`به ${who} بگو…`} autoComplete="off" spellCheck={false}
          onChange={(e) => { setText(e.target.value); if (error) setError(null); }}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }}
          style={{ minHeight: 44, maxHeight: 132 }}
          className="block min-w-0 flex-1 resize-none rounded-[12px] border border-strong bg-tile px-3 py-[9px] text-[14px] leading-6 text-ink outline-none placeholder:text-muted focus:border-[var(--hq-silver-ink)]" />
        <button type="submit" aria-label={`بفرست به ${who}`} disabled={!text.trim() || act.say.isPending} aria-busy={act.say.isPending || undefined}
          className="flex size-11 flex-none items-center justify-center rounded-full bg-gold text-on-gold hover:bg-gold-bright disabled:bg-disabled-fill disabled:text-disabled">
          <Icon name="send" size={20} mirror />
        </button>
      </div>
    </form>
  );
  return (
    <SpringSheet open onOpenChange={(v) => { if (!v) onClose(); }} title={withFa(who)} testid="side-talk" width={520} bar={composer}
      description={<Facts>{who !== seat.role_fa ? seat.role_fa : null}{seat.state === 'working' ? 'الان سر کار است' : null}{'فقط بین تو و او'}</Facts>}>
      <div className="flex min-h-[22dvh] flex-col gap-2 pb-1" data-lines={lines.length}>
        {q.hasNextPage ? (
          <Button variant="text" size="sm" className="self-center" loading={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>حرف‌های قبلی</Button>
        ) : null}
        {q.isLoading ? <p className="text-[13px] text-muted" role="status">میخوانم…</p>
          : q.isError && !lines.length ? <p className="text-[13px] text-neg" role="alert">{q.error instanceof ApiError ? q.error.messageFa : 'خوانده نشد؛ کمی بعد دوباره باز کن.'}</p>
          : lines.length ? (
            <ul aria-label={`گفتگو با ${who}`} aria-live="polite" className="flex flex-col gap-2.5">
              {lines.map((l) => <Line key={l.id} l={l} />)}
              <li ref={end} aria-hidden className="h-px" />
            </ul>
          ) : <p className="text-[13px] leading-6 text-sec" data-side-empty>{SIDE_EMPTY_FA}</p>}
      </div>
    </SpringSheet>
  );
}

// ============================================================================================================ the hire ==
/** «… استخدام شود؟», asked once: the seat is filled at once with the role's own defaults; a refusal says the hub's own sentence. */
function HireSheet({ refId, seat, onClose }: { refId: string; seat: Seat; onClose: () => void }) {
  const toast = useToast();
  const act = useSessionTeamActions(refId);
  const key = useRef(crypto.randomUUID());
  const [refused, setRefused] = useState<string | null>(null);
  const go = () => {
    if (!seat.role || act.hire.isPending) return;
    setRefused(null);
    act.hire.mutate({ role: seat.role, key: key.current }, {
      onSuccess: () => { haptic('seal'); toast({ tone: 'ok', text: `${seat.role_fa} استخدام شد و به این جلسه آمد.` }); onClose(); },
      // A refusal made nothing: the next try is a new word with its own key.
      onError: (e) => { haptic('error'); key.current = crypto.randomUUID(); setRefused(e instanceof ApiError ? e.messageFa : 'استخدام نشد؛ دوباره بزن.'); },
    });
  };
  return (
    <SpringSheet open onOpenChange={(v) => { if (!v) onClose(); }} title={hireAskFa(seat.role_fa)} testid="hire-seat" width={440}
      bar={<DecisionBar label={hireAskFa(seat.role_fa)} error={refused} state={act.hire.isPending ? 'working' : 'idle'}
        primary={{ label: 'استخدام کن', onClick: go }} quiet={[{ label: 'نه', onClick: onClose }]} />}>
      <p className="pb-1 text-[13px] leading-6 text-sec">همین حالا با تنظیم‌های پیش‌فرض نقشش به همین جلسه می‌آید؛ بی کارت و بی اثر انگشت، در سقف پاکت این ماه.</p>
    </SpringSheet>
  );
}
