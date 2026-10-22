package com.coinepro.hq.core.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// ------------------------------------------------------------------ v1.6 --
// Contract §22 (prompt 13): the media studio and the legal counsel. Departments defined by mandate and identity, roles written on
// demand by a department's manager, each company's media pipeline (script → direction → motion graphics as code → voice → sandboxed
// render → checks → publishing only through the official Telegram and Instagram APIs, under a series the owner seals once), the hub's
// own open-source voice chosen by the owner's ear, and the holding's legal counsel (cases LC-…, thread L, every outgoing email sealed).
// §22.7 ⟨1.6.1⟩ fixes the shapes the apps read. Same rules as Models.kt: camelCase here, snake_case on the wire, nullable exactly
// where §22 writes `|null`. Companies, accounts and voices are data: nothing here counts them.

/** The three model ceilings a department may have, lowest first (§22.1). */
val MODEL_CEILINGS = listOf("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")

// ------------------------------------------------- department mandate and identity (§22.1) --
/** «مبدأ و مقصد»: what a department starts from, where it must arrive, what it delivers, its limits and its ceilings. */
@Serializable
data class Mandate(
    val fromFa: String = "",
    val toFa: String = "",
    val outputsFa: List<String> = emptyList(),
    val boundariesFa: List<String> = emptyList(),
    val toolCeiling: List<String> = emptyList(),
    val modelCeiling: String = "claude-sonnet-5-5",
)

/** A starting suggestion of the template, never a limit. */
@Serializable
data class TeamRole(val role: String, val titleFa: String = "", val whyFa: String = "", val first: Boolean = false)

/** `PUT /companies/{code}/departments/{dept}/mandate`, sealed on the SHA-256 of exactly this body. */
@Serializable
data class MandateIn(val mandate: Mandate, val identityMd: String)

// ------------------------------------------------------------- roles on demand (§22.5) --
/** The overseer's review of a draft with its five checks (`ceiling` is the fifth), read in the server's order. */
@Serializable
data class DraftReview(val by: Actor? = null, val verdict: String = "pass", val checks: Map<String, Boolean> = emptyMap(), val sha256: String = "")

@Serializable
data class DraftEval(val suite: String = "", val cases: List<EvalCase> = emptyList())

@Serializable
data class CaseScore(val id: String, val score: Double? = null, val notes: String = "")

/** The draft's own eval run: score and verdict are null while it runs. */
@Serializable
data class DraftEvalRun(
    val id: String = "",
    val suite: String = "",
    /** queued · running · done · failed */
    val state: String = "done",
    val score: Double? = null,
    val passed: Boolean? = null,
    val cases: List<CaseScore> = emptyList(),
    val at: String = "",
) {
    val live: Boolean get() = state == "queued" || state == "running"
}

/** ⟨1.6.1⟩ the rule-based originality check before the overseer: the closest existing charter and how close. */
@Serializable
data class Originality(val ok: Boolean = true, val closest: String? = null, val noteFa: String? = null)

@Serializable
data class RoleDraft(
    val id: String = "",
    val ref: String,
    val company: String,
    val department: String,
    /** snake_case, unique in the company; empty while the manager writes. */
    val role: String = "",
    val titleFa: String = "",
    val titleEn: String = "",
    val whyMd: String = "",
    val charterMd: String = "",
    val tools: List<String> = emptyList(),
    val model: String = "",
    val effort: String = "",
    val limits: RoleLimits = RoleLimits(),
    val eval: DraftEval = DraftEval(),
    /** drafting · in_review · eval · proposed · active · rejected · retired */
    val state: String,
    val review: DraftReview? = null,
    val evalRun: DraftEvalRun? = null,
    val approver: Actor? = null,
    val decisionRef: String? = null,
    val version: Int = 1,
    val createdAt: String = "",
    val activatedAt: String? = null,
    // ⟨1.6.1⟩ who asked and what, who wrote it, what it was compared with, the originality check, hires on it, its retirement.
    val briefMd: String? = null,
    val requestedBy: Actor? = null,
    val writtenBy: Actor? = null,
    val compared: List<String> = emptyList(),
    val originality: Originality? = null,
    val hires: Int = 0,
    val retiredAt: String? = null,
    val stateNoteFa: String? = null,
) {
    val live: Boolean get() = state == "drafting" || state == "in_review" || state == "eval"
}

