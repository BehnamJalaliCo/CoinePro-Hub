package com.coinepro.hq.core.link

import com.coinepro.hq.core.data.NoticeKind
import com.coinepro.hq.core.data.NotificationGroups
import com.coinepro.hq.core.data.OrderNotice
import com.coinepro.hq.core.data.Refs
import com.coinepro.hq.core.data.agentTitleOf
import com.coinepro.hq.core.net.Notification
import com.coinepro.hq.core.net.StreamEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * The phone's alert channels, each with its own importance (the owner can tune each in the system's settings):
 * - [URGENT] «فوری» — high: heads-up and sound. Urgent notifications and a kill switch someone other than the owner moved.
 * - [CARTABLE] «منتظر تو» — default: sound, no heads-up. Cards waiting for the seal, holds and serious findings (the hub's `decision` level).
 * - [ORDERS] «فرمان‌ها» — default. An order the owner gave delegated, delivered, failed or done (the 0.4.0 channel).
 * - [OUTPUTS] «خروجی‌ها و گزارش‌ها» — low: silent, in the shade only. New outputs and the hub's reports.
 */
enum class AlertChannel(val id: String) { URGENT("urgent"), CARTABLE("cartable"), ORDERS("orders"), OUTPUTS("outputs") }

/** How an alert reads as a toast while the app is open. */
enum class AlertTone { OK, INFO, ERROR }

/**
 * One alert: where it goes ([channel]), what it is about ([key]: the system notification's tag, so the same subject again replaces it and
 * a card decided elsewhere takes it away), two short lines, and the page a tap opens ([route], through [Refs]). [notificationId] is the
 * hub's notification it came from: a tap marks it read, and reading it in the app takes the alert away. [count] is how many times the
 * same alert was raised while it stood unread.
 */
data class Alert(
    val channel: AlertChannel,
    val key: String,
    val title: String,
    val text: String,
    val route: String?,
    val company: String? = null,
    val at: String? = null,
    val notificationId: String? = null,
    val count: Int = 1,
    val tone: AlertTone = AlertTone.INFO,
    /** The toast's button. */
    val action: String = "باز کن",
)

/** Where the alerts go when the app is not on screen: the phone's notifications (`device/AlertNotifier`), or a fake in the tests. */
interface AlertSink {
    /** Whether the phone lets the app show notifications at all (Android 13+ asks; the owner can switch them off). */
    fun allowed(): Boolean
    fun post(alert: Alert)
    fun cancel(key: String)
    /** Hub notifications read in the app: their alerts leave the shade. */
    fun cancelRead(notificationIds: Collection<String>)
    /** «برای ادامه‌ی اعلان‌ها وارد شو»: shown once when the session expires in the background, taken away after sign-in. */
    fun sessionExpired(show: Boolean)
}

/** No notifications (a session built without a phone, the tests' default). */
object NoAlerts : AlertSink {
    override fun allowed() = false
    override fun post(alert: Alert) = Unit
    override fun cancel(key: String) = Unit
    override fun cancelRead(notificationIds: Collection<String>) = Unit
    override fun sessionExpired(show: Boolean) = Unit
}

/** What the alerts read from the hub before they speak (the stream's events carry metadata only, contract §7). */
interface AlertSource {
    /** The newest unread notifications (`GET /notifications?unread=true`; the hub has no `GET /notifications/{id}`). */
    suspend fun unread(limit: Int = 30): List<Notification>
    /** A card's status (`pending` while it waits for the owner), or null when it cannot be read. */
    suspend fun decisionStatus(ref: String): String?
    /** An output's title, company and whether the owner has seen it, or null when it cannot be read. */
    suspend fun deliverable(ref: String): OutputBrief?
}

data class OutputBrief(val ref: String, val title: String, val company: String, val seen: Boolean, val report: Boolean)

/** What an event asks of the alerts, before anything is read from the hub. */
sealed interface Trigger {
    data class Raised(val id: String, val level: String, val linkKind: String?, val linkRef: String?) : Trigger
    data class Switch(val scope: String, val engaged: Boolean, val by: String?, val company: String?) : Trigger
    data class Decided(val ref: String) : Trigger
    data class Output(val ref: String, val work: String?, val root: String?) : Trigger
}

/**
 * The pure rules: which events can become an alert, and the alert each one becomes. No I/O here, so every mapping is a unit test
 * (`AlertsTest`).
 */
object AlertRules {
    /** Levels that reach the phone: urgent, the owner's cards (`decision`) and reports. `info` and `learning` stay in the app. */
    val LEVELS = setOf("urgent", "decision", "report")

    fun trigger(e: StreamEvent): Trigger? = when {
        e.type == "notification.created" -> {
            val level = e.str("level")
            val id = e.ref ?: e.str("id")
            if (level in LEVELS && id != null) Trigger.Raised(id, level!!, e.str("link_kind"), e.str("link_ref")) else null
        }
        e.type == "control.changed" -> {
            // Only the kill switch (`kill_switch`); a deploy freeze, a new company or a mandate is not an alert.
            when (e.str("kill_switch")) {
                "engaged", "released" -> Trigger.Switch(e.str("scope") ?: e.ref ?: "holding", e.str("kill_switch") == "engaged", e.str("by"), e.company)
                else -> null
            }
        }
        e.type == "decision.decided" && e.ref != null -> Trigger.Decided(e.ref)
        e.type == "deliverable.created" && e.ref != null -> Trigger.Output(e.ref, e.str("work"), e.str("root_ref"))
        else -> null
    }

    fun channelOf(level: String): AlertChannel = when (level) {
        "urgent" -> AlertChannel.URGENT
        "decision" -> AlertChannel.CARTABLE
        else -> AlertChannel.OUTPUTS
    }

    /** The tag of a notification's alert: a card by its ref (so deciding it takes the alert away), an output by its ref (so the report
     *  and the output itself are one alert), anything else by what makes it the same alert ([NotificationGroups.key]). */
    fun keyOf(n: Notification): String {
        val kind = n.link?.kind
        val ref = n.link?.ref?.takeIf { it.isNotBlank() }
        return when {
            kind == "decision" && ref != null -> "decision:$ref"
            kind == "deliverable" && ref != null -> "deliverable:$ref"
            else -> "n:" + NotificationGroups.key(n)
        }
    }

    fun ofNotification(n: Notification, count: Int = 1): Alert {
        val channel = channelOf(n.level)
        val body = n.bodyFa.lineSequence().firstOrNull { it.isNotBlank() }?.trim().orEmpty()
        val text = listOfNotNull(if (count > 1) "${faDigits(count.toString())} بار" else null, body.ifBlank { NotificationGroups.category(n) }).joinToString(" · ")
        return Alert(
            channel, keyOf(n), short(n.titleFa, 90), short(text, 160),
            Refs.forLink(n.link?.kind, n.link?.ref) ?: "notifications", n.company, n.createdAt, n.id, count,
            tone = if (channel == AlertChannel.URGENT) AlertTone.ERROR else AlertTone.INFO,
        )
    }

    /** When the hub could not be read: an urgent notification still reaches the phone, in general words. */
    fun ofUnreadable(t: Trigger.Raised): Alert? = if (t.level != "urgent") null else Alert(
        AlertChannel.URGENT, "n:${t.id}", "اعلان فوری تازه از ستاد", "برای دیدن جزئیات، اپ را باز کن.",
        Refs.forLink(t.linkKind, t.linkRef) ?: "notifications", notificationId = t.id, tone = AlertTone.ERROR,
    )

    /** A kill switch moved; the owner's own move is not told back to them. */
    fun ofSwitch(t: Trigger.Switch): Alert? {
        if (t.by == null || t.by == "owner") return null
        val holding = t.scope == "holding"
        val code = t.scope.removePrefix("company:")
        val who = agentTitleOf(t.by) ?: if (t.by.endsWith("-OVERSEER") || t.by.contains("OVERSEER")) "ناظر کل" else t.by
        val title = when {
            holding && t.engaged -> "کل هلدینگ متوقف شد"
            holding -> "هلدینگ دوباره راه افتاد"
            t.engaged -> "شرکت $code متوقف شد"
            else -> "شرکت $code دوباره راه افتاد"
        }
        val text = if (t.engaged) "کلید توقف را $who زد؛ کارها ایستاد تا تو یا او ادامه بدهید." else "کلید توقف را $who برداشت."
        return Alert(
            AlertChannel.URGENT, "control:${t.scope}", title, text, if (holding) "control" else "companies/$code", t.company,
            tone = if (t.engaged) AlertTone.ERROR else AlertTone.INFO,
        )
    }

    fun ofOutput(o: OutputBrief): Alert = Alert(
        AlertChannel.OUTPUTS, "deliverable:${o.ref}", if (o.report) "گزارش تازه" else "خروجی تازه", short(o.title, 120), "outputs/${o.ref}", o.company,
        tone = AlertTone.OK, action = "بخوان",
    )

    fun ofOrder(n: OrderNotice): Alert = Alert(
        AlertChannel.ORDERS, "order:${n.ref}", n.headline, n.text,
        when {
            n.kind == NoticeKind.DELIVERED && n.deliverable != null -> "outputs/${n.deliverable}"
            n.workId != null -> "work/${n.workId}"
            else -> "work/${n.ref}"
        },
        n.company,
        tone = when (n.kind) { NoticeKind.FAILED -> AlertTone.ERROR; NoticeKind.DELEGATED -> AlertTone.INFO; else -> AlertTone.OK },
        action = if (n.kind == NoticeKind.DELIVERED && n.deliverable != null) "خروجی" else "باز کن",
    )

    /** Figures written Persian: the phone's own font draws the notifications, not the app's. */
    fun faDigits(s: String): String = s.map { if (it in '0'..'9') '۰' + (it - '0') else it }.joinToString("")

    private fun short(s: String, max: Int): String = s.trim().replace(Regex("\\s+"), " ").let { if (it.length <= max) it else it.take(max - 1).trimEnd() + "…" }

    private fun StreamEvent.str(k: String): String? = (data[k] as? JsonPrimitive)?.contentOrNull?.takeIf { it.isNotBlank() }
}

/**
 * Turns the stream's events (and the orders tracker's notices) into alerts, one at a time in order. Before an alert is raised, the hub is
 * asked what it is (the events carry metadata only) and whether it still stands: a notification already read (on the web, or marked read
 * here), a card already decided, an output already seen, is not raised. Every event is handled once ([LinkStore.told] keeps the ids, so a
 * replay after a reconnect or a restart repeats nothing); the same alert raised again updates its notification with the count instead of
 * adding one.
 *
 * Who speaks: while the app is on screen (and its shell is listening, [inApp]), the app does, with a toast; otherwise the phone's
 * notifications do ([AlertSink]). Never both. Outputs make no toast: the app's own badge shows them.
 */
class AlertCenter(
    private val scope: CoroutineScope,
    private val source: AlertSource,
    private val store: LinkStore,
    private val sink: AlertSink,
    /** The app is on screen. */
    private val foreground: () -> Boolean,
    /** Marked read in the app and not yet confirmed by the hub. */
    private val readHere: (String) -> Boolean = { false },
    /** Marked seen in the app (⟨1.7.3⟩, before the hub keeps it). */
    private val seenHere: (String) -> Boolean = { false },
    /** A work ref that is one of the owner's orders: its outputs are told by the orders tracker, as the order's delivery. */
    private val ownerOrder: (String) -> Boolean = { false },
    /** Keeps the CPU awake while an event is read and told (the phone may be asleep when a packet wakes it). */
    private val awake: (Long) -> Unit = {},
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val out = MutableSharedFlow<Alert>(extraBufferCapacity = 16)
    /** Alerts the app tells itself (toasts) while it is on screen. */
    val inApp: SharedFlow<Alert> = out.asSharedFlow()

    private sealed interface Item {
        data class Event(val e: StreamEvent) : Item
        data class Order(val n: OrderNotice) : Item
    }

    private var queue = Channel<Item>(Channel.UNLIMITED)
    private var jobs: List<Job> = emptyList()
    private var page: Pair<Long, List<Notification>>? = null
    /** Times each subject was raised while it stands (for «۳ بار»). */
    private val counts = HashMap<String, Int>()
    /** Which subject each hub notification was told under (reading it in the app starts its count again). */
    private val keysById = HashMap<String, String>()
    /** The last kill-switch alert per scope and state (the holding's switch arrives once per company). */
    private val switches = HashMap<String, Long>()
    /** Outputs read from the hub in the last [OUTPUT_WINDOW_MS]: a burst of outputs is not read one by one past [OUTPUT_BUDGET]. */
    private val outputReads = ArrayDeque<Long>()

    val running: Boolean get() = jobs.any { it.isActive }

    fun start(events: Flow<StreamEvent>, notices: Flow<OrderNotice>) {
        if (running) return
        queue = Channel(Channel.UNLIMITED)
        val q = queue
        jobs = listOf(
            scope.launch { events.collect { if (AlertRules.trigger(it) != null) q.trySend(Item.Event(it)) } },
            scope.launch { notices.collect { q.trySend(Item.Order(it)) } },
            scope.launch { for (item in q) runCatching { if (item is Item.Event) handle(item.e) else handle((item as Item.Order).n) } },
        )
    }

    fun stop() {
        jobs.forEach { it.cancel() }
        jobs = emptyList()
        queue.close()
    }

    /** Notifications read in the app: their alerts leave the shade. */
    fun read(ids: Collection<String>) {
        if (ids.isEmpty()) return
        for (id in ids) keysById.remove(id)?.let(counts::remove)
        sink.cancelRead(ids)
    }

    /** One event, start to end (the tests call it directly). */
    suspend fun handle(e: StreamEvent) {
        val t = AlertRules.trigger(e) ?: return
        val evKey = "ev:${e.id}"
        if (e.id.isNotBlank() && store.told(evKey)) return
        awake(15_000)
        val done = when (t) {
            is Trigger.Decided -> { sink.cancel("decision:${t.ref}"); counts.remove("decision:${t.ref}"); true }
            is Trigger.Switch -> {
                val k = "${t.scope}:${t.engaged}"
                val last = switches[k]
                if (last == null || now() - last > SWITCH_WINDOW_MS) {
                    AlertRules.ofSwitch(t)?.let { switches[k] = now(); deliver(it) }
                }
                true
            }
            is Trigger.Raised -> raised(t)
            is Trigger.Output -> output(t)
        }
        if (done && e.id.isNotBlank()) store.remember(evKey)
    }

    suspend fun handle(n: OrderNotice) {
        awake(10_000)
        deliver(AlertRules.ofOrder(n))
    }

    /** A notification raised: read it, and tell it if it still stands. False when the hub could not be read (it may be told on a replay). */
    private suspend fun raised(t: Trigger.Raised): Boolean {
        if (readHere(t.id)) return true
        val n = find(t.id)
        if (n == null) {
            if (page == null) {
                // The hub did not answer: an urgent one is told in general words rather than not at all.
                AlertRules.ofUnreadable(t)?.let { deliver(it); return true }
                return false
            }
            return true // read already, or not shown in the app (held by Khalvat): nothing to tell
        }
        if (n.readAt != null) return true
        if (n.link?.kind == "decision" && n.link.ref != null) {
            val status = source.decisionStatus(n.link.ref)
            if (status != null && status != "pending") return true
        }
        val alert = AlertRules.ofNotification(n)
        if (alert.channel == AlertChannel.OUTPUTS && store.told(alert.key)) return true
        val count = (counts[alert.key] ?: 0) + 1
        counts[alert.key] = count
        keysById[n.id] = alert.key
        deliver(if (count > 1) AlertRules.ofNotification(n, count) else alert)
        return true
    }

    private suspend fun output(t: Trigger.Output): Boolean {
        if ((t.root != null && ownerOrder(t.root)) || (t.work != null && ownerOrder(t.work))) return true
        val key = "deliverable:${t.ref}"
        if (store.told(key) || seenHere(t.ref)) return true
        if (foreground()) return true
        val at = now()
        while (outputReads.isNotEmpty() && at - outputReads.first() > OUTPUT_WINDOW_MS) outputReads.removeFirst()
        if (outputReads.size >= OUTPUT_BUDGET) return true
        outputReads.addLast(at)
        val o = source.deliverable(t.ref) ?: return false
        if (o.seen) return true
        deliver(AlertRules.ofOutput(o))
        return true
    }

    /** The unread page, read again when the id is not in a page older than half a second. */
    private suspend fun find(id: String): Notification? {
        val cached = page
        cached?.second?.firstOrNull { it.id == id }?.let { if (now() - cached.first < PAGE_MS) return it }
        val list = runCatching { source.unread() }.getOrNull()
        if (list == null) { page = null; return null }
        page = now() to list
        return list.firstOrNull { it.id == id }
    }

    private fun deliver(a: Alert) {
        if (a.channel == AlertChannel.OUTPUTS) store.remember(a.key)
        if (foreground() && out.subscriptionCount.value > 0) {
            if (a.channel != AlertChannel.OUTPUTS) out.tryEmit(a)
            return
        }
        if (sink.allowed()) sink.post(a)
    }

    companion object {
        const val PAGE_MS = 500L
        const val SWITCH_WINDOW_MS = 10 * 60_000L
        const val OUTPUT_WINDOW_MS = 5 * 60_000L
        const val OUTPUT_BUDGET = 12
    }
}
