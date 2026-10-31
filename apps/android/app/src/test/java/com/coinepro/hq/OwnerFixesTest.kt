package com.coinepro.hq

import com.coinepro.hq.core.data.JsonBits
import com.coinepro.hq.core.data.ThreadGroups
import com.coinepro.hq.core.format.percentOf
import com.coinepro.hq.core.format.percentText
import com.coinepro.hq.core.format.uptimeText
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.CatalogueSection
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.Thread
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The owner's three from the phone (2026-10-31): an uptime shown «10000.0%» (a percent scaled twice), the messages per company, and a
 * catalogue whose sections showed raw JSON.
 */
@RunWith(RobolectricTestRunner::class)
class OwnerFixesTest {
    // ---------------------------------------------------------------- percent --
    @Test
    fun aShareReadsTheSameAsAFractionOrAPercent() {
        assertEquals(99.8, percentOf(0.998), 1e-9)
        assertEquals(99.8, percentOf(99.8), 1e-9)
        assertEquals(100.0, percentOf(1.0), 1e-9)
        assertEquals(100.0, percentOf(100.0), 1e-9)
        assertEquals(100.0, percentOf(10000.0), 1e-9)
        assertEquals("99.8%", uptimeText(0.998))
        assertEquals("99.8%", uptimeText(99.8))
        assertEquals("100%", uptimeText(1.0))
        assertEquals("100%", uptimeText(100.0))
        assertEquals("0%", uptimeText(0.0))
        assertEquals("—", uptimeText(null))
        assertEquals("38%", percentText(0.38))
        assertEquals("38%", percentText(38.0))
        assertEquals("—", percentText(Double.NaN))
        // A change against a base may pass 100% and is never read as a percent already.
        assertEquals("150%", com.coinepro.hq.ui.v18.change01(1.5))
    }

    // ---------------------------------------------------------------- messages --
    private fun t(code: String, kind: String, co: String?, unread: Int = 0, at: String = "2026-10-31T08:00:00Z") =
        Thread(id = code, code = code, kind = kind, company = co, titleFa = code, lastMessageAt = at, unread = unread)

    @Test
    fun messagesAreGroupedByCompanyHoldingFirstCeoThenManagersByDepartment() {
        val companies = listOf(Company("h", "HQ", "holding", "هلدینگ"), Company("t", "TY", "company", "تریدیار"), Company("f", "FX", "company", "کوینه‌پرو FX"))
        val groups = ThreadGroups.group(
            listOf(
                t("TY-GROWTH-MGR", "manager", "TY", 1, "2026-10-31T09:00:00Z"),
                t("FX-CEO", "ceo", "FX", 2),
                t("N", "overseer", "HQ", 1),
                t("TY-TECH-MGR", "manager", "TY", 0, "2026-10-30T09:00:00Z"),
                t("A", "advisor", "HQ"),
                t("TY-CEO", "ceo", "TY", 3, "2026-10-29T09:00:00Z"),
                t("L", "legal", null),
                t("IG-CEO", "ceo", "IG"),
            ),
            companies,
        )
        assertEquals(listOf("HQ", "TY", "FX", "IG"), groups.map { it.company })
        assertTrue(groups.first().holding)
        assertEquals(listOf("A", "N", "L"), groups[0].threads.map { it.code })
        // The CEO first even when older; the managers by department (tech before growth), not by time.
        assertEquals(listOf("TY-CEO", "TY-TECH-MGR", "TY-GROWTH-MGR"), groups[1].threads.map { it.code })
        assertEquals(listOf(1, 4, 2, 0), groups.map { it.unread })
        assertEquals("GROWTH", ThreadGroups.departmentOf(t("TY-GROWTH-MGR", "manager", "TY")))
    }

    // --------------------------------------------------------------- catalogue --
    @Test
    fun jsonInProseIsDataNeverText() {
        val parts = JsonBits.split("هجده workflow در n8n؛ \"rows\": [[\"signal-broadcast\", 14], [\"kyc-reminder\", 6]] و سه cron.")
        assertEquals(3, parts.size)
        assertEquals("هجده workflow در n8n", (parts[0] as JsonBits.Part.Prose).text)
        val data = (parts[1] as JsonBits.Part.Data).value as JsonObject
        val table = (JsonBits.shape(data) as JsonBits.Shape.Table).table
        assertEquals("signal-broadcast", table.cell(0, 0))
        assertEquals("6", table.cell(1, 1))
        assertEquals("و سه cron.", (parts[2] as JsonBits.Part.Prose).text)
        for (p in parts) if (p is JsonBits.Part.Prose) assertFalse(p.text, p.text.contains("[[") || p.text.contains("\"rows\""))
    }

    @Test
    fun columnsAndRowsSideBySideAreOneTable() {
        val parts = JsonBits.split("دستورها: \"columns\": [\"دستور\", \"کاربرد\"], \"rows\": [[\"/plan\", \"پلن\"]]")
        assertEquals(2, parts.size)
        val table = (JsonBits.shape((parts[1] as JsonBits.Part.Data).value) as JsonBits.Shape.Table).table
        assertEquals(listOf("دستور", "کاربرد"), table.header)
        assertEquals("پلن", table.cell(0, 1))
    }

    @Test
    fun listsAndObjectsHaveTheirShapes() {
        val lines = JsonBits.shape(Api.json.parseToJsonElement("""["یک", "دو"]"""))
        assertEquals(listOf("یک", "دو"), (lines as JsonBits.Shape.Lines).lines)
        val objects = JsonBits.shape(Api.json.parseToJsonElement("""[{"name":"api","port":8000},{"name":"redis","port":6379,"note":{"a":1}}]""")) as JsonBits.Shape.Table
        assertEquals(listOf("name", "port", "note"), objects.table.header)
        assertEquals("6379", objects.table.cell(1, 1))
        assertEquals("a: 1", objects.table.cell(1, 2))
        assertEquals("—", objects.table.cell(0, 2))
        // A text with a bracket that is not JSON stays prose.
        assertEquals(listOf(JsonBits.Part.Prose("[ریسک] پورت باز")), JsonBits.split("[ریسک] پورت باز"))
        assertFalse(JsonBits.hasData("بی‌داده"))
    }

    @Test
    fun aSectionReadsTheHubsShape() {
        val s = Api.json.decodeFromString(
            CatalogueSection.serializer(),
            """{"key":"automations","title_fa":"اتوماسیون‌ها","summary_fa":"خلاصه","tables":[{"title_fa":"n8n","columns":["workflow","گره‌ها"],"rows":[["a",3],{"workflow":"b","گره‌ها":5}]}],"notes_fa":["یک","دو"]}""",
        )
        assertEquals("خلاصه", s.summary)
        assertEquals(listOf("یک", "دو"), s.notes)
        val t = s.tables.single()
        assertEquals("3", t.cell(0, 1))
        assertEquals("5", t.cell(1, 1))
        // An older hub's markdown notes still read.
        assertEquals(listOf("قدیمی"), Api.json.decodeFromString(CatalogueSection.serializer(), """{"notes_md":"قدیمی"}""").notes)
        assertTrue(s.tables.single().rows.last() is JsonObject)
        assertTrue(s.tables.single().rows.first() is JsonArray)
    }
}
