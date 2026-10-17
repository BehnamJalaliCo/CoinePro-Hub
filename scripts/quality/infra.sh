#!/usr/bin/env bash
# Behaviour tests of the infra scripts and the edge configuration (prompt 05.1
# §3), on throwaway directories and containers only; nothing here touches the
# coinepro-hq stack, its volumes or the host's secrets:
#   provision   provision.sh without sudo stops before any KV write that a
#               file install depends on (a dev OpenBao in a container)
#   backup      every failed backup records ok:false (no stale ok:true) and
#               leaves no partial set; a busy lock records nothing
#   anchor-dir  the backup root is 0700 whatever Hub's umask; status/ is 0755
#   reanchor    audit-reanchor.sh needs a terminal, even with HQ_REANCHOR_CONFIRM
#   canary      hq.sh derives HQ_CANARY from the sites seed
#   caddy       /__canary: 404 off, 503 on; the web never sees
#               X-Middleware-Subrequest; web request bodies are capped
#   systemd     the container-metrics unit is sandboxed (read-only system,
#               one writable directory, no new privileges)
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_env

T="$(mktemp -d)"
NAME="hq-infra-$$"
# shellcheck disable=SC2329 # invoked by the EXIT trap below
cleanup() {
  docker rm -f "$NAME-bao" "$NAME-web" "$NAME-edge-off" "$NAME-edge-on" >/dev/null 2>&1 || true
  docker network rm "$NAME-net" >/dev/null 2>&1 || true
  rm -rf "$T"
  if [[ -n "${QUALITY_TMP:-}" ]]; then rm -rf "$QUALITY_TMP"; fi
}
trap cleanup EXIT
failed=0
pass() { echo "infra: ok   $*"; }
fail() { echo "infra: FAIL $*" >&2; failed=1; }
mode() { stat -c '%a' "$1"; }

# A PATH whose docker and sudo always fail and log: a script under test never
# reaches the real stack or root, even if its test seam broke. Two stand-ins
# for hq.sh that log every call: one fails (Postgres "down"), one succeeds.
mkdir -p "$T/bin"
for c in docker:1 sudo:1 hq:1 hq-ok:0; do
  printf '#!/bin/sh\necho "%s $*" >>"%s/calls.log"\nexit %s\n' "${c%:*}" "$T" "${c#*:}" >"$T/bin/${c%:*}"
  chmod +x "$T/bin/${c%:*}"
done
SAFE_PATH="$T/bin:$PATH"
FAKE_HQ="$T/bin/hq"

# ------------------------------------------------------------- provision ----
docker network create "$NAME-net" >/dev/null
dev_token="$(openssl rand -hex 16)" # a throwaway dev server's root token, never printed
BAO_DEV_ROOT_TOKEN_ID="$dev_token" docker run -d --name "$NAME-bao" --network "$NAME-net" \
  -p 127.0.0.1::8200 -e BAO_DEV_ROOT_TOKEN_ID -e BAO_DEV_LISTEN_ADDRESS=0.0.0.0:8200 \
  "$(compose_json lean | jq -r .services.openbao.image)" >/dev/null
bao="http://$(docker port "$NAME-bao" 8200/tcp | head -n1)"
for _ in $(seq 30); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "$bao/v1/sys/health")" == 200 ]] && break
  sleep 1
done
S="$T/secrets"
mkdir -p "$S" && chmod 700 "$S"
jq -n --arg t "$dev_token" '{root_token: $t}' >"$S/openbao-init.json"
chmod 600 "$S/openbao-init.json"
# Every file already installed but the KV empty: the path where a run without
# sudo used to rotate the tokens in KV, then stop at the file install.
for f in llm-router/approle.json claude-runtime/approle.json hq-api/approle.json \
  hq-worker/approle.json prometheus/llm-metrics.token gateway/worker-token.sha256; do
  echo "$S/services/$f"
done >"$S/.provisioned"
chmod 600 "$S/.provisioned"
out="$(PATH="$SAFE_PATH" HQ_SECRETS_DIR="$S" HQ_BAO_ADDR="$bao" \
  "$REPO_DIR/infra/openbao/provision.sh" 2>&1)" && rc=0 || rc=$?
