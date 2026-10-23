# hq-admin: day-to-day administration without the root token
# (secrets, policies, AppRoles, mounts). Not allowed: seal/unseal keys,
# raft membership, audit devices, or creating root tokens.
path "kv/*" {
  capabilities = ["create", "read", "update", "patch", "delete", "list"]
}

path "sys/policies/acl" {
  capabilities = ["list"]
}

path "sys/policies/acl/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "sys/mounts" {
  capabilities = ["read"]
}

path "sys/mounts/*" {
  capabilities = ["create", "read", "update"]
}

path "sys/auth" {
  capabilities = ["read"]
}

path "sys/auth/*" {
  capabilities = ["create", "read", "update", "sudo"]
}

# Prompt 14 §3: provision.sh creates the archive's transit key once and keeps
# it undeletable; no export, backup, rotation or delete path is granted.
path "transit/keys/archive-secret" {
  capabilities = ["create", "read", "update"]
}

path "transit/keys/archive-secret/config" {
  capabilities = ["update"]
}

path "auth/approle/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "sys/storage/raft/snapshot" {
  capabilities = ["read"]
}

path "sys/health" {
  capabilities = ["read"]
}
