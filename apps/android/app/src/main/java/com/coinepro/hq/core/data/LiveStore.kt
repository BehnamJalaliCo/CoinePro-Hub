package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.EmployeeStateEvent
import com.coinepro.hq.core.net.HoldingFlow
import com.coinepro.hq.core.net.LiveCompany
import com.coinepro.hq.core.net.LivePeople
import com.coinepro.hq.core.net.LiveServers
import com.coinepro.hq.core.net.LiveSessions
import com.coinepro.hq.core.net.LiveSummary
import com.coinepro.hq.core.net.LlmTick
import com.coinepro.hq.core.net.NetworkLinkEvent
import com.coinepro.hq.core.net.ServerStateEvent
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.core.net.Totals
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// Contract §42 ⟨1.24⟩, design/LIVE_VIEWS.md K-2: the live store. Seeded from `GET /live/summary` (which carries the stream's sequence),
// then every stream event after that sequence is applied once (de-duplicated by its id) by one small reducer per view: the heartbeat
// (GL-1), the kill switches (GL-2), the office pulse (OF-1), the token meter (MO-1), each company's card (CO-1), each person's state
// (PE-1), the servers, links and flows of the network map (HM-1, HM-2, HM-3). Pure functions over an immutable [LiveState]: the unit
// tests read them, and a screen never infers anything from silence (a server is offline only when the hub says so). Companies are data:
// nothing here knows how many there are (owner rule 9). Missing data stays null («—»), never zero.

object LiveRules {
    /** GL-1: no byte from the hub for this long and the figures on screen are old («قدیمی»). */
    const val STALE_MS = 45_000L
    /** GL-1: the live dot breathes at most once in this long. */
    const val BEAT_MS = 2_000L
    /** Rule 7: more than this many events while the app was away and a chip says so instead of replaying them. */
    const val MISSED_CHIP = 20
    /** Event ids remembered for de-duplication. */
    const val SEEN_MAX = 4_096
    /** The flows the map keeps (its particles, the table's flows per hour). */
    const val FLOWS_MAX = 120
    /** A tick's window counts toward «توکن در دقیقه» this long. */
    const val PER_MIN_MS = 60_000L
    /** A company's calls in flight are believed this long after its last tick. */
    const val IN_FLIGHT_MS = 12_000L
    /** An event older than the return by more than this is a replay of what happened while away (no motion). */
    const val REPLAY_SKEW_MS = 2_000L
    /** The live store seeds itself again this often while the app is on screen (counts built from deltas never drift for long). */
    const val RESEED_MS = 5 * 60_000L
    /** A reconnected link shows positive this long (HM-3). */
    const val RECONNECTED_MS = 2_000L
    /** A failed job leaves its red tick on the server this long (§5). */
    const val FAILED_TICK_MS = 4_000L
}

// ------------------------------------------------------------------ GL-1 the heartbeat --
/** What the live dot says: live, reconnecting, old (stale: frozen figures), or no network at all. */
enum class Beat { LIVE, RECONNECTING, STALE, OFFLINE }

/** A frozen view must never look calm: particles stop and the map says «قدیمی». */
val Beat.frozen: Boolean get() = this == Beat.STALE || this == Beat.OFFLINE

/**
 * The heartbeat from the stream's state: live while every lane is; with no network, «بی‌اتصال»; [downSince] (when it stopped being live,
 * or null before it ever was) older than [LiveRules.STALE_MS], «قدیمی»; otherwise it is reconnecting.
 */
fun heartbeatOf(state: StreamState, downSince: Long?, online: Boolean, now: Long): Beat = when {
    state == StreamState.LIVE -> Beat.LIVE
    !online -> Beat.OFFLINE
    downSince != null && now - downSince >= LiveRules.STALE_MS -> Beat.STALE
    else -> Beat.RECONNECTING
}

