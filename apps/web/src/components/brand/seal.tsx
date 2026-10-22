'use client';

import { useId } from 'react';
import { BRAND } from '@/generated/brand';
import type { BrandMark } from '@/lib/api/brand';
import { CompanyMark, MarkSvg } from './company-mark';
import { Monogram } from './marks';

export type SealState = 'ready' | 'holding' | 'sealed';
type Props = {
  /** Company code; the holding seal when `holding` is true. */
  code: string;
  nameFa: string;
  nameEn: string;
  holding?: boolean;
  state?: SealState;
  size?: number;
  /** Hold progress 0..100 while `state === 'holding'`. */
  progress?: number;
  dateLabel?: string;
  /** A brand version to draw in place of the company's own mark: the owner looks at a proposal before sealing it (§18.14). */
  mark?: BrandMark | null;
};

const star = (cx: number, cy: number, ro: number, ri: number, n: number, rot = -90) => {
  const pts: string[] = [];
  for (let k = 0; k < 2 * n; k++) {
    const r = k % 2 === 0 ? ro : ri;
    const a = ((rot + (180 / n) * k) * Math.PI) / 180;
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return pts.join(' ');
};

function Arc({ id, cx, r, text, fs, fill, top, latin }: { id: string; cx: number; r: number; text: string; fs: number; fill: string; top: boolean; latin?: boolean }) {
  const rb = top ? r - fs * 0.35 : r + fs * 0.35;
  const d = top ? `M ${cx - rb},${cx} a ${rb},${rb} 0 1,1 ${2 * rb},0` : `M ${cx - rb},${cx} a ${rb},${rb} 0 1,0 ${2 * rb},0`;
  return (
    <>
      <path id={id} d={d} fill="none" />
      <text fontFamily={latin ? 'IRANYekanX, sans-serif' : 'IRANYekanXFaNum, IRANYekanX, sans-serif'} fontSize={fs} fontWeight={700} fill={fill} letterSpacing={latin ? fs * 0.22 : 0.2}>
        <textPath href={`#${id}`} startOffset="50%" textAnchor="middle">{text}</textPath>
      </text>
    </>
  );
}

/** The seal ("مُهر"), D2 owner decision 2026-10-17: a company seal carries the company's own mark with its
 *  name around it; the holding seal is the distinct one (24-ray sunburst, lapis jewel when sealed, two-metal CP). */
export function Seal({ code, nameFa, nameEn, holding = false, state = 'ready', size = 88, progress = 0, dateLabel, mark: proposal }: Props) {
  const uid = useId().replace(/:/g, '');
  const s = size;
  const cx = s / 2;
  const sealed = state === 'sealed';
  const showText = s >= 80;
  const gold = 'var(--hq-gold-fill)';
  const goldInk = 'var(--hq-gold-ink)';
  let parts: React.ReactNode;
  let mark: React.ReactNode;

  if (holding) {
    const metal = sealed ? gold : goldInk;
    const rTxt = (s / 2 * 0.85 + s / 2 * 0.57) / 2;
    parts = (
      <>
        {sealed
          ? <polygon points={star(cx, cx, s / 2, (s / 2) * 0.92, 24)} fill={metal} />
          : <polygon points={star(cx, cx, s / 2 - 0.6, (s / 2) * 0.92, 24)} fill="none" stroke={metal} strokeWidth={1} strokeLinejoin="round" />}
        <circle cx={cx} cy={cx} r={(s / 2) * 0.89} fill={sealed ? 'var(--hq-lapis-disc)' : 'var(--hq-surface-page)'} />
        <circle cx={cx} cy={cx} r={(s / 2) * 0.85} fill="none" stroke={metal} strokeWidth={1.2} />
        <circle cx={cx} cy={cx} r={(s / 2) * 0.57} fill="none" stroke={metal} strokeOpacity={0.55} strokeWidth={1} />
        {showText && (
          <>
            <Arc id={`${uid}a`} cx={cx} r={rTxt} text="ستاد کوینه‌پرو · مُهر مدیر کل" fs={s * 0.068} fill={metal} top />
            <Arc id={`${uid}b`} cx={cx} r={rTxt} text="COINEPRO HOLDING" fs={s * 0.05} fill={metal} top={false} latin />
            {[180, 0].map((ang) => (
              <polygon key={ang} points={star(cx + rTxt * Math.cos((ang * Math.PI) / 180), cx + rTxt * Math.sin((ang * Math.PI) / 180), s * 0.03, s * 0.013, 8)} fill={metal} />
            ))}
          </>
        )}
      </>
    );
    mark = sealed ? (
      <svg viewBox={BRAND.monogram.vb} width={s * 0.34} aria-hidden style={{ display: 'block' }}>
        <path fill="#DBDBDB" fillRule="evenodd" d={BRAND.monogram.silver} />
        <path fill="#D8A848" fillRule="evenodd" d={BRAND.monogram.gold} />
      </svg>
    ) : <Monogram size={Math.round(s * 0.34)} />;
  } else {
    const ink = sealed ? 'var(--hq-text-on-gold)' : goldInk;
    const rOut = s / 2 - 1;
    const rIn = (s / 2) * 0.6;
    const rTxt = (rOut - s * 0.045 + rIn) / 2;
    parts = (
      <>
        <circle cx={cx} cy={cx} r={rOut} fill={sealed ? gold : 'var(--hq-surface-page)'} stroke={sealed ? gold : goldInk} strokeWidth={1.5} />
        <circle cx={cx} cy={cx} r={rOut - s * 0.045} fill="none" stroke={ink} strokeOpacity={0.35} strokeWidth={0.8} />
        <circle cx={cx} cy={cx} r={rIn} fill="none" stroke={ink} strokeOpacity={0.5} strokeWidth={1} />
        {showText && (
          <>
            <Arc id={`${uid}a`} cx={cx} r={rTxt} text={nameFa} fs={s * 0.088} fill={ink} top />
            <Arc id={`${uid}b`} cx={cx} r={rTxt} text={nameEn.toUpperCase()} fs={s * 0.056} fill={ink} top={false} latin />
            {[180, 0].map((ang) => (
              <circle key={ang} cx={cx + rTxt * Math.cos((ang * Math.PI) / 180)} cy={cx + rTxt * Math.sin((ang * Math.PI) / 180)} r={Math.max(1, s * 0.014)} fill={ink} />
            ))}
          </>
        )}
      </>
    );
    // The company's mark as CompanyMark resolves it (GET /brands, then the built-in marks), engraved in one ink; none → the CP monogram.
    const h = Math.round(s * (showText ? 0.36 : 0.5));
    mark = proposal
      ? <MarkSvg mark={proposal} height={h} mono ink={ink} />
      : <CompanyMark code={code} height={h} mono ink={ink} fallback={<Monogram size={Math.round(s * 0.3)} ink={ink} />} />;
  }

  const R = s / 2 + 5;
  const c = 2 * Math.PI * R;
  const name = holding ? 'هلدینگ کوینه‌پرو' : nameFa;
  return (
    <span className="flex flex-none flex-col items-center gap-1.5" role="img" aria-label={sealed ? `مُهر ${name} خورد` : `مُهر ${name}`}>
      <span className="relative block" style={{ width: s, height: s }}>
        {state === 'holding' && (
          <svg width={s + 12} height={s + 12} viewBox={`0 0 ${s + 12} ${s + 12}`} className="absolute -left-1.5 -top-1.5 -rotate-90" aria-hidden>
            <circle cx={s / 2 + 6} cy={s / 2 + 6} r={R} fill="none" stroke="var(--hq-line-tahrir)" strokeWidth={3} />
            <circle cx={s / 2 + 6} cy={s / 2 + 6} r={R} fill="none" stroke="var(--hq-gold-fill)" strokeWidth={3} strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - progress / 100)} />
          </svg>
        )}
        <span
          className="relative block transition-transform"
          style={{ width: s, height: s, transform: sealed ? 'rotate(-6deg)' : state === 'holding' ? 'scale(.96)' : undefined, transitionDuration: 'var(--hq-dur-ceremony)', transitionTimingFunction: 'var(--hq-ease-ceremony)' }}
        >
          <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} className="absolute inset-0 overflow-visible" aria-hidden>{parts}</svg>
          <span className="absolute inset-0 flex items-center justify-center">{mark}</span>
        </span>
      </span>
      {sealed && dateLabel ? <span className="text-micro text-gold-ink">{dateLabel}</span> : null}
    </span>
  );
}
