package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

// ------------------------------------------------------------------ v1.4 --
// Contract §18: oversight, inquiries, the personal assistant, stars, skills, the academy, egress and MCP,
// founding and provisioning, backups. Same rules as Models.kt: camelCase here, snake_case on the wire,
// a default for every field the app can live without.

/** `"all"` or a list of company codes (MCP servers, service accounts, skill scope). Null means all. */
fun companiesOf(e: JsonElement?): List<String>? = when (e) {
    is JsonArray -> e.mapNotNull { (it as? JsonPrimitive)?.content }
    else -> null
}

@Serializable
data class Evidence(val kind: String, val ref: String, val note: String? = null)

// -------------------------------------------------------------- oversight --
@Serializable
data class LastRun(val at: String, val result: String, val findings: Int = 0)

@Serializable
data class Protocol(
    val id: String = "",
    val ref: String,
    val titleFa: String,
    val area: String,
    val checkMd: String = "",
    val method: String = "rule",
    val schedule: String = "",
    val scope: String = "",
    val evidenceMd: String = "",
    val severity: String = "medium",
    val answerable: String = "",
    val status: String = "active",
    val version: Int = 1,
    val sealedAt: String? = null,
    val lastRun: LastRun? = null,
)

@Serializable
data class FindingStep(val at: String, val by: Actor, val status: String, val note: String = "")

@Serializable
data class Finding(
    val id: String = "",
    val ref: String,
    val company: String,
    val protocol: String? = null,
    val severity: String,
    val titleFa: String,
    val bodyMd: String = "",
    val evidence: List<Evidence> = emptyList(),
    val status: String,
    val answerable: Actor? = null,
    val dueAt: String? = null,
    val openedAt: String,
    val closedAt: String? = null,
    val history: List<FindingStep> = emptyList(),
)

@Serializable
data class Criterion(val nameFa: String, val weight: Double)

@Serializable
data class Challenge(
    val id: String = "",
    val ref: String,
    val company: String,
    val period: String = "week",
    val titleFa: String,
    val briefMd: String = "",
    val criteria: List<Criterion> = emptyList(),
    val dueAt: String? = null,
    val status: String,
    val score: Double? = null,
    val judge: Actor? = null,
    val workRef: String? = null,
)

@Serializable
data class StandingOrder(
    val id: String = "",
    val ref: String,
    val textMd: String,
    val source: String = "text",
    val fileId: String? = null,
    val appliesTo: String = "overseer",
    val status: String,
    val version: Int = 1,
    val sealedAt: String? = null,
    val createdAt: String,
)

@Serializable
data class HeldAction(val kind: String, val summaryFa: String, val payloadDigest: String = "")

@Serializable
data class Hold(
    val id: String = "",
    val ref: String,
    val company: String,
    val action: HeldAction,
    val reasonMd: String = "",
    val heldBy: Actor? = null,
    val heldAt: String,
    val state: String,
    val decidedBy: Actor? = null,
    val decidedAt: String? = null,
)

@Serializable
data class OpenBySeverity(val critical: Int = 0, val high: Int = 0, val medium: Int = 0, val low: Int = 0)

@Serializable
data class ProtocolTally(val passed: Int = 0, val failed: Int = 0)

@Serializable
data class Compliance(
    val company: String,
    val score: Double,
    val byArea: Map<String, Double> = emptyMap(),
    val findingsOpen: OpenBySeverity = OpenBySeverity(),
    val protocols: ProtocolTally = ProtocolTally(),
    val trend: List<Double> = emptyList(),
)

@Serializable
data class WatchReport(
    val on: Boolean = false,
    val since: String? = null,
    val until: String? = null,
    val summaryMd: String = "",
    val held: List<String> = emptyList(),
    val urgent: List<String> = emptyList(),
    val findings: List<String> = emptyList(),
)

@Serializable
data class ChallengeWeek(val issued: Int = 0, val accepted: Int = 0, val submitted: Int = 0, val scored: Int = 0, val missed: Int = 0)

@Serializable
data class ProtocolsToday(val active: Int = 0, val failedToday: Int = 0)

