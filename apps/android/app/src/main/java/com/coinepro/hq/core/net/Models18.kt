package com.coinepro.hq.core.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull

// ------------------------------------------------------------------ v1.5 --
// Contract §21 (prompt 12): the owner's management tools. The premium advisor (decision memos, the devil's advocate, proactive
// notes, the weekly review), "ask the hub", spoken briefings and the CEOs' weekly letters, department ranks and the monthly HR round,
// the real diff on a deploy card, waste, ROI, a new connection, quick notes and cartable reminders, refuted claims on the health
// board, the digital CEO (prediction only), and §21.13's substitute players (GPT, Gemini, DeepSeek) with their seats, sign-ins and
// creatives; §21.14 ⟨1.5.1⟩ fixes the shapes the apps read. Same rules as Models.kt: camelCase here, snake_case on the wire,
// nullable exactly where §21 writes `|null`. Tokens are whole numbers, money a decimal string (§1), rates and confidences 0..1.
// Companies and players are data: nothing here counts them.

@Serializable
data class Usage(val tokens: Long = 0, val usd: String = "0")

// --------------------------------------------------- the premium advisor (§21.1) --
/** A substitute's independent opinion on the same masked facts pack (§21.13 seats `advisor_second_opinion`, `third_opinion`). */
@Serializable
data class Opinion(
    /** gpt · gemini · deepseek */
    val player: String,
    val model: String = "",
    /** approve · reject · return · ask */
    val recommendation: String = "ask",
    val confidence: Double = 0.0,
    val summaryFa: String = "",
    val differences: List<String> = emptyList(),
    /** Code: the same recommendation as the advisor's. */
    val agrees: Boolean = false,
)

@Serializable
data class MemoOption(val titleFa: String = "", val prosMd: String = "", val consMd: String = "")

@Serializable
data class MemoRisk(val titleFa: String = "", val likelihood: String = "medium", val impact: String = "medium", val mitigationFa: String = "")

@Serializable
data class DecisionMemo(
    val id: String = "",
    val ref: String,
    val decision: String,
    val decisionVersion: Int = 1,
    /** standard · devil */
    val mode: String = "standard",
    /** writing · ready · failed · stale (the card changed) */
    val state: String = "ready",
    /** owner · auto */
    val trigger: String = "owner",
    val summaryFa: String = "",
    val recommendation: String = "ask",
    val confidence: Double = 0.0,
    val options: List<MemoOption> = emptyList(),
    /** The strongest case against; never empty once ready. */
    val againstMd: String = "",
    val risks: List<MemoRisk> = emptyList(),
    /** What the owner should ask the proposer. */
    val questions: List<String> = emptyList(),
    val citations: List<Citation> = emptyList(),
    val usage: Usage = Usage(),
    val secondOpinion: Opinion? = null,
    /** ⟨1.5.1⟩ optional. */
    val thirdOpinion: Opinion? = null,
    val createdAt: String = "",
)

/** What a card carries about its memos (§21.1: `Decision.memos`). */
@Serializable
data class MemoBrief(val ref: String = "", val mode: String = "standard", val state: String = "ready")

@Serializable
data class AdvisorTrigger(
    val id: String,
    /** Unique per day: the advisor is woken once per key. */
    val key: String = "",
    /** budget · quota · compliance · incident · revenue · waiting_decisions · finding · okr */
    val kind: String,
    val company: String? = null,
    val firedAt: String = "",
    /** Gathered by code before the advisor wakes. */
    val facts: JsonObject = JsonObject(emptyMap()),
    val messageRef: String? = null,
    /** sent · deferred · capped */
    val state: String = "sent",
)

@Serializable
data class Proactive(val kind: String = "", val key: String = "")

/** What a message of thread A carries in `meta` (§21.1, §21.3, ⟨1.5.1⟩): a devil's-advocate exchange, a proactive note, the review brief. */
@Serializable
data class AdvisorMeta(val mode: String? = null, val proactive: Proactive? = null, val review: String? = null)

// ------------------------------------------------------------ ask the hub (§21.2) --
const val ASK_MAX = 500

@Serializable
data class AskScope(val companies: List<String>? = null, val kinds: List<String>? = null)

@Serializable
data class AskCitation(
    /** resolution · decision · deliverable · work · message · doc · code */
    val kind: String,
    val ref: String? = null,
    val repo: String? = null,
    val path: String? = null,
    /** [from, to] */
    val lines: List<Int>? = null,
    val commit: String? = null,
    val snippet: String = "",
)

