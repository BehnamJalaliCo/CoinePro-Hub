# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block of the rendered script sets them
# repo-clone: the company's repository in the work user's home. A read-only
# deploy key is made ON this server (its private half never leaves it); its
# public half goes to the hub for the owner to add to the repo. A public repo
# is cloned at once; a private one waits for that key (~/coinepro-clone.sh).
step_repo_clone() {
  local home="/home/$WORK_USER" name dest key
  key="$home/.ssh/coinepro_deploy"
  name="${REPO#*/}"
  dest="$home/$name"
  [[ -s "$key" ]] || runuser -u "$WORK_USER" -- ssh-keygen -q -t ed25519 -N '' \
    -C "coinepro-deploy@$(hostname)" -f "$key"
  # GitHub's published host key (pinned: no trust on first use).
  printf '%s\n' "$GITHUB_HOST_KEY" >"$home/.ssh/known_hosts"
  printf 'Host github.com\n  IdentityFile %s\n  IdentitiesOnly yes\n  StrictHostKeyChecking yes\n' \
    "$key" >"$home/.ssh/config"
  printf '#!/bin/sh\n# After the deploy key is on the repo (read-only):\nexec git clone git@github.com:%s.git %s\n' \
    "$REPO" "$dest" >"$home/coinepro-clone.sh"
  chmod 0700 "$home/coinepro-clone.sh"
  chmod 0600 "$home/.ssh/config"
  chown "$WORK_USER:$WORK_USER" "$home/.ssh/known_hosts" "$home/.ssh/config" "$home/coinepro-clone.sh"
  if [[ -d "$dest/.git" ]]; then
    result repo-clone 1 "" "already cloned in $dest"
  elif runuser -u "$WORK_USER" -- env GIT_TERMINAL_PROMPT=0 \
    git clone --quiet "https://github.com/$REPO.git" "$dest" 2>/dev/null; then
    result repo-clone 1 "" "public repository cloned in $dest"
  else
    result repo-clone 1 "" "waiting for the deploy key: add it to the repo (read-only), then run ~/coinepro-clone.sh"
  fi
}