// --------------------------------------------------------------- the media studio (§22.2) --
/** The seven checks of §22.2, in their order; a series always carries all seven. */
val MEDIA_CHECKS = listOf("brand", "red_lines", "risk_warning", "facts", "rights", "platform", "qc")

@Serializable
data class SeriesTarget(
    /** telegram · instagram */
    val channel: String,
    /** A `/tools/accounts` key: `telegram-<co>`, `instagram-<co>`. */
    val account: String,
    /** telegram_post · telegram_story · instagram_reel · instagram_story · instagram_post */
    val placement: String,
)

@Serializable
data class VoiceChoice(val voiceId: String)

@Serializable
data class SeriesOverlay(val ctaFa: String? = null, val mark: Boolean = true)

@Serializable
data class SeriesFormat(
    /** 9:16 · 4:5 · 1:1 · 16:9 */
    val aspect: String = "9:16",
    val durationS: Int? = null,
    val voice: VoiceChoice? = null,
    val captions: Boolean = false,
    /** none · library */
    val music: String = "none",
    val overlay: SeriesOverlay = SeriesOverlay(),
)

@Serializable
data class Topics(val pool: List<String> = emptyList(), val ruleFa: String? = null)

@Serializable
data class SeriesToday(val made: Int = 0, val published: Int = 0)

@Serializable
data class Series(
    val id: String = "",
    val ref: String,
    val company: String,
    val titleFa: String = "",
    /** reel · story · post · carousel */
    val kind: String,
    val targets: List<SeriesTarget> = emptyList(),
    /** RRULE in the owner's time zone. */
    val schedule: String = "",
    val topics: Topics? = null,
    val format: SeriesFormat = SeriesFormat(),
    val checks: List<String> = MEDIA_CHECKS,
    val autoPublish: Boolean = false,
    val maxPerDay: Int = 1,
    /** draft · proposed · sealed · paused · retired */
    val status: String,
    /** The seal covers exactly this version (§22.2: `media.series` on the digest). */
    val digest: String = "",
    val version: Int = 1,
    val sealedAt: String? = null,
    // ⟨1.6.1⟩ who proposed it and its card, the next runs (computed by the server from the RRULE), today's count, its history.
    val proposedBy: Actor? = null,
    val decisionRef: String? = null,
    val nextAt: List<String> = emptyList(),
    val today: SeriesToday? = null,
    val itemsTotal: Int = 0,
    val createdAt: String = "",
    val updatedAt: String = "",
    val statusNoteFa: String? = null,
) {
    fun body(): SeriesIn = SeriesIn(company, titleFa, kind, targets, schedule, topics, format, checks, autoPublish, maxPerDay)
}

/** What `POST /media/series` and `PUT /media/series/{ref}` take, written whole (a null means "none"). */
@Serializable
data class SeriesIn(
    val company: String,
    val titleFa: String,
    val kind: String,
    val targets: List<SeriesTarget>,
    val schedule: String,
    val topics: Topics?,
    val format: SeriesFormat,
    val checks: List<String>,
    val autoPublish: Boolean,
    val maxPerDay: Int,
)

@Serializable
data class MediaSource(val kind: String = "", val ref: String? = null, val url: String? = null, val note: String = "")

@Serializable
data class Script(val textFa: String = "", val sources: List<MediaSource> = emptyList(), val by: Actor? = null)

@Serializable
data class Shot(val n: Int, val durationS: Double = 0.0, val visualFa: String = "", val textOnScreenFa: String? = null, val voiceFa: String? = null)

@Serializable
data class Direction(val shots: List<Shot> = emptyList(), val by: Actor? = null)

/** The motion graphics as code (§22.2 step 4): one HTML document or a Lottie JSON, by its hash. */
@Serializable
data class Composition(val format: String = "html", val sha256: String = "", val by: Actor? = null)

@Serializable
data class CheckResult(val key: String, val result: String = "n/a", val noteFa: String? = null)

