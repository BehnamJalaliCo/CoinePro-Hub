# The covers (reel) and thumbnails (YouTube) — set in code, never a picture with letters in it

Both come from `COMMON/tools/card.py` (types `cover` and `thumb`), so the title is letter-perfect and every
cover of the grid belongs to one family: ink, one glass frame with a spectral ring, the big Estedad title with
its key word in the spectrum, the pillar chip, the handle.

## Reel cover (1080×1920, `out/cover.jpg`)
- The grid shows the middle 1080×1350 (y 285–1635): the chip, the hero and the title stay inside it.
- **Title:** the hook at its most striking, 2–5 Persian words («از ۳ ساعت به ۴ دقیقه»), one or two key words in
  `keys`. **latin:** the product's real name when there is one («Claude Fable 5.2»).
- **image:** the video's hero: the official launch image (news, model), a repo's own social preview image
  (github.com/<owner>/<repo> → its og:image), or the best AI still of the reel. Never a video frame.
- `{"type": "cover", "pillar": "…", "title": "…", "keys": […], "latin": "…", "image": "assets/use/<hero>.jpg"}`

## YouTube thumbnail (1280×720, `out/thumbnail.jpg`)
- 2–4 Persian words that read at 160 px wide (`px` 96–120), the hero on the left in its spectral frame, the
  Latin name under the words, the spectral edge around the whole.
- Two candidates (two heroes or two wordings); keep the one that reads at 160 px: `card.py --sheet` them.
- `{"type": "thumb", "pillar": "…", "title": "…", "keys": […], "latin": "…", "image": "…"}`

## Check
`PY -I COMMON/tools/card.py spec.json out/cover.jpg` prints `ok` or `overflow: <text>` (a line out of its box:
shorten it). Read the picture at full size: every letter, no word on an edge.
