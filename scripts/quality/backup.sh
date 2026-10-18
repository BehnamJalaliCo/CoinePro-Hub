#!/usr/bin/env bash
# The backup gate (prompt 07 §1), on throwaway containers, volumes and a temp
# directory only (never the coinepro-hq stack, its volumes or the host's
# secrets); a stand-in for hq.sh points the scripts at a throwaway Postgres
# with WAL-G archiving, and a local rclone remote stands in for Google Drive:
#   hourly     the hourly run makes a snapshot locally and on the "Drive"
#   encrypted  the repository holds no plaintext and does not open without
#              the password (none, or a wrong one)
#   check      restic check passed in that run; the snapshot list is written
#   secrets    the password never appears in docker's argv, the output or the
#              status files (it travels as a file only)
#   pitr       point-in-time recovery to a moment between two inserts returns
#              exactly the first one
#   down       an unreachable destination fails the run: ok:false, the
#              destination's error in status/hourly.json (the worker alerts)
#   weekly     the weekly restore test: restore from the "Drive", every
#              database check, the files' sha256 and a PITR, ok:true
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

N="hq-bk-$$"
T="$(mktemp -d)"
PG_IMAGE_T="coinepro-hq/postgres:gate"
BK_IMAGE_T="coinepro-hq/backup:gate"
TOOLS="busybox:1.38.0-musl"
failed=0
pass() { echo "backup: ok   $*"; }
fail() { echo "backup: FAIL $*" >&2; failed=1; }
# shellcheck disable=SC2329 # invoked by the EXIT trap below
cleanup() {
  docker rm -f "$N-pg" >/dev/null 2>&1 || true
  docker volume rm -f "$N-files" >/dev/null 2>&1 || true
  # Root-, postgres- and api-owned leftovers go through a container.
  docker run --rm -v "$T:/t" "$TOOLS" sh -c 'rm -rf /t/* /t/.[!.]*' >/dev/null 2>&1 || true
  rm -rf "$T"
}
trap cleanup EXIT

docker build -q -t "$PG_IMAGE_T" "$REPO_DIR/infra/postgres" >/dev/null
docker build -q -t "$BK_IMAGE_T" "$REPO_DIR/infra/backup" >/dev/null

# ---------------------------------------------------------------- set-up ----
B="$T/backups"
mkdir -p "$B/status" "$T/sec" "$T/bin" "$T/dest"
chmod 700 "$B"
docker run --rm -v "$B:/b" "$TOOLS" sh -c '
  mkdir -p /b/wal /b/restic /b/audit-anchors &&
  chown 999:999 /b/wal && chmod 700 /b/wal && chmod 700 /b/restic &&
  echo "{\"seq\": 1, \"hash\": \"ab\"}" >/b/audit-anchors/audit-chain.jsonl'
password="gate-$(openssl rand -hex 16)"
printf '%s' "$password" >"$T/sec/restic.pass"
printf '[gdrive]\ntype = alias\nremote = /dest\n' >"$T/sec/rclone.conf"
docker volume create "$N-files" >/dev/null
marker_file="file-marker-$(openssl rand -hex 8)"
docker run --rm -v "$N-files:/d" "$TOOLS" sh -c "mkdir -p /d/ab && echo $marker_file >/d/ab/f1 && chown -R 10001 /d"

docker run -d --name "$N-pg" --network none -e POSTGRES_PASSWORD="$(openssl rand -hex 12)" \
  -e WALG_FILE_PREFIX=/wal -e WALG_COMPRESSION_METHOD=zstd -v "$B/wal:/wal" "$PG_IMAGE_T" postgres \
  -c archive_mode=on -c 'archive_command=/usr/local/bin/wal-g wal-push %p' -c archive_timeout=60s >/dev/null
for _ in $(seq 1 60); do
  docker exec "$N-pg" psql -h 127.0.0.1 -U postgres -Atc 'SELECT 1' >/dev/null 2>&1 && break
  sleep 1
done
sql() { docker exec "$N-pg" psql -U postgres -X -At -v ON_ERROR_STOP=1 "$@"; }
marker_db="db-marker-$(openssl rand -hex 8)"
sql -c "CREATE DATABASE hq" >/dev/null
sql -d hq -c "CREATE EXTENSION vector" >/dev/null
sql -d hq -c "CREATE TABLE t (v text)" >/dev/null
sql -d hq -c "INSERT INTO t VALUES ('$marker_db')" >/dev/null

# The stand-in for hq.sh: config = this test's images and volume; exec = the throwaway Postgres.
jq -n --arg pg "$PG_IMAGE_T" --arg bk "$BK_IMAGE_T" --arg tools "$TOOLS" --arg files "$N-files" '{
  services: {postgres: {image: $pg}, "hq-tools": {image: $tools},
             "backup-tools": {image: $bk, deploy: {resources: {limits: {memory: "402653184"}}}}},
  volumes: {"hq-files": {name: $files}}}' >"$T/config.json"
