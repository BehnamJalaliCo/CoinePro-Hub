package com.coinepro.hq

import com.coinepro.hq.core.data.FixWay
import com.coinepro.hq.core.data.LongVoiceRules
import com.coinepro.hq.core.data.Refs
import com.coinepro.hq.core.data.appliesToFa
import com.coinepro.hq.core.data.avatarStateOf
import com.coinepro.hq.core.data.blockerFa
import com.coinepro.hq.core.data.employeeStateOf
import com.coinepro.hq.core.data.figureText
import com.coinepro.hq.core.data.fixRoute
import com.coinepro.hq.core.data.fixWay
import com.coinepro.hq.core.data.kpiMove
import com.coinepro.hq.core.data.moveText
import com.coinepro.hq.core.data.numberText
import com.coinepro.hq.core.data.orderEnded
import com.coinepro.hq.core.data.routeLineFa
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.orderWithPace
import com.coinepro.hq.core.net.problemFields
import com.coinepro.hq.core.net.Council
import com.coinepro.hq.core.net.DayValue
import com.coinepro.hq.core.net.Fix
import com.coinepro.hq.core.net.Home
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.OrderRoute29
import com.coinepro.hq.core.net.OwnerRule
import com.coinepro.hq.core.net.StandingOrder
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.kpiSeriesOf
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Contract §29 ⟨1.11⟩: the shapes the new screens read (the home, an order's report, the owner's rules with a widened `applies_to`, the
 * council v2, a group's KPIs in any of their shapes), the words the app writes for them (states, blockers, the secretary's line, whom a
 * rule applies to, figures and moves in Latin), where a fix goes, the long voice's rules, and the calls on the wire (the preview, an
 * order with its route, a fix, the chunks of a long voice, the seals).
 */
@RunWith(RobolectricTestRunner::class)
class V29Test {
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

    // ------------------------------------------------------------------- shapes --
    @Test
    fun theHomeDecodesWithItsThreeCardsAndOnlyCriticalItems() {
        val h = Api.json.decodeFromString(Home.serializer(), """
            {"cards":{"effective":{"id":"sg-1","kind":"effective","company":"TY","title_fa":"سه ریلز","why_fa":"چون","impact_fa":"1,200","cost_fa":"400K","source":"group","state":"new","reason_fa":null,"order_ref":null,"created_at":"2026-10-17T08:00:00Z"},
             "good":null,"progress":{"id":"pg-1","company":"TY","title_fa":"کلیک","before":{"value":412,"at":"2026-10-02"},"after":{"value":587,"at":"2026-10-16"},"kpi":"clicks","source":"search_console","work_ref":null}},
             "morning":["یک","دو"],"groups":[{"key":"content","title_fa":"محتوا","companies":[{"code":"TY","name_fa":"تریدیار","kpi":{"key":"followers","title_fa":"دنبال‌کننده","unit":"","series":[{"day":"2026-10-16","value":12480},{"day":"2026-10-17","value":null}]}}]}],
             "orders":[{"ref":"F-0041","text_fa":"سه ریلز","state":"in_progress","summary_fa":""}],
             "critical":[{"id":"n1","level":"urgent","company":"PC","title_fa":"سایت پایین است","created_at":"2026-10-17T08:00:00Z","domain":"infra","owner_visible":true,"critical_reason":"product_down","routed_to":"PC-TECH-MGR"}],"new_field":1}
        """.trimIndent())
        assertEquals("sg-1", h.cards.effective?.id)
        assertNull(h.cards.good)
        assertEquals("412", (h.cards.progress!!.before.value as JsonPrimitive).content)
        assertEquals(listOf(12480.0, null), h.groups.single().companies.single().kpi!!.series.map { it.value })
        assertEquals("product_down", h.critical.single().criticalReason)
        assertEquals("infra", h.critical.single().domain)
    }

