package com.coinepro.hq

import com.coinepro.hq.core.data.SYSTEM_FA
import com.coinepro.hq.core.data.SessionEntry
import com.coinepro.hq.core.data.isStepTurn
import com.coinepro.hq.core.data.oneLine
import com.coinepro.hq.core.data.sessionStatusLine
import com.coinepro.hq.core.data.sessionTimeline
import com.coinepro.hq.core.data.stepWithSpeaker
import com.coinepro.hq.core.net.Blocker
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.OrderTurn
import com.coinepro.hq.core.net.ReportOutput
import com.coinepro.hq.core.net.ReportStep
import com.coinepro.hq.core.net.SessionBrief
import com.coinepro.hq.core.net.SessionState
import com.coinepro.hq.core.net.TalkCard
import com.coinepro.hq.core.net.TalkTurn
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** ⟨0.17.0⟩ The session as a chat: the steps of the work as quiet lines in the timeline at their time, each result a card at its time,
 *  and the one status line of the compact head. */
class SessionChatTest {
    private fun turn(n: Int, by: String, text: String, at: String, source: String = "typed", cards: List<TalkCard> = emptyList(), files: List<FileRef> = emptyList()) =
        TalkTurn(id = JsonPrimitive("T-$n"), n = n, by = by, source = source, text = if (by == "owner") text else "", showMd = if (by == "owner") null else text, at = at, cards = cards, files = files)

    @Test
    fun aStepTheHubWroteIsAQuietLineButAQuestionAHelloOrACardIsNot() {
        assertTrue(isStepTurn(turn(1, "ceo@TY", "سه ریلز ساخته شد.", "2026-11-06T08:00:00Z", source = "system")))
        assertTrue(isStepTurn(turn(2, "media@TY", "مدیر رسانه آمد.", "2026-11-06T08:00:00Z", source = "system")))
        // The owner, a model's answer, the holder's question and hello, a turn with a card or files: bubbles.
        assertFalse(isStepTurn(turn(3, "owner", "خوب است", "2026-11-06T08:00:00Z", source = "system")))
        assertFalse(isStepTurn(turn(4, "ceo@TY", "شنیدم", "2026-11-06T08:00:00Z")))
        assertFalse(isStepTurn(turn(5, "ceo@TY", "**سؤال از شما** · اول کدام؟", "2026-11-06T08:00:00Z", source = "system")))
        assertFalse(isStepTurn(turn(6, "ceo@TY", "سلام، مدیرعامل تریدیار هستم و این فرمان با من است.", "2026-11-06T08:00:00Z", source = "system")))
        assertFalse(isStepTurn(turn(7, "ceo@TY", "استخدام لازم است", "2026-11-06T08:00:00Z", source = "system", cards = listOf(TalkCard(kind = "hire")))))
        assertFalse(isStepTurn(turn(8, "ceo@TY", "", "2026-11-06T08:00:00Z", source = "system")))
    }

    @Test
    fun aQuietLineNamesWhoDidItUnlessItAlreadyNamesSomeone() {
        assertEquals("مدیر رسانه: سه ریلز ساخته شد.", stepWithSpeaker("سه ریلز ساخته شد.", "مدیر رسانه"))
        assertEquals("مدیر رسانه آمد.", stepWithSpeaker("مدیر رسانه آمد.", "مدیر رسانه"))
        assertEquals("حسابدار: عددها خوانده شد", stepWithSpeaker("حسابدار: عددها خوانده شد", "مدیرعامل تریدیار"))
        assertEquals("به مدیر رسانه سپرده شد", stepWithSpeaker("به مدیر رسانه سپرده شد", null))
    }

    @Test
    fun oneLineHasNoMarksAndNoBreaks() {
        assertEquals("مدیر رسانه: سه ریلز ساخته شد و دو پست مانده", oneLine("**مدیر رسانه:** سه ریلز ساخته شد\n\nو دو پست مانده"))
    }

