package com.coinepro.hq

import com.coinepro.hq.core.data.UseDraft
import com.coinepro.hq.core.data.boardGroups
import com.coinepro.hq.core.data.changeLineFa
import com.coinepro.hq.core.data.companiesLineFa
import com.coinepro.hq.core.data.dollarsOf
import com.coinepro.hq.core.data.dollarsText
import com.coinepro.hq.core.data.exportFileName
import com.coinepro.hq.core.data.healthLineFa
import com.coinepro.hq.core.data.libraryFiltered
import com.coinepro.hq.core.data.linksProblemsFa
import com.coinepro.hq.core.data.modelFa
import com.coinepro.hq.core.data.pathLinks
import com.coinepro.hq.core.data.poolFilled
import com.coinepro.hq.core.data.repliesBody
import com.coinepro.hq.core.data.replyProblemsFa
import com.coinepro.hq.core.data.resultsLineFa
import com.coinepro.hq.core.data.scheduleFa
import com.coinepro.hq.core.data.sectionKey
import com.coinepro.hq.core.data.statsLineFa
import com.coinepro.hq.core.data.stepToolFa
import com.coinepro.hq.core.data.useMissingFa
import com.coinepro.hq.core.data.utmLink
import com.coinepro.hq.core.data.versionsOf
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.BoardItem
import com.coinepro.hq.core.net.DmButton
import com.coinepro.hq.core.net.DmTemplate
import com.coinepro.hq.core.net.FlowSchedule
import com.coinepro.hq.core.net.Health
import com.coinepro.hq.core.net.Playbook
import com.coinepro.hq.core.net.PlaybookChange
import com.coinepro.hq.core.net.PlaybookMember
import com.coinepro.hq.core.net.PlaybookSource
import com.coinepro.hq.core.net.PlaybookStats
import com.coinepro.hq.core.net.RepeatPolicy
import com.coinepro.hq.core.net.ReplyPolicy
import com.coinepro.hq.core.net.RunResults
import com.coinepro.hq.core.net.SiteLinks
import com.coinepro.hq.core.net.SiteSection
import com.coinepro.hq.core.net.SiteUrl
import com.coinepro.hq.core.net.UseBudget
import com.coinepro.hq.core.net.UseTime
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** ⟨1.1.0⟩ Contract §59: the library's and the automations' pure functions, and the shapes as the hub sends them. */
@RunWith(RobolectricTestRunner::class)
class LibraryTest {
    @Test
    fun `a playbook of 59 reads its versions, steps, package, lessons and figures`() {
        val pb = Api.json.decodeFromString(Playbook.serializer(), """{"ref":"PB-0004","title_fa":"ریلز","state":"sealed","version":2,"edits":4,"draft_version":3,
            "versions":[{"version":2,"state":"sealed","changelog_fa":["قدم «بازبینی صدا» اضافه شد"],"members":1},{"version":1,"state":"sealed"}],
            "steps":[{"key":"build","title_fa":"ساخت ویدیو","seat":"motion","kind":"workshop","helper":"workshop","model":"claude-opus-5-5","effort":"max","rules_fa":["رندر با حداکثر ۲ پردازش"]}],
            "package":[{"name":"caption.txt","title_fa":"کپشن","step":"package"}],"lessons":[{"n":18,"title_fa":"کاور","rule_fa":"چت معمولیِ تازه","step":"cover"}],
            "stats":{"runs":9,"done":8,"success_pct":88.9,"avg_cost_usd":3.42,"avg_minutes":38.0,"companies":1},"companies_fa":["پرو-چارت"],
            "members":[{"company":"PC","version":2,"automation":"AT-0700"}],"unknown_field":true}""")
        assertEquals(3, pb.draftVersion)
        assertEquals(listOf(2, 1), versionsOf(pb).map { it.version })
        assertEquals("workshop", pb.steps.single().kind)
        assertEquals("caption.txt", pb.`package`.single().name)
        assertEquals(18, pb.lessons.single().n)
        assertEquals("AT-0700", pb.members.single().automation)
        // a playbook of §40 (no versions) is its own one version
        val old = Playbook(ref = "PB-0001", state = "sealed", version = 3)
        assertEquals(listOf(3), versionsOf(old).map { it.version })
    }

    @Test
    fun `figures, companies and tools read as the owner reads them`() {
        assertEquals("هنوز اجرا نشده", statsLineFa(PlaybookStats()))
        assertEquals("هر اجرا \$3.42 · ۳۸ دقیقه · 89% موفق", statsLineFa(PlaybookStats(runs = 9, avgCostUsd = 3.42, avgMinutes = 38.0, successPct = 88.9)))
        assertEquals("هنوز هیچ شرکتی", companiesLineFa(emptyList()))
        assertEquals("پرو-چارت و تریدیار", companiesLineFa(listOf("پرو-چارت", "تریدیار")))
        assertEquals("الف، ب و ۲ شرکت دیگر", companiesLineFa(listOf("الف", "ب", "پ", "ت")))
        assertEquals("Opus 5.5", modelFa("claude-opus-5-5"))
        assertEquals("Gemini 3.8 Flash TTS", modelFa("gemini-3.8-flash-tts"))
        assertEquals("کارگاه · Opus 5.5 · بیشترین دقت", stepToolFa("workshop", "claude-opus-5-5", "max"))
        assertEquals("ChatGPT", stepToolFa("gpt", null, null))
        assertEquals(null, stepToolFa("code", null, null)?.takeIf { it != "کد هاب" })
        assertEquals("ریلز-روزانه-v2.playbook.json", exportFileName("ریلز روزانه", 2))
    }