@Serializable
data class Qc(val by: Actor? = null, val verdict: String = "pass", val noteMd: String = "")

/** Where an item goes out and what came back. ⟨1.6.1⟩ `error` ∈ no_api · account_not_configured · removed · remove_by_hand ·
 *  platform_limit; `external_id: "manual"` means the owner posted it from the card. */
@Serializable
data class PublishRow(
    val channel: String,
    val placement: String,
    val at: String? = null,
    val externalId: String? = null,
    val url: String? = null,
    val error: String? = null,
)

@Serializable
data class MediaItem(
    val id: String = "",
    val ref: String,
    val company: String,
    val series: String? = null,
    /** reel · story · post · carousel · design (UI mockups, never published) */
    val kind: String,
    val titleFa: String = "",
    /** scripting · directing · composing · voicing · rendering · checking · review · scheduled · published · waiting_owner · held · failed · rejected */
    val state: String,
    val script: Script? = null,
    val direction: Direction? = null,
    val composition: Composition? = null,
    val assets: List<FileRef> = emptyList(),
    val voice: FileRef? = null,
    val render: FileRef? = null,
    val captions: FileRef? = null,
    val checks: List<CheckResult> = emptyList(),
    val qc: Qc? = null,
    val publish: List<PublishRow> = emptyList(),
    val decisionRef: String? = null,
    val aiGenerated: Boolean = true,
    val cost: Usage = Usage(),
    val createdAt: String = "",
    val updatedAt: String = "",
    val version: Int = 1,
    // ⟨1.6.1⟩ the brief of a one-off or a design, the series topic, a design's deliverable, why it is held or failed, a carousel's pages.
    val briefMd: String? = null,
    val topicFa: String? = null,
    val deliverableRef: String? = null,
    val stateNoteFa: String? = null,
    val pages: List<FileRef> = emptyList(),
) {
    val live: Boolean get() = state in ITEM_LIVE
}

/** The states in which code or a role is still working on an item. */
val ITEM_LIVE = setOf("scripting", "directing", "composing", "voicing", "rendering", "checking")

@Serializable
data class VoiceSample(val script: String, val titleFa: String = "", val textFa: String = "", val file: FileRef)

/** One engine-and-speaker pair of the bake-off (§22.3, ⟨1.6.1⟩). `licence_commercial: false` is shown on every use. */
@Serializable
data class Voice(
    val id: String,
    val engine: String = "",
    val nameFa: String = "",
    val licence: String = "",
    val licenceCommercial: Boolean = false,
    /** Real-time factor on the hub's CPU; null until measured. */
    val rtf: Double? = null,
    val memMb: Int? = null,
    /** The owner's blind listening score, 1..10. */
    val ownerScore: Int? = null,
    /** candidate · active · retired */
    val status: String = "candidate",
    /** model · owner */
    val speaker: String = "model",
    val clones: Boolean = false,
    val samples: List<VoiceSample> = emptyList(),
    val noteFa: String? = null,
    val measuredAt: String? = null,
    val version: Int = 1,
)

/** The owner's own recorded reference (`GET /media/voices/reference`, 404 while there is none). */
@Serializable
data class VoiceReference(
    val file: FileRef? = null,
    val durationS: Double = 0.0,
    val createdAt: String = "",
    /** processing · ready · rejected */
    val state: String = "ready",
    val reasonFa: String? = null,
)

/** A publishing account's own limit and its use in the last 24 hours (`GET /media/limits`). */
@Serializable
data class PlatformLimit(
    val account: String,
    val channel: String = "",
    val company: String = "",
    @SerialName("per_24h") val per24h: Int? = null,
    @SerialName("used_24h") val used24h: Int = 0,
    val resetsAt: String? = null,
    val noteFa: String? = null,
)

// --------------------------------------------------------------- the legal counsel (§22.4) --
@Serializable
data class LegalCounterpart(
    val name: String = "",
    /** email · form · portal · other */
    val channel: String = "other",
    val address: String? = null,
)

@Serializable
data class TimelineEntry(
    val at: String,
    /** note · email_out · email_in · form · decision */
    val kind: String = "note",
    val ref: String? = null,
    val summaryFa: String = "",
)

