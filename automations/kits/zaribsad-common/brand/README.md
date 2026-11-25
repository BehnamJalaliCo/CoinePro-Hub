# Zarib100x (@Zarib100x) — the brand sheet (owner, 2026-11-26)

The page that was @zaribsad is now **@Zarib100x** (Instagram username `zarib100x`). Its name on screen, on the
cover, in the stories, the caption and the DM is **Zarib100x** — written exactly so (capital Z, «100x» with a small
x, no space, no «×»); the handle **@Zarib100x**. Never «Zarib ×100», «Zarib×100», «ضریب صد» or «@zaribsad» for
viewers (the hub's internal keys `zaribsad_*` and the kit folders keep their names).

## Colour — two corporate colours, three layers
| | name | hex | use |
|---|---|---|---|
| **brand 1** | Zarib Violet | `#8A3FFC` | the Zarib Line, chips, kickers, the HUD's progress, rims, the key light |
| **brand 2** | Obsidian | `#0A0814` | the ground of every frame, cover and story (a violet-black, never navy) |
| support | Platinum | `#EEEAF8` | text, the price line |
| support | Violet Light | `#B28CFF` | key words and «100x» on obsidian (reads at phone size) |
| support | Panel / Raised | `#141022` / `#1E1833` | glass panels |
| support | Muted | `#9A95B3` | labels, sources, the HUD's data |
| meaning | Up / Down / Flat | `#19C37D` / `#F2445A` / `#9A95B3` | ONLY numbers, candles, arrows, change chips |

**Why violet + obsidian.** The other pages own the rest: DotCoin mustard `#F3C242` + black, Pro-Chart black +
mustard `#D4A64A`, behnamjalali.tech ink + a rainbow spectrum (covers navy/electric blue), the old @zaribsad navy
`#030B26` + teal `#0FB5AE`. A saturated violet on a violet-black is free on all four, reads as premium and
nocturnal (private banking, a terminal at night), and — unlike gold, teal, blue or any green/red — it never
competes with the market's meaning colours: on a Zarib chart green is always up, red always down, and violet is
always the brand. The violet is a cool IBM-like `#8A3FFC` (blue-violet with red in it), not the blue-violet of
behnamjalali.tech's spectrum; it is never used as a gradient rainbow.

**The three layers** (as DotCoin's rule, with Zarib's colours): **brand** in every frame (≥ the HUD, the Zarib
Line or a chip; the cold open, the end slate and the cover are mostly brand) · **content** free inside the
plates (graded to obsidian with violet light; no other dominant purple/magenta, no teal/navy, no mustard/gold) ·
**meaning** fixed (above).

Delivery: Instagram re-encodes to 8-bit SDR; desk.js renders sRGB/BT.709 with an invisible ±1 dither so the
obsidian gradients never band. Never visible grain.

## Type
- **Persian: IRANYekanX Pro** (/home/studio/kits/fonts-pro, the owner's licence; the Latin-digit files — desk.js and
  the tools write Persian digits themselves). ExtraBlack 950 for headlines and the cover title, ExtraBold 800 for
  captions and panel titles, Bold/Regular for body, Light for quiet labels.
- **Data: IBM Plex Mono** (COMMON/fonts, OFL) — tickers, the HUD, panel tabs, axis labels, the handle; upper case,
  tracked +2–4 px.
- **Big Latin numbers and the wordmark: IBM Plex Sans Condensed Bold** (COMMON/fonts, OFL) — $70.48, −48.8%,
  **Zarib**`100x`.
- Digits: Persian inside Persian text; Latin on the instruments (prices, %); never mixed in one run.

## The mark and the lockup
- `profile_round.png` (round, alpha outside) / `profile.jpg` (1062², the square original): the page's profile
  photo — the owner in a suit. **These files are still the OLD @zaribsad photo** (taken 2026-11-15, the green
  background). Keep using them; when @Zarib100x has its own profile picture, take it from Instagram via IG-Hub
  (1080², the same two files, the same names) and re-run `tools/make_board.py`.
- **The lockup:** the round photo with a violet ring (ring = 3.5 % of its diameter) + **Zarib**`100x` (Plex Sans
  Condensed Bold, «100x» in Violet Light) + «بهنام جلالی» (IRANYekanX Pro Regular, Muted) under it. Small form
  (HUD, stories, cover foot): the photo + the wordmark on one line. Nothing else: no slogan, no TradeYar logo.
- `board.png` — this sheet as a picture (colours, type, the HUD, sample frames, the sample cover, the
  four pages side by side). `tokens.json` — the colours for code.
