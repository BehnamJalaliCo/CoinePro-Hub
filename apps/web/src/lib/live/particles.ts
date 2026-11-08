// ⟨1.24⟩ K-1, M4 «ذره» and the motion the map draws itself (design/LIVE_VIEWS.md §2, rules 4, 7, 8, 10). One particle layer per screen:
// one SVG group, driven by one requestAnimationFrame that runs only while something is in flight. Each particle is one event crossing one
// edge (a 4 px dot and two trail dots); at most three fly per edge, the rest fold into a «×n» chip on the edge; at most 24 things animate
// on the screen at once, beyond that they fold the same way. A hidden tab draws nothing (what is in flight is dropped, nothing new starts).
// Under reduced motion a particle is a 1.5 s tint on its edge plus the chip. Framework-free: the map hands it its groups.

export type Pt = { x: number; y: number };
export type MotionColor = 'gold' | 'silver' | 'lapis';

const SVG = 'http://www.w3.org/2000/svg';
export const MAX_PER_EDGE = 3;
export const MAX_ANIMATING = 24;
const TRAVEL_MS = 900;
const TINT_MS = 1500;
const CHIP_MS = 1800;

/** cubic-bezier(x1, y1, x2, y2) as a function of progress (Newton's method, as the browser does). */
export function bezier(x1: number, y1: number, x2: number, y2: number) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx, cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const sx = (t: number) => ((ax * t + bx) * t + cx) * t;
  const sy = (t: number) => ((ay * t + by) * t + cy) * t;
  const dx = (t: number) => (3 * ax * t + 2 * bx) * t + cx;
  return (x: number) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i++) { const d = dx(t); if (Math.abs(d) < 1e-6) break; t -= (sx(t) - x) / d; }
    return sy(Math.min(1, Math.max(0, t)));
  };
}
export const EASE_STANDARD = bezier(0.2, 0, 0, 1);
export const EASE_CEREMONY = bezier(0.3, 0, 0.1, 1);
const EASE_THROUGH = bezier(0.4, 0, 0.2, 1);

/** The point a fraction [f] along the polyline [pts]. */
export function along(pts: Pt[], f: number): Pt {
  if (pts.length < 2) return pts[0] ?? { x: 0, y: 0 };
  const seg: number[] = [];
  let total = 0;
  for (let i = 1; i < pts.length; i++) { const l = Math.hypot(pts[i]!.x - pts[i - 1]!.x, pts[i]!.y - pts[i - 1]!.y); seg.push(l); total += l; }
  let d = Math.min(1, Math.max(0, f)) * total;
  for (let i = 0; i < seg.length; i++) {
    if (d <= seg[i]! || i === seg.length - 1) {
      const t = seg[i] ? Math.min(1, d / seg[i]!) : 1;
      return { x: pts[i]!.x + (pts[i + 1]!.x - pts[i]!.x) * t, y: pts[i]!.y + (pts[i + 1]!.y - pts[i]!.y) * t };
    }
    d -= seg[i]!;
  }
  return pts[pts.length - 1]!;
}

type Anim = { t0: number; ms: number; ease: (x: number) => number; step: (e: number) => void; done: () => void; cancel: () => void };
type Chip = { g: SVGGElement; text: SVGTextElement; n: number; timer: ReturnType<typeof setTimeout> };

export type LayerOpts = {
  /** Reduced motion right now (rule 8). */
  reduced: () => boolean;
  /** Edge elements to tint while a particle crosses them (or instead of it). */
  edges?: (edge: string) => Array<Element | null | undefined>;
};

/**
 * The screen's one particle layer. [parts] is the group particles and rings are drawn in; [chips] the group the «×n» chips sit in (above
 * the nodes). Everything it draws is removed when it is done; [clear] drops all of it at once (the tab hid).
 */
export class ParticleLayer {
  private anims = new Set<Anim>();
  private raf = 0;
  private inflight = new Map<string, number>();
  private chips = new Map<string, Chip>();
  private tints = new Map<Element, ReturnType<typeof setTimeout>>();
  private timers = new Set<ReturnType<typeof setTimeout>>();
  private dead = false;

