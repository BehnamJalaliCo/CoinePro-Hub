/* Zarib100x — THE DESK: the brand's motion library (Canvas 2D, every frame a pure function of t).
 * Loaded by COMMON/motion/desk_engine.py into the day's page, before the session's motion/scene.js.
 * Read COMMON/DIRECTION.md §3–§5 and COMMON/motion/README.md first. Nothing here may be restyled per
 * reel: colours, fonts, the HUD, the lockup, the captions and the transitions ARE the brand. A reel
 * adds its own shots (plates, panels, charts, numbers) on top, in scene.js.
 *
 * The scene contract (scene.js):
 *   const SHOTS = [{a: 0, b: 2.6, tr: 'blade', draw: (t, p, s) => { ... }}, ...];  // a..b seconds
 *   const CAPS  = DESK.capsFromWords(DATA.lines, {keys: ['فیوچرز', ...]});     // or your own list
 *   DESK.reel({shots: SHOTS, caps: CAPS, hud: {brief: 41, pair: 'SOL/USDT', time: '14:00'},
 *              tape: [...], end: {word: 'الماس', at: 61.2}, END: 64.0});
 * `p` = 0..1 through the shot; `s` = the shot. A shot's `tr` is the transition INTO it
 * ('blade' | 'slats' | 'aperture' | 'slide' | 'cut'), 0.42 s centred on its start.
 */
