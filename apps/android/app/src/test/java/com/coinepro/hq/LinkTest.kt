package com.coinepro.hq

import com.coinepro.hq.core.data.LaneStatus
import com.coinepro.hq.core.data.LinkPhase
import com.coinepro.hq.core.data.NoticeKind
import com.coinepro.hq.core.data.OrderNotice
import com.coinepro.hq.core.data.OrderWatcher
import com.coinepro.hq.core.data.StreamMode
import com.coinepro.hq.core.data.WorkTitles
import com.coinepro.hq.core.link.Alert
import com.coinepro.hq.core.link.AlertSink
import com.coinepro.hq.core.link.Backoff
import com.coinepro.hq.core.link.HubLink
import com.coinepro.hq.core.link.LinkInputs
import com.coinepro.hq.core.link.LinkJournal
import com.coinepro.hq.core.link.LinkPolicy
import com.coinepro.hq.core.link.LinkSession
import com.coinepro.hq.core.link.LinkShown
import com.coinepro.hq.core.link.LinkStream
import com.coinepro.hq.core.link.MemoryLinkStore
import com.coinepro.hq.core.link.ServiceControl
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.core.net.TokenSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The background link's decisions (core/link): the reconnect backoff, the log lines that fold repeats, when the service runs (on by default
 * once notifications are allowed, never signed out, paused until the app is opened again), what a reboot or the watchdog does, what a
 * session that expires with the app closed does, and the orders tracker telling a stage it missed while the process was gone.
 */
@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
class LinkTest {
    // ------------------------------------------------------------ backoff --
    @Test
    fun theBackoffGrowsWithJitterUpToItsCap() {
        assertEquals(0L, Backoff.delayMs(0, Backoff.FOREGROUND_CAP_MS, 0.5))
        // Equal jitter: between half and all of 1 s, 2 s, 4 s…
        assertEquals(500L, Backoff.delayMs(1, Backoff.FOREGROUND_CAP_MS, 0.0))
        assertEquals(1_000L, Backoff.delayMs(1, Backoff.FOREGROUND_CAP_MS, 1.0))
        assertEquals(2_000L, Backoff.delayMs(3, Backoff.FOREGROUND_CAP_MS, 0.0))
        assertEquals(4_000L, Backoff.delayMs(3, Backoff.FOREGROUND_CAP_MS, 1.0))
        // On screen it never waits more than 30 s; in the background, five minutes; a huge attempt does not overflow.
        for (n in 1..200) {
            val fg = Backoff.delayMs(n, Backoff.FOREGROUND_CAP_MS, Math.random())
            val bg = Backoff.delayMs(n, Backoff.BACKGROUND_CAP_MS, Math.random())
            assertTrue("$n: $fg", fg in 500L..Backoff.FOREGROUND_CAP_MS)
            assertTrue("$n: $bg", bg in 500L..Backoff.BACKGROUND_CAP_MS)
        }
        assertEquals(Backoff.BACKGROUND_CAP_MS, Backoff.delayMs(64, Backoff.BACKGROUND_CAP_MS, 1.0))
        assertEquals(Backoff.BACKGROUND_CAP_MS / 2, Backoff.delayMs(64, Backoff.BACKGROUND_CAP_MS, 0.0))
    }

    // ------------------------------------------------------------ journal --
    @Test
    fun theLogFoldsRepeatsInsteadOfFloodingTheErrorReader() {
        val lines = mutableListOf<Pair<String, String>>()
        val j = LinkJournal({ t, d -> lines += t to d }, windowMs = 30 * 60_000L)
        val min = 60_000L
        j.live(0, resumed = false)
        // A phone in a lift: a dozen drops in ten minutes.
        for (i in 1..12) {
            j.dropped(i * 50_000L, "no network")
            j.live(i * 50_000L + 8_000, resumed = true)
        }
        assertEquals(listOf("link connected", "link back"), lines.map { it.first })
        assertTrue(lines[1].second.contains("8 s") && lines[1].second.contains("no network") && lines[1].second.contains("resumed"))
        // The next one after the window says how many were folded into it.
        j.dropped(45 * min, "HTTP 502")
        j.live(45 * min + 3_000, resumed = true)
        assertEquals(3, lines.size)
        assertTrue(lines[2].second, lines[2].second.contains("and 11 more"))
        // Different moments are different lines.
        j.note(46 * min, "link restarted", "the background link was started again (watchdog)")
        assertEquals(4, lines.size)
    }