cat >"$T/bin/hq" <<EOF
#!/usr/bin/env bash
set -euo pipefail
case "\$1" in
  config) cat "$T/config.json" ;;
  exec)
    shift; args=()
    while [[ "\$1" == -* ]]; do
      case "\$1" in -T) shift ;; -u|-e) args+=("\$1" "\$2"); shift 2 ;; *) shift ;; esac
    done
    shift  # the service name
    exec docker exec -i "\${args[@]}" "$N-pg" "\$@" ;;
  *) echo "hq stand-in: \$*" >&2; exit 1 ;;
esac
EOF
# docker, logged: every argv the scripts give it, for the secret scan.
real_docker="$(command -v docker)"
cat >"$T/bin/docker" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$T/docker-argv.log"
exec "$real_docker" "\$@"
EOF
chmod +x "$T/bin/hq" "$T/bin/docker"
run_env=(env PATH="$T/bin:$PATH" HQ_COMPOSE_CMD="$T/bin/hq" HQ_BACKUP_DIR="$B" HQ_BACKUP_TEST_SECRETS="$T/sec"
  HQ_ENV_FILE=/dev/null)

# ---------------------------------------------------------------- hourly ----
if out="$("${run_env[@]}" HQ_BACKUP_TEST_MOUNT="$T/dest:/dest" "$REPO_DIR/infra/backup/hourly.sh" 2>&1)"; then
  st="$B/status/hourly.json"
  if [[ "$(jq -r '.ok' "$st")" == true &&
    "$(jq -r '[.destinations[] | select(.ok == true) | .key] | sort | join(",")' "$st")" == gdrive,local &&
    -n "$(jq -r '.snapshot // empty' "$st")" && "$(jq -r '.base_backup.count' "$st")" -ge 1 ]]; then
    pass "hourly: snapshot $(jq -r '.snapshot[0:8]' "$st") in local and the Drive stand-in, a base backup made"
  else
    fail "hourly: status $(jq -c '{ok, error, destinations: [.destinations[] | {key, ok, error}]}' "$st")"
  fi
else
  fail "hourly: exit non-zero: $(tail -n3 <<<"$out")"
fi

# ------------------------------------------------------------- encrypted ----
plain="$(docker run --rm -v "$T/dest:/d:ro" -v "$B/restic:/r:ro" "$TOOLS" \
  sh -c "grep -rl -e '$marker_db' -e '$marker_file' /d /r 2>/dev/null | wc -l")"
nopass="$(docker run --rm --network none -v "$T/dest:/d:ro" "$BK_IMAGE_T" \
  restic -r /d/CoinePro-HQ/restic --insecure-no-password cat config >/dev/null 2>&1 && echo opened || echo refused)"
wrong="$(docker run --rm --network none -v "$T/dest:/d:ro" -e RESTIC_PASSWORD=wrong-password "$BK_IMAGE_T" \
  restic -r /d/CoinePro-HQ/restic cat config >/dev/null 2>&1 && echo opened || echo refused)"
if [[ "$plain" == 0 && "$nopass" == refused && "$wrong" == refused &&
  -d "$T/dest/CoinePro-HQ/restic" ]]; then
  pass "encrypted: no plaintext in either repository; no password and a wrong one are refused"
else
  fail "encrypted: plaintext files=$plain, no password=$nopass, wrong password=$wrong"
fi

# ----------------------------------------------------------------- check ----
if [[ "$(jq -r '.check.ok' "$B/status/hourly.json")" == true &&
  "$(jq '[.items[] | .destination] | unique | length' "$B/status/snapshots.json")" == 2 ]]; then
  pass "check: restic check --read-data-subset 5% passed; snapshots listed for both repositories"
else
  fail "check: check=$(jq -c .check "$B/status/hourly.json") snapshots=$(jq -c '[.items[].destination]' "$B/status/snapshots.json")"
fi

# --------------------------------------------------------------- secrets ----
leaks=0
for f in "$T/docker-argv.log" "$B/status/hourly.json" "$B/status/snapshots.json"; do
  if grep -qF "$password" "$f"; then leaks=$((leaks + 1)); fi
done
if grep -qF "$password" <<<"$out"; then leaks=$((leaks + 1)); fi
if grep -q 'RESTIC_PASSWORD=' "$T/docker-argv.log"; then leaks=$((leaks + 1)); fi
if ((leaks == 0)) && grep -q 'RESTIC_PASSWORD_FILE=' "$T/docker-argv.log"; then
  pass "secrets: the password is only a file (never in argv, env, output or status)"
else
  fail "secrets: the password leaked in $leaks place(s)"
fi

