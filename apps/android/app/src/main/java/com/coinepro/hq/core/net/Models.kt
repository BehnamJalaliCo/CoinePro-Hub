package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

// Contract models (contracts/HQ_CORE_API_v1.md, apps/api/openapi/hq-api.v1.json). Property names are
// camelCase; the JSON is snake_case (see Api.json). Every field the app does not need to exist has a
// default, so a server that adds fields or omits optional ones never breaks the app.

@Serializable
data class Page<T>(val items: List<T> = emptyList(), val nextCursor: String? = null)

@Serializable
data class Actor(val code: String = "", val kind: String = "system", val displayFa: String? = null)

// ------------------------------------------------------------------ auth --
@Serializable
data class Device(
    val id: String,
    val name: String,
    val kind: String,
    val createdAt: String,
    val lastUsedAt: String? = null,
    val revokedAt: String? = null,
    val current: Boolean = false,
)

@Serializable
data class DeviceList(val items: List<Device> = emptyList())

@Serializable
data class SessionOut(
    val token: String? = null,
    val client: String,
    val device: Device,
    val expiresAt: String,
    val absoluteExpiresAt: String,
)

@Serializable
data class LoginOut(val session: SessionOut)

@Serializable
data class Principal(val kind: String, val code: String)

@Serializable
data class SessionInfo(val principal: Principal, val device: Device, val expiresAt: String)

@Serializable
data class StepUpOut(val stepUpToken: String, val expiresAt: String)

@Serializable
data class Channels(val inApp: Boolean = true, val webPush: Boolean = false, val fcm: Boolean = false, val telegram: Boolean = false)

@Serializable
data class Meta(
    val apiVersion: String,
    val serviceVersion: String,
    val loginConfigured: Boolean,
    val publicOrigin: String? = null,
    val channels: Channels = Channels(),
    /** ⟨1.3⟩ §17.7: null until the owner chooses where the Code Workshop runs. */
    val workshop: WorkshopMeta? = null,
)

@Serializable
data class WorkshopMeta(val runtime: String? = null)

// ----------------------------------------------------------------- inbox --
@Serializable
data class ByRisk(val low: Int = 0, val medium: Int = 0, val high: Int = 0)

@Serializable
data class InboxSummary(
    val decisionsPending: Int = 0,
    val decisionsByRisk: ByRisk = ByRisk(),
    val deliverablesUnrated: Int = 0,
    /** ⟨1.7.3⟩ §5.2: outputs the owner has not marked seen; null from a hub before it. */
    val deliverablesUnseen: Int? = null,
    val messagesUnread: Int = 0,
    val khalvat: Boolean = false,
    val notifications: Map<String, Int> = emptyMap(),
)

@Serializable
data class Presence(val khalvat: Boolean, val since: String, val until: String? = null)

@Serializable
data class TopDecision(val ref: String, val company: String, val kind: String, val risk: String, val status: String, val title: String, val createdAt: String)

@Serializable
data class DecisionsBox(val new: Int = 0, val pending: Int = 0, val top: List<TopDecision> = emptyList())

@Serializable
data class TopDeliverable(val ref: String, val company: String, val title: String, val createdAt: String)

@Serializable
data class DeliverablesBox(val new: Int = 0, val unrated: Int = 0, val top: List<TopDeliverable> = emptyList())

@Serializable
data class TopThread(val thread: String, val company: String, val newMessages: Int = 0, val lastAt: String)

@Serializable
data class MessagesBox(val new: Int = 0, val unread: Int = 0, val topThreads: List<TopThread> = emptyList())

@Serializable
data class AwaySummary(
    val since: String,
    val until: String,
    val decisions: DecisionsBox = DecisionsBox(),
    val deliverables: DeliverablesBox = DeliverablesBox(),
    val messages: MessagesBox = MessagesBox(),
)

// ------------------------------------------------------------- decisions --
@Serializable
data class QuotaOut(val tokens: Long? = null, val usd: String? = null)

@Serializable
data class Seal(val method: String, val sealedAt: String, val stepUpId: String? = null)

