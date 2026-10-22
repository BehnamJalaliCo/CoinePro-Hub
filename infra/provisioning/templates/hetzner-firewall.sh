# shellcheck shell=bash
# hetzner-firewall: the Hetzner Cloud Firewall is made and attached by the
# provisioner (Hetzner side); nothing to do on the server.
step_hetzner_firewall() {
  result hetzner-firewall 1 "" "Hetzner Cloud Firewall attached by the provisioner"
}
