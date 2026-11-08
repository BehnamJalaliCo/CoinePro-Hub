package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
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
 * ⟨0.19.0⟩ The session in order, at a phone's height (860dp), night and day, on the demo's dense session (F-0100, as dense as the owner's
 * own on 2026-11-08: his nine steps, the media director's long notes, two hires approved, many of the hub's own lines with a ref among them,
 * two results together, two blockers, two at work). As it opens: the steps between two turns one quiet row each («۳ رویداد · 05:34–05:40»),
 * the two results one card, «۲ گیر» over the composer under the live work, the head's pace and «کار ۳ از ۹». Then the newest row of steps
 * opened (each line whole, without its ref), and the blockers opened (each with why, since when, and its fix). Each is checked to show its
 * words before it is drawn.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h860dp-xxhdpi")
class SessionTidyScreensTest(private val name: String, private val night: Boolean) {
    private enum class Tap { NOTHING, EVENTS, BLOCKERS }

    private class Scene(val tap: Tap, val shows: List<String>, val hides: List<String> = emptyList())

    companion object {
        private val SCREENS: Map<String, Scene> = linkedMapOf(
            "session-tidy" to Scene(Tap.NOTHING, listOf("۲ خروجی تحویل شد", "۲ گیر", "کار ۳ از ۹", "۴ رویداد", "مدیر رسانه‌ی پرو-چارت دارد کار میکند · قدم ۷")),
            // The four steps since the CEO answered, each whole; the one the hub wrote with a ref in parentheses without it.
            "session-tidy-open" to Scene(Tap.EVENTS, listOf("زیرنویس ریلز آزمایشی به تدوینگر سپرده شد", "صداگذاری منتظر بودجه ماند"), hides = listOf("W-000413", "W-000412")),
            "session-tidy-blockers" to Scene(Tap.BLOCKERS, listOf("بودجه بده", "وصل کن", "اینستاگرام پرو-چارت هنوز وصل نیست")),
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
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.link.setForeground(false)
        graph.enterDemo()
        DemoLive.servers?.still = true
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
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { com.coinepro.hq.ui.session.OrderSessionScreen("F-0100") }
                }
            }
        }
        settle(20)
        when (scene.tap) {
            Tap.NOTHING -> Unit
            // The newest row of steps: four since the CEO answered.
            Tap.EVENTS -> compose.onNodeWithText("۴ رویداد").performClick()
            Tap.BLOCKERS -> compose.onNodeWithTag("blockers").performClick()
        }
        settle(6)
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
