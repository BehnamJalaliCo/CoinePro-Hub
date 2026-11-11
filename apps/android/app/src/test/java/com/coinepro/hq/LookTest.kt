package com.coinepro.hq

import androidx.compose.ui.text.AnnotatedString
import com.coinepro.hq.core.data.CommandCompany
import com.coinepro.hq.core.data.COMMAND_TEMPLATES
import com.coinepro.hq.core.data.DECIDE_YOURSELF_FA
import com.coinepro.hq.core.data.LEVEL3_OF
import com.coinepro.hq.core.data.accountPercent
import com.coinepro.hq.core.data.accountShare
import com.coinepro.hq.core.data.allFullFa
import com.coinepro.hq.core.data.asksOwner
import com.coinepro.hq.core.data.commandReady
import com.coinepro.hq.core.data.commandWords
import com.coinepro.hq.core.data.dayLabelFa
import com.coinepro.hq.core.data.humanize
import com.coinepro.hq.core.data.inFa
import com.coinepro.hq.core.data.level3
import com.coinepro.hq.core.data.limitsReadAt
import com.coinepro.hq.core.data.meterShare
import com.coinepro.hq.core.data.meterState
import com.coinepro.hq.core.data.monthVerdict
import com.coinepro.hq.core.data.namesFa
import com.coinepro.hq.core.data.pulseOf
import com.coinepro.hq.core.data.queueOpensAt
import com.coinepro.hq.core.data.readyAnswers
import com.coinepro.hq.core.data.seeded
import com.coinepro.hq.core.data.standingFa
import com.coinepro.hq.core.data.state3
import com.coinepro.hq.core.data.taskLineFa
import com.coinepro.hq.core.data.templateText
import com.coinepro.hq.core.data.turnCount
import com.coinepro.hq.core.data.waitedFa
import com.coinepro.hq.core.data.LiveState
import com.coinepro.hq.core.format.ROUTE_NOT_READY_FA
import com.coinepro.hq.core.format.ltr
import com.coinepro.hq.core.format.ownerNote
import com.coinepro.hq.core.format.pct
import com.coinepro.hq.core.format.unltr
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.ClaudeAccount
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Limits
import com.coinepro.hq.core.net.LiveSummary
import com.coinepro.hq.core.net.Notification
import com.coinepro.hq.core.net.Office
import com.coinepro.hq.core.net.SessionCard
import com.coinepro.hq.core.net.TaskCount
import com.coinepro.hq.core.net.TodayMeter
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.commandOrder
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.FigureFace
import com.coinepro.hq.designsystem.MdParser
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.inlineOf
import com.coinepro.hq.designsystem.latinRanges
import com.coinepro.hq.designsystem.sepsFa
import com.coinepro.hq.designsystem.shape
import com.coinepro.hq.designsystem.timesFig
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
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
 * ⟨1.0.1⟩ Part C, the look (docs/UI_V1_0_1_LOOK_SPEC.md), without a screen: the text rules of C0.4 and the three bidi defects of C1
 * (one Latin token is one run; «·» is the hairline; a percent is a figure), the wording of C1.4 (no command and no «کلید ندارد» to the
 * owner), a table that fits before it scrolls, the command sheet's words and its order on the wire (with a hub that takes no company),
 * the ready answers of a question, the three states and the three levels, a machine title said in Persian, and the limits of the
 * treasury as the hub writes them (and a hub before them).
 */
@RunWith(RobolectricTestRunner::class)
class LookTest {
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

    /** The runs set Latin in [a], each as it reads (without its isolate marks and joiners). */
    private fun figures(a: AnnotatedString): List<String> =
        a.spanStyles.filter { it.item.fontFamily == FigureFace }.map { a.text.substring(it.start, it.end).trim('⁦', '⁩').replace("⁠", "") }

    private fun runs(text: String, numbers: Boolean = false): List<String> = latinRanges(text, numbers).map { text.substring(it) }