    @Test
    fun anOrderReportDecodesWithItsBlockersAndSummary() {
        val r = Api.json.decodeFromString(OrderReport.serializer(), """
            {"ref":"F-0042","text_fa":"برنامه","at":"2026-10-17T08:00:00Z","state":"blocked","ack":{"at":"2026-10-17T08:01:00Z","by":{"kind":"agent","code":"PC-CEO"},"plan_fa":"پلن","assigned":[{"company":"PC","code":"PC-GROWTH-MGR","title_fa":"مدیر رشد"}],"due_at":null},
             "route":{"companies":["PC"],"department":"GROWTH","collaborators":[],"output_kind":"plan","count":null,"budget_tokens":250000,"mode":"single","player":"auto","preview_fa":"→ پرو-چارت/رشد","confidence":0.9,"why_fa":"","kind":"work"},
             "steps":[{"at":"2026-10-17T08:00:00Z","who_fa":"منشی","what_fa":"رسید"}],
             "blockers":[{"kind":"budget","title_fa":"","detail_fa":"","since":null,"fix":{"action":"budget.add","label_fa":"","target":"100000"}}],
             "outputs":[],"summary":null,"updated_at":"2026-10-17T09:00:00Z"}
        """.trimIndent())
        assertEquals("blocked", r.state)
        assertEquals(250_000L, r.route?.budgetTokens)
        assertEquals("budget.add", r.blockers.single().fix?.action)
        assertEquals("بودجه‌ی این کار کم آمد", blockerFa(r.blockers.single().kind, r.blockers.single().titleFa))
        assertFalse(orderEnded(r.state))
        assertTrue(orderEnded("delivered") && orderEnded("failed") && orderEnded("cancelled"))
    }

    @Test
    fun aRuleAndAStandingOrderReadAWidenedAppliesTo() {
        val names = mapOf("TY" to "تریدیار", "FX" to "کوینه‌پرو FX")
        val r = Api.json.decodeFromString(OwnerRule.serializer(), """{"ref":"SO-021","text_md":"x","applies_to":{"roles":["media_director","scriptwriter"]},"status":"sealed","counts":{"applied":46,"violations":2,"fixed":2}}""")
        assertEquals("برای مدیر رسانه و طراحی، سناریست", appliesToFa(r.appliesTo) { names.getValue(it) })
        assertEquals(46L, r.counts?.applied)
        val o = Api.json.decodeFromString(StandingOrder.serializer(), """{"ref":"SO-022","text_md":"x","applies_to":{"companies":["TY","FX"]},"status":"proposed"}""")
        assertEquals("custom", o.appliesToKey)
        assertEquals("برای تریدیار، کوینه‌پرو FX", appliesToFa(o.appliesTo) { names.getValue(it) })
        val all = Api.json.decodeFromString(StandingOrder.serializer(), """{"ref":"SO-001","text_md":"x","applies_to":"all","status":"sealed"}""")
        assertEquals("all", all.appliesToKey)
        assertEquals("برای همه", appliesToFa(all.appliesTo))
        assertEquals("برای ناظر", appliesToFa(JsonPrimitive("overseer")))
    }

    @Test
    fun theCouncilV2CarriesItsRoundRolesFactPackAndPlan() {
        val k = Api.json.decodeFromString(Council.serializer(), """
            {"work_ref":"W-000222","state":"done","round":3,"roles":{"claude":"captain","gpt":"devil"},"fact_pack_ref":"FP-0007",
             "fact_pack":{"company":"TY","at":"2026-10-17T08:00:00Z","figures":[{"key":"followers","title_fa":"دنبال‌کننده","value":12480,"source":"instagram","at":"2026-10-16"}],"recent_posts":[],"notes_fa":""},
             "plan_md":"1. یک","members":[{"player":"claude","state":"done"}]}
        """.trimIndent())
        assertEquals(3, k.round)
        assertEquals("devil", k.roles["gpt"])
        assertEquals("12,480", figureText(k.factPack!!.figures.single().value))
        assertEquals("منتقد", com.coinepro.hq.ui.v29.councilRoleFa(k, "gpt"))
        assertEquals("دور سوم: کاپیتان برنامه را مینویسد", com.coinepro.hq.ui.v29.councilRoundFa(k))
        // A council before v2 has none of these.
        val old = Api.json.decodeFromString(Council.serializer(), """{"work_ref":"W-1","state":"done","members":[]}""")
        assertNull(old.planMd)
        assertNull(com.coinepro.hq.ui.v29.councilRoundFa(old))
    }

