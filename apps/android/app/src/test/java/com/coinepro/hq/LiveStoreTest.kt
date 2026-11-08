package com.coinepro.hq

import com.coinepro.hq.core.data.Beat
import com.coinepro.hq.core.data.BurstLimiter
import com.coinepro.hq.core.data.CompanyLive
import com.coinepro.hq.core.data.LiveRules
import com.coinepro.hq.core.data.LiveState
import com.coinepro.hq.core.data.LiveStore
import com.coinepro.hq.core.data.Ring
import com.coinepro.hq.core.data.StreamState
import com.coinepro.hq.core.data.activityOrder
import com.coinepro.hq.core.data.ageFa
import com.coinepro.hq.core.data.companyStateOf
import com.coinepro.hq.core.data.dotsOf
import com.coinepro.hq.core.data.flowEdge
import com.coinepro.hq.core.data.flowFa
import com.coinepro.hq.core.data.flowInk
import com.coinepro.hq.core.data.flowLegs
import com.coinepro.hq.core.data.FlowInk
import com.coinepro.hq.core.data.frozen
import com.coinepro.hq.core.data.heartbeatFa
import com.coinepro.hq.core.data.heartbeatOf
import com.coinepro.hq.core.data.idleWatch
import com.coinepro.hq.core.data.idleWatchFa
import com.coinepro.hq.core.data.inFlight
import com.coinepro.hq.core.data.lastStepFa
import com.coinepro.hq.core.data.mergeLines
import com.coinepro.hq.core.data.perMin
import com.coinepro.hq.core.data.pulseOf
import com.coinepro.hq.core.data.ringPlan
import com.coinepro.hq.core.data.serverAngles
import com.coinepro.hq.core.data.spendPct
import com.coinepro.hq.core.net.ActivityLine
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.LiveCompany
import com.coinepro.hq.core.net.LiveControl
import com.coinepro.hq.core.net.LivePeople
import com.coinepro.hq.core.net.LiveServers
import com.coinepro.hq.core.net.LiveSessions
import com.coinepro.hq.core.net.LiveSummary
import com.coinepro.hq.core.net.LiveTokens
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.core.net.Totals
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ⟨1.24⟩ Contract §42, design/LIVE_VIEWS.md K-2: the live store and its reducers, pure. The seed and the resume after its sequence, each
 * event applied once, one reducer per view (people, sessions, approvals, tokens, servers, links, flows, kill switches, the last event),
 * the burst limiter (rule 4), the heartbeat and its staleness (GL-1), what arrived while the app was away (rule 7), and the map's ring for
 * any number of companies (§5: 0, 1, 3 and 40).
 */
class LiveStoreTest {
    private var now = 1_762_590_600_000L // 2025-11-08T08:30:00Z
    private val iso: String get() = java.time.Instant.ofEpochMilli(now).toString()
    private fun store() = LiveStore { now }.also { it.foreground(true) }

    private fun ev(id: String, type: String, data: String, company: String? = null, ref: String? = null, at: String = iso) =
        StreamEvent(id, type, at, company, ref, Api.json.parseToJsonElement(data) as JsonObject)

    private val summary = LiveSummary(
        seq = 100, at = "2025-11-08T08:30:00Z",
        people = LivePeople(working = 9, thinking = 4, waiting = 3, stuck = 0, total = 28),
        sessions = LiveSessions(moving = 2, yourTurn = 1, stuck = 0, ready = 1),
        approvals = 12, urgentUnread = 0,
        servers = LiveServers(online = 4, offline = 0, total = 4),
        tokens = LiveTokens(today = 188_100, effectiveToday = 166_000, perMin = 7_600, equivUsdToday = 2.94, budgetUsd = 4.0),
        control = LiveControl(holding = false, companiesLocked = listOf("PC")),
        companies = listOf(
            LiveCompany("TY", "تریدیار", working = 3, total = 12, sessionsOpen = 1, serversOnline = 1, serversTotal = 1, spendTodayUsd = 1.12),
            LiveCompany("FX", "کوینه‌پرو FX", working = 3, total = 9, sessionsOpen = 0, serversOnline = 1, serversTotal = 1, spendTodayUsd = 1.38),
            LiveCompany("PC", "پرو-چارت", working = null, total = 7, sessionsOpen = 1, serversOnline = 1, serversTotal = 1, spendTodayUsd = 0.44),
        ),
    )

