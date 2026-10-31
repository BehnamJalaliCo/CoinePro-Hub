package com.coinepro.hq.core.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

// ------------------------------------------------------------------ v1.5 --
// Contract §20 (prompt 11): governance. The meeting room run by code, the versioned charter and company addenda, the four-layer
// knowledge base, the three cards and the live scorecard, OKRs, decision outcome reviews at 30/60/90 days, the authority matrix,
// the risk register, the change calendar and the batch seal; §20.12 ⟨1.5.1⟩ fixes the shapes the apps read. Same rules as
// Models.kt: camelCase here, snake_case on the wire, nullable exactly where §20 writes `|null`. Tokens are whole numbers, money a
// decimal string (§1), rates 0..1. Companies are data: nothing here counts them.

/** A source or evidence: `{kind, ref, note}` (§20.1, §20.3, §20.4, §20.5). */
@Serializable
data class Source(val kind: String = "", val ref: String = "", val note: String = "")

// ------------------------------------------------------------- meetings (§20.1) --
@Serializable
data class MeetingMembers(val roles: List<String> = emptyList(), val companies: String = "all")

@Serializable
data class MeetingType(
    /** board · company · standup · war_room · postmortem · strategy */
    val key: String,
    val titleFa: String,
    /** RRULE in the owner's zone; null = opened by an event (war_room, postmortem). */
    val schedule: String? = null,
    val members: MeetingMembers = MeetingMembers(),
    /** 1..3 */
    val maxRounds: Int = 2,
    /** 2..8, per agenda item. */
    val maxSpeakers: Int = 6,
    /** null = no meeting cap (war_room only). Sent as an explicit null. */
    val budgetTokens: Long? = null,
    val turnCapTokens: Long = 6000,
    /** live · summary · audio */
    val ownerPresence: String = "summary",
    val enabled: Boolean = true,
    val version: Int = 1,
)

@Serializable
data class MeetingItem(
    val id: String,
    val n: Int,
    val titleFa: String,
    val briefMd: String = "",
    val sources: List<Source> = emptyList(),
    val timeBoxMin: Int = 10,
    val speakers: List<Actor> = emptyList(),
    /** 0..3 */
    val round: Int = 0,
    /** waiting · round_1 · round_2 · done · skipped */
    val state: String = "waiting",
) {
    val current: Boolean get() = state == "round_1" || state == "round_2"
}

@Serializable
data class Participant(val actor: Actor, val roleFa: String = "", val speaker: Boolean = true, val devil: Boolean = false)

@Serializable
data class Votes(val support: Int = 0, val oppose: Int = 0, val abstain: Int = 0) {
    val total: Int get() = support + oppose + abstain
}

/** A draft resolution (§20.12: read from `GET /meetings/{ref}`); [decision] is its `meeting_resolution` card once the meeting closes. */
@Serializable
data class Draft(val id: String, val meeting: String = "", val item: String = "", val textMd: String = "", val proposer: Actor? = null, val votes: Votes = Votes(), val decision: String? = null)

/** ⟨1.5.1⟩ [cap] null: a war room has no meeting cap. */
@Serializable
data class MeetingBudget(val cap: Long? = null, val estimate: Long = 0, val reserved: Long = 0, val used: Long = 0)

@Serializable
/** The minutes' deliverable is null until the secretary has written them. */
data class Minutes(val deliverable: String? = null, val summaryMd: String? = null)

@Serializable
data class Meeting(
    val id: String = "",
    val ref: String,
    val type: String,
    /** The holding's code for board and strategy. */
    val company: String,
    val titleFa: String,
    val startsAt: String,
    /** scheduled · prep · live · closing · ended · cancelled */
    val state: String,
    /** discussion · written (not enough of the daily share left: statements only) */
    val mode: String = "discussion",
    val budget: MeetingBudget = MeetingBudget(),
    val trimmedFa: String? = null,
    val items: List<MeetingItem> = emptyList(),
    val participants: List<Participant> = emptyList(),
    val ownerPresence: String = "summary",
    val minutes: Minutes? = null,
    /** The incident (I-…) a war room or post-mortem belongs to. */
    val incident: String? = null,
    val version: Int = 1,
    val createdAt: String = "",
    val drafts: List<Draft> = emptyList(),
) {
    val live: Boolean get() = state == "live" || state == "closing"
    val before: Boolean get() = state == "scheduled" || state == "prep"
    val sortedItems: List<MeetingItem> get() = items.sortedBy { it.n }
    val currentItem: MeetingItem? get() = sortedItems.firstOrNull { it.current }
}

