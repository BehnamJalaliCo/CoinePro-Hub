#!/usr/bin/env bash
# Copies a kit's source (this folder) over the workshop's copy, code and texts only: the fonts,
# environments and browsers there are kept. Run on the hub as the hub user (it uses sudo -u studio).
# ⟨2026-11-17⟩ A kit with a topic bank (topics.md + tools/topic.py, e.g. ipoxxo-reels) keeps the
# workshop's status column: the sessions mark the topics they take there, so every status that is
# not «free» survives a sync (new rows from the source arrive as they are).
set -euo pipefail
kit="${1:?usage: sync.sh <kit>}"
src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$kit"
dst="/home/studio/kits/$kit"
[[ -d "$src" ]] || { echo "no kit $kit" >&2; exit 1; }
sudo -n -u studio mkdir -p "$dst"
bank=""
if [[ -f "$src/topics.md" && -f "$src/tools/topic.py" ]] && sudo -n -u studio test -f "$dst/topics.md"; then
  bank="$(mktemp)"
  sudo -n -u studio cat "$dst/topics.md" > "$bank"
fi
tar -C "$src" --exclude=./topics.md.lock ${bank:+--exclude=./topics.md} -cf - . | sudo -n -u studio tar -C "$dst" -xf -
if [[ -n "$bank" ]]; then
  python3 -I "$src/tools/topic.py" merge "$bank" --file "$src/topics.md" | sudo -n -u studio tee "$dst/topics.md.new" >/dev/null
  sudo -n -u studio mv "$dst/topics.md.new" "$dst/topics.md"
  rm -f "$bank"
  echo "kept the workshop's topic statuses: $(sudo -n -u studio grep -cE '^\| [0-9]+ \| (used:|taken|sample:)' "$dst/topics.md") not free"
fi
echo "synced $kit -> $dst"
