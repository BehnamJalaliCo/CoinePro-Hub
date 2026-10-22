# The provisioner (prompt 09 §4): reads, at the moment of work, the owner's
# Hetzner API token and public SSH keys (written by the owner himself:
# make hetzner-token, make owner-ssh-key) and its own api token. No write,
# no list, nothing else.
path "kv/data/provisioning/hetzner" {
  capabilities = ["read"]
}

path "kv/data/provisioning/ssh-keys" {
  capabilities = ["read"]
}

path "kv/data/provisioner/config" {
  capabilities = ["read"]
}

# Its short logins end at once after the read.
path "auth/token/revoke-self" {
  capabilities = ["update"]
}
