package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Canvas
import com.coinepro.hq.core.net.CanvasNode
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.Home
import com.coinepro.hq.core.net.HomeOrder
import com.coinepro.hq.core.net.Notification
import com.coinepro.hq.core.net.Office
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.ReportOutput
import com.coinepro.hq.core.net.ReportStep
import com.coinepro.hq.core.net.SessionParticipant
import com.coinepro.hq.core.net.SessionBrief
import com.coinepro.hq.core.net.SessionCard
import com.coinepro.hq.core.net.SessionTask
import com.coinepro.hq.core.net.TalkTurn
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

// Contract §34–§35 ⟨1.16, 1.17⟩ in the owner's words: every order a session (its badge, its people and models, its plan, its pace and
// its close), the office that is his home, and the canvas of the companies and their links. Pure functions: the unit tests read them.
// A ref (F-…, CV-…, W-…) is a key here and never a word the owner reads.

// ----------------------------------------------------------------- badges --
/** Each badge in words, and its order in a list: the owner's turn first. */
val BADGE_FA = linkedMapOf(
    "your_turn" to "نوبت تو",
    "ready" to "آماده‌ی تأیید",
    "stuck" to "گیر",
    "moving" to "در جریان",
    "closed" to "بسته",
)

fun badgeFa(badge: String): String = BADGE_FA[badge] ?: "در جریان"

fun badgeTone(badge: String): Tone = when (badge) {
    "your_turn" -> Tone.GOLD
    "ready" -> Tone.POS
    "stuck" -> Tone.NEG
    "closed" -> Tone.SILVER
    else -> Tone.LAPIS
}

private fun badgeRank(badge: String): Int = BADGE_FA.keys.indexOf(badge).let { if (it < 0) 3 else it }

/** The open sessions as the office lists them: hidden and closed ones out; your turn, ready, stuck, moving; newest move first in each. */
fun sortSessions(list: List<SessionCard>): List<SessionCard> =
    list.filter { !it.hidden && it.badge != "closed" && it.closedAt == null }
        .sortedWith(compareBy<SessionCard> { badgeRank(it.badge) }.thenByDescending { it.lastAt.ifBlank { it.openedAt } })

/** How many sessions wait for the owner (the bottom bar's badge on «جلسه‌ها»). */
fun yourTurnCount(list: List<SessionCard>): Int = list.count { it.badge == "your_turn" && !it.hidden && it.closedAt == null }

/** The one plain line under a session's title: why its badge, else what is needed from the owner, else what is happening now. */
fun sessionLine(s: SessionCard): String = s.reasonFa.ifBlank { s.brief.needFa.ifBlank { s.brief.nowFa } }

// ------------------------------------------------------------------ pace --
val PACE_FA = mapOf("step" to "با من", "auto" to "خودکار")
val PACE_HINT_FA = mapOf(
    "step" to "مسئول یک قدم برمیدارد و بعد از تو میپرسد.",
    "auto" to "مسئول برنامه میریزد و تا آخر میرود؛ فقط برای مُهر می‌ایستد.",
)


// ---------------------------------------------------------- participants --
/** The council models a session can bring in (§35.3 players), in the owner's words. */
val PLAYER_FA = linkedMapOf("gpt" to "جی‌پی‌تی", "gemini" to "جمنای", "deepseek" to "دیپ‌سیک")

/** The fixed people a session can bring in (§35.4: `invite` accepts them too). */
val FIXED_PEOPLE_FA = linkedMapOf("advisor" to "مشاور کل", "overseer" to "ناظر کل", "assistant" to "دستیار شخصی", "secretary" to "منشی هلدینگ")

fun isPlayer(key: String): Boolean = key.startsWith("player:")

/** A participant's name: the hub's words, else a model's name, else a fixed person, else the role of a manager. */
fun participantTitle(p: SessionParticipant): String = p.titleFa.ifBlank { participantKeyTitle(p.key) }

fun participantKeyTitle(key: String): String = when {
    isPlayer(key) -> PLAYER_FA[key.removePrefix("player:")] ?: "مدل بیرونی"
    else -> FIXED_PEOPLE_FA[key] ?: TALK_ROLE_FA[key.substringBefore('@')] ?: "همکار"
}