    // ------------------------------------------------------------------ C0.4 / C1.1 one token, one run --
    @Test
    fun aLatinTokenIsOneRunWhateverItIsMadeOf() {
        // «P0» was drawn «0P» in the stop sheet: its digit was isolated apart from its letter.
        assertEquals(listOf("P0"), runs("فقط کارهای اضطراری (P0) اجرا میشوند.", numbers = true))
        assertEquals(listOf("P0"), figures(com.coinepro.hq.ui.v14.figs("فقط کارهای اضطراری (P0) اجرا میشوند.")))
        // The cost label of the server seal card («ماهUSD/ 18-») and the impact chip («ماهUSDT/ 640+»): the amount, its sign and its
        // unit are one run, and the slash that leads on to the Persian word stays outside it.
        assertEquals(listOf("-18 USD"), runs("-18 USD/ماه"))
        assertEquals(listOf("+640 USDT"), runs("+640 USDT/ماه"))
        assertEquals(listOf("+640 USDT"), figures(timesFig("+640 USDT/ماه")))
        assertTrue(timesFig("+640 USDT/ماه").text.endsWith("⁩/ماه"))
        // The advisor's commission («۶۰۹۴/ USDT»): the amount and its unit are one Latin run, its point Latin.
        val line = "کمیسیون دیروز تریدیار 94.60 USDT بود"
        assertEquals(listOf("94.60 USDT"), runs(line))
        assertEquals(listOf("94.60 USDT"), figures(inlineOf(line)))
        assertFalse(inlineOf(line).text.contains("٫"))
        // A ref, a handle, a file name, money, a percent: each one run.
        assertEquals(listOf("O-000152"), runs("خروجی O-000152 را ببین"))
        assertEquals(listOf("@tradeyar"), runs("حساب @tradeyar"))
        assertEquals(listOf("reel-final.mp4"), runs("فایل reel-final.mp4 رسید"))
        assertEquals(listOf("$12.40"), runs("معادل $12.40 این ماه"))
        assertEquals(listOf("-$3.20"), runs("خرج -$3.20 شد"))
        assertEquals(listOf("21%"), runs("از سقف 21% رفته"))
        assertEquals(listOf("2026-10-17 14:00"), runs("در 2026-10-17 14:00 ثبت شد"))
        // A mark that only ends the sentence stays outside; a prose dash and a bare count are not amounts.
        assertEquals(listOf("+640"), runs("رشد +640."))
        assertEquals(emptyList<String>(), runs("مصرف - 5 بار و ۳ کار"))
        assertEquals(listOf("500", "90"), runs("500 در 90 روز", numbers = true))
        // A run already isolated is left as it is.
        val once = timesFig(ltr("@tradeyar") + " منتشر شد")
        assertEquals(1, Regex("⁦").findAll(once.text).count())
    }

    @Test
    fun aPlainStringIsShapedOnlyWhenItNeedsIt() {
        // Most Persian sentences and most bare codes are drawn as they are.
        assertNull(shape("هر فرمان یک جلسه است"))
        assertNull(shape("۳ کار و 5 پیام"))
        assertNull(shape("claude-max"))
        // Persian with a Latin token: isolated, Latin digits.
        assertEquals(listOf("P0"), figures(shape("فقط کارهای اضطراری (P0) اجرا میشوند.")!!))
        assertEquals(listOf("21%"), figures(shape("از سقف 21% رفته")!!))
        // No Persian in it: its own direction is kept (no isolate), only its digits are not drawn Persian.
        val code = shape("FX-QUANT-02")!!
        assertEquals("FX-QUANT-02", code.text)
        assertEquals(FigureFace, code.spanStyles.single().item.fontFamily)
        // «·» between facts is the hairline: read aloud, and copied, as a Persian comma («۲ از ۴ کار» never reads «۲۰ از ۴ کار»).
        assertEquals("مدیرعامل تریدیار، \u200F۲ از ۴ کار، \u200F۶ دقیقه پیش", shape("مدیرعامل تریدیار · ۲ از ۴ کار · ۶ دقیقه پیش")!!.text)
        assertEquals("، \u200Fبازنشسته", shape("· بازنشسته")!!.text)
        assertEquals("غیرتجاری، \u200F", shape("غیرتجاری ·")!!.text)
        assertEquals("۴۲ موضوع، ۴۰ نمونه", sepsFa("۴۲ موضوع · ۴۰ نمونه"))
        assertEquals("اینستاگرام، \u200F⁦@tradeyar⁩", facts("اینستاگرام", null, " ", "@tradeyar").text)
        // A long English passage wraps at its spaces like any text (no joiner); a short Latin run stays whole.
        val long = "خطا: " + "Expected Int but the hub answered with a number that carries a fraction 412.6"
        assertFalse(timesFig(long).text.contains("⁠"))
        assertTrue(timesFig("مدل GPT 5.5 آماده است").text.contains("GPT ⁠5.5"))
    }

