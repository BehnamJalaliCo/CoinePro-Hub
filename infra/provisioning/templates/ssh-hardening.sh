# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block of the rendered script sets them
# ssh-hardening: keys only, no root login, no passwords, the work user only.
# Runs after work-user (a failed work-user stops the build before this step).
step_ssh_hardening() {
  cat >/etc/ssh/sshd_config.d/10-coinepro.conf <<CONF
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AuthenticationMethods publickey
AllowUsers $WORK_USER
X11Forwarding no
MaxAuthTries 3
CONF
  chmod 0644 /etc/ssh/sshd_config.d/10-coinepro.conf
  install -d -m 0755 /run/sshd
  sshd -t
  passwd -l root >/dev/null 2>&1 || true
  rm -f /root/.ssh/authorized_keys
  systemctl reload ssh 2>/dev/null || systemctl restart ssh
  result ssh-hardening 1 "$(ssh -V 2>&1 | cut -d, -f1)" "keys only, no root login, no passwords"
}
