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
import com.coinepro.hq.core.net.SessionParticipant
import com.coinepro.hq.core.net.SessionBrief
import com.coinepro.hq.core.net.SessionCard
import com.coinepro.hq.core.net.SessionTask
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
