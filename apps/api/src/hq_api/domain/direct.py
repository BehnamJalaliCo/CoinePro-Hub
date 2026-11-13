"""⟨1.32⟩ §54 The direct session, step three: the holder is one Claude Code session with the
hub's tools (docs/SIMPLIFY_2026-11-10_DIRECT_SESSIONS.md §4.1 and §7.3).

The owner, 2026-11-10: «مثل همین سشنی که من با تو صحبت میکنم … توی شرکت هم همین اشتراک کلود هست و
همین مدل‌ها، پس نباید انقدر پیچیده باشه». Until now a session's holder was a short run of a model
that could only name a tool to call, six steps at a time, re-reading the session on every wake,
and that handed anything with hands to the workshop and waited. From here the holder's run **is**
a turn on the workshop: one brain, one thread, the same Claude session and the same folder on
every word of the owner's, up to 60 minutes a turn.

What does not change:
- **Everything of the hub goes through the Tool Gateway.** The session reaches the hub's data
  and actions only by its role's own tools (`mcp__hq__…`): the runner relays each call to the
  api, the worker hands it to the gateway with a token minted for the turn's own run, and the
  gateway decides as it does for any agent (the policy, the classes A0 to A4, the kill switch,
  the audit row). The runner's own token never goes behind the workshop's wall.
- **The Treasury sees every token** (the turn's usage comes with its result, as any workshop
  turn's), on the hub's Claude account of the moment, chosen by the hub.
- The companies' data stay apart (the wall of §43.9, the tools' own company checks), a turn
  has its hour and is never silent, and the passkey is for money, deleting for good, keys and
  access, and a destructive command (the PreToolUse hook still classifies every command).

How it starts: the holder's own run of an order's root work (whatever woke it: the owner's
word, a colleague's delivery, «ادامه بده») is handed over when the workshop can take it
(`Runner.execute` → `hand_over`): a turn of that work, the classic run finished at once. When
the workshop cannot (not paired, not online, a runner older than RUNNER_MIN, the workspace on a
company's own server), the run goes on as before: nothing ever waits for the workshop.

Roles are skills here, not seats: the session reads any role's guide with `skill_read` and does
the work itself; nobody is hired to make a reel.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import hands as HANDS
from hq_api.domain import order_report as OR
from hq_api.domain import servers as SV
from hq_api.domain import work as W
from hq_api.domain import workspace as WS
from hq_api.errors import ApiError
from hq_api.principal import Principal

log = logging.getLogger("hq_api.direct")

RUNNER_MIN = "0.3.5"  # the runner that gives a session the hub's tools
REASON = "direct:"  # the turn's own run: direct:<order ref>
TOOLS = "hub"
SERVER_NAME = "hq"  # the MCP server's name in the session: its tools are mcp__hq__<name>
RUN_TTL_S = HANDS.TURN_TIMEOUT_S + 600
STEP_CALLS = 50  # tool calls a step of the run holds (the gateway's own cap per step)
CHARTER_CHARS = 6000
BRIEF_JSON_CHARS = 9000
# what the session is (the workshop) or what only the classic runtime speaks
SKIP_TOOLS = frozenset({"workshop.run", "workshop.stop"})
# a run that only tells the owner what a turn left stays the classic, quick one
CLASSIC_REASONS = (WS.FAILED_REASON, "direct_failed:")
SYSTEM_FA = "سامانه"
HANDED = "direct turn {job}"
WAITING = "direct turn waits: a turn of this session is still working"
WAITS_FA = (
    "مسئول هنوز روی نوبت قبلی است؛ حرفت بعد از آن خوانده میشود. برای قطع کردنش «توقف» را بزن."
)
EMPTY_FA = "این نوبت بی‌جواب تمام شد؛ اگر چیزی لازم است همین‌جا بگو."
SKILL_LIST = "skill_list"
SKILL_READ = "skill_read"
# ⟨2026-11-13⟩ The owner: «نه طوری باشه که مدل چیزی نفهمه و نه طوری باشه که هر بار فراخوانده بشه و
# میلیون‌ها توکن مصرف بشه». Every model call of a turn re-reads what the Claude session carries; on
# F-0018 it had grown to ~700K tokens, so a one-word «تأیید» re-read 2.2M. A session that carries
# more than ROTATE_TOKENS (what its turns wrote to the cache, an upper bound) is ended between two
# turns: the session's memory is caught up first, and the next turn is a fresh Claude session in
# the same folder that starts from the memory, the folder's NOTES.md, the session's state and the
# owner's last words.
ROTATE_TOKENS = 250_000
NOTES_FILE = "NOTES.md"

RULES_FA = (
    "قاعده‌های این جلسه:",
    "- پاسخ نهایی هر نوبت همان حرف تو به مدیر کل در جلسه است: فارسی، ساده، کوتاه و مناسب گوشی. "
    "بگو چه کردی، چه چیزی آماده است، و اگر چیزی فقط با اوست یک سؤال کوتاه بپرس. واژه‌ی فنی، نام "
    "ابزار و نشانی سرور ننویس.",
    "- خودت کار را انجام بده. ارجاع، کارت درونی و فرستادن کار به نقش دیگر فقط وقتی که مدیر کل "
    "خودش بگوید چه کسی انجام دهد، یا کار اختیاری بخواهد که نداری (در یک خط همین را بگو).",
    "- هر فایل تحویلی را در پوشه‌ی out/ بگذار؛ فقط همین فایل‌ها با لینک در جلسه به مدیر کل "
    "میرسند (ویدیو تا ۲۰۰MB و ۱۰ دقیقه، تصویر، PDF، متن، ZIP، صدا). بسته‌ی انتشار: ویدیو، "
    "cover.jpg، caption.txt و اگر کلمه‌ی کامنت دارد comment.txt، و topic.txt.",
    "- منتشر نکن، پول نده، به کسی بیرون پیام نده و حساب نساز: انتشار با «تأیید و انتشار» خود مدیر "
    "کل روی همان فایل است. هر چه بیرون میرود و برنمیگردد پیشنهاد (propose) میشود.",
    "- هر چه از ستاد میخواهی (عدد، اتصال، فایل جلسه، صدای گوینده، ثبت موضوع، پرسیدن از مدیر کل، "
    "روال دائمی) فقط از ابزارهای ستاد بگیر؛ به پایگاه داده یا سرویس ستاد راه دیگری نداری.",
    "- هیچ رمز و کلیدی را چاپ نکن. هر دستور ویرانگر منتظر مُهر مدیر کل میماند؛ دورش نزن.",
    "- حدود ۵۵ دقیقه وقت داری. اگر کار بزرگ است، اول نسخه‌ای کامل و دیدنی در out/ بگذار، بعد "
    "بهترش کن. فایل موقت را در همین پوشه یا $TMPDIR بگذار.",
    f"- دفترچه‌ی جلسه: در پایان هر نوبت {NOTES_FILE} همین پوشه را به‌روز کن، حداکثر ۸۰ خط: "
    "تصمیم‌ها و سلیقه‌ی مدیر کل (دقیق، با همان تنظیم‌ها)، چه ساخته شد و کجای پوشه است، کار باز و "
    "قدم بعد. نشست بعدی ممکن است تازه باشد و فقط از همین دفترچه، حافظه‌ی جلسه و فایل‌ها ادامه میدهد.",
    "- هر چه میخوانی در حافظه‌ی نشست میماند و در هر قدم دوباره خوانده میشود: خروجی ابزار را کوتاه "
    "بخواه (head، tail، grep، حالت بی‌صدا)، لاگ و فایل بلند را کامل چاپ نکن و فایلی را که خواندی "
    "دوباره نخوان.",
)


def is_direct(j: dict[str, Any]) -> bool:
    return bool((j.get("args") or {}).get("direct"))


def mcp_name(tool: str) -> str:
    """A tool's name as the session calls it (MCP allows no dot): `order.ask` → `order_ask`."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", tool)[:64]