# ------------------------------------------------------------------ pitr ----
sql -d hq -c "INSERT INTO t VALUES ('before')" >/dev/null
sleep 2
target="$(sql -c "SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS.US')") UTC"
sleep 2
sql -d hq -c "INSERT INTO t VALUES ('after')" >/dev/null
sql -c "SELECT pg_switch_wal()" >/dev/null
for _ in $(seq 1 30); do
  [[ "$(sql -c "SELECT last_archived_wal >= pg_walfile_name(pg_current_wal_lsn() - 1) FROM pg_stat_archiver")" == t ]] && break
  sleep 1
done
res="$("${run_env[@]}" "$REPO_DIR/infra/backup/pitr.sh" "$target" --prefix "$B/wal" --image "$PG_IMAGE_T" \
  --db hq --sql "SELECT string_agg(v, ',' ORDER BY v) FROM t WHERE v IN ('before', 'after')" 2>&1 || true)"
if [[ "$(jq -r '.ok' <<<"$res" 2>/dev/null)" == true && "$(jq -r '.value' <<<"$res")" == before ]]; then
  pass "pitr: recovery to $target has 'before' and not 'after' (base $(jq -r .base_backup <<<"$res"))"
else
  fail "pitr: $res"
fi

# ------------------------------------------------------------------ down ----
if "${run_env[@]}" HQ_BACKUP_TEST_MOUNT="$T/nowhere:/dest:ro" "$REPO_DIR/infra/backup/hourly.sh" >/dev/null 2>&1; then
  fail "down: succeeded with the destination unreachable"
else
  st="$B/status/hourly.json"
  if [[ "$(jq -r '.ok' "$st")" == false &&
    "$(jq -r '.destinations[] | select(.key == "gdrive") | .ok' "$st")" == false &&
    "$(jq -r '.destinations[] | select(.key == "local") | .ok' "$st")" == true &&
    "$(jq -r '.last_ok_at' "$st")" != null ]]; then
    pass "down: ok:false, gdrive $(jq -r '.destinations[] | select(.key == "gdrive") | .error' "$st"), local still ok"
  else
    fail "down: status $(jq -c '{ok, error, last_ok_at, destinations}' "$st")"
  fi
fi

# ---------------------------------------------------------------- weekly ----
"${run_env[@]}" HQ_BACKUP_TEST_MOUNT="$T/dest:/dest" "$REPO_DIR/infra/backup/hourly.sh" >/dev/null 2>&1 || true
if out="$("${run_env[@]}" HQ_BACKUP_TEST_MOUNT="$T/dest:/dest" HQ_PITR_AFTER_BASE_S=1 HQ_PITR_BEFORE_SNAPSHOT_S=1 \
  HQ_PITR_TARGET="$target" "$REPO_DIR/infra/backup/restore-weekly.sh" 2>&1)"; then
  w="$B/status/restore-weekly.json"
  if [[ "$(jq -r '.ok' "$w")" == true && "$(jq -r '.source' "$w")" == gdrive &&
    "$(jq -r '.pitr.ok' "$w")" == true ]]; then
    pass "weekly: restored from the Drive stand-in; databases, files and PITR ($(jq -r .pitr.target "$w")) ok"
  else
    fail "weekly: $(jq -c . "$w")"
  fi
else
  fail "weekly: exit non-zero: $(tail -n4 <<<"$out")"
fi

# ------------------------------------------------------------------- wal ----
# 7.1 §1.1: a failing wal-push (here: the archive directory made unwritable)
# is a failed hourly run with wal.failing, never ok:true.
docker run --rm -v "$B:/b" "$TOOLS" chmod 000 /b/wal
sql -d hq -c "INSERT INTO t VALUES ('wal-failing')" >/dev/null
sql -c "SELECT pg_switch_wal()" >/dev/null
for _ in $(seq 1 60); do
  [[ "$(sql -c 'SELECT failed_count FROM pg_stat_archiver')" -gt 0 ]] && break
  sleep 1
done
if out="$("${run_env[@]}" HQ_BACKUP_TEST_MOUNT="$T/dest:/dest" "$REPO_DIR/infra/backup/hourly.sh" 2>&1)"; then
  fail "wal: the hourly run succeeded while archiving failed"
else
  st="$B/status/hourly.json"
  if [[ "$(jq -r '.ok' "$st")" == false && "$(jq -r '.wal.failing' "$st")" == true &&
    "$(jq -r '.wal.failed_count' "$st")" -gt 0 ]]; then
    pass "wal: archiving failing -> exit non-zero, ok:false, wal.failing (failed $(jq -r .wal.failed_count "$st"), waiting $(jq -r .wal.ready_count "$st"))"
  else
    fail "wal: status $(jq -c '{ok, error, wal}' "$st")"
  fi
fi
docker run --rm -v "$B:/b" "$TOOLS" chmod 700 /b/wal

exit "$failed"
