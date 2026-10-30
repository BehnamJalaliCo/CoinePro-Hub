package com.coinepro.hq

import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.diag.ErrorLog
import com.coinepro.hq.core.diag.LEVEL_ERROR
import com.coinepro.hq.core.diag.LEVEL_INFO
import com.coinepro.hq.core.diag.LEVEL_WARNING
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.ApiFailure
import java.io.File
import java.time.Instant
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** «خطاخوان»: what is kept (and what never is), a fresh log per version with the old ones archived, exact times and sequence numbers,
 *  repeats counted, a hub restart's burst collapsed into one entry, an expected 404 taken back, the cap, a crash, and the report. */
@RunWith(RobolectricTestRunner::class)
class ErrorLogTest {
    private val ctx get() = ApplicationProvider.getApplicationContext<android.content.Context>()
    private fun dir(name: String) = File(ctx.cacheDir, name)
    private fun log(name: String, app: String = "0.4.0 (400)", fresh: Boolean = true, session: Boolean = false) =
        ErrorLog(ctx, dir(name).apply { if (fresh) deleteRecursively() }, app = app, startSession = session)

    private fun at(iso: String) { HqClock.fixed = Instant.parse(iso) }

    @After
    fun tearDown() { HqClock.fixed = null }

    private fun waitWrites() = Thread.sleep(150)

    @Test
    fun pathsLoseIdsAndQueriesTheirValues() {
        assertEquals("/api/v1/files/{id}", ErrorLog.maskPath("/api/v1/files/0192f0aa-0000-7000-8000-000000000001"))
        assertEquals("/api/v1/deliverables/O-000029/file", ErrorLog.maskPath("/api/v1/deliverables/O-000029/file"))
        assertEquals("/api/v1/employees/TY-CEO", ErrorLog.maskPath("/api/v1/employees/TY-CEO"))
        assertEquals("/api/v1/support/conversations?q=…&company=TY&cursor=…", ErrorLog.maskPath("/api/v1/support/conversations?q=%D8%B9%D9%84%DB%8C&company=TY&cursor=eyJhIjoxfQ"))
        assertEquals("/api/v1/auth/devices/{token}/revoke", ErrorLog.maskPath("/api/v1/auth/devices/AbCdEfGhIjKlMnOpQrStUvWxYz012345/revoke"))
        assertEquals("customer {email} paid {phone}", ErrorLog.mask("customer ali@example.com paid +98 912 345 6789"))
        // A long class name is not a token.
        assertEquals("GetCredentialCancellationException", ErrorLog.mask("GetCredentialCancellationException"))
    }

    @Test
    fun secretsAreRedactedFromHeadersAndText() {
        // A token-like header never survives: neither as a header nor quoted in a sentence.
        val h = ErrorLog.safeHeaders(mapOf("Authorization" to "Bearer abc.def.ghi", "Set-Cookie" to "hq_session=s3cr3t", "X-Step-Up" to "su-123", "Server" to "Caddy", "Retry-After" to "5"))
        assertEquals(mapOf("server" to "Caddy", "retry-after" to "5"), h)
        assertEquals("Authorization: {redacted}", ErrorLog.redact("Authorization: Bearer abc.def.ghi"))
        // A password field (JSON or form) loses its value, its name stays so the report says what was there.
        val json = ErrorLog.mask("""{"user":"owner","password":"hunter2","note":"ok"}""")
        assertFalse(json.contains("hunter2"))
        assertTrue(json.contains("\"password\":{redacted}"))
        assertFalse(ErrorLog.mask("token=eyJhbGciOi.payload.sig&x=1").contains("eyJhbGciOi"))
        // A key-like value assembled at runtime, so the source holds no key shape for a secret scanner.
        val apiKey = listOf("sk", "live", "1234567890").joinToString("-")
        assertFalse(ErrorLog.mask("api_key: $apiKey").contains("sk-live"))
        // A server message that quotes a secret is logged without it.
        val l = log("redact")
        l.record(ApiFailure("http", "POST", "/api/v1/connections/x/secret", 422, "validation_failed", "Unprocessable", message = "secret=abcd1234 is not a valid key; Authorization: Bearer xyz"))
        val e = l.entries.value.first()
        assertFalse(e.message!!.contains("abcd1234"))
        assertFalse(e.message!!.contains("xyz"))
    }

