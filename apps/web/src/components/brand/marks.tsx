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

// A company's own mark reads GET /brands, so it lives in a client module; server components that import this file
// (not-found, the sign-in layout) only draw the holding's marks.
export { CompanyMark } from './company-mark';
