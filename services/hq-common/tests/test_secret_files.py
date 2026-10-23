"""hq_common.secret_files (prompt 12 §9.1, the rule of §21.2): a file the
secret scan flags never reaches a substitute's checkout or the corpus."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hq_common import secret_files as SF

KEY = "sk-ant-" + "api03-" + "A" * 80  # an Anthropic-shaped key (a fake)


@pytest.mark.parametrize(
    "name",
    [".env", ".env.local", "prod.env", "server.pem", "tls.key", "id_rsa", "id_ed25519.pub",
     "credentials.json", "secrets.yaml", ".npmrc", ".pypirc", ".netrc", "kubeconfig",
     "terraform.tfstate", "a/.git/config", "node_modules/x/index.js", "auth.json"],
)  # fmt: skip
def test_names_that_hold_credentials_are_flagged_whatever_they_contain(name: str) -> None:
    assert SF.flagged(name, "nothing here")


@pytest.mark.parametrize("name", ["README.md", "src/app.py", "docs/env.md", "keys.md"])
def test_ordinary_names_with_clean_text_are_kept(name: str) -> None:
    assert not SF.flagged(name, "def main():\n    return 1\n")


def test_a_key_in_the_text_flags_the_whole_file() -> None:
    assert SF.flagged("src/settings.py", f"API_KEY = '{KEY}'\n")
    assert SF.flagged("notes.txt", "-----BEGIN OPENSSH " + "PRIVATE KEY-----\nabc\n")


def test_binary_or_unreadable_is_flagged() -> None:
    assert SF.flagged("logo.png", None)


def test_prune_removes_the_test_env_and_keeps_the_code(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n")
    (tmp_path / ".env").write_text(f"ANTHROPIC_API_KEY={KEY}\n")
    (tmp_path / "src" / "conf.py").write_text(f"TOKEN = '{KEY}'\n")
    (tmp_path / "big.txt").write_text("x" * (SF.MAX_BYTES + 1))
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01\x02")
    (tmp_path / "node_modules" / "p").mkdir(parents=True)
    (tmp_path / "node_modules" / "p" / "i.js").write_text("module.exports = 1\n")
    os.symlink("/etc/passwd", tmp_path / "link")
    removed = SF.prune(tmp_path)
    left = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    assert left == ["src/app.py"]
    assert removed == 6
    assert not (tmp_path / "link").exists()


def test_the_module_entry_prints_only_the_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".env").write_text(f"K={KEY}\n")
    assert SF.main(["x", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert out.strip() == "1"
    assert KEY not in out
    assert SF.main(["x"]) == 2
