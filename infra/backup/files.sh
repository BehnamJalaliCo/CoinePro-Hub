#!/usr/bin/env bash
# Helpers for the api's file volume (hq-files) in the backup set. Sourced by
# backup.sh and restore-test.sh. Every step runs in a throwaway busybox
# container (the hq-tools image) without network; file contents never pass
# through the host's shell.

# files_archive <volume> <image> <out.tar.gz> <out.sha256>
files_archive() {
  docker run --rm --network none -v "$1:/data:ro" "$2" sh -c 'cd /data && tar -czf - .' >"$3"
  docker run --rm --network none -v "$1:/data:ro" "$2" \
    sh -c 'cd /data && find . -type f -exec sha256sum {} + | sort -k2' >"$4"
}

# files_restore_verify <archive.tar.gz> <sums> <volume> <image>
# Extracts the archive into the (empty) volume and checks every file's sha256.
files_restore_verify() {
  docker run --rm -i --network none -v "$3:/data" "$4" sh -c 'cd /data && tar -xzf -' <"$1"
  docker run --rm -i --network none -v "$3:/data:ro" "$4" sh -c 'cd /data && sha256sum -c -s -' <"$2"
}
