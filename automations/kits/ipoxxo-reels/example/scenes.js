/* The example reel (2026-11-18, v2 with its ending; published on @ipoxxo.vpn on the owner's word):
   «عمیق‌ترین چاه دنیا» — the Kola Superdeep Borehole.
   Look of the example: zoom-through transitions (family 2), crane up/down reveals (camera 4), amber support
   accent (4) for heat and rust, dark cinematic pulse (mood 0); a cool teal grade over true-colour stills.
   Lines (0-based): 0 hook · 1 12 km + Everest · 2 19 years + the question · 3 water · 4 fossils ·
   5 the answer: 180° · 6 plastic rock · THE ENDING: 7 what happened in the end · 8 how it is today (back to the
   hook's cap: the loop closes) · 9 the closing line (the Moon vs 0.2 %) · 10 the sponsor line.
   Stills: cap, station, water, cores, drill, strata (ChatGPT); fossil, earth (Gemini); everest (ChatGPT, cut out). */
CONFIG({
  look: {tr: 2, cam: 4, accent: 4, mood: 0, grade: {col: '#0b3d66', a: .16}, vign: .45},
  badgeIn: 2.0,
  gap: {at: 17.75, close: WF(5, 'صد').s, q: 'چرا متوقفش کردن؟', a: 'جواب: ۱۸۰ درجه'},
  sponsorLine: 10,
  caps: {
    0: {keys: ['عمیق‌ترین']},
    1: {text: 'بیشتر از ۱۲ کیلومتر می‌ره پایین؛ اورست رو برعکس توش بذاری، تازه ۳ کیلومتر هم جا داره!', keys: ['۱۲', 'اورست', '۳']},
    2: {text: '۱۹ سال کندن. ولی یه روز، برای همیشه متوقفش کردن. چرا؟', keys: ['۱۹', 'متوقفش']},
    3: {text: '۳ کیلومتر پایین‌تر: آب! جایی که انتظارش نبود.', keys: ['آب']},
    4: {text: '۶ کیلومتری: فسیلِ پلانکتون‌های ذره‌بینی.', keys: ['فسیلِ']},
    5: {text: 'تهِ چاه، جوابِ این راز: ۱۸۰ درجه! تقریباً ۲ برابرِ پیش‌بینی.', keys: ['۱۸۰', '۲']},
    6: {keys: ['پلاستیک', 'می‌بست']},
    7: {keys: ['آخرش', 'رها']},
    8: {keys: ['امروز', 'جوش‌خورده']},
    9: {text: 'ما تا ماه رفتیم، ولی زیر پامون فقط ۰٫۲ درصدِ راه رو کندیم.', keys: ['ماه', '۰٫۲']},
  },
});
const AMB = ACC;            // amber: heat and rust
const KM = 12.262;          // the hole's true vertical depth (km), 1989

