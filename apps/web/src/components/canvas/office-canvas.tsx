'use client';

// ⟨1.17⟩ Contract §35.6 «بوم»: the owner's canvas of the holding. The hub is the centre, each company a node, and the links between companies
// are edges drawn by their kind (arrow from the one that gives to the one that gets, dotted when turned off). He shapes it: drag a company to
// place it (PUT /canvas/nodes/{code}; a node with no place sits on a circle), «ارتباط تازه» then two companies opens the link form, a click on
// a link edits or turns it off, a click on a company opens its panel. Arrow keys move a focused company. Nothing is ever deleted.

import Link from 'next/link';
import { useMemo, useRef, useState } from 'react';
import { CompanyMark, Monogram } from '@/components/brand/marks';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, FilterChip, Pill, SectionTitle } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { PlainPara, PlainText } from '@/components/v29/bits';
import { errText, field } from '@/components/v31/kit';
import { LINK_KIND, layoutNodes, useCanvasActions, type Canvas, type CanvasNode, type CompanyLink, type LinkKind, type SessionCard } from '@/lib/api/v34';
import { cx } from '@/lib/format';
import { SessionRow } from '@/components/session/session-row';

/** One colour and one dash per kind; the word on the edge always says it too. */
const KIND_STYLE: Record<LinkKind, { color: string; dash?: string }> = {
  serves: { color: 'var(--hq-gold-ink)' },
  publishes: { color: 'var(--hq-lapis)' },
  feeds: { color: 'var(--hq-positive)', dash: '6 4' },
  sells: { color: 'var(--hq-warning)' },
  supports: { color: 'var(--hq-silver-ink)', dash: '2 4' },
};
const KINDS = Object.keys(KIND_STYLE) as LinkKind[];
const clamp = (v: number) => Math.min(0.94, Math.max(0.06, v));

type Sheet_ = { type: 'company'; code: string } | { type: 'new'; from: string; to: string } | { type: 'edit'; id: string } | null;