async def server_for(tx: Tx) -> dict[str, Any] | None:
    """The workshop when it can hold a direct turn now: online, its runner >= RUNNER_MIN."""
    server = await HANDS.workshop_server(tx)
    if server is None or SV.state_of(server) != "online":
        return None
    return server if WS.version_ok(server.get("runner_version"), RUNNER_MIN) else None


def principal(emp: dict[str, Any], run_id: Any = None) -> Principal:
    return Principal(
        kind="agent",
        code=str(emp["code"]),
        role=str(emp["kind"]),
        company=str(emp["company"]),
        company_id=emp["company_id"],
        department=emp.get("department"),
        employee_id=emp["id"],
        status=str(emp.get("status") or "active"),
        run_id=str(run_id) if run_id else None,
        charter=emp.get("role"),
    )


# ---------------------------------------------------------------- the brief --
def tools_of(lib: Any, role: str | None) -> list[str]:
    """The hub tools a direct session of this role holds: its charter's own (a role written on
    demand: its draft's), without what the session itself is."""
    held = list(lib.allowed(role)) if lib is not None else []
    known = getattr(lib, "tools", {}) or {}
    return [t for t in held if t in known and t not in SKIP_TOOLS]


async def library_for(tx: Tx, hub: Any, emp: dict[str, Any]) -> Any:
    """The charters with the company's own drafted roles (§22.5) when the holder's is one."""
    lib = hub.charters
    if lib is not None and lib.get(emp["role"]) is None:
        from hq_api.domain import role_drafts as RD

        lib = await RD.overlay(tx, lib, emp["company_id"], running=True)
    return lib