/** «۴۵ ثانیه»، «۲ دقیقه»، «۳ ساعت» — an age in Persian digits (prose). */
fun ageFa(ms: Long): String {
    val s = (ms / 1000).coerceAtLeast(0)
    return when {
        s < 60 -> "${faNum(s.toInt())} ثانیه"
        s < 3_600 -> "${faNum((s / 60).toInt())} دقیقه"
        s < 86_400 -> "${faNum((s / 3_600).toInt())} ساعت"
        else -> "${faNum((s / 86_400).toInt())} روز"
    }
}

/** «زنده» · «در حال وصل» · «قدیمی · ۲ دقیقه» · «بی‌اتصال». */
fun heartbeatFa(b: Beat, downSince: Long?, now: Long): String = when (b) {
    Beat.LIVE -> "زنده"
    Beat.RECONNECTING -> "در حال وصل"
    Beat.STALE -> "قدیمی" + (downSince?.let { " · " + ageFa(now - it) } ?: "")
    Beat.OFFLINE -> "بی‌اتصال"
}

// ------------------------------------------------------------------ the state --
/** One person's live state (PE-1). */
data class EmployeeLive(val employee: String, val company: String?, val state: String, val since: String?, val stuckFa: String?, val workRef: String?)

/** One server as the hub last said (HM-1, HM-3). [busy]: jobs running on it now (M7); [failedAt]: a job just failed (a red tick for 4 s);
 *  [backAt]: it came back online (the link positive for 2 s). */
data class ServerLive(
    val id: String,
    val company: String?,
    val state: String,
    val prevState: String? = null,
    val since: String? = null,
    val reason: String? = null,
    val reasonFa: String? = null,
    val via: String? = null,
    val hubRttMs: Double? = null,
    val openJobs: Int? = null,
    val busy: Int = 0,
    val failedAt: Long? = null,
    val backAt: Long? = null,
)

/** A measured road the hub reported failing or slow (`network.link`); server↔server roads show only while failing. */
data class LinkLive(val from: String, val to: String, val port: Int?, val ok: Boolean, val ms: Double?, val errorFa: String?, val since: String?, val lastOkAt: String?)

/**
 * One thing that crossed the holding (HM-2): `holding.flow` (order, request, accept, deliver, read, playbook, publish) or a job on a server
 * (`job` hub → server, `job_done` / `job_failed` server → hub). [n] numbers them in arrival order (the map flies each new one once);
 * [quiet]: it happened while the app was away or is a replay (applied, never flown).
 */
data class FlowLive(
    val n: Long,
    val id: String,
    val at: Long,
    val from: String,
    val to: String,
    val kind: String,
    val labelFa: String? = null,
    val ref: String? = null,
    val quiet: Boolean = false,
) {
    /** The owner's own act (gold, the hub's ceremony). */
    val owner: Boolean get() = kind == "order" || kind == "playbook"
}

/** Today's tokens by kind (MO-1's four segments): input, output, cache (read and write), thinking. */
data class TokenKinds(val input: Long = 0, val output: Long = 0, val cache: Long = 0, val thinking: Long = 0) {
    val total: Long get() = input + output + cache + thinking
    operator fun plus(o: TokenKinds) = TokenKinds(input + o.input, output + o.output, cache + o.cache, thinking + o.thinking)
}

/** MO-1: today's tokens and dollars (the seed plus every tick since), the kinds, the last minute's ticks and the calls in flight. */
data class TokensLive(
    val today: Long? = null,
    val effectiveToday: Long? = null,
    val usdToday: Double? = null,
    val budgetUsd: Double? = null,
    val seedPerMin: Long? = null,
    val seededAt: Long? = null,
    val kinds: TokenKinds? = null,
    /** (when, the window's tokens) of the last minute's ticks. */
    val ticks: List<Pair<Long, Long>> = emptyList(),
    /** Calls in flight per company, and when its tick said so. */
    val inFlight: Map<String, Pair<Int, Long>> = emptyMap(),
)

