# THE DESK — the motion library (desk.js), its engine and its sound

**Never restyle these per reel.** The HUD, the colours, the fonts, the captions, the lockup, the end slate and the
four transitions ARE the brand; a reel adds its own shots on top.

## Build a reel
1. `motion/scene.js` in your day's folder: your shots, then `DESK.reel({...})` (the contract is desk.js's header).
   `motion/sample/motion/scene.js` is a working sample (SOL, the data of 2026-11-25 — an example of the API, never
   a reel's data or a reel's look: yours must be richer, with plates).
2. Inputs the engine loads by itself: `direction/word_times.json` (→ `DATA.lines`), `qc/facts.json` (`DATA.facts`,
   with `series_1y`), `qc/news.json` (`DATA.news`), `qc/tape.json` (`DATA.tape`, the HUD tape), every picture under
   `assets/` (→ `IMG['assets/…']`), the page's mark.
3. `PY -I COMMON/motion/desk_engine.py --test t1,t2,…` → build/desk_sheet.jpg, build/desk_phone.jpg, qc/texts.json
   (~80 ms a frame). `--render --fps 60 --workers 2` (chunks; a stopped render resumes), then
   `--encode --audio build/mix.wav --out out/video.mp4`. A 70 s reel at 60 fps renders in about 6–8 minutes.
4. Sound: `build/asr/venv/bin/python -I COMMON/motion/desk_audio.py direction/sound.json qc/voice_final.wav build/mix.wav`.

## The API (all in desk.js; every frame a pure function of t)
- World: `ground(t,{lx,ly,light,horizon,grid})`, `plate(src,{x,y,w,h,p,push,pan,grade})`, `cutout(src,cx,cy,h)`.
- Panels: `panel(key,t,x,y,w,h,{t0,from,ry,tab,title},(g,w,h)=>{…})` docks a glass panel on the 3D wall; draw
  inside with `g` (pass `{g}` to the instruments); `persp` for any card in perspective.
- Colours: `Z.gr` wine-black ground, `Z.pn`/`Z.pn2` panels, `Z.ac` Zarib Mint, `Z.ox`/`Z.oxL` oxblood, `Z.tx` ivory,
  `Z.mu` warm grey, `Z.up`/`Z.dn` meaning — ONLY with ▲/▼ (brand/README.md); mint never on a value.
- Instruments: `odometer(t,value,x,y,t0,dur,{px,kind:'C'|'F',prefix,suffix,dec,col,align,change})` (`change: true`
  for any up/down value: ▲/▼, the sign and the meaning colour),
  `changeChip(t,pct,x,y,t0)`, `lineChart(t,series,x,y,w,h,t0,dur,{g,levels,smooth})`,
  `returnBars(t,rows,x,y,w,h,t0,{g})`, `gauge(t,value,cx,cy,r,t0,{g})`.
- Type: `txt(s,x,y,{px,w,kind:'F'|'M'|'C',col,align,maxW,track})` (Persian digits and Latin isolation done for
  you), `headline(t,lines,x,y,t0,{px})` with `[key]` chips, `kicker(t,num,label,t0)`, `zline(t,y,t0,{label})`.
- Captions: `capsFromWords(DATA.lines,{keys:[…]})` → `DESK.reel({caps})`; drawn in the band y 1380–1540.
- Camera: `rig(p,{s0,s1,dx0,dx1,dy0,dy1,cx,cy})` inside a shot (wrap in X.save/X.restore).
- Brand: `hud`, `tape`, `lockup(cx,cy,size)`, `endSlate` — drawn by `reel()` itself.
- Transitions: a shot's `tr` ('blade' | 'slats' | 'aperture' | 'slide' | 'cut') and `trOpt` ({cx,cy} for aperture).
