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
    /** ⟨1.10.1⟩ `DELETE /notifications`; without it «حذف» is hidden. */
    DELETE_NOTIFICATIONS,
    /** ⟨1.11⟩ §29.13 `GET /home`; without it the home shows the owner's orders and the cartable, as before. */
    HOME,
    /** ⟨1.11⟩ §29.2 `GET /orders/{ref}/report`; without it an order is followed on its work page only. */
    ORDER_REPORT,
    /** ⟨1.11⟩ §29.4 `POST /orders/preview`; without it the order goes as before and the hub decides. */
    PREVIEW,
    /** ⟨1.11⟩ §29.3 `/rules`; without it «قانون تازه» is hidden. */
    RULES,
    /** ⟨1.11⟩ §29.11 `/groups`; without it the working groups are hidden. */
    GROUPS,
    /** ⟨1.11⟩ §29.12 `/companies/{code}/connections`; without it the connections are hidden. */
    CONNECTIONS,
    /** ⟨1.11⟩ §29.9 `/companies/{code}/readiness`. */
    READINESS,
    /** ⟨1.11⟩ §29.5 `/transcribe/sessions`; without it a long dictation stays on the phone's recogniser. */
    STT_SESSIONS,
    /** ⟨1.12⟩ §30.5 `/line-templates`, `/lines`, `/line-runs`, `/calendar/lines`, `/library`; without them nothing of the production lines shows. */
    LINES,
    /** ⟨1.13⟩ §31: `/kits`, `/lines/{ref}/insights`, the newsletter, SEO, `/campaign-calendar`, ads and `/automations`; without them nothing of the growth screens shows. */
    GROWTH,
    /** ⟨1.14⟩ §32: `/talk/...` and `/voice/...`; without them the talk button is hidden. */
    TALK,
    /** ⟨1.15⟩ §33: usage reports, payments, the revenue board, the leads and the affiliate gaps; without them none of the money screens shows. */
    MONEY,
    /** ⟨1.15⟩ §33.8, §33.9: the company journey and the personas; without them those screens are hidden. */
    JOURNEY,
    /** ⟨1.17⟩ §35: `/sessions`, `/office`, the session routes of an order, `/links` and the canvas; without them the office is built from
     *  the older home and an order's report is its session. */
    SESSIONS,
    /** ⟨1.18⟩ §36.2 `file_ids` on a talk turn: a hub before it refuses the field (`422`, `fields.file_ids`); then the session's
     *  paperclip is hidden for this app start and the files stay in the composer. */
    TALK_FILES,
    /** ⟨1.19⟩ §37 `…/erase/preview` and `…/erase`; without them «پاک کردن برای همیشه» is hidden (an output keeps §28.1's delete). */
    ERASE,
    /** ⟨1.20⟩ §38.3 `/hub/services` and `/hub/jobs/{ref}`; without them the «سرویس‌ها» page says it comes with the next hub update. */
    HUB_SERVICES,
    /** ⟨1.22⟩ §40 `/playbooks…` and `POST /orders/{ref}/playbook`; without them «کارگروه از این جلسه بساز» and the library are hidden. */
    PLAYBOOKS,
    /** ⟨1.23⟩ §41 `GET /orders/{ref}/activity` and `POST /orders/{ref}/nudge`; without them the session's live panel is read from its
     *  report (who it waits for, why it is stuck, when it last moved) and «ادامه بده» is hidden. */
    SESSION_ACTIVITY,
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

/** ⟨1.18⟩ A hub before §36.2 refuses a turn's `file_ids` as an unknown field: `422 validation_failed` with `fields.file_ids` saying
 *  "Extra inputs are not permitted". A hub of ⟨1.18⟩ refusing one file (not the owner's, unknown) says something else: that is its
 *  own plain answer, not a missing feature. */
val ApiException.turnFilesUnknown: Boolean
    get() = status == 422 && fields["file_ids"]?.contains("extra", ignoreCase = true) == true

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
