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
 * Watches the live stream for the owner's orders while the app is open and says when one changes stage: delegated, delivered, failed or
 * done ([notices]; the shell shows a toast with a way in, and a system notification on the «فرمان‌ها» channel when allowed). It knows
 * which refs are the owner's from `GET /work` (and reloads after any `work.created`); what an order had already reached before the app
 * opened is not told again.
 */
class OrderWatcher(
    private val api: Api,
    private val events: SharedFlow<StreamEvent>,
    private val scope: CoroutineScope,
    private val titles: WorkTitles,
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
            load()
            events.collect { e ->
                if (e.type == "work.created") later()
                val n = synchronized(told) { noticeOf(e, orders, told) } ?: return@collect
                out.emit(n)
            }
        }
    }

    fun stop() {
        job?.cancel()
        reload?.cancel()
    }

    /** An order the owner just gave: followed at once, before the list is read again. */
    fun track(w: Work) {
        orders = orders + (w.ref to OrderBrief(w.id, w.ref, w.title, w.company))
        titles.seed(w)
    }

    private fun later() {
        reload?.cancel()
        reload = scope.launch { delay(1_500); load() }
    }

    private suspend fun load() {
        val list = runCatching { api.ownerOrders() }.getOrNull() ?: return
        titles.seed(list)
        synchronized(told) {
            for (w in list) if (w.ref !in orders) told += alreadyReached(w)
        }
        orders = list.associate { it.ref to OrderBrief(it.id, it.ref, it.title, it.company) }
    }

    companion object {
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