/* the crust in section: the strata still, `km` deep at y = yAt, `ppk` pixels a km (the still spans 0..KM+) */
function section(km, ppk, yAt = 760, o = {}) {
  const im = IM.strata, hh = (KM + .6) * ppk, ww = Math.max(W, hh * im.width / im.height * (o.squash ? 0 : 1));
  const y0 = yAt - km * ppk, x0 = (W - ww) / 2 + (o.dx || 0);
  X.fillStyle = NAVY; X.fillRect(0, 0, W, H);
  X.save(); X.imageSmoothingQuality = 'high'; X.drawImage(im, x0, y0, ww, hh); // and its mirror below: the granite goes on
  X.translate(0, y0 + 2 * hh); X.scale(1, -1); X.drawImage(im, x0, 0, ww, hh); X.restore();
  const dk = cl(km / KM); X.save(); X.globalAlpha = .18 + .32 * dk; X.fillStyle = '#000410'; X.fillRect(0, Math.max(0, y0), W, H); X.restore();
  if (o.heat) { const g = X.createLinearGradient(0, y0 + 8.5 * ppk, 0, y0 + KM * ppk); g.addColorStop(0, 'rgba(255,110,30,0)'); g.addColorStop(1, `rgba(255,110,30,${.6 * o.heat})`); X.fillStyle = g; X.fillRect(0, y0 + 8.5 * ppk, W, (KM - 8.5) * ppk + 60); }
  return y0;
}
function shaft(x, y0, ppk, km, o = {}) { // the hole from the surface (y0) down to `km`
  const y1 = y0 + km * ppk, top = Math.max(y0, -20), w = o.w || 10;
  X.save(); X.fillStyle = 'rgba(0,3,12,.92)'; X.fillRect(x - w, top, 2 * w, y1 - top); X.restore();
  glowLine(x, top, x, y1, o.col || CYAN, 3, 22, o.alpha ?? 1);
  X.save(); X.fillStyle = o.col || CYAN; X.shadowColor = o.col || CYAN; X.shadowBlur = 34; X.beginPath(); X.arc(x, y1, 13, 0, Math.PI * 2); X.fill(); X.restore();
  return y1;
}
function tower(x, y, s, alpha = 1) { // a small drilling tower on the surface
  X.save(); X.globalAlpha *= alpha; X.strokeStyle = WHITE; X.lineWidth = 5; X.lineJoin = 'round'; X.beginPath();
  X.moveTo(x - 30 * s, y); X.lineTo(x - 9 * s, y - 100 * s); X.lineTo(x + 9 * s, y - 100 * s); X.lineTo(x + 30 * s, y);
  X.moveTo(x - 21 * s, y - 33 * s); X.lineTo(x + 21 * s, y - 33 * s); X.moveTo(x - 15 * s, y - 66 * s); X.lineTo(x + 15 * s, y - 66 * s); X.stroke(); X.restore();
}
function kmMarks(y0, ppk, from, to, o = {}) { // the km ticks on the left of the hole, fading near the counter
  for (let k = from; k <= to; k++) { const y = y0 + k * ppk; if (y < 420 || y > 1000) continue; const a = (1 - pr(y, 900, 1000)) * pr(y, 420, 480);
    glowLine(470, y, 528, y, 'rgba(245,251,255,.85)', 3, 0, a); T(fa(k) + ' کیلومتر', 452, y, 38, {al: 'right', col: WHITE, stroke: 8, alpha: a}); }
}
function landmark(y0, ppk, km, label, side = 1) { // a known height passing by (a dashed line at its depth)
  const y = y0 + km * ppk; if (y < 420 || y > 1000) return; const a = (1 - pr(y, 880, 990)) * pr(y, 420, 470);
  X.save(); X.globalAlpha *= a; X.setLineDash([14, 10]); X.strokeStyle = AMB; X.lineWidth = 3; X.beginPath(); X.moveTo(560, y); X.lineTo(1000, y); X.stroke(); X.restore();
  T(label, 990, y - 30, 34, {al: 'right', col: AMB, stroke: 8, alpha: a});
}

/* 1 · the hook: the rusty cap, the title on the first frame */
SHOT(0, (s, t) => {
  plate('cap', {...CAM(s, 2.4, 'push', 1.2), ay: .55});
  shade(.55, .35);
  HEAD(t, -1, 'عمیق‌ترین چاه دنیا', 540, 560, 106, {keys: ['عمیق‌ترین'], stroke: 12});
  T(fa(12262) + ' متر، زیر این درپوش', 540, 694, 54, {col: AMB, stroke: 10, shadow: 16});
  const lp = pr(s, .5, 1.4); ring(512, 1000, 330 - 40 * E.o3(lp), lp, {col: CYAN, lw: 5, alpha: .9});
  if (s > 1.2) ring(512, 1000, 292, 1, {col: CYAN, lw: 3, alpha: .4 + osc(s, 1.2, .2)});
}, {name: 'hook: cap'});
BEAT(1.2, 'the ring locks on the cap');

/* 2 · the dive: down the hole through the real strata, the counter rolls to 12,262 m */
const dive0 = 2.25, dive1 = WF(1, 'پایین').e, PPK = 205;
const diveKm = t => KM * E.io(pr(t, dive0 + .25, dive1));
SHOT(dive0, (s, t) => {
  const km = diveKm(t), y0 = section(km, PPK);
  if (y0 > 330) tower(540, y0, 1.1);
  shaft(540, y0, PPK, km);
  kmMarks(y0, PPK, 1, 12);
  landmark(y0, PPK, .435, 'قدِ برج میلاد'); landmark(y0, PPK, 5.61, 'قدِ دماوند'); landmark(y0, PPK, 8.849, 'قدِ اورست');
  const pop = E.back(pr(t, dive1 - .1, dive1 + .35)) * (1 - pr(t, dive1 + .35, dive1 + .9));
  X.save(); X.translate(540, 1075); X.scale(1 + .14 * pop, 1 + .14 * pop);
  T(fa(Math.round(km * 1000)) + ' متر', 0, 0, 100, {col: t > dive1 - .05 ? CYAN : WHITE, stroke: 14, shadow: 24}); X.restore();
}, {name: 'dive'});
BEAT(3.4, 'the Milad tower mark'); BEAT(5.2, 'Damavand'); BEAT(6.3, 'Everest depth'); BEAT(dive1, 'the counter lands');

