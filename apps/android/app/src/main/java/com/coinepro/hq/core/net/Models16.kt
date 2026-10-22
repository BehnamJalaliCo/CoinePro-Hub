package com.coinepro.hq.core.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ------------------------------------------------------------------ v1.5 --
// Contract §19 (prompt 10): the revenue radar, the funnel and referral rescue, the support desk the owner teaches, the shadow
// test, templates, lifecycle rules and NPS, the feedback inbox and intake from outside. Same rules as Models.kt: camelCase
// here, snake_case on the wire. A field is nullable exactly where §19 writes `|null`; money and USDT are decimal strings
// (§1), rates and shares are 0..1 (⟨1.5.1⟩). Companies, channels and exchanges are data: nothing here counts them.

// ------------------------------------------------------- revenue radar (§19.1) --
@Serializable
data class RevenueAccount(
    val id: String,
    val company: String,
    val exchange: String,
    val adapter: String,
    /** A §18.13 service account key; the exchange's key and secret never pass the API (`make account-secret`). */
    val serviceAccount: String,
    val titleFa: String,
    /** not_configured · ok · error */
    val status: String,
    val lastPullAt: String? = null,
    val lastError: String? = null,
    val version: Int = 1,
)

@Serializable
data class CoinAmount(val coin: String, val amount: String, val usdt: String, val priceSource: String = "")

@Serializable
data class DaySource(val adapter: String = "", val endpoints: List<String> = emptyList())

/** One settled day of one account (the exchange's settlement day; LBank: T+1, UTC+8). */
@Serializable
data class RevenueDay(
    val company: String,
    val account: String,
    val day: String,
    val commissionUsdt: String,
    val byCoin: List<CoinAmount> = emptyList(),
    val feesUsdt: String? = null,
    val volumeUsdt: String? = null,
    val newInvitees: Int = 0,
    val activeTraders: Int? = null,
    val depositsUsdt: String? = null,
    /** True only when every page of every endpoint answered. */
    val complete: Boolean = true,
    val pulledAt: String = "",
    val source: DaySource = DaySource(),
)

@Serializable
data class CompanyRevenue(val company: String, val usdt: String, val tokenCostUsd: String, val netUsd: String, val share: Double)

@Serializable
data class AccountRevenue(val account: String, val company: String, val usdt: String)

@Serializable
data class TrendDay(val day: String, val usdt: String)

/** One per incident: `drop` · `pull_failed` · `incomplete`. */
@Serializable
data class RevenueAlert(val kind: String, val company: String, val account: String? = null, val noteFa: String = "")

@Serializable
data class RevenueSummary(
    val period: String,
    val from: String,
    val to: String,
    val totalUsdt: String,
    val prevTotalUsdt: String? = null,
    val byCompany: List<CompanyRevenue> = emptyList(),
    val byAccount: List<AccountRevenue> = emptyList(),
    val trend: List<TrendDay> = emptyList(),
    val alerts: List<RevenueAlert> = emptyList(),
)

/** `POST /revenue/accounts` (🔏 `revenue.account`, sealed on this exact body). */
@Serializable
data class RevenueAccountIn(val company: String, val exchange: String, val adapter: String, val serviceAccount: String, val titleFa: String)

// ---------------------------------------------------- funnel and rescue (§19.2) --
/** A stage with no source is `connected: false, count: null`: a count is never estimated. */
@Serializable
data class FunnelStage(val key: String, val labelFa: String, val count: Int? = null, val connected: Boolean = false, val source: String? = null)

@Serializable
data class Conversion(val from: String, val to: String, val rate: Double? = null)

@Serializable
data class Leak(val stage: String, val noteFa: String = "", val rate: Double, val medianRate: Double)

@Serializable
data class Funnel(
    val company: String,
    val period: String,
    val from: String,
    val to: String,
    val stages: List<FunnelStage> = emptyList(),
    val conversions: List<Conversion> = emptyList(),
    val leaks: List<Leak> = emptyList(),
)

