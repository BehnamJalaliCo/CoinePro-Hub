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
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.dp
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
 * ⟨1.23⟩ Contract §41, at a phone's height (860dp), night and day, with the demo holding: the session shows its work live.
 * ⟨1.0.1⟩ Part C (C2.2): the one-line header («کار n از m», the pace, the mood light) over the plan's line of parts; the «الان» bar
 * over the composer with two at work (their marks side by side, who and how many others, the whole sentence, the timer), the newest
 * steps as thin lines at the end of the thread (the one just heard on the stream among them); a stuck session (ONE «گره» card: why,
 * and its fix); one waiting for the owner as «کار زنده» says it; and «کار زنده», who works and every step.
 * Each is checked to show its words before it is drawn.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h860dp-xxhdpi")
class LiveWorkScreensTest(private val name: String, private val night: Boolean) {
    /** A screen, what it must show, and whether the demo's stream plays its first beats once it has loaded. */
    private class Scene(val shows: List<String>, val stream: Boolean = false, val content: @Composable () -> Unit)

    companion object {
        private val SCREENS: Map<String, Scene> = linkedMapOf(
            // Two at work on F-0104: the CEO and his SEO specialist; the newest steps at the end of the thread, the last one heard on
            // the stream; the plan 1 of 2.
            "session-live-working" to Scene(listOf("مدیرعامل پرو-چارت", "نفر دیگر", "کار 1 از 2", "کار میکند"), stream = true) {
                com.coinepro.hq.ui.session.OrderSessionScreen("F-0104")
            },
            // F-0103 stuck: no one to hire and hiring closed; ONE «گره» card says why, with what fixes it.
            "session-live-stuck" to Scene(listOf("گره", "استخدام را باز کن")) { com.coinepro.hq.ui.session.OrderSessionScreen("F-0103") },
            // F-0101 waits for the owner, as «کار زنده» says it: nobody works, and what it waits for. ⟨1.0.1⟩ C1.5: the session's page
            // in this state is `session-chat-your-turn` (the two used to be one and the same picture).
            "session-live-waiting" to Scene(listOf("کار زنده", "منتظر تو")) { Sheet("F-0101") },
            // «کار زنده»: the two at work on F-0104, each with its line and time, then every step.
            "session-live-sheet" to Scene(listOf("کار زنده", "قدم‌ها", "مدیرعامل پرو-چارت")) { Sheet("F-0104") },
        )

        @Composable
        private fun Sheet(ref: String) {
            val a = com.coinepro.hq.ui.rememberQuery("session-activity:$ref", "session-activity") { sessionActivity(ref) }.data ?: return
            Column(
                Modifier.fillMaxSize().background(Divan.colors.overlay).verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Text("کار زنده", style = Divan.type.h2)
                com.coinepro.hq.ui.session.LiveWorkSheetBody(a, ready = false, canNudge = true, nudging = false, onNudge = {})
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
        // ⟨1.0.1⟩ the files of a session and of an output are drawn as they are (their pictures and posters)
        picturesOn()
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

    @org.junit.After
    fun tearDown() = picturesOff()

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
        // The report, the activity, the talk and the personas: each a demo answer of ~60–150 ms on OkHttp threads. Let them land.
        settle(20)
        // One beat of the demo's stream: F-0104's next step arrives as a `session.activity` line and is appended at once.
        // The line shows at once; the stream's tag then asks the hub again two seconds later (the specialist's next step number).
        if (scene.stream) {
            graph.env.value.stream.demoSeed(1)
            settle(2)
            shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(2_100))
            settle(6)
        }
        settle(4)
        for (t in scene.shows) assertTrue("$name shows «$t»", compose.onAllNodesWithText(t, substring = true).fetchSemanticsNodes().isNotEmpty())
        if (scene.stream) {
            compose.onNodeWithTag("now-bar").assertExists()
            assertTrue("the streamed line is at the end of the thread", compose.onAllNodesWithText("tradingview.com", substring = true).fetchSemanticsNodes().isNotEmpty())
        }
        compose.onRoot().captureRoboImage(
            "src/test/screenshots/$name-${if (night) "night" else "day"}.png",
            roborazziOptions = RoborazziOptions(
                recordOptions = RoborazziOptions.RecordOptions(resizeScale = 0.5),
                compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.002f),
            ),
        )
    }
}