/** The holder first, then people, then models; each once. */
fun orderParticipants(list: List<SessionParticipant>): List<SessionParticipant> =
    list.distinctBy { it.key }.sortedBy { when (it.kind) { "holder" -> 0; "person" -> 1; else -> 2 } }

/** Who the owner's next word goes to, in words: «همه» for all, else the participant, else the holder. */
fun addresseeFa(to: String?, participants: List<SessionParticipant>): String = when (to) {
    null -> participants.firstOrNull { it.kind == "holder" }?.let(::participantTitle) ?: "مسئول"
    "all" -> "همه"
    else -> participants.firstOrNull { it.key == to }?.let(::participantTitle) ?: participantKeyTitle(to)
}

/** Models not yet in the session (the «+ مدل» sheet). */
fun playersToAdd(present: List<SessionParticipant>): List<String> = PLAYER_FA.keys.filter { k -> present.none { it.key == "player:$k" } }

// ----------------------------------------------------------------- tasks --
val TASK_STATE_FA = mapOf("todo" to "مانده", "doing" to "در کار", "done" to "انجام شد", "dropped" to "کنار رفت")

/** A tick: done ↔ todo (a task in work is ticked done). */
fun tickedState(state: String): String = if (state == "done") "todo" else "done"

/** The plan in its order: by [SessionTask.n], dropped ones last. */
fun orderedTasks(list: List<SessionTask>): List<SessionTask> = list.sortedWith(compareBy<SessionTask> { if (it.state == "dropped") 1 else 0 }.thenBy { it.n })

/** «۳ از ۵» of the plan (done of those not dropped). */
fun taskProgress(list: List<SessionTask>): Pair<Int, Int> = list.filter { it.state != "dropped" }.let { live -> live.count { it.state == "done" } to live.size }

// ------------------------------------------------------------- the report --
/** The session's state from its report: the hub's block when there is one, else read from the order's own state (a hub before ⟨1.17⟩). */
fun sessionBadge(r: OrderReport): String = r.session?.badge ?: when {
    r.turn != null -> "your_turn"
    r.state in setOf("delivered", "failed", "cancelled") -> "closed"
    r.blockers.isNotEmpty() -> "stuck"
    else -> "moving"
}

fun sessionClosed(r: OrderReport): Boolean = r.session?.state == "closed" || (r.session == null && r.state in setOf("delivered", "failed", "cancelled"))

/** «چه شد · حالا چه · از تو چه»: the hub's brief, else built from the report (its end summary, its last step, its open turn). */
fun briefOf(r: OrderReport): SessionBrief = r.brief ?: SessionBrief(
    doneFa = r.summary?.doneFa.orEmpty().ifBlank { r.steps.lastOrNull()?.whatFa.orEmpty() },
    nowFa = r.ack?.planFa.orEmpty(),
    needFa = r.turn?.questionFa?.let { "جواب بده: $it" } ?: r.summary?.needFa.orEmpty(),
)

/** ⟨0.17.0⟩ The one line beside the badge in the session's head: why it is stuck; on the owner's turn what is needed from him; else
 *  «حالا چه»; else why its badge. */
fun sessionStatusLine(r: OrderReport): String {
    val b = briefOf(r)
    val reason = r.session?.reasonFa.orEmpty()
    return when (sessionBadge(r)) {
        "stuck" -> reason.ifBlank { b.nowFa }
        "your_turn" -> b.needFa.ifBlank { r.turn?.questionFa.orEmpty() }.ifBlank { b.nowFa }
        "closed" -> reason
        else -> b.nowFa.ifBlank { reason }
    }.let(::oneLine)
}

// ------------------------------------------------------------- the timeline --
// ⟨0.17.0⟩ The session is a chat that gets things done: the talk's turns as bubbles; the steps of the work as one quiet line each at
// their time (a step the hub wrote into the talk, or a step of the report the talk never heard); each result delivered as one compact
// card at its time. Nothing is stacked above the chat.

/** Who the hub's own steps are by (`order_report._step`). */
const val SYSTEM_FA = "سامانه"

