"""Prompt 19.2: reading a sensitive file is not a change (owner's seal card, 2026-11-01).

The owner was asked to seal `cat /etc/passwd 2>&1; ... sudo -n ls ... | head -40` as an
access change: `2>&1` split the line at its `&`, and `sudo -n` swallowed the command after it.
Pure function: no database.
"""

from __future__ import annotations

import pytest

from hq_api.domain.server_classify import classify, classify_path

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


# Audit 2026-11-11: a destructive command inside a wrapper (a shell's -c, su -c, eval, flock -c,
# docker exec …) skipped the owner's seal; so did a few spellings of the plain forms.
WRAPPED = [
    ('su -c "rm -rf /var/lib/docker"', "volume_delete"),
    ('su - postgres -c "dropdb prod"', "db_drop"),
    ('sudo bash -c "rm -rf /var/lib/postgresql"', "volume_delete"),
    ('sh -c "mkfs.ext4 /dev/sdb"', "disk_wipe"),
    ("bash -c 'dropdb x'", "db_drop"),
    ("bash -lc 'rm \"$1\"' _ /srv/backups/x.sql.gz", "backup_delete"),
    ('eval "userdel bob"', "access_change"),
    ('flock /tmp/l -c "rm -rf /srv/backups"', "backup_delete"),
    ("flock -n /tmp/l rm -rf /var/lib/docker", "volume_delete"),
    ("xargs -n 1 rm -rf /var/lib/docker", "volume_delete"),
    ("timeout -s KILL 10 rm -rf /", "disk_wipe"),
    ("docker exec pg rm -rf /var/lib/postgresql/data", "volume_delete"),
    ('docker exec -it -u root pg sh -c "rm -rf /var/lib/postgresql/data"', "volume_delete"),
    ("docker compose -f x.yml exec -T db rm -rf /var/lib/postgresql/data", "volume_delete"),
    ("kubectl exec -it pod -- rm -rf /var/lib/postgresql/data", "volume_delete"),
    ("docker rm --volumes db", "volume_delete"),
    ("service ssh stop", "access_change"),
    ("systemctl --now disable ssh", "access_change"),
    ('find /etc/ssh -name "*_key" -delete', "access_change"),
    ('sudo bash -c "echo x > /etc/sudoers"', "access_change"),
    ("echo x >> /etc//passwd", "access_change"),
]
WRAPPED_READS = [
    'bash -c "cat /etc/passwd"',
    "docker exec db cat /etc/passwd",
    "docker exec db ls /var/lib/postgresql/data",
    'find /etc/ssh -name "*.pub"',
    'bash -c "ls; echo ok"',
    "bash script.sh",
    "systemctl status ssh",
    "service ssh status",
]


@pytest.mark.parametrize(("cmd", "category"), WRAPPED)
def test_a_wrapped_destructive_command_waits_for_the_seal(cmd: str, category: str) -> None:
    assert classify(cmd) == category


@pytest.mark.parametrize("cmd", WRAPPED_READS)
def test_a_wrapped_read_runs_free(cmd: str) -> None:
    assert classify(cmd) is None


@pytest.mark.parametrize(
    "path", ["/etc//passwd", "/etc/./shadow", "/etc/ssh/../passwd", "//etc/ssh/x"]
)
def test_writing_a_sensitive_path_however_spelled_is_an_access_change(path: str) -> None:
    hit = classify_path(path)
    assert hit is not None and hit[0] == "access_change"
