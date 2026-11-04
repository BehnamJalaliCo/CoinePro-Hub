package com.coinepro.hq

import com.coinepro.hq.core.data.AudioOrder
import com.coinepro.hq.core.data.HandsFree
import com.coinepro.hq.core.data.HandsFreeEvent
import com.coinepro.hq.core.data.Light
import com.coinepro.hq.core.data.TalkEvent
import com.coinepro.hq.core.data.applyPayloadEdits
import com.coinepro.hq.core.data.capFraction
import com.coinepro.hq.core.data.daysToPriceChange
import com.coinepro.hq.core.data.enginesInUse
import com.coinepro.hq.core.data.extractKey
import com.coinepro.hq.core.data.faceOrder
import com.coinepro.hq.core.data.handsFreeNext
import com.coinepro.hq.core.data.keyPatterns
import com.coinepro.hq.core.data.lightFix
import com.coinepro.hq.core.data.lightOf
import com.coinepro.hq.core.data.meterChip
import com.coinepro.hq.core.data.meterTone
import com.coinepro.hq.core.data.micOpen
import com.coinepro.hq.core.data.parseCap
import com.coinepro.hq.core.data.parseTalkEvent
import com.coinepro.hq.core.data.payloadFields
import com.coinepro.hq.core.data.personaIdTitle
import com.coinepro.hq.core.data.priceChangeFa
import com.coinepro.hq.core.data.priceWarning
import com.coinepro.hq.core.data.sampleCostFa
import com.coinepro.hq.core.data.secondsFa
import com.coinepro.hq.core.data.usdNumber
import com.coinepro.hq.core.data.usdText
import com.coinepro.hq.core.data.withoutKey
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.OwnerSettings
import com.coinepro.hq.core.net.TalkConversation
import com.coinepro.hq.core.net.TalkDetail
import com.coinepro.hq.core.net.TalkPersona
import com.coinepro.hq.core.net.TalkTurn
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.VoiceEngine
import com.coinepro.hq.core.net.VoiceMeter
import java.time.LocalDate
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
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
 * Contract §32 ⟨1.14⟩, talk: the shapes the screens read (a decimal as a number or a string, an id as a number or a string, `present`
 * as keys or as objects), the answer's stream, the order sentences are played in, the hands-free loop, the key kept out of the composer,
 * the meter and its cap, the price change ahead, and the calls (idempotent turn, sealed key, sealed card on demand).
 */
