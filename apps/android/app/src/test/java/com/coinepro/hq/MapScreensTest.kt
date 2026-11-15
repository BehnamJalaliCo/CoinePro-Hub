package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.SemanticsNodeInteractionsProvider
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
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
import com.coinepro.hq.ui.rememberQuery
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Assert.assertEquals
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
 * ⟨1.2.0⟩ Contract §59.7.1, night and day, with the demo holding: an automation's map, as n8n draws one.
 * - `N8:zaribsad_stories` on its map: the lanes, the seven stories fanned out from «زمان‌بندی» with their hours, the live sample of
 *   2026-11-15 (three past their hour, one out, three waiting), the days above, the legend under; the controls the hub keeps are not offered;
 * - the same canvas all on the screen («همه در صفحه»), and its «قدم‌ها» with each step's state that day;
 * - `N8:prochart_reels` at work in the render (lapis, the dots on the edge into it), the model chips;
 * - a node's sheet (what it does, that day, its files); the map full screen; an n8n day's timeline (its words, no rerun).
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h1600dp-xxhdpi")
class MapScreensTest(private val name: String, private val night: Boolean) {
    /** A screen, what it must show, what it must not, and a tap before the picture. */
    private class Scene(
        val shows: List<String>,
        val hides: List<String> = emptyList(),
        val act: ((SemanticsNodeInteractionsProvider) -> Unit)? = null,
        val content: @Composable () -> Unit,
    )

    companion object {
        private const val STORIES = "N8:zaribsad_stories"
        private val SCENES: Map<String, Scene> = linkedMapOf(
            "map-stories" to Scene(
                listOf("نقشه", "۱ از ۴ استوری منتشر شد", "استوری ۵", "اینستاگرام", "منتظر ساعتش", "جا ماند", "روند خودکار"),
                hides = listOf("همین حالا اجرا کن", "مکث", "منتظر مُهر تو"),
            ) { com.coinepro.hq.ui.automation.FlowScreen(STORIES) },
            "map-stories-fit" to Scene(listOf("نزدیک", "وقتی اولین استوری رفت"), act = { it.onAllNodesWithText("همه در صفحه")[0].performClick() }) {
                com.coinepro.hq.ui.automation.FlowScreen(STORIES)
            },
            "map-stories-steps" to Scene(listOf("قدم، به همین ترتیب", "کلمه‌ی امروز"), act = { it.onAllNodesWithText("قدم‌ها")[0].performClick() }) {
                com.coinepro.hq.ui.automation.FlowScreen(STORIES)
            },
            "map-reel" to Scene(listOf("ساخت ویدیو، یک بار رندر", "در کار", "Opus 5.5", "در کارگاه ساخته میشود")) {
                com.coinepro.hq.ui.automation.FlowScreen("N8:prochart_reels")
            },
            "map-node" to Scene(listOf("چه میکند", "فایل‌های همین روز", "story_1.jpg", "خط زمان همین روز")) {
                val f = com.coinepro.hq.ui.automation.rememberFlow(STORIES).data
                val run = rememberQuery("test-map-day:F-0029", "lines") { lineRun("F-0029") }.data
                if (f != null && run != null) {
                    val (title, sub) = com.coinepro.hq.ui.automation.nodeHead(f, "compose", run)
                    com.coinepro.hq.designsystem.SpringSheetPreview(title, sub = sub, fill = true) { com.coinepro.hq.ui.automation.NodeSheetBody(f, "compose", run) {} }
                }
            },
            "map-full" to Scene(listOf("نقشه‌ی روند", "خبر به مدیر کل")) { com.coinepro.hq.ui.automation.FlowMapScreen(STORIES) },
            "map-run" to Scene(listOf("منتظر ساعت انتشار", "منتظر ساعتش", "جا ماند"), hides = listOf("دوباره از همین قدم", "منتظر مُهر تو")) {
                com.coinepro.hq.ui.automation.FlowRunScreen("F-0029")
            },
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
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-11-15T08:30:00Z")
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.link.setForeground(false)
        graph.enterDemo()
        DemoLive.servers?.still = true
    }

    private fun settle(rounds: Int) = repeat(rounds) {
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
        // the flow, its days and the chosen day's run: three demo answers of ~60 ms on OkHttp threads
        settle(20)
        scene.act?.let { it(compose); settle(8) }
        for (t in scene.shows) assertTrue("$name shows «$t»", compose.onAllNodesWithText(t, substring = true).fetchSemanticsNodes().isNotEmpty())
        for (t in scene.hides) assertTrue("$name does not show «$t»", compose.onAllNodesWithText(t, substring = true).fetchSemanticsNodes().isEmpty())
        if (name == "map-stories") {
            // every node of the hub's graph is on the canvas, each with that day's state in its corner
            assertEquals(18, compose.onAllNodesWithTag("map-node").fetchSemanticsNodes().size)
            // the hour, the account, the budget and the replies are the hub's Claude's to set (§59.7.1): no settings card
            assertTrue(compose.onAllNodesWithTag("flow-settings").fetchSemanticsNodes().isEmpty())
            assertEquals(3, compose.onAllNodesWithTag("state-waiting", useUnmergedTree = true).fetchSemanticsNodes().size - 1)
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
