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
import com.coinepro.hq.core.net.AttachIn
import com.coinepro.hq.core.net.AttachOut
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.core.net.ServerPolicy
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.servers.rememberServers
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
 * ⟨1.8⟩ The companies' servers (contract §26), night and day, with the demo holding's servers awake: every company's servers with the
 * card waiting for the seal; a company's «سرورها» tab, running and stopped; a server's map (and its lower sections, and TradeYar's map
 * written as the shell prints it), its live activity, its Claude Code sessions and a pending, locked one; a Claude session on TradeYar's
 * server; the owner's terminal after `docker ps`; attaching a server (a refused address, then the key to hand on); the server rules with
 * one change; the seal card in the cartable and on its own page; a task for the server; the control room's servers card.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class ServersScreensTest(private val name: String, private val night: Boolean) {
    companion object {
        private val KEY = "SHA256:Ze4Tn8Qa1LmW6xVb0RkJy3Ps9DfGh5Uc2oNiE7tKsHw"

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            "servers" to { _ -> com.coinepro.hq.ui.servers.ServersScreen() },
            "company-servers" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("FX", tab0 = "servers") },
            "company-servers-locked" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("PC", tab0 = "servers") },
            "server-map" to { _ -> com.coinepro.hq.ui.servers.ServerScreen("srv-fx-1") },
            "server-map-lower" to { _ ->
                Cardlike {
                    val m = com.coinepro.hq.ui.servers.rememberServerMap("srv-fx-1").data
                    m?.let { com.coinepro.hq.ui.servers.MapView(it.copy(containers = emptyList(), compose = emptyList())) }
                }
            },
            "server-map-shell" to { _ ->
                Cardlike { com.coinepro.hq.ui.servers.rememberServerMap("srv-ty-1").data?.let { com.coinepro.hq.ui.servers.MapView(it) } }
            },
            "server-activity" to { _ -> com.coinepro.hq.ui.servers.ServerScreen("srv-fx-1", tab0 = "activity") },
            "server-sessions" to { _ -> com.coinepro.hq.ui.servers.ServerScreen("srv-ty-1", tab0 = "sessions") },
            "server-pending" to { _ -> com.coinepro.hq.ui.servers.ServerScreen("srv-pc-1") },
            "server-session" to { _ -> com.coinepro.hq.ui.workshop.SessionScreen("S-0011") },
            "server-terminal" to { _ -> com.coinepro.hq.ui.servers.TerminalScreen("srv-fx-1", run0 = "docker ps") },
            "server-attach" to { _ -> com.coinepro.hq.ui.servers.AttachScreen(form0 = AttachIn("TY", "ty-media", "5.161.20.4", "root", "256 SHA256:abc root@ty (ED25519)"), tried0 = true) },
            "server-attach-key" to { _ ->
                com.coinepro.hq.ui.servers.AttachScreen(out0 = AttachOut(
                    HubServer("srv-pc-1", "PC", "pc-app", privateIp = "10.10.1.1", user = "prochart", hostKeySha256 = KEY),
                    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHq9dm0Hn4pXr2vT8kLw3sB6yZcJ1fGe5uQ7aN0oRiPx hq-company-ops@PC:pc-app",
                ))
            },
            "server-policy" to { _ -> com.coinepro.hq.ui.servers.ServerPolicyScreen(draft0 = ServerPolicy().with("access_change", false)) },
            "server-seal-cartable" to { _ -> com.coinepro.hq.ui.cartable.CartableScreen() },
            "server-seal-decision" to { _ -> com.coinepro.hq.ui.cartable.DecisionScreen("D-000201") },
            "server-task" to { _ ->
                Sheetlike {
                    val ty = rememberServers().data?.firstOrNull { it.id == "srv-ty-1" }
                    if (ty != null) com.coinepro.hq.ui.servers.ServerTaskContent(
                        listOf(ty), ty, onDone = {}, title0 = "انتشار نسخه‌ی تازه‌ی سایت",
                        brief0 = "آخرین main را بگیر، تست‌ها را اجرا کن، با docker compose بالا بیاور و سلامت tradeyar.com را بسنج.", driver0 = "TY-TECH-MGR",
                    )
                }
            },
            "server-control-cards" to { _ ->
                Cardlike {
                    com.coinepro.hq.ui.servers.ServersControlCard("FX", stopped = false) {}
                    com.coinepro.hq.ui.servers.ServersControlCard("PC", stopped = true) {}
                    com.coinepro.hq.ui.servers.ServersControlCard(null, stopped = false) {}
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
            Column(Modifier.fillMaxSize().background(Divan.colors.overlay).verticalScroll(rememberScrollState()).padding(16.dp)) { content() }
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
        // The demo's servers wake on the first look at one; these screens all look, so they start awake.
        DemoLive.servers!!.wake()
        DemoLive.servers!!.raiseSeal()
        DemoLive.servers!!.still = true
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
                CompositionLocalProvider(LocalEnv provides graph.env.value, LocalToasts provides Toasts(), LocalNav provides nav) {
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { SCREENS.getValue(name)(graph) }
                }
            }
        }
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
