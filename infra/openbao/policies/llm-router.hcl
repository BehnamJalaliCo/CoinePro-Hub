# llm-router: its own config/callers and the API keys of the connections.
path "kv/data/llm-router/*" {
  capabilities = ["read"]
}

path "kv/data/llm-connections/*" {
  capabilities = ["read"]
}
