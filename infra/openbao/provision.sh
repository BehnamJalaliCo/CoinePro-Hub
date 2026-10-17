#!/usr/bin/env bash
# Idempotent OpenBao setup for the model layer (prompt 03 §7). Run by `make up`.
# Never prints a secret: values travel through stdin, environment variables
# of short-lived jq/curl processes, or files with mode 600.
#
#   - KV v2 at kv/, AppRole auth
#   - policies: llm-router, claude-runtime, hq-api, hq-worker (each reads only
#     its own paths), hq-admin
#   - a non-root admin token (periodic, 32 days, renewed on every run)
#       -> $HQ_SECRETS_DIR/openbao-admin.token (600)
#   - AppRole credentials per service, owned by the container uid (10001)
#       -> $HQ_SECRETS_DIR/services/<service>/approle.json (600)
#   - router<->runtime token, Prometheus metrics token, the first API caller
#   - empty key paths for the (disabled) API connections
#   - prompt 04: hq-api config (agent token key), Web Push (VAPID) keys,
#     empty FCM/Telegram credentials (channels stay off until the owner fills them)
#   - prompt 05: the agent runtime's tokens (kv/hq-agents/runtime: llm-router
#     caller hq-agents, the Tool Gateway's caller) and the gateway's digest file
# The root token is used only while the admin token does not exist yet; it is
# NOT revoked here (owner's decision).
#
# Routine runs need no sudo (prompt 05 §1.5): the files this script installs
# for the containers (owned by their uid, unreadable to Hub) are listed in a
# manifest ($HQ_SECRETS_DIR/.provisioned, 600, Hub's). Only a file not in the
# manifest yet needs sudo, i.e. `make bootstrap` (once, or when a service is
# added); it records files that already exist and installs missing ones.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
POLICY_DIR="$REPO_DIR/infra/openbao/policies"
INIT_FILE="$SECRETS_DIR/openbao-init.json"
MANIFEST="$SECRETS_DIR/.provisioned"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
CALLER_FILE="$SECRETS_DIR/llm-router-caller-hq-ops.token"
SERVICE_UID=10001
PROMETHEUS_UID=65534  # "nobody" in the Prometheus image
# hq-internal (172.30.0.0/24) + hq-llm (172.30.1.0/24)
ROUTER_CIDRS='["172.30.0.0/23"]'
RUNTIME_CIDRS='["172.30.1.0/24"]'
CORE_CIDRS='["172.30.0.0/24"]'
API_CONNECTIONS=(anthropic-api openai google-gemini openai-compatible)