"use strict";
const W = 1080, H = 1920;
const Z = {   // Zarib100x — the colours of the page's profile photo (brand/README.md, 2026-11-26)
  gr: '#160A0E', pn: '#241016', pn2: '#2F1620',            // wine-black ground, glass panels, raised
  ac: '#83CAAD', acD: '#5FAF90',                            // Zarib Mint (the profile's backdrop): brand accent, its shade
  ox: '#461A23', oxL: '#6B2A37',                            // Oxblood (the suit): brand light and fills
  tx: '#F4EFE6', mu: '#A8979B', hair: 'rgba(244,239,230,0.13)',
  up: '#35E06E', dn: '#FF4D57', flat: '#A8979B',            // meaning: ALWAYS with ▲ / ▼ (never colour alone); never mint
};
const C = document.getElementById('c'), X = C.getContext('2d', {alpha: false});
X.imageSmoothingQuality = 'high';
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const lerp = (a, b, p) => a + (b - a) * p;
const P = (t, t0, d) => clamp((t - t0) / d);
const E = {
  o3: p => 1 - Math.pow(1 - p, 3), o5: p => 1 - Math.pow(1 - p, 5),
  io3: p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2,
  oexpo: p => p >= 1 ? 1 : 1 - Math.pow(2, -10 * p),
  // a dock: arrives fast, settles with a 2 % overshoot (instruments snap, they never bounce)
  dock: p => { p = clamp(p); const c1 = 1.25, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); },
};
function rgba(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${clamp(a).toFixed(3)})`; }

/* ---------------------------------------------------------------- type ---- */
// families registered by the engine: ZF<weight> = IRANYekanX Pro (Persian text; digits made Persian by iso()),
// ZM<weight> = IBM Plex Mono (data, tickers, the HUD), ZC<weight> = IBM Plex Sans Condensed (big Latin numbers, the wordmark)
const FA_DIG = '۰۱۲۳۴۵۶۷۸۹';
// ⟨2026-11-27⟩ decimals «/» (fa-type: the one decimal mark every page's font draws the same)
const fa = v => String(v).replace(/[0-9]/g, d => FA_DIG[d]).replace(/\./g, '/').replace(/,/g, '٬').replace(/%/g, '٪');
// Digits and Latin runs inside RTL text (the font is IRANYekanX Pro with Latin digits; nothing is left to a
// FaNum font): a run WITH a Latin letter or $ (Zarib100x, SOL/USDT, 50 USDT, $70.48, GPT-5) stays Latin and is
// isolated LTR (LRI … PDI), so it never scrambles; a run of digits ALONE becomes Persian digits (۱۳۳، ۶۱٪، ۲/۱).
// Never Persian and Latin digits inside one run. Every DESK text call does this.
const LRI = '\u2066', PDI = '\u2069';
const iso = s => String(s).replace(/[A-Za-z0-9$][A-Za-z0-9$%.,/:+\-×#@_ ]*[A-Za-z0-9%$x]|[A-Za-z0-9$]/g,
  m => /[A-Za-z$]/.test(m) ? LRI + m + PDI : fa(m));
const endStop = s => String(s).replace(/[.،؛:]+\s*$/u, '');   // never a full stop at the end on screen
const WEIGHTS = {F: [200, 300, 400, 500, 600, 700, 800, 900, 950], M: [400, 500, 600], C: [600, 700]};
function font(kind, w, px) {   // the nearest weight the engine loaded (an unloaded name would fall back to a system face)
  const ws = WEIGHTS[kind] || WEIGHTS.F; let best = ws[0];
  ws.forEach(v => { if (Math.abs(v - w) < Math.abs(best - w)) best = v; });
  return `${px}px Z${kind}${best}`;
}
/** Draw text. o: {px, w (100..950), kind ('F' Persian | 'M' mono | 'C' condensed),
 *  col, align ('right' default for RTL | 'left' | 'center'), rtl (default true unless kind M/C), a (alpha),
 *  track (letter-spacing px, mono/condensed only), maxW (shrinks to fit)} → width drawn */
function txt(s, x, y, o = {}) {
  const kind = o.kind || 'F', ltr = o.rtl === false || kind === 'M' || kind === 'C';
  let str = endStop(s);
  if (!ltr) str = iso(str);
  let px = o.px || 48;
  X.save();
  X.direction = ltr ? 'ltr' : 'rtl';
  X.textAlign = o.align || (ltr ? 'left' : 'right');
  X.textBaseline = o.base || 'alphabetic';
  if (o.track && 'letterSpacing' in X) X.letterSpacing = `${o.track}px`;
  X.font = font(kind, o.w || 700, px);
  if (o.maxW) { const m = X.measureText(str).width; if (m > o.maxW) { px *= o.maxW / m; X.font = font(kind, o.w || 700, px); } }
  X.globalAlpha *= (o.a === undefined ? 1 : o.a);
  X.fillStyle = o.col || Z.tx;
  X.fillText(str, x, y);
  const wd = X.measureText(str).width;
  X.restore();
  return wd;
}
function measure(s, o = {}) {
  const kind = o.kind || 'F', ltr = o.rtl === false || kind === 'M' || kind === 'C';
  X.save(); X.direction = ltr ? 'ltr' : 'rtl'; if (o.track && 'letterSpacing' in X) X.letterSpacing = `${o.track}px`;
  X.font = font(kind, o.w || 700, o.px || 48);
  const w = X.measureText(ltr ? endStop(s) : iso(endStop(s))).width; X.restore(); return w;
}
const TEXTS = new Set();   // every on-screen string, for tools/textlint.py (window.DESK_TEXTS)

/* ------------------------------------------------------------ the world ---- */
let NOISE = null;
function makeNoise() {   // an invisible ±1-level dither tile: gradients never band after Instagram's 8-bit re-encode
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), d = g.createImageData(256, 256);
  let s = 1234567;
  for (let i = 0; i < d.data.length; i += 4) { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; const v = s >>> 24; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
  g.putImageData(d, 0, 0); NOISE = c;
}
/** The desk: wine-black, one soft oxblood key light, a hairline floor grid in perspective (the trading floor). */
function ground(t, o = {}) {
  X.fillStyle = Z.gr; X.fillRect(0, 0, W, H);
  const lx = o.lx === undefined ? 760 : o.lx, ly = o.ly === undefined ? 520 : o.ly;
  const g = X.createRadialGradient(lx, ly, 0, lx, ly, o.lr || 1100);
  g.addColorStop(0, rgba(Z.oxL, o.light === undefined ? 0.55 : o.light * 2.6)); g.addColorStop(0.45, rgba(Z.ox, 0.22)); g.addColorStop(1, rgba(Z.gr, 0));
  X.fillStyle = g; X.fillRect(0, 0, W, H);
  if (o.grid !== false) floorGrid(t, o.horizon || 1180, o.gridA || 0.16, o.speed || 0.35);
}
function floorGrid(t, hy, a, speed) {
  X.save(); X.lineWidth = 1.5;
  const vx = W / 2;
  for (let i = -14; i <= 14; i++) {           // rays to the vanishing point
    const x2 = vx + i * 150;
    X.strokeStyle = rgba(Z.tx, a * 0.55);
    X.beginPath(); X.moveTo(vx + i * 8, hy); X.lineTo(x2 + i * 120, H); X.stroke();
  }
  const off = (t * speed) % 1;
  for (let k = 0; k < 14; k++) {              // receding rows, moving toward the camera
    const z = (k + 1 - off) / 14, y = hy + (H - hy) * z * z;
    X.strokeStyle = rgba(Z.tx, a * z); X.beginPath(); X.moveTo(0, y); X.lineTo(W, y); X.stroke();
  }
  const g = X.createLinearGradient(0, hy - 40, 0, hy + 120);   // the horizon glows oxblood
  g.addColorStop(0, rgba(Z.oxL, 0)); g.addColorStop(0.5, rgba(Z.oxL, 0.45)); g.addColorStop(1, rgba(Z.oxL, 0));
  X.fillStyle = g; X.fillRect(0, hy - 40, W, 160);
  X.restore();
}
function dither() { if (!NOISE) makeNoise(); X.save(); X.globalAlpha = 0.018; X.globalCompositeOperation = 'overlay'; X.fillStyle = X.createPattern(NOISE, 'repeat'); X.fillRect(0, 0, W, H); X.restore(); }

/* -------------------------------------------------------------- pictures ---- */
const IMG = {};   // the engine preloads every assets/ picture: IMG['assets/plate1.jpg']
/** A photoreal plate, cover-fit, a slow camera move on it (push / pan), the brand grade over it.
 *  o: {x,y,w,h, push: [s0,s1], pan: [[x0,y0],[x1,y1]] (fractions of the spare room), p (0..1), grade (0..1), rim} */
function plate(src, o = {}) {
  const im = IMG[src]; if (!im) return;
  const x = o.x || 0, y = o.y || 0, w = o.w || W, h = o.h || H, p = o.p === undefined ? 0 : o.p;
  const s = lerp((o.push || [1.04, 1.12])[0], (o.push || [1.04, 1.12])[1], E.io3(p));
  const k = Math.max(w / im.width, h / im.height) * s;
  const dw = im.width * k, dh = im.height * k;
  const pan = o.pan || [[0.5, 0.5], [0.5, 0.5]];
  const fx = lerp(pan[0][0], pan[1][0], E.io3(p)), fy = lerp(pan[0][1], pan[1][1], E.io3(p));
  X.save(); X.beginPath(); X.rect(x, y, w, h); X.clip();
  X.drawImage(im, x - (dw - w) * fx, y - (dh - h) * fy, dw, dh);
  const gr = o.grade === undefined ? 0.55 : o.grade;     // the grade: wine-black from below, oxblood from the key side
  let g = X.createLinearGradient(0, y + h * 0.35, 0, y + h); g.addColorStop(0, rgba(Z.gr, 0)); g.addColorStop(1, rgba(Z.gr, 0.92 * gr + 0.05));
  X.fillStyle = g; X.fillRect(x, y, w, h);
  g = X.createLinearGradient(x + w, y, x, y + h * 0.6); g.addColorStop(0, rgba(Z.oxL, 0.45 * gr)); g.addColorStop(1, rgba(Z.ox, 0));
  X.globalCompositeOperation = 'soft-light'; X.fillStyle = g; X.fillRect(x, y, w, h);
  X.restore();
}
/** A cut-out (RGBA) on its own plane: drifts at its own rate (parallax), a faint mint rim on its key side. */
function cutout(src, cx, cy, hgt, o = {}) {
  const im = IMG[src]; if (!im) return;
  const k = hgt / im.height, w = im.width * k;
  X.save(); X.globalAlpha *= (o.a === undefined ? 1 : o.a);
  if (o.rim !== false) { X.shadowColor = rgba(Z.ac, 0.35); X.shadowBlur = 30; }
  X.drawImage(im, cx - w / 2, cy - hgt / 2, w, hgt); X.restore();
}

/* -------------------------------------------------------- 3D-feel panels ---- */
const OFF = {};
function offscreen(key, w, h) { let c = OFF[key]; if (!c || c.width !== w || c.height !== h) { c = document.createElement('canvas'); c.width = w; c.height = h; OFF[key] = c; } const g = c.getContext('2d'); g.clearRect(0, 0, w, h); return [c, g]; }
/** Draw `fn(g, w, h)` into an offscreen card and project it with perspective (rotY / rotX in degrees,
 *  rendered in 2 px strips, crisp). Panels on the wall turn toward the camera as they dock. */
function persp(key, w, h, cx, cy, o, fn) {
  const [c, g] = offscreen(key, w, h); fn(g, w, h);
  const ry = (o.ry || 0) * Math.PI / 180, rx = (o.rx || 0) * Math.PI / 180, f = 1600, sc = o.s || 1;
  X.save(); X.globalAlpha *= (o.a === undefined ? 1 : o.a);
  if (Math.abs(ry) >= Math.abs(rx)) {
    const st = 2;
    for (let u = 0; u < w; u += st) {
      const xl = (u - w / 2) * sc, z = xl * Math.sin(ry), q = f / (f + z);
      const xs = cx + xl * Math.cos(ry) * q, hh = h * sc * q;
      X.drawImage(c, u, 0, st, h, xs, cy - hh / 2, st * sc * Math.cos(ry) * q + 0.6, hh);
    }
  } else {
    const st = 2;
    for (let v = 0; v < h; v += st) {
      const yl = (v - h / 2) * sc, z = yl * Math.sin(rx), q = f / (f + z);
      const ys = cy + yl * Math.cos(rx) * q, ww = w * sc * q;
      X.drawImage(c, 0, v, w, st, cx - ww / 2, ys, ww, st * sc * Math.cos(rx) * q + 0.6);
    }
  }
  X.restore();
}
/** The glass panel (in an offscreen g or on X): wine glass, a hairline, the mint top edge, a mono tab. */
function panelBody(g, w, h, o = {}) {
  const r = 26;
  g.save();
  g.beginPath(); g.roundRect(1, 1, w - 2, h - 2, r);
  g.fillStyle = rgba(Z.pn, o.glass === undefined ? 0.9 : o.glass); g.fill();
  g.lineWidth = 2; g.strokeStyle = Z.hair; g.stroke();
  g.beginPath(); g.roundRect(1, 1, w - 2, h - 2, r); g.clip();
  const gl = g.createLinearGradient(0, 0, 0, h * 0.5); gl.addColorStop(0, 'rgba(255,255,255,0.06)'); gl.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gl; g.fillRect(0, 0, w, h * 0.5);
  g.fillStyle = o.edge || Z.ac; g.fillRect(0, 0, w, 4);
  g.restore();
  if (o.tab) {   // the mono tab, top-left (LTR): «01 · PRICE»
    g.save(); g.font = font('M', 500, 26); g.direction = 'ltr'; g.textAlign = 'left'; g.fillStyle = Z.mu;
    if ('letterSpacing' in g) g.letterSpacing = '3px';
    g.fillText(String(o.tab).toUpperCase(), 32, 58); g.restore();
  }
  if (o.title) {   // a Persian panel title, top-right
    g.save(); g.font = font('F', 800, 38); g.direction = 'rtl'; g.textAlign = 'right'; g.fillStyle = Z.tx;
    g.fillText(iso(endStop(o.title)), w - 32, 62); g.restore(); TEXTS.add(o.title);
  }
}
/** A panel that docks: from below and turned, to its place, 0.5 s. o: {t0, from:'below'|'right'|'left', ry, tab, title} */
function panel(key, t, x, y, w, h, o, fn) {
  const p = E.dock(P(t, o.t0 || 0, 0.55)), a = E.o3(P(t, o.t0 || 0, 0.25));
  if (a <= 0) return;
  const dx = o.from === 'right' ? 160 : o.from === 'left' ? -160 : 0, dy = o.from === 'below' || !o.from ? 120 : 0;
  const ry = lerp(o.from === 'left' ? 24 : -24, o.ry || 0, p), s = lerp(0.94, 1, p);
  persp(key, w, h, x + w / 2 + dx * (1 - p), y + h / 2 + dy * (1 - p), {ry, s, a}, (g, ww, hh) => { panelBody(g, ww, hh, o); if (fn) fn(g, ww, hh); });
}

/* ----------------------------------------------------------- the numbers ---- */
/** ⟨2026-11-27⟩ ▲ ▼ ■ are in NONE of the page's fonts (fa-type/tools/coverage.py: AnjomanMax, Ravagh, IBM Plex
 *  Mono/Condensed, IRANYekanX all lack them), so as text they were drawn by a system font: drawn as shapes. */
function tri(g, x, yBase, px, kind, col) {   // x = left edge, yBase = the text's baseline, px = the text's size
  const s = px * 0.62, top = yBase - px * 0.72, h = s * 0.87;
  g.save(); g.fillStyle = col; g.beginPath();
  if (kind === 'up') { g.moveTo(x, top + h); g.lineTo(x + s, top + h); g.lineTo(x + s / 2, top); }
  else if (kind === 'down') { g.moveTo(x, top); g.lineTo(x + s, top); g.lineTo(x + s / 2, top + h); }
  else { g.rect(x + s * 0.12, top + h * 0.1, s * 0.76, s * 0.76); }
  g.closePath(); g.fill(); g.restore();
  return s;
}
/** The odometer: every digit rolls and lands EXACTLY on the value at t0+dur (hold it ≥ 1.2 s after).
 *  o: {px, w, kind ('C' Latin condensed | 'F' Persian), col, align, prefix, suffix, dec, sep, change}
 *  change: true for a % change or any up/down value — it gets ▲/▼, the sign and the meaning colour itself. */
function odometer(t, value, x, y, t0, dur, o = {}) {
  const p = E.o5(P(t, t0, dur)), dec = o.dec || 0;
  const v = value * p, str0 = Math.abs(value).toFixed(dec), cur = Math.abs(v).toFixed(dec).padStart(str0.length, '0');
  let s = cur;
  if (o.sep !== false) { const [i, d] = s.split('.'); s = i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (d ? '.' + d : ''); }
  s = (value < 0 ? '−' : (o.plus && value > 0 ? '+' : '')) + (o.prefix || '') + s + (o.suffix || '');
  const kind = o.kind || 'C', px = o.px || 160;
  if (kind === 'F') s = fa(s);
  if (o.change) {   // the glyph at half size, left of the number, both in the meaning colour
    if (value > 0 && !o.plus) s = '+' + s;
    const col = value >= 0 ? Z.up : Z.dn, gpx = px * 0.5, gap = px * 0.22;
    const nw = measure(s, {kind, w: o.w || 700, px}), gw = gpx * 0.62;
    const al = o.align || 'center', total = nw + gap + gw;
    const left = al === 'center' ? x - total / 2 : al === 'right' ? x - total : x;
    X.save(); X.globalAlpha *= E.o3(P(t, t0, 0.3)); tri(X, left, y - px * 0.12, gpx, value >= 0 ? 'up' : 'down', col); X.restore();
    return txt(s, left + gw + gap, y, {px, w: o.w || 700, kind, col, align: 'left', rtl: false, track: o.track}) + gw + gap;
  }
  return txt(s, x, y, {px, w: o.w || 700, kind, col: o.col || Z.tx, align: o.align || 'center', rtl: kind === 'F' ? true : false, track: o.track});
}
/** A meaning chip: «+12.4%» green / «−3.1%» red, mono, with a triangle. */
function changeChip(t, pct, x, y, t0, o = {}) {
  const a = E.o3(P(t, t0, 0.3)); if (a <= 0) return;
  const up = pct > 0, col = pct === 0 ? Z.flat : up ? Z.up : Z.dn, px = o.px || 40;
  const s = `${up ? '+' : pct < 0 ? '−' : ''}${Math.abs(pct).toFixed(o.dec === undefined ? 1 : o.dec)}%`;
  const tw = px * 0.62 + px * 0.35;   // the triangle (a shape: no font has it) and its gap
  const w = tw + measure(s, {kind: 'M', w: 600, px}) + px * 1.1, h = px * 1.7;
  const x0 = o.align === 'right' ? x - w : o.align === 'center' ? x - w / 2 : x;
  X.save(); X.globalAlpha *= a;
  X.beginPath(); X.roundRect(x0, y - h / 2, w, h, h / 2); X.fillStyle = rgba(col, 0.16); X.fill(); X.lineWidth = 2; X.strokeStyle = rgba(col, 0.8); X.stroke();
  tri(X, x0 + px * 0.55, y + px * 0.36, px, up ? 'up' : pct < 0 ? 'down' : 'flat', col);
  X.restore();
  txt(s, x0 + px * 0.55 + tw, y + px * 0.36, {kind: 'M', w: 600, px, col, a});
}

/* -------------------------------------------------------------- the charts ---- */
/** A real price series (numbers from qc/facts.json), drawn progressively in t0..t0+dur, the oxblood
 *  cursor riding its head, the last price in a chip. Line: ivory; area: a faint ivory; the change
 *  over the series colours only the end chip (meaning). o: {g (target ctx, default X), levels:[{v,label}], fmt} */
function lineChart(t, series, x, y, w, h, t0, dur, o = {}) {
  const g = o.g || X, n = series.length; if (n < 2) return;
  const lo = Math.min(...series), hi = Math.max(...series), pad = (hi - lo) * 0.08 || 1;
  const Y = v => y + h - (v - lo + pad) / (hi - lo + 2 * pad) * h, Xx = i => x + i / (n - 1) * w;
  const p = E.io3(P(t, t0, dur)), m = Math.max(1, p * (n - 1));
  g.save();
  g.strokeStyle = Z.hair; g.lineWidth = 1.5;           // 4 hairline rows
  for (let k = 0; k <= 4; k++) { const yy = y + h * k / 4; g.beginPath(); g.moveTo(x, yy); g.lineTo(x + w, yy); g.stroke(); }
  // smooth: a centred moving average of o.smooth points (default 3) for the drawn line only — the
  // numbers you SHOW (price, change) come from the facts, never from the smoothed line
  const sm = o.smooth === undefined ? 3 : o.smooth;
  if (sm > 1) { const r = Math.floor(sm / 2); series = series.map((_, i) => { let a = 0, c = 0; for (let j = Math.max(0, i - r); j <= Math.min(n - 1, i + r); j++) { a += series[j]; c++; } return a / c; }); }
  const path = () => { g.beginPath(); g.moveTo(Xx(0), Y(series[0])); for (let i = 1; i <= Math.floor(m); i++) g.lineTo(Xx(i), Y(series[i])); const f = m - Math.floor(m), i0 = Math.floor(m); if (i0 < n - 1) g.lineTo(lerp(Xx(i0), Xx(i0 + 1), f), lerp(Y(series[i0]), Y(series[i0 + 1]), f)); };
  path(); const hx = Math.min(x + w, Xx(m)), hy = (() => { const i0 = Math.min(n - 2, Math.floor(m)), f = m - i0; return lerp(Y(series[i0]), Y(series[i0 + 1]), f); })();
  g.lineTo(hx, y + h); g.lineTo(x, y + h); g.closePath();
  const ag = g.createLinearGradient(0, y, 0, y + h); ag.addColorStop(0, rgba(Z.tx, 0.14)); ag.addColorStop(1, rgba(Z.tx, 0)); g.fillStyle = ag; g.fill();
  path(); g.strokeStyle = Z.tx; g.lineWidth = 5; g.lineJoin = 'round'; g.lineCap = 'round'; g.stroke();
  (o.levels || []).forEach(L => {                       // the Zarib Line on a level: mint, dashed (a level, never a value), labelled
    const ly = Y(L.v); g.setLineDash([14, 10]); g.strokeStyle = rgba(Z.ac, 0.95); g.lineWidth = 3;
    g.beginPath(); g.moveTo(x, ly); g.lineTo(x + w, ly); g.stroke(); g.setLineDash([]);
    if (L.label) { g.font = font('M', 600, 26); g.direction = 'ltr'; g.textAlign = 'left'; g.fillStyle = Z.ac; g.fillText(L.label, x + 8, ly - 12); }
  });
  g.strokeStyle = rgba(Z.tx, 0.35); g.lineWidth = 2; g.beginPath(); g.moveTo(hx, y); g.lineTo(hx, y + h); g.stroke();   // the cursor (never mint: mint is never on a value)
  g.beginPath(); g.arc(hx, hy, 13, 0, Math.PI * 2); g.fillStyle = Z.oxL; g.fill();
  g.beginPath(); g.arc(hx, hy, 7, 0, Math.PI * 2); g.fillStyle = Z.tx; g.fill();
  g.restore();
  return {hx, hy};
}
/** Return bars (24h / 7d / 30d / 1y …) growing from a zero line, coloured by meaning, Latin mono labels. */
function returnBars(t, rows, x, y, w, h, t0, o = {}) {
  const g = o.g || X, mx = Math.max(...rows.map(r => Math.abs(r.v))) || 1, bw = w / rows.length;
  const zy = y + h / 2;
  g.save(); g.strokeStyle = Z.hair; g.lineWidth = 2; g.beginPath(); g.moveTo(x, zy); g.lineTo(x + w, zy); g.stroke();
  rows.forEach((r, i) => {
    const p = E.dock(P(t, t0 + i * 0.12, 0.6)), bh = (Math.abs(r.v) / mx) * (h / 2 - 50) * clamp(p, 0, 1.05), col = r.v >= 0 ? Z.up : Z.dn;
    const bx = x + i * bw + bw * 0.22, bwi = bw * 0.56;
    g.fillStyle = rgba(col, 0.9); g.beginPath(); g.roundRect(bx, r.v >= 0 ? zy - bh : zy, bwi, Math.max(2, bh), 8); g.fill();
    g.font = font('M', 600, 30); g.direction = 'ltr'; g.textAlign = 'center'; g.fillStyle = col;
    if (p > 0.6) {   // ⟨2026-11-27⟩ the triangle as a shape (no font of the page has it), then the value
      const lab = `${r.v >= 0 ? '+' : '−'}${Math.abs(r.v).toFixed(1)}%`, ly = r.v >= 0 ? zy - bh - 16 : zy + bh + 40;
      const lw = g.measureText(lab).width, ts = 30 * 0.62, gp = 8, lx = bx + bwi / 2 - (lw + ts + gp) / 2;
      tri(g, lx, ly, 30, r.v >= 0 ? 'up' : 'down', col);
      g.textAlign = 'left'; g.fillText(lab, lx + ts + gp, ly); g.textAlign = 'center';
    }
    g.fillStyle = Z.mu; g.font = font('M', 500, 26); g.fillText(String(r.k).toUpperCase(), bx + bwi / 2, r.v >= 0 ? zy + 44 : zy - 22);
  });
  g.restore();
}
/** A half dial 0..100 (fear & greed), the needle sweeping to the value; the zones in meaning colours. */
function gauge(t, value, cx, cy, r, t0, o = {}) {
  const g = o.g || X, p = E.dock(P(t, t0, 1.0)), a0 = Math.PI, a1 = 2 * Math.PI;
  g.save(); g.lineWidth = 26; g.lineCap = 'butt';
  [[0, 25, Z.dn], [25, 45, rgba(Z.dn, 0.55)], [45, 55, Z.flat], [55, 75, rgba(Z.up, 0.55)], [75, 100, Z.up]].forEach(([s, e, c]) => {
    g.strokeStyle = c; g.beginPath(); g.arc(cx, cy, r, a0 + (a1 - a0) * s / 100 + 0.01, a0 + (a1 - a0) * e / 100 - 0.01); g.stroke();
  });
  const ang = a0 + (a1 - a0) * clamp(value * p / 100);
  g.strokeStyle = Z.tx; g.lineWidth = 7; g.lineCap = 'round'; g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(ang) * (r - 40), cy + Math.sin(ang) * (r - 40)); g.stroke();
  g.beginPath(); g.arc(cx, cy, 18, 0, Math.PI * 2); g.fillStyle = Z.oxL; g.fill();
  g.restore();
}

/* ------------------------------------------------- HUD, tape, kicker, line ---- */
let HUD = null, TAPE = null;
/** The status bar (the brand's constant: every frame but the cold open's first 0.5 s and the end slate).
 *  y 236–300, under Instagram's top bar: the mark, ZARIB100X, BRIEF #, the pair, the making time; a live dot. */
function hud(t, a = 1) {
  if (!HUD || a <= 0) return;
  const y = 268;
  X.save(); X.globalAlpha *= a;
  X.fillStyle = rgba(Z.gr, 0.72); X.fillRect(0, 232, W, 72);
  X.fillStyle = Z.hair; X.fillRect(0, 303, W, 2);
  X.fillStyle = Z.ac; X.fillRect(0, 303, W * clamp(t / (HUD.end || 60)), 2);   // the brief's progress, mint
  X.restore();
  let x = 60;
  if (IMG.__mark) { X.save(); X.globalAlpha *= a; X.beginPath(); X.arc(x + 20, y, 20, 0, Math.PI * 2); X.clip(); X.drawImage(IMG.__mark, x, y - 20, 40, 40); X.restore(); x += 56; }
  x += txt('Zarib', x, y + 11, {kind: 'C', w: 700, px: 34, col: Z.tx, a});
  x += txt('100x', x + 1, y + 11, {kind: 'C', w: 700, px: 34, col: Z.ac, a}) + 34;
  const parts = [`BRIEF ${String(HUD.brief || 1).padStart(3, '0')}`, HUD.pair, HUD.time].filter(Boolean);
  parts.forEach(s => { X.save(); X.globalAlpha *= a * 0.5; X.fillStyle = Z.mu; X.fillRect(x - 18, y - 10, 2, 20); X.restore(); x += txt(s, x, y + 9, {kind: 'M', w: 500, px: 24, col: Z.mu, a, track: 1}) + 36; });
  const blink = 0.55 + 0.45 * Math.cos(t * Math.PI * 1.6);   // the live dot breathes (never blinks hard)
  X.save(); X.globalAlpha *= a; X.beginPath(); X.arc(1020, y, 9, 0, Math.PI * 2); X.fillStyle = rgba(Z.ac, blink); X.fill(); X.restore();
  txt('LIVE', 998, y + 9, {kind: 'M', w: 600, px: 24, col: Z.ac, a, align: 'right', track: 2});
}
/** The price tape under the HUD (y 306–350): real tickers of the day, scrolling right→left, meaning colours. */
function tape(t, a = 1) {
  if (!TAPE || !TAPE.length || a <= 0) return;
  // ⟨2026-11-27⟩ «▲»/«▼» as shapes (no font of the page has them): «  » keeps their room in the measure
  const y = 338, items = TAPE.map(r => `${r.s} ${r.p}    ${r.c >= 0 ? '+' : '−'}${Math.abs(r.c).toFixed(2)}%`);
  X.save(); X.globalAlpha *= a; X.fillStyle = rgba(Z.gr, 0.6); X.fillRect(0, 306, W, 46); X.restore();
  X.save(); X.beginPath(); X.rect(0, 306, W, 46); X.clip();
  X.font = font('M', 500, 25); const gap = 70;
  const ws = items.map(s => X.measureText(s).width + gap), total = ws.reduce((s, v) => s + v, 0);
  let x = -((t * 70) % total);
  for (let rep = 0; rep < 3 && x < W; rep++) items.forEach((s, i) => {
    const r = TAPE[i];
    txt(r.s, x, y, {kind: 'M', w: 600, px: 25, col: Z.tx, a: a * 0.9});
    const w1 = measure(r.s + ' ', {kind: 'M', w: 600, px: 25});
    const col = r.c >= 0 ? Z.up : Z.dn, w2 = measure(`${r.p}  `, {kind: 'M', w: 500, px: 25});
    txt(r.p, x + w1, y, {kind: 'M', w: 500, px: 25, col, a: a * 0.9});
    X.save(); X.globalAlpha *= a * 0.9; tri(X, x + w1 + w2, y, 25, r.c >= 0 ? 'up' : 'down', col); X.restore();
    txt(`${r.c >= 0 ? '+' : '−'}${Math.abs(r.c).toFixed(2)}%`, x + w1 + w2 + 25 * 0.62 + 8, y, {kind: 'M', w: 500, px: 25, col, a: a * 0.9});
    x += ws[i];
  });
  X.restore();
}
/** The chapter tab: «01» mono + the Persian label, a mint underline drawing in. Top-right, y ≈ 420. */
function kicker(t, num, label, t0, o = {}) {
  const a = E.o3(P(t, t0, 0.35)) * (o.out ? 1 - E.o3(P(t, o.out, 0.3)) : 1); if (a <= 0) return;
  const x = o.x || 1020, y = o.y || 430, dx = (1 - E.o5(P(t, t0, 0.5))) * 40;
  const lw = txt(label, x - dx, y, {px: 44, w: 800, col: Z.tx, a});
  const nw = measure(String(num).padStart(2, '0'), {kind: 'M', w: 600, px: 34});
  txt(String(num).padStart(2, '0'), x - lw - 24 - nw - dx, y - 2, {kind: 'M', w: 600, px: 34, col: Z.ac, a});
  X.save(); X.globalAlpha *= a; X.fillStyle = Z.ac; const u = (lw + nw + 24) * E.o5(P(t, t0 + 0.1, 0.5)); X.fillRect(x - u, y + 22, u, 5); X.restore();
  TEXTS.add(label);
}
/** The Zarib Line: the brand's mint hairline across the frame, marking the one level/number that matters. */
function zline(t, y, t0, o = {}) {
  const p = E.o5(P(t, t0, o.dur || 0.7)); if (p <= 0) return;
  X.save(); X.globalAlpha *= (o.a === undefined ? 1 : o.a);
  X.shadowColor = rgba(Z.ac, 0.9); X.shadowBlur = 18; X.fillStyle = Z.ac; X.fillRect(W - W * p, y - 2, W * p, 4); X.restore();
  if (o.label) txt(o.label, 60, y - 18, {kind: 'M', w: 600, px: 28, col: Z.ac, a: E.o3(P(t, t0 + 0.3, 0.3)), track: 2});
}
/** A Persian headline set big, line by line rising (the hook, a chapter's statement). [..] = key word in a mint chip. */
function headline(t, lines, x, y, t0, o = {}) {
  const px = o.px || 118, lh = o.lh || px * 1.28, w = o.w || 900;
  lines.forEach((ln, i) => {
    const p = E.o5(P(t, t0 + i * 0.12, 0.55)), a = E.o3(P(t, t0 + i * 0.12, 0.3)); if (a <= 0) return;
    const yy = y + i * lh + (1 - p) * 50;
    X.save(); X.beginPath(); X.rect(0, yy - lh, W, lh * 1.25); X.clip();
    keyLine(ln, x, yy, {px, w, a, align: o.align});
    X.restore();
    TEXTS.add(ln.replace(/[\[\]]/g, ''));
  });
}
/** One RTL line with [key] words in the mint chip. Right-aligned at x (or centred). */
function keyLine(s, x, y, o) {
  const parts = endStop(s).split(/(\[[^\]]+\])/).filter(Boolean), px = o.px;
  const ws = parts.map(q => q.startsWith('[') ? measure(q.slice(1, -1), {px, w: o.w}) + px * 0.5 : measure(q, {px, w: o.w}));
  const total = ws.reduce((s, v) => s + v, 0);
  let cx = o.align === 'center' ? W / 2 + total / 2 : x;
  parts.forEach((q, i) => {
    if (q.startsWith('[')) {
      X.save(); X.globalAlpha *= o.a; X.fillStyle = Z.ac; X.beginPath(); X.roundRect(cx - ws[i], y - px * 0.92, ws[i], px * 1.22, px * 0.22); X.fill(); X.restore();
      txt(q.slice(1, -1), cx - px * 0.25, y, {px, w: o.w, col: Z.gr, a: o.a});
    } else txt(q, cx, y, {px, w: o.w, col: Z.tx, a: o.a});
    cx -= ws[i];
  });
}

/* --------------------------------------------------------------- captions ---- */
let CAPS = [];
/** Captions from the word times: chunks of ≤ 5 words / ≤ 2.2 s, never across a sentence. keys: words in mint. */
function capsFromWords(lines, o = {}) {
  const keys = new Set(o.keys || []), out = [];
  (lines || []).forEach(l => {
    let cur = [];
    const flush = () => { if (cur.length) out.push({s: cur[0].s, e: cur[cur.length - 1].e, words: cur}); cur = []; };
    l.words.forEach(w => {
      if (cur.length && (cur.length >= (o.max || 5) || w.e - cur[0].s > 2.2)) flush();
      cur.push({w: w.w, s: w.s, e: w.e, k: keys.has(w.w.replace(/[.،؛:!?؟«»]/g, ''))});
    });
    flush();
  });
  out.forEach((c, i) => { c.e2 = i + 1 < out.length ? Math.min(out[i + 1].s, c.e + 0.6) : c.e + 0.8; });
  return out;
}
/** The caption block (y ≈ 1400–1520): words arrive one by one (rise 24 px, 0.18 s), the newest ivory,
 *  the earlier at 80 %, key words in mint. */
function captions(t, o = {}) {
  const c = CAPS.find(c => t >= c.s - 0.05 && t < c.e2); if (!c) return;
  const px = o.px || 64, y = o.y || 1480, out = 1 - E.o3(P(t, c.e2 - 0.18, 0.18));
  const ws = c.words.map(w => endStop(w.w)), sp = measure(' ', {px, w: 800});
  const widths = ws.map(w => measure(w, {px, w: 800}));
  const total = widths.reduce((s, v) => s + v, 0) + sp * (ws.length - 1);
  const scale = Math.min(1, 940 / total);
  let x = W / 2 + total * scale / 2;
  X.save(); X.globalAlpha *= out;
  const plate = X.createLinearGradient(0, y - 150, 0, y + 90); plate.addColorStop(0, rgba(Z.gr, 0)); plate.addColorStop(0.35, rgba(Z.gr, 0.82)); plate.addColorStop(0.75, rgba(Z.gr, 0.82)); plate.addColorStop(1, rgba(Z.gr, 0.0));
  X.fillStyle = plate; X.fillRect(0, y - 150, W, 240);
  c.words.forEach((w, i) => {
    const p = E.o5(P(t, w.s - 0.06, 0.18)), a = E.o3(P(t, w.s - 0.06, 0.12));
    if (a > 0) {
      const newest = i === c.words.length - 1 || t < c.words[i + 1].s;
      txt(ws[i], x, y + (1 - p) * 24, {px: px * scale, w: 800, col: w.k ? Z.ac : Z.tx, a: a * (newest || w.k ? 1 : 0.8)});
    }
    x -= (widths[i] + sp) * scale;
    TEXTS.add(ws[i]);
  });
  X.restore();
}

/* ------------------------------------------------------------- the mark ---- */
/** The lockup: the page's round photo (a mint ring) + «Zarib100x» (Plex Condensed Bold, «100x» mint)
 *  + «بهنام جلالی» under it. size = the photo's diameter. Centre-aligned at cx. */
function lockup(cx, cy, size, a = 1, o = {}) {
  X.save(); X.globalAlpha *= a;
  if (IMG.__mark) { X.beginPath(); X.arc(cx, cy, size / 2, 0, Math.PI * 2); X.save(); X.clip(); X.drawImage(IMG.__mark, cx - size / 2, cy - size / 2, size, size); X.restore(); }
  X.lineWidth = Math.max(3, size * 0.035); X.strokeStyle = Z.ac; X.beginPath(); X.arc(cx, cy, size / 2 + X.lineWidth, 0, Math.PI * 2); X.stroke();
  X.restore();
  const px = size * 0.42, y = cy + size / 2 + px * 1.25;
  const w1 = measure('Zarib', {kind: 'C', w: 700, px}), w2 = measure('100x', {kind: 'C', w: 700, px});
  txt('Zarib', cx - (w1 + w2) / 2, y, {kind: 'C', w: 700, px, a});
  txt('100x', cx - (w1 + w2) / 2 + w1, y, {kind: 'C', w: 700, px, col: Z.ac, a});
  if (o.name !== false) txt('بهنام جلالی', cx, y + px * 0.95, {px: px * 0.5, w: 400, col: Z.mu, a, align: 'center'});
}
/** The end slate (the last ≥ 3 s): the lockup, the comment word in the mint chip, @Zarib100x. */
function endSlate(t, t0, word, o = {}) {
  const a = E.o3(P(t, t0, 0.5)); if (a <= 0) return;
  X.save(); X.globalAlpha *= a; X.fillStyle = Z.gr; X.fillRect(0, 0, W, H); X.restore();
  X.save(); X.globalAlpha *= a; ground(t, {grid: true, light: 0.26, ly: 760, lx: 540}); X.restore();
  const p = E.dock(P(t, t0 + 0.1, 0.7));
  lockup(W / 2, 700 - (1 - p) * 40, 230, a);
  if (word) {
    const q = E.o3(P(t, t0 + 0.45, 0.4));
    txt(o.ask || 'کلمه‌ی زیر رو کامنت کن', W / 2, 1130, {px: 50, w: 700, col: Z.tx, a: q, align: 'center'});
    const ww = measure(word, {px: 104, w: 900}) + 110;
    X.save(); X.globalAlpha *= q; X.fillStyle = Z.ac; X.beginPath(); X.roundRect(W / 2 - ww / 2, 1180, ww, 150, 40); X.fill(); X.restore();
    txt(word, W / 2, 1290, {px: 104, w: 900, col: Z.gr, a: q, align: 'center'});
    txt(o.then || 'تا جزئیات رو برات دایرکت کنم', W / 2, 1420, {px: 42, w: 500, col: Z.mu, a: q, align: 'center'});
    TEXTS.add(word);
  }
  txt('@Zarib100x', W / 2, 1530, {kind: 'M', w: 600, px: 40, col: Z.ac, a: E.o3(P(t, t0 + 0.7, 0.4)), align: 'center', track: 2});
}

/* ------------------------------------------------------------ transitions ---- */
/** The four brand transitions (0.42 s, centred on the cut). Each paints shot B over A through a mask.
 *  blade: a mint blade sweeps diagonally, B behind it · slats: 8 horizontal slats flip in, staggered
 *  (a split-flap board) · aperture: a rounded square opens from the centre (or o.cx/cy), mint rim ·
 *  slide: A slides out left, B in from the right, a mint seam between them. */
function transit(kind, q, drawA, drawB, o = {}) {
  const k = E.io3(clamp(q));
  if (kind === 'cut' || k <= 0) { (k < 1 && kind !== 'cut' ? drawA : drawB)(); return; }
  if (k >= 1) { drawB(); return; }
  drawA();
  X.save();
  if (kind === 'blade') {
    const d = (W + H * 0.5) * k * 1.15 - 200;
    X.beginPath(); X.moveTo(W, 0); X.lineTo(W - d, 0); X.lineTo(W - d + H * 0.5, H); X.lineTo(W, H); X.closePath(); X.save(); X.clip(); drawB(); X.restore();
    X.beginPath(); X.moveTo(W - d, 0); X.lineTo(W - d - 26, 0); X.lineTo(W - d - 26 + H * 0.5, H); X.lineTo(W - d + H * 0.5, H); X.closePath();
    X.shadowColor = Z.ac; X.shadowBlur = 30; X.fillStyle = Z.ac; X.fill();
  } else if (kind === 'slats') {
    const nS = 8, sh = H / nS;
    X.beginPath();
    for (let i = 0; i < nS; i++) { const p = E.o3(clamp(k * 1.6 - i * 0.6 / nS)); X.rect(0, i * sh + sh * (1 - p) / 2, W, sh * p); }
    X.save(); X.clip(); drawB(); X.restore();
  } else if (kind === 'aperture') {
    const cx = o.cx || W / 2, cy = o.cy || H / 2, r = 40 + k * 1500;
    X.beginPath(); X.roundRect(cx - r * 0.75, cy - r, r * 1.5, r * 2, 60); X.save(); X.clip(); drawB(); X.restore();
    X.lineWidth = 8; X.strokeStyle = Z.ac; X.shadowColor = Z.ac; X.shadowBlur = 24; X.beginPath(); X.roundRect(cx - r * 0.75, cy - r, r * 1.5, r * 2, 60); X.stroke();
  } else if (kind === 'slide') {
    X.save(); X.fillStyle = Z.gr; X.fillRect(0, 0, W, H); X.translate(-W * k, 0); drawA(); X.restore();
    X.save(); X.translate(W * (1 - k), 0); drawB(); X.restore();
    X.fillStyle = Z.ac; X.shadowColor = Z.ac; X.shadowBlur = 30; X.fillRect(W * (1 - k) - 6, 0, 6, H);
  }
  X.restore();
}

/* ---------------------------------------------------------------- camera ---- */
/** The rig: a slow push (s0→s1) and drift on a shot, around (cx,cy). Apply inside a shot's draw. */
function rig(p, o = {}) {
  const s = lerp(o.s0 || 1, o.s1 || 1.05, E.io3(p)), cx = o.cx || W / 2, cy = o.cy || H / 2;
  const dx = lerp(o.dx0 || 0, o.dx1 || 0, E.io3(p)), dy = lerp(o.dy0 || 0, o.dy1 || 0, E.io3(p));
  X.translate(cx + dx, cy + dy); X.scale(s, s); X.translate(-cx, -cy);
}

/* ----------------------------------------------------------------- the reel ---- */
let REEL = null;
function reel(cfg) {
  REEL = cfg; CAPS = cfg.caps || []; HUD = Object.assign({end: cfg.END}, cfg.hud || {}); TAPE = cfg.tape || DATA.tape || null;
  window.END = cfg.END;
}
function drawShot(s, t) { X.save(); s.draw(t, clamp((t - s.a) / Math.max(0.01, s.b - s.a)), s); X.restore(); }
function frame(t) {
  X.setTransform(1, 0, 0, 1, 0, 0); X.globalAlpha = 1; X.fillStyle = Z.gr; X.fillRect(0, 0, W, H);
  const S = REEL.shots, TR = 0.42;
  let i = S.findIndex(s => t >= s.a && t < s.b); if (i < 0) i = t < S[0].a ? 0 : S.length - 1;
  const s = S[i], nx = S[i + 1];
  if (nx && t > s.b - TR / 2 && (nx.tr || 'blade') !== 'cut') transit(nx.tr || 'blade', (t - (s.b - TR / 2)) / TR, () => drawShot(s, t), () => drawShot(nx, t), nx.trOpt || {});
  else if (i > 0 && t < s.a + TR / 2 && (s.tr || 'blade') !== 'cut') transit(s.tr || 'blade', (t - (s.a - TR / 2)) / TR, () => drawShot(S[i - 1], t), () => drawShot(s, t), s.trOpt || {});
  else drawShot(s, t);
  const endAt = REEL.end ? REEL.end.at : 1e9;
  const hudA = E.o3(P(t, REEL.hudIn === undefined ? 0.5 : REEL.hudIn, 0.4)) * (1 - E.o3(P(t, endAt - 0.2, 0.3)));
  hud(t, hudA); tape(t, hudA);
  if (t < endAt) captions(t, REEL.capOpt || {});
  if (REEL.end) endSlate(t, endAt, REEL.end.word, REEL.end);
  dither();
  return C.toDataURL('image/jpeg', 1.0);  // 1.0 = 4:4:4 (owner 2026-11-26: the highest quality)
}
window.frame = frame;
window.DESK = {Z, E, P, clamp, lerp, rgba, fa, iso, txt, measure, ground, plate, cutout, persp, panelBody, panel, odometer, changeChip,
  lineChart, returnBars, gauge, hud, tape, kicker, zline, headline, keyLine, capsFromWords, captions, lockup, endSlate, transit, rig, reel,
  IMG, TEXTS, W, H};
window.DESK_TEXTS = () => Array.from(TEXTS);
