package com.coinepro.hq

import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.HistoryOut
import com.coinepro.hq.core.net.ShadowReport
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ⟨2026-11-11⟩ The hub's audit of the Android app: each finding that was a shape or a rule the app read wrong, read as the hub writes it
 * now (the screens' own tests cover what they draw).
 */
class AuditFixTest {
    @Test
    fun aShadowTestsResultAndAHistoryImportReadAsTheHubWritesThem() {
        // the hub's model writes `pass_` (a Python keyword); an older shape's `pass` reads too
        val r = Api.json.decodeFromString(ShadowReport.serializer(), """{"company":"TY","suite":"s","at":"2026-11-11T10:00:00Z","total":10,"correct":9,"pass_":true,"threshold":0.9}""")
        assertTrue(r.pass)
        assertTrue(Api.json.decodeFromString(ShadowReport.serializer(), """{"company":"TY","suite":"s","at":"x","pass":true}""").pass)
        assertFalse(Api.json.decodeFromString(ShadowReport.serializer(), """{"company":"TY","suite":"s","at":"x"}""").pass)
        // `SupportHistoryOut`: the cases kept, and a failed import says so
        val h = Api.json.decodeFromString(HistoryOut.serializer(), """{"id":"u","company":"TY","state":"done","format":"csv","pairs_found":140,"cases_kept":100,"topics":{},"suite":"support-shadow-TY@2","error":null}""")
        assertEquals(100, h.casesKept)
        assertEquals("done", h.state)
        assertEquals("failed", Api.json.decodeFromString(HistoryOut.serializer(), """{"state":"failed","error":"فایل خوانده نشد"}""").state)
    }
}
