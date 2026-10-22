#!/usr/bin/env bash
# shellcheck disable=SC2034 # the variables are used by the scripts that source this file
# Shared by hourly.sh, restore-weekly.sh and gdrive-auth.sh (prompt 07 §1).
# Sourced, never run. Nothing here prints a secret: the restic password, the
# Google Drive token and the bucket keys only ever exist in OpenBao and, for
# one run, in a private directory ($SEC, 0700, removed on exit) on a tmpfs:
# the unit's own RuntimeDirectory= (systemd removes it when the run ends),
# else the user's runtime directory. Only two sub-directories of it are
# bind-mounted into the backup container: c/ (the restic password, read-only)
# and rclone/ (rclone's config, writable so a refreshed Drive token is kept
# for the run's next calls). Secrets never travel in argv or in a container's
# environment (only the file *paths* do), and reach jq on stdin only.
#
# Inputs (environment):
#   HQ_BACKUP_DIR            backup root (default /home/Hub/backups)
#   HQ_SECRETS_DIR           the host's secret files (default /home/Hub/.secrets)
#   HQ_BAO_ADDR              OpenBao (default http://127.0.0.1:8200)
#   HQ_COMPOSE_CMD           a stand-in for hq.sh (tests)
#   HQ_TEXTFILE_DIR          node-exporter's textfile directory (default /var/lib/coinepro-hq/textfile)
#   RUNTIME_DIRECTORY        set by systemd (RuntimeDirectory= of the unit)
#   HQ_BACKUP_TEST_GDRIVE    tests only: a file with the [gdrive] backend lines used
#                            instead of Google Drive's own (the token must still be in
#                            OpenBao: the whole OpenBao path runs, nothing is bypassed)
#   HQ_BACKUP_TEST_MOUNT     tests only: one extra "src:dst" mount (a fake remote)

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="${HQ_COMPOSE_CMD:-$REPO_DIR/infra/compose/hq.sh}"
BACKUP_ROOT="${HQ_BACKUP_DIR:-/home/Hub/backups}"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
ENV_FILE="${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}"
TEXTFILE_DIR="${HQ_TEXTFILE_DIR:-/var/lib/coinepro-hq/textfile}"
# The restic repositories. Local: root-owned, made by `make bootstrap`.
LOCAL_REPO_DIR="$BACKUP_ROOT/restic"
GDRIVE_REPO="rclone:gdrive:CoinePro-HQ/restic"
STATUS_DIR="$BACKUP_ROOT/status"
# hourly.sh's memory (what was done when); restore-weekly.sh reads it too.
HOURLY_STATE="$BACKUP_ROOT/hourly/state.json"
# Retention of the off-site repositories (prompt 07 §1.2, exactly) and of the
# local one (it only bridges the hours between off-site copies; the WAL
# archive covers the last days minute by minute).
REMOTE_KEEP=(--keep-hourly 168 --keep-daily 90 --keep-weekly 52 --keep-monthly 36 --keep-yearly 10)
LOCAL_KEEP=(--keep-hourly "${HQ_BACKUP_LOCAL_HOURLY:-48}" --keep-daily "${HQ_BACKUP_LOCAL_DAILY:-7}")
# 7.1 §2.5: the restore path waits for a lock (an hourly forget or prune) instead of failing.
RETRY_LOCK=(--retry-lock "${HQ_RESTIC_RETRY_LOCK:-30m}")
# 7.1 §3: the capabilities a restore needs on top (write anywhere, keep owners
# and modes). Every other call only reads (DAC_READ_SEARCH).
RESTORE_CAPS=(--cap-add DAC_OVERRIDE --cap-add CHOWN --cap-add FOWNER)

blog() { printf '%s %s: %s\n' "$(date -u +%FT%TZ)" "${BLOG_NAME:-backup}" "$*"; }

# write_json FILE < json -- atomically, world-readable (status files hold no secret)
write_json() {
  mkdir -p "$STATUS_DIR" && chmod 755 "$STATUS_DIR"
  cat >"$1.tmp"
  chmod 644 "$1.tmp"
  mv "$1.tmp" "$1"
}

