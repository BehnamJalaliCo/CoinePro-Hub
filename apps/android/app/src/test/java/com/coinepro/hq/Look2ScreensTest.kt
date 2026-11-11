package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.hasScrollToIndexAction
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.test.performScrollToKey
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.data.CLOSED_FA
import com.coinepro.hq.core.data.DESK_EMPTY_FA
import com.coinepro.hq.core.data.DESK_FA
import com.coinepro.hq.core.data.DIRECT_FA
import com.coinepro.hq.core.data.DIRECT_NOW_FA
import com.coinepro.hq.core.data.HELD_FA
import com.coinepro.hq.core.data.MOOD_FA
import com.coinepro.hq.core.data.STILL_FA
import com.coinepro.hq.core.data.VIDEO_FAILED_FA
import com.coinepro.hq.core.data.orderParticipants
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.designsystem.SpringSheetPreview
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.look.FilesStrip
import com.coinepro.hq.ui.look.PublishDeskScreen
import com.coinepro.hq.ui.look.VideoFailed
import com.coinepro.hq.ui.outputs.PUBLISH_SHEET_FA
import com.coinepro.hq.ui.outputs.PUBLISH_SHEET_SUB_FA
import com.coinepro.hq.ui.outputs.PublishDecisionBar
import com.coinepro.hq.ui.outputs.PublishFields
import com.coinepro.hq.ui.outputs.PublishState
import com.coinepro.hq.ui.outputs.kindFromMime
import com.coinepro.hq.ui.outputs.publishable
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.session.OrderSessionScreen
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * ⟨1.0.1⟩ Part C, phase 2 of the look, at a phone's height (880dp), night and day, with the demo holding and its pictures drawn.
 * - The session (C2.2): a workshop turn with its build ring (and near its hour: amber, «نزدیک سقف زمان»), ⟨2026-11-11⟩ a session that
 *   stands still («ایستاده», its card and «ادامه بده») and one whose draft waits in ChatGPT's queue (an outside call), the holder's own direct
 *   turn, the work held («ادامه بده»), a session ready with a reel (its files as a strip in the thread, «تأیید و انتشار» in the
 *   decision bar), the row of a video that will not play, a closed session's end leaf, the details (the files it made, the direct
 *   session's line) and «کار زنده» of a turn.
 * - The publish desk (C2.3): its top (the first ready card carries the page's gold), its queue and what is done, empty, on a hub
 *   before it, and its line on the home.
 * - Output and «تأیید و انتشار» (C3.3): the publish sheet of a reel with its cover and the account's best hour; the outputs as media
 *   cards, and their header folded into one bar.
 * - The working group (C3.4): a sealed group's member tiles with their one settings block, and a member that stands still.
 * Each is checked to show its words before it is drawn.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class Look2ScreensTest(private val name: String, private val night: Boolean) {
    private enum class Then { NOTHING, HOLD, QUEUE, FOLD, STILL, SETTING }

    /** A scene: what the demo is asked for first, what it must show (and must not), what is done on it before it is drawn. */
    private class Scene(
        val shows: List<String>, val hides: List<String> = emptyList(), val before: () -> Unit = {}, val then: Then = Then.NOTHING,
        val content: @Composable () -> Unit,
    )

    companion object {
        private val SCREENS: Map<String, Scene> = linkedMapOf(
            // ------------------------------------------------------------------ C2.2 the session
            // A workshop builds a motion graphic for Pro-Chart: the ring of real time out of its hour, the last line it wrote, «نگه دار».
            "look2-session-workshop" to Scene(listOf("سازنده‌ی موشن‌گرافی", "کارگاه", "صحنه‌ی ۳ را رندر میکند", "از 60 دقیقه", "نگه دار", "کار میکند"), hides = listOf("نزدیک سقف زمان")) { OrderSessionScreen("F-0090") },
            // …56 minutes in: the ring turns amber and says so in words.
            "look2-session-workshop-late" to Scene(listOf("نزدیک سقف زمان", "56", "نگه دار"), before = { LookDemo.ring = "late" }) { OrderSessionScreen("F-0090") },
            // A direct session: the holder himself works on the owner's order; no «کارگاه» word.
            "look2-session-direct" to Scene(listOf(DIRECT_NOW_FA, "مدیر رسانه‌ی تریدیار", "caption.md", "نگه دار"), hides = listOf("کارگاه")) { OrderSessionScreen("F-0091") },
            // «نگه دار» was tapped: the work stands, and the same place reads «ادامه بده».
            "look2-session-held" to Scene(listOf(HELD_FA, "ادامه بده"), hides = listOf("نگه دار"), then = Then.HOLD) { OrderSessionScreen("F-0090") },
            // Ready with a reel: its files as tiles where they arrived, and the one confirmation in the decision bar.
            "look2-session-ready-publish" to Scene(listOf("خروجی تحویل شد", "reel-stoploss.mp4", "cover.png", "کاور ریلز", "آماده‌ی انتشار", "تأیید و انتشار", "اصلاح", "فقط ببند", "با تأیید تو همین فایل منتشر میشود")) {
                OrderSessionScreen("F-0092")
            },
            // The files of an output as a strip, and a video that will not play: one sentence and its download.
            "look2-session-video" to Scene(listOf("reel-stoploss.mp4", VIDEO_FAILED_FA, "دانلود")) { Files("O-000967") },
            // A closed session: what it made, how long it took, what it used; read from its top.
            "look2-session-closed" to Scene(listOf("این جلسه تأیید و بایگانی شد", "دوباره باز کن", "ساخته شد", "1 ساعت و 51 دقیقه", "تمام", CLOSED_FA)) { OrderSessionScreen("F-0093") },
            // ⟨2026-11-11⟩ The owner's 12-hour stall: nobody works and the hub said «آرام». The page says «ایستاده», one calm card with the
            // last thing done and when, and «ادامه بده» (the page's one gold; the send steps back).
            "look2-session-still" to Scene(
                listOf(MOOD_FA.getValue("still"), STILL_FA, "از ChatGPT خواسته شد و در صف است", "دیشب", "22:28", "ادامه بده", "کار 3 از 18", "با من"),
                hides = listOf(MOOD_FA.getValue("idle"), "نگه دار"),
            ) { OrderSessionScreen("F-0095") },
            // …the same session while the draft waits in ChatGPT's queue: an outside call at work in the «الان» bar, its model's mark,
            // whose it is, the whole sentence and its timer; no ring, and nothing to hold.
            "look2-session-call" to Scene(
                listOf("ChatGPT", "پرو-چارت", "در صف ChatGPT: پیش‌نویس متن", "4:00", "کار میکند"),
                hides = listOf("نگه دار", MOOD_FA.getValue("still"), STILL_FA, "از 60 دقیقه"),
            ) { OrderSessionScreen("F-0094") },
            // «جزئیات»: everything it made at hand, and (a direct session) who does the work.
            "look2-session-details" to Scene(listOf("متن فرمان", "فایل‌های خروجی", "هر چه در این جلسه ساخته شد", "وضعیت و روش کار")) { Details("F-0092") },
            "look2-session-details-direct" to Scene(listOf("وضعیت و روش کار", DIRECT_FA)) { Details("F-0091") },
            // «کار زنده» of a turn: its ring, its line, every step.
            "look2-live-sheet" to Scene(listOf("کار زنده", "سازنده‌ی موشن‌گرافی", "قدم‌ها", "صحنه‌ی ۲ را رندر کرد")) { Live("F-0090") },
            // ------------------------------------------------------------------ C2.3 the publish desk
            "look2-desk-top" to Scene(listOf(DESK_FA, "آماده‌ی انتشار", "تریدیار", "اینستاگرام", "@tradeyar", "تأیید و انتشار")) { PublishDeskScreen() },
            "look2-desk-queue" to Scene(listOf("در صف", "در حال انتشار", "امشب", "21:30", "خودکار", "لغو", "منتشرشده"), then = Then.QUEUE) { PublishDeskScreen() },
            "look2-desk-empty" to Scene(listOf(DESK_FA, DESK_EMPTY_FA), before = { LookDemo.desk = "empty" }) { PublishDeskScreen() },
            // A hub before §55: the page says so (its tab and the home's line are not there).
            "look2-desk-old-hub" to Scene(listOf("میز انتشار بعد از به‌روزرسانی ستاد می‌آید"), hides = listOf("آماده‌ی انتشار"), before = { LookDemo.desk = "old" }) { PublishDeskScreen() },
            "look2-home-desk-line" to Scene(listOf(DESK_FA, "خروجی آماده‌ی انتشار", "در صف")) { com.coinepro.hq.ui.office.OfficeScreen() },
            "look2-home-old-hub" to Scene(listOf("نوبت تو"), hides = listOf(DESK_FA), before = { LookDemo.desk = "old" }) { com.coinepro.hq.ui.office.OfficeScreen() },
            // ------------------------------------------------------------------ C3.3 output and «تأیید و انتشار»
            "look2-publish-sheet" to Scene(listOf(PUBLISH_SHEET_FA, PUBLISH_SHEET_SUB_FA, "reel-stoploss.mp4", "@tradeyar", "cover.png", "حد ضرر را کجا بگذاریم", "بهترین ساعت (", "انتشار", "همین حالا")) { Sheet("O-000967") },
            "look2-outputs" to Scene(listOf("خروجی‌ها", DESK_FA, "همه", "ریلز: حد ضرر را کجا بگذاریم")) { com.coinepro.hq.ui.outputs.OutputsScreen("all") },
            "look2-outputs-folded" to Scene(listOf("خروجی‌ها", "فیلترها"), then = Then.FOLD) { com.coinepro.hq.ui.outputs.OutputsScreen("all") },
            // ------------------------------------------------------------------ C3.4 the working group
            "look2-group-tiles" to Scene(listOf("شرکت‌های عضو", "تریدیار", "آخرین نوبت", "نوبت بعد", "انتشار خودکار", "گوینده‌ی محتوا", "دفتر موضوع‌ها", "تنظیم")) { Members("PB-0001") },
            // «تنظیم» opens the standing word in place: «استوری هم بشود», the hour, «بهترین ساعت، خودکار», «ذخیره».
            "look2-group-settings" to Scene(listOf("استوری هم بشود", "بهترین ساعت، خودکار", "ذخیره"), then = Then.SETTING) { Members("PB-0001") },
            // A member that stands still: why, in one line, and the quiet «راه بینداز».
            "look2-group-still" to Scene(listOf("ایستاده", "سه نوبت پشت هم بسته‌ای تحویل نشد", "راه بینداز"), then = Then.STILL) { Members("PB-0001") },
        )

        @Composable
        private fun Cardlike(content: @Composable () -> Unit) {
            Column(
                Modifier.fillMaxSize().background(Divan.colors.page).verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) { content() }
        }

        /** The files of an output as the strip draws them, then the row of a video that would not play. */
        @Composable
        private fun Files(ref: String) {
            val d = rememberQuery("deliverable:$ref", "deliverables") { deliverable(ref) }.data ?: return
            val files = d.attachments.map(::kindFromMime)
            Cardlike {
                Text("فایل‌ها", style = Divan.type.h3)
                FilesStrip(files)
                VideoFailed(files.first())
            }
        }

        @Composable
        private fun Details(ref: String) {
            val o = com.coinepro.hq.ui.v29.rememberOrderReport(ref).data ?: return
            val a = rememberQuery("session-activity:$ref", "session-activity") { sessionActivity(ref) }.data
            SpringSheetPreview("جزئیات جلسه", sub = "همه‌ی چیزهایی که کنار گفتگو لازم میشوند", fill = true) {
                com.coinepro.hq.ui.session.SessionDetailsBody(
                    o, closed = false, sessionsOn = true, participants = orderParticipants(o.participants), addressee = null,
                    onPick = {}, onAddPerson = {}, onAddModel = {}, onPace = {}, onTasksChanged = {}, onClose = {}, onReopen = {}, onHide = {}, onErase = {},
                    activity = a, canNudge = true,
                )
            }
        }

        @Composable
        private fun Live(ref: String) {
            val a = rememberQuery("session-activity:$ref", "session-activity") { sessionActivity(ref) }.data ?: return
            SpringSheetPreview("کار زنده", sub = "هر قدم کار این جلسه، همان لحظه که برداشته میشود.", fill = true) {
                com.coinepro.hq.ui.session.LiveWorkSheetBody(a, ready = false, canNudge = true, nudging = false, onNudge = {})
            }
        }

        /** The publish sheet as it stands over its page: the fields, and its one act stuck to its bottom. */
        @Composable
        private fun Sheet(ref: String) {
            val d = rememberQuery("deliverable:$ref", "deliverables") { deliverable(ref) }.data ?: return
            val p = rememberQuery("publish:$ref", "publish", "orders") { publishPanel(ref) }.data ?: return
            val s = remember(d, p) { PublishState(d, publishable(d).first(), p) }
            SpringSheetPreview(PUBLISH_SHEET_FA, sub = PUBLISH_SHEET_SUB_FA, bar = { PublishDecisionBar(s, false) {} }, fill = true) { PublishFields(s) }
        }

        /** The member companies of a sealed working group, as its page draws them. */
        @Composable
        private fun Members(ref: String) {
            val pb = com.coinepro.hq.ui.playbook.rememberPlaybook(ref).data ?: return
            Cardlike {
                com.coinepro.hq.designsystem.SectionTitle("شرکت‌های عضو")
                com.coinepro.hq.ui.playbook.MemberTiles(pb)
            }
        }

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCREENS.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-11-06T08:30:00Z")
        picturesOn()
        LookDemo.reset()
        SCREENS.getValue(name).before()
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.link.setForeground(false)
        graph.enterDemo()
        DemoLive.servers?.still = true
    }

    @After
    fun tearDown() {
        LookDemo.reset()
        picturesOff()
    }

    private fun settle(times: Int) = repeat(times) {
        Thread.sleep(200)
        shadowOf(Looper.getMainLooper()).idle()
        compose.mainClock.advanceTimeBy(250)
    }

    @Test
    fun screen() {
        val nav = object : Nav {
            override fun go(route: String) = Unit
            override fun back() = Unit
        }
        val scene = SCREENS.getValue(name)
        compose.mainClock.autoAdvance = false
        compose.setContent {
            DivanTheme(night) {
                CompositionLocalProvider(
                    LocalEnv provides graph.env.value, LocalToasts provides Toasts(), LocalNav provides nav,
                    com.coinepro.hq.designsystem.LocalReducedMotion provides true,
                ) {
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { scene.content() }
                }
            }
        }
        // The report, the activity, the talk, the files and their pictures: each a demo answer on OkHttp threads. Let them land.
        settle(22)
        when (scene.then) {
            Then.NOTHING -> Unit
            Then.HOLD -> compose.onNodeWithText("نگه دار").performClick()
            Then.QUEUE -> compose.onNode(hasScrollToIndexAction()).performScrollToKey("h-queue")
            Then.FOLD -> compose.onNode(hasScrollToIndexAction()).performScrollToIndex(4)
            Then.STILL -> compose.onNodeWithText("راه بینداز").performScrollTo()
            Then.SETTING -> compose.onAllNodesWithText("تنظیم")[0].performClick()
        }
        if (scene.then != Then.NOTHING) settle(10)
        for (t in scene.shows) assertTrue("$name shows «$t»", compose.onAllNodesWithText(t, substring = true).fetchSemanticsNodes().isNotEmpty())
        for (t in scene.hides) assertTrue("$name never shows «$t»", compose.onAllNodesWithText(t, substring = true).fetchSemanticsNodes().isEmpty())
        compose.onRoot().captureRoboImage(
            "src/test/screenshots/$name-${if (night) "night" else "day"}.png",
            roborazziOptions = RoborazziOptions(
                recordOptions = RoborazziOptions.RecordOptions(resizeScale = 0.5),
                compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.002f),
            ),
        )
    }
}