export function OfficeCanvas({ canvas, sessions }: { canvas: Canvas; sessions: SessionCard[] }) {
  const toast = useToast();
  const act = useCanvasActions();
  const box = useRef<HTMLDivElement | null>(null);
  // [sx, sy]: where the pointer went down; [ox, oy]: the grab offset from the node's centre. A drag is a move once the pointer has gone
  // past the threshold from where it started (not from its last move), and the node follows the pointer less that offset.
  const [drag, setDrag] = useState<{ code: string; px: number; py: number; sx: number; sy: number; ox: number; oy: number; moved: boolean } | null>(null);
  const [connect, setConnect] = useState<{ from: string | null } | null>(null);
  const [sheet, setSheet] = useState<Sheet_>(null);
  const placed = useMemo(() => layoutNodes(canvas.nodes), [canvas.nodes]);
  const at = (code: string) => {
    if (drag?.code === code) return { px: drag.px, py: drag.py };
    const n = placed.find((x) => x.code === code);
    return n ? { px: n.px, py: n.py } : { px: 0.5, py: 0.5 };
  };
  const hub = canvas.nodes.find((n) => n.kind === 'holding');
  const companies = canvas.nodes.filter((n) => n.kind === 'company');

  // The edges: every company to the hub (implicit, thin), and each link, spread a little when two share a pair.
  const edges = useMemo(() => {
    const pairKey = (l: CompanyLink) => [l.from, l.to].sort().join('|');
    const groups = new Map<string, CompanyLink[]>();
    for (const l of canvas.links) groups.set(pairKey(l), [...(groups.get(pairKey(l)) ?? []), l]);
    return canvas.links.map((l) => {
      const g = groups.get(pairKey(l))!;
      return { l, idx: g.indexOf(l), n: g.length };
    });
  }, [canvas.links]);

  const point = (e: React.PointerEvent) => {
    const r = box.current!.getBoundingClientRect();
    return { px: clamp((e.clientX - r.left) / r.width), py: clamp((e.clientY - r.top) / r.height) };
  };
  const onNodeDown = (n: CanvasNode, e: React.PointerEvent) => {
    if (connect) return;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    const p = at(n.code);
    const s = point(e);
    setDrag({ code: n.code, ...p, sx: s.px, sy: s.py, ox: s.px - p.px, oy: s.py - p.py, moved: false });
  };
  const onNodeMove = (n: CanvasNode, e: React.PointerEvent) => {
    if (!drag || drag.code !== n.code) return;
    const p = point(e);
    setDrag((d) => d && { ...d, px: clamp(p.px - d.ox), py: clamp(p.py - d.oy), moved: d.moved || Math.hypot(p.px - d.sx, p.py - d.sy) > 0.012 });
  };
  const onNodeUp = (n: CanvasNode) => {
    const d = drag;
    setDrag(null);
    if (!d || d.code !== n.code) return;
    if (d.moved) act.place.mutate({ code: n.code, x: Number(d.px.toFixed(4)), y: Number(d.py.toFixed(4)) }, { onError: (e) => toast({ tone: 'error', text: errText(e, 'جای شرکت ثبت نشد.') }) });
    else pick(n);
  };
  const pick = (n: CanvasNode) => {
    if (n.kind === 'holding') return;
    if (!connect) { setSheet({ type: 'company', code: n.code }); return; }
    if (!connect.from) { setConnect({ from: n.code }); return; }
    if (connect.from === n.code) { setConnect({ from: null }); return; }
    setSheet({ type: 'new', from: connect.from, to: n.code });
    setConnect(null);
  };
  const onKey = (n: CanvasNode, e: React.KeyboardEvent) => {
    const step = 0.03;
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (d) {
      e.preventDefault();
      const p = at(n.code);
      act.place.mutate({ code: n.code, x: Number(clamp(p.px + d[0]!).toFixed(4)), y: Number(clamp(p.py + d[1]!).toFixed(4)) });
    } else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(n); }
  };

  const nameOf = (code: string) => canvas.nodes.find((n) => n.code === code)?.name_fa ?? code;
  const hint = connect ? (connect.from ? `حالا شرکتی را که با ${nameOf(connect.from)} ارتباط دارد انتخاب کن.` : 'اول شرکتی را انتخاب کن که کار میدهد یا میدهد.') : 'شرکت‌ها را بکش و جابه‌جا کن؛ روی هر ارتباط بزن تا عوضش کنی.';

  return (
    <Card as="section" className="flex flex-col gap-3 p-4" aria-label="بوم شرکت‌ها">
      <SectionTitle title="بوم" note={hint}
        action={<Button size="sm" variant={connect ? 'primary' : 'secondary'} icon="add" aria-pressed={!!connect} onClick={() => setConnect(connect ? null : { from: null })}>{connect ? 'انصراف' : 'ارتباط تازه'}</Button>} />
      <div ref={box} dir="ltr" data-testid="canvas" className="relative aspect-[4/5] w-full touch-none select-none overflow-hidden rounded-[14px] bg-tile sm:aspect-[16/10]">
        <svg className="absolute inset-0 size-full" aria-hidden>
          <defs>
            {KINDS.map((k) => <marker key={k} id={`arrow-${k}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill={KIND_STYLE[k].color} /></marker>)}
          </defs>
          {hub ? companies.map((c) => {
            const a = at(hub.code); const b = at(c.code);
            return <line key={c.code} x1={`${a.px * 100}%`} y1={`${a.py * 100}%`} x2={`${b.px * 100}%`} y2={`${b.py * 100}%`} stroke="var(--hq-line-strong)" strokeWidth={1} strokeDasharray="3 5" />;
          }) : null}
          {edges.map(({ l, idx, n }) => {
            const a = at(l.from); const b = at(l.to);
            const dx = b.px - a.px; const dy = b.py - a.py; const len = Math.hypot(dx, dy) || 1;
            const off = (idx - (n - 1) / 2) * 0.035;
            const ox = (-dy / len) * off; const oy = (dx / len) * off;
            const s = KIND_STYLE[l.kind];
            // Stop short of the nodes so the arrow head is seen.
            const cut = 0.07 / len;
            const x1 = a.px + dx * cut + ox; const y1 = a.py + dy * cut + oy; const x2 = b.px - dx * cut + ox; const y2 = b.py - dy * cut + oy;
            return <line key={l.id} data-link={l.id} data-state={l.state} x1={`${x1 * 100}%`} y1={`${y1 * 100}%`} x2={`${x2 * 100}%`} y2={`${y2 * 100}%`} stroke={s.color} strokeWidth={l.state === 'on' ? 2 : 1.5} strokeDasharray={l.state === 'on' ? s.dash : '1 5'} opacity={l.state === 'on' ? 1 : 0.55} markerEnd={`url(#arrow-${l.kind})`} />;
          })}
        </svg>
        {edges.map(({ l, idx, n }) => {
          const a = at(l.from); const b = at(l.to);
          const dx = b.px - a.px; const dy = b.py - a.py; const len = Math.hypot(dx, dy) || 1;
          const off = (idx - (n - 1) / 2) * 0.035;
          const mx = a.px + dx * 0.3 + (-dy / len) * off; const my = a.py + dy * 0.3 + (dx / len) * off;
          return (
            <button key={l.id} type="button" dir="rtl" onClick={() => setSheet({ type: 'edit', id: l.id })} aria-label={`ارتباط ${nameOf(l.from)} با ${nameOf(l.to)}: ${LINK_KIND[l.kind]}${l.state === 'off' ? '، خاموش' : ''}`}
              style={{ left: `${mx * 100}%`, top: `${my * 100}%`, color: KIND_STYLE[l.kind].color }}
              className={cx('absolute z-10 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-full bg-card px-2 py-0.5 text-[11px] font-semibold ring-1 ring-current hover:bg-hover', l.state === 'off' && 'opacity-60')}>
              {LINK_KIND[l.kind]}{l.state === 'off' ? ' · خاموش' : ''}
            </button>
          );
        })}
        {placed.map((n) => {
          const p = at(n.code);
          const isHub = n.kind === 'holding';
          const from = connect?.from === n.code;
          return (
            <button key={n.code} type="button" dir="rtl" data-node={n.code} aria-label={isHub ? `${n.name_fa}، مرکز` : `شرکت ${n.name_fa}، ${n.open_sessions} جلسه‌ی باز`} aria-pressed={from || undefined}
              style={{ left: `${p.px * 100}%`, top: `${p.py * 100}%` }}
              onPointerDown={(e) => onNodeDown(n, e)} onPointerMove={(e) => onNodeMove(n, e)} onPointerUp={() => onNodeUp(n)} onPointerCancel={() => setDrag(null)}
              onClick={(e) => { if (e.detail === 0) return; if (connect && !isHub) pick(n); }}
              onKeyDown={(e) => onKey(n, e)}
              className={cx('absolute z-20 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1 rounded-[14px] px-2.5 py-2 text-[12px] font-semibold text-ink shadow-sm', isHub ? 'bg-gold-soft ring-2 ring-[var(--hq-gold-ink)]' : 'bg-card ring-1 ring-[var(--hq-line-strong)] hover:bg-hover', from && 'ring-2 ring-[var(--hq-lapis)]', connect && !isHub ? 'cursor-pointer' : 'cursor-grab active:cursor-grabbing')}>
              <span className="text-silver-ink">{isHub ? <Monogram size={22} /> : <CompanyMark code={n.code} height={18} mono />}</span>
              <span className="max-w-[7rem] truncate">{n.name_fa}</span>
              {!isHub && n.open_sessions ? <span className="fig absolute -top-2 -end-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-page px-1 text-[11px] font-bold text-gold-ink shadow-[inset_0_0_0_1px_var(--hq-gold-ink)]">{n.open_sessions}</span> : null}
            </button>
          );
        })}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted" aria-label="راهنمای ارتباط‌ها">
        {KINDS.map((k) => <li key={k} className="inline-flex items-center gap-1.5"><span className="inline-block h-0 w-6 border-t-2" style={{ borderColor: KIND_STYLE[k].color, borderStyle: KIND_STYLE[k].dash ? 'dashed' : 'solid' }} />{LINK_KIND[k]}</li>)}
      </ul>

      {sheet?.type === 'company' ? <CompanyPanel node={canvas.nodes.find((n) => n.code === sheet.code)} canvas={canvas} sessions={sessions} onClose={() => setSheet(null)} onEdit={(id) => setSheet({ type: 'edit', id })} onConnect={() => { setSheet(null); setConnect({ from: sheet.code }); }} /> : null}
      {sheet?.type === 'new' ? <LinkForm key={`${sheet.from}-${sheet.to}`} canvas={canvas} init={{ from: sheet.from, to: sheet.to }} onClose={() => setSheet(null)} /> : null}
      {sheet?.type === 'edit' ? <LinkForm key={sheet.id} canvas={canvas} link={canvas.links.find((l) => l.id === sheet.id)} onClose={() => setSheet(null)} /> : null}
    </Card>
  );
}

