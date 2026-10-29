package com.coinepro.hq

import com.coinepro.hq.core.data.NoticeKind
import com.coinepro.hq.core.data.OrderBrief
import com.coinepro.hq.core.data.OrderEnd
import com.coinepro.hq.core.data.OrderStage
import com.coinepro.hq.core.data.OrderTrack
import com.coinepro.hq.core.data.OrderWatcher
import com.coinepro.hq.core.data.agentTitleOf
import com.coinepro.hq.core.data.endOf
import com.coinepro.hq.core.data.holdersOf
import com.coinepro.hq.core.data.isOwnerOrder
import com.coinepro.hq.core.data.lastActivityOf
import com.coinepro.hq.core.data.noticeOf
import com.coinepro.hq.core.data.progressOf
import com.coinepro.hq.core.data.reasonOf
import com.coinepro.hq.core.data.stageOf
import com.coinepro.hq.core.data.takenFa
import com.coinepro.hq.core.data.timelineOf
import com.coinepro.hq.core.net.Actor
import com.coinepro.hq.core.net.AgentStep
import com.coinepro.hq.core.net.ChainStep
import com.coinepro.hq.core.net.EmployeeRef
import com.coinepro.hq.core.net.Run
import com.coinepro.hq.core.net.StepAction
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.core.net.Work
import com.coinepro.hq.core.net.WorkEvent
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The order tracker: the stage read from status, children and runs; the estimate (honest, stepwise); who holds it; the timeline;
 *  and the notices the stream makes for the owner's orders. */
@org.junit.runner.RunWith(org.robolectric.RobolectricTestRunner::class)
class OrdersTest {
    private val ceo = EmployeeRef("TY-CEO", "TY", "ceo", "مدیرعامل")
    private val mgr = EmployeeRef("TY-GROWTH-MGR", "TY", "manager", "مدیر رشد", "GROWTH")
    private val emp1 = EmployeeRef("TY-GROWTH-01", "TY", "employee", "تحلیلگر سئو", "GROWTH")
    private val emp2 = EmployeeRef("TY-GROWTH-02", "TY", "employee", "تحلیلگر کمپین", "GROWTH")
    private val owner = Actor("owner", "owner", "مدیر کل")

    private fun work(
        id: String, ref: String, status: String, assignee: EmployeeRef = ceo, children: List<ChainStep> = emptyList(), progress: Int? = null,
        updated: String = "2026-10-17T08:00:00Z", by: Actor? = owner,
    ) = Work(id, ref, "TY", title = "کار $ref", status = status, assignee = assignee, children = children, progressPct = progress, updatedAt = updated, createdAt = "2026-10-17T06:00:00Z", createdBy = by)

    private fun step(id: String, ref: String, status: String, who: EmployeeRef) = ChainStep(id, ref, 1, status, who, "2026-10-17T07:00:00Z")

    private fun ev(kind: String, at: String, vararg data: Pair<String, String>, actor: String = "TY-CEO") =
        WorkEvent(0, kind, at, actor, "agent", JsonObject(data.toMap().mapValues { JsonPrimitive(it.value) }))

    @Test
    fun stagesFollowTheStatusTheChildrenAndTheRuns() {
        assertEquals(OrderStage.RECEIVED, stageOf(OrderTrack(work("a", "W-000001", "queued"))))
        // Accepted, nobody under it: taken; a run on it counts as taken too.
        assertEquals(OrderStage.TAKEN, stageOf(OrderTrack(work("a", "W-000001", "in_progress"))))
        val run = Run("r", "TY-CEO", "TY", state = "running", queuedAt = "2026-10-17T07:00:00Z")
        assertEquals(OrderStage.TAKEN, stageOf(OrderTrack(work("a", "W-000001", "queued"), runs = listOf(run))))
        // Children that have not started: delegated; one at work (or a progress report on the order itself): working.
        val queuedKid = step("k", "W-000002", "queued", mgr)
        assertEquals(OrderStage.DELEGATED, stageOf(OrderTrack(work("a", "W-000001", "waiting", children = listOf(queuedKid)))))
        val busyKid = step("k", "W-000002", "in_progress", mgr)
        assertEquals(OrderStage.WORKING, stageOf(OrderTrack(work("a", "W-000001", "waiting", children = listOf(busyKid)))))
        assertEquals(OrderStage.WORKING, stageOf(OrderTrack(work("a", "W-000001", "in_progress", progress = 30))))
        // A grandchild at work under a queued-looking child step: working (the child's detail says so).
        val kidDetail = work("k", "W-000002", "waiting", mgr, children = listOf(step("g", "W-000003", "in_progress", emp1)))
        assertEquals(OrderStage.WORKING, stageOf(OrderTrack(work("a", "W-000001", "waiting", children = listOf(queuedKid)), kids = listOf(kidDetail))))
        assertEquals(OrderStage.DELIVERED, stageOf(OrderTrack(work("a", "W-000001", "delivered"))))
        assertEquals(OrderStage.DONE, stageOf(OrderTrack(work("a", "W-000001", "done"))))
    }

