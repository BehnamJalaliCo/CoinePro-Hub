# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block of the rendered script sets them
# claude-code: Anthropic's official package, the pinned version, for the work
# user only. Nothing logs in: the owner runs `claude` and logs into their own
# account. No token from the hub ever comes here.
step_claude_code() {
  runuser -l "$WORK_USER" -c "npm config set prefix \"\$HOME/.npm-global\" &&
    npm install -g --no-fund --no-audit @anthropic-ai/claude-code@$CLAUDE_CODE_VERSION"
  local profile="/home/$WORK_USER/.profile" version
  # shellcheck disable=SC2016  # $HOME and $PATH are for the user's shell, not now
  grep -qF '.npm-global/bin' "$profile" 2>/dev/null ||
    printf '\nexport PATH="$HOME/.npm-global/bin:$PATH"\n' >>"$profile"
  chown "$WORK_USER:$WORK_USER" "$profile"
  # shellcheck disable=SC2016  # expanded by the work user's login shell
  version="$(runuser -l "$WORK_USER" -c '"$HOME/.npm-global/bin/claude" --version' | head -1)"
  result claude-code 1 "$version" "for $WORK_USER; log in yourself: claude"
}
