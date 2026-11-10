package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable

// Contract §47–§53 ⟨1.31⟩: what the reels order still lacked. The ledger of what a company already said in a working group (a topic is
// never made twice), the company's narrator set once, the best hour to publish at, a standing routine made from one sentence, a scheduled
// post taken back, and how hard the workshop thought. Same rules as Models.kt: camelCase here, snake_case on the wire; a field the hub
// omits takes its default. The additive fields of older shapes are where those shapes live: `MemberPublish.best`, `PublishPanel.best`,
// `OrderReport.routines` and `SessionPublish.state` `cancelled` (Models29.kt).

// ------------------------------------------------------------------ §47.4 the ledger --
/**
 * One line of the ledger: a topic, or a reference (an outside sample, with its [url]). [source]: `claim` (the routine's work named it),
 * `package` (the hub read it from what went out), `owner` (he added it himself). [id] is the key a line is freed by.
 */
@Serializable
data class TopicEntry(
    val id: String = "",
    /** topic · reference */
    val kind: String = "topic",
    val titleFa: String = "",
    val url: String? = null,
    val at: String = "",
    val by: String = "",
    val source: String = "claim",
    val workRef: String? = null,
    val output: String? = null,
)

/** `GET /groups/{key}/members/{code}/topics`: a page of the ledger, newest first, and how many topics and references it holds in all. */
@Serializable
data class TopicLedger(
    val items: List<TopicEntry> = emptyList(),
    val topics: Int = 0,
    val references: Int = 0,
    val nextCursor: String? = null,
)

// ------------------------------------------------------------------ §48 the narrator --
/** One of the prebuilt speakers: its name (Latin, as the service names it), `female` or `male`, and its character in a word. */
@Serializable
data class VoiceOption(val name: String = "", val gender: String = "", val traitFa: String = "")

/**
 * `GET`/`PUT /companies/{code}/narrator`: the voice and the style every piece of that company's content is spoken with. [set] false: none
 * yet (a model chooses each time). [aistudio]: whether the hub's own sign-in to the speech service stands (`signed_in` · `signed_out` ·
 * `unknown`); only `signed_out` is the owner's step.
 */
@Serializable
data class Narrator(
    val company: String = "",
    val set: Boolean = false,
    val voice: String = "",
    val styleFa: String = "",
    val by: String? = null,
    val updatedAt: String? = null,
    val voices: List<VoiceOption> = emptyList(),
    val aistudio: String = "unknown",
)

// ------------------------------------------------------------------ §49 the best hour --
/**
 * `GET /companies/{code}/best-hour`: the hour an account's posts did best at ([hour] «HH:MM» in the owner's zone, [at] its next
 * occurrence). [enough] false: too little data yet; [noteFa] says what it rests on, or what is missing.
 */
@Serializable
data class BestHour(
    val account: String? = null,
    val hour: String? = null,
    val at: String? = null,
    val enough: Boolean = false,
    val posts: Int = 0,
    val days: Int = 0,
    val basis: String = "likes_comments",
    val noteFa: String = "",
    val readAt: String? = null,
)

// ------------------------------------------------------------------ §50 a standing routine --
/**
 * `POST /routines` and `OrderReport.routines`: a standing routine made from one sentence of the owner. [whenFa]: its schedule in plain
 * Persian; [previewFa]: what each run does; [nextAt]: its next run while it is `on`; [noteFa]: why its last run did not go through.
 * [ref] is the key it is switched by (never shown).
 */
@Serializable
data class SessionRoutine(
    val ref: String,
    val company: String? = null,
    val sentenceFa: String = "",
    val whenFa: String = "",
    val previewFa: String = "",
    /** proposed · on · off */
    val state: String = "on",
    val nextAt: String? = null,
    val lastRunAt: String? = null,
    val runs: Int = 0,
    val order: String? = null,
    val noteFa: String? = null,
)
