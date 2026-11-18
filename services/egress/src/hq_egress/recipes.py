"""The reviewed recipes of the substitute players' web path (prompt 12 §9.1.5,
contract §21.13 "Rules first, AI last"): infra/egress/recipes/<account>.yaml,
mounted read-only into egress (EGRESS_RECIPES_DIR), one per signed-in browser
profile (chatgpt-web, gemini-web, deepseek-web).

A recipe names the site's own hosts (the only ones its profile may reach),
the hosts its sign-in window may also reach, what an expired session looks
like (a login page: never an automatic sign-in), and per task (text, image,
video) the steps the profile browser runs: open a new chat (a temporary one
when the site offers it), paste the prompt, wait for the answer, read it or
download the original, close. `{prompt}` and `{start_url}` are the only
placeholders. Changing a recipe is a reviewed change to these files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ACCOUNTS = (
    "chatgpt-web",
    "gemini-web",
    "deepseek-web",
    "aistudio-web",
    "pinterest-web",
    "youtube-web",
    # ⟨2026-11-18⟩ @behnamjalali-tech's YouTube Studio: its own Google account and profile
    "youtube-bj",
)
Account = Literal[
    "chatgpt-web",
    "gemini-web",
    "deepseek-web",
    "aistudio-web",
    "pinterest-web",
    "youtube-web",
    "youtube-bj",
]
# prompt 22 (production lines): `tts` (speech in AI Studio: the audio file), `search`
# (Pinterest, read only: the pins as JSON text) and `cover` (an image made from the files the
# job carries) join the substitutes' three tasks. ⟨2026-11-17⟩ `slides`: several images made in
# ONE chat (the owner: ChatGPT designs 10-15 story slides at once, each a picture of its own).
# ⟨2026-11-17⟩ YouTube Studio (youtube-web): `channel` reads the active channel, `titles` the
# channel's video titles (a duplicate check), `upload` publishes the job's video as a Short (its
# title the prompt, its description the job's `description`, its visibility the job's), `public`
# makes an uploaded video (the job's `video_id`) Public. ⟨2026-11-17⟩ `upload_long` publishes a long
# video (16:9, 8-10 minutes) with its thumbnail and tags, from files already in the profile
# browser's spool (the job's `spooled`; never base64 in memory); `features` reads the channel's
# feature eligibility (custom thumbnails); `videos` the channel's long videos in Studio (every
# visibility: a duplicate check). ⟨2026-11-17⟩ `details` sets an uploaded video's tags and
# language on its Studio page (the job's `video_id`, `tags`); `subtitles` uploads its subtitle
# file (the job's one spooled file, an .srt) in its language; `thumbnail` sets its custom
# thumbnail (the job's one spooled picture; the channel must be phone-verified).
TASKS = (
    "text",
    "image",
    "video",
    "tts",
    "search",
    "cover",
    "slides",
    "channel",
    "titles",
    "upload",
    "public",
    "upload_long",
    "features",
    "videos",
    "details",
    "subtitles",
    "thumbnail",
)
TaskName = Literal[
    "text",
    "image",
    "video",
    "tts",
    "search",
    "cover",
    "slides",
    "channel",
    "titles",
    "upload",
    "public",
    "upload_long",
    "features",
    "videos",
    "details",
    "subtitles",
    "thumbnail",
]
HOST = re.compile(r"^(?=.{3,253}$)[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
# The longest a task may wait for its answer (image 3 min, video 10 min, a set of slides 25 min).
TASK_CAP_S = {"text": 300, "image": 180, "video": 600, "tts": 300, "search": 120, "cover": 300,
              "slides": 1500, "channel": 120, "titles": 120, "upload": 600,
              "public": 180, "upload_long": 1500, "features": 120, "videos": 120,
              "details": 240, "subtitles": 300, "thumbnail": 180}  # fmt: skip
# ⟨2026-11-17⟩ the largest file a task's job carries, where it is over egress's web_file_bytes
# (a Short's video: about 6 Mbit/s for up to two minutes; a long video: up to 20 minutes, spooled)
TASK_FILE_BYTES = {"upload": 96 * 1024 * 1024, "upload_long": 1024 * 1024 * 1024}
# the most pictures one `download_images` takes (a day's story slides)
MAX_IMAGES = 15


# What a `fill` may type: the job's prompt or its style note (never a literal from the recipe).
# ⟨2026-11-13⟩ a voice typed into a search box; ⟨2026-11-17⟩ a video's description and its tags
# (YouTube)
FILL_TEXTS = ("{prompt}", "{style}", "{voice}", "{description}", "{tags}")
# ⟨2026-11-17⟩ a name a step may keep a read under (the answer's `notes`, beside its text)
NOTE = r"^[a-z][a-z_]{0,29}$"


class RStep(BaseModel):
    """One step of a recipe; `do` names what the profile browser does."""

    model_config = ConfigDict(extra="forbid")
    do: Literal[
        "goto",  # url (a placeholder allowed)
        "wait",  # selector visible (or `state`)
        "wait_gone",  # selector hidden or detached (the answer is done)
        "click",  # selector; optional: a missing one is skipped
        "click_unless",  # click selector unless `unless` is present (a toggle that is on)
        "fill",  # selector <- text (the prompt)
        "press",  # selector, key
        "pause",  # ms (at most 5 s)
        "read",  # the last match of selector -> the answer's text
        "download_image",  # the last match's `attr` (src) -> the original file
        "download_images",  # ⟨2026-11-17⟩ every made picture of the answer, in order (<= 15)
        # ⟨2026-11-17⟩ while the chat holds fewer made pictures (`selector`) than the job's `limit`,
        # ask in the same chat for the next one (typed into `composer`, done when `busy` is gone)
        "more_images",
        "download",  # click selector -> the file the site sends
        # prompt 22
        "select",  # choose the option named by the job's `voice` in the control `selector`
        "attach",  # put the job's files into the file input `selector`
        "collect",  # the job's `limit` items matching `selector` -> JSON {image, link, title}
        "download_media",  # like download_image, for audio, video or an image
        # ⟨2026-11-17⟩ until the page has sent everything to `url`'s host (an upload's end: no
        # request to it in flight, none for a few seconds)
        "wait_sent",
    ]
    selector: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    text: str | None = Field(default=None, max_length=200)
    key: str | None = Field(default=None, max_length=40)
    unless: str | None = Field(default=None, max_length=500)
    attr: str | None = Field(default=None, pattern=r"^[a-z-]{1,40}$")
    state: Literal["visible", "attached", "hidden", "detached"] | None = None
    timeout_s: float | None = Field(default=None, gt=0, le=1500)
    optional: bool = False
    ms: int | None = Field(default=None, ge=0, le=5000)
    # ⟨20.1⟩ `read` only: other selectors tried in turn when `selector` matches
    # nothing (a structural one first, a labelled one after: lesson of 19.3)
    alt: list[str] | None = Field(default=None, max_length=4)
    # ⟨2026-11-17⟩ `read` only: each link of the answer kept as markdown ([text](url)); a numbered
    # source mark (DeepSeek's citations) becomes [n](url) instead of a bare number
    links: bool = False
    # ⟨2026-11-17⟩ `more_images` only: the chat's input and its "still answering" control
    composer: str | None = Field(default=None, max_length=500)
    busy: str | None = Field(default=None, max_length=500)
    # ⟨2026-11-17⟩ `attach` only: which of the job's files (0 the first) goes into this input (a
    # long video's upload dialog takes file 0, its thumbnail file 1); none: all of them
    file: int | None = Field(default=None, ge=0, le=9)
    # ⟨2026-11-17⟩ `read` and `wait_sent` only: the text is kept under this name in the answer's
    # `notes` (whether a thumbnail was taken, how an upload ended), never as the answer's text
    note: str | None = Field(default=None, pattern=NOTE)
    # ⟨2026-11-17⟩ `fill` only: typed key by key, as a person types (YouTube's tag box makes a tag
    # of each comma it sees typed)
    typed: bool = False

    @model_validator(mode="after")
    def _needs(self) -> RStep:
        needs_selector = self.do not in ("goto", "pause", "wait_sent")
        if needs_selector and not self.selector:
            raise ValueError(f"{self.do} needs a selector")
        if self.do in ("goto", "wait_sent") and not self.url:
            raise ValueError(f"{self.do} needs a url")
        if self.do == "wait_sent" and not str(self.url).startswith("https://"):
            raise ValueError("wait_sent names an https url")
        if self.file is not None and self.do != "attach":
            raise ValueError("file is for attach only")
        if self.note is not None and self.do not in ("read", "wait_sent"):
            raise ValueError("note is for read and wait_sent only")
        if self.typed and self.do != "fill":
            raise ValueError("typed is for fill only")
        if self.do == "click_unless" and not self.unless:
            raise ValueError("click_unless needs `unless`")
        if self.do == "press" and not self.key:
            raise ValueError("press needs a key")
        if self.do == "fill" and self.text not in FILL_TEXTS:
            raise ValueError("fill types the prompt, the style, the voice or the description only")
        if self.do == "select" and self.text != "{voice}":
            raise ValueError("select chooses the job's voice only")
        if self.alt is not None and self.do != "read":
            raise ValueError("alt is for read only")
        if (self.composer is not None or self.busy is not None) != (self.do == "more_images"):
            raise ValueError("composer and busy are for more_images, which needs both")
        if self.do == "more_images" and not (self.composer and self.busy):
            raise ValueError("more_images needs composer and busy")
        if any(not a or len(a) > 500 for a in self.alt or []):
            raise ValueError("an alt selector is 1-500 characters")
        return self


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout_s: float = Field(gt=0, le=1500)  # (and at most its TASK_CAP_S)
    steps: list[RStep] = Field(min_length=1, max_length=50)


class Expired(BaseModel):
    """What a signed-out or expired profile shows: a login page."""

    model_config = ConfigDict(extra="forbid")
    url_contains: list[str] = Field(default_factory=list, max_length=20)
    hosts: list[str] = Field(default_factory=list, max_length=20)
    selectors: list[str] = Field(default_factory=list, max_length=20)


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: Account
    version: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]{1,3}$")
    site: str
    start_url: str = Field(pattern=r"^https://")
    hosts: list[str] = Field(min_length=1, max_length=30)
    login_hosts: list[str] = Field(default_factory=list, max_length=30)
    expired: Expired
    # Site features always used (DeepSeek: deep thinking and web search, the
    # owner's decision 2026-10-22); documentation only, the steps do it.
    features: list[str] = Field(default_factory=list, max_length=10)
    tasks: dict[TaskName, Task]

    @field_validator("hosts", "login_hosts")
    @classmethod
    def _hosts(cls, v: list[str]) -> list[str]:
        for h in v:
            if not HOST.fullmatch(h) or h.rsplit(".", 1)[-1].isdigit():
                raise ValueError(f"not a host name: {h}")  # an address is never a site
        return [h.lower() for h in v]

    @model_validator(mode="after")
    def _own_site(self) -> Recipe:
        site = self.site.lower()
        if site not in self.hosts:
            raise ValueError("the site is one of its own hosts")
        start = re.sub(r"^https://([^/:?#]+).*$", r"\1", self.start_url).lower()
        if not any(start == h or start.endswith("." + h) for h in self.hosts):
            raise ValueError("start_url is on the site's own hosts")
        for name, t in self.tasks.items():
            if t.timeout_s > TASK_CAP_S[name]:
                raise ValueError(f"{name} waits at most {TASK_CAP_S[name]} s")
            for st in t.steps:
                if st.do != "wait_sent":
                    continue
                host = re.sub(r"^https://([^/:?#]+).*$", r"\1", str(st.url)).lower()
                if not any(host == h or host.endswith("." + h) for h in self.hosts):
                    raise ValueError("wait_sent names one of the site's own hosts")
        return self

    def own_hosts(self) -> frozenset[str]:
        return frozenset(self.hosts)

    def sign_in_hosts(self) -> frozenset[str]:
        return frozenset(self.hosts) | frozenset(self.login_hosts)

    def for_job(self, task: str) -> dict[str, Any]:
        """What the profile browser gets for one job (no other task's steps)."""
        return {
            "key": self.key,
            "version": self.version,
            "start_url": self.start_url,
            "hosts": sorted(self.hosts),
            "expired": self.expired.model_dump(),
            "task": task,
            "timeout_s": self.tasks[task].timeout_s,  # type: ignore[index]
            "steps": [s.model_dump(exclude_none=True) for s in self.tasks[task].steps],  # type: ignore[index]
        }


def stamp(directory: str | Path) -> tuple[tuple[str, int, int], ...]:
    """⟨2026-11-14⟩ The recipe files as they stand (name, size, change time): egress reads
    them again when this differs (app.State.recipes)."""
    base = Path(directory)
    if not base.is_dir():
        return ()
    out: list[tuple[str, int, int]] = []
    for f in sorted(base.glob("*.yaml")):
        try:
            st = f.stat()
        except OSError:
            continue
        out.append((f.name, st.st_size, st.st_mtime_ns))
    return tuple(out)


def load(directory: str | Path) -> dict[str, Recipe]:
    """Every recipe of the directory, by account; a bad one is an error at
    start (a reviewed file never fails silently)."""
    out: dict[str, Recipe] = {}
    base = Path(directory)
    if not base.is_dir():
        return out
    for f in sorted(base.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        r = Recipe.model_validate(data)
        if f.stem != r.key:
            raise ValueError(f"{f.name}: its key is {r.key}")
        out[r.key] = r
    return out
