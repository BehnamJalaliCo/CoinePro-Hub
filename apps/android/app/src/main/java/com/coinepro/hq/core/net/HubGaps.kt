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
    /** ⟨1.24⟩ §42.3 `GET /live/summary`; without it the live views start from what the stream says after the app connects (their figures
     *  read «—» until then) and the stream resumes from its own last event. */
    LIVE,
    /** ⟨2026-11-09⟩ `POST /orders {pace}`, the owner's «با من / خودکار» given when the session is made; without it the order goes
     *  without and the pace is set on it at once (`POST /orders/{ref}/pace`). */
    ORDER_PACE,
    /** ⟨0.19.8⟩ §44.5 `GET`/`POST /deliverables/{ref}/publish`; without them «تأیید و انتشار» is not shown under an output's files. */
    SESSION_PUBLISH,
    /** ⟨0.19.9⟩ §45 `PUT /groups/{key}/members/{code}/publish`; without it the standing word on publishing is not offered. */
    STANDING_PUBLISH,
    /** ⟨1.31⟩ §47.4 `/groups/{key}/members/{code}/topics`; without it «دفتر موضوع‌ها» is not shown. */
    TOPIC_LEDGER,
    /** ⟨1.31⟩ §48 `/companies/{code}/narrator`; without it «گوینده‌ی محتوا» is not shown. */
    NARRATOR,
    /** ⟨1.31⟩ §49 `GET /companies/{code}/best-hour`; without it «بهترین ساعت» is not offered and the fixed hour stands alone. */
    BEST_HOUR,
    /** ⟨1.31⟩ §50 `POST /routines`; without it «روال دائمی» is not offered (a hub before it also sends no `routines` in a report). */
    ROUTINES,
    /** ⟨1.31⟩ §51 `POST /publishes/{job}/cancel`; without it «لغو» is not offered on a scheduled post. */
    PUBLISH_CANCEL,
    /** ⟨1.33⟩ §55.3 `GET /treasury/limits`; without it the limits block (the Claude accounts and today's meter) is hidden and the
     *  older quota card stays. */
    LIMITS,
    /** ⟨1.33⟩ `POST /orders {company}`, the company the owner picked by its mark in the command sheet; a hub that refuses the field
     *  gets the order with that company named in its words. */
    ORDER_COMPANY,
    /** ⟨1.33⟩ §55.2 `GET /publish-desk`; without it «میز انتشار» (its tab beside «خروجی‌ها», the home's line and the page) is hidden. */
    PUBLISH_DESK,
    /** `POST /work/{id}/stop` asked from a session's «الان» bar; without it «نگه دار» is not offered there. */
    WORK_STOP,
    /** `GET /groups/{key}/runs` read for a sealed working group's page; without it the runs' dots and «آخرین نوبت» are left out. */
    GROUP_RUNS,
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

/** A route this hub has not got: `405`, or a bare `404` (the framework's "Not Found", or no Problem at all). ⟨2026-11-11⟩ audit: the
 *  hub's own `not_found` without a detail (a row that is not there) is an answer, never a missing route. */
val ApiException.routeMissing: Boolean
    get() = status == 405 || (status == 404 && (detail?.trim()?.equals("Not Found", ignoreCase = true) == true || code != "not_found"))

/** ⟨1.18⟩ A hub before §36.2 refuses a turn's `file_ids` as an unknown field: `422 validation_failed` with `fields.file_ids` saying
 *  "Extra inputs are not permitted". A hub of ⟨1.18⟩ refusing one file (not the owner's, unknown) says something else: that is its
 *  own plain answer, not a missing feature. */
val ApiException.turnFilesUnknown: Boolean
    get() = status == 422 && fields["file_ids"]?.contains("extra", ignoreCase = true) == true

