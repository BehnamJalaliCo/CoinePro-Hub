"""The runtime's protocol with the model (prompt 05 §2).

Each step the model returns exactly one JSON object (enforced with a JSON
schema by the router / Claude Code):

    {"summary_fa": "...", "actions": [{"tool": "...", "args": {...}}], "done": true|false}

There is no field for thinking or reasoning: no chain of thought is ever
stored. `summary_fa` (one or two Persian sentences) is what the owner sees on
the agent screen. Actions are carried out in order by the Tool Gateway and
their (redacted) results come back in the next step.

The advisor answers the owner in a second phase: plain Persian markdown,
streamed, ending with its citations as one JSON line (parsed and validated
server-side).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from hq_common.charters import Charter, Library

STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary_fa", "actions", "done"],
    "properties": {
        "summary_fa": {"type": "string", "maxLength": 2000},
        "actions": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tool", "args"],
                "properties": {
                    "tool": {"type": "string", "maxLength": 40},
                    "args": {"type": "object"},
                },
            },
        },
        "done": {"type": "boolean"},
    },
}
CITATIONS_OPEN = "<citations>"
CITATIONS_CLOSE = "</citations>"
CITATION_KINDS = ("decision", "resolution", "deliverable", "work", "message", "audit")


@dataclass
class Action:
    tool: str
    args: dict[str, Any]


@dataclass
class StepOut:
    summary_fa: str
    actions: list[Action] = field(default_factory=list)
    done: bool = False


class BadOutput(ValueError):
    pass


def parse_step(value: Any, text: str | None, max_actions: int) -> StepOut:
    """The step from the structured output (or, failing that, the text)."""
    data = value
    if data is None and text:
        data = _first_json_object(text)
    if not isinstance(data, dict):
        raise BadOutput("the step is not a JSON object")
    summary = data.get("summary_fa")
    actions = data.get("actions", [])
    done = data.get("done")
    if not isinstance(summary, str) or not isinstance(actions, list) or not isinstance(done, bool):
        raise BadOutput("summary_fa, actions and done are required")
    out: list[Action] = []
    for a in actions[:max_actions]:
        if not isinstance(a, dict) or not isinstance(a.get("tool"), str):
            raise BadOutput("each action needs a tool name")
        args = a.get("args", {})
        out.append(Action(tool=a["tool"][:80], args=args if isinstance(args, dict) else {}))
    return StepOut(summary_fa=summary.strip()[:2000], actions=out, done=done)


def _first_json_object(text: str) -> Any:
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[start:])
            return obj
        except ValueError:
            start = text.find("{", start + 1)
    return None


# ---------------------------------------------------------------- prompt --
def tool_table(lib: Library, charter: Charter) -> str:
    rows = ["| tool | class | input | what it does |", "|---|---|---|---|"]
    for t in lib.tool_rows(charter.role):
        rows.append(f"| `{t.name}` | {t.cls} | `{t.input}` | {t.description} |")
    return "\n".join(rows)


def runtime_section(
    lib: Library, charter: Charter, *, max_actions: int, answer_phase: bool = False
) -> str:
    answer = (
        "\n- This is a conversation with the owner: use the steps to look things up (read-only tools); "
        "do NOT post your answer with a tool. When you have what you need, return done=true: the "
        "runtime then asks you for the answer, which is streamed to the owner and stored in the thread."
        if answer_phase
        else ""
    )
    return f"""# How this runtime works (protocol v1)
- Answer every step with exactly ONE JSON object and nothing else:
  {{"summary_fa": "...", "actions": [{{"tool": "<tool>", "args": {{...}}}}], "done": true|false}}
- `summary_fa`: one or two Persian sentences saying what this step does and why. The owner reads it on the agent screen. Never write your reasoning, a plan transcript or any secret here.
- `actions`: at most {max_actions} tool calls, carried out in order by the Tool Gateway. Their results (redacted) come back to you in the next step. Use only the tools listed below, with exactly the input shown; anything else is refused. Refs (W-…, D-…, O-…) come only from the context or a tool result.
- `done`: true when this run's job is finished after this step's actions. A step with no actions and done=false is wasted.
- You have a limited number of steps and tokens (stated in each message). If they are not enough, deliver what you have with a clear note of what is missing.
- Work, decisions, messages and notifications you create are records the system routes; nobody "waits" for you and you wait for nobody.{answer}

