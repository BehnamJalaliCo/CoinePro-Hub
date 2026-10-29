package com.coinepro.hq.core.data

import android.os.SystemClock
import com.coinepro.hq.core.net.ApiException
import java.util.concurrent.ConcurrentHashMap
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** What a screen sees of one query: the last good value (kept while refreshing or after an error). */
data class QueryState<out T>(val data: T? = null, val error: ApiException? = null, val loading: Boolean = true) {
    val refreshing: Boolean get() = loading && data != null
}

/** One cached query. Its [key] encodes every parameter; its [tags] decide which events refresh it. */
class Query<T> internal constructor(
    val key: String,
    val tags: Set<String>,
    private val scope: CoroutineScope,
    private val fetch: suspend () -> T,
    private val hubAway: () -> Boolean = { false },
) {
    private val flow = MutableStateFlow(QueryState<T>())
    val state: StateFlow<QueryState<T>> = flow.asStateFlow()
    private var job: Job? = null
    @Volatile private var fetchedAt = 0L

    internal val observed: Boolean get() = flow.subscriptionCount.value > 0

    /** The last fetch met a hub that was away (502/503/504 or no answer): it is waited out, not shown as an error. */
    internal val waiting: Boolean get() = flow.value.let { it.error?.transient == true || (it.loading && awaiting) }
    @Volatile private var awaiting = false

    fun refresh() {
        if (job?.isActive == true) return
        job = scope.launch {
            flow.update { it.copy(loading = true) }
            try {
                val v = fetch()
                awaiting = false
                fetchedAt = SystemClock.elapsedRealtime()
                flow.value = QueryState(v, null, false)
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiException) {
                // While the hub restarts, a screen keeps what it had (or its skeleton) and the banner says why; no error on every card.
                if (e.transient && hubAway()) { awaiting = true; flow.update { it.copy(error = null, loading = true) } }
                else flow.update { it.copy(error = e, loading = false) }
            } catch (e: Exception) {
                flow.update { it.copy(error = ApiException.unexpected(-1), loading = false) }
            }
        }
    }

    /** Refetches when older than [maxAgeMs] or never fetched. */
    fun ensureFresh(maxAgeMs: Long) {
        if (fetchedAt == 0L || SystemClock.elapsedRealtime() - fetchedAt > maxAgeMs) refresh()
    }

    internal fun markStale() { fetchedAt = 0L }

    /** The hub went away: a transient error already on screen becomes a wait (the skeleton or the last data stays). */
    internal fun hold() {
        if (flow.value.error?.transient == true) { awaiting = true; flow.update { it.copy(error = null, loading = true) } }
    }

    /** Optimistic local edit (e.g. a rating) until the next fetch confirms it. */
    fun set(value: T) { flow.update { it.copy(data = value) } }
}

/** The app's query cache (the Android twin of the web's react-query): one entry per key, shared across
 *  screens, refreshed by holding-stream events and by mutations through [invalidate]. */
class QueryCache(private val scope: CoroutineScope, private val hub: com.coinepro.hq.core.net.HubHealth? = null) {
    private val entries = ConcurrentHashMap<String, Query<*>>()

    init {
        if (hub != null) {
            scope.launch { hub.state.collect { if (it == com.coinepro.hq.core.net.HubState.RESTARTING) entries.values.forEach { q -> q.hold() } } }
            scope.launch { hub.recovered.collect { resume() } }
        }
    }

    @Suppress("UNCHECKED_CAST")
    fun <T> get(key: String, tags: Set<String>, fetch: suspend () -> T): Query<T> =
        entries.getOrPut(key) { Query(key, tags + key.substringBefore(':'), scope, fetch) { hub?.outage == true } } as Query<T>

    /** The hub is back: what waited for it fetches again (on screen now, the rest when next shown). */
    fun resume() {
        for (q in entries.values) if (q.waiting) {
            q.markStale()
            if (q.observed) q.refresh()
        }
    }

    /** Marks every query carrying one of [tags] stale and refetches those on screen now. */
    fun invalidate(vararg tags: String) {
        val t = tags.toSet()
        for (q in entries.values) if (q.tags.any { it in t }) {
            q.markStale()
            if (q.observed) q.refresh()
        }
    }

    /** After the app returns to the foreground: everything on screen refetches. */
    fun refreshObserved() {
        for (q in entries.values) {
            q.markStale()
            if (q.observed) q.refresh()
        }
    }

    fun clear() = entries.clear()
}
