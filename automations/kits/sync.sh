#!/usr/bin/env bash
# Copies a kit's source (this folder) over the workshop's copy, code and texts only: the fonts,
# environments and browsers there are kept. Run on the hub as the hub user (it uses sudo -u studio).
set -euo pipefail
kit="${1:?usage: sync.sh <kit>}"
src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$kit"
dst="/home/studio/kits/$kit"
[[ -d "$src" ]] || { echo "no kit $kit" >&2; exit 1; }
sudo -n -u studio mkdir -p "$dst"
tar -C "$src" -cf - . | sudo -n -u studio tar -C "$dst" -xf -
echo "synced $kit -> $dst"
