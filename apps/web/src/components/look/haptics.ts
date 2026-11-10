// ⟨1.0.1⟩ Part C, M21 «لرزش»: three subtle haptics, each answering an act of the owner, never a passive update.
// `tick`: a step done, a selection, «خوانده شد». `seal`: an approval sent. `error`: two short taps.
// Where the browser has no vibration (desktop, iOS) this is silently nothing.

export type Haptic = 'tick' | 'seal' | 'error';

const PATTERN: Record<Haptic, number | number[]> = { tick: 10, seal: 30, error: [12, 70, 12] };

export function haptic(kind: Haptic): void {
  try {
    if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') navigator.vibrate(PATTERN[kind]);
  } catch {
    // a browser that refuses (no user activation yet): nothing
  }
}
