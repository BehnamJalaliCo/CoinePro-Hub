package com.coinepro.hq

import com.coinepro.hq.core.data.Selection
import com.coinepro.hq.core.data.Watch
import com.coinepro.hq.core.data.WatchKind
import com.coinepro.hq.core.data.memberReasonFa
import com.coinepro.hq.core.data.soloAnswerFa
import com.coinepro.hq.core.diag.ErrorEntry
import com.coinepro.hq.core.diag.ErrorReporter
import com.coinepro.hq.core.diag.LEVEL_ERROR
import com.coinepro.hq.core.diag.LEVEL_INFO
import com.coinepro.hq.core.diag.LEVEL_WARNING
import com.coinepro.hq.core.diag.SentStore
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Catalogue
import com.coinepro.hq.core.net.Council
import com.coinepro.hq.core.net.CouncilMember
import com.coinepro.hq.core.net.Finding
import com.coinepro.hq.core.net.Protocol
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.core.net.routeMissing
import java.security.MessageDigest
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonObject
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
 * Contract §28 ⟨1.10⟩: the outputs' selection mode, the seal's target of a delete (SHA-256 of the sorted refs) and its calls, the
 * catalogue's wire shape, the watch's kinds and groups, «خطاخوان»'s uploads (batches, crashes first, every entry once, a failed batch
 * tried again), and the council's reasons in plain Persian.
 */
