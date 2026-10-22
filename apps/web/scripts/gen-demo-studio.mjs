#!/usr/bin/env node
// Demo media for the media studio in mock mode (contract §22): two short renders, a UI-redesign screenshot and the voice bake-off's
// clips, written to public/demo/. Development only: nothing in production points at these files (the fixtures module that names
// them is aliased away outside mock mode).
//
// The renders are made the way §22.2 says the hub makes them: the composition is one HTML document (CSS animations, SVG, IRANYekanX,
// the company's palette), headless Chromium renders it frame by frame with the animations' clock set by hand, and ffmpeg muxes the
// narration. The voices are stand-ins: a speech-like murmur per candidate (no TTS runs here), each with its own pitch and timbre so the
// blind test has something to tell apart.
//
// Run from apps/web: `node scripts/gen-demo-studio.mjs`. Needs ffmpeg and the Playwright Chromium already on the machine. Each file stays
// well under 300 KB.

import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'public/demo');
const TMP = mkdtempSync(join(process.env.HQ_TMP ?? tmpdir(), 'hq-studio-'));
const font = (f) => `data:font/woff2;base64,${readFileSync(join(ROOT, 'public/fonts', f)).toString('base64')}`;
const FONTS = `@font-face{font-family:"YekanFa";src:url("${font('iranyekanx-fanum.woff2')}") format("woff2");font-weight:100 1000}
@font-face{font-family:"YekanLat";src:url("${font('iranyekanx-latin.woff2')}") format("woff2");font-weight:100 1000}`;
const ff = (...args) => execFileSync('ffmpeg', ['-v', 'error', '-y', ...args], { stdio: 'inherit' });

// ------------------------------------------------------------------ voices --
/** A deterministic 0..1 sequence. */
function rng(seed) { let s = seed >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2 ** 32; }; }

/**
 * A speech-like murmur: syllables (a voiced tone under a soft envelope) in phrases, the pitch falling across each phrase.
 * `f0` sets the speaker's pitch, `bright` the weight of the upper harmonics, `breath` a little noise (the neural voices), `rate` the pace.
 */
function murmur({ seconds, f0, bright = 0.5, breath = 0, rate = 1, seed = 1, phrases = null }) {
  const sr = 16000;
  const r = rng(seed);
  const spans = phrases ?? [[0.15, seconds - 0.2]];
  const sylls = [];
  for (const [a, b] of spans) {
    let t = a;
    while (t < b - 0.12) {
      const du = (0.12 + r() * 0.16) / rate;
      const pos = (t - a) / Math.max(0.01, b - a);
      sylls.push({ t, du, f: f0 * (1.12 - 0.22 * pos) * (0.94 + r() * 0.12) });
      t += du + (0.02 + r() * 0.12) / rate;
    }
  }
  const n = Math.round(sr * seconds);
  const pcm = Buffer.alloc(n * 2);
  let k = 0;
  for (let i = 0; i < n; i++) {
    const s = i / sr;
    while (k < sylls.length && sylls[k].t + sylls[k].du < s) k++;
    let v = 0;
    for (let j = Math.max(0, k - 1); j < Math.min(sylls.length, k + 2); j++) {
      const y = sylls[j];
      if (s < y.t || s >= y.t + y.du) continue;
      const env = Math.sin((Math.PI * (s - y.t)) / y.du) ** 1.5;
      const vib = 1 + 0.012 * Math.sin(2 * Math.PI * 5.2 * s);
      const ph = 2 * Math.PI * y.f * vib * s;
      v += env * (0.55 * Math.sin(ph) + 0.3 * bright * Math.sin(2 * ph) + 0.18 * bright * Math.sin(3 * ph) + 0.08 * bright * Math.sin(5 * ph));
      if (breath) v += env * breath * (r() * 2 - 1) * 0.25;
    }
    pcm.writeInt16LE(Math.round(Math.max(-1, Math.min(1, v * 0.5)) * 32767), i * 2);
  }
  const head = Buffer.alloc(44);
  head.write('RIFF', 0); head.writeUInt32LE(36 + pcm.length, 4); head.write('WAVE', 8); head.write('fmt ', 12);
  head.writeUInt32LE(16, 16); head.writeUInt16LE(1, 20); head.writeUInt16LE(1, 22); head.writeUInt32LE(sr, 24); head.writeUInt32LE(sr * 2, 28);
  head.writeUInt16LE(2, 32); head.writeUInt16LE(16, 34); head.write('data', 36); head.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([head, pcm]);
}
function m4a(wav, out, kbps = 24) {
  const w = join(TMP, 'v.wav');
  writeFileSync(w, wav);
  ff('-i', w, '-c:a', 'aac', '-b:a', `${kbps}k`, '-ac', '1', '-map_metadata', '-1', '-fflags', '+bitexact', '-flags:a', '+bitexact', out);
}

