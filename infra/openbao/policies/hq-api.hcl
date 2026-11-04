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

# Prompt 21 part 3 (contract §29.12): a company's growth connection secret
# (kv/hq/growth/<company>/<kind>), write-only here: the owner sets it through
# the API (step-up) or `make growth-secret`; only the worker reads it.
path "kv/data/hq/growth/*" {
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

# Prompt 10 §9: the intake sources' HMAC secrets and the Telegram channels'
# webhook secret tokens, read to check a webhook (make intake-secret, make
# telegram-bot-token: the owner's terminal, never the API).
path "kv/data/support/intake/*" {
  capabilities = ["read"]
}

path "kv/data/support/telegram/*" {
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

# Prompt 22 part 3 (contract §31.3): the hub's Listmonk API user (key `user`, `token`), read
# for one call at a time; the owner writes it (make newsletter-secret), never the API.
path "kv/data/hq/newsletter/api" {
  capabilities = ["read"]
}

# Prompt 22 (contract §30.4): the HMAC secret shared with n8n (kv/hq/n8n, key
# `secret`), read only; written by `make n8n-secret` in the owner's terminal.
# The callback's signature is checked with it.
path "kv/data/hq/n8n" {
  capabilities = ["read"]
}

# Prompt 23 (contract §32.5): the voice layer's provider key (kv/hq/voice/<provider>, key
# secret), WRITE-ONLY here: the owner gives it in the talk chat (step-up voice.secret) and the api
# never reads it back. Only the worker reads it, for one provider call at a time.
path "kv/data/hq/voice/*" {
  capabilities = ["create", "update"]
}
