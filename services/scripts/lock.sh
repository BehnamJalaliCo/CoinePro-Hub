#!/usr/bin/env bash
# Regenerates the hash-pinned lock files with uv (run in its official image).
# One combined resolution keeps versions identical across both services and
# the test image; each service lock is then constrained to it.
# Transitive dependencies are limited to releases at least a week old.
set -euo pipefail

SERVICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV_IMAGE="ghcr.io/astral-sh/uv:0.12.22-python3.12-trixie-slim"
EXCLUDE_NEWER="${HQ_LOCK_EXCLUDE_NEWER:-2026-10-09T00:00:00Z}"

uv() {
  docker run --rm --user "$(id -u):$(id -g)" --tmpfs /tmp:mode=1777 -e UV_CACHE_DIR=/tmp/uv-cache \
    -v "$SERVICES_DIR:/w" -w /w "$UV_IMAGE" uv pip compile --quiet \
    --generate-hashes --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
    --exclude-newer "$EXCLUDE_NEWER" --no-header "$@"
}

uv llm-router/requirements.in claude-runtime/requirements.in requirements-dev.in -o requirements-test.lock
uv llm-router/requirements.in -c requirements-test.lock -o llm-router/requirements.lock
uv claude-runtime/requirements.in -c requirements-test.lock -o claude-runtime/requirements.lock
echo "lock: requirements-test.lock, llm-router/requirements.lock, claude-runtime/requirements.lock"
