#!/usr/bin/env bash
# Every page named, at 390 px light AND dark (+ 1440 and 920 px), from work/dist: overflow and
# direction checks, screenshots cut into one-screen parts in shots/ (READ every part):
#   bash KIT/tools/review.sh /learn/new-slug/ /learn/changed/ …
set -euo pipefail
S=site/automations/sites/dotcoin
PY=/home/studio/kits/prochart-reels/venv-render/bin/python
rm -rf shots && mkdir -p shots
PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright "$PY" -I "$S/tools/review.py" check \
  "$PWD/work/dist" "$PWD/shots" "$@" --desktop 2>&1 | grep -v '[║╔╚]'