// The candidates of §22.3 that speak (ManaTTS is not trained yet: it has no clips).
const VOICES = {
  'piper-amir': { f0: 112, bright: 0.35, rate: 1.05, seed: 11 },
  'piper-gyro': { f0: 128, bright: 0.3, rate: 1.1, seed: 12 },
  'xtts-speaker': { f0: 104, bright: 0.75, breath: 0.12, rate: 0.95, seed: 13 },
  'xtts-owner': { f0: 121, bright: 0.68, breath: 0.1, rate: 0.98, seed: 14 },
  'chatterbox-speaker': { f0: 205, bright: 0.6, breath: 0.14, rate: 1, seed: 15 },
  'chatterbox-owner': { f0: 119, bright: 0.55, breath: 0.16, rate: 1.02, seed: 16 },
};
const SCRIPTS = { numbers: 4.2, crypto: 4.6, long: 6.4 };

// ------------------------------------------------------------------ renders --
async function render(page, { html, width, height, seconds, fps, name, poster, audio }) {
  await page.setViewportSize({ width, height });
  await page.setContent(html, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  const dir = join(TMP, name);
  mkdirSync(dir, { recursive: true });
  const frames = Math.round(seconds * fps);
  for (let i = 0; i < frames; i++) {
    // The worker's clock: every animation paused and set to this frame's time, never a live recording.
    await page.evaluate((ms) => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = ms; } }, (i * 1000) / fps);
    await page.screenshot({ path: join(dir, `f${String(i).padStart(4, '0')}.png`) });
  }
  const mp4 = join(OUT, `${name}.mp4`);
  const video = ['-framerate', String(fps), '-i', join(dir, 'f%04d.png')];
  const enc = ['-c:v', 'libx264', '-preset', 'veryslow', '-tune', 'animation', '-crf', '31', '-pix_fmt', 'yuv420p', '-threads', '1', '-movflags', '+faststart', '-map_metadata', '-1'];
  if (audio) ff(...video, '-i', audio, ...enc, '-c:a', 'aac', '-b:a', '32k', '-ac', '1', '-shortest', mp4);
  else ff(...video, ...enc, '-an', mp4);
  ff('-i', join(dir, `f${String(Math.round(poster * fps)).padStart(4, '0')}.png`), '-c:v', 'libwebp', '-quality', '78', join(OUT, `${name}-poster.webp`));
}

