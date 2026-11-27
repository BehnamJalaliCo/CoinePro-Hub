// @behnamjalali.tech — the sample reel (2026-11-18): Claude Fable 5.2, a model explainer (pillar «معرفی مدل»).
// Facts: anthropic.com/claude/fable (read 2026-11-18): released Nov 9, 2026; $8 / $40 per 1M tokens (Fable 5.1:
// $10 / $50); FrontierCode 2.0 49.1 / Opus 5.5 45.5 / GPT-6 Astra 42.8 / Gemini 4 Carbon 41.1; AutomationBench
// 51.4 / 42.5 / 41.4 / 53.9; Discovered Materials: 13 phonon benchmark cases 3.3 h -> under 4 min (~36x).
CONFIG({
  pillar: 'model', kicker: 'معرفی مدل', look: {tr: 0, bg: 0, mood: 1},
  caps: {
    0: {text: 'یه محاسبه‌ی علمی که بیشتر از ۳ ساعت طول می‌کشید، حالا زیر ۴ دقیقه تموم می‌شه', keys: ['۴', 'دقیقه']},
    1: {text: 'کارِ Claude Fable 5.2؛ مدلی که Anthropic نهم نوامبر معرفی کرد', keys: ['Claude']},
    2: {text: 'ولی سؤال اینه: از GPT-6 Astra و Gemini 4 Carbon هم بهتره؟', keys: ['بهتره؟']},
    3: {text: 'توی آزمون کدنویسیِ خودکار، Fable ۴۹٪ گرفته؛ Astra ۴۲/۸٪', keys: ['۴۹٪']},
    4: {text: 'ولی توی خودکارسازیِ کارهای اداری، Carbon با ۵۴٪ جلوتره', keys: ['جلوتره']},
    5: {text: 'نقطه‌ی قوّتش؟ خودِ Anthropic می‌گه انیمیشن و ویدیوی آموزشی با صدا رو با کد می‌سازه', keys: ['کد']},
    6: {text: 'قیمتش هم پایین اومده: هر میلیون توکن ورودی ۸ دلار، خروجی ۴۰ دلار', keys: ['۸', '۴۰']},
    7: {text: 'پس برای کدنویسیِ سنگین و کار علمی عالیه؛ برای کارهای روزمره، مدل‌های ارزون‌تر کافی‌ان', keys: ['عالیه', 'ارزون‌تر']},
    8: {text: 'و جالبه بدونی: همین ویدیو هم با کد ساخته شده', keys: ['کد']},
    9: {text: 'مقایسه‌ی کامل مدل‌ها رو می‌خوای؟ کلمه‌ی «مدل» رو کامنت کن', keys: ['«مدل»']},
  },
  gap: {at: LN(2).s + .3, close: LN(7).s + .2, q: 'کدوم بهتره؟', a: 'جواب: بستگی به کارت داره'},
  cta: {at: LN(9).s, word: 'مدل', line: 'این کلمه رو کامنت کن تا مقایسه رو دایرکت بگیری'},
  edge: [[0, 1.3], [LN(7).s, LN(7).s + 1.6], [LN(8).s, LN(8).e + .2]],
});
const VIOLET = '#9B87FF', CYANM = '#22D3EE', AMBER = '#FFD166';