    @Test
    fun aFailedOrderKeepsTheStageItReached() {
        val t = OrderTrack(work("a", "W-000001", "failed", children = listOf(step("k", "W-000002", "cancelled", mgr))), events = listOf(ev("failed", "2026-10-17T08:00:00Z", "reason" to "شرکت متوقف است")))
        assertEquals(OrderEnd.FAILED, endOf(t.root))
        assertEquals(OrderStage.DELEGATED, stageOf(t))
        assertEquals(25, progressOf(t))
        assertEquals("شرکت متوقف است", reasonOf(t))
        assertEquals(OrderEnd.CANCELLED, endOf(work("a", "W-1", "cancelled")))
    }

    @Test
    fun progressIsAStepwiseEstimateFromStageAndChildren() {
        assertEquals(5, progressOf(OrderTrack(work("a", "W-1", "queued"))))
        assertEquals(15, progressOf(OrderTrack(work("a", "W-1", "in_progress"))))
        assertEquals(25, progressOf(OrderTrack(work("a", "W-1", "waiting", children = listOf(step("k", "W-2", "queued", mgr))))))
        // Two children, one delivered and one in progress at 40%: 30 + 60 × (1 + 0.4) / 2 = 72 → 70 (steps of 5).
        val kids = listOf(step("k1", "W-2", "delivered", emp1), step("k2", "W-3", "in_progress", emp2))
        val t = OrderTrack(work("a", "W-1", "waiting", children = kids), kids = listOf(work("k1", "W-2", "delivered", emp1), work("k2", "W-3", "in_progress", emp2, progress = 40)))
        assertEquals(70, progressOf(t))
        // Without the children's details, a child's step status is all there is: in progress counts 0.3 → 30 + 60 × 0.65 = 69 → 70.
        assertEquals(70, progressOf(OrderTrack(work("a", "W-1", "waiting", children = kids))))
        // Nobody under it: its own progress report (50%) → 30 + 30 = 60.
        assertEquals(60, progressOf(OrderTrack(work("a", "W-1", "in_progress", progress = 50))))
        // A cancelled child does not hold the others back.
        val withCancelled = OrderTrack(work("a", "W-1", "waiting", children = listOf(step("k1", "W-2", "delivered", emp1), step("k2", "W-3", "cancelled", emp2))))
        assertEquals(90, progressOf(withCancelled))
        assertEquals(95, progressOf(OrderTrack(work("a", "W-1", "delivered"))))
        assertEquals(100, progressOf(OrderTrack(work("a", "W-1", "done"))))
        // A 0% report is not work under way yet; any report above it is. Always a multiple of 5, never above 90 before delivery.
        assertEquals(15, progressOf(OrderTrack(work("a", "W-1", "in_progress", progress = 0))))
        for (p in 1..100) {
            val v = progressOf(OrderTrack(work("a", "W-1", "in_progress", progress = p)))
            assertEquals(0, v % 5)
            assertTrue(v in 30..90)
        }
    }

    @Test
    fun theHolderIsTheOpenPathDownToWhoeverWorks() {
        val root = work("a", "W-1", "waiting", children = listOf(step("k", "W-2", "waiting", mgr)))
        val kid = work("k", "W-2", "waiting", mgr, children = listOf(step("g1", "W-3", "in_progress", emp1), step("g2", "W-4", "delivered", emp2)))
        val paths = holdersOf(OrderTrack(root, kids = listOf(kid)))
        assertEquals(listOf(listOf("TY-CEO", "TY-GROWTH-MGR", "TY-GROWTH-01")), paths.map { p -> p.map { it.code } })
        assertEquals(listOf(listOf("TY-CEO")), holdersOf(OrderTrack(work("a", "W-1", "in_progress"))).map { p -> p.map { it.code } })
        assertTrue(holdersOf(OrderTrack(work("a", "W-1", "delivered"))).isEmpty())
    }

    @Test
    fun lastActivityIsTheNewestMomentOnItOrUnderIt() {
        val run = Run("r", "TY-GROWTH-01", "TY", state = "running", queuedAt = "2026-10-17T07:00:00Z", startedAt = "2026-10-17T07:10:00Z",
            stepsDetail = listOf(AgentStep(1, "2026-10-17T08:20:00Z", "خواند")))
        val t = OrderTrack(work("a", "W-1", "waiting", updated = "2026-10-17T08:00:00Z"), kidRuns = mapOf("W-2" to listOf(run)))
        assertEquals("2026-10-17T08:20:00Z", lastActivityOf(t))
    }