@Serializable
data class ClaimSource(val kind: String = "", val ref: String = "")

@Serializable
data class Claim(
    val id: String,
    val textFa: String,
    val source: ClaimSource? = null,
    /** sourced · unsourced · challenged · withdrawn */
    val status: String = "unsourced",
)

@Serializable
data class Stance(val draft: String = "", val vote: String = "abstain", val reasonFa: String = "")

@Serializable
data class Turn(
    val id: String,
    val meeting: String = "",
    val item: String? = null,
    val n: Int = 0,
    val round: Int = 1,
    val speaker: Actor,
    /** statement · challenge · vote · owner */
    val kind: String = "statement",
    val statementMd: String = "",
    val claims: List<Claim> = emptyList(),
    val draftMd: String? = null,
    val stance: Stance? = null,
    val runId: String? = null,
    val tokens: Long = 0,
    val at: String,
)

/** The advisor's; the owner's only. */
@Serializable
data class Whisper(val id: String, val meeting: String = "", val item: String = "", val textMd: String = "", val sources: List<Source> = emptyList(), val at: String = "")

/** ⟨1.5.1⟩ `GET /meetings/{ref}/turns`: the owner's page also carries the whispers. */
@Serializable
data class TurnsPage(val items: List<Turn> = emptyList(), val whispers: List<Whisper> = emptyList(), val nextCursor: String? = null)

/** One agenda item of `POST /meetings`: the hub's `MeetingOwnerItemIn` takes the title (and a brief, sources and companies), no time
 *  box; the hub sets each item's time itself. */
@Serializable
data class MeetingItemIn(val titleFa: String)

/** One row of `PATCH /meetings/{ref}`: the items in their new order, each may be skipped. */
@Serializable
data class ItemOrder(val id: String, val n: Int, val skip: Boolean)

// ------------------------------------------------------- charter (§20.2) --
@Serializable
data class RedLine(
    val key: String = "",
    val textFa: String = "",
    /** rule (code matches) · sample (the overseer samples) */
    val check: String = "sample",
    /** Sent as an explicit null for a sampled line. */
    val patterns: List<String>? = null,
)

@Serializable
data class Charter(
    /** "holding" or a company code. */
    val scope: String,
    val version: Int,
    /** proposed · sealed · superseded */
    val status: String,
    val bodyMd: String = "",
    val redLines: List<RedLine> = emptyList(),
    /** ⟨1.5.1⟩ the seal's target, as the server sends it; the client never recomputes it. */
    val bodySha256: String = "",
    val createdBy: Actor? = null,
    val createdAt: String = "",
    val sealedBy: Actor? = null,
    val sealedAt: String? = null,
)

@Serializable
data class CharterVersionRef(val version: Int, val status: String, val createdBy: Actor? = null, val createdAt: String = "", val sealedAt: String? = null)

/** ⟨1.5.1⟩ One scope of `GET /charter`: its sealed version, a proposed one waiting for the seal, the version list. */
@Serializable
data class CharterScope(val scope: String, val sealed: Charter? = null, val proposed: Charter? = null, val versions: List<CharterVersionRef> = emptyList())

@Serializable
data class CharterDiff(val scope: String = "", val version: Int = 0, val against: Int = 0, val diff: String = "")

/** `PUT /charter/{scope}`: a new proposed version. */
@Serializable
data class CharterIn(val bodyMd: String, val redLines: List<RedLine>)

/** Holding ≤ 6000 characters, an addendum ≤ 3000: the sealed text is read in every run. */
fun charterMax(scope: String): Int = if (scope == "holding") 6000 else 3000

