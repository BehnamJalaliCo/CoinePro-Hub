"""⟨2026-11-11⟩ W23: usage-limit wording is a quota refusal with or without the 429 / error flag,
so the CLI's limit notice is never handed back as the model's answer (audit C1c)."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

import pytest

from claude_runtime.quota import Signals, classify, limit_notice
from claude_runtime.runner import ClaudeRunner, Message, RunSpec

FAKE = Path(__file__).resolve().parents[1] / "testing" / "fake_claude.py"


def test_limit_wording_without_a_429_is_a_quota_refusal() -> None:
    # an error result that says it, without any 429
    v = classify(
        Signals(result_seen=True, is_error=True, text="Claude AI usage limit reached|1800000000")
    )
    assert (v.status, v.error_class, v.resets_at) == ("quota_exhausted", "usage_limit", 1.8e9)
    # the CLI's notice as the whole answer, no error flag at all
    for notice in (
        "You've hit your limit · resets 5pm (UTC)",
        "5-hour limit reached ∙ resets 3pm",
        "Weekly limit reached ∙ resets Mon 9am",
        "You're out of extra usage · resets 3am",
    ):
        assert classify(Signals(result_seen=True, text=notice)).status == "quota_exhausted", notice
    # no result at all, only the notice in the assistant's text: still the limit
    assert classify(Signals(text="Claude AI usage limit reached")).status == "quota_exhausted"


def test_a_real_answer_that_mentions_a_limit_stays_an_answer() -> None:
    long = "The daily quota of the API was discussed. " * 20 + "usage limit reached in March."
    assert classify(Signals(result_seen=True, text=long)).status == "ok"
    # a structured (schema) answer is a real answer whatever its text says
    short = '{"summary_fa": "usage limit reached", "done": true}'
    assert classify(Signals(result_seen=True, text=short, structured=True)).status == "ok"
    # "quota" alone in an ok answer is not the CLI's notice
    assert classify(Signals(result_seen=True, text="quota است")).status == "ok"
    assert not limit_notice("") and not limit_notice(None)
    assert limit_notice("  Claude usage limit reached  ")


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
