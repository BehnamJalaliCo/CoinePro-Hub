"""Prompt 13 §6: the measured fixed size of each media role's prompt (its
system prompt: _common, the charter, the department's identity, the runtime's
own sections), the base of the per-reel token estimate in the report. No
model is called; it prints the figures and checks they stay bounded."""

from __future__ import annotations

from typing import Any

from hq_api.agents import protocol as P
from hq_api.agents.runner import prompt_tokens
from hq_api.domain import decisions as D
from hq_api.domain import templates
from hq_api.hub import Hub

ROLES = ("scriptwriter", "video_director", "motion_designer", "voice_producer", "media_director")


def test_the_media_prompts_fixed_size(hub: Hub, capsys: Any) -> None:
    lib = hub.charters
    identity = str(templates.department("standard", "MEDIA")["identity_md"])  # type: ignore[index]
    values = {"company_code": "TY", "company_name_en": "TradeYar", "holding_code": "HQ"}
    sizes = {}
    for role in ROLES:
        c = lib.get(role)
        assert c is not None
        system = P.system_prompt(
            lib, c, values, max_actions=8, payloads=D.PAYLOADS, after_charter=identity
        )
        sizes[role] = prompt_tokens(system, [])
    with capsys.disabled():
        print("\nmedia prompt sizes (tokens, chars/4):", sizes)
    assert all(2_000 < n < 20_000 for n in sizes.values()), sizes