def skills_of(lib: Any) -> list[dict[str, str]]:
    """Every working role's guide, by its role and its Persian title."""
    roles = getattr(lib, "roles", {}) or {}
    return [
        {"role": r, "title_fa": c.title_fa} for r, c in sorted(roles.items()) if c.kind != "system"
    ]


def compose(
    w: dict[str, Any],
    emp: dict[str, Any],
    brief: dict[str, Any],
    *,
    charter: Any,
    tools: list[str],
    reason: str,
    first: bool,
    inputs: list[dict[str, Any]],
) -> str:
    """The turn's brief. The first turn of a session says who it is, the rules, its role's own
    guide and its tools; a later turn of the same Claude session only what is new (it remembers
    the rest), with the rules in one line."""
    title = str(emp.get("title_fa") or emp["code"])
    company = str(emp.get("company_name_fa") or emp["company"])
    said = [str(x) for x in brief.get("owner_said") or []]
    state = {
        k: brief[k]
        for k in ("order", "pace", "state", "owner_turn", "plan", "plan_next", "step_rule",
                  "steps", "blockers", "outputs", "files", "failed_cards", "playbooks",
                  "source_playbook", "related_sessions",
                  # ⟨2026-11-11⟩ what still works for the order outside, what ended unanswered
                  "waiting_on", "ended_without_answer")
        if brief.get(k)
    }  # fmt: skip
    lines: list[str] = []
    if first:
        lines += [
            f"# جلسه‌ی {brief.get('order')}: {w['title']}",
            "",
            f"تو {title} در {company} هستی و مسئول همین جلسه با مدیر کل (مالک هلدینگ). این جلسه "
            "«مستقیم» است: خودت کار را از اول تا آخر انجام میدهی، در همین نشست و همین پوشه، با "
            "یک کامپیوتر کامل (ffmpeg، Chromium با Playwright برای python، node، python، فونت "
            "IRANYekanX و اینترنت؛ هر چه کم داری در همین پوشه نصب کن، بی sudo) و با ابزارهای ستاد.",
            f"پوشه‌ی ماندگار این جلسه: {WS.path_of(w['ref'])}. نوبت بعد همین پوشه و همین نشست را میبیند.",
            "",
            *RULES_FA,
            "",
            "## ابزارهای ستاد",
            f"ابزارهای نقش خودت با نام mcp__{SERVER_NAME}__<نام> در دسترس تو هستند (نقطه‌ی نام "
            "ابزار خط زیر شده است: order.ask میشود order_ask). هر فراخوانی ثبت میشود و همان اجازه‌های "
            "نقش تو را دارد:",
            "، ".join(mcp_name(t) for t in tools) or "(ابزاری ثبت نشده)",
            f"راهنمای هر نقش دیگر (سناریست، موشن‌دیزاینر، سئو، …) را با {SKILL_LIST} و "
            f"{SKILL_READ} {{role}} بخوان و خودت همان کار را بکن؛ برای ساختن چیزی کسی استخدام نمیشود.",
        ]
        body = str(getattr(charter, "body", "") or "").strip()
        if body:
            lines += ["", "## راهنمای نقش تو", body[:CHARTER_CHARS]]
        if brief.get("continued"):
            lines += [
                "",
                "## ادامه‌ی همین جلسه در نشستی تازه",
                f"این جلسه پیش از این نوبت‌هایی داشته است. اول {NOTES_FILE} همین پوشه را بخوان، "
                "بعد «حافظه‌ی جلسه» و «وضع جلسه» پایین را؛ فایل‌های پوشه همان است. از همان‌جا که "
                "مانده ادامه بده و چیزی را که تصمیمش گرفته شده دوباره نپرس.",
            ]
        if brief.get("memory_md"):
            lines += ["", "## تا اینجا (حافظه‌ی جلسه)", str(brief["memory_md"])[:6000]]
        lines += ["", "## فرمان مدیر کل", str(brief.get("text") or "")[:1500]]
    else:
        lines += [
            f"# ادامه‌ی جلسه‌ی {brief.get('order')} (همان نشست، همان پوشه)",
            "",
            "قاعده‌ها همان است: پاسخ نهایی کوتاه و فارسی برای مدیر کل؛ فایل تحویلی در out/؛ منتشر "
            "نکن؛ هر چه از ستاد است از ابزارهای ستاد؛ خروجی ابزار کوتاه؛ در پایان نوبت "
            f"{NOTES_FILE} را به‌روز کن.",
        ]
    if brief.get("wake"):
        # ⟨2026-11-11⟩ the hub woke this turn because nothing of the order runs: read it first
        lines[1:1] = ["", "## بیدارباش ستاد (اول این را بخوان)", str(brief["wake"])]
    if inputs:
        lines += [
            "",
            f"**فایل‌های ورودی این نوبت در پوشه‌ی {HANDS.IN_DIR}/ هستند** (از ستاد رسیده‌اند):",
            *[f"- {HANDS.IN_DIR}/{i['name']} ({i['mime']})" for i in inputs],
        ]
    packed = json.dumps(state, ensure_ascii=False, default=str)
    lines += ["", "## وضع جلسه", packed[:BRIEF_JSON_CHARS]]
    if brief.get("direct_rule") and first:
        lines += ["", str(brief["direct_rule"])]
    if brief.get("async_rule"):
        lines += ["", str(brief["async_rule"])]
    lines += ["", "## چرا این نوبت", why_fa(reason)]
    if said:
        lines += ["", "## حرف مدیر کل (آخرین‌ها، آخری پایین)", *[f"- {s}" for s in said[-3:]]]
    return "\n".join(lines)


