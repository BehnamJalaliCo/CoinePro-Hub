# claude-runtime: only its own config and the Claude subscription token.
path "kv/data/claude-runtime/*" {
  capabilities = ["read"]
}