    // ------------------------------------------------------------------ the seed, the resume, once --
    @Test
    fun theSeedIsTheHubsWordAndMissingStaysMissing() {
        val s = store()
        assertFalse(s.state.value.seeded)
        assertNull("nothing known before the seed: «—»", pulseOf(s.state.value, now).working)
        s.seed(summary, Totals(inputTokens = 118_400, outputTokens = 41_200, cacheReadTokens = 22_100, cacheWriteTokens = 6_400))
        val v = s.state.value
        assertTrue(v.seeded)
        assertEquals(100L, v.seq)
        assertEquals(listOf("TY", "FX", "PC"), v.companies.keys.toList())
        assertNull("a company's missing figure stays null, never zero", v.companies.getValue("PC").working)
        assertEquals(28_500L, v.tokens.kinds!!.cache)
        assertEquals(setOf("PC"), v.control.locked.keys)
        val p = pulseOf(v, now)
        assertEquals(13, p.working) // working + thinking
        assertEquals(13, p.waitingYou) // approvals + your turn
        assertEquals(7_600L, p.perMin) // the hub's figure until a tick
    }

    @Test
    fun anEventAtOrBeforeTheSeedsSequenceIsAlreadyInIt() {
        val s = store()
        s.seed(summary)
        assertFalse(s.on(ev("99", "decision.created", "{}")))
        assertFalse(s.on(ev("100", "decision.created", "{}")))
        assertTrue(s.on(ev("101", "decision.created", "{}")))
        assertEquals(13, s.state.value.approvals)
    }

    @Test
    fun eachEventIsAppliedOnceByItsId() {
        val s = store()
        s.seed(summary)
        val e = ev("205", "decision.created", "{}")
        assertTrue(s.on(e))
        assertFalse("a replayed id is not applied twice", s.on(e))
        assertFalse(s.on(e.copy(at = "2025-11-08T08:31:00Z")))
        assertEquals(13, s.state.value.approvals)
        assertEquals(1L, s.state.value.applied)
        // The demo's ids are not sequences: only the de-duplication applies.
        assertTrue(s.on(ev("demo-1", "decision.decided", "{}")))
        assertFalse(s.on(ev("demo-1", "decision.decided", "{}")))
        assertEquals(12, s.state.value.approvals)
    }

    @Test
    fun aSecondSeedMendsTheCountsAndKeepsWhatEventsTaught() {
        val s = store()
        s.seed(summary)
        s.on(ev("101", "employee.state", """{"employee":"TY-GROWTH-01","company":"TY","state":"stuck","stuck_fa":"کلید تلگرام"}""", "TY"))
        s.seed(summary.copy(seq = 300, people = summary.people.copy(stuck = 1)))
        val v = s.state.value
        assertEquals(300L, v.seq)
        assertEquals(1, v.people.stuck)
        assertEquals("stuck", v.employees.getValue("TY-GROWTH-01").state)
        assertFalse(s.on(ev("250", "decision.created", "{}")))
    }

