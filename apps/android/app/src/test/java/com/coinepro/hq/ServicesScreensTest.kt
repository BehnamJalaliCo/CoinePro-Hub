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
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.net.HubBlocking
import com.coinepro.hq.core.net.HubJob
import com.coinepro.hq.core.net.HubMemory
import com.coinepro.hq.core.net.HubService
import com.coinepro.hq.core.net.HubServices
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.services.Refused
import com.coinepro.hq.ui.services.RefusedBody
import com.coinepro.hq.ui.services.ServicesBody
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
 * ⟨1.20⟩ Contract §38.3, night and day, drawn tall (1600dp): «سرویس‌ها» with the demo hub (the memory, the optional services on and off
 * with their switches, the core ones read-only); two switches running («در حال …»); a hub whose dispatcher never reported (switches off,
 * «بخش سرور هنوز نصب نشده است»); and the refused sheet with its one-tap swap.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h1600dp-xxhdpi")
class ServicesScreensTest(private val name: String, private val night: Boolean) {
    companion object {
        private fun svc(key: String, title: String, what: String, state: String, cap: Double, used: Double?, optional: Boolean = true) =
            HubService(key, title, what, state, optional, cap, used, optional, null)

        private val SERVICES = listOf(
            svc("media", "ساخت ویدیو و کاور", "ریلز، کاور و ویدیوی کوتاه را میسازد.", "on", 3072.0, 1840.0),
            svc("stt", "تبدیل گفتار به متن", "صدای تو را روی خود هاب به متن دقیق فارسی برمیگرداند.", "off", 3584.0, null),
            svc("tts", "صدای ساده‌ی هاب", "وقتی سقف صدای جمینای پر شد، هاب با صدای خودش حرف میزند.", "starting", 512.0, null),
            svc("ocr", "خواندن اسکن بایگانی", "متن سندهای اسکن‌شده را میخواند.", "failed", 1024.0, null),
            svc("api", "هسته‌ی هاب", "همه‌ی کارهای اپ و ایجنت‌ها از این میگذرد.", "on", 1024.0, 610.0, optional = false),
        )

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            // The demo hub: 16 GB, a 12 GB budget; video, voice, newsletter and n8n on; speech to text, OCR, MCP and tracing off.
            "services" to { _ -> com.coinepro.hq.ui.services.ServicesScreen() },
            // Two switches on their way («در حال روشن شدن…», «در حال خاموش شدن…»), one starting, one failed.
            "services-pending" to { _ ->
                Sheetlike(Divan.colors.page) {
                    ServicesBody(HubServices(HubMemory(16384.0, 12288.0, 11200.0, 1088.0), SERVICES, "2026-11-06T08:29:20Z"), mapOf("stt" to true, "media" to false)) { _, _ -> }
                }
            },
            // The dispatcher has never reported: no memory, every switch disabled.
            "services-not-installed" to { _ -> Sheetlike(Divan.colors.page) { ServicesBody(HubServices(null, SERVICES, null), emptyMap()) { _, _ -> } } },
            // Speech to text does not fit: what holds the memory, largest first, and «… را خاموش کن و … را روشن کن».
            "services-refused" to { _ ->
                Sheetlike(Divan.colors.overlay) {
                    Text("جا نیست؛ این‌ها جا را گرفته‌اند", style = Divan.type.h3)
                    val job = HubJob(
                        "HJ-0007", "refused", "جا نیست؛ این‌ها جا را گرفته‌اند",
                        listOf(HubBlocking("media", "ساخت ویدیو و کاور", 3072.0), HubBlocking("automations", "خودکارسازی (n8n)", 768.0), HubBlocking("tts", "صدای ساده‌ی هاب", 512.0), HubBlocking("newsletter", "خبرنامه", 256.0)),
                    )
                    RefusedBody(Refused(SERVICES[1], true, job), 2944.0, {}) {}
                }
            },
        )

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCREENS.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }

        @Composable
        private fun Sheetlike(bg: androidx.compose.ui.graphics.Color, content: @Composable () -> Unit) {
            Column(Modifier.fillMaxSize().background(bg).verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) { content() }
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
        repeat(12) {
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