  constructor(private parts: SVGGElement, private chipsG: SVGGElement, private opts: LayerOpts) {}

  /** Things animating now (particles and rings); never more than [MAX_ANIMATING]. */
  get animating() { return this.anims.size; }
  inFlight(edge: string) { return this.inflight.get(edge) ?? 0; }
  chipCount(edge: string) { return this.chips.get(edge)?.n ?? 0; }

  private hidden() { return typeof document !== 'undefined' && document.hidden; }

  private kick() {
    if (!this.raf && !this.dead && !this.hidden() && this.anims.size) this.raf = requestAnimationFrame(this.frame);
  }
  private frame = (t: number) => {
    this.raf = 0;
    for (const a of [...this.anims]) {
      const p = Math.min(1, (t - a.t0) / a.ms);
      a.step(a.ease(p));
      if (p >= 1) { this.anims.delete(a); a.done(); }
    }
    this.kick();
  };
  private run(ms: number, ease: (x: number) => number, step: (e: number) => void, done: () => void, cancel: () => void = done) {
    const a: Anim = { t0: performance.now(), ms, ease, step, done, cancel };
    this.anims.add(a);
    this.kick();
  }
  private later(ms: number, f: () => void) {
    const t = setTimeout(() => { this.timers.delete(t); f(); }, ms);
    this.timers.add(t);
  }

  /** Tints the elements of [edge] in [color] for [ms] (the particle's company under reduced motion, its highlight otherwise). */
  tint(edge: string, color: MotionColor, ms = TINT_MS) {
    for (const el of this.opts.edges?.(edge) ?? []) {
      if (!el) continue;
      el.setAttribute('data-tint', color);
      clearTimeout(this.tints.get(el));
      this.tints.set(el, setTimeout(() => { el.removeAttribute('data-tint'); this.tints.delete(el); }, ms));
    }
  }

  /** Counts one more event on [edge] in its chip, at the middle of [pts]. */
  private chip(edge: string, pts: Pt[], add = 1) {
    let c = this.chips.get(edge);
    if (!c) {
      const g = document.createElementNS(SVG, 'g');
      g.setAttribute('class', 'hq-live-chip');
      g.setAttribute('data-chip', edge);
      const r = document.createElementNS(SVG, 'rect');
      r.setAttribute('x', '-15'); r.setAttribute('y', '-9'); r.setAttribute('width', '30'); r.setAttribute('height', '18'); r.setAttribute('rx', '9');
      r.setAttribute('fill', 'var(--hq-surface-raised)'); r.setAttribute('stroke', 'var(--hq-line-strong)');
      const text = document.createElementNS(SVG, 'text');
      text.setAttribute('y', '4'); text.setAttribute('text-anchor', 'middle'); text.setAttribute('font-size', '11'); text.setAttribute('fill', 'var(--hq-text-primary)');
      text.setAttribute('class', 'fig');
      g.append(r, text);
      this.chipsG.append(g);
      c = { g, text, n: this.inFlight(edge), timer: setTimeout(() => {}, 0) };
      this.chips.set(edge, c);
    }
    c.n += add;
    c.text.textContent = `×${c.n}`;
    const mid = along(pts, 0.5);
    c.g.setAttribute('transform', `translate(${mid.x.toFixed(1)} ${(mid.y - 12).toFixed(1)})`);
    clearTimeout(c.timer);
    const cc = c;
    c.timer = setTimeout(() => { cc.g.remove(); this.chips.delete(edge); }, CHIP_MS);
  }

