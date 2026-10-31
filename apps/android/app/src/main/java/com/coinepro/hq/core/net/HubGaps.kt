package com.coinepro.hq.core.net

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/** ⟨1.10⟩ The §28 calls a hub may not serve yet: the app may be installed before the hub is deployed with them. */
enum class HubFeature {
    /** `POST /deliverables/file {refs}`; without it the app files one by one. */
    BULK_FILE,
    /** `DELETE /deliverables {refs}`; without it «حذف برای همیشه» is hidden. */
    DELETE_OUTPUTS,
    /** `/companies/{code}/catalogue`; without it the catalogue's entries are hidden. */
    CATALOGUE,
    /** `POST /client/errors`; without it the error log keeps its entries queued for a later app start. */
    CLIENT_ERRORS,
}

/**
 * What this hub turned out not to serve, learnt once per app start (the session's [Api] keeps it): the route answered `405`, or `404`
 * with the framework's own "Not Found" (no Problem of the hub's own, such as "no catalogue yet"). The screens hide what is missing, and
 * the owner never sees an error for it.
 */
class HubGaps {
    private val flow = MutableStateFlow<Set<HubFeature>>(emptySet())
    val missing: StateFlow<Set<HubFeature>> = flow.asStateFlow()

    fun has(f: HubFeature): Boolean = f !in flow.value

    fun mark(f: HubFeature) = flow.update { it + f }
}

/** A route this hub has not got: `405`, or a bare `404` (the framework's "Not Found", or no Problem at all). */
val ApiException.routeMissing: Boolean
    get() = status == 405 || (status == 404 && (detail == null || detail.trim().equals("Not Found", ignoreCase = true)))

/**
 * Runs a §28 call unless this hub is known not to serve [f]; a missing route marks it (once per app start), takes its entry back out of
 * the error log, and answers null. Every other failure is thrown as usual.
 */
suspend fun <T> Api.gated(f: HubFeature, block: suspend Api.() -> T): T? {
    if (!gaps.has(f)) return null
    return try {
        block()
    } catch (e: ApiException) {
        if (!e.routeMissing) throw e
        e.logged?.let { failures?.forget(it) }
        gaps.mark(f)
        null
    }
}
