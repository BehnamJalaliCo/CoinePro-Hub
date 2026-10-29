package com.coinepro.hq.core.net

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow

enum class HubState { OK, RESTARTING }

/**
 * Whether the hub is answering. A restart during a deploy looks like this from the phone: every call answers 502 (the proxy has nobody
 * behind it), 503 or 504, or gets no answer, for a few seconds. One such failure is retried quietly by the API; [THRESHOLD] of them within
 * [WINDOW_MS] mean the hub itself is away: the app then shows one calm banner instead of an error on every card, screens keep what they
 * had (or their skeletons), the app probes with a growing pause ([BACKOFF_MS]), and the first answer brings everything back ([recovered]).
 */
class HubHealth(private val clock: () -> Long = { android.os.SystemClock.elapsedRealtime() }) {
    private val flow = MutableStateFlow(HubState.OK)
    val state: StateFlow<HubState> = flow.asStateFlow()
    private val recoveredFlow = MutableSharedFlow<Long>(extraBufferCapacity = 4)
    /** The hub answers again; the value is how long it was away, in milliseconds. */
    val recovered: SharedFlow<Long> = recoveredFlow.asSharedFlow()
    private val recent = ArrayDeque<Long>()
    @Volatile private var since: Long = 0

    val outage: Boolean get() = flow.value == HubState.RESTARTING

    /** A 502, 503 or 504, or no answer at all. */
    fun transient() = synchronized(this) {
        val now = clock()
        recent.addLast(now)
        while (recent.isNotEmpty() && now - recent.first() > WINDOW_MS) recent.removeFirst()
        if (flow.value == HubState.OK && recent.size >= THRESHOLD) {
            since = recent.first()
            flow.value = HubState.RESTARTING
        }
    }

    /** Any other answer: the hub is there. */
    fun ok() = synchronized(this) {
        recent.clear()
        if (flow.value == HubState.RESTARTING) {
            flow.value = HubState.OK
            recoveredFlow.tryEmit(clock() - since)
        }
    }

    companion object {
        const val WINDOW_MS = 15_000L
        const val THRESHOLD = 4
        /** The pause before each probe while the hub is away. */
        val BACKOFF_MS = longArrayOf(2_000, 3_000, 5_000, 8_000, 13_000, 20_000)

        fun backoff(attempt: Int): Long = BACKOFF_MS[attempt.coerceIn(0, BACKOFF_MS.lastIndex)]
    }
}
