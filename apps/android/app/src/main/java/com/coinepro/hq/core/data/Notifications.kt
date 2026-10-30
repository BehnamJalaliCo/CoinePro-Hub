package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.level
import com.coinepro.hq.core.net.Notification
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit

/**
 * Notifications as the owner reads them (contract §6): the same alert raised again and again (the overseer's hourly finding) is one
 * row with its count, what a notification is about comes from its link (a finding is not a decision, even when the hub raises it at
 * the `decision` level), and marking read moves it out of the main list.
 */
object NotificationGroups {
    /** What a notification is about, from its link's kind (the kinds the hub raises: `raise_notification` callers in apps/api). */
    val KIND_FA: Map<String, String> = mapOf(
        "decision" to "تصمیم", "deliverable" to "خروجی", "work" to "کار", "thread" to "پیام", "message" to "یادداشت مشاور",
        "finding" to "یافته‌ی ناظر", "hold" to "نگه‌داشت ناظر", "challenge" to "چالش ناظر", "inquiry" to "استعلام",
        "meeting" to "جلسه", "founding" to "تأسیس", "provision_run" to "ساخت سرور", "server_plan" to "طرح سرور",
        "code_session" to "کارگاه کد", "archive_record" to "بایگانی", "archive_fixity" to "سلامت بایگانی",
        "support_conversation" to "پشتیبانی", "support_queue" to "صف پشتیبانی", "revenue_alert" to "درآمد",
        "substitute" to "بازیکن ذخیره", "employee" to "کارمند", "treasury" to "خزانه", "academy" to "آکادمی",
        "backup" to "پشتیبان‌گیری", "audit" to "دفتر Audit", "device" to "امنیت ورود",
    )

    /** The label on a notification: what it is about; without a link (a learning question), its level. */
    fun category(n: Notification): String = n.link?.kind?.let(KIND_FA::get) ?: level(n.level).fa

    private val NUMBER = Regex("[0-9۰-۹٠-٩]+(?:[.,٫/][0-9۰-۹٠-٩]+)*")
    private val SPACE = Regex("\\s+")

    /** A title with its figures blanked: «disk 90.4%» and «disk 90.6%» an hour later are the same alert. */
    fun normalize(title: String): String = title.trim().replace(SPACE, " ").replace(NUMBER, "#")

    /** Rows that are the same alert: one company, one level, one kind of link, one title (figures aside). A question with choices
     *  is never folded: each one waits for its own answer. */
    fun key(n: Notification): String =
        if (!n.choices.isNullOrEmpty()) "id:${n.id}" else listOf(n.company, n.level, n.link?.kind.orEmpty(), normalize(n.titleFa)).joinToString("|")

    /** [list] (newest first) folded into groups, in the order of each group's newest row; inside a group, newest first. */
    fun group(list: List<Notification>): List<NotificationGroup> {
        val out = LinkedHashMap<String, MutableList<Notification>>()
        for (n in list.sortedByDescending { it.createdAt }) out.getOrPut(key(n)) { mutableListOf() }.add(n)
        return out.map { (k, v) -> NotificationGroup(k, v) }
    }

    /** «۵ بار، آخرین ۴۴ دقیقه پیش» (the figures are drawn in Persian by the text face). */
    fun countLine(g: NotificationGroup, now: Long = com.coinepro.hq.core.format.HqClock.millis()): String = "${g.count} بار، آخرین ${ago(g.latest.createdAt, now)}"

    /**
     * The two lists the screen shows, from the hub's unread and read pages and what the owner marked a moment ago ([marked]: id →
     * when): a marked row leaves «خوانده‌نشده» at once and stands in «خوانده‌شده» with its local time until the hub confirms it.
     */
    fun split(unread: List<Notification>, read: List<Notification>, marked: Map<String, String>): Pair<List<Notification>, List<Notification>> {
        val now = unread.filter { it.readAt == null && it.id !in marked }
        val moved = unread.filter { it.id in marked || it.readAt != null }.map { it.copy(readAt = it.readAt ?: marked.getValue(it.id)) }
        val seen = (moved + read.map { r -> if (r.readAt == null && r.id in marked) r.copy(readAt = marked.getValue(r.id)) else r })
            .filter { it.readAt != null }.distinctBy { it.id }.sortedByDescending { it.createdAt }
        return now to seen
    }
}