    // ------------------------------------------------------------------ one reducer per view --
    @Test
    fun aPersonsStateMovesTheCountsAndTheirCompanysWorkers() {
        val s = store()
        s.seed(summary)
        s.on(ev("101", "employee.state", """{"employee":"TY-GROWTH-01","company":"TY","state":"working"}""", "TY"))
        var v = s.state.value
        assertEquals(10, v.people.working)
        assertEquals(4, v.companies.getValue("TY").working)
        s.on(ev("102", "employee.state", """{"employee":"TY-GROWTH-01","company":"TY","state":"stuck","stuck_fa":"کلید منقضی شده"}""", "TY"))
        v = s.state.value
        assertEquals(9, v.people.working)
        assertEquals(1, v.people.stuck)
        assertEquals(3, v.companies.getValue("TY").working)
        assertEquals("کلید منقضی شده", v.employees.getValue("TY-GROWTH-01").stuckFa)
        // Its card's dots: the known person by shape first, then the rest of the company's workers.
        assertEquals(listOf("stuck", "working", "working", "working"), dotsOf(v, v.companies.getValue("TY")))
        // A company whose figure is missing stays missing (no count from a delta alone).
        s.on(ev("103", "employee.state", """{"employee":"PC-MEDIA-01","company":"PC","state":"working"}""", "PC"))
        assertNull(s.state.value.companies.getValue("PC").working)
    }

    @Test
    fun aSessionsBadgeMovesBetweenTheCounts() {
        val s = store()
        s.seed(summary)
        // A session first heard moving joins «در جریان»…
        s.on(ev("101", "session.updated", """{"ref":"F-0104","badge":"moving"}""", ref = "F-0104"))
        assertEquals(3, s.state.value.sessions.moving)
        // …then turns to the owner: one less moving, one more on his turn.
        s.on(ev("102", "session.updated", """{"ref":"F-0104","badge":"your_turn"}""", ref = "F-0104"))
        val v = s.state.value
        assertEquals(2, v.sessions.moving)
        assertEquals(2, v.sessions.yourTurn)
        assertEquals(14, pulseOf(v, now).waitingYou)
        // The same badge again moves nothing.
        s.on(ev("103", "session.updated", """{"ref":"F-0104","badge":"your_turn"}""", ref = "F-0104"))
        assertEquals(2, s.state.value.sessions.yourTurn)
    }

    @Test
    fun aTickAddsItsWindowToTodayAndItsCompanysDay() {
        val s = store()
        s.seed(summary, Totals(inputTokens = 100, outputTokens = 100, cacheReadTokens = 100, cacheWriteTokens = 0, thinkingTokens = 0))
        s.on(
            ev(
                "101", "llm.tick",
                """{"company":"TY","window_s":5,"calls":3,"in_flight":2,"tokens":{"input":4200,"output":900,"cache_read":1600,"cache_write":300,"thinking":600},
                "equiv_usd":"0.11","day":{"tokens":null,"effective_tokens":null,"equiv_usd":"1.23","budget_usd":"1.50","pct":82.0}}""",
                "TY",
            ),
        )
        val t = s.state.value.tokens
        assertEquals(188_100L + 7_600, t.today)
        assertEquals(3.05, t.usdToday!!, 1e-9)
        assertEquals(4_300L, t.kinds!!.input)
        assertEquals(2_000L, t.kinds!!.cache)
        assertEquals(600L, t.kinds!!.thinking)
        assertEquals(7_600L, perMin(t, now))
        assertEquals(2, inFlight(t, now))
        assertEquals(76.25, spendPct(t)!!, 1e-9)
        val ty = s.state.value.companies.getValue("TY")
        assertEquals(1.23, ty.spendTodayUsd!!, 1e-9)
        assertEquals(1.50, ty.budgetUsd!!, 1e-9)
        // A minute later the window has gone by: nothing a minute, nothing in flight.
        now += LiveRules.PER_MIN_MS + 1
        assertEquals(0L, perMin(s.state.value.tokens, now))
        assertEquals(0, inFlight(s.state.value.tokens, now))
    }

