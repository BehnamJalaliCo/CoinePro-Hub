package com.coinepro.hq

import com.coinepro.hq.core.data.LabelState
import com.coinepro.hq.core.data.WorkTitles
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Work
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The live stream's lines carry the work's ref and title, never its id: unknown ids resolve once, a gone one says so, a failure retries. */
class WorkTitlesTest {
    private val id = "01a187f8-e3e9-7b4f-8dd2-3c4e5f607182"
    private val w = Work(id, "W-000003", "TY", title = "گزارش رقبا", status = "in_progress")

    @Test
    fun anIdResolvesOnceToItsRefAndTitle() = runTest {
        var calls = 0
        val t = WorkTitles(this) { key -> calls++; if (key == id) w else null }
        assertEquals(LabelState.Loading, t.get(id))
        t.request(id) // a second ask while the first is in flight does not call again
        advanceUntilIdle()
        val known = t.labels.value[id] as LabelState.Known
        assertEquals("W-000003", known.label.ref)
        assertEquals("گزارش رقبا", known.label.title)
        // Found by id, known by ref too.
        assertTrue(t.labels.value["W-000003"] is LabelState.Known)
        t.request(id)
        advanceUntilIdle()
        assertEquals(1, calls)
    }

    @Test
    fun aGoneWorkIsMissingAndAFailureIsTriedAgain() = runTest {
        var fail = true
        val t = WorkTitles(this) { key -> if (key == "W-000404") null else if (fail) throw ApiException(502, "hub_unreachable", "—") else w }
        t.request("W-000404")
        t.request(id)
        advanceUntilIdle()
        assertEquals(LabelState.Missing, t.labels.value["W-000404"])
        assertFalse(t.labels.value.containsKey(id))
        fail = false
        t.request(id)
        advanceUntilIdle()
        assertTrue(t.labels.value[id] is LabelState.Known)
    }

    @Test
    fun listsSeedTheCacheWithoutAnyCall() = runTest {
        val t = WorkTitles(this) { error("no call expected") }
        t.seed(listOf(w))
        assertTrue(t.get("W-000003") is LabelState.Known)
        assertTrue(t.get(id) is LabelState.Known)
    }

    @Test
    fun onlyRefsAndCodesMayBeShown() {
        assertTrue(WorkTitles.isUuid(id))
        assertFalse(WorkTitles.isHuman(id))
        assertTrue(WorkTitles.isHuman("W-000003"))
        assertTrue(WorkTitles.isHuman("O-000041"))
        assertTrue(WorkTitles.isHuman("TY-CEO"))
        assertTrue(WorkTitles.isHuman("AR-000110"))
        assertFalse(WorkTitles.isHuman("run-d1"))
        assertFalse(WorkTitles.isHuman("0193b1c2"))
        assertTrue(WorkTitles.isWorkRef("W-000210"))
        assertFalse(WorkTitles.isWorkRef("O-000044"))
    }
}
