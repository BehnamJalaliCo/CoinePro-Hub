"""⟨1.19⟩ «پاکش کن» in words (contract §37.3): an agent proposes an erase, the owner seals it.

erase.propose (A1)   {kind: session | archive_record | output, ref, why_fa}: a decision card
                     `erase` to the owner with the preview's counts (what goes, what stays).
                     Every working role holds it (hq_common.charters.SHARED_TOOLS); the api and
                     the policy let a role propose only what it can read. Approving the card
                     (the owner's passkey) erases exactly that thing; rejecting it changes
                     nothing. An agent never erases anything itself.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from hq_gateway import tools as T

ERASE_REF = r"^(F-[0-9]{4,}|AR-[0-9]{6,}|O-[0-9]{6,})$"


class EraseIn(T.In):
    kind: Literal["session", "archive_record", "output"]
    ref: str = Field(pattern=ERASE_REF)
    why_fa: str = Field(min_length=2, max_length=2000)


async def erase_propose(api: T.Api, call: T.Call, a: EraseIn) -> T.Result:
    resp = await api.request(
        "POST",
        "/internal/v1/erase/propose",
        call.token,
        json={"kind": a.kind, "ref": a.ref, "why_fa": await T._text(a.why_fa)},
        idem=call.idem("erase.propose"),
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        raw = r.data.get("payload")
        payload = raw if isinstance(raw, dict) else {}
        r.ref = str(r.data.get("ref") or "")
        r.data = {
            "decision": r.data.get("ref"),
            "status": r.data.get("status"),
            "erases": {"kind": a.kind, "ref": a.ref},
            "counts": payload.get("counts"),
        }
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "erase.propose": (EraseIn, erase_propose),
}
T.TOOLS.update(TOOLS)
