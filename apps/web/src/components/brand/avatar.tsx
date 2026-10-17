import { Icon } from '@/components/icon';
import { DEPT_ICON } from '@/lib/labels';
import type { IconName } from '@/generated/icons';
import { Monogram } from './marks';

export type AgentKind = 'owner' | 'ceo' | 'manager' | 'employee' | 'advisor' | 'overseer' | 'assistant' | 'inspector' | 'system';
export type AgentState = 'idle' | 'working' | 'sleeping' | 'waiting' | 'error';

/** The agent medallion (owner decision 2026-10-17): the ring says rank (1 ring employee, 2 manager,
 *  2 + 8 shamseh ticks CEO) and live state (comet = working, dim = asleep, warn, error); the glyph says
 *  the department. The owner is a gold disc with the CP monogram; the advisor is the orb. */
export function Avatar({ kind = 'employee', dept, size = 40, state = 'idle', number, label }: { kind?: AgentKind | string; dept?: string | null; size?: number; state?: AgentState | string; number?: string; label?: string }) {
  const s = size;
  if (kind === 'advisor') return <Orb size={s} label={label} />;
  if (kind === 'overseer') return <Sentinel size={s} state={state} label={label} />;
  if (kind === 'owner') {
    return (
      <span role="img" aria-label={label ?? 'مدیر کل'} className="flex flex-none items-center justify-center rounded-full bg-gold" style={{ width: s, height: s, boxShadow: `inset 0 0 0 ${Math.max(2, Math.floor(s / 16))}px var(--hq-gold-fill), inset 0 0 0 ${Math.max(3, Math.floor(s / 12))}px rgba(11,13,20,.35)` }}>
        <Monogram size={Math.round(s * 0.46)} ink="var(--hq-text-on-gold)" />
      </span>
    );
  }
  const ringColor = state === 'error' ? 'var(--hq-negative)' : state === 'waiting' ? 'var(--hq-warning)' : 'var(--hq-silver-ink)';
  const ringOp = state === 'sleeping' ? 0.45 : 1;
  const sw = s < 56 ? 1.5 : 1.8;
  const r = s / 2 - sw / 2;
  const glyph: IconName = kind === 'ceo' ? 'holding' : kind === 'inspector' ? 'search' : kind === 'assistant' ? 'assistant' : (dept && DEPT_ICON[dept]) || 'agent';
  const ticks = kind === 'ceo' && s >= 30
    ? Array.from({ length: 8 }, (_, k) => {
        const a = (Math.PI / 4) * k + Math.PI / 8;
        const r2 = r - Math.max(2.5, s * 0.07);
        return <line key={k} x1={s / 2 + (r - 0.5) * Math.cos(a)} y1={s / 2 + (r - 0.5) * Math.sin(a)} x2={s / 2 + r2 * Math.cos(a)} y2={s / 2 + r2 * Math.sin(a)} stroke={ringColor} strokeWidth={1.2} strokeLinecap="round" />;
      })
    : null;
  const c = 2 * Math.PI * r;
  const showNum = number && s >= 56;
  return (
    <span role="img" aria-label={label ?? 'ایجنت'} className="relative block flex-none" style={{ width: s, height: s }}>
      <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} className="absolute inset-0 overflow-visible" aria-hidden>
        <circle cx={s / 2} cy={s / 2} r={r} fill="var(--hq-surface-tile)" stroke={ringColor} strokeOpacity={ringOp} strokeWidth={sw} />
        {(kind === 'manager' || kind === 'ceo' || kind === 'inspector' || kind === 'assistant') && (
          <circle cx={s / 2} cy={s / 2} r={r - Math.max(3, s * 0.1)} fill="none" stroke={ringColor} strokeOpacity={0.5 * ringOp} strokeWidth={1} />
        )}
        {ticks}
        {state === 'working' && (
          <circle cx={s / 2} cy={s / 2} r={r} fill="none" stroke="var(--hq-text-primary)" strokeWidth={sw + 0.4} strokeLinecap="round" strokeDasharray={`${c * 0.18} ${c}`} style={{ transformBox: 'fill-box', transformOrigin: 'center', animation: 'hq-spin 2.4s linear infinite' }} />
        )}
      </svg>
      <span className="absolute inset-0 flex items-center justify-center" style={{ color: state === 'sleeping' ? 'var(--hq-text-muted)' : 'var(--hq-silver-ink)' }}>
        {showNum ? (
          <span className="flex flex-col items-center gap-px">
            <Icon name={glyph} size={Math.round(s * 0.36)} strokeWidth={1.4} />
            <span className="fig font-bold leading-none text-sec" style={{ fontSize: Math.max(9, Math.round(s * 0.15)) }}>{number}</span>
          </span>
        ) : (
          <Icon name={glyph} size={Math.round(s * (kind === 'ceo' ? 0.4 : 0.42))} strokeWidth={s < 56 ? 1.6 : 1.4} />
        )}
      </span>
    </span>
  );
}

/** The Chief Overseer's sentinel (rank two, beside the advisor's orb): a silver sphere with a gold rim and the eye.
 *  It turns its gaze (a slow pulse of the rim) while working, and dims when the holding sleeps. */
export function Sentinel({ size = 56, state = 'idle', label }: { size?: number; state?: AgentState | string; label?: string }) {
  const watching = state === 'working' || state === 'waiting';
  return (
    <span
      role="img"
      aria-label={label ?? 'ناظر کل'}
      className="flex flex-none items-center justify-center rounded-full"
      style={{
        width: size, height: size, opacity: state === 'sleeping' ? 0.7 : 1,
        background: 'radial-gradient(circle at 35% 30%, #F1F3F6 0%, #B9C2CE 46%, #5B6573 100%)',
        boxShadow: `0 0 0 ${Math.max(1.5, size / 28)}px var(--hq-gold-fill)${watching ? ', 0 0 18px rgba(216,168,72,.35)' : ''}`,
        animation: watching ? 'hq-breath 2.2s ease-in-out infinite' : undefined,
      }}
    >
      <Icon name="overseer" size={Math.round(size * 0.52)} strokeWidth={size < 40 ? 1.8 : 1.6} className="text-[#141821]" />
    </span>
  );
}

/** The advisor's orb: a gold sphere that breathes when listening and glows when thinking. */
export function Orb({ size = 56, state = 'rest', label }: { size?: number; state?: 'rest' | 'listening' | 'thinking' | 'speaking'; label?: string }) {
  const anim = state === 'thinking' ? 'hq-breath 1.6s ease-in-out infinite' : state === 'listening' ? 'hq-breath 2.8s ease-in-out infinite' : undefined;
  return (
    <span
      role="img"
      aria-label={label ?? 'مشاور کل'}
      className="block flex-none rounded-full"
      style={{
        width: size, height: size, animation: anim,
        background: 'radial-gradient(circle at 35% 30%, #F0CC60 0%, #D8A848 48%, #966A1F 100%)',
        boxShadow: state === 'thinking' || state === 'speaking' ? '0 0 0 6px rgba(216,168,72,.12), 0 0 24px rgba(216,168,72,.35)' : undefined,
      }}
    />
  );
}
