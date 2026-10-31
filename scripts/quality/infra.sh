#!/usr/bin/env bash
# Behaviour tests of the infra scripts and the edge configuration (prompt 05.1
# §3), on throwaway directories and containers only; nothing here touches the
# coinepro-hq stack, its volumes or the host's secrets:
#   provision   provision.sh without sudo stops before any KV write that a
#               file install depends on (a dev OpenBao in a container)
#   kv-once     kv/support/pseudonym is made once with cas 0 and kept (p10)
#   backup      every failed backup records ok:false (no stale ok:true) and
#               leaves no partial set; a busy lock records nothing
#   stt         an opt-in profile over the memory budget: shown while off, a
#               gate failure and an hq.sh refusal while on; STT_URL follows it
#   ocr         the archive's OCR (prompt 14 §4): off by default, on where it
#               fits (the worker alone gets HQ_OCR_URL), refused without room
#   transit     OpenBao transit and the key archive-secret (prompt 14 §3): made
#               once, not exportable, never deletable; the services' policies
#               reach only its data key and decrypt
#   anchor-dir  the backup root is 0700 whatever Hub's umask; status/ is 0755
#   reanchor    audit-reanchor.sh needs a terminal, even with HQ_REANCHOR_CONFIRM
#   owner-only  make gdrive-auth, backup-password and openbao-snapshot-token
#               refuse without a terminal before touching anything (prompt 07)
#   mcp-secret  a JSON key file is stored as it is; not-JSON never reaches KV
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
  docker rm -fv "$NAME-bao" "$NAME-web" "$NAME-edge-off" "$NAME-edge-on" "$NAME-api" "$NAME-edge-api" \
    >/dev/null 2>&1 || true
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
  hq-worker/approle.json provisioner/approle.json tts/approle.json media/approle.json prometheus/llm-metrics.token \
  prometheus/node-exporter.password node-exporter/web.yml gateway/worker-token.sha256; do
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

# --------------------------------------------------------------- transit ----
# Prompt 14 §3: the run above (as the non-root admin token it made) enabled
# transit and made archive-secret: aes256-gcm96, not exportable, no plaintext
# backup, not deletable. hq-api's policy reaches a data key and its
# decryption and nothing else of transit; a rerun keeps the same key.
ta="$T/transit.auth"
(umask 077 && printf 'X-Vault-Token: %s\n' "$dev_token" >"$ta")
tkey() { curl -s -H @"$ta" "$bao/v1/transit/keys/archive-secret"; }
# hq-api's policy plus OpenBao's default one (for sys/capabilities-self; it
# grants nothing on transit).
api_token="$(curl -s -H @"$ta" -d '{"policies": ["hq-api"], "ttl": "5m"}' \
  "$bao/v1/auth/token/create" | jq -r '.auth.client_token // empty')"
(umask 077 && printf 'X-Vault-Token: %s\n' "$api_token" >"$T/transit-api.auth")
unset api_token
caps="$(curl -s -H @"$T/transit-api.auth" -d '{"paths": ["transit/datakey/plaintext/archive-secret",
  "transit/decrypt/archive-secret", "transit/export/encryption-key/archive-secret", "transit/keys/archive-secret",
  "transit/encrypt/archive-secret", "transit/datakey/plaintext/other"]}' "$bao/v1/sys/capabilities-self" |
  jq -c '[.["transit/datakey/plaintext/archive-secret"], .["transit/decrypt/archive-secret"],
    .["transit/export/encryption-key/archive-secret"], .["transit/keys/archive-secret"],
    .["transit/encrypt/archive-secret"], .["transit/datakey/plaintext/other"]]')"
# One envelope round trip as the api would make it (values compared, never printed).
dk="$(curl -s -H @"$T/transit-api.auth" -X POST "$bao/v1/transit/datakey/plaintext/archive-secret")"
round="$(jq -c '{ciphertext: .data.ciphertext}' <<<"$dk" |
  curl -s -H @"$T/transit-api.auth" -d @- "$bao/v1/transit/decrypt/archive-secret" | jq -r '.data.plaintext // empty')"
same=no
if [[ -n "$round" && "$round" == "$(jq -r '.data.plaintext // empty' <<<"$dk")" ]]; then same=yes; fi
unset dk round
version_before="$(tkey | jq -r '.data.latest_version')"
PATH="$SAFE_PATH" HQ_SECRETS_DIR="$S" HQ_BAO_ADDR="$bao" "$REPO_DIR/infra/openbao/provision.sh" >/dev/null 2>&1 || true
delete_code="$(curl -s -o /dev/null -w '%{http_code}' -H @"$ta" -X DELETE "$bao/v1/transit/keys/archive-secret")"
if ! tkey | jq -e '.data.type == "aes256-gcm96" and .data.exportable == false
    and .data.allow_plaintext_backup == false and .data.deletion_allowed == false' >/dev/null; then
  fail "transit: archive-secret is missing, exportable, backed up or deletable"
