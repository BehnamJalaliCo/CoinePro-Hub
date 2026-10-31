package com.coinepro.hq

import com.coinepro.hq.core.data.QueryCache
import com.coinepro.hq.core.data.orderCreated
import com.coinepro.hq.core.data.ownerOrders
import com.coinepro.hq.core.data.recurringEscrow
import com.coinepro.hq.core.data.splitTree
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.MeetingItemIn
import com.coinepro.hq.core.net.PairCode
import com.coinepro.hq.core.net.ScheduleIn
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.TreeEvent
import com.coinepro.hq.core.net.WorkCreate
import com.coinepro.hq.device.LaunchKey
import java.io.File
import java.time.Instant
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import mockwebserver3.Dispatcher
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
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
 * The fixes of the independent review (docs/reviews/ANDROID_REVIEW_2026-10-31.md): one key per type in the query cache, a refetch after
 * an invalidation that arrived mid-load, the bodies of a recurring order and a new meeting against the hub's own schema (openapi),
 * «همه» of the cartable reading every status, the owner's orders by `created_by`, which `work.created` may be an order, the tree's
 * events in one call, the app's own launches, a case's holds, the pairing seal's refusal, and Latin digits for every clock time.
 */
@RunWith(RobolectricTestRunner::class)
class ReviewFixesTest {
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

    /** The hub's request schemas, as `apps/api/openapi/hq-api.v1.json` publishes them. */
    private val schemas: JsonObject by lazy {
        Api.json.parseToJsonElement(File("../../api/openapi/hq-api.v1.json").readText()).jsonObject["components"]!!.jsonObject["schemas"]!!.jsonObject
    }

    private fun props(schema: String): Set<String> = schemas[schema]!!.jsonObject["properties"]!!.jsonObject.keys

    // ---------------------------------------------------------- query cache --
    @Test(expected = IllegalStateException::class)
    fun oneKeyNeverServesTwoTypes() {
        // 0.9.0: «orders» held List<Work> and List<Order>; the voice order crashed on a cast. A debug build stops at the second type.
        val cache = QueryCache(CoroutineScope(kotlinx.coroutines.Dispatchers.Unconfined))
        cache.get("orders", setOf("orders"), "List<Work>") { emptyList<String>() }
        cache.get("orders", setOf("orders"), "List<Order>") { emptyList<String>() }
    }

    @Test
    fun anInvalidationDuringALoadFetchesAgain() = runTest {
        val scope = CoroutineScope(UnconfinedTestDispatcher(testScheduler))
        val cache = QueryCache(scope)
        var calls = 0
        var gate = CompletableDeferred<Int>()
        val q = cache.get("decisions:pending", setOf("decisions"), "Int") { calls++; gate.await() }
        q.refresh()
        assertEquals(1, calls)
        // The owner seals a card while the list is loading: the load under way may predate the seal.
        q.refresh()
        val first = gate
        gate = CompletableDeferred()
        first.complete(1)
        testScheduler.advanceUntilIdle()
        assertEquals("a second fetch follows the stale one", 2, calls)
        gate.complete(2)
        testScheduler.advanceUntilIdle()
        assertEquals(2, q.state.value.data)
        assertFalse(q.state.value.loading)
    }

    // ------------------------------------------------------- recurring order --
    @Test
    fun aRecurringOrderCarriesTheEscrowTheHubRequires() = runTest {
        val now = Instant.parse("2026-10-31T10:00:00Z")
        val escrow = recurringEscrow(300_000, 20, now = now)
        assertEquals(listOf("A0", "A1"), escrow.allowedActionClasses)
        assertEquals("2027-01-29T10:00:00Z", escrow.expiresAt)
        val body = WorkCreate(company = "TY", title = "گزارش روزانه", kind = "recurring", schedule = ScheduleIn("FREQ=DAILY;BYHOUR=8;BYMINUTE=0"), escrow = escrow)
        server.enqueue(json("""{"id":"w-1","ref":"W-000300","company":"TY","title":"t","status":"queued","kind":"recurring"}""", 201))
        api.createWork(body)
        val sent = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        // Every key is one the hub's model takes (`extra="forbid"`), and the escrow is there with every field.
        assertTrue(sent.keys.toString(), props("WorkCreate").containsAll(sent.keys))
        val e = sent["escrow"]!!.jsonObject
        assertEquals(props("EscrowIn"), e.keys)
        assertEquals("300000", e["token_cap_per_run"]!!.jsonPrimitive.content)
        assertEquals("20", e["usd_cap_per_month"]!!.jsonPrimitive.content)
        assertTrue(props("ScheduleIn").containsAll(sent["schedule"]!!.jsonObject.keys))
    }

