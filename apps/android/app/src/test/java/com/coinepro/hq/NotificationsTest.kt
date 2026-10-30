package com.coinepro.hq

import com.coinepro.hq.core.data.NotificationGroups
import com.coinepro.hq.core.data.NotificationReads
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Choice
import com.coinepro.hq.core.net.Link
import com.coinepro.hq.core.net.Notification
import java.time.Instant
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** The owner's notifications: the hourly overseer finding is one row with its count, what it is about comes from its link, and marking
 *  read moves a row out of «خوانده‌نشده» (with a grace time to undo, since the hub cannot mark one unread again). */
@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
class NotificationsTest {
    private val now = Instant.parse("2026-10-17T08:30:00Z")
    private fun at(min: Long) = now.minusSeconds(min * 60).toString()
    private val finding = "یافته‌ی جدی ناظر کل: سلامت خود هاب — down: otel-collector, tempo; disk 90.4%"
    private fun n(id: String, title: String = finding, min: Long = 0, level: String = "decision", kind: String? = "finding", co: String = "HQ", read: String? = null) =
        Notification(id, level, co, title, createdAt = at(min), readAt = read, link = kind?.let { Link(it, "FI-$id") })

    @Test
    fun theSameAlertRaisedHourlyIsOneRowWithItsCount() {
        val list = listOf(n("1", min = 44), n("2", min = 104), n("3", min = 164), n("4", min = 224), n("5", min = 284), n("x", "انتشار ترمینال منتظر مُهر", 15, kind = "decision"))
        val groups = NotificationGroups.group(list)
        assertEquals(2, groups.size)
        // Newest group first; inside a group, newest first.
        assertEquals("x", groups[0].latest.id)
        assertEquals(5, groups[1].count)
        assertEquals(listOf("1", "2", "3", "4", "5"), groups[1].ids)
        assertTrue(groups[1].folded)
        assertEquals("5 بار، آخرین 44 دقیقه پیش", NotificationGroups.countLine(groups[1], now.toEpochMilli()))
    }

    @Test
    fun figuresInTheTitleDoNotSplitAGroup() {
        val a = n("1", "سلامت خود هاب — disk 90.4%", 10)
        val b = n("2", "سلامت خود هاب — disk 91.2%", 70)
        assertEquals(NotificationGroups.key(a), NotificationGroups.key(b))
        assertEquals(1, NotificationGroups.group(listOf(a, b)).size)
        // A different company, level or kind of link is a different alert.
        assertEquals(2, NotificationGroups.group(listOf(a, n("3", "سلامت خود هاب — disk 90.4%", co = "TY"))).size)
        assertEquals(2, NotificationGroups.group(listOf(a, n("4", "سلامت خود هاب — disk 90.4%", level = "urgent"))).size)
        assertEquals(2, NotificationGroups.group(listOf(a, n("5", "سلامت خود هاب — disk 90.4%", kind = "hold"))).size)
    }

    @Test
    fun questionsAreNeverFolded() {
        val q1 = n("q1", "چرا انتشار قبلی را برگرداندی؟", kind = null, level = "learning").copy(choices = listOf(Choice("risk", "ریسک")))
        val q2 = q1.copy(id = "q2")
        assertEquals(2, NotificationGroups.group(listOf(q1, q2)).size)
    }

    @Test
    fun theLabelIsWhatItIsAboutNotItsLevel() {
        // The hub raises the overseer's finding at level "decision"; it is a finding.
        assertEquals("یافته‌ی ناظر", NotificationGroups.category(n("1")))
        assertEquals("نگه‌داشت ناظر", NotificationGroups.category(n("2", kind = "hold")))
        assertEquals("تصمیم", NotificationGroups.category(n("3", kind = "decision")))
        assertEquals("جلسه", NotificationGroups.category(n("4", kind = "meeting", level = "info")))
        assertEquals("تأسیس", NotificationGroups.category(n("5", kind = "founding")))
        // No link: its level.
        assertEquals("یادگیری", NotificationGroups.category(n("6", kind = null, level = "learning")))
        assertEquals("فوری", NotificationGroups.category(n("7", kind = "unknown_kind", level = "urgent")))
    }

    @Test
    fun markedRowsMoveToTheReadListAtOnce() {
        val unread = listOf(n("1", min = 1), n("2", min = 2), n("3", min = 3))
        val read = listOf(n("r", "پشتیبان ساعتی انجام شد", 90, "info", "backup", read = at(80)))
        val (u, r) = NotificationGroups.split(unread, read, mapOf("2" to at(0)))
        assertEquals(listOf("1", "3"), u.map { it.id })
        assertEquals(listOf("2", "r"), r.map { it.id })
        assertEquals(at(0), r.first().readAt)
        // Once the hub confirms, a row is read on its own; nothing is shown twice.
        val (u2, r2) = NotificationGroups.split(unread.filter { it.id != "2" }, read + n("2", min = 2, read = at(0)), mapOf("2" to at(0)))
        assertEquals(listOf("1", "3"), u2.map { it.id })
        assertEquals(listOf("2", "r"), r2.map { it.id })
    }

    @Test
    fun aSwipeIsSentAfterTheGraceTimeAndUndoSendsNothing() = runTest {
        val sent = mutableListOf<String>()
        var refreshed = 0
        val reads = NotificationReads(this, readOne = { sent += it }, readAll = { _, _ -> }, onSent = { refreshed++ }, graceMs = 5_000)
        val t = reads.mark(listOf("1", "2"))
        assertEquals(setOf("1", "2"), reads.marked.value.keys)
        advanceTimeBy(4_000)
        assertTrue(sent.isEmpty())
        advanceTimeBy(1_500)
        runCurrent()
        assertEquals(setOf("1", "2"), sent.toSet())
        assertEquals(1, refreshed)
        assertFalse(reads.undo(t))

        val t2 = reads.mark(listOf("3"))
        advanceTimeBy(1_000)
        assertTrue(reads.undo(t2))
        assertFalse("3" in reads.marked.value)
        advanceUntilIdle()
        assertFalse("3" in sent)
    }

    @Test
    fun openingSendsAtOnceAndReadAllIsOneCall() = runTest {
        val sent = mutableListOf<String>()
        var all: Pair<String?, String?>? = null
        val reads = NotificationReads(this, readOne = { sent += it }, readAll = { b, l -> all = b to l }, graceMs = 5_000)
        reads.open("9")
        runCurrent()
        assertEquals(listOf("9"), sent)
        reads.mark(listOf("1", "2", "3"), at(0) to "decision")
        reads.flush()
        runCurrent()
        // «همه خوانده شد» up to the newest the owner saw, of the level on show: one call, not one per row.
        assertEquals(at(0) to "decision", all)
        assertEquals(listOf("9"), sent)
    }

    @Test
    fun aRefusedSendMakesTheRowsUnreadAgain() = runTest {
        val reads = NotificationReads(this, readOne = { throw ApiException(500, "internal_error", "خطا") }, readAll = { _, _ -> }, graceMs = 10)
        reads.mark(listOf("1"))
        advanceUntilIdle()
        assertTrue(reads.marked.value.isEmpty())
    }

    @Test
    fun confirmedMarksAreDroppedButWaitingOnesStay() = runTest {
        val reads = NotificationReads(this, readOne = {}, readAll = { _, _ -> }, graceMs = 5_000)
        reads.open("1")
        runCurrent()
        reads.mark(listOf("2"))
        reads.confirmed(listOf("1", "2"))
        assertEquals(setOf("2"), reads.marked.value.keys)
    }
}