// 1 — the hook: a run that took 3.3 hours, now under 4 minutes (frame 0 is fully drawn)
SHOT(0, (s, t) => {
  CAM(s, {z: 1.02, punch: [WF(0, 'حالا').s - LN(0).s + .35 + 1.0]});
  HEAD(s, -1, 'از ۳ ساعت به ۴ دقیقه', W / 2, 470, 90, {keys: ['۴', 'دقیقه'], maxW: 980});
  const b = PANEL(70, 600, 940, 640, {title: 'phonon.run  ·  13 benchmark cases', right: 'GPU', accent: ACC});
  const now = WF(0, 'حالا').s;
  // the stock run: 3.3 h, already there at frame 0
  T('stock code', b.x, b.y + 50, 34, {f: 'mono', w: 500, col: MUTED, al: 'left'});
  rr(b.x, b.y + 78, b.w, 34, 17); X.fillStyle = 'rgba(160,168,190,.42)'; X.fill();
  T('3.3 h', b.x + b.w, b.y + 50, 38, {f: 'en', w: 700, col: '#C9CEDA', al: 'right'});
  // the Fable run lands on «حالا»
  const p = E.o5(pr(t, now - .1, now + .5));
  T('Claude Fable 5.2', b.x, b.y + 190, 34, {f: 'mono', w: 600, col: TEXT, al: 'left', alpha: cl(p * 2)});
  if (p > 0) { rr(b.x, b.y + 218, Math.max(34, b.w * .028 * p), 34, 17); X.fillStyle = specFill(b.x, 0, b.x + 60, 0, t); X.shadowColor = ACC; X.shadowBlur = 26; X.fill(); X.shadowBlur = 0; }
  T('< 4 min', b.x + b.w, b.y + 190, 38, {f: 'en', w: 800, col: TEXT, al: 'right', alpha: cl(p * 2)});
  // the clock: 03:18:00 runs down to 00:03:59
  const secs = Math.round(mix(3.3 * 3600, 239, E.expo(pr(t, now - .1, now + 1.1))));
  const hh = String(Math.floor(secs / 3600)).padStart(2, '0'), mm = String(Math.floor(secs % 3600 / 60)).padStart(2, '0'), ss = String(secs % 60).padStart(2, '0');
  T(`${hh}:${mm}:${ss}`, W / 2, b.y + 380, 118, {f: 'mono', w: 600, col: p > .9 ? TEXT : '#B7BDCD', spec: p > .9});
  STAT(W / 2, b.y + 540, '', '≈36×', s, now + .9, {px: 120, f: 'en'});
  if (p >= 1) SWEEP(t, now + .9, .9);
}, {tr: 'cut', bg: 'grid', name: 'hook'});
BEAT(WF(0, 'حالا').s, 'the Fable bar lands');
BEAT(WF(0, 'حالا').s + 1.0, '36x lands');
BEAT(2.6, 'the clock starts');

// 2 — the model: the official launch image, its name, who and when
SHOT(LN(1).s - .3, (s, t) => {
  CAM(s, {z: 1.0, punch: [WF(1, 'نهم').s - LN(1).s + .3]});
  IMG('fable_official', 70, 330, 940, 493, {fit: 'cover', ring: true, alpha: ease(s, 0, .5)});
  CHIP('تصویر رسمی Anthropic', W / 2, 870, {px: 26, col: '#C9CEDA', alpha: ease(s, .3, .4)});
  BIG(s, .45, 'Claude Fable 5.2', W / 2, 1060, 108, {f: 'en', track: -2});
  SWEEP(s, 1.1, .9);
  const d = WF(1, 'نهم').s - LN(1).s + .3;
  CHIP('Anthropic', W / 2 + 190, 1170, {px: 30, col: VIOLET, alpha: ease(s, d - .3, .4)});
  CHIP('۹ نوامبر ۲۰۲۶', W / 2 - 150, 1170, {px: 30, col: VIOLET, alpha: ease(s, d, .4)});
}, {tr: 'zoom', bg: 'aurora', name: 'model'});
BEAT(LN(1).s + .45, 'the name lands');
BEAT(WF(1, 'نهم').s, 'the date');

// 3 — the question: three flagships, one question mark
SHOT(LN(2).s - .1, (s, t) => {
  CAM(s, {z: 1.0, drift: 1.4});
  const q = E.o5(pr(s, .1, .9));
  X.save(); X.globalAlpha = .9 * q; BIG(s, .1, '؟', W / 2, 1030, 520, {f: 'fa', w: 900}); X.restore();
  const cards = [
    {n: 'Claude Fable 5.2', v: 'Anthropic', col: VIOLET, at: 0, y: 470, x: 120},
    {n: 'GPT-6 Astra', v: 'OpenAI', col: CYANM, at: WF(2, 'آسترا').s - LN(2).s + .1, y: 700, x: 300},
    {n: 'Gemini 4 Carbon', v: 'Google', col: AMBER, at: WF(2, 'کربن').s - LN(2).s + .1, y: 930, x: 140},
  ];
  for (const c of cards) {
    const p = E.o5(pr(s, c.at, c.at + .6));
    if (p <= 0) continue;
    X.save(); X.globalAlpha *= p; X.translate((1 - p) * -220, 0);
    PANEL(c.x, c.y, 660, 170, {accent: c.col});
    X.beginPath(); X.arc(c.x + 70, c.y + 85, 18, 0, 7); X.fillStyle = c.col; X.shadowColor = c.col; X.shadowBlur = 24; X.fill(); X.shadowBlur = 0;
    T(c.n, c.x + 112, c.y + 82, 46, {f: 'en', w: 800, al: 'left'});
    T(c.v, c.x + 114, c.y + 128, 26, {f: 'mono', w: 500, col: MUTED, al: 'left'});
    X.restore();
  }
}, {tr: 'slide', bg: 'dots', name: 'question'});
BEAT(WF(2, 'آسترا').s, 'Astra card');
BEAT(WF(2, 'کربن').s, 'Carbon card');