  /**
   * One event crossing [edge] along [pts] (two points for one edge, three when it goes through the hub). Returns what happened: it flew,
   * it folded into the chip (the edge or the screen was full, or reduced motion), or nothing (the tab is hidden).
   */
  emit(edge: string, pts: Pt[], color: MotionColor, o: { delay?: number; onMid?: () => void } = {}): 'flying' | 'folded' | 'skipped' {
    if (this.dead || this.hidden() || pts.length < 2) return 'skipped';
    if (this.opts.reduced()) { this.tint(edge, color); this.chip(edge, pts); return 'folded'; }
    if (this.inFlight(edge) >= MAX_PER_EDGE || this.anims.size >= MAX_ANIMATING) { this.chip(edge, pts); return 'folded'; }
    this.inflight.set(edge, this.inFlight(edge) + 1);
    const start = () => {
      if (this.dead || this.hidden()) { this.inflight.set(edge, Math.max(0, this.inFlight(edge) - 1)); return; }
      this.tint(edge, color, 1100);
      const make = (r: number, op: number) => {
        const c = document.createElementNS(SVG, 'circle');
        c.setAttribute('r', String(r)); c.setAttribute('opacity', String(op)); c.setAttribute('fill', `var(--hq-${color === 'gold' ? 'gold-ink' : color === 'silver' ? 'silver-ink' : 'lapis'})`);
        c.setAttribute('data-particle', color);
        this.parts.append(c);
        return c;
      };
      const t2 = make(1.6, 0.3), t1 = make(2.4, 0.55), p = make(3.8, 1);
      const legs = pts.length - 1;
      let midDone = false;
      const place = (c: SVGCircleElement, at: Pt) => { c.setAttribute('cx', at.x.toFixed(1)); c.setAttribute('cy', at.y.toFixed(1)); };
      const end = () => { p.remove(); t1.remove(); t2.remove(); this.inflight.set(edge, Math.max(0, this.inFlight(edge) - 1)); };
      this.run(legs > 1 ? TRAVEL_MS + 300 : TRAVEL_MS, legs > 1 ? EASE_THROUGH : EASE_STANDARD, (e) => {
        place(p, along(pts, e)); place(t1, along(pts, Math.max(0, e - 0.035))); place(t2, along(pts, Math.max(0, e - 0.07)));
        if (legs > 1 && !midDone && e >= 0.5) { midDone = true; o.onMid?.(); }
      }, end);
    };
    if (o.delay) this.later(o.delay, start); else start();
    return 'flying';
  }

  /** One ring that grows from [r0] to [r0 × to] and fades (M3 ripple; M10 when [ceremony]). */
  ring(at: Pt, r0: number, stroke: string, o: { ceremony?: boolean } = {}) {
    if (this.dead || this.hidden() || this.opts.reduced() || this.anims.size >= MAX_ANIMATING) return;
    const c = document.createElementNS(SVG, 'circle');
    c.setAttribute('cx', at.x.toFixed(1)); c.setAttribute('cy', at.y.toFixed(1)); c.setAttribute('r', String(r0));
    c.setAttribute('fill', 'none'); c.setAttribute('stroke', stroke); c.setAttribute('stroke-width', '2');
    c.setAttribute('data-ring', o.ceremony ? 'ceremony' : 'ripple');
    this.parts.append(c);
    const grow = o.ceremony ? 0.9 : 0.5;
    const from = o.ceremony ? 0.75 : 0.55;
    this.run(o.ceremony ? 480 : 600, o.ceremony ? EASE_CEREMONY : EASE_STANDARD, (e) => {
      c.setAttribute('r', (r0 * (1 + grow * e)).toFixed(1));
      c.setAttribute('opacity', (from * (1 - e)).toFixed(3));
    }, () => c.remove());
  }

  /** Drops everything in flight (the tab hid, or the layout changed under it). */
  clear() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
    for (const a of this.anims) a.cancel();
    this.anims.clear();
    this.inflight.clear();
    for (const t of this.timers) clearTimeout(t);
    this.timers.clear();
    for (const c of this.chips.values()) { clearTimeout(c.timer); c.g.remove(); }
    this.chips.clear();
  }

  destroy() {
    this.clear();
    for (const [el, t] of this.tints) { clearTimeout(t); el.removeAttribute('data-tint'); }
    this.tints.clear();
    this.dead = true;
  }
}