def why_fa(reason: str) -> str:
    """What woke the holder, in a line the session reads (⟨2026-11-11⟩ a re-queued run by the
    reason it retries)."""
    reason = OR.base_reason(reason)
    if reason.startswith("session_idle:"):
        return (
            "ستاد تو را بیدار کرد: روی این جلسه هیچ کاری در جریان نیست. طبق «بیدارباش ستاد» کار باز "
            "برنامه را همین حالا خودت پیش ببر یا یک سؤال کوتاه با order_ask از مدیر کل بپرس؛ فقط "
            "گزارش ننویس."
        )
    if reason.startswith("speech_done:"):
        return "صدای گوینده‌ای که خواسته بودی آماده شد (speech_make با همان job)؛ با آن ادامه بده."
    if reason.startswith("speech_failed:"):
        return "ساخت صدایی که خواسته بودی به نتیجه نرسید؛ دلیلش را ببین و بقیه‌ی کار را ادامه بده."
    if reason.startswith("creative_done:"):
        return "تصویری که از بازیکن بیرونی خواسته بودی تمام شد؛ نتیجه‌اش را ببین و ادامه بده."
    if reason.startswith(("owner_reply:", "owner_turn_over:")):
        return "مدیر کل همین حالا در جلسه حرف زد؛ همان را انجام بده یا جواب بده."
    if reason.startswith("nudge:"):
        return "مدیر کل «ادامه بده» را زد؛ کار بعدی برنامه را پیش ببر."
    if reason.startswith("pace:"):
        return "مدیر کل روش کار جلسه را عوض کرد؛ طبق همان ادامه بده."
    if reason.startswith("session_reopened:"):
        return "مدیر کل جلسه را دوباره باز کرد."
    if reason.startswith("joined:"):
        return "یک نفر تازه به جلسه آمد؛ کار را با همان برنامه ادامه بده."
    if reason.startswith(WS.DONE_REASON):
        return "نوبت قبلی کارگاه تمام شد؛ خروجی‌اش را نگاه کن و به مدیر کل نشان بده."
    return "کاری روی این جلسه برای تو رسیده است؛ برنامه را ادامه بده و هر چه شد به مدیر کل بگو."


# ----------------------------------------------------------- the hand-over --
async def _new_files(tx: Tx, rep: dict[str, Any], ws: dict[str, Any] | None) -> list[str]:
    """The owner's files of the session a turn has not carried yet (newest first, at most
    INPUTS_MAX): a turn finds them in `in/`."""
    from hq_api.domain import files as F

    rows = await F.of_order(tx, rep["order_id"])
    ids = [str(f["id"]) for f in rows if f.get("id")]
    if not ids:
        return []
    sent: set[str] = set()
    if ws is not None and ws.get("session_id") is not None:
        jobs = await tx.all(
            "SELECT args FROM infra.server_jobs WHERE session_id = :s ORDER BY created_at DESC LIMIT 50",
            s=ws["session_id"],
        )
        for j in jobs:
            args = OR._j(j["args"]) or {}
            sent.update(str(i.get("file_id")) for i in args.get("inputs") or [])
    return [i for i in ids if i not in sent][: HANDS.INPUTS_MAX]


async def _say_once(tx: Tx, rep: dict[str, Any], text: str) -> None:
    steps = OR._j(rep.get("steps")) or []
    last = steps[-1] if steps else {}
    if isinstance(last, dict) and last.get("what_fa") == text:
        return
    await OR._append_steps(tx, rep["id"], [OR._step(SYSTEM_FA, text)])