@Serializable
data class Decision(
    val id: String,
    val ref: String,
    val company: String,
    val kind: String,
    val title: String,
    val what: String = "",
    val why: String = "",
    val risk: String = "medium",
    val riskNote: String? = null,
    val actionClass: String = "A1",
    val reversible: Boolean = true,
    val status: String,
    val proposer: Actor,
    val createdAt: String,
    val expiresAt: String? = null,
    val decidedAt: String? = null,
    val decidedBy: Actor? = null,
    val note: String? = null,
    val resolution: String? = null,
    val seal: Seal? = null,
    val thread: String? = null,
    val workId: String? = null,
    val payload: JsonObject = JsonObject(emptyMap()),
    val quotaEstimate: QuotaOut = QuotaOut(),
    val version: Int = 1,
    /** ⟨1.5⟩ §20.6: what a proposal promises, measured at 30/60/90 days once sealed. */
    val expected: Expected? = null,
    /** ⟨1.5⟩ §20.6: `expected_missing` for the first days after prompt 11 (a warning, not a refusal). */
    val warnings: List<String> = emptyList(),
    /** ⟨1.5⟩ §21.1: the advisor's memos on this card. */
    val memos: List<MemoBrief> = emptyList(),
    /** ⟨1.5⟩ §21.8: hours a card the owner decides has waited, and which reminders went out. The hub sends a float (`12.5`). */
    val waitingH: Double? = null,
    val reminders: List<Reminder> = emptyList(),
    /** ⟨1.5⟩ §21.10: the digital CEO's sealed prediction, null while the card is pending (reveal "after"). */
    val digitalCeoPrediction: DceoBrief? = null,
)

@Serializable
data class Posted(val thread: String, val messageRef: String)

// ---------------------------------------------------------- deliverables --
@Serializable
data class FileRef(
    val id: String,
    val name: String,
    val mime: String,
    val size: Long,
    val sha256: String = "",
    // ⟨1.3⟩ §17.1
    val kind: String = "document",
    val status: String = "ready",
    val width: Int? = null,
    val height: Int? = null,
    val durationS: Double? = null,
    val variants: FileVariants = FileVariants(),
    val transcript: String? = null,
)

@Serializable
data class FileVariants(val thumb: String? = null, val poster: String? = null)

@Serializable
data class Rating(val score: Int, val comment: String? = null, val ratedAt: String, val historyCount: Int = 0)

@Serializable
data class EmployeeRef(val code: String, val company: String, val kind: String, val titleFa: String, val department: String? = null)

@Serializable
data class Deliverable(
    val id: String,
    val ref: String,
    val company: String,
    val title: String,
    val summary: String = "",
    val body: String? = null,
    val producer: EmployeeRef,
    /** ⟨1.5⟩ null for what no work made: a CEO's weekly letter (§21.4), the weekly review's minutes (§21.3). */
    val workId: String? = null,
    val workRef: String? = null,
    val createdAt: String,
    val rating: Rating? = null,
    val attachments: List<FileRef> = emptyList(),
    val producedWith: JsonObject = JsonObject(emptyMap()),
    /** `{input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, equiv_cost_usd, cost_usd}` (§5.2); `{}` for rules. */
    val usage: JsonObject = JsonObject(emptyMap()),
    /** ⟨1.7.3⟩ `report` (the hub's own reporting, HQ-SYS) · `work` (an agent's output); null from a hub before ⟨1.7.3⟩. */
    val category: String? = null,
    /** ⟨1.7.3⟩ when the owner marked it seen; null = unseen (and always null from a hub before ⟨1.7.3⟩). */
    val seenAt: String? = null,
    /** ⟨1.7.3⟩ the archive record it was filed as (`AR-…`). */
    val filedAs: String? = null,
) {
    /** The hub sends `category` from ⟨1.7.3⟩ on; before it, the app keeps «seen» on the phone. */
    val hubKnowsSeen: Boolean get() = category != null

    /** `report` or `work`: the hub's own word, or, from an older hub, the producer (its system employee writes the reports). */
    val kind: String get() = category ?: if (producer.code.endsWith("-SYS")) "report" else "work"
}

/** ⟨1.7.3⟩ The outputs list's filters (§5.2): [seen] false the new ones, true the seen ones, null all; [category] report · work;
 *  [from]/[to] days (YYYY-MM-DD) in the owner's zone; [text] the search. The hub filters; the app filters again with [matches], for a hub
 *  before ⟨1.7.3⟩ (it ignores seen, category, from and to) and for what the owner marked seen on this phone meanwhile. */
