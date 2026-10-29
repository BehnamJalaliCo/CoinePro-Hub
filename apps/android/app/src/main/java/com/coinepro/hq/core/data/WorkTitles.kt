package com.coinepro.hq.core.data

import com.coinepro.hq.core.net.Work
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** A work item as a line shows it: its ref and title (never its id). */
data class WorkLabel(val id: String?, val ref: String, val title: String)

/** What is known of a work key (an id or a ref): still being looked up, known, or gone (the hub has no such work any more). */
sealed interface LabelState {
    data object Loading : LabelState
    data class Known(val label: WorkLabel) : LabelState
    data object Missing : LabelState
}

/**
 * Work refs and titles for lines that only carry an id or a ref (the live stream, a run's `work`): a small cache shared by the session,
 * filled from every work list the app reads ([seed]) and, for a key it has not seen, from the hub ([fetch]: `GET /work/{id}`, or a ref
 * through the list's search). One lookup per key at a time; a failed one (the hub away) is tried again next time it is asked for.
 * A UUID is never shown to the owner: until it resolves the line shows a skeleton, and if it never does, words without it.
 */
class WorkTitles(private val scope: CoroutineScope, private val fetch: suspend (String) -> Work?) {
    private val state = MutableStateFlow<Map<String, LabelState>>(emptyMap())
    val labels: StateFlow<Map<String, LabelState>> = state.asStateFlow()
    private val inflight = mutableSetOf<String>()

    fun seed(works: List<Work>) {
        if (works.isEmpty()) return
        state.update { m -> trim(m + works.flatMap { w -> WorkLabel(w.id, w.ref, w.title).let { l -> listOf(w.id to LabelState.Known(l), w.ref to LabelState.Known(l)) } }) }
    }

    fun seed(w: Work) = seed(listOf(w))

    /** What is known of [key] now; asks the hub when nothing is. */
    fun get(key: String): LabelState {
        state.value[key]?.let { return it }
        request(key)
        return LabelState.Loading
    }

    fun request(key: String) {
        if (key.isBlank() || state.value[key] is LabelState.Known || state.value[key] == LabelState.Missing) return
        synchronized(inflight) { if (!inflight.add(key)) return }
        scope.launch {
            try {
                val w = fetch(key)
                if (w == null) state.update { trim(it + (key to LabelState.Missing)) }
                else {
                    seed(w)
                    // A ref asked for by id (or the other way round) answers under the key it was asked by too.
                    state.update { trim(it + (key to LabelState.Known(WorkLabel(w.id, w.ref, w.title)))) }
                }
            } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                // The hub away or another failure: nothing is cached, so the next ask tries again.
            } finally {
                synchronized(inflight) { inflight.remove(key) }
            }
        }
    }

    private fun trim(m: Map<String, LabelState>): Map<String, LabelState> = if (m.size <= MAX) m else m.entries.drop(m.size - MAX).associate { it.key to it.value }

    companion object {
        const val MAX = 400
        private val UUID = Regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
        private val WORK_REF = Regex("^W-\\d{3,8}$")
        /** A ref or code a person can read and say: `W-000003`, `O-000041`, `TY-CEO`, `AR-000110`; never an id. */
        private val HUMAN = Regex("^[A-Z][A-Z0-9]{0,5}(?:-[A-Z0-9]{1,12}){1,3}(?:@\\d+)?$")

        fun isUuid(s: String?): Boolean = s != null && UUID.matches(s)
        fun isWorkRef(s: String?): Boolean = s != null && WORK_REF.matches(s)
        /** Whether [s] may be shown as it is: a ref or a code, not an id or a hash. */
        fun isHuman(s: String?): Boolean = s != null && !isUuid(s) && HUMAN.matches(s) && s.count { it.isDigit() } < 12
    }
}