const BASE = (w, h, bg) => `<!doctype html><html dir="rtl" lang="fa"><head><meta charset="utf-8"><style>${FONTS}
*{box-sizing:border-box;margin:0;padding:0}html,body{width:${w}px;height:${h}px;overflow:hidden}
body{font-family:"YekanFa";color:#F2EEE4;background:${bg};position:relative;-webkit-font-smoothing:antialiased}
.lat{font-family:"YekanLat";direction:ltr;unicode-bidi:isolate;font-feature-settings:"tnum" 1}
.abs{position:absolute}
@keyframes in{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
@keyframes out{from{opacity:1}to{opacity:0}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes draw{from{stroke-dashoffset:var(--len)}to{stroke-dashoffset:0}}
@keyframes wipe{from{clip-path:inset(0 0 0 100%)}to{clip-path:inset(0 0 0 0)}}
@keyframes drift{from{transform:translateX(0)}to{transform:translateX(-60px)}}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.04)}}
</style></head><body>`;
const an = (name, delay, dur, extra = '') => `animation:${name} ${dur}s ${delay}s both cubic-bezier(.2,.7,.2,1)${extra}`;
/** One caption line, shown from `a` to `b` seconds. */
const cap = (a, b, text) => `<div class="abs" style="left:22px;right:22px;bottom:86px;text-align:center;font-size:15px;line-height:1.7;font-weight:600;
  background:rgba(8,10,16,.66);border-radius:10px;padding:6px 10px;opacity:0;animation:in .25s ${a}s both, out .2s ${b}s forwards">${text}</div>`;

/** The FX weekly-levels reel: one composition, two episodes (support levels, then resistance levels). */
const FX_EPISODES = {
  'fx-reel-levels': {
    ep: '۱۲', title: 'طلا این هفته<br>کجا می‌ایستد؟', hook: 'طلا این هفته کجا می‌ایستد؟', what: 'حمایت', ord: ['حمایت اول', 'حمایت دوم', 'حمایت سوم'], levels: [2318, 2296, 2274],
    line: '20,20 55,40 90,34 125,66 160,58 195,120 228,164 258,150 290,128 320,112 340,104',
    card: 'حمایت جایی است که خریدارها قبلاً وارد شده‌اند؛ شکستنش یعنی رفتن سراغ سطح بعدی.',
    caps: ['سه سطح حمایت از بالا به پایین:', 'دو هزار و سیصد و هجده، دو هزار و دویست و نود و شش، و دو هزار و دویست و هفتاد و چهار.', 'شکستن هر سطح یعنی رفتن سراغ سطح بعدی.'],
  },
  'fx-reel-resist': {
    ep: '۱۳', title: 'سقف طلا<br>این هفته کجاست؟', hook: 'سقف طلا این هفته کجاست؟', what: 'مقاومت', ord: ['مقاومت سوم', 'مقاومت دوم', 'مقاومت اول'], levels: [2385, 2362, 2340],
    line: '150,246 175,230 200,236 225,206 250,196 270,160 290,150 310,124 330,116 345,122',
    card: 'مقاومت جایی است که فروشنده‌ها قبلاً بیرون آمده‌اند؛ عبور از آن یعنی رفتن سراغ سطح بالاتر.',
    caps: ['سه سطح مقاومت از پایین به بالا:', 'دو هزار و سیصد و چهل، دو هزار و سیصد و شصت و دو، و دو هزار و سیصد و هشتاد و پنج.', 'عبور از هر سطح یعنی رفتن سراغ سطح بالاتر.'],
  },
};
function fxReel(name) {
  const e = FX_EPISODES[name];
  const W = 360, H = 640;
  const candles = Array.from({ length: 16 }, (_, i) => {
    const up = [1, 1, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1][i];
    const h = 22 + ((i * 37) % 40);
    const y = 300 - i * 7 + (up ? 0 : 14);
    return `<div class="abs" style="left:${14 + i * 21}px;top:${y}px;width:11px;height:${h}px;border-radius:2px;background:${up ? '#D8A848' : '#C94B5B'};opacity:.5;transform-origin:bottom;${an('grow', 0.05 * i, 0.5)}"></div>`;
  }).join('');
  const levels = e.levels.map((v, i) => [v, 236 + i * 50, e.ord[i]]).map(([v, y, fa], i) =>
    `<div class="abs" style="left:24px;right:24px;top:${y}px;height:0;border-top:2px dashed #D8A848;opacity:0;${an('in', 3.4 + i * 0.6, 0.4)}, out .3s 6.2s forwards"></div>
     <div class="abs" style="left:24px;top:${y - 26}px;display:flex;gap:8px;align-items:center;opacity:0;${an('in', 3.5 + i * 0.6, 0.4)}, out .3s 6.2s forwards">
       <span style="font-size:13px;color:#C9C2B2">${fa}</span><span class="lat" style="font-size:16px;font-weight:700;color:#D8A848">${v.toLocaleString('en-US')}</span></div>`).join('');
  return `${BASE(W, H, 'linear-gradient(160deg,#0E1422 0%,#141B2C 55%,#3A2A0C 100%)')}
  <div class="abs" style="top:22px;left:22px;font-size:13px;font-weight:700;color:#D8A848" ><span class="lat">CoinePro FX</span></div>
  <div class="abs" style="top:22px;right:22px;font-size:12px;color:#C9C2B2">سطح‌های هفته · قسمت ${e.ep}</div>
  <div class="abs" style="inset:0;${an('out', 2.4, 0.35, ', none')}">${candles}</div>
  <div class="abs" style="top:120px;right:24px;left:24px;font-size:34px;font-weight:800;line-height:1.35;${an('in', 0.25, 0.6)}, out .3s 2.3s forwards">${e.title}</div>
  <svg class="abs" style="left:0;top:120px;opacity:0;${an('in', 2.5, 0.3)}, out .3s 6.2s forwards" width="${W}" height="260" viewBox="0 0 ${W} 260">
    <polyline points="${e.line}" fill="none" stroke="#F2EEE4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"
      style="--len:520;stroke-dasharray:520;${an('draw', 2.6, 1.2)}"/>
  </svg>
  ${levels}
  <div class="abs" style="top:150px;right:24px;left:24px;padding:20px;border-radius:18px;background:rgba(216,168,72,.12);border:1px solid rgba(216,168,72,.45);
    font-size:20px;line-height:1.8;font-weight:600;opacity:0;${an('in', 6.4, 0.5)}, out .3s 8.3s forwards">${e.card}</div>
  <div class="abs" style="top:170px;right:24px;left:24px;text-align:center;opacity:0;${an('in', 8.5, 0.5)}">
    <div style="font-size:26px;font-weight:800;line-height:1.5">تحلیل کامل هفته<br>در کانال تلگرام</div>
    <div style="margin:22px auto 0;width:max-content;padding:10px 22px;border-radius:999px;background:#D8A848;color:#0B0D14;font-weight:800;font-size:16px;${an('pulse', 9, 1)}">عضو شو</div>
  </div>
  <div class="abs" style="left:22px;right:22px;bottom:30px;text-align:center;font-size:11px;line-height:1.6;color:#C9C2B2">آموزشی است، نه توصیه‌ی خرید و فروش؛ معامله ریسک دارد.</div>
  ${cap(0.3, 2.3, e.hook)}
  ${cap(2.6, 4.4, e.caps[0])}
  ${cap(4.5, 6.2, e.caps[1])}
  ${cap(6.5, 8.3, e.caps[2])}
  ${cap(8.6, 9.9, 'این آموزش است، نه توصیه.')}
  </body></html>`;
}