/** GL-2: the holding's switch (since when, by whom) and the companies locked (since when). */
data class ControlLive(val holding: Boolean = false, val holdingSince: String? = null, val holdingBy: String? = null, val locked: Map<String, String?> = emptyMap())

/** CO-1: one company right now. */
data class CompanyLive(
    val code: String,
    val nameFa: String = "",
    val working: Int? = null,
    val total: Int? = null,
    val sessionsOpen: Int? = null,
    val serversOnline: Int? = null,
    val serversTotal: Int? = null,
    val spendTodayUsd: Double? = null,
    val budgetUsd: Double? = null,
    val lastEventAt: Long? = null,
    val state: String? = null,
    /** Flows in or out of it in the last hour (the table's column). */
    val flowsHour: Int = 0,
)

/** Everything the live views read, as one immutable value. */
data class LiveState(
    val seq: Long? = null,
    val seeded: Boolean = false,
    val seededAt: Long? = null,
    val people: LivePeople = LivePeople(),
    val sessions: LiveSessions = LiveSessions(),
    val approvals: Int? = null,
    val urgentUnread: Int? = null,
    val servers: LiveServers = LiveServers(),
    val tokens: TokensLive = TokensLive(),
    val control: ControlLive = ControlLive(),
    val companies: Map<String, CompanyLive> = emptyMap(),
    val employees: Map<String, EmployeeLive> = emptyMap(),
    val serverStates: Map<String, ServerLive> = emptyMap(),
    val links: Map<String, LinkLive> = emptyMap(),
    val badges: Map<String, String> = emptyMap(),
    val flows: List<FlowLive> = emptyList(),
    val flowN: Long = 0,
    /** Events applied since the store started, and when the last one was (the live dot's breath). */
    val applied: Long = 0,
    val lastEventAt: Long? = null,
    /** Rule 7: the app on screen, since when, and the events applied while it was away (or replayed on return). */
    val foreground: Boolean = false,
    val visibleSince: Long? = null,
    val missed: Int = 0,
)

// ------------------------------------------------------------------ small helpers --
private fun Int?.add(d: Int): Int? = this?.let { (it + d).coerceAtLeast(0) }

private fun JsonElement?.text(): String? = (this as? JsonPrimitive)?.contentOrNull

private fun <T> decode(e: StreamEvent, s: KSerializer<T>): T? = runCatching { Api.json.decodeFromJsonElement(s, e.data) }.getOrNull()

/** An ISO time as epoch ms (null when it is not one). */
fun isoMs(iso: String?): Long? = if (iso.isNullOrBlank()) null else
    runCatching { java.time.OffsetDateTime.parse(iso).toInstant().toEpochMilli() }.getOrNull() ?: runCatching { java.time.Instant.parse(iso).toEpochMilli() }.getOrNull()

/** The people states the pulse counts (idle and done are not counted). */
private val COUNTED = setOf("working", "thinking", "waiting", "stuck")
/** «الان کار میکنند»: a model thinks or a tool works. */
fun busyState(s: String?): Boolean = s == "working" || s == "thinking"

private fun LivePeople.bump(state: String?, d: Int): LivePeople = when (state) {
    "working" -> copy(working = working.add(d))
    "thinking" -> copy(thinking = thinking.add(d))
    "waiting" -> copy(waiting = waiting.add(d))
    "stuck" -> copy(stuck = stuck.add(d))
    else -> this
}

private fun LiveSessions.bump(badge: String?, d: Int): LiveSessions = when (badge) {
    "moving" -> copy(moving = moving.add(d))
    "your_turn" -> copy(yourTurn = yourTurn.add(d))
    "stuck" -> copy(stuck = stuck.add(d))
    "ready" -> copy(ready = ready.add(d))
    else -> this
}

private fun LiveState.company(code: String): CompanyLive = companies[code] ?: CompanyLive(code)