@RunWith(RobolectricTestRunner::class)
class CleanupTest {
    private val server = MockWebServer()
    private val tokens = object : TokenSource {
        override fun token() = "t0ken"
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

    private fun json(body: String, code: Int = 200) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    // ------------------------------------------------------------ selection --
    @Test
    fun aLongPressOpensSelectionAndTapsToggle() {
        var s = Selection()
        assertFalse(s.active)
        s = s.start("O-2")
        assertTrue(s.active)
        assertEquals(setOf("O-2"), s.refs)
        s = s.toggle("O-1").toggle("O-3")
        assertEquals(3, s.count)
        assertEquals(listOf("O-1", "O-2", "O-3"), s.sorted)
        // A long press while open toggles like a tap.
        s = s.start("O-3")
        assertEquals(setOf("O-1", "O-2"), s.refs)
        // Leaving the last one by a tap leaves the mode.
        s = s.toggle("O-1").toggle("O-2")
        assertFalse(s.active)
        assertEquals(0, s.count)
    }

    @Test
    fun allNoneRetainAndExit() {
        val visible = listOf("O-1", "O-2", "O-3")
        var s = Selection().start("O-1").all(visible)
        assertTrue(s.allOf(visible))
        s = s.none()
        assertTrue("«هیچ» keeps the mode open", s.active)
        assertEquals(0, s.count)
        assertFalse(s.allOf(visible))
        assertFalse(s.allOf(emptyList()))
        s = s.all(visible).retain(listOf("O-1", "O-3"))
        assertEquals(setOf("O-1", "O-3"), s.refs)
        assertTrue(s.active)
        assertEquals(Selection(), s.exit())
        assertEquals(Selection(), Selection().retain(visible))
    }

    // ------------------------------------------------------- delete and file --
    @Test
    fun theDeleteIsSealedOnTheSha256OfTheSortedRefs() {
        val expected = MessageDigest.getInstance("SHA-256").digest("""["O-000026","O-000028","O-000032"]""".toByteArray()).joinToString("") { "%02x".format(it) }
        assertEquals(expected, Api.deleteTarget(listOf("O-000032", "O-000026", "O-000028", "O-000026")))
        assertEquals(Api.deleteTarget(listOf("O-000028", "O-000026", "O-000032")), Api.deleteTarget(setOf("O-000032", "O-000028", "O-000026")))
    }

    @Test
    fun deleteSendsTheSortedRefsWithTheSealAndFileSendsTheList() = runTest {
        var asked: Pair<String, String>? = null
        server.enqueue(json("""{"deleted":2}"""))
        val out = api.deleteDeliverables(listOf("O-000032", "O-000026")) { a, t -> asked = a to t; "step-tok" }
        assertEquals(2, out.deleted)
        assertEquals("deliverables.delete" to Api.deleteTarget(listOf("O-000026", "O-000032")), asked)
        val del = server.takeRequest()
        assertEquals("DELETE", del.method)
        assertEquals("/api/v1/deliverables", del.url.encodedPath)
        assertEquals("step-tok", del.headers["X-Step-Up"])
        val refs = Api.json.parseToJsonElement(del.body!!.utf8()).jsonObject["refs"]!!.jsonArray.map { it.jsonPrimitive.content }
        assertEquals(listOf("O-000026", "O-000032"), refs)

        server.enqueue(json("""{"records":[{"ref":"O-000026","record":"AR-000097"},{"ref":"O-000032","record":"AR-000098"}]}"""))
        val filed = api.fileDeliverables(listOf("O-000026", "O-000032", "O-000026"))
        assertEquals(listOf("AR-000097", "AR-000098"), filed.records.map { it.record })
        val post = server.takeRequest()
        assertEquals("/api/v1/deliverables/file", post.url.encodedPath)
        assertEquals(2, Api.json.parseToJsonElement(post.body!!.utf8()).jsonObject["refs"]!!.jsonArray.size)
    }

    // ------------------------------------------------------------- catalogue --
    @Test
    fun aCatalogueDecodesWithItsTables() = runTest {
        server.enqueue(json("""{"company":"TY","at":"2026-10-31T08:00:00Z","state":"done","record":"AR-000210","servers":[{"id":"s1","name":"ty-web","state":"done"}],
            "sections":[{"key":"data","title_fa":"داده","count":2,"tables":[{"columns":["جدول","ردیف"],"rows":[["users",48210],["signals",null]]}]}]}"""))
        val k: Catalogue = api.catalogue("TY")
        assertEquals("/api/v1/companies/TY/catalogue", server.takeRequest().url.encodedPath)
        assertFalse(k.running)
        val t = k.sections.single().tables.single()
        assertEquals("48210", t.cell(0, 1))
        assertEquals("—", t.cell(1, 1))
        assertEquals("—", t.cell(5, 5))
        server.enqueue(json("""{"company":"FX","state":"running"}"""))
        assertTrue(api.startCatalogue("FX").running)
        assertEquals("POST", server.takeRequest().method)
    }

    // ------------------------------------------------------------- the watch --
    private fun finding(ref: String, protocol: String?, kind: String? = null, severity: String = "medium", status: String = "open") =
        Finding(ref = ref, company = "TY", protocol = protocol, severity = severity, titleFa = ref, status = status, openedAt = "2026-10-31T08:00:00Z", kind = kind)

    private fun protocol(ref: String, area: String, title: String) = Protocol(ref = ref, titleFa = title, area = area)

    @Test
    fun watchFindingsAreGroupedByTheirKindOrTheirProtocol() {
        val protocols = listOf(
            protocol("PR-130", "security", "پایش امنیتی روزانه"),
            protocol("PR-131", "quality", "سلامت اپ: خطاهایی که اپ‌ها فرستاده‌اند"),
            protocol("PR-132", "quality", "بازبینی کد هفتگی"),
            protocol("PR-010", "authority", "هیچ A3 بدون مُهر اجرا نشده"),
        )
        assertEquals(WatchKind.GROWTH, Watch.kindOf(finding("FI-1", "PR-010", kind = "growth"), protocols))
        assertEquals(WatchKind.SECURITY, Watch.kindOf(finding("FI-2", "PR-130"), protocols))
        assertEquals(WatchKind.APP_HEALTH, Watch.kindOf(finding("FI-3", "PR-131"), protocols))
        assertEquals(WatchKind.CODE, Watch.kindOf(finding("FI-4", "PR-132"), protocols))
        assertNull("an older protocol's finding is not the watch's", Watch.kindOf(finding("FI-5", "PR-010"), protocols))
        assertNull(Watch.kindOf(finding("FI-6", null), protocols))

        val groups = Watch.groups(
            listOf(
                finding("FI-2", "PR-130", severity = "medium"), finding("FI-7", "PR-130", severity = "critical"),
                finding("FI-3", "PR-131"), finding("FI-8", "PR-130", status = "verified"), finding("FI-5", "PR-010"),
                finding("FI-9", null, kind = "holding"),
            ),
            protocols,
        )
        assertEquals(listOf(WatchKind.SECURITY, WatchKind.APP_HEALTH, WatchKind.HOLDING), groups.map { it.first })
        assertEquals(listOf("FI-7", "FI-2"), groups.first().second.map { it.ref })
        assertEquals("P1", Watch.priorityOf("critical"))
        assertEquals("P4", Watch.priorityOf("info"))
    }

    @Test
    fun aFindingDecodesItsKindAndFix() {
        val f = Api.json.decodeFromString(
            Finding.serializer(),
            """{"ref":"FI-0020","company":"TY","severity":"high","title_fa":"t","status":"open","opened_at":"2026-10-31T08:00:00Z","kind":"security","fix_md":"ارتقا","fix":{"kind":"decision","ref":"D-000041"}}""",
        )
        assertEquals("security", f.kind)
        assertEquals("ارتقا", f.fixMd)
        assertEquals("D-000041", f.fix?.ref)
        assertEquals("cartable/D-000041", com.coinepro.hq.core.data.Refs.route(f.fix!!.ref!!))
    }

    // ---------------------------------------------------------- error upload --
    private fun entry(id: Long, at: String, kind: String = "http", level: String = LEVEL_WARNING) = ErrorEntry(id = id, at = at, kind = kind, level = level, app = "0.10.0 (1000)")

    @Test
    fun pendingIsErrorsAndWarningsNotSentCrashesFirstThenOldest() {
        val log = listOf(
            entry(5, "2026-10-31T08:05:00.000Z"),
            entry(4, "2026-10-31T08:04:00.000Z", "crash", LEVEL_ERROR),
            entry(3, "2026-10-31T08:03:00.000Z", "session", LEVEL_INFO),
            entry(2, "2026-10-31T08:02:00.000Z", "decode", LEVEL_ERROR),
            entry(1, "2026-10-31T08:01:00.000Z"),
        )
        val sent = setOf(ErrorReporter.keyOf(log[4]))
        assertEquals(listOf(4L, 2L, 5L), ErrorReporter.pending(log, sent).map { it.id })
        assertEquals(listOf(50, 50, 20), ErrorReporter.batches((1..120).map { entry(it.toLong(), "2026-10-31T08:00:00.000Z") }).map { it.size })
        // A cleared log numbers again: the same number at another moment is another entry.
        assertFalse(ErrorReporter.keyOf(entry(1, "2026-10-31T08:01:00.000Z")) == ErrorReporter.keyOf(entry(1, "2026-10-31T09:01:00.000Z")))
    }

    @Test
    fun everyEntryGoesOnceInBatchesAndAFailedBatchGoesNextRound() = runTest {
        val log = (1..120L).map { entry(it, "2026-10-31T08:%02d:00.000Z".format(it % 60)) }.reversed()
        val store = SentStore.memory()
        val sent = mutableListOf<List<Long>>()
        var failSecond = true
        val r = ErrorReporter({ log }, store, { batch ->
            if (sent.size == 1 && failSecond) { failSecond = false; throw java.io.IOException("offline") }
            sent += batch.map { it.id }
        }, { true })
        assertEquals(50, r.flush())
        assertEquals(1, sent.size)
        assertEquals(50, r.reported.value)
        assertEquals(70, r.flush())
        assertEquals(listOf(50, 50, 20), sent.map { it.size })
        assertEquals("never twice", 120, sent.flatten().toSet().size)
        assertEquals(0, r.flush())
        assertEquals(3, sent.size)
        assertEquals(120, r.reported.value)
    }

    @Test
    fun nothingGoesWhileTheOwnerTurnedItOff() = runTest {
        var on = false
        var calls = 0
        val r = ErrorReporter({ listOf(entry(1, "2026-10-31T08:00:00.000Z", "crash", LEVEL_ERROR)) }, SentStore.memory(), { calls++ }, { on })
        assertEquals(0, r.flush())
        assertEquals(0, calls)
        on = true
        assertEquals(1, r.flush())
        assertEquals(1, calls)
    }

    @Test
    fun theUploadCarriesTheAppTheVersionAndTheMaskedEntries() = runTest {
        server.enqueue(json("""{"accepted":1}"""))
        val e = entry(7, "2026-10-31T08:00:00.000Z", "decode", LEVEL_ERROR).copy(path = "/api/v1/deliverables", field = "$.items[3].usage")
        assertEquals(1, api.clientErrors("0.10.0", ErrorReporter.wire(listOf(e))).accepted)
        val req = server.takeRequest()
        assertEquals("/api/v1/client/errors", req.url.encodedPath)
        val body = Api.json.parseToJsonElement(req.body!!.utf8()).jsonObject
        assertEquals("android", body["app"]!!.jsonPrimitive.content)
        assertEquals("0.10.0", body["version"]!!.jsonPrimitive.content)
        val sentEntry = body["entries"]!!.jsonArray.single() as JsonObject
        assertEquals("$.items[3].usage", sentEntry["field"]!!.jsonPrimitive.content)
        assertEquals("decode", sentEntry["kind"]!!.jsonPrimitive.content)
    }

    // ---------------------------------------------- a hub before ⟨1.10⟩ --
    private val missing = """{"type":"about:blank","title":"Not found","status":404,"code":"not_found","message_fa":"پیدا نشد.","detail":"Not Found"}"""

    @Test
    fun aMissingRouteIsLearntOnceAndTheCallerFallsBack() = runTest {
        server.enqueue(json(missing, 404))
        assertNull(api.gated(HubFeature.BULK_FILE) { fileDeliverables(listOf("O-1", "O-2")) })
        assertEquals(1, server.requestCount)
        assertFalse(api.gaps.has(HubFeature.BULK_FILE))
        assertTrue(HubFeature.BULK_FILE in api.gaps.missing.value)
        // Learnt for this app start: no second call to the missing route; the screen files one by one instead.
        assertNull(api.gated(HubFeature.BULK_FILE) { fileDeliverables(listOf("O-1")) })
        assertEquals(1, server.requestCount)
        assertTrue("the others are untouched", api.gaps.has(HubFeature.DELETE_OUTPUTS))
        // 405 is a missing route too.
        server.enqueue(json("""{"type":"about:blank","title":"Method Not Allowed","status":405,"code":"not_found","message_fa":"پیدا نشد.","detail":"Method Not Allowed"}""", 405))
        assertNull(api.gated(HubFeature.DELETE_OUTPUTS) { deleteDeliverables(listOf("O-1")) { _, _ -> "tok" } })
        assertFalse(api.gaps.has(HubFeature.DELETE_OUTPUTS))
    }

    @Test
    fun theHubsOwnNotFoundIsNotAMissingRoute() = runTest {
        server.enqueue(json("""{"type":"about:blank","title":"Not found","status":404,"code":"not_found","message_fa":"پیدا نشد.","detail":"no catalogue for TY yet"}""", 404))
        val e = runCatching { api.gated(HubFeature.CATALOGUE) { catalogue("TY") } }.exceptionOrNull() as ApiException
        assertFalse(e.routeMissing)
        assertTrue(api.gaps.has(HubFeature.CATALOGUE))
        assertTrue(ApiException(404, "not_found", "پیدا نشد.").routeMissing)
        assertFalse(ApiException(409, "conflict", "x").routeMissing)
    }

    @Test
    fun errorsStayQueuedWhileTheHubHasNoRoute() = runTest {
        val store = SentStore.memory()
        var served = false
        val r = ErrorReporter({ listOf(entry(1, "2026-10-31T08:00:00.000Z", "crash", LEVEL_ERROR)) }, store, { if (!served) throw ErrorReporter.NotServed() }, { true })
        assertEquals(0, r.flush())
        assertTrue("nothing is marked sent", store.keys().isEmpty())
        served = true
        assertEquals(1, r.flush())
        assertEquals(1, store.keys().size)
    }

    // ----------------------------------------------------------- the council --
    @Test
    fun reasonsArePersianAsGivenOtherwiseNoAnswerWithDetails() {
        val fa = "مدل gpt-5.3 با اشتراک ChatGPT پشتیبانی نمیشود؛ با مدل پیش‌فرض دوباره امتحان شد"
        assertEquals(fa, memberReasonFa(fa)!!.text)
        assertNull(memberReasonFa(fa)!!.raw)
        val raw = """{"error":{"code":"model_not_found","message":"The model `gpt-5.3` is not supported"}}"""
        assertEquals("پاسخ نداد", memberReasonFa(raw)!!.text)
        assertEquals(raw, memberReasonFa(raw)!!.raw)
        val en = "recipe_failed: selector [data-test-id=send-button] not found after 30000ms"
        assertEquals("پاسخ نداد", memberReasonFa(en)!!.text)
        assertEquals(en, memberReasonFa(en)!!.raw)
        assertEquals("پاسخ نداد", memberReasonFa("خطا: {\"code\": 500}")!!.text)
        assertNull(memberReasonFa("  "))
        assertNull(memberReasonFa(null))
    }

    @Test
    fun aCouncilWithOneAnswerSaysSo() {
        val members = listOf(
            CouncilMember("claude", state = "done", deliverableRef = "O-1"),
            CouncilMember("gpt", state = "failed", reason = "x"),
            CouncilMember("gemini", state = "failed"),
        )
        assertEquals("فقط Claude پاسخ داد", soloAnswerFa(Council("W-1", members, state = "done")))
        assertNull("still moving", soloAnswerFa(Council("W-1", members + CouncilMember("deepseek", state = "working"))))
        assertNull("two answered", soloAnswerFa(Council("W-1", members.map { if (it.player == "gpt") it.copy(state = "done") else it }, state = "done")))
        assertNull("a council of one is not a council", soloAnswerFa(Council("W-1", members.take(1), state = "done")))
        assertEquals("فقط GPT پاسخ داد", soloAnswerFa(Council("W-1", listOf(CouncilMember("claude", state = "failed"), CouncilMember("gpt", state = "done")), state = "done")))
    }
}