    @Test
    fun theIsolateHelperAndThePercent() {
        assertEquals("⁦O-000152⁩", ltr("O-000152"))
        assertEquals(ltr("P0"), ltr(ltr("P0")))
        assertEquals("—", ltr("—"))
        assertEquals("", ltr(null))
        assertEquals("O-000152", unltr(ltr("O-000152")))
        // A percent is a figure (Latin tabular digits), like money and a rank.
        assertEquals("21%", pct(21.4))
        assertEquals("—", pct(null))
    }

    // ------------------------------------------------------------------ C1.3 a table fits before it scrolls --
    @Test
    fun aTableThatIsALittleWideFitsByWrappingItsText() {
        // Wider than the card, but its text columns can wrap: every column keeps at least its floor, and the table is as wide as the card.
        val fit = MdParser.fitWidths(listOf(210, 130, 80, 100), floors = listOf(90, 70, 60, 80), available = 368)
        assertEquals(368, fit!!.sum())
        assertTrue(fit.zip(listOf(90, 70, 60, 80)).all { (w, f) -> w >= f })
        // Even its floors are wider than the card: it scrolls sideways inside its card instead (null).
        assertNull(MdParser.fitWidths(List(9) { 150 }, floors = List(9) { 100 }, available = 400))
        // It fits already: nothing to do.
        assertNull(MdParser.fitWidths(listOf(100, 100), floors = listOf(50, 50), available = 400))
    }

    // ------------------------------------------------------------------ C1.4 the owner's decisions --
    @Test
    fun aCommandIsNeverTheOwnersStepAndAnAccountIsNeverKeyless() {
        val note = "استوری کانال تلگرام در Bot API نیست: فایل را بردار و خودت بگذار. اینستاگرام تریدیار هنوز کلید ندارد؛ با make account-secret واردش کن."
        val n = ownerNote(note)
        assertFalse(n.fa.contains("make"))
        assertFalse(n.fa.contains("کلید ندارد"))
        assertTrue(n.fa.startsWith("استوری کانال تلگرام"))
        assertTrue(n.fa.endsWith(ROUTE_NOT_READY_FA))
        assertTrue(n.technical!!.contains("make account-secret"))
        // A note without a command is the owner's as it is.
        assertEquals("ناظر کل این را نگه داشته است.", ownerNote("ناظر کل این را نگه داشته است.").fa)
        assertNull(ownerNote("ناظر کل این را نگه داشته است.").technical)
        assertEquals("", ownerNote(null).fa)
                assertFalse(com.coinepro.hq.ui.v19.PUBLISH_ERROR.getValue("account_not_configured").contains("کلید"))
    }

    // ------------------------------------------------------------------ C2.1 the command --
    @Test
    fun theTemplatesOnlyFillTheStartingText() {
        val reel = COMMAND_TEMPLATES.first { it.key == "reel" }
        assertEquals("یک ریلز اینستاگرام بساز: ", templateText(reel, emptyList()))
        assertEquals("برای تریدیار یک ریلز اینستاگرام بساز: ", templateText(reel, listOf("تریدیار")))
        assertEquals("برای تریدیار و پرو-چارت یک موشن‌گرافی بساز: ", templateText(COMMAND_TEMPLATES.first { it.key == "motion" }, listOf("تریدیار", "پرو-چارت")))
        assertEquals("تریدیار، پرو-چارت و کوینه‌پرو FX", namesFa(listOf("تریدیار", "پرو-چارت", "کوینه‌پرو FX")))
        assertEquals("", namesFa(emptyList()))
        // Several companies: the words name them all, unless the owner's words do already.
        assertEquals("برای تریدیار و پرو-چارت: یک ریلز بساز", commandWords(" یک ریلز بساز ", listOf("تریدیار", "پرو-چارت")))
        assertEquals("برای تریدیار و پرو-چارت یک ریلز بساز", commandWords("برای تریدیار و پرو-چارت یک ریلز بساز", listOf("تریدیار", "پرو-چارت")))
        assertEquals("یک ریلز بساز", commandWords("یک ریلز بساز", emptyList()))
        assertFalse(commandReady("  ب "))
        assertTrue(commandReady("بساز"))
    }

