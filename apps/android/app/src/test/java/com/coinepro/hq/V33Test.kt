package com.coinepro.hq

import com.coinepro.hq.core.data.dollars
import com.coinepro.hq.core.data.evidenceRoute
import com.coinepro.hq.core.data.gapUsdt
import com.coinepro.hq.core.data.hasImpact
import com.coinepro.hq.core.data.impactSortKey
import com.coinepro.hq.core.data.impactText
import com.coinepro.hq.core.data.journeyCurrentIndex
import com.coinepro.hq.core.data.journeyReached
import com.coinepro.hq.core.data.leadStages
import com.coinepro.hq.core.data.moneyFigure
import com.coinepro.hq.core.data.nextAtIso
import com.coinepro.hq.core.data.openLeads
import com.coinepro.hq.core.data.partsDoneLine
import com.coinepro.hq.core.data.payAddressOk
import com.coinepro.hq.core.data.pctText
import com.coinepro.hq.core.data.personaOf
import com.coinepro.hq.core.data.rateText
import com.coinepro.hq.core.data.reconcileLine
import com.coinepro.hq.core.data.reconcileProblems
import com.coinepro.hq.core.data.retainedPercents
import com.coinepro.hq.core.data.scoreTone
import com.coinepro.hq.core.data.tokensShort
import com.coinepro.hq.core.data.usdtInput
import com.coinepro.hq.core.data.vsPrevFa
import com.coinepro.hq.core.data.workspaceStoppable
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.AffiliateGap
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.DecisionImpact
import com.coinepro.hq.core.net.Journey
import com.coinepro.hq.core.net.JourneyBoard
import com.coinepro.hq.core.net.LeadDraft
import com.coinepro.hq.core.net.LeadIn
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.Page
import com.coinepro.hq.core.net.PayReadResult
import com.coinepro.hq.core.net.PayReconcile
import com.coinepro.hq.core.net.PayRow
import com.coinepro.hq.core.net.PaySource
import com.coinepro.hq.core.net.PaySourceIn
import com.coinepro.hq.core.net.PersonaIn
import com.coinepro.hq.core.net.PersonaSuggestion
import com.coinepro.hq.core.net.PersonaTest
import com.coinepro.hq.core.net.RevSummary33
import com.coinepro.hq.core.net.RevenueBoard
import com.coinepro.hq.core.net.SalesLead
import com.coinepro.hq.core.net.SalesPersona
import com.coinepro.hq.core.net.SalesPipeline
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.UsageReport
import com.coinepro.hq.core.net.WorkStopped
import java.time.LocalDate
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
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
 * Contract §33 ⟨1.15⟩ against the hub's OpenAPI (`hq-api.v1.json`): every model decodes the shapes the routes answer (money as a Decimal
 * string, a nullable field as null), every body carries only its model's keys (the hub forbids any other), the calls use the methods,
 * paths, headers and page limits the hub takes, and the formatting the screens show.
 */
