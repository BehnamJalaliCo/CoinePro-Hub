package com.coinepro.hq

import com.coinepro.hq.core.data.DESK_EMPTY_FA
import com.coinepro.hq.core.data.DIRECT_NOW_FA
import com.coinepro.hq.core.data.MEMBER_STILL_FA
import com.coinepro.hq.core.data.deskDayFa
import com.coinepro.hq.core.data.deskEmpty
import com.coinepro.hq.core.data.deskLead
import com.coinepro.hq.core.data.deskLineFa
import com.coinepro.hq.core.data.deskQueueWordFa
import com.coinepro.hq.core.data.deskRatio
import com.coinepro.hq.core.data.deskSorted
import com.coinepro.hq.core.data.faceOf
import com.coinepro.hq.core.data.isTurn
import com.coinepro.hq.core.data.knotWhy
import com.coinepro.hq.core.data.lastSeven
import com.coinepro.hq.core.data.leadFile
import com.coinepro.hq.core.data.leadKnot
import com.coinepro.hq.core.data.leadWorker
import com.coinepro.hq.core.data.liveWorkRef
import com.coinepro.hq.core.data.memberLook
import com.coinepro.hq.core.data.memberWordFa
import com.coinepro.hq.core.data.moodOf
import com.coinepro.hq.core.data.moodWordFa
import com.coinepro.hq.core.data.nextRun
import com.coinepro.hq.core.data.nowFacts
import com.coinepro.hq.core.data.readyAnswers
import com.coinepro.hq.core.data.routeOpen
import com.coinepro.hq.core.data.runDotsFa
import com.coinepro.hq.core.data.sealSummary
import com.coinepro.hq.core.data.segmentsFa
import com.coinepro.hq.core.data.segmentsOf
import com.coinepro.hq.core.data.sentenceOf
import com.coinepro.hq.core.data.sheetBest
import com.coinepro.hq.core.data.soonestRun
import com.coinepro.hq.core.data.standingTaskFa
import com.coinepro.hq.core.data.stands
import com.coinepro.hq.core.data.summaryIsNew
import com.coinepro.hq.core.data.taskFa
import com.coinepro.hq.core.data.taskOf
import com.coinepro.hq.core.data.timerFig
import com.coinepro.hq.core.data.tookFa
import com.coinepro.hq.core.data.turnTime
import com.coinepro.hq.core.data.workerKindFa
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.BestHour
import com.coinepro.hq.core.net.Blocker
import com.coinepro.hq.core.net.DeskCard
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.Fix
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.PublishDesk
import com.coinepro.hq.core.net.PublishPanel
import com.coinepro.hq.core.net.RoutineRun
import com.coinepro.hq.core.net.SessionActivity
import com.coinepro.hq.core.net.SessionPublish
import com.coinepro.hq.core.net.SessionTask
import com.coinepro.hq.core.net.SessionWorker
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.gated
import kotlinx.coroutines.test.runTest
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
 * ⟨1.0.1⟩ Part C, phase 2 of the look, the rules behind its screens (no screen is drawn here): the session's mood on a hub that says
 * it and on one that does not, the plan as a line of parts, the build ring of a turn and its turn at 90 percent, the «الان» bar's
 * words and the work a «نگه دار» stops, the one sentence of a knot; which file a page's «تأیید و انتشار» is about; the publish desk in
 * its order with its one gold, and the day of a moment around midnight on the owner's clock; when a routine runs next, its last seven
 * runs, what a member's tile says, the one-line summary of a seal; the §55 answers decoded as the hub writes them; and a hub before
 * them, which is a gap and never an error.
 */
@RunWith(RobolectricTestRunner::class)
class Look2Test {
    private val server = MockWebServer()
    private lateinit var api: Api

