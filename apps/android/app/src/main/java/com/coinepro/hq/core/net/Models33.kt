package com.coinepro.hq.core.net

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// ----------------------------------------------------------------- v1.15 --
// Contract §33 (prompt 24): money and the Grok-like working style, in the shapes of `apps/api/openapi/hq-api.v1.json`. Usage in the
// advisor's words, crypto payments read and reconciled, the revenue board, a small CRM per company, the affiliate gaps, the money impact
// of a decision, agents in parallel, the workspace on a company's own server, the company journey, personas and the message test.
// Same rules as Models.kt: camelCase here, snake_case on the wire; a field the hub omits takes its default. Money the hub writes as a
// Decimal arrives as a string ("12.50"): [LenientNumber] reads it, and a plain number too.

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
/** `PayPaymentSource`: where a company's payments are read from: its own ledger (through its runner) or a public address on chain. */
@Serializable
data class PaySource(
    val id: String = "",
    val company: String = "",
    /** ledger · chain */
    val kind: String = "ledger",
    val adapter: String = "",
    /** bsc_usdt · trc20_usdt · null */
    val network: String? = null,
    /** A public address (never a key). */
    val address: String? = null,
    /** The company server whose runner reads the ledger (a ledger source only). */
    val server: String? = null,
    val enabled: Boolean = true,
    /** not_configured · ok · error */
    val state: String = "not_configured",
    val lastReadAt: String? = null,
    val lastErrorFa: String? = null,
)

/** `PayPaymentSourceIn`, the only fields `POST /companies/{code}/payment-sources` takes (the hub refuses any other key). */
@Serializable
data class PaySourceIn(
    val kind: String,
    val network: String? = null,
    val address: String? = null,
    val server: String? = null,
    val enabled: Boolean = true,
)

/** `PayReadResult` of «بخوان»: a ledger read is queued on the runner; a chain read says how many transfers it found. */
@Serializable
data class PayReadResult(
    val source: PaySource = PaySource(),
    val queued: Boolean = false,
    val payments: Int = 0,
    val transfers: Int = 0,
    val pages: Int = 0,
)

/** `PayPayment`: one payment as the ledger and the chain agree on it (or do not). */
@Serializable
data class PayRow(
    val id: String = "",
    val company: String = "",
    val source: String = "",
    val extId: String = "",
    /** A pseudonym, never a contact. */
    val customer: String? = null,
    val plan: String? = null,
    /** Null for a store's in-app billing (counted, not summed). */
    @Serializable(with = LenientNumber::class) val amountUsdt: Double? = null,
    /** What the chain shows for it, when it differs or there is no ledger row. */
    @Serializable(with = LenientNumber::class) val chainAmount: Double? = null,
    val network: String? = null,
    val txHash: String? = null,
    val paidAt: String = "",
    val periodStart: String? = null,
    val periodEnd: String? = null,
    /** matched · ledger_only · chain_only · amount_mismatch · pending_chain */
    val status: String = "matched",
    val noteFa: String? = null,
    val checkedAt: String? = null,
)

/** `PayReconcile`: one UTC day of the company's ledger against the chain. */
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
    val pendingChain: Int = 0,
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
    @Serializable(with = LenientNumber::class) val arpuUsdt: Double? = null,
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
    @Serializable(with = LenientNumber::class) val tokens: Double = 0.0,
    @Serializable(with = LenientNumber::class) val voice: Double = 0.0,
    @Serializable(with = LenientNumber::class) val ads: Double = 0.0,
    /** Null until the servers' cost is known. */
    @Serializable(with = LenientNumber::class) val servers: Double? = null,
) {
    val total: Double get() = tokens + voice + ads + (servers ?: 0.0)
}

@Serializable
data class RevRoi(
    @Serializable(with = LenientNumber::class) val revenueUsdt: Double = 0.0,
    val costUsd: RevCostUsd = RevCostUsd(),
    val ratio: Double? = null,
)

@Serializable
data class RevCostPer(
    /** line_run · deliverable · order */
    val kind: String = "",
    val count: Int = 0,
    @Serializable(with = LenientNumber::class) val usdEach: Double? = null,
)

/** `GET /revenue/board?company` (the holding when [company] is null). Every figure is computed by code from stored rows. */
@Serializable
data class RevenueBoard(
    val company: String? = null,
    val period: String = "month",
    val months: List<RevMonth> = emptyList(),
    val churnRate: Double? = null,
    @Serializable(with = LenientNumber::class) val ltvUsdt: Double? = null,
    @Serializable(with = LenientNumber::class) val cacUsdt: Double? = null,
    val paybackMonths: Double? = null,
    val cohorts: List<RevCohort> = emptyList(),
    val forecast: List<RevForecast> = emptyList(),
    val forecastBasisFa: String = "",
    val roi: RevRoi? = null,
    val costPerOutput: List<RevCostPer> = emptyList(),
)

