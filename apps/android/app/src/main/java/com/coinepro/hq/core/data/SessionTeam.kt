package com.coinepro.hq.core.data

import com.coinepro.hq.core.net.ReportOutput
import com.coinepro.hq.core.net.SessionSeat
import com.coinepro.hq.core.net.SessionTeam
import com.coinepro.hq.core.net.SideLine
import com.coinepro.hq.core.net.TalkTurn
import com.coinepro.hq.core.net.TeamNarrator
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// Contract §57 ⟨1.35⟩ in the owner's words: «مستقیم بزنم روی کارمند باهاش توی یه فضای کوچیک حرف بزنم و ببندم و اون ادامه بده کارشو».
// The row «تیم این جلسه» under the session's header, its side talks, and what a direct turn delivered named once (§57.6: a chain of
// versions is its newest, with «نسخه‌ی n»). Pure functions: the unit tests read them. Prose counts in Persian digits.

/** The row's own name. */
const val TEAM_FA = "تیم این جلسه"

/** The row is shown when there is someone besides the holder to talk to, or a narrator to see: a team of the holder alone says nothing
 *  the header does not. Nothing on a hub without `/team` (null). */
fun teamShown(team: SessionTeam?): Boolean = team != null && (team.seats.count { !it.holder } > 0 || team.narrator != null)

/** A seat's chip: its name; an empty one «+ نویسنده». */
fun seatChipFa(s: SessionSeat): String = if (s.empty) "+ ${s.roleFa}" else s.roleFa

/** What a reader of the screen hears for a chip: who, in which seat, at work, and how many lines wait for the owner. */
fun seatSaidFa(s: SessionSeat): String = when {
    s.empty -> "${s.roleFa}: خالی؛ استخدام"
    else -> listOfNotNull(
        s.whoFa, s.roleFa.takeIf { it != s.whoFa }, "در کار".takeIf { s.state == "working" },
        if (s.unread > 0) "${faNum(s.unread)} حرف تازه" else null,
    ).joinToString("، ")
}

/** «گوینده: Kore، محکم» (the voice as the hub says it in Persian, else its name). */
fun narratorChipFa(n: TeamNarrator): String = "گوینده: ${n.voiceFa.trim().ifBlank { n.voice }}"

/** The one question before an empty seat is filled: «نویسنده استخدام شود؟». */
fun hireAskFa(s: SessionSeat): String = "${s.roleFa} استخدام شود؟"

/** The side talk's title: «با سناریست پرو-چارت». */
fun sideTitleFa(s: SessionSeat): String = "با ${s.whoFa}"

/** The team with one seat read (its side talk was opened: the hub marks it read on the newest page). */
fun teamRead(team: SessionTeam, code: String): SessionTeam =
    team.copy(seats = team.seats.map { if (it.code == code && it.unread != 0) it.copy(unread = 0) else it })

/** An older page put before the lines already here, each line once (by its id, else its time and words), newest last. */
fun mergeSideLines(older: List<SideLine>, newest: List<SideLine>): List<SideLine> {
    fun key(l: SideLine) = l.idText.ifBlank { "${l.at}|${l.who}|${l.text}" }
    val seen = HashSet<String>()
    return (older + newest).filter { seen.add(key(it)) }
}

/** A side line as a turn of the session's chat, so it is drawn as the session's own bubbles (the owner's on his side, the seat's opposite). */
fun sideTurn(l: SideLine, code: String): TalkTurn = TalkTurn(
    id = JsonPrimitive("side-" + l.idText.ifBlank { l.at }), by = if (l.owner) "owner" else code, text = if (l.owner) l.text else "",
    showMd = if (l.owner) null else l.text, at = l.at,
)

// ------------------------------------------------------------- §57.6 a chain of versions --
/** A ref read leniently: a string, or an object with its `ref`. */
fun refOf(e: JsonElement?): String? = when (e) {
    is JsonPrimitive -> e.contentOrNull?.trim()?.ifBlank { null }?.takeIf { e.isString }
    is JsonObject -> refOf(e["ref"])
    else -> null
}

/** The earlier deliverable [o] is a new version of: the report's own word on it, else its `produced_with` (the report's, then the
 *  deliverable's own, [producedWith]). */
fun revisionOf(o: ReportOutput, producedWith: JsonObject? = null): String? =
    refOf(o.revisionOf) ?: refOf((o.producedWith as? JsonObject)?.get("revision_of")) ?: refOf(producedWith?.get("revision_of"))

/** What the timeline draws of a session's outputs: [hidden] the older versions (each superseded by a newer one here), and the [version]
 *  number of the newest of each chain (2 and up; a first version has none). */
data class Revisions(val hidden: Set<String> = emptySet(), val version: Map<String, Int> = emptyMap())

/**
 * The chains of versions among [refs] (`previous` gives the earlier one of each). An earlier version that is not among them (an older
 * page) still counts in the number; a loop is cut where it closes.
 */
fun revisions(refs: List<String>, previous: (String) -> String?): Revisions {
    val here = refs.toSet()
    val hidden = HashSet<String>()
    for (r in refs) previous(r)?.takeIf { it != r && it in here }?.let(hidden::add)
    val version = HashMap<String, Int>()
    for (r in refs) {
        if (r in hidden) continue
        var n = 1
        var cur = r
        val seen = hashSetOf(r)
        while (true) {
            val p = previous(cur) ?: break
            if (!seen.add(p)) break
            n++
            if (p !in here) break
            cur = p
        }
        if (n > 1) version[r] = n
    }
    return Revisions(hidden, version)
}

/** «نسخه‌ی ۳» (a prose count: Persian digits). */
fun versionFa(n: Int): String = "نسخه‌ی ${faNum(n)}"