    @Test
    fun theTimelineInterleavesTheHubsStepsAndTheResultsAtTheirTime() {
        val turns = listOf(
            turn(1, "advisor", "سلام. گزارش را مینویسم.", "2026-11-06T06:00:00Z"),
            turn(2, "advisor", "عددها خوانده شد.", "2026-11-06T07:00:00Z", source = "system"),
            turn(3, "owner", "خوب است", "2026-11-06T07:30:00Z"),
            turn(4, "advisor", "گزارش آماده است.", "2026-11-06T08:10:00Z"),
        )
        val r = OrderReport(
            ref = "F-1",
            steps = listOf(
                // The holder's own step: the talk heard it already (as turn 2), so it is not drawn twice.
                ReportStep("2026-11-06T07:00:00Z", "مشاور کل", "عددها خوانده شد."),
                ReportStep("2026-11-06T06:30:00Z", SYSTEM_FA, "به حسابدار سپرده شد"),
                ReportStep("2026-11-06T08:00:00Z", SYSTEM_FA, "خروجی رسید: گزارش سه‌ماهه"),
            ),
            outputs = listOf(ReportOutput("O-1", "گزارش سه‌ماهه", "report"), ReportOutput("O-2", "پیوست", "other")),
        )
        val e = sessionTimeline(turns, r, hasTalk = true)
        assertEquals(
            listOf("t-T-1-1", "sr", "st-T-2-2", "t-T-3-3", "o-O-1", "t-T-4-4", "o-O-2"),
            e.map { if (it.key.startsWith("sr-")) "sr" else it.key },
        )
        assertEquals("به حسابدار سپرده شد", (e[1] as SessionEntry.Step).text)
        assertEquals("advisor", (e[2] as SessionEntry.Step).by)
        assertEquals("2026-11-06T08:00:00Z", (e[4] as SessionEntry.Output).at)
        // A result whose arrival was never written goes to the end, with no time.
        assertEquals("", (e[6] as SessionEntry.Output).at)
        assertEquals(e.size, e.map { it.key }.toSet().size)
    }

    @Test
    fun withNoTalkYetEveryStepOfTheReportIsALineWithItsSpeaker() {
        val r = OrderReport(ref = "F-2", steps = listOf(ReportStep("2026-11-06T06:00:00Z", "مدیرعامل تریدیار", "فرمان را گرفت"), ReportStep("2026-11-06T06:10:00Z", SYSTEM_FA, "به مدیر رسانه سپرده شد")))
        val e = sessionTimeline(emptyList(), r, hasTalk = false).map { (it as SessionEntry.Step).text }
        assertEquals(listOf("مدیرعامل تریدیار: فرمان را گرفت", "به مدیر رسانه سپرده شد"), e)
    }

    @Test
    fun theHeadsLineSaysWhyItIsStuckWhatIsNeededOnHisTurnElseWhatIsHappening() {
        val brief = SessionBrief(doneFa = "برنامه نوشته شد.", nowFa = "دو پست در حال نوشتن است.", needFa = "بگو اول کدام.")
        val moving = OrderReport(ref = "F-1", brief = brief, session = SessionState(badge = "moving", reasonFa = "مدیر رسانه کار میکند."))
        assertEquals("دو پست در حال نوشتن است.", sessionStatusLine(moving))
        assertEquals("بگو اول کدام.", sessionStatusLine(moving.copy(session = SessionState(badge = "your_turn"), turn = OrderTurn(questionFa = "اول کدام؟"))))
        assertEquals("اول کدام؟", sessionStatusLine(moving.copy(brief = brief.copy(needFa = ""), session = SessionState(badge = "your_turn"), turn = OrderTurn(questionFa = "اول کدام؟"))))
        val stuck = moving.copy(session = SessionState(badge = "stuck", reasonFa = "کسی برای این کار نیست.\nاول استخدام."), blockers = listOf(Blocker("no_employee")))
        assertEquals("کسی برای این کار نیست. اول استخدام.", sessionStatusLine(stuck))
        assertEquals("مدیر رسانه کار میکند.", sessionStatusLine(moving.copy(brief = SessionBrief())))
    }
}
