import { createElement } from 'react';
import { ICONS, type IconName } from '@/generated/icons';

type Props = {
  name: IconName;
  size?: number;
  /** Filled "heart" for the active state (nav, toggles). */
  active?: boolean;
  /** Mirror for RTL when the glyph has a direction (back, next). */
  mirror?: boolean;
  strokeWidth?: number;
  className?: string;
  label?: string;
};

/** Divan icon set (design/icons): 24-grid, 1.6 stroke, round caps. Colour = currentColor. */
export function Icon({ name, size = 22, active = false, mirror = false, strokeWidth = 1.6, className, label }: Props) {
  const els = ICONS[name];
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={mirror ? { transform: 'scaleX(-1)', flex: 'none' } : { flex: 'none' }}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {els.map((e, i) => {
        const a: Record<string, string> = {};
        for (const [k, v] of Object.entries(e.a)) a[k.replace(/-([a-z])/g, (_, c: string) => c.toUpperCase())] = v;
        if (e.role === 'heart') return active ? createElement(e.tag, { key: i, ...a, fill: 'currentColor', stroke: 'none', opacity: 0.9 }) : null;
        return createElement(e.tag, { key: i, ...a });
      })}
    </svg>
  );
}
