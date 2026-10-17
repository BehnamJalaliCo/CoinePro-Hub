import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { Icon } from '@/components/icon';
import type { IconName } from '@/generated/icons';
import { cx } from '@/lib/format';

type Variant = 'primary' | 'secondary' | 'silver' | 'text' | 'danger' | 'ghost';
type Size = 'sm' | 'md' | 'lg';

const VARIANT: Record<Variant, string> = {
  // Gold = the owner's authority: one primary action per view.
  primary: 'bg-gold text-on-gold font-bold hover:bg-gold-bright active:bg-[var(--hq-gold-pressed)] disabled:bg-disabled-fill disabled:text-disabled',
  secondary: 'border border-strong text-ink hover:bg-hover active:bg-pressed disabled:border-div disabled:text-disabled',
  silver: 'bg-[var(--hq-silver-soft)] text-silver-ink hover:bg-[var(--hq-silver-soft-hover)] active:bg-[var(--hq-silver-soft-pressed)] disabled:bg-disabled-fill disabled:text-disabled',
  text: 'text-gold-ink hover:bg-gold-soft active:bg-gold-soft disabled:text-disabled',
  danger: 'border border-[var(--hq-neg-line)] text-neg hover:bg-neg-soft active:bg-neg-soft disabled:border-div disabled:text-disabled',
  ghost: 'text-sec hover:bg-hover hover:text-ink active:bg-pressed disabled:text-disabled',
};
const SIZE: Record<Size, string> = {
  sm: 'h-8 px-3 text-[12px] gap-1.5 rounded-[8px]',
  md: 'h-10 px-4 text-[13px] gap-2 rounded-[10px]',
  lg: 'h-12 px-[18px] text-[14px] gap-2 rounded-[10px]',
};

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; icon?: IconName; iconEnd?: IconName; loading?: boolean };

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', icon, iconEnd, loading, className, children, disabled, type = 'button', ...rest },
  ref,
) {
  const is = size === 'sm' ? 16 : 18;
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(
        'inline-flex flex-none select-none items-center justify-center whitespace-nowrap font-semibold transition-[background,color,transform] duration-[120ms] active:scale-[.98] disabled:active:scale-100',
        VARIANT[variant], SIZE[size], className,
      )}
      {...rest}
    >
      {loading ? <Spinner size={is} /> : icon ? <Icon name={icon} size={is} /> : null}
      {children ? <span>{children}</span> : null}
      {iconEnd && !loading ? <Icon name={iconEnd} size={is} /> : null}
    </button>
  );
});

export function IconButton({ icon, label, size = 40, className, active, mirror, ...rest }: Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> & { icon: IconName; label: string; size?: number; active?: boolean; mirror?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cx('inline-flex flex-none items-center justify-center rounded-full text-sec transition-colors duration-[120ms] hover:bg-hover hover:text-ink active:bg-pressed', active && 'text-gold-ink', className)}
      style={{ width: size, height: size }}
      {...rest}
    >
      <Icon name={icon} size={Math.round(size * 0.5)} active={active} mirror={mirror} />
    </button>
  );
}

export function Spinner({ size = 18, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={cx('flex-none', className)} style={{ animation: 'hq-spin .9s linear infinite' }} aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity=".25" strokeWidth="2.4" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}
