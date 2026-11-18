#!/usr/bin/env bash
# The whole site from site/ into work/dist (its bidi lint stops on a scrambled Latin run), then the
# SEO audit of every page:  bash KIT/tools/build.sh   (exit 1 on a build or audit error)
set -euo pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S=site/automations/sites/dotcoin
mkdir -p work
DOTCOIN_DIST="$PWD/work/dist" DOTCOIN_MEDIA="$PWD/work/no-media" python3 -I "$S/build.py" | tail -3
python3 -I "$KIT/tools/site_audit.py" work/dist "$S" > work/audit.md || true
tail -5 work/audit.md
grep -q "^ERRORS: 0$" work/audit.md
