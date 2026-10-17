#!/usr/bin/env bash
# Restores the newest backup into a throwaway Postgres container (same image
# as production, no network) and checks it, then removes the container.
# Checks: SHA256SUMS, every archive restores with --exit-on-error, the table
# count matches the archive's table of contents, hq has `vector`, and the
# Temporal databases carry a schema version. The api's files are restored
# into a throwaway volume and every sha256 is checked (an empty set runs the
# same path on a sample file); the audit-anchor copy must be valid JSONL.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
BACKUP_ROOT="${HQ_BACKUP_DIR:-/home/Hub/backups}"
# shellcheck source=files.sh
source "$REPO_DIR/infra/backup/files.sh"

log() { printf 'restore-test: %s\n' "$*"; }
started_s="$(date +%s)"
# The outcome, for the hub's own health (health.hub, prompt 05 §4).
status() { # status OK STAMP
  mkdir -p "$BACKUP_ROOT/status" && chmod 755 "$BACKUP_ROOT/status"
  jq -n --arg at "$(date -u +%FT%TZ)" --argjson ok "$1" --arg stamp "$2" \
    --argjson dur "$(($(date +%s) - started_s))" \
    '{at: $at, ok: $ok, stamp: $stamp, duration_s: $dur}' >"$BACKUP_ROOT/status/restore-test.json.tmp"
  chmod 644 "$BACKUP_ROOT/status/restore-test.json.tmp"
  mv "$BACKUP_ROOT/status/restore-test.json.tmp" "$BACKUP_ROOT/status/restore-test.json"
}
fail() { printf 'restore-test: FAIL: %s\n' "$*" >&2; status false "${latest:-}"; exit 1; }

latest="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended \
  -regex '.*/[0-9]{8}T[0-9]{6}Z' -printf '%f\n' | sort | tail -n1)"
[[ -n "$latest" ]] || fail "no backup found in $BACKUP_ROOT (run make backup)"
dir="$BACKUP_ROOT/$latest"
log "backup $latest"

(cd "$dir" && sha256sum --quiet -c SHA256SUMS) || fail "checksum mismatch"
log "checksums ok"

config="$("$HQ" config --format json)"
image="$(jq -r '.services.postgres.image' <<<"$config")"
tools_image="$(jq -r '.services["hq-tools"].image' <<<"$config")"
name="hq-restore-test-$(date -u +%s)"
volumes=()
cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
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
if [[ -s "$dir/files.sha256" ]]; then
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

if [[ -s "$dir/audit-chain.jsonl" ]]; then
  jq -e -s 'all(.[]; has("seq") and has("hash"))' "$dir/audit-chain.jsonl" >/dev/null ||
    fail "audit anchors: not valid JSONL with seq and hash"
  log "audit anchors ok ($(wc -l <"$dir/audit-chain.jsonl") line(s))"
fi

log "PASS ($latest, ${#databases[@]} databases); throwaway container and volumes removed"
status true "$latest"