/* 3 · Everest upside down in the hole: 3.4 km to spare */
const ev0 = WF(1, 'اورست').s - .3, flip = WF(1, 'برعکس').s, gapT = WF(1, 'تازه').s;
SHOT(ev0, (s, t) => {
  const y0 = 470, ppk = 56;
  X.fillStyle = NAVY; X.fillRect(0, 0, W, H);
  X.save(); X.imageSmoothingQuality = 'high'; X.drawImage(IM.strata, 0, y0, W, H - y0); X.globalAlpha = .38; X.fillStyle = '#000410'; X.fillRect(0, y0, W, H - y0); X.restore();
  X.save(); const g = X.createLinearGradient(0, y0 + (KM + .3) * ppk, 0, H); g.addColorStop(0, 'rgba(0,4,16,0)'); g.addColorStop(1, 'rgba(0,4,16,.7)'); X.fillStyle = g; X.fillRect(0, y0 + KM * ppk, W, H); X.restore();
  glowLine(0, y0, W, y0, 'rgba(245,251,255,.6)', 2, 0); tower(540, y0, .75);
  const yb = shaft(540, y0, ppk, KM, {w: 8});
  T(fa(12262) + ' متر', 300, yb, 44, {col: CYAN, stroke: 9});
  const evH = 8.849 * ppk, im = IM.everest, evW = evH * im.width / im.height;
  const f = E.io(pr(t, flip - .05, flip + .8)), drop = E.io(pr(t, flip + .45, flip + 1.25)), a = pr(t, ev0 + .05, ev0 + .35);
  const cx = 540, cy = mix(860, y0 + evH / 2, drop), sc = mix(1.25, 1, drop);
  X.save(); X.translate(cx, cy); X.rotate(Math.PI * f); X.scale(sc * mix(.85, 1, a), sc * mix(.85, 1, a)); X.globalAlpha *= a; img('everest', 0, 0, evW, {sh: 26}); X.restore();
  if (t < flip + .3) T('اورست · ' + fa(8849) + ' متر', 540, 860 - evH * 1.25 / 2 - 40, 48, {col: WHITE, stroke: 10, alpha: a * (1 - pr(t, flip, flip + .3))});
  const gp = pr(t, gapT - .15, gapT + .45);
  if (gp > 0) { const y1 = y0 + evH, y2 = yb, xb = 590; X.save(); X.globalAlpha *= gp; glowLine(xb, y1, xb, mix(y1, y2, E.o3(gp)), AMB, 7, 22); glowLine(xb - 16, y1, xb + 16, y1, AMB, 7, 10); if (gp > .9) glowLine(xb - 16, y2, xb + 16, y2, AMB, 7, 10); X.restore();
    T('هنوز ' + fa(3.4, 1) + ' کیلومتر جا', 1010, (y1 + y2) / 2, 46, {al: 'right', col: AMB, stroke: 10, alpha: gp}); }
}, {name: 'everest'});
BEAT(flip, 'Everest flips'); BEAT(gapT, 'the 3 km bracket');

/* 4 · nineteen years: the station, 1970 -> 1989 */
const st0 = LN(2).s - .55;
SHOT(st0, (s, t) => {
  plate('station', {...CAM(s, 4.5, 'up', 1.1), ay: .62});
  shade(.25, .45);
  const p = E.io(pr(t, st0 + .5, WF(2, 'کندن').e + .2)), x1 = 850, x2 = 230, y = 560;
  glowLine(x1, y, mix(x1, x2, p), y, AMB, 7, 18);
  if (p < .12) chip(fa(1970, 0, false), x1, y, 44, {fill: 'rgba(0,9,40,.88)', line: AMB, col: WHITE});
  else { glowLine(x1, y - 22, x1, y + 22, AMB, 5, 10); T(fa(1970, 0, false), x1, y - 52, 34, {f: 'YR', col: WHITE, stroke: 7}); }
  if (p > .02) chip(fa(Math.round(mix(1970, 1989, p)), 0, false), mix(x1, x2, p), y, 44, {fill: AMB, col: NAVY, line: AMB});
  T(fa(19) + ' سال حفاری', 540, 668, 58, {col: WHITE, stroke: 10, alpha: pr(t, st0 + .6, st0 + .9)});
}, {name: 'station: 19 years'});
BEAT(WF(2, 'کندن').e, '1989 lands');

