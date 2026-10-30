package com.coinepro.hq

import com.coinepro.hq.core.data.CompanyDelete
import com.coinepro.hq.core.data.DeleteOutcome
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.TokenSource
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** «حذف شرکت»: never the holding, only after the exact code, then the passkey; a company with a history is archived instead, and a hub
 *  without the call (the server gap) is met with archiving, never with a passkey asked for nothing. */
@RunWith(RobolectricTestRunner::class)
class CompanyDeleteTest {
    private val server = MockWebServer()
    private lateinit var api: Api
    private val signed = mutableListOf<Pair<String, String>>()
    private val stepUp: suspend (String, String) -> String = { a, t -> signed += a to t; "su-token" }

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
    }

    @After
    fun tearDown() = server.close()

    private fun problem(status: Int, code: String) =
        MockResponse.Builder().code(status).addHeader("Content-Type", "application/problem+json").body("""{"type":"about:blank","title":"x","status":$status,"code":"$code","message_fa":"پیام"}""").build()

    @Test
    fun theGuardWantsTheExactCodeAndNeverTheHolding() {
        assertTrue(CompanyDelete.matches("IG", "IG"))
        assertTrue(CompanyDelete.matches(" ig ", "IG"))
        assertFalse(CompanyDelete.matches("I", "IG"))
        assertFalse(CompanyDelete.matches("IGX", "IG"))
        assertFalse(CompanyDelete.matches("", ""))
        assertTrue(CompanyDelete.canConfirm("IG", "IG", holding = false))
        assertFalse(CompanyDelete.canConfirm("HQ", "HQ", holding = true))
        assertFalse(CompanyDelete.canConfirm("IG", "IG", holding = false, busy = true))
        assertFalse(CompanyDelete.canConfirm("TY", "IG", holding = false))
    }

    @Test
    fun outcomes() {
        assertEquals(DeleteOutcome.DELETED, CompanyDelete.outcome(null))
        assertEquals(DeleteOutcome.HAS_HISTORY, CompanyDelete.outcome(ApiException(409, "company_has_history", "")))
        // The live hub today: the route has GET and PATCH only, so DELETE is 405 (its handler names it not_found).
        assertEquals(DeleteOutcome.NOT_SERVED, CompanyDelete.outcome(ApiException(405, "not_found", "")))
        assertEquals(DeleteOutcome.NOT_SERVED, CompanyDelete.outcome(ApiException(404, "internal_error", "")))
        assertEquals(DeleteOutcome.GONE, CompanyDelete.outcome(ApiException(404, "not_found", "")))
        assertEquals(DeleteOutcome.FAILED, CompanyDelete.outcome(ApiException(403, "step_up_invalid", "")))
        assertEquals(DeleteOutcome.FAILED, CompanyDelete.outcome(ApiException(409, "version_conflict", "")))
    }

    @Test
    fun deleteAsksThePasskeyOnlyWhenTheHubWantsIt() = runTest {
        server.enqueue(problem(403, "step_up_required"))
        server.enqueue(MockResponse.Builder().code(204).build())
        api.deleteCompany("IG", stepUp)
        val first = server.takeRequest()
        assertEquals("DELETE", first.method)
        assertEquals("/api/v1/companies/IG", first.url.encodedPath)
        assertNull(first.headers["X-Step-Up"])
        val second = server.takeRequest()
        assertEquals("su-token", second.headers["X-Step-Up"])
        assertEquals(listOf("company.delete" to "IG"), signed)
    }

    @Test
    fun aHubWithoutDeleteIsNotAskedForAPasskey() = runTest {
        server.enqueue(problem(405, "not_found"))
        try {
            api.deleteCompany("IG", stepUp)
            fail()
        } catch (e: ApiException) {
            assertEquals(DeleteOutcome.NOT_SERVED, CompanyDelete.outcome(e))
        }
        assertTrue(signed.isEmpty())
    }

    @Test
    fun archivingIsAPatchWithIfMatchAndThePasskey() = runTest {
        server.enqueue(MockResponse.Builder().code(200).addHeader("Content-Type", "application/json").body("""{"id":"1","code":"IG","kind":"company","status":"archived","version":3}""").build())
        val co = Company("1", "IG", "company", version = 2)
        val out = api.patchCompany(co, archive = true, stepUp = stepUp)
        val req = server.takeRequest()
        assertEquals("PATCH", req.method)
        assertEquals("\"2\"", req.headers["If-Match"])
        assertEquals("su-token", req.headers["X-Step-Up"])
        assertEquals("""{"status":"archived"}""", req.body?.utf8())
        assertEquals(listOf("company.archive" to "IG"), signed)
        assertEquals("archived", out.status)
    }
}