async def hand_over(hub: Any, run: dict[str, Any], emp: dict[str, Any]) -> str | None:
    """A claimed run of a session's holder becomes a direct turn on the workshop. Returns the
    note the classic run ends with (it did nothing itself), or None: the run goes on as before.
    Never raises: a hand-over that cannot be made is a classic run."""
    if not getattr(hub.settings, "direct_sessions", True):
        return None
    if run.get("trigger") != "work" or run.get("work_id") is None:
        return None
    reason = str(run.get("reason") or "")
    if OR.base_reason(reason).startswith(CLASSIC_REASONS):
        return None  # ⟨2026-11-11⟩ a re-queued one too (`requeue:workspace_failed:…`)
    try:
        await rotate_if_heavy(hub, run["work_id"])
    except Exception:  # a session that stays long costs more, it never stops the turn
        log.exception("session rotation failed", extra={"run_id": str(run["id"])})
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            return await _hand_over(tx, hub, run, emp, reason)
    except ApiError as exc:
        log.info("no direct turn", extra={"run_id": str(run["id"]), "code": exc.code})
    except Exception:
        log.exception("direct hand-over failed", extra={"run_id": str(run["id"])})
    return None


async def _hand_over(
    tx: Tx, hub: Any, run: dict[str, Any], emp: dict[str, Any], reason: str
) -> str | None:
    from hq_api.domain import order_turns as OT

    w = await W.load(tx, run["work_id"])
    if w["parent_id"] is not None or w["assignee_id"] != emp["id"] or w["status"] in W.CLOSED:
        return None
    ref = await OR.order_of_work(tx, w["id"])
    order = await OR.load_order(tx, ref) if ref else None
    if ref is None or order is None or str(w["ref"]) not in OR.root_refs(order):
        return None  # only the order's own work is the session's thread
    roots = OR.root_refs(order)
    if len(roots) > 1 and str(w["ref"]) != roots[0]:
        # ⟨2026-11-13⟩ one brain per session: the lead holder's turn is the workshop's; a
        # colleague company's part of the same order is its classic run (it may still call
        # workshop.run for what needs hands), not a second Opus session answering every word
        return None
    rep = await OR.ensure(tx, ref)
    if rep is None or rep.get("ended_at") is not None:
        return None
    server = await server_for(tx)
    if server is None:
        return None
    ws = await WS.of_work(tx, w["id"], lock=True)
    if ws is not None and ws["server_id"] != server["id"]:
        return None  # it works on its company's own server
    owner_word = OR.base_reason(reason).startswith(OR.OWNER_WORD_REASONS)
    if (
        ws is not None
        and ws["state"] == "stopped"
        and not (owner_word and run["queued_at"] >= ws["updated_at"])
    ):
        return None  # he stopped it: only his own later word starts it again
    if ws is not None and await WS.busy_job(tx, ws) is not None:
        # one brain, one thread: his word is read when this turn ends (after_turn)
        if owner_word:
            await _say_once(tx, dict(rep), WAITS_FA)
        return WAITING
    lib = await library_for(tx, hub, emp)
    charter = lib.get(emp["role"]) if lib is not None else None
    if charter is None or charter.kind == "system":
        return None
    brief = await OT.talk_brief(tx, ref, work_id=w["id"], for_run=True) or {"order": ref}
    if ws is not None:
        brief["continued"] = True  # a fresh Claude session of a meeting that had turns
    rid = await tx.scalar(
        "SELECT agents.open_direct_run(:e, :w, :r, :ttl)",
        e=emp["id"], w=w["id"], r=f"{REASON}{ref}", ttl=RUN_TTL_S,
    )  # fmt: skip
    if rid is None:
        return WAITING
    who = principal(emp, rid)
    tools = tools_of(lib, emp["role"])
    files = await _new_files(tx, dict(rep), ws)

    def text_of(first: bool, inputs: list[dict[str, Any]]) -> str:
        return compose(w, emp, brief, charter=charter, tools=tools, reason=reason, first=first,
                       inputs=inputs)  # fmt: skip

    try:
        async with tx.conn.begin_nested():
            out = await HANDS.start(
                tx, who, server, w, brief="", title=f"{ref}: {w['title']}",
                files=files, direct={"direct": True, "tools": TOOLS, "run": str(rid),
                                     "order": ref},
                text_of=text_of,
            )  # fmt: skip
    except ApiError:
        await tx.scalar(
            "SELECT agents.close_direct_run(:r, 'failed', 'not_started', 0, 0, 0, 0, NULL)", r=rid
        )
        raise
    await events.emit(tx, str(emp["company"]), "order.updated", ref, {"direct": "working"})
    return HANDED.format(job=out.job)