    /** Friday 2026-11-06, 12:00 on the owner's clock. */
    private val now = java.time.Instant.parse("2026-11-06T08:30:00Z").toEpochMilli()

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
    }

    @After
    fun tearDown() = server.close()

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    // ------------------------------------------------------------------------------------------ C2.2 the mood --
    @Test
    fun theMoodIsTheHubsOwnWordAndOnAnOlderHubReadFromItsActivity() {
        val someone = listOf(SessionWorker(whoFa = "مدیر رسانه"))
        // the hub says it (§55.1): a run that has not taken its first step is still thinking
        assertEquals("thinking", moodOf(SessionActivity(working = someone, mood = "thinking"), closed = false))
        assertEquals("دارد فکر میکند", moodWordFa("thinking", SessionActivity(mood = "thinking", moodFa = "دارد فکر میکند")))
        // a hub before §55: stuck, then waiting, then working, then calm
        assertEquals("stuck", moodOf(SessionActivity(stuckFa = "بودجه کم است", waitingFa = "جواب بده"), false))
        assertEquals("waiting", moodOf(SessionActivity(waitingFa = "جواب بده", working = someone), false))
        assertEquals("working", moodOf(SessionActivity(working = someone), false))
        assertEquals("idle", moodOf(SessionActivity(), false))
        assertEquals("waiting", moodOf(SessionActivity(), false, asked = true))
        // a word this app does not know is read like an older hub's
        assertEquals("working", moodOf(SessionActivity(working = someone, mood = "dancing"), false))
        // no activity at all: from the session's badge
        assertEquals(listOf("waiting", "stuck", "working", "idle"), listOf("your_turn", "stuck", "moving", "ready").map { moodOf(null, false, it) })
        // a closed session is «تمام», whatever its last activity said
        assertEquals("done", moodOf(SessionActivity(working = someone, mood = "working"), closed = true))
        assertEquals("تمام", moodWordFa("done", SessionActivity(mood = "idle", moodFa = "آرام")))
        assertEquals("منتظر تو", moodWordFa("waiting", null))
    }

    // ------------------------------------------------------------------------------- C2.2 the ready answers --
    @Test
    fun aQuestionWithTwoOrThreeOptionsOffersThemAndAnOpenOneOffersNone() {
        assertEquals(listOf("اول ریلزها منتشر شود", "پست‌ها"), readyAnswers("سه ریلز و دو پست آماده است؛ اول ریلزها منتشر شود یا پست‌ها؟"))
        assertEquals(listOf("صبح", "ظهر", "شب"), readyAnswers("کدام ساعت: «صبح»، «ظهر» یا «شب»؟"))
        assertEquals(emptyList<String>(), readyAnswers("برای کاور چه رنگی میخواهی؟"))
        assertEquals(emptyList<String>(), readyAnswers("شنبه، یکشنبه، دوشنبه، سه‌شنبه یا چهارشنبه؟"))
        // the hub's own quick replies, when a report carries them, come first
        assertEquals(listOf("بله", "نه"), readyAnswers("منتشر کنم یا نه؟", listOf(" بله ", "", "نه")))
    }

    // ------------------------------------------------------------------------------ C2.2 the plan, in a line --
    @Test
    fun thePlanIsALineOfPartsAndOnlyThePartThatWaitsForHimIsHis() {
        val plan = listOf(
            SessionTask("a", 1, state = "done"), SessionTask("b", 2, state = "done"), SessionTask("c", 3, state = "doing"),
            // a line he wrote himself is not a part that waits for him
            SessionTask("d", 4, by = "owner"), SessionTask("e", 5, state = "dropped"),
        )
        assertEquals(3 to 4, taskOf(plan))
        assertEquals("کار 3 از 4", taskFa(3 to 4))
        assertEquals(listOf("done", "done", "todo", "todo"), segmentsOf(plan, waiting = false))
        assertEquals(listOf("done", "done", "waiting", "todo"), segmentsOf(plan, waiting = true))
        assertEquals("2 کار از 4 انجام شده؛ یک بخش منتظر تو است", segmentsFa(segmentsOf(plan, true)))
        assertEquals("2 کار از 4 انجام شده", segmentsFa(segmentsOf(plan, false)))
        assertEquals("کار 3 از 4 ایستاده", standingTaskFa(plan))
        // a finished plan says its last task, and nothing stands still
        val done = plan.map { it.copy(state = if (it.state == "dropped") "dropped" else "done") }
        assertEquals(4 to 4, taskOf(done))
        assertNull(standingTaskFa(done))
        assertEquals(listOf("done", "done", "done", "done"), segmentsOf(done, true))
        assertNull(taskOf(emptyList()))
        assertEquals(emptyList<String>(), segmentsOf(emptyList(), true))
    }

    // ------------------------------------------------------------------------- C2.2 the «الان» bar and its ring --
    @Test
    fun aTurnsRingFillsWithRealTimeAndTurnsAtNinetyPercent() {
        val w = SessionWorker(whoFa = "سازنده‌ی موشن‌گرافی", companyFa = "پرو-چارت", kind = "workshop", capS = 3600, startedAt = "2026-11-06T08:07:00Z")
        assertTrue(isTurn(w))
        val t = turnTime(w, now)
        assertEquals(23, t.min)
        assertEquals(60, t.capMin)
        assertEquals(23f / 60f, t.share, 0.001f)
        assertFalse(t.late)
        // 54 of 60 minutes: nine tenths, amber
        val late = turnTime(w.copy(startedAt = "2026-11-06T07:36:00Z"), now)
        assertEquals(54, late.min)
        assertTrue(late.late)
        assertFalse(turnTime(w.copy(startedAt = "2026-11-06T07:37:00Z"), now).late)
        // past its cap it stays full, and the minute does not pass the cap
        val over = turnTime(w.copy(startedAt = "2026-11-06T06:00:00Z"), now)
        assertEquals(1f, over.share, 0f)
        assertEquals(60, over.min)
        // a run is no turn, and a turn the hub gave no cap is no ring; a cap under a minute is read as a minute
        assertFalse(isTurn(SessionWorker(startedAt = "2026-11-06T08:07:00Z")))
        assertFalse(isTurn(SessionWorker(kind = "direct")))
        assertEquals(1, turnTime(SessionWorker(kind = "direct", capS = 10, startedAt = "2026-11-06T08:29:30Z"), now).capMin)
        // a clock the hub did not send: nothing has passed
        assertEquals(0, turnTime(SessionWorker(kind = "workshop", capS = 3600), now).min)
    }

    @Test
    fun theBarSaysWhoWorksForWhomAndItsWholeSentence() {
        val run = SessionWorker(whoFa = "مدیرعامل پرو-چارت", companyFa = "پرو-چارت", workTitleFa = "سئوی سایت", doingFa = "فهرست صفحه‌ها را مرتب میکند")
        val shop = SessionWorker(whoFa = "سازنده‌ی موشن‌گرافی", companyFa = "پرو-چارت", kind = "workshop", capS = 3600, doingFa = "میسازد", lastFa = "صحنه‌ی ۳ را رندر میکند")
        val direct = SessionWorker(whoFa = "مدیر رسانه‌ی تریدیار", companyFa = "تریدیار", kind = "direct", capS = 3600, lastFa = " ")
        // the last thing a live turn did, else what it is doing, else its work's title
        assertEquals("صحنه‌ی ۳ را رندر میکند", sentenceOf(shop))
        assertEquals("فهرست صفحه‌ها را مرتب میکند", sentenceOf(run))
        assertEquals("سئوی سایت", sentenceOf(run.copy(doingFa = "")))
        // a company its name already says is not said twice; a workshop turn says so; a direct turn is the holder himself
        assertEquals(listOf("مدیرعامل پرو-چارت", "و 1 نفر دیگر"), nowFacts(run, 2))
        assertEquals(listOf("سازنده‌ی موشن‌گرافی", "پرو-چارت", "کارگاه"), nowFacts(shop, 1))
        assertEquals(listOf("مدیر رسانه‌ی تریدیار", DIRECT_NOW_FA), nowFacts(direct, 1))
        assertEquals("سرور شرکت", workerKindFa(SessionWorker(kind = "server")))
        assertNull(workerKindFa(direct))
        // the bar speaks of the turn (its ring is the bar's mark), else of the first one at work
        assertEquals(shop, leadWorker(listOf(run, shop)))
        assertEquals(run, leadWorker(listOf(run, run.copy(whoFa = "کارشناس سئو"))))
        assertNull(leadWorker(emptyList()))
        // a timer is a Latin figure
        assertEquals("0:42", timerFig("2026-11-06T08:29:18Z", now))
        assertEquals("23:05", timerFig("2026-11-06T08:06:55Z", now))
        assertEquals("1:02:10", timerFig("2026-11-06T07:27:50Z", now))
        assertEquals("0:00", timerFig(null, now))
    }

    @Test
    fun theWorkAHoldStopsIsTheOneInHandAndAKnotIsOneSentence() {
        fun order(vararg t: SessionTask) = OrderReport(ref = "F-0090", tasks = t.toList())
        // the task in hand, else the first open one that names its work, else the last that names one; none: no «نگه دار»
        assertEquals("W-2", liveWorkRef(order(SessionTask("a", 1, state = "done", workRef = "W-1"), SessionTask("b", 2, state = "doing", workRef = "W-2"), SessionTask("c", 3, workRef = "W-3"))))
        assertEquals("W-3", liveWorkRef(order(SessionTask("a", 1, state = "done", workRef = "W-1"), SessionTask("b", 2, state = "doing"), SessionTask("c", 3, workRef = "W-3"))))
        assertEquals("W-1", liveWorkRef(order(SessionTask("a", 1, state = "done", workRef = "W-1"), SessionTask("b", 2, state = "done", workRef = " "))))
        assertNull(liveWorkRef(order(SessionTask("a", 1, state = "doing"))))
        // a knot: the hub's own sentence; else the knot that can be fixed, its title and its detail
        val budget = Blocker("budget", "بودجه‌ی این کار کم است", "برای صداگذاری کم میآید.", fix = Fix("budget.add", "بودجه بده"))
        val quiet = Blocker("no_progress", "ده دقیقه است قدمی برداشته نشده")
        assertEquals("مسئول جواب نمیدهد.", knotWhy(" مسئول جواب نمیدهد. ", listOf(budget)))
        assertEquals(budget, leadKnot(listOf(quiet, budget)))
        assertEquals("بودجه‌ی این کار کم است؛ برای صداگذاری کم میآید.", knotWhy(null, listOf(quiet, budget)))
        assertEquals("ده دقیقه است قدمی برداشته نشده", knotWhy("", listOf(quiet)))
        assertNull(knotWhy(null, emptyList()))
        // how long a closed session took: a count in a sentence
        assertEquals("1 ساعت و 51 دقیقه", tookFa("2026-11-04T06:14:00Z", "2026-11-04T08:05:00Z"))
        assertEquals("40 دقیقه", tookFa("2026-11-04T06:00:00Z", "2026-11-04T06:40:00Z"))
        assertEquals("2 ساعت", tookFa("2026-11-04T06:00:00Z", "2026-11-04T08:00:00Z"))
        assertEquals("3 روز", tookFa("2026-11-01T06:00:00Z", "2026-11-04T06:00:00Z"))
        assertEquals("کمتر از یک دقیقه", tookFa("2026-11-04T06:00:00Z", "2026-11-04T06:00:20Z"))
        assertNull(tookFa("2026-11-04T06:00:00Z", null))
        assertNull(tookFa("2026-11-04T06:00:00Z", "2026-11-03T06:00:00Z"))
    }

    // ------------------------------------------------------------------------ C3.3 which file the page is about --
    @Test
    fun thePagesOneConfirmationIsAboutItsFirstFileThatWaits() {
        val reel = FileRef(id = "v", name = "reel.mp4", mime = "video/mp4", kind = "video")
        val cover = FileRef(id = "c", name = "cover.png", mime = "image/png", kind = "image")
        // an output's attachment carries its type only as its mime
        val post = FileRef(id = "i", name = "post.jpg", mime = "image/jpeg", kind = "document")
        val pdf = FileRef(id = "p", name = "script.pdf", mime = "application/pdf", kind = "document")
        val panel = PublishPanel(order = "F-0092", accounts = listOf("tradeyar"), ready = true)
        // a video before a picture, wherever it sits
        assertEquals("v", leadFile(panel, listOf(cover, pdf, reel))?.id)
        assertEquals("v", faceOf(listOf(cover, pdf, reel))?.id)
        // its reel stands (set for an hour, on its way, out): a cover waits behind its reel, so nothing leads
        for (state in listOf("scheduled", "publishing", "published", "waiting_setup", "waiting_seal")) {
            assertNull(state, leadFile(panel.copy(publishes = listOf(SessionPublish(job = "1", fileId = "v", kind = "reel", state = state))), listOf(cover, reel)))
        }
        // a publication that failed or was taken back does not stand: the file leads again
        for (state in listOf("failed", "cancelled")) {
            val p = SessionPublish(job = "1", fileId = "v", kind = "reel", state = state)
            assertFalse(stands(p))
            assertEquals("v", leadFile(panel.copy(publishes = listOf(p)), listOf(cover, reel))?.id)
        }
        assertFalse(stands(null))
        // an output of pictures only: its first free one
        assertEquals("i", leadFile(panel, listOf(pdf, post, cover))?.id)
        assertEquals("c", leadFile(panel.copy(publishes = listOf(SessionPublish(job = "2", fileId = "i", state = "published"))), listOf(post, cover))?.id)
        // nothing to lead: no file that goes out, an output that is no session's, a company whose path is not set, a group that publishes itself
        assertNull(leadFile(panel, listOf(pdf)))
        assertNull(leadFile(PublishPanel(accounts = listOf("tradeyar"), ready = true), listOf(reel)))
        assertNull(leadFile(PublishPanel(order = "F-0092"), listOf(reel)))
        assertFalse(routeOpen(PublishPanel(order = "F-0092")))
        assertTrue(routeOpen(PublishPanel(accounts = listOf("tradeyar"))))
        assertNull(leadFile(panel.copy(mode = "auto"), listOf(reel)))
        assertNull(leadFile(null, listOf(reel)))
        // a working group's daily output is tapped all the same (§45 `tap`)
        assertEquals("v", leadFile(PublishPanel(tap = true, accounts = listOf("tradeyar"), mode = "ask"), listOf(reel))?.id)
        // the sheet offers the best hour only when the hub named an hour and its moment
        assertNotNull(sheetBest(BestHour(account = "tradeyar", hour = "21:00", at = "2026-11-06T17:30:00Z", enough = true)))
        assertNull(sheetBest(BestHour(account = "tradeyar", hour = "21:00", enough = true)))
        assertNull(sheetBest(BestHour(account = "tradeyar", at = "2026-11-06T17:30:00Z")))
        // a summary its text already says is not shown twice
        assertFalse(summaryIsNew("ریلز ۳۰ ثانیه‌ای با کاور؛ آماده‌ی انتشار.", "## خلاصه\nریلز ۳۰ ثانیه‌ای با کاور؛ آماده‌ی انتشار.\n\n## متن"))
        assertTrue(summaryIsNew("دقت هفته ۶۸٪ بود.", "جزئیات در پیوست پایش."))
        assertFalse(summaryIsNew(" ", "متن"))
    }

    // ------------------------------------------------------------------------------------ C2.3 the publish desk --
    private fun card(output: String, at: String, route: Boolean = true, state: String = "ready", publish: SessionPublish? = null) =
        DeskCard(output = output, at = at, routeReady = route, state = state, publish = publish)

    @Test
    fun theDeskIsInItsOrderWhateverOrderTheHubSentAndOnlyItsFirstReadyCardLeads() {
        val desk = PublishDesk(
            ready = listOf(card("old", "2026-11-05T06:00:00Z"), card("no-route", "2026-11-06T08:00:00Z", route = false), card("new", "2026-11-06T07:00:00Z")),
            queue = listOf(
                card("tonight", "2026-11-06T07:40:00Z", state = "scheduled", publish = SessionPublish(job = "2", state = "scheduled", scheduledAt = "2026-11-06T18:00:00Z")),
                card("now", "2026-11-06T08:27:00Z", state = "publishing", publish = SessionPublish(job = "1", state = "publishing")),
            ),
            done = listOf(
                card("yesterday", "2026-11-05T10:00:00Z", state = "published", publish = SessionPublish(job = "3", state = "published", publishedAt = "2026-11-05T10:30:00Z")),
                card("failed", "2026-11-06T06:30:00Z", state = "failed", publish = SessionPublish(job = "4", state = "failed")),
            ),
        )
        val s = deskSorted(desk)
        // ready newest first, the queue soonest first, what is done newest first
        assertEquals(listOf("no-route", "new", "old"), s.ready.map { it.output })
        assertEquals(listOf("now", "tonight"), s.queue.map { it.output })
        assertEquals(listOf("failed", "yesterday"), s.done.map { it.output })
        // the one full gold: the first ready card whose company's path is set
        assertEquals("new", deskLead(s.ready))
        assertNull(deskLead(listOf(card("no-route", "2026-11-06T08:00:00Z", route = false))))
        assertFalse(deskEmpty(desk))
        assertTrue(deskEmpty(PublishDesk()))
        assertEquals("چیزی آماده‌ی انتشار نیست؛ هر خروجی تأییدشدنی همین‌جا می‌آید.", DESK_EMPTY_FA)
        // the home's line: counts in a sentence
        assertEquals(listOf("3 خروجی آماده‌ی انتشار", "2 در صف"), deskLineFa(desk))
        assertEquals(listOf("چیزی آماده نیست"), deskLineFa(PublishDesk()))
        // each kind in its network's frame; a queued card that waits for no hour says what it waits for
        assertEquals(listOf(9f / 16f, 9f / 16f, 4f / 5f, 1f), listOf("reel", "story", "post", "carousel").map(::deskRatio))
        assertEquals(listOf("در حال انتشار", "در حال وصل شدن", "منتظر تأیید", null), listOf("publishing", "waiting_setup", "waiting_seal", "scheduled").map(::deskQueueWordFa))
    }

    @Test
    fun theDayOfAMomentIsSaidOnTheOwnersClock() {
        // 12:00 in Tehran: 21:30 the same day is tonight, 12:30 is today
        assertEquals("امشب", deskDayFa("2026-11-06T18:00:00Z", now))
        assertEquals("امروز", deskDayFa("2026-11-06T09:00:00Z", now))
        assertEquals("فردا", deskDayFa("2026-11-07T04:00:00Z", now))
        assertEquals("فردا شب", deskDayFa("2026-11-07T16:00:00Z", now))
        assertEquals("دیشب", deskDayFa("2026-11-05T16:00:00Z", now))
        assertEquals("دیروز", deskDayFa("2026-11-05T06:00:00Z", now))
        // a quarter past midnight in Tehran is tomorrow, though the same day still stands in UTC
        assertEquals("فردا", deskDayFa("2026-11-06T20:45:00Z", now))
        // any other day by its date
        assertEquals(jDate("2026-11-10T06:00:00Z"), deskDayFa("2026-11-10T06:00:00Z", now))
        assertEquals("", deskDayFa(null, now))
    }

    // ------------------------------------------------------------------------------------ C3.4 the working group --
    @Test
    fun aRoutinesNextRunIsWorkedOutFromItsOwnSchedule() {
        // 09:00 has passed today (it is 12:00): tomorrow; 18:30 has not: today
        assertEquals("2026-11-07T05:30:00Z", nextRun("FREQ=DAILY;BYHOUR=9;BYMINUTE=0", now))
        assertEquals("2026-11-06T15:00:00Z", nextRun("RRULE:FREQ=DAILY;BYHOUR=18;BYMINUTE=30", now))
        assertEquals("2026-11-06T08:45:00Z", nextRun("FREQ=HOURLY;BYMINUTE=15", now))
        // Friday: the next Monday or Thursday is Monday
        assertEquals("2026-11-09T07:00:00Z", nextRun("FREQ=WEEKLY;BYDAY=MO,TH;BYHOUR=10;BYMINUTE=30", now))
        assertEquals("2026-12-01T04:30:00Z", nextRun("FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=8", now))
        assertNull(nextRun("FREQ=YEARLY;BYHOUR=8", now))
        assertNull(nextRun("FREQ=DAILY;BYHOUR=25", now))
        assertNull(nextRun(" ", now))
        assertEquals("2026-11-06T08:45:00Z", soonestRun(listOf("FREQ=DAILY;BYHOUR=9;BYMINUTE=0", "junk", "FREQ=HOURLY;BYMINUTE=15"), now))
        assertNull(soonestRun(emptyList(), now))
    }

    @Test
    fun aMembersTileSaysItsLastRunWhetherItWorksNowAndWhyItStandsStill() {
        fun run(id: String, company: String, state: String, at: String, note: String = "") = RoutineRun(id = id, group = "pb_1", company = company, routine = "reels", at = at, state = state, noteFa = note)
        val runs = listOf(
            run("1", "TY", "done", "2026-11-05T05:30:00Z"), run("2", "TY", "skipped", "2026-11-06T03:30:00Z"), run("3", "TY", "queued", "2026-11-06T08:20:00Z"),
            run("4", "FX", "failed", "2026-11-06T05:30:00Z", "سه نوبت پشت هم بسته‌ای تحویل نشد؛ کارگروه در این شرکت ایستاد."), run("5", "FX", "done", "2026-11-03T05:30:00Z"),
        )
        // at work: its last run that is over, and a run in the queue is «در کار»
        val ty = memberLook("TY", on = true, runs = runs)
        assertEquals("2", ty.last?.id)
        assertTrue(ty.running)
        assertNull(ty.why)
        assertEquals(listOf("در کار", "فعال", "ایستاده"), listOf(memberWordFa(true, true), memberWordFa(true, false), memberWordFa(false, true)))
        // standing still: what its last run said when it failed, else that it was stopped
        val fx = memberLook("FX", on = false, runs = runs)
        assertEquals("سه نوبت پشت هم بسته‌ای تحویل نشد؛ کارگروه در این شرکت ایستاد.", fx.why)
        assertFalse(fx.running)
        assertEquals(MEMBER_STILL_FA, memberLook("PC", on = false, runs = runs).why)
        // a hub that does not serve the runs: nothing is said of them
        assertNull(memberLook("TY", on = true, runs = null).last)
        // the dots: the last seven, oldest first
        val nine = (1..9).map { run("r$it", "TY", if (it == 8) "failed" else "done", "2026-11-0${it}T05:30:00Z") }.shuffled(java.util.Random(7))
        assertEquals(listOf("r3", "r4", "r5", "r6", "r7", "r8", "r9"), lastSeven(nine).map { it.id })
        assertEquals("ریلز روز: 7 نوبت آخر، 1 ناموفق", runDotsFa("ریلز روز", nine))
        assertEquals("ریلز روز: 2 نوبت آخر، همه بی‌خطا", runDotsFa("ریلز روز", nine.filter { it.id in setOf("r1", "r2") }))
        assertEquals("ریلز روز: هنوز نوبتی نداشته", runDotsFa("ریلز روز", emptyList()))
        // what a seal starts, in one line
        assertEquals(listOf("3 جایگاه", "2 روال", "1 اتصال"), sealSummary(3, 2, 1))
        assertEquals(listOf("1 جایگاه", "0 روال"), sealSummary(1, 0, 0))
    }

    // ------------------------------------------------------------------------------------ §55 as the hub writes it --
    @Test
    fun theDeskAndTheSessionsNewFieldsReadAsTheHubWritesThem() {
        val desk = Api.json.decodeFromString(
            PublishDesk.serializer(),
            """{"ready":[{"output":"O-000967","title_fa":"ریلز: حد ضرر را کجا بگذاریم","company":"TY","company_fa":"تریدیار","order":"F-0092","group_fa":null,
                "file":{"id":"f-reel","name":"reel-stoploss.mp4","mime":"video/mp4","size":32183},"cover":{"id":"f-cover","name":"cover.png","mime":"image/png","size":11962},
                "files":2,"kind":"reel","channel":"instagram","account":"tradeyar","accounts":["tradeyar"],"route_ready":true,"caption":"حد ضرر را کجا بگذاریم؟",
                "state":"ready","publish":null,"best":{"account":"tradeyar","hour":"21:00","at":"2026-11-06T17:30:00Z","enough":true,"posts":38,"days":90,"note_fa":"از روی لایک و کامنت"},
                "mode":"ask","at":"2026-11-06T07:50:00Z"}],
               "queue":[{"output":"O-000972","company":"TY","file":{"id":"f2","name":"reel-02.mp4","mime":"video/mp4","size":1},"kind":"reel","state":"scheduled",
                "publish":{"job":"jp-42","file_id":"f2","kind":"reel","state":"scheduled","scheduled_at":"2026-11-06T18:00:00Z","auto":true},"at":"2026-11-06T07:40:00Z"}],
               "done":[]}""",
        )
        val k = desk.ready.single()
        assertEquals("reel-stoploss.mp4", k.file.name)
        assertEquals("cover.png", k.cover?.name)
        assertTrue(k.routeReady)
        assertEquals("21:00", k.best?.hour)
        assertEquals("2026-11-06T18:00:00Z", desk.queue.single().publish?.scheduledAt)
        // a card the hub writes with nothing but its output still reads: no path set, one file, a post
        val bare = Api.json.decodeFromString(DeskCard.serializer(), """{"output":"O-1"}""")
        assertFalse(bare.routeReady)
        assertEquals(1, bare.files)
        assertEquals("post", bare.kind)
        // §55.1 the mood and a turn's kind, cap and last line; §54 a direct session
        val a = Api.json.decodeFromString(
            SessionActivity.serializer(),
            """{"working":[{"who_fa":"سازنده‌ی موشن‌گرافی","company_fa":"پرو-چارت","work_title_fa":"موشن‌گرافی ATR","started_at":"2026-11-06T08:07:00Z","step":0,"doing_fa":"",
                "kind":"workshop","cap_s":3600,"last_fa":"صحنه‌ی ۳ را رندر میکند","last_at":"2026-11-06T08:29:00Z"}],
               "last":[],"idle_since":null,"waiting_fa":null,"stuck_fa":null,"mood":"working","mood_fa":"کار میکند"}""",
        )
        assertEquals("workshop", a.working.single().kind)
        assertEquals(3600, a.working.single().capS)
        assertEquals("working", a.mood)
        // a hub before §55 sends none of them: a run, no cap, no mood
        val old = Api.json.decodeFromString(SessionActivity.serializer(), """{"working":[{"who_fa":"مدیر رسانه","started_at":"2026-11-06T08:07:00Z"}],"last":[]}""")
        assertEquals("run", old.working.single().kind)
        assertNull(old.working.single().capS)
        assertNull(old.mood)
        assertTrue(Api.json.decodeFromString(OrderReport.serializer(), """{"ref":"F-0091","direct":true}""").direct)
        assertFalse(Api.json.decodeFromString(OrderReport.serializer(), """{"ref":"F-0091"}""").direct)
    }

    @Test
    fun theDeskIsAskedOnItsOwnRouteAndForOneCompany() = runTest {
        server.enqueue(json(200, """{"ready":[],"queue":[],"done":[]}"""))
        assertTrue(deskEmpty(api.publishDesk("TY")))
        val asked = server.takeRequest()
        assertEquals("GET", asked.method)
        assertTrue(asked.target, asked.target.endsWith("/publish-desk?company=TY"))
        server.enqueue(json(200, """{"ready":[],"queue":[],"done":[]}"""))
        api.publishDesk()
        assertTrue(server.takeRequest().target.endsWith("/publish-desk"))
    }

    @Test
    fun aHubBeforeTheDeskOrTheStopHidesThemWithoutAnError() = runTest {
        // the framework's own «Not Found»: the route is not there yet
        server.enqueue(json(404, """{"detail":"Not Found"}"""))
        assertNull(api.gated(HubFeature.PUBLISH_DESK) { publishDesk() })
        assertFalse(api.gaps.has(HubFeature.PUBLISH_DESK))
        assertNull(api.gated(HubFeature.PUBLISH_DESK) { fail("not asked again"); publishDesk() })
        server.enqueue(json(405, """{"detail":"Method Not Allowed"}"""))
        assertNull(api.gated(HubFeature.WORK_STOP) { stopWork("w390") })
        assertFalse(api.gaps.has(HubFeature.WORK_STOP))
        assertEquals(2, server.requestCount)
        // the runs of a working group are learnt the same way, on their own gate
        server.enqueue(json(404, """{"detail":"Not Found"}"""))
        assertNull(api.gated(HubFeature.GROUP_RUNS) { groupRuns("pb_1") })
        assertFalse(api.gaps.has(HubFeature.GROUP_RUNS))
        assertTrue(api.gaps.has(HubFeature.GROUPS))
    }
}