    @Test
    fun `the library filters on the phone too, with Persian folded`() {
        fun pb(ref: String, title: String, platform: String, state: String, co: String) =
            Playbook(ref = ref, titleFa = title, platform = platform, state = state, source = PlaybookSource(company = co), members = listOf(PlaybookMember(company = co)))
        val list = listOf(pb("PB-1", "ریلز روزانه‌ی پروچارت", "instagram", "sealed", "PC"), pb("PB-2", "سئوی هفتگي سايت", "site", "draft", "PC"), pb("PB-3", "کمپین", "instagram", "retired", "TY"))
        assertEquals(listOf("PB-1"), libraryFiltered(list, "روزانه ی", null, null, null).map { it.ref })
        assertEquals(listOf("PB-2"), libraryFiltered(list, "هفتگی سایت", null, null, null).map { it.ref })
        assertEquals(listOf("PB-1", "PB-3"), libraryFiltered(list, null, "instagram", null, null).map { it.ref })
        assertEquals(listOf("PB-3"), libraryFiltered(list, null, null, null, "TY").map { it.ref })
        assertEquals(listOf("PB-2"), libraryFiltered(list, "", null, "draft", "PC").map { it.ref })
    }

    @Test
    fun `a change between versions is one line`() {
        assertEquals("قدم «بازبینی صدا» اضافه شد", changeLineFa(PlaybookChange("step", "voice_check", "added", null, "بازبینی صدا")))
        assertEquals("قاعده «لایت» برداشته شد", changeLineFa(PlaybookChange("rule", "r", "removed", "لایت", null)))
        assertEquals("نام: «الف» ← «ب»", changeLineFa(PlaybookChange("title", "", "changed", "الف", "ب")))
    }

    @Test
    fun `a reply link keeps what the url has and adds the path's UTM`() {
        assertEquals("https://pro-chart.com?utm_source=instagram&utm_medium=dm&utm_campaign=at-0700&utm_content=20261113",
            utmLink("https://pro-chart.com", "instagram", "dm", "at-0700", "20261113"))
        assertEquals("https://x.com/a?ref=1&utm_source=s&utm_medium=comment&utm_campaign=c#top", utmLink("https://x.com/a?ref=1#top", "s", "comment", "c", null))
        assertEquals("https://x.com/?utm_source=keep&utm_medium=story&utm_campaign=c", utmLink("https://x.com/?utm_source=keep", "s", "story", "c", null))
        val links = SiteLinks(site = SiteUrl("https://pro-chart.com"), sections = listOf(SiteSection("replay", "بازپخش", "https://pro-chart.com/replay")))
        val three = pathLinks(links, "replay", "flow", null)
        assertEquals(listOf("کامنت", "استوری", "دایرکت"), three.map { it.first })
        assertTrue(three.all { it.second.startsWith("https://pro-chart.com/replay?utm_source=instagram&utm_medium=") })
        assertEquals("https://pro-chart.com?utm_source=instagram&utm_medium=comment&utm_campaign=flow", pathLinks(links, null, "flow", null).first().second)
    }

    @Test
    fun `links he types are checked before they go`() {
        assertTrue(linksProblemsFa(SiteLinks(site = SiteUrl("https://pro-chart.com"))).isEmpty())
        assertEquals(1, linksProblemsFa(SiteLinks(site = SiteUrl("http://pro-chart.com"))).size)
        assertTrue(linksProblemsFa(SiteLinks(site = SiteUrl("https://a.com"), sections = listOf(SiteSection("Bad Key", "x", "https://a.com/x")))).isNotEmpty())
        assertEquals("replay", sectionKey("بازپخش", "https://pro-chart.com/replay/", emptySet()))
        assertEquals("replay_2", sectionKey("", "https://pro-chart.com/replay", setOf("replay")))
        assertEquals("section", sectionKey("بازپخش", "https://pro-chart.com/", emptySet()))
    }

    @Test
    fun `the public replies keep their order, his own first, filled to ten`() {
        val filled = poolFilled(listOf("اول", "دوم", "اول", " "))
        assertEquals(10, filled.size)
        assertEquals(listOf("اول", "دوم"), filled.take(2))
        // the pool's own order after his lines: the order IG-Hub sends them in, in turn
        assertEquals("برو دایرکتت رو چک کن، فرستادم برات؛ موفق باشی 🤍", filled[2])
        val many = (1..12).map { "جواب $it" }
        assertEquals(many, poolFilled(many))
        // the body keeps the order too
        val body = repliesBody(ReplyPolicy(publicPool = listOf("سوم", "اول", "دوم")))
        assertEquals(listOf("سوم", "اول", "دوم"), (body["public_pool"] as JsonArray).map { it.jsonPrimitive.content })
    }

