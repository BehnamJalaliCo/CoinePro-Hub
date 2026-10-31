"""The substitute runner (prompt 12 §9.1 acceptance, contract §21.13), with
FAKE codex and gemini executables (tests/fakes): never the real CLIs."""

from __future__ import annotations

import io
import json
import os
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from hq_substitutes import __main__ as main_mod
from hq_substitutes import runner as R

FAKES = Path(__file__).parent / "fakes"
ETC = Path(__file__).parents[1] / "etc" / "gemini-cli"
SCHEMAS = Path(__file__).parents[1] / "schemas"
JOB = "0b7a6f2e-0a8e-4a8e-9a43-3a7f1c2d9e10"
LOGIN = "1c8b7a3f-1b9f-4b9f-8b54-4b801d3e0f21"
SECRET_QUESTION = "سؤال ماسک‌شده: خلاصه‌ی این سند را بنویس"


@pytest.fixture
def s(tmp_path: Path) -> R.Settings:
    (tmp_path / "rec").mkdir()
    work = tmp_path / "work"
    work.mkdir()
    # Both CLIs signed in (fake credentials); the signed-out test removes them.
    (tmp_path / "auth" / "codex").mkdir(parents=True)
    (tmp_path / "auth" / "codex" / "auth.json").write_text("{}")
    (tmp_path / "auth" / "gemini" / ".gemini").mkdir(parents=True)
    (tmp_path / "auth" / "gemini" / ".gemini" / "oauth_creds.json").write_text("{}")
    return R.Settings(
        codex_bin=str(FAKES / "codex"),
        gemini_bin=str(FAKES / "gemini"),
        gemini_etc=ETC,
        auth_dir=tmp_path / "auth",
        work_dir=work,
        checkout_dir=tmp_path / "checkout",
        schema_dir=SCHEMAS,
        gemini_cli_gone=False,  # the dormant CLI paths stay tested (⟨1.7.2⟩)
    )


def job(**over: Any) -> R.Job:
    base: dict[str, Any] = {
        "id": JOB,
        "kind": "call",
        "player": "gpt",
        "runner": "codex_cli",
        "seat": "advisor_second_opinion",
        "model": "gpt-5.5",
        "input_md": SECRET_QUESTION,
        "checkout": None,
        "login": None,
        "timeout_s": 20,
    }
    base.update(over)
    return R.parse_job(json.dumps({"job": base}))


def one(j: R.Job, s: R.Settings, more: list[str] | None = None) -> dict[str, Any]:
    events = list(R.run(j, s, more or []))
    assert events[-1]["event"] == "done"
    assert sum(e["event"] == "done" for e in events) == 1
    return events[-1]


def mode(s: R.Settings, name: str) -> None:
    (s.work_dir.parent / "mode").write_text(name)


def rec(s: R.Settings, name: str) -> Any:
    p = s.work_dir.parent / "rec" / name
    return json.loads(p.read_text()) if name.endswith(".json") else p.read_text()


# ---------------------------------------------------------------- the jobs --
def test_a_codex_call_answers_with_its_own_usage(s: R.Settings) -> None:
    d = one(job(), s)
    assert d["ok"] is True
    assert d["error"] is None
    assert d["text_md"].startswith("پاسخ آزمایشی")
    assert d["usage"] == {"input_tokens": 120, "output_tokens": 30, "estimated": False}


def test_the_input_is_on_stdin_and_never_in_argv(s: R.Settings) -> None:
    one(job(), s)
    argv = rec(s, "codex-argv.json")
    assert rec(s, "codex-stdin.txt") == SECRET_QUESTION
    assert all(SECRET_QUESTION not in a and "سؤال" not in a for a in argv)
    assert argv[-1] == "-"  # codex exec reads the prompt from stdin
    one(job(runner="gemini_cli", player="gemini", model="gemini-3.8", seat="long_read"), s)
    gargv = rec(s, "gemini-argv.json")
    assert rec(s, "gemini-stdin.txt") == SECRET_QUESTION
    assert all("سؤال" not in a for a in gargv)
    assert gargv[gargv.index("-p") + 1] == R.GEMINI_PROMPT


