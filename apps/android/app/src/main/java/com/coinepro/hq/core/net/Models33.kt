package com.coinepro.hq.core.net

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// ----------------------------------------------------------------- v1.15 --
// Contract §33 (prompt 24): money and the Grok-like working style. Usage in the advisor's words, crypto payments read and reconciled, the
// revenue board, a small CRM per company, the affiliate gaps, the money impact of a decision, agents in parallel, the company journey,
// personas and the message test. Same rules as Models.kt: camelCase here, snake_case on the wire; a field the hub omits takes its default.
// A figure the hub may write as a number or as a decimal string (a Decimal) is read by [LenientNumber]; an id as a [JsonPrimitive].

/** A number the hub sends as `12.5` or `"12.50"`; anything else reads as 0 (a nullable field stays null when the hub sends null). */
object LenientNumber : KSerializer<Double> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("LenientNumber", PrimitiveKind.DOUBLE)
    override fun deserialize(decoder: Decoder): Double {
        val e = (decoder as? JsonDecoder)?.decodeJsonElement()
        return (e as? JsonPrimitive)?.contentOrNull?.trim()?.toDoubleOrNull() ?: 0.0
    }
    override fun serialize(encoder: Encoder, value: Double) = encoder.encodeDouble(value)
}

// ---------------------------------------------------------------- §33.2 --
/** A place payments are read from: the company's own ledger (through its runner) or the public chain. */
@Serializable
data class PaySource(
    val id: JsonPrimitive = JsonPrimitive(""),
    val company: String = "",
    /** ledger · chain */
    val kind: String = "ledger",
    val adapter: String = "",
    /** bsc_usdt · trc20_usdt · null */
    val network: String? = null,
    /** A public address (never a key). */
    val address: String? = null,
    /** not_configured · ok · error */
    val state: String = "not_configured",
    val lastReadAt: String? = null,
    val lastErrorFa: String? = null,
)

@Serializable
data class PayRow(
    val id: JsonPrimitive = JsonPrimitive(""),
    val company: String = "",
    val source: JsonPrimitive? = null,
    val extId: String = "",
    /** A pseudonym, never a contact. */
    val customer: String = "",
    val plan: String? = null,
    /** Null for a store's in-app billing (counted, not summed). */
    @Serializable(with = LenientNumber::class) val amountUsdt: Double? = null,
    val network: String? = null,
    val txHash: String? = null,
    val paidAt: String = "",
    val periodStart: String? = null,
    val periodEnd: String? = null,
    /** matched · ledger_only · chain_only · amount_mismatch · pending_chain */
    val status: String = "matched",
    val checkedAt: String? = null,
)

@Serializable
data class PayReconcile(
    val company: String = "",
    val day: String = "",
    val ledgerCount: Int = 0,
    val chainCount: Int = 0,
    val matched: Int = 0,
    val ledgerOnly: Int = 0,
    val chainOnly: Int = 0,
    val amountMismatch: Int = 0,
    val noteFa: String = "",
)

// ---------------------------------------------------------------- §33.3 --
@Serializable
data class RevMonth(
    val month: String = "",
    @Serializable(with = LenientNumber::class) val mrrUsdt: Double = 0.0,
    val newCustomers: Int = 0,
    val churned: Int = 0,
    val active: Int = 0,
    @Serializable(with = LenientNumber::class) val arpuUsdt: Double = 0.0,
)

@Serializable
data class RevCohort(val startMonth: String = "", val size: Int = 0, val retained: List<@Serializable(with = LenientNumber::class) Double> = emptyList())

@Serializable
data class RevForecast(
    val month: String = "",
    @Serializable(with = LenientNumber::class) val mrrUsdt: Double = 0.0,
    @Serializable(with = LenientNumber::class) val low: Double = 0.0,
    @Serializable(with = LenientNumber::class) val high: Double = 0.0,
)

@Serializable
data class RevCostUsd(
    @Serializable(with = LenientNumber::class) val tokens: Double? = null,
    @Serializable(with = LenientNumber::class) val voice: Double? = null,
    @Serializable(with = LenientNumber::class) val ads: Double? = null,
    @Serializable(with = LenientNumber::class) val servers: Double? = null,
) {
    val total: Double get() = (tokens ?: 0.0) + (voice ?: 0.0) + (ads ?: 0.0) + (servers ?: 0.0)
}

@Serializable
data class RevRoi(
    @Serializable(with = LenientNumber::class) val revenueUsdt: Double = 0.0,
    val costUsd: RevCostUsd = RevCostUsd(),
    @Serializable(with = LenientNumber::class) val ratio: Double? = null,
)

@Serializable
data class RevCostPer(
    /** line_run · deliverable · order */
    val kind: String = "",
    val count: Int = 0,
    @Serializable(with = LenientNumber::class) val usdEach: Double = 0.0,
)