    @Test
    fun aNewVersionStartsEmptyAndArchivesThePrevious() {
        val a = log("versions", app = "0.3.0 (300)", session = true)
        a.record(ApiFailure("http", "GET", "/api/v1/work", 500, "internal_error", "Internal"))
        waitWrites()
        assertEquals(2, a.entries.value.size)
        // Same version again: the log goes on.
        val again = log("versions", app = "0.3.0 (300)", fresh = false, session = true)
        assertEquals(3, again.entries.value.size)
        waitWrites()
        // A new version: empty but for its own session line, the old one archived and readable apart.
        val b = log("versions", app = "0.4.0 (400)", fresh = false, session = true)
        assertEquals(listOf("session"), b.entries.value.map { it.kind })
        assertEquals(1L, b.entries.value.single().id)
        assertTrue(b.entries.value.single().detail!!.contains("app started v0.4.0 (400)"))
        assertEquals(listOf("0.3.0 (300)"), b.archives().map { it.app })
        assertEquals(3, b.archived("0.3.0 (300)").size)
        waitWrites()
        // Only the last versions are kept.
        for (v in listOf("0.5.0 (500)", "0.6.0 (600)", "0.7.0 (700)")) { log("versions", app = v, fresh = false, session = true); waitWrites(); Thread.sleep(20) }
        val last = log("versions", app = "0.8.0 (800)", fresh = false, session = true)
        assertEquals(ErrorLog.KEEP_VERSIONS, last.archives().size)
        assertFalse(last.archives().any { it.app == "0.3.0 (300)" })
    }

    @Test
    fun everyEntryHasItsSequenceExactTimeAndLevel() {
        val l = log("seq")
        at("2026-10-29T10:33:12.345Z")
        l.record(ApiFailure("decode", "GET", "/api/v1/media/voices", 200, "contract_mismatch", null, "req-1", "$[0].mem_mb", "Expected Int"))
        at("2026-10-29T10:33:13.001Z")
        l.record(ApiFailure("http", "POST", "/api/v1/work", 422, "validation_failed", "Unprocessable", durationMs = 87))
        l.note("passkey", LEVEL_INFO, "cancelled", "GetCredentialCancellationException")
        val (third, second, first) = l.entries.value
        assertEquals(listOf(1L, 2L, 3L), listOf(first.id, second.id, third.id))
        assertEquals("2026-10-29T10:33:12.345Z", first.at)
        assertEquals("2026-10-29 14:03:12.345", ErrorLog.local(first.at))
        assertEquals("2026-10-29 10:33:12.345", ErrorLog.utc(first.at))
        assertEquals(LEVEL_ERROR, first.level)
        assertEquals(LEVEL_WARNING, second.level)
        assertEquals(87L, second.durationMs)
        assertEquals(LEVEL_INFO, third.level)
    }

    @Test
    fun aHubRestartsBurstIsOneEntryAndRealErrorsStayApart() {
        val l = log("burst")
        at("2026-10-29T10:00:00.000Z")
        // A real 500 and a 404 stay as they are.
        l.record(ApiFailure("http", "GET", "/api/v1/treasury/summary", 500, "internal_error", "Internal"))
        // Fifteen 502s and three network failures over twenty seconds, on every endpoint: one entry.
        val paths = listOf("/api/v1/inbox/summary", "/api/v1/work", "/api/v1/decisions", "/api/v1/companies", "/api/v1/runs")
        var t = Instant.parse("2026-10-29T10:00:05.000Z")
        repeat(18) { i ->
            HqClock.fixed = t
            if (i % 6 == 5) l.record(ApiFailure("network", "GET", paths[i % paths.size], null, "network_error", "ConnectException"))
            else l.record(ApiFailure("http", "GET", paths[i % paths.size], 502, "hub_unreachable", "Bad Gateway"))
            t = t.plusMillis(1_150)
        }
        val list = l.entries.value
        assertEquals(listOf("unreachable", "http"), list.map { it.kind })
        val b = list.first()
        assertEquals(18, b.count)
        assertEquals(mapOf("502" to 15, "network" to 3), b.tally)
        assertEquals("2026-10-29T10:00:05.000Z", b.at)
        assertEquals(LEVEL_WARNING, b.level)
        assertTrue(b.paths.size in 1..ErrorLog.BURST_PATHS)
        val text = ErrorLog.block(b)
        assertTrue(text, text.contains("hub unreachable, 18 requests, 13:30:05.000–13:30:24.550"))
        assertTrue(text.contains("failures: 502 ×15, network ×3"))
        // A real 4xx after the burst is its own entry, as before.
        l.record(ApiFailure("http", "POST", "/api/v1/work", 422, "validation_failed", "Unprocessable"))
        assertEquals(listOf("http", "unreachable", "http"), l.entries.value.map { it.kind })
    }

