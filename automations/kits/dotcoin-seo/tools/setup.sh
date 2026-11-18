#!/usr/bin/env bash
# The day's workspace from the hub's input pack (run in the work folder, the session's cwd):
#   bash KIT/tools/setup.sh 2026-11-20
# -> in/  : a link to /home/studio/seo-inputs/dotcoin/<day> (else the newest pack, named in NOTES.md)
#    site/: the site's source at the pack's BASE, a git copy tagged `base` (your changes are its diff)
#    site/automations/sites/dotcoin/private: the fonts and logo files to build with
#    site/automations/kits/dotcoin-longform/topics.md: the long videos' bank (reserved slugs)
#    out/ work/ shots/ and NOTES.md (kept across turns: never run this twice on a day's folder)
set -euo pipefail
DAY="${1:?usage: setup.sh YYYY-MM-DD}"
ROOT=/home/studio/seo-inputs/dotcoin
[[ -e site/.git ]] && { echo "already set up (site/ exists): read NOTES.md"; exit 0; }
PACK="$ROOT/$DAY"
if [[ ! -d "$PACK" ]]; then
  PACK="$(readlink -f "$ROOT/latest" 2>/dev/null || true)"
  [[ -d "$PACK" ]] || { echo "no input pack at all: work from the live site (curl -4) and say so in report.md"; mkdir -p out work shots; exit 2; }
  echo "NOTE: no pack for $DAY; using $(basename "$PACK")"
fi
ln -sfn "$PACK" in
mkdir -p site out work shots
tar -C site -xf in/site.tar
tar -C site/automations/sites/dotcoin -xf in/private.tar
mkdir -p site/automations/kits/dotcoin-longform
cp in/longform_topics.md site/automations/kits/dotcoin-longform/topics.md
git -C site init -q -b main
git -C site config user.email seo@dotcoin.me
git -C site config user.name "dotcoin-seo"
git -C site add -A
git -C site commit -q -m "the hub's copy at $(cat in/BASE)"
git -C site tag base
{
  echo "# NOTES — DotCoin SEO day $DAY (read first every turn; keep it current)"
  echo
  echo "- pack: $(basename "$PACK") (BASE $(cut -c1-10 in/BASE)); read errors: $(python3 -c 'import json;print(len(json.load(open("in/errors.json"))))')"
  echo "- turn 1: [ ] digest [ ] audit [ ] lighthouse [ ] yesterday into LOG [ ] the day's plan below"
  echo "- turn 2: [ ] research [ ] the new page [ ] links to it"
  echo "- turn 3: [ ] fixes [ ] seo/auto [ ] build + audit + review (read every shot) [ ] pack [ ] out/"
  echo
  echo "## The day's plan"
} > NOTES.md
echo "set up: site/ (tag base), in/ -> $PACK, NOTES.md"