    // ------------------------------------------------------------ new meeting --
    @Test
    fun aNewMeetingSendsOnlyWhatTheHubTakes() = runTest {
        server.enqueue(json("""{"id":"m","ref":"MT-0100","type":"company","company":"FX","title_fa":"t","starts_at":"2026-11-01T06:30:00Z","state":"scheduled"}""", 201))
        val start = com.coinepro.hq.ui.meetings.meetingStart(1, 10, 0, today = java.time.LocalDate.parse("2026-10-31"))
        assertEquals("2026-11-01T06:30:00Z", start.toString())
        runCatching { api.createMeeting("company", "FX", start.toString(), listOf(MeetingItemIn("بودجه‌ی ماه")), "k1") }
        val sent = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertTrue(props("MeetingCreateIn").containsAll(sent.keys))
        for (it in sent["items"]!!.jsonArray) assertTrue(it.toString(), props("MeetingOwnerItemIn").containsAll(it.jsonObject.keys))
        val types = schemas["MeetingCreateIn"]!!.jsonObject["properties"]!!.jsonObject["type"]!!.jsonObject["enum"]!!.jsonArray.map { it.jsonPrimitive.content }
        assertEquals(listOf("board", "company", "strategy"), types)
    }

    // ---------------------------------------------------------- cartable «همه» --
    @Test
    fun allDecisionsReadsEveryStatus() = runTest {
        val asked = java.util.Collections.synchronizedList(mutableListOf<String>())
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val s = request.url.queryParameter("status")!!
                asked += s
                val item = """{"id":"$s","ref":"D-$s","company":"TY","kind":"proposal","status":"$s","title_fa":"$s","created_at":"2026-10-${if (s == "pending") "31" else "20"}T08:00:00Z"}"""
                return json("""{"items":[${if (s == "withdrawn") "" else item}],"next_cursor":null}""")
            }
        }
        val page = runCatching { api.decisionsAll(company = "TY") }
        assertEquals(Api.DECISION_STATUSES.toSet(), asked.toSet())
        page.getOrNull()?.let { assertEquals("D-pending", it.items.first().ref) }
    }

    // ------------------------------------------------------- the owner's orders --
    @Test
    fun ownerOrdersAskTheHubForTheOwnersOwn() = runTest {
        server.enqueue(json("""{"items":[{"id":"a","ref":"W-1","company":"TY","title":"t","status":"queued","created_by":{"code":"owner","kind":"owner"}}],"next_cursor":"c1"}"""))
        server.enqueue(json("""{"items":[{"id":"b","ref":"W-2","company":"TY","title":"t","status":"done","created_by":{"code":"owner","kind":"owner"}},{"id":"x","ref":"W-3","company":"TY","title":"t","status":"done","created_by":{"code":"TY-CEO","kind":"agent"}}],"next_cursor":null}"""))
        val list = api.ownerOrders()
        assertEquals(listOf("W-1", "W-2"), list.map { it.ref })
        val first = server.takeRequest().url
        assertEquals("owner", first.queryParameter("created_by"))
        assertEquals("c1", server.takeRequest().url.queryParameter("cursor"))
    }

    @Test
    fun onlyATopLevelWorkMayBeANewOrder() {
        fun e(vararg d: Pair<String, Any>) = StreamEvent("1", "work.created", "", "TY", "W-1", buildJsonObject {
            for ((k, v) in d) if (v is Int) put(k, v) else put(k, v.toString())
        })
        assertTrue(orderCreated(e("depth" to 0, "assignee" to "TY-CEO")))
        assertFalse("a delegation", orderCreated(e("depth" to 1)))
        assertFalse("a recurrence's occurrence", orderCreated(e("recurrence_of" to "W-9")))
        assertFalse(orderCreated(e("kind" to "knowledge_transfer")))
        assertTrue("the creator, once the hub names it", orderCreated(e("created_by" to "owner", "depth" to 1)))
        assertFalse(orderCreated(e("created_by" to "TY-CEO", "depth" to 0)))
    }

    @Test
    fun theTreeEventsSplitByWorkAndRun() {
        fun t(id: String, kind: String, ref: String, data: JsonObject = JsonObject(emptyMap()), actor: String = "TY-CEO") =
            TreeEvent(id, "2026-10-31T08:0${id.last()}:00Z", kind, "w-$ref", ref, if (ref == "W-1") 0 else 1, "agent", actor, data)
        val items = listOf(
            t("e0000000000000000001", "work.created", "W-1"),
            t("e0000000000000000002", "work.delegated", "W-1", buildJsonObject { put("child", "W-2"); put("to", "TY-GROWTH-MGR") }),
            t("e0000000000000000003", "work.accepted", "W-2", actor = "TY-GROWTH-MGR"),
            t("s0000000000000000004", "run.step", "W-2", buildJsonObject { put("run_id", "r1"); put("n", 1); put("summary_fa", "خواند") }, "TY-GROWTH-MGR"),
            t("s0000000000000000005", "run.step", "W-2", buildJsonObject { put("run_id", "r1"); put("n", 2); put("summary_fa", "نوشت") }, "TY-GROWTH-MGR"),
        )
        val (events, runs) = splitTree(items, "TY")
        assertEquals(listOf("created", "delegated"), events["W-1"]!!.map { it.kind })
        assertEquals(listOf("accepted"), events["W-2"]!!.map { it.kind })
        val r = runs["W-2"]!!.single()
        assertEquals("r1", r.id)
        assertEquals("TY-GROWTH-MGR", r.employee)
        assertEquals(listOf("خواند", "نوشت"), r.stepsDetail.map { it.summaryFa })
    }

    // ------------------------------------------------------------- launches --
    @Test
    fun onlyTheAppsOwnLaunchesOpenAPage() {
        val ctx = androidx.test.core.app.ApplicationProvider.getApplicationContext<android.content.Context>()
        val own = LaunchKey.sign(ctx, android.content.Intent())
        assertTrue(LaunchKey.trusted(ctx, own))
        assertFalse(LaunchKey.trusted(ctx, android.content.Intent().putExtra(LaunchKey.EXTRA, "guess")))
        assertFalse(LaunchKey.trusted(ctx, android.content.Intent()))
        assertTrue(LaunchKey.routeAllowed("cartable"))
        assertTrue(LaunchKey.routeAllowed("outputs/O-000031"))
        assertTrue(LaunchKey.routeAllowed("servers/srv-ty-1/terminal"))
        assertFalse(LaunchKey.routeAllowed("../../etc"))
        assertFalse(LaunchKey.routeAllowed("work/a?b=c"))
        assertFalse(LaunchKey.routeAllowed(null))
    }

    // ---------------------------------------------------------------- holds --
    @Test
    fun aCasesHoldsAreThatCasesOnly() = runTest {
        // The hub ignores `case`: it answers every hold; the app keeps the case's.
        server.enqueue(json("""[{"ref":"LH-1","case":"LC-0001"},{"ref":"LH-2","case":"LC-0002"},{"ref":"LH-3"}]"""))
        assertEquals(listOf("LH-1"), api.legalHolds(case = "LC-0001").map { it.ref })
    }

    // -------------------------------------------------------------- pairing --
    @Test
    fun aSealForAnotherCompanySaysSo() {
        val why = PairCode.refusal(ApiException(403, "step_up_invalid", "x"))!!
        assertTrue(why.contains("شرکت دیگری"))
    }

    // --------------------------------------------------------- clock digits --
    @Test
    fun everyClockTimeIsAFigure() {
        val a = com.coinepro.hq.designsystem.timesFig("خوانده شد، ۲۵ مهر، 10:50؛ تا 08:00–09:30")
        val figured = a.spanStyles.filter { it.item.fontFamily == com.coinepro.hq.designsystem.FigureFace }.map { a.text.substring(it.start, it.end) }
        assertEquals(listOf("10:50", "08:00", "09:30"), figured)
        assertNull(com.coinepro.hq.designsystem.timesFig("بی‌ساعت").spanStyles.firstOrNull())
        // No screen draws a time in the prose face: never `Text(jTime(…))` or `appendProse(jTime(…))` (review §15).
        val bad = File("src/main/java").walkTopDown().filter { it.extension == "kt" }.flatMap { f ->
            f.readLines().mapIndexedNotNull { i, l -> if (Regex("""(?<![\w.])Text\((jTime|jDateTime)\(|appendProse\((jTime|jDateTime)\(""").containsMatchIn(l)) "${f.name}:${i + 1}" else null }
        }.toList()
        assertEquals(emptyList<String>(), bad)
    }
}
