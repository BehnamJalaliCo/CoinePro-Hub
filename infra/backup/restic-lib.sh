#!/usr/bin/env bash
# shellcheck disable=SC2034 # the variables are used by the scripts that source this file
# Shared by hourly.sh, restore-weekly.sh and gdrive-auth.sh (prompt 07 §1).
# Sourced, never run. Nothing here prints a secret: the restic password, the
# Google Drive token and the bucket keys only ever exist in OpenBao and, for
# one run, in a private tmpfs directory ($SEC, 0700, removed on exit) that is
# bind-mounted read-only into the backup container. They never travel in argv
# or in a container's environment (only the file *paths* do).
#
# Inputs (environment):
#   HQ_BACKUP_DIR            backup root (default /home/Hub/backups)
#   HQ_SECRETS_DIR           the host's secret files (default /home/Hub/.secrets)
#   HQ_COMPOSE_CMD           a stand-in for hq.sh (tests)
#   HQ_BACKUP_TEST_SECRETS   tests only: a directory with restic.pass and
#                            rclone.conf used instead of OpenBao
#   HQ_BACKUP_TEST_MOUNT     tests only: one extra "src:dst" mount (a fake remote)

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="${HQ_COMPOSE_CMD:-$REPO_DIR/infra/compose/hq.sh}"
BACKUP_ROOT="${HQ_BACKUP_DIR:-/home/Hub/backups}"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
ENV_FILE="${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}"
# The restic repositories. Local: root-owned, made by `make bootstrap`.
LOCAL_REPO_DIR="$BACKUP_ROOT/restic"
GDRIVE_REPO="rclone:gdrive:CoinePro-HQ/restic"
STATUS_DIR="$BACKUP_ROOT/status"
# Retention of the off-site repositories (prompt 07 §1.2, exactly) and of the
# local one (it only bridges the hours between off-site copies; the WAL
# archive covers the last days minute by minute).
REMOTE_KEEP=(--keep-hourly 168 --keep-daily 90 --keep-weekly 52 --keep-monthly 36 --keep-yearly 10)
LOCAL_KEEP=(--keep-hourly "${HQ_BACKUP_LOCAL_HOURLY:-48}" --keep-daily "${HQ_BACKUP_LOCAL_DAILY:-7}")

blog() { printf '%s %s: %s\n' "$(date -u +%FT%TZ)" "${BLOG_NAME:-backup}" "$*"; }

# write_json FILE < json -- atomically, world-readable (status files hold no secret)
write_json() {
  mkdir -p "$STATUS_DIR" && chmod 755 "$STATUS_DIR"
  cat >"$1.tmp"
  chmod 644 "$1.tmp"
  mv "$1.tmp" "$1"
}

# compose_facts: images and the job's memory limit, from the compose model.
compose_facts() {
  local config
  config="$("$HQ" config --format json)"
  BACKUP_IMAGE="$(jq -r '.services["backup-tools"].image' <<<"$config")"
  BACKUP_MEM="$(jq -r '.services["backup-tools"].deploy.resources.limits.memory' <<<"$config")"
  PG_IMAGE="$(jq -r '.services.postgres.image' <<<"$config")"
  TOOLS_IMAGE="$(jq -r '.services["hq-tools"].image' <<<"$config")"
  FILES_VOLUME="$(jq -r '.volumes["hq-files"].name' <<<"$config")"
}

# ------------------------------------------------------------------ secrets --
SEC=""
GDRIVE_CONFIGURED=false
HETZNER_CONFIGURED=false
SNAPSHOT_TOKEN=false
HETZNER_REPO=""

secrets_cleanup() { if [[ -n "$SEC" ]]; then rm -rf "$SEC"; SEC=""; fi; }

# bao_get PATH TOKEN_HEADER_FILE -> the secret's data object on stdout (or nothing)
bao_get() {
  curl -sS -f -H @"$2" "$BAO_ADDR/v1/kv/data/$1" 2>/dev/null | jq -c '.data.data // empty' 2>/dev/null || true
}

