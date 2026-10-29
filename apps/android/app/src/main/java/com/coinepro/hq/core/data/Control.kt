package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.BudgetRowIn
import com.coinepro.hq.core.net.BudgetUse
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.ControlState
import com.coinepro.hq.core.net.Freeze
import com.coinepro.hq.core.net.FreezeOut
import com.coinepro.hq.core.net.KillSwitch
import com.coinepro.hq.core.net.StepUp
import java.time.Instant

// ------------------------------------------------------------------ state --
/** One company (or the holding) as the owner reads it at a glance: its own kill switch, the holding's, and its deploy freezes. */
data class CoState(
    val code: String,
    val holding: Boolean,
    /** Its own switch is engaged. */
    val stopped: Boolean,
    /** The holding's switch is engaged: every company stops with it (contract §9). */
    val holdingStopped: Boolean,
    /** Its own switch as the hub reports it: who changed it, when and why. */
    val switch: KillSwitch?,
    /** The freeze that ends last, while any is active. */
    val freeze: Freeze?,
) {
    val running: Boolean get() = !stopped && !holdingStopped
    val frozen: Boolean get() = freeze != null
    /** The scope the kill switch takes (`holding` or `company:<CODE>`). */
    val scope: String get() = scopeOf(code, holding)
}

fun scopeOf(code: String, holding: Boolean): String = if (holding) "holding" else "company:$code"

/** The state of [code] from `GET /control/state` (who, when, why) and, while that is loading, from the company row itself. */
fun coState(code: String, holding: Boolean, control: ControlState?, company: Company? = null, now: Long = HqClock.millis()): CoState {
    val sw = if (holding) control?.holding else control?.companies?.firstOrNull { it.company == code }
    val stopped = sw?.state?.let { it == "engaged" } ?: (company?.killSwitch == "engaged")
    val holdingStopped = !holding && control?.holding?.state == "engaged"
    val freezes = control?.deployFreezes?.filter { it.company == code && (instant(it.until)?.toEpochMilli() ?: 0) > now }
    val freeze = freezes?.maxByOrNull { it.until }
        ?: company?.deployFreezeUntil?.takeIf { control == null && (instant(it)?.toEpochMilli() ?: 0) > now }?.let { Freeze(code, "", it) }
    return CoState(code, holding, stopped, holdingStopped, sw, freeze)
}

// ------------------------------------------------------------- optimistic --
/** An optimistic change across several cached queries: each [patch] shows the expected state at once and remembers what was
 *  there, so a failed call puts every query back exactly as it was ([rollback]). */
class Optimistic {
    private val undo = mutableListOf<() -> Unit>()

    fun <T> patch(q: Query<T>, change: (T) -> T) {
        val before = q.state.value.data ?: return
        q.set(change(before))
        undo += { q.set(before) }
    }

    fun rollback() {
        for (u in undo.asReversed()) u()
        undo.clear()
    }
}

/** Shows [apply]'s expected state, runs [call], and on any failure rolls the screens back and rethrows (the API has already written
 *  the failure to the error log; the caller says it in Persian). */
suspend fun <R> optimistically(apply: Optimistic.() -> Unit, call: suspend () -> R): R {
    val o = Optimistic().apply(apply)
    try {
        return call()
    } catch (e: Throwable) {
        o.rollback()
        throw e
    }
}

// ---------------------------------------------------------------- actions --
/**
 * The owner's control over the holding and every company (contract §9, OPERATING_MODEL §1.12), with the screens updated at once:
 *
 * - [stop] engages a kill switch with no step-up (speed matters); [resume] releases it with the passkey (`kill_switch.release` on
 *   the scope). A switch the owner engaged is released only by the owner.
 * - [freeze] closes a company's deploys for a span; [unfreeze] opens them with the passkey (`deploy_freeze.lift` on `company:<CODE>`).
 * - [setMonthBudget] changes a month envelope through `PUT /budgets`, sealed on the SHA-256 of the exact body (`budgets.update`).
 *
 * Each action patches the cached `control`, `companies`, `company:<CODE>` and budget queries first and rolls them back if the hub
 * refuses; a step-up comes before anything changes on screen, so a cancelled passkey changes nothing.
 */
class CompanyControl(private val api: Api, private val cache: QueryCache, private val stepUp: StepUp, private val now: () -> Instant = { HqClock.now() }) {
    private val control get() = cache.get("control", setOf("control")) { api.control() }
    private val companies get() = cache.get("companies", setOf("companies")) { api.companies() }
    private fun company(code: String) = cache.get("company:$code", setOf("companies")) { api.company(code) }
    private val budgets get() = cache.get("treasury:budgets", setOf("treasury")) { api.budgets() }

