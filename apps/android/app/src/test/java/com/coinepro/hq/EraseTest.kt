package com.coinepro.hq

import com.coinepro.hq.core.format.decisionKind
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.EraseKind
import com.coinepro.hq.core.net.ErasePreview
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.eraseCardOf
import com.coinepro.hq.core.net.eraseCountsFa
import com.coinepro.hq.ui.cartable.needsStepUp
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.jsonObject
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * ⟨1.19⟩ Contract §37, erasing for good: the preview as the owner reads it (counts in Persian digits, what stays), the three erases
 * each sealed on its own action and ref with the press's own UUID key, and an agent's `erase` card in the cartable (sealed, its counts).
 */
@RunWith(RobolectricTestRunner::class)
class EraseTest {
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

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    @Test
    fun thePreviewReadsInPlainPersian() {
        val p = Api.json.decodeFromString(
            ErasePreview.serializer(),
            """{"ref":"F-0099","kind":"session","title_fa":"یک لوگوی تازه","counts":{"turns":12,"files":3,"outputs":0,"works":2,"notifications":1,"later":4},"keeps_fa":["یک خط در دفتر حسابرسی"]}""",
        )
        // Zeros and names the app does not know yet are left out; the counts are a sentence's, in Persian digits.
        assertEquals("۱۲ گفته، ۳ فایل، ۲ کار، ۱ اعلان", eraseCountsFa(p.counts))
        assertEquals(listOf("یک خط در دفتر حسابرسی"), p.keepsFa)
        assertEquals("", eraseCountsFa(ErasePreview().counts))
    }

    @Test
    fun eachEraseIsShownFirstThenSealedOnItsRefWithItsOwnKey() = runTest {
        val cases = listOf(
            Triple(EraseKind.SESSION, "F-0099", "/api/v1/orders/F-0099/erase"),
            Triple(EraseKind.RECORD, "AR-000110", "/api/v1/archive/records/AR-000110/erase"),
            Triple(EraseKind.OUTPUT, "O-000032", "/api/v1/deliverables/O-000032/erase"),
        )
        for ((kind, ref, path) in cases) {
            server.enqueue(json(200, """{"ref":"$ref","kind":"${kind.key}","title_fa":"x","counts":{"files":1}}"""))
            assertEquals(ref, api.erasePreview(kind, ref).ref)
            val get = server.takeRequest()
            assertEquals("GET", get.method)
            assertEquals("$path/preview", get.url.encodedPath)

            server.enqueue(json(200, """{"ref":"$ref","erased":{"files":1}}"""))
            val key = java.util.UUID.randomUUID().toString()
            val out = api.erase(kind, ref, key, stepUp)
            assertEquals(ref, out.ref)
            val post = server.takeRequest()
            assertEquals("POST", post.method)
            assertEquals(path, post.url.encodedPath)
            assertEquals(key, post.headers["Idempotency-Key"])
            assertEquals("su-token", post.headers["X-Step-Up"])
            assertEquals(kind.action to ref, signed.last())
        }
        assertEquals(listOf("session.erase", "archive.erase", "output.erase"), signed.map { it.first })
    }

    @Test
    fun anAgentsEraseCardIsSealedAndCarriesItsPreview() {
        fun card(payload: String) = Api.json.decodeFromString(
            Decision.serializer(),
            Api.json.parseToJsonElement(
                """{"id":"0193b1c2-0301-7d4f-8a2e-000000000301","ref":"D-000301","company":"HQ","kind":"erase","title":"پاک کردن: یک لوگوی تازه","status":"pending","risk":"medium",
                "action_class":"A1","payload":$payload,"proposer":{"kind":"employee","code":"HQ-CEO","display_fa":"مدیرعامل هلدینگ"},
                "created_at":"2026-11-06T08:00:00Z"}""",
            ).jsonObject.toString(),
        )
        val flat = card("""{"kind":"session","ref":"F-0099","why_fa":"گفتی پاکش کنم.","title_fa":"یک لوگوی تازه","counts":{"turns":4},"keeps_fa":["یک خط"]}""")
        val e = eraseCardOf(flat)
        assertEquals(EraseKind.SESSION, e.kind)
        assertEquals("F-0099", e.ref)
        assertEquals("۴ گفته", eraseCountsFa(e.preview.counts))
        assertEquals("گفتی پاکش کنم.", e.whyFa)
        val nested = eraseCardOf(card("""{"kind":"output","ref":"O-000032","preview":{"ref":"O-000032","kind":"output","title_fa":"گزارش","counts":{"files":2},"keeps_fa":[]}}"""))
        assertEquals(EraseKind.OUTPUT, nested.kind)
        assertEquals("گزارش", nested.preview.titleFa)
        assertEquals("۲ فایل", eraseCountsFa(nested.preview.counts))
        assertNull(eraseCardOf(card("""{}""")).kind)
        // The cartable names it and seals it with a fresh passkey.
        assertEquals("پاک کردن", decisionKind("erase").fa)
        assertTrue(needsStepUp(flat))
    }
}