@Serializable
data class RescueStep(val at: String, val kind: String, val template: String? = null, val resultFa: String = "")

/** [subject] is a keyed pseudonym, never the handle or the exchange UID. */
@Serializable
data class RescueCase(
    val id: String = "",
    val ref: String,
    val company: String,
    val source: String,
    val conversation: String? = null,
    val exchange: String = "",
    val subject: String,
    val state: String,
    val steps: List<RescueStep> = emptyList(),
    val openedAt: String,
    val rescuedAt: String? = null,
    val closedAt: String? = null,
)

// --------------------------------------------------------- support desk (§19.3) --
@Serializable
data class SupportChannel(
    val company: String,
    /** telegram_business · telegram_bot · chatwoot · product_bot · mystery */
    val kind: String,
    /** not_configured · shadow · live · paused */
    val state: String,
    /** "Already went live" is `liveSince != null`. */
    val liveSince: String? = null,
    val pausedReason: String? = null,
    /** What may leave without the owner: kb_verbatim · kb_grounded · off. */
    val autoSend: String = "off",
    /** ⟨1.5.1⟩ for If-Match. */
    val version: Int = 1,
)

@Serializable
data class Customer(val displayName: String? = null, val handleMasked: String, val lang: String = "fa")

@Serializable
data class Handoff(val reason: String, val at: String)

@Serializable
data class MessageChecks(val guard: String = "pass", val grounded: String? = null)

/** [body] is masked: secrets, cards and seed phrases are never stored raw. */
@Serializable
data class SupportMessage(
    val id: String,
    val conversation: String,
    val at: String,
    val direction: String,
    val author: String,
    val body: String = "",
    /** draft · queued · sent · blocked · failed */
    val status: String = "sent",
    val kbRefs: List<String> = emptyList(),
    val confidence: Double? = null,
    val checks: MessageChecks = MessageChecks(),
    val blockedReasons: List<String> = emptyList(),
)

/** A conversation in a list; `GET /support/conversations/{ref}` adds its [messages], oldest first. */
@Serializable
data class Conversation(
    val id: String = "",
    val ref: String,
    val company: String,
    val channel: String,
    val customer: Customer,
    /** open · waiting_owner · answered · closed */
    val state: String,
    val openedAt: String,
    val lastMessageAt: String,
    val handoff: Handoff? = null,
    val tags: List<String> = emptyList(),
    val rescue: String? = null,
    val csat: Int? = null,
    val mystery: Boolean = false,
    val messages: List<SupportMessage> = emptyList(),
)

/** The teaching queue: what waits for the owner, oldest first. */
@Serializable
data class QueueItem(val conversation: String, val kind: String, val since: String, val draft: SupportMessage? = null, val company: String)

/** ⟨1.5.1⟩ teach: the answer sent (when the conversation waited on a live channel) and the KB proposal made from it. */
@Serializable
data class TeachOut(val message: SupportMessage? = null, val article: KbArticle)

// ------------------------------------------ knowledge, shadow test, go-live (§19.4) --
@Serializable
data class KbVariable(val name: String, val source: String)

@Serializable
data class KbLink(val url: String, val labelFa: String = "")

@Serializable
data class KbCode(val exchange: String, val code: String)

@Serializable
data class KbSource(val kind: String, val ref: String? = null)

@Serializable
data class KbArticle(
    val id: String = "",
    val ref: String,
    val company: String,
    val version: Int = 1,
    /** faq · policy · procedure · referral · official_link · safety */
    val kind: String,
    /** Policy keys, e.g. "vip.min_balance". */
    val key: String? = null,
    val questionFa: String,
    val variants: List<String> = emptyList(),
    val answerMd: String = "",
    val variables: List<KbVariable> = emptyList(),
    /** Referral and official_link only. */
    val links: List<KbLink> = emptyList(),
    val codes: List<KbCode> = emptyList(),
    /** proposed · approved · expired · retired */
    val status: String,
    val source: KbSource = KbSource("owner"),
    val approvedAt: String? = null,
    val expiresAt: String = "",
    @SerialName("uses_30d") val uses30d: Int = 0,
    val sha256: String = "",
)