@Serializable
data class OversightSummary(
    val watch: WatchReport = WatchReport(),
    val compliance: List<Compliance> = emptyList(),
    val findingsOpen: Map<String, Int> = emptyMap(),
    val holdsWaiting: Int = 0,
    val challengesWeek: ChallengeWeek = ChallengeWeek(),
    val protocols: ProtocolsToday = ProtocolsToday(),
)

// -------------------------------------------------------------- inquiries --
@Serializable
data class Inquiry(
    val id: String = "",
    val ref: String,
    val from: Actor,
    val to: Actor,
    val company: String,
    val questionMd: String,
    val dueAt: String? = null,
    val status: String,
    val answerMd: String? = null,
    val evidence: List<Evidence> = emptyList(),
    val answeredAt: String? = null,
    val threadRef: String? = null,
)

// ---------------------------------------------------------------- errands --
@Serializable
data class ErrandStep(val at: String, val kind: String, val summaryFa: String, val data: JsonObject = JsonObject(emptyMap()))

@Serializable
data class Usd(val usd: Double = 0.0)

@Serializable
data class Errand(
    val id: String = "",
    val ref: String,
    val titleFa: String,
    val briefMd: String = "",
    val source: String = "text",
    val fileIds: List<String> = emptyList(),
    val dueAt: String? = null,
    val status: String,
    val steps: List<ErrandStep> = emptyList(),
    val resultMd: String? = null,
    val attachments: List<FileRef> = emptyList(),
    val decisionRef: String? = null,
    val usage: Usd = Usd(),
    val createdAt: String,
    val updatedAt: String,
) {
    val open: Boolean get() = status in setOf("queued", "working", "waiting_owner")
}

// ------------------------------------------------------------------ stars --
@Serializable
data class RubricCriterion(val key: String, val nameFa: String, val weight: Double, val descriptionMd: String = "")

@Serializable
data class StarRubric(
    val company: String,
    val version: Int = 1,
    val criteria: List<RubricCriterion> = emptyList(),
    val rulesMd: String = "",
    val by: Actor? = null,
    val status: String = "active",
    val updatedAt: String? = null,
)

@Serializable
data class StandingParts(val kpi: Double = 0.0, val challenges: Double = 0.0, val compliance: Double = 0.0, val people: Double = 0.0, val efficiency: Double = 0.0)

@Serializable
data class CompanyStanding(
    val company: String,
    val stars: Double,
    val score: Double,
    val parts: StandingParts = StandingParts(),
    val rank: Int,
    val trend: List<Double> = emptyList(),
)

@Serializable
data class EmployeeStanding(
    val code: String,
    val company: String,
    val titleFa: String,
    val stars: Double,
    val count: Int = 0,
    val rankCompany: Int = 0,
    val rankHolding: Int = 0,
    val trend: List<Double> = emptyList(),
    /** ⟨1.4.3⟩ 0–100: tokens per accepted output, failed runs, estimate accuracy. */
    val efficiency: Double? = null,
)

@Serializable
data class StarRollup(
    val period: String,
    val key: String = "",
    val bestCompany: String? = null,
    val companies: List<CompanyStanding> = emptyList(),
    val employees: List<EmployeeStanding> = emptyList(),
    val lessons: List<String> = emptyList(),
)

@Serializable
data class Adoption(val company: String, val status: String, val decisionRef: String? = null)

@Serializable
data class Lesson(
    val id: String = "",
    val ref: String,
    val sourceCompany: String,
    val period: String = "",
    val titleFa: String,
    val bodyMd: String = "",
    val evidence: List<Evidence> = emptyList(),
    val adoption: List<Adoption> = emptyList(),
)

// ----------------------------------------------------------------- skills --
@Serializable
data class SkillScope(val roles: List<String> = emptyList(), val companies: JsonElement = JsonPrimitive("all"), val departments: List<String> = emptyList())

@Serializable
data class SkillReview(val by: Actor? = null, val at: String? = null, val verdict: String, val notesMd: String = "", val checks: Map<String, Boolean> = emptyMap())

