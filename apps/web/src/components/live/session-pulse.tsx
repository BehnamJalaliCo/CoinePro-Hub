'use client';

// ⟨1.24⟩ SS-1 «نشان سشن و نگهبان توقف» (design/LIVE_VIEWS.md §4 E, contract §41.3 and §42): on every session row and in the session's
// header, the badge as the stream tells it (`session.updated`, crossfading), when the last step was, and a thin ring filling toward the hub's
// 10-minute idle sweep — after the holder is woken it fills toward the second window, and «گیر کرده» is a full red ring. The work band runs
// only while the session is moving; «نوبت تو» glints gold once when it arrives. Under reduced motion the ring is words («۷ از ۱۰ دقیقه»).

import { BADGE, type Badge } from '@/lib/api/v34';
import { useLiveState } from '@/lib/live/store';
import { Pill } from '@/components/ui/primitives';
import { ago, cx } from '@/lib/format';
import { WorkBand, useChanges, useReducedMotion, useTick } from './motion';

/** The hub's idle sweep (§41.3 `SESSION_IDLE_MINUTES`). */
export const IDLE_MINUTES = 10;

/** The badge now: the stream's when it is newer than the list's. */
export function useLiveBadge(ref: string, seed: Badge, seedAt?: string | null): Badge {
  const live = useLiveState((s) => s.sessions_by_ref[ref] ?? null);
  if (live?.badge && (!seedAt || Date.parse(live.at) >= Date.parse(seedAt))) return live.badge;
  return seed;
}

/** When the session last took a step: the latest of what the list, the activity and the stream know. */
export function useLastStep(ref: string, ...known: Array<string | null | undefined>): { at: string | null; wokeAt: string | null } {
  const live = useLiveState((s) => s.sessions_by_ref[ref] ?? null);
  const all = [...known, live?.last_step_at].filter((x): x is string => !!x && Number.isFinite(Date.parse(x)));
  const at = all.length ? all.reduce((a, b) => (Date.parse(b) > Date.parse(a) ? b : a)) : null;
  return { at, wokeAt: live?.woke_at ?? null };
}

/** The badge in words with its tone, crossfading when it changes (M2); «نوبت تو» glints gold once as it arrives (M13). */
export function LiveBadge({ badge }: { badge: Badge }) {
  const b = BADGE[badge];
  const changes = useChanges(badge);
  return (
    <span className="inline-flex flex-none flex-col" data-live-badge={badge}>
      <span key={badge} className={changes ? 'hq-m2-in' : undefined}><Pill tone={b.tone} dot={!b.live} live={b.live}>{b.fa}</Pill></span>
      {changes > 0 && badge === 'your_turn' ? <span aria-hidden className="hq-m13 mx-2 mt-0.5 block h-px" style={{ background: 'var(--hq-gold-ink)' }} /> : null}
    </span>
  );
}

const minutesSince = (iso: string | null, now: number) => (iso ? Math.max(0, Math.floor((now - Date.parse(iso)) / 60_000)) : null);

/**
 * The stall watch: «آخرین قدم n دقیقه پیش» and the idle ring. [badge] decides what it says: moving → the ring toward the sweep (the second
 * window after the hub woke the holder); stuck → full red with «گیر کرده»; the owner's turn, ready or closed → only when the last step was.
 */
export function StallWatch({ badge, lastAt, wokeAt, className }: { badge: Badge; lastAt: string | null; wokeAt?: string | null; className?: string }) {
  const rm = useReducedMotion();
  const now = useTick(30_000);
  const mins = minutesSince(lastAt, now);
  const woke = !!wokeAt && !!lastAt && Date.parse(wokeAt) >= Date.parse(lastAt);
  const watching = badge === 'moving' || badge === 'stuck';
  const into = mins == null ? 0 : woke ? Math.max(0, mins - IDLE_MINUTES) : mins;
  const frac = badge === 'stuck' ? 1 : watching ? Math.min(1, into / IDLE_MINUTES) : 0;
  const tone = badge === 'stuck' ? 'var(--hq-negative)' : frac >= 1 || woke ? 'var(--hq-warning)' : 'var(--hq-silver-ink)';
  const when = mins == null || !lastAt ? 'آخرین قدم —' : mins === 0 ? 'آخرین قدم همین الان' : `آخرین قدم ${mins < 60 ? `${mins} دقیقه پیش` : ago(lastAt, now)}`;
  const C = 2 * Math.PI * 6;
  return (
    <span className={cx('inline-flex items-center gap-1.5 text-[11px] text-muted', className)} data-stall={badge} data-idle-min={mins ?? undefined}>
      {watching && !rm ? (
        <svg width={16} height={16} viewBox="0 0 16 16" aria-hidden className="flex-none">
          <circle cx={8} cy={8} r={6} fill="none" stroke="var(--hq-line-divider)" strokeWidth={2} />
          <circle cx={8} cy={8} r={6} fill="none" stroke={tone} strokeWidth={2} strokeLinecap="round" transform="rotate(-90 8 8)" strokeDasharray={`${(C * frac).toFixed(2)} ${C.toFixed(2)}`} className="hq-m12" />
        </svg>
      ) : null}
      <span>{when}</span>
      {watching && rm && badge !== 'stuck' && mins != null ? <span>· {Math.min(into, IDLE_MINUTES)} از {IDLE_MINUTES} دقیقه</span> : null}
      {woke && badge === 'moving' ? <span>· صاحب کار بیدار شد</span> : null}
    </span>
  );
}

/** The work band under a moving session (M5), only while it moves. */
export const SessionBand = ({ moving }: { moving: boolean }) => <WorkBand on={moving} height={2} className="mt-1" label="در جریان" />;