/** `RevenueBySource`: a company's money of the period from the affiliate commission and from its customers' payments. */
@Serializable
data class RevBySource(
    val company: String = "",
    @Serializable(with = LenientNumber::class) val affiliateUsdt: Double = 0.0,
    @Serializable(with = LenientNumber::class) val paymentsUsdt: Double = 0.0,
    /** A store's in-app payments: counted, never summed. */
    val storePayments: Int = 0,
    @Serializable(with = LenientNumber::class) val totalUsdt: Double = 0.0,
)

/** `GET /revenue/summary` read for its additive `by_source` (§33.3); the radar's own fields stay with [RevenueSummary]. */
@Serializable
data class RevSummary33(
    val period: String = "month",
    val from: String = "",
    val to: String = "",
    @Serializable(with = LenientNumber::class) val totalUsdt: Double = 0.0,
    val bySource: List<RevBySource> = emptyList(),
)

// ---------------------------------------------------------------- §33.1 --
/** A row of `by_domain` (`domain`) or `by_company` (`company`). */
@Serializable
data class UsageShare(
    val domain: String = "",
    val company: String = "",
    val tokens: Long = 0,
    val usdEquiv: Double = 0.0,
    /** A fraction (0.42). */
    val share: Double = 0.0,
)

@Serializable
data class UsageRun(val ref: String = "", val role: String? = null, val tokens: Long = 0)

@Serializable
data class UsageLines(val runs: Int = 0, val tokens: Long = 0)

@Serializable
data class UsageVsPrev(val tokensPct: Double? = null, val usdPct: Double? = null)

/** tech_domain_largest · spike · voice_high · failed_calls */
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
    val voiceUsd: Double = 0.0,
    val lines: UsageLines = UsageLines(),
    val adsSpendUsd: Double = 0.0,
    val vsPrev: UsageVsPrev = UsageVsPrev(),
    val anomalies: List<UsageAnomaly> = emptyList(),
)

@Serializable
data class UsageText(val linesFa: List<String> = emptyList(), val savingFa: String = "")

/** `GET /usage/reports`: the advisor's words over a pack of figures (no words yet: [text] null). */
@Serializable
data class UsageReport(
    val ref: String = "",
    /** day · week */
    val period: String = "day",
    val from: String = "",
    val to: String = "",
    val pack: UsagePack = UsagePack(),
    val text: UsageText? = null,
    /** model · code: who wrote the words (code when the model could not). */
    val words: String? = null,
    val at: String = "",
)

// ------------------------------------------------------------ §33.4, 5 --
@Serializable
data class LeadEvent(val at: String = "", val kind: String = "", val noteFa: String = "")

/** `Lead`, one person in a company's small CRM: a pseudonym and a display name only; the contact stays in the company's systems. */
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
    val version: Int = 1,
)

/** `LeadIn`: a lead by hand. Only these keys; a null one is left out of the body. */
@Serializable
data class LeadIn(
    val source: String = "manual",
    val nameFa: String? = null,
    val contact: String? = null,
    val valueUsdt: String? = null,
    val nextAt: String? = null,
    val nextFa: String? = null,
    val noteFa: String? = null,
)

/** `LeadDraft`: the follow-up text, checked by the outbound guard and never sent (`sent` is always false). */
@Serializable
data class LeadDraft(
    val lead: String = "",
    val draftFa: String = "",
    val guardOk: Boolean = true,
    val blockedReasons: List<String> = emptyList(),
    val sent: Boolean = false,
)

/** `LeadPipelineStage`; [kind] open · won · lost. */
@Serializable
data class PipeStage(
    val stage: String = "",
    val titleFa: String = "",
    val kind: String = "open",
    val count: Int = 0,
    @Serializable(with = LenientNumber::class) val valueUsdt: Double = 0.0,
    val medianDays: Double? = null,
)

/** `GET /companies/{code}/pipeline`: counts and value by stage, the win rate, the median days in each open stage. */
@Serializable
data class SalesPipeline(
    val company: String = "",
    val stages: List<PipeStage> = emptyList(),
    val winRate: Double? = null,
    val openCount: Int = 0,
    val wonCount: Int = 0,
    val lostCount: Int = 0,
    @Serializable(with = LenientNumber::class) val openValueUsdt: Double = 0.0,
    val total: Int = 0,
)

/** `SalesAffiliateGap`: one account-month of the commission due against the commission received (§33.5). */
@Serializable
data class AffiliateGap(
    val company: String = "",
    val account: String = "",
    val exchange: String = "",
    val month: String = "",
    @Serializable(with = LenientNumber::class) val dueUsdt: Double = 0.0,
    @Serializable(with = LenientNumber::class) val receivedUsdt: Double = 0.0,
    @Serializable(with = LenientNumber::class) val gapUsdt: Double = 0.0,
    val gapPct: Double = 0.0,
    /** The exchange's settlement day: before it the month is still `waiting`. */
    val settlesOn: String = "",
    /** waiting · ok · open · closed */
    val state: String = "waiting",
    val draftFa: String? = null,
    /** The FIN manager's follow-up work. */
    val workRef: String? = null,
)