    @Test
    fun aServerDropsWithWhyAndComesBack() {
        val s = store()
        s.seed(summary)
        s.on(
            ev(
                "101", "server.state",
                """{"server":"srv-fx-1","state":"offline","prev_state":"online","since":"2025-11-08T08:30:00Z","reason":"runner_stopped","reason_fa":"runner روی سرور ایستاده","via":"private","hub_rtt_ms":null,"open_jobs":2}""",
                "FX", "srv-fx-1",
            ),
        )
        var v = s.state.value
        val sv = v.serverStates.getValue("srv-fx-1")
        assertEquals("offline" to "runner_stopped", sv.state to sv.reason)
        assertEquals(2, sv.openJobs)
        assertEquals(3, v.servers.online)
        assertEquals(1, v.servers.offline)
        assertEquals(0, v.companies.getValue("FX").serversOnline)
        now += 20_000
        s.on(ev("102", "server.state", """{"server":"srv-fx-1","state":"online","prev_state":"offline","via":"private","hub_rtt_ms":2.8,"open_jobs":0}""", "FX", "srv-fx-1"))
        v = s.state.value
        assertEquals(4, v.servers.online)
        assertEquals(1, v.companies.getValue("FX").serversOnline)
        assertEquals("back online: positive for two seconds", now, v.serverStates.getValue("srv-fx-1").backAt)
        // A job is no word on a server's state: it stays as the hub last said.
        s.on(ev("103", "server.call", """{"server":"srv-ty-1","state":"running","summary_fa":"خواندن sitemap"}""", "TY", "srv-ty-1"))
        assertEquals("", s.state.value.serverStates.getValue("srv-ty-1").state)
        assertEquals(1, s.state.value.serverStates.getValue("srv-ty-1").busy)
        s.on(ev("104", "server.call", """{"server":"srv-ty-1","exit_code":"1","summary_fa":"خواندن sitemap"}""", "TY", "srv-ty-1"))
        assertEquals(0, s.state.value.serverStates.getValue("srv-ty-1").busy)
        assertEquals(now, s.state.value.serverStates.getValue("srv-ty-1").failedAt)
    }

    @Test
    fun aMeasuredRoadFailsThenLeavesTheRedList() {
        val s = store()
        s.on(ev("101", "network.link", """{"from":"srv-pc-1","to":"srv-fx-1","port":22,"ok":false,"ms":null,"error_fa":"پورت بسته است","since":"2025-11-08T08:29:00Z","last_ok_at":null}"""))
        assertEquals("پورت بسته است", s.state.value.links.values.single().errorFa)
        s.on(ev("102", "network.link", """{"from":"srv-pc-1","to":"srv-fx-1","port":22,"ok":true,"ms":0.6}"""))
        assertTrue(s.state.value.links.isEmpty())
    }

    @Test
    fun flowsAreNumberedAndAReplayNeverFlies() {
        val s = store()
        s.seed(summary)
        s.on(ev("101", "holding.flow", """{"from":"hub","to":"TY","kind":"order","via":"hub","ref":"W-000140","root_ref":null,"label_fa":"ریلز طلا"}""", "HQ"))
        s.on(ev("102", "holding.flow", """{"from":"FX","to":"TY","kind":"request","via":"hub","ref":"W-000141"}""", "HQ"))
        s.on(ev("103", "server.call", """{"server":"srv-ty-1","state":"running","summary_fa":"sitemap"}""", "TY", "srv-ty-1"))
        // Something that happened an hour ago (a resume replaying it): applied, counted as missed, never flown.
        s.on(ev("104", "holding.flow", """{"from":"TY","to":"FX","kind":"deliver","via":"hub","ref":"W-000141"}""", "HQ", at = "2025-11-08T07:30:00Z"))
        val f = s.state.value.flows
        assertEquals(listOf(1L, 2L, 3L, 4L), f.map { it.n })
        assertEquals(listOf(false, false, false, true), f.map { it.quiet })
        assertTrue(f[0].owner)
        assertEquals(FlowInk.GOLD to FlowInk.SILVER, flowInk(f[0].kind) to flowInk(f[1].kind))
        assertEquals(FlowInk.LAPIS, flowInk(f[2].kind))
        // A request between two companies travels A → hub → B (servers never talk directly).
        assertEquals(listOf("FX", "hub", "TY"), flowLegs(f[1]))
        assertEquals(listOf("hub", "srv:srv-ty-1"), flowLegs(f[2]))
        assertEquals("FX>TY", flowEdge(f[1]))
        assertEquals("کوینه‌پرو FX از تریدیار کار خواست", flowFa(f[1]) { mapOf("TY" to "تریدیار", "FX" to "کوینه‌پرو FX")[it] ?: it })
        assertEquals("the table's flows in the last hour", 2, s.state.value.companies.getValue("TY").flowsHour)
        // §42.5: the envelope is the holding's; the ends' cards learn of it from the data, and the holding gets no card.
        assertEquals(now, s.state.value.companies.getValue("FX").lastEventAt)
        assertFalse("HQ" in s.state.value.companies)
        assertEquals(1, s.state.value.missed)
    }