function CompanyPanel({ node, canvas, sessions, onClose, onEdit, onConnect }: { node?: CanvasNode; canvas: Canvas; sessions: SessionCard[]; onClose: () => void; onEdit: (id: string) => void; onConnect: () => void }) {
  if (!node) return null;
  const mine = canvas.links.filter((l) => l.from === node.code || l.to === node.code);
  const name = (c: string) => canvas.nodes.find((n) => n.code === c)?.name_fa ?? c;
  const open = sessions.filter((s) => s.holder?.company === node.code);
  return (
    <Sheet open onOpenChange={(v) => { if (!v) onClose(); }} title={node.name_fa} description={node.line_fa} width={440}>
      <div className="flex flex-col gap-5">
        <section className="flex flex-col gap-2" aria-label="جلسه‌های باز">
          <h3 className="text-[13px] font-semibold text-sec">جلسه‌های باز</h3>
          {open.length ? <ul className="flex flex-col">{open.map((s) => <li key={s.ref}><SessionRow s={s} /></li>)}</ul> : <p className="text-[13px] text-muted">جلسه‌ی بازی ندارد.</p>}
        </section>
        <section className="flex flex-col gap-2" aria-label="ارتباط‌ها">
          <h3 className="text-[13px] font-semibold text-sec">ارتباط‌ها</h3>
          {mine.length ? (
            <ul className="flex flex-col gap-1.5">
              {mine.map((l) => (
                <li key={l.id}>
                  <button type="button" onClick={() => onEdit(l.id)} className="flex w-full flex-col gap-0.5 rounded-[10px] bg-tile px-3 py-2 text-start hover:bg-hover">
                    <span className="flex items-center gap-2 text-[13px] font-semibold"><span>{name(l.from)}</span><Icon name="next" size={14} mirror /><span>{name(l.to)}</span><Pill tone={l.state === 'on' ? 'pos' : 'neutral'} dot>{LINK_KIND[l.kind]}{l.state === 'off' ? ' · خاموش' : ''}</Pill></span>
                    <PlainPara text={l.purpose_fa} className="text-[12px] leading-5 text-sec" />
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="text-[13px] text-muted">هنوز با شرکت دیگری ارتباط ندارد؛ همه‌ی شرکت‌ها به هلدینگ وصل‌اند.</p>}
        </section>
        <div className="flex flex-wrap gap-2">
          <Button icon="add" onClick={onConnect}>ارتباط تازه از این شرکت</Button>
          <Link href={`/companies/${encodeURIComponent(node.code)}`} className="inline-flex h-10 items-center rounded-[10px] px-3 text-[14px] font-semibold text-gold-ink hover:bg-hover">صفحه‌ی شرکت</Link>
        </div>
      </div>
    </Sheet>
  );
}

/** A new link (two companies picked) or an existing one (kind, purpose, on/off). */
function LinkForm({ canvas, init, link, onClose }: { canvas: Canvas; init?: { from: string; to: string }; link?: CompanyLink; onClose: () => void }) {
  const toast = useToast();
  const act = useCanvasActions();
  const [kind, setKind] = useState<LinkKind>(link?.kind ?? 'serves');
  const [purpose, setPurpose] = useState(link?.purpose_fa ?? '');
  const from = link?.from ?? init?.from ?? '';
  const to = link?.to ?? init?.to ?? '';
  const name = (c: string) => canvas.nodes.find((n) => n.code === c)?.name_fa ?? c;
  const fail = (e: unknown) => toast({ tone: 'error', text: errText(e, 'ثبت نشد؛ دوباره بزن.') });
  const save = () => {
    if (!purpose.trim()) return;
    if (link) act.patch.mutate({ id: link.id, kind, purpose_fa: purpose.trim() }, { onSuccess: () => { toast({ tone: 'ok', text: 'ارتباط عوض شد.' }); onClose(); }, onError: fail });
    else act.create.mutate({ from, to, kind, purpose_fa: purpose.trim() }, { onSuccess: () => { toast({ tone: 'ok', text: 'ارتباط ساخته شد.' }); onClose(); }, onError: fail });
  };
  return (
    <Sheet open onOpenChange={(v) => { if (!v) onClose(); }} title={link ? 'ارتباط دو شرکت' : 'ارتباط تازه'} description={<><PlainText text={name(from)} /> ← <PlainText text={name(to)} /></>} width={440}
      footer={(
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon="seal" disabled={!purpose.trim()} loading={act.create.isPending || act.patch.isPending} onClick={save}>{link ? 'ذخیره' : 'بساز'}</Button>
          {link ? <Button variant={link.state === 'on' ? 'secondary' : 'primary'} icon={link.state === 'on' ? 'pause' : 'resume'} loading={act.patch.isPending} onClick={() => act.patch.mutate({ id: link.id, state: link.state === 'on' ? 'off' : 'on' }, { onSuccess: onClose, onError: fail })}>{link.state === 'on' ? 'خاموشش کن' : 'روشنش کن'}</Button> : null}
        </div>
      )}>
      <div className="flex flex-col gap-4">
        <fieldset className="flex flex-col gap-2"><legend className="pb-1 text-[12px] text-sec">این ارتباط چه جور است؟</legend>
          <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="جور ارتباط">{KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{LINK_KIND[k]}</FilterChip>)}</div>
        </fieldset>
        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] text-sec">برای چه؟ (یک جمله)</span>
          <textarea value={purpose} onChange={(e) => setPurpose(e.target.value)} rows={3} dir="auto" aria-label="برای چه" placeholder="مثلاً: ریلزهای این شرکت را روی صفحه‌ی آن یکی هم منتشر کند." className={cx(field, 'py-2 leading-6')} />
        </label>
        {link ? <p className="text-[12px] leading-5 text-muted">{link.state === 'on' ? 'روشن است.' : 'خاموش است.'}{link.open_works ? ` ${link.open_works} کار روی همین ارتباط باز است.` : ''} ارتباط پاک نمیشود، فقط خاموش میشود.</p> : null}
      </div>
    </Sheet>
  );
}
