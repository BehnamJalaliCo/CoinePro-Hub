package com.coinepro.hq

import android.speech.SpeechRecognizer
import com.coinepro.hq.core.data.PlayerOption
import com.coinepro.hq.core.data.SynthKind
import com.coinepro.hq.core.data.applyPlayer
import com.coinepro.hq.core.data.availabilityOf
import com.coinepro.hq.core.data.councilProgressFa
import com.coinepro.hq.core.data.councilSeats
import com.coinepro.hq.core.data.councilStateFa
import com.coinepro.hq.core.data.normaliseFa
import com.coinepro.hq.core.data.optionNoteFa
import com.coinepro.hq.core.data.recogniseOption
import com.coinepro.hq.core.data.synthesisSections
import com.coinepro.hq.core.media.PhoneFallback
import com.coinepro.hq.core.media.SpeechEngine
import com.coinepro.hq.core.media.afterPhoneFailure
import com.coinepro.hq.core.media.firstEngine
import com.coinepro.hq.core.media.hubUsable
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Council
import com.coinepro.hq.core.net.CouncilMember
import com.coinepro.hq.core.net.Meta
import com.coinepro.hq.core.net.SubLogin
import com.coinepro.hq.core.net.Substitute
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.WebProfile
import com.coinepro.hq.core.net.Work
import com.coinepro.hq.core.net.WorkCreate
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Contract §27 ⟨1.9⟩: the player of an order and its wire fields, the players a voice order names, each player's availability from
 * `GET /substitutes`, a council's state and Claude's synthesis split into its parts, the hub's speech to text as the fallback of the
 * phone's recogniser, and the calls (`player`/`mode` on orders, `/work/{id}/council`, pick and animate, `transcript_fa`).
 */
