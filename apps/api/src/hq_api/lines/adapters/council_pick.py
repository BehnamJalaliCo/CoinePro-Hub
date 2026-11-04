"""`council_pick`: the council chooses one of the candidates, with reasons (§30.2, §29.8).

The candidates come from the input step (`data.items` of a pattern search, else the numbered lines
of its text). The council's outside members (`domain/council.py` roles: the researcher, the numbers
member and the devil's advocate; the captain's tie-break is the researcher's) each get the same
question through their text seat, in Persian, and answer `{"pick": n, "reason_fa": "..."}`. The most
picked candidate wins; a tie goes to the researcher's pick, else the first answer. A member that is
signed out or limited is left out and named in the reasons; with no answer at all the step fails.
Nothing is called for a company's inside question; this is an outside choice (patterns, ideas).
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from decimal import Decimal
from typing import Any

from hq_api.domain import council as CV
from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

PLAYER_OF_ROLE = {"researcher": "gemini", "numbers": "deepseek", "devil": "gpt"}
FA = {"gemini": "جمینای", "deepseek": "دیپ‌سیک", "gpt": "ChatGPT"}
MAX_CANDIDATES = 12


def candidates_of(ctx: StepContext) -> list[dict[str, Any]]:
    src = C.first_input(ctx, C.setting(ctx, "candidates_from"))
    if src is None:
        raise StepFailed("ورودی انتخاب (فهرست گزینه‌ها) نیست.", code="no_input")
    items = (src.data or {}).get("items")
    if isinstance(items, list) and items:
        return [i if isinstance(i, dict) else {"title": str(i)} for i in items[:MAX_CANDIDATES]]
    lines = [ln.strip() for ln in str(src.text or "").splitlines() if ln.strip()]
    return [{"title": re.sub(r"^\d+[.)]\s*", "", ln)} for ln in lines[:MAX_CANDIDATES]]


def question(ctx: StepContext, cands: list[dict[str, Any]], role: str) -> str:
    lines = [
        f"{i + 1}. {c.get('title') or ''} {c.get('link') or ''}".strip()
        for i, c in enumerate(cands)
    ]
    brief = (ctx.prompt or "از میان گزینه‌ها بهترین را برای این محتوا انتخاب کن.").strip()
    return (
        f"شورای مشاوران، انتخاب یک گزینه. نقش تو: {CV.ROLE_FA[role]}. {CV.ROLE_TASK[role]}\n\n"
        f"{brief}\n\nگزینه‌ها:\n" + "\n".join(lines) + "\n\n"
        'فقط یک شیء JSON بده، بدون هیچ متن دیگر: {"pick": <شماره‌ی گزینه>, "reason_fa": "<دلیل در یک یا دو جمله>"}\n'
        + CV.PERSIAN
    )


def parse_pick(text: str, n: int) -> tuple[int, str] | None:
    try:
        obj = C.parse_json_object(text)
        pick = int(obj["pick"])
    except (ValueError, KeyError, TypeError):
        m = re.search(r"\d+", text or "")
        if not m:
            return None
        pick, obj = int(m.group()), {"reason_fa": (text or "").strip()[:300]}
    if not 1 <= pick <= n:
        return None
    return pick, str(obj.get("reason_fa") or "").strip()[:400]


class CouncilPick:
    kind = "council_pick"

    async def run(self, ctx: StepContext) -> StepOutput:
        cands = candidates_of(ctx)
        if not cands:
            raise StepFailed("گزینه‌ای برای انتخاب نیست.", code="no_candidates")
        if len(cands) == 1:
            return self._out(
                cands, 1, [{"player": "-", "pick": 1, "reason_fa": "تنها گزینه بود."}], 0
            )
        async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
            roles = await CV.roles(tx)
        # the owner's roles (council_roles setting): each outside player in its own role
        members = [(roles[p], p) for p in ("gemini", "deepseek", "gpt") if p in roles] or list(
            PLAYER_OF_ROLE.items()
        )
        results = await asyncio.gather(
            *[
                C.ask_seat(ctx, question(ctx, cands, role), player=player)
                for role, player in members
            ],
            return_exceptions=True,
        )
        votes: list[dict[str, Any]] = []
        left_out: list[str] = []
        tokens = 0
        for (_, player), got in zip(members, results, strict=True):
            if isinstance(got, StepFailed):
                left_out.append(f"{FA.get(player, player)}: {got.reason_fa}")
                continue
            if isinstance(got, BaseException):
                raise got
            tokens += int(got["tokens"])
            parsed = parse_pick(str(got["text"]), len(cands))
            if parsed is None:
                left_out.append(f"{FA.get(player, player)}: جواب قابل‌فهم نبود.")
                continue
            votes.append({"player": player, "pick": parsed[0], "reason_fa": parsed[1]})
        if not votes:
            raise StepFailed("هیچ‌یک از اعضای شورا جواب نداد: " + " | ".join(left_out), retry=True)
        return self._out(cands, self._winner(votes), votes, tokens, left_out)

    @staticmethod
    def _winner(votes: list[dict[str, Any]]) -> int:
        count = Counter(v["pick"] for v in votes)
        top = max(count.values())
        tied = [p for p, n in count.items() if n == top]
        if len(tied) == 1:
            return int(tied[0])
        for v in votes:  # a tie: the researcher's pick if it is among them, else the first answer
            if v["player"] == "gemini" and v["pick"] in tied:
                return int(v["pick"])
        return int(next(v["pick"] for v in votes if v["pick"] in tied))

    @staticmethod
    def _out(
        cands: list[dict[str, Any]],
        pick: int,
        votes: list[dict[str, Any]],
        tokens: int,
        left_out: list[str] | None = None,
    ) -> StepOutput:
        chosen = cands[pick - 1]
        reasons = [
            f"{FA.get(v['player'], v['player'])} (گزینه‌ی {v['pick']}): {v['reason_fa']}"
            for v in votes
        ]
        text = (
            f"گزینه‌ی برگزیده: {chosen.get('title') or pick}\n"
            + (f"{chosen['link']}\n" if chosen.get("link") else "")
            + "\n".join(reasons + (left_out or []))
        )
        return StepOutput(
            text=text.strip(),
            via="council",
            tokens=tokens,
            usd_equiv=Decimal(0),
            data={"pick": pick, "chosen": chosen, "votes": votes, "left_out": left_out or []},
        )


register(CouncilPick())