elif [[ "$caps" != '[["update"],["update"],["deny"],["deny"],["deny"],["deny"]]' ]]; then
  fail "transit: hq-api's policy reaches more (or less) of transit than a data key and its decryption ($caps)"
elif [[ "$same" != yes ]]; then
  fail "transit: a data key did not decrypt back to itself"
elif [[ "$(tkey | jq -r '.data.latest_version')" != "$version_before" || "$version_before" != 1 ]]; then
  fail "transit: a rerun of provision.sh changed the key"
elif [[ "$delete_code" == 204 ]] || ! tkey | jq -e '.data.name == "archive-secret"' >/dev/null; then
  fail "transit: the key could be deleted"
else
  pass "transit: archive-secret made once (not exportable, not deletable); the api reaches only a data key and decrypt"
fi
rm -f "$ta" "$T/transit-api.auth"

# ------------------------------------------------------------ kv-once ----
# Prompt 10 §1.2: kv/support/pseudonym is made once (cas 0) and kept on every
# later run; the value is 32 random bytes in hex and is never printed.
printf 'X-Vault-Token: %s\n' "$dev_token" >"$T/root.auth"
chmod 600 "$T/root.auth"
curl -s -o /dev/null -X POST -H @"$T/root.auth" -H 'Content-Type: application/json' \
  -d '{"type": "kv", "options": {"version": "2"}}' "$bao/v1/sys/mounts/kv" || true
kv_key() { curl -s -H @"$T/root.auth" "$bao/v1/kv/data/support/pseudonym" | jq -r '.data.data.key // empty'; }
kv_version() { curl -s -H @"$T/root.auth" "$bao/v1/kv/metadata/support/pseudonym" | jq -r '.data.current_version // 0'; }
once_out="$(HQ_BAO_ADDR="$bao" "$REPO_DIR/infra/openbao/kv-once.sh" "$T/root.auth" support/pseudonym key 2>&1)" &&
  k1=0 || k1=$?
first="$(kv_key)"
HQ_BAO_ADDR="$bao" "$REPO_DIR/infra/openbao/kv-once.sh" "$T/root.auth" support/pseudonym key >/dev/null 2>&1 &&
  k2=0 || k2=$?
HQ_BAO_ADDR="http://127.0.0.1:9" "$REPO_DIR/infra/openbao/kv-once.sh" "$T/root.auth" support/pseudonym key \
  >/dev/null 2>&1 && k3=0 || k3=$?
if [[ $k1 == 0 && $k2 == 0 && $k3 != 0 && "$first" =~ ^[0-9a-f]{64}$ && "$(kv_key)" == "$first" &&
  "$(kv_version)" == 1 && "$once_out" != *"$first"* ]]; then
  pass "kv-once: the pseudonym key is made once (cas 0), kept on a rerun, never printed; no OpenBao, no write"
else
  fail "kv-once: first=$k1 rerun=$k2 unreachable=$k3 version=$(kv_version) ($(tail -n1 <<<"$once_out"))"
fi
unset first
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
# Creating (make bootstrap; the stand-in sudo fails after the Hub-owned parts).
(umask 002 && HQ_BACKUP_DIR="$A" PATH="$SAFE_PATH" "$REPO_DIR/infra/backup/anchor-dir.sh" \
  >/dev/null 2>&1) || true
if [[ "$(mode "$A")" != 700 ]]; then
  fail "anchor-dir: backup root created $(mode "$A") under umask 002 (want 700)"
elif [[ "$(mode "$A/status")" != 755 ]]; then
  fail "anchor-dir: status/ is $(mode "$A/status") (want 755)"
else
  pass "anchor-dir: backup root 0700 and status/ 0755 whatever the umask"
fi
# Checking (make up) changes nothing, and says what is wrong.
C="$T/anchor-check"
if HQ_BACKUP_DIR="$C" PATH="$SAFE_PATH" "$REPO_DIR/infra/backup/anchor-dir.sh" --check >/dev/null 2>&1; then
  fail "anchor-dir: --check passed on a missing directory"
elif [[ -e "$C" ]]; then
  fail "anchor-dir: --check created $C"
else
  pass "anchor-dir: --check only verifies (nothing created or changed)"
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

# ------------------------------------------------------------ owner-only ----
for script in infra/backup/gdrive-auth.sh infra/backup/show-password.sh infra/openbao/snapshot-token.sh \
  infra/openbao/hetzner-token.sh infra/openbao/owner-ssh-key.sh; do
  : >"$T/calls.log"
  if PATH="$SAFE_PATH" HQ_COMPOSE_CMD="$T/bin/hq-ok" HQ_BACKUP_DIR="$B" HQ_SECRETS_DIR="$T/no-secrets" \
    "$REPO_DIR/$script" </dev/null >/dev/null 2>&1; then
    fail "owner-only: $script ran without a terminal"
  elif [[ -s "$T/calls.log" ]]; then
    fail "owner-only: $script ran $(wc -l <"$T/calls.log") command(s) without a terminal"
  else
    pass "owner-only: $script refuses without a terminal, before anything runs"
  fi
done

