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

ACCOUNTS = ("chatgpt-web", "gemini-web", "deepseek-web")
TASKS = ("text", "image", "video")
HOST = re.compile(r"^(?=.{3,253}$)[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
# The longest a task may wait for its answer (image 3 min, video 10 min).
TASK_CAP_S = {"text": 300, "image": 180, "video": 600}


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
        "download",  # click selector -> the file the site sends
    ]
    selector: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    text: str | None = Field(default=None, max_length=200)
    key: str | None = Field(default=None, max_length=40)
    unless: str | None = Field(default=None, max_length=500)
    attr: str | None = Field(default=None, pattern=r"^[a-z-]{1,40}$")
    state: Literal["visible", "attached", "hidden", "detached"] | None = None
    timeout_s: float | None = Field(default=None, gt=0, le=600)
    optional: bool = False
    ms: int | None = Field(default=None, ge=0, le=5000)

    @model_validator(mode="after")
    def _needs(self) -> RStep:
        needs_selector = self.do not in ("goto", "pause")
        if needs_selector and not self.selector:
            raise ValueError(f"{self.do} needs a selector")
        if self.do == "goto" and not self.url:
            raise ValueError("goto needs a url")
        if self.do == "click_unless" and not self.unless:
            raise ValueError("click_unless needs `unless`")
        if self.do == "press" and not self.key:
            raise ValueError("press needs a key")
        if self.do == "fill" and self.text not in ("{prompt}",):
            raise ValueError("fill types the prompt only")
        return self


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout_s: float = Field(gt=0, le=600)
    steps: list[RStep] = Field(min_length=1, max_length=40)


class Expired(BaseModel):
    """What a signed-out or expired profile shows: a login page."""

    model_config = ConfigDict(extra="forbid")
    url_contains: list[str] = Field(default_factory=list, max_length=20)
    hosts: list[str] = Field(default_factory=list, max_length=20)
    selectors: list[str] = Field(default_factory=list, max_length=20)


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: Literal["chatgpt-web", "gemini-web", "deepseek-web"]
    version: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]{1,3}$")
    site: str
    start_url: str = Field(pattern=r"^https://")
    hosts: list[str] = Field(min_length=1, max_length=30)
    login_hosts: list[str] = Field(default_factory=list, max_length=30)
    expired: Expired
    # Site features always used (DeepSeek: deep thinking and web search, the
    # owner's decision 2026-10-22); documentation only, the steps do it.
    features: list[str] = Field(default_factory=list, max_length=10)
    tasks: dict[Literal["text", "image", "video"], Task]

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