/* 5 · then it stopped: the lights go out, the stamp */
const stop0 = WF(2, 'ولی').s - .1, stamp = WF(2, 'متوقفش').s;
SHOT(stop0, (s, t) => {
  const dark = E.io(pr(t, stamp - .2, WF(2, 'کردن').e));
  plate('station', {...CAM(s + 3, 4.5, 'up', 1.1), ay: .62, z: 1.18 + .06 * pr(s, 0, 3)});
  X.save(); X.globalAlpha = .62 * dark; X.fillStyle = '#000410'; X.fillRect(0, 0, W, H); X.restore();
  shade(.2, .45);
  const sp = E.back(pr(t, stamp, stamp + .4));
  if (sp > 0) { X.save(); X.translate(540, 640); X.rotate(-.06); X.scale(1.6 - .6 * sp, 1.6 - .6 * sp); X.globalAlpha *= pr(t, stamp, stamp + .15);
    pill(0, 0, 560, 140, {fill: 'rgba(0,9,40,.55)', line: AMB, lw: 7, r: 18, glow: 26}); T('پایان حفاری', 0, 0, 68, {col: AMB}); X.restore(); }
}, {name: 'stopped', tr: 'flash', d: .3});
BEAT(stamp, 'the stamp');

/* 6 · «چرا؟» full screen, then it shrinks into the chip */
const why = WF(2, 'چرا').s - .08;
SHOT(why, (s, t) => {
  plate('cap', {...CAM(s, 2, 'push', 1), alpha: .35, ay: .55});
  X.save(); X.globalAlpha = .55; X.fillStyle = NAVY; X.fillRect(0, 0, W, H); X.restore();
  const p = E.back(pr(s, 0, .35)), out = E.io(pr(t, 17.35, 17.8));
  X.save(); X.translate(540, mix(860, 392, out)); const z = (.5 + .5 * p) * mix(1, .12, out); X.scale(z, z);
  T('چرا؟', 0, 0, 330, {col: AMB, glow: 40, glowCol: AMB, alpha: 1 - pr(t, 17.6, 17.8)}); X.restore();
}, {name: 'why?', tr: 'match', caps: false});
BEAT(why, 'the giant question');

/* the gauge on the right, above the captions */
function gaugeR(km, o = {}) { return gauge(990, 480, 660, km, KM, {ticks: 12, col: o.col || CYAN, alpha: o.alpha ?? 1}); }
function gaugeTag(km, s, col = CYAN) { const y = 480 + 660 * cl(km / KM); chip(s, 858, y, 34, {fill: 'rgba(0,9,40,.88)', line: col}); }

/* 7 · back down: to 3 km through the strata */
const g3 = LN(3).s - .25;
SHOT(g3, (s, t) => {
  const km = count(t, g3, g3 + 1.2, .4, 3), y0 = section(km, PPK);
  shaft(540, y0, PPK, km); kmMarks(y0, PPK, 1, 4);
  gaugeR(km); gaugeTag(km, fa(Math.round(km * 10) / 10, 1) + ' کیلومتر');
}, {name: 'down to 3 km'});
BEAT(g3 + 1.2, '3 km');

/* 8 · water, where nobody expected it */
const wa = WF(3, 'آب').s - .12, wchip = WF(3, 'جایی').s;
SHOT(wa, (s, t) => {
  plate('water', {...CAM(s, 3, 'down', 1.2), ay: .4});
  shade(.3, .5);
  gaugeR(3); gaugeTag(3, fa(3) + ' کیلومتر');
  const c = E.back(pr(t, wchip - .1, wchip + .3));
  if (c > 0) { X.save(); X.translate(500, 640); X.scale(c, c); pill(0, 0, 700, 170, {fill: 'rgba(0,9,40,.84)', line: CYAN, r: 26, glow: 16});
    T('آب، در دلِ سنگ', 0, -30, 54, {col: CYAN}); T(fa(3) + ' تا ' + fa(6) + ' کیلومتر زیرِ زمین', 0, 38, 38, {f: 'YR', col: WHITE}); X.restore(); }
}, {name: 'water'});
BEAT(wchip, 'the water card');

