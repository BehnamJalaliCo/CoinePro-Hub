package com.coinepro.hq

import com.coinepro.hq.core.data.channelFa
import com.coinepro.hq.core.data.dailyHour
import com.coinepro.hq.core.data.deskArchivedFa
import com.coinepro.hq.core.data.deskChannels
import com.coinepro.hq.core.data.deskOf
import com.coinepro.hq.core.data.groupFlowFa
import com.coinepro.hq.core.data.latestOutputFa
import com.coinepro.hq.core.data.playbookKept
import com.coinepro.hq.core.data.questionFirstLine
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.DeskCard
import com.coinepro.hq.core.net.MemberPublish
import com.coinepro.hq.core.net.Playbook
import com.coinepro.hq.core.net.PlaybookRoutine
import com.coinepro.hq.core.net.PublishDesk
import com.coinepro.hq.core.net.SessionCard
import com.coinepro.hq.ui.v32.ComposerDrafts
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ⟨1.36⟩ Contract §58: the question folded to its first line and the newest output's chip; the draft kept per session; a closed
 * session's working group read leniently wherever the hub says it; a published card's package «بایگانی شد · … آزاد شد»; the desk by
 * channel, Instagram first; and a working group's day in one line («هر روز 09:00: ساخت ← انتشار خودکار ← اینستاگرام»).
 */
class RoomTest {
    @Test
    fun theQuestionFoldsToItsFirstLineAndNamesTheNewestOutput() {
        assertEquals("نسخه‌ی اول آماده است.", questionFirstLine("\n  نسخه‌ی اول آماده است.\nیک: شروع با سؤال؟"))
        assertEquals("", questionFirstLine("  \n "))
        assertEquals("خروجی آخر: ریلز: حد ضرر را کجا بگذاریم", latestOutputFa("ریلز: حد ضرر را کجا بگذاریم (O-000967)"))
        assertEquals("خروجی آخر: بی‌عنوان", latestOutputFa(" "))
    }

    @Test
    fun aDraftIsKeptPerSessionUntilItGoes() {
        ComposerDrafts.put("session:F-1", "با سؤال شروع کن")
        ComposerDrafts.put("session:F-2", "دیگری")
        assertEquals("با سؤال شروع کن", ComposerDrafts.get("session:F-1"))
        ComposerDrafts.put("session:F-1", "")
        assertNull(ComposerDrafts.get("session:F-1"))
        assertEquals("دیگری", ComposerDrafts.get("session:F-2"))
    }