@Serializable
data class Ask(
    val id: String = "",
    val ref: String,
    val q: String,
    val scope: AskScope? = null,
    /** queued · searching · answering · done · failed */
    val state: String,
    /** 0 = nothing retrieved, and no model ran. */
    val found: Int = 0,
    val answerMd: String? = null,
    val citations: List<AskCitation> = emptyList(),
    /** Repositories the hub cannot read; they were not searched. */
    val notIndexed: List<String> = emptyList(),
    val usage: Usage = Usage(),
    val createdAt: String = "",
    val finishedAt: String? = null,
) {
    val live: Boolean get() = state == "queued" || state == "searching" || state == "answering"
}

// ------------------------------------------------------- the weekly review (§21.3) --
@Serializable
data class AgendaItem(
    val n: Int,
    /** decision · risk · okr · finding · budget · revenue · outcome_review · note */
    val kind: String,
    val ref: String = "",
    val company: String? = null,
    val titleFa: String = "",
    val whyFa: String = "",
    /** open · done · deferred */
    val status: String = "open",
    val ownerNote: String? = null,
)

@Serializable
data class WeeklyReview(
    val id: String = "",
    val ref: String,
    /** The week's Saturday, YYYY-MM-DD, owner TZ. */
    val week: String,
    /** ready · in_progress · done · skipped */
    val state: String,
    /** ≤ 12, in the kind order of §21.3. */
    val agenda: List<AgendaItem> = emptyList(),
    val briefMessageRef: String? = null,
    val minutesRef: String? = null,
    val startedAt: String? = null,
    val finishedAt: String? = null,
    val durationS: Int? = null,
    val version: Int = 1,
)

// ------------------------------------------------- briefings and CEO letters (§21.4) --
@Serializable
data class Span(val from: String = "", val to: String = "")

@Serializable
data class VoiceInfo(val engine: String = "piper", val version: String = "", val voice: String = "", val license: String = "")

@Serializable
data class Briefing(
    val id: String = "",
    val ref: String,
    /** morning · ceo_letter */
    val kind: String,
    val company: String,
    val period: Span = Span(),
    val deliverableRef: String = "",
    val textMd: String = "",
    /** Ogg/Opus made on the hub (Piper); nothing leaves it. */
    val audio: FileRef? = null,
    /** pending · ready · off · failed */
    val audioState: String = "off",
    val voice: VoiceInfo? = null,
    val createdAt: String = "",
)

// -------------------------------------------- department rank, HR round (§21.5) --
/** 0..100 each; [owner] null = no ratings, its 15% spread over the other three. */
@Serializable
data class RankParts(val people: Double = 0.0, val delivery: Double = 0.0, val efficiency: Double = 0.0, val owner: Double? = null)

@Serializable
data class DepartmentRank(
    /** week · month */
    val period: String,
    val key: String = "",
    val company: String,
    val department: String,
    val score: Double,
    val parts: RankParts = RankParts(),
    val employees: Int = 0,
    val rankCompany: Int = 0,
    /** Among the departments of the same code across companies; null when only one exists. */
    val rankHolding: Int? = null,
    val trend: List<Double> = emptyList(),
    val computedAt: String = "",
)

@Serializable
data class HrEmployee(
    val code: String,
    val titleFa: String = "",
    /** Null in a month without the facts to score (the hub sends `null`). */
    val score: Double? = null,
    val scorePrev: Double? = null,
    val stars: Double? = null,
    val efficiency: Double? = null,
    val ownerAvg: Double? = null,
    val failedShare: Double = 0.0,
    val findingsOpen: Int = 0,
    val refutedClaims: Int = 0,
    val probationUntil: String? = null,
    /** promote_candidate · coach · demote_candidate · dismiss_candidate · probation_end — rules, never a model. */
    val flags: List<String> = emptyList(),
)

@Serializable
data class HrRound(
    val id: String = "",
    val ref: String,
    val company: String,
    /** ⟨1.5.1⟩ the Jalali month the round runs in, "1405-08". */
    val month: String,
    /** drafting · proposed · done */
    val state: String,
    val evaluator: Actor,
    val dueAt: String = "",
    val employees: List<HrEmployee> = emptyList(),
    val deliverableRef: String? = null,
    val decisions: List<String> = emptyList(),
    val teachings: List<String> = emptyList(),
)