    // ------------------------------------------------------------- policy --
    private fun i(pref: Boolean? = null, allowed: Boolean = true, signedIn: Boolean = true, paused: Boolean = false) = LinkInputs(pref, allowed, signedIn, paused)

    @Test
    fun onByDefaultOnceNotificationsAreAllowed() {
        assertTrue(LinkPolicy.wantService(i()))
        assertFalse(LinkPolicy.wantService(i(allowed = false)))
        assertFalse(LinkPolicy.wantService(i(pref = false)))
        // Switched on but the permission was taken away: it cannot run (and the settings say why).
        assertFalse(LinkPolicy.wantService(i(pref = true, allowed = false)))
        assertEquals(LinkShown.NO_PERMISSION, LinkPolicy.view(i(pref = true, allowed = false), LaneStatus(LinkPhase.OFF)).shown)
        assertFalse(LinkPolicy.wantService(i(signedIn = false)))
        assertFalse(LinkPolicy.wantService(i(paused = true)))
    }

    @Test
    fun whatTheStreamKeepsOpen() {
        assertEquals(StreamMode.FULL, LinkPolicy.mode(i(), foreground = true))
        assertEquals(StreamMode.FULL, LinkPolicy.mode(i(pref = false), foreground = true))
        assertEquals(StreamMode.ALERTS, LinkPolicy.mode(i(), foreground = false))
        assertEquals(StreamMode.OFF, LinkPolicy.mode(i(pref = false), foreground = false))
        assertEquals(StreamMode.OFF, LinkPolicy.mode(i(paused = true), foreground = false))
        assertEquals(StreamMode.OFF, LinkPolicy.mode(i(signedIn = false), foreground = true))
    }

    @Test
    fun aRebootOrAnUpdateStartsItOnlyWhenWanted() {
        assertTrue(LinkPolicy.onBoot(i()))
        assertTrue(LinkPolicy.onBoot(i(pref = true)))
        assertFalse(LinkPolicy.onBoot(i(pref = false)))
        assertFalse(LinkPolicy.onBoot(i(allowed = false)))
        assertFalse(LinkPolicy.onBoot(i(signedIn = false)))
        assertFalse(LinkPolicy.onBoot(i(paused = true)))
    }

    @Test
    fun theStatusLineSaysWhy() {
        assertEquals("وصل · زنده", LinkPolicy.view(i(), LaneStatus(LinkPhase.LIVE)).fa)
        assertEquals("در حال اتصال…", LinkPolicy.view(i(), LaneStatus(LinkPhase.CONNECTING)).fa)
        assertEquals("قطع: اینترنت نیست؛ با برگشتنش وصل میشوم", LinkPolicy.view(i(), LaneStatus(LinkPhase.WAITING_NETWORK)).fa)
        assertEquals("قطع: ستاد جواب نمیدهد؛ خودکار دوباره تلاش میکنم", LinkPolicy.view(i(), LaneStatus(LinkPhase.RETRYING, "HTTP 502")).fa)
        assertEquals("قطع: نشست تمام شد؛ دوباره وارد شو", LinkPolicy.view(i(), LaneStatus(LinkPhase.REFUSED, "session expired")).fa)
        assertEquals("خاموش", LinkPolicy.view(i(pref = false), LaneStatus(LinkPhase.LIVE)).fa)
        assertEquals("قطع تا وقتی اپ را دوباره باز کنی", LinkPolicy.view(i(paused = true), LaneStatus(LinkPhase.OFF)).fa)
        assertEquals(LinkShown.DOWN, LinkPolicy.view(i(), LaneStatus(LinkPhase.OFF), refused = true).shown)
    }

    // --------------------------------------------------------------- link --
    private class FakeStream : LinkStream {
        override val mode = MutableStateFlow(StreamMode.OFF)
        override val alertLane = MutableStateFlow(LaneStatus(LinkPhase.OFF))
        var nudges = 0
        override fun setMode(m: StreamMode) { mode.value = m; alertLane.value = LaneStatus(if (m == StreamMode.OFF) LinkPhase.OFF else LinkPhase.LIVE) }
        override fun nudge() { nudges++ }
    }

    private class FakeSession(signed: Boolean = true) : LinkSession {
        override val signedIn = MutableStateFlow(signed)
        override val linkStream = FakeStream()
        override val demo = false
        var alerts = false
        override fun startAlerts() { alerts = true }
        override fun stopAlerts() { alerts = false }
    }