# ------------------------------------------------------- a lean session (2026-11-13) --
async def carried_tokens(tx: Tx, session_id: Any) -> int:
    """What a Claude session carries, at most: every token its turns wrote to the prompt cache
    (a turn writes what it adds; a cache that expired is written again, so this only errs high)."""
    n = await tx.scalar(
        """SELECT COALESCE(SUM((usage->>'cache_write_tokens')::bigint), 0)
           FROM infra.server_jobs
           WHERE session_id = :s AND kind = 'claude'
             AND usage->>'cache_write_tokens' IS NOT NULL""",
        s=session_id,
    )
    return int(n or 0)


async def rotate_if_heavy(hub: Any, work_id: Any) -> bool:
    """Between two turns: a Claude session that carries more than ROTATE_TOKENS is ended, after
    the session's memory caught up with every turn, so the next turn starts a fresh session in
    the same folder (HANDS.start opens one; its brief is the first one with `continued`).
    True when it ended one."""
    from hq_api.domain import session_memory as MEM

    async with hub.db.tx(await hub.companies.ids()) as tx:
        ws = await WS.of_work(tx, work_id)
        if ws is None or ws.get("session_id") is None or ws["state"] in WS.ENDED:
            return False
        if await WS.busy_job(tx, ws) is not None:
            return False
        carried = await carried_tokens(tx, ws["session_id"])
        if carried <= ROTATE_TOKENS:
            return False
        ref = await OR.order_of_work(tx, work_id)
    if ref:
        await MEM.catch_up(hub, MEM.api_call(hub), ref)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        ended = await tx.exec(
            """UPDATE workshop.sessions SET state = 'done', finished_at = now()
               WHERE id = :s AND state NOT IN ('done', 'failed', 'stopped')
                 AND NOT EXISTS (SELECT 1 FROM infra.server_jobs j WHERE j.session_id = :s
                                   AND j.state IN ('queued', 'running'))""",
            s=ws["session_id"],
        )
        if not ended:
            return False
        w = await W.load(tx, work_id)
        await W.event(tx, w, "session_rotated", OR.SERVICE,
                      {"session": str(ws["session_id"]), "carried": carried})  # fmt: skip
    log.info("session rotated", extra={"work": str(work_id), "carried": carried})
    return True


_FOLDS: set[Any] = set()


def fold_soon(hub: Any, ref: str) -> None:
    """After a direct turn (the api, after its commit): the session's memory folded in the
    background when DIRECT_FOLD_EVERY turns came since the last fold. Without a worker (tests, a
    bare api) there is no model to fold with."""
    import asyncio

    from hq_api.domain import session_memory as MEM

    if getattr(hub, "temporal", None) is None:
        return
    task = asyncio.get_running_loop().create_task(
        MEM.fold(hub, MEM.api_call(hub), ref, every=MEM.DIRECT_FOLD_EVERY)
    )
    _FOLDS.add(task)
    task.add_done_callback(_FOLDS.discard)


# ------------------------------------------------------------- the turn's end --
def _usage(j: dict[str, Any]) -> tuple[int, int, int, int]:
    u = OR._j(j.get("usage")) or {}

    def n(*keys: str) -> int:
        for k in keys:
            v = u.get(k)
            if isinstance(v, int | float) and not isinstance(v, bool):
                return max(0, int(v))
        return 0

    return (
        n("input_tokens"), n("output_tokens"), n("cache_read_tokens", "cache_read_input_tokens"),
        n("cache_write_tokens", "cache_creation_input_tokens"),
    )  # fmt: skip


async def close_run(tx: Tx, j: dict[str, Any]) -> None:
    """The turn's own run ends with the job: done or failed, with what it spent."""
    rid = (j.get("args") or {}).get("run")
    if not rid:
        return
    ok = j["state"] == "done"
    i, o, cr, cw = _usage(j)
    closed = await tx.scalar(
        "SELECT agents.close_direct_run(CAST(:r AS uuid), :st, :code, :i, :o, :cr, :cw, :note)",
        r=str(rid), st="done" if ok else "failed",
        code=None if ok else (re.sub(r"[^a-z0-9_]", "_", str(j.get("error_code") or "failed"))[:40]
                              or "failed"),
        i=i, o=o, cr=cr, cw=cw, note=f"direct turn, job {j['id']}",
    )  # fmt: skip
    if closed:
        await _rest(tx, str(rid))


