# hq-backup (prompt 07 §1): the host's backup scripts (infra/backup, user Hub)
# read the restic repository password, the Google Drive token, the optional
# Hetzner bucket keys and the owner's OpenBao snapshot-only token. Nothing else.
path "kv/data/backup/*" {
  capabilities = ["read"]
}
