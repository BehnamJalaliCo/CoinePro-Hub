import { Fragment, type ReactNode } from 'react';

// ⟨1.10.1⟩ Contract §28.5 note, the owner (2026-11-01): Latin inside Persian text. The body font draws digits as Persian; a Latin token
// (a model name and its version, a path, a ref, a URL, money) keeps its Latin digits and its own direction, isolated from the right-to-left
// run around it, so «ChatGPT: مدل‌های در دسترس نیست: GPT 5.5، GPT 5.3» reads exactly so. A count in Persian prose (a bare number) stays
// Persian.

/** A Latin token: starts with a letter, a digit or a currency sign; carries letters, digits and the punctuation of paths, versions, URLs. */
const TOKEN = String.raw`[A-Za-z0-9$€£@#][A-Za-z0-9._\-/:@#%+~=?&$€£]*`;
/** Latin words in a row ("GPT 5.5", "Claude Opus 5.5") are one run. */
const RUN = new RegExp(`${TOKEN}(?:[ \\u00A0]+${TOKEN})*`, 'g');
/**
 * A run is Latin when it has a Latin letter or a currency sign, or is a version, an address or a path made of digits (2.14.1, 10.10.1.4,
 * 2026/10/31); a bare number (a count, a decimal) stays in the prose, in Persian digits.
 */
const IS_LATIN = /[A-Za-z$€£]|\d\.\d+\.\d|\d[/@#]\d/;
/** Sentence punctuation after a token belongs to the sentence, not to the token. */
const TRAILING = /[.:,;!?)\]-]+$/;

export type BidiPart = { latin: boolean; text: string };

/** [text] cut into Persian and Latin runs. */
export function bidiParts(text: string): BidiPart[] {
  const out: BidiPart[] = [];
  let last = 0;
  const push = (latin: boolean, t: string) => {
    if (!t) return;
    const prev = out[out.length - 1];
    if (prev && prev.latin === latin) prev.text += t; else out.push({ latin, text: t });
  };
  for (const m of text.matchAll(RUN)) {
    let run = m[0];
    const tail = TRAILING.exec(run)?.[0] ?? '';
    // A run made only of a bare number and punctuation is prose.
    run = run.slice(0, run.length - tail.length);
    if (!run || !IS_LATIN.test(run)) continue;
    push(false, text.slice(last, m.index));
    push(true, run);
    last = m.index! + run.length;
  }
  push(false, text.slice(last));
  return out;
}

/** A Latin run as the page shows it: isolated (<bdi>), in the Latin-digit face; a long one (a path, a URL) may break anywhere. */
export function LatinRun({ text }: { text: string }) {
  return <bdi dir="ltr" className={text.length > 24 ? 'latin [overflow-wrap:anywhere]' : 'latin'}>{text}</bdi>;
}

/** [text] with its Latin runs isolated; for any plain string shown in Persian. */
export function bidi(text: string | null | undefined, key = 'b'): ReactNode[] {
  if (!text) return [];
  return bidiParts(text).map((p, i) => (p.latin ? <LatinRun key={`${key}${i}`} text={p.text} /> : <Fragment key={`${key}${i}`}>{p.text}</Fragment>));
}

/** The same as a component: `<Bidi text={reason} />`. */
export function Bidi({ text }: { text: string | null | undefined }) {
  return <>{bidi(text)}</>;
}
