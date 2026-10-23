"""The media studio's tools (prompt 13 §2, contract §22.2, agents/tools.md v1.6):

    media.item      A1  write the current step of a media item (its role's)
    media.render    A2  queue a preview render in the sandboxed render worker
    media.voice     A2  the item's narration with the hub's own voice
    media.review    A2  the media director's review (the `qc` check)
    series.propose  A1  a publishing series for the owner's seal (a card)

Text is redacted on the way out, except a composition's source: it is code,
checked by the api against the composition schema (and its visible text for
secrets) before it is stored; a mangled document would only fail there.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from hq_gateway import tools as T

REF = r"^MI-[0-9]{4,}$"


class SourceIn(T.In):
    kind: str = Field(min_length=1, max_length=40)
    ref: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=1000)
    note: str = Field(default="", max_length=1000)


class ScriptIn(T.In):
    text_fa: str = Field(min_length=1, max_length=20000)
    sources: list[SourceIn] = Field(default_factory=list, max_length=50)


class ShotIn(T.In):
    n: int = Field(ge=1, le=100)
    duration_s: float = Field(gt=0, le=180)
    visual_fa: str = Field(min_length=1, max_length=3000)
    text_on_screen_fa: str | None = Field(default=None, max_length=500)
    voice_fa: str | None = Field(default=None, max_length=2000)


class DirectionIn(T.In):
    shots: list[ShotIn] = Field(min_length=1, max_length=60)


class CompositionIn(T.In):
    format: Literal["html", "lottie"]
    source: str = Field(min_length=1, max_length=1_500_000)


class MediaItemIn(T.In):
    ref: str = Field(pattern=REF)
    step: Literal["script", "direction", "composition", "brief"]
    script: ScriptIn | None = None
    direction: DirectionIn | None = None
    composition: CompositionIn | None = None
    brief_md: str | None = Field(default=None, max_length=20000)


class MediaRefIn(T.In):
    ref: str = Field(pattern=REF)


class MediaVoiceIn(T.In):
    ref: str = Field(pattern=REF)
    text_fa: str = Field(min_length=1, max_length=20000)
    voice_id: str | None = Field(default=None, max_length=80)


class MediaReviewIn(T.In):
    ref: str = Field(pattern=REF)
    verdict: Literal["pass", "changes", "reject"]
    note_md: str = Field(default="", max_length=20000)


class TargetIn(T.In):
    channel: Literal["telegram", "instagram"]
    account: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,40}$")
    placement: Literal[
        "telegram_post", "telegram_story", "instagram_reel", "instagram_story", "instagram_post"
    ]


class TopicsIn(T.In):
    pool: list[str] = Field(default_factory=list, max_length=200)
    rule_fa: str | None = Field(default=None, max_length=1000)


class VoiceRefIn(T.In):
    voice_id: str = Field(min_length=1, max_length=80)


class OverlayIn(T.In):
    cta_fa: str | None = Field(default=None, max_length=120)
    mark: bool = True


class FormatIn(T.In):
    aspect: Literal["9:16", "4:5", "1:1", "16:9"]
    duration_s: int | None = Field(default=None, ge=3, le=180)
    voice: VoiceRefIn | None = None
    captions: bool = True
    music: Literal["none", "library"] = "none"
    overlay: OverlayIn = Field(default_factory=OverlayIn)


class SeriesProposeIn(T.In):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    title_fa: str = Field(min_length=1, max_length=200)
    kind: Literal["reel", "story", "post", "carousel"]
    targets: list[TargetIn] = Field(min_length=1, max_length=10)
    schedule: str = Field(min_length=5, max_length=500)
    topics: TopicsIn | None = None
    format: FormatIn
    checks: list[str] = Field(default_factory=list, max_length=7)
    auto_publish: bool = False
    max_per_day: int | None = Field(default=None, ge=1, le=20)
    what_fa: str = Field(default="", max_length=20000)
    why_fa: str = Field(default="", max_length=20000)


def _shape(r: T.Result) -> T.Result:
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = str(r.data.get("ref") or "")
        hint = r.data.get("hint_fa")
        if hint:
            r.hint_fa = str(hint)
    return r


async def media_item(api: T.Api, call: T.Call, a: MediaItemIn) -> T.Result:
    body: dict[str, Any] = a.model_dump(mode="json", exclude_none=True)
    source = body.pop("composition", None)
    body = await T._text(body)
    if source is not None:
        body["composition"] = source  # code: checked by the api, never rewritten here
    resp = await api.request(
        "POST", "/internal/v1/media/item", call.token, json=body, idem=call.idem(f"media.item:{a.ref}:{a.step}")
    )
    return _shape(T.from_response(resp))


async def media_render(api: T.Api, call: T.Call, a: MediaRefIn) -> T.Result:
    resp = await api.request("POST", "/internal/v1/media/render", call.token, json=a.model_dump(mode="json"))
    return _shape(T.from_response(resp))


async def media_voice(api: T.Api, call: T.Call, a: MediaVoiceIn) -> T.Result:
    body = await T._text(a.model_dump(mode="json", exclude_none=True))
    resp = await api.request("POST", "/internal/v1/media/voice", call.token, json=body)
    return _shape(T.from_response(resp))


async def media_review(api: T.Api, call: T.Call, a: MediaReviewIn) -> T.Result:
    body = await T._text(a.model_dump(mode="json"))
    resp = await api.request("POST", "/internal/v1/media/review", call.token, json=body)
    return _shape(T.from_response(resp))


async def series_propose(api: T.Api, call: T.Call, a: SeriesProposeIn) -> T.Result:
    body = await T._text(a.model_dump(mode="json", exclude_none=True))
    resp = await api.request(
        "POST",
        "/internal/v1/media/series/propose",
        call.token,
        json=body,
        idem=call.idem(f"series.propose:{a.title_fa}"),
    )
    return _shape(T.from_response(resp))


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "media.item": (MediaItemIn, media_item),
    "media.render": (MediaRefIn, media_render),
    "media.voice": (MediaVoiceIn, media_voice),
    "media.review": (MediaReviewIn, media_review),
    "series.propose": (SeriesProposeIn, series_propose),
}
T.TOOLS.update(TOOLS)