    private val order = """{"ref":"F-0200","summary_fa":"رسید.","routes":[],"routed_by":"rules","pace":"step"}"""

    @Test
    fun oneCompanyGoesWithTheOrderSeveralGoInItsWords() = runTest {
        // One company picked by its mark: the order carries it, on the existing new-order call.
        server.enqueue(json(201, order))
        assertEquals("F-0200", api.commandOrder("یک ریلز بساز", listOf(CommandCompany("TY", "تریدیار")), "step").ref)
        val one = server.takeRequest()
        assertEquals("POST", one.method)
        assertEquals("/api/v1/orders", one.url.encodedPath)
        val b1 = Api.json.parseToJsonElement(one.body!!.utf8()).jsonObject
        assertEquals("TY", b1["company"]!!.jsonPrimitive.content)
        assertEquals("step", b1["pace"]!!.jsonPrimitive.content)
        assertEquals("یک ریلز بساز", b1["text"]!!.jsonPrimitive.content)
        // Several: the hub takes one company per order, so the words name them and the order goes to the holding.
        server.enqueue(json(201, order))
        api.commandOrder("یک ریلز بساز", listOf(CommandCompany("TY", "تریدیار"), CommandCompany("PC", "پرو-چارت")), "auto")
        val b2 = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertNull(b2["company"])
        assertEquals("برای تریدیار و پرو-چارت: یک ریلز بساز", b2["text"]!!.jsonPrimitive.content)
        // None: the holding decides.
        server.enqueue(json(201, order))
        api.commandOrder("یک ریلز بساز", emptyList(), "auto")
        val b3 = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertNull(b3["company"])
        assertEquals("یک ریلز بساز", b3["text"]!!.jsonPrimitive.content)
    }

    @Test
    fun aHubThatTakesNoCompanyGetsItInTheWordsAndIsNotAskedAgain() = runTest {
        server.enqueue(json(422, """{"type":"about:blank","title":"validation_failed","status":422,"code":"validation_failed","message_fa":"ورودی درست نیست.","fields":{"company":"Extra inputs are not permitted"}}"""))
        server.enqueue(json(201, order))
        assertEquals("F-0200", api.commandOrder("یک ریلز بساز", listOf(CommandCompany("TY", "تریدیار")), "step").ref)
        server.takeRequest()
        val again = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertNull(again["company"])
        assertEquals("برای تریدیار: یک ریلز بساز", again["text"]!!.jsonPrimitive.content)
        assertFalse(api.gaps.has(HubFeature.ORDER_COMPANY))
        // Learnt once per app start: the next order goes without the field at once.
        server.enqueue(json(201, order))
        api.commandOrder("یک پست بساز", listOf(CommandCompany("TY", "تریدیار")), "auto")
        assertNull(Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject["company"])
        assertEquals(3, server.requestCount)
        // The hub's own refusal of an order is its answer (its Persian sentence stands above the bar).
        server.enqueue(json(503, """{"type":"about:blank","title":"hub_unavailable","status":503,"code":"hub_unavailable","message_fa":"ستاد الان جواب نمیدهد؛ کمی بعد دوباره بزن."}"""))
        try { api.commandOrder("یک ریلز بساز", emptyList(), "auto"); fail("expected ApiException") } catch (e: ApiException) { assertEquals("ستاد الان جواب نمیدهد؛ کمی بعد دوباره بزن.", e.messageFa) }
    }

