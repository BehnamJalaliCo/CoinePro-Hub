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