/** The lead of a holder's question in the talk (`order_turns.to_talk(ask=True)`): a question is a bubble, never a quiet line. */
private const val ASK_LEAD = "**سؤال از شما**"

/** The hub's line for a result that arrived (`order_report`, «خروجی رسید: …» / «خروجی ناقص رسید: …»). */
private val ARRIVED = listOf("خروجی رسید:", "خروجی ناقص رسید:")

/** One line of a session's chat, in time order. */
sealed interface SessionEntry {
    val key: String
    val at: String

    /** A turn of the talk: the owner's, or an answer with its cards. */
    data class Said(val turn: TalkTurn) : SessionEntry {
        override val key: String get() = "t-" + turn.idText.ifBlank { "n${turn.n}" } + "-" + turn.n
        override val at: String get() = turn.at
    }

    /** A step of the work, one quiet line at its time; [by] the persona it was written under, when it came through the talk. */
    data class Step(override val at: String, val text: String, override val key: String, val by: String? = null) : SessionEntry

    /** A result delivered, one compact card at its time (at the end when its time is not known). */
    data class Output(val output: ReportOutput, override val at: String) : SessionEntry {
        override val key: String get() = "o-" + output.ref
    }
}

/** A step the hub wrote into the talk by itself (a progress line, «… آمد.»): no model spoke, nothing to act on. A holder's question,
 *  his hello and any turn with cards, files or voice stay bubbles. */
fun isStepTurn(t: TalkTurn): Boolean {
    if (t.owner || t.source != "system" || t.state != "done" || t.cards.isNotEmpty() || t.files.isNotEmpty() || t.audio.isNotEmpty()) return false
    val s = t.shown.trim()
    return s.isNotEmpty() && !s.startsWith(ASK_LEAD) && !s.startsWith("سلام")
}

/** An instant of the hub's ISO times, read here (pure JVM: the unit tests run it without Android's calendar). */
private fun instantOf(iso: String): java.time.Instant? =
    if (iso.isBlank()) null else runCatching { java.time.OffsetDateTime.parse(iso).toInstant() }.getOrNull() ?: runCatching { java.time.Instant.parse(iso) }.getOrNull()

/** A text in one line: no markdown marks, no line breaks. */
fun oneLine(text: String): String = com.coinepro.hq.core.format.plainOfMd(text).replace(Regex("\\s*\\n+\\s*"), " ").trim()

/** A quiet line with who did it: «[title]: [text]», unless the line already names him or someone («مدیر رسانه آمد.», «مدیر رسانه: …»). */
fun stepWithSpeaker(text: String, title: String?): String =
    if (title.isNullOrBlank() || text.contains(title) || NAMED.containsMatchIn(text)) text else "$title: $text"

private val NAMED = Regex("^[^:،.]{1,40}:\\s")

/** The result a step of the report announces («خروجی رسید: <title>»), if it is one of [outputs]. */
private fun arrivalOf(s: ReportStep, outputs: List<ReportOutput>): ReportOutput? {
    val what = s.whatFa.trim()
    val lead = ARRIVED.firstOrNull { what.startsWith(it) } ?: return null
    val title = what.removePrefix(lead).trim()
    return outputs.firstOrNull { o -> o.titleFa.isNotBlank() && (o.titleFa.trim() == title || title.contains(o.titleFa.trim())) }
}

/**
 * The session's chat in time order: the talk's [turns] as they are (each a bubble, or a quiet line when [isStepTurn]); the report's
 * steps the talk never heard (the hub's own, by [SYSTEM_FA]; every step when there is no talk yet, [hasTalk] false) as quiet lines; and
 * each of its outputs as a card at the time its arrival was written. Each one goes before the first turn later than it.
 */