@Serializable
data class EvaluationChange(val model: String? = null, val effort: String? = null, val titleFa: String? = null, val quotaEstimateMonth: Long? = null)

/** `evaluation` payload v2 (§21.5). */
@Serializable
data class EvaluationPayload(
    val employee: String = "",
    /** promote · demote · dismiss · confirm */
    val recommendation: String = "",
    val change: EvaluationChange? = null,
    val transferTo: String? = null,
    val round: String = "",
    val evidence: List<Source> = emptyList(),
    val unflagged: Boolean = false,
    val overrideReason: String? = null,
)

// -------------------------------------------------- the deploy card's diff (§21.6) --
@Serializable
data class DiffFile(
    val path: String,
    /** added · modified · removed · renamed */
    val status: String = "modified",
    val additions: Int = 0,
    val deletions: Int = 0,
    val binary: Boolean = false,
    val patch: String? = null,
    /** Cut at 400 lines here; `GET /decisions/{ref}/diff?file=` gives the whole patch (≤ 2000 lines). */
    val truncated: Boolean = false,
    /** A line the secret scan flagged is masked, here and everywhere. */
    val secretMasked: Boolean = false,
)

@Serializable
data class DeployDiff(
    val baseSha: String = "",
    val headSha: String = "",
    val totalFiles: Int = 0,
    val totalAdditions: Int = 0,
    val totalDeletions: Int = 0,
    val truncated: Boolean = false,
    val fetchedAt: String = "",
    val files: List<DiffFile> = emptyList(),
)

@Serializable
data class ReviewFinding(
    val path: String = "",
    val line: Int = 0,
    /** low · medium · high · critical */
    val severity: String = "low",
    val titleFa: String = "",
    val detailMd: String = "",
    /** ⟨1.5.1⟩ the CTO's or QC's check: true, false, or null while it is checked. */
    val verified: Boolean? = null,
)

/** A substitute's second review of the change (§21.13 seat `code_review`); it never approves or blocks. */
@Serializable
data class SecondReview(
    val player: String,
    val model: String = "",
    val findings: List<ReviewFinding> = emptyList(),
    /** ⟨1.5.1⟩ `bool|int`: whether the review was checked, or how many findings were. */
    val verified: JsonElement? = null,
) {
    val checked: Int get() = (verified as? JsonPrimitive)?.let { it.intOrNull ?: if (it.booleanOrNull == true) findings.size else 0 } ?: 0
}

@Serializable
data class CiInfo(val status: String = "", val url: String? = null)

@Serializable
data class TestCount(val passed: Int = 0, val failed: Int = 0)

/** The one definition of the `deploy` payload ⟨1.5⟩ (§21.6), with prompt 11's window and conflicts (§20.9). */
@Serializable
data class DeployPayload(
    val repo: String = "",
    val prUrl: String = "",
    /** The card is bound to it, diff or not: a new push supersedes the card. */
    val headSha: String = "",
    val diffStat: String = "",
    val ci: CiInfo = CiInfo(),
    val tests: TestCount = TestCount(),
    val rollout: String = "",
    val window: Span? = null,
    val calendarConflicts: List<Conflict>? = null,
    val diff: DeployDiff? = null,
    /** no_access · too_large · fetch_failed */
    val diffUnavailable: String? = null,
    val secondReview: SecondReview? = null,
)

// ----------------------------------------------------- waste, ROI, connection (§21.7) --
@Serializable
data class WasteTop(val employee: String? = null, val runId: String? = null, val workRef: String? = null, val tokens: Long = 0)

@Serializable
data class WasteItem(
    /** failed_runs · cancelled_work · no_progress_runs · retry_loops · router_errors · duplicate_calls · cache_miss · over_model */
    val category: String,
    val tokens: Long = 0,
    val usd: String = "0",
    val count: Int = 0,
    val top: List<WasteTop> = emptyList(),
)

@Serializable
data class WasteDay(
    val day: String,
    /** null = the holding total. */
    val company: String? = null,
    val totalTokens: Long = 0,
    val totalUsd: String = "0",
    val wasteTokens: Long = 0,
    val wasteUsd: String = "0",
    val share: Double = 0.0,
    /** ⟨1.5.1⟩ the relative change of waste against the trailing 7-day average (+0.2 = 20% more). */
    @SerialName("vs_7d") val vs7d: Double = 0.0,
    val items: List<WasteItem> = emptyList(),
)

