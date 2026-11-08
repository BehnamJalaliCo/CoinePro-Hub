package com.coinepro.hq

import com.coinepro.hq.core.data.ChatRow
import com.coinepro.hq.core.data.SessionEntry
import com.coinepro.hq.core.data.blockersFa
import com.coinepro.hq.core.data.chatRows
import com.coinepro.hq.core.data.eventsCountFa
import com.coinepro.hq.core.data.eventsSpan
import com.coinepro.hq.core.data.outputsFa
import com.coinepro.hq.core.data.quietLine
import com.coinepro.hq.core.data.sessionTimeline
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.ReportOutput
import com.coinepro.hq.core.net.ReportStep
import com.coinepro.hq.core.net.TalkTurn
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ⟨0.19.0⟩ The session's chat in order (the owner, 2026-11-08: «ببین چقدر همه چیز بهم ریختس»): the steps between two turns become one row
 * (each step still there, in order), the results between two turns one card, each row where its first one fell; no ref is a word, a ref in
 * parentheses with the hub's trailing hyphen included; the counts in Persian digits and the clock range as figures.
 */
class SessionTidyTest {
    private fun said(n: Int, by: String, at: String) = SessionEntry.Said(TalkTurn(id = JsonPrimitive("T-$n"), n = n, by = by, at = at, text = if (by == "owner") "x" else "", showMd = if (by == "owner") null else "y"))
    private fun step(k: String, at: String, text: String = k) = SessionEntry.Step(at, text, "st-$k")
    private fun out(ref: String, at: String, kind: String = "reel") = SessionEntry.Output(ReportOutput(ref, "عنوان $ref", kind), at)

    @Test
    fun theStepsAndResultsBetweenTwoTurnsAreOneRowEach() {
        val e = listOf(
            said(1, "owner", "t1"), step("a", "t2"), step("b", "t3"), said(2, "ceo@PC", "t4"),
            step("c", "t5"), out("O-1", "t6"), step("d", "t7"), out("O-2", "t8"), said(3, "ceo@PC", "t9"),
            out("O-3", "t10"), step("e", "t11"),
        )
        val rows = chatRows(e)
        assertEquals(listOf("Turn", "Events", "Turn", "Events", "Outputs", "Turn", "Outputs", "Events"), rows.map { it::class.simpleName })
        assertEquals(listOf("a", "b"), (rows[1] as ChatRow.Events).steps.map { it.text })
        assertEquals(listOf("c", "d"), (rows[3] as ChatRow.Events).steps.map { it.text })
        assertEquals(listOf("O-1", "O-2"), (rows[4] as ChatRow.Outputs).outputs.map { it.output.ref })
        // Nothing is lost: every step and result is in a row.
        assertEquals(5, rows.filterIsInstance<ChatRow.Events>().sumOf { it.steps.size })
        assertEquals(3, rows.filterIsInstance<ChatRow.Outputs>().sumOf { it.outputs.size })
        // A row keeps its key as more lines join it (the list does not jump), and keys never collide.
        assertEquals(rows[3].key, chatRows(e.take(7)).last { it is ChatRow.Events }.key)
        assertEquals(rows.size, rows.map { it.key }.toSet().size)
        assertTrue(chatRows(emptyList()).isEmpty())
    }

    @Test
    fun aRealSessionReadsInOrder() {
        // The timeline of a report with a talk: the hub's own steps and its two results between the CEO's answer and nothing after.
        val report = OrderReport(
            ref = "F-0100",
            steps = listOf(
                ReportStep(at = "2026-11-08T05:34:00Z", whoFa = "سامانه", whatFa = "جواب آمد (O-000122-): نکته‌ها"),
                ReportStep(at = "2026-11-08T05:36:00Z", whoFa = "سامانه", whatFa = "خروجی رسید: متن ریلز"),
                ReportStep(at = "2026-11-08T05:37:00Z", whoFa = "سامانه", whatFa = "خروجی رسید: کاور"),
                ReportStep(at = "2026-11-08T05:40:00Z", whoFa = "سامانه", whatFa = "کار W-000412 شروع شد"),
            ),
            outputs = listOf(ReportOutput("O-000123", "متن ریلز", "reel"), ReportOutput("O-000124", "کاور", "other")),
        )
        val turns = listOf(TalkTurn(id = JsonPrimitive("T-1"), n = 1, by = "ceo@PC", showMd = "سلام", at = "2026-11-08T05:30:00Z"))
        val rows = chatRows(sessionTimeline(turns, report, hasTalk = true))
        assertEquals(listOf("Turn", "Events", "Outputs"), rows.map { it::class.simpleName })
        val ev = rows[1] as ChatRow.Events
        assertEquals(listOf("جواب آمد: نکته‌ها", "کار شروع شد"), ev.steps.map { quietLine(it.text) })
        assertEquals("05:34–05:40", eventsSpan(ev.steps) { it.substring(11, 16) })
        assertEquals("۲ خروجی تحویل شد", outputsFa((rows[2] as ChatRow.Outputs).outputs.map { it.output }))
    }

    @Test
    fun noRefIsAWord() {
        assertEquals("جواب آمد: نکته‌های مدیر رسانه", quietLine("جواب آمد (O-000122-): نکته‌های مدیر رسانه"))
        assertEquals("جواب آمد: نکته‌ها", quietLine("جواب آمد (O-000122): نکته‌ها"))
        assertEquals("صداگذاری منتظر بودجه ماند", quietLine("صداگذاری منتظر بودجه ماند (W-000413)"))
        assertEquals("کار ساخته شد", quietLine("W-000310 ساخته شد"))
        assertEquals("خروجی رسید", quietLine("O-000122- رسید"))
        assertEquals("کار «ریلز آزمایشی» شروع شد", quietLine("کار W-000412 «ریلز آزمایشی» شروع شد"))
        // Markdown and breaks out; figures and Latin words stay.
        assertEquals("سایت pro-chart.com را خواند و GPT 5.5 جواب داد", quietLine("**سایت** pro-chart.com را خواند\nو GPT 5.5 جواب داد"))
    }

    @Test
    fun countsArePersianAndTimesAreFigures() {
        assertEquals("۳ رویداد", eventsCountFa(3))
        assertEquals("۱۲ رویداد", eventsCountFa(12))
        assertEquals("۲ گیر", blockersFa(2))
        assertEquals("ریلز تحویل شد", outputsFa(listOf(ReportOutput("O-1", "t", "reel"))))
        assertEquals("۱۰ خروجی تحویل شد", outputsFa((1..10).map { ReportOutput("O-$it", "t", "other") }))
        val clock: (String) -> String = { it }
        assertEquals("05:34", eventsSpan(listOf(step("a", "05:34"), step("b", "05:34")), clock))
        assertEquals("05:34–05:40", eventsSpan(listOf(step("a", "05:34"), step("b", ""), step("c", "05:40")), clock))
        assertEquals("", eventsSpan(listOf(step("a", "")), clock))
    }
}
