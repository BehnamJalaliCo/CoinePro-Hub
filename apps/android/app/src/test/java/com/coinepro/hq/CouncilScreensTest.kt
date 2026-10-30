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
import com.coinepro.hq.ui.media.VoiceResult
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
 * ⟨1.9⟩ Contract §27, night and day, with the demo holding: «با کدام مدل؟» in the new order (Gemini chosen while it is limited: greyed,
 * its reason and the 30-minute wait; the council, its seated players' logos), the voice order that named its player («با جمنای» heard,
 * the chip set) and the hub turning a recording into words when the phone could not; an order given to GPT; a council of four (Gemini
 * kept out by its cap) on its page and its «شورا» section with Claude's synthesis (agree, differ, the recommendation); a media council's
 * two images side by side to pick and animate.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class CouncilScreensTest(private val name: String, private val night: Boolean) {
    companion object {
        private const val ORDER_GPT = "W-000197"
        private const val ORDER_COUNCIL = "W-000198"
        private const val ORDER_MEDIA = "W-000199"
        private const val SPOKEN = "با جمنای سه تصویر استوری برای دوره‌ی رایگان طلای FX بساز تا عصر."

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            "order-player" to { _ ->
                Sheetlike { com.coinepro.hq.ui.work.NewOrderContent({}, company0 = "FX", title0 = "سه تصویر استوری برای دوره‌ی طلا", priority0 = "P3", player0 = "gemini") }
            },
            "order-player-council" to { _ ->
                Sheetlike { com.coinepro.hq.ui.work.NewOrderContent({}, company0 = "TY", title0 = "پشتیبانی زنده‌ی ۲۴ ساعته: ارزش هزینه‌اش را دارد؟", priority0 = "P2", player0 = "council") }
            },
            "voice-order-heard" to { _ ->
                Sheetlike { com.coinepro.hq.ui.work.VoiceOrderBody({}, listen = false, text0 = SPOKEN, voice0 = VoiceResult(SPOKEN, null, 6.2, "phone")) }
            },
            "voice-order-hub" to { _ -> Sheetlike { com.coinepro.hq.ui.work.VoiceOrderBody({}, listen = false, hubTranscribing0 = true) } },
            "order-gpt" to { _ -> com.coinepro.hq.ui.companies.WorkScreen(ORDER_GPT) },
            "order-council" to { _ -> com.coinepro.hq.ui.companies.WorkScreen(ORDER_COUNCIL) },
            "order-council-section" to { _ -> Cardlike { WithWork(ORDER_COUNCIL) { com.coinepro.hq.ui.work.CouncilCard(it) } } },
            "order-council-media" to { _ -> Cardlike { WithWork(ORDER_MEDIA) { com.coinepro.hq.ui.work.CouncilCard(it) } } },
        )

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCREENS.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }

        /** A work as the demo serves it. */
        @Composable
        private fun WithWork(ref: String, content: @Composable (Work) -> Unit) {
            com.coinepro.hq.ui.rememberQuery("work:$ref", "work") { workOne(ref) }.data?.let { content(it) }
        }

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
        // Demo responses take ~150 ms each on OkHttp threads (the work, then its council, then each answer); let them land.
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
