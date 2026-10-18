# backup-snapshot (prompt 07 §1): the ONLY capability of the token the owner
# creates for the hourly OpenBao raft snapshot. The server never creates this
# token; the owner does, then stores it with `make openbao-snapshot-token`.
path "sys/storage/raft/snapshot" {
  capabilities = ["read"]
}