@Serializable
data class Attributed(val rescued: Int? = null, val resolvedConversations: Int? = null)

@Serializable
data class RoiRow(
    /** employee · department · company */
    val by: String,
    val key: String,
    val company: String,
    val period: String = "month",
    val periodKey: String = "",
    val costUsd: String = "0",
    val accepted: Int = 0,
    val avgRating: Double? = null,
    /** Σ (owner rating ÷ 10) over accepted deliverables. */
    val valuePoints: Double = 0.0,
    val costPerAcceptedUsd: String? = null,
    val attributed: Attributed = Attributed(),
    /** Companies only (§19.1): an agent's revenue is never invented. */
    val revenueUsd: String? = null,
    val netUsd: String? = null,
    val roi: Double? = null,
    /** ⟨1.5.1⟩ ROI for companies; cost per accepted deliverable for departments and employees. */
    val trend: List<Double> = emptyList(),
)

@Serializable
data class Price(val inputPerMtok: String, val outputPerMtok: String)

@Serializable
data class ConnLimits(val rpm: Int? = null, val tpm: Int? = null, val dailyUsd: String? = null)

/** What `POST /connections` takes (⟨1.5.1⟩ shapes): sealed on the SHA-256 of exactly this body. `pricing` and `limits` are always written. */
@Serializable
data class ConnectionIn(
    val key: String,
    val provider: String,
    /** subscription · api_key */
    val kind: String,
    val displayName: String,
    val baseUrl: String? = null,
    val models: List<String>,
    val defaultModel: String? = null,
    val pricing: Map<String, Price>,
    val limits: ConnLimits,
    val fallbackPriority: Int? = null,
)

/** ⟨1.5.1⟩ the providers the router supports. */
val ROUTER_PROVIDERS = listOf("anthropic", "openai", "google", "deepseek", "mistral", "openai_compatible")

/** A connection key: lower-case Latin, digits and hyphens, 3–40, unique. */
val CONNECTION_KEY = Regex("^[a-z0-9][a-z0-9-]{2,39}$")

/** A base URL the egress guard would take: https, and never a private, loopback or link-local address. */
fun publicHttps(u: String): Boolean {
    val url = runCatching { java.net.URI(u.trim()) }.getOrNull() ?: return false
    if (url.scheme != "https") return false
    val h = url.host?.lowercase() ?: return false
    return !(h == "localhost" || Regex("^(10|127)\\.").containsMatchIn(h) || h.startsWith("192.168.") || Regex("^172\\.(1[6-9]|2\\d|3[01])\\.").containsMatchIn(h) ||
        h.startsWith("169.254.") || h.endsWith(".internal") || h.endsWith(".local") || Regex("^\\[?(::1|f[cd])").containsMatchIn(h))
}

// ---------------------------------------------- quick notes, reminders (§21.8) --
@Serializable
data class PromotedTo(val kind: String, val ref: String)

@Serializable
data class OwnerNote(
    val id: String = "",
    val ref: String,
    val textMd: String,
    /** text · voice */
    val source: String = "text",
    /** The original recording of a voice note. */
    val fileId: String? = null,
    val tags: List<String> = emptyList(),
    /** open · promoted · archived — never deleted. */
    val status: String = "open",
    val promotedTo: PromotedTo? = null,
    val createdAt: String = "",
    val updatedAt: String = "",
    val version: Int = 1,
)

/** Tags from free text: split on commas and #, trimmed, at most eight. */
fun tagsOf(s: String): List<String> = s.split(Regex("[,،#]+")).map { it.trim() }.filter { it.isNotEmpty() }.distinct().take(8)

@Serializable
data class Reminder(
    val at: String = "",
    /** half · before_expiry · age_24h · age_72h · age_7d */
    val kind: String = "",
)

/** §5.1 ⟨1.5⟩: the digital CEO's prediction on a card; null while it is pending (reveal "after"). */
@Serializable
data class DceoBrief(val verdict: String = "", val confidence: Double = 0.0, val method: String = "baseline", val correct: Boolean? = null)

// --------------------------------------------- claims and the health board (§21.9) --
@Serializable
data class CheckedClaim(
    val id: String = "",
    val ref: String,
    val company: String,
    val deliverable: String = "",
    val employee: String = "",
    /** ≤ 300, masked. */
    val claimMd: String = "",
    /** confirmed · refuted · unverifiable */
    val verdict: String,
    val checkedBy: Actor,
    val protocol: String? = null,
    val evidence: List<Source> = emptyList(),
    val at: String = "",
)

