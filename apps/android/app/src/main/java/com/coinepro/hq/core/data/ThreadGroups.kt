package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.DEPT_FA
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.Thread

/** One company's conversations on the messages page: the holding's own first, then each company. */
data class ThreadGroup(val company: String, val holding: Boolean, val threads: List<Thread>) {
    val unread: Int get() = threads.sumOf { it.unread }
}

/**
 * The messages page per company (the owner, 2026-10-31: not one long list).
 *
 * - **The holding first:** the advisor, the overseer, the assistant, the legal counsel and anything else of the holding (or of no company).
 * - **Then each company** in the order the hub lists them: its CEO first, then its managers by department (the departments' usual order,
 *   then by name), then everyone else; inside each rank the latest conversation first.
 * - A company the owner has no conversation with is left out; a thread of a company the app does not know yet gets its own group.
 */
object ThreadGroups {
    /** The holding's counterparts in the order the owner meets them. */
    private val HOLDING_KINDS = listOf("advisor", "overseer", "assistant", "legal")

    private val DEPT_ORDER = DEPT_FA.keys.toList()

    fun group(threads: List<Thread>, companies: List<Company>): List<ThreadGroup> {
        val holdingCode = companies.firstOrNull { it.kind == "holding" }?.code ?: "HQ"
        fun groupOf(t: Thread): String = t.company?.takeIf { it.isNotBlank() } ?: holdingCode
        val by = threads.groupBy(::groupOf)
        val order = listOf(holdingCode) + companies.filter { it.kind != "holding" }.map { it.code } + by.keys.sorted()
        return order.distinct().mapNotNull { code ->
            val list = by[code] ?: return@mapNotNull null
            ThreadGroup(code, code == holdingCode, list.sortedWith(order(code == holdingCode)))
        }
    }

    /** The rank of a thread inside its company: the CEO, the managers, then the rest (the holding's own counterparts first there). */
    fun rank(t: Thread, holding: Boolean): Int = when {
        holding && t.kind in HOLDING_KINDS -> HOLDING_KINDS.indexOf(t.kind)
        t.kind == "ceo" || t.code.endsWith("-CEO") -> 10
        t.kind == "manager" || t.code.endsWith("-MGR") -> 20
        else -> 30
    }

    /** A manager's department from the thread's code ("TY-GROWTH-MGR" → GROWTH), for their order. */
    fun departmentOf(t: Thread): String? = t.code.split('-').takeIf { it.size >= 3 }?.get(1)

    private fun order(holding: Boolean): Comparator<Thread> = compareBy<Thread>(
        { rank(it, holding) },
        { departmentOf(it)?.let { d -> DEPT_ORDER.indexOf(d).let { i -> if (i < 0) DEPT_ORDER.size else i } } ?: -1 },
        { -(instant(it.lastMessageAt)?.toEpochMilli() ?: 0L) },
        { it.titleFa },
    )
}