/** `GET /revenue/board?company` (the holding when [company] is null). Every figure is computed by code from stored rows. */
@Serializable
data class RevenueBoard(
    val company: String? = null,
    val period: String = "month",
    val months: List<RevMonth> = emptyList(),
    @Serializable(with = LenientNumber::class) val churnRate: Double? = null,
    @Serializable(with = LenientNumber::class) val ltvUsdt: Double? = null,
    @Serializable(with = LenientNumber::class) val cacUsdt: Double? = null,
    @Serializable(with = LenientNumber::class) val paybackMonths: Double? = null,
    val cohorts: List<RevCohort> = emptyList(),
    val forecast: List<RevForecast> = emptyList(),
    val forecastBasisFa: String? = null,
    val roi: RevRoi? = null,
    val costPerOutput: List<RevCostPer> = emptyList(),
)

/** `GET /revenue/summary` read for its additive `by_source` (§33.3); the radar's own fields stay with [RevenueSummary]. */
@Serializable
data class RevSummary33(
    val period: String = "month",
    val from: String = "",
    val to: String = "",
    @Serializable(with = LenientNumber::class) val totalUsdt: Double? = null,
    val bySource: JsonElement? = null,
)

/** One company's money from one source (the affiliate commission, the customers' payments). */
data class SourceRow(val company: String?, val source: String, val usdt: Double)

/**
 * `by_source` as the app reads it. The contract names the field only ("summed per company"), so three shapes are taken: a list of
 * `{company, source, total_usdt}`, a map company → {source → amount}, and a map source → amount (no company).
 */