/** A hub before ⟨2026-11-09⟩ refuses an order's `pace` as an unknown field (`422`, `fields.pace` "Extra inputs are not permitted"). */
val ApiException.orderPaceUnknown: Boolean
    get() = status == 422 && fields["pace"]?.contains("extra", ignoreCase = true) == true

/**
 * ⟨2026-11-09⟩ A new session with the pace the owner chose (the owner: F-0013 went to the end on its own before his «با من» landed).
 * A hub that does not take the pace with the order gets it right after, on the session (`POST /orders/{ref}/pace`), once per app
 * start learnt; the refusal is taken back out of the error log.
 */
suspend fun Api.orderWithPace(text: String, source: String, fileId: String?, route: OrderRoute29?, pace: String, company: String? = null): Order {
    if (gaps.has(HubFeature.ORDER_PACE)) {
        try {
            return order(text, source, fileId, route, pace, company)
        } catch (e: ApiException) {
            if (!e.orderPaceUnknown) throw e
            e.logged?.let { failures?.forget(it) }
            gaps.mark(HubFeature.ORDER_PACE)
        }
    }
    val o = order(text, source, fileId, route, company = company)
    if (o.pace == pace) return o
    return try {
        setPace(o.ref, pace)
        o.copy(pace = pace)
    } catch (e: ApiException) {
        o
    }
}

/** A hub that does not take an order's `company` yet refuses it as an unknown field (`422`, `fields.company` "Extra inputs are not permitted"). */
val ApiException.orderCompanyUnknown: Boolean
    get() = status == 422 && fields["company"]?.contains("extra", ignoreCase = true) == true

/**
 * ⟨1.0.1⟩ C2.1 «باز کن»: the command sheet's order, on the one path (the existing new-order call). One company picked by its mark:
 * the order carries it (`company`). Several: the hub takes one company per order, so the words name them all and the order goes to
 * the holding, which spreads it. None: the holding decides. A hub that does not take `company` gets the order with the company named
 * in its words (learnt once per app start; the refusal is taken back out of the error log).
 */
suspend fun Api.commandOrder(text: String, companies: List<com.coinepro.hq.core.data.CommandCompany>, pace: String): Order {
    val words = text.trim()
    val named = com.coinepro.hq.core.data.commandWords(words, companies.map { it.nameFa })
    if (companies.size == 1 && gaps.has(HubFeature.ORDER_COMPANY)) {
        try {
            return orderWithPace(words, "text", null, null, pace, company = companies.single().code)
        } catch (e: ApiException) {
            if (!e.orderCompanyUnknown) throw e
            e.logged?.let { failures?.forget(it) }
            gaps.mark(HubFeature.ORDER_COMPANY)
        }
    }
    return orderWithPace(named, "text", null, null, pace)
}

/** A hub before §45 refuses an as-is gift's `publish` as an unknown field (`422`, `fields.publish` "Extra inputs are not permitted"). */
val ApiException.applyPublishUnknown: Boolean
    get() = status == 422 && fields["publish"]?.contains("extra", ignoreCase = true) == true

/**
 * ⟨0.19.9⟩ §45 Giving a working group to a company with the owner's standing word on publishing. A hub that does not take the word
 * with the gift gets the gift alone (learnt once per app start; the refusal is taken back out of the error log): each output of that
 * company then waits for his tap, as before.
 */
suspend fun Api.applyWithWord(ref: String, company: String, platform: String?, noteFa: String?, asIs: Boolean, key: String, publish: MemberPublish?): PlaybookApplied {
    if (publish != null && gaps.has(HubFeature.STANDING_PUBLISH)) {
        try {
            return applyPlaybook(ref, company, platform, noteFa, asIs, key, publish)
        } catch (e: ApiException) {
            if (!e.applyPublishUnknown) throw e
            e.logged?.let { failures?.forget(it) }
            gaps.mark(HubFeature.STANDING_PUBLISH)
        }
    }
    return applyPlaybook(ref, company, platform, noteFa, asIs, key)
}

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
