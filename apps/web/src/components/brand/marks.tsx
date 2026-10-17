import { BRAND } from '@/generated/brand';

const MONO = BRAND.monogram;
const WORD = BRAND.wordmark;

/** The CP monogram, two metals (silver + gold) or one ink. */
export function Monogram({ size = 28, ink, className }: { size?: number; ink?: string; className?: string }) {
  const [, , w, h] = MONO.vb.split(' ').map(Number) as [number, number, number, number];
  return (
    <svg viewBox={MONO.vb} width={size} height={(size * h) / w} className={className} aria-hidden style={{ flex: 'none', display: 'block' }}>
      <path fill={ink ?? 'var(--hq-mark-silver)'} fillRule="evenodd" d={MONO.silver} />
      <path fill={ink ?? 'var(--hq-mark-gold)'} fillRule="evenodd" d={MONO.gold} />
    </svg>
  );
}

/** The owner's CoinePro wordmark: silver "Coine" + gold "Pro" (graphite + ink gold by day). */
export function Wordmark({ width = 108, className }: { width?: number; className?: string }) {
  const [, , w, h] = WORD.vb.split(' ').map(Number) as [number, number, number, number];
  return (
    <svg viewBox={WORD.vb} width={width} height={(width * h) / w} className={className} role="img" aria-label="CoinePro" style={{ flex: 'none', display: 'block' }}>
      <path fill="var(--hq-mark-silver)" fillRule="evenodd" d={WORD.silver} />
      <path fill="var(--hq-mark-gold)" fillRule="evenodd" d={WORD.gold} />
    </svg>
  );
}

/** A company's own mark (data keyed by company code). Mono = one ink (lists, seals). Falls back to the code. */
export function CompanyMark({ code, height = 16, mono = false, ink, kind = 'mark', title }: { code: string; height?: number; mono?: boolean; ink?: string; kind?: 'mark' | 'wordmark'; title?: string }) {
  const m = BRAND.companies[code]?.[kind] ?? BRAND.companies[code]?.mark;
  if (!m) {
    return (
      <span className="fig inline-flex items-center rounded-[5px] border border-strong px-[5px] text-[10px] font-bold tracking-wide text-ink" style={{ height: Math.max(16, height) }} aria-label={title ?? code}>
        {code}
      </span>
    );
  }
  const [, , w, h] = m.vb.split(' ').map(Number) as [number, number, number, number];
  const color = ink ?? 'currentColor';
  return (
    <svg viewBox={m.vb} height={height} width={(height * w) / h} role="img" aria-label={title ?? code} style={{ flex: 'none', display: 'block' }}>
      {m.layers.map((l, i) => (
        <path key={i} fillRule="evenodd" d={l.d} fill={mono || l.role === 'ink' ? color : l.color} />
      ))}
    </svg>
  );
}