data class DeliverableQuery(
    val seen: Boolean? = false,
    val category: String? = null,
    val unrated: Boolean = false,
    val company: String? = null,
    val producer: String? = null,
    val text: String? = null,
    val from: String? = null,
    val to: String? = null,
) {
    /** The query cache's key: every parameter. */
    val key: String get() = listOf(seen, category, unrated, company, producer, text?.trim()?.ifEmpty { null }, from, to).joinToString("|")

    /** How many filters beyond the tab are on (the filter button's badge). */
    val active: Int get() = listOf(category != null, unrated, company != null, producer != null, from != null || to != null).count { it }

    fun matches(d: Deliverable, seenAt: String?): Boolean {
        if (seen != null && (seenAt != null) != seen) return false
        if (category != null && d.kind != category) return false
        if (unrated && d.rating != null) return false
        if (company != null && d.company != company) return false
        if (producer != null && d.producer.code != producer) return false
        val day = com.coinepro.hq.core.format.ownerDay(d.createdAt)
        if (from != null && day < from) return false
        if (to != null && day > to) return false
        val t = text?.let(::fold)?.trim().orEmpty()
        if (t.isNotEmpty() && !fold("${d.ref} ${d.title} ${d.summary}").contains(t)) return false
        return true
    }

    companion object {
        /** Persian-safe comparison, as the hub's `fa_normalize`: ي/ی, ك/ک, no ZWNJ or tatweel, case folded. */
        fun fold(s: String): String = s.replace('ي', 'ی').replace('ك', 'ک').replace("\u200C", "").replace("\u0640", "").lowercase()
    }
}

/** ⟨1.7.3⟩ `POST /deliverables/seen` → how many changed. */
@Serializable
data class SeenOut(val updated: Int = 0)

/** ⟨1.7.3⟩ `POST /deliverables/{ref}/file` → the archive record it was filed as (the same one on a second call). */
@Serializable
data class FiledOut(val record: String)

// ---------------------------------------------------------- organisation --
@Serializable
data class CompanyCounts(val decisionsPending: Int = 0, val employeesActive: Int = 0, val workOpen: Int = 0)

@Serializable
data class Company(
    val id: String,
    val code: String,
    val kind: String,
    val nameFa: String? = null,
    val nameEn: String? = null,
    val colorIndex: Int? = null,
    val status: String = "active",
    val killSwitch: String = "released",
    val deployFreezeUntil: String? = null,
    /** ⟨1.4.6⟩ the active brand version (§18.14); null: the company shows its code. */
    val brandVersion: Int? = null,
    val counts: CompanyCounts = CompanyCounts(),
    val createdAt: String = "",
    val version: Int = 1,
)

@Serializable
data class Department(
    val id: String,
    val code: String,
    val company: String,
    val nameFa: String,
    val nameEn: String = "",
    val managerTitleFa: String = "",
    val manager: EmployeeRef? = null,
    val status: String = "active",
    val sort: Int = 0,
    /** ⟨1.6⟩ §22.1: what the department starts from and must reach, its character, and the team it may start with (a suggestion). */
    val mandate: Mandate? = null,
    val identityMd: String? = null,
    val team: List<TeamRole> = emptyList(),
    /** ⟨1.6.1⟩ §22.7: If-Match of the mandate's PUT. */
    val version: Int = 1,
)

@Serializable
data class Score(val value: Double? = null, val ownerAvg: Double? = null, val rankInDepartment: Int? = null, val trend: List<Double?> = emptyList())

@Serializable
data class ModelChoice(val model: String? = null, val effort: String? = null, val connection: String? = null)

@Serializable
data class RatingBrief(val deliverable: String, val score: Int, val ratedAt: String)

@Serializable
data class WorkBrief(val id: String = "", val ref: String = "", val title: String = "", val status: String = "")

