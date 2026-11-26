# THE FILE — the motion library (story.js), its engine and its sound

**Never restyle these per reel.** The file bar, the colours, the fonts, the marker, the captions, the lockup, the
end slate and the four transitions ARE the brand; a reel adds its own shots on top.

## Build a reel
1. `motion/scene.js` in your day's folder: your shots, then `STORY.reel({...})` (the contract is story.js's
   header). `motion/sample/` is a working sample (FILE 000, the bitcoin pizza) — an example of the API, never a
   reel's data or look: yours is richer, with ≥ 7 plates and its own story.
2. Inputs the engine loads by itself: `direction/word_times.json` (→ `DATA.lines`), `qc/facts.json` (`DATA.facts`),
   every picture under `assets/` (→ `IMG['assets/…']`), the page's mark.
3. `PY -I COMMON/motion/story_engine.py --test t1,t2,…` → build/story_sheet.jpg, build/story_phone.jpg,
   qc/texts.json (~70 ms a frame). `--render --fps 60 --workers 2` (chunks; a stopped render resumes), then
   `--encode --audio build/mix.wav --out out/video.mp4`. A 90 s reel at 60 fps renders in about 8–11 minutes.
4. Sound: `build/asr/venv/bin/python -I COMMON/motion/story_audio.py direction/sound.json qc/voice_final.wav build/mix.wav`.

## The API (all in story.js; every frame a pure function of t)
- **World:** `ground(t,{lx,ly,light,ledger})` (the dark archive room: ink navy, one warm lamp, ledger rules),
  `vignette(a)`, `plate(src,{p,push,pan,tone:'color'|'duo'|'mono',grade})` (Ken Burns + the grade),
  `parallax(back,front,{p,back,front:{cx,cy,h,dx,dy,s0,s1}})` (2.5D), `cutout(src,cx,cy,h)`.
- **Evidence:** `doc(key,t,x,y,w,h,{t0,kind:'paper'|'photo'|'card',rot,from},(g,w,h)=>…)` (lands with a shadow;
  draw inside with `g`; `photoIn(g,w,h,src,{tone,caption})` for a print), `clipping(key,t,x,y,w,h,{t0,rot,paper,
  date,headline:[…]})`, `stamp(t,'ورشکسته',cx,cy,t0,{rot,col})`, `redact(t,x,y,w,h,t0)`.
- **Marker & hand:** `marker(t,x,y,w,h,t0)` (THE ORANGE MARKER), `circleMark(t,cx,cy,rx,ry,t0)`, `arrow(t,[[x,y]…],t0)`.
- **Type:** `headline(t,lines,x,y,t0,{px,align})` with `[key]` on the marker, `slam(t,'words'|[{w,at}],t0,{px,cy,keys})`,
  `typeLine(t,s,x,y,t0,{px,kind})`, `kicker(t,num,label,t0)`, `lowerThird(t,name,role,t0)`,
  `dateline(t,'1994','نیویورک',t0)`, `quote(t,lines,who,x,y,t0)`, `txt(s,x,y,{px,w,kind:'A'|'R'|'M',col,align,maxW,g})`,
  `wrap(s,maxW,{kind,px,w})`.
- **Numbers:** `counter(t,value,x,y,t0,dur,{px,prefix,suffix,dec,latin,unit,change})`, `changeChip(t,pct,x,y,t0)`,
  `bars(t,[{label,v,show}],x,y,w,rowH,t0,{hero})`, `dotGrid(t,n,total,x,y,w,t0,dur,{cols})`,
  `lineChart(t,series,x,y,w,h,t0,dur,{marks:[{i,label}]})`, `timeline(t,[{year,label}],x,y,w,t0,dur)`.
- **Places:** `mapMarks(t,[{x,y,label,at}],[{from,to,at,dur}])` over a map plate, `versus(t,srcA,srcB,labA,labB,t0)`.
- **Camera:** `rig(p,{s0,s1,dx0,dx1,dy0,dy1,r0,r1,cx,cy})` inside a shot (wrap in X.save/X.restore).
- **Brand:** `hud` (the file bar), `wordmark`, `lockup`, `endSlate` — drawn by `reel()` itself:
  `STORY.reel({shots, caps, hud: {file: NNN, title: '…'}, end: {line: '…', sub: '…', at}, END})`.
- **Transitions:** a shot's `tr`: 'swipe' | 'shutter' | 'zoom' | 'page' | 'cut'.
- **Captions:** `capsFromWords(DATA.lines,{keys:[…]})` → `STORY.reel({caps})`; drawn in the band y 1380–1540.
