# backup-snapshot (prompt 07 §1): the ONLY capability of the token the owner
# creates for the hourly OpenBao raft snapshot. The server never creates this
# token; the owner does, then stores it with `make openbao-snapshot-token`.
path "sys/storage/raft/snapshot" {
  capabilities = ["read"]
}
# 7.1 §2.2: the hourly backup renews the token after every snapshot (a
# periodic token lapses after its period unused) and may read its own lease.
# Both concern the token itself only (also in the default policy).
path "auth/token/renew-self" {
  capabilities = ["update"]
}
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