# day_due LAST [NOW] -- "once a day" by the calendar day (UTC), 7.1 §2.6: true
# when LAST is empty, unreadable or on another UTC day than NOW (default: now).
# A rule of "more than 23 hours ago" drifted later every day and let the base
# backups (and so PITR) fall short of 7 days.
day_due() {
  local last today
  [[ -n "${1:-}" ]] || return 0
  last="$(date -u -d "$1" +%F 2>/dev/null)" || return 0
  today="$(date -u -d "${2:-now}" +%F)"
  [[ "$last" != "$today" ]]
}

# compose_facts: images and the job's memory limit, from the compose model.
# backup-tools has its own compose profile (nothing in the stack depends on it).
compose_facts() {
  local config
  config="$("$HQ" --profile backup-tools config --format json)"
  BACKUP_IMAGE="$(jq -r '.services["backup-tools"].image' <<<"$config")"
  BACKUP_MEM="$(jq -r '.services["backup-tools"].deploy.resources.limits.memory' <<<"$config")"
  PG_IMAGE="$(jq -r '.services.postgres.image' <<<"$config")"
  TOOLS_IMAGE="$(jq -r '.services["hq-tools"].image' <<<"$config")"
  FILES_VOLUME="$(jq -r '.volumes["hq-files"].name' <<<"$config")"
}

# ------------------------------------------------------------------ secrets --
SEC=""
CSEC=""
RCLONE_DIR=""
LOAD_ERROR=""
GDRIVE_CONFIGURED=false
GDRIVE_ERROR=""
HETZNER_CONFIGURED=false
SNAPSHOT_TOKEN=false
SNAPSHOT_ERROR=""
HETZNER_REPO=""

secrets_cleanup() { if [[ -n "$SEC" ]]; then rm -rf "$SEC"; SEC=""; fi; }

# Google Drive was connected once (hourly.sh records it): its disappearance
# from OpenBao is an error, never a quiet fall-back to local only (7.1 §2.3).
gdrive_remembered() { [[ -n "$(jq -r '.gdrive_configured_at // empty' "$HOURLY_STATE" 2>/dev/null)" ]]; }

# secret_base: a tmpfs only this user (or this unit) can enter.
secret_base() {
  local d rd="${RUNTIME_DIRECTORY:-}"
  for d in "${rd%%:*}" "${XDG_RUNTIME_DIR:-}" /dev/shm; do
    if [[ -n "$d" && -d "$d" && -w "$d" ]]; then printf '%s\n' "$d"; return; fi
  done
  printf '%s\n' "${TMPDIR:-/tmp}"
}

# bao_get PATH AUTH_FILE -> 0 found (the data object in BAO_DATA),
# 1 absent (HTTP 404, and only that), 2 any other answer (BAO_ERR says which).
# A sealed, restarting or refusing OpenBao is never "not configured" (7.1 §2.3).
bao_get() {
  local out code
  BAO_DATA="" BAO_ERR=""
  out="$(curl -sS -H @"$2" -w '\n%{http_code}' "$BAO_ADDR/v1/kv/data/$1" 2>/dev/null)" || true
  code="${out##*$'\n'}"
  case "$code" in
    200)
      BAO_DATA="$(jq -c '.data.data // empty' <<<"${out%$'\n'*}" 2>/dev/null || true)"
      [[ -n "$BAO_DATA" ]] && return 0
      BAO_ERR="OpenBao gave an unreadable answer for kv/$1"
      return 2
      ;;
    404) return 1 ;;
    *)
      BAO_ERR="OpenBao answered HTTP ${code:-000} for kv/$1"
      return 2
      ;;
  esac
}