    @Test
    fun killSwitchesAndTheCompanyCardsState() {
        val s = store()
        s.seed(summary)
        assertEquals("locked", companyStateOf(s.state.value.companies.getValue("PC"), s.state.value.control))
        // the hub's own shape (control.py): `kill_switch`, `scope`, `by`
        s.on(ev("101", "control.changed", """{"kill_switch":"engaged","scope":"holding","by":"owner"}""", "HQ", "holding"))
        assertTrue(s.state.value.control.holding)
        assertEquals("owner", s.state.value.control.holdingBy)
        assertEquals("locked", companyStateOf(s.state.value.companies.getValue("TY"), s.state.value.control))
        // a freeze or a new company is a control.changed too: the band stays as it is
        s.on(ev("100a", "control.changed", """{"deploy_freeze_until":"2026-11-09T00:00:00Z","by":"owner"}""", "HQ", "holding"))
        s.on(ev("100b", "control.changed", """{"change":"company.created"}""", "HQ", "holding"))
        assertTrue(s.state.value.control.holding)
        // the owner releases it (the 0.19.0 band stayed red: the release was read from `state`)
        s.on(ev("102", "control.changed", """{"kill_switch":"released","scope":"holding","by":"owner"}""", "HQ", "holding"))
        s.on(ev("103", "control.changed", """{"state":"released"}""", "PC", "company:PC"))
        assertFalse(s.state.value.control.holding)
        assertTrue(s.state.value.control.locked.isEmpty())
        assertEquals("busy", companyStateOf(s.state.value.companies.getValue("TY"), s.state.value.control))
        s.on(ev("104", "notification.created", """{"level":"urgent"}"""))
        s.on(ev("105", "notification.created", """{"level":"report"}"""))
        assertEquals(1, s.state.value.urgentUnread)
    }

    @Test
    fun everyEventOfACompanyIsItsLastEvent() {
        val s = store()
        s.seed(summary)
        now += 5_000
        s.on(ev("101", "work.updated", "{}", "FX"))
        assertEquals(now, s.state.value.companies.getValue("FX").lastEventAt)
    }

    // ------------------------------------------------------------------ rule 7: away, then back --
    @Test
    fun whatArrivesWhileAwayIsAppliedAndCountedNotReplayed() {
        val s = store()
        s.seed(summary)
        s.foreground(false)
        repeat(25) { i -> s.on(ev("${200 + i}", "decision.created", "{}")) }
        assertEquals(12 + 25, s.state.value.approvals)
        assertEquals(25, s.state.value.missed)
        assertTrue(s.state.value.missed > LiveRules.MISSED_CHIP)
        s.foreground(true)
        assertEquals("kept for the chip on return", 25, s.state.value.missed)
        s.clearMissed()
        assertEquals(0, s.state.value.missed)
        // Back on screen, an event of now is live (it may fly).
        s.on(ev("300", "holding.flow", """{"from":"hub","to":"TY","kind":"order","via":"hub","ref":"W-1"}""", "HQ"))
        assertFalse(s.state.value.flows.last().quiet)
    }