private fun LiveState.withCompany(c: CompanyLive): LiveState = copy(companies = companies + (c.code to c))

// ------------------------------------------------------------------ the seed --
/**
 * The state seeded from `GET /live/summary` (and today's treasury totals for the meter's kinds, when read): the counts as the hub says
 * them now. What the store learnt from events about single people, servers, badges and flows is kept (it is still true); the counts are
 * the hub's again, so whatever a delta missed is mended.
 */
fun seeded(prev: LiveState, s: LiveSummary, day: Totals?, now: Long): LiveState {
    val companies = LinkedHashMap<String, CompanyLive>()
    for (c in s.companies) {
        if (c.code.isBlank()) continue
        val old = prev.companies[c.code]
        companies[c.code] = CompanyLive(
            c.code, c.nameFa, c.working, c.total, c.sessionsOpen, c.serversOnline, c.serversTotal, c.spendTodayUsd,
            old?.budgetUsd, isoMs(c.lastEventAt) ?: old?.lastEventAt, c.state, old?.flowsHour ?: 0,
        )
    }
    // A company the stream told of that the summary leaves out stays (companies are data; the summary is not the only word).
    for ((k, v) in prev.companies) if (k !in companies) companies[k] = v
    val kinds = day?.let { TokenKinds(it.inputTokens, it.outputTokens, it.cacheReadTokens + it.cacheWriteTokens, it.thinkingTokens) }
    val locked = s.control.companiesLocked.associateWith { prev.control.locked[it] }
    return prev.copy(
        seq = s.seq ?: prev.seq,
        seeded = true,
        seededAt = now,
        people = s.people,
        sessions = s.sessions,
        approvals = s.approvals,
        urgentUnread = s.urgentUnread,
        servers = s.servers,
        tokens = TokensLive(
            today = s.tokens.today, effectiveToday = s.tokens.effectiveToday, usdToday = s.tokens.equivUsdToday, budgetUsd = s.tokens.budgetUsd,
            seedPerMin = s.tokens.perMin, seededAt = now, kinds = kinds ?: prev.tokens.kinds, ticks = prev.tokens.ticks, inFlight = prev.tokens.inFlight,
        ),
        control = ControlLive(
            holding = s.control.holding,
            holdingSince = if (s.control.holding) prev.control.holdingSince else null,
            holdingBy = if (s.control.holding) prev.control.holdingBy else null,
            locked = locked,
        ),
        companies = companies,
    )
}

// ------------------------------------------------------------------ the reducers, one per view --
/** PE-1, OF-1, CO-1: a person's state changed; the counts move from the old state to the new (an unknown person was idle). */
fun reducePeople(s: LiveState, e: StreamEvent): LiveState {
    if (e.type != "employee.state") return s
    val ev = decode(e, EmployeeStateEvent.serializer()) ?: return s
    val who = ev.employee.ifBlank { e.ref.orEmpty() }.ifBlank { return s }
    val co = ev.company ?: e.company
    val prev = s.employees[who]?.state ?: "idle"
    val next = ev.state
    var out = s.copy(
        employees = s.employees + (who to EmployeeLive(who, co, next, ev.since ?: e.at, ev.stuckFa, ev.workRef)),
        people = if (prev == next) s.people else s.people.bump(prev, -1).bump(next, +1),
    )
    if (co != null && busyState(prev) != busyState(next)) {
        val c = out.company(co)
        out = out.withCompany(c.copy(working = c.working.add(if (busyState(next)) 1 else -1)))
    }
    return out
}

/** OF-1, SS-1: a session moved to another badge (`session.updated {ref, badge}`). */
fun reduceSessions(s: LiveState, e: StreamEvent): LiveState {
    if (e.type != "session.updated") return s
    val ref = e.data["ref"].text()?.ifBlank { null } ?: e.ref?.ifBlank { null } ?: return s
    val badge = e.data["badge"].text()?.ifBlank { null } ?: return s
    val prev = s.badges[ref]
    if (prev == badge) return s
    return s.copy(badges = s.badges + (ref to badge), sessions = s.sessions.bump(prev, -1).bump(badge, +1))
}

