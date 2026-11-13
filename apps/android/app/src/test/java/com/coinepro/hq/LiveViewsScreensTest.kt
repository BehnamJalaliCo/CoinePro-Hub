package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performScrollToKey
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.data.CompanyLive
import com.coinepro.hq.core.data.LiveState
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
 * ⟨1.24⟩ Contract §42 ⟨0.20.0⟩, design/LIVE_VIEWS.md's twelve P0 views, at a phone's width, night and day, with the demo holding and its
 * live script on the stream (an order to TradeYar, FX asking TradeYar through the hub, FX's server dropping, people working and stuck,
 * token ticks). Each scene in full motion (its clock held, so a particle is caught mid-flight at the same point every run) and with
 * animations removed (particles become edge tints and «×n», loops still glyphs and words):
 * - the office: the pulse (OF-1), the companies' live cards (CO-1, PE-1) and the token meter (MO-1);
 * - the holding's live map (HM-1, HM-2, HM-3): the hub's seal, the ring, FX's server red with «قطع · time», flows in flight; its table
 *   (HM-8); the map frozen («قدیمی · ۲ دقیقه», GL-1); forty companies on two rings with «بقیه · n»;
 * - the shell's bands: the heartbeat (GL-1), the kill switch's band (GL-2, Pro-Chart is stopped in the demo), the urgent banner (NO-1).
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h1500dp-xxhdpi")
class LiveViewsScreensTest(private val name: String, private val night: Boolean) {
    /** A scene: what it shows, its words to check, whether animations are removed, and how the stream plays around it. */
    private class Scene(
        val shows: List<String>,
        val reduced: Boolean,
        /** The live script's beats played before the screen is drawn (state only, nothing flies). */
        val before: Int = 0,
        /** Beats played once it is on screen (they fly), then the clock is moved [flyMs] into their flight. */
        val after: IntRange? = null,
        val flyMs: Long = 450,
        val down: Long? = null,
        /** ⟨1.0.1⟩ The item of the page's list the picture starts at (the live parts of the office are under what waits for the owner). */
        val from: String? = null,
        val content: @Composable () -> Unit,
    )

    companion object {
        /** Forty companies (owner rule 9: any number), busiest first, to see the ring's capacity, its second ring and «بقیه · n». */
        private fun forty(): Pair<List<String>, LiveState> {
            val codes = (1..40).map { "C" + it.toString().padStart(2, '0') }
            val live = LiveState(
                seeded = true,
                companies = codes.withIndex().associate { (i, c) -> c to CompanyLive(c, "شرکت ${i + 1}", working = (40 - i) % 7, total = 8, serversOnline = 1, serversTotal = 1) },
            )
            return codes to live
        }

        private val SCENES: Map<String, Scene> = linkedMapOf(
            "live-office" to Scene(listOf("کار میکنند", "جلسه‌ی باز", "منتظر تو"), reduced = false, before = 30, from = "pulse") { Office() },
            "live-office-reduced" to Scene(listOf("کار میکنند", "جلسه‌ی باز"), reduced = true, before = 30, from = "pulse") { Office() },
            // The token meter (past 70 %, the burn rate, a call in flight) and every company's live card (people by shape, servers, spend).
            "live-meter" to Scene(listOf("کنتور توکن، \u200Fامروز", "از ۷۰٪ گذشت", "شرکت‌ها، \u200Fزنده", "گیر کرده"), reduced = false, before = 20) { Meter() },
            "live-meter-reduced" to Scene(listOf("کنتور توکن، \u200Fامروز", "در حال مصرف", "شرکت‌ها، \u200Fزنده"), reduced = true, before = 20) { Meter() },
            "live-map" to Scene(listOf("نقشه‌ی زنده‌ی هلدینگ", "قطع"), reduced = false, before = 7, after = 7..19) { com.coinepro.hq.ui.servers.NetworkScreen() },
            "live-map-reduced" to Scene(listOf("نقشه‌ی زنده‌ی هلدینگ", "قطع", "×"), reduced = true, before = 7, after = 7..19) { com.coinepro.hq.ui.servers.NetworkScreen() },
            "live-map-table" to Scene(listOf("سرور قطع", "سرورها"), reduced = true, before = 20) { com.coinepro.hq.ui.servers.NetworkScreen(view0 = "table") },
            "live-map-stale" to Scene(listOf("قدیمی"), reduced = true, before = 20, down = 125_000) { com.coinepro.hq.ui.servers.NetworkScreen() },
            "live-map-forty" to Scene(listOf("بقیه"), reduced = true) {
                val (codes, live) = forty()
                Pad { com.coinepro.hq.ui.live.HoldingMap(null, live, frozen = false, codes0 = codes) }
            },
            "live-bands" to Scene(listOf("زنده", "قفل است", "دیدم"), reduced = true, before = 10) { Bands() },
        )

        @Composable
        private fun Office() = com.coinepro.hq.ui.office.OfficeScreen()

        @Composable
        private fun Meter() = Pad {
            Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                com.coinepro.hq.ui.live.TokenMeter()
                com.coinepro.hq.ui.live.LiveCompaniesCard()
            }
        }

