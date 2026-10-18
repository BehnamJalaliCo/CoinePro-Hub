# syntax=docker/dockerfile:1.7
# The one-shot backup tools (prompt 07 §1): restic (BSD-2) for encrypted,
# deduplicated snapshots and rclone (MIT) as its Google Drive / S3 backend.
FROM rclone/rclone:1.75.2@sha256:2687085f718d3c628f7fdfb77c52a1d344332aed543110bb88088f2c70d43eb5

# restic v0.19.1 (2026-07-05), checked against the release's SHA256SUMS.
ADD --checksum=sha256:f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c \
  https://github.com/restic/restic/releases/download/v0.19.1/restic_0.19.1_linux_amd64.bz2 /tmp/restic.bz2
RUN bunzip2 -c /tmp/restic.bz2 >/usr/local/bin/restic && rm /tmp/restic.bz2 \
  && chmod 0755 /usr/local/bin/restic && restic version
# The scripts name the program to run (restic | rclone | sh).
ENTRYPOINT []
CMD ["restic", "version"]
