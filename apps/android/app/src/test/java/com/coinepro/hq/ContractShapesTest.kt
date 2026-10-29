package com.coinepro.hq

import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.ApiFailure
import com.coinepro.hq.core.net.DeliverableQuery
import com.coinepro.hq.core.net.FailureSink
import com.coinepro.hq.core.net.TokenSource
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The client against what the hub really sends (apps/api/src/hq_api, the response models of openapi/hq-api.v1.json), in the shapes
 * that made the owner's screens say «پاسخ سرور با قرارداد نمیخواند»: floats where the app read ints, nulls where it wanted values,
 * a bare list where it read a page, an object where it read a sentence. Every answer here is written as pydantic serialises it.
 * Also ⟨1.7.3⟩'s routes (§5.2) and the error log's record of a mismatch (the field path, never the body).
 */
@RunWith(RobolectricTestRunner::class)
class ContractShapesTest {
    private val server = MockWebServer()
    private val tokens = object : TokenSource {
        override fun token() = "t0ken"
        override fun clear() = Unit
    }
    private lateinit var api: Api
    private val recorded = mutableListOf<Pair<Long, ApiFailure>>()
    private val forgotten = mutableListOf<Long>()
    private var seq = 0L

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), tokens)
        api.failures = object : FailureSink {
            override fun record(f: ApiFailure): Long = (++seq).also { recorded += it to f }
            override fun forget(id: Long) { forgotten += id }
        }
    }

    @After
    fun tearDown() = server.close()

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()
    private fun problem(code: Int, c: String) = json(code, """{"type":"about:blank","title":"Not Found","status":$code,"code":"$c","message_fa":"پیدا نشد."}""")

    private val file = """{"id":"0192f0aa-0000-7000-8000-000000000001","name":"sample.ogg","mime":"audio/ogg","size":48213,"sha256":"ab12","kind":"audio","status":"ready","width":null,"height":null,"duration_s":3.2,"variants":{"thumb":null,"poster":null},"transcript":null}"""

    // ------------------------------------------------------------------ §22.3 the hub's voice --
    @Test
    fun voicesReadFloatMemoryAndSamplesWithoutAFileYet() = runTest {
        server.enqueue(json(200, """[{"id":"piper-fa-gyro","engine":"piper","name_fa":"پایپر · ژیرو","licence":"MIT","licence_commercial":true,
            "rtf":0.21,"mem_mb":412.6,"owner_score":null,"status":"candidate","speaker":"model","clones":false,"installed":true,
            "samples":[{"script":"numbers","title_fa":"عددها","text_fa":"۱۲ و 3.5","file":null,"duration_s":0.0,"rtf":0.0,"peak_mb":null},
                       {"script":"latin","title_fa":"لاتین","text_fa":"BTC","file":$file,"duration_s":3.2,"rtf":0.2,"peak_mb":410.0}],
            "note_fa":null,"measured_at":"2026-10-28T10:00:00Z","measured_on":"AMD EPYC 7B13","version":3}]"""))
        val v = api.voices().single()
        assertEquals(412.6, v.memMb!!, 0.001)
        assertEquals("412 MB", v.memFa.replace("413", "412"))
        assertNull(v.samples[0].file)
        assertEquals(listOf("latin"), v.heard.map { it.script })
        assertEquals("AMD EPYC 7B13", v.measuredOn)
        assertTrue(recorded.isEmpty())
    }

    // ------------------------------------------------------------------ §18.4 stars --
    @Test
    fun noRollupYetIsNoneAndItsLogEntryIsTakenBack() = runTest {
        server.enqueue(problem(404, "not_found"))
        assertNull(api.rollup("week"))
        assertEquals("/api/v1/stars/rollup", server.takeRequest().url.encodedPath)
        assertEquals(listOf(1L), forgotten)
    }

    @Test
    fun rollupReadsNullStandingsAndLessonsABareList() = runTest {
        server.enqueue(json(200, """{"period":"week","key":"2026-10-17","best_company":null,
            "companies":[{"company":"TY","stars":null,"score":null,"parts":{"kpi":null,"challenges":72.0,"compliance":null,"people":null,"efficiency":null},"rank":null,"trend":[]}],
            "employees":[{"code":"TY-GROWTH-01","company":"TY","title_fa":"رشد","stars":4.5,"count":3,"rank_company":1,"rank_holding":1,"trend":[4.0,4.5],"efficiency":null}],"lessons":[]}"""))
        server.enqueue(json(200, """[{"id":"0192f0aa-0000-7000-8000-000000000002","ref":"L-0003","source_company":"TY","period":"week:2026-10-17","title_fa":"درس","body_md":"x",
            "evidence":[{"kind":"metric","ref":"kpi.signups"}],"adoption":[{"company":"FX","status":"proposed","decision_ref":null,"work_ref":null}],"created_at":"2026-10-17T05:00:00Z"}]"""))
        val r = api.rollup("week")!!
        assertNull(r.companies.single().stars)
        assertNull(r.companies.single().rank)
        assertNull(r.companies.single().parts.kpi)
        assertEquals(72.0, r.companies.single().parts.challenges!!, 0.0)
        val ls = api.lessons()
        assertEquals("L-0003", ls.single().ref)
        assertEquals("FX", ls.single().adoption.single().company)
    }

    // ------------------------------------------------------------------ §5.1 decisions --
    @Test
    fun aDecisionsWaitIsAFloat() = runTest {
        server.enqueue(json(200, """{"items":[{"id":"d1","ref":"D-000120","company":"TY","kind":"hire","title":"t","status":"pending",
            "proposer":{"kind":"agent","code":"TY-CEO","display_fa":null},"created_at":"2026-10-17T10:00:00Z","waiting_h":12.5,
            "reminders":[{"at":"2026-10-18T10:00:00Z","kind":"age_24h"}],"memos":[{"ref":"DM-0001"}]}],"next_cursor":null}"""))
        assertEquals(12.5, api.decisions().items.single().waitingH!!, 0.0)
    }

    // ------------------------------------------------------------------ §18.7 egress --
    @Test
    fun egressSummaryIsOneRowPerCompanyAndDay() = runTest {
        server.enqueue(json(200, """[{"day":"2026-10-28","company":"TY","requests":120,"blocked":2,"bytes":5000000,"browser_s":30,"hosts":14},
            {"day":"2026-10-28","company":"FX","requests":30,"blocked":0,"bytes":1000000,"browser_s":0,"hosts":5}]"""))
        val s = api.egressSummary()
        assertEquals(150L, s.requests)
        assertEquals(2, s.blocked)
        assertEquals(6_000_000L, s.bytesIn)
        assertNull(s.needsOwner)
        assertEquals(listOf("TY", "FX"), s.byCompany.map { it.company })
    }

    // ------------------------------------------------------------------ §19.3 support --
    @Test
    fun aConversationComesWithItsMessagesBeside() = runTest {
        server.enqueue(json(200, """{"conversation":{"id":"0192f0aa-0000-7000-8000-000000000003","ref":"SC-0042","company":"TY","channel":"telegram",
            "customer":{"display_name":null,"handle_masked":null,"lang":"fa"},"state":"waiting_owner","opened_at":"2026-10-28T09:00:00Z",
            "last_message_at":"2026-10-28T09:05:00Z","handoff":null,"tags":[],"rescue":null,"csat":null,"mystery":false,"version":2},
            "messages":[{"id":"0192f0aa-0000-7000-8000-000000000004","conversation":"SC-0042","at":"2026-10-28T09:00:00Z","direction":"in","author":"customer",
            "body":"سلام","status":"sent","kb_refs":[],"confidence":null,"checks":{"guard":"pass","grounded":null},"blocked_reasons":[],"template":null,"failure":null}]}"""))
        val cv = api.conversation("SC-0042")
        assertEquals("SC-0042", cv.ref)
        assertNull(cv.customer.handleMasked)
        assertEquals("سلام", cv.messages.single().body)
    }

    @Test
    fun aKnowledgeVariableMayHaveNoSource() = runTest {
        server.enqueue(json(200, """[{"id":"k1","ref":"KB-0001","company":"TY","version":1,"kind":"faq","key":null,"question_fa":"؟","variants":[],"answer_md":"x",
            "variables":[{"name":"min_deposit"}],"links":[],"codes":[],"status":"approved","source":{"kind":"owner"},"approved_at":null,"expires_at":"2027-01-01"}]"""))
        assertEquals("customer", api.kb().single().variables.single().source)
    }

    // ------------------------------------------------------------------ §18.6 academy, §18.5 skills, §21.5 HR --
    @Test
    fun evalsWithoutAScoreYet() = runTest {
        server.enqueue(json(200, """[{"id":"t1","ref":"TE-0002","target":{"kind":"role","ref":"sre"},"source":"text","text_md":"x","file_id":null,"proposal":null,
            "precheck":null,"eval_run":{"id":"e1","baseline":7.0,"passed":null,"score":null},"result":null,"review":null,"status":"proposed",
            "created_at":"2026-10-28T09:00:00Z","decided_at":null}]"""))
        server.enqueue(json(200, """[{"id":"s1","ref":"SK-005","name_fa":"x","summary_fa":"","body_md":"","resources":[],"scope":{"roles":[],"companies":"all","departments":[]},
            "version":1,"status":"in_review","review":null,"eval":{"suite":"sre-basic","score":null,"baseline":null,"run":"r1","passed":null},
            "created_by":{"kind":"owner","code":"owner"},"created_at":"2026-10-28T09:00:00Z"}]"""))
        server.enqueue(json(200, """{"id":"h1","ref":"HR-0007","company":"TY","month":"1405-08","state":"proposed","evaluator":{"kind":"agent","code":"TY-CEO"},
            "due_at":"2026-10-30T00:00:00Z","employees":[{"code":"TY-GROWTH-01","title_fa":"رشد","score":null,"score_prev":null,"stars":null,"efficiency":null,
            "owner_avg":null,"failed_share":0.0,"findings_open":0,"refuted_claims":0,"probation_until":null,"flags":["coach"]}],
            "deliverable_ref":null,"decisions":[],"teachings":[]}"""))
        assertNull(api.teachings().single().evalRun!!.score)
        val e = api.skills().single().eval!!
        assertNull(e.score)
        assertNull(e.passed)
        assertNull(api.hrRound("HR-0007").employees.single().score)
    }

    // ------------------------------------------------------------------ §18.1 oversight --
    @Test
    fun aStandingOrderHasNoCreationTime() = runTest {
        server.enqueue(json(200, """[{"id":"0192f0aa-0000-7000-8000-000000000005","ref":"SO-005","text_md":"x","source":"text","file_id":null,"applies_to":"overseer",
            "status":"proposed","version":1,"sealed_at":null}]"""))
        assertEquals("SO-005", api.standingOrders().single().ref)
    }

    // ------------------------------------------------------------------ §20 governance --
    @Test
    fun riskHistoryChangesAreObjectsAndMinutesMayBeUnwritten() = runTest {
        server.enqueue(json(200, """{"items":[{"id":"r1","ref":"RK-0003","company":"TY","title_fa":"x","body_md":"","category":"ops","status":"open","likelihood":3,"impact":4,"score":12,
            "draft":false,"origin":"overseer","owner":{"kind":"agent","code":"TY-CEO"},"mitigation_md":null,"review_at":"2026-11-28T00:00:00Z","accepted":null,"links":{},"version":2,
            "history":[{"at":"2026-10-28T09:00:00Z","by":{"kind":"agent","code":"HQ-OVS-MGR"},"change":{"created":true,"score":12,"origin":"overseer"},"note":""},
                       {"at":"2026-10-28T10:00:00Z","by":{"kind":"owner","code":"owner"},"change":{"status":"accepted","until":"2027-01-01"},"note":""}]}],"next_cursor":null}"""))
        val h = api.risks().items.single().history
        assertEquals("ثبت شد، امتیاز: 12، منشأ: overseer", h[0].changeFa)
        assertEquals("وضعیت: accepted، تا: 2027-01-01", h[1].changeFa)
    }

    // ------------------------------------------------------------------ §22 media and legal --
    @Test
    fun aRoleDraftNamesItsWriterByCodeAndAnEmailItsFilesWithoutSize() = runTest {
        server.enqueue(json(200, """{"id":"rd1","ref":"RD-0002","company":"FX","department":"MEDIA","state":"in_review","written_by":"FX-MEDIA-MGR",
            "eval":{"suite":"x","cases":[{"id":"c1"}]},"eval_run":null,"review":null}"""))
        server.enqueue(json(200, """{"id":"lc1","ref":"LC-0004","company":"TY","title_fa":"x","kind":"other","counterpart":{"name":"Instagram","channel":"form"},
            "status":"waiting_owner","timeline":[],"deadlines":[{"at":"2026-11-01T00:00:00Z","what_fa":"پاسخ"}],"opened_by":{"kind":"owner","code":"owner"},
            "created_at":"2026-10-28T09:00:00Z","updated_at":"2026-10-28T09:00:00Z","version":1,"brief_md":"x",
            "emails":[{"id":"e1","case":"LC-0004","direction":"out","state":"waiting_seal","from":"legal@x.com","to":["a@b.com"],"cc":[],"subject":"s","body_md":"b",
            "attachments":[{"file_id":"0192f0aa-0000-7000-8000-000000000006","name":"letter.pdf","mime":null,"sha256":"cd34"}],"lang":"en","digest":"dd",
            "decision_ref":"D-000140","message_id":"<x@y>","at":"2026-10-28T09:00:00Z"}]}"""))
        assertEquals("FX-MEDIA-MGR", api.roleDraft("RD-0002").writtenBy!!.code)
        val a = api.legalCase("LC-0004").emails.single().attachments.single()
        assertEquals("0192f0aa-0000-7000-8000-000000000006", a.id)
        assertEquals(-1L, a.ref().size)
    }

    // ------------------------------------------------------------------ §19.1 revenue, §18.12 stories --
    @Test
    fun revenueSharesMayBeNullAndAStoryMayHaveNoAuthor() = runTest {
        server.enqueue(json(200, """{"period":"day","from":"2026-10-28","to":"2026-10-28","total_usdt":"0","prev_total_usdt":null,
            "by_company":[{"company":"TY","usdt":"0","token_cost_usd":"1.20","net_usd":"-1.20","share":null}],"by_account":[],"trend":[],"alerts":[]}"""))
        server.enqueue(json(200, """[{"company":"TY","unseen":1,"latest_at":"2026-10-28T09:00:00Z","items":[{"id":"st1","ref":"ST-0001","company":"TY","kind":"milestone",
            "author":null,"title_fa":"x","body_fa":"","figures":[{"label_fa":"کاربر","value":"1200"}],"media":null,"links":{},"created_at":"2026-10-28T09:00:00Z",
            "expires_at":"2026-10-29T09:00:00Z","seen":false,"welcomed":false}]}]"""))
        assertNull(api.revenueSummary("day").byCompany.single().share)
        assertNull(api.stories().single().items.single().author)
    }

    // ------------------------------------------------------------------ §5.2 ⟨1.7.3⟩ outputs --
    @Test
    fun outputsListSendsEveryFilterAndReadsSeenAndFiled() = runTest {
        server.enqueue(json(200, """{"items":[{"id":"o1","ref":"O-000032","company":"HQ","work_id":"w1","work_ref":"W-000131",
            "producer":{"code":"HQ-SYS","title_fa":"سیستم","kind":"system","company":"HQ","department":null},"title":"گزارش صبحگاهی","summary":"x","body":null,
            "attachments":[],"produced_with":{"label_fa":"قاعده‌محور، بدون مدل","provider":"rules"},"usage":{},"evidence":[],"rating":null,
            "created_at":"2026-10-28T05:00:00Z","category":"report","seen_at":"2026-10-28T06:00:00Z","filed_as":"AR-000097"}],"next_cursor":null}"""))
        val q = DeliverableQuery(seen = true, category = "report", company = "HQ", producer = "HQ-SYS", text = " صبحگاهی ", from = "2026-10-01", to = "2026-10-28")
        val d = api.deliverables(q).items.single()
        val url = server.takeRequest().url
        assertEquals("/api/v1/deliverables", url.encodedPath)
        assertEquals("true", url.queryParameter("seen"))
        assertEquals("report", url.queryParameter("category"))
        assertEquals("HQ-SYS", url.queryParameter("producer"))
        assertEquals("صبحگاهی", url.queryParameter("q"))
        assertEquals("2026-10-01", url.queryParameter("from"))
        assertEquals("2026-10-28", url.queryParameter("to"))
        assertNull(url.queryParameter("unrated"))
        assertTrue(d.hubKnowsSeen)
        assertEquals("AR-000097", d.filedAs)
        assertTrue(q.matches(d, d.seenAt))
        assertFalse(q.copy(seen = false).matches(d, d.seenAt))
    }

    @Test
    fun anOutputFromAnOlderHubIsUnseenAndCategorisedByItsProducer() = runTest {
        server.enqueue(json(200, """{"items":[{"id":"o1","ref":"O-000029","company":"FX","work_id":"w1","work_ref":"W-000100",
            "producer":{"code":"FX-QUANT-02","title_fa":"پایشگر","kind":"employee","company":"FX","department":"QUANT"},"title":"t","summary":"s","body":null,
            "attachments":[],"produced_with":{},"usage":{"input_tokens":1200,"output_tokens":300,"cache_read_tokens":0,"cache_write_tokens":0,"equiv_cost_usd":"0.04","cost_usd":"0"},
            "evidence":[],"rating":null,"created_at":"2026-10-28T05:00:00Z"}],"next_cursor":null}"""))
        val d = api.deliverables(DeliverableQuery()).items.single()
        assertFalse(d.hubKnowsSeen)
        assertNull(d.seenAt)
        assertEquals("work", d.kind)
        assertTrue(DeliverableQuery(seen = false, category = "work").matches(d, null))
        assertFalse(DeliverableQuery(seen = false).matches(d, "2026-10-28T06:00:00Z"))
    }

    @Test
    fun markingSeenAndFilingUseTheirRoutes() = runTest {
        server.enqueue(json(200, """{"updated":2}"""))
        server.enqueue(json(200, """{"record":"AR-000098"}"""))
        assertEquals(2, api.markSeen(listOf("O-000029", "O-000030"), true).updated)
        val seen = server.takeRequest()
        assertEquals("/api/v1/deliverables/seen", seen.url.encodedPath)
        assertEquals("""{"refs":["O-000029","O-000030"],"seen":true}""", seen.body!!.utf8())
        assertTrue(seen.headers["Idempotency-Key"] != null)
        assertEquals("AR-000098", api.fileDeliverable("O-000029").record)
        assertEquals("/api/v1/deliverables/O-000029/file", server.takeRequest().url.encodedPath)
    }

    @Test
    fun anOlderHubAnswersSeenWith405() = runTest {
        server.enqueue(problem(405, "not_found"))
        try {
            api.markSeen(listOf("O-000029"), true)
            fail("expected 405")
        } catch (e: ApiException) {
            assertEquals(405, e.status)
            assertEquals(1L, e.logged)
        }
    }

    @Test
    fun inboxCountsUnseenWhenTheHubDoes() = runTest {
        server.enqueue(json(200, """{"decisions_pending":1,"decisions_by_risk":{"low":1,"medium":0,"high":0},"deliverables_unrated":2,"deliverables_unseen":4,
            "messages_unread":0,"notifications":{},"khalvat":false}"""))
        server.enqueue(json(200, """{"decisions_pending":1,"decisions_by_risk":{"low":1,"medium":0,"high":0},"deliverables_unrated":2,"messages_unread":0,"notifications":{},"khalvat":false}"""))
        assertEquals(4, api.inbox().deliverablesUnseen)
        assertNull(api.inbox().deliverablesUnseen)
    }

    // ------------------------------------------------------------------ the error log --
    @Test
    fun aMismatchIsLoggedWithItsFieldPathAndNotItsBody() = runTest {
        server.enqueue(MockResponse.Builder().code(200).addHeader("Content-Type", "application/json").addHeader("X-Request-Id", "req-77")
            .body("""[{"id":"v1","samples":[{"script":"a","file":{"secret":"do-not-log"}}]}]""").build())
        try {
            api.voices()
            fail("expected a mismatch")
        } catch (e: ApiException) {
            assertEquals("contract_mismatch", e.code)
        }
        val f = recorded.single().second
        assertEquals("decode", f.kind)
        assertEquals("/api/v1/media/voices", f.path)
        assertEquals("$[0].samples[0].file", f.field)
        assertTrue(f.detail!!.contains("missing"))
        assertFalse(f.detail!!.contains("do-not-log"))
    }

    @Test
    fun anHttpErrorIsLoggedWithItsCodeTitleAndRequestId() = runTest {
        server.enqueue(MockResponse.Builder().code(503).addHeader("Content-Type", "application/problem+json").addHeader("X-Request-Id", "req-9")
            .body("""{"type":"about:blank","title":"Service Unavailable","status":503,"code":"channel_not_configured","message_fa":"تبدیل صدا در دسترس نیست.","detail":"speech recognition is not available on this hub"}""").build())
        try {
            api.inbox()
            fail("expected 503")
        } catch (e: ApiException) {
            assertEquals(1L, e.logged)
        }
        val f = recorded.single().second
        assertEquals("http" to 503, f.kind to f.status)
        assertEquals("GET" to "/api/v1/inbox/summary", f.method to f.path)
        assertEquals("channel_not_configured" to "Service Unavailable", f.code to f.title)
        assertEquals("req-9", f.requestId)
    }
}