    @Test
    fun aRoutineFromOneSentenceNamesItsCompany() = runTest {
        server.enqueue(json(201, """{"ref":"AT-0903","company":"PC","sentence_fa":"هر روز ساعت ۹ رتبه‌ها را ببین","when_fa":"هر روز ساعت 09:00","preview_fa":"یک کار تازه ساخته میشود","state":"on","next_at":"2026-10-18T05:30:00Z"}"""))
        val r = api.newRoutine("هر روز ساعت ۹ رتبه‌ها را ببین", null, "key-1", "PC")
        val req = server.takeRequest()
        assertEquals("/api/v1/routines", req.url.encodedPath)
        assertEquals("key-1", req.headers["Idempotency-Key"])
        val b = Api.json.parseToJsonElement(req.body!!.utf8()).jsonObject
        assertEquals("PC", b["company"]!!.jsonPrimitive.content)
        assertNull(b["order"])
        assertEquals("هر روز ساعت 09:00", r.whenFa)
    }

    // ------------------------------------------------------------------ C2.2 / C3 the ready answers --
    @Test
    fun aQuestionOffersItsOwnAnswers() {
        assertEquals(listOf("اول ریلزها", "اول پست‌ها"), readyAnswers("کدام را اول منتشر کنم: «اول ریلزها» یا «اول پست‌ها»؟"))
        assertEquals(listOf("امروز منتشر کنم", "فردا صبح"), readyAnswers("ریلز آماده است. امروز منتشر کنم یا فردا صبح؟"))
        assertEquals(listOf("اول ریلزها منتشر شود", "پست‌ها"), readyAnswers("مدیرعامل تریدیار میپرسد: اول ریلزها منتشر شود یا پست‌ها؟"))
        // The hub's quick replies win; an open question offers nothing (only «خودت تصمیم بگیر و ادامه بده» stands).
        assertEquals(listOf("بله", "نه"), readyAnswers("منتشر کنم یا نه؟", listOf(" بله ", "نه", "")))
        assertEquals(emptyList<String>(), readyAnswers("برای کاور چه رنگی میخواهی؟"))
        assertEquals(emptyList<String>(), readyAnswers(null))
        assertTrue(DECIDE_YOURSELF_FA.isNotBlank())
    }

    // ------------------------------------------------------------------ C3.1 three states --
    @Test
    fun aSessionIsInOneOfThreeStates() {
        assertEquals(listOf("waiting", "waiting", "working", "working", "done"), listOf("your_turn", "ready", "stuck", "moving", "closed").map(::state3))
        val now = java.time.Instant.parse("2026-10-17T08:30:00Z").toEpochMilli()
        assertEquals("۶ دقیقه منتظر".replace("۶", "6"), waitedFa("2026-10-17T08:24:00Z", now))
        assertEquals("همین الان", waitedFa("2026-10-17T08:29:50Z", now))
        assertEquals("2 ساعت منتظر", waitedFa("2026-10-17T06:30:00Z", now))
        assertEquals("3 روز منتظر", waitedFa("2026-10-14T08:30:00Z", now))
        assertNull(waitedFa(null, now))
        val s = SessionCard("F-0101", badge = "your_turn", tasks = TaskCount(2, 4))
        assertEquals("کار 3 از 4 ایستاده", standingFa(s))
        assertEquals("کار 3 از 4", taskLineFa(s))
        assertNull(standingFa(s.copy(tasks = TaskCount(4, 4))))
        assertEquals("کار 4 از 4", taskLineFa(s.copy(badge = "closed", tasks = TaskCount(4, 4))))
        assertNull(taskLineFa(s.copy(tasks = TaskCount())))
        // What waits for him: sessions in his turn or ready for his approval, and the cards for his decision (hidden and closed ones out).
        val office = Office(
            sessions = listOf(s, s.copy(ref = "F-0102", badge = "ready"), s.copy(ref = "F-0103", badge = "stuck"), s.copy(ref = "F-0104", badge = "your_turn", hidden = true)),
            approvalsTotal = 10,
        )
        assertEquals(12, turnCount(office))
        assertEquals(0, turnCount(Office()))
    }

