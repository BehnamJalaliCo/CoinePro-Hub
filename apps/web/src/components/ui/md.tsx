import { Fragment, type ReactNode } from 'react';
import { RefLink } from './ref-link';
import { refRoute } from '@/lib/refs';

/** A small, safe Markdown subset for agent-written text: paragraphs, ### headings, - lists, ⟨0.3.0⟩ GFM tables and > quotes,
 *  **bold**, `code` and refs (D-…, M-…, O-…, W-…, A-…; ⟨1.3⟩ F-…, S-…, G-…, AP-…; ⟨1.4⟩ FI-…, PR-…, CH-…, SO-…, H-…, Q-…, E-…,
 *  SK-…, EV-…, TE-…, L-…, C-…, PV-…, N-…, P-…; ⟨1.5⟩ MT-…, K-…, KB-…, OB-…, KR-…, OR-…, RK-…, CE-…, B-…; DM-…, AK-…, WR-…, BR-…, HR-…,
 *  NT-…, CL-…, DP-…, CR-…; ⟨1.6⟩ SR-…, MI-…, LC-…, RD-…, HQ-LGL; ⟨1.7⟩ AR-…, FP-…, PT-…, RR-…, LH-…, RM-…, AU-…, HQ-ARC) as Latin figures. No raw HTML, ever.
 *  A ref inside a path (`hq/S-0004`) stays part of that path. */
const REF = /(?<![/\w-])([DMOWIFSGNPHQELCKB]-\d{3,6}|A-\d{4}|AR-\d{6}|(?:AP|FI|PR|CH|SO|SK|EV|TE|PV|MT|KB|OB|KR|OR|RK|CE|DM|AK|WR|BR|HR|NT|CL|DP|CR|SR|MI|LC|RD|FP|PT|RR|LH|RM|AU)-\d{3,4}|[A-Z]{2,5}(?:-[A-Z]{2,8})?-(?:\d{2,3}|MGR|CEO|ADV|OVR|PA|LGL|ARC|SYS)(?:-\d{4})?)\b/;

function inline(text: string, key: string, links = true): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) out.push(...refs(text.slice(last, m.index), `${key}t${i}`, links));
    const t = m[0];
    if (t.startsWith('**')) out.push(<strong key={`${key}b${i}`} className="font-semibold text-ink">{refs(t.slice(2, -2), `${key}bb${i}`, links)}</strong>);
    else out.push(<code key={`${key}c${i}`} className="fig whitespace-nowrap rounded-[5px] bg-tile px-1 py-px text-[0.92em] text-ink">{t.slice(1, -1)}</code>);
    last = m.index! + t.length;
    i++;
  }
  if (last < text.length) out.push(...refs(text.slice(last), `${key}e`, links));
  return out;
}

// Latin tokens that carry digits (hashes, versions, model names, money) keep Latin digits.
const LATIN = /((?:Opus|Sonnet|Haiku|Fable|Claude|GPT|Gemini) \d+(?:\.\d+)*|(?:\$|[A-Za-z])[A-Za-z0-9._%$/-]*\d[A-Za-z0-9._%/-]*|\d+(?:[.,]\d+)*[A-Za-z][A-Za-z0-9._-]*)/;

function refs(text: string, key: string, links = true): ReactNode[] {
  const parts = text.split(new RegExp(REF.source, 'g'));
  return parts.flatMap((p, i) =>
    i % 2 === 1
      ? [links ? refLink(p, `${key}${i}`) : <span key={`${key}${i}`} className="fig whitespace-nowrap text-gold-ink">{p}</span>]
      : p.split(new RegExp(LATIN.source, 'g')).map((q, j) => (j % 2 === 1 ? <span key={`${key}${i}l${j}`} className="fig whitespace-nowrap">{q}</span> : <Fragment key={`${key}${i}l${j}`}>{q}</Fragment>)),
  );
}

/** ⟨0.5.0⟩ A ref opens its own page (the ref router, lib/refs); one without a page stays a gold figure. */
function refLink(ref: string, key: string): ReactNode {
  const href = refRoute(ref);
  return href
    ? <RefLink key={key} refId={ref} href={href} />
    : <span key={key} className="fig whitespace-nowrap text-gold-ink">{ref}</span>;
}

/** One GFM table row: its cells, without the outer pipes; `\|` stays a pipe inside a cell. */
const cells = (line: string) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'));
const SEPARATOR = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;
/** A cell that is a figure (a number, money, a percentage, a code) reads left to right in Latin digits. */
const FIGURE = /^[-+]?\$?[\d.,]+%?$|^[A-Z]{2,5}$/;

/** ⟨0.3.0⟩ A GFM table (the morning report's companies): a header, aligned columns, scrolling sideways on a narrow screen. */
function Table({ lines, bi }: { lines: string[]; bi: string }) {
  const head = cells(lines[0]!);
  const align = cells(lines[1]!).map((c) => (c.startsWith(':') && c.endsWith(':') ? 'center' : c.endsWith(':') ? 'left' : null));
  const rows = lines.slice(2).map(cells);
  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <table className="w-full min-w-max border-collapse text-[13px] leading-6">
        <thead>
          <tr className="border-b border-strong">{head.map((h, i) => <th key={i} className="whitespace-nowrap px-3 py-2 text-start text-[12px] font-semibold text-ink" style={align[i] ? { textAlign: align[i]! } : undefined}>{inline(h, `${bi}h${i}`)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri} className="border-b border-div last:border-0 even:bg-tile/40">
              {head.map((_, ci) => {
                const c = r[ci] ?? '';
                return <td key={ci} className={FIGURE.test(c) ? 'fig whitespace-nowrap px-3 py-1.5 text-ink' : 'px-3 py-1.5 text-sec'} style={align[ci] ? { textAlign: align[ci]! } : undefined}>{c === '—' ? <span className="text-muted">—</span> : inline(c, `${bi}r${ri}c${ci}`)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Block({ b, bi }: { b: string; bi: string }): ReactNode {
  const lines = b.split('\n').filter((l) => l.trim() !== '');
  if (!lines.length) return null;
  // A table may follow a heading or a paragraph in the same block: what comes before it is its own block.
  const t = lines.findIndex((l, i) => l.trim().startsWith('|') && SEPARATOR.test(lines[i + 1] ?? ''));
  if (t > 0) return <Fragment key={bi}><Block b={lines.slice(0, t).join('\n')} bi={`${bi}a`} /><Block b={lines.slice(t).join('\n')} bi={`${bi}b`} /></Fragment>;
  if (t === 0) {
    const end = lines.findIndex((l, i) => i > 1 && !l.trim().startsWith('|'));
    const rows = end < 0 ? lines : lines.slice(0, end);
    return <Fragment key={bi}><Table lines={rows} bi={bi} />{end > 0 ? <Block b={lines.slice(end).join('\n')} bi={`${bi}c`} /> : null}</Fragment>;
  }
  if (lines.every((l) => /^\s*>/.test(l))) {
    return <blockquote key={bi} className="border-r-2 border-gold-ink/60 pr-3 text-[13px] text-muted">{inline(lines.map((l) => l.replace(/^\s*>\s?/, '')).join(' '), `${bi}q`)}</blockquote>;
  }
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

/** One line of agent text (event summaries, briefs): bold, code and refs, no blocks. Inside a button or a link, [links] is off: the refs
 *  stay gold figures (a link inside a link is not valid). */
export function MdInline({ text, links = true }: { text: string | null | undefined; links?: boolean }) {
  return text ? <>{inline(text.replace(/\s*\n+\s*/g, ' '), 'i', links)}</> : null;
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
