"""Hub operations (contract §38, the owner, 2026-11-06: «نمیشه که یبار توی آپ من بگم یبارم بیام به تو
بگم یبار تو به سرور بگی»): the one catalogue, as data, of what the holding's technical people (and the
owner's services page, §38.3) may do on the hub itself. Nothing here runs anything: a job is a row
(ops.hub_jobs) that the hub-ops dispatcher on the host (infra/hubops/dispatch.sh, a systemd timer as
user Hub) claims, runs and answers. The dispatcher re-checks every job against its own allow-list
and runs only the argv this module built from validated arguments (never text from a model).

    A0 read      status, logs, stats, verify, inventory, n8n.list, n8n.executions
    A2 operate   restart, profile, n8n.import, n8n.activate, backup
    A3 sealed    n8n.create, profile with `turn_off` (another service switched off to make room):
                 a 🔏 `hub_op` card bound to the op and its arguments (`digest`); approving it queues
                 the job, rejecting it refuses it
    never        SSH, users, sudo, firewall, fail2ban, OpenBao, secrets and .env, the owner's
                 sign-in and secret targets, reboot, volume or database deletion: `policy_denied`
                 with the owner's step in plain Persian (DENIED)

Left out on purpose (the owner's call, 2026-11-06): `deploy` (a deploy stays a reviewed prompt and
the owner's seal; the dispatcher has no git) and `catalogue.refresh` (the hub has no make target for
it; a company's catalogue is `catalogue.start`).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from hq_api import events
from hq_api.audit import SYSTEM
from hq_api.audit import record as audit_record
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_common.redact import scrub

SERVICE = Principal(kind="service", code="hubops", role="service")
OUTPUT_MAX = 64 * 1024
SNAPSHOT_FRESH_S = 180  # an older snapshot is shown with its time; the page says so
CLAIM_GRACE_S = 300  # a claimed job not answered within its timeout plus this ends as failed

# ------------------------------------------------------------ the stack --
# The compose services of the hub's stack (infra/compose/compose.yaml and mcp.yaml; the test keeps
# the two equal). `logs` reads any of them; `restart` only an application service.
SERVICES: tuple[str, ...] = (
    "hq-tools", "backup-tools", "postgres", "valkey", "nats", "temporal-schema", "temporal",
    "temporal-namespace", "temporal-ui", "openbao", "db-provision", "llm-migrate", "llm-router",
    "claude-runtime", "api-migrate", "opa", "api", "worker", "gateway", "egress", "searxng",
    "browser", "web", "caddy", "prometheus", "loki", "alloy", "n8n", "grafana", "node-exporter",
    "tempo", "otel-collector", "stt-fetch", "ocr-fetch", "provisioner", "stt", "ocr",
    "substitute-runner", "browser-web", "browser-web-login", "web-login-relay", "tts",
    "media-courier", "media-render", "newsletter-provision", "listmonk", "cadvisor",
    "mcp-time", "mcp-codecortex", "mcp-codecortex-index",
)  # fmt: skip
# Never restarted from here: the database, the secrets vault, the front door (contract §38.1), the
# message and workflow backbones, and every one-shot (they run and exit by design).
NEVER_RESTART = frozenset({"postgres", "openbao", "caddy", "valkey", "nats", "temporal"})
ONE_SHOTS = frozenset({
    "hq-tools", "backup-tools", "temporal-schema", "temporal-namespace", "db-provision",
    "llm-migrate", "api-migrate", "stt-fetch", "ocr-fetch", "stt", "substitute-runner",
    "browser-web-login", "web-login-relay", "tts", "media-courier", "media-render",
    "newsletter-provision", "mcp-codecortex-index",
})  # fmt: skip
RESTARTABLE: tuple[str, ...] = tuple(
    s for s in SERVICES if s not in NEVER_RESTART and s not in ONE_SHOTS
)


@dataclass(frozen=True)
class Profile:
    """One optional service the owner (or a technical role) switches on and off."""

    key: str
    var: str  # its switch in infra/compose/.env
    compose: str  # its compose profile
    title_fa: str
    what_fa: str
    toggle: bool = True
    note_fa: str | None = None


PROFILES: dict[str, Profile] = {
    p.key: p
    for p in (
        Profile("media", "HQ_MEDIA", "media", "ساخت ویدیو و کاور",
                "ساخت ویدیو، کاور و تصویر برای خط‌های تولید و رسانه‌ها"),
        Profile("tts", "HQ_TTS", "tts", "صدای ساده‌ی هاب",
                "خواندن گزارش‌ها و پیام‌ها با صدای فارسی خود هاب (Piper)"),
        Profile("stt", "HQ_STT", "stt", "تبدیل گفتار به متن",
                "نوشتن پیام‌های صوتی تو؛ فقط وقتی پیامی میآید بالا میآید"),
        Profile("ocr", "HQ_OCR", "ocr", "خواندن اسکن بایگانی",
                "خواندن متن فایل‌های اسکن‌شده‌ی بایگانی"),
        Profile("newsletter", "HQ_NEWSLETTER", "newsletter", "خبرنامه",
                "خبرنامه‌ی ایمیلی شرکت‌ها (Listmonk)"),
        Profile("automations", "HQ_AUTOMATIONS", "automations", "اتوماسیون (n8n)",
                "کارهای قاعده‌محور خط‌های تولید و اتوماسیون‌ها با n8n"),
        Profile("mcp", "HQ_MCP", "mcp", "سرورهای MCP",
                "ابزارهای MCP در کانتینر (زمان و جستجوی کد)", toggle=False,
                note_fa="روشن کردن MCP از اینجا هنوز ممکن نیست: سرورهایش را سرور هاب یک‌بار میسازد "
                        "(make mcp-build) و جای حافظه‌اش تصمیم توست."),
        Profile("tracing", "HQ_TRACING", "tracing", "ردگیری درخواست‌ها",
                "ردگیری فنی درخواست‌ها برای پیدا کردن کندی‌ها (Tempo)"),
    )
}  # fmt: skip
CORE_FA = {
    "api": "هسته‌ی هاب",
    "worker": "کارگر پس‌زمینه",
    "gateway": "دروازه‌ی ابزارهای ایجنت‌ها",
    "llm-router": "مسیریاب مدل‌ها",
    "claude-runtime": "اجرای Claude",
    "postgres": "پایگاه داده",
    "openbao": "گاوصندوق رمزها",
    "caddy": "درِ ورودی (HTTPS)",
    "opa": "سیاست‌ها",
    "egress": "اینترنت ایجنت‌ها",
    "browser": "مرورگر ایجنت‌ها",
    "browser-web": "مرورگر ورودها",
    "web": "پنل وب",
    "valkey": "حافظه‌ی موقت",
    "nats": "صف پیام‌ها",
    "temporal": "گردش‌کارها",
    "searxng": "جستجوی وب",
    "prometheus": "پایش",
    "grafana": "داشبورد پایش",
    "loki": "لاگ‌ها",
}
PROFILE_RE = r"^(media|tts|stt|ocr|newsletter|automations|mcp|tracing)$"
WORKFLOW_RE = r"^[A-Za-z0-9]{1,40}$"
SINCE_RE = r"^[0-9]{1,4}[smh]$"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


# ----------------------------------------------------------- arguments --
class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(Args):
    pass


class LogsArgs(Args):
    service: str
    lines: int = Field(default=200, ge=1, le=500)
    since: str | None = Field(default=None, pattern=SINCE_RE)

    @field_validator("service")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in SERVICES:
            raise ValueError("not a service of the hub's stack")
        return v


class RestartArgs(Args):
    service: str

    @field_validator("service")
    @classmethod
    def _app(cls, v: str) -> str:
        if v not in RESTARTABLE:
            raise ValueError(
                "only an application service of the stack (never postgres, openbao, caddy)"
            )
        return v


class ProfileArgs(Args):
    name: str = Field(pattern=PROFILE_RE)
    on: StrictBool
    turn_off: list[str] = Field(default_factory=list, max_length=7)

    @model_validator(mode="after")
    def _off_first(self) -> ProfileArgs:
        for k in self.turn_off:
            if not re.match(PROFILE_RE, k) or k == self.name:
                raise ValueError("turn_off: other optional services only")
        if self.turn_off and not self.on:
            raise ValueError("turn_off goes with on: true")
        self.turn_off = sorted(set(self.turn_off))
        return self


class ExecutionsArgs(Args):
    workflow: str | None = Field(default=None, pattern=WORKFLOW_RE)
    limit: int = Field(default=20, ge=1, le=50)


class ActivateArgs(Args):
    workflow: str = Field(pattern=WORKFLOW_RE)
    on: StrictBool


class CreateArgs(Args):
    name: str = Field(min_length=1, max_length=120)
    workflow_json: dict[str, Any]

    @field_validator("name")
    @classmethod
    def _plain(cls, v: str) -> str:
        if _CONTROL.search(v) or not v.strip():
            raise ValueError("one plain line")
        return v.strip()

    @field_validator("workflow_json")
    @classmethod
    def _workflow(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(v.get("nodes"), list) or not v["nodes"]:
            raise ValueError("an n8n workflow: an object with nodes")
        if not isinstance(v.get("connections", {}), dict):
            raise ValueError("connections must be an object")
        if len(json.dumps(v, ensure_ascii=False)) > 200_000:
            raise ValueError("at most 200 KB")
        return v


# ----------------------------------------------------------- the catalogue --
Argv = list[str]
HQ = "infra/compose/hq.sh"
PS_FORMAT = "table {{.Service}}\t{{.State}}\t{{.Health}}\t{{.Status}}"


def _logs(a: LogsArgs) -> Argv:
    out = [HQ, "logs", "--no-color", "--tail", str(a.lines)]
    if a.since:
        out += ["--since", a.since]
    return [*out, a.service]


def _profile(a: ProfileArgs) -> Argv:
    return ["infra/hubops/profile.sh", a.name, "on" if a.on else "off", *a.turn_off]


@dataclass(frozen=True)
class Op:
    name: str
    cls: Literal["A0", "A2", "A3"]
    title_fa: str
    args: type[Args]
    argv: Callable[[Any], Argv]
    timeout_s: int = 300
    full_mask: bool = False  # logs: personal data masked too, not only credentials


OPS: dict[str, Op] = {
    o.name: o
    for o in (
        Op("status", "A0", "وضعیت سرویس‌های هاب", NoArgs,
           lambda a: [HQ, "ps", "--all", "--format", PS_FORMAT], 60),
        Op("logs", "A0", "لاگ یک سرویس", LogsArgs, _logs, 60, full_mask=True),
        Op("stats", "A0", "حافظه و پردازنده‌ی هر سرویس", NoArgs,
           lambda a: ["infra/hubops/snapshot.sh"], 90),
        Op("verify", "A0", "سنجش زنده‌ی هاب", NoArgs, lambda a: ["make", "verify-live"], 900),
        Op("inventory", "A0", "فهرست اتصال‌ها", NoArgs,
           lambda a: ["infra/hubops/inventory.sh"], 180),
        Op("n8n.list", "A0", "فهرست workflowهای n8n", NoArgs,
           lambda a: ["infra/hubops/n8n.sh", "list"], 120),
        Op("n8n.executions", "A0", "اجراهای n8n", ExecutionsArgs,
           lambda a: ["infra/hubops/n8n.sh", "executions", str(a.limit),
                      *([a.workflow] if a.workflow else [])], 60),
        Op("restart", "A2", "راه‌اندازی دوباره‌ی یک سرویس", RestartArgs,
           lambda a: [HQ, "restart", a.service], 300),
        Op("profile", "A2", "روشن یا خاموش کردن یک سرویس", ProfileArgs, _profile, 2400),
        Op("n8n.import", "A2", "وارد کردن workflowهای مخزن به n8n", NoArgs,
           lambda a: ["make", "n8n-import"], 600),
        Op("n8n.activate", "A2", "روشن یا خاموش کردن یک workflow", ActivateArgs,
           lambda a: ["infra/hubops/n8n.sh", "activate", a.workflow, "on" if a.on else "off"], 300),
        Op("backup", "A2", "پشتیبان‌گیری همین حالا", NoArgs,
           lambda a: ["make", "backup-hourly"], 3600),
        Op("n8n.create", "A3", "ساختن یک workflow تازه در n8n", CreateArgs,
           lambda a: ["infra/hubops/n8n.sh", "create", "@workflow_json"], 300),
    )
}  # fmt: skip

# Never in the catalogue (contract §38.1): the owner's own step for each, in plain Persian.
_STEP_SSH = (
    "دسترسی SSH، کاربرها و sudo فقط کار خود توست، از ترمینال خودت؛ هیچ ایجنتی به آن دست نمیزند."
)
_STEP_FW = "فایروال فقط از کنسول هتزنر و به دست تو تنظیم میشود."
_STEP_BAO = "گاوصندوق رمزها (OpenBao) فقط با توست: باز کردنش با make unseal از ترمینال خودت."
_STEP_KEYS = (
    "رمزها و کلیدها هرگز از اینجا خوانده یا نوشته نمیشوند: برای گذاشتن یک کلید، صفحه‌ی همان "
    "اتصال در اپ، یا هدف make همان رمز از ترمینال خودت (مثلاً make account-secret KEY=…)."
)
_STEP_LOGIN = (
    "ورود به حساب‌ها کار خود توست: make <نام>-web-login از ترمینال خودت با تونل، و پنجره‌اش "
    "در 127.0.0.1:6080."
)
_STEP_DELETE = (
    "پاک کردن داده، volume یا پایگاه داده از اینجا ممکن نیست؛ اگر لازم است، با سرور هاب و مُهر خودت."
)
DENIED: dict[str, str] = {
    "ssh": _STEP_SSH,
    "users": _STEP_SSH,
    "user": _STEP_SSH,
    "sudo": _STEP_SSH,
    "sudoers": _STEP_SSH,
    "firewall": _STEP_FW,
    "ufw": _STEP_FW,
    "iptables": _STEP_FW,
    "docker-user": _STEP_FW,
    "fail2ban": _STEP_FW,
    "openbao": _STEP_BAO,
    "unseal": _STEP_BAO,
    "bao": _STEP_BAO,
    "root-token": _STEP_BAO,
    "policies": _STEP_BAO,
    "secrets": _STEP_KEYS,
    "secret": _STEP_KEYS,
    "env": _STEP_KEYS,
    "gdrive-auth": "وصل کردن پشتیبان به Google Drive کار خود توست: make gdrive-auth از ترمینال خودت.",
    "reboot": "راه‌اندازی دوباره‌ی خود سرور فقط با اجازه و به دست توست.",
    "shutdown": "خاموش کردن سرور فقط با اجازه و به دست توست.",
    "volume.delete": _STEP_DELETE,
    "db.drop": _STEP_DELETE,
    "delete": _STEP_DELETE,
    "down": "پایین آوردن کل هاب از اینجا ممکن نیست؛ سرویس‌ها را یکی‌یکی با restart یا profile کار کن.",
    "exec": "دستور آزاد روی خود هاب در فهرست نیست؛ فقط کارهای همین فهرست. اگر کاری کم است، به سرور هاب بگو.",
    "shell": "دستور آزاد روی خود هاب در فهرست نیست؛ فقط کارهای همین فهرست. اگر کاری کم است، به سرور هاب بگو.",
    "deploy": (
        "deploy هنوز از اینجا نیست: هر deploy یک پرامپت بازبینی‌شده برای سرور هاب و مُهر توست. "
        "بخواه تا Claude سشن مشورت پرامپت deploy بنویسد."
    ),
    "catalogue.refresh": (
        "هاب برای تازه کردن فهرست هدفی ندارد؛ فهرست یک شرکت را با catalogue.start شروع کن."
    ),
}


def denied_step(op: str) -> str | None:
    """The owner's step for an operation that is never in the catalogue, else None."""
    low = op.strip().lower().replace("_", "-")
    if low in DENIED:
        return DENIED[low]
    if low.endswith("-login") or low.startswith("login"):
        return _STEP_LOGIN
    if low.endswith(("-secret", "-token")) or "password" in low:
        return _STEP_KEYS
    if low.startswith("owner-"):
        return "کارهای owner-* فقط از ترمینال خود توست."
    if low.startswith(("ssh", "user")):
        return _STEP_SSH
    return None