function tyStory() {
  const W = 360, H = 640;
  const waves = Array.from({ length: 6 }, (_, k) => {
    const d = Array.from({ length: 31 }, (_, i) => `${i * 14},${150 + k * 38 + Math.round(Math.sin(i / (2 + k * 0.4) + k) * (14 + k * 3))}`).join(' ');
    return `<polyline points="${d}" fill="none" stroke="${k % 2 ? '#00AB8E' : '#F2EEE4'}" stroke-opacity="${0.18 + k * 0.08}" stroke-width="3"/>`;
  }).join('');
  return `${BASE(W, H, 'linear-gradient(170deg,#06221E 0%,#0B3B4A 100%)')}
  <svg class="abs" style="left:0;top:0;${an('drift', 0, 6, ', none')}" width="${W + 80}" height="${H}">${waves}</svg>
  <div class="abs" style="top:24px;left:22px;font-size:13px;font-weight:700;color:#00AB8E"><span class="lat">TradeYar</span></div>
  <div class="abs" style="top:24px;right:22px;font-size:12px;color:#BFD6D2">یک مفهوم در ۳۰ ثانیه</div>
  <div class="abs" style="top:300px;right:24px;left:24px">
    <div style="font-size:32px;font-weight:800;${an('in', 0.3, 0.5)}">حد ضرر چیست؟</div>
    <div style="margin-top:14px;font-size:17px;line-height:1.9;color:#E3EEEC;${an('in', 1.1, 0.5)}">جایی که از قبل تعیین می‌کنی اگر بازار خلاف انتظارت رفت، بیرون بیایی؛ پیش از ورود، نه بعد از ضرر.</div>
    <div style="margin-top:22px;width:max-content;padding:9px 20px;border-radius:999px;background:#00AB8E;color:#04231F;font-weight:800;font-size:15px;${an('in', 2.4, 0.4)}">ادامه در کانال</div>
  </div>
  <div class="abs" style="left:22px;right:22px;bottom:34px;text-align:center;font-size:11px;line-height:1.6;color:#BFD6D2">آموزشی است، نه توصیه‌ی معامله؛ معامله ریسک دارد.</div>
  </body></html>`;
}