@Serializable
data class AgentHealth(
    val employee: String,
    val company: String,
    val period: String = "7d",
    val runs: Int = 0,
    val failedShare: Double = 0.0,
    val refusedShare: Double = 0.0,
    val retryLoops: Int = 0,
    val ownerReturns: Int = 0,
    val claimsChecked: Int = 0,
    val refuted: Int = 0,
    val refutedShare: Double? = null,
    val costUsd: String = "0",
    /** truth · reliability · loops — rules. */
    val flags: List<String> = emptyList(),
)

// ------------------------------------------------------- the digital CEO (§21.10) --
@Serializable
data class Prediction(
    val decision: String,
    val madeAt: String = "",
    /** baseline · model */
    val method: String = "baseline",
    /** approve · reject · return */
    val verdict: String,
    val confidence: Double = 0.0,
    val rationaleFa: String? = null,
    val principles: List<String> = emptyList(),
    val sealedHash: String = "",
    val seenBefore: Boolean = false,
    val actual: String? = null,
    val correct: Boolean? = null,
    /** ⟨1.5.1⟩ the card's kind and title. */
    val kind: String? = null,
    val title: String? = null,
)

@Serializable
data class Principle(
    val id: String = "",
    val ref: String,
    val textFa: String,
    val sources: List<Source> = emptyList(),
    /** proposed · active · retired */
    val status: String,
    val editedByOwner: Boolean = false,
    val version: Int = 1,
    val updatedAt: String = "",
)

@Serializable
data class KindAccuracy(val n: Int = 0, val accuracy: Double = 0.0)

@Serializable
data class CalibrationBucket(val bucket: String, val n: Int = 0, val hitRate: Double = 0.0)

@Serializable
data class DceoStats(
    /** 30d · 90d · all */
    val window: String,
    val n: Int = 0,
    val accuracy: Double? = null,
    val baselineAccuracy: Double? = null,
    val modelAccuracy: Double? = null,
    val brier: Double? = null,
    val byKind: Map<String, KindAccuracy> = emptyMap(),
    val calibration: List<CalibrationBucket> = emptyList(),
)

@Serializable
data class DceoSettings(val enabled: Boolean = true, val reveal: String = "after", val modelPredictions: Boolean = true, val maxModelPerDay: Int = 20)

/** ⟨1.5.1⟩ `GET /digital-ceo`: the three windows, the setting, and `hidden` = clean predictions so far. */
@Serializable
data class DceoView(val stats: List<DceoStats> = emptyList(), val settings: DceoSettings = DceoSettings(), val hidden: Int = 0)

// -------------------------------------------------------- owner settings (§21.12) --
@Serializable
data class AutoMemo(val enabled: Boolean = true, val maxPerDay: Int = 3)

@Serializable
data class AdvisorSettings(val autoMemo: AutoMemo = AutoMemo(), val proactivePerDay: Int = 3)

/** A weekly moment: [day] "sa".."fr", [at] "HH:MM" in the owner's zone. */
@Serializable
data class WeeklyAt(val enabled: Boolean = true, val day: String = "sa", val at: String = "10:00")

@Serializable
data class AudioBriefings(val morning: Boolean = true, val ceoLetters: Boolean = true)

@Serializable
data class ReminderSettings(val enabled: Boolean = true, val fraction: Double = 0.5, val beforeExpiryH: Int = 6, val agesH: List<Int> = listOf(24, 72, 168))

@Serializable
data class SubstituteSettings(val behindRatio: Double = 0.4, val creativeDefaultImage: String = "gpt")

