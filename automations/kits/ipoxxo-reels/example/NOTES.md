# The example reel — NOTES (2026-11-17, built by the hub's Claude through this kit; not published)

## Topic and facts
- Topic: «عمیق‌ترین چاه دنیا» — the Kola Superdeep Borehole (row #1 of topics.md, status `sample:2026-11-17`).
- Facts used, each checked on its source the same day:
  - 12,262 m true vertical depth, reached in 1989; drilling began 24 May 1970 (19 years); the deepest
    borehole by vertical depth (longer wells, e.g. Al Shaheen 12,289 m, are mostly horizontal).
    https://en.wikipedia.org/wiki/Kola_Superdeep_Borehole
  - Water 3–6 km down; microscopic plankton fossils at 6 km; the expected basalt at 7 km never found (more
    granite); 180 °C at the bottom. (same page)
  - 180 °C instead of the predicted ~100 °C; the hot, porous rock behaved more like a plastic than a solid
    and tended to flow closed when the bit was pulled out: drilling stopped (the voice says only what all
    sources agree on). https://www.earthdate.org/ (EarthDate 216) · the 2017 version of the Wikipedia article.
  - Everest 8,849 m (12,262 − 8,849 = 3,413 m: «تازه سه کیلومتر هم جا داره»); Earth's mean radius 6,371 km
    (12.262 / 6,371 = 0.19 %: «دو دهم درصد»); Milad tower 435 m; Damavand about 5,610 m.
  - Left out on purpose: the end year (sources say 1992 or 1995) and every «well to hell» rumour.

## Voice (Cruz, speech.make path of the hub; the whole script in one call each time)
- Take 1: 59 s (138 words) — too long → the script cut to 112 words.
- Take 2: 52.8 s, but the brand heard as «آی پیک سو» and «معما» as «مهم» → the sponsor line respelled
  («آی پی اوکسو», «وی پی اِنِ», three spellings probed alone: this one heard right) and «معما» → «راز».
- Take 3: words right, but audio_qc: 1 click + 1 burst → remade. Take 4: 1 click → remade.
  Take 5: clean audio, but a WHOLE line missing in the ASR (the basalt line dropped) → rejected.
  **Take 6: 0/0/0, every line heard**, the brand «ای پی اکسو», «وی پی این» → pauses ≤ 0.40 s (voice_seams)
  → assemble → qc/voice_final.wav 54.16 s, 0 clicks, 0 cuts, 0 bursts.
- The sponsor line takes 5.9 s with Cruz (47.5–53.4 s); 3–4 s would need dropping words of the owner's line.

## Build, QC and what was redone
- Round 1 stills: the dive and the 3 / 6 km shots were flat code bands (5/10) → a ChatGPT strata still as the
  section, scrolled with the km marks, landmark heights passing by; Everest's label hid under the badge and its
  bracket text was cut off at the left edge → Everest starts upright in the middle, the bracket on the right;
  the plastic-rock walls read as brown boxes → the drill picture itself flows in strips and an iris closes;
  the planet was off-centre under the «۰٫۲٪» → measured globe, smaller, the radius line inside.
- Engine fixes found on the way (now in the kit): a still under a tiny rotation left a navy strip at the
  bottom (the clamp skipped rotated plates); Chromium measures a lone space as 0 px, so caption words glued
  («حالاکندن») → a fixed space; the caption pop overshot into its neighbour → no overshoot; years printed with
  a thousands mark («۱٬۹۷۰») → `fa(n, 0, false)`; «°» flipped side in RTL → dropped (the unit is a line below).
- Music bed raised 3 dB (it sat 23 dB under the voice in the pauses).
- Shot scores (final): hook 9 · dive 8.5 · Everest 8.5 · station 8 · stop 8 · «چرا؟» 9 · 3 km 8 · water 8 ·
  fossils 8.5 · basalt 8 · 180 8.5 · plastic 8 · planet 8.5 · sponsor/end 9.
- Retention: hook at 0.0 s (title + the cap, the voice at 0.33 s) · the question at 16.6 s, paid at 33.4 s
  (60 %) and 37.5–42.6 s, the kicker at 43–47 s, the sponsor at 47.5 s · longest stretch without an
  interrupt 2.74 s · no dead frame · the end card on the hook's still.
