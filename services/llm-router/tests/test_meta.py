"""The ledger metadata of a call: allow-listed keys, short values (prompt 08 §6-§7
adds the sealed skill versions and the academy's eval refs)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from llm_router.schemas import META_LIST_MAX, RunRequest

BODY: dict[str, Any] = {
    "company_code": "HQ",
    "actor_ref": "HQ-AIOPS-MGR",
    "task_class": "general",
    "priority": 3,
    "prompt": "x",
}


def test_the_request_and_prefix_hashes_carry_no_text() -> None:
    """Prompt 12 §8: duplicate calls and cache misses are found by hashes only."""
    from llm_router import hashes

    a = RunRequest(**{**BODY, "system": "You are the CTO.", "prompt": "متن محرمانه"})
    b = RunRequest(**{**BODY, "system": "You are the CTO.", "prompt": "متن دیگر"})
    ha, hb = hashes.of(a, "claude-sonnet-5-5"), hashes.of(b, "claude-sonnet-5-5")
    assert set(ha) == {"request_sha256", "prefix_sha256"}
    assert all(len(v) == 64 and "محرمانه" not in v for v in ha.values())
    assert ha["request_sha256"] != hb["request_sha256"]
    assert ha["prefix_sha256"] == hb["prefix_sha256"]
    assert hashes.of(a, "claude-sonnet-5-5") == ha  # stable
    assert hashes.of(a, "claude-opus-5-5")["prefix_sha256"] != ha["prefix_sha256"]
    assert set(hashes.of(RunRequest(**BODY), None)) == {"request_sha256"}  # no system: no prefix


def test_skills_and_addenda_are_lists_of_short_refs() -> None:
    r = RunRequest(
        **BODY,
        meta={
            "charter": "cto@2",
            "skills": ["SK-001@3", "SK-101@1"],
            "addenda": ["TE-0001"],
            "step": 1,
        },
    )
    assert r.meta is not None and r.meta["skills"] == ["SK-001@3", "SK-101@1"]
    r = RunRequest(
        **BODY,
        meta={"eval_run": "0193e7a1-0000-7000-8000-000000000001", "suite": "EV-001", "case": "c1"},
    )
    assert r.meta is not None and r.meta["suite"] == "EV-001"


@pytest.mark.parametrize(
    "meta",
    [
        {"subject": "x"},  # not on the allow-list
        {"charter": ["cto@2"]},  # a list only where the list keys allow it
        {"skills": ["SK-001@3"] * (META_LIST_MAX + 1)},
        {"skills": ["x" * 33]},
        {"purpose": "x" * 65},
    ],
)
def test_other_metadata_is_refused(meta: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RunRequest(**BODY, meta=meta)
