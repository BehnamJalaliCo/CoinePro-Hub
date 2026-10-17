'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Seal, type SealState } from '@/components/brand/seal';

const HOLD_MS = 600; // tokens: motion.duration.sealHold

/** The seal ritual (D2): press and hold the seal; a gold ring fills; releasing early cancels.
 *  Keyboard: Enter/Space held the same way. On completion `onSealed` runs (step-up + approve). */
export function SealButton({ code, nameFa, nameEn, holding, disabled, busy, sealed, onSealed, size = 96 }: { code: string; nameFa: string; nameEn: string; holding?: boolean; disabled?: boolean; busy?: boolean; sealed?: boolean; onSealed: () => void; size?: number }) {
  const [holdStart, setHoldStart] = useState<number | null>(null);
  const [p, setP] = useState(0);
  const done = useRef(onSealed);
  useLayoutEffect(() => { done.current = onSealed; });

  useEffect(() => {
    if (holdStart == null) return;
    let raf = 0;
    const tick = () => {
      const v = Math.min(100, ((performance.now() - holdStart) / HOLD_MS) * 100);
      setP(v);
      if (v >= 100) {
        setHoldStart(null);
        setP(0);
        navigator.vibrate?.(18);
        done.current();
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [holdStart]);

  const begin = (t: number) => { if (!disabled && !busy && !sealed) setHoldStart(t); };
  const stop = () => { setHoldStart(null); setP(0); };

  const progress = busy ? 100 : p;
  const state: SealState = sealed ? 'sealed' : progress > 0 ? 'holding' : 'ready';
  return (
    <button
      type="button"
      disabled={disabled}
      aria-label={sealed ? 'مُهر خورد' : 'برای مُهر، فشار بده و نگه دار'}
      onPointerDown={(e) => begin(e.timeStamp)}
      onPointerUp={stop}
      onPointerLeave={stop}
      onPointerCancel={stop}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !e.repeat) { e.preventDefault(); begin(e.timeStamp); } }}
      onKeyUp={(e) => { if (e.key === 'Enter' || e.key === ' ') stop(); }}
      onContextMenu={(e) => e.preventDefault()}
      className="flex touch-none select-none flex-col items-center gap-2 rounded-full disabled:opacity-50"
    >
      <Seal code={code} nameFa={nameFa} nameEn={nameEn} holding={holding} state={state} progress={progress} size={size} />
      <span className="text-[12px] text-muted">{sealed ? 'مُهر خورد' : busy ? 'در حال تأیید با passkey…' : 'فشار بده و نگه دار'}</span>
    </button>
  );
}
