package com.coinepro.hq

import com.coinepro.hq.core.data.DayRow
import com.coinepro.hq.core.data.JDate
import com.coinepro.hq.core.data.allTexts
import com.coinepro.hq.core.data.cellCountFa
import com.coinepro.hq.core.data.checkDraft
import com.coinepro.hq.core.data.countdownFa
import com.coinepro.hq.core.data.dayRows
import com.coinepro.hq.core.data.draftChanges
import com.coinepro.hq.core.data.flowDraftOf
import com.coinepro.hq.core.data.foldSearch
import com.coinepro.hq.core.data.fromJalali
import com.coinepro.hq.core.data.hitRange
import com.coinepro.hq.core.data.hoursLineFa
import com.coinepro.hq.core.data.jMonthLength
import com.coinepro.hq.core.data.monthGrid
import com.coinepro.hq.core.data.nextMonth
import com.coinepro.hq.core.data.patchBody
import com.coinepro.hq.core.data.toJalali
import com.coinepro.hq.core.data.weekOfRound
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.FlowDef
import com.coinepro.hq.core.net.FlowDefSchedule
import com.coinepro.hq.core.net.FlowOptions
import com.coinepro.hq.core.net.ModelOption
import com.coinepro.hq.core.net.PlannedItem
import com.coinepro.hq.core.net.PubCalendarDay
import com.coinepro.hq.core.net.Publication
import com.coinepro.hq.core.net.PublicationCard
import com.coinepro.hq.core.net.PublishToday
import java.time.Instant
import java.time.LocalDate
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** ⟨1.39⟩ Contracts §60 and §61: the centre's day, the Jalali month, the search's hit, the editor's checks, a save's words and body. */
class PublishFlowsTest {
    private fun iso(tehran: String) = java.time.LocalDateTime.parse(tehran).atZone(java.time.ZoneId.of("Asia/Tehran")).toInstant().toString()

    @Test
    fun jalaliMatchesTheOwnersCalendar() {
        assertEquals(JDate(1405, 8, 26), toJalali(LocalDate.of(2026, 11, 17)))
        assertEquals(JDate(1405, 1, 1), toJalali(LocalDate.of(2026, 3, 21)))
        assertEquals(JDate(1404, 12, 29), toJalali(LocalDate.of(2026, 3, 20)))
        assertEquals(LocalDate.of(2026, 10, 23), fromJalali(JDate(1405, 8, 1)))
        for (d in 0L..800L) { val g = LocalDate.of(2025, 1, 1).plusDays(d); assertEquals(g, fromJalali(toJalali(g))) }
        assertEquals(31, jMonthLength(1405, 6)); assertEquals(30, jMonthLength(1405, 8)); assertEquals(29, jMonthLength(1405, 12))
        assertEquals(JDate(1406, 1, 1), nextMonth(JDate(1405, 12, 5), 1)); assertEquals(JDate(1404, 12, 1), nextMonth(JDate(1405, 1, 9), -1))
    }

    @Test
    fun theMonthStartsOnSaturdayAndCountsItsDays() {
        // 1 Aban 1405 is a Friday: six empty cells before it, the last column
        val today = LocalDate.of(2026, 11, 17)
        val days = listOf(
            PubCalendarDay("2026-11-17", published = 6, scheduled = 19, held = 1, planned = 4),
            PubCalendarDay("2026-11-18", planned = 30),
            PubCalendarDay("2026-11-16", published = 13),
        )
        val g = monthGrid(JDate(1405, 8, 1), days, today)
        assertTrue(g.all { it.size == 7 })
        assertEquals(6, g[0].count { it == null })
        assertEquals(1, g[0][6]!!.j.d)
        val all = g.flatten().filterNotNull()
        assertEquals(30, all.size)
        val t = all.first { it.today }
        assertEquals(26, t.j.d)
        assertEquals("۶ از ۳۰", cellCountFa(t))
        assertEquals("۳۰", cellCountFa(all.first { it.j.d == 27 }))
        assertEquals("۱۳", cellCountFa(all.first { it.j.d == 25 }))
        assertNull(cellCountFa(all.first { it.j.d == 2 }))
    }

