# hq-api (apps/api): its own config (agent token key, service token digests),
# the Web Push keys and the channels' credentials. The connections' API keys
# are write-only here: the owner sets them through the API (step-up), nobody
# reads them back.
path "kv/data/hq-api/*" {
  capabilities = ["read"]
}

path "kv/data/llm-connections/*" {
  capabilities = ["create", "update"]
}

# Holding service accounts (prompt 07 §2.5): read for one agent call at a time,
# handed to the egress service through the gateway; the owner writes them
# (make account-secret), never through the API.
path "kv/data/tools/accounts/*" {
  capabilities = ["read"]
}

# The customer pseudonym's HMAC key (prompt 10 §1.2): read only; made once by
# provision.sh (kv-once.sh, cas 0).
path "kv/data/support/pseudonym" {
  capabilities = ["read"]
}