// 4 — the answer, part one: FrontierCode 2.0 (agentic coding)
SHOT(LN(3).s - .2, (s, t) => {
  CAM(s, {z: 1.0, punch: [WF(3, 'گرفته').s - LN(3).s]});
  CHIP('آزمون کدنویسی خودکار', W / 2, 430, {px: 32, col: ACC, alpha: ease(s, 0, .4)});
  const b = PANEL(60, 500, 960, 712, {title: 'FrontierCode 2.0  ·  agentic coding', right: 'xhigh', accent: ACC});
  BARS(b, [{name: 'Claude Fable 5.2', v: 49.1, hi: true}, {name: 'Claude Opus 5.5', v: 45.5},
           {name: 'GPT-6 Astra', v: 42.8, col: 'rgba(34,211,238,.55)'}, {name: 'Gemini 4 Carbon', v: 41.1, col: 'rgba(255,209,102,.5)'}],
       s, .25, {max: 60, dec: 1});
  T('source: anthropic.com/claude/fable', W / 2, 1255, 22, {f: 'mono', w: 400, col: '#5B6078'});
}, {tr: 'scan', bg: 'grid', name: 'bars-code'});
BEAT(LN(3).s + .9, 'bars grow');
BEAT(WF(3, 'آسترا').s, 'Astra row');

// 5 — the twist: AutomationBench (business workflows), Carbon ahead
SHOT(LN(4).s - .2, (s, t) => {
  CAM(s, {z: 1.0, punch: [WF(4, 'پنجاه').s - LN(4).s]});
  CHIP('ولی…', W / 2, 430, {px: 40, col: AMBER, fill: 'rgba(255,209,102,.10)', alpha: ease(s, 0, .3)});
  const b = PANEL(60, 500, 960, 712, {title: 'AutomationBench  ·  business workflows', right: 'max effort', accent: AMBER});
  BARS(b, [{name: 'Gemini 4 Carbon', v: 53.9, hi: true}, {name: 'Claude Fable 5.2', v: 51.4, col: 'rgba(155,135,255,.6)'},
           {name: 'Claude Opus 5.5', v: 42.5}, {name: 'GPT-6 Astra', v: 41.4, col: 'rgba(34,211,238,.55)'}],
       s, .25, {max: 60, dec: 1});
  T('source: anthropic.com/claude/fable', W / 2, 1255, 22, {f: 'mono', w: 400, col: '#5B6078'});
}, {tr: 'slide', bg: 'grid', name: 'bars-office'});
BEAT(LN(4).s + .9, 'bars grow');
BEAT(WF(4, 'پنجاه').s, '54 lands');