# Your tools ({charter.role}, charter v{charter.version})
{tool_table(lib, charter)}
"""


def system_prompt(
    lib: Library,
    charter: Charter,
    values: dict[str, str],
    *,
    max_actions: int,
    answer_phase: bool = False,
) -> str:
    return (
        lib.system_prompt(charter.role, values)
        + "\n\n"
        + runtime_section(lib, charter, max_actions=max_actions, answer_phase=answer_phase)
    )


ANSWER_PHASE = (
    "# Answer phase\n"
    "Now write your answer to the owner: Persian markdown, conclusion first, then the reasoning in "
    "a few lines, then the evidence. Cite records by their refs in the text (D-…, M-…, O-…, W-…, A-…).\n"
    f"After the answer, on the LAST line, write the citations you relied on as one JSON array "
    f"between {CITATIONS_OPEN} and {CITATIONS_CLOSE}, for example:\n"
    f'{CITATIONS_OPEN}[{{"kind": "decision", "ref": "D-000123"}}, '
    f'{{"kind": "message", "ref": "A-0042"}}]{CITATIONS_CLOSE}\n'
    f"Kinds: {', '.join(CITATION_KINDS)}. Cite only refs you saw in the context or in a tool "
    "result; the server drops any other. No JSON object around the answer, no tool calls now."
)


def split_answer(text: str) -> tuple[str, list[dict[str, str]]]:
    """(the answer without the citations line, the parsed citations)."""
    i = text.rfind(CITATIONS_OPEN)
    if i == -1:
        return text.strip(), []
    j = text.find(CITATIONS_CLOSE, i)
    raw = text[i + len(CITATIONS_OPEN) : j if j != -1 else len(text)]
    body = text[:i].strip()
    try:
        items = json.loads(raw)
    except ValueError:
        return body, []
    cites: list[dict[str, str]] = []
    if isinstance(items, list):
        for c in items[:50]:
            if (
                isinstance(c, dict)
                and c.get("kind") in CITATION_KINDS
                and isinstance(c.get("ref"), str)
                and 0 < len(c["ref"]) <= 40
            ):
                cites.append({"kind": c["kind"], "ref": c["ref"]})
    return body, cites


class StreamFilter:
    """Passes the answer's deltas on, holding back the citations line (and the
    few characters that might be its beginning)."""

    def __init__(self) -> None:
        self.buf = ""
        self.closed = False

    def feed(self, chunk: str) -> str:
        if self.closed:
            return ""
        self.buf += chunk
        i = self.buf.find(CITATIONS_OPEN)
        if i != -1:
            out, self.buf, self.closed = self.buf[:i], "", True
            return out
        keep = len(CITATIONS_OPEN) - 1
        out, self.buf = self.buf[:-keep] if len(self.buf) > keep else "", self.buf[-keep:]
        return out

    def flush(self) -> str:
        out, self.buf = ("" if self.closed else self.buf), ""
        return out


# --------------------------------------------------------------- context --
def render_results(results: list[dict[str, Any]], *, steps_left: int, tokens_left: int) -> str:
    lines = ["Results of your actions (redacted):"]
    for i, r in enumerate(results, 1):
        head = f"{i}. {r['tool']} -> {r['outcome']}"
        if r.get("code"):
            head += f" ({r['code']})"
        if r.get("ref"):
            head += f" [{r['ref']}]"
        lines.append(head)
        if r.get("fields"):
            lines.append("   fields: " + json.dumps(r["fields"], ensure_ascii=False))
        if r.get("result") is not None:
            lines.append("   " + json.dumps(r["result"], ensure_ascii=False, default=str))
    if not results:
        lines.append("(no actions)")
    lines.append(f"Steps left: {steps_left}. Tokens left: {tokens_left}.")
    return "\n".join(lines)


SPACES = re.compile(r"\n{3,}")


def trim(text: str, limit: int) -> str:
    text = SPACES.sub("\n\n", text)
    return text if len(text) <= limit else text[:limit] + "\n…[cut]"