    private class FakeService(var allowStart: Boolean = true) : ServiceControl {
        val starts = mutableListOf<String>()
        var stops = 0
        var watchdog: Boolean? = null
        override fun start(reason: String): Boolean { starts += reason; return allowStart }
        override fun stop() { stops++ }
        override fun watchdog(on: Boolean) { watchdog = on }
    }

    private class FakeSink(var allowed: Boolean = true) : AlertSink {
        val expired = mutableListOf<Boolean>()
        override fun allowed() = allowed
        override fun post(alert: Alert) = Unit
        override fun cancel(key: String) = Unit
        override fun cancelRead(notificationIds: Collection<String>) = Unit
        override fun sessionExpired(show: Boolean) { expired += show }
    }

    private class Rig(val scope: TestScope, val allowed: Boolean = true, val allowStart: Boolean = true) {
        val store = MemoryLinkStore()
        val session = FakeSession()
        val env: StateFlow<LinkSession> = MutableStateFlow(session)
        val service = FakeService(allowStart)
        val sink = FakeSink(allowed)
        val notes = mutableListOf<String>()
        val link = HubLink(store, env, sink, service, note = { t, _ -> notes += t }, scope = CoroutineScope(UnconfinedTestDispatcher(scope.testScheduler))).also { it.attach() }
    }

    @Test
    fun onScreenTheServiceStartsAndAllLanesOpen_closedOnlyTheAlertLaneStays() = runTest {
        val r = Rig(this)
        r.link.setForeground(true)
        assertEquals(StreamMode.FULL, r.session.linkStream.mode.value)
        assertEquals(listOf("app open"), r.service.starts)
        assertEquals(true, r.service.watchdog)
        assertTrue(r.session.alerts)
        r.link.serviceUp()
        r.link.setForeground(false)
        // One stream: the alert lane is the same connection, it is not opened again.
        assertEquals(StreamMode.ALERTS, r.session.linkStream.mode.value)
        assertEquals(1, r.service.starts.size)
        assertEquals(LinkShown.LIVE, r.link.view.value.shown)
    }

    @Test
    fun switchingOffStopsTheServiceAndTheWatchdog() = runTest {
        val r = Rig(this)
        r.link.setForeground(true)
        r.link.serviceUp()
        r.link.setEnabled(false)
        assertEquals(1, r.service.stops)
        assertEquals(false, r.service.watchdog)
        r.link.serviceDown()
        r.link.setForeground(false)
        assertEquals(StreamMode.OFF, r.session.linkStream.mode.value)
        assertFalse(r.session.alerts)
        assertEquals(LinkShown.OFF, r.link.view.value.shown)
        assertTrue("link switched" in r.notes)
    }

    @Test
    fun withoutPermissionNothingRunsInTheBackground() = runTest {
        val r = Rig(this, allowed = false)
        r.link.setForeground(true)
        assertTrue(r.service.starts.isEmpty())
        r.link.setForeground(false)
        assertEquals(StreamMode.OFF, r.session.linkStream.mode.value)
        assertEquals(LinkShown.NO_PERMISSION, r.link.view.value.shown)
        // Granted: on by default.
        r.sink.allowed = true
        r.link.refresh()
        r.link.setForeground(true)
        assertEquals(1, r.service.starts.size)
    }

    @Test
    fun pausedUntilTheAppIsOpenedAgain() = runTest {
        val r = Rig(this)
        r.link.setForeground(true)
        r.link.serviceUp()
        r.link.setForeground(false)
        r.link.pauseUntilReturn()
        assertEquals(1, r.service.stops)
        r.link.serviceDown()
        assertEquals(StreamMode.OFF, r.session.linkStream.mode.value)
        // The watchdog and a reboot respect the pause.
        assertFalse(r.link.revive("watchdog"))
        assertEquals(1, r.service.starts.size)
        // Opened again: the pause ends and the service is back.
        r.link.setForeground(true)
        assertFalse(r.store.pausedUntilReturn)
        assertEquals(2, r.service.starts.size)
    }

    @Test
    fun theWatchdogRestartsAStoppedServiceOrNudgesARunningOne() = runTest {
        val r = Rig(this)
        assertTrue(r.link.revive("boot"))
        assertEquals(listOf("boot"), r.service.starts)
        assertTrue("link restarted" in r.notes)
        r.link.serviceUp()
        assertTrue(r.link.revive("watchdog"))
        assertEquals(1, r.service.starts.size)
        assertEquals(1, r.session.linkStream.nudges)
    }

