"""Prompt 19.2: reading a sensitive file is not a change (owner's seal card, 2026-11-01).

The owner was asked to seal `cat /etc/passwd 2>&1; ... sudo -n ls ... | head -40` as an
access change: `2>&1` split the line at its `&`, and `sudo -n` swallowed the command after it.
Pure function: no database.
"""

from __future__ import annotations

import pytest

from hq_api.domain.server_classify import classify

READS = [
    'echo "=== users with shells ==="; cat /etc/passwd 2>&1; echo; '
    'echo "=== spool crontabs ==="; ls -la /var/spool/cron/crontabs/ 2>&1; '
    "sudo -n ls -la /var/spool/cron/crontabs/ 2>&1 | head -40",
    "grep root /etc/passwd",
    "sudo -n cat /etc/ssh/sshd_config",
    "sudo -u root head -5 /etc/group 2>/dev/null",
    "cat /etc/passwd >&2",
]
WRITES = [
    ("echo x >> /etc/passwd", "access_change"),
    ("sed -i s/a/b/ /etc/passwd 2>&1", "access_change"),
    ("sudo -n tee -a /etc/sudoers < x", "access_change"),
    ("useradd bob 2>&1", "access_change"),
    ("ls 2>&1 && rm -rf /var/lib/docker", "volume_delete"),
]


@pytest.mark.parametrize("cmd", READS)
def test_reading_a_sensitive_file_runs_free(cmd: str) -> None:
    assert classify(cmd) is None


@pytest.mark.parametrize(("cmd", "category"), WRITES)
def test_writing_one_still_waits_for_the_seal(cmd: str, category: str) -> None:
    assert classify(cmd) == category
