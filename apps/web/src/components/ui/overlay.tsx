'use client';

import * as D from '@radix-ui/react-dialog';
import { type ReactNode } from 'react';
import { cx } from '@/lib/format';
import { IconButton } from './button';

/** Side sheet (web: from the left in RTL, D1 shell) and bottom sheet (narrow screens). */
export function Sheet({ open, onOpenChange, title, description, children, footer, width = 480 }: { open: boolean; onOpenChange: (v: boolean) => void; title: ReactNode; description?: ReactNode; children: ReactNode; footer?: ReactNode; width?: number }) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-scrim data-[state=open]:animate-[hq-rise_200ms_both]" />
        <D.Content
          className={cx(
            'fixed z-50 flex flex-col bg-page shadow-[0_24px_64px_rgba(0,0,0,.45)] outline-none',
            'inset-x-0 bottom-0 max-h-[92dvh] rounded-t-[20px] md:inset-y-0 md:left-0 md:right-auto md:max-h-none md:rounded-none md:rounded-r-[20px]',
          )}
          style={{ width: undefined, maxWidth: '100vw' }}
        >
          {/* min-h-0: on narrow screens the sheet is capped at 92dvh; without it a long form pushes the footer off the screen instead of scrolling. */}
          <div className="flex min-h-0 w-full flex-col md:h-full" style={{ width: `min(100vw, ${width}px)` }}>
            <div className="flex items-start gap-3 border-b border-div px-5 py-4">
              <div className="flex min-w-0 flex-1 flex-col">
                <D.Title className="text-h3 font-semibold text-ink">{title}</D.Title>
                {description ? <D.Description className="text-caption text-muted">{description}</D.Description> : <D.Description className="sr-only">{typeof title === 'string' ? title : ''}</D.Description>}
              </div>
              <D.Close asChild><IconButton icon="close" label="بستن" size={36} /></D.Close>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
            {footer ? <div className="border-t border-div px-5 py-3">{footer}</div> : null}
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

/** Centered dialog for confirmations (destructive actions name the consequence). */
export function Dialog({ open, onOpenChange, title, children, actions }: { open: boolean; onOpenChange: (v: boolean) => void; title: ReactNode; children: ReactNode; actions: ReactNode }) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-scrim" />
        <D.Content className="fixed left-1/2 top-1/2 z-50 flex w-[min(92vw,440px)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-[20px] bg-raised p-6 shadow-[0_24px_64px_rgba(0,0,0,.45)] outline-none">
          <D.Title className="text-h3 font-semibold text-ink">{title}</D.Title>
          <D.Description asChild><div className="text-body text-sec">{children}</div></D.Description>
          <div className="flex flex-row-reverse flex-wrap gap-2">{actions}</div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