async def _rest(tx: Tx, rid: str) -> None:
    """⟨audit 2026-11-11⟩ The holder worked while the turn was open (the runner's finish of the
    handed-over run counts the turn as busy and leaves him `working`); once it ends and nothing
    else of his runs, he is shown at rest again."""
    emp = await tx.first(
        """SELECT e.id, e.code, c.code AS company FROM agents.runs r
           JOIN core.employees e ON e.id = r.employee_id
           JOIN core.companies c ON c.id = e.company_id
           WHERE r.id = CAST(:r AS uuid)""",
        r=rid,
    )
    if emp is None or await tx.scalar(
        """SELECT 1 FROM agents.runs WHERE employee_id = :e AND state = 'running'
             AND trigger <> 'talk'""",
        e=emp["id"],
    ):
        return
    if await tx.exec(
        """UPDATE core.employees SET activity = 'sleeping', activity_note = NULL,
               activity_at = now() WHERE id = :id AND activity = 'working'""",
        id=emp["id"],
    ):
        await events.emit(tx, str(emp["company"]), "activity.changed", emp["code"],
                          {"activity": "sleeping"})  # fmt: skip


async def pending_word(tx: Tx, ref: str, j: dict[str, Any]) -> bool:
    """Whether the owner spoke in the session after this turn was started (his word waited)."""
    rep = await tx.first("SELECT steps FROM owner.order_reports WHERE ref = :r", r=ref)
    from datetime import datetime

    for s in reversed(OR._j((rep or {}).get("steps")) or []):
        if not isinstance(s, dict) or s.get("who_fa") != "مدیر کل":
            continue
        try:
            at = datetime.fromisoformat(str(s.get("at")))
        except ValueError:
            return False
        return bool(at > j["created_at"])
    return False


