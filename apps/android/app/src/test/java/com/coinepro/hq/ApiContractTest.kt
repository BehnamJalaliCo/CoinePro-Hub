package com.coinepro.hq

import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.GrantIn
import com.coinepro.hq.core.net.HireIn
import com.coinepro.hq.core.net.RoleInfo
import com.coinepro.hq.core.net.ServerPlan
import com.coinepro.hq.core.net.Skill
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.hireableRoles
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** The Android client against contract §1–§2, §17 and §18: Bearer session, X-HQ-Client, Idempotency-Key, step-up header,
 *  snake_case JSON, Problem errors with a Persian message, a 401 that ends the session, raw-body uploads and voice,
 *  and the step-up action and target of every 🔏 write (workshop, oversight, skills, academy, MCP, founding). */
@RunWith(RobolectricTestRunner::class)
class ApiContractTest {
    private val server = MockWebServer()
    private var token: String? = "t0ken"
    private val tokens = object : TokenSource {
        override fun token() = token
        override fun clear() { token = null }
    }
    private lateinit var api: Api

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), tokens)
    }

    @After
    fun tearDown() = server.close()

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    @Test
    fun getSendsBearerAndClientHeaders() = runTest {
        server.enqueue(json(200, """{"decisions_pending":4,"decisions_by_risk":{"low":2,"medium":1,"high":1},"deliverables_unrated":2,"messages_unread":3,"khalvat":false,"notifications":{"urgent":0,"decision":1,"report":0,"info":2,"learning":1},"new_field":"ignored"}"""))
        val inbox = api.inbox()
        val req = server.takeRequest()
        assertEquals("/api/v1/inbox/summary", req.url.encodedPath)
        assertEquals("Bearer t0ken", req.headers["Authorization"])
        assertEquals("android", req.headers["X-HQ-Client"])
        assertNull(req.headers["Idempotency-Key"])
        assertEquals(4, inbox.decisionsPending)
        assertEquals(1, inbox.decisionsByRisk.high)
        assertEquals(1, inbox.notifications["decision"])
    }

    @Test
    fun postCarriesIdempotencyKeyAndStepUp() = runTest {
        server.enqueue(json(200, """{"id":"d1","ref":"D-000014","company":"TY","kind":"hire","title":"t","status":"approved","proposer":{"code":"TY-TECH-MGR","kind":"agent"},"created_at":"2026-10-17T10:00:00Z","resolution":"M-0007"}"""))
        val d = api.approve("D-000014", null, "step-up-token")
        val req = server.takeRequest()
        assertEquals("/api/v1/decisions/D-000014/approve", req.url.encodedPath)
        assertNotNull(req.headers["Idempotency-Key"])
        assertEquals("step-up-token", req.headers["X-Step-Up"])
        assertTrue(req.body!!.utf8().contains("\"amendments\":null"))
        assertEquals("M-0007", d.resolution)
    }

    @Test
    fun problemBecomesPersianError() = runTest {
        server.enqueue(json(409, """{"type":"about:blank","title":"Conflict","status":409,"code":"already_decided","message_fa":"این تصمیم قبلاً گرفته شده است."}"""))
        try {
            api.decision("D-1")
            fail("expected ApiException")
        } catch (e: ApiException) {
            assertEquals(409, e.status)
            assertEquals("already_decided", e.code)
            assertEquals("این تصمیم قبلاً گرفته شده است.", e.messageFa)
        }
        assertEquals("t0ken", token)
    }

    @Test
    fun unauthorizedEndsTheSession() = runTest {
        server.enqueue(json(401, """{"code":"unauthenticated","message_fa":"دوباره وارد شو.","status":401,"title":"Unauthorized","type":"about:blank"}"""))
        try {
            api.inbox()
            fail("expected ApiException")
        } catch (e: ApiException) {
            assertTrue(e.isAuth)
        }
        assertNull(token)
    }

    @Test
    fun workByRefResolvesThroughSearch() = runTest {
        server.enqueue(json(200, """{"items":[{"id":"6f1c","ref":"W-000104","company":"FX","title":"x","status":"queued"}],"next_cursor":null}"""))
        server.enqueue(json(200, """{"id":"6f1c","ref":"W-000104","company":"FX","title":"x","status":"queued","chain":[]}"""))
        val w = api.workOne("W-000104")
        assertEquals("q=W-000104&limit=5", server.takeRequest().url.encodedQuery)
        assertEquals("/api/v1/work/6f1c", server.takeRequest().url.encodedPath)
        assertEquals("6f1c", w.id)
    }

    @Test
    fun uploadIsARawBodyWithItsNameAndType() = runTest {
        server.enqueue(json(201, """{"id":"f1","name":"نمودار طلا.webp","mime":"image/webp","size":5,"sha256":"ab","kind":"image","status":"ready","width":960,"height":600,"variants":{"thumb":"f1t"}}"""))
        var last = 0f
        val ref = api.upload("نمودار طلا.webp", "image/webp", 5, { "hello".byteInputStream() }) { last = it }
        val req = server.takeRequest()
        assertEquals("/api/v1/files", req.url.encodedPath)
        assertEquals("image/webp", req.headers["Content-Type"])
        assertEquals("%D9%86%D9%85%D9%88%D8%AF%D8%A7%D8%B1%20%D8%B7%D9%84%D8%A7.webp", req.headers["X-File-Name"])
        assertNotNull(req.headers["Idempotency-Key"])
        assertEquals("hello", req.body!!.utf8())
        assertEquals(1f, last)
        assertEquals("image", ref.kind)
        assertEquals("f1t", ref.variants.thumb)
        assertEquals(960, ref.width)
    }

    @Test
    fun transcribeSendsAudioWithPurpose() = runTest {
        server.enqueue(json(200, """{"text":"سلام","language":"fa","duration_s":2.5,"confidence":0.93,"segments":[{"start_s":0,"end_s":2.5,"text":"سلام"}],"file_id":"a1","engine":{"name":"faster-whisper","model":"large-v3-turbo","version":"1"}}"""))
        val f = java.io.File.createTempFile("voice", ".m4a").apply { writeBytes(byteArrayOf(1, 2, 3)) }
        val t = api.transcribe(f, "audio/mp4", "order")
        val req = server.takeRequest()
        assertEquals("/api/v1/transcribe", req.url.encodedPath)
        assertEquals("purpose=order", req.url.encodedQuery)
        assertEquals("audio/mp4", req.headers["Content-Type"])
        assertEquals(3L, req.bodySize)
        assertEquals("سلام", t.text)
        assertEquals("a1", t.fileId)
    }

    @Test
    fun messageCarriesAttachmentIds() = runTest {
        server.enqueue(json(201, """{"message":{},"reply":{"state":"queued"}}"""))
        api.send("FX-CEO", "ببین", listOf("f1", "a1"))
        assertTrue(server.takeRequest().body!!.utf8().contains("\"attachments\":[\"f1\",\"a1\"]"))
    }

    @Test
    fun allowingNeedsAStepUpButDenyingDoesNot() = runTest {
        val ev = """{"seq":10,"at":"2026-10-17T10:00:00Z","type":"approval_result","actor":{"code":"owner","kind":"owner"},"summary_fa":"x","data":{}}"""
        server.enqueue(json(201, ev))
        server.enqueue(json(201, ev))
        api.answerApproval("S-0004", "AP-0007", true, "su")
        val allow = server.takeRequest()
        assertEquals("/api/v1/workshop/sessions/S-0004/approvals/AP-0007", allow.url.encodedPath)
        assertEquals("su", allow.headers["X-Step-Up"])
        api.answerApproval("S-0004", "AP-0007", false, null)
        assertNull(server.takeRequest().headers["X-Step-Up"])
    }

    @Test
    fun grantStepUpIsBoundToTheExactBody() = runTest {
        server.enqueue(json(201, """{"id":"g1","ref":"G-0004","workspace":"FX-APP","actions":["read"],"budget_usd":10,"expires_at":"2026-10-20T10:00:00Z"}"""))
        var target = ""
        val g = api.createGrant(GrantIn("FX-APP", listOf("read", "run"), "FX-TECH-MGR", 10.0, "2026-10-20T10:00:00Z")) { target = it; "su" }
        val req = server.takeRequest()
        val body = req.body!!.utf8()
        assertEquals(Api.sha256(body), target)
        assertEquals("su", req.headers["X-Step-Up"])
        assertTrue(body.contains("\"budget_usd\":10.0"))
        assertEquals("G-0004", g.ref)
    }

    /** Runs [call] with a recording signer; returns the (action, target) it was asked to sign and the request sent. */
    private suspend fun signed(response: String, call: suspend (com.coinepro.hq.core.net.StepUp) -> Unit): Triple<String, String, mockwebserver3.RecordedRequest> {
        server.enqueue(json(200, response))
        var action = ""
        var target = ""
        call { a, t -> action = a; target = t; "su-$t" }
        val req = server.takeRequest()
        assertEquals("su-$target", req.headers["X-Step-Up"])
        assertNotNull(req.headers["Idempotency-Key"])
        return Triple(action, target, req)
    }

    @Test
    fun releasingAHoldIsSignedOnTheHold() = runTest {
        val (a, t, req) = signed("""{"ref":"H-0002","company":"PC","action":{"kind":"deploy","summary_fa":"x"},"held_at":"2026-10-17T10:00:00Z","state":"released"}""") { api.releaseHold("H-0002", it) }
        assertEquals("oversight.release" to "H-0002", a to t)
        assertEquals("/api/v1/oversight/holds/H-0002/release", req.url.encodedPath)
        server.enqueue(json(200, """{"ref":"H-0002","company":"PC","action":{"kind":"deploy","summary_fa":"x"},"held_at":"2026-10-17T10:00:00Z","state":"cancelled"}"""))
        api.cancelHold("H-0002")
        assertNull(server.takeRequest().headers["X-Step-Up"])
    }

    @Test
    fun standingOrderSealIsBoundToItsRef() = runTest {
        val (a, t, req) = signed("""{"ref":"SO-005","text_md":"x","status":"sealed","created_at":"2026-10-17T10:00:00Z"}""") { api.sealStandingOrder("SO-005", it) }
        assertEquals("oversight.order" to "SO-005", a to t)
        assertEquals("/api/v1/oversight/orders/SO-005/seal", req.url.encodedPath)
    }

    @Test
    fun skillActivationIsBoundToTheVersionTested() = runTest {
        val s = Skill(ref = "SK-005", nameFa = "چک‌لیست انتشار", status = "approved", version = 3)
        val (a, t, req) = signed("""{"ref":"SK-005","name_fa":"x","status":"active","version":3}""") { api.activateSkill(s, it) }
        assertEquals("skill.activate" to "SK-005@3", a to t)
        assertEquals("""{"version":3}""", req.body!!.utf8())
    }

    @Test
    fun serverPlanSealIsBoundToTheServerDigest() = runTest {
        val p = ServerPlan(ref = "PV-0002", name = "signal-bot-1", type = "cpx21", location = "fsn1", image = "ubuntu-24.04", workUser = "signalbot", monthlyEur = "9.20", digest = "4e0d7a91c3", state = "proposed")
        val (a, t, req) = signed("""{"ref":"PV-0002","name":"signal-bot-1","type":"cpx21","location":"fsn1","image":"ubuntu-24.04","work_user":"signalbot","monthly_eur":"9.20","digest":"4e0d7a91c3","state":"running","run":"r2"}""") { api.sealPlan(p, it) }
        assertEquals("provision.seal" to "4e0d7a91c3", a to t)
        assertEquals("/api/v1/provisioning/plans/PV-0002/seal", req.url.encodedPath)
    }

    @Test
    fun teachingMcpAndFoundingSealsCarryTheirTargets() = runTest {
        val teach = signed("""{"ref":"TE-0002","target":{"kind":"role","ref":"overseer"},"text_md":"x","status":"approved","created_at":"2026-10-17T10:00:00Z"}""") { api.approveTeaching("TE-0002", it) }
        assertEquals("academy.approve" to "TE-0002", teach.first to teach.second)
        val mcp = signed("""{"key":"gsc","title_fa":"x","status":"enabled"}""") { api.enableMcp("gsc", it) }
        assertEquals("mcp.enable" to "gsc", mcp.first to mcp.second)
        val found = signed("""{"ref":"C-0001","name_fa":"x","source":{"kind":"idea"},"state":"active","created_at":"2026-10-17T10:00:00Z","updated_at":"2026-10-17T10:00:00Z"}""") { api.activateFounding("C-0001", it) }
        assertEquals("founding.activate" to "C-0001", found.first to found.second)
    }

    @Test
    fun newSkillForAllCompaniesSaysAll() = runTest {
        server.enqueue(json(201, """{"ref":"SK-006","name_fa":"x","status":"in_review","scope":{"roles":["all"],"companies":"all"}}"""))
        val s = api.newSkill("روش", "گام یک", listOf("all"), null, listOf("f1"))
        val body = server.takeRequest().body!!.utf8()
        assertTrue(body.contains("\"companies\":\"all\""))
        assertTrue(body.contains("\"file_ids\":[\"f1\"]"))
        assertNull(com.coinepro.hq.core.net.companiesOf(s.scope.companies))
    }

    @Test
    fun foundingStartsFromASource() = runTest {
        server.enqueue(json(201, """{"ref":"C-0003","name_fa":"new-bot","source":{"kind":"repo","repo":"o/new-bot"},"state":"auditing","created_at":"2026-10-17T10:00:00Z","updated_at":"2026-10-17T10:00:00Z"}"""))
        val f = api.startFounding("repo", "o/new-bot", "")
        assertEquals("""{"source":{"kind":"repo","repo":"o/new-bot","brief_md":""}}""", server.takeRequest().body!!.utf8())
        assertEquals("auditing", f.state)
    }

    // ------------------------------------------------------------ ⟨1.4.2⟩ --
    @Test
    fun openingHiringIsSignedOnTheHolding() = runTest {
        val (action, target, req) = signed("""{"state":"open","mode":"proposals","changed_at":"2026-10-17T10:00:00Z","withdrawn":["D-000001"]}""") { api.startHiring("proposals", it) }
        assertEquals("hiring.start" to "holding", action to target)
        assertEquals("/api/v1/owner/hiring/start", req.url.encodedPath)
        assertEquals("""{"mode":"proposals"}""", req.body!!.utf8())
    }

    @Test
    fun closingHiringNeedsNoPasskey() = runTest {
        server.enqueue(json(200, """{"state":"closed","mode":null,"withdrawn":["D-000001","D-000002"]}"""))
        val h = api.closeHiring()
        val req = server.takeRequest()
        assertNull(req.headers["X-Step-Up"])
        assertEquals(listOf("D-000001", "D-000002"), h.withdrawn)
    }

    @Test
    fun directHireIsBoundToTheExactBody() = runTest {
        server.enqueue(json(201, """{"employee":{"code":"TY-TECH-01","company":"TY","department":"TECH","title_fa":"x","status":"active"},"decision":{"ref":"D-000031","status":"approved","resolution":"M-0008"}}"""))
        var target = ""
        val out = api.hireDirect(HireIn("TY", "TECH", "sre", "مهندس پایداری", model = "claude-haiku-5-5", effort = "high")) { target = it; "su" }
        val req = server.takeRequest()
        val body = req.body!!.utf8()
        assertEquals("/api/v1/org/hires", req.url.encodedPath)
        assertEquals(Api.sha256(body), target)
        assertEquals("su", req.headers["X-Step-Up"])
        // Nulls are left out, so the body the passkey signed is the body the server hashes.
        assertTrue(!body.contains("reason") && !body.contains("title_en"))
        assertEquals("TY-TECH-01" to "D-000031", out.employee.code to out.decision.ref)
    }

    @Test
    fun onlyFittingEmployeeChartersAreHireable() {
        val roles = listOf(
            RoleInfo("sre", "SRE", kind = "employee", scope = "company", department = "TECH", model = "m", effort = "high"),
            RoleInfo("cto", "CTO", kind = "manager", scope = "company", department = "TECH", model = "m", effort = "high"),
            RoleInfo("ai_safety", "AI", kind = "employee", scope = "holding", department = "OVS", model = "m", effort = "high"),
            RoleInfo("writer", "W", kind = "employee", scope = "company", department = null, model = "m", effort = "high"),
        )
        assertEquals(listOf("sre", "writer"), hireableRoles(roles, "company", "TECH").map { it.role })
        assertEquals(listOf("writer"), hireableRoles(roles, "company", "GROWTH").map { it.role })
        assertEquals(listOf("ai_safety"), hireableRoles(roles, "holding", "OVS").map { it.role })
    }

    // ------------------------------------------------------------ ⟨1.4.3⟩ --
    @Test
    fun envelopesAreCompanyMonthBudgetsSealedOnTheBody() = runTest {
        server.enqueue(json(200, "[]"))
        var target = ""
        api.setEnvelopes(linkedMapOf("TY" to 6_000_000L)) { target = it; "su" }
        val req = server.takeRequest()
        val body = req.body!!.utf8()
        assertEquals("PUT", req.method)
        assertEquals("/api/v1/budgets", req.url.encodedPath)
        assertEquals(Api.sha256(body), target)
        assertEquals("""{"budgets":[{"company":"TY","scope_type":"company","scope_ref":"TY","period":"month","token_limit":6000000}]}""", body)
    }

    @Test
    fun storiesSeenWelcomeAndDismissal() = runTest {
        server.enqueue(json(200, """[{"company":"FX","unseen":1,"latest_at":"2026-10-17T10:00:00Z","items":[{"ref":"ST-000104","company":"FX","kind":"hire","author":{"code":"system","kind":"system"},"title_fa":"t","figures":[{"label_fa":"مدل","value":"Haiku 5.5"}],"links":{"employee":"FX-QUANT-02"},"created_at":"2026-10-17T10:00:00Z"}]}]"""))
        val rings = api.stories()
        assertEquals("FX-QUANT-02", rings.single().items.single().links.employee)
        server.takeRequest()
        server.enqueue(json(200, """{"updated":1}"""))
        api.storiesSeen(listOf("ST-000104"))
        assertEquals("""{"refs":["ST-000104"]}""", server.takeRequest().body!!.utf8())
        val (action, target, req) = signed("""{"employee":{"code":"FX-QUANT-02"}}""") { api.dismissEmployee("FX-QUANT-02", "مالک: از استوری", it) }
        assertEquals("employee.dismiss" to "FX-QUANT-02", action to target)
        assertEquals("/api/v1/employees/FX-QUANT-02/dismiss", req.url.encodedPath)
    }

    @Test
    fun envelopeInputReadsMillionsInEitherDigits() {
        assertEquals(5_000_000L, com.coinepro.hq.ui.settings.parseMillions("5"))
        assertEquals(2_500_000L, com.coinepro.hq.ui.settings.parseMillions("۲٫۵"))
        assertEquals(null, com.coinepro.hq.ui.settings.parseMillions("0"))
        assertEquals(null, com.coinepro.hq.ui.settings.parseMillions("x"))
    }

    // ------------------------------------------------------------ ⟨1.4.4⟩ --
    @Test
    fun workEditCarriesIfMatchAndOnlyWhatChanged() = runTest {
        server.enqueue(json(200, """{"id":"w0","ref":"W-000104","company":"FX","title":"t2","status":"in_progress","version":4}"""))
        val w = com.coinepro.hq.core.net.Work(id = "w0", ref = "W-000104", company = "FX", title = "t", status = "in_progress", version = 3)
        val out = api.patchWork(w, com.coinepro.hq.core.net.WorkPatch(title = "t2"))
        val req = server.takeRequest()
        assertEquals("PATCH", req.method)
        assertEquals("/api/v1/work/w0", req.url.encodedPath)
        assertEquals("\"3\"", req.headers["If-Match"])
        assertEquals("""{"title":"t2"}""", req.body!!.utf8())
        assertEquals(4, out.version)
    }

    @Test
    fun completingWorkSendsEvidenceAndCancellingAReason() = runTest {
        server.enqueue(json(200, """{"id":"w0","ref":"W-000104","company":"FX","title":"t","status":"done"}"""))
        api.completeWork("w0", listOf(com.coinepro.hq.core.net.EvidenceIn("deliverable", "O-000031")))
        val a = server.takeRequest()
        assertEquals("/api/v1/work/w0/complete", a.url.encodedPath)
        assertEquals("""{"evidence":[{"kind":"deliverable","ref":"O-000031"}]}""", a.body!!.utf8())
        server.enqueue(json(200, """{"id":"w0","ref":"W-000104","company":"FX","title":"t","status":"cancelled"}"""))
        api.cancelWork("w0", "دیگر لازم نیست")
        assertEquals("""{"reason":"دیگر لازم نیست"}""", server.takeRequest().body!!.utf8())
    }

    @Test
    fun dismissalIsSignedOnTheCodeAndCanTransferWork() = runTest {
        val (a, t, req) = signed("""{"work_returned":2,"transfer_work":"W-000210"}""") { api.dismiss("TY-GROWTH-01", "کم‌کاری", "TY-GROWTH-MGR", it) }
        assertEquals("employee.dismiss" to "TY-GROWTH-01", a to t)
        assertEquals("""{"reason":"کم‌کاری","transfer_to":"TY-GROWTH-MGR"}""", req.body!!.utf8())
    }

    @Test
    fun notificationSettingsReplaceTheMatrixWithIfMatch() = runTest {
        server.enqueue(json(200, """{"matrix":{"*":{"report":{"push":false}}},"version":4}"""))
        val s = com.coinepro.hq.core.net.NotificationSettings(mapOf("*" to mapOf("report" to com.coinepro.hq.core.net.LevelSettings(push = false))), version = 3)
        assertEquals(4, api.saveNotificationSettings(s).version)
        val req = server.takeRequest()
        assertEquals("PUT", req.method)
        assertEquals("\"3\"", req.headers["If-Match"])
        assertEquals("""{"matrix":{"*":{"report":{"push":false}}}}""", req.body!!.utf8())
    }

    @Test
    fun budgetsAndSitesAreSealedOnTheExactBody() = runTest {
        server.enqueue(json(200, "[]"))
        var target = ""
        api.putBudgets(listOf(com.coinepro.hq.core.net.BudgetRowIn("HQ", "holding", "HQ", "month", 30_000_000L, "600.00"))) { target = it; "su" }
        val b = server.takeRequest()
        assertEquals("PUT", b.method)
        assertEquals(Api.sha256(b.body!!.utf8()), target)
        assertEquals("su", b.headers["X-Step-Up"])
        assertEquals("""{"budgets":[{"company":"HQ","scope_type":"holding","scope_ref":"HQ","period":"month","token_limit":30000000,"usd_limit":"600.00"}]}""", b.body!!.utf8())
        server.enqueue(json(200, "[]"))
        api.putSites("TY", listOf(com.coinepro.hq.core.net.SiteIn("https://tradeyar.trade-future.ir"))) { target = it; "su2" }
        val s = server.takeRequest()
        assertEquals("/api/v1/ops/sites", s.url.encodedPath)
        assertEquals(Api.sha256(s.body!!.utf8()), target)
        assertEquals("su2", s.headers["X-Step-Up"])
    }

    @Test
    fun connectionEditIsSignedOnItsIdWithIfMatchAndTheKeyIsWriteOnly() = runTest {
        server.enqueue(json(200, """{"id":"c2","key":"anthropic-api","display_name":"x","kind":"api_key","status":"enabled","version":3}"""))
        var signedOn = "" to ""
        val c = com.coinepro.hq.core.net.Connection(id = "c2", key = "anthropic-api", displayName = "x", kind = "api_key", status = "disabled", version = 2)
        api.patchConnection(c, com.coinepro.hq.core.net.ConnectionPatch(status = "enabled")) { a, t -> signedOn = a to t; "su" }
        val p = server.takeRequest()
        assertEquals("connection.update" to "c2", signedOn)
        assertEquals("PATCH", p.method)
        assertEquals("\"2\"", p.headers["If-Match"])
        assertEquals("""{"status":"enabled"}""", p.body!!.utf8())
        val (a, t, req) = signed("""{"connection":"anthropic-api","stored":true}""") { api.connectionSecret("c2", "sk-test", it) }
        assertEquals("connection.secret" to "c2", a to t)
        assertEquals("/api/v1/connections/c2/secret", req.url.encodedPath)
    }

    @Test
    fun newCompanyIsSignedOnItsCodeAndFreezesTakeAnUntil() = runTest {
        val (a, t, req) = signed("""{"id":"co-NW","code":"NW","kind":"company","status":"active","created_at":"2026-10-18T10:00:00Z"}""") { api.createCompany(com.coinepro.hq.core.net.CompanyIn("NW", "تازه", "New"), it) }
        assertEquals("company.create" to "NW", a to t)
        assertEquals("""{"code":"NW","name_fa":"تازه","name_en":"New"}""", req.body!!.utf8())
        server.enqueue(json(200, """{"company":"FX","active":false,"until":"2026-10-18T09:00:00Z"}"""))
        assertEquals(false, api.deployFreeze("FX", "2026-10-18T09:00:00Z", "برداشته شد").active)
        assertEquals("/api/v1/control/deploy-freeze", server.takeRequest().url.encodedPath)
    }
}
