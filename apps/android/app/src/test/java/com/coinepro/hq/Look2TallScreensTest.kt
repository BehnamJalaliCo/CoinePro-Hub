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
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onRoot
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.data.DESK_FA
import com.coinepro.hq.core.data.ROUTE_WAITS_FA
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
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
 * ⟨1.0.1⟩ Part C, phase 2 of the look, drawn tall (2000dp) so a whole page is one picture, night and day, with the demo holding and
 * its pictures drawn: the publish desk with its ready cards (the first one's gold, the others outlined, a company whose path is not
 * set), an output that opens with its video, one with its picture and one that is a document (its first lines, the rating as the
 * page's action), and a working group sealed (member tiles, each routine's last seven runs, the definition folded) and as a draft
 * («مُهر کارگروه» in the decision bar with its one-line summary). Each is checked to show its words before it is drawn.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h2000dp-xxhdpi")
class Look2TallScreensTest(private val name: String, private val night: Boolean) {
    private class Scene(val shows: List<String>, val hides: List<String> = emptyList(), val content: @Composable () -> Unit)

    companion object {
        private val SCREENS: Map<String, Scene> = linkedMapOf(
            // The desk: what is ready, newest first; one full gold; a company whose path the technical team connects has no action.
            "look2-desk" to Scene(listOf(DESK_FA, "هر خروجی آماده، یک جا", "آماده‌ی انتشار", "بهترین ساعت این حساب", "ریلز: مقاومت هفته", ROUTE_WAITS_FA, "تأیید و انتشار")) {
                com.coinepro.hq.ui.look.PublishDeskScreen()
            },
            // An output that opens with the thing itself: the reel, then its numbers, its text, its files, where each stands; the
            // decision bar carries «تأیید و انتشار» and the quiet «اصلاح».
            "look2-output-video" to Scene(
                listOf("ریلز: حد ضرر را کجا بگذاریم", "ساخت", "مصرف", "331K", "سازنده", "امتیاز تو", "خوانده شد", "فایل‌ها", "انتشار در اینستاگرام", "تأیید و انتشار", "اصلاح", "بی کارت و بی اثر انگشت", "ثبت امتیاز"),
            ) { com.coinepro.hq.ui.outputs.OutputScreen("O-000967") },
            "look2-output-picture" to Scene(listOf("پست ۱: خط روند در یک نگاه", "post-01.jpg", "تأیید و انتشار", "@pro.chart")) { com.coinepro.hq.ui.outputs.OutputScreen("O-000969") },
            // A document: its first lines and «همه‌ی متن»; no decision bar, so the rating is the page's one action.
            "look2-output-document" to Scene(listOf("گزارش صبحگاهی", "همه‌ی متن", "امتیاز تو", "ثبت امتیاز"), hides = listOf("تأیید و انتشار")) { com.coinepro.hq.ui.outputs.OutputScreen("O-000032") },
            // A sealed working group: its members as tiles, each routine with its last seven runs, its definition folded.
            "look2-group-sealed" to Scene(
                listOf("کارگروه‌های آماده", "مُهر شده", "به شرکت دیگر بده", "بازنشسته کن", "شرکت‌های عضو", "در کار", "ایستاده", "راه بینداز", "روال‌ها", "هفت نوبت آخر هر روال", "نوبت بعد", "تعریف کارگروه", "جایگاه"),
                hides = listOf("مُهر کارگروه"),
            ) { com.coinepro.hq.ui.playbook.PlaybookScreen("PB-0001") },
            // A draft: lightly edited, and its seal in the decision bar with what it starts in one line.
            "look2-group-draft" to Scene(listOf("پیش‌نویس", "عنوان", "چه کسانی", "چه کاری، کِی", "قانون‌ها", "مُهر کارگروه", "ذخیره", "با مُهر، روال‌ها شروع میشوند", "جایگاه")) {
                com.coinepro.hq.ui.playbook.PlaybookScreen("PB-0002")
            },
            // A group among «کارگروه‌ها»: member tiles, routines with their dots, its history and its definition folded.
            "look2-group-page" to Scene(listOf("کارگروه‌ها", "شرکت‌های عضو", "روال‌ها", "هفت نوبت آخر هر روال", "شاخص‌ها")) { com.coinepro.hq.ui.v29.GroupScreen("content") },
        )

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
        // The page, its files, its publish panel, the runs and the pictures: each a demo answer on OkHttp threads. Let them land.
        repeat(26) {
            Thread.sleep(200)
            shadowOf(Looper.getMainLooper()).idle()
            compose.mainClock.advanceTimeBy(250)
        }
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