@Serializable
data class SkillEval(val suite: String, val score: Double, val baseline: Double) {
    /** The academy's gate (§18.6): no worse than the baseline by more than one point. */
    val passed: Boolean get() = score >= baseline - 1
}

@Serializable
data class Skill(
    val id: String = "",
    val ref: String,
    val nameFa: String,
    val summaryFa: String = "",
    val bodyMd: String = "",
    val resources: List<FileRef> = emptyList(),
    val scope: SkillScope = SkillScope(),
    val version: Int = 1,
    val status: String,
    val review: SkillReview? = null,
    val eval: SkillEval? = null,
    val createdBy: Actor? = null,
    val createdAt: String? = null,
    val activatedAt: String? = null,
)

// ---------------------------------------------------------------- academy --
@Serializable
data class CurriculumModule(val key: String, val titleFa: String, val skills: List<String> = emptyList(), val evals: List<String> = emptyList())

@Serializable
data class Curriculum(val role: String, val version: Int = 1, val modules: List<CurriculumModule> = emptyList())

@Serializable
data class Baseline(val version: String, val score: Double)

@Serializable
data class EvalRun(val at: String, val subject: String, val score: Double, val passed: Boolean)

@Serializable
data class EvalSuite(
    val ref: String,
    val role: String,
    val titleFa: String,
    val cases: Int = 0,
    val baseline: Baseline? = null,
    val runs: List<EvalRun> = emptyList(),
)

@Serializable
data class TeachTarget(val kind: String, val ref: String)

@Serializable
data class TeachProposal(val kind: String, val diffMd: String)

@Serializable
data class TeachEval(val score: Double, val baseline: Double, val passed: Boolean)

@Serializable
data class Teaching(
    val id: String = "",
    val ref: String,
    val target: TeachTarget,
    val source: String = "text",
    val textMd: String,
    val proposal: TeachProposal? = null,
    val evalRun: TeachEval? = null,
    val status: String,
    val createdAt: String,
)

// --------------------------------------------------------- egress and MCP --
@Serializable
data class CompanyEgress(val company: String, val requests: Int = 0, val blocked: Int = 0)

@Serializable
data class EgressSummary(
    val period: String = "day",
    val requests: Long = 0,
    val blocked: Int = 0,
    val needsOwner: Int = 0,
    val bytesIn: Long = 0,
    val byCompany: List<CompanyEgress> = emptyList(),
    val byTool: Map<String, Long> = emptyMap(),
)

@Serializable
data class EgressEntry(
    val id: String,
    val at: String,
    val company: String,
    val actor: String,
    val tool: String,
    val method: String,
    val host: String,
    val status: Int = 0,
    val ms: Int = 0,
    val blockedReason: String? = null,
    val `class`: String = "A0",
)

@Serializable
data class McpTool(val name: String, val `class`: String = "A0", val enabled: Boolean = false)

@Serializable
data class McpServer(
    val id: String = "",
    val key: String,
    val titleFa: String,
    val transport: String = "http",
    val url: String? = null,
    val tools: List<McpTool> = emptyList(),
    val companies: JsonElement = JsonPrimitive("all"),
    val status: String,
    val hasSecret: Boolean = false,
    val addedAt: String? = null,
)

@Serializable
data class ServiceAccount(
    val id: String = "",
    val key: String,
    val site: String,
    val titleFa: String,
    val companies: JsonElement = JsonPrimitive("all"),
    val hasSecret: Boolean = false,
    val lastUsedAt: String? = null,
)

@Serializable
data class ToolInfo(val name: String, val `class`: String, val roles: List<String> = emptyList(), val status: String = "on", val via: String = "gateway")

// ------------------------------------------------ founding and provisioning --
@Serializable
data class FoundingSource(val kind: String, val repo: String? = null, val briefMd: String = "")

@Serializable
data class FoundingAudit(val sessionRef: String, val reportMd: String = "", val scores: Map<String, Double> = emptyMap())

@Serializable
data class Kpi(val nameFa: String, val target: String)

