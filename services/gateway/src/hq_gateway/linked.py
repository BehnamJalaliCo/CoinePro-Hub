"""Another company's data (agents/tools.md, ⟨2026-11-06⟩; contract §35.6): the owner wants the
companies to give each other data, like the veins of a body.

    linked.read  A0  {company, what: profile|kpis|outputs|catalogue|connections|links, ref?}
                     another company's working data: any active company while the owner does not
                     enforce links (his setting), else along an `on` link (either way); the
                     caller's own company; any company for the holding's readers. `ref` (with
                     `outputs`): one output's body.

Every role but a system one holds it (hq_common.charters.SHARED_TOOLS); the api and the policy
decide which company may be read (OPA hq.internal, linked.rego) and leave customer data and
secrets out. The answer is redacted again by the gateway like every result.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from hq_gateway import tools as T


class LinkedReadIn(T.In):
    company: str = Field(pattern=T.CODE)
    what: Literal["profile", "kpis", "outputs", "catalogue", "connections", "links"]
    ref: str | None = Field(default=None, pattern=r"^O-[0-9]{4,}$")


async def linked_read(api: T.Api, call: T.Call, a: LinkedReadIn) -> T.Result:
    if a.ref is not None and a.what != "outputs":
        return T.Result(
            "error",
            code="invalid_args",
            fields={"ref": "only with what=outputs"},
            hint_fa="شماره‌ی خروجی (ref) فقط با what=outputs فرستاده میشود.",
        )
    resp = await api.request(
        "GET",
        "/internal/v1/linked/read",
        call.token,
        params={"company": a.company, "what": a.what, "ref": a.ref},
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok":
        r.ref = f"{a.company}:{a.what}" + (f":{a.ref}" if a.ref else "")
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "linked.read": (LinkedReadIn, linked_read),
}
T.TOOLS.update(TOOLS)
