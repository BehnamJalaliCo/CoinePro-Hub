/* bitmart — a working sample of THE FILE's API (FILE 000: the bitcoin pizza). An example of the calls only —
 * never a reel's data or a reel's look: a real reel has its own plates (≥ 6 AI stills), its own story and
 * its real numbers from qc/facts.json. Assets here: assets/owner.jpg (the cover photo), assets/owner_cut.png
 * (its cut-out), assets/plate.jpg (any picture). */
const S = STORY, {B, W, H} = S, F = DATA.facts || {};
const SHOTS = [
  // 01 the cold open: the hook drawn at frame 0, the marker on the key word
  {a: 0, b: 3.2, tr: 'cut', draw: (t, p) => {
    S.ground(t, {light: 0.55, lx: 820, ly: 600});
    X.save(); S.rig(p, {s0: 1.0, s1: 1.06});
    S.counter(t, F.btc || 10000, W / 2, 880, -1, 0.6, {px: 250, latin: false, unit: 'بیت‌کوین'});
    S.headline(t, ['دو تا پیتزا', '[یک میلیارد] دلار'], 1000, 1180, -1, {px: 112});   // landed at frame 0
    X.restore();
  }},
  // 02 the dateline over the archive photo (duotone), Ken Burns
  {a: 3.2, b: 6.6, tr: 'swipe', draw: (t, p) => {
    S.plate('assets/plate.jpg', {p, tone: 'duo', push: [1.06, 1.18], pan: [[0.3, 0.4], [0.6, 0.5]]});
    S.vignette(0.7);
    S.dateline(t, '2010', 'فلوریدا، ۲۲ می', 3.45);
    S.lowerThird(t, 'لازلو هانیچ', 'برنامه‌نویس', 4.2);
  }},
  // 03 the document lands: a clipping and a stamp
  {a: 6.6, b: 10.2, tr: 'shutter', draw: (t, p) => {
    S.ground(t, {light: 0.45});
    X.save(); S.rig(p, {s0: 1.04, s1: 1.0, r0: -1, r1: 0});
    S.clipping('c1', t, 150, 520, 780, 860, {t0: 6.75, rot: -4, paper: 'روزنامه‌ی پول', date: '۲۳ می ۲۰۱۰', headline: ['یک برنامه‌نویس', 'پیتزا را با', 'بیت‌کوین خرید']});
    S.stamp(t, 'واقعی', 760, 1260, 8.0, {rot: -10});
    X.restore();
  }},
  // 04 the numbers: bars and the unit grid
  {a: 10.2, b: 14.0, tr: 'zoom', draw: (t, p) => {
    S.ground(t, {light: 0.35, lx: 900, ly: 400});
    S.kicker(t, 1, 'ارزش امروز', 10.35);
    S.bars(t, [{label: 'سال ۲۰۱۰', v: 41, show: '$41'}, {label: 'امروز', v: 900, show: '$900M'}], 70, 640, 940, 150, 10.6, {hero: 1});
    S.dotGrid(t, 1, 400, 70, 1000, 940, 11.2, 1.4, {cols: 25});
  }},
  // 05 the timeline
  {a: 14.0, b: 17.6, tr: 'page', draw: (t, p) => {
    S.ground(t, {light: 0.4, lx: 540, ly: 900});
    S.kicker(t, 2, 'ماجرا', 14.15);
    S.timeline(t, [{year: '2009', label: 'تولد بیت‌کوین'}, {year: '2010', label: 'پیتزا'}, {year: '2017', label: 'اوج اول'}, {year: '2024', label: 'صندوق‌ها'}], 90, 900, 900, 14.4, 2.6);
  }},
  // 06 the parallax portrait + a quote
  {a: 17.6, b: 21.0, tr: 'swipe', draw: (t, p) => {
    S.parallax('assets/owner.jpg', 'assets/owner_cut.png', {p, back: {tone: 'duo'}, front: {cx: 600, cy: 1250, h: 1350, dx: -50}});
    S.quote(t, ['پشیمون نیستم'], 'لازلو، سال‌ها بعد', 1000, 470, 17.9, {px: 92});
  }},
];
const CAPS = S.capsFromWords(DATA.lines, {keys: ['پیتزا', 'میلیارد']});
S.reel({shots: SHOTS, caps: CAPS, hud: {file: 0, title: 'پیتزای بیت‌کوینی'}, end: {word: 'پیتزا', at: 21.0}, END: 24.5});