    @Test
    fun aRefusedBackgroundStartIsSaidAndTriedAgainOnScreen() = runTest {
        val r = Rig(this, allowStart = false)
        assertFalse(r.link.revive("watchdog"))
        assertEquals(LinkShown.DOWN, r.link.view.value.shown)
        assertEquals("start refused", r.link.view.value.why)
        r.service.allowStart = true
        r.link.setForeground(true)
        assertEquals(2, r.service.starts.size)
    }

    @Test
    fun anExpiredSessionWithTheAppClosedIsToldOnceAndTheLinkStops() = runTest {
        val r = Rig(this)
        r.link.setForeground(true)
        r.link.serviceUp()
        r.link.setForeground(false)
        // The hub answers 401: the token is cleared, then the link hears it.
        r.session.signedIn.value = false
        r.link.expired()
        r.link.expired()
        assertEquals(listOf(true), r.sink.expired)
        assertEquals(1, r.service.stops)
        assertEquals(false, r.service.watchdog)
        assertEquals(StreamMode.OFF, r.session.linkStream.mode.value)
        assertTrue("session expired" in r.notes)
        // Signed in again: the notice goes, the link comes back.
        r.link.serviceDown()
        r.link.setForeground(true)
        r.session.signedIn.value = true
        assertEquals(listOf(true, false), r.sink.expired)
        assertEquals(2, r.service.starts.size)
    }

    @Test
    fun anExpiredSessionOnScreenIsNotANotification() = runTest {
        val r = Rig(this)
        r.link.setForeground(true)
        r.session.signedIn.value = false
        r.link.expired()
        assertTrue(r.sink.expired.isEmpty())
    }

    // ------------------------------------------------------------- orders --
    @Test
    fun aStageAKnownOrderReachedWhileTheProcessWasGoneIsToldOnce() = runTest {
        val server = MockWebServer().apply { start() }
        try {
            fun work(ref: String, status: String) =
                """{"id":"id-$ref","ref":"$ref","company":"TY","title":"کار $ref","status":"$status","created_by":{"kind":"owner","code":"owner","display_fa":"مدیر کل"},"updated_at":"2026-10-30T07:00:00Z"}"""
            val page = """{"items":[${work("W-1", "delivered")},${work("W-2", "delivered")},${work("W-3", "waiting")}],"next_cursor":null}"""
            repeat(2) { server.enqueue(MockResponse.Builder().code(200).addHeader("Content-Type", "application/json").body(page).build()) }
            val api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
            val memory = MemoryLinkStore().apply {
                // Before the process ended: W-1 was known at work (told nothing yet), W-3 known and already told as delegated.
                ordersKnown = setOf("W-1", "W-3")
                ordersTold = setOf("W-3:DELEGATED")
            }
            val scope = CoroutineScope(UnconfinedTestDispatcher(testScheduler))
            val events = MutableSharedFlow<StreamEvent>()
            val notices = mutableListOf<OrderNotice>()
            val w = OrderWatcher(api, events, scope, WorkTitles(scope) { null }, memory)
            val sub = backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { w.notices.collect { notices += it } }
            w.start()
            repeat(50) { if (notices.isEmpty()) { Thread.sleep(20); advanceUntilIdle() } }
            Thread.sleep(100)
            advanceUntilIdle()
            // W-1: delivered while away → told; W-2: met for the first time → not repeated; W-3: already told.
            assertEquals(listOf("W-1" to NoticeKind.DELIVERED), notices.map { it.ref to it.kind })
            assertTrue("W-1:DELIVERED" in memory.ordersTold)
            assertTrue(memory.ordersKnown.containsAll(listOf("W-1", "W-2", "W-3")))
            w.stop()
            // The next process does not tell it again.
            val again = mutableListOf<OrderNotice>()
            val w2 = OrderWatcher(api, events, scope, WorkTitles(scope) { null }, memory)
            val sub2 = backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { w2.notices.collect { again += it } }
            w2.start()
            repeat(20) { Thread.sleep(20); advanceUntilIdle() }
            assertTrue(again.isEmpty())
            w2.stop()
            sub.cancel()
            sub2.cancel()
        } finally {
            server.close()
        }
    }
}
