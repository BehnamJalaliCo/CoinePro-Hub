/* bitmart — THE FILE («پرونده»): the page's motion library (Canvas 2D, every frame a pure function of t).
 * Loaded by COMMON/motion/story_engine.py into the day's page, before the session's motion/scene.js.
 * Read COMMON/DIRECTION.md and COMMON/motion/README.md first. Nothing here is restyled per reel: the
 * colours, the fonts, the HUD, the marker stroke, the captions, the lockup and the transitions ARE the
 * brand. A reel adds its own shots (plates, documents, numbers, maps, timelines) on top, in scene.js.
 *
 * The scene contract (scene.js):
 *   const SHOTS = [{a: 0, b: 2.6, tr: 'swipe', draw: (t, p, s) => { ... }}, ...];   // a..b seconds
 *   const CAPS  = STORY.capsFromWords(DATA.lines, {keys: ['FTX', 'ورشکست']});
 *   STORY.reel({shots: SHOTS, caps: CAPS, hud: {file: 12, title: 'سقوط FTX'},
 *               end: {word: 'پرونده', at: 61.2}, END: 64.0});
 * `p` = 0..1 through the shot; `s` = the shot. A shot's `tr` is the transition INTO it:
 * 'swipe' | 'shutter' | 'zoom' | 'page' | 'cut' (0.46 s centred on its start; 'cut' = none).
 */