async def after_turn(
    tx: Tx, hub: Any, j: dict[str, Any], w: dict[str, Any], *, answer: str, files: list[str]
) -> None:
    """A direct turn ended well: its answer is the holder's own word in the session (a line of
    the talk and a step), unless the turn already asked the owner something (`order.ask` wrote
    it). A word of his that waited for the turn starts the next one."""
    from hq_api.domain import order_turns as OT

    await close_run(tx, j)
    ref = str((j.get("args") or {}).get("order") or "") or await OR.order_of_work(tx, w["id"])
    rep = await OR.ensure(tx, ref) if ref else None
    if rep is None:
        return
    code = str(j["actor_code"])
    text = answer.strip()
    if SV.flagged_usage_limit(j):
        # ⟨2026-11-11⟩ a turn the account's usage limit ended (servers.usage_limited, the CLI's own
        # notice) never speaks as the holder (audit C1d); any other text is his word
        text = ""
    asked = bool(OR._j(rep.get("turn")))
    if text and not (asked and len(text) < 20):
        await OT.to_talk(tx, dict(rep), code, text[:6000])
        title = await tx.first(
            """SELECT e.title_fa, c.name_fa AS company_fa FROM core.employees e
               JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
            c=code,
        )
        who = OR.who_fa(title["title_fa"], title["company_fa"]) if title else code
        # the step is the session's own record, whatever the talk holds
        await OR._append_steps(tx, rep["id"], [OR._step(who, text[:500])])
    elif not text and not files and not asked:
        await OR._append_steps(tx, rep["id"], [OR._step(SYSTEM_FA, EMPTY_FA)])
    await events.emit(tx, w["company"], "order.updated", ref, {"direct": "idle"})
    if ref and await pending_word(tx, ref, j):
        await tx.scalar("SELECT work.wake_assignee(:w, :r)", w=w["id"], r=f"owner_reply:{ref}")


# ------------------------------------------------------------------ the tools --
def _turn_of(j: dict[str, Any]) -> dict[str, Any]:
    """The args of a job a runner asks tools for (its own server's, checked by the route): a
    live direct turn, or 422."""
    args = OR._j(j.get("args")) or {}
    if j["kind"] != "claude" or not args.get("direct") or not args.get("run"):
        raise ApiError(422, "validation_failed", "not a direct turn")
    return dict(args)


async def driver_of(tx: Tx, j: dict[str, Any]) -> dict[str, Any]:
    emp = await tx.first(
        """SELECT e.id, e.code, e.kind, e.status, e.role, e.title_fa, e.company_id,
                  c.code AS company FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
        c=str(j["actor_code"]),
    )
    if emp is None or emp["status"] != "active":
        raise ApiError(409, "validation_failed", "the turn's holder is not active")
    return dict(emp)


def pseudo_tools() -> list[dict[str, Any]]:
    """What the api itself answers (no gateway): the roles' guides, read as skills."""
    return [
        {
            "name": SKILL_LIST,
            "description": "The guides of every role of the holding (role and Persian title). "
            "Read one with skill_read and do that work yourself.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": SKILL_READ,
            "description": "The full guide of one role (its duties, standards and checklists), "
            "to do that role's work yourself in this session.",
            "input_schema": {
                "type": "object",
                "properties": {"role": {"type": "string", "description": "a role from skill_list"}},
                "required": ["role"],
                "additionalProperties": False,
            },
        },
    ]


def catalog_fallback(lib: Any, names: list[str]) -> list[dict[str, Any]]:
    """The tools as the charters' own catalog describes them, for when the gateway cannot be
    asked for their exact inputs: an open object (the gateway still checks every field)."""
    out = []
    for t in names:
        row = lib.tools.get(t)
        if row is None:
            continue
        out.append({
            "tool": t,
            "class": row.cls,
            "description": f"{row.description} Input: {row.input}"[:3000],
            "input_schema": {"type": "object", "additionalProperties": True},
        })  # fmt: skip
    return out


async def tools_for(tx: Tx, hub: Any, j: dict[str, Any]) -> list[dict[str, Any]]:
    """`GET /runners/jobs/{id}/tools`: what the session may call, each `{name, description,
    input_schema}` (`name` is what it calls; the hub maps it back)."""
    from hq_api import workflows_client

    _turn_of(j)
    emp = await driver_of(tx, j)
    lib = await library_for(tx, hub, emp)
    names = tools_of(lib, emp["role"])
    rows = await workflows_client.direct_tool(hub, {"op": "catalog", "tools": names})
    listed = (rows or {}).get("tools")
    if not isinstance(listed, list) or not listed:
        listed = catalog_fallback(lib, names)
    out = []
    for r in listed:
        if not isinstance(r, dict) or r.get("tool") not in names:
            continue
        cls = str(r.get("class") or "")
        out.append({
            "name": mcp_name(str(r["tool"])),
            "description": (f"[{cls}] " if cls else "") + str(r.get("description") or "")[:3000],
            "input_schema": r.get("input_schema")
            if isinstance(r.get("input_schema"), dict)
            else {"type": "object", "additionalProperties": True},
        })  # fmt: skip
    return [*out, *pseudo_tools()]


async def call(tx: Tx, hub: Any, j: dict[str, Any], name: str, args: Any) -> dict[str, Any]:
    """`POST /runners/jobs/{id}/tools/call`: one call of the session, carried to the Tool
    Gateway as the turn's holder (its run, its role's tools, the policy, the audit). Answers the
    gateway's own outcome `{outcome, class, code, ref, result?, hint_fa?, fields?}`."""
    from hq_api import workflows_client

    turn = _turn_of(j)
    emp = await driver_of(tx, j)
    lib = await library_for(tx, hub, emp)
    if name in (SKILL_LIST, SKILL_READ):
        return await skill(tx, lib, emp, name, args)
    by_name = {mcp_name(t): t for t in tools_of(lib, emp["role"])}
    tool = by_name.get(name)
    if tool is None:
        return {"outcome": "denied", "class": None, "code": "unknown_tool", "ref": None}
    run = await tx.first(
        "SELECT id, state, tool_calls FROM agents.runs WHERE id = CAST(:r AS uuid)",
        r=str(turn["run"]),
    )
    if run is None or run["state"] != "running":
        return {"outcome": "denied", "class": None, "code": "run_not_running", "ref": None}
    n = int(run["tool_calls"] or 0)
    got = await workflows_client.direct_tool(
        hub,
        {"op": "call", "employee": emp["code"], "run": str(run["id"]),
         "step": min(50, 1 + n // STEP_CALLS), "index": n % STEP_CALLS, "tool": tool,
         "args": args if isinstance(args, dict) else {}},
    )  # fmt: skip
    if not isinstance(got, dict) or "outcome" not in got:
        return {"outcome": "error", "class": None, "code": "gateway_unreachable", "ref": None}
    return got


async def skill(tx: Tx, lib: Any, emp: dict[str, Any], name: str, args: Any) -> dict[str, Any]:
    from hq_api import audit

    if name == SKILL_LIST:
        return {"outcome": "ok", "class": "A0", "code": None, "ref": None,
                "result": {"skills": skills_of(lib)}}  # fmt: skip
    role = str((args or {}).get("role") or "") if isinstance(args, dict) else ""
    ch = lib.get(role) if lib is not None else None
    if ch is None or ch.kind == "system":
        return {"outcome": "error", "class": "A0", "code": "not_found", "ref": None,
                "hint_fa": "چنین نقشی نیست؛ فهرست را با skill_list ببین."}  # fmt: skip
    await audit.record(
        tx,
        principal(emp),
        company_id=emp["company_id"],
        action="skill.read",
        action_class="A0",
        target_kind="role",
        target_ref=role,
        summary=f"{emp['code']} read the guide of {role} in a direct session",
    )
    return {"outcome": "ok", "class": "A0", "code": None, "ref": role,
            "result": {"role": role, "title_fa": ch.title_fa, "guide_md": ch.body[:20000]}}  # fmt: skip
