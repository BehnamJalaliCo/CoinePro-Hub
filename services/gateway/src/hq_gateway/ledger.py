"""⟨1.31⟩ The reels order's own small tools (contract §47, §48, agents/tools.md).

    topic.claim    A1  {title_fa?, kind?, url?, work?}   today's topic (or the outside sample)
    narrator.set   A1  {voice, style_fa?, work?}         a company's narrator, in his session

The owner: «هیچ روزی تکراری نباشد». A topic is named before it is made, and the hub refuses one
the working group already said: that is code, not what a model remembers. And the narrator of a
company is set once; `speech.make` takes it by itself from then on.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from hq_gateway import tools as T

CLAIMED_FA = "ثبت شد. همین موضوع را بساز؛ فایل topic.txt (همین یک خط) را هم در بسته بگذار."
AGAIN_FA = "این را همین نوبت پیش‌تر ثبت کرده بودی؛ ادامه بده."
TAKEN_FA = (
    "این پیش‌تر گفته شده و ساخته نمیشود. یک موضوع تازه انتخاب کن و دوباره topic.claim را صدا بزن؛ "
    "فهرست آخرین موضوعات در fields.recent است."
)
NARRATOR_FA = "گوینده‌ی این شرکت ثبت شد؛ از این به بعد speech.make خودش همین صدا و سبک را میگیرد."


class TopicClaimIn(T.In):
    title_fa: str | None = Field(default=None, max_length=300)
    kind: Literal["topic", "reference"] = "topic"
    url: str | None = Field(default=None, max_length=2000)
    work: str | None = Field(default=None, pattern=T.WORK_REF)


class NarratorSetIn(T.In):
    voice: str = Field(pattern=r"^[A-Za-z]{2,30}$")
    style_fa: str | None = Field(default=None, max_length=500)
    work: str | None = Field(default=None, pattern=T.WORK_REF)


async def topic_claim(api: T.Api, call: T.Call, a: TopicClaimIn) -> T.Result:
    body: dict[str, object] = {"kind": a.kind}
    if a.title_fa:
        body["title_fa"] = await T._text(a.title_fa)
    if a.url:
        body["url"] = a.url
    if a.work:
        body["work"] = a.work
    resp = await api.request("POST", "/internal/v1/topics/claim", call.token, json=body)
    r = T.from_response(resp, None)
    if r.code == "topic_taken":
        r.hint_fa = TAKEN_FA
        return r
    if r.outcome != "ok" or not isinstance(r.data, dict):
        return r
    entry = r.data.get("entry") or {}
    r.ref = str(entry.get("id") or "") or None
    r.data = {
        "kind": entry.get("kind"),
        "title_fa": entry.get("title_fa"),
        "url": entry.get("url"),
        "new": r.data.get("new"),
        "group": r.data.get("group"),
    }
    r.hint_fa = CLAIMED_FA if r.data["new"] else AGAIN_FA
    return r


async def narrator_set(api: T.Api, call: T.Call, a: NarratorSetIn) -> T.Result:
    body: dict[str, object] = {"voice": a.voice}
    if a.style_fa:
        body["style_fa"] = await T._text(a.style_fa)
    if a.work:
        body["work"] = a.work
    resp = await api.request("POST", "/internal/v1/narrator", call.token, json=body)
    r = T.from_response(resp, None)
    if r.outcome != "ok" or not isinstance(r.data, dict):
        return r
    r.ref = str(r.data.get("company") or "") or None
    r.data = {k: r.data.get(k) for k in ("company", "voice", "style_fa")}
    r.hint_fa = NARRATOR_FA
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "topic.claim": (TopicClaimIn, topic_claim),
    "narrator.set": (NarratorSetIn, narrator_set),
}
T.TOOLS.update(TOOLS)
