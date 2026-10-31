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
import com.coinepro.hq.core.net.Work
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
 * ⟨1.10⟩ Contract §28, night and day, with the demo holding: the outputs in selection mode (three checked, the bar on top, the actions
 * at the bottom) and the delete's confirmation; TradeYar's full catalogue and FX's before its first run; the watch with its findings
 * by kind; a council where only Claude answered (raw JSON and an English error read «پاسخ نداد», a Persian reason as given) and a
 * reason's details opened; «ارسال خطاها به ستاد» on and off.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class CleanupScreensTest(private val name: String, private val night: Boolean) {
    companion object {
        private const val RAW = """{"error":{"type":"invalid_request_error","code":"model_not_found","message":"The model `gpt-5.3` is not supported when using Codex with a ChatGPT account."}}"""

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            "outputs-select" to { _ -> com.coinepro.hq.ui.outputs.OutputsScreen("all", select0 = setOf("O-000031", "O-000029", "O-000043")) },
            "outputs-delete" to { _ ->
                Sheetlike {
                    val q = com.coinepro.hq.ui.rememberQuery("deliverables:del", "deliverables") { deliverables(limit = 50) }
                    q.data?.items?.filter { it.ref in setOf("O-000031", "O-000029", "O-000043") }?.let { ds ->
                        androidx.compose.material3.Text("حذف ${ds.size} خروجی برای همیشه", style = Divan.type.h2, modifier = Modifier.padding(bottom = 14.dp))
                        com.coinepro.hq.ui.outputs.DeleteOutputsContent(ds, onCancel = {}) {}
                    }
                }
            },
            "catalogue" to { _ -> com.coinepro.hq.ui.companies.CatalogueScreen("TY") },
            "catalogue-empty" to { _ -> com.coinepro.hq.ui.companies.CatalogueScreen("FX") },
            "watch" to { _ -> com.coinepro.hq.ui.oversight.WatchScreen() },
            "council-failed" to { _ ->
                Cardlike {
                    com.coinepro.hq.ui.work.CouncilCard(Work("w-000200", "W-000200", "TY", title = "سرور تریدیار را بگرد و همه‌چیز را دربیاور", status = "delivered", mode = "council"))
                }
            },
            "council-reason-details" to { _ ->
                Cardlike {
                    com.coinepro.hq.ui.work.ReasonLine(com.coinepro.hq.core.data.memberReasonFa(RAW)!!, Divan.colors.negative, open0 = true)
                    com.coinepro.hq.ui.work.ReasonLine(com.coinepro.hq.core.data.memberReasonFa("مدل gpt-5.3 با اشتراک ChatGPT پشتیبانی نمیشود؛ با مدل پیش‌فرض دوباره امتحان شد")!!, Divan.colors.textMuted)
                }
            },
            "settings-error-report" to { _ ->
                Cardlike {
                    com.coinepro.hq.ui.settings.ErrorReportCard(true, {}, 12, 3)
                    com.coinepro.hq.ui.settings.ErrorReportCard(false, {}, 12, 0)
                }
            },
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
        // Demo responses take ~150 ms each on OkHttp threads; let them land.
        repeat(18) {
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
