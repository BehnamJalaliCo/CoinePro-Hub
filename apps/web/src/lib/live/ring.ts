// ⟨1.24⟩ HM-1, the holding network map's layout (design/LIVE_VIEWS.md §5 «Scale»): the seal at the centre, every company on a ring from
// data, their servers on the outer ring. Pure: the map draws what this returns; e2e/live-model.spec.ts checks 0, 1, 3 and 40 companies.
//
// Ring capacity = ⌊2πR / (node + gap)⌋ for the width the map has. Up to capacity: full nodes. Beyond: nodes shrink to a legible minimum
// (28 px), the busiest at the top. Beyond again: a second ring opens inside the first, and the least active fold into one «بقیه · n» node
// (it opens a list; the table view always shows every company). Order is by live activity, never alphabetical; equal activity keeps the
// data's order. Nothing assumes a number of companies (owner rule 9).

export type RingItem = { code: string; score: number; servers: Array<{ id: string; state: string }> };
export type RingNode = { code: string; x: number; y: number; r: number; angle: number; ring: 0 | 1 };
export type RingRest = { codes: string[]; x: number; y: number; r: number; angle: number; ring: 0 | 1 };
export type RingServer = { id: string; code: string; x: number; y: number; size: number; angle: number };
export type RingMore = { code: string; n: number; x: number; y: number };
export type RingLayout = {
  width: number; height: number; cx: number; cy: number; hubR: number;
  /** The company ring, the second (inner) ring when it opened, and the server ring. */
  R1: number; R1b: number | null; R2: number;
  nodes: RingNode[]; rest: RingRest | null; servers: RingServer[]; more: RingMore[];
};

export const NODE_MAX = 64;
export const NODE_MIN = 28;
const GAP = 14;
/** Servers drawn per company at most; more fold into «+n». */
export const SERVERS_MAX = 4;
const SERVER_SIZE = 16;

/** How many nodes of diameter [d] fit around a ring of radius [R]. */
export const capacity = (R: number, d: number, gap = GAP) => (R <= 0 ? 0 : Math.floor((2 * Math.PI * R) / (d + gap)));

/** Busiest first; equal activity keeps the data's order (stable). */
export function byActivity(items: RingItem[]): RingItem[] {
  return items.map((x, i) => ({ x, i })).sort((a, b) => b.x.score - a.x.score || a.i - b.i).map((o) => o.x);
}

const offlineFirst = (a: { state: string }, b: { state: string }) => Number(b.state === 'offline') - Number(a.state === 'offline');

/**
 * Lays out [items] (in data order, with their activity) in a box [width] wide. The box is square up to 640 px and keeps its width on a
 * phone; the hub never moves.
 */
export function ringLayout(items: RingItem[], width: number): RingLayout {
  const w = Math.max(280, Math.round(width));
  const side = Math.min(w, 640);
  const height = side;
  const cx = w / 2, cy = height / 2;
  const R2 = side / 2 - 30;
  const R1 = Math.round(R2 * 0.66);
  const hubR = Math.round(Math.min(52, Math.max(26, R1 * 0.3)));
  const sorted = byActivity(items);
  const n = sorted.length;
  const nodes: RingNode[] = [];
  let rest: RingRest | null = null;
  let R1b: number | null = null;

  const place = (list: RingItem[], R: number, ring: 0 | 1, d: number, slots: number, withRest: string[] | null): RingRest | null => {
    list.forEach((it, i) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * i) / slots;
      nodes.push({ code: it.code, x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle), r: d / 2, angle, ring });
    });
    if (!withRest?.length) return null;
    const angle = -Math.PI / 2 + (2 * Math.PI * list.length) / slots;
    return { codes: withRest, x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle), r: d / 2, angle, ring };
  };

  if (n > 0) {
    const fitMax = capacity(R1, NODE_MAX);
    const fitMin = capacity(R1, NODE_MIN);
    if (n <= fitMin) {
      // One ring: as large as the ring allows, never below the legible minimum (one node alone is full size).
      const d = n <= fitMax ? NODE_MAX : Math.max(NODE_MIN, Math.min(NODE_MAX, (2 * Math.PI * R1) / n - GAP));
      place(sorted, R1, 0, d, Math.max(n, 1), null);
    } else {
      const inner = R1 - (NODE_MIN + 22);
      const room = inner - hubR >= NODE_MIN + 10;
      R1b = room ? inner : null;
      const c1 = fitMin;
      const c2 = room ? capacity(inner, NODE_MIN) : 0;
      if (n <= c1 + c2) {
        place(sorted.slice(0, c1), R1, 0, NODE_MIN, c1, null);
        place(sorted.slice(c1), inner, 1, NODE_MIN, n - c1, null);
      } else if (room && c2 > 0) {
        place(sorted.slice(0, c1), R1, 0, NODE_MIN, c1, null);
        rest = place(sorted.slice(c1, c1 + c2 - 1), inner, 1, NODE_MIN, c2, sorted.slice(c1 + c2 - 1).map((x) => x.code));
      } else {
        rest = place(sorted.slice(0, c1 - 1), R1, 0, NODE_MIN, c1, sorted.slice(c1 - 1).map((x) => x.code));
      }
    }
  }

  // Servers: on the outer ring at their company's angle, a few degrees apart; the offline first so a broken one is never folded away.
  const servers: RingServer[] = [];
  const more: RingMore[] = [];
  const slots = Math.max(1, nodes.length + (rest ? 1 : 0));
  const arc = (2 * Math.PI * R2) / slots;
  const perCo = Math.max(1, Math.min(SERVERS_MAX, Math.floor(arc / (SERVER_SIZE + 6))));
  const size = arc < SERVER_SIZE + 4 ? Math.max(10, arc - 4) : SERVER_SIZE;
  const step = Math.min(0.2, (2 * Math.PI) / slots / (perCo + 1));
  const byCode = new Map(items.map((x) => [x.code, x]));
  for (const node of nodes) {
    const list = [...(byCode.get(node.code)?.servers ?? [])].sort(offlineFirst);
    const shown = list.slice(0, perCo);
    shown.forEach((s, j) => {
      const a = node.angle + (shown.length === 1 ? 0 : (j - (shown.length - 1) / 2) * step);
      servers.push({ id: s.id, code: node.code, x: cx + R2 * Math.cos(a), y: cy + R2 * Math.sin(a), size, angle: a });
    });
    if (list.length > shown.length) {
      const a = node.angle + ((shown.length + 1) / 2) * step;
      more.push({ code: node.code, n: list.length - shown.length, x: cx + (R2 + 18) * Math.cos(a), y: cy + (R2 + 18) * Math.sin(a) });
    }
  }
  return { width: w, height, cx, cy, hubR, R1, R1b, R2, nodes, rest, servers, more };
}

/** The point on the map's edge straight out from [x, y] (a publish to the world leaves this way). */
export function outward(l: RingLayout, x: number, y: number): { x: number; y: number } {
  const dx = x - l.cx, dy = y - l.cy;
  const L = Math.hypot(dx, dy) || 1;
  const R = Math.min(l.width / 2, l.height / 2) - 6;
  return { x: l.cx + (dx / L) * R, y: l.cy + (dy / L) * R };
}