@Serializable
data class Employee(
    val id: String,
    val code: String,
    val company: String,
    val department: String? = null,
    val kind: String,
    val titleFa: String,
    val titleEn: String = "",
    val displayName: String? = null,
    val status: String = "active",
    val activity: String = "idle",
    val activityAt: String? = null,
    val activityNote: String? = null,
    val reportsTo: EmployeeRef? = null,
    val model: ModelChoice? = null,
    val score: Score = Score(),
    val duties: List<JsonElement> = emptyList(),
    val permissions: List<JsonElement> = emptyList(),
    val hiredAt: String = "",
    val recentRatings: List<RatingBrief> = emptyList(),
    val recentWork: List<JsonObject> = emptyList(),
)

@Serializable
data class ChartNode(
    val code: String,
    val kind: String,
    val titleFa: String,
    val displayName: String? = null,
    val department: String? = null,
    val activity: String = "idle",
    val status: String = "active",
    val children: List<ChartNode> = emptyList(),
)

@Serializable
data class OrgChart(val company: String, val roots: List<ChartNode> = emptyList())

// ------------------------------------------------------------------ work --
@Serializable
data class Budget(val tokens: Long? = null, val tokensUsed: Long = 0, val usd: String? = null, val usdUsed: String = "0")

@Serializable
data class Schedule(val rrule: String, val timezone: String, val status: String = "active", val nextAt: String? = null)

@Serializable
data class ChainStep(
    val id: String,
    val ref: String,
    val depth: Int = 0,
    val status: String,
    val assignee: EmployeeRef? = null,
    val createdAt: String = "",
    val tokensUsed: Long = 0,
    val usdUsed: Double = 0.0,
)

@Serializable
data class Work(
    val id: String,
    val ref: String,
    val company: String,
    val department: String? = null,
    val title: String,
    val brief: String = "",
    val kind: String = "one_off",
    val priority: String = "P3",
    val status: String,
    val assignee: EmployeeRef? = null,
    val createdBy: Actor? = null,
    val createdAt: String = "",
    val updatedAt: String = "",
    val dueAt: String? = null,
    val overdue: Boolean = false,
    val progressPct: Int? = null,
    val progressNote: String? = null,
    val budget: Budget = Budget(),
    val schedule: Schedule? = null,
    val depth: Int = 0,
    val deliverableIds: List<String> = emptyList(),
    val chain: List<ChainStep> = emptyList(),
    val children: List<ChainStep> = emptyList(),
    val version: Int = 1,
)

@Serializable
data class WorkEvent(val id: Long, val kind: String, val at: String, val actorCode: String, val actorKind: String, val data: JsonObject = JsonObject(emptyMap()))

@Serializable
data class BudgetIn(val tokens: Long? = null, val usd: String? = null)

@Serializable
data class ScheduleIn(val rrule: String, val timezone: String = "Asia/Tehran")

@Serializable
data class WorkCreate(
    val company: String,
    val title: String,
    val brief: String = "",
    val kind: String = "one_off",
    val priority: String = "P3",
    val department: String? = null,
    val assignee: String? = null,
    val dueAt: String? = null,
    val budget: BudgetIn? = null,
    val schedule: ScheduleIn? = null,
)

@Serializable
data class PlannerItem(
    val ref: String,
    val title: String,
    val company: String,
    val at: String,
    val status: String,
    val priority: String = "P3",
    val assignee: String? = null,
    val recurring: Boolean = false,
)

@Serializable
data class PlannerDay(val date: String, val items: List<PlannerItem> = emptyList())

@Serializable
data class Planner(val scope: String, val timezone: String, val days: List<PlannerDay> = emptyList())

// -------------------------------------------------------------- messages --
@Serializable
data class Thread(
    val id: String,
    val code: String,
    val kind: String,
    val company: String? = null,
    val titleFa: String,
    val participants: List<Actor> = emptyList(),
    val lastMessageAt: String? = null,
    val lastRef: String? = null,
    val unread: Int = 0,
)

@Serializable
data class Citation(val kind: String = "", val ref: String = "")

@Serializable
data class Message(
    val id: String,
    val ref: String,
    val thread: String,
    val kind: String = "text",
    val author: Actor,
    val body: String,
    val createdAt: String,
    val attachments: List<FileRef> = emptyList(),
    val citations: List<Citation> = emptyList(),
    /** Refs this message points at: decision, work, resolution, corrects (contract §5). */
    val links: JsonObject = JsonObject(emptyMap()),
    /** ⟨1.5⟩ §21.1, §21.3: thread A's devil's-advocate exchange, a proactive note, the weekly review's brief. */
    val meta: AdvisorMeta? = null,
)

