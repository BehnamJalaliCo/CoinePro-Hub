'use client';

// The order's system steps in the session's talk. ⟨1.0.1⟩ C2.2 «خط زمان کار»: each is a thin centred line without a box («مدیر رسانه آمد»
// and its clock time, parted by the hairline), never a ref. One alone is a quiet line; two or more between the same two real turns
// fold into one row («۳ رویداد» and their span of time) that opens to the lines, each wrapped in full.

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Ltr, Sep } from '@/components/look/text';
import { FaText } from '@/components/v29/text';
import { cx, jTime } from '@/lib/format';
import { plain } from '@/lib/plain';

export type SysItem = { at: string; who: string; text: string };

/** One system line: the words wrap in full, the time sits at the row's end. */
export function SysRow({ at, who, text }: SysItem) {
  const t = plain(text);
  return (
    <div className="mx-auto flex max-w-[40rem] items-baseline justify-center px-2 text-center text-[11px] leading-5 text-muted" data-step title={`${who}: ${t}`}>
      <span className="min-w-0 break-words">{who}: <FaText text={t} /></span>
      <Sep />
      <Ltr className="flex-none">{jTime(at)}</Ltr>
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
        className="mx-auto flex max-w-full items-center rounded-full px-3 py-1 text-[11px] leading-5 text-muted hover:bg-hover hover:text-ink">
        <span>{lines.length.toLocaleString('fa-IR')} رویداد</span>
        <Sep />
        <Ltr>{span}</Ltr>
        <Icon name="next" size={12} className={cx('ms-1.5 flex-none transition-transform', open ? 'rotate-90' : '-rotate-90')} />
      </button>
      {open ? <div className="flex flex-col gap-1 py-1" data-sys-lines>{lines.map((l, i) => <SysRow key={`${l.at}-${i}`} {...l} />)}</div> : null}
    </div>
  );
}