"use strict";
const W = 1080, H = 1920;
const B = {   // bitmart — the owner's palette (2026-11-26): orange + ink navy, cream for text (brand/README.md)
  nv: '#0F1630', nv2: '#162043', nv3: '#1E2A55', deep: '#090E20',   // ink navy ground, panels, raised, the deepest shadow
  or: '#FF6A2B', orL: '#FF8C5A', orD: '#D9521A', orG: '#FFB089',    // bitmart orange, its light, its shade, its glow
  cr: '#F5EFE6', mu: '#9AA3BD', hair: 'rgba(245,239,230,0.14)',      // cream text, muted, the hairline
  paper: '#EFE6D3', paperD: '#D9CDB4', ink: '#17130E',               // documents: paper, its shadow side, ink
  up: '#2FD67B', dn: '#FF4766', flat: '#9AA3BD',                     // meaning: ALWAYS with ▲ / ▼; orange is never a «down»
};
const C = document.getElementById('c'), X = C.getContext('2d', {alpha: false});
X.imageSmoothingQuality = 'high';
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const lerp = (a, b, p) => a + (b - a) * p;
const P = (t, t0, d) => clamp((t - t0) / d);
const E = {
  o2: p => 1 - (1 - p) * (1 - p), o3: p => 1 - Math.pow(1 - p, 3), o5: p => 1 - Math.pow(1 - p, 5),
  io3: p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2,
  io5: p => p < .5 ? 16 * Math.pow(p, 5) : 1 - Math.pow(-2 * p + 2, 5) / 2,
  oexpo: p => p >= 1 ? 1 : 1 - Math.pow(2, -10 * p),
  // a landing: fast, a 3 % settle (paper lands, it never bounces)
  land: p => { p = clamp(p); const c1 = 1.4, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); },
};
function rgba(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${clamp(a).toFixed(3)})`; }
// a seeded random (the same frame always draws the same): R(seed)() → 0..1
function R(seed) { let s = (seed * 2654435761) >>> 0 || 1; return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; }; }

/* ---------------------------------------------------------------- type ---- */
// families registered by the engine: A<w> = Anjoman Max (display: hooks, headlines, numbers, the wordmark),
// R<w> = Ravagh (captions, labels, body), M<w> = IBM Plex Mono (file numbers, dates, tickers — Latin only)
const FA_DIG = '۰۱۲۳۴۵۶۷۸۹';
const fa = v => String(v).replace(/[0-9]/g, d => FA_DIG[d]).replace(/\./g, '٫').replace(/,/g, '٬').replace(/%/g, '٪');
// Digits and Latin runs inside RTL text: a run WITH a Latin letter or $ (FTX, $65B, bitmart, iPhone 4) stays
// Latin and is isolated LTR (LRI … PDI) so it never scrambles; a run of digits ALONE becomes Persian digits
// (۱۹۹۰، ۶۵٪، ۲٫۵). Never Persian and Latin digits in one run. Every STORY text call does this.
const LRI = '⁦', PDI = '⁩';
const iso = s => String(s).replace(/[A-Za-z0-9$€£][A-Za-z0-9$€£%.,/:+\-×#@_ ]*[A-Za-z0-9%$€£]|[A-Za-z0-9$€£]/g,
  m => /[A-Za-z$€£]/.test(m) ? LRI + m + PDI : fa(m));
const endStop = s => String(s).replace(/[.،؛:]+\s*$/u, '');   // never a full stop at the end on screen
const WEIGHTS = {A: [300, 400, 500, 600, 700, 800, 900, 950, 970, 990, 1000], R: [200, 300, 400, 500, 600, 700, 800, 900], M: [500, 600]};
function font(kind, w, px) {
  const ws = WEIGHTS[kind] || WEIGHTS.R; let best = ws[0];
  ws.forEach(v => { if (Math.abs(v - w) < Math.abs(best - w)) best = v; });
  return `${px}px ${kind}${best}`;
}
const TEXTS = new Set();   // every on-screen string, for tools/textlint.py (window.STORY_TEXTS)
/** Draw text. o: {px, w (weight), kind ('A' display | 'R' body | 'M' mono), col, align ('right' default for
 *  RTL), rtl (default true unless kind M), a (alpha), track (px, mono only), maxW (shrinks to fit), g (ctx)} */
function txt(s, x, y, o = {}) {
  const g = o.g || X, kind = o.kind || 'R', ltr = o.rtl === false || kind === 'M';
  let str = endStop(s);
  if (!ltr) str = iso(str);
  let px = o.px || 48;
  g.save();
  g.direction = ltr ? 'ltr' : 'rtl';
  g.textAlign = o.align || (ltr ? 'left' : 'right');
  g.textBaseline = o.base || 'alphabetic';
  if (o.track && 'letterSpacing' in g) g.letterSpacing = `${o.track}px`;
  g.font = font(kind, o.w || 700, px);
  if (o.maxW) { const m = g.measureText(str).width; if (m > o.maxW) { px *= o.maxW / m; g.font = font(kind, o.w || 700, px); } }
  g.globalAlpha *= (o.a === undefined ? 1 : o.a);
  if (o.shadow) { g.shadowColor = rgba(B.deep, 0.6); g.shadowBlur = o.shadow; g.shadowOffsetY = o.shadow * 0.25; }
  g.fillStyle = o.col || B.cr;
  g.fillText(str, x, y);
  const wd = g.measureText(str).width;
  g.restore();
  if (String(s).trim()) TEXTS.add(endStop(s));
  return wd;
}
function measure(s, o = {}) {
  const g = o.g || X, kind = o.kind || 'R', ltr = o.rtl === false || kind === 'M';
  g.save(); g.direction = ltr ? 'ltr' : 'rtl'; if (o.track && 'letterSpacing' in g) g.letterSpacing = `${o.track}px`;
  g.font = font(kind, o.w || 700, o.px || 48);
  const w = g.measureText(ltr ? endStop(s) : iso(endStop(s))).width; g.restore(); return w;
}
/** Word-wrap a Persian string into lines no wider than maxW (for documents and quotes). */
function wrap(s, maxW, o = {}) {
  const words = endStop(s).split(/\s+/), out = []; let cur = '';
  words.forEach(w => { const n = cur ? cur + ' ' + w : w; if (cur && measure(n, o) > maxW) { out.push(cur); cur = w; } else cur = n; });
  if (cur) out.push(cur); return out;
}

/* ------------------------------------------------------------ the world ---- */
let NOISE = null;
function makeNoise() {   // an invisible ±1-level dither tile: gradients never band after Instagram's 8-bit re-encode
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), d = g.createImageData(256, 256), r = R(99);
  for (let i = 0; i < d.data.length; i += 4) { const v = r() * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
  g.putImageData(d, 0, 0); NOISE = c;
}
function dither() { if (!NOISE) makeNoise(); X.save(); X.globalAlpha = 0.018; X.globalCompositeOperation = 'overlay'; X.fillStyle = X.createPattern(NOISE, 'repeat'); X.fillRect(0, 0, W, H); X.restore(); }
/** The room: ink navy, one warm orange key light (a desk lamp in a dark archive), the ledger's faint rule
 *  lines (o.ledger), a vignette. o: {lx, ly, lr, light (0..1), ledger (0..1), drift} */
function ground(t, o = {}) {
  X.fillStyle = B.nv; X.fillRect(0, 0, W, H);
  const lx = o.lx === undefined ? 300 : o.lx, ly = o.ly === undefined ? 520 : o.ly;
  const g = X.createRadialGradient(lx, ly, 0, lx, ly, o.lr || 1250);
  const L = o.light === undefined ? 0.42 : o.light;
  g.addColorStop(0, rgba(B.orD, L * 0.85)); g.addColorStop(0.35, rgba(B.orD, L * 0.28)); g.addColorStop(1, rgba(B.nv, 0));
  X.fillStyle = g; X.fillRect(0, 0, W, H);
  const lg = o.ledger === undefined ? 0.5 : o.ledger;
  if (lg > 0) {   // the ledger: horizontal rules every 64 px drifting up slowly, one orange margin rule
    const off = ((t * (o.drift === undefined ? 10 : o.drift)) % 64);
    X.save(); X.lineWidth = 1.5;
    for (let y = -off; y < H; y += 64) { X.strokeStyle = rgba(B.cr, 0.045 * lg); X.beginPath(); X.moveTo(0, y); X.lineTo(W, y); X.stroke(); }
    X.strokeStyle = rgba(B.or, 0.16 * lg); X.beginPath(); X.moveTo(W - 120, 0); X.lineTo(W - 120, H); X.stroke();
    X.restore();
  }
  vignette(0.75);
}
function vignette(a = 0.7) {
  const g = X.createRadialGradient(W / 2, H * 0.46, H * 0.28, W / 2, H * 0.5, H * 0.78);
  g.addColorStop(0, rgba(B.deep, 0)); g.addColorStop(1, rgba(B.deep, a));
  X.fillStyle = g; X.fillRect(0, 0, W, H);
}

/* -------------------------------------------------------------- pictures ---- */
const IMG = {};     // the engine preloads every assets/ picture: IMG['assets/plate1.jpg']
const TONED = {};   // toned copies, made once per picture
/** A toned copy of a picture: 'duo' (the archive look: ink navy shadows → cream highlights, orange in the
 *  mids) or 'mono' (warm black and white). Made once, cached. */
function toned(src, tone) {
  const k = src + '|' + tone; if (TONED[k]) return TONED[k];
  const im = IMG[src]; if (!im) return null;
  const c = document.createElement('canvas'), sc = Math.min(1, 2200 / Math.max(im.width, im.height));
  c.width = Math.round(im.width * sc); c.height = Math.round(im.height * sc);
  const g = c.getContext('2d'); g.drawImage(im, 0, 0, c.width, c.height);
  const d = g.getImageData(0, 0, c.width, c.height), a = d.data;
  const ramp = tone === 'mono'
    ? [[0, [14, 12, 12]], [0.55, [150, 140, 128]], [1, [248, 242, 232]]]
    : [[0, [9, 14, 32]], [0.42, [92, 64, 70]], [0.66, [214, 120, 72]], [1, [248, 240, 228]]];
  const lut = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i++) {
    const v = i / 255; let j = 0; while (j < ramp.length - 2 && v > ramp[j + 1][0]) j++;
    const [p0, c0] = ramp[j], [p1, c1] = ramp[j + 1], f = clamp((v - p0) / (p1 - p0));
    for (let ch = 0; ch < 3; ch++) lut[i * 3 + ch] = lerp(c0[ch], c1[ch], f);
  }
  for (let i = 0; i < a.length; i += 4) {
    let l = 0.299 * a[i] + 0.587 * a[i + 1] + 0.114 * a[i + 2];
    l = clamp((l - 128) * 1.12 + 128, 0, 255) | 0;
    a[i] = lut[l * 3]; a[i + 1] = lut[l * 3 + 1]; a[i + 2] = lut[l * 3 + 2];
  }
  g.putImageData(d, 0, 0); TONED[k] = c; return c;
}
/** A plate, cover-fit, with the camera move on it (Ken Burns: push + pan) and the brand grade.
 *  o: {x,y,w,h, p (0..1), push: [s0,s1], pan: [[fx0,fy0],[fx1,fy1]], tone: 'color'|'duo'|'mono',
 *      grade (0..1: ink navy from below, orange warmth from the key side), a} */
function plate(src, o = {}) {
  const im = o.tone && o.tone !== 'color' ? toned(src, o.tone) : IMG[src]; if (!im) return;
  const x = o.x || 0, y = o.y || 0, w = o.w || W, h = o.h || H, p = o.p === undefined ? 0 : o.p;
  const pu = o.push || [1.05, 1.14], s = lerp(pu[0], pu[1], E.io3(p));
  const k = Math.max(w / im.width, h / im.height) * s, dw = im.width * k, dh = im.height * k;
  const pan = o.pan || [[0.5, 0.5], [0.5, 0.5]];
  const fx = lerp(pan[0][0], pan[1][0], E.io3(p)), fy = lerp(pan[0][1], pan[1][1], E.io3(p));
  X.save(); X.globalAlpha *= (o.a === undefined ? 1 : o.a);
  X.beginPath(); X.rect(x, y, w, h); X.clip();
  X.drawImage(im, x - (dw - w) * fx, y - (dh - h) * fy, dw, dh);
  const gr = o.grade === undefined ? 0.6 : o.grade;
  let g = X.createLinearGradient(0, y + h * 0.3, 0, y + h); g.addColorStop(0, rgba(B.nv, 0)); g.addColorStop(1, rgba(B.nv, 0.9 * gr + 0.05));
  X.fillStyle = g; X.fillRect(x, y, w, h);
  g = X.createLinearGradient(x, y, x + w, y + h * 0.7); g.addColorStop(0, rgba(B.or, 0.38 * gr)); g.addColorStop(1, rgba(B.nv, 0.25 * gr));
  X.globalCompositeOperation = 'soft-light'; X.fillStyle = g; X.fillRect(x, y, w, h);
  X.restore();
}
/** 2.5D parallax: a background plate and a cut-out subject (RGBA png) moving at different rates and
 *  scales, so the photo gains depth. o: {p, back: {push, pan, tone}, front: {cx, cy, h, dx, dy, s0, s1}} */
function parallax(srcBack, srcFront, o = {}) {
  const p = o.p || 0;
  plate(srcBack, Object.assign({p, push: [1.08, 1.16]}, o.back || {}));
  const f = o.front || {}, q = E.io3(p);
  const sc = lerp(f.s0 || 1, f.s1 || 1.08, q);
  cutout(srcFront, (f.cx || W / 2) + lerp(0, f.dx || -40, q), (f.cy || H * 0.55) + lerp(0, f.dy || 0, q), (f.h || 1100) * sc, f);
}
/** A cut-out (RGBA) on its own plane: a soft shadow under it, a warm orange rim on its key side. */
function cutout(src, cx, cy, hgt, o = {}) {
  const im = IMG[src]; if (!im) return;
  const k = hgt / im.height, w = im.width * k;
  X.save(); X.globalAlpha *= (o.a === undefined ? 1 : o.a);
  if (o.rim !== false) { X.shadowColor = rgba(B.or, 0.32); X.shadowBlur = 36; X.shadowOffsetX = -6; }
  X.drawImage(im, cx - w / 2, cy - hgt / 2, w, hgt); X.restore();
}

/* ------------------------------------------------------- 3D cards, paper ---- */
const OFF = {};
function offscreen(key, w, h) { let c = OFF[key]; if (!c || c.width !== w || c.height !== h) { c = document.createElement('canvas'); c.width = w; c.height = h; OFF[key] = c; } const g = c.getContext('2d'); g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, w, h); return [c, g]; }
/** Draw `fn(g, w, h)` into an offscreen card and project it in perspective (ry / rx degrees, 2 px strips),
 *  rotated in-plane by rot degrees, scaled by s, with an optional drop shadow (sh px). */
function persp(key, w, h, cx, cy, o, fn) {
  const [c, g] = offscreen(key, w, h); fn(g, w, h);
  const ry = (o.ry || 0) * Math.PI / 180, rx = (o.rx || 0) * Math.PI / 180, f = 1700, sc = o.s || 1;
  X.save(); X.globalAlpha *= (o.a === undefined ? 1 : o.a);
  X.translate(cx, cy); X.rotate((o.rot || 0) * Math.PI / 180);
  if (o.sh) { X.shadowColor = rgba(B.deep, 0.55); X.shadowBlur = o.sh; X.shadowOffsetY = o.sh * 0.35; }
  if (!ry && !rx) { X.drawImage(c, -w * sc / 2, -h * sc / 2, w * sc, h * sc); X.restore(); return; }
  if (o.sh) { X.fillStyle = rgba(B.deep, 0.001); }
  if (Math.abs(ry) >= Math.abs(rx)) {
    for (let u = 0; u < w; u += 2) {
      const xl = (u - w / 2) * sc, z = xl * Math.sin(ry), q = f / (f + z);
      X.drawImage(c, u, 0, 2, h, xl * Math.cos(ry) * q, -h * sc * q / 2, 2 * sc * Math.cos(ry) * q + 0.6, h * sc * q);
    }
  } else {
    for (let v = 0; v < h; v += 2) {
      const yl = (v - h / 2) * sc, z = yl * Math.sin(rx), q = f / (f + z);
      X.drawImage(c, 0, v, w, 2, -w * sc * q / 2, yl * Math.cos(rx) * q, w * sc * q, 2 * sc * Math.cos(rx) * q + 0.6);
    }
  }
  X.restore();
}
let PAPER = null;
function paperTile() {   // the paper's fibre: a soft procedural tile (made once)
  if (PAPER) return PAPER;
  const c = document.createElement('canvas'); c.width = c.height = 512;
  const g = c.getContext('2d'), d = g.createImageData(512, 512), r = R(7);
  for (let i = 0; i < d.data.length; i += 4) { const v = 238 + (r() - 0.5) * 10; d.data[i] = v; d.data[i + 1] = v - 7; d.data[i + 2] = v - 22; d.data[i + 3] = 255; }
  g.putImageData(d, 0, 0);
  g.globalAlpha = 0.05; g.strokeStyle = '#8a7a5a';
  for (let k = 0; k < 220; k++) { const x = r() * 512, y = r() * 512, l = 8 + r() * 30, an = r() * Math.PI; g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(an) * l, y + Math.sin(an) * l); g.stroke(); }
  PAPER = c; return c;
}
/** The body of a document (in an offscreen g): kind 'paper' (aged paper, a fold, toned edges), 'photo' (a
 *  print with a white border; draw the picture inside with photoIn), 'card' (an ink navy glass card with
 *  the orange top edge). */
function docBody(g, w, h, kind) {
  g.save();
  if (kind === 'card') {
    g.beginPath(); g.roundRect(1, 1, w - 2, h - 2, 24); g.fillStyle = rgba(B.nv2, 0.94); g.fill();
    g.lineWidth = 2; g.strokeStyle = B.hair; g.stroke();
    g.beginPath(); g.roundRect(1, 1, w - 2, h - 2, 24); g.clip(); g.fillStyle = B.or; g.fillRect(0, 0, w, 5);
  } else {
    g.fillStyle = g.createPattern(paperTile(), 'repeat'); g.fillRect(0, 0, w, h);
    if (kind === 'paper') {   // toned edges and one soft fold across
      const e = g.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.3, w / 2, h / 2, Math.max(w, h) * 0.75);
      e.addColorStop(0, 'rgba(120,90,40,0)'); e.addColorStop(1, 'rgba(120,90,40,0.22)'); g.fillStyle = e; g.fillRect(0, 0, w, h);
      const fy = h * 0.38, fl = g.createLinearGradient(0, fy - 18, 0, fy + 18);
      fl.addColorStop(0, 'rgba(0,0,0,0)'); fl.addColorStop(0.5, 'rgba(60,40,20,0.10)'); fl.addColorStop(0.52, 'rgba(255,255,255,0.18)'); fl.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = fl; g.fillRect(0, fy - 18, w, 36);
    }
  }
  g.restore();
}
/** A picture inside a photo print (its border 4 %). */
function photoIn(g, w, h, src, o = {}) {
  const im = o.tone && o.tone !== 'color' ? toned(src, o.tone) : IMG[src]; if (!im) return;
  const b = Math.round(Math.min(w, h) * 0.045), iw = w - 2 * b, ih = h - 2 * b - (o.caption ? b * 2.2 : 0);
  const k = Math.max(iw / im.width, ih / im.height) * (o.s || 1);
  g.save(); g.beginPath(); g.rect(b, b, iw, ih); g.clip();
  g.drawImage(im, b + (iw - im.width * k) / 2, b + (ih - im.height * k) / 2, im.width * k, im.height * k); g.restore();
  if (o.caption) txt(o.caption, w - b, h - b * 1.1, {g, px: b * 1.15, w: 600, col: B.ink, kind: 'R'});
}
/** A document that LANDS: it arrives from above (or o.from), turning, and settles at its angle o.rot with a
 *  drop shadow. o: {t0, kind ('paper'|'photo'|'card'), rot, from ('above'|'right'|'left'|'below'), ry, s}.
 *  Draw inside with fn(g, w, h) — local coordinates of the document. */
function doc(key, t, x, y, w, h, o, fn) {
  const t0 = o.t0 || 0, p = E.land(P(t, t0, 0.6)), a = E.o3(P(t, t0, 0.18)); if (a <= 0) return;
  const fr = o.from || 'above';
  const dx = fr === 'right' ? 700 : fr === 'left' ? -700 : 0, dy = fr === 'above' ? -900 : fr === 'below' ? 900 : 0;
  const rot = lerp((o.rot || 0) + (fr === 'left' ? -14 : 14), o.rot || 0, p);
  const s = lerp(1.12, o.s || 1, p);
  persp(key, w, h, x + w / 2 + dx * (1 - p), y + h / 2 + dy * (1 - p), {rot, s, a, ry: o.ry || 0, sh: o.sh === undefined ? 40 : o.sh},
    (g, ww, hh) => { docBody(g, ww, hh, o.kind || 'paper'); if (fn) fn(g, ww, hh); });
}
/** A newspaper clipping: the masthead (o.paper, never a real paper's name), a date line, the headline in
 *  Anjoman black ink, a few grey text lines. Uses doc(). */
function clipping(key, t, x, y, w, h, o) {
  doc(key, t, x, y, w, h, Object.assign({kind: 'paper'}, o), (g, ww, hh) => {
    const m = ww * 0.07;
    txt(o.paper || 'روزنامه‌ی اقتصاد', ww / 2, m + 70, {g, kind: 'A', w: 950, px: 64, col: B.ink, align: 'center'});
    g.fillStyle = B.ink; g.fillRect(m, m + 96, ww - 2 * m, 4); g.fillRect(m, m + 108, ww - 2 * m, 1.5);
    if (o.date) txt(o.date, ww - m, m + 148, {g, px: 30, w: 500, col: 'rgba(23,19,14,0.7)'});
    let yy = m + 250;
    (o.headline || []).forEach(ln => { txt(ln, ww - m, yy, {g, kind: 'A', w: 990, px: o.hpx || 82, col: B.ink, maxW: ww - 2 * m}); yy += (o.hpx || 82) * 1.22; });
    g.fillStyle = 'rgba(23,19,14,0.16)';
    for (let i = 0; i < (o.rows || 7); i++) { const lw = (ww - 2 * m) * (i % 3 === 2 ? 0.7 : 1); g.fillRect(ww - m - lw, yy + 20 + i * 38, lw, 14); }
  });
}
/** An ink stamp («ورشکسته», «محرمانه», «تأیید شد»): lands from 1.7× with a slight turn; rough ink. No sound. */
function stamp(t, s, cx, cy, t0, o = {}) {
  const p = E.land(P(t, t0, 0.32)), a = E.o3(P(t, t0, 0.1)); if (a <= 0) return;
  const px = o.px || 92, col = o.col || B.or, sc = lerp(1.7, 1, p);
  const w = measure(s, {kind: 'A', w: 990, px}) + px * 1.1, h = px * 1.55;
  X.save(); X.translate(cx, cy); X.rotate((o.rot === undefined ? -8 : o.rot) * Math.PI / 180); X.scale(sc, sc); X.globalAlpha *= a * 0.92;
  X.lineWidth = px * 0.09; X.strokeStyle = col; X.beginPath(); X.roundRect(-w / 2, -h / 2, w, h, px * 0.18); X.stroke();
  X.lineWidth = px * 0.035; X.beginPath(); X.roundRect(-w / 2 + px * 0.16, -h / 2 + px * 0.16, w - px * 0.32, h - px * 0.32, px * 0.1); X.stroke();
  txt(s, 0, px * 0.36, {kind: 'A', w: 990, px, col, align: 'center'});
  const r = R(s.length * 31 + 7); X.globalCompositeOperation = 'destination-out';   // the ink's gaps (fixed per word)
  for (let i = 0; i < 70; i++) { X.globalAlpha = 0.5 * r(); X.beginPath(); X.arc((r() - 0.5) * w, (r() - 0.5) * h, 2 + r() * 5, 0, Math.PI * 2); X.fill(); }
  X.restore();
}
/** A redaction bar wiping across (right → left), ink black. */
function redact(t, x, y, w, h, t0, o = {}) {
  const p = E.o5(P(t, t0, o.dur || 0.35)); if (p <= 0) return;
  X.save(); (o.g || X).fillStyle = o.col || B.ink; (o.g || X).fillRect(x + w * (1 - p), y, w * p, h); X.restore();
}

/* ---------------------------------------------------- the marker (signature) ---- */
/** THE ORANGE MARKER: a highlighter stroke drawn behind a word or a line, right → left, with a hand-made
 *  edge. Its signature use: under the key word of every hook (headline's [key]). o: {g, col, a, dur} */
function marker(t, x, y, w, h, t0, o = {}) {
  const g = o.g || X, p = E.io3(P(t, t0, o.dur || 0.4)); if (p <= 0) return;
  const r = R(Math.round(w + h)), xr = x + w, len = w * p;
  g.save(); g.globalAlpha *= (o.a === undefined ? 0.96 : o.a); g.fillStyle = o.col || B.or;
  g.beginPath(); g.moveTo(xr + 6, y + h * 0.1);
  for (let i = 0; i <= 10; i++) g.lineTo(xr - len * i / 10, y + h * 0.06 + (r() - 0.5) * h * 0.12);
  g.lineTo(xr - len - 8 * p, y + h * 0.5);
  for (let i = 10; i >= 0; i--) g.lineTo(xr - len * i / 10, y + h * 0.94 + (r() - 0.5) * h * 0.12);
  g.closePath(); g.fill(); g.restore();
}
/** A hand-drawn orange ring drawn around something (an ellipse that overshoots its start). */
function circleMark(t, cx, cy, rx, ry, t0, o = {}) {
  const p = E.io3(P(t, t0, o.dur || 0.55)); if (p <= 0) return;
  X.save(); X.strokeStyle = o.col || B.or; X.lineWidth = o.lw || 9; X.lineCap = 'round';
  X.beginPath();
  const a0 = -2.2, n = 60;
  for (let i = 0; i <= n * p; i++) {
    const a = a0 + (i / n) * Math.PI * 2.15, wob = 1 + 0.03 * Math.sin(i * 0.7);
    const px = cx + Math.cos(a) * rx * wob, py = cy + Math.sin(a) * ry * wob * (1 + i / n * 0.06);
    i ? X.lineTo(px, py) : X.moveTo(px, py);
  }
  X.stroke(); X.restore();
}
/** A hand-drawn orange arrow along points [[x,y],…], the head arriving last. */
function arrow(t, pts, t0, o = {}) {
  const p = E.io3(P(t, t0, o.dur || 0.5)); if (p <= 0 || pts.length < 2) return;
  const seg = []; let tot = 0;
  for (let i = 1; i < pts.length; i++) { const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); seg.push(l); tot += l; }
  let rem = tot * p, k = 0, hx = pts[0][0], hy = pts[0][1], ang = 0;
  X.save(); X.strokeStyle = o.col || B.or; X.lineWidth = o.lw || 9; X.lineCap = 'round'; X.lineJoin = 'round';
  X.beginPath(); X.moveTo(pts[0][0], pts[0][1]);
  while (k < seg.length && rem > 0) {
    const f = Math.min(1, rem / seg[k]), [x0, y0] = pts[k], [x1, y1] = pts[k + 1];
    hx = lerp(x0, x1, f); hy = lerp(y0, y1, f); ang = Math.atan2(y1 - y0, x1 - x0); X.lineTo(hx, hy); rem -= seg[k]; k++;
  }
  X.stroke();
  if (p > 0.85) { const hl = 34 * E.o3((p - 0.85) / 0.15); X.beginPath(); X.moveTo(hx, hy); X.lineTo(hx - Math.cos(ang - 0.5) * hl, hy - Math.sin(ang - 0.5) * hl); X.moveTo(hx, hy); X.lineTo(hx - Math.cos(ang + 0.5) * hl, hy - Math.sin(ang + 0.5) * hl); X.stroke(); }
  X.restore();
}

/* ------------------------------------------------------------- type moves ---- */
/** The hook / a statement: Persian lines in Anjoman, each rising from a mask; [key] words get THE ORANGE
 *  MARKER behind them (dark ink letters on it). o: {px, w, lh, align ('right'|'center'), col} */
function headline(t, lines, x, y, t0, o = {}) {
  const px = o.px || 120, lh = o.lh || px * 1.3, wt = o.w || 990;
  lines.forEach((ln, i) => {
    const ti = t0 + i * 0.12, p = E.o5(P(t, ti, 0.55)), a = E.o3(P(t, ti, 0.25)); if (a <= 0) return;
    const yy = y + i * lh;
    X.save(); X.beginPath(); X.rect(0, yy - lh * 0.95, W, lh * 1.2); X.clip();
    keyLine(t, ln, x, yy + (1 - p) * lh * 0.8, {px, w: wt, a, align: o.align, col: o.col, t0: ti + 0.25});
    X.restore();
    TEXTS.add(ln.replace(/[\[\]]/g, ''));
  });
}
function keyLine(t, s, x, y, o) {
  const parts = endStop(s).split(/(\[[^\]]+\])/).filter(Boolean), px = o.px;
  const ws = parts.map(q => measure(q.replace(/[\[\]]/g, ''), {kind: 'A', px, w: o.w}) + (q.startsWith('[') ? px * 0.36 : 0));
  const total = ws.reduce((s, v) => s + v, 0);
  let cx = o.align === 'center' ? W / 2 + total / 2 : x;
  parts.forEach((q, i) => {
    if (q.startsWith('[')) {
      marker(t, cx - ws[i], y - px * 0.86, ws[i], px * 1.12, o.t0 || 0, {a: o.a});
      txt(q.slice(1, -1), cx - px * 0.18, y, {kind: 'A', px, w: o.w, col: B.nv, a: o.a});
    } else txt(q, cx, y, {kind: 'A', px, w: o.w, col: o.col || B.cr, a: o.a});
    cx -= ws[i];
  });
}
/** Words that SLAM in one by one (scale 1.35 → 1 in 0.22 s, a two-frame motion trail while moving). Centre-
 *  aligned lines. words: [{w, at}] or a string (then o.step apart from t0). o: {px, cy, col, keys:[…]} */
function slam(t, words, t0, o = {}) {
  const list = typeof words === 'string' ? endStop(words).split(/\s+/).map((w, i) => ({w, at: t0 + i * (o.step || 0.2)})) : words;
  const px = o.px || 130, maxW = o.maxW || 940, lh = px * 1.25, sp = measure(' ', {kind: 'A', px, w: 990});
  const lines = [[]]; let lw = 0;
  list.forEach(it => { const w = measure(it.w, {kind: 'A', px, w: 990}); if (lw && lw + sp + w > maxW) { lines.push([]); lw = 0; } lines[lines.length - 1].push({...it, ww: w}); lw += (lw ? sp : 0) + w; });
  const cy = (o.cy || H / 2) - (lines.length - 1) * lh / 2;
  lines.forEach((ln, li) => {
    const tw = ln.reduce((s, v) => s + v.ww, 0) + sp * (ln.length - 1); let x = W / 2 + tw / 2;
    ln.forEach(it => {
      const p = E.o3(P(t, it.at, 0.22)), a = E.o3(P(t, it.at, 0.08));
      if (a > 0) {
        const s = lerp(1.35, 1, p), key = (o.keys || []).includes(it.w), cx = x - it.ww / 2, y = cy + li * lh;
        for (let gh = (p < 1 ? 2 : 0); gh >= 0; gh--) {   // the trail: only while it moves
          const sg = lerp(s, 1, -gh * 0.12);
          X.save(); X.translate(cx, y); X.scale(sg, sg);
          txt(it.w, 0, px * 0.35, {kind: 'A', w: 990, px, col: key ? B.or : (o.col || B.cr), a: a * (gh ? 0.18 : 1), align: 'center'});
          X.restore();
        }
      }
      x -= it.ww + sp;
    });
  });
}
/** A typewriter line (Persian is revealed by a moving mask, right → left, so the letters stay joined), a
 *  caret riding its edge. o: {px, w, kind, col, dur, g} */
function typeLine(t, s, x, y, t0, o = {}) {
  const g = o.g || X, px = o.px || 46, kind = o.kind || 'R', wd = measure(s, {g, kind, px, w: o.w || 500});
  const p = P(t, t0, o.dur || Math.max(0.5, wd / 900)); if (p <= 0) return;
  const shown = wd * p, ltr = kind === 'M';
  g.save(); g.beginPath();
  if (ltr) g.rect(x, y - px * 1.2, shown, px * 1.6); else g.rect(x - shown, y - px * 1.2, shown, px * 1.6);
  g.clip(); txt(s, x, y, {g, kind, px, w: o.w || 500, col: o.col || B.cr, align: ltr ? 'left' : 'right'}); g.restore();
  if (p < 1 || Math.floor(t * 2.4) % 2 === 0) { g.save(); g.fillStyle = o.caret || B.or; g.fillRect(ltr ? x + shown + 4 : x - shown - 10, y - px * 0.85, 5, px * 1.0); g.restore(); }
}
/** The chapter tab: an orange square with «۰۱» and the Persian label in Anjoman; the rule under it draws in.
 *  Top-right, y ≈ 440 (under the HUD). */
function kicker(t, num, label, t0, o = {}) {
  const a = E.o3(P(t, t0, 0.3)) * (o.out ? 1 - E.o3(P(t, o.out, 0.3)) : 1); if (a <= 0) return;
  const x = o.x || 1010, y = o.y || 450, dx = (1 - E.o5(P(t, t0, 0.5))) * 50;
  const n = fa(String(num).padStart(2, '0'));
  X.save(); X.globalAlpha *= a; X.fillStyle = B.or; X.beginPath(); X.roundRect(x - 78 - dx, y - 58, 78, 78, 14); X.fill(); X.restore();
  txt(n, x - 39 - dx, y - 1, {kind: 'A', w: 990, px: 46, col: B.nv, a, align: 'center'});
  const lw = txt(label, x - 104 - dx, y - 2, {kind: 'A', w: 900, px: 50, col: B.cr, a});
  X.save(); X.globalAlpha *= a; X.fillStyle = rgba(B.cr, 0.35); const u = (lw + 104) * E.o5(P(t, t0 + 0.12, 0.5)); X.fillRect(x - u, y + 34, u, 3); X.restore();
}
/** A documentary lower third for a person or a place: the orange bar grows, the name (Anjoman) and the role
 *  (Ravagh) rise in. Right-aligned at y (default 1240, above the caption band). */
function lowerThird(t, name, role, t0, o = {}) {
  const y = o.y || 1250, x = o.x || 1010, a = E.o3(P(t, t0, 0.3)) * (o.out ? 1 - E.o3(P(t, o.out, 0.3)) : 1); if (a <= 0) return;
  const p = E.o5(P(t, t0, 0.5)), nw = measure(name, {kind: 'A', w: 950, px: 66}) + 60;
  X.save(); X.globalAlpha *= a; X.fillStyle = rgba(B.nv, 0.82); X.fillRect(x - nw * p, y - 70, nw * p, 96);
  X.fillStyle = B.or; X.fillRect(x - 10, y - 70, 10, 96 + (role ? 64 : 0)); X.restore();
  X.save(); X.beginPath(); X.rect(0, y - 70, W, 96); X.clip(); txt(name, x - 32, y + (1 - p) * 60, {kind: 'A', w: 950, px: 66, col: B.cr, a}); X.restore();
  if (role) txt(role, x - 32, y + 70, {px: 40, w: 500, col: B.orG, a: a * E.o3(P(t, t0 + 0.2, 0.3))});
}
/** The place-and-time card of a documentary: «۱۹۹۴ · نیویورک» set big, the year in the orange, top-left. */
function dateline(t, year, place, t0, o = {}) {
  const a = E.o3(P(t, t0, 0.35)) * (o.out ? 1 - E.o3(P(t, o.out, 0.3)) : 1); if (a <= 0) return;
  const x = o.x || 70, y = o.y || 470, dy = (1 - E.o5(P(t, t0, 0.6))) * 30;
  const yw = txt(fa(year), x, y + dy, {kind: 'A', w: 990, px: o.px || 120, col: B.or, a, align: 'left', rtl: true});
  if (place) txt(place, x, y + 70 + dy, {px: 44, w: 600, col: B.cr, a, align: 'left'});
  return yw;
}

/* ----------------------------------------------------------- the numbers ---- */
/** The counter: every digit rolls and lands EXACTLY on the value at t0+dur (hold it ≥ 1.2 s after).
 *  o: {px, w, kind ('A' default), col, align, prefix, suffix, dec, latin (Latin digits, e.g. «$65B»),
 *      unit (a Persian word set under it), change (▲/▼ + the meaning colour)} */
function counter(t, value, x, y, t0, dur, o = {}) {
  const p = E.o5(P(t, t0, dur)), dec = o.dec || 0;
  const v = value * p;   // no leading zeros while it rolls: the number grows into its width
  let s = Math.abs(v).toFixed(dec);
  if (o.sep !== false) { const [i, d] = s.split('.'); s = i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (d ? '.' + d : ''); }
  s = (value < 0 ? '−' : (o.plus && value > 0 ? '+' : '')) + (o.prefix || '') + s + (o.suffix || '');
  const px = o.px || 200, al = o.align || 'center';
  let col = o.col || B.cr;
  if (o.change) { col = value >= 0 ? B.up : B.dn; s = (value >= 0 ? '▲ ' : '▼ ') + s; }
  const str = o.latin ? s : fa(s);
  const wd = txt(str, x, y, {kind: o.kind || 'A', w: o.w || 990, px, col, align: al, rtl: !o.latin});
  if (o.unit) txt(o.unit, al === 'center' ? x : al === 'right' ? x : x + wd, y + px * 0.62, {kind: 'R', w: 700, px: px * 0.3, col: o.unitCol || B.orG, align: al === 'left' ? 'left' : al, a: E.o3(P(t, t0 + dur * 0.6, 0.3))});
  return wd;
}
/** A meaning chip: «▲ +12.4%» green / «▼ −3.1%» red, mono. */
function changeChip(t, pct, x, y, t0, o = {}) {
  const a = E.o3(P(t, t0, 0.3)); if (a <= 0) return;
  const up = pct > 0, col = pct === 0 ? B.flat : up ? B.up : B.dn, px = o.px || 40;
  const s = `${up ? '▲' : pct < 0 ? '▼' : '■'} ${up ? '+' : pct < 0 ? '−' : ''}${Math.abs(pct).toFixed(o.dec === undefined ? 1 : o.dec)}%`;
  const w = measure(s, {kind: 'M', w: 600, px}) + px * 1.1, h = px * 1.7;
  const x0 = o.align === 'right' ? x - w : o.align === 'center' ? x - w / 2 : x;
  X.save(); X.globalAlpha *= a; X.beginPath(); X.roundRect(x0, y - h / 2, w, h, h / 2); X.fillStyle = rgba(col, 0.16); X.fill(); X.lineWidth = 2; X.strokeStyle = rgba(col, 0.8); X.stroke(); X.restore();
  txt(s, x0 + px * 0.55, y + px * 0.36, {kind: 'M', w: 600, px, col, a});
}
/** Comparison bars (Persian labels right, values left): the hero row (o.hero index) in orange, the rest in
 *  cream at 45 %; they grow staggered from the right. rows: [{label, v, show}] (show = the text for the value). */
function bars(t, rows, x, y, w, rowH, t0, o = {}) {
  const mx = Math.max(...rows.map(r => r.v)) || 1, lw = o.labelW || 300;
  rows.forEach((r, i) => {
    const p = E.io3(P(t, t0 + i * 0.14, 0.7)), a = E.o3(P(t, t0 + i * 0.14, 0.2)); if (a <= 0) return;
    const yy = y + i * rowH, bw = (w - lw - 40) * (r.v / mx) * p, hero = i === o.hero;
    txt(r.label, x + w, yy + rowH * 0.42, {px: o.px || 44, w: 700, col: hero ? B.or : B.cr, a, maxW: lw - 10});
    X.save(); X.globalAlpha *= a; X.fillStyle = hero ? B.or : rgba(B.cr, 0.45);
    X.beginPath(); X.roundRect(x + w - lw - bw, yy + rowH * 0.12, Math.max(4, bw), rowH * 0.5, 10); X.fill(); X.restore();
    if (p > 0.5 && r.show) {   // the value: beside a short bar, inside a long one (never out of the frame)
      const vpx = (o.px || 44) * 0.95, vw = measure(r.show, {kind: 'A', w: 900, px: vpx}), inside = bw > vw + 60;
      txt(r.show, inside ? x + w - lw - bw + 24 : x + w - lw - bw - 18, yy + rowH * 0.36 + vpx * 0.36,
        {kind: 'A', w: 900, px: vpx, col: inside ? (hero ? B.nv : B.nv) : (hero ? B.or : B.cr), a: E.o3((p - 0.5) * 2), align: inside ? 'left' : 'right'});
    }
  });
}
/** A unit grid: n of total squares light up in orange (scale made visible: «۱ از ۱۰۰۰»). cols squares a row. */
function dotGrid(t, n, total, x, y, w, t0, dur, o = {}) {
  const cols = o.cols || Math.ceil(Math.sqrt(total * w / (o.h || w))), cell = w / cols, gap = Math.max(1, cell * 0.16);
  const lit = Math.round(n * E.io3(P(t, t0, dur))), a = E.o3(P(t, t0 - 0.3, 0.3)); if (a <= 0) return;
  X.save(); X.globalAlpha *= a;
  for (let i = 0; i < total; i++) {
    const cx = x + w - (i % cols + 1) * cell, cy = y + Math.floor(i / cols) * cell;
    X.fillStyle = i < lit ? B.or : rgba(B.cr, 0.12); X.fillRect(cx + gap / 2, cy + gap / 2, cell - gap, cell - gap);
  }
  X.restore();
}
/** A price/value history line (real numbers from qc/facts.json), drawn progressively, the orange head
 *  riding it; events pinned on it: o.marks [{i, label}] (an orange pin + a Persian label when reached). */
function lineChart(t, series, x, y, w, h, t0, dur, o = {}) {
  const n = series.length; if (n < 2) return;
  const lo = Math.min(...series), hi = Math.max(...series), pad = (hi - lo) * 0.08 || 1;
  const Y = v => y + h - (v - lo + pad) / (hi - lo + 2 * pad) * h, Xx = i => x + i / (n - 1) * w;
  const p = E.io3(P(t, t0, dur)), m = Math.max(1, p * (n - 1));
  X.save(); X.strokeStyle = B.hair; X.lineWidth = 1.5;
  for (let k = 0; k <= 4; k++) { const yy = y + h * k / 4; X.beginPath(); X.moveTo(x, yy); X.lineTo(x + w, yy); X.stroke(); }
  const path = () => { X.beginPath(); X.moveTo(Xx(0), Y(series[0])); for (let i = 1; i <= Math.floor(m); i++) X.lineTo(Xx(i), Y(series[i])); const f = m - Math.floor(m), i0 = Math.floor(m); if (i0 < n - 1) X.lineTo(lerp(Xx(i0), Xx(i0 + 1), f), lerp(Y(series[i0]), Y(series[i0 + 1]), f)); };
  const i0 = Math.min(n - 2, Math.floor(m)), hx = Math.min(x + w, Xx(m)), hy = lerp(Y(series[i0]), Y(series[i0 + 1]), m - i0);
  path(); X.lineTo(hx, y + h); X.lineTo(x, y + h); X.closePath();
  const ag = X.createLinearGradient(0, y, 0, y + h); ag.addColorStop(0, rgba(B.or, 0.22)); ag.addColorStop(1, rgba(B.or, 0)); X.fillStyle = ag; X.fill();
  path(); X.strokeStyle = B.cr; X.lineWidth = 6; X.lineJoin = 'round'; X.lineCap = 'round'; X.stroke();
  (o.marks || []).forEach((mk, k) => {
    if (m < mk.i) return; const q = E.land(P(t, t0 + dur * mk.i / (n - 1), 0.35)), mx = Xx(mk.i), my = Y(series[mk.i]);
    X.save(); X.globalAlpha *= clamp(q); X.fillStyle = B.or; X.beginPath(); X.arc(mx, my, 14 * q, 0, Math.PI * 2); X.fill();
    X.strokeStyle = rgba(B.or, 0.6); X.lineWidth = 2; X.setLineDash([8, 8]); X.beginPath(); X.moveTo(mx, my - 20); X.lineTo(mx, my - 110 - (k % 2) * 70); X.stroke(); X.restore();
    txt(mk.label, mx + (mx > x + w / 2 ? 0 : 0), my - 124 - (k % 2) * 70, {px: 38, w: 800, col: B.cr, a: clamp(q), align: mx > x + w * 0.6 ? 'right' : mx < x + w * 0.4 ? 'left' : 'center'});
  });
  X.beginPath(); X.arc(hx, hy, 16, 0, Math.PI * 2); X.fillStyle = B.or; X.fill();
  X.beginPath(); X.arc(hx, hy, 7, 0, Math.PI * 2); X.fillStyle = B.cr; X.fill();
  X.restore();
  return {hx, hy};
}
/** The timeline: a ruler (right → left = earlier → later, as Persian reads), the cursor travels; each item
 *  ({year, label}) pops as it is reached; the current one in orange. x..x+w at y, over t0..t0+dur. */
function timeline(t, items, x, y, w, t0, dur, o = {}) {
  const a = E.o3(P(t, t0 - 0.2, 0.3)); if (a <= 0) return;
  const n = items.length, p = E.io3(P(t, t0, dur)), px = (i) => x + w - (n === 1 ? 0.5 : i / (n - 1)) * w;
  X.save(); X.globalAlpha *= a; X.strokeStyle = rgba(B.cr, 0.3); X.lineWidth = 4; X.beginPath(); X.moveTo(x, y); X.lineTo(x + w, y); X.stroke();
  for (let k = 0; k <= 40; k++) { const tx = x + w * k / 40; X.fillStyle = rgba(B.cr, k % 5 ? 0.18 : 0.4); X.fillRect(tx - 1, y - (k % 5 ? 10 : 20), 2, k % 5 ? 20 : 40); }
  X.strokeStyle = B.or; X.lineWidth = 6; X.beginPath(); X.moveTo(x + w, y); X.lineTo(x + w - w * p, y); X.stroke(); X.restore();
  const cur = p * (n - 1);
  items.forEach((it, i) => {
    const q = E.land(P(cur, i - 0.15, 0.3)); if (q <= 0) return;
    const ix = px(i), on = Math.abs(cur - i) < 0.5, up = i % 2 === 0;
    X.save(); X.globalAlpha *= clamp(q); X.fillStyle = on ? B.or : B.cr; X.beginPath(); X.arc(ix, y, on ? 18 : 12, 0, Math.PI * 2); X.fill(); X.restore();
    const ypx = on ? 84 : 64, yw = measure(fa(it.year), {kind: 'A', w: 990, px: ypx});
    const lw = it.label ? Math.min(measure(it.label, {px: 44, w: 800}), 420) : 0, half = Math.max(yw, lw) / 2;
    const lx = clamp(ix, 50 + half, W - 50 - half);   // a label at the ruler's end never leaves the frame
    txt(fa(it.year), lx, up ? y - 60 : y + 110, {kind: 'A', w: 990, px: ypx, col: on ? B.or : B.cr, a: clamp(q), align: 'center'});
    if (it.label) txt(it.label, lx, up ? y - 150 : y + 180, {px: 44, w: 800, col: B.cr, a: clamp(q) * (on ? 1 : 0.7), align: 'center', maxW: 420});
  });
}
/** A quote: the big orange «, the lines rising in Anjoman, the attribution in Ravagh. */
function quote(t, lines, who, x, y, t0, o = {}) {
  const a = E.o3(P(t, t0, 0.3)); if (a <= 0) return;
  txt('«', x, y - 40, {kind: 'A', w: 990, px: 260, col: B.or, a: a * 0.95});
  headline(t, lines, x, y + 150, t0 + 0.15, {px: o.px || 84, w: 900});
  if (who) txt('— ' + who, x, y + 150 + lines.length * (o.px || 84) * 1.3 + 30, {px: 42, w: 600, col: B.orG, a: E.o3(P(t, t0 + 0.5, 0.3))});
}
/** Pins and routes on a map plate (the map is a picture in assets/, drawn by plate() before): pins [{x,y,
 *  label, at}] drop and pulse; arcs [{from:[x,y], to:[x,y], at, dur}] draw as orange great-circle-like curves. */
function mapMarks(t, pins, arcs) {
  (arcs || []).forEach(r => {
    const p = E.io3(P(t, r.at, r.dur || 0.9)); if (p <= 0) return;
    const [x0, y0] = r.from, [x1, y1] = r.to, mx = (x0 + x1) / 2, my = Math.min(y0, y1) - Math.hypot(x1 - x0, y1 - y0) * 0.35;
    X.save(); X.strokeStyle = B.or; X.lineWidth = 6; X.lineCap = 'round'; X.setLineDash([2, 14]); X.beginPath(); X.moveTo(x0, y0);
    const N = 40; for (let i = 1; i <= N * p; i++) { const u = i / N; X.lineTo((1 - u) * (1 - u) * x0 + 2 * (1 - u) * u * mx + u * u * x1, (1 - u) * (1 - u) * y0 + 2 * (1 - u) * u * my + u * u * y1); }
    X.stroke(); X.restore();
  });
  (pins || []).forEach(pn => {
    const q = E.land(P(t, pn.at, 0.4)); if (q <= 0) return;
    const pulse = (t - pn.at) % 1.6 / 1.6;
    X.save(); X.globalAlpha *= clamp(q) * (1 - pulse); X.strokeStyle = B.or; X.lineWidth = 3; X.beginPath(); X.arc(pn.x, pn.y, 18 + pulse * 46, 0, Math.PI * 2); X.stroke(); X.restore();
    X.save(); X.globalAlpha *= clamp(q); X.fillStyle = B.or; X.beginPath(); X.arc(pn.x, pn.y - (1 - q) * 60, 16, 0, Math.PI * 2); X.fill(); X.restore();
    if (pn.label) txt(pn.label, pn.x, pn.y - 40, {px: 40, w: 800, col: B.cr, a: clamp(q), align: 'center', shadow: 12});
  });
}
/** Versus: the frame split diagonally — picture A (right) and B (left) with an orange seam; labels on each. */
function versus(t, srcA, srcB, labA, labB, t0, o = {}) {
  const p = E.io5(P(t, t0, 0.7)), q = o.p || 0;
  const sx = lerp(W * 1.2, W * 0.5, p);
  X.save(); X.beginPath(); X.moveTo(sx + 160, 0); X.lineTo(W, 0); X.lineTo(W, H); X.lineTo(sx - 160, H); X.closePath(); X.clip(); plate(srcA, {p: q, tone: o.tone}); X.restore();
  X.save(); X.beginPath(); X.moveTo(0, 0); X.lineTo(sx + 160, 0); X.lineTo(sx - 160, H); X.lineTo(0, H); X.closePath(); X.clip(); plate(srcB, {p: q, tone: o.tone, pan: [[0.4, 0.5], [0.55, 0.5]]}); X.restore();
  X.save(); X.strokeStyle = B.or; X.lineWidth = 12; X.beginPath(); X.moveTo(sx + 160, 0); X.lineTo(sx - 160, H); X.stroke(); X.restore();
  const a = E.o3(P(t, t0 + 0.5, 0.3));
  if (labA) txt(labA, 1010, 560, {kind: 'A', w: 990, px: 76, col: B.cr, a, shadow: 18});
  if (labB) txt(labB, 70, 1240, {kind: 'A', w: 990, px: 76, col: B.cr, a, align: 'left', shadow: 18});
  const vs = E.land(P(t, t0 + 0.55, 0.35));
  if (vs > 0) { X.save(); X.translate(W / 2, H / 2); X.scale(vs, vs); X.fillStyle = B.or; X.beginPath(); X.arc(0, 0, 74, 0, Math.PI * 2); X.fill(); X.restore(); txt('VS', W / 2, H / 2 + 22, {kind: 'A', w: 990, px: 64, col: B.nv, a: clamp(vs), align: 'center', rtl: false}); }
}

/* ------------------------------------------------------- HUD, the mark ---- */
let HUD = null;
/** The file bar (the brand's constant: every frame but the first 0.5 s and the end slate). y 232–300, under
 *  Instagram's top bar: the round mark (orange ring), the wordmark «bitmart», «FILE 012» in mono, the file's
 *  short Persian title on the right; the reel's progress as an orange hairline. */
function hud(t, a = 1) {
  if (!HUD || a <= 0) return;
  const y = 268;
  X.save(); X.globalAlpha *= a;
  const g = X.createLinearGradient(0, 226, 0, 306); g.addColorStop(0, rgba(B.deep, 0.0)); g.addColorStop(0.3, rgba(B.deep, 0.62)); g.addColorStop(1, rgba(B.deep, 0.62));
  X.fillStyle = g; X.fillRect(0, 226, W, 78);
  X.fillStyle = B.hair; X.fillRect(0, 303, W, 2);
  X.fillStyle = B.or; X.fillRect(W - W * clamp(t / (HUD.end || 60)), 303, W * clamp(t / (HUD.end || 60)), 3);   // RTL progress
  X.restore();
  let x = 60;
  if (IMG.__mark) { X.save(); X.globalAlpha *= a; X.beginPath(); X.arc(x + 21, y, 21, 0, Math.PI * 2); X.clip(); X.drawImage(IMG.__mark, x, y - 21, 42, 42); X.restore();
    X.save(); X.globalAlpha *= a; X.strokeStyle = B.or; X.lineWidth = 3; X.beginPath(); X.arc(x + 21, y, 23, 0, Math.PI * 2); X.stroke(); X.restore(); x += 58; }
  x += wordmark(x, y + 13, 40, a) + 24;
  txt(`FILE ${String(HUD.file ?? 1).padStart(3, '0')}`, x, y + 9, {kind: 'M', w: 600, px: 24, col: B.orG, a, track: 2});
  if (HUD.title) txt(HUD.title, 1020, y + 13, {kind: 'R', w: 700, px: 34, col: B.cr, a: a * 0.9, maxW: 420});
}
/** The wordmark «bitmart» (Anjoman Max Black, lower case, the dot of the i in orange) → its width. */
function wordmark(x, y, px, a = 1, o = {}) {
  const w = txt('bitmart', x, y, {kind: 'A', w: 990, px, col: o.col || B.cr, a, rtl: false, align: o.align || 'left'});
  return w;
}
/** The lockup: the page's round photo (an orange ring) + «bitmart» + «بهنام جلالی». Centre-aligned at cx. */
function lockup(cx, cy, size, a = 1, o = {}) {
  X.save(); X.globalAlpha *= a;
  if (IMG.__mark) { X.beginPath(); X.arc(cx, cy, size / 2, 0, Math.PI * 2); X.save(); X.clip(); X.drawImage(IMG.__mark, cx - size / 2, cy - size / 2, size, size); X.restore(); }
  X.lineWidth = Math.max(4, size * 0.04); X.strokeStyle = B.or; X.beginPath(); X.arc(cx, cy, size / 2 + X.lineWidth, 0, Math.PI * 2); X.stroke();
  X.restore();
  const px = size * 0.46, y = cy + size / 2 + px * 1.3, w = measure('bitmart', {kind: 'A', w: 990, px, rtl: false});
  wordmark(cx - w / 2, y, px, a);
  if (o.name !== false) txt('بهنام جلالی', cx, y + px * 0.95, {kind: 'R', px: px * 0.48, w: 500, col: B.mu, a, align: 'center'});
}
/** The end slate (the last ≥ 3 s): the lockup, then EITHER the ask with the comment word on the orange marker
 *  (end: {word}) OR the reel's own closing question / follow line (end: {line, sub}); @bitmart. */
function endSlate(t, t0, word, o = {}) {
  const a = E.o3(P(t, t0, 0.5)); if (a <= 0) return;
  X.save(); X.globalAlpha *= a; ground(t, {light: 0.5, lx: 540, ly: 700, ledger: 0.6}); X.restore();
  const p = E.land(P(t, t0 + 0.1, 0.7));
  lockup(W / 2, 600 - (1 - p) * 50, 240, a);
  if (word) {
    const q = E.o3(P(t, t0 + 0.45, 0.4));
    txt(o.ask || 'کلمه‌ی زیر رو کامنت کن', W / 2, 1150, {px: 52, w: 700, col: B.cr, a: q, align: 'center'});
    const ww = measure(word, {kind: 'A', px: 110, w: 990}) + 120;
    marker(t, W / 2 - ww / 2, 1195, ww, 160, t0 + 0.5, {a: q});
    txt(word, W / 2, 1315, {kind: 'A', px: 110, w: 990, col: B.nv, a: q, align: 'center'});
    txt(o.then || 'تا ادامه‌ی پرونده رو برات بفرستم', W / 2, 1450, {px: 44, w: 500, col: B.mu, a: q, align: 'center'});
  } else if (o.line) {   // no comment word (the warm-up weeks): the reel's own question / follow line
    const q = E.o3(P(t, t0 + 0.45, 0.4));
    wrap(o.line, 900, {kind: 'A', px: 74, w: 950}).forEach((ln, i) => txt(ln, W / 2, 1180 + i * 96, {kind: 'A', px: 74, w: 950, col: B.cr, a: q, align: 'center'}));
    if (o.sub) txt(o.sub, W / 2, 1450, {px: 44, w: 500, col: B.orG, a: q, align: 'center'});
  }
  txt('@bitmart', W / 2, 1560, {kind: 'M', w: 600, px: 48, col: B.or, a: E.o3(P(t, t0 + 0.7, 0.4)), align: 'center', track: 2});
}

/* --------------------------------------------------------------- captions ---- */
let CAPS = [];
/** Captions from the word times: chunks of ≤ 5 words / ≤ 2.2 s, never across a sentence. keys: words in orange. */
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
/** The caption block (y ≈ 1400–1530): Ravagh ExtraBold, words arrive one by one (rise 22 px, 0.16 s), the
 *  newest cream, the earlier at 78 %, key words in orange; a soft ink plate behind. */
function captions(t, o = {}) {
  const c = CAPS.find(c => t >= c.s - 0.05 && t < c.e2); if (!c) return;
  const px = o.px || 66, y = o.y || 1480, out = 1 - E.o3(P(t, c.e2 - 0.16, 0.16));
  const ws = c.words.map(w => endStop(w.w)), sp = measure(' ', {px, w: 800});
  const widths = ws.map(w => measure(w, {px, w: 800})), total = widths.reduce((s, v) => s + v, 0) + sp * (ws.length - 1);
  const scale = Math.min(1, 940 / total);
  let x = W / 2 + total * scale / 2;
  X.save(); X.globalAlpha *= out;
  const pl = X.createLinearGradient(0, y - 150, 0, y + 90); pl.addColorStop(0, rgba(B.deep, 0)); pl.addColorStop(0.35, rgba(B.deep, 0.78)); pl.addColorStop(0.75, rgba(B.deep, 0.78)); pl.addColorStop(1, rgba(B.deep, 0));
  X.fillStyle = pl; X.fillRect(0, y - 150, W, 240);
  c.words.forEach((w, i) => {
    const p = E.o5(P(t, w.s - 0.06, 0.16)), a = E.o3(P(t, w.s - 0.06, 0.1));
    if (a > 0) { const newest = i === c.words.length - 1 || t < c.words[i + 1].s; txt(ws[i], x, y + (1 - p) * 22, {px: px * scale, w: 800, col: w.k ? B.or : B.cr, a: a * (newest || w.k ? 1 : 0.78)}); }
    x -= (widths[i] + sp) * scale;
  });
  X.restore();
}

/* ------------------------------------------------------------ transitions ---- */
/** The brand's transitions (0.46 s, centred on the cut). Each paints shot B over A.
 *  swipe: an orange marker band sweeps right → left, B behind it · shutter: five orange slabs close over A
 *  and open on B · zoom: A pushes through to 1.4× and fades as B settles from 0.88× (a brief trail) · page: A
 *  turns away like a page (perspective) over B · cut: none. */
function transit(kind, q, drawA, drawB) {
  const k = E.io3(clamp(q));
  if (kind === 'cut' || k <= 0) { (k < 1 && kind !== 'cut' ? drawA : drawB)(); return; }
  if (k >= 1) { drawB(); return; }
  if (kind === 'swipe') {
    drawA();
    const d = (W + 600) * k;
    X.save(); X.beginPath(); X.moveTo(W, 0); X.lineTo(W - d, 0); X.lineTo(W - d + 300, H); X.lineTo(W, H); X.closePath(); X.clip(); drawB(); X.restore();
    X.save(); X.fillStyle = B.or; X.beginPath(); X.moveTo(W - d, 0); X.lineTo(W - d - 90, 0); X.lineTo(W - d - 90 + 300, H); X.lineTo(W - d + 300, H); X.closePath(); X.fill(); X.restore();
  } else if (kind === 'shutter') {
    const close = clamp(q * 2), open = clamp(q * 2 - 1), n = 5, sw = W / n;
    (q < 0.5 ? drawA : drawB)();
    X.save(); X.fillStyle = B.or;
    for (let i = 0; i < n; i++) {
      const st = i * 0.08, c = E.io3(clamp((close - st) / (1 - 0.32))), o2 = E.io3(clamp((open - st) / (1 - 0.32)));
      const hgt = H * (q < 0.5 ? c : 1 - o2);
      X.fillRect(W - (i + 1) * sw - 1, i % 2 ? H - hgt : 0, sw + 2, hgt);
    }
    X.restore();
  } else if (kind === 'zoom') {
    X.save(); X.translate(W / 2, H / 2); X.scale(lerp(1, 1.4, k), lerp(1, 1.4, k)); X.translate(-W / 2, -H / 2); X.globalAlpha = 1; drawA(); X.restore();
    X.save(); X.globalAlpha = E.o3(clamp(k * 1.6 - 0.3)); X.translate(W / 2, H / 2); const s = lerp(0.88, 1, k); X.scale(s, s); X.translate(-W / 2, -H / 2); drawB(); X.restore();
  } else if (kind === 'page') {
    const ry = -92 * k, [c, g] = offscreen('__page', W, H);
    // A is drawn by its own code on X: draw it, copy the canvas into the card, then B under the turning card
    drawA(); g.drawImage(C, 0, 0); drawB();
    X.save();
    const f = 1700, rad = ry * Math.PI / 180;
    for (let u = 0; u < W; u += 2) {
      const xl = u, z = xl * Math.sin(-rad), qq = f / (f + z), xs = xl * Math.cos(rad) * qq, hh = H * qq;
      X.globalAlpha = 1; X.drawImage(c, u, 0, 2, H, xs, H / 2 - hh / 2, 2 * Math.cos(rad) * qq + 0.6, hh);
    }
    X.fillStyle = rgba(B.deep, 0.35 * k); X.fillRect(0, 0, W, H);
    X.restore();
  } else { drawB(); }
}

/* ---------------------------------------------------------------- camera ---- */
/** The rig: a slow push (s0→s1) and a drift on a shot, around (cx,cy). Apply inside a shot's draw. */
function rig(p, o = {}) {
  const s = lerp(o.s0 || 1, o.s1 || 1.05, E.io3(p)), cx = o.cx || W / 2, cy = o.cy || H / 2;
  const dx = lerp(o.dx0 || 0, o.dx1 || 0, E.io3(p)), dy = lerp(o.dy0 || 0, o.dy1 || 0, E.io3(p));
  const rot = lerp(o.r0 || 0, o.r1 || 0, E.io3(p)) * Math.PI / 180;
  X.translate(cx + dx, cy + dy); X.rotate(rot); X.scale(s, s); X.translate(-cx, -cy);
}

/* ----------------------------------------------------------------- the reel ---- */
let REEL = null;
function reel(cfg) { REEL = cfg; CAPS = cfg.caps || []; HUD = Object.assign({end: cfg.END}, cfg.hud || {}); window.END = cfg.END; }
function drawShot(s, t) { X.save(); s.draw(t, clamp((t - s.a) / Math.max(0.01, s.b - s.a)), s); X.restore(); }
function frame(t) {
  X.setTransform(1, 0, 0, 1, 0, 0); X.globalAlpha = 1; X.fillStyle = B.nv; X.fillRect(0, 0, W, H);
  const S = REEL.shots, TR = 0.46;
  let i = S.findIndex(s => t >= s.a && t < s.b); if (i < 0) i = t < S[0].a ? 0 : S.length - 1;
  const s = S[i], nx = S[i + 1];
  if (nx && t > s.b - TR / 2 && (nx.tr || 'swipe') !== 'cut') transit(nx.tr || 'swipe', (t - (s.b - TR / 2)) / TR, () => drawShot(s, t), () => drawShot(nx, t));
  else if (i > 0 && t < s.a + TR / 2 && (s.tr || 'swipe') !== 'cut') transit(s.tr || 'swipe', (t - (s.a - TR / 2)) / TR, () => drawShot(S[i - 1], t), () => drawShot(s, t));
  else drawShot(s, t);
  const endAt = REEL.end ? REEL.end.at : 1e9;
  const hudA = E.o3(P(t, REEL.hudIn === undefined ? 0.5 : REEL.hudIn, 0.4)) * (1 - E.o3(P(t, endAt - 0.2, 0.3)));
  hud(t, hudA);
  if (t < endAt) captions(t, REEL.capOpt || {});
  if (REEL.end) endSlate(t, endAt, REEL.end.word, REEL.end);
  dither();
  return C.toDataURL('image/jpeg', 0.95);
}
window.frame = frame;
window.STORY = {B, E, P, R, clamp, lerp, rgba, fa, iso, txt, measure, wrap, ground, vignette, plate, toned, parallax, cutout, persp,
  docBody, photoIn, doc, clipping, stamp, redact, marker, circleMark, arrow, headline, keyLine, slam, typeLine, kicker, lowerThird,
  dateline, counter, changeChip, bars, dotGrid, lineChart, timeline, quote, mapMarks, versus, hud, wordmark, lockup, endSlate,
  capsFromWords, captions, transit, rig, reel, IMG, TEXTS, W, H};
window.STORY_TEXTS = () => Array.from(TEXTS);