// ----------------------------------------------------- knowledge (§20.3) --
@Serializable
data class KnowledgeReview(
    val by: Actor? = null,
    val at: String = "",
    /** pass · changes · reject */
    val verdict: String,
    /** ⟨1.5.1⟩ true = passed: injection, secrets, conflicts, policy. */
    val checks: Map<String, Boolean> = emptyMap(),
    val notesMd: String = "",
)

@Serializable
data class KnowledgeEntry(
    val id: String = "",
    /** K-…; support articles keep their KB- refs in this view. */
    val ref: String,
    /** holding · company · department · employee */
    val layer: String,
    val company: String,
    val department: String? = null,
    /** principle · policy · fact · faq · playbook · support */
    val kind: String,
    val titleFa: String,
    val bodyMd: String = "",
    val sources: List<Source> = emptyList(),
    /** A date (yyyy-mm-dd). */
    val validUntil: String = "",
    /** draft · in_review · approved · expired · retired */
    val status: String,
    val review: KnowledgeReview? = null,
    val approvedBy: Actor? = null,
    val version: Int = 1,
    val createdBy: Actor? = null,
    val createdAt: String = "",
    val updatedAt: String = "",
) {
    /** The employee layer is the employee's own memory and support articles are edited at /support/kb: both read-only here. */
    val readOnly: Boolean get() = layer == "employee" || kind == "support"
}

/** ⟨1.5.1⟩ create and update body; [department] only on the department layer. What the owner writes is approved by that act. */
@Serializable
data class KnowledgeIn(
    val layer: String,
    val company: String,
    val department: String? = null,
    val kind: String,
    val titleFa: String,
    val bodyMd: String,
    val sources: List<Source>,
    val validUntil: String,
)

/** Longest validity by kind, in days (support articles follow §19). */
val VALID_DAYS = linkedMapOf("principle" to 730, "policy" to 365, "fact" to 90, "faq" to 180, "playbook" to 365)

// ----------------------------------------- the three cards and the scorecard (§20.4) --
@Serializable
data class KpiSource(val kind: String = "manual", val query: String? = null)

/** A KPI's definition (§20.4; [Kpi] is §18's charter KPI). */
@Serializable
data class KpiDef(
    val id: String = "",
    val company: String,
    val key: String,
    /** stability · growth · safety_cost */
    val card: String,
    val nameFa: String,
    val unit: String = "",
    /** up · down (⟨1.5.1⟩ range) */
    val direction: String = "up",
    val source: KpiSource = KpiSource(),
    val freshnessHours: Int = 24,
    val target: Double? = null,
    val scorecard: Boolean = false,
    val aggregate: String = "sum",
    /** active · paused */
    val status: String = "active",
    val version: Int = 1,
)

@Serializable
data class KpiValue(val kpi: String = "", val at: String, val value: Double, val sourceRef: Source = Source())

/** One KPI of a card. A day with no value is null in [trend], never zero; a KPI without a source has no [value]. */
@Serializable
data class CardKpi(
    val key: String,
    val nameFa: String,
    val unit: String = "",
    val value: Double? = null,
    val at: String? = null,
    val sourceRef: Source? = null,
    val target: Double? = null,
    val trend: List<Double?> = emptyList(),
    /** ok · stale · no_source */
    val state: String = "ok",
    /** ⟨1.5.1⟩ scorecard rows carry both. */
    val card: String? = null,
    val direction: String? = null,
)

@Serializable
data class KpiCard(val company: String, val card: String, val kpis: List<CardKpi> = emptyList(), val direction: String? = null)

/** ⟨1.5.1⟩ one row of the scorecard. */
@Serializable
data class ScorecardRow(val company: String, val kpis: List<CardKpi> = emptyList())

/** ⟨1.5.1⟩ `GET /kpis/{company}`: the definitions and the version a PUT matches with If-Match. */
@Serializable
data class KpiSet(val company: String, val version: Int = 1, val kpis: List<KpiDef> = emptyList())

/** One row of `PUT /kpis/{company}`; a cleared target is sent as an explicit null. */
@Serializable
data class KpiPatch(val key: String, val target: Double?, val scorecard: Boolean, val status: String, val freshnessHours: Int)

