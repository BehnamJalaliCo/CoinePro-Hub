package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable

// Contract §55 ⟨1.33⟩: what the 1.0.1 look reads. The publish desk (§55.2), the limits block of the treasury (the owner's Claude accounts, each one ring, and
// today's meter) and, when the hub's live summary carries one, a 24-hour series for each figure of the office pulse. Same rules as
// Models.kt: camelCase here, snake_case on the wire; a field the hub omits takes its default, so an older hub still reads. The
// pulse's series rides beside the live summary (`LiveSummary.series`, Models42.kt): the hub's schema has no such field yet.

// ------------------------------------------------------------------ §55.3 the limits --
/**
 * One of the owner's Claude accounts. [state]: `working` (the hub is on it now) · `ready` · `full` (its window is used up until
 * [resetsAt]) · `off`. [utilization]: the share of its window that is used, 0..1 (the hub writes a decimal), null when unknown.
 * [key] is the account's key only: the owner reads [nameFa].
 */
@Serializable
data class ClaudeAccount(
    val key: String,
    val nameFa: String = "",
    val state: String = "ready",
    @Serializable(with = LenientDouble::class) val utilization: Double? = null,
    val windowFa: String? = null,
    val resetsAt: String? = null,
    val observedAt: String? = null,
)

/**
 * Today's agent spend against the daily cap. [share]: spent / cap (it may pass 1). [state]: `calm` · `warm` (past 70 %) · `near`
 * (past 90 %) · `full`. [noteFa]: the hub's one line on it; [resetsAt]: when the day's meter starts again.
 */
@Serializable
data class TodayMeter(
    val spent: Long = 0,
    val cap: Long = 0,
    @Serializable(with = LenientDouble::class) val share: Double? = null,
    val state: String? = null,
    val resetsAt: String = "",
    val noteFa: String = "",
)

/** `GET /treasury/limits`. [waiting]: every account is full and the work waits in the queue. */
@Serializable
data class Limits(
    val accounts: List<ClaudeAccount> = emptyList(),
    val waiting: Boolean = false,
    val today: TodayMeter = TodayMeter(),
)

// ------------------------------------------------------------------ the pulse's series --
/** The last 24 hours of each figure of the office pulse, oldest first, when the hub's live summary carries them; [until]: the moment
 *  of the last point. A hub that sends none: the pulse shows its numbers alone. */
@Serializable
data class PulseSeries(
    val working: List<Double>? = null,
    val sessions: List<Double>? = null,
    val waiting: List<Double>? = null,
    val until: String? = null,
)

// ------------------------------------------------------------------ §55.2 the publish desk --
/** A file of a desk card: what goes out, or the picture that goes with a reel. */
@Serializable
data class DeskFile(val id: String = "", val name: String = "", val mime: String = "application/octet-stream", val size: Long = 0)

/**
 * One output on the desk. [file]: what goes out (its video, else its picture); [cover]: the picture that goes with a reel; [files]:
 * how many files the package carries (a carousel's pictures). [routeReady] false: the company's publishing path is not set yet (the
 * technical team sets it; the card has no action). [state]: `ready` · `scheduled` · `publishing` · `published` · `failed` ·
 * `cancelled` · `waiting_setup` · `waiting_seal`. [publish]: the publication this card is about, once there is one. [at]: the
 * output's time for a ready card, the publication's own time otherwise. [output] is the app's key only: it is never shown.
 */
@Serializable
data class DeskCard(
    val output: String,
    val titleFa: String = "",
    val company: String = "",
    val companyFa: String = "",
    val order: String? = null,
    val groupFa: String? = null,
    val file: DeskFile = DeskFile(),
    val cover: DeskFile? = null,
    val files: Int = 1,
    /** reel · post · story · carousel */
    val kind: String = "post",
    val channel: String = "instagram",
    val account: String? = null,
    val accounts: List<String> = emptyList(),
    val routeReady: Boolean = false,
    val caption: String? = null,
    val state: String = "ready",
    val publish: SessionPublish? = null,
    val best: BestHour? = null,
    /** ask · auto */
    val mode: String? = null,
    val at: String = "",
)

/** `GET /publish-desk`: everything that can go out, is set to go out, or went out. Each list at most 30. */
@Serializable
data class PublishDesk(
    val ready: List<DeskCard> = emptyList(),
    val queue: List<DeskCard> = emptyList(),
    val done: List<DeskCard> = emptyList(),
)
