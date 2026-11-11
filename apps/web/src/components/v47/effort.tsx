'use client';

/**
 * ⟨1.0.1⟩ §53 how an output was made: the model's own label and how hard it thought, in Persian («بیشترین دقت» for the highest), where
 * `produced_with` names a model. An output that names none keeps the hub's own label; with neither, nothing is shown.
 */
import { madeWith } from '@/lib/api/v47';
import { Ltr, Sep, seps } from '@/components/look/text';
import { cx } from '@/lib/format';

export function MadeWith({ pw }: { pw: unknown }) {
  const made = madeWith(pw);
  const label = (pw && typeof pw === 'object' ? (pw as { label_fa?: unknown }).label_fa : null);
  if (made) {
    return (
      <div className="flex flex-col" data-testid="made-with">
        <span className="text-[11px] text-muted">ساخت</span>
        <span className="text-[13px] font-semibold"><Ltr>{made.model}</Ltr>{made.effort ? <><Sep />{made.effort}</> : null}</span>
      </div>
    );
  }
  if (typeof label !== 'string' || !label) return null;
  return (
    <div className="flex flex-col" data-testid="made-with">
      <span className="text-[11px] text-muted">ساخته‌شده با</span>
      <span className={cx('text-[13px] font-semibold', !/[؀-ۿ]/.test(label) && 'fig')}>{seps(label)}</span>
    </div>
  );
}

/** Whether there is anything to say about how an output was made. */
export const saysHow = (pw: unknown): boolean => {
  const label = (pw && typeof pw === 'object' ? (pw as { label_fa?: unknown }).label_fa : null);
  return !!madeWith(pw) || (typeof label === 'string' && !!label);
};