        @Composable
        private fun Pad(content: @Composable () -> Unit) {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) { content() }
        }

        /** The shell's live parts, as the top of every screen shows them. */
        @Composable
        private fun Bands() {
            Column(Modifier.fillMaxSize().padding(vertical = 16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Box(Modifier.padding(horizontal = 16.dp)) { com.coinepro.hq.ui.live.LiveBeat() }
                com.coinepro.hq.ui.live.KillBand()
                com.coinepro.hq.ui.live.UrgentBanner(
                    com.coinepro.hq.ui.live.UrgentNow("دیسک سرور هاب از ۹۵٪ گذشت", "پایش ساعتی: ۹۵٫۲٪ پر؛ پشتیبان ساعتی در خطر است.", null), onSeen = {}, onOpen = {},
                )
                Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (s in listOf("thinking", "working", "waiting", "stuck", "done")) androidx.compose.foundation.layout.Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        com.coinepro.hq.ui.live.PersonGlyph(s, size = 14.dp)
                        androidx.compose.material3.Text(com.coinepro.hq.ui.live.personFa(s), style = Divan.type.caption)
                    }
                }
            }
        }

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCENES.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-11-08T08:30:00Z")
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
        val scene = SCENES.getValue(name)
        val stream = graph.env.value.stream
        // The store seeded from the demo's summary and the script's first beats applied (state only, before anything is on screen).
        stream.demoLive(0, scene.before)
        scene.down?.let { stream.demoDown(it) }
        compose.mainClock.autoAdvance = false
        compose.setContent {
            DivanTheme(night, reducedMotion = scene.reduced) {
                CompositionLocalProvider(LocalEnv provides graph.env.value, LocalToasts provides Toasts(), LocalNav provides nav) {
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { scene.content() }
                }
            }
        }
        settle(16)
        // ⟨1.0.1⟩ The office opens on what waits for the owner; its live parts (the pulse, the companies' live cards, the token meter)
        // are under it, so the picture starts at the pulse: each of the two pictures shows its own state again.
        scene.from?.let { key ->
            // ⟨1.1.0⟩ On a loaded CI runner (the whole suite: 1.0.3's red run) the office's answers land after the fixed settle above, and
            // its pulse is not there yet to scroll to: wait for it (at most ~10 s more) before anything flies, so the picture is the same.
            var waits = 0
            while (runCatching { compose.onAllNodes(androidx.compose.ui.test.hasScrollToKeyAction())[0].performScrollToKey(key) }.isFailure && waits++ < 40) settle(1)
            compose.onAllNodes(androidx.compose.ui.test.hasScrollToKeyAction())[0].performScrollToKey(key)
            settle(4)
        }
        // The beats that fly: played with the screen on, then the clock moved a fixed time into their flight.
        scene.after?.let { r ->
            for (t in r) for (e in Demo.next(t)) stream.demoDispatch(e)
            shadowOf(Looper.getMainLooper()).idle()
            compose.mainClock.advanceTimeBy(scene.flyMs)
            shadowOf(Looper.getMainLooper()).idle()
        }
        for (t in scene.shows) assertTrue("$name shows «$t»", compose.onAllNodesWithText(t, substring = true).fetchSemanticsNodes().isNotEmpty())
        compose.onRoot().captureRoboImage(
            "src/test/screenshots/$name-${if (night) "night" else "day"}.png",
            roborazziOptions = RoborazziOptions(
                recordOptions = RoborazziOptions.RecordOptions(resizeScale = 0.5),
                compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.002f),
            ),
        )
    }
}
