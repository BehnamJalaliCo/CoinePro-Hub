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
# Security fixes younger than the cutoff, per package only (pip-audit, 2026-10-22):
# certifi PYSEC-2026-4320 (2026.10.19), pypdf CVE-2026-113786 and four more (6.21.1),
# pillow CVE-2026-112390 and 23 more (13.0.0; pillow-heif 1.8.0 needs pillow>=11.1).
SECURITY_NEWER=(--exclude-newer-package certifi=2026-10-21T00:00:00Z
  --exclude-newer-package pypdf=2026-10-18T00:00:00Z
  --exclude-newer-package pillow=2026-10-18T00:00:00Z)

uv() {
  docker run --rm --user "$(id -u):$(id -g)" --tmpfs /tmp:mode=1777 -e UV_CACHE_DIR=/tmp/uv-cache \
    -v "$REPO_DIR:/w" -w /w "$UV_IMAGE" uv pip compile --quiet \
    --generate-hashes --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
    --exclude-newer "$EXCLUDE_NEWER" "${SECURITY_NEWER[@]}" --no-header "$@"
}

S=services
uv $S/llm-router/requirements.in $S/claude-runtime/requirements.in $S/gateway/requirements.in \
  $S/egress/requirements.in $S/provisioner/requirements.in $S/requirements-dev.in -o $S/requirements-test.lock
uv $S/llm-router/requirements.in -c $S/requirements-test.lock -o $S/llm-router/requirements.lock
uv $S/claude-runtime/requirements.in -c $S/requirements-test.lock -o $S/claude-runtime/requirements.lock
uv $S/gateway/requirements.in -c $S/requirements-test.lock -o $S/gateway/requirements.lock
uv $S/egress/requirements.in -c $S/requirements-test.lock -o $S/egress/requirements.lock
uv $S/provisioner/requirements.in -c $S/requirements-test.lock -o $S/provisioner/requirements.lock
# The browser service (Playwright, matching its image's Chromium) is not in the
# test image either (the tests use a fake browser); shared packages follow it.
uv $S/egress/browser.requirements.in -c $S/requirements-test.lock -o $S/egress/browser.requirements.lock
# stt's speech stack (faster-whisper, CTranslate2, PyAV, onnxruntime) is not in
# the test image (the tests use its fake engine); its shared packages still
# follow the test lock.
uv $S/stt/requirements.in -c $S/requirements-test.lock -o $S/stt/requirements.lock
# tts (prompt 12 §4): Piper and onnxruntime are not in the test image either (the
# tests use a fake engine); its shared packages follow the test lock.
uv $S/tts/requirements.in -c $S/requirements-test.lock -o $S/tts/requirements.lock
uv apps/api/requirements.in apps/api/requirements-dev.in -c $S/requirements-test.lock -o apps/api/requirements-test.lock
uv apps/api/requirements.in -c apps/api/requirements-test.lock -o apps/api/requirements.lock
echo "lock: services (test, llm-router, claude-runtime, gateway, egress, provisioner, browser, stt, tts) and apps/api (test, runtime)"