@Serializable
data class TeamSeat(val role: String, val model: String, val monthlyUsd: Double)

@Serializable
data class FoundingProposal(
    val departments: List<String> = emptyList(),
    val kpis: List<Kpi> = emptyList(),
    val team: List<TeamSeat> = emptyList(),
    val roadmapMd: String = "",
    val monthlyUsd: Double = 0.0,
)

@Serializable
data class Founding(
    val id: String = "",
    val ref: String,
    val nameFa: String,
    val nameEn: String = "",
    val code: String = "",
    val source: FoundingSource,
    val state: String,
    val audit: FoundingAudit? = null,
    val proposal: FoundingProposal? = null,
    val decisionRef: String? = null,
    val plan: String? = null,
    val company: String? = null,
    val createdAt: String,
    val updatedAt: String,
)

@Serializable
data class FirewallRule(val direction: String = "in", val protocol: String, val port: String, val sources: List<String> = emptyList(), val noteFa: String = "")

@Serializable
data class ServerPlan(
    val id: String = "",
    val ref: String,
    val founding: String? = null,
    val company: String = "",
    val name: String,
    val type: String,
    val location: String,
    val image: String,
    val privateNetwork: Boolean = true,
    val firewall: List<FirewallRule> = emptyList(),
    val software: List<String> = emptyList(),
    val workUser: String,
    val repo: String? = null,
    val monthlyEur: Double,
    val digest: String,
    val state: String,
    val decisionRef: String? = null,
    val run: String? = null,
)

@Serializable
data class RunStep(val key: String, val titleFa: String, val state: String, val startedAt: String? = null, val finishedAt: String? = null, val logTail: String = "")

@Serializable
data class NewServer(val name: String, val ipv4: String, val ipv6: String = "", val privateIp: String? = null)

@Serializable
data class Login(val ssh: String, val then: List<String> = emptyList())

@Serializable
data class ProvisionRun(
    val id: String,
    val plan: String,
    val state: String,
    val steps: List<RunStep> = emptyList(),
    val server: NewServer? = null,
    val login: Login? = null,
)

// ---------------------------------------------------------------- backups --
@Serializable
data class HourlyBackup(
    val lastAt: String? = null,
    val lastOkAt: String? = null,
    val nextAt: String? = null,
    val ok: Boolean? = null,
    val error: String? = null,
    val stale: Boolean? = null,
    val snapshot: String? = null,
    val sizeBytes: Long? = null,
)

@Serializable
data class WalStatus(val lastArchivedAt: String? = null, val lagS: Long? = null, val failedCount: Long? = null, val failing: Boolean = false, val readyCount: Int = 0)

/** ⟨1.4.5⟩ The daily base backups (PITR reaches back to the oldest) and the daily repository check. */
@Serializable
data class BaseBackup(val lastAt: String? = null, val count: Int = 0)

@Serializable
data class RepoCheck(val lastAt: String? = null, val ok: Boolean? = null)

@Serializable
data class BackupDestination(
    val key: String,
    val configured: Boolean = false,
    val ok: Boolean? = null,
    val error: String? = null,
    val lastOkAt: String? = null,
    val usedBytes: Long? = null,
    val quotaBytes: Long? = null,
)

@Serializable
data class Retention(val hourly: Int = 0, val daily: Int = 0, val weekly: Int = 0, val monthly: Int = 0, val yearly: Int = 0)

@Serializable
data class RestoreTest(val lastAt: String? = null, val ok: Boolean? = null, val durationS: Long? = null, val notes: String? = null, val pitrTarget: String? = null, val source: String? = null)

@Serializable
data class VaultSnapshot(val configured: Boolean? = null, val lastAt: String? = null, val ok: Boolean? = null)

@Serializable
data class BackupStatus(
    val hourly: HourlyBackup = HourlyBackup(),
    val wal: WalStatus = WalStatus(),
    val baseBackup: BaseBackup? = null,
    val check: RepoCheck? = null,
    val destinations: List<BackupDestination> = emptyList(),
    val retention: Retention = Retention(),
    val restoreTest: RestoreTest = RestoreTest(),
    val openbaoSnapshot: VaultSnapshot = VaultSnapshot(),
    val encryption: String = "",
)

