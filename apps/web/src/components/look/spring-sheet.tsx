'use client';

// ⟨1.0.1⟩ Part C, M15 «برگه‌ی فنری» (C0.3): the ONE sheet of the look. A handle; as tall as its content (never a full-height sheet
// with an empty half); it follows the finger on its handle and title, settles like a spring, and a drag down closes it; its primary
// action is stuck to its bottom (`bar`: a DecisionBar). On a wide screen it is the same sheet, centred. Under reduced motion it is
// simply there.

import * as D from '@radix-ui/react-dialog';
import { useCallback, useRef, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { IconButton } from '@/components/ui/button';
import { cx } from '@/lib/format';

const CLOSE_PX = 120;
const CLOSE_SPEED = 0.6; // px per ms
const LEAVE_MS = 200;

export function SpringSheet({ open, onOpenChange, title, description, children, bar, width = 560, testid, onOpened }: {
  open: boolean; onOpenChange: (v: boolean) => void; title: ReactNode; description?: ReactNode; children: ReactNode;
  /** The sheet's decision bar, stuck to its bottom. */
  bar?: ReactNode;
  width?: number; testid?: string;
  /** After the sheet has opened and taken the focus (e.g. to move it to the first field). */
  onOpened?: (e: Event) => void;
}) {
  const sheet = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: number; y0: number; y: number; t: number; v: number } | null>(null);

  const down = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 && e.pointerType === 'mouse') return;
    if ((e.target as HTMLElement).closest('button, a, input, textarea, select')) return;
    drag.current = { id: e.pointerId, y0: e.clientY, y: e.clientY, t: e.timeStamp, v: 0 };
    e.currentTarget.setPointerCapture(e.pointerId);
    sheet.current?.removeAttribute('data-settle');
  }, []);
  const move = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    const el = sheet.current;
    if (!d || d.id !== e.pointerId || !el) return;
    const dt = e.timeStamp - d.t;
    if (dt > 0) d.v = (e.clientY - d.y) / dt;
    d.y = e.clientY;
    d.t = e.timeStamp;
    // It follows the finger down; upward it gives a little and holds.
    const dy = d.y - d.y0;
    el.style.transform = `translateY(${dy >= 0 ? dy : -Math.sqrt(-dy)}px)`;
  }, []);
  const up = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    const el = sheet.current;
    if (!d || d.id !== e.pointerId) return;
    drag.current = null;
    if (!el) return;
    const dy = d.y - d.y0;
    el.setAttribute('data-settle', '');
    if (dy > CLOSE_PX || (dy > 24 && d.v > CLOSE_SPEED)) {
      el.style.transform = 'translateY(100%)';
      setTimeout(() => onOpenChange(false), LEAVE_MS);
    } else {
      el.style.transform = '';
    }
  }, [onOpenChange]);

  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="hq-scrim fixed inset-0 z-40 bg-scrim" />
        <D.Content ref={sheet} data-testid={testid} data-spring-sheet onOpenAutoFocus={onOpened}
          className="hq-sheet fixed inset-x-0 bottom-0 z-50 mx-auto flex max-h-[92dvh] w-full flex-col rounded-t-[20px] bg-page shadow-[0_-12px_48px_rgba(0,0,0,.4)] outline-none"
          style={{ maxWidth: `min(100vw, ${width}px)` }}>
          <div className="flex flex-none cursor-grab touch-none select-none flex-col active:cursor-grabbing" data-sheet-handle
            onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
            <span aria-hidden className="mx-auto mt-2.5 h-1 w-9 rounded-full bg-strong" />
            <div className="flex items-start gap-3 px-5 pb-2 pt-2">
              <div className="flex min-w-0 flex-1 flex-col">
                <D.Title className="text-h3 font-semibold text-ink">{title}</D.Title>
                {description ? <D.Description className="text-caption text-muted">{description}</D.Description> : <D.Description className="sr-only">{typeof title === 'string' ? title : ''}</D.Description>}
              </div>
              <D.Close asChild><IconButton icon="close" label="بستن" size={36} /></D.Close>
            </div>
          </div>
          <div className={cx('min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pt-1', bar ? 'pb-4' : 'pb-[calc(20px+env(safe-area-inset-bottom))]')}>{children}</div>
          {bar ? <div className="flex-none">{bar}</div> : null}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