    // ------------------------------------------------------------------ rule 4: the burst limiter --
    @Test
    fun threeFlyOnAnEdgeAndTheRestFoldIntoItsChip() {
        val b = BurstLimiter(perEdge = 3, total = 24)
        assertEquals(listOf(true, true, true, false, false), List(5) { b.admit("hub>TY") })
        assertEquals("five crossed: three in flight and two folded", 5, b.chip("hub>TY"))
        assertTrue("another edge is free", b.admit("hub>FX"))
        assertNull(b.chip("hub>FX"))
        b.land("hub>TY")
        assertTrue(b.admit("hub>TY"))
        b.clearChip("hub>TY")
        assertNull(b.chip("hub>TY"))
    }

    @Test
    fun atMostTwentyFourAnimateOnAScreen() {
        val b = BurstLimiter(perEdge = 3, total = 24)
        val flew = (0 until 40).count { i -> b.admit("e$i") }
        assertEquals(24, flew)
        assertEquals(24, b.inFlight)
        assertEquals(1, b.chip("e30"))
        b.reset()
        assertEquals(0, b.inFlight)
    }

    // ------------------------------------------------------------------ GL-1 the heartbeat --
    @Test
    fun theHeartbeatIsLiveReconnectingOldOrOffline() {
        assertEquals(Beat.LIVE, heartbeatOf(StreamState.LIVE, null, online = true, now = now))
        assertEquals(Beat.RECONNECTING, heartbeatOf(StreamState.CONNECTING, null, true, now))
        assertEquals(Beat.RECONNECTING, heartbeatOf(StreamState.OFFLINE, now - 10_000, true, now))
        assertEquals(Beat.STALE, heartbeatOf(StreamState.OFFLINE, now - LiveRules.STALE_MS, true, now))
        assertEquals(Beat.OFFLINE, heartbeatOf(StreamState.OFFLINE, now - 5_000, online = false, now = now))
        assertTrue(Beat.STALE.frozen && Beat.OFFLINE.frozen)
        assertFalse(Beat.LIVE.frozen || Beat.RECONNECTING.frozen)
        assertEquals("قدیمی · ۲ دقیقه", heartbeatFa(Beat.STALE, now - 125_000, now))
        assertEquals("زنده", heartbeatFa(Beat.LIVE, null, now))
        assertEquals("در حال وصل", heartbeatFa(Beat.RECONNECTING, now, now))
        assertEquals("بی‌اتصال", heartbeatFa(Beat.OFFLINE, now, now))
        assertEquals("۴۵ ثانیه", ageFa(45_000))
        assertEquals("۳ ساعت", ageFa(3 * 3_600_000L + 5))
    }

    // ------------------------------------------------------------------ §5 the ring, any number of companies --
    @Test
    fun noCompanyIsTheHubAlone() {
        val p = ringPlan(emptyList(), 100f, 146f)
        assertTrue(p.slots.isEmpty())
        assertEquals(0, p.rings)
    }

    @Test
    fun oneCompanySitsOnTopAtFullSize() {
        val p = ringPlan(listOf("TY"), 100f, 146f)
        assertEquals(1, p.slots.size)
        assertEquals(-90.0, p.slots.single().angle, 1e-9)
        assertEquals(Ring.NODE, p.slots.single().size, 0f)
    }

    @Test
    fun threeCompaniesShareOneRingEvenly() {
        val p = ringPlan(listOf("TY", "FX", "PC"), 100f, 146f)
        assertEquals(1, p.rings)
        assertEquals(listOf(-90.0, 30.0, 150.0), p.slots.map { it.angle })
        assertTrue(p.folded.isEmpty())
    }

