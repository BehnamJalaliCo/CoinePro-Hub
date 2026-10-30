package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable

// ------------------------------------------------------------------ v1.9 --
// Contract §27 (prompt 18): the owner names who plays an order (`player`: the router, Claude, or a substitute seat of §21.13), or calls
// the council of models (`mode: "council"`): the same brief runs on every available player and Claude writes the synthesis; for images
// and videos every player that can make the kind makes its own Creative and the owner picks one. And speech to text on the hub
// (`/meta.speech.enabled`, `transcript_fa` on the file, `file.transcribed` on the stream). Same rules as Models.kt: camelCase here,
// snake_case on the wire; a field the hub omits takes its default.

/** §27.3: the hub's own speech to text; `enabled` once the `stt` service runs (the pinned `small` faster-whisper). */
@Serializable
data class SpeechMeta(val enabled: Boolean = false)

/** §27.2: one player of a council: its run, its answer (a deliverable `O-…`, or a Creative `CR-…` for media work) and, when it was
 *  skipped or failed, why. */
@Serializable
data class CouncilMember(
    /** claude · gpt · gemini · deepseek */
    val player: String,
    val model: String = "",
    /** queued · working · done · failed · skipped */
    val state: String = "queued",
    val runId: String? = null,
    val deliverableRef: String? = null,
    val reason: String? = null,
    /** A media council's version of this player (the hub names it here; a `CR-…` in [deliverableRef] reads the same). */
    val creativeRef: String? = null,
) {
    /** The member's Creative, when it made one. */
    val creativeOf: String? get() = creativeRef ?: deliverableRef?.takeIf { it.startsWith("CR-") }

    /** A media council's member answers with a Creative. */
    val creative: Boolean get() = creativeOf != null
}

/** §27.2 `GET /work/{id}/council`; stream `work.council` carries every change. */
@Serializable
data class Council(
    val workRef: String = "",
    val members: List<CouncilMember> = emptyList(),
    /** Claude's synthesis (a deliverable): where the players agree, where they differ and why, the recommendation, each answer whole. */
    val synthesisRef: String? = null,
    /** running · synthesising · done · failed */
    val state: String = "running",
    /** image · video for a media council; null for words. */
    val media: String? = null,
) {
    /** Images or videos: the members answer with Creatives, and the owner picks one. */
    val mediaCouncil: Boolean get() = media != null || members.any { it.creative }
}
