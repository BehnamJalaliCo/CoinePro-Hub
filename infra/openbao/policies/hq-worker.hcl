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

# The worker's own api service token for the connector calls of the revenue
# pulls (prompt 10 §2.2): made once by provision.sh.
path "kv/data/hq-agents/connector" {
  capabilities = ["read"]
}

# Prompt 10 §4.2: a support channel's bot token, read for one send and handed
# to egress only (make telegram-bot-token, the owner's terminal); Chatwoot's
# token is a holding service account (make account-secret).
path "kv/data/support/telegram/*" {
  capabilities = ["read"]
}

path "kv/data/tools/accounts/*" {
  capabilities = ["read"]
}

# Prompt 21 part 3 (contract §29.12): the growth connections' secrets, read for
# one daily read at a time and handed to egress only (the call's account).
path "kv/data/hq/growth/*" {
  capabilities = ["read"]
}

# Prompt 14 §3: the archive's `secret` files (envelope encryption). A data key
# for one file and the decryption of a stored one; nothing else of transit
# (no key read, no export, no rotation): the key never leaves OpenBao.
path "transit/datakey/plaintext/archive-secret" {
  capabilities = ["update"]
}

path "transit/decrypt/archive-secret" {
  capabilities = ["update"]
}

# Prompt 22 (contract §30.4): the HMAC secret shared with n8n (kv/hq/n8n, key
# `secret`), read only; written by `make n8n-secret` in the owner's terminal.
# A step's webhook call is signed with it.
path "kv/data/hq/n8n" {
  capabilities = ["read"]
}

# Prompt 22 part 3 (contract §31.3): the hub's Listmonk API user (key `user`, `token`), read
# for one call at a time; the owner writes it (make newsletter-secret), never the API.
path "kv/data/hq/newsletter/api" {
  capabilities = ["read"]
}
