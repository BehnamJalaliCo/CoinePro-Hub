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
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.core.net.PairCode
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
 * ⟨1.8⟩ The companies' servers (contract §26, a runner on each), night and day, with the demo holding's servers awake: every company's
 * servers (online, pending, offline, revoked) with the card waiting for the seal; a company's «سرورها» tab, running and stopped; a server's
 * map in §26.5's shape (and its lower sections, and TradeYar's map written as the shell prints it), its jobs live, its Claude Code
 * sessions, a pending and locked one and an offline one; a Claude session on TradeYar's server; the owner's terminal after `docker ps`;
 * pairing a server (a code typed, an expired one, then the wait for its runner); the server rules with one change; the seal card in the
 * cartable and on its own page; a task for the server in one of its repositories; the control room's servers card. ⟨§26.6⟩ The holding's
 * network map: the demo's (one road broken, one server outside the private network), a server tapped, a check under way, a healthy one.
 * Every server is named by its company (the owner's rule), its own name after it only when the company has several.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class ServersScreensTest(private val name: String, private val night: Boolean) {
    companion object {
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
            // One job in each state of §26.2 (and its folder), from FX's and TradeYar's activity.
            "server-jobs" to { _ ->
                Cardlike {
                    val fx = com.coinepro.hq.ui.rememberQuery("server:activity:srv-fx-1::", "servers") { serverActivity("srv-fx-1") }.data?.items.orEmpty()
                    val ty = com.coinepro.hq.ui.rememberQuery("server:activity:srv-ty-1::", "servers") { serverActivity("srv-ty-1") }.data?.items.orEmpty()
                    val rows = (fx + ty).map { com.coinepro.hq.core.net.callRow(it) }.distinctBy { it.outcome }
                    if (rows.isNotEmpty()) com.coinepro.hq.designsystem.HqCard(Modifier, padding = androidx.compose.foundation.layout.PaddingValues(horizontal = 14.dp, vertical = 4.dp)) {
                        rows.forEachIndexed { i, r ->
                            if (i > 0) androidx.compose.material3.HorizontalDivider(color = Divan.colors.lineDivider)
                            com.coinepro.hq.ui.servers.CallLine(r)
                        }
                    }
                }
            },
            "server-sessions" to { _ -> com.coinepro.hq.ui.servers.ServerScreen("srv-ty-1", tab0 = "sessions") },
            "server-pending" to { _ -> com.coinepro.hq.ui.servers.ServerScreen("srv-pc-1") },
            "server-offline" to { _ -> com.coinepro.hq.ui.servers.ServerScreen("srv-fx-2") },
            "server-session" to { _ -> com.coinepro.hq.ui.workshop.SessionScreen("S-0011") },
            "server-terminal" to { _ -> com.coinepro.hq.ui.servers.TerminalScreen("srv-fx-1", run0 = "docker ps") },
            "server-attach" to { _ -> com.coinepro.hq.ui.servers.AttachScreen(company0 = "TY", code0 = "ty7km4qd") },
            "server-attach-expired" to { _ ->
                com.coinepro.hq.ui.servers.AttachScreen(
                    company0 = "FX", code0 = "Q2WX-0000",
                    error0 = PairCode.refusal(com.coinepro.hq.core.net.ApiException(410, "expired_token", "")),
                )
            },
            "server-attach-wait" to { _ ->
                com.coinepro.hq.ui.servers.AttachScreen(
                    out0 = HubServer("srv-ty-9", "TY", "ty-media", privateIp = "10.10.1.9", user = "tradeyar", hostname = "ty-media", runnerVersion = "0.1.0", state = "pending"),
                )
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
                        cwd0 = "/home/tradeyar/TradeYar",
                    )
                }
            },
            // ⟨1.8⟩ §26.6 the holding's network: the demo's map (Pro-Chart cannot open FX's SSH port, IG-Hub outside the private network),
            // Pro-Chart tapped (its roads port by port), a check half answered, and a healthy network.
            "network" to { _ -> com.coinepro.hq.ui.servers.NetworkScreen() },
            // A tapped server's card (below the map on the page): Pro-Chart, whose SSH to FX is refused; IG-Hub, outside the network.
            "network-node" to { _ -> NetNode("srv-pc-1") },
            "network-node-outside" to { _ -> NetNode("srv-ig-1") },
            "network-checking" to { _ ->
                val m = com.coinepro.hq.ui.servers.rememberNetwork().data
                if (m != null) com.coinepro.hq.ui.servers.NetworkScreen(
                    check0 = com.coinepro.hq.ui.servers.NetCheckRun(m, com.coinepro.hq.core.net.CheckProgress(m.servers.map { it.id }.toSet(), setOf("srv-fx-1", "srv-ty-1")), waitedMs = 6_000),
                )
            },
            "network-all-ok" to { _ ->
                val m = com.coinepro.hq.ui.servers.rememberNetwork().data
                if (m != null) com.coinepro.hq.ui.servers.NetworkScreen(map0 = healthy(m))
            },
            "server-control-cards" to { _ ->
                Cardlike {
                    com.coinepro.hq.ui.servers.ServersControlCard("FX", stopped = false) {}
                    com.coinepro.hq.ui.servers.ServersControlCard("PC", stopped = true) {}
                    com.coinepro.hq.ui.servers.ServersControlCard(null, stopped = false) {}
                }
            },
        )

        /** The demo's network as it is once IG-Hub joins the private network (at 10.10.1.5) and FX opens its SSH port to Pro-Chart. */
        private fun healthy(m: com.coinepro.hq.core.net.NetworkMap): com.coinepro.hq.core.net.NetworkMap {
            val nodes = m.nodes.map { if (it.outside) it.copy(privateIp = "10.10.1.5", via = "private", hubRttMs = 2.6) else it }
            val servers = nodes.filter { !it.isHub }
            val at = m.links.mapNotNull { it.at }.max()
            val links = servers.flatMap { f ->
                listOf(com.coinepro.hq.core.net.NetLink(f.id, "hub", 443, true, (f.hubRttMs ?: 2.0) + 0.6, null, at)) +
                    servers.filter { it.id != f.id }.flatMap { t -> listOf(22, 80, 443).map { p -> com.coinepro.hq.core.net.NetLink(f.id, t.id, p, true, 0.4 + (p % 7) / 10.0, null, at) } }
            }
            return m.copy(nodes = nodes, links = links)
        }

        @Composable
        private fun NetNode(id: String) {
            Cardlike {
                val m = com.coinepro.hq.ui.servers.rememberNetwork().data
                val names = com.coinepro.hq.ui.servers.rememberNetNames(m)
                m?.node(id)?.let { com.coinepro.hq.ui.servers.NodeDetail(m, it, names) {} }
            }
        }

        /** Screens drawn with animations held still: the check's sparks and the live dots stop where they rest. */
        private val STILL = setOf("network", "network-node", "network-node-outside", "network-checking", "network-all-ok")

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
                CompositionLocalProvider(
                    LocalEnv provides graph.env.value, LocalToasts provides Toasts(), LocalNav provides nav,
                    com.coinepro.hq.designsystem.LocalReducedMotion provides (name in STILL || com.coinepro.hq.designsystem.LocalReducedMotion.current),
                ) {
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
