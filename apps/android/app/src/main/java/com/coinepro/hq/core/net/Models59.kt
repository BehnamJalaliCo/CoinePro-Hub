package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable

// Contract §59 ⟨1.37⟩: the library of working groups and the automations. A playbook (§40) gains its versions, its flow step by step,
// the package one run hands over and the lessons it learnt; one form gives it to any company; its daily flow is an automation of kind
// `flow` that n8n ticks and the production-line engine runs (§30: a `LineRun` is the run's timeline). Same rules as Models.kt: camelCase
// here, snake_case on the wire; a field the hub omits takes its default, so an older hub still reads (and the new places say they come
// with the next hub update).

// ------------------------------------------------------------ §59.1 the library --
/** One version of a playbook: `draft` · `sealed` · `retired`, with what changed from the one before it. */
@Serializable
data class VersionRef(
    val version: Int = 1,
    val state: String = "draft",
    val at: String? = null,
    val byFa: String? = null,
    val changelogFa: List<String> = emptyList(),
    /** How many companies run this version. */
    val members: Int = 0,
)

/** A file one run hands over (`caption.txt` «کپشن»), made by the step [step]. */
@Serializable
data class PackageFile(val name: String = "", val titleFa: String = "", val step: String? = null, val required: Boolean = true)

/** What went wrong once, why, what fixed it, and the rule it left (that rule is also in its step's `rules_fa`). */
@Serializable
data class PlaybookLesson(
    val n: Int = 0,
    val titleFa: String = "",
    val causeFa: String = "",
    val fixFa: String = "",
    val ruleFa: String = "",
    val step: String? = null,
)

/** The last 30 days of the playbook's flow runs, every member together. */
@Serializable
data class PlaybookStats(
    val runs: Int = 0,
    val done: Int = 0,
    val successPct: Double? = null,
    val avgCostUsd: Double? = null,
    val avgMinutes: Double? = null,
    val lastRunAt: String? = null,
    val companies: Int = 0,
)

/**
 * §59.2 one step of the flow, in order: the seat that owns it, its kind (§30.2's and `topic` · `voice_check` · `inspire` · `workshop` ·
 * `package` · `report`), the helper or the model that does it and at what effort, what it takes and leaves, and its own rules.
 */
@Serializable
data class FlowStep(
    val key: String = "",
    val titleFa: String = "",
    val seat: String = "",
    val kind: String = "",
    /** gpt · gemini · aistudio · workshop · code · ighub · model */
    val helper: String? = null,
    val model: String? = null,
    /** low · medium · high · max */
    val effort: String? = null,
    val inputFa: String = "",
    val outputFa: String = "",
    val rulesFa: List<String> = emptyList(),
    val inputs: List<String> = emptyList(),
    /** auto · ask */
    val gate: String = "auto",
    val optional: Boolean = false,
    val maxAttempts: Int = 1,
    val timeoutS: Int? = null,
)

/** One line of what differs between two versions (code's own, never a model's). */
@Serializable
data class PlaybookChange(
    /** title · purpose · platform · seat · step · rule · lesson · package · kpi */
    val part: String = "",
    val key: String = "",
    /** added · removed · changed */
    val kind: String = "changed",
    val beforeFa: String? = null,
    val afterFa: String? = null,
)

/** `GET /playbooks/{ref}/compare?a=&b=`. */
@Serializable
data class PlaybookDiff(val a: Int = 1, val b: Int = 1, val changes: List<PlaybookChange> = emptyList())

// --------------------------------------------------------- §59.4 the use form --
/** The brand a company's flow builds with; null in the form keeps the company's own (§18.14). */
@Serializable
data class UseBrand(val colors: List<String> = emptyList(), val font: String? = null, val logoFile: String? = null)

/** The time of each day's publication: a fixed hour or the account's best one (§49), on [days] (null: every day), and a story too. */
@Serializable
data class UseTime(val mode: String = "best", val at: String? = null, val days: List<String>? = null, val story: Boolean = true)

/** What a run and a day may spend (USD equivalent, the treasury's own figure). */
@Serializable
data class UseBudget(val perRunUsd: Double = 5.0, val perDayUsd: Double = 8.0, val spentTodayUsd: Double? = null)

/** A warning of the preview; [byHub]: the hub settles it itself (never the owner's step). */
@Serializable
data class UseWarning(val key: String = "", val textFa: String = "", val byHub: Boolean = true)

/** `POST /playbooks/{ref}/use {…, dry: true}`: what will happen each day, before anything is made. */
@Serializable
data class UsePreview(
    val linesFa: List<String> = emptyList(),
    val firstAt: String? = null,
    val costEstimateUsd: Double? = null,
    val warnings: List<UseWarning> = emptyList(),
)

