#!/usr/bin/env bash
# Restores the newest backup into a throwaway Postgres container (same image
# as production, no network) and checks it, then removes the container.
# Checks: SHA256SUMS, every archive restores with --exit-on-error, the table
# count matches the archive's table of contents, hq has `vector`, and the
# Temporal databases carry a schema version. The api's files are restored
# into a throwaway volume and every sha256 is checked (an empty set runs the
# same path on a sample file); the audit-anchor copy must be valid JSONL.
# Prompt 14 §5: one archive record's file (the newest one not destroyed) is
# found among the restored files and its sha256 compared with the one the
# restored database holds (archive.record_files.stored_sha256): a file that
# changed before the backup passes the files' own sums but not this.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="${HQ_COMPOSE_CMD:-$REPO_DIR/infra/compose/hq.sh}"
# Prompt 07 §1.5: the weekly test restores an hourly snapshot and checks it
# here: HQ_RESTORE_SET = that set's directory, HQ_RESTORE_FILES_DIR = the
# restored api files (checked against files.sha256), HQ_RESTORE_STATUS = the
# status file to write (default restore-test).
RESTORE_SET="${HQ_RESTORE_SET:-}"
RESTORE_FILES_DIR="${HQ_RESTORE_FILES_DIR:-}"
STATUS_NAME="${HQ_RESTORE_STATUS:-restore-test}"
BACKUP_ROOT="${HQ_BACKUP_DIR:-/home/Hub/backups}"
# shellcheck source=files.sh
source "$REPO_DIR/infra/backup/files.sh"

log() { printf 'restore-test: %s\n' "$*"; }
started_s="$(date +%s)"
archive_json=null  # {ref, ok} once the archive record is checked (prompt 14 §5)
# The outcome, for the hub's own health (health.hub, prompt 05 §4).
status() { # status OK STAMP
  mkdir -p "$BACKUP_ROOT/status" && chmod 755 "$BACKUP_ROOT/status"
  jq -n --arg at "$(date -u +%FT%TZ)" --argjson ok "$1" --arg stamp "$2" \
    --argjson dur "$(($(date +%s) - started_s))" --argjson archive "$archive_json" \
    '{at: $at, ok: $ok, stamp: $stamp, duration_s: $dur, archive: $archive}' \
    >"$BACKUP_ROOT/status/$STATUS_NAME.json.tmp"
  chmod 644 "$BACKUP_ROOT/status/$STATUS_NAME.json.tmp"
  mv "$BACKUP_ROOT/status/$STATUS_NAME.json.tmp" "$BACKUP_ROOT/status/$STATUS_NAME.json"
}
fail() { printf 'restore-test: FAIL: %s\n' "$*" >&2; status false "${latest:-}"; exit 1; }

if [[ -n "$RESTORE_SET" ]]; then
  latest="$(basename "$RESTORE_SET")"
  dir="$RESTORE_SET"
else
  latest="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended \
    -regex '.*/[0-9]{8}T[0-9]{6}Z' -printf '%f\n' | sort | tail -n1)"
  [[ -n "$latest" ]] || fail "no backup found in $BACKUP_ROOT (run make backup)"
  dir="$BACKUP_ROOT/$latest"
fi
log "backup $latest"

(cd "$dir" && sha256sum --quiet -c SHA256SUMS) || fail "checksum mismatch"
log "checksums ok"

config="$("$HQ" config --format json)"
image="$(jq -r '.services.postgres.image' <<<"$config")"
tools_image="$(jq -r '.services["hq-tools"].image' <<<"$config")"
name="hq-restore-test-$(date -u +%s)"
volumes=()
cleanup() {
  docker rm -fv "$name" >/dev/null 2>&1 || true  # -v: its anonymous data volume too
  for v in "${volumes[@]}"; do docker volume rm -f "$v" >/dev/null 2>&1 || true; done
}
trap cleanup EXIT

# The superuser password only has to exist; it is random and thrown away.
POSTGRES_PASSWORD="$(openssl rand -hex 24)" docker run -d --rm --name "$name" \
  --network none --memory 512m -e POSTGRES_PASSWORD "$image" >/dev/null

# TCP only answers once the entrypoint's init phase has finished.
for _ in $(seq 1 60); do
  docker exec "$name" psql -h 127.0.0.1 -U postgres -Atc 'SELECT 1' >/dev/null 2>&1 && break
  sleep 2
done
docker exec "$name" psql -h 127.0.0.1 -U postgres -Atc 'SELECT 1' >/dev/null 2>&1 ||
  fail "throwaway postgres did not start"

sql() { docker exec "$name" psql -h 127.0.0.1 -U postgres -X -At -v ON_ERROR_STOP=1 "$@"; }

# Roles first: row policies and grants name them (the superuser already exists).
docker exec -i "$name" psql -h 127.0.0.1 -U postgres -X -q -d postgres <"$dir/globals.sql" >/dev/null 2>&1 || true