// ---------------------------------------------------------------- §33.6 --
/** A decision's money impact: measured by code where the inputs exist, otherwise an estimate with its basis. */
@Serializable
data class DecisionImpact(
    val revenueUsdt: Double? = null,
    val costUsd: Double? = null,
    val horizonDays: Int = 30,
    val basisFa: String = "",
    /** measured · estimate */
    val kind: String = "estimate",
)

// ---------------------------------------------------------------- §33.7 --
/** `SplitPart`: one independent part of a split work. */
@Serializable
data class SplitPart(
    val n: Int = 0,
    val ref: String = "",
    val titleFa: String = "",
    val role: String = "",
    val assignee: String? = null,
    val whoFa: String? = null,
    /** working · delivered · failed */
    val state: String = "working",
    /** The part's work status as the hub keeps it. */
    val status: String = "",
    val progressPct: Int? = null,
    val outputRef: String? = null,
    val outputTitleFa: String? = null,
    val failedFa: String? = null,
    val budgetTokens: Long? = null,
    val tokensUsed: Long = 0,
)

/** `WorkSplit`: a work's parallel parts side by side, then the one merge (the order report's additive `parts`). */
@Serializable
data class WorkSplit(
    val workRef: String = "",
    /** running · merging · done · failed · cancelled */
    val state: String = "running",
    val proposedBy: String = "",
    val createdAt: String = "",
    val mergeQueuedAt: String? = null,
    val parts: List<SplitPart> = emptyList(),
)

// --------------------------------------------------------------- §33.10 --
/** `WorkspaceProgress`: a work done in its own folder on its company's server (the order report's additive `workspaces`). */
@Serializable
data class WorkspaceProgress(
    val workRef: String = "",
    val server: String = "",
    val path: String = "",
    /** starting · working · awaiting_seal · idle · delivered · stopped · failed */
    val state: String = "starting",
    val turns: Int = 0,
    val lastStepFa: String? = null,
    val noteFa: String? = null,
    /** Where it runs, in the owner's words (the company's name and its server). */
    val whereFa: String = "",
    val sessionRef: String? = null,
    val updatedAt: String = "",
    val closedAt: String? = null,
    val removeAfter: String? = null,
)

/** `WorkStopped`: the answer of `POST /work/{id}/stop`. */
@Serializable
data class WorkStopped(val workRef: String = "", val jobsStopped: Int = 0, val workspace: String? = null)

// ---------------------------------------------------------------- §33.8 --
@Serializable
data class JourneyEvidence(val kind: String = "", val ref: String? = null)

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
    val daysInStage: Int = 0,
)

/** A stage a company reached, on the all-companies timeline. */
@Serializable
data class JourneyEvent(val at: String = "", val company: String = "", val stage: String = "", val titleFa: String = "")

/** `GET /journeys`: every company's journey, and every reached stage on one timeline, newest first. */
@Serializable
data class JourneyBoard(val journeys: List<Journey> = emptyList(), val timeline: List<JourneyEvent> = emptyList())

// ---------------------------------------------------------------- §33.9 --
/** `PersonaRecord`. */
@Serializable
data class SalesPersona(
    val id: String = "",
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

/** `PersonaIn` (POST) and, without [source], `PersonaPatch` (PATCH): the only keys the hub takes. */
@Serializable
data class PersonaIn(
    val nameFa: String,
    val summaryFa: String,
    val painsFa: List<String> = emptyList(),
    val objectionsFa: List<String> = emptyList(),
    val channelFa: String = "",
    val source: String? = null,
)

/** `PersonaDraft`: a persona the knowledge base suggests; nothing is saved until the owner keeps it. */
@Serializable
data class PersonaDraft(
    val nameFa: String = "",
    val summaryFa: String = "",
    val painsFa: List<String> = emptyList(),
    val objectionsFa: List<String> = emptyList(),
    val channelFa: String = "",
)

@Serializable
data class PersonaSuggestion(val company: String = "", val basisFa: String = "", val personas: List<PersonaDraft> = emptyList())

@Serializable
data class PersonaScore(
    /** The persona's id. */
    val persona: String = "",
    val nameFa: String = "",
    val score: Int = 0,
    val wouldAct: Boolean = false,
    val objectionFa: String? = null,
    val fixFa: String? = null,
)

@Serializable
data class PersonaTest(
    val id: String = "",
    val text: String = "",
    val results: List<PersonaScore> = emptyList(),
    val average: Int = 0,
    val lowest: Int = 0,
    val at: String = "",
)