function pcLanding() {
  const W = 1280, H = 800;
  const card = (t, b) => `<div style="flex:1;padding:22px;border-radius:16px;background:rgba(255,255,255,.04);border:1px solid rgba(101,145,225,.28)"><div style="font-size:18px;font-weight:700">${t}</div><div style="margin-top:8px;font-size:14px;line-height:1.8;color:#B7C2DA">${b}</div></div>`;
  // Candles along a gentle up-trend: body and wick, blue up, red down.
  let price = 150;
  const bars = Array.from({ length: 34 }, (_, i) => {
    const up = (i * 7) % 5 > 1;
    const body = 8 + ((i * 53) % 26);
    const o = price, c = up ? price - body : price + body * 0.7;
    price = c + (up ? 2 : -1);
    const top = Math.min(o, c), h = Math.abs(o - c), x = 16 + i * 15, col = up ? '#6591E1' : '#C94B5B';
    return `<line x1="${x + 4}" x2="${x + 4}" y1="${top - 6 - (i % 4) * 2}" y2="${top + h + 5 + (i % 3) * 2}" stroke="${col}" stroke-width="1.5"/><rect x="${x}" y="${top}" width="8" height="${Math.max(2, h)}" rx="1.5" fill="${col}"/>`;
  }).join('');
  return `${BASE(W, H, 'linear-gradient(160deg,#101830 0%,#1A2140 60%,#2A1E40 100%)')}
  <div style="display:flex;align-items:center;gap:28px;padding:22px 56px;border-bottom:1px solid rgba(255,255,255,.07)">
    <span class="lat" style="font-size:20px;font-weight:800;color:#6591E1">Pro-Chart</span>
    <span style="font-size:14px;color:#B7C2DA">ترمینال</span><span style="font-size:14px;color:#B7C2DA">اندیکاتورها</span><span style="font-size:14px;color:#B7C2DA">آموزش</span><span style="font-size:14px;color:#B7C2DA">قیمت‌ها</span>
    <span style="margin-right:auto;padding:9px 18px;border-radius:10px;background:#6591E1;color:#0B1022;font-weight:800;font-size:14px">شروع رایگان</span>
  </div>
  <div style="display:flex;gap:48px;padding:56px">
    <div style="flex:1;padding-top:24px">
      <div style="font-size:14px;color:#6591E1;font-weight:700">نسخه‌ی تازه‌ی ترمینال</div>
      <div style="margin-top:12px;font-size:44px;font-weight:800;line-height:1.4">نمودار سریع‌تر،<br>تصمیم آرام‌تر</div>
      <div style="margin-top:16px;font-size:17px;line-height:1.9;color:#B7C2DA;max-width:460px">بارگذاری نمودار در کمتر از یک ثانیه، اندیکاتورهای فارسی و هشدار قیمت روی همه‌ی بازارها.</div>
      <div style="display:flex;gap:12px;margin-top:28px"><span style="padding:12px 22px;border-radius:12px;background:#6591E1;color:#0B1022;font-weight:800">ترمینال را باز کن</span><span style="padding:12px 22px;border-radius:12px;border:1px solid rgba(255,255,255,.2)">ویدیوی معرفی</span></div>
    </div>
    <div style="flex:1.1;padding:20px;border-radius:20px;background:rgba(11,16,34,.75);border:1px solid rgba(101,145,225,.3)">
      <div style="display:flex;gap:10px;font-size:13px;color:#B7C2DA"><span class="lat" style="color:#F2EEE4;font-weight:700">XAUUSD</span><span class="lat">H1</span><span class="lat" style="color:#6591E1">2,318.40</span><span class="lat" style="color:#5BC08A">+0.42%</span></div>
      <svg width="540" height="300" viewBox="0 -20 540 200" style="margin-top:12px">${bars}</svg>
    </div>
  </div>
  <div style="display:flex;gap:18px;padding:0 56px">${card('اندیکاتور فارسی', 'هر اندیکاتور با توضیح فارسی و مثال روی نمودار.')}${card('هشدار قیمت', 'روی تلگرام و اپ، بدون نیاز به باز بودن ترمینال.')}${card('چیدمان شخصی', 'چند نمودار کنار هم، ذخیره روی همه‌ی دستگاه‌ها.')}</div>
  <div style="display:flex;justify-content:space-between;margin:34px 56px 0;padding-top:22px;border-top:1px solid rgba(255,255,255,.07);font-size:14px;color:#B7C2DA">
    <span>بیش از <span class="lat" style="color:#F2EEE4;font-weight:700">120</span> اندیکاتور</span><span>بارگذاری زیر <span class="lat" style="color:#F2EEE4;font-weight:700">1s</span></span><span>هشدار روی <span class="lat" style="color:#F2EEE4;font-weight:700">3</span> کانال</span></div>
  </body></html>`;
}