/** OF-1 «منتظر تو» and NO-1: a card arrived or was decided; an urgent notification arrived. */
fun reduceCounts(s: LiveState, e: StreamEvent): LiveState = when (e.type) {
    "decision.created" -> s.copy(approvals = s.approvals.add(1))
    "decision.decided" -> s.copy(approvals = s.approvals.add(-1))
    "notification.created" -> if (e.data["level"].text() == "urgent") s.copy(urgentUnread = s.urgentUnread.add(1)) else s
    else -> s
}

/** MO-1, CO-1: a company's tick of the last five seconds: tokens by kind, dollars, calls in flight, its day so far. */
fun reduceTokens(s: LiveState, e: StreamEvent, now: Long): LiveState {
    if (e.type != "llm.tick") return s
    val t = decode(e, LlmTick.serializer()) ?: return s
    val co = t.company.ifBlank { e.company.orEmpty() }
    val at = isoMs(e.at) ?: now
    val window = t.tokens.total
    val tk = s.tokens
    val kinds = tk.kinds?.let { it + TokenKinds(t.tokens.input, t.tokens.output, t.tokens.cacheRead + t.tokens.cacheWrite, t.tokens.thinking) }
    val tokens = tk.copy(
        today = tk.today?.plus(window),
        effectiveToday = tk.effectiveToday?.plus(window - t.tokens.cacheRead),
        usdToday = tk.usdToday?.plus(t.equivUsd),
        kinds = kinds,
        ticks = (tk.ticks + (at to window)).filter { now - it.first < LiveRules.PER_MIN_MS },
        inFlight = if (co.isBlank()) tk.inFlight else tk.inFlight + (co to (t.inFlight to now)),
    )
    var out = s.copy(tokens = tokens)
    if (co.isNotBlank()) {
        val c = out.company(co)
        out = out.withCompany(c.copy(spendTodayUsd = t.day.equivUsd ?: c.spendTodayUsd?.plus(t.equivUsd), budgetUsd = t.day.budgetUsd ?: c.budgetUsd))
    }
    return out
}

/** HM-1, HM-3, CO-1: a server's state (and why, since when, its road); a job on it starting or ending (`server.call`). */
fun reduceServers(s: LiveState, e: StreamEvent, now: Long): LiveState {
    when (e.type) {
        "server.state" -> {
            val ev = decode(e, ServerStateEvent.serializer()) ?: return s
            val id = ev.server.ifBlank { e.ref.orEmpty() }.ifBlank { return s }
            val old = s.serverStates[id]
            val prev = old?.state?.ifBlank { null } ?: ev.prevState
            val next = ev.state.ifBlank { prev ?: return s }
            val co = e.company ?: old?.company
            val sv = ServerLive(
                id, co, next, prev, ev.since ?: if (prev != next) e.at else old?.since, ev.reason, ev.reasonFa, ev.via ?: old?.via,
                ev.hubRttMs ?: old?.hubRttMs, ev.openJobs ?: old?.openJobs, old?.busy ?: 0, old?.failedAt,
                if (prev == "offline" && next == "online") now else old?.backAt,
            )
            var out = s.copy(serverStates = s.serverStates + (id to sv))
            val was = prev == "online"
            val isOn = next == "online"
            if (prev != null && was != isOn) {
                val d = if (isOn) 1 else -1
                out = out.copy(servers = out.servers.copy(online = out.servers.online.add(d), offline = out.servers.offline.add(-d)))
                if (co != null) {
                    val c = out.company(co)
                    out = out.withCompany(c.copy(serversOnline = c.serversOnline.add(d)))
                }
            }
            return out
        }
        "server.call" -> {
            val id = e.data["server"].text()?.ifBlank { null } ?: e.ref?.ifBlank { null } ?: return s
            val state = e.data["state"].text() ?: e.data["exit_code"].text()?.let { if (it == "0") "done" else "failed" } ?: "running"
            // A job tells nothing of the server's state (blank: the map keeps what the hub last said of it).
            val old = s.serverStates[id] ?: ServerLive(id, e.company, "")
            val sv = when (state) {
                "running", "queued" -> old.copy(busy = old.busy + 1)
                "failed" -> old.copy(busy = (old.busy - 1).coerceAtLeast(0), failedAt = now)
                else -> old.copy(busy = (old.busy - 1).coerceAtLeast(0))
            }
            return s.copy(serverStates = s.serverStates + (id to sv))
        }
    }
    return s
}

