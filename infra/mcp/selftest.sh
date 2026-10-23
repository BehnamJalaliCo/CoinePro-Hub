#!/usr/bin/env bash
# The MCP container servers' own acceptance test (prompt 12 §14; `make mcp-test`),
# on the host, against the built images, in a throwaway internal network of its
# own (never the stack's hq-mcp, never a coinepro-hq-* container):
#   time         lists exactly get_current_time and convert_time, and tells the
#                time in Tehran (+03:30) through the gateway's own MCP client
#   codecortex   a fixture git repository indexed by the one-shot job
#                (network none), then PR intelligence on its "PR" branch names
#                the test the change affects and not the unrelated one; the
#                repository copy is read-only inside the server
#   both         no internet, no 10.10.1.1, no hub service from inside; root
#                read-only; uid 10001
# Env: MCP_TEST_NAME (default mcp-selftest, the prefix of everything it makes),
#      MCP_TEST_TAG (default 0.1.0), MCP_TEST_CLIENT (default coinepro-hq/gateway:0.1.0).
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAME="${MCP_TEST_NAME:-mcp-selftest}"
TAG="${MCP_TEST_TAG:-0.1.0}"
CLIENT="${MCP_TEST_CLIENT:-coinepro-hq/gateway:0.1.0}"
PROBE_IMAGE="busybox:1.38.0-musl"
NET="$NAME-net"
VOL="$NAME-cc-repos"
STATE="$NAME-cc-state"
WORK="$(mktemp -d)"
failures=0

cleanup() {
  docker rm -f "$NAME-time" "$NAME-cc" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  docker volume rm "$VOL" "$STATE" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT
fail() { echo "mcp-test: FAIL $*" >&2; failures=$((failures + 1)); }
ok() { echo "mcp-test: ok $*"; }

client() { # client URL [TOOL ARGS_JSON] -> the gateway client's JSON
  docker run --rm --network "$NET" --read-only --tmpfs /tmp --cap-drop ALL \
    --security-opt no-new-privileges:true \
    -v "$REPO_DIR/infra/mcp/selftest_client.py:/selftest_client.py:ro" \
    --entrypoint python "$CLIENT" /selftest_client.py "$@"
}
isolated() { # isolated CONTAINER LABEL: nothing outside its own network answers
  local c="$1" label="$2" target
  for target in 1.1.1.1:443 10.10.1.1:443 10.10.1.2:443 api:8000 postgres:5432 egress:8090; do
    if docker run --rm --network "container:$c" "$PROBE_IMAGE" nc -z -w 3 "${target%:*}" "${target#*:}" \
      >/dev/null 2>&1; then
      fail "$label reaches $target"
    fi
  done
  if docker exec "$c" sh -c 'touch /opt/probe' >/dev/null 2>&1; then fail "$label: the root is writable"; fi
  [[ "$(docker exec "$c" id -u)" == 10001 ]] || fail "$label does not run as uid 10001"
}
start() { # start NAME ALIAS IMAGE [docker run args...]
  local cname="$1" alias="$2" image="$3"
  shift 3
  docker run -d --name "$cname" --network "$NET" --network-alias "$alias" --read-only \
    --tmpfs /tmp:size=16m --cap-drop ALL --security-opt no-new-privileges:true \
    --user 10001:10001 "$@" "$image" >/dev/null
  local _try
  for _try in $(seq 1 30); do
    if docker run --rm --network "$NET" "$PROBE_IMAGE" nc -z -w 2 "$alias" 8080 >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  fail "$alias did not listen on :8080"
  docker logs "$cname" 2>&1 | tail -n 20 >&2
  return 1
}

docker network create --internal "$NET" >/dev/null

# ------------------------------------------------------------------- time --
if start "$NAME-time" mcp-time "coinepro-hq/mcp-time:$TAG"; then
  out="$(client http://mcp-time:8080/mcp get_current_time '{"timezone": "Asia/Tehran"}')"
  if jq -e '.tools == ["convert_time", "get_current_time"]' <<<"$out" >/dev/null; then
    ok "time lists get_current_time and convert_time"
  else
    fail "time lists $(jq -c .tools <<<"$out")"
  fi
  if jq -e '.call.is_error == false and (.call.text[0] | fromjson | .timezone == "Asia/Tehran"
            and (.datetime | endswith("+03:30")))' <<<"$out" >/dev/null; then
    ok "time tells Tehran's time (+03:30)"
  else
    fail "time's answer: $(jq -c .call <<<"$out")"
  fi
  isolated "$NAME-time" "mcp-time"
