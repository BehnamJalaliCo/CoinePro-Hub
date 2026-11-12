package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

// ----------------------------------------------------------------- v1.11 --
// Contract §29 (prompt 21): the owner sees the business. Every order answered (its report, blockers with one-tap fixes, the end
// summary), the secretary's route before an order goes, long voice in chunks, the owner's rules, the council v2's plan and fact pack,
// readiness per company and working group, the working groups themselves, the connections that measure them, the owner's home, and each
// employee's state. Same rules as Models.kt: camelCase here, snake_case on the wire; a field the hub omits takes its default.

// ------------------------------------------------------------ §29.2 report --
/** A one-tap fix (§29.2 blockers, §29.9 readiness, §29.14 a stuck employee): what [action] to post, its button's words, its target. */
@Serializable
data class Fix(val action: String, val labelFa: String = "", val target: String? = null)

/** One company and seat the dispatcher or the assignee gave the order to. */
@Serializable
data class Assigned(val company: String = "", val code: String = "", val titleFa: String = "")

/** The receipt and the assignee's plan (`order.ack`). */
@Serializable
data class OrderAck(
    val at: String = "",
    val by: Actor? = null,
    val planFa: String = "",
    val assigned: List<Assigned> = emptyList(),
    val dueAt: String? = null,
)

/** §29.4 the secretary's route: where an order goes, with what, how (the preview the owner may edit, then `POST /orders {route}`). */
@Serializable
data class OrderRoute29(
    val companies: List<String> = emptyList(),
    val department: String? = null,
    val collaborators: List<String> = emptyList(),
    /** post · reel · story · article · report · plan · code · answer · other */
    val outputKind: String = "other",
    val count: Int? = null,
    val budgetTokens: Long? = null,
    /** single · council */
    val mode: String = "single",
    val player: String = "auto",
    /** «→ تریدیار/رسانه + IG-Hub/انتشار؛ خروجی: ۳ ریلز؛ بودجه: …» */
    val previewFa: String = "",
    val confidence: Double? = null,
    val whyFa: String = "",
    /** How the hub carries it out (work · code · meeting · question · server · kit): sent back as it came, so the route is followed exactly. */
    val kind: String = "work",
    /** ⟨2026-11-11⟩ audit: a «new company» route's kit and the company's name (sent back with it, or the hub refuses the route). */
    val kit: String? = null,
    val kitNameFa: String? = null,
)

/** One step of an order, in plain Persian (§29.7), oldest first. */
@Serializable
data class ReportStep(val at: String = "", val whoFa: String = "", val whatFa: String = "")

/** What stops an order, detected by code, with its one-tap fix (§29.2 table). */
@Serializable
data class Blocker(
    /** no_employee · hiring_closed · locked · series_unsealed · budget · player_down · connection_missing · no_progress · talk_loop */
    val kind: String,
    val titleFa: String = "",
    val detailFa: String = "",
    val since: String? = null,
    val fix: Fix? = null,
)

@Serializable
data class ReportOutput(val ref: String, val titleFa: String = "", val kind: String = "")

/** The end report: «چه شد», «چه ماند», «از تو چه لازم است». */
@Serializable
data class OrderSummary(val doneFa: String = "", val leftFa: String = "", val needFa: String = "")