/** `POST /playbooks/{ref}/use`: the membership and its flow automation. */
@Serializable
data class PlaybookUsed(val playbook: Playbook, val member: PlaybookMember? = null, val automation: FlowAutomation? = null)

/** A narrator's sample to hear before choosing (`POST /narrators/sample`). */
@Serializable
data class NarratorSample(val file: FileRef = FileRef())

// ------------------------------------------------------------ §59.5 the links --
@Serializable
data class SiteSection(val key: String = "", val titleFa: String = "", val url: String = "")

@Serializable
data class SiteUrl(val url: String = "", val titleFa: String = "")

/** The `utm_medium` of each path a reply leaves by. */
@Serializable
data class UtmMedium(val comment: String = "comment", val story: String = "story", val dm: String = "dm")

@Serializable
data class SiteUtm(val source: String = "instagram", val campaign: String = "{flow}", val medium: UtmMedium = UtmMedium())

/** `GET · PUT /companies/{code}/site-links`: the company's site and its sections, and the UTM each reply link carries. */
@Serializable
data class SiteLinks(
    val company: String = "",
    val site: SiteUrl = SiteUrl(),
    val sections: List<SiteSection> = emptyList(),
    val utm: SiteUtm = SiteUtm(),
    val updatedAt: String? = null,
    val byFa: String? = null,
)

// ------------------------------------------------------------ §59.6 the replies --
@Serializable
data class CommentPolicy(
    /** any · word · per_video (each video's comment.txt chooses) */
    val match: String = "per_video",
)

/** A button under the DM: its words and the section of the company's links it opens (null: the site). */
@Serializable
data class DmButton(val titleFa: String = "", val section: String? = null)

@Serializable
data class DmTemplate(val textFa: String = "", val buttons: List<DmButton> = emptyList())

/** How often one person is answered by the same rule: once a year (Meta's way and the spam rules), or again after [days]. */
@Serializable
data class RepeatPolicy(val mode: String = "once_a_year", val days: Int? = null)

/** §59.6 an automation's policy for answering comments, story replies and DMs. */
@Serializable
data class ReplyPolicy(
    val comment: CommentPolicy = CommentPolicy(),
    val story: Boolean = true,
    val dm: Boolean = true,
    /** In the order they go out: in turn, the first commenter gets the first, … then the first again (IG-Hub `rules.public_turn`). */
    val publicPool: List<String> = emptyList(),
    val dmTemplate: DmTemplate = DmTemplate(),
    val perVideoDm: Boolean = true,
    val repeat: RepeatPolicy = RepeatPolicy(),
    val section: String? = null,
)

@Serializable
data class PreviewButton(val title: String = "", val url: String = "")

@Serializable
data class PreviewDm(val text: String = "", val buttons: List<PreviewButton> = emptyList())

/** `POST /automations/{ref}/replies/preview`: what a person sees, built by the hub's own code. */
@Serializable
data class RepliesPreview(
    val dm: PreviewDm = PreviewDm(),
    /** Every public reply, in the order they go out. */
    val public: List<String> = emptyList(),
    val commentFa: String = "",
    val storyFa: String = "",
    val dmFa: String = "",
)

// -------------------------------------------------------- §59.7 the flow automation --
@Serializable
data class FlowSchedule(val mode: String = "best", val at: String? = null, val days: List<String>? = null, val whenFa: String = "")

/** One occurrence ahead: its time, the topic once it is planned, and whether the owner skipped it. */
@Serializable
data class FlowOccurrence(val at: String = "", val topicFa: String? = null, val skip: Boolean = false)

/** A run of a flow, short: the timeline is its `LineRun` (`GET /line-runs/{ref}`). */
@Serializable
data class FlowRunRef(
    val ref: String = "",
    val at: String? = null,
    /** queued · running · waiting · done · failed · skipped · cancelled */
    val state: String = "queued",
    val topicFa: String? = null,
    val noteFa: String = "",
    val costUsd: Double? = null,
    val results: RunResults? = null,
)

@Serializable
data class FlowToday(val runs: Int = 0, val costUsd: Double = 0.0)

@Serializable
data class FlowN8n(val workflow: String = "hq-flows", val lastTickAt: String? = null)