umask 077
log() { printf 'openbao-provision: %s\n' "$*"; }
die() { printf 'openbao-provision: %s\n' "$*" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# api METHOD PATH [body on stdin] -> response body in $WORK/resp, HTTP code on stdout
api() {
  local method="$1" path="$2" body=()
  [[ "$method" != GET ]] && body=(--data-binary @-)
  curl -sS -o "$WORK/resp" -w '%{http_code}' -X "$method" \
    -H @"$WORK/auth" -H 'Content-Type: application/json' "${body[@]}" \
    "$BAO_ADDR/v1/$path" </dev/stdin
}
expect() { # expect CODE... -- fail unless the last api call returned one of them
  local code="$1"; shift
  for ok in "$@"; do [[ "$code" == "$ok" ]] && return 0; done
  die "unexpected HTTP $code from OpenBao"
}
use_token() { printf 'X-Vault-Token: %s\n' "$1" >"$WORK/auth"; }
sha256() { sha256sum | cut -d' ' -f1; }
newtoken() { openssl rand -hex 32; }
touch "$MANIFEST" && chmod 600 "$MANIFEST"
installed() { # installed DEST -- already installed for its container?
  # Listed in the manifest: yes, without sudo. Not listed: only sudo can look
  # (the file belongs to the container's uid); without sudo stop BEFORE any
  # change, so nothing is regenerated half-way.
  if grep -qxF "$1" "$MANIFEST"; then return 0; fi
  sudo -n true 2>/dev/null || die "$1 is not in the manifest yet: run make bootstrap (needs sudo, once)"
  if sudo test -s "$1"; then
    printf '%s\n' "$1" >>"$MANIFEST"
    return 0
  fi
  return 1
}
need_sudo() {
  sudo -n true 2>/dev/null || die "first-time install of $1 needs sudo: run make bootstrap"
}
install_secret() { # install_secret OWNER_UID DEST < content
  local owner="$1" dest="$2"
  need_sudo "$dest"
  sudo install -d -o "$owner" -g "$owner" -m 0700 "$(dirname "$dest")"
  cat >"$WORK/file"
  sudo install -o "$owner" -g "$owner" -m 0600 "$WORK/file" "$dest"
  rm -f "$WORK/file"
  grep -qxF "$dest" "$MANIFEST" || printf '%s\n' "$dest" >>"$MANIFEST"
}

# ---------------------------------------------------------------- token ----
[[ "$(curl -s "$BAO_ADDR/v1/sys/health" -o /dev/null -w '%{http_code}')" == 200 ]] ||
  die "OpenBao is not initialised/unsealed/active (run make up)"

token_valid() { use_token "$1"; [[ "$(api GET auth/token/lookup-self </dev/null)" == 200 ]]; }

if [[ -s "$ADMIN_FILE" ]] && token_valid "$(cat "$ADMIN_FILE")"; then
  using="admin"
else
  [[ -r "$INIT_FILE" ]] || die "no admin token and no init file"
  token_valid "$(jq -r .root_token "$INIT_FILE")" || die "root token rejected"
  using="root"
fi
log "authenticated with the $using token"

# ------------------------------------------------------ mounts and auth ----
expect "$(api GET sys/mounts </dev/null)" 200
if ! jq -e '.data["kv/"] // ."kv/"' "$WORK/resp" >/dev/null; then
  expect "$(echo '{"type":"kv","options":{"version":"2"},"description":"CoinePro HQ secrets"}' | api POST sys/mounts/kv)" 204
  log "enabled KV v2 at kv/"
fi
expect "$(api GET sys/auth </dev/null)" 200
if ! jq -e '.data["approle/"] // ."approle/"' "$WORK/resp" >/dev/null; then
  expect "$(echo '{"type":"approle"}' | api POST sys/auth/approle)" 204
  log "enabled AppRole auth"
fi

for policy in "$POLICY_DIR"/*.hcl; do
  name="$(basename "$policy" .hcl)"
  expect "$(jq -Rs '{policy: .}' "$policy" | api PUT "sys/policies/acl/$name")" 204
done
log "policies: $(basename -a "$POLICY_DIR"/*.hcl | sed 's/\.hcl$//' | paste -sd' ')"

# ------------------------------------------------------- admin token ----
if [[ "$using" == root ]]; then
  expect "$(echo '{"policies":["hq-admin"],"period":"768h","no_parent":true,"display_name":"hq-admin","meta":{"purpose":"CoinePro HQ admin (not root)"}}' |
    api POST auth/token/create)" 200
  jq -r .auth.client_token "$WORK/resp" >"$ADMIN_FILE.tmp"
  chmod 600 "$ADMIN_FILE.tmp"
  mv "$ADMIN_FILE.tmp" "$ADMIN_FILE"
  log "created the non-root admin token -> $ADMIN_FILE (600)"
fi
use_token "$(cat "$ADMIN_FILE")"
expect "$(echo '{}' | api POST auth/token/renew-self)" 200

# -------------------------------------------------------------- AppRoles ----
approle() { # approle NAME CIDRS
  local name="$1" cidrs="$2" dest="$SECRETS_DIR/services/$1/approle.json"
  expect "$(jq -n --argjson c "$cidrs" --arg p "$name" '{
      token_policies: [$p], token_no_default_policy: true, token_ttl: "1h",
      token_max_ttl: "4h", secret_id_ttl: "0", token_bound_cidrs: $c,
      secret_id_bound_cidrs: $c}' | api POST "auth/approle/role/$name")" 204
  if installed "$dest"; then
    return
  fi
  expect "$(api GET "auth/approle/role/$name/role-id" </dev/null)" 200
  jq -r .data.role_id "$WORK/resp" >"$WORK/role_id"
  expect "$(echo '{}' | api POST "auth/approle/role/$name/secret-id")" 200
  jq --rawfile r "$WORK/role_id" '{role_id: ($r | rtrimstr("\n")), secret_id: .data.secret_id}' "$WORK/resp" |
    install_secret "$SERVICE_UID" "$dest"
  log "AppRole $name: credentials -> $dest (600, uid $SERVICE_UID)"
}
approle llm-router "$ROUTER_CIDRS"
approle claude-runtime "$RUNTIME_CIDRS"
approle hq-api "$CORE_CIDRS"
approle hq-worker "$CORE_CIDRS"

# ------------------------------------------------------------ KV secrets ----
kv_exists() { [[ "$(api GET "kv/data/$1" </dev/null)" == 200 ]]; }
kv_put() { expect "$(api POST "kv/data/$1")" 200 204; }  # body on stdin

prom_token="$SECRETS_DIR/services/prometheus/llm-metrics.token"
if ! kv_exists llm-router/config || ! installed "$prom_token"; then
  runtime_token="$(newtoken)"
  metrics_token="$(newtoken)"
  RT="$runtime_token" MH="$(printf '%s' "$metrics_token" | sha256)" \
    jq -n '{data: {runtime_token: env.RT, metrics_token_sha256: env.MH}}' | kv_put llm-router/config
  RH="$(printf '%s' "$runtime_token" | sha256)" MH="$(printf '%s' "$metrics_token" | sha256)" \
    jq -n '{data: {router_token_sha256: env.RH, metrics_token_sha256: env.MH}}' | kv_put claude-runtime/config
  printf '%s' "$metrics_token" | install_secret "$PROMETHEUS_UID" "$prom_token"
  unset runtime_token metrics_token
  log "router<->runtime token and metrics token (re)generated"
fi

if ! kv_exists llm-router/callers; then
  caller_token="$(newtoken)"
  TH="$(printf '%s' "$caller_token" | sha256)" jq -n '{data: {callers: {"hq-ops": {
      token_sha256: env.TH, rpm: 30, max_input_chars: 100000}}}}' | kv_put llm-router/callers
  printf '%s' "$caller_token" >"$CALLER_FILE"
  chmod 600 "$CALLER_FILE"
  unset caller_token
  log "first API caller hq-ops -> $CALLER_FILE (600)"
fi

for key in "${API_CONNECTIONS[@]}"; do
  if ! kv_exists "llm-connections/$key"; then
    jq -n '{data: {api_key: "", note: "set by the owner when this connection is enabled"}}' |
      kv_put "llm-connections/$key"
  fi
done
log "key paths ready: kv/llm-connections/{$(IFS=,; echo "${API_CONNECTIONS[*]}")}"

# ------------------------------------------------------ holding core (p04) --
# Agent tokens are HMAC-signed per run by the agent runtime (prompt 05) and
# verified by the api; service tokens are added per caller when needed.
if ! kv_exists hq-api/config; then
  AK="$(openssl rand -hex 32)" jq -n '{data: {agent_token_key: env.AK, service_tokens: {}}}' |
    kv_put hq-api/config
  log "hq-api config created (agent token key)"
fi

# Web Push (VAPID): an EC P-256 key pair; the public key is the raw point,
# base64url. The subject falls back to the public origin once there is a domain.
if ! kv_exists hq-api/webpush; then
  openssl ecparam -name prime256v1 -genkey -noout -out "$WORK/vapid.pem" 2>/dev/null
  pub="$(openssl ec -in "$WORK/vapid.pem" -pubout -outform DER 2>/dev/null | tail -c 65 |
    base64 -w0 | tr '+/' '-_' | tr -d '=')"
  PEM="$(cat "$WORK/vapid.pem")" PUB="$pub" jq -n '{data: {private_key_pem: env.PEM, public_key: env.PUB, subject: ""}}' |
    kv_put hq-api/webpush
  rm -f "$WORK/vapid.pem"
  unset pub
  log "Web Push (VAPID) keys created"
fi

for channel in fcm telegram; do
  if ! kv_exists "hq-api/channels/$channel"; then
    case "$channel" in
      fcm) placeholder='{"data": {"service_account_json": "", "note": "set by the owner to switch FCM on"}}' ;;
      telegram) placeholder='{"data": {"bot_token": "", "chat_id": "", "note": "set by the owner; backup only, never approvals"}}' ;;
    esac
    printf '%s' "$placeholder" | kv_put "hq-api/channels/$channel"
  fi
done
log "channel paths ready: kv/hq-api/channels/{fcm,telegram} (off until filled)"

# ---------------------------------------------------- agent runtime (p05) --
# The worker runs the agents: its own llm-router caller (hq-agents) and the
# Tool Gateway's only caller. The gateway has no OpenBao access: it gets the
# digest of the worker's token as a file (600, uid 10001).
gw_digest="$SECRETS_DIR/services/gateway/worker-token.sha256"
if ! kv_exists hq-agents/runtime || ! installed "$gw_digest"; then
  llm_token="$(newtoken)"
  gw_token="$(newtoken)"
  expect "$(api GET kv/data/llm-router/callers </dev/null)" 200
  LH="$(printf '%s' "$llm_token" | sha256)" jq '{data: (.data.data | .callers["hq-agents"] =
      {token_sha256: env.LH, rpm: 240, max_input_chars: 200000})}' "$WORK/resp" | kv_put llm-router/callers
  LT="$llm_token" GT="$gw_token" jq -n '{data: {llm_router_token: env.LT, gateway_token: env.GT}}' |
    kv_put hq-agents/runtime
  printf '%s' "$gw_token" | sha256 | install_secret "$SERVICE_UID" "$gw_digest"
  unset llm_token gw_token
  log "agent runtime: llm-router caller hq-agents and the gateway's token (re)generated"
fi
log "done"
