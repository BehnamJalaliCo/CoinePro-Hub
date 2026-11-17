#!/usr/bin/env bash
# dotcoin.me: build and deploy to Cloudflare Pages (direct upload), project "dotcoin".
#
#   deploy.sh               build (+ private assets when missing) + OG cards + deploy
#   deploy.sh --assets      remake the private assets (fonts, logo files) first
#   deploy.sh --no-deploy   build only (dist/)
#
# Secrets (never printed): $DOTCOIN_SECRETS/cloudflare.token and cloudflare.ids (JSON: account_id,
# zone_id); default /home/Hub/.secrets/dotcoin. The token is IP-bound to the hub's IPv4, so this
# runs on the hub; docker's default bridge is IPv4.
set -euo pipefail

SITE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS="${DOTCOIN_SECRETS:-/home/Hub/.secrets/dotcoin}"
FONTS=/home/studio/kits/fonts-pro
LOGO=/home/studio/kits/dotcoin-common/brand/logo_round.png
RENDER_PY=/home/studio/kits/prochart-reels/venv-render/bin/python
PW_PATH=/home/studio/kits/prochart-reels/ms-playwright
STUDIO_TMP=/home/studio/tmp-dotcoin-build
VENV="${DOTCOIN_VENV:-$SITE/.venv}"
NODE_IMAGE="${DOTCOIN_NODE_IMAGE:-node:22-alpine}"
MODE="${1:-}"

as_studio() { sudo -n -u studio "$@"; }

# 1. Private assets: fonts (woff2 subsets) and the owner's logo files. Never committed.
if [ ! -f "$SITE/private/anton-metrics.json" ] || [ "$MODE" = "--assets" ]; then
  if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q fonttools brotli pillow
  fi
  SRC="$(mktemp -d)"
  trap 'rm -rf "$SRC"' EXIT
  for f in IRANYekanXFaNum-Light IRANYekanXFaNum-Regular IRANYekanXFaNum-DemiBold IRANYekanXFaNum-ExtraBold \
           IRANYekanXFaNum-ExtraBlack IRANYekanX-Regular Anton-Regular; do
    as_studio cat "$FONTS/$f.ttf" > "$SRC/$f.ttf"
  done
  as_studio cat "$LOGO" > "$SRC/logo_round.png"
  "$VENV/bin/python" -I "$SITE/tools/prep_assets.py" "$SRC" "$SITE/private"
fi

# 2. The site.
python3 -I "$SITE/build.py"

# 3. OG cards, shot by the studio's Chromium (the studio user cannot read the Hub home: copy in, copy out).
as_studio mkdir -p "$STUDIO_TMP"
as_studio find "$STUDIO_TMP" -mindepth 1 -delete
# (the reels in dist/media stay out: the cards do not need them)
tar -C "$SITE" --exclude=dist/media -cf - dist tools/render.py | as_studio tar -C "$STUDIO_TMP" -xf -
as_studio env PLAYWRIGHT_BROWSERS_PATH="$PW_PATH" "$RENDER_PY" -I "$STUDIO_TMP/tools/render.py" og "$STUDIO_TMP/dist" \
  2>&1 | grep -v '[║╔╚]' || true
rm -rf "$SITE/dist/_og" "$SITE/dist/og"
as_studio tar -C "$STUDIO_TMP/dist" -cf - og | tar -C "$SITE/dist" -xf -
as_studio find "$STUDIO_TMP" -mindepth 1 -delete
as_studio rmdir "$STUDIO_TMP"
ls "$SITE/dist/og" | grep -q '\.jpg$' || { echo "no OG cards were made" >&2; exit 1; }

[ "$MODE" = "--no-deploy" ] && { echo "built: $SITE/dist"; exit 0; }

# 4. Deploy (wrangler in a throwaway node container; the token goes in by name, never on a command line).
CLOUDFLARE_ACCOUNT_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["account_id"])' "$SECRETS/cloudflare.ids")"
CLOUDFLARE_API_TOKEN="$(cat "$SECRETS/cloudflare.token")"
export CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_API_TOKEN
docker run --rm -e CLOUDFLARE_API_TOKEN -e CLOUDFLARE_ACCOUNT_ID -e WRANGLER_SEND_METRICS=false \
  -v "$SITE/dist:/dist:ro" "$NODE_IMAGE" \
  sh -c 'npx -y wrangler@3 pages project list 2>/dev/null | grep -q " dotcoin " ||
         npx -y wrangler@3 pages project create dotcoin --production-branch main;
         npx -y wrangler@3 pages deploy /dist --project-name dotcoin --branch main --commit-dirty=true'
