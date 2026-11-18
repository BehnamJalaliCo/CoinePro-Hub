#!/usr/bin/env bash
# Lighthouse (mobile) on LIVE URLs, through a pipe (the workshop reaches no loopback port):
#   bash KIT/tools/lighthouse.sh https://dotcoin.me/learn/x/ …   -> work/lh-<n>.json + one line each
set -euo pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHROME="$(ls -d /home/studio/kits/prochart-reels/ms-playwright/chromium-*/chrome-linux*/chrome | tail -1)"
mkdir -p work/lh-home
n=0
for u in "$@"; do
  n=$((n + 1))
  HOME="$PWD/work/lh-home" CHROME_PATH="$CHROME" timeout 240 node "$KIT/tools/lh.mjs" "$u" "work/lh-$n.json" >/dev/null 2>&1 \
    || { echo "$u: lighthouse failed"; continue; }
  python3 -I -c '
import json, sys
d = json.load(open(sys.argv[1])); a = d["audits"]
c = {k: round((v["score"] or 0) * 100) for k, v in d["categories"].items()}
bad = [r["id"] for r in d["categories"]["seo"]["auditRefs"] if (a[r["id"]].get("score") is not None and a[r["id"]]["score"] < 1)]
print(sys.argv[2], c, "LCP", a["largest-contentful-paint"].get("displayValue"), "CLS", a["cumulative-layout-shift"].get("displayValue"),
      "TBT", a["total-blocking-time"].get("displayValue"), "seo-fails", bad)' "work/lh-$n.json" "$u"
done