    @Test
    fun thePulseCountsEveryOpenSessionAndCarriesItsSeries() {
        val summary = Api.json.decodeFromString(
            LiveSummary.serializer(),
            """{"seq":7,"at":"2026-10-17T08:30:00Z","people":{"working":5,"thinking":1,"waiting":2,"stuck":0,"total":28},
               "sessions":{"moving":2,"your_turn":1,"stuck":1,"ready":1},"approvals":10,"urgent_unread":0,"servers":{},"tokens":{},"control":{},"companies":[],
               "series":{"working":[1,2,3],"sessions":[2,2,5],"waiting":[9,10,11],"until":"2026-10-17T08:30:00Z"}}""",
        )
        val live = seeded(LiveState(), summary, null, 1_000)
        val p = pulseOf(live, 2_000)
        assertEquals(6, p.working)
        assertEquals(5, p.open)
        assertEquals(11, p.waitingYou)
        assertEquals(1_000L, p.readAt)
        assertEquals(listOf(2.0, 2.0, 5.0), live.series!!.sessions)
        // A hub that sends no series: the numbers stand alone; a later summary without one keeps the last.
        val bare = Api.json.decodeFromString(LiveSummary.serializer(), """{"seq":8,"at":"2026-10-17T08:31:00Z","people":{},"sessions":{},"approvals":0,"urgent_unread":0,"servers":{},"tokens":{},"control":{},"companies":[]}""")
        assertNull(seeded(LiveState(), bare, null, 1_000).series)
        assertNotNull(seeded(live, bare, null, 3_000).series)
        assertNull(pulseOf(seeded(LiveState(), bare, null, 1_000), 2_000).open)
    }

    // ------------------------------------------------------------------ C3.5 three levels --
    private fun note(level: String, readAt: String? = null, answer: String? = null) =
        Notification(id = "n-$level", level = level, company = "TY", titleFa = "t", createdAt = "2026-10-17T08:00:00Z", readAt = readAt, answer = answer)

    @Test
    fun aNotificationIsInOneOfThreeLevels() {
        assertEquals(listOf("urgent", "decision", "news", "news", "news"), listOf("urgent", "decision", "report", "info", "learning").map(::level3))
        assertEquals(listOf("report", "info", "learning"), LEVEL3_OF.getValue("news"))
        // «از تو کاری میخواهد»: urgent or a decision, not read and not answered.
        assertTrue(asksOwner(note("urgent")))
        assertTrue(asksOwner(note("decision")))
        assertFalse(asksOwner(note("report")))
        assertFalse(asksOwner(note("decision", readAt = "2026-10-17T08:10:00Z")))
        assertFalse(asksOwner(note("decision", answer = "yes")))
        val now = java.time.Instant.parse("2026-10-17T08:30:00Z").toEpochMilli()
        assertEquals("امروز", dayLabelFa("2026-10-17T05:00:00Z", now))
        // The owner's day, not the hub's: 21:00 UTC is already the next day in Tehran.
        assertEquals("امروز", dayLabelFa("2026-10-16T21:00:00Z", now))
        assertEquals("دیروز", dayLabelFa("2026-10-16T10:00:00Z", now))
        assertFalse(dayLabelFa("2026-10-10T10:00:00Z", now) in setOf("امروز", "دیروز", "—"))
    }