@Serializable
data class Deadline(val at: String, val whatFa: String = "")

/** One message of a case's thread (⟨1.6.1⟩): an outgoing draft is its `email_send` card until sealed; incoming replies are masked. */
@Serializable
data class CaseEmail(
    val id: String = "",
    val case: String = "",
    /** out · in */
    val direction: String = "out",
    /** waiting_seal · sent · received · superseded · rejected */
    val state: String = "sent",
    val from: String = "",
    val to: List<String> = emptyList(),
    val cc: List<String> = emptyList(),
    val subject: String = "",
    val bodyMd: String = "",
    val attachments: List<FileRef> = emptyList(),
    /** fa · en */
    val lang: String = "fa",
    /** SHA-256 of the canonical {from, to, cc, subject, body_md, attachment sha256s, lang}: the seal is bound to it. */
    val digest: String = "",
    val decisionRef: String? = null,
    val messageId: String? = null,
    val at: String = "",
)

@Serializable
data class LegalCase(
    val id: String = "",
    val ref: String,
    val company: String,
    val titleFa: String = "",
    /** platform_restriction · account_appeal · takedown · partner_dispute · policy_review · contract_review · compliance · other */
    val kind: String = "other",
    val counterpart: LegalCounterpart = LegalCounterpart(),
    /** open · waiting_reply · waiting_owner · resolved · closed */
    val status: String,
    val timeline: List<TimelineEntry> = emptyList(),
    val deadlines: List<Deadline> = emptyList(),
    val openedBy: Actor? = null,
    val createdAt: String = "",
    val updatedAt: String = "",
    val version: Int = 1,
    // ⟨1.6.1⟩ the brief it was opened with; GET one adds the whole email thread.
    val briefMd: String? = null,
    val emails: List<CaseEmail> = emptyList(),
)

// ------------------------------------------------------------- the §22 cards (§22.6, §22.7) --
/** `media_publish` (A3): the item, its render, each placement and how it goes out (`api` or by the owner's hand). */
@Serializable
data class Placement(
    val channel: String = "",
    val placement: String,
    val account: String = "",
    /** api · manual */
    val via: String = "api",
    /** A PublishRow error code when this placement cannot go this time. */
    val blocked: String? = null,
)

@Serializable
data class PublishPayload(
    val item: String = "",
    val series: String? = null,
    val kind: String = "",
    val titleFa: String = "",
    /** one_off · check_failed · not_auto · no_api · series_not_sealed */
    val why: String = "",
    val placements: List<Placement> = emptyList(),
    val render: FileRef? = null,
    val checks: List<CheckResult> = emptyList(),
)

/** `media_series`: sealed on its own page, on the series digest (like a server plan). */
@Serializable
data class SeriesPayload(
    val series: String? = null,
    val version: Int? = null,
    val digest: String = "",
    val titleFa: String = "",
    val kind: String = "",
    val schedule: String = "",
    val autoPublish: Boolean = false,
    val maxPerDay: Int? = null,
    val targets: List<SeriesTarget> = emptyList(),
)

/** `role_new` (🔏, target = ref), ⟨1.6.1⟩. */
@Serializable
data class RoleNewPayload(
    val draft: String? = null,
    val company: String? = null,
    val department: String? = null,
    val role: String? = null,
    val titleFa: String? = null,
    val model: String? = null,
    val effort: String? = null,
    val limits: RoleLimits? = null,
    val toolsCount: Int? = null,
    val review: String? = null,
    val evalScore: Double? = null,
    val sha256: String? = null,
)

/** The exact message of an `email_send` card. */
@Serializable
data class EmailDraft(
    val case: String = "",
    val from: String = "",
    val to: List<String> = emptyList(),
    val cc: List<String> = emptyList(),
    val subject: String = "",
    val bodyMd: String = "",
    val attachments: List<FileRef> = emptyList(),
    val lang: String = "en",
    val digest: String = "",
)

fun CaseEmail.draft(): EmailDraft = EmailDraft(case, from, to, cc, subject, bodyMd, attachments, lang, digest)