/** The §21.12 blocks of `/owner/settings`, as the settings screen edits them. */
data class ManagementSettings(
    val advisor: AdvisorSettings,
    val weeklyReview: WeeklyAt,
    val audioBriefings: AudioBriefings,
    val ceoWeeklyLetter: WeeklyAt,
    val reminders: ReminderSettings,
    val digitalCeo: DceoSettings,
    val substitutes: SubstituteSettings,
) {
    /** ⟨1.5.1⟩ PUT /owner/settings sends each changed block whole: the blocks of this that differ from [base], every field written. */
    fun changedFrom(base: ManagementSettings): Map<String, JsonElement> = buildMap {
        val j = Api.jsonBody
        if (advisor != base.advisor) put("advisor", j.encodeToJsonElement(AdvisorSettings.serializer(), advisor))
        if (weeklyReview != base.weeklyReview) put("weekly_review", j.encodeToJsonElement(WeeklyAt.serializer(), weeklyReview))
        if (audioBriefings != base.audioBriefings) put("audio_briefings", j.encodeToJsonElement(AudioBriefings.serializer(), audioBriefings))
        if (ceoWeeklyLetter != base.ceoWeeklyLetter) put("ceo_weekly_letter", j.encodeToJsonElement(WeeklyAt.serializer(), ceoWeeklyLetter))
        if (reminders != base.reminders) put("reminders", j.encodeToJsonElement(ReminderSettings.serializer(), reminders))
        if (digitalCeo != base.digitalCeo) put("digital_ceo", j.encodeToJsonElement(DceoSettings.serializer(), digitalCeo))
        if (substitutes != base.substitutes) put("substitutes", j.encodeToJsonElement(SubstituteSettings.serializer(), substitutes))
    }
}

/** The management blocks of the owner's settings, when the server sends all of them (a server before prompt 12 sends none). */
fun OwnerSettings.management(): ManagementSettings? = ManagementSettings(
    advisor ?: return null, weeklyReview ?: return null, audioBriefings ?: return null, ceoWeeklyLetter ?: return null,
    reminders ?: return null, digitalCeo ?: return null, substitutes ?: return null,
)

// ------------------------------------------------------ substitute players (§21.13) --
@Serializable
data class SubLogin(
    /** signed_out · signing_in · signed_in · expired */
    val state: String = "signed_out",
    val planFa: String = "",
    val since: String? = null,
    val lastOkAt: String? = null,
)

@Serializable
data class SubModel(val id: String, val label: String = "", val tier: String = "strong", val available: Boolean = true)

/** Cap = cli · web · api · off */
@Serializable
data class SubCaps(val text: String = "off", val image: String = "off", val video: String = "off")

/** The signed-in browser profile on the hub (Playwright). */
@Serializable
data class WebProfile(
    val account: String = "",
    /** signed_in · expired · signed_out */
    val state: String = "signed_out",
    val lastOkAt: String? = null,
    val recipeVersion: String = "",
    val lastFailure: String? = null,
)

@Serializable
data class Seat(
    /** advisor_second_opinion · code_review · overseer_cross_check · assistant_errand · content_draft · long_read · quick_search · third_opinion · creative */
    val seat: String,
    /** cli · web */
    val via: String = "cli",
    val model: String = "",
    val enabled: Boolean = true,
    val perDay: Int = 0,
    val usedToday: Int = 0,
    /** ⟨1.5.1⟩ `creative` only: its video cap beside the image cap. */
    val perDayVideo: Int? = null,
    val usedTodayVideo: Int? = null,
)

@Serializable
data class SubMonth(
    /** Jalali, "1405-08". */
    val key: String = "",
    val calls: Int = 0,
    val skipped: Int = 0,
    val inputTokens: Long = 0,
    val outputTokens: Long = 0,
    /** The CLI gave no usage report. */
    val estimated: Boolean = false,
    val equivUsd: String = "0",
    val priceUsd: String = "0",
    /** equiv_usd ÷ price_usd; null for a free account. */
    val valueRatio: Double? = null,
)

@Serializable
data class Substitute(
    /** gpt · gemini · deepseek */
    val player: String,
    /** chatgpt-plus · gemini-pro · deepseek-free */
    val connection: String,
    /** codex_cli · gemini_cli · null (DeepSeek: web only) */
    val runner: String? = null,
    val login: SubLogin = SubLogin(),
    /** ready · limited · off · error */
    val status: String = "off",
    val limitedUntil: String? = null,
    val statusReason: String? = null,
    val models: List<SubModel> = emptyList(),
    val capabilities: SubCaps = SubCaps(),
    val web: WebProfile = WebProfile(),
    val seats: List<Seat> = emptyList(),
    val month: SubMonth = SubMonth(),
    val version: Int = 1,
)

/** One row of `PUT /substitutes/{player}/seats` (sealed on the SHA-256 of the whole list); `per_day_video` only for `creative`. */
@Serializable
data class SeatIn(val seat: String, val via: String, val model: String, val enabled: Boolean, val perDay: Int, val perDayVideo: Int? = null)

