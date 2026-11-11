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
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.net.Canvas
import com.coinepro.hq.core.net.CanvasNode
import com.coinepro.hq.core.net.CompanyLink
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * ⟨1.17⟩ Contract §35.5–§35.6, night and day, with the demo holding, drawn tall (1600dp): the owner's office whole (⟨1.0.1⟩ what waits
 * for him answered in place, the pulse in one row, the command row, the sessions as cards in three states, the canvas, the money line and
 * the suggestions); the command row and its sheet with words in it; the canvas alone with its links (one off, one placed by the owner); the sessions list and the
 * archive.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h1600dp-xxhdpi")
class OfficeScreensTest(private val name: String, private val night: Boolean) {
    companion object {
        private val CANVAS = Canvas(
            nodes = listOf(
                CanvasNode("HQ", "هلدینگ کوینه‌پرو", "holding", openSessions = 2),
                CanvasNode("TY", "تریدیار", openSessions = 1),
                CanvasNode("FX", "کوینه‌پرو FX", x = 0.2, y = 0.72),
                CanvasNode("PC", "پرو-چارت", openSessions = 1),
            ),
            links = listOf(
                CompanyLink("1", "TY", "FX", "publishes", "ریلزها در کانال FX", openWorks = 2),
                CompanyLink("2", "PC", "TY", "feeds", "داده‌ی چارت", openWorks = 1),
                CompanyLink("3", "FX", "PC", "sells", "اشتراک پرو-چارت", state = "off"),
            ),
        )

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            "office" to { _ -> com.coinepro.hq.ui.office.OfficeScreen() },
            // ⟨1.0.1⟩ C2.1: the home's one-row command entry, and under it the sheet it opens with words in it (the sheet's every state is
            // in LookScreensTest).
            "office-command" to { _ ->
                Cardlike {
                    com.coinepro.hq.ui.look.CommandRow()
                    val s = androidx.compose.runtime.remember {
                        com.coinepro.hq.ui.look.CommandState(com.coinepro.hq.ui.look.CommandOpen(text = "برای کوینه‌پرو FX یک پشتیبان تلگرامی بگذار که شب‌ها هم جواب بدهد")).apply { picked = listOf("FX"); pace = "step" }
                    }
                    val companies = com.coinepro.hq.ui.rememberCompanies().filter { it.kind != "holding" }
                    com.coinepro.hq.designsystem.SpringSheetPreview(com.coinepro.hq.core.data.COMMAND_FA, bar = { com.coinepro.hq.ui.look.CommandDecisionBar(s, companies, {}, {}, {}) }) {
                        com.coinepro.hq.ui.look.CommandFields(s, companies, routineOn = true)
                    }
                }
            },
            "office-canvas" to { _ -> Cardlike { com.coinepro.hq.ui.office.CanvasCard(CANVAS, editable = true) } },
            "sessions-open" to { _ -> com.coinepro.hq.ui.session.SessionsScreen() },
            "sessions-archive" to { _ -> com.coinepro.hq.ui.session.SessionsScreen(tab0 = "closed") },
        )

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCREENS.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }

        @Composable
        private fun Cardlike(content: @Composable () -> Unit) {
            Column(
                Modifier.fillMaxSize().background(Divan.colors.page).verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) { content() }
        }
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

    @Test
    fun screen() {
        val nav = object : Nav {
            override fun go(route: String) = Unit
            override fun back() = Unit
        }
        compose.mainClock.autoAdvance = false
        compose.setContent {
            DivanTheme(night) {
                CompositionLocalProvider(
                    LocalEnv provides graph.env.value, LocalToasts provides Toasts(), LocalNav provides nav,
                    com.coinepro.hq.designsystem.LocalReducedMotion provides true,
                ) {
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { SCREENS.getValue(name)(graph) }
                }
            }
        }
        // Demo answers take ~60–150 ms each on OkHttp threads (the office, then the companies, the presence); let them all land.
        repeat(16) {
            Thread.sleep(200)
            shadowOf(Looper.getMainLooper()).idle()
            compose.mainClock.advanceTimeBy(250)
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
