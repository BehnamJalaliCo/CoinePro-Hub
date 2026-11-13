package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeRight
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.data.TEAM_FA
import com.coinepro.hq.core.data.hireAskFa
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.designsystem.SheetHandle
import com.coinepro.hq.designsystem.SpringSheetPreview
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.session.HIRE_SUB_FA
import com.coinepro.hq.ui.session.HireSeatBody
import com.coinepro.hq.ui.session.OrderSessionScreen
import com.coinepro.hq.ui.session.SideTalk
import com.coinepro.hq.ui.session.rememberSessionTeam
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
 * ⟨1.35⟩ §57 «تیم این جلسه» (1.0.3) at a phone's height, night and day, with the demo holding: Pro-Chart's daily reels session (F-0094)
 * with its row under the header (the holder and the scriptwriter at work, his line unread, «+ کارگردان» and «+ موشن‌گرافی» dashed),
 * the same row run to its end where «گوینده» stands, the scriptwriter's side talk in its half-height sheet (his lines and the owner's
 * as the session's bubbles, the composer, close) and the one question before an empty seat is filled. Each is checked to show its
 * words before it is drawn.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class TeamScreensTest(private val name: String, private val night: Boolean) {
    private enum class Then { NOTHING, NARRATOR }

    private class Scene(val shows: List<String>, val hides: List<String> = emptyList(), val then: Then = Then.NOTHING, val content: @Composable () -> Unit)

    companion object {
        private const val REF = "F-0094"

        private val SCREENS: Map<String, Scene> = linkedMapOf(
            // The row under the header: the holder first (at work: his ring), the scriptwriter (his ring and the dot of his unread line),
            // the two empty media seats dashed.
            "team-session" to Scene(listOf(TEAM_FA, "مسئول جلسه", "نویسنده", "کارگردان", "موشن‌گرافی", "ChatGPT")) { OrderSessionScreen(REF) },
            // …run to its end: «گوینده» with the company's voice.
            "team-session-narrator" to Scene(listOf(TEAM_FA, "گوینده", "Kore"), then = Then.NARRATOR) { OrderSessionScreen(REF) },
            // A filled seat's side talk: half the screen, his lines and the owner's, the composer and close; nothing of the main thread.
            "team-side-talk" to Scene(
                listOf("با سناریست پرو-چارت", "گفتگوی کوتاه", "زیر یک دقیقه", "کلمه‌ی کامنت «چارت» باشد", "پیش‌نویس تازه در صف", "به سناریست پرو-چارت بگو"),
                hides = listOf("حرف‌های پیش‌تر"),
            ) { Side("PC-SCR-01") },
            // An empty seat asks once, and «استخدام کن» is the sheet's one act (no passkey).
            "team-hire" to Scene(listOf("کارگردان استخدام شود؟", HIRE_SUB_FA, "استخدام کن")) { Hire("role:video_director") },
        )

        /** The side talk as its sheet stands over the session: the handle, then the talk (half the screen tall). */
        @Composable
        private fun Side(code: String) {
            val seat = rememberSessionTeam(REF).data?.seats?.firstOrNull { it.code == code } ?: return
            Box(Modifier.fillMaxSize().background(Divan.colors.scrim).padding(top = 24.dp), contentAlignment = Alignment.BottomCenter) {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)).background(Divan.colors.overlay)) {
                    SheetHandle()
                    SideTalk(REF, seat, closed = false, onClose = {})
                }
            }
        }

        @Composable
        private fun Hire(key: String) {
            val seat = rememberSessionTeam(REF).data?.seats?.firstOrNull { it.key == key } ?: return
            SpringSheetPreview(hireAskFa(seat), sub = HIRE_SUB_FA, fill = true) { HireSeatBody(REF, seat) {} }
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
        TeamDemo.reset()
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.link.setForeground(false)
        graph.enterDemo()
        DemoLive.servers?.still = true
    }

    @After
    fun tearDown() {
        TeamDemo.reset()
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
        // The report, the activity, the talk and the team: each a demo answer on OkHttp threads. Let them land.
        settle(22)
        when (scene.then) {
            Then.NOTHING -> Unit
            Then.NARRATOR -> {
                // found first without waiting (a missing chip fails here); the row is swiped to its end (in a right-to-left row the
                // end is on the left), never scrolled by its semantics, which animates on a clock this test holds still
                assertTrue("$name has the narrator's chip", compose.onAllNodesWithTag("team-narrator").fetchSemanticsNodes().size == 1)
                compose.onNodeWithTag("session-team").performTouchInput { swipeRight(startX = width * 0.05f, endX = width * 0.75f, durationMillis = 300) }
            }
        }
        if (scene.then != Then.NOTHING) settle(6)
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
