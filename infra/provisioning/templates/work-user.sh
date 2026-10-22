# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block of the rendered script sets them
# work-user: the owner's working user, made NEW by this build, with the
# owner's PUBLIC key(s) only; no password at all (locked); sudo with the key
# (the owner's default). An account that already exists is never taken over
# (it may be a system account): the step fails, unless this build made it on
# an earlier try (the marker it wrote in $STATE says so).
step_work_user() {
  local made="$STATE/work-user.created"
  if id "$WORK_USER" >/dev/null 2>&1; then
    if [[ "$(cat "$made" 2>/dev/null)" != "$WORK_USER" ]]; then
      log "work-user: $WORK_USER already exists on this server and this build did not make it"
      return 1
    fi
    log "work-user: $WORK_USER was made by this build on an earlier try"
  else
    useradd --create-home --shell /bin/bash --user-group "$WORK_USER"
    printf '%s' "$WORK_USER" >"$made"
  fi
  passwd -l "$WORK_USER" >/dev/null
  local home="/home/$WORK_USER"
  install -d -m 0700 -o "$WORK_USER" -g "$WORK_USER" "$home/.ssh"
  printf '%s\n' "$OWNER_KEYS" >"$home/.ssh/authorized_keys"
  chown "$WORK_USER:$WORK_USER" "$home/.ssh/authorized_keys"
  chmod 0600 "$home/.ssh/authorized_keys"
  local sudoers="/etc/sudoers.d/90-coinepro-$WORK_USER"
  printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$WORK_USER" >"$sudoers.tmp"
  chmod 0440 "$sudoers.tmp"
  if ! visudo -cqf "$sudoers.tmp"; then
    rm -f "$sudoers.tmp"
    log "work-user: visudo refuses the sudoers line; nothing installed"
    return 1
  fi
  mv "$sudoers.tmp" "$sudoers"
  result work-user 1 "" "$WORK_USER: the owner's key(s), sudo with the key, no password"
}
