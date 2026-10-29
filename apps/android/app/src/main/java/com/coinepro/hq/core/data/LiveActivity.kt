package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.StreamEvent
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/** One company's agents right now, as the live stream tells it. */
data class Pulse(
    /** Runs started and not yet finished (`run.started` … `run.finished`). */
    val runs: Set<String> = emptySet(),
    /** Employees whose activity is `working` (`activity.changed`, a run's steps). */
    val working: Set<String> = emptySet(),
    /** When the last event of this company arrived (the app's clock). */
    val lastAt: Long = 0,
    /** Its recent events worth reading (runs, deliverables, decisions, work, control), newest first. */
    val recent: List<StreamEvent> = emptyList(),
) {
    val busy: Boolean get() = runs.isNotEmpty() || working.isNotEmpty()
    /** Something happened in the last [windowMs]: a short pulse even without a run in progress. */
    fun stirred(now: Long = HqClock.millis(), windowMs: Long = 15_000): Boolean = lastAt > 0 && now - lastAt < windowMs
}

/**
 * What the holding's agents are doing, per company, from the live stream (contract §7, §16): `run.started`, `run.step` and
 * `run.finished` (the runtime's runs), `activity.changed` (an employee working or asleep), and the events the owner reads in a
 * company's activity feed. Screens combine it with `GET /runs?state=running` (what was already running before the app connected).
 */
class LiveActivity(private val clock: () -> Long = { HqClock.millis() }) {
    private val flow = MutableStateFlow<Map<String, Pulse>>(emptyMap())
    val state: StateFlow<Map<String, Pulse>> = flow.asStateFlow()

    fun on(e: StreamEvent) {
        val co = e.company ?: return
        val employee = e.data["employee"].str() ?: e.ref.takeIf { e.type == "activity.changed" }
        flow.update { all ->
            val p = all[co] ?: Pulse()
            var runs = p.runs
            var working = p.working
            when (e.type) {
                "run.started", "run.step" -> {
                    e.ref?.let { runs = runs + it }
                    employee?.let { working = working + it }
                }
                "run.finished" -> {
                    e.ref?.let { runs = runs - it }
                    employee?.let { working = working - it }
                }
                "activity.changed" -> if (employee != null) {
                    working = if (e.data["activity"].str() == "working") working + employee else working - employee
                }
            }
            val readable = FEED.any { e.type.startsWith(it) } && e.type != "run.step"
            val recent = if (readable) (listOf(e.copy(at = e.at.ifBlank { HqClock.now().toString() })) + p.recent).distinctBy { "${it.type}|${it.ref}|${it.at}" }.take(MAX) else p.recent
            all + (co to Pulse(runs, working, clock(), recent))
        }
    }

    /** Forget everything (a new session). */
    fun clear() { flow.value = emptyMap() }

    private fun kotlinx.serialization.json.JsonElement?.str(): String? = (this as? JsonPrimitive)?.contentOrNull

    companion object {
        const val MAX = 30
        /** Event types a company's feed shows. */
        val FEED = listOf("run.", "deliverable.", "decision.", "work.", "control.", "employee.", "budget.", "incident.")
    }
}
