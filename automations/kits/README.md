# Kits of the daily flows (domain/flows.py)

A kit is what a flow's day is made from on the holding's workshop: its recipe (README.md, the
day step by step) and its tools. The source is here; the workshop runs the copy in
/home/studio/kits/<kit>, with what is too big or licensed for git beside it there: the fonts
(IRANYekanX, licensed; ⟨2026-11-14⟩ every reel uses only the owner's IRANYekanX Eco pack in
/home/studio/kits/fonts-eco), the Python environments (`venv-render`, `asr` with its model) and
Playwright's Chromium (`ms-playwright`).

    automations/kits/sync.sh prochart-reels    # this source -> the workshop's copy (code and texts only)

prochart-reels: born from session F-0018 (2026-11-13); see docs/ops/reports/F-0018_SESSION_DISTILLED.md.

A kit with a topic bank keeps the workshop's topic statuses on `sync.sh`.

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
dotcoin-seo (2026-11-18): DotCoin.me's daily SEO day (flow dotcoin_seo, kind `article`): Search Console read by the
hub before the build (automations/sites/dotcoin/seo.py, recipe youtube-web gsc_*), the session's analysis, ONE new
long page for a keyword cluster and the day's improvements, measured as experiments (the site's seo/auto/), packed by
the site's own rules (tools/seo_pack.py) and published, reviewed and indexed by the hub. Its Lighthouse lives outside
git in /home/studio/kits/seo-node (npm: lighthouse 12.6.1 with puppeteer-core; run through a pipe).

bjtech-reels, bjtech-stories, bjtech-breaking, bjtech-longform (+ bjtech-common): the owner's last page
@behnamjalali.tech («Behnam Jalali | AI & Tech», company IG, IG-Hub account 3) and its YouTube channel
@behnamjalali-tech (owner, 2026-11-18: «فوق‌العاده متفاوت … پریمیوم‌ترین حالت ممکن»). Its own language, LUMEN
(bjtech-common/DIRECTION.md): an AI-native interface on ink, glass panels, live code, real benchmark bars, the
spectral edge, Estedad + Geist (fonts-bj, OFL), its own sound (bjtech-reels/motion/sound.py) and its own engine
(bjtech-reels/motion/stage.html, 9:16 and 16:9). Two reels a day (13:30 the day's kind: repo / model / tool /
trick / behind the scenes; 22:00 the day's hot news + what it means), twelve story cards a day set in code
(bjtech-common/tools/card.py), the breaking news (a host watcher on the vendors' own sources starts a flash story
and a full reel the moment a new model lands), and a daily 8–15 minute YouTube video. Narrator Arlo. Banks:
bjtech-reels/topics.md (406), bjtech-longform/topics.md (142), researched 2026-11-18 with sources.

fa-type (2026-11-27): Persian typography and the TYPE GATE every page's picture tools import (fatype.py): the
number rules, and before a picture is written Chrome's own report of the font that drew every glyph (a system
font = fail), text out of its box / chip / over other text = fail. Born from DotCoin's stories of 11-27
(F-0246: figures drawn by a system font). dotcoin-stories/tools/slide_fallback.py is the tested fallback when
the art path fails; deliver_check.py refuses a set the gate did not pass. See fa-type/README.md.