/** HM-3: a measured road failed or came back (`network.link`). A road that is fine again leaves the map's red list. */
fun reduceLinks(s: LiveState, e: StreamEvent): LiveState {
    if (e.type != "network.link") return s
    val ev = decode(e, NetworkLinkEvent.serializer()) ?: return s
    if (ev.from.isBlank() || ev.to.isBlank()) return s
    val key = "${ev.from}>${ev.to}:${ev.port ?: 0}"
    return if (ev.ok) s.copy(links = s.links - key)
    else s.copy(links = s.links + (key to LinkLive(ev.from, ev.to, ev.port, false, ev.ms, ev.errorFa, ev.since ?: e.at, ev.lastOkAt)))
}

/** HM-2: what crossed the holding, in arrival order; [quiet] when it is a replay or the app is away (applied, never flown). */
fun reduceFlows(s: LiveState, e: StreamEvent, now: Long, quiet: Boolean): LiveState {
    val at = isoMs(e.at) ?: now
    val f: FlowLive = when (e.type) {
        "holding.flow" -> {
            val h = decode(e, HoldingFlow.serializer()) ?: return s
            if (h.from.isBlank() || h.to.isBlank() || h.kind.isBlank()) return s
            FlowLive(s.flowN + 1, e.id, at, h.from, h.to, h.kind, h.labelFa, h.ref, quiet)
        }
        "server.call" -> {
            val id = e.data["server"].text()?.ifBlank { null } ?: e.ref?.ifBlank { null } ?: return s
            val state = e.data["state"].text() ?: e.data["exit_code"].text()?.let { if (it == "0") "done" else "failed" } ?: "running"
            when (state) {
                "running" -> FlowLive(s.flowN + 1, e.id, at, "hub", "srv:$id", "job", e.data["summary_fa"].text(), id, quiet)
                "failed" -> FlowLive(s.flowN + 1, e.id, at, "srv:$id", "hub", "job_failed", e.data["summary_fa"].text(), id, quiet)
                "queued", "awaiting_seal" -> return s
                else -> FlowLive(s.flowN + 1, e.id, at, "srv:$id", "hub", "job_done", e.data["summary_fa"].text(), id, quiet)
            }
        }
        else -> return s
    }
    val flows = (s.flows + f).takeLast(LiveRules.FLOWS_MAX)
    var out = s.copy(flows = flows, flowN = f.n)
    // The table's «flows per hour» and the card's last event: each company the flow touched. §42.5: a `holding.flow`'s envelope
    // company is the holding's own code; its ends are only in `data` (never read from the envelope).
    val hour = flows.filter { now - it.at < 3_600_000L }
    for (code in setOf(f.from, f.to).filter { it != "hub" && it != "outside" && !it.startsWith("srv:") }) {
        val c = out.company(code)
        out = out.withCompany(c.copy(flowsHour = hour.count { it.from == code || it.to == code }, lastEventAt = maxOf(c.lastEventAt ?: 0L, at)))
    }
    return out
}