    @Test
    fun groupKpisAreReadWhateverTheirShape() {
        val s = """{"key":"followers","title_fa":"دنبال‌کننده","unit":"","series":[{"day":"2026-10-16","value":1}]}"""
        val list = Api.json.parseToJsonElement("""[{"company":"TY",${s.drop(1)}]""")
        assertEquals("TY", kpiSeriesOf(list).single().company)
        val page = Api.json.parseToJsonElement("""{"items":[$s],"next_cursor":null}""")
        assertEquals("FX", kpiSeriesOf(page, "FX").single().company)
        val one = Api.json.parseToJsonElement("""{"company":"PC","kpis":[$s]}""")
        assertEquals("PC", kpiSeriesOf(one).single().company)
        val bare = Api.json.parseToJsonElement(s)
        assertEquals(1.0, kpiSeriesOf(bare, "TY").single().series.single().value)
        assertTrue(kpiSeriesOf(Api.json.parseToJsonElement("""{"items":[]}""")).isEmpty())
    }

    // -------------------------------------------------------------------- words --
    @Test
    fun theSecretarysLineIsTheHubsOrBuiltTheSameWay() {
        val names = mapOf("TY" to "تریدیار", "FX" to "کوینه‌پرو FX")
        val r = OrderRoute29(companies = listOf("TY"), department = "MEDIA", collaborators = listOf("FX"), outputKind = "reel", count = 3, budgetTokens = 400_000)
        assertEquals("→ تریدیار/رسانه و طراحی + کوینه‌پرو FX؛ خروجی: 3 ریلز؛ بودجه: 400K واحد مصرف", routeLineFa(r, { names.getValue(it) }))
        assertEquals("خط هاب", routeLineFa(r.copy(previewFa = "خط هاب"), { it }))
        assertTrue(routeLineFa(r.copy(mode = "council", budgetTokens = null), { names.getValue(it) }).endsWith("با شورا"))
    }

    @Test
    fun aRouteGoesBackWithExactlyTheContractsFields() {
        val r = OrderRoute29(companies = listOf("TY"), department = "MEDIA", outputKind = "reel", count = 3, budgetTokens = 400_000, previewFa = "x", kind = "work")
        val keys = Api.json.encodeToJsonElement(OrderRoute29.serializer(), r).jsonObject.keys
        val allowed = setOf("companies", "department", "collaborators", "output_kind", "count", "budget_tokens", "mode", "player", "preview_fa", "confidence", "why_fa", "kind")
        assertTrue(keys.toString(), allowed.containsAll(keys))
        assertTrue("companies" in keys && "output_kind" in keys && "budget_tokens" in keys)
    }

    @Test
    fun aFixIsPostedSignedOrOpenedWhereTheOwnerDoesIt() {
        assertEquals(FixWay.POST, fixWay(Fix("budget.add", target = "100000")))
        assertEquals(FixWay.POST, fixWay(Fix("player.auto")))
        assertEquals(FixWay.SIGNED, fixWay(Fix("hiring.open")))
        assertEquals(FixWay.OPEN, fixWay(Fix("series.seal", target = "D-000031")))
        assertEquals(FixWay.OPEN, fixWay(Fix("connection.guide", target = "FX/telegram")))
        assertEquals("cartable/D-000031", fixRoute(Fix("series.seal", target = "D-000031"), "PC"))
        assertEquals("companies/FX/connections/telegram", fixRoute(Fix("connection.guide", target = "FX/telegram"), "TY"))
        assertEquals("companies/TY/connections/instagram", fixRoute(Fix("connection.guide", target = "instagram"), "TY"))
        assertEquals("oversight", fixRoute(Fix("lock.open", target = "H-0004"), "TY"))
        assertEquals("companies/TY", fixRoute(Fix("lock.open"), "TY"))
        assertEquals("companies/PC/people", fixRoute(Fix("hire", target = "PC"), "PC"))
        assertNull(fixRoute(Fix("budget.add"), "TY"))
    }

