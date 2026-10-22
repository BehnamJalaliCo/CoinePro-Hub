# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block of the rendered script sets them
# system-upgrade: every package up to date before anything else. If the new
# kernel or libc needs it, THIS new server reboots once, during its build only,
# and coinepro-provision.service finishes the remaining steps after the boot.
# The step asks for that reboot with its exit code (REBOOT_RC); run_step reboots.
step_system_upgrade() {
  apt_get update
  apt_get full-upgrade
  apt_get autoremove
  if [[ -e /var/run/reboot-required && ! -e "$STATE/rebooted" ]]; then
    cat >/etc/systemd/system/coinepro-provision.service <<'UNIT'
[Unit]
Description=CoinePro HQ: finish provisioning after the build's reboot
After=network-online.target cloud-final.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/coinepro-provision

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable coinepro-provision.service
    touch "$STATE/rebooted"
    result system-upgrade 1 "$(uname -r)" "upgraded; this new server rebooted once to continue"
    return "$REBOOT_RC"
  fi
  result system-upgrade 1 "$(uname -r)" "upgraded"
}