    @Test
    fun aClosedSessionsWorkingGroupIsReadLeniently() {
        fun card(extra: String) = Api.json.decodeFromString(SessionCard.serializer(), """{"ref":"F-1","badge":"closed","closed_at":"2026-11-13T08:00:00Z"$extra}""")
        // the hub writes the playbook's ref (and its own line); true reads the same
        assertTrue(card(""","playbook_kept":"PB-0007","playbook_kept_fa":"کارگروه این جلسه در کتابخانه ماند"""").let { playbookKept(it.playbookKept, it.playbook) })
        assertEquals("PB-0007", card(""","playbook_kept":"PB-0007"""").let { com.coinepro.hq.core.data.keptPlaybookRef(it.playbookKept, it.playbook) })
        assertEquals("کارگروه این جلسه در کتابخانه ماند", card(""","playbook_kept_fa":"کارگروه این جلسه در کتابخانه ماند"""").playbookKeptFa)
        assertTrue(card(""","playbook_kept":true""").let { playbookKept(it.playbookKept, it.playbook) })
        assertNull(card(""","playbook_kept":true""").let { com.coinepro.hq.core.data.keptPlaybookRef(it.playbookKept, it.playbook) })
        assertTrue(card(""","playbook_kept":"true"""").let { playbookKept(it.playbookKept, it.playbook) })
        assertTrue(card(""","playbook":"PB-0007"""").let { playbookKept(it.playbookKept, it.playbook) })
        assertTrue(card(""","playbook":{"ref":"PB-0007","state":"draft"}""").let { playbookKept(it.playbookKept, it.playbook) })
        assertFalse(card(""","playbook_kept":false,"playbook":null""").let { playbookKept(it.playbookKept, it.playbook) })
        assertFalse(card("").let { playbookKept(it.playbookKept, it.playbook) })
    }

    private fun desk(json: String) = Api.json.decodeFromString(DeskCard.serializer(), """{"output":"O-1","channel":"instagram","state":"published"$json}""")

    @Test
    fun aPublishedPackageSaysWhatWasKeptAndWhatWasFreed() {
        assertNull(deskArchivedFa(desk("")))
        assertEquals("بایگانی شد", deskArchivedFa(desk(""","archived":true""")))
        assertEquals("بایگانی شد · 142 MB آزاد شد", deskArchivedFa(desk(""","archived":true,"freed_bytes":148897792""")))
        assertEquals("بایگانی شد · 5.0 MB آزاد شد", deskArchivedFa(desk(""","archived":{"ref":"AR-1","freed_bytes":"5242880"}""")))
        assertEquals("بایگانی شد", deskArchivedFa(desk(""","archived":"AR-1","freed_bytes":0""")))
        assertNull(deskArchivedFa(desk(""","archived":false""")))
    }

    @Test
    fun theDeskIsByChannelInstagramFirst() {
        val ig = DeskCard("O-1", channel = "instagram")
        val yt = DeskCard("O-2", channel = "youtube")
        val d = PublishDesk(ready = listOf(yt, ig), done = listOf(DeskCard("O-3", channel = "")))
        assertEquals(listOf("instagram", "youtube"), deskChannels(d))
        assertEquals(listOf("instagram"), deskChannels(PublishDesk()))
        assertEquals(listOf("O-1"), deskOf(d, "instagram").ready.map { it.output })
        assertEquals(listOf("O-3"), deskOf(d, "instagram").done.map { it.output })
        assertEquals(listOf("O-2"), deskOf(d, "youtube").ready.map { it.output })
        assertEquals(listOf("اینستاگرام", "یوتیوب", "tiktok"), listOf("instagram", "YouTube", "tiktok").map(::channelFa))
    }

    @Test
    fun aWorkingGroupsDayIsOneLine() {
        assertEquals("09:00", dailyHour("FREQ=DAILY;BYHOUR=11,9;BYMINUTE=0"))
        assertNull(dailyHour("FREQ=WEEKLY;BYDAY=FR;BYHOUR=20"))
        assertNull(dailyHour("FREQ=DAILY;INTERVAL=2;BYHOUR=9"))
        fun r(key: String, rule: String) = PlaybookRoutine(key = key, schedule = rule)
        val pb = Playbook("PB-1", platform = "instagram", state = "sealed", routines = listOf(r("cover", "FREQ=DAILY;BYHOUR=11;BYMINUTE=0"), r("topic", "FREQ=DAILY;BYHOUR=9;BYMINUTE=0")))
        assertEquals("هر روز 09:00: ساخت ← انتشار خودکار ← اینستاگرام", groupFlowFa(pb, MemberPublish(mode = "auto")))
        assertEquals("هر روز 09:00: ساخت ← تأیید تو ← اینستاگرام", groupFlowFa(pb, MemberPublish()))
        // no daily routine: the publish hour, else the first routine's own time
        assertEquals("هر روز 18:30: ساخت ← تأیید تو ← اینستاگرام", groupFlowFa(pb.copy(routines = emptyList()), MemberPublish(at = "18:30")))
        assertTrue(groupFlowFa(pb.copy(routines = listOf(r("weekly", "FREQ=WEEKLY;BYDAY=FR;BYHOUR=20;BYMINUTE=0"))), MemberPublish())!!.startsWith("هر جمعه"))
        assertNull(groupFlowFa(pb.copy(platform = "site"), MemberPublish(mode = "auto")))
    }
}