kv_code() {
  curl -s -o /dev/null -w '%{http_code}' -H "X-Vault-Token: $dev_token" "$bao/v1/kv/data/$1"
}
if ((rc == 0)); then
  fail "provision: succeeded without sudo"
elif [[ "$out" != *"needs sudo: run make bootstrap"* ]]; then
  fail "provision: stopped for another reason ($(tail -n1 <<<"$out"))"
elif [[ "$(kv_code llm-router/config)" != 404 || "$(kv_code claude-runtime/config)" != 404 ]]; then
  fail "provision: wrote KV before stopping for sudo (router/runtime tokens out of step)"
else
  pass "provision: without sudo it stops before any KV write a file install depends on"
fi
unset dev_token

# ---------------------------------------------------------------- backup ----
B="$T/backups"
mkdir -p "$B/status"
echo '{"ok": true, "stamp": "sentinel"}' >"$B/status/backup.json"
if PATH="$SAFE_PATH" HQ_BACKUP_DIR="$B" HQ_COMPOSE_CMD="$FAKE_HQ" \
  "$REPO_DIR/infra/backup/backup.sh" >/dev/null 2>&1; then
  fail "backup: succeeded with Postgres down"
elif [[ "$(jq -r .ok "$B/status/backup.json")" != false ]]; then
  fail "backup: a failed run left ok:$(jq -r .ok "$B/status/backup.json") in status/backup.json"
elif compgen -G "$B/.*.partial" >/dev/null; then
  fail "backup: a failed run left a partial set"
else
  pass "backup: a failed run records ok:false and removes its partial set"
fi
echo '{"ok": true, "stamp": "sentinel"}' >"$B/status/backup.json"
exec 8>"$B/.lock"
flock -n 8
if PATH="$SAFE_PATH" HQ_BACKUP_DIR="$B" HQ_COMPOSE_CMD="$FAKE_HQ" \
  "$REPO_DIR/infra/backup/backup.sh" >/dev/null 2>&1; then
  fail "backup: ran although another backup held the lock"
elif [[ "$(jq -r .stamp "$B/status/backup.json")" != sentinel ]]; then
  fail "backup: a run that found the lock busy overwrote the running backup's status"
else
  pass "backup: a busy lock exits without touching the status"
fi
exec 8>&-

# ------------------------------------------------------------ anchor-dir ----
A="$T/anchor-root"
(umask 002 && HQ_BACKUP_DIR="$A" PATH="$SAFE_PATH" "$REPO_DIR/infra/backup/anchor-dir.sh" --check \
  >/dev/null 2>&1) || true
if [[ "$(mode "$A")" != 700 ]]; then
  fail "anchor-dir: backup root created $(mode "$A") under umask 002 (want 700)"
elif [[ "$(mode "$A/status")" != 755 ]]; then
  fail "anchor-dir: status/ is $(mode "$A/status") (want 755)"
else
  pass "anchor-dir: backup root 0700 and status/ 0755 whatever the umask"
fi

# -------------------------------------------------------------- reanchor ----
: >"$T/calls.log"
if PATH="$SAFE_PATH" HQ_COMPOSE_CMD="$T/bin/hq-ok" HQ_BACKUP_DIR="$B" HQ_REANCHOR_CONFIRM=re-anchor \
  "$REPO_DIR/infra/backup/audit-reanchor.sh" "infra test" </dev/null >/dev/null 2>&1; then
  fail "reanchor: re-anchored without a terminal"
elif [[ -s "$T/calls.log" ]]; then
  fail "reanchor: ran $(wc -l <"$T/calls.log") command(s) without a terminal"
else
  pass "reanchor: HQ_REANCHOR_CONFIRM without a terminal is refused before anything runs"
fi

