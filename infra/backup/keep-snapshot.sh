#!/usr/bin/env bash
# infra/backup/keep-snapshot.sh SNAPSHOT TAG (prompt 16 §1.2): keep one hourly
# snapshot out of the retention for good. Retention (hourly.sh's forget) and
# the off-site copy only look at the tag `hourly`: here it is replaced by TAG,
# in the local repository and in its Google Drive copy (found by the id it was
# copied from). restic writes a re-tagged snapshot under a new id; the ids it
# ends with are printed, one line per repository ("local <id>", "gdrive <id>").
# Nothing is deleted; the password stays in OpenBao (restic-lib.sh).
set -euo pipefail

BLOG_NAME="keep-snapshot"
# shellcheck source=restic-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/restic-lib.sh"

SNAP="${1:-}"
TAG="${2:-}"
if [[ ! "$SNAP" =~ ^[0-9a-f]{8,64}$ || ! "$TAG" =~ ^[a-z0-9-]{3,40}$ || "$TAG" == hourly ]]; then
  echo "usage: keep-snapshot.sh SNAPSHOT TAG (TAG is not hourly)" >&2
  exit 2
fi
LOCAL_REPO=/restic/repo

umask 077
trap secrets_cleanup EXIT
compose_facts
load_secrets || { echo "keep-snapshot: secrets unavailable: $LOAD_ERROR" >&2; exit 1; }

kept() { # kept NETWORK REPO -> the id of the snapshot that came from $full, once tagged TAG
  # (a re-tagged snapshot keeps the id it first came from: the local one's,
  # in the Drive copy too)
  brestic "$1" -- -r "$2" snapshots --json --tag "$TAG" |
    jq -r --arg o "$full" '[.[] | select(.id == $o or .original == $o)] | last | .id // empty'
}
retag() { # retag NETWORK REPO ID -> the snapshot's new id (already kept: the same one)
  local id
  id="$(kept "$1" "$2")" || return 1
  if [[ -z "$id" ]]; then
    brestic "$1" -- -r "$2" tag --add "$TAG" --remove hourly "$3" --quiet >/dev/null || return 1
    id="$(kept "$1" "$2")" || return 1
  fi
  printf '%s' "$id"
}

full="$(brestic none -- -r "$LOCAL_REPO" snapshots --json "$SNAP" | jq -r '.[0].id // empty')"
[[ -n "$full" ]] || { echo "keep-snapshot: no snapshot $SNAP in the local repository" >&2; exit 1; }
remote=""
if [[ "$GDRIVE_CONFIGURED" == true ]]; then
  # the Drive copy names the local snapshot it came from
  remote="$(brestic bridge -- -r "$GDRIVE_REPO" snapshots --json |
    jq -r --arg o "$full" '[.[] | select(.original == $o)] | last | .id // empty')"
  [[ -n "$remote" ]] || { echo "keep-snapshot: $SNAP is not in Google Drive yet" >&2; exit 1; }
fi
new="$(retag none "$LOCAL_REPO" "$full")"
[[ -n "$new" ]] || { echo "keep-snapshot: the local re-tag is not visible" >&2; exit 1; }
echo "local $new"
if [[ -n "$remote" ]]; then
  new_remote="$(retag bridge "$GDRIVE_REPO" "$remote")"
  [[ -n "$new_remote" ]] || { echo "keep-snapshot: the Drive re-tag is not visible" >&2; exit 1; }
  echo "gdrive $new_remote"
fi
blog "kept $full as $TAG (local $new${remote:+, gdrive $new_remote})" >&2