/** §29.2 `GET /orders/{ref}/report`; stream `order.report` on every change. */
@Serializable
data class OrderReport(
    val ref: String,
    val textFa: String = "",
    val at: String = "",
    /** received · planned · in_progress · waiting · blocked · delivered · failed · cancelled */
    val state: String = "received",
    val ack: OrderAck? = null,
    val route: OrderRoute29? = null,
    val steps: List<ReportStep> = emptyList(),
    val blockers: List<Blocker> = emptyList(),
    val outputs: List<ReportOutput> = emptyList(),
    val summary: OrderSummary? = null,
    val updatedAt: String = "",
    /** ⟨1.15⟩ §33.7 (additive): each split work of the order, its parts side by side. */
    val parts: List<WorkSplit> = emptyList(),
    /** ⟨1.15⟩ §33.10 (additive): the works done in their own folder on their company's server. */
    val workspaces: List<WorkspaceProgress> = emptyList(),
    /** ⟨1.16⟩ §34.1 `step` (the owner leads, one step at a time) · `auto` (the holder goes to the end). */
    val pace: String = "auto",
    /** ⟨1.16⟩ §34.2 the order's live talk (`CV-…`), once opened. */
    val conversationRef: String? = null,
    /** ⟨1.16⟩ §34.3 the owner's open turn: a question waiting for his reply. */
    val turn: OrderTurn? = null,
    /** ⟨1.17⟩ §35.2 the session: open or closed, its badge and why, hidden or not. */
    val session: SessionState? = null,
    /** ⟨1.17⟩ «چه شد · حالا چه · از تو چه». */
    val brief: SessionBrief? = null,
    val tasks: List<SessionTask> = emptyList(),
    val participants: List<SessionParticipant> = emptyList(),
    /** ⟨1.18⟩ §36.3 every file of the owner's turns in the session, newest first: they belong to the order. */
    val files: List<FileRef> = emptyList(),
    /** ⟨1.22⟩ §40.1 the session's memory («تا اینجا»): what was decided, who does what, the helpers chosen, open points. Read-only. */
    val memoryMd: String? = null,
    /** ⟨0.19.6⟩ the session's cards that wait for a decision, oldest first: shown in the session and sealed from it. */
    val cards: List<OrderCard> = emptyList(),
    /** ⟨0.19.8⟩ §44.5 what the owner published from this session («تأیید و انتشار»), newest first. */
    val publishes: List<SessionPublish> = emptyList(),
    /** ⟨1.31⟩ §50 the standing routines asked for in this session, newest first. Null: a hub before §50 (it has no routines at all). */
    val routines: List<SessionRoutine>? = null,
    /** ⟨1.32⟩ §54 the workshop can take this session's turns directly now: its holder does the work himself. */
    val direct: Boolean = false,
)

/**
 * ⟨0.19.8⟩ §44.5 One «تأیید و انتشار» of a session: the owner's tap on a file, as the publish job on IG-Hub's server stands.
 * [state]: `publishing` · `published` · `failed` ([noteFa] says why) · `waiting_seal` · `waiting_setup` (the technical team is
 * connecting the company's publish path; no job yet) · ⟨1.31⟩ §51 `cancelled` (he took it back before it went out; while the cancel
 * is on its way the state stays and [noteFa] says «در حال لغو»).
 */
@Serializable
data class SessionPublish(
    val job: String? = null,
    val output: String? = null,
    val fileId: String = "",
    val fileName: String? = null,
    /** A reel's cover, when the owner chose one. */
    val coverName: String? = null,
    val channel: String = "instagram",
    /** reel · post · story */
    val kind: String = "post",
    val account: String? = null,
    val state: String = "publishing",
    val url: String? = null,
    val noteFa: String? = null,
    val at: String? = null,
    val publishedAt: String? = null,
    /** ⟨0.19.9⟩ §45 the hub sent it on the owner's standing word (no tap). */
    val auto: Boolean = false,
    /** ⟨0.20.0⟩ §46 the time it is set for ([state] `scheduled` till then); the word viewers comment for its link; a carousel's files. */
    val scheduledAt: String? = null,
    val comment: String? = null,
    val files: Int = 1,
)

/**
 * ⟨0.20.0⟩ §46 A comment rule for one post (the owner: «هر بار شاید یک کامنت باشد»): who comments one of [keywords] on it gets
 * [reply] in private, with [link] as a button.
 */
@Serializable
data class PublishComment(
    val keywords: List<String> = emptyList(),
    val reply: String = "",
    val link: String? = null,
    val button: String? = null,
    val publicReplies: List<String> = emptyList(),
)

/**
 * ⟨0.19.8⟩ §44.5 What an output's page shows of «تأیید و انتشار»: the session it belongs to, the company's Instagram accounts and
 * this output's publishes, newest first. ⟨0.19.9⟩ §45 [tap]: it can be published by a tap ([order] is null for a working group's
 * daily output, which is no session's; a hub before §45 leaves [tap] out and only a session's output has the button); [caption]:
 * the caption its package carries; [group], [groupFa], [mode]: the working group whose routine made it and the owner's standing
 * word for it (`auto`: it goes out by itself).
 */
