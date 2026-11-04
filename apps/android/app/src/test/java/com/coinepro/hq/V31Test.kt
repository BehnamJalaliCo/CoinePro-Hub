package com.coinepro.hq

import com.coinepro.hq.core.data.rankMove
import com.coinepro.hq.core.data.competitorFigure
import com.coinepro.hq.core.data.competitorNewPages
import com.coinepro.hq.core.data.adFigures
import com.coinepro.hq.core.data.roasText
import com.coinepro.hq.core.data.ruleLineFa
import com.coinepro.hq.core.data.validCompanyCode
import com.coinepro.hq.core.net.Ads
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.GrowthAutomation
import com.coinepro.hq.core.net.Campaign
import com.coinepro.hq.core.net.CampaignItem
import com.coinepro.hq.core.net.CompetitorDaily
import com.coinepro.hq.core.net.Insights
import com.coinepro.hq.core.net.Kit
import com.coinepro.hq.core.net.KitPreview
import com.coinepro.hq.core.net.KitResult
import com.coinepro.hq.core.net.Newsletter
import com.coinepro.hq.core.net.RankDaily
import com.coinepro.hq.core.net.idText
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Contract §31 ⟨1.13⟩: the shapes the growth screens read (ids as numbers or strings, a field the hub leaves out) and the rules they share. */
class V31Test {
    @Test
    fun insightsAndKitsDecode() {
        val i = Api.json.decodeFromString(Insights.serializer(), """{"line":"LN-0001","metric":"views","window_runs":12,"best":{"hour":18,"length_bucket":"25-35","voice":null,"pattern_source":"p"},"top_hooks":["a"],"lessons_fa":["b","c"],"updated_at":"2026-11-03T05:40:00Z"}""")
        assertEquals(18, i.best.hour)
        assertNull(i.best.voice)
        assertEquals(2, i.lessonsFa.size)
        val k = Api.json.decodeFromString(Kit.serializer(), """{"key":"k","title_fa":"ک","purpose_fa":"x","team_template":"t","groups":["content"],"lines":[{"template":"instagram_reel","platform":"instagram_reel","title_fa":"ریلز"}],"kpis":["reach"],"connections":["instagram"],"defaults":{}}""")
        assertEquals("instagram_reel", k.lines.single().platform)
        // The preview and the result may leave any part out.
        assertTrue(Api.json.decodeFromString(KitPreview.serializer(), """{"preview_fa":"x"}""").todoFa.isEmpty())
        assertEquals(listOf("اینستاگرام را وصل کن"), Api.json.decodeFromString(KitResult.serializer(), """{"company":{"code":"NV","name_fa":"ن"},"todo_fa":["اینستاگرام را وصل کن"]}""").todoFa)
    }

    @Test
    fun theNewsletterReadsIdsAsNumbersOrStrings() {
        val n = Api.json.decodeFromString(Newsletter.serializer(), """{"lists":[{"id":1,"name":"a","subscribers":1840,"size_limit":2000}],"campaigns":[{"id":"12","list":1,"subject":"s","state":"scheduled","scheduled_at":"2026-11-07T04:00:00Z"}]}""")
        assertEquals("1", n.lists.single().id.idText)
        assertEquals("12", n.campaigns.single().id.idText)
        assertEquals("1", n.campaigns.single().list?.idText)
        assertNull(n.campaigns.single().subjectB)
    }