    @Test
    fun anEmployeesStateComesFromTheHubOrItsOlderActivity() {
        assertEquals("stuck", employeeStateOf("stuck", "idle"))
        assertEquals("thinking", employeeStateOf("thinking", null))
        assertEquals("working", employeeStateOf(null, "working"))
        assertEquals("stuck", employeeStateOf(null, "error"))
        assertEquals("idle", employeeStateOf(null, "sleeping"))
        assertEquals("idle", employeeStateOf("unknown", "sleeping"))
        assertEquals("error", avatarStateOf("stuck"))
        assertEquals("working", avatarStateOf("thinking"))
        assertEquals("idle", avatarStateOf("done"))
    }

    @Test
    fun figuresAndMovesAreLatin() {
        assertEquals("12,480", numberText(12_480.0))
        assertEquals("2.7%", numberText(2.7, "%"))
        assertEquals("71%", numberText(0.71, "percent"))
        assertEquals("14.2", numberText(14.2))
        assertEquals("0.5", numberText(0.5))
        assertEquals("—", figureText(null))
        assertEquals("26%", figureText(JsonPrimitive("26%")))
        val m = kpiMove(listOf(DayValue("a", 412.0), DayValue("b", null), DayValue("c", 587.0)))!!
        assertEquals(587.0, m.last, 0.0)
        assertEquals("+42%", moveText(m.pct!!))
        assertEquals("−4%", moveText(-4.2))
        assertNull(kpiMove(listOf(DayValue("a", 1.0))))
        assertNull(kpiMove(listOf(DayValue("a", 0.0), DayValue("b", 3.0)))!!.pct)
    }

    @Test
    fun theLongVoiceRestartsAtPausesAndCutsChunksUnderNinetySeconds() {
        assertTrue(LongVoiceRules.CHUNK_S <= 90.0)
        assertEquals(60.0, LongVoiceRules.PHONE_LIMIT_S, 0.0)
        assertEquals(1200.0, LongVoiceRules.MAX_S, 0.0)
        assertTrue(LongVoiceRules.restartAfter(android.speech.SpeechRecognizer.ERROR_NO_MATCH))
        assertTrue(LongVoiceRules.restartAfter(android.speech.SpeechRecognizer.ERROR_SPEECH_TIMEOUT))
        assertFalse(LongVoiceRules.restartAfter(android.speech.SpeechRecognizer.ERROR_NETWORK))
        assertEquals(0, LongVoiceRules.chunks(0.0))
        assertEquals(1, LongVoiceRules.chunks(85.0))
        assertEquals(15, LongVoiceRules.chunks(1200.0))
        assertEquals("سلام دنیا", LongVoiceRules.join("سلام ", " دنیا "))
        assertEquals("سلام", LongVoiceRules.join("سلام", "  "))
        assertEquals("دنیا", LongVoiceRules.join("", "دنیا"))
    }

    @Test
    fun anOwnersOrderOpensItsReport() {
        assertEquals("session/F-0041", Refs.route("F-0041"))
        assertEquals("session/F-0041", Refs.forLink("order", "F-0041"))
        assertEquals("sessions", Refs.forLink("order", null))
        assertEquals("rules", Refs.forLink("rule", "SO-021"))
        assertEquals("groups/content", Refs.forLink("group", "content"))
        // A longer prefix still wins.
        assertEquals("oversight", Refs.route("FI-0212"))
    }

    // --------------------------------------------------------------------- wire --
    @Test
    fun thePreviewAndAnOrderWithItsRoute() = runTest {
        server.enqueue(json("""{"companies":["TY"],"department":"MEDIA","collaborators":[],"output_kind":"reel","count":3,"budget_tokens":400000,"mode":"single","player":"auto","preview_fa":"→ تریدیار/رسانه","confidence":0.9,"why_fa":"","kind":"work"}"""))
        val r = api.orderPreview("سه ریلز", "voice")
        var req = server.takeRequest()
        assertEquals("/api/v1/orders/preview", req.url.encodedPath)
        assertEquals("""{"text":"سه ریلز","source":"voice"}""", req.body!!.utf8())
        assertEquals(3, r.count)
        server.enqueue(json("""{"ref":"F-0045","summary_fa":"رفت","routes":[],"routed_by":"rules"}""", 201))
        val o = api.order("سه ریلز", "voice", null, r.copy(player = "gemini"))
        req = server.takeRequest()
        assertEquals("/api/v1/orders", req.url.encodedPath)
        val body = Api.json.parseToJsonElement(req.body!!.utf8()).jsonObject
        val route = body["route"]!!.jsonObject
        assertEquals("gemini", (route["player"] as JsonPrimitive).content)
        assertEquals("reel", (route["output_kind"] as JsonPrimitive).content)
        assertEquals("F-0045", o.ref)
        // Without a route the body is as before.
        server.enqueue(json("""{"ref":"F-0046","summary_fa":"رفت","routes":[]}""", 201))
        api.order("x", "text", null)
        assertNull(Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject["route"])
    }

