'use client';

// The order's system steps in the session's talk: small, grey, and never a ref. One alone is a quiet line; two or more between the same
// two real turns fold into one row «۳ رویداد · 05:34–05:40» that opens to the lines (wrapped in full, the time at the row's end).

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { FaText } from '@/components/v29/text';
import { cx, jTime } from '@/lib/format';
import { plain } from '@/lib/plain';

export type SysItem = { at: string; who: string; text: string };

/** One system line: the words wrap in full, the time sits at the row's end. */
export function SysRow({ at, who, text }: SysItem) {
  const t = plain(text);
  return (
    <div className="flex items-baseline gap-2 px-2 text-[11px] leading-5 text-muted" data-step title={`${who}: ${t}`}>
      <span className="min-w-0 flex-1 break-words">{who}: <FaText text={t} /></span>
      <span className="fig flex-none">{jTime(at)}</span>
    </div>
  );
}

export function SystemGroup({ lines }: { lines: SysItem[] }) {
  const [open, setOpen] = useState(false);
  const first = lines[0]!;
  const last = lines[lines.length - 1]!;
  const span = jTime(first.at) === jTime(last.at) ? jTime(first.at) : `${jTime(first.at)}–${jTime(last.at)}`;
  return (
    <div className="flex flex-col gap-1" data-sys-group data-count={lines.length}>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
        className="mx-auto flex max-w-full items-center gap-1.5 rounded-full px-3 py-1 text-[11px] leading-5 text-muted hover:bg-hover hover:text-ink">
        <span>{lines.length.toLocaleString('fa-IR')} رویداد</span>
        <span aria-hidden>·</span>
        <span className="fig">{span}</span>
        <Icon name="next" size={12} className={cx('flex-none transition-transform', open ? 'rotate-90' : '-rotate-90')} />
      </button>
      {open ? <div className="flex flex-col gap-1 rounded-[12px] bg-tile/50 p-2" data-sys-lines>{lines.map((l, i) => <SysRow key={`${l.at}-${i}`} {...l} />)}</div> : null}
    </div>
  );
}
