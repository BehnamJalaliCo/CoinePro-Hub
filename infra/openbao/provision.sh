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
#   - prompt 09: the provisioner's AppRole (read-only kv/provisioning/* and its
#     own kv/provisioner/config) and its api service token (the digest goes to
#     kv/hq-api/config service_tokens.provisioner; the api reads it at start)
#   - prompt 07: the backups' restic password (kv/backup/restic, generated once,
#     never printed) and the hq-backup AppRole of the host's backup scripts
#       -> $HQ_SECRETS_DIR/backup/approle.json (600, Hub's own: no sudo)
#   - prompt 10: the customer pseudonym's key (kv/support/pseudonym, made once
#     with cas 0, never printed; infra/openbao/kv-once.sh); the worker's api
#     service token for the revenue connector (kv/hq-agents/connector; its
#     digest in kv/hq-api/config service_tokens.worker)
#   - prompt 12 §9.1: the substitute players' host dispatcher's api service
#     token (its digest in kv/hq-api/config service_tokens.substitutes; the
#     token only in $HQ_SECRETS_DIR/substitutes/api-auth, 600, Hub's own)
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
need_sudo() { # need_sudo DEST -- call BEFORE the first write a file install depends on
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
# hq-prov (prompt 09 §4): the provisioner reaches OpenBao there only.
approle provisioner '["172.30.10.0/24"]'

# The host's backup scripts (user Hub, through 127.0.0.1:8200): their own
# AppRole, read-only on kv/backup/*. Hub owns the file, so no sudo is needed.
backup_creds="$SECRETS_DIR/backup/approle.json"
expect "$(jq -n '{token_policies: ["hq-backup"], token_no_default_policy: true, token_ttl: "1h",
    token_max_ttl: "4h", secret_id_ttl: "0"}' | api POST auth/approle/role/hq-backup)" 204
if [[ ! -s "$backup_creds" ]]; then
  install -d -m 0700 "$SECRETS_DIR/backup"
  expect "$(api GET auth/approle/role/hq-backup/role-id </dev/null)" 200
  jq -r .data.role_id "$WORK/resp" >"$WORK/role_id"
  expect "$(echo '{}' | api POST auth/approle/role/hq-backup/secret-id)" 200
  jq --rawfile r "$WORK/role_id" '{role_id: ($r | rtrimstr("\n")), secret_id: .data.secret_id}' \
    "$WORK/resp" >"$backup_creds.tmp"
  chmod 600 "$backup_creds.tmp"
  mv "$backup_creds.tmp" "$backup_creds"
  log "AppRole hq-backup: credentials -> $backup_creds (600)"
fi

# ------------------------------------------------- node-exporter (p07) ----
# node-exporter listens on the host, on the hq-internal gateway address. A
# container on a network with a route out (Caddy, egress, SearXNG) can reach
# the host's own addresses too: Docker gives no way to stop that without
# iptables, which is the owner's (CLAUDE.md rule 4). So its metrics need basic
# auth: Prometheus holds the password, node-exporter only the bcrypt hash.
NODE_EXPORTER_UID=65534  # "nobody" in the node-exporter image
ne_pass="$SECRETS_DIR/services/prometheus/node-exporter.password"
ne_web="$SECRETS_DIR/services/node-exporter/web.yml"
if ! installed "$ne_pass" || ! installed "$ne_web"; then
  need_sudo "$ne_web"
  ne_pw="$(openssl rand -hex 32)"
  ne_hash="$(NE_PW="$ne_pw" python3 -c 'import bcrypt, os
print(bcrypt.hashpw(os.environ["NE_PW"].encode(), bcrypt.gensalt(10)).decode())')"
  printf '%s' "$ne_pw" | install_secret "$PROMETHEUS_UID" "$ne_pass"
  printf 'basic_auth_users:\n  prometheus: %s\n' "$ne_hash" | install_secret "$NODE_EXPORTER_UID" "$ne_web"
  unset ne_pw ne_hash
  log "node-exporter: basic auth for Prometheus (password and hash installed, never printed)"
fi

# ------------------------------------------------------------ KV secrets ----
kv_exists() { [[ "$(api GET "kv/data/$1" </dev/null)" == 200 ]]; }
kv_put() { expect "$(api POST "kv/data/$1")" 200 204; }  # body on stdin