fun sessionTimeline(turns: List<TalkTurn>, report: OrderReport?, hasTalk: Boolean): List<SessionEntry> {
    val said = turns.map { t -> if (isStepTurn(t)) SessionEntry.Step(t.at, oneLine(t.shown), "st-" + t.idText.ifBlank { "n${t.n}" } + "-" + t.n, by = t.by) else SessionEntry.Said(t) }
    val outputs = report?.outputs.orEmpty()
    val steps = report?.steps.orEmpty()
    val extra = mutableListOf<SessionEntry>()
    for (s in steps) {
        if (arrivalOf(s, outputs) != null) continue
        if (hasTalk && s.whoFa.trim() != SYSTEM_FA) continue
        val what = oneLine(s.whatFa)
        if (what.isBlank() || what == "-") continue
        val line = if (hasTalk || s.whoFa.isBlank() || s.whoFa.trim() == SYSTEM_FA) what else "${s.whoFa.trim()}: $what"
        extra += SessionEntry.Step(s.at, line, "sr-" + s.at + "-" + line.hashCode())
    }
    for (o in outputs) extra += SessionEntry.Output(o, steps.firstOrNull { arrivalOf(it, outputs)?.ref == o.ref }?.at.orEmpty())
    val later = extra.distinctBy { it.key }.sortedBy { instantOf(it.at)?.toEpochMilli() ?: Long.MAX_VALUE }
    val out = ArrayList<SessionEntry>(said.size + later.size)
    var j = 0
    for (e in said) {
        val t = instantOf(e.at)
        if (t != null) while (j < later.size && instantOf(later[j].at)?.let { !it.isAfter(t) } == true) out += later[j++]
        out += e
    }
    while (j < later.size) out += later[j++]
    return out
}

// ---------------------------------------------------------- the chat, tidy --
// ⟨0.19.0⟩ The owner, 2026-11-08: «ببین چقدر همه چیز بهم ریختس». Nothing is taken away; it is put in order. The steps between two turns
// are one quiet row («۳ رویداد · 05:34–05:40») that opens to every line whole; the results that arrive together are one card; what
// blocks the work is over the composer, not in the chat; no ref is ever a word.

/** A ref in parentheses, with the hub's trailing hyphen too («جواب آمد (O-000122-): …»): it goes, with the space before it. */
private val REF_PAREN = Regex("[ \\t]*[(（][ \\t]*[A-Z]{1,3}-\\d{3,10}-?[ \\t]*[)）]")
/** A bare ref with a trailing hyphen («O-000122-»): read as the ref. */
private val REF_HYPHEN = Regex("(?<![A-Za-z0-9-])([A-Z]{1,3}-\\d{3,10})-(?![A-Za-z0-9])")

/** A line of the work as the owner reads it: in one line, no markdown, no ref (one in parentheses goes, any other becomes its word). */
fun quietLine(text: String): String = withoutRefs(oneLine(text).replace(REF_PAREN, "").replace(REF_HYPHEN, "$1")).trim()

/** One row of the session's chat as drawn. */
sealed interface ChatRow {
    val key: String

    /** A turn of the talk, a bubble. */
    data class Turn(val said: SessionEntry.Said) : ChatRow {
        override val key: String get() = said.key
    }

    /** The steps between two turns: one quiet row («۳ رویداد · 05:34–05:40»), or the line itself when it is one. */
    data class Events(val steps: List<SessionEntry.Step>) : ChatRow {
        override val key: String get() = "ev-" + steps.first().key
    }

    /** The results delivered between two turns: one card. */
    data class Outputs(val outputs: List<SessionEntry.Output>) : ChatRow {
        override val key: String get() = "og-" + outputs.first().key
    }
}

/** The chat in rows: each turn; between two turns, its steps as one row and its results as one card, each where its first one fell. */
fun chatRows(entries: List<SessionEntry>): List<ChatRow> {
    val out = ArrayList<ChatRow>()
    val steps = ArrayList<SessionEntry.Step>()
    val outputs = ArrayList<SessionEntry.Output>()
    var stepsFirst = true
    fun flush() {
        val ev = if (steps.isEmpty()) null else ChatRow.Events(steps.toList())
        val og = if (outputs.isEmpty()) null else ChatRow.Outputs(outputs.toList())
        if (stepsFirst) { ev?.let(out::add); og?.let(out::add) } else { og?.let(out::add); ev?.let(out::add) }
        steps.clear(); outputs.clear(); stepsFirst = true
    }
    for (e in entries) when (e) {
        is SessionEntry.Said -> { flush(); out += ChatRow.Turn(e) }
        is SessionEntry.Step -> { if (steps.isEmpty() && outputs.isEmpty()) stepsFirst = true; steps += e }
        is SessionEntry.Output -> { if (steps.isEmpty() && outputs.isEmpty()) stepsFirst = false; outputs += e }
    }
    flush()
    return out
}