// 6 — its edge: animation and lessons with sound, written in code
SHOT(LN(5).s - .2, (s, t) => {
  CAM(s, {z: 1.0, drift: 1.2});
  const b = PANEL(60, 360, 960, 420, {title: 'lesson.js', right: 'Fable 5.2', accent: VIOLET});
  CODE(b, 'const video = new Scene({ fps: 60 });\nvideo.add(Chart.bars(data));\nvideo.camera.push(1.2, { ease: "expo" });\nvideo.narrate(script, { voice: "Arlo" });\nvideo.render("lesson.mp4");', s, .2, {cps: 52, px: 27});
  // the preview: what the code draws, live
  const v = PANEL(60, 830, 960, 420, {title: 'preview', right: '60 fps', accent: ACC});
  const on = E.o3(pr(s, 1.6, 2.2));
  if (on > 0) {
    X.save(); X.globalAlpha *= on; X.beginPath(); X.rect(v.x, v.y, v.w, v.h); X.clip();
    for (let k = 0; k < 3; k++) {
      X.beginPath();
      for (let x = 0; x <= v.w; x += 6) { const y = v.y + v.h * .5 + Math.sin(x / 70 + s * 3 + k * 1.3) * (40 + k * 26) * on; x ? X.lineTo(v.x + x, y) : X.moveTo(v.x + x, y); }
      X.strokeStyle = SPEC[(k * 2) % 6]; X.lineWidth = 4 - k; X.globalAlpha = on * (.9 - k * .2); X.stroke();
    }
    X.globalAlpha = on;
    const bx = v.x + v.w * (.5 + .38 * Math.sin(s * 1.6)), by = v.y + v.h * .5 - Math.abs(Math.sin(s * 3.2)) * 120;
    ORB(bx, by, 22, s, {col: VIOLET});
    X.restore();
  }
  const words = [['انیمیشن', WF(5, 'انیمیشن')], ['ویدیوی آموزشی', WF(5, 'آموزشی')], ['با صدا', WF(5, 'صدا')]];
  words.forEach(([w, wd], k) => CHIP(w, W / 2 + (1 - k) * 310, 1305, {px: 30, col: SPEC[k * 2], alpha: E.o3(pr(t, wd.s - .1, wd.s + .25))}));
}, {tr: 'iris', bg: 'dots', name: 'code-to-video'});
BEAT(LN(5).s + 1.6, 'the preview starts');
BEAT(WF(5, 'آموزشی').s, 'chip');
BEAT(WF(5, 'کد').s, 'code word');

// 7 — the price: $8 in, $40 out, both down from Fable 5.1
SHOT(LN(6).s - .2, (s, t) => {
  CAM(s, {z: 1.0, punch: [WF(6, 'خروجی').s - LN(6).s]});
  HEAD(s, .1, 'ارزون‌تر از نسخه‌ی قبل', W / 2, 470, 70, {keys: ['ارزون‌تر']});
  const cards = [{lab: 'input', old: 10, nw: 8, at: WF(6, 'ورودی').s - LN(6).s, x: 560}, {lab: 'output', old: 50, nw: 40, at: WF(6, 'خروجی').s - LN(6).s, x: 80}];
  for (const c of cards) {
    const k = cards.indexOf(c), p = E.o5(pr(s, .15 + k * .12, .75 + k * .12));
    if (p <= 0) continue;
    X.save(); X.globalAlpha *= p; X.translate(0, (1 - p) * 60);
    PANEL(c.x, 590, 440, 560, {title: c.lab, right: '/ 1M tokens', accent: ACC});
    const v = count(s, c.at, .9, c.old, c.nw), landed = s >= c.at;
    T('Fable 5.1', c.x + 220, 720, 24, {f: 'mono', w: 500, col: '#6B7186'});
    T('$' + c.old, c.x + 220, 790, 64, {f: 'en', w: 700, col: landed ? '#6B7186' : '#C9CEDA'});
    const sp = E.o3(pr(s, c.at + .2, c.at + .6));
    X.fillStyle = '#FF6B7A'; X.fillRect(c.x + 140, 768, 160 * sp, 5);
    T('$' + Math.round(v), c.x + 220, 980, 180, {f: 'en', w: 900, spec: true, alpha: pr(s, c.at - .1, c.at + .25)});
    T('Fable 5.2', c.x + 220, 1030, 24, {f: 'mono', w: 600, col: landed ? TEXT : '#3A3F52'});
    T('per 1M tokens', c.x + 220, 1090, 26, {f: 'mono', w: 400, col: MUTED});
    X.restore();
  }
}, {tr: 'zoom', bg: 'aurora', name: 'price'});
BEAT(WF(6, 'ورودی').s, '$8');
BEAT(WF(6, 'خروجی').s, '$40');