@RunWith(RobolectricTestRunner::class)
class CouncilTest {
    private val server = MockWebServer()
    private val tokens = object : TokenSource {
        override fun token() = "t0ken"
        override fun clear() = Unit
    }
    private lateinit var api: Api

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), tokens)
    }

    @After
    fun tearDown() = server.close()

    private fun json(body: String, code: Int = 200) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    // ------------------------------------------------------------ player and mode --
    @Test
    fun optionsMapToThePlayerAndModeOnTheWire() {
        assertEquals("auto" to "single", PlayerOption.AUTO.player to PlayerOption.AUTO.mode)
        assertEquals("gemini" to "single", PlayerOption.GEMINI.player to PlayerOption.GEMINI.mode)
        // The council is a mode: the router's player, every available player seated.
        assertEquals("auto" to "council", PlayerOption.COUNCIL.player to PlayerOption.COUNCIL.mode)
        assertEquals(PlayerOption.COUNCIL, PlayerOption.of("auto", "council"))
        assertEquals(PlayerOption.COUNCIL, PlayerOption.of("gpt", "council"))
        assertEquals(PlayerOption.DEEPSEEK, PlayerOption.of("deepseek", "single"))
        // A player a newer hub knows and this app does not reads as the router's; never the council by key.
        assertEquals(PlayerOption.AUTO, PlayerOption.of("mistral", "single"))
        assertEquals(PlayerOption.AUTO, PlayerOption.of("council", "single"))
        assertEquals(PlayerOption.AUTO, PlayerOption.of(null, null))
    }

    @Test
    fun workCarriesPlayerAndModeAndDefaultsToTheRouter() {
        val old = Api.json.decodeFromString(Work.serializer(), """{"id":"w","ref":"W-000001","company":"TY","title":"t","status":"queued"}""")
        assertEquals("auto", old.player)
        assertEquals("single", old.mode)
        val council = Api.json.decodeFromString(Work.serializer(), """{"id":"w","ref":"W-000198","company":"TY","title":"t","status":"delivered","player":"auto","mode":"council"}""")
        assertEquals(PlayerOption.COUNCIL, PlayerOption.of(council.player, council.mode))
        // The new order sends the owner's choice; a caller that names none sends nothing (the hub's defaults).
        val sent = Api.json.encodeToString(WorkCreate.serializer(), WorkCreate("TY", "t", player = "gpt", mode = "single"))
        assertTrue(sent, sent.contains("\"player\":\"gpt\"") && sent.contains("\"mode\":\"single\""))
        val bare = Api.json.encodeToString(WorkCreate.serializer(), WorkCreate("TY", "t"))
        assertFalse(bare, bare.contains("player") || bare.contains("mode"))
    }

    @Test
    fun aVoiceOrderGoesAsWordsAndTheOwnersChoiceIsSetOnItsWork() = runTest {
        // The hub read no player from the words (the router's); the owner chose Gemini: the work it made is changed to it, and only that.
        val work = """{"id":"w-1","ref":"W-000301","company":"FX","title":"t","status":"queued","player":"auto","mode":"single","version":3}"""
        server.enqueue(json("""{"ref":"F-0009","summary_fa":"رفت","routes":[{"company":"FX","to":"FX-CEO","kind":"work","work_ref":"W-000301"},{"company":"FX","to":"FX-TECH-MGR","kind":"code","session_ref":"S-0009"}]}"""))
        val o = api.order("سه تصویر استوری بساز", "voice", null)
        val sent = server.takeRequest().body!!.utf8()
        assertFalse("the order's body is the contract's: no player field", sent.contains("player"))
        server.enqueue(json("""{"items":[$work],"next_cursor":null}"""))
        server.enqueue(json(work))
        server.enqueue(json(work.replace("\"auto\"", "\"gemini\"")))
        assertEquals(1, api.applyPlayer(o, PlayerOption.GEMINI))
        server.takeRequest()
        server.takeRequest()
        val patch = server.takeRequest()
        assertEquals("PATCH", patch.method)
        assertEquals("/api/v1/work/w-1", patch.url.encodedPath)
        assertEquals("\"3\"", patch.headers["If-Match"])
        val b = patch.body!!.utf8()
        assertTrue(b, b.contains("\"player\":\"gemini\"") && b.contains("\"mode\":\"single\""))
        // Already as chosen: nothing is changed.
        server.enqueue(json("""{"items":[$work],"next_cursor":null}"""))
        server.enqueue(json(work))
        assertEquals(0, api.applyPlayer(o, PlayerOption.AUTO))
        assertEquals(6, server.requestCount)
    }

    // -------------------------------------------------------------------- voice --
    @Test
    fun aVoiceOrderNamesItsPlayer() {
        assertEquals(PlayerOption.GPT, recogniseOption("با جی‌پی‌تی گزارش رقبا را بنویس")?.option)
        assertEquals("با جی‌پی‌تی".let(::normaliseFa), recogniseOption("با جی‌پی‌تی گزارش رقبا را بنویس")?.phrase)
        assertEquals(PlayerOption.GPT, recogniseOption("با جی پی تی")?.option)
        assertEquals(PlayerOption.GPT, recogniseOption("این را با ChatGPT بنویس")?.option)
        assertEquals(PlayerOption.GEMINI, recogniseOption("با جمنای سه تصویر استوری بساز")?.option)
        assertEquals("با جمنای", recogniseOption("با جمنای سه تصویر استوری بساز")?.phrase)
        assertEquals(PlayerOption.GEMINI, recogniseOption("فلان کار را جمینای بکند")?.option)
        assertEquals(PlayerOption.DEEPSEEK, recogniseOption("با دیپ‌سیک قیمت‌ها را جستجو کن")?.option)
        assertEquals(PlayerOption.DEEPSEEK, recogniseOption("با دیپسیک")?.option)
        assertEquals(PlayerOption.CLAUDE, recogniseOption("با کلود بنویس")?.option)
        // The council: said by name, or as the models working together.
        assertEquals(PlayerOption.COUNCIL, recogniseOption("شورا: پشتیبانی زنده‌ی شبانه ارزش دارد؟")?.option)
        assertEquals(PlayerOption.COUNCIL, recogniseOption("بده شورای مدل‌ها نظر بدهند")?.option)
        assertEquals(PlayerOption.COUNCIL, recogniseOption("جی‌پی‌تی و جمنای با هم مشارکت کنن")?.option)
        // The first player named wins; Arabic letters as a keyboard may type them read the same.
        assertEquals(PlayerOption.GEMINI, recogniseOption("با جمنای بساز، نه با جی‌پی‌تی")?.option)
        assertEquals(PlayerOption.GEMINI, recogniseOption("با جمناي")?.option)
        // Nothing named: the router plays.
        assertNull(recogniseOption("گزارش رقبای صرافی را تا عصر بفرست"))
        assertNull(recogniseOption(""))
        // «شوراب» is not the council.
        assertNull(recogniseOption("شورابه"))
    }

    // ------------------------------------------------------------- availability --
    private fun sub(player: String, status: String = "ready", runner: String? = "codex_cli", login: String = "signed_in", web: String = "signed_in", reason: String? = null) =
        Substitute(player, "c-$player", runner = runner, login = SubLogin(state = login), status = status, statusReason = reason, web = WebProfile(state = web))

    @Test
    fun aPlayerIsGreyedWithItsReason() {
        val subs = listOf(
            sub("gpt"),
            sub("gemini", status = "limited", runner = "gemini_cli", web = "expired", reason = "سقف روزانه پر شد"),
            sub("deepseek", runner = null, login = "signed_out", web = "signed_in"),
        )
        assertTrue(availabilityOf(PlayerOption.AUTO, subs).ok)
        assertTrue(availabilityOf(PlayerOption.CLAUDE, subs).ok)
        assertTrue(availabilityOf(PlayerOption.GPT, subs).ok)
        val g = availabilityOf(PlayerOption.GEMINI, subs)
        assertFalse(g.ok)
        assertEquals("محدود", g.stateFa)
        assertEquals("سقف روزانه پر شد", g.reasonFa)
        // DeepSeek has no CLI: its signed-in browser profile is what counts.
        assertTrue(availabilityOf(PlayerOption.DEEPSEEK, subs).ok)
        assertEquals("خارج", availabilityOf(PlayerOption.GPT, listOf(sub("gpt", login = "expired", web = "signed_out"))).stateFa)
        assertEquals("خاموش", availabilityOf(PlayerOption.GPT, listOf(sub("gpt", status = "off"))).stateFa)
        assertEquals("تعریف نشده", availabilityOf(PlayerOption.GPT, emptyList()).stateFa)
        // While the list loads nothing is greyed.
        assertTrue(availabilityOf(PlayerOption.GEMINI, null).ok)
        // The council seats Claude and every available substitute.
        assertEquals(listOf(PlayerOption.CLAUDE, PlayerOption.GPT, PlayerOption.DEEPSEEK), councilSeats(subs))
        assertEquals(listOf(PlayerOption.CLAUDE), councilSeats(null))
        // A greyed player chosen anyway waits up to 30 minutes, then the router plays.
        assertTrue(optionNoteFa(PlayerOption.GEMINI, g, 3).contains("۳۰ دقیقه"))
        assertTrue(optionNoteFa(PlayerOption.COUNCIL, availabilityOf(PlayerOption.COUNCIL, subs), 3).contains("3 بازیکن"))
    }

    // ------------------------------------------------------------------ council --
    @Test
    fun aCouncilReadsAsItsMembersAndSynthesis() = runTest {
        server.enqueue(json(
            """{"work_ref":"W-000198","state":"done","synthesis_ref":"O-000155","members":[
              {"player":"claude","model":"claude-sonnet-5-5","state":"done","run_id":"r1","deliverable_ref":"O-000152","reason":null},
              {"player":"gpt","model":"gpt-5.5","state":"done","run_id":"r2","deliverable_ref":"O-000153","reason":null},
              {"player":"gemini","model":"gemini-3.8","state":"skipped","run_id":null,"deliverable_ref":null,"reason":"سقف روزانه"},
              {"player":"deepseek","model":"deepseek-v3.2","state":"working","run_id":"r3","deliverable_ref":null,"reason":null}]}""",
        ))
        val c = api.council("w-1")
        assertEquals("/api/v1/work/w-1/council", server.takeRequest().url.encodedPath)
        assertEquals(4, c.members.size)
        assertEquals("O-000155", c.synthesisRef)
        assertFalse(c.mediaCouncil)
        // The skipped one is not waited for, and is said.
        assertEquals("2 از 3 پاسخ داده‌اند؛ 1 بازیکن کنار ماند", councilProgressFa(c))
        assertEquals("جمع‌بندی آماده است", councilStateFa(c))
        val media = Council("W-000199", listOf(CouncilMember("gpt", state = "done", deliverableRef = "CR-0101"), CouncilMember("gemini", state = "done", deliverableRef = "CR-0102")), state = "done")
        assertTrue(media.mediaCouncil)
        // The hub names a media member's version in `creative_ref`.
        val hub = Api.json.decodeFromString(Council.serializer(), """{"work_ref":"W-1","state":"done","media":"image","synthesis_ref":null,"members":[{"player":"gpt","state":"done","creative_ref":"CR-0201"}]}""")
        assertEquals("CR-0201", hub.members.single().creativeOf)
        assertTrue(hub.mediaCouncil)
        assertEquals("منتظر انتخاب تو", councilStateFa(media))
        assertEquals("Claude جمع‌بندی مینویسد", councilStateFa(c.copy(state = "synthesising")))
    }

    @Test
    fun theSynthesisSplitsIntoAgreeDifferRecommendationAndAnswers() {
        val md = "مقدمه\n\n## کجا هم‌نظرند\n- شب بی‌پاسخ نماند.\n\n## کجا فرق دارند و چرا\n- زمان.\n\n## پیشنهاد\nآزمون سه‌ماهه.\n\n## پاسخ هر بازیکن، کامل\n### Claude\nیک\n### GPT\nدو"
        val s = synthesisSections(md)
        assertEquals(listOf(SynthKind.OTHER, SynthKind.AGREE, SynthKind.DIFFER, SynthKind.RECOMMEND, SynthKind.ANSWERS), s.map { it.kind })
        assertEquals("آزمون سه‌ماهه.", s[3].body)
        // The players' own headings stay inside the answers.
        assertTrue(s[4].body.contains("### GPT"))
        assertEquals(listOf(SynthKind.OTHER), synthesisSections("فقط یک بند.").map { it.kind })
    }

    @Test
    fun theOwnerPicksAndAnimatesACreative() = runTest {
        val cr = """{"ref":"CR-0101","company":"FX","kind":"image","state":"accepted","picked_at":"2026-10-30T10:00:00Z","requested_by":{"kind":"agent","code":"FX-CEO"},"player":"gpt"}"""
        server.enqueue(json(cr))
        assertEquals("2026-10-30T10:00:00Z", api.pickCreative("CR-0101").pickedAt)
        val pick = server.takeRequest()
        assertEquals("POST", pick.method)
        assertEquals("/api/v1/creatives/CR-0101/pick", pick.url.encodedPath)
        server.enqueue(json(cr.replace("CR-0101", "CR-0103").replace("\"image\"", "\"video\"").replace("accepted", "generating"), 201))
        val v = api.animateCreative("CR-0101")
        assertEquals("/api/v1/creatives/CR-0101/animate", server.takeRequest().url.encodedPath)
        assertEquals("video", v.kind)
    }

    // ------------------------------------------------------------------ speech --
    @Test
    fun theHubTranscriptAndTheSpeechSwitchDecode() = runTest {
        val meta = Api.json.decodeFromString(Meta.serializer(), """{"api_version":"1.9","service_version":"x","login_configured":true,"speech":{"enabled":true}}""")
        assertEquals(true, meta.speech?.enabled)
        assertNull(Api.json.decodeFromString(Meta.serializer(), """{"api_version":"1.8","service_version":"x","login_configured":true}""").speech)
        server.enqueue(json("""{"id":"f1","name":"v.m4a","mime":"audio/mp4","size":10,"kind":"audio","transcript":null,"transcript_fa":"متن هاب"}"""))
        val f = api.fileMeta("f1")
        assertEquals("/api/v1/files/f1/meta", server.takeRequest().url.encodedPath)
        assertEquals("متن هاب", f.hubText)
        // A file before ⟨1.9⟩ carries `transcript` only.
        assertEquals("قدیمی", f.copy(transcriptFa = null, transcript = "قدیمی").hubText)
        assertNull(f.copy(transcriptFa = " ", transcript = null).hubText)
    }

    @Test
    fun thePhoneHearsFirstAndTheHubWhenItCannot() {
        // Live dictation: the phone first whenever it has Persian, the hub's state notwithstanding.
        assertEquals(SpeechEngine.PHONE, firstEngine(phoneAvailable = true, phonePersian = null, hubEnabled = true, hubSession = true))
        // No recogniser, or one that said it has no Persian: the hub, when `/meta.speech.enabled` says it is on.
        assertEquals(SpeechEngine.HUB, firstEngine(phoneAvailable = false, phonePersian = null, hubEnabled = true, hubSession = null))
        assertEquals(SpeechEngine.HUB, firstEngine(phoneAvailable = true, phonePersian = false, hubEnabled = true, hubSession = null))
        // The hub off: nobody hears; type.
        assertEquals(SpeechEngine.NONE, firstEngine(phoneAvailable = false, phonePersian = null, hubEnabled = false, hubSession = null))
        // A hub that refused this session (503) is not asked again, even if /meta said on.
        assertEquals(SpeechEngine.NONE, firstEngine(phoneAvailable = false, phonePersian = null, hubEnabled = true, hubSession = false))
        // A hub before ⟨1.9⟩ says nothing: tried once.
        assertTrue(hubUsable(null, null))
        assertFalse(hubUsable(false, true))
    }

    @Test
    fun aFailedPhoneRecogniserFallsBackToTheHub() {
        // Words already heard are kept, whatever the error.
        assertEquals(PhoneFallback.KEEP_WORDS, afterPhoneFailure(SpeechRecognizer.ERROR_NETWORK, unavailable = false, heardWords = true, hubOk = true))
        // The phone's service failed (network, server, busy, no Persian): the hub records and transcribes.
        for (code in listOf(SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_SERVER, SpeechRecognizer.ERROR_RECOGNIZER_BUSY, SpeechRecognizer.ERROR_CLIENT, 12)) {
            assertEquals("code $code", PhoneFallback.HUB, afterPhoneFailure(code, unavailable = code == 12, heardWords = false, hubOk = true))
        }
        // Silence, or the microphone itself: the hub would not hear either; tell the owner.
        assertEquals(PhoneFallback.TELL, afterPhoneFailure(SpeechRecognizer.ERROR_NO_MATCH, unavailable = false, heardWords = false, hubOk = true))
        assertEquals(PhoneFallback.TELL, afterPhoneFailure(SpeechRecognizer.ERROR_SPEECH_TIMEOUT, unavailable = false, heardWords = false, hubOk = true))
        assertEquals(PhoneFallback.TELL, afterPhoneFailure(SpeechRecognizer.ERROR_AUDIO, unavailable = false, heardWords = false, hubOk = true))
        assertEquals(PhoneFallback.TELL, afterPhoneFailure(SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS, unavailable = false, heardWords = false, hubOk = true))
        // The hub off: no Persian on the phone offers typing; any other failure is told.
        assertEquals(PhoneFallback.TYPE, afterPhoneFailure(12, unavailable = true, heardWords = false, hubOk = false))
        assertEquals(PhoneFallback.TELL, afterPhoneFailure(SpeechRecognizer.ERROR_NETWORK, unavailable = false, heardWords = false, hubOk = false))
    }
}