// --------------------------------------------------------- notifications --
@Serializable
data class Choice(val id: String, val labelFa: String)

@Serializable
data class Link(val kind: String, val ref: String? = null)

@Serializable
data class Notification(
    val id: String,
    val level: String,
    val company: String,
    val titleFa: String,
    val bodyFa: String = "",
    val state: String = "delivered",
    val createdAt: String,
    val readAt: String? = null,
    val link: Link? = null,
    val choices: List<Choice>? = null,
    val answer: String? = null,
)

@Serializable
data class NotificationPage(val items: List<Notification> = emptyList(), val nextCursor: String? = null)

// --------------------------------------------------------------- control --
@Serializable
data class KillSwitch(val scope: String, val company: String, val state: String, val reason: String? = null, val changedAt: String, val changedBy: String? = null)

@Serializable
data class Freeze(val company: String, val reason: String, val until: String, val createdBy: String = "")

@Serializable
data class ControlState(val holding: KillSwitch, val companies: List<KillSwitch> = emptyList(), val deployFreezes: List<Freeze> = emptyList())

// -------------------------------------------------------------- treasury --
@Serializable
data class Totals(
    val calls: Long = 0,
    val inputTokens: Long = 0,
    val outputTokens: Long = 0,
    val cacheReadTokens: Long = 0,
    val cacheWriteTokens: Long = 0,
    val thinkingTokens: Long = 0,
    val costUsd: String = "0",
    val equivCostUsd: String = "0",
)

@Serializable
data class BudgetUse(
    val company: String,
    val scopeType: String,
    val scopeRef: String,
    val period: String,
    val level: Int = 0,
    val pct: Double? = null,
    val tokenLimit: Long? = null,
    val tokensUsed: Long = 0,
    val usdLimit: String? = null,
    val usdUsed: String = "0",
)

@Serializable
data class Consumer(val actor: String, val company: String, val calls: Long = 0, val tokens: Long = 0, val usd: String = "0")

@Serializable
data class TreasurySummary(
    val period: String,
    val periodStart: String,
    val company: String? = null,
    val totals: Totals = Totals(),
    val budgets: List<BudgetUse> = emptyList(),
    val topConsumers: List<Consumer> = emptyList(),
)

@Serializable
data class BreakdownRow(
    val key: String? = null,
    val calls: Long = 0,
    val inputTokens: Long = 0,
    val outputTokens: Long = 0,
    val cacheReadTokens: Long = 0,
    val cacheWriteTokens: Long = 0,
    val costUsd: String = "0",
    val equivCostUsd: String = "0",
)

@Serializable
data class Connection(
    val id: String,
    val key: String,
    val displayName: String,
    val kind: String,
    val provider: String = "",
    val status: String,
    val statusReason: String? = null,
    val models: List<String> = emptyList(),
    val defaultModel: String? = null,
    val quotaResetAt: String? = null,
    val hasSecretRef: Boolean = false,
    val version: Int = 1,
)

// ----------------------------------------------------------------- audit --
@Serializable
data class AuditEntry(
    val seq: Long,
    val at: String,
    val action: String,
    val actionClass: String,
    val actor: Actor,
    val company: String,
    val summary: String,
    val stepUp: Boolean = false,
    val hash: String = "",
    val target: Map<String, String?> = emptyMap(),
)

@Serializable
data class AuditVerify(val ok: Boolean, val checked: Long = 0, val firstBadSeq: Long? = null, val anchor: String = "none", val verifiedAt: String)

// -------------------------------------------------------------- settings --
@Serializable
data class OwnerSettings(
    val timezone: String = "Asia/Tehran",
    val morningReportAt: String = "08:00",
    val digestMinutes: Int = 30,
    val ceoDailyAttention: Int = 6,
    val learningDailyCap: Int = 3,
    val calendars: List<String> = listOf("jalali"),
    val version: Int = 1,
    // ⟨1.5⟩ §21.12: the management tools' blocks (absent before prompt 12).
    val advisor: AdvisorSettings? = null,
    val weeklyReview: WeeklyAt? = null,
    val audioBriefings: AudioBriefings? = null,
    val ceoWeeklyLetter: WeeklyAt? = null,
    val reminders: ReminderSettings? = null,
    val digitalCeo: DceoSettings? = null,
    val substitutes: SubstituteSettings? = null,
)