// 8 — the payoff: which one, for what
SHOT(LN(7).s - .2, (s, t) => {
  CAM(s, {z: 1.0, drift: .8});
  HEAD(s, .05, 'جمع‌بندی', W / 2, 450, 92, {keys: ['جمع‌بندی']});
  const rows = [
    {q: 'کدنویسی سنگین و کار علمی', a: 'Claude Fable 5.2', ok: true, at: WF(7, 'عالیه').s - LN(7).s - .4, y: 560},
    {q: 'کارهای روزمره', a: 'مدل ارزون‌تر کافیه', ok: false, at: WF(7, 'روزمره').s - LN(7).s - .2, y: 880},
  ];
  for (const r of rows) {
    const p = E.o5(pr(s, r.at, r.at + .5));
    if (p <= 0) continue;
    X.save(); X.globalAlpha *= p; X.translate((1 - p) * 120, 0);
    PANEL(70, r.y, 940, 270, {accent: r.ok ? '#3CFFB5' : AMBER});
    T(r.q, 940, r.y + 100, 50, {f: 'fa', w: 800, al: 'right'});
    T(r.a, 940, r.y + 196, 44, {f: isLatin(r.a) ? 'en' : 'fa', w: 800, spec: r.ok, col: AMBER, al: 'right'});
    if (r.ok) CHECK(160, r.y + 135, s, r.at + .3, true, 70);
    else ARROW(110, r.y + 135, 230, r.y + 135, s, r.at + .3, AMBER);
    X.restore();
  }
}, {tr: 'scan', bg: 'grid', name: 'verdict'});
BEAT(WF(7, 'عالیه').s, 'first verdict');
BEAT(WF(7, 'روزمره').s, 'second verdict');

// 9 — full circle: this very video is code
SHOT(LN(8).s - .2, (s, t) => {
  const z = mix(1.25, 1.0, E.io(pr(s, 0, 1.4)));
  CAM(s, {z, drift: .5});
  const b = PANEL(50, 330, 980, 980, {title: 'scenes.js  —  this reel', right: 'LUMEN', accent: ACC});
  const src = ["SHOT(0, (s) => {", "  HEAD(s, 0, 'از ۳ ساعت به ۴ دقیقه');", "  STAT(W / 2, 1140, '≈36×');", "});",
               "SHOT(6.4, (s) => {", "  IMG('fable_official', 70, 330);", "  BIG(s, .45, 'Claude Fable 5.2');", "});",
               "SHOT(18.1, (s) => BARS(panel, frontierCode));", "SHOT(37.7, (s) => PRICE(8, 40));", "SHOT(51.0, (s) => META());",
               "render({ fps: 60, size: [1080, 1920] });"].join('\n');
  CODE(b, src, s, 0, {static: true, px: 27, scroll: 3.2});
  const r = E.o5(pr(s, .6, 1.2));
  X.save(); X.globalAlpha *= r;
  PANEL(130, 1040, 820, 190, {accent: ACC, fill: 'rgba(8,10,16,.95)', fill2: 'rgba(8,10,16,.95)'});
  T('همین ویدیو = کد', W / 2, 1160, 74, {f: 'fa', w: 900, spec: true});
  X.restore();
}, {tr: 'zoom', bg: 'void', name: 'meta'});
BEAT(LN(8).s + .6, 'the line lands');
BEAT(WF(8, 'کد').s, 'code');

// 10 — the call to action (the stage draws the comment card) over a quiet field of the three names
SHOT(LN(9).s - .25, (s, t) => {
  CAM(s, {z: 1.0, drift: 1});
  const names = ['Claude Fable 5.2', 'GPT-6 Astra', 'Gemini 4 Carbon', 'Claude Opus 5.5'];
  names.forEach((n, k) => T(n, W / 2 + osc(s + k * 1.7, .06, 90), 420 + k * 330, 64, {f: 'en', w: 800, col: SPEC[(k * 2 + 1) % 6], alpha: .16}));
  STREAM({x: 0, y: 1150, w: W, h: 500}, s, {seed: 11});
}, {tr: 'dissolve', bg: 'aurora', name: 'cta'});
BEAT(LN(9).s + .5, 'the word types');
BEAT(WF(9, 'کامنت').s, 'the comment word');
BEAT(LN(9).e + .65, 'the end card');
BEAT(WF(3, 'گرفته').s, 'Fable 49.1 punch');
