package com.coinepro.hq

import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubHealth
import com.coinepro.hq.core.net.HubState
import com.coinepro.hq.core.net.TokenSource
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** A hub restarting during a deploy: reads retried quietly, a burst of 502s turns into "the hub is away" (one banner) and the first
 *  answer brings it back; every call carries the id the hub echoes; writes are never retried. */
@RunWith(RobolectricTestRunner::class)
class HubTest {
    private val server = MockWebServer()
    private val tokens = object : TokenSource {
        override fun token() = "t"
        override fun clear() = Unit
    }
    private lateinit var api: Api

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), tokens)
    }

    @After
    fun tearDown() = server.close()

    private companion object {
        const val INBOX = """{"decisions_pending":4,"decisions_by_risk":{"low":2,"medium":1,"high":1},"deliverables_unrated":2,"messages_unread":3,"khalvat":false,"notifications":{"urgent":0,"decision":1,"report":0,"info":2,"learning":1}}"""
    }

    private fun r(code: Int, body: String = "") = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    @Test
    fun aBurstWithinTheWindowMeansTheHubIsAwayAndAnAnswerBringsItBack() {
        var now = 0L
        val h = HubHealth { now }
        repeat(HubHealth.THRESHOLD - 1) { h.transient(); now += 1_000 }
        assertEquals(HubState.OK, h.state.value)
        h.transient()
        assertEquals(HubState.RESTARTING, h.state.value)
        assertTrue(h.outage)
        now += 9_000
        h.ok()
        assertEquals(HubState.OK, h.state.value)
    }

    @Test
    fun failuresFarApartAreNotABurst() {
        var now = 0L
        val h = HubHealth { now }
        repeat(10) { h.transient(); now += HubHealth.WINDOW_MS / 2 }
        assertEquals(HubState.OK, h.state.value)
        // An answer in between clears the count.
        now = 0
        val g = HubHealth { now }
        repeat(HubHealth.THRESHOLD - 1) { g.transient() }
        g.ok()
        g.transient()
        assertEquals(HubState.OK, g.state.value)
    }

    @Test
    fun theProbeBackOffGrowsAndStops() {
        assertEquals(2_000, HubHealth.backoff(0))
        assertTrue(HubHealth.backoff(3) > HubHealth.backoff(2))
        assertEquals(HubHealth.backoff(99), HubHealth.BACKOFF_MS.last())
    }

    @Test
    fun aReadMeetingA502IsRetriedQuietlyWithTheSameRequestId() = runTest {
        val h = HubHealth()
        api.hub = h
        server.enqueue(r(502))
        server.enqueue(r(503))
        server.enqueue(r(200, INBOX))
        assertEquals(4, api.inbox().decisionsPending)
        val first = server.takeRequest()
        val second = server.takeRequest()
        val third = server.takeRequest()
        val id = first.headers["X-Request-Id"]
        assertNotNull(id)
        assertTrue(Regex("^[A-Za-z0-9-]{8,64}$").matches(id!!))
        assertEquals(id, second.headers["X-Request-Id"])
        assertEquals(id, third.headers["X-Request-Id"])
        assertEquals(HubState.OK, h.state.value)
    }

    @Test
    fun aReadThatKeepsFailingIsATransientErrorAndCountsTowardsTheBurst() = runTest {
        val h = HubHealth()
        api.hub = h
        repeat(1 + Api.RETRY_MS.size) { server.enqueue(r(502)) }
        try {
            api.inbox()
            fail("expected a 502")
        } catch (e: ApiException) {
            assertEquals(502, e.status)
            assertTrue(e.transient)
            assertEquals("hub_unreachable", e.code)
        }
        assertEquals(1 + Api.RETRY_MS.size, server.requestCount)
        // One more failing read and the hub is away.
        repeat(1 + Api.RETRY_MS.size) { server.enqueue(r(502)) }
        runCatching { api.inbox() }
        assertTrue(h.outage)
        // The probe asks without logging; any answer but 502–504 is the hub back.
        server.enqueue(r(200, "{}"))
        assertTrue(api.probe())
    }

    @Test
    fun aWriteIsNeverRetried() = runTest {
        server.enqueue(r(502))
        server.enqueue(r(200, "{}"))
        runCatching { api.readAll() }.onSuccess { fail("a write met a 502 and must fail") }
        assertEquals(1, server.requestCount)
        assertFalse(server.takeRequest().headers["Idempotency-Key"].isNullOrBlank())
    }
}
