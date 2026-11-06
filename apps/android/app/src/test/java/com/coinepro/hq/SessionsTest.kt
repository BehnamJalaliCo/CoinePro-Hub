package com.coinepro.hq

import com.coinepro.hq.core.data.Refs
import com.coinepro.hq.core.data.Spot
import com.coinepro.hq.core.data.addresseeFa
import com.coinepro.hq.core.data.badgeFa
import com.coinepro.hq.core.data.canLink
import com.coinepro.hq.core.data.clampSpot
import com.coinepro.hq.core.data.forOwner
import com.coinepro.hq.core.data.layoutCanvas
import com.coinepro.hq.core.data.linkAt
import com.coinepro.hq.core.data.madeFa
import com.coinepro.hq.core.data.madeRouteOf
import com.coinepro.hq.core.data.nodeAt
import com.coinepro.hq.core.data.officeFallback
import com.coinepro.hq.core.data.orderParticipants
import com.coinepro.hq.core.data.orderedTasks
import com.coinepro.hq.core.data.ownerUnread
import com.coinepro.hq.core.data.participantTitle
import com.coinepro.hq.core.data.personaIdTitle
import com.coinepro.hq.core.data.playersToAdd
import com.coinepro.hq.core.data.sessionBadge
import com.coinepro.hq.core.data.sessionClosed
import com.coinepro.hq.core.data.sessionLine
import com.coinepro.hq.core.data.sortSessions
import com.coinepro.hq.core.data.taskProgress
import com.coinepro.hq.core.data.tickedState
import com.coinepro.hq.core.data.yourTurnCount
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Blocker
import com.coinepro.hq.core.net.CanvasNode
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.CompanyLink
import com.coinepro.hq.core.net.Home
import com.coinepro.hq.core.net.HomeOrder
import com.coinepro.hq.core.net.Notification
import com.coinepro.hq.core.net.Office
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.OrderTurn
import com.coinepro.hq.core.net.SessionBrief
import com.coinepro.hq.core.net.SessionCard
import com.coinepro.hq.core.net.SessionParticipant
import com.coinepro.hq.core.net.SessionState
import com.coinepro.hq.core.net.SessionTask
import kotlin.math.abs
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** ⟨1.16, 1.17⟩ contract §34–§35: the sessions, the office, the canvas and what reaches the owner, as pure functions and wire shapes. */
class SessionsTest {
    private fun card(ref: String, badge: String, last: String, hidden: Boolean = false, closedAt: String? = null) =
        SessionCard(ref = ref, badge = badge, lastAt = last, hidden = hidden, closedAt = closedAt)

    @Test
    fun theOwnersTurnComesFirstThenReadyStuckMovingNewestFirstInEach() {
        val list = listOf(
            card("F-1", "moving", "2026-11-06T09:00:00Z"),
            card("F-2", "your_turn", "2026-11-06T07:00:00Z"),
            card("F-3", "stuck", "2026-11-06T08:00:00Z"),
            card("F-4", "your_turn", "2026-11-06T08:30:00Z"),
            card("F-5", "ready", "2026-11-05T08:30:00Z"),
            card("F-6", "moving", "2026-11-06T10:00:00Z", hidden = true),
            card("F-7", "closed", "2026-11-06T11:00:00Z", closedAt = "2026-11-06T11:00:00Z"),
        )
        assertEquals(listOf("F-4", "F-2", "F-5", "F-3", "F-1"), sortSessions(list).map { it.ref })
        assertEquals(2, yourTurnCount(list))
    }

    @Test
    fun badgesInWordsAndTheLineUnderTheTitle() {
        assertEquals("نوبت تو", badgeFa("your_turn"))
        assertEquals("آماده‌ی تأیید", badgeFa("ready"))
        assertEquals("گیر", badgeFa("stuck"))
        assertEquals("در جریان", badgeFa("anything"))
        assertEquals("مدیرعامل میپرسد", sessionLine(SessionCard("F-1", reasonFa = "مدیرعامل میپرسد", brief = SessionBrief(needFa = "جواب بده"))))
        assertEquals("جواب بده", sessionLine(SessionCard("F-1", brief = SessionBrief(needFa = "جواب بده", nowFa = "در کار"))))
        assertEquals("در کار", sessionLine(SessionCard("F-1", brief = SessionBrief(nowFa = "در کار"))))
    }

    @Test
    fun aReportWithoutTheSessionBlockReadsItsBadgeFromTheOrder() {
        assertEquals("your_turn", sessionBadge(OrderReport("F-1", turn = OrderTurn("کدام؟"))))
        assertEquals("stuck", sessionBadge(OrderReport("F-1", blockers = listOf(Blocker("budget")))))
        assertEquals("closed", sessionBadge(OrderReport("F-1", state = "delivered")))
        assertTrue(sessionClosed(OrderReport("F-1", state = "cancelled")))
        // A hub of ⟨1.17⟩: a delivered order stays open until the owner closes it.
        val ready = OrderReport("F-1", state = "delivered", session = SessionState(state = "open", badge = "ready"))
        assertEquals("ready", sessionBadge(ready))
        assertFalse(sessionClosed(ready))
    }