    @Test
    fun twoTransientFailuresAloneAreNotABurst() {
        val l = log("pair")
        at("2026-10-29T10:00:00.000Z")
        l.record(ApiFailure("http", "GET", "/api/v1/work", 502, "hub_unreachable", "Bad Gateway"))
        at("2026-10-29T10:05:00.000Z")
        l.record(ApiFailure("http", "GET", "/api/v1/work", 503, "hub_unreachable", "Service Unavailable"))
        assertEquals(listOf("http", "http"), l.entries.value.map { it.kind })
    }

    @Test
    fun repeatsAreCountedAndAnExpectedFailureIsTakenBack() {
        val l = log("t1")
        val f = ApiFailure("decode", "GET", "/api/v1/media/voices", 200, "contract_mismatch", null, "req-1", "$[0].mem_mb", "Unexpected JSON token")
        val a = l.record(f)!!
        val b = l.record(f)!!
        assertEquals(a, b)
        assertEquals(1, l.entries.value.size)
        assertEquals(2, l.entries.value.single().count)
        val c = l.record(ApiFailure("http", "GET", "/api/v1/stars/rollup?period=week", 404, "not_found", "Not Found"))!!
        l.forget(c)
        assertEquals(listOf("decode"), l.entries.value.map { it.kind })
    }

    @Test
    fun keepsTheLastThousandOfThisVersion() {
        val l = log("t2")
        repeat(ErrorLog.MAX + 20) { i -> l.record(ApiFailure("http", "GET", "/api/v1/x/$i", 500, "internal_error", "Internal")) }
        assertEquals(ErrorLog.MAX, l.entries.value.size)
        assertEquals("/api/v1/x/${ErrorLog.MAX + 19}", l.entries.value.first().path)
        assertEquals((ErrorLog.MAX + 20).toLong(), l.entries.value.first().id)
    }

    @Test
    fun breadcrumbsAndContextComeWithEachFailure() {
        val l = log("crumbs")
        l.screen = "home"
        l.crumb("sheet tools")
        l.screen = "orders"
        l.foreground = true
        l.record(ApiFailure("http", "GET", "/api/v1/work", 500, "internal_error", "Internal", "rid-1", headers = mapOf("Server" to "uvicorn", "Authorization" to "Bearer x")))
        val e = l.entries.value.first()
        assertEquals(listOf("screen home", "sheet tools", "screen orders"), e.breadcrumbs.map { it.substringAfter(' ') })
        assertEquals("orders", e.screen)
        assertEquals(true, e.foreground)
        assertEquals(mapOf("server" to "uvicorn"), e.headers)
        assertEquals("rid-1", e.requestId)
        // An info line carries no breadcrumbs.
        l.note("stream", LEVEL_INFO, "reconnected", "after 4 s")
        assertTrue(l.entries.value.first().breadcrumbs.isEmpty())
    }

    @Test
    fun aCrashKeepsItsStackAndTheReportHasTheHeaderAndOneBlockPerEntry() {
        val l = log("t3")
        at("2026-10-29T10:33:12.345Z")
        l.screen = "outputs"
        l.record(ApiFailure("decode", "GET", "/api/v1/media/voices", 200, "contract_mismatch", null, "req-7", "$[0].samples[0].file", "missing id, name (FileRef)", durationMs = 312))
        l.crash(Thread.currentThread(), IllegalStateException("boom for ali@example.com"))
        val e = l.entries.value.first()
        assertEquals("crash", e.kind)
        assertTrue(e.stack!!.contains("ErrorLogTest"))
        assertFalse(e.detail!!.contains("ali@example.com"))
        val r = l.report()
        assertTrue(r.startsWith("CoinePro HQ — error log (خطاخوان)\napp 0.4.0 (400) · "))
        assertTrue(r.contains("device "))
        assertTrue(r.contains("Android "))
        assertTrue(r.contains("time zone Asia/Tehran"))
        assertTrue(r.contains("exported 2026-10-29 14:03:12.345 Asia/Tehran · 2026-10-29 10:33:12.345 UTC"))
        assertTrue(r.contains("2 entries (2 error, 0 warning, 0 info), newest first"))
        assertTrue(r.contains("#2 · error · crash"))
        assertTrue(r.contains("#1 · error · contract mismatch (the answer does not decode)"))
        assertTrue(r.contains("time: 2026-10-29 14:03:12.345 Asia/Tehran · 2026-10-29 10:33:12.345 UTC"))
        assertTrue(r.contains("request: GET /api/v1/media/voices → 200 · 312 ms"))
        assertTrue(r.contains("field: $[0].samples[0].file"))
        assertTrue(r.contains("request-id: req-7"))
        assertTrue(r.contains("screen: outputs"))
        assertNull(l.entries.value.last().stack)
    }
}