# ---------------------------------------------------------------- canary ----
seed_on="$T/sites-on.yaml"
sed 's/canary: true, enabled: false/canary: true/' "$REPO_DIR/apps/api/seed/sites.yaml" >"$seed_on"
canary_of() { HQ_SITES_SEED="$1" compose_json lean | jq -r .services.caddy.environment.HQ_CANARY; }
seed_state=off
if grep -E 'canary:[[:space:]]*true' "$REPO_DIR/apps/api/seed/sites.yaml" | grep -qvE 'enabled:[[:space:]]*false'; then
  seed_state=on
fi
if [[ "$(canary_of "$seed_on")" != on ]]; then
  fail "canary: an enabled canary row did not give HQ_CANARY=on"
elif [[ "$(canary_of "$REPO_DIR/apps/api/seed/sites.yaml")" != "$seed_state" ]]; then
  fail "canary: HQ_CANARY does not follow the seed (want $seed_state)"
else
  pass "canary: HQ_CANARY follows the sites seed (now $seed_state)"
fi

# ----------------------------------------------------------------- caddy ----
CADDY_IMAGE="$(compose_json lean | jq -r .services.caddy.image)"
docker run -d --name "$NAME-web" --network "$NAME-net" --network-alias web "$PYTHON_IMAGE" python -c '
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class H(BaseHTTPRequestHandler):
    def reply(self, body):
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        self.reply(("sub=[%s]" % self.headers.get("X-Middleware-Subrequest", "")).encode())
    def do_POST(self):
        self.reply(b"read=%d" % len(self.rfile.read(int(self.headers.get("Content-Length") or 0))))
ThreadingHTTPServer(("0.0.0.0", 3000), H).serve_forever()' >/dev/null
for state in off on; do
  docker run -d --name "$NAME-edge-$state" --network "$NAME-net" -p 127.0.0.1::80 \
    -e HQ_SITE_ADDRESS=:80 -e HQ_API_EDGE=off -e HQ_WEB=on -e HQ_CANARY="$state" \
    -v "$REPO_DIR/infra/caddy:/etc/caddy:ro" "$CADDY_IMAGE" >/dev/null
done
edge_off="http://$(docker port "$NAME-edge-off" 80/tcp | head -n1)"
edge_on="http://$(docker port "$NAME-edge-on" 80/tcp | head -n1)"
for _ in $(seq 30); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "$edge_off/x")" == 200 ]] && break
  sleep 1
done
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
expect_eq() { # expect_eq WHAT GOT WANT
  if [[ "$2" == "$3" ]]; then pass "caddy: $1"; else fail "caddy: $1: got $2, want $3"; fi
}
expect_eq "/__canary while the canary is off" "$(code "$edge_off/__canary")" 404
expect_eq "/__canary while the canary is on" "$(code "$edge_on/__canary")" 503
expect_eq "X-Middleware-Subrequest never reaches the web" \
  "$(curl -s -H 'X-Middleware-Subrequest: middleware' "$edge_off/x")" "sub=[]"
expect_eq "a 2 MB body to the web is refused" "$(head -c 2000000 /dev/zero | code --data-binary @- "$edge_off/x")" 413
expect_eq "a 1 KB body to the web passes" "$(head -c 1000 /dev/zero | code --data-binary @- "$edge_off/x")" 200
expect_eq "/internal stays 404" "$(code "$edge_off/internal/v1/health")" 404

# --------------------------------------------------------------- systemd ----
unit="$REPO_DIR/infra/systemd/coinepro-hq-container-metrics.service"
missing=()
for want in NoNewPrivileges=yes ProtectSystem=strict ReadWritePaths=/var/lib/coinepro-hq/textfile \
  PrivateTmp=yes CapabilityBoundingSet=; do
  grep -qxF "$want" "$unit" || missing+=("$want")
done
if [[ "$(grep -c '^ReadWritePaths=' "$unit")" != 1 ]]; then missing+=("exactly one ReadWritePaths"); fi
if ((${#missing[@]})); then
  fail "systemd: container-metrics unit lacks ${missing[*]}"
else
  pass "systemd: container-metrics unit sandboxed (read-only system, only the textfile dir writable)"
fi

exit "$failed"
