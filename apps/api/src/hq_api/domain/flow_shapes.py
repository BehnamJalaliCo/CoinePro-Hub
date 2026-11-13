"""The shapes of contract §59 (prompt 38): the library's versions, the flow automation, a company's
links, the reply policy, the board and the owner's day. One module, so the library (playbooks),
the flow (flow_auto), the links and replies (site_links) and the routes all speak the same words.

The Android app 1.1.0 (`core/net/Models59.kt`) reads these shapes (snake_case on the wire). Where the
contract and the app differ, the app's form is kept and the report says so:
- `ReplyPolicy.dm` is the bool «answer the word in DMs»; the default DM text and its buttons are
  `ReplyPolicy.dm_template` (the contract wrote both under one key `dm`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from hq_api.schemas import Model

# ------------------------------------------------------------------ §59.2 a step --
Helper = Literal["gpt", "gemini", "aistudio", "workshop", "code", "ighub", "model"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class FlowStep(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    title_fa: str = Field(min_length=1, max_length=200)
    seat: str = ""
    kind: str
    helper: Helper | None = None
    model: str | None = None
    effort: Effort | None = None
    input_fa: str = ""
    output_fa: str = ""
    rules_fa: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    gate: Literal["auto", "ask"] = "auto"
    optional: bool = False
    max_attempts: int = Field(default=1, ge=1, le=3)
    timeout_s: int | None = Field(default=None, ge=10, le=4 * 3600)
    settings: dict[str, object] = Field(default_factory=dict)


class PackageFile(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    title_fa: str = ""
    step: str | None = None
    required: bool = True


class Lesson(BaseModel):
    n: int = Field(ge=1)
    title_fa: str = Field(min_length=1, max_length=300)
    cause_fa: str = ""
    fix_fa: str = ""
    rule_fa: str = ""
    step: str | None = None


class PlaybookStats(BaseModel):
    runs: int = 0
    done: int = 0
    success_pct: float | None = None
    avg_cost_usd: float | None = None
    avg_minutes: float | None = None
    last_run_at: datetime | None = None
    companies: int = 0


class VersionRef(BaseModel):
    version: int
    state: Literal["draft", "sealed", "retired"]
    at: datetime
    by_fa: str = ""
    changelog_fa: list[str] = Field(default_factory=list)
    members: int = 0


ChangePart = Literal[
    "title", "purpose", "platform", "seat", "step", "rule", "lesson", "package", "kpi", "routine",
    "connection",
]  # fmt: skip


class PlaybookChange(BaseModel):
    part: ChangePart
    key: str
    kind: Literal["added", "removed", "changed"]
    before_fa: str | None = None
    after_fa: str | None = None


class PlaybookDiff(BaseModel):
    a: int
    b: int
    changes: list[PlaybookChange] = Field(default_factory=list)


# ---------------------------------------------------------- §59.5 a company's links --
class SiteUrl(BaseModel):
    url: str
    title_fa: str = ""


class SiteSection(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{1,24}$")
    title_fa: str = ""
    url: str


class UtmMedium(BaseModel):
    comment: str = "comment"
    story: str = "story"
    dm: str = "dm"


class SiteUtm(BaseModel):
    source: str = "instagram"
    campaign: str = "{flow}"
    medium: UtmMedium = Field(default_factory=UtmMedium)


class SiteLinks(BaseModel):
    company: str
    site: SiteUrl
    sections: list[SiteSection] = Field(default_factory=list)
    utm: SiteUtm = Field(default_factory=SiteUtm)
    updated_at: datetime | None = None
    by_fa: str = ""


class SiteLinksIn(Model):
    site: SiteUrl
    sections: list[SiteSection] = Field(default_factory=list, max_length=30)
    utm: SiteUtm | None = None


# ---------------------------------------------------------------- §59.6 replies --
class CommentPolicy(BaseModel):
    match: Literal["any", "word", "per_video"] = "per_video"


class DmButton(BaseModel):
    title_fa: str = Field(min_length=1)
    section: str | None = None


class DmTemplate(BaseModel):
    text_fa: str = ""
    buttons: list[DmButton] = Field(default_factory=list)


class RepeatPolicy(BaseModel):
    mode: Literal["once_a_year", "after_days"] = "once_a_year"
    days: int | None = Field(default=None, ge=1, le=365)


class ReplyPolicy(BaseModel):
    comment: CommentPolicy = Field(default_factory=CommentPolicy)
    story: bool = True
    dm: bool = True
    public_pool: list[str] = Field(default_factory=list)
    dm_template: DmTemplate = Field(default_factory=DmTemplate)
    per_video_dm: bool = True
    repeat: RepeatPolicy = Field(default_factory=RepeatPolicy)
    section: str | None = None


class PreviewButton(BaseModel):
    title: str
    url: str


class PreviewDm(BaseModel):
    text: str = ""
    buttons: list[PreviewButton] = Field(default_factory=list)


class RepliesPreview(BaseModel):
    dm: PreviewDm = Field(default_factory=PreviewDm)
    public: list[str] = Field(default_factory=list)
    comment_fa: str = ""
    story_fa: str = ""
    dm_fa: str = ""


class RepliesPreviewIn(Model):
    topic_fa: str | None = Field(default=None, max_length=300)


# ------------------------------------------------------------ §59.7 the flow --
Day = Literal["SA", "SU", "MO", "TU", "WE", "TH", "FR"]


class FlowSchedule(BaseModel):
    mode: Literal["fixed", "best"] = "best"
    at: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    days: list[Day] | None = None
    when_fa: str = ""


class FlowBudget(BaseModel):
    per_run_usd: float = Field(default=5.0, gt=0, le=1000)
    per_day_usd: float = Field(default=8.0, gt=0, le=5000)
    spent_today_usd: float | None = None


class FlowOccurrence(BaseModel):
    at: datetime
    topic_fa: str | None = None
    skip: bool = False


class RunResults(BaseModel):
    permalink: str | None = None
    story_permalink: str | None = None
    comments: int | None = None
    dms_sent: int | None = None
    clicks: int | None = None
    views: int | None = None
    reach: int | None = None
    likes: int | None = None
    saves: int | None = None
    shares: int | None = None
    read_at: datetime | None = None


class FlowRunRef(BaseModel):
    ref: str
    at: datetime | None = None
    state: str
    topic_fa: str | None = None
    note_fa: str = ""
    cost_usd: float | None = None
    results: RunResults | None = None


class FlowToday(BaseModel):
    runs: int = 0
    cost_usd: float = 0.0


class FlowN8n(BaseModel):
    workflow: str = "hq-flows"
    last_tick_at: datetime | None = None


class FlowAutomation(BaseModel):
    ref: str
    kind: Literal["flow"] = "flow"
    company: str
    company_fa: str = ""
    playbook: str
    playbook_fa: str = ""
    version: int
    line: str
    title_fa: str
    state: Literal["on", "off", "paused"]
    paused_until: datetime | None = None
    schedule: FlowSchedule
    account: str | None = None
    story: bool = True
    mode: Literal["auto", "ask"] = "auto"
    budget: FlowBudget = Field(default_factory=FlowBudget)
    replies: ReplyPolicy = Field(default_factory=ReplyPolicy)
    steps: list[FlowStep] = Field(default_factory=list)
    next: FlowOccurrence | None = None
    upcoming: list[FlowOccurrence] = Field(default_factory=list)
    last_run: FlowRunRef | None = None
    today: FlowToday = Field(default_factory=FlowToday)
    n8n: FlowN8n = Field(default_factory=FlowN8n)
    created_at: datetime
    by_fa: str = ""


class FlowRuns(BaseModel):
    items: list[FlowRunRef] = Field(default_factory=list)
    next_cursor: str | None = None


class FlowStateIn(Model):
    state: Literal["on", "off"]


class FlowPauseIn(Model):
    until: datetime | None = None


class FlowSkipIn(Model):
    at: datetime | None = None
    skip: bool = True


class FlowPatch(Model):
    schedule: FlowSchedule | None = None
    account: str | None = Field(default=None, min_length=1, max_length=100)
    story: bool | None = None
    mode: Literal["auto", "ask"] | None = None
    budget: FlowBudget | None = None
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)


# -------------------------------------------------------------- §59.4 the use form --
class UseNarrator(BaseModel):
    voice: str = Field(min_length=1, max_length=60)
    style_fa: str | None = Field(default=None, max_length=300)


class UseBrand(BaseModel):
    colors: list[str] = Field(default_factory=list, max_length=8)
    font: str | None = None
    logo_file: str | None = None


class UseTime(BaseModel):
    mode: Literal["fixed", "best"] = "best"
    at: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    days: list[Day] | None = None
    story: bool = True


class UseBudget(BaseModel):
    per_run_usd: float = Field(default=5.0, gt=0, le=1000)
    per_day_usd: float = Field(default=8.0, gt=0, le=5000)


class UseForm(Model):
    version: int | None = Field(default=None, ge=1)
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    accounts: list[str] = Field(default_factory=list, max_length=10)
    narrator: UseNarrator | None = None
    brand: UseBrand | None = None
    links: SiteLinksIn | None = None
    replies: ReplyPolicy | None = None
    time: UseTime = Field(default_factory=UseTime)
    budget: UseBudget = Field(default_factory=UseBudget)
    mode: Literal["auto", "ask"] = "auto"
    dry: bool = False


class UseWarning(BaseModel):
    key: str
    text_fa: str
    by_hub: bool = True


class UsePreview(BaseModel):
    lines_fa: list[str] = Field(default_factory=list)
    first_at: datetime | None = None
    cost_estimate_usd: float | None = None
    warnings: list[UseWarning] = Field(default_factory=list)


class NarratorSampleIn(Model):
    voice: str = Field(min_length=1, max_length=60)
    style_fa: str | None = Field(default=None, max_length=300)
    text_fa: str | None = Field(default=None, max_length=300)


# ---------------------------------------------------------- §59.9 the owner's day --
class DayPublished(BaseModel):
    kind: str
    url: str


class DayItem(BaseModel):
    automation: str
    title_fa: str
    company_fa: str = ""
    state: str
    published: list[DayPublished] = Field(default_factory=list)
    comments: int | None = None
    dms_sent: int | None = None
    clicks: int | None = None
    cost_usd: float | None = None
    note_fa: str = ""


class DaySummary(BaseModel):
    day: str
    line_fa: str
    items: list[DayItem] = Field(default_factory=list)
    cost_usd: float = 0.0


# --------------------------------------------------------------- §59.10 the board --
BoardKind = Literal["flow", "routine", "standing_publish", "line", "rule", "archive"]


class BoardLast(BaseModel):
    at: datetime | None = None
    state: str = ""
    note_fa: str = ""


class BoardItem(BaseModel):
    ref: str
    kind: BoardKind
    title_fa: str
    company: str | None = None
    company_fa: str | None = None
    playbook: str | None = None
    playbook_fa: str | None = None
    version: int | None = None
    when_fa: str = ""
    state: Literal["on", "off", "paused", "proposed"]
    switchable: bool = True
    last: BoardLast | None = None
    next_at: datetime | None = None
    cost_today_usd: float | None = None
    opens: str = ""


class Health(BaseModel):
    key: Literal["n8n", "ighub", "publish_path", "helpers_browser", "aistudio", "workshop"]
    state: Literal["ok", "warn", "down"]
    note_fa: str = ""


class BoardToday(BaseModel):
    runs: int = 0
    published: int = 0
    cost_usd: float = 0.0


class AutomationBoard(BaseModel):
    items: list[BoardItem] = Field(default_factory=list)
    health: list[Health] = Field(default_factory=list)
    today: BoardToday = Field(default_factory=BoardToday)


class CalendarEntry(BaseModel):
    ref: str
    at: datetime
    title_fa: str
    company_fa: str = ""
    topic_fa: str | None = None
    state: Literal["planned", "skipped", "running", "done", "failed"]


class CalendarDay(BaseModel):
    day: str
    items: list[CalendarEntry] = Field(default_factory=list)


class AutoCalendar(BaseModel):
    days: list[CalendarDay] = Field(default_factory=list)


class AuditLine(BaseModel):
    at: datetime
    who_fa: str = ""
    action: str
    summary_fa: str = ""