def _denied(op: str) -> ApiError:
    step = denied_step(op)
    return ApiError(
        403,
        "policy_denied",
        f"{op} is never a hub operation",
        message_fa=step or "این کار در فهرست کارهای هاب نیست.",
    )


@dataclass(frozen=True)
class Checked:
    op: Op
    args: dict[str, Any]
    argv: Argv
    cls: str
    digest: str


def check(op: str, args: dict[str, Any] | None) -> Checked:
    """The op and its arguments validated against the catalogue: 403 policy_denied with the
    owner's step for a denied one, 422 for an unknown op or bad arguments."""
    if op not in OPS:
        if denied_step(op) is not None:
            raise _denied(op)
        raise ApiError(
            422,
            "validation_failed",
            f"unknown hub operation: {op[:60]}",
            fields={"op": "one of " + ", ".join(OPS)},
            message_fa="این کار در فهرست کارهای هاب نیست.",
        )
    o = OPS[op]
    try:
        parsed = o.args.model_validate(args or {})
    except ValueError as exc:
        raise ApiError(422, "validation_failed", fields={"args": str(exc)[:300]}) from exc
    if isinstance(parsed, ProfileArgs) and not PROFILES[parsed.name].toggle:
        raise ApiError(409, "not_ready", f"{parsed.name} is not switched from here",
                       message_fa=PROFILES[parsed.name].note_fa)  # fmt: skip
    if isinstance(parsed, ProfileArgs) and any(not PROFILES[k].toggle for k in parsed.turn_off):
        raise ApiError(409, "not_ready", "mcp is not switched from here",
                       message_fa=PROFILES["mcp"].note_fa)  # fmt: skip
    data = json.loads(parsed.model_dump_json())
    cls: str = o.cls
    if isinstance(parsed, ProfileArgs) and parsed.turn_off:
        cls = "A3"  # §38.1 a profile that needs another off to fit: the owner's seal
    return Checked(o, data, o.argv(parsed), cls, digest(op, data))


