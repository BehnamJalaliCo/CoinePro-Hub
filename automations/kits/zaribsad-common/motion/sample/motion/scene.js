/* THE DESK — the sample brief (SOL, the real data of 2026-11-25; an EXAMPLE of the API, never a reel's data).
 * Render it: cd COMMON/motion/sample && PY -I ../desk_engine.py --test 1,4,7.5,10.5,14 */
const F = DATA.facts, S = F.series_1y.map(r => r[1]), ch = F.change_pct;
const CAPS = DESK.capsFromWords(DATA.lines, {keys: ['نصف', 'سریع‌ترین‌هاست', 'منفی،', 'مثبت', 'هفت']});
const SHOTS = [
  {a: 0, b: 2.6, draw: (t, p) => {          // cold open: the hook is fully drawn at frame 0
    ground(t, {light: 0.26, horizon: 1250});
    X.save(); rig(p, {s0: 1.0, s1: 1.06, cy: 900});
    txt('SOL / USDT · 1Y', 60, 640, {kind: 'M', w: 500, px: 34, col: Z.mu, track: 4});
    odometer(t, ch['1y'], 540, 900, -1.2, 1.4, {px: 220, kind: 'C', change: true, suffix: '%', dec: 1});
    zline(t, 980, -0.6, {label: 'ONE YEAR'});
    headline(t, ['سولانا [نصف] شد', 'حالا چی؟'], 1020, 1170, -0.7, {px: 112});
    X.restore();
  }},
  {a: 2.6, b: 6.1, tr: 'blade', draw: (t, p) => {
    ground(t, {lx: 300, light: 0.2});
    kicker(t, 1, 'نمودار یک‌ساله', 2.7);
    panel('chart', t, 50, 520, 980, 760, {t0: 2.75, tab: '01 · SOL/USDT · 1D', ry: lerp(-6, 4, p)}, (g, w, h) => {
      lineChart(t, S, 40, 130, w - 80, h - 220, 2.95, 2.6, {g, levels: [{v: F.ath_usd > Math.max(...S) ? Math.max(...S) : F.ath_usd, label: 'HIGH'}]});
    });
    const pw = odometer(t, F.price_usd, 520, 1370, 3.1, 1.2, {px: 120, kind: 'C', prefix: '$', dec: 2, align: 'right'});
    changeChip(t, ch['24h'], 560, 1330, 3.9, {px: 34});
  }},
  {a: 6.1, b: 9.5, tr: 'slats', draw: (t, p) => {
    ground(t, {lx: 800, light: 0.22});
    kicker(t, 2, 'عددها', 6.2);
    panel('bars', t, 50, 540, 980, 820, {t0: 6.25, tab: '02 · RETURNS', title: 'بازده'}, (g, w, h) => {
      returnBars(t, [{k: '24h', v: ch['24h']}, {k: '7d', v: ch['7d']}, {k: '30d', v: ch['30d']}, {k: '1y', v: ch['1y']}], 40, 140, w - 80, h - 180, 6.5, {g});
    });
  }},
  {a: 9.5, b: 13.0, tr: 'aperture', draw: (t, p) => {
    ground(t, {lx: 540, ly: 700, light: 0.24, horizon: 1300});
    kicker(t, 3, 'جایگاه در بازار', 9.6);
    const cards = [['RANK', '#' + F.rank, 'رتبه'], ['MKT CAP', '$' + (F.market_cap_usd / 1e9).toFixed(1) + 'B', 'ارزش بازار'], ['ATH', '$' + F.ath_usd.toFixed(2), 'سقف تاریخی']];
    cards.forEach((c, i) => panel('st' + i, t, 90 + i * 0, 560 + i * 250, 900, 210, {t0: 9.75 + i * 0.18, tab: c[0], from: i % 2 ? 'left' : 'right', ry: (i - 1) * 7 * (1 - p)}, (g, w, h) => {
      g.font = '96px ZC700'; g.fillStyle = Z.pt; g.direction = 'ltr'; g.textAlign = 'left'; g.fillText(c[1], 32, 168);
      g.font = '40px ZF800'; g.fillStyle = Z.viL; g.direction = 'rtl'; g.textAlign = 'right'; g.fillText(c[2], w - 32, 150);
    }));
  }},
  {a: 13.0, b: 16.5, tr: 'cut', draw: (t) => { ground(t); }},
];
DESK.reel({shots: SHOTS, caps: CAPS, hud: {brief: 41, pair: 'SOL/USDT', time: '25.11 21:15 UTC'}, end: {word: 'الماس', at: 13.0}, END: 16.5});