    @Test
    fun aMachineTitleIsSaidInPersian() {
        val names = { code: String -> mapOf("TY" to "تریدیار")[code] }
        assertEquals("یافته‌ی جدی ناظر کل: سلامت خود هاب؛ دیسک ۹۰٪ پر است؛ دو سرویس پایین است", humanize("یافته‌ی جدی ناظر کل: سلامت خود هاب — disk 90.4%; down: otel-collector, tempo", names))
        assertEquals("بودجه‌ی تریدیار به ۷۲٪ رسید", humanize("بودجه‌ی company:TY (2026-10) به ۷۲٪ رسید", names))
        assertEquals("حافظه ۸۸٪ پر است", humanize("memory 88%"))
        assertEquals("یک سرویس پایین است", humanize("down: tempo"))
        // What it does not know it leaves as it is (the raw text is then not offered).
        assertEquals("جلسه‌ی هیئت‌مدیره‌ی هلدینگ شروع شد", humanize("جلسه‌ی هیئت‌مدیره‌ی هلدینگ شروع شد", names))
        assertEquals("", humanize(null))
        // A row never shows a ref; the dot that joined it to the next fact goes with it (never a doubled or a leading separator).
        val bare = { t: String -> com.coinepro.hq.core.format.withoutCodes(t) }
        assertEquals("مدیر کل حاضر است، دستورِ جلسه سه بند دارد", bare("MT-0012 · مدیر کل حاضر است، دستورِ جلسه سه بند دارد"))
        assertEquals("ریسک بالا · ۶ ساعت تا انقضا", bare("ریسک بالا · D-000085 · ۶ ساعت تا انقضا"))
        assertEquals("ریسک بالا", bare("ریسک بالا · D-000085"))
    }

    // ------------------------------------------------------------------ C3.6 the limits --
    @Test
    fun theLimitsReadAsTheHubWritesThem() = runTest {
        server.enqueue(json(200, """{"accounts":[
            {"key":"main","name_fa":"اکانت اصلی","state":"full","utilization":"1","window_fa":"پنجره‌ی پنج‌ساعته","resets_at":"2026-10-17T10:40:00Z","observed_at":"2026-10-17T08:28:00Z"},
            {"key":"second","name_fa":"اکانت دوم","state":"working","utilization":0.41,"resets_at":"2026-10-17T11:40:00Z","observed_at":"2026-10-17T08:27:00Z"},
            {"key":"third","name_fa":"اکانت سوم","state":"off"}],
            "waiting":false,"today":{"spent":456000,"cap":600000,"share":"0.7600","state":"warm","resets_at":"2026-10-17T20:30:00Z","note_fa":"از ۷۰٪ سقف امروز گذشته‌ای؛ هنوز جا هست."}}"""))
        val l = api.gated(HubFeature.LIMITS) { limits() }!!
        assertEquals("/api/v1/treasury/limits", server.takeRequest().url.encodedPath)
        assertEquals(3, l.accounts.size)
        val (main, second, third) = l.accounts
        assertEquals(1.0, main.utilization!!, 1e-9)
        assertEquals(0.41, second.utilization!!, 1e-9)
        assertNull(third.utilization)
        // A full one is whole whatever its figure says; one that is off draws nothing; an unknown one shows a dash.
        assertEquals(1f, accountShare(main.copy(utilization = 0.97))!!, 1e-6f)
        assertEquals(0.41f, accountShare(second)!!, 1e-6f)
        assertNull(accountShare(third))
        assertEquals("41%", accountPercent(second))
        assertEquals("—", accountPercent(third))
        assertEquals("2026-10-17T08:28:00Z", limitsReadAt(l))
        assertEquals("2026-10-17T10:40:00Z", queueOpensAt(l))
        assertEquals(0.76, meterShare(l.today), 1e-9)
        assertEquals("warm", meterState(l.today))
        val now = java.time.Instant.parse("2026-10-17T08:30:00Z").toEpochMilli()
        assertEquals("2 ساعت و 10 دقیقه دیگر", inFa(main.resetsAt, now))
        assertEquals("40 دقیقه دیگر", inFa("2026-10-17T09:10:00Z", now))
        assertEquals("3 ساعت دیگر", inFa("2026-10-17T11:30:00Z", now))
        assertEquals("1 روز و 2 ساعت دیگر", inFa("2026-10-18T10:30:00Z", now))
        assertEquals("کمتر از یک دقیقه دیگر", inFa("2026-10-17T08:30:20Z", now))
        assertNull(inFa("2026-10-17T08:00:00Z", now))
        assertNull(inFa(null, now))
    }