fun Seat.toIn(): SeatIn = SeatIn(seat, via, model, enabled, perDay, perDayVideo)

@Serializable
data class SubstituteLogin(
    val id: String,
    val connection: String = "",
    /** device_code · auth_code */
    val method: String = "device_code",
    val verificationUrl: String = "",
    val userCode: String? = null,
    val expiresAt: String = "",
    /** waiting · done · expired · failed */
    val state: String = "waiting",
    val statusReason: String? = null,
)

/** Persian text set by the hub over a creative, never generated. */
@Serializable
data class Overlay(val titleFa: String = "", val bodyFa: String? = null, val ctaFa: String? = null, val mark: Boolean = true)

@Serializable
data class CreativeSource(val player: String = "", val model: String = "", val at: String = "")

@Serializable
data class Creative(
    val id: String = "",
    val ref: String,
    val company: String,
    /** image · video */
    val kind: String = "image",
    val briefMd: String = "",
    /** Written by the Claude agent in charge, never by the substitute. */
    val promptMd: String = "",
    /** telegram_post · telegram_story · instagram_post · instagram_story · banner · other */
    val placement: String = "other",
    /** 1:1 · 4:5 · 9:16 · 16:9 */
    val aspect: String = "1:1",
    /** Video only, ≤ 10. */
    val durationS: Int? = null,
    val overlay: Overlay? = null,
    /** The generated file with the overlay, composed by code. */
    val composed: FileRef? = null,
    val player: String = "gpt",
    val model: String = "",
    /** web · cli · api */
    val path: String = "web",
    /** queued · generating · review · accepted · rejected · failed */
    val state: String,
    val requestedBy: Actor,
    val workRef: String? = null,
    val errandRef: String? = null,
    val files: List<FileRef> = emptyList(),
    /** ⟨1.5.1⟩ a failed creative carries its reason here. */
    val reviewMd: String? = null,
    val source: CreativeSource? = null,
    val aiGenerated: Boolean = true,
    val createdAt: String = "",
    val updatedAt: String = "",
    val version: Int = 1,
) {
    val live: Boolean get() = state == "queued" || state == "generating"
}

/** ⟨1.5.1⟩ the aspect each placement sets. */
val PLACEMENT_ASPECT = linkedMapOf(
    "telegram_post" to "16:9", "telegram_story" to "9:16", "instagram_post" to "4:5", "instagram_story" to "9:16", "banner" to "16:9", "other" to "1:1",
)

/** The terminal commands of §21.13 (the owner's own terminal; nothing in the app runs them). */
val WEB_LOGIN_CMD = mapOf("gpt" to "make chatgpt-web-login", "gemini" to "make gemini-web-login", "deepseek" to "make deepseek-web-login")
val CLI_LOGIN_CMD = mapOf("gpt" to "make chatgpt-login", "gemini" to "make gemini-login")

// ------------------------------------------------------------ codes (§21.12, §14) --
private val CODE_FA_18 = mapOf(
    "decision_not_pending" to "این کارت دیگر منتظر تصمیم نیست؛ یادداشت فقط برای کارت منتظر نوشته میشود.",
    "not_ready" to "این کار روی این نسخه‌ی سرور هنوز آماده نیست.",
    "channel_not_configured" to "این بازیکن خارج شده یا خاموش است؛ جایگاهش رد میشود و کار با مدل خود Claude ادامه دارد.",
    "envelope_exceeded" to "تغییر مدل در پاکت ماهانه‌ی شرکت جا نمیشود؛ هیچ چیز عوض نشد.",
    "version_conflict" to "همین حالا عوض شده؛ دوباره نگاه کن و بعد ذخیره کن.",
    "policy_denied" to "سیاست این کار را اجازه نمیدهد.",
)

/** The Persian sentence for a failed §21 call: its stable codes in the app's words (a rate limit with how long to wait), the server's
 *  own sentence for the rest. */
fun mgmtError(e: ApiException): String {
    if (e.code == "rate_limited" && e.retryAfter != null) {
        val wait = if (e.retryAfter < 90) "${e.retryAfter} ثانیه‌ی" else "${(e.retryAfter + 59) / 60} دقیقه‌ی"
        return "${e.messageFa}؛ $wait دیگر."
    }
    return CODE_FA_18[e.code] ?: e.messageFa
}
