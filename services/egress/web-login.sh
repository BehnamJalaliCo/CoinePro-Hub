#!/usr/bin/env bash
# The owner's sign-in window (prompt 12 §9.1.5, contract §21.13), inside the
# browser-login image: a virtual display (Xvfb), x11vnc on its loopback with a
# one-time password, noVNC (websockify) on 6080 for the relay, and the
# account's persistent profile in a visible Chromium through egress's sign-in
# listener. Everything stops after HQ_WEB_LOGIN_SECONDS (at most 900) or when
# the owner closes the browser. The hub never sees what the owner types; the
# one-time VNC password is printed to the owner's own terminal only.
# Prompt 14.1 §1.1: the image's own Chromium binary, started directly - no
# Playwright, no CDP, no --remote-debugging-*, no --enable-automation - so
# navigator.webdriver is false and Google lets the owner sign in. The same
# sandbox (Chromium's own, under the container's seccomp) as before.
# Usage (only through `make <x>-web-login`): web-login.sh chatgpt-web|gemini-web|deepseek-web
# `web-login.sh --flags <account>` prints the command line (the bench and tests).
set -euo pipefail
print_only=false
if [[ "${1:-}" == "--flags" ]]; then print_only=true; shift; fi
account="${1:-}"
case "$account" in
  chatgpt-web) url="https://chatgpt.com/" ;;
  gemini-web) url="https://gemini.google.com/app" ;;
  deepseek-web) url="https://chat.deepseek.com/" ;;
  *) echo "usage: $0 chatgpt-web|gemini-web|deepseek-web" >&2; exit 2 ;;
esac
chrome="$(ls -d /ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1 || true)"
# The sign-in window's JS heap: ChatGPT's app needs more than the read tool's 192.
heap="${BROWSER_LOGIN_JS_HEAP_MB:-512}"
[[ "$heap" =~ ^[0-9]+$ ]] || heap=512
flags=(
  "--user-data-dir=${BROWSER_WEB_PROFILES:-/profiles}/$account"
  "--proxy-server=${BROWSER_WEB_LOGIN_PROXY:-http://egress:3133}"
  --no-first-run --no-default-browser-check --disable-dev-shm-usage
  --disable-gpu --disable-quic --disable-sync --disable-background-networking
  --force-webrtc-ip-handling-policy=disable_non_proxied_udp
  "--js-flags=--max-old-space-size=$heap" --window-size=1280,900
)
if $print_only; then
  printf '%s\n' "${chrome:-chrome}" "${flags[@]}" "$url"
  exit 0
fi
[[ -n "$chrome" && -x "$chrome" ]] || { echo "error: no Chromium in this image" >&2; exit 1; }
mkdir -p -m 700 "${BROWSER_WEB_PROFILES:-/profiles}/$account"
seconds="${HQ_WEB_LOGIN_SECONDS:-900}"
if [[ ! "$seconds" =~ ^[0-9]+$ ]] || ((seconds > 900 || seconds < 60)); then seconds=900; fi
umask 077
export DISPLAY=:99 HOME=/tmp
work="$(mktemp -d)"
pids=()
stop() {
  for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done
  rm -rf "$work"
}
trap stop EXIT
Xvfb :99 -screen 0 1280x900x24 -nolisten tcp -noreset >/dev/null 2>&1 &
pids+=($!)
pass="$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 12)"
x11vnc -storepasswd "$pass" "$work/vnc.pass" >/dev/null 2>&1
x11vnc -display :99 -localhost -rfbport 5900 -rfbauth "$work/vnc.pass" -forever -shared \
  -quiet -noxdamage >/dev/null 2>&1 &
pids+=($!)
websockify --web /usr/share/novnc 6080 127.0.0.1:5900 >/dev/null 2>&1 &
pids+=($!)
echo "The sign-in window for $account is open for at most $((seconds / 60)) minutes."
echo "In your own terminal: ssh -L 6080:127.0.0.1:6080 <you>@<the hub>"
echo "Then open http://127.0.0.1:6080/vnc.html  (one-time password: $pass)"
echo "Sign in, then close the browser window. Nothing you type reaches the hub."
unset pass
timeout "$seconds" "$chrome" "${flags[@]}" "$url" >/dev/null 2>&1 || true
echo "The sign-in window is closed."
