# syntax=docker/dockerfile:1.7
# The hub's Postgres (prompt 07 §1): the pinned pgvector image plus WAL-G
# (Apache-2.0) for continuous WAL archiving and point-in-time recovery to the
# bind-mounted /wal (/home/Hub/backups/wal, uid 999 = postgres, 0700).
FROM pgvector/pgvector:0.8.7-pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d

# WAL-G v3.0.9 (2026-08-20), the Ubuntu 22.04 build (glibc 2.35 <= bookworm's 2.36).
ADD --checksum=sha256:d6795c663894d836ba20840bffe8970aed81bbe25d3151bd4951f6f9c362def9 \
  https://github.com/wal-g/wal-g/releases/download/v3.0.9/wal-g-pg-22.04-amd64 /usr/local/bin/wal-g
RUN chmod 0755 /usr/local/bin/wal-g && /usr/local/bin/wal-g --version
