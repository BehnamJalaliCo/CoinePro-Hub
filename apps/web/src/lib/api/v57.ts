/**
 * ⟨1.0.3⟩ Contract §57 «the session's team, one person at a time»: the session keeps one main thread with its holder, and each other
 * person in it gets a small side talk of his own. The owner, 2026-11-13: «میخوام … مستقیم بزنم روی کارمند باهاش توی یه فضای کوچیک حرف
 * بزنم و ببندم و اون ادامه بده کارشو». What the app reads and sends:
 * - `GET /orders/{ref}/team`: the seats (the holder first, then a content session's media seats, then the people present) and the
 *   company's narrator (§48);
 * - `GET /orders/{ref}/team/{code}/lines?limit=&before=`: one person's side talk, newest last (reading the newest page marks it read);
 * - `POST /orders/{ref}/team/{code}/say {text}`: the owner's word to that one person (`Idempotency-Key`, no passkey);
 * - `POST /orders/{ref}/team/hire {role}`: an empty media seat filled at once (`Idempotency-Key`, no passkey);
 * - §57.6 a deliverable that revises an earlier one names it (`produced_with.revision_of`): the timeline shows only the newest of a
 *   chain, with «نسخه‌ی n».
 * The shapes are §57's, typed here by hand. A hub before §57 has no `/team`: the read answers 404/405 and is null, and the row is hidden.
 */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query';
import { call } from './v13';
import { served, type Page } from './v33';

const enc = encodeURIComponent;

// ========================================================================================================= the shapes ==
/** `working`: a run of theirs in this order is queued or running; `empty`: a media seat nobody fills yet. */
export type SeatState = 'working' | 'idle' | 'empty';
export type SeatEmployee = { code: string; title_fa: string; company: string };
/** The side talk's last line (≤ 160 characters). */
export type SeatLast = { at: string; who: 'owner' | 'seat'; text: string };
/**
 * One seat of the session. `key`: the employee's code when filled, «role:<role>» when empty. `role`: the charter role
 * (scriptwriter, video_director, motion_designer, …). `role_fa`: «مسئول جلسه», «نویسنده», «کارگردان», «موشن‌گرافی» or the person's own
 * title. `holder`: the session's holder (his word is the main composer's). `unread`: the seat's lines since the owner last read them.
 */
export type Seat = {
  key: string; role: string | null; role_fa: string; holder: boolean; employee: SeatEmployee | null; state: SeatState;
  last: SeatLast | null; unread: number;
};
/** §48's narrator of the order's company, when one is set. */
export type TeamNarrator = { company: string; voice: string; voice_fa: string; style_fa: string | null };
export type SessionTeam = { seats: Seat[]; narrator: TeamNarrator | null };
/** One line of a side talk. `work_ref`: the work the word joined or made. */
export type SideLine = { id: string; at: string; who: 'owner' | 'seat'; who_fa: string; text: string; work_ref: string | null };
/** What a word to a seat answers: its line, the work it joined or made, and whether that work was woken at once. */
export type SayOut = { line: SideLine; work_ref: string | null; woken: boolean };

/** The holder's chip and a filled seat's sheet name the person: his own title, else the seat's. */
export const seatWho = (s: Pick<Seat, 'employee' | 'role_fa'>): string => s.employee?.title_fa?.trim() || s.role_fa;
/** A seat the owner can talk to on its own: a filled seat that is not the holder's. */
export const talkable = (s: Seat): boolean => !s.holder && s.state !== 'empty' && !!s.employee;
/** An empty media seat, hired with one tap. */
export const hireable = (s: Seat): boolean => s.state === 'empty' && !!s.role;

// ============================================================================================================ words ==
export const TEAM_FA = 'تیم این جلسه';
export const withFa = (who: string) => `با ${who}`;
export const hireAskFa = (roleFa: string) => `${roleFa} استخدام شود؟`;
export const NARRATOR_FA = 'گوینده';
export const SIDE_EMPTY_FA = 'هر چه این‌جا بگویی فقط به او میرسد؛ جلسه‌ی اصلی سر جایش میماند و او کارش را ادامه میدهد.';

// ======================================================================================================== the reads ==
/** At most this many lines a page of a side talk. */
export const SIDE_PAGE = 50;
/** How often an open side talk is read again (§57.7: every 4 s while it is open, and on `session.team`). */
export const SIDE_POLL_MS = 4000;

export const teamKey = (ref: string) => ['orders', 'team', ref] as const;
export const linesKey = (ref: string, code: string) => ['orders', 'team', ref, 'lines', code] as const;

/** `GET /orders/{ref}/team`; null on a hub before §57 (its row is then not shown). */
export const getSessionTeam = (ref: string) => served(call<SessionTeam>('GET', `/orders/${enc(ref)}/team`));

/** `GET /orders/{ref}/team/{code}/lines`: a page of the side talk, newest last; `before` reads the page before it. */
export function getSideLines(ref: string, code: string, before?: string | null): Promise<Page<SideLine>> {
  const q = new URLSearchParams({ limit: String(SIDE_PAGE) });
  if (before) q.set('before', before);
  return call<Page<SideLine>>('GET', `/orders/${enc(ref)}/team/${enc(code)}/lines?${q}`);
}

/** `POST /orders/{ref}/team/{code}/say {text}`: the same [key] for a retry of the same word, so it is never said twice. */
export const sayToSeat = (ref: string, code: string, text: string, key: string = crypto.randomUUID()) =>
  call<SayOut>('POST', `/orders/${enc(ref)}/team/${enc(code)}/say`, { text }, { 'Idempotency-Key': key });