/** `POST /support/kb`: a proposal; a new version of [ref] when given. Nulls and empty lists are left out. */
@Serializable
data class KbArticleIn(
    val company: String,
    val kind: String,
    val questionFa: String,
    val answerMd: String,
    val variants: List<String> = emptyList(),
    val key: String? = null,
    val variables: List<KbVariable> = emptyList(),
    val links: List<KbLink> = emptyList(),
    val codes: List<KbCode> = emptyList(),
    val ref: String? = null,
)

@Serializable
data class Disagreement(val case: String, val verdict: String, val noteFa: String = "")

/** Pass = correct ≥ [threshold] and zero safety failures and zero wrong codes or links. */
@Serializable
data class ShadowReport(
    val company: String,
    val suite: String,
    val runId: String = "",
    val at: String,
    val total: Int = 0,
    val correct: Int = 0,
    val partial: Int = 0,
    val wrong: Int = 0,
    val safetyFailures: Int = 0,
    val wrongCodes: Int = 0,
    val pass: Boolean = false,
    val threshold: Double = 0.9,
    val disagreements: List<Disagreement> = emptyList(),
)

@Serializable
data class HistoryOut(val suite: String? = null, val cases: Int? = null)

@Serializable
data class ShadowRunOut(val runId: String? = null)

// ---------------------------------------------- templates, lifecycle rules, NPS (§19.5) --
@Serializable
data class Template(
    val id: String = "",
    val ref: String,
    val company: String,
    val version: Int = 1,
    /** welcome · reactivation · rescue · nps · holding_reply · safety · csat */
    val purpose: String,
    val bodyFa: String = "",
    val variables: List<String> = emptyList(),
    /** proposed · sealed · retired */
    val status: String,
    val sealedAt: String? = null,
    val sha256: String = "",
)

@Serializable
data class RuleTrigger(val event: String? = null, val afterHours: Int? = null, val inactiveDays: Int? = null, val rrule: String? = null)

/** Every limit is sent: a rule's limits are what the owner seals in advance. */
@Serializable
data class RuleLimits(val perCustomerDays: Int, val dailyCap: Int, val quietHours: List<String>, val maxFollowUps: Int)

@Serializable
data class LifecycleRule(
    val id: String = "",
    val ref: String,
    val company: String,
    val version: Int = 1,
    /** welcome · reactivation · rescue · nps · csat */
    val kind: String,
    val trigger: RuleTrigger = RuleTrigger(),
    /** "TM-0007@2" */
    val template: String,
    val channel: String,
    val limits: RuleLimits,
    /** proposed · active · paused */
    val status: String,
    val decisionRef: String? = null,
    @SerialName("sent_30d") val sent30d: Int = 0,
    @SerialName("opt_outs_30d") val optOuts30d: Int = 0,
)

@Serializable
data class NpsWave(
    val ref: String,
    val company: String,
    val quarter: String,
    val sample: Int = 0,
    val sent: Int = 0,
    val responses: Int = 0,
    /** −100..100; null until someone answered. */
    val score: Int? = null,
    val promoters: Int = 0,
    val passives: Int = 0,
    val detractors: Int = 0,
    val opensAt: String,
    val closesAt: String,
    val commentsToFeedback: Int = 0,
)

@Serializable
data class TemplateIn(val company: String, val purpose: String, val bodyFa: String, val variables: List<String>, val ref: String? = null)

@Serializable
data class LifecycleRuleIn(val company: String, val kind: String, val trigger: RuleTrigger, val template: String, val channel: String, val limits: RuleLimits, val ref: String? = null)

// ------------------------------------------------------- feedback inbox (§19.7) --
@Serializable
data class FeedbackItem(
    val id: String = "",
    val ref: String,
    val company: String,
    /** bug · feature · confusion · complaint · praise */
    val kind: String,
    val area: String = "",
    val titleFa: String,
    val count: Int = 0,
    val firstSeen: String,
    val lastSeen: String,
    /** Masked, at most three. */
    val quotes: List<String> = emptyList(),
    /** SC-… and NP-… refs. */
    val sources: List<String> = emptyList(),
    /** new · triaged · in_backlog · done · wont_do */
    val state: String,
    val workRef: String? = null,
    val version: Int = 1,
)