/** The Problem body of every error (contract §1): a stable [code] and a Persian [messageFa]. */
@Serializable
data class Problem(
    val code: String = "internal_error",
    val messageFa: String? = null,
    val title: String? = null,
    val status: Int? = null,
    val requestId: String? = null,
    /** Field errors; ⟨1.5⟩ `422 batch_not_eligible` carries `fields.items: [{ref, reason}]` (§20.12), so it is read as JSON. */
    val fields: JsonObject? = null,
    /** ⟨1.4.6⟩ `409 not_ready`: what is still missing (§18.8, e.g. ["brand"]). */
    val missing: List<String> = emptyList(),
    /** ⟨1.5⟩ `422 send_blocked`: the outbound guard's refusal codes (§19.6). */
    val blockedReasons: List<String> = emptyList(),
)

/** One event of the holding stream (contract §7). */
@Serializable
data class StreamEvent(
    val id: String = "",
    val type: String = "",
    val at: String = "",
    val company: String? = null,
    val ref: String? = null,
    val data: JsonObject = JsonObject(emptyMap()),
)

// ------------------------------------------------------------------ v1.3 --
// Contract §17: voice to text, the Code Workshop and voice orders.

@Serializable
data class Segment(val startS: Double, val endS: Double, val text: String)

@Serializable
data class Engine(val name: String = "", val model: String = "", val version: String = "")

@Serializable
data class Transcript(
    val text: String,
    val language: String = "fa",
    val durationS: Double = 0.0,
    val confidence: Double = 0.0,
    val segments: List<Segment> = emptyList(),
    val fileId: String,
    val engine: Engine = Engine(),
)

@Serializable
data class WorkspacePolicy(val branchPrefix: String = "hq/", val mayOpenPr: Boolean = true, val merge: String = "owner_seal", val deploy: String = "owner_seal")

@Serializable
data class Workspace(
    val id: String,
    val code: String,
    val company: String,
    val repo: String,
    val defaultBranch: String = "main",
    val titleFa: String,
    val policy: WorkspacePolicy = WorkspacePolicy(),
    val status: String = "active",
)

@Serializable
data class Grant(
    val id: String,
    val ref: String,
    val workspace: String,
    val actions: List<String> = emptyList(),
    val driver: Actor? = null,
    val budgetUsd: Double,
    val expiresAt: String,
    val grantedBy: Actor? = null,
    val decisionRef: String? = null,
    val revokedAt: String? = null,
)

@Serializable
data class GrantIn(val workspace: String, val actions: List<String>, val driver: String?, val budgetUsd: Double, val expiresAt: String)

@Serializable
data class SessionUsage(val usd: Double = 0.0, val inputTokens: Long = 0, val outputTokens: Long = 0)

@Serializable
data class CodeSession(
    val id: String,
    val ref: String,
    val workspace: String,
    val grant: String,
    val title: String,
    val brief: String = "",
    val openedBy: Actor? = null,
    val driver: Actor,
    val runtime: String = "managed",
    val model: String = "",
    val effort: String = "",
    val state: String,
    val branch: String? = null,
    val prUrl: String? = null,
    val usage: SessionUsage = SessionUsage(),
    val createdAt: String,
    val updatedAt: String,
) {
    val open: Boolean get() = state !in setOf("done", "failed", "stopped")
}

@Serializable
data class SessionEvent(
    val seq: Long,
    val at: String,
    val type: String,
    val actor: Actor,
    val summaryFa: String = "",
    val data: JsonObject = JsonObject(emptyMap()),
)

@Serializable
data class OrderRoute(
    val company: String,
    val to: String,
    val kind: String,
    val workRef: String? = null,
    val sessionRef: String? = null,
    val decisionRef: String? = null,
)

@Serializable
data class Order(
    val ref: String,
    val summaryFa: String = "",
    val routes: List<OrderRoute> = emptyList(),
    val text: String = "",
    val source: String = "text",
    val fileId: String? = null,
    val createdAt: String? = null,
)