# ------------------------------------------------------------ mcp-secret ----
# make mcp-secret FILE= (7.1 §2.15): a JSON key file is stored exactly as it
# is; a file that is not a JSON object is refused before OpenBao is written.
# A pty (script) stands in for the owner's terminal; the dev OpenBao above.
MS="$T/mcp-secrets"
mkdir -p "$MS" && chmod 700 "$MS"
(umask 077 && jq -r .root_token "$S/openbao-init.json" >"$MS/openbao-admin.token")
bao_h="$T/bao.header"
(umask 077 && printf 'X-Vault-Token: %s\n' "$(cat "$MS/openbao-admin.token")" >"$bao_h")
curl -s -o /dev/null -H @"$bao_h" -d '{"type":"kv","options":{"version":"2"}}' "$bao/v1/sys/mounts/kv" || true
printf '{\n  "type": "service_account",\n  "client_email": "x@y.iam.example"\n}\n' >"$T/sa.json"
printf '{"type": "service_account",\n' >"$T/not-json.json"
mcp_secret() {
  HQ_SECRETS_DIR="$MS" HQ_BAO_ADDR="$bao" script -qec \
    "$(printf '%q ' "$REPO_DIR/infra/openbao/mcp-secret.sh" "$1" "$2")" /dev/null </dev/null >"$T/mcp.out" 2>&1
}
mcp_stored() { curl -s -H @"$bao_h" "$bao/v1/kv/data/hq-api/tools/mcp/$1"; }
if ! mcp_secret mcp-gate "$T/sa.json"; then
  fail "mcp-secret: a JSON key file was refused ($(tail -n1 "$T/mcp.out"))"
elif ! mcp_stored mcp-gate | jq -e --rawfile f "$T/sa.json" '.data.data.token == $f' >/dev/null; then
  fail "mcp-secret: the JSON key file was not stored as it is"
elif ! grep -q 'Delete it' "$T/mcp.out"; then
  fail "mcp-secret: no advice to delete the key file"
elif mcp_secret mcp-gate-bad "$T/not-json.json"; then
  fail "mcp-secret: a file that is not JSON was stored"
elif [[ "$(mcp_stored mcp-gate-bad | jq -r '.data.data.token // "none"')" != none ]]; then
  fail "mcp-secret: a refused file still reached OpenBao"
else
  pass "mcp-secret: a JSON key file is stored as it is (then: delete it); not-JSON is refused"
fi
rm -f "$bao_h"

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
expect_eq "intake stays closed without a domain" "$(code -X POST "$edge_off/intake/v1/product/TY")" 404

# Prompt 10 §9: the three intake routes with the public API on (a stub api).
docker run -d --name "$NAME-api" --network "$NAME-net" --network-alias api "$PYTHON_IMAGE" python -c '
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = len(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        body = ("api:%s:%d" % (self.path, n)).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()' >/dev/null
docker run -d --name "$NAME-edge-api" --network "$NAME-net" -p 127.0.0.1::80 \
  -e HQ_SITE_ADDRESS=:80 -e HQ_API_EDGE=on -e HQ_WEB=on -e HQ_CANARY=off \
  -v "$REPO_DIR/infra/caddy:/etc/caddy:ro" "$CADDY_IMAGE" >/dev/null
edge_api="http://$(docker port "$NAME-edge-api" 80/tcp | head -n1)"
for _ in $(seq 30); do
  [[ "$(code -X POST "$edge_api/intake/v1/product/TY")" == 200 ]] && break
  sleep 1
done
expect_eq "intake: a product event reaches the api" \
  "$(curl -s -X POST --data-binary '{}' "$edge_api/intake/v1/product/TY")" "api:/intake/v1/product/TY:2"
expect_eq "intake: a Chatwoot event reaches the api" "$(code -X POST "$edge_api/intake/v1/chatwoot/TY")" 200
expect_eq "intake: Telegram's route only from Telegram's ranges" \
  "$(code -X POST "$edge_api/intake/v1/telegram/TY/telegram_bot")" 403
expect_eq "intake: a 2 MB body is refused" \
  "$(head -c 2000000 /dev/zero | code --data-binary @- "$edge_api/intake/v1/product/TY")" 413
expect_eq "intake: any other path is unknown" "$(code -X POST "$edge_api/intake/v1/other/TY")" 404
expect_eq "/internal stays 404 with the api on" "$(code "$edge_api/internal/v1/health")" 404

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

# ------------------------------------------- the RAM hq.sh sizes against ----
# hq.sh admits an opt-in profile against the larger of the profile's reference
# and the server's MemTotal (the owner, 2026-10-30: 478a4b7). The gate tests
# below size the smallest server of each profile (HQ_MEMTOTAL_MB=0: the
# reference alone), whatever machine runs them; this one sizes a larger one.
export HQ_MEMTOTAL_MB=0
big_up="$(HQ_MEMTOTAL_MB=65536 HQ_PROFILE=lean HQ_MCP=on "$HQ" --dry-run up --no-start 2>&1)" || true
small_up="$(HQ_PROFILE=lean HQ_MCP=on "$HQ" --dry-run up --no-start 2>&1)" && small_rc=0 || small_rc=$?
if ((small_rc != 3)) || ! grep -q 'HQ_MCP=on refused' <<<"$small_up"; then
  fail "ram: lean+mcp on a server of lean's reference size was not refused (exit $small_rc)"
elif grep -q 'HQ_MCP=on refused' <<<"$big_up"; then
  fail "ram: lean+mcp was refused on a 64 GiB server (hq.sh sizes against the reference only)"
else
  pass "ram: hq.sh sizes an opt-in against this server's RAM when it is larger than the reference"
fi

# ---------------------------------------------------------- stt (opt-in) ----
# Prompt 06 §3; ⟨1.9⟩ prompt 18: stt is installed with HQ_STT=on and runs on
# demand: `up` never starts it (the host's starter does, HQ_STT_START=1); the
# memory rule counts it as a burst (infra/compose/stt-burst.jq). Over the
# budget it is shown while off, fails the gate while on, and hq.sh refuses
# it, so it can never be turned on by accident. STT_URL follows the switch.
gate_on="$(HQ_STT=on CI=1 "$REPO_DIR/scripts/quality/memory-budget.sh" 2>&1)" && on_rc=0 || on_rc=$?
on_json="$(HQ_PROFILE=full HQ_STT=on "$HQ" config --format json)"
start_services="$(HQ_PROFILE=full HQ_STT=on HQ_STT_START=1 "$HQ" config --services)"
burst="$(HQ_PROFILE=full HQ_STT=off "$HQ" --profile stt --profile backup-tools config --format json |
  jq -f "$REPO_DIR/infra/compose/stt-burst.jq")"