/**
 * GL-2: a kill switch moved (`control.changed`, ref = its scope: `holding` or `company:<CODE>`). The hub says it in `kill_switch`
 * (`engaged` | `released`); a freeze or a new company is a `control.changed` too, with neither, and leaves the band alone.
 */
fun reduceControl(s: LiveState, e: StreamEvent): LiveState {
    if (e.type != "control.changed") return s
    val scope = e.data["scope"].text()?.ifBlank { null } ?: e.ref?.ifBlank { null } ?: return s
    val state = (e.data["kill_switch"].text() ?: e.data["state"].text())?.takeIf { it == "engaged" || it == "released" } ?: return s
    val on = state == "engaged"
    val by = e.data["by"].text()
    return if (scope == "holding") s.copy(control = s.control.copy(holding = on, holdingSince = if (on) e.at else null, holdingBy = if (on) by else null))
    else {
        val code = scope.removePrefix("company:").ifBlank { e.company ?: return s }
        s.copy(control = s.control.copy(locked = if (on) s.control.locked + (code to e.at) else s.control.locked - code))
    }
}

/** CO-1: every event of a company is its «آخرین رویداد» (only the operating companies have a card: §42.5, the holding is the hub). */
fun reduceLastEvent(s: LiveState, e: StreamEvent, now: Long): LiveState {
    if (e.type == "holding.flow") return s // its envelope is the holding's; its ends are handled with the flow
    val co = e.company?.takeIf { it.isNotBlank() } ?: return s
    val c = s.companies[co] ?: return s
    return s.withCompany(c.copy(lastEventAt = maxOf(c.lastEventAt ?: 0L, isoMs(e.at) ?: now)))
}

/** Every reducer in turn: one event applied to the whole state. */
fun reduceLive(s: LiveState, e: StreamEvent, now: Long, quiet: Boolean): LiveState {
    var out = s
    out = reducePeople(out, e)
    out = reduceSessions(out, e)
    out = reduceCounts(out, e)
    out = reduceTokens(out, e, now)
    out = reduceServers(out, e, now)
    out = reduceLinks(out, e)
    out = reduceFlows(out, e, now, quiet)
    out = reduceControl(out, e)
    out = reduceLastEvent(out, e, now)
    return out.copy(applied = out.applied + 1, lastEventAt = now, missed = if (quiet) out.missed + 1 else out.missed)
}

/** Whether the event happened while the app was away (or replays the time it was): applied at once, never animated, counted. */
fun isReplay(s: LiveState, e: StreamEvent): Boolean {
    if (!s.foreground) return true
    val since = s.visibleSince ?: return false
    val at = isoMs(e.at) ?: return false
    return at < since - LiveRules.REPLAY_SKEW_MS
}

// ------------------------------------------------------------------ the store --
/**
 * The live store (K-2): [seed] from the summary, then [on] for every stream event. An event is applied once: its id is remembered, and an
 * id that is the stream's sequence at or before the seed's [LiveState.seq] is already in the seed. [foreground] follows the app on screen
 * (rule 7: what arrives while it is away is applied and counted, not replayed as motion).
 */
class LiveStore(private val clock: () -> Long = { HqClock.millis() }) {
    private val flow = MutableStateFlow(LiveState())
    val state: StateFlow<LiveState> = flow.asStateFlow()
    private val seen = LinkedHashSet<String>()

    /** Whether [e] is new: not heard before, and after the seed's sequence. */
    @Synchronized
    fun fresh(e: StreamEvent): Boolean {
        val id = e.id
        if (id.isBlank()) return true
        if (id in seen) return false
        val n = id.toLongOrNull()
        val seq = flow.value.seq
        return !(n != null && seq != null && n <= seq)
    }

    @Synchronized
    fun on(e: StreamEvent): Boolean {
        if (!fresh(e)) return false
        if (e.id.isNotBlank()) {
            seen += e.id
            if (seen.size > LiveRules.SEEN_MAX) seen.iterator().let { it.next(); it.remove() }
        }
        val s = flow.value
        flow.value = reduceLive(s, e, clock(), isReplay(s, e))
        return true
    }

