package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// Contract §57 ⟨1.35⟩, «تیم این جلسه»: the session keeps one main thread with its holder; each other person of it gets a small side talk
// the owner opens, says his word in, and closes («مستقیم بزنم روی کارمند باهاش توی یه فضای کوچیک حرف بزنم و ببندم»). Same rules as
// Models.kt: camelCase here, snake_case on the wire; a field the hub omits takes its default, so an older hub still reads.

/** The person in a seat: his code (the key of his side talk), his title, his company. */
@Serializable
data class SeatEmployee(val code: String = "", val titleFa: String = "", val company: String? = null)

/** The side talk's last line (≤ 160 letters): [who] `owner` · `seat`. */
@Serializable
data class SeatLast(val at: String = "", val who: String = "seat", val text: String = "")

/**
 * One seat of the session's team. [key]: the employee's code when filled, `role:<role>` when empty. [role]: the charter role
 * (`scriptwriter` · `video_director` · `motion_designer` · …), null for a person present in his own right. [roleFa]: «مسئول جلسه» ·
 * «نویسنده» · «کارگردان» · «موشن‌گرافی» · the person's own title. [holder]: the session's holder (no side talk: the main composer is
 * his). [state]: `working` (a run of his in this order is queued or running) · `idle` · `empty`. [unread]: his lines after the owner
 * last read this side talk.
 */
@Serializable
data class SessionSeat(
    val key: String = "",
    val role: String? = null,
    val roleFa: String = "",
    val holder: Boolean = false,
    val employee: SeatEmployee? = null,
    val state: String = "idle",
    val last: SeatLast? = null,
    val unread: Int = 0,
) {
    /** An empty media seat: «+ نویسنده», to be filled with one tap. */
    val empty: Boolean get() = state == "empty" || (employee == null && key.startsWith("role:"))
    /** The code his side talk is addressed by. */
    val code: String get() = employee?.code?.ifBlank { null } ?: key
    /** Who he is, as the owner reads him: his own title, else his seat's name. */
    val whoFa: String get() = employee?.titleFa?.trim()?.ifBlank { null } ?: roleFa
    /** The role an empty seat is filled with (`role:<role>`, or its [role]). */
    val roleKey: String? get() = role?.ifBlank { null } ?: key.removePrefix("role:").takeIf { key.startsWith("role:") && it.isNotBlank() }
}

/** §48's narrator of the order's company, for the «گوینده» chip. */
@Serializable
data class TeamNarrator(val company: String = "", val voice: String = "", val voiceFa: String = "", val styleFa: String? = null)

/** `GET /orders/{ref}/team` (and the answer of `/team/hire`): the holder first, the media seats of a content session, the rest present. */
@Serializable
data class SessionTeam(val seats: List<SessionSeat> = emptyList(), val narrator: TeamNarrator? = null)

/** One line of a side talk, newest last: [who] `owner` · `seat`. [workRef] is the app's key only: it is never shown. */
@Serializable
data class SideLine(
    val id: JsonPrimitive = JsonPrimitive(""),
    val at: String = "",
    val who: String = "seat",
    val whoFa: String = "",
    val text: String = "",
    val workRef: String? = null,
) {
    val idText: String get() = id.contentOrNull.orEmpty()
    val owner: Boolean get() = who == "owner"
}

/** `POST /orders/{ref}/team/{code}/say` → his word as a side line, the work it joined or made, and whether that work runs again now. */
@Serializable
data class SideSaid(val line: SideLine = SideLine(), val workRef: String? = null, val woken: Boolean = false)
