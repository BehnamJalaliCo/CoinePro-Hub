package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.DEPT_FA
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.EmployeeRef
import com.coinepro.hq.core.net.Run
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.core.net.Work
import com.coinepro.hq.core.net.WorkEvent
import kotlin.math.roundToInt
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// The owner's orders, followed from the moment they are given to the moment they are closed (contract §4, §5.2, §16.2): the stage on a
// stepper, an honest estimate of how far along it is, who holds it now, when it last moved, and where its output went.

/** The six stages the owner follows. The second is named after whoever took the order (a CEO, or a manager given it directly). */
enum class OrderStage(val fa: String) {
    RECEIVED("ثبت شد"),
    TAKEN("مدیرعامل گرفت"),
    DELEGATED("واگذار شد"),
    WORKING("در حال انجام"),
    DELIVERED("تحویل شد"),
    DONE("تمام"),
}

/** How an order ended when it did not reach its output. */
enum class OrderEnd { NONE, FAILED, CANCELLED }

private val CLOSED = setOf("done", "delivered", "cancelled", "failed")
private val FINISHED = setOf("done", "delivered")

/**
 * One order and what is known under it: its detail (with `chain` and `children`), its children's details (each with its own children),
 * and, on the order's own page, its events and runs and its children's ([kidEvents], [kidRuns]); [deliverables] are the refs of its outputs.
 */
data class OrderTrack(
    val root: Work,
    val kids: List<Work> = emptyList(),
    val events: List<WorkEvent> = emptyList(),
    val runs: List<Run> = emptyList(),
    val kidEvents: Map<String, List<WorkEvent>> = emptyMap(),
    val kidRuns: Map<String, List<Run>> = emptyMap(),
    val deliverables: List<String> = emptyList(),
)

/** Whether the owner gave this work (an order), as opposed to an agent's delegation or a request between departments. */
fun isOwnerOrder(w: Work): Boolean = w.createdBy?.kind == "owner"

/** How it ended, if it ended without its output. */
fun endOf(w: Work): OrderEnd = when (w.status) { "failed" -> OrderEnd.FAILED; "cancelled" -> OrderEnd.CANCELLED; else -> OrderEnd.NONE }

/**
 * The stage an order has reached. Delivered and done are the order's own status; before that it is read from below: somebody under it at
 * work (a child in progress or finished, a progress report) is [OrderStage.WORKING]; children that have not started yet are
 * [OrderStage.DELEGATED]; the order accepted (or a run on it) without children is [OrderStage.TAKEN]; otherwise it waits in the queue. A
 * failed or cancelled order keeps the stage it had reached ([endOf] says how it ended).
 */
fun stageOf(t: OrderTrack): OrderStage {
    val r = t.root
    if (r.status == "done") return OrderStage.DONE
    if (r.status == "delivered") return OrderStage.DELIVERED
    val steps = r.children.map { it.status } + t.kids.flatMap { k -> k.children.map { it.status } }
    val kidsMoving = t.kids.any { it.status in setOf("in_progress", "waiting") || it.status in FINISHED || (it.progressPct ?: 0) > 0 } ||
        steps.any { it == "in_progress" || it in FINISHED }
    val selfMoving = r.children.isEmpty() && ((r.progressPct ?: 0) > 0 || !r.progressNote.isNullOrBlank())
    return when {
        kidsMoving || selfMoving -> OrderStage.WORKING
        r.children.isNotEmpty() -> OrderStage.DELEGATED
        r.status in setOf("in_progress", "waiting") || t.runs.any { it.state in setOf("running", "done") } -> OrderStage.TAKEN
        else -> OrderStage.RECEIVED
    }
}

/** The second stage's name: who took it. */
fun takenFa(w: Work): String = when (w.assignee?.kind) {
    "ceo", null -> "مدیرعامل گرفت"
    "manager" -> "مدیر گرفت"
    else -> "مجری گرفت"
}

/** How far a child is, 0..1, from what is known of it: its status, its own progress report, or its children's statuses. */
private fun fractionOf(w: Work): Double = when {
    w.status in FINISHED -> 1.0
    w.status == "queued" -> 0.0
    w.status in setOf("failed", "cancelled") -> 0.0
    w.progressPct != null -> (w.progressPct / 100.0).coerceIn(0.0, 1.0)
    w.children.isNotEmpty() -> w.children.filter { it.status != "cancelled" }.ifEmpty { w.children }.map { stepFraction(it.status) }.average() * 0.9
    else -> 0.25
}

private fun stepFraction(s: String): Double = when (s) { "done", "delivered" -> 1.0; "in_progress", "waiting" -> 0.3; else -> 0.0 }

