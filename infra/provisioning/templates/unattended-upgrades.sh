# shellcheck shell=bash
# unattended-upgrades: security updates every day, on their own.
step_unattended_upgrades() {
  apt_get install unattended-upgrades
  cat >/etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF
  systemctl enable --now unattended-upgrades.service
  result unattended-upgrades 1 "$(pkg_version unattended-upgrades)" "security updates every day"
}
