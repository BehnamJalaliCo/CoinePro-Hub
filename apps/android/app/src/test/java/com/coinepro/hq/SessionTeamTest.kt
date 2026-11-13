package com.coinepro.hq

import com.coinepro.hq.core.data.SessionEntry
import com.coinepro.hq.core.data.hireAskFa
import com.coinepro.hq.core.data.mergeSideLines
import com.coinepro.hq.core.data.narratorChipFa
import com.coinepro.hq.core.data.revisionOf
import com.coinepro.hq.core.data.revisions
import com.coinepro.hq.core.data.seatSaidFa
import com.coinepro.hq.core.data.sessionTimeline
import com.coinepro.hq.core.data.sideTitleFa
import com.coinepro.hq.core.data.sideTurn
import com.coinepro.hq.core.data.teamRead
import com.coinepro.hq.core.data.teamShown
import com.coinepro.hq.core.data.versionFa
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.ReportOutput
import com.coinepro.hq.core.net.SessionTeam
import com.coinepro.hq.core.net.SideLine
import com.coinepro.hq.core.net.TeamNarrator
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.gated
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
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
 * ⟨1.35⟩ Contract §57, the session's team one person at a time: the team and a side talk read as the hub writes them; the row shown
 * only when there is someone besides the holder (or the narrator) and never on a hub without `/team`; the chips' words; a side talk's
 * pages put together once each; the owner's word and a hire with the press's own key and no passkey; and §57.6, a chain of versions
 * drawn as its newest with «نسخه‌ی n», read leniently wherever the hub puts `revision_of`.
 */