    suspend fun stop(code: String, holding: Boolean, reason: String): ControlState {
        val scope = scopeOf(code, holding)
        val out = optimistically({ switch(code, holding, true, reason) }) { api.engage(scope, reason) }
        settle(out)
        return out
    }

    suspend fun resume(code: String, holding: Boolean, reason: String): ControlState {
        val scope = scopeOf(code, holding)
        val token = stepUp("kill_switch.release", scope)
        val out = optimistically({ switch(code, holding, false, reason) }) { api.killSwitch(scope, false, reason, token) }
        settle(out)
        return out
    }

    suspend fun freeze(code: String, hours: Int, reason: String): FreezeOut {
        val until = now().plusSeconds(hours * 3600L).toString()
        val out = optimistically({ freezeTo(code, until, reason) }) { api.freezeDeploys(code, until, reason) }
        cache.invalidate("control", "companies")
        return out
    }

    suspend fun unfreeze(code: String, reason: String): FreezeOut {
        val token = stepUp("deploy_freeze.lift", "company:$code")
        val out = optimistically({ freezeTo(code, null, reason) }) { api.liftFreezes(code, reason, { _, _ -> token }, now()) }
        cache.invalidate("control", "companies")
        return out
    }

    /** One envelope: the company's (or the holding's) month budget in tokens and, when set, dollars. */
    suspend fun setMonthBudget(code: String, holding: Boolean, tokenLimit: Long?, usdLimit: String?): List<BudgetUse> {
        val row = BudgetRowIn(code, if (holding) "holding" else "company", code, "month", tokenLimit, usdLimit)
        val out = optimistically({
            patch(budgets) { list ->
                val hit = list.any { it.company == code && it.scopeType == row.scopeType && it.period == "month" }
                val next = BudgetUse(code, row.scopeType, code, "month", tokenLimit = tokenLimit, usdLimit = usdLimit)
                if (hit) list.map { b -> if (b.company == code && b.scopeType == row.scopeType && b.period == "month") b.copy(tokenLimit = tokenLimit, usdLimit = usdLimit, pct = pctOf(b.tokensUsed, tokenLimit, b.usdUsed, usdLimit)) else b }
                else list + next
            }
        }) { api.putBudgets(listOf(row)) { target -> stepUp("budgets.update", target) } }
        budgets.set(out)
        cache.invalidate("treasury", "hiring")
        return out
    }

    // The expected state of a switch, on every query that shows it.
    private fun Optimistic.switch(code: String, holding: Boolean, engaged: Boolean, reason: String) {
        val state = if (engaged) "engaged" else "released"
        val at = now().toString()
        patch(control) { c ->
            val k = KillSwitch(scopeOf(code, holding), code, state, reason, at, "owner")
            if (holding) c.copy(holding = k) else c.copy(companies = c.companies.map { if (it.company == code) k else it }.let { l -> if (l.any { it.company == code }) l else l + k })
        }
        patch(companies) { l -> l.map { if (it.code == code) it.copy(killSwitch = state) else it } }
        patch(company(code)) { it.copy(killSwitch = state) }
    }

    private fun Optimistic.freezeTo(code: String, until: String?, reason: String) {
        patch(control) { c ->
            val rest = c.deployFreezes.filter { it.company != code }
            c.copy(deployFreezes = if (until != null) rest + Freeze(code, reason, until, "owner") else rest)
        }
        patch(companies) { l -> l.map { if (it.code == code) it.copy(deployFreezeUntil = until) else it } }
        patch(company(code)) { it.copy(deployFreezeUntil = until) }
    }

    /** The hub's answer is the truth: the control query takes it whole; the company rows and the switch's history refetch. */
    private fun settle(out: ControlState) {
        control.set(out)
        cache.invalidate("companies", "control")
    }

    companion object {
        fun pctOf(tokens: Long, tokenLimit: Long?, usd: String, usdLimit: String?): Double? {
            val p = listOfNotNull(
                tokenLimit?.takeIf { it > 0 }?.let { 100.0 * tokens / it },
                usdLimit?.toDoubleOrNull()?.takeIf { it > 0 }?.let { 100.0 * (usd.toDoubleOrNull() ?: 0.0) / it },
            )
            return p.maxOrNull()?.let { Math.round(it * 10) / 10.0 }
        }
    }
}