// --------------------------------------------------------------- intake (§19.8) --
@Serializable
data class IntakeSource(
    val company: String,
    /** telegram · chatwoot · product */
    val kind: String,
    val configured: Boolean = false,
    val lastEventAt: String? = null,
    @SerialName("events_24h") val events24h: Int = 0,
    @SerialName("rejected_24h") val rejected24h: Int = 0,
)

/** ⟨1.5.1⟩ `POST /intake/sources` (🔏 `intake.source`, sealed on this exact body). */
@Serializable
data class IntakeSourceIn(val company: String, val kind: String, val allowedIps: List<String>, val kinds: List<String>)

/** The product events §19.8 accepts. */
val PRODUCT_EVENTS = listOf("signup", "uid_submitted", "referral_verified", "referral_failed", "vip_activated", "support_message")

// ------------------------------------------------------- codes (§19.9, §14) --
/** The outbound guard's refusals (§19.6). Without an override: the owner edits the text and the guard runs again. */
val GUARD_FA = mapOf(
    "asks_secret" to "رمز، کلید خصوصی، عبارت بازیابی، کد تأیید یا شماره‌ی کارت خواسته شده",
    "unknown_link" to "لینکی که در لینک‌های تأییدشده‌ی همین شرکت نیست",
    "unknown_code" to "کدی شبیه رفرال که عیناً تأیید نشده",
    "profit_promise" to "وعده‌ی سود (مثل «سود تضمینی» یا «بدون ضرر»)",
    "customer_data" to "داده‌ی مشتری دیگر (نام کاربری، UID یا تماس)",
    "internal_data" to "داده‌ی داخلی هلدینگ",
    "too_long" to "بیش از اندازه بلند",
    "red_line" to "خط قرمز اساسنامه؛ برای بازبینی نگه داشته شد",
)

/** No exception exists for these, not even for the owner. */
val NO_OVERRIDE = setOf("asks_secret", "profit_promise", "red_line")

private val CODE_FA = mapOf(
    "send_blocked" to "نگهبان خروجی این پیام را رد کرد و فرستاده نشد.",
    "shadow_not_passed" to "این کانال هنوز آزمون سایه را قبول نشده؛ شروع کانال فقط با کارت go-live بعد از قبولی است.",
    "template_not_sealed" to "نسخه‌ی قالب این قاعده هنوز مُهر نشده؛ اول قالب را مُهر کن.",
    "channel_not_live" to "این کانال روشن نیست؛ از آن پیامی به مشتری نمیرود.",
    "opted_out" to "این مشتری لغو کرده؛ هیچ پیام قاعده‌ای به او نمیرود.",
    "send_limit" to "سقف ارسال پر شده است",
)

/** The Persian sentence for a failed §19 call: the stable codes of §19.9 in the app's words (a 429 says when to try again);
 *  the server's own sentence for everything else. */
fun faError(e: ApiException): String {
    val base = CODE_FA[e.code] ?: e.messageFa
    val wait = e.retryAfter
    if ((e.code == "send_limit" || e.code == "rate_limited") && wait != null && wait > 0) {
        return "$base؛ " + (if (wait < 90) "$wait ثانیه‌ی" else "${(wait + 59) / 60} دقیقه‌ی") + " دیگر دوباره امتحان کن."
    }
    return base
}

/** A support channel change widens what leaves without the owner (🔏 `support.channel`): to `kb_grounded`, or a paused channel
 *  that already went live back to `live`. Narrowing (`kb_verbatim`, `off`) and pausing need no passkey. */
fun widens(c: SupportChannel, autoSend: String?, live: Boolean): Boolean =
    (autoSend == "kb_grounded" && c.autoSend != "kb_grounded") || (live && c.state != "live")
