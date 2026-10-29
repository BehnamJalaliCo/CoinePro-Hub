package com.coinepro.hq

import com.coinepro.hq.core.data.CompanyControl
import com.coinepro.hq.core.data.LiveActivity
import com.coinepro.hq.core.data.QueryCache
import com.coinepro.hq.core.data.coState
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.BudgetUse
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.ControlState
import com.coinepro.hq.core.net.Freeze
import com.coinepro.hq.core.net.KillSwitch
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.ui.companies.controlHistory
import java.time.Instant
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mockwebserver3.Dispatcher
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The owner's control (contract §9, OPERATING_MODEL §1.12) as [CompanyControl] runs it: engaging a kill switch asks no passkey,
 * releasing one asks it on the scope (`kill_switch.release`, `holding` or `company:<CODE>`), opening deploys asks it on the company
 * (`deploy_freeze.lift`), a month budget is sealed on the SHA-256 of the exact body (`budgets.update`); every action shows its
 * result on the cached screens before the hub answers and puts them back exactly as they were when the hub refuses; a cancelled
 * passkey changes nothing and sends nothing. Also the state a card reads ([coState]) and the stream's live activity ([LiveActivity]).
 */
@RunWith(RobolectricTestRunner::class)
class ControlTest {
    private val server = MockWebServer()
    private val tokens = object : TokenSource {
        override fun token() = "t0ken"
        override fun clear() = Unit
    }
    private lateinit var api: Api
    private lateinit var cache: QueryCache
    private val now = Instant.parse("2026-10-17T08:30:00Z")

