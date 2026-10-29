package com.coinepro.hq.core.data

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * ⟨1.7.3⟩ «خوانده‌شده» kept on the phone while the hub cannot keep it (a hub before ⟨1.7.3⟩ answers `POST /deliverables/seen` with
 * 404): output refs and when they were marked seen. Only refs and instants, nothing else. Once the hub sends `seen_at`, the outputs
 * screen sends these up in one call and forgets them.
 */
class SeenStore private constructor(private val prefs: SharedPreferences?) {
    constructor(context: Context) : this(context.getSharedPreferences("hq.seen", Context.MODE_PRIVATE))

    private val state = MutableStateFlow(load())

    /** ref → when it was marked seen (ISO instant). */
    val refs: StateFlow<Map<String, String>> = state.asStateFlow()

    /** Whether the owner was told, once, that «seen» syncs when the hub is updated. */
    var told: Boolean
        get() = prefs?.getBoolean(TOLD, false) ?: toldMemory
        set(v) { if (prefs != null) prefs.edit().putBoolean(TOLD, v).apply() else toldMemory = v }
    private var toldMemory = false

    @Synchronized
    fun mark(refs: Collection<String>, seen: Boolean, at: String = java.time.Instant.now().toString()) {
        val next = state.value.toMutableMap()
        for (r in refs) if (seen) next[r] = next[r] ?: at else next.remove(r)
        save(next)
    }

    @Synchronized
    fun forget(refs: Collection<String>) = save(state.value - refs.toSet())

    private fun save(next: Map<String, String>) {
        state.value = next
        prefs?.edit()?.putStringSet(KEY, next.map { (k, v) -> "$k|$v" }.toSet())?.apply()
    }

    private fun load(): Map<String, String> =
        prefs?.getStringSet(KEY, emptySet()).orEmpty().mapNotNull { s -> s.split('|', limit = 2).takeIf { it.size == 2 }?.let { it[0] to it[1] } }.toMap()

    companion object {
        private const val KEY = "refs"
        private const val TOLD = "told"

        /** A store that lives only in memory (the demo, the tests). */
        fun memory() = SeenStore(null)
    }
}