    @Test
    fun participantsHolderFirstAndModelsByName() {
        val ps = listOf(
            SessionParticipant("player:gpt", "player"), SessionParticipant("media@TY", "person"), SessionParticipant("ceo@TY", "holder", "مدیرعامل تریدیار"),
            SessionParticipant("media@TY", "person"),
        )
        assertEquals(listOf("ceo@TY", "media@TY", "player:gpt"), orderParticipants(ps).map { it.key })
        assertEquals("جی‌پی‌تی", participantTitle(SessionParticipant("player:gpt", "player")))
        assertEquals("مشاور کل", participantTitle(SessionParticipant("advisor")))
        assertEquals("مدیر رسانه", participantTitle(SessionParticipant("media@TY")))
        assertEquals(listOf("gemini", "deepseek"), playersToAdd(ps))
        assertEquals("مدیرعامل تریدیار", addresseeFa(null, ps))
        assertEquals("همه", addresseeFa("all", ps))
        assertEquals("دیپ‌سیک", personaIdTitle("player:deepseek", emptyList()))
    }

    @Test
    fun thePlanTicksDropsAndCounts() {
        val ts = listOf(
            SessionTask("a", 2, state = "done"), SessionTask("b", 1, state = "todo"), SessionTask("c", 3, state = "dropped"), SessionTask("d", 4, state = "doing"),
        )
        assertEquals(listOf("b", "a", "d", "c"), orderedTasks(ts).map { it.id })
        assertEquals(1 to 3, taskProgress(ts))
        assertEquals("done", tickedState("todo"))
        assertEquals("done", tickedState("doing"))
        assertEquals("todo", tickedState("done"))
    }

    @Test
    fun theOfficeFromAnOlderHubKeepsOpenOrdersOnly() {
        val home = Home(orders = listOf(HomeOrder("F-1", "الف", "waiting"), HomeOrder("F-2", "ب", "delivered"), HomeOrder("F-3", "پ", "blocked"), HomeOrder("F-4", "ت", "in_progress")))
        val companies = listOf(Company("1", "HQ", "holding", "هلدینگ"), Company("2", "TY", "company", "تریدیار"), Company("3", "OLD", "company", status = "archived"))
        val o = officeFallback(home, emptyList(), companies)
        assertEquals(listOf("F-1" to "your_turn", "F-3" to "stuck", "F-4" to "moving"), o.sessions.map { it.ref to it.badge })
        assertEquals(listOf("HQ" to "holding", "TY" to "company"), o.canvas.nodes.map { it.code to it.kind })
        assertEquals(0, o.approvalsTotal)
    }

    @Test
    fun theCanvasPutsTheHubInTheCentreAndCompaniesOnACircleUnlessPlaced() {
        val nodes = listOf(
            CanvasNode("HQ", kind = "holding"), CanvasNode("TY"), CanvasNode("FX", x = 0.2, y = 0.7), CanvasNode("PC"), CanvasNode("ZZ", x = 1.4, y = -0.2),
        )
        val s = layoutCanvas(nodes, radius = 0.4f)
        assertEquals(Spot(0.5f, 0.5f), s["HQ"])
        // The first company sits on top of the circle.
        assertTrue(abs(s.getValue("TY").x - 0.5f) < 1e-4 && abs(s.getValue("TY").y - 0.1f) < 1e-4)
        assertEquals(Spot(0.2f, 0.7f), s["FX"])
        assertEquals(Spot(1f, 0f), s["ZZ"])
        assertEquals("TY", nodeAt(s, 0.52f, 0.12f))
        assertNull(nodeAt(s, 0.3f, 0.3f))
        assertEquals(Spot(0.93f, 0.07f), clampSpot(1.2f, -0.5f))
    }

    @Test
    fun aTapOnALineFindsItsLinkAndANewLinkIsBetweenTwoCompaniesOnce() {
        val spots = mapOf("A" to Spot(0f, 0f), "B" to Spot(1f, 0f), "C" to Spot(0f, 1f))
        val links = listOf(CompanyLink("l1", "A", "B", "publishes"), CompanyLink("l2", "A", "C", "feeds", state = "off"))
        assertEquals("l1", linkAt(spots, links, 0.5f, 0.02f)?.id)
        assertEquals("l2", linkAt(spots, links, 0.01f, 0.6f)?.id)
        assertNull(linkAt(spots, links, 0.6f, 0.6f))
        assertFalse(canLink("A", "A", links))
        assertFalse(canLink("A", "B", links, "publishes"))
        assertTrue(canLink("A", "B", links, "feeds"))
        // An off link is made again on.
        assertTrue(canLink("A", "C", links, "feeds"))
        assertFalse(canLink(null, "B", links))
    }