    @Test
    fun theOwnersPaceGoesWithTheNewSessionAndAnOlderHubGetsItRightAfter() = runTest {
        // ⟨2026-11-09⟩ the owner: «با من یا خودکار؟» is asked when the session is made, and the answer travels with the order.
        server.enqueue(json("""{"ref":"F-0047","summary_fa":"رفت","routes":[],"pace":"step"}""", 201))
        val o = api.orderWithPace("کارگروه محتوا از اول تا آخر", "text", null, null, "step")
        var body = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals("step", (body["pace"] as JsonPrimitive).content)
        assertEquals("step", o.pace)
        // A hub before it refuses the field: the order goes without it and the pace is set on the session at once.
        server.enqueue(json("""{"type":"x","title":"Validation failed","status":422,"code":"validation_failed","message_fa":"اطلاعات ارسال‌شده درست نیست.","fields":{"pace":"Extra inputs are not permitted"}}""", 422))
        server.enqueue(json("""{"ref":"F-0048","summary_fa":"رفت","routes":[],"pace":"auto"}""", 201))
        server.enqueue(json("""{"ref":"F-0048","state":"running","pace":"step"}"""))
        val old = api.orderWithPace("کارگروه محتوا", "text", null, null, "step")
        server.takeRequest()
        body = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertNull(body["pace"])
        val set = server.takeRequest()
        assertEquals("/api/v1/orders/F-0048/pace", set.url.encodedPath)
        assertEquals("""{"pace":"step"}""", set.body!!.utf8())
        assertEquals("step", old.pace)
        // Learnt once: the next order goes without the field at first.
        server.enqueue(json("""{"ref":"F-0049","summary_fa":"رفت","routes":[],"pace":"auto"}""", 201))
        api.orderWithPace("x", "text", null, null, "auto")
        assertNull(Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject["pace"])
    }

    @Test
    fun aRefusalKeepsTheFieldsTheHubNamedForTheErrorLog() {
        // ⟨2026-11-09⟩ F-0013's refused reply read only «اطلاعات ارسال‌شده درست نیست» in the log: the fields now go with it.
        val fields = Api.json.parseToJsonElement(
            """{"text":"String should have at most 2000 characters","Idempotency-Key":"required","items":[{"ref":"D-1"}]}""",
        ).jsonObject
        assertEquals("text: String should have at most 2000 characters; Idempotency-Key: required", problemFields(fields))
        assertNull(problemFields(null))
    }

    @Test
    fun aFixIsPostedAndASignedOneCarriesItsSeal() = runTest {
        server.enqueue(json("{}"))
        api.orderFix("F-0042", Fix("budget.add", target = "100000"), 100_000)
        var req = server.takeRequest()
        assertEquals("/api/v1/orders/F-0042/fix", req.url.encodedPath)
        val b = Api.json.parseToJsonElement(req.body!!.utf8()).jsonObject
        assertEquals("100000", (b["tokens"] as JsonPrimitive).content)
        assertNull(req.headers["X-Step-Up"])
        server.enqueue(MockResponse.Builder().code(204).build())
        var signed: Pair<String, String>? = null
        val su: com.coinepro.hq.core.net.StepUp = { a, t -> signed = a to t; "su" }
        assertNull(api.orderFix("F-0042", Fix("hiring.open", target = "TY"), stepUp = su))
        req = server.takeRequest()
        assertEquals("hiring.open" to "TY", signed)
        assertEquals("su", req.headers["X-Step-Up"])
    }

