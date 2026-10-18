#!/usr/bin/env bash
# The browser service's tests against a real Chromium (prompt 7.1 §1.4, §1.5):
# egress/tests/test_browser.py in a throwaway image built from the pinned
# Playwright image of egress/Dockerfile.browser, with the browser's own lock
# and the few test packages it needs from requirements-test.lock (all
# hash-pinned). The source is mounted read-only and the container has no
# network at all: the fake sites, egress's proxy and Chromium share its
# loopback. Nothing here touches the coinepro-hq stack.
#
# Usage: browser-test.sh [pytest args...]   (HQ_TEST_IMAGE_TAG: the image's tag)
set -euo pipefail

SERVICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="coinepro-hq/browser-test:${HQ_TEST_IMAGE_TAG:-dev}"
BASE="$(sed -n 's/^FROM \(mcr\.microsoft\.com\/playwright\/python[^ ]*\).*/\1/p' "$SERVICES_DIR/egress/Dockerfile.browser")"
[[ -n "$BASE" ]] || { echo "no Playwright base image in egress/Dockerfile.browser" >&2; exit 1; }
# What the tests import beyond the browser's lock (egress's proxy and pytest).
TEST_PKGS="pytest pytest-asyncio iniconfig pluggy packaging pygments httpx httpcore certifi"

ctx="$(mktemp -d)"
trap 'rm -rf "$ctx"' EXIT
cp "$SERVICES_DIR/egress/browser.requirements.lock" "$ctx/browser.lock"
awk -v want="$TEST_PKGS" '
  BEGIN { n = split(want, w, " "); for (i = 1; i <= n; i++) keep_name[w[i]] = 1 }
  /^[a-z0-9]/ { split($1, a, "=="); keep = (a[1] in keep_name) }
  keep && (/^[a-z0-9]/ || /^    --hash/) { print }
' "$SERVICES_DIR/requirements-test.lock" >"$ctx/test.lock"
[[ "$(grep -c '==' "$ctx/test.lock")" -eq "$(wc -w <<<"$TEST_PKGS")" ]] || {
  echo "requirements-test.lock lacks one of: $TEST_PKGS" >&2
  exit 1
}
cat >"$ctx/Dockerfile" <<EOF
FROM $BASE
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \\
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright HOME=/tmp PYTHONPATH=/w/hq-common/src:/w/egress/src
COPY browser.lock test.lock /tmp/
RUN python3 -m pip install --require-hashes --no-deps --break-system-packages \\
        -r /tmp/browser.lock -r /tmp/test.lock \\
    && rm /tmp/browser.lock /tmp/test.lock \\
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq
USER 10001
WORKDIR /w
EOF
docker build -q -t "$IMAGE" "$ctx" >/dev/null
docker run --rm --network none --tmpfs /tmp:size=256m,mode=1777 --shm-size 256m \
  -v "$SERVICES_DIR:/w:ro" "$IMAGE" python3 -m pytest egress/tests/test_browser.py "$@"
