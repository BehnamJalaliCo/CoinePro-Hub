#!/usr/bin/env bash
# The day's package: every change in site/ since `base` -> out/package.zip, checked by the hub's
# own rules first (tools/seo_pack.py of the site), then checked again as the hub will:
#   bash KIT/tools/pack.sh 2026-11-20 "the new page's title" /learn/new-slug/ [/learn/x/ …]
#   (the URLs after the title: the ones to ask Google to index first)
set -euo pipefail
DAY="${1:?day}"; TOPIC="${2:-}"; shift 2 || true
S=site/automations/sites/dotcoin
python3 -I "$S/tools/seo_pack.py" make site base out/package.zip --day "$DAY" --topic "$TOPIC" \
  --hub-base "$(cat in/BASE)" --index-first "$@"
echo "(the hub checks it again against its own copy at publish time)"
