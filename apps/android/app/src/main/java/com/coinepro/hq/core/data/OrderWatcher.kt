package com.coinepro.hq.core.data

import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.core.net.Work
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch

/**
 * Watches the live stream for the owner's orders and says when one changes stage: delegated, delivered, failed or done ([notices]; the
 * alerts make it a toast while the app is open, a notification on the «فرمان‌ها» channel otherwise, `core/link/AlertCenter`). It knows
 * which refs are the owner's from `GET /work` (and reloads after any `work.created`). With a [memory] (the background link), what it told
 * and the orders it knew survive the process: a stage an order it knew reached while the process was gone is told once it is back (the
 * newest [CATCH_UP] of them); an order it meets for the first time does not repeat what it had already reached.
 */
class OrderWatcher(
    private val api: Api,
    private val events: SharedFlow<StreamEvent>,
    private val scope: CoroutineScope,
    private val titles: WorkTitles,
    private val memory: com.coinepro.hq.core.link.LinkStore? = null,
) {
    @Volatile private var orders: Map<String, OrderBrief> = emptyMap()
    private val told = mutableSetOf<String>()
    private val out = MutableSharedFlow<OrderNotice>(extraBufferCapacity = 8)
    val notices: SharedFlow<OrderNotice> = out.asSharedFlow()
    private var job: Job? = null
    private var reload: Job? = null

    fun start() {
        if (job?.isActive == true) return
        job = scope.launch {
            // Listening starts before the list is read, so an event that arrives meanwhile (a replay after a restart) waits for it.
            val pending = kotlinx.coroutines.channels.Channel<StreamEvent>(kotlinx.coroutines.channels.Channel.UNLIMITED)
            launch(start = kotlinx.coroutines.CoroutineStart.UNDISPATCHED) { events.collect { pending.trySend(it) } }
            load()
            for (e in pending) {
                if (e.type == "work.created") later()
                val n = synchronized(told) { noticeOf(e, orders, told) } ?: continue
                remember()
                out.emit(n)
            }
        }
    }

    /** Whether [ref] is one of the owner's orders (its outputs are told as the order's delivery, not as outputs of their own). */
    fun owns(ref: String): Boolean = ref in orders

    fun stop() {
        job?.cancel()
        reload?.cancel()
    }

    /** An order the owner just gave: followed at once, before the list is read again. */
    fun track(w: Work) {
        orders = orders + (w.ref to OrderBrief(w.id, w.ref, w.title, w.company))
        titles.seed(w)
        memory?.let { it.ordersKnown = it.ordersKnown + w.ref }
    }

    private fun later() {
        reload?.cancel()
        reload = scope.launch { delay(1_500); load() }
    }

    private suspend fun load() {
        val list = runCatching { api.ownerOrders() }.getOrNull() ?: return
        titles.seed(list)
        val known = memory?.ordersKnown.orEmpty()
        val missed = mutableListOf<Pair<Work, String>>()
        synchronized(told) {
            if (memory != null && told.isEmpty()) told += memory.ordersTold
            for (w in list) if (w.ref !in orders) {
                if (w.ref in known) {
                    // Known before the process ended: a stage it reached since is told now, once.
                    for (k in alreadyReached(w)) if (told.add(k)) missed += w to k
                } else told += alreadyReached(w)
            }
        }
        orders = list.associate { it.ref to OrderBrief(it.id, it.ref, it.title, it.company) }
        memory?.let { it.ordersKnown = known + list.map(Work::ref) }
        remember()
        // The newest stage of the most recently moved orders; the rest stays told without a word (a long absence is not a flood).
        missed.groupBy { it.first.ref }.values.map { it.last() }.sortedByDescending { it.first.updatedAt }.take(CATCH_UP)
            .forEach { (w, k) -> out.emit(OrderNotice(NoticeKind.valueOf(k.substringAfterLast(':')), w.ref, w.title, w.company, w.id)) }
    }

    private fun remember() {
        memory?.let { m -> m.ordersTold = synchronized(told) { told.toSet() } }
    }

    companion object {
        /** At most this many stages missed while the process was gone are told when it is back. */
        const val CATCH_UP = 3

        /** The notices an order's status already implies (so opening the app never repeats them). */
        fun alreadyReached(w: Work): List<String> {
            val k = listOf(NoticeKind.DELEGATED, NoticeKind.DELIVERED, NoticeKind.FAILED, NoticeKind.DONE)
            val reached = when (w.status) {
                "done" -> k
                "delivered" -> listOf(NoticeKind.DELEGATED, NoticeKind.DELIVERED)
                "failed" -> listOf(NoticeKind.DELEGATED, NoticeKind.FAILED)
                "waiting" -> listOf(NoticeKind.DELEGATED)
                else -> emptyList()
            }
            return reached.map { "${w.ref}:$it" }
        }
    }
}
