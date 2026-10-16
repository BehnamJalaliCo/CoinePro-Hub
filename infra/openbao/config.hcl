# CoinePro HQ — OpenBao server, integrated (raft) storage, single node.
ui = true

api_addr     = "http://openbao:8200"
cluster_addr = "https://openbao:8201"

storage "raft" {
  path    = "/openbao/file"
  node_id = "hq-openbao-1"
}

# Plain HTTP is acceptable only because the API is reachable solely from
# hq-internal and 127.0.0.1. Switch on TLS before any other host talks to it.
listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"
  tls_disable     = true

  telemetry {
    unauthenticated_metrics_access = true
  }
}

telemetry {
  prometheus_retention_time = "24h"
  disable_hostname          = true
}
