#!/usr/bin/env bash
# The backup gate (prompt 07 §1, 7.1 §2.1-§2.9 and §3), on throwaway
# containers, volumes, a network and a temp directory only (never the
# coinepro-hq stack, its volumes or the host's secrets). A real OpenBao (the
# stack's image and config.hcl, raft storage) holds the secrets, and the
# scripts read them through their own AppRole exactly as on the server
# (nothing bypassed); a stand-in for hq.sh points them at a throwaway Postgres
# with WAL-G archiving; a local rclone remote stands in for Google Drive's
# backend (the token itself still comes from OpenBao); a small proxy in front
# of OpenBao answers chosen requests with chosen errors.
#   due        "once a day" is the UTC calendar day (fixed clocks)
#   oauth      the owner's own OAuth client keeps scope drive.file (rclone's own parser)
#   rules      Prometheus' dead-man's switch fires when the last success ages (promtool)
#   units      the hourly and weekly units keep their secrets in RuntimeDirectory=
#   cas        the restic password is made once, with check-and-set: a read that
#              lies (404) or fails (503) never replaces it
#   nodrive    Drive not connected: local only and ok, gdrive "not configured"
#   hourly     a snapshot locally and on the "Drive"; the OpenBao snapshot taken
#              and its token renewed; the metrics for Prometheus; no secret left
#   encrypted  the repository holds no plaintext and does not open without
#              the password (none, or a wrong one)
#   check      restic check passed on both repositories; the snapshot list is written
#   secrets    no secret in docker's argv, the output, the status or metrics
#              files; only a restore gets the write capabilities
#   pitr       ~300 WAL segments before the target; recovery to a moment
#              between two inserts returns exactly the first one
#   down       an unreachable destination fails the run: ok:false, the
#              destination's error in status/hourly.json (the worker alerts)
#   weekly     the weekly restore test: restore from the "Drive", every
#              database check, the files' sha256 and a PITR, ok:true; every
#              restic call of the restore path waits for locks
#   random     the weekly test's own random PITR target, inside its window
#   disk       too little free disk: refused with a clear note, nothing restored
#   locks      a second weekly test exits quietly and writes nothing; a second
#              hourly run writes nothing
#   bao503     OpenBao answers 503 for kv/backup/gdrive: ok:false, never local only
#   vanished   Drive connected once, then gone from OpenBao: ok:false (hourly, weekly)
#   forget     a remote forget that fails is reported per destination; a revoked
#              snapshot token is openbao_snapshot.ok:false
#   checkfail  restic check failing: check.ok false, hq_backup_check_ok 0
#   early      a run that fails before OpenBao is read keeps Drive "configured"
#   wal        a failing wal-push is a failed run with wal.failing
#   archive    the restore test finds one archive record's file among the
#              restored files and checks it against the sha256 the restored
#              database holds (prompt 14 §5): the weekly names it; a file that
#              changed before the backup fails the test
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_env

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
  docker rm -f "$N-pg" "$N-bao" "$N-proxy" "$N-locker" >/dev/null 2>&1 || true
  docker volume rm -f "$N-files" "$N-bao-data" >/dev/null 2>&1 || true
  docker network rm "$N-net" >/dev/null 2>&1 || true
  # Root-, postgres- and api-owned leftovers go through a container.
  docker run --rm -v "$T:/t" "$TOOLS" sh -c 'rm -rf /t/* /t/.[!.]*' >/dev/null 2>&1 || true
  rm -rf "$T"
  if [[ -n "${QUALITY_TMP:-}" ]]; then rm -rf "$QUALITY_TMP"; fi
}
trap cleanup EXIT

model="$(compose_json lean)"
BAO_IMAGE="$(jq -r .services.openbao.image <<<"$model")"
PROM_IMAGE="$(jq -r .services.prometheus.image <<<"$model")"
docker build -q -t "$PG_IMAGE_T" "$REPO_DIR/infra/postgres" >/dev/null
docker build -q -t "$BK_IMAGE_T" "$REPO_DIR/infra/backup" >/dev/null
# lib FUNCTION ARGS...: one function of restic-lib.sh, in its own shell.
lib() { bash -c 'source "$0" && "$@"' "$REPO_DIR/infra/backup/restic-lib.sh" "$@"; }

# ------------------------------------------------------------------- due ----
# 7.1 §2.6: last / now / due? (the old "more than 23 hours" rule drifted).
due_bad=()
while read -r last now want; do
  [[ "$last" == - ]] && last=""
  if lib day_due "$last" "$now"; then got=yes; else got=no; fi
  [[ "$got" == "$want" ]] || due_bad+=("$last→$now=$got")
