# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block of the rendered script sets them
# private-network: the provisioner attached the server to the company's own
# Hetzner network (never an existing one); here: is the address up?
step_private_network() {
  local ip="" i
  for ((i = 0; i < WAIT_S; i++)); do
    ip="$(private_ip)"
    [[ -n "$ip" ]] && ip -4 addr show | grep -F " $ip/" >/dev/null && break
    sleep 1
  done
  if [[ -z "$ip" ]]; then
    result private-network 0 "" "no private address in the metadata"
    return 1
  fi
  if ip -4 addr show | grep -F " $ip/" >/dev/null; then
    result private-network 1 "$ip" "up"
  else
    result private-network 1 "$ip" "attached; not on an interface yet (cloud-init configures it)"
  fi
}