@RunWith(RobolectricTestRunner::class)
class V32Test {
    private val server = MockWebServer()
    private lateinit var api: Api
    private val signed = mutableListOf<Pair<String, String>>()
    private val stepUp: suspend (String, String) -> String = { a, t -> signed += a to t; "su-token" }

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
    }

    @After
    fun tearDown() = server.close()

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()
    private fun problem(status: Int, code: String) =
        MockResponse.Builder().code(status).addHeader("Content-Type", "application/problem+json").body("""{"type":"about:blank","title":"x","status":$status,"code":"$code","message_fa":"پیام"}""").build()

    // ------------------------------------------------------------ shapes --
    @Test
    fun personasAndConversationsDecode() {
        val p = Api.json.decodeFromString(TalkPersona.serializer(), """{"key":"manager","role":"ceo","title_fa":"مدیرعامل تریدیار","company":"TY","voice":{"engine":"gemini-3.8-flash-tts","voice":"Puck","rate":1.1},"brain":{"task_class":"talk_turn","effort":"medium"},"tools":["a"],"face":"f-1","consult_only":false}""")
        assertEquals("ceo@TY", p.id)
        assertEquals(1.1, p.voice.rate, 0.0)
        assertEquals("secretary", Api.json.decodeFromString(TalkPersona.serializer(), """{"key":"secretary"}""").id)
        // `present` as keys, or as objects the hub fills.
        val a = Api.json.decodeFromString(TalkConversation.serializer(), """{"ref":"CV-0001","persona":"secretary","present":["secretary","ceo@TY"],"mode":"consult","turns":4,"cost":{"tokens":900,"usd_equiv":"0.0123","voice_usd":0.004}}""")
        assertEquals(listOf("secretary", "ceo@TY"), a.presentIds)
        assertEquals(0.0123, a.cost.usdEquiv, 1e-9)
        assertEquals(0.004, a.cost.voiceUsd, 1e-9)
        val b = Api.json.decodeFromString(TalkConversation.serializer(), """{"ref":"CV-0002","persona":"ceo@TY","present":[{"key":"secretary"},{"key":"manager","role":"ceo","company":"TY"}]}""")
        assertEquals(listOf("secretary", "ceo@TY"), b.presentIds)
        assertEquals("consult", b.mode)
    }

    @Test
    fun aTurnReadsItsIdAndItsCards() {
        val t = Api.json.decodeFromString(TalkTurn.serializer(), """{"id":42,"conversation":"CV-0001","n":3,"by":"secretary","source":"typed","text":"","say_fa":"س","show_md":"**م**","cards":[{"id":"TC-1","turn":42,"kind":"order","title_fa":"ت","body_fa":"ب","payload":{"title_fa":"x"},"state":"offered","made":[]}],"audio":[{"seq":0,"file_id":"f1","seconds":3.4,"engine":"piper"}],"state":"done","at":"2026-11-04T08:00:00Z","voice":{"engine":"piper","seconds":3.4,"audio_tokens":0,"usd":"0"}}""")
        assertEquals("42", t.idText)
        assertFalse(t.owner)
        assertEquals("**م**", t.shown)
        assertEquals("TC-1", t.cards.single().idText)
        assertEquals(0.0, t.voice!!.usd, 0.0)
        val mine = Api.json.decodeFromString(TalkTurn.serializer(), """{"id":"t-1","by":"owner","source":"hold","text":"سلام"}""")
        assertTrue(mine.owner)
        assertEquals("سلام", mine.shown)
    }

    @Test
    fun theConversationDetailComesInEitherShape() {
        val flat = Api.json.parseToJsonElement("""{"ref":"CV-0001","persona":"secretary","turns":2,"turns_page":{"items":[{"id":1,"n":1,"by":"owner","text":"a"},{"id":2,"n":2,"by":"secretary","show_md":"b"}]}}""")
        val d1 = TalkDetail.parse(flat)
        assertEquals("CV-0001", d1.conversation.ref)
        assertEquals(2, d1.conversation.turns)
        assertEquals(2, d1.turns.size)
        val wrapped = Api.json.parseToJsonElement("""{"conversation":{"ref":"CV-0002","persona":"overseer"},"turns":{"items":[{"id":"x","n":1,"by":"owner","text":"a"}]}}""")
        val d2 = TalkDetail.parse(wrapped)
        assertEquals("CV-0002", d2.conversation.ref)
        assertEquals(1, d2.turns.size)
        // A hub that sends no turns leaves an empty page, not a failure.
        assertTrue(TalkDetail.parse(Api.json.parseToJsonElement("""{"ref":"CV-0003","turns":0}""")).turns.isEmpty())
    }

    @Test
    fun enginesAndTheMeterReadDecimalsAsNumbersOrStrings() {
        val e = Api.json.decodeFromString(VoiceEngine.serializer(), """{"key":"gemini-3.8-flash-tts","title_fa":"فلش","provider":"google","model":"m","languages":130,"rank_fa":"بهترین","key_pattern":"AIza[0-9A-Za-z_-]{35}","state":"ok","price":{"text_in_per_m":"0.5","audio_out_per_m":9,"audio_tokens_per_s":25,"valid_until":"2026-12-31","next":{"from":"2027-01-01","text_in_per_m":1,"audio_out_per_m":"18"}},"voices":[{"name":"Kore","gender_fa":"زن","sample_file":null}]}""")
        assertEquals(9.0, e.price.audioOutPerM, 0.0)
        assertEquals(18.0, e.price.next!!.audioOutPerM, 0.0)
        assertEquals("Kore", e.voices.single().name)
        val m = Api.json.decodeFromString(VoiceMeter.serializer(), """{"period":"month","voice_usd":"0.42","cap_usd":10,"projected_usd":"1.31","by_engine":[{"engine":"piper","usd":"0","seconds":42,"audio_tokens":0}],"by_persona":[{"persona":"secretary","usd":0.29,"seconds":150}],"talk_tokens":{"input":100,"output":20},"talk_usd_equiv":"1.07","price_note_fa":"x"}""")
        assertEquals(0.42, m.voiceUsd, 1e-9)
        assertEquals(10.0, m.capUsd!!, 0.0)
        assertEquals(120L, m.tokensTotal)
        // No cap is a null, not a zero.
        assertNull(Api.json.decodeFromString(VoiceMeter.serializer(), """{"voice_usd":0.1,"cap_usd":null}""").capUsd)
        assertNull(Api.json.decodeFromString(VoiceMeter.serializer(), """{"voice_usd":0.1}""").capUsd)
        assertEquals(1500L, Api.json.decodeFromString(VoiceMeter.serializer(), """{"talk_tokens":1500}""").tokensTotal)
        val s = Api.json.decodeFromString(OwnerSettings.serializer(), """{"version":3,"voice":{"month_cap_usd":"20","warn_at":0.8,"chain":["a","piper"]}}""")
        assertEquals(20.0, s.voice!!.monthCapUsd!!, 0.0)
        assertEquals(listOf("a", "piper"), s.voice!!.chain)
        assertNull(Api.json.decodeFromString(OwnerSettings.serializer(), """{"version":3}""").voice)
    }

    // -------------------------------------------------------- the stream --
    @Test
    fun theAnswerStreamIsRead() {
        assertEquals(TalkEvent.Text("سلا"), parseTalkEvent("text", """{"delta":"سلا"}"""))
        assertEquals(TalkEvent.Text("م"), parseTalkEvent("text", "\"م\""))
        assertEquals(TalkEvent.Say("جمله"), parseTalkEvent("say", """{"text":"جمله"}"""))
        val audio = parseTalkEvent("audio", """{"seq":2,"file_id":"f9","seconds":3.5,"engine":"piper"}""") as TalkEvent.Audio
        assertEquals(2, audio.audio.seq)
        assertEquals("f9", audio.audio.fileId)
        assertNull(parseTalkEvent("audio", """{"seq":2}"""))
        val card = parseTalkEvent("card", """{"id":"TC-9","kind":"minutes","title_fa":"ص","payload":{}}""") as TalkEvent.CardOffered
        assertEquals("minutes", card.card.kind)
        assertEquals("7", (parseTalkEvent("card", """{"card":{"id":7,"kind":"order"}}""") as TalkEvent.CardOffered).card.idText)
        assertEquals(TalkEvent.Invite("ceo", "TY"), parseTalkEvent("invite", """{"role":"ceo","company":"TY"}"""))
        assertEquals(0.5, (parseTalkEvent("meter", """{"voice_usd":"0.5"}""") as TalkEvent.Meter).usd!!, 0.0)
        assertEquals(TalkEvent.Done, parseTalkEvent("done", "{}"))
        assertEquals(TalkEvent.Error("brain_down", "الان به مغزم دسترسی ندارم"), parseTalkEvent("error", """{"code":"brain_down","reason_fa":"الان به مغزم دسترسی ندارم"}"""))
        assertEquals(TalkEvent.Tool(true), parseTalkEvent("tool", "{}"))
        // What the app does not know is ignored, never a failure.
        assertNull(parseTalkEvent("something_new", "{}"))
        assertNull(parseTalkEvent("text", "{}"))
    }

    @Test
    fun sentencesPlayInOrderWhateverTheArrival() {
        val q = AudioOrder<String>()
        q.offer(1, "b"); q.offer(2, "c")
        assertTrue(q.drain().isEmpty())
        q.offer(0, "a")
        assertEquals(listOf("a", "b", "c"), q.drain())
        // A sentence already played is not played twice.
        q.offer(1, "again")
        assertTrue(q.drain().isEmpty())
        // A sentence that never comes is stepped over.
        q.offer(5, "f"); q.offer(6, "g")
        assertTrue(q.drain().isEmpty())
        assertEquals(listOf("f", "g"), q.skip())
        assertTrue(q.skip().isEmpty())
        q.reset()
        q.offer(0, "x")
        assertEquals(listOf("x"), q.drain())
    }

    // ---------------------------------------------------------- hands-free --
    @Test
    fun handsFreeListensHearsSendsAnswersAndListensAgain() {
        var s = HandsFree.OFF
        fun go(e: HandsFreeEvent) { s = handsFreeNext(s, e) }
        go(HandsFreeEvent.SPEECH_STARTED)
        assertEquals(HandsFree.OFF, s)
        go(HandsFreeEvent.TOGGLE_ON); assertEquals(HandsFree.LISTENING, s)
        go(HandsFreeEvent.SPEECH_STARTED); assertEquals(HandsFree.HEARING, s)
        go(HandsFreeEvent.SILENCE); assertEquals(HandsFree.SENT, s)
        go(HandsFreeEvent.SENT_OK); assertEquals(HandsFree.ANSWERING, s)
        assertTrue(s.micOpen())
        go(HandsFreeEvent.ANSWER_ENDED); assertEquals(HandsFree.LISTENING, s)
        // A turn that could not go: listening goes on.
        go(HandsFreeEvent.SPEECH_STARTED); go(HandsFreeEvent.SILENCE); go(HandsFreeEvent.SEND_FAILED)
        assertEquals(HandsFree.LISTENING, s)
        // Speaking over the answer: the next turn begins at once.
        go(HandsFreeEvent.SPEECH_STARTED); go(HandsFreeEvent.SILENCE); go(HandsFreeEvent.SENT_OK)
        go(HandsFreeEvent.BARGE_IN); assertEquals(HandsFree.HEARING, s)
        go(HandsFreeEvent.TOGGLE_OFF); assertEquals(HandsFree.OFF, s)
        assertFalse(s.micOpen())
        // A second tap on is harmless.
        go(HandsFreeEvent.TOGGLE_ON); go(HandsFreeEvent.TOGGLE_ON); assertEquals(HandsFree.LISTENING, s)
    }

    // --------------------------------------------------------------- the key --
    @Test
    fun aKeyShapedStringNeverStaysInTheComposer() {
        val key = "AIza" + "a".repeat(35)
        val pats = keyPatterns(emptyList())
        assertEquals(key, extractKey(key, pats))
        assertEquals(key, extractKey("این کلید من است $key لطفاً", pats))
        assertNull(extractKey("سلام، حال شما چطور است؟ AIza کوتاه", pats))
        assertEquals("این کلید من است لطفاً", withoutKey("این کلید من است $key لطفاً", key))
        // The hub's own patterns count, and a broken one is skipped.
        val e = Api.json.decodeFromString(VoiceEngine.serializer(), """{"key":"x","provider":"other","key_pattern":"sk-[a-z]{10}"}""")
        val both = keyPatterns(listOf(e, e.copy(keyPattern = "([")))
        assertEquals("sk-abcdefghij", extractKey("sk-abcdefghij", both))
        assertNull(extractKey("x", both))
    }

    // ------------------------------------------------------ meter and cap --
    @Test
    fun theCounterReadsLikeAMeter() {
        assertEquals("0.42", usdNumber(0.42))
        assertEquals("10", usdNumber(10.0))
        assertEquals("0.4", usdNumber(0.4))
        assertEquals("0.01", usdNumber(0.003))
        assertEquals("0", usdNumber(0.0))
        assertEquals("12.5 $", usdText(12.5))
        val m = VoiceMeter(voiceUsd = 0.42, capUsd = 10.0)
        assertEquals("0.42 $ از 10 $ این ماه", meterChip(m))
        assertEquals("0.42 $ این ماه", meterChip(m.copy(capUsd = null)))
        assertEquals("0.06 $ امروز", meterChip(VoiceMeter(period = "today", voiceUsd = 0.06), "today"))
        assertEquals("کنتور صدا", meterChip(null))
        assertEquals(0.042f, capFraction(m)!!, 1e-5f)
        assertNull(capFraction(m.copy(capUsd = null)))
        assertEquals(1f, capFraction(m.copy(voiceUsd = 15.0))!!, 0f)
        assertEquals(Tone.POS, meterTone(m))
        assertEquals(Tone.WARN, meterTone(m.copy(voiceUsd = 8.5)))
        assertEquals(Tone.NEG, meterTone(m.copy(voiceUsd = 10.0)))
        assertEquals(Tone.NEUTRAL, meterTone(m.copy(capUsd = null)))
        // The owner's warning point moves the colour.
        assertEquals(Tone.WARN, meterTone(m.copy(voiceUsd = 5.0), warnAt = 0.5))
    }

    @Test
    fun theCapIsTheOwnersNumber() {
        assertEquals(15.0, parseCap("15")!!, 0.0)
        assertEquals(7.5, parseCap(" ۷٫۵ ")!!, 0.0)
        assertEquals(20.0, parseCap("۲۰")!!, 0.0)
        assertNull(parseCap("0"))
        assertNull(parseCap("-5"))
        assertNull(parseCap("ده"))
        assertNull(parseCap("999999"))
        assertEquals("5 دقیقه", secondsFa(300.0))
        assertEquals("1 دقیقه و 5 ثانیه", secondsFa(65.0))
        assertEquals("42 ثانیه", secondsFa(42.0))
        assertEquals("رایگان بود", sampleCostFa(0.0))
        assertEquals("این نمونه حدود 0.01 $ خرج داشت", sampleCostFa(0.0009))
    }

    @Test
    fun aPriceChangeAheadIsSaidFourteenDaysBefore() {
        val e = Api.json.decodeFromString(VoiceEngine.serializer(), """{"key":"gemini-3.8-flash-tts","provider":"google","price":{"audio_out_per_m":9,"next":{"from":"2027-01-01","audio_out_per_m":18}}}""")
        assertEquals("از 1 ژانویه قیمت دو برابر میشود", priceChangeFa(e.price))
        assertNull(priceChangeFa(e.copy(price = e.price.copy(next = null)).price))
        assertEquals(15L, daysToPriceChange(e.price, LocalDate.of(2026, 12, 17)))
        assertNull(daysToPriceChange(e.price, LocalDate.of(2027, 1, 2)))
        assertNull(priceWarning(listOf(e), listOf(e.key), LocalDate.of(2026, 12, 17)))
        assertEquals("از 1 ژانویه قیمت دو برابر میشود", priceWarning(listOf(e), listOf(e.key), LocalDate.of(2026, 12, 18)))
        // An engine not in use is not warned about.
        assertNull(priceWarning(listOf(e), listOf("piper"), LocalDate.of(2026, 12, 25)))
        val cheaper = e.copy(price = e.price.copy(next = e.price.next!!.copy(audioOutPerM = 4.5)))
        assertEquals("از 1 ژانویه قیمت ارزان‌تر میشود", priceChangeFa(cheaper.price))
    }

    // ----------------------------------------------- the light, the faces --
    @Test
    fun theLightSaysWhyAndWhatToDo() {
        assertEquals(Light.OK, lightOf("ok"))
        assertEquals(Light.CHECKING, lightOf("checking"))
        assertEquals(Light.CAPPED, lightOf("capped"))
        assertEquals(Light.RED, lightOf("missing"))
        assertEquals(Light.RED, lightOf("failing"))
        assertNull(lightFix("ok", null))
        assertTrue(lightFix("missing", null)!!.contains("کلید"))
        assertTrue(lightFix("failing", "صورتحساب این پروژه فعال نیست")!!.contains("صورتحساب"))
        assertTrue(lightFix("failing", "این کلید به مدل صدا دسترسی ندارد")!!.contains("دسترسی"))
        assertTrue(lightFix("failing", "سهمیه تمام شده است")!!.contains("سهمیه"))
        assertTrue(lightFix("capped", null)!!.contains("سقف"))
    }

    @Test
    fun theFacesAreTheFourAndTheManagersInTheRoom() {
        val known = listOf(TalkPersona(key = "manager", role = "ceo", company = "TY", titleFa = "مدیرعامل تریدیار"), TalkPersona(key = "secretary", titleFa = "منشی هلدینگ"))
        val faces = faceOrder(known, listOf("secretary", "ceo@TY", "media@FX"))
        assertEquals(listOf("secretary", "overseer", "assistant", "advisor", "ceo@TY", "media@FX"), faces.map { it.id })
        assertEquals("مدیرعامل تریدیار", personaIdTitle("ceo@TY", known))
        assertEquals("ناظر کل", personaIdTitle("overseer", emptyList()))
        // Before the hub lists anyone, the four still stand there.
        assertEquals(4, faceOrder(emptyList(), emptyList()).size)
        val withVoices = listOf(
            TalkPersona(key = "secretary", voice = com.coinepro.hq.core.net.TalkVoicePick("gemini-3.8-flash-tts", "Kore")),
            TalkPersona(key = "overseer", voice = com.coinepro.hq.core.net.TalkVoicePick("piper", "x")),
            TalkPersona(key = "assistant", voice = com.coinepro.hq.core.net.TalkVoicePick("piper", "y")),
        )
        assertEquals(listOf("gemini-3.8-flash-tts"), enginesInUse(withVoices, listOf("secretary")))
        assertEquals(listOf("gemini-3.8-flash-tts", "piper"), enginesInUse(withVoices, listOf("secretary", "overseer", "assistant")))
    }

    // -------------------------------------------------------------- cards --
    @Test
    fun aCardsFieldsAreEditedInPlace() {
        val payload = Api.json.parseToJsonElement("""{"summary_fa":"خلاصه","unknown":1,"tasks":[{"title_fa":"الف","company":"TY","department":"MEDIA","due":"شنبه","id":9},{"title_fa":"ب","company":"FX","due":"یکشنبه"}]}""").jsonObject
        val fields = payloadFields(payload)
        assertEquals(listOf("خلاصه", "الف", "TY", "MEDIA", "شنبه", "ب", "FX", "یکشنبه"), fields.map { it.value })
        assertEquals("مورد 1", fields[1].group)
        assertNull(fields[0].group)
        val edited = applyPayloadEdits(payload, mapOf(listOf("tasks", "1", "due") to "دوشنبه", listOf("summary_fa") to "تازه"))
        assertEquals("دوشنبه", edited["tasks"]!!.let { (it as kotlinx.serialization.json.JsonArray)[1].jsonObject["due"]!!.jsonPrimitive.content })
        assertEquals("تازه", edited["summary_fa"]!!.jsonPrimitive.content)
        // What the owner did not touch stays as the hub sent it.
        assertEquals("شنبه", (edited["tasks"] as kotlinx.serialization.json.JsonArray)[0].jsonObject["due"]!!.jsonPrimitive.content)
        assertEquals(1, edited["unknown"]!!.jsonPrimitive.content.toInt())
        assertEquals(9, (edited["tasks"] as kotlinx.serialization.json.JsonArray)[0].jsonObject["id"]!!.jsonPrimitive.content.toInt())
    }

    // -------------------------------------------------------------- calls --
    @Test
    fun aTurnGoesWithItsClientIdAsTheIdempotencyKey() = runTest {
        server.enqueue(json(202, """{"turn":{"id":7,"conversation":"CV-0001","n":2,"by":"secretary","state":"streaming"},"events":"/api/v1/talk/turns/7/events"}"""))
        val out = api.sendTalkTurn("CV-0001", "سلام", "hold", "cid-123456789")
        val r = server.takeRequest()
        assertEquals("POST", r.method)
        assertEquals("/api/v1/talk/conversations/CV-0001/turns", r.url.encodedPath)
        assertEquals("cid-123456789", r.headers["Idempotency-Key"])
        val body = Api.json.parseToJsonElement(r.body!!.utf8()).jsonObject
        assertEquals("hold", body["source"]!!.jsonPrimitive.content)
        assertEquals("cid-123456789", body["client_id"]!!.jsonPrimitive.content)
        assertEquals("7", out.turn.idText)
        assertEquals("/api/v1/talk/turns/7/events", out.events)
    }

    @Test
    fun theKeyIsSealedOnItsProviderAndWriteOnly() = runTest {
        server.enqueue(json(202, """{"state":"checking"}"""))
        val out = api.putVoiceSecret("google", "AIza" + "b".repeat(35), stepUp)
        assertEquals("checking", out.state)
        val r = server.takeRequest()
        assertEquals("PUT", r.method)
        assertEquals("/api/v1/voice/providers/google/secret", r.url.encodedPath)
        assertEquals("su-token", r.headers["X-Step-Up"])
        assertEquals(listOf("voice.secret" to "google"), signed)
        // Nothing of the key comes back; the answer is only the state.
        assertFalse(out.toString().contains("AIza"))
    }

    @Test
    fun aCardIsSealedOnlyWhenItsRouteWantsIt() = runTest {
        server.enqueue(problem(403, "step_up_required"))
        server.enqueue(json(200, """{"made":["D-000091"]}"""))
        val out = api.runTalkCard("TC-201", buildJsonObject { put("title_fa", "x") }, stepUp)
        assertEquals(listOf("D-000091"), out.made)
        val first = server.takeRequest()
        assertNull(first.headers["X-Step-Up"])
        assertEquals("/api/v1/talk/cards/TC-201/run", first.url.encodedPath)
        assertEquals("x", Api.json.parseToJsonElement(first.body!!.utf8()).jsonObject["payload"]!!.jsonObject["title_fa"]!!.jsonPrimitive.content)
        assertEquals("su-token", server.takeRequest().headers["X-Step-Up"])
        assertEquals(1, signed.size)
        // Any other refusal reaches the owner as it is.
        server.enqueue(problem(422, "validation_failed"))
        try {
            api.runTalkCard("TC-202", null, stepUp)
            org.junit.Assert.fail("expected a refusal")
        } catch (e: ApiException) {
            assertEquals(422, e.status)
        }
        assertEquals(1, signed.size)
    }

    @Test
    fun stoppingATurnAndTheRoutesOfTheVoice() = runTest {
        server.enqueue(json(200, """{"state":"stopped"}"""))
        api.stopTalkTurn("7")
        assertEquals("/api/v1/talk/turns/7/stop", server.takeRequest().url.encodedPath)
        server.enqueue(json(200, """[{"key":"piper","provider":"local","state":"ok"}]"""))
        assertEquals("piper", api.voiceEngines().single().key)
        server.takeRequest()
        server.enqueue(json(200, """{"period":"today","voice_usd":0.1}"""))
        api.voiceMeter("today")
        val m = server.takeRequest()
        assertEquals("today", m.url.queryParameter("period"))
        server.enqueue(json(200, """{"items":[{"ref":"CV-0001"}],"next_cursor":null}"""))
        assertEquals("CV-0001", api.talkConversations(persona = "secretary", q = "طلا").single().ref)
        val c = server.takeRequest()
        assertEquals("طلا", c.url.queryParameter("q"))
        assertEquals("secretary", c.url.queryParameter("persona"))
        server.enqueue(json(201, """{"ref":"CV-0002","persona":"manager"}"""))
        api.newTalkConversation("manager", "ceo", "TY")
        val n = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals("TY", n["company"]!!.jsonPrimitive.contentOrNull)
        assertEquals("ceo", n["role"]!!.jsonPrimitive.content)
    }
}