    @Test
    fun theTimelineSaysWhatHappenedNewestFirstWithRefsAsFigures() {
        val run = Run("0193b1c2-0000-7000-8000-000000000001", "TY-CEO", "TY", state = "done", queuedAt = "2026-10-17T06:05:00Z", startedAt = "2026-10-17T06:06:00Z",
            finishedAt = "2026-10-17T06:20:00Z", stepsDetail = listOf(AgentStep(1, "2026-10-17T06:10:00Z", "فرمان را خواند", listOf(StepAction("work.read", "ok")))))
        val t = OrderTrack(
            work("a", "W-000001", "delivered"),
            events = listOf(
                ev("created", "2026-10-17T06:00:00Z", "assignee" to "TY-CEO", actor = "owner"),
                ev("accepted", "2026-10-17T06:05:00Z"),
                ev("delegated", "2026-10-17T06:20:00Z", "child" to "W-000002", "to" to "TY-GROWTH-MGR"),
                ev("delivered", "2026-10-17T09:00:00Z", "deliverable" to "O-000044"),
            ),
            runs = listOf(run),
        )
        val m = timelineOf(t)
        assertEquals("delivered", m.first().kind)
        assertTrue(m.first().parts.any { it.fig && it.text == "O-000044" })
        val delegated = m.first { it.kind == "delegated" }
        assertTrue(delegated.parts.any { it.text.contains("مدیر رشد") })
        assertTrue(delegated.parts.any { it.fig && it.text == "W-000002" })
        assertTrue(m.any { it.kind == "run.step" && it.parts.any { p -> p.text == "فرمان را خواند" } })
        // No id ever reaches a line: the run is named by its employee.
        assertFalse(m.flatMap { it.parts }.any { it.text.contains("0193b1c2") })
        // Newest first.
        assertEquals(m.map { it.at }.sortedDescending(), m.map { it.at })
    }

    @Test
    fun agentCodesReadAsTitles() {
        assertEquals("مدیرعامل", agentTitleOf("TY-CEO"))
        assertEquals("مدیر رشد", agentTitleOf("TY-GROWTH-MGR"))
        assertNull(agentTitleOf("TY-GROWTH-01"))
        assertEquals("مدیرعامل گرفت", takenFa(work("a", "W-1", "queued")))
        assertEquals("مدیر گرفت", takenFa(work("a", "W-1", "queued", mgr)))
        assertTrue(isOwnerOrder(work("a", "W-1", "queued")))
        assertFalse(isOwnerOrder(work("a", "W-1", "queued", by = Actor("TY-CEO", "agent"))))
    }

    @Test
    fun theStreamMakesOneNoticePerStageOfAnOwnersOrder() {
        val orders = mapOf("W-000210" to OrderBrief("id-1", "W-000210", "گزارش رقبا", "TY"))
        val told = mutableSetOf<String>()
        fun e(type: String, ref: String?, vararg d: Pair<String, String>) = StreamEvent("1", type, "2026-10-17T08:00:00Z", "TY", ref, JsonObject(d.toMap().mapValues { JsonPrimitive(it.value) }))
        val delegated = noticeOf(e("work.delegated", "W-000210", "child" to "W-000215", "to" to "TY-GROWTH-MGR"), orders, told)!!
        assertEquals(NoticeKind.DELEGATED, delegated.kind)
        assertTrue(delegated.text.contains("مدیر رشد"))
        // A second delegation of the same order is not told again; another order's events are not told at all.
        assertNull(noticeOf(e("work.delegated", "W-000210", "child" to "W-000216", "to" to "TY-TECH-MGR"), orders, told))
        assertNull(noticeOf(e("work.delegated", "W-000999", "to" to "TY-TECH-MGR"), orders, told))
        // The output first, then the status change: one delivery notice, carrying the output's ref.
        val out = noticeOf(e("deliverable.created", "O-000048", "work" to "W-000210"), orders, told)!!
        assertEquals(NoticeKind.DELIVERED, out.kind)
        assertEquals("O-000048", out.deliverable)
        assertNull(noticeOf(e("work.updated", "W-000210", "status" to "delivered"), orders, told))
        assertEquals(NoticeKind.DONE, noticeOf(e("work.completed", "W-000210", "by" to "owner"), orders, told)!!.kind)
        assertEquals(NoticeKind.FAILED, noticeOf(e("work.updated", "W-000210", "status" to "failed"), orders, mutableSetOf())!!.kind)
        // Updates that are not a change of stage say nothing.
        assertNull(noticeOf(e("work.updated", "W-000210", "progress_pct" to "40"), orders, mutableSetOf()))
    }

    @Test
    fun whatAnOrderHadReachedBeforeTheAppOpenedIsNotToldAgain() {
        assertEquals(listOf("W-1:DELEGATED"), OrderWatcher.alreadyReached(work("a", "W-1", "waiting")))
        assertEquals(listOf("W-1:DELEGATED", "W-1:DELIVERED"), OrderWatcher.alreadyReached(work("a", "W-1", "delivered")))
        assertEquals(4, OrderWatcher.alreadyReached(work("a", "W-1", "done")).size)
        assertTrue(OrderWatcher.alreadyReached(work("a", "W-1", "queued")).isEmpty())
    }
}