/** The decision kinds of §22, all sealed with a fresh passkey (§22.6). */
val MEDIA_KINDS = setOf("media_series", "media_publish", "email_send", "role_new")

/** `email_send` is sealed on the exact message: the step-up target is the message digest, not the card's ref (§22.6). */
fun sealTarget(d: Decision): String =
    if (d.kind == "email_send") (d.payload["digest"] as? JsonPrimitive)?.contentOrNull?.takeIf { it.isNotBlank() } ?: d.ref else d.ref

/** A §22 payload as the app's model; null when it is missing or does not fit. */
fun <T> Decision.payloadAs(s: kotlinx.serialization.KSerializer<T>): T? = runCatching { Api.json.decodeFromJsonElement(s, payload) }.getOrNull()

// ------------------------------------------------------------------ publishing rules --
/** The platform's own rules (`platform`, §22.2), checked here before the server checks them again; null when the placement fits. */
fun placementFits(kind: String, aspect: String, placement: String): String? = when {
    placement == "instagram_reel" && (kind != "reel" || aspect != "9:16") -> "فقط ریلز ۹:۱۶"
    placement.endsWith("_story") && (kind != "story" || aspect != "9:16") -> "فقط استوری ۹:۱۶"
    placement == "instagram_post" && (kind !in setOf("post", "carousel") || aspect !in setOf("4:5", "1:1")) -> "پست یا کاروسل ۴:۵ یا ۱:۱"
    else -> null
}

/** The aspects each kind may take, the first the default. */
val KIND_ASPECTS = linkedMapOf("reel" to listOf("9:16"), "story" to listOf("9:16"), "post" to listOf("1:1", "4:5", "16:9"), "carousel" to listOf("4:5", "1:1"))

/** The owner's default daily caps (prompt 13 §0.9 #5). */
val KIND_CAP = mapOf("reel" to 2, "story" to 3, "post" to 2, "carousel" to 2)

/** The publishing account of a channel for a company: `telegram-fx`. */
fun accountKey(channel: String, company: String) = "$channel-${company.lowercase()}"

// ------------------------------------------------------------- codes (§22.6, §14) --
private val CODE_FA_19 = mapOf(
    "series_not_sealed" to "این برنامه‌ی انتشار مُهر نشده؛ چیزی خودکار منتشر نمیشود و آیتم کارت میشود.",
    "platform_limit" to "سقف انتشار خود پلتفرم برای این حساب پر شده",
    "held" to "ناظر کل این را نگه داشته؛ تا تصمیم تو کاری روی آن انجام نمیشود.",
    "account_not_configured" to "این حساب هنوز کلید ندارد؛ با make account-secret روی سرور واردش کن.",
    "version_conflict" to "همین حالا عوض شده؛ دوباره نگاه کن و بعد ذخیره کن.",
    "precondition_required" to "نسخه همراه درخواست نیامد؛ صفحه را تازه کن.",
    "decision_not_pending" to "این کارت دیگر منتظر تصمیم نیست.",
    "company_locked" to "کلید توقف این شرکت روشن است؛ هیچ انتشاری انجام نمیشود.",
    "policy_denied" to "سیاست این کار را اجازه نمیدهد.",
    "not_ready" to "این کار روی این نسخه‌ی سرور هنوز آماده نیست.",
)

/** The Persian sentence for a failed §22 call: its stable codes in the app's words (a platform limit or a rate limit says how long to
 *  wait; a refused body names its fields), the server's own sentence for everything else. */
fun mediaError(e: ApiException): String {
    val base = CODE_FA_19[e.code] ?: e.messageFa
    val wait = e.retryAfter
    if ((e.code == "platform_limit" || e.code == "rate_limited") && wait != null && wait > 0) {
        return "$base؛ " + (if (wait < 5400) "${(wait + 59) / 60} دقیقه‌ی" else "${(wait + 1800) / 3600} ساعت") + " دیگر."
    }
    if (e.code == "validation_failed" && e.fieldKeys.isNotEmpty()) return "${e.messageFa} (${e.fieldKeys.joinToString("، ")})"
    return base
}