# load_secrets: fills $SEC with c/restic.pass, rclone/rclone.conf and the
# snapshot token. Fails (LOAD_ERROR) without a login or a restic password; a
# Drive or snapshot entry that cannot be read sets GDRIVE_ERROR / SNAPSHOT_ERROR.
load_secrets() {
  local creds="$SECRETS_DIR/backup/approle.json" auth token rc
  SEC="$(mktemp -d "$(secret_base)/hq-backup-XXXXXX")"
  chmod 700 "$SEC"
  CSEC="$SEC/c"
  RCLONE_DIR="$SEC/rclone"
  mkdir -m 700 "$CSEC"
  # Inside the private $SEC: the backup container's root writes the refreshed
  # token here without DAC_OVERRIDE (7.1 §3); the file itself stays 0600.
  mkdir "$RCLONE_DIR"
  chmod 777 "$RCLONE_DIR"
  : >"$RCLONE_DIR/rclone.conf"
  auth="$SEC/auth"
  [[ -s "$creds" ]] || { LOAD_ERROR="no OpenBao credentials ($creds): run make up"; return 1; }
  token="$(curl -sS -f -H 'Content-Type: application/json' --data-binary @"$creds" \
    "$BAO_ADDR/v1/auth/approle/login" 2>/dev/null | jq -r '.auth.client_token // empty' 2>/dev/null || true)"
  [[ -n "$token" ]] || { LOAD_ERROR="OpenBao login refused or OpenBao sealed"; return 1; }
  printf 'X-Vault-Token: %s\n' "$token" >"$auth"
  unset token

  rc=0
  bao_get backup/restic "$auth" || rc=$?
  if ((rc == 2)); then LOAD_ERROR="$BAO_ERR"; rm -f "$auth"; return 1; fi
  if ((rc == 0)); then jq -j '.password // empty' <<<"$BAO_DATA" >"$CSEC/restic.pass"; fi
  BAO_DATA=""
  [[ -s "$CSEC/restic.pass" ]] || { LOAD_ERROR="no restic password in kv/backup/restic: run make up"; rm -f "$auth"; return 1; }

  rc=0
  bao_get backup/gdrive "$auth" || rc=$?
  if ((rc == 0)) && jq -e '.token | length > 0' <<<"$BAO_DATA" >/dev/null 2>&1; then
    if [[ -n "${HQ_BACKUP_TEST_GDRIVE:-}" ]]; then
      { echo '[gdrive]'; cat "$HQ_BACKUP_TEST_GDRIVE"; } >>"$RCLONE_DIR/rclone.conf"
    else
      # [gdrive]: Google Drive with scope drive.file (rclone sees only what it made).
      jq -r '"[gdrive]\ntype = drive\nscope = drive.file\ntoken = \(.token)\n" +
        (if (.client_id // "") != "" then "client_id = \(.client_id)\nclient_secret = \(.client_secret // "")\n" else "" end)' \
        <<<"$BAO_DATA" >>"$RCLONE_DIR/rclone.conf"
    fi
    GDRIVE_CONFIGURED=true
  elif ((rc == 2)); then
    GDRIVE_CONFIGURED=true
    GDRIVE_ERROR="$BAO_ERR"
  else
    GDRIVE_CONFIGURED=false
  fi
  BAO_DATA=""

  rc=0
  bao_get backup/openbao-snapshot "$auth" || rc=$?
  if ((rc == 0)); then
    jq -j '.token // empty' <<<"$BAO_DATA" >"$SEC/snapshot.token"
    [[ -s "$SEC/snapshot.token" ]] && SNAPSHOT_TOKEN=true
  elif ((rc == 2)); then
    SNAPSHOT_ERROR="$BAO_ERR"
  fi
  BAO_DATA=""
  rm -f "$auth"
  # Optional second destination (prompt 07 §1.4): Hetzner Object Storage as a
  # restic repository, on with HQ_BACKUP_S3_ENABLED=true in .env. Only those
  # lines are read; the file is not sourced.
  local key value
  declare -A s3=()
  if [[ -r "$ENV_FILE" ]]; then
    while IFS='=' read -r key value; do
      [[ "$key" =~ ^HQ_BACKUP_S3_[A-Z_]+$ ]] && s3[$key]="$value"
    done <"$ENV_FILE"
  fi
  if [[ "${s3[HQ_BACKUP_S3_ENABLED]:-}" == true && -n "${s3[HQ_BACKUP_S3_BUCKET]:-}" ]]; then
    {
      printf '[hetzner]\ntype = s3\nprovider = Other\nno_check_bucket = true\n'
      printf 'endpoint = %s\nregion = %s\n' "${s3[HQ_BACKUP_S3_ENDPOINT]:-}" "${s3[HQ_BACKUP_S3_REGION]:-}"
      printf 'access_key_id = %s\nsecret_access_key = %s\n' \
        "${s3[HQ_BACKUP_S3_ACCESS_KEY_ID]:-}" "${s3[HQ_BACKUP_S3_SECRET_ACCESS_KEY]:-}"
    } >>"$RCLONE_DIR/rclone.conf"
    HETZNER_REPO="rclone:hetzner:${s3[HQ_BACKUP_S3_BUCKET]}/${s3[HQ_BACKUP_S3_PREFIX]:-coinepro-hq}/restic"
    HETZNER_CONFIGURED=true
  fi
  chmod 600 "$CSEC"/* "$RCLONE_DIR/rclone.conf"
  if [[ -e "$SEC/snapshot.token" ]]; then chmod 600 "$SEC/snapshot.token"; fi
}

# gdrive_authorize_blob < "client_id\0client_secret" -> the argument of
# `rclone authorize "drive" <blob>` for the owner's own OAuth client: base64
# without padding of {"client_id", "client_secret", "scope": "drive.file"}
# (7.1 §2.8). The two-argument form of rclone authorize asks for full Drive
# access; this one keeps drive.file. Read from stdin, never from argv.
gdrive_authorize_blob() {
  jq -Rsjc 'split("\u0000") | {client_id: .[0], client_secret: (.[1] // ""), scope: "drive.file"}' |
    base64 -w0 | tr -d '='
}

# --------------------------------------------------------- the container ----
# brestic NETWORK [docker-run-args... --] restic-args...
# restic as root inside a throwaway container: the inputs belong to several
# uids (Postgres' WAL archive 999, the api's files 10001, Hub's dumps), so it
# keeps only DAC_READ_SEARCH (read any file); a restore adds RESTORE_CAPS.
# No network unless a remote is used, a read-only root filesystem.
brestic() {
  local network="$1"; shift
  local extra=()
  while (($#)) && [[ "$1" != "--" ]]; do extra+=("$1"); shift; done
  [[ "${1:-}" == "--" ]] && shift
  local test_mount=()
  if [[ -n "${HQ_BACKUP_TEST_MOUNT:-}" ]]; then test_mount=(-v "$HQ_BACKUP_TEST_MOUNT"); fi
  docker run --rm --network "$network" --memory "$BACKUP_MEM" --user 0:0 \
    --cap-drop ALL --cap-add DAC_READ_SEARCH \
    --security-opt no-new-privileges:true --read-only --tmpfs /tmp:size=64m \
    -v "$CSEC:/run/hq-backup:ro" -v "$RCLONE_DIR:/run/hq-rclone" -v "$LOCAL_REPO_DIR:/restic" "${test_mount[@]}" \
    -e RESTIC_PASSWORD_FILE=/run/hq-backup/restic.pass -e RCLONE_CONFIG=/run/hq-rclone/rclone.conf \
    -e RESTIC_CACHE_DIR=/restic/cache -e RESTIC_PROGRESS_FPS=0 \
    "${extra[@]}" "$BACKUP_IMAGE" restic "$@"
}

# brclone NETWORK rclone-args... -- rclone alone (Drive's quota, the folder check).
brclone() {
  local network="$1"; shift
  local test_mount=()
  if [[ -n "${HQ_BACKUP_TEST_MOUNT:-}" ]]; then test_mount=(-v "$HQ_BACKUP_TEST_MOUNT"); fi
  docker run --rm --network "$network" --memory "$BACKUP_MEM" --user 0:0 \
    --cap-drop ALL --cap-add DAC_READ_SEARCH \
    --security-opt no-new-privileges:true --read-only --tmpfs /tmp:size=16m \
    -v "$RCLONE_DIR:/run/hq-rclone" "${test_mount[@]}" \
    -e RCLONE_CONFIG=/run/hq-rclone/rclone.conf -e RCLONE_CACHE_DIR=/tmp/rclone \
    "$BACKUP_IMAGE" rclone "$@"
}

# repo_ready REPO NETWORK -- initialise a repository that does not exist yet.
# (Called inside `if !`, where set -e does not stop: every failure returns.)
repo_ready() {
  local rc=0
  brestic "$2" -- -r "$1" cat config >/dev/null 2>&1 || rc=$?
  if ((rc == 10)); then  # restic: "repository does not exist"
    brestic "$2" -- -r "$1" init >/dev/null || return
    blog "initialised $1"
  elif ((rc != 0)); then
    return "$rc"
  fi
}
