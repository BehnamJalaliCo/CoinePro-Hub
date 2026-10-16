import pytest

from llm_router.assignment import (
    Assignment,
    AssignmentError,
    apply_request,
    resolve,
    scope_chain,
)

CHAIN = scope_chain(
    holding="HQ", company="TY", department="TECH", role="lead-dev", task_class="summarize"
)


def test_chain_order_general_to_specific() -> None:
    assert CHAIN == [
        ("holding", "HQ"),
        ("company", "TY"),
        ("department", "TY-TECH"),
        ("role", "lead-dev"),
        ("role", "TY:lead-dev"),
        ("task_class", "summarize"),
        ("task_class", "TY:summarize"),
    ]


def test_holding_only() -> None:
    rows = {("holding", "HQ"): Assignment("claude", "sonnet", "medium")}
    r = resolve(rows, CHAIN)
    assert (r.connection_id, r.model, r.effort) == ("claude", "sonnet", "medium")
    assert r.trail == ("holding:HQ",)


def test_each_level_overrides_the_one_above() -> None:
    rows = {
        ("holding", "HQ"): Assignment("claude", "sonnet", "medium"),
        ("company", "TY"): Assignment("gemini", "gemini-pro", "low"),  # "all of TY on Gemini"
        ("department", "TY-TECH"): Assignment(effort="high"),
        ("role", "lead-dev"): Assignment("claude", "opus", None),  # "...except the lead dev"
        ("task_class", "summarize"): Assignment(effort="low"),
    }
    r = resolve(rows, CHAIN)
    assert (r.connection_id, r.model, r.effort) == ("claude", "opus", "low")
    assert r.trail == (
        "holding:HQ",
        "company:TY",
        "department:TY-TECH",
        "role:lead-dev",
        "task_class:summarize",
    )


def test_company_qualified_ref_beats_global_ref() -> None:
    rows = {
        ("holding", "HQ"): Assignment("claude", "sonnet"),
        ("task_class", "summarize"): Assignment(model="haiku"),
        ("task_class", "TY:summarize"): Assignment(model="opus"),
        ("role", "lead-dev"): Assignment(effort="max"),
        ("role", "TY:lead-dev"): Assignment(effort="xhigh"),
    }
    r = resolve(rows, CHAIN)
    assert (r.model, r.effort) == ("opus", "xhigh")


def test_switching_connection_drops_inherited_model() -> None:
    rows = {
        ("holding", "HQ"): Assignment("claude", "sonnet"),
        ("company", "TY"): Assignment("gemini"),
    }
    r = resolve(rows, CHAIN)
    assert (r.connection_id, r.model) == ("gemini", None)


def test_unrelated_company_rows_do_not_apply() -> None:
    rows = {
        ("holding", "HQ"): Assignment("claude", "sonnet"),
        ("company", "FX"): Assignment("gemini", "gemini-pro"),
        ("department", "FX-TECH"): Assignment(effort="max"),
        ("task_class", "FX:summarize"): Assignment(model="x"),
    }
    r = resolve(rows, CHAIN)
    assert (r.connection_id, r.model, r.effort) == ("claude", "sonnet", None)


def test_no_department_or_role_skips_those_levels() -> None:
    chain = scope_chain(
        holding="HQ", company="TY", department=None, role=None, task_class="general"
    )
    assert [t for t, _ in chain] == ["holding", "company", "task_class", "task_class"]


def test_no_connection_is_an_error() -> None:
    with pytest.raises(AssignmentError):
        resolve({("company", "TY"): Assignment(model="m")}, CHAIN)


def test_apply_request_overrides_and_validation() -> None:
    r = resolve({("holding", "HQ"): Assignment("c", "sonnet", "medium")}, CHAIN)
    assert apply_request(
        r,
        requested_model=None,
        requested_effort=None,
        allowed_models=["sonnet", "haiku"],
        default_model=None,
    ) == ("sonnet", "medium")
    assert apply_request(
        r,
        requested_model="haiku",
        requested_effort="low",
        allowed_models=["sonnet", "haiku"],
        default_model=None,
    ) == ("haiku", "low")
    with pytest.raises(AssignmentError):
        apply_request(
            r,
            requested_model="gpt",
            requested_effort=None,
            allowed_models=["sonnet"],
            default_model=None,
        )
    with pytest.raises(AssignmentError):
        apply_request(
            r, requested_model=None, requested_effort="turbo", allowed_models=[], default_model=None
        )
    bare = resolve({("holding", "HQ"): Assignment("c")}, CHAIN)
    assert apply_request(
        bare, requested_model=None, requested_effort=None, allowed_models=[], default_model="dflt"
    ) == ("dflt", None)
    with pytest.raises(AssignmentError):
        apply_request(
            bare, requested_model=None, requested_effort=None, allowed_models=[], default_model=None
        )