/* 9 · 6 km: plankton fossils under the microscope */
const f6 = LN(4).s - .2, fos = WF(4, 'فسیل').s - .1;
SHOT(f6, (s, t) => {
  const km = count(t, f6, f6 + .9, 3, 6), y0 = section(km, PPK);
  shaft(540, y0, PPK, km); kmMarks(y0, PPK, 3, 7);
  const r = 340 * E.back(pr(t, fos, fos + .6));
  if (r > 1) { X.save(); X.globalAlpha = .55 * pr(t, fos, fos + .3); X.fillStyle = '#000410'; X.fillRect(0, 0, W, H); X.restore();
    disc('fossil', 520, 790, r, {z: 1.05 + .3 * pr(t, fos, LN(4).e + 1), ring: CYAN, lw: 8}); }
  gaugeR(km); gaugeTag(km, fa(Math.round(km)) + ' کیلومتر');
  const l = pr(t, fos + .5, fos + .8); if (l > 0) chip('فسیلِ پلانکتون، ذره‌بینی', 520, 1172, 40, {fill: 'rgba(0,9,40,.88)', line: AMB, alpha: l});
}, {name: 'fossils'});
BEAT(fos, 'the microscope opens'); BEAT(fos + 1.4, 'the lens zooms');

/* 11 · the bottom: the drill glows, the answer 180° (the chip flips) */
const bot = LN(5).s - .2, ans = WF(5, 'صد').s, twice = WF(5, 'تقریباً').s;
SHOT(bot, (s, t) => {
  plate('drill', {...CAM(s, 6, 'push', 1.3), ay: .62});
  shade(.3, .45);
  const km = count(t, bot, bot + 1.2, 6, KM); gaugeR(km, {col: AMB}); gaugeTag(km, fa(Math.round(km * 10) / 10, 1) + ' کیلومتر', AMB);
  const c = pr(t, ans - .05, ans + 1.1);
  if (c > 0) { const v = Math.round(count(t, ans - .05, ans + 1.1, 100, 180)); X.save(); X.translate(480, 610); const z = 1 + .08 * (1 - E.o3(pr(t, ans + 1.0, ans + 1.4))) * (c >= 1 ? 1 : 0); X.scale(z, z);
    T(fa(v), 0, 0, 230, {f: 'YB', col: v >= 180 ? AMB : WHITE, glow: v >= 180 ? 50 : 0, glowCol: AMB, stroke: 14}); X.restore(); T('درجه‌ی سانتی‌گراد', 480, 750, 44, {f: 'YR', col: WHITE, stroke: 8, alpha: c}); }
  const b = pr(t, twice - .1, twice + .6);
  if (b > 0) { const L = 380, x0 = 760; X.save(); X.globalAlpha *= b;
    pill(480, 905, 700, 210, {fill: 'rgba(0,9,40,.86)', line: 'rgba(245,251,255,.3)', r: 26});
    T('پیش‌بینی', x0, 858, 36, {al: 'right', f: 'YR'}); rr(x0 - 170 - L * E.o3(b) * 100 / 180, 846, L * E.o3(b) * 100 / 180, 22, 11); X.fillStyle = 'rgba(245,251,255,.85)'; X.fill();
    T(fa(100), x0 - 185 - L * E.o3(b) * 100 / 180, 858, 36, {al: 'right', col: WHITE});
    T('واقعی', x0, 948, 36, {al: 'right', f: 'YR', col: AMB}); rr(x0 - 170 - L * E.o3(b), 936, L * E.o3(b), 22, 11); X.fillStyle = AMB; X.fill();
    T(fa(180), x0 - 185 - L * E.o3(b), 948, 36, {al: 'right', col: AMB}); X.restore(); }
}, {name: 'the answer: 180°'});
BEAT(ans, '180 lands'); BEAT(twice, 'the bars');