    @Test
    fun theDayIsInItsHoursWithNowBetween() {
        val now = Instant.parse(iso("2026-11-17T11:40:00")).toEpochMilli()
        val today = PublishToday(
            day = "2026-11-17",
            items = listOf(
                PublicationCard(ref = "P-2", account = "zaribsad", state = "scheduled", at = iso("2026-11-17T12:00:00")),
                PublicationCard(ref = "P-1", account = "theprochart", state = "published", at = iso("2026-11-17T09:30:00")),
                PublicationCard(ref = "P-9", account = "dotcoin.me", state = "scheduled", at = iso("2026-11-18T09:00:00")),
            ),
            planned = listOf(PlannedItem(automation = "AF-0004", account = "zaribsad", buildAt = iso("2026-11-17T14:00:00"), publishAt = iso("2026-11-17T19:00:00"))),
        )
        val rows = dayRows(today, now)
        assertEquals(listOf("P-1", "now", "P-2", "AF-0004"), rows.map { when (it) { is DayRow.Item -> it.card.ref; is DayRow.Plan -> it.plan.automation; is DayRow.Now -> "now" } })
        assertEquals(11 * 60 + 40, (rows[1] as DayRow.Now).minute)
        // one page only
        assertEquals(listOf("now", "P-2", "AF-0004"), dayRows(today, now, "zaribsad").map { when (it) { is DayRow.Item -> it.card.ref; is DayRow.Plan -> it.plan.automation; is DayRow.Now -> "now" } })
        assertEquals("۲۰ دقیقه", countdownFa(iso("2026-11-17T12:00:00"), now))
        assertEquals("۱ ساعت و ۲۰ دقیقه", countdownFa(iso("2026-11-17T13:00:00"), now))
        assertNull(countdownFa(iso("2026-11-17T09:30:00"), now))
    }

    @Test
    fun aSearchHitIsFoundTheHubsWay() {
        assertEquals(foldSearch("بلاک‌چین"), foldSearch("بلاکچین"))
        assertEquals(foldSearch("بلاک چین"), foldSearch("بلاكچين"))
        val t = "زی‌کش؛ حریم خصوصی در بلاک‌چین"
        val r = hitRange(t, "بلاکچین")!!
        assertEquals("بلاک‌چین", t.substring(r.first, r.last + 1))
        assertNull(hitRange("کیف پول سرد", "بلاکچین"))
    }

    @Test
    fun copyAllHoldsEveryText() {
        val p = Api.json.decodeFromString(Publication.serializer(), """{"ref":"P-1","caption":"کپشن","story_word":"سرد","comment":{"keywords":["زی‌کش","zcash"],"reply":"سلام","buttons":[{"title":"WEEX","url":"https://weex.com"}],"public_replies":["اول","دوم"]}}""")
        val all = allTexts(p)
        for (part in listOf("کپشن", "زی‌کش، zcash", "دایرکت: سلام", "• WEEX: https://weex.com", "1. اول", "2. دوم", "کلمه‌ی ریپلای: سرد")) assertTrue(part, part in all)
    }

    private val options = FlowOptions(models = listOf(ModelOption("claude-opus-5-5", "Opus 5.5", listOf("high", "xhigh", "max"))))
    private val prochart = FlowDef(
        ref = "AF-0001", kind = "reel", account = "theprochart", model = "claude-opus-5-5", effort = "xhigh", version = 3,
        schedule = FlowDefSchedule(hours = listOf("09:30", "14:00", "19:30", null), bestWeek = true, triggerAt = "00:30", sameDay = true, start = "2026-11-14"),
        budget = com.coinepro.hq.core.net.FlowDefBudget(usdCap = 10.0),
    )

    @Test
    fun theRoundAndTheHoursLine() {
        assertEquals(0, weekOfRound(prochart.schedule, LocalDate.of(2026, 11, 17)))
        assertEquals(1, weekOfRound(prochart.schedule, LocalDate.of(2026, 11, 21)))
        assertEquals(3, weekOfRound(prochart.schedule, LocalDate.of(2026, 12, 5)))
        assertEquals(0, weekOfRound(prochart.schedule, LocalDate.of(2026, 12, 12)))
        assertEquals("دور ۴ هفته: ۰۹:۳۰ · ۱۴:۰۰ · ۱۹:۳۰ · پربازدیدترین", hoursLineFa(prochart))
        assertEquals("هر روز ۱۳:۰۰", hoursLineFa(prochart.copy(schedule = prochart.schedule.copy(hours = listOf("13:00", "13:00")))))
        assertEquals("۳ استوری · ۱۰:۰۰ تا ۲۱:۰۰", hoursLineFa(prochart.copy(kind = "stories", schedule = prochart.schedule.copy(stories = listOf("16:30", "10:00", "21:00")))))
    }

