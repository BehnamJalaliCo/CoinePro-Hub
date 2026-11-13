package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onRoot
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
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
 * ⟨1.1.0⟩ Contract §59, night and day, with the demo holding, drawn tall (2400dp): the library of working groups and the automations.
 * - the library: search, the three filters, a card per playbook with its platform, version, companies and figures;
 * - PB-0004 «ریلز روزانه‌ی پروچارت» sealed v2: its member, the flow of twelve steps (one opened), the package, the lessons (folded),
 *   the versions with what changed, the acts; and its v1 (another page of the same playbook); «مقایسه» of v1 and v2;
 * - «در شرکت دیگر به کار ببر», the form as it opens;
 * - the automations board: the road's health (one part on amber), today in three figures, the owner's day, each automation with its switch;
 * - AT-0700's page (the switch, the next run, the controls, today against the budget, the settings, the runs with their figures);
 * - its replies (the comment, the story and the DM, the DM's text and button and Instagram's preview, the public replies numbered in the
 *   order they go out, and how often a person is answered);
 * - a run at work (its timeline: done steps with their outputs, the build running) and a run that failed at the cover (the one plain line,
 *   «دوباره از همین قدم» and «رد کردن این نوبت»); the calendar of the next two weeks.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h2400dp-xxhdpi")
class LibraryScreensTest(private val name: String, private val night: Boolean) {
    /** A screen and what it must show (checked before the picture is taken). */
    private class Scene(val shows: List<String>, val content: @Composable () -> Unit)

    companion object {
        private val SCENES: Map<String, Scene> = linkedMapOf(
            "library59-library" to Scene(listOf("کتابخانه‌ی کارگروه‌ها", "ریلز روزانه‌ی پروچارت", "هر اجرا")) { com.coinepro.hq.ui.playbook.PlaybooksScreen() },
            "library59-playbook" to Scene(listOf("روند، قدم‌به‌قدم", "بسته‌ای که هر روز میسازد", "درس‌ها", "نسخه‌ها", "در شرکت دیگر به کار ببر")) {
                com.coinepro.hq.ui.playbook.PlaybookScreen("PB-0004")
            },
            "library59-playbook-v1" to Scene(listOf("نسخه‌ی ۱")) { com.coinepro.hq.ui.playbook.PlaybookScreen("PB-0004", 1) },
            "library59-compare" to Scene(listOf("بازبینی صدا")) {
                val pb = com.coinepro.hq.ui.playbook.rememberPlaybook("PB-0004").data
                if (pb != null) com.coinepro.hq.designsystem.SpringSheetPreview("مقایسه‌ی نسخه‌ها", fill = true) { com.coinepro.hq.ui.playbook.CompareBody(pb) }
            },
            "library59-use" to Scene(listOf("شرکت و حساب", "جواب‌ها", "زمان", "بودجه")) { com.coinepro.hq.ui.playbook.UseScreen("PB-0004") },
            "auto-board" to Scene(listOf("اتوماسیون‌ها", "مرورگر کمک‌کارها", "ریلز روزانه‌ی پروچارت", "انتشار خودکار", "۱۲ کامنت")) {
                com.coinepro.hq.ui.automation.AutomationsBoardScreen()
            },
            "auto-flow" to Scene(listOf("همین حالا اجرا کن", "ساعت انتشار", "اجراها و نتیجه‌ها", "بازپخش جلسه‌ی زنده‌ی طلا")) { com.coinepro.hq.ui.automation.FlowScreen("AT-0700") },
            "auto-replies" to Scene(listOf("کامنت زیر ریلز", "متن دایرکت", "ورود به پرو چارت", "به نوبت", "سالی یک بار")) { com.coinepro.hq.ui.automation.RepliesScreen("AT-0700") },
            "auto-run" to Scene(listOf("سه خطای رایج در کشیدن خط روند", "ساخت ویدیو", "بیشترین دقت", "قدم‌ها")) { com.coinepro.hq.ui.automation.FlowRunScreen("RN-000704") },
            "auto-run-failed" to Scene(listOf("دوباره از همین قدم", "رد کردن این نوبت", "سه بار تصویر نساخت")) { com.coinepro.hq.ui.automation.FlowRunScreen("RN-000701") },
            "auto-calendar" to Scene(listOf("تقویم اتوماسیون‌ها", "سطح‌های حمایت در یک دقیقه")) { com.coinepro.hq.ui.automation.AutomationsCalendarScreen() },
        )

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCENES.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-11-07T08:30:00Z")
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.link.setForeground(false)
        graph.enterDemo()
        DemoLive.servers?.still = true
    }

    @Test
    fun screen() {
        val nav = object : Nav {
            override fun go(route: String) = Unit
            override fun back() = Unit
        }
        val scene = SCENES.getValue(name)
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
        // Each screen reads two or three demo answers of ~60 ms on OkHttp threads: let them land.
        repeat(20) {
            Thread.sleep(200)
            shadowOf(Looper.getMainLooper()).idle()
            compose.mainClock.advanceTimeBy(250)
        }
        for (t in scene.shows) assertTrue("$name shows «$t»", compose.onAllNodesWithText(t, substring = true).fetchSemanticsNodes().isNotEmpty())
        if (name == "auto-replies") assertTrue("the public replies are numbered in turn", compose.onAllNodesWithTag("pool-line").fetchSemanticsNodes().size == 3)
        compose.onRoot().captureRoboImage(
            "src/test/screenshots/$name-${if (night) "night" else "day"}.png",
            roborazziOptions = RoborazziOptions(
                recordOptions = RoborazziOptions.RecordOptions(resizeScale = 0.5),
                compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.002f),
            ),
        )
    }
}
