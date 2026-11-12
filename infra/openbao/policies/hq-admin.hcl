# hq-admin: day-to-day administration without the root token (secrets,
# policies, AppRoles, mounts). provision.sh runs as this token on every
# `make up` and rewrites every policy in this directory, hq-admin included.
#
# This is NOT an isolation boundary: whoever can write ACL policies and
# AppRoles can grant themselves anything. The token may rewrite any policy
# (its own too) to `path "*"` with sudo, bind an AppRole to it and log in,
# and so reach seal, raft membership, audit devices or sys/generate-root.
# No path here grants those directly, but the token is as strong as root in
# practice; protect openbao-admin.token like the root token (it lives next
# to it, in $HQ_SECRETS_DIR, 600). Narrowing the policy and AppRole paths
# would not close this: a named policy can still be rewritten to `path "*"`.
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
