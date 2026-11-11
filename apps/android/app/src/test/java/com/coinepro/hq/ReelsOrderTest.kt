package com.coinepro.hq

import com.coinepro.hq.core.data.JPEG_LINE_FA
import com.coinepro.hq.core.data.bestChoice
import com.coinepro.hq.core.data.bestClockFa
import com.coinepro.hq.core.data.bestHourLines
import com.coinepro.hq.core.data.cancellable
import com.coinepro.hq.core.data.cancelling
import com.coinepro.hq.core.data.effortFa
import com.coinepro.hq.core.data.faDigits
import com.coinepro.hq.core.data.genderFa
import com.coinepro.hq.core.data.goesAsJpeg
import com.coinepro.hq.core.data.ledgerCountsFa
import com.coinepro.hq.core.data.linkOf
import com.coinepro.hq.core.data.madeWithFa
import com.coinepro.hq.core.data.narratorBody
import com.coinepro.hq.core.data.narratorLineFa
import com.coinepro.hq.core.data.narratorStepFa
import com.coinepro.hq.core.data.publishRule
import com.coinepro.hq.core.data.publishStateFa
import com.coinepro.hq.core.data.routineBody
import com.coinepro.hq.core.data.routineReady
import com.coinepro.hq.core.data.standingLineFa
import com.coinepro.hq.core.data.topicBody
import com.coinepro.hq.core.data.topicSourceFa
import com.coinepro.hq.core.data.withPublish
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.BestHour
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.MemberPublish
import com.coinepro.hq.core.net.Narrator
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.PublishPanel
import com.coinepro.hq.core.net.SessionPublish
import com.coinepro.hq.core.net.SessionRoutine
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.TopicEntry
import com.coinepro.hq.core.net.TopicLedger
import com.coinepro.hq.core.net.VoiceOption
import com.coinepro.hq.core.net.gated
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Contract §47 to §53 ⟨1.31⟩, what the reels order still lacked: the shapes as the hub serialises them (with their nulls, and as a hub
 * before them leaves them out), the owner's words (the ledger's counts and sources, the narrator's line, the best hour's lines, a
 * publication's state, the effort), the rules (which row carries «لغو», which picture goes out as a JPEG, when «بهترین ساعت» is a time
 * of the sheet), the bodies the app sends, and an older hub tolerated (a missing route hides the feature, without an error).
 */
