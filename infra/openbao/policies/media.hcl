# The render worker's courier (prompt 13 §2.3): reads its own api token at the
# start of a pass (service principal "media": /internal/v1/media/render only).
# No write, no list, nothing else. The renderer itself has no network and no
# credential at all.
path "kv/data/media/config" {
  capabilities = ["read"]
}

# Its short logins end at once after the read.
path "auth/token/revoke-self" {
  capabilities = ["update"]
}
