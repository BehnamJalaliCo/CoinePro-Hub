# Kits of the daily flows (domain/flows.py)

A kit is what a flow's day is made from on the holding's workshop: its recipe (README.md, the
day step by step) and its tools. The source is here; the workshop runs the copy in
/home/studio/kits/<kit>, with what is too big or licensed for git beside it there: the fonts
(IRANYekanX, licensed; ⟨2026-11-14⟩ every reel uses only the owner's IRANYekanX Eco pack in
/home/studio/kits/fonts-eco), the Python environments (`venv-render`, `asr` with its model) and
Playwright's Chromium (`ms-playwright`).

    automations/kits/sync.sh prochart-reels    # this source -> the workshop's copy (code and texts only)

prochart-reels: born from session F-0018 (2026-11-13); see docs/ops/reports/F-0018_SESSION_DISTILLED.md.

ipoxxo-reels, ipoxxo-stories (+ ipoxxo-common): the page @ipoxxo.vpn for the free Telegram channel
t.me/ipoxxo, under IG-Hub (owner, 2026-11-16): two premium motion-graphics reels a day (Opus 5.5, the
Zarib×100 bar) and three photoreal stories a day; original Instagram ads, never the channel's posts.

dotcoin-reels (+ dotcoin-common): the page @dotcoin.me («Dot Coin | بهنام جلالی»), under IG-Hub (owner,
2026-11-16), designed anew: educational / informational reels, each with its own look from its own
Pinterest references, Opus 5.5 at extra-high effort (11-17; was Fable 5.2), the narrator Arlo, IRANYekanX Pro
(/home/studio/kits/fonts-pro), colour in three layers (mustard + black brand, full-colour content, green
up / red down), and the owner's own cover system (he is on every cover).
dotcoin-stories (2026-11-17): the day's educational lesson in twelve story slides, designed by ChatGPT
in ONE chat (substitute.call `images: 12`) with Gemini's art; tools/slide_frame.py puts the page's
mark, the slide's number and the day's reply word on each.
dotcoin-longform (2026-11-17): DotCoin's long YouTube videos, three a week (8–10 min, 16:9, Arlo, the reels'
look in a Swiss grid × isometric engine), each with its thumbnail (the owner's cover system, 16:9), YouTube
text with chapters, sidecar subtitles and a new lesson on dotcoin.me; rendered chapter by chapter over
several workshop turns; uploaded once each by the hub (automations/sites/dotcoin/youtube_long.py).