// ----------------------------------------------------------------- OKR (§20.5) --
@Serializable
data class Checkin(val at: String, val by: Actor? = null, val confidence: Double = 0.0, val noteMd: String = "", val evidence: List<Source> = emptyList())

@Serializable
data class KeyResult(
    val id: String = "",
    val ref: String,
    val objective: String = "",
    val titleFa: String,
    val kpi: String? = null,
    val metricFa: String? = null,
    val start: Double = 0.0,
    val target: Double = 0.0,
    val current: Double? = null,
    /** 0..1 */
    val progress: Double = 0.0,
    /** 0..1 */
    val confidence: Double = 0.0,
    val weight: Double = 1.0,
    val checkins: List<Checkin> = emptyList(),
)

@Serializable
data class Objective(
    val id: String = "",
    val ref: String,
    val company: String,
    /** Jalali, "1405-Q3". */
    val quarter: String,
    val titleFa: String,
    val whyMd: String = "",
    val owner: Actor? = null,
    /** draft · proposed · active · closed */
    val status: String,
    val decision: String? = null,
    val keyResults: List<KeyResult> = emptyList(),
) {
    /** Weighted progress, 0..1. */
    val progress: Double get() = keyResults.sumOf { it.weight }.let { w -> if (w > 0) keyResults.sumOf { it.progress * it.weight } / w else 0.0 }
}

// --------------------------------------------- decision outcomes (§20.6) --
@Serializable
data class Expected(val metricFa: String = "", val kpi: String? = null, val baseline: Double = 0.0, val target: Double = 0.0, val byDays: Int = 30)

@Serializable
data class Measured(val value: Double = 0.0, val at: String = "", val sourceRef: Source? = null)

@Serializable
data class OutcomeReview(
    val id: String = "",
    val ref: String,
    val decision: String,
    val company: String,
    /** 30 · 60 · 90 */
    val day: Int,
    val dueAt: String,
    val expected: Expected,
    val measured: Measured? = null,
    /** pending · met · partly · missed · unmeasurable */
    val verdict: String = "pending",
    val proposer: Actor,
    val proposerNoteMd: String? = null,
    val overseerNoteMd: String? = null,
    /** due · answered · verified */
    val status: String = "due",
)

/** Prediction accuracy (§1.16) from the verdicts: met 1, partly ½, missed 0; pending and unmeasurable are not counted. */
fun accuracy(rs: List<OutcomeReview>): Double? {
    val scored = rs.filter { it.verdict in setOf("met", "partly", "missed") }
    return if (scored.isEmpty()) null else scored.sumOf { if (it.verdict == "met") 1.0 else if (it.verdict == "partly") 0.5 else 0.0 } / scored.size
}

// ------------------------------------------------------ authority (§20.7) --
@Serializable
data class Bounds(val min: Double = 0.0, val max: Double = 0.0)

@Serializable
data class AuthorityRule(
    val key: String,
    val titleFa: String,
    val action: String = "",
    /** A role or a kind ("ceo", "agent", "owner", "*"). */
    val actor: String = "",
    /** own_company · holding */
    val scope: String = "own_company",
    /** `{tokens_month?, usd?, count_day?, count_hour?, days?, items?}`, kept as the server sent it so a change touches one number. */
    val limit: JsonObject? = null,
    val bounds: Bounds? = null,
    val stepUp: Boolean = false,
    @SerialName("class") val actionClass: String = "A1",
    val locked: Boolean = false,
    val noteFa: String = "",
    val version: Int = 1,
)

/** One changed row of `PUT /authority` ⟨1.5.1⟩: unlocked rows only, inside `bounds`; `actor: "owner"` takes a row back. */
@Serializable
data class AuthorityChange(val key: String, val actor: String? = null, val limit: JsonObject?, val version: Int)

/** The numeric fields a limit may carry, in the order a row is bounded on (§20.7; ⟨1.5.1⟩ `items` for the batch). */
val LIMIT_KEYS = listOf("tokens_month", "usd", "count_day", "count_hour", "items")