    @Test
    fun theEditorChecksAsTheHubDoes() {
        val base = flowDraftOf(prochart)
        assertTrue(checkDraft(base, "reel", options).isEmpty())
        // a bad hour, too close to the build's start, a cap out of its range, an unknown effort
        val bad = base.copy(hours = listOf("9:3", "01:30", "19:30", null), usdCap = 501.0, effort = "ultra")
        val e = checkDraft(bad, "reel", options).associate { it.field to it.messageFa }
        assertEquals("ساعت باید به شکل ۱۴:۰۰ باشد", e["hours.0"])
        assertEquals("هر ساعت انتشار باید دست‌کم ۹۰ دقیقه بعد از شروع ساخت باشد", e["hours.1"])
        assertTrue(e.getValue("usd_cap").contains("۵۰۰"))
        assertTrue("effort" in e)
        // stories: sixteen, two the same, one on a reel's minute
        val s = base.copy(stories = (0 until 16).map { "%02d:00".format(8 + it % 14) })
        val se = checkDraft(s, "stories", options).associate { it.field to it.messageFa }
        assertEquals("حداکثر ۱۵ استوری", se["stories"])
        assertTrue(se.keys.any { it.startsWith("stories.") })
        val reel = checkDraft(base.copy(stories = listOf("10:00", "13:00")), "stories", options, reels = listOf("13:00")).associate { it.field to it.messageFa }
        assertEquals("این ساعت با ریلز ۱۳:۰۰ همین پیج هم‌دقیقه است", reel["stories.1"])
        assertEquals("دست‌کم یک روز هفته", checkDraft(base.copy(days = emptyList()), "reel", options).single().messageFa)
    }

    @Test
    fun aSaveSaysWhatChangesAndSendsOnlyThat() {
        val before = flowDraftOf(prochart)
        val after = before.copy(hours = listOf("10:00", "14:00", "19:30", null), usdCap = 15.0)
        val ch = draftChanges(before, after)
        assertEquals(listOf("ساعت انتشار · هفته‌ی ۱", "هشدار هزینه‌ی روز"), ch.map { it.labelFa })
        assertEquals("۰۹:۳۰", ch[0].beforeFa); assertEquals("۱۰:۰۰", ch[0].afterFa)
        assertEquals("$10", ch[1].beforeFa); assertEquals("$15", ch[1].afterFa)
        val body: JsonObject = patchBody(before, after, "ساعت بهتر")
        assertEquals(setOf("schedule", "usd_cap", "note_change_fa"), body.keys)
        assertEquals(setOf("hours"), body["schedule"]!!.jsonObject.keys)
        assertEquals("10:00", body["schedule"]!!.jsonObject["hours"]!!.jsonArray[0].jsonPrimitive.content)
        assertEquals("null", body["schedule"]!!.jsonObject["hours"]!!.jsonArray[3].toString())
        assertTrue(draftChanges(before, before).isEmpty())
        assertFalse("schedule" in patchBody(before, before.copy(model = "claude-fable-5-2")))
    }

    @Test
    fun theHubsShapesRead() {
        val f = Api.json.decodeFromString(FlowDef.serializer(), """{"ref":"AF-0004","key":"zaribsad_coin","schedule":{"hours":["19:00",null],"best_week":false,"days":[0,1,2],"stories":[],"trigger_at":"14:00","same_day":true,"start":"2026-11-14","when_fa":""},"budget":{"usd_cap":100,"month_estimate_usd":3000,"envelope_usd":null,"envelope_left_usd":null,"over_envelope":false},"version":2,"legacy_ref":"N8:zaribsad_coin","health":{"state":"warn","note_fa":"x"},"alerts_open":1}""")
        assertEquals(listOf("19:00", null), f.schedule.hours)
        assertEquals(100.0, f.budget.usdCap, 0.0)
        assertEquals("N8:zaribsad_coin", f.legacyRef)
        val p = Api.json.decodeFromString(PublishToday.serializer(), """{"day":"2026-11-17","items":[{"ref":"P-1","set":{"n":12,"done":3,"next_at":null}}],"planned":[],"next":null,"counts":{"published":6,"scheduled":19,"held":1,"failed":0}}""")
        assertEquals(12, p.items.single().set!!.n)
        assertEquals(19, p.counts.scheduled)
    }
}