/**
 * An estimate of how far the order is, 0..100, from its stage and what is known below it: received 5, taken 15, delegated 25, at work
 * between 30 and 90 by the share of its children done (or its own progress report when nobody is under it), delivered 95, done 100. It
 * moves only when something happens, in steps of 5, so it never pretends to more precision than it has. A failed or cancelled order keeps
 * the value it had reached.
 */
fun progressOf(t: OrderTrack): Int {
    val v = when (stageOf(t)) {
        OrderStage.RECEIVED -> 5.0
        OrderStage.TAKEN -> 15.0
        OrderStage.DELEGATED -> 25.0
        OrderStage.WORKING -> {
            val live = t.root.children.filter { it.status != "cancelled" }
            val frac = when {
                live.isEmpty() && t.root.children.isEmpty() -> (t.root.progressPct ?: 0) / 100.0
                live.isEmpty() -> 0.0
                else -> live.map { s -> t.kids.firstOrNull { it.id == s.id }?.let(::fractionOf) ?: stepFraction(s.status) }.average()
            }
            30.0 + 60.0 * frac.coerceIn(0.0, 1.0)
        }
        OrderStage.DELIVERED -> 95.0
        OrderStage.DONE -> 100.0
    }
    return ((v / 5.0).roundToInt() * 5).coerceIn(0, 100)
}

/**
 * Who holds it now: each open path from the order's assignee down to whoever is working on a piece of it (at most two levels, as
 * delegation is). An order nobody under it holds is with its own assignee; a delivered one waits on the owner (empty).
 */
fun holdersOf(t: OrderTrack): List<List<EmployeeRef>> {
    val r = t.root
    if (r.status in CLOSED) return emptyList()
    val top = r.assignee ?: return emptyList()
    val open = r.children.filter { it.status !in CLOSED }
    if (open.isEmpty()) return listOf(listOf(top))
    return open.flatMap { s ->
        val kid = t.kids.firstOrNull { it.id == s.id }
        val head = listOfNotNull(top, s.assignee ?: kid?.assignee)
        val deeper = kid?.children.orEmpty().filter { it.status !in CLOSED }.mapNotNull { it.assignee }
        if (deeper.isEmpty()) listOf(head) else deeper.map { head + it }
    }.distinctBy { p -> p.joinToString { it.code } }
}

/** When anything last happened on it or under it. */
fun lastActivityOf(t: OrderTrack): String? {
    val times = listOf(t.root.updatedAt, t.root.createdAt) + t.kids.flatMap { listOf(it.updatedAt, it.createdAt) } +
        t.events.map { it.at } + t.kidEvents.values.flatten().map { it.at } +
        (t.runs + t.kidRuns.values.flatten()).flatMap { r -> listOfNotNull(r.startedAt, r.finishedAt) + r.stepsDetail.map { it.at } }
    return times.filter { it.isNotBlank() }.maxByOrNull { instant(it)?.toEpochMilli() ?: 0 }
}

/** Why it failed or was cancelled, in the agent's or the owner's words, from its events. */
fun reasonOf(t: OrderTrack): String? = t.events.lastOrNull { it.kind in setOf("failed", "declined", "cancelled") }?.data?.get("reason").str()

/** An agent's code as a title: "TY-CEO" → «مدیرعامل»; "TY-GROWTH-MGR" → «مدیر رشد»; another code stays a code. */
fun agentTitleOf(code: String?): String? {
    if (code.isNullOrBlank()) return null
    val parts = code.split('-')
    return when {
        code.endsWith("-CEO") -> "مدیرعامل"
        code.endsWith("-MGR") && parts.size >= 3 -> "مدیر " + (DEPT_FA[parts[1]] ?: parts[1])
        else -> null
    }
}

// ------------------------------------------------------------- timeline --
/** One piece of a timeline line: Persian words, or a figure (a ref, a code, a percentage) set Latin. */
data class Part(val text: String, val fig: Boolean = false)

/** One line of an order's timeline: when, what kind of moment (for its icon), and the words. */
data class Moment(val at: String, val kind: String, val parts: List<Part>, val sub: Boolean = false)

private fun w(t: String) = Part(t)
private fun f(t: String) = Part(t, true)

/**
 * The order's life in order, newest first: its events and its children's, the runs on it and under it (started, a few step summaries,
 * finished). Summaries only, never a prompt or a tool's payload (contract §16.2).
 */