@Serializable
data class PublishPanel(
    val order: String? = null,
    val channel: String = "instagram",
    val accounts: List<String> = emptyList(),
    val ready: Boolean = false,
    val publishes: List<SessionPublish> = emptyList(),
    val tap: Boolean = false,
    val caption: String? = null,
    /** ⟨0.20.0⟩ §46 the comment rule its package carries (`comment.txt`): the sheet opens with it. */
    val comment: PublishComment? = null,
    val group: String? = null,
    val groupFa: String? = null,
    val mode: String? = null,
    /** ⟨1.31⟩ §49 the account's best hour, only when there is enough data: one of the sheet's times. */
    val best: BestHour? = null,
)

/**
 * ⟨0.19.9⟩ §45 The owner's standing word for one company in one working group (his words, 2026-11-10: «نه اینکه هر بار من تایید
 * کنم»): [mode] `auto`, the hub publishes each day's package by itself; `ask`, each output waits for his tap.
 */
@Serializable
data class MemberPublish(
    val mode: String = "ask",
    val account: String? = null,
    val story: Boolean = false,
    val since: String? = null,
    /** ⟨0.20.0⟩ §46 the hour each day's package goes out at («HH:MM», the owner's zone); null: as soon as it is ready. */
    val at: String? = null,
    /** ⟨1.31⟩ §49 the hub chooses the hour itself (the account's best one); [at] is what it falls back on while the data is thin. */
    val best: Boolean = false,
) {
    val auto: Boolean get() = mode == "auto"
}

/** ⟨0.19.6⟩ A card of the order that waits for a decision (the owner, in his session: «بیار مهر کنم»). */
@Serializable
data class OrderCard(
    val ref: String,
    val kind: String = "",
    val titleFa: String = "",
    /** Who proposed it. */
    val byFa: String? = null,
    /** «منتظر مُهر تو» · «منتظر تصمیم مدیرعامل …؛ تو هم میتوانی مُهر کنی». */
    val waitsFa: String = "",
    val withOwner: Boolean = true,
    /** passkey · tap */
    val seal: String = "passkey",
    val createdAt: String = "",
)

// ------------------------------------------------------------- §29.3 rules --
/** The owner's rule (= a standing order of §18.1, `applies_to` widened): `"all"`, `"overseer"`, `{roles: [...]}` or `{companies: [...]}`. */
@Serializable
data class OwnerRule(
    val id: String = "",
    val ref: String,
    val textMd: String = "",
    val source: String = "text",
    val fileId: String? = null,
    val appliesTo: JsonElement = JsonPrimitive("all"),
    /** proposed · sealed · retired */
    val status: String = "proposed",
    val version: Int = 1,
    val sealedAt: String? = null,
    val createdAt: String = "",
    /** How many runs it applied to, violations found, fixed (the enforcement report's counts; absent until the first). */
    val counts: RuleCounts? = null,
)

/** ⟨2026-11-11⟩ audit: the hub counts a rule's `runs`; the older `applied` reads too. */
@OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
@Serializable
data class RuleCounts(@kotlinx.serialization.json.JsonNames("runs") val applied: Long = 0, val violations: Long = 0, val fixed: Long = 0)

// ----------------------------------------------------------- §29.5 voice --
/** `POST /transcribe/sessions` → the session the chunks go to. */
@Serializable
data class SttSession(val id: String, val expiresAt: String? = null, val maxS: Int? = null)

/** `POST /transcribe/sessions/{id}/finish`: the whole text. */
@Serializable
data class SttDone(val text: String = "", val durationS: Double = 0.0, val chunks: Int = 0, val segments: List<Segment> = emptyList())

// --------------------------------------------------------- §29.8 council v2 --
@Serializable
data class Fact(val key: String = "", val titleFa: String = "", val value: JsonElement = JsonNull, val source: String = "", val at: String? = null)

/** What the council knows before it starts: the hub's own figures and the connections', never a secret or personal data. */
@Serializable
data class FactPack(
    val company: String = "",
    val at: String = "",
    val figures: List<Fact> = emptyList(),
    val recentPosts: List<JsonElement> = emptyList(),
    val notesFa: String = "",
)