whole="$(HQ_PROFILE=full HQ_STT=off "$HQ" --profile stt --profile backup-tools config --format json |
  jq '[.services[].deploy.resources.limits.memory | tonumber] | add / 1048576 | floor')"
if ((on_rc != 0)) || ! grep -q 'full+stt ok' <<<"$gate_on"; then
  fail "stt: the memory gate with stt on (on demand, full) failed (exit $on_rc)"
elif [[ "$(jq -r '(.services | has("stt")), .services.worker.environment.STT_URL,
    .services.api.environment.STT_URL, .services.worker.environment.HQ_STT_DEMAND_DIR' <<<"$on_json" |
  paste -sd,)" != "false,http://stt:8000,http://stt:8000,/stt-demand" ]]; then
  fail "stt: HQ_STT=on: 'up' would start stt, or the worker/api lack STT_URL or the demand directory"
elif ! grep -qx stt <<<"$start_services"; then
  fail "stt: the on-demand starter (HQ_STT_START=1) does not get the stt service"
elif [[ "$(jq -r '.services.stt.restart' <<<"$(HQ_PROFILE=full HQ_STT=on HQ_STT_START=1 "$HQ" config --format json)")" != "no" ]]; then
  fail "stt: stt would come back by itself after a reboot (restart is not \"no\")"
elif ((burst >= whole)); then
  fail "stt: the burst ($burst MiB) does not leave out the start-up one-shots and the backup ($whole MiB)"
else
  pass "stt: on demand (not started by up, the starter alone), STT_URL and the demand dir set, a burst of $burst MiB"
fi
# Over the budget (a limit far too large for this test): refused, never by accident.
big_env="$T/stt-big.env"
cp "${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}" "$big_env"
printf 'MEM_STT=%s\n' 64g >>"$big_env"
refusal="$(HQ_ENV_FILE="$big_env" HQ_PROFILE=full HQ_STT=on "$HQ" --dry-run up --no-start 2>&1)" && hq_rc=0 || hq_rc=$?
rendered="$(HQ_ENV_FILE="$big_env" HQ_PROFILE=full HQ_STT=on "$HQ" config --format json 2>"$T/stt-warn")" &&
  cfg_rc=0 || cfg_rc=$?
big_gate="$(HQ_ENV_FILE="$big_env" HQ_STT=on CI=1 "$REPO_DIR/scripts/quality/memory-budget.sh" 2>&1)" &&
  big_rc=0 || big_rc=$?
off_gate="$(HQ_ENV_FILE="$big_env" HQ_STT=off CI=1 "$REPO_DIR/scripts/quality/memory-budget.sh" 2>&1)" &&
  off_rc=0 || off_rc=$?
if ((hq_rc != 3)) || ! grep -q 'HQ_STT=on refused' <<<"$refusal"; then
  fail "stt: hq.sh 'up' accepted HQ_STT=on over the memory budget (exit $hq_rc)"
elif ((cfg_rc != 0)) || ! grep -q 'HQ_STT=on ignored' "$T/stt-warn" ||
  [[ -n "$(jq -r '.services.worker.environment.STT_URL' <<<"$rendered")" ]]; then
  fail "stt: over the budget, a command that starts nothing did not run without stt (exit $cfg_rc)"
elif ((big_rc == 0)) || ! grep -q 'full+stt OVER (' <<<"$big_gate"; then
  fail "stt: the memory gate with stt on passed an over-budget burst"
elif ((off_rc != 0)) || ! grep -q 'full+stt OVER by .* not enabled' <<<"$off_gate"; then
  fail "stt: the memory gate with stt off: exit $off_rc, or the over-budget line is missing"
else
  pass "stt: over the budget it is shown while off, fails the gate and 'up' is refused while on"
fi
# The hub (MemTotal 15608 MiB): every player and the hub's speech at once.
hub_gate="$(CI='' HQ_MEMTOTAL_MB=15608 HQ_STT=on HQ_SUBSTITUTES=on HQ_SUBSTITUTES_WEB=on HQ_PROFILE=full \
  "$REPO_DIR/scripts/quality/memory-budget.sh" 2>&1)" && hub_rc=0 || hub_rc=$?
if ((hub_rc != 0)) || ! grep -q 'full+substitutes+substitutes-web+stt (on demand) ok' <<<"$hub_gate"; then
  fail "stt: on the hub (15608 MiB) full + substitutes + substitutes-web + stt does not fit (exit $hub_rc)"
else
  pass "stt: on the hub (15608 MiB) full + substitutes + substitutes-web + stt on demand fits"
fi
# The host's starter (infra/stt/on-demand.sh) with a fake hq.sh: started when
# asked, kept while asked, stopped when idle; nothing while off or for a stale ask.
od="$T/stt-od"
mkdir -p "$od"
cat >"$od/hq.sh" <<'FAKE'
#!/usr/bin/env bash
echo "${HQ_STT_START:-0} $*" >>"${0%/*}/calls"
if [[ "$*" == "ps --status running -q stt" ]]; then echo abc; fi
FAKE
chmod +x "$od/hq.sh"
od_run() { # od_run HQ_STT AGE_S -> the calls
  : >"$od/calls"
  touch -d "@$(($(date +%s) - $2))" "$od/want"
  HQ_STT="$1" HQ_SH="$od/hq.sh" HQ_STT_WANT="$od/want" HQ_ONESHOT_LOCK="$od/lock" \
    STT_IDLE_STOP_S=2 STT_POLL_S=1 STT_MAX_HOLD_S=30 "$REPO_DIR/infra/stt/on-demand.sh" >/dev/null
  paste -sd'|' "$od/calls"
}
od_on="$(od_run on 0)"
od_off="$(od_run off 0)"
od_old="$(od_run on 600)"
if [[ "$od_on" != "1 up -d --no-deps stt|1 ps --status running -q stt|1 stop -t 10 stt" &&
  "$od_on" != "1 up -d --no-deps stt|1 stop -t 10 stt" ]]; then
  fail "stt: the on-demand starter did not start, keep and stop stt ($od_on)"
elif [[ -n "$od_off" || -n "$od_old" ]]; then
  fail "stt: the starter acted while stt is off or for a stale request ($od_off / $od_old)"
else
  pass "stt: the host's starter starts it when asked and stops it when idle (no Docker socket in the worker)"
fi
off_url="$(HQ_PROFILE=full HQ_STT=off "$HQ" config --format json | jq -r '.services.worker.environment.STT_URL')"
if [[ -n "$off_url" ]]; then
  fail "stt: STT_URL is '$off_url' while stt is off"
else
  pass "stt: STT_URL empty while stt is off"
fi

# ---------------------------------------------- tracing (review 7.1 §0.2) --
# Tempo and the collector are an opt-in profile: off by default (not rendered,
# Prometheus mounts the empty scrape dir), on with HQ_TRACING=on.
off_services="$(HQ_PROFILE=full HQ_TRACING=off "$HQ" config --services)"
on_json="$(HQ_PROFILE=full HQ_TRACING=on "$HQ" config --format json)"
off_scrape="$(HQ_PROFILE=full HQ_TRACING=off "$HQ" config --format json |
  jq -r '.services.prometheus.volumes[] | select(.target == "/etc/prometheus/scrape-tracing") | .source')"