/** One row of the list: one notification, or the same alert raised [count] times. */
data class NotificationGroup(val key: String, val items: List<Notification>) {
    val latest: Notification get() = items.first()
    val count: Int get() = items.size
    val ids: List<String> get() = items.map { it.id }
    val folded: Boolean get() = items.size > 1
}

/**
 * Marking notifications read, kept on the hub (`POST /notifications/{id}/read`, `POST /notifications/read-all`; contract §6). The hub
 * has no way to mark one unread again, so a swipe or «همه خوانده شد» waits [graceMs] before it is sent: «برگردان» in that time simply
 * never sends it. Opening a notification sends at once. A screen that closes sends what is waiting ([flush]).
 */
class NotificationReads(
    private val scope: CoroutineScope,
    private val readOne: suspend (String) -> Unit,
    private val readAll: suspend (before: String?, level: String?) -> Unit,
    private val onSent: () -> Unit = {},
    private val graceMs: Long = 5_000,
    private val now: () -> String = { java.time.Instant.now().toString() },
    /** Marked read here (opened, swiped, all): their alerts leave the phone's notifications at once. */
    private val onMarked: (Collection<String>) -> Unit = {},
) {
    private val state = MutableStateFlow<Map<String, String>>(emptyMap())
    private val failed = kotlinx.coroutines.flow.MutableSharedFlow<String>(extraBufferCapacity = 4)
    /** A send the hub refused, in Persian (the rows are unread again). */
    val failures: kotlinx.coroutines.flow.SharedFlow<String> = failed
    /** Marked read on the phone and not yet confirmed by a fresh page from the hub: id → when. */
    val marked: StateFlow<Map<String, String>> = state.asStateFlow()

    private data class Batch(val ids: List<String>, val all: Pair<String?, String?>?, val job: Job)
    private val waiting = LinkedHashMap<Long, Batch>()
    private var seq = 0L

    /** Opened: read now, no undo. */
    fun open(id: String) {
        if (id in state.value) return
        state.value = state.value + (id to now())
        onMarked(listOf(id))
        scope.launch { send(listOf(id), null) }
    }

    /** Marked by a swipe, a group's button or «همه خوانده شد» ([all]: `before` and `level` for one read-all call). Returns the
     *  token [undo] takes back within the grace time. */
    fun mark(ids: List<String>, all: Pair<String?, String?>? = null): Long {
        val fresh = ids.filter { it !in state.value }
        val at = now()
        state.value = state.value + fresh.associateWith { at }
        onMarked(fresh)
        val token = ++seq
        val job = scope.launch {
            delay(graceMs)
            synchronized(waiting) { waiting.remove(token) } ?: return@launch
            send(fresh, all)
        }
        synchronized(waiting) { waiting[token] = Batch(fresh, all, job) }
        return token
    }

    /** «برگردان»: what [token] marked is unread again, and nothing was sent. */
    fun undo(token: Long): Boolean {
        val b = synchronized(waiting) { waiting.remove(token) } ?: return false
        b.job.cancel()
        state.value = state.value - b.ids.toSet()
        return true
    }

    /** Sends everything still waiting (the screen is closing). */
    fun flush() {
        val all = synchronized(waiting) { waiting.values.toList().also { waiting.clear() } }
        for (b in all) {
            b.job.cancel()
            scope.launch { send(b.ids, b.all) }
        }
    }

    /** The hub's fresh page shows these as read: the phone's marks are no longer needed. */
    fun confirmed(readIds: Collection<String>) {
        val waitingIds = synchronized(waiting) { waiting.values.flatMap { it.ids }.toSet() }
        val drop = readIds.filter { it in state.value && it !in waitingIds }
        if (drop.isNotEmpty()) state.value = state.value - drop.toSet()
    }

    private suspend fun send(ids: List<String>, all: Pair<String?, String?>?) {
        try {
            if (all != null) readAll(all.first, all.second)
            else {
                // One call per row (the hub has no bulk read by ids), a few at a time.
                val gate = Semaphore(4)
                kotlinx.coroutines.coroutineScope { ids.map { id -> async { gate.withPermit { readOne(id) } } }.awaitAll() }
            }
            onSent()
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            state.value = state.value - ids.toSet()
            failed.tryEmit((e as? com.coinepro.hq.core.net.ApiException)?.messageFa ?: "علامت خوانده‌شده به هاب نرسید.")
        }
    }
}