/** «۳ رویداد» (Persian digits: a prose count). */
fun eventsCountFa(n: Int): String = "${faNum(n)} رویداد"

/** The clock range of a row of steps, «05:34–05:40» (one time when they share it; empty without times), from [clock] (the owner's zone). */
fun eventsSpan(steps: List<SessionEntry.Step>, clock: (String) -> String): String {
    val times = steps.map { it.at }.filter { it.isNotBlank() }
    if (times.isEmpty()) return ""
    val a = clock(times.first())
    val b = clock(times.last())
    return if (a == b) a else "$a–$b"
}

/** «۲ خروجی تحویل شد»; one: «<its kind> تحویل شد». */
fun outputsFa(outputs: List<ReportOutput>): String =
    if (outputs.size == 1) "${outputKindFa(outputs.first().kind)} تحویل شد" else "${faNum(outputs.size)} خروجی تحویل شد"

/** «۲ گیر» (Persian digits). */
fun blockersFa(n: Int): String = "${faNum(n)} گیر"

// --------------------------------------------------------------- the office --
/** The office from a hub before ⟨1.17⟩ (no `/office`): its orders as sessions, the pending cards, the critical items and suggestions. */
fun officeFallback(home: Home?, pending: List<Decision>, companies: List<Company>): Office = Office(
    sessions = home?.orders.orEmpty().mapNotNull(::sessionOfOrder),
    approvals = pending.take(10),
    approvalsTotal = pending.size,
    critical = home?.critical.orEmpty(),
    suggestions = listOfNotNull(home?.cards?.effective, home?.cards?.good),
    canvas = Canvas(nodes = companies.filter { it.status != "archived" }.map { CanvasNode(it.code, it.nameFa ?: it.code, if (it.kind == "holding") "holding" else "company") }),
)

/** An order of the older home as a session: an ended one is not open. */
fun sessionOfOrder(o: HomeOrder): SessionCard? {
    val badge = when (o.state) {
        "delivered", "failed", "cancelled" -> return null
        "waiting" -> "your_turn"
        "blocked" -> "stuck"
        else -> "moving"
    }
    return SessionCard(ref = o.ref, titleFa = o.textFa, badge = badge, reasonFa = o.summaryFa)
}

// ------------------------------------------------------------- notifications --
/** What reaches the owner's list and badge: owner-visible, and nothing technical unless it is critical (§29.1, §34.4). */
fun forOwner(n: Notification): Boolean =
    n.ownerVisible && (n.domain == null || n.domain !in com.coinepro.hq.core.net.Api.TECH_DOMAINS || n.criticalReason != null)

/** The bell's count: the owner's unread, filtered as the list is. */
fun ownerUnread(list: List<Notification>): Int = list.count { it.readAt == null && forOwner(it) }

// ------------------------------------------------------------ what a card made --
/** What a ref names, in one word, for «ساخته شد: فرمان» (the ref itself is never shown). */
fun madeFa(ref: String): String = when (Refs.prefix(ref)) {
    "F" -> "فرمان"
    "D" -> "تصمیم"
    "W" -> "کار"
    "O" -> "خروجی"
    "MT" -> "جلسه"
    "LN" -> "خط تولید"
    "AT" -> "خودکارسازی"
    "SO" -> "قانون"
    "PL" -> "یادآوری"
    "CV" -> "گفتگو"
    "PB" -> "کارگروه"
    else -> "مورد"
}

/** The page a made ref opens (an order made from a card is a session); the ref router, never the ref itself as a route. */
fun madeRouteOf(ref: String): String? = Refs.route(ref)

// ------------------------------------------------------------------- links --
val LINK_KIND_FA = linkedMapOf("serves" to "خدمت", "publishes" to "انتشار", "feeds" to "داده", "sells" to "فروش", "supports" to "پشتیبانی")
val LINK_KIND_HINT_FA = mapOf(
    "serves" to "یکی برای دیگری کار انجام میدهد",
    "publishes" to "خروجی یکی در کانال دیگری منتشر میشود",
    "feeds" to "داده‌ی یکی به دیگری میرسد",
    "sells" to "یکی محصول دیگری را میفروشد",
    "supports" to "یکی مشتری‌های دیگری را پشتیبانی میکند",
)