/** `POST /orders/{ref}/team/hire {role}`: answers the team as it now stands; a refusal answers its own code with `message_fa`. */
export const hireSeat = (ref: string, role: string, key: string = crypto.randomUUID()) =>
  call<SessionTeam>('POST', `/orders/${enc(ref)}/team/hire`, { role }, { 'Idempotency-Key': key });

/** The session's team: read on open, again every half minute and on `session.team` (./stream). Off for a closed session's writes only. */
export const useSessionTeam = (ref: string) => useQuery({
  queryKey: teamKey(ref), staleTime: 10_000, refetchInterval: 30_000,
  queryFn: () => getSessionTeam(ref),
});

/**
 * One side talk while its sheet is open: the newest page, read again every [SIDE_POLL_MS]; older pages one at a time. Reading the
 * newest page marks the seat read, so its unread dot goes at once.
 */
export function useSideLines(ref: string, code: string | null) {
  const qc = useQueryClient();
  return useInfiniteQuery({
    queryKey: linesKey(ref, code ?? ''), enabled: !!code, staleTime: 2_000, refetchInterval: code ? SIDE_POLL_MS : false,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const page = await getSideLines(ref, code!, pageParam);
      if (!pageParam) qc.setQueryData<SessionTeam | null>(teamKey(ref), (t) => (t ? { ...t, seats: t.seats.map((s) => (s.key === code && s.unread ? { ...s, unread: 0 } : s)) } : t));
      return page;
    },
    getNextPageParam: (last) => last.next_cursor ?? null,
  });
}
/** The lines of the pages read so far, oldest first (each page is newest last; the first page is the newest). */
export const linesOf = (d: InfiniteData<Page<SideLine>> | undefined): SideLine[] => {
  const seen = new Set<string>();
  const out: SideLine[] = [];
  for (const p of [...(d?.pages ?? [])].reverse()) for (const l of p.items) if (!seen.has(l.id)) { seen.add(l.id); out.push(l); }
  return out;
};

// ======================================================================================================= the writes ==
export function useSessionTeamActions(ref: string) {
  const qc = useQueryClient();
  return {
    /** The owner's word to one person: his line is in the side talk at once; the seat's ring and last line are read again. */
    say: useMutation({
      mutationFn: (v: { code: string; text: string; key: string }) => sayToSeat(ref, v.code, v.text, v.key),
      onSuccess: (out, v) => {
        qc.setQueryData<InfiniteData<Page<SideLine>>>(linesKey(ref, v.code), (d) => {
          if (!d?.pages.length || d.pages[0]!.items.some((l) => l.id === out.line.id)) return d;
          const [first, ...rest] = d.pages;
          return { ...d, pages: [{ ...first!, items: [...first!.items, out.line] }, ...rest] };
        });
        qc.setQueryData<SessionTeam | null>(teamKey(ref), (t) => (t ? {
          ...t, seats: t.seats.map((s) => (s.key === v.code ? { ...s, last: { at: out.line.at, who: 'owner', text: out.line.text.slice(0, 160) }, ...(out.woken ? { state: 'working' as const } : {}) } : s)),
        } : t));
        void qc.invalidateQueries({ queryKey: teamKey(ref) });
        void qc.invalidateQueries({ queryKey: ['orders', 'report', ref] });
      },
    }),
    /** An empty media seat filled: the answer is the team as it stands now. */
    hire: useMutation({
      mutationFn: (v: { role: string; key: string }) => hireSeat(ref, v.role, v.key),
      onSuccess: (team) => {
        qc.setQueryData(teamKey(ref), team);
        void qc.invalidateQueries({ queryKey: ['orders', 'report', ref] });
      },
    }),
  };
}

// =================================================================================================== §57.6 revisions ==
const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v.trim() : null);
/**
 * The earlier deliverable this one revises, read leniently from each of [sources] in turn (the deliverable's `produced_with`, the
 * deliverable itself, the report's line of it): `revision_of` wherever it is, else null.
 */
export function revisionOf(...sources: unknown[]): string | null {
  for (const s of sources) {
    if (!s || typeof s !== 'object') continue;
    const o = s as Record<string, unknown>;
    const own = str(o.revision_of);
    if (own) return own;
    const pw = o.produced_with;
    if (pw && typeof pw === 'object') {
      const r = str((pw as Record<string, unknown>).revision_of);
      if (r) return r;
    }
  }
  return null;
}

/**
 * §57.6 the newest of each revision chain, and how many versions it has: an output another output revises is left out, and the
 * newest says «نسخه‌ی n» (n counted back through the chain; a revision of something not in the list counts it once). Order kept.
 */
export function newestOfChains<T>(items: T[], refOf: (t: T) => string, revOf: (t: T) => string | null): { shown: T[]; version: Map<string, number> } {
  const by = new Map(items.map((t) => [refOf(t), t] as const));
  const revised = new Set<string>();
  for (const t of items) { const r = revOf(t); if (r && r !== refOf(t)) revised.add(r); }
  const shown = items.filter((t) => !revised.has(refOf(t)));
  const version = new Map<string, number>();
  for (const t of shown) {
    let n = 1;
    const seen = new Set([refOf(t)]);
    let cur: T | undefined = t;
    while (cur) {
      const r = revOf(cur);
      if (!r || seen.has(r)) break;
      seen.add(r);
      n += 1;
      cur = by.get(r);
    }
    if (n > 1) version.set(refOf(t), n);
  }
  return { shown, version };
}
