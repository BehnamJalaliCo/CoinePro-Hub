# shellcheck shell=bash
# node-exporter: host metrics for the hub, on the PRIVATE address only.
step_node_exporter() {
  local ip
  ip="$(private_ip)"
  if [[ -z "$ip" ]]; then
    log "node-exporter: no private address; it is never exposed on a public one"
    return 1
  fi
  apt_get install prometheus-node-exporter
  printf 'ARGS="--web.listen-address=%s:9100"\n' "$ip" >/etc/default/prometheus-node-exporter
  systemctl restart prometheus-node-exporter
  result node-exporter 1 "$(pkg_version prometheus-node-exporter)" "listens on $ip:9100 only"
}