// ---------------------------------------------------------- hiring ⟨1.4.2⟩ --
// Contract §18.11: hiring starts with the owner. Closed by default; the owner opens it to the CEOs' proposals or hires directly.
/** ⟨1.4.3⟩ A company's month: its envelope (the month budget), what its employees' estimates commit, what it used, hires this month. */
@Serializable
data class Envelope(val company: String, val tokensMonth: Long? = null, val committedMonth: Long = 0, val usedMonth: Long = 0, val hiresMonth: Int = 0)

/** `mode`: `delegated` (each CEO hires inside the envelope and picks the model) or `proposals` (every hire is the owner's card). */
@Serializable
data class Hiring(
    val state: String = "closed",
    val mode: String? = null,
    val changedAt: String? = null,
    val changedBy: Actor? = null,
    val withdrawn: List<String> = emptyList(),
    val envelopes: List<Envelope> = emptyList(),
)

@Serializable
data class RoleLimits(val stepsPerRun: Int = 0, val tokensPerStep: Long = 0, val tokensPerRun: Long = 0)

/** A role charter as `GET /roles` returns it (agents/roles/<role>.md frontmatter). */
@Serializable
data class RoleInfo(
    val role: String,
    val titleFa: String,
    val titleEn: String = "",
    val kind: String,
    val scope: String,
    val department: String? = null,
    val model: String,
    val effort: String,
    val priority: String = "",
    val tools: List<String> = emptyList(),
    val limits: RoleLimits = RoleLimits(),
    val version: Int = 1,
)

/** The roles the owner can hire into a department: `employee` charters whose scope fits the company and whose department (if any) is this one. */
fun hireableRoles(roles: List<RoleInfo>, companyKind: String, department: String?): List<RoleInfo> {
    val scope = if (companyKind == "holding") "holding" else "company"
    return roles.filter { it.kind == "employee" && it.scope == scope && (it.department == null || it.department == department) }
}

@Serializable
data class HireIn(
    val company: String,
    val department: String,
    val role: String,
    val titleFa: String,
    val titleEn: String? = null,
    val model: String? = null,
    val effort: String? = null,
    val reason: String? = null,
)

@Serializable
data class HiredEmployee(val code: String, val company: String, val department: String? = null, val titleFa: String = "", val status: String = "active")

@Serializable
data class HireDecision(val ref: String, val status: String = "approved", val resolution: String? = null)

@Serializable
data class HireOut(val employee: HiredEmployee, val decision: HireDecision)

// --------------------------------------------------------- stories ⟨1.4.3⟩ --
// Contract §18.12: designed cards per company, system and CEO posts, 24 hours, pulled and never pushed.
@Serializable
data class StoryFigure(val labelFa: String, val value: String)

@Serializable
data class StoryLinks(val employee: String? = null, val deliverable: String? = null, val decision: String? = null, val work: String? = null, val period: String? = null)

@Serializable
data class Story(
    val id: String = "",
    val ref: String,
    val company: String,
    val kind: String,
    val author: Actor,
    val titleFa: String,
    val bodyFa: String = "",
    val figures: List<StoryFigure> = emptyList(),
    val media: FileRef? = null,
    val links: StoryLinks = StoryLinks(),
    val createdAt: String,
    val expiresAt: String? = null,
    val seen: Boolean = false,
    val welcomed: Boolean = false,
)

@Serializable
data class StoryRing(val company: String, val unseen: Int = 0, val latestAt: String = "", val items: List<Story> = emptyList())

/** The body of PUT /budgets for company month envelopes (contract §9; the seal is bound to its exact text). */
@Serializable
data class CompanyBudgetIn(val company: String, val scopeType: String, val scopeRef: String, val period: String, val tokenLimit: Long? = null, val enabled: Boolean = true)

@Serializable
data class BudgetsPut(val budgets: List<CompanyBudgetIn>)

