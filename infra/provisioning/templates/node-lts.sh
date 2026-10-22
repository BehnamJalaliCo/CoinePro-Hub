# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block of the rendered script sets them
# node-lts: the official Node.js LTS build from nodejs.org, its sha256 pinned.
# A tarball whose sha256 is not the pinned one is never unpacked or run.
step_node_lts() {
  local arch sha dir b
  case "$(uname -m)" in
    x86_64) arch=x64 sha="$NODE_SHA256_X64" ;;
    aarch64) arch=arm64 sha="$NODE_SHA256_ARM64" ;;
    *) log "node-lts: no build for $(uname -m)"; return 1 ;;
  esac
  dir="node-v$NODE_VERSION-linux-$arch"
  curl -fsSL "https://nodejs.org/dist/v$NODE_VERSION/$dir.tar.xz" -o "$STATE/node.tar.xz"
  if ! echo "$sha  $STATE/node.tar.xz" | sha256sum -c --quiet - >/dev/null 2>&1; then
    rm -f "$STATE/node.tar.xz"
    log "node-lts: the tarball's sha256 is not the pinned one; nothing unpacked"
    return 1
  fi
  install -d -m 0755 /usr/local/lib/nodejs
  tar -xJf "$STATE/node.tar.xz" -C /usr/local/lib/nodejs
  rm -f "$STATE/node.tar.xz"
  ln -sfn "/usr/local/lib/nodejs/$dir" /usr/local/lib/nodejs/current
  for b in node npm npx; do ln -sfn "/usr/local/lib/nodejs/current/bin/$b" "/usr/local/bin/$b"; done
  result node-lts 1 "$(node --version)" "nodejs.org build, sha256 checked"
}
