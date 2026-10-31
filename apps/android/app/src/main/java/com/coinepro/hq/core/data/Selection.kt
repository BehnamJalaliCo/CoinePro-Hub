package com.coinepro.hq.core.data

/**
 * ⟨1.10⟩ §28.1 the outputs list's selection mode: a long press starts it with that row, a tap toggles a row, «همه» / «هیچ» select
 * the rows on show or none, back (or the ×) leaves it. Leaving the last row by a tap leaves the mode too; «هیچ» keeps it open, since
 * the owner asked for an empty selection to pick again. What is selected but no longer on show (deleted, filtered away) is dropped.
 */
data class Selection(val refs: Set<String> = emptySet(), val active: Boolean = false) {
    val count: Int get() = refs.size

    operator fun contains(ref: String): Boolean = ref in refs

    /** A long press on [ref]: the mode opens with it (or, already open, toggles it). */
    fun start(ref: String): Selection = if (active) toggle(ref) else Selection(setOf(ref), true)

    /** A tap on [ref] in the mode. */
    fun toggle(ref: String): Selection {
        val next = if (ref in refs) refs - ref else refs + ref
        return if (next.isEmpty()) Selection() else Selection(next, true)
    }

    /** Every row on show. */
    fun all(visible: List<String>): Selection = Selection(refs + visible, true)

    /** None, the mode still open. */
    fun none(): Selection = Selection(emptySet(), true)

    fun exit(): Selection = Selection()

    /** Whether every row on show is selected (the bar then offers «هیچ»). */
    fun allOf(visible: List<String>): Boolean = visible.isNotEmpty() && visible.all { it in refs }

    /** Keeps only what is still on show. */
    fun retain(visible: Collection<String>): Selection = if (!active) this else Selection(refs.intersect(visible.toSet()), true)

    /** The refs in the order the hub seals them (sorted). */
    val sorted: List<String> get() = refs.sorted()
}
