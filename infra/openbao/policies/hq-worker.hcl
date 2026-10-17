# hq-worker (apps/api worker): only what the push channels need.
path "kv/data/hq-api/webpush" {
  capabilities = ["read"]
}

path "kv/data/hq-api/channels/*" {
  capabilities = ["read"]
}