if grep -qxE 'tempo|otel-collector' <<<"$off_services" || [[ "$off_scrape" != */scrape-tracing/off ]]; then
  fail "tracing: on by default (services or the scrape dir $off_scrape)"
elif [[ "$(jq -r '.services | has("tempo") and has("otel-collector")' <<<"$on_json")" != true ]] ||
  [[ "$(jq -r '.services.prometheus.volumes[] | select(.target == "/etc/prometheus/scrape-tracing") | .source' <<<"$on_json")" != */scrape-tracing/on ]]; then
  fail "tracing: HQ_TRACING=on does not start Tempo and the collector, or Prometheus does not scrape them"
else
  pass "tracing: off by default; HQ_TRACING=on adds Tempo, the collector and their scrape jobs"
fi

# ------------------------------------------------- mcp (prompt 12 §14) ----
# The MCP container servers are an opt-in profile: off by default (not
# rendered, the api's MCP_CONTAINERS=off); on where it fits (full: the api
# gets MCP_CONTAINERS=on); where it does not fit (lean) the memory gate fails
# once it is switched on and hq.sh refuses to start it, and a command that
# starts nothing renders without it.
mcp_of() { # mcp_of PROFILE HQ_MCP -> "<has mcp-time>,<api MCP_CONTAINERS>"
  HQ_PROFILE="$1" HQ_MCP="$2" "$HQ" config --format json 2>/dev/null |
    jq -r '[(.services | has("mcp-time")), .services.api.environment.MCP_CONTAINERS] | map(tostring) | join(",")'
}
mcp_gate="$(HQ_MCP=on CI=1 "$REPO_DIR/scripts/quality/memory-budget.sh" 2>&1)" && mcp_gate_rc=0 || mcp_gate_rc=$?
mcp_refusal="$(HQ_PROFILE=lean HQ_MCP=on "$HQ" --dry-run up --no-start 2>&1)" && mcp_up_rc=0 || mcp_up_rc=$?
if [[ "$(mcp_of full off)" != "false,off" ]]; then
  fail "mcp: on by default ($(mcp_of full off))"