    @Test
    fun fortyCompaniesShrinkThenTakeASecondRingThenFold() {
        val codes = (1..40).map { "C$it" }
        val r1 = 100f
        val r2 = 146f
        assertEquals(9, Ring.capacity(r1, Ring.NODE))
        assertEquals(14, Ring.capacity(r1, Ring.MIN))
        val p = ringPlan(codes, r1, r2)
        assertEquals(2, p.rings)
        val inner = p.slots.filter { it.ring == 0 }
        val outer = p.slots.filter { it.ring == 1 }
        assertEquals(14, inner.size)
        assertEquals(Ring.capacity(r2, Ring.MIN), outer.size)
        assertTrue("every node legible", p.slots.all { it.size >= Ring.MIN })
        assertEquals("the busiest on top", "C1", inner.first().code)
        val fold = outer.last()
        assertTrue(fold.fold)
        assertEquals(40, p.shown.size + p.folded.size)
        assertEquals("the least active fold", codes.takeLast(p.folded.size), p.folded)
        // Between full size and the second ring: smaller nodes on one ring.
        val twelve = ringPlan(codes.take(12), r1, r2)
        assertEquals(1, twelve.rings)
        assertTrue(twelve.slots.all { it.size < Ring.NODE && it.size >= Ring.MIN })
    }

    @Test
    fun theBusiestCompaniesComeFirstNeverTheAlphabet() {
        val live = mapOf(
            "TY" to CompanyLive("TY", working = 1, lastEventAt = 5),
            "FX" to CompanyLive("FX", working = 4),
            "PC" to CompanyLive("PC", working = 1, lastEventAt = 9),
        )
        assertEquals(listOf("FX", "PC", "TY", "ZZ"), activityOrder(listOf("TY", "FX", "PC", "ZZ"), live))
        assertEquals(listOf("B", "A"), activityOrder(listOf("B", "A"), emptyMap()))
        assertEquals(listOf(-6.0, 6.0), serverAngles(0.0, 2, 12.0))
        assertEquals(4, serverAngles(0.0, 9, 8.0).size)
    }

    // ------------------------------------------------------------------ SE-1, SS-1 --
    @Test
    fun aStepsEndUpdatesItsOwnLine() {
        val start = ActivityLine("2025-11-08T08:29:00Z", "مدیر رسانه", "زیرنویس را مینویسد", id = "run-7:3", kind = "step", state = "running")
        val other = ActivityLine("2025-11-08T08:29:30Z", "تدوینگر", "برش اول را ساخت")
        val end = start.copy(at = "2025-11-08T08:30:10Z", textFa = "زیرنویس را نوشت", state = "done")
        val merged = mergeLines(listOf(start, other), listOf(end))
        assertEquals(2, merged.size)
        assertEquals("the step stays where it began", "2025-11-08T08:29:00Z", merged.first().at)
        assertEquals("done" to "زیرنویس را نوشت", merged.first().state to merged.first().textFa)
        // The fetch that comes back with the step still running does not undo its end.
        assertEquals("done", mergeLines(listOf(end), listOf(start)).single().state)
    }

    @Test
    fun theStallWatchFillsTowardTheHubsSweep() {
        val at = { m: Long -> java.time.Instant.ofEpochMilli(now - m * 60_000).toString() }
        val w7 = idleWatch(at(7), now)!!
        assertEquals(0, w7.window)
        assertEquals(0.7f, w7.fraction, 1e-6f)
        assertEquals("۷ از ۱۰ دقیقه", idleWatchFa(w7))
        assertEquals("آخرین قدم ۷ دقیقه پیش", lastStepFa(at(7), now))
        val w13 = idleWatch(at(13), now)!!
        assertEquals(1, w13.window)
        assertEquals("هاب بیدارش کرد · ۳ از ۱۰ دقیقه", idleWatchFa(w13))
        assertEquals(2, idleWatch(at(25), now)!!.window)
        assertNull(idleWatch(null, now))
        assertEquals("آخرین قدم همین الان", lastStepFa(iso, now))
    }

    @Test
    fun theOfficePulseSaysMissingNeverZero() {
        val p = pulseOf(LiveState(), now)
        assertNull(p.working)
        assertNull(p.moving)
        assertNull(p.waitingYou)
        assertNull(p.perMin)
        assertNotNull(pulseOf(LiveState(approvals = 0), now).waitingYou)
    }
}
