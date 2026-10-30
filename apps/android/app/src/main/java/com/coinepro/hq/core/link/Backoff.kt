package com.coinepro.hq.core.link

import kotlin.math.min

/**
 * How long the stream waits before it tries again after a drop. Exponential from one second, with equal jitter (half fixed, half random)
 * so the lanes, or a phone and the web, never retry in step after a hub restart. Capped at [FOREGROUND_CAP_MS] while the owner is looking
 * and at [BACKGROUND_CAP_MS] in the background, where every attempt wakes the radio. The wait is cut short when the phone's network comes
 * back or changes, and by the watchdog: a blind retry loop never runs while there is no network at all.
 */
object Backoff {
    const val BASE_MS = 1_000L
    const val FOREGROUND_CAP_MS = 30_000L
    const val BACKGROUND_CAP_MS = 5 * 60_000L

    /** The wait before attempt [attempt] (1 = the first retry after a drop; 0 = now). [random] is in 0..1. */
    fun delayMs(attempt: Int, capMs: Long, random: Double = Math.random()): Long {
        if (attempt <= 0) return 0
        val exp = min(capMs, BASE_MS shl min(attempt - 1, 20))
        val half = exp / 2
        return half + (half * random.coerceIn(0.0, 1.0)).toLong()
    }
}

/**
 * The background link's lines in «خطاخوان» (info level), without flooding it: a phone in a lift drops and reconnects a dozen times an hour.
 * A line with the same title within [windowMs] of the last one written is counted, not written; the next one written says how many were
 * folded into it. A drop is written when the link is back, with how long it was gone and why.
 */
class LinkJournal(private val write: (title: String, detail: String) -> Unit, private val windowMs: Long = 30 * 60_000L) {
    private val lastAt = HashMap<String, Long>()
    private val folded = HashMap<String, Int>()
    private var dropAt: Long? = null
    private var dropWhy: String? = null
    private var connectedOnce = false

    @Synchronized
    fun note(now: Long, title: String, detail: String) {
        val last = lastAt[title]
        if (last != null && now - last < windowMs) {
            folded[title] = (folded[title] ?: 0) + 1
            return
        }
        val n = folded.remove(title) ?: 0
        lastAt[title] = now
        write(title, if (n > 0) "$detail (and $n more like it in the last ${windowMs / 60_000} min)" else detail)
    }

    /** The link dropped; only the first drop of an outage is kept. */
    @Synchronized
    fun dropped(now: Long, why: String) {
        if (dropAt == null) { dropAt = now; dropWhy = why }
    }

    /** The link is live again (or for the first time). */
    fun live(now: Long, resumed: Boolean) {
        val (at, why, first) = synchronized(this) {
            Triple(dropAt, dropWhy, !connectedOnce).also { dropAt = null; dropWhy = null; connectedOnce = true }
        }
        when {
            at != null -> note(now, "link back", "the background link is back after ${(now - at + 500) / 1000} s" + (why?.let { " (dropped: $it)" } ?: "") +
                if (resumed) ", resumed from the last event" else "")
            first -> note(now, "link connected", "the background link is connected")
        }
    }
}