    private val released = ControlState(
        holding = KillSwitch("holding", "HQ", "released", null, "2026-10-15T08:00:00Z"),
        companies = listOf(
            KillSwitch("company:TY", "TY", "released", null, "2026-10-15T08:00:00Z"),
            KillSwitch("company:FX", "FX", "released", null, "2026-10-15T08:00:00Z"),
        ),
        deployFreezes = listOf(Freeze("FX", "انتشار در جریان", "2026-10-17T10:05:00Z", "pipeline")),
    )
    private val companies = listOf(
        Company("co-HQ", "HQ", "holding"), Company("co-TY", "TY", "company"),
        Company("co-FX", "FX", "company", deployFreezeUntil = "2026-10-17T10:05:00Z"),
    )

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = now
        server.start()
        api = Api(server.url("/").toString(), tokens)
        cache = QueryCache(CoroutineScope(Dispatchers.Unconfined))
        cache.get("control", setOf("control")) { api.control() }.set(released)
        cache.get("companies", setOf("companies")) { api.companies() }.set(companies)
        cache.get("company:FX", setOf("companies")) { api.company("FX") }.set(companies[2])
    }

    @After
    fun tearDown() {
        server.close()
        com.coinepro.hq.core.format.HqClock.fixed = null
    }

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()
    private fun problem(code: Int, c: String, fa: String) = json(code, """{"type":"about:blank","title":"$c","status":$code,"code":"$c","message_fa":"$fa"}""")

    private fun stateJson(holding: String = "released", fx: String = "released", freezes: String = "[]") = """
        {"holding":{"scope":"holding","company":"HQ","state":"$holding","reason":null,"changed_by":"owner","changed_at":"2026-10-17T08:30:00Z"},
         "companies":[{"scope":"company:TY","company":"TY","state":"released","reason":null,"changed_by":null,"changed_at":"2026-10-15T08:00:00Z"},
                      {"scope":"company:FX","company":"FX","state":"$fx","reason":"رفتار غیرعادی","changed_by":"owner","changed_at":"2026-10-17T08:30:00Z"}],
         "deploy_freezes":$freezes}"""

    private val control get() = cache.get("control", setOf("control")) { api.control() }.state.value.data!!
    private val list get() = cache.get("companies", setOf("companies")) { api.companies() }.state.value.data!!

    /** A [CompanyControl] whose passkey records what it was asked to sign. */
    private fun controlWith(signed: MutableList<Pair<String, String>>, token: String = "su-1") =
        CompanyControl(api, cache, { action, target -> signed += action to target; token }, { now })

    private fun RecordedRequest.json(): JsonObject = Api.json.parseToJsonElement(body!!.utf8()).jsonObject

    // ------------------------------------------------------------------ kill switch --
    @Test
    fun engagingAKillSwitchAsksNoPasskey() = runTest {
        server.enqueue(json(200, stateJson(fx = "engaged")))
        val signed = mutableListOf<Pair<String, String>>()
        val out = controlWith(signed).stop("FX", holding = false, reason = "رفتار غیرعادی")
        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("/api/v1/control/kill-switch", req.url.encodedPath)
        assertEquals("company:FX", req.json()["scope"]!!.jsonPrimitive.content)
        assertEquals("engaged", req.json()["state"]!!.jsonPrimitive.content)
        assertEquals("رفتار غیرعادی", req.json()["reason"]!!.jsonPrimitive.content)
        assertNotNull("kill switch writes are idempotent (§1)", req.headers["Idempotency-Key"])
        assertNull("engaging takes no step-up (speed matters)", req.headers["X-Step-Up"])
        assertTrue(signed.isEmpty())
        // The hub's answer is what the screens keep.
        assertEquals("engaged", out.companies.first { it.company == "FX" }.state)
        assertEquals("engaged", control.companies.first { it.company == "FX" }.state)
        assertEquals("engaged", list.first { it.code == "FX" }.killSwitch)
    }

    @Test
    fun releasingAKillSwitchAsksThePasskeyOnItsScope() = runTest {
        cache.get("control", setOf("control")) { api.control() }.set(released.copy(companies = released.companies.map { if (it.company == "FX") it.copy(state = "engaged") else it }))
        server.enqueue(json(200, stateJson()))
        val signed = mutableListOf<Pair<String, String>>()
        controlWith(signed, token = "su-release").resume("FX", holding = false, reason = "بررسی تمام شد")
        val req = server.takeRequest()
        assertEquals(listOf("kill_switch.release" to "company:FX"), signed)
        assertEquals("su-release", req.headers["X-Step-Up"])
        assertEquals("released", req.json()["state"]!!.jsonPrimitive.content)
        assertEquals("released", control.companies.first { it.company == "FX" }.state)
    }

    @Test
    fun theHoldingSwitchIsReleasedOnTheHoldingScope() = runTest {
        cache.get("control", setOf("control")) { api.control() }.set(released.copy(holding = released.holding.copy(state = "engaged")))
        server.enqueue(json(200, stateJson()))
        val signed = mutableListOf<Pair<String, String>>()
        controlWith(signed).resume("HQ", holding = true, reason = "ادامه")
        val req = server.takeRequest()
        assertEquals(listOf("kill_switch.release" to "holding"), signed)
        assertEquals("holding", req.json()["scope"]!!.jsonPrimitive.content)
        assertEquals("su-1", req.headers["X-Step-Up"])
    }

    @Test
    fun aCancelledPasskeyChangesNothingAndSendsNothing() = runTest {
        val engaged = released.copy(companies = released.companies.map { if (it.company == "FX") it.copy(state = "engaged") else it })
        cache.get("control", setOf("control")) { api.control() }.set(engaged)
        val c = CompanyControl(api, cache, { _, _ -> throw ApiException(400, "passkey_ceremony_failed", "تأیید با اثر انگشت یا چهره لغو شد.") }, { now })
        try {
            c.resume("FX", holding = false, reason = "ادامه")
            fail("expected the passkey's refusal")
        } catch (e: ApiException) {
            assertEquals("passkey_ceremony_failed", e.code)
        }
        assertEquals(0, server.requestCount)
        assertEquals(engaged, control)
    }

    // ------------------------------------------------------------------ optimistic --
    @Test
    fun aStopShowsAtOnceAndRollsBackWhenTheHubRefuses() = runTest {
        var seenDuringCall: Pair<String?, String?>? = null
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                // While the call is in flight the screens already show the company stopped.
                seenDuringCall = control.companies.first { it.company == "FX" }.state to list.first { it.code == "FX" }.killSwitch
                return problem(503, "policy_unavailable", "سیاست در دسترس نیست؛ دوباره تلاش کن.")
            }
        }
        val before = control to list
        try {
            controlWith(mutableListOf()).stop("FX", holding = false, reason = "فوری")
            fail("expected the hub's refusal")
        } catch (e: ApiException) {
            assertEquals("policy_unavailable", e.code)
            assertEquals("سیاست در دسترس نیست؛ دوباره تلاش کن.", e.messageFa)
        }
        assertEquals("engaged" to "engaged", seenDuringCall)
        // Rolled back exactly: every query as it was.
        assertEquals(before.first, control)
        assertEquals(before.second, list)
    }

    @Test
    fun aRefusedReleaseRollsBackToStopped() = runTest {
        val engaged = released.copy(companies = released.companies.map { if (it.company == "FX") it.copy(state = "engaged", reason = "مصرف بالا", changedBy = "FX-CEO") else it })
        cache.get("control", setOf("control")) { api.control() }.set(engaged)
        server.enqueue(problem(403, "forbidden", "این کلید را فقط کسی که زده آزاد میکند."))
        try {
            controlWith(mutableListOf()).resume("FX", holding = false, reason = "ادامه")
            fail("expected the hub's refusal")
        } catch (e: ApiException) {
            assertEquals(403, e.status)
        }
        assertEquals(engaged, control)
        assertEquals("مصرف بالا", control.companies.first { it.company == "FX" }.reason)
    }

    // ------------------------------------------------------------------ deploys --
    @Test
    fun closingDeploysAsksNoPasskeyAndSendsTheSpan() = runTest {
        server.enqueue(json(200, """{"company":"TY","active":true,"until":"2026-10-17T12:30:00Z"}"""))
        val signed = mutableListOf<Pair<String, String>>()
        controlWith(signed).freeze("TY", hours = 4, reason = "انتشار بزرگ")
        val req = server.takeRequest()
        assertEquals("/api/v1/control/deploy-freeze", req.url.encodedPath)
        assertEquals("TY", req.json()["company"]!!.jsonPrimitive.content)
        assertEquals("2026-10-17T12:30:00Z", req.json()["until"]!!.jsonPrimitive.content)
        assertNull(req.headers["X-Step-Up"])
        assertTrue(signed.isEmpty())
        assertEquals("2026-10-17T12:30:00Z", list.first { it.code == "TY" }.deployFreezeUntil)
        assertTrue(control.deployFreezes.any { it.company == "TY" })
    }

    @Test
    fun openingDeploysIsSealedAndLiftsWithAPastUntil() = runTest {
        server.enqueue(json(200, """{"company":"FX","active":false,"until":"2026-10-17T08:29:00Z"}"""))
        val signed = mutableListOf<Pair<String, String>>()
        val out = controlWith(signed, token = "su-lift").unfreeze("FX", reason = "انتشار تمام شد")
        val req = server.takeRequest()
        assertEquals(listOf("deploy_freeze.lift" to "company:FX"), signed)
        assertEquals("su-lift", req.headers["X-Step-Up"])
        assertTrue(Instant.parse(req.json()["until"]!!.jsonPrimitive.content).isBefore(now))
        assertFalse(out.active)
        assertNull(list.first { it.code == "FX" }.deployFreezeUntil)
        assertTrue(control.deployFreezes.none { it.company == "FX" })
    }

    @Test
    fun aRefusedUnfreezeKeepsTheFreeze() = runTest {
        server.enqueue(problem(409, "version_conflict", "دوباره باز کن."))
        try {
            controlWith(mutableListOf()).unfreeze("FX", reason = "باز کن")
            fail("expected the hub's refusal")
        } catch (_: ApiException) {
        }
        assertEquals("2026-10-17T10:05:00Z", list.first { it.code == "FX" }.deployFreezeUntil)
        assertEquals(released.deployFreezes, control.deployFreezes)
    }

    // ------------------------------------------------------------------ budget --
    @Test
    fun aMonthBudgetIsSealedOnTheExactBody() = runTest {
        cache.get("treasury:budgets", setOf("treasury")) { api.budgets() }.set(listOf(BudgetUse("FX", "company", "FX", "month", tokenLimit = 5_000_000, tokensUsed = 4_100_000, pct = 82.0)))
        server.enqueue(json(200, """[{"company":"FX","scope_type":"company","scope_ref":"FX","period":"month","token_limit":6000000,"usd_limit":null,"tokens_used":4100000,"usd_used":"42.30","pct":68.3,"level":0}]"""))
        val signed = mutableListOf<Pair<String, String>>()
        val out = controlWith(signed).setMonthBudget("FX", holding = false, tokenLimit = 6_000_000, usdLimit = null)
        val req = server.takeRequest()
        assertEquals("PUT", req.method)
        assertEquals("/api/v1/budgets", req.url.encodedPath)
        val body = req.body!!.utf8()
        assertEquals(listOf("budgets.update" to Api.sha256(body)), signed)
        assertEquals("su-1", req.headers["X-Step-Up"])
        val row = Api.json.parseToJsonElement(body).jsonObject["budgets"]!!.let { (it as kotlinx.serialization.json.JsonArray).single().jsonObject }
        assertEquals("company", row["scope_type"]!!.jsonPrimitive.content)
        assertEquals("month", row["period"]!!.jsonPrimitive.content)
        assertEquals(6_000_000L, row["token_limit"]!!.jsonPrimitive.content.toLong())
        assertEquals(68.3, out.single().pct!!, 0.001)
    }

    @Test
    fun aRefusedBudgetPutsTheOldEnvelopeBack() = runTest {
        val old = listOf(BudgetUse("FX", "company", "FX", "month", tokenLimit = 5_000_000, tokensUsed = 4_100_000, pct = 82.0))
        val q = cache.get("treasury:budgets", setOf("treasury")) { api.budgets() }
        q.set(old)
        server.enqueue(problem(403, "step_up_invalid", "تأیید منقضی شد؛ دوباره."))
        try {
            controlWith(mutableListOf()).setMonthBudget("FX", holding = false, tokenLimit = 9_000_000, usdLimit = null)
            fail("expected the hub's refusal")
        } catch (e: ApiException) {
            assertEquals("step_up_invalid", e.code)
        }
        assertEquals(old, q.state.value.data)
    }

    // ------------------------------------------------------------------ history --
    @Test
    fun theHistoryNamesWhoWhenAndTheOwnersReasons() = runTest {
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val action = request.url.queryParameter("action")
                // The audit rows are asked for one company and one action each.
                if (action != null && request.url.queryParameter("company") != "FX") return problem(422, "validation_failed", "company")
                fun row(seq: Int, at: String, actor: String, kind: String, act: String, ref: String, summary: String) =
                    """{"seq":$seq,"at":"$at","actor":{"kind":"$kind","code":"$actor","display_fa":null},"principal_kind":"$kind","company":"FX","action":"$act",
                       "action_class":"A2","target":{"kind":"x","ref":"$ref"},"request_id":null,"ip_hash":null,"step_up":${act.endsWith("release")},"summary":"$summary","prev_hash":"a","hash":"b"}"""
                return when {
                    request.url.encodedPath == "/api/v1/owner/interactions" -> json(200, """{"items":[
                        {"id":"i1","at":"2026-10-17T07:00:00.4Z","company":"FX","kind":"control","action":"kill_switch.set","target":{"kind":"kill_switch","ref":"company:FX"},"data":{"state":"released","reason":"بررسی تمام شد"}},
                        {"id":"i2","at":"2026-10-17T06:00:00Z","company":"FX","kind":"control","action":"deploy_freeze.set","target":{"kind":"company","ref":"FX"},"data":{"until":"2026-10-17T09:00:00Z","reason":"انتشار"}}],"next_cursor":null}""")
                    action == "kill_switch.engage" -> json(200, """{"items":[${row(3, "2026-10-17T06:30:00Z", "FX-CEO", "agent", "kill_switch.engage", "company:FX", "changed: engaged")}],"next_cursor":null}""")
                    action == "kill_switch.release" -> json(200, """{"items":[${row(4, "2026-10-17T07:00:00Z", "owner", "owner", "kill_switch.release", "company:FX", "changed: released")}],"next_cursor":null}""")
                    action == "deploy_freeze.set" -> json(200, """{"items":[${row(2, "2026-10-17T06:00:00Z", "owner", "owner", "deploy_freeze.set", "FX", "active")}],"next_cursor":null}""")
                    else -> problem(404, "not_found", "پیدا نشد.")
                }
            }
        }
        val h = api.controlHistory("FX", holding = false)
        assertEquals(listOf("release", "engage", "freeze"), h.map { it.kind })
        assertEquals("بررسی تمام شد", h[0].reason)
        assertTrue(h[0].stepUp)
        // An agent's reason is not in the audit book: the switch as it stands carries it (the screen adds it).
        assertEquals("FX-CEO", h[1].by.code)
        assertNull(h[1].reason)
        assertEquals("انتشار", h[2].reason)
        assertEquals("2026-10-17T09:00:00Z", h[2].until)
    }

    // ------------------------------------------------------------------ state --
    @Test
    fun theHoldingSwitchStopsEveryCompanyAndFreezesExpire() {
        val all = released.copy(holding = released.holding.copy(state = "engaged"))
        val ty = coState("TY", false, all)
        assertFalse(ty.stopped)
        assertTrue(ty.holdingStopped)
        assertFalse(ty.running)
        assertTrue(coState("HQ", true, all).stopped)
        assertEquals("holding", coState("HQ", true, all).scope)
        assertEquals("company:TY", ty.scope)
        // FX's freeze ends at 10:05; at 10:06 it is gone.
        assertTrue(coState("FX", false, released, now = Instant.parse("2026-10-17T10:00:00Z").toEpochMilli()).frozen)
        assertFalse(coState("FX", false, released, now = Instant.parse("2026-10-17T10:06:00Z").toEpochMilli()).frozen)
        // Before /control/state has loaded, the company row says enough.
        assertTrue(coState("FX", false, null, companies[2]).frozen)
        assertTrue(coState("PC", false, null, Company("co-PC", "PC", "company", killSwitch = "engaged")).stopped)
    }

    @Test
    fun liveActivityFollowsRunsAndActivity() {
        val live = LiveActivity { 1_000L }
        fun e(type: String, ref: String?, vararg data: Pair<String, String>) =
            StreamEvent("1", type, "2026-10-17T08:30:00Z", "TY", ref, JsonObject(data.toMap().mapValues { JsonPrimitive(it.value) }))
        live.on(e("run.started", "run-1", "employee" to "TY-GROWTH-01"))
        assertTrue(live.state.value.getValue("TY").busy)
        assertEquals(setOf("run-1"), live.state.value.getValue("TY").runs)
        live.on(e("run.finished", "run-1", "employee" to "TY-GROWTH-01", "state" to "done"))
        assertFalse(live.state.value.getValue("TY").busy)
        live.on(e("activity.changed", "TY-MEDIA-03", "activity" to "working"))
        assertEquals(setOf("TY-MEDIA-03"), live.state.value.getValue("TY").working)
        live.on(e("activity.changed", "TY-MEDIA-03", "activity" to "sleeping"))
        assertFalse(live.state.value.getValue("TY").busy)
        // The feed keeps what the owner reads (runs started and finished), not the presence changes.
        assertEquals(listOf("run.finished", "run.started"), live.state.value.getValue("TY").recent.map { it.type })
    }
}
