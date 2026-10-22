# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block of the rendered script sets them
# docker: Docker Engine from Docker's official apt repository; the signing
# key's fingerprint is checked against the pinned one before apt trusts it.
step_docker() {
  apt_get install ca-certificates curl gnupg
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o "$STATE/docker.asc"
  local gh="$STATE/gnupg" fpr codename
  install -d -m 0700 "$gh"
  fpr="$(GNUPGHOME="$gh" gpg --show-keys --with-colons "$STATE/docker.asc" | awk -F: '/^fpr/ && !n++ {print $10}')"
  if [[ "$fpr" != "$DOCKER_KEY_FPR" ]]; then
    log "docker: the signing key's fingerprint is not the pinned one"
    return 1
  fi
  GNUPGHOME="$gh" gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg "$STATE/docker.asc"
  chmod 0644 /etc/apt/keyrings/docker.gpg
  # shellcheck source=/dev/null  # the new server's own release file
  codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu %s stable\n' \
    "$(dpkg --print-architecture)" "$codename" >/etc/apt/sources.list.d/docker.list
  apt_get update
  apt_get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  usermod -aG docker "$WORK_USER"
  result docker 1 "$(docker --version | cut -d' ' -f3 | tr -d ,)" "official repository; $WORK_USER in group docker"
}
