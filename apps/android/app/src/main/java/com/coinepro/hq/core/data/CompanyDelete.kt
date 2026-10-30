package com.coinepro.hq.core.data

import com.coinepro.hq.core.net.ApiException

/** What came of «حذف شرکت». */
enum class DeleteOutcome {
    /** Gone (`204`). */
    DELETED,
    /** It has done work, delivered something or earned (`409 company_has_history`): it can only be archived. */
    HAS_HISTORY,
    /** The hub has no delete yet (404/405 for the route): archiving is offered instead. */
    NOT_SERVED,
    /** Already gone (`404 not_found` for the company). */
    GONE,
    /** Anything else (the passkey cancelled, a 403, the network): nothing changed, the message says why. */
    FAILED,
}

/**
 * The guard on removing a company made by mistake (proposed `DELETE /companies/{code}` 🔏 `company.delete`): never the holding, only
 * after the owner types the company's code exactly, then the passkey; the hub refuses one with a history and the app offers to archive
 * it (`PATCH /companies/{code}` `status: archived` 🔏 `company.archive`, which the hub serves today).
 */
object CompanyDelete {
    /** What the owner typed is the code (letters only, any case: the code is what they read on the screen). */
    fun matches(typed: String, code: String): Boolean = typed.trim().uppercase() == code.uppercase() && code.isNotBlank()

    fun canConfirm(typed: String, code: String, holding: Boolean, busy: Boolean = false): Boolean = !holding && !busy && matches(typed, code)

    fun outcome(e: ApiException?): DeleteOutcome = when {
        e == null -> DeleteOutcome.DELETED
        e.status == 409 && e.code == "company_has_history" -> DeleteOutcome.HAS_HISTORY
        e.status == 405 -> DeleteOutcome.NOT_SERVED
        e.status == 404 && e.code == "not_found" -> DeleteOutcome.GONE
        e.status == 404 -> DeleteOutcome.NOT_SERVED
        else -> DeleteOutcome.FAILED
    }
}
