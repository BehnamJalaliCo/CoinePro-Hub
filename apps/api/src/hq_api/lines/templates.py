"""Line templates as data (contract §30.1): apps/api/seed/lines/*.yaml.

A template is the plan of steps; it names no company. Each file is checked
whole (keys, kinds against base.KINDS, inputs that name an earlier step,
attempts, timeouts, the schedule's rule); a file that does not hold together
is refused with its name and never half-loaded. Loaded once per process
(`load()` is cached); tests add a directory of their own with `use_dirs`.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from hq_api.domain import recurrence
from hq_api.errors import ApiError
from hq_api.lines import base

log = logging.getLogger("hq_api.lines.templates")

SEED_DIR = Path(__file__).resolve().parents[3] / "seed" / "lines"
NOT_TEMPLATES = ("rules.yaml",)  # §31.1 the platform rules live beside the templates
KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
GATES = ("auto", "owner", "ceo")
MAX_TIMEOUT_S = 7200  # a render may take long; nothing waits more than two hours
_extra_dirs: tuple[Path, ...] = ()


class StepDef(BaseModel):
    key: str = Field(pattern=KEY.pattern)
    kind: str
    title_fa: str = Field(min_length=1, max_length=200)
    prompt_fa: str | None = Field(default=None, max_length=20_000)
    settings: dict[str, Any] = Field(default_factory=dict)
    inputs: list[str] = Field(default_factory=list, max_length=20)
    gate: Literal["auto", "owner", "ceo"] = "auto"
    optional: bool = False
    enabled: bool = True
    max_attempts: int = Field(default=1, ge=1, le=3)
    timeout_s: int = Field(default=300, ge=5, le=MAX_TIMEOUT_S)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        if v not in base.KINDS:
            raise ValueError(f"unknown step kind {v!r}")
        return v


class Caps(BaseModel):
    runs_per_day: int = Field(default=1, ge=0, le=100)
    tokens_per_run: int = Field(default=200_000, ge=0, le=20_000_000)
    opus_per_day: int = Field(default=1, ge=0, le=50)


class InsightsDefaults(BaseModel):
    # §31.1 the figure the line's published runs are ranked by
    metric: str = Field(default="views", pattern=KEY.pattern)


class Defaults(BaseModel):
    caps: Caps = Field(default_factory=Caps)
    schedule: str | None = None
    auto_after: int = Field(default=7, ge=1, le=100)
    insights: InsightsDefaults = Field(default_factory=InsightsDefaults)


class Template(BaseModel):
    key: str = Field(pattern=KEY.pattern)
    title_fa: str = Field(min_length=1, max_length=200)
    platform: str = Field(pattern=KEY.pattern)
    version: int = Field(ge=1)
    steps: list[StepDef] = Field(min_length=1, max_length=40)
    defaults: Defaults = Field(default_factory=Defaults)
    outputs_fa: list[str] = Field(default_factory=list)

    @field_validator("outputs_fa", mode="before")
    @classmethod
    def _outputs(cls, v: Any) -> Any:
        if v is None:
            return []
        return [v] if isinstance(v, str) else v


def check_steps(steps: list[StepDef]) -> None:
    """Unique keys, and every input an earlier step (steps run in order)."""
    seen: set[str] = set()
    for s in steps:
        if s.key in seen:
            raise ValueError(f"step {s.key!r} twice")
        for i in s.inputs:
            if i not in seen:
                raise ValueError(f"step {s.key!r}: input {i!r} is no earlier step")
        seen.add(s.key)


def check_schedule(rule: str | None) -> None:
    if rule:
        recurrence.parse(rule)  # ApiError on a rule the calendar cannot hold


def validate(data: dict[str, Any]) -> Template:
    t = Template.model_validate(data)
    check_steps(t.steps)
    check_schedule(t.defaults.schedule)
    return t


def load_dir(root: Path) -> tuple[dict[str, Template], list[str]]:
    """Every template of one directory, and each refused file with its reason."""
    out: dict[str, Template] = {}
    refused: list[str] = []
    for p in sorted(root.glob("*.yaml")) if root.is_dir() else []:
        if p.name in NOT_TEMPLATES:
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                raise ValueError("not a mapping")
            t = validate(data)
            if t.key in out:
                raise ValueError(f"key {t.key!r} twice")
        except (OSError, yaml.YAMLError, ValueError, ValidationError, ApiError) as exc:
            why = str(exc)
            if isinstance(exc, ApiError) and exc.fields:
                why = "; ".join(f"{k}: {v}" for k, v in exc.fields.items())
            why = (why.splitlines() or [""])[0][:200]
            if isinstance(exc, ValidationError):
                why = "; ".join(
                    f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:3]
                )[:300]
            refused.append(f"{p.name}: {why}")
            log.warning("line template refused", extra={"file": p.name, "error": why})
            continue
        out[t.key] = t
    return out, refused


@lru_cache(maxsize=4)
def _load(dirs: tuple[Path, ...]) -> tuple[dict[str, Template], tuple[str, ...]]:
    found: dict[str, Template] = {}
    refused: list[str] = []
    for d in dirs:
        got, bad = load_dir(d)
        found.update(got)
        refused += bad
    return found, tuple(refused)


def use_dirs(*dirs: Path) -> None:
    """Directories read after the seed (tests: a fixture template of their own)."""
    global _extra_dirs
    _extra_dirs = tuple(dirs)


def load() -> dict[str, Template]:
    return _load((SEED_DIR, *_extra_dirs))[0]


def refused() -> tuple[str, ...]:
    return _load((SEED_DIR, *_extra_dirs))[1]


def get(key: str) -> Template:
    t = load().get(key)
    if t is None:
        raise ApiError(404, "not_found", f"no line template {key}")
    return t
