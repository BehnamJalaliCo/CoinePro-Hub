'use client';

// ⟨1.11⟩ The hub's plain Persian (§29.7) as the owner reads it: Latin runs isolated, every number a Latin figure, paragraphs justified.

import { Fragment } from 'react';
import { bidiParts, LatinRun } from '@/components/ui/bidi';
import { cx } from '@/lib/format';

// A figure keeps its sign, separators, a decimal point and a percent sign together: "1,200", "3.4", "38%", "+200", a time "05:40" or a
// date "2026/11/03". A space is part of it only before a percent sign, so the words around it keep their own spaces.
const NUMBER = /((?:[+−-])?\d(?:[\d,:/]*\d)?(?:\.\d+)?(?:\s?[%٪])?)/;

/** One plain string from the hub: Latin runs isolated, every number in Latin figures (§29.7), the words around them in Persian. */
export function FaText({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  return (
    <>
      {bidiParts(text).map((p, i) => (p.latin ? <LatinRun key={i} text={p.text} /> : (
        <Fragment key={i}>{p.text.split(NUMBER).map((x, j) => (j % 2 === 1 ? <span key={j} className="fig">{x}</span> : x))}</Fragment>
      )))}
    </>
  );
}

/** A paragraph of the hub's words, justified with its last line at the start. */
export function FaPara({ text, className }: { text: string | null | undefined; className?: string }) {
  if (!text) return null;
  return <p className={cx('text-justify [text-align-last:start] [overflow-wrap:break-word]', className)}><FaText text={text} /></p>;
}

/** «1,200»: a count or a figure in Latin digits. */
export const fig = (n: number | string | null | undefined, digits = 0) =>
  n == null || n === '' ? '—' : typeof n === 'number' ? n.toLocaleString('en-US', { maximumFractionDigits: digits }) : String(n);