def test_the_clis_own_tools_are_off(s: R.Settings) -> None:
    one(job(), s)
    argv = rec(s, "codex-argv.json")
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert {"--ephemeral", "--ignore-user-config", "--skip-git-repo-check"} <= set(argv)
    assert Path(rec(s, "codex-cwd.txt")) == s.work_dir  # the empty working dir
    one(job(runner="gemini_cli", player="gemini", model=None, seat="content_draft"), s)
    settings = json.loads(Path(rec(s, "gemini-settings.txt")).read_text())
    assert settings["tools"]["core"] == []  # no core tool is registered at all
    assert {"run_shell_command", "write_file", "web_fetch", "google_web_search"} <= set(
        settings["tools"]["exclude"]
    )
    assert settings["admin"]["mcp"]["enabled"] is False
    assert settings["privacy"]["usageStatisticsEnabled"] is False
    gargv = rec(s, "gemini-argv.json")
    assert gargv[gargv.index("--approval-mode") + 1] == "plan"


def test_the_cli_gets_a_small_fixed_environment(
    s: R.Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HQ_SOMETHING_SECRET", "x")
    for name in R.PROXY_ENV:
        monkeypatch.delenv(name, raising=False)
    env = R._env(job(), s)
    assert set(env) == {
        "PATH",
        "LANG",
        "TERM",
        "NO_COLOR",
        "NO_UPDATE_NOTIFIER",
        "HOME",
        "CODEX_HOME",
    }
    assert env["CODEX_HOME"] == str(s.auth_dir / "codex")
    monkeypatch.setenv("HTTPS_PROXY", "http://egress:3131")
    assert R._env(job(), s)["HTTPS_PROXY"] == "http://egress:3131"  # its only way out


def test_a_code_review_reads_only_its_read_only_checkout(s: R.Settings) -> None:
    mode(s, "review")
    s.checkout_dir.mkdir()
    (s.checkout_dir / "app.py").write_text("x = 1\n")
    j = job(seat="code_review", checkout={"repo": "coinepro-hub", "head_sha": "a" * 40})
    d = one(j, s)
    assert d["ok"] is True
    assert Path(rec(s, "codex-cwd.txt")) == s.checkout_dir
    argv = rec(s, "codex-argv.json")
    assert argv[argv.index("--output-schema") + 1] == str(SCHEMAS / "findings.json")
    # the malformed ones (an absolute path, an unknown severity) are dropped
    assert d["findings"] == [
        {"path": "app/x.py", "line": 12, "severity": "high", "title_fa": "خطای نمونه",
         "detail_md": "d"}
    ]  # fmt: skip
    gj = job(runner="gemini_cli", player="gemini", model=None, seat="code_review",
             checkout={"repo": "coinepro-hub", "head_sha": "b" * 40})  # fmt: skip
    one(gj, s)
    review = json.loads(Path(rec(s, "gemini-settings.txt")).read_text())
    assert set(review["tools"]["core"]) == {
        "read_file", "read_many_files", "list_directory", "glob", "grep_search"
    }  # fmt: skip
    assert "run_shell_command" in review["tools"]["exclude"]


def test_a_review_without_its_checkout_is_no_access(s: R.Settings) -> None:
    j = job(seat="code_review", checkout={"repo": "elsewhere", "head_sha": "c" * 40})
    d = one(j, s)
    assert (d["ok"], d["error"]) == (False, "no_access")


def test_a_used_up_quota_is_limited_with_its_reset(s: R.Settings) -> None:
    mode(s, "limited")
    d = one(job(), s)
    assert (d["ok"], d["error"]) == (False, "limited")
    until = datetime.fromisoformat(d["limited_until"])
    assert 1.9 * 3600 < (until - datetime.now(UTC)).total_seconds() <= 2 * 3600 + 5
    g = one(job(runner="gemini_cli", player="gemini", model=None, seat="content_draft"), s)
    assert (g["error"], g["limited_until"] is not None) == ("limited", True)


def test_a_signed_out_cli_says_signed_out(s: R.Settings) -> None:
    mode(s, "signed_out")
    assert one(job(), s)["error"] == "signed_out"
    g = one(job(runner="gemini_cli", player="gemini", model=None), s)
    assert g["error"] == "signed_out"


def test_without_a_stored_sign_in_the_cli_is_never_started(s: R.Settings) -> None:
    (s.auth_dir / "codex" / "auth.json").unlink()
    (s.auth_dir / "gemini" / ".gemini" / "oauth_creds.json").unlink()
    assert one(job(), s)["error"] == "signed_out"
    assert one(job(runner="gemini_cli", player="gemini", model=None), s)["error"] == "signed_out"
    assert one(job(kind="models", input_md=None, model=None), s)["error"] == "signed_out"
    assert not list((s.work_dir.parent / "rec").iterdir())  # no CLI ran


def test_retries_reported_on_the_way_are_not_an_error() -> None:
    out = "\n".join(
        json.dumps(e)
        for e in (
            {"type": "error", "message": "Reconnecting... 2/5 (stream disconnected)"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}},
            {"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 1}},
        )
    )
    assert R.parse_codex(out) == ("ok", {"input_tokens": 3, "output_tokens": 1}, None)


def test_no_usage_report_is_estimated_from_the_text(s: R.Settings) -> None:
    mode(s, "no_usage")
    d = one(job(), s)
    assert d["usage"]["estimated"] is True
    assert d["usage"]["input_tokens"] == R.estimate(SECRET_QUESTION)


def test_a_cli_past_its_timeout_is_killed(s: R.Settings) -> None:
    mode(s, "slow")
    d = one(job(timeout_s=5), s)
    assert (d["ok"], d["error"]) == (False, "timeout")


def test_garbage_from_the_cli_is_a_failure_without_its_words(s: R.Settings) -> None:
    mode(s, "bad")
    d = one(job(), s)
    assert (d["ok"], d["error"]) == (False, "failed")
    assert len(d["status_reason"]) <= R.REASON_CHARS


def test_a_long_output_is_read_whole_and_a_huge_one_fails_plainly(tmp_path: Path) -> None:
    """⟨1.10.1⟩ the CLI's output is read in full from a temporary file (the
    Codex model listing is ~645 KB), never cut; past the hard stop the call
    fails with that reason instead of a cut answer."""
    script = tmp_path / "big.py"
    script.write_text("import sys\nsys.stdout.write('x' * int(sys.argv[1]) + 'END')\n")
    ran = R.run_cli([sys.executable, str(script), "700000"], "", tmp_path, dict(os.environ), 20)
    assert ran.rc == 0 and len(ran.out) == 700_003 and ran.out.endswith("END") and not ran.too_large
    big = R.run_cli(
        [sys.executable, str(script), "3000"], "", tmp_path, dict(os.environ), 20, max_output=1000
    )
    assert big.too_large and big.out == "" and big.err == R.OUTPUT_TOO_LARGE
    echo = tmp_path / "echo.py"
    echo.write_text("import sys\nsys.stdout.write(sys.stdin.read())\n")
    question = "پرسش " * 50_000
    assert (
        R.run_cli([sys.executable, str(echo)], question, tmp_path, dict(os.environ), 20).out
        == question
    )


def test_models_codex_lists_what_the_account_offers(s: R.Settings) -> None:
    d = one(job(kind="models", seat=None, input_md=None, model=None), s)
    assert d["models"] == ["gpt-5.5", "gpt-6-sol"]  # the hidden one is not offered


def test_models_gemini_probes_the_one_model_it_names(s: R.Settings) -> None:
    g = {"runner": "gemini_cli", "player": "gemini", "kind": "models", "input_md": None}
    assert one(job(**g, model="gemini-3.8"), s)["models"] == ["gemini-3.8"]
    mode(s, "no_model")
    assert one(job(**g, model="gemini-9"), s)["models"] == []
    assert one(job(**g, model=None), s)["error"] == "not_ready"


def test_logout_removes_the_stored_sign_in(s: R.Settings) -> None:
    creds = s.auth_dir / "gemini" / ".gemini" / "oauth_creds.json"
    creds.write_text("{}")
    d = one(job(kind="logout", runner="gemini_cli", player="gemini", input_md=None, model=None), s)
    assert d["ok"] is True
    assert not creds.exists()
    (s.auth_dir / "codex").mkdir(parents=True, exist_ok=True)
    (s.auth_dir / "codex" / "auth.json").write_text("{}")
    assert one(job(kind="logout", input_md=None, model=None), s)["ok"] is True
    assert not (s.auth_dir / "codex" / "auth.json").exists()


# ------------------------------------------------------------------- login --
def signed_out(s: R.Settings) -> None:
    (s.auth_dir / "codex" / "auth.json").unlink()
    (s.auth_dir / "gemini" / ".gemini" / "oauth_creds.json").unlink()


def test_codex_device_login_reports_the_url_and_code(s: R.Settings) -> None:
    signed_out(s)
    j = job(kind="login", input_md=None, model=None, login={"id": LOGIN, "method": "device_code"})
    events = list(R.run(j, s, []))
    assert events[0] == {
        "event": "login_started",
        "method": "device_code",
        "verification_url": "https://auth.openai.com/codex/device",
        "user_code": "QWER-TY12Z",
    }
    assert events[-1]["ok"] is True
    auth = s.auth_dir / "codex" / "auth.json"
    assert auth.is_file()
    assert oct(auth.stat().st_mode & 0o777) == "0o600"  # umask 077


def test_gemini_auth_code_login_takes_the_owners_code_once(s: R.Settings) -> None:
    signed_out(s)
    j = job(kind="login", runner="gemini_cli", player="gemini", input_md=None, model=None,
            login={"id": LOGIN, "method": "auth_code"})  # fmt: skip
    events = list(R.run(j, s, [json.dumps({"code": "GOOD-CODE-123"})]))
    assert events[0]["method"] == "auth_code"
    assert events[0]["verification_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert events[0]["user_code"] is None
    assert events[-1]["ok"] is True
    text = json.dumps(events)
    assert "GOOD-CODE-123" not in text  # the code never comes back out


def test_a_wrong_or_missing_code_fails_the_login(s: R.Settings) -> None:
    signed_out(s)
    j = job(kind="login", runner="gemini_cli", player="gemini", input_md=None, model=None,
            login={"id": LOGIN, "method": "auth_code"}, timeout_s=8)  # fmt: skip
    bad = list(R.run(j, s, [json.dumps({"code": "WRONG-CODE"})]))
    assert (bad[-1]["ok"], bad[-1]["error"]) == (False, "failed")
    none = list(R.run(j, s, []))
    assert (none[-1]["ok"], none[-1]["error"]) == (False, "timeout")


# --------------------------------------------------------------- parsing --
def test_parse_job_refuses_what_is_not_this_interface() -> None:
    good = {"id": JOB, "kind": "call", "player": "gpt", "runner": "codex_cli",
            "input_md": "x", "timeout_s": 30}  # fmt: skip
    R.parse_job(json.dumps({"job": good}))
    for bad in (
        {**good, "kind": "shell"},
        {**good, "player": "gemini"},
        {**good, "id": "nope"},
        {**good, "model": "gpt 5; rm -rf /"},
        {**good, "input_md": ""},
        {**good, "timeout_s": 99999},
        {**good, "checkout": {"repo": "r", "head_sha": "zz"}},
        {**good, "kind": "login"},
    ):
        with pytest.raises(R.BadJob):
            R.parse_job(json.dumps({"job": bad}))
    with pytest.raises(R.BadJob):
        R.parse_job("not json")


def test_limited_until_reads_the_usual_shapes() -> None:
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    assert R.limited_until("try again in 30 minutes", now) == "2026-10-22T12:30:00+00:00"
    assert R.limited_until("Retry-After: 120", now) == "2026-10-22T12:02:00+00:00"
    assert R.limited_until("try again at 3:15 PM", now) == "2026-10-22T15:15:00+00:00"
    assert R.limited_until("try again at 9:00 am", now) == "2026-10-23T09:00:00+00:00"
    assert R.limited_until("no idea", now) is None


def test_a_reason_is_short_and_scrubbed() -> None:
    key = "sk-ant-" + "api03-" + "B" * 80
    d = R.done(False, error="failed", status_reason=f"boom {key} " + "x" * 500)
    assert key not in d["status_reason"]
    assert len(d["status_reason"]) <= R.REASON_CHARS


def test_main_reads_one_job_and_writes_json_lines(
    s: R.Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(R.Settings, "from_env", classmethod(lambda cls: s))
    line = json.dumps({"job": {"id": JOB, "kind": "call", "player": "gpt", "runner": "codex_cli",
                               "input_md": "q", "timeout_s": 20}})  # fmt: skip
    monkeypatch.setattr(sys, "stdin", io.StringIO(line + "\n"))
    assert main_mod.main() == 0
    out = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [e["event"] for e in out] == ["done"]
    assert out[0]["ok"] is True
    monkeypatch.setattr(sys, "stdin", io.StringIO("garbage\n"))
    assert main_mod.main() == 0
    bad = json.loads(capsys.readouterr().out)
    assert (bad["ok"], bad["error"]) == (False, "failed")


def _lines(items: list[str]) -> Iterator[str]:
    yield from items


def test_the_login_waits_for_the_code_line_while_the_cli_waits(s: R.Settings) -> None:
    """The dispatcher's code line may come later: the runner blocks on its stdin."""
    signed_out(s)
    j = job(kind="login", runner="gemini_cli", player="gemini", input_md=None, model=None,
            login={"id": LOGIN, "method": "auth_code"})  # fmt: skip
    r, w = os.pipe()
    reader = os.fdopen(r)

    def later() -> None:
        import time

        time.sleep(1.5)
        os.write(w, (json.dumps({"code": "GOOD-CODE-123"}) + "\n").encode())
        os.close(w)

    t = threading.Thread(target=later)
    t.start()
    events = list(R.run(j, s, (line.strip() for line in reader)))
    t.join()
    assert events[-1]["ok"] is True


def test_the_gemini_cli_player_is_unavailable_and_never_asks_for_a_key(tmp_path: Path) -> None:
    """Contract ⟨1.7.2⟩ (14.1 §2.2): Google ended the Gemini CLI's sign-in for
    individuals; every kind of Gemini CLI job answers unavailable at once,
    starts no CLI and asks for no API key."""
    s = R.Settings(gemini_bin=str(tmp_path / "no-such-gemini"), auth_dir=tmp_path / "auth",
                   work_dir=tmp_path, checkout_dir=tmp_path, schema_dir=SCHEMAS)  # fmt: skip
    assert s.gemini_cli_gone
    for kind in ("call", "models", "logout"):
        out = one(job(kind=kind, runner="gemini_cli", player="gemini", model="gemini-3.8",
                      seat="long_read"), s)  # fmt: skip
        assert out["ok"] is False and out["error"] == "unavailable"
        assert "discontinued by Google" in out["status_reason"]
        assert "gemini-web-login" in out["status_reason"]
        assert "key" not in out["status_reason"].lower()
    assert R.Settings.from_env().gemini_cli_gone