async function main() {
  mkdirSync(join(OUT, 'voice'), { recursive: true });
  for (const [v, p] of Object.entries(VOICES)) for (const [s, secs] of Object.entries(SCRIPTS)) m4a(murmur({ seconds: secs, ...p, seed: p.seed * 7 + secs * 10 }), join(OUT, 'voice', `${v}-${s}.m4a`));
  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  for (const [i, name] of Object.keys(FX_EPISODES).entries()) {
    // The reel's narration, in the voice the owner chose, one phrase per caption.
    const narration = join(OUT, `${name}-voice.m4a`);
    m4a(murmur({ seconds: 10, ...VOICES['xtts-owner'], seed: 40 + i, phrases: [[0.3, 2.2], [2.6, 4.3], [4.5, 6.1], [6.5, 8.2], [8.6, 9.8]] }), narration, 32);
    await render(page, { html: fxReel(name), width: 360, height: 640, seconds: 10, fps: 24, name, poster: 1.4, audio: narration });
  }
  await render(page, { html: tyStory(), width: 360, height: 640, seconds: 6, fps: 24, name: 'ty-story-stoploss', poster: 3 });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.setContent(pcLanding(), { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  const shot = join(TMP, 'pc.png');
  await page.screenshot({ path: shot });
  ff('-i', shot, '-vf', 'scale=960:-1', '-c:v', 'libwebp', '-quality', '80', join(OUT, 'pc-landing-redesign.webp'));
  await browser.close();
  rmSync(TMP, { recursive: true, force: true });
  for (const f of ['fx-reel-levels.mp4', 'fx-reel-levels-poster.webp', 'fx-reel-levels-voice.m4a', 'fx-reel-resist.mp4', 'fx-reel-resist-poster.webp', 'fx-reel-resist-voice.m4a', 'ty-story-stoploss.mp4', 'ty-story-stoploss-poster.webp', 'pc-landing-redesign.webp']) {
    console.log(`${f}\t${Math.round(statSync(join(OUT, f)).size / 1024)} KB`);
  }
}

await main();
