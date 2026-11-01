package com.coinepro.hq

import com.coinepro.hq.designsystem.FigureFace
import com.coinepro.hq.designsystem.inlineOf
import com.coinepro.hq.designsystem.latinRanges
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.gated
import androidx.compose.ui.text.AnnotatedString
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The owner, 2026-11-01: «ChatGPT: مدل‌های در دسترس نیست: GPT 5.5، GPT 5.3» was drawn «…نیست: 5 ۵٫۵GPT 5، ۳٫GPT». Every Latin run (a
 * model and its version, a path, a URL, a version) is one left-to-right isolate in Latin figures, its digits never Persian; and §28.5
 * notifications deleted for good.
 */
@RunWith(RobolectricTestRunner::class)
class BidiTest {
    private val server = MockWebServer()
    private lateinit var api: Api

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
    }

    @After
    fun tearDown() = server.close()

    /** The runs set Latin in [a], each as it reads (without its isolate marks). */
    private fun figures(a: AnnotatedString): List<String> =
        a.spanStyles.filter { it.item.fontFamily == FigureFace }.map { a.text.substring(it.start, it.end).trim('⁦', '⁩').replace("\u2060", "") }

    /** Every Latin run sits inside an LRI … PDI pair. */
    private fun isolated(a: AnnotatedString, run: String) = assertTrue("$run isolated in «${a.text}»", a.text.replace("\u2060", "").contains("⁦$run⁩"))

    @Test
    fun theOwnersLineKeepsEveryModelWhole() {
        val line = "ChatGPT: مدل‌های در دسترس نیست: GPT 5.5، GPT 5.3"
        assertEquals(listOf("ChatGPT", "GPT 5.5", "GPT 5.3"), latinRanges(line).map { line.substring(it) })
        for (a in listOf(timesFig(line), inlineOf(line))) {
            assertEquals(listOf("ChatGPT", "GPT 5.5", "GPT 5.3"), figures(a))
            isolated(a, "GPT 5.5")
            isolated(a, "GPT 5.3")
            // Never the Persian decimal separator inside a Latin run.
            assertFalse(a.text, a.text.contains("٫"))
        }
    }

    @Test
    fun pathsUrlsVersionsAndCommandsAreOneRunEach() {
        val path = "فایل در /opt/tradeyar/docker-compose.yml است."
        assertEquals(listOf("/opt/tradeyar/docker-compose.yml"), figures(inlineOf(path)))
        val url = "نشانی https://hq.coinepro.com/api/v1/stream?topics=all را باز کن"
        assertEquals(listOf("https://hq.coinepro.com/api/v1/stream?topics=all"), figures(inlineOf(url)))
        val version = "نسخه‌ی v0.10.1 و Pillow 10.2 نصب شد؛ disk 90.4% پر است"
        val f = figures(inlineOf(version))
        assertEquals(listOf("v0.10.1", "Pillow 10.2", "disk 90.4%"), f)
        isolated(inlineOf(version), "Pillow 10.2")
        val cmd = "روی سرور hq-runner pair --company TY را اجرا کن"
        assertEquals(listOf("hq-runner pair --company TY"), figures(timesFig(cmd)))
        // A bare prose count stays Persian (no Latin run), a clock time is a figure, a parenthesis stays outside the run.
        assertEquals(emptyList<String>(), figures(timesFig("۳ کار و 5 پیام")))
        assertEquals(listOf("10:50"), figures(timesFig("ساعت 10:50 آمد")))
        assertEquals(listOf("Never sleeping apps"), figures(timesFig("(در منوی انگلیسی Never sleeping apps)")))
        // An English phrase with its own punctuation is one run.
        assertEquals(listOf("down: otel-collector, tempo", "disk 90.4%"), figures(inlineOf("سلامت خود هاب — down: otel-collector, tempo; disk 90.4%")))
        // A decimal in plain Persian prose still takes the Persian separator.
        assertTrue(inlineOf("رشد 3.5 درصد").text.contains("3٫5"))
    }

    @Test
    fun aLatinRunNeverSplitsAtASpace() {
        val a = inlineOf("فرمان `hq-runner pair --company TY --name ty-web` و GPT 5.5")
        assertTrue(a.text.contains("hq-runner \u2060pair \u2060--company \u2060TY \u2060--name \u2060ty-web"))
        assertTrue(a.text.contains("GPT \u20605.5"))
    }

    @Test
    fun anAnnotatedTextIsIsolatedOnceAndKeepsItsSpans() {
        val once = timesFig(timesFig("مدل GPT 5.5 آماده است"))
        assertEquals(1, Regex("⁦").findAll(once.text).count())
    }

    // ------------------------------------------------------- notifications --
    private fun json(body: String, code: Int = 200) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    @Test
    fun notificationsAreDeletedByIdsOrEveryReadOneUpToTheScreen() = runTest {
        server.enqueue(json("""{"deleted":2}"""))
        assertEquals(2, api.deleteNotifications(listOf("n1", "n2", "n1")).deleted)
        val a = server.takeRequest()
        assertEquals("DELETE", a.method)
        assertEquals("/api/v1/notifications", a.url.encodedPath)
        assertEquals(listOf("n1", "n2"), Api.json.parseToJsonElement(a.body!!.utf8()).jsonObject["ids"]!!.jsonArray.map { it.jsonPrimitive.content })
        server.enqueue(json("""{"deleted":40}"""))
        api.deleteNotifications(allReadBefore = "2026-11-01T08:00:00Z")
        val b = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals("true", b["all_read"]!!.jsonPrimitive.content)
        assertEquals("2026-11-01T08:00:00Z", b["before"]!!.jsonPrimitive.content)
        assertNull(b["ids"])
        // A hub before ⟨1.10.1⟩: the route is missing, «حذف» goes away for this app start.
        server.enqueue(json("""{"type":"about:blank","title":"Method Not Allowed","status":405,"code":"not_found","message_fa":"پیدا نشد.","detail":"Method Not Allowed"}""", 405))
        assertNull(api.gated(HubFeature.DELETE_NOTIFICATIONS) { deleteNotifications(listOf("n1")) })
        assertFalse(api.gaps.has(HubFeature.DELETE_NOTIFICATIONS))
    }
}