/** §59.7 `GET /automations/{ref}` of kind `flow`. */
@Serializable
data class FlowAutomation(
    val ref: String,
    val kind: String = "flow",
    val company: String = "",
    val companyFa: String = "",
    val playbook: String? = null,
    val playbookFa: String? = null,
    val version: Int? = null,
    val line: String? = null,
    val titleFa: String = "",
    /** on · off · paused */
    val state: String = "on",
    val pausedUntil: String? = null,
    val schedule: FlowSchedule = FlowSchedule(),
    val account: String? = null,
    val story: Boolean = true,
    /** auto · ask */
    val mode: String = "auto",
    val budget: UseBudget = UseBudget(),
    val replies: ReplyPolicy = ReplyPolicy(),
    val steps: List<FlowStep> = emptyList(),
    val next: FlowOccurrence? = null,
    val upcoming: List<FlowOccurrence> = emptyList(),
    val lastRun: FlowRunRef? = null,
    val today: FlowToday = FlowToday(),
    val n8n: FlowN8n = FlowN8n(),
    val createdAt: String? = null,
    val byFa: String? = null,
) {
    val on: Boolean get() = state == "on"
}

@Serializable
data class FlowRuns(val items: List<FlowRunRef> = emptyList(), val nextCursor: String? = null)

// -------------------------------------------------------------- §59.8 the timeline --
/** A file a step left: [text] is there (≤ 4000 chars) for a `.txt` or a `.md`, so caption.txt and comment.txt read in place. */
@Serializable
data class StepFile(
    val id: String = "",
    val name: String = "",
    val mime: String = "application/octet-stream",
    val size: Long = 0,
    /** text · audio · image · video · file */
    val kind: String = "file",
    val text: String? = null,
) {
    fun asFile(): FileRef = FileRef(
        id = id, name = name, mime = mime, size = size,
        kind = when (kind) { "video", "image", "audio" -> kind; else -> "document" },
    )
}

// -------------------------------------------------------------- §59.9 the results --
@Serializable
data class RunResults(
    val permalink: String? = null,
    val storyPermalink: String? = null,
    val comments: Int? = null,
    val dmsSent: Int? = null,
    val clicks: Int? = null,
    val views: Int? = null,
    val reach: Int? = null,
    val likes: Int? = null,
    val saves: Int? = null,
    val shares: Int? = null,
    val readAt: String? = null,
)

@Serializable
data class DayPublished(val kind: String = "", val url: String = "")

@Serializable
data class DayItem(
    val automation: String = "",
    val titleFa: String = "",
    val companyFa: String = "",
    val state: String = "",
    val published: List<DayPublished> = emptyList(),
    val comments: Int? = null,
    val dmsSent: Int? = null,
    val clicks: Int? = null,
    val costUsd: Double? = null,
    val noteFa: String = "",
)

/** `GET /automations/today`: the owner's day in one line, and each flow's. */
@Serializable
data class DaySummary(val day: String = "", val lineFa: String = "", val items: List<DayItem> = emptyList(), val costUsd: Double = 0.0)

// --------------------------------------------------------------- §59.10 the board --
@Serializable
data class BoardLast(val at: String? = null, val state: String = "", val noteFa: String = "")

/** One thing that runs by itself: a flow, a routine (§50), a standing publish (§45), a line (§30), a rule (§31.7), an archive rule (§23.7). */
@Serializable
data class BoardItem(
    val ref: String = "",
    /** flow · routine · standing_publish · line · rule · archive */
    val kind: String = "",
    val titleFa: String = "",
    val company: String? = null,
    val companyFa: String? = null,
    val playbook: String? = null,
    val playbookFa: String? = null,
    val version: Int? = null,
    val whenFa: String = "",
    /** on · off · paused · proposed */
    val state: String = "on",
    val switchable: Boolean = true,
    val last: BoardLast? = null,
    val nextAt: String? = null,
    val costTodayUsd: Double? = null,
    /** The app's place for it: `automation/<ref>`, `lines/<ref>`, `groups/<key>`, an order, `archive-settings`. */
    val opens: String? = null,
)

/** The road a flow takes, read by code: n8n · ighub · publish_path · helpers_browser · aistudio · workshop; ok · warn · down. */
@Serializable
data class Health(val key: String = "", val state: String = "ok", val noteFa: String = "")

@Serializable
data class BoardToday(val runs: Int = 0, val published: Int = 0, val costUsd: Double = 0.0)

/** `GET /automations/board`. */
@Serializable
data class AutomationBoard(val items: List<BoardItem> = emptyList(), val health: List<Health> = emptyList(), val today: BoardToday = BoardToday())

@Serializable
data class CalendarEntry(
    val ref: String = "",
    val at: String = "",
    val titleFa: String = "",
    val companyFa: String = "",
    val topicFa: String? = null,
    /** planned · skipped · running · done · failed */
    val state: String = "planned",
)

@Serializable
data class CalendarDay59(val day: String = "", val items: List<CalendarEntry> = emptyList())

/** `GET /automations/calendar`. */
@Serializable
data class AutoCalendar(val days: List<CalendarDay59> = emptyList())

/** One change of an automation, from the audit log. */
@Serializable
data class AuditLine(val at: String = "", val whoFa: String = "", val action: String = "", val summaryFa: String = "")
