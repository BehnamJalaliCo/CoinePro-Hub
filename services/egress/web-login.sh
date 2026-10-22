#!/usr/bin/env bash
# The owner's sign-in window (prompt 12 §9.1.5, contract §21.13), inside the
# browser-login image: a virtual display (Xvfb), x11vnc on its loopback with a
# one-time password, noVNC (websockify) on 6080 for the relay, and the
# account's persistent profile in a visible Chromium through egress's sign-in
# listener. Everything stops after HQ_WEB_LOGIN_SECONDS (at most 900) or when
# the owner closes the browser. The hub never sees what the owner types; the
# one-time VNC password is printed to the owner's own terminal only.
# Usage (only through `make <x>-web-login`): web-login.sh chatgpt-web|gemini-web|deepseek-web
set -euo pipefail
account="${1:-}"
case "$account" in
  chatgpt-web | gemini-web | deepseek-web) ;;
  *) echo "usage: $0 chatgpt-web|gemini-web|deepseek-web" >&2; exit 2 ;;
esac
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
timeout "$seconds" python3 -m hq_egress.browser_web login "$account" || true
echo "The sign-in window is closed."