    @Synchronized
    fun seed(s: LiveSummary, day: Totals? = null) {
        flow.value = seeded(flow.value, s, day, clock())
    }

    /** The app came to the front ([on]) or left it: what arrives while away is counted (rule 7). */
    @Synchronized
    fun foreground(on: Boolean) {
        val s = flow.value
        if (s.foreground == on) return
        flow.value = if (on) s.copy(foreground = true, visibleSince = clock()) else s.copy(foreground = false, visibleSince = null, missed = 0)
    }

    /** The owner saw the «n رویداد در نبودت» chip (or it timed out). */
    @Synchronized
    fun clearMissed() { flow.value = flow.value.copy(missed = 0) }

    /** Forget everything (a new session). */
    @Synchronized
    fun clear() { seen.clear(); flow.value = LiveState() }
}

// ------------------------------------------------------------------ the views' readings --
/** The calls in flight across the holding now (MO-1's work band rides the meter only while some are). */
fun inFlight(t: TokensLive, now: Long): Int = t.inFlight.values.filter { now - it.second < LiveRules.IN_FLIGHT_MS }.sumOf { it.first }

/** «توکن در دقیقه»: the last minute's ticks; just after the seed (no tick yet), the hub's own figure; null when nothing is known. */
fun perMin(t: TokensLive, now: Long): Long? {
    val recent = t.ticks.filter { now - it.first < LiveRules.PER_MIN_MS }
    return when {
        recent.isNotEmpty() -> recent.sumOf { it.second }
        t.seededAt != null && now - t.seededAt < LiveRules.PER_MIN_MS -> t.seedPerMin
        t.seededAt != null -> 0L
        else -> null
    }
}

/** Today's dollars against the daily budget, in percent; null without either. */
fun spendPct(t: TokensLive): Double? {
    val u = t.usdToday ?: return null
    val b = t.budgetUsd?.takeIf { it > 0 } ?: return null
    return u / b * 100.0
}

/** OF-1's four figures, each null when the hub has not said («—»). */
data class PulseView(val working: Int?, val total: Int?, val moving: Int?, val waitingYou: Int?, val perMin: Long?)

fun pulseOf(s: LiveState, now: Long): PulseView {
    val p = s.people
    val working = if (p.working == null && p.thinking == null) null else (p.working ?: 0) + (p.thinking ?: 0)
    val waiting = if (s.approvals == null && s.sessions.yourTurn == null) null else (s.approvals ?: 0) + (s.sessions.yourTurn ?: 0)
    return PulseView(working, p.total, s.sessions.moving, waiting, perMin(s.tokens, now))
}

/** CO-1's card state: locked first, then stuck people, then busy, else calm. */
fun companyStateOf(c: CompanyLive, control: ControlLive): String = when {
    control.holding || c.code in control.locked -> "locked"
    c.state == "stuck" -> "stuck"
    (c.working ?: 0) > 0 -> "busy"
    else -> c.state ?: "ok"
}

/** The people of [code] the store knows to be in a state worth a dot (not idle), busiest first. */
fun peopleOf(s: LiveState, code: String): List<EmployeeLive> =
    s.employees.values.filter { it.company == code && it.state != "idle" }.sortedBy { listOf("stuck", "working", "thinking", "waiting", "done").indexOf(it.state).let { i -> if (i < 0) 9 else i } }

/** The people states a card's dots show: those the store knows by name, then the rest of [CompanyLive.working] as plain «working». */
fun dotsOf(s: LiveState, c: CompanyLive): List<String> {
    val known = peopleOf(s, c.code).map { it.state }
    val knownBusy = known.count(::busyState)
    val more = ((c.working ?: 0) - knownBusy).coerceAtLeast(0)
    return known + List(more) { "working" }
}
