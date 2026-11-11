package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable

// Contract §42 ⟨1.24⟩: the holding live, one stream the whole app moves with (design/LIVE_VIEWS.md, the 12 P0 views). The seed
// `GET /live/summary` and the five new events (`holding.flow`, `network.link`, `employee.state`, `llm.tick`, and `session.activity`'s
// additive line) plus `server.state`'s additive fields. Same rules as Models.kt: camelCase here, snake_case on the wire; a field the hub
// omits takes its default. Missing data is null (shown «—»), never zero: every count here is nullable.
// §42.5 as built (W12): every dollar is a decimal string of six places (§1: `llm.tick` `equiv_usd`, `day.equiv_usd`, `day.budget_usd`;
// the summary's `tokens.equiv_usd_today`, `tokens.budget_usd`, `companies[].spend_today_usd`), read by [LenientNumber] (a number too);
// `pct` is a number. `seq` is null only while the event bus is down (the app seeds and opens the stream without a resume then). A
// company row is an operating company (the holding is the hub, never a row) and its `working` counts thinking and working. A
// `holding.flow`'s envelope company is the holding's code; its ends are `data.from` / `data.to`. `server.state.reason_fa` is null
// when `reason` is. Slow is 300 ms or more; `llm.tick` windows are clock-aligned; «today» is the UTC day.

// ------------------------------------------------------------------ §42.3 the seed --
@Serializable
data class LivePeople(val working: Int? = null, val thinking: Int? = null, val waiting: Int? = null, val stuck: Int? = null, val total: Int? = null)

@Serializable
data class LiveSessions(val moving: Int? = null, val yourTurn: Int? = null, val stuck: Int? = null, val ready: Int? = null)

@Serializable
data class LiveServers(val online: Int? = null, val offline: Int? = null, val total: Int? = null)

@Serializable
data class LiveTokens(
    val today: Long? = null,
    val effectiveToday: Long? = null,
    val perMin: Long? = null,
    @Serializable(with = LenientNumber::class) val equivUsdToday: Double? = null,
    @Serializable(with = LenientNumber::class) val budgetUsd: Double? = null,
)

/** The kill switches at a glance: the holding's, and the companies whose own switch is engaged. */
@Serializable
data class LiveControl(val holding: Boolean = false, val companiesLocked: List<String> = emptyList())

/** One operating company at a glance (any number of them, owner rule 9; the holding is the hub, not a row). [working]: its people
 *  thinking or working now. `state`: ok · busy · stuck · locked. */
@Serializable
data class LiveCompany(
    val code: String = "",
    val nameFa: String = "",
    val working: Int? = null,
    val total: Int? = null,
    val sessionsOpen: Int? = null,
    val serversOnline: Int? = null,
    val serversTotal: Int? = null,
    @Serializable(with = LenientNumber::class) val spendTodayUsd: Double? = null,
    val lastEventAt: String? = null,
    val state: String? = null,
)

/**
 * `GET /live/summary` (owner): the holding right now. [seq] is the stream's last sequence when it was read, so the app seeds from this and
 * resumes the stream exactly after it (`Last-Event-ID`).
 */
@Serializable
data class LiveSummary(
    val seq: Long? = null,
    val at: String = "",
    val people: LivePeople = LivePeople(),
    val sessions: LiveSessions = LiveSessions(),
    val approvals: Int? = null,
    val urgentUnread: Int? = null,
    val servers: LiveServers = LiveServers(),
    val tokens: LiveTokens = LiveTokens(),
    val control: LiveControl = LiveControl(),
    val companies: List<LiveCompany> = emptyList(),
    /** ⟨1.0.1⟩ A 24-hour series for the pulse's figures, when this hub sends one (Models55.kt). Not a field of the hub's schema
     *  yet, so it is not part of this shape: [Api.liveSummary] reads it beside the summary, as the web does. */
    @kotlinx.serialization.Transient val series: PulseSeries? = null,
)

// ------------------------------------------------------------------ §42.2 the events' data --
/** `holding.flow` (topic `holding`): one thing crossing the holding. `from`/`to`: `hub`, a company code, or `outside`.
 *  `kind`: order · request · accept · deliver · read · playbook · publish. Always through the hub. */
@Serializable
data class HoldingFlow(
    val from: String = "",
    val to: String = "",
    val kind: String = "",
    val via: String = "hub",
    val ref: String? = null,
    val rootRef: String? = null,
    val labelFa: String? = null,
)

/** `network.link` (topic `servers`): a measured road changed `ok` or crossed the slow line. `to`: `hub` or a server. */
@Serializable
data class NetworkLinkEvent(
    val from: String = "",
    val to: String = "",
    val port: Int? = null,
    val ok: Boolean = true,
    @Serializable(with = LenientNumber::class) val ms: Double? = null,
    val errorFa: String? = null,
    val since: String? = null,
    val lastOkAt: String? = null,
)

/** `employee.state` (topic `activity`): idle · thinking · working · waiting · stuck · done (§29.14), coalesced per employee. */
@Serializable
data class EmployeeStateEvent(
    val employee: String = "",
    val company: String? = null,
    val department: String? = null,
    val state: String = "idle",
    val since: String? = null,
    val workRef: String? = null,
    val rootRef: String? = null,
    val stuckFa: String? = null,
)

@Serializable
data class TickTokens(
    val input: Long = 0,
    val output: Long = 0,
    val cacheRead: Long = 0,
    val cacheWrite: Long = 0,
    val thinking: Long = 0,
) {
    val total: Long get() = input + output + cacheRead + cacheWrite + thinking
}

@Serializable
data class TickDay(
    val tokens: Long? = null,
    val effectiveTokens: Long? = null,
    @Serializable(with = LenientNumber::class) val equivUsd: Double? = null,
    @Serializable(with = LenientNumber::class) val budgetUsd: Double? = null,
    @Serializable(with = LenientNumber::class) val pct: Double? = null,
)

/** `llm.tick` (topic `llm`): every 5 s for each company that had a call in the window (nothing when idle). */
@Serializable
data class LlmTick(
    val company: String = "",
    val windowS: Int = 5,
    val calls: Int = 0,
    val inFlight: Int = 0,
    val tokens: TickTokens = TickTokens(),
    @Serializable(with = LenientNumber::class) val equivUsd: Double = 0.0,
    val day: TickDay = TickDay(),
)

/** `server.state` (topic `servers`) with §42.2's additive fields: why a server is offline, since when, its road and its open jobs. */
@Serializable
data class ServerStateEvent(
    val server: String = "",
    val state: String = "",
    val prevState: String? = null,
    val since: String? = null,
    /** no_poll · runner_stopped · server_unreachable · revoked · fallback_public · slow · null */
    val reason: String? = null,
    val reasonFa: String? = null,
    val via: String? = null,
    @Serializable(with = LenientNumber::class) val hubRttMs: Double? = null,
    val openJobs: Int? = null,
)