    @Test
    fun ranksCompetitorsAndAdFigures() {
        val ranks = listOf(
            RankDaily(keyword = kw(1), day = "2026-10-20", position = 14.0), RankDaily(keyword = kw(1), day = "2026-10-27", position = 12.0),
            RankDaily(keyword = kw(1), day = "2026-11-03", position = 9.0, source = "searxng"), RankDaily(keyword = kw(2), day = "2026-11-03", position = null),
        )
        val mv = rankMove(ranks, "1")
        assertEquals(9.0, mv.latest!!, 0.0)
        assertEquals(12.0, mv.before!!, 0.0)
        assertEquals(3, mv.up)
        assertTrue(mv.approximate)
        assertNull(rankMove(ranks, "2").latest)
        val daily = listOf(
            CompetitorDaily(kw(1), "2026-10-05", "followers", 20_000.0), CompetitorDaily(kw(1), "2026-11-03", "followers", 21_100.0),
            CompetitorDaily(kw(1), "2026-10-10", "new_pages", 3.0), CompetitorDaily(kw(1), "2026-10-20", "new_pages", 3.0),
        )
        assertEquals(21_100.0 to 1_100.0, competitorFigure(daily, "1", "followers"))
        assertNull(competitorFigure(daily, "1", "subscribers"))
        assertEquals(6.0, competitorNewPages(daily, "1"), 0.0)
        val ads = Api.json.decodeFromString(Ads.serializer(), """{"accounts":[{"company":"TY","platform":"google_ads","account_id":"1","state":"connected"}],"campaigns":[{"platform":"google_ads","id":"c-1","state":"paused","paused_reason_fa":"r","days":[{"platform":"google_ads","campaign_id":"c-1","day":"2026-11-01","spend":100,"clicks":10,"conversions":2,"revenue":260,"roas":2.6},{"platform":"google_ads","campaign_id":"c-1","day":"2026-11-02","spend":100,"clicks":12,"conversions":1,"revenue":100,"roas":null}]}]}""")
        val f = adFigures(ads.campaigns.single())
        assertEquals(1.8, f.roas!!, 0.0001)
        assertEquals("1.8×", roasText(f.roas))
        assertEquals("—", roasText(null))
    }

    @Test
    fun calendarCampaignsAndAutomations() {
        val x = Api.json.decodeFromString(CampaignItem.serializer(), """{"day":"2026-11-03","at":null,"company":"TY","kind":"campaign","ref":"CP-1","title_fa":"ک","platform":null,"state":"planned","conflict_fa":"تعطیل"}""")
        assertEquals("تعطیل", x.conflictFa)
        val c = Api.json.decodeFromString(Campaign.serializer(), """{"id":3,"company":"TY","title_fa":"ک","goal_fa":"","starts":"2026-11-05","ends":"2026-11-11","channels":["instagram_reel"],"budget":null,"state":"planned"}""")
        assertEquals("3", c.id.idText)
        assertNull(c.budget)
        val a = Api.json.decodeFromString(GrowthAutomation.serializer(), """{"ref":"AT-0001","company":null,"sentence_fa":"s","rule":{"trigger":{"kind":"schedule","rrule":"FREQ=DAILY;BYHOUR=9;BYMINUTE=0"},"conditions":[],"actions":[{"kind":"line.run","args":{}},{"kind":"notify.owner","args":{}}]},"state":"on","runs":2,"last_run_at":null,"n8n_workflow":null}""")
        assertEquals(2, a.runCount)
        assertTrue(a.runList.isEmpty())
        assertEquals("هر روز ساعت 09:00 › یک خط تولید را اجرا میکند و به تو خبر میدهد", ruleLineFa(a.rule))
        val one = Api.json.decodeFromString(GrowthAutomation.serializer(), """{"ref":"AT-0001","sentence_fa":"s","rule":{},"state":"proposed","runs":[{"at":"2026-11-01T06:30:00Z","state":"done","note_fa":"ok"}]}""")
        assertEquals(1, one.runCount)
        assertEquals("ok", one.runList.single().noteFa)
        assertTrue(a.rule.jsonObject.isNotEmpty())
    }

    @Test
    fun aCompanyCodeIsCapitalsAndDigits() {
        assertTrue(validCompanyCode("NV"))
        assertTrue(validCompanyCode("TY2"))
        assertFalse(validCompanyCode("n"))
        assertFalse(validCompanyCode("2X"))
        assertFalse(validCompanyCode("TOOLONGCODE1"))
    }

    private fun kw(n: Int) = kotlinx.serialization.json.JsonPrimitive(n)
}
