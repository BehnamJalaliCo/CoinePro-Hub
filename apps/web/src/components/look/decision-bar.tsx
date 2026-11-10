'use client';

// ⟨1.0.1⟩ Part C, «نوار تصمیم» (C0.2): what waits for the owner is answered where he sees it, with one tap. One bar, stuck to the
// bottom (of a sheet, or of the page above the navigation): one optional line of what is decided, ONE primary action (the screen's
// only full gold), up to two quiet actions beside it. While the act is on its way the primary shows a small arc; when it is done a
// tick draws itself (M8) and the bar leaves. The action it carries is never repeated at the bottom of the scroll.

import { useEffect, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { bidi } from '@/components/ui/bidi';
import type { IconName } from '@/generated/icons';
import { cx } from '@/lib/format';
import { DrawnTick } from './ring';

export type DecisionState = 'idle' | 'working' | 'done';
export type DecisionAction = { label: string; onClick?: () => void; icon?: IconName; disabled?: boolean; type?: 'button' | 'submit'; form?: string };
export type QuietAction = DecisionAction & { tone?: 'neutral' | 'danger' };

const DONE_MS = 900;

export function DecisionBar({ context, error, primary, quiet = [], state = 'idle', doneLabel = 'انجام شد', onLeft, place = 'sheet', label = 'تصمیم', className }: {
  /** One sentence: what is decided here. */
  context?: ReactNode;
  /** The hub's own words when the act failed; shown above the actions in place of the context. */
  error?: string | null;
  primary: DecisionAction;
  /** At most two (e.g. «اصلاح», «بعداً»). */
  quiet?: QuietAction[];
  state?: DecisionState;
  doneLabel?: string;
  /** Called once the «done» tick has been seen: the caller takes the bar away. */
  onLeft?: () => void;
  /** `sheet`: the bottom of a sheet (the sheet places it). `page`: stuck above the navigation at the bottom of the page. */
  place?: 'sheet' | 'page';
  label?: string;
  className?: string;
}) {
  useEffect(() => {
    if (state !== 'done' || !onLeft) return;
    const t = setTimeout(onLeft, DONE_MS);
    return () => clearTimeout(t);
  }, [state, onLeft]);
  return (
    <div role="group" aria-label={label} data-testid="decision-bar" data-state={state}
      className={cx(
        'flex flex-col gap-2',
        place === 'page'
          ? 'sticky bottom-[calc(84px+env(safe-area-inset-bottom))] z-20 rounded-[16px] bg-raised/95 p-3 shadow-[0_12px_32px_rgba(0,0,0,.32)] ring-1 ring-div backdrop-blur-md lg:bottom-4'
          : 'border-t border-div bg-page px-5 pb-[calc(12px+env(safe-area-inset-bottom))] pt-3',
        className,
      )}>
      {error ? <p role="alert" className="text-[12px] leading-5 text-neg">{bidi(error)}</p>
        : context ? <p className="text-[12px] leading-5 text-sec" data-decision-context>{context}</p> : null}
      {state === 'done' ? (
        <div role="status" className="hq-m2-in flex h-12 items-center justify-center gap-2 text-[14px] font-semibold text-ink">
          <span className="text-pos"><DrawnTick size={20} /></span>{doneLabel}
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <Button variant="primary" size="lg" className="min-w-0 grow" icon={primary.icon} type={primary.type ?? 'button'} form={primary.form}
            disabled={primary.disabled} loading={state === 'working'} onClick={primary.onClick}>{primary.label}</Button>
          {quiet.slice(0, 2).map((q) => (
            <Button key={q.label} variant={q.tone === 'danger' ? 'danger' : 'secondary'} size="lg" icon={q.icon} type={q.type ?? 'button'} form={q.form}
              disabled={q.disabled || state === 'working'} onClick={q.onClick}>{q.label}</Button>
          ))}
        </div>
      )}
    </div>
  );
}
