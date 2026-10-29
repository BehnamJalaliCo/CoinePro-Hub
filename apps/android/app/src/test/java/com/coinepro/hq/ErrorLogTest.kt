package com.coinepro.hq

import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.diag.ErrorLog
import com.coinepro.hq.core.net.ApiFailure
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** «خطاخوان»: what is kept (and what never is), repeats counted, an expected 404 taken back, the cap, a crash, and the report. */
@RunWith(RobolectricTestRunner::class)
class ErrorLogTest {
    private fun log(name: String) = ErrorLog(ApplicationProvider.getApplicationContext(), File(ApplicationProvider.getApplicationContext<android.content.Context>().cacheDir, name).apply { deleteRecursively() })

    @Test
    fun pathsLoseIdsAndQueriesTheirValues() {
        assertEquals("/api/v1/files/{id}", ErrorLog.maskPath("/api/v1/files/0192f0aa-0000-7000-8000-000000000001"))
        assertEquals("/api/v1/deliverables/O-000029/file", ErrorLog.maskPath("/api/v1/deliverables/O-000029/file"))
        assertEquals("/api/v1/employees/TY-CEO", ErrorLog.maskPath("/api/v1/employees/TY-CEO"))
        assertEquals("/api/v1/support/conversations?q=…&company=TY&cursor=…", ErrorLog.maskPath("/api/v1/support/conversations?q=%D8%B9%D9%84%DB%8C&company=TY&cursor=eyJhIjoxfQ"))
        assertEquals("/api/v1/auth/devices/{token}/revoke", ErrorLog.maskPath("/api/v1/auth/devices/AbCdEfGhIjKlMnOpQrStUvWxYz012345/revoke"))
        assertEquals("customer {email} paid {phone}", ErrorLog.mask("customer ali@example.com paid +98 912 345 6789"))
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
    fun keepsTheLastThreeHundred() {
        val l = log("t2")
        repeat(ErrorLog.MAX + 20) { i -> l.record(ApiFailure("http", "GET", "/api/v1/x/$i", 500, "internal_error", "Internal")) }
        assertEquals(ErrorLog.MAX, l.entries.value.size)
        assertEquals("/api/v1/x/${ErrorLog.MAX + 19}", l.entries.value.first().path)
    }

    @Test
    fun aCrashKeepsItsStackAndTheReportIsOneBlockPerEntry() {
        val l = log("t3")
        l.screen = "outputs"
        l.record(ApiFailure("decode", "GET", "/api/v1/media/voices", 200, "contract_mismatch", null, "req-7", "$[0].samples[0].file", "missing id, name (FileRef)"))
        l.crash(Thread.currentThread(), IllegalStateException("boom for ali@example.com"))
        val e = l.entries.value.first()
        assertEquals("crash", e.kind)
        assertTrue(e.stack!!.contains("ErrorLogTest"))
        assertFalse(e.detail!!.contains("ali@example.com"))
        val r = l.report()
        assertTrue(r.startsWith("CoinePro HQ — error log (خطاخوان)\napp "))
        assertTrue(r.contains("2 entries, newest first"))
        assertTrue(r.contains("#1 · ") && r.contains("crash"))
        assertTrue(r.contains("#2 · ") && r.contains("contract mismatch (the answer does not decode)"))
        assertTrue(r.contains("request: GET /api/v1/media/voices → 200"))
        assertTrue(r.contains("field: $[0].samples[0].file"))
        assertTrue(r.contains("request-id: req-7"))
        assertTrue(r.contains("screen: outputs"))
    }
}