def digest(op: str, args: dict[str, Any]) -> str:
    """What a 🔏 hub_op card is bound to: the op and its exact arguments."""
    raw = json.dumps(
        {"op": op, "args": args}, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def mask(text: str, *, full: bool = False) -> str:
    """Masked again on the hub (the dispatcher masked it on the host) and capped at 64 KB: the
    tail is kept, since a command's verdict comes last."""
    masked = scrub(text, secrets_only=not full)
    if len(masked.encode()) <= OUTPUT_MAX:
        return masked
    tail = masked.encode()[-(OUTPUT_MAX - 200) :].decode("utf-8", "ignore")
    return f"[… the first {len(masked) - len(tail)} characters were cut]\n" + tail


# ----------------------------------------------------------------- jobs --
JOB_SQL = (
    "SELECT j.*, c.code AS company FROM ops.hub_jobs j JOIN core.companies c ON c.id = j.company_id"
)
STATE_FA = {
    "queued": "در صف",
    "running": "در حال اجرا",
    "done": "انجام شد",
    "failed": "انجام نشد",
    "refused": "رد شد",
    "awaiting_seal": "منتظر مُهر مدیر کل",
}


async def holding(tx: Tx) -> dict[str, Any]:
    row = await tx.first(
        "SELECT id, code FROM core.companies WHERE kind = 'holding' ORDER BY created_at LIMIT 1"
    )
    if row is None:
        raise ApiError(503, "not_ready", "no holding company")
    return dict(row)


async def create(
    tx: Tx,
    c: Checked,
    *,
    by: Principal,
    holding_id: UUID,
    holding_code: str,
    state: str = "queued",
) -> dict[str, Any]:
    row = await tx.first(
        """INSERT INTO ops.hub_jobs (company_id, op, args, argv, digest, class, state, requested_kind,
               requested_by, employee_id, run_id, timeout_s)
           VALUES (:co, :op, CAST(:args AS jsonb), CAST(:argv AS jsonb), :dg, :cls, :st, :rk, :rb,
                   :emp, CAST(:run AS uuid), :to)
           RETURNING id""",
        co=holding_id,
        op=c.op.name,
        args=json.dumps(c.args, ensure_ascii=False),
        argv=json.dumps(c.argv),
        dg=c.digest,
        cls=c.cls,
        st=state,
        rk="owner" if by.is_owner else "agent",
        rb=by.code,
        emp=by.employee_id,
        run=by.run_id if by.run_id and re.match(r"^[0-9a-f-]{36}$", str(by.run_id)) else None,
        to=c.op.timeout_s,
    )
    assert row is not None
    j = await load(tx, row["id"])
    await audit_record(
        tx,
        by,
        company_id=holding_id,
        action="hub.op",
        action_class=c.cls,
        target_kind="hub_job",
        target_ref=j["ref"],
        summary=f"{c.op.name} {state}"[:300],
    )
    await _emit(tx, holding_code, j)
    return j


async def load(tx: Tx, id_or_ref: UUID | str, *, lock: bool = False) -> dict[str, Any]:
    key = (
        "j.ref = :k" if isinstance(id_or_ref, str) and id_or_ref.startswith("HJ-") else "j.id = :k"
    )
    row = await tx.first(
        JOB_SQL + f" WHERE {key}" + (" FOR UPDATE OF j" if lock else ""), k=id_or_ref
    )
    if row is None:
        raise ApiError(404, "not_found", "no such hub job")
    return dict(row)


async def _emit(tx: Tx, company: str, j: dict[str, Any]) -> None:
    await events.emit(
        tx,
        company,
        "hub.job",
        j["ref"],
        {"ref": j["ref"], "op": j["op"], "state": j["state"], "result_fa": j.get("result_fa")},
    )


async def seal_card(tx: Tx, j: dict[str, Any], c: Checked, *, by: Principal) -> dict[str, Any]:
    """The 🔏 `hub_op` card of an A3 job; the job waits in `awaiting_seal` until it is decided."""
    from hq_api.domain import decisions as D

    shown = dict(c.args)
    if "workflow_json" in shown:
        wf = shown["workflow_json"]
        shown["workflow_json"] = {
            "nodes": [str(n.get("type") or n.get("name") or "?") for n in wf.get("nodes", [])][:50],
            "size": len(json.dumps(wf, ensure_ascii=False)),
        }
    payload = {
        "job": j["ref"],
        "op": c.op.name,
        "args": mask_card(shown),
        "digest": c.digest,
        "argv": c.argv,
        "actor": {"kind": by.kind, "code": by.code},
    }
    din = D.DecisionIn(
        kind="hub_op",
        title=f"کار هاب با مُهر تو: {c.op.title_fa}"[:300],
        what=f"`{' '.join(c.argv)[:1500]}`\n\n{json.dumps(payload['args'], ensure_ascii=False)[:3000]}",
        why=f"این کار روی خود هاب است و بی مُهر تو اجرا نمیشود. درخواست از {by.code}.",
        risk="medium",
        reversible=c.op.name != "n8n.create",
        payload=payload,
    )
    h = await holding(tx)
    d = await D.propose(
        tx, SERVICE, company_id=h["id"], company_code=h["code"], body=din, thread_code=None
    )
    await tx.exec(
        """UPDATE ops.hub_jobs SET decision_ref = :d, state = 'awaiting_seal', updated_at = now()
           WHERE id = :id""",
        d=d["ref"],
        id=j["id"],
    )
    j = await load(tx, j["id"])
    await _emit(tx, h["code"], j)
    return j


def mask_card(args: dict[str, Any]) -> dict[str, Any]:
    from hq_common.redact import mask_secrets

    out: dict[str, Any] = mask_secrets(args)
    return out


async def on_decided(tx: Tx, d: dict[str, Any], verdict: str) -> None:
    """A `hub_op` card was decided: sealed and still bound to the same op and arguments -> queued;
    rejected, returned or changed -> refused."""
    rows = await tx.all(JOB_SQL + " WHERE j.decision_ref = :d FOR UPDATE OF j", d=d["ref"])
    for j in rows:
        if j["state"] != "awaiting_seal":
            continue
        bound = (d.get("payload") or {}).get("digest") == j["digest"]
        if verdict == "approved" and bound:
            await tx.exec(
                "UPDATE ops.hub_jobs SET state = 'queued', updated_at = now() WHERE id = :id",
                id=j["id"],
            )
        else:
            await tx.exec(
                """UPDATE ops.hub_jobs SET state = 'refused', finished_at = now(), updated_at = now(),
                       error_code = :e, result_fa = :r WHERE id = :id""",
                id=j["id"],
                e="seal_refused" if bound else "seal_mismatch",
                r="مدیر کل این کار را تأیید نکرد" if bound else "کارت با این کار نمیخواند",
            )
        j = await load(tx, j["id"])
        await _emit(tx, j["company"], j)
    await audit_record(
        tx,
        SYSTEM,
        company_id=d["company_id"],
        action="hub.seal",
        action_class="A3",
        target_kind="decision",
        target_ref=d["ref"],
        summary=f"{verdict}: {len(rows)} hub job(s)",
    )


async def claim(tx: Tx) -> dict[str, Any]:
    """The dispatcher's next job, one at a time; none while the holding's kill switch is engaged."""
    from hq_api.domain import gate

    if await gate.holding_lock(tx) == "holding":
        return {"job": None, "skipped": "holding_locked"}
    lost = await tx.all(
        """UPDATE ops.hub_jobs SET state = 'failed', finished_at = now(), updated_at = now(),
               error_code = 'timeout', result_fa = 'اجراکننده‌ی هاب جوابی نداد'
           WHERE state = 'running'
             AND started_at < now() - make_interval(secs => timeout_s + :grace)
           RETURNING ref""",
        grace=CLAIM_GRACE_S,
    )
    if lost:
        h = await holding(tx)
        for r in lost:
            await _emit(tx, h["code"], await load(tx, r["ref"]))
    if await tx.scalar("SELECT 1 FROM ops.hub_jobs WHERE state = 'running' LIMIT 1"):
        return {"job": None}
    row = await tx.first(
        """SELECT id FROM ops.hub_jobs WHERE state = 'queued'
           ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"""
    )
    if row is None:
        return {"job": None}
    await tx.exec(
        """UPDATE ops.hub_jobs SET state = 'running', started_at = now(), updated_at = now()
           WHERE id = :id""",
        id=row["id"],
    )
    j = await load(tx, row["id"])
    await _emit(tx, j["company"], j)
    return {
        "job": {
            "ref": j["ref"],
            "op": j["op"],
            "args": j["args"],
            "argv": j["argv"],
            "timeout_s": j["timeout_s"],
        }
    }


class DoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exit_code: int = Field(ge=-1, le=255)
    output: str = Field(default="", max_length=2 * OUTPUT_MAX)
    refused: str | None = Field(default=None, pattern=r"^[a-z_]{1,40}$")


def result_fa(j: dict[str, Any], state: str, refused: str | None = None) -> str:
    if j["op"] == "profile":
        a = j["args"] or {}
        if state == "done":
            return "روشن شد" if a.get("on") else "خاموش شد"
        if state == "refused" and not refused:
            # Only hq.sh's own over-budget answer (exit 3) means no memory room;
            # the dispatcher's refusal falls through to the generic text.
            return "جا نیست؛ این‌ها جا را گرفته‌اند"
    if state == "done":
        return "انجام شد"
    if state == "refused":
        return "اجراکننده‌ی هاب این کار را نپذیرفت"
    return "انجام نشد"


async def finish(tx: Tx, ref: str, body: DoneIn) -> dict[str, Any]:
    """The dispatcher's answer (idempotent for a job already finished)."""
    j = await load(tx, ref, lock=True)
    if j["state"] in ("done", "failed", "refused"):
        return j
    if j["state"] != "running":
        raise ApiError(409, "job_finished", f"{ref} is {j['state']}")
    op = OPS.get(j["op"])
    output = mask(body.output, full=bool(op and op.full_mask))
    blocking: list[dict[str, Any]] = []
    if body.refused:
        state = "refused"
    elif j["op"] == "profile" and body.exit_code == 3:
        state = "refused"  # hq.sh's own answer over the memory budget
    elif body.exit_code == 0:
        state = "done"
    else:
        state = "failed"
    if j["op"] == "inventory" and state == "done":
        output = mask(json.dumps(await inventory(tx, output), ensure_ascii=False, default=str))
    if j["op"] == "profile" and state == "refused" and not body.refused:
        blocking = await blocking_for(tx, str((j["args"] or {}).get("name")))
    await tx.exec(
        """UPDATE ops.hub_jobs SET state = :st, output = :out, exit_code = :ec, result_fa = :r,
               blocking = CAST(:b AS jsonb), error_code = :e, finished_at = now(), updated_at = now()
           WHERE id = :id""",
        id=j["id"],
        st=state,
        out=output,
        ec=body.exit_code,
        r=result_fa(j, state, body.refused),
        b=json.dumps(blocking, ensure_ascii=False),
        e=body.refused or ("over_budget" if state == "refused" else None),
    )
    j = await load(tx, j["id"])
    await audit_record(
        tx,
        SERVICE,
        company_id=j["company_id"],
        action="hub.op_done",
        action_class=j["class"],
        target_kind="hub_job",
        target_ref=j["ref"],
        summary=f"{j['op']} {state} exit={body.exit_code}",
    )
    await _emit(tx, j["company"], j)
    return j


def view(j: dict[str, Any], *, with_output: bool = True) -> dict[str, Any]:
    """A job as its requester (and the owner) sees it."""
    op = OPS.get(j["op"])
    out: dict[str, Any] = {
        "ref": j["ref"],
        "op": j["op"],
        "title_fa": op.title_fa if op else j["op"],
        "class": j["class"],
        "state": j["state"],
        "state_fa": STATE_FA.get(j["state"], j["state"]),
        "args": mask_card(_card_args(j["args"] or {})),
        "requested_by": j["requested_by"],
        "decision_ref": j.get("decision_ref"),
        "result_fa": j.get("result_fa"),
        "blocking": j.get("blocking") or [],
        "exit_code": j.get("exit_code"),
        "created_at": j["created_at"],
        "finished_at": j.get("finished_at"),
    }
    if with_output:
        out["output"] = j.get("output")
    return out


def _card_args(a: dict[str, Any]) -> dict[str, Any]:
    if "workflow_json" in a:
        a = {**a, "workflow_json": "(the sealed workflow)"}
    return a


# ------------------------------------------------------------ snapshot --
class SnapshotIn(BaseModel):
    """The dispatcher's look at the host (infra/hubops/snapshot.sh)."""

    model_config = ConfigDict(extra="ignore")
    profile: str | None = Field(default=None, max_length=20)
    memory: dict[str, Any] | None = None
    services: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    switches: dict[str, str] = Field(default_factory=dict)


async def store_snapshot(tx: Tx, s: SnapshotIn) -> None:
    h = await holding(tx)
    data = mask_card(json.loads(s.model_dump_json()))
    await tx.exec(
        """INSERT INTO ops.hub_snapshot (company_id, at, data) VALUES (:co, now(), CAST(:d AS jsonb))
           ON CONFLICT (company_id) DO UPDATE SET at = now(), data = EXCLUDED.data""",
        co=h["id"],
        d=json.dumps(data, ensure_ascii=False)[:190_000],
    )


async def snapshot(tx: Tx) -> dict[str, Any] | None:
    row = await tx.first(
        """SELECT s.at, s.data FROM ops.hub_snapshot s
           JOIN core.companies c ON c.id = s.company_id WHERE c.kind = 'holding' LIMIT 1"""
    )
    return {"at": row["at"], **(row["data"] or {})} if row else None


def _num(v: Any) -> float | None:
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def _caps(snap: dict[str, Any] | None) -> dict[str, float]:
    """Each optional service's memory cap (the sum of its compose profile's limits)."""
    out: dict[str, float] = {}
    for s in (snap or {}).get("services") or []:
        cap = _num(s.get("cap_mb")) or 0.0
        for prof in s.get("profiles") or []:
            for p in PROFILES.values():
                if p.compose == prof:
                    out[p.key] = out.get(p.key, 0.0) + cap
    return out


def _used(snap: dict[str, Any] | None, key: str) -> float | None:
    p = PROFILES[key]
    used = [
        _num(s.get("mem_used_mb"))
        for s in (snap or {}).get("services") or []
        if p.compose in (s.get("profiles") or []) and s.get("mem_used_mb") is not None
    ]
    vals = [u for u in used if u is not None]
    return round(sum(vals), 1) if vals else None


def _switch(snap: dict[str, Any] | None, key: str) -> str:
    return str(((snap or {}).get("switches") or {}).get(key) or "off")


async def blocking_for(tx: Tx, key: str) -> list[dict[str, Any]]:
    """The optional services that are on (other than `key`), largest cap first (§38.3)."""
    snap = await snapshot(tx)
    caps = _caps(snap)
    on = [
        {"key": k, "title_fa": p.title_fa, "mem_cap_mb": caps.get(k, 0.0)}
        for k, p in PROFILES.items()
        if k != key and p.toggle and _switch(snap, k) == "on"
    ]
    return sorted(on, key=lambda x: -float(x["mem_cap_mb"] or 0))


async def services(tx: Tx) -> dict[str, Any]:
    """`GET /hub/services`: each optional service with its switch and memory, the core ones, and the
    memory of the hub from the dispatcher's latest snapshot (null while it never reported)."""
    snap = await snapshot(tx)
    caps = _caps(snap)
    pending = await tx.all(
        """SELECT args ->> 'name' AS k, state FROM ops.hub_jobs
           WHERE op = 'profile' AND state IN ('queued', 'running', 'awaiting_seal')"""
    )
    starting = {r["k"] for r in pending}
    last = await tx.all(
        """SELECT DISTINCT ON (args ->> 'name') args ->> 'name' AS k, state FROM ops.hub_jobs
           WHERE op = 'profile' ORDER BY args ->> 'name', created_at DESC"""
    )
    failed = {r["k"] for r in last if r["state"] == "failed"}
    out = []
    for k, p in PROFILES.items():
        on = _switch(snap, k) == "on"
        state = (
            "starting" if k in starting else ("on" if on else ("failed" if k in failed else "off"))
        )
        out.append(
            {
                "key": k,
                "title_fa": p.title_fa,
                "what_fa": p.what_fa,
                "state": state,
                "optional": True,
                "mem_cap_mb": caps.get(k, 0.0),
                "mem_used_mb": _used(snap, k),
                "can_toggle": p.toggle and snap is not None,
                "note_fa": p.note_fa
                if not p.toggle
                else (None if snap is not None else "بخش هاب هنوز نصب نشده است"),
            }
        )
    for s in (snap or {}).get("services") or []:
        if s.get("profiles") or s.get("one_shot") or s.get("service") not in SERVICES:
            continue
        name = str(s["service"])
        out.append(
            {
                "key": name,
                "title_fa": CORE_FA.get(name, name),
                "what_fa": "بخشی از هسته‌ی هاب؛ همیشه روشن",
                "state": "on" if s.get("state") == "running" else "failed",
                "optional": False,
                "mem_cap_mb": _num(s.get("cap_mb")) or 0.0,
                "mem_used_mb": _num(s.get("mem_used_mb")),
                "can_toggle": False,
                "note_fa": None,
            }
        )
    mem = (snap or {}).get("memory")
    memory = None
    if isinstance(mem, dict) and mem.get("total_mb") is not None:
        memory = {
            "total_mb": _num(mem.get("total_mb")),
            "budget_mb": _num(mem.get("budget_mb")),
            "caps_mb": _num(mem.get("caps_mb")),
            "free_mb": _num(mem.get("free_mb")),
        }
    return {"memory": memory, "services": out, "at": (snap or {}).get("at")}


# ------------------------------------------------------------ inventory --
async def _safe(tx: Tx, fn: Callable[..., Any], *args: Any) -> Any:
    try:
        async with tx.conn.begin_nested():
            return await fn(tx, *args)
    except Exception:  # noqa: BLE001 - a part that cannot be read is reported unknown
        return None


async def _players(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all(
        "SELECT player, status, login_state, web_state FROM substitutes.players ORDER BY player"
    )
    return [dict(r) for r in rows]


async def _voice(tx: Tx) -> dict[str, Any]:
    rows = await tx.all("SELECT provider, state, secret_set FROM talk.engine_state")
    google = [r for r in rows if r["provider"] == "google"]
    return {
        "google_key": "yes"
        if any(r["secret_set"] for r in google)
        else ("no" if google else "unknown"),
        "engines": [{"provider": r["provider"], "state": r["state"]} for r in rows],
    }


async def _connections(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT c.code AS company, g.kind, g.state FROM growth.connections g
           JOIN core.companies c ON c.id = g.company_id ORDER BY c.code, g.kind"""
    )
    return [dict(r) for r in rows]


async def _runners(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT c.code AS company, s.name, s.state, s.runner_version, s.last_seen_at
           FROM infra.servers s JOIN core.companies c ON c.id = s.company_id
           WHERE s.state IS NOT NULL ORDER BY c.code, s.name"""
    )
    return [dict(r) for r in rows]


async def _backups(tx: Tx) -> dict[str, Any]:
    row = await tx.first(
        """SELECT max(at) FILTER (WHERE ok) AS last_ok, max(at) AS last FROM backup.runs r
           JOIN core.companies c ON c.id = r.company_id WHERE c.kind = 'holding'"""
    )
    return {"last_ok_at": row["last_ok"], "last_at": row["last"]} if row else {}


async def _aistudio(tx: Tx) -> str:
    from hq_api.domain import speech_make as SM

    return str((await SM.speech_state(tx)).get("aistudio") or "unknown")


def _row(section: str, item: str, state: str, detail: str = "") -> dict[str, str]:
    return {"section": section, "item": item, "state": state, "detail": detail[:200]}


async def inventory(tx: Tx, host_text: str) -> dict[str, Any]:
    """The §25.2 connection table (names and states only): the host's part from the dispatcher
    (infra/hubops/inventory.sh: switches, services, n8n, memory), the rest from the hub's rows."""
    try:
        host = json.loads(host_text.strip().splitlines()[-1]) if host_text.strip() else {}
    except ValueError:
        host = {}
    host = host if isinstance(host, dict) else {}
    rows: list[dict[str, str]] = []
    for p in await _safe(tx, _players) or []:
        signed = "signed_in" in (p.get("login_state"), p.get("web_state"))
        state = "connected" if signed and p.get("status") == "ready" else "not_connected"
        detail = f"status={p.get('status')} login={p.get('login_state')} web={p.get('web_state')}"
        rows.append(_row("players", str(p["player"]), state, detail))
    rows.append(_row("sign_ins", "aistudio-web", str(await _safe(tx, _aistudio) or "unknown")))
    rows.append(_row("sign_ins", "pinterest-web", "unknown", "the hub keeps no state of it"))
    voice = await _safe(tx, _voice) or {}
    key = {"yes": "connected", "no": "not_connected"}.get(voice.get("google_key", ""), "unknown")
    rows.append(_row("voice", "google key (kv/hq/voice/google)", key))
    switches: dict[str, Any] = host["switches"] if isinstance(host.get("switches"), dict) else {}
    for k, v in sorted(switches.items()):
        rows.append(_row("switches", str(k), "on" if v == "on" else "off"))
    n8n: dict[str, Any] = host["n8n"] if isinstance(host.get("n8n"), dict) else {}
    if n8n:
        rows.append(_row("n8n", "n8n", str(n8n.get("health") or "unknown"),
                         f"workflows={n8n.get('workflows')} active={n8n.get('active')}"))  # fmt: skip
    for c in await _safe(tx, _connections) or []:
        rows.append(_row("connections", f"{c['company']} · {c['kind']}",
                         "connected" if c["state"] == "connected" else "not_connected"))  # fmt: skip
    for r in await _safe(tx, _runners) or []:
        rows.append(_row("runners", f"{r['company']} · {r['name']}",
                         "connected" if r["state"] == "online" else str(r["state"]),
                         f"version={r.get('runner_version')}"))  # fmt: skip
    b = await _safe(tx, _backups) or {}
    last = b.get("last_ok_at")
    fresh = isinstance(last, datetime) and datetime.now(UTC) - last < timedelta(hours=26)
    rows.append(_row("backups", "hourly backup", "connected" if fresh else "not_connected",
                     f"last_ok={last.isoformat() if isinstance(last, datetime) else None}"))  # fmt: skip
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return {
        "at": datetime.now(UTC).isoformat(),
        "counts": counts,
        "rows": rows,
        "services": host.get("services"),
        "memory": host.get("memory"),
    }


# -------------------------------------------------------------- who --
TECH_CHARTERS = frozenset({"aiops_head", "hub_platform_sre"})


def is_technical(who: Principal, *, holding_id: UUID | None) -> bool:
    """§38.1 the holding's technical people: the AI operations head, the platform SRE, the
    holding's own CTO (a CTO of an operating company works on its company's servers instead)."""
    if not who.is_agent:
        return False
    if who.charter in TECH_CHARTERS and who.scope == "holding":
        return True
    return who.charter == "cto" and holding_id is not None and who.company_id == holding_id
