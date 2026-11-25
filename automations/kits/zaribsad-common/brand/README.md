# Zarib100x (@Zarib100x) — the brand sheet (owner, 2026-11-26)

The page that was @zaribsad is now **@Zarib100x** (Instagram username `zarib100x`). Its name on screen, on the
cover, in the stories, the caption and the DM is **Zarib100x** — written exactly so (capital Z, «100x» with a small
x, no space, no «×»); the handle **@Zarib100x**. Never «Zarib ×100», «Zarib×100», «ضریب صد» or «@zaribsad» for
viewers (the hub's internal keys `zaribsad_*` and the kit folders keep their names).

## Colour — two corporate colours from the profile photo, three layers (owner, 2026-11-26: «رنگ سازمانی رو عوض کن و یه چیز خوب بذار»)
As DotCoin's mustard comes from its profile photo, Zarib100x's two colours come from its own: sampled from
`profile.jpg` — the backdrop and the suit.

| | name | hex | use |
|---|---|---|---|
| **brand 1** | **Zarib Mint** | `#83CAAD` | sampled from the backdrop: the signature accent — chips with WORDS (dark letters), the Zarib Line, the HUD's progress, kickers, the ring of the mark, «100x», the cover's arch |
| **brand 2** | **Oxblood** | `#461A23` | sampled from the suit (lit side): the brand's light and fills — the key light of every ground, panels' warmth, big brand fields |
| ground | Wine Black | `#160A0E` | the ground of every frame, story and cover (oxblood taken to near-black) |
| support | Oxblood Light | `#6B2A37` | the glow of the key light |
| support | Ivory | `#F4EFE6` | text, the price line |
| support | Panel / Raised | `#241016` / `#2F1620` | glass panels |
| support | Warm Grey | `#A8979B` | labels, sources, the HUD's data |
| meaning | Up / Down / Flat | `#35E06E` / `#FF4D57` / `#A8979B` | ONLY with ▲ / ▼ (rule below) |

Contrast on a phone (WCAG): ivory on wine-black ≈ 17:1, mint on wine-black ≈ 10:1, wine letters on a mint chip ≈ 10:1,
ivory on oxblood ≈ 13:1 — every pair reads at 360 px wide.

**The meaning rule (mint is a green: it must never be read as «up»):**
1. **Up and down are never said by colour alone.** Every directional value carries its glyph and its sign:
   `▲ +2.1%` (up, vivid green `#35E06E`), `▼ −3.4%` (down, red `#FF4D57`); flat `■ 0.0%` warm grey. desk.js
   (`changeChip`, `returnBars`, `odometer({change: true})`) and story_card.py (a signed value in the data card) draw
   them so; anything you draw yourself does the same.
2. **Mint is never on a value or a direction:** no mint number, arrow, candle, bar, price line, chart fill or change
   chip. Mint is on WORDS and brand marks only. A chart's line is ivory; its cursor ivory/oxblood; a level line may be
   the mint Zarib Line because it is labelled and is not a change.
3. **Oxblood is never a «down»:** it is dark and never on a number; down is the bright red with ▼.
4. The up green is vivid and yellow-leaning, the brand mint pale and blue-leaning: they never sit side by side as
   equals (a mint chip is a word; a green value always has ▲).

**Why mint + oxblood:** they are the page's own colours (his photo), and they are free among the other pages —
DotCoin mustard `#F3C242` + black, Pro-Chart black + mustard `#D4A64A`, behnamjalali.tech ink + spectrum (navy/blue
covers), the old @zaribsad navy + teal. A wine-dark ground with a pale mint accent reads as premium and calm
(private banking, a tailor's house), and the suit colour gives every frame a warm light instead of a cold neon.

**The three layers** (DotCoin's rule, with Zarib's colours): **brand** in every frame (≥ the HUD, the Zarib Line or a
mint chip; the cold open, the end slate, every story and every cover are mostly brand) · **content** free inside the
plates, graded to wine-black with oxblood light (no other dominant green/teal, no mustard/gold, no violet) ·
**meaning** fixed (the rule above).

Delivery: Instagram re-encodes to 8-bit SDR; desk.js renders sRGB/BT.709 with an invisible ±1 dither so the dark
wine gradients never band. Never visible grain.

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
- `profile_round.png` (round, alpha outside) / `profile.jpg` (1080², the square original): @Zarib100x's profile
  photo (2026-11-26) — the owner in an oxblood peak-lapel suit, white shirt, black knit tie, on a flat mint backdrop.
  The two brand colours are sampled from it. A new profile photo: the same two files and names, then
  `tools/make_board.py` again (and the colours re-sampled only on the owner's word).
- **The lockup:** the round photo with a mint ring (ring = 3.5 % of its diameter) + **Zarib**`100x` (Plex Sans
  Condensed Bold, «100x» in mint) + «بهنام جلالی» (IRANYekanX Pro Regular, warm grey) under it. Small form
  (HUD, stories, cover foot): the photo + the wordmark on one line. Nothing else: no slogan, no TradeYar logo.
- `board.png` — this sheet as a picture (the photo, the colours, the meaning rule, type, sample frames, the two
  sample covers, the four pages side by side). `tokens.json` — the colours for code.
