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
import com.coinepro.hq.core.net.StepOutput
import com.coinepro.hq.core.net.StepRun
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
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
 * ⟨1.12⟩ Contract §30, night and day, with the demo holding, drawn tall (1600dp): a company's lines tab, the template gallery, a line's
 * editor (prompt with variables, the speaker picker), the result of one step's test, a run waiting for the owner's seal with every kind
 * of output, the calendar and the library.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h1600dp-xxhdpi")
class V30ScreensTest(private val name: String, private val night: Boolean) {
    companion object {
        private val TEST = StepRun(
            key = "script", kind = "gpt_text", state = "done", tokens = 1200, usdEquiv = JsonPrimitive("0.03"), via = "چت‌جی‌پی‌تی",
            output = StepOutput(
                text = "**نمونه‌ی آزمایشی:** طلا امروز در محدوده‌ی 2000 دلار نوسان کرد.\n\n- حمایت نزدیک: 1980\n- مقاومت نزدیک: 2030",
                data = JsonObject(mapOf("verdict" to JsonPrimitive("تکراری نیست"), "checked" to JsonPrimitive(40))),
            ),
        )

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            "v30-company-lines" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("TY", tab0 = "lines") },
            "v30-template-gallery" to { _ -> Sheetlike { com.coinepro.hq.ui.v30.TemplateGallery("TY") {} } },
            "v30-line-editor" to { _ -> com.coinepro.hq.ui.v30.LineScreen("LN-0001", open0 = setOf("script", "voice")) },
            "v30-step-test" to { _ -> Cardlike { com.coinepro.hq.ui.v30.StepTestResult(TEST) } },
            "v30-run-waiting" to { _ -> com.coinepro.hq.ui.v30.LineRunScreen("LR-000003", open0 = setOf("script", "voice", "render", "cover", "publish")) },
            "v30-calendar" to { _ -> com.coinepro.hq.ui.v30.CalendarScreen() },
            "v30-library" to { _ -> com.coinepro.hq.ui.v30.LibraryScreen() },
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

        @Composable
        private fun Sheetlike(content: @Composable () -> Unit) {
            Column(
                Modifier.fillMaxSize().background(Divan.colors.overlay).verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) { content() }
        }
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-10-17T08:30:00Z")
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
        // Demo responses take ~150 ms each on OkHttp threads (a page, then what it opens: the group's members, runs, KPIs, each readiness);
        // the secretary's preview waits 650 ms of the test clock first. Let them all land.
        repeat(22) {
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