fun timelineOf(t: OrderTrack, steps: Int = 3): List<Moment> {
    val out = mutableListOf<Moment>()
    // Everyone on the tree by code, so a line names a person by title ("تحلیلگر سئوی فنی"), with the code beside it.
    val people: Map<String, String> = (listOfNotNull(t.root.assignee) + t.root.children.mapNotNull { it.assignee } + t.kids.mapNotNull { it.assignee } +
        t.kids.flatMap { k -> k.children.mapNotNull { it.assignee } }).associate { it.code to it.titleFa }
    fun title(code: String?): String? = code?.let { agentTitleOf(it) ?: people[it] }
    fun who(code: String): List<Part> = title(code)?.let { listOf(w("$it "), f(code)) } ?: listOf(f(code))
    fun events(ref: String, list: List<WorkEvent>, sub: Boolean) {
        for (e in list) {
            val d = e.data
            val p: List<Part> = when (e.kind) {
                "created" -> if (sub) listOf(w("کار "), f(ref), w(" ساخته شد")) else listOf(w("فرمان ثبت شد و به "), w(title(d["assignee"].str()) ?: "مجری"), w(" رسید"))
                "accepted" -> listOf(w(title(e.actorCode) ?: "مجری"), w(if (sub) " کار " else " فرمان "), f(ref), w(" را گرفت"))
                "delegated" -> buildList {
                    add(w("سپرده شد به "))
                    d["to"].str()?.let { addAll(who(it)) }
                    d["child"].str()?.let { add(w(" با کار ")); add(f(it)) }
                }
                "progress" -> d["pct"].str()?.let { listOf(w("گزارش پیشرفت $it٪ روی "), f(ref)) } ?: listOf(w("گزارش پیشرفت روی "), f(ref))
                "delivered" -> listOf(w(if (sub) "کار " else "فرمان "), f(ref), w(" تحویل شد")) + (d["deliverable"].str()?.let { listOf(w("؛ خروجی "), f(it)) } ?: emptyList())
                "completed" -> listOf(w(if (sub) "کار " else "فرمان "), f(ref), w(" تمام شد"))
                "failed" -> listOf(w("ناموفق: "), w(d["reason"].str() ?: "بی‌دلیل ثبت‌شده"))
                "declined" -> listOf(w("رد شد: "), w(d["reason"].str() ?: ""))
                "cancelled" -> listOf(w("لغو شد"), w(d["reason"].str()?.let { ": $it" } ?: ""))
                "updated" -> listOf(w("ویرایش شد"))
                else -> listOf(w("رویداد "), f(e.kind))
            }
            out += Moment(e.at, e.kind, p, sub)
        }
    }
    fun runs(list: List<Run>, sub: Boolean) {
        for (r in list) {
            r.startedAt?.let { out += Moment(it, "run.started", listOf(w("اجرای ")) + who(r.employee) + w(" شروع شد"), sub) }
            for (s in r.stepsDetail.takeLast(steps)) {
                val summary = s.summaryFa.ifBlank { s.actions.joinToString("، ") { a -> a.tool } }
                out += Moment(s.at, "run.step", listOf(w(title(r.employee) ?: r.employee), w(" · قدم "), w(s.n.toString()), w(": "), w(summary)), true)
            }
            r.finishedAt?.let {
                val how = when (r.state) { "done" -> " تمام شد"; "failed" -> " شکست خورد"; "refused" -> " متوقف شد"; else -> " بسته شد" }
                out += Moment(it, "run.finished:${r.state}", listOf(w("اجرای ")) + who(r.employee) + w(how), sub)
            }
        }
    }
    events(t.root.ref, t.events, sub = false)
    runs(t.runs, sub = false)
    // Everything under it: its children and theirs (the maps hold every descendant's, by ref).
    for (ref in (t.kidEvents.keys + t.kidRuns.keys).distinct()) {
        events(ref, t.kidEvents[ref].orEmpty(), sub = true)
        runs(t.kidRuns[ref].orEmpty(), sub = true)
    }
    if (t.events.none { it.kind == "created" }) out += Moment(t.root.createdAt, "created", listOf(w("فرمان ثبت شد")), false)
    return out.filter { it.at.isNotBlank() }.sortedByDescending { instant(it.at)?.toEpochMilli() ?: 0 }
}

// ---------------------------------------------------------------- notices --
/** A change of stage worth telling the owner about while the app is open. */
enum class NoticeKind { DELEGATED, DELIVERED, FAILED, DONE }

data class OrderNotice(val kind: NoticeKind, val ref: String, val title: String, val company: String?, val workId: String?, val deliverable: String? = null, val to: String? = null) {
    val key: String get() = "$ref:$kind"
    /** One line for the toast and the system notification. */
    val text: String get() = when (kind) {
        NoticeKind.DELEGATED -> "«$title» به ${agentTitleOf(to) ?: to ?: "مجری"} سپرده شد."
        NoticeKind.DELIVERED -> "«$title» تحویل شد" + (deliverable?.let { "؛ خروجی آماده است." } ?: ".")
        NoticeKind.FAILED -> "«$title» ناموفق ماند؛ ببین چرا."
        NoticeKind.DONE -> "«$title» تمام شد."
    }
    val headline: String get() = when (kind) {
        NoticeKind.DELEGATED -> "فرمان $ref واگذار شد"
        NoticeKind.DELIVERED -> "فرمان $ref تحویل شد"
        NoticeKind.FAILED -> "فرمان $ref ناموفق ماند"
        NoticeKind.DONE -> "فرمان $ref تمام شد"
    }
}