    @Test
    fun onlyWhatIsTheOwnersReachesTheListAndTheBell() {
        fun n(id: String, domain: String?, visible: Boolean = true, critical: String? = null, read: String? = null) =
            Notification(id, "urgent", "TY", "عنوان", createdAt = "2026-11-06T08:00:00Z", domain = domain, ownerVisible = visible, criticalReason = critical, readAt = read)
        assertTrue(forOwner(n("1", null)))
        assertTrue(forOwner(n("2", "business")))
        assertFalse(forOwner(n("3", "infra")))
        assertTrue(forOwner(n("4", "security", critical = "data_leak")))
        assertFalse(forOwner(n("5", "business", visible = false)))
        assertEquals(2, ownerUnread(listOf(n("1", null), n("2", "media"), n("3", "tech"), n("6", null, read = "2026-11-06T09:00:00Z"))))
    }

    @Test
    fun anOrderRefOpensItsSessionAndAMadeRefIsOneWord() {
        assertEquals("session/F-0101", Refs.route("F-0101"))
        assertEquals("session/F-0101", Refs.forLink("order", "F-0101"))
        assertEquals("sessions", Refs.forLink("order", null))
        assertEquals("فرمان", madeFa("F-000232"))
        assertEquals("تصمیم", madeFa("D-000091"))
        assertEquals("مورد", madeFa("not a ref"))
        assertEquals("session/F-000232", madeRouteOf("F-000232"))
        assertEquals("cartable/D-000091", madeRouteOf("D-000091"))
    }

    @Test
    fun theWireShapesReadAsTheContractWritesThem() {
        val office = Api.json.decodeFromString(Office.serializer(), """
            {"sessions":[{"ref":"F-1","conversation_ref":"CV-1","title_fa":"الف","holder":{"code":"ceo@TY","title_fa":"مدیرعامل","company":"TY","company_fa":"تریدیار"},
              "badge":"your_turn","reason_fa":"میپرسد","brief":{"done_fa":"a","now_fa":"b","need_fa":"c"},"pace":"step",
              "participants":[{"key":"player:gpt","kind":"player","title_fa":"GPT","company":null}],"tasks":{"done":1,"total":3},
              "opened_at":"2026-11-06T08:00:00Z","last_at":"2026-11-06T09:00:00Z","closed_at":null,"hidden":false}],
             "approvals":[],"approvals_total":4,"money":{"revenue_month_usd":"4820.50","spend_month_usd":312.4,"budget_month_usd":null,"line_fa":"خوب"},
             "critical":[],"suggestions":[],"canvas":{"nodes":[{"code":"HQ","name_fa":"هلدینگ","kind":"holding","x":null,"y":null,"line_fa":"","open_sessions":2}],
             "links":[{"id":"7","from":"TY","to":"FX","kind":"publishes","purpose_fa":"p","state":"on","open_works":2,"updated_at":"2026-11-06T08:00:00Z"}]}}
        """.trimIndent())
        val s = office.sessions.single()
        assertEquals("CV-1", s.conversationRef)
        assertEquals("تریدیار", s.holder?.companyFa)
        assertEquals(1 to 3, s.tasks.done to s.tasks.total)
        assertEquals("player", s.participants.single().kind)
        assertEquals(4820.5, office.money.revenueMonthUsd!!, 1e-9)
        assertEquals(312.4, office.money.spendMonthUsd, 1e-9)
        assertNull(office.money.budgetMonthUsd)
        assertEquals(2, office.canvas.links.single().openWorks)
        val r = Api.json.decodeFromString(OrderReport.serializer(), """
            {"ref":"F-1","state":"waiting","pace":"step","conversation_ref":"CV-1","turn":{"question_fa":"کدام؟","at":"2026-11-06T08:00:00Z","by":{"code":"TY-CEO","kind":"employee"},"who_fa":"مدیرعامل"},
             "session":{"state":"open","badge":"your_turn","reason_fa":"میپرسد","closed_at":null,"hidden":false},"brief":{"done_fa":"a","now_fa":"b","need_fa":"c"},
             "tasks":[{"id":"t1","n":1,"title_fa":"کار","state":"doing","by":"agent","who_fa":null,"work_ref":"W-1"}],"participants":[{"key":"ceo@TY","kind":"holder"}]}
        """.trimIndent())
        assertEquals("step", r.pace)
        assertEquals("کدام؟", r.turn?.questionFa)
        assertEquals("your_turn", r.session?.badge)
        assertEquals("W-1", r.tasks.single().workRef)
        assertEquals("holder", r.participants.single().kind)
    }
}
