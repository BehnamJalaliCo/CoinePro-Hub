package com.coinepro.hq

import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.TokenSource
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** The Android client against contract §1–§2: Bearer session, X-HQ-Client, Idempotency-Key, step-up header,
 *  snake_case JSON, Problem errors with a Persian message, and a 401 that ends the session. */
@RunWith(RobolectricTestRunner::class)
class ApiContractTest {
    private val server = MockWebServer()
    private var token: String? = "t0ken"
    private val tokens = object : TokenSource {
        override fun token() = token
        override fun clear() { token = null }
    }
    private lateinit var api: Api

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), tokens)
    }

    @After
    fun tearDown() = server.close()

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    @Test
    fun getSendsBearerAndClientHeaders() = runTest {
        server.enqueue(json(200, """{"decisions_pending":4,"decisions_by_risk":{"low":2,"medium":1,"high":1},"deliverables_unrated":2,"messages_unread":3,"khalvat":false,"notifications":{"urgent":0,"decision":1,"report":0,"info":2,"learning":1},"new_field":"ignored"}"""))
        val inbox = api.inbox()
        val req = server.takeRequest()
        assertEquals("/api/v1/inbox/summary", req.url.encodedPath)
        assertEquals("Bearer t0ken", req.headers["Authorization"])
        assertEquals("android", req.headers["X-HQ-Client"])
        assertNull(req.headers["Idempotency-Key"])
        assertEquals(4, inbox.decisionsPending)
        assertEquals(1, inbox.decisionsByRisk.high)
        assertEquals(1, inbox.notifications["decision"])
    }

    @Test
    fun postCarriesIdempotencyKeyAndStepUp() = runTest {
        server.enqueue(json(200, """{"id":"d1","ref":"D-000014","company":"TY","kind":"hire","title":"t","status":"approved","proposer":{"code":"TY-TECH-MGR","kind":"agent"},"created_at":"2026-10-17T10:00:00Z","resolution":"M-0007"}"""))
        val d = api.approve("D-000014", null, "step-up-token")
        val req = server.takeRequest()
        assertEquals("/api/v1/decisions/D-000014/approve", req.url.encodedPath)
        assertNotNull(req.headers["Idempotency-Key"])
        assertEquals("step-up-token", req.headers["X-Step-Up"])
        assertTrue(req.body!!.utf8().contains("\"amendments\":null"))
        assertEquals("M-0007", d.resolution)
    }

    @Test
    fun problemBecomesPersianError() = runTest {
        server.enqueue(json(409, """{"type":"about:blank","title":"Conflict","status":409,"code":"already_decided","message_fa":"این تصمیم قبلاً گرفته شده است."}"""))
        try {
            api.decision("D-1")
            fail("expected ApiException")
        } catch (e: ApiException) {
            assertEquals(409, e.status)
            assertEquals("already_decided", e.code)
            assertEquals("این تصمیم قبلاً گرفته شده است.", e.messageFa)
        }
        assertEquals("t0ken", token)
    }

    @Test
    fun unauthorizedEndsTheSession() = runTest {
        server.enqueue(json(401, """{"code":"unauthenticated","message_fa":"دوباره وارد شو.","status":401,"title":"Unauthorized","type":"about:blank"}"""))
        try {
            api.inbox()
            fail("expected ApiException")
        } catch (e: ApiException) {
            assertTrue(e.isAuth)
        }
        assertNull(token)
    }

    @Test
    fun workByRefResolvesThroughSearch() = runTest {
        server.enqueue(json(200, """{"items":[{"id":"6f1c","ref":"W-000104","company":"FX","title":"x","status":"queued"}],"next_cursor":null}"""))
        server.enqueue(json(200, """{"id":"6f1c","ref":"W-000104","company":"FX","title":"x","status":"queued","chain":[]}"""))
        val w = api.workOne("W-000104")
        assertEquals("q=W-000104&limit=5", server.takeRequest().url.encodedQuery)
        assertEquals("/api/v1/work/6f1c", server.takeRequest().url.encodedPath)
        assertEquals("6f1c", w.id)
    }
}