# load_secrets: fills $SEC (tmpfs, 0700) with restic.pass and rclone.conf.
load_secrets() {
  local base="/dev/shm"
  [[ -d "$base" && -w "$base" ]] || base="${TMPDIR:-/tmp}"
  SEC="$(mktemp -d "$base/hq-backup-XXXXXX")"
  chmod 700 "$SEC"
  : >"$SEC/rclone.conf"
  if [[ -n "${HQ_BACKUP_TEST_SECRETS:-}" ]]; then
    cp "$HQ_BACKUP_TEST_SECRETS/restic.pass" "$SEC/restic.pass"
    [[ -s "$HQ_BACKUP_TEST_SECRETS/rclone.conf" ]] && cp "$HQ_BACKUP_TEST_SECRETS/rclone.conf" "$SEC/rclone.conf"
    grep -q '^\[gdrive\]' "$SEC/rclone.conf" && GDRIVE_CONFIGURED=true
    grep -q '^\[hetzner\]' "$SEC/rclone.conf" && HETZNER_CONFIGURED=true
    HETZNER_REPO="rclone:hetzner:test/restic"
    chmod 600 "$SEC"/*
    return 0
  fi
  local creds="$SECRETS_DIR/backup/approle.json" auth="$SEC/auth" token restic gdrive snap
  [[ -s "$creds" ]] || { blog "no OpenBao credentials ($creds): run make up"; return 1; }
  token="$(curl -sS -f -H 'Content-Type: application/json' --data-binary @"$creds" \
    "$BAO_ADDR/v1/auth/approle/login" 2>/dev/null | jq -r '.auth.client_token // empty' 2>/dev/null || true)"
  [[ -n "$token" ]] || { blog "OpenBao login refused or OpenBao sealed"; return 1; }
  printf 'X-Vault-Token: %s\n' "$token" >"$auth"
  unset token
  restic="$(bao_get backup/restic "$auth")"
  jq -j '.password // empty' <<<"$restic" >"$SEC/restic.pass"
  unset restic
  [[ -s "$SEC/restic.pass" ]] || { blog "no restic password in kv/backup/restic: run make up"; return 1; }
  gdrive="$(bao_get backup/gdrive "$auth")"
  if [[ -n "$gdrive" ]] && jq -e '.token | length > 0' <<<"$gdrive" >/dev/null 2>&1; then
    # [gdrive]: Google Drive with scope drive.file (rclone sees only what it made).
    jq -r '"[gdrive]\ntype = drive\nscope = drive.file\ntoken = \(.token)\n" +
      (if (.client_id // "") != "" then "client_id = \(.client_id)\nclient_secret = \(.client_secret // "")\n" else "" end)' \
      <<<"$gdrive" >>"$SEC/rclone.conf"
    GDRIVE_CONFIGURED=true
  fi
  unset gdrive
  snap="$(bao_get backup/openbao-snapshot "$auth")"
  if [[ -n "$snap" ]]; then
    jq -j '.token // empty' <<<"$snap" >"$SEC/snapshot.token"
    [[ -s "$SEC/snapshot.token" ]] && SNAPSHOT_TOKEN=true
  fi
  unset snap
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
    } >>"$SEC/rclone.conf"
    HETZNER_REPO="rclone:hetzner:${s3[HQ_BACKUP_S3_BUCKET]}/${s3[HQ_BACKUP_S3_PREFIX]:-coinepro-hq}/restic"
    HETZNER_CONFIGURED=true
  fi
  chmod 600 "$SEC"/*
}

# --------------------------------------------------------- the container ----
# brestic NETWORK [docker-run-args... --] restic-args...
# restic as root inside a throwaway container: the inputs belong to several
# uids (Postgres' WAL archive 999, the api's files 10001, Hub's dumps), so it
# keeps only the file capabilities (read and write any file, keep owners on a
# restore), no network unless a remote is used, a read-only root filesystem.
brestic() {
  local network="$1"; shift
  local extra=()
  while (($#)) && [[ "$1" != "--" ]]; do extra+=("$1"); shift; done
  [[ "${1:-}" == "--" ]] && shift
  local test_mount=()
  if [[ -n "${HQ_BACKUP_TEST_MOUNT:-}" ]]; then test_mount=(-v "$HQ_BACKUP_TEST_MOUNT"); fi
  docker run --rm --network "$network" --memory "$BACKUP_MEM" --user 0:0 \
    --cap-drop ALL --cap-add DAC_READ_SEARCH --cap-add DAC_OVERRIDE --cap-add CHOWN --cap-add FOWNER \
    --security-opt no-new-privileges:true --read-only --tmpfs /tmp:size=64m \
    -v "$SEC:/run/hq-backup:ro" -v "$LOCAL_REPO_DIR:/restic" "${test_mount[@]}" \
    -e RESTIC_PASSWORD_FILE=/run/hq-backup/restic.pass -e RCLONE_CONFIG=/run/hq-backup/rclone.conf \
    -e RESTIC_CACHE_DIR=/restic/cache -e RESTIC_PROGRESS_FPS=0 \
    "${extra[@]}" "$BACKUP_IMAGE" restic "$@"
}

# repo_ready REPO NETWORK -- initialise a repository that does not exist yet.
repo_ready() {
  local rc=0
  brestic "$2" -- -r "$1" cat config >/dev/null 2>&1 || rc=$?
  if ((rc == 10)); then  # restic: "repository does not exist"
    brestic "$2" -- -r "$1" init >/dev/null
    blog "initialised $1"
  elif ((rc != 0)); then
    return "$rc"
  fi
}