fi

# ------------------------------------------------------------- codecortex --
# A fixture: calc.py with its test, an unrelated module with its own; the
# "pr" branch changes calc.add only.
src="$WORK/src/coinepro-hub"
mkdir -p "$src/app" "$src/tests"
g() { git -C "$src" -c user.name=t -c user.email=t@example.invalid "$@"; }
g init -q -b main
printf 'def add(a, b):\n    return a + b\n' >"$src/app/calc.py"
printf 'def shout(s):\n    return s.upper()\n' >"$src/app/words.py"
printf 'from app.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n' >"$src/tests/test_calc.py"
printf 'from app.words import shout\n\n\ndef test_shout():\n    assert shout("a") == "A"\n' \
  >"$src/tests/test_words.py"
touch "$src/app/__init__.py"
g add -A && g commit -q -m base
g checkout -q -b pr
printf 'def add(a, b):\n    total = a + b\n    return total\n' >"$src/app/calc.py"
g commit -q -am "change add"
g checkout -q main
chmod -R a+rX "$WORK"

docker volume create "$VOL" >/dev/null && docker volume create "$STATE" >/dev/null
if docker run --rm --network none --read-only --tmpfs /tmp:size=64m --cap-drop ALL \
  --security-opt no-new-privileges:true --user 10001:10001 \
  -v "$WORK/src:/src:ro" -v "$VOL:/index" -v "$STATE:/index/coinepro-hub/.codecortex" \
  --entrypoint /opt/server/bin/python \
  "coinepro-hq/mcp-codecortex:$TAG" /opt/hq/index.py --full >"$WORK/index.json"; then
  ok "codecortex indexed the fixture: $(tr '\n' ' ' <"$WORK/index.json")"
else
  fail "the codecortex index job: $(cat "$WORK/index.json")"
fi
if start "$NAME-cc" mcp-codecortex "coinepro-hq/mcp-codecortex:$TAG" \
  -v "$VOL:/index:ro" -v "$STATE:/index/coinepro-hub/.codecortex"; then
  out="$(client http://mcp-codecortex:8080/mcp cortex_pr_intelligence \
    '{"base_ref": "origin/main", "head_ref": "origin/pr"}')" || out='{}'
  if jq -e '(.tools | index("cortex_pr_intelligence")) != null' <<<"$out" >/dev/null &&
    jq -e '.call.is_error == false and (.call.text[0] | fromjson | .affected_tests
            | (map(test("test_calc")) | any) and (map(test("test_words")) | any | not))' \
      <<<"$out" >/dev/null; then
    ok "codecortex PR intelligence names tests/test_calc.py and not tests/test_words.py"
  else
    fail "codecortex PR intelligence: $(jq -c '.call // .' <<<"$out" | cut -c1-600)"
    docker exec "$NAME-cc" cat /index/coinepro-hub/.codecortex/runtime/mcp-errors.jsonl 2>/dev/null |
      tail -n 3 | cut -c1-800 >&2 || true
  fi
  if docker exec "$NAME-cc" sh -c 'echo x > /index/coinepro-hub/app/calc.py' >/dev/null 2>&1; then
    fail "codecortex: the repository copy is writable"
  else
    ok "codecortex: the repository copy is read-only"
  fi
  isolated "$NAME-cc" "mcp-codecortex"
fi

if ((failures)); then
  echo "mcp-test: $failures failure(s)" >&2
  exit 1
fi
echo "mcp-test: all ok"