    @Test
    fun `what the hub would refuse in a policy is said first`() {
        val ok = ReplyPolicy(dmTemplate = DmTemplate("سلام", listOf(DmButton("ورود به پرو چارت", null))))
        assertTrue(replyProblemsFa(ok, emptySet()).isEmpty())
        assertEquals(1, replyProblemsFa(ok.copy(dmTemplate = DmTemplate("x".repeat(641))), emptySet()).size)
        assertEquals(1, replyProblemsFa(ok.copy(dmTemplate = DmTemplate("x", List(4) { DmButton("b$it") })), emptySet()).size)
        assertEquals(1, replyProblemsFa(ok.copy(dmTemplate = DmTemplate("x", listOf(DmButton("یک دکمه‌ی خیلی خیلی بلند")))), emptySet()).size)
        assertEquals(1, replyProblemsFa(ok.copy(dmTemplate = DmTemplate("x", listOf(DmButton("آموزش", "academy")))), setOf("replay")).size)
        assertTrue(replyProblemsFa(ok.copy(dmTemplate = DmTemplate("x", listOf(DmButton("آموزش", "academy")))), setOf("academy")).isEmpty())
        assertEquals(1, replyProblemsFa(ok.copy(repeat = RepeatPolicy("after_days", 400)), emptySet()).size)
        val body = repliesBody(ok.copy(repeat = RepeatPolicy("after_days", 30)))
        assertEquals("30", ((body["repeat"] as JsonObject)["days"] as JsonPrimitive).content)
        assertFalse((repliesBody(ok)["repeat"] as JsonObject).containsKey("days"))
    }

    @Test
    fun `the use form's body and what it still lacks`() {
        val d = UseDraft(version = 2, company = "TY", accounts = listOf("@tradeyar"), voice = "Cruz", time = UseTime("fixed", "۱۸:۳۰", null, true), budget = UseBudget(5.0, 8.0), auto = true)
        val b = d.body()
        assertEquals("TY", b["company"]!!.jsonPrimitive.content)
        assertEquals(listOf("tradeyar"), (b["accounts"] as JsonArray).map { it.jsonPrimitive.content })
        assertEquals("18:30", ((b["time"] as JsonObject)["at"] as JsonPrimitive).content)
        assertEquals("auto", b["mode"]!!.jsonPrimitive.content)
        assertEquals("Cruz", ((b["narrator"] as JsonObject)["voice"] as JsonPrimitive).content)
        assertFalse(b.containsKey("brand"))
        assertTrue(useMissingFa(d, publishes = true).isEmpty())
        assertEquals(1, useMissingFa(d.copy(company = null), publishes = true).size)
        assertEquals(1, useMissingFa(d.copy(time = UseTime("fixed", "25:00")), publishes = true).size)
        assertEquals(1, useMissingFa(d.copy(budget = UseBudget(5.0, 3.0)), publishes = true).size)
        assertEquals(7.5, dollarsOf("۷٫۵")!!, 0.0)
        assertEquals(8.0, dollarsOf("$8")!!, 0.0)
        assertEquals(null, dollarsOf("هشت"))
        assertEquals("5", dollarsText(5.0))
        assertEquals("7.5", dollarsText(7.5))
    }

    @Test
    fun `the board groups by kind and the road reads in one line`() {
        val items = listOf(BoardItem(ref = "A", kind = "rule"), BoardItem(ref = "B", kind = "flow"), BoardItem(ref = "C", kind = "mystery"), BoardItem(ref = "D", kind = "flow"))
        val g = boardGroups(items)
        assertEquals(listOf("کارگروه‌های خودکار", "اتوماسیون از یک جمله", "دیگر"), g.map { it.first })
        assertEquals(listOf("B", "D"), g.first().second.map { it.ref })
        assertEquals("همه‌ی مسیر سالم است" to Tone.POS, healthLineFa(listOf(Health("n8n", "ok"))))
        assertEquals("IG-Hub: پاسخ نمیدهد" to Tone.NEG, healthLineFa(listOf(Health("n8n", "warn", "دیر"), Health("ighub", "down", "پاسخ نمیدهد"))))
        assertEquals("هر روز، بهترین ساعت", scheduleFa(FlowSchedule(mode = "best")))
        assertEquals("هر شنبه و دوشنبه ساعت 18:30", scheduleFa(FlowSchedule(mode = "fixed", at = "18:30", days = listOf("SA", "MO"))))
        assertEquals("حرف هاب", scheduleFa(FlowSchedule(whenFa = "حرف هاب")))
        assertEquals("۱۲ کامنت، ۹ دایرکت، ۴ کلیک", resultsLineFa(RunResults(comments = 12, dmsSent = 9, clicks = 4)))
        assertEquals(null, resultsLineFa(RunResults()))
    }
}