elif [[ "$(mcp_of full on)" != "true,on" ]]; then
  fail "mcp: HQ_MCP=on within the budget (full) does not start it or tell the api ($(mcp_of full on))"
elif ((mcp_gate_rc == 0)) || ! grep -q 'lean+mcp OVER (' <<<"$mcp_gate"; then
  fail "mcp: the memory gate with HQ_MCP=on passed lean+mcp over the budget"
elif ((mcp_up_rc != 3)) || ! grep -q 'HQ_MCP=on refused' <<<"$mcp_refusal"; then
  fail "mcp: hq.sh 'up' accepted HQ_MCP=on over the memory budget (lean, exit $mcp_up_rc)"
elif [[ "$(mcp_of lean on)" != "false,off" ]]; then
  fail "mcp: over the budget, a command that starts nothing did not run without mcp"
else
  pass "mcp: off by default; on where it fits (MCP_CONTAINERS=on); without room the gate fails and 'up' is refused"
fi
# ------------------------------------ the substitute players (prompt 12 §9.1) --
# Both profiles off by default; switched on, the lean profile (no room) refuses
# them and the full one takes them (and tells the api SUBSTITUTES_RUNNER=on):
# both together fit the hub's own server (MemTotal 15608 MiB, the owner's
# browser-web +300 MiB of 2026-10-30), not the full profile's bare reference.
subs_off="$(HQ_PROFILE=full HQ_SUBSTITUTES=off HQ_SUBSTITUTES_WEB=off "$HQ" config --services)"
if grep -qxE 'substitute-runner|browser-web|browser-web-login|web-login-relay' <<<"$subs_off"; then
  fail "substitutes: a substitute service is on by default"
else
  pass "substitutes: the runner, the profile browser and the sign-in window are off by default"
fi
refusal="$(HQ_PROFILE=lean HQ_SUBSTITUTES=on "$HQ" --dry-run up --no-start 2>&1)" && sub_rc=0 || sub_rc=$?
web_refusal="$(HQ_PROFILE=lean HQ_SUBSTITUTES_WEB=on "$HQ" --dry-run up --no-start 2>&1)" &&
  web_rc=0 || web_rc=$?
on_services="$(HQ_MEMTOTAL_MB=15608 HQ_PROFILE=full HQ_SUBSTITUTES=on HQ_SUBSTITUTES_WEB=on "$HQ" config --services)"
if ((sub_rc != 3)) || ! grep -q 'HQ_SUBSTITUTES=on refused' <<<"$refusal"; then
  fail "substitutes: lean accepted HQ_SUBSTITUTES=on over the memory budget (exit $sub_rc)"
elif ((web_rc != 3)) || ! grep -q 'HQ_SUBSTITUTES_WEB=on refused' <<<"$web_refusal"; then
  fail "substitutes: lean accepted HQ_SUBSTITUTES_WEB=on over the memory budget (exit $web_rc)"
elif ! grep -qx substitute-runner <<<"$on_services" || ! grep -qx browser-web <<<"$on_services"; then
  fail "substitutes: full did not take both profiles within its budget"
elif [[ "$(HQ_PROFILE=full HQ_SUBSTITUTES=on "$HQ" --print-substitutes-runner)" != on ]] ||
  [[ "$(HQ_PROFILE=full HQ_SUBSTITUTES=off "$HQ" --print-substitutes-runner)" != off ]]; then
  fail "substitutes: hq.sh does not export SUBSTITUTES_RUNNER=on while the runner is on"
else
  pass "substitutes: refused over the budget (lean), taken within it (full), SUBSTITUTES_RUNNER follows"
