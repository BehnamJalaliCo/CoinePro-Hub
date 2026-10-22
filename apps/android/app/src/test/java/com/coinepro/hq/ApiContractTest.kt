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
import kotlinx.serialization.json.put
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

    // ------------------------------------------------------------ ⟨1.5⟩ --
    @Test
    fun revenueAccountAndIntakeSourceAreSealedOnTheExactBody() = runTest {
        val acc = signed("""{"id":"ra-ty","company":"TY","exchange":"lbank","adapter":"lbank-affiliate-v2","service_account":"lbank-affiliate-ty","title_fa":"x","status":"not_configured","version":1}""") {
            api.saveRevenueAccount(com.coinepro.hq.core.net.RevenueAccountIn("TY", "lbank", "lbank-affiliate-v2", "lbank-affiliate-ty", "افیلیت LBank تریدیار"), it)
        }
        val body = acc.third.body!!.utf8()
        assertEquals("revenue.account" to Api.sha256(body), acc.first to acc.second)
        assertEquals("/api/v1/revenue/accounts", acc.third.url.encodedPath)
        assertEquals("""{"company":"TY","exchange":"lbank","adapter":"lbank-affiliate-v2","service_account":"lbank-affiliate-ty","title_fa":"افیلیت LBank تریدیار"}""", body)
        val src = signed("""{"company":"TY","kind":"product","configured":false,"last_event_at":null,"events_24h":0,"rejected_24h":0}""") {
            api.registerIntake(com.coinepro.hq.core.net.IntakeSourceIn("TY", "product", listOf("203.0.113.10/32"), listOf("signup", "referral_failed")), it)
        }
        val text = src.third.body!!.utf8()
        assertEquals("intake.source" to Api.sha256(text), src.first to src.second)
        assertEquals("""{"company":"TY","kind":"product","allowed_ips":["203.0.113.10/32"],"kinds":["signup","referral_failed"]}""", text)
    }

    @Test
    fun pullReplyAndTeachCarryTheCallersIdempotencyKey() = runTest {
        server.enqueue(json(202, """{"account":"ra-ty","state":"queued"}"""))
        api.pullRevenue("ra-ty", "k-pull", from = "2026-10-01", to = "2026-10-16")
        val pull = server.takeRequest()
        assertEquals("/api/v1/revenue/accounts/ra-ty/pull", pull.url.encodedPath)
        assertEquals("from=2026-10-01&to=2026-10-16", pull.url.encodedQuery)
        assertEquals("k-pull", pull.headers["Idempotency-Key"])
        assertNull(pull.headers["X-Step-Up"])
        val msg = """{"id":"m9","conversation":"SC-000411","at":"2026-10-17T10:00:00Z","direction":"out","author":"owner","body":"x","status":"sent","checks":{"guard":"pass","grounded":null}}"""
        server.enqueue(json(201, msg))
        assertEquals("sent", api.reply("SC-000411", "متن تو", "k-reply").status)
        val reply = server.takeRequest()
        assertEquals("/api/v1/support/conversations/SC-000411/reply", reply.url.encodedPath)
        assertEquals("k-reply" to """{"body":"متن تو"}""", reply.headers["Idempotency-Key"] to reply.body!!.utf8())
        server.enqueue(json(201, """{"message":null,"article":{"ref":"KB-0013","company":"TY","kind":"faq","question_fa":"q","status":"proposed"}}"""))
        val out = api.teach("SC-000411", "SC-000411-m2", "جواب درست", true, "k-teach")
        val teach = server.takeRequest()
        assertEquals("k-teach", teach.headers["Idempotency-Key"])
        assertEquals("""{"message_id":"SC-000411-m2","answer_md":"جواب درست","generalise":true}""", teach.body!!.utf8())
        assertTrue(out.message == null && out.article.ref == "KB-0013")
        server.enqueue(json(201, """{"message":$msg,"article":{"ref":"KB-0014","company":"TY","kind":"faq","question_fa":"q","status":"proposed"}}"""))
        api.teach("SC-000405", null, "جواب", false, "k-2")
        assertEquals("""{"answer_md":"جواب","generalise":false}""", server.takeRequest().body!!.utf8())
    }

    @Test
    fun theGuardsRefusalAndTheStableCodesReadInPersian() = runTest {
        server.enqueue(json(422, """{"type":"about:blank","title":"send_blocked","status":422,"code":"send_blocked","message_fa":"رد شد.","blocked_reasons":["unknown_link","profit_promise"]}"""))
        try {
            api.reply("SC-000411", "https://lbank.com/ref/X سود تضمینی", "k")
            fail("expected ApiException")
        } catch (e: ApiException) {
            assertEquals(listOf("unknown_link", "profit_promise"), e.blockedReasons)
            assertEquals("نگهبان خروجی این پیام را رد کرد و فرستاده نشد.", com.coinepro.hq.core.net.faError(e))
        }
        server.enqueue(MockResponse.Builder().code(429).addHeader("Content-Type", "application/json").addHeader("Retry-After", "30")
            .body("""{"code":"send_limit","message_fa":"سقف.","status":429}""").build())
        try {
            api.reply("SC-000411", "x", "k2")
            fail("expected ApiException")
        } catch (e: ApiException) {
            assertEquals(30, e.retryAfter)
            assertEquals("سقف ارسال پر شده است؛ 30 ثانیه‌ی دیگر دوباره امتحان کن.", com.coinepro.hq.core.net.faError(e))
        }
        for (code in listOf("shadow_not_passed", "template_not_sealed", "channel_not_live", "opted_out")) {
            val e = ApiException(409, code, "server sentence")
            assertTrue(code, com.coinepro.hq.core.net.faError(e) != "server sentence")
        }
        assertEquals("server sentence", com.coinepro.hq.core.net.faError(ApiException(409, "version_conflict", "server sentence")))
    }

    @Test
    fun channelWideningIsSignedNarrowingAndPausingAreNot() = runTest {
        val ch = com.coinepro.hq.core.net.SupportChannel("TY", "telegram_bot", "live", liveSince = "2026-10-05T10:00:00Z", autoSend = "kb_verbatim", version = 3)
        val back = """{"company":"TY","kind":"telegram_bot","state":"live","auto_send":"kb_grounded","version":4}"""
        var signedOn: Pair<String, String>? = null
        server.enqueue(json(200, back))
        api.patchChannel(ch, autoSend = "kb_grounded") { a, t -> signedOn = a to t; "su" }
        val widen = server.takeRequest()
        assertEquals("support.channel" to "TY/telegram_bot@kb_grounded", signedOn)
        assertEquals("PATCH", widen.method)
        assertEquals("\"3\"" to "su", widen.headers["If-Match"] to widen.headers["X-Step-Up"])
        assertEquals("""{"auto_send":"kb_grounded"}""", widen.body!!.utf8())
        // Narrowing needs no passkey.
        signedOn = null
        server.enqueue(json(200, back))
        api.patchChannel(ch.copy(autoSend = "kb_grounded", version = 4), autoSend = "off") { a, t -> signedOn = a to t; "su" }
        val narrow = server.takeRequest()
        assertNull(signedOn)
        assertNull(narrow.headers["X-Step-Up"])
        assertEquals("\"4\"", narrow.headers["If-Match"])
        // A paused channel that already went live comes back with a passkey, on its current auto_send.
        server.enqueue(json(200, back))
        api.patchChannel(ch.copy(state = "paused"), live = true) { a, t -> signedOn = a to t; "su" }
        assertEquals("""{"state":"live"}""", server.takeRequest().body!!.utf8())
        assertEquals("support.channel" to "TY/telegram_bot@kb_verbatim", signedOn)
        // Stopping is always safe.
        server.enqueue(json(200, back))
        api.pauseChannel(ch)
        val pause = server.takeRequest()
        assertEquals("/api/v1/support/channels/TY/telegram_bot/pause", pause.url.encodedPath)
        assertNull(pause.headers["X-Step-Up"])
    }

    @Test
    fun knowledgeTemplatesAndRulesAreSealedOnTheirVersion() = runTest {
        val a = com.coinepro.hq.core.net.KbArticle(ref = "KB-0005", company = "TY", version = 2, kind = "faq", questionFa = "q", status = "proposed")
        val kb = signed("""{"ref":"KB-0005","company":"TY","version":2,"kind":"faq","question_fa":"q","status":"approved"}""") { api.approveKb(a, it) }
        assertEquals("support.kb" to "KB-0005@2", kb.first to kb.second)
        assertEquals("/api/v1/support/kb/KB-0005/approve", kb.third.url.encodedPath)
        val t = com.coinepro.hq.core.net.Template(ref = "TM-0008", company = "TY", version = 1, purpose = "welcome", bodyFa = "x", status = "proposed", sha256 = "7351fee2")
        val tm = signed("""{"ref":"TM-0008","company":"TY","version":1,"purpose":"welcome","status":"sealed"}""") { api.sealTemplate(t, it) }
        assertEquals("growth.template" to "TM-0008@1:7351fee2", tm.first to tm.second)
        val limits = com.coinepro.hq.core.net.RuleLimits(7, 60, listOf("22:00", "09:00"), 2)
        val r = com.coinepro.hq.core.net.LifecycleRule(ref = "LR-0002", company = "TY", version = 2, kind = "rescue", template = "TM-0003@2", channel = "telegram_bot", limits = limits, status = "paused")
        val ruleJson = """{"ref":"LR-0002","company":"TY","version":2,"kind":"rescue","template":"TM-0003@2","channel":"telegram_bot","limits":{"per_customer_days":7,"daily_cap":60,"quiet_hours":["22:00","09:00"],"max_follow_ups":2},"status":"active"}"""
        val seal = signed(ruleJson) { api.sealRule(r, it) }
        assertEquals("growth.rule" to "LR-0002@2", seal.first to seal.second)
        val resume = signed(ruleJson) { api.resumeRule(r, it) }
        assertEquals("growth.rule" to "LR-0002@2", resume.first to resume.second)
        assertEquals("/api/v1/growth/rules/LR-0002/resume", resume.third.url.encodedPath)
        server.enqueue(json(200, ruleJson))
        api.pauseRule("LR-0002")
        assertNull(server.takeRequest().headers["X-Step-Up"])
        // A new rule sends every limit, including those at their usual values.
        server.enqueue(json(201, ruleJson))
        api.createRule(com.coinepro.hq.core.net.LifecycleRuleIn("TY", "csat", com.coinepro.hq.core.net.RuleTrigger(event = "conversation_closed", afterHours = 1), "TM-0005@1", "telegram_bot", com.coinepro.hq.core.net.RuleLimits(30, 100, listOf("22:00", "09:00"), 0)))
        assertEquals(
            """{"company":"TY","kind":"csat","trigger":{"event":"conversation_closed","after_hours":1},"template":"TM-0005@1","channel":"telegram_bot","limits":{"per_customer_days":30,"daily_cap":100,"quiet_hours":["22:00","09:00"],"max_follow_ups":0}}""",
            server.takeRequest().body!!.utf8(),
        )
    }

    @Test
    fun feedbackPatchUsesIfMatchAndCanDetachWork() = runTest {
        val x = com.coinepro.hq.core.net.FeedbackItem(ref = "FB-000041", company = "TY", kind = "confusion", titleFa = "t", firstSeen = "2026-10-01T00:00:00Z", lastSeen = "2026-10-17T00:00:00Z", state = "triaged", version = 2)
        val back = """{"ref":"FB-000041","company":"TY","kind":"confusion","title_fa":"t","first_seen":"2026-10-01T00:00:00Z","last_seen":"2026-10-17T00:00:00Z","state":"in_backlog","work_ref":"W-000104","version":3}"""
        server.enqueue(json(200, back))
        assertEquals(3, api.patchFeedback(x, state = "in_backlog", workRef = "W-000104", setWork = true).version)
        val link = server.takeRequest()
        assertEquals("PATCH" to "\"2\"", link.method to link.headers["If-Match"])
        assertEquals("""{"state":"in_backlog","work_ref":"W-000104"}""", link.body!!.utf8())
        server.enqueue(json(200, back))
        api.patchFeedback(x, setWork = true)
        assertEquals("""{"work_ref":null}""", server.takeRequest().body!!.utf8())
    }

    @Test
    fun section19ListsAreReadBareOrPaged() = runTest {
        val ch = """{"company":"TY","kind":"telegram_bot","state":"live","auto_send":"kb_verbatim","version":1}"""
        server.enqueue(json(200, "[$ch]"))
        server.enqueue(json(200, """{"items":[$ch],"next_cursor":null}"""))
        assertEquals(api.supportChannels("TY"), api.supportChannels("TY"))
        assertEquals("company=TY", server.takeRequest().url.encodedQuery)
        server.takeRequest()
        server.enqueue(json(200, """{"items":[],"next_cursor":"c2"}"""))
        assertEquals("c2", api.conversations(company = "TY", state = "waiting_owner", q = "  ").nextCursor)
        assertEquals("company=TY&state=waiting_owner&limit=30", server.takeRequest().url.encodedQuery)
    }

    // ------------------------------------------------------------ ⟨1.5⟩ §20 --
    private val charterJson = """{"scope":"FX","version":1,"status":"proposed","body_md":"# x","red_lines":[],"body_sha256":"9f2c","created_at":"2026-10-17T00:00:00Z"}"""

    @Test
    fun charterIsSealedOnTheHashTheServerSent() = runTest {
        val c = Api.json.decodeFromString(com.coinepro.hq.core.net.Charter.serializer(), charterJson)
        val (a, t, req) = signed(charterJson.replace("proposed", "sealed")) { api.sealCharter(c, it) }
        // §20.12: the target is body_sha256 as the server sent it; the client never recomputes it.
        assertEquals("charter.seal" to "9f2c", a to t)
        assertEquals("/api/v1/charter/FX/versions/1/seal", req.url.encodedPath)
        // A new version: the red lines go whole, a sampled one with an explicit null for its patterns.
        server.enqueue(json(201, charterJson.replace("\"version\":1", "\"version\":2")))
        api.proposeCharter("FX", com.coinepro.hq.core.net.CharterIn("# y", listOf(com.coinepro.hq.core.net.RedLine("fx_stop_loss", "حد ضرر", "sample", null))))
        val put = server.takeRequest()
        assertEquals("PUT" to "/api/v1/charter/FX", put.method to put.url.encodedPath)
        assertEquals("""{"body_md":"# y","red_lines":[{"key":"fx_stop_loss","text_fa":"حد ضرر","check":"sample","patterns":null}]}""", put.body!!.utf8())
    }

    @Test
    fun authorityAndMeetingSettingsAreSealedOnTheExactBody() = runTest {
        server.enqueue(json(200, "[]"))
        var signedOn: Pair<String, String>? = null
        api.putAuthority(listOf(
            com.coinepro.hq.core.net.AuthorityChange("hire.count_day", null, kotlinx.serialization.json.buildJsonObject { put("count_day", 7) }, 2),
            com.coinepro.hq.core.net.AuthorityChange("batch.max_usd", "owner", kotlinx.serialization.json.buildJsonObject { put("usd", 1.5) }, 1),
        )) { a, t -> signedOn = a to t; "su" }
        val put = server.takeRequest()
        val body = put.body!!.utf8()
        assertEquals("""{"rules":[{"key":"hire.count_day","limit":{"count_day":7},"version":2},{"key":"batch.max_usd","actor":"owner","limit":{"usd":1.5},"version":1}]}""", body)
        assertEquals("authority.update" to Api.sha256(body), signedOn)
        assertEquals("PUT" to "su", put.method to put.headers["X-Step-Up"])
        assertNull(put.headers["If-Match"])
        // The meeting types go whole: a war room's missing cap is an explicit null, each row with its own version.
        val war = com.coinepro.hq.core.net.MeetingType("war_room", "اتاق جنگ", null, com.coinepro.hq.core.net.MeetingMembers(listOf("ceo"), "concerned"), 3, 8, null, 6000, "live", true, 1)
        server.enqueue(json(200, """{"types":[]}"""))
        api.saveMeetingSettings(listOf(war)) { a, t -> signedOn = a to t; "su2" }
        val settings = server.takeRequest()
        val text = settings.body!!.utf8()
        assertEquals("""{"types":[{"key":"war_room","title_fa":"اتاق جنگ","schedule":null,"members":{"roles":["ceo"],"companies":"concerned"},"max_rounds":3,"max_speakers":8,"budget_tokens":null,"turn_cap_tokens":6000,"owner_presence":"live","enabled":true,"version":1}]}""", text)
        assertEquals("meetings.settings" to Api.sha256(text), signedOn)
        assertEquals("PUT" to "/api/v1/meetings/settings", settings.method to settings.url.encodedPath)
    }

    @Test
    fun batchIsSealedOnItsSortedSetAndRefusedWhole() = runTest {
        var signedOn: Pair<String, String>? = null
        server.enqueue(json(200, """{"batch":"B-0001","items":[{"ref":"D-000034","resolution":"M-0019"},{"ref":"D-000035","resolution":"M-0020"}]}"""))
        val out = api.batchApprove(listOf(com.coinepro.hq.core.net.BatchItem("D-000035", 1), com.coinepro.hq.core.net.BatchItem("D-000034", 2)), "k-batch") { a, t -> signedOn = a to t; "su" }
        val req = server.takeRequest()
        val set = """[{"ref":"D-000034","version":2},{"ref":"D-000035","version":1}]"""
        assertEquals("decision.batch" to Api.sha256(set), signedOn)
        assertEquals("/api/v1/decisions/batch/approve", req.url.encodedPath)
        assertEquals("""{"items":$set}""", req.body!!.utf8())
        assertEquals("k-batch" to "su", req.headers["Idempotency-Key"] to req.headers["X-Step-Up"])
        assertEquals("B-0001", out.batch)
        assertEquals(listOf("M-0019", "M-0020"), out.items.map { it.resolution })
        // All or nothing: each refused card and why, in Persian.
        server.enqueue(json(422, """{"type":"about:blank","title":"batch_not_eligible","status":422,"code":"batch_not_eligible","message_fa":"رد شد.","fields":{"items":[{"ref":"D-000035","reason":"changed"}]}}"""))
        try {
            api.batchApprove(listOf(com.coinepro.hq.core.net.BatchItem("D-000035", 1)), "k2") { _, _ -> "su" }
            fail("expected ApiException")
        } catch (e: ApiException) {
            assertEquals(listOf("D-000035" to "changed"), e.batchReasons)
            assertEquals("کارت بعد از انتخاب عوض شد", com.coinepro.hq.core.net.BATCH_REASON_FA[e.batchReasons.single().second])
            assertTrue(com.coinepro.hq.core.net.govError(e).contains("هیچ کارتی مُهر نشد"))
        }
    }

    @Test
    fun meetingsCarryIfMatchAndTheCallersKey() = runTest {
        val mt = """{"ref":"MT-0013","type":"company","company":"TY","title_fa":"t","starts_at":"2026-10-18T05:00:00Z","state":"prep","version":2}"""
        val m = Api.json.decodeFromString(com.coinepro.hq.core.net.Meeting.serializer(), mt)
        server.enqueue(json(200, mt))
        api.patchMeeting(m, items = listOf(com.coinepro.hq.core.net.ItemOrder("mi-13-2", 1, false), com.coinepro.hq.core.net.ItemOrder("mi-13-1", 2, true)), budgetCap = 30_000)
        val patch = server.takeRequest()
        assertEquals("PATCH" to "\"2\"", patch.method to patch.headers["If-Match"])
        assertEquals("""{"items":[{"id":"mi-13-2","n":1,"skip":false},{"id":"mi-13-1","n":2,"skip":true}],"budget_cap":30000}""", patch.body!!.utf8())
        server.enqueue(json(201, """{"id":"t1","meeting":"MT-0012","speaker":{"code":"owner","kind":"owner"},"kind":"owner","at":"2026-10-17T08:30:00Z"}"""))
        assertEquals("owner", api.speak("MT-0012", "ساعت کم‌بار", null, "k-speak").kind)
        val speak = server.takeRequest()
        assertEquals("k-speak" to """{"text":"ساعت کم‌بار"}""", speak.headers["Idempotency-Key"] to speak.body!!.utf8())
        server.enqueue(json(201, mt))
        api.createMeeting("company", "TY", "2026-10-20T10:30:00Z", listOf(com.coinepro.hq.core.net.MeetingItemIn("گزارش", 10)), "k-new")
        val create = server.takeRequest()
        assertEquals("k-new" to """{"type":"company","company":"TY","starts_at":"2026-10-20T10:30:00Z","items":[{"title_fa":"گزارش","time_box_min":10}]}""", create.headers["Idempotency-Key"] to create.body!!.utf8())
        server.enqueue(json(200, mt))
        api.meetingControl("MT-0012", "raise_budget", 20_000)
        assertEquals("""{"action":"raise_budget","tokens":20000}""", server.takeRequest().body!!.utf8())
        server.enqueue(json(409, """{"code":"meeting_not_live","message_fa":"server","status":409}"""))
        try {
            api.speak("MT-0013", "x", null, "k3")
            fail("expected ApiException")
        } catch (e: ApiException) {
            assertEquals("جلسه الان زنده نیست؛ ورود تو فقط در جلسه‌ی زنده ممکن است.", com.coinepro.hq.core.net.govError(e))
        }
    }

    @Test
    fun kpisRisksAndTheCalendarUseIfMatch() = runTest {
        val set = com.coinepro.hq.core.net.KpiSet("TY", 3, emptyList())
        server.enqueue(json(200, """{"company":"TY","version":4,"kpis":[]}"""))
        assertEquals(4, api.putKpis(set, listOf(com.coinepro.hq.core.net.KpiPatch("min_balance_rate", null, true, "active", 30))).version)
        val kpis = server.takeRequest()
        assertEquals("PUT" to "\"3\"", kpis.method to kpis.headers["If-Match"])
        // A cleared target is sent as an explicit null.
        assertEquals("""{"kpis":[{"key":"min_balance_rate","target":null,"scorecard":true,"status":"active","freshness_hours":30}]}""", kpis.body!!.utf8())
        val risk = Api.json.decodeFromString(com.coinepro.hq.core.net.Risk.serializer(), """{"ref":"RK-0002","company":"TY","title_fa":"t","category":"money","likelihood":3,"impact":5,"status":"open","version":2}""")
        assertEquals(15, risk.score)
        server.enqueue(json(200, """{"ref":"RK-0002","company":"TY","title_fa":"t","category":"money","likelihood":2,"impact":5,"score":10,"status":"mitigating","version":3}"""))
        api.patchRisk(risk, kotlinx.serialization.json.buildJsonObject { put("likelihood", 2); put("mitigation_md", null as String?) })
        val patch = server.takeRequest()
        assertEquals("\"2\"" to """{"likelihood":2,"mitigation_md":null}""", patch.headers["If-Match"] to patch.body!!.utf8())
        val ev = """{"ref":"CE-0005","company":"TY","kind":"campaign","title_fa":"t","starts_at":"2026-10-19T08:30:00Z","ends_at":"2026-10-26T08:30:00Z","version":1}"""
        val e = Api.json.decodeFromString(com.coinepro.hq.core.net.CalendarEvent.serializer(), ev)
        server.enqueue(json(200, ev))
        api.patchEvent(e, "cancelled")
        assertEquals("\"1\"" to """{"status":"cancelled"}""", server.takeRequest().let { it.headers["If-Match"] to it.body!!.utf8() })
        // An event without a version (§20.9 lists none) goes without If-Match.
        server.enqueue(json(200, ev))
        api.patchEvent(e.copy(version = null), "done")
        assertNull(server.takeRequest().headers["If-Match"])
        // A hand-made event names its company, or null for every company.
        server.enqueue(json(201, ev))
        api.createEvent(com.coinepro.hq.core.net.CalendarIn(null, "freeze", "فریز", "2026-10-19T08:30:00Z", "2026-10-19T10:30:00Z", "medium"))
        assertEquals("""{"company":null,"kind":"freeze","title_fa":"فریز","starts_at":"2026-10-19T08:30:00Z","ends_at":"2026-10-19T10:30:00Z","risk":"medium"}""", server.takeRequest().body!!.utf8())
    }

    @Test
    fun section20ListsAreReadBarePagedOrWrapped() = runTest {
        val t = """{"key":"board","title_fa":"هیئت","budget_tokens":120000,"version":3}"""
        server.enqueue(json(200, """{"types":[$t]}"""))
        server.enqueue(json(200, "[$t]"))
        assertEquals(api.meetingSettings(), api.meetingSettings())
        server.takeRequest(); server.takeRequest()
        server.enqueue(json(200, """{"rules":[{"key":"a4.never","title_fa":"A4 هرگز","class":"A4","locked":true}]}"""))
        assertEquals("A4", api.authority().single().actionClass)
        server.takeRequest()
        server.enqueue(json(200, """{"items":[{"ref":"MT-0012","type":"board","company":"HQ","title_fa":"t","starts_at":"2026-10-17T08:04:00Z","state":"live","budget":{"cap":null,"estimate":0,"reserved":0,"used":6000}}],"next_cursor":null}"""))
        val ms = api.meetings(type = "war_room", company = "FX")
        assertEquals(null, ms.single().budget.cap)
        assertEquals("type=war_room&company=FX&limit=100", server.takeRequest().url.encodedQuery)
        server.enqueue(json(200, """{"items":[],"next_cursor":null}"""))
        api.outcomes(due = true, decision = "D-000004")
        assertEquals("due=true&decision=D-000004&limit=100", server.takeRequest().url.encodedQuery)
        server.enqueue(json(200, """{"scope":"TY","version":2,"against":1,"diff":"--- TY@1"}"""))
        api.charterDiff("TY", 2, 1)
        assertEquals("/api/v1/charter/TY/versions/2/diff?against=1", server.takeRequest().url.let { "${it.encodedPath}?${it.encodedQuery}" })
    }
    // ------------------------------------------------------------ ⟨1.5⟩ §21 --
    private val sub = """{"player":"gpt","connection":"chatgpt-plus","runner":"codex_cli","status":"ready","version":3,"login":{"state":"signed_in"},"models":[{"id":"gpt-5.5"}],"capabilities":{},"web":{"account":"chatgpt-web","state":"signed_in"},"seats":[],"month":{"key":"1405-07"}}"""

    @Test
    fun aNewConnectionIsSealedOnItsExactBodyWithTheCallersKey() = runTest {
        val body = com.coinepro.hq.core.net.ConnectionIn(
            key = "openrouter-main", provider = "openai_compatible", kind = "api_key", displayName = "OpenRouter", baseUrl = "https://openrouter.ai/api/v1",
            models = listOf("deepseek-v3.2"), pricing = mapOf("deepseek-v3.2" to com.coinepro.hq.core.net.Price("0.27", "1.10")), limits = com.coinepro.hq.core.net.ConnLimits(rpm = 60),
        )
        server.enqueue(json(201, """{"id":"c9","key":"openrouter-main","display_name":"OpenRouter","kind":"api_key","provider":"openai_compatible","status":"pending_secret","models":["deepseek-v3.2"],"version":1}"""))
        var signedOn: Pair<String, String>? = null
        val c = api.createConnection(body, "k-wizard") { a, t -> signedOn = a to t; "su" }
        val req = server.takeRequest()
        val text = req.body!!.utf8()
        // pricing and limits are always written; a field left out is not sent as null.
        assertEquals("""{"key":"openrouter-main","provider":"openai_compatible","kind":"api_key","display_name":"OpenRouter","base_url":"https://openrouter.ai/api/v1","models":["deepseek-v3.2"],"pricing":{"deepseek-v3.2":{"input_per_mtok":"0.27","output_per_mtok":"1.10"}},"limits":{"rpm":60}}""", text)
        assertEquals("connection.create" to Api.sha256(text), signedOn)
        assertEquals("k-wizard" to "su", req.headers["Idempotency-Key"] to req.headers["X-Step-Up"])
        assertEquals("pending_secret", c.status)
        assertTrue(com.coinepro.hq.core.net.CONNECTION_KEY.matches("openrouter-main") && !com.coinepro.hq.core.net.CONNECTION_KEY.matches("Open_Router"))
        assertTrue(com.coinepro.hq.core.net.publicHttps("https://openrouter.ai/api/v1") && !com.coinepro.hq.core.net.publicHttps("https://192.168.1.4/v1") && !com.coinepro.hq.core.net.publicHttps("http://openrouter.ai"))
    }

    @Test
    fun seatsAndSignInsAreSealedOnTheirTargets() = runTest {
        val s = Api.json.decodeFromString(com.coinepro.hq.core.net.Substitute.serializer(), sub)
        server.enqueue(json(200, sub))
        var signedOn: Pair<String, String>? = null
        api.putSeats(s, listOf(com.coinepro.hq.core.net.SeatIn("creative", "web", "gpt-5.5", true, 20), com.coinepro.hq.core.net.SeatIn("creative", "web", "gpt-5.5", true, 20, perDayVideo = 3))) { a, t -> signedOn = a to t; "su" }
        val put = server.takeRequest()
        val list = put.body!!.utf8()
        assertEquals("""[{"seat":"creative","via":"web","model":"gpt-5.5","enabled":true,"per_day":20},{"seat":"creative","via":"web","model":"gpt-5.5","enabled":true,"per_day":20,"per_day_video":3}]""", list)
        assertEquals("substitute.seats" to Api.sha256(list), signedOn)
        assertEquals(Triple("PUT", "\"3\"", "/api/v1/substitutes/gpt/seats"), Triple(put.method, put.headers["If-Match"], put.url.encodedPath))
        val (a1, t1, r1) = signed(sub) { api.webLogout("gpt", it) }
        assertEquals(Triple("substitute.web_logout", "gpt", "/api/v1/substitutes/gpt/web/logout"), Triple(a1, t1, r1.url.encodedPath))
        val (a2, t2, r2) = signed("""{"id":"lg1","connection":"chatgpt-plus","method":"device_code","verification_url":"https://auth.openai.com/codex/device","user_code":"AK7M-4TZP","expires_at":"2026-10-17T08:40:00Z","state":"waiting"}""") { api.connectionLogin("c6", it) }
        assertEquals(Triple("connection.login", "c6", "/api/v1/connections/c6/login"), Triple(a2, t2, r2.url.encodedPath))
        val (a3, t3, r3) = signed("""{"connection":"chatgpt-plus","signed_out":true}""") { api.connectionLogout("c6", it) }
        assertEquals(Triple("connection.logout", "c6", "/api/v1/connections/c6/logout"), Triple(a3, t3, r3.url.encodedPath))
        // The code of an auth-code sign-in is covered by the start's step-up.
        server.enqueue(json(200, """{"id":"lg2","connection":"gemini-pro","method":"auth_code","verification_url":"https://accounts.google.com/x","state":"done"}"""))
        api.connectionLoginCode("c7", "lg2", "4/0Ab-xyz")
        val code = server.takeRequest()
        assertEquals("/api/v1/connections/c7/login/lg2/code" to """{"code":"4/0Ab-xyz"}""", code.url.encodedPath to code.body!!.utf8())
        assertNull(code.headers["X-Step-Up"])
    }

    @Test
    fun section21WritesCarryIfMatchAndTheCallersKey() = runTest {
        // The owner's settings: each changed block whole, with the version.
        server.enqueue(json(200, """{"version":5}"""))
        api.saveOwnerSettings(4, mapOf("digital_ceo" to Api.jsonBody.encodeToJsonElement(com.coinepro.hq.core.net.DceoSettings.serializer(), com.coinepro.hq.core.net.DceoSettings(reveal = "before"))))
        val settings = server.takeRequest()
        assertEquals(Triple("PUT", "\"4\"", """{"digital_ceo":{"enabled":true,"reveal":"before","model_predictions":true,"max_model_per_day":20}}"""), Triple(settings.method, settings.headers["If-Match"], settings.body!!.utf8()))
        // An ask and a note carry the press's key; a memo names its mode.
        server.enqueue(json(202, """{"ref":"AK-0004","q":"چرا؟","state":"queued"}"""))
        assertTrue(api.askHub("چرا؟", listOf("FX"), "k-ask").live)
        val ask = server.takeRequest()
        assertEquals("k-ask" to """{"q":"چرا؟","scope":{"companies":["FX"]}}""", ask.headers["Idempotency-Key"] to ask.body!!.utf8())
        server.enqueue(json(201, """{"ref":"NT-0007","text_md":"x","status":"open","version":1}"""))
        api.createNote("x #خزانه", "text", null, com.coinepro.hq.core.net.tagsOf("خزانه"), "k-note")
        val note = server.takeRequest()
        assertEquals("k-note" to """{"text_md":"x #خزانه","source":"text","tags":["خزانه"]}""", note.headers["Idempotency-Key"] to note.body!!.utf8())
        val n = Api.json.decodeFromString(com.coinepro.hq.core.net.OwnerNote.serializer(), """{"ref":"NT-0006","text_md":"x","status":"open","version":2}""")
        server.enqueue(json(200, """{"ref":"NT-0006","text_md":"x","status":"archived","version":3}"""))
        api.patchNote(n, archive = true)
        assertEquals("\"2\"" to """{"status":"archived"}""", server.takeRequest().let { it.headers["If-Match"] to it.body!!.utf8() })
        server.enqueue(json(200, """{"ref":"NT-0006","text_md":"x","status":"promoted","version":3}"""))
        api.promoteNote("NT-0006", "work", "PC")
        assertEquals("""{"to":"work","company":"PC"}""", server.takeRequest().body!!.utf8())
        server.enqueue(json(202, """{"ref":"DM-0004","decision":"D-000040","mode":"devil","state":"writing"}"""))
        api.requestMemo("D-000040", "devil")
        assertEquals("/api/v1/decisions/D-000040/memo" to """{"mode":"devil"}""", server.takeRequest().let { it.url.encodedPath to it.body!!.utf8() })
        // A memo or a review that does not exist yet is null, not an error.
        server.enqueue(json(404, """{"code":"not_found","message_fa":"x","status":404}"""))
        assertNull(api.memo("D-000040", "standard"))
        assertEquals("mode=standard", server.takeRequest().url.encodedQuery)
        val r = Api.json.decodeFromString(com.coinepro.hq.core.net.WeeklyReview.serializer(), """{"ref":"WR-0006","week":"2026-10-17","state":"in_progress","version":7}""")
        server.enqueue(json(200, """{"ref":"WR-0006","week":"2026-10-17","state":"in_progress","version":8}"""))
        api.reviewItem(r, 3, "deferred", "هفته‌ی بعد")
        val item = server.takeRequest()
        assertEquals(Triple("/api/v1/reviews/weekly/WR-0006/items/3", "\"7\"", """{"status":"deferred","owner_note":"هفته‌ی بعد"}"""), Triple(item.url.encodedPath, item.headers["If-Match"], item.body!!.utf8()))
        val p = Api.json.decodeFromString(com.coinepro.hq.core.net.Principle.serializer(), """{"ref":"DP-001","text_fa":"x","status":"active","version":3}""")
        server.enqueue(json(200, """{"ref":"DP-001","text_fa":"x","status":"retired","version":4}"""))
        api.editPrinciple(p, "x", "retired")
        assertEquals("\"3\"" to """{"text_fa":"x","status":"retired"}""", server.takeRequest().let { it.headers["If-Match"] to it.body!!.utf8() })
        // A creative: the overlay as written, the press's key.
        server.enqueue(json(201, """{"ref":"CR-0008","company":"FX","state":"queued","requested_by":{"code":"owner","kind":"owner"}}"""))
        api.createCreative("FX", "image", "brief", "telegram_post", com.coinepro.hq.core.net.Overlay("عنوان", null, "ثبت‌نام", true), null, "gpt", "k-cr")
        val cr = server.takeRequest()
        assertEquals("k-cr" to """{"company":"FX","kind":"image","brief_md":"brief","placement":"telegram_post","overlay":{"title_fa":"عنوان","body_fa":null,"cta_fa":"ثبت‌نام","mark":true},"player":"gpt"}""", cr.headers["Idempotency-Key"] to cr.body!!.utf8())
        // The devil's advocate is a mode of a message in thread A.
        server.enqueue(json(201, """{"message":{},"reply":{"state":"queued"}}"""))
        api.send("A", "قانعم کن", mode = "devil")
        assertEquals("""{"body":"قانعم کن","mode":"devil"}""", server.takeRequest().body!!.utf8())
    }

    @Test
    fun section21ReadsAndCodes() = runTest {
        server.enqueue(json(200, "[]"))
        api.wasteRange("2026-10-03", "2026-10-16", "PC")
        assertEquals("from=2026-10-03&to=2026-10-16&company=PC", server.takeRequest().url.encodedQuery)
        server.enqueue(json(200, """{"items":[{"by":"company","key":"TY","company":"TY","period":"month","cost_usd":"36.30","accepted":34}],"next_cursor":null}"""))
        assertEquals("TY", api.roi("company", "month").single().key)
        assertEquals("by=company&period=month", server.takeRequest().url.encodedQuery)
        server.enqueue(json(200, """{"path":"src/chart/cache.ts","patch":"@@","truncated":false}"""))
        api.diffFile("D-000017", "src/chart/cache.ts")
        assertEquals("/api/v1/decisions/D-000017/diff?file=src%2Fchart%2Fcache.ts", server.takeRequest().url.let { "${it.encodedPath}?${it.encodedQuery}" })
        // The §21.12 codes in the app's words; a rate limit says how long to wait.
        fun err(code: Int, body: String, wait: String? = null): ApiException {
            server.enqueue(MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").apply { if (wait != null) addHeader("Retry-After", wait) }.body(body).build())
            return try { kotlinx.coroutines.runBlocking { api.substitutes() }; fail("expected ApiException"); throw IllegalStateException() } catch (e: ApiException) { server.takeRequest(); e }
        }
        assertEquals("این کارت دیگر منتظر تصمیم نیست؛ یادداشت فقط برای کارت منتظر نوشته میشود.", com.coinepro.hq.core.net.mgmtError(err(409, """{"code":"decision_not_pending","message_fa":"server","status":409}""")))
        assertEquals("تغییر مدل در پاکت ماهانه‌ی شرکت جا نمیشود؛ هیچ چیز عوض نشد.", com.coinepro.hq.core.net.mgmtError(err(409, """{"code":"envelope_exceeded","message_fa":"server","status":409}""")))
        assertEquals("سقف پر شده؛ ۲ دقیقه‌ی دیگر.".replace("۲", "2"), com.coinepro.hq.core.net.mgmtError(err(429, """{"code":"rate_limited","message_fa":"سقف پر شده","status":429}""", "120")))
        assertEquals("server", com.coinepro.hq.core.net.mgmtError(err(422, """{"code":"validation_failed","message_fa":"server","status":422}""")))
    }
}