done <<'CASES'
- 2026-10-22T10:00:00Z yes
2026-10-21T23:59:00Z 2026-10-22T00:01:00Z yes
2026-10-22T00:03:00Z 2026-10-22T23:58:00Z no
2026-10-21T22:30:00Z 2026-10-22T21:00:00Z yes
2026-10-22T02:00:00+03:30 2026-10-21T23:00:00Z no
not-a-time 2026-10-22T00:00:00Z yes
CASES
if ((${#due_bad[@]})); then fail "due: ${due_bad[*]}"; else pass "due: once per UTC calendar day (6 fixed clocks)"; fi

# ----------------------------------------------------------------- oauth ----
# 7.1 §2.8: rclone itself reads the base64 form; its local /auth redirect
# names the client and the scope it will ask Google for (no network needed).
authorize_url() { # authorize_url ARGS... -> the Location rclone redirects to
  docker run --rm --network none "$BK_IMAGE_T" sh -c '
    rclone authorize drive "$@" --auth-no-open-browser >/tmp/o 2>&1 &
    url=""
    for _ in $(seq 1 40); do
      url="$(grep -o "http://127.0.0.1:53682/auth?state=[A-Za-z0-9_-]*" /tmp/o | head -n1)"
      [ -n "$url" ] && break
      sleep 0.25
    done
    wget -S -O /dev/null "$url" 2>&1 | grep -i "location:" | head -n1' sh "$@" 2>&1 || true
}
blob="$(printf '%s\0%s' gate-client.apps.googleusercontent.com gate-client-secret | lib gdrive_authorize_blob)"
own="$(authorize_url "$blob")"
two="$(authorize_url gate-client.apps.googleusercontent.com gate-client-secret)"
if [[ "$blob" != *=* && "$own" == *"client_id=gate-client.apps.googleusercontent.com"* &&
  "$own" == *"scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdrive.file"* &&
  "$two" == *"%2Fauth%2Fdrive&"* ]]; then
  pass "oauth: the owner's client in base64 form asks for drive.file (the two-argument form asked for the whole Drive)"
else
  fail "oauth: own client -> ${own:-nothing}; two-argument form -> ${two:-nothing}"
fi

# ----------------------------------------------------------------- rules ----
cat >"$T/rules-test.yml" <<'YAML'
rule_files: [/rules/backup.rules.yml]
evaluation_interval: 1m
tests:
  - interval: 1m
    input_series:
      - series: 'hq_backup_last_success_timestamp_seconds{instance="hub",job="node"}'
        values: '0x200'
      - series: 'hq_backup_check_ok{instance="hub",job="node"}'
        values: '1x5 0x10'
    alert_rule_test:
      - eval_time: 1h
        alertname: HqBackupDeadMansSwitch
        exp_alerts: []
      - eval_time: 2h10m
        alertname: HqBackupDeadMansSwitch
        exp_alerts:
          - exp_labels: {severity: urgent, category: data_loss}
            exp_annotations:
              summary: "No successful hourly backup for more than 2 hours"
              description: "infra/backup/hourly.sh: journalctl -u coinepro-hq-backup-hourly.service; status/hourly.json"
      - eval_time: 3m
        alertname: HqBackupCheckFailed
        exp_alerts: []
      - eval_time: 8m
        alertname: HqBackupCheckFailed
        exp_alerts:
          - exp_labels: {severity: urgent, category: data_loss}
            exp_annotations:
              summary: "restic check failed on a backup repository"
  - interval: 1m
    input_series:
      - series: 'hq_backup_last_success_timestamp_seconds{instance="hub",job="node"}'
        values: '0+60x200'
    alert_rule_test:
      - eval_time: 2h10m
        alertname: HqBackupDeadMansSwitch
        exp_alerts: []
      - eval_time: 2h10m
        alertname: HqBackupMetricsMissing
        exp_alerts: []
YAML
if out="$(docker run --rm --network none --entrypoint promtool \
  -v "$REPO_DIR/infra/observability/prometheus/rules:/rules:ro" -v "$T/rules-test.yml:/t.yml:ro" "$PROM_IMAGE" \
  test rules /t.yml 2>&1)"; then
  pass "rules: the dead-man's switch fires when the last success is over 2 h old, not while fresh"
else
  fail "rules: $(tail -n6 <<<"$out")"
fi

# ----------------------------------------------------------------- units ----
units_bad=()
for u in coinepro-hq-backup-hourly coinepro-hq-restore-weekly; do
  f="$REPO_DIR/infra/systemd/$u.service"
  grep -qx "RuntimeDirectory=$u" "$f" || units_bad+=("$u: no RuntimeDirectory=$u")
  grep -qx 'RuntimeDirectoryMode=0700' "$f" || units_bad+=("$u: RuntimeDirectoryMode is not 0700")
done
if grep -q '/dev/shm' "$REPO_DIR"/infra/systemd/*.service; then units_bad+=("a unit names /dev/shm"); fi
if ((${#units_bad[@]})); then fail "units: ${units_bad[*]}"; else
  pass "units: hourly and weekly keep their secrets in their own RuntimeDirectory= (0700)"
fi

# ---------------------------------------------------------------- set-up ----
B="$T/backups"
S="$T/secrets"
mkdir -p "$B/status" "$T/bin" "$T/dest" "$T/textfile" "$T/run" "$T/rules" "$S/backup"
chmod 700 "$B" "$S" "$S/backup" "$T/run"
chmod 777 "$T/dest"  # the Drive stand-in: written by the backup container's root without DAC_OVERRIDE
docker run --rm -v "$B:/b" "$TOOLS" sh -c '
  mkdir -p /b/wal /b/restic /b/audit-anchors &&
  chown 999:999 /b/wal && chmod 700 /b/wal && chmod 700 /b/restic &&
  echo "{\"seq\": 1, \"hash\": \"ab\"}" >/b/audit-anchors/audit-chain.jsonl'
docker volume create "$N-files" >/dev/null
marker_file="file-marker-$(openssl rand -hex 8)"
docker run --rm -v "$N-files:/d" "$TOOLS" sh -c "mkdir -p /d/ab && echo $marker_file >/d/ab/f1 && chown -R 10001 /d"

# OpenBao as on the server: its image and config.hcl (raft), initialised and unsealed here.
docker network create "$N-net" >/dev/null
docker volume create "$N-bao-data" >/dev/null
docker run -d --name "$N-bao" --network "$N-net" --network-alias openbao -p 127.0.0.1::8200 \
  -e SKIP_CHOWN=true -e SKIP_SETCAP=true -v "$REPO_DIR/infra/openbao/config.hcl:/openbao/config/config.hcl:ro" \
  -v "$N-bao-data:/openbao/file" "$BAO_IMAGE" server >/dev/null
bao="http://$(docker port "$N-bao" 8200/tcp | head -n1)"
for _ in $(seq 60); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "$bao/v1/sys/health")" =~ ^(501|503|200)$ ]] && break
  sleep 1
done
umask 077
curl -sS -X PUT --data '{"secret_shares": 1, "secret_threshold": 1}' "$bao/v1/sys/init" >"$T/bao-init.json"
jq -c '{key: .keys_base64[0]}' "$T/bao-init.json" | curl -sS -X PUT --data-binary @- "$bao/v1/sys/unseal" >/dev/null
jq -r '"X-Vault-Token: " + .root_token' "$T/bao-init.json" >"$T/root.auth"
umask 022
for _ in $(seq 60); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "$bao/v1/sys/health")" == 200 ]] && break
  sleep 1
done
api() { # api METHOD PATH [body on stdin] -> HTTP code; the answer in $T/api.resp (root token)
  local body=()
  [[ "$1" != GET ]] && body=(--data-binary @-)
  curl -sS -o "$T/api.resp" -w '%{http_code}' -X "$1" -H @"$T/root.auth" -H 'Content-Type: application/json' \
    "${body[@]}" "$2" </dev/stdin
}
setup_ok=true
want() { [[ "$1" =~ ^(200|204)$ ]] || { setup_ok=false; echo "backup: set-up: HTTP $1 for $2" >&2; }; }
want "$(echo '{"type": "kv", "options": {"version": "2"}}' | api POST "$bao/v1/sys/mounts/kv")" kv
want "$(echo '{"type": "approle"}' | api POST "$bao/v1/sys/auth/approle")" approle
for p in hq-backup backup-snapshot; do
  want "$(jq -Rs '{policy: .}' "$REPO_DIR/infra/openbao/policies/$p.hcl" | api PUT "$bao/v1/sys/policies/acl/$p")" "$p"
done
# The AppRole exactly as provision.sh makes it.
want "$(jq -n '{token_policies: ["hq-backup"], token_no_default_policy: true, token_ttl: "1h",
    token_max_ttl: "4h", secret_id_ttl: "0"}' | api POST "$bao/v1/auth/approle/role/hq-backup")" role
want "$(api GET "$bao/v1/auth/approle/role/hq-backup/role-id" </dev/null)" role-id
jq -r .data.role_id "$T/api.resp" >"$T/role_id"
want "$(echo '{}' | api POST "$bao/v1/auth/approle/role/hq-backup/secret-id")" secret-id
(umask 077 && jq --rawfile r "$T/role_id" '{role_id: ($r | rtrimstr("\n")), secret_id: .data.secret_id}' \
  "$T/api.resp" >"$S/backup/approle.json")
secret_id="$(jq -r .secret_id "$S/backup/approle.json")"
gdrive_token="gate-access-$(openssl rand -hex 12)"
put_gdrive() {
  jq -n --arg t "{\"access_token\":\"$gdrive_token\",\"refresh_token\":\"$gdrive_token\"}" \
    '{data: {token: $t, client_id: "", client_secret: ""}}' | api POST "$bao/v1/kv/data/backup/gdrive"
}
printf 'type = alias\nremote = /dest\n' >"$T/gdrive.backend"

# The proxy in front of OpenBao: "METHOD PATH=CODE" lines in $T/rules/rules.
cat >"$T/proxy.py" <<'PY'
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def rules():
    try:
        return dict(l.strip().split("=", 1) for l in open("/rules/rules") if "=" in l)
    except OSError:
        return {}

class H(BaseHTTPRequestHandler):
    def go(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        code = rules().get(f"{self.command} {self.path}")
        if code:
            data = b'{"errors": ["injected by the backup gate"]}'
            status, headers = int(code), [("Content-Type", "application/json")]
        else:
            c = http.client.HTTPConnection("openbao", 8200, timeout=60)
            skip = ("host", "content-length", "connection")
            c.request(self.command, self.path, body=body,
                      headers={k: v for k, v in self.headers.items() if k.lower() not in skip})
            r = c.getresponse()
            data, status = r.read(), r.status
            headers = [(k, v) for k, v in r.getheaders() if k.lower() not in skip + ("transfer-encoding",)]
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    do_GET = do_POST = do_PUT = do_DELETE = go
    def log_message(self, *args):
        pass

ThreadingHTTPServer(("0.0.0.0", 8200), H).serve_forever()
PY
: >"$T/rules/rules"
chmod 755 "$T/rules" && chmod 644 "$T/rules/rules" "$T/proxy.py"
docker run -d --name "$N-proxy" --network "$N-net" -p 127.0.0.1::8200 -v "$T/rules:/rules:ro" \
  -v "$T/proxy.py:/proxy.py:ro" "$PYTHON_IMAGE" python /proxy.py >/dev/null
proxy="http://$(docker port "$N-proxy" 8200/tcp | head -n1)"
for _ in $(seq 30); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "$proxy/v1/sys/health")" == 200 ]] && break
  sleep 1
done
inject() { printf '%s\n' "$@" >"$T/rules/rules"; }

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
# Prompt 14 §5: the archive's two columns the restore test reads, one record
# and its file in the file store's layout (<key[:2]>/<key>).
archive_key="$(openssl rand -hex 16)"
archive_body="archive-file-$(openssl rand -hex 8)"
archive_sha="$(printf '%s' "$archive_body" | sha256sum | cut -d' ' -f1)"
sql -d hq -c "CREATE SCHEMA archive" -c "CREATE TABLE archive.records (id int PRIMARY KEY, ref text NOT NULL)" \
  -c "CREATE TABLE archive.record_files (record_id int NOT NULL, storage_key text, stored_sha256 text NOT NULL,
        destroyed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now())" \
  -c "INSERT INTO archive.records VALUES (1, 'AR-000001')" \
  -c "INSERT INTO archive.record_files (record_id, storage_key, stored_sha256) VALUES (1, '$archive_key', '$archive_sha')" \
  >/dev/null
docker run --rm -v "$N-files:/d" "$TOOLS" sh -c \
  "mkdir -p /d/${archive_key:0:2} && printf %s '$archive_body' >/d/${archive_key:0:2}/$archive_key && chown -R 10001 /d"
archived_now() { # wait (up to $1 s) until the archiver has the current segment
  local _
  for _ in $(seq 1 "$1"); do
    [[ "$(sql -c "SELECT last_archived_wal >= pg_walfile_name(pg_current_wal_lsn() - 1) FROM pg_stat_archiver")" == t ]] &&
      return 0
    sleep 1
  done
  return 1
}

# The stand-in for hq.sh: config = this test's images and volume; exec = the throwaway Postgres.
jq -n --arg pg "$PG_IMAGE_T" --arg bk "$BK_IMAGE_T" --arg tools "$TOOLS" --arg files "$N-files" '{
  services: {postgres: {image: $pg}, "hq-tools": {image: $tools},
             "backup-tools": {image: $bk, deploy: {resources: {limits: {memory: "402653184"}}}}},
  volumes: {"hq-files": {name: $files}}}' >"$T/config.json"
cat >"$T/bin/hq" <<EOF
#!/usr/bin/env bash
set -euo pipefail
while [[ "\${1:-}" == --profile ]]; do shift 2; done
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
# docker, logged: every argv the scripts give it, for the secret and capability scans.
real_docker="$(command -v docker)"
cat >"$T/bin/docker" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$T/docker-argv.log"
exec "$real_docker" "\$@"
EOF
chmod +x "$T/bin/hq" "$T/bin/docker"
: >"$T/docker-argv.log"
: >"$T/outputs.log"
run_env=(env PATH="$T/bin:$PATH" HQ_COMPOSE_CMD="$T/bin/hq" HQ_BACKUP_DIR="$B" HQ_SECRETS_DIR="$S"
  HQ_BAO_ADDR="$bao" HQ_BACKUP_TEST_GDRIVE="$T/gdrive.backend" HQ_ENV_FILE=/dev/null
  HQ_TEXTFILE_DIR="$T/textfile" RUNTIME_DIRECTORY="$T/run")
run() { # run SCRIPT [ENV=VALUE...] -> its output on stdout (also kept for the secret scan); its exit code
  local script="$1" rc=0 o
  shift
  o="$("${run_env[@]}" HQ_BACKUP_TEST_MOUNT="$T/dest:/dest" "$@" "$REPO_DIR/infra/backup/$script" 2>&1)" || rc=$?
  printf '%s\n' "$o" >>"$T/outputs.log"
  printf '%s\n' "$o"
  return "$rc"
}
st="$B/status/hourly.json"
dest() { jq -r --arg k "$1" ".destinations[] | select(.key == \$k) | $2" "$st"; }
state_del() { jq "del(.$1)" "$B/hourly/state.json" >"$B/hourly/state.json.tmp" && mv "$B/hourly/state.json.tmp" "$B/hourly/state.json"; }
argv_mark() { wc -l <"$T/docker-argv.log"; }
argv_since() { tail -n +"$(($1 + 1))" "$T/docker-argv.log"; }

# ------------------------------------------------------------------- cas ----
version() { api GET "$bao/v1/kv/metadata/backup/restic" </dev/null >/dev/null; jq -r '.data.current_version // 0' "$T/api.resp"; }
cas_out="$(HQ_BAO_ADDR="$bao" "$REPO_DIR/infra/openbao/restic-password.sh" "$T/root.auth" 2>&1)" && c1=0 || c1=$?
v1="$(version)"
api GET "$bao/v1/kv/data/backup/restic" </dev/null >/dev/null
password="$(jq -r .data.data.password "$T/api.resp")"
HQ_BAO_ADDR="$bao" "$REPO_DIR/infra/openbao/restic-password.sh" "$T/root.auth" >/dev/null 2>&1 && c2=0 || c2=$?
inject "GET /v1/kv/data/backup/restic=404"
lie="$(HQ_BAO_ADDR="$proxy" "$REPO_DIR/infra/openbao/restic-password.sh" "$T/root.auth" 2>&1)" && c3=0 || c3=$?
inject "GET /v1/kv/data/backup/restic=503"
HQ_BAO_ADDR="$proxy" "$REPO_DIR/infra/openbao/restic-password.sh" "$T/root.auth" >/dev/null 2>&1 && c4=0 || c4=$?
inject
api GET "$bao/v1/kv/data/backup/restic" </dev/null >/dev/null
same=no
if [[ "$(jq -r .data.data.password "$T/api.resp")" == "$password" ]]; then same=yes; fi
if [[ "$setup_ok" == true && $c1 == 0 && "$v1" == 1 && ${#password} -ge 60 && $c2 == 0 && $c3 == 0 &&
  "$lie" == *"check-and-set"* && $c4 != 0 && "$(version)" == 1 && "$same" == yes ]]; then
  pass "cas: made once; kept on a rerun, when the read lies (404: cas 0 refused) and when it fails (503: no write)"
else
  fail "cas: set-up=$setup_ok first=$c1 version=$v1 rerun=$c2 lie=$c3 ($(tail -n1 <<<"$lie")) 503=$c4 now=$(version) same=$same first: $(tail -n1 <<<"$cas_out")"
fi

# --------------------------------------------------------------- nodrive ----
if out="$(run hourly.sh)"; then
  if [[ "$(jq -r .ok "$st")" == true && "$(dest local .ok)" == true && "$(dest gdrive .configured)" == false &&
    "$(dest gdrive .error)" == "not configured (make gdrive-auth)" && "$(dest gdrive .ok)" == null &&
    "$(jq -r .openbao_snapshot.configured "$st")" == false &&
    -z "$(jq -r '.gdrive_configured_at // empty' "$B/hourly/state.json")" ]]; then
    pass "nodrive: Drive not connected (404): local only, ok, gdrive 'not configured', nothing remembered"
  else
    fail "nodrive: status $(jq -c '{ok, error, destinations: [.destinations[] | {key, configured, ok, error}]}' "$st")"
  fi
else
  fail "nodrive: exit non-zero: $(tail -n3 <<<"$out")"
fi

# ---------------------------------------------------------------- hourly ----
want "$(put_gdrive)" gdrive
want "$(jq -n '{policies: ["backup-snapshot"], period: "768h", display_name: "hq-backup-snapshot"}' |
  api POST "$bao/v1/auth/token/create-orphan")" snapshot-token
snap_accessor="$(jq -r .auth.accessor "$T/api.resp")"
snap_token="$(jq -r .auth.client_token "$T/api.resp")"
want "$(jq '{data: {token: .auth.client_token}}' "$T/api.resp" | api POST "$bao/v1/kv/data/backup/openbao-snapshot")" snapshot-kv
state_del check_at  # the first run checked local alone; check both repositories now
state_del prune_at
if out="$(run hourly.sh)"; then
  jq -n --arg a "$snap_accessor" '{accessor: $a}' | api POST "$bao/v1/auth/token/lookup-accessor" >/dev/null
  renewed="$(jq -r '.data.last_renewal_time // 0' "$T/api.resp")"
  prom="$T/textfile/hq_backup.prom"
  last_s="$(sed -n 's/^hq_backup_last_success_timestamp_seconds //p' "$prom" 2>/dev/null)"
  if [[ "$(jq -r '.ok' "$st")" == true &&
    "$(jq -r '[.destinations[] | select(.ok == true) | .key] | sort | join(",")' "$st")" == gdrive,local &&
    -n "$(jq -r '.snapshot // empty' "$st")" && "$(jq -r '.base_backup.count' "$st")" -ge 1 &&
    "$(dest gdrive .quota_bytes)" != null &&
    "$(jq -r .openbao_snapshot.ok "$st")" == true && "$(jq -r .openbao_snapshot.ttl_s "$st")" -ge 604800 &&
    -s "$B/hourly/set/openbao.snap" && "$renewed" -gt 0 &&
    -n "$(jq -r '.gdrive_configured_at // empty' "$B/hourly/state.json")" ]]; then
    pass "hourly: snapshot $(jq -r '.snapshot[0:8]' "$st") in local and the Drive stand-in (quota read), a base backup, the OpenBao snapshot taken and its token renewed"
  else
    fail "hourly: status $(jq -c '{ok, error, openbao_snapshot, destinations: [.destinations[] | {key, ok, error, quota_bytes}]}' "$st") renewed=$renewed"
  fi
  if [[ "$last_s" =~ ^[0-9]+$ ]] && (($(date +%s) - last_s < 600)) && grep -qx 'hq_backup_last_run_ok 1' "$prom" &&
    grep -qx 'hq_backup_destination_ok{destination="gdrive"} 1' "$prom" && grep -qx 'hq_backup_openbao_snapshot_ok 1' "$prom" &&
    [[ "$(stat -c %a "$prom")" == 644 && -z "$(ls -A "$T/run")" ]]; then
    pass "hourly: hq_backup.prom for Prometheus (last success now, every destination); RuntimeDirectory left empty"
  else
    fail "hourly: metrics $(tr '\n' ' ' <"$prom" 2>/dev/null | head -c 600) run-dir=[$(ls -A "$T/run")]"
  fi
else
  fail "hourly: exit non-zero: $(tail -n3 <<<"$out")"
fi

# ------------------------------------------------------------- encrypted ----
plain="$(docker run --rm -v "$T/dest:/d:ro" -v "$B/restic:/r:ro" "$TOOLS" \
  sh -c "grep -rl -e '$marker_db' -e '$marker_file' /d /r 2>/dev/null | wc -l")"
nopass="$(docker run --rm --network none -v "$T/dest:/d:ro" "$BK_IMAGE_T" \
  restic -r "/d/CoinePro HQ Backup" --insecure-no-password cat config >/dev/null 2>&1 && echo opened || echo refused)"
wrong="$(docker run --rm --network none -v "$T/dest:/d:ro" -e RESTIC_PASSWORD=wrong-password "$BK_IMAGE_T" \
  restic -r "/d/CoinePro HQ Backup" cat config >/dev/null 2>&1 && echo opened || echo refused)"
if [[ "$plain" == 0 && "$nopass" == refused && "$wrong" == refused &&
  -d "$T/dest/CoinePro HQ Backup" ]]; then
  pass "encrypted: no plaintext in either repository; no password and a wrong one are refused"
else
  fail "encrypted: plaintext files=$plain, no password=$nopass, wrong password=$wrong"
fi

# ----------------------------------------------------------------- check ----
if [[ "$(jq -r '.check.ok' "$st")" == true &&
  "$(jq '[.items[] | .destination] | unique | length' "$B/status/snapshots.json")" == 2 ]]; then
  pass "check: restic check --read-data-subset 5% passed; snapshots listed for both repositories"
else
  fail "check: check=$(jq -c .check "$st") snapshots=$(jq -c '[.items[].destination]' "$B/status/snapshots.json")"
fi

# --------------------------------------------------------------- secrets ----
leaks=0
for s in "$password" "$gdrive_token" "$secret_id" "$snap_token"; do
  for f in "$T/docker-argv.log" "$T/outputs.log" "$B/status/hourly.json" "$B/status/snapshots.json" \
    "$T/textfile/hq_backup.prom" "$B/hourly/state.json"; do
    if grep -qF "$s" "$f"; then leaks=$((leaks + 1)); fi
  done
done
if grep -q 'RESTIC_PASSWORD=' "$T/docker-argv.log"; then leaks=$((leaks + 1)); fi
caps_bad="$(grep -E 'DAC_OVERRIDE|CAP_CHOWN|--cap-add CHOWN|FOWNER' "$T/docker-argv.log" | grep -cv ' restore ' || true)"
if ((leaks == 0 && caps_bad == 0)) && grep -q 'RESTIC_PASSWORD_FILE=' "$T/docker-argv.log" &&
  grep -qE -- '-v [^ ]*/rclone:/run/hq-rclone -v' "$T/docker-argv.log"; then
  pass "secrets: no secret in argv, env, output, status or metrics; backup calls read only (DAC_READ_SEARCH); rclone's config writable"
else
  fail "secrets: $leaks leak(s); $caps_bad non-restore call(s) with write capabilities"
fi

# ------------------------------------------------------------------ pitr ----
# 7.1 §2.1: ~300 segments before the target (replay longer than the old 120 s limit).
for i in $(seq 1 300); do
  printf "INSERT INTO t VALUES ('seg-%s');\nSELECT pg_switch_wal();\n" "$i"
done | docker exec -i "$N-pg" psql -U postgres -d hq -X -q -v ON_ERROR_STOP=1 >/dev/null
archived_now 600 || fail "pitr: the ~300 segments were not archived within 10 minutes"
sql -d hq -c "INSERT INTO t VALUES ('before')" >/dev/null
sleep 2
target="$(sql -c "SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS.US')") UTC"
sleep 2
sql -d hq -c "INSERT INTO t VALUES ('after')" >/dev/null
sql -c "SELECT pg_switch_wal()" >/dev/null
archived_now 60 || true
res="$("${run_env[@]}" "$REPO_DIR/infra/backup/pitr.sh" "$target" --prefix "$B/wal" --image "$PG_IMAGE_T" \
  --db hq --sql "SELECT string_agg(v, ',' ORDER BY v) FROM t WHERE v IN ('before', 'after')" 2>&1 || true)"
if [[ "$(jq -r '.ok' <<<"$res" 2>/dev/null)" == true && "$(jq -r '.value' <<<"$res")" == before ]]; then
  pass "pitr: ~300 segments replayed ($(jq -r .duration_s <<<"$res") s); recovery to $target has 'before' and not 'after'"
else
  fail "pitr: $res"
fi

# ------------------------------------------------------------------ down ----
if "${run_env[@]}" HQ_BACKUP_TEST_MOUNT="$T/nowhere:/dest:ro" "$REPO_DIR/infra/backup/hourly.sh" >/dev/null 2>&1; then
  fail "down: succeeded with the destination unreachable"
else
  if [[ "$(jq -r '.ok' "$st")" == false && "$(dest gdrive .ok)" == false && "$(dest local .ok)" == true &&
    "$(jq -r '.last_ok_at' "$st")" != null ]]; then
    pass "down: ok:false, gdrive $(dest gdrive .error), local still ok"
  else
    fail "down: status $(jq -c '{ok, error, last_ok_at, destinations}' "$st")"
  fi
fi

# ---------------------------------------------------------------- weekly ----
run hourly.sh >/dev/null || true
w="$B/status/restore-weekly.json"
m="$(argv_mark)"
if out="$(run restore-weekly.sh HQ_PITR_AFTER_BASE_S=1 HQ_PITR_BEFORE_SNAPSHOT_S=1 HQ_PITR_TARGET="$target")"; then
  restic_calls="$(argv_since "$m" | grep -c ' restic ' || true)"
  waiting="$(argv_since "$m" | grep ' restic ' | grep -c -- '--retry-lock 30m' || true)"
  if [[ "$(jq -r '.ok' "$w")" == true && "$(jq -r '.source' "$w")" == gdrive &&
    "$(jq -r '.pitr.ok' "$w")" == true && "$restic_calls" -ge 3 && "$waiting" == "$restic_calls" ]] &&
    argv_since "$m" | grep ' restic ' | grep ' restore ' | grep -q 'DAC_OVERRIDE'; then
    pass "weekly: restored from the Drive stand-in; databases, files and PITR ($(jq -r .pitr.target "$w")) ok; all $restic_calls restic calls --retry-lock 30m"
  else
    fail "weekly: $(jq -c . "$w"); restic calls $restic_calls, with --retry-lock $waiting"
  fi
else
  fail "weekly: exit non-zero: $(tail -n4 <<<"$out")"
fi

if [[ "$(jq -r '.db.notes' "$w")" == *"archive=AR-000001"* ]]; then
  pass "weekly: the archive record AR-000001 came back and its file's sha256 is the one its database row holds"
else
  fail "weekly: the restore test did not check the archive record ($(jq -r '.db.notes' "$w"))"
fi

# ---------------------------------------------------------------- random ----
if out="$(run restore-weekly.sh HQ_PITR_AFTER_BASE_S=1 HQ_PITR_BEFORE_SNAPSHOT_S=30)"; then
  t_s="$(date -u -d "$(jq -r .pitr.target "$w")" +%s)"
  base_s="$(date -u -d "$(jq -r .base_backup_at "$B/hourly/state.json")" +%s)"
  snap_s="$(date -u -d "$(jq -r .snapshot_time "$w")" +%s)"
  if [[ "$(jq -r '.ok' "$w")" == true && "$(jq -r '.pitr.ok' "$w")" == true ]] &&
    ((t_s > base_s && t_s <= snap_s - 30 && t_s >= $(date +%s) - 86400)); then
    pass "random: its own random PITR target $(jq -r .pitr.target "$w") (window $((snap_s - 30 - base_s)) s) recovered"
  else
    fail "random: target $(jq -r .pitr.target "$w") window $base_s..$((snap_s - 30)): $(jq -c '{ok, notes, pitr}' "$w")"
  fi
else
  fail "random: exit non-zero: $(tail -n4 <<<"$out"); $(jq -c '{notes, pitr}' "$w")"
fi

# ------------------------------------------------------------------ disk ----
m="$(argv_mark)"
if run restore-weekly.sh HQ_RESTORE_MIN_FREE_BYTES=1000000000000000 >/dev/null; then
  fail "disk: the restore test ran without room"
elif [[ "$(jq -r .ok "$w")" == false && "$(jq -r .notes "$w")" == "not enough free disk"*"nothing restored" ]] &&
  ! argv_since "$m" | grep ' restic ' | grep -q ' restore '; then
  pass "disk: restore size + reserve over the free disk: refused before restoring ($(jq -r .notes "$w" | cut -c1-70)...)"
else
  fail "disk: $(jq -c '{ok, notes}' "$w")"
fi

# ----------------------------------------------------------------- locks ----
before_w="$(sha256sum <"$w")"
flock -o "$B/.restore-weekly.lock" sleep 120 >/dev/null 2>&1 &
holder=$!
sleep 1
m="$(argv_mark)"
run restore-weekly.sh >/dev/null && wrc=0 || wrc=$?
w_calls="$(argv_since "$m" | wc -l)"
kill "$holder" 2>/dev/null || true
wait "$holder" 2>/dev/null || true
before_h="$(sha256sum <"$st")"
flock -o "$B/hourly/.lock" sleep 120 >/dev/null 2>&1 &
holder=$!
sleep 1
run hourly.sh >/dev/null && hrc=0 || hrc=$?
kill "$holder" 2>/dev/null || true
wait "$holder" 2>/dev/null || true
if ((wrc == 0 && w_calls == 0 && hrc != 0)) && [[ "$(sha256sum <"$w")" == "$before_w" && "$(sha256sum <"$st")" == "$before_h" ]]; then
  pass "locks: a second weekly test exits 0 without a call or a word in its status; a second hourly run exits non-zero and writes nothing"
else
  fail "locks: weekly exit $wrc ($w_calls docker call(s)), hourly exit $hrc; statuses unchanged: $([[ "$(sha256sum <"$w")" == "$before_w" ]] && echo yes || echo no)/$([[ "$(sha256sum <"$st")" == "$before_h" ]] && echo yes || echo no)"
fi

# ---------------------------------------------------------------- bao503 ----
inject "GET /v1/kv/data/backup/gdrive=503"
if run hourly.sh HQ_BAO_ADDR="$proxy" >/dev/null; then
  fail "bao503: succeeded while OpenBao answered 503 for the Drive token"
elif [[ "$(jq -r .ok "$st")" == false && "$(dest gdrive .configured)" == true && "$(dest gdrive .ok)" == false &&
  "$(dest gdrive .error)" == *"HTTP 503"* && "$(dest local .ok)" == true ]]; then
  pass "bao503: ok:false, gdrive '$(dest gdrive .error)', local still taken (never a quiet local-only run)"
else
  fail "bao503: status $(jq -c '{ok, error, destinations: [.destinations[] | {key, configured, ok, error}]}' "$st")"
fi
inject

# -------------------------------------------------------------- vanished ----
want "$(api DELETE "$bao/v1/kv/metadata/backup/gdrive" </dev/null)" gdrive-delete
run hourly.sh >/dev/null && vh=0 || vh=$?
vh_status="$(jq -c '{ok, error, gdrive: (.destinations[] | select(.key == "gdrive") | {configured, ok, error})}' "$st")"
run restore-weekly.sh >/dev/null && vw=0 || vw=$?
if ((vh != 0 && vw != 0)) && [[ "$(jq -r .ok "$st")" == false && "$(dest gdrive .configured)" == true &&
  "$(dest gdrive .error)" == *"is gone"* && "$(jq -r .ok "$w")" == false && "$(jq -r .notes "$w")" == *"is gone"* ]]; then
  pass "vanished: Drive connected once, then gone from OpenBao: hourly and weekly fail and say so"
else
  fail "vanished: hourly exit $vh $vh_status; weekly exit $vw $(jq -c '{ok, notes}' "$w")"
fi
want "$(put_gdrive)" gdrive-again

# ---------------------------------------------------------------- forget ----
# A foreign shared lock on the "Drive": copy (shared) passes, forget (exclusive) cannot.
(umask 077 && mkdir -p "$T/locker" && printf '%s' "$password" >"$T/locker/restic.pass")
docker run -d --name "$N-locker" --network none -v "$T/dest:/d" -v "$T/locker:/p:ro" \
  -e RESTIC_PASSWORD_FILE=/p/restic.pass "$BK_IMAGE_T" \
  sh -c 'sleep 600 | restic -r "/d/CoinePro HQ Backup" backup --stdin --stdin-filename lock --host gate-locker --quiet' >/dev/null
for _ in $(seq 30); do
  [[ -n "$(ls -A "$T/dest/CoinePro HQ Backup/locks" 2>/dev/null)" ]] && break
  sleep 1
done
want "$(jq -n --arg a "$snap_accessor" '{accessor: $a}' | api POST "$bao/v1/auth/token/revoke-accessor")" revoke
run hourly.sh >/dev/null && frc=0 || frc=$?
docker rm -f "$N-locker" >/dev/null 2>&1 || true
docker run --rm --network none -v "$T/dest:/d" -v "$T/locker:/p:ro" -e RESTIC_PASSWORD_FILE=/p/restic.pass \
  "$BK_IMAGE_T" restic -r "/d/CoinePro HQ Backup" unlock --remove-all >/dev/null 2>&1 || true
if ((frc == 0)) && [[ "$(dest gdrive .ok)" == true && "$(dest gdrive .retention_ok)" == false &&
  "$(dest gdrive .retention_error)" == "forget failed"* && "$(dest local .retention_ok)" == true &&
  "$(jq -r .openbao_snapshot.ok "$st")" == false ]] && grep -qx 'hq_backup_openbao_snapshot_ok 0' "$T/textfile/hq_backup.prom"; then
  pass "forget: the remote forget failure is reported (gdrive retention_ok:false, local ok); a revoked snapshot token is ok:false"
else
  fail "forget: exit $frc $(jq -c '{ok, error, openbao_snapshot, destinations: [.destinations[] | {key, ok, retention_ok, retention_error}]}' "$st")"
fi

# ------------------------------------------------------------- checkfail ----
docker run --rm -v "$B/restic:/r" "$TOOLS" sh -c 'printf x >>"$(find /r/repo/data -type f | head -n1)"'
state_del check_at
run hourly.sh >/dev/null || true
if [[ "$(jq -r .check.ok "$st")" == false ]] && grep -qx 'hq_backup_check_ok 0' "$T/textfile/hq_backup.prom"; then
  pass "checkfail: a pack of the local repository grown by one byte: check.ok false, hq_backup_check_ok 0 (the worker and Prometheus alert)"
else
  fail "checkfail: check $(jq -c .check "$st")"
fi

# ----------------------------------------------------------------- early ----
# 7.1 §3: a run that fails before OpenBao is read (here: Postgres does not
# answer) still shows the connected Drive as configured, never "not configured".
cat >"$T/bin/hq-broken" <<EOF
#!/usr/bin/env bash
while [[ "\${1:-}" == --profile ]]; do shift 2; done
[[ "\${1:-}" == config ]] && exec cat "$T/config.json"
exit 1
EOF
chmod +x "$T/bin/hq-broken"
if run hourly.sh HQ_COMPOSE_CMD="$T/bin/hq-broken" >/dev/null; then
  fail "early: succeeded without Postgres"
elif [[ "$(jq -r .ok "$st")" == false && "$(dest gdrive .configured)" == true && "$(dest gdrive .error)" == null ]]; then
  pass "early: failed before OpenBao was read ($(jq -r .error "$st")): Drive still shown as configured"
else
  fail "early: status $(jq -c '{ok, error, destinations: [.destinations[] | {key, configured, ok, error}]}' "$st")"
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
if out="$(run hourly.sh)"; then
  fail "wal: the hourly run succeeded while archiving failed"
else
  if [[ "$(jq -r '.ok' "$st")" == false && "$(jq -r '.wal.failing' "$st")" == true &&
    "$(jq -r '.wal.failed_count' "$st")" -gt 0 ]] && grep -qx 'hq_backup_wal_failing 1' "$T/textfile/hq_backup.prom"; then
    pass "wal: archiving failing -> exit non-zero, ok:false, wal.failing (failed $(jq -r .wal.failed_count "$st"), waiting $(jq -r .wal.ready_count "$st"))"
  else
    fail "wal: status $(jq -c '{ok, error, wal}' "$st")"
  fi
fi
docker run --rm -v "$B:/b" "$TOOLS" chmod 700 /b/wal

# --------------------------------------------------------------- archive ----
# Prompt 14 §5, on a set of backup.sh (files.tar.gz restored into a volume):
# the record's file is checked against its row; once the row's sha256 differs
# from the stored file (a file changed before the backup: the set's own sums
# still agree with it), the restore test fails on that record.
rt="$B/status/restore-test.json"
if run backup.sh >/dev/null && out="$(run restore-test.sh)" &&
  grep -q 'archive ok (AR-000001' <<<"$out" && grep -q 'archive=AR-000001' <<<"$out" &&
  [[ "$(jq -c '.archive' "$rt")" == '{"ref":"AR-000001","ok":true}' ]]; then
  sql -d hq -c "UPDATE archive.record_files SET stored_sha256 = repeat('0', 64)" >/dev/null
  if run backup.sh >/dev/null && out="$(run restore-test.sh)"; then
    fail "archive: a record whose file differs from its sha256 passed the restore test"
  elif grep -q 'FAIL: archive: AR-000001: the restored file does not match its sha256' <<<"$out" &&
    [[ "$(jq -c '[.ok, .archive]' "$rt")" == '[false,{"ref":"AR-000001","ok":false}]' ]]; then
    pass "archive: the restore test checks one record's file against its row; a changed file fails it"
  else
    fail "archive: changed file: $(tail -n2 <<<"$out") status $(jq -c . "$rt")"
  fi
  sql -d hq -c "UPDATE archive.record_files SET stored_sha256 = '$archive_sha'" >/dev/null
else
  fail "archive: the restore test of a backup.sh set: $(tail -n3 <<<"${out:-}") status $(jq -c . "$rt" 2>/dev/null)"
fi

exit "$failed"
