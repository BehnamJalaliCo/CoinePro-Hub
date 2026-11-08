package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable

// Contract §41 ⟨1.23⟩: the session shows its work live and never stalls. Who is working on the order's tree right now (each at its step,
// doing what, in plain Persian), the last lines of the work (newest last), and, when nobody works, why: the owner is asked, it is stuck
// (with the fix), or it is quiet since a time. Same rules as Models.kt: camelCase here, snake_case on the wire; a field the hub omits
// takes its default.

/** Someone working on a work of the order's tree now: who, of which company, on which work, since when, at which step, doing what. */
@Serializable
data class SessionWorker(
    val whoFa: String = "",
    val companyFa: String? = null,
    val workTitleFa: String = "",
    val startedAt: String = "",
    val step: Int = 0,
    val doingFa: String = "",
)

/**
 * One line of the work: a run's step in plain Persian («سایت pro-chart.com را خواند»، «از ChatGPT پرسید»), never a tool key or a ref.
 * ⟨1.24⟩ §42.2 additive: [id] (run id + step n: a step's end updates its own line), [kind] (start · step · end · wake · ask · join · task ·
 * memory), [state] (running · done · failed), [taskN] (the plan's task a `task` line ticked) and the [company] it happened in.
 */
@Serializable
data class ActivityLine(
    val at: String = "",
    val whoFa: String = "",
    val textFa: String = "",
    val id: String? = null,
    val company: String? = null,
    val kind: String? = null,
    val state: String? = null,
    val taskN: Int? = null,
)

/**
 * `GET /orders/{ref}/activity` and `POST /orders/{ref}/nudge`: the session's work right now. [last] holds at most 30 lines, newest last.
 * When [working] is empty: [waitingFa] (the owner is asked), else [stuckFa] (why, and what fixes it), else quiet since [idleSince].
 */
@Serializable
data class SessionActivity(
    val working: List<SessionWorker> = emptyList(),
    val last: List<ActivityLine> = emptyList(),
    val idleSince: String? = null,
    val waitingFa: String? = null,
    val stuckFa: String? = null,
)
