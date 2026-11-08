package com.coinepro.hq

import com.coinepro.hq.core.data.ActivityEvent
import com.coinepro.hq.core.data.LivePanel
import com.coinepro.hq.core.data.PlanProgress
import com.coinepro.hq.core.data.activityEventOf
import com.coinepro.hq.core.data.activityFromReport
import com.coinepro.hq.core.data.applyActivity
import com.coinepro.hq.core.data.elapsedFa
import com.coinepro.hq.core.data.idleFa
import com.coinepro.hq.core.data.lineFa
import com.coinepro.hq.core.data.livePanelOf
import com.coinepro.hq.core.data.mergeFetched
import com.coinepro.hq.core.data.mergeLines
import com.coinepro.hq.core.data.othersFa
import com.coinepro.hq.core.data.paceToastFa
import com.coinepro.hq.core.data.planProgress
import com.coinepro.hq.core.data.planProgressFa
import com.coinepro.hq.core.data.recentLines
import com.coinepro.hq.core.data.sinceFa
import com.coinepro.hq.core.data.taskInHand
import com.coinepro.hq.core.data.workingHeadFa
import com.coinepro.hq.core.net.ActivityLine
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.SessionActivity
import com.coinepro.hq.core.net.SessionTask
import com.coinepro.hq.core.net.SessionWorker
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.gated
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject
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
 * ⟨1.23⟩ Contract §41, the session shows its work live and never stalls: `SessionActivity` as the hub writes it (its nulls, the least it
 * may send), the `session.activity` stream event (the order in its data or as the event's ref, a count sent as a number or a string),
 * the lines merged (each step once whether heard on the stream or read again, in time order, the newest thirty), an event applied (a line
 * appended, nobody working → quiet since it, someone working → no longer stuck or waiting, an unknown worker standing in from his line),
 * the panel's words in Persian digits, the plan's «کار ۳ از ۹», a hub before §41 read from the report, and the two routes (`GET …/activity`,
 * `POST …/nudge` with the press's own key; a hub without them marks the feature missing).
 */
@RunWith(RobolectricTestRunner::class)
class SessionLiveTest {
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

    private val NOW = java.time.Instant.parse("2026-11-08T10:00:00Z").toEpochMilli()
    private fun at(secAgo: Long) = java.time.Instant.ofEpochMilli(NOW - secAgo * 1000).toString()
    private fun line(secAgo: Long, who: String, text: String) = ActivityLine(at(secAgo), who, text)

    /** As pydantic writes it: every field, the nulls included. */
    private val ACTIVITY = """{"working":[{"who_fa":"مدیر رسانه","company_fa":"پرو-چارت","work_title_fa":"ریلز آزمایشی","started_at":"2026-11-08T09:48:00Z","step":3,"doing_fa":"از ChatGPT پرسید"},
        {"who_fa":"نویسنده","company_fa":null,"work_title_fa":"متن ریلز","started_at":"2026-11-08T09:58:00+00:00","step":1,"doing_fa":"بریف را خواند"}],
        "last":[{"at":"2026-11-08T09:50:00Z","who_fa":"مدیر رسانه","text_fa":"سایت pro-chart.com را خواند"},{"at":"2026-11-08T09:59:00Z","who_fa":"نویسنده","text_fa":"بریف را خواند"}],
        "idle_since":null,"waiting_fa":null,"stuck_fa":null}"""

    // ------------------------------------------------------------------ shapes --
    @Test
    fun theActivityReadsAsTheHubWritesIt() {
        val a = Api.json.decodeFromString(SessionActivity.serializer(), ACTIVITY)
        assertEquals(2, a.working.size)
        assertEquals(3, a.working[0].step)
        assertNull(a.working[1].companyFa)
        assertEquals("بریف را خواند", a.last.last().textFa)
        assertEquals(LivePanel.WORKING, livePanelOf(a))
        // The least the hub may send: nobody working, no line, quiet since a time.
        val quiet = Api.json.decodeFromString(SessionActivity.serializer(), """{"working":[],"last":[],"idle_since":"2026-11-08T09:40:00Z"}""")
        assertTrue(quiet.working.isEmpty() && quiet.last.isEmpty())
        assertEquals(LivePanel.IDLE, livePanelOf(quiet))
        assertEquals(LivePanel.WAITING, livePanelOf(Api.json.decodeFromString(SessionActivity.serializer(), """{"waiting_fa":"اول ریلز یا پست؟","stuck_fa":"x"}""")))
        assertEquals(LivePanel.STUCK, livePanelOf(Api.json.decodeFromString(SessionActivity.serializer(), """{"stuck_fa":"بودجه‌ی این کار تمام شده"}""")))
        assertEquals(LivePanel.IDLE, livePanelOf(SessionActivity(waitingFa = " ", stuckFa = "")))
    }

    // ------------------------------------------------------------------ the stream --
    @Test
    fun aStreamEventReadsWithItsOrderLineAndCount() {
        val data = buildJsonObject {
            put("order", "F-0011")
            putJsonObject("line") { put("at", "2026-11-08T10:00:00Z"); put("who_fa", "مدیر رسانه"); put("text_fa", "صدا ساخت") }
            put("working", 2)
        }
        val ev = activityEventOf(StreamEvent("e1", "session.activity", "2026-11-08T10:00:00Z", "PC", null, data))!!
        assertEquals("F-0011", ev.order)
        assertEquals("صدا ساخت", ev.line?.textFa)
        assertEquals(2, ev.working)
        // The order as the event's ref, the count as a string; a line with no words is no line.
        val bare = activityEventOf(StreamEvent("e2", "session.activity", "", "PC", "F-0012", JsonObject(mapOf("working" to JsonPrimitive("0"), "line" to buildJsonObject { put("text_fa", " ") }))))!!
        assertEquals("F-0012", bare.order)
        assertNull(bare.line)
        assertEquals(0, bare.working)
        // Another event, or one with no order at all, is not one.
        assertNull(activityEventOf(StreamEvent("e3", "session.updated", "", "PC", "F-0011", data)))
        assertNull(activityEventOf(StreamEvent("e4", "session.activity", "", "PC", null, JsonObject(emptyMap()))))
    }

    // ------------------------------------------------------------------ merging --
    @Test
    fun linesMergeOnceInTimeOrderKeepingTheNewestThirty() {
        val a = listOf(line(300, "الف", "یک"), line(200, "الف", "دو"))
        // The same step read again with another spelling of its time is the same line.
        val again = ActivityLine(a[1].at.replace("Z", "+00:00"), "الف", "دو")
        val merged = mergeLines(a, listOf(line(100, "ب", "سه"), again, line(250, "ب", "میان")))
        assertEquals(listOf("یک", "میان", "دو", "سه"), merged.map { it.textFa })
        // A line without a time goes after the timed ones; an empty one is dropped.
        assertEquals(listOf("یک", "بی‌زمان"), mergeLines(listOf(ActivityLine("", "x", "بی‌زمان"), a[0], ActivityLine(at(1), "x", " ")), emptyList()).map { it.textFa })
        val many = (1..40).map { line(100L - it, "x", "خط $it") }
        val kept = mergeLines(many, emptyList())
        assertEquals(30, kept.size)
        assertEquals("خط 11", kept.first().textFa)
        assertEquals("خط 40", kept.last().textFa)
        assertEquals(listOf("خط 38", "خط 39", "خط 40"), recentLines(SessionActivity(last = kept)).map { it.textFa })
    }

    @Test
    fun anEventIsAppendedAtOnceAndMovesTheState() {
        val worker = SessionWorker(whoFa = "مدیر رسانه", startedAt = at(600), step = 3, doingFa = "بریف را خواند")
        val stuck = SessionActivity(last = listOf(line(900, "مدیر رسانه", "بریف را خواند")), stuckFa = "بودجه تمام شد", waitingFa = null)
        // Someone works again: no longer stuck; a worker the screen does not know yet stands in from his line.
        val moved = applyActivity(stuck, ActivityEvent("F-1", line(10, "مدیر رسانه", "صدا ساخت"), 1))
        assertNull(moved.stuckFa)
        assertEquals(LivePanel.WORKING, livePanelOf(moved))
        assertEquals("صدا ساخت", moved.working.single().doingFa)
        assertEquals(listOf("بریف را خواند", "صدا ساخت"), moved.last.map { it.textFa })
        // A known worker's line: he is doing what it says (his step stays the hub's until it is refetched); no stand-in is added.
        val two = applyActivity(SessionActivity(working = listOf(worker)), ActivityEvent("F-1", line(5, "مدیر رسانه", "از ChatGPT پرسید"), 1))
        assertEquals(listOf("از ChatGPT پرسید"), two.working.map { it.doingFa })
        assertEquals(3, two.working.single().step)
        // Nobody works now: quiet since that line; the same line heard twice is one.
        val done = applyActivity(two, ActivityEvent("F-1", line(1, "مدیر رسانه", "خروجی تحویل داد"), 0))
        assertTrue(done.working.isEmpty())
        assertEquals(at(1), done.idleSince)
        assertEquals(LivePanel.IDLE, livePanelOf(done))
        assertEquals(done.last, applyActivity(done, ActivityEvent("F-1", line(1, "مدیر رسانه", "خروجی تحویل داد"), 0)).last)
        // A count alone (no line) leaves the lines as they are.
        assertEquals(done.last, applyActivity(done, ActivityEvent("F-1", null, null)).last)
        // The waiting state is not cleared by a line that says nobody works.
        val waiting = SessionActivity(waitingFa = "اول ریلز یا پست؟")
        assertEquals("اول ریلز یا پست؟", applyActivity(waiting, ActivityEvent("F-1", line(1, "سامانه", "یادآوری"), 0)).waitingFa)
    }

    @Test
    fun theHubsAnswerKeepsALineHeardWhileItWasOnItsWay() {
        val held = SessionActivity(last = listOf(line(60, "الف", "یک"), line(2, "الف", "تازه")))
        val fetched = SessionActivity(working = listOf(SessionWorker(whoFa = "الف", step = 4)), last = listOf(line(60, "الف", "یک")))
        val out = mergeFetched(fetched, held)
        assertEquals(4, out.working.single().step)
        assertEquals(listOf("یک", "تازه"), out.last.map { it.textFa })
        assertEquals(fetched.last, mergeFetched(fetched, null).last)
    }

    // ------------------------------------------------------------------ the words --
    @Test
    fun thePanelSpeaksInPersianDigits() {
        val w = SessionWorker(whoFa = "مدیر رسانه", step = 12)
        assertEquals("مدیر رسانه دارد کار میکند · قدم ۱۲", workingHeadFa(w))
        assertEquals("یک همکار دارد کار میکند", workingHeadFa(SessionWorker()))
        assertNull(othersFa(listOf(w)))
        assertEquals("همزمان: نویسنده · قدم ۲، طراح", othersFa(listOf(w, SessionWorker(whoFa = "نویسنده", step = 2), SessionWorker(whoFa = "طراح"))))
        // A line by the one in the head is its words; by another, «who: words»; markdown and breaks out.
        assertEquals("صدا ساخت", lineFa(ActivityLine("", "مدیر رسانه", "صدا ساخت"), "مدیر رسانه"))
        assertEquals("نویسنده: متن را نوشت", lineFa(ActivityLine("", "نویسنده", "**متن**\nرا نوشت"), "مدیر رسانه"))
        assertEquals("۴۵ ثانیه", elapsedFa(at(45), NOW))
        assertEquals("۱۲ دقیقه", elapsedFa(at(12 * 60 + 5), NOW))
        assertEquals("۱ ساعت و ۵ دقیقه", elapsedFa(at(65 * 60), NOW))
        assertEquals("۲ ساعت", elapsedFa(at(120 * 60), NOW))
        assertNull(elapsedFa("", NOW))
        assertEquals("همین الان", sinceFa(at(10), NOW))
        assertEquals("۵ دقیقه پیش", sinceFa(at(5 * 60), NOW))
        assertEquals("۳ ساعت پیش", sinceFa(at(3 * 3600), NOW))
        assertEquals("۲ روز پیش", sinceFa(at(2 * 86400), NOW))
        assertEquals("آرام · آخرین کار ۵ دقیقه پیش", idleFa(SessionActivity(idleSince = at(300)), NOW))
        assertEquals("آرام · آخرین کار ۲ دقیقه پیش", idleFa(SessionActivity(last = listOf(line(120, "x", "y"))), NOW))
        assertEquals("آرام", idleFa(SessionActivity(), NOW))
        assertEquals("از این به بعد قدم‌به‌قدم با تو.", paceToastFa("step"))
        assertEquals("از این به بعد خودش تا آخر میرود.", paceToastFa("auto"))
    }

    // ------------------------------------------------------------------ the plan --
    @Test
    fun thePlansProgressIsTheTaskInHand() {
        fun t(n: Int, state: String) = SessionTask("t$n", n, "کار $n", state)
        assertNull(planProgress(emptyList()))
        // Nine steps of the owner's: two done, the third in work → «کار ۳ از ۹».
        val nine = (1..9).map { t(it, if (it <= 2) "done" else if (it == 3) "doing" else "todo") }
        assertEquals(PlanProgress(3, 9, 2), planProgress(nine))
        assertEquals("کار ۳ از ۹", planProgressFa(planProgress(nine)!!))
        assertEquals("کار 3", taskInHand(nine)?.titleFa)
        // Nothing in work: the first not done; a dropped one is out of the count; all done says so.
        val gap = listOf(t(1, "done"), t(2, "dropped"), t(3, "todo"), t(4, "done"))
        assertEquals(PlanProgress(2, 3, 2), planProgress(gap))
        assertEquals("کار 3", taskInHand(gap)?.titleFa)
        val all = listOf(t(1, "done"), t(2, "done"))
        assertEquals("کار ۲ از ۲ · تمام", planProgressFa(planProgress(all)!!))
        assertTrue(planProgress(all)!!.finished)
        assertEquals(1f, planProgress(all)!!.fraction)
        assertNull(taskInHand(all))
    }

    // ------------------------------------------------------------------ an older hub --
    @Test
    fun aHubBeforeItReadsThePanelFromTheReport() {
        val waiting = Api.json.decodeFromString(OrderReport.serializer(), """{"ref":"F-1","turn":{"question_fa":"اول ریلزها؟","at":"2026-11-08T09:00:00Z"},
            "steps":[{"at":"2026-11-08T08:00:00Z","who_fa":"سامانه","what_fa":"به مدیر رسانه سپرده شد"},{"at":"2026-11-08T08:30:00Z","who_fa":"مدیر رسانه","what_fa":"سه ریلز ساخت"}]}""")
        val a = activityFromReport(waiting)
        assertEquals("اول ریلزها؟", a.waitingFa)
        assertEquals(listOf("", "مدیر رسانه"), a.last.map { it.whoFa })
        val stuck = Api.json.decodeFromString(OrderReport.serializer(), """{"ref":"F-2","session":{"state":"open","badge":"stuck","reason_fa":"بودجه‌ی این کار تمام شده"}}""")
        assertEquals("بودجه‌ی این کار تمام شده", activityFromReport(stuck).stuckFa)
        val moving = Api.json.decodeFromString(OrderReport.serializer(), """{"ref":"F-3","updated_at":"2026-11-08T09:55:00Z"}""")
        assertEquals(LivePanel.IDLE, livePanelOf(activityFromReport(moving)))
        assertEquals("2026-11-08T09:55:00Z", activityFromReport(moving).idleSince)
    }

    // ------------------------------------------------------------------ routes --
    @Test
    fun theActivityIsReadAndTheNudgeCarriesThePresssKey() = runTest {
        server.enqueue(json(200, ACTIVITY))
        assertEquals(2, api.sessionActivity("F-0011").working.size)
        val get = server.takeRequest()
        assertEquals("GET", get.method)
        assertEquals("/api/v1/orders/F-0011/activity", get.url.encodedPath)
        server.enqueue(json(200, ACTIVITY))
        val key = java.util.UUID.randomUUID().toString()
        assertEquals(LivePanel.WORKING, livePanelOf(api.nudgeSession("F-0011", key)))
        val post = server.takeRequest()
        assertEquals("POST", post.method)
        assertEquals("/api/v1/orders/F-0011/nudge", post.url.encodedPath)
        assertEquals(key, post.headers["Idempotency-Key"])
        assertEquals(JsonObject(emptyMap()), Api.json.parseToJsonElement(post.body!!.utf8()).jsonObject)
    }

    @Test
    fun aHubWithoutTheRouteMarksTheFeatureMissing() = runTest {
        server.enqueue(json(404, """{"detail":"Not Found"}"""))
        assertNull(api.gated(HubFeature.SESSION_ACTIVITY) { sessionActivity("F-0011") })
        assertFalse(api.gaps.has(HubFeature.SESSION_ACTIVITY))
        // Once known missing, it is not asked again this app start.
        assertNull(api.gated(HubFeature.SESSION_ACTIVITY) { sessionActivity("F-0011") })
        assertEquals(1, server.requestCount)
    }
}
