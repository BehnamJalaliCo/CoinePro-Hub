import { Fragment, type ReactNode } from 'react';

/** A small, safe Markdown subset for agent-written text: paragraphs, ### headings, - lists,
 *  **bold**, `code` and refs (D-…, M-…, O-…, W-…, A-…, and ⟨1.3⟩ F-…, S-…, G-…, AP-…) as Latin figures. No raw HTML, ever.
 *  A ref inside a path (`hq/S-0004`) stays part of that path. */
const REF = /(?<![/\w-])([DMOWIFSG]-\d{3,6}|A-\d{4}|AP-\d{4}|[A-Z]{2,5}(?:-[A-Z]{2,8})?-(?:\d{2,3}|MGR|CEO|ADV|SYS)(?:-\d{4})?)\b/;

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) out.push(...refs(text.slice(last, m.index), `${key}t${i}`));
    const t = m[0];
    if (t.startsWith('**')) out.push(<strong key={`${key}b${i}`} className="font-semibold text-ink">{refs(t.slice(2, -2), `${key}bb${i}`)}</strong>);
    else out.push(<code key={`${key}c${i}`} className="fig whitespace-nowrap rounded-[5px] bg-tile px-1 py-px text-[0.92em] text-ink">{t.slice(1, -1)}</code>);
    last = m.index! + t.length;
    i++;
  }
  if (last < text.length) out.push(...refs(text.slice(last), `${key}e`));
  return out;
}

// Latin tokens that carry digits (hashes, versions, model names, money) keep Latin digits.
const LATIN = /((?:Opus|Sonnet|Haiku|Fable|Claude|GPT|Gemini) \d+(?:\.\d+)*|(?:\$|[A-Za-z])[A-Za-z0-9._%$/-]*\d[A-Za-z0-9._%/-]*|\d+[A-Za-z][A-Za-z0-9._-]*)/;

function refs(text: string, key: string): ReactNode[] {
  const parts = text.split(new RegExp(REF.source, 'g'));
  return parts.flatMap((p, i) =>
    i % 2 === 1
      ? [<span key={`${key}${i}`} className="fig whitespace-nowrap text-gold-ink">{p}</span>]
      : p.split(new RegExp(LATIN.source, 'g')).map((q, j) => (j % 2 === 1 ? <span key={`${key}${i}l${j}`} className="fig whitespace-nowrap">{q}</span> : <Fragment key={`${key}${i}l${j}`}>{q}</Fragment>)),
  );
}

function Block({ b, bi }: { b: string; bi: string }): ReactNode {
  const lines = b.split('\n').filter((l) => l.trim() !== '');
  if (!lines.length) return null;
  const h = /^(#{1,4})\s+(.*)$/.exec(lines[0] ?? '');
  if (h) {
    return (
      <Fragment key={bi}>
        <h4 className="pt-1 text-[14px] font-semibold text-ink">{inline(h[2]!, `${bi}h`)}</h4>
        {lines.length > 1 ? <Block b={lines.slice(1).join('\n')} bi={`${bi}r`} /> : null}
      </Fragment>
    );
  }
  if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
    return <ul key={bi} className="flex list-disc flex-col gap-1 pr-5 marker:text-muted">{lines.map((l, li) => <li key={li}>{inline(l.replace(/^\s*[-*•]\s+/, ''), `${bi}-${li}`)}</li>)}</ul>;
  }
  if (lines.every((l) => /^\s*\d+[.)]\s+/.test(l))) {
    return <ol key={bi} className="flex list-decimal flex-col gap-1 pr-5 marker:text-muted">{lines.map((l, li) => <li key={li}>{inline(l.replace(/^\s*\d+[.)]\s+/, ''), `${bi}-${li}`)}</li>)}</ol>;
  }
  return <p key={bi}>{inline(lines.join(' '), bi)}</p>;
}

/** One line of agent text (event summaries, briefs): bold, code and refs, no blocks. */
export function MdInline({ text }: { text: string | null | undefined }) {
  return text ? <>{inline(text.replace(/\s*\n+\s*/g, ' '), 'i')}</> : null;
}

export function Md({ text, className }: { text: string | null | undefined; className?: string }) {
  if (!text) return null;
  const blocks = text.replace(/\r\n/g, '\n').split(/\n{2,}/);
  return (
    <div className={className ?? 'flex flex-col gap-2 text-[14px] leading-7 text-sec'}>
      {blocks.map((b, bi) => <Block key={bi} b={b} bi={String(bi)} />)}
    </div>
  );
}