/** What the owner knows of an order, enough to word a notice: its ref, id, title and company. */
data class OrderBrief(val id: String, val ref: String, val title: String, val company: String?)

/**
 * The notice a stream event makes for one of the owner's [orders] (by ref), or null: the first delegation, a delivery (`work.updated`
 * with status delivered, or a `deliverable.created` for it), a failure, and done (`work.completed`, or status done). Each kind is told
 * once per order ([told] keeps the keys).
 */
fun noticeOf(e: StreamEvent, orders: Map<String, OrderBrief>, told: MutableSet<String>): OrderNotice? {
    val ref = when {
        e.type.startsWith("work.") -> e.ref
        e.type == "deliverable.created" -> e.data["work"].str()
        else -> null
    } ?: return null
    val o = orders[ref] ?: return null
    val status = e.data["status"].str()
    val n = when {
        e.type == "work.delegated" -> OrderNotice(NoticeKind.DELEGATED, ref, o.title, o.company, o.id, to = e.data["to"].str())
        e.type == "deliverable.created" -> OrderNotice(NoticeKind.DELIVERED, ref, o.title, o.company, o.id, deliverable = e.ref)
        e.type == "work.updated" && status == "delivered" -> OrderNotice(NoticeKind.DELIVERED, ref, o.title, o.company, o.id)
        e.type == "work.updated" && status == "failed" -> OrderNotice(NoticeKind.FAILED, ref, o.title, o.company, o.id)
        e.type == "work.completed" || (e.type == "work.updated" && status == "done") -> OrderNotice(NoticeKind.DONE, ref, o.title, o.company, o.id)
        else -> null
    } ?: return null
    return if (told.add(n.key)) n else null
}

private fun kotlinx.serialization.json.JsonElement?.str(): String? = (this as? JsonPrimitive)?.contentOrNull?.takeIf { it.isNotBlank() }

// -------------------------------------------------------------------- api --
/** The owner's orders, newest first. The API has no filter by creator (contract §4 lists none), so the newest work is read and the
 *  owner's own kept. */
suspend fun Api.ownerOrders(limit: Int = 100): List<Work> = work(limit = limit).items.filter(::isOwnerOrder)

/**
 * One order and what is under it: its detail, its children's details (in parallel), and with [full] its events and runs and its children's.
 * The outputs are named by ref: from its `delivered` events, else by matching its company's outputs to `deliverable_ids` (the API gives
 * the ids, and `GET /deliverables/{ref}` takes refs).
 */
suspend fun Api.orderTrack(id: String, full: Boolean = false): OrderTrack = coroutineScope {
    val root = workOne(id)
    val kids = root.children.map { s -> async { runCatching { workOne(s.id) }.getOrNull() } }
    val needEvents = full || root.status in CLOSED
    val events = if (needEvents) async { workEvents(root.id).items } else null
    val runs = if (full) async { runCatching { workRuns(root.id) }.getOrDefault(emptyList()) } else null
    val kidList = kids.awaitAll().filterNotNull()
    // On its own page, every descendant's events and runs: the children and the grandchildren (delegation stops at depth 2).
    val below = if (full) kidList.map { it.id to it.ref } + kidList.flatMap { k -> k.children.map { it.id to it.ref } } else emptyList()
    val kidEvents = below.map { (id, ref) -> async { ref to runCatching { workEvents(id).items }.getOrDefault(emptyList()) } }.awaitAll().toMap()
    val kidRuns = below.map { (id, ref) -> async { ref to runCatching { workRuns(id) }.getOrDefault(emptyList()) } }.awaitAll().toMap()
    val ev = events?.await().orEmpty()
    val fromEvents = ev.filter { it.kind == "delivered" }.mapNotNull { it.data["deliverable"].str() }
    val outs = if (fromEvents.isNotEmpty() || root.deliverableIds.isEmpty()) fromEvents else try {
        deliverables(company = root.company, limit = 50).items.filter { it.id in root.deliverableIds || it.workId == root.id }.map { it.ref }
    } catch (e: ApiException) {
        emptyList()
    }
    OrderTrack(root, kidList, ev, runs?.await().orEmpty(), kidEvents, kidRuns, outs.distinct())
}
