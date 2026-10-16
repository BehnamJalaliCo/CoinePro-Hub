#!/usr/bin/env bash
# No port may be published on anything but 127.0.0.1, except Caddy's 80/443.
# Host networking is allowed only for node-exporter, bound to a specific IP.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_env

failed=0
for profile in "${PROFILES[@]}"; do
  model="$(compose_json "$profile")"

  bad_ports="$(jq -r '
    .services | to_entries[] | .key as $svc | (.value.ports // [])[]
    | select(.published != null)
    | select((.host_ip // "") != "127.0.0.1")
    | select(($svc == "caddy" and (.published == "80" or .published == "443")) | not)
    | "\($svc) publishes \(.host_ip // "0.0.0.0"):\(.published)/\(.protocol // "tcp")"' <<<"$model")"

  bad_host="$(jq -r '
    .services | to_entries[] | select(.value.network_mode == "host") | .key as $svc
    | if $svc != "node-exporter" then "\($svc) uses the host network"
      elif ([.value.command[]? | select(test("^--web.listen-address=[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+:"))
             | select(test("=0\\.0\\.0\\.0:") | not)] | length) == 0
        then "\($svc) on the host network must listen on a specific IP"
      else empty end' <<<"$model")"

  if [[ -n "$bad_ports$bad_host" ]]; then
    printf 'ports: %s: %s\n' "$profile" "$bad_ports" "$profile" "$bad_host" | grep -v ': $' >&2
    failed=1
  else
    echo "ports: $profile ok (only caddy 80/443 public)"
  fi
done
exit "$failed"