@RunWith(RobolectricTestRunner::class)
class SessionTeamTest {
    private val server = MockWebServer()
    private lateinit var api: Api

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
    }

    @After
    fun tearDown() = server.close()

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    private val teamJson = """{"seats":[
        {"key":"PC-CEO","role":null,"role_fa":"مسئول جلسه","holder":true,"employee":{"code":"PC-CEO","title_fa":"مدیرعامل پرو-چارت","company":"PC"},"state":"working","last":null,"unread":0},
        {"key":"PC-SCR-01","role":"scriptwriter","role_fa":"نویسنده","holder":false,"employee":{"code":"PC-SCR-01","title_fa":"سناریست پرو-چارت","company":"PC"},"state":"working","last":{"at":"2026-11-13T08:24:00Z","who":"seat","text":"گذاشتم."},"unread":2},
        {"key":"role:video_director","role":"video_director","role_fa":"کارگردان","holder":false,"employee":null,"state":"empty","last":null,"unread":0}],
        "narrator":{"company":"PC","voice":"Kore","voice_fa":"Kore (محکم)","style_fa":null}}"""

    // ------------------------------------------------------------------ the team --
    @Test
    fun theTeamReadsAsTheHubWritesIt() {
        val t = Api.json.decodeFromString(SessionTeam.serializer(), teamJson)
        val (holder, writer, empty) = t.seats
        assertTrue(holder.holder)
        assertEquals("PC-SCR-01", writer.code)
        assertEquals("سناریست پرو-چارت", writer.whoFa)
        assertFalse(writer.empty)
        assertTrue(empty.empty)
        assertEquals("video_director", empty.roleKey)
        // an empty seat without its role field still says which role it is
        assertEquals("motion_designer", empty.copy(role = null, key = "role:motion_designer").roleKey)
        assertEquals("Kore (محکم)", t.narrator!!.voiceFa)
        // a hub that leaves fields out still reads
        assertEquals(0, Api.json.decodeFromString(SessionTeam.serializer(), """{"seats":[{"key":"x","role_fa":"y"}]}""").seats.single().unread)
    }

    @Test
    fun theRowShowsOnlyWhenThereIsSomeoneBesidesTheHolder() {
        val t = Api.json.decodeFromString(SessionTeam.serializer(), teamJson)
        assertFalse(teamShown(null))
        assertFalse(teamShown(SessionTeam()))
        assertFalse(teamShown(t.copy(seats = t.seats.take(1), narrator = null)))
        assertTrue(teamShown(t.copy(seats = t.seats.take(1))))
        assertTrue(teamShown(t.copy(seats = listOf(t.seats[0], t.seats[2]), narrator = null)))
    }

    @Test
    fun theChipsSayWhoAndWhat() {
        val (holder, writer, empty) = Api.json.decodeFromString(SessionTeam.serializer(), teamJson).seats
        assertEquals("مدیرعامل پرو-چارت، مسئول جلسه، در کار", seatSaidFa(holder))
        assertEquals("کارگردان: خالی؛ استخدام", seatSaidFa(empty))
        assertEquals("کارگردان استخدام شود؟", hireAskFa(empty))
        assertEquals("با سناریست پرو-چارت", sideTitleFa(writer))
        // a prose count in Persian digits
        assertEquals("سناریست پرو-چارت، نویسنده، در کار، ۲ حرف تازه", seatSaidFa(writer))
        assertEquals("گوینده: Kore (محکم)", narratorChipFa(TeamNarrator("PC", "Kore", "Kore (محکم)")))
        assertEquals("گوینده: Kore", narratorChipFa(TeamNarrator("PC", "Kore", " ")))
        assertEquals("نسخه‌ی ۳", versionFa(3))
    }

    @Test
    fun aSideTalkOpenedIsReadAndItsPagesAreOneList() {
        val t = Api.json.decodeFromString(SessionTeam.serializer(), teamJson)
        assertEquals(listOf(0, 0, 0), teamRead(t, "PC-SCR-01").seats.map { it.unread })
        fun l(id: String, who: String = "seat") = SideLine(JsonPrimitive(id), "2026-11-13T08:0${id.last()}:00Z", who, "", "t$id")
        // an older page before the newest, each line once; the owner's line just said, until the hub's page carries it
        assertEquals(listOf("1", "2", "3", "4"), mergeSideLines(listOf(l("1"), l("2")), listOf(l("2"), l("3"), l("4", "owner"), l("4", "owner"))).map { it.idText })
        val owner = sideTurn(l("5", "owner"), "PC-SCR-01")
        assertTrue(owner.owner)
        assertEquals("t5", owner.shown)
        val seat = sideTurn(l("6"), "PC-SCR-01")
        assertEquals("PC-SCR-01", seat.by)
        assertEquals("t6", seat.shown)
        // a line with a numeric id still reads
        assertEquals("7", Api.json.decodeFromString(SideLine.serializer(), """{"id":7,"at":"","who":"owner","who_fa":"مدیر کل","text":"x","work_ref":null}""").idText)
    }

    // ------------------------------------------------------------------ the routes --
    @Test
    fun theRoutesCarryThePressKeyAndNoPasskey() = runTest {
        server.enqueue(json(200, teamJson))
        assertEquals(3, api.sessionTeam("F-0094").seats.size)
        server.takeRequest().let { assertEquals("GET", it.method); assertEquals("/api/v1/orders/F-0094/team", it.url.encodedPath) }

        server.enqueue(json(200, """{"items":[{"id":"SL-1","at":"2026-11-13T08:00:00Z","who":"owner","who_fa":"مدیر کل","text":"کوتاه‌تر","work_ref":null}],"next_cursor":"12"}"""))
        val page = api.sideLines("F-0094", "media@TY", before = "40")
        assertEquals("12", page.nextCursor)
        assertTrue(page.items.single().owner)
        server.takeRequest().let {
            assertEquals("/api/v1/orders/F-0094/team/media%40TY/lines", it.url.encodedPath)
            assertEquals("40", it.url.queryParameter("before"))
            assertEquals("50", it.url.queryParameter("limit"))
        }

        server.enqueue(json(200, """{"line":{"id":"SL-2","at":"2026-11-13T08:01:00Z","who":"owner","who_fa":"مدیر کل","text":"کلمه‌ی کامنت «چارت» باشد","work_ref":"W-000431"},"work_ref":"W-000431","woken":true}"""))
        val said = api.sayToSeat("F-0094", "PC-SCR-01", "کلمه‌ی کامنت «چارت» باشد", "0b9a6c1e-7d6e-4c7e-9c1a-3f7b2a1d5e01")
        assertTrue(said.woken)
        assertEquals("SL-2", said.line.idText)
        server.takeRequest().let {
            assertEquals("POST", it.method)
            assertEquals("/api/v1/orders/F-0094/team/PC-SCR-01/say", it.url.encodedPath)
            assertEquals("0b9a6c1e-7d6e-4c7e-9c1a-3f7b2a1d5e01", it.headers["Idempotency-Key"])
            assertNull(it.headers["X-Step-Up"])
            assertEquals("""{"text":"کلمه‌ی کامنت «چارت» باشد"}""", it.body!!.utf8())
        }

        server.enqueue(json(200, teamJson))
        api.hireSeat("F-0094", "video_director", "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f")
        server.takeRequest().let {
            assertEquals("/api/v1/orders/F-0094/team/hire", it.url.encodedPath)
            assertEquals("1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f", it.headers["Idempotency-Key"])
            assertNull(it.headers["X-Step-Up"])
            assertEquals("""{"role":"video_director"}""", it.body!!.utf8())
        }

        // a refused hire is the hub's own Persian sentence
        server.enqueue(json(409, """{"type":"about:blank","title":"Conflict","status":409,"code":"envelope_exhausted","message_fa":"پاکت این ماه پرو-چارت پر است."}"""))
        try { api.hireSeat("F-0094", "motion_designer", "k"); fail("expected ApiException") } catch (e: ApiException) { assertEquals("پاکت این ماه پرو-چارت پر است.", e.messageFa) }
    }

    @Test
    fun aHubWithoutTheTeamHidesTheRow() = runTest {
        // the hub's own «not a seat of this session» is an answer, not a missing route
        server.enqueue(json(404, """{"code":"not_found","message_fa":"این آدم در این جلسه نیست.","status":404,"title":"Not found","type":"about:blank","detail":"no such seat"}"""))
        try { api.gated(HubFeature.SESSION_TEAM) { sideLines("F-0094", "ZZ") }; fail("expected ApiException") } catch (e: ApiException) { assertEquals(404, e.status) }
        assertTrue(api.gaps.has(HubFeature.SESSION_TEAM))
        // the framework's own 404: learnt missing once, never asked again
        server.enqueue(json(404, """{"detail":"Not Found"}"""))
        assertNull(api.gated(HubFeature.SESSION_TEAM) { sessionTeam("F-0094") })
        assertFalse(api.gaps.has(HubFeature.SESSION_TEAM))
        assertNull(api.gated(HubFeature.SESSION_TEAM) { fail("not asked again"); sessionTeam("F-0094") })
        assertEquals(2, server.requestCount)
    }

    // ------------------------------------------------------------- §57.6 versions --
    @Test
    fun aChainOfVersionsIsItsNewestWithItsNumber() {
        // O-3 is a new version of O-2, itself of O-1; O-5 of O-4, which is not on this page; O-9 stands alone
        val prev = mapOf("O-2" to "O-1", "O-3" to "O-2", "O-5" to "O-4")
        val r = revisions(listOf("O-1", "O-2", "O-3", "O-5", "O-9")) { prev[it] }
        assertEquals(setOf("O-1", "O-2"), r.hidden)
        assertEquals(mapOf("O-3" to 3, "O-5" to 2), r.version)
        // a loop is cut where it closes; a ref that names itself is no chain
        val loop = revisions(listOf("A", "B", "C")) { mapOf("A" to "B", "B" to "A", "C" to "C")[it] }
        assertEquals(setOf("A", "B"), loop.hidden)
        assertTrue(loop.version.isEmpty())
    }

    @Test
    fun revisionOfIsReadWhereverTheHubPutsIt() {
        fun out(extra: String) = Api.json.decodeFromString(ReportOutput.serializer(), """{"ref":"O-7","title_fa":"t","kind":"document"$extra}""")
        assertEquals("O-6", revisionOf(out(""","revision_of":"O-6"""")))
        assertEquals("O-6", revisionOf(out(""","revision_of":{"ref":"O-6","title_fa":"t"}""")))
        assertEquals("O-6", revisionOf(out(""","produced_with":{"model":"opus","revision_of":"O-6"}""")))
        assertNull(revisionOf(out(""","revision_of":null,"produced_with":"odd"""")))
        val pw = Api.json.parseToJsonElement("""{"model":"opus","revision_of":"O-5"}""").jsonObject
        assertEquals("O-5", revisionOf(out(""), pw))
        assertNull(revisionOf(out(""), JsonObject(emptyMap())))
    }

    @Test
    fun theTimelineDrawsOnlyTheNewestOfAChain() {
        val outs = listOf(ReportOutput("O-1", "notes-v5", "document"), ReportOutput("O-2", "notes-v6", "document", revisionOf = JsonPrimitive("O-1")))
        val report = OrderReport(ref = "F-1", outputs = outs)
        val r = revisions(outs.map { it.ref }) { ref -> outs.first { it.ref == ref }.let { revisionOf(it) } }
        val drawn = sessionTimeline(emptyList(), report, hasTalk = true).filterNot { it is SessionEntry.Output && it.output.ref in r.hidden }
        assertEquals(listOf("O-2"), drawn.filterIsInstance<SessionEntry.Output>().map { it.output.ref })
        assertEquals(2, r.version["O-2"])
    }
}
