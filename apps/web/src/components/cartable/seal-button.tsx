'use client';

import { useEffect, useRef, useState } from 'react';
import { Seal, type SealState } from '@/components/brand/seal';

const HOLD_MS = 600; // tokens: motion.duration.sealHold

/** The seal ritual (D2): press and hold the seal; a gold ring fills; releasing early cancels.
 *  Keyboard: Enter/Space held the same way. On completion `onSealed` runs (step-up + approve). */
export function SealButton({ code, nameFa, nameEn, holding, disabled, busy, sealed, onSealed, size = 96 }: { code: string; nameFa: string; nameEn: string; holding?: boolean; disabled?: boolean; busy?: boolean; sealed?: boolean; onSealed: () => void; size?: number }) {
  const [p, setP] = useState(0);
  const start = useRef<number | null>(null);
  const raf = useRef<number | null>(null);
  const fired = useRef(false);

  const stop = () => {
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = null;
    start.current = null;
    if (!fired.current) setP(0);
  };
  const tick = () => {
    if (start.current == null) return;
    const v = Math.min(100, ((performance.now() - start.current) / HOLD_MS) * 100);
    setP(v);
    if (v >= 100) {
      fired.current = true;
      stop();
      navigator.vibrate?.(18);
      onSealed();
      return;
    }
    raf.current = requestAnimationFrame(tick);
  };
  const begin = () => {
    if (disabled || busy || sealed) return;
    fired.current = false;
    start.current = performance.now();
    raf.current = requestAnimationFrame(tick);
  };
  useEffect(() => () => { if (raf.current) cancelAnimationFrame(raf.current); }, []);
  useEffect(() => { if (!busy && !sealed) { fired.current = false; setP(0); } }, [busy, sealed]);

  const state: SealState = sealed ? 'sealed' : p > 0 || busy ? 'holding' : 'ready';
  return (
    <button
      type="button"
      disabled={disabled}
      aria-label={sealed ? 'مُهر خورد' : 'برای مُهر، فشار بده و نگه دار'}
      onPointerDown={begin}
      onPointerUp={stop}
      onPointerLeave={stop}
      onPointerCancel={stop}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !e.repeat) { e.preventDefault(); begin(); } }}
      onKeyUp={(e) => { if (e.key === 'Enter' || e.key === ' ') stop(); }}
      onContextMenu={(e) => e.preventDefault()}
      className="flex touch-none select-none flex-col items-center gap-2 rounded-full disabled:opacity-50"
    >
      <Seal code={code} nameFa={nameFa} nameEn={nameEn} holding={holding} state={state} progress={busy ? 100 : p} size={size} />
      <span className="text-[12px] text-muted">{sealed ? 'مُهر خورد' : busy ? 'در حال تأیید با passkey…' : 'فشار بده و نگه دار'}</span>
    </button>
  );
}