/** The one number a row's limit carries, if any. */
fun limitNumber(l: JsonObject?): Pair<String, Double>? {
    if (l == null) return null
    for (k in LIMIT_KEYS) (l[k] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull?.let { return k to it }
    return null
}

/** The weekdays of a row (`deploy.blackout_days`): SA, SU, MO … */
fun limitDays(l: JsonObject?): List<String>? = (l?.get("days") as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }

// ---------------------------------------------------------- risks (§20.8) --
@Serializable
data class RiskLinks(val finding: String? = null, val incident: String? = null, val decision: String? = null, val work: String? = null) {
    val refs: List<String> get() = listOfNotNull(finding, incident, decision, work)
}

@Serializable
/** One change of a risk. The hub sends [change] as the object of what changed (`{"created": true, "score": 12}`,
 *  `{"status": "accepted", "until": …}`); an older answer sent a sentence. [changeFa] reads either. */
data class RiskHistory(val at: String = "", val by: Actor? = null, val change: JsonElement = JsonPrimitive(""), val note: String = "") {
    val changeFa: String get() = when (val c = change) {
        is JsonPrimitive -> c.contentOrNull.orEmpty()
        is JsonObject -> c.entries.joinToString("، ") { (k, v) ->
            val label = RISK_CHANGE_FA[k] ?: k
            when {
                v is JsonPrimitive && v.contentOrNull == "true" -> label
                v is JsonNull -> "$label: —"
                v is JsonPrimitive -> "$label: ${v.content}"
                else -> label
            }
        }
        else -> ""
    }
}

private val RISK_CHANGE_FA = mapOf(
    "created" to "ثبت شد", "score" to "امتیاز", "origin" to "منشأ", "status" to "وضعیت", "until" to "تا", "decision" to "تصمیم",
    "likelihood" to "احتمال", "impact" to "اثر", "title_fa" to "عنوان", "owner_code" to "مسئول", "owner_kind" to "نوع مسئول",
    "review_at" to "بازبینی", "closed_at" to "بسته شد", "closed_by_code" to "بست", "treatment_md" to "درمان", "mitigation_md" to "کاهش",
    "category" to "دسته",
)

@Serializable
data class RiskAccepted(val decision: String, val until: String)

@Serializable
data class Risk(
    val id: String = "",
    val ref: String,
    val company: String,
    val titleFa: String,
    val bodyMd: String = "",
    /** product · security · data · money · people · vendor · ops · reputation */
    val category: String,
    /** 1..5 */
    val likelihood: Int,
    /** 1..5 */
    val impact: Int,
    /** likelihood × impact */
    val score: Int = likelihood * impact,
    val owner: Actor? = null,
    val mitigationMd: String? = null,
    /** open · mitigating · accepted · closed */
    val status: String,
    val reviewAt: String = "",
    val accepted: RiskAccepted? = null,
    val links: RiskLinks = RiskLinks(),
    val history: List<RiskHistory> = emptyList(),
    val version: Int = 1,
)

/** ⟨1.5.1⟩ the 5 × 5 counts, `counts[likelihood − 1][impact − 1]`. */
@Serializable
data class RiskMatrix(val company: String? = null, val counts: List<List<Int>> = emptyList()) {
    fun at(likelihood: Int, impact: Int): Int = counts.getOrNull(likelihood - 1)?.getOrNull(impact - 1) ?: 0
}

/** `POST /risks`: [owner], [mitigationMd] and [reviewAt] are optional (⟨1.5.1⟩). */
@Serializable
data class RiskIn(
    val company: String,
    val titleFa: String,
    val bodyMd: String,
    val category: String,
    val likelihood: Int,
    val impact: Int,
    val owner: String? = null,
    val mitigationMd: String? = null,
    val reviewAt: String? = null,
)

/** Longest review interval by score: ≥ 15 → 14 days, ≥ 8 → 30, else 90. */
fun reviewDays(score: Int): Int = if (score >= 15) 14 else if (score >= 8) 30 else 90

// -------------------------------------------------------- calendar (§20.9) --
@Serializable
data class EventSource(val decision: String? = null, val work: String? = null, val meeting: String? = null, val order: String? = null) {
    val ref: String? get() = decision ?: meeting ?: work ?: order
}

@Serializable
data class CalendarEvent(
    val id: String = "",
    val ref: String,
    /** null = every company (a holiday). */
    val company: String? = null,
    /** deploy · campaign · event · maintenance · meeting · freeze · holiday */
    val kind: String,
    val titleFa: String,
    val startsAt: String,
    val endsAt: String,
    val source: EventSource = EventSource(),
    /** planned · done · cancelled */
    val status: String = "planned",
    /** low · medium · high */
    val risk: String = "low",
    val createdBy: Actor? = null,
    /** ⟨1.5.1⟩ for If-Match. */
    val version: Int? = null,
)

/** ⟨1.5.1⟩ a single-event rule (a deploy on a blackout day) has `a == b`. */
@Serializable
data class Conflict(val a: String, val b: String, val rule: String, val severity: String = "medium", val noteFa: String = "")

@Serializable
data class CalendarView(val events: List<CalendarEvent> = emptyList(), val conflicts: List<Conflict> = emptyList())

/** `POST /calendar`: the kinds the owner adds by hand (deploys, meetings and holidays come from code). */
@Serializable
data class CalendarIn(val company: String?, val kind: String, val titleFa: String, val startsAt: String, val endsAt: String, val risk: String)

// ------------------------------------------------------ batch seal (§20.10) --
@Serializable
data class Batchable(
    val ref: String,
    val version: Int = 1,
    val kind: String,
    val company: String,
    val title: String,
    val quotaEstimate: QuotaOut = QuotaOut(),
    val proposer: Actor,
    val risk: String? = null,
    val createdAt: String? = null,
    val expiresAt: String? = null,
)

/** The exact set a batch passkey is bound to. */
@Serializable
data class BatchItem(val ref: String, val version: Int)

@Serializable
data class BatchResolution(val ref: String, val resolution: String? = null)

@Serializable
data class BatchOut(val batch: String, val items: List<BatchResolution> = emptyList())

/** `[{ref, version}]` sorted by ref: the canonical set (keys already in order, no spaces) whose SHA-256 is the target. */
fun batchItems(xs: List<BatchItem>): List<BatchItem> = xs.sortedBy { it.ref }

/** The kinds a batch may hold (§20.10); everything else, and anything irreversible, is never batched. */
val BATCH_KINDS = setOf("proposal", "meeting_resolution", "knowledge_entry")

// ------------------------------------------------------- codes (§20.11, §14) --
private val CODE_FA_17 = mapOf(
    "meeting_not_live" to "جلسه الان زنده نیست؛ ورود تو فقط در جلسه‌ی زنده ممکن است.",
    "knowledge_expired" to "این ورودی دانشنامه منقضی شده و به‌عنوان منبع پذیرفته نمیشود.",
    "batch_not_eligible" to "یکی از کارت‌ها عوض شده یا دیگر برای مُهر گروهی شایسته نیست؛ هیچ کارتی مُهر نشد.",
    "decision_not_pending" to "این کارت دیگر منتظر مُهر نیست؛ نسخه‌ی پایه عوض شده و کارت تازه میاید.",
    "version_conflict" to "همین حالا عوض شده؛ دوباره نگاه کن و بعد ذخیره کن.",
)

/** The Persian sentence for a failed §20 call: its stable codes in the app's words, the server's own sentence for the rest. */
fun govError(e: ApiException): String = CODE_FA_17[e.code] ?: e.messageFa

/** `422 batch_not_eligible`: why each card was refused (§20.12). */
val BATCH_REASON_FA = mapOf(
    "changed" to "کارت بعد از انتخاب عوض شد", "not_pending" to "دیگر منتظر مُهر نیست", "kind" to "این نوع کارت گروهی مُهر نمیشود",
    "action_class" to "کلاس اقدامش A1 نیست", "risk" to "ریسکش کم نیست", "irreversible" to "برگشت‌ناپذیر است", "amended" to "اصلاحیه دارد",
    "over_max_usd" to "از سقف دلاری مُهر گروهی بیشتر است", "over_max_items" to "از سقف تعداد مُهر گروهی بیشتر است", "held" to "ناظر نگهش داشته",
    "not_found" to "پیدا نشد",
)
