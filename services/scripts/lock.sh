#!/usr/bin/env bash
# Regenerates the hash-pinned lock files with uv (run in its official image).
# One combined resolution keeps versions identical across both services and
# the test image; each service lock is then constrained to it. apps/api is
# resolved against the services' lock, so shared packages stay identical.
# Transitive dependencies are limited to releases at least a week old.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UV_IMAGE="ghcr.io/astral-sh/uv:0.12.22-python3.12-trixie-slim"
EXCLUDE_NEWER="${HQ_LOCK_EXCLUDE_NEWER:-2026-10-09T00:00:00Z}"

uv() {
  docker run --rm --user "$(id -u):$(id -g)" --tmpfs /tmp:mode=1777 -e UV_CACHE_DIR=/tmp/uv-cache \
    -v "$REPO_DIR:/w" -w /w "$UV_IMAGE" uv pip compile --quiet \
    --generate-hashes --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
    --exclude-newer "$EXCLUDE_NEWER" --no-header "$@"
}

S=services
uv $S/llm-router/requirements.in $S/claude-runtime/requirements.in $S/gateway/requirements.in \
  $S/requirements-dev.in -o $S/requirements-test.lock
uv $S/llm-router/requirements.in -c $S/requirements-test.lock -o $S/llm-router/requirements.lock
uv $S/claude-runtime/requirements.in -c $S/requirements-test.lock -o $S/claude-runtime/requirements.lock
uv $S/gateway/requirements.in -c $S/requirements-test.lock -o $S/gateway/requirements.lock
# stt's speech stack (faster-whisper, CTranslate2, PyAV, onnxruntime) is not in
# the test image (the tests use its fake engine); its shared packages still
# follow the test lock.
uv $S/stt/requirements.in -c $S/requirements-test.lock -o $S/stt/requirements.lock
uv apps/api/requirements.in apps/api/requirements-dev.in -c $S/requirements-test.lock -o apps/api/requirements-test.lock
uv apps/api/requirements.in -c apps/api/requirements-test.lock -o apps/api/requirements.lock
echo "lock: services (test, llm-router, claude-runtime, gateway, stt) and apps/api (test, runtime)"