/* 12 · rock like plastic: the picture itself flows, the hole closes in, the drill stops */
const pl = LN(6).s - .2, closeT = WF(6, 'چاه').s, bit = WF(6, 'مته').s;
SHOT(pl, (s, t) => {
  const im = IM.drill, z = 1.32, k = Math.max(W / im.width, H / im.height) * z, w = im.width * k, h = im.height * k, ox = (W - w) / 2, oy = H / 2 - h * .6;
  const flow = E.io(pr(t, WF(6, 'پلاستیک').s - .1, closeT + .4)), n = 48, sh = h / n;
  for (let j = 0; j < n; j++) { // horizontal strips, each pushed by its own slow wave: the rock flows
    const y = oy + j * sh, dx = flow * (osc(j / n * 2.2 + t * .55, 1, 26) + osc(j / n * 5.1 - t * .8, 1, 10));
    X.drawImage(im, 0, j * im.height / n, im.width, im.height / n + 1, ox + dx, y, w, sh + 1);
  }
  X.save(); X.globalAlpha = .25; X.fillStyle = '#2a0c04'; X.fillRect(0, 0, W, H); X.restore();
  const c = E.io(pr(t, closeT - .1, bit + .4)); // the hole closing: a dark iris from the edges
  if (c > 0) { X.save(); const g = X.createRadialGradient(540, 760, mix(1300, 260, c), 540, 760, mix(1500, 520, c)); g.addColorStop(0, 'rgba(10,3,1,0)'); g.addColorStop(1, 'rgba(10,3,1,.96)'); X.fillStyle = g; X.fillRect(0, 0, W, H); X.restore(); }
  HEAD(t, WF(6, 'پلاستیک').s - .05, 'مثل پلاستیک', 540, 480, 84, {col: AMB, stroke: 12});
  const kk = pr(t, bit + .2, bit + .7); if (kk > 0) { pill(540, 800, 140 + 420 * E.o3(kk), 130, {fill: 'rgba(0,9,40,.9)', line: '#FF5470', lw: 6, glow: 22, alpha: kk}); T('مته جلو نمی‌رفت', 540, 800, 52, {col: WHITE, alpha: pr(t, bit + .45, bit + .7)}); }
}, {name: 'plastic rock', tr: 'match'});
BEAT(WF(6, 'پلاستیک').s, 'the rock starts to flow'); BEAT(closeT, 'the hole closes'); BEAT(bit + .2, 'the drill stops');

/* 13 · THE ENDING (1): what happened in the end — the station goes dark, three dates */
const end0 = LN(7).s - .2, money = WF(7, 'پولش').s, left = WF(7, 'رها').s;
SHOT(end0, (s, t) => {
  plate('station', {...CAM(s, 4, 'pull', 1), ay: .62});
  X.save(); X.globalAlpha = .5 + .2 * pr(t, left, left + .6); X.fillStyle = '#000410'; X.fillRect(0, 0, W, H); X.restore();
  shade(.2, .5);
  HEAD(t, end0 + .05, 'پایانِ ماجرا', 540, 470, 88, {col: AMB, stroke: 12});
  const rows = [[end0 + .35, fa(1989, 0, false), fa(12262) + ' متر، عمیق‌ترین نقطه', CYAN],
                [money - .1, fa(1995, 0, false), 'بودجه تموم شد', AMB],
                [left - .1, fa(2008, 0, false), 'سایت رها شد', '#FF5470']];
  glowLine(780, 600, 780, mix(600, 1000, E.io(pr(t, end0 + .3, left + .3))), 'rgba(245,251,255,.7)', 3, 0);
  rows.forEach(([at, y, what, col], k) => { const a = E.back(pr(t, at, at + .4)); if (a <= 0) return; const yy = 620 + k * 180;
    X.save(); X.translate(780, yy); X.scale(a, a); X.fillStyle = col; X.shadowColor = col; X.shadowBlur = 20; X.beginPath(); X.arc(0, 0, 14, 0, Math.PI * 2); X.fill(); X.restore();
    T(y, 740, yy - 26, 52, {al: 'right', col, stroke: 9, alpha: pr(t, at, at + .2)}); T(what, 740, yy + 34, 40, {al: 'right', f: 'YR', col: WHITE, stroke: 8, alpha: pr(t, at + .1, at + .3)}); });
}, {name: 'ending: what happened', tr: 'flash', d: .3});
BEAT(money, '1995'); BEAT(left, '2008');

