package com.coinepro.hq

import com.coinepro.hq.core.data.calendarWeek
import com.coinepro.hq.core.data.capsRaised
import com.coinepro.hq.core.data.promptVariables
import com.coinepro.hq.core.data.scheduleFa
import com.coinepro.hq.core.data.settingFrom
import com.coinepro.hq.core.data.variablesIn
import com.coinepro.hq.core.data.withVariable
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Asset
import com.coinepro.hq.core.net.LineCalendar
import com.coinepro.hq.core.net.Line
import com.coinepro.hq.core.net.LineCaps
import com.coinepro.hq.core.net.LineRun
import com.coinepro.hq.core.net.StepDef
import com.coinepro.hq.core.net.Template
import com.coinepro.hq.core.net.Voice
import java.time.LocalDate
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Contract §30 ⟨1.12⟩: the shapes the lines' screens read, and the small rules they share (schedule words, prompt variables, caps). */
class V30Test {
    @Test
    fun aTemplateAndALineDecodeWithTheirSteps() {
        val t = Api.json.decodeFromString(Template.serializer(), """
            {"key":"instagram_reel","title_fa":"ریل","platform":"instagram_reel","version":2,"outputs_fa":"x",
             "steps":[{"key":"script","kind":"gpt_text","title_fa":"فیلمنامه","prompt_fa":"بنویس","settings":{},"inputs":[],"gate":"auto","optional":false,"enabled":true,"max_attempts":2,"timeout_s":90},
                      {"key":"voice","kind":"tts","title_fa":"صدا","prompt_fa":null,"settings":{"speaker":"Kore"},"inputs":["script"],"gate":"owner","optional":true,"enabled":false,"max_attempts":1,"timeout_s":60}],
             "defaults":{"auto_after":7},"new_field":1}
        """.trimIndent())
        assertEquals(2, t.steps.size)
        assertEquals("owner", t.steps[1].gate)
        assertNull(t.steps[1].promptFa)
        assertFalse(t.steps[1].enabled)
        val l = Api.json.decodeFromString(Line.serializer(), """
            {"ref":"LN-0001","company":"TY","template":"instagram_reel","template_version":2,"platform":"instagram_reel","channel":{"kind":"instagram","subject":"tradeyar"},
             "title_fa":"ریلز","schedule":"FREQ=DAILY;BYHOUR=9","state":"on","mode":"draft","good_runs":4,"auto_after":7,
             "caps":{"runs_per_day":3,"tokens_per_run":120000,"opus_per_day":4},"version":3,"steps":[],"library":["AS-0001"],"created_at":"2026-11-04T08:00:00Z","updated_at":"2026-11-04T08:00:00Z"}
        """.trimIndent())
        assertEquals(120_000L, l.caps.tokensPerRun)
        assertEquals(listOf("AS-0001"), l.library)
        assertNull(l.lastRun)
    }

    @Test
    fun aRunDecodesWithEveryKindOfOutput() {
        val r = Api.json.decodeFromString(LineRun.serializer(), """
            {"ref":"LR-000003","line":"LN-0001","line_version":3,"trigger":"schedule","dry":false,"state":"waiting","at":"2026-11-04T08:00:00Z","ended_at":null,
             "steps":[{"key":"script","kind":"gpt_text","state":"done","attempt":1,"started_at":"2026-11-04T08:00:00Z","ended_at":"2026-11-04T08:00:40Z",
                       "output":{"text":"متن","file_id":null,"files":[],"data":{}},"via":"x","tokens":1800,"usd_equiv":"0.04","error_fa":null},
                      {"key":"voice","kind":"tts","state":"done","output":{"file_id":"f1","files":["f1","f2"],"data":{"a":1}},"tokens":0,"usd_equiv":0.5},
                      {"key":"publish","kind":"publish","state":"waiting"}],
             "cost":{"tokens":21000,"usd_equiv":"0.61"},"published":[{"platform":"instagram_reel","kind":"reel","external_id":null,"at":null,"url":null}],
             "metrics":{"h24":{"views":10},"d7":null},"note_fa":""}
        """.trimIndent())
        assertEquals("waiting", r.state)
        assertEquals(listOf("f1", "f2"), r.steps[1].output.allFiles)
        assertEquals("0.5", r.steps[1].usdEquiv?.content)
        assertTrue(r.steps[2].output.isEmpty)
        assertEquals("متن", r.steps[0].output.text)
        assertNull(r.metrics.d7)
    }

    @Test
    fun theLibraryTheVoicesAndTheCalendarDecode() {
        val a = Api.json.decodeFromString(Asset.serializer(), """{"id":"AS-0001","company":null,"kind":"cover_folder","title_fa":"کاور","config":{},"files":["f1"],"created_at":"2026-11-01T00:00:00Z"}""")
        assertNull(a.company)
        val v = Api.json.decodeFromString(Voice.serializer(), """{"name":"Kore","title_fa":"کوره","gender":"female","sample_file":null}""")
        assertNull(v.sampleFile)
        val c = Api.json.decodeFromString(LineCalendar.serializer(), """{"days":[{"day":"2026-11-04","items":[{"line":"LN-0001","company":"TY","platform":"instagram_reel","at":"2026-11-04T14:30:00Z","state":"scheduled","run":null}]}]}""")
        assertEquals("scheduled", c.days.single().items.single().state)
    }

    @Test
    fun scheduleWordsPromptVariablesAndCaps() {
        assertEquals("هر روز ساعت 09:00", scheduleFa("FREQ=DAILY;BYHOUR=9;BYMINUTE=0"))
        assertEquals("هر شنبه و سه‌شنبه ساعت 18:30", scheduleFa("FREQ=WEEKLY;BYDAY=SA,TU;BYHOUR=18;BYMINUTE=30"))
        assertEquals("بدون برنامه", scheduleFa(null))
        val steps = listOf(StepDef("a", "gpt_text"), StepDef("b", "tts", inputs = listOf("a")), StepDef("c", "render", inputs = listOf("b")))
        assertEquals(listOf("b", "a"), promptVariables(steps, 2))
        assertEquals(listOf("a", "b"), variablesIn("از {{a}} و {{ b }} و {{a}}"))
        assertEquals("متن {{a}}", withVariable("متن", "a"))
        assertTrue(capsRaised(LineCaps(3, 100, 2), LineCaps(4, 100, 2)))
        assertFalse(capsRaised(LineCaps(3, 100, 2), LineCaps(2, 50, null)))
        assertEquals(5L, (settingFrom("5", JsonPrimitive(1)) as JsonPrimitive).content.toLong())
    }

    @Test
    fun theCalendarWeekRunsFromSaturdayToFriday() {
        // 2026-11-04 is a Wednesday: its week began on Saturday the 31st of October.
        assertEquals("2026-10-31" to "2026-11-06", calendarWeek(0, LocalDate.parse("2026-11-04")))
        assertEquals("2026-11-07" to "2026-11-13", calendarWeek(1, LocalDate.parse("2026-11-04")))
        assertEquals("2026-10-31" to "2026-11-06", calendarWeek(0, LocalDate.parse("2026-10-31")))
    }
}