// ---------------------------------------------------------- §29.9 readiness --
@Serializable
data class ReadinessCheck(val key: String, val ok: Boolean = false, val titleFa: String = "", val detailFa: String = "", val fix: Fix? = null)

@Serializable
data class Readiness(val company: String = "", val group: String = "", val ready: Boolean = false, val checks: List<ReadinessCheck> = emptyList())

// ------------------------------------------------------------ §29.11 groups --
@Serializable
data class GroupSeat(val seat: String, val role: String = "", val titleFa: String = "", val count: Int = 1)

@Serializable
data class Routine(
    val key: String,
    val titleFa: String = "",
    val seat: String = "",
    /** RRULE in the owner's zone. */
    val schedule: String = "",
    val briefMd: String = "",
    val maxTokens: Long? = null,
    /** on · paused */
    val state: String = "on",
)

@Serializable
data class GroupKpiDef(val key: String, val titleFa: String = "", val unit: String = "", val source: String = "")

@Serializable
data class WorkGroup(
    val key: String,
    val titleFa: String = "",
    val purposeFa: String = "",
    val seats: List<GroupSeat> = emptyList(),
    val routines: List<Routine> = emptyList(),
    val kpis: List<GroupKpiDef> = emptyList(),
    val connections: List<String> = emptyList(),
    /** has_channel · all */
    val eligible: String = "all",
    /** on · off */
    val state: String = "on",
)

/** Why an empty seat stays empty (handoff 2026-11-05): the refusal's code, why and what fixes it, in Persian. */
@Serializable
data class SeatBlocked(val code: String = "", val whyFa: String = "", val fixFa: String = "")

@Serializable
data class MemberSeat(val seat: String, val employee: String? = null, val blocked: SeatBlocked? = null)

@Serializable
data class Membership(
    val group: String = "",
    val company: String,
    /** on · paused */
    val state: String = "on",
    val joinedAt: String? = null,
    val seats: List<MemberSeat> = emptyList(),
    /** ⟨0.19.9⟩ §45 the owner's standing word on publishing. */
    val publish: MemberPublish = MemberPublish(),
)

@Serializable
data class RoutineRun(
    val id: String = "",
    val group: String = "",
    val company: String = "",
    val routine: String = "",
    val at: String = "",
    val workRef: String? = null,
    /** queued · done · failed · skipped */
    val state: String = "queued",
    val noteFa: String = "",
)

@Serializable
data class Experiment(
    val id: String = "",
    val group: String = "",
    val company: String = "",
    val week: String = "",
    val hypothesisFa: String = "",
    val metric: String = "",
    val target: JsonElement = JsonNull,
    val result: JsonElement = JsonNull,
    val kept: Boolean? = null,
)

/** One day's figure of a series; a day without a figure is absent (a gap, never a zero). */
@Serializable
data class DayValue(val day: String, val value: Double? = null)

/** A KPI's series for one company (the home's and `GET /groups/{key}/kpis`). */
@Serializable
data class KpiSeries(
    val key: String = "",
    val titleFa: String = "",
    val unit: String = "",
    val company: String = "",
    val series: List<DayValue> = emptyList(),
)

// -------------------------------------------------------- §29.12 connections --
@Serializable
data class DailyFigure(val day: String, val key: String = "", val value: Double? = null)

/** A company's measured channel (Search Console, GA4, Instagram…): never its secret, only `set` or `missing`. */
@Serializable
data class CompanyConnection(
    val company: String = "",
    /** search_console · ga4 · instagram · telegram · youtube · x · pagespeed · trends · bing · play_console */
    val kind: String,
    val labelFa: String = "",
    /** not_connected · connected · error */
    val state: String = "not_connected",
    val config: JsonObject = JsonObject(emptyMap()),
    /** set · missing */
    val secret: String = "missing",
    val lastReadAt: String? = null,
    val lastErrorFa: String? = null,
    val daily: List<DailyFigure> = emptyList(),
)

/** `GET /connections/guides/{kind}`: a one-page Persian guide, and the config fields the owner fills (when the hub names them). */
@Serializable
data class ConnectionGuide(
    val kind: String = "",
    val titleFa: String = "",
    val bodyMd: String = "",
    val fields: List<GuideField> = emptyList(),
    val secretLabelFa: String? = null,
)

