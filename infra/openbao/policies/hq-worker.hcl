# hq-worker (apps/api worker): the push channels' credentials, and - as the
# agent runtime (prompt 05) - the agent token key (it mints one hqa1 token per
# run) and its own tokens for llm-router and the Tool Gateway.
path "kv/data/hq-api/webpush" {
  capabilities = ["read"]
}

path "kv/data/hq-api/channels/*" {
  capabilities = ["read"]
}

path "kv/data/hq-api/config" {
  capabilities = ["read"]
}

path "kv/data/hq-agents/runtime" {
  capabilities = ["read"]
}

# The customer pseudonym's HMAC key (prompt 10 §1.2): read only; made once by
# provision.sh (kv-once.sh, cas 0).
path "kv/data/support/pseudonym" {
  capabilities = ["read"]
}