/* 14 · THE ENDING (2): how it is today — back to the hook's cap, now named for what it is */
const today = LN(8).s - .15, weld = WF(8, 'جوش').s;
SHOT(today, (s, t) => {
  plate('cap', {...CAM(s, 4, 'push', 1.1), ay: .55});
  shade(.45, .4);
  const a = E.back(pr(t, today + .1, today + .5));
  if (a > 0) { X.save(); X.translate(540, 520); X.scale(a, a); chip('امروز', 0, 0, 56, {fill: CYAN, col: NAVY, line: CYAN, glow: 24}); X.restore(); }
  const lp = pr(t, weld - .1, weld + .7); ring(512, 1000, 330 - 40 * E.o3(lp), lp, {col: AMB, lw: 6, alpha: .95});
  T('جوش‌خورده و رها', 540, 650, 54, {col: AMB, stroke: 10, alpha: pr(t, weld, weld + .3)});
}, {name: 'ending: today', tr: 'zoom'});
BEAT(weld, 'the welded cap');

/* 15 · THE ENDING (3): the closing line — the Moon, and 0.2 % under our feet */
function moon(x, y, r, alpha = 1) { // a clean code Moon: shaded disc and a few soft maria
  X.save(); X.globalAlpha *= alpha; const g = X.createRadialGradient(x - r * .35, y - r * .35, r * .1, x, y, r); g.addColorStop(0, '#e9e9e4'); g.addColorStop(.7, '#a9a9a3'); g.addColorStop(1, '#55574f');
  X.fillStyle = g; X.shadowColor = 'rgba(220,230,255,.5)'; X.shadowBlur = 30; X.beginPath(); X.arc(x, y, r, 0, Math.PI * 2); X.fill(); X.shadowBlur = 0;
  X.fillStyle = 'rgba(70,72,66,.35)'; for (const [dx, dy, rr2] of [[-.3, -.1, .22], [.15, .25, .16], [.3, -.3, .12], [-.05, .45, .09]]) { X.beginPath(); X.arc(x + dx * r, y + dy * r, rr2 * r, 0, Math.PI * 2); X.fill(); }
  X.restore();
}
const sc = LN(9).s - .25, toMoon = WF(9, 'ماه').s, pct = WF(9, 'دو').s;
SHOT(sc, (s, t) => {
  X.fillStyle = '#00030c'; X.fillRect(0, 0, W, H);
  const p = E.io(pr(s, 0, 2.6)), z = mix(2.0, .66, p);
  const im = IM.earth, k = W / im.width * z, w = im.width * k, h = im.height * k, gx = mix(540, 430, p), gy = mix(900, 1010, p), gr = .374 * w;
  X.save(); X.imageSmoothingQuality = 'high'; X.drawImage(im, gx - w * .5, gy - h * .5, w, h); X.restore();
  const m = E.back(pr(t, toMoon - .1, toMoon + .5));
  if (m > 0) { moon(850, 520, 70 * m); T('ماه · ' + fa(384400) + ' کیلومتر', 850, 630, 34, {col: WHITE, stroke: 8, alpha: pr(t, toMoon, toMoon + .3)});
    X.save(); X.globalAlpha *= pr(t, toMoon, toMoon + .4); X.setLineDash([12, 12]); X.strokeStyle = 'rgba(245,251,255,.55)'; X.lineWidth = 3; X.beginPath(); X.moveTo(gx + gr * .6, gy - gr * .8); X.lineTo(790, 560); X.stroke(); X.restore(); }
  const b = E.back(pr(t, pct - .1, pct + .35));
  if (b > 0) { X.save(); X.translate(gx, gy); X.scale(b, b); T(fa(.2, 1) + '٪', 0, 0, 150, {col: CYAN, glow: 40, stroke: 12}); X.restore();
    T('زیرِ پای خودمون', gx, gy + 110, 40, {col: WHITE, stroke: 8, alpha: pr(t, pct + .2, pct + .5)}); }
}, {name: 'ending: the closing line'});
BEAT(toMoon, 'the Moon'); BEAT(pct, '0.2 %');

/* 16 · under the sponsor card and the end card: back to the cap (the loop) */
SHOT(LN(10).s - .2, (s, t) => { plate('cap', {...CAM(s, 8, 'pull', .8), ay: .55}); }, {name: 'sponsor + end', tr: 'zoom', caps: false});
