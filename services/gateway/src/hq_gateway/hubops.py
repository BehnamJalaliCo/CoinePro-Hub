"""⟨1.20⟩ The hub run from the app (contract §38.1, agents/tools.md): `hub.ops`.

    hub.ops   A0/A1/A2  {op, args?} · {job}: one operation of the hub's fixed catalogue
                        (apps/api domain/hub_ops.py), queued on the hub and run on the hub host by
                        the hub-ops dispatcher; the first answer is `queued` with a job: call again
                        with {job} until done (output masked, ≤ 64 KB) or failed

    A0  status, logs, stats, verify, inventory, n8n.list, n8n.executions, and every {job} read
    A2  restart, profile, n8n.import, n8n.activate, backup
    A1  the A3 ones (n8n.create; a profile with turn_off): the call only proposes the owner's 🔏
        hub_op card and answers `awaiting_seal` with its ref; approving it queues the job

Only the holding's technical roles hold it (aiops_head, hub_platform_sre, the holding's CTO); the
api and the policy check again. A denied operation (SSH, users, firewall, OpenBao, secrets, the
owner's sign-ins, reboot, deletion, deploy) answers policy_denied with the owner's step.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from hq_gateway import tools as T

JOB_RE = r"^HJ-[0-9]{6,}$"
WAIT_S = 12  # within the gateway's own tool timeout
READ_OPS = frozenset(
    {"status", "logs", "stats", "verify", "inventory", "n8n.list", "n8n.executions"}
)
SEALED_OPS = frozenset({"n8n.create"})


class HubOpsIn(T.In):
    """Either a new operation (op, args?) or `{job}` to read one again."""

    op: str | None = Field(default=None, min_length=1, max_length=60)
    args: dict[str, Any] = Field(default_factory=dict)
    job: str | None = Field(default=None, pattern=JOB_RE)

    @model_validator(mode="after")
    def _either(self) -> HubOpsIn:
        if (self.op is None) == (self.job is None):
            raise ValueError("op (with its args) or job")
        return self


def call_class(a: HubOpsIn) -> str:
    if a.job is not None or a.op in READ_OPS:
        return "A0"
    if a.op in SEALED_OPS or (a.op == "profile" and a.args.get("turn_off")):
        return "A1"  # only the owner's card is proposed
    return "A2"


def _shape(r: T.Result) -> T.Result:
    if r.outcome != "ok" or not isinstance(r.data, dict):
        return r
    job = r.data.get("job") or {}
    r.ref = str(job.get("ref") or "") or None
    hint = r.data.get("hint_fa")
    if hint:
        r.hint_fa = str(hint)[: T.HINT_CHARS]
    if job.get("state") == "awaiting_seal":
        return T.Result(
            "denied",
            code="awaiting_seal",
            ref=str(job.get("decision_ref") or r.ref or ""),
            data={
                "job": job.get("ref"),
                "state": "awaiting_seal",
                "decision": job.get("decision_ref"),
            },
            hint_fa=r.hint_fa,
        )
    if job.get("state") in ("failed", "refused"):
        r.outcome, r.code = "error", "hub_op_" + str(job["state"])
    r.data = job
    return r


async def hub_ops(api: T.Api, call: T.Call, a: HubOpsIn) -> T.Result:
    if a.job is not None:
        resp = await api.request(
            "GET", f"/internal/v1/hubops/{a.job}", call.token, params={"wait_s": WAIT_S}
        )
        return _shape(T.from_response(resp, None))
    resp = await api.request(
        "POST", "/internal/v1/hubops", call.token, json={"op": a.op, "args": a.args}
    )
    return _shape(T.from_response(resp, None))


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {"hub.ops": (HubOpsIn, hub_ops)}
T.TOOLS.update(TOOLS)
T.CALL_CLASS["hub.ops"] = call_class