fun parseBySource(e: JsonElement?): List<SourceRow> {
    fun num(p: JsonElement?): Double? = (p as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()
    return when (e) {
        is JsonArray -> e.mapNotNull { x ->
            val o = x as? JsonObject ?: return@mapNotNull null
            val src = (o["source"] as? JsonPrimitive)?.contentOrNull ?: return@mapNotNull null
            val v = num(o["total_usdt"]) ?: num(o["usdt"]) ?: num(o["amount_usdt"]) ?: num(o["amount"]) ?: return@mapNotNull null
            SourceRow((o["company"] as? JsonPrimitive)?.contentOrNull, src, v)
        }
        is JsonObject -> e.entries.flatMap { (k, v) ->
            when (v) {
                is JsonObject -> v.entries.mapNotNull { (s, a) -> num(a)?.let { SourceRow(k, s, it) } }
                else -> listOfNotNull(num(v)?.let { SourceRow(null, k, it) })
            }
        }
        else -> emptyList()
    }
}

// ---------------------------------------------------------------- §33.1 --
@Serializable
data class UsageShare(
    val domain: String = "",
    val company: String = "",
    @Serializable(with = LenientNumber::class) val tokens: Double = 0.0,
    @Serializable(with = LenientNumber::class) val usdEquiv: Double = 0.0,
    @Serializable(with = LenientNumber::class) val share: Double = 0.0,
)

@Serializable
data class UsageRun(val ref: String = "", val role: String = "", @Serializable(with = LenientNumber::class) val tokens: Double = 0.0)

@Serializable
data class UsageLines(val runs: Int = 0, @Serializable(with = LenientNumber::class) val tokens: Double = 0.0)

@Serializable
data class UsageVsPrev(
    @Serializable(with = LenientNumber::class) val tokensPct: Double? = null,
    @Serializable(with = LenientNumber::class) val usdPct: Double? = null,
)

@Serializable
data class UsageAnomaly(val kind: String = "", val note: String = "")

@Serializable
data class UsagePack(
    val period: String = "day",
    val from: String = "",
    val to: String = "",
    val byDomain: List<UsageShare> = emptyList(),
    val byCompany: List<UsageShare> = emptyList(),
    val topRuns: List<UsageRun> = emptyList(),
    @Serializable(with = LenientNumber::class) val voiceUsd: Double? = null,
    val lines: UsageLines? = null,
    @Serializable(with = LenientNumber::class) val adsSpendUsd: Double? = null,
    val vsPrev: UsageVsPrev? = null,
    val anomalies: List<UsageAnomaly> = emptyList(),
)

@Serializable
data class UsageText(val linesFa: List<String> = emptyList(), val savingFa: String = "")

/** `GET /usage/reports`: the advisor's words over a pack of figures. */
@Serializable
data class UsageReport(
    val ref: String = "",
    /** day · week */
    val period: String = "day",
    val from: String = "",
    val to: String = "",
    val pack: UsagePack = UsagePack(),
    val text: UsageText = UsageText(),
    val at: String = "",
)

// ------------------------------------------------------------ §33.4, 5 --
@Serializable
data class LeadEvent(val at: String = "", val kind: String = "", val noteFa: String = "")

@Serializable
data class SalesLead(
    val ref: String = "",
    val company: String = "",
    /** support · telegram · site · payment · referral · manual */
    val source: String = "manual",
    val nameFa: String? = null,
    /** A pseudonym. */
    val contact: String = "",
    val stage: String = "new",
    @Serializable(with = LenientNumber::class) val valueUsdt: Double? = null,
    val nextAt: String? = null,
    val nextFa: String? = null,
    val assignee: Actor? = null,
    val lostReasonFa: String? = null,
    val events: List<LeadEvent> = emptyList(),
    val createdAt: String = "",
    val updatedAt: String = "",
)

@Serializable
data class PipeStage(
    val key: String = "",
    val titleFa: String? = null,
    val count: Int = 0,
    @Serializable(with = LenientNumber::class) val valueUsdt: Double? = null,
    @Serializable(with = LenientNumber::class) val medianDays: Double? = null,
)

/** `GET /companies/{code}/pipeline`: counts and value by stage, the win rate, the median days in each stage. */
@Serializable
data class SalesPipeline(
    val company: String = "",
    val stages: List<PipeStage> = emptyList(),
    @Serializable(with = LenientNumber::class) val winRate: Double? = null,
)

/** `POST /leads/{ref}/draft`: the drafted follow-up (never sent). The text sits under one of a few keys; [text] takes the first. */
@Serializable
data class LeadDraft(
    val draftFa: String? = null,
    val textFa: String? = null,
    val messageFa: String? = null,
    val bodyFa: String? = null,
    val draft: String? = null,
    val text: String? = null,
) {
    val body: String get() = listOf(draftFa, textFa, messageFa, bodyFa, draft, text).firstOrNull { !it.isNullOrBlank() }.orEmpty()
}

/** One account-month where the commission due and the commission received differ (§33.5). */
@Serializable
data class AffiliateGap(
    val company: String = "",
    val account: String? = null,
    val exchange: String? = null,
    val month: String = "",
    @Serializable(with = LenientNumber::class) val dueUsdt: Double = 0.0,
    @Serializable(with = LenientNumber::class) val receivedUsdt: Double = 0.0,
    @Serializable(with = LenientNumber::class) val gapPct: Double? = null,
    /** open · followup · paid */
    val state: String = "open",
    val noteFa: String? = null,
)

// ---------------------------------------------------------------- §33.6 --
/** A decision's money impact: measured by code where the inputs exist, otherwise an estimate with its basis. */
@Serializable
data class DecisionImpact(
    @Serializable(with = LenientNumber::class) val revenueUsdt: Double? = null,
    @Serializable(with = LenientNumber::class) val costUsd: Double? = null,
    val horizonDays: Int = 30,
    val basisFa: String = "",
    /** measured · estimate */
    val kind: String = "estimate",
)

// ---------------------------------------------------------------- §33.7 --
@Serializable
data class ReportPart(
    val ref: String = "",
    val titleFa: String = "",
    val role: String? = null,
    val company: String? = null,
    /** queued · working · waiting · done · failed */
    val state: String = "queued",
    @Serializable(with = LenientNumber::class) val progressPct: Double? = null,
    val deliverable: ReportOutput? = null,
    val noteFa: String? = null,
)

/** The short meeting: the parent's assignee merges the parts' deliverables. */
@Serializable
data class ReportMerge(
    /** waiting · working · done · failed */
    val state: String = "waiting",
    val noteFa: String? = null,
    val deliverable: ReportOutput? = null,
)

/** §33.10: the persistent folder a work does its job in on its company's own server. */
@Serializable
data class ReportWorkspace(
    val state: String? = null,
    @Serializable(with = LenientNumber::class) val progressPct: Double? = null,
    val noteFa: String? = null,
    val server: String? = null,
    val folder: String? = null,
)

// ---------------------------------------------------------------- §33.8 --
@Serializable
data class JourneyEvidence(val kind: String = "", val ref: String = "")

@Serializable
data class JourneyStage(
    val key: String = "",
    val titleFa: String = "",
    val reachedAt: String? = null,
    val evidence: JourneyEvidence? = null,
)

@Serializable
data class Journey(
    val company: String = "",
    val stages: List<JourneyStage> = emptyList(),
    val current: String = "",
    val nextFa: String? = null,
    val daysInStage: Int? = null,
)

// ---------------------------------------------------------------- §33.9 --
@Serializable
data class SalesPersona(
    val id: JsonPrimitive = JsonPrimitive(""),
    val company: String = "",
    val nameFa: String = "",
    val summaryFa: String = "",
    val painsFa: List<String> = emptyList(),
    val objectionsFa: List<String> = emptyList(),
    val channelFa: String = "",
    /** owner · kb_suggested */
    val source: String = "owner",
    val version: Int = 1,
)

@Serializable
data class PersonaScore(
    /** The persona's id (or its name). */
    val persona: JsonPrimitive = JsonPrimitive(""),
    @Serializable(with = LenientNumber::class) val score: Double = 0.0,
    val wouldAct: Boolean = false,
    val objectionFa: String? = null,
    val fixFa: String? = null,
)

@Serializable
data class PersonaTest(val text: String = "", val results: List<PersonaScore> = emptyList(), val at: String = "")