prom_token="$SECRETS_DIR/services/prometheus/llm-metrics.token"
if ! kv_exists llm-router/config || ! installed "$prom_token"; then
  # The new tokens go to KV and to a file only sudo can install: without sudo
  # stop before KV changes, or router, runtime and Prometheus would disagree.
  need_sudo "$prom_token"
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
  # As above: without sudo stop before the callers and KV change, or the
  # gateway would keep the digest of a token the worker no longer has.
  need_sudo "$gw_digest"
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
# --------------------------------------------------------- provisioner (p09) --
# Its token for the api's internal provisioning endpoints (service principal
# "provisioner"): kept in kv/provisioner/config for it, its sha256 in the
# api's service_tokens. Made once; the api reads service tokens at start.
if ! kv_exists provisioner/config; then
  prov_token="$(newtoken)"
  expect "$(api GET kv/data/hq-api/config </dev/null)" 200
  PH="$(printf '%s' "$prov_token" | sha256)" jq '{data: (.data.data | .service_tokens =
      ((.service_tokens // {}) + {provisioner: env.PH}))}' "$WORK/resp" | kv_put hq-api/config
  PT="$prov_token" jq -n '{data: {api_token: env.PT}}' | kv_put provisioner/config
  unset prov_token
  log "provisioner: its api service token created (digest in hq-api/config; restart the api)"
fi

# ------------------------------------------- the worker's connector (p10) --
# Prompt 10 §2.2: the worker's own api service token ("worker"), carried by
# the gateway's connector calls (the revenue pulls): kept in
# kv/hq-agents/connector for the worker, its sha256 in the api's
# service_tokens. Made once; the api reads service tokens at start.
if ! kv_exists hq-agents/connector; then
  conn_token="$(newtoken)"
  expect "$(api GET kv/data/hq-api/config </dev/null)" 200
  CH="$(printf '%s' "$conn_token" | sha256)" jq '{data: (.data.data | .service_tokens =
      ((.service_tokens // {}) + {worker: env.CH}))}' "$WORK/resp" | kv_put hq-api/config
  CT="$conn_token" jq -n '{data: {api_token: env.CT}}' | kv_put hq-agents/connector
  unset conn_token
  log "worker: its api service token for the connector created (digest in hq-api/config; restart the api)"
fi

# --------------------------------------- the substitute players (p12) --
# Prompt 12 §9.1: the host dispatcher's api service token ("substitutes",
# infra/substitutes/dispatch.sh): its sha256 in the api's service_tokens, the
# token itself only in a header file of Hub's own (600, no sudo), never
# printed. Made once; the api reads service tokens at start.
subs_auth="$SECRETS_DIR/substitutes/api-auth"
if [[ ! -s "$subs_auth" ]]; then
  subs_token="$(newtoken)"
  expect "$(api GET kv/data/hq-api/config </dev/null)" 200
  SH="$(printf '%s' "$subs_token" | sha256)" jq '{data: (.data.data | .service_tokens =
      ((.service_tokens // {}) + {substitutes: env.SH}))}' "$WORK/resp" | kv_put hq-api/config
  install -d -m 0700 "$SECRETS_DIR/substitutes"
  (umask 077 && printf 'Authorization: Bearer %s\n' "$subs_token" >"$subs_auth.tmp")
  mv "$subs_auth.tmp" "$subs_auth"
  unset subs_token
  log "substitutes: the dispatcher's api service token created (digest in hq-api/config; restart the api)"
fi

# ------------------------------------------------------------- backups (p07) --
# The restic repositories' password (local, Google Drive, Hetzner): made once
# and kept; changing it would lock every existing snapshot. The owner keeps a
# paper copy (`make backup-password` shows it in their own terminal only).
# 7.1 §2.9: written with KV check-and-set (cas 0), never over an existing one.
HQ_BAO_ADDR="$BAO_ADDR" "$REPO_DIR/infra/openbao/restic-password.sh" "$WORK/auth" ||
  die "backup: the restic password could not be checked or created"

# ------------------------------------------------- support pseudonym (p10) --
# The customer pseudonym's HMAC key (kv/support/pseudonym): made once with
# KV check-and-set (cas 0), never rotated unless the owner asks; read by the
# api and the worker (policies hq-api, hq-worker).
HQ_BAO_ADDR="$BAO_ADDR" "$REPO_DIR/infra/openbao/kv-once.sh" "$WORK/auth" support/pseudonym key ||
  die "support: the pseudonym key could not be checked or created"
log "done"
