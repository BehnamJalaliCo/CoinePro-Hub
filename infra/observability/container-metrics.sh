#!/usr/bin/env bash
# Per-container metrics without giving any container the Docker socket
# (prompt 05 §11: cAdvisor and its docker.sock are out of the default
# profiles). Runs on the host as Hub every 30 s (coinepro-hq-container-metrics.timer)
# and writes node-exporter's textfile collector format:
#   hq_container_up{service,oneshot}       1 running, 0 otherwise (oneshot: a job)
#   hq_container_memory_bytes{service}     memory in use (docker stats, cache excluded)
#   hq_container_memory_limit_bytes{service}
#   hq_container_cpu_percent{service}
#   hq_container_restarts_total{service,oneshot}   Docker's restart count
#   hq_container_network_{receive,transmit}_bytes_total{service}
# Only the coinepro-hq project's containers; nothing else of the host.
set -euo pipefail

OUT_DIR="${HQ_TEXTFILE_DIR:-/var/lib/coinepro-hq/textfile}"
PROJECT=coinepro-hq
tmp="$(mktemp "$OUT_DIR/.containers.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

mapfile -t ids < <(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT")
{
  echo "# HELP hq_container_up 1 when the container is running."
  echo "# TYPE hq_container_up gauge"
  echo "# HELP hq_container_memory_bytes Memory in use (cache excluded), docker stats."
  echo "# TYPE hq_container_memory_bytes gauge"
  echo "# HELP hq_container_memory_limit_bytes Memory limit of the container."
  echo "# TYPE hq_container_memory_limit_bytes gauge"
  echo "# HELP hq_container_cpu_percent CPU use in percent of one core, docker stats."
  echo "# TYPE hq_container_cpu_percent gauge"
  echo "# HELP hq_container_restarts_total Restarts counted by Docker."
  echo "# TYPE hq_container_restarts_total counter"
  echo "# HELP hq_container_network_receive_bytes_total Bytes received, docker stats."
  echo "# TYPE hq_container_network_receive_bytes_total counter"
  echo "# HELP hq_container_network_transmit_bytes_total Bytes sent, docker stats."
  echo "# TYPE hq_container_network_transmit_bytes_total counter"
  if ((${#ids[@]})); then
    docker inspect "${ids[@]}" | jq -r '.[] |
      (.Config.Labels["com.docker.compose.service"] // "unknown") as $s |
      (if .HostConfig.RestartPolicy.Name == "no" then "true" else "false" end) as $o |
      "hq_container_up{service=\"\($s)\",oneshot=\"\($o)\"} \(if .State.Running then 1 else 0 end)",
      "hq_container_restarts_total{service=\"\($s)\",oneshot=\"\($o)\"} \(.RestartCount)"'
    running="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT")"
    if [[ -n "$running" ]]; then
      # shellcheck disable=SC2086 # one id per word
      docker stats --no-stream --format '{{json .}}' $running | jq -rs '
        def bytes: capture("^(?<n>[0-9.]+)(?<u>[A-Za-z]*)$") |
          (.n | tonumber) * ({"B":1,"kB":1e3,"KiB":1024,"MB":1e6,"MiB":1048576,"GB":1e9,"GiB":1073741824}[.u] // 1) | floor;
        .[] | (.Name | sub("^coinepro-hq-"; "") | sub("-[0-9]+$"; "")) as $s |
        (.MemUsage | split(" / ")) as $m |
        "hq_container_memory_bytes{service=\"\($s)\"} \($m[0] | bytes)",
        "hq_container_memory_limit_bytes{service=\"\($s)\"} \($m[1] | bytes)",
        (.NetIO | split(" / ")) as $n |
        "hq_container_cpu_percent{service=\"\($s)\"} \(.CPUPerc | rtrimstr("%") | tonumber)",
        "hq_container_network_receive_bytes_total{service=\"\($s)\"} \($n[0] | bytes)",
        "hq_container_network_transmit_bytes_total{service=\"\($s)\"} \($n[1] | bytes)"'
    fi
  fi
} >"$tmp"
chmod 644 "$tmp"
mv "$tmp" "$OUT_DIR/containers.prom"
trap - EXIT
