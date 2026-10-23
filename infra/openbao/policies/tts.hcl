# The TTS one-shot (prompt 12 §4): reads its own api token at the start of a
# pass (service principal "tts": /internal/v1/tts/claim and /done only). No
# write, no list, nothing else.
path "kv/data/tts/config" {
  capabilities = ["read"]
}

# Its short logins end at once after the read.
path "auth/token/revoke-self" {
  capabilities = ["update"]
}