    @Test
    fun theMetersStateAndTheWordsOfAFullQueue() {
        // The hub's own word, else read from the share (a state this app does not know is read from the share too).
        assertEquals(listOf("calm", "warm", "near", "full"), listOf(0.2, 0.7, 0.93, 1.02).map { meterState(TodayMeter(share = it)) })
        assertEquals("near", meterState(TodayMeter(share = 0.2, state = "near")))
        assertEquals("calm", meterState(TodayMeter(share = 0.2, state = "odd")))
        assertEquals(0.5, meterShare(TodayMeter(spent = 300, cap = 600)), 1e-9)
        assertEquals(0.0, meterShare(TodayMeter()), 1e-9)
        // The accounts are data, never a fixed two.
        assertEquals("هر دو اکانت پر است", allFullFa(2))
        assertEquals("همه‌ی اکانت‌ها پر است", allFullFa(3))
        assertNull(queueOpensAt(Limits(accounts = listOf(ClaudeAccount("main", state = "ready", resetsAt = "2026-10-17T10:40:00Z")))))
        assertNull(limitsReadAt(Limits()))
        // «تا آخر ماه میرسم یا نه»: this month's pace against its cap.
        val day10 = java.time.Instant.parse("2026-10-10T12:00:00Z").toEpochMilli()
        assertEquals("pos", monthVerdict(6_200_000, 30_000_000, day10)!!.first)
        assertEquals("warn", monthVerdict(9_000_000, 30_000_000, day10)!!.first)
        assertEquals("neg" to "با این آهنگ، حدود روز 20 ماه به سقف میرسی.", monthVerdict(15_000_000, 30_000_000, day10))
        assertEquals("neg" to "سقف این ماه پر شده است.", monthVerdict(30_000_000, 30_000_000, day10))
        assertNull(monthVerdict(1, null, day10))
    }

    /** Every field the hub's own schema has is read (`apps/api/openapi/hq-api.v1.json`), and no other is expected of it. */
    @Test
    fun theModelsMatchTheHubsOpenApi() {
        val doc = Api.json.parseToJsonElement(java.io.File("../../api/openapi/hq-api.v1.json").readText()).jsonObject
        val schemas = doc["components"]!!.jsonObject["schemas"]!!.jsonObject
        org.junit.Assume.assumeTrue("the hub's §55 schemas are in this tree's OpenAPI", "ClaudeAccount" in schemas)
        fun snake(s: String) = s.replace(Regex("([A-Z])")) { "_" + it.value.lowercase() }
        val models = mapOf("Limits-Output" to Limits.serializer().descriptor, "ClaudeAccount" to ClaudeAccount.serializer().descriptor, "TodayMeter" to TodayMeter.serializer().descriptor)
        for ((name, d) in models) {
            val theirs = schemas[name]!!.jsonObject["properties"]!!.jsonObject.keys.sorted()
            val ours = (0 until d.elementsCount).map { snake(d.getElementName(it)) }.sorted()
            assertEquals("$name: the app reads every field the hub sends, and no other", theirs, ours)
        }
        // The routes the look calls are the hub's own: the limits, an order that names its company, a routine that names its company.
        val paths = doc["paths"]!!.jsonObject
        assertTrue("get" in paths["/api/v1/treasury/limits"]!!.jsonObject)
        assertTrue("company" in schemas["hq_api__routes__orders__OrderIn"]!!.jsonObject["properties"]!!.jsonObject)
        assertTrue("company" in schemas["RoutineIn"]!!.jsonObject["properties"]!!.jsonObject)
    }

    @Test
    fun aHubBeforeTheLimitsHidesThemWithoutAnError() = runTest {
        server.enqueue(json(404, """{"detail":"Not Found"}"""))
        assertNull(api.gated(HubFeature.LIMITS) { limits() })
        assertFalse(api.gaps.has(HubFeature.LIMITS))
        assertNull(api.gated(HubFeature.LIMITS) { fail("not asked again"); limits() })
        assertEquals(1, server.requestCount)
        assertNotNull(HubFeature.valueOf("ORDER_COMPANY"))
        // An account the hub writes with nothing but its key and its state still reads.
        assertEquals(JsonNull, Api.json.parseToJsonElement("""{"utilization":null}""").jsonObject["utilization"])
        assertEquals("ready", Api.json.decodeFromString(ClaudeAccount.serializer(), """{"key":"main"}""").state)
    }
}
