"""⟨2026-11-11⟩ W23: the CLI's own usage-limit notice (its own form: the limit phrase first, its
reset marker "|<epoch>" or "∙ resets", written by the CLI itself) is a quota refusal with or without
the 429 / error flag, so it is never handed back as the model's answer (audit C1c). Any other text
about a limit and its reset is an answer: taken for the subscription's limit it would mark both
accounts full, one after the other, and refuse every call."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

import pytest

from claude_runtime.quota import Signals, classify, limit_notice
from claude_runtime.runner import ClaudeRunner, Message, RunSpec

FAKE = Path(__file__).resolve().parents[1] / "testing" / "fake_claude.py"
# what the CLI writes when the subscription is out
NOTICES = (
    "Claude AI usage limit reached|1800000000",
    "You've hit your limit · resets 5pm (UTC)",
    "You’ve hit your session limit · resets 11pm",
    "5-hour limit reached ∙ resets 3pm",
    "Weekly limit reached ∙ resets Mon 9am",
    "Opus weekly limit reached ∙ resets Mon 9am",
    "You're out of extra usage · resets 3am",
)
# what a model may well answer about a limit (and its reset), never the subscription's
NOT_NOTICES = (
    "Instagram publishing limit reached (25/25); resets at 14:00 UTC.",
    "The IG API usage limit resets hourly; I will retry the publish then.",
    "Fail2ban limit hit for 1.2.3.4; the ban resets in 10 minutes.",
    "Disk usage limit reached; cleaned /var/log.",
    "disk quota exceeded",
    "write failed: Disk quota exceeded (errno 122)",
    "The API rate limit reached 80% yesterday; nothing to do.",
    "Claude usage limit reached. Your limit will reset at 3pm.",  # no CLI marker
    "Done. Note: 5-hour limit reached ∙ resets 3pm",  # not at the start
    "usage limit",
    "quota است",
)


def cli(text: str, **kw: object) -> Signals:
    """The CLI wrote the text itself (a synthetic message)."""
    return Signals(result_seen=True, text=text, synthetic=True, **kw)  # type: ignore[arg-type]


def test_the_clis_notice_is_a_quota_refusal_with_or_without_an_error() -> None:
    v = classify(cli(NOTICES[0], is_error=True))
    assert (v.status, v.error_class, v.resets_at) == ("quota_exhausted", "usage_limit", 1.8e9)
    for notice in NOTICES:
        assert limit_notice(notice), notice
        assert classify(cli(notice)).status == "quota_exhausted", notice
        assert classify(cli(notice, is_error=True)).error_class == "usage_limit", notice
    # no result at all, only the CLI's notice in its own message: still the limit
    only = Signals(text="Claude AI usage limit reached|1800000000", synthetic=True)
    assert classify(only).status == "quota_exhausted"


def test_an_answer_about_a_limit_is_never_the_subscriptions_limit() -> None:
    for text in NOT_NOTICES:
        assert not limit_notice(text), text
        assert classify(cli(text)).status == "ok", text
        # a failed run that says it: an error of that run, not the account's limit
        failed = classify(cli(text, is_error=True, subtype="error_x"))
        assert failed.status == "error", text
    # the notice's very words written by a model (it generated them): an answer
    for notice in NOTICES:
        assert classify(Signals(result_seen=True, text=notice)).status == "ok", notice
    long = "5-hour limit reached ∙ resets 3pm. " + "The daily quota was discussed. " * 20
    assert classify(cli(long)).status == "ok"
    # a structured (schema) answer is a real answer whatever its text says
    short = "Claude AI usage limit reached|1800000000"
    assert classify(cli(short, structured=True)).status == "ok"
    assert not limit_notice("") and not limit_notice(None)


@pytest.fixture
def runner(tmp_path: Path) -> ClaudeRunner:
    target = tmp_path / "claude"
    shutil.copy(FAKE, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    os.environ["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] = "1"
    return ClaudeRunner(lambda: "oauth-test-token", tmp_path / "runs", cli_path=str(target))


def spec(prompt: str) -> RunSpec:
    return RunSpec(
        "0192f0c0-0000-7000-8000-000000000023",
        "claude-haiku-5-5",
        "low",
        "Be brief.",
        (Message("user", prompt),),
        None,
        20,
    )


async def test_the_clis_notice_is_never_returned_as_an_answer(runner: ClaudeRunner) -> None:
    out = await runner.run(spec("[[fake:notice]] hi"))
    assert (out.status, out.error_class, out.text) == ("quota_exhausted", "usage_limit", None)
    # the same words from a model (it generated them): its answer, handed back as is
    said = await runner.run(spec("[[fake:limitanswer]] hi"))
    assert (said.status, said.text) == ("ok", "5-hour limit reached ∙ resets 3pm")
    ok = await runner.run(spec("hi"))
    assert (ok.status, ok.text) == ("ok", "OK")
