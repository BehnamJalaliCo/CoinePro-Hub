"""⟨2026-11-11⟩ W23: the CLI's own limit notice (limit wording AND its reset marker) is a quota
refusal with or without the 429 / error flag, so it is never handed back as the model's answer
(audit C1c); limit wording alone is an answer, never a refusal (a false positive would mark the
account full and move every call to the other one)."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

import pytest

from claude_runtime.quota import Signals, classify, limit_notice
from claude_runtime.runner import ClaudeRunner, Message, RunSpec

FAKE = Path(__file__).resolve().parents[1] / "testing" / "fake_claude.py"
# every notice the CLI writes when the subscription is out carries its reset
NOTICES = (
    "Claude AI usage limit reached|1800000000",
    "You've hit your limit · resets 5pm (UTC)",
    "You\u2019ve hit your session limit · resets 11pm",
    "5-hour limit reached ∙ resets 3pm",
    "Weekly limit reached ∙ resets Mon 9am",
    "You're out of extra usage · resets 3am",
    "Claude usage limit reached. Your limit will reset at 3pm.",
)
# what a turn may well say about a server, never the subscription
NOT_NOTICES = (
    "Disk usage limit reached; cleaned /var/log.",
    "disk quota exceeded",
    "write failed: Disk quota exceeded (errno 122)",
    "The API rate limit reached 80% yesterday; nothing to do.",
    "usage limit",
    "quota است",
)


def test_the_clis_notice_is_a_quota_refusal_with_or_without_an_error() -> None:
    v = classify(Signals(result_seen=True, is_error=True, text=NOTICES[0]))
    assert (v.status, v.error_class, v.resets_at) == ("quota_exhausted", "usage_limit", 1.8e9)
    for notice in NOTICES:
        assert limit_notice(notice), notice
        assert classify(Signals(result_seen=True, text=notice)).status == "quota_exhausted", notice
        assert classify(Signals(result_seen=True, is_error=True, text=notice)).error_class == (
            "usage_limit"
        )
    # no result at all, only the notice in the assistant's text: still the limit
    assert classify(Signals(text="Claude AI usage limit reached|1800000000")).status == (
        "quota_exhausted"
    )


def test_limit_wording_alone_is_never_the_subscriptions_limit() -> None:
    for text in NOT_NOTICES:
        assert not limit_notice(text), text
        assert classify(Signals(result_seen=True, text=text)).status == "ok", text
        # a failed run that says it: an error of that run, not the account's limit
        failed = classify(Signals(result_seen=True, is_error=True, subtype="error_x", text=text))
        assert failed.status == "error", text
    long = "The daily quota of the API was discussed. " * 20 + "usage limit reached, resets 3pm."
    assert classify(Signals(result_seen=True, text=long)).status == "ok"
    # a structured (schema) answer is a real answer whatever its text says
    short = '{"summary_fa": "usage limit reached|1800000000", "done": true}'
    assert classify(Signals(result_seen=True, text=short, structured=True)).status == "ok"
    assert not limit_notice("") and not limit_notice(None)


@pytest.fixture
def runner(tmp_path: Path) -> ClaudeRunner:
    target = tmp_path / "claude"
    shutil.copy(FAKE, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    os.environ["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] = "1"
    return ClaudeRunner(lambda: "oauth-test-token", tmp_path / "runs", cli_path=str(target))


async def test_the_clis_notice_is_never_returned_as_an_answer(runner: ClaudeRunner) -> None:
    spec = RunSpec(
        "0192f0c0-0000-7000-8000-000000000023",
        "claude-haiku-5-5",
        "low",
        "Be brief.",
        (Message("user", "[[fake:notice]] hi"),),
        None,
        20,
    )
    out = await runner.run(spec)
    assert (out.status, out.error_class, out.text) == ("quota_exhausted", "usage_limit", None)
    ok = await runner.run(
        RunSpec(spec.call_id, spec.model, None, None, (Message("user", "hi"),), None, 20)
    )
    assert (ok.status, ok.text) == ("ok", "OK")