@RunWith(RobolectricTestRunner::class)
class ReelsOrderTest {
    private val server = MockWebServer()
    private lateinit var api: Api

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
    }

    @After
    fun tearDown() = server.close()

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()
    private fun obj(text: String): JsonObject = Api.json.parseToJsonElement(text).jsonObject

    // ------------------------------------------------------------------ shapes --
    @Test
    fun theLedgerReadsAsTheHubWritesIt() {
        val l = Api.json.decodeFromString(
            TopicLedger.serializer(),
            """{"items":[{"id":"0193c0de-47a0-7000-8000-000000000001","kind":"topic","title_fa":"حد ضرر در ۳۰ ثانیه","url":null,"at":"2026-11-04T05:30:00Z","by":"TY-MEDIA-02","source":"claim","work_ref":"W-000340","output":null},
                {"id":"0193c0de-47a0-7000-8000-000000000002","kind":"reference","title_fa":"","url":"https://www.pinterest.com/pin/70368109/","at":"2026-11-03T05:30:00Z","by":"owner","source":"owner","work_ref":null,"output":null}],
                "topics":42,"references":40,"next_cursor":"30"}""",
        )
        assertEquals(42 to 40, l.topics to l.references)
        assertEquals("30", l.nextCursor)
        assertEquals(listOf("topic", "reference"), l.items.map { it.kind })
        assertEquals("W-000340", l.items[0].workRef)
        assertEquals("https://www.pinterest.com/pin/70368109/", l.items[1].url)
        // the last page, and a line of a source this app does not know yet
        val last = Api.json.decodeFromString(TopicLedger.serializer(), """{"items":[{"id":"x","kind":"topic","title_fa":"t","at":"2026-11-01T00:00:00Z","by":"hub","source":"import"}],"topics":1,"references":0}""")
        assertNull(last.nextCursor)
        assertEquals("", topicSourceFa(last.items.single().source))
        assertEquals(TopicEntry(), Api.json.decodeFromString(TopicEntry.serializer(), "{}"))
    }

    @Test
    fun theNarratorTheBestHourAndARoutineReadAsTheHubWritesThem() {
        val n = Api.json.decodeFromString(
            Narrator.serializer(),
            """{"company":"TY","set":true,"voice":"Charon","style_fa":"آرام و مطمئن","by":"owner","updated_at":"2026-11-07T08:00:00Z",
                "voices":[{"name":"Zephyr","gender":"female","trait_fa":"روشن"},{"name":"Charon","gender":"male","trait_fa":"اطلاع‌رسان"}],"aistudio":"signed_in"}""",
        )
        assertTrue(n.set)
        assertEquals(listOf("Zephyr", "Charon"), n.voices.map { it.name })
        assertEquals("Charon · آرام و مطمئن", narratorLineFa(n))
        assertNull(narratorStepFa(n))
        // none yet (the hub then names its default voice), and the hub out of its account: the owner's one step
        val none = Api.json.decodeFromString(Narrator.serializer(), """{"company":"FX","set":false,"voice":"Kore","style_fa":"","by":null,"updated_at":null,"voices":[],"aistudio":"signed_out"}""")
        assertEquals("تنظیم نشده؛ هر بار مدل انتخاب میکند", narratorLineFa(none))
        assertEquals("گوینده‌ی هاب از حسابش بیرون افتاده؛ یک بار ورود خودت لازم است.", narratorStepFa(none))
        assertNull(narratorStepFa(Narrator(company = "PC")))
        assertEquals("Kore", narratorLineFa(Narrator(company = "PC", set = true, voice = "Kore", styleFa = " ")))
        assertEquals(listOf("زن", "مرد", ""), listOf("female", "male", "other").map(::genderFa))

        val b = Api.json.decodeFromString(
            BestHour.serializer(),
            """{"account":"tradeyar","hour":"21:00","at":"2026-11-06T17:30:00Z","enough":true,"posts":38,"days":90,"basis":"likes_comments","note_fa":"از روی لایک و کامنت 38 پست","read_at":"2026-11-06T04:00:00Z"}""",
        )
        assertTrue(b.enough)
        // a clock is a Latin figure (C0.4)
        assertEquals("21:00", bestClockFa(b))
        val thin = Api.json.decodeFromString(BestHour.serializer(), """{"account":"coineprofx","hour":null,"at":null,"enough":false,"posts":7,"days":19,"note_fa":"هنوز داده‌ی کافی نیست","read_at":null}""")
        assertFalse(thin.enough)
        assertNull(bestClockFa(thin))
        // the standing word and the publish panel gain it; a hub before §49 sends neither
        assertTrue(Api.json.decodeFromString(MemberPublish.serializer(), """{"mode":"auto","account":"tradeyar","story":false,"since":null,"at":"18:30","best":true}""").best)
        assertFalse(Api.json.decodeFromString(MemberPublish.serializer(), """{"mode":"auto","at":"18:30"}""").best)
        assertEquals("21:00", Api.json.decodeFromString(PublishPanel.serializer(), """{"order":null,"accounts":["tradeyar"],"tap":true,"best":{"account":"tradeyar","hour":"21:00","at":"2026-11-06T17:30:00Z","enough":true}}""").best?.hour)
        assertNull(Api.json.decodeFromString(PublishPanel.serializer(), """{"order":"F-0100","accounts":[],"best":null}""").best)

        val r = Api.json.decodeFromString(
            OrderReport.serializer(),
            """{"ref":"F-0100","routines":[{"ref":"AT-0902","company":"PC","sentence_fa":"هر روز ساعت ۹ رتبه‌ها را ببین","when_fa":"هر روز ساعت 09:00","preview_fa":"یک کار تازه ساخته میشود",
                "state":"on","next_at":"2026-11-07T05:30:00Z","last_run_at":null,"runs":6,"order":"F-0100","note_fa":null}],
                "publishes":[{"job":"jp-21","file_id":"f","kind":"post","state":"cancelled","scheduled_at":"2026-11-06T15:00:00Z","note_fa":null}]}""",
        )
        assertEquals(SessionRoutine("AT-0902", "PC", "هر روز ساعت ۹ رتبه‌ها را ببین", "هر روز ساعت 09:00", "یک کار تازه ساخته میشود", "on", "2026-11-07T05:30:00Z", null, 6, "F-0100", null), r.routines!!.single())
        assertEquals("cancelled", r.publishes.single().state)
        // a hub of §50 always sends the list (empty too); a hub before it sends none, and the session offers no routine then
        assertEquals(emptyList<SessionRoutine>(), Api.json.decodeFromString(OrderReport.serializer(), """{"ref":"F-0101","routines":[]}""").routines)
        assertNull(Api.json.decodeFromString(OrderReport.serializer(), """{"ref":"F-0101"}""").routines)
    }

    /** Every field the hub's own schema has is read (`apps/api/openapi/hq-api.v1.json`), and no other is expected of it. */
    @Test
    fun theModelsMatchTheHubsOpenApi() {
        val schemas = obj(java.io.File("../../api/openapi/hq-api.v1.json").readText())["components"]!!.jsonObject["schemas"]!!.jsonObject
        org.junit.Assume.assumeTrue("the hub's §47 schemas are in this tree's OpenAPI", "TopicLedger" in schemas)
        fun snake(s: String) = s.replace(Regex("([A-Z])")) { "_" + it.value.lowercase() }
        val models = mapOf(
            "TopicEntry" to TopicEntry.serializer().descriptor, "TopicLedger" to TopicLedger.serializer().descriptor,
            "Narrator" to Narrator.serializer().descriptor, "VoiceOption" to VoiceOption.serializer().descriptor,
            "BestHour" to BestHour.serializer().descriptor, "SessionRoutine" to SessionRoutine.serializer().descriptor,
            "MemberPublish" to MemberPublish.serializer().descriptor, "PublishPanel" to PublishPanel.serializer().descriptor,
        )
        for ((name, d) in models) {
            val theirs = schemas[name]!!.jsonObject["properties"]!!.jsonObject.keys.sorted()
            val ours = (0 until d.elementsCount).map { snake(d.getElementName(it)) }.sorted()
            assertEquals("$name: the app reads every field the hub sends, and no other", theirs, ours)
        }
        assertTrue("routines" in schemas["OrderReport"]!!.jsonObject["properties"]!!.jsonObject)
        assertTrue("cancelled" in schemas["SessionPublish"]!!.jsonObject["properties"]!!.jsonObject["state"]!!.jsonObject["enum"].toString())
    }

    // ------------------------------------------------------------------- words --
    @Test
    fun theLedgersWordsAndTheLineHeAdds() {
        assertEquals("۴۲ موضوع · ۴۰ نمونه", ledgerCountsFa(42, 40))
        assertEquals("۳ موضوع · ۰ نمونه", ledgerCountsFa(3, 0))
        assertEquals("هنوز چیزی ثبت نشده", ledgerCountsFa(0, 0))
        assertEquals(listOf("ثبت کارمند", "از بسته‌ی منتشرشده", "افزوده‌ی تو"), listOf("claim", "package", "owner").map(::topicSourceFa))
        // a topic is its words; a sample needs its link, and its words are optional
        assertEquals("""{"kind":"topic","title_fa":"حد ضرر در ۳۰ ثانیه"}""", topicBody("topic", "  حد ضرر در ۳۰ ثانیه ", "").toString())
        assertNull(topicBody("topic", " ", ""))
        assertNull(topicBody("reference", "نمونه", ""))
        assertNull(topicBody("reference", "نمونه", "pinterest"))
        assertEquals("""{"kind":"reference","url":"https://pin.it/abc"}""", topicBody("reference", "", " https://pin.it/abc ").toString())
        assertEquals(setOf("kind", "url", "title_fa"), topicBody("reference", "کاور طلایی", "https://www.pinterest.com/pin/1/")!!.keys)
        assertEquals("http://x.test/a", linkOf("http://x.test/a"))
        assertNull(linkOf("x.test"))
        assertEquals("۲۱:۰۰", faDigits("21:00"))
    }

    @Test
    fun theBestHoursLinesAndTheStandingWord() {
        val best = BestHour(account = "tradeyar", hour = "21:00", at = "2026-11-06T17:30:00Z", enough = true, noteFa = "از روی لایک و کامنت 38 پست در 90 روز اخیر")
        assertEquals(listOf("بهترین ساعت این حساب: 21:00", "از روی لایک و کامنت 38 پست در 90 روز اخیر"), bestHourLines(best, null))
        val thin = BestHour(account = "coineprofx", noteFa = "هنوز داده‌ی کافی نیست (7 پست در 19 روز)")
        assertEquals(listOf("هنوز داده‌ی کافی نیست (7 پست در 19 روز)", "تا آن وقت: ساعت ثابت خودت"), bestHourLines(thin, "۱۸:۳۰"))
        assertEquals(listOf("هنوز داده‌ی کافی نیست (7 پست در 19 روز)", "تا آن وقت: همان لحظه‌ی آماده شدن"), bestHourLines(thin, null))
        assertEquals(listOf("تا آن وقت: همان لحظه‌ی آماده شدن"), bestHourLines(BestHour(), "عصر"))
        // a member's line: «بهترین ساعت» in the hour's place, with the hour once the hub knows it
        val word = MemberPublish(mode = "auto", account = "tradeyar", story = true, at = "18:30", best = true)
        assertEquals("خودکار · بهترین ساعت 21:00 · ⁦@tradeyar⁩ · استوری هم", standingLineFa(word, best))
        // the hub does not know the hour yet: his fixed hour is what it falls back on, and the line says so
        assertEquals("خودکار · بهترین ساعت · تا آن وقت ساعت 18:30 · ⁦@tradeyar⁩ · استوری هم", standingLineFa(word, thin))
        assertEquals("خودکار · بهترین ساعت", standingLineFa(MemberPublish(mode = "auto", best = true)))
        assertEquals("خودکار · ساعت 18:30", standingLineFa(MemberPublish(mode = "auto", at = "18:30")))
        assertEquals("هر بار بپرس", standingLineFa(MemberPublish(best = true)))
        // it goes with the others, only when on (the hub's default is off; a hub before §49 knows no such field)
        assertEquals("""{"mode":"auto","story":true,"at":"18:30","best":true}""", publishRule(word.copy(account = null)).toString())
        assertEquals("""{"mode":"auto","at":"18:30"}""", publishRule(MemberPublish(mode = "auto", at = "18:30")).toString())
        assertEquals("""{"mode":"ask"}""", publishRule(MemberPublish(best = true)).toString())
        assertEquals("""{"publish":{"mode":"auto","best":true}}""", com.coinepro.hq.core.data.sealBody(MemberPublish(mode = "auto", best = true)).toString())
        // «بهترین ساعت (۲۱:۰۰)» is a time of the sheet for the account it was read for
        assertEquals(best, bestChoice(best, "tradeyar"))
        assertEquals(best, bestChoice(best, null))
        assertNull(bestChoice(best, "tradeyar.academy"))
        assertNull(bestChoice(best.copy(at = null), "tradeyar"))
        assertNull(bestChoice(null, "tradeyar"))
    }

    @Test
    fun whichRowCarriesCancelAndWhatACancelAnswers() {
        fun p(state: String, job: String? = "jp-1", note: String? = null) = SessionPublish(job = job, fileId = "f", state = state, noteFa = note)
        assertTrue(cancellable(p("scheduled")))
        assertTrue(cancellable(p("publishing")))
        // out, failed, cancelled, waiting for a seal or for its path: nothing to take back; nor one without its job
        for (s in listOf("published", "failed", "cancelled", "waiting_seal", "waiting_setup")) assertFalse(s, cancellable(p(s)))
        assertFalse(cancellable(p("scheduled", job = null)))
        assertFalse(cancellable(p("scheduled", job = " ")))
        // while the cancel is on its way the row says so and asks nothing again; one IG-Hub refused can be tried again
        assertTrue(cancelling(p("scheduled", note = "در حال لغو")))
        assertFalse(cancellable(p("scheduled", note = " در حال لغو ")))
        assertTrue(cancellable(p("scheduled", note = "لغو انجام نشد (IG-Hub جواب نداد)")))
        assertFalse(cancelling(p("cancelled", note = "در حال لغو")))
        assertEquals("لغو شد", publishStateFa("cancelled"))
        assertEquals("زمان‌بندی شد", publishStateFa("scheduled"))
        // the answer takes its own row's place; another job's answer changes nothing
        val list = listOf(p("scheduled", "jp-2"), p("scheduled", "jp-1"))
        assertEquals(listOf("scheduled", "cancelled"), withPublish(list, p("cancelled", "jp-1")).map { it.state })
        assertEquals(list, withPublish(list, p("cancelled", "jp-9")))
    }

    @Test
    fun aPictureThatIsNoJpegSaysSo() {
        fun f(name: String, mime: String) = FileRef(id = "x", name = name, mime = mime, kind = "image")
        assertTrue(goesAsJpeg(f("cover.png", "image/png")))
        assertTrue(goesAsJpeg(f("cover", "image/webp")))
        assertTrue(goesAsJpeg(f("IMG_2041.HEIC", "application/octet-stream")))
        assertTrue(goesAsJpeg(f("story.webp", "")))
        assertFalse(goesAsJpeg(f("cover.jpg", "image/jpeg")))
        assertFalse(goesAsJpeg(f("cover.jpeg", "")))
        assertFalse(goesAsJpeg(FileRef(id = "v", name = "reel.mp4", mime = "video/mp4", kind = "video")))
        assertFalse(goesAsJpeg(null))
        assertTrue("JPEG" in JPEG_LINE_FA)
    }

    @Test
    fun theEffortInAWordAndHowAnOutputWasMade() {
        assertEquals(listOf("کم", "متوسط", "زیاد", "خیلی زیاد", "بیشترین دقت"), listOf("low", "medium", "high", "xhigh", "max").map { effortFa(it) })
        assertNull(effortFa(null))
        assertNull(effortFa("ultra"))
        // the model by the app's own name and its effort; a workshop's output has no label of its own
        assertEquals("Opus 5.5 · بیشترین دقت", madeWithFa(obj("""{"runtime":"workshop","model":"claude-opus-5-5","effort":"max"}""")))
        assertEquals("Sonnet 5.5 · زیاد", madeWithFa(obj("""{"model":"claude-sonnet-5-5","effort":"high","label_fa":"Sonnet 5.5 · high"}""")))
        // without an effort the hub's own label stands; without a label, the model alone; without either, nothing
        assertEquals("قاعده‌محور، بدون مدل", madeWithFa(obj("""{"label_fa":"قاعده‌محور، بدون مدل","provider":"rules"}""")))
        assertEquals("کارگاه هلدینگ", madeWithFa(obj("""{"model":"claude-opus-5-5","label_fa":"کارگاه هلدینگ"}""")))
        assertEquals("Opus 5.5", madeWithFa(obj("""{"model":"claude-opus-5-5","effort":"ultra"}""")))
        assertNull(madeWithFa(obj("""{"runtime":"workshop","effort":"max"}""")))
        assertNull(madeWithFa(obj("""{"model":"<synthetic>"}""")))
        assertNull(madeWithFa(JsonObject(emptyMap())))
    }

    @Test
    fun theBodiesOfANarratorAndARoutine() {
        assertEquals("""{"voice":"Charon","style_fa":"آرام و مطمئن، مثل گوینده‌ی خبر"}""", narratorBody(" Charon ", "آرام و  مطمئن،\nمثل گوینده‌ی خبر ").toString())
        assertEquals("""{"voice":"Kore"}""", narratorBody("Kore", "  ").toString())
        assertEquals(500, narratorBody("Kore", "آ".repeat(700))["style_fa"].toString().trim('"').length)
        // the session's ref goes as `order` only when it is an order's; the company is the session's own unless he names one
        assertEquals("""{"sentence_fa":"هر روز ساعت ۹ رتبه‌ها را ببین","order":"F-0100"}""", routineBody(" هر روز ساعت ۹ رتبه‌ها را ببین ", "F-0100").toString())
        assertEquals(setOf("sentence_fa"), routineBody("هر روز", "W-000311").keys)
        assertEquals(setOf("sentence_fa", "company"), routineBody("هر روز", null, "PC").keys)
        assertTrue(routineReady("هر روز"))
        assertFalse(routineReady(" آ "))
    }

    // ------------------------------------------------------------------ an older hub --
    @Test
    fun aHubBeforeTheseRoutesHidesThemWithoutAnError() = runTest {
        // the framework's own 404 (or a 405): the feature is learnt missing once, and never asked again
        server.enqueue(json(404, """{"detail":"Not Found"}"""))
        assertNull(api.gated(HubFeature.TOPIC_LEDGER) { topics("pb_1", "TY", limit = 1) })
        assertFalse(api.gaps.has(HubFeature.TOPIC_LEDGER))
        assertNull(api.gated(HubFeature.TOPIC_LEDGER) { fail("not asked again"); topics("pb_1", "TY") })
        server.enqueue(json(405, """{"detail":"Method Not Allowed"}"""))
        assertNull(api.gated(HubFeature.PUBLISH_CANCEL) { cancelPublish("jp-1") })
        server.enqueue(json(404, ""))
        assertNull(api.gated(HubFeature.ROUTINES) { newRoutine("هر روز ساعت ۹", "F-0100", "k") })
        assertEquals(1 + 1 + 1, server.requestCount)
        for (f in listOf(HubFeature.TOPIC_LEDGER, HubFeature.PUBLISH_CANCEL, HubFeature.ROUTINES)) assertFalse(f.name, api.gaps.has(f))
        // the hub's own «not found» (a company it does not know) is its answer, not a missing route
        server.enqueue(json(404, """{"code":"not_found","message_fa":"این شرکت را نمیشناسم.","status":404,"title":"Not found","type":"about:blank","detail":"no such company"}"""))
        try { api.gated(HubFeature.NARRATOR) { narrator("ZZ") }; fail("expected ApiException") } catch (e: ApiException) { assertEquals("این شرکت را نمیشناسم.", e.messageFa) }
        assertTrue(api.gaps.has(HubFeature.NARRATOR))
        assertTrue(api.gaps.has(HubFeature.BEST_HOUR))
        assertNotNull(HubFeature.valueOf("BEST_HOUR"))
    }
}