mapfile -t databases < <(jq -r '.databases[]' "$dir/manifest.json")
for db in "${databases[@]}"; do
  dump="$dir/$db.dump"
  sql -c "CREATE DATABASE \"$db\"" >/dev/null
  docker exec -i "$name" pg_restore -h 127.0.0.1 -U postgres -d "$db" \
    --exit-on-error --no-owner --no-privileges <"$dump" ||
    fail "$db: pg_restore failed"

  # TOC lines: "<id>; <oid> <oid> TABLE <schema> <name> <owner>" (TABLE DATA and
  # TABLE ATTACH, one per partition of a partitioned table, excluded).
  expected="$(docker exec -i "$name" pg_restore --list <"$dump" |
    awk '$4 == "TABLE" && $5 != "DATA" && $5 != "ATTACH"' | wc -l)"
  restored="$(sql -d "$db" -c "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")"
  [[ "$expected" == "$restored" ]] || fail "$db: $restored tables restored, archive lists $expected"
  details="tables=$restored"

  if [[ "$db" == "hq" ]]; then
    [[ "$(sql -d hq -c "SELECT count(*) FROM pg_extension WHERE extname = 'vector'")" == "1" ]] ||
      fail "hq: extension vector missing"
    details+=" vector=ok"
  fi
  if [[ "$db" == temporal* ]]; then
    version="$(sql -d "$db" -c 'SELECT curr_version FROM schema_version')"
    [[ -n "$version" ]] || fail "$db: no schema version"
    details+=" schema=$version"
  fi
  log "$db ok ($details)"
done

# The api's files: restore into a throwaway volume and check every sha256.
files_vol="hq-restore-files-$(date -u +%s)"
docker volume create "$files_vol" >/dev/null
volumes+=("$files_vol")
if [[ -n "$RESTORE_FILES_DIR" && -s "$dir/files.sha256" ]]; then
  # An hourly snapshot keeps the files themselves (restic deduplicates them).
  docker run --rm -i --network none -v "$RESTORE_FILES_DIR:/data:ro" "$tools_image" \
    sh -c 'cd /data && sha256sum -c -s -' <"$dir/files.sha256" ||
    fail "files: a restored file does not match its sha256"
  log "files ok ($(wc -l <"$dir/files.sha256") file(s), every sha256 verified)"
elif [[ -s "$dir/files.sha256" ]]; then
  files_restore_verify "$dir/files.tar.gz" "$dir/files.sha256" "$files_vol" "$tools_image" ||
    fail "files: a restored file does not match its sha256"
  log "files ok ($(wc -l <"$dir/files.sha256") file(s), every sha256 verified)"
else
  # Nothing stored yet: prove the same path on a sample file.
  src_vol="hq-restore-sample-$(date -u +%s)"
  docker volume create "$src_vol" >/dev/null
  volumes+=("$src_vol")
  docker run --rm --network none -v "$src_vol:/data" "$tools_image" \
    sh -c 'mkdir -p /data/ab && head -c 4096 /dev/urandom >/data/ab/abcdef0123456789' >/dev/null
  tmp="$(mktemp -d)"
  files_archive "$src_vol" "$tools_image" "$tmp/files.tar.gz" "$tmp/files.sha256"
  files_restore_verify "$tmp/files.tar.gz" "$tmp/files.sha256" "$files_vol" "$tools_image" ||
    { rm -rf "$tmp"; fail "files: sample did not survive archive and restore"; }
  rm -rf "$tmp"
  log "files ok (no files in this set; the archive/restore path passed on a sample file)"
fi

# Prompt 14 §5: one archive record restored and its hash checked. The newest
# file of the archive that was not destroyed (disposal removes the bytes and
# keeps the tombstone); a backup older than the archive has none to check.
archive_ref=none
if [[ "$(sql -d hq -c "SELECT to_regclass('archive.record_files') IS NOT NULL")" == t ]]; then
  row="$(sql -d hq -F ' ' -c "SELECT r.ref, f.storage_key, f.stored_sha256 FROM archive.record_files f
    JOIN archive.records r ON r.id = f.record_id WHERE f.destroyed_at IS NULL AND f.storage_key IS NOT NULL
    ORDER BY f.created_at DESC LIMIT 1")"
  if [[ -n "$row" ]]; then
    read -r archive_ref key want <<<"$row"
    archive_json="$(jq -n --arg r "$archive_ref" '{ref: $r, ok: false}')"
    # The file store's own layout (LocalStorage): <root>/<key[:2]>/<key>.
    [[ "$key" =~ ^[0-9a-f]{32}$ && "$want" =~ ^[0-9a-f]{64}$ ]] ||
      fail "archive: $archive_ref: the restored database names no valid file key or sha256"
    if [[ -n "$RESTORE_FILES_DIR" ]]; then src=(-v "$RESTORE_FILES_DIR:/data:ro"); else src=(-v "$files_vol:/data:ro"); fi
    got="$(docker run --rm --network none "${src[@]}" "$tools_image" \
      sh -c 'sha256sum "/data/$1" 2>/dev/null | cut -d" " -f1' sh "${key:0:2}/$key")"
    [[ -n "$got" ]] || fail "archive: $archive_ref: its file is not among the restored files"
    [[ "$got" == "$want" ]] || fail "archive: $archive_ref: the restored file does not match its sha256"
    archive_json="$(jq -n --arg r "$archive_ref" '{ref: $r, ok: true}')"
    log "archive ok ($archive_ref, its file's sha256 verified)"
  else
    log "archive: no record yet"
  fi
else
  log "archive: no archive in this backup"
fi

if [[ -s "$dir/audit-chain.jsonl" ]]; then
  jq -e -s 'all(.[]; has("seq") and has("hash"))' "$dir/audit-chain.jsonl" >/dev/null ||
    fail "audit anchors: not valid JSONL with seq and hash"
  log "audit anchors ok ($(wc -l <"$dir/audit-chain.jsonl") line(s))"
fi

log "PASS ($latest, ${#databases[@]} databases, archive=$archive_ref); throwaway container and volumes removed"
status true "$latest"