@Serializable
data class GuideField(val key: String, val labelFa: String = "", val hintFa: String = "", val required: Boolean = false)

/** `POST /companies/{code}/connections/{kind}/test`. */
@Serializable
data class ConnectionTest(val ok: Boolean = false, val messageFa: String = "", val state: String? = null)

// ------------------------------------------------------------ §29.13 home --
@Serializable
data class HomeSuggestion(
    val id: String,
    /** effective · good */
    val kind: String = "good",
    val company: String = "",
    val titleFa: String = "",
    val whyFa: String = "",
    val impactFa: String = "",
    val costFa: String = "",
    /** council · group · advisor */
    val source: String = "advisor",
    /** new · run · later · no */
    val state: String = "new",
    val reasonFa: String? = null,
    val orderRef: String? = null,
    val createdAt: String = "",
)

@Serializable
data class AtValue(val value: JsonElement = JsonNull, val at: String? = null)

/** A real move of a connection's figure, before → after, with its source. */
@Serializable
data class HomeProgress(
    val id: String,
    val company: String = "",
    val titleFa: String = "",
    val before: AtValue = AtValue(),
    val after: AtValue = AtValue(),
    val kpi: String = "",
    val source: String = "",
    val workRef: String? = null,
)

@Serializable
data class HomeCards(val effective: HomeSuggestion? = null, val good: HomeSuggestion? = null, val progress: HomeProgress? = null)

@Serializable
data class HomeKpi(val key: String = "", val titleFa: String = "", val unit: String = "", val series: List<DayValue> = emptyList())

@Serializable
data class HomeGroupCompany(val code: String, val nameFa: String = "", val kpi: HomeKpi? = null)

@Serializable
data class HomeGroup(val key: String, val titleFa: String = "", val companies: List<HomeGroupCompany> = emptyList())

@Serializable
data class HomeOrder(val ref: String, val textFa: String = "", val state: String = "received", val summaryFa: String = "")

/** §29.13 `GET /home`: three cards, the morning in five lines, each group's KPIs per company, the owner's orders, and only critical items. */
@Serializable
data class Home(
    val cards: HomeCards = HomeCards(),
    val morning: List<String> = emptyList(),
    val groups: List<HomeGroup> = emptyList(),
    val orders: List<HomeOrder> = emptyList(),
    val critical: List<Notification> = emptyList(),
)

// --------------------------------------------------------- §29.14 employees --
/** Why an employee is stuck and its one-tap fix. */
@Serializable
data class Stuck(val reasonFa: String = "", val fix: Fix? = null)

/**
 * `GET /groups/{key}/kpis` read whatever its exact shape: a list of series, a page of them, or one company's object with its series
 * under `kpis` or `series` (each series `{key, title_fa, unit, company?, series: [{day, value}]}`); [company] fills a missing company.
 */
fun kpiSeriesOf(e: JsonElement, company: String? = null): List<KpiSeries> {
    val j = Api.json
    val list: List<JsonElement> = when (e) {
        is JsonArray -> e
        is JsonObject -> {
            val items = e["items"] as? JsonArray
            val kpis = e["kpis"] as? JsonArray
            val series = e["series"] as? JsonArray
            val points = (series?.firstOrNull() as? JsonObject)?.containsKey("day") == true
            when {
                items != null -> items
                kpis != null -> kpis
                // One series on its own: its points are under `series`.
                series != null && points -> listOf(e)
                series != null -> series
                else -> emptyList()
            }
        }
        else -> emptyList()
    }
    val outer = ((e as? JsonObject)?.get("company") as? JsonPrimitive)?.takeIf { it.isString }?.content
    return list.mapNotNull { x ->
        val o = x as? JsonObject ?: return@mapNotNull null
        val k = j.decodeFromJsonElement(KpiSeries.serializer(), o)
        k.copy(company = k.company.ifBlank { outer ?: company.orEmpty() })
    }
}

/** A list or object answer read as a list (a hub may page it or not). */
internal fun JsonElement.itemsOrSelf(): List<JsonElement> = when (this) {
    is JsonArray -> this
    is JsonObject -> (this["items"] as? JsonArray) ?: emptyList()
    else -> emptyList()
}