fi
# The owner's sign-in window: noVNC on the host's loopback only, at most 15 minutes.
login_json="$(HQ_PROFILE=full "$HQ" --profile web-login config --format json)"
published="$(jq -r '[.services | to_entries[] | select(.key == "web-login-relay" or .key == "browser-web-login")
  | (.value.ports // [])[] | "\(.host_ip // "0.0.0.0"):\(.published)"] | join(",")' <<<"$login_json")"
# shellcheck disable=SC2016 # the script's own text, not an expansion
if [[ "$published" != "127.0.0.1:6080" ]]; then
  fail "web-login: published $published (only 127.0.0.1:6080)"
elif [[ "$(jq -r '.services["browser-web-login"].environment.HQ_WEB_LOGIN_SECONDS' <<<"$login_json")" != 900 ]] ||
  ! grep -q '((seconds > 900' "$REPO_DIR/services/egress/web-login.sh" ||
  ! grep -qF 'timeout "$seconds" "$chrome" "${flags[@]}" "$url"' "$REPO_DIR/services/egress/web-login.sh" ||
  ((10#$(jq -r '.services["web-login-relay"].environment.RELAY_SECONDS' <<<"$login_json") > 960)); then
  fail "web-login: the window is not closed after 15 minutes"
elif ! grep -q -- '-localhost -rfbport 5900' "$REPO_DIR/services/egress/web-login.sh"; then
  fail "web-login: x11vnc is not on the container's loopback"
else
  pass "web-login: noVNC on 127.0.0.1:6080 only, closed after 15 minutes, VNC on loopback"
fi
# The dispatcher (fake api, fake runner): off, locked, a call, a sign-in, a review.
if out="$(bash "$REPO_DIR/infra/substitutes/test-dispatch.sh" 2>&1)"; then
  pass "substitutes: the dispatcher ($(grep -c ': ok:' <<<"$out") cases)"
else
  fail "substitutes: the dispatcher: $(grep FAIL <<<"$out" | head -3 | tr '\n' ' ')"
fi
unit="$REPO_DIR/infra/systemd/coinepro-hq-substitutes.service"
missing=()
for want in NoNewPrivileges=yes ProtectSystem=full CapabilityBoundingSet= \
  RuntimeDirectory=coinepro-hq-substitutes RuntimeDirectoryMode=0700; do
  grep -qxF "$want" "$unit" || missing+=("$want")
done
if ((${#missing[@]})); then
  fail "systemd: the substitutes unit lacks ${missing[*]}"
else
  pass "systemd: the substitutes unit is sandboxed (its own 0700 runtime dir)"
fi
# ------------------------------------------ the render worker (prompt 13 §2.3) --
# Off by default (not rendered, the api's HQ_MEDIA=off); on where it fits
# (full: both one-shots, the api told HQ_MEDIA=on); where it does not fit
# (lean) the memory gate fails once switched on and hq.sh refuses to start it;
# the pass does nothing while HQ_MEDIA is off.
media_of() { # media_of PROFILE HQ_MEDIA -> "<has media-render>,<api HQ_MEDIA>"
  HQ_PROFILE="$1" HQ_MEDIA="$2" "$HQ" config --format json 2>/dev/null |
    jq -r '[(.services | has("media-render")), .services.api.environment.HQ_MEDIA] | map(tostring) | join(",")'
}
media_gate="$(HQ_MEDIA=on CI=1 "$REPO_DIR/scripts/quality/memory-budget.sh" 2>&1)" && media_gate_rc=0 ||
  media_gate_rc=$?
media_refusal="$(HQ_PROFILE=lean HQ_MEDIA=on "$HQ" --dry-run up --no-start 2>&1)" && media_up_rc=0 ||
  media_up_rc=$?
media_pass="$(HQ_MEDIA=off HQ_ONESHOT_LOCK=/nonexistent/lock "$REPO_DIR/infra/media/run-once.sh" 2>&1)" &&
  media_pass_rc=0 || media_pass_rc=$?
if [[ "$(media_of full off)" != "false,off" ]]; then
  fail "media: on by default ($(media_of full off))"
elif [[ "$(media_of full on)" != "true,on" ]] || [[ "$(HQ_PROFILE=full HQ_MEDIA=on "$HQ" --print-media)" != on ]]; then
  fail "media: HQ_MEDIA=on within the budget (full) does not run it or tell the api ($(media_of full on))"
elif ((media_gate_rc == 0)) || ! grep -q 'lean+media OVER (' <<<"$media_gate"; then
  fail "media: the memory gate with HQ_MEDIA=on passed lean+media over the budget"
elif ((media_up_rc != 3)) || ! grep -q 'HQ_MEDIA=on refused' <<<"$media_refusal"; then
  fail "media: hq.sh 'up' accepted HQ_MEDIA=on over the memory budget (lean, exit $media_up_rc)"
elif ((media_pass_rc != 0)) || [[ -n "$media_pass" ]]; then
  fail "media: the render pass did something while HQ_MEDIA is off"
else
  pass "media: off by default; on where it fits (HQ_MEDIA=on); refused without room; the pass is a no-op while off"
fi
# ------------------------------------------- the archive's OCR (prompt 14 §4) --
# Off by default (no ocr service, an empty HQ_OCR_URL); on where it fits
# (full: the service, and the worker - only the worker - told where it is);
# where it does not fit (lean) the memory gate fails once switched on, hq.sh
# refuses to start it, and a command that starts nothing runs without it.
ocr_of() { # ocr_of PROFILE HQ_OCR -> "<has ocr>,<worker HQ_OCR_URL>,<api has HQ_OCR_URL>"
  HQ_PROFILE="$1" HQ_OCR="$2" "$HQ" config --format json 2>/dev/null |
    jq -r '[(.services | has("ocr")), (.services.worker.environment.HQ_OCR_URL // ""),
            (.services.api.environment | has("HQ_OCR_URL"))] | map(tostring) | join(",")'
}
ocr_gate="$(HQ_OCR=on CI=1 "$REPO_DIR/scripts/quality/memory-budget.sh" 2>&1)" && ocr_gate_rc=0 || ocr_gate_rc=$?
ocr_refusal="$(HQ_PROFILE=lean HQ_OCR=on "$HQ" --dry-run up --no-start 2>&1)" && ocr_up_rc=0 || ocr_up_rc=$?
if [[ "$(ocr_of full off)" != "false,,false" ]]; then
  fail "ocr: on by default ($(ocr_of full off))"
elif [[ "$(ocr_of full on)" != "true,http://ocr:8088,false" ]] ||
  [[ "$(HQ_PROFILE=full HQ_OCR=on "$HQ" --print-ocr)" != on ]]; then
  fail "ocr: HQ_OCR=on within the budget (full) does not run it or tell the worker ($(ocr_of full on))"
elif ((ocr_gate_rc == 0)) || ! grep -q 'lean+ocr OVER (' <<<"$ocr_gate"; then
  fail "ocr: the memory gate with HQ_OCR=on passed lean+ocr over the budget"
elif ((ocr_up_rc != 3)) || ! grep -q 'HQ_OCR=on refused' <<<"$ocr_refusal"; then
  fail "ocr: hq.sh 'up' accepted HQ_OCR=on over the memory budget (lean, exit $ocr_up_rc)"
elif [[ "$(ocr_of lean on)" != "false,,false" ]]; then
  fail "ocr: over the budget, a command that starts nothing did not run without ocr"
else
  pass "ocr: off by default; on where it fits (the worker alone gets HQ_OCR_URL); refused without room"
fi

# ------------------------------------------- memory near the cap (19.1) ----
# A long-running service at 85% of its cap for 15 minutes is an alert (and,
# through PR-062, a finding); a one-shot job and a service below it are not.
# Temporal's caches are bounded in its dynamic config (no blind restart).
prom_image="$(HQ_PROFILE=full "$HQ" config --format json | jq -r .services.prometheus.image)"
cat >"$T/containers-test.yml" <<'YAML'
rule_files: [/rules/containers.rules.yml]
evaluation_interval: 1m
tests:
  - interval: 1m
    input_series:
      - series: 'hq_container_memory_bytes{service="temporal"}'
        values: '700000000x30'
      - series: 'hq_container_memory_limit_bytes{service="temporal"}'
        values: '805306368x30'
      - series: 'hq_container_up{service="temporal",oneshot="false"}'
        values: '1x30'
      - series: 'hq_container_memory_bytes{service="api"}'
        values: '100000000x30'
      - series: 'hq_container_memory_limit_bytes{service="api"}'
        values: '402653184x30'
      - series: 'hq_container_up{service="api",oneshot="false"}'
        values: '1x30'
      - series: 'hq_container_memory_bytes{service="backup-tools"}'
        values: '260000000x30'
      - series: 'hq_container_memory_limit_bytes{service="backup-tools"}'
        values: '268435456x30'
      - series: 'hq_container_up{service="backup-tools",oneshot="true"}'
        values: '1x30'
    alert_rule_test:
      - eval_time: 10m
        alertname: HqContainerMemoryNearCap
        exp_alerts: []
      - eval_time: 20m
        alertname: HqContainerMemoryNearCap
        exp_alerts:
          - exp_labels: {severity: warning, category: capacity, service: temporal}
            exp_annotations:
              summary: "temporal uses more than 85% of its memory cap"
              description: "docker stats on the hub; for temporal see RUNBOOK (Temporal memory)"
YAML
temporal_keys="$(grep -cE '^history\.(cacheSizeBasedLimit|hostLevelCacheMaxSizeBytes|eventsHostLevelCacheMaxSizeBytes|enableHostLevelEventsCache):' \
  "$REPO_DIR/infra/temporal/dynamicconfig/hq.yaml")"
if ! out="$(docker run --rm --network none --entrypoint promtool \
  -v "$REPO_DIR/infra/observability/prometheus/rules:/rules:ro" -v "$T/containers-test.yml:/t.yml:ro" \
  "$prom_image" test rules /t.yml 2>&1)"; then
  fail "memory: the near-cap alert: $(tail -n6 <<<"$out")"
elif ((temporal_keys != 4)); then
  fail "memory: Temporal's caches are not bounded in its dynamic config ($temporal_keys of 4 keys)"
else
  pass "memory: a service at 85% of its cap for 15 minutes alerts (not a one-shot); Temporal's caches bounded"
fi

exit "$failed"
