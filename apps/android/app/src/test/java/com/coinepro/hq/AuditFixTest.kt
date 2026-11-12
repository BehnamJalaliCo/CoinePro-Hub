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

    @Test
    fun theKnowledgeListShowsEachEntryOnceAtItsNewestVersion() {
        fun e(ref: String, v: Int, status: String) = com.coinepro.hq.core.net.KnowledgeEntry(ref = ref, layer = "holding", company = "HQ", kind = "fact", titleFa = "t", status = status, version = v)
        val got = com.coinepro.hq.ui.knowledge.latestVersions(listOf(e("K-1", 1, "retired"), e("K-2", 1, "approved"), e("K-1", 2, "approved")))
        assertEquals(listOf("K-1" to 2, "K-2" to 1), got.map { it.ref to it.version })
    }

    @Test
    fun shapesTheAppSendsBackComeBackWhole() {
        // a line's version: who made it is `{kind, code}`, its body has no ref
        val v = Api.json.decodeFromString(com.coinepro.hq.core.net.LineVersion.serializer(), """{"line":"LN-1","version":2,"body":{"template":"t","steps":[],"caps":{}},"by":{"kind":"owner","code":"owner"},"at":"2026-11-11T10:00:00Z","note_fa":"n"}""")
        assertEquals("owner", v.by?.kind)
        assertEquals("t", (v.body?.get("template") as kotlinx.serialization.json.JsonPrimitive).content)
        // a series target through a company runner keeps its server and command
        val t = Api.json.decodeFromString(com.coinepro.hq.core.net.SeriesTarget.serializer(), """{"channel":"runner","placement":"instagram_reel","server":"ig-hub","command":"publish"}""")
        assertEquals("ig-hub" to "publish", t.server to t.command)
        assertTrue(Api.json.encodeToString(com.coinepro.hq.core.net.SeriesTarget.serializer(), t).contains("\"command\":\"publish\""))
        // a «new company» route keeps its kit when it is sent back with the order
        val r = Api.json.decodeFromString(com.coinepro.hq.core.net.OrderRoute29.serializer(), """{"kind":"kit","kit":"media_channel","kit_name_fa":"نوین"}""")
        assertTrue(Api.json.encodeToString(com.coinepro.hq.core.net.OrderRoute29.serializer(), r).contains("\"kit\":\"media_channel\""))
        // the hub's names for a dismissal and a rule's counts
        val d = Api.json.decodeFromString(com.coinepro.hq.core.net.DismissOut.serializer(), """{"moved_work":3,"knowledge_transfer_work":"W-000900"}""")
        assertEquals(3 to "W-000900", d.workReturned to d.transferWork)
        assertEquals(7L, Api.json.decodeFromString(com.coinepro.hq.core.net.RuleCounts.serializer(), """{"runs":7,"violations":1,"fixed":0}""").applied)
    }

    @Test
    fun whatAPersianKeyboardTypesReadsAsItsNumber() {
        assertEquals("125.5", com.coinepro.hq.core.data.asciiDigits("۱۲۵٫۵"))
        assertEquals("1250", com.coinepro.hq.core.data.usdtInput("۱٬۲۵۰"))
        assertEquals("12.5", com.coinepro.hq.core.data.usdtInput("۱۲٫۵"))
        // the hub's `value_usdt` takes at most four decimals
        assertEquals("1.2345", com.coinepro.hq.core.data.usdtInput("1.2345"))
        assertEquals(null, com.coinepro.hq.core.data.usdtInput("1.23456"))
        // a lead's pseudonym as the hub takes it
        assertTrue(com.coinepro.hq.core.data.leadContactOk(""))
        assertTrue(com.coinepro.hq.core.data.leadContactOk("tg-user-41"))
        assertFalse(com.coinepro.hq.core.data.leadContactOk("tg-41"))
        assertFalse(com.coinepro.hq.core.data.leadContactOk("کاربر تلگرام"))
    }
}