    @Test
    fun aLongVoiceGoesInChunksThenFinishes() = runTest {
        server.enqueue(json("""{"id":"stt-1"}""", 201))
        assertEquals("stt-1", api.sttStart("order").id)
        assertEquals("""{"purpose":"order"}""", server.takeRequest().body!!.utf8())
        val f = java.io.File.createTempFile("chunk", ".m4a").apply { writeBytes(byteArrayOf(1, 2, 3)) }
        server.enqueue(MockResponse.Builder().code(204).build())
        api.sttChunk("stt-1", 0, f)
        val req = server.takeRequest()
        assertEquals("PUT", req.method)
        assertEquals("/api/v1/transcribe/sessions/stt-1/chunks/0", req.url.encodedPath)
        assertEquals("audio/mp4", req.headers["Content-Type"])
        assertEquals(3L, req.bodySize)
        server.enqueue(json("""{"text":"همه‌ی متن","duration_s":95.5,"chunks":2,"segments":[]}"""))
        val done = api.sttFinish("stt-1")
        assertEquals("/api/v1/transcribe/sessions/stt-1/finish", server.takeRequest().url.encodedPath)
        assertEquals("همه‌ی متن", done.text)
        assertEquals(2, done.chunks)
        f.delete()
    }

    @Test
    fun rulesAreSealedOnTheStandingOrderAndTheirVersionsOnTheRule() = runTest {
        var signed: Pair<String, String>? = null
        server.enqueue(json("""{"ref":"SO-022","text_md":"x","applies_to":{"companies":["TY"]},"status":"sealed"}"""))
        val r = api.sealRule("SO-022") { a, t -> signed = a to t; "su" }
        assertEquals("/api/v1/oversight/orders/SO-022/seal", server.takeRequest().url.encodedPath)
        assertEquals("oversight.order" to "SO-022", signed)
        assertEquals("sealed", r.status)
        server.enqueue(json("""{"ref":"SO-022","text_md":"y","status":"sealed","version":2}"""))
        api.putRule("SO-022", "y") { a, t -> signed = a to t; "su" }
        val req = server.takeRequest()
        assertEquals("PUT", req.method)
        assertEquals("rule.seal" to "SO-022", signed)
        server.enqueue(json("""[{"ref":"SO-021","text_md":"x","applies_to":"all","status":"sealed"}]"""))
        assertEquals("SO-021", api.rules().single().ref)
        server.enqueue(json("""{"items":[{"ref":"SO-021","text_md":"x","status":"sealed"}],"next_cursor":null}"""))
        assertEquals(1, api.rules().size)
    }

    @Test
    fun aConnectionsKeyIsWriteOnlyAndSigned() = runTest {
        var signed: Pair<String, String>? = null
        server.enqueue(MockResponse.Builder().code(204).build())
        api.putConnectionSecret("TY", "instagram", "s3cr3t") { a, t -> signed = a to t; "su" }
        val req = server.takeRequest()
        assertEquals("PUT", req.method)
        assertEquals("/api/v1/companies/TY/connections/instagram/secret", req.url.encodedPath)
        assertEquals("connection.secret" to "TY/instagram", signed)
        server.enqueue(json("""{"company":"TY","kind":"instagram","state":"connected","secret":"set"}"""))
        api.putConnectionConfig("TY", "instagram", JsonObject(mapOf("account" to JsonPrimitive("@tradeyar")))) { a, t -> signed = a to t; "su" }
        assertEquals("""{"config":{"account":"@tradeyar"}}""", server.takeRequest().body!!.utf8())
        assertEquals("connection.config" to "TY/instagram", signed)
    }

    @Test
    fun theTechnicalFindingsAskEveryTechnicalDomainOfTheCompany() = runTest {
        repeat(3) { i ->
            server.enqueue(json("""{"items":[{"ref":"FI-0${i}01","company":"TY","severity":"high","title_fa":"x","status":"open","opened_at":"2026-10-1${i}T08:00:00Z","domain":"tech"}],"next_cursor":null}"""))
        }
        val list = api.techFindings("TY")
        val asked = List(3) { server.takeRequest().url }
        assertEquals(setOf("tech", "infra", "security"), asked.map { it.queryParameter("domain") }.toSet())
        assertTrue(asked.all { it.queryParameter("scope") == "all" && it.queryParameter("company") == "TY" })
        assertEquals(3, list.size)
        assertNotNull(list.firstOrNull { it.ref == "FI-0201" })
    }
}