@RunWith(RobolectricTestRunner::class)
class V33Test {
    private val json = Api.json
    private val server = MockWebServer()
    private lateinit var api: Api
    private val signed = mutableListOf<Pair<String, String>>()

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
    }

    @After
    fun tearDown() = server.close()

    private fun answer(body: String, code: Int = 200) =
        server.enqueue(MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build())

    // ------------------------------------------------------------ decoding --
    @Test
    fun paymentSourceAndPaymentsDecodeTheOpenApiShapes() {
        val s = json.decodeFromString(PaySource.serializer(), """{"id":"5b0c1e7a-0000-4000-8000-000000000002","company":"TY","kind":"chain","adapter":"chain_read",
            "network":"bsc_usdt","address":"0x8f3a91c2d4e5b6a7c8d9e0f1a2b3c4d5e6f7a9b1","server":null,"enabled":false,"state":"error","last_read_at":null,
            "last_error_fa":"شبکه جواب نداد."}""")
        assertEquals("5b0c1e7a-0000-4000-8000-000000000002", s.id)
        assertFalse(s.enabled)
        assertEquals("error", s.state)
        val page = json.decodeFromString(Page.serializer(PayRow.serializer()), """{"items":[{"id":"9a7e0000-0000-4000-8000-000000000001","company":"TY",
            "source":"5b0c1e7a-0000-4000-8000-000000000001","ext_id":"ord-1","customer":null,"plan":null,"amount_usdt":null,"chain_amount":"45.00",
            "network":"bsc_usdt","tx_hash":"0xab","paid_at":"2026-10-16T10:00:00Z","period_start":null,"period_end":null,"status":"chain_only",
            "checked_at":"2026-10-17T08:00:00Z","note_fa":"بی‌مشتری"},{"id":"x","company":"TY","source":"y","ext_id":"ord-2","amount_usdt":"249.00",
            "paid_at":"2026-10-15T10:00:00Z","status":"amount_mismatch","checked_at":"2026-10-17T08:00:00Z","chain_amount":"199.5"}],"next_cursor":"c1"}""")
        assertNull(page.items[0].amountUsdt)
        assertEquals(45.0, page.items[0].chainAmount!!, 0.0)
        assertNull(page.items[0].customer)
        assertEquals(249.0, page.items[1].amountUsdt!!, 0.0)
        assertEquals("c1", page.nextCursor)
        val r = json.decodeFromString(PayReconcile.serializer(), """{"company":"TY","day":"2026-10-16","ledger_count":5,"chain_count":5,"matched":3,
            "ledger_only":1,"chain_only":0,"amount_mismatch":0,"pending_chain":1,"note_fa":""}""")
        assertEquals(1, reconcileProblems(r))
        assertEquals("3 از 5 تطبیق شد", reconcileLine(r))
        val read = json.decodeFromString(PayReadResult.serializer(), """{"source":{"id":"a","company":"TY","kind":"ledger","adapter":"ledger_v1","state":"ok"},"queued":true,"payments":0}""")
        assertTrue(read.queued)
        assertEquals("ledger", read.source.kind)
    }

    @Test
    fun revenueBoardAndBySourceDecodeDecimalsAsStrings() {
        val b = json.decodeFromString(RevenueBoard.serializer(), """{"company":null,"period":"month","months":[{"month":"2026-09","mrr_usdt":"2390.00",
            "new_customers":9,"churned":3,"active":80,"arpu_usdt":null}],"churn_rate":0.046,"ltv_usdt":"650.20","cac_usdt":null,"payback_months":null,
            "cohorts":[{"start_month":"2026-03","size":12,"retained":[100.0,91.0,82.0]}],"forecast":[{"month":"2026-10","mrr_usdt":"2580.00","low":"2460.00",
            "high":"2700.00"}],"forecast_basis_fa":"روند هولت","roi":{"revenue_usdt":"2610.00","cost_usd":{"tokens":"181.00","voice":"21.84","ads":"109.20",
            "servers":null},"ratio":8.4},"cost_per_output":[{"kind":"line_run","count":64,"usd_each":null}]}""")
        assertNull(b.company)
        assertEquals(2390.0, b.months[0].mrrUsdt, 0.0)
        assertNull(b.months[0].arpuUsdt)
        assertEquals(650.2, b.ltvUsdt!!, 1e-9)
        assertNull(b.cacUsdt)
        assertEquals(312.04, b.roi!!.costUsd.total, 1e-9)
        assertNull(b.costPerOutput[0].usdEach)
        assertEquals(listOf(100.0, 91.0, 82.0), retainedPercents(b.cohorts[0]))
        assertEquals("4.6%", rateText(b.churnRate, 1))
        val s = json.decodeFromString(RevSummary33.serializer(), """{"period":"month","from":"2026-09-17","to":"2026-10-16","total_usdt":"12582.26",
            "alerts":[],"by_account":[],"by_company":[],"trend":[],"by_source":[{"company":"TY","affiliate_usdt":"7409.53","payments_usdt":"1840.00",
            "store_payments":2,"total_usdt":"9249.53"}]}""")
        assertEquals(1840.0, s.bySource.single().paymentsUsdt, 0.0)
        assertEquals(2, s.bySource.single().storePayments)
    }

    @Test
    fun usageReportDecodesWithAndWithoutWords() {
        val page = json.decodeFromString(Page.serializer(UsageReport.serializer()), """{"items":[{"ref":"UR-0014","period":"week","from":"2026-10-10T00:00:00Z",
            "to":"2026-10-17T00:00:00Z","at":"2026-10-17T05:30:00Z","words":"model","text":{"lines_fa":["یک","دو","سه"],"saving_fa":"صرفه"},
            "pack":{"period":"week","from":"2026-10-10T00:00:00Z","to":"2026-10-17T00:00:00Z","by_domain":[{"domain":"content","tokens":2400000,
            "usd_equiv":21.4,"share":0.41}],"by_company":[{"company":"TY","tokens":3100000,"usd_equiv":27.8,"share":0.53}],"top_runs":[{"ref":"R-1",
            "role":null,"tokens":310000}],"voice_usd":3.2,"lines":{"runs":21,"tokens":1100000},"ads_spend_usd":18,"vs_prev":{"tokens_pct":12.4,
            "usd_pct":null},"anomalies":[{"kind":"spike","note":"جهش"}]}},{"ref":"UR-0001","period":"day","from":"2026-10-16T00:00:00Z",
            "to":"2026-10-17T00:00:00Z","at":"2026-10-17T05:30:00Z","text":null,"pack":{"period":"day","from":"a","to":"b","by_domain":[],"by_company":[],
            "top_runs":[],"voice_usd":0,"lines":{"runs":0,"tokens":0},"ads_spend_usd":0,"vs_prev":{"tokens_pct":null,"usd_pct":null},"anomalies":[]}}]}""")
        val r = page.items[0]
        assertEquals(3, r.text!!.linesFa.size)
        assertEquals(2_400_000L, r.pack.byDomain[0].tokens)
        assertNull(r.pack.topRuns[0].role)
        assertEquals("12% بیشتر از دوره‌ی قبل", vsPrevFa(r.pack.vsPrev.tokensPct))
        assertNull(vsPrevFa(r.pack.vsPrev.usdPct))
        assertNull(page.items[1].text)
    }

    @Test
    fun salesShapesDecode() {
        val l = json.decodeFromString(SalesLead.serializer(), """{"ref":"LD-000041","company":"TY","source":"support","name_fa":null,"contact":"sp-71c2",
            "stage":"trial","value_usdt":"249.00","next_at":null,"next_fa":null,"assignee":{"kind":"agent","code":"TY-SAL-1"},"lost_reason_fa":null,
            "events":[{"at":"2026-10-11T08:00:00Z","kind":"created","note_fa":"از پشتیبانی"}],"created_at":"2026-10-11T08:00:00Z",
            "updated_at":"2026-10-16T08:00:00Z","version":4}""")
        assertEquals(249.0, l.valueUsdt!!, 0.0)
        assertEquals(4, l.version)
        val p = json.decodeFromString(SalesPipeline.serializer(), """{"company":"TY","stages":[{"stage":"new","title_fa":"جدید","kind":"open","count":2,
            "value_usdt":"0","median_days":null},{"stage":"paid","title_fa":"پرداخت کرد","kind":"won","count":1,"value_usdt":"79.00","median_days":null},
            {"stage":"lost","title_fa":"از دست رفت","kind":"lost","count":1,"value_usdt":"0","median_days":null}],"win_rate":0.5,"open_count":2,
            "won_count":1,"lost_count":1,"open_value_usdt":"0","total":4}""")
        assertEquals(listOf("new", "paid", "lost"), leadStages(p).map { it.stage })
        assertEquals(6, leadStages(null).size)
        assertEquals("50%", rateText(p.winRate))
        val d = json.decodeFromString(LeadDraft.serializer(), """{"lead":"LD-000041","draft_fa":"سلام","guard_ok":false,"blocked_reasons":["لینک بیرونی"],"sent":false}""")
        assertFalse(d.guardOk)
        assertEquals(listOf("لینک بیرونی"), d.blockedReasons)
        val g = json.decodeFromString(ListSerializer(AffiliateGap.serializer()), """[{"company":"TY","account":"lbank-ty","exchange":"lbank","month":"2026-09-01",
            "due_usdt":"1840.00","received_usdt":"1622.50","gap_usdt":"217.50","gap_pct":11.82,"settles_on":"2026-10-10","state":"open","draft_fa":null,
            "work_ref":"W-000287"}]""").single()
        assertEquals(217.5, gapUsdt(g), 0.0)
        assertEquals("11.8%", pctText(g.gapPct, 1))
    }

    @Test
    fun orderReportPartsAndWorkspacesDecode() {
        val o = json.decodeFromString(OrderReport.serializer(), """{"ref":"F-0045","text_fa":"گزارش","at":"2026-10-17T04:30:00Z","state":"in_progress",
            "route":{"companies":["TY"],"collaborators":[],"output_kind":"report","player":"claude","mode":"parallel"},"updated_at":"2026-10-17T08:24:00Z",
            "parts":[{"work_ref":"W-000300","state":"running","proposed_by":"TY-CEO","created_at":"2026-10-17T04:34:00Z","parts":[
            {"n":1,"ref":"W-000301","title_fa":"تحلیل","role":"analyst","state":"delivered","status":"done","progress_pct":100,"output_ref":"O-1",
            "output_title_fa":"خروجی","tokens_used":142000},{"n":2,"ref":"W-000302","title_fa":"خبر","role":"researcher","state":"failed","status":"failed",
            "failed_fa":"داده نبود"}]}],"workspaces":[{"work_ref":"W-000304","server":"tradeyar-main","path":"~/hq-workspace/W-000304","state":"awaiting_seal",
            "turns":7,"where_fa":"تریدیار · سرور اصلی","updated_at":"2026-10-17T08:24:00Z"}]}""")
        assertEquals("1 از 2", partsDoneLine(o.parts.single().parts))
        assertEquals("داده نبود", o.parts.single().parts[1].failedFa)
        assertTrue(workspaceStoppable(o.workspaces.single().state))
        assertFalse(workspaceStoppable("delivered"))
        assertFalse(workspaceStoppable("stopped"))
        val stopped = json.decodeFromString(WorkStopped.serializer(), """{"work_ref":"W-000304","jobs_stopped":1,"workspace":"stopped"}""")
        assertEquals("stopped", stopped.workspace)
    }

    @Test
    fun journeyAndPersonasDecode() {
        val b = json.decodeFromString(JourneyBoard.serializer(), """{"journeys":[{"company":"PC","current":"first_content","days_in_stage":8,"next_fa":null,
            "stages":[{"key":"founded","title_fa":"تأسیس","reached_at":"2026-08-01T07:00:00Z","evidence":{"kind":"company","ref":"PC"}},
            {"key":"server_ready","title_fa":"سرور آماده","reached_at":"2026-08-10T07:00:00Z","evidence":{"kind":"server","ref":null}},
            {"key":"first_content","title_fa":"اولین محتوا","reached_at":"2026-09-01T07:00:00Z","evidence":{"kind":"line_run","ref":"RN-000118"}},
            {"key":"first_lead","title_fa":"اولین سرنخ","reached_at":null,"evidence":null}]}],
            "timeline":[{"at":"2026-09-01T07:00:00Z","company":"PC","stage":"first_content","title_fa":"اولین محتوا"}]}""")
        val j: Journey = b.journeys.single()
        assertEquals(2, journeyCurrentIndex(j))
        assertEquals(3, journeyReached(j))
        assertEquals("line-runs/RN-000118", evidenceRoute("PC", j.stages[2]))
        assertEquals("companies/PC/servers", evidenceRoute("PC", j.stages[1]))
        assertNull(evidenceRoute("PC", j.stages[3]))
        assertEquals("first_content", b.timeline.single().stage)
        val list = json.decodeFromString(ListSerializer(SalesPersona.serializer()), """[{"id":"a1e0c3d2-0000-4000-8000-000000000001","company":"TY",
            "name_fa":"تازه‌کار","summary_fa":"خلاصه","pains_fa":["درد"],"objections_fa":[],"channel_fa":"تلگرام","source":"owner","version":2}]""")
        val t = json.decodeFromString(PersonaTest.serializer(), """{"id":"c0ffee00-0000-4000-8000-000000000001","text":"متن","average":52,"lowest":34,
            "at":"2026-10-17T08:30:00Z","results":[{"persona":"a1e0c3d2-0000-4000-8000-000000000001","name_fa":"تازه‌کار","score":78,"would_act":true,
            "objection_fa":null,"fix_fa":"یک نمونه"}]}""")
        assertEquals("تازه‌کار", personaOf(list, t.results.single())!!.nameFa)
        assertEquals(Tone.POS, scoreTone(78))
        assertEquals(Tone.WARN, scoreTone(52))
        assertEquals(Tone.NEG, scoreTone(34))
        val s = json.decodeFromString(PersonaSuggestion.serializer(), """{"company":"TY","basis_fa":"از دانشنامه","personas":[{"name_fa":"محتاط",
            "summary_fa":"خلاصه","pains_fa":[],"objections_fa":[],"channel_fa":"سایت"}]}""")
        assertEquals("محتاط", s.personas.single().nameFa)
    }

    @Test
    fun decisionImpactIsAdditiveAndSorts() {
        val base = """{"id":"x","ref":"D-000035","company":"TY","kind":"proposal","title":"t","status":"pending","proposer":{"kind":"agent","code":"TY-CEO"},
            "created_at":"2026-10-17T08:00:00Z""""
        val none = json.decodeFromString(Decision.serializer(), "$base}")
        assertNull(none.impact)
        val est = json.decodeFromString(Decision.serializer(), "$base,\"impact\":{\"revenue_usdt\":640.0,\"cost_usd\":null,\"horizon_days\":30,\"basis_fa\":\"پایه\",\"kind\":\"estimate\"}}").impact!!
        val cost = DecisionImpact(revenueUsdt = null, costUsd = 42.5, horizonDays = 30, kind = "measured")
        assertEquals("+640 USDT/ماه", impactText(est))
        assertEquals("−42.50 USD/ماه", impactText(cost))
        assertFalse(hasImpact(DecisionImpact(horizonDays = 30)))
        assertTrue(impactSortKey(est) < impactSortKey(cost))
        assertEquals(Double.MAX_VALUE, impactSortKey(null), 0.0)
    }

    // -------------------------------------------------------------- bodies --
    @Test
    fun requestBodiesCarryOnlyTheirModelsKeys() {
        val chain = json.encodeToString(PaySourceIn.serializer(), PaySourceIn(kind = "chain", network = "bsc_usdt", address = "0x8f3a91c2d4e5b6a7c8d9e0f1a2b3c4d5e6f7a9b1"))
        assertEquals("""{"kind":"chain","network":"bsc_usdt","address":"0x8f3a91c2d4e5b6a7c8d9e0f1a2b3c4d5e6f7a9b1"}""", chain)
        val off = json.encodeToString(PaySourceIn.serializer(), PaySourceIn(kind = "ledger", server = "tradeyar-main", enabled = false))
        assertEquals("""{"kind":"ledger","server":"tradeyar-main","enabled":false}""", off)
        val lead = json.encodeToJsonElement(LeadIn.serializer(), LeadIn(nameFa = "مشتری", valueUsdt = "120")).jsonObject
        assertEquals(setOf("name_fa", "value_usdt"), lead.keys)
        val patch = json.encodeToJsonElement(PersonaIn.serializer(), PersonaIn("نام", "خلاصه", listOf("درد"), source = null)).jsonObject
        assertFalse("source" in patch.keys)
        assertTrue(patch.keys.all { it in setOf("name_fa", "summary_fa", "pains_fa", "objections_fa", "channel_fa") })
    }

    @Test
    fun sourceIsSealedOnTheExactBodyWithAnIdempotencyKey() = runTest {
        answer("""{"id":"n","company":"TY","kind":"chain","adapter":"chain_read","state":"not_configured"}""", 201)
        val body = PaySourceIn(kind = "chain", network = "trc20_usdt", address = "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE")
        api.savePaymentSource("TY", body) { a, t -> signed += a to t; "su" }
        val req = server.takeRequest()
        val text = req.body!!.utf8()
        assertEquals("POST", req.method)
        assertEquals("/api/v1/companies/TY/payment-sources", req.url.encodedPath)
        assertEquals("payment.source" to Api.sha256(text), signed.single())
        assertEquals("su", req.headers["X-Step-Up"])
        assertTrue(!req.headers["Idempotency-Key"].isNullOrBlank())
    }

    @Test
    fun readNowSendsThePressKeyAndPaymentsArePaged() = runTest {
        answer("""{"source":{"id":"s1","company":"TY","kind":"chain","adapter":"chain_read","state":"ok"},"transfers":3,"pages":1}""")
        val r = api.readPaymentSource("s1", "press-key-1")
        val read = server.takeRequest()
        assertEquals("/api/v1/payment-sources/s1/read", read.url.encodedPath)
        assertEquals("press-key-1", read.headers["Idempotency-Key"])
        assertEquals(3, r.transfers)
        answer("""{"items":[],"next_cursor":null}""")
        api.payments("TY", status = "ledger_only", cursor = "c2", limit = 1000)
        val p = server.takeRequest().url
        assertEquals("200", p.queryParameter("limit"))
        assertEquals("ledger_only", p.queryParameter("status"))
        assertEquals("c2", p.queryParameter("cursor"))
    }

    @Test
    fun leadPatchCarriesIfMatchAndOnlyLeadPatchKeys() = runTest {
        val lead = SalesLead(ref = "LD-000041", version = 4)
        answer("""{"ref":"LD-000041","company":"TY","contact":"c","stage":"lost","version":5,"created_at":"a","updated_at":"b","source":"manual"}""")
        val out = api.patchLead(lead, buildJsonObject { put("stage", JsonPrimitive("lost")); put("next_at", JsonNull); put("id", JsonPrimitive("drop")) })
        val req = server.takeRequest()
        assertEquals("PATCH", req.method)
        assertEquals("\"4\"", req.headers["If-Match"])
        val sent = json.parseToJsonElement(req.body!!.utf8()).jsonObject
        assertEquals(setOf("stage", "next_at"), sent.keys)
        assertEquals(JsonNull, sent["next_at"])
        assertEquals(5, out.version)
    }

    @Test
    fun decisionsSortByImpactAndWorkStopResolvesARef() = runTest {
        answer("""{"items":[],"next_cursor":null}""")
        api.decisions("pending", limit = 100, sort = "impact")
        assertEquals("impact", server.takeRequest().url.queryParameter("sort"))
        answer("""{"items":[{"id":"w-uuid","ref":"W-000304","company":"TY","title":"t","status":"in_progress","kind":"task","created_at":"a"}],"next_cursor":null}""")
        answer("""{"id":"w-uuid","ref":"W-000304","company":"TY","title":"t","status":"in_progress","kind":"task","created_at":"a"}""")
        answer("""{"work_ref":"W-000304","jobs_stopped":1,"workspace":"stopped"}""")
        val s = api.stopWork("W-000304")
        server.takeRequest()
        server.takeRequest()
        val stop = server.takeRequest()
        assertEquals("POST", stop.method)
        assertEquals("/api/v1/work/w-uuid/stop", stop.url.encodedPath)
        assertEquals("stopped", s.workspace)
    }

    @Test
    fun personaEditIsAPatchWithoutSource() = runTest {
        answer("""{"id":"p1","company":"TY","name_fa":"ن","summary_fa":"خ","pains_fa":[],"objections_fa":[],"channel_fa":"","source":"owner","version":2}""")
        api.editPersona("p1", PersonaIn("ن", "خ", source = "owner"))
        val req = server.takeRequest()
        assertEquals("PATCH", req.method)
        assertEquals("/api/v1/personas/p1", req.url.encodedPath)
        assertFalse("source" in json.parseToJsonElement(req.body!!.utf8()).jsonObject.keys)
    }

    // ---------------------------------------------------------- formatting --
    @Test
    fun figuresAndInputs() {
        assertEquals("1,240", moneyFigure(1240.0))
        assertEquals("12.50", moneyFigure(12.5))
        assertEquals("4.5%", pctText(4.5, 1))
        assertEquals("4%", rateText(0.04))
        assertEquals("—", rateText(null))
        assertEquals("\$1,234.50", dollars(1234.5))
        assertEquals("1.2M", tokensShort(1_240_000))
        assertEquals("84K", tokensShort(84_000))
        assertEquals("1.5K", tokensShort(1_500))
        assertEquals("950", tokensShort(950))
        assertEquals("1250", usdtInput("1,250"))
        assertEquals("12.5", usdtInput("12.50"))
        assertEquals("120", usdtInput("۱۲۰"))
        assertNull(usdtInput("-3"))
        assertNull(usdtInput("abc"))
        assertNull(usdtInput(" "))
        assertTrue(payAddressOk("bsc_usdt", "0x8f3a91c2d4e5b6a7c8d9e0f1a2b3c4d5e6f7a9b1"))
        assertFalse(payAddressOk("bsc_usdt", "0x8f3a"))
        assertTrue(payAddressOk("trc20_usdt", "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE"))
        assertFalse(payAddressOk("trc20_usdt", "0x8f3a91c2d4e5b6a7c8d9e0f1a2b3c4d5e6f7a9b1"))
        // 09:00 Tehran (UTC+3:30) is 05:30 UTC.
        assertEquals("2026-10-18T05:30:00Z", nextAtIso(1, LocalDate.parse("2026-10-17")))
    }

    @Test
    fun openLeadsLeaveTheClosedStagesOut() {
        val xs = listOf(
            SalesLead(ref = "LD-1", stage = "paid"), SalesLead(ref = "LD-2", stage = "trial", nextAt = "2026-10-20T05:30:00Z"),
            SalesLead(ref = "LD-3", stage = "new", nextAt = "2026-10-18T05:30:00Z"), SalesLead(ref = "LD-4", stage = "won_big"),
        )
        assertEquals(listOf("LD-3", "LD-2", "LD-4"), openLeads(xs).map { it.ref })
        assertEquals(listOf("LD-3", "LD-2"), openLeads(xs, closed = setOf("paid", "won_big")).map { it.ref })
    }

    @Test
    fun theDemoAnswersInTheModelsShapes() {
        val demo = V33Demo()
        fun get(path: String, q: Map<String, String?> = emptyMap()) = demo.handle("GET", path, q, null)!!.second
        json.decodeFromJsonElement(ListSerializer(PaySource.serializer()), get("/companies/TY/payment-sources"))
        val first = json.decodeFromJsonElement(Page.serializer(PayRow.serializer()), get("/companies/TY/payments", mapOf("limit" to "10")))
        assertEquals(10, first.items.size)
        val rest = json.decodeFromJsonElement(Page.serializer(PayRow.serializer()), get("/companies/TY/payments", mapOf("limit" to "10", "cursor" to first.nextCursor)))
        assertNull(rest.nextCursor)
        json.decodeFromJsonElement(ListSerializer(PayReconcile.serializer()), get("/companies/TY/reconcile"))
        assertTrue(json.decodeFromJsonElement(RevenueBoard.serializer(), get("/revenue/board")).months.size >= 4)
        json.decodeFromJsonElement(ListSerializer(AffiliateGap.serializer()), get("/revenue/affiliate-gaps"))
        json.decodeFromJsonElement(Page.serializer(UsageReport.serializer()), get("/usage/reports", mapOf("period" to "week")))
        json.decodeFromJsonElement(Page.serializer(SalesLead.serializer()), get("/companies/TY/leads"))
        json.decodeFromJsonElement(SalesPipeline.serializer(), get("/companies/TY/pipeline"))
        json.decodeFromJsonElement(JourneyBoard.serializer(), get("/journeys"))
        json.decodeFromJsonElement(ListSerializer(SalesPersona.serializer()), get("/companies/TY/personas"))
        val o = json.decodeFromJsonElement(OrderReport.serializer(), get("/orders/F-0045/report"))
        assertEquals(3, o.parts.single().parts.size)
        assertEquals(1, o.workspaces.size)
        val t = json.decodeFromJsonElement(PersonaTest.serializer(), demo.handle("POST", "/companies/TY/personas/test", emptyMap(), JsonObject(mapOf("text" to JsonPrimitive("متن"))))!!.second)
        assertEquals(3, t.results.size)
    }
}