fun linkKindFa(kind: String): String = LINK_KIND_FA[kind] ?: "پیوند"

fun linkTone(kind: String): Tone = when (kind) {
    "serves" -> Tone.LAPIS
    "publishes" -> Tone.GOLD
    "feeds" -> Tone.LEARN
    "sells" -> Tone.POS
    "supports" -> Tone.SILVER
    else -> Tone.NEUTRAL
}

/** A new link is between two different companies (the hub's link is implicit); and one that is already on is not made twice. */
fun canLink(from: String?, to: String?, links: List<com.coinepro.hq.core.net.CompanyLink>, kind: String? = null): Boolean =
    from != null && to != null && from != to && links.none { it.state == "on" && it.from == from && it.to == to && (kind == null || it.kind == kind) }

// ------------------------------------------------------------------ canvas --
/** A point on the canvas, 0…1 of its width and height. */
data class Spot(val x: Float, val y: Float)

/**
 * Where each node sits: the owner's own place when the hub has one, else the holding at the centre and the companies on a circle around
 * it (in the canvas's order, the first at the top). [radius] is a fraction of the shorter side.
 */
fun layoutCanvas(nodes: List<CanvasNode>, radius: Float = 0.36f): Map<String, Spot> {
    // Only the companies the owner has not placed share the circle, so a placed one never sits on a computed one.
    val companies = nodes.filter { it.kind != "holding" && (it.x == null || it.y == null) }
    val out = LinkedHashMap<String, Spot>()
    for (n in nodes) {
        val x = n.x; val y = n.y
        if (x != null && y != null) { out[n.code] = Spot(x.toFloat().coerceIn(0f, 1f), y.toFloat().coerceIn(0f, 1f)); continue }
        if (n.kind == "holding") { out[n.code] = Spot(0.5f, 0.5f); continue }
        val i = companies.indexOf(n)
        val a = -PI / 2 + 2 * PI * i / companies.size.coerceAtLeast(1)
        out[n.code] = Spot((0.5 + radius * cos(a)).toFloat(), (0.5 + radius * sin(a)).toFloat())
    }
    return out
}

/** The node under a point (fractions of the canvas), within [reach]; the nearest when two are close. */
fun nodeAt(spots: Map<String, Spot>, x: Float, y: Float, reach: Float = 0.09f): String? =
    spots.entries.map { it.key to hypot((it.value.x - x).toDouble(), (it.value.y - y).toDouble()) }
        .filter { it.second <= reach }.minByOrNull { it.second }?.first

/** The link under a tap: the nearest whose line passes within [reach] of the point (both ends must be on the canvas). */
fun linkAt(spots: Map<String, Spot>, links: List<com.coinepro.hq.core.net.CompanyLink>, x: Float, y: Float, reach: Float = 0.04f): com.coinepro.hq.core.net.CompanyLink? =
    links.mapNotNull { l ->
        val a = spots[l.from] ?: return@mapNotNull null
        val b = spots[l.to] ?: return@mapNotNull null
        l to segmentDistance(x, y, a, b)
    }.filter { it.second <= reach }.minByOrNull { it.second }?.first

/** The distance from a point to the segment a–b, in canvas fractions. */
fun segmentDistance(x: Float, y: Float, a: Spot, b: Spot): Float {
    val dx = b.x - a.x
    val dy = b.y - a.y
    val len = dx * dx + dy * dy
    val t = if (len == 0f) 0f else (((x - a.x) * dx + (y - a.y) * dy) / len).coerceIn(0f, 1f)
    return hypot((x - (a.x + t * dx)).toDouble(), (y - (a.y + t * dy)).toDouble()).toFloat()
}

/** A dragged node's new place, kept inside the canvas with a margin so its disc is never cut. */
fun clampSpot(x: Float, y: Float, margin: Float = 0.07f): Spot = Spot(x.coerceIn(margin, 1f - margin), y.coerceIn(margin, 1f - margin))
